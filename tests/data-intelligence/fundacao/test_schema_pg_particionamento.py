"""Particionamento mensal OPCIONAL (dil_obs_0002): mesma semântica de 0001, append-only mantido, rollback exato."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

UP1 = "dil_obs_0001_schema_observacao.sql"
UP2 = "dil_obs_0002_observacao_particionada.OPCIONAL.sql"
DOWN2 = "dil_obs_0002_observacao_particionada.OPCIONAL.down.sql"
BRT = timezone(timedelta(hours=-3))

CATALOGO = """
SELECT md5(string_agg(x, E'\\n' ORDER BY x)) FROM (
  SELECT 'rel:' || relname || ':' || relkind::text || ':' || relrowsecurity || relforcerowsecurity || ':' ||
         coalesce(array_to_string(relacl, ','), '') FROM pg_class WHERE relnamespace = 'dil_obs'::regnamespace
  UNION ALL SELECT 'con:' || conrelid::regclass::text || ':' || conname || ':' || pg_get_constraintdef(oid)
    FROM pg_constraint WHERE connamespace = 'dil_obs'::regnamespace
  UNION ALL SELECT 'idx:' || indexrelid::regclass::text || ':' || pg_get_indexdef(indexrelid) FROM pg_index
   WHERE indrelid IN (SELECT oid FROM pg_class WHERE relnamespace = 'dil_obs'::regnamespace)
  UNION ALL SELECT 'fn:' || p.oid::regprocedure::text || ':' || prosecdef || ':' || coalesce(array_to_string(proacl, ','), '')
    FROM pg_proc p WHERE pronamespace = 'dil_obs'::regnamespace
  UNION ALL SELECT 'tg:' || tgname || ':' || pg_get_triggerdef(oid) FROM pg_trigger
   WHERE tgrelid IN (SELECT oid FROM pg_class WHERE relnamespace = 'dil_obs'::regnamespace) AND NOT tgisinternal
  UNION ALL SELECT 'pol:' || polrelid::regclass::text || ':' || polname || ':' || coalesce(pg_get_expr(polqual, polrelid), '')
    FROM pg_policy WHERE polrelid IN (SELECT oid FROM pg_class WHERE relnamespace = 'dil_obs'::regnamespace)
) s(x);
"""

ASOF = ("SELECT string_agg(chave_natural || ':' || status || ':' || coalesce(valor::text, 'NULL'), ',' ORDER BY chave_natural) "
        "FROM dil_obs.observacao_as_of('{t}');")


def _carga(itens) -> str:
    """itens: (conta, dia, h_disponivel, payload, valor). Registra pelas funções públicas, como um coletor."""
    relogio = ("RESET ROLE; CREATE OR REPLACE FUNCTION dil_obs._agora() RETURNS timestamptz LANGUAGE sql STABLE PARALLEL SAFE "
               "SET search_path = '' AS $$ SELECT {} $$; SET ROLE dil_obs_escritor;")
    sql = []
    for conta, dia, h, payload, valor in itens:
        sha = hashlib.sha256(payload).hexdigest()
        ano, mes, d = dia if len(dia) == 3 else (2026, *dia)
        ini = datetime(ano, mes, d, tzinfo=BRT)
        obs_at, disp = ini + timedelta(days=1), ini + timedelta(hours=h)
        lote = f"lote-{conta}-{sha[:10]}-{h}"
        run = f"run-{conta}-{ini.date().isoformat()}"
        sql.append(relogio.format(f"'{disp.isoformat()}'::timestamptz"))  # relógio do banco simulado (R1-F1)
        sql.append(f"SELECT dil_obs.registrar_run('{run}', 'google_ads', 'c', '1', '{ini.isoformat()}');")
        sql.append(f"SELECT dil_obs.registrar_payload('{sha}', decode('{payload.hex()}', 'hex'), 'application/json');")
        sql.append(f"SELECT dil_obs.registrar_lote('{lote}', '{run}', '{sha}', 'v1', '{{}}', NULL);")
        o = {"fonte": "google_ads", "conta": conta, "entidade_tipo": "campaign", "entidade_id": "1",
             "grao": ["campaign", "day"], "dimensoes": [], "metrica": "cost", "value_kind": None, "valor": valor,
             "unidade": "micros", "moeda": "BRL" if valor is not None else None, "janela_inicio": ini.isoformat(),
             "janela_fim": (ini + timedelta(days=1)).isoformat(), "timezone": "America/Sao_Paulo",
             "observed_at": obs_at.isoformat(), "source_updated_at": None, "available_at": disp.isoformat(),
             "ingested_at": disp.isoformat(), "run_id": run, "request_id": None, "lote_id": lote,
             "payload_sha256": sha, "payload_ref": f"sha256:{sha}", "schema_version": "v1", "coletor_nome": "c",
             "coletor_versao": "1", "status": "observed" if valor else "missing",
             "motivo": None if valor else "linha_ausente_na_resposta", "cobertura_ppm": None}
        sql.append(f"SELECT 'R:' || dil_obs.registrar_observacao('{json.dumps(o)}'::json);")
    sql.append(relogio.format("pg_catalog.now()"))
    return "\n".join(sql)


DADOS = [  # dois meses, uma virada de mês em BRT, um restatement e uma ausência
    ("p1", (6, 30), 30, b"jun-a", 1_000_000),
    ("p1", (6, 30), 80, b"jun-b", 1_100_000),
    ("p1", (7, 1), 30, b"jul-a", 2_000_000),
    ("p2", (7, 31), 30, b"jul-vazio", None),
]


def _resultados(saida: str) -> list[str]:
    return [ln[2:] for ln in saida.splitlines() if ln.startswith("R:")]


def test_particionamento_preserva_semantica_append_only_e_rollback_exato(cluster_pg):
    c = cluster_pg
    db = c.novo_banco("dil_part")
    c.aplicar(UP1, db=db)
    assinatura_0001 = c.psql(CATALOGO, db=db)
    assert _resultados(c.psql(_carga(DADOS[:3]), db=db, papel="dil_obs_escritor")) == ["inserido"] * 3
    cortes = ["2026-07-02T12:00:00-03:00", "2026-07-04T12:00:00-03:00", "2026-09-01T00:00:00-03:00"]
    antes = [c.psql(ASOF.format(t=t), db=db) for t in cortes]

    c.aplicar(UP2, db=db)
    assert c.psql("SELECT relkind FROM pg_class WHERE oid = 'dil_obs.observacao'::regclass;", db=db) == "p"
    particoes = c.psql("SELECT string_agg(relname, ',' ORDER BY relname) FROM pg_inherits i JOIN pg_class k ON k.oid = i.inhrelid "
                       "WHERE inhparent = 'dil_obs.observacao'::regclass;", db=db).split(",")
    assert particoes[:2] == ["observacao_p2026_06", "observacao_p2026_07"]
    assert [c.psql(ASOF.format(t=t), db=db) for t in cortes] == antes  # mesmo as_of depois de migrar

    # idempotência e escrita continuam pelas mesmas funções, agora roteadas para a partição
    saida = c.psql(_carga(DADOS[:1] + DADOS[3:]), db=db, papel="dil_obs_escritor")
    assert _resultados(saida) == ["noop", "inserido"]
    assert c.psql("SELECT count(*) FROM dil_obs.observacao_p2026_07;", db=db) == "2"

    # append-only: pelo pai, direto na partição e TRUNCATE da partição
    for sql in ("UPDATE dil_obs.observacao SET valor = 1;", "DELETE FROM dil_obs.observacao;",
                "TRUNCATE dil_obs.observacao;", "UPDATE dil_obs.observacao_p2026_07 SET valor = 1;",
                "DELETE FROM dil_obs.observacao_p2026_06;", "TRUNCATE dil_obs.observacao_p2026_07;"):
        assert "append_only" in c.falha(sql, db=db), sql
    # leitor lê pelo pai; não lê a partição direto; anon não lê nada
    assert c.psql("SELECT count(*) FROM dil_obs.observacao_latest;", db=db, papel="dil_obs_leitor") == "3"
    assert "permission denied" in c.falha("SELECT * FROM dil_obs.observacao_p2026_07;", db=db, papel="dil_obs_leitor")
    assert "permission denied" in c.falha("SELECT * FROM dil_obs.observacao;", db=db, papel="anon")
    # linha fora de qualquer partição falha alto (sem DEFAULT silenciosa)
    assert "no partition" in c.falha(_carga([("p3", (2025, 1, 15), 30, b"antes-das-particoes", 5)]),
                                     db=db, papel="dil_obs_escritor")
    depois_escrita = [c.psql(ASOF.format(t=t), db=db) for t in cortes]

    c.aplicar(DOWN2, db=db)
    assert c.psql(CATALOGO, db=db) == assinatura_0001  # catálogo idêntico ao de 0001
    assert [c.psql(ASOF.format(t=t), db=db) for t in cortes] == depois_escrita  # dados preservados
    assert _resultados(c.psql(_carga(DADOS[3:]), db=db, papel="dil_obs_escritor")) == ["noop"]
    assert _resultados(c.psql(_carga([("p4", (7, 2), 30, b"pos-rollback", 7)]), db=db, papel="dil_obs_escritor")) == ["inserido"]
