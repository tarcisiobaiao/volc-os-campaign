# Ondas de execução — fechamento global VOLC O.S.

Regras gerais: (a) toda escrita na `main` passa por UM integrador por vez
(missões marcadas ⛓ serializam entre si); (b) missões de harness rodam em
paralelo livremente (worktrees isoladas); (c) nenhuma missão executa mutação
externa; (d) cada missão termina com handoff compacto + delta de curadoria
PROPOSTO.

## Onda 1 — Convergência e desbloqueio (nenhuma decisão de produto pendente*)

*exceto D9 (backup), que é recomendação forte e ação de 10 minutos.

Objetivo operacional: uma única verdade na main, com backup, harness funcional
e grafo reconciliado. Sem isso, toda missão futura rediscute o estado.

| ID | Missão | Runner | Modelo | Paralelismo |
|---|---|---|---|---|
| M-W1-01 | Backup remoto da main (push inicial já; push final pós-onda) | interativa + dono | Opus | livre (não toca árvore) |
| M-W1-02 | Lote documental: 16 untracked commitados com varredura de segredo | interativa | Codex | ⛓ |
| M-W1-03 | FF `integration/autonomous-closure-20260829` + gates pós-merge | interativa (integrador) | Opus | ⛓ |
| M-W1-04 | Revisão substituta + integração `656d72d` (deadman) e `5eb6b38` (PMax obs) | interativa (integrador) | Opus | ⛓, após W1-03 |
| M-W1-05 | Convergência harness v2 + defeito dos gates + defeito de escopo dos reviewers + `6fc7923` | interativa | Codex escreve, Opus revisa | ⛓, após W1-04 |
| M-W1-06 | Verificação: fix "14 achados" ⊂ `ee68085`? | harness read_only | claude opus + codex | livre |
| M-W1-08 | Destino dos órfãos `b1fa53e` e `28d2540` | harness read_only | claude opus + codex | livre |
| M-W1-09 | Curadoria + rebuild grafo + poda ~19 refs + reconciliação done↔decision | interativa (integrador) | Opus | ⛓, última |

Resultado observável no frontend: QG passa a mostrar as tarefas expandidas
(P04-T09 etc.) com evidência; grafo `current: true` no HEAD novo.

Validação humana da onda: aprovar a poda de refs (lista do INTEGRATION-LEDGER)
e o push final.

## Onda 2 — Horizonte A sem esperar o dono

Objetivo operacional: o operador VÊ diagnóstico real no cockpit; os pacotes
que dependem de decisão (banco, segurança, agenda) ficam prontos-para-janela.

| ID | Missão | Runner | Modelo | Depende de |
|---|---|---|---|---|
| M-W2-01 | Diagnóstico Search: endpoint + primeiro consumidor da v12_01 (portão de identidade obrigatório) | harness impl | Codex + reviewers | nada (base atual) |
| M-W2-02 | Migration D0/D-1 (fato canônico) escrita + rollback + provas em Postgres descartável | interativa | Codex | nada (aplicação espera D3) |
| M-W2-03 | Ratchet de coleta pytest (32 `def teste_` da ponte Pautador) | harness impl | Codex (effort low) | nada |
| M-W2-04 | 12 lacunas de contrato do Decision Lab L6 (backend, ainda sintético) | harness impl | Codex + reviewer | nada |
| M-W2-05 | Pacote de segurança executável: REVOKE/RLS, plano de rotação, fechamento de /api/supabase/*, smoke anônimo — provado em descartável, NADA aplicado | harness impl | Codex + reviewer Opus | nada |
| M-W2-06 | Colheita das worktrees dos fix-writers (o que existe além de 951fe3f?) | harness read_only | claude + codex | M-W1-03 |
| M-W2-07 | Demand Gen pós-merge: canal registrado, gates na main | harness impl | Codex | M-W1-03 |

Resultado observável no frontend: `/trafego/campanhas/:id` deixa de dizer
"capacidade não ligada" e mostra diagnóstico real de FGTS/Maquininha com
fonte, janela e `lido_em`.

Validação humana da onda: revisar OPEN-DECISIONS.md como pauta única (D1-D13)
— a onda 3 inteira destrava com essa reunião.

## Onda 3 — Destravada por decisões (planejada; specs após D*)

Espinha do caixa: D1 → aplicar v10 → writer+caller → canário fechado (P05-T11
done) → janela de segurança (D4+D10) → **Search lançável**.
Paralelos: D3 → D0/D-1 aplicado + agenda única + deadman ligado; D2 → coleta
contínua + shadow ORAKUL com dado real; D5 → Display validate_only real;
curador automatizado; reinventário n8n; supervisor reativado.

## Onda 4 — Horizonte B ordenado (planejada)

Criativos à produção (D6 → v11_03 → worker → storage → Remotion hermético →
peça real); ORAKUL Predictive (ledger → baseline → calibração → simulador);
Cofre persistido → 1Password/AdsPower → Postiz → piloto orgânico → Meta;
receita/câmbio (D11); updated_at no roadmap.

## Conflitos conhecidos e como o plano os evita

- **Escrita na main**: só o integrador (⛓); harness nunca mescla.
- **supabase/migrations/ e ROADMAP-VIVO.json**: protegidos no harness — toda
  missão que os toca é interativa, por design.
- **Supervisores vivos**: nenhuma missão toca processos/bancos deles; a
  colheita (M-W2-06) é read-only; intervenção é D13.
- **Ownership**: nenhuma missão de onda 1-2 compartilha caminho de escrita com
  outra da mesma onda (ver `allowed_paths` em missions/).
