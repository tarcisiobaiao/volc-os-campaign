# Autoridade paralela — onde o legado n8n e o VOLC OS disputam o mesmo número

> Agente G · missão **Google Growth Engine do VOLC OS** · 26/08/2026.
> **Este é o achado mais importante do inventário do legado.**

## O que conta como autoridade paralela

Um número tem **um dono** quando existe exatamente um caminho que o escreve, e
esse caminho deixa recibo. Quando dois sistemas escrevem o mesmo campo — ou
quando um sistema escreve num banco e o outro lê de outro —, não existe erro a
consertar: existe uma **pergunta sem resposta**, e ela reaparece toda vez que
alguém tenta explicar por que um valor está como está.

Este documento lista **onze pontos** em que isso já acontece hoje, ordenados por
quanto dano um acionamento acidental causaria. Cada um traz o que fazer.

Nada aqui foi desativado, alterado ou disparado. **A recomendação padrão desta
página não é "desligue o n8n"** — é *nomear o dono antes de o VOLC OS começar a
escrever no mesmo lugar*. Desligar sem nomear o dono troca dois donos por zero.

⚠️ **Uma advertência sobre a palavra "ativo".** A curadoria já registra:
*"Ativo declarado no n8n não equivale a execução comprovada."* Onde eu digo
**ativo declarado**, li `ativo: true` no `.meta.json`. Onde digo **execução
comprovada**, há escrita medida no banco. Os dois quase nunca coincidem.

---

## Quadro geral

| # | Ponto | Escreve em | Estado | Gravidade |
|---|---|---|---|---|
| 1 | Webhook de bidding chamado do browser | **Google Ads** (`campaigns:mutate`) | **ativo declarado** | 🔴 crítica |
| 2 | Seis formulários públicos da Factory v3 | **Google Ads** (73 nós de mutate) | **ativo declarado** | 🔴 crítica |
| 3 | Criação por card do ClickUp | **Google Ads** (18 mutates) + `niche_conversion_mappings` (self-hosted) | **ativo declarado** | 🟠 alta |
| 4 | `campaigns` tem dois donos | tabela `campaigns` | **ativo dos dois lados** | 🟠 alta |
| 5 | Split-brain de banco: 271 × 30 | todo o resto | **ativo declarado** | 🟠 alta |
| 6 | Force update sem autenticação | cota da Google Ads API | **ativo declarado** | 🟠 alta |
| 7 | Orientação diária escrita pelo ORAKUL | `daily_campaign_metrics.orientacao_*` | **ativo declarado** | 🟡 média |
| 8 | Vínculo campanha → operador | `campaign_members`, `user_campaigns`, `user_projects` | **ativo declarado** | 🟡 média |
| 9 | BEAST — o único que já mutou de verdade | **Google Ads** (lance e verba) | inativo, reativável | 🟡 média |
| 10 | Robô de search terms | **Google Ads** (negativas, keywords, pausas) | inativo, reativável | 🟡 média |
| 11 | Muitos MCCs, nenhum declarado como o da casa | contas de mídia | — | 🟡 média |

---

## 1 · 🔴 O webhook de bidding: uma escrita não autenticada na conta de mídia, chamada do browser

**O que é.** `atuacao-apply-bidding-webhook-v2` (10 nós) — **ativo declarado**,
gatilho `webhook` POST em `fluxos.agenciavolc.com.br/webhook/{UUID}`, com
`options: {}`: **sem autenticação, sem origem permitida, sem rate limit**. Ele
recebe `{bid_action_id, campaign_id, valor_aplicado}` e faz
`POST googleads.googleapis.com/v21/customers/{id}/campaigns:mutate`.

> O valor do UUID **não é transcrito aqui**. Ele funciona como credencial de
> portador: quem o tem, escreve na conta de mídia. Ele está no JSON do flow
> (`inventario-n8n/flows/atuacao-apply-bidding-webhook-v2.json`), aparece 3 vezes
> em `gads-new-campaign-validation.json` (constante `CONFIG.WEBHOOK_URL` dos nós
> `Code` e `Code1`, e na URL do nó HTTP) e — o que importa — está **no código do
> produto**.

**Por que é o pior ponto da lista.** A URL está **hardcoded no bundle do front**:
`src/components/campaign/BiddingActionBox.tsx:123`, no branch `feat/hub-trafego`,
verificado hoje. Qualquer visitante do dashboard a extrai do JavaScript. O único
gate é `campaign_id` existir na tabela `campaigns` — lida com a credencial do
n8n, **não com a do usuário**. E não há limite de valor: o front valida `> 0` no
cliente, o webhook aceita `0` e aceita qualquer magnitude. Um `POST` com
`valor_aplicado: 100000` fixa um tCPA de R$ 100 mil e solta o algoritmo de lance;
com `0.0001`, mata a entrega.

**Agravantes medidos.**
- **O payload construído é jogado fora.** `Build Mutate Payload` resolve
  corretamente as três estratégias, e o nó `Google Ads - Apply Bidding` **ignora
  o resultado**: usa um `body` raw fixo em `maximizeConversions` e só pesca o
  `updateMask` do payload. Consequência: campanha `TARGET_CPA` recebe corpo
  `maximizeConversions` com máscara `target_cpa.target_cpa_micros` — a máscara
  aponta para campo ausente no corpo, o que na semântica de field mask do Google
  Ads **limpa o tCPA**. `MAXIMIZE_CONVERSION_VALUE` tem o tROAS limpo e o valor
  multiplicado por 1.000.000 no campo errado. **Só `MAXIMIZE_CONVERSIONS` está
  correto** — e as 3 campanhas medidas são todas dessa estratégia, o que é
  provavelmente o motivo de o defeito nunca ter sido notado.
- **Falha não é registrada.** A saída *false* do nó de verificação não está ligada
  a nada, e a saída de erro do `Apply Bidding` (`onError: continueErrorOutput`)
  também não. Qualquer falha deixa a linha de `bid_actions` com
  `aplicado_com_sucesso = NULL` para sempre. A coluna `erro_msg` existe e nunca
  recebe erro real.
- **O front sempre vê sucesso.** Sem `responseMode`, o n8n responde no instante em
  que recebe. `webhookResponse.ok` é `true` mesmo que os 8 nós seguintes explodam,
  e o toast diz *"Bidding aplicado com sucesso!"*.
- **`bid_actions` tem 0 linhas** no self-hosted, e **nada em `src/`, `server/` ou
  `api/` lê essa tabela** — só escreve. Não há histórico de atuação visível.

**O que fazer.**
1. **Nomear o dono agora, antes de qualquer código novo de lance.** Enquanto este
   webhook existir, o VOLC OS não pode assumir que é o único a mover `target_cpa`.
2. Substituir o caminho por: front → **backend autenticado** (sessão do usuário,
   pelo portão `public.volc_role_of()` já publicado em v8_01) → fila → worker que
   fala com o Google Ads. Com **validação de faixa** (por exemplo, entre 0,3× e 2×
   do valor de referência da recomendação do dia), **idempotência por
   `action_id`** e **registro obrigatório de sucesso E de falha**.
3. Enquanto (2) não existir: tratar o UUID como credencial vazada — **rotacionar
   o path do webhook** e tirar a URL do bundle do front.
4. Não desligar o webhook sem antes desligar o botão que o chama: hoje o botão
   "Aplicar Bidding" no dashboard não tem outro caminho.

---

## 2 · 🔴 Seis formulários públicos criam campanhas na conta de mídia

**O que é.** `criacao-gads-factory-v3` — **ativo declarado**, com **6
`formTrigger`** (webhookIds distintos), 1 `manualTrigger` e 1 `scheduleTrigger`
desconectado. São **seis esteiras paralelas independentes** de 26–27 nós cada,
que nunca se falam, somando **73 nós de mutate** no Google Ads
(`campaignBudgets`, `campaigns`, `campaignCriteria`, `adGroups`,
`adGroupCriteria`, `adGroupAds`, `assets`, `campaignAssets`), na conta
`3849678045` sob o MCC `6016739364`.

**Por que é grave.** Seis formulários **públicos**, sem autenticação além da URL,
apontando para a mesma conta de mídia. Qualquer pessoa com uma das seis URLs cria
campanha, budget, ad group, keywords e anúncios. A mitigação real é uma só, e é
boa: **tudo nasce `PAUSED`** — campanha, ad group e RSA.

**Agravantes medidos.** As seis cópias **já divergiram**: 5 variantes de
`✅ Valida Conteúdo` (90, 124, 124, 125, 238 e 239 linhas), 3 de
`🎨 Prepara Assets`, 2 de `🎯 Filtra Keywords`; os **6 prompts do LLM são todos
diferentes** entre si (4.124 a 6.068 caracteres) e os **modelos divergem**
(`gemini-2.5-pro` em duas cadeias, `gemini-3-pro-preview` em quatro). Dois
formulários publicados produzem criativos por caminhos de código diferentes.
Além disso: `⚙️ Config Global5` tem `nicho` **hardcoded como `"Meu INSS"`**,
sobra de teste publicada num formulário ativo; e **4 das 6 esteiras terminam no
vazio** — o operador que submeteu não recebe o id da campanha.

**O que fazer.**
1. **Inventariar as seis URLs de formulário** e decidir, uma a uma, se ainda têm
   uso. Este é o tipo de superfície que a `wave:P0-S` da curadoria já mandou
   conter ("as sete superfícies públicas do n8n").
2. O VOLC OS **já é o caminho canônico de criação Search** (`cap_search_birth`
   está `implemented`: cockpit `/trafego/nova/:opportunityId` + engine v25 + trava
   de escrita de dois fatores em `volc_ads/gads/modo.py`). O conflito aqui não é
   de lógica — é de **porta de entrada**.
3. Manter `PAUSED` como invariante nos dois caminhos até que o dono seja único.

---

## 3 · 🟠 Arrastar um card no ClickUp sobe uma campanha

**O que é.** `gads-campaign-search` — **ativo declarado**, gatilho `clickUpTrigger`
(team `9007096682`), com um filtro que só deixa passar quando
`history_items[0].after.status == "google ads"`. **É a única porta**: sem cron,
sem webhook. 18 mutates no Google Ads na conta `5478096539`, mais duas escritas em
`niche_conversion_mappings` — e este é **o único flow de mídia que escreve no
Supabase self-hosted**, o banco que o produto lê.

**Por que está na lista mesmo estando quebrado.** Ele está quebrado no **segundo
passo**: dois nós chamam `$('⚙️ Config Global')` e o nó existente chama-se
`⚙️ Config Global5`. Corroborado por medição: `niche_conversion_mappings` = **0
linhas** e nenhuma campanha nova em `campaigns` desde **2026-02-13**. Mas o
gatilho continua armado, e **a correção é de duas linhas** — alguém "consertando"
sem saber do VOLC OS religa uma segunda porta de criação de campanha.

**Agravante estrutural.** Ele também aponta para uma **conta diferente** da
Factory v3 (`5478096539` × `3849678045`), no mesmo MCC.

**O que fazer.**
1. Decidir se o ClickUp continua sendo uma porta de criação. Se sim, ele deve
   chamar o **backend canônico**, não a API do Google Ads (é exatamente o padrão
   da **ADR-05**: *"n8n como scheduler chamando contrato interno"*).
2. Se não, o filtro de status é o ponto de corte mais barato — mas registre a
   decisão, porque o card parado em "google ads" é hoje o único sinal de que
   alguém pediu uma campanha.
3. Preservar duas peças de conhecimento antes de qualquer corte: a arquitetura de
   **dois ad groups** (`[PHRASE]` + `[BROAD-MINING]` a 70% do lance) e o fato de
   domínio de que este nicho encosta na política
   `GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES` — as duas estão nas fichas B02 e
   B03.

---

## 4 · 🟠 `campaigns` tem dois donos — e um trigger que apaga a procedência

**O que é.** A tabela `public.campaigns` é escrita por **dois caminhos
independentes**:

- **legado**: a RPC `process_google_ads_campaign`, chamada por
  `custo-gads-report` (5 nós), `custo-gads-report-d1` (5 nós) e
  `gads-new-campaign-validation`. Ela **deriva o projeto do NOME da campanha e,
  se não achar, cria o projeto** — `projects` id 1 (`portalmundomais.com`,
  `auto_created = t`, criado em 2026-02-13 09:12:41) é a prova de que o ramo de
  auto-criação já disparou em produção;
- **VOLC OS**: `_registrar_campanha`, em `backend/app/routers/trafego.py:1507`,
  que grava `google_ads_status: "PAUSED"` e `status_source: "volc_os"`.

**Por que é grave — e é pior do que "dois escritores".** Medido em 24/08/2026:
o trigger `sync_status_from_google_ads` é `BEFORE INSERT/UPDATE` e executa
`NEW.status_source = 'auto'` **sempre que `google_ads_status` não é nulo**. Como
a porta do VOLC OS **sempre** envia `google_ads_status`, a linha
`"status_source": "volc_os"` que ela escreve é **inalcançável por construção**.
Ou seja: os dois donos existem, e **o banco apaga a evidência de qual deles
escreveu**.

Um segundo defeito medido no mesmo caminho: o INSERT filtra com `if v is not
None`, então **string vazia atravessa** — foi assim que `customer_id` ficou vazio
nas linhas de `campaigns`, apesar de o recibo do lançamento
(`volc_ads/dados/recibos/`) trazer o id da conta. E do lado do legado, um dos 5
ramos do D-1 **não envia `p_customer_id`** — medido: `customer_id` NULL em 3/3
linhas do self-hosted, o que faria o `Apply Bidding` morrer em
`Merge Campaign Data1`.

**Forense disponível, e sua limitação.** `pg_stat_statements` **está instalado** e
responde "quem já executou esta forma de query", com role e contagem — **mas sem
timestamp**. `log_statement = 'ddl'`, `log_min_duration_statement = -1` e
`logging_collector = off`: **DML não é logado**, e os logs de contêiner rotacionam
em poucos dias. Para investigar escrita passada nesta tabela,
`pg_stat_statements` é praticamente a única fonte.

**O que fazer.**
1. **Um campo de procedência que o trigger não toque.** Enquanto `status_source`
   for sobrescrito, nenhuma auditoria de "quem escreveu" é possível.
2. Corrigir o filtro de `None` para rejeitar também string vazia — um id vazio é
   ausência, não valor (a mesma doutrina de
   `backend/app/trafego/inventario.py`: *"Ausência é `None`, nunca zero"*).
3. Decidir a porta única de entrada de campanha. O conceito da RPC é bom (uma
   porta que resolve/cria projeto e mapeia enums); **a implementação não**: a
   derivação por `SPLIT_PART(name,'/',3)` já não funciona no formato de nome que a
   própria fábrica gera (o 3º segmento é `" https:"`), quem trabalha é o regex de
   fallback, e o `EXCEPTION WHEN OTHERS THEN RETURN json` **transforma erro em
   200 OK**. No VOLC OS, a campanha declara `funnel_run_id`/`project_id` na
   criação (a coluna já existe), e a extração por nome vira só fallback de
   emergência, com log e alerta.

---

## 5 · 🟠 Split-brain de banco — o legado escreve num Supabase, o produto lê de outro

**O que é.** Os flows de custo, decisão e atuação escrevem em
`txvvzpstquqmbhljudfn.supabase.co` (**hospedado**, atrás de Cloudflare). O VOLC
OS lê `database.agenciavolc.com.br` (**self-hosted**, Hetzner). **Não são o mesmo
banco, e não há replicação conhecida.** No inventário inteiro: **271 endpoints
apontam para o hospedado, 30 para o self-hosted**. Dos 17 flows de mídia, **só um**
(`gads-campaign-search`) aponta para o self-hosted.

**O tamanho do estrago, medido no self-hosted em 19/08/2026:**

| medida | valor |
|---|---|
| `system_settings.google_ads_last_update` | **11/03/2026** — parado há 161 dias |
| `daily_campaign_metrics` | 92 linhas, `max(date) = 2026-06-25`, **0 nos últimos 30 dias** |
| `campaigns` | 3 linhas, **0 com `status='Active'`**, `customer_id` NULL em 3/3 |
| `bid_actions` | **0 linhas** |
| `display_ads_placements` | **0 linhas** |
| `gam_metrics` | **0 linhas** |
| `campaign_members`, `user_emails` | **não existem** (`to_regclass` = null) |
| `exchange_rate_history` | 4 linhas, última **18/02/2026**, taxa 5,25 — **congelada** |

**Por que isso é autoridade paralela e não só desatualização.** O
`atuacao-orakul-ai-agent-webgo` grava `orientacao_json` versão **2.1**; as 12
linhas que existem no self-hosted são versão **1.2/1.3**, e o front exige
`orientacao_json.decisao` (v2.1). Nessas linhas o `BiddingActionBox` **nunca
renderiza**. Ou seja: o dashboard mostra ao operador dados que o motor ativo nunca
escreveu ali — e o motor ativo escreve num lugar que o dashboard não lê.

**Consequência que atinge diretamente esta missão.** `exchange_rate_history`
alimenta `get_exchange_rate_for_date()`, que alimenta **6 triggers** de
`revenue_converted` — e é sobre essa coluna que se calculam **RPC, spread e
ROAS**, isto é, o insumo de toda regra de lance deste inventário. Enquanto o
câmbio estiver congelado, a política `lance_ancorado_no_rpc` fica **bloqueada por
insumo**, e isso está registrado no JSON canônico.

**O que fazer.** É a **prioridade 2 da curadoria** ("Unificar a verdade
operacional") e **não é tarefa de engenharia**: é uma decisão que precisa de
alguém com credencial dos dois lados. A ressalva que evita perder tempo, e que o
inventário já registra: **repontar sozinho não resolve** — há defeitos de conteúdo
que sobrevivem ao repontamento e produzem execução verde com tabela vazia.

---

## 6 · 🟠 Force update: um webhook público que queima a cota da API

**O que é.** `custo-force-update-gads` — **ativo declarado**, 2 nós, zero linhas
de código: `Webhook → Execute Workflow(GADS REPORT)`. Gatilho `webhook` com
`options: {}` — **sem autenticação declarada e sem validação de corpo**. Existe o
gêmeo `receita-force-update-gam`, fora do recorte de mídia.

**Por que é grave.** Uma requisição HTTP dispara **99 nós** e centenas de chamadas
à Google Ads API em cinco contas. Quem souber a URL derruba a cota diária. Não é
mutação, mas é **negação de serviço da medição** — e sem medição não há decisão de
lance.

**Limitações que também importam.** Só força o **D0**: se o D-1 falhar às 06:00,
não há como reprocessar o dia anterior sem abrir o n8n. E não aceita parâmetros —
**reprocessar uma data antiga é impossível por este caminho**.

**O que fazer.** Substituir por endpoint **autenticado** que aceita
`{data, conta}` e **enfileira**, em vez de disparar sincronamente. É a mesma
correção da ficha F04, e ela resolve os três problemas de uma vez.

---

## 7 · 🟡 A orientação diária: o motor ativo escreve opinião dentro da tabela de fato

**O que é.** `atuacao-orakul-ai-agent-webgo` — **ativo declarado**, cron
`30 6 * * *`, 61 nós e 4.812 linhas. Ele **não muta o Google Ads**: faz upsert em
`daily_campaign_metrics?on_conflict=campaign_id,date` gravando
`orientacao_texto`, `orientacao_resumo`, `orientacao_json`,
`orientacao_gerado_em` — no **hospedado**.

**Por que é conflito.** Três razões.
1. **Mistura fato com opinião na mesma linha.** `daily_campaign_metrics` guarda
   métrica medida (camadas de custo/receita), orientação (opinião do motor) e
   otimização (registro de atuação). O upsert por `(campaign_id, date)` **obriga o
   motor a criar linhas-fantasma de métrica**: medido, **3 linhas com
   `campaign_id` vazio** poluindo a própria tabela que o motor lê na execução
   seguinte. É a **prioridade 9 da curadoria**.
2. **`orientacao_gerado_em` tem `DEFAULT now()`.** Resultado: **92 linhas
   carimbadas contra 12 com decisão real** — qualquer medição ingênua de "quantas
   vezes o motor rodou" produz um falso positivo de 767%. Uma coluna de auditoria
   que se autopreenche é pior que não existir.
3. **A linha do dia nasce só com orientação.** O upsert grava `date = hoje` numa
   tabela cuja granularidade é métrica diária; a linha nasce com todas as métricas
   NULL. Se a ingestão de D-1 falhar, no dia seguinte o `d0` do motor é uma linha
   de zeros — `cvr_d0 = 0` ⇒ multiplicador `×0.90` **silencioso**. **O sistema
   corta 10% do lance por falha de ETL, sem nenhum alerta dizendo isso.**

**O que fazer.** Três tabelas, como a curadoria pede: `campaign_daily_metrics`
(fato), `campaign_recommendations` (uma linha por recomendação, com `engine`,
`version`, `created_at`) e `campaign_actions` (uma por atuação, com `action_id` e
FK). E colunas de "quando o motor decidiu" / "quando o atuador executou" escritas
**explicitamente**, nunca por default de schema.

---

## 8 · 🟡 Dois sistemas decidem quem enxerga qual campanha

**O que é.** `front-vincular-campanha-operador` — **ativo declarado**, a cada 6
horas, lê `change_event` do Google Ads em 4 MCCs para descobrir **qual pessoa
criou qual campanha**, e escreve `campaign_members`, `user_campaigns` e
`user_projects` — no **hospedado**.

**Por que é conflito.** O VOLC OS tem seu próprio modelo de autorização:
`public.volc_role_of()`, publicado por **v8_01 em 24/08/2026 14:48-03**, é a
autoridade do portão das 66 rotas do FastAPI. São **dois sistemas concedendo
visibilidade sobre a mesma campanha**, em bancos diferentes — e o do legado é
inofensivo hoje só por acidente: `campaign_members` e `user_emails` **não existem**
no self-hosted.

**E há algo aqui que merece sobreviver.** Este é **o código mais bem escrito de
todo o legado**, e três regras dele são conhecimento comprado com dado real:
`CLIENTES_HUMANOS = {'GOOGLE_ADS_WEB_CLIENT'}` (senão a campanha é atribuída ao
robô que a tocou); a distinção rascunho × campanha publicada, feita em JS porque
o status vem dentro de `new_resource` e *"é mensagem e não entra no WHERE"*; e o
teto de 10.000 eventos transformado em **erro explícito** em vez de truncamento
silencioso. Ver ficha F05.

**O que fazer.** Migrar as três regras para um job do backend, escrevendo no banco
do produto e no modelo de papéis do Hub. **Não desligar antes de migrar**: hoje é
a única fonte automática de autoria de campanha.

---

## 9 · 🟡 O BEAST: inativo, mas é o único que já moveu dinheiro de verdade

**O que é.** `orakul-vos-auto-adjust` — **inativo** (`ativo: false`), cron
`30 6,18 * * *`. Dois nós de mutate: `💰 Adjust Bid (GAds)` e
`📊 Adjust Budget (GAds)`, com `customer_id` **hardcoded** no `🔀 SABM Splitter`.

**Por que continua na lista.** É a **única geração da linhagem ORAKUL com
execução comprovada**: 10 mutações confirmadas entre `2026-02-16 18:30:04-03` e
`2026-02-19 18:30:10-03`. As três campanhas afetadas estão hoje `Paused` e seus
`target_value` (`0.115118`, `0.099757`, `0.0728`) **batem com os lances propostos
pelo motor naqueles dias**. Reativar é um clique.

**E o log de auditoria mente.** Medido: em `2026-02-19` a campanha `23518661646`
gerou **duas** ações de aumento de verba na mesma execução — `+30% → R$ 21,97` e
`+20% → R$ 20,28` —, ambas marcadas `executavel: true`, e o log registrou **duas
vezes o mesmo objeto** (R$ 20,28), enquanto `campaigns.budget_amount` ficou em
**R$ 21,97**. **O valor que efetivamente vingou não está no log.** A causa é
estrutural: o flow recupera contexto pós-mutação varrendo `$('nó').all()` e
casando por `tipo`, ficando sempre com o último.

**O que fazer.**
1. **Não reativar.** A curadoria já colocou isto na prioridade 14 ("Reabrir
   otimização avançada e preditivo — DEPOIS DO CHÃO"), exigindo replay e shadow
   antes de qualquer atuação automática.
2. **Extrair antes de aposentar.** Cinco das seis melhores regras deste inventário
   estão dentro deste arquivo — modo de validação, piso de verba e teto de perda,
   histerese, evento externo e a âncora de RPC. Elas já estão nas fichas e no JSON
   canônico; o arquivo pode morrer depois disso.
3. Registrar a pergunta que continua sem resposta: **por que a linha foi desligada
   em 19/02/2026?** As execuções foram bem-sucedidas e o workflow foi editado às
   23:47 do mesmo dia. Sem o histórico de execuções do n8n não dá para saber se
   houve incidente, resultado financeiro ruim, ou só uma pausa operacional.

---

## 10 · 🟡 O robô de search terms: inativo, e era o único que escrevia sozinho

**O que é.** `gads-search-terms-upgrade-kw` — **inativo** desde
`2026-02-19T23:47:16Z` (o mesmo dia do BEAST), cron `0 6 * * *`. Três mutates:
negativas em nível de campanha (`campaignCriteria`), criação de keywords PHRASE e
pausa de keywords (`adGroupCriteria`). Aponta para um MCC **diferente** do
ORAKUL (`4904074301` × `8696453882`).

**Por que continua na lista.** Era **o único robô que escrevia sozinho no Google
Ads sem humano no meio**. E a saída dele é **um e-mail**: não há registro
persistido de nada que ele negativou ou pausou. Reativar significa mutações não
auditáveis numa conta de mídia.

**Defeitos que tornam a reativação perigosa.** Nenhum dos três mutates envia
`partialFailure: true` — a API é atômica por padrão, então **uma** operação
inválida derruba o lote inteiro; o dedupe compara com acento e a escrita grava sem
acento, então o flow tenta criar a mesma duplicata todo dia e mata o lote de
promoções; e `📤 Mutate Depromote KWs` é folha órfã lida dentro de um `catch`
vazio, de modo que o relatório pode dizer `depromoteApplied: 0` **tendo pausado
keywords**.

**O que fazer.** Não reativar. A máquina de estados (ficha E01) vale e migra para
um job sobre tabela materializada; as réguas numéricas **não migram como estão**
(fichas E02, E03, E04). O stemming é descartado (ficha E06).

---

## 11 · 🟡 Muitos MCCs e contas, e nenhuma declaração de qual é a da casa

**O que foi medido.** Os 17 flows de mídia usam, entre MCCs e contas:
`6016739364` (criação), `8696453882` (ORAKUL e report), `6650747513`,
`5478096539` (campaign-search), `3849678045` (Factory v3), `4904074301`
(search terms), `1081900905`, `6084143056`, `6198200109` (ramos de report),
`2932743754` (KW mining), `8937268448` ("conta_erica", ramo órfão em API v21),
`5515684307`. O `RUN-MANIFEST.json` desta missão declara
`mcc_da_casa: 6016739364` e `conta_credito_up: 8017851692` — e **`8017851692`
não aparece em nenhum dos 17 flows**.

**Por que importa.** Cada flow tem sua própria noção de qual conta é a verdade, em
nós `Set` copiados. Pior: os campos `LOGIN ACCOUNT ID`, `MANAGER ID` e `CLIENT ID`
desses nós **nunca são lidos** — todos os nós HTTP montam
`"login-customer-id": {{ ...['CUSTOMER ID'] }}`. A divergência declarada em
`Edit Fields2` (`8696453882` vs `6650747513`) é **decoração**. Quem ler o flow
para descobrir a topologia de contas lê uma ficção.

**O que fazer.** No backend, **a lista de MCCs e contas é configuração (tabela ou
env), não topologia de workflow**. E a conta da missão (`8017851692`) precisa
entrar nessa configuração explicitamente — hoje ela existe só no manifesto e nos
recibos de lançamento.

---

## Segredos: o que encontrei ao reconferir hoje

Varri os 17 flows de mídia por padrões de credencial em 26/08/2026. **Não
transcrevo nenhum valor.**

- **Os alertas de credencial em claro dos documentos de 19/08 não se confirmam
  mais no estado atual dos arquivos.** `inventario-n8n/04-DECISAO.md` e
  `07-OTIMIZACAO.md` avisam que o `developer-token` estaria em claro em
  `orakul-vos-auto-adjust.json` (nós `💰 Adjust Bid` e `📊 Adjust Budget`,
  dentro de `jsonHeaders`) e em `atuacao-apply-bidding-webhook-v2.json` (nó
  `Parse Webhook Data`, dentro do `jsCode`). **Nas quatro ocorrências, o arquivo
  no disco hoje traz `«CENSURADO»`.** O `CLIENT ID` apontado em
  `atuacao-orakul-ai-agent-webgo.json` (nó `Edit Fields2`) está **vazio**, não em
  claro. Ou o sanitizador foi corrigido, ou o inventário foi rebaixado depois dos
  alertas — não determinei qual, e **isso não é motivo para não rotacionar**: se o
  token esteve em claro num arquivo em disco, ele deve ser considerado exposto.
- **O que continua exposto e é acionável:** o **path UUID do webhook de bidding**,
  presente 3 vezes em `gads-new-campaign-validation.json` e — o que importa — em
  `src/components/campaign/BiddingActionBox.tsx:123`, **no código do produto**.
  Ele é credencial de portador para uma escrita na conta de mídia. Ver ponto 1.
- Fora do recorte de mídia, o inventário registra a chave do `exchangerate-api`
  **no path da URL**, em 7 arquivos da camada de receita. Não verifiquei.

E um lembrete que a curadoria já carrega e que atravessa esta página:
`risk:superficie_privilegiada` — os proxies genéricos com `service_role` foram
**removidos do repositório** em 24/08/2026 (commit `4a08ef2`), mas o deployment de
produção continua sendo o de **16/02/2026**. *"O que protege hoje é ninguém ter
descoberto, não o código novo."*

---

## O que eu recomendo, em uma frase por ponto

| # | Recomendação |
|---|---|
| 1 | **Nomear o dono do lance antes de escrever a primeira linha de motor.** Rotacionar o path do webhook e tirá-lo do bundle do front. |
| 2 | Inventariar as 6 URLs de formulário e decidir uma a uma; manter `PAUSED` como invariante nos dois caminhos. |
| 3 | Se o ClickUp continuar sendo porta, que ele chame o backend (ADR-05) — nunca a API do Google Ads. |
| 4 | Criar um campo de procedência que o trigger não toque, e rejeitar string vazia como se fosse `None`. |
| 5 | Decidir qual Supabase é a verdade — é decisão de dono, não tarefa de engenharia; e repontar sozinho não resolve. |
| 6 | Trocar o webhook público por endpoint autenticado que aceita `{data, conta}` e enfileira. |
| 7 | Separar fato, recomendação e ação em três tabelas; carimbo de decisão nunca por `DEFAULT now()`. |
| 8 | Migrar as três regras de autoria antes de desligar — hoje é a única fonte automática de quem criou o quê. |
| 9 | Não reativar o BEAST; extrair as cinco regras (já extraídas) e então aposentar. |
| 10 | Não reativar o robô de search terms; migrar a máquina de estados, descartar as réguas e o stemming. |
| 11 | Lista de MCCs e contas vira configuração; a conta desta missão precisa entrar nela. |
