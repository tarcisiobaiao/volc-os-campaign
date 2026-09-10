// @vitest-environment jsdom
import React from 'react';
import {MemoryRouter} from 'react-router-dom';
import {render, screen, fireEvent, cleanup, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, it, expect, vi} from 'vitest';
import {PrepararPackMeta} from '../PrepararPackMeta';
import {lerPack, type DraftPackSelection} from '@/features/creative-studio/api';
import {pautadorApi} from '@/lib/pautadorApi';
import {criativosApi} from '@/lib/criativosApi';
vi.mock('@/features/creative-studio/api',()=>({lerPack:vi.fn()}));
vi.mock('@/lib/pautadorApi',()=>({pautadorApi:{capacidadesMidiaMeta:vi.fn(),revisarMidiaMeta:vi.fn(),registrarMidiaMeta:vi.fn()}}));
vi.mock('@/lib/criativosApi',()=>({criativosApi:{decidir:vi.fn()}}));
vi.mock('@/features/creative-studio/componentes/PackVisual',()=>({CapaPack:()=> <div>Prévia final</div>,caminhoPack:()=>'/pack'}));
const selection={pack_id:'p',adset_key:'b',manifest_sha256:'h',master_refs:['m'],version:1} as DraftPackSelection;
const pack={id:'p',nome:'Teste',manifest_sha256:'h',manifest:{items:[{master_ref:'m'}]}};
const review={ok:true,resultados:[{master_ref:'m',content_sha256:'a'.repeat(64),aprovacao_humana:true,utilizavel:true,codigo:null,politica:{decisao:'CLEAR',motivos:[]}}]};
const attached=vi.fn();
it('vincula conferência de autorização e envio ao mesmo rascunho',async()=>{
  vi.mocked(pautadorApi.capacidadesMidiaMeta).mockResolvedValue({registro_de_imagem:'ENABLED',motivo:null,escopo_do_envio:'DRAFT_SELECTED_MEDIA_ONLY',inspecao_de_imagem:{disponivel:true,capacidades_ausentes:[]}});
  render(<MemoryRouter><PrepararPackMeta draftRef="draft-1" selection={selection} accountRef="account" accountName="Conta" setName="Conjunto B" demo={false} attached={false} onAttach={attached}/></MemoryRouter>);
  await screen.findByText(/Envio autorizado apenas/);
  expect(pautadorApi.capacidadesMidiaMeta).toHaveBeenCalledWith('account','draft-1',['m']);
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button',{name:'Registrar minha aprovação'}));
  const upload=screen.getByRole('button',{name:'Enviar à conta e montar anúncios'}) as HTMLButtonElement;
  await waitFor(()=>expect(upload.disabled).toBe(false));
  fireEvent.click(upload);
  await waitFor(()=>expect(attached).toHaveBeenCalledOnce());
  expect(pautadorApi.registrarMidiaMeta).toHaveBeenCalledWith('account',review.resultados,'draft-1');
});
function mount(demo=false) {return render(<MemoryRouter><PrepararPackMeta selection={selection} accountRef="account" accountName="Conta" setName="Conjunto B" demo={demo} attached={false} onAttach={attached}/></MemoryRouter>);}
beforeEach(()=>{
  vi.mocked(lerPack).mockResolvedValue(pack as never);
  vi.mocked(pautadorApi.capacidadesMidiaMeta).mockResolvedValue({registro_de_imagem:'ENABLED',motivo:null,inspecao_de_imagem:{disponivel:true,capacidades_ausentes:[]}});
  vi.mocked(pautadorApi.revisarMidiaMeta).mockResolvedValue(review);
  vi.mocked(pautadorApi.registrarMidiaMeta).mockResolvedValue({ok:true,resultados:[{master_ref:'m',asset_ref:'asset',estado:'REGISTERED',motivo:null,codigo:null}]});
});
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('abrir pack não aprova nem envia, e demo não faz chamadas',async()=>{
  const page=mount(); await screen.findByText('Prévia final');
  expect(lerPack).toHaveBeenCalledWith(selection.pack_id,selection.manifest_sha256);
  expect(criativosApi.decidir).not.toHaveBeenCalled(); expect(pautadorApi.registrarMidiaMeta).not.toHaveBeenCalled();
  page.unmount(); vi.clearAllMocks(); mount(true);
  expect(lerPack).not.toHaveBeenCalled(); expect(pautadorApi.capacidadesMidiaMeta).not.toHaveBeenCalled();
});
it('exige aprovação explícita, revisão e segundo clique para upload',async()=>{
  vi.mocked(pautadorApi.revisarMidiaMeta).mockResolvedValueOnce({...review,resultados:[{...review.resultados[0],aprovacao_humana:false,utilizavel:false,codigo:'META_ASSET_FINAL_APPROVAL_REQUIRED'}]}).mockResolvedValue(review);
  mount(); await screen.findByText('Prévia final');
  const upload=screen.getByRole('button',{name:'Enviar à conta e montar anúncios'}) as HTMLButtonElement;
  expect(upload.disabled).toBe(true);
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button',{name:'Registrar minha aprovação'}));
  await waitFor(()=>expect(upload.disabled).toBe(false));
  expect(criativosApi.decidir).toHaveBeenCalledWith('m',{decisao:'aprovado',finalidade:'meta_ads'});
  expect(pautadorApi.registrarMidiaMeta).not.toHaveBeenCalled();
  fireEvent.click(upload); await waitFor(()=>expect(attached).toHaveBeenCalledOnce());
  expect(pautadorApi.registrarMidiaMeta).toHaveBeenCalledWith('account',review.resultados);
});
it('reusar pack já aprovado não tenta duplicar a aprovação',async()=>{
  mount(); await screen.findByText('Prévia final');
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button',{name:'Registrar minha aprovação'}));
  await screen.findByText('Imagem revisada para envio');
  expect(criativosApi.decidir).not.toHaveBeenCalled();
  expect(pautadorApi.revisarMidiaMeta).toHaveBeenCalledTimes(1);
  expect(pautadorApi.registrarMidiaMeta).not.toHaveBeenCalled();
});

it('mostra conferência concluída e autorização de envio como decisões separadas',async()=>{
  vi.mocked(pautadorApi.capacidadesMidiaMeta).mockResolvedValue({registro_de_imagem:'BLOCKED_BY_SERVER_FLAG',motivo:'Envio restrito',inspecao_de_imagem:{disponivel:true,capacidades_ausentes:[]}});
  mount(); await screen.findByText('Prévia final');
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button',{name:'Registrar minha aprovação'}));
  await screen.findByText(/Conferência concluída. As imagens estão revisadas/);
  expect(screen.getByText('Envio ainda não liberado neste servidor para esta conta.')).toBeTruthy();
  expect((screen.getByRole('button',{name:'Enviar à conta e montar anúncios'}) as HTMLButtonElement).disabled).toBe(true);
});

it('revisão vazia nunca autoriza aprovação ou upload',async()=>{
  vi.mocked(pautadorApi.revisarMidiaMeta).mockResolvedValue({ok:true,resultados:[]});
  mount(); await screen.findByText('Prévia final');
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button',{name:'Registrar minha aprovação'}));
  await screen.findByText(/A revisão não devolveu exatamente/);
  expect(criativosApi.decidir).not.toHaveBeenCalled();
  expect((screen.getByRole('button',{name:'Enviar à conta e montar anúncios'}) as HTMLButtonElement).disabled).toBe(true);
});

it('falha na atualização de capacidades não conserva autorização antiga',async()=>{
  vi.mocked(pautadorApi.capacidadesMidiaMeta).mockResolvedValueOnce({registro_de_imagem:'ENABLED',motivo:null,inspecao_de_imagem:{disponivel:true,capacidades_ausentes:[]}}).mockRejectedValueOnce(new Error('Capacidades indisponíveis'));
  mount(); await screen.findByText('Prévia final');
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button',{name:'Registrar minha aprovação'}));
  await screen.findByText('Capacidades indisponíveis');
  expect((screen.getByRole('button',{name:'Enviar à conta e montar anúncios'}) as HTMLButtonElement).disabled).toBe(true);
});

it('trocar conjunto durante conferência descarta resposta antiga e limpa consentimento',async()=>{
  let resolve!: (value: typeof review) => void;
  vi.mocked(pautadorApi.revisarMidiaMeta).mockReturnValueOnce(new Promise(r => {resolve=r;}));
  const view=mount(); await screen.findByText('Prévia final');
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button',{name:'Registrar minha aprovação'}));
  view.rerender(<MemoryRouter><PrepararPackMeta selection={{...selection,adset_key:'c'}} accountRef="account" accountName="Conta" setName="Conjunto C" demo={false} attached={false} onAttach={attached}/></MemoryRouter>);
  resolve(review);
  await waitFor(()=>expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false));
  expect(screen.queryByText('Imagem revisada para envio')).toBeNull();
  expect(criativosApi.decidir).not.toHaveBeenCalled();
  expect((screen.getByRole('button',{name:'Enviar à conta e montar anúncios'}) as HTMLButtonElement).disabled).toBe(true);
});

it('restrição de política aparece sem registrar aprovação nova',async()=>{
  vi.mocked(pautadorApi.revisarMidiaMeta).mockResolvedValue({...review,ok:false,resultados:[{...review.resultados[0],aprovacao_humana:false,utilizavel:false,codigo:'META_ASSET_POLICY_BLOCKED',politica:{decisao:'THIRD_PARTY_IDENTITY_UNVERIFIED',motivos:['Identidade sem autorização'],achados:[{termo:'Marca exemplo'}]}}]});
  mount(); await screen.findByText('Prévia final');
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button',{name:'Registrar minha aprovação'}));
  await screen.findByText(/Conferência concluída com pendências/);
  expect(screen.getByText(/Identidades encontradas: Marca exemplo/)).toBeTruthy();
  expect(criativosApi.decidir).not.toHaveBeenCalled();
});

it('conferência final incompleta não anuncia sucesso nem habilita envio',async()=>{
  vi.mocked(pautadorApi.revisarMidiaMeta).mockResolvedValueOnce({...review,ok:false,resultados:[{...review.resultados[0],aprovacao_humana:false,utilizavel:false,codigo:'META_ASSET_FINAL_APPROVAL_REQUIRED'}]}).mockResolvedValueOnce({ok:true,resultados:[]});
  mount(); await screen.findByText('Prévia final');
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button',{name:'Registrar minha aprovação'}));
  await screen.findByText(/A conferência final está incompleta/);
  expect(screen.queryByText(/Conferência concluída. As imagens estão revisadas/)).toBeNull();
  expect((screen.getByRole('button',{name:'Enviar à conta e montar anúncios'}) as HTMLButtonElement).disabled).toBe(true);
});

it('falha de aprovação identifica imagem e não mantém resultado anterior',async()=>{
  vi.mocked(pautadorApi.revisarMidiaMeta).mockResolvedValueOnce({...review,ok:false,resultados:[{...review.resultados[0],aprovacao_humana:false,utilizavel:false,codigo:'META_ASSET_FINAL_APPROVAL_REQUIRED'}]});
  vi.mocked(criativosApi.decidir).mockRejectedValueOnce(new Error('Serviço indisponível'));
  mount(); await screen.findByText('Prévia final');
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button',{name:'Registrar minha aprovação'}));
  await screen.findByText(/Não foi possível confirmar a aprovação da imagem 1/);
  expect(screen.queryByLabelText('Resultado da conferência')).toBeNull();
  expect((screen.getByRole('button',{name:'Enviar à conta e montar anúncios'}) as HTMLButtonElement).disabled).toBe(true);
});
it('detector ausente nunca habilita envio',async()=>{
  vi.mocked(pautadorApi.capacidadesMidiaMeta).mockResolvedValue({registro_de_imagem:'ENABLED',motivo:null,inspecao_de_imagem:{disponivel:false,capacidades_ausentes:['marca_visual']}});
  mount(); await screen.findByText(/Falta configurar a conferência/);
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button',{name:'Registrar minha aprovação'}));
  await screen.findByText('Imagem revisada para envio');
  expect((screen.getByRole('button',{name:'Enviar à conta e montar anúncios'}) as HTMLButtonElement).disabled).toBe(true);
  expect(pautadorApi.registrarMidiaMeta).not.toHaveBeenCalled();
});
