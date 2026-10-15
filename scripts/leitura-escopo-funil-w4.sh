#!/usr/bin/env bash
# =============================================================================
# scripts/leitura-escopo-funil-w4.sh — leitura de produção para a condição 2 da
# aprovação da v19_10 (escopo do funil). PREPARADA, NÃO EXECUTADA. Só roda com
# autorização do Tarcísio para ESTA leitura:
#   VOLC_AUTORIZA_LEITURA="escopo-funil-w4" scripts/leitura-escopo-funil-w4.sh <dir-fora-do-repo>
#
# Responde, só com contagens e ids numéricos (nenhum e-mail, nome ou valor):
#   E1. há projetos que compartilham o mesmo domínio normalizado? A função de
#       escopo (public.volc_pode_editar_funil) aceita URL do domínio do projeto
#       da campanha; dois projetos no mesmo domínio deixariam um operador de um
#       pendurar URL do outro.
#   E2. operadores/admins de public.users cujo id não é um auth.users.id (legado,
#       anterior a api/_lib/usuarios.js): com a v19_10 identificando por
#       id = auth.uid(), esses não editam funil até serem alinhados.
#   E3. vínculos (user_campaigns, user_projects) desses usuários legados.
# Mesma guarda e mesma máscara da leitura do inventário anon: só leitura
# (sessão read-only + BEGIN READ ONLY), bruto em ~/.config/volc (700/600), só a
# saída mascarada vai para o diretório dado, que não pode ficar no repo.
# =============================================================================
set -euo pipefail
[[ "${VOLC_AUTORIZA_LEITURA:-}" == "escopo-funil-w4" ]] || {
  echo "recusado: defina VOLC_AUTORIZA_LEITURA=escopo-funil-w4 (só com autorização do Tarcísio)"; exit 16; }
OUT="${1:?uso: leitura-escopo-funil-w4.sh <dir-saida-mascarada>}"
RAIZ="$(cd "$(dirname "$0")/.." && pwd -P)"
fora_do_repo() {
  local real
  real="$(python3 -I -c 'import os,sys; print(os.path.realpath(os.path.abspath(sys.argv[1])))' "$1")" || exit 2
  case "$real/" in "$RAIZ"/*)
    echo "recusado: $2 resolve para dentro do repositório ($real)" >&2; exit 2 ;; esac
  printf '%s' "$real"
}
OUT="$(fora_do_repo "$OUT" "a saída mascarada")"
RAW="$(fora_do_repo "${VOLC_INVENTARIO_RAW:-$HOME/.config/volc/escopo-funil/$(date +%Y%m%d-%H%M%S)}" "a saída bruta")"
[[ "$RAW" != "$OUT" ]] || { echo "recusado: bruta e mascarada no mesmo diretório"; exit 2; }
mkdir -p "$OUT"; umask 077; mkdir -p "$RAW"; chmod 700 "$RAW" "$(dirname "$RAW")"
MASCARAR="$RAIZ/scripts/mascarar-segredos.sh"
SSH=(ssh -i "$HOME/.ssh/volc_hetzner_claude_ed25519" -o BatchMode=yes -o ConnectTimeout=10 root@178.156.196.149)
LEITURA="docker exec -i -e PGOPTIONS=-c\\ default_transaction_read_only=on supabase-db psql -U postgres -d postgres -X -q -A -F'|' -v ON_ERROR_STOP=1"

"${SSH[@]}" "$LEITURA" > "$RAW/01-escopo-funil.txt" 2>&1 <<'SQL'
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL search_path = pg_catalog;
-- mesma normalização de domínio da public.volc_pode_editar_funil
WITH dom AS (
  SELECT pr.id,
         split_part(regexp_replace(regexp_replace(lower(coalesce(nullif(pr.domain, ''), pr.main_url)), '^[a-z]+://', ''), '^www\.', ''), '/', 1) AS d
    FROM public.projects pr
), rep AS (SELECT d, count(*) AS n, array_agg(id ORDER BY id) AS ids FROM dom GROUP BY d HAVING count(*) > 1)
SELECT 'E1 dominios_compartilhados', (SELECT count(*) FROM rep)::text, 'projetos_envolvidos=' || coalesce((SELECT sum(n) FROM rep), 0)::text
UNION ALL
SELECT 'E1 detalhe (ids de projeto por domínio repetido; domínio omitido)', n::text, array_to_string(ids, ',') FROM rep
UNION ALL
SELECT 'E1 projetos_total', (SELECT count(*) FROM dom)::text, 'sem_dominio=' || (SELECT count(*) FROM dom WHERE d = '')::text
UNION ALL
SELECT 'E2 operadores_admins_cadastro', count(*)::text,
       'id_sem_auth=' || count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM auth.users au WHERE au.id = u.id))::text
       || ' email_casa_auth_com_outro_id=' || count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM auth.users au WHERE au.id = u.id)
              AND EXISTS (SELECT 1 FROM auth.users au WHERE lower(au.email) = lower(u.email)))::text
  FROM public.users u WHERE u.role IN ('OPERATOR', 'ADMIN')
UNION ALL
SELECT 'E2 por_papel_sem_auth (' || u.role || ')', count(*)::text, ''
  FROM public.users u WHERE u.role IN ('OPERATOR', 'ADMIN')
   AND NOT EXISTS (SELECT 1 FROM auth.users au WHERE au.id = u.id) GROUP BY u.role
UNION ALL
SELECT 'E3 vinculos_de_legados', (SELECT count(*) FROM public.user_campaigns uc JOIN public.users u ON u.id = uc.user_id
          WHERE NOT EXISTS (SELECT 1 FROM auth.users au WHERE au.id = u.id))::text,
       'user_projects=' || (SELECT count(*) FROM public.user_projects up JOIN public.users u ON u.id = up.user_id
          WHERE NOT EXISTS (SELECT 1 FROM auth.users au WHERE au.id = u.id))::text;
ROLLBACK;
SQL
bash "$MASCARAR" < "$RAW/01-escopo-funil.txt" > "$OUT/01-escopo-funil.txt"
chmod 600 "$RAW"/*
( cd "$OUT" && shasum -a 256 01-*.txt > SHA256SUMS )
cat "$OUT/01-escopo-funil.txt"
echo "mascarada em $OUT; bruta, só do dono, em $RAW"
