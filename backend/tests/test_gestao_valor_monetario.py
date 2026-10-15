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
from app.trafego.gestao.application.payload import Ator  # noqa: E402
from volc_ads.gestao.valor import sha256_canonico  # noqa: E402

CID, CAMP = D.CASA, D.CAMPANHA
ORC = {"tipo": "orcamento.diario", "campaign_id": CAMP, "amount_micros": 36_000_000}
ATOR = Ator(sub="u2", papel="OPERATOR", origem="sessao")
SERVICO = Ator(sub="svc-n8n", papel="SERVICE", origem="servico")
JUST = "CPA estável, verba limitando a entrega"

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
                       motivo=JUST, autor="op@volc", ator=ATOR)
    assert exc.value.codigo == "valor_sem_autoridade"
    assert conta.chamadas == [] and led.ops == []


@pytest.mark.parametrize("payload", _DINHEIRO, ids=_IDS)
async def test_numero_sem_origem_e_recusado(payload):
    g, led, conta = D.gestao_de_teste()
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.propor(CID, payload, motivo=JUST, autor="op@volc", ator=ATOR)
    assert exc.value.codigo == "valor_sem_origem"
    assert conta.chamadas == [] and led.ops == []


async def test_operador_e_escrito_pelo_servidor_e_nao_pela_tela():
    g, _, _ = D.gestao_de_teste()
    r = await g.propor(CID, {**ORC, "origem": "operador", "evidencia": "operador:outro/ADMIN@ontem"},
                       motivo=JUST, autor="op@volc", ator=ATOR)
    origem = r["proposta"]["valor_proposto"]["origem_valor"]
    assert origem["origem"] == "operador" and origem["justificativa"] == JUST
    assert origem["evidencia"].startswith("operador:u2/OPERATOR@") and "outro" not in origem["evidencia"]


async def test_identidade_de_servico_nao_e_operador():
    """O caso R2 da revisão: um agente n8n se declarando operador com número de SERP."""
    g, led, conta = D.gestao_de_teste()
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.propor(CID, {**ORC, "origem": "operador"}, motivo=JUST,
                       autor="agente-n8n@volc", ator=SERVICO)
    assert exc.value.codigo == "valor_sem_autoridade" and "serviço" in str(exc.value)
    assert conta.chamadas == [] and led.ops == []


async def test_operador_sem_identidade_ou_sem_justificativa_e_recusado():
    g, led, _ = D.gestao_de_teste()
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.propor(CID, {**ORC, "origem": "operador"}, motivo=JUST, autor="op@volc")
    assert exc.value.codigo == "valor_sem_autoridade"
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.propor(CID, {**ORC, "origem": "operador"}, motivo="curto", autor="op@volc",
                       ator=ATOR)
    assert exc.value.codigo == "valor_sem_autoridade" and "justificativa" in str(exc.value)
    assert not led.ops


async def test_semrush_pela_http_e_recusado():
    """O caso R1 da revisão: GAQL com comentário de ferramenta externa não é medição."""
    g, led, conta = D.gestao_de_teste()
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.propor(CID, {**ORC, "origem": "medido_na_conta",
                             "evidencia": "SELECT metrics.average_cpc FROM keyword_view -- semrush"},
                       motivo=JUST, autor="op@volc", ator=ATOR)
    assert exc.value.codigo == "valor_sem_autoridade"
    assert conta.chamadas == [] and led.ops == []


async def _medicao_guardada(g, conta):
    """Uma proposta qualquer grava o 'antes' que o backend leu; depois a conta muda."""
    r = await g.propor(CID, {**ORC, "origem": "operador"}, motivo=JUST, autor="op@volc",
                       ator=ATOR)
    p = r["proposta"]
    conta.mundo[("orcamento.diario", CAMP)]["verba_diaria_micros"] = 33_000_000
    return p, {"proposta_id": p["proposta_id"], "campo": "verba_diaria_micros",
               "as_of": p["valor_atual_lido_em"], "sha256": sha256_canonico(p["valor_atual"])}


async def test_medido_na_conta_que_aponta_a_leitura_guardada_e_aceito():
    g, _, conta = D.gestao_de_teste()
    antiga, medicao = await _medicao_guardada(g, conta)
    lido = antiga["valor_atual"]["verba_diaria_micros"]
    r = await g.propor(CID, {**ORC, "amount_micros": lido, "origem": "medido_na_conta",
                             "medicao": medicao},
                       motivo="volta ao valor medido antes", autor="op@volc", ator=ATOR)
    o = r["proposta"]["valor_proposto"]["origem_valor"]
    assert o["origem"] == "medido_na_conta"
    assert o["evidencia"].startswith(f"medicao:trafego_proposta.valor_atual/{antiga['proposta_id']}#")


@pytest.mark.parametrize("estrago", ["sha256", "as_of", "valor", "proposta", "campo"])
async def test_medido_na_conta_que_nao_confere_com_o_guardado_e_recusado(estrago):
    g, led, conta = D.gestao_de_teste()
    antiga, medicao = await _medicao_guardada(g, conta)
    lido = antiga["valor_atual"]["verba_diaria_micros"]
    pedido = {**ORC, "amount_micros": lido, "origem": "medido_na_conta", "medicao": dict(medicao)}
    if estrago == "sha256":
        pedido["medicao"]["sha256"] = "0" * 64
    elif estrago == "as_of":
        pedido["medicao"]["as_of"] = "2026-01-01T00:00:00+00:00"
    elif estrago == "valor":
        pedido["amount_micros"] = lido + 1_000_000
    elif estrago == "proposta":
        pedido["medicao"]["proposta_id"] = "nao-existe"
    else:
        pedido["medicao"]["campo"] = "teto_cpc_micros"
    n = len(conta.chamadas)
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.propor(CID, pedido, motivo=JUST, autor="op@volc", ator=ATOR)
    assert exc.value.codigo == "valor_sem_autoridade"
    assert len(conta.chamadas) == n  # recusa antes de ler a conta


async def _proposta_antiga(g, led):
    """Uma proposta como as gravadas antes do W5: sem `origem_valor`."""
    r = await g.propor(CID, {**ORC, "origem": "operador"}, motivo=JUST, autor="op@volc",
                       ator=ATOR)
    pid = r["proposta"]["proposta_id"]
    led.propostas[pid]["valor_proposto"].pop("origem_valor")
    return await g.ledger.proposta(pid)


async def test_proposta_antiga_sem_origem_nao_e_aprovada():
    g, led, _ = D.gestao_de_teste()
    p = await _proposta_antiga(g, led)
    assert P.acao_da_proposta(p).verba.origem == "nao_informada"
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.aprovar(p["proposta_id"], "aprovada", motivo=None, aprovador="admin@volc",
                        diff_apresentado={"valor_atual": p["valor_atual"],
                                          "valor_proposto": p["valor_proposto"]})
    assert exc.value.codigo == "valor_sem_autoridade" and not led.aprovacoes


async def test_proposta_antiga_aprovada_nao_e_aplicada_nem_ensaiada():
    """Aprovada antes do W5 (sem a reconferência): aplicar ainda recusa."""
    g, led, conta = D.gestao_de_teste()
    r = await g.propor(CID, {**ORC, "origem": "operador"}, motivo=JUST, autor="op@volc",
                       ator=ATOR)
    pid = r["proposta"]["proposta_id"]
    p = await g.ledger.proposta(pid)
    await g.aprovar(pid, "aprovada", motivo=None, aprovador="admin@volc",
                    diff_apresentado={"valor_atual": p["valor_atual"],
                                      "valor_proposto": p["valor_proposto"]})
    led.propostas[pid]["valor_proposto"].pop("origem_valor")  # como uma linha antiga
    antes = len(conta.chamadas)
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.aplicar(pid, executor="adm")
    assert exc.value.codigo == "valor_sem_autoridade"
    assert not led.aplicacoes and len(conta.chamadas) == antes  # nem ler_antes, nem validar


async def test_proposta_antiga_viva_nao_segura_a_chave_de_idempotencia():
    """O caso R3 da revisão: a antiga vira `cancelada` e a nova nasce, com origem."""
    g, led, _ = D.gestao_de_teste()
    antiga = await _proposta_antiga(g, led)
    r = await g.propor(CID, {**ORC, "origem": "operador"}, motivo=JUST, autor="op@volc",
                       ator=ATOR)
    assert not r["ja_existia"] and r["proposta"]["proposta_id"] != antiga["proposta_id"]
    assert r["proposta"]["valor_proposto"]["origem_valor"]["origem"] == "operador"
    assert led.propostas[antiga["proposta_id"]]["estado"] == "cancelada"


@pytest.mark.parametrize("payload", [
    {"tipo": "lance.alvo", "campaign_id": CAMP, "estrategia": "TARGET_ROAS", "alvo": "troas",
     "valor": 4.0, "origem": "serp"},
    {"tipo": "lance.estrategia", "campaign_id": CAMP, "nova": "MAXIMIZE_CONVERSION_VALUE",
     "troas": 4.0, "origem": "ferramenta_externa"},
    {"tipo": "lance.estrategia", "campaign_id": CAMP, "nova": "TARGET_SPEND",
     "teto_cpc_micros": 0, "origem": "serp"},
], ids=["alvo_troas", "troca_troas", "troca_teto_zero"])
async def test_origem_que_nao_autoriza_nao_some_no_troas_nem_no_zero(payload):
    """O caso R5: a declaração de origem externa não é descartada em silêncio."""
    g, led, conta = D.gestao_de_teste()
    with pytest.raises(E.AcaoInvalida) as exc:
        await g.propor(CID, payload, motivo=JUST, autor="op@volc", ator=ATOR)
    assert exc.value.codigo == "valor_sem_autoridade" and conta.chamadas == [] and not led.ops
