# P04-T07 · Observabilidade PMax operacional — handoff factual

**Data:** 2026-09-01
**Branch:** `sprint/hermes-p04-t07-pmax-observability-v1`
**Base oficial:** `812ab0d4ab3091072e695f52db6e117f04aa2ce7`
**HEAD após convergência (ponto de partida desta lane):** `046cbb9`
**HEAD ao fim desta lane:** ver `git rev-parse HEAD` (último commit é este documento)

Esta lane **não editou** `volc-os-workbook/ROADMAP-VIVO.json`, `docs/volc-os-graph/curadoria-operacional.json`,
`graphify-out/**`, `backend/app/trafego/**`, `src/**`, `supabase/migrations/**` nem
`inventario-n8n/**`. As propostas de Roadmap e de curadoria estão nas seções 10 e 11,
para o integrador único aplicar e reconstruir o Mapa Vivo **uma vez** após o merge.

---

## 1. O que esta entrega faz, e o que ela deliberadamente não faz

Operacionaliza a leitura **read-only** de uma campanha Performance Max já existente,
nomeada por identidade canônica completa, no contrato canônico de inteligência Google
Ads (`volc_ads/inteligencia_google`).

A missão **não** cria, altera, ativa, pausa ou remove campanha; não aplica nem dispensa
recomendação; não baixa mídia; não infere qualidade visual; não cria migration; não
escreve no Supabase oficial; e não executou nenhuma leitura real de conta Google
(ver seção 8, `REAL_READ_NOT_PROVEN`).

O núcleo `volc_ads/observabilidade_pmax` **já existia** e não foi tocado: ele é
consumido como biblioteca de construção de GAQL. O delta desta lane é o **coletor
produtivo** — quem executa aquelas consultas, projeta o resultado no contrato canônico,
grava recibo e diz a verdade sobre o que não conseguiu gravar.

## 2. Commits atômicos

| SHA | Mensagem |
|---|---|
| `7c11530` | `test(inteligencia): as catorze contraprovas da observabilidade PMax, vermelhas` |
| `feb0b87` | `feat(inteligencia): a familia da leitura entra no recibo e na chave` |
| `be26ba3` | `feat(inteligencia): as sete perguntas de Performance Max, read-only` |
| `14894c1` | `feat(inteligencia): o coletor fotografa o alvo PMax e nomeia o que o ledger recusa` |
| `ae30eb2` | `feat(cli): --pmax le a estrutura do alvo e imprime resumo sanitizado` |
| (este) | `docs(closure): handoff de P04-T07, com a lacuna do ledger nomeada` |

## 3. Arquivos tocados (todos dentro do ownership)

```
backend/tests/test_google_inteligencia_pmax.py   +1164   (novo)
volc_ads/inteligencia_google/pmax.py              +831   (novo)
volc_ads/inteligencia_google/coletor.py           +276
scripts/coletar_google_inteligencia.py             +63/-17
volc_ads/inteligencia_google/modelo.py             +37
volc_ads/inteligencia_google/__init__.py           +10
```

2364 inserções, 17 remoções, 6 arquivos. Nenhum arquivo fora da lista permitida.

## 4. As sete famílias, e por que são sete

Uma família é a **pergunta** que a leitura respondeu. Elas são separadas porque falham
separadamente: se os sinais caírem, a estrutura lida continua válida, e um recibo único
transformaria uma queda parcial num retrato inteiro suspeito.

| # | Família | Recurso GAQL | Janela | `tipo_sinal` pedido | Cabe no ledger hoje? |
|---|---|---|---|---|---|
| 1 | `PMAX_CAMPANHA` | `campaign` | — | `PMAX_CAMPANHA` | **não** |
| 2 | `PMAX_ASSET_GROUPS` | `asset_group` | — | `PMAX_ASSET_GROUPS` | **não** |
| 3 | `PMAX_ASSET_GROUP_ASSETS` | `asset_group_asset` | — | `PMAX_ASSET_GROUP_ASSETS` | **não** |
| 4 | `PMAX_ASSETS` | `asset` | — | `PMAX_ASSETS` | **não** |
| 5 | `PMAX_DESEMPENHO_ASSET_GROUP` | `asset_group` + `metrics` | 14 dias | `PMAX_DESEMPENHO_ASSET_GROUP` | **não** |
| 6 | `PMAX_SINAIS` | `asset_group_signal` | — | `PMAX_SINAIS` | **não** |
| 7 | `PMAX_RECOMENDACOES_FORCA` | `recommendation` | — | `RECOMENDACOES_ARMAZENADAS` | **sim** |

Dependências declaradas, nunca implícitas: `PMAX_ASSETS` só sabe quais assets pedir
depois de `PMAX_ASSET_GROUP_ASSETS`, e `PMAX_SINAIS` depois de `PMAX_ASSET_GROUPS`.
Quando o pré-requisito **não concluiu**, a família dependente vai a `falhou` com
`erro_codigo=PREREQUISITO_NAO_LIDO` — nunca a `vazio_confirmado`. Perguntar sem recorte
leria a conta inteira, e uma leitura larga disfarçada de resposta é pior que a falha
honesta.

## 5. Queries e campos realmente validados

**Validação usada:** descritores do SDK instalado (`google-ads 31.4.0`, versão padrão
`v25`) + doutrina oficial lida em **01/09/2026**. Nenhuma leitura real de conta.

### 5.1 Confirmado presente na v25 instalada

| Recurso | Campos conferidos |
|---|---|
| `campaign` | `id`, `resource_name`, `name`, `status`, `primary_status`, `primary_status_reasons`, `serving_status`, `advertising_channel_type`, `bidding_strategy_type`, `start_date_time`, `brand_guidelines_enabled` |
| `asset_group` | `id`, `resource_name`, `name`, `campaign`, `status`, `primary_status`, `primary_status_reasons`, `ad_strength`, `asset_coverage.ad_strength_action_items{.action_item_type,.add_asset_details.*}`, `final_urls`, `final_mobile_urls`, `path1`, `path2` |
| `asset_group_asset` | `resource_name`, `asset_group`, `asset`, `field_type`, `status`, `primary_status`, `primary_status_reasons`, `primary_status_details.*`, `source`, `policy_summary.*` |
| `asset` | `id`, `resource_name`, `name`, `type`, `text_asset.text`, `youtube_video_asset.*`, `image_asset.full_size.url`, `policy_summary.*` |
| `asset_group_signal` | `resource_name`, `asset_group`, `audience.audience`, `search_theme.text` |
| `metrics` | `impressions`, `clicks`, `cost_micros`, `conversions`, `conversions_value` |
| `segments` | `date`, `ad_network_type` |
| `recommendation` | `resource_name`, `type`, `campaign`, `dismissed`, `improve_performance_max_ad_strength_recommendation.{asset_group,ad_strength}` |
| enum | `RecommendationType.IMPROVE_PERFORMANCE_MAX_AD_STRENGTH` presente |

### 5.2 Doutrina oficial consultada (01/09/2026)

| Página | O que ela decidiu aqui |
|---|---|
| `/performance-max` | Última atualização declarada: **20/08/2025**. Não declara versão de API na página. |
| `/performance-max/asset-group-reporting` | Desempenho por grupo é `FROM asset_group` + `metrics.*` + `segments.date`; segmentação por canal é `segments.ad_network_type`. Copiado literalmente. |
| `/performance-max/asset-reporting` | Estatísticas completas existem no nível do asset (`FROM asset_group_asset`). **Não menciona** `performance_label` nem `segments.asset_interaction_target`. |
| `/performance-max/asset-group-signals` | `asset_group_signal` expõe `audience`, `search_theme`, `approval_status`, `disapproval_reasons`. |
| `/performance-max/asset-requirements` | HEADLINE 3–15, LONG_HEADLINE 1–5, DESCRIPTION 2–5, BUSINESS_NAME 1–1, LOGO 1–5, MARKETING_IMAGE 1–20, SQUARE_MARKETING_IMAGE 1–20, PORTRAIT 0–20, LANDSCAPE_LOGO 0–20, YOUTUBE_VIDEO 0–15, CTA 0–1, MEDIA_BUNDLE 0–1. Brand Guidelines move `BUSINESS_NAME`/`LOGO`/`LANDSCAPE_LOGO` para `CampaignAsset`. |
| `/performance-max/asset-groups`, `/performance-max/assets` | Páginas de **criação**. Não trazem GAQL de leitura nem campos de relatório — nada foi extraído delas. |
| `/docs/recommendations` | Só o filtro `WHERE recommendation.type = ...` está demonstrado. **Não** há exemplo de filtro por `recommendation.campaign`. |

### 5.3 Divergências entre doutrina e SDK/código local

1. **`asset_group_asset.performance_label` não existe na v25.** A missão pedia
   performance label "quando suportado". O SDK instalado confirma a ausência
   (`performance_label` só aparece em `ad_group_ad_asset_view`, que é de Search) e a
   página de asset-reporting não o menciona. O campo é **nomeado** como não suportado
   no payload de `PMAX_ASSET_GROUP_ASSETS`, e nenhuma métrica com esse nome é emitida
   em família alguma. Contraprova M cobre os dois lados.
2. **Regra "pelo menos uma DESCRIPTION ≤ 60 caracteres".** Ela está implementada em
   `volc_ads/observabilidade_pmax/coverage.py` (e provada em
   `test_long_descriptions_without_one_at_most_60_are_a_real_gap`), mas a página oficial
   de asset-requirements lida hoje **não a menciona**. Não alterei nada: `coverage.py`
   está fora do ownership desta lane. Fica registrado como divergência a reconciliar.
3. **`campaign.end_date` não existe na v25** (só `start_date_time` foi usada). Nenhuma
   consulta desta lane pede `end_date`.
4. **Filtro por campanha nas recomendações.** Como só o filtro por `type` é documentado,
   a consulta pede apenas `recommendation.type = 'IMPROVE_PERFORMANCE_MAX_AD_STRENGTH'`
   e o recorte por campanha é feito **localmente**, comparando
   `recommendation.campaign` com o resource name do alvo. O recibo declara
   `filtro_por_campanha: "local"` e o motivo. Assumir que o campo é filtrável arriscaria
   um erro de consulta que apagaria a família inteira.

## 6. Contraprova → correção → prova

As catorze contraprovas obrigatórias foram escritas **antes** do módulo, no commit
`7c11530`, e falhavam por `ImportError`. Não houve "correção" no sentido de conserto de
defeito: o produto nasceu depois das provas. O que substitui a coluna "correção" é a
**decisão de projeto** que cada contraprova forçou.

| # | Contraprova | Decisão que ela forçou | Prova (teste) |
|---|---|---|---|
| A | PAUSED PMax continua coletável | Nenhuma consulta filtra `campaign.status`; o teste varre a GAQL emitida | `test_a_campanha_pmax_pausada_continua_coletavel`, `test_a_estados_externos_distintos_nao_se_achatam`, `test_a_campanha_ausente_na_resposta_nao_e_campanha_removida` |
| B | Search não entra na coleta PMax | `exigir_canal_pmax` levanta antes de qualquer consulta | `test_b_campanha_search_nao_entra_na_coleta_pmax` |
| C | Duas contas, mesmo `campaign_id`, sem colisão | `customer_id` já compõe a chave; identidade interna + externa viajam juntas em toda família | `test_c_mesma_campanha_em_contas_diferentes_nao_colide`, `test_c_identidade_interna_e_externa_viajam_juntas_em_toda_familia` |
| D | Zero métrica não vira ausência | Métricas do proto v25 têm presença explícita; `metrica_de_dict` preserva `'0'` como `medido` | `test_d_zero_medido_atravessa_como_zero`, `test_d_janela_declarada_viaja_no_recibo` |
| E | Ausência de linha não vira zero | Grupo conhecido sem linha recebe `EstadoValor.AUSENTE`; sem lista de grupos conhecidos **não se inventa ausência** | `test_e_ausencia_de_linha_nao_vira_zero`, `test_e_sem_estrutura_lida_nao_se_inventa_grupo_ausente` |
| F | Consulta verde sem recomendação ≠ falha | `vazio_confirmado` com `quantidade=0` e `erro_codigo=None`; `inelegivel` só quando a campanha PMax **foi lida e não existe** | `test_f_zero_recomendacoes_e_vazio_confirmado_nao_falha`, `test_f_recomendacao_de_outra_campanha_nao_conta_como_desta`, `test_f_campanha_pmax_ausente_torna_recomendacao_inelegivel`, `test_f_recomendacao_e_segunda_opiniao_nunca_ordem` |
| G | Falha da API não vira lista vazia | `_persistir_pmax` converte exceção em `FALHOU` com código/classe; nunca em lista | `test_g_falha_da_api_nunca_vira_lista_vazia` (5 famílias), `test_g_assets_sem_prerequisito_falha_em_vez_de_fingir_vazio`, `test_g_sem_vinculo_lido_a_familia_de_assets_e_vazio_observado` |
| H | Campo não suportado não derruba família independente | `performance_label` é nomeado no payload; famílias são laços independentes; segmentação por canal cai sozinha e rebaixa só a família de desempenho a `parcial` | `test_h_performance_label_ausente_na_v25_e_nomeado_nao_inventado`, `test_h_campo_nao_suportado_e_fato_do_sdk_instalado`, `test_h_uma_familia_caida_nao_derruba_as_independentes`, `test_h_segmentacao_por_canal_caida_deixa_desempenho_parcial`, `test_h_ad_strength_ausente_nao_recebe_valor` |
| I | Retry verde não apaga recibo vermelho | Estado (e código/classe da falha) já compõem a chave de idempotencia | `test_i_falha_e_retry_verde_preservam_os_dois_recibos` |
| J | Repetir a mesma janela é idempotente | `familia` entra na chave como componente **adicional**; chaves antigas ficam byte a byte iguais (valor congelado no teste) | `test_j_repetir_o_mesmo_alvo_e_janela_nao_duplica_fatos`, `test_j_familias_pmax_nao_colidem_entre_si_na_chave`, `test_j_familia_entra_na_chave_sem_mexer_nas_chaves_antigas` |
| K | Nenhuma query dispara mutate | Toda GAQL passa por `assert_read_only_gaql` na construção e pelo guarda de `SELECT` do coletor; o dublê explode em qualquer superfície fora de `GoogleAdsService.search_stream` | `test_k_toda_consulta_pmax_e_select_read_only`, `test_k_coleta_pmax_so_fala_com_googleadsservice`, `test_k_modulo_pmax_nao_contem_mutacao_google`, `test_k_pmax_nao_importa_agenda_nem_superficie_de_escrita` |
| L | Bloqueador não fica verde só por impressions | `avaliar_prontidao_pmax` exige as sete famílias, cada uma observada **e persistida** **e recente** | `test_l_impressions_positivas_nao_provam_prontidao`, `test_l_familia_lida_mas_nao_persistida_nao_prova_prontidao`, `test_l_fotografia_completa_e_recente_prova_prontidao`, `test_l_fotografia_velha_deixa_de_provar`, `test_l_familia_ausente_da_fotografia_nao_e_familia_verde`, `test_l_veredito_da_propria_execucao_se_declara_autoatestado` |
| M | Sem `performance_label` não se inventa valor | Ver H; e o asset não ganha qualidade inferida, nem há cliente HTTP no módulo | `test_m_asset_sem_metadado_nao_ganha_qualidade_inferida` |
| N | Campanha sem PMax recusa antes da coleta | Identidade primeiro, canal depois, consulta por último; `UNKNOWN`/`UNSPECIFIED` falham fechado e não viram PMax | `test_n_recusa_acontece_antes_de_qualquer_consulta`, `test_n_canal_sem_informacao_nao_vira_pmax` |

### 6.1 As provas foram testadas por mutação

Onze mutações dirigidas foram aplicadas ao produto e revertidas; **todas mataram pelo
menos uma prova**. Uma suíte que sobrevive à mutação do que ela afirma proteger não
protege nada.

| Mutação aplicada | Resultado |
|---|---|
| ausência de linha vira zero medido | MORREU (1 falha) |
| canal deixa de ser exigido | MORREU (2 falhas) |
| ledger passa a aceitar qualquer `tipo_sinal` | MORREU (2 falhas) |
| `familia` sai da chave de idempotência | MORREU (1 falha) |
| verde sem recomendação vira falha | MORREU (2 falhas) |
| pré-requisito caído vira vazio | MORREU (1 falha) |
| prontidão ignora persistência | MORREU (1 falha) |
| zero medido vira ausência | MORREU (2 falhas) |
| falha da API vira `vazio_confirmado` | MORREU (10 falhas) |
| segmentação caída deixa de rebaixar a `parcial` | MORREU (1 falha) |
| veredito deixa de se declarar autoatestado | MORREU (1 falha) |

## 7. Gates executados

| # | Gate | Comando | Resultado |
|---|---|---|---|
| 1 | Focais PMax | `backend/.venv/bin/python -m pytest backend/tests/test_google_inteligencia_pmax.py -q -p no:randomly` | **55 passed** |
| 2 | Herdados P09-T14 + Google | `... test_google_inteligencia_persistente.py test_google_inteligencia_saude.py test_observabilidade_pmax.py test_google_ads_auth.py` | **139 passed** |
| 3 | Suíte backend inteira | `backend/.venv/bin/python -m pytest backend/tests/ -q -p no:randomly` | **2002 passed, 102 skipped, 0 failed** (baseline antes desta lane: 1947 passed / 102 skipped; delta = +55, exatamente os testes novos) |
| 3b | Suíte `volc_ads/` (ownership) | `backend/.venv/bin/python -m pytest volc_ads/ -q -p no:randomly` | **706 passed, 0 failed** — inclui `volc_ads/campanha/testes_pmax.py`. ⚠️ Precisa do `pytest.ini` da **raiz** (`python_files = test_*.py testes_*.py`); com `-c backend/pytest.ini` a coleta devolve "no tests ran" e a contagem verde não significa nada. |
| 4 | Ausência de mutação Google | varredura de 8 arquivos + verificação das 8 GAQL | **nenhum achado**; 8 consultas confirmadas `SELECT`/read-only |
| 5 | `git diff --check` | `git diff --check <base>..HEAD` | **sem achados** |
| 6 | Credenciais no diff | 9 padrões (JWT, service_role, chave privada, AWS, OAuth Google, refresh token, `*.supabase.co`, IP do servidor, `key/secret/password/token`) sobre 2364 linhas adicionadas | **nenhum achado** |
| 7 | Árvore limpa | `git status --porcelain` | **vazio** |

Ambiente: `backend/.venv` (Python 3.11), `pytest` com `-p no:randomly`, `google-ads 31.4.0`.
Nenhuma falha de ambiente foi convertida em falha de produto; nenhuma dependência nova
foi necessária.

### 7.1 Revisão final independente

`codex` e `gemini` não estavam disponíveis no `PATH` deste ambiente no fechamento,
portanto a revisão cross-provider foi registrada como
`CROSS_PROVIDER_REVIEW_NOT_AVAILABLE`. Conforme regra da missão, foi executada uma única
revisão focal de contexto fresco com Claude Opus, somente read-only, sem rede, sem Google
Ads e sem Supabase.

**Veredito:** `APROVAR`, sem achados bloqueantes.

**Achados não bloqueantes registrados para handoff futuro:**

1. `asset_coverage_action_items` vazio confirmado pode ficar conservadoramente indistinto
   de campo omitido pelo proto, porque repeated vazio é omitido na projeção usada hoje;
2. falha de RPC/persistência em `registrar(documento)` pode escapar da família persistível
   herdando comportamento de `_persistir_familia`; não é regressão desta lane, mas tensiona
   quedas parciais quando a família é gravável;
3. a prontidão desta execução é explicitamente `execucao_local`/`autoatestada` e não deve
   ser interpretada como releitura direta do ledger sem adaptador;
4. se futura segmentação entrar no `SELECT` de desempenho, a agregação por grupo precisará
   somar linhas em vez de manter a última;
5. leitores futuros de `RECOMENDACOES_ARMAZENADAS` devem filtrar `campaign_id` e
   `payload.familia`, não apenas `tipo_sinal` + `customer_id`.

Nenhum item acima abriu falso verde, mutate, colisão de identidade ou invasão de ownership
nesta entrega; todos falham fechado ou foram nomeados como contrato para integrador futuro.

## 8. Leitura real: `REAL_READ_NOT_PROVEN`

**Nenhuma leitura real de conta Google Ads foi executada nesta lane**, por decisão
explícita da missão (evitar vazamento de dados de conta a modelos externos). Tudo o que
está provado aqui é hermético: protos `GoogleAdsRow` v25 **reais**, montados em memória,
sem socket.

O que isso significa na prática, e que nenhum teste desta lane cobre:

* **selecionabilidade** de cada campo/métrica no recurso escolhido. Os descritores do SDK
  provam que o campo existe no recurso; eles **não** provam que o par
  (recurso, métrica/segmento) é selecionável em GAQL — isso vive no
  `google_ads_field`, que só a API responde;
* se `FROM asset_group` com `metrics.*` devolve linha para grupo sem entrega;
* se `WHERE recommendation.type = '...'` aceita o literal entre aspas nessa conta;
* o volume real de `asset_group_asset` e `asset` (paginação e cota).

### Comando exato para executar a leitura real depois

```bash
cd /root/work/volc-runs/hermes-p04-t07-pmax-observability-v1
# .env com VITE_SUPABASE_URL=https://database.agenciavolc.com.br e
# SUPABASE_SERVICE_ROLE_KEY carregados no ambiente; ~/google-ads.yaml presente.
backend/.venv/bin/python scripts/coletar_google_inteligencia.py \
  --pmax \
  --customer-id      <CUSTOMER_ID_DA_CONTA> \
  --volc-campaign-id <VOLC_CAMPAIGN_ID> \
  --campaign-id      <CAMPAIGN_ID_GOOGLE> \
  --modo completa
```

Saídas: `0` sucesso · `2` identidade incompleta (argparse) · `3` canal não é
`PERFORMANCE_MAX` · `4` falha da API/persistência. A saída em `stdout` é o **resumo
sanitizado** (estado, contagem, recibo e recusas); itens e métricas ficam no banco.

⚠️ Nesta execução, as seis famílias estruturais **não serão gravadas** — elas serão
recusadas com a lacuna nomeada (seção 9). A execução ainda é útil: ela prova a
selecionabilidade das consultas e produz o retrato em memória.

## 9. Lacuna contratual exata (o que ficou por fazer, e por quê)

### 9.1 `tipo_sinal` do ledger v12_01 não admite as famílias PMax

`supabase/migrations/v12_01_google_inteligencia_coletas.sql` fecha `tipo_sinal` num CHECK
de seis valores (`trafego_google_coleta_tipo`). Seis das sete famílias não têm lugar nele.

**Por que não reaproveitei `DIAGNOSTICO_ENTREGA`:**
`backend/app/trafego/diagnostico_persistido.py:567-571` lê a coleta **mais recente** de
`tipo_sinal='DIAGNOSTICO_ENTREGA'` por `volc_campaign_id`. Gravar recibos PMax sob esse
valor faria um recibo PMax passar a responder pelo diagnóstico Search da mesma campanha —
uma regressão silenciosa numa superfície que esta lane está proibida de editar. Gravar
sob qualquer um dos outros cinco seria mentir sobre a pergunta respondida.

**O que a coleta faz em vez disso:** lê tudo, produz o documento canônico, e **para
apenas a persistência** dessas seis, com recusa estruturada em cada recibo:

```json
{
  "familia": "PMAX_ASSET_GROUPS",
  "tipo_sinal": "PMAX_ASSET_GROUPS",
  "motivo": "o CHECK trafego_google_coleta_tipo da v12_01 nao admite 'PMAX_ASSET_GROUPS'; gravar sob um dos seis valores existentes faria este recibo responder por outra pergunta",
  "migration_necessaria": "v12_03: ALTER TABLE ... CHECK (tipo_sinal IN (<os seis atuais>, 'PMAX_CAMPANHA', 'PMAX_ASSET_GROUPS', 'PMAX_ASSET_GROUP_ASSETS', 'PMAX_ASSETS', 'PMAX_DESEMPENHO_ASSET_GROUP', 'PMAX_SINAIS'))"
}
```

**O bloqueio mora no banco, não no código — e isso é executável.** O vocabulário aceito é
injetável (`ColetorGoogleInteligencia(tipos_sinal_do_ledger=...)`); com o vocabulário
ampliado, as **mesmas** famílias atravessam sem uma linha de código diferente
(`test_ampliar_o_vocabulario_basta_para_persistir_tudo`,
`test_recibo_carrega_o_contrato_minimo_da_fotografia`). E a constante local é comparada
com o CHECK do arquivo de migration em
`test_vocabulario_do_ledger_e_o_da_migration_aplicada`, então a lista não pode divergir
do banco em silêncio.

**Migration não foi criada** (hard stop respeitado). A `v12_03` acima é o pedido, não o
artefato.

### 9.2 Campos disponíveis na v25 que esta coleta ainda não pede

| Campo | Por quê |
|---|---|
| `asset_group_signal.approval_status` | A consulta de sinais é `volc_ads/observabilidade_pmax/queries.py`, fora do ownership desta lane. Declarado em `CAMPOS_NAO_COLETADOS` para que a ausência no recibo não seja lida como "o Google não devolveu". |
| `asset_group_signal.disapproval_reasons` | Mesma consulta, mesma razão. |
| `asset_group_top_combination_view.asset_group_top_combinations` | Documentado na doutrina de asset-reporting; fora do escopo declarado da missão. |
| métricas no nível de `asset_group_asset` | A doutrina confirma que existem. Esta lane mede por **asset group**, que é o que a missão §4 pede. |

### 9.3 Campo indisponível na versão instalada

`asset_group_asset.performance_label` — não existe na v25. Ver 5.3.1.

### 9.4 Observação sobre uma superfície pré-existente (não corrigida)

`executar_alvo` (o caminho Search, de P09-T14) **também** produz um recibo
`DIAGNOSTICO_ENTREGA` quando o alvo é uma campanha PMax — com consultas de
`keyword_view` e `ad_group_ad`, que para PMax não retornam nada. Esse recibo já existia
antes desta lane (é o que `test_familia_de_plano_de_palavras_fora_de_search_e_nao_suportada`
exercita) e não foi alterado: mexer nele misturaria mudança funcional de outra lane com
esta entrega. Fica registrado como candidato a revisão — `DIAGNOSTICO_ENTREGA` de uma
campanha PMax descreve uma pergunta que não se aplica àquele canal.

## 10. Bloqueador de prontidão — o que entrego, e o que **não** entrego

`backend/app/trafego/contrato_canais.py` está fora do ownership e **não foi tocado**.
`observabilidade_do_canal("PERFORMANCE_MAX")` continua devolvendo `INDETERMINADO`, e
`pmax_observabilidade_nao_provada` continua fechando `criavel_pausada`.

O que esta lane entrega é a **função de domínio** que um integrador futuro pode usar para
decidir isso com prova, em `volc_ads/inteligencia_google/pmax.py`:

```python
avaliar_prontidao_pmax(fotografia, *, agora, frescor_maximo_segundos=26*3600,
                       linhagem=LINHAGEM_EXECUCAO) -> ProntidaoPMax
```

`provada=True` exige, para **cada uma das sete famílias**, simultaneamente:

1. presença na fotografia (família ausente ≠ família verde);
2. estado em `{com_dados, vazio_confirmado}` — leitura concluída, sem falha silenciosa;
3. `persistido=True` — recibo no ledger, não só na memória do processo;
4. frescor dentro de 26 h.

Campanha existir não basta. Asset group existir não basta. `impressions > 0` não basta —
há prova disso (`test_l_impressions_positivas_nao_provam_prontidao`). HTTP 200 não entra
na conta em lugar nenhum.

⚠️ **Linhagem.** `executar_alvo_pmax` devolve `prontidao_desta_execucao` com
`linhagem="execucao_local"` e `autoatestada: true`. Quem for promover o bloqueador
precisa rodar a mesma função sobre recibos **relidos do ledger**
(`linhagem=LINHAGEM_RELEITURA`). Um veredito autoatestado descreve o que o processo
*acha* que gravou — a linhagem autoatestável já foi derrubada uma vez neste repositório,
no plano de mensuração. Há contraprova para essa distinção
(`test_l_veredito_da_propria_execucao_se_declara_autoatestado`).

**Consequência honesta:** enquanto a lacuna 9.1 existir, `provada` é **sempre `False`**
para as seis famílias estruturais, porque elas nunca chegam a `persistido=True`. O
bloqueador **deve continuar fechado**. Promovê-lo agora seria exatamente o defeito que
esta tarefa existe para evitar.

## 11. Proposta de atualização para P04-T07 (não aplicada)

`volc-os-workbook/ROADMAP-VIVO.json` → `initiatives[3].tasks[6]` (`P04-T07`).

* **status:** permanece **`partial`**. Não promover para `done`.
* **proof (proposto):** "As seis consultas do kernel PMax ganharam coletor produtivo
  (`volc_ads/inteligencia_google/pmax.py` + `executar_alvo_pmax`), com sete famílias
  independentes no contrato canônico, identidade completa, idempotência e CLI one-shot
  fail-closed. Continua partial por dois motivos nomeados: nenhuma leitura real de conta
  foi executada (`REAL_READ_NOT_PROVEN`), e o CHECK `trafego_google_coleta_tipo` da
  v12_01 não admite seis das sete famílias — a persistência delas para com recusa
  estruturada, e destravá-la exige a migration v12_03."
* **evidência a acrescentar:**

> 2026-09-01 · `feb0b87` + `be26ba3` + `14894c1` + `ae30eb2`
> (`sprint/hermes-p04-t07-pmax-observability-v1`): a observabilidade PMax deixou de ser
> só kernel e ganhou coletor. Sete famílias read-only — campanha, asset groups, vínculos,
> assets, desempenho por grupo em janela declarada, sinais e a recomendação oficial
> `IMPROVE_PERFORMANCE_MAX_AD_STRENGTH` — todas no contrato canônico de
> `volc_ads/inteligencia_google`, com recibo, chave de idempotência, erro estruturado e
> famílias que caem separadamente. 55 provas herméticas contra protos v25 reais, das
> quais três decidem esta tarefa: `test_l_impressions_positivas_nao_provam_prontidao`
> (o bloqueador não fica verde por entrega), `test_l_familia_lida_mas_nao_persistida_nao_prova_prontidao`
> (leitura sem recibo não é observabilidade) e
> `test_ampliar_o_vocabulario_basta_para_persistir_tudo` (o bloqueio restante é o CHECK
> do Postgres, não o código). Onze mutações dirigidas mataram provas. Suíte backend:
> 2002 passed / 102 skipped, contra 1947 / 102 antes. PARTIAL: `REAL_READ_NOT_PROVEN` e
> a lacuna do `tipo_sinal` (v12_03) seguem abertas, e
> `pmax_observabilidade_nao_provada` continua fechado por medição, não por esquecimento.

## 12. Proposta de delta para `concept:pmax_observability` (não aplicada)

`docs/volc-os-graph/curadoria-operacional.json` → `concepts[]`, id
`concept:pmax_observability`.

* **state:** permanece **`partial`**.
* **summary:** sem alteração.
* **evidence (proposto):** "O kernel de observabilidade e as consultas de referência
  existem, e em 2026-09-01 elas ganharam coletor produtivo: sete famílias read-only no
  contrato canônico de inteligência Google Ads, com identidade completa, idempotência por
  bucket, erro estruturado e independência entre famílias
  (`volc_ads/inteligencia_google/pmax.py`, `executar_alvo_pmax`, CLI `--pmax`). Continua
  partial por dois fatos medidos, não por falta de código: nenhuma leitura real de conta
  foi executada, e o CHECK `trafego_google_coleta_tipo` da v12_01 admite só uma das sete
  famílias — as outras seis param na persistência com recusa nomeada e a migration v12_03
  pedida. O portão `pmax_observabilidade_nao_provada` segue fechado, e
  `avaliar_prontidao_pmax` explicita o que o abriria: as sete famílias observadas,
  gravadas e recentes, avaliadas sobre recibos relidos do ledger — nunca sobre o
  autoatestado da própria execução."

**Nó novo proposto** (o integrador decide se cria):

```json
{
  "id": "google-inteligencia-pmax",
  "tipo": "modulo",
  "cluster": "aquisicao",
  "rotulo": "Coletor de observabilidade PMax",
  "estado": "ativo",
  "path": "volc_ads/inteligencia_google/pmax.py",
  "evidence": "Domínio e aplicação da leitura read-only de Performance Max: oito GAQL somente-SELECT, sete famílias com estados epistêmicos distintos, adaptador de ledger que nomeia o que o CHECK da v12_01 recusa, e avaliação de prontidão com linhagem explícita. Sem socket, sem cliente Google, sem Supabase, sem relógio próprio."
}
```

**Arestas propostas:**

| source | target | relation |
|---|---|---|
| `google-inteligencia-pmax` | `concept:pmax_observability` | `implementa` |
| `google-inteligencia-pmax` | `channel:PERFORMANCE_MAX` | `observa` |
| `google-inteligencia-pmax` | `concept:pmax_observability` | `bloqueado_por_schema` (v12_03) |

## 13. Prova de zero mutate

1. **Trava do FORGE conferida antes da primeira chamada:** `ColetorGoogleInteligencia.__init__`
   recusa construir se `estado_escrita()["escrita_permitida"]` for verdadeiro.
2. **Guarda de `SELECT` no transporte:** `_query` levanta se a GAQL não começar com `SELECT`.
3. **`assert_read_only_gaql` na construção:** toda GAQL de `pmax.py` passa por `_select`,
   que rejeita 13 palavras-chave (`MUTATE`, `INSERT`, `UPDATE`, `DELETE`, `CREATE`,
   `DROP`, `ALTER`, `EXECUTE`, `CALL`, `VALIDATE_ONLY`, `TRUNCATE`, `MERGE`, `UPSERT`).
4. **Lista branca de superfície no dublê:** a coleta PMax só obtém `GoogleAdsService`;
   qualquer outro serviço ou tipo levanta `AssertionError`, e qualquer atributo fora de
   `search_stream` levanta `AttributeError` e fica registrado
   (`test_k_coleta_pmax_so_fala_com_googleadsservice`).
5. **Varredura de fonte e de árvore sintática:** nenhum dos 8 arquivos do pacote contém
   `.mutate_`, `mutate_operation`, `apply_recommendation`, `dismiss_recommendation`,
   `validate_only`, `.upload`, `create_` ou `FORGE_PERMITIR_ESCRITA=1`; e nenhum importa
   módulo de agenda, espera ou processo (`threading`, `sched`, `asyncio`, `time`,
   `subprocess`, …). Verificado por AST, não por grep de substring — comentário nenhum
   produz import.
6. **Nenhuma escrita no Supabase oficial:** a única chamada de escrita é a RPC
   `volc_registrar_google_inteligencia` já existente (append-only, RLS forçada), e ela
   **não foi executada** nesta lane — todos os testes usam dublê.
7. **Nenhuma migration criada.** `supabase/migrations/` não foi tocado.

## 14. Hard stops encontrados

| Hard stop | Ocorreu? | O que foi feito |
|---|---|---|
| Necessidade inevitável de migration | **sim, para 6 das 7 famílias** | Não criei. Parei a persistência dessas famílias, nomeei a recusa em cada recibo e especifiquei a `v12_03` na seção 9.1. |
| Necessidade de Google mutate | não | — |
| Necessidade de escrever no Supabase oficial | não | — |
| Conflito exigindo ownership proibido | **sim, três vezes** | (a) `volc_ads/observabilidade_pmax/queries.py` — não expandi a consulta de sinais; declarei `CAMPOS_NAO_COLETADOS`. (b) `backend/app/trafego/contrato_canais.py` — não toquei; entreguei `avaliar_prontidao_pmax` como domínio e o handoff da seção 10. (c) `volc_ads/observabilidade_pmax/coverage.py` — não reconciliei a regra dos 60 caracteres; registrei a divergência em 5.3.2. |
| Risco de expor segredo/dado de produção | não | Nenhuma leitura real; CLI imprime resumo sanitizado; varredura de credenciais no diff sem achados. |
