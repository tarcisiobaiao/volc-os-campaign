"""Gate do profile `volcweb` antes de qualquer uso pela Bia. Rodar NA VPS.

Somente leitura: não chama o modelo, não cria sessão, não imprime a chave.
Sai com código != 0 no primeiro bloqueio.

Confere:
  1. o API Server escuta em 127.0.0.1:8643 e em NENHUM outro endereço;
  2. GET /health 200; /v1/capabilities 200 com auth bearer obrigatória;
  3. GET /v1/toolsets 200 e NENHUM toolset habilitado;
  4. GET /v1/models SEM chave → 401/403;
  5. o gateway do profile default (Telegram) continua ativo, com o mesmo PID
     de antes do teste quando PID_DEFAULT_ANTES for informado.

Uso:  PID_DEFAULT_ANTES=$(systemctl show -p MainPID --value hermes-gateway) \
      /usr/local/lib/hermes-agent/venv/bin/python smoke_hermes.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

ENV = Path("/root/.hermes/profiles/volcweb/.env")
BASE = "http://127.0.0.1:8643"


def bloquear(msg: str) -> None:
    print(f"BLOQUEADO: {msg}")
    sys.exit(3)


def main() -> None:
    dados = dict(l.split("=", 1) for l in ENV.read_text().splitlines()
                 if "=" in l and not l.lstrip().startswith("#"))
    chave = dados.get("API_SERVER_KEY", "").strip()
    if not chave:
        bloquear("API_SERVER_KEY ausente no volcweb")

    escuta = subprocess.run(["ss", "-ltnH"], capture_output=True, text=True).stdout
    enderecos = sorted({l.split()[3] for l in escuta.splitlines() if l.split()[3].endswith(":8643")})
    print("escuta_8643", json.dumps(enderecos))
    if enderecos != ["127.0.0.1:8643"]:
        bloquear("a porta 8643 precisa escutar só em 127.0.0.1")

    h = {"Authorization": f"Bearer {chave}"}
    with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as c:
        for caminho in ("/health", "/v1/capabilities", "/v1/toolsets"):
            r = c.get(BASE + caminho, headers=h)
            print(caminho, "HTTP", r.status_code)
            if r.status_code != 200:
                bloquear(f"{caminho} respondeu {r.status_code}")
            if caminho == "/v1/capabilities":
                corpo = r.json()
                print("modelo", corpo.get("model"))
                if not (corpo.get("auth") or {}).get("required"):
                    bloquear("o API Server não exige chave")
            if caminho == "/v1/toolsets":
                corpo = r.json()
                linhas = corpo.get("data", corpo) if isinstance(corpo, dict) else corpo
                habilitados = [x.get("name") for x in linhas if isinstance(x, dict) and x.get("enabled")]
                print("toolsets_habilitados", json.dumps(habilitados))
                if habilitados:
                    bloquear("há toolset habilitado no volcweb")
        sem_chave = c.get(BASE + "/v1/models")
        print("models_sem_chave HTTP", sem_chave.status_code)
        if sem_chave.status_code not in (401, 403):
            bloquear("rota protegida aceitou chamada sem chave")

    ativo = subprocess.run(["systemctl", "is-active", "hermes-gateway"], capture_output=True, text=True).stdout.strip()
    pid = subprocess.run(["systemctl", "show", "-p", "MainPID", "--value", "hermes-gateway"],
                         capture_output=True, text=True).stdout.strip()
    print("gateway_default", ativo, "pid", pid)
    if ativo != "active":
        bloquear("o gateway do profile default (Telegram) não está ativo")
    antes = os.environ.get("PID_DEFAULT_ANTES", "").strip()
    if antes and antes != pid:
        bloquear(f"o gateway default reiniciou durante o teste (pid {antes} → {pid})")
    print("OK: volcweb privado, autenticado e sem ferramentas; Telegram intacto.")


if __name__ == "__main__":
    main()
