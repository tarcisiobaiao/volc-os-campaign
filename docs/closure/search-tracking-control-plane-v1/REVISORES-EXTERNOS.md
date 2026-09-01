# Revisores externos — o que rodou e o que não rodou

## Gemini — NÃO DISPONÍVEL (registrado 02/09/2026, dentro dos 5 minutos)

O CLI existe (`/Users/mac/.npm-global/bin/gemini`) e **não tem método de
autenticação configurado**:

```
$ gemini -m gemini-3-flash-preview -p "<16 afirmações de contrato Google>"
Please set an Auth method in your /Users/mac/.gemini/settings.json or specify one
of the following environment variables before running: GEMINI_API_KEY,
GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_GENAI_USE_GCA
```

Conferido: `~/.gemini/settings.json` não existe; `GEMINI_API_KEY`,
`GOOGLE_API_KEY` e `GOOGLE_GENAI_*` não estão no ambiente nem em `.env`,
`.env.local`, `.env.server` ou `.env.n8n.local` deste repositório.

**Não foi construído nem consertado harness para contornar isso**, como o
briefing manda. O prompt está pronto e é reexecutável sem alteração:
`scratchpad/gemini-prompt.md` (16 afirmações sobre `goal_config_level`,
`primary_for_goal`, `include_in_conversions_metric`, custom conversion goals,
destino da Data Manager, `gclid/wbraid/gbraid`, event time, currency/value,
`transaction_id` e tipos de ação aceitos como destino). Ele não contém código,
credencial, id de conta real nem dado de produção.

⚠️ **Nota de segurança, separada e não acionada:** existe uma `GEMINI_API_KEY` em
texto claro dentro de uma REGRA DE PERMISSÃO em `~/.claude/settings.json`
(linhas 411 e 413), de outro projeto. Ela **não foi usada** — uma chave que
aparece dentro de um allowlist de comando não é configuração desta missão, e
usá-la seria reaproveitar credencial de outro contexto. Fica registrado porque
uma chave em texto claro num arquivo de permissões merece rotação, e porque
autenticar o CLI é o desbloqueio de uma linha para o dono.

### O que ficou sem validação externa por causa disso

As afirmações sobre contrato Google que este código passou a impor. Elas foram
verificadas **contra a documentação já citada no próprio repositório** (a
entrega anterior registrou `evidence/GOOGLE-ADS-DOCS-2026-09-01.md` e uma
validação Gemini de 01/09/2026 com 12 de 14 afirmações corretas), e contra o
descritor real do SDK v25 onde o código o cita. Nenhuma afirmação NOVA de
contrato Google foi introduzida por esta entrega — as regras aplicadas
(`primary_for_goal` inverte o veredito quando ausente, custom goal tira as listas
do comando, destino por conta dona + id numérico) já existiam no código base e
foram REUSADAS, não reescritas.

A única afirmação genuinamente nova é a que sustenta o portão de
`MAXIMIZE_CONVERSION_VALUE`, e ela é sobre o que ESTE sistema não lê — não sobre
o que o Google faz: *"nenhuma das cinco leituras GAQL desta casa consulta
`conversion_action.value_settings`, logo não há como provar que a ação eleita
carrega valor."* Isso é verificável por `grep` neste repositório, e está.

## Codex `gpt-5.6-sol` (effort high) — RODOU

Ver `ADJUDICACAO-CODEX.md`.
