# Supervisor contínuo do harness

O `volc-agent-run` continua sendo o executor de uma missão. O
`volc-agent-supervise` acrescenta seleção explícita, claim transacional,
idempotência, ownership e recibos — sem transformar o Roadmap em uma fila de
comandos implícitos.

## Fronteira de segurança

- Só tarefas `todo` ou `partial`, com `acceptance` e manifesto JSON explícito.
- `task_ids` da missão precisam existir no Roadmap Vivo.
- Dependência só existe quando declarada; posição editorial não bloqueia.
- A missão precisa apontar para o SHA completo que ainda é o `HEAD` local.
- Claims sobre caminhos iguais ou ancestrais/descendentes se excluem.
- O ledger fica em `tools/agent-harness/runs/supervisor.sqlite`, já ignorado.
- O estado terminal máximo é `ready_for_human`.
- Não há merge, push, deploy, migration, curadoria ou mutação externa.

## Fila explícita

```json
{
  "supervisor_id": "volc-sabado",
  "poll_seconds": 30,
  "max_writer_concurrency": 1,
  "jobs": [
    {
      "job_id": "p01-t09-ratchet",
      "task_id": "P01-T09",
      "mission_path": "/private/tmp/p01-t09-ratchet.json",
      "priority": 1,
      "dependencies": ["P01-T07"],
      "risk_class": "local_code_only",
      "max_attempts": 3
    }
  ]
}
```

O manifesto da missão continua usando o contrato `MissionSpec` e precisa
declarar `task_ids`. Um arquivo absoluto só é aceito dentro de `/private/tmp`.

## Uso

Uma passada:

```bash
.venv-adk/bin/volc-agent-supervise --repo . --queue /private/tmp/fila.json
```

Observação contínua (planejada, ainda desarmada na V0):

```bash
.venv-adk/bin/volc-agent-supervise \
  --repo . \
  --queue /private/tmp/fila.json \
  --watch
```

O modo contínuo não inventa trabalho quando a fila fica vazia: publica os
motivos de inelegibilidade em `runs/supervisor-state.json` e aguarda.

Na V0, passar `--watch` termina com erro deliberado. Cancelamento do grupo de
processos, perda de lease em voo e retomada pós-crash ainda precisam de
contraprovas antes de um processo poder permanecer ativo sem operador.

## Estados V0

```text
claimed -> running -> ready_for_human
                   -> changes_requested
                   -> blocked
                   -> failed
                   -> interrupted
```

`ok: true` significa somente que os workers responderam. A aceitação depende
de `candidate_status == ready_for_human`.

## Ratchet corretivo

O Ratchet só liga quando o manifesto declara `ratchet.enabled=true` **e** o
job autoriza mais de uma tentativa. Ele permanece limitado pelo menor teto
entre tentativas de escrita, rodadas de revisão e `job.max_attempts`.

Cada correção nasce do commit candidato anterior (ou da mesma base quando o
gate falhou antes do commit), recebe apenas achados/erros persistidos e volta a
executar todos os gates e revisores. A raiz original da linhagem é persistida
e precisa continuar ancestral do HEAD controlador exato; um avanço paralelo
da `main` não autoriza trocar essa raiz.

O loop bloqueia, sem nova chamada de modelo, quando:

1. alcança três tentativas, três revisões ou o teto menor do job;
2. esgota o orçamento total de parede;
3. repete árvore, inclusive oscilação A-B-A;
4. repete o mesmo conjunto de findings;
5. perde/corrompe o recibo que justificaria a correção;
6. recebe candidato que não é commit Git descendente da linhagem.

O lease é renovado enquanto a missão roda. Lease vencido não libera ownership
se o processo proprietário ainda está vivo.

## Próxima catraca

Ainda faltam cancelamento por grupo de processos e cleanup/quarentena explícita
de worktrees ambíguas. Até isso existir, o supervisor preserva os artefatos e
para; nunca tenta “limpar” automaticamente uma árvore sobre a qual não tem
prova de propriedade e terminalidade.

## Roteamento de modelos

O contrato versionado está em `MODEL_ROUTING.json`. O caminho econômico
padrão é Codex `gpt-5.6-sol/high` para escrita e Codex `gpt-5.5/xhigh` para
refutação profunda. Opus entra na revisão de contratos críticos; Fable fica
reservado ao planejamento excepcional; Gemini 3.7 Flash executa fatias
repetíveis com ferramentas locais allowlisted; DeepSeek é somente sniper de
microreparo com aplicação determinística fail-closed.

Esse arquivo orienta a composição do manifesto, mas não escolhe modelos em
silêncio. Cada worker continua declarando provider, model e effort no JSON da
missão, e o `MissionSpec` rejeita modelo ou effort incompatível.

### O que está efetivamente habilitado na V0

- Escrita: Codex `gpt-5.6-sol/high`.
- Revisão independente: Codex `gpt-5.5/xhigh`.
- Uma missão por invocação, um writer, uma tentativa; sem Ratchet automático.
- Claude permanece fora até a leitura de configuração pessoal e o escopo
  físico terem isolamento provado.
- Gemini tem ferramentas com allowlist física e proteção contra symlink, mas
  permanece fora até um smoke real read-only passar sem ampliar escopo.
- DeepSeek continua como sniper separado de substituição mínima; não é um
  provider genérico do supervisor.

`allowed_paths` limita o contrato e a revisão de diff. Para os CLIs Codex e
Claude ele não é uma sandbox de leitura: o processo enxerga os arquivos
rastreados da worktree. Por isso a V0 usa worktree limpa, ambiente sanitizado,
`writable_paths` estreito e não promete confidencialidade entre arquivos
rastreados. O isolamento de leitura real exige projeção física separada.
