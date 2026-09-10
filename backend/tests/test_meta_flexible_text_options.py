"""Explicit per-adset pools: all approved options survive save/compile/readback."""
from copy import deepcopy
from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.trafego.meta_execucao.compilador import compilar_plano_v2, descongelar_plano
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from app.trafego.meta_execucao.executor import ExecutorMetaPausado, ErroRemotoMeta
from app.routers.trafego_meta_validacao import PedidoPlanoMetaV2, PedidoTextosFlexiveisV2, _plano_v2_do_pedido, _resumo_v2
from app.trafego.meta.draft_storage import CampaignDraft
from test_meta_flexible_images import flexible
from test_meta_contrato_v2 import _referencias, _plano_v2, c2
from test_meta_rotas_v2 import _corpo
from test_meta_campaign_draft import draft_fixture

POOL = {'primary_text': ['Primeira copy', 'Segunda copy'],
        'headline': ['Primeiro título', 'Segundo título'], 'description': ['Descrição 1', 'Descrição 2']}


def plan(pool=None):
    base = flexible()
    return replace(base, conjuntos=(replace(base.conjuntos[0], flexible_texts=c2.TextosFlexiveisMeta(**(pool or POOL))),))


def compile(plan_value=None):
    value = plan_value or plan()
    return compilar_plano_v2(value, _referencias(value.asset_refs),
        c2.ReferenciasDePublicoResolvidas(measurement_source_ids={'metapixel_0123456789': '555'}))


def body(pool=None):
    raw = _corpo(recipe_id='WEB_SALES_CONVERSION', creative_mode='FLEXIBLE_IMAGES')
    raw['adsets'][0]['measurement'] = {'purpose': 'OPTIMIZE', 'source_kind': 'PIXEL',
        'source_ref': 'metapixel_0123456789', 'standard_event': 'CONTENT_VIEW'}
    raw['adsets'][0]['flexible_texts'] = deepcopy(pool or POOL)
    return raw


def test_single_group_contains_all_texts_and_deduplicates_images():
    compiled = compile()
    ops = [op for op in compiled.operacoes if op.tipo_objeto == 'ad']
    assert len(ops) == 1
    groups = ops[0].payload['creative_asset_groups_spec']['groups']
    assert len(groups) == 1 and groups[0]['images'] == [{'hash': 'hash_da_peca_01'}]
    assert groups[0]['texts'] == c2.TextosFlexiveisMeta(**POOL).textos_graph()
    creative = next(op for op in compiled.operacoes if op.tipo_objeto == 'creative')
    link = creative.payload['object_story_spec']['link_data']
    assert link['message'] == POOL['primary_text'][0] and link['name'] == POOL['headline'][0]
    assert link['description'] == POOL['description'][0]
    resumed = descongelar_plano(compiled.congelar())
    assert resumed.plano_sha256 == compiled.plano_sha256
    assert resumed.operacoes[-1].payload == compiled.operacoes[-1].payload


def test_distinct_images_are_all_preserved_without_crossing_adsets():
    value = plan()
    other_ref = 'metaasset_pool_002'
    second = replace(value.conjuntos[0], adset_key='second', nome='Segundo',
                     flexible_texts=c2.TextosFlexiveisMeta(['Somente segundo'], ['Título exclusivo']))
    existing = value.anuncios[1]
    changed_image = replace(existing, variacao=replace(existing.variacao, asset_ref=other_ref))
    another = replace(existing, adset_key='second', variacao=replace(existing.variacao,
        variation_key='other', creative_name='Outro criativo', ad_name='Outro anúncio', asset_ref=other_ref))
    value = replace(value, conjuntos=(*value.conjuntos, second),
                    anuncios=(value.anuncios[0], changed_image, value.anuncios[2], another))
    refs = _referencias(value.asset_refs)
    refs = replace(refs, image_hashes_by_ref={**refs.image_hashes_by_ref, other_ref: 'hash_da_peca_02'},
                   asset_supply_manifests={**refs.asset_supply_manifests,
                       other_ref: replace(refs.asset_supply_manifests[other_ref], provider_image_hash='hash_da_peca_02')})
    compiled = compilar_plano_v2(value, refs, c2.ReferenciasDePublicoResolvidas(
        measurement_source_ids={'metapixel_0123456789': '555'}))
    ads = [op for op in compiled.operacoes if op.tipo_objeto == 'ad']
    first, other = [op.payload['creative_asset_groups_spec']['groups'][0] for op in ads]
    assert first['images'] == [{'hash': 'hash_da_peca_01'}, {'hash': 'hash_da_peca_02'}]
    assert other['images'] == [{'hash': 'hash_da_peca_02'}]
    assert other['texts'] == second.flexible_texts.textos_graph()


@pytest.mark.parametrize('field', ['primary_text', 'headline', 'description'])
def test_changing_any_option_changes_approval_identity(field):
    pool = deepcopy(POOL)
    pool[field][1] += ' alterado'
    assert compile(plan(pool)).plano_sha256 != compile().plano_sha256


def test_frozen_approval_cannot_be_replayed_after_silent_option_edit():
    snapshot = deepcopy(compile().congelar())
    ad = next(op for op in snapshot['operacoes'] if op['tipo'] == 'ad')
    ad['payload']['creative_asset_groups_spec']['groups'][0]['texts'][-1]['text'] = 'Texto não aprovado'
    with pytest.raises(ErroDeNascimentoMeta):
        descongelar_plano(snapshot)


def test_description_empty_is_real_absence_not_fabricated_copy():
    pool = {**POOL, 'description': []}
    raw = body(pool)
    raw['ads'][0]['description'] = ''
    parsed = _plano_v2_do_pedido(PedidoPlanoMetaV2.model_validate(raw))
    compiled = compile(parsed)
    creative = next(op for op in compiled.operacoes if op.tipo_objeto == 'creative')
    assert 'description' not in creative.payload['object_story_spec']['link_data']
    group = compiled.operacoes[-1].payload['creative_asset_groups_spec']['groups'][0]
    assert not any(t['text_type'] == 'description' for t in group['texts'])


@pytest.mark.parametrize('field,values', [
    ('primary_text', []), ('headline', []), ('primary_text', [' ']),
    ('headline', ['']), ('description', ['']), ('description', ['x'] * 6),
    ('primary_text', ['x'] * 6), ('headline', ['x'] * 6),
    ('primary_text', ['x' * 2201]), ('headline', ['x' * 256]), ('description', ['x' * 256]),
])
def test_pool_validation_is_strict_in_dto_and_domain(field, values):
    pool = {**POOL, field: values}
    with pytest.raises(ValidationError):
        PedidoTextosFlexiveisV2.model_validate(pool)
    with pytest.raises(ErroDeNascimentoMeta):
        c2.TextosFlexiveisMeta(**pool)


def test_maximum_five_per_type_and_unknown_fields():
    pool = {key: [f'Opção {i}' for i in range(5)] for key in POOL}
    parsed = PedidoTextosFlexiveisV2.model_validate(pool)
    assert len(c2.TextosFlexiveisMeta(**parsed.model_dump()).textos_graph()) == 15
    with pytest.raises(ValidationError):
        PedidoTextosFlexiveisV2.model_validate({**pool, 'unexpected': 'no'})


def test_static_and_legacy_still_reject_empty_description():
    with pytest.raises(ErroDeNascimentoMeta):
        replace(_plano_v2(), conjuntos=(replace(_plano_v2().conjuntos[0], flexible_texts=c2.TextosFlexiveisMeta(**POOL)),))
    for mode in ('STATIC', 'FLEXIBLE_IMAGES'):
        raw = body()
        raw['creative_mode'] = mode
        raw['adsets'][0].pop('flexible_texts')
        raw['ads'][0]['description'] = ''
        with pytest.raises(ErroDeNascimentoMeta):
            _plano_v2_do_pedido(PedidoPlanoMetaV2.model_validate(raw))


def test_summary_contains_all_reviewable_options_and_correct_group_count():
    summary = _resumo_v2(plan())
    assert summary['conjuntos'][0]['flexible_texts'] == POOL
    assert summary['total_grupos_de_imagem'] == 1
    assert summary['conjuntos'][0]['grupos_de_imagem'] == 1


@pytest.mark.parametrize('field', ['primary_text', 'headline', 'description'])
def test_readback_rejects_losing_any_option(field):
    payload = deepcopy(dict(compile().operacoes[-1].payload))
    payload.update(adset_id='222', creative={'creative_id': '333'})
    data = dict(deepcopy(payload), id='444', account_id='123', campaign_id='111', creative={'id': '333'})
    def verify():
        ExecutorMetaPausado._validar_read_back('ad', data, payload=payload, identificador='444', ids={'campaign': '111'}, conta_externa='123')
    verify()
    texts = data['creative_asset_groups_spec']['groups'][0]['texts']
    texts.remove(next(t for t in texts if t['text_type'] == field))
    with pytest.raises(ErroRemotoMeta, match='creative_asset_groups_spec'):
        verify()


def test_draft_roundtrip_preserves_options_and_incomplete_edit_not_authority():
    raw = draft_fixture()
    raw['creativeMode'] = 'flexible'
    raw['conjuntos'][0]['flexibleTexts'] = deepcopy(POOL)
    saved = CampaignDraft.model_validate(raw).persisted()
    assert saved['conjuntos'][0]['flexibleTexts'] == POOL
    assert CampaignDraft.model_validate(saved).persisted() == saved
    assert saved['variations'][0]['assetRightsConfirmed'] is False
    raw['conjuntos'][0]['flexibleTexts'] = {'primary_text': [''], 'headline': [], 'description': []}
    assert CampaignDraft.model_validate(raw).persisted()['conjuntos'][0]['flexibleTexts']['primary_text'] == ['']
