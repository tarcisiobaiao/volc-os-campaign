# Contratos — plano de controle de publicação orgânica v1

**Data:** 02/09/2026
**Base:** `origin/volc-os-v2` = `382c5d4c67fc521d5e6739f8e76d1c36a96fdb53`
**Branch:** `sprint/organic-publication-control-plane-v1`

---

## 1. A decisão que precisava de prova: estender ou construir

O ADR de 28/08/2026 especificou o `PublicationJob` campo a campo. Antes de
escrever um, esta missão precisava provar que o existente não podia ser
estendido coerentemente. Duas candidatas foram examinadas contra o arquivo.

### 1.1 `pautador_funnel_runs` + `backend/app/routers/publicacao.py` — REFUTADA

O fluxo WordPress/Redator é um plano de controle de publicação **completo** —
com destino, publicação por página, reconciliação, releitura do provedor e prova
visual. Ele não foi estendido, e as razões são estruturais, não estéticas:

| dimensão | WordPress/Redator (medido) | o que orgânico exige |
|---|---|---|
| cardinalidade do destino | `project_wordpress.project_id UNIQUE` (`src/sql/pautador/02_publicacao_por_projeto.sql:71`) — **um** site por projeto | N canais por projeto |
| unidade de trabalho | `pautador_funnel_runs.opportunity_id NOT NULL` — todo run desce de uma pauta | uma peça aprovada + um destino |
| fonte da verdade | `state.json` **em disco**, e a ausência do arquivo é recusa de publicação (`publicacao.py:1387`, `:1577`) | banco + storage; sobrevive a outra máquina |
| recibo | `paginas_publicadas` jsonb **mutável**, sobrescrito em três caminhos | linha append-only, com histórico |
| idempotência | `SELECT` antes de `INSERT`, **sem constraint** (`publicacao.py:563-575`) | chave única no banco + digest derivado |
| agendamento | inexistente — zero `publish_at`, zero IANA | modo + horário local + timezone + instante UTC |
| ownership | inexistente — `grep owner_id` no pacote inteiro sai vazio | fail-closed por gatilho |
| concorrência | `os.kill(pid, 0)` | lease + fencing |

Substituir destino, unidade de trabalho, ato de publicar e fonte da verdade é
escrever um sistema novo usando o nome antigo.

**O que foi reaproveitado do Redator, e é o que ele tem de melhor — a doutrina:**

1. *"rodou ≠ publicou"* (`app/redator/worker.py:583-600`): sair com código 0 e
   não publicar é um desfecho real. Virou o estado `publicacao_solicitada`, que
   existe justamente para não colapsar "a API respondeu" em "está no ar".
2. *o provedor é dono do `status`* (`publicacao.py:944-968`): virou as arestas
   "para trás" da máquina de estados — `agendado → rascunho_externo` é
   registrável porque acontece de verdade quando alguém mexe no painel externo.
3. *404 é relatado, nunca apaga a linha* (`publicacao.py:1112`): virou o ramo da
   reconciliação sem referência externa, que mantém `indeterminado` e diz que
   não encontrou.
4. *destino inapto aparece com o motivo* (`publicacao.py:385-432`, forma
   `{id, nome, apto, motivo}`): virou `publicacao_organica_listar_destinos`.

### 1.2 `criativo_entrega` (v11_01, seção 9) — CONSIDERADA E NÃO ESTENDIDA

Esta é a candidata séria, e a decisão precisa ficar registrada porque ela é
desconfortável: existe hoje uma tabela de entrega, **vazia e sem consumidor de
produção**, com `idempotency_key`, `autorizacao_id NOT NULL REFERENCES
criativo_aprovacao` e um índice parcial `(idempotency_key, operacao) WHERE
estado='sucesso'`. É quase o que a missão pede.

Não foi estendida por cinco razões:

1. **Unidade de trabalho.** `criativo_entrega.pacote_id` é `NOT NULL` contra
   `criativo_pacote`, que é `NOT NULL` contra `criativo_projeto`. Obrigar todo
   post orgânico a descender de um pacote de mídia paga inverte o modelo.
2. **Tempo.** Entrega de pacote é imediata. Orgânico tem modo, horário local
   declarado, timezone IANA e instante UTC derivado — cinco colunas e três
   invariantes que mídia paga não quer carregar.
3. **Reconciliação.** `criativo_entrega.recibo` é jsonb mutável, sem append-only
   e sem histórico. O mesmo post muda de `QUEUE` para `PUBLISHED` horas depois;
   isso é tabela filha, não `UPDATE`.
4. **Concorrência.** Não há lease, fencing nem contador de tentativa. Um
   despachante que morre no meio deixa a linha `em_voo` para sempre.
5. **Fronteira de trabalho.** `criativo_*` é o domínio do Estúdio Criativo e
   está sob missão ativa em outro terminal. Alterar a tabela dele aqui seria
   invadir.

**⚠️ ISTO DEIXA UMA DÍVIDA REAL, E ELA ESTÁ DECLARADA:** existem agora duas
tabelas de entrega desenhadas para "peça aprovada → destino". `criativo_entrega`
continua vazia e sem chamador. A decisão sobre o destino dela — adotá-la como
ledger de mídia paga com escopo explícito, ou aposentá-la — é do dono do Estúdio
Criativo, e está em `CURATION-HANDOFF.json` como pendência nomeada. Ignorá-la
seria pior do que registrá-la.

### 1.3 O que NÃO foi reinventado: o ato de aprovar

`criativo_aprovacao` já é a decisão humana com ator, instante, finalidade,
ressalvas e revogação, com gatilho de banco que impede aprovar peça não pronta.
A publicação orgânica **consome** essa linha por FK e por gatilho. Um segundo
conceito de aprovação produziria duas verdades sobre a mesma peça.

E o vocabulário orgânico já existia: `criativo_finalidade` tem `instagram_organic`
e `youtube_shorts` na classe `organica` (`v11_02:851-852`). O gatilho exige que
a finalidade aprovada seja dessa classe — aprovar para `google_display` não
autoriza publicar no feed.

---

## 2. O domínio canônico

### 2.1 `publicacao_organica_destino` — o canal

Aponta para um `cofre_ativo` que já inventaria a página/perfil (kinds
`facebook_page`, `instagram_profile`, `youtube_channel`, `tiktok_account`,
v13_01 §3). Não é um segundo cadastro de destinos.

| campo | por quê |
|---|---|
| `ativo_id` → `cofre_ativo` | o patrimônio é do Cofre; aqui mora só o vínculo de canal |
| `plataforma` | allowlist de 8 |
| `identidade_logica` | nome lógico (`PAGINA_PILOTO`). **Nunca segredo, nunca id cru** |
| `referencia_externa` | id opaco da integração no control plane; `NULL` = não ligado |
| `adapter_apto` / `motivo_inapto` | inapto **aparece**, com o motivo |
| `owner_sub` | o dono, `= Identidade.sub` |
| `timezone_padrao` | IANA, default `America/Sao_Paulo` |
| `estado` | ativo / suspenso / aposentado |

Invariantes de banco: apto exige referência externa; inapto exige motivo.

### 2.2 `publicacao_organica_job` — a intenção canônica

Cobre os campos que o ADR pediu, e nomeia os que ele não nomeou:

| exigido pelo ADR / missão | coluna |
|---|---|
| `publication_job_id` | `id` |
| `owner_id` | `owner_sub` (+ `owner_email`) |
| `project_id` | `projeto_id` (nullable — nem toda peça tem projeto) |
| referência imutável ao ativo aprovado | `peca_tipo` + `peca_id` + `peca_content_hash` |
| revisão/versão do ativo | `peca_versao` |
| destino e plataforma | `destino_id` → destino |
| identidade lógica da página, sem segredo | no snapshot, vinda do destino |
| modo | `modo` ∈ draft / schedule / now |
| horário local declarado | `horario_local` (texto, sem fuso) |
| timezone IANA | `timezone` |
| instante UTC persistido | `instante_utc` (**derivado no banco**) |
| status | `estado` (11 valores) |
| idempotency key | `chave_idempotencia UNIQUE` |
| request digest | `entrada_hash` (sha256 derivado no banco) |
| adapter/provider | `adapter` |
| tentativas | `tentativas` |
| último erro sanitizado | `ultimo_erro` (+ CHECK de prosa limpa) |
| receipt externo sanitizado | tabela `publicacao_organica_recibo` |
| timestamps | `criado_em`, `atualizado_em`, `cancelado_em` |
| vínculo com aprovação humana | `autorizacao_id` → `criativo_aprovacao` |
| snapshot imutável da solicitação | `solicitacao` jsonb + gatilho |
| *(acrescentado)* consentimento de `now` | `consentimento_agora` + ator + instante |
| *(acrescentado)* lease | `lease_owner`, `lease_ate`, `fencing` |

### 2.3 As três tabelas de trilha

- `publicacao_organica_operacao` — idempotência e recibo interno, **append-only**.
  Tabela própria porque `cofre_operacao.chave_idempotencia` é UNIQUE global:
  compartilhar faria uma chave de publicação colidir com uma do Cofre.
- `publicacao_organica_recibo` — a prova externa. Cada observação é uma **linha
  nova**. `url_publicada` é guardada verbatim (remontar URL a partir de slug já
  produziu atribuição de receita apontando para o post errado, em silêncio —
  `steps.py:2832-2843`).
- `publicacao_organica_transicao` — o histórico de estado, append-only.

---

## 3. Os estados, e a diferença que cada um carrega

| estado | significa | tom na tela |
|---|---|---|
| `rascunho` | criado no VOLC; nada saiu daqui | neutro |
| `pronto` | validado e liberado para despacho | neutro |
| `em_voo` | reivindicado e despachado; resposta desconhecida | aguardando |
| `rascunho_externo` | o control plane confirmou um DRAFT | aguardando |
| `agendado` | o control plane confirmou um agendamento | aguardando |
| `publicacao_solicitada` | aceitou publicar AGORA; **não confirmou** | atenção |
| `publicado` | o control plane declara PUBLISHED, sem prova fechada | atenção |
| `reconciliado` | observação com referência, URL **e** instante | **sucesso** |
| `falha` | falha determinada | falha |
| `indeterminado` | ambíguo ou timeout — nem sucesso nem falha | atenção |
| `cancelado` | encerrado, com a trilha preservada | neutro |

**`reconciliado` é o único `sucesso`, e há um teste que falha se deixar de ser**
(`test_publicacao_organica_dominio.py::test_todo_estado_tem_leitura_e_nenhum_incerto_e_verde`).

As arestas são declaradas numa lista dentro de
`publicacao_organica_job_guarda_update`. As "para trás" não são descuido: depois
do despacho, **quem é dono do estado externo é o control plane**. Recusar
`agendado → rascunho_externo` faria nossa linha discordar do mundo em silêncio.

O que a lista **nunca** contém: `rascunho_externo → pronto` e
`rascunho_externo → em_voo`. Rearmar um job que já existe no destino produziria
um segundo post.

---

## 4. Idempotência, concorrência e o digest

**Chave derivada de conteúdo, nunca sorteada.** `sha256(peça, versão, destino,
modo, horário, timezone, corpo)`. O operador que reenvia sem mudar nada produz a
mesma chave e recebe o recibo que já existe.

**Digest derivado NO BANCO.** `cofre_entrada_hash(rota, payload, extra)` é
`IMMUTABLE`, genérica e reaproveitada da v13_01 — o chamador não a envia e por
isso não pode falsificá-la. Mesma chave + mesma entrada → replay; mesma chave +
outra entrada → `unique_violation`, **e a chave não entra na mensagem** (a
gramática dela aceita uma senha inteira).

**Um despacho bem-sucedido por job, fisicamente:**
```sql
CREATE UNIQUE INDEX publicacao_organica_operacao_sucesso_ux
  ON publicacao_organica_operacao (job_id)
  WHERE desfecho = 'sucesso' AND job_id IS NOT NULL
    AND rota = 'publicacao_organica.concluir_despacho';
```
⚠️ O predicado cita a rota porque a primeira versão — `(job_id, rota) WHERE
desfecho='sucesso'` — impedia a **segunda reconciliação** do mesmo job. Pego
pela prova do ciclo em 02/09/2026.

**Lease com fencing.** `reivindicar` faz `SELECT ... FOR UPDATE`, incrementa
`fencing` e conta a tentativa. `concluir_despacho` exige o fencing que recebeu;
um despachante que dormiu e perdeu o lease é recusado com `40001` em vez de
sobrescrever quem assumiu.

`FOR UPDATE` **sem** `SKIP LOCKED`, de propósito: o segundo consumidor espera,
vê o estado já mudado, e recebe "já reivindicado por outro". Com `SKIP LOCKED`
ele veria "nada para fazer", que é outra coisa.

---

## 5. A porta

```
PortaDePublicacao (Protocol)
  criar_rascunho(SolicitacaoExterna) -> ReciboExterno
  agendar(SolicitacaoExterna)        -> ReciboExterno
  publicar_agora(SolicitacaoExterna) -> ReciboExterno
  consultar(referencia_externa)      -> ReciboExterno | None
  cancelar(referencia_externa)       -> bool
  listar_canais()                    -> list[Canal]
  prontidao()                        -> Prontidao
```

Duas exceções carregam a distinção que a missão exige:

- `FalhaDoControlPlane` — recusa **conhecida** (400/401/403/422/429).
- `DesfechoIncerto` — timeout, conexão cortada, 5xx, corpo ilegível, ou 200 sem
  `postId`. **O pedido pode ter chegado.** Vira `indeterminado`, nunca falha.

### Capacidades AUSENTES na API oficial — registradas, não contornadas

| ausência | consequência no desenho |
|---|---|
| não há `GET /posts/{id}` | `consultar` usa `GET /posts?startDate&endDate` e filtra pela referência que já temos |
| não há endpoint de health | `prontidao()` usa `GET /integrations` e **diz na resposta** que é `proxy:/integrations` |
| não há idempotência documentada | ela vive no ledger da v14_01; a porta é chamada no máximo uma vez por job |
| não há webhook de confirmação documentado | a reconciliação é por consulta (pull) |

### Capacidades que existem e NÃO foram exercitadas

Declaradas em `portas.CAPACIDADES_NAO_EXERCITADAS`, com um teste que exige a
declaração:

- `PUT /posts/{id}/status` (promover rascunho → agendamento). Não implementada
  porque promover mudaria o `modo`, que faz parte do snapshot imutável. Um job
  novo com `modo='schedule'` é o caminho desta v1.
- `POST /upload` e `POST /upload-from-url`. Esta v1 envia texto; imagem exige
  decidir onde o arquivo do Asset Vault é servido, e isso é infraestrutura.
- `GET /analytics/*` — fora do escopo de publicação.

---

## 6. Timezone

O horário local declarado nunca vira instante em Python. `publicacao_organica_criar_job`
faz `horario_local::timestamp AT TIME ZONE timezone`, que é independente do
`TimeZone` do servidor por construção. Quatro recusas, todas provadas:

1. zona IANA inexistente (conferida com `AT TIME ZONE` real, não só por regex);
2. horário no passado;
3. horário local que **não existe** na zona (salto de horário de verão) —
   detectado convertendo de volta e comparando;
4. `schedule` sem horário declarado.

A prova de independência: o mesmo pedido é criado com `SET LOCAL TimeZone` em
`UTC` e em `Pacific/Kiritimati`, e os dois instantes têm de ser idênticos e
iguais a `12:30Z` para `09:30` em `America/Sao_Paulo`.

---

## 7. Fronteira de segredo

| camada | o que faz |
|---|---|
| `dominio.sanitizar_erro` | redige `Authorization`/`Bearer`/JWT/`op://`/prefixos de token, em forma de header **e de JSON**, com teto de 400 chars |
| `dominio.recusar_chave_sensivel` | recusa (não remove) chave de credencial em qualquer profundidade; a mensagem cita o **caminho**, nunca o valor |
| `infraestrutura._mensagem_segura` | `details` e `hint` do PostgREST **nunca são lidos**; `message` só sai se casar uma frase própria; varredura final descarta marcadores |
| CHECK `*_prosa_limpa` (v14_01 §9) | o banco recusa material de credencial nas colunas que a API publica |
| `test_..._segredos.py` | o adaptador não pode nem **referenciar** `service_role`, `SupabaseService`, `get_settings` ou `Settings` (verificado por AST) |

⚠️ A redação de `Authorization` foi corrigida em 02/09/2026: a primeira versão
casava o header cru e **não** casava `{"Authorization":"…"}` — a forma que
gateways devolvem no corpo de um 400. O token ia inteiro para `ultimo_erro`.

---

## 8. Egresso

`validar_base_url` recusa esquema fora de http/https e destino em rede
privada/loopback/link-local, salvo `POSTIZ_PERMITIR_REDE_INTERNA` declarado —
que é o caso normal do self-hosted, mas é um **sim explícito por configuração**,
nunca o padrão. Sem ele, uma `POSTIZ_BASE_URL` trocada por engano apontaria o
token para `169.254.169.254` e este processo entregaria a credencial da nuvem.
