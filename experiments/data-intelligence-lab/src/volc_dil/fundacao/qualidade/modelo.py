"""Protocolo mínimo de entrada e achados tipados da camada de qualidade (worker G).

Este módulo NÃO importa o contrato de observação do worker A (`volc_dil.fundacao.observacao`):
define só os nomes de campo que as checagens precisam. Os nomes espelham o contrato combinado
(status observed/zero_confirmed/missing/late/unavailable/unsupported/invalid/partial, relógios
observed_at/available_at/ingested_at, run/lote, payload_sha256). O integrador liga os dois via
`ObservacaoDQ.de_dict` / `RunDQ.de_dict`, que aceitam também os nomes das colunas reais
(v21 Google Ads e JoinAds v2).

Regra transversal: ausência nunca vira zero. Campo `None` significa "não sei", e toda checagem
trata `None` diferente de `0`.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping


class Severidade(str, enum.Enum):
    INFO = "info"
    AVISO = "aviso"
    ALTO = "alto"
    CRITICO = "critico"

    @property
    def nivel(self) -> int:
        return _NIVEL[self.value]


_NIVEL = {"ok": -1, "info": 0, "aviso": 1, "alto": 2, "critico": 3}


def nivel_severidade(valor: str | Severidade) -> int:
    """Nível numérico de uma severidade, aceitando também o rótulo `ok` das views SQL."""
    return _NIVEL[valor.value if isinstance(valor, Severidade) else valor]


class StatusDado(str, enum.Enum):
    """Vocabulário do contrato de observação (worker A). Mantido aqui só como protocolo."""

    OBSERVED = "observed"
    ZERO_CONFIRMED = "zero_confirmed"
    MISSING = "missing"
    LATE = "late"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"
    PARTIAL = "partial"


class StatusRun(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


SUCESSO = frozenset({StatusRun.COMPLETED, StatusRun.PARTIAL})


# --------------------------------------------------------------------------- utilidades de tempo


def para_datetime(valor: Any) -> datetime | None:
    """ISO-8601 ou datetime -> datetime com fuso. Sem fuso explícito é recusado (não adivinha)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        dt = valor
    else:
        texto = str(valor).strip().replace("Z", "+00:00")
        if " " in texto and "T" not in texto:
            texto = texto.replace(" ", "T", 1)
        # psql imprime "+00" (sem minutos); fromisoformat aceita no 3.11+.
        dt = datetime.fromisoformat(texto)
    if dt.tzinfo is None:
        raise ValueError(f"timestamp sem fuso horário: {valor!r}")
    return dt.astimezone(timezone.utc)


def para_date(valor: Any) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def iso(valor: date | datetime | None) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return valor.isoformat()


def numero(valor: Any) -> float | int | None:
    """Número JSON de verdade, ou `None`. Texto, booleano e nulo NÃO viram zero."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return valor
    return None


# --------------------------------------------------------------------------- achados


@dataclass(frozen=True)
class Achado:
    """Resultado tipado de uma checagem. `evidencia` só carrega agregados e chaves técnicas."""

    regra: str
    severidade: Severidade
    fonte: str
    grao: str
    janela: tuple[str | None, str | None]
    evidencia: Mapping[str, Any]
    mensagem: str
    chave: str | None = None

    def chave_dedupe(self) -> tuple[str, str, str, str | None, str | None, str | None]:
        return (self.regra, self.fonte, self.grao, self.chave, self.janela[0], self.janela[1])

    def como_dict(self) -> dict[str, Any]:
        return {
            "regra": self.regra,
            "severidade": self.severidade.value,
            "fonte": self.fonte,
            "grao": self.grao,
            "janela": list(self.janela),
            "chave": self.chave,
            "evidencia": dict(self.evidencia),
            "mensagem": self.mensagem,
        }


def ordenar_achados(achados: Iterable[Achado]) -> list[Achado]:
    """Ordem determinística: severidade desc, depois regra/fonte/grão/chave/janela."""
    return sorted(
        achados,
        key=lambda a: (
            -a.severidade.nivel,
            a.regra,
            a.fonte,
            a.grao,
            a.chave or "",
            a.janela[0] or "",
            a.janela[1] or "",
        ),
    )


# --------------------------------------------------------------------------- protocolo de entrada


_ALIASES_OBS = {
    "collected_at": "observed_at",
    "created_at": "ingested_at",
    "idempotency_key": "chave",
    "chave_idempotencia": "chave",
    "run_key": "run_id",
    "batch_id": "lote_id",
    "batch_key": "lote_id",
    "lote": "lote_id",
    "metrics": "metricas",
    "currency_code": "moeda",
    "customer_id": "conta",
    "campaign_id": "entidade",
    "collector": "coletor",
    "collector_version": "versao_coletor",
    "data_status": "status",
    "grain": "grao",
    "source": "fonte",
    "attributes": "atributos",
}


@dataclass(frozen=True)
class ObservacaoDQ:
    """Uma leitura de uma fonte num grão. Protocolo mínimo; o contrato rico é do worker A."""

    fonte: str
    grao: str
    chave: str  # chave natural/idempotente (entidade × grão × tempo), estável entre runs
    run_id: str
    status: StatusDado = StatusDado.OBSERVED
    coletor: str | None = None
    versao_coletor: int | str | None = None
    entidade: str | None = None
    conta: str | None = None
    metric_date: date | None = None
    metric_hour: int | None = None
    observed_at: datetime | None = None  # quando a fonte foi lida
    available_at: datetime | None = None  # quando ficou disponível para consumo
    ingested_at: datetime | None = None  # quando entrou no banco
    lote_id: str | None = None
    payload_sha256: str | None = None
    metricas: Mapping[str, Any] = field(default_factory=dict)
    atributos: Mapping[str, Any] = field(default_factory=dict)
    campos_payload: frozenset[str] | None = None
    moeda: str | None = None

    @classmethod
    def de_dict(cls, d: Mapping[str, Any]) -> "ObservacaoDQ":
        n: dict[str, Any] = {}
        for k, v in d.items():
            n[_ALIASES_OBS.get(k, k)] = v
        for k in ("observed_at", "available_at", "ingested_at"):
            n[k] = para_datetime(n.get(k))
        n["metric_date"] = para_date(n.get("metric_date"))
        if n.get("metric_hour") not in (None, ""):
            n["metric_hour"] = int(n["metric_hour"])
        n["status"] = StatusDado(n.get("status") or "observed")
        if n.get("campos_payload") is not None:
            n["campos_payload"] = frozenset(n["campos_payload"])
        for k in ("run_id", "chave", "lote_id"):
            if n.get(k) is not None:
                n[k] = str(n[k])
        campos = set(cls.__dataclass_fields__)
        desconhecidos = set(n) - campos
        if desconhecidos:
            atributos = dict(n.get("atributos") or {})
            for k in sorted(desconhecidos):
                atributos.setdefault(k, n.pop(k))
            n["atributos"] = atributos
        return cls(**n)

    def como_dict(self) -> dict[str, Any]:
        return {
            "fonte": self.fonte,
            "grao": self.grao,
            "chave": self.chave,
            "run_id": self.run_id,
            "status": self.status.value,
            "coletor": self.coletor,
            "versao_coletor": self.versao_coletor,
            "entidade": self.entidade,
            "conta": self.conta,
            "metric_date": iso(self.metric_date),
            "metric_hour": self.metric_hour,
            "observed_at": iso(self.observed_at),
            "available_at": iso(self.available_at),
            "ingested_at": iso(self.ingested_at),
            "lote_id": self.lote_id,
            "payload_sha256": self.payload_sha256,
            "metricas": dict(self.metricas),
            "atributos": dict(self.atributos),
            "campos_payload": sorted(self.campos_payload) if self.campos_payload is not None else None,
            "moeda": self.moeda,
        }


_ALIASES_RUN = {
    "run_key": "run_id",
    "collector": "coletor",
    "collector_version": "versao_coletor",
    "rows_written": "linhas_escritas",
    "observations_written": "linhas_escritas",
    "batches_written": "lotes",
    "window_start": "janela_inicio",
    "window_end": "janela_fim",
    "mode": "modo",
    "heartbeat_at": "ultimo_sinal",
    "last_heartbeat_at": "ultimo_sinal",
    "source": "fonte",
}


@dataclass(frozen=True)
class RunDQ:
    """Uma execução de coletor. `coletor` é o coletor LÓGICO (ex.: `n8n_joinads_v2:intraday`)."""

    run_id: str
    fonte: str
    coletor: str
    status: StatusRun
    started_at: datetime
    finished_at: datetime | None = None
    ultimo_sinal: datetime | None = None  # último sinal de vida (heartbeat ou lote gravado)
    linhas_escritas: int | None = None
    lotes: int | None = None
    versao_coletor: int | str | None = None
    janela_inicio: date | None = None
    janela_fim: date | None = None
    modo: str | None = None
    avisos: tuple[Mapping[str, Any], ...] = ()

    @classmethod
    def de_dict(cls, d: Mapping[str, Any]) -> "RunDQ":
        n: dict[str, Any] = {}
        for k, v in d.items():
            n[_ALIASES_RUN.get(k, k)] = v
        n["status"] = StatusRun(n["status"])
        for k in ("started_at", "finished_at", "ultimo_sinal"):
            n[k] = para_datetime(n.get(k))
        for k in ("janela_inicio", "janela_fim"):
            n[k] = para_date(n.get(k))
        n["run_id"] = str(n["run_id"])
        n["avisos"] = tuple(n.get("avisos") or ())
        campos = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in n.items() if k in campos})

    def como_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "fonte": self.fonte,
            "coletor": self.coletor,
            "status": self.status.value,
            "started_at": iso(self.started_at),
            "finished_at": iso(self.finished_at),
            "ultimo_sinal": iso(self.ultimo_sinal),
            "linhas_escritas": self.linhas_escritas,
            "lotes": self.lotes,
            "versao_coletor": self.versao_coletor,
            "janela_inicio": iso(self.janela_inicio),
            "janela_fim": iso(self.janela_fim),
            "modo": self.modo,
            "avisos": [dict(a) for a in self.avisos],
        }


@dataclass(frozen=True)
class CoberturaSensorDia:
    """Agregado diário do sensor (sem `sid`/`pid`): base da métrica de cobertura de atribuição."""

    dia: date
    sessoes_pagas: int | None
    pagas_com_campanha: int | None
    pagas_com_source: int | None = None
    sessoes_total: int | None = None

    @classmethod
    def de_dict(cls, d: Mapping[str, Any]) -> "CoberturaSensorDia":
        return cls(
            dia=para_date(d["dia"]),
            sessoes_pagas=None if d.get("sessoes_pagas") is None else int(d["sessoes_pagas"]),
            pagas_com_campanha=None if d.get("pagas_com_campanha") is None else int(d["pagas_com_campanha"]),
            pagas_com_source=None if d.get("pagas_com_source") is None else int(d["pagas_com_source"]),
            sessoes_total=None if d.get("sessoes_total") is None else int(d["sessoes_total"]),
        )

    def como_dict(self) -> dict[str, Any]:
        return {
            "dia": iso(self.dia),
            "sessoes_pagas": self.sessoes_pagas,
            "pagas_com_campanha": self.pagas_com_campanha,
            "pagas_com_source": self.pagas_com_source,
            "sessoes_total": self.sessoes_total,
        }
