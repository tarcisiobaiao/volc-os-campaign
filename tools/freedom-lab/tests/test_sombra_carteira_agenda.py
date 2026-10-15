"""A agenda da sombra (W13) nasce desligada e falha alto. Hermético: um python
falso no lugar do venv registra a invocação; nada fala com o Supabase."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
RUN = REPO / "deploy" / "sombra-carteira" / "run.sh"
UNIDADES = REPO / "deploy" / "sombra-carteira"


@pytest.fixture()
def raiz(tmp_path):
    (tmp_path / "current").mkdir()
    (tmp_path / "current" / ".base_ref").write_text("a8059ba0\n")
    bin_ = tmp_path / "venv" / "bin"
    bin_.mkdir(parents=True)
    falso = bin_ / "python"
    falso.write_text('#!/usr/bin/env bash\necho "$@" >> "$VOLC_TESTE_REGISTRO"\n'
                     'case "$*" in *9999999999*) exit 3;; esac\nexit 0\n')
    falso.chmod(0o755)
    return tmp_path


def rodar(raiz, **env):
    base = {"PATH": os.environ["PATH"], "VOLC_SOMBRA_RAIZ": str(raiz),
            "VOLC_SOMBRA_LOCK": str(raiz / "lock"), "VOLC_SOMBRA_DESTINO": str(raiz / "exp"),
            "VOLC_TESTE_REGISTRO": str(raiz / "chamadas"), "SERVICE_ROLE_KEY": "x"}
    p = subprocess.run(["bash", str(RUN)], env={**base, **env}, capture_output=True, text=True)
    chamadas = (raiz / "chamadas").read_text().splitlines() if (raiz / "chamadas").exists() else []
    return p.returncode, p.stderr, chamadas


def test_desligada_por_padrao_nao_le_nada(raiz):
    codigo, err, chamadas = rodar(raiz, VOLC_SOMBRA_CONTAS="1112223334")
    assert codigo == 65 and chamadas == [] and "desligada" in err


def test_ligada_roda_cada_conta_so_leitura(raiz):
    codigo, _, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim",
                                VOLC_SOMBRA_CONTAS="1112223334 5556667778",
                                VOLC_SOMBRA_JANELA_DIAS="28")
    assert codigo == 0 and len(chamadas) == 2
    for c in chamadas:
        assert c.startswith("-m volc_lab.sombra_carteira gerar --conta ")
        assert "--postgrest" in c and "--base-ref a8059ba0" in c and "--janela-dias 28" in c


def test_conta_que_falha_nao_para_as_outras_mas_sai_1(raiz):
    codigo, err, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim",
                                  VOLC_SOMBRA_CONTAS="9999999999 1112223334")
    assert codigo == 1 and len(chamadas) == 2
    assert "999****999" in err and "9999999999" not in err


@pytest.mark.parametrize("env", [
    {"VOLC_SOMBRA_CONTAS": " "},
    {"VOLC_SOMBRA_CONTAS": "1112223334", "VOLC_SOMBRA_MAX_CUSTO_SEM_RECEITA": "0,1"},
])
def test_configuracao_invalida_sai_64_sem_ler(raiz, env):
    codigo, _, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim", **env)
    assert codigo == 64 and chamadas == []


def test_sem_base_ref_sai_64(raiz):
    (raiz / "current" / ".base_ref").unlink()
    codigo, _, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim", VOLC_SOMBRA_CONTAS="1112223334")
    assert codigo == 64 and chamadas == []


def test_execucao_concorrente_sai_75(raiz):
    with open(raiz / "lock", "w") as trava:
        import fcntl
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        codigo, _, chamadas = rodar(raiz, VOLC_SOMBRA_HABILITADA="sim", VOLC_SOMBRA_CONTAS="1112223334")
    assert codigo == 75 and chamadas == []


def test_unidades_coerentes_e_exemplo_desligado():
    servico = (UNIDADES / "volc-sombra-carteira.service").read_text()
    timer = (UNIDADES / "volc-sombra-carteira.timer").read_text()
    assert "SuccessExitStatus=65 75" in servico   # desligada e concorrente não viram falha
    assert "Unit=volc-sombra-carteira.service" in timer
    assert "VOLC_SOMBRA_HABILITADA=nao" in (UNIDADES / "sombra.env.exemplo").read_text()
    assert "SERVICE_ROLE" not in (UNIDADES / "sombra.env.exemplo").read_text().split("# Sem segredo")[0]
