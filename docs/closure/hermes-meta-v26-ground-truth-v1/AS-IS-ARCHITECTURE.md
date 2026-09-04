# AS-IS Architecture

## What is already multichannel

- `backend/app/trafego/plataforma.py` declares `GOOGLE_ADS` and `META_ADS`, provider/channel hierarchy labels, and the read/propose/write vocabulary.
- `trafego_*` migrations establish provider-neutral identity, mirror, account snapshots, links, events, intent/blueprint/lote/validation/receipt patterns.
- Frontend has a Traffic Hub component tree and Meta placeholder state.

## What is Google-coupled

- `volc_ads/*` builders, validators, receipts and Google Ads v25 proto logic.
- Existing channel manifests for Search/Display/Demand Gen/PMax.
- Settings campaign UI labels Google Ads and calls status actions in a legacy context.
- Daily campaign metrics/GAM/Google facts are not Meta insight tables.

## Legacy not to extend blindly

- `campaigns`/`daily_campaign_metrics` settings stack for ROI dashboard.
- Meta CAPI wizard/site tables: server events only, not paid media object hierarchy.
- Browser-side fixture states in Hub tests.

## Reusable

- Identity/freshness/null-not-zero rules from v9.
- Proposal/approval/receipt/idempotency from v10.
- Manifest-driven UI capability disclosure.
- Creative asset lineage/validation concepts.

## Needs Meta extension

- Business/ad account/project binding.
- Meta campaign/ad set/ad/creative mirrors.
- Meta insight daily facts and sync runs.
- Backend-only credential resolver.
- Meta blueprint builder/local validator/read adapter.

## Server authority

The backend authenticated service owns operational writes and external reads. The browser renders read models and submits proposals; it does not resolve tokens or write operational plan state.

## Delegated evidence correction

A later read-only AS-IS audit refined the schema picture:

- v9 inventory is **not fully provider-neutral** in concrete identity columns: it is Google-shaped (`customer_id`, `campaign_id`, Google channel checks). Reuse its patterns — freshness, mirror, snapshots, links, events — but do not insert Meta directly into v9 tables without migration/extension.
- v10 intent/blueprint/lote/receipt layer is materially more Meta-ready because `plataforma` already allows `META_ADS` and receipt/idempotency/human approval are provider-neutral.
- `backend/app/trafego/contrato_canais.py` is still Google-only for channel cockpit contracts.
- `backend/app/trafego/ledger.py` blocks Meta because `volc_campaign_id_de()` is Google-only.
- Hub UI correctly avoids faking Meta by reading Google inventory; this no-fake-data behavior is a requirement.
