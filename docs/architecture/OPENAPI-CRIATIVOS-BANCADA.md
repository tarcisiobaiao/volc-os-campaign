# Golden OpenAPI — `/api/criativos/bancada`

**Escopo:** as oito operacoes HTTP da bancada criativa, e nada alem delas.
**Fonte:** `app.main:app.openapi()`.
**Arquivo versionado:** `backend/tests/goldens/openapi-criativos-bancada.json`.
**Gerador:** `scripts/gerar_openapi_golden.py`.
**Provas:** `backend/tests/test_openapi_golden.py`.

## Por que este arquivo existe

O contrato ja estava congelado antes desta rodada — mas **embutido**, em
zlib+base64, dentro do teste que o confere
(`backend/tests/test_criativo_rotas_equivalentes.py`, constante
`_OPENAPI_ANTES_ZLIB_B64`). O comentario de la registra a razao honestamente:

> Ele fica embutido porque esta rodada nao possui ownership para criar outro
> arquivo.

O congelamento era real. A **auditabilidade** nao era: nao havia comando para
regerar, nao havia arquivo para ler em code review, e qualquer mudanca de
contrato aparecia como uma unica linha base64 diferente. Um golden que so existe
dentro do teste que o verifica nao e reproduzivel por terceiro — e "reproduzivel
em checkout limpo" e exatamente o aceite 4 do P17-T09.

## O que foi preservado

O fragmento canonico `{"paths", "components"}` do arquivo versionado tem o
**mesmo `sha256`** do golden embutido do commit-base `9885459`:

```
28bb086dcf5ca5f4667b9c0c4aecb1778783c66c288bc060f5cb674981b020e8
```

`test_o_arquivo_extraido_tem_o_MESMO_sha256_do_golden_ja_provado` confere essa
igualdade. Sem ela, "movemos o golden para um arquivo" seria afirmacao de
intencao, e a extracao poderia ter alterado o contrato sem ninguem ver.

Sao **7 paths** (8 operacoes: `/trabalhos` tem `GET` e `POST`) e **4 schemas**
(`HTTPValidationError`, `PedidoDeCancelamento`, `PedidoDeProducao`,
`ValidationError`).

## Comandos

```bash
# conferir o golden versionado contra a aplicacao atual (sai 1 se divergir)
python3 scripts/gerar_openapi_golden.py --check

# regenerar depois de uma mudanca INTENCIONAL de contrato
python3 scripts/gerar_openapi_golden.py --write

# so imprimir o documento, sem tocar em arquivo
python3 scripts/gerar_openapi_golden.py --stdout
```

`--golden CAMINHO` troca o arquivo alvo dos dois primeiros; e o que as provas
usam para conferir um golden adulterado sem escrever por cima do versionado.

## Como a reprodutibilidade e garantida

1. **Sem `.env`.** Antes de importar a aplicacao, o gerador apaga do processo as
   variaveis com prefixo VOLC (`SUPABASE_`, `GOOGLE_`, `CRIATIVO_`, …) e desliga
   `env_file` em `Settings`. Sem isso o resultado dependeria da maquina.
2. **E devolve o ambiente que encontrou.** A restauracao acontece em `finally`.
   ⚠️ A primeira versao deste gerador nao restaurava: rodando dentro do pytest,
   `Settings.model_config["env_file"]` ficava `None` para o resto da sessao e
   `backend/tests/test_config_env_server.py` — um modulo que ninguem tocou —
   passava a estourar. `test_o_gerador_devolve_o_ambiente_que_encontrou` e a
   contraprova.
3. **Sem cache.** `app.openapi_schema` e zerado antes e depois de gerar. FastAPI
   memoriza o schema na primeira chamada; um processo que ja tivesse servido
   `/openapi.json` devolveria o documento de antes da mudanca.
4. **Sem ruido local.** `_conferir_limpeza` levanta erro se o documento contiver
   caminho do repositorio, `HOME`, hostname, `.env`, `generated_at` ou
   `hostname`. O gerador falha em vez de gravar um golden que so confere na
   maquina de quem o gerou.
5. **Determinismo medido em processo separado.**
   `test_o_gerador_e_deterministico_em_processo_limpo` roda o script **duas
   vezes em subprocesso**, com `HOME` e `CWD` apontando para diretorio
   temporario, e exige stdout byte-identico nas duas — e igual ao arquivo
   versionado. Medir determinismo dentro do pytest mediria o cache.

## Fronteira declarada

O documento carrega `x-volc-scope: /api/criativos/bancada` e
`x-volc-source: app.main:app.openapi()`. Rotas fora desse prefixo **nao** estao
cobertas por este golden, e nenhuma prova daqui deve ser lida como cobertura do
backend inteiro.

## Quando o `--check` reprova

A saida nomeia o arquivo, o comando de regeneracao e os nos JSON divergentes
(caminho no estilo `$.paths./api/....get.parameters[0].name`), seguidos de um
unified diff. Se a divergencia for intencional, rode `--write` e versione o
arquivo junto com a mudanca de contrato — **no mesmo commit**, para que a
revisao veja as duas coisas.

Se a divergencia for a **toolchain**, e outra conversa:
`test_criativo_rotas_equivalentes.py::test_toolchain_do_golden_e_declarada_e_esta_na_faixa_provada`
fixa FastAPI `0.115.6` e Pydantic na faixa `[2.11.7, 2.14.0)`. Um golden gerado
fora dessa faixa nao e comparavel com este.
