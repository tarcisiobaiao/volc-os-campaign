"""Prova VIVA: toda GAQL do motor passa no servidor (`validate_only`, sem executar).

O catálogo estático (`gads/catalogo.py`) pega campo não selecionável. Algumas
regras só o servidor aplica — ex.: em `campaign_asset`, filtrar por
`campaign.advertising_channel_type` exige o campo no SELECT (medido em
08/10/2026). Este script manda cada consulta com `validate_only=True`: o
servidor confere e não lê dado nenhum.

Uso (conta de prova Crédito Up, MCC 490-407-4301):
    backend/.venv/bin/python volc_ads/google_ads_api/provar_gaql_no_servidor.py
Sai 1 se alguma consulta for recusada.
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

CONTA = "5478096539"
MCC = "4904074301"


_INCOMPLETA = re.compile(r"(\bWHERE|\bAND|\bOR|=|\bIN|\(|'|,)\s*$", re.I)


def completa(texto: str) -> bool:
    """Só vai ao servidor a consulta que está INTEIRA no literal.

    Literal com `{…}` de `.format()`, f-string interpolada ou prefixo que acaba
    em WHERE/AND antes da concatenação é pedaço de consulta: o servidor o
    recusaria por estar incompleto, não por estar errado. Esses pedaços seguem
    cobertos pelo portão estático de campos (`gads/testes_catalogo_gaql.py`).
    """
    from volc_ads.gads import catalogo

    t = " ".join(texto.split())
    return ("{" not in t and "}" not in t and catalogo.INTERP not in t
            and not _INCOMPLETA.search(t))


def consultas() -> tuple[list[tuple[str, str]], int]:
    from volc_ads.gads import catalogo
    from volc_ads.observabilidade_pmax import queries as q

    literais = list(catalogo.varrer_gaqls(RAIZ))
    out = [(o, t) for o, t in literais if completa(t)]
    puladas = len(literais) - len(out)
    out += [(f"observabilidade_pmax:{n}", t)
            for n, t in q.build_pmax_observability_bundle_queries(CONTA, "1").items()]
    return out, puladas


def main() -> int:
    logging.disable(logging.CRITICAL)
    from google.ads.googleads.client import GoogleAdsClient

    c = GoogleAdsClient.load_from_storage(version="v25")
    c.login_customer_id = MCC
    ga = c.get_service("GoogleAdsService")
    recusadas = 0
    lista, puladas = consultas()
    for onde, gaql in lista:
        req = c.get_type("SearchGoogleAdsRequest")
        req.customer_id, req.query, req.validate_only = CONTA, gaql, True
        try:
            list(ga.search(request=req))
        except Exception as exc:  # noqa: BLE001
            recusadas += 1
            f = getattr(exc, "failure", None)
            print(f"RECUSA {onde}: {f.errors[0].message[:160] if f else str(exc)[:160]}")
    print(f"{len(lista) - recusadas}/{len(lista)} consultas aceitas pelo servidor "
          f"({puladas} literais incompletos pulados: só o portão estático os cobre)")
    return 1 if recusadas else 0


if __name__ == "__main__":
    raise SystemExit(main())
