from __future__ import annotations

import re

from funnelforge.config.settings import Settings
from funnelforge.domain.models import Issue, PageRole, PageTypeSpec, Route

_STOP = {"como", "seu", "sua", "para", "pelo", "pela", "fazer", "lista",
         "completa", "passo", "guia", "ver", "quem", "pode", "sobre"}


def _sig_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9à-ü]{4,}", text.lower())
            if t not in _STOP}


def _anchor_congruent(anchor: str, target_h1: str, target_slug: str = "") -> bool:
    """Anchor must describe its target. If nothing about the target is known we
    can only require a non-empty anchor; otherwise require a shared significant
    token between the anchor and the target's H1 OR its SLUG.

    ⚠️ O SLUG PASSOU A CONTAR, e não é afrouxamento.

    Exigir especificamente um token do H1 era uma escolha arbitrária, e ela
    CONFLITAVA com a régua da política do destino pago, que compara a âncora com
    o CAMINHO da URL (`ANCORA_INCONGRUENTE_COM_DESTINO`). Quando o H1 e o slug de
    uma página divergem — no funil de teste deste repositório, "Guia Completo do
    FGTS" mora em `/rec/quem-tem-direito-pr` —, nenhuma âncora satisfazia as duas
    réguas ao mesmo tempo: a que descrevia a manchete traía o caminho, e vice-
    versa. O slug é a identidade do destino na URL; uma âncora que o nomeia
    descreve o destino tão bem quanto uma que nomeia a manchete.
    """
    if not target_h1.strip():
        # Alvo sem H1 conhecido é o caso do `cross_funnel`, cujo `target` é uma
        # URL absoluta de outro funil — não um slug deste plano. Medir a âncora
        # contra os tokens de uma URL que não descreve nada seria acusar por uma
        # ausência de dado, então a regra antiga (âncora não vazia) fica.
        return bool(anchor.strip())
    referencia = _sig_tokens(target_h1) | _sig_tokens(target_slug.replace("-", " "))
    return bool(_sig_tokens(anchor) & referencia)


def pagespec_for(settings: Settings, role: PageRole, *, terminal: bool = False) -> PageTypeSpec:
    """Convert settings.routing[role.value] -> PageTypeSpec. Missing key is a
    ValueError (fail-closed: no spec means no build).

    `terminal=True` (only meaningful for SOLUTION) swaps in the
    `SOLUTION_TERMINAL` routing key: the last solution in the forward chain
    stops advancing and must recirculate cross-funnel instead."""
    key = "SOLUTION_TERMINAL" if terminal else role.value
    cfg = settings.routing.get(key)
    if cfg is None:
        raise ValueError(f"no routing spec for role {key}")
    return PageTypeSpec(role=role, **cfg.model_dump())


def enforce_pagespec(routes: list[Route], spec: PageTypeSpec, *, slug: str,
                     h1_by_slug: dict[str, str]) -> list[Issue]:
    issues: list[Issue] = []
    kinds = [r.kind for r in routes]
    cta = [r for r in routes if r.kind in ("funnel", "cross_funnel")]
    if len(cta) < spec.cta_min:
        issues.append(Issue(code="cta_too_few",
                            message=f"{len(cta)} CTAs < minimo {spec.cta_min}."))
    if len(cta) > spec.cta_max:
        issues.append(Issue(code="cta_too_many",
                            message=f"{len(cta)} CTAs > maximo {spec.cta_max}."))
    for r in routes:
        if r.kind not in spec.allowed_targets:
            issues.append(Issue(code="target_not_allowed",
                                message=f"kind '{r.kind}' nao permitido para {spec.role.value}."))
        if r.kind in spec.forbidden_targets:
            issues.append(Issue(code="target_forbidden",
                                message=f"kind '{r.kind}' proibido para {spec.role.value}."))
        if "self" in spec.forbidden_targets and r.target == slug:
            issues.append(Issue(code="self_loop", message="rota aponta para a propria pagina."))
        if ("bare_rec" in spec.forbidden_targets and r.kind in ("funnel", "cross_funnel")
                and not r.target.strip()):
            issues.append(Issue(code="bare_rec",
                                message="rota funnel sem destino (=/rec morto)."))
    for req in spec.required_targets:
        if req not in kinds:
            issues.append(Issue(code="target_missing",
                                message=f"falta rota obrigatoria '{req}'."))
    funnel_targets = [r.target for r in routes if r.kind == "funnel"]
    if spec.distinct_targets:
        if len(funnel_targets) != len(set(funnel_targets)):
            issues.append(Issue(code="targets_not_distinct",
                                message="alvos funnel repetidos (distinct exigido)."))
    elif len(set(funnel_targets)) > 1:
        issues.append(Issue(code="not_single_destination",
                            message="mais de um destino funnel (destino unico exigido)."))
    if spec.anchor_congruent:
        for r in routes:
            if r.kind in ("funnel", "cross_funnel") and not _anchor_congruent(
                    r.anchor, h1_by_slug.get(r.target, ""), r.target):
                issues.append(Issue(code="anchor_incongruent",
                                    message=f"ancora '{r.anchor}' nao descreve o destino."))
    return issues


def pagespec_validator(content: str, ctx: dict) -> list[Issue]:
    """Registry adapter: no-op unless step_write injected ctx['pagespec']."""
    spec_raw = ctx.get("pagespec")
    if spec_raw is None:
        return []
    spec = spec_raw if isinstance(spec_raw, PageTypeSpec) else PageTypeSpec(**spec_raw)
    parsed = ctx.get("parsed") or {}
    routes_raw = (parsed.get("routes") if isinstance(parsed, dict) else None) or []
    routes = [r if isinstance(r, Route) else Route(**r) for r in routes_raw]
    return enforce_pagespec(routes, spec, slug=ctx.get("slug", ""),
                            h1_by_slug=ctx.get("h1_by_slug", {}))
