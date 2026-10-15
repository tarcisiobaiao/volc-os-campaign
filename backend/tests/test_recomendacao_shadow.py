"""Provas herméticas da leitura da recomendação em sombra (contrato v1).

Lê o experimento Senac versionado em `tools/freedom-lab/experimentos/` e
cópias adulteradas em pasta temporária. Nenhuma rede, nenhum Supabase.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.seguranca.identidade import exigir_usuario
from app.trafego import recomendacao_shadow as rs

SENAC = "24278665189"
URL = f"/api/trafego/recomendacao-shadow/{SENAC}"


def _copia(tmp_path: Path) -> Path:
    destino = tmp_path / "experimentos" / "senac-shadow-20261015"
    shutil.copytree(rs.RAIZ_PADRAO / "senac-shadow-20261015", destino)
    return destino.parent


def _reassinar(pasta: Path, nome: str) -> None:
    manifesto = json.loads((pasta / "experimento.json").read_text())
    for a in manifesto["artifacts"]:
        if a["path"] == nome:
            a["sha256"] = hashlib.sha256((pasta / nome).read_bytes()).hexdigest()
    (pasta / "experimento.json").write_text(json.dumps(manifesto))


def test_senac_projeta_pausar_sem_execucao_nem_valor():
    corpo = TestClient(app).get(URL).json()
    assert corpo["contrato"] == "recomendacao_shadow.v1"
    assert corpo["direcao"] == "pausar"
    assert corpo["grao"] == "campanha_dia"
    assert corpo["executada"] is False
    assert corpo["valor_sugerido"] is None
    assert corpo["isolamento"] == {
        "chamadas_externas": 0, "mutacoes_executadas": 0, "oferece_aplicar": False,
    }
    assert corpo["origem"]["integridade"] == "coerente_com_manifesto"
    assert corpo["origem"]["experimentos_substituidos"] == []
    assert corpo["janela_madura"]["roas"] == pytest.approx(0.0735)
    assert len(corpo["ressalvas"]) >= 5


def test_roas_nativo_do_google_e_marcado_nao_confiavel():
    nativo = TestClient(app).get(URL).json()["roas_nativo_google"]
    assert nativo["confiavel"] is False
    assert nativo["valor_conversao_total"] == 2380.0
    assert "fixo em 10" in nativo["motivo"]


def test_ausencia_continua_ausencia_no_grao_campanha_dia():
    dias = {d["data"]: d for d in TestClient(app).get(URL).json()["dias"]}
    # Sem custo e sem receita: nada vira zero.
    assert dias["2026-09-23"]["custo_brl"] is None
    assert dias["2026-09-23"]["receita_brl"] is None
    assert dias["2026-09-23"]["contribuicao_brl"] is None
    # Custo sem receita: a contribuição não existe (não é -custo).
    assert dias["2026-10-01"]["custo_brl"] == 0.33
    assert dias["2026-10-01"]["receita_brl"] is None
    assert dias["2026-10-01"]["contribuicao_brl"] is None
    assert dias["2026-10-14"]["maduro"] is False


def test_campanha_sem_experimento_e_404_e_id_malformado_e_422():
    cliente = TestClient(app)
    ausente = cliente.get("/api/trafego/recomendacao-shadow/1234567")
    assert ausente.status_code == 404
    assert ausente.json()["detail"]["codigo"] == "sem_recomendacao_shadow"
    assert cliente.get("/api/trafego/recomendacao-shadow/abc").status_code == 422


def test_artefato_adulterado_e_409_e_nao_some(tmp_path, monkeypatch):
    raiz = _copia(tmp_path)
    csv = raiz / "senac-shadow-20261015" / "transformacao.csv"
    csv.write_text(csv.read_text().replace("34.658206", "3.0"))
    monkeypatch.setattr(rs, "RAIZ_PADRAO", raiz)
    resposta = TestClient(app).get(URL)
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "integridade_quebrada"
    assert "transformacao.csv" in resposta.json()["detail"]["mensagem"]


def test_direcao_fora_do_vocabulario_vira_evidencia_insuficiente(tmp_path, monkeypatch):
    raiz = _copia(tmp_path)
    pasta = raiz / "senac-shadow-20261015"
    resultado = json.loads((pasta / "resultado.json").read_text())
    resultado["recomendacao"]["direcao"] = "dobrar"
    (pasta / "resultado.json").write_text(json.dumps(resultado))
    _reassinar(pasta, "resultado.json")
    monkeypatch.setattr(rs, "RAIZ_PADRAO", raiz)
    corpo = TestClient(app).get(URL).json()
    assert corpo["direcao"] == "evidencia_insuficiente"
    assert "dobrar" in corpo["motivos"][0]


def test_endpoint_recusa_requisicao_sem_identidade():
    dublê = app.dependency_overrides.get(exigir_usuario)

    def sem_identidade():
        raise HTTPException(status_code=401, detail="Credencial ausente")

    app.dependency_overrides[exigir_usuario] = sem_identidade
    try:
        assert TestClient(app).get(URL).status_code == 401
    finally:
        if dublê is not None:
            app.dependency_overrides[exigir_usuario] = dublê
        else:
            app.dependency_overrides.pop(exigir_usuario, None)


# ── ciclo corretivo 2 (revisão na nuvem de 15/10) ─────────────────────────


def _segundo_experimento(raiz: Path, nome: str, *, as_of: str, direcao: str) -> Path:
    """Copia o Senac para `nome`, troca `as_of` e direção e reassina o manifesto."""
    pasta = raiz / nome
    shutil.copytree(raiz / "senac-shadow-20261015", pasta)
    resultado = json.loads((pasta / "resultado.json").read_text())
    resultado["as_of"] = as_of
    resultado["recomendacao"]["direcao"] = direcao
    (pasta / "resultado.json").write_text(json.dumps(resultado))
    _reassinar(pasta, "resultado.json")
    return pasta


def test_dois_experimentos_da_mesma_campanha_vence_o_as_of_mais_recente(tmp_path):
    # Defeito 1: a ordem do nome da pasta decidia, e a recomendação velha vencia.
    # O nome mais novo aqui ordena ANTES do antigo, para o teste não passar por
    # coincidência de ordem alfabética.
    raiz = _copia(tmp_path)
    _segundo_experimento(raiz, "a-senac-reavaliado", as_of="2026-11-01", direcao="manter")
    lida = rs.ler(SENAC, raiz=raiz)
    assert lida["as_of"] == "2026-11-01"
    assert lida["direcao"] == "manter"
    assert lida["origem"]["experimento_id"] == "a-senac-reavaliado"
    assert lida["origem"]["experimentos_substituidos"] == ["senac-shadow-20261015"]


def test_dois_experimentos_com_o_mesmo_as_of_sao_ambiguos_e_nao_escolhidos(tmp_path, monkeypatch):
    raiz = _copia(tmp_path)
    _segundo_experimento(raiz, "senac-shadow-20261015-b", as_of="2026-10-15", direcao="manter")
    monkeypatch.setattr(rs, "RAIZ_PADRAO", raiz)
    resposta = TestClient(app).get(URL)
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "experimentos_ambiguos"


def test_resultado_json_corrompido_e_integridade_e_nao_ausencia(tmp_path, monkeypatch):
    # Defeito 2: o `continue` antes da conferência fazia o corrompido sumir.
    raiz = _copia(tmp_path)
    (raiz / "senac-shadow-20261015" / "resultado.json").write_text('{"campanha": "2427')
    monkeypatch.setattr(rs, "RAIZ_PADRAO", raiz)
    resposta = TestClient(app).get(URL)
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "integridade_quebrada"
    assert "resultado.json" in resposta.json()["detail"]["mensagem"]


def test_resultado_ilegivel_com_sha_reassinado_tambem_e_integridade(tmp_path):
    # Quem reassina o manifesto passa no sha256, mas um JSON ilegível continua
    # sendo artefato quebrado, nunca ausência.
    raiz = _copia(tmp_path)
    pasta = raiz / "senac-shadow-20261015"
    (pasta / "resultado.json").write_text("não é json")
    _reassinar(pasta, "resultado.json")
    with pytest.raises(rs.IntegridadeQuebrada, match="resultado.json"):
        rs.ler(SENAC, raiz=raiz)


def test_experimento_corrompido_de_outra_campanha_impede_afirmar_ausencia(tmp_path):
    # Um resultado corrompido não diz de que campanha é; então ninguém pode
    # afirmar "nenhum experimento olhou esta campanha" enquanto ele existir.
    raiz = _copia(tmp_path)
    (raiz / "senac-shadow-20261015" / "resultado.json").write_text("{")
    with pytest.raises(rs.IntegridadeQuebrada):
        rs.ler("1234567", raiz=raiz)


def test_raiz_inexistente_e_fonte_indisponivel_e_nao_ausencia(tmp_path, monkeypatch):
    # Defeito 3: o deploy do backend só leva `app/**`; sem a pasta de
    # experimentos, toda campanha virava "nenhum experimento".
    monkeypatch.setattr(rs, "RAIZ_PADRAO", tmp_path / "nao-existe")
    resposta = TestClient(app).get(URL)
    assert resposta.status_code == 503
    assert resposta.json()["detail"]["codigo"] == "fonte_indisponivel"


def test_raiz_sem_nenhum_experimento_e_fonte_indisponivel(tmp_path):
    vazia = tmp_path / "experimentos"
    vazia.mkdir()
    with pytest.raises(rs.FonteIndisponivel):
        rs.ler(SENAC, raiz=vazia)


def test_raiz_pode_vir_do_ambiente(tmp_path, monkeypatch):
    raiz = _copia(tmp_path)
    monkeypatch.setenv("VOLC_EXPERIMENTOS_SHADOW_DIR", str(raiz))
    monkeypatch.setattr(rs, "RAIZ_PADRAO", tmp_path / "nao-existe")
    assert rs.ler(SENAC)["origem"]["experimento_id"] == "senac-shadow-20261015"
