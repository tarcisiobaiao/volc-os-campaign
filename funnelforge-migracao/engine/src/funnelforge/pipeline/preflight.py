# funnel-forge/src/funnelforge/pipeline/preflight.py
"""Pré-voo: as reprovações que já dá para saber ANTES de pagar o redator.

O desperdício mais caro do pipeline não era o retry — era a ORDEM. Uma página
que ia reprovar por falta de link oficial só descobria isso depois de pagar
pesquisa + até três redações + juiz. O texto nunca teve chance: o motivo da
reprovação já estava decidido antes da primeira palavra.

Este módulo roda, de graça e sem rede, o subconjunto dos validadores DO PRÓPRIO
PASSO que não dependem do texto gerado:

- `pagespec` valida `page.routes` (grafo determinístico de `build_funnel_routes`).
  Rodar depois de escrever é rodar sobre exatamente os mesmos dados: se reprova,
  reprova igual nas três tentativas.
- `official_link_density` depende do texto, MAS é impossível de satisfazer
  quando a pesquisa não devolveu nenhum link oficial — `official = linkados ∩
  verificados` é vazio por construção, então o mínimo (1 ou 2) nunca é atingido.

Regra de convivência: só é pré-checado o que ESTÁ na lista de validadores
daquele passo no `config.yaml`. A LP (`write_p1`, `validators: []`) segue sem
pré-voo nenhum — o pré-voo não pode inventar exigência que o passo não tem.
"""
from __future__ import annotations

from funnelforge.domain.models import Issue, PageRole
from funnelforge.pipeline.pagespec import pagespec_validator


def _preflight_pagespec(ctx: dict) -> list[Issue]:
    """`pagespec` só lê ctx (rotas + spec) — o conteúdo é irrelevante para ele."""
    return pagespec_validator("", ctx)


def _preflight_official_links(ctx: dict) -> list[Issue]:
    """Só a IMPOSSIBILIDADE: nenhuma fonte oficial para o texto costurar."""
    role = ctx.get("role")
    if role is not PageRole.SOLUTION or ctx.get("is_terminal"):
        return []
    if ctx.get("official_links"):
        return []
    return [Issue(
        code="official_links_none",
        message=("A pesquisa não devolveu nenhum link oficial elegível: "
                 "official_link_density reprovaria qualquer texto. "
                 "Redação não iniciada (economia de 1 a 3 chamadas)."),
    )]


# name do validador no config.yaml -> checagem de pré-voo equivalente
PREFLIGHT: dict[str, object] = {
    "pagespec": _preflight_pagespec,
    "official_link_density": _preflight_official_links,
}


def preflight_issues(validators: list[str], ctx: dict) -> list[Issue]:
    """Reprovações certas, calculadas antes de qualquer chamada paga.

    `validators` é a lista do passo (`cfg.validators`); nomes sem pré-voo
    equivalente são ignorados — o pré-voo nunca é mais exigente que o passo.
    """
    out: list[Issue] = []
    for name in validators:
        checagem = PREFLIGHT.get(name)
        if checagem is not None:
            out.extend(checagem(ctx))  # type: ignore[operator]
    return out
