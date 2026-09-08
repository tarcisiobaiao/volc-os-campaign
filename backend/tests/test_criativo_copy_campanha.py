"""Only approved, owner-scoped copy reaches a draft. No providers or DB writes."""
import pytest

from test_criativo_agente_retomada import (
    OWNER, PROJECT_REF, RUN_REF, RepoDeRetomada, _cliente, _decisao, _run,
)
from test_criativo_studio_adaptador import saida


def caso():
    lote = saida(1)
    lote.recibo.valido = True
    decisions = [
        _decisao('/pecas/creative_variacao_1', 'APROVADO',
                 snapshot=lote.pecas[0].model_dump(mode='json'), quando='2026-09-08T10:00:00Z'),
        _decisao('/copies_compartilhadas/copy_grupo_1', 'APROVADO',
                 snapshot=lote.copies_compartilhadas[0].model_dump(mode='json'), quando='2026-09-08T10:01:00Z'),
    ]
    return RepoDeRetomada(runs=[_run(RUN_REF, lote, quando='2026-09-08T09:00:00Z')], decisoes=decisions)


URL = f'/api/criativos/meta/agente/operacoes/{PROJECT_REF}/runs/{RUN_REF}/copy-de-campanha/creative_variacao_1'


def test_copy_is_external_text_not_pixels_and_not_launch_approval():
    repo = caso()
    r = _cliente(repo).get(URL)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['message'].startswith('COPY EXTERNA')
    assert 'Headline interna' not in str(data)
    assert data['scope'] == 'DRAFT_COPY_ONLY'
    assert data['launch_authorized'] is False
    assert data['media_registered'] is False
    assert len(data['snapshot_sha256']) == 64
    assert OWNER not in str(data)
    assert len(repo.decisoes) == 2  # no approval written by export
    assert _cliente(repo).get(URL).json() == data


@pytest.mark.parametrize('defeito', ['sem_copy', 'sem_peca', 'revogada', 'alterada', 'grupo', 'lote', 'incompleto', 'duplicada', 'cta'])
def test_export_fails_closed(defeito):
    repo = caso()
    output = repo.runs[0]['output']
    if defeito == 'sem_copy': repo.decisoes.pop()
    elif defeito == 'sem_peca': repo.decisoes.pop(0)
    elif defeito == 'revogada':
        repo.decisoes.append({**repo.decisoes[-1], 'decisao': 'REPROVADO', 'created_at': '2026-09-08T11:00:00Z'})
    elif defeito == 'alterada': output['copies_compartilhadas'][0]['texto_principal'] = 'Texto reescrito sem nova aprovação'
    elif defeito == 'grupo': output['copies_compartilhadas'][0]['group_ref'] = 'group_outro'
    elif defeito == 'lote': output['recibo']['valido'] = False
    elif defeito == 'incompleto': repo.decisoes *= 500
    elif defeito == 'duplicada': output['pecas'] *= 2
    elif defeito == 'cta': output['copies_compartilhadas'][0]['cta_nativa'] = 'DOWNLOAD'
    assert _cliente(repo).get(URL).status_code == 409


def test_other_owner_cannot_export():
    assert _cliente(caso(), sub='22222222-2222-4222-8222-222222222222').get(URL).status_code == 404


def test_wrong_project_run_pair_and_non_completed_run_cannot_export():
    repo = caso()
    repo.runs[0]['project_ref'] = 'crproj_' + 'c' * 24
    assert _cliente(repo).get(URL).status_code == 409
    repo.runs[0]['project_ref'] = PROJECT_REF
    repo.runs[0]['status'] = 'RUNNING'
    assert _cliente(repo).get(URL).status_code == 409
