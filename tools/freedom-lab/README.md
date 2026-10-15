# Freedom Lab

Laboratório descartável onde agentes podem instalar bibliotecas, criar schema,
testar migrations, simular e consultar fontes em leitura, **sem autoridade para
mutar produção**. Não é outro harness: missões continuam em
`tools/agent-harness/`; este diretório dá o ambiente, os brokers e o contrato
de experimento que elas usam.

## 1. Ambiente Python (`.venv-lab/`, raiz do checkout)

uv roda de um venv de ferramenta (`tools/freedom-lab/.uv-tool/`, ignorado), sem
tocar no Python global:

```bash
python3.14 -m venv tools/freedom-lab/.uv-tool
tools/freedom-lab/.uv-tool/bin/pip install uv==0.12.24
cd tools/freedom-lab
UV_PROJECT_ENVIRONMENT=../../.venv-lab .uv-tool/bin/uv sync --frozen   # recria do lock
.uv-tool/bin/uv lock --locked                                          # gate: lock = pyproject
```

- Lock multiplataforma com hash em `uv.lock`; janela de frescor
  `exclude-newer = 2026-10-08` (nada com menos de 7 dias).
- Agente pode `uv add X` livremente **no lab**; toda dependência entra em
  `DEPENDENCIAS.json` (versão, fonte, licença, justificativa, risco, smoke,
  decisão). `tests/test_dependencias.py` falha se lock e manifesto divergirem.
- `google-ads` fica fora (OR-Tools prende protobuf <6.34). Dado do Google entra
  por snapshot do broker, rodado com `backend/.venv`.

## 2. Banco descartável (`lab.sh`)

```bash
tools/freedom-lab/lab.sh recriar     # destruir → criar → semear → testar → destruir
MANTER=1 tools/freedom-lab/lab.sh recriar   # mantém o container para depurar
tools/freedom-lab/lab.sh criar | semear | migrar | testar | destruir | status
```

- Também é biblioteca: `. tools/freedom-lab/lab.sh` com `LAB_NOME`/`RECIBOS`
  próprios dá `criar`/`destruir`/`P`/`sqlstate`/`ok`/`nao`/`eq` sem rodar
  comando. As provas do ledger de migrations (v20_01/v20_02) sobem o banco
  assim: `scripts/provar-ledger-migracoes.sh` e
  `scripts/provar-migracao-par.sh --migration A.sql --rollback B.sql`.
- Imagem `supabase/postgres:15.8.1.085`, container `volc-freedom-lab-db` com
  rótulo `volc.freedom-lab=1`, **sem porta publicada** (só `docker exec`).
- `semear` aplica só fixtures sintéticas, depois de um gate anti-PII/segredo.
- `testar` prova a candidata (`MIGRATION=`/`ROLLBACK=`, padrão v18_01): matriz
  anon/authenticated/identidade de leitura/service_role, sonda de acesso,
  fingerprint de schema, guarda contra reaplicação, rollback que devolve o
  fingerprint exato do estado anterior, rollback idempotente, reaplicação.
  Recibo de cada rodada em `runs/<data>/` (ignorado pelo Git). Os recibos que
  sustentam o fechamento de 15/10 foram copiados à mão para `recibos/20261015/`
  (gerados por `lab.sh recriar` e `volc_lab.provar_brokers`; não editar).
- O pg_hba da imagem confia em 127.0.0.1: a prova por login confirma identidade e
  configuração do papel, não a senha. A senha de produção é definida fora do repo.
- Ledger `volc_lab.migracao_aplicada` vive só no container. Em produção o
  ledger continua sendo `supabase/migrations/README.md`.
- ⚠️ Não use `supabase db reset` em `supabase/migrations/`: o CLI pularia a
  série v8–v17 e aplicaria os rollbacks timestampados para frente.
- Base "do zero" = imagem + semente. Base "estado de produção" = `lab.sh base-prod`
  com `LAB_DUMP` (dump `--schema-only` de produção, fora do repo, sem COPY/INSERT) e
  `LAB_DUMP_SHA256`; o dump passa por `db/verificar_dump_schema.py` (recusa COPY/\copy, INSERT, DO, setval, large object e TOC de dado no nível de comando, aceitando INSERT dentro de corpo de função) e os blocos ficam em `mktemp` fora do repo, apagados no fim. Tira o default ACL da imagem, cria os pré-requisitos
  (`db/base_prod_prereqs.sql`) e restaura como `supabase_admin` em blocos
  (`db/restaurar_em_blocos.py`). Com o dump de 15/10, 8 de 11 categorias do
  fingerprint batem com produção por md5; constraints, policies e grants batem em
  contagem (o md5 difere por deparse/grantor; recibo em `recibos/20261015/fingerprint-producao-vs-base.json`). `recriar-prod` faz o ciclo inteiro.
- `criar` só devolve depois do init da imagem (auth.uid criado, postgres rebaixado).
- `PA` executa como `supabase_admin` (migrations de users e default ACL).
- `MIGRATION_SUITE=<arquivo>` troca a suíte do `testar` (padrão
  `db/suites/v18_01.sh`). Só suíte de `db/suites/` commitada e sem alteração local
  dá ao recibo `producao_acessada: false`; outra exige `LAB_SUITE_LIVRE=1` e o recibo
  diz `nao_garantido`. `LAB_SEMENTE` passa pelo mesmo gate anti-PII da semente
  sintética e tem o hash registrado; `estado <papel> <sql> [claims]` exercita policy por JWT.
- `db/sonda_search_path.sql`: leitura do search_path do papel postgres, pré-requisito
  da v20_02 em produção (não executada; exige autorização de leitura).
- Não criar outro laboratório Postgres em `scripts/`: suítes novas entram em
  `db/suites/` e usam este ciclo de vida.

## 3. Brokers de capacidade (`src/volc_lab/brokers/`)

| Broker | Capacidade | Como prende |
|---|---|---|
| `google_ads` | GAQL SELECT e `validate_only` | recusa rodar com a trava aberta; não chama `mutar`/`destravar`/`mutate`/`get_service` (AST); recibo com customer mascarado, sha256 do payload (impressão de `/provar`), request_ids. O `google-ads.yaml` tem escopo cheio: a barreira é o caminho de código + a trava de dois fatores |
| `gtm` | LEITURA | capacidades sem hierarquia; `TETO_DO_LAB = {LEITURA}`; só GET; a sessão recebe só o access token reduzido a `tagmanager.readonly` (sem refresh_token) |
| `ga4` | leitura Admin + `runReport` agregado sem dimensão | token reduzido a `analytics.readonly`; ausência de linha → `None`, não zero |
| `valor_operacional` | — | CPC de SERP/Keyword Planner/DataForSEO nunca autoriza verba; recomendação shadow não admite `executada=True` |
| Supabase | — | identidade mínima `volc_leitura_agente` só como migration candidata (`supabase/migrations/v18_01_*.PROPOSTA.sql`); workers nunca recebem service_role |

⚠️ Os brokers são bibliotecas no processo do agente, não fronteira de processo:
código hostil no mesmo processo pode ler `~/.config/volc/google-oauth.json` por
conta própria. Isolar em processo/usuário separado é o próximo passo.

Prova ao vivo (leitura): `PYTHONPATH=tools/freedom-lab/src:. backend/.venv/bin/python -m volc_lab.provar_brokers <dir> gtm ga4`.

## 4. Contrato de experimentos

`contracts/experimento.schema.json` + `python -m volc_lab.experimentos <experimento.json>`.
Além da forma: `adopt` só com número (métrica primária observada vence o
baseline por `min_effect` e foi reproduzida), observado ≠ estimado, ausência ≠
zero, `external_writes = 0`, replay coerente com chamadas externas, artefatos
confinados ao diretório do experimento e conferidos por SHA, limpeza feita.
`adopt` adota a conclusão; nunca executa ação externa.

## 5. Gates

```bash
.venv-lab/bin/python -m pytest -q tools/freedom-lab/tests
tools/freedom-lab/lab.sh recriar
```
