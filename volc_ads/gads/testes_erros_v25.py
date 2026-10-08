"""Leitura de erro contra os PROTOS da v25, não contra dublês.

⚠️ Por que este arquivo existe: `_extrair_minimo_diario` procurava
`min_daily_budget_micros` e `minimum_micros`, nomes que não existem em
`BudgetPerDayMinimumErrorDetails`. Como a busca é por `getattr` com default, o
nome errado não quebra: devolve "sem piso", e a tela mostrava só a moeda. Um
teste com objeto falso teria usado o mesmo nome errado e passado. Só o proto
real denuncia o nome. Medido em 08/10/2026 na lib 33.0.0 (v25.2).
"""
from __future__ import annotations

from google.ads.googleads.v25.errors.types.campaign_budget_error import (
    CampaignBudgetErrorEnum,
)
from google.ads.googleads.v25.errors.types.errors import GoogleAdsError

from volc_ads.gads.errors import _extrair_minimo_diario

_ABAIXO = CampaignBudgetErrorEnum.CampaignBudgetError.BUDGET_BELOW_PER_DAY_MINIMUM


def _erro_de_piso(**detalhe) -> GoogleAdsError:
    err = GoogleAdsError(message="Budget below per-day minimum")
    err.error_code.campaign_budget_error = _ABAIXO
    for campo, valor in detalhe.items():
        setattr(err.details.budget_per_day_minimum_error_details, campo, valor)
    return err


def teste_piso_por_dia_vem_do_campo_real_da_v25():
    err = _erro_de_piso(currency_code="BRL", budget_per_day_minimum_micros=25_400_000)
    piso = _extrair_minimo_diario(err)
    assert piso is not None
    assert piso.micros == 25_400_000
    assert piso.moeda == "BRL"


def teste_piso_do_campo_amount_quando_so_ele_vem():
    """`minimum_budget_amount_micros` só vem quando a recusa é sobre `amount`."""
    err = _erro_de_piso(currency_code="COP", minimum_budget_amount_micros=19_000_000_000)
    piso = _extrair_minimo_diario(err)
    assert piso is not None
    assert piso.micros == 19_000_000_000
    assert piso.moeda == "COP"


def teste_piso_por_dia_tem_precedencia_sobre_amount():
    """Os dois podem vir juntos; o piso POR DIA é o que vale para orçamento diário."""
    err = _erro_de_piso(
        currency_code="BRL",
        budget_per_day_minimum_micros=25_400_000,
        minimum_budget_amount_micros=30_000_000,
    )
    assert _extrair_minimo_diario(err).micros == 25_400_000


def teste_erro_de_piso_sem_detalhe_e_vazio_e_nao_none():
    """"É sobre orçamento e a API não disse quanto" ≠ "não é sobre orçamento"."""
    err = GoogleAdsError(message="Budget below per-day minimum")
    err.error_code.campaign_budget_error = _ABAIXO
    piso = _extrair_minimo_diario(err)
    assert piso is not None
    assert piso.micros is None


def teste_outro_erro_nao_e_piso():
    err = GoogleAdsError(message="outro")
    err.error_code.campaign_budget_error = (
        CampaignBudgetErrorEnum.CampaignBudgetError.CAMPAIGN_BUDGET_REMOVED)
    assert _extrair_minimo_diario(err) is None
