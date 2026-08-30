# funnel-forge/src/funnelforge/pipeline/uniqueness.py
"""Static content-uniqueness validator (T1C).

Jaccard token-set similarity guard against sibling drafts already written in
the same run, registered in `validators/checks.py` under 'uniqueness' and
run through `run_validators` like any other step validator. Also the single
source of the `jaccard()`/tokenizer algorithm reused by the run-time *state
hook* `uniqueness_state_guard(state, page, deps)` in `pipeline/steps.py`
(T0E) -- see that function's docstring for why both exist.

Every funnel page carries a MANDATORY, near-identical compliance kit by
design: the "Aviso de Utilidade Pública" body block, the "Sobre o Site"
footer (CNPJ/Adsense/"sem vínculo" disclosures), the nav strip, and the
author BYLINE (see `prompts/redator_p1.jinja` <formato_de_saida_marcadores>/
<COMPLIANCE> and `prompts/redator_pages.jinja`/`redator_presell.jinja`
<COMPLIANCE>). Two genuinely distinct interior pages sharing that
boilerplate can score Jaccard 0.35+ on raw token overlap alone, which wrongly
trips the duplicate-content guard. `_BOILERPLATE_TOKENS` below is subtracted
from each page's token set before intersection/union so the guard measures
similarity of the DISTINCTIVE body copy only.
"""

from __future__ import annotations

import re

from funnelforge.domain.models import Issue
from funnelforge.pipeline.doctrine import COMPLIANCE_NOTICE_TEXT, REQUIRED_COMPLIANCE_ANCHORS

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[a-z0-9à-ü]{4,}")

# ---------------------------------------------------------------------------
# Fixed compliance/nav/byline spans mandated VERBATIM (or near-verbatim) on
# every page by the redator prompts. This is a single small module-level
# constant of literal phrases copied from the templates -- NOT a per-topic
# stopword list -- so it stays in lockstep with the actual doctrine/prompt
# text instead of drifting into a hand-tuned word blacklist.
# ---------------------------------------------------------------------------
_FIXED_BOILERPLATE_PHRASES: tuple[str, ...] = (
    # AVISO body block, mandated verbatim by redator_p1.jinja <COMPLIANCE>.
    "Aviso de Utilidade Pública: Somos um portal informativo independente. "
    "Não temos vínculo com os órgãos ou instituições citados e não "
    "realizamos qualquer processo de solicitação. Nosso objetivo é apenas "
    "explicar, de forma gratuita, como cada tema funciona. Nunca "
    "solicitamos dados pessoais ou pagamentos.",
    # "AVISO DE PERMANÊNCIA" native block: legacy phrase from the pre-T1D
    # redator_pages.jinja. No current template mandates it verbatim, but
    # discounting it is harmless (a no-op subtraction) if it ever recurs in
    # older/resumed drafts, so it stays in the constant rather than risking
    # a behavior change to the Jaccard guard outside this task's scope.
    "Você permanecerá neste mesmo site",
    # "Sobre o Site" footer lead-in + fixed clauses, from redator_p1.jinja
    # <COMPLIANCE> / redator_pages.jinja / redator_presell.jinja <COMPLIANCE>.
    "Sobre o Site",
    "não pede dados pessoais nem qualquer valor",
    "os conteúdos são informativos e não têm vínculo, parceria ou ligação "
    "oficial com órgãos públicos ou entidades governamentais",
    "verifique sempre os canais oficiais",
    "financiado por anúncios em parceria com o Google Adsense",
    "não temos relação com os anunciantes",
    "não temos relação com Facebook ou Google",
    "marcas registradas dos respectivos donos",
    # NAV strip + BYLINE marker labels, fixed by redator_p1.jinja
    # <formato_de_saida_marcadores> (=== WIDGET: NAV ===/=== WIDGET: BYLINE ===).
    "Home",
    "Nome",
    "Credencial",
)

_ALL_BOILERPLATE_PHRASES = (
    COMPLIANCE_NOTICE_TEXT, *REQUIRED_COMPLIANCE_ANCHORS, *_FIXED_BOILERPLATE_PHRASES,
)
_BOILERPLATE_TOKENS: frozenset[str] = frozenset(
    tok
    for phrase in _ALL_BOILERPLATE_PHRASES
    for tok in _WORD_RE.findall(phrase.lower())
)


def _visible_tokens(text: str) -> set[str]:
    stripped = _TAG_RE.sub(" ", _COMMENT_RE.sub(" ", text))
    tokens = set(_WORD_RE.findall(stripped.lower()))
    return tokens - _BOILERPLATE_TOKENS


def jaccard(a: str, b: str) -> float:
    """Jaccard similarity over each page's DISTINCTIVE token set -- the
    shared compliance/nav/byline boilerplate (`_BOILERPLATE_TOKENS`) is
    subtracted from both sides first, so two distinct pages sharing that
    mandatory kit don't get flagged as near-duplicates on boilerplate alone."""
    ta, tb = _visible_tokens(a), _visible_tokens(b)
    if not ta or not tb:
        return 0.0
    union = len(ta | tb)
    return len(ta & tb) / union if union else 0.0


def uniqueness_guard(content: str, ctx: dict) -> list[Issue]:
    priors = ctx.get("prior_drafts") or []
    if not priors:
        return []
    threshold = float(ctx.get("jaccard_threshold", 0.35))
    worst = max((jaccard(content, p) for p in priors), default=0.0)
    if worst >= threshold:
        return [Issue(code="duplicate_content",
                      message=f"Similaridade Jaccard {worst:.2f} >= {threshold:.2f} "
                              f"com outra pagina (conteudo raso/duplicado).")]
    return []
