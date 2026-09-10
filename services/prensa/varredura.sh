#!/bin/sh
# Varre TODAS as specs do acervo pela PRENSA envelopada e reporta o veredito.
# Os fundos gerados vivem em assets_bg/ (fora do tmpfs) e são semeados em out/
# antes de cada rodada, porque resolve.py os procura lá.
set -u
cd /prensa/motor
cp -n assets_bg/*.png out/ 2>/dev/null || true
ok=0; falhou=0
for spec in spec_*.json; do
  [ "$spec" = "spec_grafico.json.bak" ] && continue
  saida=$(python resolve.py "$spec" 2>&1)
  resolvido=$(printf '%s' "$saida" | sed -n 's/.*· \([^ ]*\.resolvido\.json\) ·.*/\1/p')
  if [ -z "$resolvido" ]; then
    printf 'RESOLVE-FALHOU  %-32s %s\n' "$spec" "$(printf '%s' "$saida" | tail -1 | cut -c1-110)"
    falhou=$((falhou+1)); continue
  fi
  render=$(python render.py "out/$resolvido" 2>&1)
  n=$(printf '%s' "$render" | grep -c '^✅')
  if [ "$n" -gt 0 ]; then
    printf 'OK              %-32s %s peça(s)\n' "$spec" "$n"; ok=$((ok+1))
  else
    printf 'RENDER-FALHOU   %-32s %s\n' "$spec" "$(printf '%s' "$render" | tail -1 | cut -c1-110)"
    falhou=$((falhou+1))
  fi
done
printf '\nTOTAL: %s ok, %s falharam\n' "$ok" "$falhou"
