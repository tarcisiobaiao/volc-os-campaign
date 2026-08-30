"""O cliente de LLM real da geração de copy — o que `mock.py` finge, este faz.

## O contrato, e por que ele é tão pequeno

`ciclo.Cliente` pede um método: `gerar(sistema, usuario) -> str`. Texto entra,
texto sai. Toda a inteligência de o que fazer com uma resposta ruim mora na
cascata, e é por isso que a cascata inteira já foi provada contra o mock antes de
existir uma chave: trocar `ClienteMock` por `ClienteLLM` não muda um caminho de
decisão.

## As quatro coisas que este arquivo NÃO faz

1. ~~**Não retenta transporte.**~~ **CORRIGIDO em 19/08/2026 — ver `_http`.**

   Este item afirmava que `TRANSIENT` e `THROTTLED` eram resolvidos pela
   `PoliticaRetry` de `gads/client.py`, e que retentar aqui produziria backoff
   ao quadrado. Verdade para o caminho do Google Ads, e SÓ para ele:
   `PoliticaRetry` é usada em `volc_ads/subir.py` e nunca tocou a cascata de
   copy. Em `escrever() → ciclo → cliente.gerar() → _http` não havia ninguém
   retentando — o item descrevia um orquestrador que não existe.

   O preço disso foi medido no card 65: `RemoteProtocolError: Server
   disconnected without sending a response`, diário vazio, `segundos` nulo. A
   cascata inteira caiu por uma queda de tubo de um instante, levando junto os
   tokens já pagos.

   Agora `_http` retenta o que é TRANSITÓRIO (queda de conexão, timeout, 429,
   5xx) e só isso: um 400 ou 403 sobe na primeira, porque repetir um payload
   malformado ou uma chave inválida só esconde o motivo.

   ⚠️ E uma exceção dentro da exceção: `TuboMudo` — a conexão que cai SEM UM
   BYTE — não é retentada. Parece queda de rede e não é: o servidor corta aos
   ~60 s quando o modelo ainda está pensando, e as três tentativas caem no mesmo
   lugar (medido 3/3: 60,8 · 61,0 · 60,8 s). Quem conserta é a
   `ESCADA_DE_PENSAMENTO`, que faz o modelo COMEÇAR A FALAR mais cedo.

2. **Não julga conteúdo.** Resposta ilegível volta como TEXTO CRU. Quem diz que o
   JSON não presta é `extract_json` dentro do `ciclo.py`, que já sabe refazer o
   conjunto (uma vez) ou desistir daquele asset. Se este arquivo levantasse
   exceção em resposta ilegível, dois caminhos provados morreriam de uma vez: o
   `bruto = cliente.gerar(...)` da rodada 1 não está dentro de `try`, e o
   `except ValueError` do `_regenerar` passaria a chamar "modelo escreveu
   bobagem" o que na verdade foi queda de rede.

3. **Não monta prompt** (`render.py`) e **não confere saída** (`contrato.py`).

4. **Não inventa preço.** Ver `Config.preco_*`: sem preço configurado, o custo
   sai `None` e a tela mostra "preço não configurado" em vez de um número
   plausível. Tokens e latência são medidos de verdade, sempre.

## Por que não reusar `app.llm.gemini.GeminiClient` inteiro

Ele resolve credencial, modelo e timeout — e isso NÃO é duplicado aqui: `Config`
lê o mesmo `app.config.Settings`, com os mesmos nomes de variável. O que ele não
faz é devolver `usageMetadata`: `complete()` retorna só o texto e joga o consumo
fora. Sem token não há custo, e custo é requisito de tela (o SPEC pede quatro
casas decimais, US$ 0,0026 a US$ 0,4556). Por isso a chamada HTTP mora aqui —
síncrona, porque `ciclo.Cliente` é síncrono e embrulhar `asyncio.run()` numa
cascata que roda dentro de uma rota FastAPI é um travamento esperando acontecer.

⚠️ **A chave do LLM mora em `backend/.env`, não na raiz.** Rodando
`python -m volc_ads...` da raiz, um `Settings()` puro leria o `.env` da raiz — que
só tem chave do Supabase — e o cliente nasceria sem chave dizendo "não
configurado". Por isso `Config.do_ambiente()` passa `_env_file` explícito, com o
`backend/.env` por último (o último ganha).

Uso:
    from volc_ads.copy.cliente import criar
    cliente = criar()                      # lê Settings; erra claro se faltar chave
    resultado = ciclo.gerar(cliente=cliente, juiz=..., pedido=..., prompt_usuario=...)
    print(cliente.resumo())                # tokens, latência e custo por papel
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from ..ponte import BACKEND, RAIZ, extract_json
from .mock import SISTEMA_ASSET, SISTEMA_COMPLETO

# ── os dois papéis viram instrução de sistema de verdade ────────────────────
# `ciclo.py` passa `SISTEMA_COMPLETO` / `SISTEMA_ASSET`, que são RÓTULOS DE PAPEL
# — o mock os usa para contar quantas gerações foram de conjunto e quantas de
# asset. Mandá-los crus para a API entregaria ao modelo a system instruction
# "gerador-de-copy:conjunto", que não instrui nada e queima o slot mais forte que
# a chamada tem. O mapa traduz; string desconhecida passa literal, para quem
# quiser usar este cliente com um system prompt próprio.
SISTEMAS = {
    SISTEMA_COMPLETO: (
        "Você é o gerador de copy de Search do Volc OS. A mensagem do usuário é o "
        "documento inteiro que rege esta tarefa — siga-o à letra, inclusive as duas "
        "passadas obrigatórias e o formato de saída da seção 12. Responda JSON puro: "
        "sem cercas de código, sem comentário fora do JSON, sem texto antes ou depois."
    ),
    SISTEMA_ASSET: (
        "Você reescreve UM recurso de um anúncio de Search que já foi auditado. Os "
        "outros recursos estão de pé e não são seus: não os comente e não os "
        "reescreva. Responda JSON puro com exatamente o objeto pedido — sem cercas "
        "de código e sem texto em volta."
    ),
}

# Temperatura de `app/llm/gemini.py`, onde já roda em produção. Não há medição de
# temperatura contra qualidade de copy nesta operação — copiar o valor que já é
# usado é honesto; escolher outro seria chute com cara de ajuste.
TEMPERATURA = 0.9

#: Quanto o modelo pode pensar antes de começar a falar, do primeiro ao último
#: degrau. Só o Gemini tem este controle; o transporte da OpenAI ignora.
#:
#: A tabela inteira de medições está no comentário de `TransporteGemini.__call__`
#: — é ela que explica por que a escada COMEÇA BAIXA em vez de começar rica. O
#: resumo: o servidor corta a conexão aos ~60 s se nada foi enviado, e pensar à
#: vontade neste prompt leva mais que isso. Um degrau que falha custa 61 s de
#: relógio e devolve zero.
#:
#: Os dois degraus daqui foram medidos 2× cada contra o prompt real do card 65
#: (77.276 bytes), primeiro byte em 1,6–1,7 s nas quatro. Os degraus do meio
#: (4096, 8192) NÃO entram: 8192 passou uma vez em 44,3 s e caiu na outra, e
#: 4096 caiu — perto dos 60 s é cara ou coroa, e cara ou coroa não é motor.
#:
#: ⚠️ Se um dia a copy piorar e a suspeita cair aqui, a comparação honesta é
#: rodar o mesmo card com `({"thinkingBudget": 8192},) + ESCADA_DE_PENSAMENTO` e
#: comparar o `ad_strength` que o Google devolve — ver `volc_ads/forca.py`. Não
#: adianta olhar o texto e achar bonito.
ESCADA_DE_PENSAMENTO: tuple[dict, ...] = (
    {"thinkingBudget": 2048},
    {"thinkingLevel": "low"},
)


def _nome_do_degrau(degrau: dict | None) -> str:
    """O degrau em uma palavra, para caber na telemetria."""
    if not degrau:
        return "livre"
    if "thinkingBudget" in degrau:
        return f"teto {degrau['thinkingBudget']}"
    return f"nível {degrau.get('thinkingLevel', '?')}"


_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"
_OPENAI = "https://api.openai.com/v1/chat/completions"


class FalhaDeTransporte(RuntimeError):
    """A chamada não voltou: rede, HTTP, timeout, chave ausente, resposta vazia.

    ⚠️ NÃO herda de `ValueError`, e isso é decisão, não acaso: `ciclo._regenerar`
    captura `ValueError` para dizer "substituto ilegível para <alvo>". Se uma
    queda de rede casasse ali, ela viraria "o modelo escreveu bobagem", gastaria
    uma das 2 regenerações do teto daquele asset e sumiria do diário.
    """


class RespostaVazia(FalhaDeTransporte):
    """O tubo funcionou e o modelo não devolveu texto (recusa, filtro, corte).

    Separada porque o remédio é outro: repetir não adianta se o modelo recusou.
    Continua sendo `FalhaDeTransporte` para quem só quer saber que não veio nada.
    """


class TuboMudo(FalhaDeTransporte):
    """A conexão caiu sem UM byte de resposta — o servidor cortou enquanto pensava.

    ## Por que isto precisa de um tipo próprio

    Cair no meio do stream e cair antes do primeiro byte parecem a mesma coisa
    (`RemoteProtocolError`) e pedem remédios OPOSTOS:

    · caiu no meio  → foi a rede. Repetir igual tem chance real.
    · caiu mudo     → o servidor fechou aos 60 s porque o modelo ainda estava
                      pensando. Repetir igual cai igual, e isso foi MEDIDO:
                      três tentativas do card 65 morreram aos 60,8 · 61,0 ·
                      60,8 s, com zero bloco recebido nas três.

    O remédio do tubo mudo é fazer o modelo COMEÇAR A FALAR mais cedo — ver
    `ESCADA_DE_PENSAMENTO`.
    """


@dataclass(frozen=True)
class Resposta:
    """O que um transporte devolve: o texto e o que a API contou de consumo."""

    texto: str
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    modelo: str = ""
    #: Em que degrau da `ESCADA_DE_PENSAMENTO` esta resposta saiu. Vazio quando
    #: o provedor não tem controle de pensamento (OpenAI) ou o degrau é o livre.
    pensamento: str = ""


class Transporte(Protocol):
    """Uma chamada ao provedor. É o ponto de costura que os testes substituem."""

    def __call__(self, sistema: str, usuario: str) -> Resposta: ...


@dataclass(frozen=True)
class Chamada:
    """Telemetria de UMA chamada. É o que a tela mostra por linha.

    `parseou` é o campo que separa falha de CONTEÚDO de falha de TRANSPORTE sem
    precisar de exceção: transporte que falha levanta e chega aqui com `erro`
    preenchido; conteúdo que não vira JSON chega com `parseou=False` e o texto
    segue para a cascata decidir.
    """

    papel: str
    provedor: str
    modelo: str
    latencia_s: float
    chars_saida: int
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    custo_usd: float | None = None
    parseou: bool = False
    erro: str = ""
    #: Degrau da `ESCADA_DE_PENSAMENTO` que produziu esta resposta. Sem ele, uma
    #: copy escrita no degrau mais barato pareceria idêntica a uma escrita à
    #: vontade — e a pergunta "o teto piorou o texto?" não teria como ser feita.
    pensamento: str = ""

    @property
    def ok(self) -> bool:
        return not self.erro


# ── configuração ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Config:
    """Credencial, modelo, timeout e preço. Nada disto nasce aqui.

    `preco_*` são US$ por 1 milhão de tokens e vêm SÓ do ambiente
    (`VOLC_ADS_PRECO_ENTRADA_MI`, `VOLC_ADS_PRECO_SAIDA_MI`). Não há tabela de
    preço no código de propósito: preço de LLM muda por modelo, por região e por
    mês, e um número desatualizado escrito aqui viraria "custo medido" na tela do
    operador. Sem eles, `custo_usd` é `None` — que é a verdade.
    """

    provedor: str
    modelo: str
    chave: str
    timeout_s: float = 420.0
    max_tokens_saida: int | None = None
    preco_entrada_mi: float | None = None
    preco_saida_mi: float | None = None

    @classmethod
    def do_ambiente(cls, *, provedor: str | None = None,
                    modelo: str | None = None) -> Config:
        """Resolve tudo a partir do `app.config.Settings` do backend.

        O import é local porque arrasta `pydantic_settings`: quem só quer o
        `ClienteLLM` com um transporte próprio (o banco de provas, por exemplo)
        não deve precisar da pilha do backend instalada. Quem põe `backend/` no
        `sys.path` é a `ponte`, importada no topo deste módulo.
        """
        from app.config import Settings  # noqa: PLC0415 — ver docstring

        # Ordem importa: o último arquivo ganha, e a chave de LLM mora no backend.
        envs = [p for p in (RAIZ / ".env", BACKEND / ".env", BACKEND / ".env.local")
                if p.exists()]
        s = Settings(_env_file=envs or None)

        escolhido = (provedor or s.resolve_engine()).lower()
        if escolhido == "gemini":
            chave, padrao = s.resolved_gemini_key, s.pautador_gemini_model
        elif escolhido == "openai":
            chave, padrao = s.openai_api_key, s.pautador_openai_model
        else:
            raise FalhaDeTransporte(
                f"provedor {escolhido!r} não fala texto aqui. Configure "
                f"GEMINI_API_KEY ou OPENAI_API_KEY em backend/.env, ou passe um "
                f"transporte próprio para ClienteLLM."
            )
        if not chave:
            raise FalhaDeTransporte(
                f"provedor {escolhido!r} sem chave. Ela mora em backend/.env "
                f"({'GEMINI_API_KEY' if escolhido == 'gemini' else 'OPENAI_API_KEY'})."
            )

        # Não existe modelo MEDIDO para copy nesta operação. O default é o que o
        # backend já usa; o override existe para quando alguém medir de verdade.
        return cls(
            provedor=escolhido,
            modelo=(modelo or os.environ.get("VOLC_ADS_COPY_MODELO")
                    or padrao).strip().removeprefix("models/"),
            chave=chave,
            timeout_s=getattr(s, "llm_timeout_seconds", None) or s.request_timeout_seconds,
            max_tokens_saida=s.pautador_gemini_max_output_tokens,
            preco_entrada_mi=_preco("VOLC_ADS_PRECO_ENTRADA_MI"),
            preco_saida_mi=_preco("VOLC_ADS_PRECO_SAIDA_MI"),
        )


def _preco(variavel: str) -> float | None:
    bruto = (os.environ.get(variavel) or "").strip()
    if not bruto:
        return None
    try:
        return float(bruto.replace(",", "."))
    except ValueError as exc:
        raise FalhaDeTransporte(
            f"{variavel}={bruto!r} não é número. Preço é US$ por 1 milhão de "
            f"tokens; deixe vazio se não souber — custo None é melhor que custo errado."
        ) from exc


# ── os transportes ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransporteGemini:
    """Generative Language API v1beta, síncrona, lendo `usageMetadata`.

    O payload espelha `app/llm/gemini.py`, incluindo as duas lições que já
    custaram caro lá:
      · `responseMimeType: application/json` — pede JSON ao provedor;
      · `maxOutputTokens` só entra se estiver CONFIGURADO. Fixar 8192 trunca
        modelo com pensamento (os tokens de raciocínio comem o orçamento) e a
        geração inteira se perde.
    """

    config: Config

    def __call__(self, sistema: str, usuario: str) -> Resposta:
        # ⚠️ STREAMING + TETO DE PENSAMENTO — E OS DOIS SÃO O MESMO DEFEITO.
        #
        # Era `:generateContent`, sem streaming. Medido em 19/08/2026 com o
        # prompt real do card 65, quatro chamadas idênticas em sequência:
        #
        #     1: RemoteProtocolError em 60,8 s
        #     2: HTTP 200            em 54,1 s   (saída 1.921 · pensamento 10.937)
        #     3: RemoteProtocolError em 60,8 s
        #     4: RemoteProtocolError em 61,1 s
        #
        # Dali eu concluí que o corte era no TEMPO TOTAL e que streaming
        # resolveria. Metade certo, e a metade errada custou uma escrita inteira:
        # com `streamGenerateContent` no ar, o mesmo card voltou a morrer aos
        # 60,8 · 61,0 · 60,8 s. O que eu não tinha medido era ONDE o corte pega.
        #
        # Medido de novo, agora cronometrando o PRIMEIRO byte do SSE:
        #
        #     sem teto        1º byte NUNCA chegou · caiu aos 61,0 s · 0 blocos
        #     nível medium    1º byte NUNCA chegou · caiu aos 60,9 s · 0 blocos
        #     orçamento 32768 1º byte NUNCA chegou · caiu aos 60,8 s · 0 blocos
        #     orçamento 24576 1º byte NUNCA chegou · caiu aos 60,8 s · 0 blocos
        #     orçamento 16384 1º byte NUNCA chegou · caiu aos 60,8 s · 0 blocos
        #     orçamento  8192 1º byte aos 44,3 s   · terminou em 52,6 s
        #     orçamento  4096 1º byte NUNCA chegou · caiu aos 60,9 s · 0 blocos
        #     orçamento  2048 1º byte aos  1,7 s   · terminou em 10,0 s
        #     nível    low    1º byte aos  1,7 s   · terminou em 10,5 s
        #
        # O corte é no PRIMEIRO BYTE, não no total: enquanto o modelo pensa, não
        # há nada na linha, e o servidor fecha o socket aos ~60 s. Streaming só
        # salva quem começa a falar antes disso — e com este prompt, pensando à
        # vontade, ele não começa.
        #
        # Repare que 4096 morreu e 8192 passou: o tempo de pensamento tem
        # variação grande, então qualquer degrau perto dos 60 s é cara ou coroa.
        # Por isso a escada começa baixo em vez de começar rico: um degrau que
        # falha custa 61 s de relógio e não devolve nada.
        ultima: TuboMudo | None = None
        for degrau in ESCADA_DE_PENSAMENTO:
            try:
                return self._uma_chamada(sistema, usuario, degrau)
            except TuboMudo as exc:
                # Repetir IGUAL é comprovadamente inútil (3/3 no card 65). O que
                # muda a sorte é o modelo falar mais cedo — próximo degrau.
                ultima = exc
        # Nem o degrau mais barato começou a falar em 60 s: o problema não é
        # pensamento, e quem chama precisa ver o erro de verdade em vez de uma
        # quarta chamada de consolo.
        assert ultima is not None
        raise ultima

    def _uma_chamada(self, sistema: str, usuario: str,
                     degrau: dict | None) -> Resposta:
        geracao: dict = {"temperature": TEMPERATURA,
                         "responseMimeType": "application/json"}
        if self.config.max_tokens_saida:
            geracao["maxOutputTokens"] = self.config.max_tokens_saida
        if degrau:
            geracao["thinkingConfig"] = dict(degrau)
        payload = {
            "system_instruction": {"parts": [{"text": sistema}]},
            "contents": [{"role": "user", "parts": [{"text": usuario}]}],
            "generationConfig": geracao,
        }
        url = f"{_GEMINI}/{self.config.modelo}:streamGenerateContent"
        # Cliente por chamada, como o backend faz: são poucas chamadas por
        # campanha e um cliente vivo exigiria ciclo de vida que ninguém fecharia.
        with httpx.Client(timeout=self.config.timeout_s) as http:
            dados = _http(lambda: _juntar_stream(
                http, url, {"key": self.config.chave, "alt": "sse"}, payload))

        candidatos = dados.get("candidates") or []
        if not candidatos:
            raise RespostaVazia(f"Gemini não devolveu candidato: {str(dados)[:300]}")
        partes = (candidatos[0].get("content") or {}).get("parts") or []
        texto = "".join(p.get("text", "") for p in partes)
        if not texto:
            raise RespostaVazia(
                f"Gemini devolveu texto vazio (finishReason="
                f"{candidatos[0].get('finishReason')})"
            )

        uso = dados.get("usageMetadata") or {}
        # `thoughtsTokenCount` aparece nos modelos com pensamento e é somado à
        # saída. MEDIDO em 18/08/2026 contra gemini-3.5-flash, chamada mínima:
        # prompt 16 · candidates 67 · thoughts 168 · total 251 — ou seja, o
        # próprio provedor soma pensamento no total, e ignorá-lo esconderia 71%
        # dos tokens de saída desta chamada. NÃO verificado contra a FATURA: se
        # o custo da tela sair baixo demais, é esta linha que se confere.
        saida = uso.get("candidatesTokenCount")
        if saida is not None:
            saida += uso.get("thoughtsTokenCount") or 0
        return Resposta(texto, uso.get("promptTokenCount"), saida,
                        self.config.modelo, pensamento=_nome_do_degrau(degrau))


@dataclass(frozen=True)
class TransporteOpenAI:
    """Chat Completions, síncrona, lendo `usage`. Espelha `app/llm/openai_client.py`."""

    config: Config

    def __call__(self, sistema: str, usuario: str) -> Resposta:
        payload = {
            "model": self.config.modelo,
            "messages": [{"role": "system", "content": sistema},
                         {"role": "user", "content": usuario}],
            "temperature": TEMPERATURA,
            "response_format": {"type": "json_object"},
        }
        cabecalho = {"Authorization": f"Bearer {self.config.chave}"}
        with httpx.Client(timeout=self.config.timeout_s) as http:
            dados = _http(lambda: http.post(_OPENAI, headers=cabecalho, json=payload))

        escolhas = dados.get("choices") or []
        if not escolhas:
            raise RespostaVazia(f"OpenAI não devolveu escolha: {str(dados)[:300]}")
        texto = (escolhas[0].get("message") or {}).get("content") or ""
        if not texto:
            raise RespostaVazia(
                f"OpenAI devolveu conteúdo vazio (finish_reason="
                f"{escolhas[0].get('finish_reason')})"
            )
        uso = dados.get("usage") or {}
        return Resposta(texto, uso.get("prompt_tokens"),
                        uso.get("completion_tokens"), self.config.modelo)


def _juntar_stream(http: httpx.Client, url: str, params: dict, payload: dict) -> dict:
    """Lê o SSE do `streamGenerateContent` e remonta a resposta inteira.

    Devolve o MESMO formato do endpoint não-streaming — `candidates` com um
    `parts` de texto único e `usageMetadata` —, então quem chama não precisa
    saber que houve streaming. É de propósito: o streaming existe para manter a
    conexão viva (ver o comentário em `GeminiTransporte.__call__`), não para
    mudar o contrato.

    ⚠️ O `usageMetadata` vem no ÚLTIMO pedaço e é CUMULATIVO — cada bloco traz o
    total até ali, não um incremento. Somar os blocos multiplicaria a contagem
    de tokens, e com ela o custo que a tela mostra. Por isso o último vence.

    ⚠️ Erro de status precisa de `read()` antes: numa resposta em streaming o
    corpo ainda não foi baixado quando o status chega, e `response.text` sairia
    vazio — o operador veria "HTTP 400: " sem o motivo.

    ⚠️ Queda COM zero blocos vira `TuboMudo`, não `RemoteProtocolError`. É a
    diferença entre "a rede piscou" (repetir tem chance) e "o servidor cortou
    porque o modelo ainda pensava" (repetir igual cai igual, medido 3/3). Sem
    esta distinção, `_http` gastava três tentativas de 61 s cada e a cascata
    inteira ia ao chão com a conta já paga.
    """
    partes: list[str] = []
    uso: dict = {}
    razao: str | None = None
    blocos = 0
    try:
        with http.stream("POST", url, params=params, json=payload) as r:
            if r.status_code >= 400:
                r.read()
                r.raise_for_status()
            for linha in r.iter_lines():
                if not linha or not linha.startswith("data:"):
                    continue
                corpo = linha[len("data:"):].strip()
                if not corpo or corpo == "[DONE]":
                    continue
                blocos += 1
                try:
                    bloco = json.loads(corpo)
                except ValueError:
                    continue                  # pedaço truncado: o próximo fecha
                for cand in (bloco.get("candidates") or []):
                    for p in ((cand.get("content") or {}).get("parts") or []):
                        if p.get("text"):
                            partes.append(p["text"])
                    if cand.get("finishReason"):
                        razao = cand["finishReason"]
                if bloco.get("usageMetadata"):
                    uso = bloco["usageMetadata"]
    except httpx.TransportError as exc:
        # Zero blocos = o servidor fechou sem dizer NADA. Ver `TuboMudo`.
        if blocos == 0:
            raise TuboMudo(f"{type(exc).__name__}: {exc}") from exc
        raise
    return {
        "candidates": [{"content": {"parts": [{"text": "".join(partes)}]},
                        "finishReason": razao}],
        "usageMetadata": uso,
    }


#: Quantas vezes uma chamada é TENTADA (não quantas vezes é repetida).
TENTATIVAS_DE_TUBO = 3
#: Espera antes de cada nova tentativa, em segundos.
ESPERAS_DE_TUBO = (2.0, 6.0)


def _transitorio(exc: Exception) -> bool:
    """Isto tem chance real de dar certo se eu tentar de novo?

    SIM: queda de conexão (o servidor fechou sem responder), timeout, DNS,
    pool esgotado — tudo que é `httpx.TransportError` — mais 429 e 5xx, que o
    provedor manda quando está sobrecarregado.

    NÃO: qualquer outro 4xx. Um 400 por payload malformado ou um 403 por chave
    inválida vão dar 400 e 403 de novo; repetir só gasta tempo e esconde o
    motivo real atrás de três tentativas idênticas.

    NÃO: `TuboMudo`. É queda de conexão, mas a causa é o modelo pensando além
    dos ~60 s que o servidor tolera calado — repetir IGUAL cai igual, e isso foi
    medido 3/3 no card 65 (60,8 · 61,0 · 60,8 s, zero bloco nas três). Quem
    conserta é a `ESCADA_DE_PENSAMENTO`, não a retentativa.
    """
    if isinstance(exc, TuboMudo):
        return False
    if isinstance(exc, httpx.HTTPStatusError):
        codigo = exc.response.status_code if exc.response is not None else 0
        return codigo == 429 or codigo >= 500
    return isinstance(exc, httpx.TransportError)


def _http(chamar) -> dict:
    """Executa e traduz QUALQUER falha de tubo em `FalhaDeTransporte`.

    Um tipo só para o chamador capturar, com `__cause__` preservado para quem
    for depurar.

    ## ⚠️ AQUI RETENTA — e o cabeçalho deste arquivo dizia que não

    O item 1 afirmava que `TRANSIENT` e `THROTTLED` eram resolvidos pela
    `PoliticaRetry` de `gads/client.py`, e que retentar aqui produziria backoff
    ao quadrado. Isso é verdade para o caminho do Google Ads — e SÓ para ele.
    `PoliticaRetry` é usada em `volc_ads/subir.py`; ela nunca tocou a cascata de
    copy. No caminho `escrever() → ciclo → cliente.gerar() → _http` não havia
    ninguém retentando: a afirmação descrevia um orquestrador que não existe.

    Medido em 19/08/2026, card 65: a escrita morreu com
    `RemoteProtocolError: Server disconnected without sending a response.` —
    o servidor fechou o socket sem responder. O diário ficou VAZIO e
    `segundos` nulo, ou seja, a cascata inteira (~174 s e os tokens já pagos das
    rodadas anteriores) foi ao chão por uma queda de tubo de um instante.

    Uma chamada que não recebeu resposta não produziu resultado nenhum: repetir
    é a única forma de não perder o que já foi pago. O custo de uma chamada
    duplicada é uma fração do custo de refazer a cascata.
    """
    ultima: Exception | None = None
    for tentativa in range(1, TENTATIVAS_DE_TUBO + 1):
        try:
            resultado = chamar()
            # `_juntar_stream` já devolve o dicionário montado e já conferiu o
            # status; o POST simples devolve a resposta crua. Aceitar os dois
            # aqui mantém a retentativa num lugar só, que é o ponto de `_http`.
            if isinstance(resultado, dict):
                return resultado
            resultado.raise_for_status()
            return resultado.json()
        except Exception as exc:  # noqa: BLE001 — timeout, DNS, TLS, JSON de erro
            ultima = exc
            if tentativa >= TENTATIVAS_DE_TUBO or not _transitorio(exc):
                break
            time.sleep(ESPERAS_DE_TUBO[min(tentativa - 1, len(ESPERAS_DE_TUBO) - 1)])

    assert ultima is not None
    # ⚠️ `TuboMudo` sobe COM O TIPO. Embrulhá-lo em `FalhaDeTransporte` genérica
    # apagaria a única informação que o chamador usa para descer a escada de
    # pensamento — e ele voltaria a morrer sem tentar o degrau seguinte.
    if isinstance(ultima, TuboMudo):
        raise ultima
    if isinstance(ultima, httpx.HTTPStatusError):
        corpo = ultima.response.text[:300] if ultima.response is not None else ""
        raise FalhaDeTransporte(
            f"HTTP {ultima.response.status_code}: {corpo}") from ultima
    raise FalhaDeTransporte(f"{type(ultima).__name__}: {ultima}") from ultima


# ── o cliente ───────────────────────────────────────────────────────────────


@dataclass
class ClienteLLM:
    """Satisfaz `ciclo.Cliente`. Intercambiável com `ClienteMock`, por construção.

    Guarda o transporte, não a chave: quem quiser rodar contra um provedor novo
    escreve um `Transporte` e não toca em nada aqui — é a mesma costura que
    permite ao banco de provas rodar a cascata inteira sem rede e sem chave.
    """

    transporte: Transporte
    provedor: str = "?"
    modelo: str = "?"
    preco_entrada_mi: float | None = None
    preco_saida_mi: float | None = None
    sistemas: dict[str, str] = field(default_factory=lambda: dict(SISTEMAS))
    telemetria: list[Chamada] = field(default_factory=list)

    def gerar(self, sistema: str, usuario: str) -> str:
        """Texto entra, texto sai. O contrato do `Protocol`, e nada além dele."""
        instrucao = self.sistemas.get(sistema, sistema)
        papel = _papel(sistema)
        inicio = time.perf_counter()
        try:
            resposta = self.transporte(instrucao, usuario)
        except FalhaDeTransporte as exc:
            # A chamada falhada ENTRA na telemetria: ela consumiu tempo e, se o
            # provedor cobrou o prompt, dinheiro. Telemetria que só registra
            # sucesso mente sobre a conta do dia.
            self.telemetria.append(Chamada(
                papel=papel, provedor=self.provedor, modelo=self.modelo,
                latencia_s=time.perf_counter() - inicio, chars_saida=0,
                erro=f"{type(exc).__name__}: {exc}"))
            raise

        latencia = time.perf_counter() - inicio
        # `extract_json` roda aqui SÓ para registrar se a resposta era legível —
        # é o mesmo parser (e o mesmo reparo de delimitadores) que a cascata usa
        # em seguida, então o veredito é o mesmo. Nada é levantado: o texto cru
        # segue para a cascata, que é quem sabe o remédio.
        try:
            extract_json(resposta.texto)
            parseou = True
        except ValueError:
            parseou = False

        self.telemetria.append(Chamada(
            papel=papel, provedor=self.provedor,
            modelo=resposta.modelo or self.modelo,
            latencia_s=latencia, chars_saida=len(resposta.texto),
            tokens_entrada=resposta.tokens_entrada,
            tokens_saida=resposta.tokens_saida,
            custo_usd=self._custo(resposta),
            parseou=parseou, pensamento=resposta.pensamento))
        return resposta.texto

    # ── telemetria agregada ─────────────────────────────────────────────────

    def _custo(self, r: Resposta) -> float | None:
        if self.preco_entrada_mi is None or self.preco_saida_mi is None:
            return None
        if r.tokens_entrada is None or r.tokens_saida is None:
            return None
        return (r.tokens_entrada * self.preco_entrada_mi
                + r.tokens_saida * self.preco_saida_mi) / 1_000_000

    def resumo(self) -> dict:
        """O agregado que a tela mostra. Cada `None` diz por que é `None`.

        `sem_custo` é a contagem de chamadas cujo custo não pôde ser calculado —
        sem ela, um total de US$ 0,0031 sobre 8 chamadas pareceria o custo das
        oito quando é o de duas.
        """
        def soma(campo: str) -> int | None:
            valores = [getattr(c, campo) for c in self.telemetria if getattr(c, campo) is not None]
            return sum(valores) if valores else None

        custos = [c.custo_usd for c in self.telemetria if c.custo_usd is not None]
        return {
            "chamadas": len(self.telemetria),
            "falhas": sum(1 for c in self.telemetria if not c.ok),
            "por_papel": {
                p: sum(1 for c in self.telemetria if c.papel == p)
                for p in sorted({c.papel for c in self.telemetria})
            },
            "ilegiveis": sum(1 for c in self.telemetria if c.ok and not c.parseou),
            # Os degraus usados, do primeiro ao último. Duas entradas aqui
            # querem dizer que algum degrau ficou mudo e o motor desceu sozinho.
            "pensamento": sorted({c.pensamento for c in self.telemetria if c.pensamento}),
            "tokens_entrada": soma("tokens_entrada"),
            "tokens_saida": soma("tokens_saida"),
            "latencia_s": round(sum(c.latencia_s for c in self.telemetria), 3),
            "custo_usd": round(sum(custos), 6) if custos else None,
            "sem_custo": len(self.telemetria) - len(custos),
            "motivo_sem_custo": (
                "" if not (len(self.telemetria) - len(custos)) else
                "preço por token não configurado (VOLC_ADS_PRECO_ENTRADA_MI / "
                "VOLC_ADS_PRECO_SAIDA_MI) ou provedor não informou consumo"
            ),
        }


def _papel(sistema: str) -> str:
    if sistema == SISTEMA_COMPLETO:
        return "conjunto"
    if sistema == SISTEMA_ASSET:
        return "asset"
    return "outro"


def criar(*, provedor: str | None = None, modelo: str | None = None,
          config: Config | None = None) -> ClienteLLM:
    """Monta o cliente a partir do ambiente. Erra claro quando falta chave."""
    cfg = config or Config.do_ambiente(provedor=provedor, modelo=modelo)
    transporte: Transporte = (
        TransporteGemini(cfg) if cfg.provedor == "gemini" else TransporteOpenAI(cfg)
    )
    return ClienteLLM(
        transporte=transporte, provedor=cfg.provedor, modelo=cfg.modelo,
        preco_entrada_mi=cfg.preco_entrada_mi, preco_saida_mi=cfg.preco_saida_mi,
    )


__all__ = [
    "SISTEMAS",
    "Chamada",
    "ClienteLLM",
    "Config",
    "ESCADA_DE_PENSAMENTO",
    "FalhaDeTransporte",
    "Resposta",
    "RespostaVazia",
    "Transporte",
    "TransporteGemini",
    "TransporteOpenAI",
    "TuboMudo",
    "criar",
]
