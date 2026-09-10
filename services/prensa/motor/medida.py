#!/usr/bin/env python3
"""ETAPA 0 do COSTURA — o INSTRUMENTO. Mede a tinta real de cada bloco.

Por que existe: o motor posiciona por caixa, e a caixa mente. Medido neste lote,
a caixa do gráfico excede a tinta de +10px (multi) a +190px (mostrador) — e foi
essa mentira que fez parecer que havia sobreposição onde não há. Quem quer
posição resolvida por medida precisa antes de um instrumento que devolva a
fronteira da TINTA, não a do invólucro.

A fronteira não é arbitrada, e a origem dela precisa ser dita com precisão —
a primeira versão deste módulo dizia a coisa errada. O piso NÃO vem de
graficos.PAPEL: aquela tabela responde "esta cor cumpre o papel que declarou?",
e não tem jurisdição sobre "há marca neste pixel?". São duas perguntas, e a
segunda precisa da sua própria derivação.

Ela tem: WCAG 1.4.11, pela cláusula de IDENTIFICABILIDADE — 3:1 é a razão em que
um objeto gráfico se torna identificável como objeto distinto contra o que o
cerca. É literalmente a pergunta da composição, pixel a pixel. Não é empréstimo
do piso de argumento: é identidade de pergunta, na mesma norma de onde o motor
já importa a matemática de luminância (Lei 17).

O número NÃO é calibrado. Varredura fina mostra que [3.04, 3.16] daria uma
fronteira melhor (33 de 34 em 0px contra 32 de 34), e ficamos em 3.0 de
propósito: um número derivado não se troca por um número melhor ajustado a UMA
peça. A recusa fica registrada para ser citável quando a proposta voltar.

Método:
  · CHÃO   = as camadas de atmosfera (imagem, scrim, textura, véu, vinheta,
             vazamento). Uma chapa com todo o CONTEÚDO oculto.
  · BLOCO  = uma chapa por bloco, só ele visível.
  · Oculta-se por `visibility`, nunca por `display:none`: visibility preserva o
    layout byte a byte, então nenhuma medida nasce de uma página que se mexeu.
  · ESTABILIDADE: repete a fronteira em [0.8·piso, piso, 1.2·piso]. Se topo ou
    base andarem, o instrumento está medindo convenção e não tinta — e diz isso.

Uso: medida.py out/<spec>.resolvido.json [--json saida.json]
"""
from __future__ import annotations
import io, json, sys
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI))
import render as R
from gate_traco import PISO

# Atmosfera: pinta o papel, nunca carrega argumento. Não é bloco de composição.
CHAO = {"image", "scrim", "texture", "veu", "vinheta", "vazamento"}
PISO_TINTA = PISO["argumento"]          # 3.0 — WCAG 1.4.11, o piso que já cobramos
FATORES = (0.8, 1.0, 1.2)               # varredura de estabilidade
MIN_PX_LINHA = 2                        # 1px isolado é anti-aliasing, não linha

_LIN = np.array([((c / 255) / 12.92 if c / 255 <= 0.03928
                  else (((c / 255) + 0.055) / 1.055) ** 2.4) for c in range(256)])

_VISIBILIDADE_JS = """(a) => {
  for (const id of a.todos) {
    const el = document.getElementById(id);
    if (el) el.style.visibility = (id === a.mostrar) ? 'visible' : 'hidden';
  }
}"""


def _lum(arr: np.ndarray) -> np.ndarray:
    """Luminância relativa WCAG: lineariza POR CANAL antes de ponderar.
    (Lei 17 — uma só matemática de luminância no parque inteiro.)"""
    l = _LIN[arr]
    return 0.2126 * l[..., 0] + 0.7152 * l[..., 1] + 0.0722 * l[..., 2]


def _chapa(page, base) -> np.ndarray:
    png = page.screenshot(clip={"x": 0, "y": 0, "width": base["w"], "height": base["h"]})
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.uint8)


def _fronteira(lum_b: np.ndarray, lum_chao: np.ndarray, piso: float):
    """Primeira e última linha em que o bloco alcança o piso contra o chão local."""
    a = np.maximum(lum_b, lum_chao); b = np.minimum(lum_b, lum_chao)
    tinta = ((a + 0.05) / (b + 0.05)) >= piso
    linhas = np.flatnonzero(tinta.sum(axis=1) >= MIN_PX_LINHA)
    if not linhas.size:
        return None
    cols = np.flatnonzero(tinta.sum(axis=0) >= MIN_PX_LINHA)
    tem = tinta.any(axis=0)
    idx = np.arange(tinta.shape[0])[:, None]
    p_topo = np.where(tem, np.where(tinta, idx, tinta.shape[0]).min(axis=0), -1)
    p_base = np.where(tem, np.where(tinta, idx, -1).max(axis=0) + 1, -1)
    return {"topo": int(linhas[0]), "base": int(linhas[-1] + 1),
            "esq": int(cols[0]) if cols.size else None,
            "dir": int(cols[-1] + 1) if cols.size else None,
            "px": int(tinta.sum()),
            "perfil_topo": p_topo.astype(int).tolist(),
            "perfil_base": p_base.astype(int).tolist()}


PARQUE_Y = 200   # posição de estacionamento: qualquer y que não recorte

def mede_slide(page, slide: dict, spec: dict, fontes_js: list,
               parque: list[str] | None = None, aplicar: dict | None = None) -> dict:
    """`parque` estaciona blocos geridos antes de medir (medida de referência).
    `aplicar` mede a peça JÁ COMPOSTA — é o único jeito honesto de conferir o
    que o solver produziu, porque set_content descarta qualquer posição que
    tenha sido escrita na página antes da chamada."""
    base = spec["artboard"]["base"]
    page.set_content(R.monta_html(slide, spec), wait_until="load")
    # PASSADA 1 do motor: o fit precisa estar resolvido antes de qualquer medida,
    # senão mede-se um corpo que ainda vai mudar. O veredito pode reprovar — a
    # medida do instrumento não depende do julgamento.
    veredito = page.evaluate(R.FIT_E_VERIFY_JS, {
        "safe": spec["artboard"]["safe_area"], "fontes": fontes_js,
        "clearance": spec["gates"].get("clearance_decorativo_px", 24),
        "exploracao": False})

    conteudo = [c["id"] for c in slide["layers"] if c.get("type") not in CHAO]
    args = {"todos": conteudo, "mostrar": None}

    # HALAÇÃO FORA DA SILHUETA. O halo é atmosfera pendurada no próprio bloco:
    # sem suprimi-lo, a fronteira do bloco cresce pelo brilho e não pela letra.
    # Medido, o teto do halo puro é 2.7835:1 contra o piso de 3.0 — margem de
    # 7,2%. Hoje o piso segura a peça por 0.2165 de razão, o que é fino demais
    # para depender de sorte: sobe um pouco a opacidade de uma passada e o halo
    # vira massa. Suprime-se por `visibility`, igual ao CHÃO, e o G-ATMOSFERA
    # transforma a exclusão em AFIRMAÇÃO VERIFICADA em vez de efeito colateral
    # de um atributo CSS.
    n_atm = page.evaluate("""()=>{let n=0;
        for (const e of document.querySelectorAll('[aria-hidden="true"]')) {
          if (e.tagName.toLowerCase()==='svg') continue;   // defs, não pinta
          e.style.visibility='hidden'; n++; }
        return n;}""")

    page.evaluate(_VISIBILIDADE_JS, args)          # tudo oculto → o papel
    lum_chao = _lum(_chapa(page, base))

    # ESTACIONAMENTO. Um bloco cujo `pos.y` foi entregue ao solver nasce sem
    # posição e cai onde o CSS o deixar — medido, a headline nasce em offsetTop
    # -26, com tinta começando em -12, FORA do artboard. A chapa recorta no
    # artboard, então a fronteira medida seria a primeira linha VISÍVEL e não o
    # topo real: um deslocamento calculado sobre ela erra pelo tanto que foi
    # cortado. Antes de medir, cada bloco gerido é estacionado num y conhecido.
    # O que se extrai daí é `ink_off` — a distância entre o `top` CSS e a tinta —
    # que é invariante por translação e é exatamente a ponte que a emissão usa.
    if aplicar:
        page.evaluate("""(pos)=>{ for (const [id, a] of Object.entries(pos)) {
            const e = document.getElementById(id);
            if (!e || a.ink_topo == null || a.ink_off == null) continue;
            e.style.top = (a.ink_topo - a.ink_off) + 'px';
            e.style.bottom = 'auto'; } }""", aplicar)

    estacionado = {}
    if parque:
        estacionado = page.evaluate("""(a)=>Object.fromEntries(a.ids.map(id=>{
            const e=document.getElementById(id); if(!e) return [id,null];
            e.style.top=a.y+'px'; e.style.bottom='auto'; return [id,a.y];}))""",
            {"ids": parque, "y": PARQUE_Y})

    # EXCURSÃO: o CSS posiciona a CAIXA, o olho lê a TINTA. Entre as duas há uma
    # distância que varia por bloco (ascendente da fonte, margem interna do SVG,
    # halo de tratamento). O solver resolve posição de tinta; para escrever o y
    # ele precisa saber quanto subtrair. Medida aqui, nunca presumida.
    caixas = page.evaluate("""(ids)=>Object.fromEntries(ids.map(id=>{
        const e=document.getElementById(id); if(!e) return [id,null];
        const r=e.getBoundingClientRect();
        return [id,{topo:Math.round(r.top),base:Math.round(r.bottom)}];}))""", conteudo)

    blocos = {}
    for bid in conteudo:
        page.evaluate(_VISIBILIDADE_JS, {**args, "mostrar": bid})
        lum_b = _lum(_chapa(page, base))
        por_piso = {f: _fronteira(lum_b, lum_chao, PISO_TINTA * f) for f in FATORES}
        base_med = por_piso[1.0]
        if base_med is None:
            blocos[bid] = {"tinta": None, "motivo": "nenhuma tinta acima do piso"}
            continue
        vistos = [v for v in por_piso.values() if v]
        amp = max(max(abs(v["topo"] - base_med["topo"]),
                      abs(v["base"] - base_med["base"])) for v in vistos)
        cx = caixas.get(bid) or {}
        est = estacionado.get(bid)
        blocos[bid] = {**base_med, "ambiguidade_px": int(amp),
                       "estacionado_y": est,
                       "ink_off": (base_med["topo"] - est) if est is not None else None,
                       "instavel": len(vistos) < len(FATORES),
                       "caixa": cx,
                       "exc_topo": (base_med["topo"] - cx["topo"]) if cx else None,
                       "exc_base": (cx["base"] - base_med["base"]) if cx else None}

    # G-CLIP, a medida: o SVG recorta no próprio viewport por padrão, então tinta
    # que sai da caixa some sem deixar rastro — foi assim que o mostrador amputou
    # 52px em toda altura durante toda a vida do módulo, com os três portões
    # aprovando. Mede-se de novo com overflow:visible: o que aparecer a mais é
    # exatamente o que estava sendo cortado.
    for c in slide["layers"]:
        if c.get("type") != "grafico" or c["id"] not in blocos: continue
        b = blocos[c["id"]]
        if b.get("topo") is None: continue
        page.evaluate("""(id)=>{const e=document.getElementById(id);
            if(!e) return; e.style.overflow='visible';
            const s=e.querySelector('svg'); if(s) s.style.overflow='visible';}""", c["id"])
        page.evaluate(_VISIBILIDADE_JS, {**args, "mostrar": c["id"]})
        livre = _fronteira(_lum(_chapa(page, base)), lum_chao, PISO_TINTA)
        page.evaluate("""(id)=>{const e=document.getElementById(id);
            if(!e) return; e.style.overflow='';
            const s=e.querySelector('svg'); if(s) s.style.overflow='';}""", c["id"])
        if livre:
            # amputação nos DOIS eixos: a versão anterior media só o vertical,
            # com esq/dir já calculados e ignorados — e a trajetória vaza 19px
            # PELO LADO, que o G-CLIP aprovava sem ver.
            av = max(0, b["topo"] - livre["topo"]) + max(0, livre["base"] - b["base"])
            ah = 0
            if None not in (b.get("esq"), b.get("dir"), livre.get("esq"), livre.get("dir")):
                ah = max(0, b["esq"] - livre["esq"]) + max(0, livre["dir"] - b["dir"])
            b["amputado_px"] = av + ah
            b["amputado_v"], b["amputado_h"] = av, ah
            b["tinta_livre"] = {k: livre[k] for k in ("topo", "base", "esq", "dir")}

    # G-ATMOSFERA: a maior razão que a tinta SUPRIMIDA alcança contra o papel.
    # Se ela atinge o piso, aquilo não é atmosfera — é massa com rótulo errado,
    # e foi excluída da silhueta por engano.
    atm = 1.0
    if n_atm:
        page.evaluate(_VISIBILIDADE_JS, {**args, "mostrar": None})
        page.evaluate("""()=>{for (const e of document.querySelectorAll('[aria-hidden=\"true\"]'))
            if (e.tagName.toLowerCase()!=='svg') e.style.visibility='visible';}""")
        lum_atm = _lum(_chapa(page, base))
        a = np.maximum(lum_atm, lum_chao); b = np.minimum(lum_atm, lum_chao)
        atm = float(((a + 0.05) / (b + 0.05)).max())

    page.evaluate(_VISIBILIDADE_JS, {**args, "mostrar": "__todos__"})
    page.evaluate("""()=>{for (const e of document.querySelectorAll('[aria-hidden="true"]'))
        e.style.visibility='';}""")
    for bid in conteudo:                            # restaura
        page.evaluate("(id)=>{const e=document.getElementById(id); if(e) e.style.visibility='';}", bid)

    ordem = sorted((b for b in blocos.values() if b.get("topo") is not None),
                   key=lambda b: b["topo"])
    alvo = next((c["id"] for c in slide["layers"] if c.get("slot") == "headline"), None)
    hev = (veredito.get("evidencia") or {}).get(alvo or "", {})
    L = (hev.get("font_size_px") or 0) * (hev.get("line_height") or 1.2)

    return {"slide": slide["id"], "piso_tinta": PISO_TINTA, "blocos": blocos,
            "L_headline": round(L, 2), "headline_id": alvo,
            "atmosfera": {"nos_suprimidos": n_atm, "razao_max": round(atm, 4),
                          "margem": round(PISO_TINTA - atm, 4),
                          "ok": atm < PISO_TINTA},
            "ambiguidade_max_px": max((b.get("ambiguidade_px", 0) for b in blocos.values()),
                                      default=0),
            "veredito_ok": veredito.get("ok", False),
            "n_blocos_com_tinta": len(ordem)}


def mede(spec_path: Path) -> dict:
    spec = json.loads(spec_path.read_text())
    base = spec["artboard"]["base"]
    fontes_js = [{"familia": f["family"], "peso": f.get("weight", 400)} for f in spec["fonts"]]
    slides = spec.get("slides") or [{"id": spec["spec_id"],
                                     "background": spec.get("background", "#000"),
                                     "layers": spec["layers"]}]
    fora = []
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True, args=[
            "--disable-gpu", "--force-color-profile=srgb",
            "--font-render-hinting=none", "--disable-lcd-text", "--hide-scrollbars"])
        page = br.new_page(viewport={"width": base["w"], "height": base["h"]},
                           device_scale_factor=1)
        for sl in slides:
            fora.append(mede_slide(page, sl, spec, fontes_js))
        br.close()
    return {"spec": spec_path.name, "piso_tinta": PISO_TINTA,
            "safe": spec["artboard"]["safe_area"], "canvas": base, "slides": fora}


def vao_entre(a: dict, b: dict):
    """Menor distância vertical entre duas FORMAS de tinta, coluna a coluna.
    Devolve None quando as formas não se enfrentam em coluna nenhuma — aí não
    existe vão vertical a medir, e não existe colisão possível."""
    pa, pb = a.get("perfil_base"), b.get("perfil_topo")
    if not pa or not pb:                       # sem perfil: cai na caixa
        if None in (a.get("esq"), a.get("dir"), b.get("esq"), b.get("dir")): return None
        if min(a["dir"], b["dir"]) - max(a["esq"], b["esq"]) <= 0: return None
        return b["topo"] - a["base"]
    vaos = [pb[x] - pa[x] for x in range(min(len(pa), len(pb)))
            if pa[x] >= 0 and pb[x] >= 0]
    return min(vaos) if vaos else None


def banda_entre(a: dict, b: dict):
    """A FAIXA horizontal vazia entre dois blocos: da última linha de tinta de um
    até a primeira do outro. É outra pergunta que `vao_entre`, e confundi-las é
    erro: colisão pergunta 'qual a aproximação MÁXIMA entre estas duas formas?',
    e se responde coluna a coluna; buraco pergunta 'quanto branco corrido existe
    entre estes dois blocos?', e se responde por extremos. Medido no lote, a
    mesma costura dá 152 pela faixa e 197 pela coluna — porque a última linha da
    headline e o topo do gráfico não se cruzam nas mesmas colunas."""
    if a.get("base") is None or b.get("topo") is None: return None
    if vao_entre(a, b) is None: return None      # lado a lado: não há faixa
    return b["topo"] - a["base"]


def _cruza(a: dict, b: dict) -> bool:
    return vao_entre(a, b) is not None


def vaos(m: dict) -> list[dict]:
    """Vãos de TINTA entre blocos consecutivos, do topo da safe até a base."""
    fora = []
    for s in m["slides"]:
        anterior = None
        bs = sorted(((k, v) for k, v in s["blocos"].items() if v.get("topo") is not None),
                    key=lambda kv: kv[1]["topo"])
        # VÃO VERTICAL SÓ EXISTE ENTRE BLOCOS QUE SE CRUZAM NA HORIZONTAL.
        # handle (rodapé à esquerda) e dots (à direita) não se empilham: medir a
        # distância vertical entre eles produz -14px, que não é colisão nenhuma —
        # é a assinatura de um instrumento que presume coluna única. Sem esta
        # condição, o portão de colisão reprovaria toda lâmina do parque.
        linhas, ant, ant_id = [], m["safe"]["top"], "safe topo"
        for k, v in bs:
            if ant_id != "safe topo" and not _cruza(anterior, v):
                linhas.append((ant_id, k, None))       # lado a lado: sem vão
                if v["base"] > ant: ant, ant_id, anterior = v["base"], k, v
                continue
            linhas.append((ant_id, k, v["topo"] - ant))
            ant, ant_id, anterior = max(ant, v["base"]), k, v
        linhas.append((ant_id, "safe base", (m["canvas"]["h"] - m["safe"]["bottom"]) - ant))
        fora.append({"slide": s["slide"], "vaos": linhas,
                     "ambiguidade_max_px": s["ambiguidade_max_px"]})
    return fora


if __name__ == "__main__":
    m = mede(AQUI / sys.argv[1])
    amp_geral, n_fronteiras, n_ok = 0, 0, 0
    for s in m["slides"]:
        for b in s["blocos"].values():
            if b.get("topo") is None: continue
            n_fronteiras += 1
            amp_geral = max(amp_geral, b["ambiguidade_px"])
            n_ok += b["ambiguidade_px"] <= 1
    for v in vaos(m):
        print(f"── {v['slide']}")
        for de, para, px in v["vaos"]:
            print(f"   {'  lado a lado' if px is None else f'{px:>6}px'}  {de:>12} → {para}")
    print(f"\npiso de tinta {m['piso_tinta']} · varredura ×{FATORES}")
    print(f"ambiguidade ≤1px em {n_ok}/{n_fronteiras} fronteiras · máxima {amp_geral}px")
    if "--json" in sys.argv:
        enxuto = json.loads(json.dumps(m))
        for s_ in enxuto["slides"]:
            for b in s_["blocos"].values():
                b.pop("perfil_topo", None); b.pop("perfil_base", None)
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(
            json.dumps(enxuto, indent=1, ensure_ascii=False))
