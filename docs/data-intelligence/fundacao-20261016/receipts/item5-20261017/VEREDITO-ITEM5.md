# Veredito — item 5: contrato dos cinco coletores canônicos

Autorizações do dono: 17/10 10:49 e 10:51 UTC (escopo e moeda), 21:15 UTC (cutover dos três restantes),
21:21 UTC (exportação read-only e replay), 22:46 UTC (fechamento acelerado com canário por cópia temporária).
Branch `lab/data-foundation-20261016`, local. Legenda: **D** demonstrado, **I** inferido, **NT** não testado.
Detalhe por evento: `cutovers.jsonl`; replay: `REPLAY-ANTES-DEPOIS.md`; legados: `LEGADOS-ITEM5.md`.

## Resumo

| Coletor | Versão nova em produção | Prova funcional | Prova do agendador |
|---|---|---|---|
| Google D0 | sim (17/10 08:08 BRT) | D: 12 execuções | D: cron `7 6-23` |
| JoinAds intradiário | sim (17/10 09:07 BRT) | D: 6 execuções | D: cron `15 6-22/2` |
| JoinAds D-1 | sim (17/10 18:16 BRT) | D: canário por webhook do próprio workflow (16/10) | **pendente**: cron 06:20 de 18/10 |
| Google termos | sim (17/10 18:17 BRT) | D: cron natural 20:23 | D: o mesmo cron 20:23 |
| Google D-1 | sim (17/10 20:23 BRT) | D: canário por cópia temporária (16/10) | **pendente**: cron 06:17 de 18/10 |

`functional_execution_proven = true` nos cinco. `scheduler_execution_proven = false` para Google D-1 e JoinAds D-1
até as execuções naturais de 18/10 (06:17 e 06:20 BRT).

## 1. Workflows e versões antes/depois

| Coletor | id | versionId antes | versionId depois | cron / timezone (inalterados) | errorWorkflow |
|---|---|---|---|---|---|
| Google D0 | `Ps9y…` | `cf965a87` | `54242243` | `7 6-23 * * *` / São Paulo | — → `fvqy…` |
| Google D-1 | `7yxs…` | `23735272` | `a86d9a91` | `17 6,14 * * *` | — → `fvqy…` |
| Google termos | `TFlm…` | `609ef5b9` | `39ba1287` | `23 */4 * * *` | — → `fvqy…` |
| JoinAds intradiário | `cpb6…` | `904cfcb3` | `7b93d17b` | inalterado | — → `fvqy…` |
| JoinAds D-1 | `jDX3…` | `47c58073` | `213b931c` | `20 6 * * *` | — → `fvqy…` |
| Error workflow comum | `fvqy…` | novo | `f7cd937f` | — | — (sem loop) |
| Reaper (shadow) | `4V7w…` | novo | `1d8798fb` | `41 * * * *` | `fvqy…` |
| Cópia canário D-1 | `24cE…` | criada inativa | ativa 0,5 s, **arquivada** | webhook efêmero | — |

Todos ativos; nenhum cron, timezone ou cadência mudou (conferido pelo `cutover.py` depois de cada PUT).

## 2. Hashes dos exports de rollback (0600, fora do Git)

google_d0 `13f6bd0def50a1ca…`, google_d1 `1d2409a0804841fb…`, google_termos `d2282714b894b532…`,
joinads_d1 `186f61262d2c2f4b…`, joinads_intraday `40567044237745cb…`. Lidos depois do PUT: D-1 `3198f452…`,
termos `66c8f14d…`, JoinAds D-1 `20f2ca66…`; cópia canário `fea6cf61…`.

## 3. Alterações por coletor (gate estrutural `validar_item5.py`: só os nós listados mudaram)

- **Google D0, D-1** (Code, duas GAQL, ingestão, finalização): sem linha de métrica nada é gravado
  (`metrics = {}`, `metric_row_status = metric_row_absent`); zero do proto3 em linha presente é zero medido;
  `customer.currency_code` nas duas GAQL e gravado como veio (`currency_status observed`, fonte
  `gaql:customer.currency_code`), sem BRL fixo; `collector_version 2`.
- **Google termos** (Code, ingestão, finalização): moeda da GAQL, `metric_row_status present`, versão 2.
- **JoinAds intradiário e D-1** (Normaliza coleta, Config): receita em micros por decimal exato (BigInt) half-even,
  fail-closed (não numérico, NaN/infinito, negativo, precisão excessiva, overflow), original em
  `attributes.revenue_original`; moeda USD `attested` / `owner_attestation`; `conversion.status = nao_convertido`;
  `COLLECTOR_VERSION 5`.
- **Os cinco**: `errorWorkflow = fvqy…`.

## 4. Testes e canários

**D.** 31 testes herméticos sobre o código implantado (`test_item5_contrato_coletores.py`, 29;
`test_item5_google_d1_implantavel.py`, 2, sobre o JSON exato do D-1). Gate estrutural sem falhas. Canários:
D0 12, intradiário 6, JoinAds D-1 1 (webhook do próprio workflow, `lookback_days=0`), termos 1 (cron natural),
Google D-1 1 (cópia temporária: único delta semântico o gatilho, conferido antes de ativar; `trigger_kind` gravado como
`schedule` porque a expressão do canônico rotula qualquer modo diferente de `manual` assim; a execução se distingue
pelo `workflow_id` da cópia e **não** conta como prova do agendador).
**NT:** falha induzida numa cópia inativa de coletor (a API pública não executa cópia inativa); o error workflow foi
testado com payloads sintéticos em dry-run (5 execuções em 17/10 11:01–11:02 UTC) e pelos testes `test_error_*`.

## 5. Prova real pós-cutover (Supabase oficial, RR READ ONLY + ROLLBACK, só agregados)

| Coletor | Runs | Observações | Ausente sem custo | Zero sem linha | Moeda | Integridade |
|---|---|---|---|---|---|---|
| Google D0 v2 | 12 completed | 60 | 48 | 0 | BRL observed | lotes/linhas = declarados, 0 erro silencioso |
| Google termos v2 | 1 completed | 2.156 (14 keyword, 2.142 termo) | — | 0 | BRL observed | idem |
| Google D-1 v2 (canário) | 1 completed, janela 16/10, 1 conta | 5 (1 present, 4 absent) | 4 | 0 | BRL observed | idem |
| JoinAds v5 (intradiário + D-1) | 6 + 1 completed, 0 rejeição, 0 aviso | escala máx. 6, quantizadas = com receita | — | — | USD attested | sem duplicação de slot |

Duplicação (`g_dup`, `j_dup`): nenhuma linha. Error workflow: nenhum disparo real. Conversão cambial gravada: 0.

## 6. Os três runs órfãos

Termos de 15/10 (execuções n8n `58041`, `58042`, `58044`, todas `success` terminadas em 15/10 na versão anterior):
seguem `running`, **intactos**. O status do ledger não aceita `abandoned`; a transição exige migration (fora do
escopo), então o reaper ficou em shadow: mais de 12 execuções horárias com saída idêntica (os mesmos 3 candidatos,
ação `nenhuma_shadow:abandoned_inexistente_no_schema`).

## 7. Moeda

| Fonte | Estado | Prova |
|---|---|---|
| Google Ads (3 coletores) | **observed** | `customer.currency_code` devolvido pela API, no payload bruto e na observação |
| JoinAds | **attested** | atestação do dono (17/10 10:51); a API não declara moeda (0 de 276 payloads) |
| Câmbio USD/BRL | **unproven** | `system_settings.dollar_exchange_rate` = 5,25 parada desde 18/02/2026; funções caem em 5,2/5,5 em silêncio; o legado recalcula o histórico quando a taxa muda. Reconciliação de 3 linhas reais USD × 5,25 = BRL persistido bate (`i5_rec.sql`). Nada convertido no ledger: **decisão do dono pendente** |

## 8. Replay estrito

**D.** Segue `insuficiente` nas cinco políticas; anti-baseline null→zero 290/290 bloqueadas; nenhuma mudança de verba.
Pela primeira vez há custo Google `observed` com moeda provada em janela fechada. Motivos restantes: moeda JoinAds só
atestada, câmbio não provado, 0 de 3 dias maduros, uma única campanha ativa e histórico não reescrito.
Tabela antes × preliminar × depois: `REPLAY-ANTES-DEPOIS.md`.

## 9. Legados ainda ativos (nenhum desativado)

G ADS - REPORT `hN15…`, G ADS REPORT - DAY BEFORE OFICIAL `tKUI…`, GADS REPORT `33cQ…`, GADS REPORT - DAY BEFORE
OFICIAL `fwMK…`, JOIN ADS - REPORT - INTRA DAY `U0jE…`, JOIN ADS - REPORT - DAY BEFORE `RpxB…`, FORCE UPDATE GADS
`rb3I…`. Inventário, sobreposição, paridade, ordem de pausa e rollback: `LEGADOS-ITEM5.md`.

## 10. Rollback exato

```
python3 docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/cutover.py --rollback <chave> \
  experiments/data-intelligence-lab/artifacts/item5-20261017/rollback \
  experiments/data-intelligence-lab/artifacts/item5-20261017/implantado
```

Chaves: `google_d0`, `google_d1`, `google_termos`, `joinads_intraday`, `joinads_d1` (um por vez; restaura nós,
conexões e settings do export, inclusive sem `errorWorkflow`). Error workflow e reaper: `POST /workflows/<id>/deactivate`.
A cópia canário já está arquivada. Nenhum dado é apagado em rollback (ledger append-only).

## 11. Produção acessada e mutações

| Alvo | Acesso | Mutação |
|---|---|---|
| n8n | API pública | PUT dos 5 canônicos (mesmo id, cron, timezone); criação e ativação do error workflow e do reaper (17/10 manhã); criação, ativação por 0,5 s, desativação e arquivamento da cópia canário do D-1; 1 chamada ao webhook do JoinAds D-1 e 1 ao da cópia |
| Supabase oficial | SSH + psql com `default_transaction_read_only=on`, RR READ ONLY + ROLLBACK | nenhuma direta; as escritas foram as normais dos coletores (append-only) nas execuções agendadas e nos 2 canários |
| Google Ads / JoinAds | só leitura pelos próprios coletores | nenhuma mutate, nenhuma mudança de campanha, verba, lance, conversão ou anúncio |
| GTM, WordPress, Vercel, migrations | nenhum | nenhuma |
| Legados | leitura de metadados | nenhum desativado |

## 12. Branch

Commits pequenos em `lab/data-foundation-20261016` a partir de `e5e84b8c`; SHA final, árvore limpa e frescor do grafo
no handoff da thread. Zero push, zero merge, `main` intocado. Roadmap e curadoria aplicados **só nesta branch**
(P06-T10 e P10-T28 `todo → partial`; nada vira `done`).

## Pendências

1. **Única espera de 18/10:** execuções naturais do Google D-1 (06:17) e da JoinAds D-1 (06:20) para provar o
   agendador; ler com `verificar.sh 2026-10-18T09:00:00Z` e `verificar_integridade.sql`.
2. **`dq_zero_sintetizado = 0%` por 7 dias (18–24/10):** leitura read-only diária com `verificar.sh <dia>`; critério:
   `zero_sem_linha = 0` e `com_custo = 0` nas linhas `metric_row_absent` dos coletores versão 2. Sem rotina agendada
   (item 8 não autorizado).
3. Decisões do dono: cotação USD/BRL vigente e versionada; migration do estado `abandoned` para o reaper sair do shadow;
   autorização futura para pausar legados após paridade.
4. Achados: o `trigger_kind` do canônico chama de `schedule` qualquer modo não manual; o workflow Google guarda o
   developer token em nó Set em texto puro (não alterado; recomendação: credencial).
