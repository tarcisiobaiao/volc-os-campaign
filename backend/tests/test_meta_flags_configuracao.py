"""Permissões persistentes, sem acesso ao .env ou contas da operação."""
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.trafego.meta_execucao import capacidades as cap
from app.trafego.meta_execucao.registro import RegistroSagaMetaSupabase
from app.trafego.meta_execucao.registro_de_midia import LivroDeRegistroDeMidiaSupabase


@pytest.fixture
def configuracao(tmp_path, monkeypatch):
    for nome in (*cap.FLAGS_DE_CRIACAO, cap.FLAG_UPLOAD_DE_ATIVO, "META_VALIDATE_ONLY_ENABLED"):
        monkeypatch.delenv(nome, raising=False)
    arquivo = tmp_path / "backend.env"
    arquivo.write_text(
        "META_CREATE_PAUSED_ENABLED=1\nMETA_CREATE_LEDGER_WRITE_ENABLED=1\n"
        "META_VALIDATE_ONLY_ENABLED=1\nMETA_UPLOAD_ASSET_ENABLED=metaacct_prova\n"
    )
    monkeypatch.setattr(cap, "get_settings", lambda: Settings(_env_file=arquivo))
    return arquivo


def test_arquivo_libera_portas_mas_nao_inventa_prova_por_conta(configuracao):
    assert cap.autorizacoes_de_processo_ausentes() == []
    assert cap.validacao_liberada()
    assert cap.ledger_liberado()
    assert cap.upload_de_ativo_liberado("metaacct_prova")
    assert not cap.upload_de_ativo_liberado("metaacct_outra")
    assert cap.autorizacoes_ausentes("metaacct_prova") == [cap.FLAG_DESTINO_SHOP]


@pytest.mark.parametrize("valor", ["", "0", "true", "yes", " 1"])
def test_revogacao_explicita_prevalece_sobre_arquivo(configuracao, monkeypatch, valor):
    monkeypatch.setenv(cap.FLAG_LEDGER, valor)
    assert not cap.ledger_liberado()
    with pytest.raises(Exception, match="ledger.*fechado"):
        RegistroSagaMetaSupabase(SimpleNamespace(enabled=True))._exigir_escrita()
    with pytest.raises(Exception, match="registro durável.*fechado"):
        LivroDeRegistroDeMidiaSupabase(SimpleNamespace(enabled=True))._exigir_escrita()


def test_os_dois_ledgers_usam_mesma_configuracao(configuracao):
    RegistroSagaMetaSupabase(SimpleNamespace(enabled=True))._exigir_escrita()
    LivroDeRegistroDeMidiaSupabase(SimpleNamespace(enabled=True))._exigir_escrita()


def test_validar_nao_autoriza_criar(monkeypatch):
    for nome in cap.FLAGS_DE_CRIACAO:
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setattr(cap, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setenv("META_VALIDATE_ONLY_ENABLED", "1")
    assert cap.validacao_liberada()
    assert not cap.criacao_liberada("metaacct_prova")


def test_configuracao_recarregada_mantem_autorizacao(configuracao):
    for _ in range(2):
        assert Settings(_env_file=configuracao).meta_create_paused_enabled == "1"


def test_nao_permite_usar_leitor_para_segredos():
    with pytest.raises(ValueError):
        cap.valor_flag("SUPABASE_SERVICE_ROLE_KEY")
