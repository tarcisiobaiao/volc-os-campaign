# SPEC — VOLC O.S. Arbitragem: a arquitetura que liga as pontas

> ⚠️ **PREMISSA REFUTADA em 01/09/2026.** `campaign.selective_optimization` é campo de campanha de **APP**, não de Search — confirmado literalmente na doc oficial (callout "Important" em `conversions/goals/overview`), ver `docs/architecture/evidence/GOOGLE-ADS-DOCS-2026-09-01.md`. Para Search, a campanha **herda** os `CustomerConversionGoal` da conta, e sobrescrever exige `CampaignConversionGoal` — que a API só **atualiza**, nunca cria nem remove. O texto abaixo é histórico e não deve ser implementado como está.


> Escrito em 19/08/2026, a partir do catálogo `inventario-n8n/` (30 workflows,
> 7 camadas, tudo medido), do retrato do repositório e do banco, e das quatro
> decisões do dono registradas em `inventario-n8n/RESPOSTA-FABLE-01.md`:
> **(1)** o Supabase hospedado está abandonado — sem backfill, operação nasce
> com N=0; **(2)** JoinAds reporta em USD com revshare 10%; **(3)**
> pré-autorização existe, só na direção que reduz gasto; **(4)** o BEAST foi
> desligado por suspensão da conta AdSense, não por defeito.
>
> Todo número citado aqui foi medido — a procedência está no catálogo
> (`00-MAPA.md` e camadas 02–08) ou na verificação independente de 19/08
> (3 agentes: flows, repo, banco). Este documento **projeta**; o que já existe
> está marcado como existente.

---

## 0. Princípios — o que manda no desenho

Derivados do diagnóstico e das respostas do dono. Toda decisão abaixo se
justifica por um destes; quando dois conflitam, vale o de número menor.

- **P1 · O sistema percebe sozinho que parou.** Seis meses escrevendo no banco
  errado, 9.407 gclids nunca enviados e uma conta suspensa que parou tudo — em
  nenhum dos três casos o sistema soube. Todo componente que escreve dado
  escreve também um **recibo** (linhas contadas, no mesmo banco do dado), e o
  componente mais confiável da casa vigia o menos confiável. "Verde" sem
  linhas contadas não existe neste sistema.
- **P2 · Cold start é o caso normal, não a borda.** A operação nasce com N=0
  e sem histórico recuperável. Todo motor, tela e modelo declara seu
  comportamento com zero dados e degrada com dignidade. *"Ainda não medido"*
  é uma resposta válida em qualquer ponto do sistema; um valor inventado,
  nunca.
- **P3 · Assimetria de autorização.** Reduzir gasto (cortar verba, pausar,
  baixar lance) pode ser pré-autorizado — explícito, com teto, piso, validade,
  revogável, auditado. **Aumentar gasto exige humano, na hora, sempre.**
  Errar reduzindo custa oportunidade; errar aumentando custa dinheiro.
- **P4 · Um substantivo: Proposta.** Tudo que quer mudar o mundo externo —
  venha do motor, de um agente, do árbitro ou do operador — vira uma Proposta.
  Só o Executor executa Propostas, e só por uma porta.
- **P5 · Fato ≠ opinião ≠ ação.** Métrica medida, decisão do motor e registro
  de atuação vivem em três tabelas. Nunca mais uma coluna de auditoria com
  `DEFAULT now()` transformando 12 decisões em 92 falsos positivos.
- **P6 · Moeda e procedência declaradas.** Cada fonte de receita declara
  moeda, grão, revshare e dono da conta. Foi a moeda implícita que fez a
  camada 05 reportar 82% de perda onde havia 5%.
- **P7 · Doutrina de campanha (do dono, inegociável).** Campanha = rei: um
  termo, uma campanha, um conjunto. Nasce `PAUSED`, em `MANUAL_CPC` com
  phrase. Gradua em 30 conversões para lance automático; broad é a recompensa
  da graduação. Razão de mecânica de leilão em `SMART-BIDDING-2026-08-17.md`.
- **P8 · O portão mora dentro da porta.** Hoje o portão de MCC vive no router
  (`backend/app/trafego/escopo.py`); quem chamar o engine por fora passa por
  cima. Engine que confia no chamador não tem portão, tem convenção — o
  portão desce para dentro do cliente Google Ads.
- **P9 · A conta de monetização é um objeto vigiado.** Suspensão de conta é o
  pior modo de falha da arbitragem: a receita zera e o custo continua. O
  sistema inteiro vigiava o denominador; o numerador pode sumir por decisão
  de terceiro. Nunca mais sem vigia.

---

## 1. O modelo de domínio

### 1.1 A cadeia que já existe — e o que falta nela

```
PAUTA ──► FUNIL ──► CAMPANHA ──► RESULTADO
 │          │           │            │
 pautador_  pautador_   campaigns    daily_campaign_metrics (fato)
 entities/  funnel_runs (hoje: 3     fact_page_daily / fact_funnel_daily
 opport.    (vivo)      linhas de    joinads_metrics
 (vivo)                 fev, sem     site_visits (9.468 cliques presos)
                        funnel_run_id)
```

As entidades de PAUTA e FUNIL existem e funcionam. O que falta no domínio são
**quatro substantivos**: a Proposta (o que o sistema quer fazer), a
Autorização (o que o humano permitiu de antemão), a Execução (o que de fato
aconteceu) e a Conta de Monetização (de onde vem a receita, e em que estado
ela está). O resto deste capítulo define os quatro.

### 1.2 Proposta — o substantivo que faltava

Uma Proposta é a intenção de mudar uma campanha, com procedência, evidência,
direção e estado. A forma vem do melhor pedaço do BEAST (a fila de ações com
`executavel_base` separado de `executavel`) mais o que ele perdeu (o árbitro
com `motivos[]`) mais o que nunca teve (procedência, reversibilidade, FK).

```sql
create table propostas (
  id               uuid primary key default gen_random_uuid(),
  campaign_id      text references campaigns(campaign_id),
                   -- NOT NULL exceto na criação, onde o id só existe pós-mutate:
                   -- CHECK (tipo = 'CRIAR_CAMPANHA' OR campaign_id IS NOT NULL)
  tipo             text not null,   -- CRIAR_CAMPANHA | AJUSTAR_LANCE | AJUSTAR_VERBA |
                                    -- PAUSAR | REATIVAR | GRADUAR | NEGATIVAR_TERMO |
                                    -- PROMOVER_TERMO | ALERTA
  direcao          text not null check (direcao in ('REDUZ','AUMENTA','NEUTRA')),
  trilho           text not null check (trilho in ('A','B')),  -- A defesa, B otimização
  reversibilidade  text not null check (reversibilidade in
                     ('REVERSIVEL','CUSTOSA','IRREVERSIVEL')),
  valor_atual      numeric,          -- lance/verba vigente no momento da proposta
  valor_proposto   numeric,
  params           jsonb not null,   -- payload técnico (micros, resource names)
  razao            text not null,    -- uma frase para humano
  evidencia        jsonb not null,   -- métricas e janelas que sustentam (rpc_3d, roas, histerese…)
  origem           text not null,    -- 'motor:beast/2.0' | 'humano:<user_id>' | 'agente:<id>'
  prioridade       int  not null check (prioridade between 1 and 4),
  estado           text not null default 'PROPOSTA' check (estado in
                     ('PROPOSTA','APROVADA','VETADA','EXPIRADA',
                      'EXECUTANDO','EXECUTADA','FALHOU')),
  gate             text,             -- por que não executa (modo, histerese incompleta…)
  veto_motivos     text[],           -- herança do árbitro: cada veto é uma frase
  aprovada_por     text,             -- user_id OU 'autorizacao'
  autorizacao_id   uuid references autorizacoes(id),
  aprovada_em      timestamptz,
  valida_ate       timestamptz not null,  -- proposta velha expira, nunca executa
  created_at       timestamptz not null default now()
);
```

**A máquina de estados** (transições nomeadas, só o backend escreve):

```
PROPOSTA ─┬─► APROVADA ──► EXECUTANDO ──► EXECUTADA (ver §1.4: verificação)
          ├─► VETADA      (árbitro ou humano; veto_motivos preenchido)
          └─► EXPIRADA    (valida_ate venceu sem decisão)
                              └────────► FALHOU (erro na API; erro gravado)
```

`valida_ate` vencida leva a `EXPIRADA` a partir de **qualquer** estado
não-terminal — inclusive `APROVADA`: aprovada e não executada a tempo, não
executa mais. Para direção AUMENTA há ainda um TTL curto (minutos, em
política) entre `aprovada_em` e o mutate — "na hora" significa na hora.

**Como cada produtor atual mapeia para Proposta:**

| hoje | vira |
|---|---|
| fila de ações do BEAST (`tipo_acao`, `executavel`) | Propostas com `origem='motor:…'`; `executavel_base` → ausência de `gate`; `executavel` → cobertura por autorização |
| árbitro do predictive (`aplicar:false`, `motivos[]`) | estado `VETADA` + `veto_motivos` |
| `OrientacaoBox` (markdown) | render no front a partir de `razao` + `evidencia` — markdown morre no servidor |
| `OtimizacaoBox` (outro JSON) | leitura da tabela `execucoes` (§1.4) |
| clique "Aplicar Bidding" do operador | Proposta `origem='humano:…'` já `APROVADA` — mesmo caminho, mesma porta |
| cockpit `/trafego` subindo campanha | Proposta de criação (§2.4) — subir e ajustar são o mesmo gesto em dois momentos |

**Mapa das 11 ações do BEAST para o novo vocabulário** (com a direção, que é
o eixo de autorização do P3):

| ação BEAST | tipo | direção | trilho | executor |
|---|---|---|---|---|
| PAUSE_CAMPAIGN / ZOMBIE | `PAUSAR` | REDUZ | A | API (pausa é reversível — deixa de ser e-mail) |
| ZOMBIE_THROTTLE / LOSS_CAP_THROTTLE | `AJUSTAR_VERBA` | REDUZ | A | API |
| ADJUST_BID (corte) | `AJUSTAR_LANCE` | REDUZ | A/B | API |
| ADJUST_BID (aumento) / SCALE | `AJUSTAR_LANCE`/`AJUSTAR_VERBA` | AUMENTA | B | API, humano na hora |
| ADJUST_BUDGET (aumento) | `AJUSTAR_VERBA` | AUMENTA | B | API, humano na hora |
| reativar campanha pausada | `REATIVAR` | AUMENTA | B | API, humano na hora, sempre — retomar gasto é aumentar gasto |
| CHANGE_STRATEGY / SUPER_GRADUATION | `GRADUAR` | AUMENTA | B | API, humano na hora — graduação é evento de estrutura (estratégia+match+verba juntos) |
| REDISTRIBUTE_BUDGET | morre (nunca funcionou) — vira duas Propostas REDUZ+AUMENTA independentes | | | |
| ANOMALY / EVENTO_EXTERNO / ECPM_DEGRADING / REVIEW_COPY | `ALERTA` | NEUTRA | A | nenhum — vira item de fila |
| tribunal lexical: negativar | `NEGATIVAR_TERMO` | REDUZ | A | API, pré-autorizável com teto diário de termos |
| tribunal lexical: promover | `PROMOVER_TERMO` | AUMENTA | B | **gatilho de nascimento**: a aprovação despacha para a porta de criação (§2.4) uma campanha nova — um termo, um conjunto, phrase (P7); nunca keyword nova na campanha de origem |

**A direção não é um rótulo — é derivada e conferida.** `direcao` é declarada
pelo produtor da Proposta, mas o Executor **deriva a direção efetiva** antes
de executar (§2.2): `PAUSAR`/`NEGATIVAR_TERMO` → REDUZ por definição;
`REATIVAR`/`PROMOVER_TERMO`/`GRADUAR`/`CRIAR_CAMPANHA` → AUMENTA por
definição; `AJUSTAR_*` → comparação de `valor_proposto` contra o valor
**relido da API** no momento da execução. Declarada ≠ derivada → recusa +
alerta `CRITICO`. Um motor com bug que rotule um aumento de verba como REDUZ
não executa às 3h — é este degrau que transforma o P3 de convenção em parede,
e é sobre a direção derivada (gravada em `execucoes.direcao_efetiva`) que a
sentinela do PRD F6 conta.

### 1.3 Autorização — o "explícito" separado do "na hora"

```sql
create table autorizacoes (
  id            uuid primary key default gen_random_uuid(),
  campaign_id   text references campaigns(campaign_id),  -- NULL = carteira inteira
  classe        text not null check (classe in ('DEFESA_REDUCAO','UPLOAD_CONVERSAO')),
  direcao       text not null,
  -- o invariante do P3, POR CLASSE — não existe classe que autorize AUMENTA:
  constraint autorizacao_direcao check (
       (classe = 'DEFESA_REDUCAO'   and direcao = 'REDUZ')
    or (classe = 'UPLOAD_CONVERSAO' and direcao = 'NEUTRA') ),
  limites       jsonb not null,   -- DEFESA_REDUCAO: {piso_verba_brl, teto_corte_pct,
                                  --  max_acoes_dia, teto_termos_dia,
                                  --  gatilhos: [{regra:'ZUMBI', spend_min, ...}]}
  valida_de     timestamptz not null,
  valida_ate    timestamptz not null,
  revogada_em   timestamptz,
  criada_por    text not null,    -- sempre um humano
  created_at    timestamptz not null default now()
);
```

**O invariante do domínio, em três paredes:** (1) o CHECK acima — não existe
classe que autorize aumento; (2) o Executor recusa e alarma qualquer Proposta
cuja **direção derivada** (§1.2) não seja REDUZ e chegue com `autorizacao_id`
preenchido — a checagem é sobre a direção que ele mesmo calculou, nunca sobre
o rótulo; (3) a classe `UPLOAD_CONVERSAO` não cobre Proposta nenhuma — ela é
a autorização permanente do único fluxo contínuo fora do modelo de Propostas,
o upload de conversões offline (§5.4), criada pelo dono, revogável, e parada
pelo kill switch como tudo o mais.

A autorização nasce no mesmo gesto que o contrato de graduação: a **Mesa de
Lance** (SPEC-FRONT §5) registra, no nascimento da campanha, o que o motor
pode fazer para defendê-la — *"pode cortar verba até o piso de R$ 10 se o
gasto passar de R$ 15 sem nenhuma receita"* — com validade e botão de
revogar. É mais explícito do que um "aprovar" às 3h com sono.

### 1.4 Execução — o ledger que não mente

O log do BEAST gravou duas vezes a mesma ação de R$ 20,28 enquanto o valor
que vingou foi R$ 21,97 — porque recuperava contexto varrendo nós. Aqui cada
execução carrega o `action_id` desde a origem:

```sql
create table execucoes (
  id              uuid primary key default gen_random_uuid(),  -- action_id = chave de idempotência
  proposta_id     uuid not null references propostas(id),
  campaign_id     text not null,
  customer_id     text not null,
  request         jsonb not null,   -- o mutate exato enviado
  response        jsonb,            -- a resposta exata da API (sucesso E falha)
  valor_antes     numeric,          -- RELIDO da API antes do mutate (não o snapshot da proposta)
  valor_depois    numeric,          -- confirmado por releitura (abaixo)
  direcao_efetiva text not null,    -- derivada pelo Executor (§1.2) — a sentinela do
                                    -- PRD F6 conta sobre ELA, não sobre o rótulo
  status          text not null check (status in
                    ('ENVIADA','CONFIRMADA','DIVERGENTE','FALHOU')),
  erro            text,
  executada_em    timestamptz not null default now(),
  verificada_em   timestamptz
);
create unique index ux_execucoes_proposta on execucoes(proposta_id)
  where status <> 'FALHOU';
-- idempotência com constraint, não com promessa: reexecutar a mesma Proposta é
-- no-op; retry só após FALHOU — e é decisão registrada, não acidente.
```

**Verificação pós-execução:** após todo mutate, o Executor **relê** o campo na
API do Google Ads e grava `valor_depois`. Se diferir do proposto →
`DIVERGENTE` + alerta. É o que teria pego o bug do Apply Bidding que manda
corpo `maximizeConversions` com máscara `target_cpa` e *limpa* o tCPA de
campanhas TARGET_CPA (medido no flow; inócuo até hoje só porque as 3
campanhas eram MaxConv).

### 1.5 Conta de monetização — o objeto que ninguém vigiava

```sql
create table contas_monetizacao (
  id             serial primary key,
  provedor       text not null,    -- 'GAM' | 'ADSENSE' | 'JOINADS'
  dono           text not null,    -- 'casa' | 'parceiro'
  identificador  text not null,    -- network code / pub-id / domínio Join
  moeda          text not null,    -- 'USD' | 'BRL' — declarada, nunca implícita (P6)
  revshare       numeric not null, -- 0.10 na Join, medido e confirmado pelo dono
  estado         text not null check (estado in
                   ('ATIVA','AVISO','LIMITADA','SUSPENSA','ENCERRADA')),
  ultimo_sinal   timestamptz,      -- última receita > 0 ou último report OK
  created_at     timestamptz default now()
);
create table contas_monetizacao_eventos (
  id serial primary key,
  conta_id int not null references contas_monetizacao(id),
  de text, para text not null, motivo text, origem text,  -- 'manual' | 'monitor'
  created_at timestamptz default now()
);
```

Três usos, em ordem de importância:

1. **O gatilho mais óbvio do Trilho A** — e ele tem números, não "X": dispara
   quando *custo do dia corrente > 0* **e** *receita da última janela
   aterrissada = 0* **e** *carência vencida* (conta/campanha com ≥ 3 dias de
   operação — P2: o dia 1 tem receita zero legítima, e a Join só devolve a
   chave com tráfego) por ≥ `horas_zerada` (v1: **12h**, parâmetro em
   `politicas_decisao`). Avaliado só sobre dado **com recibo** — o mesmo
   conceito que mata o falso zombie das 18:30 (§5.2); é a cadência intraday da
   Join (4×/dia) que dá resolução ao monitor. Disparo → Propostas
   `PAUSAR`/`AJUSTAR_VERBA` REDUZ para toda campanha ligada àquela conta,
   cobertas por autorização. É a defesa contra o modo de falha que já matou a
   operação uma vez.
2. **Redundância como requisito:** `projects` ganha a relação com contas de
   monetização (qual conta serve qual site). Se uma fonte cair, o painel diz
   quanto da receita estava nela e o que assume. Um site com uma única conta
   ativa é um estado `AVISO` permanente no painel de saúde.
3. **Registro de trauma:** a suspensão de fevereiro não está escrita em lugar
   nenhum do sistema — só na memória do operador. `_eventos` é onde ela
   passaria a existir.

### 1.6 Fonte de receita — moeda como contrato

```sql
create table fontes_monitoradas (  -- o catálogo do watchdog: TUDO que tem cadência
  fonte  text primary key,         -- 'joinads' | 'gads_custo' | 'cambio' |
                                   -- 'conversao_upload' | 'kw_mining' | …
  tipo   text not null,            -- 'receita' | 'custo' | 'apoio'
  cadencia_esperada interval not null
                                   -- joinads: INTRADAY (4×/dia, 6/12/18/23h) — é essa
                                   -- resolução que sustenta o monitor do §1.5
);

create table fontes_receita (      -- o contrato comercial: só quem é receita
  fonte     text primary key references fontes_monitoradas(fonte),
  conta_id  int references contas_monetizacao(id),
  moeda     text not null,
  bruto     boolean not null,      -- true = revshare aplicado pelo banco (contrato atual)
  grao      text not null          -- 'projeto' | 'campanha' | 'placement' | 'hora'
);
```

O contrato de ingestão atual — *"o ingestor grava bruto e fino; câmbio,
revshare e project_id são triggers do banco"* — está **mantido**: é a decisão
mais acertada do sistema antigo e é o que permitiu a JoinAds subir em dias.
A tabela acima só torna declarado o que era implícito.

---

## 2. A fronteira de execução — uma porta só

### 2.1 O problema medido

Criar campanha passa por `/provar` → `validate_only` real → Selo sha256 →
`subir()` que recusa payload sem selo ou com grafo alterado (verificado:
`volc_ads/subir.py:228-431`). Ajustar lance sai de um `fetch()` no browser
para um webhook sem token, sem faixa de valor, com corpo fixo — hardcoded em
`BiddingActionBox.tsx:123`. **A porta mais perigosa é a única desprotegida.**
E o portão de MCC mora no router, não no engine.

### 2.2 O desenho

Um único módulo no backend — o **Executor** — é o único código do sistema com
credencial de mutação no Google Ads. Ele executa exclusivamente Propostas em
estado `APROVADA`, e toda execução atravessa a mesma escada:

```
Proposta APROVADA
  → 0. validade: valida_ate não vencida (senão → EXPIRADA, de qualquer estado
       não-terminal); AUMENTA tem ainda TTL curto entre aprovada_em e o mutate
  → 1. escopo: login_customer_id = MCC da casa  E  customer alvo do mutate na
       allowlist contas_anuncio — ambos DENTRO do volc_ads/gads/client (P8).
       O caso perigoso não é o login errado: é o login certo operando conta de
       terceiro sob o MCC. O check do router continua como segunda parede, e o
       USER_PERMISSION_DENIED do Google é a terceira.
  → 2. leitura viva: relê o valor vigente na API → execucoes.valor_antes
       (o snapshot da proposta é evidência, nunca âncora — TOCTOU foi o que fez
       o BEAST somar +30% e +20% sobre contexto defasado)
  → 3. direção efetiva: derivada de (tipo, valor vigente, valor_proposto);
       declarada ≠ derivada → recusa + alerta CRITICO (§1.2)
  → 4. cobertura: AUMENTA exige aprovada_por humano; REDUZ por autorização
       exige limites conferidos (piso, teto, max_acoes_dia)
  → 5. faixa: valor_proposto ∈ [0,3× , 2×] do valor VIGENTE (degrau 2), salvo
       humano com confirmação dupla (o webhook aceitava valor_aplicado: 100000)
  → 6. prova: validate_only do mutate exato               (grátis, é leitura)
  → 7. idempotência: INSERT em execucoes (UNIQUE por proposta); repetição = no-op
  → 8. mutate
  → 9. recibo: response gravado, sucesso E falha          (P1)
  → 10. verificação: releitura do campo → CONFIRMADA | DIVERGENTE
```

O Selo da criação e a prova da mutação são o **mesmo conceito** em dois
tamanhos: *nada escreve no Google Ads sem ter sido validado contra a conta
real na forma exata em que vai ser escrito.*

### 2.3 Como a defesa às 3h passa pela porta sem gargalo humano

```
motor (06:30 / 18:30 / sob evento) emite Proposta
  direcao = REDUZ, trilho A
     → Executor procura autorização válida que cubra (campanha, classe, limites)
        → achou: aprova com aprovada_por='autorizacao', executa, NOTIFICA (não pergunta)
        → não achou: fica PROPOSTA na fila, notifica com urgência
  direcao = AUMENTA
     → SEMPRE fila. Nenhum caminho de código executa AUMENTA sem humano na hora.
```

Ritmo: Trilho A não espera o cron do motor — o **monitor de saúde** (§8) pode
emitir Proposta REDUZ a qualquer hora (é ele que vigia "receita zero com
custo correndo"). Trilho B anda no ritmo humano, na fila da carteira (§6).

Freios do Trilho A mesmo pré-autorizado: teto de `max_acoes_dia` por campanha
(o cooldown que o BEAST nunca teve, agora lendo `execucoes` — dado real, não
coluna fantasma), piso de verba (`budget_floor` herdado), e **kill switch
global** (`system_settings.trava_global`) checado antes de todo mutate.

### 2.4 A criação de campanha na mesma fronteira

O `/subir` de hoje não persiste **nada** no banco — o recibo vai para arquivo
de propósito (`volc_ads/subir.py:67`) e `campaigns` nunca é escrita pelo
nosso lado (verificado: 0 ocorrências de `funnel_run_id` no backend). A junta
FUNIL→CAMPANHA se fecha aqui, na transação de criação:

1. O pedido de criação **exige `funnel_run_id`** — campanha sem procedência é
   impossível pela porta nova. A extração de domínio por regex no nome vira
   fallback de emergência com alerta, nunca caminho normal.
2. Depois do mutate com selo, na mesma transação de banco:
   `campaigns` (com `campaign_id` devolvido pela API, `customer_id`,
   `funnel_run_id`, contrato de graduação), `campaign_funnel_urls` (o Redator
   já conhece as URLs — publicou), `autorizacoes` (se a Mesa de Lance
   registrou defesa), e o recibo em `execucoes`.
3. A infraestrutura de conversão sintética — hoje só no flow ClickUp morto —
   é portada para o `volc_ads`: `conversionAction` `UPLOAD_CLICKS`/`PURCHASE`/
   `MANY_PER_CLICK`/lookback 1 dia por nicho, ~~`selective_optimization`~~ ⚠️ **REFUTADO (01/09/2026): campo de campanha de APP; em Search a meta é herdada da conta e o override é `CampaignConversionGoal`. Não implemente** (o
   campo `conversao` deixa de viajar e morrer), e a GAQL de leitura **pede
   `conversion_action.tag_snippets`** para persistir `AW-id/label` em
   `niche_conversion_mappings` — o defeito de duas pontas que deixou a tabela
   com 0 linhas.
4. A campanha nasce `PAUSED` (P7). Ativar é um gesto humano — é ele a
   "autorização explícita, na hora" de queimar dinheiro.

No vocabulário do §1.2: o `/subir` cria uma Proposta `CRIAR_CAMPANHA`
(direção AUMENTA — o humano na hora é quem está clicando) que **nasce
`APROVADA`**, com `params` = brief + selo e `campaign_id` NULL; o Executor
executa, e o id devolvido pela API preenche `propostas.campaign_id`,
`campaigns` e `execucoes` na mesma transação. Subir e ajustar são
literalmente o mesmo objeto em dois momentos.

O webhook `1cb2069d` morre; o front fala apenas com o backend autenticado.

---

## 3. Onde cada coisa roda — caso a caso

O critério: **(i)** onde dá para testar e versionar, **(ii)** onde a falha é
visível, **(iii)** custo de manter, **(iv)** quem mantém (uma pessoa).

| responsabilidade | onde | por quê — e por que não nos outros |
|---|---|---|
| Ingestão de custo (GAQL v25) | **backend FastAPI** (job) | SDK oficial já em casa com 443 testes; retry/paginação/`partialFailure` são código testável. Não n8n: foi o modo de falha (verde com tabela vazia). Não Edge: runtime Deno sem SDK Google. Não SQL: chamada externa. |
| Ingestão JoinAds | **backend** (portar os 2 flows como estão) | Os 17 nós da Join são o *modelo* de ingestor: janela de 1 dia por request, desambiguação DD/MM, guarda de `custom_key`, lote de 500. Vira um módulo Python com os mesmos comentários. |
| Ingestão GAM/AdSense próprios | **backend, adiado** | Não há conta ativa (AdSense suspenso; GAM é do parceiro, espelhado pela Join). O módulo nasce quando a conta existir — o desenho da Join serve de molde. |
| Câmbio diário | **backend** (job de ~20 linhas → `exchange_rate_history`) | Segredo (chave da API) fica no servidor, não no banco. `get_exchange_rate_for_date()` já existe e volta a funcionar como projetada. |
| Enriquecimento (câmbio→BRL, revshare, project_id, fan-out) | **Postgres (triggers)** — manter | Contrato "grava fino, banco engorda" é a joia nº 1 do sistema antigo. Já existe, já testado em produção. Uma correção: resolver a disputa alfabética de dois BEFORE em `revenue_converted` deixando **uma** função por tabela. |
| Agregação comportamental (`fact_page_daily`, `fact_funnel_daily`) | **pg_cron + funções SQL** — manter e estender | Único subsistema com 4.720/4.720 sucessos. Estender: `host` preenchido, `avg_ads_per_session` com o evento novo do sensor (§5.4). Achar e documentar o chamador de `compute_funnel_daily` (hoje fantasma). |
| Motor de decisão | **backend** (serviço Python, função pura) | 1.678 linhas de heurística precisam de teste, replay e versionamento — impossível em JSON de n8n (era o problema 2), inviável em SQL, sem numpy em Edge. |
| Executor | **backend**, colado no `volc_ads` | §2. A credencial de mutação existe num único processo. |
| Monitor de monetização | **backend** (tick ≤ 5 min, heartbeat próprio vigiado pelo watchdog) | O gatilho do P9 (§1.5) não pode esperar o cron do motor — é ele que emite Proposta REDUZ "a qualquer hora" (§2.3). Roda no backend porque cruza recibos, custo intraday e estado de conta; o watchdog pg_cron percebe se ele parar. |
| Preditivo | **backend** (biblioteca separada, job) | Nasce **desligado** (P2): liga por campanha com série ≥ 12 dias (mínimo real medido do modelo). Persiste em `previsoes`; só influencia decisão se bater o baseline `amanhã=hoje` em janela móvel — na simulação de 230 dobras, o modelo atual não bateu. |
| Agendamento | **relógio de trabalho no backend; relógio de vigilância no pg_cron** | O backend agenda e executa (APScheduler ou loop próprio), gravando *heartbeat* e recibos. O pg_cron — que nunca falhou — roda o **watchdog**: um job SQL que compara `recibos_ingestao`/heartbeat contra `cadencia_esperada` e materializa `alertas`. O componente mais confiável vigia o menos confiável (P1). Não pg_cron+pg_net para trabalho: acopla topologia de rede ao banco e esconde o job do repositório. |
| Sensor (raw_events, ad-view) | **como está** (JS + GTM + worker, fora do repo) | É a parte mais viva do parque. Mudança pedida é de *payload* (host, evento de ad-view com valor), não de lugar. Documentar a propriedade dele é tarefa do PRD (F5). |
| Edge Functions | **nada do núcleo** | Reservadas ao Meta CAPI já existente. Observabilidade fraca e runtime limitado desqualificam para dinheiro. |
| n8n | **zero papel no núcleo novo** | Os flows do núcleo **que escrevem no banco abandonado** são desligados no dia zero; **os 3 que apontam para o banco certo (JoinAds ×2, KW Minning) ficam ativos até o porte** (PRD F2 e além) — desligá-los no dia zero mataria a única ingestão viva. As joias são extraídas por este SPEC; a instância continua existindo para os outros clientes da agência. |

**Deploy do backend:** no próprio servidor Hetzner do Supabase
(`178.156.196.149`), como serviço Docker ao lado do compose existente — mesma
máquina que o Postgres (latência zero para recibos), segredos em
`.env` do servidor, e o watchdog pg_cron enxerga o heartbeat sem atravessar
rede. Restrição conhecida: a máquina tem 4 GB (`ubuntu-4gb-ash-1`); os jobs
desta escala cabem com folga, e o upgrade é vertical e barato quando doer.
A Vercel continua servindo o front — ela não roda scheduler.

---

## 4. O modelo de dados

### 4.1 O que muda no que existe

- **`daily_campaign_metrics` vira só FATO.** As colunas `orientacao_*` e
  `otimizacao_*` são congeladas (leitura histórica) e nenhum código novo as
  escreve — opinião vai para `propostas`, atuação para `execucoes`. Some o
  upsert-fantasma (3 linhas com `campaign_id = ''` medidas) e o
  `orientacao_gerado_em DEFAULT now()` deixa de mentir por inanição.
- **`campaigns`**: ganha `origem_cadastro` (`'porta' | 'descoberta' | 'legado'`).
  Pela porta (§2.4), `funnel_run_id` e `customer_id` são obrigatórios
  (validação na aplicação + trigger condicionado a `origem_cadastro='porta'`).
  O job de custo é **escritor legítimo** com `'descoberta'`: campanha
  detectada na conta sem procedência não é bloqueada nem passa calada — gera
  alerta `AVISO` ("campanha sem procedência na conta"). As 3 linhas de
  fevereiro ficam `'legado'`. Ganha também o **contrato de graduação**
  (`graduacao jsonb`: conversões-gatilho, estratégia destino, regra de verba)
  registrado no nascimento e lido pelo motor.
- **`campaign_funnel_urls`**: preenchida no `/subir` a partir do funil. É o
  elo mais barato do sistema (12 de 17 URLs já casam com `fact_page_daily.path`
  por normalização — medido).
- **`exchange_rate_history`**: alimentada diariamente pelo job de câmbio.
  Fica proibido por revisão de código qualquer cotação literal (`5.25`,
  `5.35`, `5.8` — as três conviviam no parque antigo).
- **`bid_actions`**: aposentada (0 linhas, schema divergente). Substituída por
  `propostas` + `execucoes`.
- **`site_visits` / `conversion_queue` / `conversion_batches`**: mantidas como
  estão — o desenho do loop de conversão existe e está certo; faltava quem o
  rodasse (§5.4).

### 4.2 Tabelas novas

`propostas`, `autorizacoes`, `execucoes`, `contas_monetizacao` (+`_eventos`),
`fontes_receita` (§1); e:

```sql
create table recibos_ingestao (       -- P1: o recibo no plano de dados
  id            bigserial primary key,
  fonte         text not null references fontes_monitoradas(fonte),
  data_alvo     date not null,
  janela        text not null,        -- 'D0' | 'D1' | 'sob_demanda'
  iniciado_em   timestamptz not null,
  terminado_em  timestamptz,
  linhas        int,                  -- ESCRITAS, contadas — nunca "assumidas"
  status        text not null check (status in ('OK','VAZIO','ERRO')),
                 -- VAZIO é um estado explícito com causa, não um OK
  erro          text,
  unique (fonte, data_alvo, janela, iniciado_em)
  -- o recibo é HISTÓRICO de execuções (N por janela é legal — reprocessos);
  -- a idempotência do DADO é do job, pelo on_conflict da tabela de destino
);

create table heartbeats (             -- o pulso que o watchdog compara
  componente text primary key,        -- 'scheduler' | 'monitor_monetizacao' | …
  ultimo_tick timestamptz not null,
  cadencia_esperada interval not null
);

create table contas_anuncio (         -- a allowlist do portão (P8) e a config dos jobs
  customer_id text primary key,       -- SÓ contas da casa entram aqui — é contra esta
                                      -- tabela que o client recusa alvo de terceiro
  mcc         text not null,
  apelido     text,
  ativa       boolean not null default true
);

create table projeto_contas (         -- redundância de monetização por site (§1.5)
  project_id int not null references projects(id),
  conta_id   int not null references contas_monetizacao(id),
  papel      text,                    -- 'primaria' | 'reserva'
  primary key (project_id, conta_id)
);

create table politicas_decisao (      -- as constantes compradas com dinheiro real
  id serial primary key,
  perfil     text not null,           -- 'SAFE' | 'GROWTH' | 'BLITZ'
  versao     int  not null,
  vigente    boolean not null default false,
  parametros jsonb not null,          -- escada ±30%, piso ROAS 1.70, modos por idade,
                                      -- budget floor, loss cap, histereses, k=0.70,
                                      -- z-score, micro-ajuste 5%, tribunal lexical…
  origem     text not null,           -- 'BEAST 1.3 L32-108' — procedência de cada número
  created_at timestamptz default now(),
  unique (perfil, versao)
);

create table previsoes (
  campaign_id text not null,
  prevista_para date not null,        -- a data-alvo (mata o desalinhamento de 2 dias medido)
  gerada_em timestamptz not null,
  modelo text not null,               -- versão do artefato
  spend_previsto numeric, receita_prevista numeric,
  ci_baixo numeric, ci_alto numeric,
  baseline_receita numeric,           -- amanhã=hoje, sempre junto
  primary key (campaign_id, prevista_para, modelo)
);

create table termos_busca (           -- materializa search_term_view p/ tribunal em SQL
  campaign_id text, ad_group_id text, termo text, date date,
  impressions int, clicks int, conversions numeric, cost numeric,
  primary key (campaign_id, ad_group_id, termo, date)
);

create table alertas (
  id bigserial primary key,
  origem text not null,               -- 'watchdog' | 'monitor_monetizacao' | 'executor'
  severidade text not null check (severidade in ('INFO','AVISO','CRITICO')),
  chave text not null,                -- p/ dedupe ('frescor:joinads', 'conta:adsense')
  mensagem text not null,
  resolvido_em timestamptz,
  created_at timestamptz default now()
);
```

### 4.3 A view da equação — e a honestidade sobre o que dá para medir hoje

```sql
create view vw_arbitragem_diaria as
select campaign_id, date,
       clicks, spend, spend/nullif(clicks,0)                     as cpc,
       revenue_converted_revshare                                as receita_brl,
       revenue_converted_revshare/nullif(clicks,0)               as rpc,
       (revenue_converted_revshare - spend)/nullif(clicks,0)     as spread_por_clique,
       revenue_converted_revshare/nullif(spend,0)                as roas,
       paginas_por_sessao,        -- fact_funnel_daily via campaign_funnel_urls
       anuncios_por_pagina,       -- sensor (parcial hoje)
       ecpm                       -- joinads_metrics.ecpm
from …;
```

| fator | fonte | estado no dia 1 da operação nova |
|---|---|---|
| cliques / spend / CPC | job de custo (PRD F2) | disponível assim que houver campanha |
| receita por campanha | `joinads_metrics` por `utm_campaign` | disponível quando houver tráfego com UTM (a Join só devolve a chave com tráfego — comportamento medido) |
| eCPM | `joinads_metrics.ecpm` | idem |
| páginas por sessão | `fact_page_daily` (pg_cron — **vivo**) → `fact_funnel_daily` (chamador desconhecido, §10.1; último dado 15/08) | medido; a cadeia fecha quando o chamador virar job explícito (PRD F0) |
| anúncios por página | sensor ad-view | parcial (9/33 linhas medem) — cobertura vem no PRD F5 |
| match rate / fill rate | GAM — que é do parceiro | **não medido, sem fonte.** O desfibrilador por match_rate fica desarmado até existir GAM próprio. A tela mostra "não medido" (P2), nunca um proxy. |
| câmbio do dia | `exchange_rate_history` | PRD F1 |
| conversões enviadas | `conversion_queue`/`batches` | PRD F5 |

### 4.4 Saúde e carteira

- `vw_saude`: por fonte — último recibo, linhas, atraso vs `cadencia_esperada`,
  veredito; + heartbeat do backend; + estado das `contas_monetizacao`. É a
  tela de "o que parou" e a matéria-prima do watchdog.
- `vw_carteira`: por campanha — spread/ROAS 3d, modo (EXPLORATION/…),
  propostas pendentes por direção, última execução, frescor dos dados
  daquela campanha, conta de monetização e estado. É a tela "destas N
  campanhas, estas querem algo de você hoje".

---

## 5. A camada de inteligência

### 5.1 O que se preserva — e é dado, não código

O que o sistema "aprendeu operando" são **constantes e regras compradas com
dinheiro real**, e elas entram em `politicas_decisao` com procedência:

- a fórmula `cpc_alvo = rpc_3d × Π(multiplicadores)` e a tabela inteira de
  multiplicadores do BEAST/Orakul; a escada de ±30%; o piso "abaixo de ROAS
  1,70 lance não sobe";
- os modos por idade (EXPLORATION < 7d / CALIBRATION 7–13 / PRODUCTION ≥ 14)
  com tetos de corte por modo; budget floor (`max(30%, min(R$10, verba))`);
  loss cap (dia 30%/3d 60%, relaxado se proven); histerese em contadores de
  dias consecutivos; detecção de evento externo (eCPM −20% com CPC parado);
  micro-ajuste < 5% não mexe;
- `SUPER_GRADUATION` do NEXUS (a única coisa que dele sobrevive): 30
  conversões → MaxConv com tCPA = CPA real, verba `max(2×, R$30)` — agora com
  a leitura pós-17/08: **meta = CPA observado, nunca folga** (folga virou
  autorização de gasto);
- o tribunal lexical (zona verde → zumbi → retenção → vampiro/fantasma/lixo →
  limbo), reimplementado **em SQL sobre `termos_busca`**, com três consertos:
  a punição recai sobre **todos** os termos do grupo (não só o `bestTerm`);
  todo mutate vai com `partialFailure: true`; e **promover deixou de ser
  criar keyword na campanha de origem** — sob P7 (um termo, uma campanha),
  promover é despachar o termo para a porta de criação como campanha nova,
  com landing própria (§1.2);
- o Beast Mode Parser v2 (4 regras, R$ 411 mil de receita órfã de custo de
  aprendizado) e o `parseMoneyToUSD` — portados literalmente, com os
  comentários, para o módulo de ingestão;
- `k = conversões/cliques ≈ 0,70` (medido fev/26) e o teto derivado
  `tCPA_max = RPC ÷ k` — marcado como *herdado, recalibrar quando N permitir*.

O que **não** se preserva: as 4.812 linhas do Orakul, as três rotas da bola de
cristal, os dois NEXUS, os três geradores de markdown, o stemming por remoção
de espaços. Enterros completos na §9.

### 5.2 A forma do motor

```
decidir(config_campanha, serie_diaria, politica, contexto) → [Proposta]
```

Função pura, sem I/O, com **contrato de entrada validado que falha se faltar
campo** — o cooldown do BEAST foi código morto desde que nasceu, nas quatro
gerações, porque a entrada que ele esperava nunca chegou e ninguém soube. Em
volta dela:

- **Árbitro como função separada** (resgatado do `orakul-predictive-integrado`,
  a geração que o BEAST regrediu): recebe as Propostas e os diagnósticos,
  veta com `veto_motivos[]` — vetos comportamental, temporal (cooldown lendo
  `execucoes`, dado real) e, quando existir, preditivo. Quem calcula não
  decide; quem decide não calcula.
- **Cooldown de verdade:** `max_acoes_dia` e janela mínima entre execuções por
  campanha, consultados no ledger.
- **Correções deliberadas sobre o BEAST** (documentadas no replay): o falso
  zombie das 18:30 morre — dia corrente só entra em janela com **receita
  aterrissada** (recibo da fonte de receita para aquele dia), nunca só por
  hora do relógio; conflito INCREASE+INCREASE resolve por (tipo, alvo), não
  só INCREASE vs DECREASE; nada de `customer_id` hardcoded.

### 5.3 Cold start — o comportamento com N=0 (P2)

| série da campanha | o que o motor pode fazer |
|---|---|
| 0–1 dia | nada além de `ALERTA`. Nenhum número de RPC existe. |
| 2–6 dias (EXPLORATION) | só Trilho A com gatilhos absolutos: zumbi (gasto > R$15 com receita **do dia fechado** = 0), loss cap. Cortes limitados a −10/−15%. |
| 7–13 (CALIBRATION) | Trilho A pleno; Trilho B começa a propor (fila, humano). |
| ≥ 14 (PRODUCTION) | regime completo do BEAST portado. |
| graduação sem RPC medido | **MaxConv SEM alvo** (não é estratégia baseada em meta → não convergiu para gasto autorizado; SMART-BIDDING §7.5) ou adiar — nunca meta inventada. Com RPC medido: teto `RPC ÷ k`. |

### 5.4 O instrumento que fecha três cortes — caminho crítico

O evento de **ad-view** do sensor (anúncio efetivamente visto na página, com
valor estimado) é uma coleta e três usos:

1. **`avg_ads_per_session`** — o 2º fator do RPC, hoje medido em só 9 de 33
   linhas. Sem ele, a frase-norte do produto ("o CVR caiu porque a página 3
   segura só 40% do scroll") não tem a metade dos anúncios.
2. **O valor da conversão offline** — `site_visits.conversion_value_calculated`
   está NULL em 9.468/9.468. O upload `UPLOAD_CLICKS` precisa de valor por
   gclid; é o ad-view que o dá (soma de views × eCPM estimado da sessão).
3. **O consumidor de `niche_conversion_mappings`** — o `AW-id/label` que a
   porta de criação persiste (§2.4) é lido pelo sensor/GTM para disparar o
   evento certo por nicho.

O loop da junta 4 fica: sensor → `site_visits` (com valor) →
`conversion_queue` → job de upload em lote (backend, `conversion_batches`,
diagnóstico do upload gravado) → Google Ads. As três campanhas de fevereiro
rodaram meses em MaxConv **sem um único sinal** — é a intervenção com melhor
razão retorno/esforço do sistema, e agora sem bloqueio: o dado já é capturado
e a ação de conversão nasce com a campanha.

Enquadramento na trava (P3/P4): o upload é a única escrita **contínua** no
Google Ads fora do modelo de Propostas — e influencia gasto, porque alimenta
o Smart Bidding. Por isso ele não roda por convenção: exige a autorização
permanente própria (`classe='UPLOAD_CONVERSAO'`, §1.3), criada pelo dono ao
ligar o PRD F5, revogável a qualquer momento, parada pelo kill switch global,
e auditada lote a lote em `conversion_batches` + recibo.

### 5.5 Preditivo — o que sobrevive da bola de cristal

Sobrevive a **arquitetura** (dois estágios: gasto é decisão, receita é
resposta; `planned_spend` como gancho de simulação; intervalo que soma
resíduo recente + volatilidade + discordância entre modelos) e o
**vocabulário de saída** (com `prevista_para` explícito). Morre o resto:
features que contêm o alvo (R² 1,000 in-sample medido), `boost_factor`
(constante disfarçada), XGBoost em 23 linhas de dado, `is_payday` sem
dia-da-semana, o teto por `budget_amount` (58% dos dias reais estouraram o
orçamento — o limite do Google é 2×).

Regras de existência: nasce desligado; liga por campanha com ≥ 12 dias; toda
previsão persiste em `previsoes` com o baseline ao lado; só entra como veto
do árbitro (nunca como executor) e só depois de bater o baseline em janela
móvel de 14 dias. **A direção de longo prazo é modelar a identidade do
negócio** (prever eCPM e páginas/sessão separadamente e compor o RPC) — é o
que dá previsão para funil novo por transferência de vertical e diagnóstico
de queda por fator; fica registrado como norte, não como fase.

---

## 6. O front — como as telas passam a compor

O princípio: **as telas são projeções de três substantivos** — Campanha (e
sua cadeia pauta→funil), Proposta e Saúde. Nenhuma tela nova inventa
vocabulário.

| tela | é | o que mostra |
|---|---|---|
| Pautador Pro (existe) | kanban | pauta → oportunidade → mineração |
| Redator (existe) | detalhe | funil, páginas, status WP (com o alarme de rascunho: 7 de 9 páginas em draft é fator 1 do RPC vazando) |
| Cockpit `/trafego/nova` (existe) | escada | nascimento: origem → keywords → copy → conta → **Mesa de Lance** (estratégia, graduação **e autorização de defesa** — mesmo gesto) → prova → selo → subir |
| **Carteira** (nova) | lista + fila | `vw_carteira`: "destas N, estas 6 querem algo de você hoje". A fila agrupa por direção: **REDUZ executadas** (informar — "o sistema defendeu você às 3h"), **AUMENTA pendentes** (aprovar/vetar, em lote), **ALERTA** (ler). Reversibilidade visível em cada card. |
| Detalhe de campanha (reformada) | diagnóstico | a equação decomposta (`vw_arbitragem_diaria`): spread e os 3 fatores lado a lado, cada um com "medido/não medido"; linha do tempo de `propostas`+`execucoes` (substitui OrientacaoBox/OtimizacaoBox/BiddingActionBox — os três viram render de Proposta); comportamento por página do funil (via `campaign_funnel_urls`→`fact_page_daily`) |
| **Saúde** (nova) | painel | `vw_saude`: frescor por fonte, heartbeat, contas de monetização com estado e histórico, alertas abertos. A tela que faltou por seis meses. |

Subir campanha e ajustar campanha são o mesmo gesto em dois momentos: ambos
criam uma Proposta que atravessa a mesma porta com a mesma escada. O operador
aprende **um** modelo mental.

---

## 7. Extensão para outros canais

Search fecha o ciclo primeiro; PMax, Display e Demand Gen entram sem
reescrever front nem domínio, porque as três costuras já são canal-agnósticas:

1. **Perfil de canal** (já no SPEC-FRONT §2): cada canal declara estágios do
   cockpit, campos do pedido e provas do `validate_only`. O front lê o
   perfil; não há `if canal ===` espalhado. Só SEARCH tem tela; os outros
   existem como forma no tipo.
2. **Proposta é canal-agnóstica**: `tipo` + `direcao` + `params` não sabem o
   que é keyword. Um ajuste de tROAS de PMax é `AJUSTAR_LANCE` com params
   próprios. O Executor ganha um **adaptador por canal** (updateMask e corpo
   por estratégia — a tabela que o Apply Bidding tinha e jogava fora).
3. **Política por canal**: `politicas_decisao.parametros` versionados por
   (perfil, canal). O k≈0,70 é do Search; Display terá o seu, medido.

A doutrina P7 (um termo, uma campanha) é do Search; cada canal novo entra com
a sua doutrina escrita **antes** da primeira campanha, no mesmo formato.

---

## 8. Observabilidade e segurança

### 8.1 Como se sabe que está funcionando — e que parou

- **Recibos** (`recibos_ingestao`, `execucoes`): toda escrita conta linhas.
  `VAZIO` é um estado com causa ("a Join devolveu 0 linhas para hoje às
  06:00" — comportamento normal medido — é diferente de "o job não rodou").
- **Watchdog invertido**: pg_cron (4.720/4.720) roda a cada 15 min uma função
  SQL que compara recibos e heartbeat contra `cadencia_esperada` e materializa
  `alertas` (com dedupe por chave). O backend pode morrer inteiro — o vigia
  não mora nele.
- **Monitor de monetização**: receita esperada vs observada por conta;
  `ultimo_sinal` velho demais → `AVISO`; zerada com custo correndo →
  `CRITICO` + Proposta REDUZ (limiares definidos no §1.5).
- **O vigia de fora do box**: todo o aparato acima mora numa máquina só — se
  o box cair, o alerta viraria uma linha que ninguém lê enquanto as campanhas
  gastam no Google. Por isso o backend pinga um **dead-man's switch externo**
  (healthchecks.io / UptimeRobot ou equivalente) a cada 5 min, e só pinga se
  `heartbeats` está fresco **e** não há alerta `CRITICO` aberto; ping ausente
  → o serviço externo notifica por conta própria. O box inteiro pode morrer —
  o aviso chega mesmo assim (aceite do PRD F1: notificação em ≤ 15 min com o
  backend morto, sem religar e sem ninguém olhando painel). É a diferença
  entre *detectar* que parou e *perceber* que parou.
- **Notificação**: alertas `CRITICO` saem por e-mail (canal que já existe na
  casa) a partir do backend; o painel de Saúde é a fonte da verdade, o e-mail
  é o toque no ombro.
- **Auditoria de divergência**: a verificação pós-execução (§1.4) fecha o
  ciclo — o que o sistema acha que fez é conferido contra o que o Google diz
  que ficou.

### 8.2 Que segredo mora onde

| segredo | mora | nunca |
|---|---|---|
| `service_role` do Supabase | `.env` do servidor Hetzner + `.env.server` local | no browser, no git |
| OAuth Google Ads (refresh token) + developer token | backend (Hetzner) | em nó de flow, em header montado à mão |
| chave exchangerate, token JoinAds | backend | no path de URL (era o vazamento do parque antigo) |
| anon key + URL do Supabase | bundle do front (é o desenho do PostgREST) | — |
| URL de webhook que muta conta | **não existe mais** | — |

Higiene de dia zero (PRD F0): rotacionar developer token e chave exchangerate
— o catálogo encontrou os três vazamentos **em claro** na primeira exportação
do inventário; a cópia atual já está re-sanitizada (`«CENSURADO»`, verificado
em 19/08), mas os valores existiram em dumps anteriores e a rotação não é
opcional. Manter no baixador a varredura de `jsonHeaders`/`jsonBody`/`jsCode`
e de segredos em path de URL (censura só por nome de campo foi o furo).
Desligar os **15 flows ativos** que apontam para o hospedado (a URL aparece em
18 arquivos; 3 já estão inativos), desativar os 6 formulários públicos da
Factory v3, matar o webhook `1cb2069d` e removê-lo do bundle.

### 8.3 Autenticação da porta

O front autentica no backend (sessão Supabase Auth já existente); toda rota
de Proposta/Execução exige usuário; aprovação registra `aprovada_por`. O
PostgREST continua servindo **leitura** ao front; mutação de domínio
(propostas, autorizações) só via backend — RLS nas tabelas novas nega escrita
ao role anon por construção.

---

## 9. Enterros e joias — o destino de cada peça

**Enterrar (extração concluída por este SPEC):**

| peça | o que se extrai antes de enterrar |
|---|---|
| `atuacao-orakul-ai-agent-webgo` (4.812 linhas, ativo) | fórmula de lance, multiplicadores, árbitro, confidence score → `politicas_decisao` + motor |
| `orakul-vos-auto-adjust` (BEAST) | a fila de ações → `propostas`; modos, floors, caps, histerese, evento externo → política |
| `orakul-02-analysis-engine` | só o SQL de reentrância (`last_analysis_at`) |
| `orakul-predictive-integrado-v1` | o ÁRBITRO (veto com motivos), o desfibrilador (desarmado até haver match_rate), `is_payday` como pergunta a validar |
| `bola-de-cristal-preditivo` (3 rotas) | dois estágios, conformal, `planned_spend`, vocabulário → §5.5 |
| `gads-new-campaign-validation` (NEXUS v3/v4.9) | `SUPER_GRADUATION`; cooldown por tabela |
| `gads-campaign-search` (porta ClickUp — **já morta desde 24/02**) | conversão sintética, isenção preventiva de policy, `finalUrlSuffix` 5 macros + `?sl=`, blindagem DKI, prompt SNIPER (versionado em arquivo). A sonda `[BROAD-MINING]` a 70% **não entra no nascimento** (P7: um conjunto, phrase) — vira opção do evento de graduação, forma a decidir pelo dono (§10.5) |
| `criacao-gads-factory-v3` (6 formulários públicos) | filtro de keywords (LOW/MEDIUM, dedupe, cap 50), fallbacks de Ad Strength; **desativar os formulários é segurança, não limpeza** |
| `pauta-recomendador-semantico-p3` | gate `_index >= 2` e o grafo de dependência entre benefícios — como **dados** |
| `front-webgo-new-dashboards`, `front-vincular-campanha-operador` | `parseMoneyToUSD`; `Decidir cada campanha` (junção por chave, `vaiVincular`, motivos legíveis) e a **guarda do teto de 10.000 do `change_event`** — lançar erro em vez de truncar, postura a adotar também para o teto do PostgREST → função do backend quando Memberships voltar ao escopo |
| `receita-gam-*`, `custo-gads-*` (hospedado) | pares D0/D-1 com mesmo `on_conflict` (conceito), poll SOAP com backoff, lote de 500 com soma prévia, Beast Parser v2 |
| `gads-search-terms-upgrade-kw` | o tribunal por estágios → SQL (§5.1) |
| `pauta-kw-minning-pautador-pro` (**vivo, aponta certo**) | continua até o porte; dois consertos pontuais no PRD F1 — o PATCH final grava `mined` em vez de `mining`, e o lote de seeds deixa de cair inteiro na colisão 409 |

**As dez joias portadas, com destino:** contrato "grava fino, banco engorda"
(→ triggers mantidos); pares D0/D-1 idempotentes (→ jobs parametrizáveis por
data); Beast Parser v2 (→ módulo de ingestão GAM, quando houver GAM); flows
JoinAds inteiros (→ molde do ingestor); fila de ações com mérito/permissão
separados (→ `propostas`); modos por idade + floors + caps + histerese (→
política); árbitro com motivos (→ motor); `cpc_alvo = rpc×mult` com escada e
piso (→ política); Time Warp com lista de dívida (→ config por idioma no
pautador); `exemptPolicyViolationKeys` preventivo (→ `volc_ads`, tabela
nicho→policies).

---

## 10. O que este SPEC não decide — e onde isso fecha

1. **Quem chama `compute_funnel_daily`** — fantasma fora de `cron.job`, dos 30
   flows e do repo. Caçar no F0/F1 (candidatos: os 37 flows ativos fora do
   núcleo — maioria de outros clientes, mas é onde eu olharia primeiro).
2. **A propriedade do sensor** (worker/GTM fora do repo) — descoberta é a
   primeira tarefa do F5; o risco de o dono do código não estar acessível é o
   maior risco daquela fase.
3. **Memberships/operadores** (`campaign_members` etc.) — fora do núcleo da
   arbitragem; volta ao escopo quando houver mais de um operador na operação
   nova.
4. **Ferramenta de Ajuste de Metas do Google** (citada no doc de Smart
   Bidding, nunca aberta) — avaliar quando a primeira campanha graduar.
5. **A forma da sonda broad pós-graduação.** O `[BROAD-MINING]` do flow morto
   minerava search terms a 70% do lance — mas num segundo ad group **no
   nascimento**, o que viola a doutrina (P7 + restrição 5: broad é a
   recompensa da graduação). Se a sonda volta como segundo ad group *da
   graduação em diante* ou como campanha irmã (um termo, um conjunto), é
   decisão do dono, registrada antes da primeira graduação (PRD F6).
