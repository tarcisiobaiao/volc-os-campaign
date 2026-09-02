# Pacote único de autorização — ativação da ingestão Google Ads campanha-dia

**Tarefa:** P10-T16 · **Lane:** `sprint/hermes-p10-t16-n8n-ledger-v12-v1`
**Base:** `b6e226ab2f6d339d2c7c899b83b05ff4a95ebcac` · **Data:** 01/09/2026
**Estado:** ⛔ **NADA FOI EXECUTADO.** Este documento é o pedido, não o registro.

Este é o **único** pacote de autorização desta entrega. Nenhum passo abaixo foi
executado: a migration não foi aplicada, o canário não rodou, os workflows não
foram importados nem ativados, e nenhum timer foi instalado. Enquanto os passos
5 a 8 não acontecerem com autorização explícita, **P10-T16 permanece `partial`**.

---

## O que já está pronto e provado (offline)

| Artefato | Estado | Prova |
|---|---|---|
| `supabase/migrations/v12_04_gads_fato_canonico_dia.sql` | escrita, **não aplicada** | ciclo aplicar→operar→reverter→reaplicar, 107 provas, Postgres descartável |
| `supabase/migrations/v12_04_rollback.sql` | escrito, **não executado em produção** | executado no descartável; recusa perda silenciosa sem declaração |
| `n8n/volc_gads_campanha_dia_d0.json` | gerado, **inativo, não importado** | 339 provas de validação nó a nó |
| `n8n/volc_gads_campanha_dia_d1.json` | gerado, **inativo, não importado** | idem |
| JavaScript dos Code nodes | executado offline | 65 provas com relógio injetado, zero rede |
| Costura fluxo↔RPC | provada | 12 provas ponta a ponta contra a v12_04 real |

## O que NÃO está provado, e ninguém deve supor que esteja

1. **`REAL_N8N_READ_NOT_PROVEN`.** Não havia credencial de n8n no ambiente desta
   lane. O estado real da instância viva não foi lido: nem os IDs, nem as
   versões, nem quais workflows estão ativos agora.
2. **`REAL_GOOGLE_ADS_READ_NOT_PROVEN`.** Nenhuma chamada real à Google Ads API
   foi feita. Os 27 campos GAQL existem nos *descriptors* do SDK v25 instalado
   (google-ads 31.4.0), o que prova que o campo existe no recurso — **não** que o
   par (recurso, campo) é selecionável em GAQL. Só `google_ads_field` responde
   isso, e só a API responde `google_ads_field`.
3. **Injeção do `developer-token`.** O nó do Google usa
   `={{ $credentials.developerToken }}` no cabeçalho. Isso não foi executado
   contra um n8n real. Se a instância não resolver `$credentials` ali, o passo 6
   falha com 401 e a correção é escolher outro caminho de injeção — nunca
   escrever o token no JSON.
4. **Agenda única na instância viva.** Ver o passo 1: cinco workflows da família
   aparecem com agenda **ativa** no inventário de 19/08/2026.

---

## Pré-condições (todas obrigatórias, todas humanas)

- [ ] **P1.** Autorização explícita do dono para escrever no Supabase oficial.
- [ ] **P2.** Backup conferido do banco oficial, no padrão da v12_01
      (`pg_dump` + `pg_restore --list` com contagem de objetos), com data e caminho
      registrados neste documento depois de feito.
- [ ] **P3.** Credencial n8n `VOLC Google Ads` existente e válida, com developer
      token no cofre do n8n — **nunca** no JSON, nunca em `.env` do repositório.
- [ ] **P4.** Conta-canário escolhida e uma janela de UM dia definida.
- [ ] **P5.** `python3 scripts/verificar_autoridade_supabase.py` verde na máquina
      que vai executar.

---

## Sequência de ativação

Os passos são ordenados e **não podem ser reordenados**: cada um só existe porque
o anterior aconteceu.

### Passo 1 — conferir a agenda viva ANTES de qualquer coisa

No painel do n8n, localizar por ID e registrar o estado atual:

| Papel | ID documentado | Estado esperado | Estado medido |
|---|---|---|---|
| D0 (hoje) | `hN15qFAVOqH0135q` | inativo | _(preencher)_ |
| D-1 (ontem) | `tKUItcd0AoD9mozV` | inativo | _(preencher)_ |

Depois, conferir os candidatos a agenda duplicada apontados por
`python3 scripts/gate_agenda_unica_gads.py` (inventário de 19/08/2026):

| Slug | Camada | Ativo em 19/08 | Estado medido | Decisão |
|---|---|---|---|---|
| `custo-gads-report` | custo | sim | _(preencher)_ | _(manter / desligar / é o D0)_ |
| `custo-gads-report-d1` | custo | sim | _(preencher)_ | _(manter / desligar / é o D-1)_ |
| `custo-gads-placements-display` | custo | sim | _(preencher)_ | _(outra granularidade?)_ |
| `custo-gads-placements-display-d1` | custo | sim | _(preencher)_ | _(outra granularidade?)_ |
| `criacao-gads-factory-v3` | criação | sim | _(preencher)_ | _(não é ingestão de custo)_ |

⛔ **Não avance** enquanto houver um workflow ativo que escreva campanha-dia. Duas
agendas na mesma família fazem o cursor andar duas vezes — e é literalmente o
defeito que P10-T16 fecha.

### Passo 2 — aplicar a migration v12_04

```bash
# preflight: o descartável primeiro, sempre
bash scripts/provar-ciclo-v12_04.sh          # esperado: passaram 107 · falharam 0

# só então, no oficial, com backup do P2 conferido
cat supabase/migrations/v12_04_gads_fato_canonico_dia.sql \
  | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
    "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
```

Conferir depois, **em leitura**:

```sql
select count(*) from pg_tables
 where schemaname='public'
   and tablename in ('trafego_coleta_execucao','google_ads_campanha_dia');            -- 2

select relname, relrowsecurity, relforcerowsecurity from pg_class c
  join pg_namespace n on n.oid=c.relnamespace
 where n.nspname='public'
   and relname in ('trafego_coleta_execucao','google_ads_campanha_dia');              -- t/t nas duas

select count(*) from information_schema.role_table_grants
 where table_schema='public'
   and table_name in ('trafego_coleta_execucao','google_ads_campanha_dia')
   and grantee in ('anon','authenticated','PUBLIC');                                   -- 0

select count(*) from information_schema.role_table_grants
 where table_schema='public'
   and table_name in ('trafego_coleta_execucao','google_ads_campanha_dia')
   and grantee='service_role'
   and privilege_type in ('INSERT','UPDATE','DELETE','TRUNCATE');                      -- 0
```

⚠️ Se `google_ads_campanha_dia` já existir, a migration **aborta com nome**: a
lane M-W2-02 pode ter aplicado `v13_01`. Nesse caso, PARE e decida qual é a
autoridade antes de qualquer coisa — não force.

### Passo 3 — importar os dois workflows, INATIVOS

Importar `n8n/volc_gads_campanha_dia_d0.json` e `…_d1.json` pelo painel. Manter
`active: false`. Depois, no `Config` de cada um, preencher **no n8n** (nunca no
repositório):

- `LOGIN_CUSTOMER_ID` = o MCC da carteira;
- `CONTAS_PERMITIDAS` = **apenas a conta-canário** do P4;
- `PASSO_FORCADO` = `canario` (torna a rodada repetível: repetir o canário
  devolve o recibo guardado em vez de criar outro).

Apontar a credencial `VOLC Google Ads` no nó `Google Ads: search` e a credencial
`VOLC Oficial` nos nós Supabase.

### Passo 4 — decidir sobre os workflows antigos

Com o par novo importado e o passo 1 respondido: desativar os workflows antigos
que escrevem campanha-dia, **um por vez**, registrando ID e horário. Não apagar —
desativar. Apagar destrói a única descrição do comportamento legado.

### Passo 5 — canário manual D-1, uma conta, um dia

Executar **manualmente** o workflow D-1 (botão "Test workflow"). Nada de agenda
ainda. Depois, conferir em leitura:

```sql
-- o recibo de fechamento existe, e resolve exatamente as linhas persistidas
select execucao_chave, resultado, motivo, linhas_lidas, linhas_aceitas,
       linhas_preteridas, linhas_rejeitadas, projecao_estado, projecao_linhas
  from public.trafego_coleta_execucao
 where tipo_lote='fechamento' order by encerrada_em desc limit 1;

-- a contagem do ledger bate com a tabela
select (select sum(linhas_aceitas) from public.trafego_coleta_execucao
         where execucao_chave = :chave and tipo_lote='contas') as ledger,
       (select count(*) from public.google_ads_campanha_dia g
          join public.trafego_coleta_execucao e on e.execucao_id=g.execucao_id
         where e.execucao_chave = :chave and e.tipo_lote='contas') as tabela;

-- NULL != 0 sobreviveu à ida real
select count(*) filter (where impressoes is null)  as nao_medidas,
       count(*) filter (where impressoes = 0)      as zero_medido
  from public.google_ads_campanha_dia where metric_date = :dia;
```

E reconciliar contra a fonte: abrir o relatório da conta no Google Ads para o
mesmo dia e comparar impressões, cliques e custo campanha a campanha. **Divergência
é motivo de parada**, não de ajuste no banco.

### Passo 6 — canário manual D0, mesma conta

Executar o D0 manualmente. Conferir que:

- ele **não** rebaixou a linha que o D-1 escreveu (`linhas_preteridas > 0` no
  recibo e `origem_janela = 'D-1'` no fato, se a data for a mesma);
- a data de hoje entrou com `origem_janela = 'D0'` e `janela_fechada = false`.

### Passo 7 — repetição idempotente

Executar o **mesmo** canário D-1 de novo, sem mudar nada. Esperado: nenhuma linha
nova em `google_ads_campanha_dia`, nenhum recibo novo em
`trafego_coleta_execucao`, e a RPC devolvendo `repetida: true`.

### Passo 8 — projeção de compatibilidade e telas legadas

```sql
select campaign_id, date, impressions, clicks, spend, conversions,
       revenue, revenue_converted, revenue_converted_revshare,
       orientacao_resumo, otimizacao_resumo, updated_at
  from public.daily_campaign_metrics
 where date = :dia and campaign_id in (:campanhas_do_canario);
```

Conferir, com os valores anotados **antes** do passo 5:

- entrega (impressões, cliques, spend, conversões, taxas) atualizada;
- receita, revshare, GAM, comissão, orientação e otimização **idênticas**;
- onde o canônico é NULL, a legada ficou NULL — nunca zero.

Abrir as telas que leem `daily_campaign_metrics` e confirmar que continuam
carregando.

### Passo 9 — ativar UMA agenda

Só agora: ativar **o D-1 primeiro** e observar uma janela completa (24 h). Com o
D-1 estável, ativar o D0. Remover `PASSO_FORCADO` e ampliar `CONTAS_PERMITIDAS`
(vazio = todas as contas do inventário) **depois** de o canário fechar limpo.

### Passo 10 — heartbeat, deadman e alerta

```sql
select job, execucao_chave, resultado, batimento_em, idade_do_batimento
  from public.trafego_coleta_execucao_saude
 order by encerrada_em desc limit 10;
```

Ligar o alerta de rotina parada sobre `idade_do_batimento`, com a tolerância de
cada papel (D-1: 26 h; D0: 7 h). O contrato de classificação é
`docs/contracts/HEALTH-DEADMAN-GOOGLE-INTELLIGENCE.md` — `SAUDAVEL` nunca sai
apenas de tentativa ou batimento.

---

## Rollback

**Do workflow** (imediato, sem banco): desativar os dois no painel. O ledger é
append-only: o que já entrou continua sendo evidência, e nenhuma linha some.

**Do banco** (destrutivo, exige decisão):

```bash
{ echo "SET volc.rollback_v12_04_apagar_fatos = 'sim';"
  cat supabase/migrations/v12_04_rollback.sql; } \
| ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
    "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
```

Sem a linha `SET`, o rollback **recusa** e diz quantos fatos e recibos morreriam.
Isso é proposital.

⚠️ **O rollback não desfaz a projeção.** As colunas de entrega de
`daily_campaign_metrics` que a projeção escreveu ficam com os valores novos: o
valor anterior não foi guardado e inventar um seria pior do que declarar a lacuna.
Receita, revshare, GAM, comissão e orientação nunca foram tocadas.

---

## O que continua proibido depois da ativação

- qualquer `mutate` Google Ads nesta rotina — a família é somente leitura;
- instalar ou habilitar os timers de `deploy/google-intelligence/` enquanto a ADR
  `ADR-N8N-AUTORIDADE-DE-AGENDA.md` estiver de pé;
- escrever direto em `google_ads_campanha_dia` ou `trafego_coleta_execucao` — a
  única porta é a RPC, e `service_role` não tem permissão de escrita direta;
- criar linha nova em `daily_campaign_metrics` a partir da projeção;
- tratar `daily_campaign_metrics` como autoridade de custo Google Ads.

---

## Registro da execução (preencher ao executar)

| Passo | Quem | Quando | Resultado | Evidência |
|---|---|---|---|---|
| P2 backup | | | | |
| 1 agenda viva | | | | |
| 2 migration | | | | |
| 3 import | | | | |
| 4 desativação legada | | | | |
| 5 canário D-1 | | | | |
| 6 canário D0 | | | | |
| 7 repetição | | | | |
| 8 projeção | | | | |
| 9 agenda | | | | |
| 10 deadman | | | | |
