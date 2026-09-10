// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { EscolherBusinessMeta } from '../EscolherBusinessMeta';

const mocks = vi.hoisted(() => ({ business: vi.fn(), accounts: vi.fn() }));
vi.mock('@/components/settings/MetaBusinessConnections', () => ({ businessRequest: mocks.business }));
vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: { contasMetaLocal: mocks.accounts } }));
const listing = { selected_id: 'bm-one', connections: [
  { id: 'bm-one', name: 'Portfólio A', enabled: true },
  { id: 'bm-two', name: 'Portfólio B', enabled: true },
  { id: 'bm-disabled', name: 'Desativado', enabled: false },
] };
beforeEach(() => { vi.resetAllMocks(); mocks.business.mockResolvedValue(listing); mocks.accounts.mockResolvedValue({ contas: [{ referencia_opaca: 'conta-A' }] }); });
afterEach(cleanup);
function renderBusiness(demo = false) {
  const accounts = vi.fn(); const change = vi.fn();
  render(<MemoryRouter><EscolherBusinessMeta demo={demo} onAccounts={accounts} onChangeBusiness={change} /></MemoryRouter>);
  return { accounts, change };
}

it('carrega automaticamente BM selecionada e contas, omitindo conexões desativadas', async () => {
  const callbacks = renderBusiness();
  await waitFor(() => expect(callbacks.accounts).toHaveBeenCalledWith([{ referencia_opaca: 'conta-A' }]));
  expect(mocks.business).toHaveBeenCalledTimes(1);
  expect(mocks.accounts).toHaveBeenCalledTimes(1);
  expect((screen.getByLabelText('Portfólio empresarial (BM)') as HTMLSelectElement).value).toBe('bm-one');
  expect(screen.queryByRole('option', { name: 'Desativado' })).toBeNull();
  expect(callbacks.change).not.toHaveBeenCalled();
});

it('trocar a BM confirma a seleção, limpa a conta anterior e busca as novas contas', async () => {
  const callbacks = renderBusiness();
  await waitFor(() => expect(callbacks.accounts).toHaveBeenCalledTimes(1));
  mocks.business.mockResolvedValueOnce({ ok: true });
  mocks.accounts.mockResolvedValueOnce({ contas: [{ referencia_opaca: 'conta-B' }] });
  fireEvent.change(screen.getByLabelText('Portfólio empresarial (BM)'), { target: { value: 'bm-two' } });
  await waitFor(() => expect(callbacks.accounts).toHaveBeenLastCalledWith([{ referencia_opaca: 'conta-B' }]));
  expect(mocks.business).toHaveBeenLastCalledWith('/bm-two/select', {});
  expect(callbacks.change).toHaveBeenCalledTimes(1);
  expect(callbacks.accounts.mock.calls.map(call => call[0])).toEqual([[{ referencia_opaca: 'conta-A' }], [], [{ referencia_opaca: 'conta-B' }]]);
});

it('não consulta conexões nem contas no modo demo', () => {
  renderBusiness(true);
  expect(mocks.business).not.toHaveBeenCalled();
  expect(mocks.accounts).not.toHaveBeenCalled();
  expect(screen.getByText(/conexões reais não são consultadas/)).toBeTruthy();
});

it('uma falha mostra recuperação que relê as conexões e as contas', async () => {
  mocks.business.mockRejectedValueOnce(new Error('Sem conexão agora'));
  const callbacks = renderBusiness();
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Sem conexão agora'));
  expect(mocks.accounts).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }));
  await waitFor(() => expect(callbacks.accounts).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole('alert')).toBeNull();
});

it('sem BM selecionada aguarda a escolha, sem buscar contas de outra conexão', async () => {
  mocks.business.mockResolvedValueOnce({ ...listing, selected_id: null });
  renderBusiness();
  await screen.findByRole('option', { name: 'Portfólio A' });
  expect(mocks.accounts).not.toHaveBeenCalled();
});
