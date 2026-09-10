"""Durable editing state; no provider transport, token or approval authority."""
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta.draft_storage import CampaignDraft, DraftStorage, SaveDraft, ArchiveDraft


class SafeValidationRoute(APIRoute):
    def get_route_handler(self):
        handler=super().get_route_handler()
        async def safe(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422,detail={"codigo":"META_DRAFT_INVALID","mensagem":"Confira os campos e vínculos do rascunho. Nenhuma alteração foi salva."}) from None
        return safe


router=APIRouter(prefix="/api/trafego/meta/drafts",tags=["meta-campaign-drafts"],route_class=SafeValidationRoute)


def storage(response:Response):
    response.headers["Cache-Control"]="no-store"
    repo=DraftStorage()
    if not repo.service.enabled or repo.service.base != "https://database.agenciavolc.com.br":
        raise HTTPException(503,detail={"codigo":"META_DRAFT_STORAGE_UNAVAILABLE","mensagem":"O armazenamento oficial de rascunhos está indisponível."})
    return repo


async def reply(operation, *, archive=False):
    try:
        result=await operation
    except httpx.HTTPStatusError as exc:
        try:
            error=exc.response.json()
        except ValueError:
            error={}
        if error.get("message")=="META_DRAFT_VERSION_CONFLICT":
            raise HTTPException(409,detail={"codigo":"META_DRAFT_VERSION_CONFLICT","mensagem":"Este rascunho mudou em outra aba. Recarregue a versão salva antes de continuar."}) from None
        if error.get('message')=='META_DRAFT_ARCHIVED':
            raise HTTPException(410,detail={'codigo':'META_DRAFT_ARCHIVED','mensagem':'Este rascunho foi excluído. Suas peças e packs foram preservados.'}) from None
        if error.get('message') in {'META_DRAFT_INVALID', 'META_DRAFT_LINK_INVALID', 'META_DRAFT_SECRET_FORBIDDEN'}:
            raise HTTPException(422,detail={'codigo':error['message'],'mensagem':'O banco recusou os campos ou vínculos deste rascunho. Nenhuma alteração foi salva. Confira o formulário; se persistir, o contrato de rascunhos precisa ser atualizado.'}) from None
        if exc.response.status_code==404 or error.get("code") in {"PGRST202","42P01","42883"}:
            raise HTTPException(503,detail={"codigo":"META_DRAFT_SCHEMA_REQUIRED","mensagem":"A persistência de rascunhos precisa ser instalada no banco oficial."}) from None
        raise HTTPException(503,detail={"codigo":"META_DRAFT_STORAGE_UNAVAILABLE","mensagem":"Não foi possível salvar ou recuperar o rascunho. Tente novamente."}) from None
    except httpx.HTTPError:
        raise HTTPException(503,detail={"codigo":"META_DRAFT_STORAGE_UNAVAILABLE","mensagem":"Não foi possível acessar o rascunho salvo."}) from None
    if not result:
        raise HTTPException(404,detail={"codigo":"META_DRAFT_NOT_FOUND","mensagem":"Rascunho ainda não salvo nesta conta."})
    if archive:
        if result.get('archived') is not True:
            raise HTTPException(503, detail={'codigo':'META_DRAFT_ARCHIVE_UNCONFIRMED','mensagem':'A exclusão não foi confirmada. Consulte os rascunhos antes de repetir.'})
        return result
    # Validate and clear transient attestations again at the response boundary.
    try:
        result["draft"]=CampaignDraft.model_validate(result["draft"]).persisted()
    except (ValueError,KeyError,TypeError):
        raise HTTPException(503,detail={"codigo":"META_DRAFT_INVALID_STORAGE","mensagem":"O rascunho salvo precisa de revisão antes de ser retomado."}) from None
    return result


@router.get("")
async def list_drafts(response: Response, offset: int = Query(default=0, ge=0, le=100000),
                      who:Identidade=Depends(exigir_admin), repo=Depends(storage)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return await repo.list(who.sub, offset)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, detail={"codigo":"META_DRAFT_LIST_UNAVAILABLE",
            "mensagem":"Não foi possível consultar seus rascunhos. Tente novamente."}) from None


@router.get("/{draft_ref}")
async def read(draft_ref:UUID, who:Identidade=Depends(exigir_admin),repo=Depends(storage)):
    return await reply(repo.read(who.sub,draft_ref))


@router.put("/{draft_ref}")
async def save(draft_ref:UUID, request:SaveDraft, who:Identidade=Depends(exigir_admin),repo=Depends(storage)):
    return await reply(repo.save(who.sub,draft_ref,request))


@router.delete('/{draft_ref}')
async def archive(draft_ref:UUID, request:ArchiveDraft, who:Identidade=Depends(exigir_admin),repo=Depends(storage)):
    return await reply(repo.archive(who.sub,draft_ref,request.expected_version), archive=True)
