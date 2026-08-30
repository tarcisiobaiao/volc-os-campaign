#!/usr/bin/env bash
#
# sync-upstream.sh — sincroniza este fork com uma nova versão do webgo.
#
#   ./scripts/sync-upstream.sh webgov7
#
# O script faz a parte mecânica e PARA em toda decisão que exige julgamento.
# Ele nunca resolve conflito por você e nunca faz push.
#
# Leia docs/VOLC-DELTA.md antes do primeiro uso.
#
set -euo pipefail
cd "$(dirname "$0")/.."

BRANCH="${1:-}"
if [ -z "$BRANCH" ]; then
  echo "uso: $0 <branch-do-upstream>    (ex.: $0 webgov7)" >&2
  exit 2
fi

bold() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[33m    %s\033[0m\n' "$1"; }
die()  { printf '\033[31m!!! %s\033[0m\n' "$1" >&2; exit 1; }

# --- pré-condições -----------------------------------------------------------
[ -n "$(git status --porcelain)" ] && die "working tree sujo. Commite ou guarde antes de sincronizar."
git remote get-url upstream >/dev/null 2>&1 || die "remote 'upstream' não configurado. Veja docs/VOLC-DELTA.md seção 1."

if [ "$(git config --get rerere.enabled || echo false)" != "true" ]; then
  warn "rerere desligado — ligando agora (é ele que reaplica as resoluções conhecidas)."
  git config rerere.enabled true
  git config rerere.autoUpdate true
fi

CURRENT="$(git branch --show-current)"

# --- rede de segurança -------------------------------------------------------
bold "Rede de segurança"
BACKUP="backup/${CURRENT}-pre-${BRANCH}"
git branch -f "$BACKUP" "$CURRENT"
git tag -f "pre-${BRANCH}-sync" "$CURRENT" >/dev/null
echo "    branch $BACKUP e tag pre-${BRANCH}-sync criadas em $(git rev-parse --short "$CURRENT")"

# --- baseline ----------------------------------------------------------------
bold "Baseline de qualidade (antes do merge)"
if npx tsc --noEmit >/dev/null 2>&1; then
  echo "    tsc: 0 erros  <- este é o gate; depois do merge tem que continuar 0"
else
  warn "tsc JÁ falha antes do merge. Corrija antes de sincronizar, ou o gate perde o sentido."
fi

# --- buscar upstream ---------------------------------------------------------
bold "Buscando upstream/$BRANCH"
git fetch upstream --prune
git rev-parse --verify "upstream/$BRANCH" >/dev/null 2>&1 || die "upstream/$BRANCH não existe."

AHEAD=$(git rev-list --count "HEAD..upstream/$BRANCH")
[ "$AHEAD" -eq 0 ] && { echo "    Já sincronizado — nada a fazer."; exit 0; }
echo "    $AHEAD commit(s) novo(s):"
git log --oneline "HEAD..upstream/$BRANCH" | head -25 | sed 's/^/      /'
[ "$AHEAD" -gt 25 ] && echo "      ... e mais $((AHEAD - 25))"

# --- simulação ---------------------------------------------------------------
bold "Simulando o merge (não toca no working tree)"
if MT=$(git merge-tree --write-tree "HEAD" "upstream/$BRANCH" 2>&1); then
  echo "    Sem conflito previsto."
else
  echo "$MT" | grep -E '^(CONFLICT|added in both|changed in both)' | sed 's/^/      /' || true
  warn "Conflitos previstos acima. docs/VOLC-DELTA.md seção 3 documenta os recorrentes."
fi

# --- merge -------------------------------------------------------------------
SYNC_BRANCH="sync/$BRANCH"
bold "Criando $SYNC_BRANCH e fazendo o merge"
git checkout -b "$SYNC_BRANCH"

if git merge "upstream/$BRANCH" --no-edit; then
  echo "    Merge automático limpo."
else
  UNRESOLVED=$(git diff --name-only --diff-filter=U)
  if [ -z "$UNRESOLVED" ]; then
    warn "rerere resolveu tudo sozinho. CONFIRA antes de aceitar:"
    echo "      git diff --cached"
    warn "Depois: git commit"
  else
    bold "PAUSA — resolva estes conflitos à mão"
    echo "$UNRESOLVED" | sed 's/^/      /'
    echo
    echo "    docs/VOLC-DELTA.md seção 3 tem a decisão registrada para os recorrentes."
    echo "    Quando terminar:  git add -A && git commit"
    echo "    Depois rode de novo com --continue:  $0 $BRANCH --continue"
    exit 3
  fi
fi

# --- pós-merge ---------------------------------------------------------------
bold "Podando o Pautador Pro"
./scripts/prune-pautador.sh

bold "PAUSA — edições manuais em arquivos compartilhados"
cat <<'EOF'
    O script de poda não mexe em arquivo compartilhado. Confira agora:

      src/App.tsx                          -> import e rota /pautador-pro
      src/components/layout/Navigation.tsx -> item de menu e ícone Radar
      package.json                         -> dev:backend, dev:stop, dev:all

    NÃO remova src/v6 — é núcleo (RBAC/comissões), não Pautador.
EOF

bold "Verificando o branding VOLC"
# `backend/app/**` entrou na varredura porque a marca vazou por lá: o compositor
# do briefing passava brand="WEBGO" e nomeava o arquivo *_WEBGO.docx sem que
# ninguém visse, justamente por estar fora deste grep. O escopo é `app/` e não
# `backend/` inteiro de propósito: em `backend/scripts/` e `backend/tests/` a
# palavra é nome de variável de caminho, não marca — varrer tudo devolveria uma
# dúzia de falsos positivos e um alerta que ninguém lê deixa de ser alerta.
LEFT=$(git grep -in 'webgo' -- 'src/**' 'backend/app/**' index.html README.md 2>/dev/null \
        | grep -vE 'src/v6/(README\.md|featureFlag\.ts)|^README\.md:22|webgov[0-9]' || true)
if [ -n "$LEFT" ]; then
  warn "Marca 'webgo' encontrada onde não deveria:"
  echo "$LEFT" | sed 's/^/      /'
else
  echo "    OK."
fi
git grep -q 'logo-webgocontent' -- 'src/**' 2>/dev/null \
  && warn "Logo antigo ainda referenciado em src/" \
  || echo "    Logo: OK."
grep -q 'Sistema VOLC O.S.' src/pages/Reports.tsx 2>/dev/null \
  && echo "    Rodapé do PDF: OK." \
  || warn "Rodapé do PDF perdeu a marca VOLC — src/pages/Reports.tsx"

bold "Divergências de banco a checar"
cat <<'EOF'
    Um sync de código NÃO sincroniza banco. Compare os schemas antes de subir:
      docs/VOLC-DELTA.md seção 6

    Procure DDL novo que possa ter vindo junto:
      git diff --name-only HEAD@{1} -- src/sql/
EOF

bold "Validação final"
echo "    npm ci && npx tsc --noEmit && npm run build && npm test"
echo
echo "    Quando tudo passar:"
echo "      git checkout $CURRENT && git merge $SYNC_BRANCH"
echo
echo "    Se der errado:"
echo "      git checkout $CURRENT && git branch -D $SYNC_BRANCH   # (backup em $BACKUP)"
echo
warn "REGISTRE as resoluções novas em docs/VOLC-DELTA.md — é o que mantém o próximo sync barato."
