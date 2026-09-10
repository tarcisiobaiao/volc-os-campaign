"""Reserve a cosmetic campaign sequence; no Meta object writes or approvals."""
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from app.seguranca.identidade import Identidade, exigir_admin
from app.routers.trafego_meta_drafts import SafeValidationRoute, storage, reply
from app.routers.meta_local import _credencial_salva
from app.trafego.meta.draft_storage import Closed
from app.trafego.meta.business_credentials import credencial_operacional
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta.adaptador import ErroDeLeituraMeta
from app.trafego.meta.naming import resolved_history

router = APIRouter(prefix='/api/trafego/meta/drafts', tags=['meta-campaign-naming'], route_class=SafeValidationRoute)


class ReserveNaming(Closed):
    expected_version: int = Field(ge=1, le=2147483647)


@router.post('/{draft_ref}/naming-reservation')
async def reserve(draft_ref: UUID, request: ReserveNaming,
                  who: Identidade = Depends(exigir_admin), repo=Depends(storage)):
    # Read/version check before resolving credentials or fetching remote names.
    current = await reply(repo.read(who.sub, draft_ref))
    if current['version'] != request.expected_version:
        raise HTTPException(409, detail={'codigo': 'META_DRAFT_VERSION_CONFLICT', 'mensagem': 'Recarregue a versão salva do rascunho antes de reservar o número.'})
    account_ref = current['draft']['accountRef']
    if not account_ref:
        raise HTTPException(422, detail={'codigo': 'META_NAMING_ACCOUNT_REQUIRED', 'mensagem': 'Selecione e salve a conta da campanha antes de reservar o número.'})
    credential = await credencial_operacional(who, legado=_credencial_salva)
    try:
        account, history = await resolved_history(account_ref, SegredoEfemero(credential.token))
        if not history.complete:
            raise ErroDeLeituraMeta('META_NAMING_HISTORY_INCOMPLETE', 'O histórico ainda está incompleto; nenhum número foi reservado.')
        result = await repo.service.rpc('trafego_meta_campaign_naming_reserve', {
            'p_owner_id': who.sub, 'p_draft_ref': str(draft_ref), 'p_expected_version': request.expected_version,
            'p_account_id': account.id_externo, 'p_account_ref': account_ref,
            'p_history_max': history.maximum, 'p_history_count': history.count,
            'p_history_complete': history.complete})
    except ErroDeLeituraMeta as exc:
        raise HTTPException(409, detail={'codigo': exc.codigo, 'mensagem': exc.mensagem_segura}) from None
    except TimeoutError:
        raise HTTPException(504, detail={'codigo': 'META_NAMING_HISTORY_TIMEOUT', 'mensagem': 'A leitura do histórico demorou demais. Nenhum número foi reservado.'}) from None
    except httpx.HTTPStatusError as exc:
        try:
            error = exc.response.json()
        except ValueError:
            error = {}
        code = error.get('message')
        if code in {'META_DRAFT_VERSION_CONFLICT', 'META_NAMING_ACCOUNT_CHANGED', 'META_NAMING_RANGE_EXHAUSTED'}:
            raise HTTPException(409, detail={'codigo': code, 'mensagem': 'O rascunho ou a numeração mudou. Recarregue antes de continuar.'}) from None
        if code == 'META_DRAFT_ARCHIVED':
            raise HTTPException(410, detail={'codigo': code, 'mensagem': 'Este rascunho foi arquivado.'}) from None
        if code == 'META_DRAFT_NOT_FOUND':
            raise HTTPException(404, detail={'codigo': code, 'mensagem': 'Este rascunho não está mais disponível.'}) from None
        raise HTTPException(503, detail={'codigo': 'META_NAMING_STORAGE_UNAVAILABLE', 'mensagem': 'A reserva de numeração está indisponível. Nenhum nome foi alterado na Meta.'}) from None
    except httpx.HTTPError:
        raise HTTPException(503, detail={'codigo': 'META_NAMING_STORAGE_UNAVAILABLE', 'mensagem': 'Não foi possível confirmar a reserva. Tentar novamente recupera o mesmo número já reservado.'}) from None
    if (not isinstance(result, dict) or result.get('draft_ref') != str(draft_ref)
            or result.get('account_ref') != account_ref or result.get('history_complete') is not True
            or type(result.get('campaign_number')) is not int or not 1 <= result['campaign_number'] <= 2147483647
            or type(result.get('history_count')) is not int or result['history_count'] < 0):
        raise HTTPException(503, detail={'codigo': 'META_NAMING_RESERVATION_UNCONFIRMED', 'mensagem': 'A reserva não foi confirmada. Não use um número estimado.'})
    return {key: result[key] for key in ('campaign_number', 'account_ref', 'draft_ref', 'history_complete', 'history_count')}
