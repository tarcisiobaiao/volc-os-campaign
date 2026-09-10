import { describe, it, expect } from 'vitest';
import { materializarPack, packMaterializado } from '../materializarPack';
import { type Draft, conjuntoInicial, variacaoInicial } from '../rascunho';
import type { CreativePack, DraftPackSelection } from '@/features/creative-studio/api';
import type { RegistroMidiaMeta } from '@/lib/pautadorApi';
const pack = {id: 'p', nome: 'Pack', manifest_sha256: 'hash', manifest: {source:'STUDIO', launch_authorized:false,
  items:[{master_ref:'m', copy_snapshot:{texto_principal:'Texto', titulo:'Título', descricao:'Descrição', cta_nativa:'LEARN_MORE'}}]}} as CreativePack;
const selection = {pack_id:'p', manifest_sha256:'hash', adset_key:'b', master_refs:['m'], version:1} as DraftPackSelection;
const receipt: RegistroMidiaMeta = {ok:true, resultados:[{master_ref:'m', asset_ref:'asset', estado:'REGISTERED', motivo:null, codigo:null}]};
function draft(): Draft {
  return {accountRef:'account', creativeMode:'batch', variations:[],
    conjuntos:['a','b'].map(k => conjuntoInicial(k,k,'2026-10-01T10:00','10,00'))} as Draft;
}
describe('pack → anúncio por conjunto', () => {
  it('substitui só o placeholder inicial intocado, preservando qualquer edição', () => {
    const d=draft(); d.variations=[variacaoInicial('variation-001',1,'b')];
    expect(materializarPack(d,selection,pack,'account',receipt).variations).toHaveLength(1);
    d.variations[0].message='Meu texto';
    const r=materializarPack(d,selection,pack,'account',receipt);
    expect(r.variations).toHaveLength(1); expect(r.variations[0]).toMatchObject({message:'Meu texto',assetRef:'asset'});
  });
  it('liga no conjunto explícito, traz a copy mas não herda aprovação', () => {
    const result = materializarPack(draft(),selection,pack,'account',receipt);
    expect(result.variations[0]).toMatchObject({adsetKey:'b',assetRef:'asset',message:'Texto',assetRightsConfirmed:false});
    expect(packMaterializado(result,selection)).toBe(true);
    expect(packMaterializado(result,{...selection,adset_key:'a'})).toBe(false);
  });
  it('preenche o anúncio duplicado escolhido sem perder sua copy e identidade', () => {
    const d=draft();
    const duplicated={...variacaoInicial('duplicated',4,'b'),message:'Copy preservada',headline:'Headline preservada',adName:'CP0001_CJ002_AN004 [IMG]'};
    d.variations=[variacaoInicial('empty-first',1,'b'),duplicated];
    const result=materializarPack(d,selection,pack,'account',receipt,'duplicated');
    expect(result.variations).toHaveLength(2);
    expect(result.variations.find(v=>v.key==='duplicated')).toMatchObject({
      assetRef:'asset',message:'Copy preservada',headline:'Headline preservada',adName:'CP0001_CJ002_AN004 [IMG]',
      packOrigin:{packId:'p',masterRef:'m'},
    });
    expect(result.variations.find(v=>v.key==='empty-first')?.assetRef).toBe('');
  });
  it('não duplica no mesmo conjunto ao reaplicar recibo e preserva outro conjunto', () => {
    const first = materializarPack(draft(),selection,pack,'account',receipt);
    const second = materializarPack(first,selection,pack,'account',receipt);
    expect(second.variations).toEqual(first.variations);
    const reuse = materializarPack(second,{...selection,adset_key:'a'},pack,'account',receipt);
    expect(reuse.variations.map(v=>v.adsetKey)).toEqual(['b','a']);
    expect(reuse.variations[0]).toEqual(first.variations[0]);
  });
  it('preserva o modo flexível e seu banco de copies ao inserir o pack', () => {
    const d=draft();
    d.creativeMode='flexible';
    d.conjuntos=d.conjuntos.map(item=>item.key==='b'?{...item,flexibleTexts:{
      primary_text:['Texto A','Texto B'],headline:['Título A'],description:['Descrição A'],
    }}:item);
    const result=materializarPack(d,selection,pack,'account',receipt);
    expect(result.creativeMode).toBe('flexible');
    expect(result.conjuntos.find(item=>item.key==='b')?.flexibleTexts).toEqual({
      primary_text:['Texto A','Texto B'],headline:['Título A'],description:['Descrição A'],
    });
    expect(result.variations[0]).toMatchObject({adsetKey:'b',assetRef:'asset'});
  });
  it.each(['account','set','manifest','partial','duplicate','missing'])('recusa %s sem alterar rascunho', kind => {
    const d=draft(); const s={...selection}; const p=structuredClone(pack); const r=structuredClone(receipt);
    if(kind==='account') d.accountRef='other';
    if(kind==='set') s.adset_key='missing';
    if(kind==='manifest') p.manifest_sha256='different';
    if(kind==='partial') {r.ok=false; r.resultados[0].estado='AMBIGUOUS_REGISTRATION';}
    if(kind==='duplicate') r.resultados.push({...r.resultados[0]});
    if(kind==='missing') r.resultados[0].master_ref='other';
    expect(()=>materializarPack(d,s,p,'account',r)).toThrow();
    expect(d.variations).toEqual([]);
  });
  it('mudança de conta, versão ou mídia impede declarar o pack resolvido', () => {
    const r=materializarPack(draft(),selection,pack,'account',receipt);
    expect(packMaterializado({...r,accountRef:'other'},selection)).toBe(false);
    expect(packMaterializado(r,{...selection,version:2})).toBe(false);
    r.variations[0].assetRef=''; expect(packMaterializado(r,selection)).toBe(false);
  });
});
