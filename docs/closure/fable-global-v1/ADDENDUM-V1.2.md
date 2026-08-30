# ADDENDUM V1.2 — execução factual da fila de recuperação

*2026-08-29 · branch `integration/global-closure-20260829`*

Este addendum substitui fatos operacionais da v1.1 que envelheceram durante a
própria janela. Ele não promove tarefas e não autoriza ação externa.

## Estado consolidado

| Item da v1.1 | Estado agora | Prova |
|---|---|---|
| RQ-01 — snapshot | **executado** | main original preservada; árvore suja inventariada; origem pública identificada |
| RQ-02 — fast-forward | **executado em integração isolada** | base incorporada até `5b92b94`, incluindo os fixes de venv; gates amplos verdes |
| RQ-03 — preservar colheita | **superado por preservação mais forte** | os quatro diffs deixaram de ser WIP frágil e ganharam candidatos commitados |
| ORAKUL Predictive | **aceito e integrado como experimento offline** | `ee0dfe1` + `e6a4fd6` + `9720550`; 63/63 na integração |
| Fronteira Criativa S0 | **aceita e integrada** | `e776da0` + `1415713`; tenant preservado no pós-despacho |
| Demand Gen | **aceito e integrado, ainda sem criação produtiva** | `ca308d3` + `bdf218e`; fronteira HTTP fail-closed |
| Ratchet pytest | **rejeitado** | candidato alterava `pytest.ini` para coletar `teste_*`, proibido pela M-W2-03 |
| Search diagnóstico Gemini | **rejeitado; correção em curso** | consultava tabelas/colunas inexistentes e colapsava falha/ausência em 404 |
| PMax Gemini | **rejeitado; correção em curso** | campos GAQL v25 inexistentes, zero fabricado, Brand Guidelines ausente e limites incorretos |
| Health/deadman Gemini | **em revisão independente** | nenhum merge antes do veredito |
| RQ-10 — Roadmap/curadoria/grafo | **aguarda convergência técnica** | será uma única passada após Search, PMax e harnesses |

## Gates da integração já medidos

- `volc_ads`: **533 passed**;
- ORAKUL de baseline: **36 passed**;
- backend completo: **1406 passed, 53 skipped** fora do sandbox; a primeira
  execução no sandbox falhou em `initdb`, portanto não foi tratada como
  regressão;
- frontend TypeScript: **76 erros**, exatamente o baseline;
- Vite build: verde;
- ORAKUL Predictive após integração: **63 passed**.

## Correções à narrativa anterior

1. O alvo autônomo não parou em `bdf9e1c`: avançou de forma limpa até
   `5b92b94`, que torna a seleção do venv explicitamente restrita ao projeto
   primário.
2. Os candidatos da colheita já não dependem de patches soltos. Não há razão
   para executar `git clean`, remover worktrees ou repetir RQ-03.
3. “Gates verdes” não significou “aceito”: Search e PMax foram recusados por
   defeitos que as suítes dos autores não modelavam.
4. O QG não deve subir percentuais por quantidade de commits. Demand Gen e
   ORAKUL continuam, por contrato, parciais; o percentual só muda no RQ-10
   quando cada aceite factual for reconciliado com a fonte viva.
5. `origin` aponta para um repositório **público** e está centenas de commits
   atrás. RQ-11 permanece proibido até o dono fornecer um destino privado e
   autorizar explicitamente o backup.

## Próxima fila, já reordenada

1. concluir correção e revisão Search;
2. concluir correção e revisão PMax;
3. concluir revisão Health/deadman;
4. revisar `6fc7923` (cancelamento/limpeza do harness);
5. integrar seletivamente o supervisor contínuo, sem importar Roadmap,
   curadoria ou grafo gerado defasados;
6. integrar o harness Gemini depois do supervisor e resolver a sobreposição
   serialmente;
7. executar gates consolidados em árvore limpa;
8. reconciliar uma vez o Roadmap Vivo, a curadoria humana e o grafo híbrido;
9. validar o QG em `localhost:8080`;
10. somente depois decidir merge na main e backup privado.

## Decisões humanas ainda intactas

- **D9**: URL do repositório privado e autorização de push;
- **H1**: confirmação dos vínculos Maquininha e FGTS;
- **D1/D4/D10**: migrations e janela de segurança que antecedem escrita real;
- **D5**: `validate_only` real contra a conta de teste.

Nenhuma migration, escrita no Supabase, Google Ads, n8n, push ou deploy foi
executada nesta convergência.
