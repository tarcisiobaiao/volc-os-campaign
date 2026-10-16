# 03 — Matriz de atribuição: identidade, chaves e grão honesto

**Thread:** C (identidade e atribuição) · **Data:** 2026-10-16 · **Branch:** `lab/dil-fundacao-20261016-c`
**Estado (taxonomia do manifesto §7):** módulo `volc_dil.fundacao.identidade` *testado hermeticamente + testado com sintético*;
a matriz abaixo é **leitura de código** em cada ref, cruzada com as **leituras read-only de produção do integrador**
(`docs/data-intelligence/fundacao-20261016/receipts/leituras-externas/RECIBO-LEITURAS-20261016.md`, L1–L12). Nada aqui é
"calibrado com dado real" além do que aquele recibo mediu.

Rótulos: **[D]** demonstrado em `main`/base; **[W]** demonstrado só em `wip/*` ou em `043c77f5`; **[P]** medido em
produção pelo recibo do integrador; **[X]** executado nesta thread (JavaScript real rodado em Node, sem rede);
**[I]** inferido; **[NT]** não verificável sem leitura externa nova.

## 0. Veredito

1. **Confirmado: há fundação para custo × receita em campanha × dia, e não há atribuição determinística por clique.**
   A ponte é `campaign.id` (Ads) = `custom_value` da JoinAds com `custom_key=utm_campaign`, porque o Final URL suffix
   vivo põe `utm_campaign={campaignid}` [W] e a JoinAds devolve esse id: 97–100 % do earnings de domínio cai em
   `custom_value` numérico em todos os dias de 08 a 16/10, inclusive depois do GTM v35 [P L5].
2. **Refinamento que a missão não tinha: o tráfego do sensor NÃO junta com campanha hoje.** O VOLC Sensor v3 lê
   `utm_campaign`, mas a regex de "telefone" do filtro de PII descarta qualquer valor com ≥ 10 dígitos — e
   `campaign.id` (11 dígitos) e `ad_group.id` são descartados. Provado executando o código real [X] e medido em produção:
   28 sessões `paid=1` em 15–16/10, **nenhuma** com `utm.campaign` [P L4]. Hoje o sensor só carrega
   `source/medium/term` + `paid`. Logo "custo × tráfego × receita por campanha × dia" tem a coluna de tráfego
   **não atribuível** (não zero).
3. **Clique e sessão: impossível** — o sensor nunca envia o valor de `gclid/gbraid/wbraid` (só `paid=1`) e nenhuma fonte
   de receita tem grão de sessão. Receita agregada não pode ser distribuída por sessão; o módulo recusa com erro tipado.

## 1. Onde mora cada pedaço (refs sem histórico comum)

| Peça | Ref / caminho | Observação |
|---|---|---|
| VOLC Sensor v3 | `wip/historico-measurement-20261015` (`918e9571`) `measurement/gtm/volc-sensor-v3.html` (409 linhas) | sha256 `cb018224…a41e4`, **idêntico** ao arquivo não rastreado `volc-os-campaign/measurement/gtm/volc-sensor-v3.html` (checkout de `043c77f5`). **Ausente** de `main` e de `043c77f5` |
| WEBS Wrapper v2 | idem, `measurement/gtm/webs-wrapper-v2.html` (152 linhas) | sha256 `bbd4c821…ed699`, idêntico ao não rastreado |
| `volc-ingest` | idem, `supabase/functions/volc-ingest/index.ts` (171 linhas) | sha256 `3739594b…0ca`, idêntico ao não rastreado |
| Final URL suffix vivo | `043c77f5:.claude-ads/runs/google-ads-recovery-20261015T125729-0300/receipts/d-live-campaign-audit.json:37`; `…/receipts/c-ads-readonly-summary.json:1952` | `utm_source=google&utm_medium=cpc&utm_campaign={campaignid}&utm_term={keyword}&utm_content={adgroupid}&utm_device={device}&utm_placement={placement}&vc_creative={creative}&vc_match={matchtype}&vc_network={network}&vc_target={targetid}&vc_loc={loc_physical_ms}&vc_ext={extensionid}` + auto-tagging ligado |
| Fatos Google Ads | `main:supabase/migrations/v12_04_gads_fato_canonico_dia.sql:259-266` (campanha-dia); `main:…/v17_01_gads_fatos_granulares.sql:55-182` (famílias `hora_dispositivo,url,geo,placement,termo,keyword,asset`; CHECK `:125`) | v21 append-only aplicado em produção [P L1] |
| JoinAds legado | `main:src/sql/joinads/01_joinads_metrics.sql:24-45` (`date, utm_campaign_value, joinads_domain`, `revenue NOT NULL DEFAULT 0` `:30`); `main:n8n/gerar_flows_joinads.py:12-31` (1 dia por request), `:221-227` (guarda de chave trocada), `:394-396` (custom_keys válidas) | |
| JoinAds v2 | `wip/historico-joinads-20261015` (`192bc065`) `n8n/joinads_v2_normalize.js:66-116` (`campaign_id` só se `^\d+$`, `:69-70`), `:166-184` (rejeita chave trocada e id inválido), `:186-233` (endpoints) | aplicado e ativo em shadow [P L1, L9] |
| GAM | `main:supabase/migrations/20260910143000_gam_attribution_grain_router.sql:1-22`; `main:…/v17_04_arbitragem_reconciliada.sql:84-86` | `gam_metrics` vazia no snapshot (grafo) |
| AdSense | `main:src/sql/adsense_funnel_aggregation.sql:38,226-227` (`url × date`) | suspenso desde fev/2026 [W identity-gap-matrix] |
| Funil | `campaign_funnel_urls` (17 linhas antigas, 0/17 com host do site monetizado, campanha atual ausente) [W `journey-contract.json` `page_role`]; `trafego_vinculo` vazio [D grafo `concept:reconciliation`] | |
| Contratos de atribuição anteriores | `043c77f5:.claude-ads/runs/economic-attribution-20261015T1310-0300/{identity-gap-matrix,journey-contract,writer-reader-map}.json` | o `journey-contract.json` **já registrava** o defeito como risco R7 |

## 2. Sobrevivência ponta a ponta de cada chave

Cadeia: Ads (Final URL suffix / auto-tagging) → URL de chegada → Sensor v3 (`campaign()`) → `volc-ingest` → `raw_events`
→ JoinAds (key-value) → junção.

| Chave | Ads → URL | URL → Sensor v3 | Sensor → `raw_events` | URL → JoinAds | Resultado |
|---|---|---|---|---|---|
| `campaign.id` | ✓ `utm_campaign={campaignid}` [W] | **✗ descartado** (≥10 dígitos casa `sensor:73`; `utmValue` `:107-112`) [X][P L4] | ✗ (nada a gravar) | ✓ `custom_value` numérico [P L5]; setter **não identificado** (o wrapper v2 também o descarta, `wrapper:38,77`) [X] | Ads↔JoinAds **sim**; sensor↔qualquer **não** |
| `ad_group.id` | ✓ `utm_content={adgroupid}` [W] | ✗ (ids de grupo têm ≥10 dígitos [I]; mesma regex) [X para 12 dígitos] | ✗ | custom_key `utm_content` existe na API, **não coletada** [D `gerar_flows_joinads.py:394`] | nenhuma junção hoje |
| keyword (texto) | ✓ `utm_term={keyword}` | ✓ normalizada (minúscula, sem acento/pontuação, espaço→`_`, ≤40 UTF-16) salvo se tiver ≥10 dígitos/e-mail [X] | ✓ `payload.utm.term` (28 em 3 dias [P L4]) | ✗ (não há custom_key `utm_term`) | Ads↔sensor **probabilística** (texto, colide entre grupos/tipos) |
| match type, device, placement, creative, network, target, loc, extension | ✓ (`utm_device`, `utm_placement`, `vc_*`) | ✗ fora da allowlist (`sensor:121`) | ✗ | ✗ | perdidas |
| `gclid/gbraid/wbraid` | ✓ auto-tagging | só **presença** → `paid=1`; valor nunca sai (`sensor:114,125`) [X] | `payload.utm.paid` | ✗ (wrapper bloqueia a key, `wrapper:33`) | clique **impossível** |
| landing / URI | ✓ URL final (`landing_page_view`) | ✓ `host` + `path` (pathname, PII mascarado, ≤200, sem query) `sensor:139-140` | ✓ colunas `host`,`path` | ✓ `land_uri` (v2, `custom_key=land_uri`) [W] | página × dia **sim** (Ads/sensor determinística; JoinAds probabilística até verificar o formato de `land_uri`) — mas **não** cruza com campanha |
| post WordPress | ✗ | ✗ (só path) | ✗ | ✓ `id_post_wp` (v2) [W] | via funil declarado (path→post) |
| sessão | — | `sid` por aba em `sessionStorage` (`sensor:88-94`) | ✓ `sid` | ✗ | sessão existe só no sensor |
| país | geo `geoTargetConstants/*` (v17_01 família `geo`) | ✗ | ✗ | ✓ campanha × país × ad unit (v2 `key_value_country_adunit`) [W] | campanha × país × dia **probabilística** (semânticas diferentes) |
| dispositivo | `hora_dispositivo.dispositivo` | só viewport `vw/vh` | ✓ `vw/vh` | ✗ | não é chave |
| hora | `hora_dispositivo.hora` no fuso da conta | `ts` (relógio do cliente) | ✓ `ts`, `ts_sec` | `metric_hour` existe no normalizador v2; endpoint que a preencha **não demonstrado** [NT] | sem receita horária |
| data | `metric_date` no fuso da conta (America/Sao_Paulo) | `ts` | `ts` timestamptz (UTC) | `date` DD/MM/AAAA, **fuso de fechamento não verificado** (`src/sql/joinads/README.md`, "Ainda em aberto") | dia exige conversão declarada |

## 3. Matriz chave × fonte (expõe? em que campo? onde?)

`—` = a fonte não expõe. Entre parênteses, o estado em produção quando o recibo do integrador mediu.

| Chave | Google Ads | GTM / Sensor v3 / `raw_events` | Funil / página / destino | JoinAds | GAM / AdSense |
|---|---|---|---|---|---|
| conta | `customer_id` (`v12_04:263`, `v17_01:60`) | — | `projects.google_ads_customer_id` | — (só `domain`) | — |
| campanha | `campaign_id` (`v12_04`, `v17_01:61`) | `payload.utm.campaign` em `volc_sensor_ready` — **vazio para id numérico** (`sensor:107-125,403-407`) [P L4: 0 de 28 sessões pagas] | `campaign_funnel_urls.campaign_id`, `trafego_vinculo` (declarado; vazio/antigo) | `custom_value` c/ `custom_key=utm_campaign` (legado `utm_campaign_value` `01_joinads_metrics.sql:24`; v2 `campaign_id` `normalize.js:69`) [P L5] | `gam_metrics.utm_campaign_value` (0 linhas) |
| ad group | `ad_group_id` só nas famílias `termo`/`keyword` (`v17_01:79,173`) | `payload.utm.content` — vazio para id numérico [X] | — | custom_key `utm_content` disponível, não coletada | — |
| anúncio | — (nenhuma família `ad`; `asset_id` ≠ anúncio) | — | — | — | — |
| keyword | `criterion_id`, `keyword_texto` (`v17_01:83-84`) | `payload.utm.term` (texto normalizado) | — | — | — |
| termo de busca | `termo` (`v17_01:80`; `search_term_day` 23.891 obs [P L10]) | — (termo real não vai à URL) | — | — | — |
| landing / URI | família `url` (`url`, `url_tipo`) | `host`, `path` (colunas) | `campaign_funnel_urls.url`, `paginas_publicadas.url_wp` | `land_uri` (v2) | AdSense `adsense_metrics.url` |
| post WP | — | — | `paginas_publicadas[].id` | `id_post_wp` (v2) | — |
| sessão | — | `sid` (por aba, sem timeout) | — | — | — |
| clique | `click_view` não coletado | só `paid` 0/1 | — | — | — |
| país | família `geo` (`geo_constant`, `local_tipo`) | — | — | `country`/`iso` (v2) | — |
| dispositivo | família `hora_dispositivo` | `vw`,`vh` (viewport) | — | — | — |
| hora | `hora` (`v17_01:66`) | `ts`, `ts_sec` | — | `metric_hour` [NT] | — |

## 4. Grão honesto por par de fontes (hoje → potencial)

Codificado como dado em `volc_dil.fundacao.identidade.graos.MATRIZ`; `exigir_grao()` recusa o que está `nao_atribuivel`.

| Par | Grão honesto hoje | Confiança | Mais fino possível depois de… | Nunca |
|---|---|---|---|---|
| Google Ads × JoinAds | **campanha × dia** (e conta × dia por roll-up) | determinística | grupo × dia, se coletar `custom_key=utm_content` e provar a chegada do `{adgroupid}` | sessão, clique, hora (sem receita horária) |
| Google Ads × JoinAds | campanha × país × dia | probabilística | — (geo do Ads ≠ geo da requisição) | |
| Google Ads × Sensor | **landing × dia** (determinística na chave; contagens não reconciliam: consentimento, bot, aba); keyword-texto × dia (probabilística) | ver ao lado | campanha × dia e grupo × dia, se o sensor deixar passar id numérico; clique, se o sensor enviar `gclid` (decisão de privacidade) | termo de busca |
| Sensor × JoinAds | landing × dia | probabilística | campanha × dia, com a correção do sensor | **sessão** (receita agregada) |
| Funil × JoinAds | post WP × dia | determinística | | |
| Funil × Sensor | landing × dia | determinística (path declarado) | post × dia com tabela funil→url→post | |
| Google Ads × Funil | campanha | não atribuível hoje (vínculo da campanha atual não existe) | determinística, com vínculo datado em `trafego_vinculo` | |
| Google Ads × GAM | campanha × dia | não atribuível hoje (fonte vazia) | determinística | |
| Google Ads × AdSense | landing × dia | não atribuível hoje (suspenso) | probabilística | |

**Consequência para a junção econômica:** custo (BRL) × receita (USD) por campanha × dia é determinística; tráfego do sensor
nessa mesma linha sai `nao_atribuivel` com motivo, nunca zero. Receita sem chave (≈0–3 % do earnings [P L5]) fica num balde
explícito.

## 5. A contradição `utm_campaign`

### 5.1 A evidência antiga

`volc-os-workbook/ROADMAP-VIVO.json`, tarefa **P06-T09**, campo **`proof`**, nas refs `043c77f5` e
`wip/historico-fontes-de-verdade-20261015` (`4be92dfc`; ausente de `main`/`HEAD`, onde P06-T09 não tem esse texto):
"… sessão, página e ad view não se ligam à campanha (**sensor v3 descarta utm_campaign**; sem click id)".
Comando: `git show <ref>:volc-os-workbook/ROADMAP-VIVO.json | python3 -c '…walk… re.search("descart", …)'` (busca em todos os campos;
única ocorrência). A mesma conclusão está, com o mecanismo, em
`043c77f5:.claude-ads/runs/economic-attribution-20261015T1310-0300/journey-contract.json`, `duplication_and_loss_risks[R7]`
("utm_campaign numérico descartado como PII … Observado: sessões google/cpc com campaign=null") e em
`fact_page_daily.gaps` ("sem campanha (utm_campaign descartado no sensor)").

### 5.2 O código, ref por ref

| Ref | Sensor | Linhas |
|---|---|---|
| `main` (`104bb0d0`) | **não existe** (`git grep -l "volc_utm\|utmValue\|__VOLC_S" main` → só docs de incidente) | — |
| `043c77f5` | **não existe** no commit (só recibos que o citam) | — |
| `wip/historico-measurement-20261015` (`918e9571`) | existe, único commit que o contém | allowlist `:121` (`utm_source…utm_term`); `utmValue` `:107-112`; regex `:73` |
| arquivo sujo `volc-os-campaign/measurement/gtm/volc-sensor-v3.html` | não rastreado (`??`), sha256 idêntico ao do wip | idem |
| demais `wip/historico-*` | não contêm `measurement/` | — |

Histórico: `git log -S utm_campaign -- measurement/gtm/volc-sensor-v3.html measurement/gtm/webs-wrapper-v2.html supabase/functions/volc-ingest/index.ts`
→ `main`: vazio; `043c77f5`: vazio; `wip/historico-measurement-20261015`: só `918e9571` (preservação L1). **Não há versão anterior
versionada** do sensor nem do wrapper v1 — a v34 do GTM (rollback) não está no repositório.

O mecanismo (`sensor:69-79,107-112`):

```js
/\+?\d[\d\s().-]{8,}\d/g                        // telefone, cartão, sequências longas   (:73)
if (!v || clean(v, 200) !== v.replace(/\s+/g, ' ')) return '';                       // (:109)
```

`clean()` troca PII por `[x]`; se mudou algo, o valor inteiro é descartado. Qualquer sequência de ≥ 10 caracteres entre
dígitos/espaço/`().-` que comece e termine em dígito casa — o id da campanha ativa (11 dígitos; nos vetores, o sintético `20000000011`) casa (e casa também a de CPF, `:72`).

### 5.3 Veredito

**As duas afirmações estão certas pela metade; a do roadmap está certa no efeito.** O código *lê* `utm_campaign`
(allowlist `:121`), mas, para o template vivo (`{campaignid}`), *descarta o valor*. Provas:

- [X] Executando o `utmValue` real extraído do HTML em Node: `utmValue("20000000011") === ""` (id sintético de 11 dígitos; o real, de mesmo comprimento, dá o mesmo resultado); a URL real do template vira
  `{source:"google", medium:"cpc", term:"cursos_tecnicos", paid:1}` — sem `campaign` e sem `content`
  (`receipts/identidade/vetores_utm_sensor_v3.json`, `cenarios_campaign[0]`).
- [P] Produção 15–16/10: 28 sessões `paid=1`, todas com `utm.source`, nenhuma com `utm.campaign`; chaves em 3 dias:
  paid 53, source 29, medium 29, term 28, **campaign 1** (RECIBO-LEITURAS L4).
- Teste executável: `tests/data-intelligence/fundacao/test_identidade_ponta_a_ponta.py::test_hoje_custo_e_receita_juntam_mas_trafego_e_nao_atribuivel`.

Corolário novo: a frase do `identity-gap-matrix.json` (`043c77f5`, `answers.d`) — "WEBS wrapper copia `utm_campaign` da URL
para setTargeting … coincide com o id" — é **falsa para o wrapper v2**: `safeValue` tem a mesma regex (`wrapper:38,77`) e
descarta o id [X]. Como a JoinAds continua recebendo o id depois da v35 [P L5], o key-value chega por outro setter — mais
provavelmente o script da própria JoinAds (`script.joinads.me` carregado no `<head>`, `main:docs/architecture/GADS-FECHAMENTO-SNIPER-2026-10-09.md:61`;
as custom_keys `land_uri`/`id_post_wp` que o wrapper não define também chegam) [I]. Mecanismo **não identificado** (L6).

### 5.4 Os outros quatro pontos

| Afirmação | Veredito | Prova |
|---|---|---|
| Sensor envia `utm_content`/`utm_term`? | **Lê os dois**; `utm_term={keyword}` chega (texto normalizado, 28 em 3 dias [P]); `utm_content={adgroupid}` é numérico ≥10 dígitos e **cai** pela mesma regex | `sensor:121`; vetores [X]; L4 [P] |
| Wrapper GPT envia só source/medium/campaign? | **Sim por padrão** (`targeting` default `wrapper:8,28`, até 10 keys `:83`) **mais** a key de página `pg` (slug, `:29,84,109`). E, para o template vivo, o `campaign` numérico **não** é enviado (`safeValue` `:74-80`). Diverge do sensor em dois pontos: sem o teto de 200 (trunca em vez de descartar) e testa PII **sem** colapsar espaços antes (sequência como `13 85⏎⏎7.7` cai no wrapper e passa no sensor) — o comentário "mesma normalização do WEBS Wrapper" (`sensor:105`) não é exato | código; vetores [X] (11 de 3000 aleatórios divergem: 10 por > 200, 1 por espaço não colapsado) |
| Valores de gclid/gbraid/wbraid nunca saem, só `paid=1`? | **Sim** no sensor (`:114,125`; presença, até vazia `?gclid=`, vira `paid=1`); o wrapper bloqueia essas keys (`:33`); o ingest não tem campo (`index.ts:16-27`) | [X] `test_valor_do_gclid_nunca_chega_ao_raw_events` |
| Lote 10 s / 20 eventos? | **Sim**, com ressalvas: `flushMs:10000`, `maxBatch:20` (`sensor:31-32`); flush imediato também em clique interno (`:361`), `pagehide` (`:194`), aba oculta (`:196`) e ao atingir 20 (`:149`); lote > 60 000 bytes é partido ao meio (`:157-162`); o ingest corta em 20 (`index.ts:7,124`) e colapsa duplicatas por `(sid,pid,event_name,ts_sec)` (`:161-164`; índice UNIQUE confirmado [P L3]) | código |

### 5.5 Delta de curadoria proposto (não aplicado)

- **P06-T09** (`proof`): manter "sensor v3 descarta utm_campaign", acrescentar o mecanismo e a prova:
  "regex de PII ≥10 dígitos (`volc-sensor-v3.html:73,109`, wip `918e9571`); 0/28 sessões pagas com campaign em 15–16/10 (recibo
  L4); a ponte custo×receita campanha×dia via JoinAds segue íntegra após o GTM v35 (L5)". Status segue `partial`.
- **P08-T07**: ver handoff (§ HANDOFF-C).

## 6. Leituras externas

Já feitas pelo integrador (read-only, recibo citado): L1, L3, L4, L5, L9–L12. Pendentes, consultas exatas:

1. **Setter do key-value da JoinAds (L6)** — GTM API read-only, versão live: listar tags e o HTML de cada tag custom
   (`GET https://tagmanager.googleapis.com/tagmanager/v2/accounts/<conta-gtm>/containers/<container-gtm>/versions/live`, escopo
   `tagmanager.readonly`), procurar `setTargeting`, `utm_campaign` e `joinads`. E no site, sem gerar impressão:
   `curl -s https://<site-monetizado>/<landing>/ | grep -o 'script.joinads.me[^"]*'`.
2. **Comprimento de `ad_group.id`** — GAQL read-only: `SELECT ad_group.id FROM ad_group WHERE campaign.id = <campanha-ativa>`
   (só o comprimento interessa; não precisa imprimir o valor).
3. **Formato de `land_uri`** e `custom_key=utm_content` — `SELECT endpoint, custom_key, left(custom_value,1) AS inicio,
   length(custom_value) AS n, count(*) FROM joinads_observation WHERE metric_date >= date '2026-10-08' GROUP BY 1,2,3,4 ORDER BY 1,2;`
   (com `default_transaction_read_only=on`).
4. **Fuso de fechamento JoinAds** — comparar `/earnings` D-1 lido às 23:00 e às 06:00 BRT do dia seguinte
   (`SELECT metric_date, collected_at, sum(revenue_gross) FROM joinads_observation WHERE endpoint='earnings' GROUP BY 1,2 ORDER BY 1,2;`).
5. **Sessões pagas × cliques** — `SELECT (ts AT TIME ZONE 'America/Sao_Paulo')::date d, count(DISTINCT sid) FILTER (WHERE (payload->'utm'->>'paid')='1')
   FROM raw_events WHERE event_name='volc_sensor_ready' AND ts >= now()-interval '7 days' GROUP BY 1 ORDER BY 1;` contra cliques Ads do dia
   (razão, não soma).

## 7. Lacunas e plano para descer de campanha × dia (proposta; nada executado)

| # | Passo | Destrava | Custo / risco | Autorização | Teste que provaria |
|---|---|---|---|---|---|
| 1 | **Sensor: isentar `utm_campaign`/`utm_content` da regex de telefone quando o valor é `^\d{6,20}$`** (allowlist por chave, mantendo o filtro para o resto) | campanha × dia e grupo × dia no tráfego; funil por campanha | Baixo risco de privacidade (id de campanha/grupo não é dado pessoal, mas 11 dígitos podem ser um CPF por coincidência — mitigar exigindo chave UTM conhecida, nunca valor livre); **mudança no GTM** | publicação GTM (P16-T05/P06-T07) | vetor-ouro novo: `utmValue('<campanha-ativa>')` com a regra nova = `'<campanha-ativa>'` e `utmValue('123.456.789-01')` = `''`; canário: `count(*) FILTER (WHERE payload->'utm'->>'campaign' ~ '^\d+$') > 0` em `raw_events` pós-publicação; `test_identidade_ponta_a_ponta` com `RegistroCampanhas` igual e `cobertura.fracao_sessoes_pagas_resolvidas` → próxima de 1 |
| 2 | Alternativa sem tocar o filtro: `utm_campaign=gads_{campaignid}`? **Não funciona** — a regex não é ancorada (`c20000000011` também cai [X]). Só funcionaria quebrando o id com letras, o que ValueTrack não faz | — | — | — | `test_campaign_id_real_e_descartado_como_pii` já prova |
| 3 | **JoinAds: coletar `custom_key=utm_content`** (grupo) no v2 | grupo × dia custo × receita | +1 request/dia/endpoint (API agrega por chamada); quota não documentada; depende de o setter do key-value levar `utm_content` cru | n8n (ativação) | `SELECT count(*) FROM joinads_observation WHERE custom_key='utm_content' AND custom_value ~ '^\d{10,}$'`; reconciliação Σ grupo ≈ Σ campanha por dia |
| 4 | ValueTrack `{matchtype}`/`{keyword}` já estão no sufixo; para keyword determinística seria preciso `{targetid}` (`kwd-<criterion_id>`) **e** a JoinAds aceitar essa key — não aceita (lista fechada `gerar_flows_joinads.py:394`) | keyword × dia só no tráfego | allowlist do sensor ampliada (`vc_target`) | GTM | vetor + canário como no passo 1 |
| 5 | **Chave de sessão na receita** (ex.: key-value `sid` por impressão) | sessão × receita | **Alto**: o wrapper bloqueia `sid/session` por política (`wrapper:33`), viola o desenho privacy-by-design e provavelmente a política do Ad Manager para identificadores; a JoinAds não reporta por key arbitrária | jurídico + parceiro | — (não recomendado) |
| 6 | **Click id** (`gclid` em `raw_events`) | clique × sessão | **Alto** (identificador de clique é dado pessoal sob LGPD com consentimento); exige revisão de consentimento — o site envia `granted` por padrão antes da escolha (`VOLC-MEASUREMENT-V3-2026-10-15.md` §Consentimento) | jurídico | — |
| 7 | Vínculo datado campanha → funil (`trafego_vinculo`) para <campanha-ativa> | funil × campanha | baixo; humano confirma | operador | `SELECT … FROM trafego_vinculo WHERE campaign_id='<campanha-ativa>' AND valido_em…` = 1 linha |
| 8 | Declarar o fuso da JoinAds (leitura 4) | dia determinístico dos dois lados | nenhum | — | `Cobertura.fuso_receita_verificado=True` com prova |

## 8. Módulo `volc_dil.fundacao.identidade` (API pública)

- `normalizacao`: `normalizar_utm_sensor_v3`, `diagnosticar_utm_sensor_v3` (→ `MotivoDescarte`: `mantido|vazio|pii|longo_demais`),
  `normalizar_valor_wrapper_v2`, `utm_da_pagina_sensor_v3` (réplica de `campaign()` com `sessionStorage`),
  `parse_query_urlsearchparams`, `limpar_utm_ingest`, `UtmSessao`. Fiel a JS em `\s`, `\d`, `/i`, corte UTF-16 e
  `URLSearchParams` — provado contra 65 vetores nomeados + 3000 pseudoaleatórios + 11 cenários de `campaign()` gerados pelo
  código real. **Ressalva Unicode (R1-F24):** idêntica até o Unicode 15.1 do CPython 3.13; o Node 26 usa Unicode 17 e o
  revisor mediu 3.536/4.000 divergências em caracteres novos do 16/17 (0/6.003 até 15.1). Valor fora do 15.1 → chave probabilística.
- `chave_campanha`: `interpretar_chave_campanha` (→ `campaign_id` **ou** `MotivoRecusa`: `ausente`, `descartado_pelo_sensor`,
  `macro_nao_expandida`, `chave_trocada`, `textual_ambiguo`, `possivelmente_truncado`, `id_invalido`),
  `interpretar_campanha_da_sessao` (distingue "UTM perdida pelo sensor" de "orgânico").
- `resolvedor`: `RegistroCampanhas`/`CampanhaRegistrada` (conta + id + nome + validade + template `id|nome`) e
  `resolver()` → `Resolucao(confianca ∈ {deterministica, probabilistica, nao_atribuivel}, motivo)`.
- `graos`: `MATRIZ`, `exigir_grao`, `receita_por_sessao` (sempre recusa), `GraoNaoSuportado` (carrega o grão honesto disponível).
- `colisao`: `detectar_colisoes_registro` (mesma UTM/duas campanhas, id em duas contas, renomeação, truncamento ambíguo),
  `detectar_custom_key_substituida`, `colisoes_de_normalizacao`.
- `juncao`: `juntar_campanha_dia(custos, eventos, receitas, registro, *, as_of, receitas_dominio=None,
  dominios_dia_kv_coletados=None, trafego_campanha_comprovado=False, …)` → `ResultadoJuncao(linhas, cobertura,
  receita_nao_atribuida)`; `para_json`. Só receita **determinística** entra na linha; probabilística vai ao balde com
  motivo `receita_exige_chave_deterministica:*`. Tráfego aceita probabilística e marca `confianca_sessoes`.

### 8.1 Contrato de entrada da junção (R1-F5)

A junção recebe **estado `as_of`, não fluxo**:

1. `as_of` obrigatório, com fuso. Linha com `disponivel_em > as_of` (ou evento com `ts > as_of`) → `FuturoNaJuncao`.
2. Cada `ReceitaChaveDia` é a **versão vigente em `as_of`** de uma identidade
   `(endpoint, grao, dia, dominio, custom_key, custom_value, dimensao)` e traz `disponivel_em` (sem ele → `ContratoDeEntrada`).
   Quem resolve versões é o chamador (ex.: `joinads_observation_latest` ou o `as_of` da thread A).
3. **Um único grão de receita por chamada** (`campaign_day` legado, `campaign_adunit_day` ou `campaign_country_adunit_day`
   da v2), com `len(dimensao)` coerente; dois grãos/endpoints → `GraoMistoNaReceita` (são cortes do mesmo dinheiro:
   somá-los dobra a receita). Identidade repetida (inclusive diferindo só por espaço/`www.`) → `LinhaDuplicada`.
4. Custo: um estado por `(conta, campanha, dia)`; earnings: um por `(dia, domínio)`; repetição → `LinhaDuplicada`.
5. Tráfego segue `MATRIZ` (R1-F6): Google Ads × Sensor em campanha × dia é `nao_atribuivel` hoje ⇒ toda linha sai com
   sessões `nao_atribuivel` e o motivo da matriz; `trafego_campanha_comprovado=True` só quando a condição `requer` estiver
   provada (vetor-ouro do sensor novo + canário). Zero de sessões só com sensor visto no **host declarado da campanha**
   (`CampanhaRegistrada.hosts`) naquele dia; sem host declarado → `ausente`. Cliques `None` → `nao_coletado`.
6. Cobertura de receita (R1-F19): denominador = earnings dos domínio × dia que **também** tiveram /key-value coletado
   (padrão: os presentes nas linhas; ou `dominios_dia_kv_coletados` explícito, para incluir coleta que voltou vazia).
   Earnings sem /key-value coletado vai a `receita_earnings_sem_kv`; receita com chave sem earnings, a
   `receita_kv_sem_earnings`; ambos com aviso, nenhum entra como "sem chave".

## 9. Resposta à revisão adversarial R1

Fonte: `handoffs/REVISAO-ADVERSARIAL-R1.md` (achados da thread C). Testes novos em
`tests/data-intelligence/fundacao/test_identidade_r1.py` (18) e `test_identidade_sem_sensiveis.py` (3); todos falhavam
antes (os scripts do revisor reproduziram 2× a receita, cliques `0`, zero de sessão sem sensor, fração 1/10 e `custon_key`
ignorado na base `3c5281e8`; o F18 dava `UnicodeEncodeError`).

| Achado | Correção | Prova |
|---|---|---|
| F5 dupla contagem | identidade de linha `(endpoint, grão, dia, domínio, custom_key, custom_value, dimensão)`; `GraoMistoNaReceita`, `LinhaDuplicada`, `FuturoNaJuncao`; `as_of` obrigatório (contrato §8.1); custo e earnings também sem duplicata | `test_f5_*` (8) |
| F6 null→0 e matriz | cliques `None` → `nao_coletado`; sessões seguem `capacidade(G,S,campanha,dia)` (hoje `nao_atribuivel`); zero só com sensor no host da campanha | `test_f6_*` (4) |
| F18 surrogate | `_js_len` (surrogatepass) no parser | `test_f18_*` |
| F19 universos | denominador = earnings ∩ /key-value coletado; baldes `receita_earnings_sem_kv`/`receita_kv_sem_earnings` + avisos | `test_f19_*` (3) |
| F23 `??` | `custom_key` null cai para `custon_key` | `test_f23_*` |
| F20 (M13) | teste com `" utm_campaign "` | `test_m13_*` — mutante M13 reaplicado: morre |
| F24 Unicode | ressalva no docstring de `normalizacao.py` e no §8 | — |
| F25 dados reais | conta, campanha, GTM, domínio, cliente e valores monetários substituídos por sintéticos nos arquivos da thread C; vetores regenerados do mesmo JS (sha256 da fonte inalterado); varredura `test_identidade_sem_sensiveis.py` | 3 testes |

Mutantes nas correções: 11 aplicados, 11 mortos (M13, `??`, duplicata de receita, grão misto, cliques `None`, matriz,
host do zero, universo do denominador, `as_of`, custo duplicado, `_js_len`).

Não contestei nenhum achado. Observação: o veredito da contradição (§5) não muda — os valores reais citados antes estão
nos recibos do repositório (`043c77f5`); aqui ficam só ids sintéticos de mesmo comprimento, que reproduzem a mesma prova.
