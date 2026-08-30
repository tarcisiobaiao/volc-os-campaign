// @vitest-environment jsdom
/**
 * As duas telas têm de saber que a campanha já existe.
 *
 * ⚠️ Medido em 19/08/2026: depois de publicar, `/trafego` continuava dizendo
 * "montar campanha" e `/trafego/nova/74?run=7` continuava com "Lançar campanha"
 * como ação primária. A campanha existia no Google Ads e nas duas telas era
 * como se nada tivesse acontecido.
 *
 * A raiz era o `/subir` não gravar nada. Mas mesmo depois de gravar, eu tinha
 * acrescentado um CARTÃO e não mexido no BOTÃO — e é o botão que o operador
 * olha. Estes testes travam o comportamento, não a existência do cartão.
 */
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const cockpitDeTrafego = vi.hoisted(() => vi.fn());
const lerCopy = vi.hoisted(() => vi.fn());

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: {
    cockpitDeTrafego,
    lerCopy,
    estadoDaTrava: async () => ({
      escrita_permitida: false, destravado_no_codigo: false, env_presente: true,
      motivo: '', explicacao: '',
    }),
    verticaisEPortoes: async () => ({ verticais: [
      { id: 'informativo', titulo: 'Informativo', descricao: '', exige: null,
        severidade: null, paises_exigem: [] },
    ] }),
  },
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import NovaCampanhaPage from '../NovaCampanhaPage';

afterEach(() => { cleanup(); vi.clearAllMocks(); });

const base = (campanhas: unknown[]) => ({
  opportunity_id: 74, cluster_id: 1,
  origem: {
    opportunity_id: 74, run_id: 7, project_id: 2, nicho: 'Maquininha de Cartão',
    slug: 'maquininha', pais: 'BR', idioma: 'pt', vertical: 'financeiro',
    vertical_declarada: null, idioma_declarado: null, dominio: 'creditoup.com.br',
    url_final: 'https://creditoup.com.br/r/x/', url_procedencia: 'wp',
    status_wp: 'publish', post_type: 'r', resumo_da_pesquisa: '', fatos: [],
    tem_texto_da_lp: false,
  },
  triagem: null, grupos: [], descartadas: [], procedencia: null, avisos: [],
  conta: {
    project_id: 2, dominio: 'creditoup.com.br', customer_id: '8017851692',
    login_customer_id: '6016739364', vinculada: true, motivo: null,
  },
  campanhas_lancadas: campanhas,
});

const montar = () => render(
  <MemoryRouter initialEntries={['/trafego/nova/74?run=7']}>
    <Routes><Route path="/trafego/nova/:opportunityId" element={<NovaCampanhaPage />} /></Routes>
  </MemoryRouter>,
);

describe('a barra de ação sincroniza com o que já foi lançado', () => {
  it('sem campanha, a ação primária é "Lançar campanha"', async () => {
    cockpitDeTrafego.mockResolvedValue(base([]));
    lerCopy.mockResolvedValue({ existe: false });
    montar();
    await waitFor(() => expect(screen.getByText('Lançar campanha')).toBeTruthy());
    expect(screen.queryByText(/campanha no ar/)).toBeNull();
  });

  it('com campanha pausada, avisa que está no ar e a ação vira "Lançar outra"', async () => {
    cockpitDeTrafego.mockResolvedValue(base([{
      campaign_id: '24155134757', campaign_name: 'BR - … / Maquininha / https://…',
      status: 'Paused', google_ads_status: 'PAUSED',
      customer_id: '8017851692', budget_amount: 10, created_at: null,
    }]));
    lerCopy.mockResolvedValue({ existe: false });
    montar();
    await waitFor(() => expect(screen.getByText(/campanha no ar/)).toBeTruthy());
    expect(screen.getByText('Lançar outra')).toBeTruthy();
    expect(screen.queryByText('Lançar campanha')).toBeNull();
  });

  it('o cartão do que está no ar aparece com o id e o aviso de duplicidade', async () => {
    cockpitDeTrafego.mockResolvedValue(base([{
      campaign_id: '24155134757', campaign_name: 'BR - … / Maquininha / https://…',
      status: 'Paused', google_ads_status: 'PAUSED',
      customer_id: '8017851692', budget_amount: 10, created_at: null,
    }]));
    lerCopy.mockResolvedValue({ existe: false });
    montar();
    await waitFor(() => expect(screen.getByText('24155134757')).toBeTruthy());
    expect(screen.getByText(/competem entre si/)).toBeTruthy();
  });
});
