from uuid import uuid4
from pathlib import Path
import pytest
from test_meta_v2_approval_sql import pg
from test_meta_campaign_draft import draft_fixture

MIGRATION=Path(__file__).resolve().parents[2]/"supabase/migrations/20260909000758_meta_campaign_draft_persistence.sql"


@pytest.fixture(scope="module")
def draft_pg(pg):
    pg.execute("RESET ROLE")
    pg.execute(MIGRATION.read_text()); pg.execute(MIGRATION.read_text())
    listing=MIGRATION.parent/'20260909013856_meta_campaign_draft_list.sql'
    pg.execute(listing.read_text()); pg.execute(listing.read_text())
    regulatory=MIGRATION.parent/'20260909112458_meta_draft_regulatory_identity.sql'
    pg.execute(regulatory.read_text()); pg.execute(regulatory.read_text())
    return pg


def test_list_sql_owner_bound_summary_only_and_no_public_access(draft_pg):
    import psycopg
    from psycopg.types.json import Jsonb
    conn=draft_pg
    conn.execute("SET ROLE service_role")
    for _ in range(22):
        conn.execute("SELECT trafego_meta_campaign_draft_save(%s,%s,0,%s)",("list-owner",uuid4(),Jsonb(draft_fixture())))
    rows=conn.execute("SELECT trafego_meta_campaign_draft_list('list-owner',0)").fetchone()[0]
    assert len(rows)==21 and all('draft' not in row and 'owner_id' not in row for row in rows)
    assert len(conn.execute("SELECT trafego_meta_campaign_draft_list('list-owner',20)").fetchone()[0])==2
    assert conn.execute("SELECT trafego_meta_campaign_draft_list('other-owner',0)").fetchone()[0]==[]
    with pytest.raises(psycopg.Error): conn.execute("SELECT * FROM trafego_meta_campaign_draft")
    for role in ('anon','authenticated'):
        conn.execute(f"SET ROLE {role}")
        with pytest.raises(psycopg.Error): conn.execute("SELECT trafego_meta_campaign_draft_list('list-owner',0)")
        with pytest.raises(psycopg.Error): conn.execute("SELECT meta_draft_private.list_campaign_drafts('list-owner',0)")
    conn.execute("RESET ROLE")


def test_sql_draft_cas_scope_clear_authority_and_service_only(draft_pg):
    import psycopg
    from psycopg.types.json import Jsonb
    conn=draft_pg; ref=uuid4(); draft=draft_fixture()
    conn.execute("SET ROLE service_role")
    def save(version,owner="owner-one"):
        return conn.execute("SELECT trafego_meta_campaign_draft_save(%s,%s,%s,%s)",(owner,ref,version,Jsonb(draft))).fetchone()[0]
    first=save(0)
    assert first["version"]==1
    assert first["draft"]["categoryConfirmed"] is False
    assert first["draft"]["variations"][0]["assetRightsConfirmed"] is False
    assert first["draft"]["variations"][0]["packOrigin"]==draft["variations"][0]["packOrigin"]
    with pytest.raises(psycopg.Error,match="META_DRAFT_VERSION_CONFLICT"): save(0)
    draft["variations"][0]["message"]="Updated copy"
    assert save(1)["version"]==2
    with pytest.raises(psycopg.Error,match="META_DRAFT_VERSION_CONFLICT"): save(1)
    other=conn.execute("SELECT trafego_meta_campaign_draft_read(%s,%s)",("owner-two",ref)).fetchone()[0]
    assert other is None
    same=conn.execute("SELECT trafego_meta_campaign_draft_read(%s,%s)",("owner-one",ref)).fetchone()[0]
    assert same["draft"]["variations"][0]["message"]=="Updated copy"
    conn.execute("SET ROLE authenticated")
    with pytest.raises(psycopg.Error): conn.execute("SELECT * FROM trafego_meta_campaign_draft")
    with pytest.raises(psycopg.Error): conn.execute("SELECT trafego_meta_campaign_draft_read(%s,%s)",("owner-one",ref))
    conn.execute("RESET ROLE")


@pytest.mark.parametrize("kind",["secret","orphan","oversized"])
def test_sql_refuses_invalid_payload_before_write(draft_pg,kind):
    import psycopg
    from psycopg.types.json import Jsonb
    draft=draft_fixture()
    if kind=="secret": draft["variations"][0]["message"]="Bearer "+"a"*60
    elif kind=="orphan": draft["variations"][0]["adsetKey"]="missing"
    else: draft["campaignName"]="x"*121000
    draft_pg.execute("SET ROLE service_role")
    with pytest.raises(psycopg.Error,match="META_DRAFT"):
        draft_pg.execute("SELECT trafego_meta_campaign_draft_save(%s,%s,%s,%s)",("owner-one",uuid4(),0,Jsonb(draft)))
    draft_pg.execute("RESET ROLE")


def test_sql_regulatory_identity_save_update_read_and_remove(draft_pg):
    from psycopg.types.json import Jsonb
    from app.trafego.meta.draft_storage import CampaignDraft
    ref=uuid4(); draft=draft_fixture()
    draft['conjuntos'][0]['regulatoryIdentityRef']='metareg_'+'a'*32
    draft_pg.execute('SET ROLE service_role')
    def save(version):
        return draft_pg.execute('SELECT trafego_meta_campaign_draft_save(%s,%s,%s,%s)',
            ('regulatory-owner',ref,version,Jsonb(CampaignDraft.model_validate(draft).persisted()))).fetchone()[0]
    first=save(0)
    assert first['draft']['conjuntos'][0]['regulatoryIdentityRef']=='metareg_'+'a'*32
    draft['conjuntos'][0]['regulatoryIdentityRef']='metareg_'+'b'*32
    assert save(1)['version']==2
    read=draft_pg.execute('SELECT trafego_meta_campaign_draft_read(%s,%s)',('regulatory-owner',ref)).fetchone()[0]
    restored=CampaignDraft.model_validate(read['draft']).persisted()
    assert restored['conjuntos'][0]['regulatoryIdentityRef']=='metareg_'+'b'*32
    assert restored['categoryConfirmed'] is False and read['launch_authorized'] is False
    assert restored['variations'][0]['adsetKey']=='adset-001'
    assert draft_pg.execute('SELECT trafego_meta_campaign_draft_read(%s,%s)',('other-owner',ref)).fetchone()[0] is None
    draft['conjuntos'][0]['regulatoryIdentityRef']=''
    assert 'regulatoryIdentityRef' not in save(2)['draft']['conjuntos'][0]
    del draft['conjuntos'][0]['regulatoryIdentityRef']
    assert 'regulatoryIdentityRef' not in save(3)['draft']['conjuntos'][0]
    draft_pg.execute('RESET ROLE')


@pytest.mark.parametrize('value', ['', None, 123, {}, '1234567890123456', 'metareg_'+'G'*32, 'metareg_'+'a'*31])
def test_sql_regulatory_identity_rejects_invalid_direct_rpc(draft_pg,value):
    import psycopg
    from psycopg.types.json import Jsonb
    draft=draft_fixture(); draft['conjuntos'][0]['regulatoryIdentityRef']=value
    draft_pg.execute('SET ROLE service_role')
    with pytest.raises(psycopg.Error,match='META_DRAFT_INVALID'):
        draft_pg.execute('SELECT trafego_meta_campaign_draft_save(%s,%s,0,%s)',('regulatory-owner',uuid4(),Jsonb(draft)))
    draft_pg.execute('RESET ROLE')
