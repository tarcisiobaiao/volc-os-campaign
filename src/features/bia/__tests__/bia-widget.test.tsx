// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ErroDeApi } from '@/lib/secureApi';

import type { AnexoDaBia, ComandoDoCatalogo, EventoDeFluxo, ExecucaoDaBia } from '../tipos';

const estadoAuth = vi.hoisted(() => ({
  valor: { user: null as null | { id: string }, userProfile: null as null | { role: string } },
}));
const flag = vi.hoisted(() => ({ ligada: true }));
const api = vi.hoisted(() => ({
  estado: vi.fn(),
  novaConversa: vi.fn(),
  conversas: vi.fn(),
  historico: vi.fn(),
  enviar: vi.fn(),
  execucao: vi.fn(),
  reconciliar: vi.fn(),
  comandos: vi.fn(),
  executarComando: vi.fn(),
  removerAnexo: vi.fn(),
  enviarAnexo: vi.fn(),
  urlDoAnexo: vi.fn(),
  acompanhar: vi.fn(),
  cerebroStatus: vi.fn(),
  gravarCaptura: vi.fn(),
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
import { lerRascunho, montarConteudo } from '../componentes/CartaoDeCaptura';
import { chaveDoRascunho } from '../componentes/Compositor';
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
  limites: { max_caracteres: 4000, envios_por_minuto: 6, espera_maxima_s: 240 }, capacidades: [],
};

const cmd = (nome: string, p: Partial<ComandoDoCatalogo> = {}): ComandoDoCatalogo => ({
  nome, descricao: `faz ${nome}`, args: '', origem: 'volc', classe: 'local_ui', disponivel: true,
  execucao: 'local', motivo: '', equivalente_web: null, aliases: [], ...p,
});
const CATALOGO: ComandoDoCatalogo[] = [
  cmd('nova'), cmd('conversas'), cmd('anexar'), cmd('copiar'),
  cmd('contexto', { args: '<id da campanha>' }),
  cmd('status', { classe: 'hermes_safe', execucao: 'backend' }),
  cmd('ajuda', { aliases: ['/commands'] }),
  cmd('cerebro', { classe: 'hermes_safe', execucao: 'backend' }), cmd('salvar'),
  cmd('compress', { origem: 'hermes_registro', classe: 'hermes_safe', disponivel: false, execucao: null,
                    motivo: 'Reescreve o histórico da sessão; fora da V1.' }),
  cmd('cron', { origem: 'hermes_registro', classe: 'requires_tool', disponivel: false, execucao: null,
                motivo: 'Agenda tarefas: exige ferramentas, desligadas na web.' }),
];

const anexo = (p: Partial<AnexoDaBia> = {}): AnexoDaBia => ({
  id: 'a0000000-0000-4000-8000-00000000000a', nome: 'foto.png', tipo: 'png', familia: 'imagem', tamanho: 2048,
  mime: 'image/png', sha256: 'x', criado_em: '', expira_em: '', paginas: null, largura: 10, altura: 10,
  caracteres: null, truncado: false, ...p,
});

function logar(id: string | null, role = 'ADMIN') {
  estadoAuth.valor = { user: id ? { id } : null, userProfile: id ? { role } : null };
}

async function abrir() {
  fireEvent.click(await screen.findByRole('button', { name: /^Abrir a Bia/ }));
  return screen.findByRole('dialog', { name: 'Bia' });
}

async function campoPronto() {
  const campo = (await screen.findByRole('combobox', { name: 'Mensagem para a Bia' })) as HTMLTextAreaElement;
  await waitFor(() => expect(api.estado).toHaveBeenCalled());
  return campo;
}

async function digitar(campo: HTMLTextAreaElement, texto: string) {
  await act(async () => {
    fireEvent.change(campo, { target: { value: texto } });
  });
}

async function teclar(el: Element, key: string, extra: Record<string, unknown> = {}) {
  await act(async () => {
    fireEvent.keyDown(el, { key, ...extra });
  });
}

const arquivo = (nome: string, tipo: string, bytes = 10) => new File([new Uint8Array(bytes)], nome, { type: tipo });

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
  Object.defineProperty(window, 'sessionStorage', { value: storageEmMemoria(), configurable: true });
  flag.ligada = true;
  mobile.valor = false;
  Object.values(api).forEach((f) => f.mockReset());
  api.estado.mockResolvedValue(SERVICO);
  api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [], aviso: '' });
  api.novaConversa.mockResolvedValue({ conversa: { id: CONV, titulo: null, criada_em: '', atualizada_em: '' } });
  api.comandos.mockResolvedValue({ comandos: CATALOGO });
  api.urlDoAnexo.mockResolvedValue('blob:miniatura');
  api.removerAnexo.mockResolvedValue({ removido: true });
  // Sem SSE nos testes: o fluxo cai e o hook sonda por leitura.
  api.acompanhar.mockRejectedValue(new Error('sem fluxo'));
  if (!globalThis.crypto?.randomUUID) {
    vi.stubGlobal('crypto', { randomUUID: () => '99999999-9999-4999-8999-999999999999' });
  }
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
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
    expect(screen.queryByRole('button', { name: /Bia/ })).toBeNull();
  });

  it('ADMIN vê o lançador e os avisos de modo consulta e memória ao abrir', async () => {
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    expect(painel.textContent).toContain(AVISO_MODO_CONSULTA);
    expect(painel.textContent).toContain('memória do Telegram');
    expect(await within(painel).findByText(AVISO_MEMORIA_COMPARTILHADA)).toBeTruthy(); // estado vazio
  });

  it('logout desmonta o widget e apaga os rascunhos da aba', async () => {
    window.sessionStorage.setItem(chaveDoRascunho(A, CONV), 'meu rascunho');
    window.sessionStorage.setItem('outra.chave', 'fica');
    logar(A);
    const { rerender } = render(<BiaNoLayout />);
    await abrir();
    logar(null);
    rerender(<BiaNoLayout />);
    expect(window.sessionStorage.getItem(chaveDoRascunho(A, CONV))).toBeNull();
    expect(window.sessionStorage.getItem('outra.chave')).toBe('fica');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('button', { name: /Bia/ })).toBeNull();
  });

  it('troca de usuário isola conversa e rascunho', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    window.sessionStorage.setItem(chaveDoRascunho(A, CONV), 'rascunho do A');
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ entrada: 'segredo do A' })] });
    logar(A);
    const { rerender } = render(<BiaNoLayout />);
    await abrir();
    expect(await screen.findByText('segredo do A')).toBeTruthy();
    expect((await campoPronto()).value).toBe('rascunho do A');
    api.historico.mockClear();
    logar(B);
    rerender(<BiaNoLayout />);
    await abrir();
    expect(screen.queryByText('segredo do A')).toBeNull();
    expect((await campoPronto()).value).toBe('');
    expect(api.historico).not.toHaveBeenCalled(); // B não tem conversa salva
  });
});

describe('conversa', () => {
  it('recupera o histórico depois do reload pelo id salvo do usuário', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ entrada: 'o código é AMBAR', resposta: 'anotado' })] });
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    expect(await screen.findByText('o código é AMBAR')).toBeTruthy();
    expect(screen.getByText('anotado')).toBeTruthy();
    expect(api.historico).toHaveBeenCalledWith(CONV);
    expect(within(painel).getByRole('log', { name: 'Conversa com a Bia' })).toBeTruthy();
  });

  it('conversa salva que não existe mais é esquecida e mostra o estado vazio', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockRejectedValue(new ErroDeApi('Conversa não encontrada.', 404, 'nao_encontrado'));
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    expect(await screen.findByText('Converse com a Bia')).toBeTruthy();
    expect(window.localStorage.getItem(chaveDaConversa(A))).toBeNull();
  });

  it('nova conversa isola o histórico anterior', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockImplementation(async (id: string) => ({
      conversa: { id }, execucoes: id === CONV ? [exe({ entrada: 'antiga' })] : [],
    }));
    api.novaConversa.mockResolvedValue({ conversa: { id: 'c-nova', titulo: null, criada_em: '', atualizada_em: '' } });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    await screen.findByText('antiga');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Nova conversa' }));
    });
    await waitFor(() => expect(screen.queryByText('antiga')).toBeNull());
    expect(window.localStorage.getItem(chaveDaConversa(A))).toBe('c-nova');
  });

  it('lista de conversas é do servidor; abrir uma troca a conversa', async () => {
    api.conversas.mockResolvedValue({ conversas: [
      { id: CONV, titulo: 'Campanha Primavera', criada_em: '2026-10-15T10:00:00Z', atualizada_em: '2026-10-15T10:00:00Z', mensagens: 2 },
    ] });
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ entrada: 'da lista' })] });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Conversas recentes' }));
    });
    const lista = await screen.findByRole('list', { name: 'Conversas recentes' });
    await act(async () => {
      fireEvent.click(within(lista).getByRole('button', { name: /Campanha Primavera/ }));
    });
    expect(await screen.findByText('da lista')).toBeTruthy();
    expect(window.localStorage.getItem(chaveDaConversa(A))).toBe(CONV);
  });

  it('envia só request_id e texto; Enter envia, Shift+Enter e IME não', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.enviar.mockResolvedValue({ execucao: exe({ id: 'e9', entrada: 'pergunta', resposta: 'resposta' }) });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    const campo = await campoPronto();
    await digitar(campo, 'pergunta');
    await teclar(campo, 'Enter', { shiftKey: true });
    await teclar(campo, 'Enter', { isComposing: true, keyCode: 229 });
    expect(api.enviar).not.toHaveBeenCalled();
    await teclar(campo, 'Enter');
    expect(api.enviar).toHaveBeenCalledTimes(1);
    const [conversa, pedido] = api.enviar.mock.calls[0];
    expect(conversa).toBe(CONV);
    expect(Object.keys(pedido).sort()).toEqual(['request_id', 'texto']);
    expect(pedido.request_id).toMatch(/^[0-9a-f-]{36}$/);
    await waitFor(() => expect(campo.value).toBe(''));
    expect(window.sessionStorage.getItem(chaveDoRascunho(A, CONV))).toBeNull();
  });

  it('dois Enter no mesmo instante viram UM envio', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    let liberar: (v: unknown) => void = () => undefined;
    api.enviar.mockImplementation(() => new Promise((r) => { liberar = r; }));
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    const campo = await campoPronto();
    await digitar(campo, 'uma vez');
    await act(async () => {
      fireEvent.keyDown(campo, { key: 'Enter' });
      fireEvent.keyDown(campo, { key: 'Enter' });
    });
    expect(api.enviar).toHaveBeenCalledTimes(1);
    await act(async () => liberar({ execucao: exe({}) }));
  });

  it('sem conversa aberta, o primeiro envio cria uma e envia nela', async () => {
    api.novaConversa.mockResolvedValue({ conversa: { id: 'c-nova', titulo: null, criada_em: '', atualizada_em: '' } });
    api.enviar.mockResolvedValue({ execucao: exe({ conversa_id: 'c-nova' }) });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    const campo = await campoPronto();
    await digitar(campo, 'primeira');
    await teclar(campo, 'Enter');
    await waitFor(() => expect(api.enviar).toHaveBeenCalledWith('c-nova', expect.objectContaining({ texto: 'primeira' })));
  });

  it('Markdown sanitizado: HTML cru some, imagem remota não carrega, javascript: não vira link', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({
      conversa: { id: CONV },
      execucoes: [exe({ resposta:
        '**forte** <img src=x onerror="alert(1)"><b>cru</b>\n\n![remota](https://evil.example/x.png)\n\n' +
        '[clique](javascript:alert(1)) e [docs](https://support.google.com/a)\n\n- item 1\n- item 2' })],
    });
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    await within(painel).findByText('forte');
    expect(within(painel).getByText('forte').tagName).toBe('STRONG');
    expect(painel.querySelector('img[src*="evil"]')).toBeNull();
    expect(painel.querySelector('b')).toBeNull();
    expect(painel.innerHTML).not.toContain('onerror');
    expect(painel.querySelector('a[href^="javascript"]')).toBeNull();
    const docs = within(painel).getByRole('link', { name: /docs/ });
    expect(docs.getAttribute('rel')).toContain('noopener');
    expect(docs.getAttribute('target')).toBe('_blank');
    expect(docs.textContent).toContain('support.google.com');
    expect(painel.querySelectorAll('li li, ul li').length).toBeGreaterThanOrEqual(2);
  });

  it('histórico longo e mensagem longa renderizam sem quebrar', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    const longa = 'x'.repeat(3900);
    api.historico.mockResolvedValue({
      conversa: { id: CONV },
      execucoes: Array.from({ length: 60 }, (_, i) => exe({ id: `e${i}`, entrada: i === 59 ? longa : `msg ${i}`, resposta: `resp ${i}` })),
    });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    expect(await screen.findByText('resp 59')).toBeTruthy();
    expect(screen.getByText(longa)).toBeTruthy();
  });
});

describe('estados honestos', () => {
  it('na fila, preparando (sem delta) e digitando (com delta real)', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    let emitir: (e: EventoDeFluxo) => void = () => undefined;
    api.acompanhar.mockImplementation((_id: string, ao: (e: EventoDeFluxo) => void, sinal: AbortSignal) => {
      emitir = ao;
      return new Promise<void>((r) => sinal.addEventListener('abort', () => r()));
    });
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ estado: 'queued', resposta: null, terminada_em: null, entrada: 'q' })] });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    // No turno e no cabeçalho.
    expect((await screen.findAllByText('Mensagem na fila')).length).toBe(2);
    await act(async () => emitir({ tipo: 'estado', execucao: exe({ estado: 'running', resposta: null, terminada_em: null, entrada: 'q' }) }));
    expect(await screen.findByText('Bia está preparando a resposta…')).toBeTruthy();
    expect(screen.queryByText(/digitando/)).toBeNull();
    await act(async () => emitir({ tipo: 'parcial', texto: 'Começo da resposta' }));
    expect(await screen.findByText('Bia está digitando…')).toBeTruthy();
    expect(screen.getByText('Começo da resposta')).toBeTruthy();
    await act(async () => emitir({ tipo: 'estado', execucao: exe({ entrada: 'q', resposta: 'Começo da resposta, fim.' }) }));
    expect(await screen.findByText('Começo da resposta, fim.')).toBeTruthy();
    expect(screen.queryByText('Bia está digitando…')).toBeNull();
  });

  it('incerta: oferece verificar, segura o envio e não reenvia nada', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({
      conversa: { id: CONV },
      execucoes: [exe({ estado: 'uncertain', resposta: null,
                        erro: { codigo: 'hermes_timeout', mensagem: 'O Hermes não respondeu dentro do prazo.' } })],
    });
    api.reconciliar.mockResolvedValue({ execucao: exe({ estado: 'succeeded', resposta: 'chegou' }) });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    expect(await screen.findByText('Resultado incerto')).toBeTruthy();
    expect(screen.getByText(/nada será reenviado automaticamente/)).toBeTruthy();
    const campo = await campoPronto();
    await digitar(campo, 'outra');
    expect((screen.getByRole('button', { name: 'Enviar mensagem' }) as HTMLButtonElement).disabled).toBe(true);
    await teclar(campo, 'Enter');
    expect(api.enviar).not.toHaveBeenCalled();
    expect((await screen.findAllByText(/resultado incerto nesta conversa/)).length).toBeGreaterThan(0);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Verificar resposta' }));
    });
    expect(api.reconciliar).toHaveBeenCalledWith('e1');
    expect(await screen.findByText('chegou')).toBeTruthy();
    expect(api.enviar).not.toHaveBeenCalled();
  });

  it('falha: causa pública, próximo passo e reaproveitar põe o texto no campo (sem enviar)', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({
      estado: 'failed', resposta: null, entrada: 'pause o grupo',
      erro: { codigo: 'hermes_usou_ferramenta', mensagem: 'A Bia tentou usar uma ferramenta.' } })] });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    expect(await screen.findByText('A Bia tentou usar uma ferramenta.')).toBeTruthy();
    expect(screen.getByText(/Reformule como pergunta de consulta/)).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Reaproveitar o texto' }));
    });
    await waitFor(async () => expect((await campoPronto()).value).toBe('pause o grupo'));
    expect(api.enviar).not.toHaveBeenCalled();
  });

  it('falha de rede: alerta em texto, rascunho preservado, relê e não reenvia', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.enviar.mockRejectedValue(new ErroDeApi('Failed to fetch', 0, 'REDE'));
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    const campo = await campoPronto();
    await digitar(campo, 'não me perca');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Enviar mensagem' }));
    });
    const alerta = await screen.findByRole('alert');
    expect(alerta.textContent).toContain('nada foi reenviado');
    expect(api.enviar).toHaveBeenCalledTimes(1);
    expect(api.historico).toHaveBeenCalledTimes(2); // carga + releitura
    expect(campo.value).toBe('não me perca');
    expect(window.sessionStorage.getItem(chaveDoRascunho(A, CONV))).toBe('não me perca');
  });

  it('403 do servidor vira mensagem de acesso, não deslogue', async () => {
    api.estado.mockRejectedValue(new ErroDeApi('Esta operação exige papel administrativo.', 403));
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    expect((await screen.findByRole('alert')).textContent).toContain('restrita a administradores');
  });

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
    expect(api.acompanhar).toHaveBeenCalledWith('e1', expect.any(Function), expect.anything());
    expect(api.enviar).not.toHaveBeenCalled();
  });
});

describe('anexos', () => {
  async function prepararComAnexo() {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    const campo = await campoPronto();
    const seletor = painel.querySelector('input[type=file]') as HTMLInputElement;
    return { painel, campo, seletor };
  }

  it('seletor sobe o arquivo e a mensagem leva só o id do anexo', async () => {
    api.enviarAnexo.mockReturnValue({ promessa: Promise.resolve(anexo()), cancelar: vi.fn() });
    api.enviar.mockResolvedValue({ execucao: exe({}) });
    const { campo, seletor } = await prepararComAnexo();
    await act(async () => {
      fireEvent.change(seletor, { target: { files: [arquivo('foto.png', 'image/png')] } });
    });
    expect(api.enviarAnexo).toHaveBeenCalledTimes(1);
    expect(await screen.findByText('PNG · 10 B')).toBeTruthy();
    await digitar(campo, 'o que tem na foto?');
    await teclar(campo, 'Enter');
    const pedido = api.enviar.mock.calls[0][1];
    expect(pedido.anexos).toEqual([anexo().id]);
    expect(Object.keys(pedido).sort()).toEqual(['anexos', 'request_id', 'texto']);
    await waitFor(() => expect(screen.queryByRole('list', { name: 'Arquivos para enviar' })).toBeNull());
  });

  it('tipo proibido e excesso são recusados antes de subir', async () => {
    const { seletor } = await prepararComAnexo();
    await act(async () => {
      fireEvent.change(seletor, { target: { files: [arquivo('virus.exe', 'application/x-msdownload'), arquivo('pagina.html', 'text/html')] } });
    });
    expect(api.enviarAnexo).not.toHaveBeenCalled();
    expect((await screen.findByRole('alert')).textContent).toContain('tipo não aceito');
    api.enviarAnexo.mockReturnValue({ promessa: new Promise(() => undefined), cancelar: vi.fn() });
    await act(async () => {
      fireEvent.change(seletor, { target: { files: Array.from({ length: 5 }, (_, i) => arquivo(`d${i}.txt`, 'text/plain')) } });
    });
    expect(api.enviarAnexo).toHaveBeenCalledTimes(4);
    expect((await screen.findByRole('alert')).textContent).toContain('Até 4 anexos');
  });

  it('falha no upload: erro perto do arquivo, repetir sobe de novo, remover tira da fila', async () => {
    api.enviarAnexo
      .mockImplementationOnce(() => ({ promessa: Promise.reject(new ErroDeApi('Armazenamento indisponível.', 503, 'anexo_indisponivel')), cancelar: vi.fn() }))
      .mockReturnValueOnce({ promessa: Promise.resolve(anexo({ nome: 'nota.txt', tipo: 'txt', familia: 'documento' })), cancelar: vi.fn() });
    const { seletor } = await prepararComAnexo();
    await act(async () => {
      fireEvent.change(seletor, { target: { files: [arquivo('nota.txt', 'text/plain')] } });
    });
    expect(await screen.findByText('Armazenamento indisponível.')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Enviar mensagem' }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Enviar de novo nota.txt/ }));
    });
    expect(api.enviarAnexo).toHaveBeenCalledTimes(2);
    expect(await screen.findByText('TXT · 10 B')).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Remover nota.txt/ }));
    });
    expect(api.removerAnexo).toHaveBeenCalledWith(anexo().id);
    expect(screen.queryByText('nota.txt')).toBeNull();
  });

  it('recusa definitiva (4xx) não oferece repetir; só remover', async () => {
    api.enviarAnexo.mockImplementation(() => ({
      promessa: Promise.reject(new ErroDeApi('Arquivo recusado: executável Windows.', 422, 'tipo_proibido')), cancelar: vi.fn() }));
    const { seletor } = await prepararComAnexo();
    await act(async () => {
      fireEvent.change(seletor, { target: { files: [arquivo('falso.png', 'image/png')] } });
    });
    expect(await screen.findByText('Arquivo recusado: executável Windows.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Enviar de novo/ })).toBeNull();
    expect(screen.getByRole('button', { name: /Remover falso.png/ })).toBeTruthy();
  });

  it('enquanto sobe: progresso acessível e envio segurado', async () => {
    let progresso: (f: number) => void = () => undefined;
    api.enviarAnexo.mockImplementation((_f: File, ao: (f: number) => void) => {
      progresso = ao;
      return { promessa: new Promise(() => undefined), cancelar: vi.fn() };
    });
    const { campo, seletor } = await prepararComAnexo();
    await act(async () => {
      fireEvent.change(seletor, { target: { files: [arquivo('grande.pdf', 'application/pdf')] } });
    });
    await act(async () => progresso(0.5));
    const barra = screen.getByRole('progressbar', { name: 'Enviando grande.pdf' });
    expect(barra.getAttribute('aria-valuenow')).toBe('50');
    await digitar(campo, 'resume?');
    await teclar(campo, 'Enter');
    expect(api.enviar).not.toHaveBeenCalled();
    expect((await screen.findByRole('alert')).textContent).toContain('Aguarde os arquivos');
  });

  it('colar imagem e soltar arquivo também anexam', async () => {
    api.enviarAnexo.mockReturnValue({ promessa: Promise.resolve(anexo()), cancelar: vi.fn() });
    const { painel, campo } = await prepararComAnexo();
    await act(async () => {
      fireEvent.paste(campo, { clipboardData: { files: [arquivo('colada.png', 'image/png')], getData: () => '' } });
    });
    expect(api.enviarAnexo).toHaveBeenCalledTimes(1);
    const dt = { files: [arquivo('solto.pdf', 'application/pdf')], types: ['Files'], dropEffect: 'none' };
    await act(async () => {
      fireEvent.dragEnter(painel, { dataTransfer: dt });
    });
    expect(screen.getByText('Solte para anexar')).toBeTruthy();
    await act(async () => {
      fireEvent.drop(painel, { dataTransfer: dt });
    });
    expect(api.enviarAnexo).toHaveBeenCalledTimes(2);
    expect(screen.queryByText('Solte para anexar')).toBeNull();
  });

  it('anexos do histórico aparecem com nome, tipo e tamanho; imagem pela URL autenticada', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ contexto: { campanha: null, anexos: [
      { id: 'img1', nome: 'foto.jpg', tipo: 'jpeg', familia: 'imagem', tamanho: 304458 },
      { id: 'doc1', nome: 'relatorio.pdf', tipo: 'pdf', familia: 'documento', tamanho: 1281 },
    ] } })] });
    logar(A);
    render(<BiaNoLayout />);
    await abrir();
    expect(await screen.findByText('relatorio.pdf')).toBeTruthy();
    expect(screen.getByText('PDF · 1 KB')).toBeTruthy();
    expect(await screen.findByRole('img', { name: 'Imagem anexada: foto.jpg' })).toBeTruthy();
    expect(api.urlDoAnexo).toHaveBeenCalledWith('img1');
  });
});

describe('comandos /', () => {
  async function preparar() {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    const campo = await campoPronto();
    await waitFor(() => expect(api.comandos).toHaveBeenCalled());
    return { painel, campo };
  }

  it('"/" abre a paleta (combobox/listbox) com disponíveis e bloqueados', async () => {
    const { campo } = await preparar();
    await digitar(campo, '/c');
    const lista = await screen.findByRole('listbox', { name: 'Comandos da Bia' });
    expect(campo.getAttribute('aria-expanded')).toBe('true');
    expect(campo.getAttribute('aria-controls')).toBe(lista.id);
    const opcoes = within(lista).getAllByRole('option');
    expect(opcoes.map((o) => o.textContent)).toEqual(expect.arrayContaining([
      expect.stringContaining('/conversas'), expect.stringContaining('/compress'),
    ]));
    const bloqueada = opcoes.find((o) => o.textContent?.includes('/compress'))!;
    expect(bloqueada.getAttribute('aria-disabled')).toBe('true');
    expect(bloqueada.textContent).toContain('fora da V1');
    expect(campo.getAttribute('aria-activedescendant')).toBe(opcoes[0].id);
  });

  it('setas e Enter escolhem; comando local roda sem ir ao servidor', async () => {
    const { campo } = await preparar();
    await digitar(campo, '/');
    await screen.findByRole('listbox');
    // /nova, /conversas, ... → seta para baixo leva a /conversas
    await teclar(campo, 'ArrowDown');
    const ativa = document.getElementById(campo.getAttribute('aria-activedescendant')!);
    expect(ativa?.textContent).toContain('/conversas');
    api.conversas.mockResolvedValue({ conversas: [] });
    await teclar(campo, 'Enter');
    expect(await screen.findByText(/ainda não tem conversas/)).toBeTruthy();
    expect(api.enviar).not.toHaveBeenCalled();
  });

  it('comando bloqueado mostra o motivo e NADA vai à Bia', async () => {
    const { campo } = await preparar();
    await digitar(campo, '/cron todo dia');
    await teclar(campo, 'Enter');
    expect(await screen.findByText(/exige ferramentas, desligadas na web/)).toBeTruthy();
    expect(screen.getByText(/Nada foi enviado à Bia/)).toBeTruthy();
    expect(api.enviar).not.toHaveBeenCalled();
    expect(api.executarComando).not.toHaveBeenCalled();
  });

  it('comando desconhecido não é encaminhado como texto', async () => {
    const { campo } = await preparar();
    await digitar(campo, '/apagar-tudo agora');
    await teclar(campo, 'Enter');
    expect(await screen.findByText(/Comando desconhecido/)).toBeTruthy();
    expect(api.enviar).not.toHaveBeenCalled();
  });

  it('/status usa a rota tipada e mostra o recibo de leitura', async () => {
    api.executarComando.mockResolvedValue({
      comando: 'status',
      resultado: { conversa: { mensagens: 3, por_estado: { succeeded: 3 } }, hermes: { versao: '0.18.0', gateway: 'running' }, sessao_web: null, avisos: ['aviso x'] },
      recibo: { duracao_ms: 12 },
    });
    const { campo } = await preparar();
    await digitar(campo, '/status');
    await teclar(campo, 'Enter');
    expect(api.executarComando).toHaveBeenCalledWith('status', CONV);
    expect(await screen.findByText('/status · somente leitura')).toBeTruthy();
    expect(screen.getByText('no ar · v0.18.0')).toBeTruthy();
    expect(api.enviar).not.toHaveBeenCalled();
  });

  it('/ajuda lista os comandos da web; /contexto vira chip e entra no pedido', async () => {
    api.enviar.mockResolvedValue({ execucao: exe({}) });
    const { campo } = await preparar();
    await digitar(campo, '/ajuda');
    await teclar(campo, 'Enter');
    expect(await screen.findByText('Comandos nesta conversa')).toBeTruthy();
    await digitar(campo, '/contexto camp-42');
    await teclar(campo, 'Enter');
    expect(await screen.findByText('Campanha camp-42')).toBeTruthy();
    await digitar(campo, 'como está?');
    await teclar(campo, 'Enter');
    expect(api.enviar.mock.calls[0][1].contexto).toEqual({ campaign_ref: 'camp-42', janela: 'ultimos_7_dias' });
  });

  it('Esc fecha a paleta sem fechar o painel; o botão / reabre', async () => {
    const { campo } = await preparar();
    await digitar(campo, '/');
    await screen.findByRole('listbox');
    await teclar(campo, 'Escape');
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(screen.getByRole('dialog', { name: 'Bia' })).toBeTruthy();
    await digitar(campo, '');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Comandos' }));
    });
    expect(await screen.findByRole('listbox')).toBeTruthy();
    expect(campo.value).toBe('/');
  });
});

describe('teclado, foco e celular', () => {
  it('foco entra no campo ao abrir; Esc minimiza, devolve o foco e preserva o estado', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ entrada: 'fica' })] });
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    const campo = await campoPronto();
    await waitFor(() => expect(document.activeElement).toBe(campo));
    await digitar(campo, 'rascunho vivo');
    fireEvent.keyDown(painel, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull(); // escondido (hidden), não desmontado
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole('button', { name: /^Abrir a Bia/ })));
    await abrir();
    expect(screen.getByText('fica')).toBeTruthy();
    expect((await campoPronto()).value).toBe('rascunho vivo');
    expect(api.historico).toHaveBeenCalledTimes(1); // reabrir não recarrega
  });

  it('no celular o painel cobre a tela, é modal e o botão é "Fechar"', async () => {
    mobile.valor = true;
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    expect(painel.getAttribute('aria-modal')).toBe('true');
    expect(painel.className).toContain('inset-x-0');
    expect(painel.className).toContain('h-[100dvh]');
    expect(within(painel).getByRole('button', { name: 'Fechar a Bia' })).toBeTruthy();
  });

  it('região de status anuncia só o envio novo, sem reler a conversa', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ criada_em: '2020-01-01T00:00:00Z' })] });
    api.enviar.mockResolvedValue({ execucao: exe({ id: 'e2', estado: 'queued', resposta: null, terminada_em: null, criada_em: new Date().toISOString() }) });
    api.acompanhar.mockImplementation((_i: string, _a: unknown, s: AbortSignal) => new Promise<void>((r) => s.addEventListener('abort', () => r())));
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    const status = painel.querySelector('p[role=status]')!;
    expect(status.textContent).toBe('');
    const campo = await campoPronto();
    await digitar(campo, 'nova');
    await teclar(campo, 'Enter');
    await waitFor(() => expect(status.textContent).toBe('Mensagem na fila.'));
  });

  it('todo controle tem nome acessível', async () => {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes: [exe({ resposta: 'r' })] });
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    await screen.findByText('r');
    for (const el of painel.querySelectorAll('button, textarea, select')) {
      const nome = el.getAttribute('aria-label') || el.textContent?.trim() ||
        el.querySelector('[aria-label]')?.getAttribute('aria-label') ||
        (el.id && painel.querySelector(`label[for="${el.id}"]`)?.textContent);
      expect(nome, el.outerHTML.slice(0, 80)).toBeTruthy();
    }
  });
});


describe('cérebro (rascunho pela Bia, gravação tipada pelo servidor)', () => {
  const RASCUNHO = {
    destino: 'volc', titulo: 'Atalhos do cérebro na web', tipo: 'decisao',
    resumo: 'Decidimos os atalhos.', decisoes: ['Botões chamam executor tipado'], aprendizados: [],
    pendencias: ['Instalar executor no VPS'], hipoteses: ['Uso diário'], tags: ['bia'],
  };
  const rascunhoExe = (resposta: string) =>
    exe({ id: 'r1', entrada: 'Preparar captura desta conversa para o cérebro.', resposta,
          contexto: { campanha: null, anexos: [], intencao: 'rascunho_cerebro' } });

  async function preparar(execucoes: ExecucaoDaBia[]) {
    window.localStorage.setItem(chaveDaConversa(A), CONV);
    api.historico.mockResolvedValue({ conversa: { id: CONV }, execucoes });
    logar(A);
    render(<BiaNoLayout />);
    const painel = await abrir();
    return { painel, campo: await campoPronto() };
  }

  it('lê o JSON do rascunho e monta o conteúdo separando decisão de hipótese', () => {
    const r = lerRascunho('Aqui:\n```json\n' + JSON.stringify(RASCUNHO) + '\n```')!;
    expect(r.titulo).toBe('Atalhos do cérebro na web');
    const md = montarConteudo(r, new Date('2026-10-16T12:00:00Z'));
    expect(md).toContain('## Decisões\n\n- Botões chamam executor tipado');
    expect(md).toContain('- [ ] 2026-10-16: Instalar executor no VPS');
    expect(md).toContain('## Hipóteses (não confirmadas)');
    expect(lerRascunho('sem json')).toBeNull();
    expect(lerRascunho('{"destino":"x"}')).toBeNull(); // sem título
  });

  it('"Salvar no cérebro" pede o rascunho por intenção tipada, sem texto livre nem anexos', async () => {
    api.enviar.mockResolvedValue({ execucao: rascunhoExe('...') });
    await preparar([exe({ resposta: 'conversa' })]);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Salvar no cérebro/ }));
    });
    const pedido = api.enviar.mock.calls[0][1];
    expect(pedido.intencao).toBe('rascunho_cerebro');
    expect(pedido.anexos).toBeUndefined();
  });

  it('sem conversa ainda, o atalho explica e não envia', async () => {
    await preparar([]);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Salvar no cérebro/ }));
    });
    expect(api.enviar).not.toHaveBeenCalled();
    expect((await screen.findByRole('alert')).textContent).toContain('converse com a Bia primeiro');
  });

  it('prévia editável → salvar grava com o MESMO request_id e mostra o recibo honesto', async () => {
    api.gravarCaptura
      .mockRejectedValueOnce(new ErroDeApi('A rede falhou.', 0, 'REDE'))
      .mockResolvedValueOnce({ captura: {
        cerebro: 'volc', repo: 'cerebro-volc', caminho: 'inbox/bia-web/2026-10-16-1200-atalhos.md',
        sidecar: 'inbox/bia-web/2026-10-16-1200-atalhos.md.meta.yaml', sha256: 'abcdef0123456789', bytes: 120,
        salvo_no_servidor: true, sincronizado_github: false, git: { estado: '??', commitado: false }, ja_existia: false } });
    await preparar([exe({ resposta: 'conversa' }), rascunhoExe('```json\n' + JSON.stringify(RASCUNHO) + '\n```')]);
    const form = await screen.findByRole('form', { name: 'Captura para o cérebro' });
    expect(within(form).getByText('Rascunho — ainda não salvo')).toBeTruthy();
    const titulo = within(form).getByLabelText('Título') as HTMLInputElement;
    expect(titulo.value).toBe('Atalhos do cérebro na web');
    fireEvent.change(titulo, { target: { value: 'Atalhos (editado)' } });
    fireEvent.change(within(form).getByLabelText('Cérebro'), { target: { value: 'arbitragem' } });
    await act(async () => {
      fireEvent.click(within(form).getByRole('button', { name: /Salvar no cérebro/ }));
    });
    expect((await screen.findByRole('alert')).textContent).toContain('rede falhou');
    await act(async () => {
      fireEvent.click(within(form).getByRole('button', { name: /Salvar no cérebro/ }));
    });
    const [primeiro, segundo] = api.gravarCaptura.mock.calls.map((c) => c[0]);
    expect(segundo.request_id).toBe(primeiro.request_id);
    expect(segundo).toMatchObject({ destino: 'arbitragem', titulo: 'Atalhos (editado)', tipo: 'decisao', execucao_id: 'r1' });
    expect(segundo.conteudo).toContain('## Decisões');
    expect(await screen.findByText('Salvo no servidor')).toBeTruthy();
    expect(screen.getByText('inbox/bia-web/2026-10-16-1200-atalhos.md')).toBeTruthy();
    expect(screen.getByText(/Não sincronizado com o GitHub/)).toBeTruthy();
  });

  it('servidor sem executor: diz o motivo e oferece copiar', async () => {
    api.gravarCaptura.mockRejectedValue(new ErroDeApi(
      'A gravação no cérebro pela web ainda não está ligada neste servidor. Copie a captura e use /salve no Telegram.',
      503, 'cerebro_nao_configurado'));
    await preparar([exe({ resposta: 'conversa' }), rascunhoExe('```json\n' + JSON.stringify(RASCUNHO) + '\n```')]);
    const form = await screen.findByRole('form', { name: 'Captura para o cérebro' });
    await act(async () => {
      fireEvent.click(within(form).getByRole('button', { name: /Salvar no cérebro/ }));
    });
    expect((await screen.findByRole('alert')).textContent).toContain('ainda não está ligada');
    expect(within(form).getByText('Copie e use /salve no Telegram.')).toBeTruthy();
  });

  it('rascunho fora do formato não vira formulário nem grava', async () => {
    await preparar([rascunhoExe('Desculpe, não consegui.')]);
    expect(await screen.findByText('A Bia não devolveu a captura no formato esperado.')).toBeTruthy();
    expect(screen.queryByRole('form', { name: 'Captura para o cérebro' })).toBeNull();
  });

  it('/cerebro mostra o status dos três, só leitura', async () => {
    api.cerebroStatus.mockResolvedValue({ verificado_em: '', somente_leitura: true, repos: [
      { cerebro: 'volc', branch: 'main', commit: 'e5f80c3', commit_em: '', alteracoes: 0, capturas_web_pendentes: 2,
        a_frente: 0, atras: 1, ultima_busca: null, estacao_web: true, ok: true },
    ] });
    const { campo } = await preparar([]);
    await digitar(campo, '/cerebro');
    await teclar(campo, 'Enter');
    expect(await screen.findByText('/cerebro · somente leitura')).toBeTruthy();
    expect(screen.getByText('e5f80c3 · 1 atrás')).toBeTruthy();
    expect(screen.getByText(/Nada foi sincronizado/)).toBeTruthy();
    expect(api.enviar).not.toHaveBeenCalled();
  });
});
