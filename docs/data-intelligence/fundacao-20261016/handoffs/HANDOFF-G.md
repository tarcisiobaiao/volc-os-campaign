# HANDOFF-G — Observabilidade e Data Quality (thread G)

Branch `lab/dil-fundacao-20261016-g` (worktree esparso `worktrees/dil-fundacao-20261016-g`), com
`lab/data-foundation-20261016` @ `d4475d30` mesclado localmente (contrato A, a pedido do integrador; sem push).
Doc completo: `docs/data-intelligence/fundacao-20261016/09-OBSERVABILIDADE.md`.
Nada aplicado fora do PostgreSQL descartável; nenhuma rede, nenhum segredo, nenhum `.env*`/`~/.ssh`; roadmap,
curadoria e grafo intocados; nenhum alerta enviado (sink injetado).

## 1. Arquivos

| Caminho | O quê |
|---|---|
| `experiments/data-intelligence-lab/src/volc_dil/fundacao/qualidade/__init__.py` | API pública |
| `.../qualidade/modelo.py` | `Achado`, `Severidade`, protocolo mínimo `ObservacaoDQ`/`RunDQ`/`CoberturaSensorDia` (`de_dict` aceita nomes das colunas reais) |
| `.../qualidade/agenda.py` | `SLA`, `SLA_PADRAO` (5 coletores), `LIMIARES_PADRAO`, parser de cron diário, slots |
| `.../qualidade/runs.py` | frescor, completude por slot, runs órfãos, falha silenciosa |
| `.../qualidade/leituras.py` | duplicação, zero sintetizado, completude de grade (late ≠ missing, null ≠ 0) |
| `.../qualidade/reconciliacao.py` | receita JoinAds (réplica pura de `joinads_observation_latest`) e custo D0×D-1 |
| `.../qualidade/deriva.py` | KS + efeito mediana/MAD + correção de autocorrelação; `medir_falso_alarme`, `medir_poder` |
| `.../qualidade/integridade.py` | schema drift, source substitution, cobertura de atribuição do sensor |
| `.../qualidade/adaptadores.py` | linhas reais (v21, JoinAds v2, raw_events) → protocolo |
| `.../qualidade/ponte_observacao.py` | `Observacao` de A → `ObservacaoDQ`; `dil_obs.run_coleta` → `RunDQ`; latência e dead letter |
| `.../qualidade/alertas.py` | `PoliticaAlerta`, `decidir_alertas` (pura), `despachar(alertas, sink)` |
| `.../qualidade/motor.py` | `ConjuntoSaude`, `avaliar_saude`, mapa regra → view |
| `.../qualidade/recibo.py` | `health_receipt.json` + `.md` (CLI `python -m volc_dil.fundacao.qualidade.recibo`) |
| `.../qualidade/sintetico.py` | gerador no formato das tabelas reais; cenários `limpo`, `producao_conhecida`, `estressado` |
| `.../qualidade/sql_views.py` | gerador dos SELECTs read-only a partir das views |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/dq_01_views_qualidade.sql` + `.down.sql` | 15 views (v21/JoinAds v2/raw_events) |
| `.../views_qualidade/dq_02_views_dil_obs.sql` + `.down.sql` | 4 views sobre `dil_obs` (depende de `dil_obs_0001`, thread A) |
| `.../views_qualidade/selects_somente_leitura.sql` | GERADO: SELECTs autocontidos (não editar à mão) |
| `.../views_qualidade/export_recibo_somente_leitura.sql` | export minimizado para o recibo com dado real |
| `.../views_qualidade/base_real/*.sql` | cópia byte a byte do DDL real (`043c77f5` v21_01..03; `192bc065` JoinAds v2) + prelúdio SÓ de teste (pgcrypto, `raw_events` mínima) |
| `tests/data-intelligence/fundacao/test_qualidade_{checagens,deriva,alertas_recibo,pg_views}.py` | testes |
| `docs/.../09-OBSERVABILIDADE.md`, este arquivo | docs |

Não criei `conftest.py` nem `fundacao/__init__.py`: os testes PG usam `cluster_pg`/`obs` do conftest de A.

## 2. Provas

```bash
cd /Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/dil-fundacao-20261016-g
OMP_NUM_THREADS=2 /Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/data-intelligence-overnight-20261015/experiments/data-intelligence-lab/.venv/bin/python -m pytest tests/data-intelligence -q
```

Resultado: suíte completa verde (herdados + A + B + C mesclados + **66 novos** de G); só `-k qualidade`: 66 em ~8 s.
Nenhum skip (PostgreSQL 16.11 do Homebrew subiu).

| Arquivo | Testes | Gate |
|---|---|---|
| `test_qualidade_checagens.py` | 27 | cada regra: positivo, negativo, borda (null ≠ 0, late ≠ missing, fora da agenda ≠ buraco, prazo aberto = pendente, heartbeat salva run, `failed` não é silencioso); ponte A; zero sintetizado caminho A (`adaptar_google_ads_v21`) = caminho direto |
| `test_qualidade_deriva.py` | 8 | falso alarme ≤ 2% (com correção, `phi` 0/0,3/0,6); KS cru > 5% em `phi`=0,6 (contraprova); poder ≥ 90% em ×0,1, ≥ 60% em ×3; null descartado |
| `test_qualidade_alertas_recibo.py` | 8 | decisão pura, silêncio/dedupe, sink injetado, AST sem import de rede, recibo reprodutível, cenários limpo/estressado, CLI com export |
| `test_qualidade_pg_views.py` | 23 | DDL base = refs (`git show`); security_invoker + grants (anon negado, service_role só SELECT); sem sid/pid; parâmetros SQL = Python; dispara/não dispara por view; **equivalência Python×SQL em 3 cenários**; SELECTs read-only = views; export read-only reproduz achados; rollback + reaplicação; recusa sem tabelas-base; dq_02 sobre dil_obs + rollback |

## 3. API pública (`volc_dil.fundacao.qualidade`)

- Tipos: `Achado(regra, severidade, fonte, grao, janela, evidencia, mensagem, chave)`, `Severidade`,
  `ObservacaoDQ`, `RunDQ`, `CoberturaSensorDia`, `LinhaReceitaDia`, `CelulaEsperada`, `SLA`, `SLA_PADRAO`, `LIMIARES_PADRAO`.
- Avaliações (estado por item, inclusive `ok`): `avaliar_frescor`, `avaliar_completude_slots`, `avaliar_runs_orfaos`,
  `classificar_duplicacao`, `medir_zero_sintetizado`, `classificar_zero`, `classificar_celula`,
  `avaliar_reconciliacao_receita`, `agregar_receita_joinads`, `joinads_latest`, `avaliar_reconciliacao_custo`,
  `avaliar_cobertura_atribuicao`, `detectar_deriva`.
- Checagens (→ `list[Achado]`): `checar_frescor`, `checar_completude_slots`, `checar_completude_grade`,
  `checar_runs_orfaos`, `checar_falha_silenciosa`, `checar_duplicacao`, `checar_zero_sintetizado`,
  `checar_reconciliacao_receita`, `checar_reconciliacao_custo`, `checar_deriva`, `checar_deriva_esquema`,
  `checar_substituicao_fonte`, `checar_cobertura_atribuicao`, `checar_latencia_ingestao`, `checar_dead_letter`.
- Orquestração: `ConjuntoSaude(.de_tabelas|.de_dict)`, `avaliar_saude`, `view_da_regra`; alertas
  `decidir_alertas`, `despachar`, `POLITICAS_PADRAO`; ponte `de_observacoes`, `runs_de_run_coleta`;
  calibração `medir_falso_alarme`, `medir_poder`.

Mapeamento protocolo ↔ contrato A: tabela no docstring de `ponte_observacao.py`. O protocolo mínimo ficou porque
as checagens trabalham por LEITURA (várias métricas juntas: zero sintetizado precisa de custo e impressões na mesma
linha), enquanto `Observacao` de A tem uma métrica por linha; a ponte agrupa e preserva `motivo`
(`zero_sem_linha_de_metrica` → sintetizado, `zero_sem_prova_de_linha` → ambíguo).

## 4. Leituras read-only que o integrador deve rodar (SELECT puro, sem criar view)

Mesma trava do recibo de 16/10: `PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=20000'`,
confirmar `SHOW default_transaction_read_only` = `on`. Não imprimir credencial; saída bruta no scratchpad.

| # | O quê | Arquivo / seção | O que se espera (forma de 16/10) |
|---|---|---|---|
| G1 | frescor dos 5 coletores | `selects_somente_leitura.sql` → `dq_freshness` | d0/d1/termos/JoinAds com estado; termos pode estar `atrasado` |
| G2 | órfãos | `→ dq_runs_orfaos` | os 3 runs de 15/10 11:48 (L9) |
| G3 | buracos por slot (7 dias) | `→ dq_completude_hora` (filtrar `classe NOT IN ('ok','pendente')`) | falhas de termos (L9) |
| G4 | falha silenciosa | `→ dq_falha_silenciosa` | desconhecido |
| G5 | duplicação | `→ dq_duplicacao` (filtrar `severidade <> 'info'`; a lista info é grande por termos) | desconhecido; conflito no run seria novo |
| G6 | zero sintetizado | `→ dq_zero_sintetizado` | ~80% (L11: 88/110) — separa sem linha × com linha × sem prova |
| G7 | receita kv/earnings | `→ dq_reconciliacao_joinads` | 0,97–1,00 em 08–16/10 (L5) |
| G8 | custo D0×D-1 | `→ dq_reconciliacao_custo_d0_d1` | primeira medida real de maturação D0→D-1 |
| G9 | sensor × campanha | `→ dq_cobertura_atribuicao_sensor` (só agregado) | cobertura 0 (L4) |
| G10 | esquema JoinAds | `→ dq_esquema_joinads` | 3 versões de coletor (v2/v3/v4) |
| G11 | substituição | `→ dq_substituicao_fonte` | desconhecido |
| G12 | export para recibo real | `export_recibo_somente_leitura.sql` → arquivo no scratchpad; `python -m volc_dil.fundacao.qualidade.recibo --entrada <arq> --agora <instante do export> --saida <scratchpad>` | recibo `dado exportado`; commitar só o resumo agregado (as chaves de termos contêm texto de busca) |

Seções `dq_obs_*` do mesmo arquivo só fazem sentido quando `dil_obs` existir (não existe em produção).

## 5. Falhas e limites encontrados

- Primeiro rascunho do detector de deriva usava autocorrelação estimada na amostra combinada: matava o poder (a
  quebra parecia persistência). Corrigido para estimar só na base; números finais no doc 09 §4.
- O cenário `estressado` inicialmente escondia conflito/esquema/substituição em runs que o próprio cenário
  removia (intraday parado); marcas movidas para runs existentes — o recibo agora dispara todas as famílias.
- Poder do detector de deriva é baixo para mudanças ≤ ×1,5 com 7 dias (é detector de quebra, não de tendência).
- `json_agg` do psql quebra linha; os testes usam `jsonb_agg` (sem impacto nas views).

## 6. Riscos

| Risco | Mitigação / estado |
|---|---|
| Views nunca rodaram em produção; colunas/valores reais podem divergir do DDL wip | G1–G11 como SELECT puro primeiro; DDL base é cópia conferida das refs |
| `raw_events` real tem DDL desconhecido (R8) | view usa só `ts`, `event_name`, `payload` (as colunas que L4 já leu) |
| `partial` conta como sucesso no frescor (JoinAds marca partial por qualquer aviso) | documentado; trocar é uma linha nos dois lados + teste de equivalência |
| "primeiro run" define a vigência: coletor que sumiu antes da janela de 7 dias aparece como `sem_registro` sem slots perdidos contados além de 7 dias | intencional (crítico) |
| `dq_duplicacao` sobre termos (≈24 mil leituras) pode pesar | janela de 14 dias; `statement_timeout` |
| Limiares iniciais não calibrados | parâmetros numa view/dict únicos; calibrar com G6–G9 reais |
| Sem error workflow nos coletores (R7): falha pré-lote só aparece como `ausente_silencioso` | a checagem existe; a causa é do coletor |
| GUC `dil_qualidade.agora` permite a uma sessão "mudar o agora" das views | só afeta a própria sessão de leitura; views não escrevem |

## 7. Delta de curadoria proposto (NÃO aplicado; para o integrador decidir)

| Tarefa | Proposta | Estado sugerido |
|---|---|---|
| **P10-T04** Heartbeat e deadman | evidência: "16/10 (G): health contracts dos 5 coletores canônicos (Google D0/D-1/termos, JoinAds intraday/D-1) com frescor por slot, completude declarada×silenciosa, órfãos `running` sem sinal e falha silenciosa; views candidatas `dil_qualidade.dq_freshness/dq_completude_hora/dq_runs_orfaos/dq_falha_silenciosa` testadas em PG 16 descartável com equivalência Python×SQL; não aplicadas; JoinAds v2 ganha a primeira visão de saúde (antes inexistente)". Lacunas: rodar G1–G4 em produção; reaper dos 3 órfãos; error workflow (R7); canal de alerta | manter `partial` |
| **P06-T01** Mostrar frescor no inventário e por conta (`done` em `main`) | evidência adicional: "frescor com contrato de SLA por coletor canônico (cadência + tolerância, slot vencido, fora da agenda não é buraco) em `dq_freshness`, espelho Python testado por equivalência"; lacuna honesta: as views medem frescor por COLETOR, não por conta — frescor por conta exigiria `customer_id` × último lote (proposta, não feito) | não reabrir; só anexar evidência |
| **P06-T07** Tracking Control Plane em modo leitura | evidência: "cobertura de atribuição do sensor como métrica (`dq_cobertura_atribuicao_sensor`, só agregado, sem sid); forma de L4 (0/28) reproduzida em teste"; lacuna: correção depende de publicação GTM autorizada | manter `partial` |
| **P08-T07** Versionar telemetria e agregador do funil | evidência: "a view de cobertura do sensor depende só de `ts/event_name/payload`; DDL real de `raw_events` segue não versionado (R8) — a tabela de teste é mínima" | manter `partial` |

Nós/arestas sugeridos (curadoria, sem IDs sensíveis): `concept:data_quality_observability` (novo, `experimento`)
→ `observa` → `concept:google_ads_collection_ledger` e `cap_revenue_ingestion`; → `mede` → `concept:tracking_control_plane`
(cobertura de atribuição); `depende_de` → contrato de observação da thread A (`dil_obs`, para `dq_02`).
Nada disso existe em `main`; só nesta branch/worktree — não marcar concluído na fonte compartilhada.
