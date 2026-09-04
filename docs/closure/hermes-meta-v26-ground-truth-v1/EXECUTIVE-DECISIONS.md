# Executive Decisions

1. **Schema decision: C — reuse provider-neutral traffic core with Meta extensions.** Legacy `campaigns` remains non-authoritative for new Meta operational writes; `campaigns_meta` alone would duplicate receipts/freshness/identity.
2. **MVP starts read-only and contract-first.** Meta account sync, hierarchy render, ZIP manifest and local validation precede any external write.
3. **Future first mutation is one PAUSED campaign/ad set/ad only, separately authorized.** `META_CREATE_PAUSED` never implies `META_ENABLE`.
4. **Credential data plane is backend-only.** VOLC stores opaque 1Password reference and readiness receipts; browser never receives Meta token.
5. **Meta MCP is advisory/control-plane only.** It is not the production data plane or mutation plane.
6. **CAPI is separate.** Existing Meta CAPI artifacts do not constitute Meta Ads capability.
