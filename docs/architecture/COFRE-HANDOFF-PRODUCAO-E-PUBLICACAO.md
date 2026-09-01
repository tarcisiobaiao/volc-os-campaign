# Contrato de handoff — do Cofre para produção criativa e publicação

**Data:** 01/09/2026
**Estado:** contrato aceito; os três consumidores ainda não existem
**Alvos:** P03-T11 (broker 1Password ↔ AdsPower), P12-T08 e P12-T09 (Postiz), P12-T11 (QA visual)

## Resultado em uma frase

O Cofre responde *quem recebe a peça, o que pode produzi-la, qual referência de
acesso será resolvida e qual componente vem depois* — e não executa nenhum deles.

## Por que este documento existe

O ADR de 28/08 desenhou o fluxo `1Password → broker → AdsPower → recibo` e o
fluxo `Pauta → job → aprovação → Postiz → QA visual`. Os dois dependem de um
inventário que responda "qual página?", "com qual acesso?", "produzido por
qual engine?". Esse inventário passou a existir em 01/09/2026 (v13_01 +
`/api/cofre`), e sem um contrato explícito o próximo a implementar o broker
faria a escolha errada por conta própria: pediria ao Cofre que resolvesse o
endereço do segredo, porque é o caminho mais curto.

Este documento existe para que essa escolha não seja tomada por conveniência.

## A rota

```
GET /api/cofre/ativos/{ativo_id}/handoff      (ADMIN, sessão do Supabase)
```

Ela **responde**. Não cria job, não abre navegador, não publica, não resolve
segredo. É leitura composta de dados que já existem.

### O que ela devolve

| Bloco | Conteúdo | O que NÃO contém |
|---|---|---|
| `destino` | ativo, nome, tipo, plataforma, estado, URL pública, projeto, vertical | nada sensível |
| `referencia_de_acesso[]` | provider, **nome lógico**, estado, estado e data da verificação | **o localizador** |
| `perfis_de_navegador[]` | as arestas `authenticates_through` declaradas | ID de sessão, cookie, API key |
| `engines_disponiveis[]` | identidade, modalidade, estado operacional, formatos, skins, destinos, limitações | caminho absoluto de disco |
| `proximo_componente` | o nome e a tarefa de cada consumidor, com o estado real | promessa de que existe |
| `pronto_para_handoff` / `bloqueios[]` | booleano + o motivo, em português | — |

### A assimetria deliberada

`referencia_de_acesso` traz **provider e nome lógico**, e nunca o `localizador`.

Quem resolve `op://VOLC/Pagina%20Piloto/credential` é o **broker, no host
isolado, com o papel `postgres`** — não esta API, não o navegador, não o agente.
Um handoff que já viesse com o endereço resolvido transformaria a rota na porta
do cofre: bastaria uma sessão ADMIN comprometida para enumerar todos os
endereços da operação de uma vez.

O nome lógico (`FB_PAGE_ADMIN`) é suficiente para o broker saber *o que* pedir, e
insuficiente para alguém pegar. Essa é exatamente a divisão da tabela de
autoridade do ADR.

## Os três consumidores, e a fronteira de cada um

### P03-T11 — broker 1Password ↔ AdsPower

```text
worker local
   │ GET /api/cofre/ativos/{id}/handoff        (nome lógico, perfil, bloqueios)
   ▼
broker no host isolado
   │ resolve o localizador NO BANCO, com papel postgres, operação auditada
   │ injeta em memória (op run), nunca em arquivo
   ▼
AdsPower Local API — loopback + Bearer ativo
   │
   ▼
screenshot + console + recibo SANITIZADO ──► POST /api/cofre/.../verificacoes
```

**O que o Cofre entrega:** o `handoff`, e depois recebe o recibo como
verificação (`alvo: "credencial"`, resultado `verified` / `failed` / `blocked`).

**O que o Cofre NÃO entrega:** o localizador, a API key do AdsPower, o perfil
aberto, a sessão.

**Pré-condições que o `handoff` já verifica:** existe referência registrada,
existe perfil relacionado, a referência já foi verificada com sucesso, o ativo
não está aposentado. Quando alguma falta, `pronto_para_handoff` é `false` e o
motivo vem em `bloqueios` — um 200 mudo faria o broker tentar e falhar sem saber
por quê.

**Guarda que o broker deve implementar e o Cofre não pode impor:** allowlist de
ação por perfil, timeout, e a recusa de `--no-masking` (que o smoke de P03-T09
já trata como flag proibida no preflight).

### P12-T08 / P12-T09 — Postiz e a porta VOLC de publicação

```text
peça aprovada ──► PublicationJob (VOLC)
                     │ pergunta ao Cofre: quem recebe, com qual acesso
                     ▼
                  GET /api/cofre/ativos/{id}/handoff
                     │
                     ▼
                  adapter Postiz (draft | schedule | now)
                     │ recibo com ID e URL externos
                     ▼
                  reconciliação ──► POST /api/cofre/.../verificacoes
```

**Chave de idempotência do `PublicationJob`:** derivada de
`(ativo_id, peça, versão, horário-alvo)` — nunca sorteada, pela mesma razão que
a do Cofre não é: um retry que gera chave nova publica duas vezes. O Cofre já
implementa a semântica de replay (mesma chave + mesma entrada devolve o recibo;
mesma chave + entrada diferente **falha**), e o `PublicationJob` deve copiá-la.

**O Postiz não recebe a `service_role` do Supabase.** O adapter fala com o Cofre
pela API administrativa, com sessão própria.

### P12-T11 — QA visual

Consome `destino.url_publica` e `perfis_de_navegador`, devolve o veredito como
verificação com `alvo: "ativo"`. **Falha do AdsPower não reprova a página:** o
resultado é `blocked`, que o schema distingue de `failed` justamente para isso.

## Produção criativa — o que o Cofre sabe sobre engines

`GET /api/cofre/engines` lista os engines importados dos manifestos versionados,
com modalidade, estado operacional, contagens **declaradas** e limitações.

Três coisas que este contrato afirma, e que importam para quem for montar a fila:

1. **Nenhum engine está `integrado`.** Os sete estão em `catalogado`,
   `externo_parcial` ou `somente_referencia`, porque
   `integration_state.registered_in_volc_os_runtime` é `false` e os três
   adapters também. Um consumidor que assumir runtime disponível vai falhar.
2. **Contagem ausente é `null`, nunca `0`.** `formatos: null` significa "o
   manifesto não declara", e o banco recusa gravar zero justamente para que a
   diferença sobreviva. Quem consumir deve tratar `null` como *desconhecido*, e
   não como *nenhum*.
3. **A localização é um rótulo, não um caminho.** `Drive compartilhado VOLC ·
   IESDE/2026/Aprova-Ad-Sstudio` é o que sai da API; o caminho absoluto — que
   contém o e-mail do operador — não entra no banco nem na resposta.

## O que este contrato NÃO resolve

- **Não existe `PublicationJob`.** O contrato dele está no ADR de distribuição
  orgânica; a implementação é P12-T09.
- **Não existe broker.** P03-T11 depende de P03-T09, que hoje está `blocked`
  porque não há 1Password instalado nesta máquina.
- **Não existe adapter de engine.** O runtime dos motores continua fora do
  VOLC O.S., e esta missão não o tocou de propósito.
- **O Cofre não decide pauta, não aprova peça e não escolhe destino.** Ele
  responde sobre patrimônio; a decisão é do Redator e do humano.

## Fontes

- `docs/architecture/ADR-1PASSWORD-ADSPOWER-E-RECUPERACAO-AGENTICA.md`
- `docs/architecture/ADR-DISTRIBUICAO-ORGANICA-E-QA-VISUAL.md`
- `docs/architecture/COFRE-DE-ATIVOS-CONTRATO.md`
- `supabase/migrations/v13_01_cofre_de_ativos.sql` (seções 8, 15 e 16)
- `backend/app/asset_vault/aplicacao.py` (`CasosDeUso.handoff`)
