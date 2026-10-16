"""Maturação / nowcasting transparente de coortes com atraso de reporte.

Modelo de dados (sem olhar o futuro por construção):
- ``triangulo[c, a]`` = valor ACUMULADO reportado da coorte ``c`` (dia de origem) até a
  idade ``a`` dias; ``NaN`` onde ``c + a > as_of`` (futuro, ainda não observado) e onde
  o reporte está ausente (ausência != 0);
- ``idade_final`` (A) = idade em que a coorte é considerada madura. É um parâmetro de
  CENÁRIO/hipótese: tudo que chega depois de A é assumido inexistente.

Baseline (chain-ladder simples, versão "coortes maduras"):
    m(a) = sum_c C[c, a] / sum_c C[c, A]  sobre as últimas ``janela_coortes`` coortes com
    c + A <= as_of (maduras ANTES do as_of), excluindo coortes com célula ausente.
    nowcast(c) = C[c, as_of - c] / m(as_of - c)

Variante ``link_ratio`` (chain-ladder clássico): fatores idade->idade+1 usando coortes
parcialmente maduras, m(a) = 1 / prod_{j>=a} f_j.

Guarda: se m(a) < ``maturidade_minima`` ou se há menos que ``min_coortes`` coortes
válidas, o resultado é ``ResultadoInsuficiente`` — não um número.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats

from volc_dil.statlab.base import ResultadoInsuficiente


# ---------------------------------------------------------------------------
# distribuições de atraso (configuráveis; todas truncadas em ``maximo``)
# ---------------------------------------------------------------------------

def pmf_atraso_lognormal(mediana: float, sigma: float, maximo: int) -> np.ndarray:
    """PMF discreta em 0..maximo de floor(D), D ~ LogNormal(log(mediana), sigma), truncada."""
    bordas = np.arange(1, maximo + 1, dtype=float)
    cdf = stats.lognorm.cdf(bordas, s=sigma, scale=mediana)
    pmf = np.diff(np.concatenate([[0.0], cdf, [1.0]]))
    pmf[-1] = 0.0  # massa além de ``maximo`` é descartada (hipótese do cenário) e renormalizada
    pmf = pmf[: maximo + 1]
    return pmf / pmf.sum()


def pmf_atraso_geometrica(media: float, maximo: int, minimo: int = 0) -> np.ndarray:
    """PMF geométrica deslocada (minimo + Geom) truncada em ``maximo``. ``minimo=1`` modela
    reporte que nunca chega no mesmo dia (ex.: D+1)."""
    if media <= minimo:
        raise ValueError("media deve ser > minimo")
    p = 1.0 / (media - minimo + 1.0)
    k = np.arange(0, maximo + 1)
    pmf = np.where(k >= minimo, p * (1 - p) ** np.clip(k - minimo, 0, None), 0.0)
    return pmf / pmf.sum()


@dataclass(frozen=True)
class CenarioMaturacao:
    """Parâmetros de CENÁRIO. Nenhum valor aqui é default operacional."""

    n_coortes: int
    idade_final: int
    eventos_por_dia: float
    mediana_valor: float
    sigma_valor: float
    pmf_atraso: np.ndarray
    sigma_volume_diario: float = 0.2
    regime_inicio: int | None = None  # coorte a partir da qual o atraso muda
    pmf_atraso_regime: np.ndarray | None = None
    nome: str = "cenario"
    # granularidade do reporte (ex.: 0.01 = arredondamento a centavo do acumulado reportado)
    granularidade: float | None = None

    def descrever(self) -> dict[str, Any]:
        def resumo_pmf(p: np.ndarray | None) -> Any:
            if p is None:
                return None
            cdf = np.cumsum(p)
            return {
                "media_dias": float((np.arange(p.size) * p).sum()),
                "massa_idade0": float(p[0]),
                "cdf_idade_1_3_7_14_30": [float(cdf[min(i, p.size - 1)]) for i in (1, 3, 7, 14, 30)],
            }

        return {
            "nome": self.nome,
            "n_coortes": self.n_coortes,
            "idade_final": self.idade_final,
            "eventos_por_dia": self.eventos_por_dia,
            "mediana_valor": self.mediana_valor,
            "sigma_valor": self.sigma_valor,
            "sigma_volume_diario": self.sigma_volume_diario,
            "atraso": resumo_pmf(self.pmf_atraso),
            "regime_inicio": self.regime_inicio,
            "granularidade": self.granularidade,
            "atraso_regime": resumo_pmf(self.pmf_atraso_regime),
        }


def simular_incrementos(cen: CenarioMaturacao, rng: np.random.Generator) -> np.ndarray:
    """Matriz ``inc[c, d]`` de valor reportado com atraso exato ``d`` (0..A). Verdade final =
    ``inc.sum(1)``. Cada evento (clique/conversão) tem valor lognormal e atraso próprio."""
    C, A = cen.n_coortes, cen.idade_final
    if cen.pmf_atraso.size != A + 1:
        raise ValueError("pmf_atraso deve ter idade_final + 1 posições")
    dia = np.arange(C)
    sazonal = 1 + 0.3 * np.sin(2 * np.pi * dia / 7)
    lam = cen.eventos_por_dia * sazonal * rng.lognormal(0.0, cen.sigma_volume_diario, C)
    n = rng.poisson(lam)
    coorte = np.repeat(dia, n)
    valor = rng.lognormal(np.log(cen.mediana_valor), cen.sigma_valor, coorte.size)
    atraso = rng.choice(A + 1, size=coorte.size, p=cen.pmf_atraso)
    if cen.regime_inicio is not None:
        if cen.pmf_atraso_regime is None or cen.pmf_atraso_regime.size != A + 1:
            raise ValueError("regime exige pmf_atraso_regime com idade_final + 1 posições")
        novos = coorte >= cen.regime_inicio
        atraso[novos] = rng.choice(A + 1, size=int(novos.sum()), p=cen.pmf_atraso_regime)
    flat = np.bincount(coorte * (A + 1) + atraso, weights=valor, minlength=C * (A + 1))
    return flat.reshape(C, A + 1)


def arredondar(valores: np.ndarray, granularidade: float | None) -> np.ndarray:
    """Arredonda ao múltiplo de ``granularidade`` (reporte em centavos). None = sem arredondar."""
    if granularidade is None:
        return valores
    return np.round(valores / granularidade) * granularidade


def triangulo_observado(incrementos: np.ndarray, as_of: int,
                        granularidade: float | None = None) -> np.ndarray:
    """Acumulado observado até ``as_of``; células futuras (c + a > as_of) ficam NaN."""
    C, A1 = incrementos.shape
    acum = arredondar(np.cumsum(incrementos, axis=1), granularidade)
    c = np.arange(C)[:, None]
    a = np.arange(A1)[None, :]
    return np.where(c + a <= as_of, acum, np.nan)


# ---------------------------------------------------------------------------
# fator de maturação
# ---------------------------------------------------------------------------

def _coortes_maduras(n_coortes: int, idade_final: int, as_of: int, janela: int) -> np.ndarray:
    ultima = as_of - idade_final  # última coorte madura no as_of
    if ultima < 0:
        return np.array([], dtype=int)
    primeira = max(0, ultima - janela + 1)
    return np.arange(primeira, min(ultima, n_coortes - 1) + 1)


def fatores_maturacao(triangulo: np.ndarray, as_of: int, *, janela_coortes: int,
                      metodo: str = "coortes_maduras") -> dict[str, Any]:
    """Fator m(a) para todas as idades 0..A, usando só células observadas até ``as_of``.

    Retorna ``fator`` (NaN onde indefinido — nunca 0 por ausência), ``n_coortes`` válidas
    por idade e ``n_excluidas_ausentes`` (coortes descartadas por célula NaN).
    """
    C, A1 = triangulo.shape
    A = A1 - 1
    # salvaguarda anti-futuro: tudo além do as_of é descartado mesmo que o chamador passe
    c = np.arange(C)[:, None]
    a = np.arange(A1)[None, :]
    tri = np.where(c + a <= as_of, triangulo, np.nan)

    if metodo == "coortes_maduras":
        maduras = _coortes_maduras(C, A, as_of, janela_coortes)
        fator = np.full(A1, np.nan)
        n_val = np.zeros(A1, dtype=int)
        n_exc = np.zeros(A1, dtype=int)
        if maduras.size:
            bloco = tri[maduras]
            final = bloco[:, A]
            for idade in range(A1):
                ok = np.isfinite(bloco[:, idade]) & np.isfinite(final)
                n_val[idade] = int(ok.sum())
                n_exc[idade] = int((~ok).sum())
                den = final[ok].sum()
                if n_val[idade] > 0 and den > 0:
                    fator[idade] = bloco[ok, idade].sum() / den
        return {"metodo": metodo, "fator": fator, "n_coortes": n_val, "n_excluidas_ausentes": n_exc,
                "coortes_usadas": [int(maduras[0]), int(maduras[-1])] if maduras.size else None}

    if metodo == "link_ratio":
        link = np.full(A, np.nan)
        n_val = np.zeros(A1, dtype=int)
        n_exc = np.zeros(A1, dtype=int)
        for idade in range(A):
            ultima = as_of - idade - 1
            if ultima < 0:
                continue
            cs = np.arange(max(0, ultima - janela_coortes + 1), min(ultima, C - 1) + 1)
            x0, x1 = tri[cs, idade], tri[cs, idade + 1]
            ok = np.isfinite(x0) & np.isfinite(x1)
            n_val[idade] = int(ok.sum())
            n_exc[idade] = int((~ok).sum())
            den = x0[ok].sum()
            if n_val[idade] > 0 and den > 0:
                link[idade] = x1[ok].sum() / den
        n_val[A] = n_val[A - 1] if A > 0 else 0
        # m(a) = 1 / prod_{j>=a} f_j ; NaN em qualquer f_j torna m(a) NaN (não 0, não 1)
        prod_rev = np.cumprod(link[::-1])[::-1]
        fator = np.concatenate([1.0 / prod_rev, [1.0]])
        # n válido para m(a) é o mínimo ao longo da cadeia a..A-1
        n_cadeia = np.minimum.accumulate(n_val[:A][::-1])[::-1] if A > 0 else np.array([], int)
        n_val = np.concatenate([n_cadeia, [n_cadeia[-1] if A > 0 else 0]])
        return {"metodo": metodo, "fator": fator, "n_coortes": n_val, "n_excluidas_ausentes": n_exc,
                "fator_link": link}

    raise ValueError(f"metodo desconhecido: {metodo}")


def nowcast_sem_guarda(observado: float, fator: float) -> float:
    """Estimador ingênuo obs / m(a). Existe só para DEMONSTRAR a falha (fator ~0 explode;
    fator 0 dá inf/NaN). Não use operacionalmente."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(np.float64(observado) / np.float64(fator))


@dataclass(frozen=True)
class ConfigNowcast:
    """Configuração do nowcast. Todos os limiares são OBRIGATÓRIOS (sem default operacional)."""

    janela_coortes: int
    maturidade_minima: float
    min_coortes: int
    metodo: str = "coortes_maduras"
    nivel_intervalo: float | None = None
    n_bootstrap: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def nowcast_coorte(triangulo: np.ndarray, as_of: int, coorte: int, cfg: ConfigNowcast,
                   rng: np.random.Generator | None = None) -> dict[str, Any] | ResultadoInsuficiente:
    """Nowcast de uma coorte no ``as_of`` com guarda. Retorna dict com estimativa, baseline
    (observado), n, intervalo e versão do método — ou ``ResultadoInsuficiente``."""
    C, A1 = triangulo.shape
    A = A1 - 1
    if coorte > as_of or coorte < 0 or coorte >= C:
        return ResultadoInsuficiente("coorte_inexistente_no_as_of", {"coorte": coorte, "as_of": as_of})
    idade = min(as_of - coorte, A)
    obs = triangulo[coorte, idade]
    if not np.isfinite(obs):
        return ResultadoInsuficiente("observacao_ausente", {"coorte": coorte, "idade": idade})
    if idade == A:
        return {"status": "maduro", "estimativa": float(obs), "observado": float(obs), "fator": 1.0,
                "idade": idade, "n_coortes": None, "intervalo": [float(obs), float(obs)],
                "metodo": cfg.metodo}
    fat = fatores_maturacao(triangulo, as_of, janela_coortes=cfg.janela_coortes, metodo=cfg.metodo)
    m = fat["fator"][idade]
    n = int(fat["n_coortes"][idade])
    if n < cfg.min_coortes:
        return ResultadoInsuficiente("coortes_maduras_insuficientes",
                                     {"n_coortes": n, "min_coortes": cfg.min_coortes, "idade": idade})
    if not np.isfinite(m):
        return ResultadoInsuficiente("fator_indefinido", {"idade": idade, "n_coortes": n})
    if m < cfg.maturidade_minima:
        return ResultadoInsuficiente("maturidade_abaixo_do_minimo",
                                     {"fator": float(m), "maturidade_minima": cfg.maturidade_minima,
                                      "idade": idade, "observado": float(obs)})
    out: dict[str, Any] = {
        "status": "estimado", "estimativa": float(obs / m), "observado": float(obs),
        "fator": float(m), "idade": idade, "n_coortes": n, "metodo": cfg.metodo,
        "intervalo": None,
    }
    if cfg.nivel_intervalo is not None:
        lo, hi = intervalo_razao_empirica(triangulo, as_of, idade, obs, cfg)
        out["intervalo"] = [lo, hi]
        out["intervalo_tipo"] = "razao_empirica_coortes_maduras"
    return out


def intervalo_razao_empirica(triangulo: np.ndarray, as_of: int, idade: int, obs: float,
                             cfg: ConfigNowcast) -> tuple[float | None, float | None]:
    """Intervalo preditivo: obs x quantis de final/observado(idade) entre coortes maduras.
    Indefinido (None) se obs == 0 (razão sem sentido) ou se < min_coortes razões válidas."""
    C, A1 = triangulo.shape
    A = A1 - 1
    maduras = _coortes_maduras(C, A, as_of, cfg.janela_coortes)
    if obs <= 0 or maduras.size == 0 or cfg.nivel_intervalo is None:
        return None, None
    x, f = triangulo[maduras, idade], triangulo[maduras, A]
    ok = np.isfinite(x) & np.isfinite(f) & (x > 0)
    if ok.sum() < cfg.min_coortes:
        return None, None
    r = f[ok] / x[ok]
    q = (1 - cfg.nivel_intervalo) / 2
    return float(obs * np.quantile(r, q)), float(obs * np.quantile(r, 1 - q))


# ---------------------------------------------------------------------------
# avaliação Monte Carlo (vetorizada por mundo)
# ---------------------------------------------------------------------------

def avaliar_mundo(cen: CenarioMaturacao, rng: np.random.Generator, as_of: int, cfg: ConfigNowcast
                  ) -> dict[str, np.ndarray]:
    """Simula um mundo e avalia o nowcast das coortes ``as_of - a`` para a = 0..A-1.

    Saídas por idade: verdade, observado, fator, estimativa com guarda (NaN se insuficiente),
    estimativa sem guarda, intervalos (razão empírica e bootstrap do fator).
    """
    A = cen.idade_final
    inc = simular_incrementos(cen, rng)
    # verdade = acumulado na idade final pelo MESMO caminho numérico do triângulo (evita falso
    # "não cobre" por arredondamento de ponto flutuante quando a coorte já está madura)
    verdade_total = arredondar(np.cumsum(inc, axis=1), cen.granularidade)[:, A]
    tri = triangulo_observado(inc, as_of, cen.granularidade)
    fat = fatores_maturacao(tri, as_of, janela_coortes=cfg.janela_coortes, metodo=cfg.metodo)
    idades = np.arange(A)
    coortes = as_of - idades
    obs = tri[coortes, idades]
    m = fat["fator"][:A]
    ncoort = fat["n_coortes"][:A]
    verdade = verdade_total[coortes]
    with np.errstate(divide="ignore", invalid="ignore"):
        sem_guarda = obs / m
    valido = np.isfinite(m) & (m >= cfg.maturidade_minima) & (ncoort >= cfg.min_coortes) & np.isfinite(obs)
    com_guarda = np.where(valido, sem_guarda, np.nan)

    res = {"idade": idades, "verdade": verdade, "observado": obs, "fator": m,
           "sem_guarda": sem_guarda, "com_guarda": com_guarda}

    if cfg.nivel_intervalo is not None and cfg.metodo == "coortes_maduras":
        q = (1 - cfg.nivel_intervalo) / 2
        maduras = _coortes_maduras(cen.n_coortes, A, as_of, cfg.janela_coortes)
        bloco = tri[maduras]  # (K, A+1), todas observadas
        # (1) razão empírica (preditivo: incerteza do fator + ruído de processo)
        lo_r = np.full(A, np.nan)
        hi_r = np.full(A, np.nan)
        for i in range(A):
            if not valido[i] or obs[i] <= 0:
                continue
            x = bloco[:, i]
            okx = np.isfinite(x) & (x > 0)
            if okx.sum() < cfg.min_coortes:
                continue
            r = bloco[okx, A] / x[okx]
            lo_r[i], hi_r[i] = obs[i] * np.quantile(r, q), obs[i] * np.quantile(r, 1 - q)
        res["ic_razao_lo"], res["ic_razao_hi"] = lo_r, hi_r
        # (2) bootstrap do fator (só incerteza de parâmetro) — esperado sub-cobrir
        if cfg.n_bootstrap > 0 and cfg.metodo == "coortes_maduras" and maduras.size:
            idx = rng.integers(0, maduras.size, size=(cfg.n_bootstrap, maduras.size))
            num = bloco[idx][:, :, :A].sum(axis=1)
            den = bloco[idx][:, :, A].sum(axis=1)[:, None]
            with np.errstate(divide="ignore", invalid="ignore"):
                est_b = obs[None, :] / (num / den)
            est_b = np.where(np.isfinite(est_b), est_b, np.inf)  # fator 0 na reamostra = explosão, não ausência
            with np.errstate(invalid="ignore"):  # quantil com +inf é intencional (explosão)
                lo_b = np.where(valido, np.quantile(est_b, q, axis=0), np.nan)
                hi_b = np.where(valido, np.quantile(est_b, 1 - q, axis=0), np.nan)
            res["ic_boot_lo"], res["ic_boot_hi"] = lo_b, hi_b
    return res


FAIXAS_IDADE = ((0, 0), (1, 2), (3, 6), (7, 13), (14, 29), (30, 59))


def _ic_por_mundo(valores: np.ndarray, mascara: np.ndarray) -> dict[str, Any]:
    """IC de Monte Carlo por CLUSTER (mundo): média das células válidas em cada mundo, depois IC
    entre mundos. Células da mesma réplica compartilham o fator e não são independentes; tratar
    cada célula como uma simulação daria IC otimista. Mundos sem célula válida são excluídos e contados."""
    from volc_dil.statlab.base import ic_media

    soma = np.where(mascara, valores, 0.0).sum(axis=1)
    cont = mascara.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        por_mundo = np.where(cont > 0, soma / np.where(cont > 0, cont, 1), np.nan)
    out = ic_media(por_mundo)
    out["n_celulas"] = int(cont.sum())
    out["unidade_ic"] = "mundo"
    return out


def agregar(mundos: list[dict[str, np.ndarray]], faixas: tuple[tuple[int, int], ...] = FAIXAS_IDADE
            ) -> list[dict[str, Any]]:
    """Agrega MAE, MAPE, viés relativo, cobertura e taxa de 'insuficiente' por faixa de idade.
    MAPE e cobertura excluem (e contam) verdades == 0 e estimativas ausentes; nada vira 0.
    ICs de Monte Carlo são por mundo (cluster). Viés relativo e APE máx/p99 são agregados."""
    pilha = {k: np.stack([w[k] for w in mundos]) for k in mundos[0] if k != "idade"}
    idade = mundos[0]["idade"]
    saida = []
    for lo, hi in faixas:
        sel = (idade >= lo) & (idade <= hi)
        if not sel.any():
            continue
        V = pilha["verdade"][:, sel]
        fs = pilha["fator"][:, sel]
        linha: dict[str, Any] = {"faixa_idade": [lo, hi],
                                 "fator_medio": float(np.nanmean(fs)) if np.isfinite(fs).any() else None,
                                 "frac_fator_indefinido": float(np.mean(~np.isfinite(fs)))}
        for nome in ("sem_guarda", "com_guarda"):
            E = pilha[nome][:, sel]
            OK = np.isfinite(E)
            OKP = OK & (V > 0)
            with np.errstate(invalid="ignore", divide="ignore"):
                APE = np.where(OKP, np.abs(E - V) / np.where(V > 0, V, 1), np.nan)
                REL = np.where(OKP, (E - V) / np.where(V > 0, V, 1), np.nan)
            ape = APE[OKP]
            erro = (E - V)[OK]
            linha[nome] = {
                "n_estimados": int(OK.sum()),
                "n_total": int(E.size),
                "frac_insuficiente_ou_nao_finito": _ic_por_mundo((~OK).astype(float), np.ones_like(OK)),
                "mae": _ic_por_mundo(np.abs(np.where(OK, E - V, 0.0)), OK),
                "mape": _ic_por_mundo(np.nan_to_num(APE), OKP),
                "ape_p99": float(np.quantile(ape, 0.99)) if ape.size else None,
                "ape_max": float(ape.max()) if ape.size else None,
                "vies_relativo": (float(erro.sum() / V[OK].sum()) if OK.any() and V[OK].sum() > 0 else None),
                "erro_relativo_medio": _ic_por_mundo(np.nan_to_num(REL), OKP),
                "n_verdade_zero_excluida_mape": int((OK & (V <= 0)).sum()),
            }
        for tipo in ("razao", "boot"):
            klo, khi = f"ic_{tipo}_lo", f"ic_{tipo}_hi"
            if klo in pilha:
                LO, HI = pilha[klo][:, sel], pilha[khi][:, sel]
                OK = np.isfinite(LO) & np.isfinite(HI)
                tol = 1e-9 * np.maximum(np.abs(V), 1.0)  # tolerância numérica, não estatística
                with np.errstate(invalid="ignore"):
                    COBRE = OK & (LO - tol <= V) & (V <= HI + tol)
                linha[f"cobertura_{tipo}"] = _ic_por_mundo(COBRE.astype(float), OK)
                linha[f"cobertura_{tipo}"]["n_sem_intervalo"] = int((~OK).sum())
        saida.append(linha)
    return saida
