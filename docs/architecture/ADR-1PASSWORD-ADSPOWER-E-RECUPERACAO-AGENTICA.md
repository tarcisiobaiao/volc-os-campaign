# ADR — Segredos, navegação isolada e recuperação agêntica

**Status:** aceito como direção; integrações ainda não implementadas
**Data:** 2026-08-28
**Escopo:** Cofre de Ativos, AdsPower, Redator, análise de mídia e futuras fábricas VOLC

## Resultado em uma frase

O 1Password guarda os segredos, o Supabase oficial guarda somente referências e auditoria, o AdsPower executa navegação num host isolado e o Google ADK pode acionar um agente barato para diagnosticar e reparar falhas pequenas — sempre dentro de um envelope limitado, observável e sem autoridade automática sobre produção.

## O que foi confirmado

- O 1Password MCP roda localmente pelo aplicativo desktop, usa `stdio`, pede aprovação por ambiente e expõe nomes de ambientes e variáveis sem devolver o valor secreto ao modelo.
- O MCP do 1Password serve ao operador e aos agentes locais. Ele não é, sozinho, uma solução de segredo para processos remotos e contínuos na VPS.
- A Local API do AdsPower pode ser autenticada com API key Bearer e escutada em loopback. O guia de MCP também ensina um modo com verificação desativada; esse modo não é aceito como configuração de produção VOLC.
- O Google ADK Python já existe no ambiente de desenvolvimento do projeto (`2.8.0`). O conector oficial LiteLLM suporta DeepSeek, mas o pacote LiteLLM ainda não está instalado no ambiente do harness.
- O modelo `DeepSeek-V4-Flash-0731` existe na API como `deepseek-v4-flash` e oferece interface compatível com OpenAI/Anthropic, ferramentas e saída JSON.
- O ADK oferece confirmação humana de ferramenta, mas o recurso é experimental. A segurança principal continuará no nosso domínio: allowlist de ferramentas, credenciais por referência, idempotência, limites e portões server-side.

## Decisão 1 — fronteira dos segredos

### Autoridade

| Camada | Pode guardar | Não pode guardar |
|---|---|---|
| 1Password | senha, token, chave de API e material criptográfico | estado operacional do ativo |
| Supabase oficial | ID de referência, provider, nome lógico da variável, owner, finalidade, validade, última verificação, política e recibo | valor bruto do segredo |
| Cofre de Ativos | relação ativo ↔ referência de credencial, estado e próximo uso | senha, cookie, token, chave ou `.env` |
| Grafo e Roadmap | capacidade, dependência, risco e evidência sanitizada | qualquer segredo ou identificador que permita usá-lo |

`backend/app/seguranca/segredo.py` pode continuar protegendo metadados operacionais sensíveis quando necessário. Ele não transforma o banco numa réplica do 1Password.

### Fluxo 1Password → AdsPower

```text
operador/worker local
        │ pede referência autorizada
        ▼
1Password ── injeta em memória ──► broker local do AdsPower
                                      │ loopback + Bearer
                                      ▼
                                Local API / perfil
                                      │
                                      ▼
                         screenshot + console + recibo
                                      │ sem segredo
                                      ▼
                              Supabase oficial
```

O MCP do AdsPower é adequado para desenvolvimento e operação assistida. Um job contínuo usará um broker/sidecar no mesmo host do AdsPower, com porta não pública, autenticação ativa, allowlist de ações e segredo injetado pelo mecanismo de runtime escolhido do 1Password.

## Decisão 2 — recuperação agêntica não substitui o motor determinístico

O motor determinístico continua dono de estados, validações, escrita e idempotência. O agente entra quando há uma falha que exige interpretação e não possui resolução segura já codificada.

### Casos iniciais

1. **Redator:** ler erro sanitizado, contrato da etapa, artefatos da run e recorte do grafo; propor ou executar uma correção apenas em sandbox.
2. **Tráfego:** explicar por que uma campanha não entrega usando snapshot real, frescor, políticas e evidências; somente leitura na primeira fase.
3. **Rotinas:** classificar erro, escolher recipe conhecido, produzir diagnóstico e escalar quando a confiança ou os limites acabarem.

### Envelope mínimo de uma execução

- `run_id`, `case_type`, `input_hash`, `graph_built_at` e versões de prompt/modelo/recipe;
- contexto sanitizado e mínimo; nenhum `.env`, token, cookie ou payload privilegiado;
- ferramentas numa allowlist explícita;
- no máximo 3 iterações e 12 chamadas de ferramenta no primeiro smoke;
- timeout total e orçamento de tokens/custo;
- saída tipada: `repaired`, `recommendation`, `needs_human` ou `blocked`;
- evidências, artefatos produzidos e razão da decisão;
- nenhuma ação externa no smoke;
- qualquer futura ação T1/T2 passa pela porta canônica, confirmação humana e recibo.

### Escada de autonomia

| Degrau | O agente pode fazer | Estado inicial |
|---|---|---|
| A0 | explicar e recomendar | permitido em dado sanitizado |
| A1 | editar artefato numa sandbox e revalidar | alvo do primeiro smoke do Redator |
| A2 | registrar nota/tarefa reversível | futuro, com aprovação |
| A3 | propor mutação operacional tipada | futuro, sem executar |
| A4 | executar ação limitada e reversível | proibido até ADR e canário próprios |

## Smoke de viabilidade

O contrato executável está em `docs/architecture/contracts/agentic-recovery-smoke-v1.json`.

O smoke possui duas cenas:

- uma saída inválida do Redator que pode ser corrigida localmente e revalidada;
- duas campanhas Search com entrega baixa, analisadas read-only sem inventar causa ou recomendar aumento automático de verba.

Ele passa apenas se a saída validar no schema, repetir o mesmo veredito sem efeitos colaterais, citar evidências recebidas, respeitar limites e escalar quando faltarem dados. Conectividade com o modelo, qualidade de decisão e integração ao produto são gates diferentes.

## VOLC Gold Site Factory — reservado

A fábrica de sites permanece no radar, sem competir com o destravamento de mídia. A visão é uma CLI/skill que recebe um contrato aprovado e coordena:

1. domínio e DNS, com compra sempre confirmada por humano;
2. infraestrutura e WordPress por adapter de provedor;
3. identidade visual via motores criativos VOLC;
4. tema, CSS, páginas e publicação;
5. GTM/GA4 e validação de eventos;
6. smoke visual, rollback e recibo.

Não existe ainda prova de GoDaddy MCP, contrato de compra, provisionador idempotente ou ambiente descartável. Por isso, as tarefas entram como `reserved`.

## Fontes oficiais consultadas

- 1Password Environments MCP: https://www.1password.dev/environments/mcp-server
- AdsPower MCP: https://help.adspower.com/docs/MCP
- AdsPower Local API: https://help.adspower.com/docs/api
- Google ADK com LiteLLM: https://adk.dev/agents/models/litellm/
- Google ADK — confirmação de ferramentas: https://adk.dev/tools-custom/confirmation/
- DeepSeek API — changelog: https://api-docs.deepseek.com/updates/

## Próxima decisão executável

Rodar o smoke A0/A1 fora do backend de produção, com `litellm>=1.84`, chave injetada por ambiente e zero ferramenta mutável. Só depois de medir pelo menos dez repetições é que se decide criar o adapter do Redator.
