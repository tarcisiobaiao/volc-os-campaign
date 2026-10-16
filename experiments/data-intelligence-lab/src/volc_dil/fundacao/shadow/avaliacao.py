"""Avaliação das decisões shadow contra a VERDADE de um gerador (testado com sintético, não eficácia).

Shadow é malha ABERTA: nenhuma proposta é executada, o mundo segue com a verba atual. Por isso:

- com gerador (provisório ou simulador da thread E), o lucro de cada política é CONTRAFACTUAL:
  a verdade responde "qual teria sido o lucro da campanha c no dia d com fator de verba f";
- com dado real, só duas coisas são mensuráveis sem modelo: o lucro realizado de `manter` (o que
  de fato aconteceu) e o contrafactual de `pausar` (= 0, sob a hipótese de não haver carryover);
  `reduzir`/`aumentar` exigem modelo de resposta ou experimento — isso fica explícito no ledger.

Métricas por política (sobre as decisões do corte diário `hora_decisao`, aplicadas ao dia seguinte):
lucro contrafactual total; diferença para `manter` e `equal`; regret contra o oráculo por célula
(máximo do menu de fatores, incluindo o da própria política); drawdown máximo da diferença acumulada
para `manter`; cortes errados (corte que perdeu dinheiro contra manter) e, deles, por sinal imaturo;
propostas bloqueadas; estabilidade entre cortes adjacentes (fração de trocas de ação por campanha);
custo computacional (fora da parte determinística).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional, Protocol, Sequence
from zoneinfo import ZoneInfo

from volc_dil.contracts.money import Dinheiro

from ..observacao.modelo import Observacao
from .fluxo import FluxoIndexado
from .ledger import LedgerShadow
from .motor import ConfigShadow, ResultadoReplay
from .snapshot import STATUS_COM_VALOR_FECHADO, construir_snapshot
from .tipos import ACOES_DE_CORTE, BPS, EntidadeCampanha, PropostaShadow


class Verdade(Protocol):
    def celulas(self) -> list[tuple[EntidadeCampanha, date]]: ...

    def lucros(self, plano: dict) -> dict:
        """{(entidade, dia): fator_bps} → {(entidade, dia): lucro em micros BRL}. Só para avaliação."""
        ...


@dataclass(frozen=True)
class FluxoSintetico:
    observacoes: tuple[Observacao, ...]
    verdade: Verdade
    cambios: tuple
    nome: str
    seed: int
    meta: dict = field(default_factory=dict)


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def plano_da_politica(resultado: ResultadoReplay, politica: str, *, hora_decisao: int, fuso: str,
                      horizonte_dias: int = 1) -> dict[tuple[EntidadeCampanha, date], PropostaShadow]:
    """Propostas do corte diário `hora_decisao` (hora local), aplicadas aos `horizonte_dias` seguintes."""
    zona = ZoneInfo(fuso)
    plano: dict = {}
    for d in resultado.da_politica(politica):
        t = _dt(d.as_of).astimezone(zona)
        if t.hour != hora_decisao or t.minute != 0:
            continue
        for p in d.decisao.propostas:
            for k in range(1, horizonte_dias + 1):
                plano[(p.entidade, t.date() + timedelta(days=k))] = p
    return plano


def _drawdown(serie: list[int]) -> int:
    pico = acum = 0
    pior = 0
    for x in serie:
        acum += x
        pico = max(pico, acum)
        pior = max(pior, pico - acum)
    return pior


def estabilidade(resultado: ResultadoReplay, politica: str) -> dict:
    ultima: dict = {}
    trocas = pares = 0
    for d in resultado.da_politica(politica):
        for p in d.decisao.propostas:
            a = (p.acao.value, p.fator_bps, p.bloqueada)
            if p.entidade in ultima:
                pares += 1
                trocas += ultima[p.entidade] != a
            ultima[p.entidade] = a
    return {"trocas": trocas, "pares": pares, "fracao_trocas": f"{trocas}/{pares}" if pares else None}


def _imaturo(p: PropostaShadow) -> bool:
    ev = p.evidencia_dict()
    idade = ev.get("horas_desde_primeiro_custo")
    return bool(ev.get("dias_imaturos_usados")) or (idade is not None and idade < 72)


def avaliar(resultado: ResultadoReplay, verdade: Verdade, *, hora_decisao: int = 7, fuso: str = "America/Sao_Paulo",
            menu_bps: Sequence[int] = (BPS, 7000, 0), horizonte_dias: int = 1) -> dict:
    planos = {pol: plano_da_politica(resultado, pol, hora_decisao=hora_decisao, fuso=fuso, horizonte_dias=horizonte_dias)
              for pol in resultado.politicas}
    universo = set(verdade.celulas())
    celulas = sorted({c for pl in planos.values() for c in pl} & universo)
    base = verdade.lucros({c: BPS for c in celulas})
    menu = {f: verdade.lucros({c: f for c in celulas}) for f in menu_bps}
    saida: dict = {"n_celulas": len(celulas), "hora_decisao": hora_decisao, "horizonte_dias": horizonte_dias,
                   "menu_bps": list(menu_bps), "lucro_manter_micros": sum(base.values()), "politicas": {}}
    for pol, plano in planos.items():
        fatores = {c: (plano[c].fator_efetivo_bps if c in plano else BPS) for c in celulas}
        luc = verdade.lucros(fatores)
        oraculo = 0
        for c in celulas:
            cand = [menu[f][c] for f in menu_bps] + [luc[c]]
            oraculo += max(cand)
        por_dia: dict = defaultdict(int)
        errados = errados_imaturos = cortes = bloqueadas = mudancas = 0
        for c in celulas:
            por_dia[c[1]] += luc[c] - base[c]
            p = plano.get(c)
            if p is None:
                continue
            bloqueadas += p.bloqueada
            if p.fator_efetivo_bps != BPS:
                mudancas += 1
            if p.acao in ACOES_DE_CORTE and not p.bloqueada:
                cortes += 1
                if luc[c] < base[c]:
                    errados += 1
                    errados_imaturos += _imaturo(p)
        acoes: dict = defaultdict(int)
        for d in resultado.da_politica(pol):
            for p in d.decisao.propostas:
                acoes[p.acao.value] += 1
        total = sum(luc.values())
        saida["politicas"][pol] = {
            "lucro_micros": total, "vs_manter_micros": total - saida["lucro_manter_micros"],
            "regret_vs_oraculo_micros": oraculo - total, "drawdown_max_vs_manter_micros": _drawdown([por_dia[d] for d in sorted(por_dia)]),
            "celulas_com_mudanca_de_verba": mudancas, "cortes_executaveis_em_tese": cortes, "cortes_errados": errados,
            "cortes_errados_por_sinal_imaturo": errados_imaturos, "propostas_bloqueadas_no_corte_diario": bloqueadas,
            "acoes_em_todos_os_cortes": dict(sorted(acoes.items())), "estabilidade": estabilidade(resultado, pol),
        }
    if "equal" in saida["politicas"]:
        eq = saida["politicas"]["equal"]["lucro_micros"]
        for v in saida["politicas"].values():
            v["vs_equal_micros"] = v["lucro_micros"] - eq
    saida["natureza"] = "testado_com_sintetico"
    return saida


# --------------------------------------------------------------------------- resultado maduro no ledger
def registrar_resultados_maduros(ledger: LedgerShadow, resultado: ResultadoReplay, fluxo: FluxoIndexado,
                                 config: ConfigShadow, *, hora_decisao: int = 7, k_dias: int = 4,
                                 verdade: Optional[Verdade] = None) -> int:
    """Depois da maturidade (D+1+k), grava para cada decisão diária o resultado observado do dia aplicado.

    `lucro_realizado_manter`: custo e receita maduros observados (o mundo não foi tocado pelo shadow);
    `contrafactual_pausa = 0` (identificável sem modelo, sob ausência de carryover). Com `verdade`,
    acrescenta o lucro contrafactual verdadeiro do fator proposto (só gerador sintético).
    """
    zona = ZoneInfo(config.corte.fuso)
    hashes = {(e["as_of"], e["politica"]): e["hash"] for e in ledger.entradas if e["tipo"] == "decisao"}
    fim = fluxo.ultimo_available_at()
    snaps: dict = {}
    n = 0
    for d in resultado.decisoes:
        t = _dt(d.as_of)
        local = t.astimezone(zona)
        if local.hour != hora_decisao or local.minute != 0 or (d.as_of, d.politica) not in hashes:
            continue
        t_mat = t + timedelta(days=1 + k_dias)
        if fim is None or t_mat > fim:
            continue
        if t_mat not in snaps:
            snaps[t_mat] = construir_snapshot(fluxo, t_mat, config.corte, rotulo="maturidade")
        s = snaps[t_mat]
        dia_aplicado = local.date() + timedelta(days=1)
        linhas = []
        for p in d.decisao.propostas:
            f = s.fato(p.entidade, dia_aplicado)
            item: dict = {"entidade": [p.entidade.customer_id, p.entidade.campaign_id], "dia": dia_aplicado.isoformat(),
                          "acao": p.acao.value, "fator_efetivo_bps": p.fator_efetivo_bps, "contrafactual_pausa_micros": 0}
            if (f is not None and f.custo_status in STATUS_COM_VALOR_FECHADO and f.receita_status in STATUS_COM_VALOR_FECHADO
                    and isinstance(f.custo.valor, Dinheiro) and isinstance(f.receita.valor, Dinheiro)):
                taxa = s.cambio(f.receita.valor.moeda, f.custo.valor.moeda)
                if taxa is not None:
                    rec = f.receita.valor.micros * taxa.numerator // taxa.denominator
                    item["lucro_realizado_manter_micros"] = rec - f.custo.valor.micros
                    item["ganho_se_pausasse_micros"] = -(rec - f.custo.valor.micros)
                else:
                    item["lucro_realizado_manter_micros"] = None
                    item["pendencia"] = "moeda_sem_cambio"
            else:
                item["lucro_realizado_manter_micros"] = None
                item["pendencia"] = "sem custo e receita maduros observados no dia aplicado"
            if verdade is not None:
                cel = (p.entidade, dia_aplicado)
                v = verdade.lucros({cel: p.fator_efetivo_bps})
                m = verdade.lucros({cel: BPS})
                if cel in v:
                    item["verdade_lucro_fator_proposto_micros"] = v[cel]
                    item["verdade_lucro_manter_micros"] = m[cel]
            linhas.append(item)
        ledger.registrar_resultado(ref_hash=hashes[(d.as_of, d.politica)], as_of_maduro=s.as_of_iso, k_dias=k_dias,
                                   resultado={"politica": d.politica, "fingerprint_maturidade": s.fingerprint,
                                              "itens": linhas, "natureza": "sintetico" if verdade is not None else "observado"})
        n += 1
    return n
