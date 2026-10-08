"""Gestão de campanhas no ar — `/api/trafego/gestao`. Contrato: docs/contracts/GADS-GESTAO-v1.md.

Este router só traduz HTTP ↔ caso de uso (`app.trafego.gestao.application`).
Regra, persistência e integração moram fora daqui (CLAUDE.md: routers não
concentram as três).

## Os portões

· `exigir_usuario` no APIRouter: toda rota, inclusive a que alguém adicionar
  depois, nasce exigindo sessão — mesma disciplina de `routers/trafego.py`.
· `exigir_admin` nas rotas que ESCREVEM NO GOOGLE (aplicar, reverter) e nas que
  AUTORIZAM a escrita (aprovar, recusar): aprovar é a trava 1 de T1 — quem
  aprova responde pelo gasto, e essa autoridade é a mesma de quem aplica.
· Conta fora da casa: 403, decidido no caso de uso (`escopo.conta_da_casa`)
  ANTES de qualquer leitura no Google ou escrita no ledger — inclusive nas
  rotas por id, em que a conta vem de `alvo_chave` da proposta.

## Por que o motor é importado tarde

`volc_ads` puxa o SDK do Google Ads. O router é importado por `main.py` na
subida; se ele importasse o motor no topo, o backend inteiro deixaria de subir
num ambiente sem o SDK — Pautador e Redator inclusive. O provedor
`obter_gestao` é quem importa, na primeira requisição.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings, get_settings
from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario
from app.trafego.gestao.application.erros import ErroDeGestao

log = logging.getLogger("volc.trafego.gestao.rota")

router = APIRouter(prefix="/api/trafego/gestao", tags=["trafego-gestao"],
                   dependencies=[Depends(exigir_usuario)])


def obter_gestao(settings: Settings = Depends(get_settings)) -> Any:
    """A fachada dos casos de uso sobre a infraestrutura real. Sobrescrita nos testes."""
    from app.trafego.gestao.infrastructure.conta_google import (  # noqa: PLC0415
        ContaGoogleAds, garantir_volc_ads)

    try:
        garantir_volc_ads()
    except ErroDeGestao as exc:
        raise HTTPException(status_code=exc.status, detail=exc.corpo()) from exc
    from app.trafego.gestao.application.casos_de_uso import Gestao  # noqa: PLC0415
    from app.trafego.gestao.infrastructure.repositorio_postgrest import (  # noqa: PLC0415
        RepositorioGestaoPostgrest)

    repo = RepositorioGestaoPostgrest(str(getattr(settings, "supabase_url", "") or ""),
                                      str(getattr(settings, "supabase_service_role_key", "")
                                          or ""))
    return Gestao(repo, ContaGoogleAds())


def _quem(identidade: Identidade) -> str:
    """O autor que vai para `criada_por`/`decidida_por` como `humano:<quem>`."""
    return identidade.email or identidade.sub


async def _rodar(coro: Any) -> Any:
    try:
        return await coro
    except ErroDeGestao as exc:
        if exc.status >= 500:
            log.warning("gestão indisponível: %s", exc)
        raise HTTPException(status_code=exc.status, detail=exc.corpo()) from exc


# ── corpos ──────────────────────────────────────────────────────────────────


class PedidoDeProposta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(..., description="Conta Google Ads (só dígitos ou com hífen).")
    acao: Dict[str, Any] = Field(..., description="{tipo, ...campos do tipo} — ver o contrato.")
    motivo: str = Field(..., min_length=1, description="Por que mudar. Vira a explicação "
                                                       "do diagnóstico que o aprovador lê.")
    regra_chave: Optional[str] = Field(None, description="Regra vigente que limita a proposta. "
                                                         "Padrão: gestao_manual_google.")
    validade_horas: Optional[int] = Field(None, ge=1, le=168)


class PedidoDeDecisao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: Optional[str] = None
    diff_apresentado: Optional[Dict[str, Any]] = Field(
        None, description="O diff que a tela MOSTROU (valor_atual, valor_proposto, …).")


class PedidoDeReversao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(..., min_length=1)
    acompanhamento_id: Optional[str] = None


class PedidoDeImportacao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    campaign_id: str


# ── leitura ─────────────────────────────────────────────────────────────────


@router.get("/propostas")
async def painel(customer_id: str = Query(...),
                 estado: Optional[str] = Query(None),
                 limite: int = Query(50, ge=1, le=200),
                 gestao: Any = Depends(obter_gestao)) -> Dict[str, Any]:
    """`trafego_proposta_painel` da conta: diff, regra, diagnóstico, decisão, `proximo_passo`."""
    linhas = await _rodar(gestao.painel(customer_id, estado=estado, limite=limite))
    return {"propostas": linhas, "total": len(linhas)}


@router.get("/recomendacoes")
async def recomendacoes(customer_id: str = Query(...),
                        gestao: Any = Depends(obter_gestao)) -> Dict[str, Any]:
    """GAQL `recommendation` (não dispensadas). Leitura pura; aplicar vira proposta."""
    linhas = await _rodar(gestao.recomendacoes(customer_id))
    return {"recomendacoes": linhas, "total": len(linhas)}


# ── proposta e decisão ──────────────────────────────────────────────────────


@router.post("/propostas", status_code=201)
async def propor(response: Response, corpo: PedidoDeProposta = Body(...),
                 identidade: Identidade = Depends(exigir_usuario),
                 gestao: Any = Depends(obter_gestao)) -> Dict[str, Any]:
    """Lê o "antes" na conta e grava evidência → diagnóstico → proposta. Não escreve no Google.

    201 quando nasce; 200 quando a MESMA proposta (mesmo conteúdo sobre o mesmo
    "antes") já existia e ainda está viva. Anterior recusada/expirada/revertida/
    aplicada não segura o pedido: nasce outra (201). O corpo é o mesmo nos dois.
    """
    saida = await _rodar(gestao.propor(
        corpo.customer_id, corpo.acao, motivo=corpo.motivo, autor=_quem(identidade),
        regra_chave=corpo.regra_chave, validade_horas=corpo.validade_horas))
    if saida.get("ja_existia"):
        response.status_code = 200
    return saida


@router.post("/propostas/{proposta_id}/aprovar", dependencies=[Depends(exigir_admin)])
async def aprovar(proposta_id: str, corpo: PedidoDeDecisao = Body(...),
                  identidade: Identidade = Depends(exigir_usuario),
                  gestao: Any = Depends(obter_gestao)) -> Dict[str, Any]:
    return await _rodar(gestao.aprovar(proposta_id, "aprovada", motivo=corpo.motivo,
                                       aprovador=_quem(identidade),
                                       diff_apresentado=corpo.diff_apresentado))


@router.post("/propostas/{proposta_id}/recusar", dependencies=[Depends(exigir_admin)])
async def recusar(proposta_id: str, corpo: PedidoDeDecisao = Body(...),
                  identidade: Identidade = Depends(exigir_usuario),
                  gestao: Any = Depends(obter_gestao)) -> Dict[str, Any]:
    return await _rodar(gestao.aprovar(proposta_id, "recusada", motivo=corpo.motivo,
                                       aprovador=_quem(identidade),
                                       diff_apresentado=corpo.diff_apresentado or {}))


# ── escrita no Google ───────────────────────────────────────────────────────


@router.post("/propostas/{proposta_id}/aplicar", dependencies=[Depends(exigir_admin)])
async def aplicar(proposta_id: str, identidade: Identidade = Depends(exigir_usuario),
                  gestao: Any = Depends(obter_gestao)) -> Dict[str, Any]:
    """Relê o "antes", grava `em_voo`, ensaia (validate_only) e escreve pela trava. Idempotente."""
    return await _rodar(gestao.aplicar(proposta_id, executor=_quem(identidade)))


@router.post("/aplicacoes/{aplicacao_id}/verificar")
async def verificar(aplicacao_id: str, identidade: Identidade = Depends(exigir_usuario),
                    gestao: Any = Depends(obter_gestao)) -> Dict[str, Any]:
    """Relê a conta e compara com o proposto → `trafego_acompanhamento` (verificacao)."""
    return await _rodar(gestao.verificar(aplicacao_id, observador=_quem(identidade)))


@router.post("/aplicacoes/{aplicacao_id}/reverter", dependencies=[Depends(exigir_admin)])
async def reverter(aplicacao_id: str, corpo: PedidoDeReversao = Body(...),
                   identidade: Identidade = Depends(exigir_usuario),
                   gestao: Any = Depends(obter_gestao)) -> Dict[str, Any]:
    return await _rodar(gestao.reverter(aplicacao_id, motivo=corpo.motivo,
                                        autor=_quem(identidade),
                                        acompanhamento_id=corpo.acompanhamento_id))


# ── identidade ──────────────────────────────────────────────────────────────


@router.post("/campanhas/importar", status_code=201)
async def importar(response: Response, corpo: PedidoDeImportacao = Body(...),
                   identidade: Identidade = Depends(exigir_usuario),
                   gestao: Any = Depends(obter_gestao)) -> Dict[str, Any]:
    """Identidade em `trafego_campanha` (procedência `descoberta`) para gerir campanha externa.

    201 quando a identidade nasce; 200 quando já existia (idempotente).
    """
    saida = await _rodar(gestao.importar_campanha_externa(
        corpo.customer_id, corpo.campaign_id, autor=_quem(identidade)))
    if saida.get("ja_existia"):
        response.status_code = 200
    return saida
