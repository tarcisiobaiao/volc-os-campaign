"""Gera o lote fixo que o backend usa para testar a carteira em sombra (W13).

O backend não importa o motor (`volc_lab` exige jsonschema, que só existe no
venv do Freedom Lab). Ele lê este lote já gravado, e o teste
`test_fixture_da_carteira_no_backend_e_o_que_o_motor_grava` (no lab) regenera
em pasta temporária e exige os mesmos bytes. Se o motor mudar, aquele teste
falha e o lote é regenerado com:

    cd tools/freedom-lab && PYTHONPATH=src python3 tests/gerar_fixture_carteira_backend.py

Destino: backend/tests/fixtures/carteira_shadow/ (arquivo gerado; não editar à mão).
Dados sintéticos: conta e campanhas inventadas, nenhuma rede, nenhum banco.
"""
from __future__ import annotations

import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

from volc_lab.sombra_carteira import aplicacao
from volc_lab.sombra_carteira.portas import Leitura

DESTINO = Path(__file__).resolve().parents[3] / "backend" / "tests" / "fixtures" / "carteira_shadow"
CONTA = "1112223334"
HOJE = date(2026, 10, 15)
LIDO = "2026-10-15T12:00:00Z"
BASE_REF = "a8059ba0"
RUIM, SEM_CAMBIO = "900000000001", "900000000003"


def _custo(cid, d, micros, cliques=40):
    return {"customer_id": CONTA, "campaign_id": cid, "metric_date": d.isoformat(), "segmentos": {},
            "custo_micros": micros, "cliques": cliques, "currency_code": "BRL", "janela_fechada": True,
            "campaign_name": f"camp {cid[-1]}", "campaign_status": "ENABLED", "valor_conversoes": 10.0,
            "colhida_em": LIDO, "origem_janela": "backfill"}


def _receita(cid, d, valor, moeda):
    return {"fonte": "joinads", "chave": {"date": d.isoformat(), "utm_campaign_value": cid,
                                          "joinads_domain": "a.com.br"},
            "data_referencia": d.isoformat(), "moeda": moeda, "receita": valor,
            # O câmbio da ingestão não é usado pelo motor; fica como o W12 gravaria.
            "receita_brl": None, "cambio_modo": "defasada", "cambio_taxa": None,
            "cambio_defasagem_dias": 40, "coletado_em": LIDO, "removida": False}


class _Fonte:
    def __init__(self, c, r):
        self.c, self.r = c, r

    def custo_campanha_dia(self, conta, inicio, fim):
        return Leitura(tuple(self.c), LIDO, "fixture: google_ads_campanha_dia sintético")

    def receita_vigente(self, inicio, fim):
        return Leitura(tuple(self.r), LIDO, "fixture: receita_as_of sintética")

    def cotacoes(self, pedidos, conhecido_ate, max_defasagem_dias):
        # USD com a cotação da véspera; EUR só com cotação velha demais (sem dado).
        linhas = []
        for par, d in pedidos:
            usd = par == "USD/BRL"
            linhas.append({"par": par, "data": d.isoformat(), "modo": "anterior" if usd else "defasada",
                           "taxa": 5.4 if usd else None,
                           "data_cotacao": (d - timedelta(days=1 if usd else 40)).isoformat(),
                           "defasagem_dias": 1 if usd else 40, "cotacao_id": 7, "fonte": "ptax"})
        return Leitura(tuple(linhas), LIDO, "fixture: cambio_resolver sintético")


def gerar(destino: Path) -> dict:
    c, r = [], []
    for i in range(1, 21):
        d = HOJE - timedelta(days=i)
        c += [_custo(RUIM, d, 30_000_000), _custo(SEM_CAMBIO, d, 10_000_000)]
        r += [_receita(RUIM, d, 0.30, "USD"), _receita(SEM_CAMBIO, d, 5.0, "EUR")]
    f = _Fonte(c, r)
    return aplicacao.gerar_lote(CONTA, f, f, f, destino, base_ref=BASE_REF, hoje=HOJE)


if __name__ == "__main__":
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    saida = gerar(DESTINO)
    print(f"{len(saida['novos'])} experimentos em {DESTINO}", file=sys.stderr)
