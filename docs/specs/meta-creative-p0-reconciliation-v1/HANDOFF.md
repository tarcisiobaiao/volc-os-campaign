# Meta + Creative P0 Reconciliation Master Contract

**Verdict:** `META_CREATIVE_P0_MASTER_CONTRACT_READY`

This package reconciles the frozen operational code at `884393b0e99b5ee403a6f38e1e4225012705f942`, Astra's Meta completion spec at `2766e49aed7055f24cd97932e9995406a409826b`, and Fable's Creative Supply Chain spec at `5d2cbd0006b7d794e685ebf67d3d79e6a879e12c`.

It is documentary only. It does not authorize migration, Meta mutate, canary execution, deploy, Roadmap/graph/curation edits, or activation.

## Current fact

`884393b` remains approved only for `CANARY_PREP`. The real `validate_only` receipt accepted independent roots only: Campaign + `creative:variation-001`, `objects_created=0`, plan hash `10e5b56aaf0d1d4c4b87bc309532c148463f40ab721ac44de6b60cfcb061d767`. AdSet and Ad remain provable only during a governed canary.

## Blocking decisions before canary

1. **C01 website-only/Shop** — canary precondition. Do not invent a destination field or default. Prove official opt-out/noneligibility or block.
2. **C03/OCC-01 creative supply** — canary precondition. The selected static image must have bytes read server-side, `content_sha256`, technical gate, third-party identity/policy gate, CLEAR/AUTHORIZED receipt, `supply_sha256`, and exact match to the Meta `image_hash`.
3. **C04 ambiguity/absence** — fix before migration. For P0, only FOUND+CONGRUENT may close. Absence/doubt remains AMBIGUOUS/manual.
4. **C06 flags** — fix before migration. Validate receipt/read/reconciliation must not depend on the dispatch/create flag. Create still requires both create + ledger flags.
5. **C07 Page/Instagram/placements** — canary precondition. Prove Page/Instagram identity or restrict placements safely; no silent fallback.

## Minimal runtime work before canary

The executor has at most five runtime tasks before the first canary: `P0-RT-01` through `P0-RT-05` in `MASTER-P0-EXECUTION-PLAN.json`.

## Act separation

- Local implementation: allowed only as a later separate mission.
- Official migration: separate authorization.
- `validate_only`: separate authorization.
- `create_paused`: separate authorization.
- Read-back: mandatory after each veiculable step.
- Activation: out of scope; no route or authorization.

## Main artifacts

- `MASTER-P0-DECISIONS.json` — adjudicated decisions C01/C02/C03/C04/C05/C06/C07/C13/C16/OCC-01.
- `MASTER-P0-CONTRACT.json` — executable master contract.
- `MASTER-P0-CONFLICT-MAP.json` — one classification per conflict.
- `MASTER-P0-EXECUTION-PLAN.json` — maximum five runtime tasks before canary.
- `MASTER-P0-CANARY-GATE.json` — objective canary gate; currently `CANARY_READY=false`.

## Zero-sensitive-evidence policy

No raw account ID, Page ID, image hash, token, provider request ID, secret path, or row-level operational evidence is intentionally versioned here. Evidence references use commit/file/line or sanitized receipts only.
