# ADR: Bia V1, a conversa autenticada do VOLC O.S. com o Hermes privado

- **Estado:** aceito para a branch `feat/bia-hermes-volc-v1` em 15/10/2026. Código e prova hermética estão prontos. A prova real aguarda dois checkpoints externos: aplicar a migration v27_01 e subir o profile `volcweb`.
- **Tarefas do roadmap:** P09-T04 (Bia em modo leitura e sugestão) e P09-T06 (gateway agêntico somente leitura).
- **Nós do grafo:** `cap_bia_copilot`, `system:hermes`, `concept:ads_agent_gateway` e `doc:bia-proposal`.
- **Insumo considerado:** `TUTORIAL_BIA_VOLC_HERMES.docx`. Foi tratado como proposta, não como autoridade.

## Pergunta

Onde deve morar a ponte entre o navegador do VOLC e o Hermes? Quem autentica, onde a conversa é guardada e como a Bia passa a ver dados do VOLC sem ganhar poder de agir?

## Fatos levantados em 15/10/2026

| Fato | Evidência |
|---|---|
| O FastAPI canônico roda só no Mac do operador (uvicorn em :8010) e não está em produção. O front de produção é Vercel + Express. | `start-dev.sh`; `docs/architecture/ADR-RUNTIME-ORAKUL-E-WORKERS.md:20` |
| O FastAPI já valida a sessão do navegador contra o Supabase oficial e lê o papel do banco (`exigir_usuario` e `exigir_admin`). Não usa JWT local nem `user_metadata`. | `backend/app/seguranca/identidade.py` |
| O Hermes v0.18.0 roda na VPS Hostinger `srv1546019` com um único profile, `default`. Ele atende o Telegram pelo `hermes-gateway.service`, como root. | `hermes profile list` e `hermes gateway status`, lidos somente |
| Nenhuma API Server do Hermes escuta hoje. Só o painel ocupa 127.0.0.1:9119. A curadoria dizia 8642, mas não há listener nessa porta. | `ss -ltnp` na VPS |
| A API Server da v0.18.0 tem `/api/sessions`, `/api/sessions/{id}/chat` (síncrono) e `/api/sessions/{id}/messages`. A rota `/chat` **aceita** `instructions`/`system_message` e `X-Hermes-Session-Key` do chamador. | `gateway/platforms/api_server.py:1722,1811,1876`, lido somente |
| Com `platform_toolsets.api_server = []`, a resolução de toolsets devolve conjunto vazio. Um nome inexistente fica como toolset "habilitado" fantasma. | `_get_platform_tools` executado com `HERMES_HOME` temporário, sem tocar em profile |
| Do Mac, a VPS é alcançável por SSH (alias `hermes`). | `~/.ssh/config` |

## Decisão

### 1. As rotas `/api/agent/*` ficam no FastAPI existente. Não há bridge separado.

O `bridge.py` do tutorial traria um segundo FastAPI, uma segunda validação de token, SQLite como fonte de verdade e uma allowlist de UUID no ambiente. Nada disso é necessário: o backend existente já tem a identidade correta, a autoridade Supabase e os padrões de ledger e recibo. A Bia é o módulo `backend/app/agente_bia/`, organizado em `dominio`, `portas`, `aplicacao`, `infra_*` e `rotas`, e reaproveita:

- `exigir_admin`: a V1 é só para ADMIN, com o papel lido do banco a cada requisição;
- `Settings` central, com flag estrita `BIA_ENABLED=1`;
- o Supabase oficial como persistência, por RPC nomeada (o mesmo padrão de `volc_role_of`);
- `secureApi` no front, que ganhou o parser do `detail` do FastAPI e um método `requisitar`.

### 2. O FastAPI alcança o Hermes pelo loopback, por um túnel SSH local

A topologia real mostra que o backend existente consegue alcançar o Hermes sem expor nada: um túnel SSH aberto a partir do Mac (`ssh -N -L 127.0.0.1:18643:127.0.0.1:8643 hermes`). Isso dispensa Nginx, DNS, firewall e Tailscale. A base do Hermes aceita `http` **somente em loopback**; qualquer outro host exige `https` (`configuracao.validar_base_hermes`). Quando o FastAPI for implantado num servidor (proposta do ADR-RUNTIME), o mesmo contrato vale com túnel persistente ou Tailscale Serve. Funnel e porta pública ficam fora.

### 3. O ledger da conversa fica num schema privado do Supabase oficial (v27_01). SQLite foi descartado.

SQLite local seria uma segunda fonte de verdade, sem backup e presa ao disco de uma máquina. Por isso a migration candidata `v27_01_agente_bia.sql` define:

- três tabelas (`conversa`, `execucao`, `evento`) no schema `agente_bia`, fora do Data API, com RLS e sem privilégio para anon, authenticated ou service_role;
- 11 RPCs `SECURITY DEFINER` com `search_path` fixo e EXECUTE só para service_role, todas filtrando pelo dono, que é o auth UUID apurado pelo backend;
- garantias que o próprio banco impõe: idempotência por `(dono, request_id)`, uma execução em voo por dono (índice único parcial e trava consultiva), limite por minuto, conversa com execução incerta bloqueada, transições fechadas e eventos append-only.

Esse ledger não guarda número financeiro, e nenhuma view de negócio o lê.

### 4. Execução: 202 e tarefa de fundo, com incerteza honesta

O envio é reservado no banco como `queued` e a resposta é 202. A ida ao Hermes roda em tarefa de fundo do mesmo request. Estados possíveis: queued, running, succeeded, failed, uncertain e cancelled.

- Timeout, queda de conexão depois do envio, 5xx ou corpo ilegível viram `uncertain`.
- `uncertain` nunca é reenviado. A única saída é a reconciliação por read-back (`GET /api/sessions/{id}/messages`), que não chama o modelo.
- No restart, quem estava `queued` vira `cancelled`, porque nunca saiu. Quem estava `running` vira `uncertain`.

### 5. O adaptador do Hermes manda só `{input}`

O adaptador nunca envia `instructions`, `system_message`, `model` ou `X-Hermes-Session-Key`, e não existe parâmetro na assinatura que permita enviá-los. O id da sessão Hermes (`volc_<32 hex>`) é gerado no servidor, guardado no banco e nunca sai pelas rotas.

### 6. VOLC Agent Gateway: capacidade tipada, invocada pelo servidor, injetada como dado

O profile `volcweb` não recebe ferramenta, MCP nem credencial. Quando o operador pede contexto de campanha, o **backend** invoca `volc_get_campaign_context` em nome do usuário autenticado e manda o resultado ao Hermes como bloco delimitado e marcado como dado não confiável. Essa escolha:

- mantém o Hermes sem caminho de ação;
- deixa a autorização no servidor, com o papel do usuário real e não um token de serviço do agente;
- impede que conteúdo de campanha, anúncio ou funil amplie o que a Bia pode fazer.

O catálogo (`gateway/catalogo.py`) recusa no registro qualquer capacidade cujo efeito não seja `leitura`. A próxima fase poderá expor o mesmo catálogo ao Hermes como MCP com token por execução, escopo e recibo. Isso não está habilitado aqui.

## Evolução registrada, não implementada

| Papel | Componente | Pode mutar? |
|---|---|---|
| Interface conversacional e coordenadora | Hermes (profile `volcweb`, depois perfis por domínio) | Não. Propõe. |
| Capacidades de negócio tipadas | VOLC Agent Gateway (`backend/app/agente_bia/gateway/`) | Não. Lê e, na fase 2, registra proposta. |
| Worker interno para missões delimitadas | Codex SDK ou app-server (interface `WorkerInterno` em `gateway/execucao.py`) | Não diretamente. Missão tipada com recibo, nunca shell exposto ao Hermes. |
| Mutação | Execution plane (`PlanoDeExecucao`; modelo: `trafego/ledger.py`, v10_02) | **Só ele**, depois de aprovação humana vinculada ao sha256 do payload, com read-back e recibo |

Autonomia não se decide por prompt: é dado do execution plane, por ação e por conta. Na V1, `PlanoDesabilitado` recusa propor, aprovar e executar.

## Consequências

- O widget só funciona com o FastAPI no ar, ou seja, hoje só no Mac do operador. É coerente com o resto do FastAPI. Implantar o backend é decisão do ADR-RUNTIME.
- A prova real depende de dois atos externos autorizados: aplicar a v27_01 e subir o `volcweb`. Os comandos estão em `docs/bia-hermes/RUNBOOK-IMPLANTACAO.md`.
- O papel `postgres` da imagem Supabase lê o schema via `pg_read_all_data`, porque é administração do banco e não papel da API. Ele não escreve. Ver o threat model.

## Alternativas recusadas

- **Bridge do tutorial na VPS (Caminho A):** duplica o backend e a autenticação, cria SQLite como fonte de verdade e exige mudar Nginx, DNS e certificado na VPS do Telegram.
- **Navegador falando direto com o Hermes:** a chave do profile iria para o bundle.
- **Dar ferramentas ou MCP ao Hermes na V1:** o modelo passaria a decidir quando ler dado de negócio, com credencial própria. A injeção pelo servidor é mais estreita.
- **Reaproveitar a sessão do Telegram:** misturaria memória pessoal e operacional. O próprio Hermes recusa sessão de outra superfície nas rotas de API.
