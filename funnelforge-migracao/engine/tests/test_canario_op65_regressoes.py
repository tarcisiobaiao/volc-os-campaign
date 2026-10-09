"""Regressões reais: rótulo oficial não é rendimento; slug descartado não é href."""
import copy
import json
from types import SimpleNamespace

import pytest
from funnelforge.domain.models import ResearchFacts
from funnelforge.pipeline import inteligencia
from funnelforge.pipeline.validators.checks import critical_fact_grounding

SOURCE = 'https://www.fgts.gov.br/Paginas/subpaginas/saque-dispensa.aspx'
LABEL = 'Solicite seu saque 100% digital'


def contexto(**trocas):
    fatos = dict(dados_validados=[{'tipo':'processo','fato':f'A CAIXA orienta selecionar “{LABEL}”.',
                                 'fonte':SOURCE}], fontes_resolvidas=[SOURCE])
    fatos.update(trocas)
    return {'facts': ResearchFacts(**fatos)}


def texto(label=LABEL, fonte=True):
    return f'<p>Selecione “{label}”.' + (f' <a href="{SOURCE}">CAIXA</a>' if fonte else '') + '</p>'


def test_rotulo_literal_de_processo_com_fonte_resolvida_e_citada():
    assert not critical_fact_grounding(texto(), contexto())


@pytest.mark.parametrize('html,ctx,codigo',[
    (texto(fonte=False),contexto(),'critical_claim_without_citation'),
    (texto(),contexto(fontes_resolvidas=[]),'ungrounded_critical_claim'),
    (texto('Receba 100% do saldo'),contexto(),'ungrounded_critical_claim'),
    (texto()+ '<p>Você receberá 100% do saldo.</p>',contexto(),'ungrounded_critical_claim'),
    (texto(),contexto(dados_validados=[{'tipo':'processo','fato':LABEL,'fonte':SOURCE,'citavel':False}]),'ungrounded_critical_claim'),
])
def test_rotulo_nao_autoriza_porcentagem_financeira_ou_fato_sem_fonte(html,ctx,codigo):
    assert codigo in {i.code for i in critical_fact_grounding(html,ctx)}


def test_prompt_projeta_somente_links_resolvidos_sem_mutar_pacote(monkeypatch):
    pacote={
      'pagina':{'page_type':'SOLUÇÃO','role':'SOLUTION','h1_title':'Saldo retido',
        'emotional_objective':'Entender o bloqueio','main_content_structure':[],
        'target_keywords':[],'hook_to_next_page':'Confirmar disponibilidade','page_number':7,
        'engajamento':'','editorial':{'links':[{'target':'slug-descartado-p4','cta':'Pedir o saque','reason':'retorno'}]}},
      'jornada':{'pergunta':'Por que ficou retido?','condicao_terminal':'consulta',
                 'saida_oficial':{'classificacao':'boa'},'plano_visual':[]},
      'destinos':[], 'links':[{'kind':'external_official','href':SOURCE,'anchor':'Conferir condições no FGTS'}],
      'factual':{'urls_oficiais':[SOURCE]},'total_pages':8,'dominio':'https://creditoup.com.br',
      'autor':'Crédito Up','credencial':'','cnpj':'','data':'2026-10-09','sha256':'original',
    }
    original=copy.deepcopy(pacote); capturado={}
    monkeypatch.setattr(inteligencia,'pacote_conferido',lambda *args:copy.deepcopy(pacote))
    import funnelforge.prompts
    monkeypatch.setattr(funnelforge.prompts,'render',lambda nome,**kw:(capturado.update(kw) or 'prompt'))
    inteligencia.prompt_do_pacote(None,SimpleNamespace(page_number=7))
    assert capturado['editorial']['links']==[]
    assert 'slug-descartado-p4' not in capturado['briefing_texto']
    assert json.loads(capturado['briefing_texto'])['links']==pacote['links']
    assert pacote==original
