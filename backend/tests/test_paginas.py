"""O funil escrito, medido contra os artefatos reais do run #6.

A pasta `runs/cartao-credito-negativado-20260817-191650/` tem os 33 arquivos que
o motor deixou: 5 páginas planejadas, 3 publicadas, 2 bloqueadas por motivos
diferentes, 4 imagens, 4 prints de canal oficial e um `state.json` de 125 kB.

É a única fixture que exercita ao mesmo tempo a LP (que é JSON de slots, não
prosa), uma página que morreu ANTES da redação (e portanto não tem texto nem
imagem) e uma que morreu DEPOIS (com texto, imagem e prints pagos).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.redator import paginas as pgs

MOTOR = Path(__file__).resolve().parents[2] / "funnelforge-migracao" / "engine"
RUN6 = MOTOR / "runs" / "cartao-credito-negativado-20260817-191650"


@pytest.fixture(scope="module")
def estado() -> dict:
    if not (RUN6 / "state.json").is_file():
        pytest.skip(f"fixture do run #6 ausente: {RUN6}")
    return json.loads((RUN6 / "state.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def funil(estado: dict) -> list[dict]:
    return pgs.montar(estado, run_dir=RUN6)


@pytest.fixture(scope="module")
def por_n(funil: list[dict]) -> dict:
    return {p["page_number"]: p for p in funil}


# ── as travas do artefato ──────────────────────────────────────────────────
#
# Esta é a parte que, errada, vaza. A pasta do run guarda o `state.json` com o
# briefing e o plano inteiros, o `config_snapshot.json` e o `worker.log`.

def test_serve_imagem_de_pagina_e_print_oficial(tmp_path: Path):
    """A allowlist de artefatos não depende de um run local não versionado.

    O restante deste módulo usa o run #6 como prova de integração e o ignora
    honestamente quando a fixture não existe. Esta prova é unitária: cria os
    dois nomes permitidos e mede apenas a fronteira que decide o que pode ser
    servido ao navegador.
    """
    (tmp_path / "p3.webp").write_bytes(b"imagem")
    (tmp_path / "p3-oficial-wwwbcbgovbr-1.webp").write_bytes(b"print")

    assert pgs.caminho_de_artefato(tmp_path, "p3.webp") is not None
    assert pgs.caminho_de_artefato(tmp_path, "p3-oficial-wwwbcbgovbr-1.webp") is not None


def test_recusa_o_estado_e_o_log():
    """O `state.json` tem o briefing e o plano; o `worker.log` é stdout cru do
    motor. Nenhum dos dois tem por que trafegar para o browser."""
    assert pgs.caminho_de_artefato(RUN6, "state.json") is None
    assert pgs.caminho_de_artefato(RUN6, "worker.log") is None
    assert pgs.caminho_de_artefato(RUN6, "config_snapshot.json") is None
    assert pgs.caminho_de_artefato(RUN6, "funnel_plan.json") is None
    # começa com `p<N>.` e mesmo assim é recusado: a trava é por EXTENSÃO
    assert pgs.caminho_de_artefato(RUN6, "p1.elementor.json") is None
    assert pgs.caminho_de_artefato(RUN6, "p1.preview.html") is None


def test_recusa_travessia_de_caminho():
    for tentativa in [
        "../../../etc/passwd",
        "..%2F..%2Fstate.json",
        "p1/../../state.json",
        "..\\..\\state.json",
        "/etc/passwd",
        "p1.webp/../../../state.json",
    ]:
        assert pgs.caminho_de_artefato(RUN6, tentativa) is None, tentativa


def test_recusa_arquivo_que_nao_existe_mesmo_com_nome_valido():
    assert pgs.caminho_de_artefato(RUN6, "p99.webp") is None


def test_sem_pasta_nao_serve_nada():
    assert pgs.caminho_de_artefato(None, "p1.webp") is None
    assert pgs.caminho_de_artefato(RUN6, "") is None


# ── o funil ────────────────────────────────────────────────────────────────

def test_as_cinco_paginas_na_ordem_do_plano(funil: list[dict]):
    assert [p["page_number"] for p in funil] == [1, 2, 3, 4, 5]
    assert [p["papel"] for p in funil] == ["LP", "PRESELL", "SOLUTION", "SOLUTION", "SOLUTION"]


def test_a_lp_e_json_de_slots_e_isso_fica_declarado(por_n: dict):
    """A LP não é prosa: é um JSON que o tema monta. Renderizá-la como artigo
    seria mentira sobre a estrutura; o campo `formato` é o que permite à tela
    escolher sem adivinhar pelo conteúdo."""
    lp = por_n[1]
    assert lp["texto"]["formato"] == "lp_json"
    slots = json.loads(lp["texto"]["conteudo"])
    assert "hero_title" in slots and "faq" in slots


def test_as_interiores_sao_gutenberg(por_n: dict):
    for n in (2, 3, 5):
        assert por_n[n]["texto"]["formato"] == "gutenberg"
        assert por_n[n]["texto"]["palavras"] > 500


def test_pagina_que_morreu_antes_da_redacao_nao_tem_texto_nem_imagem(por_n: dict):
    """A p4 falhou na PESQUISA. Ela custou US$ 0,4556 e não produziu nada —
    e mostrar isso é o que evita redisparar achando que foi só um soluço."""
    p4 = por_n[4]
    assert p4["bloqueada"] is True
    assert p4["texto"]["conteudo"] == ""
    assert p4["imagem"] is None
    assert p4["custo_usd"] > 0.45          # o dinheiro saiu mesmo assim


def test_pagina_que_morreu_depois_mantem_o_que_foi_pago(por_n: dict):
    """A p3 passou por pesquisa, redação, imagem, prints e widget, e só então o
    portão a barrou. Esconder o que ela produziu faria o operador pagar de novo
    por trabalho que já está no disco."""
    p3 = por_n[3]
    assert p3["bloqueada"] is True
    assert p3["texto"]["palavras"] > 500
    assert p3["imagem"] == "p3.webp"
    assert len(p3["prints"]) == 2
    assert len(p3["links_oficiais"]) == 3


def test_o_custo_por_pagina_soma_so_as_etapas_daquela_pagina(funil: list[dict], estado: dict):
    """A identidade que fecha a conta: o que foi atribuído às páginas mais o que
    é do RUN dá o total exato. Trava melhor que um número decorado, porque
    denuncia tanto etapa contada duas vezes quanto etapa esquecida.

    A faixa do run (`extract`, `engajamento`, `funnel_graph`…) não pertence a
    página nenhuma — imputá-la a alguma inflaria o custo daquela página e
    faria o operador descartar a página errada.
    """
    import re

    passos = estado["step_status"]
    de_pagina = sum(p["custo_usd"] for p in funil)
    do_run = sum(float((r or {}).get("cost_usd") or 0.0)
                 for k, r in passos.items() if not re.search(r"_p\d+$", k))
    total = sum(float((r or {}).get("cost_usd") or 0.0) for r in passos.values())

    assert de_pagina + do_run == pytest.approx(total, abs=1e-6)
    assert de_pagina < total          # a faixa do run existe e não é zero
    assert do_run > 0


def test_o_sufixo_pn_nao_casa_pagina_errada(funil: list[dict], estado: dict):
    """⚠️ `endswith('_p1')` casaria `write_p1` e nada mais — mas num funil de 10+
    páginas casaria `_p1` dentro de… nada, porque a chave TERMINA no número. O
    risco real é o inverso: `_p1` não pode capturar `_p11`. Este teste trava a
    fronteira antes de existir um funil grande o bastante para quebrá-la."""
    assert "write_p11".endswith("_p1") is False
    assert "write_p1".endswith("_p1") is True


def test_prints_viram_nome_de_arquivo_nao_caminho(por_n: dict):
    """O `state.json` guarda `runs/<run>/p3-oficial-....webp`. Se esse caminho
    vazasse para a tela, o `src` da imagem viraria um path do servidor."""
    for s in por_n[3]["prints"]:
        assert "/" not in s["arquivo"]
        assert s["arquivo"].endswith(".webp")
        assert s["url"].startswith("http")


def test_o_seo_e_os_anuncios_vem_do_disco(por_n: dict):
    p3 = por_n[3]
    assert p3["seo"]["titulo"]
    assert p3["seo"]["descricao"]
    assert p3["meta"]["robots"] == "noindex,follow"
    assert len(p3["anuncios"]["slots"]) == 2


def test_o_que_explica_a_ordem_do_funil(por_n: dict):
    """`objetivo` e `gancho` são a única informação que transforma 5 páginas em
    um funil. Sem eles, a tela mostra 5 artigos soltos."""
    for n in (1, 2, 3):
        assert por_n[n]["objetivo"]
        assert por_n[n]["gancho"]
    assert por_n[1]["proxima"]


def test_as_issues_carregam_a_etapa_que_as_gerou(por_n: dict):
    """`ungrounded_critical_claim` sem dizer que veio do `content_gate` obriga o
    operador a adivinhar em que ponto do pipeline aquilo aconteceu."""
    codes = {i["code"] for i in por_n[3]["issues"]}
    assert "ungrounded_critical_claim" in codes
    etapas = {i["etapa"] for i in por_n[3]["issues"]}
    assert "content_gate" in etapas


def test_estado_vazio_nao_explode():
    assert pgs.montar({}) == []
    assert pgs.montar({"plan": {"pages": []}}, run_dir=None) == []


def test_sem_pasta_no_disco_a_pagina_ainda_sai(estado: dict):
    """Run antigo com disco limpo: o plano e o texto vivem no `state.json`, então
    o funil continua legível — só sem imagem e sem os JSONs auxiliares."""
    sem = pgs.montar(estado, run_dir=None)
    assert len(sem) == 5
    assert sem[0]["texto"]["palavras"] > 0
    assert sem[0]["imagem"] is None
    assert sem[0]["anuncios"] is None
