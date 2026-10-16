"""Maturação (nowcast) de custo D0 e receita JoinAds a partir de registros ``as_of``.

Reusa o Stat Lab herdado (``volc_dil.statlab.maturacao``): ``fatores_maturacao`` (chain-ladder por
coortes maduras / link ratio), ``motivo_guarda`` + ``ConfigNowcast`` (guarda única que devolve
``insuficiente`` em vez de número) e ``intervalo_razao_empirica``. Este módulo acrescenta:

- ``triangulo_de_tabela``: triângulo coorte(dia) × idade(dias) montado com cortes ``as_of`` reais
  sobre os registros (não sobre a verdade), agregado ou por campanha;
- ``nowcast``: chain-ladder herdado, Bornhuetter-Ferguson e fator fixo (congelado numa janela de
  calibração), com a MESMA guarda;
- ``monitor_maturacao``: CUSUM sobre a razão de ligação (link ratio) das coortes recentes contra as
  coortes da janela de referência — a correção do "degrada sem avisar" herdado: quando dispara, o
  nowcast passa a usar só coortes pós-mudança e devolve ``insuficiente`` até haver base;
- ``curva_intradiaria`` / ``nowcast_intradiario``: fração do valor final conhecida em cada passada
  intradiária (ex.: D0 do Google com 16 runs/dia), razão de somas sobre coortes maduras.

Todos os limiares (janela, maturidade mínima, k e h do CUSUM) são parâmetros obrigatórios.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

import numpy as np

from volc_dil.statlab.maturacao import (
    ConfigNowcast,
    fatores_maturacao,
    intervalo_razao_empirica,
    motivo_guarda,
)

from .base import Achado, ResultadoInsuficiente
from .dados import TabelaVersoes, instante_local

METODOS_NOWCAST = ("chain_ladder", "bornhuetter_ferguson", "fator_fixo", "observado")


# ---------------------------------------------------------------------------
# triângulo a partir de registros
# ---------------------------------------------------------------------------

def paineis_diarios(tabela: TabelaVersoes, calendario, *, hora_corte: float, n_cortes: int) -> np.ndarray:
    """(K, E, D): painel ``as_of`` no instante local ``dia k + hora_corte`` para k = 0..K-1."""
    return np.stack([tabela.painel(instante_local(calendario, k, hora_corte)) for k in range(n_cortes)])


def triangulo_de_tabela(tabela: TabelaVersoes, calendario, *, hora_corte: float, idade_max: int,
                        paineis: Optional[np.ndarray] = None) -> dict[str, np.ndarray]:
    """Triângulo ACUMULADO conhecido: ``por_campanha[e, d, a]`` = valor vigente do fato (e, d) no corte
    do dia ``d + a`` (hora local ``hora_corte``); ``agregado[d, a]`` = soma sobre as campanhas com valor
    (NaN se nenhuma). Células cujo corte cai depois do último dia do calendário + idade_max ficam NaN.
    O chamador aplica o ``as_of`` (``c + a <= as_of``) — o herdado também mascara por segurança."""
    E, D = tabela.forma
    K = D + idade_max
    P = paineis if paineis is not None else paineis_diarios(tabela, calendario, hora_corte=hora_corte, n_cortes=K)
    por = np.full((E, D, idade_max + 1), np.nan)
    for a in range(idade_max + 1):
        ks = np.arange(D) + a
        ok = ks < P.shape[0]
        por[:, ok, a] = P[ks[ok], :, np.arange(D)[ok]].T
    with np.errstate(invalid="ignore"):
        tem = np.isfinite(por).any(axis=0)
        agg = np.where(tem, np.nansum(por, axis=0), np.nan)
    n = np.isfinite(por).sum(axis=0)
    return {"por_campanha": por, "agregado": agg, "n_campanhas": n}


# ---------------------------------------------------------------------------
# monitor de regime de maturação (link ratio + CUSUM robusto)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConfigMonitor:
    """Parâmetros do monitor (obrigatórios; nenhum default operacional)."""

    idade: int            # monitora a ligação idade -> idade + 1
    janela_ref: int       # nº de coortes de referência (as mais antigas da janela)
    k: float              # folga do CUSUM em unidades de desvio robusto
    h: float              # limiar do CUSUM
    min_ref: int = 5
    escala: str = "mad"   # "mad" (robusta) | "max_mad_dp" (conservadora: MAD subestima com cauda pesada e ref curta)


def _razao_ligacao(tri: np.ndarray, as_of: int, idade: int) -> np.ndarray:
    C = tri.shape[0]
    c = np.arange(C)
    ok = c + idade + 1 <= as_of
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(ok, tri[:, idade + 1] / tri[:, idade], np.nan)
    return np.where(np.isfinite(r) & (r > 0), r, np.nan)


def _ponto_mle(lr: np.ndarray, idx: np.ndarray, alarme: int, inicio_excursao: Optional[int]) -> int:
    """Ponto de mudança por máxima verossimilhança gaussiana de dois segmentos (média antes × depois),
    procurado entre o início da excursão do CUSUM (que tende a começar cedo demais) e o alarme."""
    seg = idx[idx <= alarme]
    v = lr[seg]
    lo = int(np.searchsorted(seg, inicio_excursao)) if inicio_excursao is not None else 1
    melhor, custo = int(seg[max(lo, 1)]), np.inf
    for j in range(max(lo, 1), seg.size):
        a, b = v[:j], v[j:]
        c = ((a - a.mean()) ** 2).sum() + ((b - b.mean()) ** 2).sum()
        if c < custo:
            melhor, custo = int(seg[j]), c
    return melhor


def monitor_maturacao(tri: np.ndarray, as_of: int, cfg: ConfigMonitor, *, inicio_ref: int = 0) -> Achado:
    """CUSUM bilateral sobre log(razão de ligação) das coortes posteriores à referência.

    Referência = as ``janela_ref`` primeiras coortes com razão definida a partir de ``inicio_ref``;
    padronização por mediana e MAD (robusta). Só usa células com ``c + a <= as_of``."""
    r = _razao_ligacao(tri, as_of, cfg.idade)
    lr = np.log(r)
    idx = np.nonzero(np.isfinite(lr) & (np.arange(lr.size) >= inicio_ref))[0]
    if idx.size < cfg.min_ref + 1:
        return Achado("sem_achado", False, "cusum_link_ratio", detalhes={"motivo": "coortes_insuficientes",
                                                                          "n": int(idx.size)})
    ref = idx[:cfg.janela_ref]
    if ref.size < cfg.min_ref:
        return Achado("sem_achado", False, "cusum_link_ratio", detalhes={"motivo": "referencia_insuficiente"})
    med = float(np.median(lr[ref]))
    mad = float(np.median(np.abs(lr[ref] - med))) * 1.4826
    if cfg.escala == "max_mad_dp":
        mad = max(mad, float(np.std(lr[ref], ddof=1)))
    elif cfg.escala != "mad":
        raise ValueError("escala: mad | max_mad_dp")
    escala = max(mad, 1e-6 * max(abs(med), 1.0), 1e-9)
    sp = sn = 0.0
    inicio_p = inicio_n = None
    for c in idx[ref.size:]:
        z = (lr[c] - med) / escala
        sp_novo = max(0.0, sp + z - cfg.k)
        sn_novo = max(0.0, sn - z - cfg.k)
        inicio_p = (c if sp == 0.0 else inicio_p) if sp_novo > 0 else None
        inicio_n = (c if sn == 0.0 else inicio_n) if sn_novo > 0 else None
        sp, sn = sp_novo, sn_novo
        if sp > cfg.h or sn > cfg.h:
            ponto = _ponto_mle(lr, idx, int(c), inicio_p if sp > cfg.h else inicio_n)
            return Achado("mudanca_maturacao", True, "cusum_link_ratio", indice=int(c), ponto_estimado=int(ponto),
                          estatistica=float(max(sp, sn)), limiar=cfg.h,
                          detalhes={"idade": cfg.idade, "mediana_ref": med, "escala_ref": escala,
                                    "direcao": "mais_lenta" if sp > cfg.h else "mais_rapida",  # razão de ligação maior = chega mais tarde
                                    "coortes_ref": [int(ref[0]), int(ref[-1])]})
    return Achado("sem_achado", False, "cusum_link_ratio", estatistica=float(max(sp, sn)), limiar=cfg.h,
                  detalhes={"idade": cfg.idade, "coortes_ref": [int(ref[0]), int(ref[-1])]})


def regime_vigente(tri: np.ndarray, as_of: int, cfgs: ConfigMonitor | Sequence[ConfigMonitor]) -> Achado:
    """Segmentação sem estado: roda os monitores (uma ou mais idades) a partir da coorte 0; a cada
    detecção, recomeça com a referência no ponto estimado, até não haver mais mudança. Devolve o achado
    da ÚLTIMA mudança (``ponto_estimado`` = início do regime vigente) ou ``sem_achado``. Por ser sem
    estado, a mesma chamada no dia seguinte reencontra a mudança (a decisão é persistente)."""
    lista = [cfgs] if isinstance(cfgs, ConfigMonitor) else list(cfgs)
    inicio, ultimo, pontos = 0, None, []
    for _ in range(tri.shape[0]):
        achados = [monitor_maturacao(tri, as_of, c, inicio_ref=inicio) for c in lista]
        det = [a for a in achados if a.detectado]
        if not det:
            break
        primeiro = min(det, key=lambda a: (a.indice, a.ponto_estimado))
        if primeiro.ponto_estimado <= inicio:
            break
        ultimo = primeiro
        inicio = int(primeiro.ponto_estimado)
        pontos.append(inicio)
    if ultimo is None:
        return Achado("sem_achado", False, "cusum_link_ratio", detalhes={"idades": [c.idade for c in lista]})
    return Achado("mudanca_maturacao", True, "cusum_link_ratio", indice=ultimo.indice,
                  ponto_estimado=ultimo.ponto_estimado, estatistica=ultimo.estatistica, limiar=ultimo.limiar,
                  detalhes={**dict(ultimo.detalhes), "pontos": pontos, "idades": [c.idade for c in lista]})


# ---------------------------------------------------------------------------
# nowcast: chain-ladder herdado, BF, fator fixo, com a guarda herdada
# ---------------------------------------------------------------------------

def _prior_final(tri: np.ndarray, as_of: int, idade_final: int, janela: int, inicio: int) -> float:
    ultima = as_of - idade_final
    cs = np.arange(max(inicio, ultima - janela + 1), ultima + 1)
    cs = cs[(cs >= 0) & (cs < tri.shape[0])]
    v = tri[cs, idade_final] if cs.size else np.array([])
    v = v[np.isfinite(v)]
    return float(v.mean()) if v.size else float("nan")


def nowcast(tri: np.ndarray, as_of: int, coorte: int, cfg: ConfigNowcast, *, metodo: str = "chain_ladder",
            fator_fixo: Optional[np.ndarray] = None, prior_final: Optional[float] = None,
            monitor: ConfigMonitor | Sequence[ConfigMonitor] | None = None,
            regime: Optional[Achado] = None) -> dict[str, Any] | ResultadoInsuficiente:
    """Nowcast do valor final da coorte ``coorte`` no ``as_of`` (inteiros em dias).

    ``metodo``: ``chain_ladder`` (obs/m(a), herdado), ``bornhuetter_ferguson`` (obs + (1-m(a))·prior,
    prior = média dos finais maduros da janela, ou ``prior_final``), ``fator_fixo`` (obs/f(a) com
    ``fator_fixo`` congelado pelo chamador), ``observado`` (anti-baseline: obs como se fosse final).
    Com ``monitor`` (um ou vários) ou ``regime`` já calculado por ``regime_vigente``: o fator usa só as
    coortes do MESMO segmento de regime da coorte pedida (o herdado exclui coortes com célula NaN);
    coorte do regime novo → ``insuficiente`` (motivo ``regime_de_maturacao_mudou``) até haver
    ``min_coortes`` coortes pós-mudança maduras; coorte do regime antigo segue com o fator antigo."""
    if metodo not in METODOS_NOWCAST:
        raise ValueError(f"método desconhecido: {metodo}")
    C, A1 = tri.shape
    A = A1 - 1
    if coorte < 0 or coorte > as_of or coorte >= C:
        return ResultadoInsuficiente("coorte_inexistente_no_as_of", {"coorte": coorte, "as_of": as_of})
    idade = min(as_of - coorte, A)
    obs = tri[coorte, idade]
    if not np.isfinite(obs):
        return ResultadoInsuficiente("observacao_ausente", {"coorte": coorte, "idade": idade})
    if idade == A or metodo == "observado":
        return {"status": "maduro" if idade == A else "estimado", "estimativa": float(obs), "observado": float(obs),
                "fator": 1.0, "idade": idade, "metodo": metodo, "intervalo": None, "regime": None}
    base = tri
    achado = regime
    inicio = 0
    if achado is None and monitor is not None:
        achado = regime_vigente(tri, as_of, monitor)
    if achado is not None and achado.detectado:
        pontos = sorted(int(p) for p in achado.detalhes.get("pontos", [achado.ponto_estimado]))
        cortes = [0] + pontos + [C]
        j = max(i for i in range(len(cortes) - 1) if cortes[i] <= coorte)
        inicio, fim = cortes[j], cortes[j + 1]
        base = tri.copy()
        base[:inicio] = np.nan  # coortes de outro regime saem do fator (o herdado as exclui)
        base[fim:] = np.nan
    if metodo == "fator_fixo":
        if fator_fixo is None:
            raise ValueError("fator_fixo exige o vetor de fatores congelado")
        m = float(fator_fixo[idade])
        n = cfg.min_coortes  # o fator fixo não tem base viva: a guarda só checa maturidade mínima
    else:
        fat = fatores_maturacao(base, as_of, janela_coortes=cfg.janela_coortes, metodo=cfg.metodo)
        m = float(fat["fator"][idade])
        n = int(fat["n_coortes"][idade])
    motivo = str(motivo_guarda(m, n, obs, cfg)[0])
    regime = achado.como_dict() if achado is not None else None
    if motivo:
        if inicio > 0 and motivo in ("coortes_maduras_insuficientes", "fator_indefinido"):
            motivo = "regime_de_maturacao_mudou"
        return ResultadoInsuficiente(motivo, {"idade": idade, "n_coortes": n, "fator": m if np.isfinite(m) else None,
                                              "regime": regime})
    if metodo == "bornhuetter_ferguson":
        pf = prior_final if prior_final is not None else _prior_final(base, as_of, A, cfg.janela_coortes, inicio)
        if not np.isfinite(pf):
            return ResultadoInsuficiente("prior_indefinido", {"idade": idade})
        est = float(obs + (1.0 - m) * pf)
    else:
        est = float(obs / m)
    out: dict[str, Any] = {"status": "estimado", "estimativa": est, "observado": float(obs), "fator": m,
                           "idade": idade, "n_coortes": n, "metodo": metodo, "intervalo": None, "regime": regime}
    if cfg.nivel_intervalo is not None and metodo != "fator_fixo":
        lo, hi = intervalo_razao_empirica(base, as_of, idade, float(obs), cfg)
        if lo is not None and metodo == "bornhuetter_ferguson":
            # mesma largura relativa em torno da estimativa BF (aproximação declarada)
            lo, hi = float(est * lo / (obs / m)), float(est * hi / (obs / m))
        out["intervalo"] = [lo, hi]
    return out


def maturar(tri: np.ndarray, as_of: int, cfg: ConfigNowcast, *, metodo: str = "chain_ladder",
            coortes: Optional[Sequence[int]] = None, **kw: Any) -> list[dict[str, Any] | ResultadoInsuficiente]:
    """API para o shadow: nowcast de várias coortes no mesmo ``as_of`` (default: as A mais recentes)."""
    A = tri.shape[1] - 1
    cs = list(coortes) if coortes is not None else [c for c in range(as_of - A + 1, as_of + 1) if 0 <= c < tri.shape[0]]
    return [nowcast(tri, as_of, c, cfg, metodo=metodo, **kw) for c in cs]


def fator_congelado(tri: np.ndarray, as_of_calibracao: int, *, janela_coortes: int) -> np.ndarray:
    """Fator chain-ladder medido UMA vez (as_of de calibração) e nunca mais atualizado: o "fator fixo"
    que uma regra codificada usaria (ex.: "D0 vale 85% do final")."""
    return fatores_maturacao(tri, as_of_calibracao, janela_coortes=janela_coortes)["fator"]


# ---------------------------------------------------------------------------
# maturação intradiária (custo D0 multiversão)
# ---------------------------------------------------------------------------

def paineis_intradiarios(tabela: TabelaVersoes, calendario, *, horas: Sequence[float], folga_s: int = 900
                         ) -> np.ndarray:
    """(H, E, D): para cada hora local h e dia d, o valor vigente em ``dia d + h`` (+ folga) — o que
    um consumidor via naquela hora sobre o próprio dia."""
    E, D = tabela.forma
    out = np.full((len(horas), E, D), np.nan)
    for j, h in enumerate(horas):
        for d in range(D):
            out[j, :, d] = tabela.painel(instante_local(calendario, d, h) + folga_s)[:, d]
    return out


def curva_intradiaria(vh: np.ndarray, final: np.ndarray, dias_ref: Sequence[int]) -> dict[str, np.ndarray]:
    """m(h) = Σ V_h / Σ final sobre células (campanha, dia) dos ``dias_ref`` com ambos conhecidos e final > 0.
    ``dias_ref`` deve conter só dias cujo final já era conhecido no corte (responsabilidade do chamador)."""
    H = vh.shape[0]
    m = np.full(H, np.nan)
    n = np.zeros(H, dtype=int)
    ds = np.asarray(list(dias_ref), dtype=int)
    for j in range(H):
        a, f = vh[j][:, ds], final[:, ds]
        ok = np.isfinite(a) & np.isfinite(f) & (f > 0)
        n[j] = int(ok.sum())
        if n[j] and f[ok].sum() > 0:
            m[j] = a[ok].sum() / f[ok].sum()
    return {"fator": m, "n_celulas": n}


def nowcast_intradiario(v: np.ndarray, fator: float, n_celulas: int, cfg: ConfigNowcast) -> np.ndarray:
    """Vetorizado por campanha: v / m(h) com a guarda herdada; NaN onde ``insuficiente``."""
    motivos = motivo_guarda(fator, n_celulas, v, cfg)
    with np.errstate(divide="ignore", invalid="ignore"):
        est = v / fator
    return np.where(motivos == "", est, np.nan)


__all__ = ["ConfigMonitor", "ConfigNowcast", "METODOS_NOWCAST", "curva_intradiaria", "fator_congelado", "maturar",
           "monitor_maturacao", "nowcast", "regime_vigente", "nowcast_intradiario", "paineis_diarios", "paineis_intradiarios",
           "triangulo_de_tabela"]
