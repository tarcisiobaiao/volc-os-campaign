"""Deadman Meta (W15): expectativa do workflow versionado, evidência do ledger.

Sem banco e sem rede: as linhas de `trafego_meta_sync_run` são dublês na forma
que a RPC `trafego_meta_persistir_snapshot` grava para `insights_fechamento`
(`supabase/migrations/20260908000000_meta_insights_escopo.sql`, bloco 7.9).
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.trafego.meta.deadman_insights import (
    FonteMeta,
    diagnosticar_insights_meta,
    job_do_workflow_meta,
)
from volc_ads.inteligencia_google.saude import EstadoSaudeColetor, MotivoDiagnostico

RAIZ = Path(__file__).resolve().parents[2]
D1 = "n8n/volc_meta_insights_dia_d1.json"
RECOLETA = "n8n/volc_meta_insights_dia_recoleta.json"
UTC = timezone.utc


def _wf(rel: str) -> dict:
    return json.loads((RAIZ / rel).read_text(encoding="utf-8"))


def _job(rel: str, *, ativo: bool = True):
    return job_do_workflow_meta(_wf(rel), rel, ativo_na_instancia=ativo)


def _fech(data: str, origem: str, concluido: str, *, completa=True, aceitas=1,
          escopo="insights_fechamento") -> dict:
    """Uma linha de trafego_meta_sync_run como a RPC grava o fechamento."""
    return {
        "escopo": escopo,
        "resultado": "ok",
        "iniciado_em": concluido,
        "concluido_em": concluido,
        "contagens": {"contas": 1, "contas_aceitas": aceitas},
        "cursor_final": {"window": f"{data}:{origem}", "leitura_completa": completa,
                         "chave_origem": "estavel"},
    }


# 15/10 09:00 em São Paulo (UTC-3) = 12:00Z.
AGORA = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


# ── expectativa ─────────────────────────────────────────────────────────────

def test_a_expectativa_sai_dos_workflows_versionados():
    d1 = job_do_workflow_meta(_wf(D1), D1)
    rec = job_do_workflow_meta(_wf(RECOLETA), RECOLETA)
    assert (d1.job, d1.origem_janela, d1.cron) == ("meta_insights_dia_d1", "D-1", "0 7 * * *")
    assert (rec.job, rec.origem_janela, rec.cron) == (
        "meta_insights_dia_recoleta", "RECOLETA", "30 8 * * *")
    assert d1.fuso == rec.fuso == "America/Sao_Paulo"
    # Versionado inativo = desligado, não "ligado por padrão".
    assert d1.ativo is False and rec.ativo is False


def test_workflow_versionado_desligado_e_desabilitado_e_nao_atrasado():
    job = job_do_workflow_meta(_wf(RECOLETA), RECOLETA)
    p = diagnosticar_insights_meta(job, [], now=AGORA)
    assert p.estado is EstadoSaudeColetor.DESABILITADO


@pytest.mark.parametrize("mexer, motivo", [
    (lambda wf: wf["meta"]["volc"].update(provider="GOOGLE_ADS"), "nao e um workflow"),
    (lambda wf: wf["meta"]["volc"].update(papel="D-1"), "papel diverge"),
    (lambda wf: _set_cfg(wf, "JANELA_MODO", "D0"), "JANELA_MODO invalido"),
    (lambda wf: _set_cfg(wf, "PASSOS", "09"), "AGENDA_AMBIGUA"),
    (lambda wf: _set_cfg(wf, "JOB", ""), "JOB valido"),
])
def test_expectativa_ambigua_ou_alheia_e_recusada_por_nome(mexer, motivo):
    wf = copy.deepcopy(_wf(RECOLETA))
    mexer(wf)
    with pytest.raises(ValueError, match=motivo):
        job_do_workflow_meta(wf, RECOLETA)


def _set_cfg(wf: dict, nome: str, valor: str) -> None:
    no = next(n for n in wf["nodes"] if n["name"] == "Config")
    for a in no["parameters"]["assignments"]["assignments"]:
        if a["name"] == nome:
            a["value"] = valor


# ── evidência ───────────────────────────────────────────────────────────────

def test_fechamento_completo_recente_e_saudavel():
    p = diagnosticar_insights_meta(
        _job(RECOLETA), [_fech("2026-10-15", "RECOLETA", "2026-10-15T11:40:00+00:00")],
        now=AGORA)
    assert p.estado is EstadoSaudeColetor.SAUDAVEL
    assert p.job == "meta_insights_dia_recoleta" and p.origem_janela == "RECOLETA"


def test_o_fechamento_do_d1_nao_pinta_a_recoleta_de_verde():
    """Mesmo dia, mesmo ledger, papéis diferentes: o rótulo separa."""
    linhas = [_fech("2026-10-15", "D-1", "2026-10-15T10:05:00+00:00")]
    rec = diagnosticar_insights_meta(_job(RECOLETA), linhas, now=AGORA)
    d1 = diagnosticar_insights_meta(_job(D1), linhas, now=AGORA)
    assert rec.estado is EstadoSaudeColetor.NUNCA_EXECUTADO
    assert d1.estado is EstadoSaudeColetor.SAUDAVEL


def test_leitura_de_hierarquia_e_pagina_nao_contam_como_fechamento():
    linhas = [
        _fech("2026-10-15", "RECOLETA", "2026-10-15T11:40:00+00:00", escopo="insights_pagina"),
        _fech("2026-10-15", "RECOLETA", "2026-10-15T11:41:00+00:00", escopo="hierarchy"),
    ]
    p = diagnosticar_insights_meta(_job(RECOLETA), linhas, now=AGORA)
    assert p.estado is EstadoSaudeColetor.NUNCA_EXECUTADO


def test_rotulo_torto_nao_e_evidencia():
    linha = _fech("2026-10-15", "RECOLETA", "2026-10-15T11:40:00+00:00")
    linha["cursor_final"]["window"] = "RECOLETA"
    p = diagnosticar_insights_meta(_job(RECOLETA), [linha], now=AGORA)
    assert p.estado is EstadoSaudeColetor.NUNCA_EXECUTADO


def test_ultimo_sucesso_alem_de_um_dia_e_atrasado():
    p = diagnosticar_insights_meta(
        _job(RECOLETA), [_fech("2026-10-13", "RECOLETA", "2026-10-13T11:40:00+00:00")],
        now=AGORA)
    assert p.estado is EstadoSaudeColetor.ATRASADO
    assert p.motivo is MotivoDiagnostico.INTERVALO_EXECUCAO_EXPIRADO


def test_a_mais_recente_decide_e_nao_a_primeira_da_lista():
    linhas = [
        _fech("2026-10-15", "RECOLETA", "2026-10-15T11:40:00+00:00", completa=False, aceitas=0),
        _fech("2026-10-14", "RECOLETA", "2026-10-14T11:40:00+00:00"),
    ]
    p = diagnosticar_insights_meta(_job(RECOLETA), list(reversed(linhas)), now=AGORA)
    assert p.estado is EstadoSaudeColetor.FALHOU
    assert p.falha_codigo == "FALHA_COLETA"


def test_fechamento_parcial_e_falha_parcial_e_nunca_sucesso():
    p = diagnosticar_insights_meta(
        _job(D1), [_fech("2026-10-15", "D-1", "2026-10-15T10:05:00+00:00",
                         completa=False, aceitas=2)], now=AGORA)
    assert p.estado is EstadoSaudeColetor.FALHOU
    assert (p.falha_codigo, p.falha_classe) == ("COLETA_PARCIAL", "PARCIAL")


@pytest.mark.parametrize("cursor", [
    {"window": "2026-10-15:D-1"},                              # completude ausente
    {"window": "2026-10-15:D-1", "leitura_completa": None},
    {"window": "2026-10-15:D-1", "leitura_completa": "true"},  # texto não é booleano
])
def test_completude_nao_declarada_nao_vira_sucesso(cursor):
    linha = _fech("2026-10-15", "D-1", "2026-10-15T10:05:00+00:00")
    linha["cursor_final"] = cursor
    linha["contagens"] = {}
    p = diagnosticar_insights_meta(_job(D1), [linha], now=AGORA)
    assert p.estado is EstadoSaudeColetor.FALHOU
    assert p.falha_codigo == "FALHA_COLETA"


@pytest.mark.parametrize("fonte", [FonteMeta.TABELA_AUSENTE, FonteMeta.LEITURA_FALHOU])
def test_sem_fonte_e_indeterminado_e_nunca_nunca_executado(fonte):
    p = diagnosticar_insights_meta(_job(D1), None, now=AGORA, fonte=fonte)
    assert p.estado is EstadoSaudeColetor.INDETERMINADO


def test_timestamp_sem_fuso_e_indeterminado():
    p = diagnosticar_insights_meta(
        _job(D1), [_fech("2026-10-15", "D-1", "2026-10-15T10:05:00")], now=AGORA)
    assert p.estado is EstadoSaudeColetor.INDETERMINADO
    assert p.motivo is MotivoDiagnostico.TIMEZONE_NAIVE


def test_a_tolerancia_segura_o_alarme_durante_a_execucao_do_dia():
    """24h e 10 min depois do último sucesso: atrasado sem tolerância, ok com 1h."""
    linhas = [_fech("2026-10-14", "D-1", "2026-10-14T10:05:00+00:00")]
    agora = datetime(2026, 10, 15, 10, 15, tzinfo=UTC)
    assert diagnosticar_insights_meta(_job(D1), linhas, now=agora).estado \
        is EstadoSaudeColetor.ATRASADO
    assert diagnosticar_insights_meta(
        _job(D1), linhas, now=agora, tolerancia_atraso=timedelta(hours=1)).estado \
        is EstadoSaudeColetor.SAUDAVEL


def test_a_projecao_publica_nao_carrega_conta_nem_id_google():
    p = diagnosticar_insights_meta(
        _job(D1), [_fech("2026-10-15", "D-1", "2026-10-15T10:05:00+00:00")], now=AGORA)
    campos = set(vars(p))
    assert not campos & {"identidade", "customer_id", "login_customer_id", "campaign_id"}


def test_active_ausente_e_desligado_e_nao_ligado():
    wf = copy.deepcopy(_wf(D1))
    del wf["active"]
    assert job_do_workflow_meta(wf, D1).ativo is False
    wf["active"] = "true"  # texto não é booleano
    assert job_do_workflow_meta(wf, D1).ativo is False


def test_fechamento_parcial_nao_conta_como_ultimo_sucesso():
    p = diagnosticar_insights_meta(
        _job(D1), [_fech("2026-10-15", "D-1", "2026-10-15T10:05:00+00:00",
                         completa=False, aceitas=2)], now=AGORA)
    assert p.tempo_desde_ultima_tentativa is not None
    assert p.tempo_desde_ultimo_sucesso is None


def test_workflow_ligado_na_instancia_e_falhando_nao_se_esconde_atras_do_arquivo():
    """Achado da revisão: só com o arquivo versionado, tudo é DESABILITADO."""
    linhas = [_fech("2026-10-01", "RECOLETA", "2026-10-01T11:40:00+00:00")]
    arquivo = job_do_workflow_meta(_wf(RECOLETA), RECOLETA)
    assert diagnosticar_insights_meta(arquivo, linhas, now=AGORA).estado \
        is EstadoSaudeColetor.DESABILITADO
    vivo = job_do_workflow_meta(_wf(RECOLETA), RECOLETA, ativo_na_instancia=True)
    assert diagnosticar_insights_meta(vivo, linhas, now=AGORA).estado \
        is EstadoSaudeColetor.ATRASADO
    with pytest.raises(TypeError):
        job_do_workflow_meta(_wf(RECOLETA), RECOLETA, ativo_na_instancia="sim")


def test_lista_ausente_e_nao_li_e_nao_nunca_executado():
    p = diagnosticar_insights_meta(_job(D1), None, now=AGORA)
    assert p.estado is EstadoSaudeColetor.INDETERMINADO


@pytest.mark.parametrize("ruim", ["2026-10-15T10:05:00", None, "ontem"])
def test_instante_ruim_misturado_com_bom_e_indeterminado_e_nao_excecao(ruim):
    linhas = [_fech("2026-10-15", "D-1", "2026-10-15T10:05:00+00:00"),
              _fech("2026-10-15", "D-1", "2026-10-15T10:05:00+00:00")]
    linhas[1]["concluido_em"] = ruim
    p = diagnosticar_insights_meta(_job(D1), linhas, now=AGORA)
    assert p.estado is EstadoSaudeColetor.INDETERMINADO
