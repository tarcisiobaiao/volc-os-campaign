#!/usr/bin/env python3
"""PORTA ÚNICA — roda TODOS os portões sobre um spec já renderizado.

Por que existe: enquanto cada portão for um comando separado, publicar é uma
questão de lembrar. Um portão opcional não é portão — é sugestão. Aqui a peça só
é declarada publicável se atravessar a fila inteira, e a fila é fail-closed:
qualquer reprovação derruba o lote, porque carrossel se publica inteiro.

A fila, em ordem de custo crescente:
  1. VEREDITO   — o que o Chromium já mediu no DOM (fit, zona, colisão, respiro)
  2. PIXEL      — tinta que existe e não transborda a margem (gates_pixel)
  3. TRAÇO      — contraste ALCANÇADO da tinta não-textual (gate_traco)

Cada um enxerga o que o anterior não enxerga. O veredito aprova caixa que o
pixel reprova (a caixa declara y, a tinta pousa noutro y). O pixel aprova cor
que o traço reprova (a tinta existe, mas não contrasta com o papel). Nenhum
deles sozinho é a lei.

Uso: portoes.py <spec.resolvido.json>
"""
from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gates_pixel, gate_traco, gate_composicao

AQUI = Path(__file__).parent
SAIDA = AQUI / "out"


def pecas(spec: dict, spec_path: Path) -> list[tuple[str, Path, Path]]:
    """Casa cada lâmina com seu PNG e seu veredito, pelo mesmo esquema de nome
    que o render usa: peça única sem sufixo, carrossel com _sNN."""
    base = spec_path.name.split(".")[0]
    slides = spec.get("slides") or [{"id": spec.get("spec_id", base)}]
    fora = []
    for i, s in enumerate(slides, 1):
        cand = [SAIDA / f"{base}_s{i:02d}.png"] if len(slides) > 1 else []
        cand.append(SAIDA / f"{base}.png")
        png = next((p for p in cand if p.exists()), None)
        if png is None:
            fora.append((s["id"], cand[0], None)); continue
        fora.append((s["id"], png, png.parent / f"{png.stem}.veredito.json"))
    return fora


def main() -> None:
    spec_path = Path(sys.argv[1])
    spec = json.loads(spec_path.read_text())
    falhas: list[str] = []

    for sid, png, ver_path in pecas(spec, spec_path):
        if ver_path is None or not png.exists():
            falhas.append(f"{sid}: PNG ausente ({png.name}) — renderize antes")
            print(f"  ✗ {sid:12} PNG ausente"); continue
        if not ver_path.exists():
            falhas.append(f"{sid}: veredito ausente ({ver_path.name})")
            print(f"  ✗ {sid:12} veredito ausente"); continue
        ver = json.loads(ver_path.read_text())

        # 1. VEREDITO — o que o navegador já julgou, relido aqui para que a porta
        #    única não dependa de alguém ter olhado a saída do render.
        probs = list(ver.get("problemas") or [])
        if not ver.get("ok", True) or probs:
            falhas += [f"{sid}/dom: {p}" for p in probs] or [f"{sid}/dom: reprovado"]

        # 2. PIXEL
        try:
            r = gates_pixel.audita(png, ver, spec)
            if not r.get("ok", False):
                falhas += [f"{sid}/pixel: {p}" for p in (r.get("problemas") or ["reprovado"])]
        except Exception as e:                      # portão que quebra é portão que reprova
            falhas.append(f"{sid}/pixel: portão falhou — {e}")

        # 3. TRAÇO
        t = gate_traco.audita(png, ver, spec, sid)
        if not t["ok"]:
            falhas += [f"{sid}/traço: {p}" for p in t["problemas"]]

        # 4. COMPOSIÇÃO — mede na peça EMITIDA (com a composição aplicada), que é
        #    a única que existe de verdade. Sem isto, um gráfico pousado em cima
        #    da headline atravessa os três portões anteriores sem um arranhão:
        #    aconteceu, e é por isso que este portão está aqui.
        try:
            c = gate_composicao.audita_emitido(png, ver, spec, sid)
            if not c["ok"]:
                falhas += [f"{sid}/composição: {x}" for x in c["problemas"]]
        except Exception as e:
            falhas.append(f"{sid}/composição: portão falhou — {e}")

        marca = "✓" if not any(f.startswith(f"{sid}/") for f in falhas) else "✗"
        n_traco = sum(1 for m in t["medidas"] if m.get("razao") is not None)
        print(f"  {marca} {sid:12} dom+pixel+traço" + (f" · {n_traco} tintas medidas" if n_traco else ""))

    if falhas:
        print(f"\n❌ LOTE REPROVADO — {len(falhas)} reprovação(ões):")
        for f in falhas: print(f"   · {f}")
        sys.exit(1)
    print(f"\n✅ LOTE PUBLICÁVEL · {spec_path.name}")


if __name__ == "__main__":
    main()
