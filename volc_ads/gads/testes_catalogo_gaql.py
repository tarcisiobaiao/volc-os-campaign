"""Portão: toda GAQL do motor só seleciona o que o SERVIDOR v25 aceita.

Medido em 08/10/2026: 3 das 6 consultas de observabilidade de PMax pediam
subcampos de mensagem (`…asset_coverage.ad_strength_action_items.action_item_type`,
`…primary_status_details.status`). O servidor recusa com UNRECOGNIZED_FIELD e a
consulta inteira cai. O descriptor do SDK não pega isso; o catálogo do servidor pega.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from volc_ads.gads import catalogo

RAIZ = Path(__file__).resolve().parents[2]
INTERP = catalogo.INTERP


GAQLS = list(catalogo.varrer_gaqls(RAIZ))


def test_a_varredura_acha_as_gaqls_do_motor():
    assert len(GAQLS) >= 30, len(GAQLS)


def test_toda_gaql_literal_so_seleciona_o_que_o_servidor_aceita():
    ruins = {}
    for onde, gaql in GAQLS:
        fora = [c for c in catalogo.invalidos(gaql) if INTERP not in c]
        if fora:
            ruins[onde] = fora
    assert not ruins, ruins


def test_builders_de_observabilidade_pmax_so_pedem_campo_selecionavel():
    from volc_ads.observabilidade_pmax import queries as q

    ruins = {nome: catalogo.invalidos(gaql)
             for nome, gaql in q.build_pmax_observability_bundle_queries("5478096539", "1").items()
             if catalogo.invalidos(gaql)}
    assert not ruins, ruins


@pytest.mark.parametrize("pai, filho", [
    ("asset_group.asset_coverage.ad_strength_action_items",
     "asset_group.asset_coverage.ad_strength_action_items.action_item_type"),
    ("asset_group_asset.primary_status_details",
     "asset_group_asset.primary_status_details.status"),
    ("campaign_asset.primary_status_details",
     "campaign_asset.primary_status_details.reason"),
])
def test_mensagem_se_seleciona_inteira(pai, filho):
    """O fato medido com validate_only em 08/10/2026, preso no catálogo."""
    campos = catalogo.carregar()["campos"]
    assert campos[pai][1] is True
    assert filho not in campos


def test_exigir_valida_recusa_antes_de_sair():
    with pytest.raises(ValueError, match="não selecionáveis"):
        catalogo.exigir_valida(
            "SELECT asset_group_asset.primary_status_details.status FROM asset_group_asset")
    ok = "SELECT campaign.id, metrics.clicks FROM campaign"
    assert catalogo.exigir_valida(ok) == ok
