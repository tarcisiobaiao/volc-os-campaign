# PMax observability v25 — correction handoff

Scope: read-only Google Ads API v25 observability. This module does not expose a
campaign builder, mutation, `validate_only`, approval, or creation authority.

## Evidence contract

Every GAQL result enters the kernel in a `CollectionEnvelope`. The states are
`PRESENT`, `PRESENT_EMPTY`, `NOT_COLLECTED`, `COLLECTION_FAILED`, and `STALE`.
Only the first two authorize structural diagnosis. In particular, `[]` is a
measurement only when the collector explicitly marks it `PRESENT_EMPTY`.

The query contract is checked offline against the v25 protobuf descriptors in
the installed Google Ads SDK. It deliberately does not select the nonexistent
`campaign.url_expansion_opt_out` or
`asset_group_asset.performance_label` fields. It collects:

- `campaign.brand_guidelines_enabled`;
- `asset_group.asset_coverage`;
- AssetGroupAsset primary status, reasons, details, source and policy summary;
- CampaignAsset links for `BUSINESS_NAME` and `LOGO` when Brand Guidelines are
  enabled.

Resource-name filters require a validated ten-digit `customer_id`; wildcard
`customers/*/...` values are neither emitted nor synthesized.

## Structural semantics

- Removed/paused/unknown asset links do not count as enabled coverage.
- Removed asset groups are historical and do not create operational gaps.
- Eligibility is derived from `asset_group.primary_status == ELIGIBLE`, not
  from the mutable administrative `status` field. Missing primary status makes
  the aggregate indeterminate.
- With Brand Guidelines enabled, business name and logo are checked at
  CampaignAsset level, not falsely required in AssetGroupAsset.
- Limits follow `docs/growth-engine/matriz-api/performance-max.md`: landscape
  logo 20, YouTube video 15, media bundle 1, and at least one description with
  at most 60 characters.

## Integration boundary

The collector must execute and receipt all six SELECT families independently:
campaign, asset group, asset-group asset, asset, signal and campaign asset. It
must preserve failures and timestamps in their envelopes. A caller that cannot
provide that contract receives no diagnosis, by design.

This handoff changes no Roadmap, curation or generated graph. The single
integrator must reconcile those shared authorities after accepting the commit.
