"""A carteira em sombra (W13) lida pela mesma porta da tela do W7.

O lote vem de `tests/fixtures/carteira_shadow/`, gravado pelo motor do Freedom
Lab a partir de dados sintéticos (sem rede, sem Supabase). O backend NÃO importa
o motor: `volc_lab` exige jsonschema, que só existe no venv do lab. O contrato
entre os dois lados continua provado, do lado do lab: o teste
`test_fixture_da_carteira_no_backend_e_o_que_o_motor_grava` regenera o lote e
exige os mesmos bytes. Gerador: `tools/freedom-lab/tests/gerar_fixture_carteira_backend.py`.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.trafego import recomendacao_shadow as rs

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "carteira_shadow"
RUIM, SEM_CAMBIO = "900000000001", "900000000003"
SENAC = "24278665189"


@pytest.fixture()
def raiz(tmp_path, monkeypatch):
    # Cópia: vários testes adulteram arquivos, e a fixture versionada não muda.
    destino = tmp_path / "experimentos"
    shutil.copytree(FIXTURE, destino)
    # O experimento Senac (anterior ao motor) convive na mesma pasta.
    shutil.copytree(rs.RAIZ_PADRAO / "senac-shadow-20261015", destino / "senac-shadow-20261015")
    monkeypatch.setenv(rs.VARIAVEL_RAIZ, str(destino))
    return destino


def test_backend_nao_importa_o_motor_do_lab():
    texto = Path(__file__).read_text()
    assert "import " + "volc_lab" not in texto and "from " + "volc_lab" not in texto


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
    alvo = raiz / f"gads-{RUIM}-sombra-20261015t120000z" / "resultado.json"
    doc = json.loads(alvo.read_text())
    doc["recomendacao"]["direcao"] = "aumentar"
    alvo.write_text(json.dumps(doc))
    resp = TestClient(app).get("/api/trafego/recomendacao-shadow")
    assert resp.status_code == 409
    assert resp.json()["detail"]["codigo"] == "integridade_quebrada"


def test_empate_de_as_of_vira_linha_ambigua_sem_direcao(raiz):
    # Um segundo experimento da mesma campanha, reassinado, com o mesmo as_of.
    copia = raiz / "gads-copia-manual-20261015"
    shutil.copytree(raiz / f"gads-{RUIM}-sombra-20261015t120000z", copia)
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


def _reassinar(pasta: Path, nome: str) -> None:
    manifesto = json.loads((pasta / "experimento.json").read_text())
    for a in manifesto["artifacts"]:
        if a["path"] == nome:
            a["sha256"] = hashlib.sha256((pasta / nome).read_bytes()).hexdigest()
    (pasta / "experimento.json").write_text(json.dumps(manifesto))


def test_experimento_integro_sem_as_of_de_outra_campanha_nao_derruba_a_leitura_w7(raiz):
    """Regressão apontada na revisão: antes do W13 a leitura por campanha
    filtrava a campanha antes de interpretar o as_of."""
    outro = raiz / f"gads-{SEM_CAMBIO}-sombra-20261015t120000z"
    doc = json.loads((outro / "resultado.json").read_text())
    del doc["as_of"]
    (outro / "resultado.json").write_text(json.dumps(doc))
    _reassinar(outro, "resultado.json")
    assert TestClient(app).get(f"/api/trafego/recomendacao-shadow/{SENAC}").json()["direcao"] == "pausar"
    # Na carteira, só a campanha ilegível perde a direção.
    por_id = {l["campanha_externa"]: l for l in rs.listar()["campanhas"]}
    assert por_id[SEM_CAMBIO]["situacao"] == "ilegivel" and por_id[SEM_CAMBIO]["direcao"] is None
    assert por_id[RUIM]["direcao"] == "pausar"


def test_experimento_de_outro_tipo_sem_campanha_fica_fora_da_carteira(raiz):
    alheio = raiz / "ortools-alocacao-teste"
    alheio.mkdir()
    (alheio / "resultado.json").write_text(json.dumps({"as_of": "2026-10-15", "metrica": 1}))
    (alheio / "experimento.json").write_text(json.dumps({"artifacts": [
        {"path": "resultado.json", "sha256": hashlib.sha256((alheio / "resultado.json").read_bytes()).hexdigest()}]}))
    ids = {l["campanha_externa"] for l in rs.listar()["campanhas"]}
    assert ids == {RUIM, SEM_CAMBIO, SENAC}


def test_linha_velha_e_marcada_defasada(raiz):
    por_id = {l["campanha_externa"]: l for l in rs.listar()["campanhas"]}
    assert por_id[RUIM]["defasada"] is False
    # Senac: as_of 2026-10-15 (meia-noite) contra 12:00 do lote, menos de 2 dias.
    assert por_id[SENAC]["defasada"] is False
    alvo = raiz / f"gads-{RUIM}-sombra-20261015t120000z"
    doc = json.loads((alvo / "resultado.json").read_text())
    doc["as_of"] = "2026-10-01T12:00:00+00:00"
    (alvo / "resultado.json").write_text(json.dumps(doc))
    _reassinar(alvo, "resultado.json")
    por_id = {l["campanha_externa"]: l for l in rs.listar()["campanhas"]}
    assert por_id[RUIM]["defasada"] is True


def test_artefato_trocado_depois_da_conferencia_nao_e_o_interpretado(raiz, monkeypatch):
    """TOCTOU (revisor de nuvem 2): o que é interpretado são os bytes conferidos.
    Simula uma troca do arquivo logo depois da primeira leitura; antes do ciclo
    2 o arquivo era reaberto para o JSON/CSV e a troca passava."""
    pasta = raiz / f"gads-{RUIM}-sombra-20261015t120000z"
    original = Path.read_bytes
    trocados: set[str] = set()

    def ler_e_trocar(self):
        bruto = original(self)
        if self.parent == pasta and self.name in ("resultado.json", "transformacao.csv") \
                and self.name not in trocados:
            trocados.add(self.name)
            if self.name == "resultado.json":
                doc = json.loads(bruto)
                doc["recomendacao"]["direcao"] = "aumentar"
                self.write_text(json.dumps(doc))
            else:
                self.write_text("date,custo_brl,receita_brl\n2026-10-14,1,99999\n")
        return bruto

    monkeypatch.setattr(Path, "read_bytes", ler_e_trocar)
    corpo = rs.ler(RUIM)
    assert trocados == {"resultado.json", "transformacao.csv"}
    assert corpo["direcao"] == "pausar"
    assert len(corpo["dias"]) == 20 and all(d["receita_brl"] != 99999 for d in corpo["dias"])
    # Na leitura seguinte, a troca é vista e recusada como integridade quebrada.
    monkeypatch.setattr(Path, "read_bytes", original)
    with pytest.raises(rs.IntegridadeQuebrada):
        rs.ler(RUIM)


def test_carteira_inteira_velha_contra_o_relogio(raiz):
    from datetime import datetime
    em_dia = rs.listar(agora=datetime(2026, 10, 16, 9, 0))
    assert em_dia["carteira_defasada"] is False
    assert em_dia["leitura_mais_nova"] == "2026-10-15T12:00:00"
    # A agenda parou: todas as linhas têm a mesma idade, nenhuma é "defasada"
    # em relação às outras, mas a carteira está velha.
    parada = rs.listar(agora=datetime(2026, 10, 25, 9, 0))
    assert parada["carteira_defasada"] is True
    assert not any(l["defasada"] for l in parada["campanhas"])
