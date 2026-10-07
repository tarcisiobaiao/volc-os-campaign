"""A matriz conhece os passos do fluxo editorial v2 (briefing e revisor).

## Por que isto precisa existir antes do motor

A matriz lista as etapas (`COLUNAS`) e joga na FAIXA DO RUN toda chave cuja
etapa não é coluna (`matriz.py`, laço de `montar`). Sem isto, os passos novos
do motor — `briefing_pN` e `revisor_pN` — apareceriam como passos do run, fora
da linha da página, e a célula da página ficaria "pendente" para sempre.

E uma correção que vem junto: a LP TEM juiz quando traz `editorial`
(`steps.py`, `if page.editorial: _judge_page`). A máscara dizia que a LP nunca
tem juiz e pintava de "não se aplica" uma etapa que rodou e custou.

Os nomes `briefing`/`revisor` seguem a convenção do motor (`<passo>_p<N>`, como
`judge_pN`). `revisao_pN` é aceito como sinônimo até a trilha do motor fixar o
nome — ver o handoff B3a.
"""
from __future__ import annotations

from app.redator import matriz as mz

FLAGS = {"featured_image": True, "official_screenshots": False,
         "widgets_enabled": False, "publish": True}


def _plano(*, lp_editorial: bool = True) -> dict:
    return {"pages": [
        {"page_number": 1, "role": "LP", "slug": "guia-cursos-senac",
         "editorial": {"reader_question": "O Senac tem curso de graça?"} if lp_editorial else None},
        {"page_number": 2, "role": "SOLUTION", "slug": "senac-por-estado-p1",
         "editorial": {"reader_question": "Onde vejo a oferta do meu estado?"}},
    ]}


def _ok(custo: float = 0.0) -> dict:
    return {"status": "OK", "attempts": 1, "cost_usd": custo}


def _estado_v2() -> dict:
    passos = {}
    for n in (1, 2):
        for etapa in ("research", "briefing", "write", "seo", "revisor", "image", "image_gen",
                      "build", "content_gate", "publish"):
            passos[f"{etapa}_p{n}"] = _ok(0.01)
    return {"plan": _plano(), "step_status": passos}


# ── os passos novos são da PÁGINA, não do run ──────────────────────────────

def test_briefing_e_revisor_viram_celulas_da_pagina():
    g = mz.montar(_estado_v2(), flags=FLAGS)
    for n in (1, 2):
        assert f"briefing_p{n}" in g["celulas"]
        assert f"revisor_p{n}" in g["celulas"]
        assert f"briefing_p{n}" not in g["faixa"]
        assert f"revisor_p{n}" not in g["faixa"]


def test_run_v2_ganha_as_colunas_na_ordem_do_fluxo_novo():
    """Pesquisa → briefing → redação → SEO → revisor: o SEO roda ANTES do
    revisor no v2 (contrato entre trilhas, decisão 4), para o título que vira
    H1 também passar pela revisão."""
    g = mz.montar(_estado_v2(), flags=FLAGS)
    ordem = [c["chave"] for c in g["colunas"]]
    assert "judge" not in ordem             # o revisor substitui o juiz no v2
    assert ordem.index("research") < ordem.index("briefing") < ordem.index("write")
    assert ordem.index("write") < ordem.index("seo") < ordem.index("revisor")
    assert ordem.index("revisor") < ordem.index("build") < ordem.index("publish")
    pagas = {c["chave"]: c["paga"] for c in g["colunas"]}
    assert pagas["briefing"] is True and pagas["revisor"] is True


def test_no_v2_toda_pagina_tem_briefing_e_revisor_inclusive_a_lp():
    g = mz.montar(_estado_v2(), flags=FLAGS)
    for pg in g["paginas"]:
        assert "briefing" in pg["aplicaveis"]
        assert "revisor" in pg["aplicaveis"]
        assert "judge" not in pg["aplicaveis"]


def test_a_flag_do_perfil_liga_as_colunas_antes_do_primeiro_passo_v2():
    """No começo do run só existe `research_pN`. Sem a flag, a tela mostraria a
    grade antiga e trocaria de colunas no meio do caminho."""
    estado = {"plan": _plano(), "step_status": {"research_p1": _ok(0.3)}}
    g = mz.montar(estado, flags={**FLAGS, "editorial_v2": True})
    ordem = [c["chave"] for c in g["colunas"]]
    assert "briefing" in ordem and "revisor" in ordem
    assert "briefing" in g["paginas"][0]["aplicaveis"]


def test_run_antigo_fica_com_as_onze_colunas_de_sempre():
    estado = {"plan": _plano(), "step_status": {"research_p1": _ok(0.3), "judge_p2": _ok(0.02)}}
    g = mz.montar(estado, flags=FLAGS)
    assert g["colunas"] == mz.COLUNAS
    assert len(g["colunas"]) == 11


def test_revisao_pn_e_aceito_como_sinonimo_de_revisor():
    passos = {"research_p2": _ok(), "briefing_p2": _ok(), "write_p2": _ok(),
              "revisao_p2": {"status": "FAILED", "issues": [{"code": "revisao_humana",
                                                             "message": "decisão humana"}]}}
    g = mz.montar({"plan": _plano(), "step_status": passos}, flags=FLAGS)
    assert "revisor_p2" in g["celulas"]
    assert "revisao_p2" not in g["faixa"]
    assert g["celulas"]["revisor_p2"]["issues"][0]["code"] == "revisao_humana"


def test_pagina_barrada_no_briefing_morre_no_briefing():
    passos = {"research_p2": _ok(), "briefing_p2": {"status": "FAILED", "issues": []},
              "write_p2": {"status": "FAILED", "issues": []},
              "blocked_p2": {"status": "BLOCKED"}}
    g = mz.montar({"plan": _plano(), "step_status": passos},
                  flags={**FLAGS, "editorial_v2": True})
    p2 = next(p for p in g["paginas"] if p["page_number"] == 2)
    assert p2["bloqueada_em"] == "briefing"     # a causa vence a consequência


def test_toda_ausencia_do_run_v2_e_explicada():
    """O mesmo alarme do run #6, agora sobre a grade v2."""
    g = mz.montar(_estado_v2(), flags=FLAGS)
    ordem = [c["chave"] for c in g["colunas"]]
    inexplicadas = []
    for pg in g["paginas"]:
        n = pg["page_number"]
        for c in ordem:
            if f"{c}_p{n}" in g["celulas"] or c not in pg["aplicaveis"]:
                continue
            inexplicadas.append(f"{c}_p{n}")
    assert inexplicadas == []


# ── a LP com editorial tem juiz ────────────────────────────────────────────

def test_lp_com_editorial_tem_juiz_no_fluxo_atual():
    assert "judge" in mz.aplicaveis_da_pagina("LP", tem_editorial=True)
    assert "judge" not in mz.aplicaveis_da_pagina("LP", tem_editorial=False)


def test_a_mascara_do_run_le_o_editorial_do_plano():
    estado = {"plan": _plano(lp_editorial=True), "step_status": {"judge_p1": _ok(0.02)}}
    g = mz.montar(estado, flags=FLAGS)
    assert "judge" in g["paginas"][0]["aplicaveis"]

    sem = {"plan": _plano(lp_editorial=False), "step_status": {}}
    g2 = mz.montar(sem, flags=FLAGS)
    assert "judge" not in g2["paginas"][0]["aplicaveis"]


def test_celula_que_existe_nunca_e_pintada_de_nao_se_aplica():
    """Se o motor gravou o passo, ele rodou — e pode ter custado. A máscara pode
    explicar AUSÊNCIA; ela não pode esconder uma célula que existe."""
    estado = {"plan": _plano(lp_editorial=False), "step_status": {"judge_p1": _ok(0.02)}}
    g = mz.montar(estado, flags=FLAGS)
    assert "judge" in g["paginas"][0]["aplicaveis"]


# ── a flag chega à matriz pelo worker ──────────────────────────────────────

def test_o_worker_leva_a_flag_do_perfil_para_a_matriz(tmp_path):
    """O perfil é a verdade de runtime do funil (como o `--publish` é para a
    publicação): se ele ligou o v2, a grade nasce com as colunas do v2."""
    from app.redator import worker

    (tmp_path / "config.yaml").write_text("run:\n  widgets_enabled: true\n", encoding="utf-8")
    ligada = worker._flags_do_run(tmp_path, True, {"editorial_v2": True})
    assert ligada["editorial_v2"] is True
    assert ligada["widgets_enabled"] is True and ligada["publish"] is True

    padrao = worker._flags_do_run(tmp_path, True, {"site": {}})
    assert not padrao.get("editorial_v2")
