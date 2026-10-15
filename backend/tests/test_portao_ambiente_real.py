"""O portão de `ambiente_real`: sem VOLC_TESTES_AMBIENTE_REAL=1, as fixtures pulam
ANTES de tocar no ambiente (nem setenv, nem delenv, nem get_settings), então o
pytest no checkout oficial não lê nem escreve no Supabase de produção."""
import ast
import inspect

import pytest

import conftest


def test_sem_a_variavel_o_portao_pula(monkeypatch):
    monkeypatch.delenv(conftest.VAR_PORTAO, raising=False)
    with pytest.raises(pytest.skip.Exception, match="PRODUÇÃO"):
        conftest._portao_ambiente_real()


@pytest.mark.parametrize("valor", ["", "0", "true", "sim", " 1"])
def test_so_o_valor_1_abre(monkeypatch, valor):
    monkeypatch.setenv(conftest.VAR_PORTAO, valor)
    with pytest.raises(pytest.skip.Exception):
        conftest._portao_ambiente_real()


def test_com_1_abre(monkeypatch):
    monkeypatch.setenv(conftest.VAR_PORTAO, "1")
    conftest._portao_ambiente_real()  # não pula


@pytest.mark.parametrize("fixture", ["ambiente_real", "ambiente_real_modulo"])
def test_portao_e_a_primeira_coisa_da_fixture(fixture):
    """Antes do portão não pode haver import de settings nem mexida no ambiente."""
    fn = getattr(conftest, fixture)
    fn = getattr(fn, "__wrapped__", None) or getattr(fn, "_get_wrapped_function", lambda: fn)()
    corpo = ast.parse(inspect.getsource(fn).lstrip()).body[0].body
    corpo = [n for n in corpo if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    primeira = corpo[0]
    assert isinstance(primeira, ast.Expr) and isinstance(primeira.value, ast.Call)
    assert getattr(primeira.value.func, "id", None) == "_portao_ambiente_real"


def test_os_quatro_modulos_levam_o_marcador():
    from pathlib import Path
    base = Path(__file__).parent
    for nome in ("test_trafego.py", "test_quadro.py", "test_publicar_pagina.py", "test_reler_wordpress.py"):
        fonte = (base / nome).read_text(encoding="utf-8")
        assert "pytest.mark.ambiente_real" in fonte, nome


def test_settings_da_sessao_nao_le_env_do_disco(tmp_path, monkeypatch):
    """Com um .env falso no diretório corrente, Settings da sessão não o lê."""
    from app.config import Settings, get_settings

    (tmp_path / ".env").write_text(
        "SUPABASE_URL=https://falso.invalid\nSUPABASE_SERVICE_ROLE_KEY=falso\nOPENAI_API_KEY=falso-do-disco\n")
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    try:
        s = Settings()
        # Só booleanos na asserção: se falhar, o pytest não imprime credencial nenhuma.
        sem_supabase = not s.supabase_url and not s.supabase_service_role_key
        sem_disco = s.openai_api_key != "falso-do-disco"
        del s
        assert sem_supabase, "credencial Supabase entrou na sessão de testes"
        assert sem_disco, "o .env do diretório corrente foi lido"
    finally:
        get_settings.cache_clear()


def test_um_modulo_sozinho_tambem_e_hermetico(tmp_path):
    """pytest de um arquivo só, com cwd onde há um .env falso: nada do disco entra."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    (tmp_path / ".env").write_text("SUPABASE_URL=https://falso.invalid\nOPENAI_API_KEY=falso-do-disco\n")
    alvo = Path(__file__).resolve()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SUPABASE_", "VOLC_"))}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        f"{alvo}::test_settings_da_sessao_nao_le_env_do_disco"],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "1 passed" in r.stdout, r.stdout[-800:] + r.stderr[-800:]


def test_configuracao_do_fastapi_intocada():
    """O hermetismo é por fonte, não por model_config: o env_file do FastAPI segue o mesmo."""
    from app.config import Settings
    assert tuple(Settings.model_config["env_file"])[1:] == (".env", ".env.local")
