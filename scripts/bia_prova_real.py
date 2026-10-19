#!/usr/bin/env python3
"""Roteiro de aceite REAL da Bia V1, ponta a ponta, contra o backend rodando.

⚠️ Faz inferência real (consome crédito do provedor do profile `default`, a
mesma Bia do Telegram, em sessão web separada). Só rodar depois dos checkpoints
(migration v27_01 aplicada, superfície API do default ligada, túnel aberto) — ver
docs/bia-hermes/RUNBOOK-IMPLANTACAO.md.

Entrada (ambiente, nunca argumento de linha de comando, para não ir ao histórico):
  BIA_BACKEND   base do FastAPI (padrão http://localhost:8010)
  BIA_TOKEN     access token da sessão Supabase de um ADMIN (DevTools → a
                requisição para /api/agent leva `Authorization: Bearer …`)
  BIA_ORIGEM    origem exata do front configurada em BIA_ALLOWED_ORIGINS
  BIA_CAMPANHA  (opcional) volc_campaign_id para a prova do contexto read-only

Saída: um recibo JSON em stdout com estados, durações e contagens. Nunca
imprime token, chave, texto de resposta além do necessário ao aceite, nem id
de sessão do Hermes (o backend nem os devolve).
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

import httpx

BASE = os.environ.get("BIA_BACKEND", "http://localhost:8010").rstrip("/")
TOKEN = os.environ.get("BIA_TOKEN", "")
ORIGEM = os.environ.get("BIA_ORIGEM", "")
CAMPANHA = os.environ.get("BIA_CAMPANHA", "")

recibo: dict = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "passos": []}


def passo(nome: str, ok: bool, **extra) -> None:
    recibo["passos"].append({"passo": nome, "ok": ok, **extra})
    print(("✓ " if ok else "✗ ") + nome, file=sys.stderr)


def h(**extra):
    base = {"Authorization": f"Bearer {TOKEN}"}
    if ORIGEM:
        base["Origin"] = ORIGEM
    return {**base, **extra}


def esperar(c: httpx.Client, eid: str, limite_s: int = 180) -> dict:
    fim = time.time() + limite_s
    while time.time() < fim:
        e = c.get(f"{BASE}/api/agent/runs/{eid}", headers=h()).json()["execucao"]
        if e["estado"] in ("succeeded", "failed", "cancelled", "uncertain"):
            return e
        time.sleep(1.5)
    return c.get(f"{BASE}/api/agent/runs/{eid}", headers=h()).json()["execucao"]


def enviar(c: httpx.Client, cid: str, texto: str, **extra) -> dict:
    t0 = time.time()
    r = c.post(f"{BASE}/api/agent/conversations/{cid}/messages", headers=h(),
               json={"request_id": str(uuid.uuid4()), "texto": texto, **extra})
    r.raise_for_status()
    e = esperar(c, r.json()["execucao"]["id"])
    e["_duracao_s"] = round(time.time() - t0, 2)
    return e


def main() -> int:
    if not TOKEN:
        print("defina BIA_TOKEN (access token de um ADMIN)", file=sys.stderr)
        return 2
    with httpx.Client(timeout=200, trust_env=False) as c:
        st = c.get(f"{BASE}/api/agent/estado", headers=h())
        passo("estado da Bia", st.status_code == 200 and st.json().get("motor_configurado") is True,
              http=st.status_code, capacidades=st.json().get("capacidades") if st.status_code == 200 else None)

        passo("sem token é 401", c.get(f"{BASE}/api/agent/conversations").status_code == 401)
        passo("token inválido é 401", c.get(f"{BASE}/api/agent/conversations",
                                           headers={"Authorization": "Bearer invalido"}).status_code == 401)

        cid = c.post(f"{BASE}/api/agent/conversations", headers=h(), json={}).json()["conversa"]["id"]
        e = enviar(c, cid, "Responda apenas: conexão VOLC funcionando.")
        passo("inferência real", e["estado"] == "succeeded"
              and "conexão volc funcionando" in (e["resposta"] or "").lower(),
              estado=e["estado"], duracao_s=e["_duracao_s"], erro=e["erro"])

        enviar(c, cid, "Guarde isto: o código desta conversa é AMBAR. Responda só: anotado.")
        e2 = enviar(c, cid, "Qual é o código desta conversa? Responda só o código.")
        passo("continuidade (AMBAR)", "AMBAR" in (e2["resposta"] or "").upper(),
              estado=e2["estado"], duracao_s=e2["_duracao_s"])

        hist = c.get(f"{BASE}/api/agent/conversations/{cid}/messages", headers=h()).json()
        passo("reload recupera o histórico", len(hist["execucoes"]) == 3)

        nova = c.post(f"{BASE}/api/agent/conversations", headers=h(), json={}).json()["conversa"]["id"]
        e3 = enviar(c, nova, "Qual é o código desta conversa? Se não souber, responda só: não sei.")
        passo("nova conversa isolada", "AMBAR" not in (e3["resposta"] or "").upper(),
              estado=e3["estado"], duracao_s=e3["_duracao_s"])

        passo("id inválido é 404", c.get(f"{BASE}/api/agent/conversations/{uuid.uuid4()}/messages",
                                         headers=h()).status_code == 404)
        extra = c.post(f"{BASE}/api/agent/conversations/{nova}/messages", headers=h(),
                       json={"request_id": str(uuid.uuid4()), "texto": "x", "model": "outro"})
        passo("campo extra (model) é 422", extra.status_code == 422)

        ferr = c.get(f"{BASE}/api/agent/tools", headers=h()).json()
        passo("catálogo só leitura", ferr["mutacoes"] == []
              and all(x["efeito"] == "leitura" for x in ferr["capacidades"]))

        if CAMPANHA:
            e4 = enviar(c, nova, "Resuma o contexto desta campanha em 3 linhas. Não estime nada.",
                        contexto={"campaign_ref": CAMPANHA, "janela": "ultimos_7_dias"})
            passo("contexto VOLC read-only", e4["estado"] == "succeeded",
                  estado=e4["estado"], duracao_s=e4["_duracao_s"])

    recibo["fim"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    recibo["aprovado"] = all(p["ok"] for p in recibo["passos"])
    print(json.dumps(recibo, ensure_ascii=False, indent=2))
    return 0 if recibo["aprovado"] else 1


if __name__ == "__main__":
    sys.exit(main())
