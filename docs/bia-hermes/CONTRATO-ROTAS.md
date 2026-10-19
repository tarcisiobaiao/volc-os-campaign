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

---

## Missão 3 (15/10/2026): anexos, fluxo e comandos

Mesmos portões acima, em todas. Nenhuma rota nova aceita URL, caminho, modelo, profile, sessão Hermes ou toolset.

### `POST /api/agent/conversations/{id}/messages` (campos novos)

`{"request_id", "texto"?, "contexto"?, "anexos"?: [uuid, …até 4]}`. Texto vazio com anexo vira "Veja os anexos.".
- `texto` começando com `/<letra>` → **422 `comando_no_texto`** (comando nunca vai ao Hermes como texto).
- Anexo que não existe, expirou ou é de outro dono → **422 `anexo_invalido`** (mesma resposta para os três). Repetido → `anexo_repetido`. Mais de 3 imagens ou 6 MB de imagem → `imagens_demais`.
- O ledger guarda só a referência `{id, nome, tipo, familia, tamanho, sha256}` em `execucao.contexto.anexos`. No envio ao Hermes o servidor confere dono e SHA-256 de novo; divergência ou arquivo sumido → turno `failed` com `anexo_indisponivel`, sem chamar o Hermes.

### `POST /api/agent/anexos`

Corpo **cru** (o arquivo), `Content-Type` do arquivo, nome em `X-Bia-Nome` (URL-encoded; só exibição, normalizado no servidor). Limite lido em fluxo: 10 MB (**413 `arquivo_grande`** sem ler o resto).
- 201: `{anexo: {id, nome, tipo, familia, mime, tamanho, sha256, criado_em, expira_em, paginas, largura, altura, caracteres, truncado}}`.
- 422: `tipo_divergente`, `tipo_proibido`, `tipo_nao_suportado`, `arquivo_vazio`, `imagem_invalida`, `pdf_protegido`, `pdf_sem_texto`, `pdf_grande`, `docx_invalido`, `docx_com_conteudo_ativo`, `documento_vazio`. 413: `arquivo_grande`, `imagem_grande`. 429: `cota_excedida`. 503: `anexo_indisponivel` (disco), sem detalhe interno.
- Mesmo arquivo do mesmo dono devolve o anexo existente com validade renovada.

### `GET /api/agent/anexos/{id}`

Bytes do PRÓPRIO anexo (imagem saneada ou documento original). `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, `Content-Security-Policy: sandbox`; imagem `inline`, documento `attachment`. Não é do dono / expirou → **404**.

### `POST /api/agent/anexos/{id}/remover`

`{}` → 200 `{removido: true}`; não é do dono → 404.

### `GET /api/agent/runs/{id}/fluxo`  (SSE)

`text/event-stream`, só leitura, só o dono. Eventos: `estado` `{execucao}` (recibo público), `parcial` `{texto}` (deltas reais do Hermes, filtrados; os últimos 64 caracteres ficam retidos até o fim; `<think>` removido), `aviso` `{codigo}`. Keepalive a cada 15 s. Termina em estado terminal ou `uncertain`. Cair e reassinar **nunca** reenvia nada.

### `GET /api/agent/comandos`

200: `{comandos: [{nome, descricao, args, origem, classe, disponivel, execucao, motivo, equivalente_web, aliases}]}` — 137 entradas (ver `CATALOGO-COMANDOS.md`).

### `POST /api/agent/comandos/{nome}`

`{conversa_id?}`. Só `disponivel` e `execucao == "backend"` (hoje: `status`). 404 `comando_desconhecido`; 403 `comando_indisponivel_na_web` (+`classe`); 409 `comando_local`; 501 `comando_sem_acao`.
200: `{comando, resultado: {conversa, hermes: {versao, gateway}, sessao_web, avisos}, recibo: {executado_em, origem: "backend", somente_leitura: true, duracao_ms}}`. Lê o ledger e `GET /health/detailed` + `GET /api/sessions/{id}` do Hermes; não escreve nada.
