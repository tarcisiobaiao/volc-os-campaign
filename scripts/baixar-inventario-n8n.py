#!/usr/bin/env python3
"""Baixa os workflows do núcleo da arbitragem e sanitiza os segredos.

## Por que sanitizar por NOME DE CAMPO e não por formato

Já falhou duas vezes nesta casa tentar reconhecer segredo pelo formato do valor:
o developer token do Google Ads é uma string de 22 caracteres sem prefixo, e um
`client_id` de ClickUp parece um id qualquer. O que identifica uma credencial não
é o que ela parece — é ONDE ela mora. Então a regra é a inversa: qualquer campo
cujo NOME cheire a credencial vira «CENSURADO», independente do conteúdo.

O formato continua como rede de segurança, para o que vem embutido em código.

## O que este script produz

    inventario-n8n/flows/<slug>.json      workflow sanitizado, pronto para leitura
    inventario-n8n/flows/<slug>.meta.json id, nome, ativo, contagens, gatilhos

Uso:
    backend/.venv/bin/python scripts/baixar-inventario-n8n.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "inventario-n8n" / "flows"

CHAVE_SENSIVEL = re.compile(
    r"(?i)(token|secret|password|senha|passwd|api[_\-]?key|apikey|"
    r"authorization|bearer|credential|service[_\-]?role|anon[_\-]?key|"
    r"private[_\-]?key|refresh)"
)

FORMATO_SENSIVEL = re.compile(
    r"(eyJ[\w\-]{10,}\.[\w\-]{10,}\.[\w\-]{6,}"          # JWT
    r"|pk_[0-9A-Z]{6,}_[0-9A-Z]{20,}"                     # ClickUp
    r"|sk-[A-Za-z0-9_\-]{20,}"                            # OpenAI/Anthropic
    r"|AIza[0-9A-Za-z_\-]{30,}"                           # Google API key
    r"|(?<![\w])([A-Za-z0-9]{4} ){3}[A-Za-z0-9]{4}(?![\w]))"  # WP app password
)

# O núcleo da arbitragem. `True` = confirmado ativo na instância em 19/08/2026.
NUCLEO: dict[str, tuple[str, str]] = {
    # ── os seis que o operador apontou ──────────────────────────────────────
    "Q6IunKtTI0gY0KgX": ("orakul-vos-auto-adjust", "decisao"),
    "pjItRZhP2yrNyrDs": ("gads-new-campaign-validation", "decisao"),
    "IygWdazRpEW0GKFM": ("gads-campaign-search", "criacao"),
    "svJWqv5r1NSxB8MO": ("gads-search-terms-upgrade-kw", "otimizacao"),
    "lua75uELXh3xiB2g": ("gads-buscar-id-conversoes", "apoio"),
    "i21UFesZCR3nkMfN": ("bola-de-cristal-preditivo", "preditivo"),
    # ── receita (sell side), todos ATIVOS ───────────────────────────────────
    "m4raVVEXGqRA956U": ("receita-gam-adsense-projects", "receita"),
    "AJnsRGPFwMdc6Rho": ("receita-gam-adsense-projects-d1", "receita"),
    "Mklpt0em3vb7LHLB": ("receita-gam-campaign-id", "receita"),
    "azK8XrXY2noYtHP0": ("receita-gam-campaign-id-d1", "receita"),
    "HeKrxGT6qQGJEVIk": ("receita-gam-ecpm-hourly", "receita"),
    "AeeKyqMYwgg0GM0a": ("receita-gam-placements-display", "receita"),
    "BGsqwhbWCXQ6luGN": ("receita-gam-placements-display-d1", "receita"),
    "RpxB9ppefxZWujEV": ("receita-joinads-d1", "receita"),
    "U0jEfGt30HqbUq1o": ("receita-joinads-intraday", "receita"),
    "SRJyJW2vaDowlLar": ("receita-force-update-gam", "receita"),
    # ── custo (buy side), todos ATIVOS ──────────────────────────────────────
    "33cQyqJLsL7LJzUI": ("custo-gads-report", "custo"),
    "fwMKXA2EFxQ3jQQo": ("custo-gads-report-d1", "custo"),
    "cI56Z2jSu0S8Z4pk": ("custo-gads-placements-display", "custo"),
    "OmewKD5Nj8H5eusV": ("custo-gads-placements-display-d1", "custo"),
    "rb3Ict4vFU8zg5GH": ("custo-force-update-gads", "custo"),
    # ── atuação e front, ATIVOS ─────────────────────────────────────────────
    "T2Lr1MD33w4aZFJY": ("atuacao-apply-bidding-webhook-v2", "atuacao"),
    "dbpKlrxR6B2pqiAs": ("atuacao-orakul-ai-agent-webgo", "atuacao"),
    "AFJBJTC5NNozhbjO": ("front-vincular-campanha-operador", "front"),
    "y9Z9Iw4OlKHV2YCv": ("front-webgo-new-dashboards", "front"),
    # ── criação e conteúdo, ATIVOS ──────────────────────────────────────────
    "KL28wCookpwjQ7AO": ("criacao-gads-factory-v3", "criacao"),
    "MAhL2OEWFu7Psb45": ("pauta-kw-minning-pautador-pro", "pauta"),
    "NlDpiKPIqHCDblto": ("pauta-recomendador-semantico-p3", "pauta"),
    # ── comportamento e otimização editorial (legado proprietário) ────────────
    "GHMVIgFAv6oytKuj": ("comportamento-gtm-scroll-funil", "comportamento"),
    "awNXK3BdPTplsmKy": ("otimizacao-cta-congruencia-page", "otimizacao"),
    "RYmky2S9FCy2dVuz": ("rsa-darwin-optimizer-ctr", "otimizacao"),
    # ── linhagem do ORAKUL (inativos, mas são a genealogia) ─────────────────
    "3vujeIn8UkaXYzqZ": ("orakul-02-analysis-engine", "linhagem"),
    "pLVASdJ8TaUSNFp0": ("orakul-predictive-integrado-v1", "linhagem"),
}


def limpar(o):
    """Cópia do objeto com todo campo sensível trocado por «CENSURADO»."""
    if isinstance(o, dict):
        saida = {}
        for k, v in o.items():
            if CHAVE_SENSIVEL.search(str(k)) and isinstance(v, (str, int, float)):
                saida[k] = "«CENSURADO»"
            # o n8n guarda header como {"name": "developer-token", "value": "..."}
            elif k == "value" and CHAVE_SENSIVEL.search(str(o.get("name", ""))):
                saida[k] = "«CENSURADO»"
            else:
                saida[k] = limpar(v)
        return saida
    if isinstance(o, list):
        return [limpar(v) for v in o]
    if isinstance(o, str):
        return FORMATO_SENSIVEL.sub("«CENSURADO»", o)
    return o


def env(chave: str) -> str:
    for linha in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if linha.startswith(f"{chave}="):
            return linha.partition("=")[2].strip()
    raise SystemExit(f"{chave} ausente no .env")


def api(caminho: str) -> dict:
    req = urllib.request.Request(env("N8N_BASE_URL").rstrip("/") + caminho)
    req.add_header("X-N8N-API-KEY", env("N8N_API_KEY"))
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def gatilhos(nos: list[dict]) -> list[str]:
    saida = []
    for n in nos:
        t = n["type"].split(".")[-1]
        if t in ("scheduleTrigger", "cron"):
            r = n.get("parameters", {}).get("rule", {})
            cron = (r.get("interval") or [{}])[0]
            saida.append(f"schedule:{cron.get('expression') or json.dumps(cron, ensure_ascii=False)}")
        elif t in ("webhook", "formTrigger"):
            saida.append(f"{t}:{n.get('parameters', {}).get('path', '?')}")
        elif t.endswith("Trigger") or t == "executeWorkflowTrigger":
            saida.append(t)
    return saida


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    indice = []
    for wid, (slug, camada) in NUCLEO.items():
        try:
            d = api(f"/api/v1/workflows/{wid}")
        except urllib.error.HTTPError as e:
            print(f"  ❌ {slug}: HTTP {e.code}")
            continue
        nos = d.get("nodes", [])
        limpo = limpar(d)
        (DESTINO / f"{slug}.json").write_text(
            json.dumps(limpo, ensure_ascii=False, indent=1), encoding="utf-8")

        codigo = {}
        for n in nos:
            p = n.get("parameters", {})
            c = p.get("jsCode") or p.get("pythonCode")
            if c:
                codigo[n["name"]] = ("python" if p.get("pythonCode") else "js",
                                     len(c.splitlines()))
        meta = {
            "id": wid, "nome": d.get("name"), "slug": slug, "camada": camada,
            "ativo": d.get("active"), "nos": len(nos),
            "atualizado_em": d.get("updatedAt"),
            "gatilhos": gatilhos(nos),
            "tipos_de_no": sorted({n["type"].split(".")[-1] for n in nos}),
            "nos_com_codigo": {k: {"linguagem": v[0], "linhas": v[1]}
                               for k, v in sorted(codigo.items(), key=lambda x: -x[1][1])},
            "linhas_de_codigo": sum(v[1] for v in codigo.values()),
        }
        (DESTINO / f"{slug}.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        indice.append(meta)
        marca = "▶" if d.get("active") else "·"
        print(f"  {marca} {slug:<38} {len(nos):>3} nós · {meta['linhas_de_codigo']:>5} linhas")

    (DESTINO.parent / "indice.json").write_text(
        json.dumps(sorted(indice, key=lambda m: (m["camada"], m["slug"])),
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(indice)} workflows em {DESTINO}")


if __name__ == "__main__":
    main()
