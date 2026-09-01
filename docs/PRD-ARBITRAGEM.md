# PRD — VOLC O.S. Arbitragem: o que construir, em que ordem

> ⚠️ **PREMISSA REFUTADA em 01/09/2026.** `campaign.selective_optimization` é campo de campanha de **APP**, não de Search — confirmado literalmente na doc oficial (callout "Important" em `conversions/goals/overview`), ver `docs/architecture/evidence/GOOGLE-ADS-DOCS-2026-09-01.md`. Para Search, a campanha **herda** os `CustomerConversionGoal` da conta, e sobrescrever exige `CampaignConversionGoal` — que a API só **atualiza**, nunca cria nem remove. O texto abaixo é histórico e não deve ser implementado como está.


> Escrito em 19/08/2026. Par do [SPEC-ARBITRAGEM.md](SPEC-ARBITRAGEM.md) — os
> porquês de arquitetura moram lá; aqui mora a ordem, o critério de aceite e
> o risco. Premissas herdadas das decisões do dono: Supabase hospedado
> abandonado (sem backfill, N=0), JoinAds em USD/revshare 10%, pré-autorização
> só na direção REDUZ, BEAST desligado por suspensão de conta (não por
> defeito).
>
> **O enquadramento que muda o tom:** o spread medido de fevereiro foi −5%,
> com uma campanha em ROAS 1,17 — *sem sinal de conversão, com câmbio
> congelado e sem o segundo fator do RPC medido*. Isto não é resgate de um
> sistema falido; é fechar três elos de um sistema que quase fecha a conta.
> E a única entrega inegociável, acima de qualquer feature: **o sistema
> precisa perceber sozinho que parou.**

## Como ler as fases

Ordenadas por **valor destravado ÷ esforço**. Cada fase declara: objetivo,
escopo, critério de aceite **verificável** (comando ou consulta), o que fica
explicitamente de fora, o que destrava, de que depende, o risco de fazer
errado, e reversibilidade. Esforço em T-shirt (S < 1 dia · M = dias ·
L = 1–2 semanas de uma pessoa sênior).

Regra transversal, válida em toda fase: **nenhuma escrita no Google Ads sem
autorização humana** — e são exatamente três as classes de escrita, cada uma
com sua autorização: criação/aumento (humano, na hora, sempre); defesa
(direção REDUZ, pré-autorizável, só a partir do F6); upload de conversões
(autorização permanente própria, criada pelo dono no F5, revogável). Não
existe quarta classe. `validate_only` roda à vontade. O portão de MCC nunca
abre para conta de terceiro.

---

## F0 — Estancar: apagar as luzes do prédio velho *(horas · reversível)*

**Objetivo.** Parar de queimar quota, fechar as portas abertas e remover o
ruído que contamina qualquer diagnóstico daqui em diante.

**Escopo.**
1. Desligar no n8n os **15 flows ativos** que apontam para o Supabase
   hospedado (a URL aparece em 18 arquivos do inventário; 3 já estão
   inativos — lista no `00-MAPA.md` §duplicatas). Nas 06:00, os alvos são
   **11 dos 13** que disparam: os 5 pares D0/D-1 de custo/receita e o
   `front-webgo-new-dashboards`. **Os outros 2 das 06:00 são os JoinAds e
   FICAM.** Checklist explícito do que FICA ativo: `receita-joinads-d1`,
   `receita-joinads-intraday`, `pauta-kw-minning-pautador-pro` — os três que
   apontam para o banco certo. (`gads-campaign-search` aponta certo mas está
   quebrado desde 24/02 e sua porta morre por decisão — desligar também.)
2. Desativar os **6 formulários públicos** da Factory v3 (endpoints abertos
   contra conta real de anúncio).
3. Desativar o webhook `1cb2069d…` (Apply Bidding) no n8n e **remover a URL do
   bundle do front** — o botão do `BiddingActionBox` fica desabilitado com a
   mensagem "atuação migrando para a porta nova" até o F3.
4. Rotacionar o developer token do Google Ads e a chave da exchangerate-api —
   a primeira exportação do inventário saiu com os dois **em claro**; a cópia
   atual já está re-sanitizada, mas os valores circularam. Garantir no
   `baixar-inventario-n8n.py` a varredura permanente de
   `jsonHeaders`/`jsonBody`/`jsCode` e de segredos em path de URL.
5. Caçar o chamador fantasma de `compute_funnel_daily` (não está em
   `cron.job`, nos 30 flows nem no repo — começar pelos 37 flows ativos fora
   do núcleo). Achado ou não, **o fallback é adotá-la como job explícito do
   pg_cron** (23:00, ao lado de `compute_page_daily`) — elimina o fantasma de
   vez.

**Aceite (verificável).**
- API do n8n: nenhum workflow **ativo** do núcleo contém
  `txvvzpstquqmbhljudfn` (script de conferência sobre o inventário re-baixado).
- `curl -X POST https://fluxos.agenciavolc.com.br/webhook/1cb2069d-… ` →
  404/erro, não 200.
- `grep -r "1cb2069d" src/` → 0 ocorrências; build novo publicado.
- `curl` nos 6 webhooks de formulário da Factory → não respondem formulário.
- Tokens antigos revogados no console; backend local testa os novos.
- JoinAds continua entregando: `select max(date) from daily_project_metrics`
  avança no dia seguinte.
- Chamador de `compute_funnel_daily` documentado em `docs/`, **ou** job
  pg_cron próprio criado (e o fantasma, se existir, desligado).

**Fora.** Deletar workflows (só desativar — são documentação arqueológica);
mexer em qualquer flow dos outros clientes da agência.

**Destrava.** Diagnóstico limpo para todas as fases; remove o maior risco de
segurança ativo. **Depende.** De nada. **Risco de fazer errado.** Desligar um
dos 3 flows vivos por engano — por isso o checklist do que fica é parte do
escopo, não nota de rodapé. **Reversível.** Totalmente (reativar é um clique;
tokens novos já testados antes de revogar os velhos).

---

## F1 — O sistema percebe que parou: recibos, relógio e câmbio *(M · reversível)*

**Objetivo.** Construir o alicerce do P1 antes de qualquer funcionalidade:
recibos no plano de dados, watchdog no componente que nunca falhou, e o
primeiro job do padrão novo (câmbio) como prova do desenho.

**Escopo.**
1. Migração: `fontes_monitoradas`, `fontes_receita`, `recibos_ingestao`,
   `alertas`, `heartbeats`, `contas_monetizacao` (+`_eventos`),
   `projeto_contas` — SPEC §1.6/§4.2. Popular `fontes_monitoradas` (joinads
   com cadência **intraday**, 4×/dia; cambio 1×/dia; kw_mining sob demanda),
   `fontes_receita` (joinads: USD, bruto, grão projeto+campanha, conta da
   Join), `contas_monetizacao` (Join/parceiro ATIVA; AdSense da casa SUSPENSA
   com o evento de fevereiro registrado — o trauma vira dado) e
   `projeto_contas` (creditoup → Join, papel `primaria`).
2. Backend deployado no Hetzner (Docker ao lado do compose do Supabase), com
   scheduler interno e **heartbeat** gravado em tabela a cada tick.
3. Job de câmbio: 1×/dia → `exchange_rate_history` + recibo. A partir daqui
   `get_exchange_rate_for_date()` volta a funcionar como projetada.
4. Watchdog em pg_cron (15 min): função SQL compara recibos/heartbeat contra
   `cadencia_esperada` e materializa `alertas` com dedupe; alerta CRITICO
   dispara e-mail via backend — e se o backend estiver morto, o próprio
   atraso do heartbeat é o alerta (o vigia não mora no vigiado).
5. **Dead-man's switch externo** (SPEC §8.1): o backend pinga um monitor fora
   do box a cada 5 min, e só pinga se o heartbeat está fresco e não há
   `CRITICO` aberto; ping ausente → notificação externa. O box inteiro pode
   morrer — o aviso chega mesmo assim.
6. Retrofit nos 3 flows n8n sobreviventes: um nó de recibo no fim de cada um
   (POST em `recibos_ingestao`, linhas contadas) e **dois consertos no KW
   Minning** — o PATCH final passa a gravar `mined` (hoje regrava `mining` e o
   card fica preso no Kanban) e o lote de seeds deixa de cair inteiro na
   colisão 409 (normalizar a query e tolerar duplicata). É o único
   investimento em n8n deste PRD — barato e morre junto com o porte.
7. Tela **Saúde** v1 no front: `vw_saude` — frescor por fonte, heartbeat,
   contas de monetização, alertas abertos.

**Aceite.**
- `select * from exchange_rate_history order by effective_date desc limit 1`
  → data de hoje, todo dia, com recibo `OK` e `linhas = 1`.
- Teste do vigia: parar o container do backend → linha em `alertas` (origem
  `watchdog`, severidade `CRITICO`) sem intervenção humana, **e notificação
  externa chegando em ≤ 15 min com o backend ainda morto** (dead-man's
  switch) — religar não é pré-requisito de ser avisado.
- Execução da Join às 06:00 gera recibo com `linhas` contadas; um dia sem
  linhas gera recibo `VAZIO` — distinguível de "não rodou" no painel.
- A tela Saúde mostra verde/vermelho fiel em pelo menos: joinads, cambio,
  heartbeat, conta AdSense (SUSPENSA aparece).
- Re-mineração de uma oportunidade já minerada: o lote de seeds não cai
  (colisão tolerada) e o card sai de `mining` sozinho ao terminar.

**Fora.** Qualquer ingestão nova; qualquer coisa de Proposta.
**Destrava.** Todas as fases seguintes herdam recibo e vigia de graça; a
regra "verde só com linhas contadas" nasce aqui. **Depende.** F0 (ruído
removido). **Risco de fazer errado.** Fazer o watchdog no backend — aí o vigia
morre com o vigiado, que é exatamente o modo de falha da história deste
sistema. **Reversível.** Sim (tabelas novas, nada destrutivo).

---

## F2 — Custo no banco certo: a ingestão própria mínima *(M–L · reversível)*

**Objetivo.** O lado esquerdo da equação fluindo para o banco que o produto
lê, com o padrão do SPEC (job por fonte, parametrizável por data, recibo,
lote, `partialFailure`).

**Escopo.**
1. Job `gads_custo` no backend (SDK v25 já da casa): cadastro de campanha —
   escrita direta em `campaigns` com `origem_cadastro='descoberta'` e projeto
   resolvido (a RPC `process_google_ads_campaign` se aposenta; campanha sem
   procedência detectada na conta gera alerta `AVISO`, nunca bloqueio nem
   silêncio — SPEC §4.1) + série diária em `daily_campaign_metrics` (mesmas
   11 colunas, mesmo `on_conflict` — os triggers de enriquecimento continuam
   fazendo o resto).
2. Janela D0 4×/dia + passe D-1 às 06:00 — **parametrizável por
   (conta, data)**: reprocessar D-3 é uma chamada, não uma impossibilidade.
   Lista de MCCs/contas em `contas_anuncio` (migração desta fase) — a mesma
   tabela é a allowlist do portão no F3.
3. Filtro de cadastro `status != 'REMOVED'` (o `ENABLED` do D0 antigo fazia
   campanha pausada sumir do custo do dia — defeito medido, não repetir).
4. Porte do ingestor JoinAds do n8n para o backend (os 17 nós viram um
   módulo com os mesmos comentários) — os 2 flows n8n são desligados no fim
   desta fase e o núcleo zera sua dependência de n8n para dados.
5. `termos_busca` materializada pelo mesmo job (base do tribunal no F6).

**Aceite.**
- Reprocessamento histórico: `POST /jobs/gads_custo?data=2026-02-15&conta=<legada>`
  (autenticado) reescreve as linhas de fevereiro **idênticas às existentes**
  (diff por chave `campaign_id,date`) com recibo `sob_demanda` — prova o
  pipeline inteiro sem gastar um real e sem depender de campanha ativa.
- Caminho corrente: rodada D-1 contra a conta com tudo pausado → recibo
  `VAZIO` legítimo, distinguível de falha no painel. (O teste com campanha
  ativa acontece na primeira campanha real do F4 — dependência de gasto,
  marcada lá: às 06:15 de D+1 a linha de ontem existe com spend e recibo `OK`.)
- Paralelo JoinAds: o job novo escreve 3 dias em **tabelas-sombra**
  (`*_paralelo`) enquanto o flow segue em produção; diff sombra×produção por
  chave = zero divergência inexplicada; só então o job assume o destino real
  e o flow desliga. (Escrever os dois no mesmo `on_conflict` compararia a
  linha com ela mesma.)
- Nenhuma cotação literal no código novo (`grep -rE '5[.,](25|35|8)' backend/app/ingestao/` → 0).

**Fora.** GAM/AdSense próprios (sem conta ativa — o módulo nasce quando a
conta existir, com o molde da Join); placements de display (sem campanha
Display na operação nova).
**Destrava.** `vw_arbitragem_diaria` com CPC real; o motor (F6) tem o que
ler; `contas_anuncio` vira a allowlist do F3. **Depende.** F1 (recibos).
**Risco de fazer errado.** Desligar os flows JoinAds antes do diff
sombra×produção fechar — a única fonte de receita viva não pode ter um dia de
buraco. **Reversível.** Sim (reativar flow).

---

## F3 — O substantivo e a porta: Proposta, Autorização, Executor *(L · reversível até armar)*

**Objetivo.** Nascem os quatro substantivos (SPEC §1) e a porta única (§2).
Toda mutação de conta passa a atravessar a mesma escada da criação. Nesta
fase o Executor só executa Propostas **aprovadas por humano** — a
pré-autorização só arma no F6.

**Escopo.**
1. Migrações: `propostas`, `autorizacoes` (com o CHECK `direcao='REDUZ'`),
   `execucoes`, `politicas_decisao` (v1 populada com as constantes herdadas e
   procedência), RLS negando escrita anon.
2. Executor no backend com a escada completa (§2.2): validade → escopo
   (allowlist) → **leitura viva do valor vigente** → **direção derivada** →
   cobertura → faixa sobre o valor vigente → prova `validate_only` →
   idempotência (constraint) → mutate → recibo → **verificação por
   releitura**. Adaptador de estratégia correto por tipo (a tabela
   updateMask×corpo que o Apply Bidding calculava e jogava fora).
3. **Portão desce para o engine**: `volc_ads/gads/client.py` recusa
   `login_customer_id ≠ MCC da casa` **e** alvo de mutação fora da allowlist
   `contas_anuncio` — o caso perigoso não é o login errado, é o login certo
   operando conta de terceiro sob o MCC. O check do router permanece, e o
   `USER_PERMISSION_DENIED` do Google é a terceira parede.
4. Rotas: `POST /propostas` (origem humana), `POST /propostas/{id}/aprovar`,
   `/vetar`, `GET /propostas?estado=…`. Aprovação exige sessão; faixa
   [0,3×–2×] com confirmação dupla fora dela.
5. Front: `BiddingActionBox` renasce como painel de Proposta (cria + aprova
   pela porta); `OrientacaoBox`/`OtimizacaoBox` passam a renderizar
   Proposta/Execução (as colunas `orientacao_*`/`otimizacao_*` congelam).

**Aceite.**
- Ajuste de lance de ponta a ponta numa campanha de teste: criar Proposta no
  front → aprovar → `execucoes` tem `request`, `response`, `valor_antes`,
  `valor_depois` `CONFIRMADA` — e o valor confere no Google Ads Editor.
- `POST /propostas/{id}/aprovar` sem sessão → 401. Webhook antigo → morto
  (re-teste do F0).
- Teste automatizado: Proposta `direcao='AUMENTA'` com `autorizacao_id`
  preenchido → recusada + alerta (o invariante do P3 tem teste, não só CHECK).
- **Direção derivada**: Proposta rotulada `REDUZ` cujo `valor_proposto` está
  acima do valor vigente relido → recusada + alerta `CRITICO` (o rótulo não
  manda; teste).
- Testes de contrato do portão, ambos antes de qualquer HTTP: (a)
  `login_customer_id` estranho → exceção; (b) login da casa + `customer_id`
  alvo fora de `contas_anuncio` → exceção.
- Idempotência: reexecutar a mesma Proposta → no-op garantido por constraint
  (`ux_execucoes_proposta`), com recibo dizendo isso.

**Fora.** Motor automático (F6); qualquer execução sem humano.
**Destrava.** F4 (criação usa a mesma porta), F6 (o motor só emite
Propostas), F7 (a fila é a tabela). **Depende.** F1 (recibos), F2
(`contas_anuncio` populada; séries para evidência — a âncora da trava de
faixa é o valor **relido da API** na execução, não snapshot). **Risco de
fazer errado.** Fazer "só o endpoint" e deixar escada/verificação para
depois — a porta sem escada é o webhook antigo com outro nome.
**Reversível.** Sim.

---

## F4 — Nascimento completo: a junta 2 fechada na transação *(M–L · a 1ª campanha real é gasto — decisão do dono)*

**Objetivo.** O cockpit passa a criar campanha **inteira**: com procedência,
com vínculo de funil, com a conversão sintética, e gravando tudo no banco na
mesma transação. É o conserto definitivo da junta FUNIL→CAMPANHA — que hoje
não tem nem gravação.

**Escopo.**
1. `/subir` persiste na transação: `campaigns` (`campaign_id` devolvido,
   `customer_id`, `funnel_run_id` **obrigatório**, contrato de graduação),
   `campaign_funnel_urls` (do funil publicado, adeus digitação manual no
   `FunnelUrlsEditor`), recibo em `execucoes`. Recibo em arquivo continua
   como cópia, deixa de ser o único registro.
2. Porte da infraestrutura de conversão do flow ClickUp morto para
   `volc_ads`: `conversionAction` por nicho (`UPLOAD_CLICKS`, `PURCHASE`,
   `MANY_PER_CLICK`, lookback 1 dia), `selective_optimization` no payload da
   campanha (o campo `conversao` deixa de viajar e morrer), GAQL **com
   `tag_snippets`** → `niche_conversion_mappings` com `AW-id/label`
   preenchidos. Isenção preventiva de policy entra como opção do brief,
   parametrizada por nicho.
3. Mesa de Lance completa (SPEC-FRONT §5) + o bloco de **autorização de
   defesa** (cria a linha em `autorizacoes` — ainda inerte até o F6).
4. Doutrina P7 garantida por validação: nasce `PAUSED`, `MANUAL_CPC`, phrase;
   graduação registrada (30 conversões → MaxConv com meta = CPA real, ou SEM
   alvo se RPC não medido — cold start do SPEC §5.3).

**Aceite.**
- Ensaio a seco: `/provar` de um pedido completo (com conversão) passa
  `validate_only` e emite selo — repetível à vontade, sem custo.
- Com autorização do dono, uma campanha real: depois do `/subir`,
  `select funnel_run_id, customer_id from campaigns where campaign_id=:novo`
  → ambos preenchidos; `campaign_funnel_urls` ≥ nº de páginas do funil;
  `niche_conversion_mappings` tem a linha do nicho com label **não vazio**.
- A campanha existe no Google Ads `PAUSED`, com a conversão vinculada
  (`selectiveOptimization` visível na API) e `finalUrlSuffix` com as 5 macros.
- Ativação continua sendo gesto humano no Google Ads/front — a fase não muda
  a trava.

**Fora.** Qualquer automatismo de lance; PMax/Display; **o ad group
`[BROAD-MINING]` no nascimento** — broad é a recompensa da graduação
(P7/restrição 5); a forma da sonda broad pós-graduação é decisão do dono,
registrada antes da primeira graduação (SPEC §10.5).
**Destrava.** F5 (o `AW-id/label` que o upload precisa nasce aqui) e a
operação nova em si — é esta fase que permite voltar a operar. **Depende.**
F3 (porta), funil publicado pelo Redator (existe). **Risco de fazer errado.**
Portar os 19 mutates como sequência sem idempotência — modelar como máquina
de estados retomável por `funnel_run_id` (falhou no 12º passo → retoma, não
deixa órfãos na conta). **Reversibilidade.** Criar campanha real gasta
dinheiro quando ativada — a ativação é decisão do dono; tudo antes dela é
reversível (pausada/removível).

---

## F5 — O loop de conversão e o sensor: a junta 4 e o fator 2 *(M–L · reversível)*

**Objetivo.** Fechar o corte mais caro (9.407 gclids, zero enviados) e cegar
menos: o evento de ad-view que fecha três cortes de uma vez (SPEC §5.4).

**Escopo.**
1. **Descoberta e posse do sensor** (primeira tarefa): localizar o worker/GTM
   que escreve `raw_events`/`site_visits`, versionar o código em repositório
   da casa, documentar o deploy.
2. Sensor: payload ganha `host` (conserta as 654/654 linhas vazias) e o
   evento **ad-view com valor estimado** (views × eCPM estimado da sessão);
   `compute_page_daily`/`compute_funnel_daily` estendidas para
   `avg_ads_per_session` completo.
3. `site_visits.conversion_value_calculated` preenchido pelo trigger/job a
   partir dos ad-views da sessão; fila `conversion_queue` populada
   (`pending` → `queued`).
4. Job de upload no backend: lotes `UPLOAD_CLICKS` via API oficial
   (`conversion_batches`), com o diagnóstico do upload gravado (aceitos,
   rejeitados, motivo) e recibo. Usa o `AW-id/label` de
   `niche_conversion_mappings` (F4). **Enquadramento na trava:** o upload é
   escrita contínua na conta e influencia gasto (alimenta o Smart Bidding) —
   só liga quando o dono criar a autorização permanente
   `classe='UPLOAD_CONVERSAO'` (SPEC §1.3/§5.4), revogável, parada pelo kill
   switch global.
5. GTM do portal dispara o evento certo por nicho lendo
   `niche_conversion_mappings` (o consumidor presumido vira consumidor real).

**Aceite.**
- `select count(*) from fact_page_daily where host = '' and report_date > :data_do_deploy` → 0.
- Funil ativo: `avg_ads_per_session > 0` em 100% das linhas novas de
  `fact_funnel_daily` daquele funil.
- Clique de teste com gclid → aparece em `conversion_queue` → lote enviado →
  `conversion_send_status='sent'` e a conversão visível no Google Ads
  (diagnóstico de upload OK) em ≤ 24h.
- Painel de campanha mostra a decomposição do RPC com os 3 fatores
  preenchidos (eCPM da Join + páginas/sessão + anúncios/página) — a
  frase-norte do produto vira consulta.
- Sem a autorização `UPLOAD_CONVERSAO` ativa (ou com o kill switch ligado),
  o job não envia lote nenhum e o recibo diz por quê (teste).

**Fora.** Otimizar o valor da conversão (v1 = estimativa honesta declarada);
floors dinâmicos (`bucket_weights` fica como está).
**Destrava.** O bidding do Google finalmente recebe sinal — a explicação mais
econômica para o −5% de fevereiro deixa de existir; o motor (F6) ganha o CVR
real. **Depende.** F4 (label), campanha ativa (F4 + decisão do dono).
**Risco de fazer errado.** O maior risco do PRD inteiro é de *descoberta*: o
sensor é um terceiro sistema fora do repo. Por isso a posse é o item 1 do
escopo — se ela travar, o resto da fase trava e o cronograma deve dizer isso
cedo. **Reversível.** Sim (conversões enviadas são aditivas; upload pode
parar).

---

## F6 — O motor em casa: replay, sombra, e o Trilho A armado *(L · armar é reversível por revogação + kill switch)*

**Objetivo.** A inteligência sai do JSON e vira serviço testado; a defesa
noturna passa a existir de verdade — só na direção REDUZ.

**Escopo.**
1. Motor como função pura (SPEC §5.2) lendo `politicas_decisao`, emitindo
   Propostas; árbitro separado com `veto_motivos`; cooldown lendo
   `execucoes`; correções deliberadas documentadas (falso zombie 18:30,
   conflito INCREASE+INCREASE, customer_id).
2. **Replay dourado**: as 12 decisões + 10 mutações de 16–19/fev viram
   fixtures (entrada = `daily_campaign_metrics` da janela; esperado =
   `orientacao_json`/`otimizacao_json` gravados). Relatório de divergências
   campo a campo, cada divergência classificada como *bug corrigido* ou
   *regressão* — commitado em `docs/replay-beast.md`.
3. **Sombra**: motor roda no cron (06:30/18:30) emitindo Propostas com
   `gate='SOMBRA'` por ≥ 14 dias sobre as campanhas novas — visíveis na fila,
   inexecutáveis. Critério de saída da sombra: zero Propostas inexplicadas
   pelo operador.
4. **Armar Trilho A**: Propostas REDUZ cobertas por autorização executam
   sem humano (§2.3), com teto diário, piso de verba e kill switch global.
   Trilho B permanece 100% fila humana.
5. Monitor de monetização ligado ao gatilho de defesa: conta com receita
   zerada e custo correndo → Propostas REDUZ para as campanhas da conta
   (o teste é simulado, marcando a conta como SUSPENSA em staging de dados).
6. Tribunal lexical em SQL sobre `termos_busca`: negativações saem como
   Propostas `NEGATIVAR_TERMO` (REDUZ, `teto_termos_dia` nos limites da
   autorização), promoções como `PROMOVER_TERMO` na fila — cuja aprovação
   **despacha para a porta de criação** uma campanha nova (um termo, um
   conjunto; P7), nunca keyword na campanha de origem. Mutates com
   `partialFailure: true`.

**Aceite.**
- `pytest` do motor: replay dourado passa com divergências 100% classificadas.
- 14 dias de sombra com diário de bordo; nenhuma execução de aumento sob
  autorização (consulta: `select count(*) from execucoes e join propostas p
  on p.id = e.proposta_id where e.direcao_efetiva = 'AUMENTA' and
  p.aprovada_por = 'autorizacao'` → **0, sempre** — sobre a direção
  **derivada** pelo Executor, não sobre o rótulo do produtor; vigiado pelo
  watchdog, não só testado).
- Ensaio de defesa em duas metades: (a) **detecção** — staging de dados com
  custo correndo e receita zerada além do limiar (`horas_zerada`, política) →
  o monitor muda o estado da conta e emite as Propostas **sozinho**; (b)
  **reação** — Propostas REDUZ executadas até o piso em ≤ 15 min, notificação
  enviada, tudo no ledger.
- Kill switch: com `trava_global` ligada, Executor recusa tudo (teste).

**Fora.** Preditivo influenciando decisão; BLITZ/PROVEN (nunca rodaram em
produção — só entram com N que os exercite).
**Destrava.** A promessa do produto (gestão que se defende sozinha e pede
permissão para crescer). **Depende.** F2 (dados), F3 (porta), F5 (CVR real —
o motor pode rodar antes, em sombra, com o que houver). **Risco de fazer
errado.** Armar sem sombra, ou portar as constantes sem o replay — é trocar
um motor não testado por outro. **Reversibilidade.** Revogar autorizações +
kill switch param tudo em segundos; cada execução é individualmente
reversível (lance/verba/pausa voltam).

---

## F7 — A carteira: as telas compõem *(M · reversível)*

**Objetivo.** A tela que não existe: "das suas N campanhas, estas 6 querem
algo de você hoje" — e o detalhe que explica *por quê* com a equação
decomposta.

**Escopo.**
1. `vw_carteira` + página Carteira: fila de Propostas agrupada por direção
   (REDUZ executadas = informar; AUMENTA = aprovar/vetar em lote; ALERTA =
   ler), com reversibilidade e frescor visíveis por card.
2. Detalhe de campanha reformado: `vw_arbitragem_diaria` (spread + 3 fatores,
   cada um com "medido/não medido"), linha do tempo Propostas+Execuções,
   comportamento por página do funil.
3. Saúde v2: contas de monetização com histórico, redundância por site
   (site com uma única fonte ativa = AVISO permanente).
4. Aposentadoria visual: OrientacaoBox/OtimizacaoBox/BiddingActionBox somem;
   markdown de orientação morre no servidor.

**Aceite.**
- Com ≥ 5 campanhas ativas: a Carteira responde em uma consulta quais
  precisam de ação hoje; aprovar 3 Propostas em lote gera 3 execuções no
  ledger.
- No detalhe, um fator não medido aparece como "não medido" — nunca zero
  disfarçado (teste de UI com fixture sem eCPM).

**Fora.** Multi-operador/memberships (volta quando houver segundo operador).
**Destrava.** Operação em escala (40 campanhas sem 40 abas). **Depende.** F3
(Propostas existem), F6 (fila tem conteúdo do motor — a tela funciona antes,
só com Propostas humanas). **Risco.** Baixo — é projeção de dados que já
existem. **Reversível.** Sim.

---

## F8 — Previsão persistida *(M · reversível · condicionada a N)*

**Objetivo.** A bola de cristal vira serviço honesto: persistida, medida
contra baseline, e útil como simulador — nunca como executor.

**Escopo.** `previsoes` + biblioteca (dois estágios sem vazamento, conformal
calibrado fora da amostra, teto 2× budget); gate de ativação por campanha
(≥ 12 dias); acurácia empírica publicada na tela (cobertura real do
intervalo, MAE vs baseline); simulador `planned_spend` no cockpit ("se eu
subir para R$ 80 amanhã…"); veto preditivo no árbitro **só depois** de bater
o baseline por 14 dias.

**Aceite.** `select count(*) from previsoes where prevista_para = current_date + 1`
> 0 para campanhas elegíveis; painel mostra cobertura real do CI (meta ≥ 80%
para CI de 90% — o antigo entregava 64% prometendo 90%); log do gate mostra
o veto preditivo inativo até o critério.

**Fora.** Modelar a identidade do negócio (eCPM × páginas/sessão) — é o norte
do SPEC §5.5, entra quando houver volume por vertical.
**Depende.** F2+F5 rodando por semanas (N=0 no dia 1 — sem dados, sem fase).
**Risco.** Ligar o veto preditivo antes do baseline — um intervalo otimista
vetando escala boa é pior que nenhum preditivo. **Reversível.** Sim.

---

## A ordem, defendida em uma tabela

| fase | valor destravado | esforço | por que antes da seguinte |
|---|---|---|---|
| F0 | segurança + diagnóstico limpo | horas | tudo que vem depois mede errado com o ruído ligado |
| F1 | o sistema se vigia (P1) | M | sem recibo, cada fase seguinte pode "passar" mentindo — o alicerce vem antes da parede |
| F2 | CPC real no banco certo | M–L | o motor e a carteira leem daqui; e é pré-requisito de faixa do F3 |
| F3 | o substantivo + a porta | L | F4/F6/F7 são impossíveis sem Proposta/Executor; F2 antes só porque a porta precisa do valor_atual |
| F4 | voltar a operar (junta 2) | M–L | precisa da porta; destrava F5 (label) e o negócio em si |
| F5 | sinal de conversão + fator 2 (junta 4) | M–L | precisa do label do F4; sem ele o Google otimiza no escuro de novo |
| F6 | defesa sozinha + otimização na fila | L | precisa de dados (F2), porta (F3) e idealmente CVR (F5); sombra pode começar cedo |
| F7 | escala de operação | M | projeta o que F3/F6 criaram; antes seria tela vazia |
| F8 | antecipação honesta | M | último porque exige N que só as fases anteriores geram |

**Marcações de reversibilidade que importam:** o único ato *irreversível por
natureza* do PRD é gastar dinheiro de mídia — e ele fica atrás de dois gestos
humanos (subir com selo no F4, ativar a campanha) e de uma direção (AUMENTA
nunca é automático). Abandonar o hospedado é irreversível *por decisão* — os
dados continuam lá, mas nenhuma fase depende deles. Todo o resto — flows
desativados, tabelas novas, autorizações, motor armado — desfaz com um
clique, uma revogação ou o kill switch.

## Riscos transversais (não pertencem a uma fase)

1. **O sensor é de terceiros até o F5 provar o contrário.** A posse do código
   é a tarefa mais incerta do PRD — antecipar a descoberta (pode começar no
   F1, é só leitura).
2. **Monocultura de receita.** Até existir segunda fonte, a Join é ponto
   único de falha — o painel diz isso em AVISO permanente (F1/F7), e a
   decisão de abrir GAM/AdSense próprios é do dono, não deste PRD.
3. **Regime pós-17/08 do Smart Bidding.** Toda graduação segue
   `SMART-BIDDING-2026-08-17.md`: meta = CPA observado ou MaxConv sem alvo;
   revisar a regra de escalada (+15% por rank) antes de qualquer porte — foi
   calibrada num regime que acabou.
4. **Uma pessoa mantém tudo.** Cada fase termina com o runbook de si mesma
   (como rodar, como saber que parou, como desligar). Um sistema que só o
   autor opera é o problema 2 de novo, com outra roupa.
