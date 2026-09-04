// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import MetaCriacaoPage from '@/pages/trafego/MetaCriacaoPage';

Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });

const { api } = vi.hoisted(() => ({
  api: {
    estadoMetaLocal: vi.fn(),
    contasMetaLocal: vi.fn(),
    capacidadesCriacaoMeta: vi.fn(),
    ativosCriacaoMeta: vi.fn(),
    previewAtivoMeta: vi.fn(),
    compilarPlanoMeta: vi.fn(),
    validarPlanoMeta: vi.fn(),
  },
}));

vi.mock('@/lib/pautadorApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/pautadorApi')>()),
  pautadorApi: api,
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const conta = {
  referencia_opaca: 'metaacct_conta_de_prova',
  nome: 'Conta de prova',
  id_mascarado: '••••1426',
  status: '1',
  moeda: 'BRL',
  fuso: 'America/Sao_Paulo',
  prontidao_leitura: 'READY_FOR_READ' as const,
  business: null,
};

const imagem = (sufixo: string) => ({
  referencia_opaca: `metaasset_${sufixo}`,
  nome: `Imagem ${sufixo}`,
  tipo: 'image_asset' as const,
  id_mascarado: null,
  largura: 1080,
  altura: 1080,
  preview_disponivel: false,
});

beforeEach(() => {
  api.estadoMetaLocal.mockReset().mockResolvedValue({
    configurado: true, armazenamento: 'macOS Keychain', api_version: 'v26.0',
  });
  api.contasMetaLocal.mockReset().mockResolvedValue({
    ok: true, api_version: 'v26.0', armazenamento: 'macOS Keychain', contas: [conta],
  });
  api.capacidadesCriacaoMeta.mockReset().mockResolvedValue({
    ok: true, api_version: 'v26.0', validate_only: 'BLOCKED_BY_SERVER_FLAG',
    single_static: 'AVAILABLE', static_batch: 'AVAILABLE_UP_TO_10',
    video_creative: 'BLOCKED_UNTIL_VIDEO_CONTRACT_PROVEN',
    flexible_creative: 'BLOCKED_UNTIL_ASSET_FEED_SPEC_PROVEN',
  });
  api.ativosCriacaoMeta.mockReset().mockResolvedValue({
    ok: true, api_version: 'v26.0', account_ref: conta.referencia_opaca, conta,
    paginas: [{
      referencia_opaca: 'metaobj_pagina', nome: 'Página de prova', tipo: 'page' as const,
      id_mascarado: '••••7788', largura: null, altura: null, preview_disponivel: false,
    }],
    imagens: [imagem('um'), imagem('dois')],
    videos: [],
    receita: 'OUTCOME_TRAFFIC_WEBSITE_LPV_STATIC_PAUSED',
  });
  api.previewAtivoMeta.mockReset().mockRejectedValue(new Error('sem prévia no teste'));
  api.compilarPlanoMeta.mockReset().mockResolvedValue({
    ok: true, efeito_externo: 'NENHUM',
    plano: {
      account_ref: conta.referencia_opaca, destination_url: 'https://focogenial.com/',
      api_version: 'v26.0', plano_sha256: 'a'.repeat(64), estado_ao_nascer: 'PAUSED',
      operacoes: [],
    },
  });
  api.validarPlanoMeta.mockReset();
});

afterEach(cleanup);

function abrir(etapa: string) {
  return render(
    <MemoryRouter initialEntries={[`/trafego/meta/nova?etapa=${etapa}`]}>
      <MetaCriacaoPage />
    </MemoryRouter>,
  );
}

async function esperarAtivos() {
  await waitFor(() => expect(api.ativosCriacaoMeta).toHaveBeenCalled());
}

/** Satisfaz as decisões que a bancada exige antes de liberar a conferência.
 *  A confirmação de categoria especial é uma delas, e é deliberada: sem ela o
 *  plano não pode ser compilado. */
function confirmarEnquadramento() {
  fireEvent.click(screen.getByRole('button', { name: /^Campanha/i }));
  fireEvent.click(screen.getByRole('checkbox', { name: /não é de crédito, emprego/i }));
}

/** Vai até a revisão e dispara a conferência do plano no backend. */
async function compilarPelaRevisao() {
  confirmarEnquadramento();
  fireEvent.click(screen.getByRole('button', { name: /^Revisão/i }));
  fireEvent.click(await screen.findByRole('button', { name: /conferir o plano/i }));
  await waitFor(() => expect(api.compilarPlanoMeta).toHaveBeenCalled());
}

describe('Bancada de criação Meta — contrato do rascunho', () => {
  it('lê orçamento com ponto decimal sem multiplicar a verba por cem', async () => {
    abrir('orcamento');
    await esperarAtivos();
    fireEvent.change(screen.getByLabelText(/orçamento diário/i), {
      target: { value: '10.00' },
    });
    await waitFor(() => expect(screen.getAllByText(/R\$\s*10,00/).length).toBeGreaterThan(0));
    await compilarPelaRevisao();
    expect(api.compilarPlanoMeta.mock.calls[0][0].daily_budget_minor).toBe(1000);
  });

  it('trata milhar pt-BR sem transformar mil reais em dez', async () => {
    abrir('orcamento');
    await esperarAtivos();
    fireEvent.change(screen.getByLabelText(/orçamento diário/i), {
      target: { value: '1.000' },
    });
    await compilarPelaRevisao();
    expect(api.compilarPlanoMeta.mock.calls[0][0].daily_budget_minor).toBe(100000);
  });

  it('envia a recusa explícita de Advantage+ público, nunca a omissão', async () => {
    abrir('publico');
    await esperarAtivos();
    await compilarPelaRevisao();
    expect(api.compilarPlanoMeta.mock.calls[0][0].advantage_audience).toBe(false);
  });

  it('mantém variation_key única ao remover uma linha do meio e adicionar outra', async () => {
    abrir('criativo');
    await esperarAtivos();
    fireEvent.click(screen.getByRole('radio', { name: /lote controlado/i }));
    const adicionar = () => screen.getByRole('button', { name: /adicionar outro anúncio/i });
    fireEvent.click(adicionar());
    fireEvent.click(adicionar());
    await waitFor(() => expect(screen.getByText('3 de 10')).toBeTruthy());
    fireEvent.click(screen.getAllByRole('button', { name: /remover/i })[1]);
    await waitFor(() => expect(screen.getByText('2 de 10')).toBeTruthy());
    fireEvent.click(adicionar());
    await waitFor(() => expect(screen.getByText('3 de 10')).toBeTruthy());
    const chaves = screen.getAllByTestId('variacao-chave').map((no) => no.textContent);
    expect(new Set(chaves).size).toBe(chaves.length);
  });

  it('modo individual compila exatamente uma variação, mesmo depois de um lote', async () => {
    abrir('criativo');
    await esperarAtivos();
    fireEvent.click(screen.getByRole('radio', { name: /lote controlado/i }));
    fireEvent.click(screen.getByRole('button', { name: /adicionar outro anúncio/i }));
    await waitFor(() => expect(screen.getByText('2 de 10')).toBeTruthy());
    fireEvent.click(screen.getByRole('radio', { name: /individual/i }));
    await waitFor(() => expect(screen.getByText('1 de 10')).toBeTruthy());
    await compilarPelaRevisao();
    const enviado = api.compilarPlanoMeta.mock.calls[0][0];
    expect(enviado.variations).toHaveLength(1);
  });

  it('não expõe o nome da variável de ambiente do servidor ao operador', async () => {
    const { container } = abrir('revisao');
    await esperarAtivos();
    expect(container.innerHTML).not.toContain('META_VALIDATE_ONLY_ENABLED');
  });
});
