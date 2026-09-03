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

- `plano_de_destino_pago` avalia H1/título/subtítulos/CTAs do PLANO contra a
  política do destino pago. Ele ignora o texto gerado por construção: a alegação
  que derrubou a conta ("Saque-Aniversário FGTS Liberado pelo Governo") estava no
  H1, decidida antes da primeira palavra.

Regra de convivência: só é pré-checado o que ESTÁ na lista de validadores
daquele passo no `config.yaml` — o pré-voo não pode inventar exigência que o
passo não tem. ⚠️ Isto deixou de ser inócuo para a LP: `write_p1.validators`
não é mais uma lista vazia, e é justamente por o nome estar lá que a LP passou a
ter pré-voo.
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


def _preflight_plano_de_destino_pago(ctx: dict) -> list[Issue]:
    """O portão de POLÍTICA sobre o plano: H1, título, subtítulos e CTAs.

    Ele não depende de uma linha do texto gerado — o defeito que derrubou a
    conta estava no H1 do PLANO, decidido antes da primeira palavra. Rodar aqui
    é a diferença entre reprovar de graça e reprovar depois de pesquisa + até
    três redações + juiz.

    Mesma função que o validador do passo executa (`checks.plano_de_destino_pago`),
    não uma cópia: pré-voo que discorda do passo é pior que pré-voo nenhum.
    """
    from funnelforge.pipeline.validators.checks import plano_de_destino_pago

    return plano_de_destino_pago("", ctx)


# name do validador no config.yaml -> checagem de pré-voo equivalente
PREFLIGHT: dict[str, object] = {
    "pagespec": _preflight_pagespec,
    "official_link_density": _preflight_official_links,
    "plano_de_destino_pago": _preflight_plano_de_destino_pago,
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
