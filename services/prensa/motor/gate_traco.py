#!/usr/bin/env python3
"""PORTÃO DE TRAÇO — contraste da tinta NÃO-TEXTUAL, medido no pixel.

Por que existe: o portão de contraste do motor lê nós `data-verify`, que são
DIVs de texto. Um gráfico é SVG — seus rótulos e seus fios são invisíveis para
aquele portão. Pior: um fio de 1px NUNCA alcança a cor declarada, porque o
antialiasing mistura tinta e papel dentro do mesmo pixel. Então "declarei
#C9A84C" não prova nada sobre o que o olho recebe.

Este portão mede o que chegou ao papel:
  · o CHÃO é medido por ladrilho, não pela peça inteira — um vazamento de luz
    levanta a luminância só onde passa, e uma média global esconderia isso;
  · a TINTA é a mediana do núcleo do traço (os pixels mais próximos da cor
    declarada), não a cor declarada;
  · o PISO vem do papel da cor (ver graficos.PAPEL): argumento 3.0 (WCAG 1.4.11,
    objeto gráfico), rótulo 4.5, estrutura isenta — régua tênue é intenção.

Reprova também a tinta que não chegou: menos de 24 pixels de núcleo significa
que a cor foi declarada e não pintou nada legível.
Uso: gate_traco.py <png> <veredito.json> <spec.resolvido.json>"""
from __future__ import annotations
import json, sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
from graficos import PAPEL

PISO = {"argumento": 3.0, "rotulo": 4.5}
LADRILHOS = (6, 4)          # colunas × linhas: pega vazamento local sem custo alto
NUCLEO = 0.25               # fração mais próxima da cor declarada = núcleo do traço
MIN_NUCLEO = 24             # abaixo disso a tinta declarada não pintou nada

_LIN = [((c/255)/12.92 if c/255 <= 0.03928 else (((c/255)+0.055)/1.055)**2.4)
        for c in range(256)]

def _lum(rgb):
    r, g, b = rgb
    return 0.2126*_LIN[r] + 0.7152*_LIN[g] + 0.0722*_LIN[b]

def contraste(a, b):
    la, lb = _lum(a), _lum(b)
    if la < lb: la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)

def _hex(v):
    """Aceita #rgb, #rrggbb e rgb()/rgba() — o resolvedor emite os três."""
    v = v.strip()
    if v.startswith("rgb"):
        n = [float(x) for x in v[v.index("(")+1:v.index(")")].replace("/", ",").split(",")[:3]]
        return tuple(int(round(x)) for x in n)
    h = v.lstrip("#")
    if len(h) == 3: h = "".join(c*2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _mediana_rgb(px):
    n = len(px)
    return tuple(sorted(p[i] for p in px)[n//2] for i in range(3))

def audita(png: Path, veredito: dict, spec: dict, slide_id: str) -> dict:
    slide = next(s for s in spec["slides"] if s["id"] == slide_id)
    graficos = [c for c in slide["layers"] if c.get("type") == "grafico"]
    if not graficos:
        return {"ok": True, "medidas": [], "motivo": "sem gráfico"}
    caixas = {e["id"]: e["bbox"] for e in (veredito.get("extras") or [])}
    im = Image.open(png).convert("RGB")
    problemas, medidas = [], []

    for g in graficos:
        bb = caixas.get(g["id"])
        if not bb:
            problemas.append(f"{g['id']}: sem caixa medida no veredito"); continue
        crop = im.crop((bb["x"], bb["y"], bb["x"]+bb["w"], bb["y"]+bb["h"]))
        W, H = crop.size
        px = crop.load()
        # cores declaradas com papel cobrável
        # AGRUPAMENTO POR COR: dois papéis podem resolver para a MESMA tinta
        # (arco e faixa do mostrador são ambos o ouro da marca). O pixel não sabe
        # qual parâmetro o pintou — sabe a cor. Medir por parâmetro faria o
        # desempate por vizinhança descartar tudo e reprovar tinta que está lá.
        # Mede-se uma vez por cor distinta, cobrando o piso mais severo entre os
        # papéis que a compartilham.
        grupos = {}
        for k, v in g.items():
            if not k.startswith("cor_") or PAPEL.get(k) not in PISO: continue
            rgb = _hex(v)
            gr = grupos.setdefault(rgb, {"params": [], "piso": 0.0, "papel": ""})
            gr["params"].append(k)
            if PISO[PAPEL[k]] > gr["piso"]:
                gr["piso"], gr["papel"] = PISO[PAPEL[k]], PAPEL[k]
        alvos = {"+".join(sorted(v["params"])): rgb for rgb, v in grupos.items()}
        regra = {"+".join(sorted(v["params"])): v for v in grupos.values()}
        if not alvos: continue
        # DESAMBIGUAÇÃO DE TINTA: duas cores declaradas podem estar mais perto uma
        # da outra do que da tolerância de casamento — no painel, o cinza do rótulo
        # e o cinza da série "não cedeu" distam 43 no RGB. Limiar independente faz
        # o portão atribuir pixel de uma à outra e medir a cor errada (o sintoma é
        # a tinta "alcançada" sair MAIS ESCURA que a declarada, o que é impossível
        # sob antialiasing contra papel escuro). Cada pixel pertence à tinta mais
        # próxima, e só conta se a segunda estiver 1.6x mais longe.
        # a paleta de desambiguação é o conjunto de CORES distintas da peça —
        # inclusive as de estrutura, que competem pelos mesmos pixels — e a
        # comparação é por cor, nunca por nome de parâmetro: uma cor pode ser
        # cobrável sob um nome e isenta sob outro.
        paleta = list({_hex(v) for k, v in g.items() if k.startswith("cor_")})
        fundo = slide.get("background", "#000000")
        papel_escuro = _lum(_hex(fundo) if isinstance(fundo, str) else (0,0,0)) < 0.18
        nc, nl = LADRILHOS
        for k, alvo in alvos.items():
            papel, piso = regra[k]["papel"], regra[k]["piso"]
            pior = None
            for tj in range(nl):
                for ti in range(nc):
                    x0, x1 = ti*W//nc, (ti+1)*W//nc
                    y0, y1 = tj*H//nl, (tj+1)*H//nl
                    cand, chao = [], []
                    for y in range(y0, y1):
                        for x in range(x0, x1):
                            p = px[x, y]
                            chao.append(p)
                            ds = sorted((sum((p[i]-c[i])**2 for i in range(3)), c)
                                        for c in paleta)
                            if ds[0][1] != alvo or ds[0][0] >= 3000: continue
                            if len(ds) > 1 and ds[1][0] < ds[0][0] * 1.6: continue
                            cand.append((ds[0][0], p))
                    if len(cand) < MIN_NUCLEO: continue
                    # PAPEL, NÃO OUTRA TINTA: num ladrilho tomado por um
                    # preenchimento, a mediana simples pousa no preenchimento e o
                    # portão passaria a medir traço contra traço. O papel é o
                    # extremo de luminância oposto à tinta — mas não o extremo
                    # absoluto (isso seria o grão mais escuro, e inflaria a razão).
                    # Fatia [20%,45%] a partir do lado do papel: fora da tinta,
                    # dentro do papel, e sobe junto quando um vazamento levanta a luz.
                    chao.sort(key=_lum, reverse=not papel_escuro)
                    a, b = int(len(chao)*0.20), max(int(len(chao)*0.45), int(len(chao)*0.20)+1)
                    chao = chao[a:b]
                    cand.sort(key=lambda t: t[0])
                    nucleo = _mediana_rgb([p for _, p in cand[:max(8, int(len(cand)*NUCLEO))]])
                    razao = contraste(nucleo, _mediana_rgb(chao))
                    if pior is None or razao < pior[0]:
                        pior = (razao, nucleo, _mediana_rgb(chao), f"{ti},{tj}", len(cand))
            if pior is None:
                problemas.append(f"{g['id']}/{k}: tinta declarada não alcançou o papel "
                                 f"(<{MIN_NUCLEO}px de núcleo em todo ladrilho)")
                medidas.append({"no": f"{g['id']}/{k}", "papel": papel, "razao": None})
                continue
            razao, nucleo, chao, lad, n = pior
            ok = razao >= piso
            medidas.append({"no": f"{g['id']}/{k}", "papel": papel, "piso": piso,
                            "razao": round(razao, 2), "ladrilho": lad, "px": n,
                            "declarado": "#%02X%02X%02X" % alvo,
                            "alcancado": "#%02X%02X%02X" % nucleo,
                            "chao": "#%02X%02X%02X" % chao, "ok": ok})
            if not ok:
                problemas.append(f"{g['id']}/{k} ({papel}): {razao:.2f}:1 < {piso} "
                                 f"no ladrilho {lad} — declarado #%02X%02X%02X, "
                                 f"alcançado #%02X%02X%02X sobre #%02X%02X%02X"
                                 % (*alvo, *nucleo, *chao))
    return {"ok": not problemas, "problemas": problemas, "medidas": medidas}

if __name__ == "__main__":
    png, ver, esp = (Path(a) for a in sys.argv[1:4])
    v = json.loads(ver.read_text()); s = json.loads(esp.read_text())
    # o render nomeia peça única sem sufixo e carrossel com _sNN — a lâmina é
    # deduzida do nome, e cai na primeira quando não há sufixo.
    sid = v.get("slide")
    if not sid:
        cauda = png.stem.rsplit("_s", 1)
        i = int(cauda[1]) - 1 if len(cauda) == 2 and cauda[1].isdigit() else 0
        sid = s["slides"][i]["id"]
    r = audita(png, v, s, sid)
    for m in r["medidas"]:
        if m.get("razao") is None: continue
        print(f"   {'ok ' if m['ok'] else 'XX '}{m['no']:28} {m['papel']:9} "
              f"{m['razao']:>6.2f}:1 (piso {m['piso']}) {m['declarado']}→{m['alcancado']} /{m['chao']}")
    for p in r["problemas"]: print(f"   ⚠ {p}")
    print(("✅ TRAÇO OK " if r["ok"] else "❌ TRAÇO REPROVADO ") + png.name)
    sys.exit(0 if r["ok"] else 1)
