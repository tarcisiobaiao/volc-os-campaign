// @vitest-environment jsdom
/**
 * A Bancada tem de saber que a campanha já existe.
 *
 * ⚠️ Medido em 19/08/2026: depois de publicar, `/trafego` continuava dizendo
 * "montar campanha" e `/trafego/nova/74?run=7` continuava com "Lançar campanha"
 * como ação primária. A campanha existia no Google Ads e nas duas telas era
 * como se nada tivesse acontecido.
 *
 * A raiz era o `/subir` não gravar nada. Mas mesmo depois de gravar, o cartão
 * tinha sido acrescentado e o BOTÃO não — e é o botão que o operador olha.
 *
 * ## O que mudou em 03/09/2026, e o que continua igual
 *
 * A ação dominante deixou de se chamar "Lançar campanha": na Bancada ela é
 * **"Provar contra a conta"**, na parada Revisão, porque provar não lança —
 * `validate_only` confere e descarta. A antiga etiqueta prometia o ato errado.
 *
 * O que este arquivo protege NÃO era a etiqueta: era o operador SABER que já
 * existe campanha deste funil antes de criar outra. Isso continua trancado
 * aqui, e agora com o fato mais forte — o id externo e o aviso de que duas
 * campanhas do mesmo funil competem entre si no mesmo leilão.
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
      { id: 'financeiro', titulo: 'Financeiro', descricao: '', exige: null,
        severidade: null, paises_exigem: [] },
    ] }),
    revisarConjuntoPago: async () => ({
      opportunity_id: 74, cluster_id: 1,
      selecionadas: [], excluidas: [], em_revisao_humana: [], negativas: [],
      selected_set_sha256: 'c'.repeat(64), approved_set_sha256: 'c'.repeat(64),
      aprovado_por: 'operador@volc', selection_policy_version: 'v1',
      blockers: [], alertas: [], pode_aprovar: false, porque_nao: 'já aprovado',
    }),
    aprovarConjuntoPago: vi.fn(),
    planoDeMensuracaoVigente: async () => { throw new Error('sem plano gravado'); },
    escreverCopy: vi.fn(),
    salvarCopyEditada: vi.fn(),
    provarCampanha: vi.fn(),
    subirCampanha: vi.fn(),
  },
  PautadorApiError: class extends Error { corpo?: unknown; status = 0; },
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import NovaCampanhaPage from '../NovaCampanhaPage';

afterEach(() => { cleanup(); window.sessionStorage.clear(); vi.clearAllMocks(); });

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

const montar = (etapa = 'revisao') => render(
  <MemoryRouter initialEntries={[`/trafego/nova/74?run=7&etapa=${etapa}`]}>
    <Routes><Route path="/trafego/nova/:opportunityId" element={<NovaCampanhaPage />} /></Routes>
  </MemoryRouter>,
);

describe('a Bancada sincroniza com o que já foi lançado', () => {
  it('sem campanha, nada afirma que existe uma no ar', async () => {
    cockpitDeTrafego.mockResolvedValue(base([]));
    lerCopy.mockResolvedValue({ existe: false });
    montar();
    await waitFor(() => expect(screen.getByText('Maquininha de Cartão')).toBeTruthy());
    // A ação dominante é a prova, e ela não promete criar.
    expect(screen.getByRole('button', { name: /Provar contra a conta/ })).toBeTruthy();
    expect(screen.queryByText(/campanha no ar/)).toBeNull();
  });

  it('com campanha pausada, a Bancada avisa que já existe uma no ar', async () => {
    cockpitDeTrafego.mockResolvedValue(base([{
      campaign_id: '24155134757', campaign_name: 'BR - … / Maquininha / https://…',
      status: 'Paused', google_ads_status: 'PAUSED',
      customer_id: '8017851692', budget_amount: 10, created_at: null,
    }]));
    lerCopy.mockResolvedValue({ existe: false });
    montar();
    // ⚠️ O fato que importa: o operador vê que já existe ANTES de criar outra.
    // Ele aparece em DOIS lugares de propósito — no Pedido, que é a projeção
    // que ele lê antes de agir, e no cartão, que traz o id para conferir.
    await waitFor(() => expect(screen.getByText(/esta pauta já virou campanha/)).toBeTruthy());
    expect(screen.getAllByText('campanhas deste funil já no ar').length).toBeGreaterThan(0);
    expect(screen.getByText('24155134757')).toBeTruthy();
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
