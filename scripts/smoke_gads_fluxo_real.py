"""Smoke do fluxo real Google Ads — backend em processo, dependências reais.

Real: Supabase oficial (leitura), Google Ads (leitura + validate_only),
mensuração, portão de destino, canário, trava de escrita.

⚠️ ÚNICA substituição, declarada: a IDENTIDADE (um admin de teste no lugar do
login Supabase), porque o smoke não tem senha de usuário. Nenhuma outra
dependência é trocada por dublê.

Não escreve no Google (a trava fica fechada: FORGE_PERMITIR_ESCRITA removida do
ambiente) e não chama nenhuma rota que grave no banco.

Uso (do worktree, com o .env real do backend):
    set -a; . backend/.env; set +a
    cd backend && PYTHONPATH=..:. .venv/bin/python ../scripts/smoke_gads_fluxo_real.py
"""
from __future__ import annotations

import json
import os
import sys
import time

os.environ.pop("FORGE_PERMITIR_ESCRITA", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario  # noqa: E402

DUBLE = Identidade(sub="00000000-0000-0000-0000-000000000000",
                   email="smoke@agenciavolc.com.br", papel="ADMIN", origem="sessao")
app.dependency_overrides[exigir_usuario] = lambda: DUBLE
app.dependency_overrides[exigir_admin] = lambda: DUBLE
c = TestClient(app)

CONTA, MCC = "5478096539", "6016739364"
OPP, RUN = 106, 28   # pautador_funnel_runs.id 28 = guia-gas-do-povo-20261008-134021 (sem cluster)
OPP_OK, RUN_OK = 65, 9  # card 65 (FGTS): passa da mineração
CAMPANHA_ATIVA = "24278665189"   # Senac: só LEITURA aqui
resultado: dict = {"identidade": "DUBLÊ declarado (admin de teste)", "passos": []}


def passo(nome, resp, resumo):
    try:
        corpo = resp.json()
    except Exception:  # noqa: BLE001
        corpo = {"bruto": resp.text[:300]}
    item = {"passo": nome, "http": resp.status_code, "resumo": resumo(corpo) if resp.status_code < 500 else corpo}
    resultado["passos"].append(item)
    print(f"[{resp.status_code}] {nome}: {json.dumps(item['resumo'], ensure_ascii=False)[:400]}")


t0 = time.time()
passo("trava de escrita", c.get("/api/trafego/trava"),
      lambda b: {"escrita_permitida": b.get("escrita_permitida"), "env_presente": b.get("env_presente")})
passo("esquema dos canais", c.get("/api/trafego/canais/esquema"),
      lambda b: {"canais": sorted((b.get("canais") or b).keys()) if isinstance(b, dict) else b})
passo("escopo (leitura Google)", c.get("/api/trafego/escopo"),
      lambda b: {"mcc": b.get("mcc"), "contas": [x.get("customer_id") for x in b.get("contas", [])][:5]})
passo("cockpit da oportunidade (Supabase + Google)", c.get(f"/api/trafego/candidatos/{OPP}", params={"run_id": RUN}),
      lambda b: {"conta": (b.get("conta") or {}), "bloqueado": b.get("bloqueado"),
                 "bloqueios": b.get("bloqueios"), "grupos": len(b.get("grupos") or [])})

for estrategia, extra in (("MANUAL_CPC", {"cpc_inicial": 0.5}), ("MAXIMIZE_CONVERSIONS", {})):
    pedido = {"opportunity_id": OPP_OK, "run_id": RUN_OK, "customer_id": CONTA, "login_customer_id": MCC,
              "canal": "SEARCH", "budget_diario": 10, "estrategia_lance": estrategia,
              "rede": {"google_search": True, "search_partners": False, "display_expansion": False},
              **extra}
    passo(f"/provar SEARCH {estrategia} (validate_only real, portões reais)", c.post("/api/trafego/provar", json=pedido),
          lambda b: {"aprovado": (b.get("preparo") or {}).get("aprovado"),
                     "falha_validacao": (b.get("preparo") or {}).get("falha_validacao"),
                     "destino": {k: (b.get("destino") or {}).get(k) for k in ("elegivel", "veredito", "motivos")},
                     "mensuracao": (b.get("prontidao") or {}).get("mensuracao"),
                     "chaves": sorted(b.keys())[:20],
                     "detail": b.get("detail")})

passo("gestão: propor +10% verba na Senac (deve recusar sem regra, sem gravar)",
      c.post("/api/trafego/gestao/propostas", json={
          "customer_id": CONTA, "motivo": "smoke do fluxo real, sem aplicar",
          "acao": {"tipo": "orcamento.diario", "campaign_id": CAMPANHA_ATIVA, "amount_micros": 33_000_000,
                   # W5: sem origem a recusa seria `valor_sem_origem`, não a da regra.
                   "origem": "operador"}}),
      lambda b: {"detail": b.get("detail"), "codigo": (b.get("detail") or {}).get("codigo") if isinstance(b.get("detail"), dict) else None})
passo("gestão: recomendações (leitura Google)", c.get("/api/trafego/gestao/recomendacoes", params={"customer_id": CONTA}),
      lambda b: {"n": len(b) if isinstance(b, list) else len(b.get("recomendacoes", [])) if isinstance(b, dict) else None})

resultado["duracao_s"] = round(time.time() - t0, 1)
destino = "/tmp/volc-gads-blindagem/testes/smoke-fluxo-real.json"
json.dump(resultado, open(destino, "w"), ensure_ascii=False, indent=1, default=str)
print("→", destino)
sys.exit(0)
