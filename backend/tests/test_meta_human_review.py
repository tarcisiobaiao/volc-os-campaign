from unittest.mock import AsyncMock
from types import SimpleNamespace
import pytest
from test_meta_revisao_de_midia import setup
from app.trafego.meta_execucao import revisao_de_midia as review
from app.trafego.meta_execucao.registro_de_midia import LivroDeRegistroDeMidiaSupabase, ErroDeRegistroDeMidia

@pytest.mark.anyio
async def test_human_default_never_constructs_or_calls_ai(setup, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError('Human review must never call a detector')
    monkeypatch.setattr(review,'detector_meta_se_autorizado',forbidden)
    monkeypatch.setattr(review.politica,'avaliar',forbidden)
    monkeypatch.setattr(review,'detectores_de_pixel_registrados',forbidden)
    assert review.capacidades_de_inspecao()['envia_para_ia'] is False
    piece, repo=setup
    rows=await review.revisar_pecas([piece],repo=repo,ator='owner',account_ref='metaacct_example')
    assert rows[0]['utilizavel'] and rows[0]['modo_revisao']=='HUMAN_ONLY'
    assert rows[0]['politica']['decisao']=='HUMAN_REVIEW' and rows[0]['politica']['detectores']==[]
    repo.approvals[0]['revogada_em']='now'
    assert not (await review.revisar_pecas([piece],repo=repo,ator='owner',account_ref='metaacct_example'))[0]['utilizavel']

@pytest.mark.anyio
async def test_scoped_ledger_checks_authority_each_write_without_global_flag(monkeypatch):
    from app.trafego.meta_execucao import capacidades
    monkeypatch.setattr(capacidades,'ledger_liberado',lambda:False)
    service=SimpleNamespace(enabled=True,base='https://database.agenciavolc.com.br',rpc=AsyncMock(return_value={'ok':True}))
    authority=AsyncMock(side_effect=[True,False])
    book=LivroDeRegistroDeMidiaSupabase(service,autorizar_escrita=authority)
    assert await book._rpc('trafego_meta_reservar_registro_ativo',{})=={'ok':True}
    assert await book._rpc('trafego_meta_concluir_registro_ativo',{})=={'ok':True}
    with pytest.raises(ErroDeRegistroDeMidia): await book._rpc('trafego_meta_reservar_registro_ativo',{})
    assert service.rpc.await_count==2
    with pytest.raises(ErroDeRegistroDeMidia): await LivroDeRegistroDeMidiaSupabase(service)._rpc('test',{})
