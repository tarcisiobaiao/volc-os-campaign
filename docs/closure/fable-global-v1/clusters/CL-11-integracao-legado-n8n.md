# CL-11 · Integrações e legado n8n / Supabase hosted

**Horizonte**: A tardio / B · **Resultado**: cada rotina crítica usa o banco
oficial, deixa recibo, e o legado morre com sucessor nomeado — nunca por
substituição cega de URL.

## Estado factual (F018, F019, F029)

- 13 flows do núcleo (8 receita + 5 custo) escrevem no hosted legado; 271
  referências n8n ao hosted registradas como dívida no ADR.
- Snapshot n8n é de 19/08 (defasado); instância tem 396 workflows.
- Orientações: front lê `orientacao_*` no oficial; workflow ativo grava v2.1
  no legado (P09-T07).
- Code nodes carregam contas/domínios/thresholds/fórmulas (P10-T08 todo).
- Disputa de triggers BEFORE INSERT em revenue_converted; câmbio 04 BLOQUEADA (**D11**).

## Missões

| ID | O quê | Onda | Portão |
|---|---|---|---|
| M-W3-14 | Reinventariar n8n vivo (read-only API) e reclassificar estado declarado → medido | 3 | acesso n8n |
| M-W3-07 | (compartilhada) custo D0/D-1 migra para o contrato canônico | 3 | D3 |
| M-W4-12 | Receita GAM/JoinAds: migração rotina a rotina com dupla escrita provada e recibo | 4 | D11 |
| M-W4-13 | Resgate `orientacao_*`: dump sanitizado do legado, diff objeto a objeto, sucessor no ledger oficial | 4 | acesso legado |
| M-W4-14 | Retirar config/inteligência sensível dos Code nodes (job_id + DTO mínimo) | 4 | — |

## Regra dura

Nenhum consumidor legado migra por troca cega de URL (regra do AGENTS.md);
cada aposentadoria registra sucessor e rollback; dados nunca são promovidos
automaticamente entre bancos.
