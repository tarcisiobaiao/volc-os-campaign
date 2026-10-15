#!/usr/bin/env python3
"""Liga os recibos do pacote do incidente anon (W4) ao ledger de migrations (v20).

O pacote v19 roda ANTES e FORA do ledger (superusuário, transação por arquivo, por
scripts/aplicar-incidente-anon-w4.sh) e grava RECEIPT-<carimbo>.json. Este script
transforma esses recibos em SQL do ledger:

  v20_02  RECEIPT-passo1.json  →  supabase/migrations/v20_02_ledger_linha_de_base_pos_v19.sql
          (arquivo NOVO; nunca sobrescreve um existente nem um versionado)
  importar RECEIPT-passo2.json | RECEIPT-rollback.json  →  --saida ARQ (novo)

O RECIBO NÃO PROVA A SI MESMO. O campo `alvo` não é critério de confiança. A SQL
gerada mede o banco onde roda e recusa (P0001, nada gravado) se:
  · volc_ops.fingerprint_schema() ≠ fingerprint_depois do recibo;
  · o efeito da operação não está lá (passo 1: anon sem SELECT em public.users e
    app_auth.w4_acl existe; passo 2: authenticated sem SELECT em
    public.users.password_hash; rollback: anon voltou a ler public.users);
  · não há aprovador do protocolo (volc_ops.aprovador) na transação.
Um recibo forjado para um banco sem a v19 falha ao aplicar, mesmo com o sha certo.

NENHUM TEXTO DO RECIBO VIRA SQL OU COMENTÁRIO SEM PASSAR POR FORMATO ESTRITO: cada
campo tem expressão regular de ponta a ponta (\\A…\\Z, sem quebra de linha, sem $, sem
aspas, sem barra invertida), e entra por literal(), a única fábrica de literal, que
recusa de novo qualquer caractere fora do alfabeto permitido. O SQL fixa
standard_conforming_strings = on e deve rodar com ON_ERROR_STOP=1.

Composição do pacote é fixa (a mesma de sha_esperado do script do W4): passo 1 são
exatamente v19_00, v8_03, v19_01, v8_05, v19_02, nessa ordem; passo 2 é v8_06;
rollback são as 6 versões revertidas pelo v19_99. sha256 de cada arquivo = repositório.

Uso:
  ledger_recibo_incidente.py v20_02   RECEIPT.json [--saida ARQ]
  ledger_recibo_incidente.py importar RECEIPT.json  --saida ARQ
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MIGR = "supabase/migrations"
FP_SQL = "tools/freedom-lab/db/fingerprint_schema.sql"
V20_01 = f"{MIGR}/v20_01_ledger_migrations.sql"
V20_01_ROLL = f"{MIGR}/v20_01_rollback.sql"
V19_99 = f"{MIGR}/v19_99_rollback.sql"
SAIDA_V20_02 = f"{MIGR}/v20_02_ledger_linha_de_base_pos_v19.sql"
ANCORA_PRE_V19 = "695e913a4373efd1c2265cdd5ac87251"  # produção, 15/10 ~10:55Z (fingerprint-prod.out)
EVID_PROD = "fingerprint-prod.out sha256 fbd623d78b4d21267251599fa8d80855c33dd80cc0e176b29c69d6212b77d170, medido em producao antes da v19"

PASSO1 = ["v19_00_users_gatilho_papel_real", "v8_03_users_rls_policies", "v19_01_anon_fecha_public",
          "v8_05_users_safe_view", "v19_02_default_acl_public_sem_anon"]
PASSO2 = ["v8_06_users_sensitive_columns_revoke"]
REVERTIDAS = ["v8_06_users_sensitive_columns_revoke", "v19_02_default_acl_public_sem_anon", "v8_05_users_safe_view",
              "v19_01_anon_fecha_public", "v8_03_users_rls_policies", "v19_00_users_gatilho_papel_real"]

# Efeito de CADA migration que tem de estar no banco para o recibo valer (SQL fixa,
# nunca vinda do recibo). Aplicação parcial do pacote falha na primeira ausente.
_DEF_ACL_ANON = ("EXISTS (SELECT 1 FROM pg_default_acl d JOIN pg_namespace ns ON ns.oid = d.defaclnamespace, "
                 "aclexplode(d.defaclacl) a WHERE ns.nspname = 'public' AND d.defaclobjtype = 'r' "
                 "AND a.grantee = 'anon'::regrole)")
EFEITO = {
    "--passo1": [
        ("v19_00_users_gatilho_papel_real",
         "coalesce((SELECT prosrc FROM pg_proc WHERE oid = to_regprocedure('app_auth.tg_users_guard_privileged_columns()')), '') "
         "LIKE '%current_setting(''role'', true)%'",
         "o gatilho de users não lê o papel real (v19_00 ausente)"),
        ("v8_03_users_rls_policies",
         "coalesce((SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass('public.users')), false)",
         "public.users sem RLS (v8_03 ausente)"),
        ("v19_01_anon_fecha_public",
         "NOT has_table_privilege('anon', 'public.users', 'SELECT') AND to_regclass('app_auth.w4_acl') IS NOT NULL",
         "anon ainda lê public.users ou app_auth.w4_acl não existe (v19_01 ausente)"),
        ("v8_05_users_safe_view", "to_regclass('public.users_safe') IS NOT NULL",
         "public.users_safe não existe (v8_05 ausente)"),
        ("v19_02_default_acl_public_sem_anon", f"NOT {_DEF_ACL_ANON}",
         "default ACL de public ainda concede a anon (v19_02 ausente)"),
    ],
    "--passo2": [("v8_06_users_sensitive_columns_revoke",
                  "NOT has_column_privilege('authenticated', 'public.users', 'password_hash', 'SELECT')",
                  "authenticated ainda lê public.users.password_hash (v8_06 ausente)")],
    "--rollback": [("v19_99_rollback", "has_table_privilege('anon', 'public.users', 'SELECT')",
                    "anon não lê public.users (rollback v19_99 ausente)")],
}

FORMATO = {
    "md5": re.compile(r"\A[0-9a-f]{32}\Z"),
    "sha": re.compile(r"\A[0-9a-f]{64}\Z"),
    "versao": re.compile(r"\A[A-Za-z0-9_.-]{3,120}\Z"),
    "arquivo": re.compile(r"\Asupabase/migrations/[A-Za-z0-9_.-]{3,120}\.sql\Z"),
    "instante": re.compile(r"\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z"),
    "data": re.compile(r"\A\d{4}-\d\d-\d\d\Z"),
    "carimbo": re.compile(r"\A\d{8}-\d{6}\Z"),
    "alvo": re.compile(r"\A(producao|volc-[a-z0-9-]{3,60})\Z"),
    "executor": re.compile(r"\A[a-z_]{3,40}@[A-Za-z0-9.-]{1,63}\Z"),
    "aprovador": re.compile(r"\A[A-Za-z0-9._-](?:[A-Za-z0-9 ._-]{0,78}[A-Za-z0-9._-])?\Z"),
}
ALFABETO_LITERAL = re.compile(r"\A[A-Za-z0-9 ._:@/|=,()+-]*\Z")


class ReciboInvalido(ValueError):
    pass


def sha_arquivo(rel: str) -> str:
    return hashlib.sha256((RAIZ / rel).read_bytes()).hexdigest()


def literal(valor: str | None) -> str:
    """ÚNICA fábrica de literal SQL. Só aceita texto já validado por formato estrito."""
    if valor is None:
        return "NULL"
    if not isinstance(valor, str) or not ALFABETO_LITERAL.match(valor):
        raise ReciboInvalido("valor fora do alfabeto permitido para literal SQL")
    return "'" + valor + "'"


def campo(d: dict, chave: str, formato: str, onde: str = "recibo") -> str:
    v = d.get(chave)
    if not isinstance(v, str) or not FORMATO[formato].match(v):
        raise ReciboInvalido(f"{onde}.{chave}: formato inválido ({formato})")
    return v


def carregar(caminho: Path, operacao: str) -> tuple[dict, str]:
    bruto = caminho.read_bytes()
    try:
        r = json.loads(bruto, parse_constant=lambda c: (_ for _ in ()).throw(ReciboInvalido(c)))
    except json.JSONDecodeError as e:
        raise ReciboInvalido(f"JSON inválido: {e.msg}") from None
    if not isinstance(r, dict):
        raise ReciboInvalido("recibo não é objeto")
    if r.get("pacote") != "incidente-anon-w4":
        raise ReciboInvalido("pacote")
    if r.get("operacao") != operacao:
        raise ReciboInvalido(f"operacao (esperado {operacao})")
    if r.get("resultado") != "ok":
        raise ReciboInvalido("resultado")
    campo(r, "alvo", "alvo")
    campo(r, "carimbo", "carimbo")
    if r.get("fingerprint_sql") != FP_SQL:
        raise ReciboInvalido("fingerprint_sql: caminho diferente da SQL do repositório")
    if campo(r, "fingerprint_sql_sha256", "sha") != sha_arquivo(FP_SQL):
        raise ReciboInvalido("fingerprint_sql_sha256: outra SQL (âncora não comparável)")
    antes, depois = campo(r, "fingerprint_antes", "md5"), campo(r, "fingerprint_depois", "md5")
    if antes == depois:
        raise ReciboInvalido("fingerprint_antes = fingerprint_depois: a operação não mudou o schema")
    eventos = r.get("eventos")
    if not isinstance(eventos, list) or not eventos:
        raise ReciboInvalido("sem eventos")
    esperadas = {"--passo1": PASSO1, "--passo2": PASSO2, "--rollback": REVERTIDAS}[operacao]
    tipo = "reverter" if operacao == "--rollback" else "aplicar"
    if [e.get("versao") if isinstance(e, dict) else None for e in eventos] != esperadas:
        raise ReciboInvalido("composição do pacote diferente da esperada")
    for e in eventos:
        onde = f"evento {e['versao']}"
        campo(e, "versao", "versao", onde)
        if e.get("operacao") != tipo:
            raise ReciboInvalido(f"{onde}: operacao (esperado {tipo})")
        arq = campo(e, "arquivo", "arquivo", onde)
        alvo_arq = V19_99 if tipo == "reverter" else f"{MIGR}/{e['versao']}.sql"
        if arq != alvo_arq or not (RAIZ / arq).is_file():
            raise ReciboInvalido(f"{onde}: arquivo diferente do pacote")
        if campo(e, "sha256", "sha", onde) != sha_arquivo(arq):
            raise ReciboInvalido(f"{onde}: sha256 do recibo ≠ sha256 do arquivo no repositório")
        if tipo == "aplicar":
            if e.get("rollback_arquivo") != V19_99 or campo(e, "rollback_sha256", "sha", onde) != sha_arquivo(V19_99):
                raise ReciboInvalido(f"{onde}: rollback diferente do v19_99 do repositório")
        elif e.get("rollback_arquivo") is not None or e.get("rollback_sha256") is not None:
            raise ReciboInvalido(f"{onde}: reverter não leva par de rollback")
        campo(e, "aprovador", "aprovador", onde)
        campo(e, "executado_por", "executor", onde)
        campo(e, "inicio", "instante", onde)
        campo(e, "fim", "instante", onde)
        campo(e, "aprovado_em", "data", onde)
    return r, hashlib.sha256(bruto).hexdigest()


def _cabecalho_sql(r: dict, sha_rec: str) -> str:
    return f"""SET standard_conforming_strings = on;
BEGIN;
SET LOCAL standard_conforming_strings = on;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $volc_w4$
DECLARE
  recibo     constant text := {literal(sha_rec)};
  esperado   constant text := {literal(r['fingerprint_depois'])};
  medido     text;
  aprovador  text := nullif(btrim(current_setting('volc_ops.aprovador', true)), '');
  aprov_em   date := nullif(current_setting('volc_ops.aprovado_em', true), '')::date;
BEGIN
  IF current_setting('standard_conforming_strings') <> 'on' THEN
    RAISE EXCEPTION 'ledger W4: standard_conforming_strings precisa ser on' USING ERRCODE = 'P0001';
  END IF;
  IF to_regclass('volc_ops.migracao_evento') IS NULL THEN
    RAISE EXCEPTION 'ledger W4: ledger ausente — aplique v20_01 antes' USING ERRCODE = 'P0001';
  END IF;
  IF aprovador IS NULL THEN
    RAISE EXCEPTION 'ledger W4: sem aprovador (volc_ops.aprovador) — rode pelo protocolo' USING ERRCODE = 'P0001';
  END IF;
  SELECT f.md5 INTO medido FROM volc_ops.fingerprint_schema() f WHERE f.categoria = '_TOTAL';
  IF medido IS DISTINCT FROM esperado THEN
    RAISE EXCEPTION 'ledger W4: o banco mede %, o recibo % diz %: recibo não corresponde a este banco', medido, recibo, esperado
      USING ERRCODE = 'P0001';
  END IF;
{chr(10).join(f"  IF NOT ({cond}) THEN{chr(10)}    RAISE EXCEPTION 'ledger W4: {msg} (recibo %)', recibo USING ERRCODE = 'P0001';{chr(10)}  END IF;" for _v, cond, msg in EFEITO[r['operacao']])}
"""


def _evid(r: dict, sha_rec: str, e: dict) -> str:
    return literal(f"RECEIPT sha256 {sha_rec} carimbo {r['carimbo']} alvo {r['alvo']} executado_por {e['executado_por']} "
                   f"inicio {e['inicio']} fim {e['fim']} aprovador_no_recibo {e['aprovador']}")


def _insert(e: dict, operacao: str, fingerprint_sql: str, evid: str, rollback: bool) -> str:
    rb = (literal(V19_99), literal(sha_arquivo(V19_99))) if rollback else ("NULL", "NULL")
    return (f"  INSERT INTO volc_ops.migracao_evento\n"
            f"    (versao, operacao, arquivo, sha256, rollback_arquivo, rollback_sha256, aprovador, aprovado_em, fingerprint, evidencia)\n"
            f"  VALUES ({literal(e['versao'])}, {literal(operacao)}, {literal(e['arquivo'])}, {literal(e['sha256'])},\n"
            f"          {rb[0]}, {rb[1]}, aprovador, aprov_em, {fingerprint_sql}, {evid});")


def gerar_v20_02(caminho: Path, ancora_pre_v19: str = ANCORA_PRE_V19) -> str:
    r, sha_rec = carregar(caminho, "--passo1")
    if not FORMATO["md5"].match(ancora_pre_v19):
        raise ReciboInvalido("âncora pré-v19: formato inválido")
    if r["fingerprint_antes"] != ancora_pre_v19:
        raise ReciboInvalido(f"fingerprint_antes do recibo ≠ âncora pré-v19 {ancora_pre_v19}: houve DDL entre a "
                             "medição de produção e o passo 1 do W4 — remeça a âncora e registre essa DDL antes")
    linhas = []
    for i, e in enumerate(r["eventos"]):
        # fingerprint por evento só existe para o primeiro (estado anterior ao pacote); os
        # intermediários não foram medidos pelo script — NULL declarado, não inventado.
        fp = literal(r["fingerprint_antes"]) if i == 0 else "NULL"
        linhas.append(_insert(e, "aplicar", fp, _evid(r, sha_rec, e), rollback=True))
    return f"""-- v20_02_ledger_linha_de_base_pos_v19.sql — GERADA por scripts/ledger_recibo_incidente.py
-- a partir de um RECEIPT do passo 1 do W4 (sha256 na constante `recibo`). Não editar à mão.
-- Linha de base pré-v19 ({ancora_pre_v19}), backfill da v19 e registro da v20_01, numa
-- transação, só se o banco medir o fingerprint e o efeito que o recibo declara.
-- Rodar pelo protocolo (volc_ops.aprovador) e com ON_ERROR_STOP=1.
{_cabecalho_sql(r, sha_rec)}
  INSERT INTO volc_ops.migracao_evento
    (versao, operacao, arquivo, sha256, aprovador, aprovado_em, fingerprint, evidencia)
  VALUES ('linha_de_base_producao_20261015', 'linha_de_base', {literal(FP_SQL)}, {literal(sha_arquivo(FP_SQL))},
          aprovador, aprov_em, {literal(ancora_pre_v19)},
          {literal(EVID_PROD if ancora_pre_v19 == ANCORA_PRE_V19 else "ancora pre-v19 informada por --ancora-pre-v19 (laboratorio)")});

{chr(10).join(linhas)}

  INSERT INTO volc_ops.migracao_evento
    (versao, operacao, arquivo, sha256, rollback_arquivo, rollback_sha256, aprovador, aprovado_em, fingerprint, evidencia)
  VALUES ('v20_01_ledger_migrations', 'aplicar', {literal(V20_01)}, {literal(sha_arquivo(V20_01))},
          {literal(V20_01_ROLL)}, {literal(sha_arquivo(V20_01_ROLL))}, aprovador, aprov_em, medido,
          'registrada retroativamente (o ledger não existia antes de si mesmo)');
END $volc_w4$;

COMMIT;
"""


def gerar_importacao(caminho: Path) -> str:
    try:
        bruto = json.loads(caminho.read_bytes())
    except (OSError, ValueError):
        bruto = None
    operacao = bruto.get("operacao") if isinstance(bruto, dict) else None
    if operacao not in ("--passo2", "--rollback"):
        raise ReciboInvalido("operacao (importar aceita --passo2 ou --rollback)")
    r, sha_rec = carregar(caminho, operacao)
    reverter = operacao == "--rollback"
    corpo = []
    for e in r["eventos"]:
        # fingerprint = estado ANTES do ato (semântica da coluna em v20_01), vindo do recibo
        ins = _insert(e, "reverter" if reverter else "aplicar", literal(r["fingerprint_antes"]), _evid(r, sha_rec, e),
                      rollback=not reverter)
        if reverter:
            corpo.append(f"  IF EXISTS (SELECT 1 FROM volc_ops.migracao_estado WHERE versao = {literal(e['versao'])} AND estado = 'aplicada') THEN\n"
                         f"  {ins}\n    n := n + 1;\n  END IF;")
        else:
            corpo.append(ins + "\n  n := n + 1;")
    cab = _cabecalho_sql(r, sha_rec).replace("  medido     text;", "  medido     text;\n  n          int := 0;")
    return f"""-- Importação GERADA por scripts/ledger_recibo_incidente.py a partir de um RECEIPT do W4
-- (sha256 na constante `recibo`). Rodar pelo protocolo/com aprovador e ON_ERROR_STOP=1.
{cab}
{chr(10).join(corpo)}
  IF n = 0 THEN
    RAISE EXCEPTION 'ledger W4: nada a importar (nenhuma versão do recibo está aplicada no ledger)' USING ERRCODE = 'P0001';
  END IF;
END $volc_w4$;

COMMIT;
"""


def destino_livre(destino: Path) -> Path:
    destino = destino if destino.is_absolute() else (Path.cwd() / destino)
    resolvido = destino.resolve()
    if resolvido.is_relative_to(RAIZ):
        rel = resolvido.relative_to(RAIZ)
        r = subprocess.run(["git", "-C", str(RAIZ), "ls-files", "--error-unmatch", str(rel)],
                           capture_output=True)
        if r.returncode == 0:
            raise ReciboInvalido(f"destino versionado no git: {rel}")
    if destino.exists():
        raise ReciboInvalido(f"destino já existe: {destino.name} (nunca sobrescrevo)")
    return destino


def escrever(destino: Path, conteudo: str) -> None:
    dados = conteudo.encode("utf-8")  # erro de codificação acontece ANTES de abrir qualquer arquivo
    fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=".ledger-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
        os.link(tmp, destino)  # falha se o destino surgiu no meio: nunca sobrescreve
    finally:
        os.unlink(tmp)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("modo", choices=["v20_02", "importar"])
    p.add_argument("recibo", type=Path)
    p.add_argument("--saida", type=Path)
    p.add_argument("--ancora-pre-v19", default=ANCORA_PRE_V19,
                   help="só laboratório: fingerprint da base antes do passo 1 (produção usa o padrão medido em 15/10)")
    a = p.parse_args(argv)
    if a.modo == "importar" and a.saida is None:
        print("RECUSADO: importar exige --saida", file=sys.stderr)
        return 2
    try:
        destino = destino_livre(a.saida or (RAIZ / SAIDA_V20_02))
        sql = gerar_v20_02(a.recibo, a.ancora_pre_v19) if a.modo == "v20_02" else gerar_importacao(a.recibo)
        escrever(destino, sql)
    except (ReciboInvalido, OSError, UnicodeError) as e:
        print(f"RECUSADO: {e}", file=sys.stderr)
        return 1
    print(f"{destino} sha256 {hashlib.sha256(sql.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
