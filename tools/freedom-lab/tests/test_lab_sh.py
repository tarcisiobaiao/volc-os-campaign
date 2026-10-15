"""lab.sh recusa executar SQL fora do container do laboratório (nome + rótulo + sem rede)."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1] / "lab.sh"


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker ausente")
@pytest.mark.parametrize("comando", ["semear", "testar", "migrar"])
def test_recusa_container_que_nao_e_do_lab(comando, tmp_path):
    env = os.environ | {"LAB_NOME": "volc-nao-e-do-lab-zz", "RECIBOS": str(tmp_path)}
    r = subprocess.run([str(LAB), comando], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert "nada executado" in r.stderr + r.stdout


def test_toda_execucao_de_sql_passa_pela_guarda():
    fonte = LAB.read_text(encoding="utf-8")
    assert 'P() { exigir_lab || return $?;' in fonte
    # docker exec direto só dentro de funções que começam por exigir_lab
    for nome in ("semear() {", "testar() {"):
        trecho = fonte[fonte.index(nome):]
        assert trecho.splitlines()[1].strip() == "exigir_lab || return $?", nome
