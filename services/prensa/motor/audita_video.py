#!/usr/bin/env python3
"""PRENSA → VÍDEO: audita a tipografia do runner Remotion medindo no MESMO motor.

A descoberta que torna a ponte barata: **Remotion É Chromium**. A medição que o
PRENSA faz para post estático vale idêntica para frame de vídeo — mesma engine,
mesmo shaping, mesmas fontes. Não é preciso portar nada: é o mesmo instrumento.

O que este script mede, com as fontes e os tamanhos REAIS do compositor holerite:

  1. `fitFont` do compositor é HEURÍSTICA POR CONTAGEM DE CARACTERE:
        min(base, maxW / (maior_palavra_em_chars * 0.6))
     Ela só impede uma PALAVRA de estourar a largura. Não sabe quantas linhas o
     bloco vai ter, não sabe a altura, não conhece a fonte. É chute educado.
  2. A medição real: binary-search do corpo com a fonte carregada, contando
     linhas de verdade — o mesmo laço do render.py do PRENSA.
  3. A divergência entre as duas, string por string.

Uso: .venv/bin/python audita_video.py
"""
from __future__ import annotations
import base64, json, math
from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).parent
BLACK = AQUI / "fonts/Archivo-Variable.ttf"      # Archivo Black = wght 900
MONO_B = AQUI / "fonts/IBMPlexMono-Bold.ttf"

# Canvas e safe area REAIS do motor de vídeo (motor/visual/fx.tsx:9)
W, H = 1080, 1920
SAFE = {"top": 120, "bottom": 320, "right": 140, "left": 60}

def fit_font_heuristica(texto: str, base: int, maxW: int = 1000, f: float = 0.52) -> int:
    """Réplica exata de fitFont() do compositor — para comparação honesta."""
    maior = max((len(p) for p in texto.split()), default=1)
    return min(base, math.floor(maxW / (maior * f)))

# strings REAIS do runner MEI + os tamanhos cravados no compositor holerite
CASOS = [
    # (rótulo, texto, familia, peso, tamanho_cravado, largura_disponivel, fitFont?)
    ("título do card", "MEI: O LIMITE QUE PEGA TODO MUNDO", "Archivo", 900, 92, 940, (92, 940, 0.6)),
    ("card: cabeçalho", "ENQUADRAMENTO MEI — 2026", "IBM Plex Mono", 700, 26, 772, None),
    ("card: cabeçalho 2", "TOLERANCIA DE 20% — A REGRA", "IBM Plex Mono", 700, 26, 772, None),
    ("card: linha", "DESENQUADRA SO NO ANO SEGUINTE", "IBM Plex Mono", 700, 28, 772, None),
    ("card: label", "LIMITE DE FATURAMENTO:", "IBM Plex Mono", 700, 24, 772, None),
    ("quiz: opção", "paga a diferença e segue", "IBM Plex Mono", 700, 40, 700, None),
    ("odômetro", "97.200", "IBM Plex Mono", 700, 92, 772, None),
    ("countdown", "DESENQUADRAMENTO RETROATIVO", "Archivo", 900, 74, 940, None),
]

JS = """
async (args) => {
  await document.fonts.ready;
  const el = document.getElementById('alvo');
  // getClientRects numa DIV devolve UMA caixa (a do bloco). Só um SPAN inline
  // devolve um retângulo por LINHA — é assim que se conta linha de verdade.
  const sp = document.getElementById('conteudo');
  el.style.fontFamily = `'${args.familia}'`;
  el.style.fontWeight = args.peso;
  el.style.fontVariationSettings = `'wght' ${args.peso}`;
  el.style.width = args.larg + 'px';
  sp.textContent = args.texto;
  const linhas = () => {
    const r = [...sp.getClientRects()];
    if (!r.length) return 0;
    const tops = [];
    for (const x of r) if (!tops.some(t => Math.abs(t - x.top) < 3)) tops.push(x.top);
    return tops.length;
  };
  // como o compositor renderiza hoje: tamanho cravado
  el.style.fontSize = args.cravado + 'px';
  const nCravado = linhas();
  const alturaCravado = el.getBoundingClientRect().height;
  const larguraUmaLinha = (() => { el.style.width = 'max-content';
    const w = el.getBoundingClientRect().width; el.style.width = args.larg + 'px'; return w; })();
  // medição PRENSA: maior corpo que cabe em N linhas
  let lo = 12, hi = args.cravado * 2;
  const cabe = (t) => { el.style.fontSize = t + 'px';
    return linhas() <= args.maxLinhas && el.scrollWidth <= el.clientWidth + 1; };
  let medido = null;
  if (cabe(lo)) { while (hi - lo > 0.5) { const m = (lo + hi) / 2; cabe(m) ? lo = m : hi = m; }
    medido = Math.floor(lo); }
  el.style.fontSize = args.cravado + 'px';
  return {linhas_cravado: nCravado, altura_cravado: Math.round(alturaCravado),
          largura_uma_linha: Math.round(larguraUmaLinha), medido};
}
"""

def main() -> None:
    faces = "".join(
        f"@font-face{{font-family:'{fam}';src:url('data:font/ttf;base64,"
        f"{base64.b64encode(p.read_bytes()).decode()}') format('truetype');"
        f"font-weight:{rng};}}"
        for fam, p, rng in [("Archivo", BLACK, "100 900"), ("IBM Plex Mono", MONO_B, "700")])
    html = (f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{faces}"
            f"*{{margin:0;padding:0;box-sizing:border-box}}</style></head>"
            f"<body style='width:{W}px;height:{H}px;background:#26251F'>"
            f"<div id='alvo' style='color:#F4EFE2;line-height:1.05;"
            f"word-break:normal;overflow-wrap:normal'>"
            f"<span id='conteudo'></span></div></body></html>")
    print(f"canvas {W}x{H} · safe {SAFE} · fontes reais do compositor holerite\n")
    print(f"{'elemento':18} {'crav':>5} {'linhas':>7} {'1 linha':>9} {'medido':>7}  veredito")
    print("-" * 78)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True,
                              args=["--disable-gpu", "--force-color-profile=srgb",
                                    "--font-render-hinting=none", "--hide-scrollbars"])
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.set_content(html, wait_until="load")
        achados = []
        for rot, txt, fam, peso, crav, larg, heur in CASOS:
            r = pg.evaluate(JS, {"texto": txt, "familia": fam, "peso": peso,
                                 "cravado": crav, "larg": larg, "maxLinhas": 2})
            estoura = r["largura_uma_linha"] > larg
            v = []
            if r["linhas_cravado"] > 2: v.append(f"{r['linhas_cravado']} linhas")
            if estoura: v.append(f"não cabe em 1 linha ({r['largura_uma_linha']}px > {larg})")
            if heur:
                h = fit_font_heuristica(txt, *heur)
                if r["medido"] and abs(h - r["medido"]) > 4:
                    v.append(f"heurística diz {h}px, medição diz {r['medido']}px")
            achados.append((rot, bool(v)))
            print(f"{rot:18} {crav:>4}px {r['linhas_cravado']:>7} {r['largura_uma_linha']:>8}px "
                  f"{str(r['medido'] or '—'):>7}  {'⚠ ' + ' · '.join(v) if v else '✓'}")
        b.close()
    n = sum(1 for _, x in achados if x)
    print(f"\n{n} de {len(achados)} elementos com divergência entre o cravado e o medido.")

if __name__ == "__main__":
    main()
