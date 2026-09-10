// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SelecionarAtivoMeta } from '../SelecionarAtivoMeta';
import type { AtivoCriacaoMeta } from '@/lib/pautadorApi';

const items: AtivoCriacaoMeta[] = Array.from({length:72}, (_, index) => ({
  referencia_opaca:`metaasset_${index.toString().padStart(24,'0')}`,
  nome:index === 71 ? 'Certificação · Campeão ABO' : `Criativo ${index}`,
  tipo:'image_asset', id_mascarado:null, largura:1080, altura:1350, preview_disponivel:true,
}));
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('busca sem acento encontra peça além dos primeiros60 e preserva a referência opaca', async () => {
  const onChange = vi.fn();
  render(<SelecionarAtivoMeta id="asset" items={items} value="" onChange={onChange}/>);
  fireEvent.click(screen.getByRole('combobox'));
  expect(await screen.findByText(/72 resultados/)).toBeTruthy();
  expect(screen.queryByRole('option',{name:/Campeão ABO/})).toBeNull();
  fireEvent.change(screen.getByRole('combobox',{name:'Buscar criativo pelo nome'}),{target:{value:'campeao'}});
  fireEvent.click(await screen.findByRole('option',{name:/Certificação · Campeão ABO/}));
  expect(onChange).toHaveBeenCalledOnce();
  expect(onChange).toHaveBeenCalledWith(items[71].referencia_opaca);
  expect(screen.queryByRole('option')).toBeNull();
});

it('desabilitado não abre o catálogo nem permite escolha', () => {
  const onChange = vi.fn();
  render(<SelecionarAtivoMeta id="asset" items={items} value="" onChange={onChange} disabled/>);
  const trigger = screen.getByRole('combobox') as HTMLButtonElement;
  expect(trigger.disabled).toBe(true);
  fireEvent.click(trigger);
  expect(screen.queryByRole('option')).toBeNull();
  expect(onChange).not.toHaveBeenCalled();
});

it('desabilitar durante consulta aberta também bloqueia seleção', async () => {
  const onChange = vi.fn();
  const view = render(<SelecionarAtivoMeta id="asset" items={items} value="" onChange={onChange}/>);
  fireEvent.click(screen.getByRole('combobox'));
  await screen.findByRole('option',{name:'Criativo 0 · 1080×1350'});
  view.rerender(<SelecionarAtivoMeta id="asset" items={items} value="" onChange={onChange} disabled/>);
  const option = screen.getByRole('option',{name:'Criativo 0 · 1080×1350'});
  expect(option.getAttribute('aria-disabled')).toBe('true');
  fireEvent.click(option);
  expect(onChange).not.toHaveBeenCalled();
});
