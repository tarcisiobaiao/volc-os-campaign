# Runbook de schema — perfil CREATE_ONLY

Tarefa T11 · checkpoint CP2 · pacote `docs/specs/traffic-operational-closure-v2/`.

Este runbook prepara uma janela curta. **Ele não é a autorização dela.** A
autorização de execução local que produziu este arquivo cobre um PostgreSQL
descartável e mais nada; o `apply` oficial exige um ato separado
(`EXPLICIT_OFFICIAL_SCHEMA_AND_CATALOG`).

O contrato exato — arquivos, ordem, hashes, dependências e o que nunca entra no
apply — está em [SCHEMA-DEPLOY-MANIFEST.json](SCHEMA-DEPLOY-MANIFEST.json). Este
documento é o procedimento; aquele é a fonte.

## O que este perfil é, e o que ele não é

`CREATE_ONLY` é a autoridade durável do nascimento Meta PAUSED: o recibo do
`validate_only`, a aprovação humana e os passos da saga. São três tabelas e onze
funções.

Ele **não** inclui o read model operacional de insights (`v15_02`) nem o ledger
PMax (`v12_03`). Nenhuma guarda do `CREATE_ONLY` cita esses arquivos, então
exigi-los antes do primeiro canário faria o nascimento esperar por um dashboard
— exatamente o que o `MASTER-SPEC.json` recusa em `releases.R0.note`.

## Antes de qualquer coisa

```bash
python3 scripts/verificar_autoridade_supabase.py
```

Saída esperada: `✓ Supabase oficial: https://database.agenciavolc.com.br`.
Qualquer outra coisa encerra a janela. O único Supabase operacional deste
projeto é o self-hosted; `*.supabase.co` nunca é fallback.

## ⚠️ Nunca aplique por glob

`supabase/migrations/` tem 50 arquivos. **20 deles são rollbacks** que dropam
tabelas e funções, e os dois restantes nem são SQL (`README.md`,
`PLANO-v11_03.md`). Um `for f in supabase/migrations/*.sql` executa apply e
rollback na mesma passada.

Além disso, todo arquivo abre com `\set ON_ERROR_STOP on` — meta-comando de
`psql`. Um driver que envie o arquivo como SQL puro ou falha na primeira linha
ou, pior, ignora o `ON_ERROR_STOP` e **continua depois de um erro**, deixando
metade do schema aplicado sem ninguém saber.

O executor é `psql`. A lista de arquivos é a do manifesto, explícita e ordenada.

## Ordem do apply

| # | Arquivo | Por que ele está aqui |
|---|---------|------------------------|
| 1 | `v13_01_cofre_de_ativos.sql` | A guarda de `v15_01` exige `public.cofre_ativo`. |
| 2 | `v15_01_meta_ads_read_model.sql` | A guarda do `CREATE_ONLY` exige `public.trafego_meta_ad_account`. |
| 3 | `20260904183418_meta_create_paused_executor.sql` | É o perfil. |

Pré-condições que as próprias guardas cobram, e abortam se faltarem:

- `current_user` é `postgres` ou `supabase_admin`;
- `server_version_num >= 150000`;
- os papéis `anon`, `authenticated` e `service_role` existem;
- nenhuma tabela do perfil já existe.

Nenhuma extensão adicional é necessária: `gen_random_uuid()` e
`hashtextextended()` são nativos do PostgreSQL 13+. Medido no ciclo local, que
aplicou sem instalar nada.

## Conferir os hashes antes de rodar

Divergência **aborta a janela**. O arquivo mudou depois de o manifesto ter sido
produzido, e o que seria aplicado não é o que foi conferido.

```bash
python3 - <<'PY'
import hashlib, json, pathlib
m = json.load(open('docs/closure/traffic-operational-closure-v2/SCHEMA-DEPLOY-MANIFEST.json'))
perfil = next(p for p in m['profiles'] if p['id'] == 'CREATE_ONLY')
falhou = False
for passo in perfil['apply_order']:
    real = hashlib.sha256(pathlib.Path(passo['file']).read_bytes()).hexdigest()
    ok = real == passo['sha256']
    falhou |= not ok
    print(('OK  ' if ok else 'DIVERGE '), passo['file'])
raise SystemExit(1 if falhou else 0)
PY
```

## Classificar o estado antes de decidir

Os três estados têm caminhos **diferentes**. Não os misture.

```sql
SELECT t AS objeto,
       CASE WHEN to_regclass('public.' || t) IS NULL THEN 'AUSENTE' ELSE 'PRESENTE' END AS estado
  FROM unnest(ARRAY[
    'cofre_ativo','trafego_meta_ad_account',
    'trafego_meta_validation_receipt','trafego_meta_create_approval','trafego_meta_create_step'
  ]) AS t;
```

- **NOT_APPLIED** — nenhuma tabela do perfil existe. Aplicar na ordem.
- **ALREADY_APPLIED** — todas existem. Não aplicar; a guarda aborta sozinha.
  Registrar o estado no recibo de CP2 e seguir.
- **PARTIALLY_APPLIED** — algumas existem. **Não rodar rollback para "limpar".**
  Inventariar objeto a objeto, decidir forward, aplicar só o delta.

Um rollback usado como faxina dropa tabelas que podem já conter recibos reais —
e esses recibos são a única prova de que um objeto pode existir numa conta.

## Backup e a única pergunta que decide o rollback

Tire ponto de recuperação/export do schema `public` antes da janela. O perfil só
cria objetos novos e não altera tabelas existentes, então o risco é colisão de
nome, não perda; o export é o que permite distinguir as duas coisas depois.

```sql
-- Diferente de 0 PROÍBE o rollback.
SELECT count(*) FILTER (WHERE external_object_id IS NOT NULL) AS objetos_reais
  FROM public.trafego_meta_create_step;
```

Rollback é permitido **apenas** quando o perfil acabou de ser aplicado, a janela
falhou e as tabelas estão provadamente vazias. Com qualquer linha de aprovação
ou qualquer `external_object_id` gravado, o conserto é para frente: fechar
`META_CREATE_PAUSED_ENABLED` e `META_CREATE_LEDGER_WRITE_ENABLED`, preservar as
linhas e corrigir por migration nova.

Apagar o ledger não apaga a campanha. Apaga só a prova dela.

## Aplicar schema não abre criação

As flags de runtime continuam fechadas depois da janela, e isso é o desenho:

| Flag | Depois do apply |
|------|-----------------|
| `META_CREATE_PAUSED_ENABLED` | fechada |
| `META_CREATE_LEDGER_WRITE_ENABLED` | fechada até autorização própria |
| `META_VALIDATE_ONLY_ENABLED` | irrelevante aqui; nunca reutilizar como licença de criar |

## O que o ciclo local provou — e o que ele não prova

Exercitado num PostgreSQL 17.9 descartável (`initdb` próprio, `127.0.0.1:55432`,
datadir no scratchpad da sessão, sem qualquer ligação com o oficial):

| Etapa | Resultado |
|-------|-----------|
| apply na ordem declarada | as três aplicaram |
| fronteira de autorização com os papéis **reais** | `anon` e `authenticated` recusados na função; `anon` sem `SELECT` na tabela; `service_role` **sem `INSERT` direto**; `service_role` passa o grant e para na regra (`META_APPROVAL_NOT_FOUND`) |
| uso | `record_validation` → `approve` → `prepare_step` = `DESPACHAR` |
| concorrência real, duas sessões `psql` simultâneas no mesmo passo | `worker1=DESPACHAR`, `worker2=AMBIGUO` — no máximo um despacho autorizado |
| repetição | reaplicar recusado: *"ja parece aplicado; rode o rollback correspondente"* |
| rollback (tabelas vazias) | aplicado; as 3 tabelas sumiram e o read model `v15_01` foi **preservado** |
| reapply | aplicada |

A fronteira foi medida com `SET ROLE`, não como superusuário: um teste que roda
tudo como `postgres` não prova autorização nenhuma, porque `postgres` passa por
cima de qualquer `GRANT`.

**Este ciclo não prova**, e o recibo não pode dizer que prova:

- em que estado o catálogo oficial está — ele não foi lido;
- que o self-hosted tenha a mesma versão, os mesmos papéis ou as mesmas extensões;
- qualquer comportamento da Meta.

## O que fecha CP2

A janela oficial autorizada, executada por esta lista, com o estado do catálogo
classificado **antes** do apply e o `sha256` de cada arquivo conferido **no
momento** da janela — e o recibo dizendo, arquivo por arquivo, o que foi
efetivamente aplicado.
