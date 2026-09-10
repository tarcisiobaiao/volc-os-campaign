#!/usr/bin/env python3
"""PRENSA POC — gera o fundo via gpt-image-2 (SEM texto, SEM gradiente: scrim é do engine).
Credencial pela porta única `ambiente.chave` — nunca por caminho fixo de outro
motor (ver ../AUDITORIA-SEGREDOS.md). Uso: python3 gen_bg.py"""
from __future__ import annotations
import base64, hashlib, json, sys, urllib.request
from pathlib import Path

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI))
from ambiente import chave  # noqa: E402  (porta única de credencial)

OUT = AQUI / "out" / "bg_news.png"  # 1088x1360 = 4:5 instagram-ready (lados multiplos de 16)

# Doutrina PRENSA lei 1: o modelo de imagem NUNCA escreve tipografia nem o fade —
# o pixel exato (scrim + texto) nasce no render determinístico.
PROMPT = (
    "Documentary-editorial photograph, Brazilian photojournalism style (Folha/UOL quality), "
    "vertical 4:5 composition, shot for a magazine cover where the lower area carries the headline. "
    "A Brazilian woman in her 60s (parda, gray-streaked hair tied back, reading glasses, "
    "simple plain blouse) sits at a kitchen table reviewing paper bills and a payment booklet, "
    "holding a pen, thoughtful but dignified expression. Setting: simple Brazilian kitchen — "
    "4-burner stove, steel-front cabinets, fridge with magnets, window light from the upper left. "
    "LIGHTING IS THE COMPOSITION: a single soft window light falls on her face and hands in the "
    "UPPER 55 percent of the frame, and rolls off steeply downward — the LOWER 40 percent of the "
    "frame sits in deep, clean shadow, heavily underexposed, almost black, a plain unlit dark "
    "surface with NO pattern, NO tablecloth print, NO objects, NO highlights, nothing to read. "
    "Chiaroscuro falloff, moody but natural, warm color grading, f/2.8, real skin texture, "
    "lived-in face with dignity, authentic, not stock-looking. "
    "ABSOLUTELY NO text, no letters, no numbers, no watermark, no logo, no graphic overlay, "
    "no artificial gradient bar, no borders, no vignette frame."
)

def main() -> None:
    # Falha ANTES de montar o corpo: se a chave falta, nada de rede, nada escrito.
    chave_openai = chave("OPENAI_API_KEY")
    corpo = json.dumps({
        "model": "gpt-image-2",
        "prompt": PROMPT,
        "size": "1088x1360",
        "quality": "medium",
        "n": 1,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=corpo,
        headers={"Authorization": f"Bearer {chave_openai}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP {e.code}: {e.read().decode()[:500]}"); sys.exit(1)
    b64 = resp["data"][0]["b64_json"]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(base64.b64decode(b64))
    sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(f"✅ {OUT.name} · {OUT.stat().st_size} bytes · sha256 {sha}")

if __name__ == "__main__":
    main()
