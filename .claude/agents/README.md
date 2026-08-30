# Agentes de projeto do VOLC O.S.

Seis agentes versionados que reproduzem o protocolo de condução usado nas
missões longas deste repositório. Medidos contra **Claude Code 2.1.247**.

## Quem é quem

| agente | escreve? | modelo | effort | background | papel |
|---|---|---|---|---|---|
| `volc-coordinator` | **sim — o único** | opus | high | não | conduz o ciclo, delega, implementa, converge |
| `volc-investigator` | não | sonnet | high | sim | grafo primeiro, evidência com caminho e linha |
| `volc-architect` | não | opus | high | sim | fatia vertical, contratos, ownership |
| `volc-adversarial-reviewer` | não | opus | **xhigh** | sim | tenta refutar a entrega |
| `volc-gatekeeper` | não | sonnet | high | sim | roda gates, separa falha nova de herdada |
| `volc-curator` | não | sonnet | high | sim | propõe delta de Work Road e grafo |

**Um único escritor.** Os cinco read-only não têm `Edit`, `Write` nem
`NotebookEdit` — a restrição está na chave `tools` de cada arquivo, que
**substitui** o conjunto padrão. Nenhum deles tem `Agent`, então não delegam para
alguém que escreva.

## O que foi medido nesta versão, e diverge do esperado

**1 · O registro de agentes é lido na abertura da sessão.**
Criar um arquivo em `.claude/agents/` **não** o torna disponível na sessão que
está rodando: o `Agent` tool continua respondendo `Agent type not found`. Prova:
os seis foram criados, validados contra o schema, e só apareceram num processo
novo (`claude -p`). **Consequência prática:** depois de editar um agente, use uma
sessão nova, ou `claude -p --agent <nome>` como subprocesso.

**2 · `effort: xhigh` funciona, embora o schema não o documente.**
O texto do próprio schema descreve `effort` como "`low`, `medium`, `high`, `max`,
ou um inteiro" — e `xhigh` não está na lista. Mas o runtime o reconhece, e o
`Agent` tool o aceita como valor válido. Está em uso no revisor adversarial.

**3 · `disallowedTools` é ignorado quando `tools` está presente.**
Por isso a restrição dos read-only é feita por **allowlist** e não por denylist:
uma denylist que o parser descarta seria uma proteção que não existe.

**4 · `nohup claude -p ... &` não captura a resposta do modelo.**
O arquivo de saída fica só com os avisos de permissão, e o processo sai 0. Rode
síncrono, ou use o `Agent` tool numa sessão que já enxergue os agentes.

## Campos aceitos no frontmatter (schema estrito da 2.1.247)

`name`\* · `description`\* · `model` · `tools` · `disallowedTools` · `color` ·
`effort` · `permissionMode` · `mcpServers` · `hooks` · `maxTurns` · `skills` ·
`initialPrompt` · `memory` · `background` · `isolation` · `observer` ·
`observerMessage` · `observeSubagents`.  (\* obrigatórios.)

`permissionMode` aceita `default`, `acceptEdits`, `auto`, `dontAsk`, `plan` e
`bypassPermissions`. **Todos os seis usam `default`, e `bypassPermissions` é
proibido neste projeto** — pedido de permissão tem de chegar ao operador.

## O ciclo

```
A selecionar  →  B investigar (investigator ‖ architect)  →  C sintetizar
     →  D implementar (só o coordenador)  →  E verificar (reviewer ‖ gatekeeper)
     →  F corrigir (teto de 3 ciclos)  →  G aceitar  →  H curadoria
```

Detalhe em `volc-coordinator.md`. As regras duras — ausência não é zero, erro de
prova não é prova, todo número carrega frescor — estão em cada arquivo, perto de
quem precisa obedecê-las.
