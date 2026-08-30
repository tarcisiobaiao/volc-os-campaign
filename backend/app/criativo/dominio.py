"""O domínio do Estúdio Criativo — regra pura, sem rede, sem banco, sem FastAPI.

Este módulo não importa `httpx`, não conhece PostgREST e não sabe o que é uma
request. Ele responde quatro perguntas, e são as quatro que decidem se o Estúdio
cobra duas vezes, mente sobre progresso ou promove uma peça que falhou:

    1. duas submissões são o MESMO pedido?      -> `chave_de_idempotencia`
    2. o que este slot pede ao motor?           -> `FORMATOS`
    3. em que estado o job está, dadas as peças? -> `estado_do_lote`
    4. o que pode ser dito ao operador?         -> `sanitizar`

Estar fora do framework é o que permite provar as quatro sem subir servidor,
sem banco e sem gastar com o provider.

## A regra que o resto do sistema herda daqui

O catálogo de formatos vive AQUI e em `src/types/criativos.ts`, e os dois têm de
concordar. Um `<select>` que oferece um slot que o motor não conhece produz um
job aceito que falha depois, e o operador descobre pagando. `testes_criativo_
dominio.py` compara as duas listas arquivo contra arquivo, para que a divergência
apareça no gate e não em produção.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Literal

from volc_ads.criativo.contrato import EspecificacaoDeAsset, TipoDeAsset

# ─────────────────────────────────────────────────────────────────────────────
# Estados
# ─────────────────────────────────────────────────────────────────────────────

EstadoDoJob = Literal[
    "draft", "queued", "running", "partial", "succeeded", "failed", "cancelled"
]
EstadoDaRendition = Literal["pendente", "gerando", "pronta", "falhou", "cancelada"]

ESTADOS_TERMINAIS: frozenset[str] = frozenset(
    {"partial", "succeeded", "failed", "cancelled"}
)


# ─────────────────────────────────────────────────────────────────────────────
# Formatos
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Formato:
    """Um slot que o Estúdio sabe produzir.

    `tipo` amarra o slot ao vocabulário de `volc_ads/criativo/contrato.py`, que
    é quem já sabe o que Display, Demand Gen e Performance Max exigem de cada
    papel. Sem essa amarração, o Estúdio produziria imagens que a validação de
    canal reprova depois, e a descoberta viria pelo custo.
    """

    slot: str
    rotulo: str
    proporcao: str
    largura: int
    altura: int
    tipo: TipoDeAsset
    descricao: str
    destinos_tipicos: tuple[str, ...]

    def especificacao(self) -> EspecificacaoDeAsset:
        return EspecificacaoDeAsset(
            tipo=self.tipo,
            largura_recomendada=self.largura,
            altura_recomendada=self.altura,
            fonte_dos_numeros=f"estudio-criativo:{self.slot}",
        )


FORMATOS: tuple[Formato, ...] = (
    Formato(
        slot="1x1",
        rotulo="Quadrado",
        proporcao="1:1",
        largura=1080,
        altura=1080,
        tipo=TipoDeAsset.IMAGEM_MARKETING_QUADRADA,
        descricao="Feed quadrado e display quadrado.",
        destinos_tipicos=("google_display", "meta_feed", "instagram_organic"),
    ),
    Formato(
        slot="4x5",
        rotulo="Retrato",
        proporcao="4:5",
        largura=1080,
        altura=1350,
        tipo=TipoDeAsset.IMAGEM_MARKETING_RETRATO,
        descricao="Ocupa mais altura no feed sem entrar em tela cheia.",
        destinos_tipicos=("meta_feed", "instagram_organic"),
    ),
    Formato(
        slot="9x16",
        rotulo="Vertical",
        proporcao="9:16",
        largura=1080,
        altura=1920,
        tipo=TipoDeAsset.IMAGEM_MARKETING_RETRATO_ALTO,
        descricao="Tela cheia de stories, reels e shorts.",
        destinos_tipicos=("meta_stories_reels", "youtube_shorts"),
    ),
    Formato(
        slot="1.91x1",
        rotulo="Paisagem",
        proporcao="1.91:1",
        largura=1200,
        altura=628,
        tipo=TipoDeAsset.IMAGEM_MARKETING,
        descricao="Imagem de marketing paisagem do Display.",
        destinos_tipicos=("google_display", "meta_feed"),
    ),
)

_POR_SLOT: dict[str, Formato] = {f.slot: f for f in FORMATOS}


def formato_de(slot: str) -> Formato:
    try:
        return _POR_SLOT[slot]
    except KeyError:
        raise SlotDesconhecido(slot) from None


class SlotDesconhecido(ValueError):
    """Slot que o motor não sabe produzir.

    Erro próprio, e não `KeyError`, porque o router precisa distinguir "pedido
    inválido" (400, culpa de quem chamou) de "defeito nosso" (500). Um
    `KeyError` que sobe até o handler genérico vira 500 e acusa o servidor de um
    erro do cliente.
    """

    def __init__(self, slot: str) -> None:
        super().__init__(f"formato não disponível: {slot!r}")
        self.slot = slot


# ─────────────────────────────────────────────────────────────────────────────
# Idempotência
# ─────────────────────────────────────────────────────────────────────────────

# Campos que ENTRAM na chave. A lista é explícita, e não `todo o payload`, por
# um motivo medido: um payload inteiro carrega ruído do cliente (ordem de
# chaves, campo vazio, timestamp de formulário), e qualquer ruído faz o mesmo
# pedido produzir chaves diferentes. Uma chave que muda sozinha transforma todo
# reenvio em cobrança nova, que é exatamente o defeito que ela existe para
# impedir.
_CAMPOS_DA_CHAVE = (
    "projeto_titulo",
    "objetivo",
    "mensagem",
    "audiencia",
    "brand_pack_id",
    "modo",
    "slots",
    "motor",
    "motor_versao",
    # ⚠️ `criado_por` e `destinos_pretendidos` ENTRARAM em 28/08/2026, e cada um
    # fechou um defeito diferente.
    #
    # SEM `criado_por`, dois operadores que submetessem o mesmo briefing padrão
    # recebiam o MESMO job: o segundo herdava projeto, estado e resultado do
    # primeiro, inclusive um cancelamento ou uma fila morta, sem poder forçar
    # produção. A chave existe para proteger UMA pessoa do próprio duplo clique,
    # não para fundir o trabalho de duas.
    #
    # SEM `destinos_pretendidos`, pedir o mesmo visual para `google_display` e
    # para `meta_feed` produzia a mesma chave, e o destino do segundo pedido era
    # descartado em silêncio, embora seja ele que a validação de canal vai ler
    # depois.
    "criado_por",
    "destinos_pretendidos",
)


def chave_de_idempotencia(pedido: dict[str, Any]) -> str:
    """A identidade do PEDIDO, derivada do conteúdo e nunca sorteada.

    Se o operador não mudou nada, a segunda submissão produz a MESMA chave e o
    backend devolve o job que já existe. Se ele mudou o briefing, a chave muda e
    o job novo é outra coisa, que é a verdade.

    `slots` é ordenado antes de entrar: pedir `[1x1, 4x5]` e `[4x5, 1x1]` é o
    mesmo pedido, e uma chave sensível à ordem cobraria duas vezes por um
    reordenamento de checkbox.

    O texto é normalizado (espaços colapsados, NFC) porque um espaço a mais
    colado de um documento não é um briefing diferente.
    """
    material: dict[str, Any] = {}
    for campo in _CAMPOS_DA_CHAVE:
        valor = pedido.get(campo)
        if campo in ("slots", "destinos_pretendidos"):
            # Ordenado: reordenar caixa de seleção não é pedido novo.
            material[campo] = sorted(str(s) for s in (valor or []))
        elif isinstance(valor, str):
            material[campo] = _normalizar_texto(valor)
        else:
            material[campo] = valor
    cru = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "cri_" + hashlib.sha256(cru.encode("utf-8")).hexdigest()


def _normalizar_texto(valor: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", valor)).strip()


def hash_de_insumo(insumo: str) -> str:
    """Hash do que foi realmente mandado ao motor.

    Diferente da chave de idempotência de propósito: a chave identifica O
    PEDIDO; este identifica O QUE FOI ENVIADO. Os dois divergem quando o motor
    reescreve o prompt, e é a divergência que permite reproduzir uma geração que
    deu certo.
    """
    return hashlib.sha256(_normalizar_texto(insumo).encode("utf-8")).hexdigest()


def hash_de_conteudo(dados: bytes) -> str:
    """`sha256:` prefixado. Hash sem algoritmo declarado é impossível de migrar.

    Mesma função e mesmo prefixo de `volc_ads.criativo.contrato.hash_de_conteudo`
    — replicada aqui só para não obrigar a camada de I/O a importar o pacote de
    domínio de campanha por uma linha.
    """
    return "sha256:" + hashlib.sha256(dados).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Estado do lote
# ─────────────────────────────────────────────────────────────────────────────


def estado_do_lote(estados: Iterable[str]) -> EstadoDoJob:
    """O estado do job a partir do estado das peças, e nada mais.

    A regra que importa é a do meio: **algumas prontas e algumas falhas é
    `partial`, nunca `failed` nem `succeeded`**. Chamar de `failed` jogaria fora
    peças que já foram pagas e estão boas; chamar de `succeeded` esconderia que
    o operador pediu três e recebeu duas.

    Um lote sem nenhuma peça é `failed`, e não `succeeded`: um job que não
    produziu nada não teve sucesso, mesmo que nada tenha dado erro. "Zero peças
    sem erro" é o desfecho mais suspeito possível, e um `succeeded` ali esconde
    um motor que devolveu vazio em silêncio.
    """
    lista = list(estados)
    if not lista:
        return "failed"
    if any(e in ("pendente", "gerando") for e in lista):
        return "running"

    prontas = sum(1 for e in lista if e == "pronta")
    falhas = sum(1 for e in lista if e == "falhou")
    canceladas = sum(1 for e in lista if e == "cancelada")

    if prontas == len(lista):
        return "succeeded"
    if prontas == 0 and canceladas > 0 and falhas == 0:
        return "cancelled"
    if prontas == 0:
        return "failed"
    return "partial"


def pode_retentar(estado: EstadoDoJob) -> bool:
    """Retry faz sentido onde sobrou buraco para preencher.

    ⚠️ `cancelled` e `queued` ENTRAM, e isso é conserto de dois becos sem saída
    medidos em 28/08/2026.

    `cancelled`: a chave de idempotência é derivada do conteúdo, então reenviar
    o mesmo briefing devolve o job cancelado com `200 replay` e zero peça. O
    operador que cancelou por engano ficava sem saída nenhuma: retry recusava,
    reenviar não produzia, e a única escapatória era alterar um caractere do
    texto. Cancelar é uma decisão reversível; selar o briefing para sempre não
    era o que ninguém pediu.

    `queued`: um job cujo insert deu certo mas cuja gravação das peças falhou
    fica em `queued` com zero rendition. A chave já está ocupada, o reenvio
    devolve replay sem disparar nada, e o retry recusava. O mesmo beco.

    `running` continua fora: enquanto houver peça em voo, retentar é o caminho
    para pagar duas vezes. Job preso em `running` por processo morto é problema
    da reconciliação de subida, não do botão.
    """
    return estado in ("partial", "failed", "cancelled", "queued")


def pode_cancelar(estado: EstadoDoJob) -> bool:
    return estado in ("draft", "queued", "running")


# ─────────────────────────────────────────────────────────────────────────────
# Sanitização
# ─────────────────────────────────────────────────────────────────────────────

# O que NUNCA pode chegar ao operador. DESIGN.md: "Não exponha PostgREST, GAQL,
# SQL, internal table names, environment flags or stack traces to the operator."
# SPEC §10: "Não exponha prompt sensível, token, caminho de servidor ou stack
# trace ao operador."
_PADROES_PROIBIDOS = (
    re.compile(r"/(?:Users|home|root|var|etc|opt|private|tmp)/\S*"),
    # Caminho do Windows. ⚠️ A versão anterior era `[A-Za-z]:\\\\\\S*` numa
    # string raw, o que exigia DUAS contrabarras literais e nunca casava com
    # `C:\Users\...`: o caminho atravessava inteiro até o operador.
    re.compile(r"[A-Za-z]:\\[^\s]*"),
    re.compile(r"https?://\S+"),
    re.compile(r"\b[A-Za-z0-9_]*key[A-Za-z0-9_]*\s*[=:]\s*\S+", re.IGNORECASE),
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{10,}"),
    re.compile(r"\bsk-[0-9A-Za-z_\-]{10,}"),
    re.compile(r"\beyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]+\.?\S*"),
    re.compile(r"Traceback \(most recent call last\)[\s\S]*"),
    re.compile(r'File "[^"]+", line \d+'),
    # Nome de tabela interna. ⚠️ Ancorado por prefixo de esquema OU por
    # vizinhança de SQL, e não por palavra solta: a versão anterior comia
    # `trafego_pago` no meio de uma frase de negócio legítima
    # ("nossa equipe de trafego_pago aprovou") e a transformava em `[omitido]`.
    re.compile(r"\b(?:public|app_auth|storage)\.[a-z_]+\b"),
    re.compile(
        r"\b(?:from|into|update|table|join)\s+(?:public\.)?"
        r"(?:criativo|trafego|pautador)_[a-z_]+\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE)\b\s+\S+", re.IGNORECASE),
)

_TETO_DA_MENSAGEM = 240


def sanitizar(mensagem: str) -> str:
    """Deixa passar só o que o operador pode ler, e nunca devolve vazio.

    A substituição é por `[omitido]` e não por remoção silenciosa: uma frase com
    buraco avisa que houve corte, e uma frase costurada esconde que a mensagem
    original dizia mais. Quando sobra ruído demais, cai para uma frase genérica,
    porque meia mensagem técnica é pior que uma frase honesta.
    """
    limpa = (mensagem or "").strip()
    if not limpa:
        return "O motor não informou o motivo."
    for padrao in _PADROES_PROIBIDOS:
        limpa = padrao.sub("[omitido]", limpa)
    limpa = re.sub(r"\s+", " ", limpa).strip()
    if len(limpa) > _TETO_DA_MENSAGEM:
        limpa = limpa[:_TETO_DA_MENSAGEM].rstrip() + "…"
    # Sobrou mais omissão que texto: a mensagem não diz nada de útil e finge
    # dizer. Melhor a frase genérica.
    if not limpa or limpa.count("[omitido]") * 10 >= max(len(limpa), 1):
        return "O motor recusou o pedido e não deu um motivo que possa ser mostrado."
    return limpa


@dataclass(frozen=True)
class Falha:
    """Falha como dado, com `permanente` decidindo o remédio.

    Espelha `volc_ads.criativo.contrato.Falha`. A mensagem já entra sanitizada:
    esta classe é o que atravessa a fronteira até o browser, e sanitizar na
    borda de saída seria tarde demais se alguém logasse o objeto no meio.
    """

    codigo: str
    mensagem: str
    permanente: bool
    em: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "mensagem", sanitizar(self.mensagem))

    def para_dict(self) -> dict[str, Any]:
        return {
            "codigo": self.codigo,
            "mensagem": self.mensagem,
            "permanente": self.permanente,
            "em": self.em,
        }
