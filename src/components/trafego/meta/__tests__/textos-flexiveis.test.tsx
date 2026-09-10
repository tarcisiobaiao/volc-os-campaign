// @vitest-environment jsdom
import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { TextosDoAnuncioFlexivel } from '../TextosDoAnuncioFlexivel';
import { RevisaoHumanaDosAnuncios } from '../RevisaoHumanaDosAnuncios';
import { conjuntoInicial, variacaoInicial, type Draft, type TextosFlexiveisDraft } from '../rascunho';

const inicial: TextosFlexiveisDraft = { primary_text: ['Argumento inicial'], headline: ['Título inicial'], description: [] };
function Editor({ value = inicial, disabled = false }: { value?: TextosFlexiveisDraft; disabled?: boolean }) {
  const [textos, setTextos] = useState(value);
  return <TextosDoAnuncioFlexivel value={textos} onChange={setTextos} conjunto="Conjunto A" imagens={3} disabled={disabled} />;
}
function draftInicial(): Draft {
  return {
    recipeId: 'WEB_SALES_CONVERSION', accountRef: 'conta', pageRef: 'pagina', instagramActorRef: '',
    campaignName: 'Campanha', destinationUrl: 'https://example.test/', nivelDeOrcamento: 'ADSET',
    periodoDeOrcamento: 'DAILY', budgetBrl: '10,00', categoryConfirmed: false, creativeMode: 'flexible',
    conjuntos: [{ ...conjuntoInicial('A', 'Conjunto A', '2026-10-01T10:00'), flexibleTexts: {
      primary_text: ['Argumento A', 'Argumento B'], headline: ['Título A', 'Título B'], description: ['Descrição A', 'Descrição B'],
    } }],
    variations: [{ ...variacaoInicial('v1', 1, 'A'), assetRef: 'asset-local', message: 'Legado principal oculto', headline: 'Legado título oculto', description: 'Legado descrição oculta' }],
  };
}

beforeEach(() => { vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Teste local sem rede')); });
afterEach(() => { cleanup(); expect(globalThis.fetch).not.toHaveBeenCalled(); vi.restoreAllMocks(); });

it.each([
  ['texto principal', 'Texto principal', 1], ['título', 'Título', 1], ['descrição', 'Descrição', 0],
] as const)('adiciona até cinco opções de %s e permite remover a excedente', (nome, rotulo, minimo) => {
  render(<Editor />);
  const adicionar = screen.getByRole('button', { name: `Adicionar ${nome}` });
  for (let index = minimo; index < 5; index += 1) fireEvent.click(adicionar);
  expect((adicionar as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getAllByLabelText(new RegExp(`^${rotulo} \\d+$`))).toHaveLength(5);
  fireEvent.click(adicionar);
  expect(screen.getAllByLabelText(new RegExp(`^${rotulo} \\d+$`))).toHaveLength(5);
  fireEvent.click(screen.getByRole('button', { name: `Remover ${nome} 5` }));
  expect((adicionar as HTMLButtonElement).disabled).toBe(false);
  expect(screen.getAllByLabelText(new RegExp(`^${rotulo} \\d+$`))).toHaveLength(4);
});

it('mantém mínimos obrigatórios e permite ficar sem descrição, sem pendência', () => {
  render(<Editor />);
  expect((screen.getByRole('button', { name: 'Remover texto principal 1' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button', { name: 'Remover título 1' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByRole('status')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar descrição' }));
  expect(within(screen.getByRole('status')).getByText(/itens vazios em descrições/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Descrição 1'), { target: { value: 'Descrição opcional' } });
  expect(screen.queryByRole('status')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Remover descrição 1' }));
  expect(screen.queryByLabelText('Descrição 1')).toBeNull();
  expect(screen.queryByRole('status')).toBeNull();
  expect(screen.getByText('1 textos · 1 títulos · 0 descrições')).toBeTruthy();
});

it('mostra erro de opção vazia, corrige ao preencher e mantém os outros tipos', () => {
  render(<Editor />);
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar texto principal' }));
  expect(screen.getByRole('status').textContent).toContain('Preencha ou remova os itens vazios em textos principais.');
  fireEvent.change(screen.getByLabelText('Texto principal 2'), { target: { value: 'Outro ângulo' } });
  expect(screen.queryByRole('status')).toBeNull();
  expect((screen.getByLabelText('Texto principal 1') as HTMLTextAreaElement).value).toBe('Argumento inicial');
  expect((screen.getByLabelText('Título 1') as HTMLInputElement).value).toBe('Título inicial');
  expect(screen.getByLabelText('Texto principal 2').getAttribute('aria-describedby')).toBeTruthy();
});

it('bloqueado desabilita os grupos de edição sem alterar os textos', () => {
  const onChange = vi.fn();
  const { container } = render(<TextosDoAnuncioFlexivel value={inicial} onChange={onChange} conjunto="A" imagens={2} disabled />);
  expect([...container.querySelectorAll('fieldset')].every(field => field.disabled)).toBe(true);
  expect(onChange).not.toHaveBeenCalled();
});

it('revisão humana exibe todas as opções do pool e não os campos legados invisíveis', () => {
  const draft = draftInicial();
  const onAnuncio = vi.fn();
  const onCategoria = vi.fn();
  render(<RevisaoHumanaDosAnuncios draft={draft} anuncios={draft.variations} bloqueado={false} onCategoria={onCategoria} onAnuncio={onAnuncio} preview={() => <div>Prévia local</div>} />);
  for (const texto of Object.values(draft.conjuntos[0].flexibleTexts!).flat()) expect(screen.getByText(texto)).toBeTruthy();
  expect(screen.queryByText('Legado principal oculto')).toBeNull();
  expect(screen.queryByText('Legado título oculto')).toBeNull();
  expect(screen.queryByText('Legado descrição oculta')).toBeNull();
  expect(screen.getByText(/esta imagem com todas as opções de texto acima/)).toBeTruthy();
  expect(onAnuncio).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('checkbox', { name: /Aprovo o uso da imagem no anúncio 1/ }));
  expect(onAnuncio).toHaveBeenCalledWith('v1', true);
  expect(onCategoria).not.toHaveBeenCalled();
});

it('revisão STATIC mantém cópia legada; descrição vazia no flexível não reaparece como legado', () => {
  const draft = draftInicial();
  draft.conjuntos[0].flexibleTexts!.description = [];
  const props = { anuncios: draft.variations, bloqueado: false, onCategoria: vi.fn(), onAnuncio: vi.fn(), preview: () => null };
  const { rerender } = render(<RevisaoHumanaDosAnuncios {...props} draft={draft} />);
  expect(screen.queryByText('Descrições')).toBeNull();
  expect(screen.queryByText('Legado descrição oculta')).toBeNull();
  rerender(<RevisaoHumanaDosAnuncios {...props} draft={{ ...draft, creativeMode: 'batch' }} />);
  expect(screen.getByText('Legado principal oculto')).toBeTruthy();
  expect(screen.getByText('Legado título oculto')).toBeTruthy();
  expect(screen.getByText('Legado descrição oculta')).toBeTruthy();
  expect(screen.queryByText('Argumento B')).toBeNull();
});
