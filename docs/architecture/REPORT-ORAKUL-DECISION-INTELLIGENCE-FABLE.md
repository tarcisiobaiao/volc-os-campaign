# REPORT — ORAKUL / Decision Intelligence (double check Fable 5)

- **Data:** 2026-08-28 · **HEAD:** `5193575` · **Grafo:** `current: true`
  (`--check`, build no 69f5658, "insumos idênticos").
- **Natureza da missão:** investigação, validação adversarial e especificação.
  **Nenhuma** mutação Google Ads, escrita no Supabase, migration, edição de
  workflow, deploy ou push. `FORGE_PERMITIR_ESCRITA` ausente o tempo todo.
- **Método:** 12 investigadores read-only + 8 lentes adversariais de refutação +
  reprodução direta pelo autor (todo achado BLOCKER/HIGH deste relatório foi
  confirmado por leitura direta ou comando read-only reproduzido pelo autor).
- **Provas executadas:** replay sintético 8/8; testes do Lab 28/28; suíte backend
  1109 pass / **1 fail que NÃO é herdado** — ver B3: é regressão viva em
  `/api/trafego/provar`; `tsc -p tsconfig.app.json` 77 erros do baseline webgo
  (documentado: 76; o excedente é pré-existente no HEAD, mas ver M-tsc);
  `npm run build` verde.

> **Correção do próprio autor.** No meio da missão classifiquei o teste
> `test_provar_sem_copy_reprova_e_diz_por_que` como "falha herdada alheia ao
> Lab". Estava errado: a refutação me obrigou a abrir o código e o defeito é
> uma regressão viva do caminho de criação de campanha (B3). Fica registrado
> porque é exatamente o erro que esta missão veio caçar — ausência de erro
> confundida com acerto.

## 1. O que existe, de fato

### 1.1 Legado n8n (inventário 2026, snapshots em `inventario-n8n/flows/`)

| Flow | Ativo no snapshot | O que é | Muta Google Ads? |
|---|---|---|---|
| `orakul-vos-auto-adjust` | não | BEAST GOD MODE: **um único** motor Python de 1.678 linhas (não dois), cron 06h30/18h30, perfis SAFE/GROWTH/BLITZ, maturidade EXPLORATION/CALIBRATION/PRODUCTION, z-score, histerese, floors e loss caps | sim — `v21/...googleAds:mutate` budget e bid; PAUSE só manda e-mail |
| `atuacao-orakul-ai-agent-webgo` | **sim** | apesar do nome "AI Agent", cadeia 100 % determinística de 61 nós (21 Code nodes; Motor 2 Insights, Análise Lance1, motores AdSense) — **zero LLM**; grava `orientacao_*` em `daily_campaign_metrics` | não — só `searchStream`; a mutação fica no webhook abaixo |
| `atuacao-apply-bidding-webhook-v2` | **sim** | executor de mutação por webhook (`campaigns:mutate` em v21) | tenta — sem autenticação, sem limite, sem validate_only, sem aprovação; **hoje a chamada morre em 404 porque a v21 sofreu sunset em 05/08/2026** (ver B1) |
| `criacao-gads-factory-v3` | **sim** | 6 formulários públicos + LLM (Gemini/Azure) que criam budget, campanha e ad group | tenta — `:mutate` em v21 (mesma morte silenciosa) |
| `gads-campaign-search` | **sim** | busca/criação de campanha Search com LLM | tenta — `:mutate` em v21 |
| `gads-new-campaign-validation` | não | NEXUS: dois ramos assimétricos (v4.9 cron/ClickUp somente-leitura; v3.0 manual que loga `bid_actions` e chama o webhook de bidding) | indireta via webhook |
| `gads-search-terms-upgrade-kw` | não | upgrade de termos: 3 nodes de mutate (negativar em campanha, promover keyword, pausar keyword) sem persistir decisão | sim, quando ativo |
| `bola-de-cristal-preditivo` / `orakul-predictive-integrado-v1` | não | linhagem preditiva: Ridge/XGBoost re-treinados a cada execução, intervalos in-sample, boost_factor arbitrário | não |
| `orakul-02-analysis-engine` | não | "Motor 1/Motor 2" são **placeholders** ("cole aqui o código... não replico as 500 linhas"), retornos hardcoded | não |

**Sobre "os dois motores Python":** a hipótese da missão não bate com o
auto-adjust (que tem UM motor, o BEAST). Os pares reais "Motor 1 – Lance
(Quantitativo)" / "Motor 2 – Insights (Comportamental)" vivem funcionais em
`orakul-predictive-integrado-v1` (~12 k caracteres cada) e replicados no flow de
atuação ativo; em `orakul-02-analysis-engine` são só scaffold.

### 1.2 O que o VOLC já construiu por cima (o sucessor)

- **Kernel do Lab** (`volc_ads/inteligencia_decisao/`): pipeline puro
  observação→validação→features anuláveis→políticas versionadas→eventos→
  conflitos→health gate→diagnóstico→proposta T1 bloqueada; relógio explícito;
  fail-closed testado (28 contraprovas); crítica LLM atrás de `PortaCritica`
  com allowlist e rejeição por campo extra; replay dourado 8/8.
- **Ledger desenhado** (v10_01 intenção/lote/recibo/verificação/rollback;
  v10_02 regra/evidência/diagnóstico/proposta/aprovação/aplicação/
  acompanhamento/reversão/cooldown) com guardas em gatilho: aplicação exige
  aprovação da mesma proposta, diff imutável, T2 recusado por CHECK,
  idempotência por índice único parcial. **Não aplicado** (decisão pendente do
  dono).
- **Identidade v9_01** (`trafego_campanha` etc.): **aplicada e viva** (84
  campanhas), RLS forçada deny-by-default, append-only por gatilho.
- **Executor real com recibo**: o canário Search de 28/08 (Portal Mundo Mais,
  campanha 24183717006, PAUSED) passou por `validate_only` → mutate atômico →
  releitura → recibo em arquivo (`volc_ads/dados/recibos/`), sob a política
  estreita `canario.py` — mas gravou na tabela legada `campaigns` e o recibo não
  tem espelho em banco.
- **Frontend**: Lab navegável com estados explícitos e selo PROTÓTIPO
  triplicado; EscadaDeEntrega e CaixaDePropostas reaproveitadas entre Lab e
  cockpit real; PortaoDeAprovacao completo como componente **porém sem nenhum
  caller de produção** (`aoSubmeter` nunca conectado).

### 1.3 Autoridade externa (Google Ads API, doc oficial, acesso 2026-08-28)

- Versão corrente: **v25.1** (19/08/2026), major v25 (22/07/2026).
  **"v25.2" não existe** — a postura do Lab (`v25_2 = nao_afirmada`) está correta.
- `change_event`: janela 30 dias, `LIMIT ≤ 10.000` obrigatório, Editor não
  capturado; `change_status`: 90 dias, só ADDED/CHANGED/REMOVED.
- `validate_only`: suportado nas mutações (resposta vazia = OK).
- `recommendation`: ~73 tipos; Apply/Dismiss via API; auto-apply só p/ 15 tipos.
- `search_term_view` **não cobre Performance Max** — o substituto é
  **`campaign_search_term_view`** (termo + custo), não `campaign_search_term_insight`
  (categorias agregadas, sem `cost_micros`); termos de baixo volume são omitidos
  por privacidade. Vídeo é somente leitura na API.
- **A v21 — usada por todos os flows legados de mutação — sofreu sunset em
  05/08/2026** (post oficial do blog de desenvolvedores). Confirmado ao vivo em
  28/08 por sonda sem credencial: `/v21` devolve **404 HTML**, enquanto
  `/v22`–`/v25` devolvem 401 JSON. Ou seja, todo caminho de mutação legado está
  morto há 23 dias — e falha **em silêncio**, porque o 404 é HTML do front-end
  do Google, não um erro da Google Ads API que os flows saibam interpretar.

### 1.4 Banco vivo (leitura direta, 28/08)

- 86 tabelas em `public`; v9_01 aplicada; **v10_01/v10_02 ausentes**; nenhuma
  tabela/função de acurácia, previsão ou as-of em nenhuma migration ou no banco.
- Legado sem RLS: `campaigns`, `daily_campaign_metrics`, `users`, `projects`,
  `operational_costs`, `user_campaigns` com **CRUD completo (até TRUNCATE) para
  `anon` e `authenticated`** — reproduzido ao vivo pelo autor.
- `daily_campaign_metrics.campaign_id` sem FK; `campaigns.campaign_id` nullable.

## 2. Achados (após refutação adversarial)

> Severidades finais; cada linha tem evidência reproduzida. A matriz completa
> com vereditos por lente está em `ORAKUL-DECISION-INTELLIGENCE-AUDIT.json`.

### BLOCKER

| ID | Achado | Evidência |
|---|---|---|
| **B0** | **O `JWT_SECRET` do Supabase de produção é o segredo demo público** do `.env.example` do Supabase. Verificado sem expor valor: SHA-256 do segredo vivo (`/root/supabase/docker/.env`) == SHA-256 do demo público conhecido (`1453cea2dc3799e9…`). Consequência: qualquer pessoa na internet forja um JWT `service_role` válido e obtém acesso total ao banco — RLS, grants e todo o resto deixam de importar. Isto supera B1 e B2 em severidade e urgência. | comparação de hashes reproduzida pelo autor em 28/08 (nenhum segredo impresso) |
| B1 | Executor de mutação alcançável **sem autenticação**: `atuacao-apply-bidding-webhook-v2` (`active:true` no snapshot; `Webhook1` sem credencial nem verificação de origem). **Ajuste factual da refutação:** o alvo é `v21`, cuja **sunset foi 05/08/2026** (blog oficial), e a sonda ao vivo em 28/08 devolve **HTTP 404 HTML** no prefixo `/v21` (v22–v25 devolvem 401). Ou seja: o endpoint público continua chamável e continua gastando execução, mas **a mutação não acontece** — e o flow interpreta um 404 HTML como se fosse resposta da API, podendo reportar sucesso. Risco atual: endpoint anônimo + falha silenciosa; risco se alguém "consertar a versão" sem ver o resto: mutação real sem portão. | JSON do webhook; blog oficial "v21 sunset on August 5, 2026"; sonda sem credencial (404 em /v21, 401 em /v22–/v25) |
| B2 | Chave `anon` (pública no bundle) com DELETE/INSERT/UPDATE/TRUNCATE **sem RLS** em `campaigns`, `daily_campaign_metrics`, `users`, `projects`, `operational_costs`, `user_campaigns` no banco vivo — inclui data poisoning do insumo histórico de decisão. | consulta psql read-only reproduzida pelo autor em 28/08 |
| **B3** | **Caminho de criação de campanha quebrado no HEAD:** `backend/app/routers/trafego.py:1452` e `:1662` chamam `pp.Escolha(carimbo_nome=…)`, mas a `Escolha` real (`volc_ads/pautador_ponte.py:282`) **não tem esse campo** (0 ocorrências no arquivo). `/api/trafego/provar` responde **500**. O defeito passou despercebido porque `backend/tests/test_trafego_canario.py:168-171` usa um dublê `class Escolha` cujo `__init__(self, **_kwargs)` aceita qualquer coisa — a prova aceita qualquer erro. | reproduzido pelo autor: pytest + grep de assinatura |

### HIGH

| ID | Achado | Evidência |
|---|---|---|
| H1 | Payload de bidding com campo fixo: o corpo sempre escreve `maximizeConversions` ainda que a estratégia da campanha seja outra (updateMask vem do chamador; campo do body não) — mutação errada ou rejeição silenciosa. | JSON do webhook, node "Google Ads - Apply Bidding" |
| H2 | Falha de mutação sem recibo: branch de erro desconectada; `bid_actions.erro_msg` nunca preenchido; e o ramo NEXUS v3.0 grava `aplicado_com_sucesso=true` **antes** de qualquer confirmação (fire-and-forget). | connections dos JSONs; nodes de PATCH em `bid_actions` |
| H3 | Split-brain de autoridade: o único produtor ativo de `orientacao_*` escreve **no Supabase legado** `txvvzpstquqmbhljudfn.supabase.co` (condenado pelo ADR de autoridade), enquanto o produto lê o self-hosted — a inteligência ativa alimenta um banco morto. | URLs nos flows ativos; ADR-SUPABASE-AUTORIDADE-OPERACIONAL.md |
| H4 | O executor real de produção (`/provar`→`/subir`) registra a campanha criada na tabela legada `campaigns` (não em `trafego_campanha`), e o recibo vive só em arquivo local — a proteção que motivou a v9_01 não cobre o caminho que criou campanha real em 28/08. | `backend/app/routers/trafego.py:1828-1882`; recibo `20260828_123051_*.json` |
| H5 | Todo o aparato de aprovação humana (v10_02) e a UI de aprovação existem mas **nenhum dos dois está ligado**: migrations não aplicadas, sem writer Python, `aoSubmeter` sem caller — "existe aprovação" seria conclusão errada. | README migrations:510-516; rg `aoSubmeter=` em src/ |
| H6 | Identidade frouxa no legado: métricas sem FK, `campaign_id` nullable — mesma família do trigger "campaigns tem dois donos". | pg_constraint/\d+ reproduzidos |
| H7 | Duas idempotências paralelas (v10_01 `idempotency_key` × `canario.py` marca VOLC-CANARY): sem plano de convergência, o histórico pré-ledger fica invisível à defesa "um sucesso por chave" quando a v10 for aplicada. | `lote.py:216-261` × `canario.py:98-157` |
| H8 | Reativar qualquer flow preditivo/auto-adjust reintroduziria: target leakage, validação in-sample, cooldown morto (inputs `last_action`/`all_campaigns_summary` nunca populados), filtro silencioso de estratégia e API v21 possivelmente em sunset. | Code nodes lidos; `RESGATE-INTELIGENCIA-N8N-ORAKUL-PREDITIVO.md` |
| H9 | Pipelines de search terms que assumirem cobertura de PMax via `search_term_view` ficarão silenciosamente incompletos. **Correção da refutação:** o substituto certo é **`campaign_search_term_view`** (termo individual + custo), **não** `campaign_search_term_insight`, que devolve categorias agregadas e **não expõe `cost_micros`** — construir negativas de PMax sobre o `insight` seria impossível de custear e não mapeia para criterion de keyword. | doc oficial v25 `search_term_view` e comparação de campos dos dois recursos (acesso 28/08) |
| H10 | **Três** flows `active:true` chamam `:mutate` (não dois): `atuacao-apply-bidding-webhook-v2`, `criacao-gads-factory-v3` (6 formulários públicos que criam budget+campanha+ad group) e `gads-campaign-search` — todos hardcoded em **v21 morta**. Enquanto v21 responde 404 isso é falha silenciosa; qualquer "atualização de versão" isolada os transforma em caminhos de escrita reais sem portão. | enumeração dos JSONs reproduzida pelo autor |
| H11 | Gate de segredos verde com segredo presente: `scripts/verificar_segredos.py` passa enquanto `backend/n8n_kw_pautador.json` (arquivo **rastreado no git**) carrega credencial em claro; e `inventario-n8n/backups/` grava workflows **sem passar pelo sanitizador**. Isto refuta a premissa "os tokens estão fora do git": parte está fora (`inventario-n8n/` é gitignored — confirmado), parte não. | `git check-ignore` + leitura dos arquivos (valores não impressos) |
| H12 | Triggers vivos que fabricam número: `calculate_revenue_converted_by_date()` trata ausência como zero e `get_exchange_rate_for_date()` usa a taxa de hoje quando o mês não tem taxa medida; `process_google_ads_campaign` engole exceção e responde sucesso HTTP. É a mesma doutrina que o Lab combate, viva na tabela que alimentaria qualquer política futura. | funções lidas no banco vivo (read-only) |

### MEDIUM (seleção; lista completa no AUDIT.json)

- Coleções sem data no contrato do Lab (`quality`, `search_terms`, `negatives`)
  não têm checagem própria de as-of — reproduzido pelo autor: injetar uma
  observação extra de qualidade não muda o estado da leitura (segue "atual").
  Honesto no sintético, porta de vazamento quando a coleta real chegar.
- **`cost_spike_ratio` gera falso positivo sazonal — reproduzido pelo autor.**
  Série 3,5M / 3,5M / 7,0M (fim de semana voltando ao patamar de dia útil) dá
  ratio 2,0 ≥ limite 1,75, emite `cost_spike`, fecha o health gate e **bloqueia
  uma proposta legítima**. Com janela de 3 dias, a "mediana dos anteriores" é a
  mediana de dois pontos. Corrigir antes de qualquer uso real.
- Recibo do canário sem marca VOLC-CANARY visível no nome da campanha —
  a dedup por marca pode não reconhecer a campanha numa retomada (pergunta
  aberta ao dono).
- Developer token do Google Ads em claro nos JSONs locais do inventário
  (`inventario-n8n/` é gitignored — confirmado), **mas** `backend/n8n_kw_pautador.json`
  é rastreado no git e carrega credencial em claro (ver H11).
- Jargão técnico no frontend do Lab (v25/v25.1, `regra_id`, paths crus) sem
  teste de sanitização, divergindo da doutrina das outras telas de Tráfego.
- Cabeçalho de `v9_01_trafego_inventario.sql` diz "NAO APLICADO" mas está
  aplicada — leitor que confie no arquivo conclui errado.
- `change_event` não cobre 100 % (30 dias, Editor fora) — não usar como fonte
  única de auditoria de mudanças.

### REFUTADO / AJUSTADO (exemplos relevantes)

- "ORAKUL auto-adjust contém dois motores Python" — **refutado**: um motor
  (BEAST); os pares Motor 1/Motor 2 estão em outros flows (funcionais no
  preditivo-integrado e na atuação; placeholders no analysis-engine).
- "O flow de atuação usa IA generativa" — **refutado**: zero nodes LLM em toda a
  linhagem de decisão; LLM só existe em flows de criação/pauta.
- "v25.2 existe / é corrente" — **refutado** pela doc oficial (v25.1 é a última;
  o Lab já se recusava a afirmar v25.2 — postura correta).
- "O Lab está pronto para shadow" — **refutado** pelo próprio repo: estado
  `partial` correto; faltam coleta real, persistência, aprovação e recibo.

## 3. O que é redundante / aposentável

| Item | Veredito |
|---|---|
| `orakul-02-analysis-engine` | descartar (placeholders; nada a resgatar além do desenho de intenção) |
| Linhagem preditiva (bola de cristal, integrado-v1) | memória (P14-T01 já fez); não portar método |
| Webhook de bidding | aposentar; substituído pela etapa de aplicação do ledger |
| Escrita `orientacao_*` no Supabase legado | condenada; desligar após paridade com o diagnóstico canônico |
| BEAST auto-adjust | não reativar; réguas viram `RegraDeOtimizacao` versionadas com shadow (P09-T08/T09) |
| Referências open source (ARBA/Ads Monitor/IFTTA) | permanecem referências: sinais de share/QS (ARBA), ocorrência+dedup+health (Ads Monitor), gatilho→ação tipada (IFTTA); **nenhum runtime entra**; IFTTA muta via API v14 morta — perigo se instalado |

## 4. Matriz de aderência (mandato da missão × realidade)

| Requisito da missão | Estado | Nota |
|---|---|---|
| Grafo consultado antes de arquivos | ✅ | `--check current:true`; 5 `explain` executados |
| Fontes proprietárias lidas até os Code nodes | ✅ | 5 flows + 3 irmãos; motores extraídos e lidos |
| Open source como referência, não autoridade | ✅ | nada instalado/executado |
| Google Ads API pela doc oficial com URL+data | ✅ | v25.1 confirmada; lacunas de fetch registradas como ausência de prova |
| Supabase somente leitura | ✅ | psql catálogos; zero writes |
| Frontend auditado | ✅ | inclusive UI morta de aprovação |
| Auditoria adversarial independente | ✅ | 8 lentes de refutação; vereditos no AUDIT.json |
| Nenhuma mutação/migração/deploy | ✅ | contadores zerados |
| Ausência ≠ zero; fato ≠ inferência | ✅ | classificação em todos os artefatos |

## 5. Riscos se nada for feito

0. **B0 é emergência.** Com o `JWT_SECRET` demo, todo o resto da defesa é
   decorativo: um token `service_role` forjado ignora RLS, grants e views. A
   ordem correta de ação é B0 (rotacionar segredo e reemitir chaves) antes de
   B2, e antes de qualquer trabalho de decisão/autonomia.
1. B1 continua chamável enquanto o n8n vivo mantiver o webhook (o snapshot é de
   inventário; **verificar e desativar no n8n vivo é ação do dono**). Hoje ele
   falha em 404 por causa da sunset da v21 — o perigo é alguém "consertar a
   versão" sem notar que não há autenticação nem aprovação no caminho.
2. B2 permite a qualquer visitante corromper a base histórica que qualquer
   futura política aprendida usaria (data poisoning barato).
3. O produto segue com duas verdades (legado hospedado × oficial) e três
   idempotências, e cada dia de operação aumenta o custo do corte.
4. A sensação de "já temos aprovação e recibo" (UI + SQL prontos) sem nada
   ligado é o terreno clássico de promover capacidade inexistente a `done`.

## 6. Próxima fatia vertical (sem abrir trava de escrita)

**Objetivo:** shadow-read real de uma conta (Portal Mundo Mais): coletor GAQL
somente-leitura → `trafego_fotografia` (nova, proposta) → kernel → proposta
persistida `shadow=true` → placar no frontend.
**Aceite:** (a) replay as-of da fotografia reproduz o resultado; (b) zero
mutações (contadores em recibo de job); (c) paridade explicada com a orientação
legada por 7 dias; (d) curadoria/Roadmap atualizados pelo curador único.
**Bloqueado nesta fatia:** aplicar migrations sem autorização; qualquer mutate;
qualquer edição de workflow ativo; abrir `FORGE_PERMITIR_ESCRITA`.

— Fable 5, 2026-08-28.
