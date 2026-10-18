"""Teto do primeiro experimento, derivado SÓ da tolerância de perda informada pelo owner.

Sem `perda_maxima` informada não há teto: o kernel devolve `Indisponivel("perda_maxima_ausente")`.
Nunca inventa tolerância. Quando o RPC é desconhecido, a perda esperada por clique é o CPC inteiro.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional, Union

from volc_dil.contracts import Dinheiro

from .contrato import EntradaViabilidade
from .economia import Indisponivel, envelope_conservador

MATURITY_WAIT_DIAS = 7       # JoinAds D-1 relê D-7..D-1; custo fecha em D+3
MIN_CLIQUES_MADUROS = 200    # abaixo disso o resultado é inconclusivo (premissa declarada, não calibrada)
MIN_DIAS_MADUROS = 3


@dataclass(frozen=True)
class Condicao:
    nome: str
    gatilhos: tuple[str, ...]


@dataclass(frozen=True)
class TetoExperimento:
    moeda: str
    perda_maxima: Dinheiro
    horizonte_dias: int
    cpc_conservador: Fraction
    rpc_conservador: Fraction
    perda_por_clique_conservadora: Fraction
    click_cap: int
    spend_cap: Dinheiro
    day_cap: int
    maturity_wait_dias: int
    parada: Condicao
    continuidade: Condicao
    inconclusao: Condicao
    premissas: tuple[str, ...]


def _cpc_rpc_conservadores(e: EntradaViabilidade) -> Union[tuple[Fraction, Fraction, list[str]], Indisponivel]:
    env = envelope_conservador(e)
    prem: list[str] = []
    if not isinstance(env, Indisponivel):
        prem.append("cpc_rpc_do_envelope_conservador")
        return env.cpc_conservador, env.rpc_conservador, prem
    # sem economia observada: CPC de pesquisa (limite superior) e RPC desconhecido = perda total
    if e.cpc_intervalo is not None:
        if e.cpc_intervalo[0].moeda != e.cpc_intervalo[1].moeda:
            return Indisponivel("cpc_intervalo_moeda_incompativel", f"{e.cpc_intervalo[0].moeda} vs {e.cpc_intervalo[1].moeda}")
        cpc = Fraction(max(e.cpc_intervalo[0].micros, e.cpc_intervalo[1].micros))
        prem.append("cpc_de_pesquisa_limite_superior_nunca_autoriza_verba")
    else:
        return Indisponivel("cpc_desconhecido", env.motivo)
    rpc = Fraction(0)
    if e.rpc_intervalo is not None:
        if {e.rpc_intervalo[0].moeda, e.rpc_intervalo[1].moeda} != {e.cpc_intervalo[0].moeda}:
            return Indisponivel("rpc_intervalo_moeda_incompativel", f"rpc em {e.rpc_intervalo[0].moeda}/{e.rpc_intervalo[1].moeda}, cpc em {e.cpc_intervalo[0].moeda}")
        rpc = Fraction(min(e.rpc_intervalo[0].micros, e.rpc_intervalo[1].micros))
        prem.append("rpc_de_pesquisa_limite_inferior")
    else:
        prem.append("rpc_desconhecido_perda_total")
    return cpc, rpc, prem


def calcular_teto(e: EntradaViabilidade) -> Union[TetoExperimento, Indisponivel]:
    pm = e.perda_maxima
    if not pm.informada():
        return Indisponivel("perda_maxima_ausente", "tolerância do owner não informada; o kernel não a deriva")
    assert pm.valor is not None and pm.horizonte_dias is not None
    r = _cpc_rpc_conservadores(e)
    if isinstance(r, Indisponivel):
        return r
    cpc, rpc, prem = r
    # moeda de referência: a do custo observado; sem custo, a do CPC de pesquisa. Nunca conversão implícita.
    moeda_ref = e.custo.valor.moeda if e.custo.valor is not None else (e.cpc_intervalo[0].moeda if e.cpc_intervalo is not None else None)
    if moeda_ref is None or pm.valor.moeda != moeda_ref:
        return Indisponivel("perda_maxima_moeda_incompativel", f"perda_maxima em {pm.valor.moeda}, referência em {moeda_ref}")
    moeda = pm.valor.moeda
    perda = Fraction(pm.valor.micros)
    perda_clique = max(Fraction(0), cpc - rpc)
    if perda_clique > 0:
        click_cap = int(perda / perda_clique)
        prem.append("click_cap=perda/(cpc_cons-rpc_cons)")
    elif e.volume_diario_possivel is not None:
        click_cap = e.volume_diario_possivel * pm.horizonte_dias
        prem.append("click_cap=volume_diario×horizonte (perda esperada por clique = 0)")
    else:
        click_cap = int(perda / cpc) if cpc > 0 else 0
        prem.append("click_cap=perda/cpc_cons (sem volume declarado, gasto limitado à tolerância)")
    spend_micros = int(math.floor(click_cap * cpc))
    if perda_clique > 0 and rpc == 0:
        spend_micros = min(spend_micros, pm.valor.micros)
    spend_cap = Dinheiro(spend_micros, moeda)
    if e.volume_diario_possivel is not None and e.volume_diario_possivel > 0:
        day_cap = max(1, min(pm.horizonte_dias, math.ceil(click_cap / e.volume_diario_possivel)))
    else:
        day_cap = pm.horizonte_dias
    parada = Condicao("parada", (
        f"gasto acumulado >= spend_cap ({spend_cap.decimal()} {moeda})",
        f"cliques acumulados >= click_cap ({click_cap})",
        f"contribuição madura por clique <= -{perda_clique} micros com >= {MIN_CLIQUES_MADUROS} cliques maduros",
        "qualquer sinal de política (reprovação, aviso) ou de IVT declarado pela plataforma",
    ))
    continuidade = Condicao("continuidade", (
        f"rpc maduro >= break-even conservador ({cpc} micros/clique) com >= {MIN_CLIQUES_MADUROS} cliques maduros e >= {MATURITY_WAIT_DIAS} dias de maturação",
        "moeda da receita observada ou atestada com extrato reconciliado",
    ))
    inconclusao = Condicao("inconclusao", (
        f"menos de {MIN_CLIQUES_MADUROS} cliques maduros ao fim do horizonte ({pm.horizonte_dias} dias)",
        f"menos de {MIN_DIAS_MADUROS} dias maduros",
        "receita em estado invalid/unknown ao fim do horizonte",
    ))
    return TetoExperimento(moeda, pm.valor, pm.horizonte_dias, cpc, rpc, perda_clique, click_cap, spend_cap, day_cap,
                           MATURITY_WAIT_DIAS, parada, continuidade, inconclusao, tuple(prem))
