# Fichas do legado n8n — conhecimento operacional de mídia paga

> Agente G · missão **Google Growth Engine do VOLC OS** · 26/08/2026.
> Fonte primária: `inventario-n8n/` (extração read-only da instância de produção
> do n8n em 19/08/2026, **fora do versionamento**). Todo número literal desta
> página foi reconferido contra o JSON do flow no disco em 26/08/2026 — a
> conferência está descrita no README. **Nenhum workflow foi ativado, editado,
> disparado ou importado; nenhuma chamada à API do n8n ou do Google Ads foi
> feita.**

## Como ler uma ficha

O legado n8n é **evidência de intenção e conhecimento operacional, não
autoridade automática**. Uma regra estar escrita num flow não a torna verdadeira,
e um flow estar `ativo: true` não prova que ele executou. Cada ficha separa o que
foi medido do que foi apenas declarado, e termina num **destino canônico**:

| # | Destino | Significado |
|---|---|---|
| ① | **política versionada do domínio** | vira regra em código, com janela, amostra mínima, cooldown e teto — entra em `regras-canonicas.json` |
| ② | **job que chama o backend canônico** | a lógica migra para o VOLC OS; o n8n (ou pg_cron) fica só como agendador (ADR-05) |
| ③ | **absorvido** | já existe no VOLC OS — a ficha aponta arquivo e linha |
| ④ | **descartar** | com o motivo e o que se perde |
| ⑤ | **decidir depois** | com a pergunta exata que falta responder |

Quando a regra é do tipo que a missão proíbe reimplementar — *"CPA acima de X
pausa"*, *"aumente sempre 20%"*, *"CPC baixo é sempre o problema"*, *"sem
conversão em um dia significa campanha ruim"* — a ficha traz o selo
**⚠️ UNIVERSAL DEMAIS** e diz o que faltaria para torná-la defensável.

Quando o flow escreve no Google Ads ou no Supabase ao lado do VOLC OS, a ficha
traz **🔶 AUTORIDADE PARALELA** e remete a `conflitos.md`.

---

# A · Nascimento e validação de campanha nova

Fonte: `gads-new-campaign-validation` ("GOOGLE ADS - New Campaigns Validation",
44 nós, 486 linhas). **Estado: inativo** (`ativo: false` no `.meta.json`; última
alteração `2026-07-16T20:06:17Z` — é o mais recente dos quatro motores de
decisão). Dois gatilhos: cron `0 0 6,15 * * *` (06:00 e 15:00) e `manualTrigger`.

O arquivo carrega **dois motores divergentes**: `Code1` ("NEXUS v4.9",
139 linhas) no ramo agendado, e `Code` ("NEXUS v3.0", 297 linhas) no ramo manual.
Os dois decidem a mesma coisa com números diferentes. O arquivo não escolhe.

---

### A01 · Portão de idade mínima de 48 horas

- **Propósito.** Impedir que a campanha seja julgada antes de o leilão e o
  algoritmo do Google reagirem ao que acabou de subir.
- **Entrada.** `campaign.start_date_time` da Google Ads API v21 (`FROM campaign`),
  convertido em `campaign_age_hours` no nó `Code`.
- **Decisão.** `MIN_CAMPAIGN_AGE_HOURS: 48` — abaixo disso o diagnóstico é
  `APRENDIZADO_INICIAL` e **nenhuma ação é gerada**.
- **Saída.** Nenhuma. A campanha sai da fila daquela rodada.
- **Evidência usada.** Constante literal no bloco `CONFIG` do nó `Code`, lida do
  JSON em 26/08.
- **Risco.** Baixo, e é um risco de omissão: 48h pode ser pouco para uma conta
  com pouco volume. O defeito real está no fallback — `campaign_age_hours` cai
  para `999` quando o parse da data falha, e **uma campanha com data malformada
  é tratada como madura** e escapa da proteção.
- **Reversibilidade.** Total: é um portão de leitura, não altera nada.
- **Estado atual.** Inativo (o workflow inteiro está desligado).
- **Conflito com o engine atual.** Nenhum. O VOLC OS ainda não tem portão de
  maturidade, porque ainda não tem laço de decisão.
- **Destino: ① política versionada** — absorvido dentro de
  `modo_de_validacao_por_idade` (ficha C01), que é a versão madura desta ideia.
  O fallback `999` **não vai junto**: idade indeterminada é `null`, e `null`
  bloqueia a ação em vez de liberá-la.

---

### A02 · Diagnóstico de inércia por utilização de verba e impressões

- **Propósito.** Achar campanha que subiu e **não anda** — o problema oposto ao
  de gastar mal.
- **Entrada.** Métricas de **D-1 apenas** (`segments.date BETWEEN ontem AND
  ontem`): `metrics.impressions`, `metrics.cost_micros`; `campaign_budget.amount_micros`.
- **Decisão.** `isInertia = utilization < 30% || impressions < 500`
  (`UTILIZATION_THRESHOLD: 30`, `IMPRESSIONS_THRESHOLD: 500`). Só campanhas
  `ENABLED` entram.
- **Saída.** Marca a campanha como candidata; o remédio vem das fichas A03–A05.
- **Evidência usada.** `CONFIG` do nó `Code`, conferido no JSON.
- **Risco.** ⚠️ **UNIVERSAL DEMAIS** em parte: "500 impressões" e "30% de
  utilização" são absolutos, sem referência a canal, vertical, geo ou tamanho de
  verba. Uma campanha de R$10/dia e uma de R$500/dia recebem a mesma régua.
- **Reversibilidade.** Total (é diagnóstico).
- **Estado atual.** Inativo. E mesmo ativo, o ramo que roda por cron é o
  **v4.9**, não este — o v3.0 está pendurado no `manualTrigger`.
- **Conflito com o engine atual.** Parcial e **em favor do VOLC OS**:
  `backend/app/trafego/alertas.py` já responde "ligada há N horas, uma impressão,
  R$ 0,00" a partir de snapshot em Postgres, sem tocar no Google Ads.
- **Destino: ③ absorvido, com lacuna.** O sinal já existe em
  `backend/app/trafego/alertas.py:364` (`alerta_projetado`) e
  `backend/app/trafego/alertas.py:312` (`razoes_do_espelho`). O que falta lá é o
  **limiar relativo**; o que sobra aqui é o número absoluto. Fica registrado
  como entrada de política em `inercia_de_entrega` só quando houver referência
  medida — hoje o campo é `null`.

---

### A03 · "CTR bom e não entrega" ⇒ subir o lance

- **Propósito.** Diagnóstico central do v3.0: se o anúncio agrada quem o vê mas
  o volume não vem, o gargalo é preço de leilão, não relevância.
- **Entrada.** `metrics.ctr` de D-1, `ad_group.cpc_bid_micros`, `campaign.target_cpa`.
- **Decisão.** `ctr > 3%` (`CTR_GOOD_THRESHOLD: 0.03`) ⇒ `LANCE_ABAIXO_DO_LEILAO`.
  Novo valor = `base + max(base × incremento%, piso)`, com
  `CPC_INCREMENT_PERCENT: 0.25` / `CPC_INCREMENT_FLOOR: 0.05` e
  `TCPA_INCREMENT_PERCENT: 0.20` / `TCPA_INCREMENT_FLOOR: 0.02`, capado em
  `MAX_CPC_BRL: 0.50` / `MAX_TCPA_BRL: 0.30`.
- **Saída.** Item na `webhook_queue` → cooldown de 24h → **POST no webhook de
  bidding** → `campaigns:mutate` no Google Ads → `INSERT bid_actions` com
  `action_type: "AUTO_NEXUS_V3"`.
- **Evidência usada.** `CONFIG` do nó `Code`, transcrito do JSON em 26/08.
- **Risco.** ⚠️ **UNIVERSAL DEMAIS**, e é exatamente o padrão *"CPC baixo é
  sempre o problema"*. Três defeitos: (a) **+25% é um passo fixo** que não olha
  a distância até o alvo nem o spread; (b) `MAX_TCPA_BRL` é uma constante
  escolhida uma vez — e depois de **17/08/2026** o tCPA deixou de ser teto e
  passou a ser gasto autorizado (ver `inventario-n8n/sistema-atual/SMART-BIDDING-2026-08-17.md`);
  (c) CTR alto com RPC baixo é motivo para **baixar** o lance, não subir, e o
  v3.0 não olha receita nenhuma.
- **O que faltaria para ser defensável.** Janela ≥ 3 dias em vez de D-1; amostra
  mínima de cliques declarada; teto derivado (`tCPA_max = RPC ÷ k`, com
  `k = conversões ÷ cliques` medido — foi **0,677 / 0,676 / 0,805** nas três
  campanhas da casa entre 12 e 19/02/2026); passo proporcional ao gap, não fixo;
  cooldown e rollback explícitos.
- **Reversibilidade.** Baixa na prática: o lance anterior é gravado em
  `bid_actions.valor_anterior`, mas **nada lê essa tabela** e o webhook não
  registra falha — ver ficha A08 e `conflitos.md`.
- **Estado atual.** Inativo. 🔶 **AUTORIDADE PARALELA** latente: o executor que
  ele chama (`atuacao-apply-bidding-webhook-v2`) **continua ativo**.
- **Conflito com o engine atual.** Direto. O VOLC OS não move lance; se esta
  regra voltar a rodar, passam a existir dois donos do `target_cpa_micros`.
- **Destino: ① política versionada**, reescrita — entra como
  `escala_por_impression_share_perdido` (C09) e `escada_de_alteracao` (C04). O
  gatilho por CTR absoluto **é descartado**; o gatilho canônico é perda de
  impressão por rank com spread positivo comprovado.

---

### A04 · "Muita impressão e ninguém clica" ⇒ revisão humana

- **Propósito.** Separar problema de preço (A03) de problema de relevância.
- **Entrada.** `metrics.impressions` e `metrics.ctr` de D-1.
- **Decisão.** `impressions > 100 && ctr <= 1%` (`CTR_BAD_THRESHOLD: 0.01`) ⇒
  `RELEVANCIA_CRITICA` ⇒ `REVIEW_MANUAL`.
- **Saída.** Nenhuma mutação. Vira item de revisão (e, no ramo agendado, task no
  ClickUp).
- **Evidência usada.** `CONFIG` do nó `Code`.
- **Risco.** ⚠️ **UNIVERSAL DEMAIS** na amostra: **100 impressões não decidem
  CTR**. Com CTR real de 1%, a expectativa em 100 impressões é 1 clique — zero
  cliques é resultado comum de campanha saudável.
- **O que faltaria.** Amostra mínima derivada de intervalo de confiança, não um
  inteiro redondo; comparação contra a mediana do ad group/vertical em vez de um
  absoluto; e a saída correta é sempre humana, o que esta regra já acerta.
- **Reversibilidade.** Total — a saída é uma tarefa, não uma mutação.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum, e há **convergência de doutrina**: o
  VOLC OS já trata "não sei" como resposta legítima
  (`backend/app/trafego/alertas.py:179`, campo `nao_sabemos`).
- **Destino: ① política versionada** com amostra corrigida — entra como
  `relevancia_sob_suspeita`, saída sempre **fila humana**, nunca mutação.

---

### A05 · "Zero impressão" ⇒ lance fixo de R$ 0,15

- **Propósito.** Destravar campanha que não entra em leilão nenhum.
- **Entrada.** `metrics.impressions == 0` e `campaign_budget.amount_micros`.
- **Decisão.** `impressions == 0 && budget >= 10` (`MIN_BUDGET_BRL: 10.00`) ⇒
  `FORCAR_LANCE_MINIMO`: lance **fixo em R$ 0,15**, ignorando o valor atual.
- **Saída.** Mesmo caminho da A03 — webhook → `campaigns:mutate`.
- **Evidência usada.** Nó `Code`.
- **Risco.** ⚠️ **UNIVERSAL DEMAIS** e o mais perigoso do grupo: um número
  mágico sobrescreve a decisão anterior sem olhar histórico. Zero impressão tem
  pelo menos cinco causas — anúncio reprovado, keyword sem volume, geo errado,
  verba não liberada, campanha recém-criada — e **quatro delas não melhoram com
  lance maior**.
- **O que faltaria.** Diagnosticar a causa antes do remédio: ler
  `ad_group_ad.policy_summary`, `keyword_view` de volume e o estado de veiculação
  da campanha. Só com "elegível, com volume, e perdendo por rank" o lance é a
  resposta — e aí o valor sai da fórmula, não de uma constante.
- **Reversibilidade.** Baixa: sobrescreve o lance sem guardar de onde saiu.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** O VOLC OS **já sabe diagnosticar isso melhor**:
  `volc_ads/forca.py` lê `ad_group_ad.ad_strength` e `action_items` da própria
  API, e `backend/app/trafego/alertas.py:312` deriva razões do espelho.
- **Destino: ④ descartar.** O que se perde: a intenção de destravar campanha
  parada. Ela é preservada — mas como **alerta com causa nomeada**, não como
  lance mágico. O substituto já existe em `alertas.py`.

---

### A06 · SUPER_GRADUATION — 30 conversões migram de CPC manual para Maximize Conversions

- **Propósito.** A regra de negócio mais explícita do legado inteiro: dizer
  quando uma campanha "formou" e pode passar da mão para o algoritmo.
- **Entrada.** `campaign.bidding_strategy_type == 'MANUAL_CPC'`,
  `metrics.conversions` e `metrics.cost_micros` de **D-1**,
  `campaign_budget.amount_micros`.
- **Decisão.** `isManual && convs >= 30` (`TCPA_GRADUATION_CONVS: 30`) ⇒
  `newValue = spend / convs` (**o CPA real de ontem**) e
  `newBudgetValue = max(budget × 2, 30.00)` (`GRADUATION_BUDGET_MULT: 2`,
  `GRADUATION_BUDGET_FLOOR: 30.00`).
- **Saída.** No ramo agendado: **uma task no ClickUp** (team `9007096682`), para
  um humano executar. Não há mutação automática nesse ramo.
- **Evidência usada.** Bloco `CONFIG` e regra R1 do nó `Code1`, transcritos
  literalmente do JSON em 26/08.
- **Risco.** Metade boa, metade cara. **Definir a meta = CPA observado é
  exatamente o comportamento correto depois de 17/08/2026** — não há folga a
  perder, porque o Google passou a convergir para a meta. **Dobrar o orçamento
  no mesmo passo é o erro**: remove a restrição que segurava o gasto no mesmo
  instante em que a meta vira autorização. E o CPA base vem de **um único dia**.
- **O que faltaria.** Separar os dois movimentos: graduar primeiro, observar,
  mexer em verba depois — com cooldown entre eles. CPA base de janela ≥ 7 dias.
  E decidir explicitamente entre `MAXIMIZE_CONVERSIONS` **sem** alvo (não é
  estratégia baseada em meta, não converge) e **com** alvo (converge para o
  número declarado) — o `SMART-BIDDING-2026-08-17.md` §5.4 mostra que essa
  escolha virou decisão de regime, e o engine já a expressa literalmente em
  `volc_ads/campanha/comum.py:113`.
- **Reversibilidade.** Alta se feita pelo caminho do ClickUp (humano no meio);
  baixa se automatizada, porque a estratégia anterior não é registrada.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** O VOLC OS já sabe **criar** nos dois regimes
  (`volc_ads/campanha/comum.py:113` e `:123`), mas não sabe **migrar** uma
  campanha existente. É lacuna, não colisão.
- **Destino: ① política versionada** — `graduacao_de_estrategia`, com o passo de
  verba **separado** e sob aprovação humana.

---

### A07 · Escala por impression share perdido (NEXUS v4.9, regras 2 e 3)

- **Propósito.** Usar o que o próprio leilão informa sobre o motivo de a
  campanha não aparecer: falta de verba ou falta de rank.
- **Entrada.** `metrics.search_budget_lost_impression_share`,
  `metrics.search_rank_lost_impression_share`, `metrics.ctr`, e
  `utilization = spend / budget` — tudo de **D-1**.
- **Decisão.** Três regras mutuamente exclusivas, nesta ordem:
  - R1 = graduação (ficha A06);
  - **R2** `lost_budget > 0.20 && ctr >= 0.03` ⇒ `INCREASE_BUDGET`,
    `budget × 1.25` (`IS_BUDGET_THRESHOLD: 0.20`, `MIN_CTR_FOR_SCALE: 0.03`,
    `BUDGET_INCREMENT_STEP: 0.25`);
  - **R3** `lost_rank > 0.25 && utilization > 0.8 && ctr >= 0.03` ⇒
    `min(base × 1.15, teto)` com teto `MAX_CPC_BRL: 0.50` ou `MAX_TCPA_BRL: 0.35`
    (`IS_RANK_THRESHOLD: 0.25`, `BID_INCREMENT_STEP: 0.15`).
- **Saída.** Task no ClickUp (ramo agendado).
- **Evidência usada.** `CONFIG` e as três regras do nó `Code1`, lidas do JSON.
- **Risco.** O **diagnóstico é bom e o remédio é universal demais**. Distinguir
  "perdi por verba" de "perdi por rank" é exatamente a pergunta certa; responder
  sempre com +25% e +15% não é. ⚠️ *"aumente sempre 20%"* na forma literal.
  Agravante medido: `MAX_TCPA_BRL` vale **0,35** aqui e **0,30** no v3.0 do mesmo
  arquivo, e `MAX_CPC_BRL 0,50` com o `k ≈ 0,70` medido equivale a um CPA de
  R$ 0,714 — **o dobro** do teto de tCPA. Os dois tetos da casa não conversam.
- **O que faltaria.** Passo proporcional ao share perdido e ao spread projetado,
  não constante; teto derivado de `RPC ÷ k`; janela ≥ 3 dias; verificação de que
  o spread continua positivo **depois** do aumento, com rollback automático.
- **Reversibilidade.** Média — o valor anterior existe na resposta da API mas
  não é persistido em lugar que alguém leia.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum hoje.
- **Destino: ① política versionada** — `escala_por_impression_share_perdido`,
  com os passos fixos substituídos por passo proporcional e teto derivado.

---

### A08 · Cooldown de 24 horas consultado em `bid_actions`

- **Propósito.** Impedir que a mesma campanha receba duas mudanças de lance no
  mesmo dia.
- **Entrada.** `GET /rest/v1/bid_actions?campaign_id=eq.X&aplicado_com_sucesso=eq.true
  &aplicado_em=gte.{agora-24h}&limit=1`.
- **Decisão.** Array vazio ⇒ pode agir (`IF - Cooldown OK1`).
- **Saída.** Libera ou barra o POST no webhook de bidding.
- **Evidência usada.** Nós `Supabase - Check Cooldown1` e `IF - Cooldown OK1`.
- **Risco.** **É o único cooldown do legado inteiro que consulta um fato
  persistido** — e por isso o único que poderia funcionar. Os outros três são
  código morto: o do BEAST depende de `last_action`, que nunca é preenchido; o
  dos dois árbitros depende de `last_bid_change_at`, coluna que **não existe** em
  `campaigns` nem em `daily_campaign_metrics`. O defeito deste é a assimetria:
  ele filtra por `aplicado_com_sucesso = true`, e o executor **nunca grava
  `false`** — uma falha deixa a linha com `NULL` e a campanha volta a ser
  elegível na rodada seguinte, sem ninguém saber que a anterior falhou.
- **Reversibilidade.** N/A (é uma trava, não uma ação).
- **Estado atual.** Inativo, e **`bid_actions` tem 0 linhas** no Supabase
  self-hosted (medido em 19/08/2026). O schema local também **não tem** as
  colunas `customer_id`, `campaign_name`, `causa_raiz`, `action_type` que o
  `INSERT` do flow envia — o insert quebraria contra este banco.
- **Conflito com o engine atual.** Nenhum, mas a tabela é citada na prioridade
  **9 da curadoria** ("Separar fato, recomendação e ação").
- **Destino: ① política versionada** — `cooldown_entre_atuacoes`. A correção
  obrigatória: o cooldown olha **tentativa**, não sucesso; e toda tentativa
  grava linha, com resultado, antes de a próxima ser avaliada.

---

# B · O que a fábrica de campanhas sabia

Fontes: `gads-campaign-search` ("Google Ads Search - Clickup", 39 nós, **ativo**,
gatilho `clickUpTrigger` — arrastar um card para a coluna "google ads" sobe uma
campanha) e `criacao-gads-factory-v3` ("🚀 Google Ads Factory v3.0 - FIXED",
171 nós, **ativo**, **6 formulários públicos** sem autenticação além da URL).

Recorte: esta camada não mede spread, mas define os parâmetros iniciais de verba,
lance e keywords — e por isso entra. O que é copy/criativo fica fora.

---

### B01 · Toda campanha nasce `PAUSED`

- **Propósito.** A trava de segurança única da criação: a decisão de queimar
  dinheiro continua sendo humana.
- **Entrada.** N/A — é uma constante do payload de criação.
- **Decisão.** `"status": "PAUSED"` no `campaigns:mutate` dos dois flows.
- **Saída.** Campanha existente e inerte no Google Ads.
- **Evidência usada.** Payload do nó `📢 2. Cria Campanha5` de
  `gads-campaign-search`; equivalente na Factory v3 (que pausa também ad group e
  RSA).
- **Risco.** Nenhum. O risco é o oposto — esquecer de despausar.
- **Reversibilidade.** Total.
- **Estado atual.** Ativo declarado nos dois. O `gads-campaign-search` porém
  **quebra no segundo passo**: os nós `🔧 Extrai e Mapeia (ID + Label)` e
  `Code in JavaScript` chamam `$('⚙️ Config Global')`, e o nó existente chama-se
  `⚙️ Config Global5`. Corroborado por medição: `niche_conversion_mappings` = 0
  linhas e nenhuma campanha nova em `campaigns` desde **2026-02-13**.
- **Conflito com o engine atual.** **Nenhum — é a mesma doutrina.**
- **Destino: ③ absorvido.** `volc_ads/campanha/comum.py:92`
  (`camp.status = c.enums.CampaignStatusEnum.PAUSED`). O VOLC OS vai além, com
  trava de escrita de dois fatores em `volc_ads/gads/modo.py:34`
  (`escrita_permitida()`) e `:49` (`destravar(motivo)`), que o n8n não tem.

---

### B02 · Dois ad groups no mesmo orçamento: `[PHRASE]` de performance + `[BROAD-MINING]` a 70% do lance

- **Propósito.** Rodar descoberta de termos de busca **dentro** da campanha de
  performance, a um preço menor, sem abrir uma segunda campanha e sem dividir a
  verba em dois tetos.
- **Entrada.** A lista de keywords do card do ClickUp, com volume parseado de
  linhas no formato `- keyword | Vol: 12.300 (...)`.
- **Decisão.**
  - `[PHRASE] - AdGroup_{ts}` recebe **todas** as keywords em `matchType: PHRASE`,
    com `cpcBidMicros = cpc_micros`;
  - `[BROAD-MINING] - AdGroup_{ts}` recebe as **3 de maior volume** em
    `matchType: BROAD`, com `Math.round((cpc_micros * 0.7) / 10000) * 10000` —
    para R$ 0,12 isso dá exatamente **R$ 0,08**.
- **Saída.** Dois `adGroups:mutate` e dois `adGroupCriteria:mutate`.
- **Evidência usada.** Nós `🔑 Prepara Keywords5`, `📁 3. Cria AdGroups5` e os
  dois `adGroupCriteria:mutate` de `gads-campaign-search`.
- **Risco.** Baixo e bem desenhado. O arredondamento a 10.000 micros é
  deliberado (o Google trabalha em passos de centavo). O risco residual é o
  BROAD canibalizar o PHRASE no mesmo leilão — mitigado pelo lance menor.
- **Reversibilidade.** Total (pausar o ad group de mineração).
- **Estado atual.** Ativo declarado, mas inalcançável: o fluxo quebra antes
  (ficha B01). E o operador **não controla verba nem CPC**: os nós leem
  `$json['Budget Diário (R$)']` e `$json['CPC Inicial (R$)']`, campos que **não
  existem numa task do ClickUp** (são resíduo do formulário da Factory v3) —
  logo toda campanha nasceria com R$ 10/dia e R$ 0,12, independentemente do que
  o operador escreveu.
- **Conflito com o engine atual.** Nenhum. O VOLC OS cria Search com estrutura
  própria (`volc_ads/campanha/search.py`), e a arquitetura de dois ad groups
  **não está lá**.
- **Destino: ⑤ decidir depois.** *A pergunta exata:* **o ad group de mineração
  BROAD a 70% do lance deve fazer parte do perfil de canal SEARCH do VOLC OS, ou
  a descoberta de termos passa a ser um job de leitura de `search_term_view` sem
  comprar tráfego exploratório?** É uma decisão de custo de aprendizado, e cabe
  ao dono do domínio de aquisição — não a mim. Registro o número medido (0,7 e
  as 3 de maior volume) para que a decisão não precise ser reconstruída.

---

### B03 · Isenção preventiva de política, keyword a keyword

- **Propósito.** Subir keyword de nicho de benefício social sem ser reprovado
  uma a uma. Enviar a isenção **antes** da reprovação é o que torna a criação
  one-shot.
- **Entrada.** Cada keyword do brief.
- **Decisão.** Em **todo** `adGroupCriteria:mutate`, para cada keyword:
  `exemptPolicyViolationKeys: [{ policyName: "GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES", violatingText: kw }]`.
- **Saída.** Operação de criação de keyword com isenção embutida.
- **Evidência usada.** Os dois nós `adGroupCriteria:mutate` de `gads-campaign-search`.
- **Risco.** **Alto e conceitual**, e o VOLC OS já resolveu melhor. Pedir isenção
  é **afirmar ao Google que o anúncio não é daquela categoria**. Fazer isso em
  bloco, preventivamente, para toda keyword, transforma uma afirmação verificável
  numa declaração automática — e o preço não é "barrado agora", é "veicula e cai
  depois, com a conta marcada".
- **Reversibilidade.** Baixa: reputação de conta não tem rollback.
- **Estado atual.** Ativo declarado (inalcançável na prática).
- **Conflito com o engine atual.** **Colisão de doutrina, e o VOLC OS está
  certo.** `volc_ads/politica_auto.py` inverte o padrão: `ISENTAR_SOZINHO` é uma
  **allowlist de uma política só** (`NON_FAMILY_SAFE`), nascida de recusa real
  medida; o desconhecido cai no padrão seguro, que é **remover a keyword**. E
  `volc_ads/isencao.py:184` (`montar`) monta o plano a partir da falha real
  devolvida pela API, com `is_exemptible` lido do Google, em vez de presumido.
- **Destino: ③ absorvido — e superado.** `volc_ads/politica_auto.py` (allowlist +
  `decidir` + `podar`) e `volc_ads/isencao.py:184`. O que vale guardar do legado
  é só o **fato de domínio**: `GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES` é a
  política que este nicho encosta. Isso vira **evidência para avaliar entrada na
  allowlist quando houver recusa real medida**, não uma entrada automática.

---

### B04 · Seleção de keywords do Keyword Planner: competição LOW/MEDIUM, top 50

- **Propósito.** Escolher o que comprar sem operador digitando lista.
- **Entrada.** `POST customers/{id}:generateKeywordIdeas` com
  `geoTargetConstants/2076` (Brasil), `languageConstants/1014` (português),
  `pageSize: 100`, `includeAdultKeywords: false`, janela histórica de 3 meses.
- **Decisão.** `ALLOWED_COMPETITION = ['LOW','MEDIUM']` (descarta `HIGH`);
  dedupe case-insensitive mantendo o de **maior volume**; ordena por
  `avgMonthlySearches` desc; corta em `MAX_KEYWORDS = 50`; fallback para o
  próprio nicho se a API não devolver nada.
- **Saída.** Lista que vira as keywords da campanha.
- **Evidência usada.** Nó `🎯 Filtra Keywords` (141 linhas) da Factory v3.
- **Risco.** Baixo e honesto. O viés é conhecido: excluir `HIGH` exclui
  justamente onde há dinheiro — defensável em arbitragem de display, onde a
  margem é fina, mas é uma **escolha estratégica disfarçada de filtro técnico**.
- **Reversibilidade.** Total (é seleção, antes de qualquer gasto).
- **Estado atual.** Ativo declarado. **6 cópias divergentes** do mesmo nó no
  mesmo workflow (2 variantes de `🎯 Filtra Keywords`, 5 de `✅ Valida Conteúdo`,
  3 de `🎨 Prepara Assets`) e 6 prompts de LLM diferentes entre si.
- **Conflito com o engine atual.** O VOLC OS obtém keywords por outra porta (o
  Pautador / motor de pautas), e `backend/app/trafego/projecao.py` impõe uma
  regra que o legado não tem: **nenhum CPC sai sem procedência** — porque o
  `DATAFORSEO-MEDIDO.md` mediu, em 96 chamadas, que `keyword_info.cpc`
  superestima o CPC real em **7,4×** e inverte a ordem dentro do cluster.
- **Destino: ② job que chama o backend canônico.** A chamada ao Keyword Planner
  é uma fonte de dados legítima e **o CPC dela vem do próprio Google, não do
  DataForSEO** — é a melhor procedência disponível hoje. O agendamento/gatilho
  pode ficar fora; a seleção e o registro de procedência vão para o backend.

---

### B05 · A esteira de escala da Factory v3 — 50 conversões migram para Maximize Conversions

- **Propósito.** A mesma ideia da ficha A06, escrita por outra mão e com outros
  números: declarar quando a campanha "forma".
- **Entrada.** Google Sheets (`filtro fase = "1_MANUAL_CPC"`) +
  `metrics.conversions, cost_micros, clicks ... DURING LAST_30_DAYS`.
- **Decisão.** `🎯 Conversões >= 50?` ⇒ `maximizeConversions.targetCpaMicros =
  (cpa_target || 0.17) × 1e6`, `updateMask: "maximizeConversions.targetCpaMicros"`;
  depois grava `fase = "2_MAXIMIZE_CONVERSIONS"` na planilha.
- **Saída.** `campaigns:mutate` no Google Ads + linha em Google Sheets.
- **Evidência usada.** Componente órfão de 5 nós da Factory v3.
- **Risco.** **É código morto duplamente**, e isso é o achado. (a) O
  `⏰ Trigger - Verificar Escala` tem `rule.interval: [{}]` — sem intervalo — e
  **nenhuma conexão de saída**; (b) os 5 nós referenciam
  `$('⚙️ Configurações Globais')`, nó que **não existe** no workflow. Se alguém
  ligar o trigger, quebra na primeira linha.
- **Reversibilidade.** N/A.
- **Estado atual.** Inalcançável dentro de um workflow **ativo**. É a definição
  de armadilha: o código está publicado, parece uma regra da casa, e nunca rodou.
- **Conflito com o engine atual.** Contradiz a ficha A06 no mesmo repositório —
  **50 conversões aqui, 30 lá; tCPA default R$ 0,17 aqui, CPA real medido lá**.
  Duas políticas da casa, nenhuma decidida.
- **Destino: ④ descartar**, guardando **um** fato: o número R$ 0,17 e o limiar
  50 existiram como intenção. O que se perde: nada operacional — nunca executou.
  O que fica: a prova de que a graduação precisa de **uma** definição
  versionada, que é a `graduacao_de_estrategia` da ficha A06.

---

# C · Lance, orçamento e contenção — a linhagem ORAKUL

Quatro gerações, **nenhuma ativa**:

```
VOLC - Orakul - AI Agent - Webgo      ATIVO   4.812 linhas · cron 30 6 * * *   ← só recomenda
  ├── 02 - ORAKUL - Analysis Engine   inativo   esqueleto: motores viraram comentários "cole aqui"
  └── ORAKUL + PredictiveModel v1.0   inativo   arquitetura completa + previsão D+1 + ÁRBITRO
        └── ORAKUL V.OS AUTO ADJUST   inativo   fila de ações priorizada · ÚNICO que já mutou de verdade
GOOGLE ADS - New Campaigns Validation inativo   escola concorrente (NEXUS) — fichas A01–A08
```

**A única geração que já mexeu em dinheiro** é o `orakul-vos-auto-adjust`
("BEAST"), e apenas em 4 dias: **6 execuções, 14 linhas escritas, 12 com payload
de decisão e 10 mutações confirmadas**, entre `2026-02-16 18:30` e
`2026-02-19 18:30`. Depois disso a linha inteira foi desligada — e **não se sabe
por quê** (ver "Perguntas que continuam abertas", no README).

⚠️ Armadilha de medição que quase virou conclusão errada, e que vale para
qualquer auditoria futura: `daily_campaign_metrics.orientacao_gerado_em` tem
`DEFAULT now()`. **92 linhas têm carimbo; só 12 têm decisão.** Quem quiser saber
se o motor rodou precisa contar `orientacao_json IS NOT NULL`, nunca o carimbo.

---

### C01 · Modo de validação por idade: EXPLORATION / CALIBRATION / PRODUCTION

- **Propósito.** Impedir que o otimizador mate uma campanha antes de o algoritmo
  do Google convergir. É a defesa mais importante de todo o legado.
- **Entrada.** `n_completos` = dias de histórico em `daily_campaign_metrics`,
  já descontado o dia parcial.
- **Decisão.** Três faixas, com tetos de corte e histerese distintos:

  | Modo | Faixa | corte máx. de lance | corte máx. de verba | histerese p/ pausar | Trilho B |
  |---|---|---|---|---|---|
  | EXPLORATION | `< 7` dias | −10% | −15% | 5 dias | **desligado** |
  | CALIBRATION | `7–13` dias | −20% | −20% | 3 dias | ligado |
  | PRODUCTION | `≥ 14` dias | −30% | −30% | 3 dias | ligado |

  Constantes de apoio: `AGE_EXPLORATION = 7`, `AGE_CALIBRATION = 14`,
  `MIN_DIAS_OPERACAO = 2`, `MIN_DIAS_ESTATISTICA = 7`, `MIN_DIAS_ESCALA = 5`.
- **Saída.** Não é uma ação: é o **modulador** de todas as outras. Em EXPLORATION
  o "Trilho B" (otimização: escala, mudança de estratégia) fica bloqueado, e a
  ação recebe `gate = "BLOQUEADO: Modo … Trilho B desabilitado"`.
- **Evidência usada.** Nó `🧠 BEAST GOD MODE ENGINE1`, L45–50 e L381–416.
- **Risco.** Baixo, e este é o tipo de regra que **falta** quando se automatiza.
  Um detalhe medido a corrigir: o comentário do próprio código (L79–81) diz
  "0-10 / 10-21 / 21+ dias" e **está errado** — os valores reais são 7 e 14.
- **Reversibilidade.** Total (é um portão).
- **Estado atual.** Inativo. E **nunca foi exercitado em PRODUCTION**: todas as
  execuções medidas ocorreram em CALIBRATION (9 dias de histórico em 19/02), ou
  seja o caminho PRODUCTION/PROVEN/BOOST **nunca rodou**.
- **Conflito com o engine atual.** Nenhum — o VOLC OS não tem laço de decisão.
- **Destino: ① política versionada** — `modo_de_validacao_por_idade`. **Uma das
  cinco regras que mais valem a pena absorver.**

---

### C02 · O lance ancorado no RPC medido — o coração da arbitragem

- **Propósito.** Amarrar o preço que se paga pelo clique ao que o clique
  **rendeu**, e não a uma meta de CPA escolhida por alguém.
- **Entrada.** 15 dias (ORAKUL ativo) ou 30 dias (BEAST) de
  `daily_campaign_metrics`: `revenue_converted_revshare`, `spend`, `clicks`,
  `conversions`, `gam_impressions`. Derivados: `rpc = receita/cliques`,
  `cpc = gasto/cliques`, `spread = rpc − cpc`, `roas = receita/gasto`.
- **Decisão.**
  ```
  cpc_alvo     = rpc_3d × Π(multiplicadores)
  valor        = cpc_alvo                        (estratégia CPC máx.)
  valor        = cpc_alvo / max(cvr_3d, 0.01)    (estratégia tCPA)
  ```
  Os multiplicadores encadeados do BEAST: fase (`LEARNING 0.70`,
  `EARLY_OPTIMIZATION 0.80`, `OPTIMIZATION 0.85`, `SCALING 0.90`); saúde do
  spread (`NEGATIVO_CRITICO ×0.75`, `NEGATIVO_LEVE ×0.90`, `EXCELENTE ×1.05`);
  posicionamento (`×1.08` / `×0.95`); inclinação do spread (`×0.92` / `×1.05`);
  convergência (`RAPIDA ×1.05`, `DIVERGENTE ×0.85`); evento externo (`×0.85`, e
  mais `×0.85` se a queda de eCPM passou de 50%). Fecha com
  `mult = clamp(mult, 0.40, 1.30)`.
- **Saída.** `ADJUST_BID` → `campaigns:mutate` com
  `updateMask: "maximizeConversions.targetCpaMicros"`.
- **Evidência usada.** `🧠 BEAST GOD MODE ENGINE1` L906–998; equivalente em
  `Análise Lance1` (625 linhas) do `atuacao-orakul-ai-agent-webgo`.
- **Risco.** Conceitualmente correto — **`cpc_alvo = rpc × mult` é literalmente
  a definição de arbitragem**. Os riscos são de medição, não de fórmula:
  (a) `rpc` depende de `revenue_converted_revshare`, que depende de
  `exchange_rate_history` — **congelada em 5,25 desde 18/02/2026**, o que torna
  todo `revenue_converted` dos últimos meses suspeito; (b) o run das 18:30 lê um
  dia com custo completo e receita ainda não aterrissada, puxando `rpc_3d` para
  baixo — **viés sistemático de corte à noite e correção de manhã**, sem nenhum
  fator de maturação de receita no código.
- **Reversibilidade.** Média: o valor anterior existe em `base_bid`, mas o log de
  auditoria do BEAST **grava o objeto errado** — medido: uma linha registrou duas
  vezes a mesma ação de R$ 20,28 enquanto `campaigns.budget_amount` ficou em
  R$ 21,97. O valor que vingou não está no log.
- **Estado atual.** Inativo (BEAST). A versão **ativa** (`atuacao-orakul-ai-agent-webgo`)
  calcula a mesma coisa e **só grava recomendação** — não muta nada.
- **Conflito com o engine atual.** Nenhum hoje. **Mas o teto precisa mudar de
  forma**: o `SMART-BIDDING-2026-08-17.md` deriva, de `SPREAD > 0` e
  `CPA = CPC ÷ k`, que **`tCPA_max = RPC ÷ k`** — um teto calculado a partir da
  receita medida, e não uma constante herdada. Com o `k ≈ 0,70` medido na conta,
  `tCPA_max ≈ RPC × 1,43`.
- **Destino: ① política versionada** — `lance_ancorado_no_rpc`. **Uma das cinco
  que mais valem.** Vai como função pura testável, com o teto derivado, e
  **bloqueada enquanto o câmbio e a ingestão de receita não voltarem** — porque
  a fórmula está certa e o insumo, hoje, não está.

---

### C03 · Piso de ROAS para qualquer aumento de lance

- **Propósito.** Uma trava de duas linhas que impede o otimizador de se
  auto-explodir: abaixo de um ROAS mínimo, **o lance nunca sobe**.
- **Entrada.** `roas_3d` e `roas_atual` de `daily_campaign_metrics`.
- **Decisão.** Divergente entre gerações, e é o problema:
  - `atuacao-orakul-ai-agent-webgo` e `orakul-predictive-integrado-v1`:
    `if roas_atual < 1.70 and valor_calculado > base: valor_sugerido = base`
    — piso duro em **1,70**, com regimes `CORRIGIR_MARGEM < 1.30`,
    `ACUMULAR_CAIXA 1.30–1.70`, `ESCALA ≥ 1.70`;
  - `orakul-vos-auto-adjust` (BEAST): faixas
    `ROAS_CRITICO 0.50`, `ROAS_RUIM 0.70`, `ROAS_BREAKEVEN 1.00`,
    `ROAS_SAUDAVEL 1.30`, `ROAS_ESCALA 1.70` — mas escala com `roas_3d ≥ 1.00`,
    e `ROAS_ESCALA` é **declarada e nunca lida**.
- **Saída.** Zera o aumento (mantém o valor de referência).
- **Evidência usada.** `Análise Lance1`; `BEAST GOD MODE ENGINE1` L61–65 e L1253.
- **Risco.** A trava é boa; a **divergência é o risco**. A geração mais nova
  afrouxou o piso de escala de 1,70 para 1,00 sem que isso esteja registrado como
  decisão em lugar nenhum, e ainda deixou a constante antiga no arquivo,
  enganando quem lê.
- **Reversibilidade.** Total (é um veto).
- **Estado atual.** Inativo no BEAST; **ativo** no `atuacao-orakul-ai-agent-webgo`,
  mas só como recomendação.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ① política versionada** — entra dentro de `lance_ancorado_no_rpc`
  como campo explícito `piso_de_roas_para_aumento`, com **um** valor versionado
  e a data da decisão. Hoje o valor é `null` no JSON: **1,70 e 1,00 são as duas
  candidatas medidas, e escolher entre elas é decisão do dono do domínio, não
  minha.**

---

### C04 · Escada de ±30% e guardrail de micro-ajuste (< 5% não mexe)

- **Propósito.** Limitar o tamanho de qualquer passo e eliminar ruído de lance.
- **Entrada.** Valor atual (`target_value` de `campaigns`, ou `cpa_3d`/`cpc_3d`
  como base) e valor calculado.
- **Decisão.** `MAX_BID_STEP = 0.30` e `MAX_BUDGET_STEP = 0.30`; abaixo,
  `MIN_VARIACAO_BID = 0.02` — só age se `|variação| > 2%`. Nos dois árbitros
  (`orakul-predictive-integrado-v1` e `atuacao-orakul-ai-agent-webgo`):
  `minChangePercent = 5` — variação < 5% vira `MANTER` ("micro-ajuste").
- **Saída.** Clampa ou cancela a ação.
- **Evidência usada.** `BEAST` L53–56 e L971–976; `Code in JavaScript2` (árbitro).
- **Risco.** Baixo, e é o tipo de regra que **sempre falta** quando se automatiza.
  Duas incoerências medidas: o limiar de ruído é **2% no BEAST e 5% no árbitro**,
  e `MIN_VARIACAO_BUDGET = 0.05` é **declarada e nunca lida**.
- **Reversibilidade.** Total.
- **Estado atual.** Inativo (BEAST) / ativo mas consultivo (ORAKUL).
- **Conflito com o engine atual.** Nenhum.
- **Destino: ① política versionada** — `escada_de_alteracao`, com **um** limiar
  de ruído versionado e o teto de passo por modo de validação (ficha C01).

---

### C05 · Histerese em contadores de dias consecutivos

- **Propósito.** Exigir que um sinal **persista** antes de virar ação. Elimina a
  maior parte do ruído diário sem precisar de teste estatístico.
- **Entrada.** A série diária ordenada do mais recente para o mais antigo.
- **Decisão.** Quatro contadores independentes, todos "dias consecutivos a partir
  do mais recente, para no primeiro dia que quebra"
  (`contar_dias_negativos` L218 / `contar_dias_acima` L233):

  | contador | condição | usado para |
  |---|---|---|
  | `dias_spread_negativo` | spread < tolerância (`−0.01`) | pausar (≥ 3 ou 5, por modo) |
  | `dias_roas_abaixo_ruim` | roas < `0.70` | cortar verba (≥ 2) |
  | `dias_spread_positivo` | spread > `0.01` | escalar (≥ 2) |
  | `dias_roas_ok` | roas > `1.05` | escalar (≥ 2) |

  Constantes: `HISTERESE_DECREASE_DIAS = 2`, `HISTERESE_PAUSE_DIAS = 5`,
  `HISTERESE_PAUSE_PROD = 3`, `SCALE_HISTERESE_DIAS = 2`, `SCALE_MIN_ROAS = 1.05`,
  `SCALE_SPREAD_MIN = 0.01`.
- **Saída.** Zera a ação quando a histerese não bate (L996–997).
- **Evidência usada.** `BEAST GOD MODE ENGINE1` L92–94, L218, L233.
- **Risco.** Baixo. Um defeito medido: o "relaxamento" da escala (L1270) na
  prática **não relaxa nada** — reexige `dias_spread_positivo >= 2`.
- **Reversibilidade.** Total.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ① política versionada** — `histerese_de_dias_consecutivos`.
  **Uma das cinco que mais valem**, e a mais barata de implementar.

---

### C06 · Piso de verba + teto de perda (budget floor e loss cap)

- **Propósito.** Apostar sem quebrar: limitar a perda diária **sem** zerar o
  aprendizado que o algoritmo do Google já acumulou.
- **Entrada.** `budget_amount` de `campaigns`; `spend` e receita do dia e dos
  últimos 3 dias.
- **Decisão.**
  ```
  budget_floor = max(budget_atual × 0.30, min(10.0, budget_atual))
  max_loss_day = budget × 0.30        (0.45 se a campanha for `proven`)
  max_loss_3d  = budget × 3 × 0.60    (0.75 se `proven`)
  proven = PRODUCTION e roas_7d ≥ 1.20 e spread_7d > 0 e sem loss cap 3d e sem evento
  ```
  Estourar o cap do dia dispara throttle de −15% (EXPLORATION) ou −25%; e no
  bloco de conflitos (L1481–1485) **remove todo `ADJUST_BUDGET` INCREASE da fila**.
- **Saída.** `ADJUST_BUDGET` (LOSS_CAP_THROTTLE), prioridade 2 → `campaignBudgets:mutate`.
- **Evidência usada.** `BEAST` L84–85, L395–396, L619–633, L834, L1481–1485.
- **Risco.** Baixo, e o desenho é bom: **perda controlada com piso de
  aprendizado**. Um risco não tratado: o cap é sobre perda **medida**, e a
  receita do dia corrente chega atrasada — ver ficha C08.
- **Reversibilidade.** Alta: verba volta a subir sozinha quando o sinal melhora.
- **Estado atual.** Inativo. O caminho `proven` **nunca foi exercitado**.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ① política versionada** — `piso_de_verba_e_teto_de_perda`.
  **Uma das cinco que mais valem.**

---

### C07 · Zombie hunter — gastou e não devolveu nada

- **Propósito.** Cortar a campanha que queima verba com receita **zero**.
- **Entrada.** `m_d0['spend']` e `m_d0['revenue']` do dia corrente.
- **Decisão.** `spend > 15.0 and revenue == 0`. Em EXPLORATION vira throttle de
  −20%; em CALIBRATION, −30% (respeitando o floor); em **PRODUCTION vira
  `PAUSE_CAMPAIGN` prioridade 1** — e P1 executável, pelo passo 2 do bloco de
  conflitos, **descarta todas as outras ações da fila**.
- **Saída.** `ADJUST_BUDGET` ou `PAUSE_CAMPAIGN`.
- **Evidência usada.** `BEAST` L771 e L1468.
- **Risco.** ⚠️ **UNIVERSAL DEMAIS**, e é o exemplo canônico de *"sem conversão
  em um dia significa campanha ruim"* — agravado por um artefato de medição
  documentado no próprio inventário: **às 18:30 o D0 é classificado
  `QUASE_COMPLETO` e entra nas janelas**; se o gasto já passou de R$ 15 e a
  receita do GAM/AdSense do dia ainda não aterrissou, a condição é **verdadeira
  por atraso de dado, não por desempenho**. O acaso que salvou a operação é a
  pausa não ter executor de API (ficha D07).
- **O que faltaria.** (a) **Atraso de receita explícito**: a condição só pode
  olhar dias com receita fechada; (b) janela ≥ 2 dias, não 1; (c) o R$ 15 tem de
  virar fração da verba, não constante; (d) confirmação de que a ingestão de
  receita **rodou** para aquele dia — hoje falha de ETL é indistinguível de
  receita zero; (e) rollback: reativar automaticamente se a receita aterrissar.
- **Reversibilidade.** Baixa: pausa é fácil de desfazer, mas o aprendizado do
  algoritmo não volta.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ① política versionada** — `zumbi_gasto_sem_receita`, com os cinco
  consertos acima e **saída de defesa por throttle, nunca pausa automática** em
  primeira instância.

---

### C08 · O dia parcial não decide

- **Propósito.** Impedir que o dia corrente, incompleto, entre nas janelas de
  cálculo e envenene a média.
- **Entrada.** Hora local (`now_br() = utcnow() − 3h`), cliques do dia e média
  de cliques.
- **Decisão.** Antes das **15h** o dia corrente é `PARCIAL`/`VAZIO` e é
  **descartado**; depois das 15h vira `QUASE_COMPLETO` se tiver ≥ **40%** dos
  cliques médios **ou** > 10 cliques, e **entra** nas janelas 3d/7d/14d
  (`HORA_CORTE_DIA_CONFIAVEL = 15`, `PCT_MIN_CLICKS_DIA_PARCIAL = 0.40`).
- **Saída.** Define `n_completos` e o conteúdo das janelas.
- **Evidência usada.** `BEAST` L107–108 e L179–215.
- **Risco.** A **ideia** é certa e rara; a **execução é assimétrica e é a raiz de
  dois defeitos**. O corte olha só o lado da compra (cliques). Custo do Google
  Ads chega quase em tempo real; receita de GAM/AdSense, não. Admitir o dia
  parcial com custo completo e receita incompleta é o que produz o viés de queda
  das 18:30 (ficha C02) e o falso zumbi (ficha C07).
- **Reversibilidade.** Total.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** **Convergência de doutrina.** O VOLC OS já
  distingue provisório de fechado e recusa número sem frescor:
  `backend/app/trafego/inventario.py` — *"Nenhum número sem frescor"*, com
  `Entrega.__post_init__` levantando exceção, e *"Ausência é `None`, nunca zero"*.
- **Destino: ① política versionada** — `dia_parcial_nao_decide`, corrigida para
  **exigir maturidade das DUAS pernas** (custo e receita) antes de o dia entrar
  na janela, e não só da perna da compra.

---

### C09 · Escala por impression share perdido, quantificada em reais

- **Propósito.** Traduzir "estou perdendo impressão" em **quanto dinheiro por
  dia** isso vale, para decidir se compensa escalar.
- **Entrada.** `search_impression_share`,
  `search_budget_lost_impression_share`, `search_rank_lost_impression_share`,
  cliques/dia e spread.
- **Decisão.** `roas_3d ≥ 1.00` **e** `lost_rank + lost_budget > 0.40` **e**
  `spread > 0`, com histerese de 2 dias bons. E a quantificação:
  ```
  clicks_potenciais = clicks/dia × total_perdido × 0.40
  lucro_potencial   = clicks_potenciais × spread
  ```
  Subida de verba: `pct_up = min(lost_budget × 0.5, teto)`, com teto por perfil
  (`EXPLORATION 0.20`, `GROWTH 0.30`, `BLITZ+PROVEN 0.40`).
- **Saída.** `SCALE_OPPORTUNITY` (informativo) + par executável
  `ADJUST_BUDGET`/`ADJUST_BID`.
- **Evidência usada.** `BEAST` L1253–1270; `IS_LOST_THRESHOLD = 0.30`,
  `SCALE_*_MAX` L40–42.
- **Risco.** O **fator 0,40** ("só 40% do share perdido é recuperável") é um
  chute não documentado — mas é um chute **conservador e declarado**, o que é
  diferente de um chute escondido. O defeito real é outro, e foi medido: **duas
  ações `ADJUST_BUDGET` INCREASE podem sobreviver na mesma execução e ambas são
  executadas** — em 19/02/2026 a campanha `23518661646` gerou `+30% → R$ 21,97`
  pela AÇÃO 3a **e** `+20% → R$ 20,28` pela AÇÃO 7, ambas `executavel: true`. O
  bloco de conflitos só resolve INCREASE-vs-DECREASE. Duas mutações no mesmo
  `campaignBudget`, e ninguém sabe qual venceu.
- **Reversibilidade.** Média.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ① política versionada** — `escala_por_impression_share_perdido`,
  com **desduplicação por tipo de recurso alvo** (uma ação por `campaignBudget`
  por execução, sempre) e o fator de recuperabilidade como parâmetro versionado,
  não literal.

---

### C10 · O ÁRBITRO — o motor propõe, o árbitro veta

- **Propósito.** Separar quem calcula de quem decide. Foi **removido**
  deliberadamente na geração mais nova, e a remoção piorou o sistema.
- **Entrada.** As saídas dos dois motores (financeiro e comportamental) + a
  previsão D+1, quando existe.
- **Decisão.** Contrato do `orakul-predictive-integrado-v1`:
  ```js
  cooldownHours = 24;  minChangePercent = 5;
  emergencia    = roas3d > 0 && roas3d < 1.30      // ignora cooldown e micro-ajuste
  blockIncrease = insight ALTA || momentum CVR baixa_* || anomalia ALTA
               || gargalo GAM ALTA || (previsao && roas_previsto < 1.30)
  if (!emergencia) { if (inCooldown) aplicar=false; if (isMicro) aplicar=false; }
  if (!emergencia && blockIncrease && isIncrease) aplicar=false;
  if (!aplicar) valorFinal = valorRef;              // "MANTER"
  risco = emergencia ? ALTO : blockIncrease ? MEDIO : BAIXO
  ```
  Cada veto vira uma string em `motivos[]` — **auditabilidade sem esforço**.
  Note a assimetria correta: `blockIncrease` **só barra aumento**; redução passa.
- **Saída.** `orientacao_json.decisao{acao, aplicar, valor_sugerido, risco, motivos}`.
- **Evidência usada.** Nó `Árbitro (Integrado com Prediction)` (227 linhas);
  `Code in JavaScript2` (236 linhas) no flow ativo.
- **Risco.** O desenho é o melhor artefato conceitual do legado. O defeito é de
  insumo: **`last_bid_change_at` não existe** em `campaigns` nem em
  `daily_campaign_metrics`, então **o cooldown de 24h anunciado em `motivos[]`
  nunca foi exercido**. O árbitro diz ao operador que houve uma trava que não
  houve.
- **Reversibilidade.** N/A (é um veto).
- **Estado atual.** **Ativo** dentro do `atuacao-orakul-ai-agent-webgo` — e é o
  campo `risco` deste bloco que pinta a caixa vermelha no dashboard.
- **Conflito com o engine atual.** Nenhum, mas é exatamente o que a prioridade 9
  da curadoria pede: *"Recomendação tem versão/razão; autorização tem dono; ação
  tem recibo e verificação."*
- **Destino: ① política versionada + ② job.** O árbitro vira **função pura
  testável** separada do motor, com `motivos[]` obrigatório e cooldown lido de
  uma tabela de atuações reais (ficha A08). É a **forma** em que as demais
  políticas se encaixam.

---

### C11 · A fila de ações priorizada (`executavel_base` vs `executavel`)

- **Propósito.** Estrutura de saída do BEAST: cada regra **deposita** uma ação
  com prioridade e justificativa, e um bloco final resolve conflitos — em vez de
  um `if/else` gigante escolher uma.
- **Entrada.** Todas as regras do motor.
- **Decisão.** Cada ação carrega `tipo`, `prioridade`, `params`, `razao`,
  `condicoes_satisfeitas`, `gate`, `trilho`, `executavel_base`, `executavel`, com
  `executavel_base = (prioridade <= 3) and not gate.startswith("BLOQUEADO")`.
  Resolução (L1462–1500): ordena por prioridade; se há PAUSE executável descarta
  o resto; resolve INCREASE-vs-DECREASE; remove INCREASE se o loss cap disparou;
  aplica cooldown com bypass de prioridade 1.
- **Saída.** Lista de ações, das quais **só 3 dos 11 tipos têm executor** — e um
  deles (PAUSE) é e-mail.
- **Evidência usada.** `BEAST` `add_acao` L664–696 e bloco 9 L1462–1500.
- **Risco.** **Separar `executavel_base` (mérito) de `executavel` (permissão
  temporal) é o design certo** — permite mostrar ao operador *por que* uma ação
  não rodou. Dois defeitos medidos: o bloco de cooldown é **código morto**
  (`ultima_acao` nunca é preenchida, então `em_cooldown` é sempre `False`), e a
  ordenação por prioridade é estável mas **não determinística por tipo** em
  empate — quem vence depende da ordem de inserção, que ninguém documentou.
- **Reversibilidade.** N/A.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ② job que chama o backend canônico.** A fila é **arquitetura**, não
  política: vira uma tabela `campaign_actions` e uma API `POST /decide` que
  devolve a fila **sem executar nada**. Regra que vem junto e não é negociável:
  cada ação carrega um `action_id`, e a resposta da API é gravada **contra esse
  id** — não recuperada varrendo nós, que é a causa direta do log de auditoria
  errado (ficha C02).

---

### C12 · Redistribuição de verba entre campanhas — e a lição de contrato que ela deixa

- **Propósito.** Tirar verba de quem rende menos e dar a quem rende mais.
- **Entrada.** `all_campaigns_summary` — a visão do portfólio.
- **Decisão.** `roas_3d < média_das_outras × 0.70` **e** `< 0.80` ⇒
  `REDISTRIBUTE_BUDGET`, prioridade 3.
- **Saída.** Nenhuma. **A ação nunca dispara.**
- **Evidência usada.** `BEAST` L12–22 e L1229. O nó anterior
  (`Code in JavaScript`) só emite `campaign_id`, `campaign_config` e
  `daily_metrics` — `all_campaigns_summary` e `last_action` são **declarados e
  nunca alimentados**.
- **Risco.** O risco **é a lição**: um motor que declara entradas e degrada em
  silêncio quando elas faltam produz duas mortes invisíveis — a AÇÃO 6 nunca
  dispara **e** o cooldown de 10h nunca ativa. Nada no log diz isso.
- **Reversibilidade.** N/A.
- **Estado atual.** Inativo, e morto mesmo quando ativo.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ⑤ decidir depois.** *A pergunta exata:* **a otimização de portfólio
  (mover verba entre campanhas do mesmo projeto) é escopo do motor de autogestão
  do VOLC OS, ou é decisão humana de alocação?** Enquanto não houver resposta, a
  regra fica fora. O que **entra agora**, independente da resposta: **o contrato
  de entrada do motor deve ser um schema validado que FALHA se faltar campo**, em
  vez de degradar para "sem cooldown".

---

# D · Anomalia, alerta e contenção

---

### D01 · Anomalia por z-score

- **Propósito.** Detectar o dia que foge do próprio histórico da campanha, sem
  limiar absoluto.
- **Entrada.** Série de 7 a 14 dias de ROAS, SPREAD, CVR, eCPM, CPC, match_rate.
- **Decisão.** `abs(z) > 2.0` no BEAST (≥ 7 dias exigidos); `|z| > 2.5` nos
  `Motor 2 Insigths` / `Motor Insights AdSense` (mínimo **7 dias**, senão devolve
  erro). Severidade `ALTA` alimenta o `blockIncrease` do árbitro (ficha C10).
- **Saída.** `ANOMALY_ALERT`, prioridade 2 ou 3 — **sem executor**. É sinal, não
  ação. Isso está certo.
- **Evidência usada.** `BEAST` L562; `Motor 2 Insigths` (556 linhas).
- **Risco.** ⚠️ **UNIVERSAL DEMAIS na amostra, não no conceito.** Z-score sobre
  **7 pontos** é frágil: o desvio-padrão amostral é instável e a própria
  observação anômala entra no cálculo do desvio, mascarando-se. E os dois
  limiares (2,0 e 2,5) divergem sem justificativa registrada.
- **O que faltaria.** Amostra mínima maior ou estimador robusto (mediana e MAD
  em vez de média e desvio); excluir a observação avaliada do cálculo da base;
  **um** limiar versionado; e — o mais importante — separar "anômalo" de
  "acionável", que o desenho já faz ao não dar executor ao alerta.
- **Reversibilidade.** Total (é sinal).
- **Estado atual.** Ativo (consultivo) no `atuacao-orakul-ai-agent-webgo`;
  inativo no BEAST.
- **Conflito com o engine atual.** Nenhum. O VOLC OS tem alertas de **entrega**
  (`backend/app/trafego/alertas.py`), não de **desvio estatístico**.
- **Destino: ① política versionada** — `anomalia_por_desvio`, com estimador
  robusto e amostra mínima declarada. Saída **sempre** informativa; anomalia
  pode **vetar aumento**, nunca **causar corte** sozinha.

---

### D02 · Evento externo pelo desacoplamento compra × venda

- **Propósito.** Distinguir "meu leilão piorou" de "o mercado de display caiu" —
  e não punir a campanha por um problema que não é dela.
- **Entrada.** Os dois dias mais recentes: eCPM do lado venda e CPC do lado
  compra.
- **Decisão.** `queda_ecpm < −0.20` **e** `|Δcpc| < 0.15` ⇒ `evento_externo = True`
  (`QUEDA_ECPM_EVENTO = −0.20`).
  Efeitos, todos no sentido de **segurar a mão**: tolerância de spread relaxa de
  `−0.01` para `−0.05`; `histerese_pause += 2`; `mult *= 0.85` (mais `×0.85` se a
  queda passou de 50%); a pausa vira `"ADIADO: Evento externo detectado"`; cortes
  de verba limitados a 15%; escala executável bloqueada.
- **Saída.** `EVENTO_EXTERNO`, prioridade 2, sem executor — modula todo o resto.
- **Evidência usada.** `BEAST` L521–558, L67, L103–104.
- **Risco.** Baixo. É simples, barato e **é exatamente o diagnóstico que um
  operador humano faria**: se o preço que eu pago não mudou e o preço que eu
  recebo caiu, o problema está do outro lado do mercado. Limitação real: é
  calculado **por campanha**, quando o fenômeno é **global** — dez campanhas
  detectam o mesmo evento dez vezes, e uma campanha com pouco volume pode não
  detectar um evento que existe.
- **Reversibilidade.** Total.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ① política versionada + ② job.** `evento_externo_desacoplamento`.
  **Uma das cinco que mais valem** — e com uma correção de escopo: deve ser um
  **serviço de mercado**, avaliado uma vez por dia sobre o portfólio e consumido
  por todas as campanhas, não recalculado por campanha.

---

### D03 · Desfibrilador — quando o inventário não carrega, o RPC observado é falso

- **Propósito.** Reconhecer que um RPC baixo pode ser falha de **entrega de
  anúncio**, não falta de valor do clique — e nesse caso cortar o lance é o
  remédio errado.
- **Entrada.** `match_rate` (GAM) ou `spread` (AdSense) de D-1 e D-2.
- **Decisão.** Duas variantes com **sinais opostos**:
  - **GAM** (`Análise Lance1`): `match_rate` em D-1 **e** D-2 < **70,0%** ⇒
    `SUPORTE_DE_VIDA`, e **infla** o lance por `min(95.0 / match_atual, 2.0)` —
    até dobrar — "para manter CPC estável";
  - **AdSense** (`Motor Lance AdSense`): `spread` em D-1 **e** D-2 < **0,005** ⇒
    `SUPORTE_DE_VIDA`, e **reduz** o lance em 30% (`× 0.7`). O `fator_compensacao`
    é calculado e **nunca usado** — cicatriz de copy-paste do ramo GAM.
- **Saída.** Multiplica o lance sugerido.
- **Evidência usada.** `Análise Lance1` e `Motor Lance AdSense` do
  `atuacao-orakul-ai-agent-webgo`.
- **Risco.** A **ideia GAM é uma joia** e o BEAST a perdeu — é uma regressão
  registrada. Mas inflar o lance até **2×** quando a monetização está quebrada é
  a aposta mais agressiva de todo o legado, feita **exatamente no momento de
  maior incerteza**. E as duas variantes contradizem-se: mesma situação
  conceitual (a venda não está entregando), remédios opostos.
- **O que faltaria.** Provar que `match_rate` baixo é transitório antes de
  compensar; teto de compensação bem menor que 2×; e **decidir qual das duas
  escolas está certa** — hoje o arquivo não decide.
- **Reversibilidade.** Média.
- **Estado atual.** **Ativo** (consultivo) no `atuacao-orakul-ai-agent-webgo`.
- **Conflito com o engine atual.** Nenhum, e há um bloqueio de fato: `gam_metrics`
  tem **0 linhas** no self-hosted, então `match_rate` não existe para ser lido.
- **Destino: ⑤ decidir depois.** *A pergunta exata:* **quando `match_rate` cai
  abaixo do piso, o lance deve ser compensado para cima (tese GAM) ou contido
  para baixo (tese AdSense)?** Só há uma forma honesta de responder: medir o que
  aconteceu com o spread nos episódios reais. Enquanto `gam_metrics` estiver
  vazia, isso não é respondível — e por isso a regra fica fora do JSON canônico,
  com o campo reservado.

---

### D04 · Momentum 3d × 14d e gargalos de monetização

- **Propósito.** Ler tendência sem série temporal formal: comparar a janela curta
  com a longa.
- **Entrada.** CVR, ROAS e spread em 3 e 14 dias; `match_rate` e `fill_rate` do GAM.
- **Decisão.** "Metodologia Felipe": `CVR3d ≥ 95% de CVR14d` = estável/alta;
  `≥ 85%` = `baixa_moderada`; abaixo = `baixa_severa` (ROAS usa `0.90`).
  Gargalos GAM: `match_rate 3d < 85` (ALTA se `< 75`), `fill_rate 3d < 70`
  (ALTA se `< 60`). Eficiência CPA vs tCPA: `< 0.7×` under-delivery severo,
  `< 0.85×` under, `> 1.15×` over, `> 1.3×` over severo.
- **Saída.** Insights que alimentam `blockIncrease` no árbitro.
- **Evidência usada.** `Motor 2 Insigths` / `Motor Insights AdSense`.
- **Risco.** Razão de médias sobre janelas sobrepostas (3d está **dentro** de
  14d) atenua o sinal e não tem intervalo de confiança. As faixas 0,95/0,85 são
  redondas e não derivadas. Mas a saída é **veto de aumento**, não corte — o que
  torna o erro barato.
- **Reversibilidade.** Total.
- **Estado atual.** Ativo (consultivo).
- **Conflito com o engine atual.** Nenhum.
- **Destino: ⑤ decidir depois** para as faixas; **① política versionada** só para
  a **forma**: "tendência é veto de aumento, nunca causa de corte". A régua
  numérica fica `null` até haver janela não sobreposta e uma medição que a
  justifique.

---

### D05 · `confidence_score` e `proxima_revisao_horas`

- **Propósito.** Dizer **quanta fé** ter na recomendação e **quando voltar a
  olhar** — barato e útil para priorizar fila humana.
- **Entrada.** Tamanho do histórico, volume de conversões, volatilidade do
  spread, saúde da monetização.
- **Decisão.** Quatro fatores (0,25 / 0,15): ≥ 14 dias de histórico; > 100
  conversões em 14d; volatilidade de spread < 0,01; saúde (`match > 95 &&
  fill > 97` no GAM; `spread_3d > 0.02` no AdSense). `proxima_revisao_horas`:
  **6h** se ROAS < 1,30; **12h** em escala; **18h** se ROAS < 1,50; senão **24h**.
- **Saída.** Campos do `orientacao_json` que o front consome.
- **Evidência usada.** `Análise Lance1`; gerador de orientação v2.1.
- **Risco.** Baixo. Não é confiança estatística — é um **índice de completude de
  evidência**, e chamá-lo de "confidence" confunde. Renomeado, é útil.
- **Reversibilidade.** Total.
- **Estado atual.** Ativo (consultivo).
- **Conflito com o engine atual.** **Convergência** com a doutrina de frescor e
  procedência de `backend/app/trafego/inventario.py`.
- **Destino: ① política versionada** — entra como **campo obrigatório de toda
  recomendação** (`confianca` no JSON canônico), renomeado para
  `completude_da_evidencia`, com os quatro fatores explícitos.

---

### D06 · eCPM degradando (tendência do lado venda)

- **Propósito.** Avisar que a monetização está caindo de forma sustentada, o que
  invalida o RPC usado como âncora do lance.
- **Entrada.** Série de eCPM do lado venda.
- **Decisão.** `slope(ecpm_sell) < −2.0` **e** sem evento externo detectado ⇒
  `ECPM_DEGRADING`, prioridade 3.
- **Saída.** Alerta, sem executor.
- **Evidência usada.** `BEAST` L1444.
- **Risco.** O limiar `−2.0` é uma inclinação **em unidade absoluta de eCPM**, o
  que o torna dependente do patamar: −2,0 sobre eCPM de 40 é ruído; sobre eCPM de
  4 é colapso. Deveria ser relativo.
- **Reversibilidade.** Total.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum. Bloqueado de fato pela ausência de
  dados de GAM.
- **Destino: ① política versionada** — dentro de `anomalia_por_desvio`, com
  inclinação **relativa ao patamar**, e limiar `null` até haver série medida.

---

### D07 · Pausa é humana — não existe executor de pausa em lugar nenhum

- **Propósito.** Não é uma regra deliberada; é um **fato do legado** que vale
  registrar como decisão implícita da casa.
- **Entrada.** N/A.
- **Decisão.** `PAUSE_CAMPAIGN`, quando chega a prioridade 1, dispara **um e-mail
  pelo Gmail** para `tarcisio@agenciavolc.com.br`. **Não existe chamada de API
  para pausar em nenhum dos 17 flows de mídia.** O `🔀 SABM Splitter` roteia só
  `ADJUST_BID`, `ADJUST_BUDGET` e `PAUSE_CAMPAIGN`, e o último cai em e-mail.
- **Saída.** E-mail.
- **Evidência usada.** Nó `Send a message` do `orakul-vos-auto-adjust`;
  varredura dos 17 flows por `campaigns:mutate` com `status` — nenhuma ocorrência.
- **Risco.** Este acaso **salvou a operação**: sem executor de pausa, o falso
  zumbi das 18:30 (ficha C07) nunca matou uma campanha por atraso de receita.
- **Reversibilidade.** N/A.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum, e **a doutrina deve ser preservada**.
- **Destino: ① política versionada** — vira regra explícita em vez de acidente:
  **pausa de campanha exige aprovação humana**; a defesa automática permitida é
  throttle de verba com piso (ficha C06). Escrita como
  `aprovacao_humana_obrigatoria` nas políticas de contenção.

---

# E · Termos de busca, keywords e negativas

Fonte única: `gads-search-terms-upgrade-kw` ("KW Optmization - Search Terms
upgrade", 23 nós, 636 linhas). **Estado: inativo** desde `2026-02-19T23:47:16Z`
— o mesmo dia em que o BEAST foi desligado. Gatilho: cron `0 6 * * *`.
Era **o único robô que escrevia sozinho no Google Ads** sem humano no meio.

---

### E01 · O tribunal em estágios — a máquina de estados

- **Propósito.** Decidir, todo dia, o destino de cada raiz de termo de busca:
  proteger, promover, reter, condenar ou adiar.
- **Entrada.** Duas GAQL v21: `search_term_view` com
  `metrics.impressions > 1 AND segments.date DURING LAST_7_DAYS` (janela de **7
  dias**), e `keyword_view WHERE ad_group_criterion.status = 'ENABLED'` — **sem
  filtro de data, a conta inteira** — para montar a "zona verde".
- **Decisão.** Cinco estágios, em ordem, e cada `continue` encerra o julgamento:
  1. **Zona verde** — já é keyword ativa **e** (0 conversões **ou** CPA ≤ 5,00):
     intocável;
  2. **Com conversão** — CPA > 5,00 ⇒ `🧟 ZUMBI` (negativa + pausa da keyword
     homônima); senão avalia promoção;
  3. **Retenção** — `CTR ≥ 8% && clicks ≥ 2 && custo < 1,50` ⇒ deixa viver;
  4. **Zona vermelha** — `🧛 VAMPIRO`, `👻 FANTASMA`, `❌ LIXO` (ficha E02);
  5. **Limbo** — nada; roda de novo amanhã.
- **Saída.** Três `mutate` e um e-mail (ficha E02).
- **Evidência usada.** Nó `🧠 Analisa e Decide2` ("MINING BRAIN v10.1").
- **Risco.** **A máquina de estados é boa**: ordem explícita, proteção antes de
  punição, e um estado "limbo" que assume ignorância em vez de forçar decisão. O
  defeito estrutural está no agrupamento (ficha E06), não aqui.
- **Reversibilidade.** Negativa é reversível (remover o critério); a keyword
  pausada é reversível; o **aprendizado perdido**, não.
- **Estado atual.** Inativo desde 19/02/2026.
- **Conflito com o engine atual.** Nenhum — o VOLC OS não lê `search_term_view`.
- **Destino: ② job que chama o backend canônico.** A máquina de estados vale, mas
  **em SQL sobre uma tabela `search_terms` materializada**, não em JS dentro de
  um nó. O agendamento pode ficar no n8n (ADR-05); a decisão, não.

---

### E02 · Zona vermelha — vampiro, fantasma e lixo

- **Propósito.** Nomear os três modos de queimar verba sem retorno.
- **Entrada.** Métricas agregadas por raiz, janela de 7 dias.
- **Decisão.** Nesta ordem:
  - `🧛 VAMPIRO`: `clicks ≥ 3 && custo ≥ 1,50 && conv == 0`
    (`VAMPIRE_MIN_CLICKS: 3`, `VAMPIRE_COST_BRL: 1.50`);
  - `👻 FANTASMA`: `imps ≥ 100 && clicks == 0` (`GHOST_IMPS: 100`);
  - `❌ LIXO`: `imps ≥ 50 && CTR < 0,5%` (`MIN_IMPRESSIONS_NEGATE: 50`,
    `CTR_NEGATE_THRESHOLD: 0.5`).
- **Saída.** `campaignCriteria:mutate` com
  `{keyword:{matchType:'EXACT', text}, negative:true}` — negativa em **nível de
  campanha**.
- **Evidência usada.** Objeto `THRESHOLDS` do nó `🧠 Analisa e Decide2`,
  transcrito do JSON em 26/08.
- **Risco.** ⚠️ **UNIVERSAL DEMAIS nas três amostras.** 3 cliques não decidem
  conversão; 100 impressões não decidem CTR; 50 impressões, menos ainda. Com CVR
  real de 0,7 (o `k` medido na casa), **3 cliques sem conversão têm probabilidade
  de ~2,7% se a keyword for boa** — mas com CVR de 5%, é ~86%, e a mesma regra
  condena keywords saudáveis. A régua não sabe qual dos dois mundos está olhando.
  Agravante operacional medido: **nenhum dos três `mutate` envia
  `partialFailure: true`** — a API do Google Ads é atômica por padrão, então
  **uma** operação inválida (duplicata, caractere proibido, keyword > 80 chars)
  derruba o lote inteiro. Um dia ruim = zero negativas, silenciosamente.
- **O que faltaria.** Amostra mínima derivada da CVR observada do ad group, não
  constante; atraso de conversão explícito (a janela de lookback da conversão da
  casa é **1 dia** — `clickThroughLookbackWindowDays: 1` —, o que é curto e ajuda,
  mas precisa estar declarado); `partialFailure: true` sempre; e registro linha a
  linha do resultado.
- **Reversibilidade.** Média: a negativa é removível, mas **nada registra o que
  foi negativado** além de um e-mail.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ① política versionada** — `negativa_de_termo_de_busca`, com amostra
  mínima **derivada** (campo `null` no JSON até haver a medição), `partialFailure`
  obrigatório e tabela de auditoria por operação.

---

### E03 · O ZUMBI — CPA acima de R$ 5,00 mata a keyword mesmo convertendo

- **Propósito.** Impedir que uma keyword que converte, mas caro, sobreviva por
  ter conversão.
- **Entrada.** Conversões e custo agregados por raiz.
- **Decisão.** Com conversão **e** `CPA > 5,00` ⇒ `🧟 ZUMBI`: negativa **e**
  agenda pausa da keyword homônima.
- **Saída.** `campaignCriteria:mutate` (negativa) + `adGroupCriteria:mutate`
  update `status: 'PAUSED'`.
- **Evidência usada.** `THRESHOLDS.MAX_CPA_BRL: config.MAX_CPA_BRL || 5.00` —
  e o `config` **não define `MAX_CPA_BRL`**, então cai sempre no literal.
- **Risco.** ⚠️ **UNIVERSAL DEMAIS — este é o caso-livro de *"CPA acima de X
  pausa"*.** Três problemas: (a) R$ 5,00 é uma constante enterrada num literal,
  apesar de o `|| 5.00` sugerir que é configurável — é a regra mais destrutiva do
  workflow e a menos visível; (b) o teto correto **não é um número, é uma
  função**: pela identidade da casa, `SPREAD > 0 ⟺ CPA < RPC ÷ k`; com o `k ≈
  0,70` medido, o teto é `RPC × 1,43` — e **os CPAs reais medidos foram R$ 0,099,
  R$ 0,083 e R$ 0,246**, ou seja **vinte a cinquenta vezes abaixo do teto**, o
  que sugere que R$ 5,00 nunca disparou e ninguém percebeu; (c) matar uma keyword
  que converte é a decisão mais cara possível, e ela está tomada por um literal.
- **O que faltaria.** Substituir a constante pela derivação `RPC ÷ k`, com RPC e
  k medidos por ad group; amostra mínima de conversões; janela ≥ 7 dias; e
  saída de **revisão humana**, não negativa automática.
- **Reversibilidade.** Baixa: negativa + pausa da keyword no mesmo passo, sem
  registro estruturado.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum, mas a **derivação já está escrita** em
  `inventario-n8n/sistema-atual/SMART-BIDDING-2026-08-17.md` §6.
- **Destino: ① política versionada**, reescrita — entra como
  `teto_de_cpa_derivado_do_rpc`, com o número literal **removido** e o teto
  calculado. Saída: fila humana.

---

### E04 · Promoção GOLD — de termo de busca a keyword PHRASE

- **Propósito.** Transformar descoberta em performance: o que converte barato no
  BROAD vira keyword própria.
- **Entrada.** Métricas por raiz + o mapa de keywords já ativas.
- **Decisão.** `conv ≥ 2 && clicks ≥ 5 && CTR ≥ 8% && CPC ≤ 0,40 && CPA ≤ 5,00`
  e **não** ser keyword existente (`GOLD_MIN_CONVERSIONS: 2`,
  `GOLD_MIN_CLICKS: 5`, `GOLD_CTR: 8.0`, `GOLD_MAX_CPC: 0.40`).
- **Saída.** `adGroupCriteria:mutate` `create` com
  `{keyword:{matchType:'PHRASE', text: cleanText}, status:'ENABLED'}`.
- **Evidência usada.** `THRESHOLDS` e o nó `💎 Prepara Promoções1`, que descarta
  itens sem `adGroupResource` e termos com mais de 10 palavras.
- **Risco.** ⚠️ **UNIVERSAL DEMAIS na amostra** — promover com **5 cliques e 2
  conversões** é promover ruído. Mas o erro aqui é **barato e reversível**, ao
  contrário do da ficha E03: uma keyword PHRASE nova entra com o lance do ad
  group e pode ser pausada. Defeito operacional medido: `existingKWs` guarda o
  texto **com acento** e a promoção grava `cleanText` **sem acento** — "pé de
  meia" nunca casa com a keyword existente "pe de meia", então o flow **tenta
  criar a duplicata todo dia** e, combinado com a ausência de `partialFailure`,
  **mata o lote de promoções inteiro, diariamente**.
- **Reversibilidade.** Alta.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum. O VOLC OS já **normaliza sem acento**
  para comparação em `volc_ads/campanha/validacao.py` (`_normalizar`, L76) e
  recusa duplicata por chave normalizada em `checar_lista` (L91) e
  `checar_keywords` (L131) — exatamente o defeito que quebra o legado.
- **Destino: ① política versionada** — `promocao_de_termo_para_keyword`, com
  amostra mínima declarada, comparação **normalizada** (reusando
  `validacao._normalizar`) e `partialFailure` obrigatório.

---

### E05 · Despromoção acoplada à negativa

- **Propósito.** Coerência: se um termo foi condenado e ele também é keyword
  ativa, a keyword tem de sair junto — senão a negativa não surte efeito.
- **Entrada.** O mapa `texto → resourceName` das keywords ativas.
- **Decisão.** `scheduleDepromoteIfNeeded`: ao negativar um termo que é keyword
  ativa, empurra o `resourceName` para `toDepromote`.
- **Saída.** `adGroupCriteria:mutate` `update {status:'PAUSED'}` com
  `updateMask:'status'` — **o comentário do código diz "REMOVER", o código pausa**.
- **Evidência usada.** Nó `📤 Mutate Depromote KWs`.
- **Risco.** A lógica é correta e necessária. O defeito é de encanamento e é
  grave para auditoria: **`📤 Mutate Depromote KWs` é folha órfã** — não tem
  conexão de saída, e `📦 Empacota Negativas1` lê o resultado dele dentro de um
  `try{}catch(e){}` **vazio**. Com `executionOrder: v1` não há garantia de que
  esse ramo já executou; se não executou, o `catch` engole e o relatório diz
  `depromoteApplied: 0` **mesmo tendo pausado keywords**. O sistema mente sobre o
  que fez.
- **Reversibilidade.** Alta (despausar), se alguém souber o que foi pausado — e
  hoje ninguém sabe.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ① política versionada** — vai junto de `negativa_de_termo_de_busca`
  como **efeito obrigatório e transacional**: negativar um termo que é keyword
  ativa e não pausar a keyword é um estado inconsistente que a política proíbe.

---

### E06 · O stemming que junta o que não deveria — e pune o representante

- **Propósito.** Agrupar variantes do mesmo termo para somar métricas e decidir
  sobre volume agregado em vez de linha a linha.
- **Entrada.** O texto do termo de busca.
- **Decisão.** A chave é a raiz sem acento, sem stopwords e **sem espaços**:
  ```js
  text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/\b(el|la|mi|tu|su|un|una|de|del|para|por|en|que|si|me|se|te|o|a|
                 os|as|do|da|no|na|em|com|um|uma|ao|e|sao|foi|ser|ter|esta|isso|
                 esse|pelo|pela|nos|nas|dos|das)\b/g, '')
      .replace(/\s+/g, '').trim();
  ```
  Métricas somadas **por stem**; o "termo representativo" (`bestTerm`) é o de
  maior impressão do grupo.
- **Saída.** Toda a decisão usa o agregado do stem, mas **a punição e a promoção
  recaem só sobre o `bestTerm`**.
- **Evidência usada.** Função `getStem` do nó `🧠 Analisa e Decide2`.
- **Risco.** **Este é o defeito central de design do workflow, não um bug de
  borda.** O stem `pedemeia` soma "pé de meia", "pe de meia 2026" e
  "pé-de-meia consulta"; se o conjunto é vampiro, **só o `bestTerm` vira negativa
  EXACT** e as demais variantes continuam gastando amanhã. E o inverso é pior:
  **uma variante ruim pode condenar o `bestTerm` que era justamente o bom**.
  Além disso a lista de stopwords é **bilíngue** (espanhol e português
  misturados) e a remoção de espaços faz o hash colidir de formas imprevisíveis.
- **Reversibilidade.** N/A (é o agrupamento).
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ④ descartar.** O que se perde: nada de valor — o agrupamento
  **como implementado** produz decisões erradas nas duas direções. O que fica: a
  **exigência** de agrupar por intenção antes de julgar, e a regra que o
  substituto tem de respeitar — **a punição recai sobre todos os termos do
  grupo, ou o julgamento é feito termo a termo**; julgar o agregado e punir o
  singular é proibido.

---

### E07 · Diagnóstico de inércia de campanha no relatório de termos

- **Propósito.** Aproveitar a varredura de termos para sinalizar campanha que
  quase não aparece.
- **Entrada.** Impressões da campanha na janela de 7 dias.
- **Decisão.** `0 < impressões < 100` ⇒ entra em `observations` como `🐢 INÉRCIA`.
- **Saída.** Só relatório por e-mail. **Nenhuma ação.**
- **Evidência usada.** Nó `🧠 Analisa e Decide2`.
- **Risco.** Baixo — é observação, e observar sem agir é a escolha certa aqui.
- **Reversibilidade.** N/A.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** **Sobreposição:** o VOLC OS já responde a
  mesma pergunta melhor, e sem gastar chamada de API, em
  `backend/app/trafego/alertas.py:364`.
- **Destino: ③ absorvido.** `backend/app/trafego/alertas.py`.

---

# F · Monitoramento, relatório e frescor

Fontes: `custo-gads-report` / `-d1`, `custo-gads-placements-display` / `-d1`,
`custo-force-update-gads`, `front-vincular-campanha-operador`,
`gads-buscar-id-conversoes`. **Todos ativos, exceto o último.**

Estes flows não decidem nada — mas **produzem o insumo de toda decisão de
lance**, e por isso entram no recorte. Também são os que mais escrevem.

---

### F01 · O par D0/D-1 com upsert por `(campaign_id, date)`

- **Propósito.** Ter o número **de hoje** para decidir hoje, e o número
  **fechado** para a contabilidade — sem uma linha de código de reconciliação.
- **Entrada.** `googleAds:searchStream` v24, `FROM campaign`, com
  `segments.date BETWEEN hoje AND hoje` (D0, cron `0 6,12,18,23 * * *`) ou
  `ontem AND ontem` (D-1, `triggerAtHour: 6`).
- **Decisão.** Não há decisão — há **arquitetura**: os dois gravam com
  `on_conflict=campaign_id,date` e `Prefer: resolution=merge-duplicates`, então o
  passe D-1 das 06:00 **sobrescreve** as linhas parciais que o D0 deixou no dia
  anterior, substituindo números intradiários (que o Google ainda ajusta por
  cliques inválidos, conversões tardias e arredondamento) pelos fechados.
- **Saída.** `daily_campaign_metrics` (11 colunas de custo) + RPC
  `process_google_ads_campaign` (cadastro) + `PATCH system_settings`.
- **Evidência usada.** GAQL e nós de escrita dos dois flows.
- **Risco.** **A decisão arquitetural está certa** e é o que permite custo e
  receita ocuparem a mesma linha sem coordenação. Os riscos são de execução:
  (a) o par está **fora de sincronia em 6 aspectos medidos** — o D0 filtra
  `status = 'ENABLED'` e o D-1 `!= 'REMOVED'`, o D0 manda `p_campaign_url` e o
  D-1 não, um dos 5 ramos do D-1 não manda `p_customer_id` (**medido:
  `campaigns.customer_id` está NULL em 3/3 linhas**) e não carimba
  `system_settings`; (b) **não há como reprocessar uma data específica** — o D-1
  é `now − 1 dia` fixo; (c) `onError: continueRegularOutput` em todo nó de
  escrita torna a camada **incapaz de falhar visivelmente**.
- **Reversibilidade.** Alta (o upsert é idempotente por natureza).
- **Estado atual.** **Ativos**, mas escrevendo no Supabase **hospedado** — ver
  `conflitos.md`. Medido no self-hosted: `google_ads_last_update` parado em
  **11/03/2026**, `daily_campaign_metrics` sem escrita desde **25/06/2026**.
- **Conflito com o engine atual.** 🔶 **AUTORIDADE PARALELA** — ficha 3 de
  `conflitos.md`.
- **Destino: ② job que chama o backend canônico.** A ingestão migra; o par
  D0/D-1 e o upsert por `(campaign_id, date)` são **preservados como contrato**,
  com uma correção obrigatória: **o passe de fechamento é parametrizável por
  data**, e cada execução deixa recibo (`ingest_runs(source, target_date,
  started_at, finished_at, rows, status)`) em vez de sobrescrever uma chave
  global em `system_settings`.

---

### F02 · Agregar antes de upsertar — a regra que evita perder dinheiro em silêncio

- **Propósito.** A peça de conhecimento operacional mais bem documentada de todo
  o legado, e o próprio código explica o porquê.
- **Entrada.** `group_placement_view` do Google Ads, que vem por **ad group ×
  placement**.
- **Decisão.** A chave do destino é `(campaign_id, domain, date)` — **mais grossa
  que a da fonte**. O nó `Agregar por domínio` soma `cost` e `conversions` por
  `(campaign_id, domain)`, arredonda a 6 casas e **recalcula** a derivada em vez
  de somá-la (`cost_per_conv = conversions > 0 ? cost/conversions : 0`).
  O comentário no código:
  > *"POR QUE AGREGAR — nao e otimizacao, e correcao. […] varias linhas do mesmo
  > dominio colidem. […] E e obrigatorio para o lote funcionar: com duas linhas
  > da mesma chave no MESMO array, o Postgres recusa o lote inteiro com
  > 'ON CONFLICT DO UPDATE command cannot affect row a second time'
  > (SQLSTATE 21000)."*

  E mais duas lições compradas com dado real: **lote de 500**
  (*"Antes era um POST por linha: ~27 mil requisicoes por execucao, metade
  morrendo em connection timeout. Em lotes de 500 viram ~55"*) e o **lote vazio
  de segurança** (*"Sem linhas, ainda assim emite UM lote vazio: se este no nao
  produzir item, o upsert nao roda, o Loop Over Accounts nunca recebe o sinal de
  continuar e a execucao trava no meio"*).
- **Saída.** `display_ads_placements`, com `batchSize: 50`, `retryOnFail`,
  `maxTries: 3`, `waitBetweenTries: 2000`.
- **Evidência usada.** Nós `Parse Placements` e `Agregar por domínio`.
- **Risco.** Baixo. Perdas conhecidas: a granularidade de ad group é descartada,
  `tipo` sobrevive por acidente (fica o `placement_type` da primeira linha vista
  do domínio) e o `currency_code` é **descartado** — o custo é gravado sem moeda,
  assumindo BRL tacitamente.
- **Reversibilidade.** Alta.
- **Estado atual.** **Ativos** (4×/dia + D-1). `display_ads_placements` tem
  **0 linhas** no self-hosted, e **nenhum dos 30 flows lê essa tabela**.
- **Conflito com o engine atual.** 🔶 Escreve no hospedado — `conflitos.md`.
- **Destino: ③ absorvido em doutrina, ② job na prática.** As três lições
  (agregar à granularidade do destino; recalcular derivadas em vez de somá-las;
  lote vazio como sinal de continuação) já são a mesma família de regra que o
  VOLC OS aplica em `backend/app/trafego/inventario.py` ("ausência é `None`,
  nunca zero"). A ingestão de placements em si vira job do backend — **é o
  insumo da negativação de placement de Display**, que a missão vai precisar.

---

### F03 · Normalização de domínio — a única cola entre custo e receita

- **Propósito.** Permitir comparar, **no mesmo domínio**, o que foi pago para
  aparecer ali (Google Ads, placement) contra o que aquele domínio devolveu
  (GAM, por domínio).
- **Entrada.** `group_placement_view.target_url` / `display_name`.
- **Decisão.**
  ```js
  const u = new URL(url.startsWith('http') ? url : 'https://' + url);
  domain = u.hostname.replace(/^www\./, '');
  ```
- **Saída.** A coluna `domain`, que é parte da chave do upsert.
- **Evidência usada.** Nó `Parse Placements`.
- **Risco.** Baixo. Sem `toLowerCase()` explícito no trecho medido — e o
  inventário registra que uma diferença de caixa no domínio pode produzir duas
  chaves para o mesmo lugar, o que reintroduz o `SQLSTATE 21000` da ficha F02.
- **Reversibilidade.** N/A.
- **Estado atual.** Ativo.
- **Conflito com o engine atual.** Existe `backend/app/trafego/dominio.py` no
  VOLC OS; a consolidação é do domínio de plataforma.
- **Destino: ③ absorvido / ② job.** Função **única e compartilhada**, com testes
  — inclusive o caso de caixa. Nunca duas implementações.

---

### F04 · Carimbo de frescor e o botão "atualizar agora"

- **Propósito.** Dizer ao dashboard quando o dado foi lido pela última vez, e
  permitir forçar uma releitura.
- **Entrada/Decisão/Saída.** `PATCH system_settings?key=eq.google_ads_last_update`
  ao fim de cada ramo; e o `custo-force-update-gads` (2 nós, zero código):
  `Webhook → Execute Workflow(GADS REPORT D0)`.
- **Evidência usada.** Nós `gam_reports7/8/9/12/15` e o flow de force-update.
- **Risco.** Alto, em três frentes. (a) O carimbo é gravado como
  `toLocaleString('pt-BR')` — **string localizada, não ISO** (medido:
  `"11/03/2026, 06:00:17"`), enquanto `joinads_last_update` é ISO: **dois
  formatos na mesma tabela**. (b) É **uma chave global sobrescrita por cinco
  ramos** — não dá para saber qual conta falhou. (c) O webhook de force-update é
  **público e sem autenticação**, e dispara 99 nós e centenas de chamadas à
  Google Ads API: quem souber a URL derruba a cota diária da conta. Ele também
  **só força o D0** — se o D-1 falhar às 06:00, não há como reprocessar.
- **Reversibilidade.** N/A.
- **Estado atual.** **Ativos**.
- **Conflito com o engine atual.** 🔶 **AUTORIDADE PARALELA** por superfície
  pública — ver `conflitos.md`.
- **Destino: ② job + ① política.** Substituir por `ingest_runs` (uma linha por
  fonte × data processada, com `timestamptz`) e por um endpoint **autenticado**
  que aceita `{data, conta}` e **enfileira**, em vez de disparar sincronamente.

---

### F05 · Quem criou a campanha — atribuição por `change_event`

- **Propósito.** Descobrir **qual pessoa** criou qual campanha, para o dashboard
  filtrar por operador.
- **Entrada.** `FROM change_event WHERE change_date_time >= (agora − 5 dias)
  AND change_resource_type = 'CAMPAIGN' AND resource_change_operation = 'CREATE'
  ORDER BY change_date_time ASC LIMIT 10000` (`janelaDias = 5`, quatro MCCs).
- **Decisão.** Este é **o código mais bem escrito de todo o legado**, e as três
  regras merecem sobreviver ao n8n:
  - **quem conta como pessoa**: `CLIENTES_HUMANOS = new Set(['GOOGLE_ADS_WEB_CLIENT'])`
    — *"lance automático, regra automatizada e script do Google também geram
    change_event; a campanha seria atribuída ao robô que a tocou"*;
  - **rascunho vs. campanha publicada**: descarta só quando o status **existe** e
    não é `ENABLED`/`PAUSED` — porque o status vem dentro de `new_resource` e
    *"é mensagem e não entra no WHERE"*;
  - **o teto silencioso vira erro explícito**:
    `if (totalBruto >= 10000) throw new Error(... 'há mudanças que ficaram de fora')`.
  - E deduplicação por par `(conta + nome)` para o caso rascunho→publicada, com o
    caso medido em produção anotado no comentário.
- **Saída.** `campaign_members`, `user_campaigns`, `user_projects`, com
  `Prefer: resolution=ignore-duplicates`.
- **Evidência usada.** Nó `Decidir cada campanha` (884 linhas no flow).
- **Risco.** Baixo no código, alto no destino: escreve no **hospedado**, e
  `campaign_members` e `user_emails` **não existem** no self-hosted
  (`to_regclass` = null). O flow roda a cada 6 horas e **não chega ao banco que o
  produto lê**.
- **Reversibilidade.** Alta (vínculos são idempotentes).
- **Estado atual.** **Ativo**. 🔶 **AUTORIDADE PARALELA** sobre a propriedade de
  campanha e, portanto, sobre o que cada operador enxerga.
- **Conflito com o engine atual.** O VOLC OS tem seu próprio modelo de
  autorização (`public.volc_role_of()`, v8_01 aplicada em 24/08/2026). Dois
  sistemas concedendo visibilidade sobre a mesma campanha, em bancos diferentes.
- **Destino: ② job que chama o backend canônico.** As três regras
  (`CLIENTES_HUMANOS`, rascunho vs. publicada, teto de 10.000 como erro) vão
  literalmente; o destino passa a ser o banco do produto e o modelo de papéis do
  Hub.

---

### F06 · Inventário de ações de conversão por conta

- **Propósito.** Descobrir qual `conversionAction` já existe antes de criar uma
  duplicada.
- **Entrada.** `FROM customer_client WHERE status='ENABLED'` → por conta,
  `FROM conversion_action WHERE conversion_action.status = 'ENABLED'`.
- **Decisão.** Nenhuma — é inventário.
- **Saída.** **Nada.** A saída `done` do `Loop Over Items` não está conectada; os
  dados morrem no painel do n8n.
- **Evidência usada.** `gads-buscar-id-conversoes` (7 nós, **0 linhas de código**).
- **Risco.** Nenhum (não escreve). É ferramenta de bancada.
- **Reversibilidade.** N/A.
- **Estado atual.** Inativo, `manualTrigger`.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ④ descartar.** O que se perde: nada — a consulta é duas linhas de
  GAQL e o VOLC OS já fala com a API pelo SDK oficial v25. O que fica registrado
  é a **necessidade**: antes de criar ação de conversão, listar as existentes.
  Vale notar que este flow aponta para um **terceiro MCC** (`8696453882` /
  `6650747513`), diferente dos usados pelos flows de criação (`6016739364`) e do
  MCC da casa declarado no `RUN-MANIFEST.json` (`6016739364`).

---

# G · Preditivo

Fontes: `bola-de-cristal-preditivo` ("Python predict flow final", 46 nós,
1.102 linhas, **inativo**, `triggerCount: 0`, só `manualTrigger`) e o estágio
`PredictiveModel (D+1)` do `orakul-predictive-integrado-v1` (**inativo**).
Existe ainda um ramo de ML **órfão de ~1.100 linhas dentro do workflow ativo**
`atuacao-orakul-ai-agent-webgo`, terminando num nó sem saída.

---

### G01 · Previsão D+1 de gasto e de receita

- **Propósito.** Antecipar o lado direito da equação: saber se o spread de amanhã
  continua positivo **antes** de o dia começar.
- **Entrada.** ≥ **8 dias** de `daily_campaign_metrics` (e ≥ 5 após `dropna()`).
- **Decisão.** Dois estágios:
  - **gasto**: 12 features (lags, médias móveis, z-score, EWMA, utilização de
    verba, CPC, tendência de impressões) num ensemble fixo
    **`0.4 × Ridge(alpha=0.5) + 0.6 × XGBRegressor(n_estimators=200,
    learning_rate=0.1, max_depth=4, subsample=0.9)`**, com **clamp triplo**:
    `max(0, min(pred, recent_max × 1.1, budget_amount))`;
  - **receita**: 8 features (`spend`, `spend_squared`, `campaign_age`,
    `roas_lag1`, `ctr_ma3`, `ctr_ma7`, `conversion_rate_ma7`, `is_payday`) com
    `StandardScaler` + `Ridge(alpha=1.0)`. O termo `spend_squared` é a **única
    estrutura de retorno decrescente** de todo o sistema.
- **Saída.** No `bola-de-cristal-preditivo`: **nada** — zero escritas, o
  resultado morre no log de execução. No `orakul-predictive-integrado-v1`:
  modula a agressividade do lance.
- **Evidência usada.** Nós `Code2`/`Code4`/`Code7` (três variantes do mesmo
  modelo, rodando A/B/C sobre **a mesma campanha e a mesma janela**).
- **Risco.** Alto, e o inventário é explícito: *"A ideia é a joia; a
  implementação atual não é utilizável como está."* (a) O estágio de gasto tem
  **vazamento de alvo** que o reduz a uma persistência disfarçada; (b) a
  "validação" que compara previsto contra realizado está **desalinhada em dois
  dias** e olha para um dia que estava dentro do treino; (c) `sklearn`, `xgboost`
  e `pandas` dentro de um nó Code do n8n (Pyodide) é pesado, lento e frágil a
  upgrade; (d) **nada acumula histórico de acerto** — não existe tabela cujo nome
  contenha `predi`, `forecast` ou `model` no banco, então **é impossível medir
  erro fora da amostra ao longo do tempo**.
- **Reversibilidade.** Total (nada é escrito).
- **Estado atual.** Inativo. A campanha hardcoded (`23731140888`) **nem existe**
  no Supabase self-hosted.
- **Conflito com o engine atual.** Nenhum. E a **curadoria já decidiu a ordem**:
  prioridade **14**, *"Reabrir otimização avançada e preditivo — DEPOIS DO CHÃO"*,
  com a exigência de *"replay e shadow […] antes de qualquer atuação automática"*.
- **Destino: ⑤ decidir depois**, com a pergunta já formulada pela curadoria e uma
  precondição que eu acrescento: **nenhuma previsão move verba antes de existir
  uma tabela de previsões versionadas com erro fora da amostra medido em janela
  contínua.** Sem isso não há como saber se o modelo ajuda ou atrapalha.

---

### G02 · Intervalo de confiança conformal modulando a agressividade

- **Propósito.** Fazer a **incerteza** da previsão participar da decisão, em vez
  de tratar a previsão como fato.
- **Entrada.** Erros absolutos das últimas `k = max(7, ceil(0.3·n))` observações
  de treino.
- **Decisão.** Quantil **0,90** dos erros absolutos, somado a uma reprevisão de
  receita com o gasto deslocado de
  `spend_delta = max(spread_de_volatilidade × 0.5, ensemble_spread × 0.5)`.
  E o uso: **`intervalo > 50% da previsão → multiplicador × 0.95`** — a
  agressividade cai quando a incerteza sobe.
- **Saída.** Ajuste no multiplicador do lance.
- **Evidência usada.** `PredictiveModel (D+1)` do `orakul-predictive-integrado-v1`.
- **Risco.** Baixo, e o inventário chama isto de *"a parte mais bem pensada do
  arquivo"*. **Previsão sem barra de erro não deve mover verba** — e aqui a barra
  de erro já modula a decisão. É conformal rudimentar, mas é conformal.
- **Reversibilidade.** Total.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum, e é **a mesma doutrina** de
  `backend/app/trafego/inventario.py` e `projecao.py`: número sem procedência ou
  sem frescor não chega à tela.
- **Destino: ① política versionada** — não como modelo, mas como **regra de
  contrato**: `previsao_sem_intervalo_nao_move_verba`. Vale mesmo antes de
  existir modelo algum, porque proíbe o atalho.

---

### G03 · `is_payday` — sazonalidade de salário como feature

- **Propósito.** Capturar o ciclo de renda brasileiro, que move busca e conversão
  em nicho de benefício social.
- **Entrada.** `day_of_month`.
- **Decisão.** `is_payday = day_of_month ∈ {1, 21, 27}`.
- **Saída.** Feature do modelo de receita.
- **Evidência usada.** `_preprocess_data` dos três modelos.
- **Risco.** Baixa e barata, mas é **uma hipótese hardcoded sem validação
  registrada** — dispara ~3 vezes por mês e ninguém mediu se os três dias são os
  certos (o calendário do INSS, por exemplo, escalona por dígito do benefício).
- **Reversibilidade.** Total.
- **Estado atual.** Inativo.
- **Conflito com o engine atual.** Nenhum.
- **Destino: ⑤ decidir depois.** *A pergunta exata:* **os dias 1, 21 e 27
  explicam variação de conversão na série da casa, ou o calendário relevante é
  outro (INSS por dígito final, Bolsa Família, FGTS)?** É respondível com os
  dados que já existem, assim que a série voltar a crescer. Registro a hipótese
  para que ela não se perca — é conhecimento de domínio barato e possivelmente
  valioso.
