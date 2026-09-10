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
from app.trafego.meta.business_credentials import credencial_operacional

import uuid
from datetime import datetime
from typing import Any, Annotated
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.routers.meta_local import _credencial_salva, _exigir_host_local
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao.ativos import ResolvedorAtivosMeta
from app.trafego.meta_execucao import capacidades as capacidades_meta
from app.trafego.meta_execucao.capacidades import (
    criacao_liberada,
    ledger_liberado,
    motivo_da_criacao_fechada,
)
from app.trafego.meta_execucao import contrato_v2, receitas
from app.trafego.meta_execucao.compilador import (
    PlanoCompiladoMeta,
    compilar_plano_pausado,
    compilar_plano_v2,
)
from app.trafego.meta_execucao.publicos import resolver_referencias_de_publico
from app.trafego.meta_execucao import identidades_regulatorias
from app.trafego.meta_execucao.contrato import (
    DESTINO_SHOP_CONTA_NAO_ELEGIVEL,
    DESTINO_SHOP_NAO_PROVADO,
    AutorizacaoMeta,
    DeclaracaoPoliticaAtivoMeta,
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


#: ⚠️ A FRONTEIRA HTTP FECHA, e o padrão do pydantic v2 é o oposto.
#:
#: Sem isto os modelos rodam com `extra='ignore'`: um campo que o cliente manda
#: e o DTO não declara é DESCARTADO EM SILÊNCIO, com HTTP 200. Uma tela que
#: passasse a enviar `age_min`, `objective` ou `placements` — todos fixos nesta
#: receita, nenhum deles conectado ao DTO — receberia sucesso e o operador
#: acreditaria ter escolhido algo que nunca saiu do navegador.
#:
#: `forbid` transforma esse silêncio num 422 com o nome do campo. É a mesma
#: postura do resto da lane: o vocabulário é fechado, e o que está fora dele é
#: recusado com nome próprio em vez de ser absorvido.
#:
#: ⚠️ Isto NÃO é um endurecimento de compatibilidade quebrada: os defaults que
#: existem para abas antigas (`is_adset_budget_sharing_enabled=False`,
#: `advantage_audience=False`) continuam sendo CAMPOS DECLARADOS com default —
#: omiti-los continua válido e continua significando a escolha segura. O que
#: passa a ser recusado é o campo que o servidor não conhece.
SEM_CAMPO_DESCONHECIDO = ConfigDict(extra="forbid")


class PedidoVariacaoEstaticaMeta(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    variation_key: str = Field(min_length=1, max_length=32)
    asset_ref: str = Field(min_length=8, max_length=180)
    creative_name: str = Field(min_length=1, max_length=400)
    ad_name: str = Field(min_length=1, max_length=400)
    message: str = Field(min_length=1, max_length=2200)
    headline: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=255)
    call_to_action_type: str = Field(default="LEARN_MORE", min_length=3, max_length=40)
    asset_rights_confirmed: bool = False
    third_party_identity_cleared: bool = False
    asset_policy_confirmed_at: datetime | None = None


class PedidoPlanoMetaPausado(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

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
    asset_rights_confirmed: bool = False
    third_party_identity_cleared: bool = False
    asset_policy_confirmed_at: datetime | None = None
    variations: list[PedidoVariacaoEstaticaMeta] = Field(default_factory=list, max_length=10)


class PedidoValidarMeta(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

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
    *,
    ator: str,
) -> PlanoCompiladoMeta:
    """Resolve os ativos da conta e compila o plano JÁ validado.

    ⚠️ Recebe o plano pronto em vez de construí-lo. O contrato de
    `PlanoMetaPausado` é puro e não precisa de segredo nenhum; validá-lo antes
    de abrir o Keychain faz um plano recusável — `true` no compartilhamento de
    verba, por exemplo — parar sem que o token seja sequer lido.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
        asset_refs = [item.asset_ref for item in payload.variations] or [payload.asset_ref]
        declaracoes = _declaracoes_de_politica(payload)
        referencias = await ResolvedorAtivosMeta(cliente).resolver_lote(
            account_ref=payload.account_ref,
            page_ref=payload.page_ref,
            asset_refs=asset_refs,
            segredo=segredo,
            # ⚠️ O ATOR VEM DA SESSÃO, nunca do corpo do pedido. O recibo de
            # supply se vincula a quem atestou; aceitar essa identidade do
            # navegador deixaria o mesmo interessado em subir a campanha
            # assinar a atestação que a autoriza.
            ator=ator,
            declaracoes=declaracoes,
            # ⚠️ A prova vem da AUTORIZAÇÃO DO SERVIDOR, nunca do corpo do
            # pedido. Aceitá-la do navegador deixaria o mesmo interessado em
            # subir a campanha assinar a prova de que ela pode subir.
            # ⚠️ POR CONTA. A prova é sobre a conta que este pedido escolheu, e
            # a referência opaca é o que a identifica sem expor o id do provedor.
            prova_de_destino=(
                DESTINO_SHOP_CONTA_NAO_ELEGIVEL
                if capacidades_meta.destino_website_liberado(payload.account_ref)
                else DESTINO_SHOP_NAO_PROVADO
            ),
        )
    return compilar_plano_pausado(plano, referencias)


def _declaracoes_de_politica(
    payload: PedidoPlanoMetaPausado,
) -> dict[str, DeclaracaoPoliticaAtivoMeta]:
    """Julga as declarações antes de Keychain, inventário e download."""
    declaracoes: dict[str, DeclaracaoPoliticaAtivoMeta] = {}
    for item in payload.variations or [payload]:
        if item.asset_policy_confirmed_at is None:
            raise ErroDeNascimentoMeta(
                "META_ASSET_POLICY_RECEIPT_MISSING",
                "confirme direitos e identidade de cada peça antes de compilar",
            )
        declaracoes[item.asset_ref] = DeclaracaoPoliticaAtivoMeta(
            direitos_confirmados=item.asset_rights_confirmed,
            identidade_de_terceiro_liberada=item.third_party_identity_cleared,
            confirmada_em=item.asset_policy_confirmed_at,
        )
    return declaracoes


@router.get("/tracking")
async def tracking_automatico(
    request: Request,
    destination_url: str = Query(default="", max_length=2000),
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    from app.trafego.meta_execucao.tracking import apresentar_tracking

    _exigir_host_local(request)
    return apresentar_tracking(destination_url)


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
        "flexible_creative": "AVAILABLE",
        "flexible_scope": "V2_SALES_IMAGE_GROUPS_REQUIRES_REMOTE_VALIDATION",
        "validate_only": (
            "ENABLED" if capacidades_meta.validacao_liberada()
            else "BLOCKED_BY_SERVER_FLAG"
        ),
        # A rota existe (`trafego_meta_criacao`), então "NOT_MOUNTED" deixou de
        # ser verdade. O que decide agora é a autorização do servidor, e as duas
        # flags são reportadas juntas para a tela poder dizer o que falta.
        # ⚠️ As travas DE PROCESSO. A prova de destino não entra aqui porque ela
        # é POR CONTA, e esta rota não recebe conta nenhuma: reportá-la como
        # bloqueio global faria a tela dizer "fechado" mesmo para a conta que
        # foi conferida, e reportá-la como aberta faria o oposto. Ela viaja
        # separada, em `destino_website`, e a tela a resolve quando o operador
        # escolhe a conta.
        "create_paused": (
            "ENABLED" if not capacidades_meta.autorizacoes_de_processo_ausentes()
            else "BLOCKED_BY_SERVER_FLAG"
        ),
        "destino_website": {
            "escopo": "CRIATIVO_PROPRIO_COM_OPT_OUT",
            "controle_por_payload": "WEBSITE_AND_SHOP_OPT_OUT",
            "exige_readback": True,
            "legado_exige_prova_por_conta": True,
            "contas_conferidas": len(capacidades_meta.contas_com_destino_liberado()),
            "motivo": "Criativos próprios novos levam opt-out explícito de Shop; a saga exige confirmação desse controle pela Meta. Planos antigos preservam a prova por conta.",
        },
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
                "Imagens em grupos: um anúncio flexível por conjunto, apenas em Vendas. "
                "A elegibilidade depende da validação da Meta para a conta e o plano. "
                "Vídeos, catálogo e DCO via asset_feed_spec são contratos diferentes."
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
            "create_paused": " ".join(
                capacidades_meta.motivos_de_processo_ausentes()
            ) or (
                "A criação PAUSED está liberada neste servidor. Ela ainda exige "
                "aprovação humana vinculada ao plano validado, a conferência de "
                "destino da conta escolhida, e nasce sempre em estado pausado."
            ),
        },
    }


@router.get("/ativos")
async def ativos(
    request: Request,
    account_ref: str = Query(min_length=8, max_length=180),
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    segredo = SegredoEfemero((await credencial_operacional(quem, legado=_credencial_salva)).token)
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
    segredo = SegredoEfemero((await credencial_operacional(quem, legado=_credencial_salva)).token)
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
        _declaracoes_de_politica(payload)
        compilado = await _compilar(
            payload, plano, SegredoEfemero((await credencial_operacional(quem, legado=_credencial_salva)).token),
            ator=quem.sub)
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
    if not capacidades_meta.validacao_liberada():
        raise HTTPException(status_code=409, detail={
            "codigo": "META_VALIDATE_ONLY_BLOCKED",
            "mensagem": "validate_only Meta permanece fechado neste servidor",
        })
    try:
        # O contrato do plano é puro. Ele julga primeiro, e só um plano que
        # passa chega perto do Keychain ou da rede.
        pedido = _plano(payload.plano)
        _declaracoes_de_politica(payload.plano)
        segredo = SegredoEfemero((await credencial_operacional(quem, legado=_credencial_salva)).token)
        plano = await _compilar(payload.plano, pedido, segredo, ator=quem.sub)
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
    # A prova durável exige somente a autoridade do ledger. A flag de criação
    # governa o POST que pode nascer objetos; reutilizá-la aqui transformava
    # "registrar o que a Meta respondeu" em "autorizar despacho".
    if not ledger_liberado():
        return {
            "registrada": False,
            "motivo": (
                "o registro durável Meta está fechado neste servidor, então a prova "
                "desta validação não foi gravada"
            ),
            "codigo": "META_CREATE_LEDGER_WRITE_BLOCKED",
        }
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


# ═════════════════════════════════════════════════════════════════════════════
# Contrato V2: campanha + N conjuntos + N anúncios
#
# ⚠️ Mora NESTE arquivo, e não num router novo, de propósito. `validate_only` é
# um ATO com autoridade própria — flag de servidor, clique explícito e recibo
# durável. Um segundo módulo com a mesma rota criaria uma segunda porta para o
# mesmo ato, e fechar uma delas deixaria a outra aberta.
#
# As rotas V1 acima continuam intactas: uma aba antiga que ainda fale com elas
# não muda de comportamento por causa daqui.
# ═════════════════════════════════════════════════════════════════════════════

class PedidoOrcamentoV2(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    nivel: str = Field(pattern="^(ADSET|CAMPAIGN)$")
    periodo: str = Field(pattern="^(DAILY|LIFETIME)$")
    amount_minor: int = Field(gt=0, le=10_000_000)
    currency: str = Field(default="BRL", min_length=3, max_length=3)


class PedidoRaioV2(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    latitude: float
    longitude: float
    radius: int = Field(gt=0, le=80)
    distance_unit: str = Field(default="kilometer", pattern="^(mile|kilometer)$")


class PedidoGeografiaV2(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    countries: list[str] = Field(default_factory=list, max_length=50)
    region_keys: list[str] = Field(default_factory=list, max_length=100)
    city_keys: list[str] = Field(default_factory=list, max_length=200)
    zip_keys: list[str] = Field(default_factory=list, max_length=200)
    custom_locations: list[PedidoRaioV2] = Field(default_factory=list, max_length=50)
    excluded_countries: list[str] = Field(default_factory=list, max_length=50)
    excluded_region_keys: list[str] = Field(default_factory=list, max_length=100)
    excluded_city_keys: list[str] = Field(default_factory=list, max_length=200)
    excluded_zip_keys: list[str] = Field(default_factory=list, max_length=200)


class PedidoPublicoV2(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    mode: str = Field(pattern="^(BROAD|MANUAL|EXISTING_CUSTOM|EXISTING_LOOKALIKE)$")
    geo: PedidoGeografiaV2
    age_min: int = Field(default=18, ge=13, le=65)
    age_max: int = Field(default=65, ge=13, le=65)
    locale_refs: list[str] = Field(default_factory=list, max_length=50)
    include_custom_refs: list[str] = Field(default_factory=list, max_length=50)
    exclude_custom_refs: list[str] = Field(default_factory=list, max_length=50)
    lookalike_refs: list[str] = Field(default_factory=list, max_length=50)
    interest_refs: list[str] = Field(default_factory=list, max_length=50)
    # ⚠️ Sem default. Desde a v23.0 a omissão LIGA o Advantage+ na Meta, então o
    # DTO obriga a escolha a viajar — omitir aqui vira 422 com o nome do campo,
    # não uma expansão silenciosa de alcance.
    expansion: bool


class PedidoPosicionamentosV2(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    mode: str = Field(default="FACEBOOK_ONLY", pattern="^(FACEBOOK_ONLY|MANUAL)$")
    values: list[str] = Field(default_factory=list, max_length=10)


class PedidoMensuracaoV2(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    purpose: str = Field(default="REPORT_ONLY", pattern="^(REPORT_ONLY|OPTIMIZE)$")
    source_kind: str | None = Field(default=None, pattern="^(PIXEL|DATASET)$")
    source_ref: str | None = Field(default=None, min_length=8, max_length=180)
    custom_conversion_ref: str | None = Field(default=None, min_length=8, max_length=180)
    standard_event: str | None = Field(default=None, min_length=2, max_length=50)


class PedidoTextosFlexiveisV2(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO
    primary_text: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2200)]] = Field(min_length=1, max_length=5)
    headline: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]] = Field(min_length=1, max_length=5)
    description: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]] = Field(default_factory=list, max_length=5)


class PedidoConjuntoV2(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    adset_key: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=400)
    start_time: datetime
    end_time: datetime | None = None
    audience: PedidoPublicoV2
    placements: PedidoPosicionamentosV2 = Field(default_factory=PedidoPosicionamentosV2)
    measurement: PedidoMensuracaoV2 = Field(default_factory=PedidoMensuracaoV2)
    budget: PedidoOrcamentoV2 | None = None
    regulatory_identity_ref: str | None = Field(default=None, pattern=r"^metareg_[a-f0-9]{32}$")
    flexible_texts: PedidoTextosFlexiveisV2 | None = None


class PedidoAnuncioV2(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    variation_key: str = Field(min_length=1, max_length=32)
    adset_key: str = Field(min_length=1, max_length=32)
    asset_ref: str = Field(min_length=8, max_length=180)
    existing_post_ref: str | None = Field(default=None, pattern=r"^metapost_[a-f0-9]{32}$")
    creative_name: str = Field(min_length=1, max_length=400)
    ad_name: str = Field(min_length=1, max_length=400)
    message: str = Field(min_length=1, max_length=2200)
    headline: str = Field(min_length=1, max_length=255)
    # V2 context decides: only an explicit flexible pool may omit description.
    description: str = Field(min_length=0, max_length=255)
    call_to_action_type: str = Field(default="LEARN_MORE", min_length=3, max_length=40)
    asset_rights_confirmed: bool = False
    third_party_identity_cleared: bool = False
    asset_policy_confirmed_at: datetime | None = None


class PedidoPlanoMetaV2(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    creative_mode: str = Field(default="STATIC", pattern=r"^(STATIC|FLEXIBLE_IMAGES)$")

    recipe_id: str = Field(min_length=3, max_length=80)
    account_ref: str = Field(min_length=8, max_length=180)
    page_ref: str = Field(min_length=8, max_length=180)
    instagram_actor_ref: str | None = Field(default=None, min_length=8, max_length=180)
    campaign_name: str = Field(min_length=1, max_length=400)
    destination_url: str = Field(min_length=10, max_length=2000)
    campaign_budget: PedidoOrcamentoV2 | None = None
    special_ad_categories: list[str] = Field(default_factory=list, max_length=6)
    special_categories_confirmed: bool
    is_adset_budget_sharing_enabled: bool = False
    adsets: list[PedidoConjuntoV2] = Field(min_length=1, max_length=10)
    ads: list[PedidoAnuncioV2] = Field(min_length=1, max_length=50)


class PedidoValidarMetaV2(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    plano: PedidoPlanoMetaV2
    confirmar_validate_only: bool


def _plano_v2_do_pedido(payload: PedidoPlanoMetaV2) -> contrato_v2.PlanoMetaV2:
    """Traduz o DTO HTTP no contrato PURO, que julga antes de qualquer rede."""
    conjuntos = tuple(
        contrato_v2.ConjuntoMeta(
            adset_key=item.adset_key,
            flexible_texts=(contrato_v2.TextosFlexiveisMeta(**item.flexible_texts.model_dump())
                            if item.flexible_texts is not None else None),
            regulatory_identity_ref=item.regulatory_identity_ref,
            nome=item.name,
            programacao=contrato_v2.ProgramacaoMeta(
                start_time=item.start_time, end_time=item.end_time),
            publico=contrato_v2.PublicoMeta(
                modo=item.audience.mode,
                geografia=contrato_v2.GeografiaMeta(
                    countries=tuple(item.audience.geo.countries),
                    region_keys=tuple(item.audience.geo.region_keys),
                    city_keys=tuple(item.audience.geo.city_keys),
                    zip_keys=tuple(item.audience.geo.zip_keys),
                    custom_locations=tuple(
                        contrato_v2.LocalizacaoPorRaio(
                            latitude=raio.latitude,
                            longitude=raio.longitude,
                            radius=raio.radius,
                            distance_unit=raio.distance_unit,
                        )
                        for raio in item.audience.geo.custom_locations
                    ),
                    excluded_countries=tuple(item.audience.geo.excluded_countries),
                    excluded_region_keys=tuple(item.audience.geo.excluded_region_keys),
                    excluded_city_keys=tuple(item.audience.geo.excluded_city_keys),
                    excluded_zip_keys=tuple(item.audience.geo.excluded_zip_keys),
                ),
                idade_min=item.audience.age_min,
                idade_max=item.audience.age_max,
                locale_refs=tuple(item.audience.locale_refs),
                incluir_custom_refs=tuple(item.audience.include_custom_refs),
                excluir_custom_refs=tuple(item.audience.exclude_custom_refs),
                lookalike_refs=tuple(item.audience.lookalike_refs),
                interesse_refs=tuple(item.audience.interest_refs),
                expansao_advantage=item.audience.expansion,
            ),
            posicionamentos=contrato_v2.PosicionamentosMeta(
                modo=item.placements.mode, plataformas=tuple(item.placements.values)),
            mensuracao=contrato_v2.MensuracaoMeta(
                proposito=item.measurement.purpose,
                source_kind=item.measurement.source_kind,
                source_ref=item.measurement.source_ref,
                custom_conversion_ref=item.measurement.custom_conversion_ref,
                standard_event=item.measurement.standard_event,
            ),
            orcamento=None if item.budget is None else contrato_v2.OrcamentoMeta(
                nivel=item.budget.nivel,
                periodo=item.budget.periodo,
                amount_minor=item.budget.amount_minor,
                currency=item.budget.currency,
            ),
        )
        for item in payload.adsets
    )
    anuncios = tuple(
        contrato_v2.AnuncioMeta(
            variacao=VariacaoEstaticaMeta(
                variation_key=item.variation_key,
                asset_ref=item.asset_ref,
                existing_post_ref=item.existing_post_ref,
                creative_name=item.creative_name,
                ad_name=item.ad_name,
                message=item.message,
                headline=item.headline,
                description=item.description,
                description_optional=(payload.creative_mode == "FLEXIBLE_IMAGES" and any(
                    conjunto.adset_key == item.adset_key and conjunto.flexible_texts is not None
                    for conjunto in payload.adsets)),
                call_to_action_type=item.call_to_action_type,
            ),
            adset_key=item.adset_key,
        )
        for item in payload.ads
    )
    return contrato_v2.PlanoMetaV2(
        recipe_id=payload.recipe_id,
        creative_mode=payload.creative_mode,
        account_ref=payload.account_ref,
        page_ref=payload.page_ref,
        instagram_actor_ref=payload.instagram_actor_ref,
        campaign_name=payload.campaign_name,
        destination_url=payload.destination_url,
        conjuntos=conjuntos,
        anuncios=anuncios,
        special_ad_categories=tuple(payload.special_ad_categories),
        special_categories_confirmed=payload.special_categories_confirmed,
        is_adset_budget_sharing_enabled=payload.is_adset_budget_sharing_enabled,
        orcamento_campanha=None if payload.campaign_budget is None else contrato_v2.OrcamentoMeta(
            nivel=payload.campaign_budget.nivel,
            periodo=payload.campaign_budget.periodo,
            amount_minor=payload.campaign_budget.amount_minor,
            currency=payload.campaign_budget.currency,
        ),
    )


def _declaracoes_de_politica_v2(
    payload: PedidoPlanoMetaV2,
) -> dict[str, DeclaracaoPoliticaAtivoMeta]:
    """Julga as declarações de direitos ANTES de Keychain, inventário e rede."""
    declaracoes: dict[str, DeclaracaoPoliticaAtivoMeta] = {}
    for item in payload.ads:
        if item.asset_policy_confirmed_at is None:
            raise ErroDeNascimentoMeta(
                "META_ASSET_POLICY_RECEIPT_MISSING",
                "confirme direitos e identidade de cada peça antes de compilar",
            )
        declaracoes[item.asset_ref] = DeclaracaoPoliticaAtivoMeta(
            direitos_confirmados=item.asset_rights_confirmed,
            identidade_de_terceiro_liberada=item.third_party_identity_cleared,
            confirmada_em=item.asset_policy_confirmed_at,
        )
    return declaracoes


async def _compilar_v2(
    payload: PedidoPlanoMetaV2,
    plano: contrato_v2.PlanoMetaV2,
    segredo: SegredoEfemero,
    *,
    ator: str,
) -> PlanoCompiladoMeta:
    """Resolve peças e referências de público, e compila o plano JÁ validado."""
    async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
        referencias = await ResolvedorAtivosMeta(cliente).resolver_lote(
            account_ref=payload.account_ref,
            page_ref=payload.page_ref,
            asset_refs=list(plano.asset_refs),
            segredo=segredo,
            ator=ator,
            declaracoes=_declaracoes_de_politica_v2(payload),
            prova_de_destino=(
                DESTINO_SHOP_CONTA_NAO_ELEGIVEL
                if capacidades_meta.destino_website_liberado(payload.account_ref)
                else DESTINO_SHOP_NAO_PROVADO
            ),
        )
        publicos = await resolver_referencias_de_publico(
            cliente, plano=plano, account_ref=payload.account_ref, segredo=segredo)
        regulatory = {}
        if any(item.regulatory_identity_ref for item in plano.conjuntos):
            regulatory = await identidades_regulatorias.catalogo(cliente, payload.account_ref, segredo)
        from app.trafego.meta_execucao import posts_existentes
        posts = await posts_existentes.catalogo(cliente, payload.account_ref, payload.page_ref, segredo) if any(item.existing_post_ref for item in payload.ads) else {}
    return compilar_plano_v2(plano, referencias, publicos, regulatory=regulatory, existing_posts=posts)


@router.get("/v2/posts-existentes")
async def listar_posts_existentes(request: Request,
    account_ref: str = Query(min_length=8, max_length=180),
    page_ref: str = Query(min_length=8, max_length=180),
    q: str = Query(default="", max_length=200),
    offset: int = Query(default=0, ge=0), limit: int = Query(default=24, ge=1, le=100),
    quem: Identidade = Depends(exigir_admin)) -> dict[str, Any]:
    _exigir_host_local(request)
    from app.trafego.meta_execucao import posts_existentes
    try:
        segredo = SegredoEfemero((await credencial_operacional(quem, legado=_credencial_salva)).token)
        async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
            items = await posts_existentes.catalogo_cached(cliente, account_ref, page_ref, segredo, owner=quem.sub)
        return posts_existentes.publico(items, q, offset, limit)
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


@router.get("/v2/identidades-regulatorias")
async def listar_identidades_regulatorias(request: Request,
    account_ref: str = Query(min_length=8, max_length=180),
    quem: Identidade = Depends(exigir_admin)) -> dict[str, Any]:
    _exigir_host_local(request)
    try:
        segredo = SegredoEfemero((await credencial_operacional(quem, legado=_credencial_salva)).token)
        async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
            return await identidades_regulatorias.consultar_publico(cliente, account_ref, segredo)
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


def _resumo_v2(plano: contrato_v2.PlanoMetaV2) -> dict[str, Any]:
    """O que a revisão precisa afirmar sobre orçamento, público e mensuração.

    ⚠️ Derivado do CONTRATO, não do rascunho do navegador. `A33`/`F37` cobram
    que rascunho e resumo não possam divergir; a única forma de garantir isso é
    o resumo não ter outra fonte.
    """
    return {
        "formato_criativo": plano.creative_mode,
        "total_anuncios_emitidos": len(plano.conjuntos) if plano.creative_mode == "FLEXIBLE_IMAGES" else len(plano.anuncios),
        "total_grupos_de_imagem": sum(1 if c.flexible_texts is not None else len(plano.anuncios_do_conjunto(c.adset_key))
                                      for c in plano.conjuntos) if plano.creative_mode == "FLEXIBLE_IMAGES" else 0,
        "receita": {
            "id": plano.receita.id,
            "rotulo": plano.receita.rotulo,
            "objetivo": plano.receita.objective,
            "otimizacao": plano.receita.optimization_goal,
            "prova": plano.receita.prova,
            "capacidade_pausada": receitas.capacidade_pausada(),
        },
        "orcamento": {
            "nivel": plano.nivel_de_orcamento,
            "periodo": plano.periodo_de_orcamento,
            "modo": plano.modo_de_orcamento.id,
            "prova": plano.modo_de_orcamento.prova,
            "onde_a_verba_mora": (
                "na campanha (CBO)" if plano.orcamento_e_da_campanha
                else "em cada conjunto (ABO)"),
        },
        "conjuntos": [
            {
                "adset_key": conjunto.adset_key,
                "nome": conjunto.nome,
                "orcamento_minor": (
                    conjunto.orcamento.amount_minor if conjunto.orcamento else None),
                "publico_modo": conjunto.publico.modo,
                "publicos_incluidos": len(conjunto.publico.incluir_custom_refs)
                + len(conjunto.publico.lookalike_refs),
                "publicos_excluidos": len(conjunto.publico.excluir_custom_refs),
                "expansao_advantage": conjunto.publico.expansao_advantage,
                # ⚠️ A frase que a tela mostra sobre remarketing sai DAQUI.
                # Com expansão ligada a Meta trata a seleção como sugestão, e
                # prometer alcance exclusivo seria a tela afirmando o que o
                # provedor não garante (`A16`).
                "promete_alcance_exclusivo": conjunto.publico.promete_alcance_exclusivo,
                "posicionamentos": list(conjunto.posicionamentos.plataformas),
                "mensuracao_proposito": conjunto.mensuracao.proposito,
                "mensuracao_altera_entrega": conjunto.mensuracao.altera_payload,
                "anuncios": [item.variation_key for item in (
                    plano.anuncios_do_conjunto(conjunto.adset_key)[:1]
                    if plano.creative_mode == "FLEXIBLE_IMAGES"
                    else plano.anuncios_do_conjunto(conjunto.adset_key))],
                "grupos_de_imagem": (1 if conjunto.flexible_texts is not None else len(plano.anuncios_do_conjunto(conjunto.adset_key))) if plano.creative_mode == "FLEXIBLE_IMAGES" else 0,
                **({"flexible_texts": conjunto.flexible_texts.publico()} if conjunto.flexible_texts is not None else {}),
            }
            for conjunto in plano.conjuntos
        ],
        "bloqueios_para_criar": list(plano.bloqueios_para_criar()),
        "lacunas_de_prova_historica": list(plano.bloqueios_para_criar()),
    }


@router.get("/v2/receitas")
async def receitas_disponiveis(
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    """O catálogo de receitas COM o nível de prova de cada uma.

    A tela precisa saber não só o que existe, mas o que está provado — uma
    receita apresentada como disponível e recusada pela rota é pior do que uma
    receita ausente.
    """
    _exigir_host_local(request)
    del quem
    return {
        "ok": True,
        "api_version": "v26.0",
        "receita_padrao": receitas.RECEITA_PADRAO,
        "receitas": receitas.catalogo_publico(),
        "limites": {
            "conjuntos": contrato_v2.MAX_CONJUNTOS,
            "anuncios_por_conjunto": contrato_v2.MAX_ANUNCIOS_POR_CONJUNTO,
            "anuncios_total": contrato_v2.MAX_ANUNCIOS_TOTAL,
            "classificacao": "limites operacionais do produto, não limites oficiais da Meta",
        },
        "idade": {
            "min": contrato_v2.IDADE_MINIMA,
            "max": contrato_v2.IDADE_MAXIMA,
            "motivo": (
                "limite do produto, não da Meta. Ampliá-lo em silêncio ampliaria o "
                "alcance de campanhas já aprovadas."
            ),
        },
    }


@router.post("/v2/compilar")
async def compilar_v2(
    payload: PedidoPlanoMetaV2,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    _exigir_host_local(request)
    try:
        plano = _plano_v2_do_pedido(payload)
        _declaracoes_de_politica_v2(payload)
        compilado = await _compilar_v2(
            payload, plano, SegredoEfemero((await credencial_operacional(quem, legado=_credencial_salva)).token), ator=quem.sub)
        return {
            "ok": True,
            "contrato": "V2",
            "plano": compilado.publico(),
            "resumo": _resumo_v2(plano),
            "efeito_externo": "NENHUM",
        }
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


@router.post("/v2/validar")
async def validar_v2(
    payload: PedidoValidarMetaV2,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    """`validate_only` do plano V2 — por clique, e sem criar nada.

    ⚠️ Uma receita ou um modo de orçamento SEM prova remota continua chegando
    aqui de propósito: é esta chamada que produz a prova que falta. O que a
    ausência de prova fecha é CRIAR, e esse portão vive no executor.
    """
    _exigir_host_local(request)
    if not payload.confirmar_validate_only:
        raise HTTPException(status_code=409, detail={
            "codigo": "META_VALIDATE_ONLY_NOT_CONFIRMED",
            "mensagem": "confirme explicitamente a validacao remota",
        })
    if not capacidades_meta.validacao_liberada():
        raise HTTPException(status_code=409, detail={
            "codigo": "META_VALIDATE_ONLY_BLOCKED",
            "mensagem": "validate_only Meta permanece fechado neste servidor",
        })
    try:
        plano = _plano_v2_do_pedido(payload.plano)
        _declaracoes_de_politica_v2(payload.plano)
        segredo = SegredoEfemero((await credencial_operacional(quem, legado=_credencial_salva)).token)
        compilado = await _compilar_v2(payload.plano, plano, segredo, ator=quem.sub)
        autorizacao = AutorizacaoMeta(
            plano_sha256=compilado.plano_sha256,
            ator=quem.sub,
            approval_id=f"validation_{uuid.uuid4()}",
            permitir_validate_only=True,
        )
        async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
            resultado = await ExecutorMetaPausado(cliente).validar_raizes(
                compilado, segredo, autorizacao)
        prova = await _gravar_prova_da_validacao(resultado, compilado, ator=quem.sub)
        return {
            "ok": resultado.aceito,
            "contrato": "V2",
            "cobertura": resultado.cobertura,
            # ⚠️ A cobertura em português, ao lado do enum, porque `A44` proíbe
            # a tela afirmar que AdSet/Ad/expansão/receita foram provados por
            # uma validação que só tocou as raízes independentes.
            "cobertura_explicada": (
                "a Meta aceitou apenas as operações que não dependem de um objeto "
                "pai real (campanha e criativos). Conjunto e anúncio não foram "
                "validados, e nada foi criado."
            ),
            "operacoes_validadas": list(resultado.operacoes_validadas),
            "operacoes_dependentes_pendentes": list(resultado.operacoes_dependentes_pendentes),
            "plano_sha256": resultado.plano_sha256,
            "objetos_criados": 0,
            "resumo": _resumo_v2(plano),
            "prova_duravel": prova,
        }
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


@router.post("/v2/canario/ficha")
async def ficha_do_canario(
    payload: PedidoPlanoMetaV2,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    """A ficha de autorização do primeiro canário — um documento, não um ato.

    ⚠️ Ela COMPILA (para ter o hash exato do que seria criado) e NÃO cria, não
    valida remotamente e não guarda autorização. Compilar é local: nenhum
    objeto nasce, nenhuma verba é comprometida.

    ⚠️ E ela procura o recibo durável de validação DESTE hash. Sem recibo, a
    ficha sai com a lacuna nomeada em vez de sair "pronta" — porque pedir
    autorização para um plano que ninguém validou é pedir uma assinatura em
    branco.
    """
    _exigir_host_local(request)
    try:
        plano = _plano_v2_do_pedido(payload)
        _declaracoes_de_politica_v2(payload)
        compilado = await _compilar_v2(
            payload, plano, SegredoEfemero((await credencial_operacional(quem, legado=_credencial_salva)).token), ator=quem.sub)
        ficha = contrato_v2.ficha_de_canario(
            plano, compilado,
            prova_de_validacao=await _prova_de_validacao_do_hash(compilado.plano_sha256, ator=quem.sub),
        )
        # O tracking real vem do plano COMPILADO, não de uma constante repetida
        # aqui: duas cópias do mesmo template é como uma delas fica para trás.
        ficha["tracking"]["template"] = next(
            (op.payload.get("url_tags") for op in compilado.operacoes
             if op.tipo_objeto == "creative"),
            None,
        )
        return {"ok": True, "efeito_externo": "NENHUM", "ficha": ficha}
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


async def _prova_de_validacao_do_hash(plano_sha256: str, *, ator: str) -> dict[str, Any]:
    """Procura o recibo durável de validate_only para ESTE hash exato.

    ⚠️ Um hash novo exige recibo novo. É o mesmo princípio de
    `AutorizacaoMeta.exigir`: mudar qualquer campo muda o hash, e um recibo
    antigo descreveria um plano que já não é este.
    """
    from app.routers.trafego_meta_criacao import JANELA_DA_VALIDACAO_S

    try:
        encontrado = await _registro_saga().buscar_validacao(
            plano_sha256=plano_sha256, ator=ator, janela_da_validacao_s=JANELA_DA_VALIDACAO_S)
    except ErroDeNascimentoMeta as exc:
        return {"registrada": False, "motivo": str(exc), "codigo": exc.codigo}
    return {"registrada": bool(encontrado), "recibo": encontrado or None}
