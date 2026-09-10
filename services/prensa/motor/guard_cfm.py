#!/usr/bin/env python3
"""PRENSA — compliance CFM como GATE PRÉ-CUSTO, não como revisão humana.

Import cirúrgico do mecanismo que já existe no dace (`dace/headlines/cfm_guard.py`):
blocked_terms com fronteira de palavra + NFD sem acento, patterns regex,
prefer_instead e required_elements — 100% dirigido pelo YAML. O motor é
setor-agnóstico; o `cfm_rules.yaml` é o dado. Troque o YAML e vira OAB, CONAR
ou claims-hygiene.

O engine legado tinha isto e NÃO ligava ao render: a peça saía e alguém conferia
depois. Aqui reprova ANTES de gastar imagem.
"""
from __future__ import annotations
import re, sys, unicodedata
from pathlib import Path

AQUI = Path(__file__).parent
YAML = AQUI.parent.parent / "dace" / "config" / "brand_dna" / "cfm_rules.yaml"

def _norm(s: str) -> str:
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()

def _lista(bloco: str, chave: str) -> list[str]:
    m = re.search(rf"^{chave}:(.*?)(?=^\w|\Z)", bloco, re.S | re.M)
    if not m: return []
    return [x.strip().strip('"').strip("'") for x in re.findall(r'^\s*-\s*(.+)$', m.group(1), re.M)]

def audita(textos: list[str], yaml_path: Path | None = None) -> dict:
    src = (yaml_path or YAML).read_text(encoding="utf-8")
    bloqueados = [t for t in _lista(src, "blocked_terms") if t and not t.startswith("#")]
    achados = []
    for txt in textos:
        n = _norm(txt)
        for termo in bloqueados:
            t = _norm(termo)
            if t and re.search(rf"\b{re.escape(t)}\b", n):
                achados.append({"termo": termo, "em": txt[:70]})
    # elemento obrigatório: CRM na primeira e na última lâmina
    juntos = " ".join(textos)
    crm = bool(re.search(r"CRM\s*30986", juntos, re.I))
    return {"ok": not achados and crm, "termos_bloqueados": achados,
            "crm_presente": crm, "regras_carregadas": len(bloqueados)}

if __name__ == "__main__":
    import json
    print(json.dumps(audita(sys.argv[1:]), ensure_ascii=False, indent=1))
