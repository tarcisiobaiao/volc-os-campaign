"""Actual PG migration: additive backfill, reapply, version uniqueness and RLS."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

SQL = Path(__file__).resolve().parents[2] / "supabase/migrations/20260909234342_creative_generation_versions.sql"


def test_generation_version_migration_real_postgres():
    if not all(shutil.which(x) for x in ("initdb", "pg_ctl", "psql")):
        pytest.skip("PostgreSQL binaries unavailable")
    psycopg = pytest.importorskip("psycopg")
    root = Path(tempfile.mkdtemp(prefix="volc-creative-versions-"))
    data, sock = root / "data", root / "socket"
    sock.mkdir()
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    def cmd(*args):
        r = subprocess.run(args, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    cmd("initdb", "-D", str(data), "-U", "postgres", "--encoding=UTF8", "--locale=C")
    cmd("pg_ctl", "-D", str(data), "-l", str(root / "log"), "-o", f"-k {sock} -h ''", "-w", "start")
    try:
        with psycopg.connect(host=str(sock), dbname="postgres", user="postgres", autocommit=True) as conn:
            conn.execute("CREATE TABLE criativo_agente_peca_job(run_ref text NOT NULL, creative_ref text NOT NULL, owner_id text NOT NULL, constraint criativo_agente_peca_job_unica unique(run_ref,creative_ref)); ALTER TABLE criativo_agente_peca_job ENABLE ROW LEVEL SECURITY; INSERT INTO criativo_agente_peca_job VALUES ('run','piece','owner')")
            for _ in range(2):
                conn.execute(SQL.read_text())
            assert conn.execute("SELECT geracao_ref FROM criativo_agente_peca_job").fetchone()[0] == "original"
            version = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            conn.execute("INSERT INTO criativo_agente_peca_job(run_ref,creative_ref,owner_id,geracao_ref) VALUES ('run','piece','owner',%s)", (version,))
            with pytest.raises(psycopg.errors.UniqueViolation):
                conn.execute("INSERT INTO criativo_agente_peca_job(run_ref,creative_ref,owner_id,geracao_ref) VALUES ('run','piece','owner',%s)", (version,))
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute("INSERT INTO criativo_agente_peca_job(run_ref,creative_ref,owner_id,geracao_ref) VALUES ('run','piece','owner','invalid')")
            assert conn.execute("SELECT count(*) FROM criativo_agente_peca_job").fetchone()[0] == 2
            assert conn.execute("SELECT relrowsecurity FROM pg_class WHERE oid='criativo_agente_peca_job'::regclass").fetchone()[0]
    finally:
        subprocess.run(["pg_ctl", "-D", str(data), "-m", "immediate", "stop"], env=env, capture_output=True)
