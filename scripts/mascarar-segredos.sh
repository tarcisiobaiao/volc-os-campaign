#!/usr/bin/env bash
# scripts/mascarar-segredos.sh — filtro stdin → stdout que mascara segredo antes
# de qualquer saída de produção ser gravada onde outra pessoa ou o Git leia.
# Cobre: JWT (eyJ…), Authorization Bearer, connection string com senha
# (postgres://user:senha@host), chaves de serviço com prefixo (sbp_, sk_, sk-,
# pk_, rk_, whsec_, ghp_, github_pat_, AIza, xox*), e pares chave=valor/chave: valor cujo
# nome sugere segredo (password, senha, secret, token, apikey, api_key, key),
# quando o valor é um literal (não uma chamada como Deno.env.get(...)).
# Testado por scripts/tests/test_mascarar_segredos.py — um formato que vazar
# derruba o teste.
set -euo pipefail
LC_ALL=C sed -E \
  -e 's/eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*/<JWT-MASCARADO>/g' \
  -e 's/([Bb]earer)[[:space:]]+[A-Za-z0-9._~+\/=-]{8,}/\1 <BEARER-MASCARADO>/g' \
  -e 's#([a-zA-Z][a-zA-Z0-9+.-]*://[^:/@[:space:]]+):[^[:space:]]*@#\1:<SENHA-MASCARADA>@#g' \
  -e 's/(sbp_|sk_live_|sk_test_|sk_|sk-|pk_live_|pk_test_|rk_|whsec_|ghp_|gho_|github_pat_|xox[abprs]-)[A-Za-z0-9_-]{8,}/\1<CHAVE-MASCARADA>/g' \
  -e 's/AIza[A-Za-z0-9_-]{20,}/AIza<CHAVE-MASCARADA>/g' \
  -e 's/(([Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Ss][Ee][Nn][Hh][Aa]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Tt][Oo][Kk][Ee][Nn]|[Aa][Pp][Ii]_?[Kk][Ee][Yy]|[Kk][Ee][Yy])[A-Za-z0-9_-]*["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"']?)[^"'"'"'[:space:],;\&|()]{6,}([[:space:]"'"'"',;\&|]|$)/\1<SEGREDO-MASCARADO>\3/g'
