"""Julgamento editorial pertence ao revisor; contratos técnicos bloqueiam.

Inventário de 10/10/2026 dos bloqueios ativos no caminho canônico (V2).
"""
from types import SimpleNamespace as NS

import pytest

from funnelforge.pipeline.retry_policy import classe_da_issue, classificar_issues

PREFERENCIA = ["cta_generic", "cta_editorial_execution", "cta_external_channel",
               "official_links_few", "cta_longo", "cta_rotulo_repetido", "fear_language",
               "official_impersonation", "composicao_paredao_de_texto",
               "plano_visual_nao_cumprido", "critical_claim_without_citation",
               "ungrounded_critical_claim",
               # 10/10/2026: similaridade de palavras entre páginas do mesmo tema
               # é pista para o revisor, não reprovação técnica.
               "similaridade_lexical", "duplicate_content", "hub_not_distinct"]
TECNICO_OU_FATO = ["unbalanced", "has_script", "lp_schema", "lp_missing_slot", "lp_sections",
                   "ad_slot_inseguro", "bloco_malformado", "cross_domain",
                   "unplanned_external_link", "fake_credential", "wrong_cnpj",
                   "terminal_exit_not_authorized", "self_loop",
                   "bloco_sem_fechamento", "texto_fora_dos_blocos"]


@pytest.mark.parametrize("code", PREFERENCIA)
def test_preferencia_editorial_nao_reescreve_a_pagina(code):
    assert classe_da_issue(NS(code=code, message="")) == "patchavel"
    veredito = classificar_issues([NS(code=code, message="")], {"editorial_v2": True})
    assert veredito.retentar is False and veredito.classe == "patchavel"


@pytest.mark.parametrize("code", TECNICO_OU_FATO)
def test_integridade_tecnica_e_factual_continua_bloqueando(code):
    assert classe_da_issue(NS(code=code, message="")) == "estrutural"
