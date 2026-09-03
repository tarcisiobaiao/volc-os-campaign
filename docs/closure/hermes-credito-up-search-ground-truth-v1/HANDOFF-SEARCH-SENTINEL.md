# Handoff — Search Delivery Sentinel (sanitized)

## Inputs available privately

Full row-level evidence is preserved outside Git and referenced only by hashes in `PRIVATE-EVIDENCE-MANIFEST.json`. Public branch keeps aggregates only.

## Signals to collect and alert on

| Signal | Evidence in mission | Alert state |
|---|---|---|
| Account suspended | Target account status `SUSPENDED` | Block launch/use; request human evidence; no mutate |
| Near/low delivery | 1202 impressions, 12 clicks, R$ 0.48 | Alert after launch window |
| Below first page bid | 52 keyword rows | Human bid review; no automatic raise |
| Campaign removed | 3 campaign rows | Treat as historical/removed, not active |
| RSA strength | {'AVERAGE': 3, 'GOOD': 1, 'POOR': 1} | Creative quality warning, separate from policy |
| Recommendations | 0 rows | Empty confirmed; not health proof |
| Conversion readiness | {'campaign_conversions_observed_90d': 0.0, 'conversion_action_rows': 5, 'customer_goal_rows': 2, 'included_in_conversions_metric': 1, 'primary_actions': 1, 'smart_bidding_readiness': 'NOT_NEEDED_FOR_OBSERVED_MANUAL_CPC_BUT_SIGNAL_WEAK_FOR_FUTURE_SMART_BIDDING'} | Gate Smart Bidding readiness separately |
| Paid destination receipt | `/r/` final URLs observed privately | Require policy receipt before eligibility |

## Correct governance wording

Use `SEARCH_ALERT_OPERATIONAL_GAP: PARTIALLY_PROVEN`, not `VOLC_EARLY_WARNING_GAP: PROVEN`.

Some Google intelligence collection/projection exists already. The unproven gap is continuous collection + delivered alert + reaction loop.

## Do not do

- Do not version search terms.
- Do not version row-level keywords.
- Do not treat unavailable account/customer_client reads as zero.
- Do not auto-apply Google recommendations.
- Do not infer suspension cause from delivery metrics.
