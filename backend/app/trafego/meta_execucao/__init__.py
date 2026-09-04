"""First isolated Meta campaign-birth seam.

This package is intentionally isolated from routes, credentials and Supabase.
It compiles one narrow website-traffic recipe and exposes an injected Graph
transport. Importing it cannot call Meta or mutate external state.
"""

from .contrato import (
    AutorizacaoMeta,
    ErroDeNascimentoMeta,
    PlanoMetaPausado,
    ReferenciasMetaResolvidas,
    VariacaoEstaticaMeta,
)
from .compilador import PlanoCompiladoMeta, compilar_plano_pausado
from .ativos import AtivoDeCriacaoMeta, ResolvedorAtivosMeta
from .registro import PassoPreparadoMeta, RegistroSagaMeta, RegistroSagaMetaSupabase

__all__ = [
    "AutorizacaoMeta",
    "ErroDeNascimentoMeta",
    "PlanoMetaPausado",
    "ReferenciasMetaResolvidas",
    "VariacaoEstaticaMeta",
    "PlanoCompiladoMeta",
    "compilar_plano_pausado",
    "AtivoDeCriacaoMeta",
    "ResolvedorAtivosMeta",
    "PassoPreparadoMeta",
    "RegistroSagaMeta",
    "RegistroSagaMetaSupabase",
]
