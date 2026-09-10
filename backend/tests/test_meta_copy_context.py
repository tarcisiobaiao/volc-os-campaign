"""Hermetic traversal of saved creative relationships; no live DB/model/network."""
import asyncio
from copy import deepcopy
import hashlib
import json
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.routers import trafego_meta_copy as route
from app.trafego.meta.copy_context import clean, destination_identity, read_saved_context
from app.trafego.meta.copy_suggestions import CopyFailure
from app.trafego.meta.dominio import referencia_opaca_conta
from app.trafego.meta_execucao.registro_de_midia import referencia_opaca_de_imagem
from app.seguranca.identidade import Identidade, exigir_admin
from test_meta_campaign_draft import draft_fixture


class GraphFixture:
    def __init__(self):
        self.calls = []
        self.pack_id, self.master_id, self.job_id = str(uuid4()), str(uuid4()), str(uuid4())
        self.project, self.run = 'crproj_' + 'a' * 24, 'crrun_' + 'b' * 24
        self.bridge = {'project_ref': self.project, 'run_ref': self.run,
            'creative_ref': 'creative_chosen', 'copy_ref': 'copy_chosen', 'group_ref': 'group_chosen'}
        self.master = {'id': self.master_id, 'job_id': self.job_id, 'kind': 'imagem', 'arquivado_em': None, 'content_hash': 'c' * 64}
        self.manifest = {'source': 'STUDIO', 'items': [{'master_ref': self.master_id, 'job_id': self.job_id,
            'content_hash': 'c' * 64, 'strategy': deepcopy(self.bridge)}]}
        self.digest = hashlib.sha256(json.dumps(self.manifest, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        self.pack = {'id': self.pack_id, 'nome': 'Pack Educação', 'manifest': self.manifest, 'manifest_sha256': self.digest}
        self.selection = {'pack_id': self.pack_id, 'manifest_sha256': self.digest, 'master_refs': [self.master_id], 'version': 2}
        self.record = {'input': {'project_ref': self.project, 'url_destino': 'https://example.test/encceja/',
            'assunto_principal': 'Encceja 2026', 'ancora_de_desejo': 'Certificação',
            'contexto_do_publico': 'PRIVATE AUDIENCE DATA MUST NOT ENTER',
            'fatos_da_oferta': [{'ref': 'fact_lp_abc', 'declaracao': 'O artigo explica as etapas do exame.'},
                                {'ref': 'fact_other', 'declaracao': 'OTHER TOPIC MUST NOT ENTER'}],
            'contexto_da_pagina': {'url_solicitada': 'https://example.test/encceja/', 'url_final': 'https://example.test/encceja/',
                'titulo': 'Entenda o Encceja', 'fatos': [{'ref': 'fact_lp_abc'}],
                'motivacoes_sugeridas': [{'tipo': 'desejo', 'hipotese': 'Entender o caminho de certificação',
                    'pergunta_latente': 'Quais são as etapas?', 'entrega_da_pagina': 'Explicação das etapas', 'fato_refs': ['fact_lp_abc']},
                    {'tipo': 'receio', 'hipotese': 'UNSUPPORTED MOTIVATION', 'fato_refs': ['fact_other']}]}},
            'output': {'project_ref': self.project, 'pecas': [{'ref': 'creative_chosen', 'group_ref': 'group_chosen',
                'shared_copy_ref': 'copy_chosen', 'angulo': 'Tirar dúvidas', 'fato_refs': ['fact_lp_abc'],
                'big_idea': {'pergunta_latente': 'Como funciona?'}, 'direcao_de_arte': {'cena': 'Um estudante com material de estudo'}},
                {'ref': 'creative_other', 'hook': 'UNSELECTED PIECE MUST NOT ENTER'}],
                'copies_compartilhadas': [{'ref': 'copy_chosen', 'group_ref': 'group_chosen', 'fato_refs': ['fact_lp_abc'],
                    'texto_principal': 'Descubra as etapas para planejar seus estudos.', 'titulo': 'Entenda as etapas', 'descricao': 'Informação editorial'}]}}
        self.draft = draft_fixture()
        self.physical = '1234567890'
        self.draft['accountRef'] = referencia_opaca_conta(self.physical)
        self.draft['variations'][0]['assetRef'] = referencia_opaca_de_imagem(self.physical, 'imagehash123')
        self.draft['destinationUrl'] = 'https://example.test/encceja/?utm_source=meta'
        self.draft['variations'][0]['packOrigin'] = {'packId': self.pack_id, 'manifestHash': self.digest,
            'masterRef': self.master_id, 'accountRef': self.draft['accountRef'], 'selectionVersion': 2}
        self.receipt = {'account_ref': self.draft['accountRef'], 'actor_id': 'owner-one',
            'master_ref': self.master_id, 'content_sha256': self.master['content_hash'], 'state': 'REGISTRADO', 'image_hash': 'imagehash123'}
        self.missing = set()
        self.revision = None

    async def select(self, table, params):
        self.calls.append((table, deepcopy(params)))
        if table == 'trafego_meta_ad_account':
            assert params['select'] == 'account_external_id' and params['limit'] == 100
            return [] if table in self.missing else [{'account_external_id': self.physical}]
        assert params['limit'] == 2
        if table == 'criativo_master':
            assert params['criativo_job.criado_por'] == 'eq.owner-one'
            assert '!inner' in params['select']
            result = self.master
        elif table == 'trafego_meta_asset_registration':
            assert params['actor_id'] == 'eq.owner-one'
            assert params['account_ref'] == f'eq.{self.draft["accountRef"]}'
            assert params['master_ref'] == f'eq.{self.master_id}'
            assert params['content_sha256'] == f'eq.{self.master["content_hash"]}'
            result = self.receipt
        else:
            assert params['owner_id'] == 'eq.owner-one'
            result = {'trafego_meta_rascunho_pack': self.selection, 'criativo_reuso_pack': self.pack,
                'criativo_reuso_pack_revision': self.revision, 'criativo_agente_peca_job': self.bridge,
                'criativo_agente_run': self.record}[table]
        if table == 'criativo_agente_run':
            assert params['project_ref'] == f'eq.{self.project}'
            assert params['run_ref'] == f'eq.{self.run}' and params['status'] == 'eq.COMPLETED'
            assert params['select'] == 'input,output'
        return [] if table in self.missing or result is None else [deepcopy(result)]

    def resolve(self):
        return asyncio.run(read_saved_context(self, 'owner-one', uuid4(), self.draft, 'adset-001'))


def test_selected_asset_exact_run_facts_and_motives_only():
    graph = GraphFixture()
    result = graph.resolve()
    context = result['saved_creative_context'][0]
    assert context['facts_from_saved_briefing'] == ['O artigo explica as etapas do exame.']
    assert len(context['motivations_hypotheses']) == 1
    assert context['visual_summary_saved_not_inspected'] == 'Um estudante com material de estudo'
    assert result['context_summary']['mode'] == 'SAVED_CREATIVE_CONTEXT'
    assert result['context_summary']['facts_count'] == 1
    assert {s['kind'] for s in result['context_summary']['sources']} == {'LP_SNAPSHOT', 'STRATEGY', 'BRIEFING', 'PACK_COPY'}
    serialized = json.dumps(result)
    for private in (graph.project, graph.run, graph.master_id, graph.pack_id, graph.job_id,
                    'OTHER TOPIC', 'PRIVATE AUDIENCE', 'UNSUPPORTED MOTIVATION', 'UNSELECTED PIECE', 'https://'):
        assert private not in serialized


@pytest.mark.parametrize('table', ['trafego_meta_rascunho_pack', 'criativo_reuso_pack', 'criativo_master',
    'trafego_meta_asset_registration', 'trafego_meta_ad_account', 'criativo_agente_peca_job', 'criativo_agente_run'])
def test_missing_or_foreign_edge_falls_back_honestly(table):
    graph = GraphFixture(); graph.missing.add(table)
    result = graph.resolve()
    assert result['saved_creative_context'] == []
    assert result['context_summary']['mode'] == 'CURRENT_TEXTS_ONLY'
    assert result['context_summary']['warnings']


def test_pack_revision_used_instead_of_new_latest_contents():
    graph = GraphFixture()
    graph.revision = deepcopy(graph.pack)
    graph.pack['manifest_sha256'] = 'd' * 64
    graph.pack['manifest'] = {'items': [{'unrelated': 'LATEST MUST NOT ENTER'}]}
    result = graph.resolve()
    assert result['context_summary']['mode'] == 'SAVED_CREATIVE_CONTEXT'
    assert any(table == 'criativo_reuso_pack_revision' for table, _ in graph.calls)


@pytest.mark.parametrize('kind', ['version', 'digest', 'master', 'project', 'destination', 'query'])
def test_stale_or_mismatched_origin_excluded(kind):
    graph = GraphFixture()
    if kind == 'version': graph.selection['version'] = 3
    elif kind == 'digest': graph.manifest['items'][0]['content_hash'] = 'e' * 64
    elif kind == 'master': graph.master['content_hash'] = 'e' * 64
    elif kind == 'project': graph.record['output']['project_ref'] = 'crproj_' + 'f' * 24
    elif kind == 'destination': graph.draft['destinationUrl'] = 'https://example.test/other-topic/'
    elif kind == 'query': graph.draft['destinationUrl'] = 'https://example.test/encceja/?article=other'
    result = graph.resolve()
    assert result['saved_creative_context'] == []
    assert result['context_summary']['warnings']


def test_ad_without_origin_does_not_inherit_unrelated_locked_pack():
    graph = GraphFixture()
    graph.draft['variations'][0].pop('packOrigin')
    graph.draft['variations'][0]['assetRef'] = 'metaasset_other'
    assert graph.resolve()['saved_creative_context'] == []
    graph.draft['variations'][0]['assetRef'] = ''
    graph.draft['variations'][0]['videoRef'] = ''
    assert graph.resolve()['saved_creative_context']


def test_parent_check_before_any_graph_read():
    graph = GraphFixture()
    with pytest.raises(CopyFailure):
        asyncio.run(read_saved_context(graph, 'owner-one', uuid4(), graph.draft, 'other-adset'))
    assert not graph.calls


def test_text_redaction_and_destination_identity():
    result = clean('2026 test@example.test CPF 123.456.789-00 Tel (11) 99999-9999 https://example.test/?access_token=secret crproj_abcdef Bearer ' + 'a' * 30)
    for excluded in ('test@example', '123.456', '99999', 'access_token', 'crproj_', 'a' * 30): assert excluded not in result
    assert '2026' in result
    assert destination_identity('https://EXAMPLE.test/a/?utm_campaign=1#x') == 'https://example.test/a'
    assert destination_identity('https://example.test/a?id=1') != destination_identity('https://example.test/a?id=2')


def test_context_length_cap_is_enforced(monkeypatch):
    graph = GraphFixture()
    monkeypatch.setattr('app.trafego.meta.copy_context.MAX_CONTEXT_CHARS', 10)
    result = graph.resolve()
    assert not result['saved_creative_context']
    assert any('limite' in message for message in result['context_summary']['warnings'])


def preview_app(graph, changed=False):
    class Repo:
        service = graph
        reads = 0
        async def read(self, owner, ref):
            self.reads += 1
            if owner != 'owner-one': return None
            return {'draft': deepcopy(graph.draft), 'version': 5 if changed and self.reads > 1 else 4}
    app = FastAPI(); app.include_router(route.router)
    app.dependency_overrides[route.storage] = lambda: Repo()
    app.dependency_overrides[exigir_admin] = lambda: Identidade(sub='owner-one', email='operator@example.test', papel='ADMIN', origem='sessao')
    def forbidden(): raise AssertionError('GET preview must not instantiate any model')
    app.dependency_overrides[route.copy_client] = forbidden
    return TestClient(app)


def test_get_preview_is_summary_only_no_model_or_write():
    response = preview_app(GraphFixture()).get(f'/api/trafego/meta/drafts/{uuid4()}/copy-context?adset_key=adset-001')
    assert response.status_code == 200, response.text
    assert set(response.json()) == {'draft_version', 'context_summary'}
    assert response.json()['context_summary']['facts_count'] == 1
    assert 'Descubra as etapas' not in response.text


def test_get_preview_rechecks_version():
    response = preview_app(GraphFixture(), changed=True).get(f'/api/trafego/meta/drafts/{uuid4()}/copy-context?adset_key=adset-001')
    assert response.status_code == 409


def test_brief_and_campaign_new_url_cannot_reuse_old_page_snapshot():
    graph = GraphFixture()
    graph.record['input']['url_destino'] = 'https://example.test/new-topic/'
    graph.draft['destinationUrl'] = 'https://example.test/new-topic/'
    result = graph.resolve()
    assert not result['saved_creative_context']
    assert any('destino' in warning for warning in result['context_summary']['warnings'])


def test_consistent_recorded_redirect_is_accepted_without_fetch():
    graph = GraphFixture()
    graph.record['input']['contexto_da_pagina']['url_final'] = 'https://example.test/redirected/'
    graph.draft['destinationUrl'] = 'https://example.test/redirected/?utm_source=meta'
    assert graph.resolve()['saved_creative_context']


@pytest.mark.parametrize('field,value', [('assetRef', 'metaasset_different'), ('videoRef', 'metavideo_other'),
    ('existingPostRef', 'metapost_' + 'a' * 32), ('assetRef', '')])
def test_changed_actual_ad_media_never_uses_old_pack_origin(field, value):
    graph = GraphFixture()
    graph.draft['variations'][0][field] = value
    result = graph.resolve()
    assert not result['saved_creative_context']
    assert any('vínculo de envio' in warning for warning in result['context_summary']['warnings'])


@pytest.mark.parametrize('field,value', [('actor_id', 'other-owner'), ('account_ref', 'metaacct_other'),
    ('master_ref', 'other-master'), ('content_sha256', 'd' * 64), ('state', 'AMBIGUO'), ('image_hash', 'differenthash')])
def test_registration_must_bind_owner_account_master_bytes_and_actual_asset(field, value):
    graph = GraphFixture(); graph.receipt[field] = value
    assert not graph.resolve()['saved_creative_context']
    if field != 'image_hash':
        assert not any(table == 'trafego_meta_ad_account' for table, _ in graph.calls)


@pytest.mark.parametrize('path,value', [
    (('output', 'pecas'), 'old piece format'),
    (('output', 'pecas'), [None]),
    (('output', 'copies_compartilhadas'), [1]),
    (('input', 'fatos_da_oferta'), 'legacy'),
    (('input', 'contexto_da_pagina', 'fatos'), 'legacy'),
    (('input', 'contexto_da_pagina', 'motivacoes_sugeridas'), [1]),
    (('output', 'pecas', 0, 'big_idea'), 'old prose'),
    (('output', 'pecas', 0, 'direcao_de_arte'), 'old prose'),
    (('output', 'pecas', 0, 'fato_refs'), [None]),
])
def test_malformed_legacy_nested_values_are_excluded_not_http_500(path, value):
    graph = GraphFixture()
    target = graph.record
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    response = preview_app(graph).get(f'/api/trafego/meta/drafts/{uuid4()}/copy-context?adset_key=adset-001')
    assert response.status_code == 200, response.text
    assert response.json()['context_summary']['mode'] == 'CURRENT_TEXTS_ONLY'
    assert response.json()['context_summary']['warnings']
