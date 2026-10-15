"""Prova da primeira dobra da LP por geometria renderizada (Chromium local).

Mede, numa página já renderizada, as caixas do H1, do subtítulo e dos botões
do herói visível e da folha de consentimento (CMP), e decide:

- título legível (inteiro na tela, acima da CMP, fonte >= 20 px);
- CTA principal inteiro na primeira dobra (acima da CMP);
- 2º caminho identificável (inteiro acima da CMP);
- 3º botão acessível sem ficar parcialmente encoberto (inteiro acima da CMP,
  e o centro dele recebe o toque, `elementFromPoint`);
- zero sobreposição entre título, subtítulo, botões e CMP;
- zero rolagem horizontal.

Dois modos, mesma medição:

    # prévia estática (render_lp + adapters.preview + CMP real lida do PHP)
    python scripts/prova_dobra_lp.py preview --cmp-php <volc-consent-manager.php> --saida DIR

    # página servida (ex.: WordPress descartável com Elementor)
    python scripts/prova_dobra_lp.py url http://localhost:8099/?page_id=N --saida DIR

Não publica, não chama modelo e não acessa site real: o modo `url` recusa host
que não seja localhost/127.0.0.1. Grava screenshots e `metricas-*.json`.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

SITE = "https://creditoup.com.br"
HREFS = [f"{SITE}/rec/por-onde-comecar-senac-pr", f"{SITE}/rec/tipos-de-curso-senac-p1",
         f"{SITE}/rec/bolsas-de-estudo-senac-p2"]

# Conteúdo realista (funil Senac, rótulos do 4e43c9b2) e o pior caso que o
# motor orienta: título 40, subtítulo 80, rótulo 60 caracteres (ctas.py).
CONTEUDOS = {
    "realista": {
        "hero_title": "Cursos gratuitos no Senac Paraná",
        "hero_subtitle": "Para quem tem renda de até 2 salários mínimos por pessoa.",
        "cta_texts": ["Ver se a minha renda permite a vaga",
                      "Conhecer os tipos de curso gratuitos",
                      "Entender as bolsas de estudo do Senac"],
    },
    "pior_caso": {
        "hero_title": "Cursos gratuitos e bolsas do Senac em 26",
        "hero_subtitle": ("Para quem tem renda familiar de até 2 salários mínimos por "
                          "pessoa no estado."),
        "cta_texts": ["Ver se a minha renda familiar permite a vaga gratuita agora",
                      "Conhecer os tipos de curso gratuitos e os requisitos de cada",
                      "Entender as bolsas de estudo do Senac e o que elas cobrem já"],
    },
}
_CORPO = {
    "article_title": "Como funciona", "intro": "<p>Resposta curta para decidir.</p>",
    "sections": [{"title": f"Seção {i}", "body": f"<p>Corpo da seção {i}.</p>" * 3}
                 for i in range(4)],
    "faq": [{"q": "Quem pode?", "a": "Quem cumpre a renda."}], "faq_title": "Dúvidas",
    "transition": "<p>Escolha o seu caminho.</p>",
}

_MEDIR_JS = r"""() => {
  const vis = e => e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden'
      && getComputedStyle(e).display !== 'none';
  const box = e => { const r = e.getBoundingClientRect();
    return {top: r.top, bottom: r.bottom, left: r.left, right: r.right,
            width: r.width, height: r.height}; };
  const h1 = [...document.querySelectorAll('h1')].find(vis);
  let hero = h1;
  while (hero && hero.parentElement && !hero.parentElement.matches('body,main,.elementor,.elementor-section-wrap,[data-elementor-type]')) {
    const btns = hero.querySelectorAll('a.elementor-button');
    if ([...btns].filter(vis).length >= 1 && hero.querySelector('h1') === h1 &&
        hero.getBoundingClientRect().height > h1.getBoundingClientRect().height * 2) break;
    hero = hero.parentElement;
  }
  const botoes = hero ? [...hero.querySelectorAll('a.elementor-button')].filter(vis) : [];
  const titulos = hero ? [...hero.querySelectorAll('h1, p.elementor-heading-title, .elementor-heading-title, h2, p')]
      .filter(vis).filter(e => e !== h1 && !e.closest('a') && (e.innerText||'').trim()) : [];
  const sub = titulos.find(e => !e.contains(h1) && !h1.contains(e));
  const cmp = document.getElementById('volc-consent-banner');
  const cmpVis = cmp && !cmp.hidden && vis(cmp);
  const toque = botoes.map(b => { const r = b.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    const alvo = (y >= 0 && y < innerHeight) ? document.elementFromPoint(x, y) : null;
    return !!alvo && (alvo === b || b.contains(alvo)); });
  return {
    viewport: {width: innerWidth, height: innerHeight},
    scroll_width: document.documentElement.scrollWidth,
    client_width: document.documentElement.clientWidth,
    h1: h1 ? {...box(h1), texto: h1.innerText, fonte_px: parseFloat(getComputedStyle(h1).fontSize)} : null,
    subtitulo: sub ? {...box(sub), texto: sub.innerText} : null,
    botoes: botoes.map((b, i) => ({...box(b), texto: b.innerText, recebe_toque: toque[i]})),
    cmp: cmpVis ? box(cmp) : null,
  };
}"""


def _cruza(a: dict, b: dict) -> bool:
    return (min(a["right"], b["right"]) - max(a["left"], b["left"]) > 0.5
            and min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]) > 0.5)


def avaliar(m: dict, *, mobile: bool) -> dict:
    """As decisões a partir das caixas medidas (puro, testável sem navegador)."""
    vh = m["viewport"]["height"]
    limite = m["cmp"]["top"] if m.get("cmp") else vh
    inteiro = lambda c: c is not None and c["top"] >= 0 and c["bottom"] <= limite + 0.5 \
        and c["left"] >= 0 and c["right"] <= m["viewport"]["width"] + 0.5
    botoes = m.get("botoes") or []
    caixas = [c for c in [m.get("h1"), m.get("subtitulo"), *botoes] if c]
    sobreposicoes = [(i, j) for i in range(len(caixas)) for j in range(i + 1, len(caixas))
                     if _cruza(caixas[i], caixas[j])]
    sob_cmp = [i for i, c in enumerate(caixas) if m.get("cmp") and _cruza(c, m["cmp"])]
    r = {
        "titulo_legivel": inteiro(m.get("h1")) and (m["h1"] or {}).get("fonte_px", 0) >= 20,
        "cta_principal_inteiro": len(botoes) >= 1 and inteiro(botoes[0]),
        "segundo_caminho_identificavel": len(botoes) >= 2 and inteiro(botoes[1]),
        "terceiro_botao_acessivel": len(botoes) >= 3 and inteiro(botoes[2])
        and bool(botoes[2].get("recebe_toque")),
        "zero_sobreposicao": not sobreposicoes and not sob_cmp,
        "zero_rolagem_horizontal": m["scroll_width"] <= m["client_width"],
        "folga_ate_a_cmp_px": round(limite - botoes[-1]["bottom"], 1) if botoes else None,
    }
    if not mobile:
        sub = (m.get("subtitulo") or {}).get("texto", "")
        r["desktop_sem_toque_abaixo"] = "toque abaixo" not in sub.lower()
        r = {k: r[k] for k in ("titulo_legivel", "cta_principal_inteiro",
                               "segundo_caminho_identificavel", "zero_sobreposicao",
                               "zero_rolagem_horizontal", "desktop_sem_toque_abaixo")}
    r["ok"] = all(v for k, v in r.items() if k != "folga_ate_a_cmp_px")
    return r


def _cmp_estatica(cmp_php: Path) -> tuple[str, str]:
    """CSS e markup da CMP EXATAMENTE como o MU-plugin do site imprime (sem PHP)."""
    fonte = cmp_php.read_text(encoding="utf-8")
    css = re.search(r'<style id="volc-consent-styles">(.*?)</style>', fonte, re.S).group(1)
    sec = re.search(r'(<section class="volc-consent".*?</section>)', fonte, re.S).group(1)
    sec = re.sub(r"<\?php.*?\?>", "", sec, flags=re.S)
    return css, sec


def html_da_previa(conteudo: dict, cmp_php: Path | None) -> str:
    from funnelforge.adapters.preview import document, elementor_body
    from funnelforge.pipeline.lp_template import load_lp_template, render_lp
    cont, _ = render_lp(load_lp_template(), {**_CORPO, **conteudo}, HREFS, id_seed="prova",
                        hero_image_url="data:image/gif;base64,R0lGODlhAQABAIAAAP8AOwAAACwAAAAAAQABAAACAkQBADs=",
                        site_domain=SITE, copy_rapida=True, footer_disclosure=True)
    body, css = elementor_body(cont)
    head = ""
    if cmp_php is not None:
        cmp_css, cmp_html = _cmp_estatica(cmp_php)
        head = f"<style>{cmp_css}</style>"
        body += cmp_html
    return document("prova", body, css=css, head=head)


def medir(page, alvo: str, saida: Path, nome: str, *, set_content: bool) -> dict:
    resultado = {}
    for rotulo, (w, h, mobile) in {"360x800": (360, 800, True),
                                   "1366x900": (1366, 900, False)}.items():
        page.set_viewport_size({"width": w, "height": h})
        if set_content:
            page.set_content(alvo, wait_until="load")
        else:
            page.goto(alvo, wait_until="load")
        page.wait_for_timeout(300)
        m = page.evaluate(_MEDIR_JS)
        page.screenshot(path=str(saida / f"{nome}-{rotulo}.png"))
        resultado[rotulo] = {"medidas": m, "decisao": avaliar(m, mobile=mobile)}
    return resultado


def main(argv: list[str]) -> int:
    import argparse
    from playwright.sync_api import sync_playwright
    p = argparse.ArgumentParser()
    p.add_argument("modo", choices=["preview", "url"])
    p.add_argument("alvo", nargs="?")
    p.add_argument("--cmp-php", type=Path)
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--nome", default="lp")
    a = p.parse_args(argv)
    a.saida.mkdir(parents=True, exist_ok=True)
    relatorio = {}
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=True)
        ctx = navegador.new_context(device_scale_factor=2)
        page = ctx.new_page()
        if a.modo == "url":
            host = urlsplit(a.alvo or "").hostname or ""
            if host not in ("localhost", "127.0.0.1"):
                raise SystemExit("modo url só aceita localhost/127.0.0.1")
            page.route("**/*", lambda r: r.continue_() if (urlsplit(r.request.url).hostname
                       in ("localhost", "127.0.0.1", "fonts.googleapis.com",
                           "fonts.gstatic.com")) or r.request.url.startswith("data:")
                       else r.abort())
            relatorio[a.nome] = medir(page, a.alvo, a.saida, a.nome, set_content=False)
        else:
            for nome, conteudo in CONTEUDOS.items():
                html = html_da_previa(conteudo, a.cmp_php)
                relatorio[nome] = medir(page, html, a.saida, f"previa-{nome}",
                                        set_content=True)
        navegador.close()
    (a.saida / f"metricas-{a.modo}-{a.nome}.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: {v: r["decisao"] for v, r in d.items()} for k, d in relatorio.items()},
                     ensure_ascii=False, indent=2))
    return 0 if all(r["decisao"]["ok"] for d in relatorio.values() for r in d.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
