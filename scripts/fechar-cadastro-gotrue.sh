#!/usr/bin/env bash
# =============================================================================
# scripts/fechar-cadastro-gotrue.sh — fecha o cadastro público do GoTrue de
# produção (DISABLE_SIGNUP=true). PREPARADO, NÃO EXECUTADO. --aplicar e
# --reverter só com OK explícito do Tarcísio repassado pelo coordenador.
#
# Por quê (leitura de 15/10/2026, W4-inventario-leitura/02 e 07): DISABLE_SIGNUP=false,
# ENABLE_PHONE_SIGNUP=true e ENABLE_PHONE_AUTOCONFIRM=true. Qualquer pessoa com
# a anon key (pública, no bundle) pode se cadastrar e virar `authenticated` —
# papel que, mesmo depois do pacote v19, lê e escreve as tabelas do app.
# O que continua funcionando: login de quem já existe (1 usuário em auth.users)
# e criação de usuário pelo app, que usa auth.admin.createUser com service_role
# (api/_lib/usuarios.js:73) — a API admin ignora DISABLE_SIGNUP.
# O que para: cadastro por /auth/v1/signup (e-mail e telefone) e o 1º login por
# OAuth (Google) de quem ainda não existe em auth.users.
#
# Uso:
#   scripts/fechar-cadastro-gotrue.sh --checar     só leitura (pode rodar a qualquer hora)
#   VOLC_AUTORIZA_GOTRUE=fechar-cadastro  scripts/fechar-cadastro-gotrue.sh --aplicar
#   VOLC_AUTORIZA_GOTRUE=reabrir-cadastro scripts/fechar-cadastro-gotrue.sh --reverter
#
# Efeito colateral: --aplicar/--reverter recriam só o container do GoTrue
# (`docker compose up -d --no-deps auth`): alguns segundos sem /auth/v1 (login e
# refresh de token falham e tentam de novo). Kong NÃO é reiniciado (armadilha do
# kong.yml, CLAUDE.md). Nenhum segredo é impresso: do .env só se lê/escreve a
# linha DISABLE_SIGNUP; a anon key usada no pós-check é lida dentro do servidor
# e nunca sai dele.
# =============================================================================
set -euo pipefail
SSH=(ssh -i "$HOME/.ssh/volc_hetzner_claude_ed25519" -o BatchMode=yes -o ConnectTimeout=10 root@178.156.196.149)
DIR=/root/supabase/docker
CARIMBO="$(date +%Y%m%d-%H%M%S)"

checar() { # só leitura: flags, mapeamento no compose, o que o GoTrue anuncia
  "${SSH[@]}" "cd $DIR && grep -oE '^(DISABLE_SIGNUP|ENABLE_EMAIL_SIGNUP|ENABLE_EMAIL_AUTOCONFIRM|ENABLE_PHONE_SIGNUP|ENABLE_PHONE_AUTOCONFIRM)=(true|false)' .env;
    echo '-- compose:'; grep -nE 'GOTRUE_DISABLE_SIGNUP|GOTRUE_EXTERNAL_PHONE_ENABLED|GOTRUE_SMS_AUTOCONFIRM' docker-compose.yml;
    echo '-- container auth:'; docker ps --filter name=supabase-auth --format '{{.Names}} {{.Status}}';
    echo '-- /auth/v1/settings (o que o GoTrue anuncia):';
    K=\$(grep -E '^ANON_KEY=' .env | cut -d= -f2-);
    curl -s -m 10 -H \"apikey: \$K\" http://localhost:8000/auth/v1/settings \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(\"disable_signup=\", d.get(\"disable_signup\"), \"| email=\", d.get(\"external\",{}).get(\"email\"), \"| phone=\", d.get(\"external\",{}).get(\"phone\"), \"| autoconfirm=\", d.get(\"mailer_autoconfirm\"), d.get(\"phone_autoconfirm\"))'"
}

poscheck_fechado() { # prova sem criar conta: settings diz fechado E um signup é recusado
  "${SSH[@]}" "cd $DIR && K=\$(grep -E '^ANON_KEY=' .env | cut -d= -f2-);
    s=\$(curl -s -m 10 -H \"apikey: \$K\" http://localhost:8000/auth/v1/settings | python3 -c 'import json,sys; print(json.load(sys.stdin).get(\"disable_signup\"))');
    echo \"disable_signup=\$s\";
    # Só tenta o cadastro se o GoTrue JÁ anuncia fechado: com cadastro aberto a
    # tentativa criaria conta, e isso aqui nunca pode criar conta.
    [ \"\$s\" = True ] || { echo 'NAO FECHADO: tentativa de cadastro NÃO executada'; exit 1; };
    for corpo in '{\"email\":\"w4-poscheck@example.invalid\",\"password\":\"x-poscheck-123456\"}' '{\"phone\":\"+5500000000000\",\"password\":\"x-poscheck-123456\"}'; do
      c=\$(curl -s -o /tmp/w4-signup.json -w '%{http_code}' -m 10 -H \"apikey: \$K\" -H 'Content-Type: application/json' -d \"\$corpo\" http://localhost:8000/auth/v1/signup);
      echo \"signup -> HTTP \$c \$(python3 -c 'import json; d=json.load(open(\"/tmp/w4-signup.json\")); print(d.get(\"error_code\") or d.get(\"msg\") or d.get(\"message\") or \"?\")' 2>/dev/null)\";
      rm -f /tmp/w4-signup.json; [ \"\$c\" = 422 ] || [ \"\$c\" = 403 ] || [ \"\$c\" = 400 ] || { echo 'ALERTA: signup não recusado'; exit 1; };
    done;
    docker exec -i supabase-db psql -U postgres -d postgres -X -A -t -c \"select 'contas de poscheck criadas: ' || count(*) from auth.users where email = 'w4-poscheck@example.invalid' or phone = '5500000000000'\""
}

trocar() { # trocar <de> <para>
  "${SSH[@]}" "cd $DIR && cp -p .env .env.bak-w4-signup-$CARIMBO && chmod 600 .env.bak-w4-signup-$CARIMBO &&
    grep -qx 'DISABLE_SIGNUP=$1' .env && sed -i 's/^DISABLE_SIGNUP=$1\$/DISABLE_SIGNUP=$2/' .env &&
    grep -x 'DISABLE_SIGNUP=$2' .env && docker compose up -d --no-deps auth &&
    for i in \$(seq 1 30); do docker ps --filter name=supabase-auth --format '{{.Status}}' | grep -q healthy && break; sleep 2; done;
    docker ps --filter name=supabase-auth --format '{{.Names}} {{.Status}}'; echo 'backup do .env: $DIR/.env.bak-w4-signup-$CARIMBO'"
}

case "${1:-}" in
  --checar) checar ;;
  --aplicar)
    [[ "${VOLC_AUTORIZA_GOTRUE:-}" == fechar-cadastro ]] || { echo "recusado: falta VOLC_AUTORIZA_GOTRUE=fechar-cadastro"; exit 16; }
    checar; trocar false true; sleep 3; poscheck_fechado ;;
  --reverter)
    [[ "${VOLC_AUTORIZA_GOTRUE:-}" == reabrir-cadastro ]] || { echo "recusado: falta VOLC_AUTORIZA_GOTRUE=reabrir-cadastro"; exit 16; }
    trocar true false; sleep 3; checar ;;
  *) sed -n 2,30p "$0"; exit 2 ;;
esac
