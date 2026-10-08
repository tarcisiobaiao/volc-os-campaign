from __future__ import annotations

from pathlib import Path

import pytest

from funnelforge.config.perfil import aplicar_perfil
from funnelforge.config.settings import load_settings, problemas_do_modo_openai


def test_preset_rapido_chatgpt_e_fechado_sem_fallback_faturado():
    settings = load_settings(config_path=Path("config.yaml"))
    novo = aplicar_perfil(settings, {
        "preset": "rapido_chatgpt",
        "site": {
            "domain": "https://creditoup.com.br",
            "rodape_institucional": "Rodapé medido.",
            "rodape_institucional_persistente": True,
        },
    })

    # O nome do preset é compatibilidade de API. Qualidade não tem mais ramo
    # reduzido: a única aceleração é page_workers/cache.
    assert novo.run.perfil == "completo"
    assert novo.run.editorial_v2 is True
    assert novo.run.page_workers == 3 and novo.run.dossie_factual is True
    assert novo.run.publish_status == "draft"
    assert novo.run.imagens_habilitadas is True
    assert novo.run.official_screenshots is True
    assert novo.openai.auth_mode == "chatgpt_plan"
    assert novo.openai.somente_plano is True
    assert novo.steps["dossie"].web_search is True
    assert all(p.model.startswith("chatgpt/") for p in novo.steps.values())
    assert all(not p.fallbacks for p in novo.steps.values())
    # O client_id público vem do Keychain/host em runtime; não é defeito do
    # preset nem deve ser persistido no perfil do run.
    assert problemas_do_modo_openai(novo) == [
        "openai.client_id vazio: registre o client_id do VOLC antes do login"
    ]


def test_preset_desconhecido_falha_cedo():
    settings = load_settings(config_path=Path("config.yaml"))
    with pytest.raises(ValueError, match="preset de execução desconhecido"):
        aplicar_perfil(settings, {"preset": "talvez"})
