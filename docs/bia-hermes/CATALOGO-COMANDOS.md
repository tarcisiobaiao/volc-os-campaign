# Bia web: catálogo de comandos `/`

Gerado por `scripts/bia_gerar_catalogo_comandos.py` a partir de `backend/app/agente_bia/comandos/catalogo.py`
(inventário real do Hermes v0.18.0 em `inventario_hermes_v0_18_0.json`: `COMMAND_REGISTRY` com 82 comandos
e 48 comandos de skill do profile `default`). **Não edite à mão.**

## Regras

- Texto que começa com `/` **nunca** é encaminhado ao Hermes: o servidor devolve 422 `comando_no_texto`, e o front intercepta antes.
- Só rodam os comandos com `disponivel = true`. Os locais rodam no navegador; o único de servidor (`/status`) é **somente leitura**, por rota tipada `POST /api/agent/comandos/status`, com recibo `{executado_em, origem, somente_leitura, duracao_ms}`. A rota despacha por nome: comando de servidor sem ação devolve 501.
- Nenhum comando habilita toolset. As classes `requires_tool`, `external_mutation` e `telegram_only` ficam **bloqueadas** e aparecem na paleta com o motivo.
- Comando desconhecido vira nota local "Comando desconhecido"; nada sai do navegador.
- Alias do Telegram (`/new`, `/help`…) mostra o motivo e o equivalente da web.

## Contagem por classe

| Classe | Total |
|---|---:|
| local_ui — roda na tela | 10 |
| hermes_safe — leitura do Hermes | 9 |
| requires_tool — exige ferramenta | 63 |
| external_mutation — muda algo fora | 38 |
| telegram_only — só no Telegram | 10 |
| **Total** | **137** |

## Comandos da web (disponíveis)

| Comando | Origem | Classe | Na web | Execução | Descrição / motivo |
|---|---|---|---|---|---|
| `/nova` (aliases: /new, /clear) | volc | local_ui | sim | local | Abrir uma nova conversa, isolada da atual |
| `/conversas` (aliases: /history, /sessions, /resume) | volc | local_ui | sim | local | Ver e retomar suas conversas recentes |
| `/anexar` (aliases: /image, /paste) | volc | local_ui | sim | local | Escolher imagem ou documento para enviar |
| `/copiar` (aliases: /copy) | volc | local_ui | sim | local | Copiar a última resposta da Bia |
| `/contexto <id da campanha>` | volc | local_ui | sim | local | Incluir o contexto somente leitura de uma campanha |
| `/status` (aliases: /status, /usage, /version) | volc | hermes_safe | sim | backend | Ver o estado da conversa: mensagens, tokens, custo e versão do Hermes |
| `/ajuda` (aliases: /help, /commands) | volc | local_ui | sim | local | Listar os comandos disponíveis e indisponíveis |

## Registro do Hermes (82)

| Comando | Origem | Classe | Na web | Execução | Descrição / motivo |
|---|---|---|---|---|---|
| `/start` | hermes_registro | telegram_only | não | — | Ping de início de plataforma de mensagens. |
| `/new [name]` (aliases: reset) | hermes_registro | local_ui | não | — | Na web, nova conversa é do VOLC: /nova. |
| `/topic [off\|help\|session-id]` | hermes_registro | telegram_only | não | — | Tópicos de DM do Telegram. |
| `/clear` | hermes_registro | local_ui | não | — | Na web, equivale a /nova. |
| `/redraw` | hermes_registro | external_mutation | não | — | Interface do terminal. |
| `/history` | hermes_registro | local_ui | não | — | Na web, o histórico é o do VOLC: /conversas. |
| `/save` | hermes_registro | external_mutation | não | — | Salva conversa em arquivo (terminal). |
| `/retry` | hermes_registro | hermes_safe | não | — | Bloqueado por política: nada é reenviado sem uma nova mensagem sua. |
| `/prompt [initial text]` (aliases: compose) | hermes_registro | external_mutation | não | — | Abre editor no servidor (terminal). |
| `/undo [N]` | hermes_registro | hermes_safe | não | — | Desfazer turnos conflita com o ledger e o recibo; fora da V1. |
| `/title [name]` | hermes_registro | hermes_safe | não | — | Títulos da web são do VOLC; fora da V1. |
| `/handoff <platform>` | hermes_registro | telegram_only | não | — | Passa a sessão para uma plataforma de mensagens. |
| `/branch [name]` (aliases: fork) | hermes_registro | hermes_safe | não | — | Ramificar conflita com o ledger da conversa; fora da V1. |
| `/compress [here [N] \| focus topic \| --preview\|--dry-run]` (aliases: compact) | hermes_registro | hermes_safe | não | — | Reescreve o histórico da sessão com outro modelo; fora da V1. |
| `/rollback [number]` | hermes_registro | requires_tool | não | — | Restaura checkpoints de arquivos. |
| `/snapshot [create\|restore <id>\|prune]` (aliases: snap) | hermes_registro | external_mutation | não | — | Cria ou restaura estado do Hermes (terminal). |
| `/stop` | hermes_registro | requires_tool | não | — | Mata processos em segundo plano. |
| `/approve [session\|always]` | hermes_registro | telegram_only | não | — | Aprovação de comando perigoso no canal. |
| `/deny [all] [reason]` | hermes_registro | telegram_only | não | — | Negação de comando perigoso no canal. |
| `/background <prompt>` (aliases: bg, btw) | hermes_registro | requires_tool | não | — | Roda o agente em segundo plano com ferramentas. |
| `/agents` (aliases: tasks) | hermes_registro | requires_tool | não | — | Lista agentes e tarefas do gateway inteiro. |
| `/journey [list\|delete <id>\|edit <id>]` (aliases: learning, memory-graph) | hermes_registro | requires_tool | não | — | Linha do tempo de aprendizado (terminal). |
| `/queue <prompt>` (aliases: q) | hermes_registro | requires_tool | não | — | Enfileira turnos fora do recibo do VOLC. |
| `/steer <prompt>` | hermes_registro | requires_tool | não | — | Injeta mensagem depois de uma chamada de ferramenta. |
| `/goal [text \| draft <text> \| show \| pause \| resume \| clear \| status \| wait <pid> \| unwait]` | hermes_registro | requires_tool | não | — | Meta permanente executada pelo agente com ferramentas. |
| `/moa <prompt>` | hermes_registro | requires_tool | não | — | Mistura de agentes; custo e ferramentas fora da superfície web. |
| `/subgoal [text \| remove N \| clear]` | hermes_registro | requires_tool | não | — | Critério de meta permanente. |
| `/status` | hermes_registro | hermes_safe | não | — | Na web: /status (só leitura, sessão desta conversa). |
| `/whoami` | hermes_registro | telegram_only | não | — | Nível de acesso no canal; na web, quem decide é o papel do VOLC. |
| `/profile` | hermes_registro | hermes_safe | não | — | Leitura inofensiva, mas o API Server não expõe o profile; fora da V1. |
| `/sethome` (aliases: set-home) | hermes_registro | telegram_only | não | — | Canal principal do Telegram. |
| `/resume [name]` | hermes_registro | local_ui | não | — | Na web, retome pela lista de /conversas. |
| `/sessions` | hermes_registro | local_ui | não | — | No Hermes lista sessões de todas as superfícies; na web, /conversas lista só as suas. |
| `/config` | hermes_registro | external_mutation | não | — | Configuração do profile (terminal). |
| `/model [model] [--provider name] [--global\|--session] [--refresh]` | hermes_registro | external_mutation | não | — | Troca o modelo do profile, que é o mesmo do Telegram. |
| `/codex-runtime [auto\|codex_app_server]` (aliases: codex_runtime) | hermes_registro | external_mutation | não | — | Muda o runtime do provider do profile. |
| `/personality [name]` | hermes_registro | external_mutation | não | — | Muda a personalidade do profile (afeta o Telegram). |
| `/statusbar` (aliases: sb) | hermes_registro | external_mutation | não | — | Interface do terminal. |
| `/timestamps [on\|off\|status]` (aliases: ts) | hermes_registro | external_mutation | não | — | Interface do terminal. |
| `/verbose` | hermes_registro | external_mutation | não | — | Exibição de progresso do gateway. |
| `/footer [on\|off\|status]` | hermes_registro | external_mutation | não | — | Muda a configuração do gateway. |
| `/yolo` | hermes_registro | external_mutation | não | — | Desliga aprovações de comandos perigosos. |
| `/reasoning [level\|show\|hide\|full\|clamp]` | hermes_registro | external_mutation | não | — | Muda o esforço de raciocínio do profile. |
| `/fast [normal\|fast\|status]` | hermes_registro | external_mutation | não | — | Muda o modo de prioridade do provider. |
| `/skin [name]` | hermes_registro | external_mutation | não | — | Tema do terminal. |
| `/indicator [kaomoji\|emoji\|unicode\|ascii]` | hermes_registro | external_mutation | não | — | Indicador do terminal. |
| `/voice [on\|off\|tts\|status]` | hermes_registro | external_mutation | não | — | Muda o modo de voz do profile. |
| `/busy [queue\|steer\|interrupt\|status]` | hermes_registro | external_mutation | não | — | Comportamento do terminal. |
| `/tools [list\|disable\|enable] [name...]` | hermes_registro | requires_tool | não | — | Gerencia ferramentas (terminal). |
| `/toolsets` | hermes_registro | requires_tool | não | — | Lista toolsets (terminal). |
| `/skills` | hermes_registro | external_mutation | não | — | Instala ou altera skills do profile. |
| `/memory [pending\|approve\|reject\|approval] [id\|on\|off]` | hermes_registro | external_mutation | não | — | Aprova ou altera gravações de memória longa compartilhada. |
| `/bundles` | hermes_registro | external_mutation | não | — | Pacotes de skills do profile. |
| `/pet [toggle\|list\|scale <n>\|<slug>]` | hermes_registro | external_mutation | não | — | Mascote do terminal. |
| `/hatch [description]` (aliases: generate-pet) | hermes_registro | external_mutation | não | — | Gera mascote (terminal). |
| `/learn <what to learn from>` | hermes_registro | requires_tool | não | — | Aprende skill lendo diretórios e URLs. |
| `/cron [subcommand]` | hermes_registro | requires_tool | não | — | Agenda tarefas com ferramentas. |
| `/suggestions [accept\|dismiss N \| catalog]` (aliases: suggest) | hermes_registro | external_mutation | não | — | Aceita automações sugeridas. |
| `/blueprint [name] [slot=value ...]` (aliases: bp) | hermes_registro | external_mutation | não | — | Cria automação a partir de modelo. |
| `/curator [subcommand]` | hermes_registro | external_mutation | não | — | Manutenção de skills em segundo plano. |
| `/kanban [subcommand]` | hermes_registro | external_mutation | não | — | Quadro compartilhado entre profiles. |
| `/reload` | hermes_registro | external_mutation | não | — | Recarrega variáveis de ambiente. |
| `/reload-mcp` (aliases: reload_mcp) | hermes_registro | external_mutation | não | — | Recarrega servidores MCP do profile. |
| `/reload-skills` (aliases: reload_skills) | hermes_registro | external_mutation | não | — | Recarrega skills do profile. |
| `/browser [connect\|disconnect\|status]` | hermes_registro | requires_tool | não | — | Conecta ferramentas de navegador. |
| `/plugins` | hermes_registro | external_mutation | não | — | Plugins do profile (terminal). |
| `/commands [page]` | hermes_registro | local_ui | não | — | Na web: /ajuda. |
| `/help` | hermes_registro | local_ui | não | — | Na web: /ajuda. |
| `/restart` | hermes_registro | external_mutation | não | — | Reinicia o gateway — derruba o Telegram. |
| `/usage` | hermes_registro | hermes_safe | não | — | Na web: /status (tokens e custo desta conversa). |
| `/credits` | hermes_registro | external_mutation | não | — | Conta de créditos do provedor. |
| `/billing` | hermes_registro | external_mutation | não | — | Cobrança do provedor (terminal). |
| `/insights [days]` | hermes_registro | telegram_only | não | — | Lê sessões de todas as superfícies, inclusive o Telegram. |
| `/platforms` (aliases: gateway) | hermes_registro | telegram_only | não | — | Estado das plataformas de mensagens (terminal). |
| `/platform <pause\|resume\|list> [name]` | hermes_registro | telegram_only | não | — | Pausa ou retoma plataforma de mensagens. |
| `/copy [number]` | hermes_registro | local_ui | não | — | Na web: /copiar. |
| `/paste` | hermes_registro | local_ui | não | — | Na web: cole a imagem no campo de mensagem. |
| `/image <path>` | hermes_registro | local_ui | não | — | Na web: /anexar ou o botão de anexo. |
| `/update` | hermes_registro | external_mutation | não | — | Atualiza o Hermes. |
| `/version` (aliases: v) | hermes_registro | hermes_safe | não | — | Na web: /status (inclui a versão do Hermes). |
| `/debug [nous\|local]` | hermes_registro | external_mutation | não | — | Envia logs para fora do servidor. |
| `/quit [--delete]` (aliases: exit) | hermes_registro | external_mutation | não | — | Encerra a CLI. |

## Comandos de skill do profile `default` (48)

| Comando | Origem | Classe | Na web | Execução | Descrição / motivo |
|---|---|---|---|---|---|
| `/agent-setup-migration` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/architecture-audit` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/architecture-diagram` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/arxiv` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/brainaudit` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/brainstorming` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/cerebro` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/claude-code` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/claude-design` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/codebase-inspection` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/codex` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/coding-agent-process-orchestration` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/community-intelligence-reports` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/dev-agent-dispatcher` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/dogfood` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/executing-plans` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/flush` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/git-checkpoint-transport` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/github-auth` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/github-code-review` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/github-pr-workflow` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/github-repo-management` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/google-marketing-oss-recon` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/hermes-agent` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/hermes-agent-skill-authoring` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/hermes-executor-missions` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/hermes-operationalization` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/hermes-second-brain-ops` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/hermes-second-brain-setup` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/jupyter-live-kernel` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/ocr-and-documents` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/operational-intelligence-dashboard-design` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/plan` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/popular-web-designs` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/public-evidence-governance` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/requesting-code-review` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/research-to-operational-assets` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/rotina` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/salve` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/sketch` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/systematic-debugging` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/test-driven-development` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/verification-before-completion` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/volc-agentic-ecosystem-orchestration` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/volc-agentic-orchestration` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/writing-plans` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/xurl` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |
| `/youtube-content` | hermes_skill | requires_tool | não | — | Skill do Hermes: na web não roda — a superfície web não carrega skills nem tem ferramentas. Use pelo Telegram. |

