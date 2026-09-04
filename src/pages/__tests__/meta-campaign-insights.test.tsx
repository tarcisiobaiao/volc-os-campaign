// @vitest-environment jsdom
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import { SeletorRedeCampanhas } from '@/components/campaign/SeletorRedeCampanhas';
import MetaCampaignInsightPage from '@/pages/MetaCampaignInsightPage';

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// recharts' <ResponsiveContainer> needs a real ResizeObserver, absent from jsdom.
// The old Meta detail page had no charts at all, so this gap only surfaces now
// that the page mirrors Google's chart grid for visual parity.
beforeAll(() => {
  if (!('ResizeObserver' in window)) {
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    // @ts-expect-error jsdom has no ResizeObserver; recharts only needs the shape above.
    window.ResizeObserver = ResizeObserverStub;
  }
});

describe('detalhe canônico de campanha Meta', () => {
  it('expõe a mesma espinha do dashboard Google, métricas Meta e o caráter demonstrativo', () => {
    render(
      <MemoryRouter initialEntries={['/dashboard/campaign/campanha-descoberta-01?rede=meta&modo=demo']}>
        <Routes>
          <Route path="/dashboard/campaign/:campaignId" element={<MetaCampaignInsightPage />} />
        </Routes>
      </MemoryRouter>,
    );

    // Mesmo header do Google: kicker + H1 genérico "Dashboard da Campanha" — o
    // nome da campanha mora no card de identidade, não no H1.
    expect(screen.getByText('Detalhe da campanha')).toBeTruthy();
    expect(screen.getByRole('heading', { level: 1 }).textContent).toContain('Dashboard da Campanha');
    expect(screen.getByRole('heading', { name: 'Guia Encceja · Descoberta' })).toBeTruthy();

    // Espinha econômica comum: mesmos quatro títulos do Google.
    expect(screen.getByText('Investimento Total')).toBeTruthy();
    expect(screen.getByText('Revenue')).toBeTruthy();
    expect(screen.getAllByText('ROAS').length).toBeGreaterThan(0);
    expect(screen.getByText('Lucro Bruto')).toBeTruthy();

    // Métricas Meta específicas, nos mesmos componentes visuais.
    expect(screen.getByText('Landing Page Views')).toBeTruthy();
    expect(screen.getByText('Janela de Atribuição')).toBeTruthy();

    // Caráter demonstrativo declarado, sem fingir sincronização real.
    expect(screen.getByText('Dados demonstrativos')).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>('button', { name: /Configurar/i }).disabled).toBe(true);
  });

  it('troca a rede pela decisão explícita do operador', () => {
    const mudar = vi.fn();
    render(<SeletorRedeCampanhas rede="meta" onChange={mudar} />);
    fireEvent.click(screen.getByRole('button', { name: 'Google Ads' }));
    expect(mudar).toHaveBeenCalledWith('google');
  });
});
