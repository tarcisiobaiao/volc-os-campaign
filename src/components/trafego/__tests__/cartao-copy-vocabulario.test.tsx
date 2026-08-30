// @vitest-environment jsdom
/**
 * A tela não pode sumir por causa do formato do JSON.
 *
 * ⚠️ Defeito real de 19/08/2026: a rota de edição faz a copy passar pela
 * dataclass do engine, que chama o título de sitelink de `texto`. A tela lia
 * `title`. Depois da primeira edição, `comprimentoEfetivo(undefined)` fez
 * `undefined.replace(...)` e derrubou a PÁGINA INTEIRA em tela branca —
 * levando junto tudo o que estava correto.
 *
 * Duas defesas, e as duas são provadas aqui: a função tolera vazio, e a tela
 * lê os dois vocabulários.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CartaoCopy, comprimentoEfetivo, tituloDoSitelink } from '../CartaoCopy';
import type { CopyPersistida } from '@/types/trafego';

afterEach(cleanup);

describe('comprimentoEfetivo tolera vazio', () => {
  it.each([undefined, null, ''])('não explode com %p', (v) => {
    expect(comprimentoEfetivo(v as unknown as string)).toBe(0);
  });

  it('continua contando o DKI pelo fallback, não pelo cru', () => {
    expect(comprimentoEfetivo('{KeyWord:Maquininha}')).toBe('Maquininha'.length);
  });
});

describe('tituloDoSitelink lê os dois vocabulários', () => {
  it('aceita o nome da tela', () => {
    expect(tituloDoSitelink({ title: 'Garantia da Ton' })).toBe('Garantia da Ton');
  });
  it('aceita o nome do engine — é o que a edição grava', () => {
    expect(tituloDoSitelink({ texto: 'Garantia da Ton' })).toBe('Garantia da Ton');
  });
  it('sem nenhum dos dois devolve string vazia, nunca undefined', () => {
    expect(tituloDoSitelink({})).toBe('');
    expect(tituloDoSitelink(undefined as unknown as Record<string, unknown>)).toBe('');
  });
});

const escritaCom = (sitelinks: unknown[]): CopyPersistida => ({
  existe: true, status: 'done', erro: null, perdida: false,
  keywords: ['maquininha'], segundos: 12, criado_em: null,
  medicao: {}, pendencias: [],
  copy: {
    headlines: ['Um título'], descriptions: ['Uma descrição'],
    sitelinks, callouts: ['Um callout'],
    snippet: { header: 'Modelos', values: ['A'] },
  },
} as unknown as CopyPersistida);

const montar = (sitelinks: unknown[]) =>
  render(<CartaoCopy escrita={escritaCom(sitelinks)} escrevendo={false}
                     podeEscrever onEscrever={vi.fn()} onEditar={vi.fn()}
                     modelo="" onModelo={vi.fn()} />);

describe('CartaoCopy sobrevive aos dois formatos', () => {
  it('renderiza sitelink no vocabulário da tela', () => {
    montar([{ title: 'Garantia da Ton', description1: 'x' }]);
    expect(screen.getByDisplayValue('Garantia da Ton')).toBeTruthy();
  });

  it('renderiza sitelink no vocabulário do engine — o caso da tela branca', () => {
    montar([{ texto: 'Garantia da Ton', descricao1: 'x' }]);
    expect(screen.getByDisplayValue('Garantia da Ton')).toBeTruthy();
  });

  it('sitelink sem título nenhum não derruba o cartão', () => {
    montar([{}]);
    expect(screen.getByText('títulos')).toBeTruthy();
  });
});
