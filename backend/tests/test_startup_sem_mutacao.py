"""Iniciar o backend não autoriza manutenção no banco configurado."""
import asyncio

import pytest

from app.main import _reconciliar_runs_orfaos


@pytest.mark.parametrize("flag", [None, "0", "true", ""])
def test_startup_nao_constroi_cliente_nem_reconcilia_sem_optin(monkeypatch, flag):
    from app.services import supabase_service

    def proibido(*args, **kwargs):
        pytest.fail("startup sem opt-in tentou construir cliente de banco")

    monkeypatch.setattr(supabase_service, "SupabaseService", proibido)
    monkeypatch.delenv("VOLC_RECONCILIAR_RUNS_NO_STARTUP", raising=False)
    if flag is not None:
        monkeypatch.setenv("VOLC_RECONCILIAR_RUNS_NO_STARTUP", flag)
    asyncio.run(_reconciliar_runs_orfaos())
