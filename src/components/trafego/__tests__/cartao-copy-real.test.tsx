// @vitest-environment jsdom
/**
 * O cartão contra o dado REAL do banco.
 *
 * ⚠️ Duas telas brancas em 19/08/2026, a mesma causa: a rota de edição faz a
 * copy passar pela dataclass do engine, que usa OUTRO vocabulário —
 * `texto`/`descricao1` no sitelink, `valores` no snippet. A tela lia
 * `title`/`description1` e `values`, e `undefined.length` derrubou a página
 * inteira duas vezes seguidas.
 *
 * Fixture inventada não pega isso: ela nasce com o vocabulário que o autor do
 * teste tinha em mente. Por isso esta prova usa o JSON EXATO que a API devolveu
 * para o card 74, capturado depois da primeira edição.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CartaoCopy } from '../CartaoCopy';
import real from './copy-real-74.json';
import type { CopyPersistida } from '@/types/trafego';

afterEach(cleanup);

describe('CartaoCopy com o dado real do card 74', () => {
  it('renderiza sem derrubar a página', () => {
    render(<CartaoCopy escrita={real as unknown as CopyPersistida} escrevendo={false}
                       podeEscrever onEscrever={vi.fn()} onEditar={vi.fn()}
                       modelo="" onModelo={vi.fn()} />);
    expect(screen.getByText('títulos')).toBeTruthy();
  });

  it('mostra o snippet mesmo com o vocabulário do engine (`valores`)', () => {
    render(<CartaoCopy escrita={real as unknown as CopyPersistida} escrevendo={false}
                       podeEscrever onEscrever={vi.fn()} onEditar={vi.fn()}
                       modelo="" onModelo={vi.fn()} />);
    expect(screen.getByText(/snippet · Modelos/)).toBeTruthy();
    expect(screen.getByText('Minizinha NFC 2')).toBeTruthy();
  });

  it('mostra o sitelink corrigido, com o título vindo de `texto`', () => {
    render(<CartaoCopy escrita={real as unknown as CopyPersistida} escrevendo={false}
                       podeEscrever onEscrever={vi.fn()} onEditar={vi.fn()}
                       modelo="" onModelo={vi.fn()} />);
    expect(screen.getByDisplayValue('Garantia da Ton')).toBeTruthy();
  });

  it('o callout corrigido está com 23 caracteres, dentro do teto', () => {
    render(<CartaoCopy escrita={real as unknown as CopyPersistida} escrevendo={false}
                       podeEscrever onEscrever={vi.fn()} onEditar={vi.fn()}
                       modelo="" onModelo={vi.fn()} />);
    expect(screen.getByDisplayValue('Garantia 5 Anos PagBank')).toBeTruthy();
  });
});
