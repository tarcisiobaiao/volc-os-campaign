"""A carteira em sombra (W13) lida pela mesma porta da tela do W7.

O lote é gerado aqui mesmo pelo motor do Freedom Lab, a partir de dados
sintéticos (sem rede, sem Supabase), e lido de volta por
`recomendacao_shadow.listar/ler` e pela rota. Prova o contrato entre os dois
lados: o que o motor grava, a tela lê sem adaptação.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.trafego import recomendacao_shadow as rs

sys.path.insert(0, str(Path(rs.__file__).resolve().parents[3] / "tools" / "freedom-lab" / "src"))
from volc_lab.sombra_carteira import aplicacao  # noqa: E402
from volc_lab.sombra_carteira.portas import Leitura  # noqa: E402

CONTA = "1112223334"
HOJE = date(2026, 10, 15)
LIDO = "2026-10-15T12:00:00Z"
RUIM, SEM_CAMBIO = "900000000001", "900000000003"
SENAC = "24278665189"


def _custo(cid, d, micros, cliques=40):
    return {"customer_id": CONTA, "campaign_id": cid, "metric_date": d.isoformat(), "segmentos": {},
            "custo_micros": micros, "cliques": cliques, "currency_code": "BRL", "janela_fechada": True,
            "campaign_name": f"camp {cid[-1]}", "campaign_status": "ENABLED", "valor_conversoes": 10.0,
            "colhida_em": LIDO, "origem_janela": "backfill"}


def _receita(cid, d, usd, modo="anterior"):
    return {"fonte": "joinads", "chave": {"date": d.isoformat(), "utm_campaign_value": cid,
                                          "joinads_domain": "a.com.br"},
            "data_referencia": d.isoformat(), "moeda": "USD", "receita": usd,
            "receita_brl": round(usd * 5.4, 4) if modo == "anterior" else None,
            "cambio_modo": modo, "cambio_taxa": 5.4 if modo == "anterior" else None,
            "cambio_defasagem_dias": 1 if modo == "anterior" else 40, "coletado_em": LIDO, "removida": False}


class _Fonte:
    def __init__(self, c, r):
        self.c, self.r = c, r

    def custo_campanha_dia(self, conta, inicio, fim):
        return Leitura(tuple(self.c), LIDO, "teste")

    def receita_vigente(self, inicio, fim):
        return Leitura(tuple(self.r), LIDO, "teste")


@pytest.fixture()
def raiz(tmp_path, monkeypatch):
    destino = tmp_path / "experimentos"
    c, r = [], []
    for i in range(1, 21):
        d = HOJE - timedelta(days=i)
        c += [_custo(RUIM, d, 30_000_000), _custo(SEM_CAMBIO, d, 10_000_000)]
        r += [_receita(RUIM, d, 0.30), _receita(SEM_CAMBIO, d, 5.0, modo="defasada")]
    f = _Fonte(c, r)
    aplicacao.gerar_lote(CONTA, f, f, destino, base_ref="a8059ba0", hoje=HOJE)
    # O experimento Senac (anterior ao motor) convive na mesma pasta.
    shutil.copytree(rs.RAIZ_PADRAO / "senac-shadow-20261015", destino / "senac-shadow-20261015")
    monkeypatch.setenv(rs.VARIAVEL_RAIZ, str(destino))
    return destino


def test_carteira_lista_todas_as_campanhas_sem_acao(raiz):
    corpo = TestClient(app).get("/api/trafego/recomendacao-shadow").json()
    assert corpo["contrato"] == "carteira_shadow.v1"
    por_id = {l["campanha_externa"]: l for l in corpo["campanhas"]}
    assert set(por_id) == {RUIM, SEM_CAMBIO, SENAC}
    assert por_id[RUIM]["direcao"] == "pausar"
    assert por_id[RUIM]["estado_dado"] == "completo"
    assert por_id[RUIM]["campanha_nome"] == "camp 1"
    assert por_id[SENAC]["direcao"] == "pausar"
    assert por_id[SENAC]["estado_dado"] is None          # anterior ao motor: não declara
    for linha in corpo["campanhas"]:
        assert linha["executada"] is False and linha["valor_sugerido"] is None
    assert corpo["isolamento"] == {"chamadas_externas": 0, "mutacoes_executadas": 0, "oferece_aplicar": False}


def test_sem_cambio_chega_na_tela_como_sem_dado_e_nunca_zero(raiz):
    linha = {l["campanha_externa"]: l for l in rs.listar()["campanhas"]}[SEM_CAMBIO]
    assert linha["estado_dado"] == "sem_dado"
    assert linha["direcao"] == "evidencia_insuficiente"
    assert linha["janela_madura"]["roas"] is None
    assert linha["janela_madura"]["receita_brl"] is None
    detalhe = TestClient(app).get(f"/api/trafego/recomendacao-shadow/{SEM_CAMBIO}").json()
    assert detalhe["estado_dado"] == "sem_dado"
    assert all(d["receita_brl"] is None for d in detalhe["dias"])
    assert all(d["contribuicao_brl"] is None for d in detalhe["dias"])


def test_detalhe_de_cada_campanha_do_lote_e_lido_pela_rota_do_w7(raiz):
    for cid in (RUIM, SEM_CAMBIO):
        corpo = TestClient(app).get(f"/api/trafego/recomendacao-shadow/{cid}").json()
        assert corpo["contrato"] == "recomendacao_shadow.v1"
        assert corpo["origem"]["integridade"] == "coerente_com_manifesto"
        assert corpo["origem"]["replay_sem_api"] is True
        assert corpo["executada"] is False and corpo["valor_sugerido"] is None
        assert corpo["roas_nativo_google"]["confiavel"] is False
        assert len(corpo["dias"]) == 20


def test_resultado_adulterado_derruba_a_carteira_com_409(raiz):
    alvo = raiz / f"gads-{RUIM}-sombra-20261015" / "resultado.json"
    doc = json.loads(alvo.read_text())
    doc["recomendacao"]["direcao"] = "aumentar"
    alvo.write_text(json.dumps(doc))
    resp = TestClient(app).get("/api/trafego/recomendacao-shadow")
    assert resp.status_code == 409
    assert resp.json()["detail"]["codigo"] == "integridade_quebrada"


def test_empate_de_as_of_vira_linha_ambigua_sem_direcao(raiz):
    # Um segundo experimento da mesma campanha, reassinado, com o mesmo as_of.
    copia = raiz / "gads-copia-manual-20261015"
    shutil.copytree(raiz / f"gads-{RUIM}-sombra-20261015", copia)
    corpo = TestClient(app).get("/api/trafego/recomendacao-shadow").json()
    linha = {l["campanha_externa"]: l for l in corpo["campanhas"]}[RUIM]
    assert linha["situacao"] == "ambigua" and linha["direcao"] is None
    assert {l["situacao"] for l in corpo["campanhas"] if l["campanha_externa"] != RUIM} == {"lida"}


def test_pasta_ausente_e_503(tmp_path, monkeypatch):
    monkeypatch.setenv(rs.VARIAVEL_RAIZ, str(tmp_path / "nao-existe"))
    resp = TestClient(app).get("/api/trafego/recomendacao-shadow")
    assert resp.status_code == 503
    assert resp.json()["detail"]["codigo"] == "fonte_indisponivel"


def test_manifesto_do_lote_confere_cada_experimento(raiz):
    lote = json.loads(next((raiz / "_lotes").glob("*.json")).read_text())
    assert lote["resumo"]["campanhas"] == 2
    for item in lote["experimentos"]:
        manifesto = raiz / item["experimento_id"] / "experimento.json"
        assert hashlib.sha256(manifesto.read_bytes()).hexdigest() == item["manifesto_sha256"]
