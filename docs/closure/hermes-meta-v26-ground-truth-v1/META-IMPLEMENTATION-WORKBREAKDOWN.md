# Meta Implementation Work Breakdown

| Order | Work | Files candidates | Size | Parallel? | Acceptance |
|---|---|---|---|---|---|
| 1 | Schema migration from draft | `supabase/migrations/v15_*` | M | no | SQL tests/RLS/grants pass |
| 2 | Domain contracts | `backend/app/trafego/meta_*` | M | partly | pydantic/dataclass validation tests |
| 3 | Secure onboarding/readiness | `backend/app/trafego/meta_credenciais.py`, settings API | M | partly | no token leaves backend; readiness states covered |
| 4 | Read-only sync adapter | `backend/app/trafego/meta_sincronizador.py` | L | after 1/2 | mocked Graph pagination/freshness/read models pass |
| 5 | Frontend read model | `/trafego?plataforma=meta` components | M | after API contract | not-configured/stale/error/empty states tested |
| 6 | ZIP manifest import | creative/asset module | M | parallel with 4 | zip-bomb/path traversal/MIME tests pass |
| 7 | Blueprint/local validation | backend meta builder | L | after 2/6 | v26 rules and capability blocks pass |
| 8 | Future create PAUSED executor | separate authorization | L | no | receipt/read-back/idempotency in sandbox/real approved mission |

First useful proof: mocked read-only sync of Campaign → Ad Set → Ad → Creative into private read model with freshness and no tokens.

## Corrections from delegated AS-IS audit

Add before schema migration:

| Order | Work | Files candidates | Size | Sequential reason |
|---|---|---|---|---|
| 0 | Decide v9-vs-v10 integration seam | `supabase/migrations/v9_*`, `v10_*`, `backend/app/trafego/ledger.py` | M | v9 identity is Google-shaped; v10 is Meta-aware. |
| 0.5 | Implement Meta identity derivation/read closing | `backend/app/trafego/ledger.py`, Meta synchronizer | M | Successful Meta receipts cannot close canonical campaigns while ledger is Google-only. |
| 0.6 | Preserve no-fake Meta UI states | `src/components/trafego/hub/adaptacao.ts`, server read models | S | Browser must not invent zero inventory for unread Meta accounts. |
