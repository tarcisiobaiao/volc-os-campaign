"""Entradas melhores para o redator, sem trava semântica (rodada de 10/10, M1–M6).

- M3: o redator vê controles e cenários da peça pronta em texto (não o JSON nem
  o HTML) e o gerador da peça vê as seções e blocos que o texto já entrega.
- M5: a legenda do print reaproveita a proveniência (título da página capturada
  e trecho que a fonte sustenta); sem eles, a legenda fica como era.
- M6: a promessa e a profundidade declaradas por coorte chegam ao prompt.
- M1/M2/M4: a orientação está no prompt ATIVO (arquiteto, jornada, interior,
  sniper), como orientação editorial, nunca como veto ou contagem.
"""
import json
from importlib import resources

from funnelforge.pipeline import steps as st
from funnelforge.pipeline.inteligencia import congelar_pacotes, peca_em_texto, prompt_do_pacote
from funnelforge.pipeline.jornada.contexto import contexto_de_jornada
from funnelforge.prompts import render
from tests.test_ctas_do_funil import estado
from tests.test_widgets_do_funil import NAVEGADOR, com_widgets, widget_calls


def _fonte(nome: str) -> str:
    return resources.files("funnelforge.prompts").joinpath(nome).read_text("utf-8")


# ---------------------------------------------------------------------------
# M3 — texto e peça se veem
# ---------------------------------------------------------------------------

def test_peca_em_texto_mostra_controles_cenarios_e_rodape_sem_html():
    texto = peca_em_texto(NAVEGADOR)
    assert 'pergunta "Em que etapa você está?" com as opções Ainda não comecei / Já enviei a inscrição' in texto
    assert 'cenário "Comece pela unidade do seu estado" [primeiro passo]' in texto
    assert "Procure a unidade do Senac do seu estado; Separe os documentos" in texto
    assert "rodapé: Orientação com base nas regras do Senac." in texto
    assert "<" not in texto and "{" not in texto
    assert peca_em_texto(None) == "" and peca_em_texto("NONE") == ""


def test_redator_recebe_os_cenarios_da_peca_em_texto_e_nao_o_json(tmp_path):
    state, deps, llm = estado(tmp_path, com_widgets(lambda i: {"widget": NAVEGADOR}
                                                    if i == 0 else {"widget": "NONE"}))
    congelar_pacotes(state, deps)
    n = next(n for n, p in state.pacotes.items() if p["ferramenta"].get("orientacao"))
    page = next(p for p in state.plan.pages if p.page_number == n)
    prompt = prompt_do_pacote(state, page)
    assert "O que a peça já diz ao leitor, por situação" in prompt
    assert "Comece pela unidade do seu estado" in prompt and "Acompanhe a resposta da unidade" in prompt
    assert "não repita os cenários dela em lista, passos ou tabela" in prompt
    assert '"conteudo"' not in prompt and '"cenarios"' not in prompt     # texto, não JSON
    assert 'class="vw-' not in prompt                                    # nem HTML
    # O pacote congelado continua inteiro: a correção localizada do revisor
    # parte do conteúdo validado.
    assert state.pacotes[n]["ferramenta"]["orientacao"]["conteudo"]["cenarios"]


def test_gerador_da_peca_ve_as_secoes_e_blocos_que_o_texto_ja_entrega(tmp_path):
    state, deps, llm = estado(tmp_path, com_widgets(lambda i: {"widget": "NONE"}))
    congelar_pacotes(state, deps)
    prompt = widget_calls(llm)[0]["messages"][-1]["content"]
    assert "Seções e blocos que o texto já entrega (não repita isto em cenários):" in prompt
    candidatas = [p for p in state.plan.pages if p.page_number in
                  json.loads(next(i.message for i in state.step_status["widgets_do_funil"].issues
                                  if i.code == "widgets_do_funil"))["paginas"]]
    assert any(h2 in prompt for p in candidatas for h2 in p.main_content_structure)
    assert "A peça complementa o texto" in prompt
    assert "não repita esse limite no subtítulo, nos cenários nem no rodapé" in prompt


# ---------------------------------------------------------------------------
# M5 — legenda e alt do print pela proveniência
# ---------------------------------------------------------------------------

def test_legenda_do_print_reaproveita_titulo_e_trecho_quando_existem():
    base = st.legenda_do_print("www.gov.br", capturado_em="2026-10-10T12:00:00+00:00")
    assert base.startswith("Reprodução: site oficial (www.gov.br)")
    assert "página" not in base and "sustenta" not in base      # sem proveniência, sem afirmação
    rica = st.legenda_do_print("www.gov.br", capturado_em="2026-10-10T12:00:00+00:00",
                               titulo="  Tarifa Social de Energia  Elétrica — ANEEL ",
                               trecho="100 % (desconto nos primeiros 80 kWh)")
    assert "página “Tarifa Social de Energia Elétrica — ANEEL”" in rica
    assert "O que esta fonte sustenta no texto: 100 % (desconto nos primeiros 80 kWh)" in rica


def test_figcaption_publicada_leva_a_legenda_escapada_e_o_formato_antigo_continua():
    html = ('<!-- wp:heading --><h2>Como atualizar</h2><!-- /wp:heading -->\n'
            '<!-- wp:paragraph --><p>Acesse o <a href="https://meu.inss.gov.br/x">Meu INSS</a>.</p>'
            '<!-- /wp:paragraph -->')
    novo = st._insert_official_screenshot(
        html, "https://cdn.example/shot.webp", "https://meu.inss.gov.br/x", "meu.inss.gov.br",
        "alt", capturado_em="2026-10-10T12:00:00+00:00",
        titulo="Meu INSS <Atualizar> cadastro", trecho="atualização em até 5 dias")
    assert "Reprodução: site oficial (meu.inss.gov.br)" in novo
    assert "página “Meu INSS &lt;Atualizar&gt; cadastro”" in novo
    assert "O que esta fonte sustenta no texto: atualização em até 5 dias" in novo
    antigo = st._insert_official_screenshot(
        html, "https://cdn.example/shot.webp", "https://meu.inss.gov.br/x", "meu.inss.gov.br", "alt")
    assert "página" not in antigo.split("figcaption")[1]


def test_alt_do_print_descreve_a_pagina_capturada(tmp_path):
    from funnelforge.domain.models import ResearchFacts
    arquivo = tmp_path / "p.webp"
    arquivo.write_bytes(b"x")
    com = st.proveniencia_do_print("https://www.gov.br/x", arquivo, ResearchFacts(),
                                   titulo="Consultar FGTS — gov.br", crop="desktop")
    assert com["alt"].startswith("Reprodução: www.gov.br — tela oficial de")
    assert com["alt"].endswith(": página “Consultar FGTS — gov.br”")
    sem = st.proveniencia_do_print("https://www.gov.br/x", arquivo, ResearchFacts(),
                                   titulo="", crop="desktop")
    assert "página" not in sem["alt"]


# ---------------------------------------------------------------------------
# M6 — promessa e profundidade por coorte chegam ao prompt (só repasse)
# ---------------------------------------------------------------------------

def test_coortes_detalhadas_sao_so_as_que_entram_na_pagina(tmp_path):
    state, deps, llm = estado(tmp_path, com_widgets(lambda i: {"widget": "NONE"}))
    plano = state.plan
    assert plano.jornada is not None and plano.jornada.coortes, "fixture sem coortes"
    por_pagina = {p.jornada.duvida_id: contexto_de_jornada(plano, p, state.dossie)["coortes_detalhadas"]
                  for p in plano.pages}
    for c in plano.jornada.coortes:
        detalhes = por_pagina[c.entrada]
        assert {"canal": c.canal, "promessa": c.promessa, "profundidade": c.profundidade}.items() <= \
            {k: v for d in detalhes if d["canal"] == c.canal for k, v in d.items()}.items()
    fora = [d for duvida, ds in por_pagina.items() for d in ds
            if not any(c.entrada == duvida and c.canal == d["canal"] for c in plano.jornada.coortes)]
    assert fora == []
    texto = render("jornada_da_pagina", jornada=contexto_de_jornada(
        plano, next(p for p in plano.pages if p.jornada.duvida_id == plano.jornada.coortes[0].entrada),
        state.dossie))
    assert f"quem chega por {plano.jornada.coortes[0].canal} espera: {plano.jornada.coortes[0].promessa}" in texto


# ---------------------------------------------------------------------------
# M1/M2/M4 — a orientação está no prompt ativo e não virou veto
# ---------------------------------------------------------------------------

def test_arquiteto_separa_resposta_imediata_do_limite_do_portal():
    from funnelforge.adapters.attention_matrix import modulo_do_repo
    prompt = modulo_do_repo("backend/app/n8n_prompts/funnel_builder.py")
    sistema = prompt.FUNNEL_ARCHITECT_SYSTEM_MESSAGE
    usuario = prompt.build_funnel_architect_user(
        pais="Brasil", tema="t", lingua="pt-BR", data_atual="2026-10-10",
        supporting_data="", user_questions="")
    assert "não a escreva em" in sistema and "resposta_imediata, useful_delivery" in sistema
    assert "Um limite que É a resposta ao leitor fica" in sistema
    assert "afirmativa e\n  nas palavras de quem busca" in usuario
    assert "A forma segue a entrega do destino" in sistema
    assert "não são obrigatórios nem proibidos" in sistema


def test_jornada_interior_e_sniper_orientam_sem_vetar():
    jornada = _fonte("jornada_da_pagina.jinja")
    assert "não o aviso do portal" in jornada and "só fica o limite que é a própria resposta" in jornada
    interior = _fonte("interior_editorial_v2.jinja")
    assert "o primeiro parágrafo é a resposta imediata" in interior
    assert "Ela não descreve o site nem a navegação" in interior
    assert "só quando há, por perto, um passo em outro site" in interior
    sniper = _fonte("ctas_do_funil.jinja")
    assert "A forma segue a entrega do destino, não um molde" in sniper
    assert "não são obrigatórios nem proibidos" in sniper and "Nenhum verbo é proibido" in sniper
    assert 'Trocar "Saiba" por "Descubra" não é melhora' in sniper
    assert "no país e no idioma do funil" in sniper
    # Nada disto virou contagem, lista de palavras ou bloqueio no código.
    for nome in ("ctas.py", "revisao.py", "steps.py"):
        fonte = resources.files("funnelforge.pipeline").joinpath(nome).read_text("utf-8")
        assert "deste site" not in fonte and "PALAVRAS_PROIBIDAS" not in fonte
