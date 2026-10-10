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
from funnelforge.pipeline.inteligencia import (
    chave_da_pergunta,
    compilar_brief,
    congelar_pacotes,
    mensagens_do_arquiteto,
    pacote_conferido,
    prompt_do_pacote,
)
from funnelforge.pipeline.jornada import revisar_esqueleto
from funnelforge.pipeline.jornada._comum import norm, tokens
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


def test_demanda_unicode_nao_apaga_nem_colapsa_tailandes():
    perguntas = [
        'เงินอุดหนุนบุตร',
        'เงินอุดหนุนบุตร 2569',
        'เงินอุดหนุนบุตรตุลาคม 2569',
        'เงินอุดหนุนบุตรเข้าวันไหน',
        'เงินอุดหนุนบุตรเดือนตุลาคม 2569',
    ]
    chaves = [chave_da_pergunta(q) for q in perguntas]
    assert all(chaves)
    assert len(set(chaves)) == len(perguntas)
    brief = compilar_brief(
        {"main_keyword": perguntas[0], "country": "TH", "native_language": "th-TH"},
        {"perguntas": perguntas, "origem": "attention_matrix_fixture"},
    )
    assert len(brief.duvidas) == 5
    assert {d.jornada.pergunta_principal for d in brief.duvidas} == set(perguntas)


def test_validadores_de_jornada_nao_transformam_tailandes_em_string_vazia():
    cta = 'ดูวันโอนแต่ละเดือนในปี 2569 เพื่อวางแผน'
    h1 = 'ปฏิทินเงินอุดหนุนบุตร 2569: วันโอนแต่ละเดือน'
    assert norm(cta)
    assert norm(h1)
    assert norm(cta) != norm(h1)
    assert tokens(cta)

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


def test_hub_decisional_sem_requisito_factual_nao_inventa_pesquisa():
    plan=plano_do_funnel_architecture(arquitetura()); plan.brief_pre_arquitetura=brief()
    hub=next(p for p in plan.pages if p.role.value=='PRESELL')
    hub.jornada.requisitos=[]
    assert 'requisitos_previsiveis_ausentes' not in {
        i.code for i in revisar_esqueleto(plan).bloqueantes
        if f'[{hub.jornada.duvida_id}]' in i.message}

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

def cenario(tmp_path,monkeypatch,invalida=False,aliases_conflitantes=False):
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
            if aliases_conflitantes:
                a['pages'][0]['jornada']['requisitos'] = [{
                    'id': 'regra.correta', 'fact_id': 'regra.diferente',
                    'descricao': 'Regra correta', 'afirmacao': 'Outra afirmação',
                }]
            return json.dumps(a)
        return responder_v2(model,messages)
    llm,deps=montar_deps(tmp_path,s,responder)
    class Proibido:
        def __getattr__(self,nome): raise AssertionError('Publicação proibida')
    deps.publisher=Proibido()
    state=run_pipeline(None,deps,card_pre_arquitetura=CARD,publish=False,timestamp='hermetico')
    return state,llm,pesquisa

def test_entrega_editorial_incompleta_avisa_sem_barrar_writer(tmp_path,monkeypatch):
    state,llm,pesquisa=cenario(tmp_path,monkeypatch,True)
    assert any(k.startswith('write_') for k in state.step_status)
    assert not state.published


def test_alias_conflitante_recusado_antes_do_writer(tmp_path,monkeypatch):
    state,llm,pesquisa=cenario(tmp_path,monkeypatch,aliases_conflitantes=True)
    assert state.step_status['extract'].status.value=='FAILED'
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
        payload = json.loads(req.content)
        assert payload['state']['pais'] == 'BR'
        assert payload['state']['perguntas'][0]['duvida_id'] == 'q_telefone'
        assert payload['model'] == 'jev-1.13.0'
        assert payload['questions']['emocao_incerteza_0']['type'] == 'noul'
        assert payload['questions']['emocao_oportunidade_0']['type'] == 'noul'
        assert payload['questions']['ganho_informacional_0']['type'] == 'score'
        assert payload['questions']['intencao_0']['type'] == 'choice'
        assert payload['state']['contexto_medido']['monthly_searches'] == 1200
        answers = {}
        for chave, questao in payload['questions'].items():
            if chave.startswith('formato_'):
                answers[chave] = {'type':'choice','choice':'faq','confidence':0.91}
            elif chave.startswith('emocao_incerteza_'):
                answers[chave] = {'type':'noul','noul':0.92}
            elif chave.startswith('emocao_necessidade_de_acao_'):
                answers[chave] = {'type':'noul','noul':0.78}
            elif chave.startswith('emocao_'):
                answers[chave] = {'type':'noul','noul':0.12}
            elif chave.startswith(('sinal_observavel_', 'respondavel_editorialmente_')):
                answers[chave] = {'type':'noul','noul':0.94}
            elif questao['type'] == 'noul':
                answers[chave] = {'type':'noul','noul':0.73}
            elif chave.startswith('entrega_'):
                answers[chave] = {'type':'choice','choice':'confirmacao','confidence':0.84}
            elif chave.startswith('momento_'):
                answers[chave] = {'type':'choice','choice':'qualificacao','confidence':0.86}
            elif chave.startswith('intencao_'):
                answers[chave] = {'type':'choice','choice':'acesso_oficial','confidence':0.89}
            else:
                answers[chave] = {'type':'score','score':3,'confidence':0.9}
        return httpx.Response(200,json={'model':'jev-fixture','answers':answers,
                                        'usage':{'input_tokens':1000,'output_tokens':300}})
    j=JevDeIntencao(enabled=True,key='fixture',transport=httpx.MockTransport(responder))
    r=j.classificar(['Qual o telefone?'], contexto={'tema':'benefício','pais':'BR',
        'idioma':'pt-BR','duvida_ids':['q_telefone'],
        'contexto_medido':{'monthly_searches':1200}})
    assert r['requested_model']=='jev-1.13.0' and r['served_model']=='jev-fixture' and not r['fallback']
    perfil = r['perfil_emocional']
    assert perfil['familia_dominante'] == 'incerteza'
    assert perfil['climax_duvida_id'] == 'q_telefone'
    assert perfil['sinais'][0]['intensidade'] == 75.0
    assert perfil['sinais'][0]['correspondencia']['incerteza'] == 92.0
    assert perfil['sinais'][0]['correspondencia']['necessidade_de_acao'] == 78.0
    assert perfil['sinais'][0]['sensibilidade_temporal'] == 73.0
    assert perfil['sinais'][0]['intencao'] == 'acesso_oficial'
    assert perfil['sinais'][0]['direcao_cta']
    assert r['custo_usd'] is None
    assert r['custo_estimado_usd'] == pytest.approx(0.000042)
    assert j.chamadas == 1


def test_jev_um_lote_com_vinte_sinais_nao_cai_na_heuristica():
    def responder(req):
        payload=json.loads(req.content); answers={}
        for chave, questao in payload['questions'].items():
            if chave.startswith('formato_'):
                answers[chave]={'type':'choice','choice':'avaliar','confidence':.9}
            elif chave.startswith('emocao_incerteza_'):
                answers[chave]={'type':'noul','noul':.91}
            elif chave.startswith('emocao_'):
                answers[chave]={'type':'noul','noul':.1}
            elif questao['type']=='noul':
                answers[chave]={'type':'noul','noul':.9}
            elif chave.startswith('entrega_'):
                answers[chave]={'type':'choice','choice':'criterios','confidence':.9}
            elif chave.startswith('momento_'):
                answers[chave]={'type':'choice','choice':'qualificacao','confidence':.9}
            elif chave.startswith('intencao_'):
                answers[chave]={'type':'choice','choice':'elegibilidade','confidence':.9}
            else:
                answers[chave]={'type':'score','score':3,'confidence':.9}
        return httpx.Response(200,json={'model':'jev-fixture','answers':answers})
    perguntas=[f'Eu tenho direito no caso {n}?' for n in range(20)]
    j=JevDeIntencao(enabled=True,key='fixture',transport=httpx.MockTransport(responder))
    r=j.classificar(perguntas,contexto={'duvida_ids':[f'q{n}' for n in range(20)]})
    assert not r['fallback'] and len(r['perfil_emocional']['sinais'])==20
    assert j.chamadas==1


def test_jev_pos_arquitetura_verifica_arestas_sem_reescrever_plano():
    plan=plano_do_funnel_architecture(arquitetura())
    antes=plan.model_dump(mode='json')
    def responder(req):
        payload=json.loads(req.content)
        assert payload['state']['fase']=='pos_arquitetura'
        assert payload['state']['arestas']
        answers={}
        for chave, questao in payload['questions'].items():
            if questao['type']=='noul':
                if chave.startswith(('cta_generico_','resposta_origem_')):
                    valor=.50  # inconclusivo: não cria revisão humana
                elif chave.startswith('resultado_pessoal_'):
                    valor=.08
                else:
                    valor=.94
                answers[chave]={'type':'noul','noul':valor}
            else:
                answers[chave]={'type':'score','score':4,'confidence':.93}
        return httpx.Response(200,json={'model':'jev-1.13.0','answers':answers,
                                       'usage':{'input_tokens':1500,'output_tokens':400}})
    j=JevDeIntencao(enabled=True,key='fixture',transport=httpx.MockTransport(responder))
    resultado=j.verificar_jornada(plan, contexto={'tema':'Senac','pais':'BR','idioma':'pt-BR'})
    assert not resultado['fallback']
    assert resultado['arestas'] and all(a['decisao']=='usar' for a in resultado['arestas'])
    assert resultado['resumo']['usar']==len(resultado['arestas'])
    assert resultado['custo_estimado_usd']==pytest.approx(.000063)
    assert plan.model_dump(mode='json')==antes
    assert j.chamadas==1


def test_brief_entrega_contexto_medido_e_proveniencia_ao_jev():
    visto={}
    class Provider:
        def classificar(self, perguntas, *, contexto=None):
            visto.update(contexto)
            return HeuristicaDeIntencao().classificar(perguntas, contexto=contexto)
    card={**CARD,
          'volumes':{'Quem tem direito?':3210},
          'contexto_de_busca':{'monthly_searches':3210,'cpc_usd':.17,
                               'radar_state':'em_janela'},
          'search_terms':[{'termo':'quem pode fazer curso gratuito'}]}
    compilar_brief(card,{'perguntas':['Quem tem direito?'],'origem':'dataforseo'},provider=Provider())
    assert visto['contexto_medido']['monthly_searches']==3210
    assert visto['duvidas'][0]['prioridade']==3210
    assert {e['tipo'] for e in visto['duvidas'][0]['evidencia_demanda']}=={'paa'}


def test_brief_propaga_avatar_comportamental_sem_duplicar():
    class Provider:
        def classificar(self, perguntas, *, contexto=None):
            assert {k: contexto[k] for k in ('tema','pais','idioma')} == {
                'tema':'curso gratuito Senac','pais':'BR','idioma':'pt-BR'}
            assert len(contexto['duvida_ids']) == 1
            sinal = {'pergunta': perguntas[0], 'duvida_id':contexto['duvida_ids'][0],
                     'familia':'oportunidade',
                     'correspondencia':{'oportunidade':82.0,'incerteza':18.0},
                     'confianca':91.0,'intensidade':75.0,'autorrelevancia':50.0,
                     'potencial_continuacao':100.0,'urgencia_de_acao':25.0,
                     'entrega':'criterios','momento':'qualificacao','formato':'avaliar',
                     'direcao_cta':'mostrar o critério concreto','limite_cta':'sem promessa'}
            perfil = {'schema_version':1,'estado':'presente','provider':'typesafe_jev',
                      'modelo_pedido':'jev-latest','modelo_servido':'jev-fixture',
                      'familia_dominante':'oportunidade','distribuicao':{'oportunidade':82.0},
                      'resumo':'Busca uma possibilidade concreta.','sinais':[sinal],
                      'correlacoes':[],'climax_pergunta':0,
                      'climax_duvida_id':contexto['duvida_ids'][0],
                      'hipotese':'Hipótese a calibrar.'}
            return {'formatos':['avaliar'],'provider':'typesafe_jev',
                    'requested_model':'jev-latest','served_model':'jev-fixture',
                    'fallback':False,'perfil_emocional':perfil}
    b = compilar_brief(CARD, {'perguntas':['Quem tem direito?'],'origem':'fixture'},
                       provider=Provider())
    assert b.perfil_emocional.familia_dominante == 'oportunidade'
    assert b.duvidas[0].sinal_emocional.entrega == 'criterios'
    assert 'perfil_emocional' not in b.contexto['decisao_intencao']
    prompt = mensagens_do_arquiteto(b)[1]['content']
    assert prompt.count('"perfil_emocional"') == 1
    assert 'não uma pessoa inventada' in prompt

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


def test_resposta_real_do_arquiteto_normaliza_aliases_de_requisito():
    """Regressão do canário real de 08/10: alias seguro não derruba o funil."""
    contrato = modulo_do_repo("backend/app/agents/funnel_pro/jornada_contrato.py")
    factory = modulo_do_repo("backend/app/agents/funnel_pro/page_factory.py")
    raw = raw_arquiteto()
    for numero, pagina in enumerate(raw["pages"], 1):
        pagina["jornada"]["requisitos"] = [{
            "fact_id": f"p{numero}_r1",
            "afirmacao": "Confirmar a regra oficial antes de publicar.",
            "base_disponivel": "pesquisa oficial adicional necessária",
        }]
    normalizada, recibo = contrato.normalizar_arquitetura(raw)
    assert recibo["estado"] == "valida"
    assert len(recibo["normalizacoes"]) == len(raw["pages"]) * 2
    assert len(recibo["avisos"]) == len(raw["pages"])
    for pagina in normalizada["pages"]:
        requisito = pagina["jornada"]["requisitos"][0]
        assert set(requisito) == {"id", "descricao"}
    canonica = {
        "funnel_strategy": normalizada["funnel_strategy"],
        "pages": factory.architect_pages_to_funnel_pages(normalizada),
        "writing_jobs": factory.page_factory(normalizada)["writingJobs"],
    }
    plano = plano_do_funnel_architecture(canonica)
    assert len(plano.pages) == 5
    assert all(p.jornada.requisitos[0].id.startswith("p") for p in plano.pages)


def test_aliases_conflitantes_de_requisito_falham_fechado():
    contrato = modulo_do_repo("backend/app/agents/funnel_pro/jornada_contrato.py")
    raw = raw_arquiteto()
    raw["pages"][0]["jornada"]["requisitos"] = [{
        "id": "regra.correta",
        "fact_id": "regra.diferente",
        "descricao": "Regra correta",
        "afirmacao": "Outra afirmação",
    }]
    _, recibo = contrato.normalizar_arquitetura(raw)
    assert recibo["estado"] == "invalida"
    assert {e["motivo"] for e in recibo["erros"]} == {
        "id e fact_id conflitantes", "descricao e afirmacao conflitantes"
    }


def test_saida_direta_do_arquiteto_aplica_papeis_e_reescreve_links():
    """Regressão do 2º canário: a saída crua ainda não tem sufixos de papel."""
    contrato = modulo_do_repo("backend/app/agents/funnel_pro/jornada_contrato.py")
    factory = modulo_do_repo("backend/app/agents/funnel_pro/page_factory.py")
    roles = modulo_do_repo("backend/app/entities/funnel_roles.py")
    raw = raw_arquiteto()
    mapa = {
        "por-onde-comecar-senac-pr": "por-onde-comecar-senac",
        "tipos-de-curso-senac-p1": "tipos-de-curso-senac",
        "bolsas-de-estudo-senac-p2": "bolsas-de-estudo-senac",
        "portal-do-senac-do-seu-estado-p3": "portal-do-senac-do-seu-estado",
    }
    for pagina in raw["pages"]:
        pagina["slug"] = mapa.get(pagina["slug"], pagina["slug"])
        for link in pagina["editorial"]["links"]:
            link["target"] = mapa.get(link["target"], link["target"])
    normalizada, recibo = contrato.normalizar_arquitetura(raw)
    assert recibo["estado"] == "valida"
    paginas = factory.architect_pages_to_funnel_pages(normalizada)
    jobs = factory.page_factory(normalizada)["writingJobs"]
    paginas, jobs = roles.apply_roles_and_slugs(paginas, jobs)
    canonica = {"funnel_strategy": normalizada["funnel_strategy"],
                "pages": paginas, "writing_jobs": jobs}
    plano = plano_do_funnel_architecture(canonica)
    slugs = {p.slug for p in plano.pages}
    assert "por-onde-comecar-senac-pr" in slugs
    assert "tipos-de-curso-senac-p1" in slugs
    assert [p.ordinal for p in plano.pages if p.role.value == "SOLUTION"] == [1, 2, 3]
    assert all(link.target in slugs for p in plano.pages
               if p.editorial for link in p.editorial.links)
