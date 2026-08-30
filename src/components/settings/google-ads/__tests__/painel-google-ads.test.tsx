// @vitest-environment jsdom
/**
 * A aba Google Ads MONTA, e mostra só o que é da casa?
 *
 * O smoke do wizard existe porque uma tela ficou branca com `tsc` limpo. Aqui
 * vale o mesmo, e mais uma coisa: este painel é o que oferece contas para
 * vincular, e as duas asserções que importam são "a lista é a da casa" e "o
 * MCC gravado é o da casa" — não aparência.
 *
 * ⚠️ Passar aqui NÃO prova que conta de terceiro está barrada. A guarda é
 * `app/trafego/escopo.py`, e quem prova é `backend/tests/test_trafego.py`:
 * `/provar` e `/subir` recebem `customer_id` no corpo e nenhuma tela alcança.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import type { EscopoDeContas, ProjetoComConta } from '@/types/trafego';

// `vi.hoisted`: a fábrica de `vi.mock` sobe para o topo do arquivo, então um
// `const` comum declarado aqui ainda não existe quando ela roda.
const { vincularConta } = vi.hoisted(() => ({
  vincularConta: vi.fn(async () => ({ vinculado: true, project_id: 1 })),
}));

// Medido em 18/08/2026 por `GET /api/trafego/escopo`.
const ESCOPO: EscopoDeContas = {
  mcc: '6016739364',
  nome: 'VOLC Negócios Digitais',
  contas: [
    { customer_id: '8017851692', nome: 'Crédito Up', moeda: 'BRL', fuso: 'America/Sao_Paulo', manager: false, teste: false, oculta: false, nivel: 1 },
    { customer_id: '3849678045', nome: 'PMUNDO+', moeda: 'BRL', fuso: 'America/Sao_Paulo', manager: false, teste: false, oculta: false, nivel: 1 },
    { customer_id: '5478096539', nome: 'Portal Mundo Mais', moeda: 'BRL', fuso: 'America/Sao_Paulo', manager: false, teste: false, oculta: false, nivel: 1 },
  ],
  ids_acessiveis: 12,
  ids_fora_do_escopo: 9,
  por_que: 'Este sistema opera apenas sob o MCC 6016739364.',
};

// O projeto 1 é o caso real: `google_ads_status='connected'` com os dois ids
// NULOS. É por ele que a divergência com o webgo tem de aparecer escrita.
const PROJETOS: ProjetoComConta[] = [
  { id: 1, dominio: 'portalmundomais.com', nome: 'portalmundomais.com', google_ads_customer_id: null, google_ads_manager_id: null, vinculada: false, google_ads_status: 'connected' },
  { id: 2, dominio: 'creditoup.com.br', nome: 'creditoup.com.br', google_ads_customer_id: '8017851692', google_ads_manager_id: '6016739364', vinculada: true, google_ads_status: 'connected' },
];

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: {
    escopoDeContas: async () => ESCOPO,
    projetosComConta: async () => ({ projetos: PROJETOS }),
    estadoDaTrava: async () => ({
      escrita_permitida: false, destravado_no_codigo: false, env_presente: false,
      motivo: '', explicacao: '',
    }),
    vincularConta,
    desvincularConta: async () => ({ vinculado: false }),
  },
  PautadorApiError: class extends Error {},
}));

import { PainelGoogleAds } from '../PainelGoogleAds';

afterEach(() => {
  cleanup();
  vincularConta.mockClear();
});

describe('PainelGoogleAds', () => {
  it('monta e declara o escopo da casa, com o que ficou de fora', async () => {
    render(<PainelGoogleAds />);
    await waitFor(() => expect(screen.getByText(/VOLC Negócios Digitais/)).toBeTruthy());
    // O número de fora é dito, não omitido: lista curta sem explicação faria o
    // operador procurar a conta que "sumiu".
    expect(screen.getByText(/12 ids, e 9 ficam de fora/)).toBeTruthy();
    expect(screen.getByText(/escrita bloqueada/)).toBeTruthy();
  });

  it('explica o selo do webgo no projeto que está `connected` sem conta', async () => {
    render(<PainelGoogleAds />);
    await waitFor(() => expect(screen.getByText(/portalmundomais\.com/)).toBeTruthy());
    expect(screen.getByText(/ingestão de gasto/)).toBeTruthy();
  });

  it('o seletor oferece só as contas da casa e grava o MCC da casa', async () => {
    render(<PainelGoogleAds />);
    await waitFor(() => expect(screen.getByText(/portalmundomais\.com/)).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: /Vincular/ }));
    await waitFor(() => expect(screen.getByText('PMUNDO+')).toBeTruthy());

    // Três contas, e nenhuma das 36 de cliente que a credencial alcança.
    for (const nome of ['Crédito Up', 'PMUNDO+', 'Portal Mundo Mais']) {
      expect(screen.getByText(nome)).toBeTruthy();
    }

    fireEvent.click(screen.getByText('PMUNDO+'));
    await waitFor(() => expect(vincularConta).toHaveBeenCalledWith(1, '3849678045', '6016739364'));
  });
});
