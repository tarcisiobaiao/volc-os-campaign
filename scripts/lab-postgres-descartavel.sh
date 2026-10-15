# lab-postgres-descartavel.sh — sourced (não executado) pelas provas do ledger.
#
# Um Postgres em container que nasce e morre na prova, com os papéis do Supabase
# e o default ACL QUEBRADO de public reproduzidos (testar_migration_descartavel.sh
# l.88-125). A espera de prontidão é a corrigida em provar-v18_01.sh: a imagem
# oficial sobe um servidor temporário, roda o init e REINICIA, então "aceitou
# conexão" não basta — exige o mesmo postmaster por três leituras seguidas.
#
# Variáveis: VOLC_PG_IMAGE (padrão postgres:15) · VOLC_LAB_PREFIXO (padrão volc-lab-)
# Exporta:   LAB_CN (nome do container) · P (psql -At) · lab_sqlstate · ok/nao/eq · FALHAS

LAB_IMG="${VOLC_PG_IMAGE:-postgres:15}"
LAB_CN="${VOLC_LAB_PREFIXO:-volc-lab-}${1:-prova}-$$"
FALHAS=0

lab_limpar() { docker rm -f "$LAB_CN" >/dev/null 2>&1; [ -n "${LAB_DIR:-}" ] && rm -rf "$LAB_DIR"; }

lab_criar() {
  command -v docker >/dev/null || { echo "docker ausente"; exit 2; }
  LAB_DIR="$(mktemp -d "${TMPDIR:-/tmp}/volclabXXXX")"
  trap lab_limpar EXIT
  docker run -d --name "$LAB_CN" -e POSTGRES_PASSWORD=lab -e POSTGRES_HOST_AUTH_METHOD=trust "$LAB_IMG" >/dev/null \
    || { echo "docker run falhou"; exit 2; }
  local ant="" iguais=0
  for _ in $(seq 1 120); do
    local t; t="$(docker exec "$LAB_CN" psql -U postgres -X -At -c 'select pg_postmaster_start_time()' 2>/dev/null)"
    if [ -n "$t" ] && [ "$t" = "$ant" ]; then iguais=$((iguais+1)); else iguais=0; fi
    ant="$t"
    [ $iguais -ge 3 ] && break
    sleep 1
  done
  [ $iguais -ge 3 ] || { echo "container não ficou pronto"; docker logs "$LAB_CN" 2>&1 | tail -5; exit 2; }
}

P() { docker exec -i "$LAB_CN" psql -U postgres -d postgres -X -q -At -v ON_ERROR_STOP=1 "$@"; }

# SQLSTATE do primeiro erro de um bloco SQL, ou "ok"
lab_sqlstate() {
  local out st
  out="$(printf '\\set VERBOSITY verbose\n%s\n' "$1" | docker exec -i "$LAB_CN" psql -U postgres -d postgres -X -At 2>&1)"
  st="$(printf '%s' "$out" | grep -oE 'ERROR:  [0-9A-Z]{5}' | head -1 | awk '{print $2}')"
  [ -n "$st" ] && echo "$st" || echo ok
}

ok()  { printf '  ✓ %s\n' "$1"; }
nao() { printf '  ✗ %s\n' "$1"; FALHAS=$((FALHAS+1)); }
eq()  { [ "$1" = "$2" ] && ok "$3" || nao "$3 (esperado=$2 obtido=$1)"; }

lab_papeis_supabase() {
  P >/dev/null <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN NOINHERIT; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN NOINHERIT; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS; END IF;
END $$;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO anon, authenticated, service_role;
SQL
  # sem o defeito reproduzido, toda prova de fechamento mede um ambiente mais seguro que o real
  P -c "CREATE TABLE public._sonda_default_acl(i int)" >/dev/null
  eq "$(P -c "select has_table_privilege('anon','public._sonda_default_acl','INSERT')")" "t" \
     "default ACL quebrado de public reproduzido (tabela nova nasce gravável por anon)"
  P -c "DROP TABLE public._sonda_default_acl" >/dev/null
}
