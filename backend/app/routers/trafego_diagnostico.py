"""Router de Diagnóstico Persistido de Tráfego — P05-T07.

Endpoint canônico:
GET /api/trafego/campanhas/{volc_campaign_id}/diagnostico

Lê exclusivamente o ledger persistido v12 já existente.
Não consulta Google Ads e não aceita campaign_id externo como fallback.
Preserva identidade interna, autenticação e isolamento de conta.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path

from app.config import Settings, get_settings
from app.seguranca.identidade import Identidade, exigir_usuario
from app.services.supabase_service import SupabaseService
from app.trafego.diagnostico_persistido import (
    CampanhaNaoEncontradaError,
    RespostaDoDiagnostico,
    IdentificadorInvalidoError,
    ServicoIndisponivelError,
    SupabaseRepositorioDiagnostico,
    obter_diagnostico_campanha,
)

log = logging.getLogger("volc.trafego.diagnostico_rota")

router = APIRouter(
    prefix="/api/trafego",
    tags=["trafego-diagnostico"],
    dependencies=[Depends(exigir_usuario)],
)


def obter_repositorio_diagnostico(
    settings: Settings = Depends(get_settings),
) -> SupabaseRepositorioDiagnostico:
    """Provedor do repositório do ledger persistido.

    Permite injeção e sobrescrita hermética em testes.
    """
    supa = SupabaseService(settings)
    return SupabaseRepositorioDiagnostico(supa)


@router.get(
    "/campanhas/{volc_campaign_id}/diagnostico",
    response_model=RespostaDoDiagnostico,
    summary="Diagnóstico persistido de campanha de Search pelo ledger v12",
)
async def get_diagnostico_campanha(
    volc_campaign_id: str = Path(
        ...,
        description="ID interno canônico da campanha (volc_campaign_id)",
        example="volc_cmp_01j7x8k2m9p4",
    ),
    identidade: Identidade = Depends(exigir_usuario),
    repositorio: SupabaseRepositorioDiagnostico = Depends(obter_repositorio_diagnostico),
) -> RespostaDoDiagnostico:
    """Retorna o diagnóstico persistido de uma campanha de Search a partir do ledger v12.

    Regras:
    - Lê exclusivamente dados persistidos no ledger v12;
    - Não faz chamadas de rede à API do Google Ads;
    - Não aceita campaign_id externo do Google Ads como fallback;
    - Diferencia explicitamente dado presente, zeros medidos, campos ausentes,
      coleta pendente, falha de coleta e leitura antiga.
    """
    try:
        return await obter_diagnostico_campanha(
            volc_campaign_id=volc_campaign_id,
            repositorio=repositorio,
        )
    except IdentificadorInvalidoError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CampanhaNaoEncontradaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServicoIndisponivelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("falha ao processar diagnóstico persistido para '%s'", volc_campaign_id)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao processar o diagnóstico persistido da campanha.",
        ) from exc
