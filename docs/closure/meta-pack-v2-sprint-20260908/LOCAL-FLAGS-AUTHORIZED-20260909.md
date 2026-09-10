# Local Meta permissions — confirmed authorization

The operator explicitly confirmed the three exact local settings on 2026-09-09:

- `META_VALIDATE_ONLY_ENABLED=1`
- `META_CREATE_PAUSED_ENABLED=1`
- `META_CREATE_LEDGER_WRITE_ENABLED=1`

Saved in ignored `backend/.env.local`. No credentials changed. No Supabase schema/data writes, uploads, Meta validations, campaign creations or activations were performed in this configuration run.

The backend was restarted on127.0.0.1:8010 with `PYTHONPATH=..:.`; frontend8080 remained running. Fresh real Settings and the unchanged capability handler returned validate_only=ENABLED, create_paused=ENABLED, ledger=true, activation=NOT_IMPLEMENTED. Live /health returned200, Supabase configured, no missing routers/rotinas, startup reconciliation disabled. The live capability endpoint without authentication returned401.

Ten focused configuration tests passed, including precedence of explicit revocation and separation between validation and creation. Per-plan validation/approval, identity, media custody, destination control and PAUSED-only enforcement remain unchanged.

This supersedes only the configuration-refusal blocker in RELEASE-CHAIN-20260909.md. P11-T09 remains partial until the operator reviews, validates and approves a concrete plan and the PAUSED canary/read-back succeeds. No live campaign success is claimed.

Rollback: set these three keys to0 in backend/.env.local and restart the backend. Do not change unrelated keys, media grants or campaign state.

Roadmap: P11-T10 done (local configuration only); P11-T09 partial. Graph: cap_meta_ads.
