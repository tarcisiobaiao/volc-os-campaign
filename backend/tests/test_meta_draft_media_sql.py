"""Real SQL: exact owner/draft/account/bytes/selection, never a user-issued grant."""
from pathlib import Path
from uuid import uuid4
import pytest
from test_meta_v2_approval_sql import pg

MIGRATIONS = Path(__file__).resolve().parents[2] / 'supabase/migrations'


@pytest.fixture(scope='module')
def media_pg(pg):
    pg.execute('RESET ROLE')
    pg.execute((MIGRATIONS / '20260909000758_meta_campaign_draft_persistence.sql').read_text())
    pg.execute('CREATE TABLE criativo_job(id uuid PRIMARY KEY, criado_por uuid); '
               'CREATE TABLE criativo_master(id uuid PRIMARY KEY, job_id uuid REFERENCES criativo_job(id), content_hash text, arquivado_em timestamptz); '
               'CREATE TABLE trafego_meta_rascunho_pack(owner_id uuid, draft_ref uuid, adset_key text, master_refs uuid[])')
    sql = (MIGRATIONS / '20260909070930_meta_draft_media_authorization.sql').read_text()
    pg.execute(sql); pg.execute(sql)
    pg.execute('ALTER TABLE trafego_meta_campaign_draft ADD COLUMN IF NOT EXISTS archived_at timestamptz')
    sql = (MIGRATIONS / '20260909114432_meta_account_draft_upload_authority.sql').read_text()
    pg.execute(sql); pg.execute(sql)
    return pg


@pytest.fixture
def selected(media_pg):
    from psycopg.types.json import Jsonb
    conn=media_pg; conn.execute('RESET ROLE')
    ref, master, job = uuid4(), uuid4(), uuid4()
    owner=str(uuid4()); account='metaacct_fixture'; sha='sha256:'+'a'*64
    draft={'accountRef':account, 'conjuntos':[{'key':'set-one'}]}
    conn.execute('INSERT INTO trafego_meta_campaign_draft(owner_id,draft_ref,version,draft) VALUES(%s,%s,1,%s)', (owner,ref,Jsonb(draft)))
    conn.execute('INSERT INTO criativo_job VALUES(%s,%s)', (job,owner))
    conn.execute('INSERT INTO criativo_master VALUES(%s,%s,%s,NULL)', (master,job,sha))
    conn.execute('INSERT INTO trafego_meta_rascunho_pack VALUES(%s,%s,%s,%s)', (owner,ref,'set-one',[master]))
    conn.execute("INSERT INTO meta_media_private.draft_upload_grant(owner_id,draft_ref,account_ref,master_hashes,expires_at,authority_note) VALUES(%s,%s,%s,%s,now()+interval '1 hour','Explicit selected-draft approval')", (owner,ref,account,Jsonb({str(master):sha})))
    def check(who=owner, draft_ref=ref, acct=account, refs=None):
        conn.execute('SET ROLE service_role')
        try:
            return conn.execute('SELECT trafego_meta_draft_upload_check(%s,%s,%s,%s)', (who,draft_ref,acct,[master] if refs is None else refs)).fetchone()[0]
        finally: conn.execute('RESET ROLE')
    return conn, ref, master, job, check


def test_exact_scope_and_role_boundaries(selected):
    import psycopg
    conn, ref, master, job, check = selected
    assert check()['allowed'] is True
    assert check()['scope']=='DRAFT_SELECTED_MEDIA_ONLY'
    for kwargs in ({'who':'other'}, {'draft_ref':uuid4()}, {'acct':'metaacct_other'}, {'refs':[]}, {'refs':[master,master]}, {'refs':[None]}, {'refs':[uuid4()]}):
        assert check(**kwargs)['allowed'] is False
    for role in ('anon','authenticated','service_role'):
        conn.execute(f'SET ROLE {role}')
        for sql in ('SELECT * FROM meta_media_private.draft_upload_grant', "UPDATE meta_media_private.draft_upload_grant SET expires_at=now()+interval '1 year'", 'DELETE FROM meta_media_private.draft_upload_grant'):
            with pytest.raises(psycopg.Error): conn.execute(sql)
        if role != 'service_role':
            with pytest.raises(psycopg.Error): conn.execute('SELECT trafego_meta_draft_upload_check(%s,%s,%s,%s)', ('other',ref,'metaacct_fixture',[master]))
    conn.execute('RESET ROLE')


@pytest.mark.parametrize('change', ['revoked','expired','hash','archived','owner','selection','set','account'])
def test_context_changes_invalidate_grant(selected,change):
    conn, ref, master, job, check=selected
    assert check()['allowed']
    statements={
        'revoked': ('UPDATE meta_media_private.draft_upload_grant SET revoked_at=now() WHERE draft_ref=%s', ref),
        'expired': ("UPDATE meta_media_private.draft_upload_grant SET issued_at=now()-interval '2 hours',expires_at=now()-interval '1 hour' WHERE draft_ref=%s",ref),
        'hash': ("UPDATE criativo_master SET content_hash='sha256:changed' WHERE id=%s",master),
        'archived': ('UPDATE criativo_master SET arquivado_em=now() WHERE id=%s',master),
        'owner': ("UPDATE criativo_job SET criado_por=gen_random_uuid() WHERE id=%s",job),
        'selection': ('DELETE FROM trafego_meta_rascunho_pack WHERE draft_ref=%s',ref),
        'set': ("UPDATE trafego_meta_campaign_draft SET draft=jsonb_set(draft,'{conjuntos}','[]') WHERE draft_ref=%s",ref),
        'account': ("UPDATE trafego_meta_campaign_draft SET draft=jsonb_set(draft,'{accountRef}','\"metaacct_other\"') WHERE draft_ref=%s",ref),
    }
    sql,arg=statements[change]; conn.execute(sql,(arg,))
    assert check()['allowed'] is False


def test_account_authority_covers_new_owned_drafts_without_selection_grants(selected):
    from psycopg.types.json import Jsonb
    conn, ref, master, job, check = selected
    owner = conn.execute('SELECT owner_id FROM trafego_meta_campaign_draft WHERE draft_ref=%s',(ref,)).fetchone()[0]
    conn.execute('DELETE FROM meta_media_private.draft_upload_grant WHERE draft_ref=%s',(ref,))
    assert not check()['allowed']
    conn.execute("INSERT INTO meta_media_private.account_upload_grant(owner_id,account_ref,authority_note) VALUES(%s,'metaacct_fixture','Explicit account authorization for owned drafts')",(owner,))
    assert check()['scope']=='ACCOUNT_OWNED_DRAFTS'
    assert check()['expires_at'] is None
    new_ref=uuid4()
    conn.execute('INSERT INTO trafego_meta_campaign_draft(owner_id,draft_ref,version,draft) VALUES(%s,%s,1,%s)',
        (owner,new_ref,Jsonb({'accountRef':'metaacct_fixture','conjuntos':[{'key':'new-set'}]})))
    conn.execute('INSERT INTO trafego_meta_rascunho_pack VALUES(%s,%s,%s,%s)',(owner,new_ref,'new-set',[master]))
    assert check(draft_ref=new_ref)['allowed']
    assert not check(who='other',draft_ref=new_ref)['allowed']
    assert not check(acct='metaacct_other',draft_ref=new_ref)['allowed']
    assert not check(refs=[uuid4()],draft_ref=new_ref)['allowed']
    conn.execute('UPDATE trafego_meta_campaign_draft SET archived_at=now() WHERE draft_ref=%s',(new_ref,))
    assert not check(draft_ref=new_ref)['allowed']
    conn.execute('UPDATE meta_media_private.account_upload_grant SET revoked_at=now() WHERE owner_id=%s',(owner,))
    assert not check()['allowed']


def test_account_authority_cannot_be_self_issued(selected):
    import psycopg
    conn, *_=selected
    for role in ('anon','authenticated','service_role'):
        conn.execute(f'SET ROLE {role}')
        with pytest.raises(psycopg.Error):
            conn.execute("INSERT INTO meta_media_private.account_upload_grant(owner_id,account_ref,authority_note) VALUES('other','metaacct_fixture','Must never self authorize')")
        with pytest.raises(psycopg.Error):
            conn.execute('SELECT * FROM meta_media_private.account_upload_grant')
    conn.execute('RESET ROLE')
