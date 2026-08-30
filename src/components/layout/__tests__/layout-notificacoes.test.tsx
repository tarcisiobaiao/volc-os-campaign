// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Layout } from '@/components/layout/Layout';
import { useIsMobile } from '@/hooks/useIsMobile';

vi.mock('@/hooks/useIsMobile', () => ({ useIsMobile: vi.fn() }));
vi.mock('@/components/layout/Navigation', () => ({
  Navigation: () => <nav aria-label="navegação de teste" />,
}));
vi.mock('@/components/layout/SinoDeAlertas', () => ({
  default: () => <button type="button">notificações de teste</button>,
}));
vi.mock('@/components/CommandPalette', () => ({ openCommandPalette: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Layout, posição global das notificações', () => {
  it('mantém o sino no cabeçalho superior do desktop', () => {
    vi.mocked(useIsMobile).mockReturnValue(false);
    render(<Layout><div>conteúdo</div></Layout>);

    const sino = screen.getByRole('button', { name: 'notificações de teste' });
    expect(sino.closest('header')).toBeTruthy();
    expect(sino.closest('nav')).toBeNull();
  });

  it('mantém o sino no cabeçalho móvel', () => {
    vi.mocked(useIsMobile).mockReturnValue(true);
    render(<Layout><div>conteúdo</div></Layout>);

    expect(screen.getByRole('button', { name: 'notificações de teste' }).closest('header')).toBeTruthy();
  });
});

