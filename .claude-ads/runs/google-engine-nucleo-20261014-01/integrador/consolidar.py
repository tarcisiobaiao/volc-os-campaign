"""Consolida semente + resultados dos pesquisadores + decisões do integrador.

Uso (da raiz do checkout): python3 -I .claude-ads/runs/google-engine-nucleo-20261014-01/integrador/consolidar.py
Falha se algum item ficar sem decisão ou justificativa. Só lê JSON (nunca eval).
"""
import json
import sys
from collections import Counter
from pathlib import Path

RUN = Path(__file__).resolve().parents[1]
DECISOES = {"reutilizar_existente", "integrar_agora", "extrair_padrao", "experimentar_sandbox",
            "adiar_prerequisito", "rejeitar", "nao_verificavel"}

semente = {i["id"]: i for i in json.loads((RUN / "inventario-semente.json").read_text())["itens"]}
resultados = {}
for pasta in ("pesquisa-A-apis", "pesquisa-B-economia", "pesquisa-C-dados"):
    arq = RUN / pasta / "resultados.json"
    if not arq.exists():
        sys.exit(f"faltando {arq}")
    dados = json.loads(arq.read_text())
    itens = dados if isinstance(dados, list) else dados.get("itens") or dados.get("items") or []
    for r in itens:
        resultados[r["id"]] = {**r, "_pasta": pasta}
integrador = json.loads((RUN / "integrador" / "decisoes-integrador.json").read_text())

final = []
for id_ in sorted(set(semente) | set(resultados) | set(integrador), key=lambda x: (x[0], int(x[1:]))):
    base = dict(semente.get(id_, {}))
    r = resultados.get(id_, {})
    d = integrador.get(id_, {})
    item = {**base, **{k: v for k, v in r.items() if not k.startswith("_")}}
    if "origens" not in item:
        item["origens"] = r.get("origem") or r.get("origens") or ["descoberto na pesquisa"]
    item["pesquisa"] = r.get("_pasta")
    item["recomendacao_pesquisador"] = r.get("recomendacao_decisao")
    item["decisao"] = d.get("decisao") or r.get("recomendacao_decisao")
    item["justificativa_final"] = d.get("justificativa") or r.get("justificativa")
    if d:
        item["decisao_do_integrador"] = d
    if item["decisao"] not in DECISOES or not item["justificativa_final"]:
        sys.exit(f"{id_}: sem decisão válida/justificativa ({item['decisao']!r})")
    final.append(item)

(RUN / "INVENTARIO.json").write_text(json.dumps(
    {"schema": "volc-inventario-v1", "verificado_em": "2026-10-14", "itens": final},
    ensure_ascii=False, indent=1) + "\n")

linhas = ["# Inventário consolidado — google-engine-nucleo-20261014-01", "",
          f"{len(final)} itens; decisões: " + ", ".join(f"{k} {v}" for k, v in
                                                         sorted(Counter(i['decisao'] for i in final).items())),
          "", "| ID | Item | Origem | Veredito da alegação | Decisão | Justificativa |",
          "|---|---|---|---|---|---|"]
for i in final:
    origem = "; ".join(i["origens"]) if isinstance(i["origens"], list) else str(i["origens"])
    j = (i["justificativa_final"] or "").replace("|", "/").replace("\n", " ")
    linhas.append(f"| {i['id']} | {i.get('nome', '')} | {origem[:90]} | "
                  f"{i.get('veredito_alegacao', '—')} | {i['decisao']} | {j[:260]} |")
(RUN / "INVENTARIO.md").write_text("\n".join(linhas) + "\n")
print(len(final), Counter(i["decisao"] for i in final))
