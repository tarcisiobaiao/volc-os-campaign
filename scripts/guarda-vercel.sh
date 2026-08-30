#!/usr/bin/env bash
#
# guarda-vercel — recusa qualquer procedimento de deploy se o vínculo local
# não for exatamente o projeto aprovado.
#
# ESTE SCRIPT NÃO FAZ DEPLOY. Ele só responde "pode ou não pode", e é para ser
# a primeira linha de qualquer runbook que vá falar com a Vercel:
#
#     ./scripts/guarda-vercel.sh || exit 1
#
# ---------------------------------------------------------------------------
# POR QUE ELE EXISTE
# ---------------------------------------------------------------------------
# Em 24/08/2026 uma investigação de exposição foi conduzida inteira contra o
# projeto ERRADO. O repositório estava vinculado a `webgo`
# (prj_yjLbJZus5dTTtaY3pBbUDP6uLriX), e todo comando `vercel` sem `--scope` e
# sem nome de projeto obedeceu a esse vínculo em silêncio. A cronologia
# apurada — "produção há 52 dias, deployment atual de 11 dias" — era de outro
# sistema. A janela real do `volc-os-campaign` é de 189 dias.
#
# Nenhum comando falhou. Nenhum aviso apareceu. `.vercel/project.json` é um
# arquivo local, gerado, gitignorado e trivialmente trocado por um `vercel
# link` distraído — e ainda assim é a autoridade padrão de todo comando da CLI.
# Um deploy nessas condições publica o código de um cliente no domínio de
# outro, e o erro só aparece depois.
#
# Por isso a identidade aprovada está ESCRITA AQUI, versionada, e não lida de
# lugar nenhum que um engano possa reescrever.
set -euo pipefail

PROJETO_APROVADO="volc-os-campaign"
ID_APROVADO="prj_tn56w79cDSALjzdqLruqeGYKMaVs"
ESCOPO_APROVADO="tarcisios-projects-2895d85f"

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VINCULO="$RAIZ/.vercel/project.json"

falhar() {
  echo "" >&2
  echo "  ✖ GUARDA VERCEL: deploy bloqueado." >&2
  echo "    $1" >&2
  echo "" >&2
  echo "    Esperado:  $PROJETO_APROVADO / $ID_APROVADO" >&2
  echo "    Escopo:    $ESCOPO_APROVADO" >&2
  echo "" >&2
  echo "    Para corrigir o vínculo (não faz deploy):" >&2
  echo "      npx vercel link --project $PROJETO_APROVADO --scope $ESCOPO_APROVADO --yes" >&2
  echo "" >&2
  exit 1
}

[ -f "$VINCULO" ] || falhar "não existe .vercel/project.json — o repositório não está vinculado."

# `node -p` em vez de grep/sed: o arquivo é JSON, e casar chave por texto é
# como um valor entre aspas escapadas passa despercebido.
nome="$(node -p "require('$VINCULO').projectName || ''" 2>/dev/null || echo '')"
id="$(node -p "require('$VINCULO').projectId || ''" 2>/dev/null || echo '')"

[ "$nome" = "$PROJETO_APROVADO" ] || falhar "projectName vinculado é '$nome'."
[ "$id" = "$ID_APROVADO" ] || falhar "projectId vinculado é '$id'."

echo "  ✓ guarda vercel: $nome / $id"
echo "    lembre-se de passar --scope $ESCOPO_APROVADO em todo comando da CLI."
