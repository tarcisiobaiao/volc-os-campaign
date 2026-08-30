"""O contrato de saída do PROMPT.md — parser, 7 checagens e orçamento de cota.

Só stdlib. Nenhuma rede, nenhuma credencial, nenhum `google.ads` — este módulo
tem de rodar contra o mock sem custo. O juiz do Google entra em `ciclo.py`,
injetado.

## O que este arquivo é

O `PROMPT.md` exige do modelo dois blocos que NÃO vão para o Google:
`ancoragem` (de onde veio cada afirmação) e `auditoria` (o que a passada 2
derrubou e a contagem final). Hoje nada consome esses blocos, e um bloco que
ninguém confere é um bloco que o modelo aprende a preencher de qualquer jeito.

Aqui eles viram checagem. As três que importam — 5, 6 e 7 — são a mesma
escotilha fechada que fez o classificador de pauta parar de absolver: com a
saída de fuga bloqueada, os sinais de entrada ficam honestos. Um modelo não
consegue declarar uma passada 2 que não fez.

## As 7 checagens

  1 ESTRUTURA   as chaves de topo existem e têm o tipo certo
  2 CONTAGEM    as contagens batem com o que foi pedido
  3 ANCORAGEM   uma entrada por título, `i` contíguo de 0 a n-1
  4 CHARS       `chars` declarado == comprimento efetivo (DKI pelo fallback)
  5 MECANICA    a mecânica declarada é cumprida pela própria string  (A9)
  6 CONTAGEM_F  `auditoria.contagem_final` == o que a medição encontra
  7 FATO        toda afirmação concreta declara um `fato` que existe no brief

## O LIMITE DA CHECAGEM 7 — leia antes de confiar nela

A checagem 7 prova que o `fato_id` **existe**. Ela NÃO prova que o fato
**sustenta** a afirmação, e a diferença é a reprovação mais cara que existe.

O próprio PROMPT.md dá o exemplo: se o fato diz `"até 5 parcelas"`, o título
`"5 Parcelas do Saque"` declara um id válido, passa aqui com nota cheia, e é
**A2** — o teto virou promessa de quantidade. O mesmo vale para troca de
sujeito ("a cessão está limitada a 3 por ano" → "novo limite de 3 saques por
ano") e para troca de escopo.

Nenhuma regra determinística fecha isso: exigiria entender o fato. A checagem 7
é um portão de EXISTÊNCIA, não de SUFICIÊNCIA. Quem adjudica suficiência é a
passada 2 do modelo e o revisor humano.

Não a trate como se `ancoragem` tivesse virado determinística. Ela não virou.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

# ── primitivas de texto ─────────────────────────────────────────────────────
# Elas moram AQUI e não em `provar.py` de propósito: a checagem 6 compara a
# `contagem_final` declarada pelo modelo com a medição do juiz 3. Se as duas
# usassem regexes diferentes, a checagem 6 mediria a divergência entre dois
# medidores em vez de flagrar teatro do modelo. `provar.py` importa daqui.

_DKI = re.compile(r"\{KeyWord:([^}]*)\}", re.IGNORECASE)


def sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def comprimento_efetivo(t: str) -> int:
    """O Google conta a tag DKI pelo FALLBACK, não pelo texto cru.

    `{KeyWord:Saque FGTS} 2026` são 15 caracteres para a API, não 25. Contar
    errado reprova texto válido e — pior — aprova texto que estoura no leilão.
    """
    return len(_DKI.sub(lambda m: m.group(1), t))


# Marcadores medidos no corpus. Regex, não lista de palavras proibidas: eles
# MEDEM, não bloqueiam. Cobrem pt e es porque é onde a operação tem evidência.
RX_EXEC = (r"\b(sacar|saca|tirar|tire|emitir|emita|solicitar|solicite|tramitar|"
           r"tramite|renovar|renove|obtener|obtenha|agendar|agende|inscrever|"
           r"inscreva|inscribir|baixar|baixe|descargar|cadastrar|cadastre|"
           r"registrar|registre|imprimir|checa|checar|consulte|consulta)\b")
RX_LEIT = (r"\b(como|c[oó]mo|veja|vea|entenda|saiba|sepa|confira|descubra|guia|"
           r"gu[ií]a|onde|d[oó]nde|quem|qui[eé]n|quais|cu[aá]les|requisitos|"
           r"regras|reglas|passo a passo|paso a paso|calend[aá]rio|calendario|"
           r"prazo|plazo|tabela|tabla|lista)\b")
RX_PERG = r"[?¿]"
RX_ANO = r"\b20\d\d\b"
RX_NUM = r"\d"
RX_DOIS_BLOCOS = r":"
RX_NEGACAO = r"\b(nao|sem|nunca|jamais|nem|no|sin|not|without|never)\b"

# Contraste é por idioma: `o` é contraste em espanhol e artigo em português.
# Uma regex só produziria 100% de falso positivo em pt.
RX_CONTRASTE = {
    "pt": r"\bou\b",
    "es": r"\b(o|u)\b",
    "en": r"\b(or|vs)\b",
}

# Marcador de recência para a M5 — ano OU palavra de mudança.
RX_RECENCIA = (r"(\b20\d\d\b|\b(novo|nova|novas|novos|mudou|muda|mudanca|"
               r"atualizado|atualizada|nuevo|nueva|cambio|cambia|actualizado|"
               r"new|changed|updated)\b)")

# Data, janela ou prazo para a M9.
RX_PRAZO = (r"(\d{1,2}/\d{1,2}(/\d{2,4})?|\b\d{1,3}\s*(dias?|d[ií]as?|meses|"
            r"m[êe]s|anos?|horas?)\b|\bate\b|\bhasta\b|\bprazo\b|\bplazo\b|"
            r"\bdeadline\b)")


def taxa(itens: list[str], rx: str) -> float:
    if not itens:
        return 0.0
    return sum(1 for t in itens if re.search(rx, sem_acento(t.lower()))) / len(itens) * 100


def _casa(texto: str, rx: str) -> bool:
    return bool(re.search(rx, sem_acento(texto.lower())))


# ── endereçamento de asset ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Alvo:
    """Endereço estável de UM recurso dentro do payload.

    A cascata regenera assets, não conjuntos. Sem um endereço estável a única
    substituição possível é "gere tudo de novo" — que queima os títulos bons
    junto com o ruim e viola o C2 (troca lateral, não descendente).
    """

    tipo: str          # headline | description | sitelink | callout | snippet
    indice: int
    sub: str = ""      # title | description1 | description2 | header (sitelink/snippet)

    def __str__(self) -> str:
        base = f"{self.tipo}[{self.indice}]"
        return f"{base}.{self.sub}" if self.sub else base

    @classmethod
    def de_texto(cls, campo: str) -> "Alvo | None":
        """`headline[3]` ou `sitelink[1].descricao1` → Alvo. Formato inválido → None.

        O juiz semântico devolve o endereço como TEXTO (é o que um LLM consegue
        produzir de forma estável). Sem esta tradução, a cascata receberia um
        achado sem alvo e regeneraria o conjunto inteiro — queimando os títulos
        bons junto com o ruim, que é exatamente o que a arquitetura por asset
        existe para evitar.
        """
        m = re.match(r"^([a-z_]+)\[(\d+)\](?:\.([a-z0-9_]+))?$", (campo or "").strip())
        if not m:
            return None
        return cls(tipo=m.group(1), indice=int(m.group(2)), sub=m.group(3) or "")

    def ler(self, dados: dict) -> str:
        if self.tipo == "snippet":
            sn = dados.get("snippet") or {}
            if self.sub == "header":
                return str(sn.get("header", ""))
            vals = sn.get("values") or []
            return str(vals[self.indice]) if self.indice < len(vals) else ""
        seq = dados.get(_PLURAL[self.tipo]) or []
        if self.indice >= len(seq):
            return ""
        item = seq[self.indice]
        return str(item.get(self.sub, "") if isinstance(item, dict) else item)

    def escrever(self, dados: dict, texto: str) -> None:
        # ⚠️ ÍNDICE FORA DA LISTA NÃO EXPLODE — e o snippet estava de fora disso.
        #
        # O caminho das listas já parava em `indice >= len(seq)`; o do snippet
        # não, e escrevia direto em `values[indice]`. A assimetria era latente
        # porque nenhuma checagem endereçava valor de snippet por índice — até a
        # C10 passar a endereçar. Medido no card 65 em 19/08/2026: a cascata
        # morreu inteira com `IndexError: list assignment index out of range`,
        # depois de os tokens já estarem pagos.
        #
        # O alvo some porque o mundo muda entre ACHAR e CONSERTAR: uma correção
        # de excesso (`CONTAGEM_EXCESSO`) corta a lista antes de a regeneração
        # deste achado rodar. Quem percebe que o alvo sumiu é `_regenerar`, que
        # anota no diário — aqui só não se derruba a geração por isso.
        if self.tipo == "snippet":
            sn = dados.setdefault("snippet", {})
            if self.sub == "header":
                sn["header"] = texto
                return
            vals = sn.setdefault("values", [])
            if self.indice < len(vals):
                vals[self.indice] = texto
            return
        seq = dados.setdefault(_PLURAL[self.tipo], [])
        if self.indice >= len(seq):
            return
        if isinstance(seq[self.indice], dict):
            seq[self.indice][self.sub] = texto
        else:
            seq[self.indice] = texto


_PLURAL = {
    "headline": "headlines",
    "description": "descriptions",
    "sitelink": "sitelinks",
    "callout": "callouts",
}

# Limites da API v25 — os mesmos de `limites.yaml`, por recurso endereçável.
MAX_CHARS = {
    ("headline", ""): 30,
    ("description", ""): 90,
    ("sitelink", "title"): 25,
    ("sitelink", "description1"): 35,
    ("sitelink", "description2"): 35,
    ("callout", ""): 25,
    ("snippet", ""): 25,
}


# ── achados ─────────────────────────────────────────────────────────────────


class Classe(Enum):
    """A classe decide o REMÉDIO. É o que a cascata consulta, não o código."""

    ESTRUTURA = "estrutura"                  # JSON/chaves quebradas → refaz
    FORMA_SANEAVEL = "forma_saneavel"        # normaliza em código, sem LLM
    FORMA_REESCREVER = "forma_reescrever"    # regenera o asset nomeado
    CONTAGEM_EXCESSO = "contagem_excesso"    # corta o excedente, sem LLM
    CONTAGEM_FALTA = "contagem_falta"        # regenera só o déficit
    ANCORAGEM_MENTIU = "ancoragem_mentiu"    # C4: refaz a passada 1 inteira
    COTA = "cota"                            # C6: fora de faixa após troca


@dataclass(frozen=True)
class Achado:
    codigo: str          # "C4.mecanica", "C1.chave_ausente"...
    classe: Classe
    detalhe: str
    alvo: Alvo | None = None

    @property
    def chave_regra(self) -> str:
        """O que a parada por 'mesma regra duas vezes' compara.

        É o CÓDIGO, não o detalhe: dois estouros de caractere no mesmo título
        são a mesma regra falhando duas vezes, mesmo com textos diferentes.
        """
        return self.codigo

    def __str__(self) -> str:
        onde = f" @{self.alvo}" if self.alvo else ""
        return f"[{self.classe.value}] {self.codigo}{onde}: {self.detalhe}"


# ── o pedido ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Pedido:
    """O que foi pedido ao modelo. É contra isto que a saída é conferida."""

    n_headlines: int = 15
    n_descriptions: int = 4
    # ⚠️ 6, e o número é do Google, não nosso: "ter 6 ou mais sitelinks no nível
    # de conta, campanha ou grupo melhora a sua pontuação" (Ad Strength).
    # O engine pedia 4 — o mínimo aceito — e o anúncio saía com "Adicione mais
    # sitelinks" sem check. A API aceita 20; 6 é onde a régua do Google vira.
    n_sitelinks: int = 6
    n_callouts: int = 6
    n_snippet: int = 6
    idioma: str = "pt"
    # País e vertical existem aqui por causa da C10: é com eles que o
    # `policy/spec.json` decide QUAIS regras se aplicam. Sem eles, a cascata
    # julgaria a copy com um conjunto de regras e o lançamento com outro.
    pais: str = "BR"
    vertical: str = "informativo"
    fatos: tuple[str, ...] = ()          # ids válidos: ("F1", "F2", ...)
    headers_snippet: tuple[str, ...] = ()
    max_dki: int = 1

    # ── cobertura do termo nos títulos ──────────────────────────────────────
    #
    # ⚠️ Medido no card 74 em 19/08/2026: 7 das 10 keywords do cluster contêm
    # "maquininha", e o termo aparecia em **1 de 15 títulos**. O Google marcou
    # "Inclua palavras-chave bastante usadas nos títulos" sem check, e a nota
    # ficou Médio.
    #
    # O `PROMPT.md` nunca pediu isso: ele limitava DKI a 1 e era silencioso
    # sobre cobertura. É uma exigência da régua do Google, não uma medição do
    # nosso corpus — e está declarada como tal, sem fingir que é medição da casa.
    raiz_do_termo: str = ""
    min_titulos_com_termo: int = 4
    # ⚠️ AS RAÍZES, NO PLURAL — e o piso passou a ser PROPORCIONAL.
    #
    # Medido no card 65 em 19/08/2026, DEPOIS do conserto do card 74: `fgts`
    # em 4 de 15 títulos, `min_titulos_com_termo` em 4. Passou raspando e o
    # Google devolveu Ad Strength **Ruim**, com o mesmo item sem check.
    #
    # Duas causas. Primeira: uma raiz só. As 82 keywords tinham `fgts` (56),
    # `saque` (55) e `aniversario` (46) praticamente empatados — porque o que a
    # pessoa digita são frases ("consultar fgts pelo cpf"). Cobrir uma delas
    # deixava passar "Modalidade: Elegibilidade" e "Vantagens da Modalidade".
    # Segunda: 4 é absoluto, e 4 em 15 é 27%.
    #
    # 0,6 é regra da casa derivada de uma reprovação medida, NÃO um número
    # publicado pelo Google — eles não publicam o limiar do Ad Strength. O que
    # se sabe medido é que 27% com uma raiz dá Ruim.
    raizes_do_termo: tuple[str, ...] = ()
    # ⚠️ ZERO, E O ZERO É MEDIDO — este número já foi 0,6.
    #
    # A fração existia para forçar a raiz em 60% dos títulos. Medido em
    # 19/08/2026 na campanha 24161105437: com a raiz em **15 de 15** títulos e
    # **4 de 4** descrições, o Google devolveu a MESMA nota (AVERAGE) e os
    # MESMOS dois itens da copy que tinha 4 de 15. A régua não move a agulha.
    #
    # E move a agulha para o lado ERRADO: cada título gasto repetindo a raiz é
    # um título que não espelha outra busca — que é o que o Google pede de
    # verdade (ver `C11`). A fração ficou em zero em vez de a checagem sumir
    # porque `min_titulos_com_termo` continua sendo um piso útil contra anúncio
    # completamente genérico; quem cobra cobertura agora é a variedade.
    fracao_titulos_com_termo: float = 0.0

    # ── VARIEDADE: o que o Google pede de verdade ───────────────────────────
    #
    # ⚠️ ESTE BLOCO EXISTE PORQUE A RÉGUA ACIMA FOI MEDIDA E NÃO FUNCIONOU.
    #
    # Medido no card 65 em 19/08/2026, campanha 24161105437, subida pausada só
    # para isto. A copy levou a cobertura de raiz ao TETO — `fgts`/`saque`/
    # `aniversario` em **15 de 15** títulos e **4 de 4** descrições, zero
    # pendência — e o Google devolveu a MESMA nota e os MESMOS dois itens da
    # campanha anterior, que tinha 4 de 15:
    #
    #     AVERAGE
    #       • Try including more keywords in your headlines.
    #       • Try including more keywords in your descriptions.
    #
    # Ou seja: "more keywords" nunca quis dizer "repita mais o termo". Quer
    # dizer MAIS KEYWORDS DISTINTAS do grupo. Medido nos textos que subiram:
    #
    #     keywords do grupo                        82
    #     cobertas por algum título/descrição        7
    #     vocabulário das keywords (palavras)       64
    #     presente nos textos                       15
    #
    # E o pior: empurrar a raiz para 15/15 REDUZ variedade, porque gasta os 30
    # caracteres de cada título repetindo o que já foi dito. Eu otimizei contra
    # a métrica que queria melhorar.
    #
    # Uma keyword conta como coberta quando TODAS as suas palavras de conteúdo
    # (≥3 letras) aparecem em UM mesmo título ou descrição — que é o que faz o
    # anúncio "espelhar" a busca.
    keywords_do_grupo: tuple[str, ...] = ()
    # Pelo menos uma keyword nova por título, em média. 15 títulos → 15 keywords
    # distintas. É regra da casa derivada da falha medida (7 cobertas → AVERAGE),
    # NÃO um limiar publicado pelo Google — eles não publicam o do Ad Strength.
    keywords_por_titulo: float = 1.0
    # Metade do vocabulário RECORRENTE presente em algum texto.
    #
    # ⚠️ "RECORRENTE" É A PALAVRA QUE SALVA ESTA REGRA DE SER IMPOSSÍVEL.
    #
    # A primeira versão cobrava metade de TODO o vocabulário das keywords: 32 de
    # 64 no card 65. Medido em 19/08/2026, a cascata entregou 18 e desistiu —
    # porque as 46 que faltavam incluíam `1331`, `www`, `gov`, `meu`, `nao`,
    # `ser`, `tenho`, `voltei`, `pediu`. São o jeito de UMA pessoa digitar uma
    # busca, não vocabulário do nicho, e nenhum título de 30 caracteres os
    # carrega. Regra insatisfazível não é rigor: é a cascata queimando rodada
    # atrás de rodada, exatamente como a cota de dígitos do C8 já fez.
    #
    # Palavra que aparece em UMA keyword de 82 é idiossincrasia. Em duas ou
    # mais, é o que as pessoas repetem — e aí cobrar faz sentido. Medido no
    # mesmo card: 36 palavras recorrentes, das quais a copy cobria 13.
    fracao_vocabulario: float = 0.5
    min_keywords_por_palavra: int = 2
    # ⚠️ AS DESCRIÇÕES TAMBÉM — e isto veio do próprio Google, não de dedução.
    # `ad_group_ad.action_items`, consultado em 19/08/2026 nas duas campanhas
    # da conta, devolveu palavra por palavra: "Try including more keywords in
    # your headlines." E: "Try including more keywords in your descriptions."
    # A C9 olhava só títulos; metade do pedido passava sem ninguém olhar.
    fracao_descricoes_com_termo: float = 0.5

    def alvos_texto(self) -> list[tuple[str, str, int]]:
        return [
            ("headline", "", self.n_headlines),
            ("description", "", self.n_descriptions),
            ("callout", "", self.n_callouts),
            ("snippet", "", self.n_snippet),
        ]


# ── cotas da seção 6 ────────────────────────────────────────────────────────
# Faixas medidas sobre 6.651 aprovados, declaradas no PROMPT.md para 15
# títulos. Fora de 15 elas são escaladas proporcionalmente — o PROMPT.md
# declara as faixas "em {n_headlines} títulos", e a proporção é a única
# leitura que não inventa número novo.

FAIXAS_15 = {
    "sem_verbo": (7, 8),
    "leitura": (4, 5),
    "verbo": (0, 2),
    "pergunta": (2, 3),
    "ano": (1, 2),
    "digito_nao_ano": (0, 1),
    "digito_total": (2, 3),
    "dois_blocos": (3, 4),
    "negacao": (0, 2),
    "contraste": (0, 1),
    "dki": (0, 1),
}


def faixas(n_headlines: int) -> dict[str, tuple[int, int]]:
    if n_headlines == 15:
        return dict(FAIXAS_15)
    f = n_headlines / 15
    return {
        k: (int(lo * f), max(int(lo * f), round(hi * f)))
        for k, (lo, hi) in FAIXAS_15.items()
    }


def medir(headlines: list[str], idioma: str = "pt") -> dict[str, int]:
    """A contagem de marcadores, na régua da seção 6. Absoluta, não percentual.

    É a MESMA medição que a checagem 6 compara com `auditoria.contagem_final`
    e que o orçamento de regeneração consulta. Uma função, três consumidores.
    """
    hs = [h for h in headlines if h]
    rx_contraste = RX_CONTRASTE.get(idioma, RX_CONTRASTE["en"])
    n = lambda rx: sum(1 for h in hs if _casa(h, rx))  # noqa: E731
    ano = n(RX_ANO)
    digito = n(RX_NUM)
    return {
        "sem_verbo": sum(1 for h in hs
                         if not _casa(h, RX_EXEC) and not _casa(h, RX_LEIT)),
        "leitura": n(RX_LEIT),
        "verbo": n(RX_EXEC),
        "pergunta": n(RX_PERG),
        "ano": ano,
        "digito_nao_ano": sum(
            1 for h in hs
            if re.search(RX_NUM, re.sub(RX_ANO, "", sem_acento(h.lower())))
        ),
        "digito_total": digito,
        "dois_blocos": sum(1 for h in hs if RX_DOIS_BLOCOS in h),
        "negacao": n(RX_NEGACAO),
        "contraste": n(rx_contraste),
        "dki": sum(1 for h in hs if _DKI.search(h)),
    }


# Qual headline carrega cada marcador. `medir()` devolve a CONTAGEM; isto
# devolve os ÍNDICES, e é a diferença entre dizer "9 títulos no mesmo molde" e
# poder mandar a cascata reescrever exatamente o 5º, o 6º e o 7º.
#
# ⚠️ Atravessa idioma pelo mesmo motivo que `medir()`: os marcadores são
# MECANISMO (dois-pontos, interrogação, dígito, tag DKI) e não vocabulário. Os
# dois que dependem de língua — `leitura`/`verbo` (regex pt/es/en) e `contraste`
# (`o` é contraste em espanhol e artigo em português) — já recebem o idioma.
def indices_por_marcador(headlines: list[str], idioma: str = "pt") -> dict[str, list[int]]:
    rx_contraste = RX_CONTRASTE.get(idioma, RX_CONTRASTE["en"])
    def onde(teste) -> list[int]:
        return [i for i, h in enumerate(headlines) if h and teste(h)]
    return {
        "sem_verbo": onde(lambda h: not _casa(h, RX_EXEC) and not _casa(h, RX_LEIT)),
        "leitura": onde(lambda h: _casa(h, RX_LEIT)),
        "verbo": onde(lambda h: _casa(h, RX_EXEC)),
        "pergunta": onde(lambda h: _casa(h, RX_PERG)),
        "ano": onde(lambda h: _casa(h, RX_ANO)),
        "digito_nao_ano": onde(
            lambda h: re.search(RX_NUM, re.sub(RX_ANO, "", sem_acento(h.lower())))),
        "digito_total": onde(lambda h: _casa(h, RX_NUM)),
        "dois_blocos": onde(lambda h: RX_DOIS_BLOCOS in h),
        "negacao": onde(lambda h: _casa(h, RX_NEGACAO)),
        "contraste": onde(lambda h: _casa(h, rx_contraste)),
        "dki": onde(lambda h: bool(_DKI.search(h))),
    }


def _c8_faixa_medida(dados: dict, pedido: Pedido) -> list[Achado]:
    """A cota MEDIDA contra a faixa dos aprovados. O portão que faltava.

    ## O buraco que isto fecha

    `FAIXAS_15` sai de 6.651 headlines aprovados e servindo, e `_cotas_fora()`
    já comparava o medido contra ela — mas o resultado ia para o DIÁRIO, nunca
    para um `Achado`. Ninguém reprovava.

    Medido em 18/08/2026, card 74: `dois_blocos` = **9 de 15** contra uma faixa
    de **3–4**. Nove títulos no molde `Assunto: Verbo`, 6,4× a taxa do corpus —
    e a única coisa que o sistema disse foi que o modelo declarou 4. A seção 6
    do `PROMPT.md` afirma que anúncio EXCELLENT cobre 6,44 mecânicas distintas
    contra 5,76 do GOOD; o prompt sabia, o contrato media, e nada obrigava.

    ## Por que aponta o ASSET e não o conjunto

    Um achado de conjunto vira pendência: a cascata não tem remédio por asset e
    o texto sobe torto. Nomeando os EXCEDENTES — os que passam do teto, do fim
    para o começo — a regeneração por asset já existente conserta, e
    `orcamento_restante()` diz ao prompt menor o que ainda cabe.

    ## Só o TETO reprova, nunca o piso

    Faltar `contraste` não estraga anúncio nenhum: é uma cor que não foi usada.
    Sobrar é que produz o título repetido N vezes. Reprovar por piso obrigaria
    o modelo a enfiar marcador para bater cota — que é como se fabrica texto
    artificial.
    """
    hs = [h for h in (dados.get("headlines") or []) if h]
    # ⚠️ SÓ JULGA CONJUNTO FECHADO.
    #
    # Distribuição de conjunto incompleto não é distribuição — é um pedaço. Com
    # 13 de 15 títulos a cascata ainda vai preencher duas vagas, e reprovar
    # agora manda regenerar um título que talvez já esteja certo. Quem raciocina
    # sobre vaga é `orcamento_restante()`, e ele existe exatamente para isso: o
    # prompt menor recebe o que AINDA cabe, em vez de um veredito prematuro.
    #
    # Faltar título já é achado de `_c2_contagem`; dois portões para o mesmo
    # defeito só produzem trabalho dobrado.
    if len(hs) != pedido.n_headlines:
        return []
    reais = medir(hs, pedido.idioma)
    onde = indices_por_marcador(hs, pedido.idioma)
    fx = faixas(pedido.n_headlines)

    fora: list[Achado] = []
    for marcador, (_lo, hi) in fx.items():
        # ⚠️ `sem_verbo` NÃO TEM TETO AQUI, e isso é decisão de política.
        #
        # Ele é o complemento de `leitura ∪ verbo`: limitar o teto dele é a
        # mesma coisa que exigir um PISO de verbo. E `verbo` é verbo de
        # EXECUÇÃO — solicitar, consultar, cadastrar —, que num portal
        # informativo é exatamente o que parece prometer serviço. Empurrar o
        # modelo para lá em nome de distribuição seria trocar CTR por risco de
        # suspensão na conta que sustenta a operação.
        #
        # O excesso de `sem_verbo` é o lado SEGURO do desvio. Ele continua
        # medido e continua no diário; só não reprova.
        if marcador == "sem_verbo":
            continue

        atual = reais.get(marcador, 0)
        # ⚠️ UM título acima do teto não é molde repetido — é ruído de uma faixa
        # MEDIDA, não de uma lei. Reprovar por 1 faria a cascata gastar uma
        # geração de LLM para trocar um título que os aprovados reais também
        # teriam. Molde repetido começa em DOIS excedentes.
        if atual <= hi + 1:
            continue
        # Os excedentes são os ÚLTIMOS: os primeiros `hi` ficam, e o modelo
        # tende a caprichar mais no começo da lista.
        excedentes = onde.get(marcador, [])[hi:]
        for i in excedentes:
            fora.append(Achado(
                "C8.cota_estourada", Classe.FORMA_REESCREVER,
                f"{marcador}: {atual} títulos, e a faixa medida em 6.651 "
                f"aprovados é até {hi}. Este é excedente — troque o molde.",
                Alvo("headline", i)))
    return fora


def orcamento_restante(
    headlines: list[str], pedido: Pedido, *, vagas: int
) -> dict[str, tuple[int, int]]:
    """Quanto de cada cota AINDA cabe, dadas as sobreviventes e as vagas.

    Este é o insumo que faltava no desenho anterior da regeneração. Sem ele o
    prompt menor pode entregar a quinta pergunta num conjunto cujo teto é 3 —
    o substituto passa em política, passa em forma, e estoura a seção 6 sem
    ninguém perceber até o C6 reprovar o conjunto inteiro.

    Devolve, por marcador, `(minimo_ainda_necessario, maximo_ainda_permitido)`
    para o total de `vagas` a preencher.
    """
    atual = medir(headlines, pedido.idioma)
    fx = faixas(pedido.n_headlines)
    out: dict[str, tuple[int, int]] = {}
    for marcador, (lo, hi) in fx.items():
        falta = max(0, lo - atual.get(marcador, 0))
        sobra = max(0, hi - atual.get(marcador, 0))
        out[marcador] = (min(falta, vagas), min(sobra, vagas))
    return out


# ── as mecânicas verificáveis (A9) ──────────────────────────────────────────
# Só entram as que uma regex decide. M1, M2, M3, M7, M10 e M11 dependem de
# leitura semântica — declará-las verificáveis produziria falso positivo, e
# falso positivo em portão é pior que portão ausente.

MECANICAS_VERIFICAVEIS = {
    "M4": ("dois blocos", lambda t, i: ":" in t),
    "M5": ("recência", lambda t, i: _casa(t, RX_RECENCIA)),
    "M6": ("dígito", lambda t, i: bool(re.search(RX_NUM, t))),
    "M8": ("pergunta", lambda t, i: ("?" in t) and (i != "es" or "¿" in t)),
    "M9": ("data/prazo", lambda t, i: _casa(t, RX_PRAZO)),
    "M12": ("contraste", lambda t, i: _casa(t, RX_CONTRASTE.get(i, RX_CONTRASTE["en"]))),
}

# Marcadores de afirmação concreta — o que a checagem 7 exige lastrear.
RX_CONCRETO = r"(\d|\bate\b|\bhasta\b|\bnovo\b|\bnova\b|\bmudou\b|\bmuda\b)"


# ── as 7 checagens ──────────────────────────────────────────────────────────


def checar(dados: dict, pedido: Pedido, *, semantico_ativo: bool = False) -> list[Achado]:
    """Roda as checagens determinísticas. Devolve todos os achados, sem parar.

    ## ⚠️ `semantico_ativo` desliga C7 e C8, e o motivo é de competência

    Estas duas dependem de uma distinção que padrão de texto não faz: separar
    NOME PRÓPRIO de ALEGAÇÃO.

    Medido no card 74 em 19/08/2026, nicho de comparação de maquininhas:

      C7 acusou `'Point Pro 3 Mercado Pago'` de "afirmação concreta sem fato
         declarado" — são dois nomes de produto, não há alegação nenhuma.
      C8 contou o `3` de `Point Pro 3`, o `2` de `Minizinha NFC 2` e o `3` de
         `T3 Smart` como dígitos de valor, e a cota `digito_nao_ano ≤ 1 em 15`
         virou **insatisfazível dizendo a verdade** — a cascata queimou 142 s
         tentando obedecer uma regra impossível.

    Além disso a faixa de C8 foi medida em 6.651 aprovados das contas desta
    operação, que eram todas de BENEFÍCIO PÚBLICO (FGTS, INSS, Pé de Meia).
    Aplicá-la a comparação de produto é usar número medido fora do domínio em
    que foi medido — exatamente o defeito que esta casa existe para não cometer.

    Com o juiz semântico ligado, quem julga sentido é ele. O que fica aqui é o
    que é EXATO e onde o modelo é comprovadamente pior: estrutura, contagem,
    caracteres e reconciliação. Na mesma geração em que ele errou o sentido,
    declarou 1 dígito onde havia 3 e 1 verbo onde havia 0.
    """
    achados: list[Achado] = []
    achados += _c1_estrutura(dados, pedido)
    if any(a.classe is Classe.ESTRUTURA for a in achados):
        return achados  # sem estrutura, as outras medem lixo
    achados += _c2_contagem(dados, pedido)
    achados += _c3_ancoragem(dados, pedido)
    achados += _c4_chars(dados, pedido)
    achados += _c5_mecanica(dados, pedido)
    achados += _c6_contagem_final(dados, pedido)
    if not semantico_ativo:
        achados += _c8_faixa_medida(dados, pedido)
        achados += _c7_fato(dados, pedido)
    achados += _c9_cobertura_do_termo(dados, pedido)
    achados += _c10_portao_do_lancamento(dados, pedido)
    achados += _c11_variedade_de_keywords(dados, pedido)
    achados += _forma(dados, pedido)
    return achados


def _conteudo(texto: str) -> set[str]:
    """As palavras que carregam sentido de busca: 3+ caracteres, sem acento.

    Dígitos entram — `2026` é o que separa "calendário fgts" de "calendário
    fgts 2026", e são buscas diferentes.
    """
    return {p for p in re.split(r"[^a-z0-9]+", sem_acento(str(texto or "").lower()))
            if len(p) >= 3}


def medir_variedade(dados: dict, keywords: Sequence[str],
                    *, min_keywords_por_palavra: int = 2) -> dict:
    """Quantas keywords DISTINTAS o anúncio espelha. É a régua da C11.

    Separada da checagem porque é medição, e medição tem de poder ser olhada
    sem levantar achado — é com ela que se compara uma copy com a outra.

    ⚠️ `min_keywords_por_palavra` decide o que é VOCABULÁRIO e o que é jeito de
    uma pessoa digitar. Palavra que aparece em uma keyword de 82 (`1331`, `www`,
    `tenho`, `voltei`) não cabe em título de 30 caracteres, e cobrá-la torna a
    regra insatisfazível — ver o comentário em `Pedido.fracao_vocabulario`.
    """
    textos = [str(t or "") for t in (dados.get("headlines") or [])]
    textos += [str(t or "") for t in (dados.get("descriptions") or [])]
    conjuntos = [_conteudo(t) for t in textos]

    cobertas, ausentes = [], []
    quantas: Counter = Counter()
    for k in keywords:
        alvo = _conteudo(k)
        quantas.update(alvo)
        if alvo and any(alvo <= c for c in conjuntos):
            cobertas.append(k)
        else:
            ausentes.append(k)

    vocab = {p for p, n in quantas.items() if n >= max(1, min_keywords_por_palavra)}
    presentes = set()
    for c in conjuntos:
        presentes |= c
    return {
        "keywords": len(list(keywords)),
        "cobertas": cobertas,
        "ausentes": ausentes,
        "vocabulario": len(vocab),
        "vocabulario_presente": len(vocab & presentes),
        "vocabulario_ausente": sorted(vocab - presentes),
    }


def _c11_variedade_de_keywords(dados: dict, pedido: Pedido) -> list[Achado]:
    """O anúncio precisa ESPELHAR keywords distintas, não repetir uma raiz.

    ## ⚠️ ESTA CHECAGEM NASCEU DE UM ERRO MEU, MEDIDO

    A C9 cobra que o termo apareça em muitos títulos. Eu a escrevi lendo o item
    do Google — "Try including more keywords in your headlines" — como "repita
    mais o termo". Está errado, e a prova é a campanha 24161105437, subida
    pausada em 19/08/2026 só para medir:

        copy anterior   raiz em  4 de 15 títulos, 2 de 4 descrições → AVERAGE
        copy nova       raiz em 15 de 15 títulos, 4 de 4 descrições → AVERAGE
                        (os MESMOS dois itens, palavra por palavra)

    Levar a cobertura de raiz ao teto não moveu a nota. E medindo os textos que
    subiram, dá para ver por quê:

        keywords do grupo                        82
        cobertas por algum título/descrição        7
        vocabulário das keywords (palavras)       64
        presente nos textos                       15

    "More keywords" quer dizer MAIS KEYWORDS DISTINTAS. Pior: empurrar a raiz
    para 15/15 gasta os 30 caracteres de cada título repetindo o que já foi
    dito — a régua antiga trabalhava CONTRA a métrica que queria melhorar.

    ## O que ela cobra

    Duas coisas, porque uma sozinha se engana:

    1. **Keywords cobertas** — quantas buscas o anúncio espelha inteiras. Conta
       quando TODAS as palavras de conteúdo da keyword aparecem num MESMO
       título ou descrição.
    2. **Vocabulário** — quanto do léxico do grupo aparece em algum lugar.
       Existe porque 15 títulos não cabem 82 keywords: cobrir só o item 1
       deixaria `cpf`, `extrato`, `aplicativo` e `saldo` fora para sempre, e são
       eles que fazem o anúncio casar com a busca da pessoa.

    Devolve achado SEM alvo: qual título trocar é escolha do modelo, e apontar
    um específico o faria trocar o errado.

    ## ✅ E ELA FOI MEDIDA CONTRA O GOOGLE — o primeiro Bom desta operação

    Campanha `24156373085`, mesma conta, mesmo dia, subida pausada com a copy
    que esta checagem aprovou:

        4/15 de raiz  ·  7/82 keywords espelhadas · 13/36 vocabulário → Médio
        15/15 de raiz ·  7/82 keywords espelhadas · 13/36 vocabulário → Médio
        raiz livre    · 16/82 keywords espelhadas · 16/36 vocabulário → **Bom**

    A segunda linha é a que prova a causa: cobertura de raiz no TETO, mesma nota.
    A terceira mudou só a variedade, e a nota subiu.

    ⚠️ Dois avisos sobre o que este número NÃO é:

    · Não é limiar do Google — eles não publicam o do Ad Strength. É a menor
      variedade que ESTA conta aceitou, nesta data, neste nicho.
    · Não é o teto. O painel ainda mostrava "Inclua palavras-chave bastante
      usadas nos títulos" DESMARCADO quando a nota virou Bom. Existe folga
      acima, e ela mora nas keywords de maior volume — que o cluster do
      Pautador já traz (`volume: high|medium|low`) e esta checagem ainda ignora.
    """
    kws = [str(k) for k in (pedido.keywords_do_grupo or ()) if str(k or "").strip()]
    if not kws:
        return []
    hs = dados.get("headlines") or []
    if not hs:
        return []

    m = medir_variedade(dados, kws,
                        min_keywords_por_palavra=pedido.min_keywords_por_palavra)
    fora: list[Achado] = []

    # Teto óbvio: não dá para cobrir mais keywords do que existem, nem mais do
    # que um título por keyword. Cobrar o impossível trava a cascata.
    alvo_cob = min(len(kws), int(len(hs) * pedido.keywords_por_titulo + 0.999))
    if len(m["cobertas"]) < alvo_cob:
        exemplos = "; ".join(repr(k) for k in m["ausentes"][:6])
        fora.append(Achado(
            "C11.keywords_cobertas", Classe.FORMA_REESCREVER,
            f"o anúncio espelha {len(m['cobertas'])} das {len(kws)} keywords do "
            f"grupo, e precisa espelhar {alvo_cob}. Não repita o termo: cada "
            f"título deve nomear uma BUSCA DIFERENTE. Nenhum texto cobre estas: "
            f"{exemplos}",
            None))

    alvo_voc = int(m["vocabulario"] * pedido.fracao_vocabulario + 0.999)
    if m["vocabulario_presente"] < alvo_voc:
        fora.append(Achado(
            "C11.vocabulario", Classe.FORMA_REESCREVER,
            f"{m['vocabulario_presente']} das {m['vocabulario']} palavras que as "
            f"pessoas digitam aparecem no anúncio, e são precisas {alvo_voc}. "
            f"Estas não aparecem em lugar nenhum: "
            f"{', '.join(m['vocabulario_ausente'][:12])}",
            None))
    return fora


def _barra_o_lancamento(viol) -> bool:
    """Esta violação IMPEDE o mutate — pelo critério do portão, não pelo meu.

    `_SEVERIDADE_BARRA` e `_SO_AVISO` vêm de `campanha/search.py`, que é quem
    decide isso na hora de subir. Importar de lá em vez de copiar é o ponto
    inteiro da C10: duas cópias do critério divergem na primeira mudança, e a
    divergência reaparece como reprovação surpresa no `/provar`.
    """
    from ..campanha.search import _SEVERIDADE_BARRA, _SO_AVISO  # noqa: PLC0415

    return viol.regra not in _SO_AVISO and viol.severidade in _SEVERIDADE_BARRA


def _c10_portao_do_lancamento(dados: dict, pedido: Pedido) -> list[Achado]:
    """O MESMO portão que o `/provar` aplica, rodado aqui, antes de custar.

    ## Por que esta checagem existe

    Medido no card 65 em 19/08/2026. A copy saiu da cascata com zero achado de
    contrato — 13 de 15 títulos com o termo, 4 de 4 descrições, o melhor
    resultado até então — e o `/provar` a reprovou na hora:

        [erro] description: Repetição de palavra dentro do mesmo texto
               (política 14848296)
               → "Guia completo SOBRE o FGTS... tire suas dúvidas SOBRE as
                  regras de 2026"

    O portão do lançamento (`policy/spec.json`, via `subir.preparar`) cobrava
    uma regra que o contrato da copy NÃO cobrava. Resultado: a cascata declarava
    a copy pronta, o operador clicava em provar, e a reprovação chegava depois
    de a geração inteira estar paga — sem ninguém para consertar, porque a
    cascata já tinha terminado.

    Dois julgadores com réguas diferentes sobre o mesmo texto é o defeito. Aqui
    não há régua nova: é o mesmo `Validador`, o mesmo `spec.json`, os mesmos
    campos. O que muda é a HORA — dentro da cascata, onde ainda há remédio.

    ## O que entra e o que não entra

    Só o que BARRA o mutate — e "o que barra" não é lido do spec cru: é
    `campanha/search._SEVERIDADE_BARRA` menos `search._SO_AVISO`, importados de
    lá. Copiar o critério para cá seria recriar o defeito um nível abaixo.

    ⚠️ Isso importa de verdade, e eu já errei aqui: a primeira versão desta
    checagem lia `viol.severidade == "erro"` direto do spec e passou a barrar
    `editorial.maiusculas.tudo_caixa_alta`, que o portão real REBAIXA a aviso
    de propósito (a exceção de sigla é lista fechada, e "Resolução CCFGTS
    1.130/2025" fica de fora dela — ver o comentário em `search._SO_AVISO`).
    Resultado: a C10 virou mais dura que o portão que ela existe para espelhar,
    e a cascata passaria a refazer copy por causa de uma sigla legítima.

    Aviso não impede lançar e continua aparecendo na tela do `/provar`;
    transformá-lo em achado faria a cascata gastar rodadas para calar um alerta
    que não bloqueia nada.

    E as raízes do termo saem da repetição ENTRE itens pelo mesmo motivo que
    saem do `F.repeticao` — ver o comentário lá. Sem essa saída, a C9 mandaria
    repetir o termo e a C10 proibiria, e a cascata ficaria oscilando entre as
    duas até esgotar o teto de refazer.
    """
    from ..policy.spec import Validador  # noqa: PLC0415 — carrega o spec.json

    v = Validador(pais=pedido.pais, vertical=pedido.vertical, idioma=pedido.idioma)
    raizes = {sem_acento(str(r).lower()) for r in (pedido.raizes_do_termo or ())}

    # ⚠️ O tipo do `Alvo` é SINGULAR ("description"), não o nome da lista:
    # `Alvo.ler` resolve o plural pelo `_PLURAL`. Passar "descriptions" aqui
    # estoura `KeyError` lá dentro — na hora de CONSERTAR, não na de achar.
    sn = dados.get("snippet") or {}
    listas: list[tuple[str, list[str]]] = [
        ("headline", [str(h or "") for h in (dados.get("headlines") or [])]),
        ("description", [str(d or "") for d in (dados.get("descriptions") or [])]),
        ("callout", [str(x or "") for x in (dados.get("callouts") or [])]),
        ("snippet", [str(x or "") for x in (sn.get("values") or [])]),
    ]

    fora: list[Achado] = []
    for campo, textos in listas:
        for viol in v.checar_lista(textos, campo):
            if not _barra_o_lancamento(viol):
                continue
            # Violação de item traz o TEXTO; a de conjunto traz a PALAVRA.
            if viol.texto and sem_acento(viol.texto.lower()) in raizes:
                continue
            indice = next((i for i, t in enumerate(textos)
                           if t[:90] == viol.texto), None)
            fora.append(Achado(
                f"C10.{viol.regra}", Classe.FORMA_REESCREVER,
                f"{viol.titulo} → {viol.texto!r}",
                Alvo(campo, indice) if indice is not None else None))

    # Sitelinks têm três textos por item e campos próprios no spec.
    for i, s in enumerate(dados.get("sitelinks") or []):
        if not isinstance(s, dict):
            continue
        for sub, campo in (("title", "sitelink_titulo"),
                           ("description1", "sitelink_desc"),
                           ("description2", "sitelink_desc")):
            for viol in v.checar_texto(str(s.get(sub) or ""), campo):
                if viol.severidade != "erro":
                    continue
                fora.append(Achado(
                    f"C10.{viol.regra}", Classe.FORMA_REESCREVER,
                    f"{viol.titulo} → {viol.texto!r}", Alvo("sitelink", i, sub)))
    return fora


def _c9_cobertura_do_termo(dados: dict, pedido: Pedido) -> list[Achado]:
    """O termo que as pessoas buscam tem de aparecer nos títulos.

    ⚠️ Medido no card 74 em 19/08/2026: 7 das 10 keywords do cluster continham
    "maquininha" e o termo aparecia em **1 de 15 títulos**. O Google devolveu
    "Inclua palavras-chave bastante usadas nos títulos" sem check, e a nota do
    anúncio ficou Médio.

    Esta checagem NÃO vem do corpus da casa — vem da régua de Ad Strength do
    Google, e está declarada como tal. O corpus mediu molde e política; nunca
    mediu cobertura de termo.

    Ela devolve UM achado sem alvo quando falta cobertura: qual título trocar é
    escolha do modelo, e apontar um específico o faria trocar o título errado.

    ## ⚠️ O CARD 65 PASSOU AQUI E O GOOGLE DEU **RUIM**

    Medido em 19/08/2026, depois do conserto do card 74: `fgts` aparecia em
    **4 de 15** títulos e `min_titulos_com_termo` era 4. Passou raspando, num
    limiar que eu havia CHUTADO — e a nota veio Ruim, com o mesmo item sem
    check.

    Dois defeitos, não um:

    1. **Uma raiz só.** `raiz_do_termo` escolhe a mais frequente por maioria e
       devolveu `fgts` (56 das 82 keywords), ignorando `saque` (55) e
       `aniversario` (46). Praticamente empatados — porque o que a pessoa
       digita são FRASES. Títulos como "Modalidade: Elegibilidade" não
       carregavam nenhum dos três e passavam.
    2. **Piso absoluto.** "Pelo menos 4" não escala: 4 em 15 é 27%.

    Agora a régua é PROPORCIONAL e vale para o conjunto de raízes: pelo menos
    `fracao_titulos_com_termo` dos títulos precisa carregar ALGUMA delas.
    """
    raizes = tuple(
        sem_acento(str(r or "").lower()).strip()
        for r in (pedido.raizes_do_termo or ())
        if str(r or "").strip()
    )
    if not raizes:
        # Compatibilidade com quem ainda passa uma raiz só.
        uma = sem_acento((pedido.raiz_do_termo or "").lower()).strip()
        raizes = (uma,) if uma else ()
    if not raizes:
        return []
    fora: list[Achado] = []

    # ── AS DESCRIÇÕES TAMBÉM, e isso veio do PRÓPRIO GOOGLE ─────────────────
    #
    # ⚠️ Não é dedução minha. Consultado em 19/08/2026, `ad_group_ad.action_items`
    # das duas campanhas da conta devolveu, palavra por palavra:
    #
    #     "Try including more keywords in your headlines."
    #     "Try including more keywords in your descriptions."
    #
    # Esta checagem olhava só títulos. Metade do que o Google pede passava sem
    # ninguém olhar — e nenhum limiar de título, por mais apertado, corrigiria
    # isso.
    ds = [str(d or "") for d in (dados.get("descriptions") or [])]
    if ds:
        norm_d = [sem_acento(d.lower()) for d in ds]
        com_d = sum(1 for d in norm_d if any(r in d for r in raizes))
        minimo_d = max(1, int(len(ds) * pedido.fracao_descricoes_com_termo + 0.999))
        if com_d < minimo_d:
            sem = [d for d, n in zip(ds, norm_d) if not any(r in n for r in raizes)]
            fora.append(Achado(
                "C9.cobertura_desc", Classe.FORMA_REESCREVER,
                f"os termos ({', '.join(raizes)}) aparecem em {com_d} de "
                f"{len(ds)} descrições, e são precisas {minimo_d} — o Google "
                f"pede keyword nas descrições tanto quanto nos títulos. Estas "
                f"não nomeiam nenhum: {'; '.join(repr(t) for t in sem[:3])}",
                None))

    hs = [str(h or "") for h in (dados.get("headlines") or [])]
    if not hs:
        return fora

    # O DKI conta: `{KeyWord:Saque-Aniversário FGTS}` entrega o termo no leilão.
    normalizados = [sem_acento(h.lower()) for h in hs]
    com = sum(1 for h in normalizados if any(r in h for r in raizes))
    minimo = max(pedido.min_titulos_com_termo,
                 int(len(hs) * pedido.fracao_titulos_com_termo + 0.999))
    if com >= minimo:
        return fora

    faltam = [h for h, n in zip(hs, normalizados) if not any(r in n for r in raizes)]
    return fora + [Achado(
        "C9.cobertura", Classe.FORMA_REESCREVER,
        f"os termos que as pessoas buscam ({', '.join(raizes)}) aparecem em "
        f"{com} de {len(hs)} títulos, e são precisos {minimo}. Reescreva "
        f"títulos genéricos para nomear um dos termos — estes não nomeiam "
        f"nenhum: {'; '.join(repr(t) for t in faltam[:5])}",
        None)]


def _c1_estrutura(dados: dict, pedido: Pedido) -> list[Achado]:
    fora: list[Achado] = []
    esperado = {
        "headlines": list, "descriptions": list, "sitelinks": list,
        "callouts": list, "snippet": dict, "ancoragem": dict, "auditoria": dict,
    }
    for chave, tipo in esperado.items():
        if chave not in dados:
            fora.append(Achado("C1.chave_ausente", Classe.ESTRUTURA,
                               f"chave {chave!r} ausente na saída"))
        elif not isinstance(dados[chave], tipo):
            fora.append(Achado("C1.tipo_errado", Classe.ESTRUTURA,
                               f"{chave!r} deveria ser {tipo.__name__}"))
    return fora


def _c2_contagem(dados: dict, pedido: Pedido) -> list[Achado]:
    fora: list[Achado] = []
    alvos = [
        ("headlines", pedido.n_headlines, "headline"),
        ("descriptions", pedido.n_descriptions, "description"),
        ("sitelinks", pedido.n_sitelinks, "sitelink"),
        ("callouts", pedido.n_callouts, "callout"),
    ]
    for chave, esperado, tipo in alvos:
        tem = len(dados.get(chave) or [])
        if tem > esperado:
            fora.append(Achado(
                "C2.excesso", Classe.CONTAGEM_EXCESSO,
                f"{chave}: {tem} > {esperado} pedidos",
                Alvo(tipo, esperado)))
        elif tem < esperado:
            fora.append(Achado(
                "C2.falta", Classe.CONTAGEM_FALTA,
                f"{chave}: {tem} < {esperado} pedidos ({esperado - tem} faltando)",
                Alvo(tipo, tem)))
    vals = (dados.get("snippet") or {}).get("values") or []
    if len(vals) != pedido.n_snippet:
        classe = (Classe.CONTAGEM_EXCESSO if len(vals) > pedido.n_snippet
                  else Classe.CONTAGEM_FALTA)
        fora.append(Achado("C2.snippet", classe,
                           f"snippet.values: {len(vals)} != {pedido.n_snippet}",
                           Alvo("snippet", min(len(vals), pedido.n_snippet))))
    header = (dados.get("snippet") or {}).get("header", "")
    if pedido.headers_snippet and header not in pedido.headers_snippet:
        fora.append(Achado("C2.header", Classe.FORMA_REESCREVER,
                           f"header {header!r} fora dos permitidos",
                           Alvo("snippet", 0, "header")))
    return fora


def _c3_ancoragem(dados: dict, pedido: Pedido) -> list[Achado]:
    """Uma entrada por título, índices contíguos. Sem isto, 4 a 7 não têm base."""
    entradas = (dados.get("ancoragem") or {}).get("headlines") or []
    hs = dados.get("headlines") or []
    fora: list[Achado] = []
    if len(entradas) != len(hs):
        fora.append(Achado(
            "C3.desalinhada", Classe.ANCORAGEM_MENTIU,
            f"ancoragem.headlines tem {len(entradas)} entradas para {len(hs)} títulos"))
        return fora
    vistos = sorted(int(e.get("i", -1)) for e in entradas if isinstance(e, dict))
    if vistos != list(range(len(hs))):
        fora.append(Achado(
            "C3.indice", Classe.ANCORAGEM_MENTIU,
            f"índices da ancoragem não são 0..{len(hs) - 1}: {vistos}"))
    return fora


def _c4_chars(dados: dict, pedido: Pedido) -> list[Achado]:
    """`chars` declarado contra o comprimento efetivo.

    Divergir aqui não é erro de conta: é prova de que o modelo declarou uma
    conferência que não fez. O remédio não é corrigir o número — é refazer.
    """
    fora: list[Achado] = []
    hs = dados.get("headlines") or []
    for e in (dados.get("ancoragem") or {}).get("headlines") or []:
        if not isinstance(e, dict) or "chars" not in e:
            continue
        i = int(e.get("i", -1))
        if not 0 <= i < len(hs):
            continue
        real = comprimento_efetivo(str(hs[i]))
        declarado = int(e["chars"])
        if declarado != real:
            fora.append(Achado(
                "C4.chars", Classe.ANCORAGEM_MENTIU,
                f"declarou chars={declarado}, o efetivo é {real}",
                Alvo("headline", i)))
    return fora


def _c5_mecanica(dados: dict, pedido: Pedido) -> list[Achado]:
    """A9 — a mecânica declarada é cumprida pela própria string.

    A checagem mais barata do arquivo e a que mais informa: rótulo errado
    corrói exatamente a auditoria que a `ancoragem` existe para permitir.
    """
    fora: list[Achado] = []
    hs = dados.get("headlines") or []
    for e in (dados.get("ancoragem") or {}).get("headlines") or []:
        if not isinstance(e, dict):
            continue
        mec = str(e.get("mecanica", "")).upper().strip()
        i = int(e.get("i", -1))
        if mec not in MECANICAS_VERIFICAVEIS or not 0 <= i < len(hs):
            continue
        nome, cumpre = MECANICAS_VERIFICAVEIS[mec]
        if not cumpre(str(hs[i]), pedido.idioma):
            fora.append(Achado(
                "C5.mecanica", Classe.ANCORAGEM_MENTIU,
                f"declarou {mec} ({nome}) e a string não cumpre: {hs[i]!r}",
                Alvo("headline", i)))
    return fora


#: Códigos em que o modelo erra a CONTAGEM QUE ELE MESMO DECLAROU — nunca o
#: anúncio.
#:
#: ⚠️ ESTA SEPARAÇÃO EXISTE PORQUE ELA CUSTOU O CARD 65.
#:
#: Medido em 19/08/2026. A cascata reescreveu a copy, a C9 gerou o achado certo
#: ("os termos aparecem em 7 de 15 títulos, e são precisos 9") — e morreu antes
#: de corrigi-lo. O diário:
#:
#:     → C4: a passada 2 foi teatro (C4.chars). Refaz a passada 1 inteira (1/1)
#:     · mentira de conjunto (C6.divergencia): não há versão por asset
#:     ✗ ancoragem mentiu de novo e o teto de refazer (1) estourou
#:
#: `C4.chars` e `C6.divergencia` são o modelo errando a própria contabilidade —
#: "declarou 7, medido 8" num marcador de estilo. O QUE ELES DECLARAM já é
#: medido de forma independente: o limite real de caracteres é `_c4_chars`, e a
#: distribuição real é `medir()`. A divergência não muda uma letra do que vai
#: ao ar.
#:
#: A própria tela já dizia a verdade: "3 divergências na auto-declaração do
#: modelo — não afetam o anúncio". E mesmo assim elas consumiam o ÚNICO
#: refazer, deixando sem conserto a cobertura de termo — que é o que o Google
#: pune de verdade, com Ad Strength.
#:
#: Inversão de prioridade: um erro de contagem cosmético gastava o orçamento
#: que o defeito publicável precisava. Agora eles viram pendência relatada, e o
#: refazer pertence a quem afeta o anúncio.
AUTO_DECLARACAO: frozenset[str] = frozenset({
    "C4.chars", "C6.divergencia", "C6.ausente",
})


def _c6_contagem_final(dados: dict, pedido: Pedido) -> list[Achado]:
    """`auditoria.contagem_final` contra a medição.

    O PROMPT.md avisa que estar on-distribution não prova licitude. Verdade —
    mas DIVERGIR do que se declarou prova que a passada 2 foi teatro, e é isso
    que esta checagem mede.
    """
    declarado = (dados.get("auditoria") or {}).get("contagem_final") or {}
    if not declarado:
        return [Achado("C6.ausente", Classe.ANCORAGEM_MENTIU,
                       "auditoria.contagem_final ausente")]
    real = medir(dados.get("headlines") or [], pedido.idioma)
    fora: list[Achado] = []
    for marcador, valor in real.items():
        if marcador not in declarado:
            continue
        if int(declarado[marcador]) != valor:
            fora.append(Achado(
                "C6.divergencia", Classe.ANCORAGEM_MENTIU,
                f"{marcador}: declarou {declarado[marcador]}, medido {valor}"))
    return fora


def _c7_fato(dados: dict, pedido: Pedido) -> list[Achado]:
    """Toda afirmação concreta aponta um `fato` que EXISTE.

    Existência, não suficiência — ver o aviso no topo do arquivo. Um título
    que transforma "até 5 parcelas" em "5 parcelas" passa aqui.
    """
    fora: list[Achado] = []
    hs = dados.get("headlines") or []
    anc = (dados.get("ancoragem") or {}).get("headlines") or []
    por_indice = {int(e["i"]): e for e in anc if isinstance(e, dict) and "i" in e}

    for i, h in enumerate(hs):
        if not _casa(str(h), RX_CONCRETO):
            continue
        entrada = por_indice.get(i, {})
        fid = str(entrada.get("fato", "-")).strip()
        if fid in ("-", ""):
            fora.append(Achado(
                "C7.sem_lastro", Classe.FORMA_REESCREVER,
                f"afirmação concreta sem fato declarado: {h!r}",
                Alvo("headline", i)))
        elif pedido.fatos and fid not in pedido.fatos:
            fora.append(Achado(
                "C7.fato_inexistente", Classe.ANCORAGEM_MENTIU,
                f"declara fato {fid!r}, que não existe no brief",
                Alvo("headline", i)))

    for e in (dados.get("ancoragem") or {}).get("descriptions") or []:
        if not isinstance(e, dict):
            continue
        fatos = e.get("fatos") or []
        if "-" in fatos or not fatos:
            # ⚠️ A mensagem tem de dizer QUAL dos dois casos disparou. Ela
            # falava só do '-' e, quando a lista vinha VAZIA, mandava o
            # operador procurar um traço que não existia no JSON.
            motivo = ("declarou `-`, e o PROMPT.md proíbe traço em descrição"
                      if "-" in fatos else "não declarou fato nenhum")
            fora.append(Achado(
                "C7.descricao_sem_fato", Classe.FORMA_REESCREVER,
                f"descrição sem fato: {motivo}",
                Alvo("description", int(e.get("i", 0)))))
    return fora


def _forma(dados: dict, pedido: Pedido) -> list[Achado]:
    """Forma determinística, separada em SANEÁVEL e REESCREVER.

    A separação é a economia central da cascata: espaço duplo se resolve com
    `re.sub`, e gastar uma geração nisso é queimar dinheiro e arriscar perder
    um título bom na troca. Estouro de caractere não se resolve cortando —
    cortar muda o sentido, e sentido é o que a passada 2 auditou.
    """
    fora: list[Achado] = []

    for tipo, sub, _ in pedido.alvos_texto():
        limite = MAX_CHARS[(tipo, sub)]
        itens = _sequencia(dados, tipo)
        vistos: dict[str, int] = {}
        for i, bruto in enumerate(itens):
            t = str(bruto or "")
            alvo = Alvo(tipo, i, sub)
            if not t.strip():
                fora.append(Achado("F.vazio", Classe.FORMA_REESCREVER,
                                   "recurso vazio", alvo))
                continue
            if re.search(r"[!?]{2,}|\.{3,}|\s{2,}", t) or t != t.strip():
                fora.append(Achado("F.pontuacao", Classe.FORMA_SANEAVEL,
                                   f"espaço/pontuação repetido: {t!r}", alvo))
            simb = [c for c in t if unicodedata.category(c) in ("So", "Sk", "Cs")]
            if simb:
                fora.append(Achado("F.simbolo", Classe.FORMA_SANEAVEL,
                                   f"símbolo/emoji {simb!r}", alvo))
            if comprimento_efetivo(_sanear_texto(t)) > limite:
                fora.append(Achado(
                    "F.comprimento", Classe.FORMA_REESCREVER,
                    f"{comprimento_efetivo(t)} chars > {limite}: {t!r}", alvo))
            chave = sem_acento(t.lower()).strip()
            if chave in vistos:
                fora.append(Achado("F.duplicata", Classe.FORMA_REESCREVER,
                                   f"duplica [{vistos[chave]}]: {t!r}", alvo))
            vistos[chave] = i

    # Repetição entre títulos (política 14848296). O alvo é o ÚLTIMO título que
    # carrega a palavra: derrubar o primeiro perderia a melhor ocorrência dela.
    #
    # ⚠️ AS RAÍZES DO TERMO NÃO CONTAM — E ISSO NÃO É EXCEÇÃO DE CONVENIÊNCIA.
    #
    # Medido no card 65 em 19/08/2026: a copy nova saiu com 13 de 15 títulos
    # carregando o termo — exatamente o que a C9 cobra e o que o Google pediu
    # ("Try including more keywords in your headlines", lido de `ad_group_ad.
    # action_items`) — e caiu aqui com DUAS pendências: 'fgts' em 11 títulos,
    # 'saque' em 8, teto de 4.
    #
    # Ou seja: uma regra deste arquivo mandava repetir o termo e a outra proibia.
    # Enquanto as duas contam a mesma palavra, a cascata gasta rodadas tentando
    # satisfazer as duas ao mesmo tempo e, na tentativa, TIRA o termo dos
    # títulos — desfazendo a cobertura que é o motivo de tudo isto existir. É o
    # motor brigando consigo mesmo, o mesmo defeito que o prompt já teve.
    #
    # O teto continua valendo para todo o resto do vocabulário, que é onde a
    # política 14848296 realmente mora: título repetitivo é o que diz a mesma
    # coisa com as mesmas palavras. Repetir o termo buscado não é repetição
    # gratuita — é relevância, e quem arbitra isso é o Ad Strength.
    hs = [str(h or "") for h in (dados.get("headlines") or [])]
    raizes = {sem_acento(str(r).lower()) for r in (pedido.raizes_do_termo or ())}
    palavras: Counter = Counter()
    dono: dict[str, int] = {}
    for i, h in enumerate(hs):
        for p in set(re.findall(r"\b[^\W\d_]{4,}\b", sem_acento(h.lower()))):
            palavras[p] += 1
            dono[p] = i
    for p, n in palavras.items():
        if p in raizes:
            continue
        if n > 4:
            fora.append(Achado(
                "F.repeticao", Classe.FORMA_REESCREVER,
                f"palavra {p!r} aparece em {n} títulos (máx 4)",
                Alvo("headline", dono[p])))

    dki = sum(1 for h in hs if _DKI.search(h))
    if dki > pedido.max_dki:
        fora.append(Achado("F.dki", Classe.FORMA_REESCREVER,
                           f"DKI em {dki} títulos (máx {pedido.max_dki})",
                           Alvo("headline", next(i for i, h in enumerate(hs)
                                                 if _DKI.search(h)))))
    return fora


def _sequencia(dados: dict, tipo: str) -> list:
    if tipo == "snippet":
        return (dados.get("snippet") or {}).get("values") or []
    return dados.get(_PLURAL[tipo]) or []


# ── saneamento determinístico ───────────────────────────────────────────────


def _sanear_texto(t: str) -> str:
    t = "".join(c for c in t if unicodedata.category(c) not in ("So", "Sk", "Cs"))
    t = re.sub(r"([!?])\1+", r"\1", t)
    t = re.sub(r"\.{3,}", ".", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def sanear(dados: dict) -> tuple[dict, list[str]]:
    """Conserta o que se conserta sem LLM. Devolve (dados, o que foi feito).

    Roda ANTES de qualquer geração. Toda linha aqui é uma chamada de modelo
    que não aconteceu.
    """
    feitos: list[str] = []
    for tipo in ("headline", "description", "callout", "snippet"):
        itens = _sequencia(dados, tipo)
        for i, bruto in enumerate(itens):
            if not isinstance(bruto, str):
                continue
            limpo = _sanear_texto(bruto)
            if limpo != bruto:
                Alvo(tipo, i).escrever(dados, limpo)
                feitos.append(f"{Alvo(tipo, i)}: {bruto!r} → {limpo!r}")
    for i, s in enumerate(dados.get("sitelinks") or []):
        if not isinstance(s, dict):
            continue
        for sub in ("title", "description1", "description2"):
            bruto = str(s.get(sub, ""))
            limpo = _sanear_texto(bruto)
            if limpo != bruto:
                s[sub] = limpo
                feitos.append(f"sitelink[{i}].{sub}: {bruto!r} → {limpo!r}")
    return dados, feitos


def cortar_excesso(dados: dict, pedido: Pedido) -> list[str]:
    """Corta o que veio a mais. Determinístico, pelo fim, sem LLM."""
    feitos: list[str] = []
    for chave, n in (("headlines", pedido.n_headlines),
                     ("descriptions", pedido.n_descriptions),
                     ("sitelinks", pedido.n_sitelinks),
                     ("callouts", pedido.n_callouts)):
        seq = dados.get(chave) or []
        if len(seq) > n:
            feitos.append(f"{chave}: cortados {len(seq) - n} do fim")
            dados[chave] = seq[:n]
            anc = (dados.get("ancoragem") or {}).get(chave)
            if isinstance(anc, list) and len(anc) > n:
                dados["ancoragem"][chave] = anc[:n]
    vals = (dados.get("snippet") or {}).get("values") or []
    if len(vals) > pedido.n_snippet:
        feitos.append(f"snippet.values: cortados {len(vals) - pedido.n_snippet}")
        dados["snippet"]["values"] = vals[:pedido.n_snippet]
    return feitos
