"""Os quatro canais, os quatro portões, e o motivo de cada recusa.

## O problema que este módulo resolve

O sistema conhece quatro canais do Google e três registros que falam sobre
eles — o manifesto (`plataforma.py`), as capacidades de quem pediu
(`capacidades.py`) e a janela do canário (`canario.py`). Nenhum deles responde
sozinho a pergunta que a tela faz, que é uma só e tem quatro respostas:

    o que EU posso fazer com ESTE canal, AGORA, e por que não posso o resto?

Sem um lugar que junte os três, a tela junta — e juntar autorização no
navegador é a falha que este módulo existe para impedir. Um `if capacidades
.google_mutate && manifesto.sabe_criar` escrito em TypeScript é uma decisão de
autorização tomada onde ninguém a cobra: o servidor continua recusando no
clique, mas só depois de o operador montar o pedido inteiro; e se a regra
mudar num lado e não no outro, a tela promete o que a rota nega.

Aqui o servidor decide. A resposta carrega o veredito **e** a frase que o
explica, e a tela não tem o que recalcular.

## Os quatro portões, e por que não são um booleano

"Pronto" sem sujeito não quer dizer nada — é a mesma lição que
`prontidao.py` aprendeu para o lançamento Search, e ela vale por canal:

    PLANEJÁVEL       existe o que montar? há campos de pedido, há construtor?
    VALIDÁVEL        dá para mandar o Google CONFERIR o pedido sem criar nada?
    CRIÁVEL PAUSADA  dá para criar de verdade, sempre PAUSADA?
    ATIVÁVEL         dá para despausar?

Eles são degraus, mas **não são o mesmo degrau visto de longe**. Display tem
construtor e passa por VALIDÁVEL; ele é recusado em CRIÁVEL PAUSADA pela
janela do canário, que só admite Search — e essa recusa não tem nada a ver com
o construtor. Colapsar os quatro num `pode: boolean` apagaria exatamente a
informação que o operador precisa para saber a quem pedir o quê.

⚠️ **ATIVÁVEL nunca é `PERMITIDO` hoje**, e isso não é um `if` esquecido: não
existe rota de ativação neste sistema, a política do canário declara
`inclui_ativacao=False`, e a elegibilidade de Smart Bidding é `False` por
construção enquanto medição e observação não forem provadas. As três razões
são diferentes e as três aparecem nomeadas.

## Os quatro estados, e por que nenhum deles é zero

    PERMITIDO       medido, e a resposta é sim
    BLOQUEADO       medido, e a resposta é não — com causa nomeada
    INDETERMINADO   NÃO medido. Não é "não", é "ninguém olhou"
    NAO_APLICAVEL   a pergunta não cabe neste canal

`INDETERMINADO` é o padrão deliberado de tudo que depende de leitura viva.
Uma rota de cockpit que chamasse o Google Ads a cada carregamento gastaria
quota da conta para desenhar uma tela; a leitura viva mora em `POST /provar`,
e o que chega aqui sem ter sido observado sai dizendo que não foi observado.

Colapsar `INDETERMINADO` em `BLOQUEADO` seria mentir para o lado seguro, e
mentir para o lado seguro ensina o operador a ignorar o aviso. Colapsar em
`PERMITIDO` seria a mentira cara.

## O que este módulo NÃO faz

Não recusa nada. `exigir_admin` na rota, `modo.exigir_leitura_apenas` na saída
da requisição, `canario.elegivel` no pedido e `perfil.exigir` no engine
continuam sendo quem decide — e continuam valendo mesmo que esta projeção
minta. Aqui só se PROJETA, para a tela, o que aquelas quatro já decidiram.

Também não chama o Google Ads. Nenhuma função deste arquivo abre cliente,
autentica ou emite GAQL. O que ele sabe sobre a conta chega injetado por quem
já leu — e o que não chegou sai `INDETERMINADO`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from app.trafego import canario as can
from app.trafego import capacidades as cap
from app.trafego import plataforma as plat
from app.trafego import prontidao as pr

# ═══════════════════════════════════════════════════════════════════════════
# VOCABULÁRIO
# ═══════════════════════════════════════════════════════════════════════════

#: Medido, e a resposta é sim.
PERMITIDO = "PERMITIDO"
#: Medido, e a resposta é não. Sempre acompanhado de ao menos um bloqueador.
BLOQUEADO = "BLOQUEADO"
#: NÃO medido. Diferente de `BLOQUEADO` porque leva a outra ação: `BLOQUEADO`
#: pede que alguém abra uma permissão ou conserte algo; `INDETERMINADO` pede
#: uma leitura que ninguém fez.
INDETERMINADO = "INDETERMINADO"
#: A pergunta não cabe. Reservado para o caso em que responder "não" seria tão
#: enganoso quanto responder "sim".
NAO_APLICAVEL = "NAO_APLICAVEL"

ESTADOS: Tuple[str, ...] = (PERMITIDO, BLOQUEADO, INDETERMINADO, NAO_APLICAVEL)

#: Os quatro portões, na ordem em que o operador os atravessa.
PLANEJAVEL = "planejavel"
VALIDAVEL = "validavel"
CRIAVEL_PAUSADA = "criavel_pausada"
ATIVAVEL = "ativavel"

PORTOES: Tuple[str, ...] = (PLANEJAVEL, VALIDAVEL, CRIAVEL_PAUSADA, ATIVAVEL)

# ── de onde vem uma recusa ──────────────────────────────────────────────────
#
# A origem existe porque ela decide A QUEM PEDIR. Um bloqueio de `operador` se
# resolve com quem administra o sistema; um de `construtor` se resolve com
# quem escreve o engine; um de `politica` é uma decisão do dono. Um botão
# cinza sem origem faz as três virarem a mesma frustração.

ORIGEM_CONSTRUTOR = "construtor"
ORIGEM_MANIFESTO = "manifesto"
ORIGEM_SERVIDOR = "servidor"
ORIGEM_OPERADOR = "operador"
ORIGEM_POLITICA = "politica"
ORIGEM_MENSURACAO = "mensuracao"
ORIGEM_OBSERVABILIDADE = "observabilidade"
ORIGEM_PRODUTO = "produto"

ORIGENS: Tuple[str, ...] = (
    ORIGEM_CONSTRUTOR, ORIGEM_MANIFESTO, ORIGEM_SERVIDOR, ORIGEM_OPERADOR,
    ORIGEM_POLITICA, ORIGEM_MENSURACAO, ORIGEM_OBSERVABILIDADE, ORIGEM_PRODUTO,
)

#: Os quatro canais do Google, na ordem em que a tela os mostra. Meta Ads não
#: entra: ele existe no manifesto para o eixo de navegação, e não tem portão de
#: criação nenhum para projetar — nem ler ele pode hoje.
CANAIS: Tuple[str, ...] = ("SEARCH", "DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX")


# ═══════════════════════════════════════════════════════════════════════════
# AS PEÇAS
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Bloqueador:
    """Uma razão nomeada para um portão estar fechado.

    ⚠️ `causa` é escrita para o OPERADOR. Ela não cita variável de ambiente,
    função nem caminho de arquivo — é a mesma correção que a rota `/trava` já
    levou: uma instrução que a pessoa não tem como executar faz ela concluir
    que o sistema está quebrado.

    `origem` é para a tela agrupar e para o operador saber a quem pedir.
    """

    codigo: str
    causa: str
    origem: str
    #: Quando o fato foi observado, para os bloqueios que vêm de uma leitura
    #: registrada e não de uma regra. `None` quando é regra — regra não tem
    #: data de observação, ela vale enquanto estiver escrita.
    observado_em: Optional[str] = None
    #: Como conferir de novo. `None` quando não há caminho de revalidação.
    revalidacao: Optional[str] = None

    def __post_init__(self) -> None:
        if not str(self.codigo or "").strip():
            raise ValueError("bloqueador sem código não é rastreável")
        if not str(self.causa or "").strip():
            raise ValueError(
                "bloqueador sem causa é botão cinza com outro nome: ele fecha "
                "a porta e não diz a quem pedir a chave")
        if self.origem not in ORIGENS:
            raise ValueError(
                f"origem {self.origem!r} não existe. As origens são: "
                f"{', '.join(ORIGENS)}.")

    def json(self) -> Dict[str, Any]:
        return {
            "codigo": self.codigo,
            "causa": self.causa,
            "origem": self.origem,
            "observado_em": self.observado_em,
            "revalidacao": self.revalidacao,
        }


@dataclass(frozen=True)
class Portao:
    """Um dos quatro portões, com veredito e razões.

    A invariante que sustenta o contrato inteiro: **`BLOQUEADO` sem bloqueador
    é proibido**. Um portão fechado que não diz por quê devolve à tela
    exatamente o problema que este módulo existe para resolver.

    A recíproca também vale: `PERMITIDO` com bloqueador seria a tela mostrando
    permissão e impedimento ao mesmo tempo, e o operador não teria como saber
    qual dos dois é verdade.
    """

    nome: str
    estado: str
    bloqueadores: Tuple[Bloqueador, ...] = ()

    def __post_init__(self) -> None:
        if self.nome not in PORTOES:
            raise ValueError(
                f"portão {self.nome!r} não existe. Os portões são: "
                f"{', '.join(PORTOES)}.")
        if self.estado not in ESTADOS:
            raise ValueError(f"estado {self.estado!r} não existe.")
        if self.estado == BLOQUEADO and not self.bloqueadores:
            raise ValueError(
                f"{self.nome}: BLOQUEADO sem causa nomeada. Um portão fechado "
                "que não diz por quê faz o operador procurar contorno em vez "
                "de permissão.")
        if self.estado == PERMITIDO and self.bloqueadores:
            raise ValueError(
                f"{self.nome}: PERMITIDO com bloqueador. A tela mostraria "
                "permissão e impedimento ao mesmo tempo.")
        if self.estado == INDETERMINADO and not self.bloqueadores:
            raise ValueError(
                f"{self.nome}: INDETERMINADO sem dizer o que não foi lido. "
                "Ignorância anônima é indistinguível de silêncio.")

    @property
    def aberto(self) -> bool:
        """⚠️ Só `PERMITIDO` abre. `INDETERMINADO` não é permissão."""
        return self.estado == PERMITIDO

    def json(self) -> Dict[str, Any]:
        return {
            "nome": self.nome,
            "estado": self.estado,
            "aberto": self.aberto,
            "bloqueadores": [b.json() for b in self.bloqueadores],
        }


@dataclass(frozen=True)
class Assets:
    """Que recursos criativos este canal monta — e se sabemos disso.

    ⚠️ `estado=INDETERMINADO` e `recursos=()` são coisas diferentes de
    `estado=PERMITIDO` e `recursos=()`. A primeira é "não consegui perguntar ao
    engine"; a segunda seria "perguntei, e ele não monta nenhum". Hoje a
    segunda só acontece em Performance Max, que não tem construtor — e lá o
    estado é `NAO_APLICAVEL`, porque um canal sem construtor não tem contrato
    de assets a cumprir, e dizer `0 assets` sugeriria que ele monta zero de uma
    lista que existe.
    """

    estado: str
    #: Os tipos de recurso criativo declarados pelo engine para este canal.
    recursos: Tuple[str, ...] = ()
    #: De onde a lista veio, ou por que ela não veio.
    fonte: Optional[str] = None
    causa: Optional[str] = None

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS:
            raise ValueError(f"estado {self.estado!r} não existe.")
        if self.estado == INDETERMINADO and not self.causa:
            raise ValueError(
                "assets INDETERMINADO sem causa: a tela não teria como "
                "distinguir 'não perguntei' de 'não existe'")
        if self.estado == PERMITIDO and not self.recursos:
            raise ValueError(
                "assets PERMITIDO com lista vazia: leitura bem-sucedida que "
                "devolve nada é indistinguível de leitura que não aconteceu")

    def json(self) -> Dict[str, Any]:
        return {
            "estado": self.estado,
            "recursos": list(self.recursos),
            "quantidade": len(self.recursos) if self.estado == PERMITIDO else None,
            "fonte": self.fonte,
            "causa": self.causa,
        }


@dataclass(frozen=True)
class Mensuracao:
    """O que se sabe sobre a campanha deste canal poder APRENDER.

    Reaproveita, sem reescrever, o vocabulário de `prontidao.py` — os mesmos
    cinco estados, os mesmos nomes de campo. Duas verdades sobre a mesma
    pergunta seria o defeito, não a solução.

    ⚠️ Quando ninguém leu a conta, todos os campos saem `INDETERMINADO` e
    `lida` sai `False`. Nenhum ramo aqui liga `smart_bidding_eligible` por
    ausência de bloqueio conhecido: um sistema que conclui "elegível" porque
    não achou problema está afirmando algo sobre o mundo a partir do que ele
    não olhou.
    """

    #: Alguém leu a conta para responder isto? Quando `False`, os estados
    #: abaixo são o padrão de ignorância, e não um veredito.
    lida: bool
    conversion_goal_status: str = pr.INDETERMINADO
    conversion_signal_status: str = pr.INDETERMINADO
    signal_sources: Tuple[str, ...] = ()
    measurement_readiness: str = pr.INDETERMINADO
    data_manager_status: str = pr.INDETERMINADO
    observability_status: str = pr.INDETERMINADO
    smart_bidding_eligible: bool = False
    #: Como esta leitura foi obtida, ou por que ela não foi.
    fonte: Optional[str] = None
    notas: Mapping[str, Any] = field(default_factory=dict)
    #: O plano canônico de mensuração, quando alguém leu os três recursos que
    #: decidem a meta efetiva.
    #:
    #: ⚠️ `None` NÃO é "não há plano": é "ninguém leu". A tela precisa da
    #: diferença porque as duas pedem coisas opostas — uma pede que alguém
    #: configure a conta, a outra pede uma leitura. E é ele que carrega, com
    #: estrutura em vez de prosa, os quatro fatos que a tela tem de mostrar:
    #: meta efetiva, fonte do sinal, frescor da última conversão e bloqueadores.
    plano: Optional[Any] = None

    def __post_init__(self) -> None:
        for nome in ("conversion_goal_status", "conversion_signal_status",
                     "measurement_readiness", "data_manager_status",
                     "observability_status"):
            valor = getattr(self, nome)
            if valor not in pr.ESTADOS:
                raise ValueError(f"{nome}={valor!r} não é estado de prontidão")
        if self.smart_bidding_eligible and not self.lida:
            raise ValueError(
                "Smart Bidding elegível sem ninguém ter lido a conta: é "
                "exatamente a afirmação sobre o mundo a partir do que não se "
                "olhou que `prontidao.py` existe para impedir.")

    def json(self) -> Dict[str, Any]:
        return {
            "lida": self.lida,
            "conversion_goal_status": self.conversion_goal_status,
            "conversion_signal_status": self.conversion_signal_status,
            "signal_sources": list(self.signal_sources),
            "measurement_readiness": self.measurement_readiness,
            "data_manager_status": self.data_manager_status,
            "observability_status": self.observability_status,
            "smart_bidding_eligible": self.smart_bidding_eligible,
            "fonte": self.fonte,
            "notas": dict(self.notas),
            "plano": (None if self.plano is None
                      else self.plano.para_json()),
        }


@dataclass(frozen=True)
class ContagemDoEspelho:
    """Quantas campanhas de um canal a leitura de volta encontrou.

    ⚠️ Existe como tipo, e não como `int`, por causa de `truncada`. Um inteiro
    solto obrigaria quem chama a carregar a marca de truncamento por fora — e
    ela se perde exatamente no caminho em que importa, que é o da resposta HTTP.
    """

    total: int
    truncada: bool = False

    def __post_init__(self) -> None:
        if self.total < 0:
            raise ValueError("contagem negativa não é contagem")


@dataclass(frozen=True)
class Observabilidade:
    """Depois de criada, conseguimos reler a campanha deste canal?

    ⚠️ Separado de `Mensuracao` de propósito. Medir é sobre o que a campanha
    aprende; observar é sobre o que NÓS aprendemos sobre ela. Uma campanha
    pode ter sinal de conversão perfeito e ser invisível para o nosso espelho —
    é literalmente o caso do canário pausado, e colapsar os dois esconderia
    isso.
    """

    estado: str
    #: Quem lê este canal de volta, quando alguém lê.
    coletor: Optional[str] = None
    causa: Optional[str] = None
    #: Fatos contados, quando alguém contou. `None` ≠ `0`: `None` é "não
    #: contei", `0` é "contei e não há nenhuma".
    campanhas_no_espelho: Optional[int] = None
    #: ⚠️ A contagem bateu no teto da consulta, e o número é um PISO, não um
    #: total. Sem esta marca, `500` de um universo de 5.000 sairia com cara de
    #: total exato — um número preciso e falso, que é pior que nenhum número.
    contagem_truncada: bool = False

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS:
            raise ValueError(f"estado {self.estado!r} não existe.")
        if self.estado in (BLOQUEADO, INDETERMINADO) and not self.causa:
            raise ValueError("observabilidade fechada ou não lida sem causa")
        if self.contagem_truncada and self.campanhas_no_espelho is None:
            raise ValueError(
                "contagem marcada como truncada sem número: truncar o que não "
                "foi contado não quer dizer nada")

    def json(self) -> Dict[str, Any]:
        return {
            "estado": self.estado,
            "coletor": self.coletor,
            "causa": self.causa,
            "campanhas_no_espelho": self.campanhas_no_espelho,
            "contagem_truncada": self.contagem_truncada,
        }


@dataclass(frozen=True)
class ContratoDeCanal:
    """Tudo o que a tela precisa saber sobre um canal, decidido no servidor."""

    plataforma: str
    canal: str
    rotulo: str
    #: A projeção do manifesto — hierarquia, painéis, campos e indisponibilidades.
    manifesto: Mapping[str, Any]
    portoes: Tuple[Portao, ...]
    assets: Assets
    mensuracao: Mensuracao
    observabilidade: Observabilidade
    #: Fatos operacionais deste canal que não cabem nos portões. Hoje: o
    #: canário, em Search.
    operacional: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        vistos = tuple(p.nome for p in self.portoes)
        if vistos != PORTOES:
            raise ValueError(
                f"{self.canal}: os quatro portões precisam estar todos "
                f"presentes e na ordem {PORTOES}; vieram {vistos}.")

    @property
    def por_nome(self) -> Dict[str, Portao]:
        return {p.nome: p for p in self.portoes}

    def json(self) -> Dict[str, Any]:
        return {
            "plataforma": self.plataforma,
            "canal": self.canal,
            "rotulo": self.rotulo,
            "manifesto": dict(self.manifesto),
            "portoes": [p.json() for p in self.portoes],
            "assets": self.assets.json(),
            "mensuracao": self.mensuracao.json(),
            "observabilidade": self.observabilidade.json(),
            "operacional": dict(self.operacional),
        }


# ═══════════════════════════════════════════════════════════════════════════
# FATOS MEDIDOS QUE VIRAM BLOQUEIO
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ Cada constante abaixo é uma LEITURA REGISTRADA, com data, e não uma
# suposição. Elas carregam `observado_em` e `revalidacao` justamente porque
# podem envelhecer — e um bloqueio que envelhece em silêncio é pior que nenhum:
# ele fecha uma porta que já poderia estar aberta, com a autoridade de um fato.

#: Medido em 01/09/2026 na releitura da campanha 24195821946 (Portal Mundo
#: Mais). A campanha nasceu com `goal_config_level=CUSTOMER` — herda as metas
#: da conta — e o ÚNICO `campaign_conversion_goal` com `biddable=true` é
#: DOWNLOAD/APP, enquanto a conta declara oito ações primárias PURCHASE.
#:
#: Em MANUAL_CPC isso não afeta o lance. Sob qualquer Smart Bidding, a campanha
#: otimizaria para um objetivo que ninguém escolheu — e otimizar para o
#: objetivo errado é pior que otimizar para nada, porque parece funcionar.
BLOQUEIO_META_EFETIVA = Bloqueador(
    codigo="meta_efetiva_divergente",
    causa=(
        "a única meta de conversão que esta campanha pode otimizar é "
        "'download de aplicativo', e a conta declara oito ações de compra como "
        "primárias. Em lance manual isso não muda nada; em lance automático a "
        "campanha aprenderia a perseguir um objetivo que ninguém escolheu."),
    origem=ORIGEM_MENSURACAO,
    observado_em="2026-09-01",
    revalidacao=(
        "a leitura viva das metas acontece ao provar um pedido para esta conta"),
)

#: A leitura de metas que existe hoje é uma GAQL sobre `conversion_action`, e
#: ela NÃO é a meta efetiva: o efetivo exige `customer_conversion_goal`,
#: `campaign_conversion_goal` e `conversion_goal_campaign_config
#: .goal_config_level`, que decide se quem manda é a conta ou a campanha.
BLOQUEIO_META_NAO_EFETIVA = Bloqueador(
    codigo="meta_efetiva_nao_lida",
    causa=(
        "o sistema sabe quais ações de conversão a conta marcou como "
        "primárias, e ainda não sabe qual delas esta campanha efetivamente "
        "persegue. São perguntas diferentes, e a segunda é a que decide o "
        "lance automático."),
    origem=ORIGEM_MENSURACAO,
    observado_em="2026-09-01",
)

#: Medido em 01/09/2026: `trafego_campanha_espelho` tem zero linhas para a
#: campanha 24195821946. O coletor de entrega lê somente campanhas ENABLED, e
#: uma campanha PAUSED some da observabilidade contínua.
BLOQUEIO_ESPELHO_SO_ENABLED = Bloqueador(
    codigo="espelho_so_le_ativas",
    causa=(
        "a leitura contínua de entrega só enxerga campanhas ativas. Uma "
        "campanha pausada existe na conta e não aparece nesse espelho — o que "
        "não a torna invisível aqui: o registro de criação continua sendo a "
        "memória do que aconteceu."),
    origem=ORIGEM_OBSERVABILIDADE,
    observado_em="2026-09-01",
)

#: Regra de produto, não leitura: ativar campanha não é ato deste fluxo.
BLOQUEIO_ATIVACAO_FORA_DE_ESCOPO = Bloqueador(
    codigo="ativacao_fora_de_escopo",
    causa=(
        "despausar campanha não é uma ação que este sistema executa. A janela "
        "autorizada cria sempre pausada, e ligar uma campanha continua sendo "
        "um ato feito por uma pessoa, no painel do Google, com consciência do "
        "gasto que começa ali."),
    origem=ORIGEM_PRODUTO,
)


# ═══════════════════════════════════════════════════════════════════════════
# ASSETS
# ═══════════════════════════════════════════════════════════════════════════


#: O módulo do engine que planeja cada canal. Os nomes vêm do contrato dos
#: canais (`CONTRATO-CANAIS-PARA-API.md` §2), e não de uma convenção que eu
#: adivinhei — `PERFORMANCE_MAX` mora em `pmax.py`, e derivar o nome do canal
#: acharia `performance_max.py`, que não existe.
_MODULO_DO_CANAL: Dict[str, str] = {
    "SEARCH": "search",
    "DISPLAY": "display",
    "DEMAND_GEN": "demand_gen",
    "PERFORMANCE_MAX": "pmax",
}


def planeja_offline(canal: str) -> Optional[bool]:
    """Este canal sabe montar um plano SEM falar com o Google?

    ⚠️ Pergunta diferente de "sabe provar" e de "sabe criar". Performance Max
    planeja offline e o módulo possui validador direto, mas a porta HTTP
    genérica continua fechada.

    `None` quando o engine não pôde ser consultado. Ele NÃO vira `False`:
    "não consegui perguntar" e "não planeja" levam a ações opostas.
    """
    alvo = str(canal or "").strip().upper()
    modulo = _MODULO_DO_CANAL.get(alvo)
    if modulo is None:
        return False
    try:
        import importlib
        import pathlib as _pathlib
        import sys

        raiz = _pathlib.Path(__file__).resolve().parents[3]
        if str(raiz) not in sys.path:
            sys.path.insert(0, str(raiz))
        mod = importlib.import_module(f"volc_ads.campanha.{modulo}")
    except Exception:  # noqa: BLE001 — SDK ou pacote ausente é ignorância
        return None
    return callable(getattr(mod, "planejar", None))


#: A decisão registrada em `DECISAO-PMAX-FORA-DO-EXECUTOR.md` (01/09/2026).
#:
#: ⚠️ Código PRÓPRIO, e não `CANAL_SEM_BUILDER`, porque as duas leituras são
#: OPOSTAS para quem opera: "o canal não existe aqui" convida a desistir; "o
#: canal planeja e a porta ainda não abriu" convida a pedir a porta. O código é
#: o mesmo que `volc_ads.campanha.plano.PMAX_FORA_DO_EXECUTOR` declara, para o
#: 422 da rota e este contrato dizerem a mesma coisa com a mesma palavra.
CODIGO_PMAX_FORA_DO_EXECUTOR = "PMAX_FORA_DO_EXECUTOR"

_CAUSA_PMAX_FORA_DO_EXECUTOR = (
    "Performance Max monta o plano inteiro aqui, sem falar com o Google — e "
    "não está habilitado nesta versão para ser conferido nem criado. Isso não "
    "é falha, não é ausência e não é zero: é uma decisão registrada, e ela "
    "existe porque habilitar o canal no executor derrubaria a criação dos "
    "outros três.")


def bloqueio_pmax_fora_do_executor() -> Bloqueador:
    return Bloqueador(
        codigo=CODIGO_PMAX_FORA_DO_EXECUTOR,
        causa=_CAUSA_PMAX_FORA_DO_EXECUTOR,
        origem=ORIGEM_PRODUTO,
        observado_em="2026-09-01",
    )


def assets_do_canal(canal: str) -> Assets:
    """Que recursos criativos o ENGINE declara para este canal.

    ⚠️ Importação preguiçosa e dentro da função, como `capacidades.py` já faz
    com o SDK de Demand Gen. O motivo é o mesmo: `volc_ads` mora fora do
    pacote do backend e pode não estar no caminho de importação de um processo
    que só serve a API. Deixar a exceção subir derrubaria a rota inteira por
    causa de uma lista de assets; devolver `()` calado afirmaria que o canal
    não monta nenhum. As duas saídas são piores que dizer que não se sabe.
    """
    alvo = str(canal or "").strip().upper()
    if alvo == "PERFORMANCE_MAX":
        # ⚠️ ESTE RAMO DIZIA "não tem construtor", E ISSO DEIXOU DE SER VERDADE.
        #
        # `pmax.planejar()` existe, monta o grafo e serializa protos v25. Os
        # papéis de asset dele são o CONTRATO do canal — em PMax o papel é o
        # `AssetFieldType` —, e continuar respondendo `NAO_APLICAVEL` esconderia
        # a exigência mais dura do canal atrás de uma frase sobre ausência.
        #
        # A lista vem do contrato de papéis do próprio builder, a fonte mais
        # estrita para AssetGroupAsset.
        return _assets_de_pmax()
    try:
        import sys
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        if str(raiz) not in sys.path:
            sys.path.insert(0, str(raiz))
        from volc_ads.campanha import perfil as engine_perfil

        p = engine_perfil.PERFIS.get(engine_perfil.canonizar(alvo))
    except Exception as exc:  # noqa: BLE001 — ausência do engine é estado
        return Assets(
            estado=INDETERMINADO,
            causa=("não foi possível consultar o construtor de campanhas para "
                   f"saber quais recursos criativos este canal monta ({type(exc).__name__})."),
        )
    if p is None:
        return Assets(
            estado=INDETERMINADO,
            causa=("o construtor de campanhas não reconhece este canal, e a "
                   "lista de recursos criativos dele não pôde ser lida."),
        )
    recursos = tuple(getattr(p, "recursos_criativos", ()) or ())
    if not recursos:
        return Assets(
            estado=NAO_APLICAVEL,
            fonte="volc_ads/campanha/perfil.py",
            causa="este canal não declara recursos criativos próprios.",
        )
    return Assets(estado=PERMITIDO, recursos=recursos,
                  fonte="volc_ads/campanha/perfil.py")


def _assets_de_pmax() -> Assets:
    """Os papéis de asset de Performance Max, lidos de onde eles são o contrato.

    ⚠️ `perfil.PERFORMANCE_MAX.recursos_criativos` é `()` e está DESATUALIZADO
    em relação a `pmax.py` — o registro não acompanhou o construtor. Ler dele
    devolveria "este canal não declara recursos criativos próprios", que é
    falso, e falso com a autoridade de um registro.
    """
    if planeja_offline("PERFORMANCE_MAX") is False:
        return Assets(
            estado=NAO_APLICAVEL,
            fonte="app/trafego/plataforma.py",
            causa=("Performance Max não monta plano neste servidor, então não "
                   "há pedido para carregar assets."),
        )
    try:
        import pathlib as _pathlib
        import sys

        raiz = _pathlib.Path(__file__).resolve().parents[3]
        if str(raiz) not in sys.path:
            sys.path.insert(0, str(raiz))
        from volc_ads.campanha.brief import PAPEIS_DE_ASSET_PMAX
    except Exception as exc:  # noqa: BLE001
        return Assets(
            estado=INDETERMINADO,
            causa=("não foi possível ler os papéis de asset de Performance Max "
                   f"({type(exc).__name__})."),
        )
    recursos = tuple(papel for papel, _campo in PAPEIS_DE_ASSET_PMAX)
    if not recursos:
        return Assets(
            estado=INDETERMINADO,
            causa="a lista de papéis de asset de Performance Max veio vazia.",
        )
    return Assets(estado=PERMITIDO, recursos=recursos,
                  fonte="volc_ads/campanha/brief.py")


# ═══════════════════════════════════════════════════════════════════════════
# OS PORTÕES
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ As frases abaixo são ditas UMA VEZ, aqui, e nunca montadas por
# concatenação na tela. Texto de recusa remontado no navegador diverge do que o
# servidor decidiu no dia em que alguém mexe só num dos dois lados.

_SEM_PAPEL_PARA_LER = (
    "sua sessão não tem papel ativo agora, e sem papel não há leitura da conta "
    "para montar um pedido. O papel é concedido por quem administra o sistema.")
_SEM_ADMIN_PARA_PROVAR = (
    "mandar o Google conferir um pedido bate na conta do cliente e consome "
    "quota dela, então exige papel administrativo. A conferência não cria "
    "nada — mas ela também não é anônima.")
_SEM_PAPEL_PARA_PROVAR = (
    "sua sessão não tem papel ativo agora. Conferir um pedido contra a conta "
    "exige papel, e ele é concedido por quem administra o sistema.")
_DEMAND_GEN_DESLIGADO = (
    "a conferência de Demand Gen é uma porta experimental e nasce desligada "
    "neste servidor. Ela depende de uma versão específica do SDK do Google "
    "estar disponível aqui, e quem administra o sistema é que a liga.")
_PORTAO_ANTERIOR = (
    "a escada é montar → conferir → criar, e o degrau anterior está fechado. "
    "Criar sem conferir é pular exatamente a etapa que separa 'montei um "
    "pedido' de 'tenho o direito de gastar'.")


def _causa_do_canal(m: plat.ManifestoDeCanal, prefixo: str,
                    pistas: Sequence[str]) -> str:
    """A indisponibilidade do manifesto QUE FALA DESTE PORTÃO.

    ⚠️ A primeira versão devolvia `indisponibilidades[0]` sem olhar o conteúdo,
    e isso produziu uma frase errada com cara de certa: Demand Gen declara
    quatro indisponibilidades, a primeira fala da porta de PROVA e a segunda da
    de CRIAÇÃO. O portão "criável pausada" saía explicando que a conferência
    nasce desligada — que é verdade sobre outro portão, e responde a uma
    pergunta que ninguém fez.

    ⚠️ Recuo, e não silêncio, quando nenhuma pista casa. Um manifesto sem
    indisponibilidade declarada para um canal que não sabe fazer algo é um
    defeito do manifesto — mas ele não pode virar um portão fechado sem causa,
    que é a única coisa que este contrato proíbe de verdade.
    """
    for texto in m.indisponibilidades:
        baixo = texto.lower()
        if any(p.lower() in baixo for p in pistas):
            return texto
    return f"{prefixo} {m.rotulo}."


#: As pistas que reconhecem, no texto do manifesto, a frase que fala de cada
#: portão. Elas são do vocabulário do manifesto, não do meu: mudá-las sem
#: mudar o manifesto faz a busca voltar ao recuo, que é legível e genérico.
_PISTAS_MONTAGEM: Tuple[str, ...] = ("construtor", "não monta", "nao monta")
_PISTAS_PROVA: Tuple[str, ...] = ("construtor", "validate_only", "conferid",
                                  "prova")
_PISTAS_CRIACAO: Tuple[str, ...] = ("construtor", "criação real", "criar:",
                                    "subir")


def _portao_planejavel(m: plat.ManifestoDeCanal, c: cap.Capacidades,
                       planeja: Optional[bool]) -> Portao:
    """Existe o que montar, e esta pessoa pode montar?

    ⚠️ Este portão é sobre o PEDIDO, não sobre a campanha. Ele abre quando há
    campos para preencher e a pessoa pode ver a conta — nada aqui promete que o
    pedido vai ser aceito, provado ou criado. Confundir os dois foi o defeito
    que fez uma tela oferecer "criar campanha" por simetria visual: quatro
    canais na lista, quatro botões, e a ausência descoberta depois do trabalho.
    """
    # ⚠️ O PLANEJADOR DO ENGINE VEM PRIMEIRO, E O MANIFESTO É O RECUO.
    #
    # `plataforma.PERFORMANCE_MAX.campos_do_pedido` continua vazio porque a
    # fronteira HTTP ainda não carrega o brief tipado. `pmax.planejar()` existe
    # e monta o plano inteiro offline; perguntar ao engine preserva essa verdade
    # sem fazer a tela oferecer um formulário que ainda não consegue enviar.
    #
    # `planeja is None` — engine não consultável — cai no manifesto, que é a
    # única resposta disponível, e não em `False`.
    declara = bool(m.campos_do_pedido)
    bloqueios = []

    # ⚠️ OS DOIS REGISTROS PODEM DISCORDAR, E A DISCORDÂNCIA NÃO É UM "NÃO".
    #
    # Eu vi isto acontecer: numa execução, `demand_gen` importou no meio de uma
    # escrita e respondeu sem `planejar`. O portão fechou — anunciando ausência
    # de capacidade num canal que monta plano desde sempre. Um "não" derivado de
    # um registro que falhou é pior que um "não sei", porque parece medido.
    #
    # Discordância só é conclusiva numa direção: o manifesto NÃO declarar campos
    # e o engine planejar é o caso conhecido de Performance Max — o manifesto
    # envelheceu, e o engine é quem tem o construtor. O contrário — manifesto
    # declara, engine nega — não tem explicação boa, e vira ignorância declarada.
    #   engine   manifesto   resposta
    #   ------   ---------   --------
    #   sim      qualquer    monta          — o construtor existe, e ele manda
    #   não sei  declara     monta          — o manifesto é a única resposta que há
    #   não sei  cala        não sei        — ninguém pôde responder
    #   não      declara     não sei        — contradição, e "não" seria inventado
    #   não      cala        não monta      — os dois concordam
    if planeja is True:
        estado_do_plano: Optional[bool] = True
    elif planeja is None:
        estado_do_plano = True if declara else None
    else:
        estado_do_plano = None if declara else False

    if estado_do_plano is None:
        bloqueios.append(Bloqueador(
            codigo="montagem_indeterminada",
            causa=(
                "não deu para confirmar se este canal monta um pedido: o "
                "registro da tela e o construtor de campanhas responderam "
                "coisas diferentes, ou o construtor não pôde ser consultado. "
                "Isso não é o mesmo que o canal não montar."),
            origem=ORIGEM_CONSTRUTOR,
        ))
        return Portao(nome=PLANEJAVEL, estado=INDETERMINADO,
                      bloqueadores=tuple(bloqueios))

    if not estado_do_plano:
        bloqueios.append(Bloqueador(
            codigo="sem_campos_de_pedido",
            causa=_causa_do_canal(
                m, "não há pedido de campanha para montar em",
                _PISTAS_MONTAGEM),
            origem=ORIGEM_CONSTRUTOR,
        ))
    elif not c.google_read:
        bloqueios.append(Bloqueador(
            codigo="sem_leitura",
            causa=_SEM_PAPEL_PARA_LER,
            origem=ORIGEM_OPERADOR,
        ))
    return Portao(
        nome=PLANEJAVEL,
        estado=BLOQUEADO if bloqueios else PERMITIDO,
        bloqueadores=tuple(bloqueios),
    )


def _portao_validavel(m: plat.ManifestoDeCanal,
                      c: cap.Capacidades) -> Portao:
    """Dá para mandar o Google conferir o pedido sem criar nada?

    ⚠️ `validate_only` é leitura para todos os efeitos — a API confere o payload
    e o descarta —, e por isso este portão NÃO espera a trava de escrita. Tratá-
    lo como escrita faria a única etapa que separa "montei um pedido" de "tenho
    o direito de gastar" ficar do lado errado da porta, e o operador subiria sem
    provar por ser o caminho aberto.
    """
    bloqueios = []
    if not m.sabe_provar:
        # ⚠️ PMax não é recusado por AUSÊNCIA, e dizer que é seria a leitura
        # oposta da verdadeira. O manifesto ainda explica a recusa dele com
        # "não há construtor — o engine levanta exceção", frase que era certa
        # até `pmax.py` existir. Hoje o motivo é uma decisão registrada.
        if m.canal == "PERFORMANCE_MAX" and planeja_offline(m.canal) is not False:
            bloqueios.append(bloqueio_pmax_fora_do_executor())
        else:
            bloqueios.append(Bloqueador(
                codigo="sem_porta_de_prova",
                causa=_causa_do_canal(
                    m, "não há como conferir um pedido de campanha em",
                    _PISTAS_PROVA),
                origem=ORIGEM_CONSTRUTOR,
            ))
    else:
        if not c.google_validate_only:
            bloqueios.append(Bloqueador(
                codigo="sem_capacidade_de_prova",
                causa=(_SEM_PAPEL_PARA_PROVAR if not c.google_read
                       else _SEM_ADMIN_PARA_PROVAR),
                origem=ORIGEM_OPERADOR,
            ))
        # ⚠️ A porta experimental de Demand Gen NÃO é herdada da geral. Ela
        # depende de uma flag durável do servidor E de o SDK v25 existir e
        # serializar neste processo — e as duas são fatos do ambiente, não da
        # pessoa. Derivá-la de `google_validate_only` ofereceria à tela uma
        # prova que o executor recusa.
        if m.canal == "DEMAND_GEN" and not c.google_demand_gen_validate_only:
            bloqueios.append(Bloqueador(
                codigo="demand_gen_experimental_desligado",
                causa=_DEMAND_GEN_DESLIGADO,
                origem=ORIGEM_SERVIDOR,
            ))
    return Portao(
        nome=VALIDAVEL,
        estado=BLOQUEADO if bloqueios else PERMITIDO,
        bloqueadores=tuple(bloqueios),
    )


def _portao_criavel_pausada(m: plat.ManifestoDeCanal, c: cap.Capacidades,
                            politica: can.Politica,
                            validavel: Portao) -> Portao:
    """Dá para criar de verdade — e sempre PAUSADA?

    ⚠️ O nome do portão carrega a restrição de propósito. Não existe "criável"
    solto neste sistema: a janela autorizada cria pausada, e uma campanha
    pausada não entra em leilão, não gasta e não veicula. Chamar o portão de
    "criável" faria o operador ler permissão de gasto onde há permissão de
    existência.

    ⚠️ E `permite_mutacao_real` no manifesto NÃO é permissão. Display o declara
    `True` e continua recusado aqui, porque a janela do canário só admite
    Search. As duas coisas são independentes: uma diz que o construtor existe,
    a outra diz que o dono autorizou usá-lo. Colapsá-las abriria Display no dia
    em que a trava global abrisse — sem ninguém ter decidido isso.
    """
    bloqueios = []
    # ⚠️ DUAS AUSÊNCIAS DIFERENTES, e chamá-las pelo mesmo nome enganava.
    #
    # Performance Max não tem construtor: não existe código que monte a
    # campanha. Demand Gen TEM construtor — `demand_gen.construir` existe e é
    # exercitado pela prova — e mesmo assim não cria, porque o executor recusa
    # a mutação real do canal. Um único código `sem_construtor` para os dois
    # faria o operador concluir que Demand Gen ainda não foi escrito.
    if not m.sabe_provar:
        if m.canal == "PERFORMANCE_MAX" and planeja_offline(m.canal) is not False:
            bloqueios.append(bloqueio_pmax_fora_do_executor())
        else:
            bloqueios.append(Bloqueador(
                codigo="sem_construtor",
                causa=_causa_do_canal(m, "não há como criar campanha em",
                                      _PISTAS_CRIACAO),
                origem=ORIGEM_CONSTRUTOR,
            ))
    elif not m.permite_mutacao_real:
        bloqueios.append(Bloqueador(
            codigo="mutacao_real_recusada",
            causa=_causa_do_canal(m, "a criação real ainda não foi liberada em",
                                  _PISTAS_CRIACAO),
            origem=ORIGEM_MANIFESTO,
        ))
    else:
        if not validavel.aberto:
            bloqueios.append(Bloqueador(
                codigo="portao_anterior_fechado",
                causa=_PORTAO_ANTERIOR,
                origem=ORIGEM_CONSTRUTOR if any(
                    b.origem == ORIGEM_CONSTRUTOR
                    for b in validavel.bloqueadores) else ORIGEM_OPERADOR,
            ))
        if not c.google_mutate:
            bloqueios.append(Bloqueador(
                codigo="sem_capacidade_de_escrita",
                # A frase vem pronta de `capacidades.py`, que já a escreve para
                # o operador. Reescrevê-la aqui criaria duas versões da mesma
                # recusa, e elas divergiriam.
                causa=(c.porque_sem_mutacao or
                       "a permissão de escrever nas contas está fechada."),
                # Um admin sem escrita está preso pela trava do SERVIDOR; quem
                # não é admin está preso pelo próprio papel. A origem decide a
                # quem o operador vai pedir, e errá-la manda a pessoa para a
                # porta errada.
                origem=ORIGEM_SERVIDOR if c.is_admin else ORIGEM_OPERADOR,
            ))
        if m.canal != politica.canal:
            bloqueios.append(Bloqueador(
                codigo="fora_da_janela_do_canario",
                causa=(
                    f"a janela de criação autorizada hoje é somente "
                    f"{politica.canal.replace('_', ' ').title()}, na conta "
                    f"{can.CONTA_FORMATADA} ({politica.customer_label}), "
                    f"sempre pausada. {m.rotulo} tem construtor pronto e "
                    f"continua fora dessa janela — abri-la é uma decisão do "
                    f"dono, não uma consequência de o construtor existir."),
                origem=ORIGEM_POLITICA,
            ))
    return Portao(
        nome=CRIAVEL_PAUSADA,
        estado=BLOQUEADO if bloqueios else PERMITIDO,
        bloqueadores=tuple(bloqueios),
    )


def _portao_ativavel(politica: can.Politica, medicao: Mensuracao,
                     observacao: Observabilidade) -> Portao:
    """Dá para despausar? **Hoje, em nenhum canal — e por três razões.**

    ⚠️ `BLOQUEADO`, e não `NAO_APLICAVEL`. A pergunta cabe: a campanha existe,
    está pausada, e alguém pode querer ligá-la. A resposta é não, e as razões
    são independentes — fechar uma não abre o portão, e é por isso que as três
    aparecem nomeadas em vez de a primeira encerrar a lista.

    ⚠️ E `activation_blockers` vazio nunca significaria "pode ativar". Não
    existe, neste contrato, campo que autorize ativação: o portão é a resposta,
    e ele está fechado.
    """
    bloqueios = [BLOQUEIO_ATIVACAO_FORA_DE_ESCOPO]
    if not politica.inclui_ativacao:
        bloqueios.append(Bloqueador(
            codigo="politica_nao_inclui_ativacao",
            causa=(
                "a autorização em vigor cobre criar pausada e nada além. "
                "Ativar é outro ato, e ele não foi autorizado."),
            origem=ORIGEM_POLITICA,
        ))
    if not medicao.smart_bidding_eligible:
        if not medicao.lida:
            bloqueios.append(Bloqueador(
                codigo="mensuracao_nao_lida",
                causa=(
                    "ninguém leu a conta para saber se existe meta de "
                    "conversão e sinal chegando. Ativar sem essa leitura é "
                    "deixar a campanha aprender do que ninguém mediu."),
                origem=ORIGEM_MENSURACAO,
            ))
        else:
            bloqueios.append(Bloqueador(
                codigo="mensuracao_nao_provada",
                causa=(
                    "a medição não está provada: sem meta efetiva e sem uma "
                    "fonte de sinal comprovada, uma campanha em lance "
                    "automático gasta o orçamento inteiro aprendendo o que "
                    "ninguém mediu."),
                origem=ORIGEM_MENSURACAO,
            ))
    if observacao.estado != PERMITIDO:
        bloqueios.append(Bloqueador(
            codigo="observabilidade_nao_provada",
            causa=(observacao.causa or
                   "a releitura pós-criação não foi provada: sem ela, um "
                   "desvio de entrega ou de política não seria notado."),
            origem=ORIGEM_OBSERVABILIDADE,
        ))
    return Portao(nome=ATIVAVEL, estado=BLOQUEADO,
                  bloqueadores=tuple(bloqueios))


# ═══════════════════════════════════════════════════════════════════════════
# MENSURAÇÃO E OBSERVABILIDADE
# ═══════════════════════════════════════════════════════════════════════════


#: Por que a leitura viva não acontece aqui, dito uma vez. Público porque a
#: rota o repassa em `fontes`: a tela precisa poder EXPLICAR o `INDETERMINADO`,
#: e uma tela que só mostra o estado sem o motivo ensina a ignorá-lo.
SEM_LEITURA_VIVA = (
    "esta tela não consulta a conta do Google — ela gastaria quota do cliente "
    "a cada carregamento. A leitura de metas e sinal acontece quando um pedido "
    "é conferido.")


def mensuracao_do_canal(canal: str, *,
                        prontidao: Optional[pr.Prontidao] = None) -> Mensuracao:
    """O que se sabe sobre medição neste canal — e nada além.

    `prontidao=None` é o caso normal do cockpit: ninguém leu. Ele NÃO vira
    `NAO_PRONTO`; vira `INDETERMINADO` com a razão dita, porque as duas levam a
    ações opostas — `NAO_PRONTO` pede conserto, `INDETERMINADO` pede leitura.

    Quando uma `Prontidao` chega — ela é produzida por `POST /provar`, que de
    fato leu a conta —, os campos são COPIADOS, não recalculados. Recalcular
    aqui criaria uma segunda autoridade sobre a mesma pergunta.
    """
    alvo = str(canal or "").strip().upper()
    if prontidao is None:
        return Mensuracao(lida=False, fonte=SEM_LEITURA_VIVA,
                          notas={"canal": alvo})
    return Mensuracao(
        lida=True,
        conversion_goal_status=prontidao.conversion_goal_status,
        conversion_signal_status=prontidao.conversion_signal_status,
        signal_sources=tuple(prontidao.signal_sources),
        measurement_readiness=prontidao.measurement_readiness,
        data_manager_status=prontidao.data_manager_status,
        observability_status=prontidao.observability_status,
        smart_bidding_eligible=prontidao.smart_bidding_eligible,
        fonte="leitura da conta feita ao conferir um pedido",
        notas=dict(prontidao.notas),
        # ⚠️ COPIADO, como todo o resto. Recalcular o plano aqui criaria uma
        # segunda autoridade sobre a mesma pergunta — foi por isso que este
        # ramo inteiro copia em vez de derivar.
        plano=prontidao.plano_de_mensuracao,
    )


#: Quem lê a campanha de volta. É a varredura do Hub, e ela NÃO filtra por
#: status — campanha pausada e removida entram no espelho, porque presença é
#: estado do contrato e filtrá-la faria uma campanha que existe aparecer como
#: `nao_encontrada`.
COLETOR_DO_HUB = "varredura do Hub de Tráfego"

#: Quem lê a ESTRUTURA interna de uma campanha Performance Max de volta — grupos
#: de recursos, assets, sinais e desempenho por grupo. É outro coletor que o do
#: espelho, e ele grava no ledger de inteligência Google (v12_01 + v12_03).
COLETOR_PMAX = "releitura do ledger de inteligência Google Ads"

#: ⚠️ A ÚNICA linhagem que abre o portão de observabilidade de Performance Max.
#:
#: `volc_ads.inteligencia_google.pmax` calcula o mesmo veredito nos dois
#: caminhos — sobre o resultado da própria execução e sobre recibos relidos do
#: banco — e a etiqueta é o que os separa. Um veredito `execucao_local` descreve
#: o que o processo ACHA que gravou: quem afirma que persistiu é quem persistiu.
#: A linhagem autoatestável já derrubou uma entrega neste repositório, no plano
#: de mensuração, e é por isso que aqui ela não é aceita nem com `provada=True`.
#:
#: O valor é repetido, e não importado, para não arrastar `volc_ads` para dentro
#: do contrato de canais. `test_a_linhagem_exigida_e_a_do_dominio` amarra os dois
#: — a mesma técnica que já ata `CODIGO_PMAX_FORA_DO_EXECUTOR` ao engine.
LINHAGEM_RELEITURA_DO_LEDGER = "releitura_do_ledger"

_PMAX_SEM_RELEITURA = (
    "Performance Max é inventariado como qualquer campanha da conta, e a "
    "estrutura interna dele — grupos de recursos e seus assets — só é relida "
    "quando alguém fotografa a campanha e a fotografia volta do ledger. "
    "Ninguém releu esta campanha ainda, então o que a tela mostra deste canal é "
    "o nível da campanha, e só.")


def _observabilidade_de_pmax(
        prontidao_pmax: Optional[Mapping[str, Any]],
        campanhas_no_espelho: Optional[int],
        contagem_truncada: bool) -> Observabilidade:
    """O veredito de Performance Max, e as quatro maneiras de ele não abrir.

    ⚠️ Nenhum ramo aqui produz `BLOQUEADO`. Não conseguir reler não é "medi e a
    resposta é não" — é `INDETERMINADO`, e as duas pedem coisas opostas:
    `BLOQUEADO` pede conserto, `INDETERMINADO` pede leitura. Quem fecha o portão
    de criação é `_bloqueios_de_observabilidade_na_criacao`, que trata qualquer
    coisa diferente de `PERMITIDO` como razão para não criar.
    """
    def indeterminado(causa: str) -> Observabilidade:
        return Observabilidade(
            estado=INDETERMINADO, coletor=COLETOR_PMAX,
            campanhas_no_espelho=campanhas_no_espelho,
            contagem_truncada=contagem_truncada, causa=causa)

    if prontidao_pmax is None:
        return indeterminado(_PMAX_SEM_RELEITURA)
    if not isinstance(prontidao_pmax, Mapping):
        return indeterminado(
            "o veredito de observabilidade de Performance Max chegou num "
            "formato que esta tela não sabe ler; sem conseguir lê-lo, ela não "
            "tem como afirmar que a releitura aconteceu.")

    linhagem = str(prontidao_pmax.get("linhagem") or "").strip()
    if linhagem != LINHAGEM_RELEITURA_DO_LEDGER:
        # Inclui o caso `execucao_local`: a própria coleta dizendo que gravou.
        return indeterminado(
            f"o veredito disponível tem linhagem {linhagem or 'não declarada'!r}, "
            f"e não {LINHAGEM_RELEITURA_DO_LEDGER!r}. Um veredito autoatestado "
            f"pela execução descreve o que o processo acha que gravou, não o que "
            f"o ledger devolveu quando alguém perguntou de volta.")

    if prontidao_pmax.get("provada") is not True:
        faltando = [str(f) for f in (prontidao_pmax.get("faltando") or ())]
        motivos = [str(m) for m in (prontidao_pmax.get("motivos") or ())]
        detalhe = "; ".join(motivos[:7]) or ", ".join(faltando) or "sem detalhe"
        return indeterminado(
            f"a releitura do ledger não fechou a fotografia das sete famílias "
            f"de Performance Max: {detalhe}.")

    return Observabilidade(
        estado=PERMITIDO, coletor=COLETOR_PMAX,
        campanhas_no_espelho=campanhas_no_espelho,
        contagem_truncada=contagem_truncada)


def observabilidade_do_canal(
        canal: str, *,
        campanhas_no_espelho: Optional[int] = None,
        contagem_truncada: bool = False,
        prontidao_pmax: Optional[Mapping[str, Any]] = None) -> Observabilidade:
    """Conseguimos reler campanhas deste canal?

    ⚠️ `campanhas_no_espelho=0` NÃO vira `BLOQUEADO`. Zero campanhas de um canal
    no espelho é ambíguo por construção: pode ser uma conta que não tem nenhuma,
    ou uma leitura que nunca chegou lá. Daqui as duas são indistinguíveis, e
    escolher uma delas seria afirmar o que não se olhou. `None` — ninguém
    contou — e `0` — contei e não achei — continuam sendo estados diferentes na
    resposta.

    ⚠️ `prontidao_pmax` é o veredito serializado de
    `volc_ads.inteligencia_google.pmax.ProntidaoPMax`, e ele só vale para
    Performance Max. Ausente — o caso normal do cockpit, que não faz leitura
    viva — o canal continua `INDETERMINADO`, como sempre esteve.
    """
    alvo = str(canal or "").strip().upper()
    if alvo == "PERFORMANCE_MAX":
        return _observabilidade_de_pmax(
            prontidao_pmax, campanhas_no_espelho, contagem_truncada)
    if campanhas_no_espelho is None:
        return Observabilidade(
            estado=INDETERMINADO,
            coletor=COLETOR_DO_HUB,
            causa=("ninguém contou quantas campanhas deste canal foram lidas de "
                   "volta nesta sessão."),
        )
    if campanhas_no_espelho <= 0:
        return Observabilidade(
            estado=INDETERMINADO,
            coletor=COLETOR_DO_HUB,
            campanhas_no_espelho=campanhas_no_espelho,
            contagem_truncada=contagem_truncada,
            causa=("nenhuma campanha deste canal aparece na leitura de volta. "
                   "Isso pode significar que a conta não tem nenhuma, ou que a "
                   "leitura nunca alcançou este canal — daqui as duas são "
                   "indistinguíveis."),
        )
    return Observabilidade(
        estado=PERMITIDO,
        coletor=COLETOR_DO_HUB,
        campanhas_no_espelho=campanhas_no_espelho,
        contagem_truncada=contagem_truncada,
    )


# ═══════════════════════════════════════════════════════════════════════════
# O CANÁRIO, VISTO POR CADA SUPERFÍCIE
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ ESTE BLOCO EXISTE POR UM FATO DESCONFORTÁVEL, E ELE NÃO PODE SER ESCONDIDO.
#
# A campanha 24195821946 nasceu em 01/09/2026, PAUSED, com recibo fechado como
# sucesso. Ela existe na conta do Google e existe no registro de criação. Ela
# NÃO aparece na leitura contínua de entrega, porque essa leitura só enxerga
# campanhas ativas.
#
# Um cockpit que perguntasse "a campanha está no espelho?" e respondesse "não"
# concluiria que ela não existe. Um cockpit que perguntasse só ao registro de
# criação responderia "sim" e esconderia que a observabilidade contínua não a
# alcança. As duas respostas isoladas são falsas pela metade — por isso a
# resposta é POR SUPERFÍCIE, com o que cada uma sabe e o que cada uma não sabe.


#: A campanha que este bloco procura. Ela é o canário do ledger v10, e o número
#: está aqui porque a pergunta "o canário aparece?" é sobre ELA — não sobre uma
#: campanha genérica que o operador tenha que digitar.
CANARIO_CAMPANHA_ID = "24195821946"


# ── a leitura de campo do canário, em 01/09/2026 ────────────────────────────
#
# ⚠️ ESTE BLOCO É UMA LEITURA REGISTRADA, COM DATA — não uma suposição, e não
# um cache. Ele veio de um GAQL v25 contra a conta 5478096539 pelo MCC
# 6016739364, e viaja com `observado_em` para poder ser desconfiado.
#
# Ele existe porque a alternativa é pior: sem ele, o cockpit mostraria campos
# vazios para uma campanha que o sistema criou e leu de volta no mesmo dia — e
# um campo vazio ao lado de "criada com sucesso" é a tela contradizendo a si
# mesma.

#: ⚠️ `MANUAL_CPC` NÃO É AUSÊNCIA DE DADO. É uma escolha registrada, e é ela
#: que explica por que o bloqueio de Smart Bidding não afeta o lance hoje: a
#: campanha não usa lance automático. Mostrar este campo em branco faria o
#: operador procurar a estratégia que "faltou configurar".
CANARIO_ESTRATEGIA_DE_LANCE = "MANUAL_CPC"

#: O estado que o Google chama de primário, e as razões dele.
#:
#: ⚠️ RAZÕES, no plural, e o contrato carrega LISTA. São duas simultâneas, e
#: elas dizem coisas diferentes: uma é consequência do que nós fizemos (a
#: campanha nasce pausada, por desenho), a outra é o veredito que ainda não
#: chegou. Reduzir a uma só apagaria justamente a que ainda pode mudar.
CANARIO_PRIMARY_STATUS = "PAUSED"

#: ⚠️ `em_revisao` NÃO É VERDE E NÃO É VERMELHO.
#:
#: `MOST_ADS_UNDER_REVIEW` é o estado que o canário existe para colher: o
#: Google ainda não decidiu. Pintá-lo de verde afirmaria uma aprovação que não
#: houve; pintá-lo de vermelho afirmaria uma reprovação que também não houve. É
#: o terceiro estado, e ele precisa aparecer com esse nome.
CANARIO_RAZOES_DO_ESTADO: Tuple[Dict[str, str], ...] = (
    {
        "codigo": "CAMPAIGN_PAUSED",
        "natureza": "por_desenho",
        "texto": ("a campanha está pausada porque foi criada assim. A janela "
                  "autorizada cria pausada e nada além — pausada ela não entra "
                  "em leilão, não veicula e não gasta."),
    },
    {
        "codigo": "MOST_ADS_UNDER_REVIEW",
        "natureza": "em_revisao",
        "texto": ("a maior parte dos anúncios ainda está em revisão pelo "
                  "Google. Isto não é aprovação nem reprovação: é o veredito "
                  "que o canário existe para colher, e ele ainda não chegou."),
    },
)

#: A leitura acima foi feita neste dia. Ela envelhece, e a tela precisa poder
#: dizer isso em vez de apresentá-la como o estado de agora.
CANARIO_OBSERVADO_EM = "2026-09-01"

#: O bloqueio de ativação que sai da leitura de campo, e não de uma regra.
BLOQUEIO_ANUNCIOS_EM_REVISAO = Bloqueador(
    codigo="anuncios_em_revisao",
    causa=(
        "a maior parte dos anúncios desta campanha ainda está em revisão pelo "
        "Google. Ligar a campanha antes do veredito é começar a gastar sobre "
        "uma decisão que ainda pode ser 'reprovado'."),
    origem=ORIGEM_OBSERVABILIDADE,
    observado_em=CANARIO_OBSERVADO_EM,
    revalidacao="o veredito por anúncio é lido pela consulta de política",
)


def leitura_de_campo_do_canario() -> Dict[str, Any]:
    """O que a conta respondeu sobre a campanha 24195821946, com data."""
    return {
        "observado_em": CANARIO_OBSERVADO_EM,
        "estrategia_de_lance": {
            "valor": CANARIO_ESTRATEGIA_DE_LANCE,
            # ⚠️ `escolhido`, e não `ausente`: o campo tem valor, e o valor é
            # uma decisão. É por isso que o bloqueio de Smart Bidding existe e
            # não afeta o lance de hoje.
            "estado": "escolhido",
            "por_que_importa": (
                "lance manual não aprende com conversão, então a meta efetiva "
                "divergente não afeta o gasto hoje. Ela afetaria no dia em que "
                "alguém trocasse a estratégia."),
        },
        "primary_status": CANARIO_PRIMARY_STATUS,
        "primary_status_reasons": [dict(r) for r in CANARIO_RAZOES_DO_ESTADO],
    }



def _superficie(nome: str, *, visivel: Optional[bool], descricao: str,
                causa: Optional[str] = None,
                detalhe: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Uma superfície e o que ela sabe.

    ⚠️ `visivel=None` é leitura que não aconteceu, e é diferente de
    `visivel=False`. A primeira não autoriza conclusão nenhuma; a segunda é um
    fato sobre a superfície.
    """
    return {
        "nome": nome,
        "descricao": descricao,
        "visivel": visivel,
        "causa": causa,
        "detalhe": dict(detalhe) if detalhe else None,
    }


async def canario_operacional(supa: Any) -> Dict[str, Any]:
    """Onde o canário pausado aparece, e onde ele não aparece.

    Leitura pura, e somente de dados já persistidos: três `SELECT` no snapshot,
    zero chamada ao Google. Falha de leitura vira `visivel=None` com causa —
    nunca `False`, que afirmaria ausência onde houve silêncio.
    """
    superficies: list[Dict[str, Any]] = []
    identidade: Optional[Dict[str, Any]] = None
    recibo: Optional[Dict[str, Any]] = None

    disponivel = bool(getattr(supa, "enabled", False))
    if not disponivel:
        indisponivel = ("o registro operacional não está acessível neste "
                        "servidor, então nada pôde ser conferido.")
        for nome, desc in (
            ("registro_de_criacao",
             "o recibo da criação — a memória do que este sistema fez"),
            ("identidade_de_campanha",
             "a identidade interna que amarra a campanha ao VOLC O.S."),
            ("espelho_de_leitura",
             "a leitura de volta da conta, que alimenta o painel de entrega"),
        ):
            superficies.append(_superficie(nome, visivel=None, descricao=desc,
                                           causa=indisponivel))
        return {
            "campaign_id": CANARIO_CAMPANHA_ID,
            "conta": can.CONTA_FORMATADA,
            "conta_label": can.NOME_DA_CONTA,
            "canal": can.CANAL,
            "estado_declarado": "PAUSED",
            # ⚠️ A leitura de campo continua valendo mesmo com o registro
            # operacional fora do ar: ela é sobre a CONTA, e não sobre o nosso
            # banco. Omiti-la aqui esconderia o que se sabe por causa do que
            # não se conseguiu conferir.
            "leitura_de_campo": leitura_de_campo_do_canario(),
            "superficies": superficies,
            "resumo": indisponivel,
        }

    # ── 1. o registro de criação ────────────────────────────────────────────
    try:
        recibos = await supa.select("trafego_recibo", {
            "select": ("recibo_id,desfecho,respondido_em,resposta_id_externo,"
                       "operacoes_consumidas,tentativa"),
            "resposta_id_externo": f"eq.{CANARIO_CAMPANHA_ID}",
            "desfecho": "eq.sucesso",
            "limit": 1,
        })
        recibo = recibos[0] if recibos else None
        superficies.append(_superficie(
            "registro_de_criacao",
            descricao="o recibo da criação — a memória do que este sistema fez",
            visivel=bool(recibo),
            causa=(None if recibo else
                   "não há recibo de criação bem-sucedida para esta campanha "
                   "neste servidor."),
            detalhe=recibo,
        ))
    except Exception as exc:  # noqa: BLE001 — falha de leitura não é ausência
        superficies.append(_superficie(
            "registro_de_criacao",
            descricao="o recibo da criação — a memória do que este sistema fez",
            visivel=None,
            causa=f"a leitura do registro de criação falhou ({type(exc).__name__}).",
        ))

    # ── 2. a identidade interna ─────────────────────────────────────────────
    try:
        ids = await supa.select("trafego_campanha", {
            "select": "volc_campaign_id,customer_id,campaign_id,procedencia,criada_em",
            "campaign_id": f"eq.{CANARIO_CAMPANHA_ID}",
            "customer_id": f"eq.{can.CONTA}",
            "limit": 1,
        })
        identidade = ids[0] if ids else None
        superficies.append(_superficie(
            "identidade_de_campanha",
            descricao="a identidade interna que amarra a campanha ao VOLC O.S.",
            visivel=bool(identidade),
            causa=(None if identidade else
                   "esta campanha não tem identidade declarada no registro."),
            detalhe=identidade,
        ))
    except Exception as exc:  # noqa: BLE001
        superficies.append(_superficie(
            "identidade_de_campanha",
            descricao="a identidade interna que amarra a campanha ao VOLC O.S.",
            visivel=None,
            causa=f"a leitura da identidade falhou ({type(exc).__name__}).",
        ))

    # ── 3. o espelho de leitura ─────────────────────────────────────────────
    #
    # ⚠️ Sem identidade não dá para perguntar ao espelho: a chave dele é a
    # identidade interna, não o id do Google. Isso NÃO vira "não está no
    # espelho" — vira "não deu para perguntar", que é outra coisa.
    if identidade is None:
        superficies.append(_superficie(
            "espelho_de_leitura",
            descricao="a leitura de volta da conta, que alimenta o painel de entrega",
            visivel=None,
            causa=("sem identidade declarada não há como perguntar ao espelho: "
                   "ele é indexado pela identidade interna, e não pelo número "
                   "da campanha no Google."),
        ))
    else:
        try:
            espelho = await supa.select("trafego_campanha_espelho", {
                "select": "volc_campaign_id,lido_em,presenca,estado_externo,nome",
                "volc_campaign_id": f"eq.{identidade.get('volc_campaign_id')}",
                "limit": 1,
            })
            linha = espelho[0] if espelho else None
            superficies.append(_superficie(
                "espelho_de_leitura",
                descricao="a leitura de volta da conta, que alimenta o painel de entrega",
                visivel=bool(linha),
                causa=(None if linha else BLOQUEIO_ESPELHO_SO_ENABLED.causa),
                detalhe=linha,
            ))
        except Exception as exc:  # noqa: BLE001
            superficies.append(_superficie(
                "espelho_de_leitura",
                descricao="a leitura de volta da conta, que alimenta o painel de entrega",
                visivel=None,
                causa=f"a leitura do espelho falhou ({type(exc).__name__}).",
            ))

    vistas = [s for s in superficies if s["visivel"] is True]
    ausentes = [s for s in superficies if s["visivel"] is False]
    nao_lidas = [s for s in superficies if s["visivel"] is None]
    if vistas and not ausentes and not nao_lidas:
        resumo = ("o canário pausado aparece em todas as superfícies "
                  "operacionais conferidas.")
    elif vistas:
        resumo = (
            f"o canário pausado aparece em {len(vistas)} de "
            f"{len(superficies)} superfícies operacionais. "
            + ("Onde ele não aparece, a razão está dita ao lado. "
               if ausentes else "")
            + ("Onde a leitura não aconteceu, a resposta é 'não sei' — não "
               "'não existe'." if nao_lidas else "")).strip()
    else:
        resumo = ("o canário pausado não foi encontrado em nenhuma superfície "
                  "operacional conferida — e onde a leitura não aconteceu, "
                  "isso não é o mesmo que ausência.")

    return {
        "campaign_id": CANARIO_CAMPANHA_ID,
        "conta": can.CONTA_FORMATADA,
        "conta_label": can.NOME_DA_CONTA,
        "canal": can.CANAL,
        "estado_declarado": "PAUSED",
        "leitura_de_campo": leitura_de_campo_do_canario(),
        "superficies": superficies,
        "resumo": resumo,
    }


# ═══════════════════════════════════════════════════════════════════════════
# A COMPOSIÇÃO
# ═══════════════════════════════════════════════════════════════════════════


def _com_extras(portao: Portao,
                extras: Sequence[Bloqueador]) -> Portao:
    """Acrescenta bloqueadores a um portão, respeitando a invariante.

    ⚠️ Um extra NUNCA reabre um portão, e SEMPRE fecha um aberto: se há uma
    razão nomeada para não passar, o portão não está aberto — foi essa a
    definição desde o começo. Um extra que chegasse sem mudar o estado seria um
    aviso disfarçado de bloqueio, e a tela mostraria permissão com uma razão de
    recusa ao lado.
    """
    if not extras:
        return portao
    return Portao(
        nome=portao.nome,
        estado=BLOQUEADO,
        bloqueadores=tuple(portao.bloqueadores) + tuple(extras),
    )


def _bloqueios_medidos(canal: str, medicao: Mensuracao) -> Tuple[Bloqueador, ...]:
    """Os bloqueios que vêm de uma leitura registrada, por canal.

    Hoje só Search tem leitura registrada: ele é o único canal em que uma
    campanha nasceu de verdade, e o que se sabe sobre metas veio da releitura
    dela. Emitir os mesmos bloqueios para Display seria transportar uma medição
    de uma campanha que existe para uma que não existe.
    """
    if str(canal or "").strip().upper() != can.CANAL:
        return ()
    # ⚠️ Quando alguém DE FATO leu a conta e a leitura disse que a meta efetiva
    # está resolvida, o bloqueio medido sai. Ele descreve um instante, não uma
    # lei — e mantê-lo depois de a leitura discordar seria justamente o
    # bloqueio que envelhece em silêncio.
    if medicao.lida and medicao.conversion_goal_status == pr.PRONTO:
        # ⚠️ A revisão dos anúncios NÃO sai junto com a meta. São bloqueios
        # independentes, e fechar um não abre o portão — foi por isso que eles
        # nasceram nomeados em vez de a primeira razão encerrar a lista.
        return (BLOQUEIO_ANUNCIOS_EM_REVISAO,)
    if medicao.lida and medicao.conversion_goal_status == pr.PARCIAL:
        return (BLOQUEIO_META_EFETIVA, BLOQUEIO_META_NAO_EFETIVA,
                BLOQUEIO_ANUNCIOS_EM_REVISAO)
    return (BLOQUEIO_META_EFETIVA, BLOQUEIO_META_NAO_EFETIVA,
            BLOQUEIO_ANUNCIOS_EM_REVISAO)


#: O código do bloqueio de observabilidade de Performance Max na CRIAÇÃO.
#:
#: ⚠️ CÓDIGO PRÓPRIO, e não `PMAX_FORA_DO_EXECUTOR`. Os dois fecham o mesmo
#: portão hoje e por razões INDEPENDENTES, e é essa independência que precisa
#: sobreviver: `PMAX_FORA_DO_EXECUTOR` é uma decisão de produto, com dono e
#: data, que alguém pode reverter numa tarde; a observabilidade é um fato sobre
#: o que este sistema consegue RELER. No dia em que a decisão for revertida, o
#: primeiro bloqueio some — e se ele fosse o único, Performance Max passaria a
#: ser criável sem ninguém conseguir observar o que acontece com a campanha
#: depois. Duas razões, dois códigos, e fechar uma não abre o portão.
CODIGO_PMAX_SEM_OBSERVABILIDADE = "pmax_observabilidade_nao_provada"

_CAUSA_PMAX_SEM_OBSERVABILIDADE = (
    "criar uma campanha de Performance Max que este sistema não sabe reler "
    "seria criar algo que ninguém consegue acompanhar. O inventário enxerga a "
    "campanha; a estrutura interna dela — os grupos de recursos e os assets de "
    "cada um — não é lida por ninguém aqui, e é nela que Performance Max "
    "decide o que entrega. Enquanto isso não for provado, criar é assumir um "
    "gasto cego.")


def _bloqueios_de_observabilidade_na_criacao(
        canal: str, observacao: Observabilidade) -> Tuple[Bloqueador, ...]:
    """A observabilidade que a CRIAÇÃO exige, e que hoje só falta em PMax.

    ⚠️ A guarda de canal é obrigatória, e não defensiva. `_com_extras` FECHA
    qualquer portão que receba um extra: sem a guarda, este bloqueio derrubaria
    `criavel_pausada` de Search — que hoje é o único canal que o atravessa — e
    a janela do canário deixaria de existir na prática.

    ⚠️ E ele é anexado por FORA de `_portao_criavel_pausada`, de propósito.
    Dentro, ele viveria no mesmo `if/elif/else` que produz
    `PMAX_FORA_DO_EXECUTOR` e morreria junto com ele no dia em que o canal
    entrasse no executor — que é exatamente o dia em que este bloqueio passa a
    ser o único de pé.
    """
    if str(canal or "").strip().upper() != "PERFORMANCE_MAX":
        return ()
    if observacao.estado == PERMITIDO:
        # Observabilidade provada: este bloqueio some sozinho, e some por
        # medição — não por alguém ter apagado a linha.
        return ()
    return (Bloqueador(
        codigo=CODIGO_PMAX_SEM_OBSERVABILIDADE,
        causa=_CAUSA_PMAX_SEM_OBSERVABILIDADE,
        origem=ORIGEM_OBSERVABILIDADE,
        revalidacao=(observacao.causa or
                     "a releitura da estrutura de Performance Max ainda não "
                     "existe neste sistema."),
    ),)


def contrato(canal: str, *, capacidades: cap.Capacidades,
             politica: Optional[can.Politica] = None,
             prontidao: Optional[pr.Prontidao] = None,
             espelho: Optional[ContagemDoEspelho] = None,
             operacional: Optional[Mapping[str, Any]] = None,
             prontidao_pmax: Optional[Mapping[str, Any]] = None) -> ContratoDeCanal:
    """O contrato de UM canal, decidido no servidor.

    Todos os argumentos que descrevem o mundo — `prontidao`,
    `campanhas_no_espelho`, `operacional` — são opcionais e ausentes por padrão.
    Ausência produz `INDETERMINADO` com causa, nunca um veredito.
    """
    pol = politica or can.POLITICA
    m = plat.manifesto(plat.GOOGLE_ADS, canal)
    if m is None:
        raise ValueError(
            f"canal {canal!r} não existe no manifesto do Google Ads. Os canais "
            f"do contrato são: {', '.join(CANAIS)}.")

    medicao = mensuracao_do_canal(m.canal, prontidao=prontidao)
    observacao = observabilidade_do_canal(
        m.canal,
        campanhas_no_espelho=espelho.total if espelho else None,
        contagem_truncada=bool(espelho and espelho.truncada),
        prontidao_pmax=prontidao_pmax)

    planejavel = _portao_planejavel(m, capacidades, planeja_offline(m.canal))
    validavel = _portao_validavel(m, capacidades)
    criavel = _com_extras(
        _portao_criavel_pausada(m, capacidades, pol, validavel),
        _bloqueios_de_observabilidade_na_criacao(m.canal, observacao))
    ativavel = _com_extras(
        _portao_ativavel(pol, medicao, observacao),
        _bloqueios_medidos(m.canal, medicao))

    return ContratoDeCanal(
        plataforma=m.plataforma,
        canal=m.canal,
        rotulo=m.rotulo,
        manifesto=m.json(),
        portoes=(planejavel, validavel, criavel, ativavel),
        assets=assets_do_canal(m.canal),
        mensuracao=medicao,
        observabilidade=observacao,
        operacional=dict(operacional or {}),
    )


def contrato_dos_canais(
        *, capacidades: cap.Capacidades,
        politica: Optional[can.Politica] = None,
        prontidao_por_canal: Optional[Mapping[str, pr.Prontidao]] = None,
        espelho_por_canal: Optional[Mapping[str, ContagemDoEspelho]] = None,
        operacional_por_canal: Optional[Mapping[str, Mapping[str, Any]]] = None,
        prontidao_pmax: Optional[Mapping[str, Any]] = None,
) -> Tuple[ContratoDeCanal, ...]:
    """Os quatro canais, na ordem da tela.

    ⚠️ Os quatro SEMPRE saem, inclusive Performance Max, que não sabe criar
    nada. Esconder um canal sem construtor faria a tela mentir por omissão: a
    conta tem campanhas dele gastando dinheiro, e a ausência declarada — com o
    motivo — é conteúdo, não lacuna.
    """
    pron = dict(prontidao_por_canal or {})
    esp = dict(espelho_por_canal or {})
    oper = dict(operacional_por_canal or {})
    return tuple(
        contrato(c, capacidades=capacidades, politica=politica,
                 prontidao=pron.get(c), espelho=esp.get(c),
                 operacional=oper.get(c),
                 # Só Performance Max tem releitura de estrutura; passá-la aos
                 # quatro faria os outros herdarem um veredito de outro canal —
                 # e `observabilidade_do_canal` a ignora fora de PMax de
                 # qualquer forma, mas a intenção fica dita aqui.
                 prontidao_pmax=(prontidao_pmax if c == "PERFORMANCE_MAX" else None))
        for c in CANAIS
    )


# ═══════════════════════════════════════════════════════════════════════════
# LEITURA DO ESPELHO — read-only, e com teto declarado
# ═══════════════════════════════════════════════════════════════════════════

#: Teto por canal na contagem do espelho. Ele existe porque o PostgREST corta
#: toda resposta e uma contagem truncada em silêncio sairia com cara de total.
#: Ao bater no teto, a resposta marca `contagem_truncada` e o número passa a
#: significar "ao menos isto".
TETO_DE_CONTAGEM = 500


async def contar_espelho_por_canal(
        supa: Any,
        canais: Sequence[str] = CANAIS) -> Optional[Dict[str, ContagemDoEspelho]]:
    """Quantas campanhas de cada canal a leitura de volta encontrou.

    `None` — e não um dicionário de zeros — quando o registro operacional não
    está acessível. Zero por indisponibilidade é a mentira que este contrato
    inteiro existe para não contar: a tela mostraria "nenhuma campanha lida" e
    o operador concluiria que a varredura falhou, quando na verdade ninguém
    perguntou.

    Um canal cuja consulta falha simplesmente NÃO ENTRA no dicionário, e a
    ausência da chave produz `INDETERMINADO` lá na frente. Entrar com zero
    transformaria uma falha de rede num veredito sobre a conta.
    """
    if not bool(getattr(supa, "enabled", False)):
        return None
    saida: Dict[str, ContagemDoEspelho] = {}
    for canal in canais:
        try:
            linhas = await supa.select("trafego_campanha_espelho", {
                "select": "volc_campaign_id",
                "canal": f"eq.{canal}",
                "limit": TETO_DE_CONTAGEM,
            })
        except Exception:  # noqa: BLE001 — falha de leitura não vira contagem
            continue
        n = len(linhas or [])
        saida[canal] = ContagemDoEspelho(total=n, truncada=n >= TETO_DE_CONTAGEM)
    return saida or None
