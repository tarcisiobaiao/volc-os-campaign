# Gates

- Python focal: `47 passed`.
- Frontend focal: `2 files, 4 tests passed`.
- Vite build: passou.
- `git diff --check`: passou.
- scanner de segredos: nenhum padrão forte.
- PostgreSQL 16 descartável: apply → aprovação → preparo → fechamento → retry
  idempotente → recibo sanitizado → rollback passou.
- Auditoria de rotas: compile e validate-only montados; create, approve e
  activation ausentes.
- Contraprovas: flag fechada recusa antes de token/rede; conta inativa é
  recusada; categoria especial é recusada; inventário público não contém IDs
  brutos nem image hash.

Não executado: Meta validate-only real, Meta mutate, Supabase oficial, migration
oficial, deploy, n8n e WordPress.
