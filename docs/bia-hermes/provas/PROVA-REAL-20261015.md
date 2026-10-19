# Bia V1: recibo da prova real (15/10/2026, cerca de 21h40 a 22h00 BRT)

Topologia: frontend real na worktree (Vite :8091) → FastAPI da worktree (:8031) → túnel SSH (`127.0.0.1:18642` → VPS `127.0.0.1:8642`) → Hermes v0.18.0, **profile `default`** (a mesma Bia do Telegram), superfície `api_server` sem ferramentas. O ledger fica no Supabase oficial (`agente_bia`, v27_01). Operador: Tarcisio (ADMIN), logado no próprio navegador.

## Gates antes de qualquer mensagem

| Gate | Evidência |
|---|---|
| Telegram conectado | `gateway_state.json`: pid 1537673 (novo), `running`, telegram `connected` desde 00:40:32Z; nenhum erro de Telegram no journal depois do restart |
| O VOLC usa o profile `default` | 8642 escuta só em `127.0.0.1`, no próprio processo `hermes-gateway` (pid 1537673); `/root/.hermes/profiles` não existe |
| API sem ferramenta | `/v1/toolsets` 200 com zero habilitados; `_get_platform_tools(api_server)` = `[]`; Telegram com os mesmos 17 toolsets |
| Rota protegida sem chave | `/v1/models` 401 |
| Um só consumidor do bot | um único `hermes_cli.main gateway run` |
| Restart | um, pelo `api_default.py aplicar`; todos os gates verdes; rollback não acionado (`hermes-aplicar-recibo-20261016-004014.json`) |

## Roteiro executado na interface real

| # | Passo | Resultado | Duração / tokens | Ferramentas |
|---|---|---|---|---|
| 1 | "Responda apenas: conexão VOLC funcionando." | `succeeded`: "conexão VOLC funcionando." | 13,6 s (modelo 8,6 s) · 1.348 / 11 | 0 |
| 2 | registro do código AMBAR | `succeeded`: "anotado." | 2,6 s · 1.439 / 8 | 0 |
| 3 | reload da página + nova aba | histórico recuperado pelo id salvo do usuário | — | — |
| 4 | "Qual é o código desta conversa?" | `succeeded`: "AMBAR" (contexto mantido depois do reload) | 3,4 s · 1.493 / 6 | 0 |
| 5 | nova conversa, mesma pergunta | 1ª tentativa `failed: hermes_recusou` (título de sessão repetido; ver Defeitos). 2ª tentativa `succeeded`: **não respondeu AMBAR** (isolada) | 4,3 s · 1.360 / 28 | 0 |
| 6 | id aleatório (conversa e run) e id fora do formato | 404 / 404 / 404 | — | — |
| 7 | campos proibidos `model`, `instructions`, `session_id`, `tools`, `profile` | 422 em todos, sem ecoar o valor | — | — |
| 8 | sem credencial / credencial inválida | 401 / 401 | — | — |
| 9 | logout pela UI | widget desmontado, sessão removida do navegador, token antigo **401 no servidor** | — | — |

Modelo do profile: `gpt-6.1-sol` (provider `openai-codex`). O `state.db` registra o custo como `0.0`, `cost_status=included` (plano). Somando as sessões web: 4.488 tokens de entrada e 53 de saída.

## Gates depois

| Gate | Evidência (state.db do Hermes, só leitura, sem conteúdo) |
|---|---|
| Sessão web separada | 2 sessões `source=api_server`, ids `volc_<hex32>` criados pelo backend; as sessões ativas do Telegram continuam com **137 e 90 mensagens**, idênticas à linha de base |
| Identidade e memória do mesmo profile | trechos do `SOUL.md`, `MEMORY.md` e `USER.md` presentes no system prompt da sessão web |
| Mensagem web fora do Telegram | 0 mensagens novas em sessões do Telegram; 0 marcadores `[ref VOLC` nelas; as 8 mensagens novas desde a linha de base são todas `api_server` |
| Nenhuma ferramenta chamada | `tool_call_count = 0` e 0 mensagens `tool`/`tool_calls` nas sessões web; `ferramentas_no_turno = 0` em todo recibo |
| Chave fora do navegador | a chave existe só em `backend/.env.local`; 0 ocorrências em `.env.local`/`.env.server`; 0 `VITE_*` do Hermes; módulos da Bia servidos ao navegador sem chave nem endereço do Hermes |
| Navegador só no FastAPI do VOLC | as chamadas da Bia vão só para `localhost:8031/api/agent/*`; nenhum destino 8642/18642/VPS na página |
| Mutação externa | nenhuma: escritas só em `agente_bia` (2 conversas, 5 execuções, 15 eventos); fingerprint do schema igual ao pós-v27_01 (`dfe4bc0c…`); no FastAPI, toda escrita foi em `/api/agent/*` (o resto foram GETs do próprio dashboard); nenhum job/cron criado no Hermes (só o batimento do agendador mudou) |
| Telegram depois | `connected`, `active_agents 0`, sem erro no log |

## Defeitos encontrados na prova real e corrigidos

1. **Título de sessão repetido.** O Hermes exige título único por sessão (`set_session_title` levanta ValueError, que vira 400). A 2ª conversa falhou com `hermes_recusou`; a falha foi certa, porque nada rodou. Correção: título `VOLC · Bia · <8 hex>`. O dublê de teste agora recusa título repetido, e há regressão.
2. **Marcador da auditoria confundindo o modelo.** Perguntada pelo "código da conversa" numa conversa nova, a Bia respondeu o id da execução, que aparece no marcador `[ref VOLC <id>]`. Não é segredo (o id é público), mas é ruído. Correção: o marcador agora diz que é metadado técnico a ignorar.
3. **Autenticação intermitente.** Duas chamadas ao `/auth/v1/user` falharam por rede e deram 503. O portão falhou fechado e nada foi reservado nem enviado. Em seguida, 8/8 chamadas responderam em cerca de 0,5 s.
4. **Automação (não é defeito do produto).** No reenvio depois do 503, o campo preservava o texto (por desenho, sem reenvio automático) e a minha digitação emendou os dois. A mensagem do AMBAR foi gravada duplicada.

## O que não foi provado

- **Troca de usuário com um segundo login real.** Não há segunda conta ADMIN, e criar contas está fora do que posso fazer. Ela está provada por testes automatizados (`key={user.id}`, armazenamento por uid) e no banco real (outro dono não lê, postflight).
- **Teste humano no Telegram.** O estado `connected` e o log estão comprovados. Uma mensagem sua no Telegram fecha a conferência.
- **`volc_get_campaign_context` em inferência real.** Não fez parte do roteiro autorizado. Ela está provada hermeticamente.
