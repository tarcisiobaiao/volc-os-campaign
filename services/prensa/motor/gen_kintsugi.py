#!/usr/bin/env python3
"""PRENSA POC — gera o fundo da rota KINTSUGI (estátua estoica) via gpt-image-2.

Origem da rota: bancada-n8n/viral-images-wow-v3.json, nó `AI Agent5` + persona
`personas/vos-kintsugi-v4.0.md`. O fluxo original pedia a TIPOGRAFIA ao modelo de
imagem ("legenda estilo Netflix, fonte amarela com borda preta"). Aqui a imagem é
só fotografia: o texto vem do engine, e a posição dele é DESCOBERTA por medição.

Por isso o prompt também não pede gradiente nem área escura reservada — a
composição é livre, e o analisador acha o lugar do texto depois.

Credencial pela porta única `ambiente.chave` (ver ../AUDITORIA-SEGREDOS.md).
Uso: python3 gen_kintsugi.py
"""
from __future__ import annotations
import base64, hashlib, json, sys, urllib.request
from pathlib import Path

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI))
from ambiente import chave  # noqa: E402  (porta única de credencial)

QUALIDADE = sys.argv[1] if len(sys.argv) > 1 else "medium"
OUT = AQUI / "out" / f"bg_kintsugi_{QUALIDADE}.png"

PROMPT = (
    "Vertical 4:5 cinematic photograph of a broken classical marble statue — a stoic "
    "philosopher bust and shoulders — standing in a vast dark void. "
    "The marble is pale and luminous with bold sculpted contours. "
    "KINTSUGI: thick molten-gold cracks (#FFD700) run through the marble like glowing "
    "golden rivers, some edged with neon purple (#BF00FF), lit from within. "
    "The eyes are deep black voids with small neon green (#39FF14) stars glowing inside. "
    "A few luminous butterflies float around the figure — neon green, neon purple and gold, "
    "each softly glowing. A subtle neon purple mystical aura surrounds the statue, with fine "
    "light particles and scattered tiny green stars in the air. "
    "Background: very deep black to dark purple (#0a0a0f to #1a0a2e), maximum contrast, "
    "empty and atmospheric, with soft nebula hints. "
    "The statue occupies roughly the upper-right portion of the frame; the rest of the "
    "frame is deep atmospheric emptiness. "
    "Light sources: the golden cracks, the green eyes, and the purple ambient aura. "
    "Hyper-detailed, dramatic, mystical, cinematic. "
    "ABSOLUTELY NO text, no letters, no numbers, no captions, no subtitles, no watermark, "
    "no logo, no signature, no graphic overlay, no gradient bar, no borders, no frame."
)

def main() -> None:
    # Falha ANTES de montar o corpo: sem chave, nenhuma chamada e nada escrito.
    chave_openai = chave("OPENAI_API_KEY")
    corpo = json.dumps({"model": "gpt-image-2", "prompt": PROMPT,
                        "size": "1088x1360", "quality": QUALIDADE, "n": 1}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations", data=corpo,
        headers={"Authorization": f"Bearer {chave_openai}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP {e.code}: {e.read().decode()[:400]}"); sys.exit(1)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(base64.b64decode(resp["data"][0]["b64_json"]))
    u = resp.get("usage") or {}
    print(f"✅ {OUT.name} · qualidade={QUALIDADE} · {OUT.stat().st_size} bytes")
    print(f"   uso reportado pela API: {json.dumps(u)}")

if __name__ == "__main__":
    main()
