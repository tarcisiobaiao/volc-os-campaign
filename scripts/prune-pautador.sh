#!/usr/bin/env bash
#
# prune-pautador.sh — remove o bloco Pautador Pro do fork VOLC O.S.
#
# POR QUE ESTE SCRIPT EXISTE
# O VOLC O.S. é um fork do webgo (metro-campaign-view). O webgo desenvolve o
# "Pautador Pro" (backend Python FastAPI + frontend de arbitragem de atenção),
# que está fora do escopo do VOLC. Cada `git merge upstream/webgovN` traz esse
# bloco de volta. Em vez de redescobrir o que apagar a cada sync, rode isto.
#
# USO
#   git merge upstream/webgovN     # resolve conflitos, commita o merge
#   ./scripts/prune-pautador.sh    # remove o Pautador
#   git commit -m "chore: poda do Pautador Pro (fora do escopo VOLC)"
#
# O script é idempotente: rodar duas vezes não causa erro.
#
# CUIDADO — o que NÃO é Pautador, apesar do nome/aparência:
#   src/v6/                    → RBAC/comissões por campanha. É NÚCLEO. Mantém.
#   src/sql/v6_*.sql           → schema do RBAC v6. Mantém.
#   src/sql/v7_13_*.sql        → Meta CAPI (só o nome da série coincide). Mantém.
#   vitest.config.ts           → os únicos testes do repo são do Meta CAPI. Mantém.
#   @dnd-kit/*                 → usado pelo Kanban da Incubadora. Mantém.
#   docs/archive/plans/incubadora-sites-plan.md → plano da Incubadora. Mantém.
#
set -euo pipefail
cd "$(dirname "$0")/.."

removed=0
rm_path() {
  if [ -e "$1" ] || git ls-files --error-unmatch "$1" >/dev/null 2>&1; then
    git rm -r -q --ignore-unmatch "$1" 2>/dev/null || rm -rf "$1"
    echo "  removido: $1"
    removed=$((removed + 1))
  fi
}

echo "==> Removendo árvore do Pautador Pro"
rm_path "backend"
rm_path "src/components/pautador-pro"
rm_path "src/pages/pautador-pro"
rm_path "src/data/pautadorCountries.ts"
rm_path "n8n/pautador_kw_mining_webhook.json"
rm_path "start-dev.sh"   # só orquestra o backend Python; dev:all volta a usar concurrently

for f in $(git ls-files 'src/hooks/pautador*' 'src/lib/pautador*' 'src/services/pautador*' 'src/types/pautador*' 2>/dev/null); do
  rm_path "$f"
done

echo "==> Removendo migrations do Pautador (preservando v7_13 = Meta CAPI)"
for f in $(git ls-files 'src/sql/v7_*.sql' 2>/dev/null); do
  case "$f" in
    *v7_13_meta_capi_sites.sql) echo "  PRESERVADO: $f (Meta CAPI)" ;;
    *) rm_path "$f" ;;
  esac
done

echo "==> Removendo docs do Pautador"
for f in $(git ls-files 'docs/superpowers/**' 2>/dev/null); do
  case "$f" in
    *pautador*|*duplicar-entidade*) rm_path "$f" ;;
  esac
done

echo
echo "==> Verificação: nenhuma referência órfã ao Pautador no código que fica"
orphans=$(git grep -lniE "pautador" -- 'src/**' 'api/**' 'server/**' 'package.json' 'vercel.json' 2>/dev/null || true)
if [ -n "$orphans" ]; then
  echo "  ATENÇÃO — ainda há referências a 'pautador' em:"
  echo "$orphans" | sed 's/^/    /'
  echo "  Se for src/sql/v7_13 (função set_pautador_updated_at), é esperado e inofensivo."
else
  echo "  OK — nenhuma referência."
fi

echo
echo "==> $removed caminho(s) removido(s)."
echo "    Edições manuais em arquivos compartilhados NÃO são feitas por este script."
echo "    Confira src/App.tsx, src/components/layout/Navigation.tsx e package.json"
echo "    conforme documentado em docs/VOLC-DELTA.md."
