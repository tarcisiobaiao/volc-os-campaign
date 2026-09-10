"""Registro tipado das receitas Meta que este servidor sabe emitir.

## Por que um registro, e não um `if` no compilador

Até aqui existia UMA receita, escrita à mão dentro de `PlanoMetaPausado`:
`OUTCOME_TRAFFIC` + `LANDING_PAGE_VIEWS` + `IMPRESSIONS` +
`LOWEST_COST_WITHOUT_CAP`, orçamento no conjunto, Facebook-only, um conjunto
só. Ela é correta e continua correta — mas ela estava CODIFICADA COMO
CONSTANTE, e por isso qualquer objetivo novo virava um `if` a mais espalhado
entre contrato, compilador e tela.

O preço disso não é estético. Um `if` espalhado permite a combinação
cartesiana: alguém liga `OUTCOME_SALES` no objetivo, o compilador continua
emitindo `LANDING_PAGE_VIEWS` na otimização, e o payload sai com um par que
ninguém adjudicou. `OBJECTIVE-MEASUREMENT-MATRIX.json` proíbe isso com todas
as letras:

    "Only listed complete and adjudicated recipes can compile; do not form
     Cartesian product of enums. null in recipe is unresolved, never provider
     omission permission."

Então a receita passa a ser um OBJETO, com identidade, e o compilador emite
somente o que o objeto declara. O que não está no registro não existe.

## De onde vêm estes valores

NENHUM enum aqui foi inventado. Cada receita é a transcrição de uma linha já
adjudicada em `docs/specs/meta-completion-v1/OBJECTIVE-MEASUREMENT-MATRIX.json`
(campo `recipe_id`), que por sua vez cita as fontes oficiais em `source_ids`.
Quando aquele documento diz `null`, aqui o campo fica `None` e a receita é
declarada não emissível — `null` é "ninguém resolveu", nunca "o provedor
aceita omitir".

## O que "não provado" fecha, e o que ele NÃO fecha

O catálogo distingue prova histórica de capacidade implementada. Uma receita
FIELD_SHAPE_ONLY pode percorrer compilar → validar → aprovação real do plano
exato → criação PAUSED. A aceitação prévia cobre apenas raízes independentes;
o executor valida cada passo dependente resolvido antes de criá-lo. Isso não
promove a receita inteira nem sua elegibilidade para outra conta.

Os portões de processo, política, autorização e destino Shop permanecem
independentes. `capacidade_pausada` descreve o caminho disponível, nunca licença
para ignorar esses portões nem ativar uma campanha.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .contrato import ErroDeNascimentoMeta


#: Onde o orçamento é autoritativo. Nunca nos dois ao mesmo tempo — a matriz
#: lista "simultaneous authoritative Campaign and AdSet budgets" entre os
#: `incompatible_fields` de todas as receitas.
ORCAMENTO_NO_CONJUNTO = "ADSET"
ORCAMENTO_NA_CAMPANHA = "CAMPAIGN"
NIVEIS_DE_ORCAMENTO: frozenset[str] = frozenset({
    ORCAMENTO_NO_CONJUNTO, ORCAMENTO_NA_CAMPANHA})

#: Diário e total são EXCLUSIVOS entre si no mesmo objeto: a Graph aceita
#: `daily_budget` OU `lifetime_budget`, e mandar os dois é erro do provedor.
PERIODO_DIARIO = "DAILY"
PERIODO_TOTAL = "LIFETIME"
PERIODOS_DE_ORCAMENTO: frozenset[str] = frozenset({PERIODO_DIARIO, PERIODO_TOTAL})

#: Para que a conversão selecionada serve. São contratos DIFERENTES: relatar
#: não toca `promoted_object`, `objective` nem `bid_strategy`; otimizar muda o
#: payload e exige fonte elegível comprovada.
MENSURACAO_RELATORIO = "REPORT_ONLY"
MENSURACAO_OTIMIZACAO = "OPTIMIZE"
PROPOSITOS_DE_MENSURACAO: frozenset[str] = frozenset({
    MENSURACAO_RELATORIO, MENSURACAO_OTIMIZACAO})

#: O nível de prova de uma combinação. A distinção é o ponto inteiro do
#: registro: "o campo existe no SDK" e "esta conta aceitou este payload" são
#: afirmações diferentes, e só a segunda autoriza criar.
PROVA_REMOTA_ACEITA = "REMOTE_VALIDATE_ACCEPTED"
PROVA_FORMA_DE_CAMPO = "FIELD_SHAPE_ONLY"
PROVA_PESQUISA_PENDENTE = "RESEARCH_REQUIRED"
NIVEIS_DE_PROVA: frozenset[str] = frozenset({
    PROVA_REMOTA_ACEITA, PROVA_FORMA_DE_CAMPO, PROVA_PESQUISA_PENDENTE})


@dataclass(frozen=True)
class ModoDeOrcamento:
    """Uma combinação nível+período, com o próprio nível de prova.

    ⚠️ A prova é POR MODO, não por receita. A receita de tráfego foi aceita
    pela Meta em 05/09/2026 com orçamento DIÁRIO NO CONJUNTO; nada naquela
    resposta diz o que aconteceria com orçamento total na campanha. Guardar um
    único booleano na receita transformaria a prova de um modo em licença para
    os quatro.
    """

    nivel: str
    periodo: str
    prova: str
    fonte: str
    #: Estratégia de lance obrigatória no objeto que carrega o orçamento.
    #: Em CBO ela sobe para a Campaign junto com a verba — foi exatamente esta
    #: a exigência que a Meta declarou no código 100/4005 de 05/09/2026, e a
    #: receita de conjunto único a recusou por não poder atendê-la sem mudar de
    #: receita. Aqui ela é atendida, porque a receita É outra.
    lance_acompanha_orcamento: bool = True

    @property
    def id(self) -> str:
        return f"{self.nivel}_{self.periodo}"

    @property
    def emissivel_para_criar(self) -> bool:
        return self.prova == PROVA_REMOTA_ACEITA

    def __post_init__(self) -> None:
        if self.nivel not in NIVEIS_DE_ORCAMENTO:
            raise ValueError(f"nivel de orcamento invalido: {self.nivel}")
        if self.periodo not in PERIODOS_DE_ORCAMENTO:
            raise ValueError(f"periodo de orcamento invalido: {self.periodo}")
        if self.prova not in NIVEIS_DE_PROVA:
            raise ValueError(f"nivel de prova invalido: {self.prova}")


@dataclass(frozen=True)
class Receita:
    """Uma combinação COMPLETA e adjudicada, do objetivo ao objeto promovido."""

    id: str
    #: A linha de `OBJECTIVE-MEASUREMENT-MATRIX.json` que esta receita
    #: transcreve. Sem ela ninguém consegue auditar de onde o enum saiu.
    recipe_id_adjudicado: str
    rotulo: str
    descricao: str
    objective: str
    optimization_goal: str
    billing_event: str
    bid_strategy: str
    #: Modos de orçamento aceitos, em ordem estável de apresentação.
    modos_de_orcamento: tuple[ModoDeOrcamento, ...]
    #: `True` quando a receita EXIGE `promoted_object` no conjunto. Traffic/LPV
    #: não exige, e injetar um só para satisfazer um seletor de tela é
    #: explicitamente proibido pelo contrato desta missão.
    exige_promoted_object: bool
    #: Propósitos de mensuração que esta receita admite. Traffic/LPV admite
    #: relatório — o operador pode querer VER conversões — e NÃO admite
    #: otimização, porque otimizar mudaria o objetivo.
    propositos_de_mensuracao: frozenset[str]
    #: Tipos de fonte de evento aceitos quando `exige_promoted_object`.
    fontes_de_evento: frozenset[str]
    prova: str
    fonte: str
    #: Por que criar está fechado, em linguagem de operador. `None` quando a
    #: receita tem prova remota aceita.
    motivo_sem_prova: str | None = None

    @property
    def emissivel_para_criar(self) -> bool:
        return self.prova == PROVA_REMOTA_ACEITA

    def modo_de_orcamento(self, nivel: str, periodo: str) -> ModoDeOrcamento:
        for modo in self.modos_de_orcamento:
            if modo.nivel == nivel and modo.periodo == periodo:
                return modo
        raise ErroDeNascimentoMeta(
            "META_BUDGET_MODE_NOT_IN_RECIPE",
            f"a receita {self.id} nao registra orcamento {nivel}/{periodo}",
        )

    def exigir_proposito(self, proposito: str) -> None:
        if proposito not in PROPOSITOS_DE_MENSURACAO:
            raise ErroDeNascimentoMeta(
                "META_MEASUREMENT_PURPOSE_INVALID",
                "o proposito da mensuracao precisa ser REPORT_ONLY ou OPTIMIZE",
            )
        if proposito not in self.propositos_de_mensuracao:
            raise ErroDeNascimentoMeta(
                "META_MEASUREMENT_PURPOSE_NOT_IN_RECIPE",
                f"a receita {self.id} nao admite mensuracao com proposito {proposito}",
            )


#: ⚠️ Fonte de cada enum: `docs/specs/meta-completion-v1/OBJECTIVE-MEASUREMENT-MATRIX.json`.
#: Cada `recipe_id_adjudicado` abaixo existe LITERALMENTE naquele arquivo.

_ABO_DIARIO_PROVADO = ModoDeOrcamento(
    nivel=ORCAMENTO_NO_CONJUNTO,
    periodo=PERIODO_DIARIO,
    prova=PROVA_REMOTA_ACEITA,
    fonte=(
        "validate_only real de 05/09/2026 aceitou campaign+adset desta receita "
        "com daily_budget no conjunto"
    ),
)

_ABO_TOTAL_FORMA = ModoDeOrcamento(
    nivel=ORCAMENTO_NO_CONJUNTO,
    periodo=PERIODO_TOTAL,
    prova=PROVA_FORMA_DE_CAMPO,
    fonte=(
        "AdSet.Field.lifetime_budget existe no catálogo do SDK v26.0.0; nenhuma "
        "resposta desta conta provou a combinação com end_time"
    ),
)

_CBO_DIARIO_FORMA = ModoDeOrcamento(
    nivel=ORCAMENTO_NA_CAMPANHA,
    periodo=PERIODO_DIARIO,
    prova=PROVA_FORMA_DE_CAMPO,
    fonte=(
        "Campaign.Field.daily_budget e Campaign.Field.bid_strategy existem no "
        "catálogo do SDK v26.0.0; a combinação não foi validada nesta conta"
    ),
)

_CBO_TOTAL_FORMA = ModoDeOrcamento(
    nivel=ORCAMENTO_NA_CAMPANHA,
    periodo=PERIODO_TOTAL,
    prova=PROVA_FORMA_DE_CAMPO,
    fonte=(
        "Campaign.Field.lifetime_budget existe no catálogo do SDK v26.0.0; a "
        "combinação com end_time do conjunto não foi validada nesta conta"
    ),
)

_MODOS_PADRAO = (
    _ABO_DIARIO_PROVADO, _ABO_TOTAL_FORMA, _CBO_DIARIO_FORMA, _CBO_TOTAL_FORMA)

# Traffic's historical acceptance is not evidence about Sales/Leads. Each
# conversion budget combination remains field-shape evidence until its own
# exact plan is validated and its dependent steps are created/read back.
_MODOS_CONVERSAO = (
    ModoDeOrcamento(
        nivel=ORCAMENTO_NO_CONJUNTO, periodo=PERIODO_DIARIO,
        prova=PROVA_FORMA_DE_CAMPO,
        fonte="daily_budget existe no AdSet; a prova histórica de Traffic não prova esta receita de conversão",
    ),
    _ABO_TOTAL_FORMA, _CBO_DIARIO_FORMA, _CBO_TOTAL_FORMA,
)

#: Fontes de evento que o contrato aceita NOMEAR. Nenhuma delas cria coisa
#: alguma: são referências a objetos que já existem na conta.
FONTE_PIXEL = "EXISTING_PIXEL"
FONTE_CONVERSAO_PERSONALIZADA = "EXISTING_CUSTOM_CONVERSION"


TRAFFIC_WEBSITE_LPV_STATIC = Receita(
    id="TRAFFIC_WEBSITE_LPV_STATIC",
    recipe_id_adjudicado="RECIPE-P0-TRAFFIC-LPV",
    rotulo="Tráfego · visualizações da página de destino",
    descricao=(
        "Leva o clique para a landing page e otimiza por quem realmente carrega "
        "a página. Não usa pixel para otimizar."
    ),
    objective="OUTCOME_TRAFFIC",
    optimization_goal="LANDING_PAGE_VIEWS",
    billing_event="IMPRESSIONS",
    bid_strategy="LOWEST_COST_WITHOUT_CAP",
    modos_de_orcamento=_MODOS_PADRAO,
    exige_promoted_object=False,
    # ⚠️ Só relatório. Escolher uma conversão aqui é uma preferência de LEITURA;
    # ela não pode virar `promoted_object`, porque isso mudaria a otimização
    # que o operador aprovou. A matriz é explícita: "P0 does not require
    # conversion optimization".
    propositos_de_mensuracao=frozenset({MENSURACAO_RELATORIO}),
    fontes_de_evento=frozenset({FONTE_PIXEL, FONTE_CONVERSAO_PERSONALIZADA}),
    prova=PROVA_REMOTA_ACEITA,
    fonte=(
        "validate_only real de 05/09/2026 nesta lane; raízes campaign e "
        "adcreative aceitas pela Meta"
    ),
)

WEB_SALES_CONVERSION = Receita(
    id="WEB_SALES_CONVERSION",
    recipe_id_adjudicado="RECIPE-SALES-PURCHASE",
    rotulo="Vendas no site · conversão",
    descricao=(
        "Otimiza por uma conversão do seu site. Exige um pixel/dataset da conta "
        "e um evento elegível — a Meta precisa já ter visto esse evento."
    ),
    objective="OUTCOME_SALES",
    optimization_goal="OFFSITE_CONVERSIONS",
    billing_event="IMPRESSIONS",
    bid_strategy="LOWEST_COST_WITHOUT_CAP",
    modos_de_orcamento=_MODOS_CONVERSAO,
    exige_promoted_object=True,
    propositos_de_mensuracao=frozenset({MENSURACAO_RELATORIO, MENSURACAO_OTIMIZACAO}),
    fontes_de_evento=frozenset({FONTE_PIXEL, FONTE_CONVERSAO_PERSONALIZADA}),
    prova=PROVA_FORMA_DE_CAMPO,
    fonte=(
        "OBJECTIVE-MEASUREMENT-MATRIX RECIPE-SALES-PURCHASE: "
        "'Sales Website/OFFSITE listed; eligible Purchase source, domain and "
        "account need proof'"
    ),
    motivo_sem_prova=(
        "A Meta lista este objetivo com otimização por conversão, mas ninguém "
        "provou nesta conta que a fonte, o domínio e o evento escolhidos são "
        "elegíveis. Compilar e validar continuam liberados — é a validação que "
        "produz essa prova. Criar permanece fechado até ela existir."
    ),
)

WEB_LEADS_CONVERSION = Receita(
    id="WEB_LEADS_CONVERSION",
    recipe_id_adjudicado="RECIPE-LEADS-WEB",
    rotulo="Cadastros no site · conversão",
    descricao=(
        "Otimiza por um evento de cadastro do seu site. Exige pixel/dataset da "
        "conta e evento elegível; não usa formulário instantâneo."
    ),
    objective="OUTCOME_LEADS",
    optimization_goal="OFFSITE_CONVERSIONS",
    billing_event="IMPRESSIONS",
    bid_strategy="LOWEST_COST_WITHOUT_CAP",
    modos_de_orcamento=_MODOS_CONVERSAO,
    exige_promoted_object=True,
    propositos_de_mensuracao=frozenset({MENSURACAO_RELATORIO, MENSURACAO_OTIMIZACAO}),
    fontes_de_evento=frozenset({FONTE_PIXEL, FONTE_CONVERSAO_PERSONALIZADA}),
    prova=PROVA_FORMA_DE_CAMPO,
    fonte=(
        "OBJECTIVE-MEASUREMENT-MATRIX RECIPE-LEADS-WEB: "
        "'Leads Website/OFFSITE listed; scoped pixel event eligibility needs "
        "provider proof'"
    ),
    motivo_sem_prova=(
        "A Meta lista este objetivo com otimização por conversão, mas a "
        "elegibilidade do evento de cadastro desta conta não foi provada. "
        "Compilar e validar continuam liberados; criar permanece fechado."
    ),
)


REGISTRO: Mapping[str, Receita] = {
    receita.id: receita
    for receita in (
        TRAFFIC_WEBSITE_LPV_STATIC,
        WEB_SALES_CONVERSION,
        WEB_LEADS_CONVERSION,
    )
}

#: A receita que um pedido sem `recipe_id` assume. É a única com prova remota,
#: e essa coincidência é deliberada: o default nunca pode ser a combinação mais
#: ambiciosa.
RECEITA_PADRAO = TRAFFIC_WEBSITE_LPV_STATIC.id


def receita(identificador: str | None) -> Receita:
    """Resolve a receita pelo id, recusando o desconhecido antes de qualquer rede."""
    escolhida = str(identificador or RECEITA_PADRAO)
    try:
        return REGISTRO[escolhida]
    except KeyError:
        raise ErroDeNascimentoMeta(
            "META_RECIPE_UNKNOWN",
            "esta receita nao esta registrada neste servidor",
        ) from None


def capacidade_pausada() -> Mapping[str, object]:
    """Implemented workflow, NOT provider proof or permission to dispatch.

    Current named recipes compile into the same guarded V2 saga. Historical
    field/recipe evidence must not be mistaken for a feature toggle: approval
    consumes a fresh exact-hash receipt, and every resolved dependent operation
    is validated again before creation. No catalog response grants that right.
    """
    return {
        "implementada": True,
        "fluxo": "VALIDAR_APROVAR_CRIAR_PAUSADA",
        "estado_ao_nascer": "PAUSED",
        "autoriza_ativacao": False,
        "exige_recibo_exato_do_plano": True,
        "cobertura_previa": "INDEPENDENT_ROOTS_ONLY",
        "dependentes_validados_antes_de_criar": True,
        "exige_aprovacao_humana": True,
        "exige_capacidades_do_servidor": True,
        "exige_prova_de_destino": True,
        "prova_historica_nao_e_capacidade": True,
    }


def catalogo_publico() -> list[Mapping[str, object]]:
    """O que a tela precisa para MOSTRAR as receitas sem inventar semântica.

    Inclui o nível de prova e o motivo do bloqueio, porque uma receita que a
    tela apresenta como disponível e a rota recusa é pior do que uma receita
    ausente.
    """
    return [
        {
            "id": item.id,
            "rotulo": item.rotulo,
            "descricao": item.descricao,
            "objetivo": item.objective,
            "otimizacao": item.optimization_goal,
            "exige_fonte_de_conversao": item.exige_promoted_object,
            "propositos_de_mensuracao": sorted(item.propositos_de_mensuracao),
            "prova": item.prova,
            "capacidade_pausada": capacidade_pausada(),
            # Legacy historical badge, not permission to bypass approval/Shop.
            "criar_liberado": item.emissivel_para_criar,
            "motivo_sem_prova": item.motivo_sem_prova,
            "modos_de_orcamento": [
                {
                    "id": modo.id,
                    "nivel": modo.nivel,
                    "periodo": modo.periodo,
                    "prova": modo.prova,
                    "capacidade_pausada": capacidade_pausada(),
                    "criar_liberado": modo.emissivel_para_criar,
                }
                for modo in item.modos_de_orcamento
            ],
        }
        for item in REGISTRO.values()
    ]
