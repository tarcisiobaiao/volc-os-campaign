# IR-0 — preparação da resposta ao incidente

**Companheiro de:** [`INCIDENTE-JWT-SECRET.md`](./INCIDENTE-JWT-SECRET.md)
**Data:** 26/08/2026 · **Estado:** preparado, **nada executado**

> Nenhum segredo, hash, prefixo ou tamanho aparece neste documento. As
> verificações imprimiram só veredito, contagem e carimbo.

---

## 0. O escopo cresceu

O incidente foi aberto sobre o `JWT_SECRET`. A auditoria dos demais defaults
mostrou que **o `.env` inteiro é o arquivo de exemplo**: os valores não-secretos
foram ajustados, e os secretos, não.

**13 de 17 segredos críticos são o valor publicado.**

Isto muda a natureza do problema. Não é "alguém pode forjar um token" — é
**"as chaves estão publicadas"**. Não há forja: há cópia.

⚠️ **A memória do projeto está errada.** Ela registra que "as chaves de API
foram regeneradas uma vez" e que arquivos antigos estariam defasados. O `.env`
vivo tem `mtime` de **18/02/2026** — a data da instalação — e é idêntico ao
exemplo nos campos que importam. Ou a regeneração nunca alcançou este arquivo,
ou uma reinstalação a desfez.

---

## 1. Evidências preservadas — **antes** de qualquer reinício

`/root/incidente-jwt-20260826/` · diretório `700`, todos os arquivos `600`,
fora do Git, **51 MB**.

### Cobertura de cada log

| serviço | linhas | de | até |
|---|---:|---|---|
| `supabase-kong` | 70.843 | **2026-07-26 07:10** | 2026-08-26 16:31 |
| `supabase-auth` | 3.335 | 2026-02-03 16:50 | 2026-08-26 15:49 |
| `supabase-rest` | 1.528 | 2026-02-03 16:50 | 2026-08-25 10:58 |
| `supabase-db` | 10.648 | 2026-02-03 16:50 | 2026-08-26 16:00 |
| `supabase-analytics` | 242.751 | **2026-08-21 10:20** | 2026-08-26 16:47 |
| `supabase-pooler` | 141.653 | **2026-08-18 10:57** | 2026-08-26 16:47 |
| `supabase-edge-functions` | 23.921 | 2026-02-18 23:53 | 2026-08-26 06:32 |
| `realtime` | 3.415 | 2026-02-03 16:50 | 2026-08-26 13:20 |
| `supabase-storage` | 31 | 2026-02-03 16:50 | 2026-08-05 18:20 |
| `supabase-meta` | 57 | 2026-02-03 16:50 | 2026-08-05 18:18 |
| `supabase-vector` | 837 | 2026-02-03 16:50 | 2026-08-05 19:18 |
| `supabase-studio` | 18 | 2026-02-03 16:50 | 2026-08-05 18:17 |
| `supabase-imgproxy` | 16 | 2026-02-03 16:50 | 2026-08-05 18:17 |

⚠️ **A janela do gateway começa em 26/07.** O Kong é o único log que veria abuso
pela borda, e ele cobre **31 dias** de uma instância que existe desde
**03/02**. Cinco meses e meio de tráfego de borda **não existem mais**. Qualquer
conclusão sobre "não houve uso indevido" está limitada a essa janela — e a
ausência de evidência aqui não é evidência de ausência.

### Banco

| arquivo | conteúdo |
|---|---|
| `banco/pg_stat_statements.csv` | 4.742 consultas — texto e contadores, **sem parâmetros** |
| `banco/schema.sql` | 19.802 linhas, `--schema-only` |
| `banco/grants.psv` | 322 linhas · `public`, `auth`, `storage`, `app_auth` |
| `banco/rls.psv` | 100 tabelas com `rowsecurity` e nº de policies |
| `banco/security_definer.psv` | 26 funções `SECURITY DEFINER` com dono e `search_path` |
| `banco/extensoes.psv` | 11 extensões |
| `banco/ev_users.csv` | 1 conta — id, carimbos, `md5(email)`. **Sem e-mail, sem hash de senha** |
| `banco/ev_sessoes.csv` | 3 sessões vivas |
| `banco/ev_refresh.csv` | 14 refresh tokens (3 não revogados) — **sem o token** |

### Configuração

`config/HASHES.tsv` — sha256, bytes e mtime de `.env`, `docker-compose.yml`,
`kong.yml`, `.env.example`, `vector.yml` e o backup `kong.yml.bak-20260805`.

Cópias íntegras de `docker-compose.yml` e `kong.yml`. **Verificado: nenhuma das
duas carrega segredo** — o `kong.yml` em disco é o TEMPLATE, com
`$DASHBOARD_USERNAME` e afins; a substituição acontece no entrypoint. O `.env`
**não foi copiado**: dele só ficou o hash.

---

## 2. Auditoria de defaults — sanitizada

Comparação `==` contra o `.env.example` instalado ao lado, que é o distribuído
pelo Supabase. Sem valor, sem hash, sem prefixo, sem tamanho.

| chave | veredito |
|---|---|
| `POSTGRES_PASSWORD` | **DEFAULT_INSEGURO** |
| `JWT_SECRET` | **DEFAULT_INSEGURO** |
| `ANON_KEY` | **DEFAULT_INSEGURO** |
| `SERVICE_ROLE_KEY` | **DEFAULT_INSEGURO** |
| `DASHBOARD_USERNAME` | **DEFAULT_INSEGURO** |
| `DASHBOARD_PASSWORD` | **DEFAULT_INSEGURO** |
| `SECRET_KEY_BASE` | **DEFAULT_INSEGURO** |
| `VAULT_ENC_KEY` | **DEFAULT_INSEGURO** |
| `PG_META_CRYPTO_KEY` | **DEFAULT_INSEGURO** |
| `LOGFLARE_PUBLIC_ACCESS_TOKEN` | **DEFAULT_INSEGURO** |
| `LOGFLARE_PRIVATE_ACCESS_TOKEN` | **DEFAULT_INSEGURO** |
| `POOLER_TENANT_ID` | **DEFAULT_INSEGURO** |
| `SMTP_PASS` | **DEFAULT_INSEGURO** |
| `S3_PROTOCOL_ACCESS_KEY_ID` | AUSENTE |
| `S3_PROTOCOL_ACCESS_KEY_SECRET` | AUSENTE |
| `GLOBAL_S3_BUCKET` | AUSENTE |
| `OPENAI_API_KEY` | AUSENTE (presente e vazio) |

Mais **33 chaves não-secretas** idênticas ao exemplo (portas, flags, caminhos de
e-mail). Essas são normais e não entram na rotação.

### O que cada default significa

- **`POSTGRES_PASSWORD`** — acesso direto ao banco pelo pooler.
- **`DASHBOARD_USERNAME` / `PASSWORD`** — o Studio está atrás de basic-auth com
  as credenciais publicadas. Studio fala com `pg-meta`, e `pg-meta` executa SQL.
- **`SECRET_KEY_BASE`** — o Realtime assina sessão com ele.
- **`VAULT_ENC_KEY`** — o que estiver no Supabase Vault é decifrável.
- **`PG_META_CRYPTO_KEY`** — as conexões guardadas pelo pg-meta.
- **`SMTP_PASS`** — envio de e-mail em nome do domínio.

---

## 3. Exposição real — medida, e menor do que eu escrevi antes

| porta | publicada pelo Docker | alcançável da internet |
|---|---|---|
| 8000 (Kong) | `0.0.0.0` | **não** direto |
| 5432 / 6543 (pooler) | `0.0.0.0` | **não** |
| 4000 (analytics) | `0.0.0.0` | **não** |
| 9000 (edge) | `0.0.0.0` | **não** |
| **443** (Caddy) | — | **sim** |

`ufw` permite só 22, 80 e 443. A corrente `DOCKER-USER` está **vazia** — o que
normalmente fura o ufw —, mas o teste externo confirma que 5432, 4000 e 8000
**não respondem**. Há filtragem antes do host (firewall de nuvem).

**Caddy** → `database.agenciavolc.com.br` → `localhost:8000` (Kong). O Kong é a
única porta de entrada, e por ela passam `/rest/v1/`, `/auth/v1/`,
`/storage/v1/`, `/realtime/v1/`, `/functions/v1/`, `/analytics/v1/` e **`/pg/`**.

⚠️ **`/pg/` é o pg-meta.** Ele é protegido por `key-auth` + `acl allow: admin` —
o grupo do `SERVICE_ROLE_KEY`. Como essa chave é o valor publicado, **`/pg/`
está aberto a quem tiver a documentação do Supabase**, e por ele passa SQL
arbitrário.

Isto é pior que forjar JWT: não exige forjar nada.

⚠️ **A armadilha do `kong.yml` está INTACTA** — `origins: - \"*\"` continua
escapado. Um restart não derruba o gateway por esse motivo. O backup
`kong.yml.bak-20260805-182724` está preservado.

---

## 4. A pilha viva

| serviço | imagem | estado |
|---|---|---|
| gateway | `kong:2.8.1` | **Kong**, não Envoy |
| db | `supabase/postgres:15.8.1.085` | PG 15 |
| auth | `supabase/gotrue:v2.185.0` | HS256 direto |
| rest | `postgrest/postgrest:v14.3` | HS256 direto |
| realtime | `supabase/realtime:v2.72.0` | HS256 + `SECRET_KEY_BASE` |
| storage | `supabase/storage-api:v1.33.5` | HS256 direto |
| edge | `supabase/edge-runtime:v1.70.0` | `FUNCTIONS_VERIFY_JWT` |
| meta | `supabase/postgres-meta:v0.95.2` | `PG_META_CRYPTO_KEY` |
| pooler | `supabase/supavisor:2.7.4` | `POOLER_TENANT_ID` |
| analytics | `supabase/logflare:1.30.3` | tokens Logflare |
| studio | `supabase/studio:2026.01.27` | basic-auth do dashboard |

Sem `docker-compose.override.yml`. Um único `docker-compose.yml` (18.560 bytes,
mtime 18/02/2026). Todos "Up 2 weeks".

**Quem valida HS256 diretamente:** auth, rest, realtime, storage e edge. Todos
leem `JWT_SECRET` do ambiente — por isso a troca exige restart de todos, e não
só do Kong.

**Ferramenta oficial de geração:** o Supabase publica um gerador de chaves na
documentação de self-hosting. Não há script local. A geração precisa produzir
`JWT_SECRET` novo e derivar `ANON_KEY`/`SERVICE_ROLE_KEY` com os mesmos claims
(`role`, `iss`, `iat`, `exp`).

---

## 5. Inventário de consumidores

| consumidor | ambiente | chave | onde é configurada | dono | como atualizar | reinício? | teste depois | estado |
|---|---|---|---|---|---|---|---|---|
| pilha Supabase | produção | todas | `/root/supabase/docker/.env` | infra | editar arquivo | `docker compose up -d` | healthcheck dos 13 | **confirmado** |
| Caddy | produção | — | `/etc/caddy/Caddyfile` | infra | não muda | não | `curl` 443 | **confirmado** |
| frontend (bundle) | Vercel prod | `anon` | `VITE_SUPABASE_ANON_KEY` | web | painel Vercel | **redeploy** | login real | **confirmado** |
| funções `api/` | Vercel prod | `service_role` | `SUPABASE_SERVICE_ROLE_KEY` | web | painel Vercel | **redeploy** | `GET /api/me` | **confirmado** |
| — | — | — | projeto `volc-os-campaign` · `prj_tn56w79c…` · 5 variáveis, 194 dias | — | — | — | — | — |
| FastAPI | local/worker | `service_role` | `backend/.env` (44 vars) | backend | editar | reiniciar uvicorn | `/api/trafego/inventario` | **confirmado** |
| `server/index.js` | local | `service_role` | `.env.server` (5 vars) | backend | editar | `./start-dev.sh` | `/health` | **confirmado** |
| Edge Functions | produção | injetada | ambiente do Supabase | infra | automático | segue o restart | `volc-ingest` | **confirmado** |
| — | — | — | `hello`, `main`, **`volc-ingest`** | — | — | — | — | — |
| **n8n — credencial `Supabase account`** | produção | `service_role` | credencial no n8n | automação | painel n8n | não | 1 execução de cada workflow | **confirmado** · **169 nós** |
| **n8n — credencial `VOLC Oficial`** | produção | `service_role` | credencial no n8n | automação | painel n8n | não | idem | **confirmado** · **15 nós** |
| **n8n — `gads-campaign-search`** | produção | `apikey` **escrita à mão** | dentro de 2 nós HTTP | automação | **editar o workflow** | não | execução manual | ⚠️ **o que quebra calado** |
| `.env` local (dev) | máquina | ambas | `.env`, `.env.local` | dev | editar | reiniciar | `npm run dev` | **confirmado** |
| `volc_ads` | local/worker | `service_role` | `pautador_ponte.py` lê do ambiente | backend | herda do `.env` | reiniciar | teste do engine | **confirmado** |
| scripts | máquina | `service_role` | herdam do `.env` | dev | nenhuma | não | rodar um | **confirmado** |
| — | — | — | `caderno-arbitragem.py`, `inventariar_supabase.py`, `verificar_segredos.py`, `meta-capi-selftest.mjs` | — | — | — | — | — |
| **FunnelForge** | ? | — | — | ? | — | — | — | ⚠️ **INDETERMINADO** |
| cron / timers | servidor | — | nenhum cron de aplicação | infra | — | — | — | **confirmado** |

### n8n — **NÃO é bloqueador**

30 workflows, 23 ativos, extraídos da instância de produção pela API em
**19/08/2026** e versionados em [`inventario-n8n/`](../inventario-n8n/) com
1.047 segredos censurados.

**23 workflows tocam o Supabase**, por dois caminhos:

- **22 via credencial** — só **duas** credenciais (`Supabase account`, 169 nós;
  `VOLC Oficial`, 15 nós). Trocar duas cobre 184 nós;
- **1 com chave escrita à mão** — `gads-campaign-search`, 2 nós HTTP com
  `apikey` no cabeçalho. **Este não segue a credencial** e quebra na próxima
  execução agendada sem ninguém ver.

⚠️ **O inventário tem 7 dias.** Workflow criado ou editado depois de 19/08 não
está nele. **Refazer a extração é o primeiro passo do runbook**, e até lá o
número 23 é uma medição de 19/08, não de hoje.

### FunnelForge — **INDETERMINADO**

O diretório existe em `~/Desktop/Rewrite-job-good-quality/funnel-forge` e
aparece no `sys.path` do Python desta máquina. **Nenhuma referência a Supabase
foi encontrada** nos fontes — mas "não encontrei" não é "não usa": ele pode ler
de ambiente herdado, ou ter `.env` próprio não varrido.

**Classificado como indeterminado**, e não como "não usa".

---

## 6. Estratégia — a menor mudança segura

Trocar **o `.env` inteiro** nos 13 campos `DEFAULT_INSEGURO`, e nada além disso.

**Entra:** `JWT_SECRET` novo aleatório · `ANON_KEY` e `SERVICE_ROLE_KEY`
derivadas dele · `POSTGRES_PASSWORD` · `DASHBOARD_*` · `SECRET_KEY_BASE` ·
`VAULT_ENC_KEY` · `PG_META_CRYPTO_KEY` · `LOGFLARE_*` · `POOLER_TENANT_ID` ·
`SMTP_PASS`.

**Fica fora, e vira fase de hardening:** Kong → Envoy · `sb_publishable` /
`sb_secret` · ES256/JWKS · upgrade do Postgres · v9_03 / v9_04.

Misturar modernização com resposta a incidente troca um problema conhecido por
vários desconhecidos, na única janela em que não se pode errar.

⚠️ **`VAULT_ENC_KEY` e `PG_META_CRYPTO_KEY` cifram dado em repouso.** Trocá-los
sem migrar o que já foi cifrado torna esse dado ilegível. **Antes de trocar os
dois, conferir se há algo no Vault e nas conexões do pg-meta** — se houver, eles
saem desta janela e entram numa própria, com migração.

---

## 7. Runbook — **comandos prontos, nada executado**

**Janela estimada: 2h30**, dos quais ~40 min de indisponibilidade real.
Fora de horário comercial.

**Responsáveis:** infra (servidor) · web (Vercel) · automação (n8n) ·
backend (locais). A janela exige os quatro disponíveis **ao mesmo tempo** — a
troca no servidor invalida tudo instantaneamente.

### Fase 0 · antes (30 min, sem indisponibilidade)

```bash
# 0.1 · REFAZER o inventário do n8n — o versionado tem 7 dias
python3 scripts/baixar-inventario-n8n.py            # confirmar o caminho do script
git -C . status --porcelain -- inventario-n8n/       # diff = workflow novo desde 19/08

# 0.2 · backup do banco, e VERIFICADO — não só criado
ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  "docker exec supabase-db pg_dump -U postgres -Fc postgres > /root/backups/pre-rotacao-$(date +%Y%m%d-%H%M).dump"
ssh … "ls -la /root/backups/ | tail -3"
ssh … "docker exec -i supabase-db pg_restore --list /root/backups/pre-rotacao-*.dump | wc -l"   # > 0 = legível

# 0.3 · backup da configuração
ssh … "cd /root/supabase/docker && cp .env .env.pre-rotacao-$(date +%Y%m%d-%H%M) && \
       cp volumes/api/kong.yml volumes/api/kong.yml.pre-rotacao-$(date +%Y%m%d-%H%M) && \
       chmod 600 .env.pre-rotacao-*"

# 0.4 · a evidência já está preservada (ver §1) — conferir que continua 600
ssh … "find /root/incidente-jwt-20260826 -type f ! -perm 600 | wc -l"    # tem de ser 0

# 0.5 · CONFERIR se Vault e pg-meta guardam algo cifrado (decide se as duas
#       chaves de cifra entram nesta janela ou saem para outra)
ssh … "docker exec -i supabase-db psql -U postgres -X -A -t -c \
  \"SELECT 'vault=' || (SELECT count(*) FROM vault.secrets) \" " 2>/dev/null || echo "vault ausente"
```

### Fase 1 · gerar as credenciais **sem exibi-las** (10 min)

```bash
# Gera direto para o .env, sem passar por stdout, sem entrar no histórico.
ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 'bash -s' <<'FIM'
set +x; umask 077
cd /root/supabase/docker
NOVO_JWT=$(openssl rand -base64 48 | tr -d '\n=+/' | cut -c1-64)
NOVA_PG=$(openssl rand -base64 32 | tr -d '\n=+/' | cut -c1-40)
# … demais segredos …
# As chaves anon/service são JWT assinados: derivar com a ferramenta oficial
# do Supabase, alimentada por $NOVO_JWT, e gravar direto no arquivo.
# NADA é ecoado.
FIM
```

⚠️ **`echo` de qualquer um desses valores anula a rotação** — ele vai para o
histórico do shell, para o log do SSH e para este transcript.

### Fase 2 · Supabase (20 min · **indisponibilidade começa**)

```bash
ssh … "cd /root/supabase/docker && docker compose up -d"
ssh … "docker ps --format '{{.Names}}\t{{.Status}}' | grep -v healthy"   # vazio = todos saudáveis
```

⚠️ **Conferir o `kong.yml` ANTES**: `origins: - \"*\"` tem de estar escapado.
Hoje está. Se alguém o tiver editado na janela, o Kong não sobe.

**Ordem:** db → auth/rest/storage/realtime → kong → studio/meta/analytics.
O `docker compose up -d` respeita `depends_on`; conferir um a um mesmo assim.

### Fase 3 · consumidores (40 min, em paralelo)

```bash
# 3.1 · Vercel — SOMENTE volc-os-campaign
npx vercel env rm  VITE_SUPABASE_ANON_KEY    production --scope tarcisios-projects-2895d85f
npx vercel env add VITE_SUPABASE_ANON_KEY    production --scope tarcisios-projects-2895d85f
npx vercel env rm  SUPABASE_SERVICE_ROLE_KEY production --scope tarcisios-projects-2895d85f
npx vercel env add SUPABASE_SERVICE_ROLE_KEY production --scope tarcisios-projects-2895d85f
./scripts/guarda-vercel.sh && npx vercel --prod --scope tarcisios-projects-2895d85f

# 3.2 · n8n — DUAS credenciais, no painel
#   · "Supabase account"  → 169 nós
#   · "VOLC Oficial"      → 15 nós
# 3.3 · n8n — o workflow com chave à mão, EDITADO NÓ A NÓ
#   · gads-campaign-search — 2 nós HTTP, cabeçalho `apikey`

# 3.4 · locais
#   .env · .env.local · .env.server · backend/.env  (4 arquivos, 4 chaves)
```

### Fase 4 · smoke tests (30 min)

```bash
# 4.1 · a chave ANTIGA morreu — este é o teste que prova a rotação
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "apikey: <ANON ANTIGA>" \
  https://database.agenciavolc.com.br/rest/v1/projects?select=id    # ESPERADO: 401

# 4.2 · a nova vive
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "apikey: <ANON NOVA>" \
  https://database.agenciavolc.com.br/rest/v1/projects?select=id    # ESPERADO: 401 (sem sessão) — o
                                                                    # que prova o Kong, não o RLS

# 4.3 · login real, no navegador, com conta de verdade
# 4.4 · inventário   → GET /api/trafego/inventario   200 com as 84 campanhas
# 4.5 · Auth         → /auth/v1/health
# 4.6 · Storage      → listar um bucket
# 4.7 · Realtime     → abrir o socket na tela
# 4.8 · Edge         → invocar `volc-ingest`
# 4.9 · backend      → GET /api/me e GET /health
# 4.10 · n8n         → executar 1 workflow de cada credencial + gads-campaign-search
```

⚠️ **A `service_role` ANTIGA não entra em teste ativo.** Provar que ela morreu
exigiria usá-la, e usá-la é exatamente o que não se faz com credencial
comprometida. A prova pela `anon` antiga basta: as duas são assinadas pelo mesmo
segredo, e o 401 dela prova que o segredo mudou.

---

## 8. Rollback de incidente

**"Voltar ao segredo comprometido" não é rollback.** A chave publicada não volta
a ser confiável em nenhuma hipótese — se voltasse, a janela toda teria sido
teatro.

Pode reverter: **imagem** · **compose** · **template** · **código** ·
**configuração de consumidor**.

Não pode reverter: **as credenciais**.

Se a pilha nova não subir, a manutenção **continua** até o reparo. A alternativa
— voltar as chaves velhas para "restabelecer o serviço" — restabelece o serviço
para todo mundo, inclusive para quem tem a documentação do Supabase aberta.

---

## 9. Controle compensatório — **correção**

⚠️ **A versão anterior deste plano listava "allowlist de origem" entre os
controles aceitáveis. Está errado e foi retirado.**

CORS e restrição por `Origin` são instruções que o **navegador** obedece.
`curl`, um script, ou qualquer cliente que não seja navegador simplesmente não
as aplica. Elas não são controle de segurança: são compatibilidade entre
páginas.

Controles reais, se a rotação não puder ser hoje:

| controle | o que faz | custo |
|---|---|---|
| **allowlist de IP no firewall de nuvem** | fecha 443 a tudo que não for Vercel + n8n + escritório | derruba quem estiver fora da lista |
| **Cloudflare Access na frente do Caddy** | exige identidade antes de chegar ao Kong | precisa isentar as chamadas máquina-a-máquina |
| **manutenção controlada** | 443 fechado, sistema fora do ar | honesto e total |

Os três **têm relógio** (ADR-15): aceite nominal, prazo, e data de reavaliação.
Nenhum é substituto da rotação.

**Nenhum foi aplicado.**

---

## 10. Checklist de aceite

- [ ] inventário do n8n refeito **hoje**, e o diff contra 19/08 revisado
- [ ] backup do banco criado **e** verificado com `pg_restore --list`
- [ ] `.env` e `kong.yml` copiados com carimbo
- [ ] Vault / pg-meta conferidos — decidido se as chaves de cifra entram
- [ ] os quatro responsáveis disponíveis na mesma janela
- [ ] 13 segredos trocados, **nenhum ecoado**
- [ ] 13 contêineres saudáveis
- [ ] Vercel: 2 variáveis + redeploy, **só** `volc-os-campaign`
- [ ] n8n: 2 credenciais + `gads-campaign-search` editado à mão
- [ ] 4 arquivos locais
- [ ] `anon` antiga responde **401**
- [ ] login real funciona
- [ ] inventário devolve as 84 campanhas
- [ ] 1 execução de cada credencial do n8n, verde
- [ ] incidente fechado com data, executor e o que foi verificado
- [ ] memória do projeto corrigida — ela ainda diz que as chaves foram
      regeneradas

---

## 11. Autorização

Nada acima roda sem esta frase, do dono, literal:

> **AUTORIZO A ROTAÇÃO DE CREDENCIAIS DO SUPABASE EM PRODUÇÃO, CONFORME O
> RUNBOOK IR-0, NA JANELA DE [data e hora].**

Ela autoriza **apenas** as fases 0 a 4 deste documento. Não autoriza migration,
deploy de funcionalidade, upgrade de pilha, nem qualquer item da fase de
hardening.
