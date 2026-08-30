"""Dado → UM bloco `wp:html`. Determinístico, e é isso que o torna confiável.

O modelo nunca mais escreve HTML, CSS ou JavaScript. Ele descreve o conteúdo
(`contrato.Widget`) e este módulo imprime — sempre com as mesmas tags, os mesmos
atributos, o mesmo script. As regras de `checks.py::sanitize_widget_block`
deixam de ser um pedido feito em linguagem natural e passam a ser propriedade do
gabarito:

- só tags da allowlist (`div span strong em ul li h3 h4 button label select
  option section`) — em especial, NUNCA `<p>`, que `paragraph_in_raw_html` recusa;
- só atributos da allowlist mais `data-*`/`aria-*`;
- exatamente um `<style>` e um `<script>`, ambos inline;
- `grid-area` presente, `.style.display` ausente, `&` ausente do script.

A prova `testes_render.py::test_todo_arquetipo_passa_no_sanitizador` roda o
sanitizador de verdade sobre os quatro arquétipos. Se algum dia a allowlist
apertar, é ali que aparece — não no navegador do leitor.

## Progressive enhancement

O cenário de abertura sai do forno com `style="visibility:visible"`. Se o
JavaScript não rodar — bloqueado, erro de outro plugin, navegador antigo — o
leitor ainda vê a peça montada, com o título, a instrução e os controles. Ele
perde a interação, não a página.
"""
from __future__ import annotations

import hashlib

from funnelforge.widgets.contrato import ARQUETIPOS, Cenario, Widget
from funnelforge.widgets.estilo import CSS, JS


def _esc(texto: str) -> str:
    """Escapa para texto e para valor de atributo ao mesmo tempo.

    O `&` vira `&amp;` no HTML — permitido e necessário aqui. Ele é proibido
    apenas dentro do `<script>`, que é constante e não passa por esta função.
    """
    return (texto.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;").replace('"', "&quot;"))


def _id_do_widget(w: Widget) -> str:
    """Identificador estável: mesma entrada, mesmo id.

    Estável e não aleatório para que reexecutar a mesma run produza o mesmo
    HTML — um diff de publicação que muda só por causa de um id sorteado é
    ruído que esconde a mudança real.
    """
    semente = f"{w.arquetipo}|{w.titulo}|{len(w.cenarios)}"
    return "vw-" + hashlib.sha256(semente.encode("utf-8")).hexdigest()[:10]


def _chave(w: Widget, c: Cenario) -> str:
    """`c1=valor|c2=valor`, na ordem dos controles — o mesmo que o JS monta."""
    return "|".join(f"{ctl.id}={c.quando.get(ctl.id, '')}" for ctl in w.controles)


def _controles(w: Widget) -> str:
    partes = []
    forma = w.forma
    for ctl in w.controles:
        cid = f"{_id_do_widget(w)}-{ctl.id}"
        if forma == "botoes":
            # ⚠️ Um <label for> não rotula um grupo de botões, e `role="group"`
            # está FORA da allowlist do sanitizador — que só deixa passar
            # `aria-*` e `data-*` por prefixo. Afrouxar a allowlist para caber
            # semântica seria mexer num controle de segurança por conveniência.
            #
            # A saída é dar o contexto em cada botão: quem tabula ouve
            # "Rota: Saque-Aniversário" em vez de um nome solto. O texto visível
            # continua contido no nome acessível, que é o que a regra
            # "Label in Name" (WCAG 2.5.3) exige para o comando de voz.
            opcoes = "".join(
                f'<button type="button" class="vw-bt" data-vw-opt="{_esc(o.valor)}" '
                f'aria-pressed="{"true" if i == 0 else "false"}" '
                f'aria-label="{_esc(ctl.rotulo)}: {_esc(o.texto)}">'
                f'{_esc(o.texto)}</button>'
                for i, o in enumerate(ctl.opcoes))
            corpo = (f'<span class="vw-rot" id="{cid}-r">{_esc(ctl.rotulo)}</span>'
                     f'<div class="vw-bts">{opcoes}</div>')
        else:
            opcoes = "".join(
                f'<option value="{_esc(o.valor)}"'
                f'{" selected" if i == 0 else ""}>{_esc(o.texto)}</option>'
                for i, o in enumerate(ctl.opcoes))
            corpo = (f'<label class="vw-rot" for="{cid}">{_esc(ctl.rotulo)}</label>'
                     f'<select class="vw-sel" id="{cid}">{opcoes}</select>')
        # ⚠️ A PEÇA NASCE RESPONDIDA — e é isso que mata o buraco branco.
        #
        # Antes havia um "Selecione…" e um cenário de abertura com uma
        # instrução. Como todos os cenários dividem a mesma célula do grid, o
        # container já nascia com a altura do MAIOR — e a abertura, curta,
        # deixava o resto vazio. Medido em 19/08/2026: 148px de abertura num
        # container de 864px na p4, ou seja 716px de branco no meio do artigo,
        # ANTES de o leitor tocar em qualquer coisa.
        #
        # Preselecionar a primeira opção resolve de vez: o leitor chega e já vê
        # um resultado real, com a caixa do tamanho do conteúdo. Um instrumento
        # preenchido e que responde também é mais obviamente interativo que um
        # vazio pedindo para ser preenchido.
        #
        # O custo é declarar uma escolha inicial pelo leitor. O prompt endereça
        # isso pedindo que a PRIMEIRA opção seja a mais comum ou a mais neutra —
        # nunca a mais grave.
        inicial = _esc(ctl.opcoes[0].valor) if ctl.opcoes else ""
        partes.append(f'<div data-vw-ctl="{_esc(ctl.id)}" '
                      f'data-vw-valor="{inicial}">{corpo}</div>')
    return f'<div class="vw-ctls">{"".join(partes)}</div>'


def _cenario(w: Widget, c: Cenario, *, visivel: bool = False) -> str:
    interno = [f'<span class="vw-chip">{_esc(c.chip)}</span>',
               f'<h4 class="vw-ctit">{_esc(c.titulo)}</h4>']
    if c.corpo:
        interno.append(f'<div class="vw-corpo">{_esc(c.corpo)}</div>')
    if c.passos:
        itens = "".join(f'<li class="vw-passo">{_esc(p)}</li>' for p in c.passos)
        interno.append(f'<ul class="vw-passos">{itens}</ul>')
    if c.listas:
        blocos = []
        for lst in c.listas:
            itens = "".join(f'<li class="vw-litem">{_esc(i)}</li>' for i in lst.itens)
            blocos.append(f'<div><div class="vw-lrot">{_esc(lst.rotulo)}</div>'
                          f'<ul>{itens}</ul></div>')
        interno.append(f'<div class="vw-listas">{"".join(blocos)}</div>')

    padrao = ' data-vw-padrao="1"' if c.padrao else ""
    # O cenário inicial sai do forno já visível: sem isto haveria um piscar
    # entre o HTML chegar e o script rodar, e a peça ficaria vazia se o script
    # nunca rodasse.
    estilo = ' style="visibility:visible"' if visivel else ""
    return (f'<div class="vw-cen vw-t-{c.tom}" data-vw-cen="1" '
            f'data-vw-quando="{_esc(_chave(w, c))}"{padrao}{estilo}>'
            f'<div class="vw-caixa">{"".join(interno)}</div></div>')


def _inicial(w: Widget) -> Cenario | None:
    """Qual cenário está visível quando a página carrega.

    É o que casa com a primeira opção de cada controle — a mesma conta que o
    JavaScript faz. Renderizá-lo já visível é o que evita um piscar entre o
    HTML chegar e o script rodar, e é o que mantém a peça útil se o script
    NUNCA rodar (bloqueado, erro de outro plugin, navegador antigo).
    """
    if not w.cenarios:
        return None
    chave_inicial = "|".join(
        f"{c.id}={c.opcoes[0].valor if c.opcoes else ''}" for c in w.controles)
    for c in w.cenarios:
        if _chave(w, c) == chave_inicial:
            return c
    for c in w.cenarios:
        if c.padrao:
            return c
    return w.cenarios[0]


def renderizar(w: Widget) -> str:
    """Devolve o bloco Gutenberg completo, pronto para `inject_widget`."""
    wid = _id_do_widget(w)
    eyebrow = str(ARQUETIPOS[w.arquetipo]["eyebrow"])

    sub = f'<div class="vw-sub">{_esc(w.subtitulo)}</div>' if w.subtitulo else ""
    pe = f'<div class="vw-pe">{_esc(w.rodape)}</div>' if w.rodape else ""
    primeiro = _inicial(w)
    cenarios = "".join(_cenario(w, c, visivel=(c is primeiro)) for c in w.cenarios)

    # `aria-live="polite"` porque a troca de cenário é a resposta à ação do
    # leitor: sem isso, quem usa leitor de tela escolhe e não ouve nada mudar.
    html = (
        f'<section class="vw" id="{wid}">'
        f'<div class="vw-top">'
        f'<span class="vw-olho">{_esc(eyebrow)}</span>'
        f'<h3 class="vw-tit">{_esc(w.titulo)}</h3>{sub}'
        f'</div>'
        f'{_controles(w)}'
        f'<div class="vw-out" aria-live="polite">{cenarios}</div>'
        f'{pe}'
        f'</section>'
    )
    return ("<!-- wp:html -->\n"
            f"<style>{CSS}</style>\n"
            f"{html}\n"
            f"<script>{JS.replace('__ID__', wid)}</script>\n"
            "<!-- /wp:html -->")


def texto_visivel(w: Widget) -> str:
    """Só as palavras que o leitor lê — para o portão factual.

    O gate de ancoragem tem de julgar o CONTEÚDO, não o CSS. Antes ele recebia o
    bloco inteiro, com 4 KB de folha de estilo dentro; agora recebe isto.
    """
    linhas = [w.titulo, w.subtitulo]
    for c in w.cenarios:
        linhas += [c.chip, c.titulo, c.corpo, *c.passos]
        for lst in c.listas:
            linhas += [lst.rotulo, *lst.itens]
    for ctl in w.controles:
        linhas.append(ctl.rotulo)
        linhas += [o.texto for o in ctl.opcoes]
    linhas.append(w.rodape)
    return "\n".join(l for l in linhas if l)
