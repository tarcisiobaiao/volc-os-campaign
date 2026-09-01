# Preflight — aplicar a v10 no Supabase oficial

*Sprint `sprint/search-production-closure-v1` · destino `https://database.agenciavolc.com.br`*

**Autorizado pelo dono em 31/08/2026** para **três** migrations: `v10_01`, `v10_03` e
`v10_04`. A `v10_02` está **fora desta janela** por decisão explícita: ela é autogestão
T1 e não participa do caminho `/subir`. A autorização não cobre nenhuma tabela ou
migration além dessas três.

## 1. O que será aplicado, e em que ordem

| # | Arquivo | Linhas | sha256 | Depende de | Rollback |
|---|---|---|---|---|---|
| 1 | `v10_01_intencao_e_lote.sql` | 1950 | `827e8caae24b088f6601208c9c816f6b5ef5215c423d2729e99426871e3f54fb` | v9_01 (aplicada) | `v10_01_rollback.sql` (`b75eb90b09447493…`) |
| 2 | `v10_03_recibo_atomico.sql` | 992 | `bdb26eed7da08b649b735966bbd99809540843afb780ca91f94979b9aaad392c` | v9_01 + v10_01 | `v10_03_rollback.sql` (`b1c9d6598bd0bf52…`) |
| 3 | `v10_04_saida_do_indeterminado.sql` | 384 | `9122135ac98de62ee5b9f12e086a817f16860d59bb117a1d32b2a38b39dedd1b` | v10_01 + v10_03 | `v10_04_rollback.sql` (`eb93e200b66cf6dfa289193a8ddbb6b8b49567c52f1ca5e5bcb04699c880439b`) |

**Fora da janela:** `v10_02_autogestao.sql`
(`124eac489c9d3bb88eb6c79fed0b3c2a8e7256064279954b2023144e073e0846`) — **não aplicar**.
A v10_03 não depende dela, e a v10_04 tampouco.

Confira os hashes antes de qualquer coisa:

```bash
shasum -a 256 supabase/migrations/v10_0{1,3,4}*.sql
```

### Por que a v10_04 existe, em uma frase

Sem ela a reconciliação **aborta**: `trafego_ledger_fechar(...,'sem_resposta')` põe o lote
em `interrompido`, a reconciliação tenta `interrompido->concluido`, e a máquina de estados
da v10_01 não tem essa transição. A exceção derruba a transação inteira e o item
`indeterminado` fica sem saída que não seja `UPDATE` à mão. Aplicar v10_01+v10_03 **sem** a
v10_04 entrega um fluxo cuja única saída de emergência não funciona.

## 2. Antes de aplicar — o que conferir você mesmo

```bash
# 2.1 · o ciclo completo num cluster descartável (não toca produção)
./scripts/provar-ciclo-v10.sh          # v10_01 + v10_02: aplicar → reverter → reaplicar
./scripts/provar-ledger-v10-03.sh      # a fronteira atômica: 85 provas, 0 falhas

# 2.2 · o banco é o oficial?
python3 scripts/verificar_autoridade_supabase.py

# 2.3 · backup ANTES, conferido — não "o backup roda de noite"
ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  'docker exec supabase-db pg_dump -U postgres -Fc postgres > /root/backups/pre-v10-$(date +%F-%H%M).dump && ls -lh /root/backups/ | tail -3'
```

⚠️ **O rollback da v9_03 estava documentado e abortava.** Ele só foi descoberto quando
alguém tentou. Por isso 2.1 não é formalidade: é a única evidência de que existe caminho
de volta. A `v10_04` tem o ciclo `aplicar → reverter → reaplicar sobre banco com dado`
provado no bloco **M2** do mesmo script.

## 3. Estado atual, medido (não presumido)

```sql
-- 3.1 · esperado: 0 linhas. Qualquer resultado significa que a v10 JÁ está
-- parcialmente aplicada — PARE e investigue antes de seguir.
SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public'
   AND c.relname IN ('trafego_intencao','trafego_lote','trafego_lote_item','trafego_recibo');

-- 3.2 · pré-requisito: a v9_01 tem de estar lá (o item aponta para trafego_campanha)
SELECT to_regclass('public.trafego_campanha') IS NOT NULL AS v9_01_aplicada,
       to_regclass('public.trafego_linhagem') IS NOT NULL AS linhagem_ok;

-- 3.3 · os papéis nominais: sem eles a migration aborta de propósito
SELECT rolname, rolbypassrls FROM pg_roles
 WHERE rolname IN ('anon','authenticated','service_role') ORDER BY 1;

-- 3.4 · nenhuma função do ledger pode pré-existir
SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname='public' AND p.proname LIKE 'trafego\_ledger\_%';
-- esperado: 0 linhas
```

**Se 3.1 ou 3.4 devolverem qualquer linha, PARE.** Aplicação parcial não se resolve
aplicando o resto por cima.

## 4. A aplicação

```bash
for m in v10_01_intencao_e_lote v10_03_recibo_atomico v10_04_saida_do_indeterminado; do
  echo "── $m ──"
  cat supabase/migrations/$m.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
    root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1" \
    || { echo "ABORTOU em $m — pare aqui e leia o erro"; break; }
done
```

Cada arquivo abre `BEGIN`, verifica suas próprias garantias antes do `COMMIT` e aborta
inteiro se qualquer uma falhar. Um `ABORTOU` acima significa que **nada daquele arquivo**
persistiu. **Não continue depois de uma falha**, e não rode rollback automaticamente sobre
migrations já commitadas — preserve a evidência e reporte primeiro.

## 5. Contraprova depois de aplicar — a parte que não pode ser pulada

```sql
-- 5.1 · os objetos existem (SEM a v10_02 nesta janela)
SELECT count(*) AS tabelas_v10 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind='r' AND c.relname LIKE 'trafego\_%'
   AND c.relname NOT IN ('trafego_campanha','trafego_campanha_espelho','trafego_linhagem',
                         'trafego_snapshot_conta','trafego_evento','trafego_vinculo');
-- esperado: 10 (as 10 da v10_01; a v10_02 NÃO foi aplicada e a v10_04 não cria tabela)

-- 5.2 · anon e authenticated não alcançam NADA
SELECT count(*) AS vazamentos FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname LIKE 'trafego\_%'
   AND (has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE')
     OR has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE'));
-- esperado: 0

-- 5.3 · quem pode chamar o ledger (esperado: só service_role executa as 4)
SELECT p.proname, r.rolname, has_function_privilege(r.rolname, p.oid, 'EXECUTE') AS executa
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  CROSS JOIN (VALUES ('anon'),('authenticated'),('service_role')) AS r(rolname)
 WHERE n.nspname='public' AND p.proname LIKE 'trafego\_ledger\_%' ORDER BY 1,2;

-- 5.4 · a CAMADA 4 está de pé (é ela que impede a segunda campanha)
SELECT count(*) AS camada_4 FROM pg_trigger
 WHERE tgname='trafego_recibo_um_voo_por_item' AND NOT tgisinternal;
-- esperado: 1

-- 5.5 · RLS ligada E forçada, com zero policies
SELECT count(*) FILTER (WHERE NOT (relrowsecurity AND relforcerowsecurity)) AS sem_rls
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind='r' AND c.relname LIKE 'trafego\_%';
-- esperado: 0
SELECT count(*) AS policies FROM pg_policies WHERE schemaname='public'
   AND tablename LIKE 'trafego\_%';
-- esperado: 0

-- 5.6 · A V10_04 ENTROU, E NÃO APAGOU AS GUARDAS DA V10_01.
-- ⚠️ As duas metades importam. `CREATE OR REPLACE FUNCTION` substitui o corpo
-- inteiro, e uma versão anterior desta migration acrescentou a transição nova
-- apagando quatro guardas da v10_01 em silêncio. Conferir só a transição
-- deixaria passar exatamente isso.
SELECT
  pg_get_functiondef(p.oid) LIKE '%interrompido->concluido%'            AS transicao_nova,
  pg_get_functiondef(p.oid) LIKE '%a autorizacao nao se reescreve%'     AS guarda_aprovacao,
  pg_get_functiondef(p.oid) LIKE '%sao a identidade do lote e nao mudam%' AS guarda_identidade,
  pg_get_functiondef(p.oid) LIKE '%mais velha que a corrente%'          AS guarda_quota,
  pg_get_functiondef(p.oid) LIKE '%atualizado_em := now()%'             AS carimbo_tempo
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='trafego_lote_estado_valido';
-- esperado: t | t | t | t | t

-- 5.7 · a reconciliação confere posse (v10_04)
SELECT pg_get_functiondef(p.oid) LIKE '%pertence a conta%' AS confere_posse
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='trafego_ledger_reconciliar';
-- esperado: t

-- 5.8 · nenhuma função do ledger é SECURITY DEFINER
SELECT count(*) AS security_definer FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname LIKE 'trafego\_ledger\_%' AND p.prosecdef;
-- esperado: 0
```

**Registre a saída de 5.1–5.8 no `supabase/migrations/README.md`**, na tabela de estado.
Uma migration só é "aplicada" com recibo de execução e query de contraprova — arquivo
existir na pasta não é evidência de nada.

## 6. Depois da aplicação, o backend precisa de uma coisa

`/subir` **recusa** (503) quando o ledger não está configurado. O processo que serve a API
precisa ter `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` no ambiente — os mesmos que o
resto do router já usa (`.env.server`). Nenhuma variável nova foi introduzida.

## 7. Se der errado

`ROLLBACK-SEARCH-PRODUCTION-CLOSURE.md`, seção 1. A ordem de reversão é a inversa da
aplicação: `v10_04_rollback` → `v10_03_rollback` → `v10_01_rollback`.

⚠️ **Não rode rollback automaticamente** depois de uma migration já commitada. Preserve a
evidência do estado, reporte, e só então decida — reverter apaga a informação de que se
precisa para entender o que aconteceu.
