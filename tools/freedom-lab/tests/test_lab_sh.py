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


def _base_prod(tmp_path, conteudo, sha=None):
    import hashlib
    dump = tmp_path / "dump.sql"
    dump.write_text(conteudo)
    env = os.environ | {"LAB_NOME": "volc-nao-e-do-lab-zz", "RECIBOS": str(tmp_path),
                        "LAB_DUMP": str(dump),
                        "LAB_DUMP_SHA256": sha or hashlib.sha256(conteudo.encode()).hexdigest()}
    return subprocess.run([str(LAB), "base-prod"], env=env, capture_output=True, text=True, timeout=60)


def test_base_prod_recusa_sha_divergente(tmp_path):
    r = _base_prod(tmp_path, "-- schema\n", sha="0" * 64)
    assert r.returncode != 0 and "sha256 divergente" in r.stderr


def test_base_prod_recusa_dump_com_dado(tmp_path):
    r = _base_prod(tmp_path, "CREATE TABLE t(i int);\nCOPY public.t (i) FROM stdin;\n1\n\\.\n")
    assert r.returncode != 0 and "contém dado" in r.stderr


def test_restaurar_em_blocos_corta_so_em_fronteira(tmp_path):
    import sys
    sys.path.insert(0, str(LAB.parent / "db"))
    import restaurar_em_blocos as rb
    objs = "".join(f"\n--\n-- Name: t{i}; Type: TABLE\n--\n\nCREATE TABLE t{i}(i int);\n" + "\n" * 50 for i in range(200))
    dump = tmp_path / "d.sql"
    dump.write_text("-- cabeçalho\nSET x = 1;\nCREATE SCHEMA public;\n" + objs)
    saida = tmp_path / "b"
    saida.mkdir()
    n = rb.main(str(dump), str(saida), linhas_por_bloco=1000)
    assert n > 1
    juntos = "".join(f.read_text().replace("-- cabeçalho\nSET x = 1;\n", "", 1) for f in sorted(saida.iterdir()))
    assert juntos.count("CREATE TABLE") == 200 and "CREATE SCHEMA public" not in juntos
    assert all(f.read_text().startswith("-- cabeçalho") for f in saida.iterdir())
