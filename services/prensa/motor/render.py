#!/usr/bin/env python3
"""PRENSA POC — render.py v2: spec RESOLVIDO → HTML inline-only → Chrome headless
→ fit por binary-search → verify DOM ANTES do screenshot → PNG(s) + evidência.
v2: multi-slide (carrossel), runs com accent, rect/dots/texture/ghost, fontes por skin.
Doutrina: reprovou no verify = NENHUM PNG do slide é escrito (fail-closed).
Uso: .venv/bin/python render.py out/<spec>.resolvido.json [--sufixo _x]"""
from __future__ import annotations
import base64, hashlib, json, sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI))  # graficos.py

# ---------------------------------------------------------------------------
# BIBLIOTECA DE EFEITOS — todos simulam PROCESSO FÍSICO (filme, lente, papel,
# tinta), nunca "glow bonito". É essa diferença que tira a cara de AI design:
# o olho reconhece halação de lente e grão de filme como fotografia; reconhece
# glow neon e mesh gradient como render de IA.
# 100% determinístico (seed fixa), zero rede, zero API.
# ---------------------------------------------------------------------------

def svg_ruido(seed: int, freq: float, octaves: int, tile: int = 300,
              como_alpha: bool = False, piso: float | None = None,
              amplitude: float = 1.0) -> str:
    """Turbulência fractal → data-URI. como_alpha=True gera máscara (canal R vira
    alpha), usada para DISSOLVER gradiente em grão em vez de deixar banding.

    piso/amplitude remapeiam o ruído para uma faixa estreita perto do branco.
    Motivo medido: sobre fundo claro (L≈249) os blends overlay/soft-light
    SATURAM e não produzem textura alguma; só multiply funciona — e multiply
    com ruído cinza escurece o papel inteiro. Ruído com piso 0.86 multiplica
    sem deslocar a cor: fibra sem sujar o creme."""
    if como_alpha:
        matriz = ("<feColorMatrix type='matrix' values='0 0 0 0 0  0 0 0 0 0  "
                  "0 0 0 0 0  1 0 0 0 0'/>")
    elif piso is not None:
        matriz = ("<feColorMatrix type='saturate' values='0'/>"
                  "<feComponentTransfer>"
                  f"<feFuncR type='linear' slope='{amplitude}' intercept='{piso}'/>"
                  f"<feFuncG type='linear' slope='{amplitude}' intercept='{piso}'/>"
                  f"<feFuncB type='linear' slope='{amplitude}' intercept='{piso}'/>"
                  "<feFuncA type='linear' slope='0' intercept='1'/>"
                  "</feComponentTransfer>")
    else:
        matriz = "<feColorMatrix type='saturate' values='0'/>"
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{tile}' height='{tile}'>"
           f"<filter id='f' x='0' y='0' width='100%' height='100%'>"
           f"<feTurbulence type='fractalNoise' baseFrequency='{freq}' "
           f"numOctaves='{octaves}' seed='{seed}' stitchTiles='stitch'/>{matriz}</filter>"
           f"<rect width='{tile}' height='{tile}' filter='url(#f)'/></svg>")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()

def err(msg: str) -> None:
    print(f"❌ RENDER: {msg}"); sys.exit(1)

def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"

def css_gradient(scrim: dict) -> str:
    # stops na ordem declarada: em "to top", 0% = borda inferior (piso do texto)
    stops = ", ".join(f"{s['cor']} {s['at']}" for s in scrim["stops"])
    return f"linear-gradient({scrim['direcao']}, {stops})"

def _pos_css(layer: dict, W: int, H: int) -> str:
    """Posição de um layer/frame: anchor + offset em px (já resolvidos)."""
    pos = layer.get("pos", {})
    anchor = pos.get("anchor", "top_left")
    ox, oy = pos.get("x", 0), pos.get("y", 0)
    partes = ["position:absolute"]
    partes.append(f"left:{ox}px" if "left" in anchor else f"right:{ox}px")
    partes.append(f"top:{oy}px" if "top" in anchor else f"bottom:{oy}px")
    if "max_width" in layer:
        partes.append(f"max-width:{layer['max_width']}px")
    if "width" in layer:
        partes.append(f"width:{layer['width']}px")
    return ";".join(partes)

def filtros_svg(seed: int = 3) -> str:
    """Defs de filtro SVG usadas pelos tratamentos de tipografia. São simulações
    ópticas/mecânicas reais — não 'brilho bonito':

    verniz3d  — feSpecularLighting com luz distante: relevo REAL calculado a partir
                do alfa do glifo. É o que hot foil e verniz localizado fazem com a luz.
    mordida   — feMorphology (ganho de tinta) + feDisplacementMap (turbulência):
                a borda do glifo perde a perfeição vetorial, como tipo mordendo papel.
    """
    return f"""<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<filter id="verniz3d" x="-25%" y="-25%" width="150%" height="150%">
  <feGaussianBlur in="SourceAlpha" stdDeviation="4" result="rel"/>
  <feSpecularLighting in="rel" surfaceScale="9" specularConstant="1.5"
      specularExponent="14" lighting-color="#fff6e8" result="esp">
    <feDistantLight azimuth="228" elevation="46"/>
  </feSpecularLighting>
  <feComposite in="esp" in2="SourceAlpha" operator="in" result="espRec"/>
  <feOffset in="SourceAlpha" dx="0" dy="3" result="sombraA"/>
  <feFlood flood-color="#000" flood-opacity="0.55" result="preto"/>
  <feComposite in="preto" in2="sombraA" operator="in" result="sombra"/>
  <feMerge>
    <feMergeNode in="sombra"/><feMergeNode in="SourceGraphic"/>
    <feMergeNode in="espRec"/>
  </feMerge>
</filter>
<filter id="duotone" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">
  <feColorMatrix type="matrix" result="cinza"
      values="0.2126 0.7152 0.0722 0 0  0.2126 0.7152 0.0722 0 0
              0.2126 0.7152 0.0722 0 0  0 0 0 1 0"/>
  <feComponentTransfer in="cinza">
    <feFuncR type="table" tableValues="0.055 0.87"/>
    <feFuncG type="table" tableValues="0.06 0.62"/>
    <feFuncB type="table" tableValues="0.075 0.34"/>
  </feComponentTransfer>
</filter>
<filter id="mordida" x="-12%" y="-12%" width="124%" height="124%">
  <feTurbulence type="fractalNoise" baseFrequency="0.045 0.09" numOctaves="3"
      seed="{seed}" result="ruido"/>
  <feDisplacementMap in="SourceGraphic" in2="ruido" scale="3.2"
      xChannelSelector="R" yChannelSelector="G" result="desl"/>
  <feMorphology in="desl" operator="dilate" radius="0.4"/>
</filter>
</defs></svg>"""

def _lum_rel(c8: float) -> float:
    c = c8 / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def tinta_sobre(hexa: str, claro: str = "#FFFFFF", escuro: str = "#111111") -> str:
    """Escolhe a tinta MEDINDO o contraste contra a chapa, em vez de decorar.

    Marca costuma cravar 'palavra destacada fica branca' — e sobre highlight
    amarelo isso dá ~1,3:1. A cor do texto sobre um campo pintado não é decisão
    de gosto: é a que ganha na conta."""
    r, g, b = (int(hexa.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    Y = 0.2126 * _lum_rel(r) + 0.7152 * _lum_rel(g) + 0.0722 * _lum_rel(b)
    def contra(t):
        tr, tg, tb = (int(t.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        Yt = 0.2126 * _lum_rel(tr) + 0.7152 * _lum_rel(tg) + 0.0722 * _lum_rel(tb)
        hi, lo = max(Y, Yt), min(Y, Yt)
        return (hi + 0.05) / (lo + 0.05)
    return claro if contra(claro) >= contra(escuro) else escuro

def _tratamento_css(t: dict, camada: dict) -> str:
    """CSS de um tratamento aplicado a UM run. Cada um tem referente material."""
    k = t["tipo"]
    if t.get("cor_texto") == "auto":
        t = {**t, "cor_texto": tinta_sobre(t["cor"])}
    if k == "marcador":
        # MARCADOR: bloco de tinta atrás da palavra. O BLEND DEPENDE DO FUNDO —
        # multiply só funciona sobre claro (é assim que marca-texto age no papel);
        # sobre fundo escuro ele apaga a palavra e o correto é screen.
        return (f'background:{t["cor"]};mix-blend-mode:{t.get("blend", "multiply")};'
                f'color:{t.get("cor_texto", "inherit")};'
                f'box-decoration-break:clone;-webkit-box-decoration-break:clone;'
                f'padding:{t.get("padding", "0.02em 0.12em 0.06em")};'
                f'border-radius:{t.get("radius", "0.04em")}')
    if k == "riso":
        # RISOGRAFIA: duas passadas de cor fora de registro. O deslocamento é o
        # erro mecânico da impressora — e é ele que grita "impresso, não render".
        d = t.get("desvio", "0.045em")
        return (f'color:{t["cor"]};'
                f'text-shadow:{d} {d} 0 {t["cor_fantasma"]};'
                f'mix-blend-mode:{t.get("blend", "normal")}')
    if k == "knockout":
        # KNOCKOUT: a palavra é vazada do bloco — a tinta é o fundo, não a letra
        return (f'background:{t["cor"]};color:{t["cor_texto"]};'
                f'box-decoration-break:clone;-webkit-box-decoration-break:clone;'
                f'padding:{t.get("padding", "0.02em 0.14em 0.08em")}')
    if k == "contorno":
        # CONTORNO: só o traço. Uma palavra oca no meio das cheias — hierarquia
        # por PESO ÓPTICO, não por cor.
        return (f'-webkit-text-stroke:{t.get("espessura", "2px")} {t["cor"]};'
                f'color:transparent;paint-order:stroke fill')
    if k == "recorte":
        # RECORTE: a própria FOTO preenche a letra. Único uso legítimo de
        # background-clip:text — material real, não gradiente decorativo.
        # o recorte precisa de faixa tonal PRÓPRIA: a foto que serve de fundo é
        # exposta para a cena, e dentro da letra ela vira tipografia — o gate de
        # contraste mede a letra, não a cena. Daí o ajuste declarado.
        ajuste = (f'filter:{t["ajuste"]};' if t.get("ajuste") else "")
        return (f'background-image:url(\'{t["imagem"]}\');'
                f'background-size:{t.get("cobertura", "160%")};'
                f'background-position:{t.get("origem", "center 30%")};'
                f'-webkit-background-clip:text;background-clip:text;'
                f'color:transparent;{ajuste}')
    if k == "verniz":
        return "filter:url(#verniz3d)"
    if k == "mordida":
        return "filter:url(#mordida)"
    if k == "peso":
        # PESO: ênfase por eixo de fonte variável. Mais sofisticado que cor —
        # é a mesma voz falando mais alto, não outra voz.
        return (f'font-variation-settings:\'wght\' {t.get("wght", 900)};'
                f'font-weight:{t.get("wght", 900)}')
    err(f"tratamento tipográfico desconhecido: {k}")

def _spans(camada: dict, so_accent: bool = False) -> str:
    """so_accent=True: mantém o texto ocupando o mesmo espaço, mas só o acento
    pinta. É a fonte do halo — quem sangra luz é a cor saturada, não o corpo."""
    accent_cor = camada.get("style", {}).get("accent_color")
    out = []
    for r in camada["runs"]:
        texto = r["text"].replace("\n", "<br>")
        if r.get('nowrap'):
            texto = '<span style="white-space:nowrap">'+texto+'</span>'
        # TIPOGRAFIA DUAL: um run pode trocar de FAMÍLIA no meio da frase — a
        # palavra emocional em serifada itálica dentro da grotesca bold. É ênfase
        # por VOZ, não por cor: a frase muda de timbre, não de destaque.
        f2 = r.get("fonte")
        if f2 and not so_accent:
            css2 = (f'font-family:\'{f2["family"]}\',serif;'
                    f'font-weight:{f2.get("weight", 500)};'
                    f'font-style:{f2.get("style", "italic")};'
                    f'font-size:{f2.get("escala", 1.0)}em;'
                    f'letter-spacing:{f2.get("tracking", "normal")};'
                    f'font-variation-settings:{f2.get("variacao", "normal")}')
            out.append(f'<span data-dual style="{css2}">{texto}</span>')
            continue
        trat = r.get("tratamento")
        if trat and not so_accent:
            # accent e tratamento COMPÕEM: a cor entra primeiro e o tratamento
            # pode sobrescrevê-la. Sem isso, verniz/mordida perdem a cor do acento.
            base = f"color:{accent_cor};" if (r.get("accent") and accent_cor) else ""
            out.append(f'<span data-trat style="{base}{_tratamento_css(trat, camada)}">{texto}</span>')
        elif r.get("accent") and accent_cor:
            out.append(f'<span data-accent style="color:{accent_cor}">{texto}</span>')
        else:
            cor = "transparent" if so_accent else "inherit"
            out.append(f'<span style="color:{cor}">{texto}</span>')
    return "".join(out)

def html_runs(camada: dict) -> str:
    """Runs → spans. '\\n' no texto é quebra EDITORIAL declarada (fronteira sintática
    escolhida por quem escreve), não sugestão: vira <br> e continua sujeita ao max_lines.

    HALAÇÃO: cópia desfocada por trás do texto — o sangramento de luz que filme e
    lente produzem em torno de fontes brilhantes. Renderiza DENTRO do nó (absoluta,
    fora do fluxo) e a caixa do nó cresce pelo raio do halo, de modo que a tinta
    espalhada continue dentro do box declarado. Efeito que vaza da caixa é bug;
    efeito que declara sua caixa é design."""
    corpo = _spans(camada)
    fx = camada.get("efeitos") or {}
    conteudo = f'<span data-conteudo style="display:inline">{corpo}</span>'
    if "halacao" not in fx:
        return conteudo
    passes = fx["halacao"].get("passes", [[18, 0.55], [46, 0.30]])
    fonte_halo = _spans(camada, so_accent=True)
    r = max(p[0] for p in passes)
    if "sombra" in fx:  # o padding real é o maior orçamento; o halo segue ele
        sb = fx["sombra"]; r = max(r, sb.get("raio", 16) + sb.get("dy", 2))
    halos = "".join(
        f'<span aria-hidden="true" style="display:block;filter:blur({raio}px);'
        f'opacity:{op};">{fonte_halo}</span>' for raio, op in passes)
    # halo ANTES do conteúdo (pinta atrás), fora do fluxo, e recuado pelo padding
    # do orçamento do efeito — assim registra EXATAMENTE sobre as letras
    return (f'<span aria-hidden="true" style="position:absolute;left:{r}px;top:{r}px;'
            f'width:calc(100% - {2*r}px);pointer-events:none;">{halos}</span>{conteudo}')

def html_texto(camada: dict) -> str:
    fit = camada["fit"]
    estilo = camada["style"]
    fonte = estilo["font"]
    decorativo = " data-decorative data-mask" if camada.get("decorative") else " data-verify"
    tam_ini = fit["size"] if fit["mode"] == "fixed" else fit["max"]
    peso = fonte.get("weight", 400)
    css = [
        # ink_padding: fontes cujos glifos pintam fora do layout box (descendentes de
        # serifa display) declaram o respiro no token — o box DECLARADO cobre a TINTA
        f'padding:{fonte.get("ink_padding", "0")}',
        f'font-family:\'{fonte["family"]}\',sans-serif', f"font-weight:{peso}",
        f"font-size:{tam_ini}px", f'line-height:{fonte.get("line_height", 1.2)}',
        f'color:{estilo["color"]}', "margin:0",
        f'letter-spacing:{fonte.get("tracking", "normal")}',
        f'text-transform:{fonte.get("transform", "none")}',
        f'text-wrap:{"balance" if fonte.get("wrap") == "balance" else "normal"}',
        f'font-style:{fonte.get("style", "normal")}',
        "hyphens:none", "overflow-wrap:normal",
        # hang: pontuação inicial (travessão, aspas) pendurada à esquerda da coluna.
        # margin, NÃO text-indent: a caixa precisa acompanhar a tinta, senão o
        # pixel gate acusa overflow (o plano descreve onde a tinta está).
        f'margin-left:{fonte.get("hang", "0")}',
        # features OpenType da SKIN (ex.: lnum força algarismos lining em fontes
        # old-style — sem isso o ghost numeral muda de altura a cada lâmina)
        f'font-feature-settings:{fonte.get("features", "normal")}',
    ]
    if fonte.get('variacao'):
        css.append(f'font-variation-settings:{fonte["variacao"]}')
    sombras = [estilo['shadow']] if estilo.get('shadow') not in (None, 'none') else []
    if "opacity" in estilo:
        css.append(f'opacity:{estilo["opacity"]}')
    fx = camada.get("efeitos") or {}
    # ORÇAMENTO ÚNICO (Lei 9): cada efeito que espalha tinta declara seu alcance;
    # a caixa cresce UMA vez pelo maior deles e a margem negativa devolve a posição.
    # Somar padding por efeito deslocaria o bloco duas vezes.
    orcamento = 0
    if "halacao" in fx:
        orcamento = max(orcamento, max(p[0] for p in fx["halacao"].get("passes", [[46, 0]])))
    if "sombra" in fx:
        # SOMBRA DE LEGIBILIDADE: não é decoração — é o seguro contra a foto que
        # muda debaixo da letra. Difusa e sem deslocamento lateral, para ler como
        # densidade do fundo e não como camada de template.
        s = fx["sombra"]
        raio, dy = s.get("raio", 16), s.get("dy", 2)
        sombras.append(f'0 {dy}px {raio}px {s.get("cor", "rgba(0,0,0,0.78)")}')
        orcamento = max(orcamento, raio + dy)
    if orcamento:
        css += ["position:relative", f"padding:{orcamento}px", f"margin:-{orcamento}px"]
    if "sangria" in fx:
        # SANGRIA DE TINTA: a tinta penetra a fibra do papel e o glifo perde o
        # corte vetorial perfeito. É a assinatura de impresso — e o contrário
        # dela (borda infinitamente nítida) é o que denuncia render digital.
        # Um sopro da PRÓPRIA cor, nunca offset: offset vira sombra de template.
        s = fx["sangria"]
        sombras.append(f'0 0 {s.get("raio", "0.012em")} {s.get("cor", "currentColor")}')
    css.append('text-shadow:' + (','.join(sombras) if sombras else 'none'))
    if "pos" in camada:
        css.append(_pos_css(camada, 0, 0))
    return (
        f'<div id="{camada["id"]}"{decorativo} data-fit-mode="{fit["mode"]}" '
        f'data-fit-min="{fit.get("min", tam_ini)}" data-fit-max="{fit.get("max", tam_ini)}" '
        f'data-shrink-priority="{fit.get("shrink_priority",0)}" '
        f'data-max-lines="{fit.get("max_lines", 99)}" data-role="{camada.get("slot", "text")}" '
        f'data-weight="{peso}" style="{";".join(css)}">{html_runs(camada)}</div>'
    )

def html_rect(c: dict) -> str:
    fundo = c["fill"]
    if c.get("verniz"):
        # VERNIZ LOCALIZADO / HOT FOIL: a luz varre a superfície metálica num
        # ângulo. Gradiente sobre a chapa, não em cima do texto (texto com
        # gradiente é proibido: decorativo sem significado).
        v = c["verniz"]
        fundo = (f'linear-gradient({v.get("angulo", 104)}deg, '
                 f'{v.get("borda", "rgba(255,255,255,0)")} 0%, '
                 f'{v.get("brilho", "rgba(255,255,255,.55)")} {v.get("pico", 38)}%, '
                 f'{v.get("borda", "rgba(255,255,255,0)")} 62%), {fundo}')
    css = [f'width:{c["w"]}px', f'height:{c["h"]}px', f'background:{fundo}',
           f'border-radius:{c.get("radius", 0)}px', f'opacity:{c.get("opacity", 1)}']
    if "pos" in c:
        css.append(_pos_css(c, 0, 0))
    return f'<div id="{c["id"]}" data-mask style="{";".join(css)}"></div>'

def html_dots(c: dict) -> str:
    pontos = []
    for i in range(c["total"]):
        cor = c["cor_ativa"] if i == c["atual"] else c["cor_inativa"]
        pontos.append(f'<div style="width:{c["size"]}px;height:{c["size"]}px;'
                      f'border-radius:50%;background:{cor}"></div>')
    css = [f'display:flex;gap:{c["gap"]}px;align-items:center']
    if "pos" in c:
        css.append(_pos_css(c, 0, 0))
    return f'<div id="{c["id"]}" data-mask style="{";".join(css)}">{"".join(pontos)}</div>'

def html_layer(c: dict, spec: dict) -> str:
    t = c["type"]
    if t == "image":
        asset = next(a for a in spec["assets"] if a["id"] == c["asset"])
        uri = data_uri(AQUI / asset["file"], "image/png")
        filtro = f'filter:{c["filtro"]};' if c.get("filtro") else ""
        return (f'<img id="{c["id"]}" data-mask src="{uri}" style="position:absolute;inset:0;'
                f'width:100%;height:100%;object-fit:cover;{filtro}'
                f'object-position:{c.get("object_position", "center")};" />')
    if t == "scrim":
        # ⚠️ `box` só significa região LOCAL quando tem medida em px. O acervo
        # declara scrim de tela cheia como `{"x":0,"y":0,"w":"100%","h":"100%"}`
        # desde `7b80a70`, e o render antigo simplesmente ignorava o box e
        # pintava `inset:0`. Exigir `fill_local` também nesse caso derrubou
        # `spec_news.json` — a única spec do acervo com scrim+box — com
        # "scrim local não resolvido", exit 1, zero PNG. Fail-closed, mas é peça
        # fora do ar sem ninguém ter pedido, e `varredura.sh` varre `spec_*.json`.
        #
        # E a porcentagem não sobreviveria à interpolação de qualquer jeito:
        # `width:{b["w"]}px` com `w="100%"` emite `width:100%px`, que o CSS
        # descarta em silêncio.
        caixa = c.get("box") or {}
        local = any(isinstance(caixa.get(eixo), (int, float))
                    for eixo in ("w", "h"))
        if local:
            if 'fill_local' not in c: err('scrim local não resolvido')
            b=c['box']; fill=c['fill_local']; feather=c.get('feather',0)
            return (f'<div id="{c["id"]}" data-scrim data-mask style="position:absolute;'
                    f'left:{b["x"]}px;top:{b["y"]}px;width:{b["w"]}px;height:{b["h"]}px;'
                    f'background:{fill};box-shadow:0 0 {feather}px {feather/2}px {fill};"></div>')
        return (f'<div id="{c["id"]}" data-scrim data-mask style="position:absolute;inset:0;'
                f'background:{css_gradient(c["style"]["gradient"])};"></div>')
    if t == "texture":
        # GRÃO DE FILME: emulsão, não ruído digital. Duas camadas de frequência
        # diferente (grão fino + estrutura) reproduzem a assinatura da película.
        piso, amp = c.get("piso"), c.get("amplitude", 1.0)
        fino = svg_ruido(seed=7, freq=0.90, octaves=1, tile=280, piso=piso, amplitude=amp)
        estr = svg_ruido(seed=13, freq=0.32, octaves=2, tile=420, piso=piso, amplitude=amp)
        op = c.get("opacity", 0.05)
        return (
            f'<div id="{c["id"]}" style="position:absolute;inset:0;pointer-events:none;'
            f"background-image:url('{fino}');background-size:{c.get('escala', 300)}px;"
            f'opacity:{op};mix-blend-mode:{c.get("blend", "overlay")};"></div>'
            f'<div id="{c["id"]}_estrutura" style="position:absolute;inset:0;'
            f"pointer-events:none;background-image:url('{estr}');background-size:640px;"
            f'opacity:{round(op * 0.55, 4)};mix-blend-mode:soft-light;"></div>')
    if t == "veu":
        # VÉU LOCALIZADO: densidade só onde o texto vive, com borda difusa que
        # dissolve na cena. Não é o fade global de rodapé — é o mínimo necessário
        # na zona que a análise elegeu, e só quando a análise diz que a foto não
        # oferece um lugar claramente bom.
        b, a = c["box"], c["alpha"]
        return (f'<div id="{c["id"]}" style="position:absolute;'
                f'left:{b["x"]}px;top:{b["y"]}px;width:{b["w"]}px;height:{b["h"]}px;'
                f'pointer-events:none;background:{c.get("cor", "rgba(6,5,12,1)")};'
                f'opacity:{a};'
                f'-webkit-mask-image:radial-gradient(ellipse 78% 74% at 42% 52%,'
                f'#000 38%, transparent 100%);'
                f'mask-image:radial-gradient(ellipse 78% 74% at 42% 52%,'
                f'#000 38%, transparent 100%);"></div>')
    if t == "tabela":
        # LEDGER / BIOMARCADOR: linhas rótulo→valor com régua pontilhada entre
        # eles. É a mesa de dados do editorial clínico — o `biomarker_ledger` do
        # engine HTML, agora declarado no contrato em vez de escrito à mão.
        est = c["style"]; fr, fv = est["font_rotulo"], est["font_valor"]
        linhas = []
        for i, ln in enumerate(c["linhas"]):
            destaque = ln.get("destaque")
            cor_v = est["cor_destaque"] if destaque else est["cor_valor"]
            linhas.append(
                f'<div style="display:flex;align-items:baseline;gap:14px;'
                f'padding:{c.get("padding_linha", "13px 0")};'
                f'border-bottom:1px {c.get("regra_estilo", "dotted")} {est["cor_regua"]};">'
                f'<span style="font-family:\'{fr["family"]}\';font-weight:{fr.get("weight",400)};'
                f'font-size:{c.get("tam_rotulo",26)}px;color:{est["cor_rotulo"]};'
                f'letter-spacing:{fr.get("tracking","normal")};'
                f'text-transform:{fr.get("transform","none")};white-space:nowrap;">{ln["rotulo"]}</span>'
                f'<span style="flex:1;border-bottom:1px dotted {est["cor_regua"]};'
                f'opacity:.5;transform:translateY(-4px);"></span>'
                f'<span style="font-family:\'{fv["family"]}\';font-weight:{fv.get("weight",700)};'
                f'font-size:{c.get("tam_valor",34)}px;color:{cor_v};white-space:nowrap;'
                f'font-variant-numeric:tabular-nums;">{ln["valor"]}</span></div>')
        css = [_pos_css(c, 0, 0), f'width:{c.get("w",888)}px']
        return f'<div id="{c["id"]}" data-mask style="{";".join(css)}">{"".join(linhas)}</div>'
    if t == "colunas":
        # DUAS COLUNAS: comparação lado a lado, com fio vertical no meio.
        est = c["style"]; ft, fc = est["font_titulo"], est["font_corpo"]
        cols = []
        for i, col in enumerate(c["colunas"]):
            borda = (f'border-left:1px solid {est["cor_fio"]};padding-left:{c.get("gap",34)}px;'
                     if i else "")
            vertical=c.get('orientacao')=='vertical'
            if vertical: borda=f'display:grid;grid-template-columns:auto 1fr;gap:{c.get("gap",16)}px;'
            if c.get('verificar'):
                titulo=html_texto(dict(id=f'{c["id"]}_{i}_titulo',runs=[{'text':col['titulo']}],
                    fit={'mode':'fixed','size':c.get('tam_titulo',25)},
                    style={'font':ft,'color':col.get('cor') or est['cor_titulo']}))
                corpo=html_texto(dict(id=f'{c["id"]}_{i}_corpo',runs=[{'text':col['texto']}],
                    fit={'mode':'fixed','size':c.get('tam_corpo',27)},
                    style={'font':fc,'color':est['cor_corpo']}))
                cols.append(f'<div style="flex:1;min-width:0;{borda}">{titulo}{corpo}</div>')
                continue
            cols.append(
                f'<div style="flex:1;{borda}">'
                f'<div style="font-family:\'{ft["family"]}\';font-weight:{ft.get("weight",700)};'
                f'font-size:{c.get("tam_titulo",25)}px;color:{col.get("cor") or est["cor_titulo"]};'
                f'letter-spacing:{ft.get("tracking","normal")};text-transform:{ft.get("transform","none")};'
                f'margin-bottom:12px;">{col["titulo"]}</div>'
                f'<div style="font-family:\'{fc["family"]}\';font-weight:{fc.get("weight",450)};'
                f'font-size:{c.get("tam_corpo",27)}px;line-height:{fc.get("line_height",1.4)};'
                f'color:{est["cor_corpo"]};">{col["texto"]}</div></div>')
        css = [_pos_css(c, 0, 0), f'width:{c.get("w",888)}px', "display:flex",
               f'gap:{c.get("gap",34)}px']
        if c.get('orientacao')=='vertical': css.append('flex-direction:column')
        if est.get('fill'):
            css.extend([f'background:{est["fill"]}',f'padding:{c.get("padding",0)}px','box-sizing:border-box'])
        return f'<div id="{c["id"]}" data-mask style="{";".join(css)}">{"".join(cols)}</div>'
    if t == "medidor":
        # MEDIDOR: barra com faixa segura e marcador na posição medida. O
        # `meter_monument` — dado que vira geometria, não número solto.
        est = c["style"]
        frac = max(0.0, min(1.0, c["valor_frac"]))
        zona = c.get("faixa_segura")
        marca_zona = ""
        if zona:
            marca_zona = (f'<div style="position:absolute;left:{zona[0]*100:.1f}%;'
                          f'width:{(zona[1]-zona[0])*100:.1f}%;top:0;bottom:0;'
                          f'background:{est["cor_faixa"]};opacity:.30;"></div>')
        css = [_pos_css(c, 0, 0), f'width:{c.get("w",888)}px']
        return (f'<div id="{c["id"]}" data-mask style="{";".join(css)}">'
                f'<div style="position:relative;height:{c.get("h",16)}px;'
                f'background:{est["cor_trilho"]};border-radius:{c.get("h",16)}px;'
                f'overflow:hidden;">{marca_zona}'
                f'<div style="position:absolute;left:0;top:0;bottom:0;width:{frac*100:.1f}%;'
                f'background:{est["cor_preenchido"]};"></div>'
                f'<div style="position:absolute;left:calc({frac*100:.1f}% - 2px);top:-6px;'
                f'bottom:-6px;width:4px;background:{est["cor_marcador"]};"></div></div></div>')
    if t == "grafico":
        # MOTOR DE GRÁFICOS: o dado vira geometria em Python (determinístico,
        # sem lib JS) e entra como SVG inline. O gráfico é CAMADA do contrato —
        # declarado, medido e reprovável como qualquer outra tinta.
        import graficos
        fn = graficos.GRAFICOS.get(c["kind"])
        if fn is None: err(f"gráfico desconhecido: {c['kind']}")
        args = {k: v for k, v in c.items() if k not in ("id","type","kind","pos","w","h")}
        if "w" in c: args["w"] = c["w"]
        if "h" in c: args["h"] = c["h"]
        svg = fn(**args)
        css = [_pos_css(c, 0, 0), "pointer-events:none"]
        return f'<div id="{c["id"]}" data-mask style="{";".join(css)}">{svg}</div>'
    if t == "vinheta":
        # QUEDA DE LUZ DE LENTE: escurecimento radial nos cantos. A objetiva faz
        # isso; o render digital plano não — por isso a ausência denuncia CGI.
        return (f'<div id="{c["id"]}" style="position:absolute;inset:0;'
                f'pointer-events:none;background:radial-gradient('
                f'ellipse {c.get("raio", "78% 68%")} at {c.get("centro", "50% 42%")},'
                f'transparent 0%, transparent 55%, {c["cor"]} 100%);'
                f'opacity:{c.get("opacity", 1)};"></div>')
    if t == "vazamento":
        # VAZAMENTO DE LUZ: fuga de luz na frestas do corpo da câmera. Sempre de
        # uma borda, sempre quente, sempre dissolvido em grão — nunca uma bolha
        # de mesh gradient centralizada (essa é a assinatura do design de IA).
        mascara = svg_ruido(seed=21, freq=0.55, octaves=3, tile=360, como_alpha=True)
        return (f'<div id="{c["id"]}" style="position:absolute;inset:0;'
                f'pointer-events:none;mix-blend-mode:screen;'
                f'opacity:{c.get("opacity", 0.18)};'
                f'background:radial-gradient(ellipse {c.get("raio", "60% 45%")} at '
                f'{c.get("origem", "8% -6%")}, {c["cor"]} 0%, transparent 70%);'
                f"-webkit-mask-image:url('{mascara}');-webkit-mask-size:520px;"
                f"mask-image:url('{mascara}');mask-size:520px;\"></div>")
    if t == "text":
        return html_texto(c)
    if t == "rect":
        return html_rect(c)
    if t == "dots":
        return html_dots(c)
    if t == "frame":
        lay = c.get("layout", {})
        modo = "row" if lay.get("mode") == "horizontal" else "column"
        zona = f' data-zona-h="{c["zona_h"]}"' if "zona_h" in c else ""
        css = [_pos_css(c, 0, 0), "display:flex", f"flex-direction:{modo}",
               f'gap:{lay.get("gap", 0)}px',
               f'align-items:{lay.get("align", "flex-start")}',
               f'justify-content:{lay.get("justify", "flex-start")}']
        est = c.get("style") or {}
        mask = ""
        if "fill" in est:  # frame como container pintado (chip, cartela)
            css += [f'background:{est["fill"]}', f'border-radius:{est.get("radius", 0)}px',
                    f'padding:{est.get("padding", "0")}']
            mask = " data-mask"  # o campo pintado é vizinho declarado, não tinta de texto
        filhos = "".join(html_layer(f, spec) for f in c["children"])
        return f'<div id="{c["id"]}"{mask}{zona} style="{";".join(css)}">{filhos}</div>'
    err(f"tipo de layer desconhecido: {t}")

def monta_html(slide: dict, spec: dict) -> str:
    base = spec["artboard"]["base"]
    W, H = base["w"], base["h"]
    faces = []
    for f in spec["fonts"]:
        uri = data_uri(AQUI / f["file"], "font/ttf")
        estilo = f.get("style", "normal")
        faixa = f.get("weight_range", str(f.get("weight", 400)))
        faces.append(f"@font-face {{ font-family:'{f['family']}'; src:url('{uri}') "
                     f"format('truetype'); font-weight:{faixa}; font-style:{estilo}; }}")
    fundo = slide.get("background", "#000")
    corpo = "".join(html_layer(c, spec) for c in slide["layers"])
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
            f'{"".join(faces)} * {{ margin:0; padding:0; box-sizing:border-box; }}'
            f'</style></head><body style="width:{W}px;height:{H}px;position:relative;'
            f'overflow:hidden;background:{fundo};">{filtros_svg()}{corpo}</body></html>')

FIT_E_VERIFY_JS = """
async (args) => {
  const safe = args.safe, fontes = args.fontes;
  for (const f of fontes) await document.fonts.load(`${f.peso} 20px '${f.familia}'`);
  await document.fonts.ready;
  const problemas = [];
  for (const f of fontes)
    if (!document.fonts.check(`${f.peso} 20px '${f.familia}'`))
      problemas.push(`fonte nao carregou: ${f.familia} ${f.peso}`);

  const linhas = (el) => {
    const span = el.querySelector('[data-conteudo]');
    const rects = [...span.getClientRects()];
    if (!rects.length) return 0;
    const tops = [];
    for (const r of rects) if (!tops.some(t => Math.abs(t - r.top) < 3)) tops.push(r.top);
    return tops.length;
  };
  const paraHex = (rgb) => {
    const m = rgb.match(/\\d+(\\.\\d+)?/g);
    return '#' + [0,1,2].map(i => Math.round(+m[i]).toString(16).padStart(2,'0')).join('');
  };

  // PASSADA 1 — resolver TODOS os fits. Nenhuma medição aqui: o fit de um
  // elemento muda a altura do bloco e reposiciona os vizinhos (frame ancorado
  // embaixo), então qualquer bbox lido agora nasce velho.
  const alvos = [...document.querySelectorAll('[data-verify]')];
  const tamanhos = {};
  for (const el of alvos) {
    const min = +el.dataset.fitMin, max = +el.dataset.fitMax,
          maxLinhas = +el.dataset.maxLines, modo = el.dataset.fitMode;
    if (modo !== 'auto') { tamanhos[el.id] = parseFloat(getComputedStyle(el).fontSize); continue; }
    let lo = min, hi = max;
    const cabe = (t) => { el.style.fontSize = t + 'px';
      return linhas(el) <= maxLinhas && el.scrollWidth <= el.clientWidth + 1; };
    if (!cabe(lo)) { problemas.push(`${el.id}: nao cabe nem no minimo ${lo}px (overflow=fail)`);
      tamanhos[el.id] = null; continue; }
    while (hi - lo > 0.5) { const m = (lo + hi) / 2; cabe(m) ? lo = m : hi = m; }
    tamanhos[el.id] = Math.floor(lo); el.style.fontSize = tamanhos[el.id] + 'px';
  }

  // PASSADA 1.5 — CONTENÇÃO NA ZONA. Achar a região certa não basta: o bloco
  // tem que CABER nela. O fit por elemento só garante largura e nº de linhas;
  // a altura do bloco inteiro é outra restrição, e sem ela o texto transborda
  // a zona medida e invade justamente o que a análise mandou preservar.
  for (const fr of document.querySelectorAll('[data-zona-h]')) {
    const maxH = +fr.dataset.zonaH;
    const flex = [...fr.querySelectorAll('[data-verify][data-fit-mode="auto"]')];
    let guarda = 0;
    while (fr.getBoundingClientRect().height > maxH && guarda++ < 80) {
      let mudou = false;
      const elegiveis = flex.filter(el => tamanhos[el.id] !== null && tamanhos[el.id] > +el.dataset.fitMin);
      const prioridade = Math.min(...elegiveis.map(el => +el.dataset.shrinkPriority));
      for (const el of elegiveis.filter(el => +el.dataset.shrinkPriority === prioridade)) {
        const min = +el.dataset.fitMin, atual = tamanhos[el.id];
        if (atual !== null && atual > min) {
          tamanhos[el.id] = Math.max(min, atual - 2);
          el.style.fontSize = tamanhos[el.id] + 'px';
          mudou = true;
        }
      }
      if (!mudou) break;
    }
    const sobra = fr.getBoundingClientRect().height - maxH;
    if (sobra > 1)
      problemas.push(`${fr.id}: bloco não cabe na zona medida (${Math.ceil(sobra)}px a mais mesmo no corpo mínimo)`);
  }

  // PASSADA 2 — layout estabilizado: agora sim medir e julgar.
  const evidencia = {};
  for (const el of alvos) {
    const maxLinhas = +el.dataset.maxLines, tam = tamanhos[el.id];
    if (tam === null) { evidencia[el.id] = { fit: 'FALHOU', linhas: linhas(el) }; continue; }
    const n = linhas(el);
    if (n > maxLinhas) problemas.push(`${el.id}: ${n} linhas > max ${maxLinhas}`);
    if (el.scrollWidth > el.clientWidth + 1) problemas.push(`${el.id}: clip horizontal`);
    const b = el.getBoundingClientRect();
    // SAFE AREA mede a TINTA, não a caixa: a caixa carrega o orçamento do efeito
    // (halo, respiro de serifa) e cresce de propósito. Quem não pode encostar na
    // borda é a letra. Já o clearance mede a caixa — halo precisa de espaço.
    const rt = [...el.querySelector('[data-conteudo]').getClientRects()];
    const tinta = rt.length ? {
      l: Math.min(...rt.map(r => r.left)), r: Math.max(...rt.map(r => r.right)),
      t: Math.min(...rt.map(r => r.top)), b: Math.max(...rt.map(r => r.bottom)) } : null;
    const W = document.body.clientWidth, H = document.body.clientHeight;
    if (tinta && (tinta.l < safe.left - 1 || tinta.r > W - safe.right + 1 ||
        tinta.t < safe.top - 1 || tinta.b > H - safe.bottom + 1))
      problemas.push(`${el.id}: tinta fora da safe area (${JSON.stringify(
        {l:tinta.l|0,r:tinta.r|0,t:tinta.t|0,b:tinta.b|0})})`);
    const cs = getComputedStyle(el);
    evidencia[el.id] = { font_size_px: tam, linhas: n,
      bbox: { x: b.left|0, y: b.top|0, w: b.width|0, h: b.height|0 },
      cor: paraHex(cs.color), peso: +el.dataset.weight, role: el.dataset.role,
      line_height: parseFloat(cs.lineHeight) / tam || 1.2 };
  }
  // EVIDÊNCIA POR RUN: um run com cor/tratamento próprio é uma unidade de
  // legibilidade independente. Medir só o nó deixa passar a palavra que sumiu —
  // o branco do resto da headline dilui a média e o gate aplaude um buraco.
  const runs = [];
  for (const el of alvos) {
    const cs0 = getComputedStyle(el);
    for (const sp of el.querySelectorAll('[data-trat],[data-accent],[data-dual]')) {
      const rs = [...sp.getClientRects()];
      if (!rs.length) continue;
      const x0 = Math.min(...rs.map(r => r.left)), x1 = Math.max(...rs.map(r => r.right));
      const y0 = Math.min(...rs.map(r => r.top)), y1 = Math.max(...rs.map(r => r.bottom));
      const cs = getComputedStyle(sp);
      runs.push({ id: el.id + '/' + (sp.dataset.trat !== undefined ? 'trat' :
                   sp.dataset.accent !== undefined ? 'accent' : 'dual') + ':' + runs.length,
        bbox: { x: x0|0, y: y0|0, w: Math.ceil(x1-x0), h: Math.ceil(y1-y0) },
        cor: paraHex(cs.color), peso: parseInt(cs.fontWeight) || 400,
        font_size_px: parseFloat(cs.fontSize) || parseFloat(cs0.fontSize),
        texto: sp.textContent.slice(0, 40) });
    }
  }

  // nós visíveis não-texto (réguas, dots, ghosts): declarados para o masking
  // de vizinhança do pixel gate — tinta deles não é overflow de ninguém
  // ATMOSFERA DECLARADA ENTRA NO MASCARAMENTO. A halação é aria-hidden e o
  // G-ATMOSFERA já verifica, por medida, que ela fica abaixo do piso de tinta —
  // é atmosfera, não letra. Sem declará-la aqui, o portão de pixel conta o mesmo
  // halo como transbordo da caixa do texto, e o motor passa a ter dois portões
  // com leituras opostas do mesmo pixel (é contra isso que existe a Lei 17).
  // TRANSBORDO DE ATMOSFERA, MEDIDO POR NÓ. `filter: blur(s)` é gaussiana e não
  // termina em s: o padding do efeito cobre o RAIO, não o alcance da tinta. Em
  // vez de arbitrar um múltiplo, mede-se o retângulo que a atmosfera de fato
  // ocupa e declara-se o quanto ela excede a caixa. O portão de pixel expande a
  // caixa planejada por esse valor — e assim ele e o G-ATMOSFERA passam a ler o
  // mesmo pixel do mesmo jeito.
  for (const el of document.querySelectorAll('[data-verify]')) {
    const atm = [...el.querySelectorAll('[aria-hidden="true"]')];
    if (!atm.length || !evidencia[el.id]) continue;
    // getBoundingClientRect NÃO inclui transbordo de filtro: devolve a caixa do
    // elemento, não a tinta que o blur espalha. O alcance vem da definição do
    // próprio filtro — `filter: blur(s)` é gaussiana de desvio s, efetivamente
    // nula além de 3s. Lê-se o s aplicado, e desconta-se o recuo que a caixa já
    // reserva. Derivado do que está desenhado, não arbitrado.
    const b = el.getBoundingClientRect();
    let sigma = 0, recuo = Infinity;
    for (const a of atm) {
      const m = /blur[(]([0-9.]+)px[)]/.exec(getComputedStyle(a).filter || '');
      if (m) sigma = Math.max(sigma, parseFloat(m[1]));
      const q = a.getBoundingClientRect();
      // o recuo que importa é o do filho MAIS ALTO: é dele que o blur sobe.
      // Tomar o máximo pegava o span da linha do acento, centenas de px abaixo,
      // e zerava o transbordo justamente onde ele existe.
      if (q.height > 0) recuo = Math.min(recuo, q.top - b.top);
    }
    if (!sigma || !isFinite(recuo)) continue;
    const fora = Math.ceil(Math.max(0, 3 * sigma - recuo));
    evidencia[el.id].atm_outset = { l: fora, t: fora, r: fora, b: fora,
                                    sigma: sigma, recuo: Math.round(recuo) };
  }

  const extras = [];
  for (const el of document.querySelectorAll('[data-mask], [aria-hidden="true"]')) {
    if (el.tagName.toLowerCase() === 'svg' && !el.hasAttribute('data-mask')) continue;
    const b = el.getBoundingClientRect();
    if (b.width > 0 && b.height > 0)
      extras.push({ id: el.id || ('atm_' + extras.length),
                    bbox: { x: b.left|0, y: b.top|0, w: Math.ceil(b.width), h: Math.ceil(b.height) } });
  }

  // MODO EXPLORAÇÃO: prancha de estudo, não peça publicável. Resolve o fit e
  // renderiza, mas não julga composição. Nunca deve alimentar publicação.
  if (args.exploracao) return { ok: true, problemas: [], evidencia, extras: [] };

  // GATE DE COLISÃO — dois textos legíveis nunca se sobrepõem, e um numeral
  // decorativo mantém clearance do texto (ghost é fundo, não vizinho de letra).
  const caixas = [...document.querySelectorAll('[data-verify]')].map(el => {
    const b = el.getBoundingClientRect();
    // caixa da TINTA, não do line-box: o line-box de display tem folga vertical
    // que geraria falso positivo entre blocos empilhados
    const rects = [...el.querySelector('[data-conteudo]').getClientRects()];
    const x0 = Math.min(...rects.map(r => r.left)), x1 = Math.max(...rects.map(r => r.right));
    const y0 = Math.min(...rects.map(r => r.top)), y1 = Math.max(...rects.map(r => r.bottom));
    return { id: el.id, x0, y0, x1, y1 };
  });
  for (let i = 0; i < caixas.length; i++)
    for (let j = i + 1; j < caixas.length; j++) {
      const a = caixas[i], b = caixas[j];
      const ov = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0);
      const oy = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
      if (ov > 2 && oy > 2) problemas.push(`colisão de texto: ${a.id} × ${b.id} (${ov|0}×${oy|0}px)`);
    }
  for (const el of document.querySelectorAll('[data-decorative]')) {
    const rects = [...el.querySelector('[data-conteudo]').getClientRects()];
    if (!rects.length) continue;
    const d = { x0: Math.min(...rects.map(r => r.left)), x1: Math.max(...rects.map(r => r.right)),
                y0: Math.min(...rects.map(r => r.top)), y1: Math.max(...rects.map(r => r.bottom)) };
    for (const c of caixas) {
      const ov = Math.min(d.x1, c.x1) - Math.max(d.x0, c.x0) + args.clearance;
      const oy = Math.min(d.y1, c.y1) - Math.max(d.y0, c.y0) + args.clearance;
      if (ov > 0 && oy > 0)
        problemas.push(`clearance: decorativo ${el.id} invade ${c.id} (falta ${Math.ceil(Math.min(ov, oy))}px)`);
    }
  }
  return { ok: problemas.length === 0, problemas, evidencia, extras };
}
"""

def render_slide(page, slide, spec, safe, fontes_js, saida_png: Path,
                 clearance: int = 24, exploracao: bool = False, posicoes: dict | None = None):
    page.set_content(monta_html(slide, spec), wait_until="load")
    veredito = page.evaluate(FIT_E_VERIFY_JS,
                             {"safe": safe, "fontes": fontes_js, "clearance": clearance,
                              "exploracao": exploracao})
    if posicoes:
        # POSIÇÃO RESOLVIDA — aplica o que o solver decidiu e RE-MEDE. A segunda
        # medição é a autoridade: se a peça se mexeu ao ser reposicionada (fit
        # que muda de linha, sombra que reflui), o veredito reprova. O solver
        # propõe; o Chromium confirma. Nunca itera.
        # POSIÇÃO POR DESLOCAMENTO, NUNCA POR COORDENADA ABSOLUTA.
        # A excursão foi medida contra o retângulo ENVOLVENTE, e a halação é um
        # filho absoluto e desfocado que transborda a caixa: o envolvente fica
        # 26px acima da caixa CSS na headline com acento. Escrever `top` com uma
        # excursão medida no envolvente mistura duas origens e desloca o bloco
        # pelo raio do halo. O deslocamento é diferencial — "mova esta tinta
        # tantos px" — e por isso é imune a halo, sombra, blur ou qualquer coisa
        # que faça caixa e envolvente divergirem.
        # `ink_off` é a distância medida entre o `top` CSS e a tinta, com o bloco
        # estacionado em posição conhecida — invariante por translação. A emissão
        # é uma subtração, sem depender de offsetTop (que carrega margem), de
        # getBoundingClientRect (que carrega o transbordo do halo) nem do estado
        # em que o bloco por acaso nasceu.
        page.evaluate("""(pos)=>{ for (const [id, a] of Object.entries(pos)) {
            const e = document.getElementById(id);
            if (!e || a.ink_topo == null || a.ink_off == null) continue;
            e.style.top = (a.ink_topo - a.ink_off) + 'px';
            e.style.bottom = 'auto'; } }""", posicoes)
        veredito = page.evaluate(FIT_E_VERIFY_JS,
                                 {"safe": safe, "fontes": fontes_js, "clearance": clearance,
                                  "exploracao": exploracao})
        veredito["composicao_aplicada"] = posicoes
    if not veredito["ok"]:
        print(json.dumps(veredito["problemas"], indent=2, ensure_ascii=False))
        return veredito, False
    base = spec["artboard"]["base"]
    page.screenshot(path=str(saida_png),
                    clip={"x": 0, "y": 0, "width": base["w"], "height": base["h"]})
    return veredito, True

def main() -> None:
    if len(sys.argv) < 2:
        err("uso: render.py out/<spec>.resolvido.json [--sufixo _x]")
    spec = json.loads((AQUI / sys.argv[1]).read_text())
    sufixo = sys.argv[sys.argv.index("--sufixo") + 1] if "--sufixo" in sys.argv else ""
    base = spec["artboard"]["base"]
    safe = spec["artboard"]["safe_area"]
    fontes_js = [{"familia": f["family"], "peso": f.get("weight", 400)} for f in spec["fonts"]]
    slides = spec.get("slides") or [{"id": "s1", "background": spec.get("background", "#000"),
                                     "layers": spec["layers"]}]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=[
            "--disable-gpu", "--force-color-profile=srgb",
            "--font-render-hinting=none", "--disable-lcd-text", "--hide-scrollbars"])
        page = browser.new_page(viewport={"width": base["w"], "height": base["h"]},
                                device_scale_factor=1)
        # PASSADA DE COMPOSIÇÃO — só existe quando alguém declara `composicao`.
        # Sem declaração o caminho é bit a bit o de sempre: nenhuma medida extra,
        # nenhum screenshot extra, nenhum PNG diferente. É a única forma de a
        # migração ser faseada sem que o parque inteiro precise ser revalidado
        # no mesmo commit.
        geridas = [s for s in slides if s.get("composicao")]
        posicoes_por_slide = {}
        if geridas:
            import medida, costura
            print(f"   composição: {len(geridas)}/{len(slides)} lâmina(s) gerida(s) — "
                  f"medindo a classe inteira antes de emitir")
            fxp = AQUI / "out" / "faixa_elastica.json"
            fx = json.loads(fxp.read_text()) if fxp.exists() else {}
            laminas = []
            for sl in geridas:
                pilha_ids = [b["ref"] for b in sl["composicao"]["pilha"]]
                ms = medida.mede_slide(page, sl, spec, fontes_js, parque=pilha_ids)
                flex = next((b["ref"] for b in sl["composicao"]["pilha"] if b.get("flex")), None)
                kind = next((c["kind"] for c in sl["layers"]
                             if c.get("id") == flex and c.get("type") == "grafico"), None)
                laminas.append({"id": sl["id"], "decl": sl["composicao"],
                                "L": (ms.get("L_headline") or 0),
                                "faixa_forma": ({flex: fx[kind]["faixa_span"]}
                                                if kind and kind in fx else {}),
                                "blocos": {k: {"ink_topo": v["topo"], "ink_base": v["base"],
                                               "ink_off": v.get("ink_off"),
                                               "exc_topo": v.get("exc_topo"),
                                               "exc_base": v.get("exc_base")}
                                           for k, v in ms["blocos"].items()
                                           if v.get("topo") is not None}})
            r = costura.resolve_classe(laminas, spec.get("skin_tokens") or {})
            posicoes_por_slide = {x["slide"]: x["posicoes"] for x in r["laminas"]}
            # SEGUNDA RESOLUÇÃO, com o flexível já medido na altura emitida.
            r = costura.resolve_classe(laminas, spec.get("skin_tokens") or {})
            posicoes_por_slide = {x["slide"]: x["posicoes"] for x in r["laminas"]}

            # a tinta MEDIDA de cada bloco viaja junto: é o outro lado do
            # deslocamento diferencial aplicado na hora de emitir
            for lam in laminas:
                for bid, p in posicoes_por_slide.get(lam["id"], {}).items():
                    p["ink_off"] = lam["blocos"][bid].get("ink_off")
            print(f"   módulo M = {r['modulo_px']}px ({r['modulo_origem']})")

            # ALTURA DO FLEXÍVEL — o solver decidiu o SPAN de tinta; a altura de
            # caixa que o produz sai por bissecção sobre medida real, porque
            # span(h) não é afim para todo gerador. Resolvida aqui, a camada é
            # reescrita ANTES do render final: a peça sai com a altura resolvida,
            # e a PASSADA 2 re-mede o que de fato foi pintado.
            import elastico
            alturas = {}
            for sl in geridas:
                for cam in sl["layers"]:
                    alvo = (posicoes_por_slide.get(sl["id"]) or {}).get(cam.get("id"), {})
                    if cam.get("type") != "grafico" or "span_alvo" not in alvo:
                        continue
                    par = {k: v for k, v in cam.items()
                           if k not in ("id", "type", "kind", "pos", "w", "h")}
                    faixa = tuple(fx.get(cam["kind"], {}).get("faixa_h", [260, 620]))
                    res = elastico.resolve_h(page, cam["kind"], par,
                                             alvo["span_alvo"], faixa)
                    cam["h"] = res["h"]
                    alturas[(sl["id"], cam["id"])] = res["h"]
                    alvo["h_resolvido"] = res["h"]
                    alvo["span_medido"] = res["span"]
                    # o flexível deixa de ser flexível: passa a ser um bloco de
                    # altura e excursão MEDIDAS na altura resolvida. Não é
                    # iteração — o span já foi decidido, e resolver a posição uma
                    # vez com o valor real é mais exato que resolvê-la com o alvo.
                    lam = next(l for l in laminas if l["id"] == sl["id"])
                    b = lam["blocos"][cam["id"]]
                    b["ink_base"] = b["ink_topo"] + res["span"]
                    if res.get("ink_off") is not None:
                        b["ink_off"] = res["ink_off"]
                    lam["faixa_forma"] = {cam["id"]: [res["span"], res["span"]]}
                    print(f"   {sl['id']}/{cam['id']}: span alvo {alvo['span_alvo']} → "
                          f"h={res['h']} (span medido {res['span']}"
                          + (", SATURADO" if res.get("saturado") else
                             f", erro {res.get('erro_px')}px") + ")")

            # SEGUNDA RESOLUÇÃO — agora o flexível não é mais flexível: é um
            # bloco de altura e excursão MEDIDAS na altura que será emitida. Não
            # é iteração (o span já está decidido e imobilizado): é resolver a
            # posição uma única vez com o número real em vez do alvo.
            r = costura.resolve_classe(laminas, spec.get("skin_tokens") or {})
            posicoes_por_slide = {x["slide"]: x["posicoes"] for x in r["laminas"]}
            for lam in laminas:
                for bid, pp in posicoes_por_slide.get(lam["id"], {}).items():
                    pp["ink_off"] = lam["blocos"][bid].get("ink_off")
                    # a altura emitida viaja no veredito: sem ela, quem for
                    # auditar a peça depois re-renderiza o gráfico na altura
                    # padrão e mede outra peça (aconteceu comigo duas vezes)
                    hr = alturas.get((lam["id"], bid))
                    if hr: pp["h_resolvido"] = hr
            print(f"   módulo M = {r['modulo_px']}px ({r['modulo_origem']})")

        falhas = 0
        for i, slide in enumerate(slides, 1):
            nome = f"{spec['spec_id']}{sufixo}_s{i:02d}" if len(slides) > 1 else f"{spec['spec_id']}{sufixo}"
            png = AQUI / "out" / f"{nome}.png"
            veredito, ok = render_slide(page, slide, spec, safe, fontes_js, png,
                                        spec["gates"].get("clearance_decorativo_px", 24),
                                        spec["gates"].get("modo_exploracao", False),
                                        posicoes_por_slide.get(slide["id"]))
            (AQUI / "out" / f"{nome}.veredito.json").write_text(
                json.dumps(veredito, indent=2, ensure_ascii=False))
            if ok:
                sha = hashlib.sha256(png.read_bytes()).hexdigest()
                print(f"✅ {nome}.png · sha256 {sha[:16]}…")
            else:
                falhas += 1
                print(f"❌ {nome}: verify REPROVOU — nenhum PNG escrito (fail-closed)")
        browser.close()
    if falhas:
        err(f"{falhas} slide(s) reprovado(s)")

if __name__ == "__main__":
    main()
