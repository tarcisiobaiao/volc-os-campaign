"""Rodada de copy, navegação e composição (10/10): navegação do topo nas
internas, hubs que antecipam a resposta dos destinos, sniper com o passo
principal marcado e leitura rápida no redator e no revisor."""
import re

from funnelforge.pipeline.dossie import projecao_para_o_prompt
from funnelforge.pipeline.inteligencia import prompt_do_pacote
from funnelforge.pipeline.revisao import PADROES_DE_ESCRITA
from funnelforge.pipeline.steps import CLASSE_DA_NAVEGACAO, navegacao_do_topo
from funnelforge.pipeline.validators.checks import (_slots_do_ad_inserter, composicao_editorial,
                                                    run_validators)
from funnelforge.prompts import render
from tests.test_fechamento_entregas_e_prompts import _com_pacotes


def _p(texto):
    return f"<!-- wp:paragraph -->\n<p>{texto}</p>\n<!-- /wp:paragraph -->"


BOTAO_DO_REDATOR = ('<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button -->\n'
                    '<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" '
                    'href="https://x.com/rec/a">Antigo</a></div>\n<!-- /wp:button --></div>'
                    '<!-- /wp:buttons -->')
TITULO = '<!-- wp:heading -->\n<h2 class="wp-block-heading">Quem pode receber</h2>\n<!-- /wp:heading -->'
ROTAS = [{"kind": "funnel", "href": "https://x.com/rec/a", "anchor": "Quem pode receber"},
         {"kind": "funnel", "href": "https://x.com/rec/b", "anchor": "O pagamento não caiu"},
         {"kind": "external_official", "href": "https://gov.br/x", "anchor": "gov.br: agenda >>>"}]


def _rascunho():
    return "\n\n".join([_p("Resposta curta."), BOTAO_DO_REDATOR, _p("Dois."), _p("Três."),
                        TITULO, _p("Quatro.")])


def test_navegacao_do_topo_depois_da_orientacao_com_o_principal_em_destaque():
    novo, caminhos = navegacao_do_topo(_rascunho(), ROTAS, principal="https://x.com/rec/b")

    assert [c["rotulo"] for c in caminhos] == ["O pagamento não caiu", "Quem pode receber"]
    assert "gov.br" not in novo and "Antigo" not in novo        # só funil; botão velho saiu
    blocos = re.findall(r"<!--\s*wp:(paragraph|buttons|heading)", novo)
    assert blocos[:3] == ["paragraph", "buttons", "paragraph"]
    nav = re.search(r'<div class="wp-block-buttons ' + CLASSE_DA_NAVEGACAO + r'">([\s\S]*?)</div>\n'
                    r'<!-- /wp:buttons -->', novo).group(1)
    principal, alternativa = re.findall(r"<a [^>]*>", nav)
    assert "has-background" not in principal and "rec/b" in principal
    assert "background-color:#e6f1f4" in alternativa and "is-style-outline" not in nav
    assert "<p" not in nav                                       # Ad Inserter conta <p>
    assert navegacao_do_topo(novo, ROTAS, principal="https://x.com/rec/b")[0] == novo


def test_navegacao_respeita_slots_blocos_e_links():
    novo, _ = navegacao_do_topo(_rascunho(), ROTAS, principal="https://x.com/rec/b")
    ctx = {"editorial_v2": True, "contextual_editorial": True, "domain": "https://x.com",
           "resolved_internal_routes": ["https://x.com/rec/a", "https://x.com/rec/b"],
           "ad_paragraph_anchors": [1, 3]}
    assert _slots_do_ad_inserter(novo, ctx) == []
    assert run_validators(["gutenberg_blocks", "raw_html_contract", "contextual_links"], novo, ctx) == []
    assert composicao_editorial(novo, ctx) == []


def test_sem_rota_interna_nada_muda():
    so_oficial = [r for r in ROTAS if r["kind"] != "funnel"]
    assert navegacao_do_topo(_rascunho(), so_oficial) == (_rascunho(), [])


def test_hub_recebe_os_fatos_dos_destinos_e_a_solucao_nao():
    f1, f2, f3 = "f_" + "1" * 12, "f_" + "2" * 12, "f_" + "3" * 12
    dossie = {"fatos": [{"fact_id": f, "afirmacao": f"afirmação {f}", "tipo": "regra",
                         "source_url": "https://g.br"} for f in (f1, f2, f3)],
              "paginas": [
                  {"page_number": 1, "slug": "lp", "role": "LP", "fatos_verificados": [f1],
                   "cta": {"destinos": [{"slug": "sol"}]}},
                  {"page_number": 2, "slug": "sol", "role": "SOLUTION", "fatos_verificados": [f2],
                   "cta": {"destinos": [{"slug": "fim"}]}},
                  {"page_number": 3, "slug": "fim", "role": "SOLUTION", "fatos_verificados": [f3],
                   "cta": {"destinos": []}}]}
    lp = projecao_para_o_prompt(dossie, 1)["fatos"]
    assert [(f["id"], f.get("do_destino")) for f in lp] == [(f1, None), (f2, "sol")]
    assert [f["id"] for f in projecao_para_o_prompt(dossie, 2)["fatos"]] == [f2]


def test_sniper_marca_o_passo_principal_de_cada_pagina(tmp_path):
    from funnelforge.pipeline.ctas import _arestas
    state, deps = _com_pacotes(tmp_path)
    por_numero = {p.page_number: p for p in state.plan.pages}
    funil = [a for a in _arestas(state, deps, {}, {})[0] if a["tipo"] == "funnel"]
    assert any(b["principal"] for b in funil)
    for b in funil:
        origem, alvo = por_numero[b["origem"]], por_numero[b["destino_pagina"]]
        assert b["principal"] == (alvo.jornada.duvida_id == origem.jornada.proxima_duvida)


def test_redator_das_internas_sabe_da_navegacao_e_da_leitura_rapida(tmp_path):
    state, _ = _com_pacotes(tmp_path)
    interna = next(p for p in state.plan.pages if p.page_type != "LANDING PAGE"
                   and any(l["kind"] == "funnel" for l in state.pacotes[p.page_number]["links"]))
    prompt = prompt_do_pacote(state, interna)
    assert "Navegação do topo" in prompt and "<leitura_rapida>" in prompt
    lp = next(p for p in state.plan.pages if p.page_type == "LANDING PAGE")
    assert "Navegação do topo" not in prompt_do_pacote(state, lp)


def test_revisor_corrige_titulo_sem_resposta_e_termo_sem_explicacao():
    assert {"titulo_sem_resposta", "termo_sem_explicacao"} <= set(PADROES_DE_ESCRITA)
    from importlib import resources
    fonte = resources.files("funnelforge.prompts").joinpath("revisor.jinja").read_text("utf-8")
    assert "titulo_sem_resposta" in fonte and "termo_sem_explicacao" in fonte
    assert "sigla entra explicada" in render("escrita_natural")


def test_negrito_aberto_num_paragrafo_fecha_no_proprio_paragrafo():
    from funnelforge.pipeline.steps import fechar_inline_por_paragrafo
    bruto = (_p("<strong>Não.") + "\n\n" + _p("As modalidades atingem parcelas diferentes.</strong>")
             + "\n\n" + _p("Texto <em>certo</em>."))
    novo, ajustes = fechar_inline_por_paragrafo(bruto)
    assert ajustes == 2
    assert "<p><strong>Não.</strong></p>" in novo
    assert "<p>As modalidades atingem parcelas diferentes.</p>" in novo
    assert "<p>Texto <em>certo</em>.</p>" in novo
    assert fechar_inline_por_paragrafo(novo) == (novo, 0)


def test_paragrafo_que_so_repete_o_h1_sai_sem_quebrar_os_slots():
    from funnelforge.pipeline.steps import sem_eco_do_titulo
    titulo = "Quem tem direito à Tarifa Social?"
    corpo = "\n\n".join([_p(titulo), _p("Um."), _p("Dois."), _p("Três."), TITULO, _p("Quatro.")])
    novo, saiu = sem_eco_do_titulo(corpo, titulo, [1, 3])
    assert saiu and titulo not in novo and novo.startswith("<!-- wp:paragraph -->\n<p>Um.")
    curto = "\n\n".join([_p(titulo), _p("Um."), _p("Dois.")])
    assert sem_eco_do_titulo(curto, titulo, [1, 3]) == (curto, False)   # slot ficaria sem <p>
    assert sem_eco_do_titulo(corpo, "Outro título", [1, 3]) == (corpo, False)


def test_bloqueante_resolvido_quando_o_patch_embrulha_o_trecho(tmp_path):
    from tests.test_revisor_decisao import _rodar
    import json as _json
    trecho = "para quem cumpre a regra"
    resposta = _json.dumps({
        "versao": "revisao-v1", "decisao": "ajustar",
        "achados": [{"id": "a1", "severidade": "bloqueante", "categoria": "congruencia_destino",
                     "campo": "corpo", "trecho": trecho, "motivo": "quebra",
                     "evidencia": {"tipo": "destino", "ref": "d1"}}],
        "patches": [{"achado": "a1", "campo": "corpo", "antes": trecho,
                     "depois": f"<strong>{trecho}</strong>"}],
        "afirmacoes_nao_verificadas": [], "preservado": [],
        "notas": {"compliance": 9, "cta_discipline": 9, "useful_delivery": 9,
                  "destination_relevance": 9}}, ensure_ascii=False)
    r, _ = _rodar([resposta], tmp_path)
    assert r.registro["rodadas"][0]["patches_aplicados"], r.registro
    assert not any(m.startswith("bloqueante_nao_resolvido") for m in r.registro["motivos"]), r.registro
    assert r.decisao == "aprovado"
