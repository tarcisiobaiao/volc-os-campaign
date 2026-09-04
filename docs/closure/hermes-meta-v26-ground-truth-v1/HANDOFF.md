# Handoff

Start implementation from this corrected contract only after reviewing official Meta v26 object refs again and approving the isolated v15 identity/read-model slice, tenancy and secret-broker decisions. Do not resolve Meta credentials in browser. Implement/review schema and read-only sync first, then local validation, then request separate authorization for any Meta validate/upload/create.

Recommended first command:

```bash
python3 -m json.tool docs/closure/hermes-meta-v26-ground-truth-v1/META-V26-CAPABILITY-MATRIX.json >/dev/null
```

## Delegated audit addendum

Before coding, inspect these seams first:

1. `backend/app/trafego/ledger.py::volc_campaign_id_de()` — currently Google-only.
2. `backend/app/trafego/contrato_canais.py::contrato()` — currently returns Google manifests.
3. The deployed v9 and v10 migration files — v9 is Google-shaped; v10 is a reusable workflow seam but its exact keys/FKs must not be invented.
4. `src/components/trafego/hub/adaptacao.ts` — preserve existing rule: never query Google inventory pretending it is Meta.
5. `criativo_master` (v11) and Cofre Meta objects (v13) — reuse them instead of creating duplicate asset or token authorities.

Canonical UI selection is `rede=meta`; `plataforma=meta` is only a normalized input alias.
