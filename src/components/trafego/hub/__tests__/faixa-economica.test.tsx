// @vitest-environment jsdom
/**
 * A faixa do Hub desenhada: nenhum número sem moeda ganha "R$", e falha de
 * leitura não se apresenta como "lendo".
 */
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { FaixaEconomica } from '@/components/trafego/hub/FaixaEconomica';
import { inventarioSaudavel } from '@/components/trafego/inventario/fixtureDeProvas';

afterEach(cleanup);

describe('FaixaEconomica', () => {
  it('carteira sem moeda declarada: custo sem R$ e verdade indisponível', () => {
    const inv = structuredClone(inventarioSaudavel());
    for (const conta of inv.contas) {
      for (const c of conta.campanhas) c.entrega = { ...c.entrega, moeda: null };
    }
    const { container, getByTestId } = render(<FaixaEconomica inventario={inv} carregando={false} />);
    expect(container.textContent).not.toMatch(/R\$/);
    const verdades = [...getByTestId('faixa-economica').querySelectorAll('[data-verdade]')].map((n) =>
      n.getAttribute('data-verdade'),
    );
    expect(verdades[0]).toBe('indisponivel');
  });

  it('declara a janela e a fonte da soma', () => {
    const { container } = render(<FaixaEconomica inventario={inventarioSaudavel()} carregando={false} />);
    expect(container.textContent).toMatch(/últimos 30 dias, espelho do inventário/);
  });

  it('sem inventário e sem carregar não diz "lendo"', () => {
    const { container } = render(<FaixaEconomica inventario={null} carregando={false} />);
    expect(container.textContent).toMatch(/carteira não lida/);
    expect(container.textContent).not.toMatch(/lendo a carteira/);
  });
});
