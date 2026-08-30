# Handoff de curadoria — bancada criativa, achados #10, #13, #15 e #16

> **Proposta**, não aplicação. Nada aqui foi escrito no Roadmap Vivo nem na
> curadoria humana. A promoção para `done` fica para depois da integração e da
> revisão Codex, conforme o protocolo.

- **Worktree:** `/private/tmp/volc-template-lab` · **branch:** `feat/estudio-template-lab`
- **HEAD inicial:** `e0d9c912bb52bee2c248a5efd1c2584a5732e200` (árvore limpa)
- **HEAD final:** `99daa09`
- **Data:** 2026-08-29

## Commits por assunto

| SHA | Assunto | Achados |
|---|---|---|
| `87d5395` | hook de acompanhamento: geração, escopo por execução e refresh pendente | #15, #16 |
| `f72aa19` | operário: bandeira de lease consumida, diretório por reivindicação | #13 |
| `e03da7c` | provas SQL sob papéis reais, com SQLSTATE específico | #10 |
| `0d198d2` | achados altos da revisão adversarial (zumbi, lease, posse, recibo forjável) | #10, #13 |
| `3fa0fd7` | cada recusa declara código **e** guarda | #10 |
| `99daa09` | identidade viaja com a peça (frame intermediário) | #15 |

## Capacidades afetadas

| Capacidade / tarefa | Estado anterior | Estado proposto | Prova |
|---|---|---|---|
| Execução criativa `v11_03` — segurança | `partial` (provas de catálogo) | `partial` → candidato a `done` **após revisão Codex** | ciclo 129/0 com 29 provas comportamentais sob 4 papéis; 3 contraprovas |
| Bancada — lease e operário zumbi | `partial` | `partial` → candidato a `done` | 9 provas de corrida sem sleep; 6 mutantes mortos |
| Bancada — acompanhamento na tela | `partial` | `partial` → candidato a `done` | 20 provas do hook; 3 mutantes mortos |
| Recibo como prova (imutabilidade) | **não coberto** | novo invariante, provado | 4 forjas reproduzidas e barradas |

Mantenho todas como `partial` na proposta: os quatro achados estão fechados com
prova, mas o protocolo do projeto pede revisão Codex e integração antes de `done`,
e há pendências explícitas abaixo.

## Critérios demonstrados

1. **#10** — as provas distinguem, com SQLSTATE e nome de guarda: `42501` (grant),
   zero linhas sem erro (RLS), `23000` (gatilho de negócio), `23514`/`23505`
   (CHECK/unique nomeados) e `42P01`/`42703`/`42601`/`42883` (**prova quebrada**,
   nunca verde). O papel privilegiado nasce com `BYPASSRLS`, como o de produção
   — medido em `pg_roles` no Supabase oficial, só leitura.
2. **#13** — a bandeira `perdeu_o_trabalho` é consumida em dois checkpoints e tem
   prova que a isola do veredito do depósito; o diretório passou a ser por
   reivindicação; o operário que perde o lease não transiciona, não grava recibo
   e não toca no diretório alheio.
3. **#15** — nenhuma resposta de A altera estado de B ou C, e nenhum render
   intermediário mostra a peça de A sob o id de B.
4. **#16** — refresh durante consulta em voo não se perde, coalesce e não repolla
   trabalho terminal.

## Lacunas restantes (explícitas)

| # | Lacuna | Severidade | Por que não foi fechada aqui |
|---|---|---|---|
| L1 | `_mensagem_para_o_operador` sanitiza só caminho Unix; `C:\...` e UNC passam | média | Fora dos quatro achados. A migration já barra esses formatos no banco (`mensagem_sem_caminho`), mas a fila SQLite não. Corrigir exige tocar a fronteira de mensagem, que não pertence a esta missão. |
| L2 | `leituraFalhou` e pausa do polling não são anunciados por leitor de tela | média | O defeito está em `Producao.tsx`, cuja edição a missão restringe a "estritamente necessário". Não é necessário para fechar #15/#16. |
| L3 | Diretório de falha permanente e de gate reprovado não é limpo | baixa | Comportamento herdado, fora dos quatro achados; nenhum recibo aponta para esses arquivos. |
| L4 | `inicial` do hook não tem segundo consumidor | baixa | Remover é mudança de API pública do hook, sem relação com os achados. |

## Arquivos tocados

```
backend/app/criativo/bancada/operario.py
backend/app/criativo/bancada/deposito.py
backend/tests/test_criativo_bancada.py
scripts/provar-ciclo-v11_03.sh
scripts/provas-v11_03.sql
scripts/provas-papeis-v11_03.sql          (novo)
supabase/migrations/v11_03_execucao_criativa.sql
supabase/migrations/v11_03_rollback.sql
src/hooks/useTrabalhoDaBancada.ts
src/components/criativos/__tests__/polling-da-bancada.test.tsx
```

## Gates

| Gate | Baseline (origem) | Agora |
|---|---|---|
| Ciclo `v11_03` (cluster descartável) | 95 provas | **129 · 0 falhas** |
| `backend/tests` + `volc_ads` | 1838 (medido em `e0d9c91`, worktree temporário) | **1847** |
| Frontend Criativos + hooks | 119 | **129** |
| Frontend completo | 902 (7 arq./2 testes falhos) | **912** — falhas **idênticas** ao baseline |
| TypeScript (`tsc -p tsconfig.app.json`) | 77 | **77** |
| `npm run build` | verde | verde |
| `git diff --check` | limpo | limpo |

## Envelope respeitado

- Google Ads: **0** chamadas · Supabase oficial: **0** escritas, **0** migrations
  (verificado: `criativo_render_%` não existe em produção) · deploys: **0** ·
  pushes: **0** · `FORGE_PERMITIR_ESCRITA`: **ausente**.
- Única consulta ao banco real: leitura de `pg_roles` para medir `rolbypassrls`.
- Varredura de segredo no diff: nenhuma credencial, token ou chave.
