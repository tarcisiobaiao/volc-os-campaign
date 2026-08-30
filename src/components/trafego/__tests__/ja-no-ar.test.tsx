// @vitest-environment jsdom
/**
 * Provas do cartão "já no ar".
 *
 * ⚠️ Medido em 19/08/2026: depois de publicar, o cockpit continuava idêntico —
 * mesmo botão "lançar campanha", nenhuma menção à campanha que acabara de
 * nascer. A causa era o `/subir` não gravar nada; a consequência é a doutrina
 * P7 (um termo, uma campanha) ficar sem defesa na tela.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { JaNoAr } from '../JaNoAr';
import type { CampanhaLancada } from '@/types/trafego';

afterEach(cleanup);

const pausada: CampanhaLancada = {
  campaign_id: '24155134757',
  campaign_name: 'BR - 20260819_131546 / Maquininha de Cartão / https://creditoup.com.br/r/x/',
  status: 'Paused', google_ads_status: 'PAUSED',
  customer_id: '8017851692', budget_amount: 10, created_at: null,
};

describe('JaNoAr', () => {
  it('some quando nada foi lançado — não polui a tela do caso comum', () => {
    const { container } = render(<JaNoAr campanhas={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('diz que a pausada NÃO está gastando — é a pergunta do operador', () => {
    render(<JaNoAr campanhas={[pausada]} />);
    expect(screen.getByText(/não está gastando/)).toBeTruthy();
  });

  it('destaca a ATIVA de forma diferente — ela gasta agora', () => {
    render(<JaNoAr campanhas={[{ ...pausada, google_ads_status: 'ENABLED' }]} />);
    expect(screen.getByText(/está gastando agora/)).toBeTruthy();
  });

  it('avisa que relançar cria uma SEGUNDA campanha no mesmo leilão', () => {
    render(<JaNoAr campanhas={[pausada]} />);
    expect(screen.getByText(/segunda/)).toBeTruthy();
    expect(screen.getByText(/competem entre si/)).toBeTruthy();
  });

  it('mostra o id, o nome inteiro e o orçamento', () => {
    render(<JaNoAr campanhas={[pausada]} />);
    expect(screen.getByText('24155134757')).toBeTruthy();
    expect(screen.getByText(/BR - 20260819_131546/)).toBeTruthy();
    expect(screen.getByText('10,00')).toBeTruthy();
  });

  it('leva ao veredito com a conta DA CAMPANHA, não a do projeto', () => {
    const onVerVeredito = vi.fn();
    render(<JaNoAr campanhas={[pausada]} onVerVeredito={onVerVeredito} />);
    fireEvent.click(screen.getByText(/ver o veredito/));
    expect(onVerVeredito).toHaveBeenCalledWith('8017851692', '24155134757');
  });

  it('lista as duas quando houve duplicidade — é o caso que o aviso previne', () => {
    render(<JaNoAr campanhas={[pausada, { ...pausada, campaign_id: '99' }]} />);
    expect(screen.getByText('24155134757')).toBeTruthy();
    expect(screen.getByText('99')).toBeTruthy();
  });
});
