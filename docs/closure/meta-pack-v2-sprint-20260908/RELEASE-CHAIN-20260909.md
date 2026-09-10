# Meta release chain — 2026-09-09

Status: **PARTIAL — media upload verified; campaign canary not executed.**

## Live evidence

- Official authority: `https://database.agenciavolc.com.br`.
- Migration `20260909080926_meta_media_ledger_install.sql` applied and committed successfully. SHA256 `dafd3bba0461f62a944fea9fb5a7a259967716c174f8fb46c80c718f721fb293`.
- Previous physical catalog had no media registration table or the four registration RPCs. Added private definer implementations, public invoker wrappers, service-only execution, forced RLS, unique account/content hash, serialized reservations and NULL-safe fencing.
- The first real attempt reached Meta and was explicitly rejected. Corrected the multipart `filename` field per official SDK and opaque filename suffix per stored MIME. Subsequent explicit rejection was `100/1487411` (unsupported file type); after suffix correction one selected, human-approved master was registered successfully.
- Exact live route implementation performed custody/hash/owner/approval/draft-grant checks, durable reservation, upload and settlement. No mocked repository or provider in this test. Admin identity was resolved for the scoped diagnostic from the actual draft owner; browser authentication was not exercised by this script.
- Replays returned `ALREADY_REGISTERED`, same opaque asset reference and one official ledger row. Meta GET by the persisted hash confirmed 1080×1350. Media-library status ACTIVE is the asset state, not activation of an ad: **zero campaigns, adsets or ads created/activated**.
- User-provided real HTTPS destination saved through the versioned draft RPC. No category, rights or copy confirmation was fabricated.
- Human-only review: zero vision calls and zero image generation calls. Existing final-master approval reused.

## Corrected behavior

- Media capabilities consult the official schema readiness RPC before enabling upload. Missing RPC errors have a specific installation message rather than generic HTTP404.
- An unmaterialized pack or failed selection load blocks continuing, compilation, validation, approval and creation; an old ad cannot silently substitute the selected pack.
- Final review groups image, copy, URL and adset; human rights/identity confirmation per current ad and special-category confirmation remain explicit.
- Recipe capability is separated from historical remote evidence. Sales/Leads no longer inherit a Traffic budget proof.
- Receipt validation rejects missing/negative/invalid age, missing consumption state and nonzero/unknown object count.
- Primary v26 changelog now confirms `destination_spec.destination_type=WEBSITE_AND_SHOP_OPT_OUT`. Own website creatives compile that explicit control and require exact read-back. Legacy/post paths retain their earlier guard; no account is labeled shop-ineligible by inference. See `SHOP-OPT-OUT-OFFICIAL-20260909.json`.

## Verification

- Backend media/review focused suite: 66 passing before the additional missing-RPC regression; SQL/authority follow-up 8 passing including two concurrent workers getting exactly one dispatch token.
- V1/V2 creation/opt-out/receipt suite: 280 passing across 11 files.
- Frontend V2/nascimento final suite: 63 passing; prior focused draft/demo/materialization regressions also passed.
- Build passed, with existing bundle/Tailwind warnings. `git diff --check` clean.
- Chrome: approval/upload feedback at375/768/1440 light/dark, keyboard, loading, enabled button, no overflow/page errors. Isolated components and simulated responses; all external requests blocked. Not authenticated end-to-end QA.
- Local frontend8080 and backend8010 healthy after reload, missing routers/rotinas empty.

## Remaining release conditions

The execution permission reviewer twice refused persistent global flags `META_VALIDATE_ONLY_ENABLED`, `META_CREATE_PAUSED_ENABLED`, `META_CREATE_LEDGER_WRITE_ENABLED`, treating prior authorization as draft-limited. No workaround was used and no local flag file was created. Process creation/validation remains closed pending an accepted explicit operational authorization/configuration.

The operator still needs to materialize the already-uploaded pack in the browser (reuses receipt), review ad copy/rights/category, compile and validate the exact current plan, and explicitly approve PAUSED creation. Shop opt-out has official documentation and executable tests, **not** a successful live creative read-back yet. Tracking arrival at GAM, activation, broad management, video/flexible formats and Webgo migration are outside this proof.

Roadmap: P11-T09 partial; P11-T02/P11-T05 remain partial. Graph capabilities: `cap_meta_ads`, `cap_bancada_criativa`.

Sources: [Meta SDK AdImage](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adimage.py), [Meta v26 changelog](https://developers.facebook.com/docs/graph-api/changelog/version26.0/?locale=en_US).
