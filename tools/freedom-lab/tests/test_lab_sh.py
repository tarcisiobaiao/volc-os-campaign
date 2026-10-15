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


def test_base_prod_usa_o_verificador_estrutural():
    fonte = LAB.read_text(encoding="utf-8")
    assert "verificar_dump_schema.py" in fonte
    assert "grep -qE '^(COPY|INSERT) '" not in fonte


def test_blocos_do_dump_ficam_fora_do_repo_e_somem():
    fonte = LAB.read_text(encoding="utf-8")
    assert 'mktemp -d "${TMPDIR:-/tmp}/volc-lab-blocos' in fonte
    corpo = fonte[fonte.index("base_prod() {"):]
    corpo = corpo[:corpo.index("\n}\n")]
    assert corpo.index('rm -rf "$blocos"') < corpo.index("[ $c = 0 ] || return $c")
    assert 'blocos="$RECIBOS/blocos"' not in fonte


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker ausente")
def test_suite_fora_de_db_suites_e_recusada_sem_flag(tmp_path):
    suite = tmp_path / "suite.sh"
    suite.write_text('ok "nada"\n')
    env = os.environ | {"MIGRATION_SUITE": str(suite), "RECIBOS": str(tmp_path)}
    # o container do lab precisa existir para chegar à checagem; sem ele, a guarda de lab recusa antes
    r = subprocess.run([str(LAB), "testar"], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0


def test_recibo_so_afirma_producao_intocada_com_suite_versionada():
    fonte = LAB.read_text(encoding="utf-8")
    assert "LAB_SUITE_LIVRE" in fonte and "nao_garantido" in fonte
    assert '"producao_acessada\\": false' not in fonte  # nunca mais fixo


def test_semente_de_producao_passa_pelo_gate():
    fonte = LAB.read_text(encoding="utf-8")
    corpo = fonte[fonte.index("semear_prod() {"):]
    assert corpo.splitlines()[2].strip() == 'gate_semente "$LAB_SEMENTE" || return 1'
    assert "semear_prod" in fonte[fonte.index("recriar-prod)"):]
