"""Two real failure modes: invented official paths and instructions as SEO.

No network, auth, inference, publication or new evaluation framework.
"""
import pytest

from funnelforge.domain.models import PageDraft
from funnelforge.pipeline.steps import seo_deterministico
from funnelforge.pipeline.validators.checks import contextual_links
from tests.test_lucro_por_visita import _plano

OFFICIAL = 'https://www.gov.br/mds/pt-br/acoes-e-programas/gas-do-povo'


def ctx(**changes):
    return {'contextual_editorial': True, 'domain': 'https://creditoup.com.br',
            'resolved_internal_routes': ['https://creditoup.com.br/rec/retirada'],
            'resolved_external_links': [OFFICIAL], **changes}


def body(href):
    return f'<!-- wp:paragraph --><p>Fonte: <a href="{href}">MDS</a>.</p><!-- /wp:paragraph -->'


def test_body_official_same_host_wrong_path_is_not_authorized():
    issues = contextual_links(body(OFFICIAL + '-errado'), ctx())
    assert [i.code for i in issues] == ['unplanned_external_link']


@pytest.mark.parametrize('href', [OFFICIAL, OFFICIAL + '/', OFFICIAL + '#regra',
                                OFFICIAL + '?utm_source=openai'])
def test_exact_verified_source_and_nonfunctional_tracking_are_accepted(href):
    assert not contextual_links(body(href), ctx())


def test_functional_query_is_not_silently_authorized():
    assert contextual_links(body(OFFICIAL + '?beneficiario=outro'), ctx())


def test_no_verified_external_source_does_not_authorize_one():
    assert contextual_links(body(OFFICIAL), ctx(resolved_external_links=[]))


@pytest.mark.parametrize('href', ['/rec/retirada', '#documentos'])
def test_internal_planned_route_and_local_anchor_remain_valid(href):
    assert not contextual_links(body(href), ctx())


def test_old_context_without_new_source_list_keeps_legacy_behavior():
    old = ctx()
    old.pop('resolved_external_links')
    assert not contextual_links(body(OFFICIAL + '-errado'), old)


def draft(content, format='gutenberg'):
    return PageDraft(page_number=3, page_type='SOLUÇÃO', content=content, format=format)


def test_meta_uses_written_answer_instead_of_architect_instruction():
    page = _plano().pages[2]
    page.jornada.resposta_imediata = 'A página deve explicar a regra de renda.'
    seo = seo_deterministico(page, draft('<p>Confira a regra de renda e os critérios do programa.</p>'))
    assert seo['metadescription'] == 'Confira a regra de renda e os critérios do programa.'


def test_meta_decodes_text_not_markup_or_entities():
    page = _plano().pages[2]
    page.jornada.resposta_imediata = 'A página deve explicar.'
    seo = seo_deterministico(page, draft('<p>Regra de <strong>renda</strong> &amp; cadastro.</p>'))
    assert seo['metadescription'] == 'Regra de renda & cadastro.'


def test_lp_meta_uses_visible_intro_if_brief_is_instruction():
    page = _plano().pages[0]
    page.jornada.resposta_imediata = 'The page should explain the program.'
    seo = seo_deterministico(page, draft('{"intro":"Conheça o programa e confira os critérios."}', 'lp_json'))
    assert seo['metadescription'] == 'Conheça o programa e confira os critérios.'


def test_meta_without_written_answer_never_publishes_instruction():
    page = _plano().pages[2]
    page.jornada.resposta_imediata = 'La página debe explicar el programa.'
    assert seo_deterministico(page, None)['metadescription'] == ''


def test_meta_always_describes_the_written_page_not_the_plan():
    page = _plano().pages[2]
    page.jornada.resposta_imediata = 'O programa atende famílias conforme os critérios publicados.'
    assert seo_deterministico(page, draft('<p>Outra abertura.</p>'))['metadescription'] == 'Outra abertura.'


def test_imperative_from_actual_canary_never_becomes_meta():
    page = _plano().pages[2]
    page.jornada.resposta_imediata = 'Descrever os meios de validação comprovados e suas condições de uso.'
    assert seo_deterministico(page, draft('<p>Prepare a identificação para a retirada.</p>'))['metadescription'] == 'Prepare a identificação para a retirada.'


def test_broken_lp_json_does_not_fall_back_to_architect_instructions():
    page = _plano().pages[0]
    page.jornada.resposta_imediata = 'Explicar o programa.'
    assert seo_deterministico(page, draft('{"intro":', 'lp_json'))['metadescription'] == ''


@pytest.mark.parametrize('v2', [True, False])
def test_existing_writer_context_wires_verified_urls_only_in_v2(config_files, v2):
    from funnelforge.domain.models import ResearchFacts, RunState
    from funnelforge.pipeline.routing import build_funnel_routes
    from funnelforge.pipeline.steps import _write_ctx
    from tests.fakes import FakeLLM
    from tests.test_contextual_editorial import plan
    from tests.test_steps_prompt_routing import _deps
    deps = _deps(config_files, FakeLLM(responses=[]))
    p = plan()
    build_funnel_routes(p, deps.settings)
    page = p.pages[2]
    state = RunState(run_id='exact-source', plan=p, editorial_v2=v2,
                     facts={3: ResearchFacts(fontes_resolvidas=[OFFICIAL])})
    context = _write_ctx(state, page, deps)
    if v2:
        assert OFFICIAL in context['resolved_external_links']
        assert contextual_links(body(OFFICIAL + '-errado'), context)
    else:
        assert 'resolved_external_links' not in context
