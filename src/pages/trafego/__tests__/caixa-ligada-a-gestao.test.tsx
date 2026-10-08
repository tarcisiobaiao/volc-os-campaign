// @vitest-environment jsdom
/**
 * A CAIXA DE PROPOSTAS LIGADA AO FLUXO REAL.
 *
 * Antes, a caixa era renderizada sem `aoSubmeter` e toda proposta nascia com
 * "endereço seguro não ligado": botão morto. Agora o que a gestão realiza
 * (ligar campanha, verba, alvo de lance automático) abre "Gerir campanha" no
 * grupo certo, com o motivo trazido da caixa; o que ela não realiza continua
 * bloqueado com a dependência REAL (lance manual vive no grupo).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CaixaDePropostas } from '@/components/trafego/diagnostico/CaixaDePropostas';
import { maquininha } from '@/components/trafego/inventario/fixtureDeProvas';
import { derivarDiagnostico } from '@/lib/diagnostico/derivar';
import { evidenciaDeProva, ID_FGTS } from '@/lib/diagnostico/fixtureDeEvidencia';
import { SEM_ENDERECO_SEGURO, proporMudancas } from '@/lib/diagnostico/propor';
import { caixaLigadaAGestao, preenchimentoDaCaixa } from '@/lib/trafego/gestao/fila';
import type { Proposta } from '@/types/diagnostico';
import type { CampanhaCanonica } from '@/types/trafego';

const api = vi.hoisted(() => ({
  campanhaCanonica: vi.fn(),
  diagnosticoDeEntrega: vi.fn(),
  correspondenciasDaCampanha: vi.fn(() => new Promise(() => {})),
  capacidades: vi.fn(() => new Promise(() => {})),
  inventario: vi.fn(() => {
    throw new Error('a página canônica não pode percorrer o inventário');
  }),
}));
const gestao = vi.hoisted(() => ({
  propostas: vi.fn(),
  propor: vi.fn(),
  aprovar: vi.fn(),
  recusar: vi.fn(),
  aplicar: vi.fn(),
  verificar: vi.fn(),
  reverter: vi.fn(),
  importarCampanha: vi.fn(),
  recomendacoes: vi.fn(),
}));

vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: api }));
vi.mock('@/lib/trafego/gestaoApi', () => ({ gestaoApi: gestao }));
vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import CampanhaCanonPage from '@/pages/trafego/CampanhaCanonPage';

const AGORA = new Date('2026-08-26T18:10:11.000Z');
const diagnostico = derivarDiagnostico(evidenciaDeProva(), ID_FGTS, { agora: AGORA });
const caixa = proporMudancas(diagnostico);

const detalhe: CampanhaCanonica = {
  versao: 2,
  campanha: maquininha,
  identidade: {
    volc_campaign_id: maquininha.volc_campaign_id,
    campaign_lineage_id: null,
    plataforma: 'GOOGLE_ADS',
    conta_externa: maquininha.externa.customer_id,
    id_externo: maquininha.externa.campaign_id,
  },
  conta: { customer_id: maquininha.externa.customer_id, frescor: 'recente', tentativa_resultado: 'ok' },
  manifesto: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.campanhaCanonica.mockResolvedValue(detalhe);
  api.diagnosticoDeEntrega.mockResolvedValue({ versao: 1, diagnostico, propostas: caixa });
  gestao.propostas.mockResolvedValue({ propostas: [], total: 0 });
});
afterEach(cleanup);

const lance: Proposta = { ...caixa.propostas[0], id: 'rever-lance', alvo: 'lance', titulo: 'Rever o lance' };

describe('a ponte é pura e diz a dependência real', () => {
  it('verba e ligar campanha saem liberadas; lance manual continua bloqueado com o porquê', () => {
    const ligada = caixaLigadaAGestao({ ...caixa, propostas: [...caixa.propostas, lance] }, 'MANUAL_CPC');
    expect(ligada.propostas[0].bloqueio).toBeNull();
    expect(ligada.propostas[1].bloqueio?.dependencia).toMatch(/grupo e na palavra-chave/);
    expect(ligada.propostas[1].bloqueio).not.toEqual(SEM_ENDERECO_SEGURO);
  });
  it('lance com estratégia automática vira alvo de lance', () => {
    expect(preenchimentoDaCaixa(lance, 'MAXIMIZE_CONVERSIONS')?.grupo).toBe('alvo_de_lance');
    expect(caixaLigadaAGestao({ ...caixa, propostas: [lance] }, 'MAXIMIZE_CONVERSIONS').propostas[0].bloqueio).toBeNull();
  });
});

describe('a CaixaDePropostas com aoSubmeter', () => {
  it('o gesto chama aoSubmeter com a proposta, e não escreve nada', () => {
    const aoSubmeter = vi.fn();
    render(
      <CaixaDePropostas
        caixa={caixaLigadaAGestao(caixa, 'MANUAL_CPC')}
        abertoInicial="subir-verba"
        aoSubmeter={aoSubmeter}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'submeter para aprovação' }));
    expect(aoSubmeter).toHaveBeenCalledTimes(1);
    expect(aoSubmeter.mock.calls[0][0].id).toBe('subir-verba');
    expect(gestao.propor).not.toHaveBeenCalled();
  });
});

describe('na página, o botão deixa de ser morto', () => {
  it('submeter abre "Gerir campanha" no grupo da proposta, com o motivo da caixa', async () => {
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={cliente}>
        <MemoryRouter initialEntries={[`/trafego/campanhas/${maquininha.volc_campaign_id}`]}>
          <Routes>
            <Route path="/trafego/campanhas/:volcCampaignId" element={<CampanhaCanonPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByRole('heading', { name: 'Gerir campanha' });
    fireEvent.click(await screen.findByText('Subir a verba diária'));
    const submeter = screen.getByRole('button', { name: 'submeter para aprovação' });
    expect(screen.queryByRole('button', { name: 'indisponível nesta tela' })).toBeNull();
    fireEvent.click(submeter);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Orçamento diário' }).getAttribute('aria-pressed')).toBe('true'),
    );
    fireEvent.change(screen.getByLabelText('nova verba diária'), { target: { value: '15' } });
    fireEvent.click(screen.getByRole('button', { name: 'Revisar antes de propor' }));
    expect((screen.getByLabelText('motivo') as HTMLTextAreaElement).value).toMatch(/^Subir a verba diária: /);
    const confirmar = screen.getByRole('group', { name: 'confirmar proposta' });
    expect(within(confirmar).getByText('R$ 10,00')).toBeTruthy();
    expect(within(confirmar).getByText('R$ 15,00')).toBeTruthy();
    expect(gestao.propor).not.toHaveBeenCalled();
  });
});
