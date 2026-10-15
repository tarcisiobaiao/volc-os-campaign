"""Coletor Google Ads → banco. Somente leitura no Google; escreve só pela RPC.

Uso:
    backend/.venv/bin/python -m volc_ads.coleta --conta 5478096539 --mcc 4904074301 \\
        --origem D-1 --data 2026-10-07 [--familias campanha_dia,hora_dispositivo] [--seco]

--seco: lê o Google e monta os documentos, mas NÃO chama a RPC (mostra o que iria).
--agenda PASSO: execução recorrente (`disparo='agenda'`). O passo entra na chave e,
    antes de ler o Google, cada família cujo passo já tem tentativa concluída no
    ledger é PULADA — rodar duas vezes o mesmo passo não relê nem regrava.
--recibo ARQ: grava o recibo JSON da execução (famílias, chaves, lotes, saída).
--recoleta-dias N: relê os N dias fechados anteriores ao D-1 ([hoje-1-N, hoje-2]
    no fuso da conta) como `backfill`, para absorver os ajustes tardios do
    Google em custo e conversões. Padrão de famílias: só `campanha_dia`.
    Na agenda: `--recoleta-dias 7 --agenda rec` (ver deploy/gads-coleta/README.md).
Sem --data: D-1 = ontem no fuso da conta; D0 = hoje no fuso da conta.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import executor
from .contrato import RECOLETA_DIAS_MAXIMO, Contexto, janela_recoleta
from .familias import todas


def _conta(cid: str, mcc: str) -> tuple[str, str]:
    from ..gads.client import buscar

    q = "SELECT customer.time_zone, customer.currency_code FROM customer"
    for r in buscar(cid, q, login_customer_id=mcc):
        return r.customer.time_zone, r.customer.currency_code
    raise SystemExit(f"conta {cid} não respondeu ao SELECT de customer")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m volc_ads.coleta")
    ap.add_argument("--conta", required=True)
    ap.add_argument("--mcc", required=True)
    ap.add_argument("--origem", choices=("D0", "D-1", "backfill"), default=None,
                    help="padrão: D-1 (backfill com --recoleta-dias)")
    ap.add_argument("--data", help="YYYY-MM-DD (D0/D-1) ou início do backfill")
    ap.add_argument("--ate", help="fim do backfill (YYYY-MM-DD)")
    ap.add_argument("--familias", help="lista separada por vírgula; padrão: todas")
    ap.add_argument("--seco", action="store_true")
    ap.add_argument("--agenda", metavar="PASSO", help="passo da agenda (ex.: 06, 12, 18, 23)")
    ap.add_argument("--recibo", metavar="ARQ", help="grava o recibo JSON da execução")
    ap.add_argument("--recoleta-dias", type=int, metavar="N",
                    help="relê os N dias fechados antes do D-1 como backfill (1..90)")
    a = ap.parse_args(argv)
    if a.recoleta_dias is not None:
        if a.data or a.ate:
            ap.error("--recoleta-dias calcula a janela sozinho; não combine com --data/--ate")
        if a.origem is not None:
            ap.error("--recoleta-dias grava sempre como backfill; não combine com --origem")
        if not 1 <= a.recoleta_dias <= RECOLETA_DIAS_MAXIMO:
            ap.error(f"--recoleta-dias aceita 1..{RECOLETA_DIAS_MAXIMO}")
        a.origem = "backfill"
    elif a.origem is None:
        a.origem = "D-1"
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("google.ads.googleads.client").setLevel(logging.ERROR)

    from ..gads.client import buscar

    fuso, moeda = _conta(a.conta, a.mcc)
    hoje = datetime.now(ZoneInfo(fuso)).date()
    if a.recoleta_dias is not None:
        ini, fim = janela_recoleta(hoje, a.recoleta_dias)
    else:
        if a.data:
            ini = date.fromisoformat(a.data)
        else:
            ini = hoje if a.origem == "D0" else hoje - timedelta(days=1)
        fim = date.fromisoformat(a.ate) if (a.origem == "backfill" and a.ate) else ini
    rpc_cliente = None
    mapa: dict[str, str] = {}
    if not a.seco:
        from .persistencia import RPC
        rpc_cliente = RPC()
        mapa = rpc_cliente.mapa_volc(a.conta)
    ctx = Contexto(customer_id=a.conta, login_customer_id=a.mcc, origem_janela=a.origem,
                   data_inicio=ini, data_fim=fim, fuso=fuso, moeda=moeda,
                   colhida_em=datetime.now(timezone.utc), mapa_volc=mapa,
                   disparo="agenda" if a.agenda else "manual", passo=a.agenda,
                   # A recoleta NÃO reescreve `daily_campaign_metrics`: lá o
                   # UPDATE de spend dispara a comissão do operador, e reabrir
                   # dias fechados (até 90) mexeria em comissão já apurada. O
                   # custo maduro mora só no fato canônico.
                   projetar_compat=a.recoleta_dias is None)

    familias = todas()
    # A recoleta existe para o custo maduro: por padrão só o fato campanha-dia.
    # Reler as 10 famílias por N dias multiplica leitura sem pedido.
    padrao = ["campanha_dia"] if a.recoleta_dias is not None else sorted(familias)
    escolhidas = a.familias.split(",") if a.familias else padrao
    faltando = [f for f in escolhidas if f not in familias]
    if faltando:
        raise SystemExit(f"famílias desconhecidas: {faltando}; existem: {sorted(familias)}")

    if a.seco:
        documentos: list[tuple[str, dict]] = []
        registrar = lambda rpc, doc: (documentos.append((rpc, doc)) or  # noqa: E731
                                      {"seco": True, "linhas": len(doc.get("linhas", []))})
    else:
        registrar = rpc_cliente

    def _buscar(cid: str, gaql: str):
        return buscar(cid, gaql, login_customer_id=a.mcc)

    print(f"conta {a.conta} · fuso {fuso} · moeda {moeda} · {a.origem} {ini}..{fim} · "
          f"{'SECO (sem RPC)' if a.seco else 'gravando via RPC'} · vínculos {len(mapa)}")
    falhou = False
    recibo: dict = {"conta": a.conta, "origem": a.origem, "janela": [ini.isoformat(), fim.isoformat()],
                    "disparo": ctx.disparo, "passo": ctx.passo, "colhida_em": ctx.colhida_iso,
                    "seco": a.seco, "recoleta_dias": a.recoleta_dias, "moeda": moeda,
                    "fuso": fuso, "familias": {}}
    for nome in escolhidas:
        prefixo = executor.prefixo_do_passo(nome, ctx)
        try:
            if a.agenda and not a.seco and executor.passo_concluido(
                    rpc_cliente.execucoes_do_passo(prefixo),
                    exige_fechamento=hasattr(familias[nome], "fechamento")):
                print(f"  {nome}: passo {a.agenda} já concluído no ledger · pulada")
                recibo["familias"][nome] = {"prefixo": prefixo, "pulada": "passo_concluido"}
                continue
            r = executor.coletar(familias[nome], ctx, buscar=_buscar, registrar=registrar)
            print("  " + r.resumo())
            recibo["familias"][nome] = {"prefixo": prefixo, "resumo": r.resumo(), "lotes": r.lotes,
                                        "fechamento": r.fechamento, "truncado": r.truncado}
            if r.truncado:
                falhou = True
            for lote in r.lotes:
                if lote.get("rejeicoes"):
                    print("     rejeições:", json.dumps(lote["rejeicoes"][:3], ensure_ascii=False))
                if lote.get("resultado") == "falhou":
                    falhou = True
        except Exception as exc:  # noqa: BLE001 — uma família não derruba as outras
            falhou = True
            print(f"  {nome}: ERRO {type(exc).__name__}: {str(exc)[:300]}")
            recibo["familias"][nome] = {"prefixo": prefixo, "erro": f"{type(exc).__name__}: {str(exc)[:300]}"}
    recibo["saida"] = 1 if falhou else 0
    if a.recibo:
        with open(a.recibo, "w", encoding="utf-8") as fh:
            json.dump(recibo, fh, ensure_ascii=False, indent=1, default=str)
    return recibo["saida"]


if __name__ == "__main__":
    sys.exit(main())
