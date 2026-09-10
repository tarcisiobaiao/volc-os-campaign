#!/usr/bin/env python3
"""PRENSA POC — gates_pixel.py: pluga o gate de PIXEL REAL do dace
(godmode_render/pixel_gates.py, import cirúrgico, zero modificação no repo)
sobre um PNG renderizado + sua evidência de medição.
O gate reabre o PNG e CONFIRMA: bbox de tinta vs box medido, contraste WCAG
amostrado nos pixels finais (mediana do fundo atrás dos glifos — funciona
sobre foto/gradiente), clipping de borda.
Uso: .venv/bin/python gates_pixel.py out/<nome>.png out/<nome>.veredito.json out/<spec>.resolvido.json"""
from __future__ import annotations
import json, sys
from pathlib import Path

AQUI = Path(__file__).parent
DACE = AQUI.parent.parent / "dace"

# Import CIRÚRGICO do arquivo, sem passar pelo __init__ do pacote (que arrasta
# godmode_core inteiro + yaml/pydantic — a mesma classe de acoplamento que a
# DEVOLUTIVA aponta no godmode_v4). O pixel_gates.py em si só precisa de numpy+PIL
# e tem fallback interno para o contrast_ratio do core.
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "pixel_gates_standalone", DACE / "godmode_render" / "pixel_gates.py")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["pixel_gates_standalone"] = _mod  # dataclass exige o módulo em sys.modules
_spec.loader.exec_module(_mod)
audit_render = _mod.audit_render

def audita(png: Path, veredito: dict, spec: dict) -> dict:
    """API do portão. Mesmo julgamento do CLI, sem imprimir nem sair — para que
    a porta única (portoes.py) possa enfileirá-lo com os demais."""
    base = spec["artboard"]["base"]

    # adapter: evidência do verify DOM → slide dict cru que o pixel_gates aceita
    nodes, pesos = [], {}
    for nid, ev in veredito["evidencia"].items():
        if "bbox" not in ev:
            continue
        role = ev.get("role", nid)
        pesos[role] = {"weight": ev.get("peso", 400)}
        # a caixa planejada inclui o transbordo MEDIDO da atmosfera do próprio nó
        # (halação). Sem isso, o halo que o G-ATMOSFERA certifica como atmosfera
        # é contado aqui como letra vazando — dois portões, leituras opostas.
        o = ev.get("atm_outset") or {"l": 0, "t": 0, "r": 0, "b": 0}
        nodes.append({
            "id": nid, "kind": "text", "visible": True,
            "box": {"x": ev["bbox"]["x"] - o["l"], "y": ev["bbox"]["y"] - o["t"],
                    "width": ev["bbox"]["w"] + o["l"] + o["r"],
                    "height": ev["bbox"]["h"] + o["t"] + o["b"]},
            "metrics": {"text": {
                "font_size": ev["font_size_px"], "line_count": ev["linhas"],
                "line_height": ev.get("line_height", 1.2),
                "longest_line_width": ev["bbox"]["w"]}},
            "style": {"foreground": ev.get("cor"), "typography": role},
        })
    # nós não-texto declarados (réguas, dots, ghost): entram como media para o
    # masking de vizinhança — tinta deles não conta como overflow de um texto
    HALO = 3  # antialias pinta ~1px fora do bbox declarado; mask levemente generoso
    for ex in veredito.get("extras", []):
        nodes.append({
            "id": ex["id"], "kind": "media", "visible": True,
            "box": {"x": ex["bbox"]["x"] - HALO, "y": ex["bbox"]["y"] - HALO,
                    "width": ex["bbox"]["w"] + 2 * HALO, "height": ex["bbox"]["h"] + 2 * HALO},
        })
    gates_cfg = spec.get("gates", {})
    design = {
        "canvas": {"width": base["w"], "height": base["h"]},
        "quality": {"hard": {
            "min_contrast_normal": gates_cfg.get("contrast_min", 4.5),
            "min_contrast_large": gates_cfg.get("contrast_min_large", 3.0)}},
        "typography": pesos,
    }
    # LIMIAR DE TINTA vs GRÃO: o gate separa tinta de fundo por distância RGB.
    # Se a skin declara grão, os picos do ruído passam do limiar padrão (48) e
    # 14 pixels de película bastam para esticar o bbox e forjar um overflow de
    # 20px. Onde há grão, o limiar sobe acima do piso de ruído — tinta de texto
    # fica a 100+ de distância, então nada real é escondido.
    tem_grao = any(c.get("type") == "texture"
                   for sl in spec.get("slides", [{"layers": spec.get("layers", [])}])
                   for c in sl["layers"])
    limiar = 68.0 if tem_grao else 48.0
    resultado = audit_render(png, {"nodes": nodes}, design, ink_threshold=limiar)
    d = resultado.to_dict()
    png.with_suffix(".pixelgate.json").write_text(json.dumps(d, indent=2, ensure_ascii=False))
    status = d.get("status", "?")
    problemas = [f"{c.get('gate')}/{c.get('node_id')}: {c.get('detail')}"
                 for c in d.get("checks", []) if not c.get("passed", True)]
    return {"ok": status == "PIXEL_READY",   # o "PASS" do dace
            "status": status, "problemas": problemas, "detalhe": d}

def main() -> None:
    if len(sys.argv) < 4:
        print("uso: gates_pixel.py <png> <veredito.json> <spec.resolvido.json>"); sys.exit(1)
    png = AQUI / sys.argv[1]
    r = audita(png, json.loads((AQUI / sys.argv[2]).read_text()),
               json.loads((AQUI / sys.argv[3]).read_text()))
    print(f"{'✅' if r['ok'] else '❌'} PIXEL GATE [{r['status']}] {png.name}")
    for p in r["problemas"]: print(f"   ✗ {p}")
    if not r["ok"]: sys.exit(1)

if __name__ == "__main__":
    main()
