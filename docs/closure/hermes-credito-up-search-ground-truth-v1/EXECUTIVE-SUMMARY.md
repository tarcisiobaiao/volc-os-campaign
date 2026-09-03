# Executive Summary — Crédito Up Search Ground Truth V1 (sanitized public package)

Generated: 2026-09-03T10:28:56.029422+00:00
Branch: `sprint/hermes-credito-up-search-ground-truth-v1`
Base: `34dc7b41bce901bd8bebfdec0a01e293678cbf08`

## Why this package was rebuilt

The repository is public. The previous branch contained useful operational evidence, but also row-level search-term/keyword/API-call material that should not remain public. Full evidence was preserved privately, mode 700/600, and this branch now publishes only aggregate sanitized evidence plus handoffs.

## Core facts

- Google Ads API/SDK: `google-ads` Python, API `v25`.
- Target account pseudonym: `CUST_e130fdfff3`.
- Account status observed: `SUSPENDED`.
- Suspension reason: `ACCOUNT_SUSPENSION_REASON_NOT_EXPOSED_BY_API`.
- Search campaign rows: 5.
- Ads rows: 5.
- Keyword rows counted privately: 263 — not versioned row-by-row.
- Search terms counted privately: 371 — not versioned row-by-row.
- Impressions/clicks/cost/conversions: 1202 / 12 / R$ 0.48 / 0.0.

## Corrected verdicts

```text
ACCOUNT_TOPOLOGY: PARTIAL
ACCOUNT_SUSPENSION_STATE: PROVEN
ACCOUNT_SUSPENSION_ROOT_CAUSE: HYPOTHESIS_PARTIALLY_SUPPORTED
SEARCH_NON_DELIVERY_ROOT_CAUSE: MULTIFACTORIAL
GOOGLE_RECOMMENDATIONS_READ: EMPTY_CONFIRMED
KEYWORD_DIAGNOSTICS_READ: PROVEN
SEARCH_ALERT_OPERATIONAL_GAP: PARTIALLY_PROVEN
DESTINATION_POLICY_FACTS: PROVEN_WITH_ROLE_SEPARATION_LIMITATION
READY_FOR_ENGINE_HANDOFF: YES
```

Removed broad claim: `VOLC_EARLY_WARNING_GAP: PROVEN`.

## Correct early-warning statement

The mission proves an operational alert gap partially: Google exposed signals that should feed Search Delivery Sentinel, but this branch did not prove the complete continuous collection → persisted interpretation → frontend delivery → operator reaction path. Some collection/projection already exists in VOLC; the remaining gap is the end-to-end sentinel/alert loop.

## Zero-mutate

No Google Ads mutate, validate-only mutate, ApplyRecommendation, Supabase write, page-live call, WordPress write, Data Manager call, deployment, Roadmap edit, curation edit, graph edit, or merge was performed during this microcorrection.
