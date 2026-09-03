# Postiz — o que foi entregue, o que foi verificado, e o que continua sem prova

**Data:** 02/09/2026 · Fontes primárias consultadas nesta data.
O runbook operacional completo vive em [`deploy/postiz/README.md`](../../../deploy/postiz/README.md).
Este documento é o **registro de fatos e limites** — o que sabemos, de onde, e
até onde vale.

---

## 1. O contrato externo, com a fonte de cada linha

| fato | fonte |
|---|---|
| Autenticação: header `Authorization` com a API key **crua**, sem `Bearer` | docs.postiz.com/public-api/introduction |
| `POST /public/v1/posts` exige `type`, `date`, `shortLink`, `tags`; e `posts[]` quando `type ≠ draft` | docs.postiz.com/public-api/posts/create |
| `type` ∈ `draft` \| `schedule` \| `now` | idem |
| `date` é ISO 8601 **UTC** e é ignorado quando `type = now` | idem |
| Resposta de criação: `[{postId, integration}]` | idem |
| `GET /public/v1/posts` exige `startDate` e `endDate`; devolve `posts[]` com `id`, `content`, `state`, `publishDate`, `releaseURL`, `integration` | docs.postiz.com/public-api/posts/list |
| `state` ∈ `QUEUE` \| `PUBLISHED` \| `ERROR` \| `DRAFT` | idem |
| `DELETE /public/v1/posts/{id}` apaga o post **e todos do mesmo grupo** | docs.postiz.com/public-api/posts/delete |
| `PUT /public/v1/posts/{id}/status` com `{"status":"draft"\|"schedule"}` | docs.postiz.com/public-api/posts/change-status |
| `GET /public/v1/integrations` devolve `id`, `name`, `identifier`, `picture`, `disabled`, `profile`, `customer` | docs.postiz.com/public-api/integrations/list |
| Licença **AGPL-3.0**, © 2025 Nevo David | github.com/gitroomhq/postiz-app/blob/main/LICENSE |
| Release pinável: `v2.23.0`, publicada 2026-08-04 | api.github.com/repos/gitroomhq/postiz-app/releases/latest |
| O Postiz usa **PostgreSQL próprio** via Prisma (`DATABASE_URL`) | docs.postiz.com/self-host/configuration/reference |

Um revisor factual independente (Gemini 3.7 Flash) confirmou 17 dos 18 itens
acima contra a documentação oficial.

## 2. As quatro ausências — registradas, nunca contornadas

### 2.1 Não existe `GET /posts/{id}`
A consulta é por **janela de data** e devolve uma lista; a reconciliação filtra
pela referência que já temos. Uma implementação que fingisse `/posts/{id}`
produziria 404 em produção e apontaria o diagnóstico para o lugar errado.
Há teste que falha se alguém "otimizar" para essa rota.

### 2.2 Não existe endpoint de health público
`prontidao()` usa `GET /integrations` como sonda e **diz isso na resposta**
(`fonte: "proxy:/integrations"`, e o texto "não há endpoint de health oficial
nesta versão do Postiz"). Chamar isso de health check afirmaria uma capacidade
que a API não publica.

> ⚠️ **Divergência registrada.** O revisor factual (Gemini) **refutou** este item,
> alegando um `/health` público que checa DB, Redis e Temporal. A refutação **não
> se sustentou** contra a fonte primária: `docs.postiz.com/self-host/architecture.md`
> não menciona health/readiness; `llms.txt` não lista página de health; e o
> healthcheck do compose **oficial** aponta para `http://localhost:5000/` — a
> **raiz**, não `/health`. Se o endpoint fosse a sonda recomendada, o compose
> oficial o usaria. Mantida a leitura conservadora; reconferir quando houver
> instância, que é uma pergunta de um comando.

### 2.3 Não existe idempotência documentada
Nenhum campo de request-id no schema público de `POST /posts`. **Consequência de
desenho:** a idempotência não pode ser delegada — ela vive no ledger da v14_01, e
a porta é chamada no máximo uma vez por job.

### 2.4 Não há webhook de confirmação documentado
A reconciliação desta v1 é por **consulta (pull)**, não por notificação.

## 3. Divergência dentro da própria documentação oficial

O limite de requisições aparece de duas formas em páginas oficiais:

- `public-api/posts/create`: "There is a limit of **30 requests per hour**."
- `public-api/introduction`: "**90 requests per hour** (100 for the cloud) …
  applies to only the create post endpoint", ajustável por `API_LIMIT`
  (default 90 na referência de configuração).

**Não resolvida por adivinhação.** O adaptador trata `429` como falha **não
permanente** e não assume nenhum dos dois números.

## 4. Capacidades que existem e NÃO foram exercitadas

Declaradas em código (`portas.CAPACIDADES_NAO_EXERCITADAS`), com um teste que
exige a declaração — para que "não implementamos" nunca vire "não existe".

| capacidade | endpoint | por que não foi feita |
|---|---|---|
| promover rascunho → agendamento | `PUT /posts/{id}/status` | promover mudaria o `modo`, que faz parte do snapshot imutável. Um job novo com `modo='schedule'` é o caminho desta v1 |
| upload de mídia | `POST /upload`, `POST /upload-from-url` | esta v1 envia texto; imagem exige decidir **onde** o arquivo do Asset Vault é servido, e isso é infraestrutura |
| analytics | `GET /analytics/*` | fora do escopo de publicação |

## 5. O pacote operacional

`deploy/postiz/` — compose adaptado do oficial, com o que o oficial não tem:

- **imagens pinadas** (o compose oficial usa `:latest` no `postiz-app`, e isso é
  um problema para rollback e para conformidade de licença);
- healthcheck em todo serviço, e `depends_on` com `condition: service_healthy`;
- **fronteira de rede**: rede `interna` com `internal: true`; só `postiz` (e
  `temporal-ui`, sob perfil) na rede de borda; nada em `0.0.0.0`;
- **menor privilégio**: `cap_drop: [ALL]`, `no-new-privileges:true`, nenhum
  `privileged`;
- variáveis por **nome**, nunca por valor; `DISABLE_SSRF_PROTECTION` e
  `NOT_SECURED` marcadas como **proibidas**, com o motivo;
- backup/restore, upgrade/rollback, e o procedimento do primeiro usuário que
  **fecha a entrada externa antes** de abrir o cadastro — e agenda o fechamento
  antes de abrir, para a janela ter prazo mesmo se quem abriu sumir.

### O validador, e por que ele tem autoteste

`scripts/validar_postiz_pacote.py` é **offline por construção** (importar o módulo
e chamar `socket.socket()` levanta `RedeProibida`). Ele confere: nomes de arquivo
de compose não declarados, imagem com tag flutuante ou `:latest`, porta publicada
fora de loopback, healthcheck ausente/desligado/trivial, variável interpolada não
documentada, postura de segurança (privileged, cap_drop, no-new-privileges,
internal, condição de dependência) e material de credencial versionado.

Duas versões dele foram **derrotadas por YAML válido** antes de chegar aqui: um
parser próprio que não entendia sintaxe de fluxo, e a leitura de um único arquivo
quando o Compose **mescla** overrides. Por isso o `--autoteste`: ele aplica **18
mutações conhecidas** numa cópia temporária e exige que cada uma reprove pelo
rótulo certo. Um gate sem prova de mordida é exatamente o defeito que ele existe
para consertar.

## 6. Licença — a fronteira, e o que ela proíbe

AGPL-3.0 é copyleft forte com cláusula de rede. A leitura desta casa, registrada
em `deploy/postiz/LICENCA-E-FRONTEIRA.md`:

- **integração por processo e API**, com o Postiz rodando como serviço separável;
- **nenhuma linha do Postiz entra no core do VOLC-OS**;
- o VOLC não distribui o Postiz nem o oferece como serviço próprio.

⚠️ Isto **não substitui aconselhamento jurídico**.

## 7. Limites de segurança que continuam abertos, e estão declarados

| limite | o que foi feito | o que continua aberto |
|---|---|---|
| **DNS rebinding** | o destino é revalidado **a cada chamada**, e não só na construção — a janela cai de "a vida do objeto" para "milissegundos" | entre a validação e o `connect()` ainda há um intervalo. Só um transporte com **pinagem de IP** o fecharia |
| **redirect** | `follow_redirects=False` explícito; `3xx` é recusa explícita; um cliente injetado que siga redirect **não constrói** | — |
| **token em trânsito** | `http` exige `POSTIZ_PERMITIR_REDE_INTERNA` declarado | numa rede interna sem TLS o token trafega em claro. É decisão escrita, não padrão |
| **tag flutuante** | `postiz-app` pinado; `redis:7.2`, `postgres:16`, `postgres:17-alpine` herdadas do compose oficial → **3 avisos** do validador | trocar por digest antes de produção (`docker buildx imagetools inspect`) |

## 8. O que precisa de instância para ser provado

1. O adapter criando draft/agendamento em **sandbox** (aceite de P12-T09).
2. Backup e restore **provados** (aceite de P12-T08).
3. Healthcheck respondendo (aceite de P12-T08).
4. Se existe ou não um `/health` não documentado (§2.2).
5. Qual dos dois limites de requisição vale na prática (§3).
6. "Falha de um destino não contamina outro" com dois destinos reais.

Todos os seis estão no bloco de autorização de `AUTORIZACAO-EXTERNA.md`.
