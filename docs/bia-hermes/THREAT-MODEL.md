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

- **R1.** Na v0.18.0 a chave do API Server é de escopo amplo: dá acesso a `/api/jobs` (jobs agendados rodam com o toolset de cron do profile, não com o `api_server`), `/api/cron/fire` e `/v1/runs`. Ela também abre **as sessões do Telegram** (`/api/sessions/{id}/messages` e `/chat` aceitam qualquer id do profile): quem tiver a chave pode ler e escrever no histórico pessoal. A chave fica só no `.env.local` do backend no Mac, nunca no navegador. O adaptador só chama 5 rotas fixas e **recusa qualquer id de sessão fora de `volc_<hex32>`** (`test_adaptador_recusa_sessao_que_nao_e_do_volc`). Mesmo assim é uma credencial administrativa do profile `default`. Endurecimento futuro: um proxy local na VPS que só repasse `/api/sessions*`, `/v1/toolsets` e `/health`.
- **R2.** O túnel usa a chave SSH root já existente do operador. Endurecimento recomendado, não aplicado: chave dedicada com `permitopen="127.0.0.1:8642",no-pty,command="/bin/false"`.
- **R3.** A memória longa é **a do Telegram, por decisão**. A revisão de memória em segundo plano do Hermes (limitada a ferramentas de memória e skills) pode gravar nela fatos das conversas web, inclusive texto vindo de dados de campanha. A V1 é de um único operador ADMIN e a interface declara isso. Multiusuário exigirá escopo de memória por usuário.
- **R7.** A auditoria por turno **detecta** uso de ferramenta, mas não impede: se um uso acontecesse, o efeito já teria ocorrido quando o turno é marcado `failed`. A prevenção é o `api_server: []` mais o portão `/v1/toolsets`. A revisão de memória e skills em segundo plano roda fora do transcript da sessão e a auditoria não a vê. Uma **skill** escrita a partir de texto de campanha passaria a ser carregada pelo agente do Telegram, que tem ferramentas: é um caminho persistente de injeção entre superfícies, e é por isso que o contexto entra marcado como dado e a V1 é de um único ADMIN.
- **R8.** Quando a reconciliação detecta ferramenta, a linha vai a `failed`, mas a RPC aplicada (v27_01) mantém o `erro_codigo` anterior (ex.: `hermes_timeout`). O uso fica registrado em `detalhe.ferramenta` e no evento `reconciliada`. Corrigir exige uma v27_02, porque a v27_01 já está aplicada e não é alterada.
- **R6.** O restart controlado para ligar a API interrompe o Telegram por alguns segundos. O `aplicar` só roda sem agente ativo e com rollback automático.
- **R4.** O filtro de resposta é por padrão textual, não uma garantia. A garantia real é o Hermes não ter acesso a segredo nenhum.
- **R5.** Configurar toolsets expressa intenção. A prova em runtime é o smoke e o read-back da sessão sem `tool_calls` depois da primeira inferência.

## Missão 3 (15/10/2026): anexos, fluxo e comandos

| # | Ameaça | Mitigação | Prova |
|---|---|---|---|
| T23 | Arquivo malicioso (executável, script, HTML/SVG ativo, polyglot, ZIP genérico, DOCX com macro) | Tipo pelos BYTES contra extensão e Content-Type; assinaturas proibidas; imagem recodificada (polyglot vira só imagem); DOCX com teto de entradas/tamanho e sem `vbaProject`/`embeddings`. | `test_recusas_*`, prova real `falso.png` |
| T24 | Bomba de descompressão / DoS por upload | 10 MB lidos em fluxo (413 sem ler o resto); limite de pixels conferido **no cabeçalho, antes de decodificar** (40 Mpx; o global do Pillow só avisava até 2×); imagem reduzida a 2048 px; PDF ≤ 300 páginas e extração que para no limite; cota 40 arquivos/80 MB por usuário. | `test_imagem_com_pixels_demais_*`, `test_pdf_com_paginas_demais_*` |
| T25 | Anexo de outro usuário (IDOR) | Pasta por `sha256(dono)`, `Armazem.obter` confere UUID + dono no metadado; download, remoção, envio e `/fluxo` só do dono; 404 igual para "não existe" e "não é seu". | `test_anexo_de_outro_dono_e_404_e_nao_entra_em_mensagem` |
| T26 | Corrida entre uploads paralelos apagando arquivo alheio | Trava por dono (thread + `flock`) em gravar/remover/limpar; órfão só é lixo depois de 10 min; cota conferida dentro da trava. | `test_uploads_paralelos_*` |
| T27 | Injeção por conteúdo de arquivo | Texto em bloco com nonce aleatório por mensagem, declarado DADO; linhas que imitam a moldura neutralizadas; nomes sem colchetes/bidi e dentro de bloco; nunca no system prompt; e, acima de tudo, **zero ferramentas** no turno web (portão + auditoria). | `test_texto_do_arquivo_que_imita_*`, `test_nome_de_arquivo_*` |
| T28 | Vazamento por streaming (raciocínio, tool call, segredo pelo prefixo) | Só `assistant.delta` é repassado; evento de ferramenta aborta o turno; `<think>` removido; últimos 64 caracteres retidos até o fim; mesmo filtro da resposta final; parcial só para o dono. | `test_parcial_retem_*`, `test_streaming_*`, `test_ferramenta_no_stream_*`, `test_fluxo_sse_*` |
| T29 | Comando `/` encaminhado ao agente / comando que muda algo | Texto com `/` → 422 no servidor e interceptado no front; allowlist tipada; só `/status` roda no servidor (leitura), por despacho explícito; classes `requires_tool`/`external_mutation`/`telegram_only` bloqueadas com motivo. | `test_texto_com_barra_*`, `test_comando_*` |
| T30 | XSS pela resposta (Markdown) | `react-markdown` com `skipHtml`, sem `dangerouslySetInnerHTML`; link só http(s)/mailto, `noopener noreferrer nofollow`, domínio visível; imagem remota nunca carregada. | `bia-widget.test.tsx` "Markdown sanitizado" |
| T31 | Rascunho/estado de um usuário visto por outro | `key={user.id}` desmonta tudo; rascunho por usuário+conversa no `sessionStorage`; logout apaga os rascunhos da aba. | "troca de usuário isola conversa e rascunho", "logout … apaga os rascunhos" |

### Revisão dos riscos R3 e R7 com o código do Hermes v0.18.0 (lido na VPS, só leitura)

- A revisão de memória/skills em segundo plano só dispara se a ferramenta `memory` (ou `skill_manage`) estiver em `valid_tool_names` do agente do turno (`agent/turn_context.py:307-313`, `agent/turn_finalizer.py:455-459`). No `api_server` o toolset é vazio: **turnos web não disparam revisão nem gravam memória/skill sozinhos.** Não há provedor de memória externo configurado.
- **R9 (novo, aberto).** O `session_search` do agente do Telegram (que TEM ferramentas) enxerga sessões `api_server`: só `subagent` e `tool` ficam ocultas (`tools/session_search_tool.py:36-41`). Texto de um arquivo de terceiros enviado na web pode, mais tarde, voltar como resultado de busca numa conversa do Telegram — um caminho indireto de injeção para uma superfície com ferramentas. Mitigações possíveis, todas fora desta missão e **decisão do dono**: (a) aceitar (operador único, conteúdo próprio); (b) restringir anexos a arquivos próprios; (c) pedir ao Hermes uma fonte oculta para sessões web; (d) profile separado para a web (já recusado na missão 2).
