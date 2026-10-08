"""`chatgpt_plan_web_search` — o provider da pesquisa do dossiê pelo plano.

O transporte é um dublê que emite SSE no formato observado no microprobe real
de 07/10/2026: `response.completed.output` VAZIO, itens só nos eventos."""
from __future__ import annotations

import json
from datetime import date

import pytest

from funnelforge.adapters import pesquisa_plano as pp
from funnelforge.adapters.openai_responses import (
    NaoSuportadoNoPlano, OpenAIResponsesClient, RespostaHTTP)
from funnelforge.config.settings import StepConfig
from funnelforge.pipeline.dossie import fatos_da_resposta, verificar_ao_vivo

PB = "https://pb.senac.br/programa-senac-de-gratuidade/"
MG = "https://programasenacdegratuidade.mg.senac.br/faq.aspx"
NAO_CITADA = "https://ma.senac.br/edital-psg.pdf"
SEGREDO = "tok-secreto-do-teste-123"
CFG = StepConfig(model="chatgpt/gpt-6.1-sol", web_search=True, reasoning_effort="low")
PAGINAS = [{"duvida_id": "renda", "pergunta": "Minha renda se enquadra?", "promessa": "",
            "entregas": [], "requisitos": [{"id": "renda.limite_per_capita",
                                            "descricao": "limite de renda per capita",
                                            "tipos": ["numero", "condicao"]}]}]

FRASE1 = ("[renda.limite_per_capita] O PSG aceita renda familiar mensal por pessoa de até "
          "dois salários mínimos federais, regra do Decreto 6.633 de 2008. ")
FRASE2 = "A renda é somada e dividida pelo número de pessoas da família. "


def _link(url):
    return f"([senac]({url}?utm_source=openai))"


def _texto_e_citacoes():
    l1, l2 = _link(PB), _link(MG)
    texto = FRASE1 + l1 + " " + FRASE2 + l2
    i1 = len(FRASE1)
    i2 = len(FRASE1) + len(l1) + 1 + len(FRASE2)
    return texto, [(PB + "?utm_source=openai", "Senac PB", i1, i1 + len(l1)),
                   (MG + "?utm_source=openai", None, i2, i2 + len(l2))]


def _sse(texto, citacoes=(), sources=(PB, MG, NAO_CITADA), *, modelo="gpt-6.1-sol",
         busca=True, status_busca="completed", completed=True):
    ev = [{"type": "response.created"}]
    if busca:
        ws = {"id": "ws_1", "type": "web_search_call", "status": "in_progress"}
        ev += [{"type": "response.output_item.added", "output_index": 0, "item": ws}]
        ev += [{"type": f"response.web_search_call.{e}", "item_id": "ws_1", "output_index": 0}
               for e in ("in_progress", "searching", "completed")]
        ev += [{"type": "response.output_item.done", "output_index": 0,
                "item": dict(ws, status=status_busca, action={
                    "type": "search", "queries": ["psg renda per capita"],
                    "sources": [{"type": "url", "url": u, "title": None} for u in sources]})}]
    msg = {"id": "msg_1", "type": "message", "status": "in_progress", "content": []}
    ev += [{"type": "response.output_item.added", "output_index": 1, "item": msg}]
    for k in range(0, len(texto), 40):
        ev.append({"type": "response.output_text.delta", "item_id": "msg_1",
                   "output_index": 1, "content_index": 0, "delta": texto[k:k + 40]})
    ev.append({"type": "response.output_text.done", "item_id": "msg_1", "output_index": 1,
               "content_index": 0, "text": texto})
    for ai, (url, titulo, ini, fim) in enumerate(citacoes):
        ev.append({"type": "response.output_text.annotation.added", "item_id": "msg_1",
                   "output_index": 1, "content_index": 0, "annotation_index": ai,
                   "annotation": {"type": "url_citation", "url": url, "title": titulo,
                                  "start_index": ini, "end_index": fim}})
    ev.append({"type": "response.output_item.done", "output_index": 1,
               "item": dict(msg, status="completed")})
    if completed:
        ev.append({"type": "response.completed", "response": {
            "id": "resp_1", "status": "completed", "model": modelo, "output": [],
            "usage": {"input_tokens": 8640, "output_tokens": 228,
                      "output_tokens_details": {"reasoning_tokens": 47}}}})
    return [f"data: {json.dumps(e, ensure_ascii=False)}" for e in ev] + ["data: [DONE]"]


def _estruturado(fatos, **kw):
    return _sse(json.dumps({"fatos": fatos}, ensure_ascii=False), busca=False, **kw)


FATO_OK = {"evidencia_id": "e1", "afirmacao": "O PSG aceita renda familiar por pessoa de até "
           "dois salários mínimos", "tipo": "numero", "valor": "2",
           "unidade": "salários mínimos", "vigente_desde": "2008-11-05",
           "dispositivo": "Decreto 6.633/2008", "paginas": ["renda"],
           "requisitos": ["renda.limite_per_capita"]}
PAGINA_PB = ("renda familiar mensal per capita não ultrapasse dois (2) salários mínimos federais "
             "para concorrer a uma vaga gratuita do Programa Senac de Gratuidade")


class _Credencial:
    def access_token(self, forcar_renovacao=False):
        return SEGREDO


class _Transporte:
    def __init__(self, *respostas):
        self.respostas, self.corpos, self.cabecalhos = list(respostas), [], []

    def __call__(self, url, headers, body, timeout):
        self.corpos.append(body)
        self.cabecalhos.append(headers)
        r = self.respostas.pop(0)
        return r if isinstance(r, RespostaHTTP) else RespostaHTTP(200, iter(r), {})


class _LLM:
    def __init__(self, transporte):
        self.plano = OpenAIResponsesClient(_Credencial(), enviar=transporte)
        self.contadas = []

    def _contar(self, modelo):
        self.contadas.append(modelo)


def _rodar(*respostas, paginas_lidas=None):
    transporte = _Transporte(*respostas)
    llm = _LLM(transporte)
    lidas = {PB: (PAGINA_PB, "")} if paginas_lidas is None else paginas_lidas
    resp = pp.pesquisar_dossie_plano(llm, CFG, "Senac gratuito", PAGINAS, None,
                                     ler=lambda u: lidas.get(u, ("", "HTTP 404")),
                                     hoje="07/10/2026")
    return resp, transporte, llm


def _grounded():
    texto, cits = _texto_e_citacoes()
    return _sse(texto, cits)


# ---------------------------------------------------------------------------

def test_montagem_do_stream_com_output_final_vazio():
    texto, cits = _texto_e_citacoes()
    m = pp.montar_stream(_sse(texto, cits))
    assert m.completed and m.output_no_completed == 0 and m.modelo == "gpt-6.1-sol"
    assert m.texto == texto
    b = m.buscas[0]
    assert (b.item_id, b.output_index, b.status, b.action_type) == ("ws_1", 0, "completed", "search")
    assert b.eventos == ["in_progress", "searching", "completed"]
    assert b.queries == ["psg renda per capita"] and len(b.sources) == 3
    assert [(c.annotation_index, c.url) for c in m.citacoes] == [(0, PB), (1, MG)]
    assert m.uso["output_tokens_details"]["reasoning_tokens"] == 47


def test_canonicaliza_so_rastreio_e_preserva_query_funcional():
    url = ("https://x.senac.br/curso?id=7&utm_source=openai&utm_medium=a&utm_campaign=b&"
           "utm_term=c&utm_content=d&gclid=1&fbclid=2&msclkid=3&uf=PR")
    assert pp.canonica(url) == "https://x.senac.br/curso?id=7&uf=PR"
    assert pp.canonica("https://x.senac.br/p") == "https://x.senac.br/p"


def test_sources_separadas_das_citacoes_e_source_sem_citacao_nao_vira_fato():
    resp, _, _ = _rodar(_grounded(), _estruturado([FATO_OK]))
    assert resp.defeito == ""
    meta = resp.metadados[0]
    fontes = [s["url"] for b in meta["web_search_calls"] for s in b["sources"]]
    assert NAO_CITADA in fontes                               # consultada...
    assert NAO_CITADA not in resp.citacoes                    # ...não citada
    assert all(f["fonte"] != NAO_CITADA for f in resp.dados["fatos"])
    assert [e["id"] for e in meta["evidencias"]] == ["e1", "e2"]
    assert meta["evidencias"][0]["urls"] == [PB]              # trecho -> citação sobreposta


def test_titulo_nulo_e_aceito():
    m = pp.montar_stream(_grounded())
    assert m.buscas[0].sources[0]["titulo"] is None and m.citacoes[1].titulo is None
    evs, defeitos = pp.evidencias(m)
    assert not defeitos and evs[1].urls == [MG]


def test_citacao_com_posicao_fora_do_texto_reprova():
    texto, cits = _texto_e_citacoes()
    ruim = [cits[0], (cits[1][0], None, len(texto) - 5, len(texto) + 40)]
    resp, transporte, _ = _rodar(_sse(texto, ruim))
    assert "posição fora do texto" in resp.defeito
    assert len(transporte.corpos) == 1                       # não estrutura


def test_afirmacao_fora_do_trecho_citado_e_valor_ausente_sao_rejeitados():
    fora = dict(FATO_OK, afirmacao="Inscrições abertas para cursos técnicos em março")
    sem_valor = dict(FATO_OK, valor="3")
    outra = dict(FATO_OK, evidencia_id="e2")                 # e2 não fala de 2 salários
    resp, _, _ = _rodar(_grounded(), _estruturado([fora, sem_valor, outra]))
    motivos = [r["motivo"] for r in resp.metadados[1]["rejeitados"]]
    assert "afirmação sem lastro suficiente no trecho citado" in motivos
    assert "valor '3' não aparece no trecho citado" in motivos
    assert "valor '2' não aparece no trecho citado" in motivos
    assert resp.dados["fatos"] == []


def test_estruturador_nao_cria_url_nem_fato():
    schema = pp.schema_da_estruturacao(["numero"])
    assert "fonte" not in schema["properties"]["fatos"]["items"]["properties"]
    inventado = dict(FATO_OK, evidencia_id="e9")
    com_url = dict(FATO_OK, fonte="https://golpe.example.com")
    resp, transporte, _ = _rodar(_grounded(), _estruturado([inventado, com_url]))
    assert resp.metadados[1]["rejeitados"][0]["motivo"] == "evidencia_id inexistente"
    assert [f["fonte"] for f in resp.dados["fatos"]] == [PB]  # a URL é a da citação
    corpo = transporte.corpos[1]
    assert "tools" not in corpo and corpo["text"]["format"]["strict"] is True


def test_vigencia_que_o_trecho_nao_traz_e_descartada():
    resp, _, _ = _rodar(_grounded(), _estruturado([dict(FATO_OK, vigente_desde="2019-01-01")]))
    assert resp.dados["fatos"][0]["vigente_desde"] == ""


def test_pagina_citada_que_nao_confirma_o_valor_nao_verifica():
    resp, _, _ = _rodar(_grounded(), _estruturado([FATO_OK]),
                        paginas_lidas={PB: ("página institucional sem a regra", "")})
    assert resp.dados["fatos"][0]["motivo_nao_verificado"].startswith("página citada não confirma")
    fato = fatos_da_resposta(resp)[0]
    assert fato.motivo_do_status.startswith("página citada não confirma")


@pytest.mark.parametrize("kw, motivo", [
    ({"modelo": "gpt-6-sol"}, "modelo trocado pelo servidor"),
    ({"busca": False}, "nenhum web_search_call"),
    ({"status_busca": "failed"}, "web_search_call sem status completed"),
    ({"completed": False}, "sem response.completed"),
])
def test_modelo_trocado_busca_ausente_ou_incompleta_reprova(kw, motivo):
    texto, cits = _texto_e_citacoes()
    resp, transporte, _ = _rodar(_sse(texto, cits, **kw))
    assert motivo in resp.defeito and len(transporte.corpos) == 1


def test_resposta_sem_citacao_reprova():
    resp, _, _ = _rodar(_sse(FRASE1, []))
    assert "sem url_citation" in resp.defeito


def test_recusa_do_servidor_nao_e_repetida():
    resp, transporte, _ = _rodar(RespostaHTTP(400, [], {"error": {
        "code": "unsupported_tool", "message": "web_search indisponível"}}))
    assert resp.defeito.startswith("Responses API recusou (400 unsupported_tool)")
    assert len(transporte.corpos) == 1


def test_verificacao_ao_vivo_continua_obrigatoria():
    resp, _, _ = _rodar(_grounded(), _estruturado([FATO_OK]))
    fatos = fatos_da_resposta(resp)
    assert fatos[0].motivo_do_status == ""

    class _Fora:
        def verify_url(self, url):
            return False

        def motivo(self, url):
            return "HTTP 503"
    verificar_ao_vivo(fatos, _Fora(), date(2026, 10, 7))
    assert fatos[0].status == "unverified" and "não respondeu" in fatos[0].motivo_do_status


def test_provider_dedicado_funciona_com_chatgpt_plan_e_nao_vaza_token():
    resp, transporte, llm = _rodar(_grounded(), _estruturado([FATO_OK]))
    assert resp.defeito == "" and resp.auth_mode == "chatgpt_plan"
    assert resp.custo_informado is False and resp.modelo_servido == "gpt-6.1-sol"
    assert llm.contadas == ["chatgpt/gpt-6.1-sol"] * 2       # entram no teto de chamadas
    busca = transporte.corpos[0]
    assert busca["tools"][0]["type"] == "web_search" and busca["tool_choice"] == "required"
    assert busca["include"] == ["web_search_call.action.sources"] and busca["store"] is False
    assert transporte.cabecalhos[0]["Authorization"] == f"Bearer {SEGREDO}"
    recibo = json.dumps(resp.metadados, ensure_ascii=False, default=str)
    assert SEGREDO not in recibo and "Bearer" not in recibo and "Authorization" not in recibo
    assert resp.metadados[0]["custo_retornado_pelo_servidor"] is None


def test_cliente_generico_do_plano_continua_recusando_web_search():
    cliente = OpenAIResponsesClient(_Credencial(), enviar=_Transporte())
    with pytest.raises(NaoSuportadoNoPlano):
        cliente.complete("chatgpt/gpt-6.1-sol", [], [{"role": "user", "content": "x"}], 0,
                         web_search=True)


def test_despacho_do_dossie_por_modelo():
    from funnelforge.adapters import research_perplexity as rp
    chamado = {}
    import funnelforge.adapters.pesquisa_plano as mod
    original = mod.pesquisar_dossie_plano
    try:
        mod.pesquisar_dossie_plano = lambda *a, **k: chamado.setdefault("plano", True)
        rp.pesquisar_funil(None, CFG, "x", [], None)
    finally:
        mod.pesquisar_dossie_plano = original
    assert chamado == {"plano": True}


@pytest.mark.parametrize("valor, texto, esperado", [
    ("até 2", "renda per capita de até 02 (dois) salários mínimos", True),   # canário real
    ("2", "não ultrapasse dois salários mínimos", True),
    ("1,5", "limite de 1.5 salário", True),
    ("R$ 3.242,00", "equivale a R$ 3.242,00 em 2026", True),
    ("até 3", "até 02 (dois) salários mínimos", False),
    ("20", "renda de 2 salários", False),
])
def test_valor_comparado_pelo_numero_e_nao_pela_string(valor, texto, esperado):
    assert pp._valor_presente(valor, texto) is esperado


def test_estruturacao_pede_data_convertida_para_iso():
    prompt = pp._prompt_da_estruturacao("t", [], [], PAGINAS)
    assert "'14/01/2026' -> '2026-01-14'" in prompt and "mês/ano ou sem data -> vazio" in prompt
