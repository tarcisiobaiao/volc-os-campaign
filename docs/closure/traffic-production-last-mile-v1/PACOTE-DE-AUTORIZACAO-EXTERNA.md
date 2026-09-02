# Pacote único de autorização externa

Este é o **único** ponto da missão que pede autorização. Tudo abaixo está
preparado, provado localmente e **não executado**. Nada aqui foi feito.

| | |
|---|---|
| Branch | `sprint/traffic-production-last-mile-v1` |
| Base | `c8ca8628e83742dd7da5242f0a015f76292aafe7` |
| HEAD | `97df0ee` |
| Destino único | `https://database.agenciavolc.com.br` (self-hosted, Hetzner `178.156.196.149`) |

---

## Estado factual de HOJE, medido — o que já é verdade sem autorização nenhuma

| Objeto | Estado no Supabase oficial | Como foi medido |
|---|---|---|
| `v12_02` plano de mensuração | **APLICADA**, 0 linhas (85 campanhas em `trafego_campanha`) | catálogo + `count(*)`, read-only |
| `v12_03` PMax observability | **NÃO aplicada** | CHECK `trafego_google_coleta_tipo` ainda tem só os 6 valores da v12_01 |
| `v12_04` fato canônico | **NÃO aplicada** | 0 de 3 relações, 0 de 4 funções |
| Ledger v10 | v10_01 ✅ · **v10_02 ❌** · v10_03 ✅ · v10_04 ✅ | catálogo, objeto a objeto |
| Campanha canário | **EXISTE e está PAUSED** | GAQL read-only hoje |
| Workflows D0/D-1 | versionados, **`active: false`** | campo `active` dos dois JSON |
| Agenda concorrente | **nenhuma** | `pg_cron` só tem 3 jobs, nenhum de tráfego; sem systemd/cron/launchd local |

---

## 1 · Aplicar a `v12_04` no Supabase oficial

### Arquivo exato e identidade

```
2934b1a2eb5c8c49299fb197215041ac810bacf83e29a6ab8ca3fb0fdfd5b0f2  supabase/migrations/v12_04_gads_fato_canonico_dia.sql   (1219 linhas)
583a2f7189db739feeed944cb3bd51e4a333a878cadbaa366ec9511cb95cbee3  supabase/migrations/v12_04_rollback.sql                 (80 linhas)
```

Confira na máquina de onde for aplicar. **Não bateu: PARE.**

```bash
shasum -a 256 supabase/migrations/v12_04_gads_fato_canonico_dia.sql
```

### Objetos que serão criados

**Tabelas** `public.trafego_coleta_execucao` · `public.google_ads_campanha_dia`
**View** `public.trafego_coleta_execucao_saude`
**Funções** `volc_registrar_gads_campanha_dia(jsonb)` · `volc_gads_projetar_daily_compat(uuid)` · `volc_gads_uuid_da_chave(text)` · `trafego_coleta_execucao_append_only()`
**Índices** 4 em cada tabela
**Trigger** append-only no ledger
**Grants** `service_role` recebe SELECT nas duas tabelas e na view, e EXECUTE só na RPC de ingestão. `anon` e `authenticated` ficam sem nada. RLS habilitada **e forçada**, zero policies.

### Objetos que NÃO serão tocados

`daily_campaign_metrics` não é criada, alterada, nem tem coluna/constraint/trigger
mexida. Ela recebe apenas uma **projeção** de compatibilidade, restrita às colunas
de entrega, e a projeção **nunca** encosta em receita, revshare, GAM, comissão,
orientação ou otimização. `trafego_campanha` (v9_01) é só referenciada por FK.

### Preflight (read-only, rode antes)

```sql
-- 1. a dependência existe?
select to_regclass('public.trafego_campanha');            -- precisa NÃO ser null

-- 2. os alvos estão livres? (a migration ABORTA sozinha se não estiverem)
select to_regclass('public.trafego_coleta_execucao'),
       to_regclass('public.google_ads_campanha_dia');      -- os dois precisam ser null

-- 3. a legada está como esperado?
select count(*) from public.daily_campaign_metrics;        -- registre o número
select count(*) from public.trafego_campanha;              -- registre o número

-- 4. a isolação é a que a projeção pressupõe?
show default_transaction_isolation;                        -- precisa ser 'read committed'
```

> ⚠️ O item 4 é material e **não foi medido**. A trava consultiva da projeção
> pressupõe `READ COMMITTED` — é ele que dá snapshot novo a cada instrução. Sob
> `REPEATABLE READ` a trava ainda serializa, mas a releitura de ambiguidade seria
> cega. Se não for `read committed`, aplique a migration e mantenha
> `projetar_compat: false` até haver prova sob a isolação em uso.

### Backup antes

```bash
ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  "docker exec supabase-db pg_dump -U postgres -Fc postgres > /root/backups/pre-v12_04-$(date +%Y%m%d-%H%M).dump && ls -la /root/backups/ | tail -3"
```

### Aplicar

```bash
cat supabase/migrations/v12_04_gads_fato_canonico_dia.sql | \
ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
```

### Rollback

Ele **recusa** rodar com dado gravado, a menos que a perda seja declarada — e essa
recusa está provada no ciclo:

```bash
{ echo "SET volc.rollback_v12_04_apagar_fatos = 'sim';";
  cat supabase/migrations/v12_04_rollback.sql; } | \
ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
```

⚠️ **O rollback NÃO desfaz a projeção** já escrita em `daily_campaign_metrics`.
É por isso que a projeção só escreve quando o documento pede `projetar_compat: true`,
e por isso ela recusa quando a linha legada é ambígua.

### Verificação posterior

```sql
select to_regclass('public.trafego_coleta_execucao'),
       to_regclass('public.google_ads_campanha_dia'),
       to_regclass('public.trafego_coleta_execucao_saude');
select count(*) from public.trafego_coleta_execucao;   -- 0 esperado
select count(*) from public.google_ads_campanha_dia;   -- 0 esperado
select has_table_privilege('anon','public.google_ads_campanha_dia','SELECT');       -- f
select has_function_privilege('anon','public.volc_registrar_gads_campanha_dia(jsonb)','EXECUTE'); -- f
select has_function_privilege('service_role','public.volc_registrar_gads_campanha_dia(jsonb)','EXECUTE'); -- t
select relrowsecurity, relforcerowsecurity from pg_class
 where relname in ('trafego_coleta_execucao','google_ads_campanha_dia');            -- t,t nas duas
select count(*) from public.daily_campaign_metrics;    -- IGUAL ao preflight
```

### Contraprovas que sustentam este pedido

| prova | resultado | o que ela mede |
|---|---|---|
| `scripts/provar-ciclo-v12_04.sh` | **107 / 0** | estrutura, segurança, comportamento, contenção, rollback, reaplicação |
| `scripts/provar-concorrencia-v12_04.sh` | **32 / 0** | as sete invariantes com DUAS sessões reais; contra o código base, 16 de 23 falhavam |
| `scripts/provar-ponta-a-ponta-gads.sh` | **17 / 0** | os documentos que o n8n produz, aceitos pela RPC real |

---

## 2 · Importar os workflows n8n (SEM ativar)

```
1c652a24ab4cdf2a09d279c9272a29f4cba24bfd40ab0b1efe650c8006e264da  n8n/volc_gads_campanha_dia_d0.json
8ce36ae24cd0ccd65f0f0ba15294aca3e4b9765db99fd97ac2f917e557aa1b4a  n8n/volc_gads_campanha_dia_d1.json
```

- Os dois têm **`active: false`** e devem ser importados assim.
- Agenda declarada: D0 `0 6,12,18,23 * * *` · D-1 `0 6 * * *`, fuso `America/Sao_Paulo`.
- **Antes de qualquer execução**, dois campos precisam ser preenchidos à mão:
  `googleAdsOAuth2Api.id` está como `REPLACE_ME`, e `LOGIN_CUSTOMER_ID` está vazio.
  Enquanto estiverem assim, uma execução falharia como 401 classificado.
- Credenciais são referenciadas por id/nome. **Nenhum segredo no JSON** — verificado.

**Autorização para IMPORTAR é separada da autorização para ATIVAR.** Importar
inativo não coleta nada e não gasta nada.

### Risco de agenda duplicada

Medido: `pg_cron` tem 3 jobs e nenhum é de tráfego; não há systemd, cron ou
launchd local disparando esta coleta; nenhum artefato executável chama a API de
ativação do n8n. **Mas a instância n8n viva não foi lida** (sem credencial nesta
máquina), e o inventário versionado mostra 5 workflows da família já ativos, dois
deles com papel D0/D-1 e chamando a RPC legada. **Antes de ativar, alguém precisa
listar os workflows ativos na instância e desligar os antigos.** Comando:

```bash
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" "$N8N_URL/api/v1/workflows?active=true"
```

---

## 3 · O que NÃO estou pedindo autorização para fazer

Nenhuma destas está preparada, e nenhuma deve ser feita agora:

- **ativar** qualquer workflow ou campanha;
- aplicar a **v12_03** (fora do escopo desta missão; segue não aplicada);
- escrever no **Data Manager** (`data_manager.enviar()` levanta exceção sempre —
  sem flag, sem HTTP, sem credencial: a capacidade não existe, e está declarada
  como inexistente);
- criar ou alterar **ConversionAction**, meta, orçamento, anúncio ou campanha;
- instalar **systemd/timer**;
- **deploy**, **merge** ou **push**.

---

## 4 · Smart Bidding continua FECHADO, e agora se sabe por quê

Três bloqueadores independentes, todos **lidos** da conta hoje, nenhum inferido:

1. `goal_config_level = CUSTOMER` — a campanha herda a conta. A única meta
   *biddable* é `DOWNLOAD/APP`, e a única ação que a mede é
   `ANDROID_INSTALLS_ALL_OTHER_APPS` com `primary_for_goal = False`
   (presence=True: declarado falso, não ausente). As 8 ações primárias e
   habilitadas da conta são todas `PURCHASE/WEBSITE` — a categoria cujo
   `biddable` é `false`. Na prática o lance automático não teria o que perseguir.
2. **`include_in_conversions_metric = False` nas 10 ações**, com presence=True —
   explicitamente desligado. Mesmo que uma conversão dispare, ela não entra em
   `metrics.conversions`. **Este achado é novo e não estava registrado em lugar
   nenhum.**
3. `frescor.estado = inelegivel`, `destino.resolvido = false` (Data Manager),
   `acao_alvo = null`, plano com 2 bloqueadores e `completo = false`.

Nenhum destes se resolve aplicando migration. Os três são decisões na conta
Google Ads, e o item 2 sozinho impediria qualquer número de aparecer.
