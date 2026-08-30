"""Contrato canônico de critério de keyword — a positiva e a negativa no mesmo tipo.

## Por que este módulo existe

Até aqui uma keyword era uma `str` dentro de uma `list[str]`, e tudo o que a
distinguia de outra vinha do NOME DO CAMPO em que ela morava: `Brief.keywords`
era positiva, `Brief.negativas_campanha` era negativa de campanha,
`SubIntencao.negativas` era negativa daquele grupo. O match type não morava na
keyword: `Brief.match_type` era um só para o brief inteiro, e as negativas nem
isso tinham — `search.py` as escrevia todas em `BROAD`, fixo no código.

Isso tem três consequências que só aparecem com a campanha no ar:

1. **O match type da negativa era uma ficção.** Negativar "curso gratis" em
   BROAD bloqueia toda consulta que contenha as duas palavras em qualquer
   ordem, com qualquer coisa no meio — "curso de ingles gratis para
   iniciantes" morre junto. Quem escreveu a negativa queria, quase sempre,
   PHRASE ou EXACT. O engine trocava a intenção do operador por uma regra
   fixa, e nada no payload denunciava a troca.

2. **A procedência sumia.** Uma negativa vinda de `search_term_view` com 300
   impressões e zero conversão e uma negativa que um modelo de linguagem
   chutou olhando a landing page chegavam ao payload como a mesma `str`. Na
   hora de auditar por que a campanha não entrega, não havia como separar o
   que foi medido do que foi imaginado.

3. **O erro sumia junto.** `checar_keywords()` recebia um `Resultado()`
   descartável (ver `search.py`, versão anterior), então negativa com 90
   caracteres ou 12 palavras era silenciosamente removida do payload sem uma
   linha de aviso. A campanha subia sem a proteção que o operador declarou.

`Criterio` é a resposta às três: o texto, o match type, o nível, o grupo, a
origem, o motivo e a evidência viajam juntos, num objeto imutável, do cockpit
até a operação da API.

## A regra da ausência

Ausência é `None`, nunca um valor inventado. Um critério sem motivo declarado
tem `motivo=None` — não `""`, não `"sem motivo"`. Um critério sem evidência
medida tem `evidencia=None`, e a interface é obrigada a mostrá-lo como
hipótese. Preencher a ausência com um default plausível é como se perde a
diferença entre "ninguém mediu" e "mediu e deu zero".

## O que este módulo NÃO decide

Não decide se uma keyword é boa, não sugere negativa, não tem lista de
"negativas universais". A doutrina da casa é que negativa sem evidência
medida é proposta, não fato — e proposta se aprova no cockpit, uma a uma. A
lista genérica de `free`, `jobs`, `salary` que as ferramentas de mercado
aplicam por bom senso é exatamente o que produz o bloqueio excessivo que
`conflitos()` existe para detectar.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any

#: Os três match types de keyword da Google Ads API v25 (`KeywordMatchTypeEnum`).
#: `UNSPECIFIED` e `UNKNOWN` existem no enum mas são de leitura — não se
#: escreve um critério com eles.
MATCH_TYPES: tuple[str, ...] = ("EXACT", "PHRASE", "BROAD")

#: Onde o critério é anexado. `CAMPAIGN` vira `CampaignCriterion`, `AD_GROUP`
#: vira `AdGroupCriterion`. Não existe nível `ACCOUNT` aqui de propósito: a
#: negativa de conta (`CustomerNegativeCriterion`) atravessa TODAS as campanhas
#: da conta, inclusive as que este engine não criou, e por isso não pode nascer
#: de um brief de campanha nova.
NIVEIS: tuple[str, ...] = ("CAMPAIGN", "AD_GROUP")

#: De onde o critério veio. Não é rótulo decorativo: é o que separa o medido do
#: imaginado na hora de auditar.
#:
#:   MANUAL       o operador digitou no cockpit
#:   PAUTADOR     veio da mineração de keywords (`pautador_keyword_clusters`)
#:   SITE         extraído da landing page — hipótese até alguém medir
#:   SEARCH_TERM  observado em `search_term_view` na conta real
#:   LEGADO       veio de um contrato antigo `list[str]`, sem match type próprio
ORIGENS: tuple[str, ...] = ("MANUAL", "PAUTADOR", "SITE", "SEARCH_TERM", "LEGADO")

#: Evidência MEDIDA saiu de um relatório da conta, com janela e números.
#: Evidência HIPÓTESE saiu de um modelo, de uma heurística ou do bom senso.
#: A interface tem obrigação de mostrar a diferença; misturar as duas é como
#: um número inventado vira decisão de orçamento.
TIPOS_EVIDENCIA: tuple[str, ...] = ("MEDIDO", "HIPOTESE")


def chave(texto: str) -> str:
    """Chave de comparação: minúscula, espaço colapsado — e ACENTO PRESERVADO.

    Escrita aqui e não importada de `conteudo.chave` por duas diferenças, e as
    duas são deliberadas.

    1. **Colapsa espaço**, o que lá não acontece: `"curso  gratis"` e
       `"curso gratis"` são a mesma keyword, e deduplicar sem isso manda duas
       operações para o mesmo critério — a API recusa a segunda e, num mutate
       atômico, derruba a campanha inteira.

    2. **NÃO remove acento**, o que lá acontece. Esta é a diferença que importa,
       e a razão é de assimetria de custo:

       - se o Google tratar `"grátis"` e `"gratis"` como a mesma coisa, mandar
         as duas custa uma operação redundante que a API aceita;
       - se tratar como coisas diferentes — e a doutrina de negativa é que ela
         NÃO expande para variantes próximas, que é o que `bloqueia()` afirma
         logo abaixo —, deduplicar as duas APAGA um bloqueio que o operador
         declarou, e a campanha compra o tráfego que ele mandou excluir.

       Mandar as duas nunca é pior. Apagar uma pode ser. Na dúvida sobre o
       comportamento da API, escolhe-se o lado em que errar é barato.

    ⚠️ `conteudo.chave` continua removendo acento, e continua certo para o que
    ela serve: a dedup de keyword POSITIVA entre ad groups, onde o Google de
    fato casa variantes próximas e duas grafias competiriam entre si.
    """
    s = unicodedata.normalize("NFC", texto.strip().lower())
    return " ".join(s.split())


def _tokens(texto: str) -> list[str]:
    return chave(texto).split()


@dataclass(frozen=True)
class Evidencia:
    """O que sustenta um critério — e de que tipo é esse sustento.

    `janela_inicio`/`janela_fim` e `metricas` só fazem sentido em evidência
    MEDIDA. Uma hipótese não tem janela: inventar uma seria transformar o chute
    em observação, que é precisamente o defeito que este tipo existe para
    impedir.
    """

    tipo: str
    fonte: str
    janela_inicio: date | None = None
    janela_fim: date | None = None
    metricas: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS_EVIDENCIA:
            raise ValueError(
                f"tipo de evidência {self.tipo!r} inválido — use "
                f"{' ou '.join(TIPOS_EVIDENCIA)}"
            )
        if not self.fonte.strip():
            raise ValueError("evidência sem fonte — quem observou isto?")
        if self.tipo == "MEDIDO":
            # Medição sem janela não é medição: sem o período, "300 impressões"
            # não distingue um dia ruim de um trimestre ruim, e a decisão de
            # negativar muda completamente entre os dois.
            if self.janela_inicio is None or self.janela_fim is None:
                raise ValueError(
                    "evidência MEDIDO exige janela (janela_inicio e janela_fim) "
                    "— número sem período não sustenta decisão"
                )
            if self.janela_fim < self.janela_inicio:
                raise ValueError("janela invertida: janela_fim antes de janela_inicio")
            # Observação no FUTURO não é observação. A guarda de `SEARCH_TERM`
            # era só estrutural: bastava preencher três campos para carimbar
            # "medido na conta", e uma janela de 2030 passava. Continua sendo
            # possível declarar métricas que ninguém conferiu contra a conta —
            # isso só se fecha quando existir um produtor real de evidência
            # (o tribunal lexical do F6) —, mas o que é impossível de ser
            # verdade agora é recusado agora.
            if self.janela_inicio > date.today():
                raise ValueError(
                    f"janela começa em {self.janela_inicio.isoformat()}, no "
                    "futuro — observação medida não pode começar depois de hoje"
                )
            if not self.metricas:
                raise ValueError(
                    "evidência MEDIDO exige métricas — o que exatamente foi medido?"
                )

    @property
    def medida(self) -> bool:
        return self.tipo == "MEDIDO"


@dataclass(frozen=True)
class Criterio:
    """Uma keyword — positiva ou negativa — com tudo o que a define.

    Imutável de propósito. Um critério que já entrou no cálculo do selo do
    payload não pode ser alterado em silêncio: para mudar, use
    `dataclasses.replace()`, que devolve outro objeto e portanto outro hash.
    """

    texto: str
    match_type: str = "PHRASE"
    negativa: bool = False
    nivel: str = "AD_GROUP"
    #: Nome da sub-intenção. `None` com `nivel="AD_GROUP"` significa TODOS os ad
    #: groups — é a semântica histórica de `Brief.negativas_adgroup`, preservada
    #: de propósito. Com nome, vale só naquele grupo.
    grupo: str | None = None
    origem: str = "MANUAL"
    motivo: str | None = None
    evidencia: Evidencia | None = None
    observado_em: datetime | None = None
    aprovado_por: str | None = None

    def __post_init__(self) -> None:
        if not self.texto or not self.texto.strip():
            raise ValueError("critério sem texto")
        if self.match_type not in MATCH_TYPES:
            raise ValueError(
                f"match_type {self.match_type!r} inválido — use "
                f"{', '.join(MATCH_TYPES)}"
            )
        if self.nivel not in NIVEIS:
            raise ValueError(f"nivel {self.nivel!r} inválido — use {', '.join(NIVEIS)}")
        if self.origem not in ORIGENS:
            raise ValueError(
                f"origem {self.origem!r} inválida — use {', '.join(ORIGENS)}"
            )
        # Não existe keyword POSITIVA de campanha na API: `CampaignCriterion`
        # aceita `keyword` apenas com `negative=True`. Deixar passar produziria
        # um payload que só falha na API, e num mutate atômico isso derruba a
        # campanha inteira por um campo que dava para checar aqui.
        if not self.negativa and self.nivel == "CAMPAIGN":
            raise ValueError(
                "keyword positiva não existe em nível de campanha — a API só "
                "aceita `CampaignCriterion.keyword` com `negative=True`. "
                "Use nivel='AD_GROUP'."
            )
        # Nível de campanha com grupo declarado é contradição: ou vale para a
        # campanha toda, ou vale para um grupo. Silenciar um dos dois é como a
        # negativa acaba no lugar errado.
        if self.nivel == "CAMPAIGN" and self.grupo is not None:
            raise ValueError(
                f"critério de campanha não pode declarar grupo ({self.grupo!r}) "
                "— escolha nivel='AD_GROUP' para restringir a um grupo"
            )
        if self.origem == "SEARCH_TERM" and (
            self.evidencia is None or not self.evidencia.medida
        ):
            # A origem SEARCH_TERM afirma observação na conta real. Sem a
            # janela e as métricas que a sustentam, é hipótese com crachá de
            # fato — o defeito exato que a doutrina da casa proíbe.
            raise ValueError(
                "origem SEARCH_TERM exige evidência MEDIDO com janela e "
                "métricas — termo observado sem os números que o observaram é "
                "hipótese vestida de fato"
            )

    # ── identidade ──────────────────────────────────────────────────────────

    @property
    def chave(self) -> str:
        """Texto normalizado. Não identifica o critério sozinho."""
        return chave(self.texto)

    @property
    def identidade(self) -> tuple[str, str, bool, str, str | None]:
        """O que torna dois critérios A MESMA operação para a API.

        Inclui o match type de propósito: "curso" EXACT e "curso" PHRASE são
        critérios DIFERENTES e legítimos no mesmo ad group — a API os aceita
        lado a lado. Deduplicar por texto só, como um `set(textos)` faria,
        apagaria um dos dois sem avisar.
        """
        return (self.chave, self.match_type, self.negativa, self.nivel, self.grupo)

    @property
    def medido(self) -> bool:
        """Este critério tem número de conta atrás dele, ou é hipótese?"""
        return self.evidencia is not None and self.evidencia.medida

    def em_grupo(self, nome: str) -> bool:
        """Este critério de ad group se aplica ao grupo `nome`?

        `grupo=None` vale em todos — é a semântica de `negativas_adgroup`.
        """
        if self.nivel != "AD_GROUP":
            return False
        return self.grupo is None or chave(self.grupo) == chave(nome)

    def bloqueia(self, consulta: str) -> bool:
        """Esta NEGATIVA bloquearia a consulta `consulta`?

        Semântica real da API, que não é a das keywords positivas:

          EXACT   bloqueia só a consulta idêntica.
          PHRASE  bloqueia consulta que contenha os tokens NA ORDEM, contíguos.
          BROAD   bloqueia consulta que contenha TODOS os tokens, em qualquer
                  ordem e não necessariamente juntos.

        ⚠️ Negativa NÃO expande para variantes próximas — plural, erro de
        digitação e sinônimo passam. É por isso que uma negativa BROAD parece
        inofensiva e não é: ela não expande, mas o "todos os tokens em qualquer
        ordem" já pega muito mais do que quem a escreveu costuma imaginar.
        """
        if not self.negativa:
            return False
        alvo = _tokens(consulta)
        meus = _tokens(self.texto)
        if not meus or not alvo:
            return False
        if self.match_type == "EXACT":
            return alvo == meus
        if self.match_type == "BROAD":
            return set(meus).issubset(set(alvo))
        # PHRASE — subsequência contígua na ordem declarada.
        n = len(meus)
        return any(alvo[i : i + n] == meus for i in range(len(alvo) - n + 1))


# ── adaptador de compatibilidade ────────────────────────────────────────────


def de_lista(
    textos: list[str],
    *,
    match_type: str = "PHRASE",
    negativa: bool = False,
    nivel: str = "AD_GROUP",
    grupo: str | None = None,
    origem: str = "LEGADO",
    motivo: str | None = None,
) -> list[Criterio]:
    """Converte o contrato antigo `list[str]` em critérios tipados.

    Existe para que todo cliente que já monta `Brief(keywords=[...])` continue
    funcionando sem uma linha de mudança — o adaptador é EXPLÍCITO, e é o único
    lugar do pacote autorizado a inventar um match type que o chamador não
    declarou. Código novo não deve passar por aqui: monte `Criterio` direto,
    com o match type que o operador escolheu.

    Condição de aposentadoria: quando nenhum caminho de entrada produzir
    `list[str]` — hoje ainda produzem o Pautador e os briefs versionados de
    `volc_ads/briefs/`.

    Texto vazio ou só espaço é DESCARTADO aqui em silêncio, e só aqui: é ruído
    de serialização (lista com vírgula sobrando), não declaração do operador.
    """
    saida: list[Criterio] = []
    for t in textos or []:
        if not t or not t.strip():
            continue
        saida.append(
            Criterio(
                texto=t.strip(),
                match_type=match_type,
                negativa=negativa,
                nivel=nivel,
                grupo=grupo,
                origem=origem,
                motivo=motivo,
            )
        )
    return saida


def textos(criterios: list[Criterio]) -> list[str]:
    """Volta para `list[str]` — para quem ainda lê o contrato antigo."""
    return [c.texto for c in criterios]


# ── deduplicação e conflito ─────────────────────────────────────────────────


def deduplicar(
    criterios: list[Criterio],
) -> tuple[list[Criterio], list[tuple[Criterio, Criterio]]]:
    """Remove critérios com a mesma identidade, preservando a ORDEM de entrada.

    Devolve `(únicos, descartados)`, onde cada descartado vem com o critério
    que o venceu — sem esse par, "duplicata removida" não diz qual sobreviveu,
    e as duas podem ter motivo e origem diferentes.

    O primeiro declarado vence. É determinístico de propósito: ordenar por
    origem ou por "qualidade" faria o payload mudar entre duas execuções com a
    mesma entrada, e o selo do payload deixaria de significar alguma coisa.
    """
    vistos: dict[tuple, Criterio] = {}
    unicos: list[Criterio] = []
    descartados: list[tuple[Criterio, Criterio]] = []
    for c in criterios:
        dono = vistos.get(c.identidade)
        if dono is not None:
            descartados.append((c, dono))
            continue
        vistos[c.identidade] = c
        unicos.append(c)
    return unicos, descartados


def deduplicar_por_emissao(
    criterios: list[Criterio],
) -> tuple[list[Criterio], list[tuple[Criterio, Criterio]]]:
    """Dedup pelo que a API enxerga DENTRO de um recurso: (texto, match type).

    ⚠️ Não é o mesmo que `deduplicar`, e a diferença é a que derruba campanha.

    `Criterio.identidade` inclui o grupo, porque é assim que o operador declara:
    `grupo=None` significa "vale em todos os grupos" e `grupo="VALOR"` significa
    "vale só naquele". São declarações diferentes — identidades diferentes, e
    `deduplicar` está certo em manter as duas.

    Mas as duas RESOLVEM PARA O MESMO `ad_group` na hora de emitir a operação.
    O caso concreto, que o contrato antigo produz sozinho:

        Brief(negativas_adgroup=["gratis"],
              sub_intencoes=[SubIntencao("VALOR", [...], negativas=["gratis"])])

    Duas operações byte a byte iguais no mesmo ad group. A API recusa a segunda
    e, num mutate atômico, leva a campanha inteira junto.

    Por isso esta função roda DEPOIS de resolver quem vale em cada grupo, e
    compara só o que sobrevive à resolução.
    """
    vistos: dict[tuple[str, str], Criterio] = {}
    unicos: list[Criterio] = []
    descartados: list[tuple[Criterio, Criterio]] = []
    for c in criterios:
        k = (c.chave, c.match_type)
        dono = vistos.get(k)
        if dono is not None:
            descartados.append((c, dono))
            continue
        vistos[k] = c
        unicos.append(c)
    return unicos, descartados


@dataclass(frozen=True)
class Conflito:
    """Uma negativa que ANULA uma positiva declarada no mesmo payload.

    ⚠️ Só o caso PROVÁVEL entra aqui: a negativa bloqueia o texto da positiva
    tal como declarado, e portanto aquela keyword não pode servir NENHUMA
    consulta — nasce morta, e o dinheiro do grupo vai todo para as outras sem
    que nada no relatório explique por quê.

    O caso "a negativa apenas ESTREITA o tráfego da positiva" ficou de fora de
    propósito: decidir isso exigiria enumerar o espaço de consultas que uma
    keyword PHRASE ou BROAD alcança, que é aberto. Marcar por semelhança de
    palavras produziria alarme onde não há defeito — e alarme falso treina
    quem revisa a ignorar a faixa inteira, inclusive quando ela estiver certa.
    """

    negativa: Criterio
    positiva: Criterio

    def __str__(self) -> str:
        onde = (
            "na campanha"
            if self.negativa.nivel == "CAMPAIGN"
            else (
                "em todos os grupos"
                if self.negativa.grupo is None
                else f"no grupo {self.negativa.grupo!r}"
            )
        )
        return (
            f"a negativa {self.negativa.texto!r} ({self.negativa.match_type}) "
            f"anula a keyword {self.positiva.texto!r} {onde}"
        )


def conflitos(criterios: list[Criterio]) -> list[Conflito]:
    """Toda negativa que bloqueia uma positiva que alcança o mesmo escopo.

    O escopo importa: uma negativa do grupo `ACESSO` não conflita com a
    keyword do grupo `VALOR`, porque não a alcança. Uma negativa de campanha
    conflita com qualquer positiva, e uma negativa de ad group sem grupo
    declarado também — as duas atravessam tudo.

    Isto não é opinião sobre a qualidade da negativa: é a detecção de uma
    contradição que o operador declarou sem perceber. A campanha sobe, a
    keyword está lá, e ela nunca serve uma consulta.
    """
    positivas = [c for c in criterios if not c.negativa]
    negativas = [c for c in criterios if c.negativa]
    achados: list[Conflito] = []
    for n in negativas:
        for p in positivas:
            # Alcance: campanha pega todo mundo; ad group pega quem estiver no
            # mesmo grupo (ou todos, quando a negativa não declara grupo).
            if n.nivel == "AD_GROUP":
                if n.grupo is not None and p.grupo is not None:
                    if chave(n.grupo) != chave(p.grupo):
                        continue
                elif n.grupo is not None and p.grupo is None:
                    # Negativa de um grupo só contra positiva sem grupo: a
                    # positiva mora em todos os grupos, inclusive naquele.
                    pass
            if n.bloqueia(p.texto):
                achados.append(Conflito(negativa=n, positiva=p))
    return achados


def por_nivel(
    criterios: list[Criterio],
) -> tuple[list[Criterio], list[Criterio], list[Criterio]]:
    """Separa em (positivas, negativas de campanha, negativas de ad group).

    Uma função só, para que nenhum chamador refaça a triagem com um predicado
    ligeiramente diferente — foi assim que a negativa de grupo virou negativa
    de campanha na versão anterior.
    """
    positivas = [c for c in criterios if not c.negativa]
    neg_camp = [c for c in criterios if c.negativa and c.nivel == "CAMPAIGN"]
    neg_grupo = [c for c in criterios if c.negativa and c.nivel == "AD_GROUP"]
    return positivas, neg_camp, neg_grupo


__all__ = [
    "MATCH_TYPES",
    "NIVEIS",
    "ORIGENS",
    "TIPOS_EVIDENCIA",
    "Conflito",
    "Criterio",
    "Evidencia",
    "chave",
    "conflitos",
    "de_lista",
    "deduplicar",
    "por_nivel",
    "textos",
]
