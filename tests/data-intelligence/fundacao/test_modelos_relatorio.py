"""Resultados do Model Lab: RESUMO.md em sincronia com os JSONs, manifesto com hash do código atual,
tamanho total pequeno e pré-registro anterior aos resultados (por histórico do git, quando disponível)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
LAB = RAIZ / "experiments" / "data-intelligence-lab"
RES = LAB / "results" / "fundacao" / "modelos"
SCRIPTS = LAB / "scripts"


def _modulo(nome):
    spec = importlib.util.spec_from_file_location(nome, SCRIPTS / f"{nome}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _jsons():
    return sorted(RES.glob("m*.json"))


@pytest.mark.skipif(not (RES / "RESUMO.md").exists(), reason="resultados ainda não gerados")
def test_resumo_regenera_byte_a_byte():
    rel = _modulo("fundacao_modelos_relatorio")
    assert (RES / "RESUMO.md").read_text(encoding="utf-8") == rel.gerar()


@pytest.mark.skipif(not _jsons(), reason="resultados ainda não gerados")
def test_manifestos_tem_hash_do_codigo_atual_e_natureza_sintetica():
    comum = _modulo("fundacao_modelos_comum")
    for p in _jsons():
        man = json.loads(p.read_text(encoding="utf-8"))["manifesto"]
        assert man["natureza"] == "simulacao_com_seed_sem_dado_real"
        assert man["teto_de_estado"] == "testado com sintético"
        assert man["sha256_codigo"] == comum.sha256_codigo(SCRIPTS / man["script"]), p.name
        assert len(man["seeds"]) >= 3


def test_resultados_pequenos_e_pre_registro_existe():
    assert (RES / "PRE-REGISTRO.md").exists()
    total = sum(f.stat().st_size for f in RES.rglob("*") if f.is_file())
    assert total < 5 * 1024 * 1024
