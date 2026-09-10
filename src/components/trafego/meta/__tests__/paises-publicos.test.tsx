// @vitest-environment jsdom
import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import { SeletorDePaises, PAISES_META } from '../SeletorDePaises';
import { PainelDePublico } from '../PainelDePublico';
import { conjuntoInicial, type Draft } from '../rascunho';

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

function Paises() {
  const [selecionados, setSelecionados] = useState(['BR']);
  return <><SeletorDePaises id="countries" selecionados={selecionados} impedidos={['AR']} onChange={setSelecionados} />
    <output data-testid="countries">{selecionados.join(',')}</output></>;
}

it('encontra países pelo nome, mantém ISO no contrato e impede incluir um país excluído', async () => {
  render(<Paises />);
  fireEvent.click(screen.getByRole('combobox'));
  fireEvent.change(screen.getByLabelText('Buscar país'), { target: { value: 'Portugal' } });
  fireEvent.click(await screen.findByRole('option', { name: /Portugal/ }));
  expect(screen.getByTestId('countries').textContent).toBe('BR,PT');
  fireEvent.change(screen.getByLabelText('Buscar país'), { target: { value: 'Argentina' } });
  const argentina = await screen.findByRole('option', { name: /Argentina/ });
  expect(argentina.getAttribute('aria-disabled')).toBe('true');
  fireEvent.click(argentina);
  expect(screen.getByTestId('countries').textContent).toBe('BR,PT');
  fireEvent.keyDown(screen.getByLabelText('Buscar país'), { key: 'Escape' });
  fireEvent.click(screen.getByRole('button', { name: 'Remover Brasil' }));
  expect(screen.getByTestId('countries').textContent).toBe('PT');
});

it('o catálogo geográfico tem todos os 249 códigos ISO sem duplicação', () => {
  expect(PAISES_META).toHaveLength(249);
  expect(new Set(PAISES_META.map(p => p.codigo)).size).toBe(249);
  expect(PAISES_META.find(p => p.codigo === 'BR')).toMatchObject({ nome: 'Brasil', bandeira: '🇧🇷' });
});

it('busca públicos automaticamente uma vez por conta e não repete após erro', async () => {
  const ler = vi.fn();
  const props = {
    draft: { accountRef: 'conta-1' } as Draft,
    conjunto: conjuntoInicial('adset-1', 'Conjunto', '2026-10-01T10:00', '10,00'),
    idade: { min: 18, max: 65, motivo: null }, resumoDoConjunto: null,
    onConjunto: vi.fn(), catalogoDePublicos: null, lendoPublicos: false, erroDosPublicos: null,
    onLerPublicos: ler, catalogoDeLugares: null, lendoLugares: false, erroDosLugares: null, onBuscarLugares: vi.fn(),
  };
  const view = render(<PainelDePublico {...props} />);
  await waitFor(() => expect(ler).toHaveBeenCalledTimes(1));
  view.rerender(<PainelDePublico {...props} erroDosPublicos="Falha temporária" />);
  expect(ler).toHaveBeenCalledTimes(1);
  view.rerender(<PainelDePublico {...props} draft={{ accountRef: 'conta-2' } as Draft} />);
  await waitFor(() => expect(ler).toHaveBeenCalledTimes(2));
});
