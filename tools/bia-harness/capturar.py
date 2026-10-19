"""Capturas e medições da Bia na bancada visual.

Uso (com a bancada no ar: `HARNESS_PORT=8095 node_modules/.bin/vite --config tools/bia-harness/vite.config.ts`):

    python3 tools/bia-harness/capturar.py <pasta-de-saida> [--base http://127.0.0.1:8095] [--anexos <pasta>]

Para cada viewport × tema × cena: abre o widget, monta a cena, salva PNG e
mede, na própria página, (1) overflow horizontal da página e do painel,
(2) alvos de toque < 44 px no celular, (3) pares de texto/fundo abaixo de
4,5:1 dentro do painel. Escreve `medicoes.json` ao lado das imagens.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWPORTS = {"375": (375, 812), "768": (768, 1024), "1024": (1024, 768), "1440": (1440, 900)}
TEMAS = ("light", "dark")
CENAS = ("vazio", "longa", "fila", "processando", "digitando", "incerta", "erro", "upload", "paleta", "conversas")

MEDIR = r"""
() => {
  const painel = document.querySelector('[role=dialog]');
  const doc = document.scrollingElement;
  const r = { overflow_pagina: doc.scrollWidth > window.innerWidth + 1, overflow_painel: false,
              alvos_pequenos: [], contraste_baixo: [] };
  if (!painel) return r;
  const lista = painel.querySelectorAll('*');
  for (const el of lista) {
    const b = el.getBoundingClientRect();
    if (b.width && b.right > window.innerWidth + 1 && getComputedStyle(el).position !== 'fixed') {
      const rolavel = el.closest('pre, table, [class*=overflow-x-auto]');
      if (!rolavel) { r.overflow_painel = true; }
    }
  }
  if (window.innerWidth < 768) {
    for (const el of painel.querySelectorAll('button, a[href], select, textarea, [role=option]')) {
      const b = el.getBoundingClientRect();
      if (!b.width || el.closest('[aria-hidden=true]')) continue;
      if (b.width < 44 || b.height < 44) r.alvos_pequenos.push(`${el.tagName.toLowerCase()} ${(el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40)} ${Math.round(b.width)}x${Math.round(b.height)}`);
    }
  }
  const cor = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const mistura = (topo, base) => ({ r: topo.r * topo.a + base.r * (1 - topo.a), g: topo.g * topo.a + base.g * (1 - topo.a), b: topo.b * topo.a + base.b * (1 - topo.a), a: 1 });
  const fundo = (el) => {
    const pilha = [];
    for (let n = el; n; n = n.parentElement) { const c = cor(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { pilha.push(c); if (c.a >= 1) break; } }
    let base = { r: 255, g: 255, b: 255, a: 1 };
    for (const c of pilha.reverse()) base = mistura(c, base);
    return base;
  };
  for (const el of painel.querySelectorAll('p, span, button, a, dt, dd, li, h2, time, label, td, th, code, strong')) {
    const texto = Array.from(el.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('');
    if (!texto) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || el.closest('.sr-only') || el.closest('[aria-hidden=true]')) continue;
    const b = el.getBoundingClientRect(); if (!b.width || !b.height) continue;
    let c = cor(cs.color); if (!c) continue;
    const bg = fundo(el);
    let op = 1; for (let n = el; n; n = n.parentElement) op *= Number(getComputedStyle(n).opacity);
    c = mistura({ ...c, a: c.a * op }, bg);
    const L1 = lum(c), L2 = lum(bg);
    const razao = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const tamanho = parseFloat(cs.fontSize), peso = Number(cs.fontWeight) || 400;
    const grande = tamanho >= 24 || (tamanho >= 18.66 && peso >= 700);
    const desabilitado = el.closest('button:disabled');
    if (!desabilitado && razao < (grande ? 3 : 4.5)) r.contraste_baixo.push(`${razao.toFixed(2)} ${tamanho}px "${texto.slice(0, 40)}"`);
  }
  return r;
};
"""


def montar(pagina, cena: str, anexos: Path | None) -> None:
    pagina.get_by_role("button", name="Abrir a Bia").click()
    pagina.wait_for_timeout(500)
    campo = pagina.get_by_role("combobox", name="Mensagem para a Bia")
    if cena == "paleta":
        campo.click()
        campo.type("/co")
    elif cena == "upload" and anexos:
        arquivos = [str(anexos / n) for n in ("foto-suculentas.jpg", "relatorio-teste.pdf", "falso.png")]
        pagina.locator("input[type=file]").set_input_files(arquivos)
        campo.click()
        campo.type("Compare a foto com o relatório.")
    elif cena == "conversas":
        pagina.get_by_role("button", name="Conversas recentes").click()
    elif cena == "erro":
        campo.click()
        campo.type("Tente de novo, por favor.")
        campo.press("Enter")
    pagina.wait_for_timeout(700)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("saida")
    ap.add_argument("--base", default="http://127.0.0.1:8095")
    ap.add_argument("--anexos", default=None)
    ap.add_argument("--cenas", default=",".join(CENAS))
    a = ap.parse_args()
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    anexos = Path(a.anexos) if a.anexos else None
    medicoes = {}
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        for vp, (w, h) in VIEWPORTS.items():
            for tema in TEMAS:
                ctx = nav.new_context(viewport={"width": w, "height": h}, device_scale_factor=2,
                                      color_scheme="dark" if tema == "dark" else "light",
                                      has_touch=w < 768, is_mobile=w < 768)
                for cena in a.cenas.split(","):
                    pg = ctx.new_page()
                    pg.goto(f"{a.base}/?cena={cena}&tema={tema}")
                    pg.wait_for_load_state("networkidle")
                    montar(pg, cena, anexos)
                    nome = f"{vp}-{tema}-{cena}"
                    pg.screenshot(path=str(saida / f"{nome}.png"))
                    medicoes[nome] = pg.evaluate(MEDIR)
                    pg.close()
                ctx.close()
        # Movimento reduzido: os pontos de atividade param (nenhuma animação infinita).
        ctx = nav.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        pg = ctx.new_page()
        pg.goto(f"{a.base}/?cena=processando")
        pg.wait_for_load_state("networkidle")
        montar(pg, "processando", anexos)
        medicoes["reduzido-processando"] = {
            "animacoes_ativas": pg.evaluate("""() => Array.from(document.querySelectorAll('[role=dialog] *'))
                .filter((el) => getComputedStyle(el).animationName !== 'none').length"""),
            "overflow_pagina": False, "overflow_painel": False, "alvos_pequenos": [], "contraste_baixo": [],
        }
        ctx.close()
        # Zoom 200%: 1280 px de largura útil vira 640 CSS px — o painel tem que caber.
        ctx = nav.new_context(viewport={"width": 640, "height": 450}, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(f"{a.base}/?cena=longa")
        pg.wait_for_load_state("networkidle")
        montar(pg, "longa", anexos)
        pg.screenshot(path=str(saida / "zoom200-light-longa.png"))
        medicoes["zoom200-light-longa"] = pg.evaluate(MEDIR)
        ctx.close()
        nav.close()
    (saida / "medicoes.json").write_text(json.dumps(medicoes, ensure_ascii=False, indent=1))
    falhas = {k: v for k, v in medicoes.items()
              if v["overflow_pagina"] or v["overflow_painel"] or v["alvos_pequenos"] or v["contraste_baixo"] or v.get("animacoes_ativas")}
    print(json.dumps(falhas, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
