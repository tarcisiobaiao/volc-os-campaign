#!/usr/bin/env python3
"""PRENSA POC — composicao.py: o engine PEDE a composição e depois CONFERE.

Descoberta medida na Fase 0: foto cujo prompt provisionou espaço para texto tem
dinâmica de quietude 52,3x (news); foto cujo prompt não provisionou tem 1,96x
(kintsugi medium, reprovada por texto encostando na estátua). Provisionar
funciona — mas provisionar não é confiar.

Duas regras que fazem isso ser engenharia e não torcida:

1. NUNCA pedir marcador visível. Nada de "deixe um retângulo", "barra escura",
   "área cinza": isso vira sujeira na foto e devolve ao modelo o pixel que o
   engine controla. Pede-se COMPOSIÇÃO FOTOGRÁFICA — queda de luz, profundidade,
   névoa, espaço negativo — que é o que um diretor de fotografia faria.

2. O pedido é uma HIPÓTESE, verificada depois. O plano declara a zona esperada;
   `analisa_foto` mede a zona real; `confere()` compara. Modelo que não obedeceu
   é detectado, e a peça é recusada ou a foto regerada — nunca publicada no
   escuro.

A escolha do plano é ALEATÓRIA POR SEED: variedade no feed (nem todo post com
texto no mesmo canto) sem perder reprodutibilidade — mesma seed, mesmo plano.
"""
from __future__ import annotations

# Cada plano: como pedir (linguagem de fotografia) + onde esperar a zona,
# em fração do canvas (x0, y0, x1, y1).
PLANOS = {
    "coluna_esquerda": {
        "pedido": ("Compose with the subject anchored in the RIGHT third of the frame, "
                   "turned slightly inward. The entire LEFT side of the frame falls away "
                   "into deep atmospheric emptiness — unlit, uncluttered, no objects and "
                   "no detail, only depth."),
        "zona": (0.05, 0.20, 0.52, 0.92),
    },
    "coluna_direita": {
        "pedido": ("Compose with the subject anchored in the LEFT third of the frame, "
                   "turned slightly inward. The entire RIGHT side of the frame falls away "
                   "into deep atmospheric emptiness — unlit, uncluttered, no objects and "
                   "no detail, only depth."),
        "zona": (0.48, 0.20, 0.95, 0.92),
    },
    "faixa_inferior": {
        "pedido": ("Compose with the subject in the UPPER half of the frame. A single "
                   "light source rakes across it and rolls off steeply downward, so the "
                   "LOWER 40 percent of the frame sits in deep clean shadow — a plain "
                   "unlit surface with no pattern, no objects, nothing to read."),
        "zona": (0.05, 0.58, 0.95, 0.94),
    },
    "faixa_superior": {
        "pedido": ("Compose from a low angle with the subject occupying the LOWER half of "
                   "the frame. Above it opens a vast unbroken expanse of empty sky or void, "
                   "holding one even quiet tone across the UPPER 40 percent of the frame."),
        "zona": (0.05, 0.06, 0.95, 0.42),
    },
    "faixa_inferior_clara": {
        "pedido": ("Compose with the subject in the UPPER half of the frame, resting on a "
                   "bright surface — pale marble, white tile or a light linen cloth — that "
                   "extends toward the camera and fills the LOWER 40 percent of the frame "
                   "as an even, softly lit, completely empty expanse: no objects, no "
                   "pattern, no crumbs, no shadows crossing it."),
        "zona": (0.05, 0.58, 0.95, 0.94),
    },
    "diagonal_superior_direita": {
        "pedido": ("Compose on a diagonal: the subject rises from the LOWER-LEFT corner, "
                   "and the UPPER-RIGHT quadrant of the frame opens into empty atmosphere "
                   "with no detail — a quiet field of depth and haze."),
        "zona": (0.45, 0.06, 0.95, 0.48),
    },
}

def escolhe(seed: int) -> tuple[str, dict]:
    """Plano deterministicamente derivado da seed: variedade reprodutível.
    Random de verdade quebraria o determinismo, que é a lei nº 1 do motor."""
    nomes = sorted(PLANOS)
    nome = nomes[seed % len(nomes)]
    return nome, PLANOS[nome]

def sobreposicao(esperada: tuple, achada: tuple) -> float:
    """Fração da zona ACHADA que cai dentro da região pedida (0..1).

    Medir pelo denominador errado (quanto da região pedida foi coberta) reprova
    obediência real: a zona achada tem tamanho de bloco de texto e nunca cobre
    uma região de meia página. A pergunta certa é CONTENÇÃO — o texto caiu onde
    o plano mandou? — não cobertura."""
    ix = max(0.0, min(esperada[2], achada[2]) - max(esperada[0], achada[0]))
    iy = max(0.0, min(esperada[3], achada[3]) - max(esperada[1], achada[1]))
    area_achada = max(1e-9, (achada[2] - achada[0]) * (achada[3] - achada[1]))
    return (ix * iy) / area_achada

def confere(plano: dict, zona_real: dict, canvas: dict,
            minimo: float = 0.35) -> dict:
    """O modelo obedeceu? Compara a zona pedida com a que a medição achou.
    Sem esta conferência, provisionar espaço vira fé — e fé não é gate."""
    W, H = canvas["w"], canvas["h"]
    achada = (zona_real["x"] / W, zona_real["y"] / H,
              (zona_real["x"] + zona_real["w"]) / W,
              (zona_real["y"] + zona_real["h"]) / H)
    cob = sobreposicao(plano["zona"], achada)
    return {"obedeceu": cob >= minimo, "cobertura": round(cob, 3),
            "zona_pedida": plano["zona"], "zona_achada": [round(v, 3) for v in achada]}
