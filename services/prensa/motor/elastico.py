#!/usr/bin/env python3
"""FAIXA ELÁSTICA — mede quanto de TINTA cada gerador entrega por altura de caixa.

Por que existe: o solver decide o tamanho do gráfico para consumir o campo, e
para isso precisa saber duas coisas que ninguém pode declarar de cabeça —
(a) quanta tinta o gerador produz para um dado `h`, e (b) até onde ele ainda é
aquela forma. O painel que projetou o COSTURA foi ao fonte e provou que o
mostrador tinha inclinação ZERO: crescer a caixa não crescia o desenho. Um solver
apoiado em elasticidade presumida constrói sobre areia.

Mede-se span(h) em 7 pontos. A inclinação ajustada serve para JULGAR (cresce o
bastante para ser flexível?), nunca para inverter. Quem inverte é `resolve_h`,
por bissecção sobre medidas reais.

REPROVA um gerador quando:
  · inclinação < 0.25 — cresce tão pouco que não serve como flexível;
  · monotonia quebrada — dar mais espaço produzir menos tinta é bug, não forma;
  · amputação > 0 — tinta fora do viewport em qualquer eixo da faixa.

NÃO reprova por não-afinidade. A afinidade nunca foi requisito: o solver inverte
span→h por candidato MEDIDO com bissecção, nunca por interpolação de reta. Exigir
afinidade era testar propriedade que ninguém usa — e pior, dava a impressão de
cobrir a inversão errada que estava viva em costura.py.

Uso: elastico.py [kind ...]
"""
from __future__ import annotations
import io, json, sys
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI))
import graficos
from medida import _lum, _fronteira, PISO_TINTA

W = 884
PONTOS = 7
INCLINACAO_MIN = 0.25
FUNDO = "#0B1D3A"


MOLDURA = 200   # o SVG pode vazar para fora da caixa; sem moldura a chapa
                # recorta o vazamento e o instrumento mede 0 onde há amputação

def _pagina(svg: str, h: int) -> str:
    # overflow:visible tem de ir no <svg> TAMBÉM: ele recorta no próprio viewport
    # por padrão, então pô-lo só no <div> deixa o instrumento cego exatamente
    # para o defeito que ele existe para medir.
    return (f'<!doctype html><html><body style="margin:0;background:{FUNDO}">'
            f'<div style="position:absolute;left:{MOLDURA}px;top:{MOLDURA}px;'
            f'width:{W}px;height:{h}px;overflow:visible">'
            f'{svg.replace("<svg ", "<svg style=\'overflow:visible\' ", 1)}'
            f'</div></body></html>')


def _mede_ponto(page, kind: str, params: dict, h: int, h1: int) -> dict:
        svg = graficos.GRAFICOS[kind](w=W, h=h, **params)
        LARG, ALT = W + 2 * MOLDURA, h1 + 2 * MOLDURA
        page.set_viewport_size({"width": LARG, "height": ALT})
        page.set_content(_pagina("", h), wait_until="load")
        chao = _lum(np.asarray(Image.open(io.BytesIO(
            page.screenshot(clip={"x": 0, "y": 0, "width": LARG, "height": ALT}))
        ).convert("RGB"), dtype=np.uint8))
        page.set_content(_pagina(svg, h), wait_until="load")
        cheio = _lum(np.asarray(Image.open(io.BytesIO(
            page.screenshot(clip={"x": 0, "y": 0, "width": LARG, "height": ALT}))
        ).convert("RGB"), dtype=np.uint8))
        f = _fronteira(cheio, chao, PISO_TINTA)
        if not f:
            return {"h": h, "vazio": True, "span": 0, "amputado": 0}
        topo, base = f["topo"] - MOLDURA, f["base"] - MOLDURA   # a moldura desloca tudo
        esq, dir_ = f["esq"] - MOLDURA, f["dir"] - MOLDURA
        return {"h": h, "topo": topo, "base": base, "span": base - topo,
                "esq": esq, "dir": dir_,
                "amputado_v": max(0, base - h) + max(0, -topo),
                "amputado_h": max(0, dir_ - W) + max(0, -esq),
                "amputado": max(0, base - h) + max(0, -topo)
                           + max(0, dir_ - W) + max(0, -esq)}


def mede_kind(page, kind: str, params: dict, faixa_h: tuple[int, int]) -> dict:
    vp0 = page.viewport_size
    h0, h1 = faixa_h
    hs = [round(h0 + (h1 - h0) * i / (PONTOS - 1)) for i in range(PONTOS)]
    pts = []
    for h in hs:
        pt = _mede_ponto(page, kind, params, h, h1)
        if pt.get("vazio"):
            return {"kind": kind, "ok": False, "motivo": f"sem tinta em h={h}"}
        pts.append(pt)

    spans = [p["span"] for p in pts]
    n = len(hs); mh = sum(hs) / n; ms = sum(spans) / n
    den = sum((x - mh) ** 2 for x in hs)
    a = sum((x - mh) * (y - ms) for x, y in zip(hs, spans)) / den if den else 0.0
    b = ms - a * mh
    desvio = max(abs(y - (a * x + b)) for x, y in zip(hs, spans))
    monotona = all(spans[i] <= spans[i + 1] + 0.5 for i in range(n - 1))
    amputa = max(p["amputado"] for p in pts)

    probs = []
    if a < INCLINACAO_MIN:
        probs.append(f"kind_inelastico: inclinação {a:.3f} < {INCLINACAO_MIN} — "
                     f"span invariante para h em {faixa_h}; crescer a caixa não "
                     f"cresce o desenho, e o conserto é no gerador, não no solver")
    if not monotona:
        probs.append(f"nao_monotona: mais altura produziu menos tinta em algum ponto "
                     f"({spans}) — isso é bug de geometria, não escolha de forma")
    if amputa:
        probs.append(f"amputa: {amputa}px de tinta fora do viewport dentro da faixa")
    _restaura_viewport(page, vp0)
    return {"kind": kind, "ok": not probs, "problemas": probs,
            "faixa_h": list(faixa_h), "inclinacao": round(a, 3),
            "intercepto": round(b, 2), "desvio_max_px": round(desvio, 2),
            "faixa_span": [min(spans), max(spans)], "monotona": monotona,
            "amputado_max_px": amputa, "pontos": pts}


def _restaura_viewport(page, antes):
    if antes: page.set_viewport_size(antes)


def resolve_h(page, kind: str, params: dict, span_alvo: float,
              faixa_h: tuple[int, int], iteracoes: int = 6) -> dict:
    """Qual altura de caixa produz o span que o solver pediu — por BISSECÇÃO sobre
    medida real, nunca por inversão de reta. A relação span(h) não precisa ser
    afim, e para 2 dos 5 geradores ela não é: somar a excursão (o que costura.py
    fazia) só é exato quando dspan/dh vale 1, e a excursão do radar espalha 72px
    ao longo da faixa."""
    vp0 = page.viewport_size            # medir não deixa rastro em quem chamou
    lo, hi = faixa_h
    def span_de(h):
        p = _mede_ponto(page, kind, params, int(round(h)), faixa_h[1])
        return p["span"], p
    s_lo, _ = span_de(lo)
    s_hi, _ = span_de(hi)
    if not (s_lo <= span_alvo <= s_hi):
        h = lo if span_alvo < s_lo else hi
        s, pt = span_de(h)
        _restaura_viewport(page, vp0)
        return {"h": int(h), "span": s, "saturado": True, "ink_off": pt.get("topo"),
                "faixa_span": [s_lo, s_hi]}
    pt = None
    for _ in range(iteracoes):
        mid = (lo + hi) / 2
        s, pt = span_de(mid)
        if s < span_alvo: lo = mid
        else: hi = mid
    h = int(round((lo + hi) / 2))
    s, pt = span_de(h)
    _restaura_viewport(page, vp0)
    # `ink_off` NA ALTURA RESOLVIDA. A excursão de um gerador flexível não é
    # invariante em h para todo kind (o radar espalha 72px na faixa), então
    # posicionar com a excursão medida na altura ANTIGA erra pelo tanto que ela
    # mudou. Devolvida aqui, ela é a da peça que vai ser emitida.
    return {"h": h, "span": s, "saturado": False, "ink_off": pt.get("topo"),
 "erro_px": round(abs(s - span_alvo), 2),
            "faixa_span": [s_lo, s_hi]}


if __name__ == "__main__":
    spec = json.loads((AQUI / "out/anderson_grafico.vos-anderson-navy.resolvido.json").read_text())
    # usa os MESMOS parâmetros da peça real: cor muda contraste, e contraste
    # muda a fronteira de tinta. Medir com cor de laboratório mediria outra coisa.
    porkind = {}
    for sl in spec["slides"]:
        for c in sl["layers"]:
            if c.get("type") == "grafico":
                porkind[c["kind"]] = {k: v for k, v in c.items()
                                      if k not in ("id", "type", "kind", "pos", "w", "h")}
    alvos = sys.argv[1:] or list(porkind)
    fora = {}
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True, args=[
            "--disable-gpu", "--force-color-profile=srgb",
            "--font-render-hinting=none", "--disable-lcd-text", "--hide-scrollbars"])
        page = br.new_page(device_scale_factor=1)
        for kind in alvos:
            r = mede_kind(page, kind, porkind[kind], (260, 620))
            fora[kind] = r
            marca = "✓" if r["ok"] else "✗"
            print(f"  {marca} {kind:18} inclinação {r.get('inclinacao'):>6} · "
                  f"span {r.get('faixa_span')} · desvio {r.get('desvio_max_px')}px · "
                  f"amputa {r.get('amputado_max_px')}px")
            for pr in r.get("problemas", []):
                print(f"      ⚠ {pr}")
        br.close()
    (AQUI / "out" / "faixa_elastica.json").write_text(json.dumps(fora, indent=1, ensure_ascii=False))
    ruins = [k for k, v in fora.items() if not v["ok"]]
    print(f"\n{'❌' if ruins else '✅'} {len(fora)-len(ruins)}/{len(fora)} geradores "
          f"aptos a flexível" + (f" · fora: {ruins}" if ruins else ""))
    sys.exit(1 if ruins else 0)
