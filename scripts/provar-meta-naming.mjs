// Explicit official DB proof. Synthetic drafts/reservations ALWAYS roll back.
// Default also rolls back DDL; --apply commits only the reviewed migration.
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const authority = spawnSync('python3', ['scripts/verificar_autoridade_supabase.py'], { cwd: root, encoding: 'utf8' });
if (authority.status !== 0) { process.stderr.write(authority.stderr || authority.stdout || 'Authority check failed'); process.exit(1); }
const migration = readFileSync(new URL('../supabase/migrations/20260910081646_meta_campaign_naming_reservations.sql', import.meta.url), 'utf8');
const body = migration.replace(/^BEGIN;$/m, '').replace(/^COMMIT;$/m, '');
const apply = process.argv.includes('--apply');
const proof = `
SET LOCAL ROLE service_role;
DO $proof$
DECLARE
  ref uuid := gen_random_uuid();
  second_ref uuid := gen_random_uuid();
  third_ref uuid := gen_random_uuid();
  owner_a text := 'naming-smoke-' || ref::text;
  owner_b text := 'naming-smoke-other-' || ref::text;
  account_id text := '999' || translate(replace(ref::text,'-',''),'abcdef','123456');
  opaque text;
  draft jsonb := '{"accountRef":"metaacct_fixture","creativeMode":"flexible","categoryConfirmed":true,"naming":{"enabled":true,"topic":"Tema sintético","site":"Fixture","landingType":"LP_R","quiz":false,"conversionLabel":"VC","adsetNumbers":{"a":1},"adNumbers":{"a:image-a":1},"generated":{"campaign":"0001 - Fixture"}},"conjuntos":[{"key":"a","flexibleTexts":{"primary_text":["Copy A","Copy B"],"headline":["Título A","Título B"],"description":[]}}],"variations":[{"key":"image-a","adsetKey":"a","existingPostRef":"metapost_cccccccccccccccccccccccccccccccc","assetRightsConfirmed":true,"thirdPartyIdentityCleared":true,"assetPolicyConfirmedAt":"fixture"}]}';
  saved jsonb; actual jsonb; first_reservation jsonb; next_reservation jsonb; bad jsonb;
BEGIN
  opaque := 'metaacct_' || substr(encode(sha256(convert_to('META_ADS:account:' || account_id,'UTF8')),'hex'),1,24);
  draft := jsonb_set(draft,'{accountRef}',to_jsonb(opaque));
  saved := public.trafego_meta_campaign_draft_save(owner_a,ref,0,draft);
  IF saved->'draft'->'naming' IS DISTINCT FROM draft->'naming'
    OR saved->'draft'->'conjuntos' IS DISTINCT FROM draft->'conjuntos'
    OR saved->'draft'->'variations'->0->>'existingPostRef' IS DISTINCT FROM draft->'variations'->0->>'existingPostRef'
    OR saved->>'launch_authorized' <> 'false'
    OR saved->'draft'->>'categoryConfirmed' <> 'false'
    OR saved->'draft'->'variations'->0->>'assetRightsConfirmed' <> 'false' THEN
    RAISE EXCEPTION 'NAMING_SMOKE_SAVE_MISMATCH'; END IF;
  first_reservation := public.trafego_meta_campaign_naming_reserve(owner_a,ref,1,account_id,opaque,35,12,true);
  IF first_reservation->>'campaign_number' <> '36' OR first_reservation->>'history_count' <> '12'
    OR first_reservation->>'account_ref' <> opaque OR first_reservation->>'history_complete' <> 'true'
    OR first_reservation ? 'account_id' THEN RAISE EXCEPTION 'NAMING_SMOKE_BOOTSTRAP'; END IF;
  IF public.trafego_meta_campaign_naming_reserve(owner_a,ref,1,account_id,opaque,80,22,true) IS DISTINCT FROM first_reservation THEN
    RAISE EXCEPTION 'NAMING_SMOKE_IDEMPOTENCY'; END IF;
  PERFORM public.trafego_meta_campaign_draft_save(owner_b,second_ref,0,draft);
  next_reservation := public.trafego_meta_campaign_naming_reserve(owner_b,second_ref,1,account_id,opaque,35,12,true);
  IF next_reservation->>'campaign_number' <> '37' THEN RAISE EXCEPTION 'NAMING_SMOKE_OWNER_COUNTER_COLLISION'; END IF;
  draft := jsonb_set(draft,'{naming,campaignNumber}','36');
  draft := jsonb_set(draft,'{naming,accountRef}',to_jsonb(opaque));
  saved := public.trafego_meta_campaign_draft_save(owner_a,ref,1,draft);
  actual := public.trafego_meta_campaign_draft_read(owner_a,ref);
  IF actual->'draft' IS DISTINCT FROM saved->'draft' OR actual->>'version' <> '2' THEN RAISE EXCEPTION 'NAMING_SMOKE_READ'; END IF;
  IF public.trafego_meta_campaign_draft_read(owner_b,ref) IS NOT NULL THEN RAISE EXCEPTION 'NAMING_SMOKE_OWNER'; END IF;
  BEGIN
    PERFORM public.trafego_meta_campaign_naming_reserve(owner_a,ref,1,account_id,opaque,35,12,true);
    RAISE EXCEPTION 'NAMING_SMOKE_CAS_ACCEPTED';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'META_DRAFT_VERSION_CONFLICT' THEN RAISE; END IF; END;
  BEGIN
    PERFORM public.trafego_meta_campaign_naming_reserve(owner_a,ref,2,account_id,'metaacct_aaaaaaaaaaaaaaaaaaaaaaaa',35,12,true);
    RAISE EXCEPTION 'NAMING_SMOKE_ACCOUNT_ACCEPTED';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'META_NAMING_ACCOUNT_CHANGED' THEN RAISE; END IF; END;
  BEGIN
    PERFORM public.trafego_meta_campaign_naming_reserve(owner_a,ref,2,account_id,opaque,35,12,false);
    RAISE EXCEPTION 'NAMING_SMOKE_PARTIAL_ACCEPTED';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'META_NAMING_INVALID' THEN RAISE; END IF; END;
  FOR bad IN SELECT value FROM jsonb_array_elements('[null,[],{}, {"enabled":true}, {"enabled":true,"topic":"","site":"","landingType":"","quiz":false,"conversionLabel":"","adsetNumbers":{},"adNumbers":{"a:b":false},"generated":{}}]') LOOP
    BEGIN
      PERFORM public.trafego_meta_campaign_draft_save(owner_a,ref,2,jsonb_set(draft,'{naming}',bad));
      RAISE EXCEPTION 'NAMING_SMOKE_INVALID_ACCEPTED';
    EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'META_DRAFT_NAMING_INVALID' THEN RAISE; END IF; END;
  END LOOP;
  PERFORM public.trafego_meta_campaign_draft_archive(owner_a,ref,2);
  BEGIN
    PERFORM public.trafego_meta_campaign_naming_reserve(owner_a,ref,3,account_id,opaque,35,12,true);
    RAISE EXCEPTION 'NAMING_SMOKE_ARCHIVED_ACCEPTED';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'META_DRAFT_ARCHIVED' THEN RAISE; END IF; END;
  PERFORM public.trafego_meta_campaign_draft_save(owner_a,third_ref,0,draft);
  IF public.trafego_meta_campaign_naming_reserve(owner_a,third_ref,1,account_id,opaque,35,12,true)->>'campaign_number' <> '38' THEN
    RAISE EXCEPTION 'NAMING_SMOKE_ARCHIVE_RECYCLED_NUMBER'; END IF;
  IF has_function_privilege('anon','public.trafego_meta_campaign_naming_reserve(text,uuid,integer,text,text,integer,integer,boolean)','EXECUTE')
    OR has_function_privilege('authenticated','public.trafego_meta_campaign_naming_reserve(text,uuid,integer,text,text,integer,integer,boolean)','EXECUTE')
    OR has_table_privilege('service_role','meta_draft_private.campaign_naming_reservation','DELETE')
    OR has_table_privilege('service_role','meta_draft_private.campaign_naming_reservation','SELECT') THEN RAISE EXCEPTION 'NAMING_SMOKE_GRANTS'; END IF;
END $proof$;
RESET ROLE;
`;
const sql = apply
  ? migration + '\nBEGIN;\n' + proof + '\nROLLBACK;\n'
  : 'BEGIN;\n' + body + '\n' + body + '\n' + proof + '\nROLLBACK;\n';
const result = spawnSync('ssh', ['-i','/Users/mac/.ssh/volc_hetzner_claude_ed25519','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','root@178.156.196.149',
  'docker exec -i supabase-db psql -X -U postgres -d postgres -v ON_ERROR_STOP=1'], { input: sql, encoding: 'utf8', timeout: 60000 });
if (result.status !== 0) { process.stderr.write(result.stderr || 'SQL smoke failed'); process.exit(1); }
console.log(JSON.stringify({ authority: 'https://database.agenciavolc.com.br', mode: apply ? 'migration-applied-fixture-rolled-back' : 'migration-and-fixture-rolled-back',
  sha256: createHash('sha256').update(migration).digest('hex'), passed: true,
  checked: ['save/read naming', 'flexible/existing-post preservation', 'approval reset', 'physical account bootstrap', 'idempotency', 'cross-owner next number', 'CAS', 'account binding', 'incomplete history', 'invalid naming', 'archive without recycling', 'private grants', ...(apply ? [] : ['migration idempotency'])] }));
