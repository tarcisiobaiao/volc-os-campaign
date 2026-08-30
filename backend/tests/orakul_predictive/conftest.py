"""Conftest hermético do Predictive Core.

Não importa `app.main`, não lê `.env`, não fala com rede. O conftest pai do
backend ainda pode ser carregado quando a suíte inteira roda; estes testes
não dependem dele e o pacote `services.orakul_predictive` não lê ambiente.
"""

from __future__ import annotations

import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[3]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))
