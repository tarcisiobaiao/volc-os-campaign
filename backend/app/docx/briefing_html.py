"""
Briefing de Funil (HTML) — a página que o operador abre em nova aba.

É o SEGUNDO renderizador do mesmo `BriefingModel` que gera o `.docx`. Nenhuma
decisão de composição mora aqui: quais campos, em que ordem e sob que rótulo já
foi resolvido em `briefing_model`. Aqui só existe desenho.

Por que HTML servido pelo backend, e não uma rota React consumindo JSON: a
composição depende de `role_for_position` e da montagem card+`funnel_architecture`
que vivem no Python. Uma tela React teria de reimplementar os dois — e aí o
briefing passaria a ter duas verdades, uma para o Word e outra para a tela. Uma
página servida pelo backend reaproveita o modelo inteiro e ainda ganha de graça
o que o operador pediu: abre em nova aba por URL, sem estado, e o Ctrl+P do
navegador vira PDF.

Auto-contido de propósito: todo o CSS é inline, sem arquivo estático, sem JS de
biblioteca. A única requisição externa são as duas famílias tipográficas — as
MESMAS que o `index.html` do produto já carrega do Google Fonts (Space Grotesk +
Inter), com pilha de fallback caso a rede caia.

O DESENHO segue `docs/design/DESIGN-SYSTEM.md` da VOLC:
  · flat estrito — NENHUM box-shadow no arquivo; a profundidade vem do brilho de
    gradiente ATRÁS do bloco sólido (a capa preta);
  · a Aurora em duas camadas, como no `EntityKanbanBoard`: `::before` é a luz
    (gradiente desfocado), `::after` é o grão nítido em `overlay`. Separadas
    porque o `blur` que faz o brilho apagaria o grão se fossem a mesma camada;
  · sem cantos arredondados em elemento estrutural, linhas de 1px e cruzetas (+);
  · Space Grotesk em caixa alta com tracking largo no display, Inter no corpo;
  · muito espaço negativo, tudo alinhado à esquerda.

Uma leitura precisa ser explicada: os neons (`#00D4FF`, `#8A2BE2`, `#FF3D00`)
só aparecem DENTRO do gradiente e sobre a capa preta. No papel claro o texto é
tinta escura — o próprio Design System manda "dark slate on light slides", e neon
sobre `#F4F5F6` seria ilegível num documento que existe para ser lido inteiro.
"""
from __future__ import annotations

from html import escape
from typing import List, Optional

from .briefing_model import BRAND, BriefingModel, Diretrizes, PaginaBriefing

# Ladrilho de grão de 90px. Tamanho FIXO e repetido: sem `width/height` o
# navegador estica a textura até o tamanho do elemento, e aí um bloco alto ganha
# grão graúdo e um baixo ganha grão fino — o oposto de grão de filme.
_GRAO = (
    "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' "
    "width='90' height='90'><filter id='n'><feTurbulence type='fractalNoise' "
    "baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/></filter>"
    "<rect width='90' height='90' filter='url(%23n)'/></svg>\")"
)

_CSS = """
*, *::before, *::after { box-sizing: border-box; }
:root {
  --preto: #000000;
  --papel: #F4F5F6;
  --tinta: #1A1C1E;
  --tinta-fraca: #6C7278;
  --linha: rgba(0,0,0,.16);
  --linha-clara: rgba(255,255,255,.15);
  --azul-profundo: #0D47A1;
  --aurora: linear-gradient(118deg,#FF3D00 0%,#8A2BE2 34%,#0D47A1 68%,#00D4FF 100%);
  --grao: __GRAO__;
  --display: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif;
  --corpo: 'Inter', ui-sans-serif, system-ui, sans-serif;
}
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--papel); color: var(--tinta);
  font-family: var(--corpo); font-size: 16px; line-height: 1.6;
  font-weight: 400; text-align: left;
}
.folha { max-width: 1000px; margin: 0 auto; padding: 0 48px; }

/* ── kicker / rótulo técnico ─────────────────────────────────────────────── */
.kicker {
  font-family: var(--display); font-size: .75rem; font-weight: 600;
  letter-spacing: .18em; text-transform: uppercase; color: var(--tinta-fraca);
  margin: 0 0 8px;
}

/* ── AÇÕES (não existem no papel) ────────────────────────────────────────── */
.acoes {
  display: flex; gap: 12px; justify-content: flex-end;
  max-width: 1000px; margin: 0 auto; padding: 20px 48px 0;
}
.acao {
  font-family: var(--display); font-size: .75rem; font-weight: 600;
  letter-spacing: .14em; text-transform: uppercase;
  padding: 9px 18px; border: 1px solid var(--linha); background: transparent;
  color: var(--tinta); cursor: pointer; text-decoration: none;
  transition: border-color .3s cubic-bezier(.16,1,.3,1), color .3s cubic-bezier(.16,1,.3,1);
}
.acao:hover { border-color: var(--azul-profundo); color: var(--azul-profundo); }

/* ── CAPA: bloco preto sólido com a Aurora brilhando ATRÁS ───────────────── */
.capa-envelope { position: relative; z-index: 0; margin: 28px 0 0; }
.capa-envelope::before, .capa-envelope::after {
  content: ''; position: absolute; inset: -26px -18px -34px; z-index: -1;
  pointer-events: none;
}
/* Desfoque MENOR e opacidade MAIOR do que a aurora do Kanban: lá o brilho nasce
   sobre um card claro dentro de uma coluna cinza; aqui ele sangra sobre papel
   quase branco, que lava a saturação. Sem essa correção o neon vira pastel. */
.capa-envelope::before { background: var(--aurora); filter: blur(22px); opacity: .72; }
.capa-envelope::after {
  background-image: var(--grao); background-size: 90px 90px;
  opacity: .22; mix-blend-mode: overlay;
}
.capa {
  background: var(--preto); color: #FFFFFF; position: relative;
  padding: 72px 56px 88px;
}
.capa-topo {
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 16px; border-bottom: 1px solid var(--linha-clara); padding-bottom: 18px;
}
.capa-marca {
  font-family: var(--display); font-weight: 700; font-size: .875rem;
  letter-spacing: .3em; text-transform: uppercase; color: #FFFFFF;
}
.capa-selo {
  font-family: var(--display); font-weight: 600; font-size: .6875rem;
  letter-spacing: .22em; text-transform: uppercase; color: rgba(255,255,255,.55);
}
.capa-titulo {
  font-family: var(--display); font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; line-height: 1.02;
  font-size: clamp(2rem, 5.5vw, 3.5rem); margin: 96px 0 0; color: #FFFFFF;
}
/* Tipografia vazada — assinatura da marca. `color: transparent` só entra se o
   navegador realmente souber desenhar o traço, senão o nome sumiria da capa. */
.capa-entidade {
  font-family: var(--display); font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; line-height: 1.02;
  font-size: clamp(2rem, 5.5vw, 3.5rem); margin: 4px 0 0; color: #FFFFFF;
}
@supports ((-webkit-text-stroke: 1px #FFFFFF) or (text-stroke: 1px #FFFFFF)) {
  .capa-entidade { -webkit-text-stroke: 1px #FFFFFF; text-stroke: 1px #FFFFFF; color: transparent; }
}
.capa-sub {
  font-family: var(--corpo); font-size: 1rem; color: rgba(255,255,255,.72);
  margin: 40px 0 0;
}
.capa-sub + .capa-sub { margin-top: 6px; }
.capa-sub--tec {
  font-family: var(--display); font-size: .8125rem; font-weight: 500;
  letter-spacing: .16em; text-transform: uppercase; color: rgba(255,255,255,.9);
}
/* Cruzetas: clima técnico/arquitetônico, nos quatro cantos do bloco. */
.cruz {
  position: absolute; font-family: var(--display); font-size: 1rem;
  line-height: 1; color: rgba(255,255,255,.42); user-select: none;
}
.cruz-se { top: 20px; left: 20px; }
.cruz-sd { top: 20px; right: 20px; }
.cruz-ie { bottom: 20px; left: 20px; }
.cruz-id { bottom: 20px; right: 20px; }
/* A linha de 1px que o design pede — mesma aurora, sem desfoque. */
.fio { height: 1px; width: 100%; background: var(--aurora); }

/* ── SEÇÕES ──────────────────────────────────────────────────────────────── */
.secao { padding: 96px 0 0; }
.secao-titulo {
  font-family: var(--display); font-weight: 700; text-transform: uppercase;
  letter-spacing: .02em; font-size: clamp(1.5rem, 3.2vw, 2.5rem);
  line-height: 1.1; margin: 0 0 24px; padding-bottom: 20px;
  border-bottom: 1px solid var(--tinta);
}
.campo { margin: 0 0 28px; max-width: 68ch; }
.campo p { margin: 0; }
.ausente { color: var(--tinta-fraca); }

/* ── PÁGINAS DO FUNIL ────────────────────────────────────────────────────── */
.pagina { display: grid; grid-template-columns: 96px minmax(0,1fr); gap: 0 32px; padding: 64px 0 0; }
.pagina + .pagina { border-top: 1px solid var(--linha); }
.pagina-marcador { padding-top: 4px; }
.pagina-num {
  font-family: var(--display); font-weight: 700; font-size: 2rem; line-height: 1;
  letter-spacing: .04em; color: var(--tinta);
}
@supports ((-webkit-text-stroke: 1px #1A1C1E) or (text-stroke: 1px #1A1C1E)) {
  .pagina-num { -webkit-text-stroke: 1px var(--tinta); text-stroke: 1px var(--tinta); color: transparent; }
}
.pagina-corpo { min-width: 0; }
.pagina-papel {
  font-family: var(--display); font-size: .75rem; font-weight: 600;
  letter-spacing: .18em; text-transform: uppercase; color: var(--azul-profundo);
  margin: 0 0 10px;
}
.pagina-titulo {
  font-family: var(--corpo); font-size: 1.5rem; font-weight: 600;
  line-height: 1.25; margin: 0 0 14px; max-width: 34ch;
}
.pagina-url {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .8125rem;
  color: var(--azul-profundo); margin: 0 0 18px; word-break: break-all;
}
.bloco { margin: 0 0 28px; max-width: 68ch; }
.bloco h4 {
  font-family: var(--display); font-size: .75rem; font-weight: 600;
  letter-spacing: .18em; text-transform: uppercase; color: var(--tinta-fraca);
  margin: 0 0 10px; padding-bottom: 8px; border-bottom: 1px solid var(--linha);
}
.bloco ul { margin: 0; padding: 0; list-style: none; }
.bloco li { position: relative; padding-left: 22px; margin: 0 0 8px; }
.bloco li::before {
  content: '+'; position: absolute; left: 0; top: 0;
  font-family: var(--display); color: var(--azul-profundo);
}
.bloco p { margin: 0; }

/* ── FICHA DE REDAÇÃO ────────────────────────────────────────────────────── */
table.ficha { width: 100%; border-collapse: collapse; }
table.ficha th, table.ficha td {
  border: 1px solid var(--linha); padding: 10px 14px; text-align: left;
  vertical-align: top; font-size: .9375rem;
}
table.ficha th {
  font-family: var(--display); font-size: .6875rem; font-weight: 600;
  letter-spacing: .16em; text-transform: uppercase; color: var(--tinta-fraca);
  background: #FFFFFF; width: 30%;
}
table.ficha td { word-break: break-word; }

/* ── AVISO (funil sem páginas) ───────────────────────────────────────────── */
.aviso { position: relative; padding: 24px 24px 24px 32px; background: #FFFFFF; max-width: 68ch; }
.aviso::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--aurora); }

/* ── RODAPÉ ──────────────────────────────────────────────────────────────── */
.rodape {
  display: flex; justify-content: space-between; gap: 16px;
  margin: 120px 0 0; padding: 20px 0 72px; border-top: 1px solid var(--linha);
  font-family: var(--display); font-size: .6875rem; font-weight: 500;
  letter-spacing: .16em; text-transform: uppercase; color: var(--tinta-fraca);
}

@media (max-width: 720px) {
  .folha, .acoes { padding-left: 20px; padding-right: 20px; }
  .capa { padding: 48px 24px 56px; }
  .capa-titulo { margin-top: 56px; }
  .pagina { grid-template-columns: minmax(0,1fr); gap: 12px; }
  .secao { padding-top: 64px; }
}
@media (prefers-reduced-motion: reduce) { .acao { transition: none; } }

/* ── IMPRESSÃO (Ctrl+P -> PDF) ───────────────────────────────────────────── */
@page { size: A4; margin: 16mm 14mm; }
@media print {
  body { background: #FFFFFF; font-size: 10.5pt; }
  .folha { max-width: none; padding: 0; }
  .acoes { display: none; }
  /* A capa vira tinta econômica: o brilho da Aurora é um efeito de tela e não
     sobrevive ao papel — o que sobrevive é o fio de 1px, que fica. */
  .capa-envelope { margin: 0; }
  .capa-envelope::before, .capa-envelope::after { display: none; }
  .capa { background: transparent; color: var(--tinta); padding: 0 0 40px; break-after: page; }
  .capa-topo { border-bottom-color: var(--tinta); }
  .capa-marca, .capa-titulo { color: var(--tinta); }
  .capa-selo, .capa-sub { color: var(--tinta-fraca); }
  .capa-sub--tec { color: var(--tinta); }
  .capa-entidade { color: var(--tinta); -webkit-text-stroke: 0; text-stroke: 0; }
  /* As cruzetas marcam os cantos do BLOCO preto. Sem o bloco elas pousam em
     lugar nenhum no meio da folha — no papel quem faz o clima técnico são os
     fios de 1px. */
  .cruz { display: none; }
  .pagina-num { color: var(--tinta); -webkit-text-stroke: 0; text-stroke: 0; }
  .fio, .aviso::before { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .secao { padding-top: 40px; }
  .pagina { padding-top: 32px; break-before: auto; }
  .pagina-cabeca { break-after: avoid; }
  .bloco h4 { break-after: avoid; }
  table.ficha, .aviso { break-inside: avoid; }
  .rodape { margin-top: 48px; padding-bottom: 0; }
  a { color: inherit; text-decoration: none; }
}
""".replace("__GRAO__", _GRAO)


def _esc(v: str) -> str:
    return escape(str(v), quote=True)


def _valor(v: Optional[str]) -> str:
    """Ausente é buraco: o travessão vem MARCADO, para não se confundir com um
    valor que por acaso é um travessão."""
    if v is None or v == "":
        return '<span class="ausente">—</span>'
    return _esc(v)


def _bloco_diretrizes(d: Optional[Diretrizes]) -> str:
    if d is None:
        return ""
    if d.bullets:
        itens = "".join(f"<li>{_esc(b)}</li>" for b in d.bullets)
        miolo = f"<ul>{itens}</ul>"
    elif d.prosa:
        miolo = f"<p>{_esc(d.prosa)}</p>"
    else:
        return ""
    return f'<div class="bloco"><h4>{_esc(d.titulo)}</h4>{miolo}</div>'


def _bloco_lista(titulo: str, itens: List[str]) -> str:
    if not itens:
        return ""
    lis = "".join(f"<li>{_esc(i)}</li>" for i in itens)
    return f'<div class="bloco"><h4>{_esc(titulo)}</h4><ul>{lis}</ul></div>'


def _pagina(pag: PaginaBriefing) -> str:
    partes: List[str] = []
    # cabeça da página: papel + título + URL andam juntos na quebra de impressão
    cabeca = [f'<p class="pagina-papel">{_esc(pag.papel)}</p>'] if pag.papel else []
    cabeca.append(f'<h3 class="pagina-titulo">{_valor(pag.titulo)}</h3>')
    if pag.slug:
        cabeca.append(f'<p class="pagina-url">/{_esc(pag.slug)}</p>')
    partes.append(f'<div class="pagina-cabeca">{"".join(cabeca)}</div>')

    if pag.objetivo:
        partes.append(
            '<div class="bloco"><h4>Objetivo da página</h4>'
            f"<p>{_esc(pag.objetivo)}</p></div>"
        )
    # a introdução vem ANTES da lista de H2 e o fechamento DEPOIS — a ordem é a
    # da página que o redator vai escrever (decidida no modelo, repetida aqui).
    partes.append(_bloco_diretrizes(pag.introducao))
    partes.append(_bloco_lista("Estrutura da página (H2)", pag.estrutura_h2))
    partes.append(_bloco_diretrizes(pag.fechamento))
    partes.append(_bloco_lista("Links internos", pag.links_internos))

    if pag.ficha:
        linhas = "".join(
            f"<tr><th scope=\"row\">{_esc(c.rotulo)}</th><td>{_valor(c.valor)}</td></tr>"
            for c in pag.ficha
        )
        partes.append(
            '<div class="bloco"><h4>Ficha de redação</h4>'
            f'<table class="ficha"><tbody>{linhas}</tbody></table></div>'
        )

    return (
        '<article class="pagina">'
        f'<div class="pagina-marcador"><span class="pagina-num">P{pag.posicao}</span></div>'
        f'<div class="pagina-corpo">{"".join(partes)}</div>'
        "</article>"
    )


def render_briefing_html(model: BriefingModel, *, docx_url: Optional[str] = None) -> str:
    """Documento HTML completo e auto-contido. `docx_url` só é renderizado se o
    chamador souber a rota do arquivo — o botão de exportar não é inventado."""
    acoes = ['<button type="button" class="acao" onclick="window.print()">Imprimir / PDF</button>']
    if docx_url:
        acoes.insert(0, f'<a class="acao" href="{_esc(docx_url)}">Exportar .docx</a>')

    estrategia: List[str] = []
    for rotulo, valor in (("Avatar", model.avatar), ("Tom de voz", model.tom),
                          ("Arquitetura", model.arquitetura)):
        if valor:
            estrategia.append(
                f'<div class="campo"><p class="kicker">{_esc(rotulo)}</p>'
                f"<p>{_esc(valor)}</p></div>"
            )

    corpo: List[str] = [_pagina(p) for p in model.paginas]
    if model.aviso_sem_paginas:
        corpo.append(f'<div class="aviso"><p>{_esc(model.aviso_sem_paginas)}</p></div>')

    sub1 = f'<p class="capa-sub">{_esc(model.capa_subtitulo_1)}</p>' if model.capa_subtitulo_1 else ""

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(model.titulo_documento)}</title>
<meta name="description" content="{_esc(model.descricao)}">
<meta name="robots" content="noindex, nofollow">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
<div class="acoes">{"".join(acoes)}</div>
<div class="folha">
  <div class="capa-envelope">
    <header class="capa">
      <span class="cruz cruz-se">+</span><span class="cruz cruz-sd">+</span>
      <span class="cruz cruz-ie">+</span><span class="cruz cruz-id">+</span>
      <div class="capa-topo">
        <span class="capa-marca">{_esc(BRAND)} · Pautador Pro</span>
        <span class="capa-selo">Confidencial</span>
      </div>
      <h1 class="capa-titulo">{_esc(model.capa_titulo)}</h1>
      <p class="capa-entidade">{_esc(model.entidade)}</p>
      {sub1}
      <p class="capa-sub capa-sub--tec">{_esc(model.capa_subtitulo_2)}</p>
    </header>
  </div>
  <div class="fio"></div>

  <section class="secao">
    <h2 class="secao-titulo">{_esc(model.nome_funil)}</h2>
    {"".join(estrategia)}
  </section>

  <section class="secao">
    {"".join(corpo)}
  </section>

  <footer class="rodape">
    <span>{_esc(BRAND)} · {_esc(model.capa_titulo)} · {_esc(model.entidade)}</span>
    <span>{_esc(model.periodo)}</span>
  </footer>
</div>
</body>
</html>
"""
