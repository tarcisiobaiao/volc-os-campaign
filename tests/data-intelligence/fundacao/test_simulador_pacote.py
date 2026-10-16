"""Simulator Lab — pacote de datasets: manifesto, hashes, tamanho e sincronia com o código."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from volc_dil.contracts.fingerprint import sha256_arquivo
from volc_dil.fundacao.simulador import NOMES
from volc_dil.fundacao.simulador.pacote import conteudo_cenario, gerar_pacote, sha256_de_bytes

RAIZ = Path(__file__).resolve().parents[3]
PACOTE = RAIZ / "experiments" / "data-intelligence-lab" / "results" / "fundacao" / "simulador"
SRC = RAIZ / "experiments" / "data-intelligence-lab" / "src" / "volc_dil" / "fundacao" / "simulador"
LIMITE_BYTES = 50 * 1024 * 1024


def test_gerar_pacote_em_diretorio_temporario(tmp_path, monkeypatch):
    import volc_dil.fundacao.simulador.pacote as pac

    monkeypatch.setattr(pac, "TAMANHO_PACOTE", (3, 4))
    manif = gerar_pacote(tmp_path, 7, ["estavel", "moeda_misturada"])
    assert (tmp_path / "MANIFEST.json").exists()
    for rel, meta in manif["arquivos"].items():
        assert sha256_arquivo(str(tmp_path / rel)) == meta["sha256"]
    for nome in ("estavel", "moeda_misturada"):
        linhas = (tmp_path / nome / "observacoes.jsonl").read_text(encoding="utf-8").splitlines()
        gab = (tmp_path / nome / "gabarito.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(linhas) == len(gab) > 0
        primeiro = json.loads(linhas[0])
        assert primeiro["natureza"] == "sintetico" and "valor" in primeiro and "available_at" in primeiro
        cen = json.loads((tmp_path / nome / "cenario.json").read_text(encoding="utf-8"))
        assert cen["seed"] == 7 and cen["parametros"]["nome"] == nome
    assert manif["seed"] == 7 and len(manif["fingerprint"]) == 64


@pytest.mark.skipif(not (PACOTE / "MANIFEST.json").exists(), reason="pacote ainda não gerado")
def test_pacote_versionado_completo_pequeno_e_em_sincronia_com_o_codigo():
    manif = json.loads((PACOTE / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manif["cenarios"] == list(NOMES)
    assert manif["bytes_total"] < LIMITE_BYTES
    for rel, meta in manif["arquivos"].items():
        assert sha256_arquivo(str(PACOTE / rel)) == meta["sha256"], rel
    # o pacote foi gerado pelo código atual: um cenário regenerado bate byte a byte
    for arq, dados in conteudo_cenario("zero_falso", manif["seed"]).items():
        assert sha256_de_bytes(dados) == manif["arquivos"][f"zero_falso/{arq}"]["sha256"], arq


def test_modulo_sem_rede_sem_segredo():
    proibidos = {"socket", "urllib", "http", "requests", "httpx", "subprocess", "ftplib", "smtplib", "aiohttp"}
    for py in SRC.glob("*.py"):
        texto = py.read_text(encoding="utf-8")
        arvore = ast.parse(texto)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                assert not {a.name.split(".")[0] for a in no.names} & proibidos, py.name
            elif isinstance(no, ast.ImportFrom) and no.module:
                assert no.module.split(".")[0] not in proibidos, py.name
            elif isinstance(no, ast.Call) and isinstance(no.func, ast.Name):
                assert no.func.id not in {"eval", "exec", "__import__"}, py.name
        for marca in (".env", "os.environ", "getenv", "importlib", "SERVICE_ROLE"):
            assert marca not in texto, (py.name, marca)
