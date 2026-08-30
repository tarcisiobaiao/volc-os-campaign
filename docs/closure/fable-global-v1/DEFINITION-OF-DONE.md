# Definition of Done — Fechamento Global VOLC O.S. (fable-global-v1)

Base: HEAD `e858651a5a0c46087bf10365ebf44f7b0e8c42e3` · 2026-08-29
Autoridade de processo: `AGENTS.md` (protocolo de fechamento) e `CLAUDE.md`.

Este documento define quando uma tarefa, missão ou cluster pode ser declarado
concluído. Ele existe porque o padrão de falha dominante neste repositório não é
código ruim — é **código pronto tratado como produto pronto**. O Roadmap Vivo já
usa a escada `todo → partial → risk → done`; este DoD torna binária a passagem
para `done`.

## 1. Escada de estados que NUNCA se colapsam

Estas distinções são obrigatórias em qualquer prova, recibo ou handoff. Um item
mais abaixo na escada nunca prova um item acima:

1. **código presente** — o arquivo existe no worktree/branch;
2. **teste existente** — arquivo de teste cobre o comportamento;
3. **teste executado** — comando + saída registrados (contagem exata, não "verde");
4. **commit existente** — SHA identificável;
5. **commit alcançável pela main** — `git merge-base --is-ancestor SHA main`;
6. **funcionalidade integrada** — rota/registro/import ativos, não órfãos;
7. **disponível em localhost** — visível via `./start-dev.sh` sem passo manual oculto;
8. **migration escrita** — arquivo SQL + rollback no repo;
9. **migration aplicada** — evidência de execução no Supabase oficial (recibo, query de verificação);
10. **dado sintético** — fixtures, cluster descartável, cliente falso;
11. **shadow com dado real** — dado da conta/banco real atravessou o contrato, sem mutação;
12. **produção operacional** — rotina contínua ativa, com owner, heartbeat e recibo.

Regra dura: **ausência ≠ zero medido ≠ falha ≠ indisponível ≠ não aplicável ≠
vazio confirmado**. Qualquer contrato, tela ou ledger que colapse dois desses
estados reprova no gate (o padrão v12_01 — `vazio_confirmado=0` distinto de
`falhou`/`null` — é o piso, não o teto).

## 2. DoD global (aplica-se a toda missão)

Uma missão só está `done` quando TODOS os itens aplicáveis abaixo têm evidência
citável (caminho + comando + saída). "Não aplicável" deve ser declarado por
item, com motivo — nunca por omissão.

| # | Dimensão | Critério binário |
|---|---|---|
| G1 | Contrato | Tipos/schema/ADR do dado ou da API existem e são citados pela implementação |
| G2 | Implementação | Código na branch da missão, dentro do ownership declarado |
| G3 | Testes | Novos comportamentos têm prova nova; contagem antes/depois registrada |
| G4 | Contraprova | Pelo menos um teste prova que o caminho errado FALHA (fail-closed) |
| G5 | Gates herdados | `npx tsc --noEmit -p tsconfig.app.json` não piora o baseline de 76 erros; suíte relevante não perde nenhum teste que passava |
| G6 | Banco real | Se a missão alega persistência: query de verificação no Supabase oficial ou declaração explícita "não aplicado — aguarda autorização" |
| G7 | Frontend | Se a missão alega superfície: rota registrada e estado renderizado, incluindo os estados de ausência |
| G8 | Observabilidade | Execução deixa recibo/ledger consultável; falha silenciosa impossível no caminho novo |
| G9 | Segurança operacional | Zero segredo em código, doc, recibo ou prompt; zero mutação externa fora do envelope autorizado |
| G10 | Documentação | ADR/SPEC/README tocados quando o comportamento público mudou |
| G11 | Integração | Commit alcançável pela branch de integração declarada; trabalho preso em worktree não conta |
| G12 | Fonte humana | Delta de curadoria/roadmap PROPOSTO no handoff (nunca aplicado direto por worker paralelo) |
| G13 | Rebuild do grafo | Após integração material: pipeline `scripts/atualizar_grafo_volc_os.py` + `--check` (responsabilidade do integrador único, não do worker) |
| G14 | Mutação não autorizada | Diff da missão auditado: nenhum arquivo fora do `allowed_paths`, nenhum processo/banco/API externo tocado |

## 3. DoD por cluster

Cada cluster (ver `clusters/`) adiciona critérios específicos sobre o DoD
global. Resumo dos aditivos:

### CL-A · Convergência e autoridade (integração de branches)
- A branch integrada passa os gates DEPOIS do merge, não só antes.
- Toda branch consumida é registrada no `INTEGRATION-LEDGER.md` com decisão:
  `integrada`, `superada`, `descartada com motivo` ou `pendente com dono`.
- Worktrees consumidas são listadas para remoção — mas a remoção em si exige
  confirmação do dono (nenhuma missão apaga worktree de outra).

### CL-B · Lançamento Search (caminho do caixa)
- Nenhuma mutação real sem: validate_only aceito + aprovação humana registrada +
  recibo em_voo antes da rede + verificação posterior por releitura.
- Conta-laboratório (Portal Mundo Mais 547-809-6539) e conta financeira
  (Crédito Up) jamais se confundem no mesmo fluxo.
- Timeout NUNCA oferece reenvio (lição do canário de 28/08).

### CL-C · Dados e ingestão (Supabase oficial)
- Migration só é "aplicada" com recibo de execução + query de contraprova.
- Uma única autoridade de agenda por rotina (n8n OU worker; nunca ambos).
- Chave canônica conta+campanha+data+segmento; dinheiro em micros com moeda.

### CL-D · Decisão e ORAKUL
- Fato, recomendação, proposta, autorização, aplicação e rollback são objetos
  distintos; nenhum estágio pula o anterior.
- Replay não enxerga futuro; shadow declara janela; T2/autonomia exige ADR.

### CL-E · Frontend operacional
- Estado de ausência renderizado explicitamente (nunca "tudo certo" por falta de dado).
- Baseline tsc 76 não piora; build Vite verde; a11y/contraste não regridem.

### CL-F · Criativos e assets
- Linhagem por bytes (sha256), nunca por nome; divergência rebaixa a
  `desconhecida`, jamais promove.
- Peça só é "verificada" após releitura dos bytes no destino.

### CL-G · Harness e agentes
- Run só é "concluído" com veredito dos reviewers + gates verdes + handoff.
- "Agente terminou" ≠ "produto pronto": exige classificação no ledger de
  integração.

## 4. Anti-padrões que reprovam automaticamente

- Promover tarefa a `done` citando apenas existência de código ou de branch.
- Prova que aceita qualquer erro (try/except silencioso em gate, teste sem assert).
- Percentual de progresso sem fórmula declarada (a fórmula oficial é a de
  `status_weights` do ROADMAP-VIVO.json, aplicada sobre tarefas não-reserved).
- "Verde" sem contagem (quantos testes? quais? comando exato?).
- Migração aplicada "porque o arquivo existe em supabase/migrations/".
- Marcar a fonte compartilhada (Roadmap/curadoria) a partir de uma worktree
  não integrada.
- Colapsar ausência/zero/falha/não-aplicável em qualquer camada nova.
