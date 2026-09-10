// @vitest-environment jsdom
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, it, expect, vi } from 'vitest';
import { MetaBusinessConnections, businessRequest } from './MetaBusinessConnections';
import IntegrationsSettings from '@/pages/settings/IntegrationsSettings';
vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession: vi.fn(async () => ({ data: { session: { access_token: 'session-fixture' } } })) } } }));
vi.mock('@/components/layout/Layout', () => ({ Layout: ({children}: any) => <main>{children}</main> }));
vi.mock('@/hooks/useIsMobile', () => ({ useIsMobile: () => false }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ userProfile: { role: 'ADMIN' } }) }));
vi.mock('@/hooks/useMetaCapiSites', () => ({ useMetaCapiSites: () => ({ sites: [], loading: false }) }));
vi.mock('@/components/settings/google-ads/PainelGoogleAds', () => ({ PainelGoogleAds: () => <div>Google</div> }));
vi.mock('@/components/settings/meta-capi/SiteList', () => ({ SiteList: () => <div>CAPI</div> }));
vi.mock('@/components/settings/meta-capi/MetaCapiWizard', () => ({ MetaCapiWizard: () => null }));

const empty = { connections: [], selected_id: null, vault_ready: true, truncated: false };
beforeEach(() => {
  vi.stubGlobal('localStorage', { setItem: vi.fn(), getItem: vi.fn(), removeItem: vi.fn() });
  vi.stubEnv('VITE_PAUTADOR_API_URL', 'http://localhost:8010');
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(empty), { status: 200 })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

it('a rota integrações renderiza o título e a aba oficial, sem ReferenceError', async () => {
  render(<MemoryRouter initialEntries={['/settings/integrations?tab=meta-ads']}><IntegrationsSettings /></MemoryRouter>);
  expect(screen.getByRole('heading', { level: 1 })).toBeTruthy();
  expect(screen.getByRole('tab', { name: 'Meta Ads' }).getAttribute('aria-selected')).toBe('true');
  await screen.findByText('Nenhuma conexão cadastrada. Adicione o primeiro Business Manager abaixo.');
});

it('o token é enviado apenas ao backend, limpo do campo e nunca salvo no browser', async () => {
  render(<MemoryRouter><MetaBusinessConnections /></MemoryRouter>);
  await screen.findByText(/Nenhuma conexão cadastrada/);
  fireEvent.change(screen.getByLabelText('Nome para identificar o negócio'), { target: { value: 'Minha BM' } });
  fireEvent.change(screen.getByLabelText('Business Manager ID'), { target: { value: '123456789' } });
  const input = screen.getByLabelText('Token de usuário de sistema') as HTMLInputElement;
  expect(input.type).toBe('password');
  fireEvent.change(input, { target: { value: 'fixture-only-not-a-real-token' } });
  fireEvent.click(screen.getByRole('button', { name: 'Conferir e salvar token' }));
  await screen.findByText(/Token conferido e salvo/);
  expect(input.value).toBe('');
  const calls = vi.mocked(fetch).mock.calls.filter(([, opts]) => opts?.method === 'POST');
  expect(calls).toHaveLength(1);
  expect(calls[0][0]).toBe('http://localhost:8010/api/trafego/meta/business');
  expect(JSON.parse(String(calls[0][1]?.body)).token).toBe('fixture-only-not-a-real-token');
  expect(localStorage.setItem).not.toHaveBeenCalled();
});

it('não renderiza segredo devolvido por gateway ou validator', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response('{"detail":"SECRET_ECHO"}', { status: 422 }));
  await expect(businessRequest('', { token: 'SECRET_ECHO' })).rejects.toThrow('Não foi possível confirmar');
  render(<MemoryRouter><MetaBusinessConnections /></MemoryRouter>);
  await screen.findByRole('alert');
  expect(document.body.textContent).not.toContain('SECRET_ECHO');
});

it('não expõe conteúdo de um proxy que retorna HTML com status 200', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response('<html>SECRET_ECHO</html>', { status: 200 }));
  await expect(businessRequest()).rejects.toThrow('O servidor retornou uma resposta inválida.');
});

it('a conexão só é selecionada por ação explícita e desconectada não pode ser usada', async () => {
  vi.mocked(fetch).mockImplementation(async () => new Response(JSON.stringify({ ...empty, connections: [
    { id: 'one', name: 'BM principal', business_id: '123456789', enabled: true, verified_at: '2026-09-08T12:00:00Z' },
    { id: 'two', name: 'BM inativa', business_id: '987654321', enabled: false, verified_at: '2026-09-08T12:00:00Z' },
  ] }), { status: 200 }));
  render(<MemoryRouter><MetaBusinessConnections /></MemoryRouter>);
  await screen.findByText('BM principal');
  expect(vi.mocked(fetch).mock.calls.every(([,opts]) => opts?.method === 'GET')).toBe(true);
  const buttons = screen.getAllByRole('button', { name: 'Usar este negócio' });
  expect((buttons[1] as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(buttons[0]);
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('http://localhost:8010/api/trafego/meta/business/one/select', expect.objectContaining({ method: 'POST' })));
});
