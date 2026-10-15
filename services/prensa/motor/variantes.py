"""`artboard.variants` — multi-proporção pelo caminho que já funcionava.

## O que era, e por que mudou

O `PRENSA-SPEC.md` §3 promete `artboard.variants` (4:5, 9:16, 1:1, cada uma
com `safe_area` opcional). Até aqui o campo atravessava `resolve.py`, entrava no
`hash_canonico` e `render.py` nunca o lia: uma spec com três variants devolvia
UM PNG na proporção base, byte a byte igual ao da spec sem variants (medido em
10/09/2026; ver `backend/app/criativo/bancada/adaptadores/prensa_tradutor.py`).
Falha silenciosa — a pior classe.

## Como é agora

Nenhum motor novo. Cada variante é a MESMA spec com `artboard.base.{w,h}` (e a
`safe_area`, quando a variante declara a sua) trocados, renderizada de novo pelo
caminho de sempre — exatamente o que `traduzir_lote` já fazia por fora com N
specs. Cada formato continua sendo uma geração própria, nunca um recorte do
4x5: o fit, o verify e os gates rodam de novo na geometria da variante, e uma
variante em que o texto não cabe reprova como qualquer peça.

Quando `variants` existe, a lista É o conjunto de saída: a base só fornece os
defaults (cor de perfil, safe_area). Quem quer o 4x5 o declara na lista, como o
exemplo canônico do SPEC faz.

## O que é recusado, e por quê

Tudo que o `resolve.py` calcula sobre a geometria BASE e grava como literal na
spec resolvida: a colocação automática (`colocacao.modo = auto` mede a zona da
foto no artboard base e escreve `pos` em px) e o selo local
(`gradient.auto_local` mede o recorte cover da foto no artboard base). Aplicar
esses números a outra proporção seria pintar a medição de uma peça em outra.
Isso falha explícito, antes de custo — nunca é ignorado.

Chave desconhecida numa variante também falha: um campo que o motor não lê é
exatamente o defeito que este módulo existe para fechar.
"""
from __future__ import annotations

import copy
import re

CHAVES_VARIANTE = frozenset({"id", "w", "h", "safe_area"})
LADOS = frozenset({"top", "bottom", "left", "right"})
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


class VarianteInvalida(ValueError):
    """`artboard.variants` declarado de um jeito que o motor não sabe honrar."""


def _inteiro(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _camadas(no):
    """Todas as camadas da spec, slides e children incluídos."""
    if isinstance(no, list):
        for item in no:
            yield from _camadas(item)
    elif isinstance(no, dict):
        if "type" in no:
            yield no
        for chave in ("layers", "children", "slides"):
            if chave in no:
                yield from _camadas(no[chave])


def _valida_safe_area(sa, w: int, h: int, onde: str) -> None:
    if not isinstance(sa, dict) or set(sa) != LADOS:
        raise VarianteInvalida(f"{onde}: safe_area exige exatamente {sorted(LADOS)}")
    if not all(_inteiro(v) and v >= 0 for v in sa.values()):
        raise VarianteInvalida(f"{onde}: safe_area exige inteiros >= 0")
    if sa["left"] + sa["right"] >= w or sa["top"] + sa["bottom"] >= h:
        raise VarianteInvalida(f"{onde}: safe_area não deixa área útil em {w}x{h}")


def valida_variantes(spec: dict) -> list[dict] | None:
    """Devolve a lista validada, `None` se a spec não declara variants.

    Levanta `VarianteInvalida` com motivo nomeado em vez de seguir adiante.
    """
    artboard = spec.get("artboard") or {}
    if "variants" not in artboard:
        return None
    variantes = artboard["variants"]
    if not isinstance(variantes, list) or not variantes:
        raise VarianteInvalida("artboard.variants deve ser lista não vazia")

    vistos: set[str] = set()
    for i, v in enumerate(variantes):
        onde = f"artboard.variants[{i}]"
        if not isinstance(v, dict):
            raise VarianteInvalida(f"{onde}: esperado objeto")
        extras = set(v) - CHAVES_VARIANTE
        if extras:
            raise VarianteInvalida(
                f"{onde}: chave(s) não suportada(s) {sorted(extras)} — o motor só honra "
                f"{sorted(CHAVES_VARIANTE)}; chave ignorada seria falha silenciosa")
        vid = v.get("id")
        if not isinstance(vid, str) or not _ID.match(vid):
            raise VarianteInvalida(f"{onde}: id ausente ou fora de [a-z0-9_-] (vira nome de arquivo)")
        if vid in vistos:
            raise VarianteInvalida(f"{onde}: id duplicado {vid!r} — o segundo PNG sobrescreveria o primeiro")
        vistos.add(vid)
        if not (_inteiro(v.get("w")) and _inteiro(v.get("h")) and v["w"] > 0 and v["h"] > 0):
            raise VarianteInvalida(f"{onde} ({vid}): w e h exigem inteiros > 0")
        if "safe_area" in v:
            _valida_safe_area(v["safe_area"], v["w"], v["h"], f"{onde} ({vid})")

    colocacao = spec.get("colocacao") or {}
    if colocacao.get("modo") == "auto" or "colocacao_resolvida" in spec:
        raise VarianteInvalida(
            "variants + colocacao.modo='auto' não é suportado: a zona do texto é medida "
            "na foto sobre o artboard BASE e gravada em px; em outra proporção ela mente. "
            "Gere uma spec por formato (traduzir_lote) ou remova a colocação automática.")
    for camada in _camadas(spec):
        gradiente = (camada.get("style") or {}).get("gradient") or {}
        if gradiente.get("auto_local") or "contraste_local" in camada:
            raise VarianteInvalida(
                f"variants + selo local (camada {camada.get('id')!r}, gradient.auto_local) não é "
                f"suportado: o contraste é medido no recorte cover do artboard BASE. "
                f"Gere uma spec por formato.")
    return variantes


def spec_da_variante(spec: dict, variante: dict) -> dict:
    """A mesma spec, com a geometria da variante. Nunca muta a original."""
    copia = copy.deepcopy(spec)
    artboard = copia["artboard"]
    artboard.pop("variants", None)
    artboard["base"] = {**artboard["base"], "w": variante["w"], "h": variante["h"]}
    if "formato" in artboard["base"]:
        # o rótulo da base (ex.: feed_4x5) mentiria sobre uma peça 9x16
        artboard["base"]["formato"] = variante["id"]
    if "safe_area" in variante:
        artboard["safe_area"] = dict(variante["safe_area"])
    artboard["variante"] = variante["id"]
    return copia
