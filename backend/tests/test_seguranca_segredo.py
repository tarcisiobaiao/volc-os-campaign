"""O cofre precisa falhar fechado — e é isso que estes testes fixam.

Cada teste aqui existe porque a falha oposta seria silenciosa: credencial
gravada em texto puro, senha vazando em log, ou um segredo ilegível sendo
tratado como "não cadastrado" e apagando a configuração de quem já tinha.
"""
from __future__ import annotations

import pytest

from app.seguranca import (
    CofreSemChave,
    SegredoCorrompido,
    cifrar,
    cofre_configurado,
    decifrar,
    gerar_chave,
    mascara,
)

SENHA = "abcd EFGH ijkl MNOP qrst UVWX"  # formato real de Application Password


@pytest.fixture
def com_chave(monkeypatch):
    chave = gerar_chave()
    monkeypatch.setenv("VOLC_SEGREDO_KEY", chave)
    return chave


@pytest.fixture
def sem_chave(monkeypatch):
    """Ambiente limpo E Settings limpa.

    As duas pontas precisam ser zeradas: o cofre lê do ambiente e, se não achar,
    cai na `Settings` — que carrega o `backend/.env` do desenvolvedor. Zerar só
    o ambiente faria o teste passar na CI e falhar na máquina de quem tem a
    chave configurada.
    """
    monkeypatch.delenv("VOLC_SEGREDO_KEY", raising=False)
    from app.config import get_settings

    # Na INSTÂNCIA, não na classe: a `Settings` do pydantic guarda o valor no
    # próprio objeto, então um `setattr` na classe fica encoberto e o teste
    # passa a ler a chave real do desenvolvedor.
    monkeypatch.setattr(get_settings(), "volc_segredo_key", None, raising=False)
    yield
    get_settings.cache_clear()


def test_sem_chave_recusa_cifrar(sem_chave):
    """Nunca existe modo degradado: sem chave é erro, não texto puro."""
    assert cofre_configurado() is False
    with pytest.raises(CofreSemChave):
        cifrar(SENHA)


def test_chave_malformada_e_erro_de_setup(monkeypatch):
    monkeypatch.setenv("VOLC_SEGREDO_KEY", "isto-nao-e-uma-chave-fernet")
    assert cofre_configurado() is False
    with pytest.raises(CofreSemChave):
        cifrar(SENHA)


def test_ida_e_volta(com_chave):
    token = cifrar(SENHA)
    assert token != SENHA
    assert SENHA not in token
    assert decifrar(token) == SENHA


def test_texto_cifrado_nao_contem_fragmento_do_segredo(com_chave):
    """Um dump do banco não pode entregar nem pedaço da senha."""
    token = cifrar(SENHA)
    for pedaco in SENHA.split():
        assert pedaco not in token


def test_cifra_nao_e_deterministica(com_chave):
    """Fernet carrega IV e timestamp: cifrar a mesma senha duas vezes dá tokens
    diferentes. Sem isso, dois projetos com a mesma senha seriam identificáveis
    por comparação direta das colunas."""
    assert cifrar(SENHA) != cifrar(SENHA)


def test_chave_trocada_nao_abre_em_silencio(com_chave, monkeypatch):
    """O caso mais perigoso: se `decifrar` devolvesse None numa chave trocada, a
    rota leria 'credencial não cadastrada' e a tela ofereceria cadastrar por
    cima — apagando a original sem ninguém saber que ela existia."""
    token = cifrar(SENHA)
    monkeypatch.setenv("VOLC_SEGREDO_KEY", gerar_chave())
    with pytest.raises(SegredoCorrompido):
        decifrar(token)


def test_none_e_vazio_sao_estado_legitimo(com_chave):
    """Projeto sem credencial ainda não é erro — é projeto novo."""
    assert decifrar(None) is None
    assert decifrar("") is None


def test_cifrar_vazio_e_erro_de_chamada(com_chave):
    with pytest.raises(ValueError):
        cifrar("")


def test_mascara_nunca_devolve_o_segredo(com_chave):
    m = mascara(SENHA)
    assert m.endswith("UVWX")
    assert "abcd" not in m and "EFGH" not in m
    # os espaços somem para não entregar o formato de agrupamento
    assert " " not in m


def test_mascara_de_segredo_curto_nao_vaza_nada():
    assert set(mascara("abc")) == {"•"}
    assert mascara(None) == "—"
