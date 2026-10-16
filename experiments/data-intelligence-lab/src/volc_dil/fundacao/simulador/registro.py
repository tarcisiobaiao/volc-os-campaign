"""Registro de observação emitido pelo observador simulado (independente do worker A).

Os 17 campos de ``CAMPOS_CONTRATO`` têm exatamente os nomes do contrato de observação da
missão (grafia ASCII: ``grão`` → ``grao``; ``valor micros ou None`` → ``valor`` + ``unidade``,
porque contagens também são observadas). Os campos de ``CAMPOS_EXTRAS`` são do simulador e
podem ser descartados pelo integrador. Mapeamento completo em 07-SIMULATOR-LAB.md §3.4.

Invariantes que o simulador garante (testados em ``test_simulador_status.py``):

- ``valor is None`` ⇔ ``status ∈ {missing, unavailable, unsupported, invalid}``;
- ``status == zero_confirmed`` ⇒ ``valor == 0``; ``partial``/``observed``/``late`` ⇒ ``valor`` int ≥ 0;
- ``unidade == "micros"`` ⇒ ``moeda`` ∈ ISO-4217 (BRL/USD); ``unidade == "contagem"`` ⇒ ``moeda is None``;
- ``observed_at ≤ available_at ≤ ingested_at``; ``available_at < janela_fim`` só em leitura intradiária;
- ``late`` ⇒ ``available_previsto`` preenchido e ``available_at > available_previsto``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

STATUS = ("observed", "zero_confirmed", "missing", "late", "unavailable", "unsupported", "invalid", "partial")
STATUS_COM_VALOR = frozenset({"observed", "zero_confirmed", "late", "partial"})
STATUS_SEM_VALOR = frozenset({"missing", "unavailable", "unsupported", "invalid"})
TIPOS_LEITURA = ("intradia", "d1", "releitura", "backfill", "dimensao")
MATURIDADES = ("intradiaria", "preliminar", "final", "nao_aplicavel")
METRICAS_MONETARIAS = frozenset({"cost", "revenue"})
METRICAS = ("cost", "clicks", "impressions", "revenue", "pageviews", "sessions", "destino")

CAMPOS_CONTRATO = (
    "fonte", "conta", "entidade", "grao", "metrica", "valor", "moeda", "janela_inicio", "janela_fim",
    "timezone", "observed_at", "available_at", "ingested_at", "run_id", "payload_sha256", "status", "motivo",
)
CAMPOS_EXTRAS = (
    "obs_id", "leitura_id", "unidade", "tipo_leitura", "maturidade", "cobertura_ate", "entidade_tipo",
    "custom_key_solicitada", "custom_key_efetiva", "dimensoes", "available_previsto", "cenario", "natureza",
)


@dataclass(frozen=True, slots=True)
class RegistroObservacao:
    fonte: str
    conta: str
    entidade: str
    grao: tuple[str, ...]
    metrica: str
    valor: Optional[int]
    moeda: Optional[str]
    janela_inicio: str
    janela_fim: str
    timezone: str
    observed_at: str
    available_at: str
    ingested_at: str
    run_id: str
    payload_sha256: str
    status: str
    motivo: Optional[str]
    obs_id: str
    leitura_id: str
    unidade: str
    tipo_leitura: str
    maturidade: str
    cobertura_ate: Optional[str]
    entidade_tipo: str
    custom_key_solicitada: Optional[str]
    custom_key_efetiva: Optional[str]
    dimensoes: tuple[tuple[str, str], ...]
    available_previsto: Optional[str]
    cenario: str
    natureza: str = "sintetico"

    def como_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["grao"] = list(self.grao)
        d["dimensoes"] = [list(x) for x in self.dimensoes]
        return d

    def contrato(self) -> dict[str, Any]:
        """Só os 17 campos do contrato de observação da missão."""
        d = self.como_dict()
        return {k: d[k] for k in CAMPOS_CONTRATO}


@dataclass(frozen=True, slots=True)
class Gabarito:
    """Verdade por registro, para AVALIAÇÃO. Nunca é entrada de consumidor.

    ``valor_verdade_final``: valor fechado verdadeiro do fato pedido (campanha × métrica × dia),
    na moeda da fonte; para registro com chave trocada é o valor da campanha PEDIDA.
    ``valor_verdade_cobertura``: verdade restrita às horas cobertas pela leitura (intradiária).
    ``restatement_pendente``: valor_emitido − valor_verdade_final quando há valor (custo D0/D-1).
    """

    obs_id: str
    campanha_pedida: Optional[str]
    valor_verdade_final: Optional[int]
    valor_verdade_cobertura: Optional[int]
    restatement_pendente: Optional[int]
    armadilhas: tuple[str, ...]

    def como_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["armadilhas"] = list(self.armadilhas)
        return d
