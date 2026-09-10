"""Tipografia resolvida por código — a letra nunca é gerada, é desenhada.

## De onde veio e o que foi consertado no caminho

Origem: `motor-imagem/positivo/backend/app/utils/render.py`, o kit tipográfico
PIL da VOLC — o único caminho de tipografia do acervo que roda sem navegador,
sem rede e sem credencial. Os três caminhos HTML da origem (prensa, godmode_render,
dace/render/html) exigem Google Chrome REAL instalado
(`prensa-poc/render.py:777`, `channel="chrome"`), o que é impossível no runtime
deste produto — não é pesado, é impossível.

⚠️ **O bug que veio junto, e que foi corrigido aqui.** A origem chama
`f.set_variation_by_axes([weight])` — UM valor — dentro de um `except: pass`.
A fonte que ESTE produto empacota, `bancada/fontes/Inter-Variable.ttf`, tem DOIS
eixos: `Optical size` (14–32) e `Weight` (100–900). Passar um único valor seta o
PRIMEIRO eixo, não o peso. Medido nesta fonte, com o kit da origem:

    getlength("ABERTAS") @ wght=100 → 437.000
    getlength("ABERTAS") @ wght=400 → 437.000
    getlength("ABERTAS") @ wght=900 → 437.000     ← idênticos

Isto é, toda a hierarquia (900 na headline, 500 no apoio) desapareceria e nada
levantaria exceção: o `except: pass` engoliria o erro e o recibo diria
"produziu". Com os dois eixos preenchidos na ordem certa, a mesma medição dá
434 → 460 → 492, que é a hierarquia existindo de fato.

`_variacao()` resolve o eixo pelo NOME e não pela posição, para que trocar a
fonte por outra com eixos em ordem diferente não reintroduza o defeito em
silêncio.

## O que este módulo NÃO faz

Não decide layout. Ele mede, quebra linha, ajusta escala e desenha; onde cada
bloco vive é decisão da direção de arte, que chega pronta. Um kit que também
escolhesse posição seria o template hardcoded voltando por outra porta.
"""
from __future__ import annotations

import functools
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

#: A fonte que este produto empacota. Variável, dois eixos.
CAMINHO_DA_FONTE = (
    Path(__file__).resolve().parents[1] / "bancada" / "fontes" / "Inter-Variable.ttf"
)


class FonteIndisponivel(RuntimeError):
    """Sem fonte real não há tipografia — e não há fallback.

    O PIL tem uma fonte bitmap embutida que produziria uma imagem parecida com
    tipografia sem ser tipografia. Cair nela faria a tela dizer "pronta" sobre
    uma peça que ninguém usaria, que é a pior falha possível aqui.
    """


def _eixos(fonte: ImageFont.FreeTypeFont) -> list[dict]:
    try:
        return fonte.get_variation_axes()
    except Exception:  # noqa: BLE001 — fonte estática não tem eixos, e tudo bem
        return []


def _variacao(fonte: ImageFont.FreeTypeFont, peso: int) -> None:
    """Aplica o peso resolvendo o eixo pelo NOME, nunca pela posição.

    Uma fonte de eixo único aceita `[peso]`; uma de dois eixos precisa de um
    valor por eixo, na ordem em que a fonte os declara. Resolver por nome é o
    que faz este módulo sobreviver a uma troca de fonte.
    """
    eixos = _eixos(fonte)
    if not eixos:
        return
    valores: list[float] = []
    for eixo in eixos:
        nome = eixo.get("name")
        if isinstance(nome, bytes):
            nome = nome.decode("utf-8", "replace")
        if (nome or "").strip().casefold() == "weight":
            valores.append(max(eixo["minimum"], min(eixo["maximum"], peso)))
        else:
            valores.append(eixo.get("default", eixo["minimum"]))
    fonte.set_variation_by_axes(valores)


@functools.lru_cache(maxsize=256)
def fonte(tamanho: int, peso: int = 700) -> ImageFont.FreeTypeFont:
    """A fonte no tamanho e peso pedidos. Falha fechada quando o arquivo falta."""
    if not CAMINHO_DA_FONTE.exists():
        raise FonteIndisponivel(
            f"fonte tipográfica ausente em {CAMINHO_DA_FONTE}; "
            "sem ela a composição determinística não roda"
        )
    resolvida = ImageFont.truetype(str(CAMINHO_DA_FONTE), tamanho)
    _variacao(resolvida, peso)
    return resolvida


def quebrar(
    desenho: ImageDraw.ImageDraw,
    texto: str,
    fnt: ImageFont.FreeTypeFont,
    largura_max: int,
) -> list[str]:
    """Quebra gulosa por palavra, respeitando quebras explícitas do texto."""
    linhas: list[str] = []
    for paragrafo in texto.split("\n"):
        palavras = paragrafo.split()
        if not palavras:
            linhas.append("")
            continue
        atual = palavras[0]
        for palavra in palavras[1:]:
            tentativa = f"{atual} {palavra}"
            if desenho.textlength(tentativa, font=fnt) <= largura_max:
                atual = tentativa
            else:
                linhas.append(atual)
                atual = palavra
        linhas.append(atual)
    return linhas


def ajustar(
    desenho: ImageDraw.ImageDraw,
    texto: str,
    largura_max: int,
    tamanho_inicial: int,
    peso: int,
    tamanho_minimo: int = 14,
    caixa_alta: bool = False,
) -> tuple[ImageFont.FreeTypeFont, str]:
    """O maior tamanho cuja PALAVRA MAIS LONGA ainda cabe na largura.

    Mede a palavra e não a linha de propósito: uma linha sempre pode ser
    quebrada, uma palavra não. É a palavra que estoura a caixa.
    """
    conteudo = texto.upper() if caixa_alta else texto
    tamanho = tamanho_inicial
    while tamanho > tamanho_minimo:
        candidata = fonte(tamanho, peso)
        maior = max(
            (desenho.textlength(p, font=candidata) for p in conteudo.split()),
            default=0,
        )
        if maior <= largura_max:
            return candidata, conteudo
        tamanho -= 2
    return fonte(tamanho_minimo, peso), conteudo


def desenhar_linhas(
    desenho: ImageDraw.ImageDraw,
    linhas: list[str],
    fnt: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    cor,
    entrelinha: float = 1.18,
) -> int:
    """Desenha o bloco e devolve o y logo abaixo dele."""
    ascendente, descendente = fnt.getmetrics()
    altura_da_linha = int((ascendente + descendente) * entrelinha)
    for linha in linhas:
        desenho.text((x, y), linha, font=fnt, fill=cor)
        y += altura_da_linha
    return y


def painel(
    tamanho: tuple[int, int], raio: int, cor, opacidade: int = 255
) -> Image.Image:
    """Retângulo de cantos arredondados — a base de botão, cartela e selo."""
    camada = Image.new("RGBA", tamanho, (0, 0, 0, 0))
    ImageDraw.Draw(camada).rounded_rectangle(
        [(0, 0), (tamanho[0] - 1, tamanho[1] - 1)],
        radius=raio,
        fill=(*cor[:3], opacidade),
    )
    return camada


def marca_de_selecao(tamanho: int, cor) -> Image.Image:
    """O check do checklist, desenhado — não um glifo de fonte que pode faltar."""
    camada = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(camada)
    espessura = max(2, tamanho // 8)
    desenho.line(
        [
            (tamanho * 0.20, tamanho * 0.52),
            (tamanho * 0.42, tamanho * 0.74),
            (tamanho * 0.80, tamanho * 0.26),
        ],
        fill=cor,
        width=espessura,
        joint="curve",
    )
    return camada


def contraste(frente, fundo) -> float:
    """Razão de contraste WCAG entre duas cores RGB.

    Linearizada por canal ANTES de ponderar, que é a única forma que entra na
    fórmula — a versão gama-codificada serve para o olho ler detalhe, não para
    medir contraste, e confundir as duas é o erro clássico aqui.
    """

    def luminancia(cor) -> float:
        canais = []
        for valor in cor[:3]:
            proporcao = valor / 255.0
            canais.append(
                proporcao / 12.92
                if proporcao <= 0.04045
                else ((proporcao + 0.055) / 1.055) ** 2.4
            )
        return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]

    clara, escura = sorted((luminancia(frente), luminancia(fundo)), reverse=True)
    return (clara + 0.05) / (escura + 0.05)
