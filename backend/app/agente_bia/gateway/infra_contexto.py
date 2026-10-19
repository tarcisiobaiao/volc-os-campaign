"""Leitura real do contexto de campanha. Só GET no PostgREST, só fontes canônicas.

Compõe as duas fontes que já servem o Hub — `FonteDeReconciliacao` (snapshot
da campanha) e `FonteDeCustoCanonico` (ledger de fechamento) — e acrescenta UMA
leitura: as linhas do fato campanha-dia DESTA campanha, com a coluna
`conversoes`. Mesma tabela, mesmos filtros (`segmentos = {}`), mesmo cliente
paginado; a diferença é o filtro por campanha e a coluna a mais.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.trafego.custo_canonico import Periodo
from app.trafego.custo_canonico_fonte import COLUNAS_FATO, FonteDeCustoCanonico
from app.trafego.persistencia import FonteDeReconciliacao

_DIGITOS = frozenset("0123456789")


def _so_digitos(v: str) -> bool:
    return bool(v) and set(v) <= _DIGITOS


class FonteDoContextoSupabase(FonteDeCustoCanonico):
    def __init__(self, base: str, chave: str) -> None:
        super().__init__(base, chave)
        self._snapshot = FonteDeReconciliacao(base, chave)

    async def uma_campanha(self, volc_campaign_id: str) -> Optional[Dict[str, Any]]:
        return await self._snapshot.uma_campanha(volc_campaign_id)

    async def fechamentos(self, contas: Sequence[str], periodo: Periodo) -> List[Dict[str, Any]]:  # type: ignore[override]
        return await super().fechamentos(list(contas), periodo)

    async def linhas_da_campanha(self, customer_id: str, campaign_id: str,
                                 periodo: Periodo) -> List[Dict[str, Any]]:
        # Os dois ids vêm do snapshot, não do navegador; ainda assim só dígitos
        # entram no filtro (CHECK da v12_04), para nenhum valor virar operador.
        if not (_so_digitos(customer_id) and _so_digitos(campaign_id)):
            return []
        params: Dict[str, Any] = {
            "select": COLUNAS_FATO + ",conversoes",
            "customer_id": f"eq.{customer_id}",
            "campaign_id": f"eq.{campaign_id}",
            "metric_date": [f"gte.{periodo.inicio.isoformat()}",
                            f"lte.{periodo.fim.isoformat()}"],
            "segmentos": "eq.{}",
        }
        return await self._tudo("google_ads_campanha_dia", params, chave="fato_id")
