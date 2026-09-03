#!/usr/bin/env python3
"""Inventário das rotas `/r/*` — os DESTINOS PAGOS, de três fontes independentes.

## Por que três fontes, e não a mais fácil

Cada uma sozinha mente de um jeito diferente:

  **sitemap**   diz o que o site publica HOJE. Não sabe o que já saiu do ar, e
                não sabe quais dessas rotas alguma campanha já apontou.
  **artefatos** dizem o que o motor GEROU. Não sabem se foi publicado, nem com
                que slug o WordPress ficou (o `-2` de duplicata muda o caminho).
  **conta**     diz para onde o anúncio APONTOU. É a única fonte que liga a rota
                ao dinheiro — e aqui ela entra já pseudonimizada, do JSON
                sanitizado; este script nunca fala com a API do Google.

A rota que aparece nas três é rota viva e paga. A que aparece só na conta é
destino que sumiu do site (o caso `portalmundomais.com`, HTTP 410 em
03/09/2026). A que aparece só no sitemap é página que ninguém anunciou.

## O que este script NÃO faz

Não rasteja. Ele lê `robots.txt` e os sitemaps declarados — nada mais — com
pausa entre requisições, e só quando recebe `--ao-vivo`. Não abre página, não
segue link, não envia formulário, não escreve em lugar nenhum. Sem `--ao-vivo`
ele roda inteiramente offline sobre o que já está no repositório.

Uso:
    python3 scripts/inventariar_landing_r.py                 # offline
    python3 scripts/inventariar_landing_r.py --ao-vivo       # + sitemaps
    python3 scripts/inventariar_landing_r.py --saida <arq>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

FECHAMENTO = RAIZ / "docs" / "closure" / "hermes-redator-google-ads-policy-incident-v1"
SAIDA_PADRAO = FECHAMENTO / "ROUTE-R-INVENTORY.json"
EVIDENCIA_DA_CONTA = FECHAMENTO / "account-evidence-sanitized.json"
REFERENCIA = RAIZ / "funnelforge-migracao" / "referencia"

#: Pausa entre requisições. Não é educação abstrata: é a diferença entre ler o
#: índice de um site e parecer um rastreador para quem já está sob revisão.
PAUSA_S = 2.0

_ROTA_R_RE = re.compile(r"https?://[^\s\"'<>]+/r/[^\s\"'<>]*")


def _rota(url: str) -> tuple[str, str]:
    partes = urlparse(url)
    return partes.netloc.lower(), partes.path.rstrip("/") or "/"


def da_conta() -> dict[str, dict]:
    """URLs finais que o JSON sanitizado da conta registrou. Sem ID cru."""
    achado: dict[str, dict] = {}
    if not EVIDENCIA_DA_CONTA.is_file():
        return achado
    dados = json.loads(EVIDENCIA_DA_CONTA.read_text(encoding="utf-8"))
    for cliente in dados.get("customers", []):
        for anuncio in cliente.get("matching_search_ads", []) or []:
            for url in anuncio.get("final_urls", []) or []:
                host, caminho = _rota(url.split("?")[0])
                chave = f"https://{host}{caminho}"
                item = achado.setdefault(
                    chave,
                    {"host": host, "path": caminho, "campanhas": 0,
                     "campaign_status": set(), "policy_approval": set()},
                )
                item["campanhas"] += 1
                item["campaign_status"].add(anuncio.get("campaign_status") or "UNKNOWN")
                item["policy_approval"].add(
                    (anuncio.get("policy_summary") or {}).get("approval_status") or "UNKNOWN"
                )
    for item in achado.values():
        item["campaign_status"] = sorted(item["campaign_status"])
        item["policy_approval"] = sorted(item["policy_approval"])
    return achado


def dos_artefatos() -> dict[str, list[str]]:
    """Rotas `/r/` citadas por artefato histórico versionado no repositório."""
    achado: dict[str, list[str]] = {}
    if not REFERENCIA.is_dir():
        return achado
    for arquivo in sorted(REFERENCIA.rglob("*")):
        if not arquivo.is_file() or arquivo.suffix.lower() not in {".json", ".md", ".html"}:
            continue
        try:
            texto = arquivo.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for bruto in _ROTA_R_RE.findall(texto):
            host, caminho = _rota(bruto.split("?")[0])
            chave = f"https://{host}{caminho}"
            rel = str(arquivo.relative_to(RAIZ))
            if rel not in achado.setdefault(chave, []):
                achado[chave].append(rel)
    return achado


def do_sitemap(hosts: list[str], *, pausa: float = PAUSA_S) -> dict[str, dict]:
    """Índice público do site, lido devagar. Só `robots.txt` e sitemaps."""
    from app.publisher_quality.fetch import fetch_public_https_chain

    achado: dict[str, dict] = {}
    for host in hosts:
        indice = f"https://{host}/sitemap_index.xml"
        try:
            robots = fetch_public_https_chain(f"https://{host}/robots.txt", timeout=20)
            declarado = re.search(r"(?im)^\s*Sitemap:\s*(\S+)", robots.get("html", "") or "")
            if declarado:
                indice = declarado.group(1).strip()
        except Exception as exc:  # noqa: BLE001 — host fora do ar é dado, não erro
            achado[f"https://{host}/robots.txt"] = {"erro": f"{type(exc).__name__}: {exc}"[:160]}
        time.sleep(pausa)

        try:
            resposta = fetch_public_https_chain(indice, timeout=25)
        except Exception as exc:  # noqa: BLE001
            achado[indice] = {"erro": f"{type(exc).__name__}: {exc}"[:160]}
            continue
        if int(resposta.get("status") or 0) >= 400:
            achado[indice] = {"status": resposta.get("status")}
            time.sleep(pausa)
            continue

        filhos = [
            u for u in re.findall(r"<loc>([^<]+)</loc>", resposta.get("html", ""))
            if "/r-sitemap" in u or "/rec-sitemap" in u
        ]
        for filho in filhos:
            time.sleep(pausa)
            try:
                pagina = fetch_public_https_chain(filho, timeout=25)
            except Exception as exc:  # noqa: BLE001
                achado[filho] = {"erro": f"{type(exc).__name__}: {exc}"[:160]}
                continue
            for loc, lastmod in re.findall(
                r"<url>\s*<loc>([^<]+)</loc>(?:\s*<lastmod>([^<]*)</lastmod>)?",
                pagina.get("html", ""),
            ):
                host_l, caminho = _rota(loc)
                achado[f"https://{host_l}{caminho}"] = {
                    "host": host_l,
                    "path": caminho,
                    "lastmod": lastmod or None,
                    "sitemap": filho,
                }
        time.sleep(pausa)
    return achado


def montar(ao_vivo: bool) -> dict:
    conta = da_conta()
    artefatos = dos_artefatos()
    hosts = sorted({urlparse(u).netloc for u in list(conta) + list(artefatos)})
    sitemap = do_sitemap(hosts) if ao_vivo else {}

    rotas: dict[str, dict] = {}
    for chave in sorted(set(conta) | set(artefatos) | set(sitemap)):
        host, caminho = _rota(chave)
        do_site = sitemap.get(chave) or {}
        entrada_conta = conta.get(chave)
        rotas[chave] = {
            "host": host,
            "path": caminho,
            "kind": "paid_destination_route" if caminho.startswith("/r/") else "funnel_interior",
            "sources": sorted(
                filter(
                    None,
                    [
                        "account_evidence" if entrada_conta else None,
                        "repository_artifact" if chave in artefatos else None,
                        "public_sitemap" if chave in sitemap and "erro" not in do_site else None,
                    ],
                )
            ),
            "ads_pointing": (entrada_conta or {}).get("campanhas", 0),
            "campaign_status": (entrada_conta or {}).get("campaign_status", []),
            "policy_approval": (entrada_conta or {}).get("policy_approval", []),
            "sitemap_lastmod": do_site.get("lastmod"),
            "artifact_refs": artefatos.get(chave, []),
        }

    somente_na_conta = [k for k, v in rotas.items()
                        if v["sources"] == ["account_evidence"] and v["path"].startswith("/r/")]
    return {
        "schema": "RouteRInventory.v1",
        "generated_by": "scripts/inventariar_landing_r.py",
        "live_read": ao_vivo,
        "rate_limit_seconds": PAUSA_S if ao_vivo else None,
        "crawl_performed": False,
        "forms_submitted": False,
        "sources": {
            "account_evidence": str(EVIDENCIA_DA_CONTA.relative_to(RAIZ)),
            "repository_artifacts": str(REFERENCIA.relative_to(RAIZ)),
            "public_sitemap": "robots.txt + declared sitemap index only" if ao_vivo else None,
        },
        "counts": {
            "routes": len(rotas),
            "paid_destination_routes": sum(1 for v in rotas.values() if v["path"].startswith("/r/")),
            "routes_with_ads": sum(1 for v in rotas.values() if v["ads_pointing"]),
            "routes_only_in_account": len(somente_na_conta),
        },
        "routes_only_in_account_evidence": sorted(somente_na_conta),
        "sitemap_errors": {k: v for k, v in sitemap.items() if "erro" in v or "status" in v},
        "routes": rotas,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ao-vivo", action="store_true",
                    help="lê robots.txt e os sitemaps declarados, com pausa entre requisições")
    ap.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = ap.parse_args()

    inventario = montar(args.ao_vivo)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(
        json.dumps(inventario, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"ok · {inventario['counts']['routes']} rotas "
          f"({inventario['counts']['paid_destination_routes']} destinos pagos) → {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
