#!/usr/bin/env bash
# Coleta recorrente Google Ads → ledger v12_04/v17_01, pela RPC. Read-only no Google.
#
#   run.sh d0        passada intradia (passo = hora de São Paulo)
#   run.sh d1        dia de ontem, uma vez (passo 06)
#   run.sh recoleta  relê os N dias fechados antes do D-1 como backfill
#                    (VOLC_GADS_RECOLETA_DIAS, padrão 7), só o fato campanha-dia
#
# Contas: VOLC_GADS_CONTAS="5478096539,1234567890" (ou VOLC_GADS_CONTA, uma só),
# todas sob o mesmo VOLC_GADS_MCC. Uma conta que falha não impede as outras;
# a saída é 1 se qualquer uma falhou.
set -euo pipefail

MODE="${1:-}"
case "$MODE" in d0|d1|recoleta) ;; *) echo "modo invalido: use d0, d1 ou recoleta" >&2; exit 64 ;; esac

# Os caminhos aceitam override só para o teste hermético do contrato de invocação.
ROOT="${VOLC_GADS_ROOT:-/opt/volc-gads-coleta}"
LOCK="${VOLC_GADS_LOCK:-/run/lock/volc-gads-coleta.lock}"
RECIBOS="${VOLC_GADS_RECIBOS:-/var/lib/volc-gads-coleta/recibos}"
CONTAS="${VOLC_GADS_CONTAS:-${VOLC_GADS_CONTA:?defina VOLC_GADS_CONTAS ou VOLC_GADS_CONTA}}"
MCC="${VOLC_GADS_MCC:?defina VOLC_GADS_MCC}"
DIAS="${VOLC_GADS_RECOLETA_DIAS:-7}"

# Só a recoleta lê DIAS: um valor torto aqui não pode derrubar D0 e D-1.
if [ "$MODE" = recoleta ]; then
  case "$DIAS" in ''|*[!0-9]*) echo "VOLC_GADS_RECOLETA_DIAS invalido: $DIAS" >&2; exit 64 ;; esac
  if [ "$((10#$DIAS))" -lt 1 ] || [ "$((10#$DIAS))" -gt 90 ]; then
    echo "VOLC_GADS_RECOLETA_DIAS fora de 1..90: $DIAS" >&2; exit 64
  fi
fi

# Dono único: uma execução por vez, qualquer modo. D0/D-1 concorrentes saem 75
# sem ler nada (a próxima passada cobre). A recoleta ESPERA até 30 min e, se
# ainda assim não pegar a vez, sai 1: 75 conta como sucesso na unit e o dia
# ficaria sem maturação em silêncio.
exec 9>"$LOCK"
if [ "$MODE" = recoleta ]; then
  if ! flock -w "${VOLC_GADS_RECOLETA_ESPERA_S:-1800}" 9; then
    echo "recoleta nao conseguiu a vez em ${VOLC_GADS_RECOLETA_ESPERA_S:-1800}s; FALHOU" >&2
    exit 1
  fi
elif ! flock -n 9; then
  echo "coleta ja esta em execucao; esta invocacao nao concorre" >&2
  exit 75
fi

# Passo da agenda no fuso da conta (v12_04: 06/12/18/23 em D0; D-1 roda uma vez).
# Na recoleta a janela muda todo dia, então o passo fixo `rec` só impede a
# repetição dentro do mesmo dia (catch-up do timer, disparo manual).
case "$MODE" in
  d0)       JANELA=(--origem D0 --agenda "$(TZ=America/Sao_Paulo date +%H)") ;;
  d1)       JANELA=(--origem D-1 --agenda 06) ;;
  recoleta) JANELA=(--recoleta-dias "$DIAS" --agenda rec) ;;
esac

export HOME="$ROOT"
export GOOGLE_ADS_CONFIGURATION_FILE_PATH="$ROOT/google-ads.yaml"
export SUPABASE_URL="https://database.agenciavolc.com.br"
export SUPABASE_SERVICE_ROLE_KEY="$SERVICE_ROLE_KEY"
unset FORGE_PERMITIR_ESCRITA
export PYTHONPATH="$ROOT/current:$ROOT/current/backend"

mkdir -p "$RECIBOS"
SAIDA=0
TENTADAS=0
IFS=',' read -r -a LISTA <<< "$CONTAS"
# `${LISTA[@]+...}`: bash 3.2 (macOS) com `set -u` trata array vazio como não definido.
for CONTA in ${LISTA[@]+"${LISTA[@]}"}; do
  CONTA="${CONTA//[[:space:]]/}"
  [ -n "$CONTA" ] || continue
  TENTADAS=$((TENTADAS + 1))
  case "$CONTA" in *[!0-9]*) echo "conta invalida: $CONTA" >&2; SAIDA=1; continue ;; esac
  if ! "$ROOT/venv/bin/python" -m volc_ads.coleta \
      --conta "$CONTA" --mcc "$MCC" "${JANELA[@]}" \
      --recibo "$RECIBOS/$(date -u +%Y%m%dT%H%M%SZ)-$MODE-$CONTA.json"; then
    echo "conta $CONTA: coleta $MODE falhou" >&2
    SAIDA=1
  fi
done
# Lista de contas vazia (",", espaços) não é "coletei nada": é configuração errada.
if [ "$TENTADAS" -eq 0 ]; then echo "nenhuma conta em VOLC_GADS_CONTAS: $CONTAS" >&2; exit 64; fi
exit "$SAIDA"
