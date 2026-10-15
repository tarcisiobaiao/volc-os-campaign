"""fechar-cadastro-gotrue.sh: falha remota sai não-zero e o --reverter só
restaura o backup exato (sha256 conferido). A cadeia "remota" roda localmente
sobre um diretório temporário com um docker falso; nada fala com produção."""
import os
import pathlib
import subprocess

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "fechar-cadastro-gotrue.sh"
LIB = RAIZ / "scripts" / "lib" / "gotrue-cadastro.sh"


@pytest.fixture
def servidor(tmp_path):
    d = tmp_path / "docker"; d.mkdir()
    (d / ".env").write_text("ANON_KEY=x\nDISABLE_SIGNUP=false\nOUTRA=1\n")
    bin_ = tmp_path / "bin"; bin_.mkdir()
    docker = bin_ / "docker"
    docker.write_text("#!/usr/bin/env bash\n"
                      "case \"$1 $2\" in 'compose up') [ -f \"$FALHA_COMPOSE\" ] && exit 9; exit 0;;"
                      " 'ps --filter') echo 'Up 3 seconds (healthy)';; esac\n")
    docker.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith("VOLC_")}
    env.update(PATH=f"{bin_}:{env['PATH']}", TMPDIR=str(tmp_path.parent),
               FALHA_COMPOSE=str(tmp_path / "falha"))
    return d, env, tmp_path


def test_falha_no_meio_da_cadeia_sai_nao_zero(servidor):
    d, env, t = servidor
    (t / "falha").write_text("1")
    r = subprocess.run(["bash", "-c", f'SSH=(bash -c); DIR={d}; CARIMBO=20261015-120000; '
                        f'source {LIB}; set -euo pipefail; fechar'],
                       capture_output=True, text=True, env=env)
    assert r.returncode != 0, r.stdout + r.stderr


def test_reverter_restaura_backup_exato(servidor):
    d, env, t = servidor
    r = subprocess.run(["bash", "-c", f'SSH=(bash -c); DIR={d}; CARIMBO=20261015-120000; '
                        f'source {LIB}; set -euo pipefail; fechar'],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DISABLE_SIGNUP=true" in (d / ".env").read_text()
    original = (d / ".env.bak-w4-signup-20261015-120000").read_bytes()
    r = subprocess.run(["bash", "-c", f'SSH=(bash -c); DIR={d}; CARIMBO=20261015-130000; '
                        f'source {LIB}; set -euo pipefail; reabrir 20261015-120000'],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (d / ".env").read_bytes() == original


def test_reverter_recusa_backup_adulterado(servidor):
    d, env, t = servidor
    subprocess.run(["bash", "-c", f'SSH=(bash -c); DIR={d}; CARIMBO=20261015-120000; '
                    f'source {LIB}; set -euo pipefail; fechar'],
                   capture_output=True, text=True, env=env, check=True)
    bak = d / ".env.bak-w4-signup-20261015-120000"
    bak.write_text(bak.read_text() + "INJETADO=1\n")
    r = subprocess.run(["bash", "-c", f'SSH=(bash -c); DIR={d}; CARIMBO=20261015-130000; '
                        f'source {LIB}; set -euo pipefail; reabrir 20261015-120000'],
                       capture_output=True, text=True, env=env)
    assert r.returncode != 0 and "sha256 não confere" in r.stdout + r.stderr
    assert "DISABLE_SIGNUP=true" in (d / ".env").read_text(), "não podia ter restaurado nada"


def test_reverter_sem_autorizacao_recusa(servidor):
    d, env, t = servidor
    r = subprocess.run(["bash", str(SCRIPT), "--reverter", "20261015-120000"], capture_output=True, text=True, env=env)
    assert r.returncode == 16




def test_reverter_carimbo_errado_para_antes_do_sha_e_do_cp(servidor):
    d, env, t = servidor
    subprocess.run(["bash", "-c", f'SSH=(bash -c); DIR={d}; CARIMBO=20261015-120000; '
                    f'source {LIB}; set -euo pipefail; fechar'], capture_output=True, text=True, env=env, check=True)
    antes = (d / ".env").read_bytes()
    r = subprocess.run(["bash", "-c", f'SSH=(bash -c); DIR={d}; CARIMBO=20261015-130000; '
                        f'source {LIB}; set -euo pipefail; reabrir 20991231-235959'],
                       capture_output=True, text=True, env=env)
    assert r.returncode != 0
    assert "backup ausente" in r.stdout + r.stderr
    assert "sha256 não confere" not in r.stdout + r.stderr, "não podia ter chegado à conferência do sha"
    assert (d / ".env").read_bytes() == antes
    assert not list(d.glob(".env.antes-de-reverter-*")), "não podia ter copiado nada"
