"""Leitura do fato canônico e do ledger para `custo_canonico`. Só GET.

Infraestrutura: PostgREST com a `service_role` do backend (a v12_04 só dá
SELECT a ela). Nenhuma regra mora aqui, e nada daqui importa `volc_ads` nem o
SDK do Google: esta leitura serve o Hub em tempo de render.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.trafego.custo_canonico import JOBS_DO_FATO, Periodo
from app.trafego.persistencia import _Cliente

COLUNAS_FATO = ",".join((
    "fato_id", "customer_id", "campaign_id", "metric_date", "campaign_name",
    "campaign_status", "advertising_channel_type", "volc_campaign_id",
    "custo_micros", "currency_code", "colhida_em", "origem_janela",
))
COLUNAS_LEDGER = ",".join((
    "execucao_id", "job", "origem_janela", "janela_inicio", "janela_fim",
    "resultado", "contas_aceitas", "contas_tentadas", "contas_recusadas", "encerrada_em",
))


def _lista_pg(valores: Sequence[str]) -> str:
    # customer_id só tem dígitos (CHECK da v12_04); o router já recusa o resto.
    return ",".join(valores)


class FonteDeCustoCanonico(_Cliente):
    async def linhas_do_fato(self, contas: Optional[Sequence[str]],
                             periodo: Periodo) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "select": COLUNAS_FATO,
            "metric_date": [f"gte.{periodo.inicio.isoformat()}",
                            f"lte.{periodo.fim.isoformat()}"],
            # Só a linha de campanha inteira: segmento repetiria o mesmo gasto.
            "segmentos": "eq.{}",
        }
        if contas:
            params["customer_id"] = f"in.({_lista_pg(contas)})"
        return await self._tudo("google_ads_campanha_dia", params, chave="fato_id")

    async def fechamentos(self, contas: Optional[Sequence[str]],
                          periodo: Periodo) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "select": COLUNAS_LEDGER,
            "tipo_lote": "eq.fechamento",
            "job": f"in.({','.join(JOBS_DO_FATO)})",
            "janela_inicio": f"lte.{periodo.fim.isoformat()}",
            "janela_fim": f"gte.{periodo.inicio.isoformat()}",
        }
        if contas:
            # `contas_tentadas` também: o coletor Python grava `contas_aceitas=[]`
            # quando a conta foi lida e não gastou (ver `contas_lidas`).
            lista = "{" + _lista_pg(contas) + "}"
            params["or"] = f"(contas_aceitas.ov.{lista},contas_tentadas.ov.{lista})"
        return await self._tudo("trafego_coleta_execucao", params, chave="execucao_id")
