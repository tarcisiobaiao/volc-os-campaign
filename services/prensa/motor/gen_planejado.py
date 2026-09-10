#!/usr/bin/env python3
"""PRENSA POC — gera a foto COM a composição pedida pelo plano da seed, e depois
CONFERE se o modelo obedeceu (Lei 21: o prompt pede, a medição confere).
Credencial pela porta única `ambiente.chave` (ver ../AUDITORIA-SEGREDOS.md).
Uso: python3 gen_planejado.py <seed> [qualidade]"""
from __future__ import annotations
import base64, json, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import composicao
from analisa_foto import analisa
from ambiente import chave  # porta única de credencial

AQUI = Path(__file__).parent
CANVAS = {"w": 1088, "h": 1360}
SAFE = {"top": 88, "bottom": 88, "left": 88, "right": 88}

BASE = (
    "Vertical 4:5 cinematic photograph of a broken classical marble statue — a stoic "
    "philosopher bust — in a vast dark void. Pale luminous marble with bold contours. "
    "KINTSUGI: thick molten-gold cracks (#FFD700) run through the marble like glowing "
    "rivers, some edged with neon purple (#BF00FF). The eyes are black voids with small "
    "neon green (#39FF14) stars inside. A few luminous butterflies float nearby — green, "
    "purple and gold. Subtle neon purple aura, fine light particles, scattered tiny green "
    "stars. Background: very deep black to dark purple (#0a0a0f to #1a0a2e), maximum "
    "contrast, atmospheric. Hyper-detailed, dramatic, mystical, cinematic. "
)
PROIBIDO = (
    " ABSOLUTELY NO text, no letters, no numbers, no captions, no watermark, no logo, "
    "no graphic overlay, no gradient bar, no dark rectangle, no borders, no frame. "
    "The reserved emptiness must read as real photographic depth and light — never as "
    "an added shape or panel."
)

def main() -> None:
    # Falha ANTES de gastar seed/plano: sem chave, nenhuma chamada e nada escrito.
    chave_openai = chave("OPENAI_API_KEY")
    seed = int(sys.argv[1]); qual = sys.argv[2] if len(sys.argv) > 2 else "low"
    nome, plano = composicao.escolhe(seed)
    out = AQUI / "out" / f"bg_plano_{nome}.png"
    prompt = BASE + plano["pedido"] + PROIBIDO
    corpo = json.dumps({"model": "gpt-image-2", "prompt": prompt,
                        "size": "1088x1360", "quality": qual, "n": 1}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/images/generations",
        data=corpo, headers={"Authorization": f"Bearer {chave_openai}",
                             "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.load(r)
    out.write_bytes(base64.b64decode(resp["data"][0]["b64_json"]))
    tok = (resp.get("usage") or {}).get("output_tokens", "?")

    a = analisa(out.name and f"out/{out.name}", CANVAS, SAFE)
    if not a.get("viavel"):
        print(f"seed {seed} · {nome:26} → RECUSADA ({a['motivo']})"); return
    v = composicao.confere(plano, a["zona"], CANVAS)
    m = a["medidas"]
    print(f"seed {seed} · {nome:26} · {tok:>5} tok · "
          f"obedeceu={'SIM' if v['obedeceu'] else 'NÃO'} (cob {v['cobertura']}) · "
          f"dinâmica {m['dinamica_de_quietude']:>6}x · {m['confianca']}")

if __name__ == "__main__":
    main()
