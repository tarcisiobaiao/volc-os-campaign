"""`funnelforge revisar`: o revisor sobre conteúdo JÁ PUBLICADO, exportado em
arquivo (B5). Gera `revisao.json` e `patches.json`. Sem WordPress, sem publicar:
os patches viram lote para aprovação humana.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import funnelforge.cli as cli
from funnelforge.adapters import wordpress
from funnelforge.pipeline import revisao_avulsa
from tests.cenario_editorial import DataCongelada, texto_da_mensagem
from tests.fakes import FakeLLM

HTML = """<!-- wp:paragraph -->
<p>O programa oferece vagas gratuitas para quem cumpre o criterio de renda do edital.</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>Todo mundo consegue a vaga se fizer a inscricao cedo.</p>
<!-- /wp:paragraph -->

<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button -->
<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="https://site.exemplo.com.br/rec/requisitos-p1">Garantir minha vaga</a></div>
<!-- /wp:button --></div><!-- /wp:buttons -->
"""

BRIEFING = {"versao": "briefing-v1",
            "intencao": {"pergunta_do_leitor": {"texto": "Quem pode fazer o curso gratuito?"}},
            "limites": [{"texto": "não prometer vaga", "base": "identidade"}]}
CONTEXTO = {
    "pagina": {"numero": 3, "slug": "cursos-gratuitos-p1", "papel": "SOLUTION",
               "h1": "Quem pode fazer curso gratuito"},
    "fatos": [{"id": "f1", "tipo": "condicao",
               "texto": "A gratuidade exige renda familiar dentro do criterio do edital.",
               "fonte": "https://www.exemplo.org.br/gratuidade", "citavel": True}],
    "destinos": [{"id": "d1", "tipo": "funnel", "destino": "requisitos-p1",
                  "entrega": "lista os requisitos do edital"}],
    "seotitle": "Curso gratuito: quem pode fazer",
    "metadescription": "Veja quem pode fazer o curso gratuito e o que o edital exige.",
}
PROMESSA = "Todo mundo consegue a vaga se fizer a inscricao cedo."


def _revisor(model, messages):
    prompt = texto_da_mensagem(messages[-1])
    assert "REVISOR EDITORIAL CONTEXTUAL" in prompt
    if "RODADA 2" in prompt:
        return json.dumps({"versao": "revisao-v1", "decisao": "aprovado", "achados": [],
                           "patches": [], "afirmacoes_nao_verificadas": []})
    return json.dumps({
        "versao": "revisao-v1", "decisao": "ajustar",
        "achados": [
            {"id": "a1", "severidade": "bloqueante", "categoria": "erro_factual",
             "campo": "corpo", "trecho": PROMESSA, "motivo": "a vaga depende do edital",
             "evidencia": {"tipo": "fato", "ref": "f1"}},
            {"id": "a2", "severidade": "bloqueante", "categoria": "congruencia_destino",
             "campo": "corpo", "trecho": "Garantir minha vaga",
             "motivo": "o destino lista requisitos; não garante vaga",
             "evidencia": {"tipo": "destino", "ref": "d1"}}],
        "patches": [
            {"achado": "a1", "campo": "corpo", "antes": PROMESSA,
             "depois": "A vaga depende do criterio de renda e das vagas do edital."},
            {"achado": "a2", "campo": "corpo", "antes": "Garantir minha vaga",
             "depois": "Ver os requisitos do edital"}],
        "afirmacoes_nao_verificadas": [],
        "notas": {"compliance": 8, "cta_discipline": 7, "useful_delivery": 8,
                  "destination_relevance": 8}}, ensure_ascii=False)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        "run: {max_retries: 0}\n"
        "site: {domain: 'https://site.exemplo.com.br'}\n"
        "steps:\n"
        "  revisor: {model: gpt-4.1, fallbacks: [], temperature: 0.0, validators: []}\n",
        encoding="utf-8")
    llm = FakeLLM(responses=_revisor)
    monkeypatch.setattr(cli, "_cliente_do_revisor", lambda: llm)
    monkeypatch.setattr(revisao_avulsa, "date", DataCongelada)   # pacote dentro da validade

    def _proibido(*a, **k):
        raise AssertionError("o comando revisar nunca fala com o WordPress")

    monkeypatch.setattr(wordpress, "WordPressPublisher", _proibido)
    return tmp_path, llm


def _invocar(tmp_path: Path, conteudo: Path, *extra: str):
    (tmp_path / "briefing.json").write_text(json.dumps(BRIEFING, ensure_ascii=False))
    return CliRunner().invoke(cli.app, [
        "revisar", str(conteudo), "--briefing", str(tmp_path / "briefing.json"),
        "--config", str(tmp_path / "config.yaml"), "--env", str(tmp_path / ".env"), *extra])


def test_revisar_html_publicado_gera_revisao_e_patches_sem_publicar(ambiente):
    tmp_path, llm = ambiente
    conteudo = tmp_path / "post-2309.html"
    conteudo.write_text(HTML, encoding="utf-8")
    (tmp_path / "contexto.json").write_text(json.dumps(CONTEXTO, ensure_ascii=False))
    saida = tmp_path / "saida"
    res = _invocar(tmp_path, conteudo, "--contexto", str(tmp_path / "contexto.json"),
                   "--saida", str(saida))
    assert res.exit_code == 0, res.output
    revisao = json.loads((saida / "revisao.json").read_text())
    patches = json.loads((saida / "patches.json").read_text())
    assert revisao["versao"] == "revisao-v1" and revisao["decisao"] == "aprovado"
    assert {p["achado"] for p in patches["patches"]} == {"a1", "a2"}
    assert patches["sha256_entrada"] != patches["sha256_revisado"]
    assert "aprovação humana" in patches["aviso"]
    revisado = (saida / "conteudo_revisado.html").read_text()
    assert "Ver os requisitos do edital" in revisado and PROMESSA not in revisado
    assert 'href="https://site.exemplo.com.br/rec/requisitos-p1"' in revisado
    assert conteudo.read_text() == HTML                       # o original não muda
    primeiro = texto_da_mensagem(llm.calls[0]["messages"][-1])
    assert "A gratuidade exige renda familiar" in primeiro
    assert "lista os requisitos do edital" in primeiro
    assert "Curso gratuito: quem pode fazer" in primeiro


def test_revisar_lp_em_json_sem_contexto_declara_o_que_falta(ambiente):
    tmp_path, llm = ambiente
    lp = {"hero_title": "Curso gratuito", "hero_subtitle": "Quem pode",
          "article_title": "Quem pode fazer", "intro": f"<p>{PROMESSA}</p>",
          "sections": [{"title": "t", "body": "<p>b</p>"}] * 4,
          "faq": [{"q": "q?", "a": "a"}], "transition": "<p>t</p>",
          "cta_texts": ["Garantir minha vaga", "Ver regras", "Ver passo a passo"]}
    conteudo = tmp_path / "lp.json"
    conteudo.write_text(json.dumps(lp, ensure_ascii=False), encoding="utf-8")
    res = _invocar(tmp_path, conteudo)
    assert res.exit_code == 0, res.output
    saida = tmp_path / "lp_revisao"
    revisao = json.loads((saida / "revisao.json").read_text())
    assert revisao["rodadas"][0]["decisao_do_modelo"] == "ajustar"
    primeiro = texto_da_mensagem(llm.calls[0]["messages"][-1])
    assert "NÃO COLETADOS" in primeiro or "ausente" in primeiro
    # sem contexto, "f1" e "d1" não existem: nenhum patch é aplicado às cegas
    patches = json.loads((saida / "patches.json").read_text())
    assert patches["patches"] == []
    assert {r["motivo"] for r in patches["recusados"]} <= {"achado_nao_patchavel",
                                                           "campo_inexistente"}
