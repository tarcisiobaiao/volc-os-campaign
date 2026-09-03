# Autorização externa — o checkpoint único desta missão

**Data:** 02/09/2026 · **Branch:** `sprint/organic-publication-control-plane-v1`

---

## Primeiro: o que NÃO aconteceu

Esta missão não executou nenhum ato externo. Concretamente, e cada linha é
verificável:

| ato proibido | aconteceu? | como se confere |
|---|---|---|
| deploy do Postiz | **não** | nenhum container subiu; `docker` está indisponível nesta máquina |
| importar/alterar configuração numa instância Postiz | **não** | não existe instância |
| conectar página ou perfil real | **não** | o único ativo social é uma fixture (`asset:facebook-page:piloto`) que só existe em Postgres descartáveis |
| criar draft real | **não** | todo tráfego HTTP passou por `httpx.MockTransport` |
| agendar conteúdo real | **não** | idem |
| publicar conteúdo real | **não** | idem |
| aplicar migration no Supabase oficial | **não** | a v14_01 só rodou em clusters `mktemp -d` que morreram no fim de cada execução |
| escrever no Supabase oficial | **não** | o `SupabaseService` real nunca foi construído com credencial; o E2E usa um shim sobre Postgres local |
| iniciar AdsPower ou perfil real | **não** | AdsPower não é tocado por esta missão |
| Meta/Facebook/Instagram write | **não** | nenhuma chamada à Graph API |
| alterar Google Ads | **não** | fora do escopo |
| ativar n8n | **não** | fora do escopo |
| deploy / merge / push | **não** | `git log origin/volc-os-v2..HEAD` = 4 commits **locais**; nada foi empurrado |

**Leituras externas feitas, todas read-only e sem credencial:** documentação
pública do Postiz (`docs.postiz.com`), o `LICENSE` e a API de releases do GitHub,
e o `docker-compose.yaml` do repositório público `gitroomhq/postiz-docker-compose`.
Nenhuma delas envia dado do VOLC nem exige autenticação.

---

## O bloco de autorização

Tudo o que resta é externo, e está aqui — em **um** pedido, na ordem de
dependência. Cada item diz o que faz, o que arrisca e o que fecha.

### Bloco A — infraestrutura (fecha P12-T08)

> **A1.** Subir a pilha de `deploy/postiz/` num host isolado, com
> `DISABLE_REGISTRATION=true` depois do primeiro usuário, atrás de TLS, sem porta
> em `0.0.0.0`.
> **Risco:** superfície nova na rede. Mitigado por rede `internal`, `cap_drop`,
> `no-new-privileges` e nada publicado além do necessário.
> **Fecha:** "instância isolada responde healthcheck".
>
> **A2.** Provar backup e restore com dado de teste (o runbook tem os comandos).
> **Risco:** nenhum — é dado de teste, no host novo.
> **Fecha:** "backup e restauração provados".
>
> **A3.** Trocar as três tags flutuantes herdadas (`redis:7.2`, `postgres:16`,
> `postgres:17-alpine`) por digest.
> **Risco:** nenhum. Remove os 3 avisos do validador.
>
> **A4.** Responder duas perguntas que só a instância responde: existe um
> `/health` não documentado? Qual limite de requisição vale — 30/h ou 90/h?
> **Risco:** nenhum. Dois `curl`.

### Bloco B — credencial (depende de A)

> **B1.** Gerar a API key do Postiz e guardá-la no 1Password, registrando no
> Cofre apenas a **referência** (`cofre_referenciar_credencial`, nome lógico tipo
> `POSTIZ_API_TOKEN`).
> ⚠️ **Não** criar uma settings em texto puro. O caminho de menor esforço já foi
> trilhado uma vez neste repositório e a chave de serviço acabou dentro de um
> JSON de workflow.
> **Risco:** uma credencial com poder de publicar. Mitigado por: o adaptador
> conhece **só** ela (provado por AST) e nunca alcança o Supabase.

### Bloco C — destino real (fecha P12-T02, e é pré-requisito do piloto)

> **C1.** Cadastrar a página real no Cofre. `scripts/onboarding_pagina_facebook.py`
> já emite os payloads e **se recusa a tocar a rede** — a aplicação é um ato
> humano deliberado.
> **Risco:** o inventário passa a nomear um ativo real. Nenhum segredo entra.
>
> **C2.** Conectar a página ao Postiz pelo OAuth **dele**, e registrar o
> `integration.id` como `referencia_externa` do destino.
> ⚠️ Este é o ato que dá ao Postiz poder de publicar na página. Ele é
> irreversível na prática (revogar exige mexer no Business Manager).
> **Risco:** o mais alto do conjunto.
> **Fatos a conferir antes** (levantados pelo revisor factual e **não** conferidos
> por esta missão): Page Access Token com `pages_manage_posts`, `pages_show_list`,
> `pages_read_engagement`; Business Verification e App Review desde 2024-2025;
> token de usuário é short-lived e exige a troca por long-lived → page token, ou
> os agendamentos falham em ~60 dias.

### Bloco D — a primeira peça (fecha o aceite de P12-T09)

> **D1.** Aplicar `v14_01` no Supabase oficial. **Pré-requisito medido:** ela
> exige v11_01, v11_02 e v13_01 aplicadas. v13_01 e v13_02 estão aplicadas; **a
> série v11 precisa ser conferida antes** — se não estiver, a guarda da seção 0
> aborta com mensagem nomeada, que é o comportamento desejado.
> **Risco:** 5 tabelas novas, todas com RLS forçada e zero policy. `v14_99`
> reverte, e o ciclo completo está provado.
>
> **D2.** Publicar **um rascunho** (`modo='draft'`) de uma peça já aprovada, e
> reconciliar. Draft não vai ao ar: é o menor ato externo que prova a porta
> inteira.
> **Risco:** baixo — um rascunho no painel do Postiz.
> **Fecha:** "adapter cria draft em sandbox".
>
> **D3.** Só depois de D2 fechar: um **agendamento** real, com o horário
> conferido no painel antes de chegar.
> **Risco:** conteúdo vai ao ar no horário. Reversível por `DELETE /posts/{id}`
> antes da hora.
>
> **D4.** `modo='now'` **não** faz parte deste pedido. Ele exige o consentimento
> explícito por job que o contrato já implementa, e um segundo pedido humano no
> momento.

### Bloco E — o que fica fora, e é decisão de outro dono

> **E1.** O destino de `criativo_entrega` (D1 do `CURATION-HANDOFF.json`):
> adotá-la como ledger de mídia paga com escopo escrito, ou aposentá-la. Hoje há
> duas tabelas de entrega e ninguém consegue dizer qual é a canônica.
>
> **E2.** Dois defeitos de uma linha no fluxo WordPress/Redator, achados pelo
> mapeamento desta missão e **não** consertados aqui para não misturar assuntos:
> `publicacao.py:1606` (tabela errada, ramo morto) e `publicacao.py:990`
> (`status='error'` contra um CHECK que só aceita `'failed'`).

---

## A ordem importa

```
A (infra) → B (credencial) → C (destino real) → D2 (rascunho) → D3 (agendamento)
```

Pular C e ir direto para D não funciona: **o primeiro elo que falta não é o
adapter, é o destino.** Um adaptador construído antes do onboarding real não tem
contra o que publicar.

---

## O que NÃO precisa de autorização

Continuar o trabalho local: estender o fake, escrever mais contraprovas, montar
o segundo destino hermético para provar isolamento entre canais, ou implementar
a promoção rascunho→agendamento (`PUT /posts/{id}/status`). Nada disso toca o
mundo.
