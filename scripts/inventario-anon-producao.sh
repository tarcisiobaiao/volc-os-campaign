#!/usr/bin/env bash
# =============================================================================
# scripts/inventario-anon-producao.sh — leitura de produção para o inventário de
# consumidores da anon key (pacote do incidente anon, W4). PREPARADO, NÃO RODADO.
# Só roda com autorização do Tarcísio para ESTA leitura:
#   VOLC_AUTORIZA_LEITURA="inventario-anon-w4" scripts/inventario-anon-producao.sh <dir-saida>
#
# Somente leitura. Nada aqui imprime segredo: do .env do servidor só se lê o
# NOME e o valor booleano de duas flags; o código da edge function é filtrado
# por grep (nomes de variável, tabelas e chamadas), nunca impresso inteiro;
# do banco só saem contagens e datas, em BEGIN READ ONLY.
# O que não dá para ler daqui (GTM vivo, credenciais do n8n) fica no fim como
# passo manual, com o que olhar.
# =============================================================================
set -euo pipefail
[[ "${VOLC_AUTORIZA_LEITURA:-}" == "inventario-anon-w4" ]] || {
  echo "recusado: defina VOLC_AUTORIZA_LEITURA=inventario-anon-w4 (só com autorização do Tarcísio)"; exit 16; }
OUT="${1:?uso: inventario-anon-producao.sh <dir-saida>}"; mkdir -p "$OUT"
SSH=(ssh -i "$HOME/.ssh/volc_hetzner_claude_ed25519" -o BatchMode=yes -o ConnectTimeout=10 root@178.156.196.149)
# Mascara qualquer coisa com cara de segredo antes de gravar (JWT, chaves longas).
mascarar() { sed -E 's/eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/<JWT-MASCARADO>/g;
  s/((sk|pk|key|token|secret|senha|password)[-_A-Za-z0-9]*["'"'"' :=]+)[A-Za-z0-9_\/+=.-]{16,}/\1<SEGREDO-MASCARADO>/Ig'; }
LEITURA="docker exec -i -e PGOPTIONS=-c\\ default_transaction_read_only=on supabase-db psql -U postgres -d postgres -X -q -A -F'|' -v ON_ERROR_STOP=1"

echo "== 1. edge function volc-ingest: existe, verifica JWT, que chave e que tabelas usa" | tee "$OUT/01-volc-ingest.txt"
"${SSH[@]}" 'ls -la /root/supabase/docker/volumes/functions/ 2>&1;
  d=/root/supabase/docker/volumes/functions/volc-ingest;
  [ -d "$d" ] && { ls -la "$d"; sha256sum "$d"/*;
    grep -nE "SUPABASE_(ANON|SERVICE_ROLE)_KEY|Deno\.env\.get|createClient|\.from\(|\.rpc\(|/rest/v1|Authorization|apikey" "$d"/* ; } || echo "volc-ingest: diretório ausente";
  grep -oE "^(FUNCTIONS_VERIFY_JWT|VERIFY_JWT)=(true|false)" /root/supabase/docker/.env || echo "flag VERIFY_JWT não encontrada"' \
  2>&1 | mascarar >> "$OUT/01-volc-ingest.txt"

echo "== 2. GoTrue: cadastro público" | tee "$OUT/02-gotrue.txt"
"${SSH[@]}" 'grep -oE "^(DISABLE_SIGNUP|ENABLE_EMAIL_SIGNUP|ENABLE_ANONYMOUS_USERS)=(true|false)" /root/supabase/docker/.env' >> "$OUT/02-gotrue.txt" 2>&1 || true

echo "== 3. Kong: chamadas aos alvos da anon nos últimos 14 dias (método, caminho, status, contagem)" | tee "$OUT/03-kong.txt"
"${SSH[@]}" 'docker logs supabase-kong --since 336h 2>&1 \
  | grep -oE "\"(GET|POST|PATCH|DELETE) /(rest/v1/(site_visits|raw_events|niche_conversion_mappings|hourly_stats|fact_[a-z_]+)|functions/v1/volc-ingest)[^ ?\"]*[^\"]*\" [0-9]{3}" \
  | sed -E "s/\?[^ ]*//" | sort | uniq -c | sort -rn | head -50' 2>&1 | mascarar >> "$OUT/03-kong.txt" || true

echo "== 4. Banco: atividade de escrita nas tabelas que a anon alcançava (só contagens e datas)" | tee "$OUT/04-banco.txt"
"${SSH[@]}" "$LEITURA" >> "$OUT/04-banco.txt" 2>&1 <<'SQL' || true
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SELECT 'stats_reset', coalesce(stats_reset::text, 'nunca') FROM pg_stat_database WHERE datname = current_database();
SELECT relname, n_tup_ins, n_tup_upd, n_tup_del, coalesce(last_autoanalyze::text, '-')
  FROM pg_stat_user_tables
 WHERE schemaname = 'public'
   AND relname IN ('site_visits','raw_events','niche_conversion_mappings','hourly_stats','fact_page_daily','fact_funnel_daily')
 ORDER BY 1;
SELECT 'site_visits ultima', max(created_at)::text FROM public.site_visits;
SELECT 'raw_events ultima', max(created_at)::text FROM public.raw_events;
ROLLBACK;
SQL

cat > "$OUT/05-manual.txt" <<'TXT'
== 5. Passos manuais (não dá para ler daqui)
- GTM-N4KS27ZV e GTM-KJK7QQK9: na UI do Tag Manager, versão publicada atual; listar
  tags com "/rest/v1" ou "/functions/v1" e o estado (pausada/ativa). Não copiar o JWT.
- n8n "gads-campaign-search" e "comportamento-gtm-scroll-funil": abrir o nó HTTP,
  decodificar só o payload do apikey e anotar o claim "role" (anon ou service_role).
- n8n credencial "VOLC Oficial": mesmo procedimento; anotar só o claim "role".
Preencher docs/closure/incidente-anon-w4/INVENTARIO-ANON.json a partir de
docs/INCIDENTE-ANON-INVENTARIO.modelo.json com o resultado e a decisão de cada item.
TXT
cat "$OUT/05-manual.txt"
( cd "$OUT" && shasum -a 256 0*.txt > SHA256SUMS ) && echo "saídas em $OUT (SHA256SUMS)"
