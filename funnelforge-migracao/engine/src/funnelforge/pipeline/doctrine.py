"""Single source of truth for the calm-utility copy doctrine.

Every banned/required phrase used to police funnel copy (fear-mongering,
official-sounding claims, 1st-person emotional CTAs, service-execution verb
CTAs) and every compliance anchor / approved CTA exemplar lives HERE and
only here. Prompts (redator/judge templates), validators, and the judge
must all import from this module instead of hardcoding their own phrase
lists — that duplication is exactly what let the prompt mandate strings the
validator banned, and the judge explicitly ignore.

Layering rule: this module imports ONLY `funnelforge.domain.models` (or the
stdlib) — no network, no other pipeline modules, no adapters.
"""
from __future__ import annotations

import re

from funnelforge.domain.models import PageRole

# ---------------------------------------------------------------------------
# Fear / urgency / scarcity — banned everywhere, on every page role.
# ---------------------------------------------------------------------------
BANNED_FEAR: tuple[str, ...] = (
    "muitos perdem",
    "não perca o prazo",
    "o sistema pode recusar",
    "cuidado, um detalhe bloqueia",
    "poucos sabem",
    "última chance",
    "vagas limitadas",
    "corra antes que",
    "não perca essa chance",
)

# ---------------------------------------------------------------------------
# Official-sounding / false government-affiliation claims — banned
# everywhere, on every page role.
# ---------------------------------------------------------------------------
BANNED_OFFICIAL: tuple[str, ...] = (
    "liberado pelo governo",
    "sistema oficial",
    "aprovado pelo governo",
    "canal oficial do governo",
    "site oficial do governo",
    "portal oficial do governo",
)

# ---------------------------------------------------------------------------
# 1st-person emotional CTAs — banned ONLY on the Landing Page (P1). Interior
# funnel pages (PRESELL/SOLUTION) intentionally use this register by design.
# ---------------------------------------------------------------------------
BANNED_CTA_FIRST_PERSON: tuple[str, ...] = (
    "quero ver",
    "quero descobrir",
    "quero conferir",
    "será que eu",
    "e se eu",
    "não quero perder",
    "não quero correr",
)

# ---------------------------------------------------------------------------
# Service-execution verb CTAs — banned everywhere. Copy describes curiosity
# about a topic; it never promises to execute a government/institutional
# service on the reader's behalf.
# ---------------------------------------------------------------------------
BANNED_CTA_EXECUTION: tuple[str, ...] = (
    "agendar",
    # ⚠️ `solicitar` SAIU desta lista por decisão do operador, em 17/08/2026.
    #
    # O motivo: o radical stemizado (`solicit`) reprovava o próprio exemplar
    # APROVADO desta mesma doutrina — "Como fazer a solicitação pelo app >>>" —,
    # e a contradição derrubava a LP por um CTA que a casa considera correto.
    # Medido rodando `banned_cta_execution_hit` sobre `APPROVED_CTA_EXEMPLARS`.
    #
    # O QUE ISSO LIBERA, medido antes da remoção: além do exemplar pretendido,
    # passam a ser aceitos "Solicitar agora »" e "Solicite seu cartão »" — que
    # SÃO promessa de executar o serviço pelo leitor, e é o que a regra existia
    # para pegar. A troca foi feita de olhos abertos: a contradição custava
    # página reprovada hoje; o risco de política é de política de anúncio.
    #
    # Se um dia isso doer, a correção cirúrgica é distinguir o SUBSTANTIVO
    # ("a solicitação", informacional) do VERBO ("solicitar", execução) em vez
    # de banir o radical — hoje o stem `solicit` não sabe a diferença.
    "emitir",
    "cadastrar",
    "consultar meu cpf",
    "garantir minha consulta",
    "garantir meu acesso",
)


def _cta_execution_regex() -> re.Pattern[str]:
    r"""Build the matcher for banned service-execution verbs in CTA text.

    Single-word infinitives are STEMMED (-ar/-er/-ir dropped) so conjugated /
    imperative forms are still caught ("Solicite" -> stem "solicit"), and every
    alternative is anchored to a WORD START (`\b`). The word-boundary anchor is
    the fix for a real false positive: the bare substring "emit" (stem of
    "emitir") otherwise matches INSIDE "d-emit-ido"/"d-emit-ir" -- the
    demission vocabulary at the heart of the FGTS saque-rescisão funnel -- and
    wrongly blocks a perfectly calm curiosity CTA like "E se eu for demitido?".
    Anchoring to `\b` keeps every genuine ban (a banned verb always BEGINS a
    word in a CTA) while never firing mid-word."""
    alts = []
    for phrase in BANNED_CTA_EXECUTION:
        p = phrase.lower()
        stem = p[:-2] if (" " not in p and len(p) > 4 and p.endswith(("ar", "er", "ir"))) else p
        alts.append(re.escape(stem))
    return re.compile(r"\b(?:" + "|".join(alts) + r")", re.IGNORECASE)


_CTA_EXECUTION_RE = _cta_execution_regex()


def banned_cta_execution_hit(text: str) -> str | None:
    """Return the matched banned execution verb found in `text`, else None.

    Callers MUST pass only CTA button/anchor text (never body/compliance
    prose, which legitimately says "sem solicitar dados" etc.). Word-boundary
    anchored (see `_cta_execution_regex`)."""
    m = _CTA_EXECUTION_RE.search(text or "")
    return m.group(0) if m else None

# ---------------------------------------------------------------------------
# Compliance anchors REQUIRED somewhere in the page (utility-notice body
# block + "Sobre o Site" footer): informative-only stance, no data/payment
# request, no official government link, ad monetization disclosure.
# ---------------------------------------------------------------------------
REQUIRED_COMPLIANCE_ANCHORS: tuple[str, ...] = (
    "utilidade pública",
    "não pede dados pessoais",
    "vínculo",
    "google adsense",
    "não temos relação com facebook ou google",
)

# The interior-page compliance footnote, in ONE place. The Gutenberg enhancer
# (finalize_compliance_notice) renders it as a discreet italic footnote at the
# end of every /rec page, and the uniqueness guard subtracts its tokens as
# boilerplate (it is identical on every page by design).
COMPLIANCE_NOTICE_TEXT: str = (
    "Aviso de Utilidade Pública: portal informativo independente, sem vínculo com os "
    "órgãos citados, não realizamos solicitações e não solicitamos dados pessoais nem "
    "pagamentos."
)

# ---------------------------------------------------------------------------
# Approved CTA exemplars — the calm, 3rd-person/infinitive register that
# Landing Page CTAs must follow instead of the banned 1st-person phrasing.
# ---------------------------------------------------------------------------
APPROVED_CTA_EXEMPLARS: tuple[str, ...] = (
    "Ver o passo a passo",
    "Como consultar seu saldo >>>",
    "Como fazer a solicitação pelo app >>>",
    "Ver a lista completa >>>",
    "Toque abaixo e veja o passo a passo",
    "Toque na opção certa >>>",
)


def banned_for_role(role: PageRole) -> tuple[str, ...]:
    """Banned phrases applicable to `role`.

    Fear, official-sounding, and execution-verb bans apply to every page
    role. 1st-person emotional CTA bans apply ONLY to the Landing Page
    (`PageRole.LP`) — interior funnel pages use that register by design.
    """
    base = BANNED_FEAR + BANNED_OFFICIAL + BANNED_CTA_EXECUTION
    return base + BANNED_CTA_FIRST_PERSON if role == PageRole.LP else base


def doctrine_context() -> dict:
    """Plain-dict/list rendering of the doctrine for prompt templating.

    `compliance_notice_text` entra aqui porque a frase EXATA do aviso estava
    copiada à mão em dois prompts (redator_pages e redator_presell) enquanto o
    enhancer que reposiciona o aviso e o guard de unicidade liam a constante.
    Bastava alguém ajustar a redação num lado para o sistema deixar de
    reconhecer o aviso que o próprio redator escreveu.
    """
    return {
        "banned_fear": list(BANNED_FEAR),
        "banned_official": list(BANNED_OFFICIAL),
        "banned_cta_first_person": list(BANNED_CTA_FIRST_PERSON),
        "banned_cta_execution": list(BANNED_CTA_EXECUTION),
        "required_compliance_anchors": list(REQUIRED_COMPLIANCE_ANCHORS),
        "approved_cta_exemplars": list(APPROVED_CTA_EXEMPLARS),
        "compliance_notice_text": COMPLIANCE_NOTICE_TEXT,
    }
