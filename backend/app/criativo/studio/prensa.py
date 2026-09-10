"""PRENSA — a tipografia entra por código, na zona que o modelo abriu.

## O que este módulo faz, em uma frase

Recebe a CENA que o provider gerou sem texto nenhum, MEDE onde a área calma
realmente ficou, CONFERE se ela caiu onde o plano pediu, e então desenha a
tipografia com fonte real e contraste medido.

## Por que medir antes de desenhar

Porque provisionar espaço no prompt é hipótese, não garantia. O plano pede
"queda de luz no terço inferior" e o modelo obedece na maioria das vezes — mas
"na maioria das vezes" é o que produz a peça com a headline em cima do rosto,
e ninguém descobre até olhar. Medir transforma a hipótese em fato verificável:
`planos.conferir` compara a zona achada com a pedida e devolve um veredito com
evidência, e quem chama decide o que fazer com a desobediência.

## Como a zona é medida, e por que assim

Por VARIÂNCIA LOCAL em tons de cinza, em blocos. Uma área boa para texto é uma
área CALMA: pouco detalhe, pouco contorno, pouco contraste interno. Detectar
"escuro" seria errado — `faixa_inferior_clara` pede uma superfície branca —, e
detectar borda por Canny traria dependência que este runtime não tem. Variância
por bloco é a medida certa e cabe em numpy puro.

⚠️ A varredura procura o maior RETÂNGULO calmo alinhado ao plano pedido, e não a
maior região calma do quadro. A diferença importa: um céu liso no topo é calmo,
e se o plano pediu a faixa inferior, achar o céu e declarar obediência seria
mentir com número. A busca é ancorada na região pedida; a contenção mede o
quanto do que se achou coube ali.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw

from . import planos, tipografia


@dataclass(frozen=True)
class Zona:
    """Uma caixa em pixels do canvas final, com a prova de que ela é usável.

    `fracao_calma` é a fração da REGIÃO PEDIDA que a medição achou calma, e é
    ela que julga a obediência — não a contenção.

    ⚠️ Contenção não serve a este medidor, e a razão é geométrica: a varredura é
    confinada à região que o plano pediu, então a faixa achada está contida
    nela POR CONSTRUÇÃO e a contenção dá ~1,0 sempre. Medi isso contra uma peça
    que é tarja e texto de ponta a ponta e o portão aprovou com 1,000. A
    contenção continua valendo em `planos.conferir`, onde a zona vem de uma
    medição livre; aqui a pergunta certa é outra — a região pedida ficou mesmo
    limpa?
    """

    x: int
    y: int
    w: int
    h: int
    fracao_calma: float = 0.0

    def como_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass(frozen=True)
class Impressa:
    """O resultado: os bytes finais e a prova de como se chegou neles."""

    conteudo: bytes
    zona: dict[str, int]
    veredito: dict
    tipografia: dict


def medir_zona_calma(
    imagem: Image.Image, regiao_pedida: tuple[float, ...], bloco: int = 24
) -> Zona:
    """Acha a maior faixa horizontal calma DENTRO da região que o plano pediu.

    Faixa horizontal e não retângulo livre porque é isso que a tipografia usa:
    linhas de texto ocupam a largura e crescem para baixo. Procurar um retângulo
    arbitrário devolveria caixas altas e estreitas onde nenhuma headline cabe.
    """
    largura, altura = imagem.size
    x0 = int(regiao_pedida[0] * largura)
    y0 = int(regiao_pedida[1] * altura)
    x1 = int(regiao_pedida[2] * largura)
    y1 = int(regiao_pedida[3] * altura)

    cinza = imagem.convert("L")
    # Desvio-padrão por bloco, calculado sem numpy: PIL já sabe reduzir, e a
    # diferença entre a média dos quadrados e o quadrado da média é a variância.
    linhas_calmas: list[bool] = []
    for topo in range(y0, y1, bloco):
        base = min(topo + bloco, y1)
        if base - topo < 4:
            continue
        faixa = cinza.crop((x0, topo, x1, base))
        estatistica = faixa.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
        quadrados = faixa.point(lambda v: (v * v) // 255)
        media_dos_quadrados = quadrados.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
        variancia = max(0.0, media_dos_quadrados * 255.0 - estatistica * estatistica)
        linhas_calmas.append(variancia**0.5 <= _LIMIAR_DE_CALMA)

    if not linhas_calmas:
        return Zona(x0, y0, max(1, x1 - x0), max(1, y1 - y0), 0.0)

    melhor_inicio = melhor_tamanho = atual_inicio = atual_tamanho = 0
    for indice, calma in enumerate(linhas_calmas):
        if calma:
            if atual_tamanho == 0:
                atual_inicio = indice
            atual_tamanho += 1
            if atual_tamanho > melhor_tamanho:
                melhor_tamanho, melhor_inicio = atual_tamanho, atual_inicio
        else:
            atual_tamanho = 0

    fracao = melhor_tamanho / len(linhas_calmas)
    if melhor_tamanho == 0:
        # Nada calmo onde o plano pediu. Devolver a região inteira com fração
        # zero faz a desobediência aparecer como número em vez de exceção.
        return Zona(x0, y0, max(1, x1 - x0), max(1, y1 - y0), 0.0)

    topo = y0 + melhor_inicio * bloco
    # A altura é limitada por y1: `melhor_tamanho * bloco` pode ultrapassar o
    # fim da região quando o último bloco foi recortado na varredura.
    altura_da_faixa = min(melhor_tamanho * bloco, y1 - topo)
    return Zona(x0, topo, max(1, x1 - x0), max(1, altura_da_faixa), round(fracao, 3))


#: Desvio-padrão de luminância abaixo do qual um bloco é "calmo".
#:
#: 18 saiu de calibragem contra as cenas que este produto gera: céu, parede
#: pintada, mesa lisa e sombra profunda ficam abaixo; rosto, tecido com dobra,
#: folhagem e texto ficam acima. Não é constante universal — é o piso desta
#: família de imagens, e mover isto exige recalibrar contra um lote real.
_LIMIAR_DE_CALMA = 18.0

#: Quanto da região pedida precisa estar calma para a peça ser aceitável.
#:
#: 0,45 porque a região de um plano é generosa de propósito (a faixa inferior
#: pede 36% da altura) e o texto usa uma parte dela. Exigir a região inteira
#: reprovaria cena boa; aceitar um quinto aprovaria cena onde o texto vai cair
#: em cima do sujeito.
MINIMO_DE_CALMA = 0.45

#: Quantas reduções de escala antes de desistir. 8 passos de 0,88 chegam a ~36%
#: do corpo inicial, o que já é ilegível em feed — insistir além disso trocaria
#: uma falha honesta por uma peça que ninguém consegue ler.
_TENTATIVAS_DE_AJUSTE = 8


class TextoNaoCabe(ValueError):
    """A copy não cabe na zona nem no menor corpo aceitável."""


def _montar_pilha(desenho, textos: dict[str, str], caixa_largura: int,
                  altura: int, escala: float) -> tuple[list[tuple], int]:
    """Mede a pilha inteira sem desenhar. Devolve o plano e a altura total."""
    pilha: list[tuple] = []
    total = 0

    headline = (textos.get("headline") or "").strip()
    if headline:
        fnt, conteudo = tipografia.ajustar(
            desenho, headline, caixa_largura,
            tamanho_inicial=max(18, int(altura * 0.075 * escala)), peso=900,
        )
        linhas = tipografia.quebrar(desenho, conteudo, fnt, caixa_largura)
        ascendente, descendente = fnt.getmetrics()
        alto = int((ascendente + descendente) * 1.06) * len(linhas)
        pilha.append(("headline", fnt, linhas, 1.06, 0))
        total += alto

    complemento = (textos.get("complemento") or "").strip()
    if complemento:
        fnt = tipografia.fonte(max(12, int(altura * 0.026 * escala)), 500)
        linhas = tipografia.quebrar(desenho, complemento, fnt, caixa_largura)
        ascendente, descendente = fnt.getmetrics()
        respiro = int(altura * 0.012 * escala)
        pilha.append(("complemento", fnt, linhas, 1.22, respiro))
        total += respiro + int((ascendente + descendente) * 1.22) * len(linhas)

    cta = (textos.get("cta") or "").strip()
    if cta:
        fnt = tipografia.fonte(max(12, int(altura * 0.028 * escala)), 700)
        ascendente, descendente = fnt.getmetrics()
        respiro = int(altura * 0.018 * escala)
        pilha.append(("cta", fnt, [cta], 1.0, respiro))
        total += respiro + ascendente + descendente + int(altura * 0.014 * escala) * 2

    return pilha, total


def imprimir(
    *,
    cena: bytes,
    textos: dict[str, str],
    plano: dict,
    tinta: tuple[int, int, int] | None = None,
    acento: tuple[int, int, int] = (255, 203, 0),
    margem_fracao: float = 0.07,
) -> Impressa:
    """Desenha headline, complemento e CTA na zona calma da cena.

    `tinta` e `acento` chegam de fora porque cor é decisão de direção de arte, e
    um default aqui viraria a paleta de um cliente virando lei — o defeito que o
    motor de origem tem em `photo_ad_composer.py:46-52` e em `verify.py:114`.
    """
    imagem = Image.open(io.BytesIO(cena)).convert("RGB")
    largura, altura = imagem.size

    zona = medir_zona_calma(imagem, tuple(plano["zona"]))

    # ⚠️ A tinta sai de contraste MEDIDO contra o fundo real da zona, e não de
    # um default. Medi o custo do default: o plano `faixa_inferior_clara` pede
    # uma superfície branca de propósito, e a tinta branca fixa escreveu texto
    # claro sobre mármore claro — legível no monitor grande, invisível na
    # miniatura do feed, que é onde a peça vive. O CTA já escolhia sua tinta
    # assim; o corpo do texto não, e a incoerência era o defeito.
    if tinta is None:
        recorte = imagem.crop((zona.x, zona.y, zona.x + zona.w, zona.y + zona.h))
        fundo = recorte.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
        escuro, claro = (17, 17, 17), (255, 255, 255)
        tinta = escuro if tipografia.contraste(escuro, fundo) >= tipografia.contraste(claro, fundo) else claro
    veredito = {
        **planos.conferir(plano, zona.como_dict(), {"w": largura, "h": altura}),
        "fracao_calma": zona.fracao_calma,
        "obedeceu": zona.fracao_calma >= MINIMO_DE_CALMA,
        "minimo_calma": MINIMO_DE_CALMA,
    }

    margem = int(largura * margem_fracao)
    caixa_x = zona.x + margem
    caixa_largura = max(80, zona.w - margem * 2)
    desenho = ImageDraw.Draw(imagem)

    # ⚠️ DUAS PASSADAS, e a primeira não desenha nada.
    #
    # A pilha inteira é medida antes de qualquer pixel e a escala cai até caber
    # na zona. Sem isto o texto simplesmente transborda: medi a versão de uma
    # passada e a headline terminava 29 px abaixo do fim da zona, com o CTA
    # caindo 23 px FORA da imagem. Um render que corta o CTA é pior que um
    # render que falha, porque parece pronto.
    escala = 1.0
    plano_de_desenho: list[tuple] = []
    for _ in range(_TENTATIVAS_DE_AJUSTE):
        plano_de_desenho, altura_usada = _montar_pilha(
            desenho, textos, caixa_largura, altura, escala
        )
        if altura_usada <= zona.h - margem:
            break
        escala *= 0.88
    else:
        # Nem no menor tamanho coube. Falhar aqui é honesto: a alternativa é
        # entregar peça com texto cortado e recibo dizendo "pronta".
        raise TextoNaoCabe(
            f"a copy não cabe na zona de {zona.w}x{zona.h}px nem no menor corpo; "
            "reduza a densidade da peça ou escolha um plano com zona maior"
        )

    medidas: dict[str, dict] = {}
    y = zona.y + margem // 2
    for papel, fnt, linhas, entrelinha, respiro in plano_de_desenho:
        y += respiro
        if papel == "cta":
            texto_do_cta = linhas[0]
            largura_texto = int(desenho.textlength(texto_do_cta, font=fnt))
            ascendente, descendente = fnt.getmetrics()
            respiro_x = int(altura * 0.022 * escala)
            respiro_y = int(altura * 0.014 * escala)
            botao = tipografia.painel(
                (largura_texto + respiro_x * 2, ascendente + descendente + respiro_y * 2),
                raio=int(altura * 0.008), cor=acento,
            )
            imagem.paste(botao, (caixa_x, y), botao)
            # A tinta do CTA é decidida por CONTRASTE MEDIDO contra o acento e
            # não por convenção: acento claro com texto branco por cima é o
            # jeito clássico de perder o botão inteiro em miniatura.
            escuro, claro = (17, 17, 17), (255, 255, 255)
            tinta_cta = escuro if tipografia.contraste(escuro, acento) >= tipografia.contraste(claro, acento) else claro
            desenho.text((caixa_x + respiro_x, y + respiro_y), texto_do_cta, font=fnt, fill=tinta_cta)
            medidas[papel] = {
                "tamanho_px": fnt.size, "peso": 700, "y": y,
                "contraste_no_botao": round(tipografia.contraste(tinta_cta, acento), 2),
            }
            y += ascendente + descendente + respiro_y * 2
        else:
            antes = y
            y = tipografia.desenhar_linhas(desenho, linhas, fnt, caixa_x, y, tinta, entrelinha)
            medidas[papel] = {
                "tamanho_px": fnt.size, "linhas": len(linhas),
                "peso": 900 if papel == "headline" else 500, "y": antes,
            }

    veredito["escala_aplicada"] = round(escala, 3)
    veredito["tinta"] = list(tinta)
    veredito["altura_da_pilha"] = y - (zona.y + margem // 2)

    saida = io.BytesIO()
    imagem.save(saida, format="PNG", optimize=False)
    return Impressa(
        conteudo=saida.getvalue(),
        zona=zona.como_dict(),
        veredito=veredito,
        tipografia=medidas,
    )
