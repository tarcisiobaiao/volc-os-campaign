"""Remoção de campanha pelo funil único de escrita.

⚠️ Por que este módulo existe (medido em 08/10/2026): `POST /remover` chamava
`CampaignService.mutate_campaigns` direto do router. Era a única operação
destrutiva do sistema e a única escrita que não passava por `gads.client.mutar`
nem deixava rastro no banco — uma campanha removida sumia sem ninguém saber
quem, quando ou por quê. `REMOVED` é terminal no Google Ads: não há desfazer.

O desenho:
1. a intenção vai para o diário (`trafego_evento`) ANTES do mutate; sem
   diário, não remove;
2. o mutate sai por `mutar()` (trava de dois fatores + retry tipado);
3. o desfecho vai para o diário; se só ESSA gravação falhar, a remoção já
   aconteceu e quem chama recebe um aviso — mentir que não removeu seria pior.

Este módulo não faz HTTP de entrada nem conhece FastAPI.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

PRODUTOR = "backend:remover"
TIPO_PEDIDA = "campanha.remocao_pedida"
TIPO_REMOVIDA = "campanha.removida"
TIPO_FALHOU = "campanha.remocao_falhou"


def chave_de_remocao(customer_id: str, campaign_id: str, quando: datetime) -> str:
    """Uma chave por TENTATIVA. Os três eventos de uma tentativa a compartilham."""
    return f"remover:{customer_id}:{int(campaign_id)}:{quando.isoformat()}"


def evento(
    tipo: str,
    *,
    chave: str,
    customer_id: str,
    campaign_id: str,
    carga: Dict[str, Any],
    quando: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Linha de `trafego_evento` (v9_01). Sem FK de propósito: a falha também é registrada."""
    return {
        "ocorrido_em": (quando or datetime.now(timezone.utc)).isoformat(),
        "tipo": tipo,
        "chave_de_agrupamento": chave,
        "produtor": PRODUTOR,
        "sujeito_tipo": "campanha",
        "sujeito_id": str(int(campaign_id)),
        "customer_id": str(customer_id),
        "carga": carga,
    }


def operacao_de_remocao(get_type: Callable[[str], Any], customer_id: str,
                        campaign_id: str) -> Any:
    """`MutateOperation` com `campaign_operation.remove`, pronta para `mutar()`."""
    op = get_type("MutateOperation")
    op.campaign_operation.remove = f"customers/{customer_id}/campaigns/{int(campaign_id)}"
    return op


def ler_campanha(login_customer_id: str, customer_id: str,
                 campaign_id: str) -> tuple[str, str]:
    """(nome, status) da campanha na conta. ("", "") quando ela não existe."""
    from volc_ads.gads.client import buscar  # noqa: PLC0415

    q = (f"SELECT campaign.id, campaign.name, campaign.status "
         f"FROM campaign WHERE campaign.id = {int(campaign_id)}")
    for r in buscar(customer_id, q, login_customer_id=login_customer_id):
        return r.campaign.name, r.campaign.status.name
    return "", ""


def remover(login_customer_id: str, customer_id: str, campaign_id: str,
            motivo: str) -> str:
    """Remove pela porta única de escrita. Devolve o resource name removido."""
    from volc_ads.gads import modo  # noqa: PLC0415
    from volc_ads.gads.client import cliente, mutar  # noqa: PLC0415

    op = operacao_de_remocao(cliente(login_customer_id).get_type, customer_id, campaign_id)
    with modo.destravar(motivo):
        resposta = mutar(customer_id, [op], login_customer_id=login_customer_id)
    return resposta.mutate_operation_responses[0].campaign_result.resource_name
