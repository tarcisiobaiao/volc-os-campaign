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
    for (const etapa of ['Base', 'Campanha', 'Orçamento', 'Conjunto', 'Público', 'Anúncios', 'Mensuração', 'Revisão']) {
      expect(screen.getByRole('button', { name: new RegExp(`^${etapa}`, 'i') })).toBeTruthy();
    }
    fireEvent.click(screen.getByRole('button', { name: /^Revisão/i }));
    expect(screen.getByText('O que será enviado à Meta')).toBeTruthy();
    // Não existe botão de criar: um primário desabilitado sugeriria que o ato
    // existe e está apenas indisponível. Ele não existe nesta rota.
    expect(screen.queryByRole('button', { name: /criar campanha/i })).toBeNull();
    expect(screen.getByText(/criar de verdade é outro ato/i)).toBeTruthy();
  });

  it('expõe lote estático explícito e não finge criativo flexível', () => {
    render(
      <MemoryRouter initialEntries={['/trafego/meta/nova?modo=demo&etapa=criativo']}>
        <MetaCriacaoPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole('radiogroup', { name: 'Modo de criativo' })).toBeTruthy();
    expect(screen.getByRole('radio', { name: /lote controlado/i })).toBeTruthy();
    fireEvent.click(screen.getByRole('radio', { name: /flexível/i }));
    expect(screen.getByText('Criativo flexível não emite payload')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /adicionar outro anúncio ao lote/i })).toBeNull();
    fireEvent.click(screen.getByRole('radio', { name: /lote controlado/i }));
    fireEvent.click(screen.getByRole('button', { name: /adicionar outro anúncio ao lote/i }));
    expect(screen.getByText('2 de 10')).toBeTruthy();
    expect(screen.getByText('Anúncio 2')).toBeTruthy();
  });
});
