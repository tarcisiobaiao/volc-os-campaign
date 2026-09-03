# HANDOFF — P09-T17 Campaign Birth Single Authority V1

## Verdict proposed
`P09_T17_CAMPAIGN_BIRTH_SINGLE_AUTHORITY_ACCEPTED`, contingent on final review/push read-back by Bia/Hermes.

## Base and branch
- Base: `origin/volc-os-v2` = `207e91f1da290130e8d02b78c3ba1c8e9a761111`
- Branch: `sprint/hermes-p09-t17-campaign-birth-authority-v1`
- Worktree: isolated local mission worktree (local path intentionally not versioned)

## What changed
- Added `volc_ads/gads/autoridade.py`: signed, one-use birth capability with explicit proof fields.
- `backend/app/routers/trafego.py` now emits the capability only after route gates, ledger dispatch and measurement-plan persistence, and returns a sanitized authorization receipt.
- `volc_ads/subir.py` requires and checks the capability before mode gate/pre-receipt/mutate; payload status must be `PAUSED`.
- `volc_ads/gads/client.py::mutar` consumes the capability before constructing the Google client/network request.
- Added structural gate `scripts/gate_autoridade_de_nascimento.py`.
- Added P09-T17 backend tests and extended `volc_ads/testes_subir.py` counterproofs.
- Added machine-readable producer inventory and closure docs.

## Red proof
On the authorized base, a direct import of `volc_ads.subir.subir` with forged `Selo`, arbitrary account/MCC and campaign payload `ENABLED` reached a fake adapter exactly once and produced a fake created campaign. No network was possible.

On the fixed tree, the same script exits green with `AutorizacaoAusente`, fake adapter calls `0`, receipts `0`.

## External effects
- Google Ads real: **none**.
- Google Ads `validate_only` real: **none by this lane**; tests use hermetic fakes/sentinels.
- Supabase write/migration: **none**.
- n8n live/WordPress/deploy/systemd: **none**.
- Roadmap/grafo/curadoria shared: **not edited**; see `CURATION-HANDOFF.json`.
