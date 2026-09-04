# Remaining Risks

- Official reference pages for several object refs were partially rate-limited by scraper; core v26 changelog and overview were read, but executor should re-open individual object refs before coding exact field allowlists.
- No real Meta account/readiness/token was available or accessed.
- n8n legacy workflows were not readable in this environment.
- Two local reference input sets are now available to the executor but were not bulk-ingested. Selected files still require inventory, hashes and provenance before their content can support implementation claims.
- v26 examples in some docs still show older version URLs; contracts pin behavior to v26 changelog and require implementation-time recheck.

## Delegated evidence refinements

- v9 traffic inventory tables are Google-shaped in concrete identity columns; future migrations must avoid direct Meta insertion into those columns without a platform-aware design.
- Access-tier production readiness depends on Meta App Review / Full Access; Limited access is not sufficient for production advertiser operations.
- Asset Feed Spec has official count limits that must be enforced before any future adcreative submit.
- The contract now specifies the provider/account/object-level Insights grain, exact v9/v10 reuse boundaries, `criativo_master` reuse and capability mapping. The current v15 slice covers hierarchy/read-sync only; Insights, upload and full ad-creative temporal history remain NEXT schema.
