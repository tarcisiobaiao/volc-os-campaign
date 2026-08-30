"""Projeção autenticada do Decision Intelligence Lab.

O adapter só lê o dataset versionado do monorepo. Não resolve campanha real,
não consulta inventário, Supabase, Google Ads ou n8n e não expõe executor.
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Any


_RAIZ = pathlib.Path(__file__).resolve().parents[3]
_SCENARIO_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


def _dominio():
    if str(_RAIZ) not in sys.path:
        sys.path.insert(0, str(_RAIZ))
    from volc_ads.inteligencia_decisao import (  # noqa: PLC0415
        CriticoDeterministico,
        catalogo_de_cenarios,
        executar_replay,
    )
    from volc_ads.inteligencia_decisao.replay import projetar_cenario  # noqa: PLC0415

    return CriticoDeterministico, catalogo_de_cenarios, executar_replay, projetar_cenario


def projetar(scenario_id: str) -> dict[str, Any]:
    """Retorna uma fotografia navegável ou levanta `KeyError` para ID ausente."""

    if not _SCENARIO_ID.fullmatch(str(scenario_id or "")):
        raise KeyError(scenario_id)
    Critico, catalogo, replay, projetar_cenario = _dominio()
    resultado = projetar_cenario(scenario_id, critico=Critico())
    avaliacao = replay()
    resultado["catalogo"] = catalogo()
    resultado["replay"] = {
        "dataset_version": avaliacao["dataset_version"],
        "as_of": avaliacao["as_of"],
        "total": avaliacao["total"],
        "passaram": avaliacao["passaram"],
        "falharam": avaliacao["falharam"],
    }
    resultado["isolamento"] = {
        "somente_sintetico": True,
        "entra_em_contagens_reais": False,
        "aceita_volc_campaign_id": False,
        "oferece_aplicar": False,
        "chamadas_externas": 0,
        "escopo_chamadas_externas": "dominio_do_laboratorio; autenticacao HTTP fica fora desta contagem",
        "mutacoes_executadas": 0,
    }
    return resultado
