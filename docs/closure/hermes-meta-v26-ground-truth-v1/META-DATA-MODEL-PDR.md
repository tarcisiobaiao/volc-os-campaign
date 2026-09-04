# Meta Data Model PDR

Decision: **C — reuse provider-neutral core with Meta extensions**.

## Why not A — add Meta into legacy campaigns
Legacy campaigns/settings/daily metrics are historically Google/GAM-oriented and include browser-facing actions. Extending them would mix identity, spend controls and external IDs across providers.

## Why not B — parallel campaigns_meta only
A standalone Meta island would duplicate the traffic core's identity, mirror, snapshots, links, events, blueprints, validation and receipts.

## Chosen shape
Use `trafego_campanha`, `trafego_campanha_espelho`, snapshots, vínculos, eventos, intenção, blueprint, lote, validação and recibo as nucleus. Add Meta extension tables for business, ad account, project binding, ad set, ad, creative, asset, insights and sync run.

## Non-negotiables
No names as identity; no Meta tokens in DB/browser/logs; browser never writes operational plan; backend is authority; 1Password ref opaque; absence is NULL; sync has cursor/freshness/receipt/error; frontend reads views/read models.
