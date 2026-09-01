# P10-T16 — ingestão contínua Google Ads + autoridade de agenda n8n · handoff da lane

**Branch:** `sprint/hermes-p10-t16-n8n-ledger-v12-v1`
**Base:** `b6e226ab2f6d339d2c7c899b83b05ff4a95ebcac` (= `origin/volc-os-v2` na abertura)
**Data:** 01/09/2026
**Estado proposto para P10-T16:** continua **`partial`**. Esta lane NÃO promove nada.

---

## 1. Resumo

A tarefa pedia duas coisas que se sustentam mutuamente: **adaptar os workflows
n8n D0/D-1 ao ledger v12** e **decidir a autoridade de agenda**. Adaptar sem
decidir deixaria duas rotinas concorrendo; decidir sem adaptar deixaria a decisão
sem consequência.

A lane entrega as duas, e nada é ligado:

- **`ADR-N8N-AUTORIDADE-DE-AGENDA.md`** registra `N8N_IS_SCHEDULE_AUTHORITY`: o
  n8n é a única autoridade de agenda; o coletor Python vira biblioteca /
  one-shot / fallback / diagnóstico; os timers systemd ficam desinstalados, com
  condição explícita de aposentadoria.
- **`supabase/migrations/v12_04_gads_fato_canonico_dia.sql`** cria o fato
  canônico campanha-dia e o ledger de execução, com uma RPC única governada.
  Escrita e provada em Postgres descartável; **não aplicada**.
- **`n8n/volc_gads_campanha_dia_d0.json` e `…_d1.json`** implementam a ordem
  obrigatória do contrato, ponta a ponta, e nascem **inativos**.

### O que esta lane encontrou e que ninguém tinha medido

**1. Um defeito de semântica do n8n, achado antes de qualquer ativação.** A
primeira versão lia o contexto da iteração com `$('Pagina: preparar pedido')`.
`$()` resolve pelo **índice da rodada do nó que pergunta** — e uma conta que falha
faz o nó de pedido rodar mais vezes que o de normalização. A partir dali, cada
iteração colava a resposta certa na **conta errada**, em silêncio. O simulador
offline derrubou; a correção foi trocar `$()` por dois `Merge` por posição; a
regressão virou contraprova nomeada em três lugares.

**2. Cinco workflows da família com agenda ATIVA na instância viva.** O inventário
sanitizado de 19/08/2026 registra `custo-gads-report`, `custo-gads-report-d1`,
`custo-gads-placements-display`, `custo-gads-placements-display-d1` e
`criacao-gads-factory-v3` com `scheduleTrigger` e `ativo: true`. Esta lane **não
conseguiu ler a instância viva** (`REAL_N8N_READ_NOT_PROVEN`), então não afirma
que a agenda já é única — afirma que **nenhuma agenda desta entrega está ligada**,
o que torna a sobreposição impossível hoje e obrigatória de conferir antes de
ligar. É o Passo 1 do pacote de autorização.

### Decisão de projeto que vale registrar

Reaproveitar `scripts/adaptar_gads_reports_n8n.py` era o caminho curto: ele já
sabia remendar os exports antigos. Foi descartado, e o motivo não é gosto — **o
export que ele remenda não existe no repositório**. O adaptador opera sobre um
JSON que vive só na instância viva; sem ele, nada é reprodutível, nada é
testável, e cada correção futura dependeria de baixar o workflow de novo. A lane
gerou os dois fluxos a partir de um **gerador versionado**, com JSON determinístico
e três camadas de prova offline. O adaptador continua onde está, intocado: ele é
a única descrição de como os fluxos antigos foram corrigidos em 28/08.

---

## 2. Arquivos

| Arquivo | Natureza |
|---|---|
| `supabase/migrations/v12_04_gads_fato_canonico_dia.sql` | **NOVO.** Ledger + fato + RPC única + projeção + view de saúde |
| `supabase/migrations/v12_04_rollback.sql` | **NOVO.** Reversão par a par, recusa perda silenciosa |
| `supabase/migrations/README.md` | seção v12_04 com hashes, provas e o portão que falta |
| `scripts/provas-v12_04.sql` | **NOVO.** 65 provas de comportamento, em SQL puro |
| `scripts/provar-ciclo-v12_04.sh` | **NOVO.** Ciclo aplicar→operar→reverter→reaplicar em container |
| `scripts/provar-ponta-a-ponta-gads.sh` | **NOVO.** Documentos do fluxo contra a RPC real |
| `n8n/gerar_flows_gads_ledger_v12.py` | **NOVO.** Gerador único dos dois papéis, com `--check` |
| `n8n/volc_gads_campanha_dia_d0.json` | **NOVO.** Gerado, inativo |
| `n8n/volc_gads_campanha_dia_d1.json` | **NOVO.** Gerado, inativo |
| `scripts/validar_workflows_n8n_gads.py` | **NOVO.** 339 provas: estrutura, nó a nó, expressões, `node --check`, topologia, varreduras, GAQL contra o SDK v25 |
| `scripts/simular_gads_ledger_v12.mjs` | **NOVO.** Executa o JavaScript real num `vm`, relógio injetado, zero rede |
| `scripts/gate_agenda_unica_gads.py` | **NOVO.** systemd desta máquina + artefatos capazes de agendar + inventário vivo |
| `backend/tests/test_gads_workflows_n8n.py` | **NOVO.** 18 contraprovas; roda os gates dentro da suíte |
| `docs/closure/hermes-p10-t16-n8n-ledger-v12-v1/**` | ADR, autorização, matriz, gates, handoff, delta de curadoria |

Commits atômicos locais:

- `ad64524` `feat(banco): fato canonico Google Ads campanha-dia com ledger e RPC unica`
- `8e4750c` `feat(n8n): workflows D0/D-1 do fato campanha-dia, inativos e provados`
- (este) `docs(closure): ADR de agenda, autorizacao e matriz de contraprovas`

**Nenhum arquivo fora do ownership foi tocado.** `volc-os-workbook/ROADMAP-VIVO.json`,
`docs/volc-os-graph/**`, `graphify-out/**`, `backend/app/criativo/**`,
`services/creative_engine/**`, `volc_ads/criativo/**`, o Cofre, as migrations v13
e a v12_03 permanecem intocados. `scripts/adaptar_gads_reports_n8n.py` e
`volc_ads/inteligencia_google/**` foram apenas lidos.

---

## 3. O desenho, em uma passada

```
Agenda (cron) ─┐
Manual ────────┴→ Config → Identidade da execucao → Contas autorizadas
   → Selecionar contas → Campanhas conhecidas → Identidade VOLC por conta
   → Lote de contas (SplitInBatches, batchSize 1)
        main[1] → Pagina: preparar pedido → Google Ads: search (v25, SELECT)
                     ├ sucesso → Juntar contexto e resposta → Pagina: normalizar
                     │            → Validar semanticamente → RPC: ingerir lote
                     │            → Reconciliar lote → Tem proxima pagina?
                     │                 true  → Pagina: preparar pedido
                     │                 false → Lote de contas
                     └ erro    → Juntar contexto e erro → Classificar erro do Google
                                  → Lote de contas
        main[0] → Fechar execucao → Limite do fechamento → RPC: fechar recibo
                  → Releitura do recibo → Batimento e saude → Falha real?
                       true → Alerta de rotina parada
```

**D0**: `0 6,12,18,23 * * *`, janela = hoje em `America/Sao_Paulo`.
**D-1**: `0 6 * * *`, janela = dia anterior, fechado.

Sete escolhas que carregam o contrato:

1. **A chave da execução inclui o PASSO.** As quatro passadas D0 do mesmo dia são
   quatro leituras da mesma janela, não repetições. Colapsá-las obrigaria a
   ATUALIZAR o recibo — e recibo que se atualiza deixa de ser recibo. Repetir a
   mesma passada é idempotente; a passada seguinte tem recibo próprio.
2. **A precedência é total e declarada:** `D0(1) < D-1(2) < backfill(3)`. Janela
   fechada nunca é rebaixada por leitura intradia; a linha rebaixada é
   `preterida`, que não é `rejeitada` nem `aceita`.
3. **NULL ≠ 0 vive no schema.** Nenhuma métrica tem DEFAULT; ausência,
   `undefined` e `''` viram `null`; número que chega como **string** é recusado
   com motivo — porque `''::numeric` explode e `'0'` passaria como zero medido.
4. **O fechamento reconcilia contra o banco**, não contra a própria memória: soma
   do ledger, contiguidade dos lotes e `COUNT` real da tabela. Divergência levanta
   exceção nomeada.
5. **A FK do fato para o ledger é `DEFERRABLE INITIALLY DEFERRED`**: o fato entra
   antes, o recibo depois, e fato sem recibo não sobrevive ao `COMMIT`.
6. **A projeção legada é fault-isolated e restrita.** 16 colunas de entrega;
   nunca receita, revshare, GAM, comissão, orientação ou otimização; NULL vira
   NULL; `campaign_id` ambíguo é recusado (a legada não tem conta na chave); e ela
   não cria linha nova. Se ela falhar, o SQLSTATE vai para o recibo e o fato vive.
7. **O batimento sai da releitura**, não da memória do fluxo. `SAUDAVEL` nunca é
   derivado de tentativa; recibo que não aparece na releitura é `INDETERMINADO`.

### Uma escolha que precisa de justificativa explícita

`Lote de contas` tem `batchSize: 1`, e o Code seguinte **falha fechado** se
receber mais de um item. O endpoint `googleAds:search` é por cliente: um lote com
N contas exigiria reabrir o lote dentro do laço, e o retorno passaria a disparar
mais de uma vez por iteração — que é exatamente como um `SplitInBatches` pula
lote. O lote de **volume** é a página (`PAGE_SIZE` linhas por chamada e por RPC).

---

## 4. Gates

Detalhe completo em `GATES.md`. Resumo:

| Gate | Resultado |
|---|---|
| `bash scripts/provar-ciclo-v12_04.sh` | **107 provas, 0 falhas** |
| `python3 scripts/validar_workflows_n8n_gads.py` | **339 provas, 0 falhas, 0 pulados** |
| `node scripts/simular_gads_ledger_v12.mjs` | **65 provas, 0 falhas** |
| `bash scripts/provar-ponta-a-ponta-gads.sh` | **12 provas, 0 falhas** |
| `python3 scripts/gate_agenda_unica_gads.py` | **14 provas, 0 falhas, 1 pulado declarado** |
| `pytest backend/tests/test_gads_workflows_n8n.py` | **18 passed** |
| `pytest backend/tests volc_ads` | **2922 passed / 20 failed / 101 skipped** |
| baseline `b6e226a`, worktree limpa | **2904 passed / 20 failed / 101 skipped** |
| `verificar_autoridade_supabase.py` | ✓ `https://database.agenciavolc.com.br` |
| `gate_sem_mutacao_google.py` | 3/3 ok |
| `verificar_segredos.py` · `git diff --check` | sem achados |
| `gerar_flows_gads_ledger_v12.py --check` | JSON em disco = o que o gerador produz |

**As 20 falhas são herdadas, e isso foi provado, não suposto:** a mesma suíte
rodou numa worktree destacada em `b6e226a` e as mesmas 20 falham lá
(`test_criativo_execucao.py` por ausência de `pytest-asyncio`,
`test_criativo_rotas_equivalentes.py` por *golden* de OpenAPI e faixa de
toolchain). Delta desta lane: **+18 passaram, 0 novas falhas**.

> ⚠️ A primeira tentativa de medir o baseline em segundo plano foi **morta pelo
> limite de turnos do executor** (task `bodd94q1l`, saída `[killed]`). A medição
> acima é de reexecução completa em primeiro plano; a worktree temporária foi
> removida (`git worktree remove` + `prune`) e a lista de worktrees está limpa.

---

## 5. As 30 contraprovas

`MATRIZ-CONTRAPROVAS.json` amarra cada uma ao comando que a executa, ao mecanismo
que a sustenta e ao que a derrubaria. **28 `provada`, 2 `parcial`**:

- **#9 (retry 429/5xx)** — provada a *declaração* do teto (`retryOnFail`,
  `maxTries: 3`, `waitBetweenTries`) e a classificação da falha depois dele; o
  comportamento do retry é do motor do n8n e não foi exercitado contra um n8n real.
- **#25 (somente o n8n agenda)** — provado que nenhum artefato deste repositório
  agenda a família fora do conjunto declarado e que nada está ligado; **não**
  provado que a instância viva já tem agenda única (ver §1, achado 2).

Sete contraprovas extras, não exigidas pelo brief, entraram porque a lane
encontrou o risco: o contexto que não vem de índice de rodada, os nomes de campo
do fluxo conferidos contra os que a RPC valida, a reconferência da identidade
devolvida, a falha fechada com zero conta autorizada, D0 e D-1 byte a byte
idênticos no código, o round trip de import/export, e a guarda contra tocar a
série reservada a outras lanes.

---

## 6. O que NÃO foi feito — literalmente

- ❌ **nenhuma** migration aplicada em `database.agenciavolc.com.br`;
- ❌ **nenhum** workflow importado, atualizado ou **ativado** no n8n;
- ❌ **nenhuma** chamada à Google Ads API — leitura ou mutação;
- ❌ **nenhuma** chamada à API de ativação do n8n;
- ❌ **nenhum** canário, primeira janela automática ou heartbeat em produção;
- ❌ **nenhuma** unit systemd instalada, habilitada ou iniciada;
- ❌ **nenhum** `push`, merge, rebase ou cherry-pick da lane PMax/v12_03;
- ❌ **nenhuma** edição em Roadmap, curadoria ou grafo.

## 7. Limitações declaradas

| Sigla | O que significa |
|---|---|
| `REAL_N8N_READ_NOT_PROVEN` | sem credencial de n8n no ambiente. IDs (`hN15qFAVOqH0135q`, `tKUItcd0AoD9mozV`), versões e estado ativo vêm de documento e inventário versionados |
| `REAL_GOOGLE_ADS_READ_NOT_PROVEN` | zero chamada à API. Os 27 campos GAQL existem nos *descriptors* v25 (google-ads 31.4.0); isso não prova que o par (recurso, campo) é selecionável em GAQL — só `google_ads_field` responde |
| `CREDENCIAL_DEVELOPER_TOKEN_NAO_EXERCITADA` | `={{ $credentials.developerToken }}` não foi resolvido contra um n8n real. Se falhar, a correção é outro caminho de injeção — nunca o token no JSON |
| `RETRY_DO_MOTOR_NAO_EXERCITADO` | `retryOnFail`/`maxTries` são do motor do n8n |
| `SERVIDOR_HETZNER_NAO_INSPECIONADO` | o gate de systemd mede esta máquina, não o servidor oficial |
| `COLISAO_v13_01_NAO_RESOLVIDA` | se a lane M-W2-02 aplicar `v13_01` com os mesmos objetos, o integrador escolhe UMA. A v12_04 aborta com mensagem nomeada se as tabelas já existirem |
| `PROJECAO_AMBIGUA_NAO_RETROAGE` | quando duas contas passam a compartilhar um `campaign_id`, a projeção da segunda é recusada, mas a da primeira **não** é revertida. O fato canônico guarda as duas separadas |

---

## 8. Para o integrador

**IDs de tarefa afetados:** `P10-T16` (principal), `P06-T08` (evidência nova do
fato canônico), `P06-T02` e `P02-T03`/`P06-T03` (contexto de F018/F019).

**Delta de curadoria:** `curation-handoff.json` nesta pasta. Esta lane **não**
editou `ROADMAP-VIVO.json`, `curadoria-operacional.json` nem `graphify-out/**`,
conforme o AGENTS.md — o integrador único aplica e reconstrói o Mapa Vivo UMA vez
depois do merge, e roda `python3 scripts/atualizar_grafo_volc_os.py --check`.

**Frescor do grafo nesta lane:** não recalculado, por proibição explícita de
tocar o grafo. `graphify-out/UPDATE_STATUS.json` continua apontando para o commit
anterior a esta entrega — divergência esperada e declarada.

**Por que P10-T16 continua `partial`:** o critério de aceite exige canário
manual, reconciliação de recibos, ativação de uma única agenda e heartbeat
ligado. Nada disso pode ser feito sem autorização de banco e acesso ao n8n. Código
pronto não fecha entrega material.

**Ordem sugerida:** revisar → merge → aplicar o delta de curadoria → reconstruir
o Mapa Vivo → só então abrir `AUTORIZACAO-ATIVACAO.md` com o dono.
