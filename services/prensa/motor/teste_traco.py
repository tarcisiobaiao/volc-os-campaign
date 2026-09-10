#!/usr/bin/env python3
"""REGRESSÃO DO PORTÃO DE TRAÇO — prova que ele ainda reprova o que deve.

Um portão que nunca reprova não é portão. Este teste falsifica uma peça que já
passou: repinta a tinta de ARGUMENTO a um passo do papel, sem tocar em geometria,
caixa ou copy. O DOM continua íntegro, o texto continua cabendo, o portão de
pixel continua satisfeito — só o olho perde a informação.

Verifica as duas direções, porque só uma delas não prova nada:
  · o lote real atravessa a fila inteira;
  · o lote falsificado é reprovado, E o é pelo portão de TRAÇO (não por acidente
    de outro portão, o que passaria a impressão errada de cobertura).

Uso: .venv/bin/python teste_traco.py
"""
from __future__ import annotations
import copy, json, subprocess, sys
from pathlib import Path

AQUI = Path(__file__).parent
PY = str(AQUI / ".venv" / "bin" / "python")
REAL = "spec_grafico.json"
FALSO = "spec_falso_traco.json"
QUASE_O_PAPEL = "#1B3050"     # a um passo de #142F55, o papel renderizado


def roda(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *args], cwd=AQUI, capture_output=True, text=True)


def resolvido(spec_nome: str) -> str:
    spec = json.loads((AQUI / spec_nome).read_text())
    skin = spec["skin"]["id"].lower().replace(":", "-")
    return f"out/{spec['spec_id']}.{skin}.resolvido.json"


def prepara_falso() -> None:
    s = json.loads((AQUI / REAL).read_text())
    f = copy.deepcopy(s)
    f["spec_id"] = "falso_traco"
    f["slides"] = [x for x in f["slides"] if x["id"] == "curva"]
    if not f["slides"]:
        sys.exit("spec real não tem a lâmina 'curva' — teste desatualizado")
    for c in f["slides"][0]["layers"]:
        if c.get("type") == "grafico":
            c["cor_marca"] = QUASE_O_PAPEL
        if c.get("id") == "dots":
            c["total"], c["atual"] = 1, 0
    (AQUI / FALSO).write_text(json.dumps(f, ensure_ascii=False, indent=2))


def ciclo(spec_nome: str) -> subprocess.CompletedProcess:
    for etapa in (("resolve.py", spec_nome), ("render.py", resolvido(spec_nome))):
        r = roda(*etapa)
        if r.returncode != 0:
            sys.exit(f"{etapa[0]} falhou em {spec_nome}:\n{r.stdout}{r.stderr}")
    return roda("portoes.py", resolvido(spec_nome))


def main() -> None:
    falhas = []

    r = ciclo(REAL)
    if r.returncode != 0:
        falhas.append(f"lote REAL deveria passar e foi reprovado:\n{r.stdout}")
    else:
        print("✓ lote real atravessa a fila inteira")

    prepara_falso()
    r = ciclo(FALSO)
    if r.returncode == 0:
        falhas.append("lote FALSIFICADO passou — o portão de traço parou de medir")
    elif "/traço:" not in r.stdout:
        falhas.append(f"falsificado reprovou, mas NÃO pelo traço "
                      f"(cobertura ilusória):\n{r.stdout}")
    else:
        linha = next(l for l in r.stdout.splitlines() if "/traço:" in l)
        print(f"✓ lote falsificado reprovado pelo traço\n   {linha.strip()}")

    if falhas:
        print("\n❌ REGRESSÃO:")
        for f in falhas:
            print(f"   · {f}")
        sys.exit(1)
    print("\n✅ portão de traço mede nas duas direções")


if __name__ == "__main__":
    main()
