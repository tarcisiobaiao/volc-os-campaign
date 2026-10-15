// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

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
// O menu do usuário lê a sessão (AuthContext → cliente Supabase). Aqui só
// interessa a posição das peças do cabeçalho.
vi.mock('@/components/layout/MenuDoUsuario', () => ({
  MenuDoUsuario: () => <button type="button">conta de teste</button>,
}));

const montar = (rota = '/') =>
  render(
    <MemoryRouter initialEntries={[rota]}>
      <Layout><div>conteúdo</div></Layout>
    </MemoryRouter>,
  );

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Layout, posição global das notificações', () => {
  it('mantém o sino no cabeçalho superior do desktop', () => {
    vi.mocked(useIsMobile).mockReturnValue(false);
    montar();

    const sino = screen.getByRole('button', { name: 'notificações de teste' });
    expect(sino.closest('header')).toBeTruthy();
    expect(sino.closest('nav')).toBeNull();
  });

  it('mantém o sino no cabeçalho móvel', () => {
    vi.mocked(useIsMobile).mockReturnValue(true);
    montar();

    expect(screen.getByRole('button', { name: 'notificações de teste' }).closest('header')).toBeTruthy();
  });

  it('o cabeçalho do desktop diz onde a pessoa está, pelo mesmo mapa do menu', () => {
    vi.mocked(useIsMobile).mockReturnValue(false);
    montar('/settings/costs');

    const trilha = screen.getByRole('navigation', { name: 'Você está em' });
    expect(trilha.textContent).toContain('Sistema');
    expect(screen.getByText('Custos').getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('button', { name: 'conta de teste' }).closest('header')).toBeTruthy();
  });

  it('numa rota filha o destino vira caminho de volta, e rota fora do mapa não ganha trilha', () => {
    vi.mocked(useIsMobile).mockReturnValue(false);
    montar('/settings/qg-agentico/tarefas/T-1');
    expect(screen.getByRole('link', { name: 'QG Agêntico' }).getAttribute('href')).toBe('/settings/qg-agentico');
    cleanup();

    montar('/rota-inventada');
    expect(screen.queryByRole('navigation', { name: 'Você está em' })).toBeNull();
  });
});
