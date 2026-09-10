"""Packs use the same authenticated Studio boundary, never browser service keys."""
from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from app.seguranca.identidade import Identidade, exigir_usuario, exigir_admin
from app.routers.criativos import obter_repo
from app.criativo.persistencia import Repositorio, ErroDePersistencia, ConflitoDeChave
from app.criativo import packs

router = APIRouter(prefix='/api/criativos/meta/agente/packs', tags=['creative-packs'])


async def resposta(awaitable):
    try:
        return await awaitable
    except ValueError as exc:
        raise HTTPException(409, detail={'codigo': 'PACK_UNAVAILABLE', 'mensagem': str(exc)}) from None
    except ConflitoDeChave:
        raise HTTPException(409, detail={'codigo': 'PACK_DRAFT_CONFLICT',
            'mensagem': 'A seleção mudou em outra aba. Atualize e tente novamente.'}) from None
    except ErroDePersistencia:
        raise HTTPException(503, detail={'codigo': 'PACK_STORAGE_UNAVAILABLE',
            'mensagem': 'Não foi possível acessar os packs. Tente novamente; suas imagens permanecem no Estúdio.'}) from None


@router.post('')
async def salvar(pedido: packs.PedidoPack, quem: Identidade = Depends(exigir_usuario),
                 repo: Repositorio = Depends(obter_repo)):
    return await resposta(packs.salvar_assets(repo, quem.sub, pedido))


@router.get('')
async def listar(quem: Identidade = Depends(exigir_usuario), repo: Repositorio = Depends(obter_repo),
                 offset: int = Query(0, ge=0, le=100000), q: Annotated[str, Query(max_length=120)] = ''):
    params = {'owner_id': f'eq.{quem.sub}', 'order': 'created_at.desc,id.asc', 'limit': 21, 'offset': offset}
    if q.strip():
        # Literal substring, not SQL wildcard or PostgREST filter syntax.
        term = q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_').replace('*', '\\*')
        params['nome'] = f'ilike.%{term}%'
    rows = await resposta(repo._get(packs.TABLE, params))
    return {'packs': [packs.dto(x) for x in rows[:20]], 'has_more': len(rows) > 20}


@router.post('/meta')
async def salvar_meta(pedido: packs.PedidoPackMeta, request: Request,
                      quem: Identidade = Depends(exigir_admin), repo: Repositorio = Depends(obter_repo)):
    from app.routers.meta_local import _exigir_host_local, _repositorio_read_model
    _exigir_host_local(request)
    return await resposta(packs.salvar_meta(repo, _repositorio_read_model(), quem.sub, pedido))


@router.get('/drafts/{draft_ref}/selections')
async def listar_selecoes(draft_ref: UUID, quem: Identidade = Depends(exigir_usuario),
                          repo: Repositorio = Depends(obter_repo)):
    return await resposta(packs.listar_selecoes_do_rascunho(repo, quem.sub, draft_ref))


@router.put('/drafts/{draft_ref}/adsets/{adset_key}')
async def fixar_selecao(
    draft_ref: UUID,
    pedido: packs.PedidoSelecaoPack,
    adset_key: str = Path(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    quem: Identidade = Depends(exigir_usuario),
    repo: Repositorio = Depends(obter_repo),
):
    return await resposta(packs.fixar_pack_no_conjunto(
        repo, quem.sub, draft_ref, adset_key, pedido))


@router.delete('/drafts/{draft_ref}/adsets/{adset_key}')
async def retirar_selecao(
    draft_ref: UUID,
    expected_version: int = Query(ge=1),
    adset_key: str = Path(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    quem: Identidade = Depends(exigir_usuario),
    repo: Repositorio = Depends(obter_repo),
):
    return await resposta(packs.retirar_pack_do_conjunto(
        repo, quem.sub, draft_ref, adset_key, expected_version))


@router.get('/{pack_id}/selecao')
async def selecionar(pack_id: UUID, quem: Identidade = Depends(exigir_usuario),
                      repo: Repositorio = Depends(obter_repo),
                      manifest_sha256: Annotated[str | None, Query(pattern=r'^[a-f0-9]{64}$')] = None):
    return await resposta(packs.selecionar_assets(repo, quem.sub, str(pack_id), manifest_sha256))


@router.post('/{pack_id}/assets')
async def adicionar(pack_id: UUID, pedido: packs.PedidoAdicionarAssets,
                    quem: Identidade = Depends(exigir_usuario), repo: Repositorio = Depends(obter_repo)):
    return await resposta(packs.adicionar_assets(repo, quem.sub, str(pack_id), pedido))


@router.get('/{pack_id}')
async def detalhe(pack_id: UUID, quem: Identidade = Depends(exigir_usuario),
                  repo: Repositorio = Depends(obter_repo),
                  manifest_sha256: Annotated[str | None, Query(pattern=r'^[a-f0-9]{64}$')] = None):
    row = await resposta(packs._pack_do_dono(repo, quem.sub, str(pack_id), manifest_sha256))
    if not row:
        raise HTTPException(404, detail={'codigo': 'PACK_NOT_FOUND',
            'mensagem': 'Pack não encontrado para sua conta.'})
    return packs.dto(row)
