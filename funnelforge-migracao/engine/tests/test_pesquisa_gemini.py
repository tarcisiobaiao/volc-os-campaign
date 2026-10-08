"""Pesquisa NATIVA do dossiê (google-genai): telemetria, schema e o desvio
controlado de RECITATION. O cliente é um dublê que devolve objetos REAIS do
SDK (`types.GenerateContentResponse`), então nome de campo errado quebra aqui."""
from __future__ import annotations

import json

import pytest
from google.genai import types

from funnelforge.adapters import pesquisa_gemini as pg
from funnelforge.adapters.research_perplexity import _prompt_do_funil
from funnelforge.config.settings import StepConfig
from funnelforge.domain.models import RunState
from funnelforge.pipeline import pipeline as pl
from tests.cenario_editorial import congelar_data, rodar_cenario
from tests.test_dossie_factual import (
    FATOS_COMPLETOS,
    PSG,
    _arq_com_requisito_de_renda,
    _ligar_pesquisa,
    _Pesquisa,
    _settings_com_dossie,
)

CFG = StepConfig(model="gemini/gemini-3.8-flash", web_search=True, temperature=0.2)
FATO = {"afirmacao": "Renda per capita de até 2 salários mínimos", "tipo": "numero",
        "valor": "2", "unidade": "salários mínimos", "fonte": PSG,
        "vigente_desde": "2008-07-21", "evidencia_resumida": "O PSG usa esse limite de renda.",
        "paginas": ["renda"], "requisitos": ["renda.limite_per_capita"]}


def _resposta(texto="", fim="STOP", mensagem="", consultas=("senac psg renda",),
              fontes=(PSG,), apoios=1, bloqueio=None):
    gm = types.GroundingMetadata(
        web_search_queries=list(consultas),
        grounding_chunks=[types.GroundingChunk(web=types.GroundingChunkWeb(uri=u, title="senac.br"))
                          for u in fontes],
        grounding_supports=[types.GroundingSupport() for _ in range(apoios)])
    return types.GenerateContentResponse(
        candidates=[types.Candidate(
            finish_reason=getattr(types.FinishReason, fim), finish_message=mensagem or None,
            content=types.Content(role="model", parts=[types.Part(text=texto)] if texto else []),
            grounding_metadata=gm,
            safety_ratings=[types.SafetyRating(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                                               probability=types.HarmProbability.NEGLIGIBLE)])],
        prompt_feedback=(types.GenerateContentResponsePromptFeedback(
            block_reason=bloqueio, block_reason_message="bloqueado") if bloqueio else None),
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=1000, candidates_token_count=200, thoughts_token_count=300,
            tool_use_prompt_token_count=50, total_token_count=1550),
        model_version="gemini-3.8-flash", response_id="r-1")


class _Cliente:
    def __init__(self, *respostas):
        self.respostas, self.pedidos = list(respostas), []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.pedidos.append({"model": model, "prompt": contents,
                             "busca": bool(config.tools), "json": config.response_mime_type,
                             "schema": config.response_json_schema is not None})
        return self.respostas.pop(0)


def _pesquisar(*respostas):
    cliente = _Cliente(*respostas)
    return pg.pesquisar_dossie_nativo(CFG, "Senac", [{"duvida_id": "renda"}], None,
                                      cliente=cliente), cliente


def test_prompt_nao_exige_reproducao_literal():
    for estruturado in (True, False):
        texto = _prompt_do_funil("Senac", [], None, estruturado=estruturado)
        assert "copiad" not in texto and "parafrase" not in texto.lower()
        assert "Não reproduza trechos literais extensos" in texto
        assert "groundingMetadata e pela URL verificada" in texto


def test_structured_output_e_grounding_capturados_no_contrato_nativo():
    resp, cliente = _pesquisar(_resposta(json.dumps({"fatos": [FATO]})))
    assert cliente.pedidos == [{"model": "gemini-3.8-flash", "prompt": cliente.pedidos[0]["prompt"],
                                "busca": True, "json": "application/json", "schema": True}]
    assert resp.defeito == "" and resp.dados["fatos"][0]["valor"] == "2"
    assert resp.citacoes == [PSG] and resp.modelo_servido == "gemini-3.8-flash"
    meta = resp.metadados[0]
    assert meta["web_search_queries"] == ["senac psg renda"]
    assert (meta["grounding_chunks"], meta["grounding_supports"]) == (1, 1)
    assert meta["safety_ratings"][0]["probabilidade"] == "NEGLIGIBLE"
    assert meta["tokens"] == {"entrada": 1000, "saida": 200, "raciocinio": 300,
                              "ferramenta": 50, "total": 1550}
    assert "_texto" not in meta and resp.consultas_de_busca == 1
    assert meta["grounding_metadata_presente"] is True
    assert meta["grounding_metadata_campos"] == [
        "grounding_chunks", "grounding_supports", "web_search_queries"]
    # tokens a preço de tabela: (1000+50)×0,75/M + (200+300)×3,75/M
    assert resp.custo_usd == pytest.approx(1050 * 0.75e-6 + 500 * 3.75e-6, abs=1e-6)


def test_finish_reason_e_finish_message_sao_preservados():
    resp, _ = _pesquisar(_resposta("", fim="MAX_TOKENS", mensagem="limite de saída"))
    assert resp.metadados[0]["finish_reason"] == "MAX_TOKENS"
    assert resp.metadados[0]["finish_message"] == "limite de saída"
    assert resp.defeito == "finish_reason=MAX_TOKENS limite de saída"


def test_prompt_bloqueado_e_registrado():
    resp, _ = _pesquisar(_resposta("", bloqueio=types.BlockedReason.SAFETY))
    assert resp.metadados[0]["block_reason"] == "SAFETY"
    assert resp.defeito.startswith("prompt bloqueado: SAFETY")


@pytest.mark.parametrize("kw, motivo", [
    ({"consultas": ()}, "0 webSearchQueries"),
    ({"fontes": ()}, "sem groundingChunks"),
])
def test_sem_busca_ou_sem_citacao_reprova(kw, motivo):
    resp, _ = _pesquisar(_resposta(json.dumps({"fatos": [FATO]}), **kw))
    assert motivo in resp.defeito and resp.dados == {"fatos": []}


def test_saida_fora_do_schema_reprova():
    resp, _ = _pesquisar(_resposta('{"fatos": [{"afirmacao": "sem fonte"}]}'))
    assert resp.defeito.startswith("structured output fora do schema")
    longo = dict(FATO, evidencia_resumida="x" * 400)       # evidência literal extensa
    resp, _ = _pesquisar(_resposta(json.dumps({"fatos": [longo]})))
    assert resp.defeito.startswith("structured output fora do schema")


def test_recitation_com_busca_desvia_uma_vez_sem_repetir_o_prompt():
    prosa = "O PSG atende renda per capita de até 2 salários mínimos (senac.br/psg)."
    resp, cliente = _pesquisar(
        _resposta("", fim="RECITATION"),
        _resposta(prosa),
        _resposta(json.dumps({"fatos": [FATO]}), consultas=(), fontes=()))
    prompts = [p["prompt"] for p in cliente.pedidos]
    assert len(prompts) == 3 and len(set(prompts)) == 3              # nenhum repetido
    assert [(p["busca"], p["schema"]) for p in cliente.pedidos] == [
        (True, True), (True, False), (False, True)]
    assert prosa in prompts[2] and PSG in prompts[2]                 # só as fontes da prosa
    assert [m["chamada"] for m in resp.metadados] == [
        "estruturada_com_busca", "prosa_com_busca:recitation", "estruturacao_sem_busca"]
    assert resp.defeito == "" and resp.citacoes == [PSG]


def test_recitation_sem_busca_nao_desvia():
    resp, cliente = _pesquisar(_resposta("", fim="RECITATION", consultas=()))
    assert len(cliente.pedidos) == 1 and resp.defeito.startswith("finish_reason=RECITATION")


def test_somente_dossie_nao_chama_redacao_e_a_retomada_reusa_o_dossie(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    _ligar_pesquisa(monkeypatch, _Pesquisa(FATOS_COMPLETOS))
    settings = _settings_com_dossie(tmp_path)
    from tests.cenario_editorial import montar_deps
    from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
    llm, deps = montar_deps(tmp_path, settings, lambda m, msgs: pytest.fail("chamou LLM"))
    monkeypatch.setattr(pl.st, "declarar_engajamento", lambda state, deps: None)
    state = pl.run_pipeline(None, deps, plan=plano_do_funnel_architecture(
        _arq_com_requisito_de_renda()), timestamp="20261007-120000", ate_o_dossie=True)
    assert llm.calls == [] and state.dossie_sha256
    assert all(state.step_status[f"dossie_p{p.page_number}"].status.value == "OK"
               for p in state.plan.pages)
    passos = {k.split("_p")[0] for k in state.step_status}
    assert not passos & {"briefing", "write", "seo", "widget", "revisor", "image", "build"}
    pasta = deps.runner.runs_dir / state.run_id
    assert json.loads((pasta / "pesquisa_dossie.json").read_text())[0]["fatos"] == len(FATOS_COMPLETOS)

    _ligar_pesquisa(monkeypatch, lambda *a: pytest.fail("a retomada pesquisou de novo"))
    from tests.cenario_editorial import responder_v1
    llm.__init__(responses=responder_v1)
    final = pl.run_pipeline(None, deps, resume_state=RunState.from_json(state.to_json()))
    assert final.dossie_sha256 == state.dossie_sha256 and final.drafts


def test_redirect_do_grounding_so_no_texto_nao_vira_fonte():
    """O microprobe real de 07/10: STOP, JSON válido, `fonte` = URL de redirect
    do grounding escrita pelo modelo, e groundingMetadata sem nenhum chunk."""
    redirect = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZ"
    fato = dict(FATO, fonte=redirect)
    resp, _ = _pesquisar(_resposta(json.dumps({"fatos": [fato]}), consultas=(), fontes=(),
                                   apoios=0))
    meta = resp.metadados[0]
    assert meta["redirect_do_grounding_no_texto"] is True
    assert meta["grounding_metadata_campos"] == []
    assert "0 webSearchQueries" in resp.defeito and resp.citacoes == []
