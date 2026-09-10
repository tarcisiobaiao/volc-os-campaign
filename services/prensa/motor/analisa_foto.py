#!/usr/bin/env python3
"""PRENSA POC — analisa_foto.py: descobre ONDE o texto deve entrar numa foto.

É o corte ESPACIAL que a auditoria apontou como ausente no dace (existe no
positivo como plan_split/PhotoAnalyzer): em vez de assumir "texto embaixo com
fade escuro", o engine MEDE a imagem e escolhe a região.

O que ele mede, tudo com numpy+PIL, determinístico, milissegundos:

  detalhe    magnitude do gradiente — tipografia sobre textura é ilegível
  planura    desvio da luminância na janela — fundo que oscila cansa a leitura
  polaridade distância do cinza médio — zona clara OU escura serve; cinza médio
             não serve para nenhuma cor de texto
  foco       centróide da energia de detalhe = onde está o sujeito; o texto
             não pode cobri-lo (regra de composição, não de contraste)

Emite a zona vencedora + a decisão de cor do texto + o selo MÍNIMO necessário
naquela zona (não um fade global). Se nenhuma zona serve, devolve None e o
chamador decide — fail-closed, nunca "coloca em cima e torce".
"""
from __future__ import annotations
import json, sys
from pathlib import Path

import numpy as np
from PIL import Image

AQUI = Path(__file__).parent
ESCALA = 8  # análise em 1/8 da resolução: 15x mais rápido, mesma decisão

def _lum_relativa(c8: float) -> float:
    c = c8 / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

def contraste(a8: float, b8: float) -> float:
    la, lb = _lum_relativa(a8), _lum_relativa(b8)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

def _faixas(y0: int, x0: int, y1: int, x1: int):
    """Terços verticais e horizontais da zona — o sujeito costuma entrar por
    UMA borda, e é essa faixa que precisa acusar."""
    ty, tx = (y1 - y0) // 3, (x1 - x0) // 3
    for i in range(3):
        yield (y0, x0 + i * tx, y1, x0 + (i + 1) * tx if i < 2 else x1)
        yield (y0 + i * ty, x0, y0 + (i + 1) * ty if i < 2 else y1, x1)

def _integral(m: np.ndarray) -> np.ndarray:
    return np.pad(m.cumsum(0).cumsum(1), ((1, 0), (1, 0)))

def _soma(ii: np.ndarray, y0: int, x0: int, y1: int, x1: int) -> float:
    return float(ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0])

_LUT = np.array([(c / 255.0) / 12.92 if c / 255.0 <= 0.04045
                 else (((c / 255.0) + 0.055) / 1.055) ** 2.4 for c in range(256)])

def analisa(caminho: str | Path, canvas: dict, safe: dict,
            alvo_contraste: float = 4.5) -> dict:
    from PIL import ImageOps
    im = Image.open(AQUI / caminho)
    im = ImageOps.exif_transpose(im)   # foto com EXIF girado seria medida deitada
    if im.mode in ("RGBA", "LA", "P"):
        fundo = Image.new("RGBA", im.size, (0, 0, 0, 255))
        im = Image.alpha_composite(fundo, im.convert("RGBA"))
    im = im.convert("RGB")
    W, H = canvas["w"], canvas["h"]
    im = im.resize((W, H), Image.LANCZOS) if im.size != (W, H) else im
    # redução por FATOR INTEIRO (média de área exata). LANCZOS introduz ringing,
    # e ringing vira BORDA FALSA — justamente a grandeza que este módulo mede.
    im = im.reduce(ESCALA)
    a8 = np.asarray(im)
    a = a8.astype(np.float32)

    # DUAS luminâncias, cada uma no seu papel — misturá-las é o erro clássico:
    #  · gama-codificada → ESTRUTURA (gradiente, desvio): é nela que o olho lê detalhe
    #  · linearizada por CANAL → CONTRASTE: só ela vale em fórmula WCAG.
    # Calcular luma no gama e linearizar depois (o que este arquivo fazia) chega a
    # divergir 12:1 vs 4:1 em cor saturada, SEMPRE otimista. Mesma ordem do
    # pixel_gates.py do dace, senão os dois módulos brigam.
    L = 0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]
    Yrel = (0.2126 * _LUT[a8[:, :, 0]] + 0.7152 * _LUT[a8[:, :, 1]]
            + 0.0722 * _LUT[a8[:, :, 2]])
    h, w = L.shape

    gy, gx = np.gradient(L)
    detalhe = np.hypot(gx, gy)

    # ponto focal: centróide da energia de detalhe (onde o olho vai primeiro)
    peso = detalhe ** 2
    total = peso.sum() + 1e-9
    foco_y = float((peso.sum(1) * np.arange(h)).sum() / total)
    foco_x = float((peso.sum(0) * np.arange(w)).sum() / total)

    # energia do detalhe: a MÉDIA não distingue "fundo liso" de "fundo liso com
    # uma silhueta atravessando". A raiz quadrática média sim — uma borda forte
    # eleva a RMS mesmo com média baixa. É o que impede o texto de encostar no
    # sujeito por um zona que "em média" parecia calma.
    ii_d, ii_d2 = _integral(detalhe), _integral(detalhe ** 2)
    ii_L, ii_L2 = _integral(L), _integral(L ** 2)
    sy, sx = safe["top"] // ESCALA, safe["left"] // ESCALA
    ey, ex = h - safe["bottom"] // ESCALA, w - safe["right"] // ESCALA

    # candidatas: faixa cheia, coluna esquerda e coluna direita, alturas variadas
    larguras = [(sx, ex), (sx, sx + (ex - sx) * 55 // 100), (ex - (ex - sx) * 55 // 100, ex)]
    candidatas = []
    for x0, x1 in larguras:
        for frac in (0.26, 0.32, 0.40):
            bh = int(h * frac)
            for y0 in range(sy, ey - bh + 1, max(1, h // 40)):
                candidatas.append((y0, x0, y0 + bh, x1))

    # calibra o limite na PRÓPRIA foto: fixo em absoluto reprovaria toda foto
    # de alto contraste e aprovaria toda foto lavada
    rms_todas = []
    for (y0, x0, y1, x1) in candidatas:
        n = (y1 - y0) * (x1 - x0)
        rms_todas.append((max(0.0, _soma(ii_d2, y0, x0, y1, x1) / n)) ** 0.5)
    limite_silhueta = float(np.percentile(rms_todas, 45))

    melhor, ranking = None, []
    for (y0, x0, y1, x1) in candidatas:
        n = (y1 - y0) * (x1 - x0)
        det = _soma(ii_d, y0, x0, y1, x1) / n
        rms = (max(0.0, _soma(ii_d2, y0, x0, y1, x1) / n)) ** 0.5
        media = _soma(ii_L, y0, x0, y1, x1) / n
        var = max(0.0, _soma(ii_L2, y0, x0, y1, x1) / n - media ** 2)
        planura = var ** 0.5

        # SILHUETA POR FAIXA: a RMS do bloco inteiro DILUI uma intrusão de
        # borda (13% da largura tomada pelo sujeito some na média). Testa-se a
        # zona em terços verticais e horizontais: basta UM terço acusar para a
        # zona ser inadmissível. É o que impede o texto de encostar no contorno.
        pior_faixa = 0.0
        for (fy0, fx0, fy1, fx1) in _faixas(y0, x0, y1, x1):
            nf = max(1, (fy1 - fy0) * (fx1 - fx0))
            pior_faixa = max(pior_faixa,
                             (max(0.0, _soma(ii_d2, fy0, fx0, fy1, fx1) / nf)) ** 0.5)
        if pior_faixa > limite_silhueta * 1.25:
            continue

        quietude = 1.0 / (1.0 + det / 6.0)          # pouco detalhe → perto de 1
        uniforme = 1.0 / (1.0 + planura / 22.0)     # luminância estável → perto de 1
        polaridade = abs(media - 127.5) / 127.5     # extremo (claro/escuro) é bom
        # respeito ao sujeito: penaliza cobrir o ponto focal
        cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
        dist = ((cy - foco_y) / h) ** 2 + ((cx - foco_x) / w) ** 2
        respeito = min(1.0, dist ** 0.5 / 0.34)
        area = (y1 - y0) * (x1 - x0) / (h * w)

        nota = (quietude * 0.32 + uniforme * 0.24 + polaridade * 0.20
                + respeito * 0.18 + area * 0.06)
        ranking.append((nota, y0, x0, y1, x1, media, planura, det, respeito))
    if not ranking:
        return {"viavel": False, "motivo": "toda zona candidata cruza a silhueta do sujeito"}
    ranking.sort(reverse=True)
    nota, y0, x0, y1, x1, media, planura, det, respeito = ranking[0]

    # DINÂMICA DE QUIETUDE: quanto a melhor zona é melhor que a pior. Foto sem
    # zona quieta distinguível (razão baixa) não tem "lugar certo" — a decisão
    # existe, mas é fraca, e quem consome precisa saber disso.
    dinamica = round(max(rms_todas) / max(min(rms_todas), 1e-6), 2)

    # cor do texto e selo mínimo — TUDO em luminância relativa linear (WCAG)
    zona_rel = Yrel[y0:y1, x0:x1]
    escura = media < 127.5
    tinta_rel = _LUT[245] if escura else _LUT[20]
    # o pior caso: para texto claro, o pixel mais CLARO do fundo; e vice-versa
    pior_rel = float(np.percentile(zona_rel, 95 if escura else 5))
    alpha = None
    for passo in range(0, 100):
        cand = passo / 100
        # selo preto (escurece) sob texto claro; selo branco (clareia) sob texto escuro
        fundo_rel = pior_rel * (1 - cand) if escura else pior_rel + (1.0 - pior_rel) * cand
        hi, lo = max(tinta_rel, fundo_rel), min(tinta_rel, fundo_rel)
        if (hi + 0.05) / (lo + 0.05) >= alvo_contraste:
            alpha = round(cand, 2); break

    return {
        "zona": {"x": x0 * ESCALA, "y": y0 * ESCALA,
                 "w": (x1 - x0) * ESCALA, "h": (y1 - y0) * ESCALA},
        "nota": round(nota, 4),
        "limite_silhueta": round(limite_silhueta, 2),
        "medidas": {"luminancia_media": round(media, 1), "planura": round(planura, 1),
                    "detalhe": round(det, 2), "respeito_ao_foco": round(respeito, 3),
                    "pior_luminancia_relativa": round(pior_rel, 5),
                    "dinamica_de_quietude": dinamica,
                    "zonas_admissiveis": len(ranking),
                    "confianca": "alta" if dinamica >= 2.5 else "baixa"},
        "foco": {"x": int(foco_x * ESCALA), "y": int(foco_y * ESCALA)},
        "texto_claro": bool(escura),
        "selo_alpha": alpha,
        "viavel": alpha is not None,
    }

if __name__ == "__main__":
    caminho = sys.argv[1] if len(sys.argv) > 1 else "out/bg_kintsugi.png"
    canvas = {"w": 1088, "h": 1360}
    safe = {"top": 88, "bottom": 88, "left": 88, "right": 88}
    print(json.dumps(analisa(caminho, canvas, safe), indent=2, ensure_ascii=False))
