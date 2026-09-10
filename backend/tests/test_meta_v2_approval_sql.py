"""Exercise actual PostgreSQL approval RPCs and fencing with V2 budget scopes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from test_meta_v2_approval_budget import snapshot
from app.trafego.meta_execucao.orcamento_aprovado import manifesto_orcamentario

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase/migrations"
CANDIDATE = "20260908234824_meta_v2_approval_budget_manifest.sql"


@pytest.fixture(scope="module")
def pg():
    if not all(shutil.which(x) for x in ("initdb","pg_ctl","psql")):
        pytest.skip("PostgreSQL binaries unavailable")
    psycopg = pytest.importorskip("psycopg")
    root = Path(tempfile.mkdtemp(prefix="volc-v2-approval-pg-"))
    data, sock = root / "data", root / "socket"
    sock.mkdir()
    env = {**os.environ,"LC_ALL":"C","LANG":"C"}
    def cmd(*args):
        result=subprocess.run(args,env=env,capture_output=True,text=True)
        assert result.returncode == 0, result.stderr
    cmd("initdb","-D",str(data),"-U","postgres","--encoding=UTF8","--locale=C")
    cmd("pg_ctl","-D",str(data),"-l",str(root/"log"),"-o",f"-k {sock} -h ''","-w","start")
    try:
        with psycopg.connect(host=str(sock),dbname="postgres",user="postgres",autocommit=True) as conn:
            conn.execute("CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; CREATE TABLE trafego_meta_ad_account(id text)")
            for filename in ("20260904183418_meta_create_paused_executor.sql", "20260907120000_meta_recovery_snapshot.sql", "20260907190000_meta_worker_fencing.sql", CANDIDATE, CANDIDATE):
                sql="\n".join(line for line in (MIGRATIONS/filename).read_text().splitlines() if not line.startswith("\\"))
                conn.execute(sql)
            yield conn
    finally:
        subprocess.run(["pg_ctl","-D",str(data),"-m","immediate","stop"],env=env,capture_output=True)


def approve(conn, plan):
    from psycopg.types.json import Jsonb
    import hashlib
    nonce=str(datetime.now(timezone.utc))
    sha=hashlib.sha256(nonce.encode()).hexdigest()
    plan={**plan,"compiler_version":"meta-paused-v1","plano_sha256":sha,"account_ref":"metaacct_test_12345",
          "estado_ao_nascer":"PAUSED","api_version":"v26.0","asset_supply":[{}]}
    for op in plan["operacoes"]:
        op["endpoint"]="/act_1234567890/"+op["tipo"]
    steps=[op["nome"] for op in plan["operacoes"]]
    conn.execute("SET ROLE service_role")
    validation=conn.execute("SELECT trafego_meta_create_record_validation(%s,%s,%s,%s,%s,%s,%s,0)",
        (sha,plan["account_ref"],"test-operator","INDEPENDENT_ROOTS_ONLY",[steps[0]],steps[1:],len(steps))).fetchone()[0]
    expiry=datetime.now(timezone.utc)+timedelta(minutes=10)
    receipt={"asset_ref":"metaasset_test_12345","content_sha256":"a"*64,"supply_sha256":"b"*64,
        "policy_receipt_ref":"metapolicy_"+"a"*24,"policy_state":"CLEAR","lifecycle":"READY_FOR_PAID_MEDIA",
        "image_hash_bound":True,"policy_expires_at":(expiry+timedelta(minutes=1)).isoformat()}
    budget=manifesto_orcamentario(plan)
    args=(sha,plan["account_ref"],"test-operator",budget["daily_total_minor"],"BRL",expiry,steps,
          validation["validation_id"],1800,True,Jsonb({}),Jsonb([receipt]),Jsonb(plan),plan["compiler_version"],sha)
    result=conn.execute("SELECT trafego_meta_create_approve(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",args).fetchone()[0]
    return result, budget


@pytest.mark.parametrize("cbo,lifetime",[(False,False),(True,False),(False,True),(True,True)])
def test_live_rpc_budget_roundtrip_and_immutable_snapshot(pg,cbo,lifetime):
    import psycopg
    result,budget=approve(pg,snapshot(cbo=cbo,lifetime=lifetime))
    assert result["budget_manifest"] == budget
    manifest=pg.execute("SELECT trafego_meta_create_approval_manifest(%s)",(result["approval_id"],)).fetchone()[0]
    assert manifest["budget_manifest"] == budget
    assert manifest["daily_budget_minor"] == budget["daily_total_minor"]
    pg.execute("RESET ROLE")
    with pytest.raises(psycopg.Error,match="META_APPROVAL_IMMUTABLE"):
        pg.execute("UPDATE trafego_meta_create_approval SET compiled_plan='{}'::jsonb WHERE approval_id=%s",(result["approval_id"],))


def test_thirty_one_steps_are_accepted_and_adset_claim_is_fenced(pg):
    import psycopg
    result,_=approve(pg,snapshot(count=10))
    assert result["operations_expected"] == 31
    first=pg.execute("SELECT trafego_meta_create_prepare_step(%s,%s,%s,%s,%s)",
        (result["plan_sha256"],result["approval_id"],"test-operator","campaign","d"*64)).fetchone()[0]
    # Signature discovered from existing worker_fencing contract; close rotates token.
    pg.execute("SELECT trafego_meta_create_close_step(%s,%s,%s)",(first["step_ref"],"12345",first["claim_token"]))
    second=pg.execute("SELECT trafego_meta_create_prepare_step(%s,%s,%s,%s,%s)",
        (result["plan_sha256"],result["approval_id"],"test-operator","adset:s0","e"*64)).fetchone()[0]
    assert second["claim_token"]
    pg.execute("SET ROLE authenticated")
    with pytest.raises(psycopg.Error):
        pg.execute("SELECT trafego_meta_create_approval_manifest(%s)",(result["approval_id"],))
    pg.execute("RESET ROLE")
