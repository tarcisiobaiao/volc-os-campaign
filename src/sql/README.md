# Linha SQL do produto

Esta pasta contém migrações, funções, validações e SQL histórico ainda em
consolidação. As linhas com ordem explícita são:

- `pautador/` — evolução do Pautador/Redator;
- `joinads/` — ingestão JoinAds;
- `volc-sync/` — sincronização controlada com o upstream;
- `v6_*` e `v7_*` — sequências legadas versionadas na raiz desta pasta.

## Regras

1. Não escolha por sufixos como `FINAL`, `WORKING`, `fixed` ou `v2`.
2. Não edite uma migração comprovadamente aplicada; crie a próxima etapa.
3. Separe migração, diagnóstico, validação e rollback.
4. Documente pré-condição, efeito, idempotência e verificação.
5. SQL destrutivo deve falhar fechado e exigir confirmação explícita.
6. O status aplicado/pendente será inventariado na onda SQL antes de novos moves.

`volc-sync/04_monthly_exchange_rate.BLOQUEADO.sql` permanece bloqueado: consulte o
README local. A presença do arquivo não autoriza sua aplicação.
