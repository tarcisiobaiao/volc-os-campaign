"""Cliente mínimo da API pública do n8n para a rodada do item 5. Credenciais só em memória (N8N_BASE_URL e
N8N_API_KEY do .env local do checkout oficial); nunca imprime URL base, chave ou corpo de resposta bruto."""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV_OFICIAL = Path("/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign/.env")
CANONICOS = {
    "google_d0": "Ps9yLfQkHeaAbyZZ",
    "google_d1": "7yxs1aOlzWkkkSf9",
    "google_termos": "TFlmThr4930oPneE",
    "joinads_intraday": "cpb6tNxt211UkAn2",
    "joinads_d1": "jDX397ViVcRQft4A",
}


def _cfg():
    env = {}
    for l in ENV_OFICIAL.read_text().splitlines():
        if "=" in l and not l.strip().startswith("#"):
            k, v = l.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    base = env["N8N_BASE_URL"].rstrip("/")
    if not base.endswith("/api/v1"):
        base += "/api/v1"
    return base, env["N8N_API_KEY"]


class ErroN8n(RuntimeError):
    pass


def chamar(metodo: str, caminho: str, corpo=None, consulta=None):
    base, chave = _cfg()
    url = base + caminho + ("?" + urllib.parse.urlencode(consulta) if consulta else "")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo,
                                 headers={"X-N8N-API-KEY": chave, "accept": "application/json", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read()
            return json.loads(b) if b else {}
    except urllib.error.HTTPError as e:
        msg = e.read()[:400].decode("utf-8", "replace")
        raise ErroN8n(f"HTTP {e.code} em {metodo} {caminho}: {msg}") from None


def sha_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
