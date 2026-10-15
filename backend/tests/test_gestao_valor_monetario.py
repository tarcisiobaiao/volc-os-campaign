"""W5 — verba e lance só com origem operador ou medido_na_conta, na borda HTTP.

O motor (`volc_ads/gestao/testes_valor.py`) prova que `operacoes()` recusa.
Aqui se prova que o caso de uso recusa ANTES: o pedido com CPC de SERP ou de
ferramenta externa não lê a conta, não grava ledger e não chega ao
`validate_only`; e a proposta antiga sem origem gravada não é aplicada.
Ledger em memória e conta Google de mentira (`gestao_dubles.py`).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

import gestao_dubles as D  # noqa: E402
from app.trafego.gestao.application import erros as E  # noqa: E402
from app.trafego.gestao.application import payload as P  # noqa: E402

CID, CAMP = D.CASA, D.CAMPANHA
ORC = {"tipo": "orcamento.diario", "campaign_id": CAMP, "amount_micros": 36_000_000}
GAQL = ("SELECT campaign.id, campaign_budget.amount_micros FROM campaign "
        f"WHERE campaign.id = {CAMP}")

#: Os pedidos de dinheiro, cada um com o número vindo de fora.
_DINHEIRO = [
    ORC,
    {"tipo": "lance.alvo", "campaign_id": CAMP, "estrategia": "MAXIMIZE_CONVERSIONS",
     "alvo": "tcpa", "valor": 25_000_000},
    {"tipo": "lance.alvo", "campaign_id": CAMP, "estrategia": "TARGET_SPEND",
     "alvo": "teto_cpc", "valor": 2_500_000},
    {"tipo": "lance.estrategia", "campaign_id": CAMP, "nova": "TARGET_SPEND",
     "teto_cpc_micros": 2_500_000},
    {"tipo": "lance.estrategia", "campaign_id": CAMP, "nova": "MAXIMIZE_CONVERSIONS",
     "tcpa_micros": 25_000_000},
]
_IDS = [f"{p['tipo']}:{p.get('alvo') or p.get('nova', '')}" for p in _DINHEIRO]


@pytest.mark.parametrize("origem", ["serp", "ferramenta_externa", "keyword_planner",
                                    "dataforseo", "estimativa_modelo"])
@pytest.mark.parametrize("payload", _DINHEIRO, ids=_IDS)
async def test_origem_externa_e_recusada_sem_ler_conta_nem_gravar(payload, origem):
    g, led, conta = D.gestao_de_teste()
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.propor(CID, {**payload, "origem": origem, "evidencia": f"{origem}: CPC R$ 2,50"},
                       motivo="CPC de mercado", autor="op@volc")
    assert exc.value.codigo == "valor_sem_autoridade"
    assert conta.chamadas == [] and led.ops == []


@pytest.mark.parametrize("payload", _DINHEIRO, ids=_IDS)
async def test_numero_sem_origem_e_recusado(payload):
    g, led, conta = D.gestao_de_teste()
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.propor(CID, payload, motivo="m", autor="op@volc")
    assert exc.value.codigo == "valor_sem_origem"
    assert conta.chamadas == [] and led.ops == []


async def test_operador_e_carimbado_pelo_servidor_e_nao_pela_tela():
    g, _, _ = D.gestao_de_teste()
    r = await g.propor(CID, {**ORC, "origem": "operador", "evidencia": "operador:outro@ontem"},
                       motivo="CPA estável", autor="op@volc")
    origem = r["proposta"]["valor_proposto"]["origem_valor"]
    assert origem["origem"] == "operador"
    assert origem["evidencia"].startswith("operador:op@volc@") and "outro" not in origem["evidencia"]


async def test_medido_na_conta_com_a_gaql_e_aceito():
    g, _, _ = D.gestao_de_teste()
    r = await g.propor(CID, {**ORC, "origem": "medido_na_conta", "evidencia": GAQL},
                       motivo="volta ao valor medido", autor="op@volc")
    assert r["proposta"]["valor_proposto"]["origem_valor"] == {
        "origem": "medido_na_conta", "evidencia": GAQL}


async def test_medido_na_conta_sem_a_gaql_e_recusado():
    g, led, conta = D.gestao_de_teste()
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.propor(CID, {**ORC, "origem": "medido_na_conta", "evidencia": "olhei no painel"},
                       motivo="m", autor="op@volc")
    assert exc.value.codigo == "valor_sem_autoridade" and conta.chamadas == [] and not led.ops


async def test_proposta_antiga_sem_origem_nao_e_aplicada_nem_ensaiada():
    """Proposta gravada antes do W5: reconstrói (verificar/reverter seguem), não aplica."""
    g, led, conta = D.gestao_de_teste()
    r = await g.propor(CID, {**ORC, "origem": "operador"}, motivo="m", autor="op@volc")
    pid = r["proposta"]["proposta_id"]
    led.propostas[pid]["valor_proposto"].pop("origem_valor")  # como uma linha antiga
    p = await g.ledger.proposta(pid)
    assert P.acao_da_proposta(p).verba.origem == "nao_informada"
    await g.aprovar(pid, "aprovada", motivo=None, aprovador="admin@volc",
                    diff_apresentado={"valor_atual": p["valor_atual"],
                                      "valor_proposto": p["valor_proposto"]})
    antes = len(conta.chamadas)
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.aplicar(pid, executor="adm")
    assert exc.value.codigo == "valor_sem_autoridade"
    assert not led.aplicacoes and len(conta.chamadas) == antes  # nem ler_antes, nem validar
