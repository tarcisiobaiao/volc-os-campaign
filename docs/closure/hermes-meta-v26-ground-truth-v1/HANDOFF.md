# Handoff

Start implementation from this package only after reviewing official Meta v26 object refs again. Do not resolve Meta credentials in browser. Implement read-only sync first, then local validation, then request separate authorization for any Meta validate/upload/create.

Recommended first command:

```bash
cd /root/work/volc-runs/hermes-meta-v26-ground-truth-v1
python3 -m json.tool docs/closure/hermes-meta-v26-ground-truth-v1/META-V26-CAPABILITY-MATRIX.json >/dev/null
```

## Delegated audit addendum

Before coding, inspect these seams first:

1. `backend/app/trafego/ledger.py::volc_campaign_id_de()` — currently Google-only.
2. `backend/app/trafego/contrato_canais.py::contrato()` — currently returns Google manifests.
3. `supabase/migrations/v9_01_trafego_inventario.sql` vs `v10_01_intencao_e_lote.sql` — v9 is Google-shaped, v10 is the safer Meta entrypoint.
4. `src/components/trafego/hub/adaptacao.ts` — preserve existing rule: never query Google inventory pretending it is Meta.
