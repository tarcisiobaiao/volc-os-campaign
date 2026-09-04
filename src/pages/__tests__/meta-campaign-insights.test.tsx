// @vitest-environment jsdom
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { SeletorRedeCampanhas } from '@/components/campaign/SeletorRedeCampanhas';
import MetaCampaignInsightPage from '@/pages/MetaCampaignInsightPage';

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

describe('detalhe canônico de campanha Meta', () => {
  it('expõe economia comum, métricas Meta e o caráter demonstrativo', () => {
    render(
      <MemoryRouter initialEntries={['/dashboard/campaign/campanha-descoberta-01?rede=meta&modo=demo']}>
        <Routes>
          <Route path="/dashboard/campaign/:campaignId" element={<MetaCampaignInsightPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Guia Encceja · Descoberta' })).toBeTruthy();
    expect(screen.getByText(/Dados fictícios para inspeção da interface/i)).toBeTruthy();
    expect(screen.getByText('Gasto Meta')).toBeTruthy();
    expect(screen.getByText('Revenue GAM')).toBeTruthy();
    expect(screen.getByText('Landing page views')).toBeTruthy();
    expect(screen.getByText('Demonstração · não sincronizada')).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>('button', { name: /Pausar campanha/i }).disabled).toBe(true);
  });

  it('troca a rede pela decisão explícita do operador', () => {
    const mudar = vi.fn();
    render(<SeletorRedeCampanhas rede="meta" onChange={mudar} />);
    fireEvent.click(screen.getByRole('button', { name: 'Google Ads' }));
    expect(mudar).toHaveBeenCalledWith('google');
  });
});
