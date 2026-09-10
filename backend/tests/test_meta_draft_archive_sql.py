from pathlib import Path
from uuid import uuid4
import pytest
from test_meta_draft_media_sql import media_pg, selected, MIGRATIONS
from test_meta_v2_approval_sql import pg

@pytest.fixture
def archived_schema(selected):
    conn,*_=selected
    conn.execute((MIGRATIONS/'20260909013856_meta_campaign_draft_list.sql').read_text())
    sql=(MIGRATIONS/'20260909073845_meta_draft_archive.sql').read_text()
    conn.execute(sql); conn.execute(sql)
    return selected

def test_archive_cas_owner_grants_retained_data_and_no_resurrection(archived_schema):
    import psycopg
    conn,ref,master,job,check=archived_schema
    owner=conn.execute('SELECT owner_id FROM trafego_meta_campaign_draft WHERE draft_ref=%s',(ref,)).fetchone()[0]
    assert check()['allowed']
    conn.execute('SET ROLE service_role')
    assert conn.execute('SELECT trafego_meta_campaign_draft_archive(%s,%s,1)',('other',ref)).fetchone()[0] is None
    with pytest.raises(psycopg.Error,match='VERSION_CONFLICT'):
        conn.execute('SELECT trafego_meta_campaign_draft_archive(%s,%s,9)',(owner,ref))
    result=conn.execute('SELECT trafego_meta_campaign_draft_archive(%s,%s,1)',(owner,ref)).fetchone()[0]
    assert result['archived'] and result['version']==2
    assert conn.execute('SELECT trafego_meta_campaign_draft_archive(%s,%s,1)',(owner,ref)).fetchone()[0]==result
    assert conn.execute('SELECT trafego_meta_campaign_draft_read(%s,%s)',(owner,ref)).fetchone()[0] is None
    assert conn.execute('SELECT trafego_meta_campaign_draft_list(%s,0)',(owner,)).fetchone()[0]==[]
    assert not check()['allowed']
    assert conn.execute('SELECT count(*) FROM trafego_meta_rascunho_pack WHERE draft_ref=%s',(ref,)).fetchone()[0]==1
    assert conn.execute('SELECT count(*) FROM criativo_master WHERE id=%s',(master,)).fetchone()[0]==1
    with pytest.raises(psycopg.Error,match='META_DRAFT_ARCHIVED'):
        conn.execute('UPDATE trafego_meta_campaign_draft SET version=3 WHERE draft_ref=%s',(ref,))
    for role in ('anon','authenticated'):
        conn.execute(f'SET ROLE {role}')
        with pytest.raises(psycopg.Error): conn.execute('SELECT trafego_meta_campaign_draft_archive(%s,%s,2)',(owner,ref))
    conn.execute('RESET ROLE')
