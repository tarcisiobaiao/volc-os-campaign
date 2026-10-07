"""D2 — regressão de COMPOSIÇÃO no ramo editorial_v2 (não de copy).

Diagnóstico: o ramo v2 zerava `exigencia_visual` sem condição e o catálogo v2
ficou todo opcional; as páginas saíam só com parágrafo/título/lista/botões.
Correção: o briefing declara um `visual_plan` tipado por seção; a exigência
visual do redator v2 sai desse plano; um portão de composição determinístico
aponta paredão, repetição e bloco inadequado ao revisor (localizador) e
BLOQUEIA só a dependência comprovada: os slots do Ad Inserter (diretriz 2,
item 8: bloco 1 antes do 1º <p>, bloco 2 após o 3º <p>, só <p> contável).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from funnelforge.pipeline import steps
from funnelforge.pipeline.retry_policy import classe_da_issue
from funnelforge.pipeline.validators.briefing_contract import (
    INTENCOES_VISUAIS,
    PADROES_VISUAIS,
    exigencia_visual_do_plano,
    validar_briefing,
)
from funnelforge.pipeline.validators.checks import VALIDATORS, composicao_editorial
from funnelforge.prompts import render
from tests.cenario_editorial import (
    arquitetura_base,
    briefing_valido,
    congelar_data,
    prompts_do_run,
    responder_v2,
    rodar_cenario,
    settings_do_cenario,
    texto_da_mensagem,
)
from tests.test_briefing_contrato import BRIEFING_VALIDO, _ref

PROMPTS = Path(__file__).resolve().parents[1] / "src" / "funnelforge" / "prompts"

PLANO = [
    {"secao": "Quem tem direito", "intencao": "checklist", "padrao": "list",
     "motivo": "requisitos que o leitor confere um a um"},
    {"secao": "Tarifa social x desconto comum", "intencao": "comparar",
     "padrao": "core/table", "motivo": "dois programas com os mesmos atributos"},
    {"secao": "Dúvidas", "intencao": "faq", "padrao": "details",
     "motivo": "perguntas reais do PAA"},
]


def _avaliar(plano):
    dados = copy.deepcopy(BRIEFING_VALIDO)
    if plano is not ...:
        dados["visual_plan"] = plano
    erros, avisos = validar_briefing(dados, _ref())
    return [i.code for i in erros], [i.code for i in avisos]


# --------------------------------------------------------------------------
# 1. visual_plan no contrato do briefing (só estrutura e vocabulário fechado)
# --------------------------------------------------------------------------

def test_visual_plan_valido_passa_sem_erro_nem_aviso():
    erros, avisos = _avaliar(PLANO)
    assert erros == []
    assert not [a for a in avisos if "visual" in a]


def test_visual_plan_ausente_e_aviso_nao_erro():
    erros, avisos = _avaliar(...)
    assert erros == []
    assert "aviso_sem_plano_visual" in avisos


def test_visual_plan_fora_do_vocabulario_e_erro_estrutural():
    for ruim in (
        [{**PLANO[0], "intencao": "enfeitar"}],
        [{**PLANO[0], "padrao": "slider"}],
        [{**PLANO[0], "secao": "  "}],
        [{**PLANO[0], "motivo": ""}],
        ["checklist"],
        {"secao": "x"},
    ):
        erros, _ = _avaliar(ruim)
        assert "plano_visual_invalido" in erros, ruim


def test_padrao_valido_mas_atipico_para_a_intencao_e_so_aviso():
    erros, avisos = _avaliar([{**PLANO[0], "intencao": "faq", "padrao": "table"}])
    assert erros == []
    assert "aviso_padrao_atipico_para_a_intencao" in avisos


def test_vocabulario_fechado_mapeia_toda_intencao_para_padrao_do_catalogo():
    assert set(INTENCOES_VISUAIS) == {
        "comparar", "passo_a_passo", "checklist", "fato_chave",
        "navegacao_por_regiao", "atencao", "faq", "exemplos_numericos"}
    for intencao, padroes in INTENCOES_VISUAIS.items():
        assert padroes and set(padroes) <= set(PADROES_VISUAIS), intencao


def test_exigencia_visual_segue_o_plano_sem_repetir_e_na_ordem():
    plano = PLANO + [{"secao": "Mais", "intencao": "comparar", "padrao": "wp:table",
                      "motivo": "m"}]
    assert exigencia_visual_do_plano({"visual_plan": plano}) == ["list", "table", "details"]
    assert exigencia_visual_do_plano({}) == []
    assert exigencia_visual_do_plano({"visual_plan": [{"padrao": "slider"}]}) == []


def test_prompt_do_briefing_declara_o_vocabulario_inteiro():
    texto = (PROMPTS / "briefing.jinja").read_text(encoding="utf-8")
    assert '"visual_plan"' in texto
    for intencao in INTENCOES_VISUAIS:
        assert intencao in texto, intencao
    for padrao in PADROES_VISUAIS:
        assert padrao in texto, padrao


# --------------------------------------------------------------------------
# 2. catálogo v2: padrões nativos, intenção -> padrão, wp:html só sem nativo
# --------------------------------------------------------------------------

def test_catalogo_v2_mapeia_intencao_para_padrao_nativo():
    texto = (PROMPTS / "blocks_gutenberg_v2.jinja").read_text(encoding="utf-8")
    for intencao in INTENCOES_VISUAIS:
        assert intencao in texto, intencao
    # checklist, passo a passo e a favor x atenção eram wp:html; agora são nativos
    assert "<!-- wp:list {\"ordered\":true} -->" in texto
    assert texto.count("<!-- wp:html -->") == 1          # só a barra de progresso
    assert "<thead>" in texto and "<summary>" in texto   # tabela e details semânticos
    assert "não a duplique" in texto                     # pullquote move, não duplica


def test_redator_v2_recebe_o_plano_por_secao():
    from tests.test_prompts_v2 import REDATORES_V2
    texto = render("redator_pages_v2", **{**REDATORES_V2["redator_pages_v2"],
                                          "exigencia_visual": ["list", "table"],
                                          "plano_visual": PLANO})
    assert "wp:list, wp:table" in texto
    assert "Tarifa social x desconto comum" in texto
    assert "comparar" in texto


# --------------------------------------------------------------------------
# 3. exigencia_visual não é mais esvaziada no v2: segue o visual_plan
# --------------------------------------------------------------------------

def _responder_com_plano(plano):
    def responder(model: str, messages: list[dict]) -> str:
        prompt = texto_da_mensagem(messages[-1])
        if "EDITOR DE BRIEFING" in prompt:
            dados = json.loads(briefing_valido(prompt))
            dados["visual_plan"] = plano
            return json.dumps(dados, ensure_ascii=False)
        return responder_v2(model, messages)
    return responder


def _rodar_v2(tmp_path, monkeypatch, responder):
    congelar_data(monkeypatch)
    settings = settings_do_cenario(tmp_path, editorial_v2=True, passos_v2=True)
    return rodar_cenario(tmp_path, arquitetura_base(), settings, responder=responder)


def test_v2_redator_recebe_exigencia_visual_do_visual_plan(tmp_path, monkeypatch):
    state, deps, _ = _rodar_v2(tmp_path, monkeypatch, _responder_com_plano(PLANO))
    prompts = prompts_do_run(deps.runner.runs_dir, state.run_id)
    for n in range(2, 6):
        redator = prompts[f"write_p{n}"]
        assert "O plano visual do briefing pede estes blocos" in redator, n
        assert "wp:list, wp:table, wp:details" in redator, n
        assert "Tarifa social x desconto comum" in redator, n
    assert state.briefings[3]["visual_plan"][1]["padrao"] == "core/table"


def test_v2_sem_visual_plan_nao_inventa_exigencia(tmp_path, monkeypatch):
    state, deps, _ = _rodar_v2(tmp_path, monkeypatch, responder_v2)
    prompts = prompts_do_run(deps.runner.runs_dir, state.run_id)
    assert "O plano visual do briefing pede estes blocos" not in prompts["write_p3"]


def test_steps_nao_esvazia_mais_a_exigencia_visual_sem_condicao():
    fonte = Path(steps.__file__).read_text(encoding="utf-8")
    assert 'extras_v2["exigencia_visual"] = []' not in fonte


# --------------------------------------------------------------------------
# 4. portão de composição
# --------------------------------------------------------------------------

def _p(texto: str) -> str:
    return f"<!-- wp:paragraph -->\n<p>{texto}</p>\n<!-- /wp:paragraph -->"


def _h2(texto: str) -> str:
    return f'<!-- wp:heading -->\n<h2 class="wp-block-heading">{texto}</h2>\n<!-- /wp:heading -->'


LOREM = ("A família confere a renda por pessoa, junta os documentos pedidos e leva "
         "o pedido à distribuidora de energia da sua cidade sem pagar intermediário. ")
GRUPO = ('<!-- wp:group {"layout":{"type":"constrained"}} -->\n<div class="wp-block-group">'
         + _p("Resumo curto da seção.") + '</div>\n<!-- /wp:group -->')
GRUPO2 = ('<!-- wp:group {"layout":{"type":"constrained"}} -->\n<div class="wp-block-group">'
          + _p("Outro destaque diferente.") + '</div>\n<!-- /wp:group -->')
TABELA_OK = ('<!-- wp:table -->\n<figure class="wp-block-table"><table><thead><tr><th>A</th>'
             '<th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>'
             '</figure>\n<!-- /wp:table -->')
TABELA_SEM_CABECALHO = ('<!-- wp:table -->\n<figure class="wp-block-table"><table><tbody><tr>'
                        '<td>1</td><td>2</td></tr></tbody></table></figure>\n<!-- /wp:table -->')
DETALHE_OK = ('<!-- wp:details -->\n<details class="wp-block-details"><summary>Quem pede?'
              '</summary>' + _p("O titular da conta.") + '</details>\n<!-- /wp:details -->')
DETALHE_SEM_SUMMARY = ('<!-- wp:details -->\n<details class="wp-block-details">'
                       + _p("O titular da conta.") + '</details>\n<!-- /wp:details -->')
LISTA = ('<!-- wp:list -->\n<ul class="wp-block-list"><!-- wp:list-item --><li>um</li>'
         '<!-- /wp:list-item --></ul>\n<!-- /wp:list -->')
CTX = {"ad_paragraph_anchors": [1, 3]}


def _abertura() -> list[str]:
    return [_p("Primeiro parágrafo da abertura."), _p("Segundo parágrafo."),
            _p("Terceiro parágrafo, ainda no fluxo principal.")]


def _codigos(partes: list[str], ctx=CTX) -> set[str]:
    return {i.code for i in composicao_editorial("\n".join(partes), ctx)}


def test_pagina_bem_composta_passa_limpa():
    corpo = _abertura() + [_h2("Quem tem direito"), LISTA, _p(LOREM), TABELA_OK,
                           _h2("Dúvidas"), DETALHE_OK, DETALHE_OK]
    assert _codigos(corpo) == set()


def test_paredao_de_texto_em_pagina_longa_vira_localizador():
    corpo = _abertura() + [_h2("Seção")] + [_p(LOREM * 4) for _ in range(7)]
    issues = composicao_editorial("\n".join(corpo), CTX)
    paredao = [i for i in issues if i.code == "composicao_paredao_de_texto"]
    assert len(paredao) == 1
    assert classe_da_issue(paredao[0]) == "patchavel"
    # página curta com o mesmo número de parágrafos não é paredão
    curta = _abertura() + [_h2("Seção")] + [_p("Frase curta.") for _ in range(7)]
    assert "composicao_paredao_de_texto" not in _codigos(curta)


def test_repeticao_visual_sem_motivo_vira_localizador():
    corpo = _abertura() + [GRUPO, GRUPO2, _p(LOREM)]
    issues = composicao_editorial("\n".join(corpo), CTX)
    rep = [i for i in issues if i.code == "composicao_repeticao_visual"]
    assert rep and classe_da_issue(rep[0]) == "patchavel"
    # perguntas do leitor em sequência (um details por pergunta) é o padrão
    assert "composicao_repeticao_visual" not in _codigos(_abertura() + [DETALHE_OK] * 3)


def test_bloco_semanticamente_inadequado_vira_localizador():
    pull = ('<!-- wp:pullquote -->\n<figure class="wp-block-pullquote"><blockquote><p>'
            'Quem paga intermediário paga por algo que é de graça.</p></blockquote></figure>'
            '\n<!-- /wp:pullquote -->')
    corpo = _abertura() + [
        TABELA_SEM_CABECALHO, _p(LOREM), DETALHE_SEM_SUMMARY, _p(LOREM),
        _p("Lembre: quem paga intermediário paga por algo que é de graça."), pull]
    issues = composicao_editorial("\n".join(corpo), CTX)
    codigos = {i.code for i in issues}
    assert {"bloco_tabela_sem_cabecalho", "bloco_details_sem_summary",
            "bloco_pullquote_duplicado"} <= codigos
    assert all(classe_da_issue(i) == "patchavel" for i in issues)


def test_slot_do_ad_inserter_sem_terceiro_p_contavel_bloqueia():
    pull = ('<!-- wp:pullquote -->\n<figure class="wp-block-pullquote"><blockquote><p>'
            'Frase em destaque.</p></blockquote></figure>\n<!-- /wp:pullquote -->')
    # o <p> do pullquote (blockquote) NÃO é contado pelo Ad Inserter
    corpo = [_p("Um."), pull, _p("Dois."), _h2("Seção"), LISTA]
    issues = composicao_editorial("\n".join(corpo), CTX)
    slot = [i for i in issues if i.code == "ad_slot_inseguro"]
    assert slot and classe_da_issue(slot[0]) == "estrutural"


def test_slot_com_primeiro_ou_terceiro_p_fora_do_fluxo_principal_bloqueia():
    no_details = [DETALHE_OK, _p("Dois."), _p("Três."), _p("Quatro.")]
    assert "ad_slot_inseguro" in _codigos(no_details)
    tabela_com_p = ('<!-- wp:table -->\n<figure class="wp-block-table"><table><thead><tr>'
                    '<th>A</th></tr></thead><tbody><tr><td><p>x</p></td></tr></tbody></table>'
                    '</figure>\n<!-- /wp:table -->')
    terceiro_na_tabela = [_p("Um."), _p("Dois."), tabela_com_p, _p("Quatro.")]
    assert "ad_slot_inseguro" in _codigos(terceiro_na_tabela)
    # o 2º <p> dentro de caixa não é âncora: não bloqueia
    segundo_em_coluna = [_p("Um."), GRUPO, _p("Três."), _p("Quatro.")]
    assert "ad_slot_inseguro" not in _codigos(segundo_em_coluna)


def test_sem_ancoras_configuradas_nao_ha_slot_a_proteger():
    assert "ad_slot_inseguro" not in _codigos([_p("Só um.")], ctx={})


def test_portao_esta_registrado_mas_fora_do_portao_final_do_ramo_antigo():
    assert VALIDATORS["composicao_editorial"] is composicao_editorial
    assert "composicao_editorial" not in steps._FINAL_CONTENT_VALIDATORS


def test_portao_final_v2_bloqueia_slot_e_entrega_o_resto_ao_revisor(tmp_path, monkeypatch):
    state, deps, _ = _rodar_v2(tmp_path, monkeypatch, responder_v2)
    pagina = next(p for p in state.plan.pages if p.page_number == 3)
    ruim = "\n".join([DETALHE_OK, _p("Dois."), _h2("Seção"), GRUPO, GRUPO2])
    codigos = {i.code for i in steps._final_content_issues(state, pagina, deps, ruim)}
    assert "ad_slot_inseguro" in codigos
    assert "composicao_repeticao_visual" not in codigos   # localizador, não bloqueio


def test_plano_visual_nao_cumprido_e_localizador_para_o_revisor():
    corpo = _abertura() + [_h2("Quem tem direito"), LISTA]
    issues = composicao_editorial("\n".join(corpo),
                                  {**CTX, "exigencia_visual": ["list", "table"]})
    faltou = [i for i in issues if i.code == "plano_visual_nao_cumprido"]
    assert len(faltou) == 1 and "wp:table" in faltou[0].message
    assert classe_da_issue(faltou[0]) == "patchavel"
