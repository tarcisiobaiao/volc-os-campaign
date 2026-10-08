"""As ações de gestão — uma classe imutável por ação.

Cada ação responde a cinco perguntas, e as cinco moram juntas de propósito:

  1. é válida em si?            `__post_init__`  (sem rede, levanta AcaoRecusada)
  2. o que a API recebe?        `operacoes(get_type, customer_id, temporario)`
                                (função pura: nenhuma requisição sai daqui)
  3. como ler o "antes"?        `consultas_antes` + `interpretar_antes`
  4. o "antes" permite?         `conferir(antes)` (estratégia trocada por fora,
                                orçamento compartilhado, diff que não difere…)
  5. como desfazer?             `reverso(antes, criados)`

Separar 3–5 da ação seria o caminho mais curto para um reverso que não sabe o
que a ação mudou. O reverso de "teto de CPC = R$ 1,50" só existe se quem montou
a operação também sabe ler o teto anterior — e no MESMO campo.

## Por que `conferir` existe além do `validate_only`

O `validate_only` responde "a API aceita este payload?", não "este payload faz
o que o humano aprovou?". Mudar `maximize_conversions.target_cpa_micros` numa
campanha que alguém trocou para Maximizar cliques na véspera é payload válido
— e troca a estratégia em silêncio. `conferir` compara a ação com o estado lido
AGORA e recusa quando o mundo mudou desde a proposta.

## O que NÃO está aqui

Remover campanha, grupo ou anúncio. `REMOVED` é terminal no Google Ads e tem
funil próprio (`backend/app/trafego/remocao.py`). Status aqui é ENABLED/PAUSED,
e só. A única remoção que este módulo monta é a de recursos que a PRÓPRIA
gestão criou (critério, lista, vínculo), como reverso.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Sequence

from google.ads.googleads.v25.enums.types.day_of_week import DayOfWeekEnum
from google.ads.googleads.v25.enums.types.keyword_match_type import KeywordMatchTypeEnum
from google.ads.googleads.v25.enums.types.minute_of_hour import MinuteOfHourEnum

GetType = Callable[[str], Any]
Temporario = Callable[[], int]

#: A menor unidade de moeda que a API aceita, em micros, para TODA moeda que
#: operamos (BRL, USD, EUR, MXN… = 0,01). Moedas sem centavo (JPY, COP, CLP)
#: exigem mais — essa recusa fica com a API (NON_MULTIPLE_OF_MINIMUM_CURRENCY_UNIT),
#: porque inventar a tabela de moedas aqui seria um número desta casa.
MICROS_MINIMO = 10_000


class AcaoRecusada(ValueError):
    """A ação não sai da máquina: inválida em si, ou incompatível com o "antes"."""


# ── utilidades ──────────────────────────────────────────────────────────────


def _id(valor: Any, rotulo: str) -> int:
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        raise AcaoRecusada(f"{rotulo} não é um id numérico: {valor!r}") from None
    if n <= 0:
        raise AcaoRecusada(f"{rotulo} tem de ser positivo: {valor!r}")
    return n


def _micros(valor: Any, rotulo: str, *, zero_ok: bool = False) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise AcaoRecusada(f"{rotulo} tem de ser inteiro em micros: {valor!r}")
    if valor < 0 or (valor == 0 and not zero_ok):
        raise AcaoRecusada(f"{rotulo} tem de ser positivo: {valor}")
    if valor % MICROS_MINIMO:
        raise AcaoRecusada(
            f"{rotulo}={valor} não é múltiplo de {MICROS_MINIMO} micros (0,01 da moeda)")
    return valor


def _nome_enum(enum_cls: Any, nome: str, rotulo: str) -> str:
    validos = {e.name for e in enum_cls} - {"UNSPECIFIED", "UNKNOWN"}
    if nome not in validos:
        raise AcaoRecusada(f"{rotulo} desconhecido: {nome!r} (válidos: {sorted(validos)})")
    return nome


def _enum(v: Any) -> str:
    return getattr(v, "name", None) or str(v)


def _tem(msg: Any, campo: str) -> bool:
    """proto3 optional: 0 e "não definido" só se distinguem por presença."""
    try:
        return msg._pb.HasField(campo)
    except (AttributeError, ValueError):
        return False


def _modificador_lido(criterio: Any) -> float | None:
    """`bid_modifier` é FLOAT32 no proto: 1.2 volta como 1.2000000476837158.

    Sem arredondar, "o ajuste já está em 1.2" nunca seria verdade e o reverso
    escreveria 1.2000000476837158 de volta. 4 casas é a granularidade que a
    interface do Google mostra (0,01%).
    """
    return round(float(criterio.bid_modifier), 4) if _tem(criterio, "bid_modifier") else None


def _rn(customer_id: str, colecao: str, ident: Any) -> str:
    return f"customers/{customer_id}/{colecao}/{ident}"


def _criterio_rn(customer_id: str, campaign_id: int, criterion_id: int) -> str:
    return _rn(customer_id, "campaignCriteria", f"{campaign_id}~{criterion_id}")


# ── a base ──────────────────────────────────────────────────────────────────


class Acao:
    """Contrato comum. As subclasses são `@dataclass(frozen=True)`.

    `tipo` vira `trafego_proposta.operacao`; `alvo_nivel` respeita a CHECK
    `trafego_proposta_alvo_conhecido` da v10_02 — por isso só usa os sete
    valores de lá.
    """

    tipo: ClassVar[str] = ""
    #: Quando `reverso()` devolve vazio, o porquê. Vazio = reverso existe.
    motivo_sem_reverso: ClassVar[str] = ""
    #: Ação que não é `GoogleAdsService.Mutate` (recomendação).
    fora_do_mutate: ClassVar[bool] = False

    @property
    def alvo_nivel(self) -> str:  # pragma: no cover - sobrescrito
        raise NotImplementedError

    @property
    def alvo_id(self) -> str:  # pragma: no cover - sobrescrito
        raise NotImplementedError

    def operacoes(self, get_type: GetType, customer_id: str,
                  temporario: Temporario) -> list[Any]:  # pragma: no cover
        raise NotImplementedError

    def campos_alterados(self, customer_id: str) -> tuple[tuple[str, str], ...]:
        """(resource_name, campo) que a ação ATUALIZA ou REMOVE. Criação não entra.

        É o que o lote usa para recusar duas ações que brigam pelo mesmo campo
        do mesmo recurso — a segunda sobrescreveria a primeira dentro da mesma
        requisição, e o ledger registraria duas aplicações bem-sucedidas.
        """
        return ()

    def consultas_antes(self, customer_id: str) -> tuple[str, ...]:
        return ()

    def interpretar_antes(self, linhas: tuple[list[Any], ...]) -> dict:
        return {}

    def conferir(self, antes: dict) -> None:
        """Levanta AcaoRecusada se o estado lido não permite a ação."""

    def valor_proposto(self) -> dict:  # pragma: no cover - sobrescrito
        raise NotImplementedError

    def reverso(self, antes: dict, criados: tuple[str, ...] = ()) -> tuple["Acao", ...]:
        return ()

    def descrever(self) -> str:
        return f"{self.tipo} {self.alvo_nivel}:{self.alvo_id} → {self.valor_proposto()}"


# ── 1. status ───────────────────────────────────────────────────────────────

#: nivel → (coleção do resource name, operação do MutateOperation, recurso GAQL)
_NIVEIS_STATUS = {
    "campanha": ("campaigns", "campaign_operation", "campaign"),
    "grupo": ("adGroups", "ad_group_operation", "ad_group"),
    "anuncio": ("adGroupAds", "ad_group_ad_operation", "ad_group_ad"),
    "asset_group": ("assetGroups", "asset_group_operation", "asset_group"),
}
STATUS_GERIVEIS = ("ENABLED", "PAUSED")


@dataclass(frozen=True)
class AlterarStatus(Acao):
    """ENABLED ↔ PAUSED em campanha, grupo, anúncio ou asset group.

    `ident` do anúncio é `"<ad_group_id>~<ad_id>"`, que é como a API o
    identifica (`adGroupAds/{ad_group_id}~{ad_id}`): o mesmo ad id pode viver
    em dois grupos.
    """

    tipo: ClassVar[str] = "status"
    nivel: str
    ident: str
    status: str

    def __post_init__(self):
        if self.nivel not in _NIVEIS_STATUS:
            raise AcaoRecusada(f"nível de status desconhecido: {self.nivel!r}")
        if self.status not in STATUS_GERIVEIS:
            raise AcaoRecusada(
                f"status {self.status!r} não é gestão: só {STATUS_GERIVEIS}. "
                "REMOVED é terminal e tem funil próprio (trafego/remocao.py).")
        if self.nivel == "anuncio":
            partes = str(self.ident).split("~")
            if len(partes) != 2:
                raise AcaoRecusada(f"anúncio é '<ad_group_id>~<ad_id>': {self.ident!r}")
            ident = f"{_id(partes[0], 'ad_group_id')}~{_id(partes[1], 'ad_id')}"
        else:
            ident = str(_id(self.ident, f"id de {self.nivel}"))
        object.__setattr__(self, "ident", ident)

    @property
    def alvo_nivel(self) -> str:
        return self.nivel

    @property
    def alvo_id(self) -> str:
        return self.ident

    def _rn(self, customer_id: str) -> str:
        return _rn(customer_id, _NIVEIS_STATUS[self.nivel][0], self.ident)

    def operacoes(self, get_type, customer_id, temporario):
        _, campo_op, _ = _NIVEIS_STATUS[self.nivel]
        op = get_type("MutateOperation")
        sub = getattr(op, campo_op)
        sub.update.resource_name = self._rn(customer_id)
        sub.update.status = self.status
        sub.update_mask.paths.append("status")
        return [op]

    def campos_alterados(self, customer_id):
        return ((self._rn(customer_id), "status"),)

    def consultas_antes(self, customer_id):
        if self.nivel == "anuncio":
            ag, ad = self.ident.split("~")
            return ("SELECT ad_group_ad.ad.id, ad_group_ad.status FROM ad_group_ad "
                    f"WHERE ad_group.id = {ag} AND ad_group_ad.ad.id = {ad}",)
        recurso = _NIVEIS_STATUS[self.nivel][2]
        return (f"SELECT {recurso}.id, {recurso}.status FROM {recurso} "
                f"WHERE {recurso}.id = {self.ident}",)

    def interpretar_antes(self, linhas):
        recurso = _NIVEIS_STATUS[self.nivel][2]
        for r in linhas[0]:
            return {"existe": True, "status": _enum(getattr(r, recurso).status)}
        return {"existe": False}

    def conferir(self, antes):
        if not antes.get("existe"):
            raise AcaoRecusada(f"{self.nivel} {self.ident} não existe na conta")
        if antes["status"] == "REMOVED":
            raise AcaoRecusada(f"{self.nivel} {self.ident} está REMOVED; não volta")
        if antes["status"] == self.status:
            raise AcaoRecusada(f"{self.nivel} {self.ident} já está {self.status}")

    def valor_proposto(self):
        return {"status": self.status}

    def reverso(self, antes, criados=()):
        if antes.get("status") in STATUS_GERIVEIS and antes["status"] != self.status:
            return (AlterarStatus(self.nivel, self.ident, antes["status"]),)
        return ()


# ── 2. orçamento diário ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class AlterarOrcamento(Acao):
    """`campaign_budget.amount_micros`, com `update_mask` só nesse campo.

    ⚠️ Orçamento COMPARTILHADO: mudar o valor muda a verba de TODAS as campanhas
    que o usam. Quem propôs olhando uma campanha estaria mexendo em N. Sem
    `compartilhado_ciente=True`, `conferir` recusa e diz quantas são.

    Orçamento de período total (`total_amount_micros`, campanhas com data de
    fim) não é diário; mexer em `amount_micros` nele é erro de categoria.
    """

    tipo: ClassVar[str] = "orcamento.diario"
    campaign_id: int
    budget_id: int
    amount_micros: int
    compartilhado_ciente: bool = False

    def __post_init__(self):
        object.__setattr__(self, "campaign_id", _id(self.campaign_id, "campaign_id"))
        object.__setattr__(self, "budget_id", _id(self.budget_id, "budget_id"))
        _micros(self.amount_micros, "amount_micros")

    @classmethod
    def do_estado(cls, antes: dict, amount_micros: int, *,
                  compartilhado_ciente: bool = False) -> "AlterarOrcamento":
        """A ação montada a partir do "antes" lido — o budget é o que a campanha usa HOJE."""
        if not antes.get("existe"):
            raise AcaoRecusada("campanha não existe na conta")
        return cls(antes["campaign_id"], antes["budget_id"], amount_micros,
                   compartilhado_ciente)

    @property
    def alvo_nivel(self):
        return "campanha"

    @property
    def alvo_id(self):
        return str(self.campaign_id)

    def operacoes(self, get_type, customer_id, temporario):
        op = get_type("MutateOperation")
        b = op.campaign_budget_operation
        b.update.resource_name = _rn(customer_id, "campaignBudgets", self.budget_id)
        b.update.amount_micros = self.amount_micros
        b.update_mask.paths.append("amount_micros")
        return [op]

    def campos_alterados(self, customer_id):
        return ((_rn(customer_id, "campaignBudgets", self.budget_id), "amount_micros"),)

    def consultas_antes(self, customer_id):
        return ("SELECT campaign.id, campaign_budget.id, campaign_budget.amount_micros, "
                "campaign_budget.total_amount_micros, campaign_budget.period, "
                "campaign_budget.explicitly_shared, campaign_budget.reference_count, "
                "customer.currency_code FROM campaign "
                f"WHERE campaign.id = {self.campaign_id}",)

    def interpretar_antes(self, linhas):
        for r in linhas[0]:
            b = r.campaign_budget
            return {
                "existe": True,
                "campaign_id": int(r.campaign.id),
                "budget_id": int(b.id),
                "verba_diaria_micros": int(b.amount_micros) if _tem(b, "amount_micros") else None,
                "total_micros": int(b.total_amount_micros) if _tem(b, "total_amount_micros") else None,
                "periodo": _enum(b.period),
                "compartilhado": bool(b.explicitly_shared),
                "campanhas_no_orcamento": int(b.reference_count),
                "moeda": r.customer.currency_code,
            }
        return {"existe": False}

    def conferir(self, antes):
        if not antes.get("existe"):
            raise AcaoRecusada(f"campanha {self.campaign_id} não existe na conta")
        if antes["budget_id"] != self.budget_id:
            raise AcaoRecusada(
                f"a campanha usa hoje o orçamento {antes['budget_id']}, não "
                f"{self.budget_id}: a proposta foi feita sobre outro estado")
        if antes["total_micros"] is not None or antes["periodo"] != "DAILY":
            raise AcaoRecusada(
                f"orçamento {self.budget_id} é de período {antes['periodo']} "
                "(total), não diário")
        n = antes["campanhas_no_orcamento"]
        if (antes["compartilhado"] or n > 1) and not self.compartilhado_ciente:
            raise AcaoRecusada(
                f"orçamento {self.budget_id} é compartilhado por {n} campanha(s): "
                "mudar o valor muda a verba de todas. Repita com "
                "compartilhado_ciente=True se é isso mesmo.")
        if antes["verba_diaria_micros"] == self.amount_micros:
            raise AcaoRecusada("orçamento já está nesse valor")

    def valor_proposto(self):
        # `verba_diaria_micros` é a chave que o gatilho
        # `trafego_proposta_respeita_regra` lê para o teto de orçamento.
        return {"verba_diaria_micros": self.amount_micros, "budget_id": self.budget_id}

    def reverso(self, antes, criados=()):
        v = antes.get("verba_diaria_micros")
        if v and v != self.amount_micros:
            return (AlterarOrcamento(self.campaign_id, self.budget_id, v,
                                     compartilhado_ciente=True),)
        return ()


# ── 3. alvo de lance (sem trocar de estratégia) ─────────────────────────────

#: (estratégia lida, alvo) → (submensagem de Campaign, campo). Fora daqui não
#: existe alvo de nível campanha — e a recusa é a resposta certa:
#:  · MAXIMIZE_CONVERSIONS.cpc_bid_ceiling_micros só é mutável em PORTFÓLIO
#:    (o catálogo v25 nem deixa selecioná-lo em `campaign`);
#:  · MANUAL_CPC não tem alvo de campanha: o lance vive no grupo/keyword.
CAMPO_DO_ALVO: dict[tuple[str, str], tuple[str, str]] = {
    ("TARGET_SPEND", "teto_cpc"): ("target_spend", "cpc_bid_ceiling_micros"),
    ("MAXIMIZE_CONVERSIONS", "tcpa"): ("maximize_conversions", "target_cpa_micros"),
    ("MAXIMIZE_CONVERSION_VALUE", "troas"): ("maximize_conversion_value", "target_roas"),
    ("TARGET_CPA", "tcpa"): ("target_cpa", "target_cpa_micros"),
    ("TARGET_ROAS", "troas"): ("target_roas", "target_roas"),
}
TROAS_MAXIMO = 1000.0  # 100.000%; acima disso é erro de digitação, não meta

_GAQL_LANCE = (
    "SELECT campaign.id, campaign.advertising_channel_type, "
    "campaign.bidding_strategy_type, campaign.bidding_strategy, "
    "campaign.target_spend.cpc_bid_ceiling_micros, "
    "campaign.maximize_conversions.target_cpa_micros, "
    "campaign.maximize_conversion_value.target_roas, "
    "campaign.target_cpa.target_cpa_micros, campaign.target_roas.target_roas, "
    "customer.currency_code FROM campaign WHERE campaign.id = {cid}"
)


def _lance_antes(linhas) -> dict:
    for r in linhas[0]:
        c = r.campaign
        estrategia = _enum(c.bidding_strategy_type)
        antes = {
            "existe": True,
            "campaign_id": int(c.id),
            "canal": _enum(c.advertising_channel_type),
            "estrategia": estrategia,
            "portfolio": c.bidding_strategy or None,
            "moeda": r.customer.currency_code,
            "teto_cpc_micros": int(c.target_spend.cpc_bid_ceiling_micros),
            "tcpa_micros": int(c.maximize_conversions.target_cpa_micros
                               or c.target_cpa.target_cpa_micros),
            "troas": float(c.maximize_conversion_value.target_roas
                           or c.target_roas.target_roas),
        }
        return antes
    return {"existe": False}


def _valor_do_alvo(antes: dict, alvo: str) -> float | int:
    return {"teto_cpc": antes.get("teto_cpc_micros", 0),
            "tcpa": antes.get("tcpa_micros", 0),
            "troas": antes.get("troas", 0.0)}[alvo]


@dataclass(frozen=True)
class AlterarAlvoDeLance(Acao):
    """tCPA, tROAS ou teto de CPC do Maximizar cliques — no campo da estratégia ATUAL.

    `estrategia` é a estratégia que a proposta LEU. Ela escolhe o campo, e
    `conferir` recusa se a conta mudou de estratégia desde então: escrever
    `maximize_conversions.target_cpa_micros` numa campanha que está em
    TARGET_SPEND trocaria a estratégia sem ninguém ter pedido.

    `valor` 0 limpa o alvo (tCPA/tROAS opcionais no Maximizar conversões/valor;
    teto de CPC opcional no Maximizar cliques). Em TARGET_CPA/TARGET_ROAS
    padrão o alvo é obrigatório, e 0 é recusado.
    """

    tipo: ClassVar[str] = "lance.alvo"
    campaign_id: int
    estrategia: str
    alvo: str
    valor: float | int

    def __post_init__(self):
        object.__setattr__(self, "campaign_id", _id(self.campaign_id, "campaign_id"))
        if (self.estrategia, self.alvo) not in CAMPO_DO_ALVO:
            raise AcaoRecusada(
                f"{self.estrategia} não tem alvo '{self.alvo}' no nível da campanha. "
                f"Pares válidos: {sorted(CAMPO_DO_ALVO)}")
        limpa_ok = self.estrategia not in ("TARGET_CPA", "TARGET_ROAS")
        if self.alvo == "troas":
            if isinstance(self.valor, bool) or not isinstance(self.valor, (int, float)):
                raise AcaoRecusada(f"tROAS é razão (3.5 = 350%): {self.valor!r}")
            if self.valor < 0 or self.valor > TROAS_MAXIMO or (self.valor == 0 and not limpa_ok):
                raise AcaoRecusada(f"tROAS fora de (0, {TROAS_MAXIMO}]: {self.valor}")
            object.__setattr__(self, "valor", float(self.valor))
        else:
            _micros(self.valor, self.alvo, zero_ok=limpa_ok)

    @classmethod
    def do_estado(cls, antes: dict, alvo: str, valor: float | int) -> "AlterarAlvoDeLance":
        if not antes.get("existe"):
            raise AcaoRecusada("campanha não existe na conta")
        if antes.get("portfolio"):
            raise AcaoRecusada(
                f"a campanha usa a estratégia de portfólio {antes['portfolio']}: o alvo "
                "mora no BiddingStrategy e vale para todas as campanhas dele")
        return cls(antes["campaign_id"], antes["estrategia"], alvo, valor)

    @property
    def alvo_nivel(self):
        return "campanha"

    @property
    def alvo_id(self):
        return str(self.campaign_id)

    @property
    def caminho(self) -> str:
        grupo, campo = CAMPO_DO_ALVO[(self.estrategia, self.alvo)]
        return f"{grupo}.{campo}"

    def operacoes(self, get_type, customer_id, temporario):
        grupo, campo = CAMPO_DO_ALVO[(self.estrategia, self.alvo)]
        op = get_type("MutateOperation")
        c = op.campaign_operation.update
        c.resource_name = _rn(customer_id, "campaigns", self.campaign_id)
        getattr(c._pb, grupo).SetInParent()
        setattr(getattr(c, grupo), campo, self.valor)
        op.campaign_operation.update_mask.paths.append(self.caminho)
        return [op]

    def campos_alterados(self, customer_id):
        return ((_rn(customer_id, "campaigns", self.campaign_id), "campaign_bidding_strategy"),)

    def consultas_antes(self, customer_id):
        return (_GAQL_LANCE.format(cid=self.campaign_id),)

    def interpretar_antes(self, linhas):
        return _lance_antes(linhas)

    def conferir(self, antes):
        if not antes.get("existe"):
            raise AcaoRecusada(f"campanha {self.campaign_id} não existe na conta")
        if antes["portfolio"]:
            raise AcaoRecusada(
                f"a campanha passou a usar o portfólio {antes['portfolio']}; o alvo "
                "não é mais da campanha")
        if antes["estrategia"] != self.estrategia:
            raise AcaoRecusada(
                f"a proposta foi feita sobre {self.estrategia} e a campanha está em "
                f"{antes['estrategia']}. Alvo não troca estratégia: use TrocarEstrategia.")
        if _valor_do_alvo(antes, self.alvo) == self.valor:
            raise AcaoRecusada(f"{self.alvo} já está em {self.valor}")

    def valor_proposto(self):
        return {"estrategia": self.estrategia, self.alvo: self.valor}

    def reverso(self, antes, criados=()):
        if antes.get("estrategia") != self.estrategia:
            return ()
        anterior = _valor_do_alvo(antes, self.alvo)
        if anterior == self.valor:
            return ()
        return (AlterarAlvoDeLance(self.campaign_id, self.estrategia, self.alvo, anterior),)


# ── 4. troca de estratégia ──────────────────────────────────────────────────

#: Estratégias que a gestão sabe ESCREVER, por canal. TARGET_CPA/TARGET_ROAS
#: padrão ficam de fora: em Search e PMax viraram MaxConv/MaxConvValue com alvo,
#: e criar a forma antiga hoje é pedir recusa. Ler, lemos (AlterarAlvoDeLance).
ESTRATEGIAS_POR_CANAL: dict[str, frozenset[str]] = {
    "SEARCH": frozenset({"MANUAL_CPC", "TARGET_SPEND", "MAXIMIZE_CONVERSIONS",
                         "MAXIMIZE_CONVERSION_VALUE", "PORTFOLIO"}),
    "DISPLAY": frozenset({"MANUAL_CPC", "TARGET_SPEND", "MAXIMIZE_CONVERSIONS",
                          "MAXIMIZE_CONVERSION_VALUE", "PORTFOLIO"}),
    "DEMAND_GEN": frozenset({"TARGET_SPEND", "MAXIMIZE_CONVERSIONS",
                             "MAXIMIZE_CONVERSION_VALUE"}),
    "PERFORMANCE_MAX": frozenset({"MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE"}),
}
_ESTRATEGIAS_ESCREVIVEIS = frozenset().union(*ESTRATEGIAS_POR_CANAL.values())


@dataclass(frozen=True)
class TrocarEstrategia(Acao):
    """Troca o oneof `campaign_bidding_strategy`, com o alvo junto se houver.

    É ação EXPLÍCITA e separada de propósito: trocar estratégia reinicia o
    aprendizado do lance automático (dias de entrega instável). Ninguém deve
    chegar aqui por efeito colateral de "ajustar o tCPA".

    O `update_mask` nomeia um subcampo da estratégia nova mesmo quando o valor é
    0 (`maximize_conversions.target_cpa_micros`): máscara vazia não troca nada,
    e o descriptor não registra presença de submensagem vazia — daí o
    `SetInParent()` no proto cru.
    """

    tipo: ClassVar[str] = "lance.estrategia"
    campaign_id: int
    nova: str
    tcpa_micros: int = 0
    troas: float = 0.0
    teto_cpc_micros: int = 0
    portfolio: str = ""

    def __post_init__(self):
        object.__setattr__(self, "campaign_id", _id(self.campaign_id, "campaign_id"))
        if self.nova not in _ESTRATEGIAS_ESCREVIVEIS:
            raise AcaoRecusada(
                f"estratégia {self.nova!r} não é escrita pela gestão "
                f"(válidas: {sorted(_ESTRATEGIAS_ESCREVIVEIS)})")
        _micros(self.tcpa_micros, "tcpa_micros", zero_ok=True)
        _micros(self.teto_cpc_micros, "teto_cpc_micros", zero_ok=True)
        if not (0 <= float(self.troas) <= TROAS_MAXIMO):
            raise AcaoRecusada(f"tROAS fora de [0, {TROAS_MAXIMO}]: {self.troas}")
        sobra = {
            "tcpa_micros": self.tcpa_micros and self.nova != "MAXIMIZE_CONVERSIONS",
            "troas": self.troas and self.nova != "MAXIMIZE_CONVERSION_VALUE",
            "teto_cpc_micros": self.teto_cpc_micros and self.nova != "TARGET_SPEND",
            "portfolio": self.portfolio and self.nova != "PORTFOLIO",
        }
        errados = [k for k, v in sobra.items() if v]
        if errados:
            raise AcaoRecusada(f"{errados} não pertence(m) a {self.nova}")
        if self.nova == "PORTFOLIO" and not re.fullmatch(
                r"customers/\d+/biddingStrategies/\d+", self.portfolio or ""):
            raise AcaoRecusada(f"portfólio exige resource name: {self.portfolio!r}")

    @property
    def alvo_nivel(self):
        return "campanha"

    @property
    def alvo_id(self):
        return str(self.campaign_id)

    def _mascara_e_valor(self) -> tuple[str, str, Any]:
        return {
            "MANUAL_CPC": ("manual_cpc", "enhanced_cpc_enabled", False),
            "TARGET_SPEND": ("target_spend", "cpc_bid_ceiling_micros", self.teto_cpc_micros),
            "MAXIMIZE_CONVERSIONS": ("maximize_conversions", "target_cpa_micros",
                                     self.tcpa_micros),
            "MAXIMIZE_CONVERSION_VALUE": ("maximize_conversion_value", "target_roas",
                                          float(self.troas)),
        }[self.nova]

    def operacoes(self, get_type, customer_id, temporario):
        op = get_type("MutateOperation")
        c = op.campaign_operation.update
        c.resource_name = _rn(customer_id, "campaigns", self.campaign_id)
        if self.nova == "PORTFOLIO":
            c.bidding_strategy = self.portfolio
            op.campaign_operation.update_mask.paths.append("bidding_strategy")
            return [op]
        grupo, campo, valor = self._mascara_e_valor()
        getattr(c._pb, grupo).SetInParent()
        setattr(getattr(c, grupo), campo, valor)
        op.campaign_operation.update_mask.paths.append(f"{grupo}.{campo}")
        return [op]

    def campos_alterados(self, customer_id):
        return ((_rn(customer_id, "campaigns", self.campaign_id), "campaign_bidding_strategy"),)

    def consultas_antes(self, customer_id):
        return (_GAQL_LANCE.format(cid=self.campaign_id),)

    def interpretar_antes(self, linhas):
        return _lance_antes(linhas)

    def conferir(self, antes):
        if not antes.get("existe"):
            raise AcaoRecusada(f"campanha {self.campaign_id} não existe na conta")
        canal = antes["canal"]
        if canal not in ESTRATEGIAS_POR_CANAL:
            raise AcaoRecusada(f"canal {canal} fora do escopo da gestão")
        if self.nova not in ESTRATEGIAS_POR_CANAL[canal]:
            raise AcaoRecusada(
                f"{canal} não aceita {self.nova} "
                f"(aceita: {sorted(ESTRATEGIAS_POR_CANAL[canal])})")
        atual = "PORTFOLIO" if antes["portfolio"] else antes["estrategia"]
        if atual == self.nova and (self.nova != "PORTFOLIO"
                                   or antes["portfolio"] == self.portfolio):
            raise AcaoRecusada(
                f"a campanha já está em {self.nova}; para mudar o alvo use AlterarAlvoDeLance")

    def valor_proposto(self):
        v: dict[str, Any] = {"estrategia": self.nova}
        for k in ("tcpa_micros", "troas", "teto_cpc_micros", "portfolio"):
            if getattr(self, k):
                v[k] = getattr(self, k)
        return v

    def reverso(self, antes, criados=()):
        if not antes.get("existe"):
            return ()
        if antes.get("portfolio"):
            return (TrocarEstrategia(self.campaign_id, "PORTFOLIO",
                                     portfolio=antes["portfolio"]),)
        e = antes["estrategia"]
        if e not in _ESTRATEGIAS_ESCREVIVEIS:
            # TARGET_CPA/TARGET_ROAS padrão: não se recria pela API de hoje.
            return ()
        return (TrocarEstrategia(
            self.campaign_id, e,
            tcpa_micros=antes["tcpa_micros"] if e == "MAXIMIZE_CONVERSIONS" else 0,
            troas=antes["troas"] if e == "MAXIMIZE_CONVERSION_VALUE" else 0.0,
            teto_cpc_micros=antes["teto_cpc_micros"] if e == "TARGET_SPEND" else 0),)


# ── itens: termo e placement ────────────────────────────────────────────────

_PROIBIDOS_KEYWORD = set("!@%,*(){};~`<>?\\|^=")


@dataclass(frozen=True)
class Termo:
    """Uma palavra-chave negativa. O texto é normalizado (espaços) na criação."""

    texto: str
    correspondencia: str = "PHRASE"

    def __post_init__(self):
        t = " ".join(str(self.texto or "").split())
        if not t:
            raise AcaoRecusada("negativa vazia")
        if len(t) > 80:
            raise AcaoRecusada(f"negativa com mais de 80 caracteres: {t!r}")
        if len(t.split()) > 10:
            raise AcaoRecusada(f"negativa com mais de 10 palavras: {t!r}")
        ruins = sorted(set(t) & _PROIBIDOS_KEYWORD)
        if ruins:
            raise AcaoRecusada(f"negativa com caractere que a API recusa {ruins}: {t!r}")
        _nome_enum(KeywordMatchTypeEnum.KeywordMatchType, self.correspondencia,
                   "correspondência")
        object.__setattr__(self, "texto", t)

    @property
    def chave(self) -> tuple[str, str]:
        """Identidade para deduplicar: a API não diferencia caixa."""
        return (self.texto.lower(), self.correspondencia)

    def preencher(self, keyword_info: Any) -> None:
        keyword_info.text = self.texto
        keyword_info.match_type = self.correspondencia

    def json(self) -> dict:
        return {"texto": self.texto, "correspondencia": self.correspondencia}


_TIPOS_PLACEMENT = {
    # tipo → (campo do critério, subcampo, regex)
    "site": ("placement", "url", re.compile(r"^[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}(/\S*)?$")),
    "app": ("mobile_application", "app_id", re.compile(r"^[12]-[\w.\-]+$")),
    "youtube_canal": ("youtube_channel", "channel_id", re.compile(r"^UC[\w\-]{22}$")),
    "youtube_video": ("youtube_video", "video_id", re.compile(r"^[\w\-]{11}$")),
}


@dataclass(frozen=True)
class Placement:
    """Um lugar a excluir. `site` sem esquema (`exemplo.com.br/caminho`);
    `app` é `1-<id iOS>` ou `2-<pacote Android>`, como a API os escreve."""

    tipo: str
    valor: str

    def __post_init__(self):
        if self.tipo not in _TIPOS_PLACEMENT:
            raise AcaoRecusada(f"placement de tipo desconhecido: {self.tipo!r}")
        v = str(self.valor or "").strip()
        if self.tipo == "site":
            v = re.sub(r"^https?://", "", v.lower()).removeprefix("www.").rstrip("/")
        if not _TIPOS_PLACEMENT[self.tipo][2].fullmatch(v):
            raise AcaoRecusada(f"{self.tipo} inválido: {self.valor!r}")
        object.__setattr__(self, "valor", v)

    @property
    def chave(self) -> tuple[str, str]:
        return (self.tipo, self.valor.lower())

    def preencher(self, criterio: Any) -> None:
        campo, sub, _ = _TIPOS_PLACEMENT[self.tipo]
        setattr(getattr(criterio, campo), sub, self.valor)

    def json(self) -> dict:
        return {"tipo": self.tipo, "valor": self.valor}


def _placement_da_linha(crit: Any) -> Placement | None:
    t = _enum(crit.type_)
    try:
        if t == "PLACEMENT":
            return Placement("site", crit.placement.url)
        if t == "MOBILE_APPLICATION":
            return Placement("app", crit.mobile_application.app_id)
        if t == "YOUTUBE_CHANNEL":
            return Placement("youtube_canal", crit.youtube_channel.channel_id)
        if t == "YOUTUBE_VIDEO":
            return Placement("youtube_video", crit.youtube_video.video_id)
    except AcaoRecusada:
        return None  # o que já está na conta não precisa passar no NOSSO formato
    return None


def _sem_repetidos(itens: Sequence[Any], rotulo: str) -> tuple:
    vistos: set = set()
    for i in itens:
        if i.chave in vistos:
            raise AcaoRecusada(f"{rotulo} repetido na própria ação: {i.json()}")
        vistos.add(i.chave)
    if not itens:
        raise AcaoRecusada(f"nenhum {rotulo}")
    return tuple(itens)


# ── 5. negativas de keyword (campanha e grupo) ──────────────────────────────


@dataclass(frozen=True)
class AdicionarNegativas(Acao):
    """Negativas de keyword na campanha (`CampaignCriterion`) ou no grupo
    (`AdGroupCriterion`), com `negative=True`.

    Duplicata é recusada no `conferir` em vez de filtrada em silêncio: a
    proposta aprovada é exatamente esta lista, e mandar menos do que o humano
    viu é aplicar outra coisa.
    """

    tipo: ClassVar[str] = "negativa.keyword"
    escopo: str  # "campanha" | "grupo"
    alvo: int
    termos: tuple[Termo, ...]

    def __post_init__(self):
        if self.escopo not in ("campanha", "grupo"):
            raise AcaoRecusada(f"escopo de negativa desconhecido: {self.escopo!r}")
        object.__setattr__(self, "alvo", _id(self.alvo, f"id de {self.escopo}"))
        object.__setattr__(self, "termos", _sem_repetidos(tuple(self.termos), "termo"))

    @property
    def alvo_nivel(self):
        return self.escopo

    @property
    def alvo_id(self):
        return str(self.alvo)

    def operacoes(self, get_type, customer_id, temporario):
        ops = []
        for t in self.termos:
            op = get_type("MutateOperation")
            if self.escopo == "campanha":
                c = op.campaign_criterion_operation.create
                c.campaign = _rn(customer_id, "campaigns", self.alvo)
            else:
                c = op.ad_group_criterion_operation.create
                c.ad_group = _rn(customer_id, "adGroups", self.alvo)
            c.negative = True
            t.preencher(c.keyword)
            ops.append(op)
        return ops

    def consultas_antes(self, customer_id):
        if self.escopo == "campanha":
            return ("SELECT campaign.id, campaign_criterion.criterion_id, "
                    "campaign_criterion.keyword.text, campaign_criterion.keyword.match_type "
                    f"FROM campaign_criterion WHERE campaign.id = {self.alvo} "
                    "AND campaign_criterion.negative = TRUE "
                    "AND campaign_criterion.type = KEYWORD",)
        return ("SELECT ad_group.id, ad_group_criterion.criterion_id, "
                "ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type "
                f"FROM ad_group_criterion WHERE ad_group.id = {self.alvo} "
                "AND ad_group_criterion.negative = TRUE "
                "AND ad_group_criterion.type = KEYWORD",)

    def interpretar_antes(self, linhas):
        recurso = "campaign_criterion" if self.escopo == "campanha" else "ad_group_criterion"
        existentes = []
        for r in linhas[0]:
            k = getattr(r, recurso).keyword
            existentes.append([k.text.lower(), _enum(k.match_type)])
        return {"negativas_existentes": len(existentes), "chaves": sorted(existentes)}

    def conferir(self, antes):
        ja = {tuple(k) for k in antes.get("chaves", [])}
        dup = [t.json() for t in self.termos if t.chave in ja]
        if dup:
            raise AcaoRecusada(f"negativa(s) já existente(s) em {self.escopo} {self.alvo}: {dup}")

    def valor_proposto(self):
        return {"escopo": self.escopo, "adicionar": [t.json() for t in self.termos]}

    def reverso(self, antes, criados=()):
        return (RemoverCriados(tuple(criados)),) if criados else ()


# ── listas compartilhadas (keywords e placements) ───────────────────────────

TIPOS_LISTA = {"NEGATIVE_KEYWORDS": Termo, "NEGATIVE_PLACEMENTS": Placement}


def _criterio_compartilhado(get_type, shared_set_rn: str, item: Any) -> Any:
    op = get_type("MutateOperation")
    sc = op.shared_criterion_operation.create
    sc.shared_set = shared_set_rn
    if isinstance(item, Termo):
        item.preencher(sc.keyword)
    else:
        item.preencher(sc)
    return op


def _vinculo(get_type, customer_id, campaign_id: int, shared_set_rn: str) -> Any:
    op = get_type("MutateOperation")
    v = op.campaign_shared_set_operation.create
    v.campaign = _rn(customer_id, "campaigns", campaign_id)
    v.shared_set = shared_set_rn
    return op


def _conferir_tipo_dos_itens(tipo: str, itens: tuple) -> None:
    if tipo not in TIPOS_LISTA:
        raise AcaoRecusada(f"tipo de lista não gerido: {tipo!r} (só {sorted(TIPOS_LISTA)})")
    errado = [i for i in itens if not isinstance(i, TIPOS_LISTA[tipo])]
    if errado:
        raise AcaoRecusada(f"lista {tipo} só leva {TIPOS_LISTA[tipo].__name__}")


@dataclass(frozen=True)
class CriarListaCompartilhada(Acao):
    """`SharedSet` (NEGATIVE_KEYWORDS ou NEGATIVE_PLACEMENTS) + itens
    (`SharedCriterion`) + vínculo às campanhas (`CampaignSharedSet`), num só
    trecho do lote, ligados por id temporário.

    Com `partial_failure`, se a lista falhar, os itens e vínculos que apontam
    para o id temporário dela falham junto — o lote reporta a ação como
    `falhou`, não como `parcial`, e não sobra item órfão.
    """

    tipo: ClassVar[str] = "lista.criar"
    tipo_lista: str
    nome: str
    itens: tuple
    campanhas: tuple[int, ...] = ()

    def __post_init__(self):
        nome = " ".join(str(self.nome or "").split())
        if not nome or len(nome) > 255:
            raise AcaoRecusada(f"nome de lista vazio ou longo demais: {self.nome!r}")
        object.__setattr__(self, "nome", nome)
        itens = _sem_repetidos(tuple(self.itens), "item")
        _conferir_tipo_dos_itens(self.tipo_lista, itens)
        object.__setattr__(self, "itens", itens)
        object.__setattr__(self, "campanhas",
                           tuple(_id(c, "campaign_id") for c in self.campanhas))
        if len(set(self.campanhas)) != len(self.campanhas):
            raise AcaoRecusada("campanha repetida no vínculo")

    @property
    def alvo_nivel(self):
        return "conta"

    @property
    def alvo_id(self):
        return f"lista:{self.nome}"

    def operacoes(self, get_type, customer_id, temporario):
        rn = _rn(customer_id, "sharedSets", temporario())
        op = get_type("MutateOperation")
        s = op.shared_set_operation.create
        s.resource_name = rn
        s.name = self.nome
        s.type_ = self.tipo_lista
        ops = [op]
        ops += [_criterio_compartilhado(get_type, rn, i) for i in self.itens]
        ops += [_vinculo(get_type, customer_id, c, rn) for c in self.campanhas]
        return ops

    def consultas_antes(self, customer_id):
        return ("SELECT shared_set.id, shared_set.name, shared_set.type, shared_set.status "
                f"FROM shared_set WHERE shared_set.type = {self.tipo_lista} "
                "AND shared_set.status = ENABLED",)

    def interpretar_antes(self, linhas):
        return {"listas_com_mesmo_nome": [int(r.shared_set.id) for r in linhas[0]
                                          if r.shared_set.name == self.nome]}

    def conferir(self, antes):
        if antes.get("listas_com_mesmo_nome"):
            raise AcaoRecusada(
                f"já existe lista {self.tipo_lista} chamada {self.nome!r} "
                f"(ids {antes['listas_com_mesmo_nome']}); use AdicionarNaLista")

    def valor_proposto(self):
        return {"lista": self.nome, "tipo": self.tipo_lista,
                "itens": [i.json() for i in self.itens], "campanhas": list(self.campanhas)}

    def reverso(self, antes, criados=()):
        return (RemoverCriados(tuple(criados)),) if criados else ()


@dataclass(frozen=True)
class AdicionarNaLista(Acao):
    """Itens novos numa lista compartilhada que já existe."""

    tipo: ClassVar[str] = "lista.adicionar"
    shared_set_id: int
    tipo_lista: str
    itens: tuple

    def __post_init__(self):
        object.__setattr__(self, "shared_set_id", _id(self.shared_set_id, "shared_set_id"))
        itens = _sem_repetidos(tuple(self.itens), "item")
        _conferir_tipo_dos_itens(self.tipo_lista, itens)
        object.__setattr__(self, "itens", itens)

    @property
    def alvo_nivel(self):
        return "conta"

    @property
    def alvo_id(self):
        return f"lista:{self.shared_set_id}"

    def operacoes(self, get_type, customer_id, temporario):
        rn = _rn(customer_id, "sharedSets", self.shared_set_id)
        return [_criterio_compartilhado(get_type, rn, i) for i in self.itens]

    def consultas_antes(self, customer_id):
        return ("SELECT shared_set.id, shared_set.type, shared_set.status, "
                "shared_criterion.type, shared_criterion.keyword.text, "
                "shared_criterion.keyword.match_type, shared_criterion.placement.url "
                f"FROM shared_criterion WHERE shared_set.id = {self.shared_set_id}",
                "SELECT shared_set.id, shared_set.type, shared_set.status FROM shared_set "
                f"WHERE shared_set.id = {self.shared_set_id}")

    def interpretar_antes(self, linhas):
        chaves = []
        for r in linhas[0]:
            sc = r.shared_criterion
            if _enum(sc.type_) == "KEYWORD":
                chaves.append([sc.keyword.text.lower(), _enum(sc.keyword.match_type)])
            elif _enum(sc.type_) == "PLACEMENT":
                chaves.append(["site", sc.placement.url.lower()])
        for r in linhas[1]:
            return {"existe": True, "tipo": _enum(r.shared_set.type_),
                    "status": _enum(r.shared_set.status), "itens": len(chaves),
                    "chaves": sorted(chaves)}
        return {"existe": False}

    def conferir(self, antes):
        if not antes.get("existe") or antes["status"] != "ENABLED":
            raise AcaoRecusada(f"lista {self.shared_set_id} não existe ou não está ativa")
        if antes["tipo"] != self.tipo_lista:
            raise AcaoRecusada(f"lista {self.shared_set_id} é {antes['tipo']}, não {self.tipo_lista}")
        ja = {tuple(k) for k in antes.get("chaves", [])}
        dup = [i.json() for i in self.itens if i.chave in ja]
        if dup:
            raise AcaoRecusada(f"item(ns) já na lista: {dup}")

    def valor_proposto(self):
        return {"lista": self.shared_set_id, "adicionar": [i.json() for i in self.itens]}

    def reverso(self, antes, criados=()):
        return (RemoverCriados(tuple(criados)),) if criados else ()


@dataclass(frozen=True)
class AnexarLista(Acao):
    """Liga uma lista compartilhada existente a campanhas (`CampaignSharedSet`)."""

    tipo: ClassVar[str] = "lista.anexar"
    shared_set_id: int
    campanhas: tuple[int, ...]

    def __post_init__(self):
        object.__setattr__(self, "shared_set_id", _id(self.shared_set_id, "shared_set_id"))
        cs = tuple(_id(c, "campaign_id") for c in self.campanhas)
        if not cs or len(set(cs)) != len(cs):
            raise AcaoRecusada("campanhas vazias ou repetidas")
        object.__setattr__(self, "campanhas", cs)

    @property
    def alvo_nivel(self):
        return "campanha" if len(self.campanhas) == 1 else "conta"

    @property
    def alvo_id(self):
        return str(self.campanhas[0]) if len(self.campanhas) == 1 else f"lista:{self.shared_set_id}"

    def operacoes(self, get_type, customer_id, temporario):
        rn = _rn(customer_id, "sharedSets", self.shared_set_id)
        return [_vinculo(get_type, customer_id, c, rn) for c in self.campanhas]

    def consultas_antes(self, customer_id):
        return ("SELECT campaign.id, campaign_shared_set.status, shared_set.id "
                f"FROM campaign_shared_set WHERE shared_set.id = {self.shared_set_id} "
                "AND campaign_shared_set.status = ENABLED",)

    def interpretar_antes(self, linhas):
        return {"campanhas_vinculadas": sorted(int(r.campaign.id) for r in linhas[0])}

    def conferir(self, antes):
        ja = set(antes.get("campanhas_vinculadas", []))
        dup = [c for c in self.campanhas if c in ja]
        if dup:
            raise AcaoRecusada(f"lista {self.shared_set_id} já anexada a {dup}")

    def valor_proposto(self):
        return {"lista": self.shared_set_id, "anexar": list(self.campanhas)}

    def reverso(self, antes, criados=()):
        return (RemoverCriados(tuple(criados)),) if criados else ()


# ── 6. exclusão de placement (campanha e conta) ─────────────────────────────


@dataclass(frozen=True)
class ExcluirPlacements(Acao):
    """Placement negativo na campanha (`CampaignCriterion`, `negative=True`) ou
    na conta inteira (`CustomerNegativeCriterion`, que é negativo por natureza).

    Exclusão de conta vale para Display, Demand Gen, Vídeo e PMax de uma vez —
    é a alavanca de quem paga 42% do gasto em Display.
    """

    tipo: ClassVar[str] = "exclusao.placement"
    escopo: str  # "campanha" | "conta"
    itens: tuple[Placement, ...]
    campaign_id: int | None = None

    def __post_init__(self):
        if self.escopo not in ("campanha", "conta"):
            raise AcaoRecusada(f"escopo de exclusão desconhecido: {self.escopo!r}")
        if self.escopo == "campanha":
            object.__setattr__(self, "campaign_id", _id(self.campaign_id, "campaign_id"))
        elif self.campaign_id is not None:
            raise AcaoRecusada("exclusão de conta não leva campaign_id")
        object.__setattr__(self, "itens", _sem_repetidos(tuple(self.itens), "placement"))

    @property
    def alvo_nivel(self):
        return self.escopo

    @property
    def alvo_id(self):
        return str(self.campaign_id) if self.escopo == "campanha" else "conta"

    def operacoes(self, get_type, customer_id, temporario):
        ops = []
        for p in self.itens:
            op = get_type("MutateOperation")
            if self.escopo == "campanha":
                c = op.campaign_criterion_operation.create
                c.campaign = _rn(customer_id, "campaigns", self.campaign_id)
                c.negative = True
            else:
                c = op.customer_negative_criterion_operation.create
            p.preencher(c)
            ops.append(op)
        return ops

    def consultas_antes(self, customer_id):
        if self.escopo == "campanha":
            return ("SELECT campaign.id, campaign.advertising_channel_type, "
                    "campaign_criterion.type, campaign_criterion.placement.url, "
                    "campaign_criterion.mobile_application.app_id, "
                    "campaign_criterion.youtube_channel.channel_id, "
                    "campaign_criterion.youtube_video.video_id FROM campaign_criterion "
                    f"WHERE campaign.id = {self.campaign_id} "
                    "AND campaign_criterion.negative = TRUE AND campaign_criterion.type IN "
                    "(PLACEMENT, MOBILE_APPLICATION, YOUTUBE_CHANNEL, YOUTUBE_VIDEO)",)
        return ("SELECT customer_negative_criterion.id, customer_negative_criterion.type, "
                "customer_negative_criterion.placement.url, "
                "customer_negative_criterion.mobile_application.app_id, "
                "customer_negative_criterion.youtube_channel.channel_id, "
                "customer_negative_criterion.youtube_video.video_id "
                "FROM customer_negative_criterion WHERE customer_negative_criterion.type IN "
                "(PLACEMENT, MOBILE_APPLICATION, YOUTUBE_CHANNEL, YOUTUBE_VIDEO)",)

    def interpretar_antes(self, linhas):
        recurso = "campaign_criterion" if self.escopo == "campanha" else "customer_negative_criterion"
        chaves = []
        for r in linhas[0]:
            p = _placement_da_linha(getattr(r, recurso))
            if p:
                chaves.append(list(p.chave))
        return {"exclusoes_existentes": len(chaves), "chaves": sorted(chaves)}

    def conferir(self, antes):
        ja = {tuple(k) for k in antes.get("chaves", [])}
        dup = [p.json() for p in self.itens if p.chave in ja]
        if dup:
            raise AcaoRecusada(f"placement(s) já excluído(s): {dup}")

    def valor_proposto(self):
        return {"escopo": self.escopo, "excluir": [p.json() for p in self.itens]}

    def reverso(self, antes, criados=()):
        return (RemoverCriados(tuple(criados)),) if criados else ()


# ── 7. exclusão de IP ───────────────────────────────────────────────────────

LIMITE_IPS_POR_CAMPANHA = 500


def _ip(texto: str) -> str:
    """Endereço único, ou faixa IPv4 /24+ (o Google não aceita faixa mais larga)."""
    t = str(texto or "").strip()
    try:
        if "/" not in t:
            return str(ipaddress.ip_address(t))
        rede = ipaddress.ip_network(t, strict=True)
    except ValueError:
        raise AcaoRecusada(f"IP inválido: {texto!r}") from None
    if rede.version != 4 or rede.prefixlen < 24:
        raise AcaoRecusada(f"faixa de IP aceita só IPv4 /24 a /32: {texto!r}")
    return str(rede)


@dataclass(frozen=True)
class ExcluirIps(Acao):
    """`ip_block` negativo na campanha (`CampaignCriterion`) ou na conta
    (`CustomerNegativeCriterion.ip_block`). Até 500 por campanha.

    A gestão de arbitragem usa isto contra clique inválido recorrente, que é
    custo sem receita.
    """

    tipo: ClassVar[str] = "exclusao.ip"
    escopo: str
    ips: tuple[str, ...]
    campaign_id: int | None = None

    def __post_init__(self):
        if self.escopo not in ("campanha", "conta"):
            raise AcaoRecusada(f"escopo de exclusão desconhecido: {self.escopo!r}")
        if self.escopo == "campanha":
            object.__setattr__(self, "campaign_id", _id(self.campaign_id, "campaign_id"))
        elif self.campaign_id is not None:
            raise AcaoRecusada("exclusão de conta não leva campaign_id")
        ips = tuple(_ip(i) for i in self.ips)
        if not ips or len(set(ips)) != len(ips):
            raise AcaoRecusada("IPs vazios ou repetidos")
        if len(ips) > LIMITE_IPS_POR_CAMPANHA:
            raise AcaoRecusada(f"mais de {LIMITE_IPS_POR_CAMPANHA} IPs numa ação")
        object.__setattr__(self, "ips", ips)

    @property
    def alvo_nivel(self):
        return self.escopo

    @property
    def alvo_id(self):
        return str(self.campaign_id) if self.escopo == "campanha" else "conta"

    def operacoes(self, get_type, customer_id, temporario):
        ops = []
        for ip in self.ips:
            op = get_type("MutateOperation")
            if self.escopo == "campanha":
                c = op.campaign_criterion_operation.create
                c.campaign = _rn(customer_id, "campaigns", self.campaign_id)
                c.negative = True
            else:
                c = op.customer_negative_criterion_operation.create
            c.ip_block.ip_address = ip
            ops.append(op)
        return ops

    def consultas_antes(self, customer_id):
        if self.escopo == "campanha":
            return ("SELECT campaign.id, campaign_criterion.ip_block.ip_address "
                    f"FROM campaign_criterion WHERE campaign.id = {self.campaign_id} "
                    "AND campaign_criterion.type = IP_BLOCK",)
        return ("SELECT customer_negative_criterion.id, "
                "customer_negative_criterion.ip_block.ip_address "
                "FROM customer_negative_criterion "
                "WHERE customer_negative_criterion.type = IP_BLOCK",)

    def interpretar_antes(self, linhas):
        recurso = "campaign_criterion" if self.escopo == "campanha" else "customer_negative_criterion"
        ips = sorted(getattr(r, recurso).ip_block.ip_address for r in linhas[0])
        return {"ips_existentes": ips}

    def conferir(self, antes):
        ja = set(antes.get("ips_existentes", []))
        dup = [i for i in self.ips if i in ja]
        if dup:
            raise AcaoRecusada(f"IP(s) já excluído(s): {dup}")
        if self.escopo == "campanha" and len(ja) + len(self.ips) > LIMITE_IPS_POR_CAMPANHA:
            raise AcaoRecusada(
                f"a campanha já tem {len(ja)} IPs; +{len(self.ips)} passa de "
                f"{LIMITE_IPS_POR_CAMPANHA}")

    def valor_proposto(self):
        return {"escopo": self.escopo, "excluir_ips": list(self.ips)}

    def reverso(self, antes, criados=()):
        return (RemoverCriados(tuple(criados)),) if criados else ()


# ── 8. programação de anúncios e ajustes de lance ───────────────────────────

_MINUTOS = {0: "ZERO", 15: "FIFTEEN", 30: "THIRTY", 45: "FORTY_FIVE"}
_MINUTOS_INV = {v: k for k, v in _MINUTOS.items()}
MAX_JANELAS_POR_DIA = 6


def _hhmm(texto: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(texto or ""))
    if not m:
        raise AcaoRecusada(f"horário é HH:MM: {texto!r}")
    h, mi = int(m.group(1)), int(m.group(2))
    if mi not in _MINUTOS or not (0 <= h <= 24) or (h == 24 and mi):
        raise AcaoRecusada(f"horário fora da grade de 15 min (00:00–24:00): {texto!r}")
    return h, mi


def _modificador(valor: float | None, rotulo: str, *, zero_ok: bool) -> float | None:
    if valor is None:
        return None
    v = float(valor)
    if v == 0 and zero_ok:
        return 0.0
    if not (0.1 <= v <= 10.0):
        raise AcaoRecusada(
            f"{rotulo} {valor} fora de [0.1, 10.0] (−90% a +900%)"
            + (" ou 0 (−100%)" if zero_ok else ""))
    return round(v, 4)


@dataclass(frozen=True)
class Janela:
    """Uma janela de programação. `modificador` é o ajuste de lance da hora:
    1.2 = +20%; None = sem ajuste."""

    dia: str
    inicio: str
    fim: str
    modificador: float | None = None

    def __post_init__(self):
        _nome_enum(DayOfWeekEnum.DayOfWeek, self.dia, "dia")
        if self._minutos(self.fim) <= self._minutos(self.inicio):
            raise AcaoRecusada(f"janela {self.dia} {self.inicio}–{self.fim} termina antes de começar")
        object.__setattr__(self, "modificador",
                           _modificador(self.modificador, "ajuste de hora", zero_ok=False))

    @staticmethod
    def _minutos(t: str) -> int:
        h, m = _hhmm(t)
        return h * 60 + m

    @property
    def faixa(self) -> tuple[int, int]:
        return self._minutos(self.inicio), self._minutos(self.fim)

    def sobrepoe(self, outra: "Janela") -> bool:
        a, b = self.faixa
        c, d = outra.faixa
        return self.dia == outra.dia and a < d and c < b

    def preencher(self, ad_schedule: Any) -> None:
        hi, mi = _hhmm(self.inicio)
        hf, mf = _hhmm(self.fim)
        ad_schedule.day_of_week = self.dia
        ad_schedule.start_hour = hi
        ad_schedule.start_minute = _MINUTOS[mi]
        ad_schedule.end_hour = hf
        ad_schedule.end_minute = _MINUTOS[mf]

    def json(self) -> dict:
        return {"dia": self.dia, "inicio": self.inicio, "fim": self.fim,
                "modificador": self.modificador}


def _conferir_janelas(janelas: Sequence[Janela]) -> None:
    for i, a in enumerate(janelas):
        for b in janelas[i + 1:]:
            if a.sobrepoe(b):
                raise AcaoRecusada(f"janelas sobrepostas: {a.json()} × {b.json()}")
    por_dia: dict[str, int] = {}
    for j in janelas:
        por_dia[j.dia] = por_dia.get(j.dia, 0) + 1
    cheio = {d: n for d, n in por_dia.items() if n > MAX_JANELAS_POR_DIA}
    if cheio:
        raise AcaoRecusada(f"mais de {MAX_JANELAS_POR_DIA} janelas por dia: {cheio}")


def _min_enum(v: Any) -> str:
    return f"{_MINUTOS_INV.get(_enum(v), 0):02d}"


@dataclass(frozen=True)
class ProgramarAnuncios(Acao):
    """Cria janelas de `ad_schedule` (`CampaignCriterion`) e, se pedido,
    remove janelas existentes — pelo `criterion_id` lido do estado.

    "Substituir a programação" é remover N + criar M na MESMA ação, para que o
    reverso saiba recriar exatamente as N removidas (com seus ajustes).
    Use `ProgramarAnuncios.substituindo(antes, …)` para remover todas as atuais.
    """

    tipo: ClassVar[str] = "programacao.anuncios"
    campaign_id: int
    janelas: tuple[Janela, ...] = ()
    remover: tuple[int, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "campaign_id", _id(self.campaign_id, "campaign_id"))
        janelas = tuple(self.janelas)
        remover = tuple(_id(r, "criterion_id") for r in self.remover)
        if not janelas and not remover:
            raise AcaoRecusada("programação sem janela a criar nem a remover")
        _conferir_janelas(janelas)
        object.__setattr__(self, "janelas", janelas)
        object.__setattr__(self, "remover", remover)

    @classmethod
    def substituindo(cls, antes: dict, campaign_id: int,
                     janelas: Sequence[Janela]) -> "ProgramarAnuncios":
        return cls(campaign_id, tuple(janelas),
                   tuple(j["criterion_id"] for j in antes.get("janelas", [])))

    @property
    def alvo_nivel(self):
        return "campanha"

    @property
    def alvo_id(self):
        return str(self.campaign_id)

    def operacoes(self, get_type, customer_id, temporario):
        ops = []
        for cid in self.remover:
            op = get_type("MutateOperation")
            op.campaign_criterion_operation.remove = _criterio_rn(
                customer_id, self.campaign_id, cid)
            ops.append(op)
        for j in self.janelas:
            op = get_type("MutateOperation")
            c = op.campaign_criterion_operation.create
            c.campaign = _rn(customer_id, "campaigns", self.campaign_id)
            j.preencher(c.ad_schedule)
            if j.modificador is not None:
                c.bid_modifier = j.modificador
            ops.append(op)
        return ops

    def campos_alterados(self, customer_id):
        return tuple((_criterio_rn(customer_id, self.campaign_id, c), "*") for c in self.remover)

    def consultas_antes(self, customer_id):
        return ("SELECT campaign.id, campaign_criterion.criterion_id, "
                "campaign_criterion.bid_modifier, campaign_criterion.ad_schedule.day_of_week, "
                "campaign_criterion.ad_schedule.start_hour, "
                "campaign_criterion.ad_schedule.start_minute, "
                "campaign_criterion.ad_schedule.end_hour, "
                "campaign_criterion.ad_schedule.end_minute FROM campaign_criterion "
                f"WHERE campaign.id = {self.campaign_id} "
                "AND campaign_criterion.type = AD_SCHEDULE",)

    def interpretar_antes(self, linhas):
        janelas = []
        for r in linhas[0]:
            cc = r.campaign_criterion
            s = cc.ad_schedule
            janelas.append({
                "criterion_id": int(cc.criterion_id),
                "dia": _enum(s.day_of_week),
                "inicio": f"{int(s.start_hour):02d}:{_min_enum(s.start_minute)}",
                "fim": f"{int(s.end_hour):02d}:{_min_enum(s.end_minute)}",
                "modificador": _modificador_lido(cc),
            })
        janelas.sort(key=lambda j: (j["dia"], j["inicio"]))
        return {"janelas": janelas}

    def conferir(self, antes):
        atuais = {j["criterion_id"]: j for j in antes.get("janelas", [])}
        fantasmas = [c for c in self.remover if c not in atuais]
        if fantasmas:
            raise AcaoRecusada(f"janela(s) a remover não existe(m) mais: {fantasmas}")
        ficam = [Janela(j["dia"], j["inicio"], j["fim"])
                 for c, j in atuais.items() if c not in self.remover]
        _conferir_janelas(ficam + list(self.janelas))

    def valor_proposto(self):
        return {"criar": [j.json() for j in self.janelas], "remover": list(self.remover)}

    def reverso(self, antes, criados=()):
        atuais = {j["criterion_id"]: j for j in antes.get("janelas", [])}
        recriar = tuple(Janela(atuais[c]["dia"], atuais[c]["inicio"], atuais[c]["fim"],
                               atuais[c]["modificador"])
                        for c in self.remover if c in atuais)
        passos: list[Acao] = []
        if criados:
            passos.append(RemoverCriados(tuple(criados)))
        if recriar:
            passos.append(ProgramarAnuncios(self.campaign_id, recriar))
        return tuple(passos)


#: O id de critério que o Google dá ao dispositivo em TODA campanha.
#: Medido na Crédito Up (24278665189): 30000/30001/30002 já existem ao nascer.
DISPOSITIVOS = {"DESKTOP": 30000, "MOBILE": 30001, "TABLET": 30002, "CONNECTED_TV": 30004}


@dataclass(frozen=True)
class _AjusteDeCriterio(Acao):
    """Base: `CampaignCriterion.bid_modifier` num critério que já existe.

    ⚠️ Não é `CampaignBidModifier`. Na v25 esse recurso só tem
    `interaction_type` (chamadas). Dispositivo e hora são `CampaignCriterion`
    com `bid_modifier` — o critério de dispositivo nasce com a campanha, e o
    ajuste é um UPDATE nele, não uma criação.
    """

    campaign_id: int
    criterion_id: int
    modificador: float

    @property
    def alvo_nivel(self):
        return "campanha"

    @property
    def alvo_id(self):
        return str(self.campaign_id)

    def operacoes(self, get_type, customer_id, temporario):
        op = get_type("MutateOperation")
        c = op.campaign_criterion_operation.update
        c.resource_name = _criterio_rn(customer_id, self.campaign_id, self.criterion_id)
        c.bid_modifier = self.modificador
        op.campaign_criterion_operation.update_mask.paths.append("bid_modifier")
        return [op]

    def campos_alterados(self, customer_id):
        return ((_criterio_rn(customer_id, self.campaign_id, self.criterion_id), "bid_modifier"),)

    def consultas_antes(self, customer_id):
        return ("SELECT campaign.id, campaign.advertising_channel_type, "
                "campaign_criterion.criterion_id, campaign_criterion.bid_modifier "
                f"FROM campaign_criterion WHERE campaign.id = {self.campaign_id} "
                f"AND campaign_criterion.criterion_id = {self.criterion_id}",)

    def interpretar_antes(self, linhas):
        for r in linhas[0]:
            cc = r.campaign_criterion
            return {"existe": True, "canal": _enum(r.campaign.advertising_channel_type),
                    "modificador": _modificador_lido(cc)}
        return {"existe": False}

    def conferir(self, antes):
        if not antes.get("existe"):
            raise AcaoRecusada(
                f"critério {self.criterion_id} não existe na campanha {self.campaign_id}")
        if antes.get("canal") == "PERFORMANCE_MAX":
            raise AcaoRecusada("PMax não aceita ajuste de lance por critério")
        atual = antes["modificador"] if antes["modificador"] is not None else 1.0
        if atual == self.modificador:
            raise AcaoRecusada(f"ajuste já está em {self.modificador}")

    def valor_proposto(self):
        return {"criterion_id": self.criterion_id, "modificador": self.modificador}

    def reverso(self, antes, criados=()):
        if not antes.get("existe"):
            return ()
        # "Sem ajuste" (None) e 1.0 são o mesmo lance; a API não tem como
        # "desdefinir" o campo por update, então o reverso escreve 1.0.
        anterior = antes["modificador"] if antes["modificador"] is not None else 1.0
        if anterior == self.modificador:
            return ()
        return (type(self)._refazer(self, anterior),)


@dataclass(frozen=True)
class AjustarDispositivo(_AjusteDeCriterio):
    """Ajuste de lance por dispositivo. 0 = −100% (não exibir no dispositivo)."""

    tipo: ClassVar[str] = "ajuste.dispositivo"
    campaign_id: int = 0
    criterion_id: int = 0
    modificador: float = 1.0
    dispositivo: str = ""

    def __post_init__(self):
        object.__setattr__(self, "campaign_id", _id(self.campaign_id, "campaign_id"))
        if self.dispositivo not in DISPOSITIVOS:
            raise AcaoRecusada(f"dispositivo desconhecido: {self.dispositivo!r}")
        object.__setattr__(self, "criterion_id", DISPOSITIVOS[self.dispositivo])
        object.__setattr__(self, "modificador",
                           _modificador(self.modificador, "ajuste de dispositivo", zero_ok=True))

    @classmethod
    def de(cls, campaign_id: int, dispositivo: str, modificador: float) -> "AjustarDispositivo":
        return cls(campaign_id=campaign_id, modificador=modificador, dispositivo=dispositivo)

    def _refazer(self, modificador: float) -> "AjustarDispositivo":
        return AjustarDispositivo.de(self.campaign_id, self.dispositivo, modificador)

    def valor_proposto(self):
        return {"dispositivo": self.dispositivo, "modificador": self.modificador}


@dataclass(frozen=True)
class AjustarHorario(_AjusteDeCriterio):
    """Ajuste de lance de uma janela de programação que já existe."""

    tipo: ClassVar[str] = "ajuste.horario"

    def __post_init__(self):
        object.__setattr__(self, "campaign_id", _id(self.campaign_id, "campaign_id"))
        object.__setattr__(self, "criterion_id", _id(self.criterion_id, "criterion_id"))
        object.__setattr__(self, "modificador",
                           _modificador(self.modificador, "ajuste de hora", zero_ok=False))

    def _refazer(self, modificador: float) -> "AjustarHorario":
        return AjustarHorario(self.campaign_id, self.criterion_id, modificador)


# ── reverso de criação ──────────────────────────────────────────────────────

#: Coleção → (operação, ordem de remoção). O vínculo sai antes da lista e o
#: item antes da lista, para que nenhuma remoção dependa de outra ter falhado.
_REMOVIVEIS = {
    "campaignSharedSets": ("campaign_shared_set_operation", 0),
    "campaignCriteria": ("campaign_criterion_operation", 1),
    "adGroupCriteria": ("ad_group_criterion_operation", 1),
    "customerNegativeCriteria": ("customer_negative_criterion_operation", 1),
    "sharedCriteria": ("shared_criterion_operation", 2),
    "sharedSets": ("shared_set_operation", 3),
}
_RN_REMOVIVEL = re.compile(r"^customers/(\d+)/(" + "|".join(_REMOVIVEIS) + r")/([\d~]+)$")


@dataclass(frozen=True)
class RemoverCriados(Acao):
    """Remove recursos que a GESTÃO criou — o reverso de toda ação de criação.

    Só aceita critério, lista e vínculo. Campanha, grupo e anúncio não estão no
    vocabulário: um resource name desses aqui é defeito de quem chamou, e a
    remoção deles tem funil próprio.
    """

    tipo: ClassVar[str] = "reverso.remover_criados"
    motivo_sem_reverso: ClassVar[str] = "o reverso de remover é recriar a ação original"
    recursos: tuple[str, ...]

    def __post_init__(self):
        rs = tuple(self.recursos)
        if not rs:
            raise AcaoRecusada("nada a remover")
        ruins = [r for r in rs if not _RN_REMOVIVEL.match(r)]
        if ruins:
            raise AcaoRecusada(f"a gestão só remove o que ela cria (critério/lista/vínculo): {ruins}")
        if len(set(rs)) != len(rs):
            raise AcaoRecusada("recurso repetido")
        ordem = sorted(rs, key=lambda r: _REMOVIVEIS[_RN_REMOVIVEL.match(r).group(2)][1])
        object.__setattr__(self, "recursos", tuple(ordem))

    @property
    def alvo_nivel(self):
        colecoes = {_RN_REMOVIVEL.match(r).group(2) for r in self.recursos}
        if colecoes == {"campaignCriteria"}:
            return "campanha"
        if colecoes == {"adGroupCriteria"}:
            return "grupo"
        return "conta"

    @property
    def alvo_id(self):
        r = self.recursos[0]
        m = _RN_REMOVIVEL.match(r)
        return m.group(3).split("~")[0] if self.alvo_nivel in ("campanha", "grupo") else "conta"

    def operacoes(self, get_type, customer_id, temporario):
        ops = []
        for r in self.recursos:
            m = _RN_REMOVIVEL.match(r)
            if m.group(1) != str(customer_id):
                raise AcaoRecusada(f"{r} é de outra conta que não {customer_id}")
            op = get_type("MutateOperation")
            getattr(op, _REMOVIVEIS[m.group(2)][0]).remove = r
            ops.append(op)
        return ops

    def campos_alterados(self, customer_id):
        return tuple((r, "*") for r in self.recursos)

    def valor_proposto(self):
        return {"remover": list(self.recursos)}


# ── 9. recomendações (fora do GoogleAdsService.Mutate) ──────────────────────

_RN_RECOMENDACAO = re.compile(r"^customers/(\d+)/recommendations/[A-Za-z0-9+=_\-~]+$")


@dataclass(frozen=True)
class _AcaoDeRecomendacao(Acao):
    """Base: `RecommendationService`, que NÃO é `GoogleAdsService.Mutate`.

    ⚠️ `ApplyRecommendationRequest` e `DismissRecommendationRequest` da v25 têm
    só `customer_id`, `operations` e `partial_failure` — NÃO há
    `validate_only`. Não existe ensaio de graça: chamar é aplicar. Por isso o
    lote marca estas ações como `nao_validavel` e nunca as manda no ensaio.
    """

    fora_do_mutate: ClassVar[bool] = True
    recurso: str

    def __post_init__(self):
        if not _RN_RECOMENDACAO.match(str(self.recurso or "")):
            raise AcaoRecusada(f"resource name de recomendação inválido: {self.recurso!r}")

    @property
    def alvo_nivel(self):
        return "conta"

    @property
    def alvo_id(self):
        return self.recurso.rsplit("/", 1)[-1]

    def operacoes(self, get_type, customer_id, temporario):
        raise AcaoRecusada(
            f"{self.tipo} não é GoogleAdsService.Mutate; use lote.aplicar_recomendacoes")

    def consultas_antes(self, customer_id):
        return ("SELECT recommendation.resource_name, recommendation.type, "
                "recommendation.dismissed, recommendation.campaign, "
                "recommendation.campaign_budget, recommendation.ad_group "
                "FROM recommendation WHERE recommendation.resource_name = "
                f"'{self.recurso}'",)

    def interpretar_antes(self, linhas):
        for r in linhas[0]:
            rec = r.recommendation
            return {"existe": True, "tipo": _enum(rec.type_),
                    "dispensada": bool(rec.dismissed),
                    "campanha": rec.campaign or None,
                    "orcamento": rec.campaign_budget or None,
                    "grupo": rec.ad_group or None}
        return {"existe": False}

    def conferir(self, antes):
        if not antes.get("existe"):
            raise AcaoRecusada(f"recomendação {self.recurso} não existe mais (expira com o tempo)")
        if antes["dispensada"]:
            raise AcaoRecusada(f"recomendação {self.recurso} já foi dispensada")


@dataclass(frozen=True)
class AplicarRecomendacao(_AcaoDeRecomendacao):
    """`RecommendationService.ApplyRecommendation`, como o Google recomendou.

    Sem reverso automático: o efeito depende do tipo (keyword nova, orçamento,
    troca de estratégia, asset…) e a resposta só devolve o resource name da
    recomendação, não o que ela mudou. Para recomendação de ORÇAMENTO ou de
    ALVO, prefira montar `AlterarOrcamento`/`AlterarAlvoDeLance` com o valor
    recomendado: o efeito é o mesmo, há `validate_only` e o reverso é exato.
    """

    tipo: ClassVar[str] = "recomendacao.aplicar"
    motivo_sem_reverso: ClassVar[str] = (
        "aplicar recomendação não devolve o que mudou; desfazer exige ler "
        "change_event e montar a ação tipada inversa")

    def operacao_de_recomendacao(self, get_type) -> Any:
        op = get_type("ApplyRecommendationOperation")
        op.resource_name = self.recurso
        return op

    def valor_proposto(self):
        return {"aplicar": self.recurso}


@dataclass(frozen=True)
class DispensarRecomendacao(_AcaoDeRecomendacao):
    """`RecommendationService.DismissRecommendation`. Não muda a campanha."""

    tipo: ClassVar[str] = "recomendacao.dispensar"
    motivo_sem_reverso: ClassVar[str] = "recomendação dispensada não volta pela API"

    def operacao_de_recomendacao(self, get_type) -> Any:
        req = get_type("DismissRecommendationRequest")
        op = type(req).DismissRecommendationOperation()
        op.resource_name = self.recurso
        return op

    def valor_proposto(self):
        return {"dispensar": self.recurso}


__all__ = [
    "Acao", "AcaoRecusada", "AdicionarNaLista", "AdicionarNegativas", "AjustarDispositivo",
    "AjustarHorario", "AlterarAlvoDeLance", "AlterarOrcamento", "AlterarStatus",
    "AnexarLista", "AplicarRecomendacao", "CriarListaCompartilhada", "DispensarRecomendacao",
    "ExcluirIps", "ExcluirPlacements", "Janela", "Placement", "ProgramarAnuncios",
    "RemoverCriados", "Termo", "TrocarEstrategia",
]
