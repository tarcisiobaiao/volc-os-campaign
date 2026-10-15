# scripts/lib/gotrue-cadastro.sh — funções de escrita do fechar-cadastro-gotrue.sh,
# separadas para os testes (scripts/tests/test_fechar_cadastro_gotrue.py) as
# exercitarem sobre um diretório temporário. Usam SSH (array), DIR e CARIMBO
# definidos por quem faz source.
# Todo comando remoto roda sob "set -euo pipefail": qualquer falha no meio da
# cadeia sai não-zero, e o set -e daqui derruba o script na hora.
remoto() { "${SSH[@]}" "set -euo pipefail
  command -v sha256sum >/dev/null || sha256sum() { shasum -a 256 \"\$@\"; }
  $1"; }

fechar() { # backup com sha256 gravado ao lado; troca a linha; recria só o auth
  local bak="$DIR/.env.bak-w4-signup-$CARIMBO"
  remoto "cd $DIR
    grep -qx 'DISABLE_SIGNUP=false' .env
    cp -p .env $bak; chmod 600 $bak
    sha256sum $bak | cut -d' ' -f1 > $bak.sha256; chmod 600 $bak.sha256
    sed -i.w4tmp 's/^DISABLE_SIGNUP=false\$/DISABLE_SIGNUP=true/' .env; rm -f .env.w4tmp
    grep -qx 'DISABLE_SIGNUP=true' .env
    docker compose up -d --no-deps auth
    for i in \$(seq 1 30); do docker ps --filter name=supabase-auth --format '{{.Status}}' | grep -q healthy && break; sleep 2; done
    docker ps --filter name=supabase-auth --format '{{.Status}}' | grep -q healthy"
  echo "backup do .env no servidor: $bak (sha256 em $bak.sha256)"
  echo "para reverter: VOLC_AUTORIZA_GOTRUE=reabrir-cadastro $0 --reverter $CARIMBO"
}

reabrir() { # restaura o backup EXATO depois de conferir o sha256 gravado na aplicação
  local carimbo="${1:?--reverter exige o carimbo impresso pelo --aplicar}" bak
  [[ "$carimbo" =~ ^[0-9]{8}-[0-9]{6}$ ]] || { echo "carimbo inválido: $carimbo"; exit 2; }
  bak="$DIR/.env.bak-w4-signup-$carimbo"
  remoto "cd $DIR
    if [ ! -f $bak ] || [ ! -f $bak.sha256 ]; then echo 'backup ausente para este carimbo: nada conferido, nada restaurado'; exit 1; fi
    [ \"\$(sha256sum $bak | cut -d' ' -f1)\" = \"\$(cat $bak.sha256)\" ] || { echo 'backup alterado: sha256 não confere; nada restaurado'; exit 1; }
    cp -p .env .env.antes-de-reverter-$CARIMBO; chmod 600 .env.antes-de-reverter-$CARIMBO
    cp -p $bak .env
    grep -qx 'DISABLE_SIGNUP=false' .env
    docker compose up -d --no-deps auth
    for i in \$(seq 1 30); do docker ps --filter name=supabase-auth --format '{{.Status}}' | grep -q healthy && break; sleep 2; done
    docker ps --filter name=supabase-auth --format '{{.Status}}' | grep -q healthy"
  echo "restaurado $bak (sha256 conferido); o .env de antes da reversão ficou em $DIR/.env.antes-de-reverter-$CARIMBO"
}

