// @vitest-environment jsdom
/**
 * #3 · a trava de escrita que NINGUÉM CONSEGUIU LER não pode sumir do cartão.
 *
 * `useContasGoogleAds` fazia `estadoDaTrava().catch(() => null)` e o painel
 * renderizava o selo com `{trava && …}`. Falha de leitura → o selo desaparece,
 * e o cartão continua com o escudo azul e a frase "Este sistema opera só sob o
 * MCC…". A ausência do selo é indistinguível de um cartão saudável — e o selo
 * é justamente o que responde "um clique daqui pode gastar dinheiro?".
 *
 * A palavra honesta já existe no repositório e não era usada aqui:
 * `oportunidades/linguagem.ts` → `fraseDoPortao(null).palavra`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

import type { EscopoDeContas, ProjetoComConta } from '@/types/trafego';

const { estadoDaTrava } = vi.hoisted(() => ({ estadoDaTrava: vi.fn() }));

const ESCOPO: EscopoDeContas = {
  mcc: '6016739364',
  nome: 'VOLC Negócios Digitais',
  contas: [
    { customer_id: '8017851692', nome: 'Crédito Up', moeda: 'BRL',
      fuso: 'America/Sao_Paulo', manager: false, teste: false, oculta: false, nivel: 1 },
  ],
  ids_acessiveis: 12,
  ids_fora_do_escopo: 9,
  por_que: 'Este sistema opera apenas sob o MCC da casa.',
};

const PROJETOS: ProjetoComConta[] = [
  { id: 2, dominio: 'creditoup.com.br', nome: 'creditoup.com.br',
    google_ads_customer_id: '8017851692', google_ads_manager_id: '6016739364',
    vinculada: true, google_ads_status: 'connected' },
];

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: {
    escopoDeContas: async () => ESCOPO,
    projetosComConta: async () => ({ projetos: PROJETOS }),
    estadoDaTrava,
    vincularConta: vi.fn(),
    desvincularConta: vi.fn(),
  },
  PautadorApiError: class extends Error {},
}));

const { PainelGoogleAds } = await import('../PainelGoogleAds');

beforeEach(() => {
  estadoDaTrava.mockReset();
});
afterEach(cleanup);

describe('#3 · o selo da trava quando a leitura falha', () => {
  it('a falha de leitura vira uma palavra, não a ausência do selo', async () => {
    estadoDaTrava.mockRejectedValue(new Error('sem resposta'));
    render(<PainelGoogleAds />);

    await waitFor(() => expect(screen.getByText(/Este sistema opera só sob o MCC/)).toBeTruthy());
    expect(screen.getByText(/permissão não verificada/)).toBeTruthy();
    // E não pode afirmar nenhum dos dois vereditos.
    expect(screen.queryByText('escrita LIBERADA')).toBeNull();
    expect(screen.queryByText('escrita bloqueada')).toBeNull();
  });

  it('trava lida e fechada continua dizendo "escrita bloqueada"', async () => {
    estadoDaTrava.mockResolvedValue({
      escrita_permitida: false, destravado_no_codigo: false, env_presente: false,
      motivo: '', explicacao: '',
    });
    render(<PainelGoogleAds />);

    await waitFor(() => expect(screen.getByText('escrita bloqueada')).toBeTruthy());
    expect(screen.queryByText(/permissão não verificada/)).toBeNull();
  });

  it('trava lida e aberta continua dizendo "escrita LIBERADA"', async () => {
    estadoDaTrava.mockResolvedValue({
      escrita_permitida: false, destravado_no_codigo: false, env_presente: true,
      motivo: '', explicacao: '',
    });
    render(<PainelGoogleAds />);

    await waitFor(() => expect(screen.getByText('escrita LIBERADA')).toBeTruthy());
    expect(screen.queryByText(/permissão não verificada/)).toBeNull();
  });
});
