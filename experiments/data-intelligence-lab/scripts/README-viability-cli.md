# viability_cli.py — CLI local do kernel de viabilidade

Offline/shadow. Nenhuma chamada de rede, banco, Google, n8n ou modelo de linguagem. O único
subprocesso é `git rev-parse HEAD` na raiz do repositório, para registrar o commit de origem.

```bash
# da raiz do lab (experiments/data-intelligence-lab), com o Python do lab
.venv/bin/python -I scripts/viability_cli.py evaluate   entrada.json --saida DIR
.venv/bin/python -I scripts/viability_cli.py frontier   entrada.json --saida DIR
.venv/bin/python -I scripts/viability_cli.py simulation entrada.json --saida DIR [--normalizar]
.venv/bin/python -I scripts/viability_cli.py replay     fixtures/viability --saida DIR
.venv/bin/python -I scripts/viability_cli.py verify     DIR/recibo.json
```

Exit codes: `0` conclusivo · `2` entrada inválida · `3` insuficiente/indisponível · `4` invariante
violada ou recibo não verificado.

## Entrada

`entrada.json` é `{"entrada": {...}}` (ou o objeto direto) no contrato v2 (`volc_dil.viability.contrato`):

- `perda_maxima` só entra como `{valor, horizonte_dias, autorizacao}`; `autorizacao` carrega
  `authorization_id`, `version`, `issuer` com identidade (`"owner:tarcisio@…"`, nunca `"owner"`),
  `effective_at`, `expires_at`, `disponivel_em` e `hash` (sha256 do JSON canônico). Um valor sem
  autorização, uma autorização expirada no `as_of` ou um `hash` errado são entrada inválida (`2`).
- `cambio`, `revshare` e `imposto` são versionados: `effective_at`, `disponivel_em`, `versao`, `hash`.
  Nada pode ser `disponivel_em`/`effective_at` depois do `as_of` (lookahead).
- `freshness` (dict) não existe mais; use `freshness_sla_dias` (int, padrão 7).

As fixtures em `fixtures/viability/` são geradas por `scripts/viability_gerar_fixtures.py`
(nunca editadas à mão); o `MANIFEST.json` guarda o sha256 de cada uma.

## Saídas de `evaluate`

| arquivo | conteúdo |
|---|---|
| `resultado.json` | resultado canônico do kernel (`ResultadoViabilidade.para_json()`) |
| `relatorio.md` | relatório humano curto |
| `recibo.json` | recibo verificável (abaixo) |

## Recibo

Campos do recibo de `evaluate` (`tipo: "evaluate"`):

| campo | o que é |
|---|---|
| `kernel_version` | `VERSAO_KERNEL` |
| `codigo_sha256` | sha256 dos módulos `volc_dil/viability/*.py` **e** deste CLI (nome + bytes, em ordem) |
| `source_commit` | `git rev-parse HEAD` da raiz do repositório, ou `"indisponivel"` se o git falhar |
| `ambiente` | `{python: sys.version, plataforma: platform.platform(), uv_lock_sha256: sha256(experiments/data-intelligence-lab/uv.lock)}` |
| `entrada` | a entrada completa (`para_json`) |
| `input_hash` | `hash_entrada(entrada)` |
| `result_hash` | hash do resultado calculado pelo kernel |
| `resultado_arquivo` / `resultado_sha256` | nome e sha256 do `resultado.json` ao lado do recibo |
| `relatorio_arquivo` / `relatorio_sha256` | nome e sha256 do `relatorio.md` ao lado do recibo |
| `external_actions` | sempre `0` |

O recibo de `replay` (`tipo: "replay"`, também gravado como `recibo.json` em `--saida`) troca
`entrada`/`input_hash`/`result_hash` por `replay_hash`, `fixtures_dir` (caminho absoluto) e
`fixtures_sha256` (sha256 de cada fixture); `resultado_arquivo` é `replay.json` e
`relatorio_arquivo` é `replay.md`.

## `verify`

`verify DIR/recibo.json` devolve `4` (e lista todas as falhas em stderr) quando qualquer uma vale:

- `resultado.json` ou `relatorio.md` (os nomes do recibo) não está ao lado do recibo;
- `resultado_sha256` ou `relatorio_sha256` não bate com o arquivo;
- `codigo_sha256` difere do código atual;
- `ambiente.uv_lock_sha256` difere do `uv.lock` atual;
- `external_actions != 0`;
- (evaluate) `input_hash` não bate com a `entrada` do recibo, ou `result_hash` não reproduz ao
  reavaliar a entrada com o código atual, ou uma invariante falha;
- (replay) `fixtures_dir` não existe, `fixtures_sha256` difere das fixtures atuais, ou `replay_hash`
  não reproduz ao rodar o replay de novo.

`python` e `plataforma` em `ambiente` são registrados, não comparados: um recibo reproduzido em outro
Python/SO com o mesmo `uv.lock` e o mesmo código ainda verifica (e isso é informação, não falha).

## O que o sha256 prova — e o que não prova

O recibo prova **integridade** (os arquivos ao lado são os que o CLI escreveu; o código e o lockfile
são os mesmos) e **reprodutibilidade** (a mesma entrada, com o mesmo código, dá o mesmo resultado).

Ele **não prova identidade nem autoria**: qualquer pessoa com o código consegue gerar um recibo
válido para qualquer entrada, inclusive com `issuer: "owner:…"` na autorização da tolerância. O
`hash` da `Autorizacao` prova que o conteúdo da autorização não foi alterado depois de calculado, não
que o owner a emitiu. Provar autoria exige uma assinatura (chave privada do emissor, verificável por
chave pública), que o laboratório não tem. Enquanto não houver, a cadeia de confiança de uma
tolerância de perda é organizacional (quem registrou o `authorization_id` no lado VOLC), não
criptográfica.
