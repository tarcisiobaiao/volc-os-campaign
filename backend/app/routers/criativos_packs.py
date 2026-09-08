"""Packs use the same authenticated Studio boundary, never browser service keys."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
    except (ErroDePersistencia, ConflitoDeChave):
        raise HTTPException(503, detail={'codigo': 'PACK_STORAGE_UNAVAILABLE',
            'mensagem': 'Não foi possível acessar os packs. Tente novamente; suas imagens permanecem no Estúdio.'}) from None


@router.post('')
async def salvar(pedido: packs.PedidoPack, quem: Identidade = Depends(exigir_usuario),
                 repo: Repositorio = Depends(obter_repo)):
    return await resposta(packs.salvar_assets(repo, quem.sub, pedido))


@router.get('')
async def listar(quem: Identidade = Depends(exigir_usuario), repo: Repositorio = Depends(obter_repo),
                 offset: int = Query(0, ge=0, le=100000)):
    rows = await resposta(repo._get(packs.TABLE, {'owner_id': f'eq.{quem.sub}',
        'order': 'created_at.desc,id.asc', 'limit': 21, 'offset': offset}))
    return {'packs': [packs.dto(x) for x in rows[:20]], 'has_more': len(rows) > 20}


@router.post('/meta')
async def salvar_meta(pedido: packs.PedidoPackMeta, request: Request,
                      quem: Identidade = Depends(exigir_admin), repo: Repositorio = Depends(obter_repo)):
    from app.routers.meta_local import _exigir_host_local, _repositorio_read_model
    _exigir_host_local(request)
    return await resposta(packs.salvar_meta(repo, _repositorio_read_model(), quem.sub, pedido))


@router.get('/{pack_id}/selecao')
async def selecionar(pack_id: UUID, quem: Identidade = Depends(exigir_usuario),
                      repo: Repositorio = Depends(obter_repo)):
    return await resposta(packs.selecionar_assets(repo, quem.sub, str(pack_id)))
