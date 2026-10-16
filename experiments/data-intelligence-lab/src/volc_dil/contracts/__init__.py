"""Contrato mínimo de dado econômico confiável do laboratório (Fase 1).

Stdlib apenas. Ver `docs/data-intelligence/CONTRATO-DADO-ECONOMICO.md`.
"""
from .aggregate import (
    Agregado,
    Circularidade,
    Contribuicao,
    IdentidadeIncompativel,
    ValueKindsMisturados,
    agregar,
    contribuicao,
    exigir_mesma_identidade,
    rotulo_economico,
    verificar_nao_circular,
)
from .fingerprint import json_canonico, manifesto_execucao, sha256_arquivo, sha256_de, versoes
from .money import MICROS, Dinheiro, MoedasDiferentes
from .observation import ChaveUnidade, ContratoViolado, Observacao
from .snapshot import ESQUEMA_SNAPSHOT, Snapshot, VazamentoDeFuturo, VersaoAmbigua, verificar_sem_futuro
from .vocab import (
    RECEITA_CONTABIL,
    ROTULO_ECONOMICO,
    Cobertura,
    EstadoMedida,
    Maturidade,
    Metrica,
    MetodoAtribuicao,
    ValueKind,
)

__all__ = [
    "Agregado", "ChaveUnidade", "Circularidade", "Cobertura", "Contribuicao", "ContratoViolado",
    "Dinheiro", "ESQUEMA_SNAPSHOT", "EstadoMedida", "IdentidadeIncompativel", "MICROS", "Maturidade",
    "Metrica", "MetodoAtribuicao", "MoedasDiferentes", "Observacao", "RECEITA_CONTABIL",
    "ROTULO_ECONOMICO", "Snapshot", "ValueKind", "ValueKindsMisturados", "VazamentoDeFuturo",
    "VersaoAmbigua", "agregar", "contribuicao", "exigir_mesma_identidade", "json_canonico",
    "manifesto_execucao", "rotulo_economico", "sha256_arquivo", "sha256_de", "verificar_nao_circular",
    "verificar_sem_futuro", "versoes",
]
