# Gemini 3.7 Flash review package — Publisher Ground Truth V1

Status: `REVIEW_PASSED` — resultado factual preservado em `GEMINI-REVIEW-RESULT.json`.

Use Gemini 3.7 Flash via API only when `GEMINI_API_KEY` is injected in a secure process environment. Do not persist or print the key.

## Files to review

- `backend/app/publisher_quality/snapshot.py`
- `backend/app/publisher_quality/fetch.py`
- `backend/tests/test_publisher_quality_snapshot.py`
- `scripts/auditar_publisher_quality.py`
- `docs/closure/hermes-publisher-ground-truth-v1/README.md`

## Scope for Gemini

Verify only factual Google/Chrome ecosystem claims and contract compatibility:

1. GPT semantics: loader, `defineSlot`, div id, ad unit path, sizes, SRA, lazy loading, refresh.
2. Publisher Console / observable slot facts: whether the fields represented here are reasonable as observations vs unavailable.
3. Core Web Vitals: lab vs field, p75, LCP/INP/CLS, CrUX/RUM distinction.
4. GA4/dataLayer: event/parameter cardinality limits and PII/cardinality risk framing.
5. Whether any implemented detection wrongly implies causality, policy violation, or authority to mutate.

## Non-goals

- Do not write implementation.
- Do not approve push alone.
- Do not inspect secrets.
- Do not use non-official docs as authority for Google contracts.
- Do not convert observations into causal claims.

## Minimal implementation summary

`PublisherSurfaceSnapshot` is a deterministic JSON contract. Every semantic field is represented as `{status, evidence, value?, observed_at?}` where status is one of:

- `observed`
- `absent_confirmed`
- `unavailable`
- `not_applicable`
- `failed`

Absent fields intentionally omit `value`, so absence is not collapsed to zero, `false`, or empty list.

The scanner reads local sanitized artifacts containing optional HTML, optional dataLayer array, and optional FunnelForge-shaped `AdManifest`. It may also read one public HTTPS URL with SSRF guards, but no real target was proven in this run.

Detections implemented as observations/risks:

- duplicated GPT loader;
- duplicated `div_id`;
- slot without identity;
- slot without size/breakpoint;
- slot without reserved space;
- fluid ATF;
- BTF without lazy-load evidence;
- refresh without observable policy;
- canonical/host/path absent or contradictory;
- dangerous dataLayer cardinality;
- possible personal data in dataLayer;
- AdManifest × DOM divergence.

## Official sources consulted locally before package

- https://developers.google.com/publisher-tag/guides/get-started
- https://developers.google.com/publisher-tag/guides/control-ad-loading
- https://developers.google.com/publisher-tag/guides/minimize-layout-shift
- https://developers.google.com/tag-platform/tag-manager/datalayer
- https://web.dev/articles/vitals
- https://developers.google.com/analytics/devguides/collection/ga4/event-parameters
- https://support.google.com/analytics/answer/9267744

## Requested Gemini verdict format

Return JSON only:

```json
{
  "model": "gemini-3.7-flash",
  "verdict": "pass|blocking_findings",
  "blocking_findings": [
    {
      "id": "GEMINI-001",
      "file": "path",
      "claim_or_code": "short quote or symbol",
      "official_source_url": "https://...",
      "why_blocking": "...",
      "reproduction_or_counterexample": "..."
    }
  ],
  "non_blocking_notes": [],
  "official_sources_used": []
}
```

Only mark blocking if there is an executable counterproof or documented factual incompatibility with official Google/Chrome/web.dev sources.
