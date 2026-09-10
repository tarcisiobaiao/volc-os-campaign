"""Real PostgreSQL media authority: grants, fencing, idempotency and isolation."""
import uuid

import pytest
from test_meta_v2_approval_sql import pg, MIGRATIONS


def test_media_ledger_authority(pg):
    import psycopg
    pg.execute('RESET ROLE')
    pg.execute((MIGRATIONS / '20260909080926_meta_media_ledger_install.sql').read_text())
    pg.execute('SET ROLE service_role')
    assert pg.execute('SELECT trafego_meta_media_schema_status()').fetchone()[0]['ready'] is True
    args = ('metaacct_sql_test', 'a' * 64, 'operator-test', 'master-test')
    sql = 'SELECT trafego_meta_reservar_registro_ativo(%s,%s,%s,%s)'
    first = pg.execute(sql, args).fetchone()[0]
    assert first['estado'] == 'DESPACHAR'
    duplicate = pg.execute(sql, args).fetchone()[0]
    assert duplicate['estado'] == 'AMBIGUO'
    assert 'claim_token' not in duplicate
    for token in (None, str(uuid.uuid4())):
        for finish, tail in (
            ('trafego_meta_concluir_registro_ativo', ('image_hash_test', token)),
            ('trafego_meta_marcar_registro_ativo_ambiguo', (token,)),
            ('trafego_meta_falhar_registro_ativo', ('PROVIDER_REJECTED', token)),
        ):
            params = (first['reserva_ref'], *tail)
            with pytest.raises(psycopg.Error, match='META_ASSET_CLAIM_FENCED'):
                pg.execute(f'SELECT {finish}({",".join(["%s"] * len(params))})', params)
    pg.execute('SELECT trafego_meta_concluir_registro_ativo(%s,%s,%s)',
               (first['reserva_ref'], 'image_hash_test', first['claim_token']))
    reused = pg.execute(sql, args).fetchone()[0]
    assert reused['estado'] == 'REGISTRADO'
    assert reused['image_hash'] == 'image_hash_test'
    assert 'claim_token' not in reused
    other = pg.execute(sql, ('metaacct_other_test', *args[1:])).fetchone()[0]
    assert other['estado'] == 'DESPACHAR'
    # Two workers racing on an absent key receive one dispatch token only.
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(2)
    def reserve_concurrently():
        with psycopg.connect(pg.info.dsn, autocommit=True) as conn:
            conn.execute('SET ROLE service_role')
            barrier.wait(timeout=10)
            return conn.execute(sql, ('metaacct_race_test', 'b' * 64, 'operator-test', 'master-test')).fetchone()[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve_concurrently(), range(2)))
    assert sorted(r['estado'] for r in results) == ['AMBIGUO', 'DESPACHAR']
    assert sum('claim_token' in r for r in results) == 1
    with pytest.raises(psycopg.Error):
        pg.execute("UPDATE trafego_meta_asset_registration SET state='AMBIGUO'")
    for role in ('anon', 'authenticated'):
        pg.execute(f'SET ROLE {role}')
        with pytest.raises(psycopg.Error):
            pg.execute(sql, args)
        with pytest.raises(psycopg.Error):
            pg.execute('SELECT * FROM trafego_meta_asset_registration')
    pg.execute('RESET ROLE')
    assert pg.execute("SELECT bool_and(NOT prosecdef) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname IN ('trafego_meta_reservar_registro_ativo','trafego_meta_concluir_registro_ativo','trafego_meta_falhar_registro_ativo','trafego_meta_marcar_registro_ativo_ambiguo')").fetchone()[0]
