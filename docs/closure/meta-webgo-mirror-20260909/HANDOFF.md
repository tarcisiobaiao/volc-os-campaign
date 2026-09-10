# Webgo Meta mirror — 2026-09-09

Status: LOCAL_PARTIAL. Target branch `migration/meta-volc-mirror-20260909`, base `9c91e1cc`. Source `be4483b1` plus explicitly hashed uncommitted Meta work. No push/deploy. Source Google and database configuration unchanged.

Webgo now contains an isolated Meta frontend dependency closure, Meta-only traffic routes, Google/Meta campaign switch, a Meta Ads integration tab, creative assistant/packs and an independent Python service. Existing Webgo Google pages, Meta CAPI and Pautador remain in place. The mirror is not a whole-repository overwrite.

The user-authorized Webgo cloud migration `20260909123008_webgo_meta_mirror` was applied and entered in migration history. SHA256 `c714e36b23c0339258dee78533ee50ed67558016e0bf630b3150dbba1658ca6d`. It composes 30 source migrations; missing working-tree read-model prerequisites were read from source HEAD without restoring source deletions. Privileged function implementations are private with service-only invoker RPC wrappers. Initial administrator resolves an existing confirmed Webgo auth identity.

Post-commit live verification: 63 public module tables; zero without RLS; zero exposed new privileged definer RPCs; one administrator and one migration receipt. Zero source customer images, business tokens or upload grants transferred. Google/GAM data was not rewritten. Source operational authority remains the self-hosted database, independently of the explicitly authorized Webgo target.

Proof: local disposable PostgreSQL install and behavioral tests; cloud full install rehearsal + behavior rolled back; atomic cloud apply; live PostgREST role/draft-list and anonymous negative tests. Draft save/read, owner isolation, stale version conflict, archive and orphan-adset rejection were exercised without leaving test records. Vite build passed. Three offline ASGI tests passed. Backend imported 95 routes without Google/Pautador endpoints.

Limits: global Webgo TSC stops at pre-existing Login 2 JSX syntax; a diagnostic excluding it showed no module errors but host errors remain. No authenticated browser QA or deployment. Independent runtime secrets, storage, provider credentials and target business/token/account configuration are not installed or exercised. Source runtime/credentials not reused. No Meta canary or paid generation. Video/typography auxiliary assets and Webgo reporting scheduler/n8n deployment are not certified. This does not close upstream Meta remote-creation tasks.

Target runbook: `meta-service/README.md`; ADR: `docs/decisions/001-isolated-meta-mirror.md`; source/SQL hash manifests live in `meta-service/`. Continue with target runtime setup, authenticated session QA, then explicitly reviewed PAUSED canary. No blanket source authorization carried to Webgo.
