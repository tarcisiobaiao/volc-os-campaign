# Meta v26 breaking changes → VOLC rules

## V26_ADVANTAGE_AUDIENCE_HECF

Source: https://developers.facebook.com/docs/graph-api/changelog/version26.0 (v26.0, read 2026-09-04)

Rule: If special_ad_categories intersects HEC-F and targeting is constrained/relaxable, require explicit advantage_audience in targeting_automation; omission is stable error META_V26_ADVANTAGE_AUDIENCE_REQUIRED.

## V26_INSTAGRAM_EXPLORE_REMOVED

Source: https://developers.facebook.com/docs/graph-api/changelog/version26.0 (v26.0, read 2026-09-04)

Rule: Reject instagram_positions containing explore; suggest eligible alternatives; never silently send removed placement.

## V26_MESSENGER_STORIES_DEPRECATED

Source: https://developers.facebook.com/docs/graph-api/changelog/version26.0 (v26.0, read 2026-09-04)

Rule: Warn/block messenger_positions story in manual placements unless explicitly modeled as unsupported; read-back effective placements is mandatory.

## V26_POLL_CREATIVE_REJECTED

Source: https://developers.facebook.com/docs/graph-api/changelog/version26.0 (v26.0, read 2026-09-04)

Rule: Reject poll_spec and interactive_components_spec.type=poll in local validation.

## V26_WEB_APP_WEB_ONLY_RESTRICTED

Source: https://developers.facebook.com/docs/graph-api/changelog/version26.0 (v26.0, read 2026-09-04)

Rule: If campaign conversion locations are Website+App, creative.applink_treatment cannot be web_only.

## V26_DELIVERY_ESTIMATE_FIELDS_REMOVED

Source: https://developers.facebook.com/docs/graph-api/changelog/version26.0 (v26.0, read 2026-09-04)

Rule: Contracts may read delivery_estimate only without removed fields; no replacement API; no outcome promise.

## V26_SHOP_ADS_DEFAULTING

Source: https://developers.facebook.com/docs/graph-api/changelog/version26.0 (v26.0, read 2026-09-04)

Rule: For eligible shop advertisers, require explicit destination choice; do not inherit WEBSITE_AND_SHOP silently.
