# Gates

- `backend/.venv/bin/python -m pytest backend/tests/test_trafego_meta_*.py -q`: 24 passed.
- `npx vitest run` no recorte Hub/alertas: 45 passed.
- `npm run build`: passou.
- TypeScript: zero erros nos arquivos tocados; o baseline global herdado permanece vermelho.
- `bash scripts/provar-ciclo-v15_01-meta.sh`: passou em PostgreSQL 15 descartável.
- JSON do pacote Meta: 17 documentos válidos.
- `git diff --check`: passou.
- zero chamada Meta, zero Supabase oficial, zero migration, zero deploy.

