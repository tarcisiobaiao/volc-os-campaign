# HANDOFF — Meta Real Read Model V1

Verdict targets:

- `META_REAL_READ_PREVIEW_READY`
- `META_READ_MODEL_RUNTIME_READY`

These mean code is ready for a later real proof. They do **not** mean a migration was applied, inventory was persisted, a real Meta account was read by Hermes, or any campaign was created.

## Base

- Remote base: `origin/execution/volc-os-operacao-80-20`
- Base SHA: `462e2ff9f7e9c4638d84e6f6adfcfccd1e75037d`
- Branch: `sprint/hermes-meta-real-read-model-v1`

## What changed

- Evolved local Meta discovery from masked-only output to stable opaque account references.
- Added backend resolution rule: every opaque reference is resolved by re-reading accessible accounts internally.
- Added local ADMIN endpoints for account discovery, read-only preflight, sync preparation and last preview receipt.
- Connected the local Keychain credential seam to the existing read-only adapter contract through in-memory token objects.
- Extended the adapter to read/paginate Campaign → Ad Set → Ad → Creative, plus preflight checks for pages, Instagram, pixels/datasets and insights.
- Added typed Meta insights/actions domain objects and row mapping that preserves `NULL` and does not flatten actions.
- Added draft-only migrations for insights read model and rollback; they were not applied.

## Endpoints

```text
GET  /api/trafego/meta/local/contas
POST /api/trafego/meta/local/preflight
POST /api/trafego/meta/local/sincronizacao/preparar
GET  /api/trafego/meta/local/recibo/ultimo
```

Existing token setup endpoints remain local/admin-only:

```text
GET    /api/trafego/meta/local/configuracao
POST   /api/trafego/meta/local/configuracao
POST   /api/trafego/meta/local/testar
DELETE /api/trafego/meta/local/configuracao
```

No route creates, updates, deletes, enables, validates remotely or uploads Meta objects.

## Runtime proof path for a future local operator

1. Run backend on macOS localhost with authenticated ADMIN session.
2. Ensure token exists in Keychain service `br.com.agenciavolc.volc-os.meta-system-user`, account `supabase-user:{sub}`.
3. Call `GET /api/trafego/meta/local/contas`.
4. Select only `referencia_opaca` from response.
5. Call `POST /api/trafego/meta/local/preflight` with the opaque reference.
6. If preflight is healthy, call `POST /api/trafego/meta/local/sincronizacao/preparar`.
7. Do not persist until v15_01/v15_02 are reviewed/applied in a separately authorized Supabase mission.

## Remaining blocks

- No Supabase migration was applied.
- The persistence adapter is still in-memory/contractual; official Supabase transaction implementation remains future work.
- No real Meta account read was performed in this Hermes environment.
- Frontend binding is intentionally untouched because Claude Sonnet owns visual parity.
- Meta create/update/delete remains absent by design.
