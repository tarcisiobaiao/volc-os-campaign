"""Duas passagens: fixtures herméticas, sem publicação ou rede."""
import copy
import json
import httpx
import pytest
from funnelforge.adapters.attention_matrix import modulo_do_repo, perguntas
from funnelforge.adapters.decisao_intencao import HeuristicaDeIntencao, JevDeIntencao
from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.config.settings import StepConfig
from funnelforge.domain.models import RunState
from funnelforge.pipeline.inteligencia import compilar_brief, congelar_pacotes, mensagens_do_arquiteto, pacote_conferido, prompt_do_pacote
from funnelforge.pipeline.jornada import revisar_esqueleto
from funnelforge.pipeline.pipeline import run_pipeline, _populate_routes
from tests.cenario_editorial import montar_deps, settings_do_cenario, responder_v2, REVISOR_APROVA
from tests.test_dossie_factual import _Pesquisa, _ligar_pesquisa, _compilar, FATOS_COMPLETOS, arquitetura
CARD = {"main_keyword":"curso gratuito Senac", "country":"BR", "native_language":"pt-BR", "location_code":2076,"language_code":"pt"}
SERP = {"items":[{"type":"people_also_ask","items":[{"title":q} for q in ["Quem tem direito?","Quem tem direito?","Direito quem tem?","Como calcular a renda?"]]}]}
def brief():
    return compilar_brief(CARD,{"perguntas":["Quem tem direito?"],"origem":"fixture"})

def test_paa_real_cache_uma_serp(tmp_path,monkeypatch):
    sensor=modulo_do_repo("backend/app/motor_pautas/sensores/dataforseo.py")
    calls,extractions=[],[]
    original=sensor.perguntas_do_paa
    monkeypatch.setattr(sensor,"perguntas_do_paa",lambda s:(extractions.append(s),original(s))[1])
    class Cliente:
        def chamar(self,endpoint,tarefas):
            calls.append((endpoint,tarefas))
            return {"tasks":[{"result":[SERP]}]}
    a=perguntas(CARD,tmp_path,cliente=Cliente(),agora=1000)
    b=perguntas(CARD,tmp_path,cliente=Cliente(),agora=1001)
    assert a['perguntas']==b['perguntas'] and len(extractions)==2
    assert b['origem']=='cache_serp_recente' and len(calls)==1
    assert calls[0][1][0]['depth']==10

def test_paa_ausente_duplicatas_sem_fatos(tmp_path):
    vazio=compilar_brief(CARD,perguntas(CARD,tmp_path))
    assert not vazio.duvidas and vazio.lacunas
    p=perguntas({**CARD,'serp':SERP},tmp_path)
    b=compilar_brief(CARD,p)
    assert len(b.duvidas)==2 and not b.fatos_existentes
    assert all(not s['factual'] for s in b.sinais)
    assert sorted(d.jornada.duvida_id for d in b.duvidas)==sorted(d.jornada.duvida_id for d in compilar_brief(CARD,{**p,'perguntas':list(reversed(p['perguntas']))}).duvidas)

def test_brief_arquiteto_e_requisitos():
    b=brief()
    assert b.sha256 in mensagens_do_arquiteto(b)[1]['content']
    assert b.duvidas[0].jornada.requisitos
    assert all(p.jornada.requisitos for p in plano_do_funnel_architecture(arquitetura()).pages)

@pytest.mark.parametrize('defeito',['entrega','loop','resolvida','requisito','cta'])
def test_defeitos_pre_writer(defeito):
    plan=plano_do_funnel_architecture(arquitetura()); plan.brief_pre_arquitetura=brief(); p=plan.pages[1]
    if defeito=='entrega': p.jornada.valor=None
    elif defeito=='loop': p.jornada.proxima_duvida=plan.pages[0].jornada.duvida_id
    elif defeito=='resolvida': p.jornada.ja_resolvido.append(p.jornada.proxima_duvida)
    elif defeito=='requisito': p.jornada.requisitos=[]
    else: p.editorial.cta_label='Saiba mais'
    assert revisar_esqueleto(plan).bloqueantes

def test_sha_estavel_copia_isolada_prompt(tmp_path):
    s=settings_do_cenario(tmp_path,editorial_v2=True,passos_v2=True)
    _,deps=montar_deps(tmp_path,s,responder_v2)
    state=RunState(run_id='pacotes',plan=plano_do_funnel_architecture(arquitetura()),brief_pre_arquitetura=brief())
    d=_compilar(state,_Pesquisa(FATOS_COMPLETOS)); state.dossie=d.model_dump(mode='json')
    _populate_routes(state,deps); congelar_pacotes(state,deps); antes=copy.deepcopy(state.pacotes)
    congelar_pacotes(state,deps); assert antes==state.pacotes
    p=state.plan.pages[0]; local=pacote_conferido(state,p); local['pagina']['h1_title']='mutação'
    assert state.pacotes==antes and antes[1]['sha256'] in prompt_do_pacote(state,p)
    state.pacotes[1]['avatar']='corrompido'
    with pytest.raises(ValueError,match='SHA-256'): pacote_conferido(state,p)

def raw_arquiteto():
    a=arquitetura(); pages=[]
    for p,job in zip(a['pages'],a['writing_jobs']):
        w=job['writer_briefing']
        pages.append({'page_number':w['page_num'],'page_type':('LANDING PAGE' if w['page_num']==1 else 'SOLUÇÃO'),'slug':w['current_url'],'h1_title':w['headline'],'emotional_objective':w['objective'],'main_content_structure':p['subtitles'],'target_keywords':[],'hook_to_next_page':w['cta_text'],'editorial':w['editorial'],'jornada':w['jornada']})
    return {'funnel_strategy':a['funnel_strategy'],'pages':pages}

def cenario(tmp_path,monkeypatch,invalida=False):
    pesquisa=_Pesquisa([],FATOS_COMPLETOS); _ligar_pesquisa(monkeypatch,pesquisa)
    s=settings_do_cenario(tmp_path,editorial_v2=True,passos_v2=True)
    s.run.dossie_factual=True; s.run.page_workers=3; s.run.imagens_habilitadas=False; s.run.max_retries=0
    s.steps['dossie']=StepConfig(model='gemini/gemini-3.8-flash',web_search=True)
    s.steps['extract']=StepConfig(model='gpt-4.1')
    def responder(model,messages):
        text=messages[-1]['content']
        if 'REVISOR GLOBAL' in text:
            return json.dumps({'paginas':[{'page_number':n,'revisao':json.loads(REVISOR_APROVA)} for n in range(1,6)]})
        if len(messages)==2 and 'brief_pre_arquitetura' in text:
            a=raw_arquiteto()
            if invalida: a['pages'][1]['jornada']['valor']=None
            return json.dumps(a)
        return responder_v2(model,messages)
    llm,deps=montar_deps(tmp_path,s,responder)
    class Proibido:
        def __getattr__(self,nome): raise AssertionError('Publicação proibida')
    deps.publisher=Proibido()
    state=run_pipeline(None,deps,card_pre_arquitetura=CARD,publish=False,timestamp='hermetico')
    return state,llm,pesquisa

def test_invalida_zero_writer(tmp_path,monkeypatch):
    state,llm,pesquisa=cenario(tmp_path,monkeypatch,True)
    assert state.step_status['funnel_graph'].status.value=='FAILED'
    assert not any(k.startswith('write_') for k in state.step_status)
    assert len(llm.calls)==1 and len(pesquisa.pedidos)==1

def test_duas_passagens_lote_sem_repesquisa_sem_publicar(tmp_path,monkeypatch):
    state,llm,pesquisa=cenario(tmp_path,monkeypatch)
    assert state.brief_pre_arquitetura and len(pesquisa.pedidos)==2
    assert pesquisa.pedidos[0] is None and pesquisa.pedidos[1] is not None
    assert len({f['requisito'] for f in pesquisa.pedidos[1]})==len(pesquisa.pedidos[1])
    assert len(state.pacotes)==5 and 'revisor_lote' in state.step_status
    assert not any(k.startswith('dossie_complemento_p') for k in state.step_status)
    assert all(state.step_status[f'briefing_p{n}'].attempts==0 for n in range(1,6))
    assert not state.published

ROTULADAS=[('Como calcular a renda?','ferramenta'),('Qual o telefone do órgão?','faq'),('O que é o benefício?','secao'),('Quem tem direito?','avaliar')]
def test_jev_off_rotulos():
    qs,labels=map(list,zip(*ROTULADAS)); j=JevDeIntencao(enabled=False,key='fixture')
    assert HeuristicaDeIntencao().classificar(qs)['formatos']==labels
    assert j.classificar(qs)['formatos']==labels and j.chamadas==0

@pytest.mark.parametrize('falha',['timeout','contrato','http'])
def test_jev_failsoft_sem_retry_segredo(falha):
    def responder(req):
        if falha=='timeout': raise httpx.ReadTimeout('segredo fixture')
        return httpx.Response(500 if falha=='http' else 200,json={})
    j=JevDeIntencao(enabled=True,key='segredo_fixture',transport=httpx.MockTransport(responder))
    r=j.classificar(['Como calcular?'])
    assert r['fallback'] and r['formatos']==['ferramenta'] and j.chamadas==1
    assert 'segredo' not in json.dumps(r)
    j.classificar(['Como calcular?']); assert j.chamadas==1

def test_jev_recibo_hermetico():
    def responder(req):
        assert json.loads(req.content)['questions']['q0']['type']=='choice'
        return httpx.Response(200,json={'model':'jev-fixture','answers':{'q0':{'type':'choice','choice':'faq','confidence':0.9}}})
    j=JevDeIntencao(enabled=True,key='fixture',transport=httpx.MockTransport(responder)); r=j.classificar(['Qual o telefone?'])
    assert r['requested_model']=='jev-latest' and r['served_model']=='jev-fixture' and not r['fallback']

def test_lacuna_compartilhada_complementada_uma_vez():
    from funnelforge.domain.models import RequisitoFactual
    from funnelforge.pipeline.dossie import CompiladorDeDossie
    from tests.test_dossie_factual import _estado, _Deps, _registrar_canais, _ler
    state=_estado()
    for p in state.plan.pages[1:3]:
        p.jornada.requisitos.append(RequisitoFactual(id='canal.compartilhado',descricao='Canal nacional do PSG'))
    pesquisa=_Pesquisa([],[])
    vivo=CompiladorDeDossie(state,_Deps(),pesquisa,registrar_canais=_registrar_canais,ler_documento=_ler)
    vivo.compilar(complementos=0)
    vivo.complementar_lote(state.plan.pages,state)
    assert len(pesquisa.pedidos)==2
    assert sum(f['requisito']=='canal.compartilhado' for f in pesquisa.pedidos[1])==1


def test_fonte_indisponivel_afeta_so_dependentes():
    from tests.test_dossie_factual import _estado, _Verificador, CITADAS, EAD
    state=_estado(); d=_compilar(state,_Pesquisa(FATOS_COMPLETOS),_Verificador([u for u in CITADAS if u!=EAD]))
    status={p.duvida_id:p.cobertura.estado for p in d.paginas}
    assert status['curso'] in {'degraded','review'}
    assert status['renda']=='ready' and status['inscricao']=='ready'


def test_worker_nao_altera_pacotes_ou_irmaos():
    from funnelforge.pipeline import paralelo as par
    from tests.test_dossie_factual import _estado
    original=_estado(); original.pacotes={1:{'sha256':'congelado'},2:{'sha256':'irma'}}
    copia=original.model_copy(deep=True); copia.pacotes[2]['sha256']='mutado'
    delta=par.extrair_delta(original,copia,copia.plan.pages[0],sinal=None,publicar=False,duracao_s=0)
    assert delta.violacoes and original.pacotes[2]['sha256']=='irma'


def test_writer_so_recebe_seu_sha(tmp_path,monkeypatch):
    state,llm,_=cenario(tmp_path,monkeypatch)
    prompts=[c['messages'][-1]['content'] for c in llm.calls if 'Pacote congelado prevalece:' in c['messages'][-1]['content']]
    assert len(prompts)==5
    for n,pacote in state.pacotes.items():
        own=[p for p in prompts if pacote['sha256'] in p]
        assert len(own)==1
        assert not any(other['sha256'] in own[0] for m,other in state.pacotes.items() if m!=n)


def test_contexto_historico_compacto_sem_duplicacao_no_prompt():
    arq=raw_arquiteto()
    b=compilar_brief({**CARD,'historico':{'arquitetura_referencia':arq,'origem':'fixture'}},
                    {'perguntas':[],'origem':'ausente'})
    assert 'arquitetura_referencia' not in b.contexto['historico']
    assert len(b.contexto['historico']['paginas_anteriores'])==5
    prompt=mensagens_do_arquiteto(b)[1]['content']
    assert prompt.count('"paginas_anteriores"')==1
