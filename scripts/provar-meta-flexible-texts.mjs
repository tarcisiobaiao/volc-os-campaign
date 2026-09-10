// Explicit official-database smoke. All fixture rows roll back; no Meta API calls.
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const migration = readFileSync(new URL('../supabase/migrations/20260910075813_meta_flexible_texts_draft.sql', import.meta.url), 'utf8');
const body = migration.replace(/^BEGIN;$/m, '').replace(/^COMMIT;$/m, '');
const apply = process.argv.includes('--apply');
const proof = `
SET LOCAL ROLE service_role;
DO $proof$
DECLARE
  ref uuid := gen_random_uuid();
  owner text := 'flexible-pool-smoke-' || ref::text;
  draft jsonb := '{"accountRef":"metaacct_fixture","creativeMode":"flexible","categoryConfirmed":true,"conjuntos":[{"key":"a","flexibleTexts":{"primary_text":["Copy A","Copy B"],"headline":["Título A","Título B"],"description":[]}}],"variations":[{"key":"image-a","adsetKey":"a","assetRightsConfirmed":true,"thirdPartyIdentityCleared":true,"assetPolicyConfirmedAt":"fixture"}]}';
  saved jsonb; actual jsonb; bad jsonb;
BEGIN
  saved := public.trafego_meta_campaign_draft_save(owner,ref,0,draft);
  IF saved->'draft'->'conjuntos' IS DISTINCT FROM draft->'conjuntos'
    OR saved->>'launch_authorized' <> 'false'
    OR saved->'draft'->>'categoryConfirmed' <> 'false'
    OR saved->'draft'->'variations'->0->>'assetRightsConfirmed' <> 'false' THEN
    RAISE EXCEPTION 'FLEXIBLE_SMOKE_SAVE_MISMATCH'; END IF;
  actual := public.trafego_meta_campaign_draft_read(owner,ref);
  IF actual->'draft' IS DISTINCT FROM saved->'draft' THEN RAISE EXCEPTION 'FLEXIBLE_SMOKE_READ_MISMATCH'; END IF;
  IF public.trafego_meta_campaign_draft_read(owner || '-other',ref) IS NOT NULL THEN RAISE EXCEPTION 'FLEXIBLE_SMOKE_OWNER'; END IF;
  draft := jsonb_set(draft,'{conjuntos,0,flexibleTexts,primary_text}','["Copy A","Copy B","Copy C"]');
  saved := public.trafego_meta_campaign_draft_save(owner,ref,1,draft);
  IF saved->>'version' <> '2' THEN RAISE EXCEPTION 'FLEXIBLE_SMOKE_VERSION'; END IF;
  BEGIN
    PERFORM public.trafego_meta_campaign_draft_save(owner,ref,1,draft);
    RAISE EXCEPTION 'FLEXIBLE_SMOKE_CAS_NOT_ENFORCED';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'META_DRAFT_VERSION_CONFLICT' THEN RAISE; END IF; END;
  FOR bad IN SELECT value FROM jsonb_array_elements('[null,[],{}, {"primary_text":[1],"headline":[],"description":[]}, {"primary_text":[],"headline":["1","2","3","4","5","6"],"description":[]}]') LOOP
    BEGIN
      PERFORM public.trafego_meta_campaign_draft_save(owner,ref,2,jsonb_set(draft,'{conjuntos,0,flexibleTexts}',bad));
      RAISE EXCEPTION 'FLEXIBLE_SMOKE_INVALID_ACCEPTED';
    EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'META_DRAFT_FLEXIBLE_TEXTS_INVALID' THEN RAISE; END IF; END;
  END LOOP;
  draft := jsonb_set(draft,'{conjuntos,0,flexibleTexts}','{"primary_text":[""],"headline":[],"description":[]}');
  PERFORM public.trafego_meta_campaign_draft_save(owner,ref,2,draft);
  IF has_function_privilege('anon','public.trafego_meta_campaign_draft_save(text,uuid,integer,jsonb)','EXECUTE')
    OR has_function_privilege('authenticated','public.trafego_meta_campaign_draft_save(text,uuid,integer,jsonb)','EXECUTE') THEN RAISE EXCEPTION 'FLEXIBLE_SMOKE_GRANTS'; END IF;
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
  sha256: createHash('sha256').update(migration).digest('hex'), passed: true, checked: ['save/read','owner isolation','CAS','approval reset','invalid pools','incomplete edit','private grants', ...(apply ? [] : ['idempotency'])] }));
