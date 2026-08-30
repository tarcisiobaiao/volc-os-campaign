"""Série sintética marcada. Não afirma performance real."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .constantes import DATASET_SINTETICO, FUSO_NEGOCIO, MOEDA, UNIDADE_MONETARIA
from .contratos import SourceReceipt, recibo_sintetico
from .features import ObservacaoDiaria
from .relogio import iso_civil, iso_instante
from .semantica import EstadoSemantico

INSTANTE_FIXO = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
CAMPANHA_A = "camp-sintetica-a"
CAMPANHA_B = "camp-sintetica-curta"
CONTA = "conta-sintetica-1"
INICIO = date(2026, 6, 1)


def procedencia_sintetica() -> SourceReceipt:
    return recibo_sintetico("orakul-predictive-core-v1", iso_instante(INSTANTE_FIXO))


def _obs(
    campanha: str,
    dia: date,
    spend: int | None,
    revenue: int | None,
    estado_s: EstadoSemantico,
    estado_r: EstadoSemantico,
    *,
    falhou: bool = False,
    vintage_fechado: bool = False,
) -> ObservacaoDiaria:
    instante = (
        datetime(dia.year, dia.month, dia.day, 20, tzinfo=timezone.utc)
        if not vintage_fechado
        else datetime(dia.year, dia.month, dia.day, 4, tzinfo=timezone.utc) + timedelta(days=1)
    )
    return ObservacaoDiaria(
        campanha_id=campanha,
        conta_id=CONTA,
        civil_date=iso_civil(dia),
        spend_micros=spend,
        revenue_micros=revenue,
        spend_estado=estado_s,
        revenue_estado=estado_r,
        # A fixture preserva a vintage intraday usada pela previsão e a
        # vintage fechada do D+1 usada como actual. Revisão posterior não
        # reescreve nenhuma delas.
        lido_em=iso_instante(instante),
        dataset_kind=DATASET_SINTETICO,
        campaign_start=iso_civil(INICIO),
        moeda=MOEDA,
        unidade=UNIDADE_MONETARIA,
        fuso=FUSO_NEGOCIO,
        fonte_falhou=falhou,
    )


def serie_sintetica_a(n_dias: int = 42) -> tuple[ObservacaoDiaria, ...]:
    """Sazonalidade semanal determinística + tendência leve.

    SYNTHETIC_FIXTURE. entra_em_contagens_reais=False.
    """

    fator = {0: 1.25, 1: 1.05, 2: 1.00, 3: 0.98, 4: 1.10, 5: 0.75, 6: 0.65}
    linhas: list[ObservacaoDiaria] = []

    def registrar(*args, **kwargs) -> None:
        linhas.append(_obs(*args, **kwargs))
        linhas.append(_obs(*args, **kwargs, vintage_fechado=True))

    for i in range(n_dias):
        dia = INICIO + timedelta(days=i)
        if i == 15:
            continue  # ausência: dia sem linha
        if i == 20:
            registrar(CAMPANHA_A, dia, None, None, EstadoSemantico.FALHA, EstadoSemantico.FALHA, falhou=True)
            continue
        if i == 10:
            registrar(CAMPANHA_A, dia, 0, 0, EstadoSemantico.ZERO_MEDIDO, EstadoSemantico.ZERO_MEDIDO)
            continue
        spend = int(40_000_000 * fator[dia.weekday()] + i * 120_000)
        revenue = int(spend * (1.20 + 0.05 * (dia.weekday() == 0)))
        estado_s = EstadoSemantico.ANTIGO if i == 25 else EstadoSemantico.MEDIDO
        estado_r = estado_s
        registrar(CAMPANHA_A, dia, spend, revenue, estado_s, estado_r)
    return tuple(linhas)


def serie_sintetica_curta() -> tuple[ObservacaoDiaria, ...]:
    linhas = []
    for i in range(8):
        dia = INICIO + timedelta(days=i)
        spend = 10_000_000 + i * 100_000
        args = (CAMPANHA_B, dia, spend, int(spend * 1.1), EstadoSemantico.MEDIDO, EstadoSemantico.MEDIDO)
        linhas.append(_obs(*args))
        linhas.append(_obs(*args, vintage_fechado=True))
    return tuple(linhas)


def dataset_sintetico() -> tuple[ObservacaoDiaria, ...]:
    return serie_sintetica_a() + serie_sintetica_curta()
