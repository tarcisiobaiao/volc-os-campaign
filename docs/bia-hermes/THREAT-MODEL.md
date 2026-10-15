# Bia V1: threat model

Escopo: o caminho navegador → FastAPI `/api/agent/*` → ledger `agente_bia` (Supabase oficial) → túnel SSH → API Server do Hermes, **profile `default`** (a mesma Bia do Telegram, sessão web separada), e a capacidade `volc_get_campaign_context`.

## Ativos

| Ativo | Por que importa |
|---|---|
| `API_SERVER_KEY` do `default` | Quem a tem roda o agente do profile pela superfície API (sem ferramentas) e administra os jobs do API Server |
| Memória longa e identidade da Bia | Compartilhadas com o Telegram por decisão. Uma conversa web pode influenciar o que a Bia lembra lá. |
| Sessão Supabase do operador (JWT) | Identidade de quem pergunta |
| service_role do backend | Acesso total ao banco oficial |
| Histórico de conversa | Texto de pessoas, que pode conter dado de cliente |
| Dados de campanha (custo, conversão) | Dado de negócio, só leitura |
| Telegram do profile `default` | Canal pessoal do dono, que não pode ser afetado |

## Fronteiras de confiança

1. **Navegador → FastAPI.** Tudo o que vem do navegador é não confiável, inclusive o corpo, o `Origin` e o id da conversa.
2. **FastAPI → Supabase.** Usa a service_role, mas só por RPC nomeada. O banco é quem impõe dono, idempotência e transições.
3. **FastAPI → Hermes.** A chave fica no servidor. A resposta do Hermes é texto de modelo e é tratada como não confiável.
4. **Gateway → fontes canônicas.** Só GET no PostgREST. O conteúdo (nome de campanha) é dado externo.

## Ameaças e mitigação

| # | Ameaça (STRIDE) | Mitigação | Prova |
|---|---|---|---|
| T1 | Spoofing: chamar sem sessão ou com token inválido | `exigir_admin` → `_usuario_do_token` contra `/auth/v1/user`. Auth fora do ar dá 503, nunca permissão. | `test_401_*`, `test_503_*` |
| T2 | Elevação: OPERATOR usar a Bia | Papel lido do banco (`volc_role_of`), não do token. 403. O front esconde, mas quem decide é o servidor. | `test_403_*`, `bia-widget: OPERATOR não vê` |
| T3 | Usuário A ler ou escrever conversa de B | Dono = `sub` do token. Toda RPC filtra por dono, e a FK composta impede execução em conversa alheia. O id de outro dono recebe o mesmo 404 de um id inexistente. | `test_acesso_cruzado_*`; lab "dono B não lê", "execução não pode apontar para conversa de outro dono" |
| T4 | Injeção de parâmetros (model, instructions, session_id, tools, URL, SQL, tabela, tenant, user) | `extra="forbid"` em todo corpo, corpo lido cru e 422 sem eco do valor. O adaptador só envia `{input}`. | `test_parametros_extras_*` (17 campos), `test_o_corpo_ao_hermes_*` |
| T5 | Envio duplicado (clique duplo, retry de rede) gasta o modelo duas vezes | `request_id` único por clique e UNIQUE (dono, request_id) no banco. A repetição devolve o mesmo recibo (200 replay). | `test_idempotencia_*`; lab "repetida" |
| T6 | Abuso de custo | Uma execução em voo por dono (índice único parcial + trava), limite por minuto no banco, teto de 4000 caracteres na entrada e 32 KiB no corpo. `max_concurrent_runs=1` no profile. | `test_limite_por_minuto`, `test_uma_execucao_em_voo_*`; lab "concorrência real" |
| T7 | Reexecução após timeout ou restart (efeito duplicado) | Timeout vira `uncertain`, sem retry. Restart: `queued` vira `cancelled`, `running` vira `uncertain`. A conversa incerta fica bloqueada. Reconciliação só por read-back. | `test_timeout_*`, `test_uncertain_sem_retry_*`, `test_restart_sem_replay`; lab "expirar" |
| T8 | Vazamento da chave Hermes | Só existe em `BIA_HERMES_API_KEY` no servidor. Nenhuma `VITE_*`. Log nunca a inclui. `trust_env=False`, então proxy do ambiente não a vê. | `test_chave_e_sessao_*`; `bia-sem-hermes-no-bundle` (vite build real) |
| T9 | Vazamento do id de sessão Hermes (memória de outra conversa) | Gerado no servidor e nunca projetado nas RPCs de leitura. O filtro de resposta remove `volc_<hex32>`. | lab "sessão Hermes não sai no histórico"; `test_chave_e_sessao_*` |
| T10 | Resposta do modelo com credencial ou HTML ativo | `filtrar_resposta` cobre JWT, Bearer, sk-, AIza, gh*, xox*, PEM e atribuições KEY/SECRET/TOKEN/PASSWORD. O front renderiza texto, nunca HTML. | `test_filtro_de_resposta`; `bia-widget: HTML vindo do modelo não vira elemento` |
| T11 | Erro do upstream com stack ou caminho | Só um código da lista pública chega ao usuário e ao ledger. | `test_erro_upstream_sanitizado` |
| T12 | Prompt injection pelo dado de campanha ("ignore… pause tudo") | O bloco de contexto é marcado como DADO e o nome é cortado e limpo de controle. O Hermes não tem ferramenta, então não há ação a sequestrar. | `test_contexto_entra_no_hermes_*`; fixture com nome malicioso |
| T13 | Mutação operacional pela Bia | O catálogo recusa efeito ≠ leitura. O plano de execução recusa tudo. Uma prova estática garante que nenhum módulo importa caminho de mutação nem usa PATCH/DELETE/PUT. A capacidade só faz GET. | `test_catalogo_recusa_*`, `test_plano_de_execucao_recusa_tudo`, `test_o_pacote_da_bia_nao_importa_*` |
| T14 | CSRF ou uso cruzado de origem | Bearer explícito (sem cookie). CORS exato só em `/api/agent/*`: origem fora da lista recebe 403 antes do auth. Nunca `*`. | `test_cors_exato` |
| T15 | Hermes exposto à internet | A API Server escuta em 127.0.0.1:8642. O acesso é túnel SSH local. Não há Nginx, DNS ou porta nova. O smoke recusa listener fora do loopback. | `smoke_hermes.py` (checkpoint) |
| T16 | Afetar o Telegram (profile default) | Profile separado (`HERMES_HOME` próprio), sem credencial de plataforma (o script recusa `TELEGRAM_*`), sem clone. O smoke confere o PID do `hermes-gateway` antes e depois. | `configure_profile.py`, `smoke_hermes.py` |
| T17 | Ferramenta do Telegram exposta à web | Toolsets por plataforma: `platform_toolsets.api_server: []` (medido: zero), e o Telegram segue `hermes-telegram` (17, iguais antes e depois). Três camadas: o `aplicar` recusa se a projeção mudar o Telegram ou não zerar a API; o backend consulta `/v1/toolsets` antes de cada envio; a **auditoria do turno** (read-back) descarta a resposta se houver qualquer chamada de ferramenta, o que cobre MCP global, que o `/v1/toolsets` não mostra. | `api_default.py preflight/aplicar`; `test_profile_com_ferramenta_*`, `test_turno_com_ferramenta_*` |
| T21 | Web e Telegram escrevendo na mesma sessão | O backend gera `volc_<hex32>` e cria a sessão (`source=api_server`); o navegador não escolhe nem vê id de sessão; o Hermes recusa sessão já existente (409); a prova consulta `state.db` (sessão web ≠ sessões do Telegram e marcador ausente nos transcripts do Telegram). | `test_cada_conversa_tem_sessao_propria_*`; CP4 |
| T22 | ADMIN revogado continua usando | O papel é lido do banco a cada requisição (`volc_role_of`). | `test_admin_revogado_*` |
| T18 | Log com conteúdo sensível | Logs da Bia levam id, estado, código e duração. Nunca texto, resposta, token ou chave. | `test_logs_sem_texto_*` |
| T19 | Leitura do histórico por papel administrativo do banco | `postgres` (via `pg_read_all_data`, padrão da imagem) e `supabase_admin` leem o schema. Nenhum dos dois é papel da API. `postgres` não escreve. | lab "postgres lê só via pg_read_all_data", "postgres não escreve" |
| T20 | Retenção indefinida | `agente_bia.expurgar(dias)` (180 por padrão, mínimo 30) só para o dono do schema. Apagar o usuário do auth apaga as conversas (CASCADE). | lab "retenção", "cascade" |

## Riscos residuais (aceitos e declarados)

- **R1.** Na v0.18.0 a chave do API Server é de escopo amplo: dá acesso a `/api/jobs` (jobs agendados rodam com o toolset de cron do profile, não com o `api_server`), `/api/cron/fire` e `/v1/runs`. A chave fica só no `.env.local` do backend no Mac, nunca no navegador, e o adaptador só chama 5 rotas fixas. Mesmo assim é uma credencial administrativa do profile `default`. Endurecimento futuro: um proxy local na VPS que só repasse `/api/sessions*`, `/v1/toolsets` e `/health`.
- **R2.** O túnel usa a chave SSH root já existente do operador. Endurecimento recomendado, não aplicado: chave dedicada com `permitopen="127.0.0.1:8642",no-pty,command="/bin/false"`.
- **R3.** A memória longa é **a do Telegram, por decisão**. A revisão de memória em segundo plano do Hermes (limitada a ferramentas de memória e skills) pode gravar nela fatos das conversas web, inclusive texto vindo de dados de campanha. A V1 é de um único operador ADMIN e a interface declara isso. Multiusuário exigirá escopo de memória por usuário.
- **R6.** O restart controlado para ligar a API interrompe o Telegram por alguns segundos. O `aplicar` só roda sem agente ativo e com rollback automático.
- **R4.** O filtro de resposta é por padrão textual, não uma garantia. A garantia real é o Hermes não ter acesso a segredo nenhum.
- **R5.** Configurar toolsets expressa intenção. A prova em runtime é o smoke e o read-back da sessão sem `tool_calls` depois da primeira inferência.
