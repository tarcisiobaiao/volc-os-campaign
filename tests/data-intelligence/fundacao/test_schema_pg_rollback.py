"""Rollback da migration candidata: up → down → up limpo, down idempotente, up repetido atômico.

Usa um cluster dedicado (papéis são globais do cluster; o rollback os remove).
"""
from __future__ import annotations

import hashlib

UP = "dil_obs_0001_schema_observacao.sql"
DOWN = "dil_obs_0001_schema_observacao.down.sql"

CATALOGO = """
SELECT md5(string_agg(x, E'\\n' ORDER BY x)) FROM (
  SELECT 'rel:' || relname || ':' || relkind::text || ':' || relrowsecurity || relforcerowsecurity FROM pg_class
   WHERE relnamespace = 'dil_obs'::regnamespace
  UNION ALL SELECT 'con:' || conname || ':' || pg_get_constraintdef(oid) FROM pg_constraint
   WHERE connamespace = 'dil_obs'::regnamespace
  UNION ALL SELECT 'fn:' || p.oid::regprocedure::text || ':' || prosecdef || ':' || coalesce(array_to_string(proacl, ','), '')
    FROM pg_proc p WHERE pronamespace = 'dil_obs'::regnamespace
  UNION ALL SELECT 'tg:' || tgname || ':' || pg_get_triggerdef(oid) FROM pg_trigger
   WHERE tgrelid IN (SELECT oid FROM pg_class WHERE relnamespace = 'dil_obs'::regnamespace) AND NOT tgisinternal
  UNION ALL SELECT 'pol:' || polname || ':' || coalesce(pg_get_expr(polqual, polrelid), '') FROM pg_policy
   WHERE polrelid IN (SELECT oid FROM pg_class WHERE relnamespace = 'dil_obs'::regnamespace)
  UNION ALL SELECT 'acl:' || relname || ':' || coalesce(array_to_string(relacl, ','), '') FROM pg_class
   WHERE relnamespace = 'dil_obs'::regnamespace
) s(x);
"""

RESIDUO = """
SELECT (SELECT count(*) FROM pg_namespace WHERE nspname = 'dil_obs') || '|' ||
       (SELECT count(*) FROM pg_roles WHERE rolname LIKE 'dil\\_obs\\_%') || '|' ||
       (SELECT count(*) FROM pg_default_acl d JOIN pg_roles r ON r.oid = d.defaclrole WHERE r.rolname LIKE 'dil\\_obs\\_%');
"""


def _uma_observacao_sql() -> str:
    corpo = b'{"cost_micros": 5000000}'
    h = hashlib.sha256(corpo).hexdigest()
    obs = (
        '{"fonte":"google_ads","conta":"rb","entidade_tipo":"campaign","entidade_id":"1","grao":["campaign","day"],'
        '"dimensoes":[],"metrica":"cost","value_kind":null,"valor":5000000,"unidade":"micros","moeda":"BRL",'
        '"janela_inicio":"2026-08-01T00:00:00-03:00","janela_fim":"2026-08-02T00:00:00-03:00",'
        '"timezone":"America/Sao_Paulo","observed_at":"2026-08-02T04:00:00-03:00","source_updated_at":null,'
        '"available_at":"2026-08-02T04:05:00-03:00","ingested_at":"2026-08-02T04:06:00-03:00","run_id":"run-rb",'
        f'"request_id":null,"lote_id":"lote-rb","payload_sha256":"{h}","payload_ref":"sha256:{h}",'
        '"schema_version":"google_ads.gaql.campaign_day.v1","coletor_nome":"c","coletor_versao":"1",'
        '"status":"observed","motivo":null,"cobertura_ppm":null}'
    )
    relogio = ("RESET ROLE; CREATE OR REPLACE FUNCTION dil_obs._agora() RETURNS timestamptz LANGUAGE sql STABLE PARALLEL SAFE "
               "SET search_path = '' AS $$ SELECT {} $$;")
    return (
        relogio.format("'2026-08-02T04:05:00-03:00'::timestamptz") +  # relógio do banco simulado (R1-F1)
        "SET ROLE dil_obs_escritor;"
        "SELECT dil_obs.registrar_run('run-rb','google_ads','c','1','2026-08-01T00:00:00-03:00');"
        f"SELECT dil_obs.registrar_payload('{h}', decode('{corpo.hex()}','hex'), 'application/json');"
        f"SELECT dil_obs.registrar_lote('lote-rb','run-rb','{h}','google_ads.gaql.campaign_day.v1','{{}}',NULL);"
        f"SELECT dil_obs.registrar_observacao('{obs}'::json);"
        f"SELECT dil_obs.registrar_observacao('{obs}'::json);"
        + relogio.format("pg_catalog.now()")
    )


def test_up_down_up_limpo_e_idempotente(cluster_pg_dedicado):
    c = cluster_pg_dedicado
    db = c.novo_banco("dil_rollback")
    assert c.psql(RESIDUO, db=db) == "0|0|0"

    c.aplicar(UP, db=db)
    assert c.psql(RESIDUO, db=db) == "1|3|1"
    assinatura_1 = c.psql(CATALOGO, db=db)
    assert c.psql(_uma_observacao_sql(), db=db).splitlines()[-2:] == ["inserido", "noop"]

    # up repetido sem down: falha inteiro (transação), sem objeto parcial nem dado perdido
    assert "already exists" in c.falha(_ler(UP), db=db)
    assert c.psql(CATALOGO, db=db) == assinatura_1
    assert c.psql("SELECT count(*) FROM dil_obs.observacao;", db=db) == "1"

    c.aplicar(DOWN, db=db)
    assert c.psql(RESIDUO, db=db) == "0|0|0"
    c.aplicar(DOWN, db=db)  # down idempotente
    assert c.psql(RESIDUO, db=db) == "0|0|0"

    c.aplicar(UP, db=db)
    assert c.psql(CATALOGO, db=db) == assinatura_1  # recriado idêntico
    assert c.psql("SELECT count(*) FROM dil_obs.observacao;", db=db) == "0"  # o down apagou o histórico (documentado)
    assert c.psql(_uma_observacao_sql(), db=db).splitlines()[-2:] == ["inserido", "noop"]
    c.aplicar(DOWN, db=db)
    assert c.psql(RESIDUO, db=db) == "0|0|0"


def test_down_preserva_papeis_usados_em_outro_banco(cluster_pg_dedicado):
    c = cluster_pg_dedicado
    a, b = c.novo_banco("dil_a"), c.novo_banco("dil_b")
    c.aplicar(UP, db=a)
    c.aplicar(UP, db=b)  # papéis já existem: o DO idempotente reaproveita
    c.aplicar(DOWN, db=a)  # papéis ainda têm dependência em dil_b: ficam, com NOTICE, sem erro
    assert c.psql(RESIDUO, db=a).split("|")[:2] == ["0", "3"]
    assert c.psql("SELECT count(*) FROM pg_namespace WHERE nspname = 'dil_obs';", db=b) == "1"
    c.aplicar(DOWN, db=b)
    assert c.psql(RESIDUO, db=b) == "0|0|0"


def _ler(nome: str) -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[3] / "experiments" / "data-intelligence-lab" / "migrations_candidatas" / nome).read_text()
