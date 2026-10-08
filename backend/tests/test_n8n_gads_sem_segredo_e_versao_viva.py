"""Workflows n8n versionados não carregam credencial literal nem versão morta da API.

Medido em 08/10/2026:
- `backend/n8n_kw_pautador.json` tinha developer token, MCC e customer ID
  LITERAIS no nó de config. O MCC e a conta eram de terceiros (Fla&Fe/D2).
- `n8n/pautador_kw_mining_webhook.json` chamava a v21, que devolve 404.

Em n8n, valor literal também começa com `=`; só `={{ … }}` é expressão.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted(
    p for p in [*RAIZ.glob("n8n/*.json"), *RAIZ.glob("backend/*.json")]
    if "googleads.googleapis.com" in p.read_text(encoding="utf-8")
)
CAMPOS_DE_CREDENCIAL = {"developer_token", "mcc_id", "customer_id", "login_customer_id"}
# v23 é a mais antiga ainda servida pela lib 33.0.0; v21 e v22 estão aposentadas.
VERSAO_MINIMA = 23


def _atribuicoes(wf: dict):
    for no in wf.get("nodes", []):
        for a in no.get("parameters", {}).get("assignments", {}).get("assignments", []):
            yield no["name"], a


def test_ha_workflows_google_ads_para_checar():
    assert len(WORKFLOWS) >= 3, [p.name for p in WORKFLOWS]


@pytest.mark.parametrize("caminho", WORKFLOWS, ids=lambda p: p.name)
def test_credencial_nunca_e_literal(caminho: Path):
    wf = json.loads(caminho.read_text(encoding="utf-8"))
    literais = [
        f"{no}:{a['name']}"
        for no, a in _atribuicoes(wf)
        if a.get("name") in CAMPOS_DE_CREDENCIAL
        and str(a.get("value", "")).strip()
        and not str(a.get("value", "")).lstrip("=").strip().startswith("{{")
    ]
    assert not literais, f"{caminho.name}: credencial literal em {literais}"


@pytest.mark.parametrize("caminho", WORKFLOWS, ids=lambda p: p.name)
def test_nenhuma_url_em_versao_aposentada(caminho: Path):
    texto = caminho.read_text(encoding="utf-8")
    versoes = {int(v) for v in re.findall(r"googleads\.googleapis\.com/v(\d+)/", texto)}
    mortas = sorted(v for v in versoes if v < VERSAO_MINIMA)
    assert not mortas, f"{caminho.name}: versões aposentadas {mortas}"
