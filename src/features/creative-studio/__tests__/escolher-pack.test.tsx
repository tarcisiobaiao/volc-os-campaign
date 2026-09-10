// @vitest-environment jsdom
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { EscolherPack } from '../componentes/EscolherPack';
import { listarPacks } from '../api';
vi.mock('../api', () => ({ listarPacks: vi.fn() }));
vi.mock('../componentes/PackVisual', () => ({ CapaPack: () => <div>Imagem</div>, caminhoPack: (id: string) => `/packs/${id}` }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it('seleciona pack salvo sem gerar nem publicar e não oferece snapshot como mídia', async () => {
  vi.mocked(listarPacks).mockResolvedValue({ packs: [
    { id: 'studio', nome: 'Encceja', manifest: { source: 'STUDIO', items: [{}] } },
    { id: 'meta', nome: 'Referência', manifest: { source: 'META_SNAPSHOT', items: [{}] } },
  ], has_more: false } as never);
  const selecionar = vi.fn();
  render(<MemoryRouter><EscolherPack selecionado={null} onEscolher={selecionar} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: 'Usar este pack' }));
  expect(selecionar).toHaveBeenCalledWith('studio');
  expect(screen.getAllByRole('button', { name: 'Usar este pack' })).toHaveLength(1);
});
it('erro de listagem tem retry sem substituir erro por biblioteca vazia', async () => {
  vi.mocked(listarPacks).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ packs: [], has_more: false });
  render(<MemoryRouter><EscolherPack selecionado={null} onEscolher={() => {}} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: 'Tentar novamente' }));
  await screen.findByText(/Nenhum pack salvo/);
  expect(listarPacks).toHaveBeenCalledTimes(2);
});

it('busca por nome reinicia a paginação e bloqueia seleção da lista anterior durante busca', async () => {
  vi.mocked(listarPacks).mockResolvedValue({packs:[{id:'studio',nome:'Encceja',manifest:{source:'STUDIO',items:[{}]}}],has_more:true} as never);
  render(<MemoryRouter><EscolherPack selecionado={null} onEscolher={vi.fn()} /></MemoryRouter>);
  await screen.findByRole('button',{name:'Usar este pack'});
  fireEvent.click(screen.getByRole('button',{name:'Próximos packs'}));
  await waitFor(() => expect(listarPacks).toHaveBeenLastCalledWith(20,''));
  fireEvent.change(screen.getByLabelText('Buscar pack pelo nome'),{target:{value:'CNH'}});
  expect(screen.getByRole('button',{name:'Usar este pack'})).toHaveProperty('disabled',true);
  await waitFor(() => expect(listarPacks).toHaveBeenLastCalledWith(0,'CNH'));
});
