from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.trafego.meta import dominio as dom
from app.trafego.meta import persistencia as per


AGORA = datetime(2026, 9, 4, 12, tzinfo=timezone.utc)


def leitura_valida() -> dom.LeituraDaHierarquia:
    return dom.LeituraDaHierarquia(
        conta_externa="123",
        campanhas=(dom.ObjetoMeta("campaign", "10", "C", "PAUSED", "PAUSED",
                                  objetivo="OUTCOME_TRAFFIC"),),
        conjuntos=(dom.ObjetoMeta("adset", "20", "S", "PAUSED", "PAUSED",
                                  parent_id_externo="10",
                                  optimization_goal="LANDING_PAGE_VIEWS"),),
        anuncios=(dom.ObjetoMeta("ad", "30", "A", "PAUSED", "PAUSED",
                                 parent_id_externo="20", creative_id_externo="40"),),
        criativos=(dom.ObjetoMeta("creative", "40", "CR", None, None,
                                  object_story_id="page_99"),),
        paginas_lidas=4,
    )


def test_mapeamento_e_allowlist_tipados_sem_documento_bruto():
    linhas = per.linhas_da_leitura(
        leitura_valida(), AGORA, conta_ativo_id="asset:meta-ad-account:piloto")
    assert tuple(linhas) == per.TABELAS_META
    assert len(linhas["trafego_meta_ad_creative_binding"]) == 1
    assert linhas["trafego_meta_campaign"][0]["ad_account_ativo_id"].startswith("asset:")
    texto = repr(linhas).lower()
    for proibido in ("access_token", "client_secret", "localizador", "raw_response"):
        assert proibido not in texto


def test_hierarquia_orfa_e_recusada_antes_de_persistir():
    leitura = dom.LeituraDaHierarquia(
        conta_externa="123", campanhas=(),
        conjuntos=(dom.ObjetoMeta("adset", "20", None, None, None,
                                  parent_id_externo="999"),),
        anuncios=(), criativos=(), paginas_lidas=4)
    with pytest.raises(dom.ContratoMetaInvalido, match="fora da leitura"):
        per.linhas_da_leitura(
            leitura, AGORA, conta_ativo_id="asset:meta-ad-account:piloto")
