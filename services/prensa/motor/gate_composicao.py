#!/usr/bin/env python3
"""PORTÕES UNIVERSAIS DE COMPOSIÇÃO — medem a distribuição vertical na TINTA.

Universais quer dizer: NÃO dependem de o spec declarar nada. Valem sobre qualquer
peça do parque desde já, migrada ou não. O solver (COSTURA) é opt-in; a lei não.
Essa partição é deliberada — as três arquiteturas propostas tornavam solver e
portão opt-in juntos, e nenhuma delas reprovava as lâminas que estavam erradas.

Todos operam sobre `medida.py`, isto é, sobre a fronteira de TINTA derivada do
piso de contraste que o motor já cobra — nunca sobre a caixa declarada. A caixa
mente: medido neste parque, ela excede a tinta do gráfico em até 190px.

  G-CLIP    o gráfico não amputa a própria tinta. O SVG recorta no próprio
            viewport, então tinta que sai da caixa some sem deixar rastro. Mede-se
            com overflow desligado e compara-se. REPROVA a partir de 1px.
  G-TINTA   nenhum par de blocos empilhados fica mais perto que `clearance_px`.
            Vão vertical só existe entre blocos que se cruzam na horizontal —
            sem essa condição, todo rodapé de dois cantos vira falsa colisão.
  G-BURACO  vão INTERIOR maior que 3M é inominável: não existe laço no vocabulário
            do motor que produza tanto. O teto não é constante nova — é o degrau
            mais alto da escada de laços. Interior é definição POSICIONAL (nem o
            primeiro nem o último vão), então não depende de declarar taxonomia.
  G-ANCORA  se AMBAS as costuras de borda excedem 3× o maior vão interior, a
            mancha perdeu relação com os dois trilhos e flutua. Uma borda grande
            é margem, e margem é correta; duas é ilha.
  G-AMBIGUA o instrumento não pode mentir: se a fronteira da tinta anda mais que
            M/4 ao varrer o piso de contraste ±20%, a medida é convenção e não
            tinta, e nenhuma decisão de posição pode se apoiar nela.

O MÓDULO M, aqui, é medido por lâmina: metade da entrelinha resolvida da headline
(M = L/2). A co-quantização de M pelo lote inteiro pertence ao solver; para o
portão universal, que roda sobre peça não migrada, a entrelinha da própria lâmina
é a única referência honesta — e é medida, não declarada.

Uso: gate_composicao.py out/<spec>.resolvido.json
"""
from __future__ import annotations
import json, sys
from pathlib import Path

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI))
import medida

TETO_INTERIOR_M = 3.0      # degrau mais alto da escada de laços (articulacao = 3M)
RESOLUCAO_PX = 2           # a chapa mede linhas INTEIRAS de pixel, e a FAIXA é a
                           # diferença entre DUAS fronteiras quantizadas de forma
                           # independente (base de um bloco, topo do seguinte):
                           # cada uma erra até 1px contra a posição geométrica,
                           # logo a faixa erra até 2. Não é tolerância — o teto
                           # continua sendo 3M, o degrau mais alto da escada. É a
                           # resolução do instrumento, e ignorá-la reprovava por
                           # 0.6px uma costura emitida exatamente no teto.
RAZAO_ANCORA = 3.0         # mesma razão de saturação; nenhuma constante nova
FRACAO_AMBIGUA = 0.25      # M/4: o menor passo emitido é M/2 — ambiguidade abaixo
                           # de meio-passo não pode virar decisão de posição


def _modulo(veredito: dict, slide: dict) -> tuple[float | None, str]:
    """M = L/2, com L = entrelinha resolvida da headline, medida no Chromium."""
    alvo = next((c["id"] for c in slide["layers"] if c.get("slot") == "headline"), None)
    ev = (veredito.get("evidencia") or {}).get(alvo or "", {})
    fs, lh = ev.get("font_size_px"), ev.get("line_height")
    if not fs:
        return None, "lâmina sem headline medida"
    return (fs * (lh or 1.2)) / 2, f"L_{alvo}/2"


def audita(m_slide: dict, veredito: dict, slide: dict, clearance: int = 16) -> dict:
    probs, medidas = [], {}
    blocos = m_slide["blocos"]

    # ── G-CLIP
    for bid, b in blocos.items():
        if b.get("amputado_px"):
            probs.append(f"G-CLIP/{bid}: {b['amputado_px']}px de tinta amputada pelo "
                         f"viewport do próprio SVG")

    # ── G-AMBIGUA (precisa de M; sem headline, cobra o piso absoluto de 1px)
    M, origem = _modulo(veredito, slide)
    medidas["modulo_px"] = round(M, 2) if M else None
    medidas["modulo_origem"] = origem
    teto_amb = M * FRACAO_AMBIGUA if M else 1
    for bid, b in blocos.items():
        if b.get("ambiguidade_px", 0) > teto_amb:
            probs.append(f"G-AMBIGUA/{bid}: fronteira da tinta anda {b['ambiguidade_px']}px "
                         f"ao varrer o piso ±20% (teto {teto_amb:.1f}px) — o instrumento "
                         f"está medindo convenção, não tinta")

    # ── vãos de tinta, só entre blocos que se cruzam na horizontal
    bs = sorted(((k, v) for k, v in blocos.items() if v.get("topo") is not None),
                key=lambda kv: kv[1]["topo"])
    # duas leituras da mesma costura, porque são duas perguntas:
    #   `aprox` = aproximação máxima entre as formas (colisão)  → G-TINTA
    #   `banda` = branco corrido entre os extremos (ritmo)      → G-BURACO/G-ANCORA
    seq, ant, ant_id, anterior = [], None, None, None
    for k, v in bs:
        if anterior is not None:
            aprox = medida.vao_entre(anterior, v)
            banda = medida.banda_entre(anterior, v)
            if aprox is not None: seq.append((ant_id, k, banda, aprox))
        if anterior is None or v["base"] > (ant or 0):
            ant, ant_id, anterior = v["base"], k, v
    medidas["vaos"] = [{"de": a, "para": b, "banda": bd, "aprox": ap}
                       for a, b, bd, ap in seq]

    # ── G-TINTA (aproximação máxima, coluna a coluna)
    for a, b, bd, ap in seq:
        if ap < clearance:
            probs.append(f"G-TINTA/{a}→{b}: {ap}px de tinta a tinta, abaixo do "
                         f"respiro de {clearance}px")

    # ── G-BURACO / G-ANCORA (bordas = primeira e última costura, por POSIÇÃO)
    if len(seq) >= 3 and M:
        interiores = seq[1:-1]
        maior = max(interiores, key=lambda t: t[2])   # pela BANDA, não pela aproximação
        teto = TETO_INTERIOR_M * M
        medidas["maior_interior"] = {"de": maior[0], "para": maior[1], "px": maior[2],
                                     "teto_px": round(teto, 2)}
        if maior[2] > teto + RESOLUCAO_PX:
            probs.append(f"G-BURACO/{maior[0]}→{maior[1]}: vão interior de {maior[2]}px "
                         f"excede 3M = {teto:.1f}px — nenhum laço do vocabulário "
                         f"produz esse vão, logo ele não foi desenhado, sobrou")
        b0, b1 = seq[0][2], seq[-1][2]
        medidas["bordas"] = {"topo": b0, "base": b1}
        if b0 > RAZAO_ANCORA * maior[2] and b1 > RAZAO_ANCORA * maior[2]:
            probs.append(f"G-ANCORA: ambas as bordas ({b0}px e {b1}px) excedem "
                         f"{RAZAO_ANCORA}× o maior interior ({maior[2]}px) — a mancha "
                         f"flutua, sem relação com nenhum dos dois trilhos")

    return {"ok": not probs, "problemas": probs, "medidas": medidas}


def audita_emitido(png, veredito: dict, spec: dict, slide_id: str,
                   clearance: int = 16) -> dict:
    """Audita a peça EMITIDA, não o layout de referência. Reconstrói a lâmina com
    a composição aplicada e a altura de gráfico que foi de fato usada, mede, e
    julga. Sem isto, um gráfico pousado sobre a headline atravessa dom, pixel e
    traço sem um arranhão — aconteceu, e é o motivo deste caminho existir."""
    from playwright.sync_api import sync_playwright
    import render as R

    slide = next(s for s in spec["slides"] if s["id"] == slide_id)
    pos = veredito.get("composicao_aplicada")
    if not pos:                       # lâmina não gerida: audita o layout como está
        return audita(medida_de(spec, slide), veredito, slide, clearance)

    import copy
    sl = copy.deepcopy(slide)
    for cam in sl["layers"]:
        hr = (pos.get(cam.get("id")) or {}).get("h_resolvido")
        if hr: cam["h"] = hr
    base = spec["artboard"]["base"]
    fj = [{"familia": f["family"], "peso": f.get("weight", 400)} for f in spec["fonts"]]
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True, args=[
            "--disable-gpu", "--force-color-profile=srgb",
            "--font-render-hinting=none", "--disable-lcd-text", "--hide-scrollbars"])
        pg = br.new_page(viewport={"width": base["w"], "height": base["h"]},
                         device_scale_factor=1)
        ms = medida.mede_slide(pg, sl, spec, fj, aplicar=pos)
        br.close()
    return audita(ms, veredito, sl, clearance)


def medida_de(spec, slide):
    from playwright.sync_api import sync_playwright
    base = spec["artboard"]["base"]
    fj = [{"familia": f["family"], "peso": f.get("weight", 400)} for f in spec["fonts"]]
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True, args=[
            "--disable-gpu", "--force-color-profile=srgb",
            "--font-render-hinting=none", "--disable-lcd-text", "--hide-scrollbars"])
        pg = br.new_page(viewport={"width": base["w"], "height": base["h"]},
                         device_scale_factor=1)
        ms = medida.mede_slide(pg, sl := slide, spec, fj)
        br.close()
    return ms


def main() -> None:
    spec_path = AQUI / sys.argv[1]
    spec = json.loads(spec_path.read_text())
    m = medida.mede(spec_path)
    base = spec_path.name.split(".")[0]
    slides = spec.get("slides") or [{"id": spec["spec_id"], "layers": spec["layers"]}]
    clearance = spec["gates"].get("clearance_decorativo_px", 16)
    falhas = 0
    for i, (sl, ms) in enumerate(zip(slides, m["slides"]), 1):
        nome = f"{base}_s{i:02d}" if len(slides) > 1 else base
        vp = AQUI / "out" / f"{nome}.veredito.json"
        ver = json.loads(vp.read_text()) if vp.exists() else {}
        r = audita(ms, ver, sl, clearance)
        mm = r["medidas"]
        mi = mm.get("maior_interior")
        resumo = (f"M={mm['modulo_px']} · maior interior "
                  f"{mi['px']}px (teto {mi['teto_px']})" if mi else f"M={mm.get('modulo_px')}")
        print(f"  {'✓' if r['ok'] else '✗'} {sl['id']:12} {resumo}")
        for p in r["problemas"]:
            print(f"      ⚠ {p}")
        falhas += not r["ok"]
    print(f"\n{'❌' if falhas else '✅'} COMPOSIÇÃO — {falhas}/{len(slides)} lâmina(s) reprovada(s)")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
