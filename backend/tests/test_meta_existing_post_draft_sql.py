"""Exercise the actual existing-post draft migration on disposable PostgreSQL."""
from uuid import uuid4

import pytest

from test_meta_campaign_draft import draft_fixture
from test_meta_campaign_draft_sql import draft_pg
from test_meta_v2_approval_sql import MIGRATIONS, pg


@pytest.fixture(scope="module")
def post_pg(draft_pg):
    draft_pg.execute("RESET ROLE")
    sql = (MIGRATIONS / "20260909221222_meta_existing_post_draft.sql").read_text()
    draft_pg.execute(sql)
    draft_pg.execute(sql)  # Reapplication must preserve the durable API.
    return draft_pg


def save(conn, ref, draft, version=0, owner="post-owner"):
    from psycopg.types.json import Jsonb
    return conn.execute(
        "SELECT trafego_meta_campaign_draft_save(%s,%s,%s,%s)",
        (owner, ref, version, Jsonb(draft)),
    ).fetchone()[0]


def test_existing_post_roundtrip_preserves_identity_link_and_cas(post_pg):
    import psycopg
    draft = draft_fixture()
    ref = uuid4()
    draft["variations"][0]["existingPostRef"] = "metapost_" + "a" * 32
    draft["conjuntos"][0]["regulatoryIdentityRef"] = "metareg_" + "b" * 32
    post_pg.execute("SET ROLE service_role")
    first = save(post_pg, ref, draft)
    assert first["version"] == 1
    assert first["launch_authorized"] is False
    assert first["draft"]["categoryConfirmed"] is False
    assert first["draft"]["variations"][0]["assetRightsConfirmed"] is False
    assert first["draft"]["variations"][0]["thirdPartyIdentityCleared"] is False
    draft["variations"][0]["message"] = "Revised copy"
    assert save(post_pg, ref, draft, 1)["version"] == 2
    with pytest.raises(psycopg.Error, match="META_DRAFT_VERSION_CONFLICT"):
        save(post_pg, ref, draft, 1)
    read = post_pg.execute(
        "SELECT trafego_meta_campaign_draft_read(%s,%s)", ("post-owner", ref)
    ).fetchone()[0]
    assert read["draft"]["variations"][0]["existingPostRef"] == "metapost_" + "a" * 32
    assert read["draft"]["variations"][0]["adsetKey"] == "adset-001"
    assert read["draft"]["variations"][0]["message"] == "Revised copy"
    assert read["draft"]["conjuntos"][0]["regulatoryIdentityRef"] == "metareg_" + "b" * 32
    assert post_pg.execute(
        "SELECT trafego_meta_campaign_draft_read(%s,%s)", ("other-owner", ref)
    ).fetchone()[0] is None
    post_pg.execute("RESET ROLE")


@pytest.mark.parametrize("value", ["", 123, {}, [], "123456789_987654321", "metapost_" + "G" * 32, "metapost_" + "a" * 31, "metapost_" + "a" * 33])
def test_existing_post_rejects_malformed_direct_rpc_before_write(post_pg, value):
    import psycopg
    draft = draft_fixture()
    ref = uuid4()
    draft["variations"][0]["existingPostRef"] = value
    post_pg.execute("SET ROLE service_role")
    with pytest.raises(psycopg.Error, match="META_DRAFT_INVALID"):
        save(post_pg, ref, draft)
    assert post_pg.execute(
        "SELECT trafego_meta_campaign_draft_read(%s,%s)", ("post-owner", ref)
    ).fetchone()[0] is None
    post_pg.execute("RESET ROLE")


def test_existing_post_keeps_orphan_and_regulatory_guards(post_pg):
    import psycopg
    draft = draft_fixture()
    draft["variations"][0]["existingPostRef"] = "metapost_" + "c" * 32
    post_pg.execute("SET ROLE service_role")
    draft["variations"][0]["adsetKey"] = "nonexistent-adset"
    with pytest.raises(psycopg.Error, match="META_DRAFT_LINK_INVALID"):
        save(post_pg, uuid4(), draft)
    draft["variations"][0]["adsetKey"] = "adset-001"
    draft["conjuntos"][0]["regulatoryIdentityRef"] = "invalid"
    with pytest.raises(psycopg.Error, match="META_DRAFT_INVALID"):
        save(post_pg, uuid4(), draft)
    post_pg.execute("RESET ROLE")


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_existing_post_rpc_not_public(post_pg, role):
    import psycopg
    post_pg.execute(f"SET ROLE {role}")
    with pytest.raises(psycopg.Error):
        save(post_pg, uuid4(), draft_fixture())
    post_pg.execute("RESET ROLE")
