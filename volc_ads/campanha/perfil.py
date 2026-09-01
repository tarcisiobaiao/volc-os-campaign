"""Perfil de canal — o índice do que cada canal do engine sabe fazer.

## O problema

Com UM canal, "o que o sistema sabe fazer" cabia num dicionário de uma linha
(`subir.CONSTRUTORES_POR_CANAL`) e todo o resto era implícito: `ai_max` era
parâmetro de `preparar()` porque Search tem `ai_max`; a autocorreção podava
keyword porque Search tem keyword; o nome da campanha não marcava canal porque
só havia um. Nada disso estava errado — estava **não declarado**.

Com dois canais, cada implícito vira um `if canal == …` em algum lugar. E `if`
espalhado é o desenho que obriga a varrer o produto inteiro quando o terceiro
canal chegar. A missão pede o contrário: *cada canal possui manifesto/capability
profile*.

Este módulo é esse perfil, do lado do ENGINE.

## Quem declara o quê — a regra que evita a terceira verdade

    fato                          declarado em            lido por
    ────────────────────────────  ──────────────────────  ─────────────────────
    como montar o grafo           campanha/<canal>.py     perfil (referência)
    lances aceitos                campanha/<canal>.py     perfil (referência)
    opções além do brief          campanha/<canal>.py     perfil (referência)
    quem sabe provar/criar        perfil.PERFIS           subir.py
    o que a TELA mostra           app/trafego/plataforma  o front

**Cada fato é declarado uma vez, no módulo do canal, e este índice o
REFERENCIA** — `PERFIS["DISPLAY"].lances_permitidos is display.LANCES_PERMITIDOS`.
Não há cópia para divergir, e a dependência aponta sempre canal → índice, o que
é o que impede o ciclo de import (`display.py` não conhece `perfil.py`).

`app/trafego/plataforma.ManifestoDeCanal` continua existindo e continua sendo a
verdade dita para a TELA — outra pergunta, outro vocabulário (ele fala em
"grupo" e "anúncio", rótulos que o operador lê; aqui se fala em `ad_group` e
`responsive_display_ad`, que são tipos da API). Ele **não copia** este arquivo:
`backend/tests/test_trafego_plataforma.py` compara o conjunto de canais que
sabem criar lendo `subir.py` por árvore sintática, sem importar o SDK do
Google, e `backend/tests/test_trafego_canal_de_criacao.py` faz o mesmo contra
este módulo. Duas verdades sobre o mesmo fato é o defeito; uma verdade e uma
projeção verificada, não.

⚠️ **O backend não pode importar este módulo.** Ele referencia os construtores,
que importam `google.ads.googleads` — e o Hub não depende do SDK em tempo de
import hoje. A coerência entre os dois é provada por leitura de árvore
sintática, justamente para continuar assim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, Optional, Tuple

from . import demand_gen, display, pmax, search

# ═══════════════════════════════════════════════════════════════════════════
# VOCABULÁRIO
# ═══════════════════════════════════════════════════════════════════════════

#: Os degraus do grafo, no vocabulário da API — não no da tela.
CAMPANHA = "campaign"
AD_GROUP = "ad_group"
ANUNCIO_RSA = "responsive_search_ad"
ANUNCIO_RDA = "responsive_display_ad"
ANUNCIO_DEMAND_GEN_MULTI_ASSET = "demand_gen_multi_asset_ad"
KEYWORD = "keyword"
ASSET_DE_CAMPANHA = "campaign_asset"
ASSET_DE_ANUNCIO = "ad_asset"

#: Apelidos de tela. `PMAX` é o que aparece em link antigo e em rótulo de
#: painel; ele nunca é valor de contrato (ADR-18) e é traduzido na fronteira.
APELIDOS: Dict[str, str] = {
    "PMAX": "PERFORMANCE_MAX",
}


class CanalSemConstrutor(ValueError):
    """O canal existe no inventário, mas ainda não possui builder seguro."""


class CanalSemPlanejador(ValueError):
    """O canal não sabe produzir um `plano.PlanoDeCanal`.

    Separada de `CanalSemConstrutor` de propósito: um canal pode saber PLANEJAR
    (montar offline e projetar) sem estar autorizado a PROVAR ou CRIAR — é
    exatamente o estado de Performance Max hoje. Colapsar as duas exceções
    faria a rota devolver "não possui builder provável" para um canal que
    monta, serializa e devolve plano completo.
    """


class OpcaoIndisponivel(ValueError):
    """Pediram ao construtor uma opção que este canal não tem."""


# ═══════════════════════════════════════════════════════════════════════════
# O PERFIL
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PerfilDeCanal:
    """O que este canal monta, com o quê, e o que ele NÃO faz.

    Campo vazio é resposta, não lacuna — a mesma doutrina do manifesto do Hub:
    `construtor=None` significa "não há como criar", e é o que faz a recusa
    acontecer por ausência DECLARADA em vez de por um `if` esquecido.
    """

    canal: str
    rotulo: str

    #: O modificador que entra no nome da campanha (`taxonomia.MODIFICADOR`).
    #: Vazio em Search de propósito: ele nasceu sem marcador e mudar o nome do
    #: que já subiu quebraria o `analisar()` sem consertar nada.
    marcador: str

    #: Os degraus que ESTE canal emite, do topo para baixo.
    hierarquia: Tuple[str, ...]

    #: Os campos do `Brief` que este canal de fato transforma em payload. O que
    #: o brief traz e não está aqui é ignorado — e o construtor avisa quando
    #: ignora, porque descarte em silêncio é o defeito.
    campos_operados: Tuple[str, ...]

    #: Monta o grafo. `None` = este canal não sabe criar.
    construtor: Optional[Callable[..., Any]] = None
    #: Monta e prova por `validate_only`. Anda junto com o construtor.
    validador: Optional[Callable[..., Any]] = None

    #: Monta offline e devolve `plano.PlanoDeCanal` — a forma serializável que
    #: a API e a tela consomem. **NÃO anda junto com o construtor**, e essa
    #: independência é o ponto: Performance Max planeja, serializa e devolve
    #: plano completo sem estar no registro do executor. Um canal que só sabe
    #: planejar responde a "o que aconteceria?" sem responder a "posso?".
    planejador: Optional[Callable[..., Any]] = None

    #: Se o único executor pode encaminhar este canal a ``mutar``. Demand Gen
    #: deliberadamente tem builder e validador, mas permanece False nesta onda.
    permite_mutacao_real: bool = False

    #: Quem lê a campanha DE VOLTA depois de criada. Não é um gancho vazio: é o
    #: endereço de quem responde "o que está na conta agora", e a resposta hoje
    #: é a mesma para os dois canais que criam.
    coletor: str = ""

    #: Os recursos criativos que o anúncio deste canal carrega.
    recursos_criativos: Tuple[str, ...] = ()

    #: `Brief.estrategia_lance` aceitos aqui.
    lances_permitidos: Tuple[str, ...] = ()

    #: Opções de construção além do brief (ex.: `ai_max`).
    opcoes: FrozenSet[str] = frozenset()

    #: As provas que separam "montei o pedido" de "posso gastar".
    provas_obrigatorias: Tuple[str, ...] = ()

    #: A autocorreção de política poda KEYWORD. Só faz sentido onde há keyword;
    #: nos outros canais ela remontaria o brief sem mudar nada e registraria no
    #: diário uma decisão que não existiu.
    autocorrige_keywords: bool = False

    acoes_permitidas: Tuple[str, ...] = ()
    acoes_indisponiveis: Tuple[str, ...] = ()

    @property
    def sabe_provar(self) -> bool:
        return self.construtor is not None

    @property
    def sabe_planejar(self) -> bool:
        """Produz plano serializável offline? Independente de provar/criar."""
        return self.planejador is not None

    @property
    def sabe_criar(self) -> bool:
        """Pode chegar a ``subir()`` e criar recurso remoto de verdade?"""
        return self.sabe_provar and self.permite_mutacao_real

    def __post_init__(self) -> None:
        if self.sabe_provar:
            if self.validador is None:
                raise ValueError(
                    f"{self.canal}: tem construtor e não tem validador. Montar "
                    f"sem poder provar é montar sem direito de gastar — o selo "
                    f"de `subir.py` sai do `validate_only`.")
            if not self.lances_permitidos:
                raise ValueError(
                    f"{self.canal}: sabe provar e não declara lance permitido. "
                    f"Sem a lista, o brief multicanal entrega qualquer "
                    f"estratégia e o canal a ignora em silêncio.")
            if not self.provas_obrigatorias:
                raise ValueError(
                    f"{self.canal}: sabe provar e não declara prova obrigatória.")
        if self.permite_mutacao_real and not self.sabe_provar:
            raise ValueError(
                f"{self.canal}: permite mutação real sem builder/validador"
            )


# ═══════════════════════════════════════════════════════════════════════════
# OS PERFIS DE HOJE
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ Nenhuma linha abaixo COPIA um fato do módulo do canal — ela o referencia.
# `search.LANCES_PERMITIDOS` é um objeto só, lido em dois lugares.

#: As provas que valem em qualquer canal que monte. `selo` é o `validate_only`
#: na conta real, e sem ele "montei o pedido" não é "posso gastar".
_PROVAS = ("politica", "duplicidade", "selo")

#: Quem lê a campanha de volta. Hoje é um só, para os dois canais: a varredura
#: do Hub, que inventaria a conta inteira independentemente de quem criou.
_COLETOR = "app/trafego/sincronizador.py (varredura do Hub)"

SEARCH = PerfilDeCanal(
    canal=search.CANAL,
    rotulo="Search",
    marcador="",
    hierarquia=(CAMPANHA, AD_GROUP, ANUNCIO_RSA, KEYWORD, ASSET_DE_CAMPANHA),
    campos_operados=(
        "keywords", "sub_intencoes", "negativas_campanha", "negativas_adgroup",
        "match_type", "cpc_inicial", "tcpa", "copy.headlines",
        "copy.descriptions", "copy.sitelinks", "copy.callouts", "copy.snippet",
        "url_final", "budget_diario", "estrategia_lance",
    ),
    construtor=search.construir,
    validador=search.validar,
    planejador=search.planejar,
    coletor=_COLETOR,
    recursos_criativos=("texto", "sitelink", "callout", "structured_snippet"),
    lances_permitidos=search.LANCES_PERMITIDOS,
    opcoes=search.OPCOES,
    provas_obrigatorias=_PROVAS,
    autocorrige_keywords=True,
    permite_mutacao_real=True,
    acoes_permitidas=("montar", "provar", "subir"),
)

DISPLAY = PerfilDeCanal(
    canal=display.CANAL,
    rotulo="Display",
    marcador="Display",
    hierarquia=(CAMPANHA, AD_GROUP, ANUNCIO_RDA, ASSET_DE_ANUNCIO),
    campos_operados=(
        "copy.headlines", "copy.long_headlines", "copy.descriptions",
        "copy.business_name", "imagens_display", "videos", "url_final",
        "budget_diario", "tcpa", "estrategia_lance",
    ),
    construtor=display.construir,
    validador=display.validar,
    planejador=display.planejar,
    coletor=_COLETOR,
    recursos_criativos=("texto", "imagem_marketing", "imagem_marketing_quadrada",
                        "logo", "logo_quadrado", "video_youtube"),
    lances_permitidos=display.LANCES_PERMITIDOS,
    opcoes=display.OPCOES,
    provas_obrigatorias=_PROVAS,
    autocorrige_keywords=False,
    permite_mutacao_real=True,
    acoes_permitidas=("montar", "provar", "subir"),
    acoes_indisponiveis=display.NAO_OPERADO,
)

DEMAND_GEN = PerfilDeCanal(
    canal=demand_gen.CANAL,
    rotulo="Demand Gen",
    marcador="GD",
    hierarquia=(CAMPANHA, AD_GROUP, ANUNCIO_DEMAND_GEN_MULTI_ASSET,
                ASSET_DE_ANUNCIO),
    campos_operados=(
        "copy.headlines", "copy.descriptions", "copy.business_name",
        "imagens_demand_gen", "demand_gen.upgraded_targeting",
        "demand_gen.controles_de_canal", "demand_gen.audiencias",
        "demand_gen.intencoes", "demand_gen.exclusoes_de_audiencia",
        "url_final", "budget_diario", "estrategia_lance",
    ),
    construtor=demand_gen.construir,
    validador=demand_gen.validar,
    planejador=demand_gen.planejar,
    coletor=_COLETOR,
    recursos_criativos=(
        "texto", "imagem_marketing", "imagem_marketing_quadrada",
        "imagem_marketing_retrato", "imagem_marketing_retrato_alto",
        "logo_quadrado",
    ),
    lances_permitidos=demand_gen.LANCES_PERMITIDOS,
    opcoes=demand_gen.OPCOES,
    provas_obrigatorias=_PROVAS,
    autocorrige_keywords=False,
    permite_mutacao_real=False,
    acoes_permitidas=("inventariar", "montar", "provar"),
    acoes_indisponiveis=demand_gen.NAO_OPERADO,
)

#: ⚠️ **`construtor` e `validador` continuam `None`, e isso é uma DECISÃO.**
#:
#: `campanha/pmax.py` existe, monta o grafo completo, serializa os protos v25 e
#: devolve plano — está referenciado abaixo em `planejador`. O que ele NÃO faz é
#: entrar no registro do executor, e o motivo é mecânico: `sabe_provar` deriva de
#: `construtor is not None`, `subir.py` compara `PROVADORES_POR_CANAL` com
#: `canais_que_provam()` **no import** e levanta se divergirem. Preencher
#: `construtor` aqui sem mexer em `subir.py`, no backend e em `plataforma.py`
#: derrubaria a rota HTTP dos QUATRO canais — trocar um canal novo por uma
#: regressão nos três que funcionam.
#:
#: `planejador` é o campo que permite dizer a verdade inteira: PMax **planeja** e
#: não **prova**. Sem ele, a única forma de expressar "este canal faz alguma
#: coisa" seria ligar o construtor, e a única forma de expressar "não pode
#: gastar" seria não fazer nada.
PERFORMANCE_MAX = PerfilDeCanal(
    canal=pmax.CANAL,
    rotulo="Performance Max",
    marcador="Pmax",
    #: PMax é o único canal SEM ad group e SEM anúncio: o Google monta a
    #: combinação a partir dos assets ligados ao asset group.
    hierarquia=(CAMPANHA, "asset_group", "asset_group_asset",
                "asset_group_signal", ASSET_DE_CAMPANHA),
    campos_operados=(
        "copy.headlines", "copy.long_headlines", "copy.descriptions",
        "copy.business_name", "imagens_pmax", "pmax.brand_guidelines_enabled",
        "pmax.mensuracao", "pmax.sinais", "pmax.negativas",
        "pmax.nome_do_asset_group", "url_final", "budget_diario", "tcpa",
        "target_roas", "estrategia_lance",
    ),
    planejador=pmax.planejar,
    coletor="volc_ads/observabilidade_pmax (kernel read-only, GAQL v25)",
    recursos_criativos=(
        "texto", "imagem_marketing", "imagem_marketing_quadrada",
        "imagem_marketing_retrato", "logo", "logo_paisagem", "video_youtube",
    ),
    lances_permitidos=pmax.LANCES_PERMITIDOS,
    opcoes=pmax.OPCOES,
    autocorrige_keywords=False,
    permite_mutacao_real=False,
    acoes_permitidas=("inventariar", "planejar"),
    acoes_indisponiveis=(
        "criar: Performance Max não está no registro do executor "
        "(`subir.CONSTRUTORES_POR_CANAL`). O canal existe no inventário porque "
        "a conta pode ter campanhas dele, e escondê-las seria mentir sobre o "
        "que está gastando.",
        "provar por validate_only: o builder monta e serializa offline, e a "
        "prova externa exige o canal habilitado no executor — mudança "
        "coordenada em subir.py, backend e plataforma.py. Ver "
        "`plano.PMAX_FORA_DO_EXECUTOR`.",
    ) + pmax.NAO_OPERADO,
)

PERFIS: Dict[str, PerfilDeCanal] = {
    p.canal: p for p in (SEARCH, DISPLAY, DEMAND_GEN, PERFORMANCE_MAX)
}


# ═══════════════════════════════════════════════════════════════════════════
# CONSULTA
# ═══════════════════════════════════════════════════════════════════════════


def canonizar(canal: Any) -> str:
    """`" pmax "` → `PERFORMANCE_MAX`. O apelido nunca chega ao registro."""
    bruto = str(canal or "").strip().upper()
    return APELIDOS.get(bruto, bruto)


def perfil(canal: Any) -> Optional[PerfilDeCanal]:
    return PERFIS.get(canonizar(canal))


def canais_que_criam() -> Tuple[str, ...]:
    """Canais autorizados a chegar ao mutate real."""
    return tuple(sorted(c for c, p in PERFIS.items() if p.sabe_criar))


def canais_que_provam() -> Tuple[str, ...]:
    """Canais com builder e validate_only, mesmo sem mutação real."""
    return tuple(sorted(c for c, p in PERFIS.items() if p.sabe_provar))


def canais_que_planejam() -> Tuple[str, ...]:
    """Canais que montam offline e devolvem plano serializável.

    Superconjunto de `canais_que_provam()`: Performance Max planeja e não prova.
    """
    return tuple(sorted(c for c, p in PERFIS.items() if p.sabe_planejar))


def exigir(canal: Any) -> PerfilDeCanal:
    """O perfil, e ele PRECISA poder criar remotamente."""
    canonico = canonizar(canal)
    p = PERFIS.get(canonico)
    if p is None or not p.sabe_criar:
        disponiveis = ", ".join(canais_que_criam())
        raise CanalSemConstrutor(
            f"canal {canonico or '(vazio)'} ainda não possui construtor seguro; "
            f"disponível para criação: {disponiveis}. O inventário pode ler "
            "outros canais sem autorizar sua criação."
        )
    return p


def exigir_prova(canal: Any) -> PerfilDeCanal:
    """O perfil, e ele PRECISA ter builder + validate_only."""
    canonico = canonizar(canal)
    p = PERFIS.get(canonico)
    if p is None or not p.sabe_provar:
        disponiveis = ", ".join(canais_que_provam())
        raise CanalSemConstrutor(
            f"canal {canonico or '(vazio)'} ainda não possui builder provável; "
            f"disponível para montar/validate_only: {disponiveis}."
        )
    return p


def montar(canal: Any, cid: str, brief: Any, *, login_customer_id: str, **opcoes):
    """Chama o construtor do canal com as opções que ELE declara aceitar.

    É o que substitui o `if canal == …` que a segunda entrada no registro
    criaria. `preparar()` não sabe que `ai_max` é de Search — ele passa a opção
    e o perfil decide. Opção pedida em canal que não a tem é RECUSADA, não
    ignorada: ignorar faria o operador marcar uma caixa que não faz nada.
    """
    p = exigir_prova(canal)
    pedidas = {k for k, v in opcoes.items() if v}
    faltantes = sorted(pedidas - set(p.opcoes))
    if faltantes:
        raise OpcaoIndisponivel(
            f"{p.rotulo} não tem a opção {', '.join(faltantes)}. "
            f"Opções deste canal: {', '.join(sorted(p.opcoes)) or '(nenhuma)'}. "
            f"Desmarque no pedido ou escolha um canal que a tenha."
        )
    aceitas = {k: v for k, v in opcoes.items() if k in p.opcoes}
    return p.construtor(cid, brief, login_customer_id=login_customer_id, **aceitas)


def exigir_planejador(canal: Any) -> PerfilDeCanal:
    """O perfil, e ele PRECISA saber montar offline e projetar o plano."""
    canonico = canonizar(canal)
    p = PERFIS.get(canonico)
    if p is None or not p.sabe_planejar:
        disponiveis = ", ".join(canais_que_planejam())
        raise CanalSemPlanejador(
            f"canal {canonico or '(vazio)'} não sabe produzir plano; "
            f"disponível para planejar: {disponiveis}."
        )
    return p


def planejar(canal: Any, cid: str, brief: Any, *, login_customer_id: str,
             **opcoes):
    """Monta offline e devolve `plano.PlanoDeCanal`. **Não fala com o Google.**

    É o irmão de `montar()` para quem precisa do payload em forma serializável
    em vez de em protobuf — a rota HTTP e a tela, que não podem importar o SDK.

    A mesma disciplina de opções vale aqui: opção pedida em canal que não a tem
    é RECUSADA, não ignorada. Ignorar faria o operador marcar uma caixa que não
    faz nada, e ver um plano que não corresponde ao que ele pediu.
    """
    p = exigir_planejador(canal)
    pedidas = {k for k, v in opcoes.items() if v}
    faltantes = sorted(pedidas - set(p.opcoes))
    if faltantes:
        raise OpcaoIndisponivel(
            f"{p.rotulo} não tem a opção {', '.join(faltantes)}. "
            f"Opções deste canal: {', '.join(sorted(p.opcoes)) or '(nenhuma)'}. "
            f"Desmarque no pedido ou escolha um canal que a tenha."
        )
    aceitas = {k: v for k, v in opcoes.items() if k in p.opcoes}
    return p.planejador(cid, brief, login_customer_id=login_customer_id,
                        **aceitas)
