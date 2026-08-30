"""Relógio explícito. Civil date em America/Sao_Paulo; instantes em UTC."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .constantes import FUSO_NEGOCIO
from .excecoes import ContratoInvalido, MoedaOuFusoIncompativel, VazamentoDeFuturo

FUSO = ZoneInfo(FUSO_NEGOCIO)
UTC = timezone.utc


def parse_civil(valor: str | date) -> date:
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError as exc:
        raise MoedaOuFusoIncompativel(f"data civil inválida: {valor}") from exc


def parse_instante(valor: str | datetime) -> datetime:
    if isinstance(valor, datetime):
        dt = valor
    else:
        try:
            dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        except ValueError as exc:
            raise MoedaOuFusoIncompativel(f"instante inválido: {valor}") from exc
    if dt.tzinfo is None:
        raise MoedaOuFusoIncompativel("instante sem timezone recusado")
    return dt.astimezone(UTC)


def civil_de_instante(instante: str | datetime) -> date:
    return parse_instante(instante).astimezone(FUSO).date()


def iso_civil(dia: date) -> str:
    return dia.isoformat()


def iso_instante(dt: datetime) -> str:
    return parse_instante(dt).isoformat().replace("+00:00", "Z")


def somar_dias(dia: str | date, n: int) -> date:
    return parse_civil(dia) + timedelta(days=n)


def recusar_futuro(data_usada: str | date, as_of_civil: str | date, contexto: str) -> None:
    if parse_civil(data_usada) > parse_civil(as_of_civil):
        raise VazamentoDeFuturo(f"{contexto}: {data_usada} > as_of {as_of_civil}")


def cutoff_utc(as_of: str | date | datetime) -> datetime:
    """Normaliza cutoff sem transformar uma data civil em meia-noite UTC.

    Uma data sem hora significa o último microssegundo daquele dia no fuso de
    negócio. Um instante sempre precisa trazer timezone.
    """

    if isinstance(as_of, datetime) or (isinstance(as_of, str) and "T" in as_of):
        return parse_instante(as_of)
    dia = parse_civil(as_of)
    return datetime.combine(dia, time.max, tzinfo=FUSO).astimezone(UTC)


def recusar_instante_futuro(
    instante_usado: str | datetime,
    cutoff_em: str | datetime,
    contexto: str,
) -> None:
    usado = parse_instante(instante_usado)
    limite = parse_instante(cutoff_em)
    if usado > limite:
        raise VazamentoDeFuturo(
            f"{contexto}: {iso_instante(usado)} > cutoff {iso_instante(limite)}"
        )


def exigir_target_d1(origin_date: str | date, target_date: str | date, horizonte_dias: int) -> None:
    if horizonte_dias != 1:
        raise ContratoInvalido("Predictive Core V1 exige horizonte estrito D+1")
    esperado = parse_civil(origin_date) + timedelta(days=1)
    if parse_civil(target_date) != esperado:
        raise ContratoInvalido(
            f"target D+1 inválido: origin={parse_civil(origin_date)} "
            f"target={parse_civil(target_date)} esperado={esperado}"
        )


def idade_horas(instante: str | datetime, cutoff_em: str | datetime) -> float:
    lido = parse_instante(instante)
    limite = parse_instante(cutoff_em)
    recusar_instante_futuro(lido, limite, "idade da observação")
    return (limite - lido).total_seconds() / 3600.0
