"""S2 · item 4 (30/09/2026): a PROMESSA da LP chega ao juiz de sentido da copy Search.

Até aqui o prompt do juiz dizia "a promessa da página de destino NÃO foi
entregue a este juiz". Ele julgava congruência anúncio ↔ destino só pela URL e
pelos fatos — e a Diretriz 1 do operador exige que o rótulo corresponda ao que
o destino ENTREGA, verificado e não presumido.

A cadeia coberta: `state.json` (rascunho `lp_json` da LP) → ponte
(`_promessa_da_lp` → `Origem.promessa_da_lp`) → `encomendar.escrever` → prompt
do juiz. Ausência é dita com o motivo. Sem rede, sem LLM (dublês).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from volc_ads import pautador_ponte as ponte
from volc_ads.copy import encomendar as em
from volc_ads.copy import juiz_semantico as js
from volc_ads.copy.mock import ClienteMock, RoteiroEsgotado
from volc_ads.copy.testes_localizadores import _com_palavras_antes_proibidas

LP = {"hero_title": "Cursos gratuitos do Senac: veja como achar a turma no seu estado",
      "hero_subtitle": "O <b>Senac</b> publica as vagas por Departamento Regional",
      "cta_texts": ["Ver como achar a turma no seu estado", "Descobrir se tenho direito", " "],
      "article_title": "x", "intro": "x", "transition": "x", "sections": [], "faq": []}


def _estado(conteudo) -> dict:
    return {"drafts": {"1": {"content": conteudo, "format": "lp_json"}}}


def test_promessa_presente_vem_dos_slots_da_lp():
    p = ponte._promessa_da_lp(_estado(json.dumps(LP)), 1)
    assert p["estado"] == "presente"
    assert p["titulo"] == LP["hero_title"]
    assert p["subtitulo"] == "O  Senac  publica as vagas por Departamento Regional"
    assert p["ctas"] == ["Ver como achar a turma no seu estado", "Descobrir se tenho direito"]
    assert p["fonte"] == "state.json drafts[1] (lp_json)"


def test_ausencia_e_dita_com_o_motivo_nunca_preenchida():
    casos = {
        "state": ponte._promessa_da_lp(None, 1),
        "pagina": ponte._promessa_da_lp(_estado("{}"), None),
        "rascunho": ponte._promessa_da_lp({"drafts": {}}, 1),
        "gutenberg": ponte._promessa_da_lp(_estado("<!-- wp:paragraph --><p>x</p>"), 1),
        "vazio": ponte._promessa_da_lp(_estado(json.dumps({"hero_title": "", "cta_texts": []})), 1),
    }
    for nome, p in casos.items():
        assert p["estado"] == "ausente", nome
        assert p["motivo_ausencia"], nome
        assert set(p) == {"estado", "motivo_ausencia"}, nome


def test_bloco_do_prompt_presente_ausente_e_nao_entregue():
    presente = js.bloco_promessa_da_lp(ponte._promessa_da_lp(_estado(json.dumps(LP)), 1))
    assert "título: 'Cursos gratuitos do Senac" in presente
    assert "CTA[1]: 'Ver como achar a turma no seu estado'" in presente
    ausente = js.bloco_promessa_da_lp({"estado": "ausente", "motivo_ausencia": "sem state"})
    assert "AUSENTE (sem state)" in ausente
    assert js.bloco_promessa_da_lp(None) == ""
    prompt = js.montar_prompt({"headlines": ["x"]}, fatos_texto="", nicho="n", regras=[])
    assert "NÃO ENTREGUE a este juiz" in prompt


def _cockpit(promessa):
    origem = SimpleNamespace(
        nicho="Senac", url_final="https://exemplo.com.br/r/senac/", pais="BR", idioma="pt",
        vertical="informativo", fatos=(), promessa_da_lp=promessa)
    return SimpleNamespace(origem=origem)


def _prompt_do_juiz(cockpit) -> str:
    c = ClienteMock([_com_palavras_antes_proibidas(), '{"observacoes": []}'])
    try:
        em.escrever(cockpit, keywords=["cursos senac gratuitos"], cliente=c)
    except RoteiroEsgotado:
        pass  # só a primeira rodada interessa
    juizes = [u for s, u in c.chamadas if s == js.SISTEMA]
    assert juizes
    return juizes[0]


def test_escrever_entrega_a_promessa_da_lp_ao_juiz():
    """A porta que o backend chama (`/trafego/copy`): o juiz de verdade recebe
    o título, o subtítulo e os CTAs da LP junto do destino."""
    u = _prompt_do_juiz(_cockpit(ponte._promessa_da_lp(_estado(json.dumps(LP)), 1)))
    assert "A PROMESSA DA PÁGINA DE DESTINO" in u
    assert LP["hero_title"] in u
    assert "Ver como achar a turma no seu estado" in u
    assert "NÃO ENTREGUE" not in u


def test_escrever_sem_promessa_diz_a_ausencia_ao_juiz():
    u = _prompt_do_juiz(_cockpit({"estado": "ausente",
                                  "motivo_ausencia": "o state.json do run não está no disco"}))
    assert "AUSENTE (o state.json do run não está no disco)" in u
    u = _prompt_do_juiz(_cockpit(None))
    assert "NÃO ENTREGUE a este juiz" in u


def test_cockpit_leva_a_promessa_da_lp_na_origem():
    """A ponte monta a `Origem` com a promessa da página da LP publicada."""
    from volc_ads.testes_pautador_ponte import _linhas

    linhas = _linhas()
    pagina = next(p["page_number"] for p in linhas.run["paginas_publicadas"] if p["role"] == "LP")
    estado = dict(linhas.estado_do_run or {})
    estado["drafts"] = {**(estado.get("drafts") or {}), str(pagina): {"content": json.dumps(LP)}}
    import dataclasses
    c = ponte.montar_cockpit(dataclasses.replace(linhas, estado_do_run=estado))
    assert c.origem.promessa_da_lp["estado"] == "presente"
    assert c.origem.promessa_da_lp["titulo"] == LP["hero_title"]
