# Programa de profissionalização do VOLC O.S.

## Norte

Clareza, segurança e escala sem reescrita total. Cada onda precisa ser pequena,
reversível, medida pelo Mapa Vivo e encerrada com gates verdes.

## Onda zero — fronteiras e contenção

Status: **executada em 22/08/2026**.

- raiz reduzida a `README`, `CLAUDE`, `AGENTS` e `PRODUCT`;
- documentação vigente separada de arquivo e referência;
- SQL solto da raiz classificado em diagnóstico ou arquivo;
- scripts legados de campaign highlights bloqueados;
- `.venv-graphify`, gerados e arquivo histórico fora do grafo corrente;
- duplicatas exatas Google Ads consolidadas;
- inventário Markdown/SQL automatizado;
- scanner de segredos incorporado ao pipeline;
- chave legada exposta removida do working tree e rotação registrada como P0.

## Onda um — linhagem SQL

Objetivo: saber qual SQL foi aplicado, qual foi substituído e qual é apenas teste.

1. medir funções, views, triggers e tabelas no Supabase self-hosted em read-only;
2. cruzar o catálogo vivo com os nós SQL do Graphify;
3. criar manifesto `src/sql/MANIFEST.json` com ordem, estado, checksum e ambiente;
4. resolver famílias nominais (`FINAL`, `WORKING`, `fixed`, `v2`, `v3`);
5. separar migrations, diagnostics, validations, backfills e rollbacks;
6. arquivar somente versões comprovadamente substituídas;
7. criar gate que impeça duas migrations com a mesma identidade lógica.

Entrada medida: 50 SQL ainda sem linhagem e 8 scripts fora da linha principal que
exigem revisão. Arquivos destrutivos não serão executados para descobrir seu estado.

## Onda dois — testes, mocks e artefatos

Objetivo: diferenciar especificação executável de resíduo.

1. inventariar runners reais: Vitest, Pytest, testes do `volc_ads` e FunnelForge;
2. padronizar nomes e discovery sem mover tudo de uma vez;
3. separar mocks de runtime, fakes de teste, fixtures e golden files;
4. retirar resultados gerados do versionamento quando forem reproduzíveis;
5. registrar cobertura por domínio e smoke tests mínimos;
6. excluir apenas testes redundantes cujo comportamento esteja coberto.

## Onda três — Clean Architecture por domínio

Objetivo: reduzir acoplamento sem quebrar jornadas.

Ordem sugerida:

1. Tráfego e nascimento de campanha;
2. Redator/Publicação;
3. Descoberta/Pautador;
4. Medição/Monetização;
5. Decisão/Atuação;
6. Governança e plataforma.

Em cada domínio: identificar regras, casos de uso, portas, adapters e presentation;
criar testes de caracterização; mover um fluxo vertical; manter facade temporária;
medir impacto no grafo; aposentar a facade somente quando não houver consumidores.

## Onda quatro — blindagem operacional

- rotação das credenciais registradas em `docs/security/SECURITY-ACTIONS.md`;
- secret scanning no CI e proteção de branch;
- build, Vitest, Pytest e inventário como checks obrigatórios;
- manifesto de migração SQL e dry-run;
- dependency audit e atualização controlada;
- headers/CSP e revisão de superfícies administrativas;
- observabilidade, recibos, idempotência e rollback por rotina crítica;
- política de release e changelog arquitetural.

## Definição de pronto de uma onda

- inventário atualizado;
- paths e links corrigidos;
- nenhum segredo forte no working tree;
- build e testes relevantes verdes;
- dívida pré-existente separada de regressão;
- grafo reconstruído e `--check` atual;
- rollback documentado;
- mudanças versionadas em commit dedicado.
