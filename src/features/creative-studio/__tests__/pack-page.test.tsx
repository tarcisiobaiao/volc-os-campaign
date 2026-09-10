// @vitest-environment jsdom
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import CreativePackPage from '@/pages/trafego/CreativePackPage';
import { lerPack, listarPacks } from '../api';
import { criativosApi } from '@/lib/criativosApi';
vi.mock('../api', () => ({ lerPack: vi.fn(), listarPacks: vi.fn() }));
vi.mock('@/lib/criativosApi', () => ({ criativosApi: { job: vi.fn() } }));
vi.mock('@/components/layout/Layout', () => ({ Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(lerPack).mockResolvedValue({ id: 'pack', nome: 'Encceja', manifest: { source: 'STUDIO', items: [
    { master_ref: 'master1', job_id: 'job1', content_hash: 'hash1', copy_snapshot: { titulo: 'Primeira copy', texto_principal: 'Texto um', descricao: 'Descrição', cta_nativa: 'LEARN_MORE' } },
    { master_ref: 'master2', job_id: 'job2', content_hash: 'hash2', copy_snapshot: { titulo: 'Segunda copy', texto_principal: 'Texto dois', descricao: '', cta_nativa: 'SIGN_UP' } },
  ] } } as never);
  vi.mocked(criativosApi.job).mockImplementation(async id => ({ renditions: [{ masterId: id === 'job1' ? 'master1' : 'master2', contentHash: id === 'job1' ? 'hash1' : 'hash2', estado: 'pronta', previewUrl: `https://images.example/${id}.png` }] }) as never);
});
function abrir() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={['/packs/pack']}><Routes><Route path="/packs/:packId" element={<CreativePackPage />} /></Routes></MemoryRouter></QueryClientProvider>);
}
it('deep link carrega pack e alterna imagem e copy sem gerar nem publicar', async () => {
  abrir();
  await screen.findByText('Primeira copy');
  expect(lerPack).toHaveBeenCalledWith('pack');
  expect((await screen.findByAltText('Peça 1 do pack Encceja')).getAttribute('src')).toContain('job1.png');
  fireEvent.click(screen.getByRole('button', { name: 'Ver peça 2' }));
  await screen.findByText('Segunda copy');
  expect((await screen.findByAltText('Peça 2 do pack Encceja')).getAttribute('src')).toContain('job2.png');
  expect(screen.getByRole('link', { name: /Preparar campanha/ }).getAttribute('href')).toBe('/trafego/meta/nova?pack=pack');
});
it('não mostra imagem de outro master do mesmo job', async () => {
  vi.mocked(criativosApi.job).mockResolvedValue({ renditions: [{ masterId: 'foreign', contentHash: 'hash1', estado: 'pronta', previewUrl: 'https://images.example/foreign.png' }] } as never);
  abrir();
  await screen.findByText('Primeira copy');
  expect(screen.queryByAltText('Peça 1 do pack Encceja')).toBeNull();
  expect((screen.getByRole('button', { name: 'Baixar imagem' }) as HTMLButtonElement).disabled).toBe(true);
});

it('a vitrine de packs busca no servidor pelo nome e mantém links para a galeria', async () => {
  vi.mocked(listarPacks).mockResolvedValue({packs:[{id:'p',nome:'CNH',manifest:{items:[]}}],has_more:false} as never);
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={['/packs']}><Routes><Route path="/packs" element={<CreativePackPage />} /></Routes></MemoryRouter></QueryClientProvider>);
  await screen.findByRole('heading',{name:'CNH'});
  fireEvent.change(screen.getByLabelText('Buscar pack pelo nome'),{target:{value:'CNH'}});
  await waitFor(() => expect(listarPacks).toHaveBeenLastCalledWith(0,'CNH'));
  expect(screen.getByRole('link',{name:/CNH.*Explorar pack/}).getAttribute('href')).toBe('/trafego/meta/packs/p');
});
