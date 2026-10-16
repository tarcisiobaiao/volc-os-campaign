"""Gerador PROVISÓRIO e mínimo (isolado para troca): verdade campanha × dia + linhas no formato real.

Existe para que os gates do shadow rodem neste worktree com controle fino (qual campanha, qual dia,
qual defeito). O simulador da thread E (`volc_dil.fundacao.simulador`) é a fonte principal de
avaliação depois da integração (ver `fonte_simulador.py`). Interface comum consumida pelo resto do
pacote: `FluxoSintetico(observacoes, verdade, cambios, espec)` e o protocolo `Verdade`
(`celulas()`, `lucros(plano)`), ambos definidos em `avaliacao.py`.

Verdade: custo C(c,d) (BRL) e receita R(c,d) (BRL equivalente) com ROAS por campanha; contrafactual
de verba com fator f: custo = C·f, receita = R·f^0,8 (retorno decrescente; sem carryover entre dias).
Observação: as linhas passam pelos adaptadores da thread A, exatamente como o dado real passará:
D0 parcial (horas `horas_d0`), D-1 às 04:00 (às vezes inflado), backfill exato em D+3 05:00;
receita JoinAds em USD lida em D+1/D+2/D+3 08:15 (preliminar → final), earnings do domínio.
Defeitos injetáveis: campanha nova com preliminar muito baixa, zero sintetizado do v21 (R3),
custom_key trocada, receita em outra moeda, restatement tardio de receita.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from fractions import Fraction
from typing import Optional

from .avaliacao import FluxoSintetico
from .linhas_formato_real import (
    CONTA_SINTETICA,
    DOMINIO_SINTETICO,
    instante_local,
    linha_joinads_earnings,
    linha_joinads_kv,
    linha_v21,
)
from .real import observacoes_de_linhas_reais
from .snapshot import CambioDeclarado
from .tipos import BPS, EntidadeCampanha

VERSAO_GERADOR = "provisorio@1"


@dataclass(frozen=True)
class EspecProvisoria:
    nome: str = "base"
    seed: int = 20261016
    inicio: date = date(2026, 9, 1)
    n_dias: int = 16
    roas_bps: tuple[int, ...] = (15000, 12500, 10800, 9000, 6000, 4500)
    custo_base_micros: tuple[int, ...] = (300_000_000, 220_000_000, 180_000_000, 250_000_000, 200_000_000, 150_000_000)
    cambio_brl_por_usd: Fraction = Fraction(5)
    horas_d0: tuple[int, ...] = (8, 14, 20)
    nova: Optional[tuple[int, int]] = None  # (campanha, dia de lançamento)
    nova_preliminar_bps: int = 2500  # fração da verdade nas leituras preliminares da campanha nova
    zero_sintetizado: tuple[tuple[int, int], ...] = ()  # (campanha, dia): v21 sem linha de métrica
    custom_key_trocada: tuple[tuple[int, int], ...] = ()  # (campanha, dia): JoinAds devolve land_uri
    receita_brl: tuple[int, ...] = ()  # campanhas cuja receita chega em BRL (moeda misturada no dia)
    restatement_tardio: tuple[tuple[int, int, int], ...] = ()  # (campanha, dia, fator_bps) relido em D+6

    def ids(self) -> list[str]:
        return [f"2400000{c:04d}" for c in range(len(self.roas_bps))]


class VerdadeProvisoria:
    def __init__(self, espec: EspecProvisoria, custo: dict, receita_brl: dict) -> None:
        self.espec = espec
        self._c = custo
        self._r = receita_brl

    def celulas(self) -> list[tuple[EntidadeCampanha, date]]:
        return sorted(self._c)

    def lucros(self, plano: dict) -> dict:
        getcontext().prec = 40
        out = {}
        for (ent, dia), fator in plano.items():
            if (ent, dia) not in self._c:
                continue
            f = Decimal(fator) / Decimal(BPS)
            c = Decimal(self._c[(ent, dia)]) * f
            r = Decimal(self._r[(ent, dia)]) * (f ** Decimal("0.8") if f > 0 else Decimal(0))
            out[(ent, dia)] = int((r - c).to_integral_value())
        return out


def gerar(espec: EspecProvisoria = EspecProvisoria()) -> FluxoSintetico:
    rng = random.Random(f"{VERSAO_GERADOR}:{espec.seed}")
    ids = espec.ids()
    custo: dict = {}
    receita_brl: dict = {}
    v21: list[dict] = []
    jo: list[dict] = []
    zeros = set(espec.zero_sintetizado)
    trocas = set(espec.custom_key_trocada)
    late = {(c, d): f for c, d, f in espec.restatement_tardio}
    for d_idx in range(espec.n_dias):
        dia = espec.inicio + timedelta(days=d_idx)
        total_usd: dict[int, int] = {1: 0, 2: 0, 3: 0}  # receita USD lida em cada releitura (inclui linha trocada)
        for c, cid in enumerate(ids):
            if espec.nova and espec.nova[0] == c and d_idx < espec.nova[1]:
                continue
            ent = EntidadeCampanha(CONTA_SINTETICA, cid)
            ruido_c = rng.randint(9000, 11000)
            ruido_r = rng.randint(8500, 11500)
            cst = espec.custo_base_micros[c] * ruido_c // BPS // 10_000 * 10_000
            rec = cst * espec.roas_bps[c] // BPS * ruido_r // BPS
            custo[(ent, dia)] = cst
            receita_brl[(ent, dia)] = rec
            em_brl = c in espec.receita_brl
            moeda = "BRL" if em_brl else "USD"
            rec_moeda = rec if em_brl else int(Fraction(rec) / espec.cambio_brl_por_usd)
            rec_moeda = rec_moeda // 10_000 * 10_000
            # custo D0 parcial, D-1 (às vezes inflado), backfill exato
            sem_linha = (c, d_idx) in zeros
            for h in espec.horas_d0:
                col = instante_local(dia, h)
                run = f"d0-{dia.isoformat()}-{h:02d}"
                parc = cst * h // 24 // 10_000 * 10_000
                v21.append(linha_v21(run_id=run, batch_id=f"{run}:{cid}", customer_id=CONTA_SINTETICA, campaign_id=cid,
                                     dia=dia, custo_micros=parc, impressoes=parc // 50_000, cliques=parc // 800_000,
                                     collected_at=col, created_at=col.replace(minute=3), linha_metrica_presente=parc > 0))
            inflado = cst * (BPS + (rng.choice((0, 0, 0, 500, 800)))) // BPS // 10_000 * 10_000
            for desloc, hora, valor in ((1, 4, inflado), (3, 5, cst)):
                col = instante_local(dia + timedelta(days=desloc), hora)
                run = f"d{desloc}-{dia.isoformat()}"
                v21.append(linha_v21(run_id=run, batch_id=f"{run}:{cid}", customer_id=CONTA_SINTETICA, campaign_id=cid,
                                     dia=dia, custo_micros=valor, impressoes=valor // 50_000, cliques=valor // 800_000,
                                     collected_at=col, created_at=col.replace(minute=4),
                                     linha_metrica_presente=not sem_linha))
            # receita JoinAds: preliminar → final; campanha nova começa muito subestimada
            nova_cedo = espec.nova is not None and espec.nova[0] == c and d_idx < espec.nova[1] + 4
            prelim = espec.nova_preliminar_bps if nova_cedo else rng.randint(5500, 8500)
            leituras = [(1, prelim), (2, (prelim + BPS) // 2 if nova_cedo else 9500), (3, BPS)]
            if (c, d_idx) in late:
                leituras.append((6, late[(c, d_idx)]))
            for desloc, frac in leituras:
                if sem_linha:
                    continue  # campanha sem linha no v21 também não tem linha kv (nenhuma observação de receita)
                col = instante_local(dia + timedelta(days=desloc), 8, 15)
                run = f"jo{desloc}-{dia.isoformat()}"
                valor = rec_moeda * frac // BPS // 10_000 * 10_000
                if not em_brl and desloc in total_usd:
                    total_usd[desloc] += valor
                if (c, d_idx) in trocas:
                    jo.append(linha_joinads_kv(run_key=run, batch_key=f"{run}:{cid}", domain=DOMINIO_SINTETICO, dia=dia,
                                               campaign_id=None, custom_key="land_uri", custom_value="/", receita_micros=valor,
                                               collected_at=col, created_at=col.replace(minute=17), currency=moeda))
                else:
                    jo.append(linha_joinads_kv(run_key=run, batch_key=f"{run}:{cid}", domain=DOMINIO_SINTETICO, dia=dia,
                                               campaign_id=cid, custom_key="utm_campaign", custom_value=cid,
                                               receita_micros=valor, collected_at=col, created_at=col.replace(minute=17),
                                               currency=moeda))
        for desloc in (1, 2, 3):  # earnings do domínio = receita com chave + ~2% sem chave, mesma maturação
            col = instante_local(dia + timedelta(days=desloc), 8, 15)
            run = f"jo{desloc}-{dia.isoformat()}"
            jo.append(linha_joinads_earnings(run_key=run, batch_key=f"{run}:earnings", domain=DOMINIO_SINTETICO, dia=dia,
                                             receita_micros=total_usd[desloc] * 102 // 100 // 10_000 * 10_000,
                                             collected_at=col, created_at=col.replace(minute=17)))
    adapt = observacoes_de_linhas_reais(v21, jo)
    cambio = CambioDeclarado("USD", "BRL", espec.cambio_brl_por_usd.numerator, espec.cambio_brl_por_usd.denominator,
                             "declarado:gerador_provisorio")
    return FluxoSintetico(adapt.observacoes, VerdadeProvisoria(espec, custo, receita_brl), (cambio,), espec.nome,
                          espec.seed, {"gerador": VERSAO_GERADOR, "adaptacao": adapt.resumo()})


def cenarios_provisorios() -> dict[str, EspecProvisoria]:
    b = EspecProvisoria()
    return {
        "base": b,
        "campanha_nova": EspecProvisoria(nome="campanha_nova", nova=(1, 7)),
        "zero_sintetizado": EspecProvisoria(nome="zero_sintetizado", zero_sintetizado=tuple((0, d) for d in range(5, 16))),
        "identidade_trocada": EspecProvisoria(nome="identidade_trocada", custom_key_trocada=((4, 9), (2, 10))),
        "moeda_misturada": EspecProvisoria(nome="moeda_misturada", receita_brl=(3,)),
        "restatement_tardio": EspecProvisoria(nome="restatement_tardio", restatement_tardio=((2, 8, 5000), (0, 9, 4000))),
    }


def preparar(nome: str = "base", *, passo_horas: int = 1, dia_inicial: int = 5, hora_inicial: int = 0, **sobrescritas):
    """(FluxoSintetico, cortes, ConfigShadow) prontos para replay — atalho de testes e do script."""
    from dataclasses import replace

    from .fluxo import cortes_regulares
    from .motor import ConfigShadow
    from .snapshot import ConfigCorte

    espec = cenarios_provisorios()[nome]
    if sobrescritas:
        espec = replace(espec, **sobrescritas)
    fs = gerar(espec)
    cortes = cortes_regulares(instante_local(espec.inicio + timedelta(days=dia_inicial), hora_inicial),
                              instante_local(espec.inicio + timedelta(days=espec.n_dias - 1), 0), timedelta(hours=passo_horas))
    return fs, cortes, ConfigShadow(ConfigCorte(cambios=fs.cambios))
