// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MetaCampaignExplorer, type MetaCampaignExplorerProps } from '../MetaCampaignExplorer';
import type { FinanceiroMeta } from '@/lib/pautadorApi';

vi.mock('../AcoesDaHierarquia', () => ({ AcoesDaHierarquia: (p: {entidade:string;nome:string;referencia:string;contaRef:string;campanhaRef:string;compacto:boolean}) => <div data-testid={`acoes-${p.referencia}`} data-conta={p.contaRef} data-campanha={p.campanhaRef} data-compacto={p.compacto}><button>Preparar pausa: {p.nome}</button>{p.entidade==='anuncio' && <button>Salvar pack: {p.nome}</button>}</div> }));
afterEach(cleanup);
const metrica = (ad_ref:string,adset_ref:string,spend:number,impressions:number,clicks:number) => ({ad_ref,adset_ref,spend,impressions,clicks,ctr:99,cpc:1,cpm:2,source_freshness:'2026-09-10T10:00:00Z',completo:true});
const financeiro = (): FinanceiroMeta => ({ok:true,estado:'OK',currency:'BRL',timezone:'America/Sao_Paulo',periodo_inicio:'2026-09-01',periodo_fim:'2026-09-09',provisorio:false,frescor:null,spend:400,revenue:800,profit_gross:400,roas_ratio:2,retorno_excedente_pct:100,spend_completo:true,revenue_completo:true,impedimentos:[],anuncios_completo:true,anuncios:[metrica('ad1','setA',100,1000,10),metrica('ad2','setA',0,0,0),metrica('ad3','setB',300,3000,90)]});
const props = (): MetaCampaignExplorerProps => ({
  escopo:{contaRef:'contaA',campanhaRef:'campanhaA'}, financeiro:financeiro(), overview:<p>Resumo da campanha real</p>,
  arvore:[{conjunto:{entity_ref:'setA',nome:'ABO',status:'ACTIVE'},anuncios:[
    {anuncio:{entity_ref:'ad1',nome:'Teste A',status:'PAUSED'},criativo:{entity_ref:'creative1',nome:'imagem.png',body:'Texto validado',thumbnail_url:'/demo/peca.svg'}},
    {anuncio:{entity_ref:'ad2',nome:'Teste B'},criativo:{entity_ref:'creative2',nome:'imagem.png',image_url:'javascript:alert(1)'}},
  ]},{conjunto:{entity_ref:'setB',nome:'CBO'},anuncios:[
    {anuncio:{entity_ref:'ad3',nome:'Escala A'},criativo:{entity_ref:'creative1',nome:'imagem.png',body:'Texto validado',thumbnail_url:'/demo/peca.svg'}},
  ]}],
});
const tab = (nome:string) => fireEvent.mouseDown(screen.getByRole('tab',{name:new RegExp(`^${nome}`)}),{button:0,ctrlKey:false});

it('abre a campanha como padrão e mantém os outros níveis alcançáveis', () => {
  render(<MetaCampaignExplorer {...props()}/>);
  expect(screen.getByText('Resumo da campanha real')).toBeTruthy();
  expect(screen.getByRole('tab',{name:'Campanha'}).getAttribute('aria-selected')).toBe('true');
  expect(screen.getByRole('tab',{name:'Conjuntos (2)'})).toBeTruthy();
  expect(screen.getByRole('tab',{name:'Anúncios (3)'})).toBeTruthy();
  expect(screen.getByRole('tab',{name:'Criativos (2)'})).toBeTruthy();
});

it('conjunto abre apenas seus anúncios e limpar restaura a lista', () => {
  render(<MetaCampaignExplorer {...props()}/>); tab('Conjuntos');
  expect(screen.queryByRole('button',{name:'Salvar pack: ABO'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'ABO'}));
  expect(screen.getByRole('button',{name:'Teste A'})).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Escala A'})).toBeNull();
  expect((screen.getByRole('combobox',{name:'Filtrar conjunto'}) as HTMLSelectElement).value).toBe('setA');
  fireEvent.click(screen.getByRole('button',{name:'Limpar filtros'}));
  expect(screen.getByRole('button',{name:'Escala A'})).toBeTruthy();
});

it('detalhe do anúncio mostra métricas próprias e ações com escopo, sem receita atribuída', () => {
  render(<MetaCampaignExplorer {...props()}/>); tab('Anúncios');
  expect(screen.queryByRole('columnheader',{name:'Receita GAM'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Teste A'}));
  const detalhe=screen.getByRole('region',{name:'Detalhes de Teste A'});
  expect(within(detalhe).getByText('R$ 100,00')).toBeTruthy();
  expect(within(detalhe).queryByText('R$ 400,00')).toBeNull();
  expect(within(detalhe).queryByText('ROAS')).toBeNull();
  expect(screen.getByTestId('acoes-ad1').getAttribute('data-conta')).toBe('contaA');
  expect(screen.getByTestId('acoes-ad1').getAttribute('data-campanha')).toBe('campanhaA');
  expect(screen.getByTestId('acoes-ad1').getAttribute('data-compacto')).toBe('true');
  fireEvent.click(screen.getByRole('button',{name:'Ver criativo vinculado'}));
  expect(screen.getByRole('button',{name:'Ver 2 anúncio(s)'})).toBeTruthy();
});

it('agrupa pelo ID, não filename, agrega CTR por denominador e permite ver usos', () => {
  render(<MetaCampaignExplorer {...props()}/>); tab('Criativos');
  expect(screen.getAllByRole('article')).toHaveLength(2);
  const reuso=screen.getByRole('button',{name:'Ver 2 anúncio(s)'}).closest('article')!;
  expect(within(reuso).getByText('R$ 400,00')).toBeTruthy();
  expect(within(reuso).getByText('2,50%')).toBeTruthy();
  expect(within(reuso).queryByText('198,00%')).toBeNull();
  expect(screen.getByText(/não comprovam qual peça veiculou durante todo o período/)).toBeTruthy();
  fireEvent.click(within(reuso).getByRole('button',{name:'Ver 2 anúncio(s)'}));
  expect(screen.getByRole('button',{name:'Teste A'})).toBeTruthy();
  expect(screen.getByRole('button',{name:'Escala A'})).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Teste B'})).toBeNull();
});

it('métricas ausentes ou com outro pai não viram zero nem gasto do conjunto', () => {
  const p=props(); p.financeiro!.anuncios=[metrica('ad1','outro-pai',999,100,1)];
  render(<MetaCampaignExplorer {...p}/>); tab('Anúncios');
  fireEvent.click(screen.getByRole('button',{name:'Teste A'}));
  const detalhe=screen.getByRole('region',{name:'Detalhes de Teste A'});
  expect(within(detalhe).getAllByText('—')).toHaveLength(6);
  expect(within(detalhe).queryByText('R$ 0,00')).toBeNull();
  expect(within(detalhe).getByText(/Não há leitura de métricas/)).toBeTruthy();
});

it('zero medido continua zero e falta de identidade não agrupa criativos desconhecidos', () => {
  const p=props();p.arvore[0].anuncios.forEach(a=>a.criativo=null);
  render(<MetaCampaignExplorer {...p}/>); tab('Criativos');
  expect(screen.getAllByRole('article')).toHaveLength(3);
  expect(screen.getByText('R$ 0,00')).toBeTruthy();
  expect(screen.getAllByText(/identidade não disponível/)).toHaveLength(2);
});

it('recusa mídia perigosa e mostra ausência explicitamente', () => {
  render(<MetaCampaignExplorer {...props()}/>); tab('Criativos');
  expect(screen.getAllByRole('img')).toHaveLength(1);
  expect(screen.getByRole('img').getAttribute('src')).toBe('/demo/peca.svg');
  expect(screen.getByText('Prévia indisponível')).toBeTruthy();
});

it('mantém a publicação reutilizável visível sem inventar IDs e quebra identificadores longos', () => {
  const p=props(); const post='publicacao_'+'1234567890'.repeat(12);
  p.arvore[0].anuncios[0].criativo!.object_story_id=post;
  render(<MetaCampaignExplorer {...p}/>); tab('Criativos');
  expect(screen.getAllByText('Identidade e publicação')).toHaveLength(2);
  expect(screen.getByText(post).classList.contains('break-all')).toBe(true);
  expect(screen.getByText('Não disponível nesta leitura')).toBeTruthy();
  tab('Conjuntos');
  for (const heading of ['Impressões','Cliques','CTR','CPC']) expect(screen.getByRole('columnheader',{name:heading})).toBeTruthy();
});

it('mudança de período ou conta não retém filtro nem detalhe antigo', () => {
  const p=props(); const view=render(<MetaCampaignExplorer {...p}/>); tab('Anúncios');
  fireEvent.change(screen.getByRole('searchbox',{name:'Buscar pelo nome'}),{target:{value:'Teste A'}});
  fireEvent.click(screen.getByRole('button',{name:'Teste A'}));
  view.rerender(<MetaCampaignExplorer {...p} financeiro={{...p.financeiro!,periodo_inicio:'2026-09-02'}}/>);
  expect(screen.getByRole('tab',{name:'Campanha'}).getAttribute('aria-selected')).toBe('true');
  tab('Anúncios'); expect((screen.getByRole('searchbox',{name:'Buscar pelo nome'}) as HTMLInputElement).value).toBe('');
  view.rerender(<MetaCampaignExplorer {...p} escopo={{contaRef:'contaB',campanhaRef:'campanhaB'}}/>);
  expect(screen.getByRole('tab',{name:'Campanha'}).getAttribute('aria-selected')).toBe('true');
});

it('inventário e subtotal parciais são nomeados e não somam linhas financeiras duplicadas', () => {
  const p=props();p.partial=true;p.financeiro!.anuncios!.push({...p.financeiro!.anuncios![0]});
  render(<MetaCampaignExplorer {...p}/>);tab('Criativos');
  expect(screen.getByText(/Leitura parcial. Contagens/)).toBeTruthy();
  const reuso=screen.getByRole('button',{name:'Ver 2 anúncio(s)'}).closest('article')!;
  expect(within(reuso).getByText(/Subtotal disponível: 1 de 2/)).toBeTruthy();
  expect(within(reuso).getByText('R$ 300,00')).toBeTruthy();
});
