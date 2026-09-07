// @vitest-environment jsdom
/**
 * `/settings/campaigns?rede=meta` monta a leitura REAL, não a demonstração.
 *
 * ⚠️ O defeito: a rota montava `MetaCampaignsSettingsDemo` incondicionalmente.
 * O operador pedia a lista de campanhas Meta e recebia números inventados sem
 * ter escolhido demonstração nenhuma — e um cenário fictício que é o destino
 * padrão de uma rota de produção deixou de ser demonstração: virou o painel.
 *
 * O ramo do Google não é exercitado aqui de propósito. Ele não muda neste
 * marco, e montá-lo exigiria simular a camada inteira de dados do Google só
 * para provar uma decisão que é sobre a Meta.
 */
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api } = vi.hoisted(() => ({
  api: {
    contasMetaReadModel: vi.fn(),
    inventarioMetaReadModel: vi.fn(),
    detalheMetaReadModel: vi.fn(),
  },
}));

vi.mock('@/lib/pautadorApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/pautadorApi')>()),
  pautadorApi: api,
}));

vi.mock('@/lib/supabase', () => ({ supabase: {} }));
vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/services/supabaseDataService', () => ({
  useSupabaseData: () => ({ projects: [], campaigns: [], loading: false, error: null, refresh: vi.fn() }),
  supabaseDataService: { getServerDate: async () => '2026-09-07' },
}));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ userProfile: { role: 'admin' } }) }));
vi.mock('@/hooks/useUserFilters', () => ({
  useUserFilters: () => ({ allowedProjectIds: [], allowedCampaignIds: [], hasFilters: false }),
}));
vi.mock('@/hooks/useCampaignComparisons', () => ({ useCampaignComparisons: () => ({}) }));

import CampaignsSettings from '@/pages/settings/CampaignsSettings';

const CONTA = {
  cofre_ativo_id: 'meta_account_h1',
  conta_ref: 'meta-account:h1',
  id_mascarado: '••••1426',
  nome_observado: 'Conta Foco Genial',
  moeda: 'BRL',
  timezone_name: 'America/Sao_Paulo',
  ultima_leitura_ok_em: '2026-09-07T09:00:00Z',
};

const CAMPANHA = {
  meta_campaign_id: 'c-uuid-1',
  entity_ref: 'metaobj_campanha_1',
  id_mascarado: '••••7781',
  nome: 'Encceja · leitura real',
  effective_status: 'ACTIVE',
  objetivo: 'OUTCOME_TRAFFIC',
  observado_em: '2026-09-07T09:00:00Z',
};

beforeEach(() => {
  api.contasMetaReadModel.mockReset().mockResolvedValue({
    ok: true,
    has_snapshot: true,
    estado: 'COM_SNAPSHOT',
    contas: [CONTA],
  });
  api.inventarioMetaReadModel.mockReset().mockResolvedValue({
    ok: true,
    has_snapshot: true,
    estado: 'COM_SNAPSHOT',
    entidade: 'campanhas',
    conta_ref: CONTA.conta_ref,
    moeda: 'BRL',
    fuso: 'America/Sao_Paulo',
    frescor: '2026-09-07T09:00:00Z',
    items: [CAMPANHA],
    completo: true,
    has_more: false,
    proximo_cursor: null,
    motivo: null,
  });
  api.detalheMetaReadModel.mockReset();
});

afterEach(cleanup);

function abrir(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/settings/campaigns" element={<CampaignsSettings />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('a decisão de montagem de /settings/campaigns', () => {
  it('`?rede=meta` lê o read model e NÃO monta a demonstração', async () => {
    abrir('/settings/campaigns?rede=meta');

    expect(await screen.findByText('Encceja · leitura real')).toBeTruthy();
    expect(api.contasMetaReadModel).toHaveBeenCalled();
    expect(api.inventarioMetaReadModel).toHaveBeenCalledWith('campanhas', {
      contaRef: CONTA.conta_ref,
    });

    // Nada do cenário fictício: nem os nomes, nem a faixa, nem o cartão final.
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
    expect(screen.queryByRole('note', { name: 'cenário demonstrativo' })).toBeNull();
    expect(screen.queryByText('Pré-visualização Meta Ads')).toBeNull();

    // A demonstração continua alcançável — por um link que diz o que ela é.
    const porta = screen.getByRole('link', { name: /cenário demonstrativo/i });
    expect(porta.getAttribute('href')).toContain('modo=demo');
  });

  it('`?rede=meta&modo=demo` monta a demonstração, e ela se declara na tela', async () => {
    abrir('/settings/campaigns?rede=meta&modo=demo');

    expect(await screen.findByText('Guia Encceja · Descoberta')).toBeTruthy();
    const faixa = screen.getByRole('note', { name: 'cenário demonstrativo' });
    expect(faixa.textContent).toContain('nada aqui é real');
    expect(faixa.textContent).toContain('Nenhuma conta Meta foi consultada');

    // O cenário fictício não fala com o backend.
    expect(api.contasMetaReadModel).not.toHaveBeenCalled();
    expect(api.inventarioMetaReadModel).not.toHaveBeenCalled();
  });

  it('a demonstração nomeia o retorno com a unidade, em vez de chamá-lo de ROAS', async () => {
    abrir('/settings/campaigns?rede=meta&modo=demo');
    await screen.findByText('Guia Encceja · Descoberta');
    expect(screen.getAllByText('Retorno excedente (%)').length).toBeGreaterThan(0);
  });
});
