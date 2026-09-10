"""Planos de composição: pedir a LUZ que abre a zona, e conferir depois.

## De onde isto veio, e por que foi portado em vez de reinventado

Origem: `motor-imagem/compartilhado/prensa-poc/composicao.py`, o motor PRENSA da
VOLC. Está aqui reescrito para o vocabulário deste produto, não copiado: os
nomes dos planos, os textos de pedido e a doutrina de conferência são de lá; o
acoplamento com `rota_de_texto` e `CreativeSpec` é daqui.

A descoberta que justifica o módulo foi MEDIDA na origem, não deduzida: foto
cujo prompt provisionou espaço para o texto teve dinâmica de quietude 52,3x na
zona; foto cujo prompt não provisionou teve 1,96x — e o texto encostou no
sujeito. Provisionar funciona.

## As duas leis, e por que o compilador daqui violava as duas

1. **Nunca pedir marcador visível.** Nada de "deixe um retângulo", "barra
   escura", "área reservada": isso vira sujeira desenhada na foto e devolve ao
   modelo o pixel que o código controla. Pede-se COMPOSIÇÃO FOTOGRÁFICA — queda
   de luz, profundidade, névoa, espaço negativo —, que é o que um diretor de
   fotografia pediria.

   ⚠️ `spec_visual` pedia, até 10/09/2026, "use uma área limpa e contínua para
   renderizar o texto aprovado". É exatamente o pedido errado, na formulação
   errada: nomeia a área em vez da luz, e ainda por cima pedia o texto junto.

2. **O pedido é HIPÓTESE, verificada depois.** O plano declara a zona esperada;
   a medição acha a zona real; `conferir()` compara. Modelo que não obedeceu é
   detectado — e a peça é recusada ou regerada, nunca publicada no escuro.
   Provisionar sem conferir é fé, e fé não é portão.

## Por que os pedidos estão em inglês

Porque são assim na origem, e a origem tem 9/9 peças aprovadas em gate de pixel
com eles. Traduzir seria inventar uma variável nova numa formulação já provada.
O texto que vai à ARTE continua sendo português — estes pedidos descrevem a
fotografia, e não aparecem em lugar nenhum da peça.
"""
from __future__ import annotations

#: Cada plano: como PEDIR (linguagem de fotografia) e ONDE esperar a zona,
#: em fração do canvas final `(x0, y0, x1, y1)`.
PLANOS: dict[str, dict] = {
    "coluna_esquerda": {
        "pedido": (
            "Compose with the subject anchored in the RIGHT third of the frame, "
            "turned slightly inward. The entire LEFT side of the frame falls away "
            "into deep atmospheric emptiness — unlit, uncluttered, no objects and "
            "no detail, only depth."
        ),
        "zona": (0.05, 0.20, 0.52, 0.92),
    },
    "coluna_direita": {
        "pedido": (
            "Compose with the subject anchored in the LEFT third of the frame, "
            "turned slightly inward. The entire RIGHT side of the frame falls away "
            "into deep atmospheric emptiness — unlit, uncluttered, no objects and "
            "no detail, only depth."
        ),
        "zona": (0.48, 0.20, 0.95, 0.92),
    },
    "faixa_inferior": {
        "pedido": (
            "Compose with the subject in the UPPER half of the frame. A single "
            "light source rakes across it and rolls off steeply downward, so the "
            "LOWER 40 percent of the frame sits in deep clean shadow — a plain "
            "unlit surface with no pattern, no objects, nothing to read."
        ),
        "zona": (0.05, 0.58, 0.95, 0.94),
    },
    "faixa_inferior_clara": {
        "pedido": (
            "Compose with the subject in the UPPER half of the frame, resting on a "
            "bright surface — pale marble, white tile or a light linen cloth — that "
            "extends toward the camera and fills the LOWER 40 percent of the frame "
            "as an even, softly lit, completely empty expanse: no objects, no "
            "pattern, no crumbs, no shadows crossing it."
        ),
        "zona": (0.05, 0.58, 0.95, 0.94),
    },
    "faixa_superior": {
        "pedido": (
            "Compose from a low angle with the subject occupying the LOWER half of "
            "the frame. Above it opens a vast unbroken expanse of empty sky or void, "
            "holding one even quiet tone across the UPPER 40 percent of the frame."
        ),
        "zona": (0.05, 0.06, 0.95, 0.42),
    },
    "diagonal_superior_direita": {
        "pedido": (
            "Compose on a diagonal: the subject rises from the LOWER-LEFT corner, "
            "and the UPPER-RIGHT quadrant of the frame opens into empty atmosphere "
            "with no detail — a quiet field of depth and haze."
        ),
        "zona": (0.45, 0.06, 0.95, 0.48),
    },
}

#: Que planos servem a cada arquitetura de texto já declarada pela peça.
#:
#: `integrado_na_cena` e `tipografia_protagonista` estão FORA de propósito: na
#: primeira a letra encosta na cena por decisão de arte, e na segunda a
#: tipografia É a imagem. Reservar zona nas duas seria contradizer a rota que o
#: estrategista escolheu — o plano serve à direção, não o contrário.
PLANOS_POR_ROTA: dict[str, tuple[str, ...]] = {
    "campo_cromatico": ("faixa_superior", "faixa_inferior", "coluna_esquerda", "coluna_direita"),
    "rodape_limpo": ("faixa_inferior", "faixa_inferior_clara"),
}


class PlanoDesconhecido(KeyError):
    pass


def planos_de(rota_de_texto: str | None) -> tuple[str, ...]:
    """Os planos compatíveis com uma arquitetura de texto. Vazio = não reserva."""
    return PLANOS_POR_ROTA.get(rota_de_texto or "", ())


def escolher(rota_de_texto: str | None, semente: int) -> tuple[str, dict] | None:
    """Escolhe um plano de forma determinística a partir de uma semente.

    Determinístico e não aleatório porque a mesma peça precisa produzir o mesmo
    pedido em toda execução — é o que torna o replay possível e o recibo
    verdadeiro. A semente varia entre peças do lote para que o texto não caia
    sempre no mesmo canto, que é o defeito que um plano fixo produziria.
    """
    candidatos = planos_de(rota_de_texto)
    if not candidatos:
        return None
    nome = candidatos[semente % len(candidatos)]
    return nome, PLANOS[nome]


def contencao(esperada: tuple[float, ...], achada: tuple[float, ...]) -> float:
    """Fração da zona ACHADA que caiu dentro da região pedida (0..1).

    ⚠️ O denominador é a zona ACHADA, e essa escolha é a diferença entre um
    portão que funciona e um que reprova tudo. Medir cobertura — quanto da
    região pedida foi ocupada — reprovaria obediência real: um bloco de texto
    tem tamanho de bloco de texto e nunca cobre meia página. A pergunta certa é
    contenção: o espaço livre caiu ONDE o plano mandou?
    """
    ix = max(0.0, min(esperada[2], achada[2]) - max(esperada[0], achada[0]))
    iy = max(0.0, min(esperada[3], achada[3]) - max(esperada[1], achada[1]))
    area_achada = max(1e-9, (achada[2] - achada[0]) * (achada[3] - achada[1]))
    return (ix * iy) / area_achada


def conferir(
    plano: dict, zona_real: dict, canvas: dict, minimo: float = 0.35
) -> dict:
    """O modelo obedeceu ao plano? Devolve o veredito, sempre com a evidência.

    `zona_real` vem em pixels (`x`, `y`, `w`, `h`) porque é o que uma medição de
    imagem produz; a normalização acontece aqui para que o plano continue
    expresso em frações e sirva a qualquer canvas.
    """
    largura, altura = canvas["w"], canvas["h"]
    achada = (
        zona_real["x"] / largura,
        zona_real["y"] / altura,
        (zona_real["x"] + zona_real["w"]) / largura,
        (zona_real["y"] + zona_real["h"]) / altura,
    )
    medida = contencao(tuple(plano["zona"]), achada)
    return {
        "obedeceu": medida >= minimo,
        "contencao": round(medida, 3),
        "minimo": minimo,
        "zona_pedida": list(plano["zona"]),
        "zona_achada": [round(v, 3) for v in achada],
    }
