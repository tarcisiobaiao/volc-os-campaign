"""Adapters de integração FUTURA — interfaces puras, sem chamadas externas.

Cada adapter transforma uma forma de dado já conhecida (ledger campanha×dia, linha GAQL de
`campaign_simulation`, Keyword Planner/DataForSEO, JoinAds, card do Pautador, pedido da Bia) em
`EntradaViabilidade` ou em partes dela. Nenhum adapter lê rede, banco ou arquivo: recebe dicts.

A Bia pode PEDIR uma avaliação; nunca define tolerância do owner, câmbio, revshare, imposto,
nem transforma a recomendação em execução.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence

from volc_dil.contracts import Dinheiro

from .contrato import (
    Cambio, EntradaViabilidade, Evidencia, JanelaObservada, MedidaContagem, MedidaMonetaria, PerdaMaxima,
    PontoSimulacao, SimulacaoEntrada, Taxa,
)

_STATUS_COM_VALOR = {"observed", "zero_confirmed"}
_STATUS_PARA_EVIDENCIA = {"observed": Evidencia.OBSERVED, "zero_confirmed": Evidencia.OBSERVED, "partial": Evidencia.IMMATURE,
                          "missing": Evidencia.ABSENT, "late": Evidencia.UNKNOWN, "unavailable": Evidencia.UNKNOWN,
                          "unsupported": Evidencia.UNKNOWN, "invalid": Evidencia.INVALID}


def _cambio(d: Optional[Mapping[str, Any]], de: str, para: str) -> Cambio:
    if not d or d.get("taxa") is None:
        return Cambio(taxa=None, de=de, para=para, proveniencia=(d or {}).get("proveniencia", "ausente"), evidencia=Evidencia.ABSENT)
    return Cambio(taxa=Decimal(str(d["taxa"])), de=d.get("de", de), para=d.get("para", para), proveniencia=d.get("proveniencia", ""),
                  evidencia=Evidencia(d.get("evidencia", "estimated")))


def _taxa(d: Optional[Mapping[str, Any]]) -> Taxa:
    if not d or d.get("valor") is None:
        return Taxa(valor=None, evidencia=Evidencia.UNKNOWN, proveniencia=(d or {}).get("proveniencia", "ausente"))
    return Taxa(valor=Decimal(str(d["valor"])), evidencia=Evidencia(d.get("evidencia", "attested")), proveniencia=d.get("proveniencia", ""))


def _perda(d: Optional[Mapping[str, Any]]) -> PerdaMaxima:
    if not d or d.get("valor") is None:
        return PerdaMaxima(valor=None, horizonte_dias=None, proveniencia=(d or {}).get("proveniencia", "ausente"))
    return PerdaMaxima(valor=Dinheiro.de_json(d["valor"]), horizonte_dias=d.get("horizonte_dias"), proveniencia=d.get("proveniencia", "owner"))


def de_ledger_campanha_dia(candidato_id: str, linhas: Sequence[Mapping[str, Any]], *, as_of: datetime, vertical: str = "", pais: str = "",
                           fonte_custo: str = "google_ads", fonte_receita: str = "joinads", cambio: Optional[Mapping[str, Any]] = None,
                           revshare: Optional[Mapping[str, Any]] = None, imposto: Optional[Mapping[str, Any]] = None,
                           perda_maxima: Optional[Mapping[str, Any]] = None, simulacao: Optional[SimulacaoEntrada] = None) -> EntradaViabilidade:
    """Agrega linhas campanha×dia do ledger econômico. Só dias MADUROS com custo E receita com valor entram na
    economia comparável; dias com custo e sem receita viram flag (nunca receita zero)."""
    maduras = [l for l in linhas if l.get("maduro")]
    imaturas = [l for l in linhas if not l.get("maduro")]
    com_ambos = [l for l in maduras if l.get("receita_status") in _STATUS_COM_VALOR and l.get("custo_micros") is not None]
    sem_receita = [l for l in maduras if l.get("custo_micros") is not None and l.get("receita_status") not in _STATUS_COM_VALOR]
    disp = max((datetime.fromisoformat(l["disponivel_em"]) for l in linhas), default=as_of)
    moeda_custo = next((l["custo_moeda"] for l in linhas if l.get("custo_moeda")), "BRL")
    moeda_rec = next((l["receita_moeda"] for l in linhas if l.get("receita_moeda")), "USD")
    moeda_rec_ev = Evidencia(next((l["receita_moeda_evidencia"] for l in linhas if l.get("receita_moeda_evidencia")), "unknown"))
    flags = []
    if sem_receita:
        flags.append(f"dias_com_custo_sem_receita={len(sem_receita)}")
    if com_ambos:
        custo = MedidaMonetaria(Dinheiro(sum(int(l["custo_micros"]) for l in com_ambos), moeda_custo), Evidencia.OBSERVED, Evidencia.OBSERVED, disp, fonte_custo)
        cliques = MedidaContagem(sum(int(l.get("cliques") or 0) for l in com_ambos), Evidencia.OBSERVED, disp, fonte_custo)
        receita = MedidaMonetaria(Dinheiro(sum(int(l["receita_micros"]) for l in com_ambos), moeda_rec), Evidencia.RECONCILED, moeda_rec_ev, disp, fonte_receita)
    else:
        custo = MedidaMonetaria(None, Evidencia.ABSENT, Evidencia.UNKNOWN, disp, fonte_custo) if not maduras else \
            MedidaMonetaria(Dinheiro(sum(int(l["custo_micros"]) for l in maduras if l.get("custo_micros") is not None), moeda_custo), Evidencia.OBSERVED, Evidencia.OBSERVED, disp, fonte_custo)
        cliques = MedidaContagem(None, Evidencia.ABSENT, disp, fonte_custo) if not maduras else \
            MedidaContagem(sum(int(l.get("cliques") or 0) for l in maduras), Evidencia.OBSERVED, disp, fonte_custo)
        receita = MedidaMonetaria(None, Evidencia.ABSENT, moeda_rec_ev if moeda_rec_ev is not Evidencia.OBSERVED else Evidencia.UNKNOWN, disp, fonte_receita)
    dias = sorted(l["dia"] for l in linhas) or [as_of.date().isoformat()]
    return EntradaViabilidade(
        candidato_id=candidato_id, vertical=vertical, pais=pais, fonte_custo=fonte_custo, fonte_receita=fonte_receita, as_of=as_of,
        janela=JanelaObservada(dias[0], dias[-1], dias_maduros=len(com_ambos), dias_imaturos=len(imaturas)),
        cliques=cliques, custo=custo, receita=receita, cambio=_cambio(cambio, moeda_rec, moeda_custo), revshare=_taxa(revshare),
        imposto=_taxa(imposto), perda_maxima=_perda(perda_maxima), simulacao=simulacao, flags_qualidade=tuple(flags),
    )


def _int(v: Any) -> Optional[int]:
    return None if v is None else int(v)


def de_campaign_simulation_gaql(linha: Mapping[str, Any], *, moeda: str, disponivel_em: datetime, estrategia_lance: str = "", canal: str = "") -> SimulacaoEntrada:
    """Mapeia uma linha GAQL de `campaign_simulation` (camelCase ou snake_case) para `SimulacaoEntrada`.
    Tipos sem lista de pontos interpretável devolvem pontos vazios (o kernel diz 'tipo_nao_suportado')."""
    cs = linha.get("campaign_simulation") or linha.get("campaignSimulation") or {}
    tipo = cs.get("type", "")
    lista = {"CPC_BID": ("cpc_bid_point_list", "cpcBidPointList", "cpc_bid_micros", "cpcBidMicros"),
             "BUDGET": ("budget_point_list", "budgetPointList", "budget_amount_micros", "budgetAmountMicros")}.get(tipo)
    pontos: list[PontoSimulacao] = []
    if lista:
        pl = cs.get(lista[0]) or cs.get(lista[1]) or {}
        for p in pl.get("points", []):
            mod = p.get(lista[2], p.get(lista[3]))
            conv = p.get("biddable_conversions", p.get("biddableConversions"))
            pontos.append(PontoSimulacao(
                modificacao_micros=int(mod), cliques=_int(p.get("clicks")), custo_micros=_int(p.get("cost_micros", p.get("costMicros"))),
                impressoes=_int(p.get("impressions")), conversoes=None if conv is None else Decimal(str(conv)),
            ))
    return SimulacaoEntrada(tipo=tipo, moeda=moeda, pontos=tuple(pontos), disponivel_em=disponivel_em, estrategia_lance=estrategia_lance, canal=canal)


def de_pesquisa_keyword_planner(d: Mapping[str, Any], *, moeda: str) -> Optional[tuple[Dinheiro, Dinheiro]]:
    """CPC de pesquisa (Keyword Planner / DataForSEO): intervalo [low, high] em micros. NUNCA autoriza verba."""
    lo, hi = d.get("low_top_of_page_bid_micros"), d.get("high_top_of_page_bid_micros")
    if lo is None or hi is None:
        return None
    return (Dinheiro(int(lo), moeda), Dinheiro(int(hi), moeda))


def de_joinads_campanha_dia(linhas: Sequence[Mapping[str, Any]], *, moeda: str, moeda_evidencia: str, disponivel_em: datetime) -> MedidaMonetaria:
    """Soma earnings JoinAds (micros) de dias com valor. Moeda vem ATESTADA por padrão (a API não declara)."""
    com_valor = [l for l in linhas if l.get("status") in _STATUS_COM_VALOR and l.get("earnings_micros") is not None]
    if not com_valor:
        return MedidaMonetaria(None, Evidencia.ABSENT, Evidencia(moeda_evidencia) if moeda_evidencia != "observed" else Evidencia.UNKNOWN, disponivel_em, "joinads")
    return MedidaMonetaria(Dinheiro(sum(int(l["earnings_micros"]) for l in com_valor), moeda), Evidencia.RECONCILED, Evidencia(moeda_evidencia), disponivel_em, "joinads")


def de_pautador_card(card: Mapping[str, Any], *, as_of: datetime, cpc_intervalo: Optional[tuple[Dinheiro, Dinheiro]] = None,
                     rpc_intervalo: Optional[tuple[Dinheiro, Dinheiro]] = None, perda_maxima: Optional[PerdaMaxima] = None,
                     moeda: str = "BRL") -> EntradaViabilidade:
    """Card sem histórico: só pesquisa e tolerância do owner. Custo/receita/cliques ficam AUSENTES."""
    return EntradaViabilidade(
        candidato_id=str(card.get("id", "card")), vertical=card.get("vertical", ""), pais=card.get("pais", ""), fonte_custo="pesquisa", fonte_receita="pesquisa",
        as_of=as_of, janela=JanelaObservada(as_of.date().isoformat(), as_of.date().isoformat(), 0, 0),
        cliques=MedidaContagem(None, Evidencia.ABSENT, as_of, "pautador"),
        custo=MedidaMonetaria(None, Evidencia.ABSENT, Evidencia.UNKNOWN, as_of, "pautador"),
        receita=MedidaMonetaria(None, Evidencia.ABSENT, Evidencia.UNKNOWN, as_of, "pautador"),
        cambio=Cambio(None, moeda, moeda, "nao_aplicavel", Evidencia.ABSENT), revshare=Taxa(None, Evidencia.UNKNOWN, "ausente"),
        imposto=Taxa(None, Evidencia.UNKNOWN, "ausente"),
        perda_maxima=perda_maxima or PerdaMaxima(None, None, "ausente"), cpc_intervalo=cpc_intervalo, rpc_intervalo=rpc_intervalo,
    )


class BiaNaoPodeDefinirFinanceiro(PermissionError):
    """A Bia pediu para definir tolerância, câmbio, revshare ou imposto."""


_CAMPOS_FINANCEIROS = ("perda_maxima", "cambio", "revshare", "imposto", "tolerancia", "orcamento", "lance")


@dataclass(frozen=True)
class RequisicaoBia:
    entrada: EntradaViabilidade
    motivo: str
    somente_leitura: bool = True
    pode_executar: bool = False


def requisicao_bia(entrada: EntradaViabilidade, pedido: Mapping[str, Any]) -> RequisicaoBia:
    """A Bia só pode pedir a avaliação de uma entrada já montada pelo lado VOLC. Qualquer campo financeiro
    no pedido é recusado por construção; a resposta nunca carrega capacidade de execução."""
    proibidos = [k for k in pedido if k in _CAMPOS_FINANCEIROS]
    if proibidos:
        raise BiaNaoPodeDefinirFinanceiro(f"campos financeiros no pedido da Bia: {proibidos}")
    return RequisicaoBia(entrada=entrada, motivo=str(pedido.get("motivo", "")))
