#!/usr/bin/env python3
"""Valida o inventário de consumidores da anon key exigido pelo --passo1 do
pacote do incidente anon (W4). Uso: validar-inventario-anon-w4.py <arquivo.json>

A lista de consumidores e a lista de decisões ficam FIXAS AQUI, não no arquivo:
um inventário forjado com menos consumidores, ids trocados ou decisões
inventadas é recusado. Para acrescentar um consumidor, muda-se este arquivo
(revisado e com hash no pacote), não o JSON.

Saída: 0 = válido; 1 = recusado (motivos no stdout); 2 = uso/arquivo ilegível.
"""
import json
import sys

# Os 8 consumidores identificados pelo inventário do repositório (15/10/2026) e
# confirmados pela leitura de produção autorizada.
CONSUMIDORES_OBRIGATORIOS = (
    "gtm-n4ks27zv-tag-35",
    "gtm-n4ks27zv-tag-28",
    "gtm-n4ks27zv-tag-39-volc-ingest",
    "gtm-kjk7qqk9",
    "n8n-gads-campaign-search",
    "n8n-comportamento-gtm-scroll-funil",
    "n8n-credencial-volc-oficial",
    "logs-kong-anon-fora-do-app",
)
DECISOES_VALIDAS = frozenset({"nao_usa_anon", "aceita_quebra", "migrado_antes", "desativado"})
MIN_EVIDENCIA = 20  # caracteres: "ok" ou "sim" não é evidência


def motivos_de_recusa(d: dict) -> list[str]:
    erros: list[str] = []
    consumidores = d.get("consumidores")
    if not isinstance(consumidores, list):
        return ["campo consumidores ausente ou não é lista"]
    por_id: dict[str, dict] = {}
    for c in consumidores:
        if not isinstance(c, dict) or not isinstance(c.get("id"), str):
            erros.append("consumidor sem id")
            continue
        if c["id"] in por_id:
            erros.append(f"consumidor duplicado: {c['id']}")
        por_id[c["id"]] = c
    faltam = [i for i in CONSUMIDORES_OBRIGATORIOS if i not in por_id]
    if faltam:
        erros.append("faltam consumidores obrigatórios: " + ", ".join(faltam))
    extras = sorted(set(por_id) - set(CONSUMIDORES_OBRIGATORIOS))
    if extras:
        erros.append("consumidores fora da lista fixa (mude o validador, não o JSON): " + ", ".join(extras))
    for i in CONSUMIDORES_OBRIGATORIOS:
        c = por_id.get(i)
        if c is None:
            continue
        if not str(c.get("confirmado_em_producao") or "").strip():
            erros.append(f"{i}: sem confirmação em produção")
        if len(str(c.get("evidencia") or "").strip()) < MIN_EVIDENCIA:
            erros.append(f"{i}: evidência ausente ou curta demais")
        if c.get("decisao") not in DECISOES_VALIDAS:
            erros.append(f"{i}: decisão {c.get('decisao')!r} fora de {sorted(DECISOES_VALIDAS)}")
    if not str(d.get("assinado_por") or "").strip():
        erros.append("sem assinatura (assinado_por)")
    if not str(d.get("assinado_em") or "").strip():
        erros.append("sem data de assinatura (assinado_em)")
    if d.get("bloqueia_passo1") is not False:
        erros.append("bloqueia_passo1 não é false")
    return erros


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        d = json.load(open(argv[1], encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"inventario ilegível: {e}")
        return 2
    erros = motivos_de_recusa(d if isinstance(d, dict) else {})
    if erros:
        print("inventario RECUSADO: " + "; ".join(erros))
        return 1
    print(f"inventario ok: {len(CONSUMIDORES_OBRIGATORIOS)} consumidores obrigatórios, "
          f"assinado por {d['assinado_por']} em {d['assinado_em']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
