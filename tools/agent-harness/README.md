# VOLC Agent Harness

Harness local de desenvolvimento. Ele usa o Google ADK como coordenador e os
CLIs já autenticados de Claude Code e Codex como trabalhadores. Não faz parte
do runtime do VOLC OS e não deve receber chaves de API do produto.

## Estado atual

- Google ADK fixado em `2.8.0`.
- Python isolado em `.venv-adk/`.
- Preflight read-only implementado.
- Contrato inicial de tarefa em `contracts/task.schema.json`.
- Runner paralelo read-only com Claude e Codex em worktrees exclusivas.
- Modo de implementação com exatamente um writer Codex em sandbox
  `workspace-write`, seguido de revisores read-only Claude/Codex.
- Modelo e effort ficam explícitos na missão e no relatório; não dependem mais
  dos defaults silenciosos das CLIs.
- O harness cria um commit candidato isolado. Merge, push, deploy, migration em
  produção e mutação externa continuam inexistentes no fluxo.

## Instalação reproduzível

Na raiz do repositório:

```bash
python3 -m venv .venv-adk
.venv-adk/bin/python -m pip install "setuptools>=77"
.venv-adk/bin/python -m pip install \
  -c https://raw.githubusercontent.com/google/adk-python/main/constraints-3.14.txt \
  -e tools/agent-harness
```

## Preflight

```bash
.venv-adk/bin/volc-agent-preflight --repo . --json
```

Teste local sem chamar modelo:

```bash
.venv-adk/bin/python -m unittest discover \
  -s tools/agent-harness/tests -p 'test_*.py'
```

O aviso de árvore suja é deliberado: `git worktree add` parte de um commit e
não copia mudanças não commitadas. Nenhum escritor deve iniciar sem um
`base_ref` explícito e sem ownership de caminhos.

## Primeira missão paralela

```bash
.venv-adk/bin/volc-agent-run \
  --repo . \
  --mission tools/agent-harness/missions/pilot-search-zero-readonly.json
```

O comando cria uma worktree por worker, executa Claude e Codex em paralelo,
espera os dois no `JoinNode` do ADK e grava o resultado em
`tools/agent-harness/runs/<run-id>/mission-result.json`. As worktrees são
preservadas para inspeção e nenhuma integração é feita automaticamente.

Durante a execução, cada worker emite um heartbeat no terminal no intervalo
definido por `heartbeat_seconds` na missão. O ping mostra processo vivo, tempo
total, tempo desde o último evento e volume de saída. Silêncio prolongado vira
`alive_without_output`, mas não encerra um modelo que ainda pode estar
raciocinando; somente `timeout_seconds` encerra a execução. Os mesmos pings
ficam em `workers/<worker-id>/heartbeat.jsonl` para auditoria posterior.

## Catálogo de gates (schema 3)

Uma missão **não escreve linha de comando**. Ela declara o tipo do gate:

```json
"gates": [
  {"kind": "pytest", "targets": ["backend/tests"]},
  {"kind": "git_diff_check"}
]
```

`argv` livre não existe mais no schema 3. Era por ali que `python -c`,
`node -e`, `sh -c`, `git reset` e `git checkout` entravam: quem escrevia o
comando era o autor da missão, e nenhuma allowlist de executável segura um
interpretador.

Três tipos selecionam conteúdo que o harness não escreveu — `npm_script`,
`tracked_script` e `build`. Eles **só existem por ID** do catálogo versionado
em `tools/agent-harness/gate-catalog.json`:

```json
"gates": [{"kind": "catalog", "gate_id": "verificar-segredos"}]
```

O compilador resolve o ID contra o arquivo rastreado pelo Git, calcula o digest
da definição e dos insumos materiais (corpo do script, `package.json`,
lockfiles) e **reconfere esse digest imediatamente antes de cada gate rodar**.
Mudou entre compilar e executar? `STALE_INPUT`, zero retry de writer, sem
colheita. A revalidação é por gate e não uma vez antes do laço, porque o gate
anterior roda código e código altera arquivo.

⚠️ Isto fecha política de **declaração** e a janela de troca de insumo. Não é
contenção de processo: um gate auditado roda com os privilégios do harness e
pode tocar o filesystem inteiro. `LocalRunner.contains_filesystem` continua
`False`, e é honesto.

## Invariantes

1. Uma frente de escrita = uma branch + uma worktree exclusiva.
2. Um único escritor por worktree.
3. Revisores rodam em modo read-only.
4. Claude roda com autenticação normal; nunca usar `--bare` nem bypass de
   permissões.
5. Codex roda com `--sandbox read-only` ou `workspace-write`; nunca usar
   `danger-full-access` nem bypass.
6. Nenhum worker edita Roadmap, curadoria ou grafo em paralelo.
7. O curador atualiza Roadmap e grafo uma única vez, depois da integração.
8. Merge permanece humano até termos provas suficientes do harness.
9. Todo writer emite `curation_handoff` tipado com tarefas, nós, estado, provas
   e lacunas; o resultado candidato permanece `pending_single_curator` até a
   reconciliação operacional após integração.

## Missão de implementação

Uma missão com `mode: implementation` exige:

- `base_ref` como SHA completo e ancestral da `main` local;
- um único worker `role: writer`, obrigatoriamente Codex;
- ao menos um reviewer read-only;
- ownership de caminhos e gates como `argv`, sem shell;
- modelos e effort explícitos (por exemplo, Codex `gpt-5.6-sol` em `xhigh`
  e Claude `opus` em `max`).

O writer não pode tocar `.env*`, configurações locais, migrations, Roadmap,
curadoria ou saídas do grafo. O harness confere o HEAD, recusa alterações fora
do ownership, executa secret scan e gates, cria um commit isolado e entrega o
SHA aos revisores. O resultado final é `ready_for_human`,
`changes_requested` ou `blocked`; nunca há merge automático.
