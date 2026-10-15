"""Deadman da recoleta (W11): silêncio da recoleta vira evidência, e backfill
manual não se passa por ela."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.trafego.deadman_coleta import (
    PASSO_RECOLETA,
    diagnosticar_coleta,
    job_da_recoleta,
)
from volc_ads.coleta import executor
from volc_ads.coleta.contrato import Contexto
from volc_ads.inteligencia_google.saude import EstadoSaudeColetor

RAIZ = Path(__file__).resolve().parents[2]
TIMER = RAIZ / "deploy" / "gads-coleta" / "volc-gads-coleta-recoleta.timer"
RUN = RAIZ / "deploy" / "gads-coleta" / "run.sh"
CONTA, MCC = "5478096539", "4904074301"
AGORA = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def _job(ativo=True):
    return job_da_recoleta(TIMER.read_text(encoding="utf-8"), str(TIMER), ativo=ativo)


def _chave_real(passo: str | None = PASSO_RECOLETA) -> str:
    """A chave que o coletor de verdade monta — não uma string copiada."""
    ctx = Contexto(customer_id=CONTA, login_customer_id=MCC, origem_janela="backfill",
                   data_inicio=datetime(2026, 10, 8).date(), data_fim=datetime(2026, 10, 14).date(),
                   fuso="America/Sao_Paulo", moeda="BRL",
                   disparo="agenda" if passo else "manual", passo=passo)
    return f"{executor.prefixo_do_passo('campanha_dia', ctx)}:{ctx.colhida_iso}"


def _fecho(horas_atras: float, *, passo=PASSO_RECOLETA, resultado="ok", origem="backfill"):
    t = AGORA - timedelta(hours=horas_atras)
    return {"job": "gads_campanha_dia", "origem_janela": origem, "execucao_chave": _chave_real(passo),
            "resultado": resultado, "encerrada_em": t, "batimento_em": t}


def _diag(fechos, ativo=True):
    return diagnosticar_coleta(_job(ativo), fechos, login_customer_id=MCC, customer_id=CONTA, now=AGORA)


def teste_expectativa_vem_do_timer_versionado():
    job = _job()
    assert (job.job, job.origem_janela, job.cron, job.fuso) == (
        "gads_campanha_dia", "backfill", "15 7 * * *", "America/Sao_Paulo")
    assert job.marcador_chave == ":passorec:"


def teste_o_passo_do_deadman_e_o_mesmo_que_o_run_sh_passa():
    assert f"--agenda {PASSO_RECOLETA})" in RUN.read_text(encoding="utf-8")
    assert f":passo{PASSO_RECOLETA}:" in _chave_real()


def teste_timer_versionado_nao_ligado_e_desabilitado_nao_atrasado():
    assert _diag([], ativo=False).estado == EstadoSaudeColetor.DESABILITADO


def teste_recoleta_recente_ok_e_saudavel():
    assert _diag([_fecho(5)]).estado == EstadoSaudeColetor.SAUDAVEL


def teste_recoleta_que_parou_ha_dias_acusa():
    assert _diag([_fecho(24 * 3)]).estado == EstadoSaudeColetor.ATRASADO


def teste_backfill_manual_nao_pinta_a_recoleta_de_verde():
    """Mesmo job e mesma origem; só o passo na chave distingue."""
    assert _diag([_fecho(1, passo=None)]).estado == EstadoSaudeColetor.NUNCA_EXECUTADO
    assert _diag([_fecho(1, passo=None), _fecho(24 * 3)]).estado == EstadoSaudeColetor.ATRASADO


def teste_d1_nao_conta_como_recoleta():
    assert _diag([_fecho(1, origem="D-1")]).estado == EstadoSaudeColetor.NUNCA_EXECUTADO


def teste_ultima_recoleta_falhou():
    assert _diag([_fecho(30), _fecho(2, resultado="falhou")]).estado == EstadoSaudeColetor.FALHOU


@pytest.mark.parametrize("timer", [
    "OnCalendar=*-*-* 07:15:00\n",                                              # outra unit
    "Unit=volc-gads-coleta@recoleta.service\nOnCalendar=hourly\n",               # forma livre
    "Unit=volc-gads-coleta@recoleta.service\n"
    "OnCalendar=*-*-* 07:15:00\nOnCalendar=*-*-* 19:15:00\n",                    # duas agendas
])
def teste_timer_fora_da_forma_e_recusado_em_vez_de_palpite(timer):
    with pytest.raises(ValueError):
        job_da_recoleta(timer, "x")
