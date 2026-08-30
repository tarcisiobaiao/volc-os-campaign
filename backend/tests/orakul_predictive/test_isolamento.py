"""Sem rede, sem .env, sem mutação externa."""

from __future__ import annotations

import pytest

from services.orakul_predictive.excecoes import IsolamentoViolado
from services.orakul_predictive.isolamento import auditar_fonte_pacote
from services.orakul_predictive.motor import recusar_executor


def test_pacote_nao_importa_rede_nem_dotenv():
    auditar_fonte_pacote()


def test_nao_existe_executor_de_campanha():
    with pytest.raises(IsolamentoViolado):
        recusar_executor()
