# Preflight — aplicar a v10 no Supabase oficial

*Sprint `sprint/search-production-closure-v1` · destino `https://database.agenciavolc.com.br`*

⚠️ **Nada aqui foi executado.** Esta sessão não tinha (e não pediu) autorização para
escrever no banco oficial. Este documento é o pedido, com o que precisa ser conferido
antes e o que precisa ser verdade depois.

## 1. O que se está pedindo autorização para fazer

Aplicar **três** migrations, nesta ordem, no banco `postgres` do Supabase self-hosted:

| # | Arquivo | Linhas | sha256 (12) | Depende de |
|---|---|---|---|---|
| 1 | `v10_01_intencao_e_lote.sql` | 1950 | `827e8caae24b` | v9_01 (aplicada) |
| 2 | `v10_02_autogestao.sql` | 1722 | `124eac489c9d` | v10_01 |
| 3 | `v10_03_recibo_atomico.sql` | 992 | *(ver `README.md` da pasta)* | v9_01 + v10_01 |

Isto corresponde à **decisão D1** do `OPEN-DECISIONS.md`, ampliada: a v10_03 não existia
quando D1 foi escrita.

**A v10_02 é opcional para o lançamento Search.** Ela é a autogestão T1 e não participa
do caminho `/subir`. Se quiser reduzir a superfície da janela, aplique 1 e 3 e deixe a 2
para outra ocasião — a v10_03 não depende dela.

## 2. Antes de autorizar — o que conferir você mesmo

```bash
# 2.1 · o ciclo completo num cluster descartável (não toca produção)
./scripts/provar-ciclo-v10.sh          # v10_01 + v10_02: aplicar → reverter → reaplicar
./scripts/provar-ledger-v10-03.sh      # a fronteira atômica: 53 provas

# 2.2 · o banco é o oficial?
python3 scripts/verificar_autoridade_supabase.py

# 2.3 · backup ANTES, conferido — não "o backup roda de noite"
ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  'docker exec supabase-db pg_dump -U postgres -Fc postgres > /root/backups/pre-v10-$(date +%F-%H%M).dump && ls -lh /root/backups/ | tail -3'
```

⚠️ **O rollback da v9_03 estava documentado e abortava.** Ele só foi descoberto quando
alguém tentou. Por isso 2.1 não é formalidade: é a única evidência de que existe caminho
de volta.

## 3. Estado atual, medido (não presumido)

```sql
-- esperado: 0 linhas. Qualquer resultado aqui significa que a v10 JÁ está parcialmente
-- aplicada, e a migration vai abortar com "ja parece aplicada" — o que é o certo.
SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public'
   AND c.relname IN ('trafego_intencao','trafego_lote','trafego_lote_item','trafego_recibo');

-- pré-requisito: a v9_01 tem de estar lá (o item aponta para trafego_campanha)
SELECT to_regclass('public.trafego_campanha') IS NOT NULL AS v9_01_aplicada,
       to_regclass('public.trafego_linhagem') IS NOT NULL AS linhagem_ok;

-- os papéis nominais: sem eles a migration aborta de propósito
SELECT rolname, rolbypassrls FROM pg_roles
 WHERE rolname IN ('anon','authenticated','service_role') ORDER BY 1;
```

## 4. A aplicação

```bash
for m in v10_01_intencao_e_lote v10_02_autogestao v10_03_recibo_atomico; do
  echo "── $m ──"
  cat supabase/migrations/$m.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
    root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1" \
    || { echo "ABORTOU em $m — pare aqui e leia o erro"; break; }
done
```

Cada arquivo abre `BEGIN`, verifica suas próprias garantias antes do `COMMIT` e aborta
inteiro se qualquer uma falhar. Um `ABORTOU` acima significa que **nada daquele arquivo**
persistiu.

## 5. Contraprova depois de aplicar — a parte que não pode ser pulada

```sql
-- 5.1 · os objetos existem
SELECT count(*) AS tabelas_v10 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind='r' AND c.relname LIKE 'trafego\_%'
   AND c.relname NOT IN ('trafego_campanha','trafego_campanha_espelho','trafego_linhagem',
                         'trafego_snapshot_conta','trafego_evento','trafego_vinculo');
-- esperado: 19 (10 da v10_01 + 9 da v10_02)

-- 5.2 · anon e authenticated não alcançam NADA
SELECT count(*) AS vazamentos FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname LIKE 'trafego\_%'
   AND (has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE')
     OR has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE'));
-- esperado: 0

-- 5.3 · quem pode chamar o ledger (esperado: só service_role, 4 funções)
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
```

**Registre a saída de 5.1–5.5 no `supabase/migrations/README.md`**, na tabela de estado.
Uma migration só é "aplicada" com recibo de execução e query de contraprova — arquivo
existir na pasta não é evidência de nada.

## 6. Depois da aplicação, o backend precisa de uma coisa

`/subir` agora **recusa** (503) quando o ledger não está configurado. O processo que serve
a API precisa ter `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` no ambiente — os mesmos que
o resto do router já usa (`.env.server`). Nenhuma variável nova foi introduzida.

## 7. Se der errado

`ROLLBACK-SEARCH-PRODUCTION-CLOSURE.md`, seção 1. Os três rollbacks são independentes e
provados no ciclo descartável; a ordem de reversão é a inversa da aplicação.
