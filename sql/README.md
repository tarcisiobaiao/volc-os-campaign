# SQL fora da linha principal

Esta pasta não é uma sequência automática de migrações.

- `diagnostics/` — consultas preferencialmente read-only;
- `archive/` — incidentes, correções one-off e scripts destrutivos preservados;
- arquivos ainda na raiz de `sql/` aguardam classificação na próxima onda.

As migrações do produto permanecem em `src/sql/` até a consolidação da linha
versionada. Antes de executar qualquer SQL, leia o cabeçalho, confirme o schema vivo
e procure uma versão posterior ou um README de sequência.
