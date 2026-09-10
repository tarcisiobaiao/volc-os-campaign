// @vitest-environment jsdom
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AdicionarSelecaoAoPack } from '../componentes/AdicionarSelecaoAoPack';
import { AdicionarDaBiblioteca } from '../componentes/AdicionarDaBiblioteca';
import { adicionarAssetsAoPack, lerPack, listarPacks, type CreativePack } from '../api';
import { criativosApi } from '@/lib/criativosApi';
vi.mock('../api', () => ({ adicionarAssetsAoPack: vi.fn(), lerPack: vi.fn(), listarPacks: vi.fn() }));
vi.mock('@/lib/criativosApi', () => ({ criativosApi: { assets: vi.fn() } }));
vi.mock('../componentes/PackVisual', () => ({ CapaPack: () => <div>Imagem</div>, caminhoPack: (id: string) => `/packs/${id}` }));
const pack = { id: 'pack', nome: 'Encceja', manifest_sha256: 'a'.repeat(64), manifest: { source: 'STUDIO', items: [{master_ref: 'old'}] } } as CreativePack;
function mount(child: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter>{child}</MemoryRouter></QueryClientProvider>); }
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(lerPack).mockResolvedValue(pack);
  vi.mocked(listarPacks).mockResolvedValue({ packs:[pack], has_more:false });
  vi.mocked(adicionarAssetsAoPack).mockResolvedValue({...pack,manifest_sha256:'b'.repeat(64)});
  vi.mocked(criativosApi.assets).mockResolvedValue({assets:[{id:'old',projetoTitulo:'Existente'}, {id:'new',projetoTitulo:'Nova peça'}],total:2} as never);
});
afterEach(cleanup);

it('a seleção gerada lê hash vigente, deduplica refs e impede duplo clique', async () => {
  mount(<AdicionarSelecaoAoPack masterRefs={['new','new']} />);
  fireEvent.click(screen.getByRole('button',{name:/Adicionar seleção a um pack existente/}));
  const add = await screen.findByRole('button',{name:'Adicionar neste pack'});
  act(() => { fireEvent.click(add); fireEvent.click(add); });
  await screen.findByRole('link',{name:'Abrir pack atualizado'});
  expect(lerPack).toHaveBeenCalledExactlyOnceWith('pack');
  expect(adicionarAssetsAoPack).toHaveBeenCalledExactlyOnceWith('pack',['new'],pack.manifest_sha256);
});

it('conflito de hash não mostra sucesso nem descarta a seleção', async () => {
  vi.mocked(adicionarAssetsAoPack).mockRejectedValue(new Error('O pack mudou em outra aba'));
  mount(<AdicionarSelecaoAoPack masterRefs={['new']} />);
  fireEvent.click(screen.getByRole('button',{name:/Adicionar seleção a um pack existente/}));
  fireEvent.click(await screen.findByRole('button',{name:'Adicionar neste pack'}));
  await screen.findByRole('alert');
  expect(screen.queryByRole('link',{name:'Abrir pack atualizado'})).toBeNull();
  expect(screen.getByRole('button',{name:'Adicionar neste pack'})).toHaveProperty('disabled',false);
});

it('biblioteca não consulta ao montar; impede duplicatas e envia só a seleção nova', async () => {
  const saved=vi.fn(); mount(<AdicionarDaBiblioteca pack={pack} onSaved={saved} />);
  expect(criativosApi.assets).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Adicionar peças da biblioteca'}));
  const old=await screen.findByRole('checkbox',{name:/Existente/});
  expect(old).toHaveProperty('checked',true); expect(old).toHaveProperty('disabled',true);
  fireEvent.click(screen.getByRole('checkbox',{name:'Nova peça'}));
  fireEvent.click(screen.getByRole('button',{name:'Adicionar 1 peças ao pack'}));
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
  expect(adicionarAssetsAoPack).toHaveBeenCalledExactlyOnceWith('pack',['new'],pack.manifest_sha256);
});

it('biblioteca limita seleção à capacidade restante e envia busca paginada', async () => {
  const nearlyFull={...pack,manifest:{...pack.manifest,items:Array.from({length:9},(_,i)=>({master_ref:`old-${i}`}))}};
  mount(<AdicionarDaBiblioteca pack={nearlyFull as CreativePack} onSaved={vi.fn()} />);
  fireEvent.click(screen.getByRole('button',{name:'Adicionar peças da biblioteca'}));
  fireEvent.click(await screen.findByRole('checkbox',{name:'Nova peça'}));
  expect(screen.getByRole('checkbox',{name:'Existente'})).toHaveProperty('disabled',true);
  fireEvent.change(screen.getByLabelText('Buscar imagem pelo nome do projeto'),{target:{value:'Curso'}});
  await waitFor(() => expect(criativosApi.assets).toHaveBeenLastCalledWith({kind:'imagem',busca:'Curso',offset:0,limite:24}));
});
