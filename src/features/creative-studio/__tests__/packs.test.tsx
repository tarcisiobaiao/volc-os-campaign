// @vitest-environment jsdom
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PacksDeCriativos } from '../componentes/PacksDeCriativos';
import { salvarPack, listarPacks } from '../api';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
function Wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>;
}
vi.mock('../api', () => ({ salvarPack:vi.fn(), listarPacks:vi.fn(), selecionarPack:vi.fn() }));
afterEach(cleanup);
const pack = { id:'pack-ref', nome:'Primeiro teste', manifest:{ source:'STUDIO', items:[{}], launch_authorized:false } };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(listarPacks).mockResolvedValue({ packs:[pack], has_more:false } as never); vi.mocked(salvarPack).mockResolvedValue(pack as never); });

it('seleção exige nome e salva somente refs; preparar campanha não lança', async () => {
  render(<Wrapper><PacksDeCriativos masterRefs={['master-ref']} /></Wrapper>);
  expect((screen.getByRole('button',{ name:'Salvar seleção (1)' }) as HTMLButtonElement).disabled).toBe(true);
  expect(listarPacks).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Nome do pack'), { target:{ value:'Primeiro teste' } });
  fireEvent.click(screen.getByRole('button',{ name:'Salvar seleção (1)' }));
  await screen.findByText(/Pack “Primeiro teste” salvo/);
  expect(salvarPack).toHaveBeenCalledWith('Primeiro teste',['master-ref']);
  expect(screen.getByRole('link',{ name:'Preparar campanha' }).getAttribute('href')).toBe('/trafego/meta/nova?pack=pack-ref');
  expect(screen.getByRole('link', { name: /Abrir galeria do pack/ }).getAttribute('href')).toBe('/trafego/meta/packs/pack-ref');
});

it('erro de persistência não vira pack salvo nem sucesso', async () => {
  vi.mocked(salvarPack).mockRejectedValue(new Error('Banco indisponível'));
  render(<Wrapper><PacksDeCriativos masterRefs={['master-ref']} /></Wrapper>);
  fireEvent.change(screen.getByLabelText('Nome do pack'), { target:{ value:'Teste' } });
  fireEvent.click(screen.getByRole('button',{ name:'Salvar seleção (1)' }));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Banco indisponível'));
  expect(screen.queryByText(/Pack “/)).toBeNull();
});
