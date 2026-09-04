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
