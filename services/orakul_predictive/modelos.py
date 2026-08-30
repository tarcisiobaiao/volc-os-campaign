"""Baselines honestos: persistência, persistência semanal e linear defasado.

Nenhum LLM. Nenhuma feature contemporânea do alvo. Treino só com pares
cujo target_date já era conhecido no origin de treino.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional, Sequence

from .algebra import matvec, ridge
from .constantes import (
    ALVO_REVENUE,
    ALVO_SPEND,
    CENARIO_OBSERVADO,
    DEFINICOES_ALVO,
    FEATURE_SET_V1,
    MODELO_LAGGED_LINEAR,
    MODELO_NAIVE_PERSISTENCE,
    MODELO_NAIVE_WEEKDAY,
)
from .contratos import FeatureSnapshot
from .excecoes import ContratoInvalido, DatasetInsuficiente, DefinicaoDeAlvoIncompativel
from .features import ObservacaoDiaria
from .hashes import hash_canonico
from .semantica import EstadoSemantico, valor_numerico_ou_nulo

FEATURES_OLS_SPEND = (
    "spend_lag0",
    "spend_lag6",
    "spend_ma7",
    "dow_tue",
    "dow_wed",
    "dow_thu",
    "dow_fri",
    "dow_sat",
    "dow_sun",
    "campaign_age_days",
)
FEATURES_OLS_REVENUE = (
    "revenue_lag0",
    "revenue_lag6",
    "revenue_ma7",
    "spend_lag0",
    "dow_tue",
    "dow_wed",
    "dow_thu",
    "dow_fri",
    "dow_sat",
    "dow_sun",
    "campaign_age_days",
)


@dataclass(frozen=True)
class ArtefatoLinear:
    modelo_id: str
    alvo: str
    coeficientes: tuple[float, ...]
    nomes: tuple[str, ...]
    medias: tuple[float, ...]
    desvios: tuple[float, ...]
    alpha: float
    n_treino: int
    residuos_abs: tuple[float, ...]
    feature_set_id: str
    code_hash: str
    training_hash: str
    target_definition: str
    intercepto_penalizado: bool = False
    cenarios_suportados: tuple[str, ...] = (CENARIO_OBSERVADO,)

    def __post_init__(self) -> None:
        if self.alvo not in (ALVO_SPEND, ALVO_REVENUE):
            raise ContratoInvalido(f"artefato com alvo inválido: {self.alvo}")
        if self.target_definition != DEFINICOES_ALVO[self.alvo]:
            raise DefinicaoDeAlvoIncompativel("artefato mistura alvo e target_definition")
        if self.feature_set_id != FEATURE_SET_V1:
            raise ContratoInvalido("artefato pertence a outro feature set")
        if not self.code_hash or not self.training_hash:
            raise ContratoInvalido("artefato sem identidade de código/treino")
        if self.intercepto_penalizado:
            raise ContratoInvalido("Core V1 proíbe Ridge com intercepto penalizado")
        if self.cenarios_suportados != (CENARIO_OBSERVADO,):
            raise ContratoInvalido("artefato observacional não pode alegar resposta causal")
        tamanho = len(self.coeficientes)
        if not tamanho or not (
            tamanho == len(self.nomes) == len(self.medias) == len(self.desvios)
        ):
            raise ContratoInvalido("vetores do artefato desalinhados")
        if self.nomes[0] != "intercept" or self.medias[0] != 1.0 or self.desvios[0] != 1.0:
            raise ContratoInvalido("identidade do intercepto inválida")
        if self.n_treino != len(self.residuos_abs):
            raise ContratoInvalido("resíduos não correspondem à população de treino")
        if self.n_treino <= 0:
            raise ContratoInvalido("artefato sem amostra de treino")
        if not isfinite(self.alpha) or self.alpha < 0:
            raise ContratoInvalido("alpha Ridge negativo")
        if any(not isfinite(v) for v in (*self.coeficientes, *self.medias, *self.desvios)):
            raise ContratoInvalido("artefato contém número não finito")
        if any(v <= 0 for v in self.desvios):
            raise ContratoInvalido("artefato contém desvio não positivo")
        if any(not isfinite(v) or v < 0 for v in self.residuos_abs):
            raise ContratoInvalido("artefato contém resíduo inválido")

    @property
    def artifact_id(self) -> str:
        return f"artifact:{self.artifact_hash}"

    @property
    def artifact_hash(self) -> str:
        return hash_canonico({
            "schema": "orakul-linear-artifact/v2",
            "modelo_id": self.modelo_id,
            "alvo": self.alvo,
            "coeficientes": self.coeficientes,
            "nomes": self.nomes,
            "medias": self.medias,
            "desvios": self.desvios,
            "n_treino": self.n_treino,
            "alpha": self.alpha,
            "residuos_abs": self.residuos_abs,
            "feature_set_id": self.feature_set_id,
            "code_hash": self.code_hash,
            "training_hash": self.training_hash,
            "target_definition": self.target_definition,
            "intercepto_penalizado": self.intercepto_penalizado,
            "cenarios_suportados": self.cenarios_suportados,
        })


def _vetor(snapshot: FeatureSnapshot, nomes: Sequence[str]) -> Optional[list[float]]:
    valores: list[float] = [1.0]
    for nome in nomes:
        estado = snapshot.feature_estados.get(nome)
        valor = snapshot.features.get(nome)
        if estado not in (EstadoSemantico.MEDIDO, EstadoSemantico.ZERO_MEDIDO) or valor is None:
            if nome.startswith("dow_"):
                valores.append(0.0)
                continue
            return None
        valores.append(float(valor))
    return valores


def naive_persistence(snapshot: FeatureSnapshot, alvo: str) -> Optional[int]:
    if alvo == ALVO_SPEND:
        chave, estado = "spend_lag0", snapshot.feature_estados["spend_lag0"]
    elif alvo == ALVO_REVENUE:
        chave, estado = "revenue_lag0", snapshot.feature_estados["revenue_lag0"]
    else:
        return None
    valor = snapshot.features[chave]
    if estado not in (EstadoSemantico.MEDIDO, EstadoSemantico.ZERO_MEDIDO) or valor is None:
        return None
    return int(round(valor * 1_000_000))


def naive_weekday(serie: Sequence[ObservacaoDiaria], snapshot: FeatureSnapshot, alvo: str) -> Optional[int]:
    """Último mesmo weekday <= origin (lag 7 civil se existir)."""

    from datetime import timedelta

    from .features import serie_sem_futuro
    from .relogio import parse_civil

    origin = parse_civil(snapshot.janela_fim)
    alvo_d = origin + timedelta(days=snapshot.horizonte_dias)
    candidato = alvo_d - timedelta(days=7)
    as_of = serie_sem_futuro(serie, snapshot.origin_date, snapshot.cutoff_em)
    for obs in as_of:
        if (
            obs.conta_id != snapshot.conta_id
            or obs.campanha_id != snapshot.campanha_id
            or obs.civil_date != candidato.isoformat()
        ):
            continue
        if alvo == ALVO_SPEND:
            return valor_numerico_ou_nulo(obs.spend_estado, obs.spend_micros)
        if alvo == ALVO_REVENUE:
            return valor_numerico_ou_nulo(obs.revenue_estado, obs.revenue_micros)
    return None


def _padronizar(
    linhas: list[list[float]],
    medias: Optional[list[float]] = None,
    desvios: Optional[list[float]] = None,
) -> tuple[list[list[float]], list[float], list[float]]:
    nfeat = len(linhas[0])
    if medias is None:
        medias = []
        desvios = []
        for j in range(nfeat):
            col = [row[j] for row in linhas]
            mu = sum(col) / len(col)
            var = sum((x - mu) ** 2 for x in col) / max(len(col) - 1, 1)
            sd = var ** 0.5
            medias.append(mu)
            desvios.append(sd if sd > 1e-9 else 1.0)
    out = []
    for row in linhas:
        nova = [row[0]]  # intercept
        for j in range(1, nfeat):
            nova.append((row[j] - medias[j]) / desvios[j])
        out.append(nova)
    return out, medias, desvios


def treinar_linear(
    pares: Sequence[tuple[FeatureSnapshot, int]],
    alvo: str,
    *,
    alpha: float = 1.0,
    n_minimo: int = 14,
) -> ArtefatoLinear:
    if alvo not in (ALVO_SPEND, ALVO_REVENUE):
        raise DefinicaoDeAlvoIncompativel(f"Ridge não suporta alvo {alvo}")
    nomes = FEATURES_OLS_SPEND if alvo == ALVO_SPEND else FEATURES_OLS_REVENUE
    xs: list[list[float]] = []
    ys: list[float] = []
    identidade_treino: list[dict[str, object]] = []
    pares_ordenados = sorted(pares, key=lambda par: (par[0].target_date, par[0].snapshot_id))
    code_hashes: set[str] = set()
    for snap, y_micros in pares_ordenados:
        if snap.alvo != alvo or snap.target_definition != DEFINICOES_ALVO[alvo]:
            raise DefinicaoDeAlvoIncompativel("snapshot de outro alvo entrou no artefato")
        if snap.feature_set_id != FEATURE_SET_V1:
            raise ContratoInvalido("mistura de feature sets no treino")
        if snap.cenario != CENARIO_OBSERVADO:
            raise ContratoInvalido("planned_spend não identifica efeito causal e não entra no treino")
        code_hashes.add(snap.codigo_hash)
        vet = _vetor(snap, nomes)
        if vet is None:
            continue
        xs.append(vet)
        ys.append(y_micros / 1_000_000.0)
        identidade_treino.append({
            "snapshot_id": snap.snapshot_id,
            "hash_inputs": snap.hash_inputs,
            "origin_date": snap.origin_date,
            "target_date": snap.target_date,
            "y_micros": y_micros,
        })
    if len(xs) < n_minimo:
        raise DatasetInsuficiente(f"{alvo}: {len(xs)} pares completos < {n_minimo}")
    if len(code_hashes) != 1:
        raise ContratoInvalido("treino mistura versões de código")
    xs_s, medias, desvios = _padronizar(xs)
    coef = ridge(xs_s, ys, alpha=alpha, penalizar_intercepto=False)
    pred = matvec(xs_s, coef)
    residuos = tuple(abs(yi - pi) for yi, pi in zip(ys, pred))
    return ArtefatoLinear(
        modelo_id=MODELO_LAGGED_LINEAR,
        alvo=alvo,
        coeficientes=tuple(coef),
        nomes=("intercept",) + tuple(nomes),
        medias=tuple(medias),
        desvios=tuple(desvios),
        alpha=alpha,
        n_treino=len(xs),
        residuos_abs=residuos,
        feature_set_id=FEATURE_SET_V1,
        code_hash=next(iter(code_hashes)),
        training_hash=hash_canonico(identidade_treino),
        target_definition=DEFINICOES_ALVO[alvo],
        intercepto_penalizado=False,
        cenarios_suportados=(CENARIO_OBSERVADO,),
    )


def prever_linear(artefato: ArtefatoLinear, snapshot: FeatureSnapshot) -> Optional[float]:
    if artefato.alvo != snapshot.alvo or artefato.target_definition != snapshot.target_definition:
        raise DefinicaoDeAlvoIncompativel("artefato e snapshot têm alvos diferentes")
    if artefato.modelo_id != snapshot.versao_modelo:
        raise ContratoInvalido("artefato e snapshot têm versões diferentes")
    if artefato.feature_set_id != snapshot.feature_set_id:
        raise ContratoInvalido("artefato e snapshot têm feature sets diferentes")
    if snapshot.cenario not in artefato.cenarios_suportados:
        raise ContratoInvalido("artefato observacional não suporta cenário planejado")
    nomes = artefato.nomes[1:]
    vet = _vetor(snapshot, nomes)
    if vet is None:
        return None
    xs, _, _ = _padronizar([vet], list(artefato.medias), list(artefato.desvios))
    y_brl = matvec(xs, list(artefato.coeficientes))[0]
    return y_brl


def brl_para_micros(valor: Optional[float]) -> Optional[int]:
    if valor is None:
        return None
    return int(round(max(0.0, valor) * 1_000_000))


def modelos_declarados() -> tuple[str, ...]:
    return (MODELO_NAIVE_PERSISTENCE, MODELO_NAIVE_WEEKDAY, MODELO_LAGGED_LINEAR)
