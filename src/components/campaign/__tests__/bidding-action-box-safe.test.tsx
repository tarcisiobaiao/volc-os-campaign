// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/utils/currencyUtils', () => ({
  formatCostCurrency: (valor: number) => `R$ ${valor.toFixed(2)}`,
}));

import { BiddingActionBox } from '../BiddingActionBox';


describe('BiddingActionBox legado é somente leitura', () => {
  it('mostra a recomendação sem oferecer uma porta de escrita', () => {
    render(<BiddingActionBox
      campaignId="123"
      currentBid={0.5}
      suggestedBid={0.7}
      action="AUMENTAR"
      risk="MEDIO"
      variationPercent={40}
      dataReferencia="2026-08-28"
    />);
    const botao = screen.getByRole('button', {
      name: 'Aplicação bloqueada nesta página legada',
    });
    expect((botao as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText('Aplicar Bidding')).toBeNull();
    expect(screen.getByText(/não envia alterações/)).toBeTruthy();
  });
});
