// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { criarLeitorDeIdentidadesCompartilhado } from '../leituraCompartilhadaDeIdentidades';
import { IdentidadeDoAnunciante } from '../IdentidadeDoAnunciante';
import { conjuntoInicial } from '../rascunho';
vi.mock('@/lib/pautadorApi',()=>({pautadorApi:{identidadesRegulatoriasMeta:vi.fn()}}));
afterEach(cleanup);
const deferred=<T,>()=>{let resolve!:(v:T)=>void,reject!:(e:Error)=>void;const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const catalogo={complete:true,items:[{reference:'ref',label:'Empresa fixture',beneficiary_name:'Empresa fixture',payer_name:'Pagador fixture',names_available:true,category:'BRAZIL_REGULATION'}]};

it('vários conjuntos compartilham apenas a leitura em voo, sem confirmar automaticamente',async()=>{
  const pending=deferred<typeof catalogo>(),ler=vi.fn(()=>pending.promise),consultar=criarLeitorDeIdentidadesCompartilhado(ler),onChange=vi.fn();
  render(<>{['A','B','C'].map(key=><IdentidadeDoAnunciante key={key} accountRef="conta" conjunto={conjuntoInicial(key,key,'')} onChange={onChange} consultar={consultar}/>)}</>);
  await act(async()=>pending.resolve(catalogo));expect(ler).toHaveBeenCalledTimes(1);expect(screen.getAllByRole('button',{name:'Confirmar anunciante e pagador'})).toHaveLength(3);expect(onChange).not.toHaveBeenCalled();
  await consultar('conta');expect(ler).toHaveBeenCalledTimes(2);
});

it('contas e instâncias de sessão não compartilham resposta nem rejeição; erro permite nova tentativa',async()=>{
  const pending=deferred<number>(),ler=vi.fn(()=>pending.promise),one=criarLeitorDeIdentidadesCompartilhado(ler),two=criarLeitorDeIdentidadesCompartilhado(ler);
  const a=one('A'),b=one('B'),c=two('A');expect(one('A')).toBe(a);expect(b).not.toBe(a);expect(c).not.toBe(a);
  const settled=Promise.allSettled([a,b,c]);pending.reject(new Error('falha fixture'));await settled;expect(ler).toHaveBeenCalledTimes(3);
  ler.mockResolvedValue(2);expect(await one('A')).toBe(2);expect(ler).toHaveBeenCalledTimes(4);
});

it('troca do leitor de sessão descarta resposta antiga mesmo na mesma conta',async()=>{
  const old=deferred<typeof catalogo>(),novo=deferred<typeof catalogo>();const first=criarLeitorDeIdentidadesCompartilhado(()=>old.promise),second=criarLeitorDeIdentidadesCompartilhado(()=>novo.promise),onChange=vi.fn(),conjunto=conjuntoInicial('A','A','');
  const view=render(<IdentidadeDoAnunciante accountRef="conta" conjunto={conjunto} onChange={onChange} consultar={first}/>);
  view.rerender(<IdentidadeDoAnunciante accountRef="conta" conjunto={conjunto} onChange={onChange} consultar={second}/>);
  await act(async()=>old.resolve(catalogo));expect(screen.queryByText('Empresa fixture')).toBeNull();
  await act(async()=>novo.resolve({...catalogo,items:[]}));expect(screen.queryByRole('button',{name:'Confirmar anunciante e pagador'})).toBeNull();expect(onChange).not.toHaveBeenCalled();
});

it('clear invalida resposta de sessão anterior e não remove o pedido da nova sessão',async()=>{
  const old=deferred<string>(),fresh=deferred<string>();const read=vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise),consultar=criarLeitorDeIdentidadesCompartilhado<string>(read);
  const first=consultar('conta');const rejection=expect(first).rejects.toThrow('sessão mudou');await Promise.resolve();consultar.clear();const second=consultar('conta');
  old.resolve('identidade anterior');await rejection;expect(consultar('conta')).toBe(second);fresh.resolve('identidade nova');expect(await second).toBe('identidade nova');expect(read).toHaveBeenCalledTimes(2);
});

it('clear antes do despacho cancela a leitura antiga sem consultar o transport',async()=>{
  const read=vi.fn().mockResolvedValue('identidade'),consultar=criarLeitorDeIdentidadesCompartilhado(read),pending=consultar('conta');consultar.clear();await expect(pending).rejects.toThrow('sessão mudou');expect(read).not.toHaveBeenCalled();
});
