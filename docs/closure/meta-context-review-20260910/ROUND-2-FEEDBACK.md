# Integrator adjudication for the second review

Read this before proposing changes. Do not repeat already implemented protections.
Return at most three concrete findings in the assigned lane, valid JSON only using
the master schema. Actually use Google Search for current official Meta evidence;
links recalled from memory are not search verification. If official documentation
cannot be retrieved, declare that limitation and mark unsupported claims honestly.
Do not invent proof or turn unverified conjectures into new operational blocks.

1. Preflight is already local and campaign-level before creation. The executor
validates children after their remote parent IDs exist, with every created object
PAUSED. Source inspection and V2 tests confirm remote IDs are saved before
readback; ambiguous reconciliation does not blindly repeat POST. Do not suggest
retrying solely because a lookup returns zero matches: eventual absence is not
proof that a previous remote creation failed.
2. The previous universal Instagram-identity requirement is rejected. Identity
requirements depend on placements and account configuration; the cited reference
does not prove that all campaigns require an Instagram identity.
3. Transferring a body-text limit from asset_feed_spec to
creative_asset_groups_spec is rejected without field-specific official evidence.
Do not impose an additional character gate on that basis.
4. Sales-objective eligibility for the supported flexible recipe, five entries
per text type, uniform CTA and mutual exclusion with existing-post reuse are
already implemented. Preserve them; do not present them as missing features.
5. Advertiser identification is already queried automatically. Its frontend
requests are now coalesced per account and session; 27 UI tests passed.
6. Expanded runtime-copy context is awaiting separate user consent. The local
context resolver uses read-only requests; 47 tests passed. This review receives
only this sanitized engineering summary, not runtime creative or campaign data.
7. The integrator's independent official-Meta fetches received HTTP 429 responses.
That is a verification gap, not evidence that remembered platform claims are true.

Prioritize one actual remaining gap over generic recommendations. Every proposed
change needs a bounded implementation plan and observable regression test.
