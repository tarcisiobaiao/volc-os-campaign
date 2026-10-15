# Bia V1: contrato de `/api/agent/*`

Implementação: `backend/app/agente_bia/rotas.py`. Cliente: `src/features/bia/api.ts`.

## Portões, nesta ordem, em toda rota

1. `BIA_ENABLED` diferente de `"1"` → **404** antes de qualquer outra coisa. O auth e o Hermes não são tocados.
2. `Origin` presente e fora de `BIA_ALLOWED_ORIGINS` → **403**, sem `Access-Control-Allow-Origin`.
3. `exigir_admin`: sem token **401**, token inválido **401**, auth fora do ar **503**, papel diferente de ADMIN **403**.
4. Corpo: lido cru, até 32 KiB (**413** acima disso), JSON objeto, `extra="forbid"`. O **422** traz `{codigo, mensagem, erros:[{campo, erro}]}` e nunca o valor recusado.
5. Id de conversa ou execução fora do formato UUID → **404**, nunca 422, para não ensinar o formato.

Erros de domínio voltam como `{"detail": {"codigo": "...", "mensagem": "..."}}`.

## Rotas

### `GET /api/agent/estado`

200: `{modo: "consulta", aviso, motor_configurado: bool, limites: {max_caracteres, envios_por_minuto}, capacidades: [nome]}`

### `POST /api/agent/conversations`

O corpo é `{}` ou vazio. Qualquer campo dá 422.
201: `{conversa: {id, titulo, criada_em, atualizada_em}}`. A sessão Hermes nasce no primeiro envio.

### `GET /api/agent/conversations`

200: `{conversas: [conversa]}`, só as do dono e no máximo 50.

### `GET /api/agent/conversations/{id}/messages`

200: `{conversa, execucoes: [recibo], aviso}`. **404** se não existir ou não for do dono.
Antes de ler, rebaixa as execuções órfãs do dono (queued → cancelled, running → uncertain).

### `POST /api/agent/conversations/{id}/messages`

Corpo:

```json
{"request_id": "<uuid gerado no cliente, um por clique>",
 "texto": "1..4000 caracteres, sem caractere de controle",
 "contexto": {"campaign_ref": "<volc_campaign_id>", "janela": "ultimos_7_dias|ultimos_14_dias|ultimos_30_dias"}}
```

O campo `contexto` é opcional.

| Resposta | Quando |
|---|---|
| **202** `{execucao: recibo(queued), aviso}` | envio novo; a execução segue em fundo |
| **200** `{execucao, aviso}` + `X-Bia-Idempotente: replay` | mesmo `request_id` com o mesmo texto e a mesma conversa; nada novo sai |
| **409** `request_id_conflito` | mesmo `request_id` com outro conteúdo ou outra conversa |
| **409** `execucao_em_andamento` | já há envio do dono em queued/running |
| **409** `conversa_incerta` | a conversa tem execução `uncertain` |
| **429** `limite_por_minuto` | passou de `BIA_LIMITE_POR_MINUTO` |
| **404** | conversa inexistente ou de outro dono |
| **422** `mensagem_invalida` / `corpo_invalido` / `contexto_invalido` | vazio, grande, controle, campo extra ou contexto fora do schema |
| **503** `hermes_indisponivel` | motor não configurado; nada é reservado |
| **503** `ledger_indisponivel` | banco fora do ar ou v27_01 não aplicada |

### `GET /api/agent/runs/{id}`

200: `{execucao: recibo}`. Também rebaixa órfãs antes de ler.

### `POST /api/agent/runs/{id}/reconcile`

O corpo é `{}` ou vazio. Faz read-back da sessão no Hermes, **sem chamar o modelo**.

- 200 `succeeded` se a última mensagem do usuário na sessão é esta entrada e há resposta depois dela;
- 200 `uncertain` se não for possível concluir (o evento `reconciliacao_inconclusiva` é registrado);
- 404 se a execução não for `uncertain` ou não for do dono;
- 503 se o Hermes estiver indisponível.

### `GET /api/agent/tools`

200: `{capacidades: [{nome, descricao, efeito: "leitura", papel_minimo, entrada: jsonschema, saida: jsonschema}], mutacoes: []}`

### `POST /api/agent/tools/{nome}`

O corpo são os argumentos da capacidade (schema estrito). 200 `{resultado}`; 404 para capacidade ou campanha desconhecida; 422 para entrada inválida; 503 se a fonte estiver fora do ar.

## Recibo de execução (o único formato que sai)

```json
{"id": "uuid público", "conversa_id": "uuid", "request_id": "uuid",
 "estado": "queued|running|succeeded|failed|uncertain|cancelled",
 "entrada": "texto do operador", "resposta": "texto filtrado | null",
 "erro": {"codigo": "hermes_timeout", "mensagem": "…"} | null,
 "contexto": {"campaign_ref": "...", "janela": "..."} | null,
 "criada_em": "...", "terminada_em": "... | null"}
```

Nunca saem: o id da sessão Hermes, a chave, `usage` cru, `tool_calls`, `reasoning`, o corpo do upstream nem a mensagem de erro do upstream.

## Estados

```
queued ──► running ──► succeeded
   │          ├──────► failed      (Hermes recusou ANTES de agir: 4xx, conexão recusada, contexto ilegível)
   │          └──────► uncertain   (timeout, queda após envio, 5xx, corpo ilegível, processo morreu)
   └──► cancelled                  (nunca saiu: órfã de processo morto)
uncertain ──► succeeded | failed   (só por reconciliação read-back)
```

Códigos públicos de erro: `hermes_timeout`, `hermes_conexao`, `hermes_resposta_ilegivel`, `hermes_recusou`, `hermes_autenticacao`, `hermes_indisponivel`, `hermes_sessao_ausente`, `processo_interrompido`, `contexto_indisponivel`.

## O que o corpo não aceita (cada um vira 422)

`model`, `provider`, `profile`, `instructions`, `system_prompt`, `system_message`, `session_id`, `hermes_session_id`, `tools`, `url`, `sql`, `table`, `tabela`, `tenant`, `user_id`, `dono` e `role`, além de qualquer outro campo não listado acima.
