from __future__ import annotations

import importlib.util
from pathlib import Path


CAMINHO = Path(__file__).resolve().parents[1] / "verificar_autoridade_unica_adspower.py"
SPEC = importlib.util.spec_from_file_location("autoridade_unica_adspower", CAMINHO)
assert SPEC and SPEC.loader
MODULO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULO)


def test_arvore_atual_tem_autoridade_unica():
    assert MODULO.conferir() == []


def test_pacote_removido_falha(tmp_path):
    (tmp_path / "backend/app/asset_vault/broker").mkdir(parents=True)
    (tmp_path / "backend/app/asset_vault/broker/cli.py").write_text(
        "print('segundo broker')\n", encoding="utf-8"
    )
    (tmp_path / "tools/adspower-broker").mkdir(parents=True)
    erros = MODULO.conferir(tmp_path)
    assert any("backend/app/asset_vault/broker" in erro for erro in erros)


def test_cliente_local_api_fora_da_fronteira_falha(tmp_path):
    (tmp_path / "tools/adspower-broker").mkdir(parents=True)
    invasor = tmp_path / "backend/app/outro/cliente.py"
    invasor.parent.mkdir(parents=True)
    invasor.write_text(
        'url = "http://127.0.0.1:50325/api/v1/browser/start"\n'
        'headers = {"Authorization": "Bearer x"}\n',
        encoding="utf-8",
    )
    erros = MODULO.conferir(tmp_path)
    assert any("cliente.py" in erro and "/api/v1/browser/" in erro for erro in erros)


def test_infraestrutura_volc_nao_pode_falar_com_adspower(tmp_path):
    (tmp_path / "tools/adspower-broker").mkdir(parents=True)
    infra = tmp_path / "backend/app/visual_proof/infraestrutura.py"
    infra.parent.mkdir(parents=True)
    infra.write_text(
        'VAR_ENDERECO = "VOLC_BROKER_URL"\n'
        'pedido = "/api/v1/browser/start"\n',
        encoding="utf-8",
    )
    erros = MODULO.conferir(tmp_path)
    assert any("infraestrutura.py" in erro and "Local API" in erro for erro in erros)


def test_hermes_sem_supersessao_falha(tmp_path):
    (tmp_path / "tools/adspower-broker").mkdir(parents=True)
    doc = tmp_path / "docs/closure/hermes-asset-vault-organic-access-v1/HANDOFF.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "O sidecar vive em backend/app/asset_vault/broker/ e é a autoridade.\n",
        encoding="utf-8",
    )
    erros = MODULO.conferir(tmp_path)
    assert any("supersessão" in erro or "supersessao" in erro.lower() for erro in erros)


def test_hermes_com_supersessao_passa_no_marcador(tmp_path):
    (tmp_path / "tools/adspower-broker").mkdir(parents=True)
    doc = tmp_path / "docs/closure/hermes-asset-vault-organic-access-v1/HANDOFF.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "> **SUPERSESSÃO.** backend/app/asset_vault/broker/ é "
        "CANDIDATO NÃO INTEGRADO/SUPERADO.\n",
        encoding="utf-8",
    )
    erros = [e for e in MODULO.conferir(tmp_path) if "hermes-asset-vault" in e]
    assert erros == []
