// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FormatoDeCriativos } from '../FormatoDeCriativos';
import { type Draft, conjuntoInicial, variacaoInicial } from '../rascunho';

afterEach(cleanup);
const draft = (): Draft => ({
  recipeId: 'WEB_SALES_CONVERSION', accountRef: 'account', pageRef: 'page', instagramActorRef: '',
  campaignName: 'Fixture', destinationUrl: 'https://example.com/', categoryConfirmed: true,
  nivelDeOrcamento: 'ADSET', periodoDeOrcamento: 'DAILY', budgetBrl: '10,00', creativeMode: 'flexible',
  conjuntos: ['a', 'b'].map(k => conjuntoInicial(k, k, '2026-10-01T10:00', '10,00')),
  variations: [variacaoInicial('v1', 1, 'a'), variacaoInicial('v2', 2, 'a'), variacaoInicial('v3', 3, 'b')],
});

it('informa anúncios emitidos e imagens sem confundir variações com conjuntos', () => {
  const onChange = vi.fn();
  render(<FormatoDeCriativos draft={draft()} onChange={onChange}/>);
  expect(screen.getByRole('status').textContent).toContain('2 anúncio(s) flexível(is), com 3 imagem(ns)');
  expect(screen.getByRole('status').textContent).toContain('seu próprio banco de textos');
  expect(screen.getByRole('button', { name: 'Flexível: agrupar por conjunto' }).getAttribute('aria-pressed')).toBe('true');
  fireEvent.click(screen.getByRole('button', { name: 'Uma peça por anúncio' }));
  expect(onChange).toHaveBeenCalledWith('batch');
});

it('informa a incompatibilidade com Tráfego e preserva a escolha para correção', () => {
  render(<FormatoDeCriativos draft={{...draft(), recipeId:'TRAFFIC_WEBSITE_LPV_STATIC'}} onChange={vi.fn()}/>);
  expect(screen.getByRole('alert').textContent).toContain('escolha Vendas');
  expect(screen.getByRole('status').textContent).toContain('sujeito à validação da Meta');
});
