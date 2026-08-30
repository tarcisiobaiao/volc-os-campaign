# Política de higiene do repositório

## Objetivo

Manter o VOLC O.S. claro, seguro e escalável sem apagar comportamento útil. A
organização é guiada por domínio, evidência e reversibilidade — não por estética.

## Autoridade por tipo

| Tipo | Local esperado | Regra |
|---|---|---|
| instrução de projeto | raiz (`README`, `CLAUDE`, `AGENTS`, `PRODUCT`) | curta e vigente |
| arquitetura | `docs/architecture/` | decisão e trade-off explícitos |
| especificação | `docs/` ou `docs/superpowers/specs/` | escopo e aceite |
| auditoria | `docs/audits/<domínio>/` | datada; não misturar ao runtime |
| histórico | `docs/archive/` | sem autoridade operacional |
| referência externa/gerada | `docs/reference/` | origem e data declaradas |
| migração SQL | `src/sql/<linha>/` | ordem, pré-condição e idempotência claras |
| diagnóstico SQL | `sql/diagnostics/` | read-only por padrão |
| SQL de incidente/one-off | `sql/archive/` | bloqueado para aplicação automática |
| prompt consumido em runtime | junto do módulo consumidor | coberto por teste/contrato |
| relatório gerado | `entregaveis/` ou área ignorada | nunca editar como fonte |

## Estados de arquivo

- `active`: consumidor e finalidade atuais comprovados;
- `compatibility`: necessário enquanto uma ponte antiga existir;
- `migration`: executado em sequência controlada;
- `reference`: consultivo, não executável;
- `generated`: reproduzível por script;
- `archived`: histórico sem autoridade atual;
- `candidate`: faltam evidências; não remover;
- `dead-proven`: nenhum consumidor, substituto presente e gates verdes.

## Gate para mover ou excluir

1. Consultar Graphify (`explain`, `affected`, `path`).
2. Procurar imports, strings de path, rotas, scripts e workflows com `rg`.
3. Verificar se o Git conhece o arquivo e se há duplicata por hash.
4. Identificar substituto, dono, risco e rollback.
5. Mover primeiro quando houver valor histórico; excluir apenas `dead-proven`.
6. Corrigir referências no mesmo lote.
7. Rodar build/testes do domínio e reconstruir o grafo.

## SQL blindado

- nunca executar um arquivo porque se chama `FINAL`, `FIXED` ou `APLICAR`;
- diagnósticos devem ser `SELECT`-only, salvo aviso explícito;
- `DELETE`, `DROP`, `TRUNCATE`, backfill e `CREATE OR REPLACE` exigem revisão;
- migrações aplicadas são imutáveis; uma correção vira nova migração;
- cada linha de migração precisa de README com ordem e estado do ambiente;
- o schema vivo é medido em modo read-only antes de qualquer mutação.

## Ondas de profissionalização

1. **Onda zero:** fronteiras, índices, arquivo histórico e scripts soltos.
2. **Onda um:** SQL versionado, status aplicado/pendente e remoção de versões nominais.
3. **Onda dois:** testes, mocks, fixtures e relatórios gerados.
4. **Onda três:** fronteiras de domínio e adapters de compatibilidade.
5. **Onda quatro:** segurança, observabilidade, CI e políticas de release.

Cada onda deve terminar com inventário, gates e Mapa Vivo atualizados.
