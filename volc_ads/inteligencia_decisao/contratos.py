"""Contratos pequenos do kernel, alinhados ao ledger v10_02.

`RegraDeOtimizacao` e `avaliar_suficiencia` continuam sendo a autoridade. Este
módulo apenas os importa para a fatia nova; não cria uma segunda definição.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Tuple

try:  # backend executado com PYTHONPATH=backend
    from app.trafego.intencao import (  # type: ignore
        RegraDeOtimizacao,
        Suficiencia,
        avaliar_suficiencia,
    )
except ImportError:  # testes/CLI executados a partir da raiz do monorepo
    from backend.app.trafego.intencao import (  # type: ignore
        RegraDeOtimizacao,
        Suficiencia,
        avaliar_suficiencia,
    )


@dataclass(frozen=True)
class EventoDeDecisao:
    """Evento tipado e append-only: fato observado, nunca ordem de mutação."""

    evento_id: str
    tipo: str
    entidade: str
    observado_em: str
    janela_inicio: str
    janela_fim: str
    evidencia_refs: Tuple[str, ...]
    severidade: str
    dedup_key: str
    resolucao: str = "aberta"

    def serializar(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PropostaTipada:
    """Proposta compatível com o ciclo v10_02, sem autorização ou executor."""

    proposta_id: str
    idempotency_key: str
    evento_id: str
    regra_chave: str
    regra_versao: int
    operacao: str
    alvo: str
    antes: Optional[str]
    depois: Optional[str]
    evidencias: Tuple[Mapping[str, Any], ...]
    confianca: str
    bloqueios: Tuple[str, ...]
    aprovacao: str = "nao_submetida"
    aplicacao: str = "nao_executada"
    recibo: None = None

    def serializar(self) -> dict[str, Any]:
        return asdict(self)
