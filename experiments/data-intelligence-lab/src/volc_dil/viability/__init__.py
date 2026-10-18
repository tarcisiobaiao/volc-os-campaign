"""VOLC Viability & Marginal Economics Kernel v1 (offline/shadow).

Núcleo determinístico que avalia, ANTES de gastar, se uma campanha, funil ou vertical tem
fronteira econômica plausível: CPC máximo sustentável, RPC necessário, teto do primeiro
experimento e onde a expansão marginal destrói valor.

Não chama rede, banco, Google, n8n, GTM nem modelo de linguagem. Não emite ação externa.
Dinheiro só em micros inteiros (`volc_dil.contracts.Dinheiro`); razões em `Fraction`/`Decimal`.
"""
from __future__ import annotations

from .contrato import (  # noqa: F401
    Autorizacao,
    Cambio,
    ContratoViabilidadeViolado,
    EntradaViabilidade,
    Evidencia,
    JanelaObservada,
    MedidaContagem,
    MedidaMonetaria,
    PerdaMaxima,
    Taxa,
    hash_entrada,
)

VERSAO_KERNEL = "viability-kernel@2.0.0"
