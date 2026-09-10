"""Read-only server grant, separate from editable draft and human approval."""
from uuid import UUID

from app.config import get_settings
from app.services.supabase_service import SupabaseService


async def check_draft_upload(owner: str, draft_ref: UUID, account_ref: str,
                             master_refs: list[str], service=None) -> dict:
    service = service or SupabaseService(get_settings())
    if service.base != 'https://database.agenciavolc.com.br' or not service.enabled:
        raise RuntimeError('Official draft authority unavailable')
    refs = [str(UUID(ref)) for ref in master_refs]
    if not 1 <= len(refs) <= 10 or len(set(refs)) != len(refs):
        return {'allowed': False, 'reason': 'META_DRAFT_UPLOAD_SELECTION_INVALID'}
    result = await service.rpc('trafego_meta_draft_upload_check', {
        'p_owner_id': owner, 'p_draft_ref': str(draft_ref),
        'p_account_ref': account_ref, 'p_master_refs': refs,
    })
    if not isinstance(result, dict) or type(result.get('allowed')) is not bool:
        raise RuntimeError('Invalid draft authority response')
    return result
