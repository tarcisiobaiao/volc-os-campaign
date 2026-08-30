"""Vocabulário Gutenberg do funil. Um lugar só, para as três páginas de solução
usarem os mesmos blocos e a mesma convenção de cor.

Regras que este módulo garante por construção:
  - botão em sequência SEMPRE separado por wp:spacer (senão o tema cola os dois)
  - cor do botão determinada pelo DESTINO, nunca escolhida à mão
  - nenhum <p> dentro de bloco wp:html (ver README: <p> vazio é removido pelo
    the_content e leva o id junto, matando o getElementById do widget)
"""

PR1 = "https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr1/"
P1  = "https://creditoup.com.br/rec/como-consultar-fgts-pelo-cpf-p1/"
P2  = "https://creditoup.com.br/rec/bancos-antecipar-fgts-pix-whatsapp-p2/"
P3  = "https://creditoup.com.br/rec/regras-demissao-quitar-emprestimo-fgts-p3/"

COR = {PR1: "#008353", P1: "#008353", P2: "#ea580c", P3: "#2563eb"}


def p(t):
    return f"<!-- wp:paragraph -->\n<p>{t}</p>\n<!-- /wp:paragraph -->"


def h2(t, anchor=None):
    idp = f' id="{anchor}"' if anchor else ""
    j = f' {{"anchor":"{anchor}"}}' if anchor else ""
    return f'<!-- wp:heading{j} -->\n<h2 class="wp-block-heading"{idp}>{t}</h2>\n<!-- /wp:heading -->'


def h3(t):
    return f'<!-- wp:heading {{"level":3}} -->\n<h3 class="wp-block-heading">{t}</h3>\n<!-- /wp:heading -->'


def lista(*itens, ordenada=False):
    tag = "ol" if ordenada else "ul"
    attr = ' {"ordered":true}' if ordenada else ""
    li = "".join(f"<li>{i}</li>" for i in itens)
    return f'<!-- wp:list{attr} -->\n<{tag} class="wp-block-list">{li}</{tag}>\n<!-- /wp:list -->'


def spacer(h=12):
    return (f'<!-- wp:spacer {{"height":"{h}px"}} -->\n'
            f'<div style="height:{h}px" aria-hidden="true" class="wp-block-spacer"></div>\n'
            f"<!-- /wp:spacer -->")


def botao(url, texto):
    """Um botão. Cor vem do destino."""
    c = COR[url]
    return ('<!-- wp:buttons --><div class="wp-block-buttons">'
            f'<!-- wp:button {{"width":100,"style":{{"border":{{"radius":"10px"}},'
            f'"color":{{"background":"{c}"}}}}}} -->'
            '<div class="wp-block-button has-custom-width wp-block-button__width-100">'
            f'<a class="wp-block-button__link has-background wp-element-button" href="{url}" '
            f'style="border-radius:10px;background-color:{c}"><strong>{texto} &raquo;</strong></a>'
            '</div><!-- /wp:button --></div><!-- /wp:buttons -->')


def botoes(*pares):
    """Vários botões em sequência, com spacer entre eles.

    Sem o spacer o tema encosta um no outro — foi o defeito visual reportado.
    """
    saida = []
    for i, (url, texto) in enumerate(pares):
        if i:
            saida.append(spacer(8))
        saida.append(botao(url, texto))
    return "\n\n".join(saida)


def nota_mesmo_site():
    return ('<!-- wp:paragraph {"align":"center","fontSize":"small"} -->\n'
            '<p class="has-text-align-center has-small-font-size">'
            "<em>* Você permanece neste mesmo site *</em></p>\n"
            "<!-- /wp:paragraph -->")


def destaque(t):
    """Frase-chave da seção. wp:pullquote, o mesmo bloco que o funil original usava."""
    return ('<!-- wp:pullquote -->\n<figure class="wp-block-pullquote">'
            f"<blockquote><p>{t}</p></blockquote></figure>\n<!-- /wp:pullquote -->")


def caixa(titulo, corpo, cor="#f5f7fb", borda="#008353"):
    """Callout. Grupo com fundo e barra lateral — quebra a parede de texto.

    A margem vai NO BLOCO, não num spacer ao lado: o tema zera margem de
    `wp-block-group`, e dois callouts seguidos encostam (defeito visto em P2).
    """
    return ('<!-- wp:group {"style":{"spacing":{"padding":{"top":"18px","right":"20px",'
            '"bottom":"18px","left":"20px"},"margin":{"top":"18px","bottom":"18px"}},'
            '"border":{"left":{"color":"' + borda +
            '","width":"4px"},"radius":"8px"},"color":{"background":"' + cor + '"}},'
            '"layout":{"type":"constrained"}} -->\n'
            f'<div class="wp-block-group has-background" style="border-left-color:{borda};'
            f"border-left-width:4px;border-radius:8px;background-color:{cor};"
            'margin-top:18px;margin-bottom:18px;padding:18px 20px 18px 20px">'
            f"<!-- wp:paragraph --><p><strong>{titulo}</strong></p><!-- /wp:paragraph -->"
            f"<!-- wp:paragraph --><p>{corpo}</p><!-- /wp:paragraph -->"
            "</div>\n<!-- /wp:group -->")


def sanfona(pergunta, resposta):
    """wp:details — a pergunta frequente que abre. Substitui o su_spoiler do tema antigo."""
    return ('<!-- wp:details {"style":{"spacing":{"margin":{"top":"10px","bottom":"10px"},'
            '"padding":{"top":"12px","right":"14px","bottom":"12px","left":"14px"}},'
            '"border":{"radius":"8px","width":"1px","color":"#e6eaf0"}}} -->\n'
            '<details class="wp-block-details has-border-color" '
            'style="border-color:#e6eaf0;border-width:1px;border-radius:8px;'
            'margin-top:10px;margin-bottom:10px;padding:12px 14px">'
            f"<summary>{pergunta}</summary>"
            f"<!-- wp:paragraph --><p>{resposta}</p><!-- /wp:paragraph -->"
            "</details>\n<!-- /wp:details -->")


def duas_colunas(esq, dir_):
    return ('<!-- wp:columns -->\n<div class="wp-block-columns">'
            f'<!-- wp:column --><div class="wp-block-column">{esq}</div><!-- /wp:column -->'
            f'<!-- wp:column --><div class="wp-block-column">{dir_}</div><!-- /wp:column -->'
            "</div>\n<!-- /wp:columns -->")


def imagem(mid, url, alt, legenda):
    return (f'<!-- wp:image {{"id":{mid},"sizeSlug":"large","linkDestination":"none"}} -->\n'
            f'<figure class="wp-block-image size-large">'
            f'<img src="{url}" alt="{alt}" class="wp-image-{mid}"/>'
            f"<figcaption class=\"wp-element-caption\">{legenda}</figcaption></figure>\n"
            "<!-- /wp:image -->")


def html(x):
    return f"<!-- wp:html -->\n{x}\n<!-- /wp:html -->"


def separador():
    return ('<!-- wp:separator {"opacity":"css"} -->\n'
            '<hr class="wp-block-separator has-css-opacity"/>\n<!-- /wp:separator -->')


# ─────────────────────────────────────────────────────────────────────────────
# Validador. Roda ANTES de publicar. Cada regra existe porque um defeito real
# chegou ao ar — a referência entre parênteses é o caso que a originou.
# ─────────────────────────────────────────────────────────────────────────────

import re as _re

# "abaixo de R$ 100" é comparação de valor, não direção. Só o uso posicional conta.
_DIRECIONAL = _re.compile(
    r"\b(?:abaixo|acima|ao lado|logo em seguida|a seguir)\b(?!\s+de\s+R\$|\s+de\s+\d)",
    _re.I)


def validar(conteudo: str) -> list[str]:
    """Devolve a lista de falhas. Lista vazia = pode publicar."""
    falhas = []

    # 1) Copy direcional no corpo. O injetor de anúncio insere entre parágrafos,
    #    então "responda abaixo" pode acabar apontando para um anúncio — indução
    #    de clique. A instrução tem que morar DENTRO do widget. (P3, 11/08/2026)
    corpo = _re.sub(r"<!-- wp:html -->.*?<!-- /wp:html -->", "", conteudo, flags=_re.S)
    for m in _re.finditer(r"<p\b[^>]*>(.*?)</p>", corpo, _re.S):
        texto = _re.sub(r"<[^>]+>", "", m.group(1))
        achado = _DIRECIONAL.search(texto)
        if achado:
            falhas.append(f'copy direcional "{achado.group(0)}" no corpo: "{texto.strip()[:70]}…"')

    # 1b) Parágrafo imediatamente antes de um widget. Mesmo sem a palavra
    #     "abaixo", um parágrafo que apresenta o widget vira legenda do anúncio
    #     quando o injetor insere entre os dois. Quem apresenta o widget é o
    #     próprio widget: ele tem título e chamada. (P1/P3, 11/08/2026)
    for m in _re.finditer(r"<!-- /wp:paragraph -->\s*<!-- wp:html -->", conteudo):
        trecho = conteudo[max(0, m.start() - 320):m.start()]
        ante = _re.findall(r"<p\b[^>]*>(.*?)</p>", trecho, _re.S)
        if ante:
            texto = _re.sub(r"<[^>]+>", "", ante[-1]).strip()
            falhas.append(f'parágrafo colado no widget: "{texto[:70]}…" — mover para dentro do widget')

    # 2) <p> dentro de wp:html. <p> vazio é removido pelo the_content e leva o id
    #    junto, matando o getElementById do widget. (os 3 widgets, 11/08/2026)
    for m in _re.finditer(r"<!-- wp:html -->(.*?)<!-- /wp:html -->", conteudo, _re.S):
        interior = _re.sub(r"<script>.*?</script>|<style>.*?</style>", "", m.group(1), flags=_re.S)
        n = len(_re.findall(r"<p\b", interior))
        if n:
            falhas.append(f"{n} <p> dentro de bloco wp:html — trocar por <div>")

    # 2b) Rótulo que promete um destino que o link não entrega. Se o CTA diz
    #     "Consultar no App FGTS" e leva para uma página nossa, isso é navegação
    #     enganosa — o mesmo defeito que condenamos na LP antiga, e passível de
    #     punição. O verbo tem que descrever o que a NOSSA página faz:
    #     "ver onde", "ver o passo a passo", "ver como". (widget P2, 11/08/2026)
    _ACAO_EXTERNA = _re.compile(
        r"^\s*(?:consultar|conferir|acessar|baixar|instalar|entrar|abrir|solicitar"
        r"|contratar|autorizar|simular|sacar|antecipar|pedir)\b", _re.I)
    _MENCAO_EXTERNA = _re.compile(r"\b(?:no App FGTS|no site da CAIXA|no gov\.br|no aplicativo)\b", _re.I)
    for m in _re.finditer(r'href="([^"]+)"[^>]*>(?:<strong>)?(.*?)(?:&raquo;|</strong>|</a>)', conteudo, _re.S):
        url, rot = m.group(1), _re.sub(r"<[^>]+>|&#x[0-9a-f]+;", "", m.group(2)).strip()
        interno = url.startswith("#") or "creditoup.com.br" in url
        if interno and _MENCAO_EXTERNA.search(rot) and _ACAO_EXTERNA.match(rot):
            falhas.append(f'CTA enganoso "{rot[:56]}" → destino interno. '
                          'Trocar o verbo por "ver onde/como/o passo a passo"')

    # 3) is-style-outline: o core zera o fundo e o tema herda texto branco.
    #    Botão fantasma, visível só no hover. (PR1, 11/08/2026)
    if "is-style-outline" in conteudo:
        falhas.append("is-style-outline presente — renderiza invisível neste tema")

    # 4) Blocos wp:buttons consecutivos sem spacer entre eles encostam: o core
    #    define margin:0 e o gap do flex só vale DENTRO de um bloco. (P1, 11/08/2026)
    seq = _re.findall(r"<!-- /wp:buttons -->\s*(<!-- wp:buttons)", conteudo)
    if seq:
        falhas.append(f"{len(seq)} par(es) de wp:buttons coladas — usar botoes() em vez de botao() repetido")

    # 5) Cor do botão tem que bater com o destino. Cor é wayfinding, não enfeite.
    for m in _re.finditer(r'href="([^"]+)"[^>]*style="[^"]*background-color:(#[0-9a-f]{6})', conteudo):
        url, cor = m.group(1), m.group(2).lower()
        esperada = COR.get(url if url.endswith("/") else url + "/")
        if esperada and cor != esperada.lower():
            falhas.append(f"botão para {url.split('/rec/')[-1]} com cor {cor}, esperada {esperada}")

    # 6) Blocos abertos e fechados têm que fechar a conta.
    ab = len(_re.findall(r"<!--\s+wp:", conteudo))
    fe = len(_re.findall(r"<!--\s+/wp:", conteudo))
    if ab != fe:
        falhas.append(f"blocos desbalanceados: {ab} aberturas, {fe} fechamentos")

    return falhas
