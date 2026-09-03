# Postiz — runbook do control plane de publicação orgânica

Este diretório é o **pacote operacional isolado** do Postiz: o serviço externo
que o VOLC-OS usa para despachar publicação orgânica. Ele sobe sozinho, é
operado sozinho e pode ser derrubado sozinho — o backend do VOLC só sabe falar
HTTP com ele.

> ⚠️ **Nada aqui foi executado.** Nenhum container subiu, nenhuma imagem foi
> baixada, nenhum healthcheck foi observado passar, nenhum backup foi restaurado.
> O que está escrito abaixo é procedimento derivado de fontes oficiais datadas —
> não é relato de execução. A lista completa do que exige uma instância real
> está em [Capacidades não provadas](#capacidades-não-provadas), no fim.

---

## 1. O que este pacote é, e o que ele deliberadamente não é

| É | Não é |
|---|---|
| Um serviço de terceiro rodando **ao lado** do VOLC | Uma dependência do processo do backend |
| Integração por **API HTTP oficial** | Biblioteca importada, fork, ou código copiado |
| Dono do **próprio** Postgres, Redis e Temporal | Consumidor do Supabase do VOLC |
| Executor de decisões já tomadas | Autoridade de agenda ou de idempotência |

A última linha é a que mais confunde. **Quem decide o que publicar, quando, e
quantas vezes é a v14_01** (`supabase/migrations/v14_01_publicacao_organica.sql`
e o ledger que ela define). O Postiz recebe uma ordem já decidida e devolve um
recibo. A idempotência **não pode** ser delegada a ele: a API pública dele não
documenta nenhum campo de request-id (verificado em 02/09/2026), então dois
POST idênticos produzem dois posts.

---

## 2. Pré-requisitos

- **Docker Engine ≥ 24** e o plugin **Compose v2** (`docker compose`, com
  espaço — não `docker-compose`). O arquivo usa `depends_on` com
  `condition: service_healthy`, `profiles` e a chave `name` no topo; tudo isso é
  Compose v2.
- **~4 GB de RAM livres.** O Elasticsearch sozinho reserva 512 MB de heap (e o
  dobro disso de memória real, entre heap e off-heap); Temporal, Postgres ×2,
  Redis e o Postiz somam o resto. Numa máquina apertada o primeiro sintoma é o
  ES ser morto pelo OOM killer e o Temporal nunca ficar `healthy`.
- **Um reverse proxy com TLS**, se a instância for acessível por pessoas fora da
  máquina. O compose publica em `127.0.0.1` de propósito (§7).
- **Um `deploy/postiz/.env` preenchido**, modo `600`. Ver `.env.example`.
- **Um Python com PyYAML** para rodar o validador do pacote (§10). O `python3` do
  sistema desta máquina não tem; `backend/.venv/bin/python` tem. O gate falha
  fechado sem ele — de propósito.

Não é pré-requisito: nada do VOLC. Este pacote sobe numa máquina que nunca ouviu
falar do backend.

---

## 3. Subir

```bash
cd deploy/postiz
cp .env.example .env && chmod 600 .env
${EDITOR:-vi} .env          # preencha; entradas vazias com default ficam vazias

# 1) confira a interpolação SEM subir nada. Este comando resolve todo ${...} e
#    falha nomeando a variável obrigatória que estiver faltando.
docker compose config >/dev/null && echo "compose OK"

# 2) confira o pacote (offline, não sobe nada, não chama rede)
#    ⚠️ PyYAML é OBRIGATÓRIO e o gate FALHA FECHADO sem ele (saída 2). O
#    `python3` do sistema desta máquina não tem; o venv do backend tem.
../../backend/.venv/bin/python ../../scripts/validar_postiz_pacote.py

# 3) baixe as imagens antes, para separar "demora de download" de "erro de boot"
docker compose pull

# 4) suba
docker compose up -d
```

O `up` respeita a ordem por saúde: Elasticsearch e o Postgres do Temporal
primeiro, depois o Temporal, depois o Postgres e o Redis do Postiz, e só então o
Postiz. **A primeira subida é lenta** — o `auto-setup` do Temporal cria schema, e
o Postiz roda as migrations do Prisma. Os `start_period` do compose já contam
com isso (120 s para o Postiz, 90 s para o Temporal).

### O primeiro usuário

`DISABLE_REGISTRATION` nasce em `true`, ou seja, **não há como criar conta**.
Para criar a primeira:

⚠️ **Enquanto o cadastro está aberto, qualquer pessoa que alcance a instância
cria uma conta com poder de publicar nas páginas reais dos clientes.** No
desenho B (§5) a instância está atrás de um reverse proxy TLS, ou seja,
alcançável por gente fora da máquina. Por isso a ordem abaixo começa **fechando
o acesso externo**, e não abrindo o cadastro.

```bash
cd deploy/postiz

# 1) FECHE a porta de entrada externa ANTES de abrir o cadastro.
#    Pare o proxy que estiver na frente (nginx/caddy/traefik — o comando é o da
#    sua máquina) e prove que só sobrou loopback:
sudo systemctl stop nginx
docker compose port postiz 5000        # tem de imprimir 127.0.0.1:4007
ss -ltnp | grep -E ':4007'             # o bind tem de ser 127.0.0.1, nunca 0.0.0.0
#   (macOS: lsof -nP -iTCP:4007 -sTCP:LISTEN)

# 2) AGENDE O FECHAMENTO ANTES DE ABRIR. A janela passa a ter prazo mesmo que
#    quem abriu seja interrompido, saia para almoçar ou perca a conexão.
( sleep 600; POSTIZ_DISABLE_REGISTRATION=true docker compose up -d postiz ) &
FECHAMENTO=$!

# 3) só agora abra o cadastro
POSTIZ_DISABLE_REGISTRATION=false docker compose up -d postiz

# 4) cadastre A ÚNICA conta de operação. Sem proxy, o acesso é por túnel SSH:
#    ssh -N -L 4007:127.0.0.1:4007 <usuario>@<host>   e abra http://127.0.0.1:4007

# 5) feche JÁ — não espere o prazo — e cancele o fechamento agendado
docker compose up -d postiz
kill "$FECHAMENTO" 2>/dev/null

# 6) PROVE que fechou, e só então religue o proxy
docker compose exec postiz sh -lc 'echo "$DISABLE_REGISTRATION"'   # tem de imprimir: true
sudo systemctl start nginx
```

⚠️ O passo 6 não é formalidade. `docker compose up -d` só recria o container se
a configuração mudou; se por algum motivo ele não recriar, o cadastro fica aberto
sem ninguém perceber. O `exec` acima é a verificação, não a intenção — e é ele
que autoriza religar o proxy.

⚠️ O fechamento agendado do passo 2 vive **no shell em que você o disparou**:
não feche o terminal antes do passo 6 imprimir `true`. Se precisar de garantia
independente do shell, use `at now + 10 minutes` (ou um `systemd-run --on-active=10m`)
com o mesmo comando de fechamento — o ponto é que o prazo exista antes da janela,
não depois.

---

## 4. Healthcheck — e o que cada camada realmente prova

São **três** perguntas diferentes, e confundi-las é o erro clássico:

```bash
# (a) os processos estão de pé?
docker compose ps
docker inspect --format '{{.Name}} {{.State.Health.Status}}' \
  $(docker compose ps -q)

# (b) o Postiz responde HTTP na porta dele?
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4007/

# (c) o VOLC consegue OPERAR o control plane?
curl -sS http://127.0.0.1:8010/api/publicacao-organica/prontidao
```

| Pergunta | O que prova | O que **não** prova |
|---|---|---|
| (a) healthcheck do compose | o processo subiu e a porta responde | que as migrations passaram; que o Temporal conectou |
| (b) HTTP na 4007 | a borda HTTP está viva | que o token do VOLC é válido; que há canal conectado |
| (c) `/prontidao` do VOLC | token válido + a instância responde `GET /integrations` | nada sobre publicar de fato |

⚠️ **Não existe endpoint de health público no Postiz.** Verificado em
02/09/2026 e registrado em `backend/app/publicacao_organica/portas.py`. O
healthcheck (a) é o mesmo proxy HTTP que o compose oficial usa, e a prontidão (c)
é `GET /public/v1/integrations` — declarada no próprio resultado como
`fonte='proxy:/integrations'`, porque chamar isso de "health check" seria
afirmar uma capacidade que a API não documenta.

Quando algo não sobe, olhe **na ordem da dependência**, não na do sintoma:

```bash
docker compose logs --tail 100 temporal-elasticsearch
docker compose logs --tail 100 temporal
docker compose logs --tail 100 postiz-postgres
docker compose logs --tail 200 postiz
```

---

## 5. Como o VOLC se conecta

O backend do VOLC **não lê o `.env` deste diretório**. Ele lê três nomes do
ambiente dele (`backend/.env`), declarados em `backend/app/config.py`:

| Nome | O que é |
|---|---|
| `POSTIZ_BASE_URL` | raiz da instância. A API vive em `/public/v1` e **quem acrescenta esse sufixo é o adaptador** — não ponha o caminho aqui. |
| `POSTIZ_API_TOKEN` | a chave emitida dentro da interface do Postiz. Vai **crua** no header `Authorization`, sem `Bearer`. |
| `POSTIZ_PERMITIR_REDE_INTERNA` | o "sim" explícito para `http://` ou para host privado/loopback. |

**Sem os três, o backend responde 503 dizendo que não há control plane.** Não
existe adaptador silencioso que responda "despachado" sobre nada.

### O terceiro nome não é burocracia

`validar_base_url()` (em `adaptadores/postiz.py`) recusa, **antes da primeira
chamada**, `http://` sem essa autorização e qualquer host que resolva para rede
privada, loopback, link-local ou reservado. O motivo está escrito lá: sem essa
trava, uma `POSTIZ_BASE_URL` trocada por engano apontaria para
`169.254.169.254` e **este processo entregaria a credencial da nuvem** junto com
o token. Numa instalação self-hosted, `http://postiz:5000` é o caso normal — por
isso a autorização existe; e é por isso que ela é explícita e nunca o padrão.

### Os dois desenhos possíveis

**A — VOLC e Postiz na mesma máquina** (o mais simples):
```
POSTIZ_BASE_URL=http://127.0.0.1:4007
POSTIZ_PERMITIR_REDE_INTERNA=true
```
O tráfego não sai da máquina. `http` é aceitável **porque** a autorização
explícita foi dada e o caminho é loopback.

**B — VOLC noutra máquina**:
```
POSTIZ_BASE_URL=https://postiz.interno.exemplo
POSTIZ_PERMITIR_REDE_INTERNA=false
```
Aqui `https` não é opcional: o `POSTIZ_API_TOKEN` viaja no header em texto
claro dentro do TLS. Sem TLS, qualquer salto no caminho lê a credencial que
publica nas páginas reais dos clientes.

⚠️ **O que nunca acontece nos dois desenhos:** o Postiz receber a
`service_role` do Supabase. Isso é decisão de ADR (28/08/2026) e virou controle
executável — `test_publicacao_organica_segredos` falha se o módulo do adaptador
passar a referenciar essa chave. O único segredo que o adaptador conhece é o
`POSTIZ_API_TOKEN`.

---

## 6. Backup e restore

Há **dois** artefatos, e eles só valem juntos: o banco (posts, canais, contas) e
o volume de uploads (os arquivos). Um dump do banco sem os uploads produz posts
que apontam para arquivos inexistentes.

### Backup

⚠️ **A imagem utilitária do `tar` também precisa de pin.** Os comandos abaixo
usam um container efêmero só para ler/escrever o volume, e `alpine:3.20` é **tag
flutuante** — fora do regime de pin do compose (§8). Ela toca os seus dados de
produção: resolva para digest uma vez (`docker buildx imagetools inspect
alpine:3.20`) e fixe abaixo. Enquanto isso não for feito, fica registrado como
dívida, não como decisão.

```bash
cd deploy/postiz
CARIMBO="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p ./backups

# imagem utilitária, num lugar só. Troque por alpine@sha256:<digest> quando
# tiver rede para resolver — o resto do procedimento não muda.
UTIL="alpine:3.20"

# (1) banco do Postiz — formato custom (-Fc), que permite restore seletivo.
#     As credenciais vêm de DENTRO do container: nenhum segredo passa pelo
#     histórico do shell do host.
docker compose exec -T postiz-postgres \
  sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "./backups/postiz-banco-${CARIMBO}.dump"

# (2) volume de uploads — tar de um container efêmero que monta o volume ro.
#     `postiz_postiz-uploads` = <projeto>_<volume>; o projeto é `postiz`
#     (chave `name:` no topo do compose). Confirme com `docker volume ls`.
docker run --rm \
  -v postiz_postiz-uploads:/dados:ro \
  -v "$PWD/backups":/saida \
  "$UTIL" \
  tar czf "/saida/postiz-uploads-${CARIMBO}.tgz" -C /dados .

# (3) prove que o dump não está vazio ANTES de confiar nele
ls -lh "./backups/postiz-banco-${CARIMBO}.dump" "./backups/postiz-uploads-${CARIMBO}.tgz"
docker run --rm -v "$PWD/backups":/b "$UTIL" tar tzf "/b/postiz-uploads-${CARIMBO}.tgz" | head
```

⚠️ **O `.env` também é parte do backup**, e é a parte que não pode ir para o
mesmo lugar dos outros dois: ele contém `POSTIZ_JWT_SECRET` e as senhas. Guarde
no cofre de segredos da operação, nunca no diretório `backups/`. E
⚠️ **`backups/` não pode ser versionado** — se este diretório passar a existir,
acrescente-o ao `.gitignore` antes do primeiro dump.

⚠️ O Postgres do **Temporal** não entra no backup de propósito. Ele guarda estado
de execução de workflow, não dados de negócio; num desastre, o `auto-setup`
recria o schema vazio. Restaurar um estado de workflow antigo contra um banco do
Postiz novo produziria execuções órfãs — pior do que não ter.

### Restore

A ordem importa, e ela existe para o Postiz **não estar rodando** enquanto o
banco muda debaixo dele:

```bash
cd deploy/postiz
UTIL="alpine:3.20"      # o mesmo do backup; pin por digest antes de produção

# (1) derrube SÓ a aplicação; o banco continua de pé para receber o restore
docker compose stop postiz

# (2) banco. --clean --if-exists derruba os objetos antigos antes de recriar.
docker compose exec -T postiz-postgres \
  sh -lc 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
  < ./backups/postiz-banco-<CARIMBO>.dump

# (3) uploads — o `rm -rf` é o que impede um híbrido de dois instantes
docker run --rm \
  -v postiz_postiz-uploads:/dados \
  -v "$PWD/backups":/entrada \
  "$UTIL" \
  sh -c 'rm -rf /dados/* /dados/.[!.]* 2>/dev/null; tar xzf /entrada/postiz-uploads-<CARIMBO>.tgz -C /dados'

# (4) suba e confira as três camadas do §4
docker compose up -d postiz
docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q postiz)"
```

⚠️ **Use o dump e o tar do MESMO carimbo.** Misturar instantes é a forma mais
fácil de produzir um estado que parece íntegro e não é: os posts existem, os
arquivos não.

⚠️ `pg_restore` imprime avisos de "does not exist, skipping" durante o `--clean`
num banco novo. **Isso é normal.** O que não é normal é erro de constraint ou de
tipo — nesse caso pare, não suba o Postiz, e verifique se o dump veio de uma
versão de schema diferente da imagem que está no compose.

---

## 7. Fronteira de rede

```
                        internet
                            │
                    ┌───────┴────────┐
                    │  reverse proxy │  (TLS, fora deste compose)
                    └───────┬────────┘
                            │ 127.0.0.1:4007
        ┌───────────────────┴──────────────────────────────┐
        │  rede `borda`  (com saída para a internet)        │
        │  postiz          temporal-ui (só `--profile       │
        │                  depuracao`; publica              │
        │                  127.0.0.1:8080)                  │
        └───────────────────┬──────────────────────────────┘
                            │
        ┌───────────────────┴──────────────────────────────┐
        │  rede `interna`  —  internal: true, SEM gateway   │
        │  postiz-postgres · postiz-redis · temporal        │
        │  temporal-postgresql · temporal-elasticsearch     │
        └──────────────────────────────────────────────────┘
```

Três decisões, e o motivo de cada uma:

1. **`internal: true` na rede interna.** O Docker não cria rota de saída. Se o
   Elasticsearch ou o Redis for comprometido, não há para onde exfiltrar — não
   existe gateway. Isso é mais forte do que "não publicar porta", que só impede
   a entrada.
2. **Nenhuma porta publicada para banco, Redis ou Temporal.** O compose oficial
   publica o Temporal em `127.0.0.1:7233`; aqui não. Porta em loopback ainda é
   porta aberta para qualquer processo local — inclusive um container de outro
   projeto na mesma máquina. O `postiz` alcança o Temporal pelo DNS do compose.
3. **Na operação normal a única porta publicada é a do Postiz, em `127.0.0.1`
   por padrão.** O compose oficial usa `4007:5000`, que em Docker significa
   `0.0.0.0`: a instância inteira exposta em toda interface, sem TLS, com o
   login administrativo junto. Para expor de verdade, TLS no reverse proxy — não
   trocar o bind.
   ⚠️ **"Operação normal" é literal:** com `--profile depuracao`, a
   `temporal-ui` sobe e publica `127.0.0.1:8080` — e, por causa da pegadinha
   abaixo, ela também entra na rede `borda`. São duas portas e dois serviços com
   rota de saída enquanto esse profile estiver de pé; o preço de deixá-lo
   sempre ligado é esse. A lista de quem pode estar na `borda` é conferida pelo
   validador (`SERVICOS_NA_BORDA`).

⚠️ **Pegadinha de compose:** porta publicada **não funciona** quando o container
está apenas numa rede `internal: true` — o Docker não monta a regra de NAT. É por
isso que `temporal-ui` (perfil `depuracao`) aparece também na rede `borda`, mesmo
sem usar a internet; e é justamente por ganhar essa rota que ela fica atrás de um
profile em vez de subir sempre.

### Menor privilégio

Todos os serviços: `no-new-privileges` e `cap_drop: [ALL]`, com o mínimo
readicionado onde o entrypoint precisa trocar de usuário ou ajustar dono de
arquivo. `read_only: true` nos dois Postgres, no Redis e na UI do Temporal, com
`tmpfs` nos caminhos efêmeros.

⚠️ **Três serviços ficaram sem `read_only`, e o motivo está escrito no compose:**
o `postiz` (roda vários processos supervisionados que escrevem em `/tmp` e em
cache do Next, e nenhum desses caminhos foi medido nesta missão); o `temporal`
(a imagem `auto-setup` **gera** o arquivo de configuração em
`/etc/temporal/config` no boot — rootfs somente leitura mata o container no
primeiro segundo, e um `tmpfs` ali mascararia os templates da imagem); e o
`temporal-elasticsearch` (escreve log em diretório que não é volume). Ligar
`read_only` sem medir produz falha de boot obscura — pior do que não ter a
proteção. Fica registrado como trabalho pendente, não como decisão final.

---

## 8. Upgrade e rollback

### Por que a tag está pinada

⚠️ **O compose oficial usa `ghcr.io/gitroomhq/postiz-app:latest`, e isso é um
problema, não um detalhe.** Com `:latest`:

- um `docker compose pull` de rotina **troca a versão do control plane** sem que
  ninguém tenha decidido;
- a **migration do Prisma roda no boot** e altera o schema do banco;
- o **rollback deixa de existir**, porque não há para onde voltar — `:latest` de
  ontem não é um endereço.

Aqui a tag é `v2.23.0` — o release oficial mais recente conhecido em 02/09/2026,
publicado em 2026-08-04 ("Streamed media uploads, duplicate-post protection & MCP
fixes"). As duas primeiras mudanças desse release tocam exatamente o que o nosso
ledger observa.

⚠️ **Não verificado offline:** que essa tag exista **no registry**. O release do
GitHub é uma tag de git; o GHCR pode publicar com outro esquema. Antes da
primeira subida, sem baixar a imagem inteira:

```bash
docker buildx imagetools inspect ghcr.io/gitroomhq/postiz-app:v2.23.0
```

e troque a linha por `image: ghcr.io/gitroomhq/postiz-app@sha256:<digest>` —
digest é o único pin que não se move. Faça o mesmo com `postgres:17-alpine`,
`redis:7.2` e `postgres:16`, que são **tags flutuantes herdadas do oficial** (o
validador emite AVISO para cada uma).

### Upgrade

```bash
cd deploy/postiz

# 1) LEIA o changelog do release de destino. Migration de Prisma não se desfaz.

# 2) BACKUP COMPLETO (§6). Não negociável — é ele o rollback de verdade.

# 3) anote a referência ATUAL, para poder voltar
docker compose config | grep -E '^\s+image:'
docker inspect --format '{{index .RepoDigests 0}}' \
  "$(docker compose ps -q postiz)"          # guarde este digest

# 4) edite a tag no docker-compose.yml e COMITE a mudança
#    (a versão em produção tem de estar no histórico do repositório)

# 5) baixe antes de trocar, para separar download de boot
docker compose pull postiz

# 6) troque só a aplicação; a infraestrutura continua de pé
docker compose up -d postiz

# 7) acompanhe a migration EM TEMPO REAL — não confie no exit code
docker compose logs -f postiz

# 8) prove as três camadas do §4, incluindo a (c), do lado do VOLC
```

### Rollback

**Caso A — falhou antes de a migration tocar o banco** (imagem não baixou,
container não subiu, erro de configuração). O schema está intacto:

```bash
# volte a tag/digest anterior no compose e recrie
docker compose up -d postiz
```

**Caso B — a migration do Prisma rodou e falhou no meio.** ⚠️ **Voltar a imagem
NÃO desfaz o schema.** O Prisma aplica migrations para frente e não gera
migration de descida; um schema meio-migrado com uma imagem antiga é uma
combinação que ninguém testou. Também **não tente consertar o schema à mão** — o
Prisma guarda estado em `_prisma_migrations`, e um remendo manual deixa esse
registro mentindo sobre o banco.

O caminho é restaurar, nesta ordem:

```bash
cd deploy/postiz
docker compose stop postiz                    # 1) pare a aplicação
# 2) restaure banco E uploads do MESMO carimbo, pelo §6
# 3) volte a tag/digest anterior no docker-compose.yml
docker compose up -d postiz                   # 4) suba a versão antiga
docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q postiz)"
```

⚠️ **Antes de subir de novo, feche a ponte com o VOLC.** Enquanto o control
plane está num estado indefinido, um despacho em andamento pode virar
`DesfechoIncerto` — a exceção que a porta levanta quando não se sabe se o pedido
chegou. Ela existe justamente para isso: tratar como falha convida a reenviar e
duplicar o post; tratar como sucesso inventa um recibo. O desfecho correto é
`indeterminado`, resolvido pela reconciliação (`POST
/api/publicacao-organica/jobs/{id}/reconciliar`) **depois** que o Postiz voltar.

---

## 9. Nota de licença — AGPL-3.0

O Postiz é **AGPL-3.0**, copyright (C) 2025 Nevo David
(<https://github.com/gitroomhq/postiz-app/blob/main/LICENSE>, consultado em
02/09/2026).

A AGPL estende o copyleft ao **uso em rede**: quem oferece a um terceiro, pela
rede, um serviço construído a partir de uma **obra derivada** do software deve
oferecer a esse terceiro o código-fonte correspondente. É a cláusula que fecha a
brecha do SaaS na GPL comum.

**Por isso a integração é por processo e por API, e não por biblioteca.** O
Postiz roda como serviço separado, no seu próprio container, com o seu próprio
banco. O VOLC fala com ele por HTTP, sobre a API pública documentada. Nenhuma
linha do Postiz é compilada, importada ou vendorizada no backend do VOLC — e a
fronteira está codificada em
`backend/app/publicacao_organica/portas.py`, que diz literalmente: de um lado,
tipos do VOLC; do outro, HTTP.

**O que isso proíbe, na prática:**

- copiar trecho de código do Postiz para dentro do VOLC-OS;
- fazer fork do Postiz, alterar, e servir esse fork sem publicar a fonte;
- criar biblioteca-ponte que faça link com código do Postiz no mesmo processo;
- redistribuir a imagem modificada sem carregar a AGPL e as fontes junto.

**O que isso não proíbe:**

- rodar o Postiz como está, self-hosted, para uso próprio ou de clientes;
- chamar a API pública dele a partir de software proprietário;
- automatizar o deploy dele — que é exatamente o que este diretório faz.

A análise completa está em [LICENCA-E-FRONTEIRA.md](./LICENCA-E-FRONTEIRA.md),
inclusive a ressalva de que **isto não é aconselhamento jurídico**.

---

## 10. Validador do pacote

```bash
# da raiz do repositório. ⚠️ PyYAML é obrigatório: o `python3` do sistema desta
# máquina não tem, e o gate FALHA FECHADO (saída 2) em vez de rodar mais fraco.
backend/.venv/bin/python scripts/validar_postiz_pacote.py

# prova de mordida: quebra cópias temporárias do pacote e exige reprovação
backend/.venv/bin/python scripts/validar_postiz_pacote.py --autoteste
```

Ele é **offline por construção**: não sobe container, não chama rede, não lê
`.env` real. O que ele confere:

| Rótulo | Conferência |
|---|---|
| `[compose]` | nenhum arquivo de compose fora do declarado — `docker compose up -d` **mescla** os `*.override.*` e prefere `compose.yaml` ao `docker-compose.yml`, então um arquivo a mais troca o que roda |
| `[imagem]` | nada em `:latest` nem sem tag (tag flutuante vira **aviso**) |
| `[healthcheck]` | existe, não está `disable: true` e não é teste trivial (`true`, `exit 0`) |
| `[rede]` | toda porta publicada em loopback por padrão, nas sintaxes curta e longa |
| `[dependencia]` | todo `depends_on` com `condition: service_healthy` — lista só ordena a partida |
| `[postura]` | `cap_drop: [ALL]`, `no-new-privileges:true`, `internal: true` na rede interna, nenhum `privileged`/`network_mode: host`, e só `postiz` e `temporal-ui` na `borda` |
| `[variavel]` | toda variável interpolada documentada no `.env.example` — `${NOME}`, `${NOME:-x}` **e** `$NOME` |
| `[proibida]` | `DISABLE_SSRF_PROTECTION` e `NOT_SECURED` só dentro de comentário |
| `[segredo]` | nenhum valor de credencial versionado (mesma família de padrões do `test_publicacao_organica_segredos`) |

Sai com código 1 e uma mensagem que diz **onde** e **por quê**; 2 para erro de
ambiente (PyYAML ausente) ou de uso.

⚠️ **Por que existe `--autoteste`.** A versão anterior deste gate tinha um parser
próprio de YAML e lia um arquivo só, e as duas coisas foram derrubadas por prova:
um item de porta com 8 espaços, uma sequência de fluxo (`ports: ["0.0.0.0:…"]`) e
um `docker-compose.override.yml` de 10 linhas passavam com **APROVADO** —
inclusive com `privileged: true` e as duas variáveis PROIBIDAS ativas. O
`--autoteste` aplica cada uma dessas mutações a uma cópia temporária e exige que o
gate reprove **com o rótulo certo**. Conferência sem prova de mordida não conta
como conferência.

---

## Capacidades não provadas

Tudo abaixo exige uma instância real e **não foi verificado nesta missão**.
Nenhum item aqui é opinião sobre probabilidade — é declaração de ausência de
evidência.

| # | O que não foi provado | Como provar |
|---|---|---|
| 1 | Que a tag `ghcr.io/gitroomhq/postiz-app:v2.23.0` existe no registry | `docker buildx imagetools inspect ghcr.io/gitroomhq/postiz-app:v2.23.0` |
| 2 | Que as tags `postgres:17-alpine`, `redis:7.2`, `postgres:16`, `elasticsearch:7.17.27`, `temporalio/auto-setup:1.28.1`, `temporalio/ui:2.34.0` resolvem — e a `alpine:3.20` do backup (§6), que é tag flutuante fora do compose | `docker buildx imagetools inspect <imagem>` para cada uma |
| 3 | Que a imagem do Postiz tem `curl` **ou** `wget` (o healthcheck depende de um dos dois) | `docker compose exec postiz sh -lc 'command -v curl wget'` |
| 4 | Que os conjuntos de `cap_add` bastam (são hipótese fundamentada, não medição) | subir e ler o log; se der "operation not permitted", **adicionar** a capability nomeada — nunca voltar ao conjunto padrão |
| 5 | Que `read_only: true` nos dois Postgres, no Redis e na UI do Temporal não quebra o boot | `docker compose up -d` e ler o log de cada um |
| 6 | Que os `start_period` bastam para a primeira subida (migrations do Prisma + `auto-setup`) | cronometrar a primeira subida numa máquina representativa |
| 7 | Que a topologia com Elasticsearch é necessária (talvez Postgres-only baste para a visibility do Temporal) | trocar em ambiente descartável e observar; **não** mexer sem instância |
| 8 | Que o `pg_dump`/`pg_restore` deste runbook restaura um Postiz operante | fazer o ciclo completo num ambiente descartável, com dados de teste |
| 9 | Que o upgrade e o rollback do §8 funcionam | executar um upgrade real de uma versão anterior para a `v2.23.0` |
| 10 | Qualquer comportamento da API sob carga, incluindo qual dos dois limites oficiais (30/h ou 90/h) vale de fato | medir contra a instância; a divergência está **registrada**, não resolvida |

E as ausências da própria API pública, já registradas em `portas.py` e que
**nenhum ajuste de infraestrutura resolve**: não há `GET /posts/{id}`, não há
chave de idempotência, não há endpoint de health público e não há webhook de
confirmação documentado (consulta de 02/09/2026).

---

## Fontes oficiais consultadas (02/09/2026)

- Compose oficial: <https://github.com/gitroomhq/postiz-docker-compose>
- Licença: <https://github.com/gitroomhq/postiz-app/blob/main/LICENSE>
- Release `v2.23.0`: <https://api.github.com/repos/gitroomhq/postiz-app/releases/latest>
- API pública: <https://docs.postiz.com/public-api/introduction>
- Referência de configuração: <https://docs.postiz.com/self-host/configuration/reference>
