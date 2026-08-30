from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from volc_ads.inteligencia_google.modelo import (
    DocumentoColeta, EstadoColeta, EstadoValor, Metrica,
)
from volc_ads.inteligencia_google.persistencia import (
    ErroPersistenciaGoogle, SupabaseGoogleIntelligence,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/v12_01_google_inteligencia_coletas.sql"


def documento(**trocas):
    base = dict(
        tipo_sinal="EXPERIMENTOS",
        estado=EstadoColeta.VAZIO_CONFIRMADO,
        customer_id="8017851692",
        login_customer_id="6016739364",
        competencia=date(2026, 8, 29),
        coletada_em=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        bucket="daily:2026-08-29",
        quantidade=0,
    )
    base.update(trocas)
    return DocumentoColeta(**base)


def test_zero_medido_nao_e_ausencia():
    metrica = Metrica(
        "campaign", "24156373085", "clicks", EstadoValor.MEDIDO,
        valor_numerico=0,
    ).serializar()
    assert metrica["estado_valor"] == "medido"
    assert metrica["valor_numerico"] == "0"


def test_ausencia_nao_pode_carregar_zero():
    with pytest.raises(ValueError, match="nao medida"):
        Metrica(
            "campaign", "24156373085", "clicks", EstadoValor.AUSENTE,
            valor_numerico=0,
        )


def test_vazio_confirmado_e_falha_tem_quantidades_opostas():
    vazio = documento().serializar()
    falha = documento(
        estado=EstadoColeta.FALHOU, quantidade=None,
        erro_codigo="TIMEOUT", erro_classe="TimeoutError", erro_detalhe="tempo esgotado",
    ).serializar()
    assert vazio["quantidade"] == 0
    assert vazio["erro_codigo"] is None
    assert falha["quantidade"] is None
    assert falha["erro_codigo"] == "TIMEOUT"


def test_falha_nao_pode_se_disfarcar_de_vazio():
    with pytest.raises(ValueError, match="nao pode inventar quantidade"):
        documento(
            estado=EstadoColeta.FALHOU, quantidade=0,
            erro_codigo="X", erro_classe="Erro",
        )


def test_idempotencia_e_por_escopo_tipo_bucket_e_versao():
    a = documento().serializar()["chave_idempotencia"]
    b = documento(
        coletada_em=datetime(2026, 8, 29, 23, tzinfo=timezone.utc),
    ).serializar()["chave_idempotencia"]
    c = documento(bucket="daily:2026-08-30").serializar()["chave_idempotencia"]
    assert a == b
    assert a != c


def test_falha_nao_memoriza_fracasso_e_esconde_retry_bem_sucedido():
    falha = documento(
        estado=EstadoColeta.FALHOU, quantidade=None,
        erro_codigo="TIMEOUT", erro_classe="TimeoutError",
    ).serializar()["chave_idempotencia"]
    sucesso = documento().serializar()["chave_idempotencia"]
    assert falha != sucesso


def test_persistencia_recusa_outro_supabase(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "nao-vazia")
    with pytest.raises(ErroPersistenciaGoogle, match="autoridade recusada"):
        SupabaseGoogleIntelligence("https://projeto-legado.supabase.co")


def test_migration_blinda_rls_append_only_e_semantica():
    sql = MIGRATION.read_text()
    for tabela in (
        "trafego_google_inteligencia_coleta",
        "trafego_google_inteligencia_item",
        "trafego_google_inteligencia_metrica",
    ):
        assert f"ALTER TABLE public.{tabela} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE public.{tabela} FORCE ROW LEVEL SECURITY" in sql
        assert f"REVOKE ALL ON public.{tabela} FROM PUBLIC, anon, authenticated" in sql
    assert "estado = 'vazio_confirmado' AND quantidade = 0" in sql
    assert "estado IN ('inelegivel', 'nao_suportado', 'falhou') AND quantidade IS NULL" in sql
    assert "estado_valor = 'medido'" in sql
    assert "e append-only" in sql


def test_coletor_nao_contem_mutacao_google():
    source = (ROOT / "volc_ads/inteligencia_google/coletor.py").read_text()
    proibidos = (
        ".mutate_", "apply_recommendation", "dismiss_recommendation",
        "FORGE_PERMITIR_ESCRITA=1",
    )
    assert not [token for token in proibidos if token in source.lower()]
