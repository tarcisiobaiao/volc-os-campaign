# Smoke seguro do 1Password local (P03-T09)

Prova, num processo descartável, que a cadeia **CLI → app → sessão → injeção**
do 1Password funciona nesta máquina — **sem nunca revelar, medir ou derivar o
valor do segredo**. Quando não consegue provar, ele diz exatamente onde parou,
com estado tipado e exit code próprio. Nunca emite sucesso por omissão.

## Estado REAL desta máquina — medido em 01/09/2026

Nada de 1Password está instalado aqui. Os fatos, como saíram do shell:

| Comando | Saída |
|---|---|
| `which op` | `op not found` (exit 1) |
| `ls -d /Applications/1Password.app` | `No such file or directory` (exit 1) |
| `which 1password-mcp` | `1password-mcp not found` (exit 1) |
| `env \| grep -c '^OP_'` | `0` |
| `which timeout` | `timeout not found` |
| `which gtimeout` | `gtimeout not found` |

Também não há servidor MCP do 1Password configurado em `~/.claude.json` nem em
`~/.claude/settings.json`.

Consequências diretas no código:

- o smoke real **tem** que sair `blocked/cli_ausente` (exit 10) hoje, e sai;
- **nenhum** limite de tempo usa o binário `timeout` (que não existe neste
  shell): todo limite é `subprocess.run(timeout=...)` do Python;
- toda a lógica é provada por um **duplê controlado**, porque sem 1Password
  instalado não existe outra forma honesta de provar nada.

## Uso

```bash
python3 tools/onepassword-smoke/run.py                 # smoke real (hoje: blocked/cli_ausente)
python3 tools/onepassword-smoke/run.py --json          # só o recibo JSON
python3 tools/onepassword-smoke/run.py --autoteste     # as 6 provas com o duplê; sai 0 ou 1

# com um ambiente real, depois de instalar e aprovar:
python3 tools/onepassword-smoke/run.py --referencia 'op://<vault>/<item>/<campo>'
```

Flags: `--referencia` (`op://<vault>/<item>/[secao/]<campo>`), `--nome-var`
(padrão `VOLC_SMOKE_SEGREDO`), `--caminho-app` (padrão `/Applications/1Password.app`
no macOS), `--permitir-service-account`, `--duple <dir>`.

## Estados de saída

| Estado | Exit | Significado |
|---|---|---|
| `ok` | 0 | ambiente encontrado, nomes listados, variável injetada, presença confirmada, sem eco |
| `blocked/cli_ausente` | 10 | `op` não está no PATH |
| `blocked/app_ausente` | 11 | CLI existe, app não |
| `blocked/sem_sessao` | 12 | `LostConnectionToApp`, `connectionreset` ou `No accounts configured` |
| `blocked/aprovacao_negada` | 13 | a aprovação por Environment não foi concedida |
| `blocked/referencia_ausente` | 14 | não há `--referencia`, ou o cofre dela não apareceu em `op vault list` |
| `falha/vazamento` | 20 | houve eco do valor, ou saída fora da lista-branca |
| `falha/injecao_nao_ocorreu` | 21 | `op run` saiu 0, mas o filho não viu segredo algum |
| `falha/preflight` | 30 | `--no-masking`, ou service account sem consentimento explícito |
| `falha/interna` | 40 | erro não classificado; nunca vira `ok` |

Os estados 14, 21, 30 e 40 são **acréscimos** aos cinco pedidos na tarefa. Cada
um existe porque a alternativa seria mentir: sem referência não há ambiente a
testar (14); `op run` que retorna 0 sem injetar nada não é sucesso (21); uma
recusa de preflight não é bloqueio de ambiente (30); e um erro que não sabemos
classificar não pode ser promovido a nenhum diagnóstico específico (40).

## O que o smoke PROVA

1. **Preflight recusa `--no-masking`.** A documentação diz que segredos impressos
   em stdout/stderr são ocultados por padrão e que `--no-masking` é a única forma
   de desligar isso. Aqui a flag é proibida, em qualquer posição da linha de
   comando — inclusive as que o `argparse` não reconhece (por isso o parsing usa
   `parse_known_args`: a recusa tem de ser nossa, com estado próprio, e não um
   "unrecognized arguments").
2. **Preflight recusa `OP_SERVICE_ACCOUNT_TOKEN`** sem `--permitir-service-account`.
   Service account é outro modelo de confiança (sem app, sem aprovação por
   Environment) e não é o que P03-T09 pede.
3. **Lista só nomes**, de `op vault list` e `op item list`, e sanitiza antes de
   imprimir: IDs de 26 caracteres, e-mails e caracteres de controle saem.
4. **A injeção aconteceu de verdade.** `op run -- <filho>` roda um processo
   descartável que imprime **uma única linha**: `VARIAVEL_PRESENTE=true|false`.
   Se a variável chegar ainda na forma `op://…`, o filho responde `false` — logo
   `ok` é impossível quando `op run` não resolveu nada.
5. **Não houve eco do valor**, por duas camadas independentes (abaixo).
6. **O recibo JSON é sanitizado**: sem valor, sem localizador utilizável. Da
   referência sobra só a *forma* (quantidade de segmentos, se tem seção, se tem
   query param) — nunca os segmentos.

### Por que nem comprimento nem hash podem sair

O filho confirma **apenas presença booleana**. Não imprime comprimento nem hash:

- **comprimento vaza entropia.** Saber que a senha tem 12 caracteres corta o
  espaço de busca em ordens de grandeza; é informação que só ajuda o atacante.
- **hash permite confirmar um palpite.** Quem suspeita do valor testa o palpite
  offline, sem limite de tentativas e sem deixar rastro. Um hash publicado num
  recibo transforma "eu acho que é X" em "eu tenho certeza que é X".

Por isso o único fato que atravessa a fronteira do processo é um booleano.

### As duas camadas da varredura de eco

O processo pai **não conhece o valor** — esse é o ponto. Procurar por ele
exigiria possuí-lo, e possuí-lo já seria o vazamento que queremos impedir. Então:

- **Camada 1 — lista-branca estrita.** A saída do filho tem de ser exatamente a
  linha canônica, e stderr tem de estar vazio. Qualquer byte fora disso conta
  como eco suspeito. É conservador de propósito: preferimos um falso
  `falha/vazamento` a um falso `ok`. Um aviso benigno do `op` derruba o smoke —
  e essa é a troca desejada.
- **Camada 2 — varredura por valor, feita de dentro.** Um segundo filho roda
  **também sob `op run`**, onde o valor existe legitimamente, lê o arquivo com
  tudo o que foi capturado e devolve um único booleano: `ECO_DETECTADO=true|false`.
  Assim a pergunta "o valor apareceu na saída?" é respondida sem que o pai jamais
  toque no valor. Valor com menos de 8 caracteres devolve `indeterminado` (casaria
  por acaso em qualquer log) e o resultado **não** é `ok`.

O arquivo capturado pode conter o eco de um segredo real: ele vive num diretório
`0700` criado por `mkdtemp` e é destruído num `finally`, aconteça o que acontecer.

## O que o smoke NÃO prova

- **Nada sobre o valor**: se é o segredo certo, se está atualizado, se o campo é
  o esperado. O smoke prova *que chegou algo*, não *o que chegou*. Isso é
  deliberado, não uma lacuna a fechar.
- **Comprimento ou hash do segredo** — proibidos, pelas razões acima.
- **Durabilidade da aprovação.** A documentação diz que a aprovação por
  Environment vale "until 1Password locks"; um `ok` de agora não garante um `ok`
  depois que o app travar.
- **A string exata de uma aprovação negada.** A documentação não a publica. A
  detecção de `blocked/aprovacao_negada` é heurística **declarada** (`not
  authorized`, `unauthorized`, `authorization`, `approval`, `approve`, `denied`,
  `declined`); se nada casar, o estado cai em `falha/interna`, nunca em `ok`.
- **Presença do app fora do macOS.** Não há caminho canônico documentado; o smoke
  diz "não verificado" e exige `--caminho-app` em vez de inventar um.
- **O caminho MCP (`1password-mcp`, stdio).** O binário não existe nesta máquina;
  o smoke exercita o caminho CLI (`op run`), não o servidor MCP.
- **Versão mínima do `op` ou tier de plano.** A documentação consultada não os
  declara, e este README não vai inventá-los.

## Para sair de `blocked`

1. Instalar o **app de desktop do 1Password** e o **CLI `op`**. O CLI sozinho não
   basta: neste modelo é o app que guarda a sessão.
2. No app, ligar **Settings → Developer → "Integrate with 1Password CLI"**.
3. Destravar o app e confirmar que `op account list` responde — sem
   `LostConnectionToApp`, `connectionreset` ou `No accounts configured`.
4. Criar o **Environment** e conceder a aprovação (ela vale até o 1Password
   travar; depois disso, aprovar de novo).
5. Rodar com a referência do campo:
   `python3 tools/onepassword-smoke/run.py --referencia 'op://<vault>/<item>/<campo>'`.

## O duplê controlado

`duple_op.py` imita **só** o que a documentação declara: `op --version`,
`op account list`, `op vault list`, `op item list`, `op run -- <cmd>` (com
resolução de `op://` e mascaramento de ecos). Ele é copiado como `op` para um
diretório temporário e **só entra no PATH quando o smoke recebe `--duple <dir>`**.

Isso é regra, não detalhe: um smoke que escolhe sozinho um `op` falso é um smoke
que mente. Verificado — com `VOLC_DUPLE_MODO`/`VOLC_DUPLE_VALOR` no ambiente mas
**sem** `--duple`, o smoke ignora o duplê e sai `blocked/cli_ausente` com
`duple_em_uso: false`. E todo recibo carrega `duple_em_uso` e `duple_caminho`,
para que nenhuma execução de duplê possa ser confundida com uma execução real.

O duplê **recusa** rodar sem `VOLC_DUPLE_MODO` e sem `VOLC_DUPLE_VALOR` (exit 3):
ausência é ausência explícita, ele não inventa segredo nem adivinha modo. A versão
que ele reporta é `0.0.0-duple` — sintética de propósito, para não parecer real.

Modos: `feliz`, `vazamento` (mascaramento quebrado: ecoa o segredo em stderr),
`app_bloqueado` (`LostConnectionToApp`), `sem_contas` (`No accounts configured…`).

## As 6 provas do `--autoteste`

| Prova | O que exige |
|---|---|
| a | caminho feliz → `ok` (exit 0) **e** `presenca_confirmada: true` |
| b | duplê que ecoa → `falha/vazamento` (exit 20) **e** `varredura_por_valor: "true"` |
| c | `LostConnectionToApp` → `blocked/sem_sessao` (12) **e** classificação `documentado:lostconnectiontoapp` |
| d | `No accounts configured` → `blocked/sem_sessao` (12) **e** classificação `documentado:no accounts configured` |
| e | `--no-masking` → `falha/preflight` (30) |
| f | o valor de teste não aparece em recibo nenhum nem em log nenhum |

### As provas foram testadas contra mutantes

Um teste que passa não vale nada até alguém mostrar que ele sabe falhar. Cada
prova foi rodada contra uma versão sabotada do código:

| Mutante | Efeito |
|---|---|
| lista-branca desligada | b ainda **passa** (a camada 2 pega) — defesa em profundidade real |
| varredura por valor cega | b **falha** |
| **as duas camadas desligadas** | b **falha com `estado=ok, exit=0`** — sem elas, o smoke emitiria sucesso sobre um vazamento |
| preflight permissivo | e **falha** (`estado=ok`) |
| padrões documentados quebrados | c **falha** (`nao_classificado`) |
| stderr cru no recibo | f **falha** (`prova-b.stdout` contaminado) |
| duplê que não injeta | a **falha** com `falha/injecao_nao_ocorreu` (exit 21) — `ok` é inalcançável sem injeção real |

O mutante dos padrões documentados foi o que encontrou um defeito **na prova, não
no smoke**: c e d passavam mesmo com o reconhecimento quebrado, porque qualquer
`rc != 0` já cai em `blocked/sem_sessao`. As provas passaram a exigir a
classificação, e só então o mutante ficou vermelho.
