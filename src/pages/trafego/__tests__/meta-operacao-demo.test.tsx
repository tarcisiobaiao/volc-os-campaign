// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import MetaCriacaoPage from '@/pages/trafego/MetaCriacaoPage';
import MetaObjetoPage from '@/pages/trafego/MetaObjetoPage';

Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

afterEach(cleanup);

describe('Meta demonstrativa navegável', () => {
  it('abre a página canônica de campanha sem fingir dado real', () => {
    render(
      <MemoryRouter initialEntries={['/trafego/meta/campanhas/campanha-descoberta-01?modo=demo']}>
        <Routes><Route path="/trafego/meta/:tipo/:objetoId" element={<MetaObjetoPage />} /></Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { name: 'Guia Encceja · Descoberta' })).toBeTruthy();
    expect(screen.getByText(/identidade, entrega e métricas são fictícias/i)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Brasil · Amplo · 18–54' })).toBeTruthy();
    expect(screen.getByRole('button', { name: /editar campanha/i }).hasAttribute('disabled')).toBe(true);
  });

  it('expõe as oito decisões da criação e mantém o envio bloqueado', () => {
    render(
      <MemoryRouter initialEntries={['/trafego/meta/nova?modo=demo&etapa=base']}>
        <MetaCriacaoPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { name: 'Nova campanha Meta' })).toBeTruthy();
    expect(screen.getByRole('navigation', { name: 'Etapas da criação Meta' })).toBeTruthy();
    for (const etapa of ['Base', 'Campanha', 'Orçamento', 'Conjunto', 'Público', 'Anúncio', 'Mensuração', 'Revisão']) {
      expect(screen.getByRole('button', { name: new RegExp(etapa, 'i') })).toBeTruthy();
    }
    fireEvent.click(screen.getByRole('button', { name: /revisãopedido pausado/i }));
    expect(screen.getByText('Pedido que seria criado pausado')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Criar campanha pausada' }).hasAttribute('disabled')).toBe(true);
    expect(screen.getByText(/criação real bloqueada/i)).toBeTruthy();
  });
});
