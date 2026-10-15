"""inventario-anon-producao.sh: a saída nunca cai dentro do repo e o stderr da
leitura também passa pela máscara.

O ssh é trocado por um script local (VOLC_INVENTARIO_SSH_TESTE) que imprime um
segredo FALSO no stdout e no stderr; nada aqui fala com produção.
"""
import os
import pathlib
import subprocess

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "inventario-anon-producao.sh"
FALSO = "Zq9fK2mPw7xR4tYb8nVc3LdH"


@pytest.fixture
def ssh_falso(tmp_path):
    f = tmp_path / "leitor-falso.sh"
    f.write_text(
        "#!/usr/bin/env bash\ncat >/dev/null 2>&1 || true\n"
        f"echo 'linha comum stdout'\necho 'PASSWORD={FALSO}' >&2\necho 'Authorization: Bearer {FALSO}' >&2\n"
    )
    return f


def rodar(saida, ssh, raw=None, extra_env=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("VOLC_")}
    env.update(VOLC_AUTORIZA_LEITURA="inventario-anon-w4", VOLC_INVENTARIO_SSH_TESTE=str(ssh))
    if raw is not None:
        env["VOLC_INVENTARIO_RAW"] = str(raw)
    env.update(extra_env or {})
    return subprocess.run(["bash", str(SCRIPT), str(saida)], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)


def arquivos_no_repo_depois(antes):
    return set(subprocess.run(["git", "-C", str(RAIZ), "status", "--porcelain", "--ignored"],
                              capture_output=True, text=True).stdout.splitlines()) - antes


def estado_repo():
    return set(subprocess.run(["git", "-C", str(RAIZ), "status", "--porcelain", "--ignored"],
                              capture_output=True, text=True).stdout.splitlines())


def test_stderr_da_leitura_e_mascarado(tmp_path, ssh_falso):
    out, raw = tmp_path / "mascarada", tmp_path / "bruta"
    r = rodar(out, ssh_falso, raw)
    assert r.returncode == 0, r.stdout + r.stderr
    assert FALSO not in r.stdout + r.stderr, "segredo do stderr da leitura vazou no terminal"
    for f in out.glob("0*.txt"):
        assert FALSO not in f.read_text(), f"vazou em {f.name}"
    assert any(FALSO in f.read_text() for f in raw.glob("0*.txt")), "o bruto deveria ter o stderr (privado)"
    assert oct(raw.stat().st_mode & 0o777) == "0o700"
    assert all(oct(f.stat().st_mode & 0o777) == "0o600" for f in raw.glob("0*.txt"))


CONTORNOS = {
    "raiz-do-repo": lambda t: (RAIZ, None),
    "dentro-do-repo": lambda t: (RAIZ / "docs" / "closure" / "w4-x", None),
    "pai-inexistente-dentro": lambda t: (RAIZ / "nao" / "existe" / "ainda", None),
    "ponto-ponto": lambda t: (pathlib.Path(str(t) + "/.." * len(t.resolve().parts)) / RAIZ.relative_to("/") / "w4-x", None),
    "symlink-para-o-repo": "symlink",
    "bruta-dentro-do-repo": lambda t: (t / "ok", RAIZ / "w4-bruto"),
    "bruta-symlink-para-o-repo": "symlink-raw",
}


@pytest.mark.parametrize("nome", sorted(CONTORNOS))
def test_contornos_da_guarda_sao_recusados(nome, tmp_path, ssh_falso):
    c = CONTORNOS[nome]
    if c == "symlink":
        (tmp_path / "link").symlink_to(RAIZ)
        saida, raw = tmp_path / "link" / "w4-x", None
    elif c == "symlink-raw":
        (tmp_path / "link").symlink_to(RAIZ)
        saida, raw = tmp_path / "ok", tmp_path / "link" / "bruto"
    else:
        saida, raw = c(tmp_path)
    if raw is None:
        raw = tmp_path / "bruta"
    antes = estado_repo()
    r = rodar(saida, ssh_falso, raw)
    assert r.returncode == 2, f"{nome}: aceito ({r.returncode}) {r.stdout}{r.stderr}"
    assert "recusado" in r.stderr + r.stdout
    assert arquivos_no_repo_depois(antes) == set(), f"{nome}: escreveu no repo"


def test_sem_autorizacao_recusa(tmp_path, ssh_falso):
    env = {k: v for k, v in os.environ.items() if not k.startswith("VOLC_")}
    r = subprocess.run(["bash", str(SCRIPT), str(tmp_path / "x")], capture_output=True, text=True, env=env)
    assert r.returncode == 16


def test_hook_de_teste_nao_aceita_ssh(tmp_path):
    r = rodar(tmp_path / "x", "/usr/bin/ssh", tmp_path / "b")
    assert r.returncode == 2
