<!-- Cópia versionada de /mnt/project-files/handoffs/W15-meta.md (o revisor do Mac não enxerga /mnt/project-files). O SHA do commit que traz esta cópia não aparece nela: ele está na resposta da thread W15 e no git log. -->

# Handoff W15: recoleta madura e deadman da coleta Meta

- **Estado:** `ready_for_human`. Não está integrado, não está instalado e nada foi ligado.
- **Branch:** `mission/w15-meta-g0y5xz`
- **Commit:** `24486270174399a22bfb66b9a70f8128a42c1bae`
  - ciclo 1: `e7b1cb7` (recoleta) e `cb71e88` (deadman)
  - ciclo 2: `4344502` (correções da revisão adversarial), aprovado pelo revisor de nuvem 1
  - ciclo 3: `bf968bc` (v26_01: a view latest prefere a revisão completa)
  - ciclo 3b: `908e556` (semente da suíte com referência vazia, como no `lab.sh` do Mac)
  - ciclo 3c: `c34a597` (loops da suíte não entregam o stdin ao `docker exec -i`)
  - ciclo 4: `2448627` (v26_01 e rollback só trocam a definição; COMMENT, ACL e dono preservados): lab do Mac 42/42, aprovado com ressalvas baixas (R-mission-w15-2448627.md)
  - ciclo 5: commit seguinte a `2448627` (ressalvas fechadas), aguardando reconfirmação
- **Base:** `591a9895` (origin/main)
- **Roadmap afetado (o Roadmap não foi tocado):** P11-T06, P11-T20, P11-T25 (grão adset/dia e a primeira linha real) e P11-T03 (a integração n8n segura). O espelho Google é P06-T08/P09-T14 (W11).
- **Migration:** `v26_01` candidata, **não aplicada** em lugar nenhum além de Postgres descartável. Desde `2448627`, a v26_01 e o rollback não tocam COMMENT, grants nem dono.

## Por que este item

A coleta Meta de custo por conjunto/dia **já existia** no main:

- workflow D-1 no fuso da conta (`n8n/volc_meta_insights_dia_d1.json`);
- fato `trafego_meta_insight_daily` com moeda, fuso e revisão por `observado_em`;
- upsert idempotente via `trafego_meta_persistir_snapshot`;
- `vw_trafego_meta_insight_latest`;
- views financeiras conjunto/campanha-dia casadas com o GAM.

Reescrever essa coleta criaria um sistema paralelo. Faltavam duas coisas, as mesmas que a W11 fechou no lado Google:

1. **Maturação.** O D-1 lia cada dia uma vez. Com `action_report_time=impression`, as conversões chegam ao dia da impressão vários dias depois.
2. **Deadman.** Não havia observador externo dos workflows Meta.

## O que mudou

| arquivo | mudança |
|---|---|
| `n8n/gerar_flows_meta_ledger.py` | `PAPEIS` com `d1` e `recoleta`. O código dos nós é o mesmo nos dois; muda só o Config (`JOB`, `JANELA_MODO`, `PASSOS`, `DIAS_DE_RECOLETA`). A Identidade aceita `RECOLETA`, com janela `[hoje-1-N, hoje-2]` no fuso da conta e N de 1 a 28 (padrão 7). N inválido é recusado antes de falar com a Meta. O D-1 não lê `DIAS_DE_RECOLETA` |
| `n8n/volc_meta_insights_dia_recoleta.json` | Novo, gerado. Cron `30 8 * * *` em SP. Inativo e sem credencial |
| `n8n/volc_meta_insights_dia_d1.json` | Regerado. Só mudou o JS (offset da janela, chave da página, fechamento e linha sem data) |
| `backend/app/trafego/meta/deadman_insights.py` | Novo. A expectativa vem do workflow versionado. A evidência vem de `trafego_meta_sync_run` (`escopo='insights_fechamento'`, `cursor_final.window` = `<data>:<origem>`, `leitura_completa`). A decisão é de `saude.projetar_saude_coletor`, a mesma tabela-verdade do Google |
| `scripts/validar_workflows_n8n_meta.py` | Valida os dois artefatos e o papel de cada um |
| `scripts/gate_agenda_unica_gads.py` | Declara a recoleta Meta. Mescla limpo com a W11 |
| `backend/tests/test_meta_recoleta_n8n.py` | Novo: 14 testes, com o JS executado em `node` e relógio injetado |
| `backend/tests/test_meta_deadman_insights.py` | Novo: 29 testes |
| `backend/tests/test_meta_workflows_n8n.py` | 2 asserções ajustadas à mudança |

## Ciclo 2: o que a revisão adversarial pegou e foi corrigido

A revisão teve 11 achados confirmados (4 importantes, 7 menores) e 3 hipóteses. Foram corrigidos:

1. **Releitura descartada como replay.** A chave estável da página não levava papel nem dia. A recoleta com N=1 (ou um D-1 com reprocesso) relia um dia já lido ontem, gerava a mesma chave, e a RPC devolvia `repetido` sem gravar nada, com recibo verde. Agora a chave leva `job`, `origem_janela` e `data_do_disparo`. Rodar de novo no mesmo dia continua idempotente.
2. **Fechamento `ok` com conta pulada.** Uma conta recusada na seleção (sem fuso, ou com fuso desconhecido) deixava o fechamento `ok`. Agora ele sai `parcial`. **Isso também muda o D-1.**
3. **Linha sem data.** Uma linha sem `date_start`/`date_stop` numa janela de vários dias virava um grão de N dias com o gasto de um. Agora é recusada.
4. **Deadman.** `ativo_na_instancia` passa a vir de quem leu a instância. Sem isso, o artefato versionado (sempre inativo) dava DESABILITADO para sempre. `fechamentos=None` passou a dar INDETERMINADO. Um instante naive ou ilegível passou a dar INDETERMINADO em vez de `TypeError`.
5. **Texto da recoleta.** Ele dizia que a recoleta nunca relê o D-1, e isso é falso em Auckland no horário de verão. Agora é uma revisão a mais, com chave própria.

## Comandos e resultados (nuvem, Python 3.13, node 22, sem credenciais)

```
python3 n8n/gerar_flows_meta_ledger.py --check            → ok · 2 workflow(s)
python3 scripts/validar_workflows_n8n_meta.py (backend no path) → passaram 601 · falharam 0 · pulados 0
python3 scripts/gate_agenda_unica_gads.py                → passaram 18 · falharam 0 · pulados 1 (systemctl)
pytest test_meta_recoleta_n8n + test_meta_workflows_n8n + test_meta_deadman_insights → 80 passed
pytest volc_ads backend/tests
  base 591a9895: 35 failed, 7528 passed, 303 skipped
  branch 4344502: 35 failed, 7571 passed, 303 skipped   (lista de falhas IDÊNTICA)
```

A W11 registrou 25 falhas na base dela; aqui foram 35 com o mesmo comando. A diferença é de ambiente (dependências instaladas). As 35 se repetem iguais na base e na branch.

Mutações conferidas; cada uma derruba pelo menos um teste:

- **Gerador (8):** a recoleta inclui o D-1; N inválido vira o padrão; janela com erro de um dia; reprocesso aceito na recoleta; o D-1 lê `DIAS_DE_RECOLETA`; chave sem papel; recusa na seleção vira `ok`; linha sem data vira grão de N dias.
- **Deadman (11):** sem filtro de escopo; sem filtro de origem; completude por truthy; parcial vira sucesso; a mais antiga decide; inativo vira ativo; `None` vira "nunca executado"; override ignorado; sem fonte vira "nunca executado"; agenda ambígua aceita.

Merge de teste com `origin/mission/w11-coleta-custo-8kx0pi`: limpo, com 102 testes verdes (deadman Google + Meta, workflows). Este commit não altera `deadman_coleta.py`.

## sha256 (4344502)

```
177e6e4ec3b4b017e1ea195dfec9e43a2731ba10845731a04a4952f109995ed6  n8n/gerar_flows_meta_ledger.py
e21025f278a991b595eb80b18db12da96158bc04752d8de44d39ea28c0461ba6  n8n/volc_meta_insights_dia_d1.json
412dbf5ebd4d3df221b0ba69e9bed81abafa09a39659cecac9a184c3c2f7ed56  n8n/volc_meta_insights_dia_recoleta.json
b27a3445a7321d6d851acbe1d8d686a1a2ac5ff03053a10501f857f45872f90c  backend/app/trafego/meta/deadman_insights.py
07106a6156d4c02ebea047a2c6030e343a57bef6fe237ebcfcb5679ea4f7710c  backend/tests/test_meta_recoleta_n8n.py
c7a53c4adef07ef74f03448d7b7687115ac86dc04ed6854dc4e927eee2341d87  backend/tests/test_meta_deadman_insights.py
49751d735219b4802a8f95b7a95561fcc1045361dae6820721a0b68c46d730de  backend/tests/test_meta_workflows_n8n.py
ca7077b95b9894c388769c9220d890be527ed2d93d28c1b5a66e14c2dcd25c42  scripts/validar_workflows_n8n_meta.py
d737a391e2a091c7d840ce243e81036b35360aa2b1c9b79e99642c587f6684c6  scripts/gate_agenda_unica_gads.py
```

## Lacunas (honestas, não corrigidas)

1. **Nada provado contra a Meta nem contra o banco.** O schema Meta está ausente no Supabase oficial (`docs/closure/meta-operator-go-live-v1/SCHEMA-APPLY-RECEIPT.json`). A credencial n8n não existe. A Meta hoje só tem a campanha raiz PAUSED. A premissa de que as ações de um dia mudam depois do D-1 **não foi medida**.
2. **Reexecução corretiva no mesmo dia fica invisível.** Uma rodada das 08:30 falha, a rodada manual das 13:00 dá certo, e as duas têm a mesma chave de fechamento. A RPC grava todo fechamento como `resultado='ok'` e deduplica por isso, então descarta a segunda. O deadman fica FALHOU até o dia seguinte. É herdado do desenho da chave estável e da RPC; corrigir exige mexer na RPC (migration).
3. **[Resolvida no ciclo 3 por migration candidata, não aplicada]** **A view latest não prefere revisão completa.** `vw_trafego_meta_insight_latest` pega o `observado_em` mais recente, mesmo com `completo=false` ou com métrica NULL. A recoleta multiplica as revisões por 7. Também precisa de migration.
4. **O publicador só conhece o D-1.** `scripts/publicar_workflows_n8n_meta.py` não publica a recoleta, e a trinca (gerador, dono, contrato_sha256) é igual nos dois. Publicar a recoleta hoje seria manual.
5. **O deadman não tem consumidor de produção.** Também não sabe se o fechamento veio da agenda ou de uma rodada manual, e não distingue um canário (`CONTAS_PERMITIDAS`) de uma rodada completa. A tolerância padrão é zero, igual ao Google: quem consultar precisa passar `tolerancia_atraso` e `ativo_na_instancia`.
6. **O validador prova os offsets por texto.** A prova semântica está nas simulações em `node`.
7. **Hipóteses não medidas:** N=7 pode não cobrir eventos CAPI tardios. O D-1 e a recoleta compartilham a cota da Graph. A releitura com paginação diferente no mesmo dia pode perder linhas.
8. **A hierarquia Meta não tem agenda.** Os insights em nível adset dependem de `trafego_meta_adset` atualizado para casar com campanha e projeto, e o único caminho de hierarquia hoje é a rota local.

## Para o integrador

Merge `--no-ff` do commit do ciclo 5 (inclui `2448627` e todos os anteriores), só depois da reconfirmação e na ordem que o integrador definir. A ordem com a W11 é indiferente (mescla limpa).

Depois, reconciliar P11-T06/T20/T25 como `partial`, com a prova acima e as lacunas 1 a 8. Não marcar `done`.

Para ligar, nesta ordem e com autorização do Tarcisio:

1. aplicar o schema Meta;
2. aplicar `v26_01` (depois da cadeia Meta; ver ciclo 3);
3. provisionar a credencial;
4. canário D-1 com uma conta;
5. depois, a recoleta. **Pré-condição: `v26_01` aplicada.**

## Ciclo 3: v26_01, a view latest prefere a revisão completa

Pedido do coordenador após a aprovação de `4344502`: antes de ligar qualquer recoleta, a "latest" precisa preferir a revisão completa.

**Regra nova.** `vw_trafego_meta_insight_latest` continua com `DISTINCT ON` no grão, mas ordena por `completo DESC, observado_em DESC`. Entre as revisões completas ganha a mais recente. Um grão que só tem revisões incompletas continua aparecendo, com a mais recente e `completo=false` visível: ausência de completa não some nem vira zero. As views financeiras dependentes não mudam de forma.

| arquivo | conteúdo |
|---|---|
| `supabase/migrations/v26_01_meta_insight_latest_completa.sql` | Guarda: papel `postgres`/`supabase_admin`, view e coluna `completo` existentes, recusa reaplicar sobre si mesma. `CREATE OR REPLACE VIEW` com `security_invoker` preservado, comentário novo, grants reafirmados iguais |
| `supabase/migrations/v26_01_rollback.sql` | Devolve a view, o comentário e os grants originais. Idempotente |
| `backend/tests/test_meta_v26_01_latest_completa.py` | Pula sem `VOLC_PG_DESCARTAVEL`. Aplica a cadeia Meta num banco temporário, semeia 4 grãos sintéticos e prova o ciclo inteiro |
| `tools/freedom-lab/db/suites/v26_w15.sh` | Suíte do `lab.sh` (`MIGRATION_SUITE`), mesmas asserções, com impressão digital da view (viewdef, reloptions, ACL, comentário, colunas) |

**Casos semeados (sintéticos):** A, completa antiga + incompleta nova → a completa; B, duas completas → a mais nova; C, só incompletas → a incompleta mais nova; D, completa, incompleta, completa mais nova → a última completa.

**Comandos e resultados (nuvem, PG16 descartável em socket local, sem credenciais):**

```
VOLC_PG_DESCARTAVEL=... pytest backend/tests/test_meta_v26_01_latest_completa.py   → 2 passed
  antes : 1001=w15-a2:false (o defeito)
  depois: 1001=w15-a1:true, 1002=w15-b2:true, 1003=w15-c2:false, 1004=w15-d3:true
  anon/authenticated negados; service_role só SELECT; security_invoker mantido
  reaplicar recusado sem alterar a view; rollback restaura a impressão digital; rollback 2x idem
  papel não dono é recusado
suíte v26_w15.sh via stub de lab.sh contra o mesmo PG16                          → ok=26 falhou=0
pytest dos 4 arquivos Meta                                                       → 82 passed
```

Mutações conferidas, ambas derrubam o teste: `completo ASC`; `observado_em` antes de `completo`.

**O que isto não prova.** A prova oficial é `lab.sh recriar-prod` no Mac com `MIGRATION_SUITE=tools/freedom-lab/db/suites/v26_w15.sh`; o stub da nuvem só imita os helpers. Como o schema Meta não está em produção, a suíte aplica a cadeia Meta faltante dentro do container antes da v26_01. As linhas semeadas ficam no container (os triggers append-only bloqueiam DELETE; o container é descartado).

**sha256 (bf968bc, só o delta; os demais arquivos são os de 4344502):**

```
37e39a43d7bb12f1101421b30fb74b1489214318e603c506736b750d5edb0a71  supabase/migrations/v26_01_meta_insight_latest_completa.sql
2fb5f22184c9969234e5fd26f412a3fa9a889761635609f208c8d7eb5bb2a322  supabase/migrations/v26_01_rollback.sql
29770ffde2ee76057540853af5491b639fe59d7a5967c3ec8f99708f7a0e3a1b  backend/tests/test_meta_v26_01_latest_completa.py
927ccfd5e650be4ea8fa183a444e2f156cc6fc49fea2cc17ba59c003f95d04bc  tools/freedom-lab/db/suites/v26_w15.sh
```

Workflows continuam inativos e a credencial continua placeholder. Nenhum workflow foi tocado neste ciclo.

## Ciclo 3b: a semente da suíte com a referência vazia

**O que falhou no Mac.** O integrador não mesclou `bf968bc`. Os gates herméticos passaram, mas o `lab.sh recriar-prod` falhou na semente: o INSERT em `public.cofre_ativo` violou a FK `(kind, cluster)=(meta_ad_account, paid_media)`. O dump de produção é schema-only, então `cofre_gaveta` e `cofre_tipo` chegam vazias. A prova da nuvem não pegou isso porque aplicava a `v13_01` inteira, com os dados de referência.

**Reproduzido na nuvem.** Apliquei a `v13_01` num banco, fiz `pg_dump --schema-only` e restaurei num banco novo (`cofre_gaveta=0`, `cofre_tipo=0`). A suíte de `bf968bc` falhou ali com a mesma mensagem: `Key (kind, cluster)=(meta_ad_account, paid_media) is not present in table "cofre_tipo"`.

**Correção (só a suíte e o teste; migration e rollback não mudaram).**

- A suíte semeia via `PA`, antes do `cofre_ativo`, só a gaveta `paid_media` e o tipo `(meta_ad_account, paid_media)`, com os valores literais da `v13_01` e `ON CONFLICT DO NOTHING`. Depois afirma que os dois existem e para se não existirem.
- Cada INSERT de prova (ativo, conta e os 9 fatos) confere **exatamente 1 linha** via `RETURNING`, o que não depende do `-q` do psql. Depois confere 9 revisões no fato. A suíte não tem UPDATE de prova.
- O pytest espelho esvazia `cofre_tipo` e `cofre_gaveta` logo depois da `v13_01`, para reproduzir a base do Mac, e usa as mesmas contagens.

**Resultados (PG16 descartável, stub dos helpers do `lab.sh`):**

```
base schema-only (referência vazia, como no Mac)   → ok=39 falhou=0
base com v13_01 completa (referência presente)     → ok=39 falhou=0
banco vazio, sem v13_01                            → ok=39 falhou=0
mutação: INSERT do ativo engole conflito (0 linhas) → FALHOU "semente ativo: 0 linha(s), esperado 1"
pytest test_meta_v26_01_latest_completa.py         → 2 passed
  mutação sem a semente de referência              → 2 errors (FK), como esperado
pytest dos 4 arquivos Meta                          → 82 passed
```

A prova oficial continua sendo o `lab.sh recriar-prod` no Mac, que ainda não rodou sobre `908e556`.

**sha256 (908e556):**

```
37e39a43d7bb12f1101421b30fb74b1489214318e603c506736b750d5edb0a71  supabase/migrations/v26_01_meta_insight_latest_completa.sql   (igual a bf968bc)
2fb5f22184c9969234e5fd26f412a3fa9a889761635609f208c8d7eb5bb2a322  supabase/migrations/v26_01_rollback.sql                      (igual a bf968bc)
10f14ae3d487a91ac3d81200b2b436b646be53d82632c34db4747913a53e7659  backend/tests/test_meta_v26_01_latest_completa.py
20d4216b592835bcef6f4812c58dae4d9f15c5fc4de6facdd04d9665f6c09f62  tools/freedom-lab/db/suites/v26_w15.sh
```

Workflows continuam inativos e a credencial continua placeholder.

## Ciclo 3c: os loops da suíte e o stdin do `docker exec -i`

**O que falhou no Mac.** Na prova oficial de `908e556`, 2 de 9 checks falharam. A referência do Cofre entrou, mas a semente parou no primeiro fato: `4 grãos, 9 revisões no fato (esperado=9 obtido=1)`. No Mac, P e PA são `docker exec -i ... psql`, e o docker repassa ao container todo o stdin do chamador, mesmo com `-c`. A primeira chamada dentro de `while read ... done <<< "$fatos"` engolia as linhas seguintes. O stub da nuvem não lia stdin, por isso passou aqui.

**Reproduzido na nuvem.** Com um stub fiel (P e PA como `cat | psql`), a suíte de `908e556` quebra. Aqui o loop da cadeia também é engolido pelo `w15_sql` dentro do `if`, então só a `v13_01` é lida e a semente falha na conta.

**Correção:**

- Toda chamada P/PA que não lê SQL do stdin (`w15_sql`, `w15_contar`) recebe `< /dev/null`.
- Os dois loops (cadeia e fatos) leem por fd 3 (`read ... <&3` / `done 3<<< ...`).
- A suíte afirma que percorreu os 6 arquivos da cadeia. A contagem de 9 revisões no fato já existia.
- Novo `backend/tests/test_meta_v26_w15_suite_lab.py` versiona o stub fiel. Ele monta a base por dump schema-only da `v13_01` (referência vazia) e roda a suíte inteira. Um segundo teste prova que o stub engole o stdin (um loop de 3 linhas lê só 1).

**Resultados (PG16 descartável):**

```
pytest test_meta_v26_w15_suite_lab.py, suíte c34a597          → 2 passed (ok=40 falhou=0)
pytest test_meta_v26_w15_suite_lab.py, suíte do pai 908e556   → 1 failed ("semente conta"), 1 passed
stub antigo (sem consumir stdin), suíte c34a597               → ok=40 falhou=0
pytest dos 5 arquivos Meta                                    → 84 passed
sem VOLC_PG_DESCARTAVEL                                       → 2 skipped (não é prova)
```

A migration e o rollback não mudaram. A prova oficial continua sendo o `lab.sh recriar-prod` no Mac, que ainda não rodou sobre `c34a597`.

**sha256 (c34a597):**

```
37e39a43d7bb12f1101421b30fb74b1489214318e603c506736b750d5edb0a71  supabase/migrations/v26_01_meta_insight_latest_completa.sql   (igual)
2fb5f22184c9969234e5fd26f412a3fa9a889761635609f208c8d7eb5bb2a322  supabase/migrations/v26_01_rollback.sql                      (igual)
10f14ae3d487a91ac3d81200b2b436b646be53d82632c34db4747913a53e7659  backend/tests/test_meta_v26_01_latest_completa.py           (igual)
08856fcd0959f8cdb14eaa1bc74e2e6647fab7db841efea8be78420c149b23d5  tools/freedom-lab/db/suites/v26_w15.sh
7f089912f16ced5ce5e1628dd169efb0d88043fdd4ecc4060d499e907e408240  backend/tests/test_meta_v26_w15_suite_lab.py
```

Workflows continuam inativos e a credencial continua placeholder.

## Ciclo 4: o rollback devolve o estado exato de produção

**O que falhou no Mac** (RECIBO-w15-c34a5971-devolvido.md, no Mac, não lido daqui). Em produção, `vw_trafego_meta_insight_latest` não tem COMMENT (dono `postgres`). A v26_01 gravava um COMMENT novo, e o rollback (`v26_01_rollback.sql:62` em `c34a597`) gravava o COMMENT da migration original. Assim o rollback não devolvia o fingerprint de antes. Os dois arquivos também reafirmavam grants por nome, o que mudaria a ACL se a de produção fosse diferente da do repositório.

**Correção.** Commit novo sobre `c34a597`, sem reescrever a linhagem.

- A v26_01 e o rollback não emitem mais COMMENT, GRANT nem REVOKE. O `CREATE OR REPLACE VIEW` preserva dono, ACL e COMMENT; só a definição muda. Isso substitui o "grants reafirmados" dos ciclos 3 a 3c.
- O `WITH (security_invoker = true)` reescreve reloptions. Conferi que um `CREATE OR REPLACE` sem `WITH` zera essa opção. Por isso as duas guardas recusam rodar se reloptions não forem exatamente `security_invoker=true`, em vez de mudá-las em silêncio.

**Testes:**

- `test_meta_v26_01_latest_completa.py` roda em três estados de partida:
  - `repositorio`: com COMMENT;
  - `producao`: sem COMMENT;
  - `acl_extra`: sem COMMENT e com um grant a mais.
- Em cada estado ele prova:
  - COMMENT, ACL e dono iguais depois de aplicar e depois de reverter;
  - fingerprint pré igual ao pós-rollback;
  - rollback duas vezes dá o mesmo resultado;
  - reaplicar dá o mesmo fingerprint;
  - as duas guardas recusam reloptions diferentes sem mudar nada.
- `test_meta_v26_w15_suite_lab.py` roda a suíte com o stub fiel (stdin consumido) sobre duas bases montadas por dump schema-only, com referência do Cofre vazia:
  - `so_cofre`;
  - `producao`: cadeia Meta aplicada e view sem COMMENT.
- A suíte passou a afirmar "aplicar não mexe em COMMENT, ACL nem dono" e "rollback devolve COMMENT, ACL e dono de antes". Ela também imprime o estado de antes.

**Resultados (PG16 descartável):**

```
pytest test_meta_v26_01_latest_completa.py   → 9 passed (3 estados × 3 testes)
  com o SQL do pai c34a597                   → 6 failed (os 3 estados no ciclo e na guarda de reloptions)
pytest test_meta_v26_w15_suite_lab.py        → 4 passed (ok=42 falhou=0 nas duas bases)
  com o SQL do pai c34a597                   → 2 failed; na base producao: "rollback devolve o fingerprint de antes
                                               (obtido cd4f… | esperado fe23…)", o mesmo defeito do Mac
pytest dos 5 arquivos Meta                   → 93 passed
sem VOLC_PG_DESCARTAVEL                      → 13 skipped (não é prova)
```

Nenhuma leitura ou escrita de produção. A base `producao` é uma recriação a partir do repositório, com o COMMENT removido como o recibo descreve, e não um dump real. A prova oficial continua sendo o `lab.sh recriar-prod` no Mac.

**sha256 (2448627):**

```
186cf16f7ba77d9f76cc07eafbc876705e396b2131d3f823ac935dfd43b235fb  supabase/migrations/v26_01_meta_insight_latest_completa.sql
fecb43cc2688970f9ac8ba605ad191f953c8a0f4ad30eede494a41f75cfd97d0  supabase/migrations/v26_01_rollback.sql
196214ac502ea535c53554a772e1d104e94f9360a2dba92241e7ad0bbe14dca4  backend/tests/test_meta_v26_01_latest_completa.py
854fde3aa948a72a646a98d194bba23dc554bc549176ce93a7eda604a4d9983d  backend/tests/test_meta_v26_w15_suite_lab.py
2de6ab03499b053c8489758ce4730ab8f67c63e8cbd0254a33d8d869cde5a7c2  tools/freedom-lab/db/suites/v26_w15.sh
```

Os workflows continuam inativos e a credencial continua placeholder.

## Ciclo 5: ressalvas da revisão de 2448627

`2448627` passou no lab do Mac com 42/42 e foi aprovado com ressalvas baixas (R-mission-w15-2448627.md, nos handoffs do Mac, não lido daqui; os itens vieram do coordenador). Fechei as quatro num commit novo por cima, sem reescrita.

1. **Comentários errados:**
   - A suíte dizia que o schema Meta não está no Supabase oficial. Agora diz que a prova de `2448627` encontrou a view no dump (dono `postgres`, sem COMMENT) e que o recibo SCHEMA-APPLY de 07/09 está defasado.
   - A migration dizia "provada só em PostgreSQL 16 descartável". Agora cita a prova do lab do Mac (42/42) e os dois testes herméticos.
2. **Checagens fail-closed na suíte:**
   - `w15_fp` e `w15_meta` validam a leitura. O fingerprint precisa ser um md5; o COMMENT/ACL/dono precisa do prefixo esperado. Erro do psql, saída vazia ou ACL nula viram `INVALIDO[...]`.
   - O fingerprint agora devolve NULL quando a ACL é nula. O COMMENT nulo vira `<sem COMMENT>` em vez de sumir do `concat_ws`.
   - Toda comparação passa por `w15_igual`, que **falha** se qualquer lado for inválido. Antes, dois erros iguais passavam por igualdade.
   - O pytest tem a mesma regra (`Banco.fp()` e `Banco.meta()`).
3. **`lock_timeout`:** `SET LOCAL lock_timeout = '5s'` logo depois do `BEGIN`, na migration e no rollback. Com uma leitura longa segurando a view, os dois falham com `lock timeout`, desfazem e não mudam o fingerprint, em vez de enfileirar os leitores seguintes.
4. **Handoff na branch:** cópia em `docs/handoffs/W15-meta.md`, porque o revisor do Mac não enxerga `/mnt/project-files`.

**Testes novos:**
- `test_lock_timeout_falha_e_desfaz_em_vez_de_esperar`, nos 3 estados de partida:
  - um leitor segura AccessShareLock;
  - a migration e o rollback falham entre 4 e 30 s com `lock timeout`;
  - o fingerprint não muda;
  - sem o leitor, a migration volta a aplicar.
- `test_leituras_da_suite_falham_com_erro_ou_acl_nula`, nas 2 bases:
  - na base `so_cofre` a view não existe e a leitura dá erro;
  - na base `producao` a ACL é forçada a nula;
  - nas duas, `w15_igual` de uma leitura consigo mesma dá FALHOU, com `ok=0 falhou=2`.

**Resultados (PostgreSQL descartável, sem produção):**

```
pytest dos 5 arquivos Meta                        → 98 passed
  test_meta_v26_01_latest_completa.py             → 12 passed (3 estados × 4 testes)
  test_meta_v26_w15_suite_lab.py                  → 6 passed (suíte ok=42 falhou=0 nas 2 bases)
sem VOLC_PG_DESCARTAVEL                           → 18 skipped (não é prova)
mutação: w15_igual sem a checagem de inválido     → 2 failed
mutação: sem lock_timeout na migration            → 1 failed ("esperou o lock por 30s")
```

A prova oficial no `lab.sh` do Mac sobre este commit ainda não rodou. Os workflows continuam inativos e a credencial continua placeholder.
