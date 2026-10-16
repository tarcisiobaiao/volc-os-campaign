"""Aplica o delta proposto de curadoria e roadmap (CURADORIA-DELTA-20261016.json).

NÃO roda sozinho em CI. Uso pelo integrador autorizado, a partir da raiz do repositório:

    python3 docs/data-intelligence/fundacao-20261016/handoffs/aplicar_curadoria_delta.py
    python3 scripts/atualizar_grafo_volc_os.py
    python3 scripts/atualizar_grafo_volc_os.py --check

Regras (do próprio delta, `como_aplicar`): proof/gaps/latest_evidence são acréscimos datados,
links sem duplicar, status é set, toda tarefa tocada recebe updated_at, tarefas novas vão ao fim
da iniciativa, graph_nodes de iniciativa só depois de os nós existirem na curadoria.
"""
import copy
import hashlib
import json
import sys

DELTA = "docs/data-intelligence/fundacao-20261016/handoffs/CURADORIA-DELTA-20261016.json"
RP = "volc-os-workbook/ROADMAP-VIVO.json"
CP = "docs/volc-os-graph/curadoria-operacional.json"
HOJE = "2026-10-16"


def conferir_base(op: dict, antigo) -> None:
    """Recusa aplicar sobre um campo que mudou desde que o delta foi gerado (R2-G16)."""
    esperado = op.get("base_sha256_campo_anterior")
    if esperado is None:
        return
    texto = "" if antigo is None else (antigo if isinstance(antigo, str) else json.dumps(antigo, ensure_ascii=False))
    obtido = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    if obtido != esperado:
        sys.exit(f"campo mudou desde a geração do delta: {op.get('task_id') or op.get('id')}.{op.get('campo')} "
                 f"(esperado {esperado[:12]}…, obtido {obtido[:12]}…); regere o delta")


def acrescentar(antigo, valor):
    if antigo is None or str(antigo).strip() == "":
        return valor[2:] if valor.startswith("· ") else valor
    return str(antigo).rstrip() + " " + valor


def main() -> None:
    d = json.load(open(DELTA))

    cur = json.load(open(CP))
    c = d["curadoria_updates"]
    if c["meta"]["campo"] != "meta.curadoria_atualizada_em":
        sys.exit("meta inesperada")
    cur["meta"]["curadoria_atualizada_em"] = c["meta"]["valor"]
    if c["mudancas_de_estado"]:
        sys.exit("o delta não deveria mudar estados da curadoria")
    # a guarda compara com o campo ANTES de qualquer operação deste delta (várias operações no mesmo campo)
    original_c = {(s, x["id"]): copy.deepcopy(x) for s in ("capabilities", "concepts", "documents") for x in cur[s]}
    for e in c["evidence_appends"]:
        itens = [x for x in cur[e["secao"]] if x["id"] == e["id"]]
        if len(itens) != 1:
            sys.exit(f"nó ausente ou duplicado: {e['id']}")
        conferir_base(e, original_c[(e["secao"], e["id"])].get(e["campo"]))
        itens[0][e["campo"]] = acrescentar(itens[0].get(e["campo"]), e["valor"])
    ids = {x["id"] for s in ("capabilities", "concepts", "documents") for x in cur[s]}
    for secao in ("concepts", "documents"):
        for n in c["novos_nos"][secao]:
            if n["id"] in ids:
                sys.exit(f"id já existe: {n['id']}")
            cur[secao].append(n)
            ids.add(n["id"])
    cur["edges"].extend(c["novas_arestas"])

    r = json.load(open(RP))
    tarefas = {t["id"]: t for i in r["initiatives"] for t in i["tasks"]}
    iniciativas = {i["id"]: i for i in r["initiatives"]}
    tocadas = set()
    original_r = copy.deepcopy(tarefas)
    for u in d["roadmap_updates"]:
        t, campo, valor = tarefas[u["task_id"]], u["campo"], u["valor"]
        tocadas.add(t["id"])
        conferir_base(u, original_r[t["id"]].get(campo))
        if campo in ("proof", "gaps", "latest_evidence"):
            if isinstance(t.get(campo), list):
                t[campo].extend(valor if isinstance(valor, list) else [valor])
            else:
                t[campo] = acrescentar(t.get(campo), valor)
        elif campo == "links":
            t.setdefault("links", [])
            for x in valor if isinstance(valor, list) else [valor]:
                if x not in t["links"]:
                    t["links"].append(x)
        elif campo == "status":
            t["status"] = valor
        else:
            sys.exit(f"campo desconhecido: {campo}")
    for n in d["roadmap_new_tasks"]:
        t = n["task"]
        if t["id"] in tarefas:
            sys.exit(f"tarefa já existe: {t['id']}")
        iniciativas[n["initiative"]]["tasks"].append(t)
        tarefas[t["id"]] = t
        tocadas.add(t["id"])
    for u in d["roadmap_initiative_updates"]:
        lista = iniciativas[u["initiative"]].setdefault(u["campo"], [])
        for x in u["acrescentar"]:
            if x not in ids:
                sys.exit(f"nó inexistente na curadoria: {x}")
            if x not in lista:
                lista.append(x)
    for i in tocadas:
        tarefas[i]["updated_at"] = HOJE
    r["updated_at"] = HOJE

    with open(CP, "w") as f:
        f.write(json.dumps(cur, indent=2, ensure_ascii=False) + "\n")
    with open(RP, "w") as f:
        f.write(json.dumps(r, indent=2, ensure_ascii=False) + "\n")
    print(f"ok: {len(tarefas)} tarefas, {len(tocadas)} tocadas, "
          f"{len(cur['concepts'])} conceitos, {len(cur['edges'])} arestas")


if __name__ == "__main__":
    main()
