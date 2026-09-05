"""Safe control plane for compiling and remotely validating the Meta P0 plan.

This router has no create, approval or activation endpoint — those live in
``trafego_meta_criacao``, behind their own flags. Here we only read
account-scoped assets, compile a deterministic plan and, behind an independent
flag plus an explicit click, call Meta with ``execution_options=validate_only``.

## A única escrita desta rota, e por que ela existe

Depois de a Meta ACEITAR a validação, o resultado é gravado como recibo durável
(``trafego_meta_create_record_validation``). Sem essa gravação a prova de que o
plano foi validado existiria apenas no corpo da resposta HTTP — quer dizer,
apenas no navegador — e a aprovação teria que acreditar no cliente quando ele
diz "eu fui validado". Um recibo verde inventado pelo browser é exatamente o
que separa uma autoridade de um enfeite.

A gravação **não** é condição para responder. Ela depende de
``META_CREATE_LEDGER_WRITE_ENABLED``, que pode estar fechada; nesse caso a
validação continua valendo e a resposta declara, com todas as letras, que a
prova não foi persistida — e a aprovação vai recusar mais tarde, por falta de
recibo, em vez de aceitar uma afirmação sem lastro.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.routers.meta_local import _credencial_salva, _exigir_host_local
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao.ativos import ResolvedorAtivosMeta
from app.trafego.meta_execucao.capacidades import (
    criacao_liberada,
    motivo_da_criacao_fechada,
)
from app.trafego.meta_execucao.compilador import PlanoCompiladoMeta, compilar_plano_pausado
from app.trafego.meta_execucao.contrato import (
    AutorizacaoMeta,
    ErroDeNascimentoMeta,
    PlanoMetaPausado,
    VariacaoEstaticaMeta,
)
from app.trafego.meta_execucao.executor import (
    ErroRemotoMeta,
    ExecutorMetaPausado,
    ResultadoValidacaoMeta,
)
from app.trafego.meta_execucao.registro import RegistroSagaMetaSupabase
from app.services.supabase_service import SupabaseService
from app.config import get_settings


router = APIRouter(prefix="/api/trafego/meta/local/criacao", tags=["meta-validate-paused"])
TIMEOUT_META = 20.0


def _registro_saga() -> RegistroSagaMetaSupabase:
    """Seam do ledger para ESTA rota.

    ⚠️ `trafego_meta_criacao` tem uma fábrica própria com o mesmo corpo, e a
    duplicação de uma linha é deliberada: cada módulo precisa de um ponto de
    substituição independente nos testes. Compartilhar a função faria uma
    troca na rota de validação silenciosamente reconfigurar a rota de criação.
    """
    return RegistroSagaMetaSupabase(SupabaseService(get_settings()))


class PedidoVariacaoEstaticaMeta(BaseModel):
    variation_key: str = Field(min_length=1, max_length=32)
    asset_ref: str = Field(min_length=8, max_length=180)
    creative_name: str = Field(min_length=1, max_length=400)
    ad_name: str = Field(min_length=1, max_length=400)
    message: str = Field(min_length=1, max_length=2200)
    headline: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=255)
    call_to_action_type: str = Field(default="LEARN_MORE", min_length=3, max_length=40)


class PedidoPlanoMetaPausado(BaseModel):
    account_ref: str = Field(min_length=8, max_length=180)
    page_ref: str = Field(min_length=8, max_length=180)
    asset_ref: str = Field(min_length=8, max_length=180)
    campaign_name: str = Field(min_length=1, max_length=400)
    adset_name: str = Field(min_length=1, max_length=400)
    creative_name: str = Field(min_length=1, max_length=400)
    ad_name: str = Field(min_length=1, max_length=400)
    destination_url: str = Field(min_length=10, max_length=2000)
    message: str = Field(min_length=1, max_length=2200)
    headline: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=255)
    daily_budget_minor: int = Field(gt=0, le=10_000_000)
    start_time: datetime
    special_ad_categories: list[str] = Field(default_factory=list, max_length=6)
    special_categories_confirmed: bool
    # Backward-compatible default for tabs opened before this field entered the
    # UI contract. Meta requires the value explicitly; omission means the safe
    # Ad Set budget behavior, never an implicit opt-in to sharing.
    is_adset_budget_sharing_enabled: bool = False
    # Mesma classe de campo: desde a v23.0 a Meta assume 1 quando o Ad Set nasce
    # sem `targeting_automation.advantage_audience`. O padrão seguro aqui é a
    # recusa explícita, nunca a omissão.
    advantage_audience: bool = False
    call_to_action_type: str = Field(default="LEARN_MORE", min_length=3, max_length=40)
    variations: list[PedidoVariacaoEstaticaMeta] = Field(default_factory=list, max_length=10)


class PedidoValidarMeta(BaseModel):
    plano: PedidoPlanoMetaPausado
    confirmar_validate_only: bool


def _erro(exc: Exception) -> HTTPException:
    if isinstance(exc, ErroDeNascimentoMeta):
        return HTTPException(status_code=409, detail={"codigo": exc.codigo, "mensagem": str(exc)})
    if isinstance(exc, ErroRemotoMeta):
        # 422 é "a Meta olhou e recusou". Um timeout não é isso: ninguém do
        # outro lado disse nada. Misturar os dois no mesmo status ensina o
        # operador a ler silêncio como reprovação do plano. 504 separa os dois
        # casos no protocolo, antes de qualquer texto de tela.
        return HTTPException(
            status_code=504 if exc.codigo == "META_VALIDATE_TIMEOUT" else 422,
            detail={
                "codigo": exc.codigo,
                "mensagem": str(exc),
                "retry_permitido": exc.retryable,
                "provedor": exc.detalhe_provedor,
            },
        )
    return HTTPException(status_code=500, detail="Falha interna no controle Meta.")


def _plano(payload: PedidoPlanoMetaPausado) -> PlanoMetaPausado:
    return PlanoMetaPausado(
        account_ref=payload.account_ref,
        campaign_name=payload.campaign_name,
        adset_name=payload.adset_name,
        creative_name=payload.creative_name,
        ad_name=payload.ad_name,
        destination_url=payload.destination_url,
        page_ref=payload.page_ref,
        asset_ref=payload.asset_ref,
        message=payload.message,
        headline=payload.headline,
        description=payload.description,
        daily_budget_minor=payload.daily_budget_minor,
        start_time=payload.start_time,
        special_ad_categories=tuple(payload.special_ad_categories),
        special_categories_confirmed=payload.special_categories_confirmed,
        is_adset_budget_sharing_enabled=payload.is_adset_budget_sharing_enabled,
        advantage_audience=payload.advantage_audience,
        call_to_action_type=payload.call_to_action_type,
        variacoes_estaticas=tuple(
            VariacaoEstaticaMeta(
                variation_key=item.variation_key,
                asset_ref=item.asset_ref,
                creative_name=item.creative_name,
                ad_name=item.ad_name,
                message=item.message,
                headline=item.headline,
                description=item.description,
                call_to_action_type=item.call_to_action_type,
            )
            for item in payload.variations
        ),
    )


async def _compilar(
    payload: PedidoPlanoMetaPausado,
    plano: PlanoMetaPausado,
    segredo: SegredoEfemero,
) -> PlanoCompiladoMeta:
    """Resolve os ativos da conta e compila o plano JÁ validado.

    ⚠️ Recebe o plano pronto em vez de construí-lo. O contrato de
    `PlanoMetaPausado` é puro e não precisa de segredo nenhum; validá-lo antes
    de abrir o Keychain faz um plano recusável — `true` no compartilhamento de
    verba, por exemplo — parar sem que o token seja sequer lido.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
        asset_refs = [item.asset_ref for item in payload.variations] or [payload.asset_ref]
        referencias = await ResolvedorAtivosMeta(cliente).resolver_lote(
            account_ref=payload.account_ref,
            page_ref=payload.page_ref,
            asset_refs=asset_refs,
            segredo=segredo,
        )
    return compilar_plano_pausado(plano, referencias)


@router.get("/capacidades")
async def capacidades(
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    del quem
    return {
        "ok": True,
        "api_version": "v26.0",
        "receita": "OUTCOME_TRAFFIC_LPV_STATIC_PAUSED",
        "read_assets": "AVAILABLE_WITH_LOCAL_KEYCHAIN",
        "single_static": "AVAILABLE",
        "static_batch": "AVAILABLE_UP_TO_10",
        # Capacidade preservada como planejada, fechada NESTA receita. Não é
        # "não existe": é "não pertence a uma receita de conjunto único".
        "adset_budget_sharing": "BLOCKED_IN_SINGLE_ADSET_RECIPE",
        "video_creative": "BLOCKED_UNTIL_VIDEO_THUMBNAIL_CONTRACT_PROVEN",
        "video_inventory": "AVAILABLE_READ_ONLY",
        "flexible_creative": "BLOCKED_UNTIL_ASSET_FEED_SPEC_PROVEN",
        "validate_only": (
            "ENABLED" if os.environ.get("META_VALIDATE_ONLY_ENABLED") == "1"
            else "BLOCKED_BY_SERVER_FLAG"
        ),
        # A rota existe (`trafego_meta_criacao`), então "NOT_MOUNTED" deixou de
        # ser verdade. O que decide agora é a autorização do servidor, e as duas
        # flags são reportadas juntas para a tela poder dizer o que falta.
        "create_paused": "ENABLED" if criacao_liberada() else "BLOCKED_BY_SERVER_FLAG",
        "activation": "NOT_IMPLEMENTED",
        # Causa verificável de cada bloqueio, em linguagem de operador. A tela
        # mostra isto no lugar do nome de qualquer variável de ambiente.
        "bloqueios": {
            "video_creative": (
                "A miniatura do criativo de vídeo precisa ser um image_hash da biblioteca "
                "da conta ou uma URL hospedada por nós; a documentação oficial proíbe usar "
                "a URL de miniatura devolvida pelo CDN da Meta, e enviar uma imagem nova "
                "seria uma escrita de ativo não autorizada nesta missão."
            ),
            "flexible_creative": (
                "Está provado que asset_feed_spec exige ad_formats, link_urls e "
                "call_to_action_types, que as imagens usam a chave hash e que "
                "is_dynamic_creative vive no conjunto. Falta prova oficial de como a Página "
                "viaja junto do asset_feed_spec: nenhum exemplo da Meta mostra "
                "object_story_spec e asset_feed_spec no mesmo criativo."
            ),
            "adset_budget_sharing": (
                "Esta campanha possui um único conjunto. Em 05/09/2026 a validação real "
                "recusou o compartilhamento com o código 100/4005: a Meta exige uma "
                "estratégia de lance no Campaign para compartilhar orçamento entre "
                "conjuntos, e esta receita mantém a estratégia no conjunto. O "
                "compartilhamento ficará disponível em uma receita multiconjunto com "
                "estratégia de lance compatível."
            ),
            "validate_only": (
                "A validação remota está fechada neste servidor. Um administrador precisa "
                "liberá-la antes de qualquer chamada à Meta."
            ),
            "create_paused": motivo_da_criacao_fechada(),
        },
    }


@router.get("/ativos")
async def ativos(
    request: Request,
    account_ref: str = Query(min_length=8, max_length=180),
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    segredo = SegredoEfemero(_credencial_salva(quem).token)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
            return dict(await ResolvedorAtivosMeta(cliente).inventariar(account_ref, segredo))
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


@router.get("/ativos/preview")
async def preview_ativo(
    request: Request,
    account_ref: str = Query(min_length=8, max_length=180),
    asset_ref: str = Query(min_length=8, max_length=180),
    quem: Identidade = Depends(exigir_admin),
) -> Response:
    """Proxy an authenticated preview without exposing Meta's signed URL."""
    _exigir_host_local(request)
    segredo = SegredoEfemero(_credencial_salva(quem).token)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
            preview_url = await ResolvedorAtivosMeta(cliente).preview_url(
                account_ref=account_ref, asset_ref=asset_ref, segredo=segredo)
            partes = urlparse(preview_url)
            host = (partes.hostname or "").lower()
            if partes.scheme != "https" or not host.endswith(".fbcdn.net"):
                raise ErroDeNascimentoMeta(
                    "META_ASSET_PREVIEW_HOST_REJECTED",
                    "a URL de preview devolvida pela Meta nao pertence ao CDN permitido",
                )
            imagem = await cliente.get(preview_url)
            if imagem.status_code >= 400:
                raise ErroDeNascimentoMeta(
                    "META_ASSET_PREVIEW_FAILED", "a Meta recusou o download da previa")
            tipo = imagem.headers.get("content-type", "").split(";", 1)[0].lower()
            if not tipo.startswith("image/") or len(imagem.content) > 12_000_000:
                raise ErroDeNascimentoMeta(
                    "META_ASSET_PREVIEW_INVALID", "a previa nao e uma imagem segura")
            return Response(
                content=imagem.content,
                media_type=tipo,
                headers={
                    "Cache-Control": "private, max-age=300",
                    "X-Content-Type-Options": "nosniff",
                },
            )
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


@router.post("/compilar")
async def compilar(
    payload: PedidoPlanoMetaPausado,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    try:
        plano = _plano(payload)
        compilado = await _compilar(
            payload, plano, SegredoEfemero(_credencial_salva(quem).token))
        return {"ok": True, "plano": compilado.publico(), "efeito_externo": "NENHUM"}
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


@router.post("/validar")
async def validar(
    payload: PedidoValidarMeta,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    if not payload.confirmar_validate_only:
        raise HTTPException(status_code=409, detail={
            "codigo": "META_VALIDATE_ONLY_NOT_CONFIRMED",
            "mensagem": "confirme explicitamente a validacao remota",
        })
    if os.environ.get("META_VALIDATE_ONLY_ENABLED") != "1":
        raise HTTPException(status_code=409, detail={
            "codigo": "META_VALIDATE_ONLY_BLOCKED",
            "mensagem": "validate_only Meta permanece fechado neste servidor",
        })
    try:
        # O contrato do plano é puro. Ele julga primeiro, e só um plano que
        # passa chega perto do Keychain ou da rede.
        pedido = _plano(payload.plano)
        segredo = SegredoEfemero(_credencial_salva(quem).token)
        plano = await _compilar(payload.plano, pedido, segredo)
        autorizacao = AutorizacaoMeta(
            plano_sha256=plano.plano_sha256,
            ator=quem.sub,
            approval_id=f"validation_{uuid.uuid4()}",
            permitir_validate_only=True,
        )
        async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
            resultado = await ExecutorMetaPausado(cliente).validar_raizes(
                plano, segredo, autorizacao)
        prova = await _gravar_prova_da_validacao(resultado, plano, ator=quem.sub)
        return {
            "ok": resultado.aceito,
            "cobertura": resultado.cobertura,
            "operacoes_validadas": list(resultado.operacoes_validadas),
            "operacoes_dependentes_pendentes": list(resultado.operacoes_dependentes_pendentes),
            "plano_sha256": resultado.plano_sha256,
            "objetos_criados": 0,
            # A aprovação só aceita esta referência opaca. Sem ela a validação
            # continua verdadeira e a aprovação continua impossível — que é o
            # comportamento certo quando a autoridade durável está fechada.
            "prova_duravel": prova,
        }
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


async def _gravar_prova_da_validacao(
    resultado: ResultadoValidacaoMeta,
    plano: PlanoCompiladoMeta,
    *,
    ator: str,
) -> dict[str, Any]:
    """Persiste o recibo da validação e diz honestamente se conseguiu.

    ⚠️ Uma falha aqui NÃO derruba a resposta. A Meta já respondeu, nada foi
    criado, e apagar esse fato porque o ledger está fechado seria mentir na
    direção oposta. O que a resposta faz é declarar `registrada: false` e o
    motivo — e é a APROVAÇÃO que falha fechada depois, por não encontrar
    recibo nenhum para o hash.
    """
    if not resultado.aceito:
        return {"registrada": False, "motivo": "a Meta não aceitou este plano"}
    try:
        gravado = await _registro_saga().registrar_validacao(
            plano_sha256=resultado.plano_sha256,
            account_ref=plano.account_ref,
            ator=ator,
            cobertura=resultado.cobertura,
            passos_validados=resultado.operacoes_validadas,
            passos_pendentes=resultado.operacoes_dependentes_pendentes,
            operacoes_totais=len(plano.operacoes),
            objetos_criados=0,
        )
    except ErroDeNascimentoMeta as exc:
        return {"registrada": False, "motivo": str(exc), "codigo": exc.codigo}
    return {
        "registrada": True,
        "validation_id": str(gravado.get("validation_id") or ""),
        "validated_at": gravado.get("validated_at"),
    }
