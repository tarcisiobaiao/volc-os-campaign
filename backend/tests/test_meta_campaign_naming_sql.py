"""Durable numbering against disposable PostgreSQL; never an operational DB."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from threading import Barrier
from uuid import uuid4

import pytest

from test_meta_campaign_draft import draft_fixture
from test_meta_campaign_draft_sql import draft_pg
from test_meta_existing_post_draft_sql import post_pg, save
from test_meta_flexible_texts_draft_sql import flexible_pg, POOL
from test_meta_v2_approval_sql import MIGRATIONS, pg
from test_meta_campaign_naming import naming_fixture

MIGRATION = MIGRATIONS / '20260910081646_meta_campaign_naming_reservations.sql'


def account_ref(account):
    return 'metaacct_' + sha256(f'META_ADS:account:{account}'.encode()).hexdigest()[:24]


@pytest.fixture(scope='module')
def naming_pg(flexible_pg):
    flexible_pg.execute('RESET ROLE')
    # The base draft fixture predates archival; this is only its missing column,
    # not a replacement or relaxation of the production archival RPC.
    flexible_pg.execute('ALTER TABLE public.trafego_meta_campaign_draft ADD COLUMN IF NOT EXISTS archived_at timestamptz')
    sql = MIGRATION.read_text()
    flexible_pg.execute(sql)
    flexible_pg.execute(sql)
    return flexible_pg


def new_draft(conn, account, owner='naming-owner', ref=None):
    draft = draft_fixture()
    draft['accountRef'] = account_ref(account)
    ref = ref or uuid4()
    conn.execute('SET ROLE service_role')
    save(conn, ref, draft, owner=owner)
    return ref, draft


def reserve(conn, ref, account, owner='naming-owner', version=1, maximum=0,
            count=0, complete=True, opaque=None):
    return conn.execute('SELECT trafego_meta_campaign_naming_reserve(%s,%s,%s,%s,%s,%s,%s,%s)',
        (owner, ref, version, account, opaque or account_ref(account), maximum, count, complete)).fetchone()[0]


def test_number_global_per_physical_account_and_idempotent(naming_pg):
    conn = naming_pg
    first, _ = new_draft(conn, '71001', 'owner-a')
    initial = reserve(conn, first, '71001', 'owner-a', maximum=35, count=8)
    assert initial == {'campaign_number': 36, 'account_ref': account_ref('71001'),
        'draft_ref': str(first), 'history_complete': True, 'history_count': 8}
    # Changing topics/history on retry never reallocates an existing reservation.
    assert reserve(conn, first, '71001', 'owner-a', maximum=100, count=10) == initial
    second, _ = new_draft(conn, '71001', 'owner-b')
    assert reserve(conn, second, '71001', 'owner-b', maximum=35)['campaign_number'] == 37
    third, _ = new_draft(conn, '71002', 'owner-a')
    assert reserve(conn, third, '71002', 'owner-a')['campaign_number'] == 1
    assert conn.execute('SELECT trafego_meta_campaign_draft_read(%s,%s)', ('owner-a', first)).fetchone()[0]['version'] == 1
    conn.execute('RESET ROLE')


def test_account_switch_delete_and_archive_never_recycle(naming_pg):
    import psycopg
    conn = naming_pg
    ref, draft = new_draft(conn, '72001')
    assert reserve(conn, ref, '72001')['campaign_number'] == 1
    draft['accountRef'] = account_ref('72002')
    save(conn, ref, draft, 1, 'naming-owner')
    assert reserve(conn, ref, '72002', version=2)['campaign_number'] == 1
    draft['accountRef'] = account_ref('72001')
    save(conn, ref, draft, 2, 'naming-owner')
    assert reserve(conn, ref, '72001', version=3)['campaign_number'] == 1
    conn.execute('RESET ROLE')
    conn.execute('UPDATE trafego_meta_campaign_draft SET archived_at=now() WHERE owner_id=%s AND draft_ref=%s', ('naming-owner', ref))
    conn.execute('SET ROLE service_role')
    with pytest.raises(psycopg.Error, match='META_DRAFT_ARCHIVED'):
        reserve(conn, ref, '72001', version=3)
    conn.execute('RESET ROLE')
    conn.execute('DELETE FROM trafego_meta_campaign_draft WHERE owner_id=%s AND draft_ref=%s', ('naming-owner', ref))
    other, _ = new_draft(conn, '72001')
    assert reserve(conn, other, '72001')['campaign_number'] == 2
    conn.execute('RESET ROLE')


@pytest.mark.parametrize('change,code', [
    ({'version': 2}, 'META_DRAFT_VERSION_CONFLICT'),
    ({'owner': 'wrong-owner'}, 'META_DRAFT_NOT_FOUND'),
    ({'complete': False}, 'META_NAMING_INVALID'),
    ({'maximum': -1}, 'META_NAMING_INVALID'),
    ({'opaque': account_ref('79999')}, 'META_NAMING_ACCOUNT_CHANGED'),
    ({'maximum': 2147483647}, 'META_NAMING_RANGE_EXHAUSTED'),
])
def test_failed_guards_do_not_consume_number(naming_pg, change, code):
    import psycopg
    conn, account = naming_pg, str(73000000 + int(uuid4().hex[:6], 16))
    ref, _ = new_draft(conn, account)
    with pytest.raises(psycopg.Error, match=code):
        reserve(conn, ref, account, **change)
    assert reserve(conn, ref, account)['campaign_number'] == 1
    conn.execute('RESET ROLE')


def test_two_concurrent_owners_receive_different_numbers(naming_pg):
    import psycopg
    conn, account = naming_pg, '74001'
    one, _ = new_draft(conn, account, 'race-owner-a')
    two, _ = new_draft(conn, account, 'race-owner-b')
    conn.execute('RESET ROLE')
    barrier = Barrier(2)
    def run(ref, owner):
        with psycopg.connect(conn.info.dsn, autocommit=True) as own:
            own.execute('SET ROLE service_role')
            barrier.wait(timeout=10)
            return reserve(own, ref, account, owner, maximum=12)['campaign_number']
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(run, one, 'race-owner-a')
        b = pool.submit(run, two, 'race-owner-b')
        assert sorted([a.result(timeout=20), b.result(timeout=20)]) == [13, 14]


def test_naming_roundtrip_preserves_flexible_existing_post_and_approval_guards(naming_pg):
    conn, ref, draft = naming_pg, uuid4(), draft_fixture()
    draft['naming'] = naming_fixture()
    draft['conjuntos'][0]['flexibleTexts'] = deepcopy(POOL)
    draft['variations'][0]['existingPostRef'] = 'metapost_' + 'c' * 32
    conn.execute('SET ROLE service_role')
    result = save(conn, ref, draft)
    assert result['draft']['naming'] == draft['naming']
    assert result['draft']['conjuntos'][0]['flexibleTexts'] == POOL
    assert result['draft']['variations'][0]['existingPostRef'] == draft['variations'][0]['existingPostRef']
    assert result['draft']['variations'][0]['assetRightsConfirmed'] is False
    assert result['draft']['categoryConfirmed'] is False
    assert result['launch_authorized'] is False
    conn.execute('RESET ROLE')


@pytest.mark.parametrize('changes', [
    {'topic': 'x' * 201}, {'quiz': 'yes'}, {'campaignNumber': 0},
    {'campaignNumber': 1.5}, {'campaignNumber': 2147483648},
    {'adNumbers': {'a:b': True}}, {'adNumbers': {'a' * 66: 1}},
    {'adsetNumbers': {'a:b': 1}}, {'generated': {'campaign': 'x' * 401}},
    {'generated': {f'ad:{i}': 'name' for i in range(101)}}, {'unknown': True},
])
def test_direct_sql_rejects_malformed_naming(naming_pg, changes):
    import psycopg
    draft = draft_fixture()
    draft['naming'] = {**naming_fixture(), **changes}
    naming_pg.execute('SET ROLE service_role')
    with pytest.raises(psycopg.Error, match='META_DRAFT_NAMING_INVALID'):
        save(naming_pg, uuid4(), draft)
    naming_pg.execute('RESET ROLE')


@pytest.mark.parametrize('role', ['anon', 'authenticated'])
def test_reservation_is_not_public(naming_pg, role):
    import psycopg
    naming_pg.execute(f'SET ROLE {role}')
    with pytest.raises(psycopg.Error):
        reserve(naming_pg, uuid4(), '75001')
    naming_pg.execute('RESET ROLE')


def test_service_role_cannot_read_or_delete_private_numbers(naming_pg):
    import psycopg
    naming_pg.execute('SET ROLE service_role')
    with pytest.raises(psycopg.Error):
        naming_pg.execute('SELECT * FROM meta_draft_private.campaign_naming_reservation')
    with pytest.raises(psycopg.Error):
        naming_pg.execute('DELETE FROM meta_draft_private.campaign_naming_reservation')
    naming_pg.execute('RESET ROLE')
