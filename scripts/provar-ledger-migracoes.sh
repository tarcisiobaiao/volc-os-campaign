#!/usr/bin/env bash
# provar-ledger-migracoes.sh — o ledger (v20_01) e a linha de base (v20_02) num
# Postgres descartável, pelo protocolo. Nada sai do container; nada de produção.
#
#   A. v20_01 cria volc_ops sem mudar o fingerprint de public+app_auth, fechado a
#      anon/authenticated/service_role; fingerprint_schema() = fingerprint_schema.sql
#   B. v20_02 ORIGINAL recusa (o laboratório não é a produção 695e913a…) e sem
#      aprovador recusa; uma cópia com o fingerprint do laboratório registra a
#      linha de base sem reaplicar nada; os sha256 embutidos batem com os arquivos
#   C. reaplicação recusada; log append-only
#   D. rollback da v20_02 (recusa hash divergente) → reaplicar → reverter
#   E. rollback da v20_01 devolve o fingerprint de antes; reaplicar
#   F. com outra migration registrada, o rollback do ledger é recusado
#   G. dois aplicadores simultâneos da mesma versão: exatamente um vence
#
# Uso: VOLC_LAB_PREFIXO=volc-lab-w9- [VOLC_PG_IMAGE=supabase/postgres:15.8.1.085] scripts/provar-ledger-migracoes.sh
set -uo pipefail
export LC_ALL=C LANG=C
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROTO="$RAIZ/scripts/migracao-protocolo.sh"
M="$RAIZ/supabase/migrations"
FPSQL="$RAIZ/tools/freedom-lab/db/fingerprint_schema.sql"
L1="$M/v20_01_ledger_migrations.sql";    R1="$M/v20_01_rollback.sql"
L2="$M/v20_02_ledger_linha_de_base.sql"; R2="$M/v20_02_rollback.sql"

# shellcheck source=lab-postgres-descartavel.sh
. "$RAIZ/scripts/lab-postgres-descartavel.sh" ledger
lab_criar
echo "▶ servidor $(P -c 'show server_version') · imagem $LAB_IMG · container $LAB_CN"
lab_papeis_supabase

sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
REC="$LAB_DIR/recibos"; mkdir -p "$REC"
proto() { "$PROTO" "$@" --alvo "docker:$LAB_CN" --recibo-dir "$REC" >"$LAB_DIR/proto.out" 2>&1; echo $?; }
fp_bruto() { P < "$FPSQL" | grep '^_TOTAL|' | cut -d'|' -f3; }
fp_tudo_bruto() { P < "$FPSQL" | grep '|' | sort; }
fp_tudo_funcao() { P -c "select categoria||'|'||itens||'|'||md5 from volc_ops.fingerprint_schema()" | sort; }
eventos() { P -c "select count(*) from volc_ops.migracao_evento"; }

echo "▶ semear: um public sintético com cada categoria do fingerprint"
P >/dev/null <<'SQL'
CREATE SCHEMA app_auth;
CREATE TABLE public.campanha_sintetica (id int PRIMARY KEY, nome text NOT NULL DEFAULT 'x', custo numeric CHECK (custo >= 0));
CREATE INDEX ON public.campanha_sintetica (nome);
ALTER TABLE public.campanha_sintetica ENABLE ROW LEVEL SECURITY;
CREATE POLICY le ON public.campanha_sintetica FOR SELECT TO authenticated USING (true);
CREATE VIEW public.vw_campanha_sintetica WITH (security_invoker = true) AS SELECT id, nome FROM public.campanha_sintetica;
CREATE FUNCTION public.fn_sintetica() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN RETURN NEW; END $f$;
CREATE TRIGGER tg_sintetico BEFORE INSERT ON public.campanha_sintetica FOR EACH ROW EXECUTE FUNCTION public.fn_sintetica();
CREATE TABLE app_auth.papel_sintetico (id int);
INSERT INTO public.campanha_sintetica VALUES (1, 'a', 10);
SQL
FP_BASE="$(fp_bruto)"
echo "  fingerprint do laboratório antes do ledger: $FP_BASE"

echo "▶ A · v20_01 cria o ledger"
eq "$(proto aplicar --migration "$L1" --sha "$(sha "$L1")" --rollback "$R1" --sha-rollback "$(sha "$R1")" --aprovador laboratorio --cria-ledger)" 0 "v20_01 aplicada pelo protocolo"
eq "$(fp_bruto)" "$FP_BASE" "fingerprint de public+app_auth INALTERADO pelo ledger (a âncora segue válida)"
eq "$(fp_tudo_funcao)" "$(fp_tudo_bruto)" "volc_ops.fingerprint_schema() = fingerprint_schema.sql, categoria a categoria"
eq "$(proto aplicar --migration "$L1" --sha "$(sha "$L1")" --aprovador laboratorio --cria-ledger)" 11 "criar o ledger de novo pelo protocolo → 11"
eq "$(P < "$L1" >/dev/null 2>&1; echo $?)" 3 "v20_01 rodada à mão de novo aborta (schema já existe)"
for r in anon authenticated service_role; do
  eq "$(P -c "select has_schema_privilege('$r','volc_ops','USAGE')")" f "$r sem USAGE em volc_ops"
  eq "$(lab_sqlstate "SET ROLE $r; SELECT volc_ops.fingerprint_schema()")" 42501 "$r não executa fingerprint_schema()"
done

echo "▶ B · linha de base (v20_02)"
eq "$(proto aplicar --migration "$L2" --sha "$(sha "$L2")" --aprovador laboratorio)" 14 "v20_02 ORIGINAL recusa: o laboratório não tem o fingerprint 695e913a de produção"
grep -q 'o schema mudou desde a medição' "$REC"/RECEIPT-v20_02_ledger_linha_de_base-aplicar-*.txt \
  && ok "o motivo da recusa é o fingerprint, não outro erro" || nao "motivo da recusa"
eq "$(eventos)" 0 "nenhum evento registrado pela tentativa recusada"
mkdir -p "$LAB_DIR/lab"; LAB2="$LAB_DIR/lab/v20_02_ledger_linha_de_base.sql"
sed "s/695e913a4373efd1c2265cdd5ac87251/$FP_BASE/" "$L2" > "$LAB2"
eq "$(lab_sqlstate "$(cat "$LAB2")")" P0001 "cópia do laboratório rodada sem o protocolo (sem aprovador) recusa"
eq "$(proto aplicar --migration "$LAB2" --sha "$(sha "$LAB2")" --rollback "$R2" --sha-rollback "$(sha "$R2")" --aprovador laboratorio --aprovado-em 2026-10-15)" 0 \
   "cópia com o fingerprint do laboratório registra a linha de base"; cat "$LAB_DIR/proto.out" | tail -8
eq "$(P -c "select string_agg(versao||':'||operacao, ',' order by id) from volc_ops.migracao_evento")" \
   "v20_02_ledger_linha_de_base:aplicar,linha_de_base_producao_20261015:linha_de_base,v20_01_ledger_migrations:aplicar" \
   "ledger: v20_02 aplicada, linha de base, v20_01 retroativa"
eq "$(P -c "select fingerprint from volc_ops.migracao_evento where operacao='linha_de_base'")" "$FP_BASE" "linha de base ancorada no fingerprint medido"
eq "$(P -c "select aprovador||'|'||aprovado_em from volc_ops.migracao_evento where versao='v20_01_ledger_migrations'")" "laboratorio|2026-10-15" "aprovador e data vêm do protocolo"
eq "$(fp_bruto)" "$FP_BASE" "nada reaplicado: fingerprint de public+app_auth intacto"
eq "$(P -c "select count(*) from public.campanha_sintetica")" 1 "dado de negócio intacto"
# os sha256 embutidos na v20_02 são os dos arquivos versionados
for f in "$L1" "$R1" "$FPSQL"; do
  grep -q "$(sha "$f")" "$L2" && ok "v20_02 cita o sha256 atual de $(basename "$f")" || nao "v20_02 cita sha256 defasado de $(basename "$f")"
done

echo "▶ C · reaplicação recusada e log append-only"
eq "$(proto aplicar --migration "$LAB2" --sha "$(sha "$LAB2")" --aprovador laboratorio)" 11 "reaplicar v20_02 → 11"
eq "$(lab_sqlstate "BEGIN; SELECT set_config('volc_ops.aprovador','x',true); $(sed '/^BEGIN;/d;/^COMMIT;/d' "$LAB2"); COMMIT;")" P0001 \
   "v20_02 rodada à mão de novo: o banco recusa a 2ª linha de base"
eq "$(lab_sqlstate "UPDATE volc_ops.migracao_evento SET fingerprint=NULL")" P0001 "UPDATE recusado"
eq "$(lab_sqlstate "DELETE FROM volc_ops.migracao_evento WHERE operacao='linha_de_base'")" P0001 "DELETE da linha de base recusado"

echo "▶ D · rollback da v20_02"
mkdir -p "$LAB_DIR/div"; cp "$R2" "$LAB_DIR/div/"; echo '-- alterado' >> "$LAB_DIR/div/$(basename "$R2")"
eq "$(proto reverter --versao v20_02_ledger_linha_de_base --rollback "$LAB_DIR/div/$(basename "$R2")" --sha-rollback "$(sha "$LAB_DIR/div/$(basename "$R2")")" --aprovador laboratorio)" 10 \
   "rollback divergente do aprovado → 10"
eq "$(proto reverter --versao v20_02_ledger_linha_de_base --rollback "$R2" --sha-rollback "$(sha "$R2")" --aprovador laboratorio)" 0 "v20_02 revertida"
eq "$(P -c "select count(*) from volc_ops.migracao_evento where versao in ('linha_de_base_producao_20261015','v20_01_ledger_migrations')")" 0 "linha de base removida"
eq "$(P -c "select count(*) from pg_trigger where tgname='migracao_evento_guarda' and tgenabled='O'")" 1 "guarda append-only religada depois do rollback"
eq "$(proto aplicar --migration "$LAB2" --sha "$(sha "$LAB2")" --rollback "$R2" --sha-rollback "$(sha "$R2")" --aprovador laboratorio)" 0 "v20_02 reaplicada após rollback"
eq "$(proto reverter --versao v20_02_ledger_linha_de_base --rollback "$R2" --sha-rollback "$(sha "$R2")" --aprovador laboratorio)" 0 "v20_02 revertida de novo"

echo "▶ E · rollback da v20_01"
eq "$(proto reverter --versao v20_01_ledger_migrations --rollback "$R1" --sha-rollback "$(sha "$R1")" --aprovador laboratorio --remove-ledger)" 0 "v20_01 revertida"
eq "$(P -c "select to_regnamespace('volc_ops') is null")" t "volc_ops removido"
eq "$(fp_bruto)" "$FP_BASE" "fingerprint igual ao de antes do ledger"
eq "$(P < "$R1" >/dev/null 2>&1; echo $?)" 0 "rollback da v20_01 idempotente (sem ledger, não faz nada)"
eq "$(P < "$R2" >/dev/null 2>&1; echo $?)" 0 "rollback da v20_02 idempotente (sem ledger, não faz nada)"
eq "$(proto aplicar --migration "$L1" --sha "$(sha "$L1")" --aprovador laboratorio --cria-ledger)" 0 "v20_01 reaplicada"
eq "$(fp_bruto)" "$FP_BASE" "fingerprint ainda intacto"

echo "▶ F · ledger com história não se apaga"
X="$LAB_DIR/lab/v99_01_sintetica.sql"; XR="$LAB_DIR/lab/v99_01_rollback.sql"
printf 'BEGIN;\nCREATE TABLE public.tabela_sintetica_99 (i int);\nCOMMIT;\n' > "$X"
printf 'BEGIN;\nDROP TABLE IF EXISTS public.tabela_sintetica_99;\nCOMMIT;\n' > "$XR"
eq "$(proto aplicar --migration "$X" --sha "$(sha "$X")" --rollback "$XR" --sha-rollback "$(sha "$XR")" --aprovador laboratorio)" 0 "migration sintética registrada"
eq "$(proto reverter --versao v20_01_ledger_migrations --rollback "$R1" --sha-rollback "$(sha "$R1")" --aprovador laboratorio --remove-ledger)" 14 "rollback do ledger recusado (há história de outra migration)"
eq "$(P -c "select count(*) from volc_ops.migracao_evento where versao='v99_01_sintetica'")" 1 "história preservada"

echo "▶ G · dois aplicadores simultâneos"
Y="$LAB_DIR/lab/v99_02_lenta.sql"
printf 'BEGIN;\nSELECT pg_sleep(2);\nCREATE TABLE public.tabela_sintetica_lenta (i int);\nCOMMIT;\n' > "$Y"
( "$PROTO" aplicar --alvo "docker:$LAB_CN" --recibo-dir "$REC" --migration "$Y" --sha "$(sha "$Y")" --aprovador a >/dev/null 2>&1; echo $? > "$LAB_DIR/c1" ) &
( "$PROTO" aplicar --alvo "docker:$LAB_CN" --recibo-dir "$REC" --migration "$Y" --sha "$(sha "$Y")" --aprovador b >/dev/null 2>&1; echo $? > "$LAB_DIR/c2" ) &
wait
CODS="$(sort "$LAB_DIR/c1" "$LAB_DIR/c2" | tr '\n' ' ')"
case "$CODS" in "0 11 "|"0 14 ") ok "exatamente um venceu (saídas: $CODS)";; *) nao "corrida: saídas $CODS";; esac
eq "$(P -c "select count(*) from volc_ops.migracao_evento where versao='v99_02_lenta'")" 1 "um único evento de aplicação"

echo
if [ "$FALHAS" = 0 ]; then echo "  LEDGER VERDE — $(P -c 'show server_version')"; exit 0
else echo "  $FALHAS FALHA(S) no ledger"; exit 1; fi
