// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { IdentidadeDeCanal } from '@/components/trafego/hub/IdentidadeDeCanal';

afterEach(cleanup);

describe('tags de identidade', () => {
  it('plataforma e canal são palavra, e o nome acessível não depende de cor', () => {
    const { container } = render(<IdentidadeDeCanal rede="google" canal="SEARCH" />);
    expect(container.querySelector('[aria-label]')).toBeNull();
    expect(screen.getByText('Google Ads')).toBeTruthy();
    expect(screen.getByText('Search')).toBeTruthy();
  });

  it('PERFORMANCE_MAX é o rótulo canônico; PMAX legado continua lendo Performance Max', () => {
    const { rerender } = render(<IdentidadeDeCanal rede="google" canal="PERFORMANCE_MAX" />);
    expect(screen.getByText('Performance Max')).toBeTruthy();
    rerender(<IdentidadeDeCanal rede="google" canal="PMAX" />);
    expect(screen.getByText('Performance Max')).toBeTruthy();
  });

  it('Meta Ads existe como palavra, sem fingir canal Google', () => {
    render(<IdentidadeDeCanal rede="meta" />);
    expect(screen.getByText('Meta Ads')).toBeTruthy();
    expect(screen.queryByText('Search')).toBeNull();
  });

  it('Display, Demand Gen, Vídeo e Shopping têm rótulo próprio', () => {
    const { rerender } = render(<IdentidadeDeCanal rede="google" canal="DISPLAY" />);
    expect(screen.getByText('Display')).toBeTruthy();
    rerender(<IdentidadeDeCanal rede="google" canal="DEMAND_GEN" />);
    expect(screen.getByText('Demand Gen')).toBeTruthy();
    rerender(<IdentidadeDeCanal rede="google" canal="VIDEO" />);
    expect(screen.getByText('Vídeo')).toBeTruthy();
    rerender(<IdentidadeDeCanal rede="google" canal="SHOPPING" />);
    expect(screen.getByText('Shopping')).toBeTruthy();
  });
});
