# Handoff — Paid Destination Policy Spine V2 (sanitized)

## Destination facts

The private evidence contains final URL observations and limited public GET results. This public package publishes only aggregate destination facts in `GROUND-TRUTH-SUMMARY.json`.

## Required role separation

The previous evidence had aggregate external host extraction only. For V2, measure and store separate fields:

- `clickable_link_hosts`
- `form_action_hosts`
- `script_hosts`
- `resource_hosts`
- `document_redirects`

Current public package marks these as `not_measured` or `not_measured_separately...` when the original evidence cannot distinguish role safely. Do not promote aggregate `external_hosts` to clickable links.

## Correct suspension-cause handling

- Account status `SUSPENDED` is proven.
- Suspension reason literal is not exposed by API.
- Destination policy risk remains a hypothesis/risk input, not confirmed root cause.
- Links/FGTS/Caixa context should remain `HYPOTHESIS_PARTIALLY_SUPPORTED`, not `SUSPENSION_CAUSE_CONFIRMED`.

## Engine implication

Require paid-destination receipts before `/r/` eligibility in campaign creation/submission flows, but this branch is evidence-only and implements no product code.
