#!/usr/bin/env bash
# Motor shadow da carteira (W13): um experimento conferido por campanha, por conta.
# Lê google_ads_campanha_dia e receita_as_of pelo PostgREST (só leitura) e grava
# em $VOLC_SOMBRA_DESTINO. Não fala com o Google Ads e não executa nada.
#
# Saídas: 0 ok · 1 alguma conta falhou · 64 configuração inválida
#         65 agenda desligada (VOLC_SOMBRA_HABILITADA != sim) · 75 outra execução em curso
set -euo pipefail

ROOT="${VOLC_SOMBRA_RAIZ:-/opt/volc-sombra-carteira}"
LOCK="${VOLC_SOMBRA_LOCK:-/run/lock/volc-sombra-carteira.lock}"

# Trava dupla: a unit não está instalada E, mesmo instalada, só roda com o "sim"
# explícito no arquivo de configuração. Ligar é decisão do dono.
if [ "${VOLC_SOMBRA_HABILITADA:-nao}" != "sim" ]; then
  echo "agenda da sombra desligada (VOLC_SOMBRA_HABILITADA=${VOLC_SOMBRA_HABILITADA:-nao}); nada lido" >&2
  exit 65
fi

# Nunca como root: a unit roda como volc-sombra. O escape existe só para o
# teste hermético, que roda como root no contêiner; a unit não o define.
if [ "$(id -u)" = "0" ] && [ "${VOLC_SOMBRA_TESTE_PERMITE_ROOT:-}" != "1" ]; then
  echo "run.sh não roda como root; use o usuário de serviço volc-sombra" >&2
  exit 64
fi

# Só a service_role do .env do Supabase. Se aparecer qualquer outra chave
# dele, alguém apontou o EnvironmentFile para o arquivo inteiro: recusa.
for vazado in JWT_SECRET POSTGRES_PASSWORD DASHBOARD_PASSWORD DASHBOARD_USERNAME ANON_KEY \
              SECRET_KEY_BASE VAULT_ENC_KEY LOGFLARE_API_KEY SMTP_PASS; do
  if [ -n "${!vazado:-}" ]; then
    echo "$vazado no ambiente: o EnvironmentFile deve ter só SERVICE_ROLE_KEY, não o .env inteiro" >&2
    exit 64
  fi
done

CONTAS="${VOLC_SOMBRA_CONTAS:-}"
DESTINO="${VOLC_SOMBRA_DESTINO:-/var/lib/volc-sombra-carteira/experimentos}"
BASE_REF="$(cat "$ROOT/current/.base_ref" 2>/dev/null || true)"
if [ -z "${CONTAS// /}" ]; then echo "VOLC_SOMBRA_CONTAS vazia" >&2; exit 64; fi
if ! [[ "$BASE_REF" =~ ^[0-9a-f]{7,40}$ ]]; then
  echo "$ROOT/current/.base_ref ausente ou inválido: o experimento precisa do commit do código" >&2
  exit 64
fi

# Parâmetros do laboratório que a configuração pode sobrescrever (vazios = padrão do código).
PARAMS=()
for par in JANELA_DIAS:--janela-dias DIAS_IMATUROS:--dias-imaturos \
           MIN_CLIQUES_MADUROS:--min-cliques-maduros MAX_CUSTO_SEM_RECEITA:--max-custo-sem-receita \
           MAX_DEFASAGEM_CAMBIO_DIAS:--max-defasagem-cambio-dias; do
  var="VOLC_SOMBRA_${par%%:*}"; flag="${par##*:}"
  val="${!var:-}"
  if [ -n "$val" ]; then
    if ! [[ "$val" =~ ^[0-9]+([.][0-9]+)?$ ]]; then echo "$var inválido: $val" >&2; exit 64; fi
    PARAMS+=("$flag" "$val")
  fi
done

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "sombra da carteira já em execução; esta invocação não concorre" >&2
  exit 75
fi

export SUPABASE_URL="https://database.agenciavolc.com.br"
export SUPABASE_SERVICE_ROLE_KEY="${SERVICE_ROLE_KEY:?SERVICE_ROLE_KEY ausente no ambiente}"
unset SERVICE_ROLE_KEY
export PYTHONPATH="$ROOT/current/tools/freedom-lab/src"
mkdir -p "$DESTINO"

falhou=0
for conta in $CONTAS; do
  # Uma conta que falha não impede as outras, mas a execução sai 1.
  if ! "$ROOT/venv/bin/python" -m volc_lab.sombra_carteira gerar \
        --conta "$conta" --postgrest --destino "$DESTINO" --base-ref "$BASE_REF" "${PARAMS[@]}"; then
    echo "sombra da conta ${conta:0:3}****${conta: -3} falhou" >&2
    falhou=1
  fi
done
exit "$falhou"
