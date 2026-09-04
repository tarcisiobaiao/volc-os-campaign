# GATES — Meta Real Read Model V1

## Commands executed

```bash
python3 -m pytest backend/tests/test_meta_configuracao_local.py backend/tests/test_meta_real_read_model.py -q
python3 -m json.tool docs/closure/hermes-meta-real-read-model-v1/CONTRACT.json >/dev/null
python3 -m json.tool docs/closure/hermes-meta-real-read-model-v1/CURATION-HANDOFF.json >/dev/null
python3 scripts/verificar_segredos.py
git diff --check
```

## Assertions covered

- Opaque account reference is stable and does not expose raw account id.
- Unknown opaque reference is refused after internal account re-read.
- Fake Keychain/resolver keeps token only in memory; secret repr is redacted.
- Campaign/adset/ad/creative pagination is read completely.
- Page-2 failure does not apply absence and does not erase last good read.
- Insights preserve `NULL` metrics.
- Actions remain separate rows and are not flattened into daily metric columns.
- Token does not appear in response, URL, log assertion or exception body in focal tests.
- Router contains no mutate/create/activate route names.
- SQL and rollback for insights are structurally coherent.
- Roadmap, graph, curation and frontend remain untouched.

## Result

Latest focal result:

```text
12 passed, 5 warnings
```

Warnings are pre-existing project warnings/deprecations plus pytest config noise; no warning exposed a token or indicates a Meta network call.

## External effects

- Zero Meta real call in tests.
- Zero Meta mutate.
- Zero Meta validate real.
- Zero Supabase write.
- Zero migration applied.
- Zero frontend edit.
- Zero Roadmap/graph/curation edit.
