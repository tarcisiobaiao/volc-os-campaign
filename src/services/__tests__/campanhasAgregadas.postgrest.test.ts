/**
 * Prova contra um PostgREST de verdade (laboratório descartável), não contra dublê.
 *
 * Só roda com VOLC_LAB_POSTGREST_URL apontando para um PostgREST cujo banco tem
 * o schema de produção (pg_dump --schema-only) e o seed do roteiro em
 * handoffs/freedom-lab-20261015/W3-migrations.md: 1203 campanhas em 2026-10-14
 * e os dois carimbos de system_settings como estão em produção.
 *
 *   VOLC_LAB_POSTGREST_URL=http://127.0.0.1:55494 npx vitest run src/services/__tests__/campanhasAgregadas.postgrest.test.ts
 */
import { PostgrestClient } from '@supabase/postgrest-js';
import { describe, expect, it } from 'vitest';
import { lerCampanhasAgregadas, type ClienteRpc } from '../campanhasAgregadas';

const URL_LAB = process.env.VOLC_LAB_POSTGREST_URL;
const PARAMS = { p_project_id: null, p_start_date: '2026-10-14', p_end_date: '2026-10-14' };

describe.skipIf(!URL_LAB)('get_campaigns_aggregated no PostgREST do laboratório', () => {
  const cliente = new PostgrestClient(URL_LAB ?? 'http://invalido');

  it('reproduz o defeito: a chamada antiga com p_limit/p_offset não acha a função', async () => {
    const { error, status } = await cliente.rpc('get_campaigns_aggregated', { ...PARAMS, p_limit: 500, p_offset: 0 });
    expect(status).toBe(404);
    expect(error?.code).toBe('PGRST202');
  });

  it('a chamada nova lê todas as 1203 campanhas em 3 páginas, sem repetir nem perder linha', async () => {
    const { linhas, erro } = await lerCampanhasAgregadas<{ campaign_id: string; aggregated_commission: unknown }>(
      cliente as unknown as ClienteRpc,
      PARAMS,
      { tamanhoPagina: 500 },
    );
    expect(erro).toBeNull();
    expect(linhas).toHaveLength(1203);
    expect(new Set(linhas.map((l) => l.campaign_id)).size).toBe(1203);
    // A função viva devolve colunas que o arquivo de paginação antigo não tem.
    expect(linhas[0]).toHaveProperty('aggregated_commission');
  });

  it('reproduz o 400 da RPC get_last_data_update com o carimbo pt-BR', async () => {
    const { status, error } = await cliente.rpc('get_last_data_update');
    expect(status).toBe(400);
    expect(error?.code).toBe('22008');
  });
});
