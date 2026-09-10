// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { EscolherPublicacaoMeta } from '../EscolherPublicacaoMeta';
const api = vi.hoisted(() => vi.fn());
vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: { postsExistentesMeta: api } }));
const item = { post_ref: `metapost_${'a'.repeat(32)}`, asset_ref:'metaasset_image', label:'ABO vencedor',
  creative_name:'Imagem original', source_ad_names:['ABO vencedor'], destination_url:'https://example.com/',
  message:'Texto original', headline:'Título original', description:'Descrição original', call_to_action_type:'LEARN_MORE', preview_url:null,
  is_flexible:false, image_variants:1, text_variants:1 };
const result = { items:[item],total:1,offset:0,has_more:false,complete:true };
const props = { accountRef:'conta1',pageRef:'pagina1',demo:false,disabled:false,onSelect:vi.fn(),onClear:vi.fn() };
beforeEach(() => { api.mockReset(); api.mockResolvedValue(result); props.onSelect.mockReset(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });
const open = () => fireEvent.click(screen.getByRole('button',{name:/Buscar anúncio existente/}));

it('seleciona o post original com sua copy e referência, sem criar nada', async () => {
  render(<EscolherPublicacaoMeta {...props}/>); open();
  await screen.findByText('ABO vencedor', {selector:'p.font-medium'});
  fireEvent.click(screen.getByRole('button',{name:'Usar este post'}));
  expect(props.onSelect).toHaveBeenCalledWith(item);
  expect(api).toHaveBeenCalledWith('conta1','pagina1','',0);
});

it('não promete preservar variações de um asset feed pelo ID do post', async () => {
  api.mockResolvedValue({...result, items:[{...item, is_flexible:true, image_variants:3, text_variants:5,
    reuse_supported:false, copy_variants:{messages:['Versão A', 'Versão B'], headlines:['Título A'], descriptions:[]}}]});
  render(<EscolherPublicacaoMeta {...props}/>); open();
  await screen.findByText(/Múltiplos assets · 3 imagens · 5 textos/);
  const button = screen.getByRole('button',{name:'Somente referência'}) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  fireEvent.click(button);
  expect(props.onSelect).not.toHaveBeenCalled();
  expect(screen.queryByText(/As variações originais serão mantidas/)).toBeNull();
  expect(screen.getByText('Versão B')).toBeTruthy();
});

it.each(['accountRef','pageRef'] as const)('fecha catálogo e remove resultados ao trocar %s', async key => {
  const view = render(<EscolherPublicacaoMeta {...props}/>); open();
  await screen.findByText('ABO vencedor', {selector:'p.font-medium'});
  view.rerender(<EscolherPublicacaoMeta {...props} {...{[key]:''}}/>);
  expect(screen.queryByRole('button',{name:'Usar este post'})).toBeNull();
  expect((screen.getByRole('button',{name:/Buscar anúncio existente/}) as HTMLButtonElement).disabled).toBe(true);
  expect(props.onSelect).not.toHaveBeenCalled();
});

it('ignora resposta da conta anterior que chega depois da troca', async () => {
  let resolve!: (value:typeof result)=>void;
  api.mockImplementationOnce(() => new Promise(r=>{resolve=r;}));
  const view = render(<EscolherPublicacaoMeta {...props}/>); open();
  view.rerender(<EscolherPublicacaoMeta {...props} accountRef="conta2"/>);
  await act(async()=>{resolve(result);});
  expect(screen.queryByRole('button',{name:'Usar este post'})).toBeNull();
  open();
  await screen.findByRole('button',{name:'Usar este post'});
  expect(api).toHaveBeenLastCalledWith('conta2','pagina1','',0);
});

it('busca com debounce e desabilita seleção dos resultados anteriores', async () => {
  vi.useFakeTimers();
  render(<EscolherPublicacaoMeta {...props}/>);
  await act(async()=>{open();});
  fireEvent.change(screen.getByRole('searchbox'),{target:{value:'CBO'}});
  expect((screen.getByRole('button',{name:'Usar este post'}) as HTMLButtonElement).disabled).toBe(true);
  await act(async()=>{await vi.advanceTimersByTimeAsync(299);});
  expect(api).toHaveBeenCalledTimes(1);
  await act(async()=>{await vi.advanceTimersByTimeAsync(1);});
  expect(api).toHaveBeenLastCalledWith('conta1','pagina1','CBO',0);
});

it('pagina com offset e recusa catálogo incompleto', async () => {
  api.mockResolvedValueOnce({...result,has_more:true});
  render(<EscolherPublicacaoMeta {...props}/>); open();
  fireEvent.click(await screen.findByRole('button',{name:'Próximas publicações'}));
  await waitFor(()=>expect(api).toHaveBeenLastCalledWith('conta1','pagina1','',24));
  api.mockResolvedValue({...result,complete:false});
  fireEvent.click(await screen.findByRole('button',{name:'Anterior'}));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('não foi concluída'));
  expect(screen.queryByRole('button',{name:'Usar este post'})).toBeNull();
});

it('modo demo não consulta posts reais', () => {
  render(<EscolherPublicacaoMeta {...props} demo/>);
  expect((screen.getByRole('button',{name:/Buscar anúncio existente/}) as HTMLButtonElement).disabled).toBe(true);
  expect(api).not.toHaveBeenCalled();
});
