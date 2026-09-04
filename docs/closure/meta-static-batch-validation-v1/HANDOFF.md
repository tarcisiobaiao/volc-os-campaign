# Meta Static Batch Validation V1

State: `PARTIAL`, ready for operator review and remote `validate_only` only.

This slice fixes the v26-required campaign field
`is_adset_budget_sharing_enabled`, including backward compatibility for browser
tabs opened before the field entered the UI. Omission is compiled as the safe,
explicit value `false`; opt-in remains visible in the Budget step.

The same canonical compiler now supports one to ten explicit static variations
inside one Campaign and one Ad Set. Every variation is exactly one Creative plus
one PAUSED Ad. Stable step keys, opaque asset references, bulk account-scoped
resolution, semantic hashing, per-item receipts and read-back preserve the
boundary between UI intent and provider identifiers.

The Anúncio step exposes three honest modes:

- Individual: available.
- Controlled batch: available for up to ten explicit variations, with a real
  authenticated preview per selected image and no implicit Cartesian product.
- Flexible creative: inspectable as an explicit non-emitting mode. The local
  v26 inventory proves the asset limits, but the exact `asset_feed_spec`, Ad Set
  dynamic flag, placement rules and read-back contract still need an
  official-reference plus remote validation pass. The operator can inspect the
  boundary without the UI pretending that the mode can compile or validate.
  No guessed payload is emitted.

No create, approve or enable route was mounted. Remote validation still requires
an explicit operator click and the ephemeral server flag. No Meta mutation,
Supabase write, migration application or deploy was performed.

Roadmap authority remains `P11-T05=partial`: a real root validation and a future
separately authorized PAUSED canary are still required.
