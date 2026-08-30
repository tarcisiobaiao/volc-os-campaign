# Convergência global — 29 de agosto de 2026

## Resultado executivo

Esta convergência junta somente entregas aceitas e verificadas em uma árvore limpa. Ela não transforma laboratório em produção e não incorpora automaticamente toda branch existente.

O percentual editorial continua sendo calculado sobre o universo inteiro conhecido. Depois da reconciliação, há 145 tarefas: 32 concluídas, 33 parciais, 1 com risco, 68 a fazer e 11 reservadas. As reservadas ficam fora do denominador. O índice ponderado é 48,75 de 134, ou 36,4%. O número não mede horas nem commits; mede tarefas que satisfizeram o aceite declarado. A expansão do mapa pode manter ou reduzir o percentual mesmo quando capacidades novas são entregues.

## Entregas integradas

| Frente | Origem | Integração | Provas principais | Estado honesto |
| --- | --- | --- | --- | --- |
| QG/Kanban legível | `agent/deepseek-qg-kanban-v4` · `4430a4f` | `c33f4ae` | 53 testes QG e build Vite | Concluída; não muda a autoridade da fonte |
| Decision Lab L6 | `feat/decision-intelligence-ui-l6` · `3f9e22a`, `9c1c907` | `9f10d39` | 44 testes e build Vite | Parcial; superfície pronta, shadow real ausente |
| Template Lab e bancada criativa | `feat/estudio-template-lab` · `6693316` | `4da6a26` | 234 testes backend, 226 frontend, ciclo v11_03 129/129 | Parcial; execução local provada, produção remota ausente |

## Fronteiras que não podem ser confundidas

### Bancada criativa

- O runtime em uso persiste a fila em SQLite local.
- A migration `v11_03` modela a execução em Postgres e possui rollback provado.
- Não existe writer que una os dois caminhos.
- `v11_03` não foi aplicada no Supabase oficial.
- Não existem worker remoto, bucket remoto verificado ou Remotion hermético.

Portanto, a bancada local é produto provado; a capacidade de execução criativa produtiva permanece parcial.

### Decision Lab

- A interface distingue sintético, insuficiente, antigo, indisponível, zero medido e não aplicável.
- Fixture sintética não pode afirmar `SHADOW READ`, dado real ou conta de teste.
- Não existe ainda bundle shadow verdadeiro vindo do backend.
- Nenhuma linha real de Google Ads percorreu toda a fronteira de normalização e decisão.

Portanto, a superfície L6 é provada; o loop de decisão produtivo permanece parcial.

### Google Search

- O primeiro canário Search pausado foi criado na Portal Mundo Mais e possui recibo.
- Ele ainda precisa fechar ledger, vínculo e reconciliação no inventário/H0.
- A explicação factual de por que uma campanha não escala ainda carece da coleta real completa de sinais Google Ads.

Estas duas tarefas receberam prioridade explícita global: primeiro fechar o canário, depois entregar o diagnóstico Search factual.

## Autoridade de prioridade no QG

Antes desta convergência, a ordenação aplicava o `rank` da iniciativa antes da prioridade explícita da tarefa. Isso fazia uma pendência editorial antiga aparecer antes de uma tarefa operacional declarada urgente.

A ordem passa a ser:

1. prioridade explícita da tarefa;
2. rank da iniciativa;
3. ordem editorial dentro da iniciativa.

Dependência continua existindo apenas quando declarada por ID na fonte. Proximidade editorial não vira bloqueio.

## Próxima sequência operacional

1. `P05-T11` — fechar ledger, intenção, vínculo e reconciliação do canário Search pausado.
2. `P05-T07` — coletar e explicar, com fonte e frescor, por que Search não escala.
3. `P09-T01..T03` — fechar contrato de intenção, idempotência, aprovação, recibo e rollback que governa ações.
4. `P17-T03..T06` — aplicar v11_03 com autorização, criar writer Postgres, worker remoto e storage verificado.
5. `P14-T02` — atravessar um bundle shadow real pelo Decision Lab antes de qualquer autonomia.

## Branches e processos que permanecem fora

- Branch ativa do supervisor contínuo: aguarda recibo final e revisão; não integrar durante execução.
- Candidatos antigos ou superseded: não entram apenas por existirem ou possuírem commits.
- WIP da `main`: preservado fora desta árvore de convergência; não foi incluído nem descartado.

## Dependência do rebuild que precisa virar contrato

Os nós curados do legado n8n dependem dos arquivos sanitizados em `inventario-n8n/flows/*.meta.json`. Esses snapshots existem na mesa principal, mas estão ignorados pelo Git; uma worktree limpa nasce sem eles e o gerador recusa corretamente as relações órfãs. Nesta convergência, uma cópia somente de insumo foi usada para preservar o legado. Próxima correção estrutural: versionar um manifesto sanitizado mínimo ou ensinar o pipeline a materializá-lo de uma fonte declarada antes de validar a curadoria.

## Critério para a próxima convergência

Uma frente só entra quando apresenta: base e HEAD, árvore limpa, ownership, gates reproduzíveis, fronteiras externas declaradas, recibos que atualizam o Roadmap Vivo e proposta de curadoria quando altera arquitetura ou capacidade.
