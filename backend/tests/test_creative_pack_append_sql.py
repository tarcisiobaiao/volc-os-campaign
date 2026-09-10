import hashlib
import json
from uuid import uuid4
import pytest
from test_meta_v2_approval_sql import pg, MIGRATIONS


def test_append_sql_cas_history_immutable_items_and_owner(pg):
    import psycopg
    from psycopg.types.json import Jsonb
    for filename in ('20260908205124_creative_reuse_packs.sql',
                     '20260908230430_meta_creative_draft_pack_selection.sql',
                     '20260909215941_creative_pack_append_revisions.sql'):
        pg.execute((MIGRATIONS / filename).read_text())
    owner, other, ref = uuid4(), uuid4(), uuid4()
    manifest = {'version': 'creative-pack-v1', 'source': 'STUDIO', 'launch_authorized': False,
                'items': [{'master_ref': str(uuid4()), 'copy_snapshot': {'titulo': 'Original'}}]}
    digest = 'a' * 64
    pg.execute('SET ROLE service_role')
    pg.execute('INSERT INTO criativo_reuso_pack(id,owner_id,nome,manifest,manifest_sha256) VALUES(%s,%s,%s,%s,%s)',
               (ref,owner,'Pack',Jsonb(manifest),digest))
    draft_ref = uuid4()
    pg.execute('INSERT INTO trafego_meta_rascunho_pack(owner_id,draft_ref,adset_key,pack_id,manifest_sha256,master_refs) VALUES(%s,%s,%s,%s,%s,%s)',
               (owner,draft_ref,'adset-1',ref,digest,[manifest['items'][0]['master_ref']]))
    next_manifest = {**manifest, 'items': [*manifest['items'], {'master_ref': str(uuid4())}]}
    canonical = json.dumps(next_manifest, sort_keys=True, separators=(',', ':'))
    def append(who, old_hash, body):
        return pg.execute('SELECT criativo_reuso_pack_append(%s,%s,%s,%s)', (who,ref,old_hash,body)).fetchone()[0]
    assert not append(other,digest,canonical)['ok']
    assert not append(owner,'b'*64,canonical)['ok']
    result = append(owner,digest,canonical)
    assert result['ok'] and result['pack']['manifest'] == next_manifest
    new_hash = hashlib.sha256(canonical.encode()).hexdigest()
    assert result['pack']['manifest_sha256'] == new_hash
    assert pg.execute('SELECT manifest FROM criativo_reuso_pack_revision WHERE pack_id=%s AND manifest_sha256=%s', (ref,digest)).fetchone()[0] == manifest
    locked = pg.execute('SELECT manifest_sha256, master_refs, version FROM trafego_meta_rascunho_pack WHERE draft_ref=%s',(draft_ref,)).fetchone()
    assert locked[0] == digest and str(locked[1][0]) == manifest['items'][0]['master_ref'] and locked[2] == 1
    assert not append(owner,digest,canonical)['ok']
    changed = {**next_manifest, 'items': [{'master_ref': str(uuid4())}, *next_manifest['items']]}
    with pytest.raises(psycopg.Error, match='Existing pack items'):
        append(owner,new_hash,json.dumps(changed))
    duplicate = {**next_manifest, 'items': [*next_manifest['items'], next_manifest['items'][0]]}
    with pytest.raises(psycopg.Error, match='unique'):
        append(owner,new_hash,json.dumps(duplicate))
    excessive = {**next_manifest, 'items': [*next_manifest['items'], *[{'master_ref': str(uuid4())} for _ in range(9)]]}
    with pytest.raises(psycopg.Error, match='10 items'):
        append(owner,new_hash,json.dumps(excessive))
    assert pg.execute('SELECT manifest_sha256 FROM criativo_reuso_pack WHERE id=%s',(ref,)).fetchone()[0] == new_hash
    for role in ('anon', 'authenticated'):
        pg.execute(f'SET ROLE {role}')
        with pytest.raises(psycopg.Error): append(owner,new_hash,canonical)
    pg.execute('RESET ROLE')
    with pytest.raises(psycopg.Error, match='immutable'):
        pg.execute('UPDATE criativo_reuso_pack_revision SET nome=%s WHERE pack_id=%s',('changed',ref))
