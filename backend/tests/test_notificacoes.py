"""Contrato da central de notificações.

Estas provas são herméticas: nenhum teste consulta ou altera conta do Google.
"""
from __future__ import annotations

from app.trafego import projecao
from volc_ads.entrega import Diagnostico


def _diagnostico() -> Diagnostico:
    return Diagnostico(
        campaign_id="24155134757",
        campaign_name="BR - Maquininha de Cartão",
        status="ENABLED",
        horas_ligada=26.4,
        impressoes=1,
        cliques=0,
        custo=0.0,
        lance=0.12,
        orcamento=10.0,
    )


def test_a_notificacao_carrega_a_conta_que_identifica_o_destino():
    alerta = projecao.alerta_de_entrega(
        _diagnostico(),
        customer_id="8017851692",
        customer_name="Crédito Up",
    )

    assert alerta["customer_id"] == "8017851692"
    assert alerta["customer_name"] == "Crédito Up"
    assert alerta["campaign_id"] == "24155134757"


def test_a_notificacao_nao_inventa_cpc_de_mercado():
    alerta = projecao.alerta_de_entrega(
        _diagnostico(), customer_id="8017851692")

    campos = {campo.lower() for campo in alerta}
    assert not campos.intersection({"cpc_de_mercado", "cpc_estimado", "mediana"})
    assert alerta["teto_de_cliques"] == 83

