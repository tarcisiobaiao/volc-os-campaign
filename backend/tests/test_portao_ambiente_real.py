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
