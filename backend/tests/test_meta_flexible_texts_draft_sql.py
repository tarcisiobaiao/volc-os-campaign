"""Actual PostgreSQL RPC, disposable cluster only; no live project writes."""
from copy import deepcopy
from uuid import uuid4

import pytest

from test_meta_campaign_draft_sql import draft_pg
from test_meta_v2_approval_sql import MIGRATIONS, pg
from test_meta_existing_post_draft_sql import post_pg, save
from test_meta_campaign_draft import draft_fixture

MIGRATION = MIGRATIONS / '20260910075813_meta_flexible_texts_draft.sql'
POOL = {'primary_text': ['Copy 1', 'Copy 2'], 'headline': ['Título 1', 'Título 2'], 'description': []}


@pytest.fixture(scope='module')
def flexible_pg(post_pg):
    post_pg.execute('RESET ROLE')
    sql = MIGRATION.read_text()
    post_pg.execute(sql)
    post_pg.execute(sql)
    return post_pg


def test_pool_roundtrip_owner_cas_and_existing_guards(flexible_pg):
    import psycopg
    conn, ref, draft = flexible_pg, uuid4(), draft_fixture()
    draft['creativeMode'] = 'flexible'
    draft['conjuntos'][0]['flexibleTexts'] = deepcopy(POOL)
    draft['conjuntos'][0]['regulatoryIdentityRef'] = 'metareg_' + 'b' * 32
    draft['variations'][0]['existingPostRef'] = 'metapost_' + 'c' * 32
    conn.execute('SET ROLE service_role')
    first = save(conn, ref, draft)
    assert first['draft']['conjuntos'][0]['flexibleTexts'] == POOL
    assert first['draft']['variations'][0]['assetRightsConfirmed'] is False
    assert first['draft']['categoryConfirmed'] is False and first['launch_authorized'] is False
    draft['conjuntos'][0]['flexibleTexts']['primary_text'].append('Copy 3')
    assert save(conn, ref, draft, 1)['version'] == 2
    with pytest.raises(psycopg.Error, match='META_DRAFT_VERSION_CONFLICT'):
        save(conn, ref, draft, 1)
    assert conn.execute('SELECT trafego_meta_campaign_draft_read(%s,%s)', ('another-owner', ref)).fetchone()[0] is None
    read = conn.execute('SELECT trafego_meta_campaign_draft_read(%s,%s)', ('post-owner', ref)).fetchone()[0]
    assert read['draft']['conjuntos'][0]['flexibleTexts']['primary_text'][-1] == 'Copy 3'
    assert read['draft']['variations'][0]['existingPostRef'] == draft['variations'][0]['existingPostRef']
    conn.execute('RESET ROLE')


@pytest.mark.parametrize('pool', [None, [], {}, {**POOL, 'headline': 'not array'},
    {**POOL, 'primary_text': [3]}, {**POOL, 'primary_text': ['x'] * 6},
    {**POOL, 'headline': ['x' * 256]}, {**POOL, 'description': ['x' * 256]},
    {**POOL, 'primary_text': ['x' * 2201]}, {**POOL, 'extra': []}])
def test_direct_rpc_refuses_invalid_options(flexible_pg, pool):
    import psycopg
    draft, ref = draft_fixture(), uuid4()
    draft['conjuntos'][0]['flexibleTexts'] = pool
    flexible_pg.execute('SET ROLE service_role')
    with pytest.raises(psycopg.Error, match='META_DRAFT_FLEXIBLE_TEXTS_INVALID'):
        save(flexible_pg, ref, draft)
    assert flexible_pg.execute('SELECT trafego_meta_campaign_draft_read(%s,%s)', ('post-owner', ref)).fetchone()[0] is None
    flexible_pg.execute('RESET ROLE')


def test_incomplete_draft_is_editable_and_legacy_still_saves(flexible_pg):
    flexible_pg.execute('SET ROLE service_role')
    draft = draft_fixture()
    assert 'flexibleTexts' not in save(flexible_pg, uuid4(), draft)['draft']['conjuntos'][0]
    draft['conjuntos'][0]['flexibleTexts'] = {'primary_text': [''], 'headline': [], 'description': []}
    assert save(flexible_pg, uuid4(), draft)['draft']['conjuntos'][0]['flexibleTexts']['primary_text'] == ['']
    flexible_pg.execute('RESET ROLE')


@pytest.mark.parametrize('role', ['anon', 'authenticated'])
def test_permission_grants_unchanged(flexible_pg, role):
    import psycopg
    flexible_pg.execute(f'SET ROLE {role}')
    with pytest.raises(psycopg.Error):
        save(flexible_pg, uuid4(), draft_fixture())
    flexible_pg.execute('RESET ROLE')
