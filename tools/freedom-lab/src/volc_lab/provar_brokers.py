"""Prova ao vivo, somente leitura, dos brokers Google. Grava recibos sanitizados em JSONL.

    PYTHONPATH=tools/freedom-lab/src:. backend/.venv/bin/python -m volc_lab.provar_brokers <destino_dir> [gtm|ga4|ads ...]

Não imprime nem grava token, ID não mascarado ou conteúdo de tag/propriedade.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from volc_lab.brokers import recibos


def _gtm(destino: Path) -> None:
    from volc_lab.brokers import gtm

    t0 = time.perf_counter()
    cli = gtm.ClienteGTMLeitura(gtm.ConcessaoGTM(frozenset({gtm.CapacidadeGTM.LEITURA}),
                                                 "inventário read-only Freedom Lab"))
    inv = cli.inventariar(todos_workspaces=True)
    rec = inv.recibo() | {"duracao_s": round(time.perf_counter() - t0, 1)}
    recibos.gravar(rec, destino / "gtm.jsonl")
    print("gtm", {k: rec[k] for k in ("accounts", "containers", "workspaces", "tags", "triggers",
                                      "variables", "erros_http", "escopos_efetivos")})


def _ga4(destino: Path) -> None:
    from volc_lab.brokers import ga4

    cli = ga4.ClienteGA4Leitura()
    inv = cli.inventariar()
    recibos.gravar(inv.recibo(), destino / "ga4.jsonl")
    props = cli.properties()
    meta = cli.metadata(props[0]) if props else None
    com_linha = sem_linha = 0
    for p in props:
        if cli.agregado(p)["tem_linha"]:
            com_linha += 1
        else:
            sem_linha += 1
    rec = {"broker": "ga4", "operacao": "leitura:metadata+runReport_agregado_sem_dimensao",
           "metadata_primeira_property": meta, "properties_com_sessoes_7d": com_linha,
           "properties_sem_linha_7d": sem_linha, "em": recibos.agora_utc()}
    recibos.gravar(rec, destino / "ga4.jsonl")
    print("ga4", inv.recibo() | rec)


def _ads(destino: Path) -> None:
    import os

    from volc_lab.brokers import google_ads

    login = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "")
    cliente = os.environ.get("LAB_ADS_CUSTOMER", "")
    if not (login and cliente):
        print("ads: defina GOOGLE_ADS_LOGIN_CUSTOMER_ID e LAB_ADS_CUSTOMER (não impressos)")
        return
    gaql = ("SELECT campaign.id, segments.date, metrics.cost_micros, metrics.clicks "
            "FROM campaign WHERE segments.date DURING LAST_7_DAYS")
    linhas = google_ads.ler(cliente, gaql, login_customer_id=login, destino_recibo=destino / "ads.jsonl")
    print("ads", {"linhas": len(linhas)})


def main(argv: list[str]) -> int:
    destino = Path(argv[0])
    alvos = argv[1:] or ["gtm", "ga4"]
    for a in alvos:
        {"gtm": _gtm, "ga4": _ga4, "ads": _ads}[a](destino)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
