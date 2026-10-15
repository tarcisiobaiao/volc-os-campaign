#!/usr/bin/env python3
"""Liga os recibos do pacote do incidente anon (W4) ao ledger de migrations (v20).

O pacote v19 roda ANTES e FORA do ledger (superusuário, transação por arquivo, por
scripts/aplicar-incidente-anon-w4.sh) e grava RECEIPT-<carimbo>.json. Este script
transforma esses recibos em SQL do ledger, sem nada digitado à mão:

  v20_02  RECEIPT-passo1.json  →  supabase/migrations/v20_02_ledger_linha_de_base.sql
          Linha de base com ÂNCORA CONSTANTE = fingerprint_depois do recibo (o valor
          fica no arquivo cujo sha256 o dono aprova; nada vem de GUC), backfill dos
          eventos v19 na ordem do recibo, e o registro da própria v20_01.
  importar RECEIPT-passo2.json | RECEIPT-rollback.json  →  SQL de importação
          Passo 2: um "aplicar" (v8_06). Rollback: um "reverter" por versão que o
          ledger tiver como aplicada no momento (o resto é pulado, sem erro).
          Roda pelo protocolo, com volc_ops.aprovador na transação.

Recusas (exit 1, nada escrito): recibo de outro pacote, resultado ≠ ok, alvo de
laboratório usado sem --aceitar-lab, fingerprint medido com outra SQL, evento
cujo sha256 não é o do arquivo no repositório, aprovador vazio, versão repetida.

Uso:
  ledger_recibo_incidente.py v20_02   RECEIPT.json [--saida ARQ] [--aceitar-lab]
  ledger_recibo_incidente.py importar RECEIPT.json  --saida ARQ  [--aceitar-lab]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FP_SQL = "tools/freedom-lab/db/fingerprint_schema.sql"
V20_01 = "supabase/migrations/v20_01_ledger_migrations.sql"
V20_01_ROLL = "supabase/migrations/v20_01_rollback.sql"
V20_02 = "supabase/migrations/v20_02_ledger_linha_de_base.sql"
ANCORA_PRE_V19 = "695e913a4373efd1c2265cdd5ac87251"  # produção, 15/10 ~10:55Z (fingerprint-prod.out)
EVID_PRE_V19 = ("fingerprint-prod.out sha256 fbd623d78b4d21267251599fa8d80855c33dd80cc0e176b29c69d6212b77d170 "
                "(handoffs/freedom-lab-20261015, B-banco.md §0); estado anterior aplicado à mão, "
                "registro histórico em supabase/migrations/README.md")
MD5 = re.compile(r"^[0-9a-f]{32}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
VERSAO = re.compile(r"^[A-Za-z0-9_.-]{3,120}$")


class ReciboInvalido(ValueError):
    pass


def sha_arquivo(rel: str) -> str:
    return hashlib.sha256((RAIZ / rel).read_bytes()).hexdigest()


def q(valor) -> str:
    """Literal SQL seguro (o recibo é dado, nunca SQL)."""
    if valor is None:
        return "NULL"
    return "'" + str(valor).replace("'", "''") + "'"


def carregar(caminho: Path, operacoes: set[str], aceitar_lab: bool) -> tuple[dict, str]:
    bruto = caminho.read_bytes()
    r = json.loads(bruto, parse_constant=lambda c: (_ for _ in ()).throw(ReciboInvalido(c)))
    erros = []
    if r.get("pacote") != "incidente-anon-w4":
        erros.append(f"pacote {r.get('pacote')!r}")
    if r.get("operacao") not in operacoes:
        erros.append(f"operacao {r.get('operacao')!r} (esperado {sorted(operacoes)})")
    if r.get("resultado") != "ok":
        erros.append(f"resultado {r.get('resultado')!r}")
    if r.get("alvo") != "producao" and not aceitar_lab:
        erros.append(f"alvo {r.get('alvo')!r}: recibo de laboratório só com --aceitar-lab")
    if r.get("fingerprint_sql") != FP_SQL or r.get("fingerprint_sql_sha256") != sha_arquivo(FP_SQL):
        erros.append("fingerprint medido com outra SQL (âncora não comparável)")
    for k in ("fingerprint_antes", "fingerprint_depois"):
        if not MD5.match(str(r.get(k, ""))):
            erros.append(f"{k} inválido")
    eventos = r.get("eventos") or []
    if not eventos:
        erros.append("sem eventos")
    vistos = set()
    for e in eventos:
        v = e.get("versao", "")
        if not VERSAO.match(v) or v in vistos:
            erros.append(f"versão inválida ou repetida: {v!r}")
        vistos.add(v)
        if not str(e.get("aprovador", "")).strip():
            erros.append(f"{v}: sem aprovador")
        arq = e.get("arquivo", "")
        if not arq.startswith("supabase/migrations/") or ".." in arq or not (RAIZ / arq).is_file():
            erros.append(f"{v}: arquivo fora do repo ou ausente: {arq!r}")
        elif e.get("sha256") != sha_arquivo(arq):
            erros.append(f"{v}: sha256 do recibo ≠ sha256 do arquivo no repositório")
        if e.get("rollback_arquivo"):
            ra = e["rollback_arquivo"]
            if not (RAIZ / ra).is_file() or e.get("rollback_sha256") != sha_arquivo(ra):
                erros.append(f"{v}: rollback ausente ou com sha256 divergente")
        if e.get("operacao") not in ("aplicar", "reverter"):
            erros.append(f"{v}: operacao {e.get('operacao')!r}")
    if erros:
        raise ReciboInvalido("; ".join(erros))
    return r, hashlib.sha256(bruto).hexdigest()


def evidencia(caminho: Path, sha: str, r: dict, e: dict) -> str:
    return (f"{caminho.name} sha256 {sha} (alvo {r['alvo']}, carimbo {r.get('carimbo')}); "
            f"executado_por {e.get('executado_por')}, inicio {e.get('inicio')}, fim {e.get('fim')}; "
            f"aprovado_em do recibo = data da execução")


def insert_evento(e: dict, operacao: str, fingerprint: str, evid: str, condicional: bool = False) -> str:
    cols = "(versao, operacao, arquivo, sha256, rollback_arquivo, rollback_sha256, aprovador, aprovado_em, fingerprint, evidencia)"
    vals = (f"({q(e['versao'])}, {q(operacao)}, {q(e['arquivo'])}, {q(e['sha256'])}, "
            f"{q(e.get('rollback_arquivo'))}, {q(e.get('rollback_sha256'))}, {q(e['aprovador'])}, "
            f"{q(e.get('aprovado_em'))}::date, {q(fingerprint)}, {q(evid)})")
    if not condicional:
        return f"  INSERT INTO volc_ops.migracao_evento\n    {cols}\n  VALUES\n    {vals};"
    return (f"  IF EXISTS (SELECT 1 FROM volc_ops.migracao_estado WHERE versao = {q(e['versao'])} AND estado = 'aplicada') THEN\n"
            f"    INSERT INTO volc_ops.migracao_evento\n      {cols}\n    VALUES\n      {vals};\n"
            f"  ELSE\n    RAISE NOTICE 'importar: % não está aplicada no ledger — reverter pulado', {q(e['versao'])};\n  END IF;")


def gerar_v20_02(caminho: Path, aceitar_lab: bool) -> str:
    r, sha_rec = carregar(caminho, {"--passo1"}, aceitar_lab)
    if any(e["operacao"] != "aplicar" for e in r["eventos"]):
        raise ReciboInvalido("recibo do passo 1 só pode ter eventos aplicar")
    ancora = r["fingerprint_depois"]
    backfill = "\n\n".join(insert_evento(e, "aplicar", r["fingerprint_antes"], evidencia(caminho, sha_rec, r, e))
                           for e in r["eventos"])
    return f"""-- =============================================================================
-- v20_02_ledger_linha_de_base.sql — CANDIDATA, NÃO APLICADA
-- GERADA por scripts/ledger_recibo_incidente.py v20_02 a partir de
--   {caminho.name} (sha256 {sha_rec}, alvo {r['alvo']}).
-- Não editar à mão: regenerar do recibo; o dono aprova o sha256 DESTE arquivo.
--
-- Ordem decidida: o pacote do incidente anon (v19) roda antes e fora do ledger.
-- Esta migration registra, numa transação:
--   1. linha_de_base_producao_20261015 — fingerprint {ANCORA_PRE_V19}, o estado de
--      produção medido em 15/10 antes da v19;
--   2. um "aplicar" por migration do passo 1, na ordem do recibo, com o sha256 e o
--      par de rollback que o script do W4 aplicou (o gatilho do ledger recusa
--      duplicata e sha256 divergente);
--   3. v20_01_ledger_migrations — o próprio ledger.
-- ÂNCORA CONSTANTE: recusa se volc_ops.fingerprint_schema() não for {ancora}
-- (fingerprint_depois do recibo). Schema mudou desde o passo 1 → falha fechada.
-- O aprovador entra pelo protocolo (volc_ops.aprovador). Rollback: v20_02_rollback.sql.
-- =============================================================================
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $$
DECLARE
  esperado   constant text := {q(ancora)};
  medido     text;
  aprovador  text := nullif(btrim(current_setting('volc_ops.aprovador', true)), '');
  aprov_em   date := nullif(current_setting('volc_ops.aprovado_em', true), '')::date;
BEGIN
  IF to_regclass('volc_ops.migracao_evento') IS NULL THEN
    RAISE EXCEPTION 'v20_02: ledger ausente — aplique v20_01 antes' USING ERRCODE = 'P0001';
  END IF;
  IF aprovador IS NULL THEN
    RAISE EXCEPTION 'v20_02: sem aprovador (volc_ops.aprovador) — aplique pelo protocolo'
      USING ERRCODE = 'P0001';
  END IF;

  SELECT f.md5 INTO medido FROM volc_ops.fingerprint_schema() f WHERE f.categoria = '_TOTAL';
  IF medido IS DISTINCT FROM esperado THEN
    RAISE EXCEPTION 'v20_02: fingerprint de public+app_auth é %, a âncora aprovada (pós-v19) é % — o schema mudou desde o passo 1; regenere do recibo novo',
      medido, esperado USING ERRCODE = 'P0001';
  END IF;

  INSERT INTO volc_ops.migracao_evento
    (versao, operacao, arquivo, sha256, aprovador, aprovado_em, fingerprint, evidencia)
  VALUES
    ('linha_de_base_producao_20261015', 'linha_de_base', {q(FP_SQL)}, {q(sha_arquivo(FP_SQL))},
     aprovador, aprov_em, {q(ANCORA_PRE_V19)}, {q(EVID_PRE_V19)});

{backfill}

  INSERT INTO volc_ops.migracao_evento
    (versao, operacao, arquivo, sha256, rollback_arquivo, rollback_sha256,
     aprovador, aprovado_em, fingerprint, evidencia)
  VALUES
    ('v20_01_ledger_migrations', 'aplicar', {q(V20_01)}, {q(sha_arquivo(V20_01))},
     {q(V20_01_ROLL)}, {q(sha_arquivo(V20_01_ROLL))},
     aprovador, aprov_em, medido,
     'registrada retroativamente pela v20_02 (o ledger não existia antes de si mesmo)');
END $$;

COMMIT;
"""


def gerar_importacao(caminho: Path, aceitar_lab: bool) -> str:
    r, sha_rec = carregar(caminho, {"--passo2", "--rollback"}, aceitar_lab)
    reverter = r["operacao"] == "--rollback"
    corpo = []
    for e in r["eventos"]:
        esperado = "reverter" if reverter else "aplicar"
        if e["operacao"] != esperado:
            raise ReciboInvalido(f"{e['versao']}: evento {e['operacao']} num recibo {r['operacao']}")
        if reverter and e.get("rollback_arquivo"):
            raise ReciboInvalido(f"{e['versao']}: evento reverter não leva par de rollback")
        corpo.append(insert_evento(e, esperado, r["fingerprint_antes"], evidencia(caminho, sha_rec, r, e),
                                   condicional=reverter))
    # No rollback, o arquivo do evento é o v19_99 e o gatilho exige que o sha256 seja o
    # rollback aprovado na aplicação daquela versão; versões não aplicadas são puladas.
    return f"""-- Importação gerada por scripts/ledger_recibo_incidente.py a partir de
--   {caminho.name} (sha256 {sha_rec}, operação {r['operacao']}, alvo {r['alvo']}).
-- Roda pelo protocolo (volc_ops.aprovador na transação). Nada além de INSERT no ledger.
BEGIN;
DO $$
BEGIN
  IF to_regclass('volc_ops.migracao_evento') IS NULL THEN
    RAISE EXCEPTION 'importar: ledger ausente' USING ERRCODE = 'P0001';
  END IF;
{chr(10).join(corpo)}
END $$;
COMMIT;
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("modo", choices=["v20_02", "importar"])
    p.add_argument("recibo", type=Path)
    p.add_argument("--saida", type=Path)
    p.add_argument("--aceitar-lab", action="store_true")
    a = p.parse_args(argv)
    try:
        sql = (gerar_v20_02 if a.modo == "v20_02" else gerar_importacao)(a.recibo, a.aceitar_lab)
    except (ReciboInvalido, json.JSONDecodeError, KeyError) as e:
        print(f"RECUSADO: {e}", file=sys.stderr)
        return 1
    destino = a.saida or (RAIZ / V20_02 if a.modo == "v20_02" else None)
    if destino is None:
        print("RECUSADO: importar exige --saida", file=sys.stderr)
        return 2
    destino.write_text(sql, encoding="utf-8")
    print(f"{destino} sha256 {hashlib.sha256(sql.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
