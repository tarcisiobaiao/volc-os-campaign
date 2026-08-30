"""A matriz páginas × etapas, medida contra um run real.

A fixture é o `state.json` do run #6 (17/08/2026, 43 passos, US$ 2,4215): funil
de 5 páginas, 3 publicadas como rascunho, 2 bloqueadas por motivos DIFERENTES —
a 4 morreu na pesquisa, a 3 no portão de conteúdo. É a única fixture que exercita
os sete estados de célula ao mesmo tempo, e por isso ela é o teste.

Um `state.json` inventado à mão não serviria: as três armadilhas que este módulo
existe para resolver (a chave `page_N` sem o `p`, a ausência ambígua e a cauda
cancelada) só aparecem em estado real.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.redator import matriz as mz

MOTOR = Path(__file__).resolve().parents[2] / "funnelforge-migracao" / "engine"
RUN6 = MOTOR / "runs" / "cartao-credito-negativado-20260817-191650" / "state.json"

FLAGS = {"featured_image": True, "official_screenshots": True,
         "widgets_enabled": True, "publish": True}


@pytest.fixture(scope="module")
def estado() -> dict:
    if not RUN6.is_file():
        pytest.skip(f"fixture do run #6 ausente: {RUN6}")
    return json.loads(RUN6.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def grade(estado: dict) -> dict:
    return mz.montar(estado, flags=FLAGS)


# ── o parse ────────────────────────────────────────────────────────────────

def test_page_n_nao_vira_passo_fantasma():
    """A armadilha central. `page_5` quebra a convenção `<etapa>_p<N>`: não tem
    o `p` do meio. Um `split('_p')` devolveria ('', 5) e um `rsplit` devolveria
    ('age', 5) — uma coluna que não existe, com dados reais dentro."""
    assert mz.parse_chave("page_5") == ("page", 5)
    assert mz.parse_chave("page_1") == ("page", 1)
    # o que um split ingênuo produziria, para o teste falhar se alguém "otimizar"
    assert mz.parse_chave("page_5") != ("age", 5)
    assert mz.parse_chave("page_5") != ("", 5)


def test_parse_das_chaves_normais():
    assert mz.parse_chave("write_p3") == ("write", 3)
    assert mz.parse_chave("image_gen_p2") == ("image_gen", 2)   # underscore no nome
    assert mz.parse_chave("content_gate_p10") == ("content_gate", 10)
    assert mz.parse_chave("publish_p12") == ("publish", 12)


def test_passos_do_run_nao_tem_numero_de_pagina():
    for chave in mz.FAIXA_DO_RUN:
        assert mz.parse_chave(chave) == (chave, None)


def test_blocked_pn_nao_e_coluna(grade: dict):
    """`blocked_p3` casa com a regex `_p(\\d+)$`, mas `blocked` não é etapa. Se
    escorregar para `celulas`, a tela ganha uma coluna fantasma."""
    assert "blocked_p3" not in grade["celulas"]
    assert "blocked_p3" in grade["faixa"]


# ── a máscara ──────────────────────────────────────────────────────────────

def test_lp_nao_tem_juiz_print_nem_widget():
    ok = mz.aplicaveis_da_pagina("LP", tem_screenshot=True, widgets_ligados=True)
    assert "judge" not in ok        # a LP dá return antes do juiz: é JSON de slots
    assert "screenshot" not in ok
    assert "widget" not in ok
    assert "image_gen" in ok        # a LP SEMPRE quer imagem, mesmo sem featured_image


def test_presell_tem_juiz_mas_nao_widget():
    ok = mz.aplicaveis_da_pagina("PRESELL", tem_screenshot=True, widgets_ligados=True)
    assert "judge" in ok
    assert "widget" not in ok       # widget é só de SOLUTION
    assert "screenshot" not in ok


def test_dado_unico_derruba_o_widget():
    """O engajamento `dado_unico` é a exceção que não vem do papel. Sem ela a
    tela mostraria um widget pendente que nunca vai existir."""
    com = mz.aplicaveis_da_pagina("SOLUTION", widgets_ligados=True, engajamento="calculadora")
    sem = mz.aplicaveis_da_pagina("SOLUTION", widgets_ligados=True, engajamento="dado_unico")
    assert "widget" in com
    assert "widget" not in sem


def test_flag_desligada_remove_a_coluna():
    assert "widget" not in mz.aplicaveis_da_pagina("SOLUTION", widgets_ligados=False)
    assert "screenshot" not in mz.aplicaveis_da_pagina("SOLUTION", tem_screenshot=False)
    assert "publish" not in mz.aplicaveis_da_pagina("SOLUTION", publica=False)


def test_a_mascara_sai_na_ordem_do_pipeline():
    """A tela desenha a linha na ordem em que recebe. Fora de ordem, o funil
    apareceria com o `publish` antes do `build`."""
    ok = mz.aplicaveis_da_pagina("SOLUTION", tem_screenshot=True, widgets_ligados=True)
    ordem = [c["chave"] for c in mz.COLUNAS]
    assert ok == [c for c in ordem if c in set(ok)]


def test_toda_ausencia_do_run_real_e_explicada(grade: dict):
    """O teste que justifica a máscara existir.

    Percorre as 55 posições da grade do run #6. Toda célula ausente tem de ser
    explicada por UM de três motivos: não se aplica àquela página, está na cauda
    de uma página bloqueada, ou a página não chegou lá. Qualquer ausência sem
    explicação é um buraco que a tela pintaria de "pendente" para sempre.
    """
    ordem = [c["chave"] for c in mz.COLUNAS]
    inexplicadas = []
    for pg in grade["paginas"]:
        n = pg["page_number"]
        corte = (ordem.index(pg["bloqueada_em"])
                 if pg["bloqueada_em"] else len(ordem))
        for i, c in enumerate(ordem):
            if f"{c}_p{n}" in grade["celulas"]:
                continue
            if c not in pg["aplicaveis"]:
                continue                      # ausência estrutural
            if pg["bloqueada"] and i > corte:
                continue                      # cauda cancelada
            inexplicadas.append(f"{c}_p{n}")
    assert inexplicadas == [], f"a tela não saberia o que pintar em: {inexplicadas}"


# ── as linhas ──────────────────────────────────────────────────────────────

def test_as_cinco_paginas_com_os_papeis_certos(grade: dict):
    papeis = [(p["page_number"], p["papel"]) for p in grade["paginas"]]
    assert papeis == [(1, "LP"), (2, "PRESELL"), (3, "SOLUTION"),
                      (4, "SOLUTION"), (5, "SOLUTION")]


def test_o_papel_nunca_vem_do_page_type():
    """`page_type` diz HUB onde o papel é PRESELL. Usá-lo daria juiz e widget
    errados na linha inteira."""
    assert mz._papel({"role": "PRESELL", "page_type": "HUB"}) == "PRESELL"
    # sem `role`, deriva do slug — a mesma convenção do `derive_role` do motor
    assert mz._papel({"slug": "como-conseguir-cartao-pr"}) == "PRESELL"
    assert mz._papel({"slug": "requisitos-cartao-p1"}) == "SOLUTION"
    assert mz._papel({"slug": "cartao-credito-negativado"}) == "LP"


def test_onde_cada_pagina_bloqueada_morreu(grade: dict):
    """Os dois bloqueios do run #6 são em colunas diferentes — é isso que faz a
    cauda cancelada ter tamanhos diferentes."""
    por_n = {p["page_number"]: p for p in grade["paginas"]}
    assert por_n[3]["bloqueada"] and por_n[3]["bloqueada_em"] == "content_gate"
    assert por_n[4]["bloqueada"] and por_n[4]["bloqueada_em"] == "research"
    for n in (1, 2, 5):
        assert not por_n[n]["bloqueada"]
        assert por_n[n]["bloqueada_em"] is None


def test_a_causa_vence_a_consequencia(grade: dict):
    """`research_p4` FAILED e `write_p4` também (com `research_dependency_failed`).
    A coluna reportada tem de ser a PRIMEIRA na ordem do pipeline — a causa."""
    assert grade["celulas"]["write_p4"]["status"] == "FAILED"
    por_n = {p["page_number"]: p for p in grade["paginas"]}
    assert por_n[4]["bloqueada_em"] == "research"        # não "write"


def test_prints_sao_contados_nao_deduzidos(estado: dict, grade: dict):
    """`screenshot OK` não significa que existe print: o motor grava o OK fora
    do `if shots`. A célula mostra a CONTAGEM."""
    por_n = {p["page_number"]: p for p in grade["paginas"]}
    for n, pg in por_n.items():
        reais = len((estado.get("screenshots") or {}).get(str(n))
                    or (estado.get("screenshots") or {}).get(n) or [])
        assert pg["prints"] == reais


# ── o dinheiro ─────────────────────────────────────────────────────────────

def test_o_total_bate_com_a_soma_das_celulas(grade: dict, estado: dict):
    soma = sum(float((r or {}).get("cost_usd") or 0.0)
               for r in estado["step_status"].values())
    assert grade["custo_total"] == pytest.approx(soma, abs=1e-6)
    assert grade["custo_total"] == pytest.approx(2.4215, abs=1e-3)


def test_retentativa_nao_subestima(grade: dict):
    """`runner.py:125` faz `cost_usd += res.cost_usd` a cada tentativa que
    RETORNOU. `write_p5` teve 3 tentativas e traz a soma das três — então uma
    célula RETRIED não é motivo de aviso."""
    c = grade["celulas"]["write_p5"]
    assert c["status"] == "RETRIED" and c["tentativas"] == 3
    assert c["custo_usd"] > 0.2
    # e o run #6 inteiro não tem o caminho de exceção não faturada
    assert grade["subestimado"] is False


def test_subestimado_pega_o_caminho_de_excecao():
    """A assinatura do `runner.py:110`: FAILED SEM issue. Reprovação de
    validação sempre carrega issues; exceção não chega aqui — e nesse caso o
    provedor pode ter faturado uma chamada que o motor nunca contou."""
    honesto = mz.montar({"step_status": {
        "write_p1": {"status": "FAILED", "cost_usd": 0.1,
                     "issues": [{"code": "ungrounded_critical_claim"}]}}})
    cego = mz.montar({"step_status": {
        "write_p1": {"status": "FAILED", "cost_usd": 0.0, "issues": []}}})
    assert honesto["subestimado"] is False
    assert cego["subestimado"] is True


def test_a_maior_celula_da_a_escala(grade: dict):
    """A altura de cada célula é proporcional a ela. Zero aqui seria divisão por
    zero na tela."""
    assert grade["custo_maior_celula"] == pytest.approx(0.4556, abs=1e-3)
    assert grade["custo_maior_celula"] > 0


def test_colunas_nao_pagas_declaradas():
    """A tela não pode escrever "US$ 0,00" numa coluna que nunca custa: isso
    sugere medição onde não há. `build`, `screenshot`, `content_gate` e
    `publish` são locais."""
    nao_pagas = {c["chave"] for c in mz.COLUNAS if not c["paga"]}
    assert nao_pagas == {"screenshot", "build", "content_gate", "publish"}


def test_o_run_real_confirma_que_nao_pagas_nao_custam(grade: dict):
    nao_pagas = {c["chave"] for c in mz.COLUNAS if not c["paga"]}
    for chave, celula in grade["celulas"].items():
        etapa, _ = mz.parse_chave(chave)
        if etapa in nao_pagas:
            assert celula["custo_usd"] == 0.0, f"{chave} custou dinheiro"


# ── o elo com a campanha ───────────────────────────────────────────────────

def test_as_publicadas_trazem_o_que_o_wp_devolveu(estado: dict):
    """É por igualdade de string com `campaign_funnel_urls` que a receita do
    AdSense é atribuída ao clique comprado. Remontar a URL do slug quebraria a
    atribuição em silêncio quando o WP acrescenta `-2`."""
    pub = estado.get("published") or {}
    assert len(pub) == 3
    for reg in pub.values():
        assert reg["post_id"] > 0
        assert reg["url_wp"].startswith("http")
        assert reg["status_wp"] == "draft"
        assert reg["slug"]


def test_rascunho_nao_finge_ter_permalink(estado: dict):
    """O WP devolve `?post_type=r&p=2146` para rascunho. O `/r/<slug>/` só nasce
    no ar — e `status_wp` é o que avisa quem consome."""
    for reg in (estado.get("published") or {}).values():
        if reg["status_wp"] == "draft":
            assert "?post_type=" in reg["url_wp"] or "/?p=" in reg["url_wp"]


# ── o polling ──────────────────────────────────────────────────────────────

def test_a_impressao_muda_com_o_estado_e_so_com_ele():
    a = {"write_p1": {"status": "OK", "cost_usd": 0.1}}
    b = {"write_p1": {"status": "OK", "cost_usd": 0.2}}
    assert mz.impressao(a) == mz.impressao(a)
    assert mz.impressao(a) != mz.impressao(b)
    # ordem de inserção não pode mudar a impressão: seriam 900 escritas por run
    assert mz.impressao({"a": 1, "b": 2}) == mz.impressao({"b": 2, "a": 1})


def test_estado_vazio_nao_explode():
    """Um run recém-enfileirado não tem `state.json`. A tela tem de abrir."""
    g = mz.montar({})
    assert g["paginas"] == [] and g["celulas"] == {}
    assert g["custo_total"] == 0.0
    assert g["custo_maior_celula"] == 0.0        # a tela divide por isto
    assert g["subestimado"] is False


def test_flags_ausentes_nao_ligam_coluna(tmp_path):
    """Chave ausente no YAML significa o padrão do pydantic (False), não
    "ligado" — senão a tela mostraria widget pendente num motor sem widget."""
    (tmp_path / "config.yaml").write_text("run:\n  max_retries: 2\n")
    assert mz.flags_do_motor(tmp_path) == {
        "featured_image": False, "official_screenshots": False,
        "widgets_enabled": False}


def test_sem_config_a_tela_ainda_abre(tmp_path):
    assert mz.flags_do_motor(tmp_path / "nao-existe") == {
        "featured_image": False, "official_screenshots": False,
        "widgets_enabled": False}
