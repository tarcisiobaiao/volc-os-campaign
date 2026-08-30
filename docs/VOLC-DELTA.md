# VOLC-DELTA — o que separa este fork do webgo

O **VOLC O.S.** é um fork do **webgo** (`metro-campaign-view`). O webgo continua
evoluindo em branches `webgovN`; este repositório absorve essas evoluções por
`git merge`.

Este documento é o registro do que **sempre diverge**. Ele existe para que cada
sincronização futura seja mecânica em vez de arqueológica — sem ele, cada sync
recomeça a investigação do zero.

> **Regra de ouro:** toda vez que uma resolução de conflito for tomada num sync,
> ela vira uma entrada aqui. Se você resolveu um conflito e não documentou,
> o próximo sync vai pagar de novo.

---

## 1. Como sincronizar com uma nova versão do webgo

```bash
# 1. Rede de segurança — sempre, sem exceção
git branch backup/$(git branch --show-current)-pre-sync
git tag pre-webgovN-sync

# 2. Trazer o upstream
git fetch upstream --prune
git log --oneline HEAD..upstream/webgovN        # o que vem
git diff --stat HEAD upstream/webgovN | tail -1 # o tamanho do estrago

# 3. Simular ANTES de mexer no working tree
git merge-tree --write-tree HEAD upstream/webgovN

# 4. Merge de verdade
git checkout -b sync/webgovN
git merge upstream/webgovN
#    -> o rerere reaplica sozinho as resoluções já conhecidas (seção 3)
#    -> resolva o que sobrar e DOCUMENTE aqui

# 5. Podar o que não é do VOLC
./scripts/prune-pautador.sh
#    -> mais as edições manuais da seção 4

# 6. Provar que compila
npm ci && npx tsc --noEmit && npm run build && npm test

# 7. Conferir que o branding sobreviveu (seção 2)
git grep -in 'webgo' -- src/ index.html | grep -vE 'src/v6/(README\.md|featureFlag\.ts)'
git grep -n 'logo-webgocontent' -- src/
```

**Pré-requisito, uma vez por clone:**

```bash
git remote add upstream https://github.com/tarcisiobaiao/metro-campaign-view.git
git config rerere.enabled true
git config rerere.autoUpdate true
```

O `rerere` é o que faz este processo barato. Ele grava a resolução de cada
conflito e a reaplica quando o mesmo conflito reaparece. As resoluções do sync
`webgov6` já estão gravadas em `.git/rr-cache` — **esse diretório não é
versionado pelo git**, então quem clonar do zero paga as resoluções de novo.
Se o time crescer, vale espelhar o `rr-cache`.

---

## 2. Branding — sempre resolver a favor do VOLC

| Arquivo | O que diverge |
|---|---|
| `index.html` | `<title>`, description, author, `og:title`, `og:description` |
| `README.md` | primeira linha |
| `src/components/layout/Layout.tsx` | header mobile: `/volc-logo-baixa.png`, alt `VOLC O.S.` |
| `src/components/layout/Navigation.tsx` | sidebar: mesmo logo e alt |
| `src/pages/Reports.tsx` | rodapé do PDF: `Sistema VOLC O.S. - Relatórios` |
| `src/sql/restructure_daily_project_metrics.sql` | comentário do cabeçalho |
| `backend/app/docx/volc_engine.py` | `brand` padrão do `VolcDocx` (autor, rodapé e logo da capa do DOCX) |
| `backend/app/docx/briefing_model.py` | `BRAND` — vai para o nome do arquivo (`Briefing_Funil_..._VOLC.docx`) e para a capa do HTML |

**`src/pages/Reports.tsx` é o de maior risco.** O webgo reescreve esse arquivo
pesadamente a cada versão (no `webgov6` foram +621 linhas), e a string do rodapé
reaparece deslocada. O auto-merge tem preservado, mas **confira sempre**:

```bash
grep -n 'Sistema VOLC O.S.' src/pages/Reports.tsx
```

O asset `public/volc-logo-baixa.png` só existe neste fork.
`public/logo-webgocontent-horizontal.png` continua no repo dos dois lados — não
é referenciado por nada aqui, e remover só criaria conflito à toa.

---

## 2b. ClickUp — DESLIGADO no VOLC O.S., e é decisão de produto

O webgo cria uma task no ClickUp quando o card chega em **Pronto**, anexa o
`.docx` do briefing e comenta. **No VOLC O.S. isso não acontece**, e o merge
NUNCA deve trazer esse comportamento de volta.

O motivo é de produto, não técnico: o VOLC O.S. concentra o log e a
documentação. Uma cópia num gerenciador externo vira uma segunda verdade que
nasce desatualizada no instante em que o funil muda — e aí ninguém sabe qual das
duas vale.

Medido antes de cortar: **0 de 20 cards** tinham `clickup_task_id`. A integração
nunca chegou a ser usada nesta instância.

| Arquivo | O que diverge |
|---|---|
| `backend/app/routers/entities.py` | `_dispatch_clickup_briefing` é **no-op** (`clickup_desligado_no_volc_os`); sem rota `POST .../clickup`, sem disparo automático em "Pronto", sem `_clickup_task_name`/`_clickup_description` |
| `backend/tests/test_clickup.py` | testa a AUSÊNCIA: nenhuma rota, nenhum helper, dispatch inerte |
| `src/components/pautador-pro/entity/EntityDrawer.tsx` | sem botão "Criar task ClickUp" e sem link "Task no ClickUp" — só `<BriefingAcoes>` |
| `src/pages/pautador-pro/PautadorProPage.tsx` | sem o `AlertDialog` de confirmação do skip |
| `src/hooks/pautador/useEntityPautador.ts` | sem `createClickupTask` / `clickupConfirm` |

**O que ficou de propósito, e não é esquecimento:**

- As colunas `clickup_task_id` / `clickup_task_url` seguem no banco. Estão
  vazias, e derrubar coluna é destrutivo por um ganho de nada.
- `backend/app/services/clickup_service.py` fica sem chamadores. Se a decisão
  um dia voltar, ele volta inteiro em vez de ser reescrito de memória.
- `task_description` no card virou **campo órfão**: era o corpo da task. Segue
  salvo e editável, e hoje ninguém o lê. Está marcado como órfão no tipo.

**Substituiu o quê:** o briefing virou página no próprio sistema
(`GET /entity-opportunities/{id}/briefing.html`, abre em nova aba, Ctrl+P vira
PDF) com o `.docx` sob demanda em `/briefing.docx`.

## 3. Arquivos estruturalmente propensos a conflito

Estes colidem a cada versão porque os dois lados mexem na mesma região.
O `rerere` já sabe resolver os quatro; a coluna "decisão" existe para quando
o contexto mudar e o rerere não casar.

### `src/pages/CampaignDetailDashboard.tsx` — trivial
Os dois lados inserem imports logo depois de `BiddingActionBox`.
**Decisão:** manter os três — `OtimizacaoBox` (nosso), `DisplayROITable` e
`PlacementNegationCard` (deles). É puramente aditivo.

### `.env.example` — moderado
Os dois lados acrescentam variáveis.
**Decisão:** somar, nunca escolher um lado. Preservar sempre
`VITE_SUPABASE_URL=https://database.agenciavolc.com.br` e `SECRET_KEY_BASE`.
Depois conferir que não duplicou nada:

```bash
for v in VITE_API_URL VITE_SITE_URL VITE_SUPABASE_URL; do echo "$v: $(grep -c "^$v=" .env.example)"; done
```

### `src/pages/GeneralDashboard.tsx` — delicado
Duas linhas de webhook n8n. O host e os UUIDs divergem.
**Decisão (webgov6):** host do upstream + UUIDs do VOLC →
`https://fluxos.agenciavolc.com.br/webhook/e8c5cc2a-4154-4527-a5e3-f2cf84fae469`
e `.../43dd1321-07a0-42f0-a119-65c531ef73fc`.
**Confirme no painel do n8n antes de aceitar cegamente** — um webhook errado
falha em silêncio.

### `src/components/currency/FinalExchangeRateManager.tsx` — delicado
**Decisão:** ficar com a lógica funcional do upstream, mas roteada por
`secureApi` em vez de `supabase` direto (ver seção 5). A armadilha: nem toda
chamada a `secureApi` neste arquivo está dentro do bloco de conflito —
`loadExchangeRate` fica fora. Depois de resolver, confira:

```bash
grep -n 'supabase' src/components/currency/FinalExchangeRateManager.tsx   # deve não retornar nada
```

---

## 4. O que não entra: Pautador Pro

O webgo desenvolve o **Pautador Pro** (backend Python FastAPI + frontend de
arbitragem de atenção). Está fora do escopo do VOLC O.S.

Rode `./scripts/prune-pautador.sh` — ele remove a árvore inteira e é idempotente.
**O script não faz as edições em arquivos compartilhados.** Estas são manuais:

| Arquivo | Ação |
|---|---|
| `src/App.tsx` | remover import de `PautadorProPage` e a rota `/pautador-pro` |
| `src/components/layout/Navigation.tsx` | remover o item `Pautador Pro` de `navigationItems[]` e o ícone `Radar` do import de `lucide-react` |
| `package.json` | remover `dev:backend` e `dev:stop`; `dev:all` volta a ser `concurrently "npm run dev" "npm run dev:server"` |

### Armadilhas — o que PARECE Pautador e não é

| Item | Realidade |
|---|---|
| `src/v6/` | **RBAC/comissões por campanha. É núcleo.** Importado por `settings/UsersSettings.tsx`. Remover quebra o build. |
| `src/sql/v6_*.sql` | schema do RBAC v6 |
| `src/sql/v7_13_meta_capi_sites.sql` | Meta CAPI — só a série numérica coincide com as migrations do Pautador |
| `vitest.config.ts` | os únicos testes do repo são do Meta CAPI |
| `@dnd-kit/*` | usado pelo Kanban da **Incubadora** |
| `docs/archive/plans/incubadora-sites-plan.md` | plano histórico da **Incubadora** |

`src/sql/v7_13` chama `public.set_pautador_updated_at()`, criada originalmente
por uma migration do Pautador. O arquivo tem guarda idempotente que cria a
função se não existir — roda sozinho. Só o nome ficou.

---

## 5. Divergências funcionais deliberadas

### Supabase self-hosted
O webgo usa Supabase hosted (`*.supabase.co`); o VOLC usa self-hosted
(`https://database.agenciavolc.com.br`). Todo código do upstream que assume o
padrão hosted precisa de adaptação. Já corrigido em `src/lib/metaCapi/derive.ts`
(`deriveRouterFunctionUrl` aceita as duas formas). **Ao trazer feature nova do
upstream, procure por `.supabase.co` hardcoded:**

```bash
git grep -n 'supabase\.co' -- src/ api/ supabase/ server/
```

### Roteamento por `secureApi`
Este fork move chamadas ao Supabase do browser para o proxy `secureApi`
(`/api/supabase/*`), para não expor credencial no bundle. O upstream **não** faz
isso. Onde o fork já está à frente:

- `src/services/systemSettingsService.ts` — migrado por inteiro. O upstream nunca
  tocou nesse arquivo; em caso de conflito futuro, **a versão do fork vence**.
- `src/components/currency/FinalExchangeRateManager.tsx` — usa `secureApi.rpc()`
  para chamar `rpc_set_dollar_exchange_rate`.

A migração é parcial: `src/services/supabaseDataService.ts` (o maior serviço)
ainda fala direto com o Supabase pela anon key. É débito técnico conhecido.

### `OtimizacaoBox` — feature exclusiva do VOLC
`src/components/campaign/OtimizacaoBox.tsx` (152 linhas) + ~63 linhas de
integração em `CampaignDetailDashboard.tsx` (state `otimizacaoData`, `useEffect`
com `getServerDate`). Card "Auto Adjust Realizado", lê
`otimizacao_resumo` / `otimizacao_json` / `otimizacao_realizada_em` de
`daily_campaign_metrics`, só para a data de hoje.

O upstream **não tem nada equivalente** — `git grep otimizacao_ upstream/webgovN`
retorna vazio. As três colunas só existem no banco do VOLC e **não são criadas
por nenhuma migration versionada**; foram adicionadas à mão. Se o banco for
recriado do zero, elas somem.

---

## 6. Divergência de banco

As duas instâncias divergiram. Um sync de código **não** sincroniza banco.

### Só no VOLC — nunca destruir

Pipeline de tracking/conversão que o webgo não tem:

`raw_events` · `site_visits` · `fact_page_daily` · `fact_funnel_daily` ·
`conversion_queue` · `conversion_batches` · `bucket_weights` ·
`niche_conversion_mappings` · `adsense_daily_snapshots` · `sync_logs` ·
`vw_adsense_adjusted` · `vw_campaign_daily_revenue`

RPCs: `compute_funnel_daily` · `compute_page_daily` · `get_cta_intelligence` ·
`get_daily_intelligence` · `get_funnel_cro_intelligence` · `cleanup_old_events`

> Essa lista foi levantada com a **anon key**, que só enxerga o que tem GRANT.
> É um **piso, não um teto**. Antes de qualquer operação destrutiva, revalide
> com uma service_role válida.

### Colisões de schema conhecidas

| Objeto | Divergência |
|---|---|
| `campaigns` | webgo tem `campaign_url`; VOLC tem `lp_path` |
| `adsense_metrics` | VOLC tem 5 colunas a mais: `calculated_rpm`, `clicks`, `ctr`, `impressions`, `page_views` |
| `daily_campaign_metrics` | VOLC tem 7 a mais, incluindo as três `otimizacao_*` |
| `get_campaigns_aggregated` | webgo aceita `p_limit`/`p_offset`; VOLC ainda não |

**Consequência prática:** SQL vindo do webgo pode assumir coluna que aqui não
existe (e vice-versa). Sempre valide o DDL contra o schema do VOLC antes de aplicar.

### Como comparar os dois schemas

```bash
# VOLC (anon key funciona para leitura do schema)
cd /Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign
set -a && . ./.env && set +a
curl -s "$VITE_SUPABASE_URL/rest/v1/" -H "apikey: $VITE_SUPABASE_ANON_KEY" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('\n'.join(sorted(d['definitions'])))"

# RPCs
curl -s "$VITE_SUPABASE_URL/rest/v1/" -H "apikey: $VITE_SUPABASE_ANON_KEY" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('\n'.join(sorted(p[5:] for p in d['paths'] if p.startswith('/rpc/'))))"
```

Trocando as variáveis pelas do webgo (`.env.server` daquele repo) sai o outro lado.
`comm -13` entre as duas listas dá o que falta aqui.

---

## 7. Pendências abertas

| Pendência | Detalhe |
|---|---|
| **Credenciais expostas no histórico** | `git show 904cb0b:.env` ainda devolve `SUPABASE_SERVICE_ROLE_KEY` e `SECRET_KEY_BASE`. Remover do tree não removeu do histórico — **precisam ser rotacionadas**. |
| **Anon key é a demo padrão** | O JWT da anon key tem `iss: supabase-demo` — é a chave de exemplo do Supabase self-hosted. Se o JWT secret também for o default, qualquer um forja um token `service_role`. |
| **`/api/supabase/*` sem autenticação** | Os endpoints aceitam `table` e `functionName` arbitrários com a service_role key, CORS `*`, sem verificar quem chama. |
| **service_role key do VOLC inválida** | A que está no `.env` não é um JWT (401 em tudo). |
| **Edge runtime no self-hosted** | Não confirmado se o Docker expõe `/functions/v1`. Sem ele, a Edge Function `capi-router` do Meta CAPI não sobe. Verificar com: `curl -i https://database.agenciavolc.com.br/functions/v1/` |
| **Colunas `otimizacao_*` sem migration** | Existem só no banco. Se recriar do zero, o `OtimizacaoBox` para de funcionar. |
| **`useCampaignComparisons` tem `.limit(50000)`** | Truncamento silencioso dos deltas em períodos longos com muitas campanhas. |

---

## 8. Histórico de sincronizações

| Data | De | Para | Notas |
|---|---|---|---|
| 2026-08-05 | `bbdbd84` (webgov5.1) | `upstream/webgov6` | 63 commits. 4 conflitos. Núcleo + Meta CAPI + Incubadora entraram; Pautador Pro podado. Correção de premissa: `src/v6` é núcleo, não Pautador. |
