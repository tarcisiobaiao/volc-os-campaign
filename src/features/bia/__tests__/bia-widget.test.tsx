// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ErroDeApi } from '@/lib/secureApi';

import type { ExecucaoDaBia } from '../tipos';

const estadoAuth = vi.hoisted(() => ({
  valor: { user: null as null | { id: string }, userProfile: null as null | { role: string } },
}));
const flag = vi.hoisted(() => ({ ligada: true }));
const api = vi.hoisted(() => ({
  estado: vi.fn(),
  novaConversa: vi.fn(),
  historico: vi.fn(),
  enviar: vi.fn(),
  execucao: vi.fn(),
  reconciliar: vi.fn(),
}));
const mobile = vi.hoisted(() => ({ valor: false }));

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => estadoAuth.valor }));
vi.mock('@/features/bia/featureFlag', () => ({ isBiaEnabled: () => flag.ligada }));
vi.mock('@/features/bia/api', () => ({ biaApi: api }));
vi.mock('@/hooks/useIsMobile', () => ({ useIsMobile: () => mobile.valor }));
// A Supabase real não é tocada: o api é dublado inteiro.
vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession: vi.fn() } } }));

import { BiaNoLayout } from '../BiaNoLayout';
import { AVISO_MEMORIA_COMPARTILHADA, AVISO_MODO_CONSULTA } from '../BiaWidget';
import { chaveDaConversa } from '../useBia';

const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const CONV = 'c0000000-0000-4000-8000-000000000001';

const exe = (p: Partial<ExecucaoDaBia>): ExecucaoDaBia => ({
  id: 'e1', conversa_id: CONV, request_id: 'r1', estado: 'succeeded', entrada: 'oi',
  resposta: 'olá', erro: null, contexto: null, criada_em: '2026-10-15T10:00:00Z',
  terminada_em: '2026-10-15T10:00:01Z', ...p,
});

const SERVICO = {
  modo: 'consulta', aviso: AVISO_MODO_CONSULTA, motor_configurado: true,
  memoria: { compartilhada_com: 'telegram', aviso: AVISO_MEMORIA_COMPARTILHADA },
  limites: { max_caracteres: 4000, envios_por_minuto: 6, espera_maxima_s: 240 }, capacidades: ['volc_get_campaign_context'],
};

function logar(id: string | null, role = 'ADMIN') {
  estadoAuth.valor = { user: id ? { id } : null, userProfile: id ? { role } : null };
}

async function abrir() {
  fireEvent.click(await screen.findByRole('button', { name: 'Bia' }));
  return screen.findByRole('dialog', { name: 'Bia' });
}

// Node 26 + jsdom: `window.localStorage` não existe. Storage em memória, por teste.
function storageEmMemoria(): Storage {
  const m = new Map<string, string>();
  return {
    get length() { return m.size; },
    clear: () => m.clear(),
    getItem: (k) => (m.has(k) ? (m.get(k) as string) : null),
    key: (i) => [...m.keys()][i] ?? null,
    removeItem: (k) => { m.delete(k); },
    setItem: (k, v) => { m.set(k, String(v)); },
  };
}

beforeEach(() => {
  Object.defineProperty(window, 'localStorage', { value: storageEmMemoria(), configurable: true });
  flag.ligada = true;
  mobile.valor = false;
  window.localStorage.clear();
  Object.values(api).forEach((f) => f.mockReset());
  api.estado.mockResolvedValue(SERVICO);
  api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [], aviso: AVISO_MODO_CONSULTA });
  api.novaConversa.mockResolvedValue({ conversa: { id: CONV, titulo: null, criada_em: '', atualizada_em: '' } });
  Element.prototype.scrollIntoView = vi.fn();
  if (!globalThis.crypto?.randomUUID) {
    vi.stubGlobal('crypto', { randomUUID: () => '99999999-9999-4999-8999-999999999999' });
  }
});

afterEach(() => {
  cleanup();
});

describe('portão da Bia no Layout', () => {
  it('flag desligada: nada aparece e a sessão nem é consultada', () => {
    flag.ligada = false;
    logar(A);
    const { container } = render(<BiaNoLayout />);
    expect(container.innerHTML).toBe('');
    expect(api.estado).not.toHaveBeenCalled();
  });

  it('OPERATOR não vê a Bia', () => {
    logar(A, 'OPERATOR');
    render(<BiaNoLayout />);
    expect(screen.queryByRole('button', { name: 'Bia' })).toBeNull();
  });

  it('ADMIN vê o lançador e o aviso de modo consulta ao abrir', async () => {
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    expect(painel.textContent).toContain(AVISO_MODO_CONSULTA);
    expect(painel.textContent).toContain('mesma Bia do Telegram');
  });

  it('logout desmonta o widget', async () => {
    logar(A);
    const { rerender } = render(<BiaNoLayout />);
    await abrir();
    logar(null);
    rerender(<BiaNoLayout />);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Bia' })).toBeNull();
  });

  it('troca de usuário isola o estado: a conversa de A não aparece para B', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ entrada: 'segredo do A' })] });
    logar(A);
    const { rerender } = render(<BiaNoLayout />);
    await abrir();
    expect(await screen.findByText('segredo do A')).toBeTruthy();
    api.historico.mockClear();
    logar(B);
    rerender(<BiaNoLayout />);
    await abrir();
    expect(screen.queryByText('segredo do A')).toBeNull();
    expect(api.historico).not.toHaveBeenCalled(); // B não tem conversa salva
  });
});

describe('conversa', () => {
  it('recupera o histórico depois do reload pelo id salvo do usuário', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ entrada: 'o código é AMBAR', resposta: 'anotado' })] });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    expect(await screen.findByText('o código é AMBAR')).toBeTruthy();
    expect(screen.getByText('anotado')).toBeTruthy();
    expect(api.historico).toHaveBeenCalledWith(CONV);
  });

  it('conversa salva que não existe mais é esquecida', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockRejectedValue(new ErroDeApi('Conversa não encontrada.', 404, 'nao_encontrado'));
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    expect(await screen.findByRole('button', { name: 'Começar conversa' })).toBeTruthy();
    expect(window.localStorage.getItem(chaveDaConversa(A))).toBeNull();
  });

  it('nova conversa isola o histórico anterior', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ entrada: 'antiga' })] });
    api.novaConversa.mockResolvedValue({ conversa: { id: 'c-nova', titulo: null, criada_em: '', atualizada_em: '' } });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    await screen.findByText('antiga');
    fireEvent.click(screen.getByRole('button', { name: 'Nova conversa' }));
    await waitFor(() => expect(screen.queryByText('antiga')).toBeNull());
    expect(window.localStorage.getItem(chaveDaConversa(A))).toBe('c-nova');
  });

  it('envia só request_id e texto; Enter envia e Shift+Enter não', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.enviar.mockResolvedValue({ execucao: exe({ id: 'e9', entrada: 'pergunta', resposta: 'resposta' }) });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    const campo = await screen.findByRole('textbox', { name: 'Mensagem para a Bia' });
    await waitFor(() => expect((campo as HTMLTextAreaElement).disabled).toBe(false));
    fireEvent.change(campo, { target: { value: 'pergunta' } });
    fireEvent.keyDown(campo, { key: 'Enter', shiftKey: true });
    expect(api.enviar).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.keyDown(campo, { key: 'Enter' });
    });
    expect(api.enviar).toHaveBeenCalledTimes(1);
    const [conversa, pedido] = api.enviar.mock.calls[0];
    expect(conversa).toBe(CONV);
    expect(Object.keys(pedido).sort()).toEqual(['request_id', 'texto']);
    expect(pedido.request_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('resposta é texto: HTML vindo do modelo não vira elemento', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({
      conversa: { id: CONV },
      execucoes: [exe({ resposta: '<img src=x onerror="alert(1)"><b>negrito</b>' })],
    });
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    await screen.findByText('<img src=x onerror="alert(1)"><b>negrito</b>');
    expect(painel.querySelector('img')).toBeNull();
    expect(painel.querySelector('b')).toBeNull();
  });
});

describe('estados e erros', () => {
  it('incerta: oferece verificar, bloqueia o campo e não reenvia nada', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({
      conversa: { id: CONV },
      execucoes: [exe({ estado: 'uncertain', resposta: null,
                        erro: { codigo: 'hermes_timeout', mensagem: 'O Hermes não respondeu dentro do prazo. O resultado é incerto.' } })],
    });
    api.reconciliar.mockResolvedValue({ execucao: exe({ estado: 'succeeded', resposta: 'chegou' }) });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    expect(await screen.findByText('Resultado incerto')).toBeTruthy();
    expect((screen.getByRole('textbox', { name: 'Mensagem para a Bia' }) as HTMLTextAreaElement).disabled).toBe(true);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Verificar resposta' }));
    });
    expect(api.reconciliar).toHaveBeenCalledWith('e1');
    expect(api.enviar).not.toHaveBeenCalled();
    expect(await screen.findByText('chegou')).toBeTruthy();
  });

  it('falha de rede: mensagem em texto, relê o histórico e não reenvia', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.enviar.mockRejectedValue(new ErroDeApi('Failed to fetch', 0, 'REDE'));
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    const campo = await screen.findByRole('textbox', { name: 'Mensagem para a Bia' });
    await waitFor(() => expect((campo as HTMLTextAreaElement).disabled).toBe(false));
    fireEvent.change(campo, { target: { value: 'oi' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));
    });
    const alerta = await screen.findByRole('alert');
    expect(alerta.textContent).toContain('nada foi reenviado');
    expect(api.enviar).toHaveBeenCalledTimes(1);
    expect(api.historico).toHaveBeenCalledTimes(2); // carga + releitura
  });

  it('403 do servidor vira mensagem de acesso, não deslogue', async () => {
    api.estado.mockRejectedValue(new ErroDeApi('Esta operação exige papel administrativo.', 403));
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    expect((await screen.findByRole('alert')).textContent).toContain('restrita a administradores');
  });
});

describe('retomada depois do reload', () => {
  it('execução em voo encontrada na carga volta a ser acompanhada, sem reenviar', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico
      .mockResolvedValueOnce({ conversa: { id: CONV }, execucoes: [exe({ estado: 'running', resposta: null, terminada_em: null })] })
      .mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ estado: 'succeeded', resposta: 'chegou depois' })] });
    api.execucao.mockResolvedValue({ execucao: exe({ estado: 'succeeded', resposta: 'chegou depois' }) });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    expect(await screen.findByText('chegou depois', {}, { timeout: 4000 })).toBeTruthy();
    expect(api.execucao).toHaveBeenCalledWith('e1');
    expect(api.enviar).not.toHaveBeenCalled();
  });
});

describe('teclado, foco e celular', () => {
  it('foco entra no campo ao abrir; Esc fecha e devolve o foco ao lançador', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    await waitFor(() => expect(document.activeElement?.tagName).toBe('TEXTAREA'));
    fireEvent.keyDown(painel, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Bia' })));
  });

  it('no celular o painel cobre a tela e é modal', async () => {
    mobile.valor = true;
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    expect(painel.getAttribute('aria-modal')).toBe('true');
    expect(painel.className).toContain('inset-0');
  });

  it('todo controle tem nome acessível', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    fireEvent.click(screen.getByRole('checkbox'));
    for (const el of painel.querySelectorAll('button, input, textarea, select')) {
      const nome = el.getAttribute('aria-label') || el.textContent?.trim() ||
        (el.id && painel.querySelector(`label[for="${el.id}"]`)?.textContent) ||
        el.closest('label')?.textContent;
      expect(nome, el.outerHTML.slice(0, 80)).toBeTruthy();
    }
  });
});
