"""Drift de distribuição de métrica por campanha: KS de duas amostras + filtro de efeito robusto.

Decisão: `deriva = p_KS < alfa  E  |Δ mediana| / escala_robusta(base) >= efeito_minimo`.
- O KS é livre de distribuição; com empates (zeros, valores discretos) o p-valor exato é
  conservador, logo a taxa de falso alarme por teste fica <= alfa em dado i.i.d. estacionário.
- O filtro de efeito (mediana/MAD) só REMOVE alarmes; protege contra diferenças minúsculas mas
  "significativas" e é a evidência legível no achado.
- Autocorrelação (custo diário é persistente) infla o falso alarme do KS cru, porque as amostras
  deixam de ser independentes (medido: AR(1) phi=0,6 -> ~9% com alfa=1%). Correção padrão
  (`corrigir_autocorrelacao=True`): estima a autocorrelação lag-1 dos POSTOS da base (só da base,
  para a quebra não se disfarçar de persistência), reduz o tamanho efetivo n·(1-ρ)/(1+ρ) e usa o
  p-valor assintótico de Kolmogorov com esse n efetivo (o maior dos dois p-valores). Custa poder;
  a troca está medida em `tests/.../test_qualidade_deriva.py` e no doc 09.
- `None` é descartado da amostra (null não é zero) e contado na evidência.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np
from scipy import stats

from .modelo import Achado, Severidade

ALFA_PADRAO = 0.01
EFEITO_MINIMO_PADRAO = 0.5
MIN_BASE = 14
MIN_RECENTE = 7


def escala_robusta(x: np.ndarray) -> float:
    """1.4826·MAD; se MAD = 0 (muitos empates), 1.2533·média do desvio absoluto à mediana;
    se ainda 0 (base constante), 0.0 — o chamador trata."""
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    if mad > 0:
        return 1.4826 * mad
    mean_ad = float(np.mean(np.abs(x - med)))
    return 1.2533 * mean_ad


def autocorrelacao_postos(x: np.ndarray) -> float:
    """Autocorrelação lag-1 dos postos (robusta a cauda e a empates)."""
    if len(x) < 3:
        return 0.0
    r = stats.rankdata(x)
    r = r - r.mean()
    d = float((r * r).sum())
    return 0.0 if d == 0 else float((r[1:] * r[:-1]).sum() / d)


@dataclass(frozen=True)
class ResultadoDeriva:
    n_base: int
    n_recente: int
    descartados_nulos: int
    estatistica_ks: float | None
    p_valor: float | None
    efeito_robusto: float | None  # |Δ mediana| / escala_robusta(base); inf se base constante e mediana mudou
    rho_base: float | None
    deriva: bool
    motivo: str  # deriva | estavel | amostra_insuficiente


def detectar_deriva(
    base: Sequence[float | None],
    recente: Sequence[float | None],
    *,
    alfa: float = ALFA_PADRAO,
    efeito_minimo: float = EFEITO_MINIMO_PADRAO,
    min_base: int = MIN_BASE,
    min_recente: int = MIN_RECENTE,
    corrigir_autocorrelacao: bool = True,
) -> ResultadoDeriva:
    nb = [float(v) for v in base if v is not None and not (isinstance(v, float) and math.isnan(v))]
    nr = [float(v) for v in recente if v is not None and not (isinstance(v, float) and math.isnan(v))]
    descartados = (len(base) - len(nb)) + (len(recente) - len(nr))
    if len(nb) < min_base or len(nr) < min_recente:
        return ResultadoDeriva(len(nb), len(nr), descartados, None, None, None, None, False,
                              "amostra_insuficiente")
    b, r = np.asarray(nb), np.asarray(nr)
    ks = stats.ks_2samp(b, r, alternative="two-sided", method="auto")
    p = float(ks.pvalue)
    rho = min(max(autocorrelacao_postos(b), 0.0), 0.9)
    if corrigir_autocorrelacao and rho > 0:
        f = (1 - rho) / (1 + rho)
        n1, n2 = len(b) * f, len(r) * f
        p = max(p, float(stats.kstwobign.sf(float(ks.statistic) * math.sqrt(n1 * n2 / (n1 + n2)))))
    delta = abs(float(np.median(r)) - float(np.median(b)))
    escala = escala_robusta(b)
    if escala > 0:
        efeito = delta / escala
    else:
        efeito = 0.0 if delta == 0 else math.inf
    deriva = bool(p < alfa and efeito >= efeito_minimo)
    return ResultadoDeriva(len(nb), len(nr), descartados, float(ks.statistic), p,
                           efeito, rho, deriva, "deriva" if deriva else "estavel")


def checar_deriva(
    series: Mapping[str, Sequence[float | None]],
    *,
    fonte: str = "google_ads",
    grao: str = "campaign_day",
    metrica: str = "cost_micros",
    janela_recente: int = 7,
    janela_base: int = 28,
    alfa: float = ALFA_PADRAO,
    efeito_minimo: float = EFEITO_MINIMO_PADRAO,
    corrigir_autocorrelacao: bool = True,
) -> list[Achado]:
    """`series[chave]` em ordem temporal (mais antigo primeiro). Compara os últimos `janela_recente`
    pontos com os `janela_base` anteriores. Sem correção múltipla: o alfa é por série e a taxa global
    de falso alarme esperada é `alfa × n_series` (registrado na evidência)."""
    achados = []
    n_series = len(series)
    for chave in sorted(series):
        valores = list(series[chave])
        recente = valores[-janela_recente:]
        base = valores[-(janela_recente + janela_base):-janela_recente]
        res = detectar_deriva(base, recente, alfa=alfa, efeito_minimo=efeito_minimo,
                              corrigir_autocorrelacao=corrigir_autocorrelacao)
        if not res.deriva:
            continue
        achados.append(
            Achado(
                regra="deriva_distribuicao",
                severidade=Severidade.AVISO,
                fonte=fonte,
                grao=grao,
                janela=(None, None),
                chave=chave,
                evidencia={"metrica": metrica, "n_base": res.n_base, "n_recente": res.n_recente,
                           "ks": round(res.estatistica_ks, 4), "p_valor": res.p_valor,
                           "efeito_robusto": None if math.isinf(res.efeito_robusto) else round(res.efeito_robusto, 3),
                           "rho_base": round(res.rho_base, 3), "corrigido": corrigir_autocorrelacao,
                           "alfa": alfa, "falsos_alarmes_esperados": round(alfa * n_series, 3),
                           "descartados_nulos": res.descartados_nulos},
                mensagem=f"{chave}: distribuição de {metrica} mudou (KS p={res.p_valor:.2g}, efeito {res.efeito_robusto:.2f})",
            )
        )
    return achados


# --------------------------------------------------------------------------- calibração (medida)


def _serie_sintetica(rng: np.random.Generator, n: int, phi: float, p_zero: float,
                     mu: float = 10.0, sigma: float = 0.5) -> np.ndarray:
    """Custo diário sintético: log-normal com AR(1) no log (phi) e zeros (dias sem entrega)."""
    eps = rng.normal(0.0, sigma * math.sqrt(1 - phi**2), n)
    z = np.empty(n)
    z[0] = rng.normal(0.0, sigma)
    for t in range(1, n):
        z[t] = phi * z[t - 1] + eps[t]
    x = np.exp(mu + z)
    x[rng.random(n) < p_zero] = 0.0
    return np.round(x)


def medir_falso_alarme(
    *,
    n_series: int = 2000,
    seed: int = 20261016,
    phi: float = 0.0,
    p_zero: float = 0.05,
    janela_base: int = 28,
    janela_recente: int = 7,
    alfa: float = ALFA_PADRAO,
    efeito_minimo: float = EFEITO_MINIMO_PADRAO,
    corrigir_autocorrelacao: bool = True,
) -> dict:
    """Taxa de alarme em séries ESTACIONÁRIAS (nenhuma deriva verdadeira)."""
    rng = np.random.default_rng(seed)
    alarmes = 0
    for _ in range(n_series):
        x = _serie_sintetica(rng, janela_base + janela_recente, phi, p_zero)
        res = detectar_deriva(x[:janela_base], x[janela_base:], alfa=alfa, efeito_minimo=efeito_minimo,
                              corrigir_autocorrelacao=corrigir_autocorrelacao)
        alarmes += res.deriva
    return {"n_series": n_series, "seed": seed, "phi": phi, "p_zero": p_zero, "alfa": alfa,
            "efeito_minimo": efeito_minimo, "corrigido": corrigir_autocorrelacao, "alarmes": alarmes, "taxa": alarmes / n_series}


def medir_poder(
    *,
    multiplicador: float,
    n_series: int = 1000,
    seed: int = 20261017,
    phi: float = 0.0,
    p_zero: float = 0.05,
    janela_base: int = 28,
    janela_recente: int = 7,
    alfa: float = ALFA_PADRAO,
    efeito_minimo: float = EFEITO_MINIMO_PADRAO,
    corrigir_autocorrelacao: bool = True,
) -> dict:
    """Taxa de detecção quando a janela recente é multiplicada por `multiplicador` (quebra injetada)."""
    rng = np.random.default_rng(seed)
    detect = 0
    for _ in range(n_series):
        x = _serie_sintetica(rng, janela_base + janela_recente, phi, p_zero)
        x[janela_base:] = np.round(x[janela_base:] * multiplicador)
        res = detectar_deriva(x[:janela_base], x[janela_base:], alfa=alfa, efeito_minimo=efeito_minimo,
                              corrigir_autocorrelacao=corrigir_autocorrelacao)
        detect += res.deriva
    return {"n_series": n_series, "seed": seed, "multiplicador": multiplicador, "phi": phi,
            "alfa": alfa, "corrigido": corrigir_autocorrelacao, "detectados": detect, "poder": detect / n_series}


def series_por_chave(pares: Iterable[tuple[str, float | None]]) -> dict[str, list[float | None]]:
    """Agrupa (chave, valor) em ordem de chegada — utilitário para montar `checar_deriva`."""
    saida: dict[str, list[float | None]] = {}
    for k, v in pares:
        saida.setdefault(k, []).append(v)
    return saida
