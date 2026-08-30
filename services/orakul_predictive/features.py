"""Observação diária as-of e montagem de features sem vazamento de futuro."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping, Optional, Sequence

from .constantes import (
    ALVO_SPEND,
    CENARIO_OBSERVADO,
    CENARIO_PLANNED_SPEND,
    CENARIOS,
    DATASET_KINDS,
    DEFINICOES_ALVO,
    FEATURE_SET_V1,
    FRESCO_MAX_HORAS,
    FUSO_NEGOCIO,
    MOEDA,
    UNIDADE_MONETARIA,
)
from .contratos import FeatureSnapshot, SourceReceipt
from .excecoes import ContratoInvalido, MoedaOuFusoIncompativel, VazamentoDeFuturo
from .hashes import chave_idempotencia, hash_canonico, id_canonico
from .relogio import (
    civil_de_instante,
    cutoff_utc,
    idade_horas,
    iso_civil,
    iso_instante,
    parse_civil,
    parse_instante,
    recusar_futuro,
    recusar_instante_futuro,
)
from .semantica import EstadoSemantico, validar_estado_valor, valor_numerico_ou_nulo

FEATURES_LAGGED_V1 = (
    "spend_lag0",
    "spend_lag6",
    "revenue_lag0",
    "revenue_lag6",
    "spend_ma7",
    "revenue_ma7",
    "dow_tue",
    "dow_wed",
    "dow_thu",
    "dow_fri",
    "dow_sat",
    "dow_sun",
    "campaign_age_days",
    "planned_spend_scenario",
)

# Features históricas que reconstituiam o alvo no mesmo dia (legado n8n).
FEATURES_PROIBIDAS_MESMO_DIA = frozenset({
    "budget_utilization",
    "cpc",
    "spend_mean_7d_inclusive_target",
    "spend_std_7d_inclusive_target",
    "spend_zscore_inclusive_target",
    "spend_ewma_7d_inclusive_target",
    "max_spend_7d_inclusive_target",
    "spend_squared_target",
})


@dataclass(frozen=True)
class ObservacaoDiaria:
    campanha_id: str
    civil_date: str
    spend_micros: Optional[int]
    revenue_micros: Optional[int]
    spend_estado: EstadoSemantico
    revenue_estado: EstadoSemantico
    lido_em: str
    dataset_kind: str = ""
    conta_id: Optional[str] = None
    campaign_start: Optional[str] = None
    moeda: str = MOEDA
    unidade: str = UNIDADE_MONETARIA
    fuso: str = FUSO_NEGOCIO
    fonte_falhou: bool = False

    def __post_init__(self) -> None:
        if self.moeda != MOEDA or self.unidade != UNIDADE_MONETARIA:
            raise MoedaOuFusoIncompativel("observação fora de BRL micros")
        if self.fuso != FUSO_NEGOCIO:
            raise MoedaOuFusoIncompativel("observação fora de America/Sao_Paulo")
        if self.dataset_kind not in DATASET_KINDS:
            raise ContratoInvalido("observação sem dataset_kind real/sintético explícito")
        if not self.conta_id or not self.campanha_id:
            raise ContratoInvalido("observação sem identidade conta/campanha")
        parse_civil(self.civil_date)
        parse_instante(self.lido_em)
        validar_estado_valor(self.spend_estado, self.spend_micros, contexto="spend observado")
        validar_estado_valor(self.revenue_estado, self.revenue_micros, contexto="revenue observado")
        if self.fonte_falhou:
            if self.spend_estado is not EstadoSemantico.FALHA or self.revenue_estado is not EstadoSemantico.FALHA:
                raise ContratoInvalido("fonte_falhou exige FALHA em spend e revenue")
        elif EstadoSemantico.FALHA in (self.spend_estado, self.revenue_estado):
            raise ContratoInvalido("estado FALHA exige fonte_falhou=true")


def _micros_util(estado: EstadoSemantico, micros: Optional[int]) -> Optional[int]:
    return valor_numerico_ou_nulo(estado, micros)


def _media(valores: Sequence[int]) -> Optional[float]:
    if len(valores) < 3:
        return None
    return sum(valores) / float(len(valores))


def _lookup(serie: Sequence[ObservacaoDiaria], dia: date) -> Optional[ObservacaoDiaria]:
    chave = iso_civil(dia)
    for obs in serie:
        if obs.civil_date == chave:
            return obs
    return None


def _estado_no_cutoff(
    obs: ObservacaoDiaria,
    estado: EstadoSemantico,
    cutoff_em: str,
) -> EstadoSemantico:
    if obs.fonte_falhou or estado is EstadoSemantico.FALHA:
        return EstadoSemantico.FALHA
    if estado is EstadoSemantico.ANTIGO:
        return EstadoSemantico.ANTIGO
    # A idade da leitura só degrada o fato do próprio dia de corte. Um valor
    # diário histórico finalizado não se torna "antigo" só porque é lag 6.
    if (
        estado in (EstadoSemantico.MEDIDO, EstadoSemantico.ZERO_MEDIDO)
        and parse_civil(obs.civil_date) == civil_de_instante(cutoff_em)
    ):
        if idade_horas(obs.lido_em, cutoff_em) > FRESCO_MAX_HORAS:
            return EstadoSemantico.ANTIGO
    return estado


def validar_serie_as_of(
    serie: Sequence[ObservacaoDiaria],
    as_of: str,
    cutoff_em: Optional[str] = None,
) -> None:
    as_of_d = parse_civil(as_of)
    limite = iso_instante(cutoff_utc(cutoff_em or as_of))
    for obs in serie:
        recusar_futuro(obs.civil_date, as_of_d, f"observação {obs.campanha_id}")
        recusar_instante_futuro(obs.lido_em, limite, f"leitura {obs.campanha_id}/{obs.civil_date}")
    # Também detecta duas revisões contraditórias no mesmo instante.
    serie_sem_futuro(serie, as_of, limite)


def detectar_leakage_de_alvo(
    features: Mapping[str, Optional[float]],
    alvo_futuro_micros: Optional[int],
    *,
    nomes_proibidos: frozenset[str] = FEATURES_PROIBIDAS_MESMO_DIA,
) -> None:
    for nome in features:
        if nome in nomes_proibidos:
            raise VazamentoDeFuturo(f"feature proibida por leakage histórico: {nome}")
    # Persistência honesta (spend_lag0 ≈ spend futuro) NÃO é leakage.
    # Replica do alvo contemporâneo com nome legado sim.
    if alvo_futuro_micros is None:
        return
    futuro_brl = alvo_futuro_micros / 1_000_000.0
    for nome, valor in features.items():
        if valor is None:
            continue
        if nome in nomes_proibidos or nome.startswith("future_") or nome.endswith("_target"):
            if abs(valor - futuro_brl) < 1e-9:
                raise VazamentoDeFuturo(f"feature {nome} replica o alvo futuro")


def montar_snapshot(
    serie: Sequence[ObservacaoDiaria],
    *,
    campanha_id: str,
    origin: str,
    horizonte_dias: int,
    versao_modelo: str,
    procedencia: SourceReceipt,
    codigo_hash: str,
    alvo: str,
    planned_spend_micros: Optional[int] = None,
    conta_id: Optional[str] = None,
    observado_em: str,
    cutoff_em: Optional[str] = None,
    cenario: str = CENARIO_OBSERVADO,
    injetar_feature_futura: Optional[Mapping[str, float]] = None,
) -> FeatureSnapshot:
    """Monta features disponíveis até o cutoff intraday, nunca só pela data.

    `injetar_feature_futura` existe só para o teste adversário de leakage:
    o detector deve recusar.
    """

    if horizonte_dias != 1:
        raise ContratoInvalido("FeatureSnapshot V1 exige target D+1")
    if cenario not in CENARIOS:
        raise ContratoInvalido("cenário inválido")
    if cenario == CENARIO_PLANNED_SPEND and planned_spend_micros is None:
        raise ContratoInvalido("planned_spend sem valor explícito")
    if cenario == CENARIO_OBSERVADO and planned_spend_micros is not None:
        raise ContratoInvalido("cenário observado não aceita planned_spend")
    if planned_spend_micros is not None and planned_spend_micros < 0:
        raise ContratoInvalido("planned_spend negativo")

    origin_d = parse_civil(origin)
    alvo_d = origin_d + timedelta(days=horizonte_dias)
    execucao_em = iso_instante(parse_instante(observado_em))
    cutoff_em = iso_instante(parse_instante(cutoff_em or observado_em))
    recusar_instante_futuro(cutoff_em, execucao_em, "cutoff point-in-time do snapshot")
    candidatas = [o for o in serie if o.campanha_id == campanha_id]
    contas = {o.conta_id for o in candidatas}
    if conta_id is None:
        if len(contas) != 1:
            raise ContratoInvalido("campanha ambígua entre contas; conta_id é obrigatório")
        conta_id = next(iter(contas))
    todas = [o for o in candidatas if o.conta_id == conta_id]
    if not todas:
        raise ContratoInvalido(f"série vazia para conta/campanha {conta_id}/{campanha_id}")
    filtrada = list(serie_sem_futuro(todas, origin, cutoff_em))
    if not filtrada:
        raise ContratoInvalido(f"nenhuma observação disponível no cutoff para {campanha_id}")
    kinds = {o.dataset_kind for o in filtrada}
    if kinds != {procedencia.dataset_kind}:
        raise ContratoInvalido(
            f"procedência {procedencia.dataset_kind} diverge das observações {sorted(kinds)}"
        )
    recusar_instante_futuro(procedencia.extraido_em, execucao_em, "procedência do snapshot")
    for obs in filtrada:
        recusar_instante_futuro(
            obs.lido_em,
            procedencia.extraido_em,
            f"observação posterior ao recibo {obs.campanha_id}/{obs.civil_date}",
        )

    def brl(estado: EstadoSemantico, micros: Optional[int]) -> Optional[float]:
        v = _micros_util(estado, micros)
        return None if v is None else v / 1_000_000.0

    def ponto(
        offset: int,
        campo: str,
    ) -> tuple[Optional[float], EstadoSemantico, Optional[str], Optional[str]]:
        dia = origin_d - timedelta(days=offset)
        obs = _lookup(filtrada, dia)
        if obs is None:
            return None, EstadoSemantico.AUSENTE, None, None
        if campo == "spend":
            estado = _estado_no_cutoff(obs, obs.spend_estado, cutoff_em)
            micros = obs.spend_micros
        else:
            estado = _estado_no_cutoff(obs, obs.revenue_estado, cutoff_em)
            micros = obs.revenue_micros
        return brl(estado, micros), estado, obs.lido_em, obs.civil_date

    def janela_media(
        campo: str,
        dias: int,
    ) -> tuple[Optional[float], EstadoSemantico, Optional[str], Optional[str]]:
        valores: list[int] = []
        instantes: list[str] = []
        datas: list[str] = []
        estados_vistos: list[EstadoSemantico] = []
        for i in range(dias):
            dia = origin_d - timedelta(days=i)
            obs = _lookup(filtrada, dia)
            if obs is None:
                continue
            recusar_futuro(obs.civil_date, origin_d, "janela_media")
            estado_bruto = obs.spend_estado if campo == "spend" else obs.revenue_estado
            estado = _estado_no_cutoff(obs, estado_bruto, cutoff_em)
            micros = obs.spend_micros if campo == "spend" else obs.revenue_micros
            estados_vistos.append(estado)
            instantes.append(obs.lido_em)
            datas.append(obs.civil_date)
            v = _micros_util(estado, micros)
            if v is None:
                continue
            valores.append(v)
        ultimo_instante = max(instantes, key=parse_instante) if instantes else None
        ultima_data = max(datas, key=parse_civil) if datas else None
        if EstadoSemantico.FALHA in estados_vistos:
            return None, EstadoSemantico.FALHA, ultimo_instante, ultima_data
        if EstadoSemantico.ANTIGO in estados_vistos:
            return None, EstadoSemantico.ANTIGO, ultimo_instante, ultima_data
        media = _media(valores)
        if media is None:
            return None, EstadoSemantico.AUSENTE, ultimo_instante, ultima_data
        estado_media = EstadoSemantico.ZERO_MEDIDO if media == 0 else EstadoSemantico.MEDIDO
        return media / 1_000_000.0, estado_media, ultimo_instante, ultima_data

    spend0, st_s0, as_s0, civil_s0 = ponto(0, "spend")
    spend6, st_s6, as_s6, civil_s6 = ponto(6, "spend")
    rev0, st_r0, as_r0, civil_r0 = ponto(0, "revenue")
    rev6, st_r6, as_r6, civil_r6 = ponto(6, "revenue")
    sma, st_sma, as_sma, civil_sma = janela_media("spend", 7)
    rma, st_rma, as_rma, civil_rma = janela_media("revenue", 7)

    target_wd = alvo_d.weekday()  # 0=segunda; dummies terça-domingo
    dummies = {
        "dow_tue": 1.0 if target_wd == 1 else 0.0,
        "dow_wed": 1.0 if target_wd == 2 else 0.0,
        "dow_thu": 1.0 if target_wd == 3 else 0.0,
        "dow_fri": 1.0 if target_wd == 4 else 0.0,
        "dow_sat": 1.0 if target_wd == 5 else 0.0,
        "dow_sun": 1.0 if target_wd == 6 else 0.0,
    }

    starts = [parse_civil(o.campaign_start or o.civil_date) for o in filtrada]
    start = min(starts)
    if start > origin_d:
        raise ContratoInvalido("campaign_start posterior à origem")
    age = float((origin_d - start).days)

    planned_estado = EstadoSemantico.NAO_APLICAVEL
    planned_val: Optional[float] = None
    if planned_spend_micros is not None:
        planned_val = planned_spend_micros / 1_000_000.0
        planned_estado = EstadoSemantico.HIPOTESE

    features: dict[str, Optional[float]] = {
        "spend_lag0": spend0,
        "spend_lag6": spend6,
        "revenue_lag0": rev0,
        "revenue_lag6": rev6,
        "spend_ma7": sma,
        "revenue_ma7": rma,
        **dummies,
        "campaign_age_days": age,
        "planned_spend_scenario": planned_val,
    }
    estados = {
        "spend_lag0": st_s0,
        "spend_lag6": st_s6,
        "revenue_lag0": st_r0,
        "revenue_lag6": st_r6,
        "spend_ma7": st_sma,
        "revenue_ma7": st_rma,
        **{k: EstadoSemantico.MEDIDO for k in dummies},
        "campaign_age_days": EstadoSemantico.MEDIDO,
        "planned_spend_scenario": planned_estado,
    }
    as_of_map = {
        "spend_lag0": as_s0,
        "spend_lag6": as_s6,
        "revenue_lag0": as_r0,
        "revenue_lag6": as_r6,
        "spend_ma7": as_sma,
        "revenue_ma7": as_rma,
        **{k: cutoff_em for k in dummies},
        "campaign_age_days": cutoff_em,
        "planned_spend_scenario": cutoff_em if planned_val is not None else None,
    }
    civil_map = {
        "spend_lag0": civil_s0,
        "spend_lag6": civil_s6,
        "revenue_lag0": civil_r0,
        "revenue_lag6": civil_r6,
        "spend_ma7": civil_sma,
        "revenue_ma7": civil_rma,
        **{k: iso_civil(origin_d) for k in dummies},
        "campaign_age_days": iso_civil(origin_d),
        "planned_spend_scenario": iso_civil(origin_d) if planned_val is not None else None,
    }
    unidades = {
        "spend_lag0": "brl",
        "spend_lag6": "brl",
        "revenue_lag0": "brl",
        "revenue_lag6": "brl",
        "spend_ma7": "brl",
        "revenue_ma7": "brl",
        **{k: "indicador" for k in dummies},
        "campaign_age_days": "dias",
        "planned_spend_scenario": "brl",
    }

    if injetar_feature_futura:
        features.update(dict(injetar_feature_futura))
        for nome in injetar_feature_futura:
            estados[nome] = EstadoSemantico.MEDIDO
            as_of_map[nome] = cutoff_em
            civil_map[nome] = iso_civil(alvo_d)
            unidades[nome] = "brl"
            recusar_futuro(alvo_d, origin_d, f"feature injetada {nome}")

    datas_usadas = [v for v in civil_map.values() if v]
    max_usada = max(datas_usadas, key=parse_civil) if datas_usadas else iso_civil(origin_d)
    recusar_futuro(max_usada, origin_d, "max_data_usada")
    instantes_usados = [v for v in as_of_map.values() if v]
    max_instante = max(instantes_usados, key=parse_instante) if instantes_usados else cutoff_em
    recusar_instante_futuro(max_instante, cutoff_em, "max_instante_usado")
    target_definition = DEFINICOES_ALVO.get(alvo)
    if target_definition is None:
        raise ContratoInvalido(f"alvo não suportado: {alvo}")

    payload_inputs = {
        "conta_id": conta_id,
        "campanha_id": campanha_id,
        "origin": origin,
        "target_date": iso_civil(alvo_d),
        "horizonte_dias": horizonte_dias,
        "cutoff_em": cutoff_em,
        "cenario": cenario,
        "features": features,
        "feature_estados": {k: v.value for k, v in estados.items()},
        "feature_as_of": as_of_map,
        "feature_civil_dates": civil_map,
        "feature_unidades": unidades,
        "feature_set": FEATURE_SET_V1,
        "alvo": alvo,
        "target_definition": target_definition,
        "versao_modelo": versao_modelo,
        "codigo_hash": codigo_hash,
        "procedencia_hash": procedencia.hash_fonte,
        "dataset_kind": procedencia.dataset_kind,
        "janela_inicio": min(o.civil_date for o in filtrada),
        "janela_fim": iso_civil(origin_d),
    }
    hash_inputs = hash_canonico(payload_inputs)
    identidade = {
        "conta_id": conta_id,
        "campanha_id": campanha_id,
        "origin": origin,
        "target_date": iso_civil(alvo_d),
        "alvo": alvo,
        "cenario": cenario,
        "versao_modelo": versao_modelo,
    }
    snapshot = FeatureSnapshot(
        snapshot_id=id_canonico("snap", **identidade),
        campanha_id=campanha_id,
        conta_id=conta_id,
        observado_em=execucao_em,
        janela_inicio=min(o.civil_date for o in filtrada),
        janela_fim=iso_civil(origin_d),
        horizonte_dias=horizonte_dias,
        versao_modelo=versao_modelo,
        hash_inputs=hash_inputs,
        procedencia=procedencia,
        estado_semantico=_estado_snapshot(estados, alvo),
        chave_idempotencia=chave_idempotencia(
            kind="snapshot",
            **identidade,
        ),
        alvo=alvo,
        feature_set_id=FEATURE_SET_V1,
        features=features,
        feature_estados=estados,
        feature_as_of=as_of_map,
        feature_unidades=unidades,
        feature_civil_dates=civil_map,
        origin_date=iso_civil(origin_d),
        target_date=iso_civil(alvo_d),
        cutoff_em=cutoff_em,
        cenario=cenario,
        target_definition=target_definition,
        codigo_hash=codigo_hash,
        max_data_usada=max_usada,
        max_instante_usado=max_instante,
    )
    # O detector não recebe o actual futuro: nem mesmo a validação pode consultar D+1.
    detectar_leakage_de_alvo(snapshot.features, None)
    return snapshot


def _estado_snapshot(estados: Mapping[str, EstadoSemantico], alvo: str) -> EstadoSemantico:
    if any(e is EstadoSemantico.FALHA for e in estados.values()):
        return EstadoSemantico.FALHA
    if any(e is EstadoSemantico.ANTIGO for e in estados.values()):
        return EstadoSemantico.ANTIGO
    principal = "spend_lag0" if alvo == ALVO_SPEND else "revenue_lag0"
    if estados.get(principal) is EstadoSemantico.AUSENTE:
        return EstadoSemantico.AUSENTE
    return EstadoSemantico.MEDIDO


def serie_sem_futuro(
    serie: Sequence[ObservacaoDiaria],
    as_of: str,
    cutoff_em: Optional[str] = None,
) -> tuple[ObservacaoDiaria, ...]:
    """Seleciona a última revisão conhecida por dia no instante de corte.

    Revisões posteriores ao cutoff são invisíveis. Duas linhas diferentes para
    a mesma conta/campanha/dia e o mesmo `lido_em` são conflito, não desempate.
    """

    limite_civil = parse_civil(as_of)
    limite_instante = cutoff_utc(cutoff_em or as_of)
    por_dia: dict[tuple[str, str, str], ObservacaoDiaria] = {}
    for obs in serie:
        if parse_civil(obs.civil_date) > limite_civil:
            continue
        lido = parse_instante(obs.lido_em)
        if lido > limite_instante:
            continue
        chave = (str(obs.conta_id), obs.campanha_id, obs.civil_date)
        anterior = por_dia.get(chave)
        if anterior is None or parse_instante(anterior.lido_em) < lido:
            por_dia[chave] = obs
        elif parse_instante(anterior.lido_em) == lido and anterior != obs:
            raise ContratoInvalido(f"revisões contraditórias no mesmo instante: {chave}")
    return tuple(
        sorted(
            por_dia.values(),
            key=lambda o: (str(o.conta_id), o.campanha_id, parse_civil(o.civil_date), parse_instante(o.lido_em)),
        )
    )
