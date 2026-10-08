from __future__ import annotations

import json
import pytest

from funnelforge.pipeline.copy_contract import (
    SHORT_NOTICE, clean_body_notice, cta_issues, disclosure_issues, footer_discloses,
)
from funnelforge.pipeline.doctrine import COMPLIANCE_NOTICE_TEXT
from funnelforge.pipeline.editorial_safety import EDITORIAL_NOTICE
from funnelforge.pipeline.lp_template import _fillable, load_lp_template, render_lp
from funnelforge.pipeline.validators.checks import run_validators
from funnelforge.prompts import render
from tests.test_perfil_rapido import _rodar, _revisor, _todos_pass

CTX = {'copy_rapida': True, 'domain':'https://portal.test',
       'rodape_institucional_persistente':True,
       'rodape_institucional':'Conteúdo informativo sem vínculo com instituições. Financiado por anúncios.'}


@pytest.mark.parametrize('label', ['Ver o que acontece com seu saldo',
    'Entender quanto pode sair por ano', 'Descobrir qual situação se aplica',
    'Ver como consultar sua situação no aplicativo'])
def test_cta_nomeia_resposta_em_vez_de_formato(label):
    assert cta_issues([(label,'https://portal.test/rec/resposta')],CTX)==[]


@pytest.mark.parametrize('label', ['Consultar saldo','Solicitar benefício','Liberar valor',
                                   'Receber dinheiro','Calcular agora','Sacar agora'])
def test_execucao_nao_pode_ser_prometida_por_conteudo(label):
    assert 'cta_editorial_execution' in {i.code for i in cta_issues([(label,'/rec/resposta')],CTX)}


@pytest.mark.parametrize('label', ['Ler o guia','Abrir o guia','Acessar o conteúdo',
    'Leia o guia de calendário','Guia de calendário','Saiba mais','Ver informações',
    'Continuar','Ver o passo a passo','Identificar qual dúvida resolver',
    'Descobrir qual assunto ver primeiro'])
def test_generico_recusado_com_feedback_acionavel(label):
    issues=cta_issues([(label,'/rec/resposta')],CTX)
    assert issues[0].code=='cta_generic' and 'resposta' in issues[0].message
    assert cta_issues([(label,'/rec/resposta')],{**CTX,'copy_rapida':False})==[]


def test_externo_identifica_canal_e_nao_segue_regra_de_execucao_editorial():
    assert cta_issues([('Consultar no site da instituição (externo)','https://instituicao.test/app')],CTX)==[]
    assert cta_issues([('Consultar agora','https://instituicao.test/app')],CTX)[0].code=='cta_external_channel'
    assert cta_issues([('Consultar no site da instituição','/rec/artigo')],CTX)[0].code=='cta_editorial_execution'


def test_lp_json_tambem_tem_feedback_antes_do_modelo_ser_retentado():
    from tests.cenario_editorial import LP_JSON
    data=json.loads(LP_JSON)
    data['cta_texts']=['Calcular agora','Ler o guia','Ver como conferir o valor']
    issues=run_validators(['lp_json_contract'],json.dumps(data),CTX)
    assert {'cta_editorial_execution','cta_generic'} <= {i.code for i in issues}


def test_disclosure_footer_exige_declaracao_persistente_e_texto_suficiente():
    assert footer_discloses(CTX)
    assert not footer_discloses({**CTX,'rodape_institucional_persistente':False})
    assert not footer_discloses({**CTX,'rodape_institucional':'Sobre nós'})
    assert run_validators(['compliance'],'Conteúdo útil',CTX)==[]
    assert run_validators(['compliance'],'Conteúdo útil',{**CTX,'copy_rapida':False})


def test_aviso_longo_removido_sem_apagar_alertas_contextuais():
    body=(f'<!-- wp:paragraph --><p>{COMPLIANCE_NOTICE_TEXT}</p><!-- /wp:paragraph -->'
          '<!-- wp:paragraph --><p>Não envie CPF ou senha nem pague para consultar.</p><!-- /wp:paragraph -->')
    assert clean_body_notice(body,footer=True).count(COMPLIANCE_NOTICE_TEXT)==0
    assert 'Não envie CPF ou senha' in clean_body_notice(body,footer=True)
    short=clean_body_notice(body,footer=False)
    assert short.count(SHORT_NOTICE)==1
    assert clean_body_notice(short,footer=False)==short
    assert not disclosure_issues(short,{**CTX,'rodape_institucional_persistente':False})
    assert disclosure_issues(short+short,CTX)[0].code=='duplicate_disclosure'
    assert disclosure_issues(COMPLIANCE_NOTICE_TEXT,CTX)[0].code=='long_body_disclaimer'


def test_renderer_lp_disclosure_curto_ou_footer_sem_mudar_v1():
    from tests.cenario_editorial import LP_JSON
    args=dict(template=load_lp_template(),content=json.loads(LP_JSON),funnel_hrefs=['https://portal.test/rec/x']*3)
    v1,_=render_lp(**args)
    assert EDITORIAL_NOTICE in json.dumps(v1,ensure_ascii=False)
    short,_=render_lp(**args,copy_rapida=True)
    assert json.dumps(short,ensure_ascii=False).count(SHORT_NOTICE)==1
    footer,_=render_lp(**args,copy_rapida=True,footer_disclosure=True)
    assert SHORT_NOTICE not in json.dumps(footer,ensure_ascii=False)
    assert EDITORIAL_NOTICE not in json.dumps(footer,ensure_ascii=False)
    assert v1==render_lp(**args,copy_rapida=False,footer_disclosure=True)[0]


def test_renderer_rapido_usa_breakpoints_sem_depender_de_id_ou_indice():
    from tests.cenario_editorial import LP_JSON
    template=load_lp_template()
    # Simula reexport do Elementor: ids e ordem externa mudam, mas os dois
    # containers continuam declarando o breakpoint que representam.
    template['content'][0]['id']='id-novo-mobile'
    template['content'][1]['id']='id-novo-desktop'
    content=json.loads(LP_JSON)
    rendered,_=render_lp(template,content,['https://portal.test/rec/x']*3,
                         copy_rapida=True,footer_disclosure=True)
    heroes=[n for n in rendered if (n.get('settings') or {}).get('hide_desktop')
            or (n.get('settings') or {}).get('hide_mobile')]
    assert len(heroes)==2
    for hero in heroes:
        headings=[w for w in _fillable([hero]) if w.get('widgetType')=='heading']
        assert [h['settings']['header_size'] for h in headings[:2]]==['h1','p']


def test_prompt_rapido_da_prioridade_ao_ganho_e_nao_injeta_aviso_longo():
    normal=render('redator_pages',headline='tema',editorial={})
    fast=render('redator_pages',headline='tema',editorial={},escrita_natural=True)
    assert COMPLIANCE_NOTICE_TEXT in normal
    assert COMPLIANCE_NOTICE_TEXT not in fast
    assert '[identificação controlada' not in fast
    assert 'Não escreva disclaimer institucional no corpo' in fast
    assert 'ação + resposta + canal' in fast
    assert 'qual incerteza fica menor' in fast
    assert '<copy_do_avanco' in fast and '<copy_do_avanco' not in normal


@pytest.mark.parametrize('name', ['redator_pages', 'redator_pages_v2'])
def test_prompt_rapido_nunca_expoe_marcador_copiavel_ao_modelo(name):
    fast=render(name,headline='tema',objective='resolver',skeleton=[],keywords=[],
                editorial={},escrita_natural=True)
    assert COMPLIANCE_NOTICE_TEXT not in fast
    assert '[identificação controlada' not in fast
    assert 'qual incerteza fica menor' in fast


def test_funil_inteiro_com_identidade_curta_e_zero_disclaimer_longo(tmp_path,monkeypatch):
    state,folder,_=_rodar(tmp_path,monkeypatch,_revisor(_todos_pass))
    for n,draft in state.drafts.items():
        assert COMPLIANCE_NOTICE_TEXT not in draft.content
        if n!=1: assert draft.content.count(SHORT_NOTICE)==1
    lp=(folder/'p1.elementor.json').read_text()
    assert EDITORIAL_NOTICE not in lp and lp.count(SHORT_NOTICE)==1
    assert all(state.step_status[f'content_gate_p{n}'].status.value=='OK' for n in state.drafts)


def test_falsa_oficialidade_nao_e_perdoada_pelo_footer():
    assert run_validators(['calm_utility'],'Sistema oficial do governo',CTX)
