"""Projecao read-only de saude e deadman dos coletores Google Intelligence.

O modulo apenas transforma recibos ja obtidos. Ele nao consulta n8n, Google Ads
ou Supabase, nao persiste resultados e nao envia alertas. A identidade de um
coletor inclui a hierarquia Google Ads (MCC e conta), o job e o tipo de sinal;
assim, schedules de contas diferentes nunca sao confundidos.

Regras centrais:

* ``SAUDAVEL`` exige sucesso confirmado dentro da janela esperada.
* tentativa nao substitui sucesso e heartbeat nao prova execucao.
* heartbeat obrigatorio ausente e uma ausencia observavel, nunca zero.
* falhas sao estruturadas em codigo e classe; detalhe bruto nao entra na saida.
* o relogio precisa ser injetado para manter a projecao deterministica.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .modelo import DocumentoColeta, EstadoColeta


_ID_INTERNO = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,119}$")
_TIPO_COLETOR = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{0,119}$")
_ROTULO_ERRO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")


class EstadoSaudeColetor(str, Enum):
    SAUDAVEL = "saudavel"
    ATRASADO = "atrasado"
    FALHOU = "falhou"
    NUNCA_EXECUTADO = "nunca_executado"
    DESABILITADO = "desabilitado"
    INDETERMINADO = "indeterminado"


class MotivoDiagnostico(str, Enum):
    OK = "OK"
    COLETOR_DESABILITADO = "COLETOR_DESABILITADO"
    SEM_EXECUCAO_PREVIA = "SEM_EXECUCAO_PREVIA"
    TENTATIVA_SEM_DESFECHO = "TENTATIVA_SEM_DESFECHO"
    SEM_SUCESSO_CONFIRMADO = "SEM_SUCESSO_CONFIRMADO"
    FALHA_NA_ULTIMA_TENTATIVA = "FALHA_NA_ULTIMA_TENTATIVA"
    INTERVALO_EXECUCAO_EXPIRADO = "INTERVALO_EXECUCAO_EXPIRADO"
    HEARTBEAT_AUSENTE = "HEARTBEAT_AUSENTE"
    HEARTBEAT_EXPIRADO = "HEARTBEAT_EXPIRADO"
    SCHEDULE_AUSENTE = "SCHEDULE_AUSENTE"
    SCHEDULE_CONFLITANTE = "SCHEDULE_CONFLITANTE"
    TIMESTAMP_NO_FUTURO = "TIMESTAMP_NO_FUTURO"
    TIMEZONE_NAIVE = "TIMEZONE_NAIVE"
    INCONSISTENCIA_TEMPORAL = "INCONSISTENCIA_TEMPORAL"


def _normalizar_google_id(valor: str, campo: str) -> str:
    if not isinstance(valor, str):
        raise TypeError(f"{campo} deve ser string")
    normalizado = "".join(ch for ch in valor if not ch.isspace() and ch != "-")
    if not (normalizado.isdigit() and 6 <= len(normalizado) <= 12):
        raise ValueError(f"{campo} deve conter entre 6 e 12 digitos")
    return normalizado


def _normalizar_id_interno(valor: str, campo: str) -> str:
    if not isinstance(valor, str):
        raise TypeError(f"{campo} deve ser string")
    normalizado = valor.strip().lower()
    if not _ID_INTERNO.fullmatch(normalizado):
        raise ValueError(f"{campo} possui formato invalido")
    return normalizado


def _normalizar_tipo(valor: str) -> str:
    if not isinstance(valor, str):
        raise TypeError("tipo_coletor deve ser string")
    normalizado = valor.strip().upper()
    if not _TIPO_COLETOR.fullmatch(normalizado):
        raise ValueError("tipo_coletor possui formato invalido")
    return normalizado


def _normalizar_rotulo_erro(valor: str, campo: str) -> str:
    if not isinstance(valor, str):
        raise TypeError(f"{campo} deve ser string")
    normalizado = valor.strip()
    if not _ROTULO_ERRO.fullmatch(normalizado):
        raise ValueError(f"{campo} deve ser um rotulo publico nao-vazio")
    return normalizado


@dataclass(frozen=True, order=True)
class IdentidadeColetor:
    """Escopo canonico de um job dentro da hierarquia Google Ads."""

    login_customer_id: str
    customer_id: str
    coletor_id: str
    tipo_coletor: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "login_customer_id",
            _normalizar_google_id(self.login_customer_id, "login_customer_id"),
        )
        object.__setattr__(
            self,
            "customer_id",
            _normalizar_google_id(self.customer_id, "customer_id"),
        )
        object.__setattr__(
            self,
            "coletor_id",
            _normalizar_id_interno(self.coletor_id, "coletor_id"),
        )
        object.__setattr__(self, "tipo_coletor", _normalizar_tipo(self.tipo_coletor))


@dataclass(frozen=True)
class FalhaColetor:
    """Falha publica estruturada; detalhe bruto e deliberadamente proibido."""

    codigo: str
    classe: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "codigo", _normalizar_rotulo_erro(self.codigo, "codigo"))
        object.__setattr__(self, "classe", _normalizar_rotulo_erro(self.classe, "classe"))


@dataclass(frozen=True)
class ScheduleColetor:
    intervalo_esperado: timedelta
    tolerancia_atraso: timedelta | None = None
    tolerancia_heartbeat: timedelta | None = None
    desabilitado: bool = False
    schedule_id: str | None = None
    expressao: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.intervalo_esperado, timedelta):
            raise TypeError("intervalo_esperado deve ser timedelta")
        if self.intervalo_esperado <= timedelta(0):
            raise ValueError("intervalo_esperado deve ser estritamente positivo")
        for campo in ("tolerancia_atraso", "tolerancia_heartbeat"):
            valor = getattr(self, campo)
            if valor is not None and not isinstance(valor, timedelta):
                raise TypeError(f"{campo} deve ser timedelta")
            if valor is not None and valor < timedelta(0):
                raise ValueError(f"{campo} nao pode ser negativa")
        if not isinstance(self.desabilitado, bool):
            raise TypeError("desabilitado deve ser booleano")
        if self.schedule_id is not None:
            object.__setattr__(
                self,
                "schedule_id",
                _normalizar_id_interno(self.schedule_id, "schedule_id"),
            )
        if self.expressao is not None:
            expressao = self.expressao.strip()
            if not expressao:
                raise ValueError("expressao nao pode ser vazia")
            object.__setattr__(self, "expressao", expressao)


@dataclass(frozen=True)
class ReciboColetor:
    identidade: IdentidadeColetor
    schedule: ScheduleColetor | None = None
    ultima_tentativa_em: datetime | None = None
    ultimo_sucesso_em: datetime | None = None
    ultimo_heartbeat_em: datetime | None = None
    falha_ultima_tentativa: FalhaColetor | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identidade, IdentidadeColetor):
            raise TypeError("identidade deve ser IdentidadeColetor")
        if self.schedule is not None and not isinstance(self.schedule, ScheduleColetor):
            raise TypeError("schedule deve ser ScheduleColetor ou None")
        for campo in (
            "ultima_tentativa_em",
            "ultimo_sucesso_em",
            "ultimo_heartbeat_em",
        ):
            valor = getattr(self, campo)
            if valor is not None and not isinstance(valor, datetime):
                raise TypeError(f"{campo} deve ser datetime ou None")
        if self.falha_ultima_tentativa is not None:
            if not isinstance(self.falha_ultima_tentativa, FalhaColetor):
                raise TypeError("falha_ultima_tentativa deve ser FalhaColetor ou None")
            if self.ultima_tentativa_em is None:
                raise ValueError("falha estruturada exige ultima_tentativa_em")

    @property
    def login_customer_id(self) -> str:
        return self.identidade.login_customer_id

    @property
    def customer_id(self) -> str:
        return self.identidade.customer_id

    @property
    def coletor_id(self) -> str:
        return self.identidade.coletor_id

    @property
    def tipo_coletor(self) -> str:
        return self.identidade.tipo_coletor


@dataclass(frozen=True)
class ProjecaoSaudeColetor:
    identidade: IdentidadeColetor
    estado: EstadoSaudeColetor
    motivo: MotivoDiagnostico
    mensagem: str
    calculado_em: datetime
    tempo_desde_ultimo_sucesso: timedelta | None = None
    tempo_desde_ultima_tentativa: timedelta | None = None
    tempo_desde_ultimo_heartbeat: timedelta | None = None
    atraso_estimado: timedelta | None = None
    conflitos_detectados: tuple[str, ...] = ()

    @property
    def login_customer_id(self) -> str:
        return self.identidade.login_customer_id

    @property
    def customer_id(self) -> str:
        return self.identidade.customer_id

    @property
    def coletor_id(self) -> str:
        return self.identidade.coletor_id

    @property
    def tipo_coletor(self) -> str:
        return self.identidade.tipo_coletor


def _obter_agora(
    *,
    now: datetime | None,
    clock: Callable[[], datetime] | None,
) -> datetime:
    if (now is None) == (clock is None):
        raise ValueError("forneca exatamente um entre now e clock")
    instante = clock() if clock is not None else now
    if not isinstance(instante, datetime):
        raise TypeError("o relogio deve produzir datetime")
    if instante.tzinfo is None or instante.tzinfo.utcoffset(instante) is None:
        raise ValueError("o relogio deve ser timezone-aware")
    return instante.astimezone(timezone.utc)


def _timezone_aware(instante: datetime | None) -> bool:
    return (
        instante is None
        or instante.tzinfo is not None
        and instante.tzinfo.utcoffset(instante) is not None
    )


def _utc(instante: datetime | None) -> datetime | None:
    return instante.astimezone(timezone.utc) if instante is not None else None


def detectar_conflitos_schedules(
    schedules_por_coletor: Mapping[IdentidadeColetor, Sequence[ScheduleColetor]],
) -> dict[IdentidadeColetor, list[str]]:
    """Detecta duplicidade apenas dentro do mesmo tenant/job/tipo."""

    conflitos: dict[IdentidadeColetor, list[str]] = {}
    for identidade, schedules in schedules_por_coletor.items():
        if not isinstance(identidade, IdentidadeColetor):
            raise TypeError("a chave de schedule deve ser IdentidadeColetor")
        if len(schedules) <= 1:
            continue
        primeiro = schedules[0]
        if not isinstance(primeiro, ScheduleColetor):
            raise TypeError("schedule deve ser ScheduleColetor")
        detalhes: list[str] = []
        for indice, schedule in enumerate(schedules[1:], start=2):
            if not isinstance(schedule, ScheduleColetor):
                raise TypeError("schedule deve ser ScheduleColetor")
            divergencias: list[str] = []
            for campo in (
                "intervalo_esperado",
                "tolerancia_atraso",
                "tolerancia_heartbeat",
                "desabilitado",
                "expressao",
            ):
                if getattr(schedule, campo) != getattr(primeiro, campo):
                    divergencias.append(campo)
            if divergencias:
                detalhes.append(
                    f"schedule #{indice} diverge do #1 em {', '.join(divergencias)}"
                )
            else:
                detalhes.append(
                    "schedule duplicado no mesmo escopo "
                    f"({schedule.schedule_id or 'sem_id'} vs "
                    f"{primeiro.schedule_id or 'sem_id'})"
                )
        conflitos[identidade] = detalhes
    return conflitos


def projetar_saude_coletor(
    recibo: ReciboColetor,
    *,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    conflitos_conhecidos: Sequence[str] | None = None,
) -> ProjecaoSaudeColetor:
    if not isinstance(recibo, ReciboColetor):
        raise TypeError("recibo deve ser ReciboColetor")
    agora = _obter_agora(now=now, clock=clock)

    timestamps = (
        ("ultima_tentativa_em", recibo.ultima_tentativa_em),
        ("ultimo_sucesso_em", recibo.ultimo_sucesso_em),
        ("ultimo_heartbeat_em", recibo.ultimo_heartbeat_em),
    )
    for campo, instante in timestamps:
        if not _timezone_aware(instante):
            return ProjecaoSaudeColetor(
                recibo.identidade,
                EstadoSaudeColetor.INDETERMINADO,
                MotivoDiagnostico.TIMEZONE_NAIVE,
                f"{campo} precisa ser timezone-aware.",
                agora,
            )

    tentativa = _utc(recibo.ultima_tentativa_em)
    sucesso = _utc(recibo.ultimo_sucesso_em)
    heartbeat = _utc(recibo.ultimo_heartbeat_em)
    desde_tentativa = agora - tentativa if tentativa is not None else None
    desde_sucesso = agora - sucesso if sucesso is not None else None
    desde_heartbeat = agora - heartbeat if heartbeat is not None else None

    def resultado(
        estado: EstadoSaudeColetor,
        motivo: MotivoDiagnostico,
        mensagem: str,
        *,
        atraso: timedelta | None = None,
        conflitos: Sequence[str] = (),
    ) -> ProjecaoSaudeColetor:
        return ProjecaoSaudeColetor(
            identidade=recibo.identidade,
            estado=estado,
            motivo=motivo,
            mensagem=mensagem,
            calculado_em=agora,
            tempo_desde_ultimo_sucesso=desde_sucesso,
            tempo_desde_ultima_tentativa=desde_tentativa,
            tempo_desde_ultimo_heartbeat=desde_heartbeat,
            atraso_estimado=atraso,
            conflitos_detectados=tuple(conflitos),
        )

    if conflitos_conhecidos:
        return resultado(
            EstadoSaudeColetor.INDETERMINADO,
            MotivoDiagnostico.SCHEDULE_CONFLITANTE,
            "Ha schedules conflitantes no mesmo escopo do coletor.",
            conflitos=conflitos_conhecidos,
        )

    for campo, instante in (
        ("ultima_tentativa_em", tentativa),
        ("ultimo_sucesso_em", sucesso),
        ("ultimo_heartbeat_em", heartbeat),
    ):
        if instante is not None and instante > agora:
            return resultado(
                EstadoSaudeColetor.INDETERMINADO,
                MotivoDiagnostico.TIMESTAMP_NO_FUTURO,
                f"{campo} esta no futuro em relacao ao relogio injetado.",
            )

    if sucesso is not None and (tentativa is None or sucesso > tentativa):
        return resultado(
            EstadoSaudeColetor.INDETERMINADO,
            MotivoDiagnostico.INCONSISTENCIA_TEMPORAL,
            "Ultimo sucesso nao pode existir sem tentativa nem ser posterior a ela.",
        )

    if recibo.schedule is not None and recibo.schedule.desabilitado:
        return resultado(
            EstadoSaudeColetor.DESABILITADO,
            MotivoDiagnostico.COLETOR_DESABILITADO,
            "Coletor desabilitado no schedule.",
        )

    if tentativa is None and sucesso is None:
        return resultado(
            EstadoSaudeColetor.NUNCA_EXECUTADO,
            MotivoDiagnostico.SEM_EXECUCAO_PREVIA,
            "Nenhuma execucao foi registrada; heartbeat isolado nao prova execucao.",
        )

    if recibo.falha_ultima_tentativa is not None:
        falha = recibo.falha_ultima_tentativa
        return resultado(
            EstadoSaudeColetor.FALHOU,
            MotivoDiagnostico.FALHA_NA_ULTIMA_TENTATIVA,
            f"Ultima tentativa falhou ({falha.codigo}/{falha.classe}).",
        )

    if recibo.schedule is None:
        return resultado(
            EstadoSaudeColetor.INDETERMINADO,
            MotivoDiagnostico.SCHEDULE_AUSENTE,
            "Schedule ausente; nao ha baseline universal seguro.",
        )

    schedule = recibo.schedule
    tolerancia = schedule.tolerancia_atraso or timedelta(0)
    janela = schedule.intervalo_esperado + tolerancia

    if sucesso is None or tentativa is not None and tentativa > sucesso:
        if desde_tentativa is not None and desde_tentativa > janela:
            return resultado(
                EstadoSaudeColetor.ATRASADO,
                MotivoDiagnostico.SEM_SUCESSO_CONFIRMADO,
                "A tentativa excedeu a janela sem produzir sucesso confirmado.",
                atraso=desde_tentativa - janela,
            )
        return resultado(
            EstadoSaudeColetor.INDETERMINADO,
            MotivoDiagnostico.TENTATIVA_SEM_DESFECHO,
            "A tentativa mais recente ainda nao tem sucesso ou falha confirmada.",
        )

    if schedule.tolerancia_heartbeat is not None and heartbeat is None:
        return resultado(
            EstadoSaudeColetor.INDETERMINADO,
            MotivoDiagnostico.HEARTBEAT_AUSENTE,
            "Heartbeat obrigatorio ausente.",
        )

    atrasos: list[tuple[timedelta, MotivoDiagnostico, str]] = []
    if desde_sucesso is not None and desde_sucesso > janela:
        excesso = desde_sucesso - janela
        atrasos.append((
            excesso,
            MotivoDiagnostico.INTERVALO_EXECUCAO_EXPIRADO,
            "Ultimo sucesso confirmado excedeu a janela esperada.",
        ))
    if (
        schedule.tolerancia_heartbeat is not None
        and desde_heartbeat is not None
        and desde_heartbeat > schedule.tolerancia_heartbeat
    ):
        excesso = desde_heartbeat - schedule.tolerancia_heartbeat
        atrasos.append((
            excesso,
            MotivoDiagnostico.HEARTBEAT_EXPIRADO,
            "Heartbeat excedeu a tolerancia configurada.",
        ))
    if atrasos:
        excesso, motivo, mensagem = max(atrasos, key=lambda item: item[0])
        return resultado(
            EstadoSaudeColetor.ATRASADO,
            motivo,
            mensagem,
            atraso=excesso,
        )

    return resultado(
        EstadoSaudeColetor.SAUDAVEL,
        MotivoDiagnostico.OK,
        "Coletor tem sucesso confirmado dentro da janela esperada.",
    )


def avaliar_saude_coletores(
    recibos: Sequence[ReciboColetor],
    *,
    schedules_adicionais: Mapping[
        IdentidadeColetor, Sequence[ScheduleColetor]
    ] | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
) -> list[ProjecaoSaudeColetor]:
    agora = _obter_agora(now=now, clock=clock)
    mapa: dict[IdentidadeColetor, list[ScheduleColetor]] = {}
    for recibo in recibos:
        if not isinstance(recibo, ReciboColetor):
            raise TypeError("todos os recibos devem ser ReciboColetor")
        if recibo.schedule is not None:
            schedules = mapa.setdefault(recibo.identidade, [])
            if recibo.schedule not in schedules:
                schedules.append(recibo.schedule)
    if schedules_adicionais:
        for identidade, schedules in schedules_adicionais.items():
            mapa.setdefault(identidade, []).extend(schedules)
    conflitos = detectar_conflitos_schedules(mapa)
    return [
        projetar_saude_coletor(
            recibo,
            now=agora,
            conflitos_conhecidos=conflitos.get(recibo.identidade),
        )
        for recibo in recibos
    ]


@dataclass(frozen=True)
class _RegistroColeta:
    identidade_base: tuple[str, str, str]
    coletada_em: datetime
    estado: EstadoColeta
    erro_codigo: str | None
    erro_classe: str | None


def _datetime_de_registro(valor: Any) -> datetime:
    if isinstance(valor, datetime):
        instante = valor
    elif isinstance(valor, str):
        try:
            instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("coletada_em possui formato invalido") from exc
    else:
        raise TypeError("coletada_em deve ser datetime ou ISO-8601")
    if not _timezone_aware(instante):
        raise ValueError("coletada_em precisa ser timezone-aware")
    return instante.astimezone(timezone.utc)


def _registro_de_documento(
    documento: DocumentoColeta | Mapping[str, Any],
) -> _RegistroColeta:
    if isinstance(documento, DocumentoColeta):
        login_customer_id = documento.login_customer_id
        customer_id = documento.customer_id
        tipo = documento.tipo_sinal
        coletada_em = documento.coletada_em
        estado_bruto: EstadoColeta | str = documento.estado
        erro_codigo = documento.erro_codigo
        erro_classe = documento.erro_classe
    elif isinstance(documento, Mapping):
        login_customer_id = documento.get("login_customer_id")
        customer_id = documento.get("customer_id")
        tipo = documento.get("tipo_sinal")
        coletada_em = documento.get("coletada_em")
        estado_bruto = documento.get("estado")
        erro_codigo = documento.get("erro_codigo")
        erro_classe = documento.get("erro_classe")
    else:
        raise TypeError("documento deve ser DocumentoColeta ou Mapping")

    identidade = IdentidadeColetor(
        login_customer_id=login_customer_id,
        customer_id=customer_id,
        coletor_id="adaptador",
        tipo_coletor=tipo,
    )
    try:
        estado = (
            estado_bruto
            if isinstance(estado_bruto, EstadoColeta)
            else EstadoColeta(str(estado_bruto))
        )
    except ValueError as exc:
        raise ValueError("estado de coleta desconhecido") from exc
    instante = _datetime_de_registro(coletada_em)

    if estado is EstadoColeta.FALHOU:
        if not erro_codigo or not erro_classe:
            raise ValueError("registro falho exige erro_codigo e erro_classe")
    elif erro_codigo is not None or erro_classe is not None:
        raise ValueError("registro nao falho nao pode carregar erro")

    return _RegistroColeta(
        identidade_base=(
            identidade.login_customer_id,
            identidade.customer_id,
            identidade.tipo_coletor,
        ),
        coletada_em=instante,
        estado=estado,
        erro_codigo=str(erro_codigo) if erro_codigo is not None else None,
        erro_classe=str(erro_classe) if erro_classe is not None else None,
    )


def _falha_publica(registros: Sequence[_RegistroColeta]) -> FalhaColetor:
    pares = {(r.erro_codigo or "", r.erro_classe or "") for r in registros}
    if len(pares) != 1:
        return FalhaColetor("MULTIPLAS_FALHAS", "FalhaColeta")
    codigo, classe = next(iter(pares))
    try:
        return FalhaColetor(codigo, classe)
    except (TypeError, ValueError):
        return FalhaColetor("FALHA_COLETA", "ErroColeta")


def recibo_de_documentos(
    documentos: Sequence[DocumentoColeta | Mapping[str, Any]],
    *,
    coletor_id: str,
    schedule: ScheduleColetor | None,
    ultimo_heartbeat_em: datetime | None = None,
) -> ReciboColetor:
    """Adapta historico real/serializado sem consultar a persistencia.

    Todo o historico precisa pertencer ao mesmo MCC, conta e tipo de sinal. O
    estado mais recente define a ultima tentativa; qualquer falha no instante
    mais recente vence de forma fail-closed. ``erro_detalhe`` nunca e lido.
    """

    if not documentos:
        raise ValueError("ao menos um documento e necessario para derivar identidade")
    registros = [_registro_de_documento(documento) for documento in documentos]
    bases = {registro.identidade_base for registro in registros}
    if len(bases) != 1:
        raise ValueError("documentos misturam tenant, conta ou tipo de coletor")
    login_customer_id, customer_id, tipo_coletor = next(iter(bases))
    identidade = IdentidadeColetor(
        login_customer_id=login_customer_id,
        customer_id=customer_id,
        coletor_id=coletor_id,
        tipo_coletor=tipo_coletor,
    )
    ultima_tentativa = max(registro.coletada_em for registro in registros)
    sucessos = [
        registro.coletada_em
        for registro in registros
        if registro.estado is not EstadoColeta.FALHOU
    ]
    falhas_recentes = [
        registro
        for registro in registros
        if registro.coletada_em == ultima_tentativa
        and registro.estado is EstadoColeta.FALHOU
    ]
    return ReciboColetor(
        identidade=identidade,
        schedule=schedule,
        ultima_tentativa_em=ultima_tentativa,
        ultimo_sucesso_em=max(sucessos) if sucessos else None,
        ultimo_heartbeat_em=ultimo_heartbeat_em,
        falha_ultima_tentativa=(
            _falha_publica(falhas_recentes) if falhas_recentes else None
        ),
    )
