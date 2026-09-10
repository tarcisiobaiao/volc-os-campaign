"""Owner-scoped text assistant. Suggestions never mutate a draft."""
import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import Settings, get_settings
from app.llm.gemini import GeminiClient
from app.routers.trafego_meta_drafts import SafeValidationRoute, reply, storage
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta.copy_suggestions import CopyFailure, CopyRequest, CopyResponse, OwnerCopyLimiter, context_for, suggest
from app.trafego.meta.copy_context import clean, read_saved_context

router = APIRouter(prefix="/api/trafego/meta/drafts", tags=["meta-copy-suggestions"], route_class=SafeValidationRoute)
TIMEOUT_SECONDS = 70  # End-to-end deadline, below the browser's 75 seconds.
RECHECK_BUDGET_SECONDS = 20
_limiter = OwnerCopyLimiter()


def copy_client(settings: Settings = Depends(get_settings)):
    if not settings.resolved_gemini_key or not settings.criativo_meta_gemini_model:
        raise HTTPException(503, detail={"codigo": "META_COPY_MODEL_UNAVAILABLE", "mensagem": "O modelo de texto está indisponível. Nenhuma sugestão fictícia foi usada."})
    return GeminiClient(settings, model=settings.criativo_meta_gemini_model, temperature=0.65)


def _version(record, expected):
    if record.get("version") != expected:
        raise HTTPException(409, detail={"codigo": "META_DRAFT_VERSION_CONFLICT", "mensagem": "O rascunho mudou. Recarregue a versão salva antes de aplicar ou pedir sugestões."})


@router.get("/{draft_ref}/copy-context")
async def copy_context_preview(draft_ref: UUID,
        adset_key: Annotated[str, Query(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")],
        who: Identidade = Depends(exigir_admin), repo=Depends(storage)):
    """Local source summary only. No model dependency, paid call or draft write."""
    record = await reply(repo.read(who.sub, draft_ref))
    try:
        resolved = await read_saved_context(getattr(repo, 'service', None), who.sub, draft_ref, record['draft'], adset_key)
    except CopyFailure as exc:
        raise HTTPException(exc.status, detail={'codigo': exc.code, 'mensagem': exc.message}) from None
    fresh = await reply(repo.read(who.sub, draft_ref))
    _version(fresh, record['version'])
    return {'draft_version': record['version'], 'context_summary': resolved['context_summary']}


@router.post("/{draft_ref}/copy-suggestions", response_model=CopyResponse, response_model_exclude_none=True)
async def copy_suggestions(draft_ref: UUID, request: CopyRequest, who: Identidade = Depends(exigir_admin),
                           repo=Depends(storage), client=Depends(copy_client)):
    try:
        with _limiter.reserve(who.sub):
            async with asyncio.timeout(TIMEOUT_SECONDS) as deadline:
                record = await reply(repo.read(who.sub, draft_ref))
                _version(record, request.expected_version)
                context = context_for(record["draft"], request)
                resolved = await read_saved_context(getattr(repo, 'service', None), who.sub, draft_ref,
                                                    record['draft'], request.adset_key)
                # User authorized saved textual context, not raw graph records,
                # IDs, credentials, images or audience lists. Only allowlist out.
                context['topic'] = clean(context['topic'], 200)
                context['operator_brief_unverified'] = clean(context['operator_brief_unverified'], 2000)
                context['current_texts_unverified'] = {key: [clean(value, 2200) for value in values]
                    for key, values in context['current_texts_unverified'].items()}
                context['context_summary'] = resolved['context_summary']
                if resolved['saved_creative_context']:
                    context['saved_creative_context'] = resolved['saved_creative_context']
                model_budget = deadline.when() - asyncio.get_running_loop().time() - RECHECK_BUDGET_SECONDS
                if model_budget <= 0:
                    raise TimeoutError()
                try:
                    result = await asyncio.wait_for(suggest(client, context, request.count), timeout=model_budget)
                except TimeoutError:
                    raise
                except Exception:
                    raise HTTPException(502, detail={"codigo": "META_COPY_SUGGESTION_FAILED", "mensagem": "O modelo não retornou sugestões válidas. Seus textos atuais foram preservados."}) from None
                fresh = await reply(repo.read(who.sub, draft_ref))
                _version(fresh, request.expected_version)
                checked = await read_saved_context(getattr(repo, 'service', None), who.sub, draft_ref,
                                                   fresh['draft'], request.adset_key)
                if checked['selection_stamp'] != resolved['selection_stamp']:
                    raise HTTPException(409, detail={'codigo': 'META_COPY_CONTEXT_CHANGED',
                        'mensagem': 'A seleção ou a origem dos criativos mudou durante a geração. Atualize antes de pedir novas sugestões.'})
                return result
    except TimeoutError:
        raise HTTPException(504, detail={"codigo": "META_COPY_TIMEOUT", "mensagem": "A sugestão excedeu o tempo disponível. Seus textos não foram alterados; tente novamente quando desejar."}) from None
    except CopyFailure as exc:
        raise HTTPException(exc.status, detail={"codigo": exc.code, "mensagem": exc.message},
                            headers={"Retry-After": "5"} if exc.status == 429 else None) from None
