# Meta Real Read Integration V1

Verdict: `META_REAL_READ_RUNTIME_PROVEN` and
`META_READ_ONLY_OPERATOR_PREVIEW_READY`.

These verdicts mean that the local macOS runtime can resolve the Meta system
user token from Keychain, discover real accounts and execute a sanitized v26
read-only preflight after an explicit operator click. They do not authorize or
claim persistence, migration, campaign creation, editing, activation or deploy.

## Integrated runtime

- Local ADMIN routes resolve opaque account references by re-reading the
  accessible account inventory; raw IDs do not cross the operator contract.
- The adapter paginates Campaign, AdSet, Ad, Creative, Page, Instagram,
  Pixel/Dataset, Custom Conversion and Insights reads.
- `time_range` is encoded as valid compact JSON for Graph API requests.
- Custom Conversion output excludes the raw rule and reports availability and
  firing state.
- Insight fact identities are stable across response ordering and preserve
  account/campaign level instead of pretending every row is a campaign.
- The Meta Hub now exposes a read-only proof panel. It performs no Meta request
  on render; account discovery and preflight require explicit clicks.

## Real proof

Four accessible accounts were discovered and preflighted. The aggregate,
sanitized result is in `REAL-READ-PROOF.json`: zero preflight errors, one Custom
Conversion observed, zero insight rows for today's window, and zero mutations.

## Review adjudication

Claude returned useful architecture findings but not every requested review
completed. Gemini evaluated a stale pre-integration tree and its negative
conclusion about missing Insights was rejected. Acceptance rests on inspected
code, executable counterproofs and the real read-only run, not model consensus.

## Still partial

- v15_01/v15_02 remain draft migrations and were not applied.
- The preview is not a persisted inventory or campaign dashboard yet.
- The productive Cofre resolver remains separate from the local Keychain seam.
- There is no Meta executor, remote creation validation, PAUSED creation or
  activation path.

## Safety boundary

No token, raw account ID or conversion rule is stored in this closure package.
No Meta mutate, Supabase write, migration, n8n, WordPress or deploy occurred.
