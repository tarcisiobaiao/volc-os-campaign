"""Leitura do "antes" e a tradução para o ledger v10_02 — sem rede e sem banco."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from google.ads.googleads.client import GoogleAdsClient

from volc_ads.gestao import acoes as A
from volc_ads.gestao import estado, ledger
from volc_ads.gestao.acoes import AcaoRecusada
from volc_ads.gestao.lote import ResultadoAcao
from volc_ads.gads.errors import ErroGads
from volc_ads.gestao.valor import ValorMonetario


def OP(micros):
    return ValorMonetario(micros, "operador", "operador:teste/operador@2026-10-15T00:00:00+00:00",
                          "valor digitado no teste")

CID = "5478096539"
CAMP = 24278665189
AGORA = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def _gt():
    c = GoogleAdsClient.__new__(GoogleAdsClient)
    c.version = "v25"
    c.use_proto_plus = True
    return c.get_type


GT = _gt()


def _linha_orcamento(compartilhado=False, n=1):
    r = GT("GoogleAdsRow")
    r.campaign.id = CAMP
    r.campaign_budget.id = 15886629542
    r.campaign_budget.amount_micros = 30_000_000
    r.campaign_budget.period = "DAILY"
    r.campaign_budget.explicitly_shared = compartilhado
    r.campaign_budget.reference_count = n
    r.customer.currency_code = "BRL"
    return r


def teste_ler_confere_gaql_carimba_e_interpreta():
    vistas = []

    def buscar(cid, q):
        vistas.append((cid, q))
        return [_linha_orcamento()]

    a = A.AlterarOrcamento(CAMP, 15886629542, OP(35_000_000))
    antes = estado.ler(CID, a, buscar=buscar, agora=lambda: AGORA)
    assert antes.lido_em == AGORA and antes.dados["verba_diaria_micros"] == 30_000_000
    assert vistas == [(CID, antes.consultas[0])]


def teste_ler_recusa_quando_o_estado_nao_permite():
    a = A.AlterarOrcamento(CAMP, 15886629542, OP(35_000_000))
    with pytest.raises(AcaoRecusada, match="compartilhado"):
        estado.ler(CID, a, buscar=lambda c, q: [_linha_orcamento(True, 4)])
    sem = estado.ler(CID, a, buscar=lambda c, q: [_linha_orcamento(True, 4)], conferir=False)
    assert sem.dados["campanhas_no_orcamento"] == 4


def teste_gaql_fora_do_catalogo_nao_sai(monkeypatch):
    a = A.AlterarStatus("campanha", CAMP, "PAUSED")
    monkeypatch.setattr(type(a), "consultas_antes",
                        lambda self, cid: ("SELECT campaign.campo_que_nao_existe FROM campaign",))
    chamou = []
    with pytest.raises(ValueError, match="não selecionáveis"):
        estado.ler(CID, a, buscar=lambda c, q: chamou.append(q) or [])
    assert chamou == []


# ── ledger ──────────────────────────────────────────────────────────────────

_CHAVE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


def teste_proposta_de_orcamento_tem_delta_moeda_e_chave_do_teto():
    a = A.AlterarOrcamento(CAMP, 15886629542, OP(36_000_000))
    antes = a.interpretar_antes(([_linha_orcamento()],))
    p = ledger.proposta(a, CID, antes, AGORA)
    assert p["operacao"] == "orcamento.diario" and p["alvo_nivel"] == "campanha"
    assert p["alvo_chave"] == f"google_ads:{CID}:campanha:{CAMP}"
    assert p["valor_proposto"]["verba_diaria_micros"] == 36_000_000  # lida pelo gatilho do teto
    assert (p["delta_pct"], p["delta_absoluto_micros"], p["moeda"]) == (20.0, 6_000_000, "BRL")
    assert p["valor_atual"] != p["valor_proposto"]
    assert _CHAVE.match(p["idempotency_key"])


def teste_chave_de_idempotencia_muda_com_o_antes():
    a = A.AlterarStatus("campanha", CAMP, "PAUSED")
    k1 = ledger.chave_idempotencia(a, CID, {"existe": True, "status": "ENABLED"})
    k2 = ledger.chave_idempotencia(a, CID, {"existe": True, "status": "ENABLED"})
    k3 = ledger.chave_idempotencia(a, CID, {"existe": True, "status": "PAUSED"})
    assert k1 == k2 != k3 and _CHAVE.match(k1)


def teste_proposta_sem_numero_nao_inventa_delta():
    a = A.AdicionarNegativas("campanha", CAMP, (A.Termo("x"),))
    p = ledger.proposta(a, CID, {"negativas_existentes": 0, "chaves": []}, AGORA)
    assert (p["delta_pct"], p["delta_absoluto_micros"], p["moeda"]) == (None, None, None)


def teste_troas_tem_so_percentual():
    a = A.AlterarAlvoDeLance(CAMP, "MAXIMIZE_CONVERSION_VALUE", "troas", 5.0)
    p = ledger.proposta(a, CID, {"troas": 4.0, "moeda": "BRL"}, AGORA)
    assert (p["delta_pct"], p["delta_absoluto_micros"], p["moeda"]) == (25.0, None, None)


def teste_desfecho_parcial_vira_erro_com_os_criados():
    rn = f"customers/{CID}/campaignCriteria/{CAMP}~1"
    erro = ErroGads("criterion_error", "KEYWORD_HAS_INVALID_CHARS", "inválido", indice_operacao=1)
    r = ResultadoAcao(A.AdicionarNegativas("campanha", CAMP, (A.Termo("a"), A.Termo("b"))),
                      "parcial", (erro,), (rn,), (0, 2))
    d = ledger.desfecho_da_aplicacao(r)
    assert d["desfecho"] == "erro" and d["resposta_bruta"]["criados"] == [rn]
    assert d["erro_codigo"] == "criterion_error.KEYWORD_HAS_INVALID_CHARS"
    ok = ledger.desfecho_da_aplicacao(ResultadoAcao(r.acao, "ok"))
    assert ok["desfecho"] == "sucesso" and "erro_mensagem" not in ok
    with pytest.raises(ValueError):
        ledger.desfecho_da_aplicacao(ResultadoAcao(r.acao, "nao_validavel"))


def teste_reversao_sai_do_valor_anterior_e_diz_quando_nao_ha():
    a = A.AlterarStatus("campanha", CAMP, "PAUSED")
    rev = ledger.reversao(a, {"existe": True, "status": "ENABLED"})
    assert rev["valor_restaurado"]["reversivel"]
    assert rev["valor_restaurado"]["passos"] == [{"operacao": "status",
                                                  "valor": {"status": "ENABLED"}}]
    rec = ledger.reversao(A.AplicarRecomendacao(f"customers/{CID}/recommendations/x1"), {})
    assert not rec["valor_restaurado"]["reversivel"] and "change_event" in rec["valor_restaurado"]["motivo"]
