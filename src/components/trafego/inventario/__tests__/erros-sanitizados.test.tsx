// @vitest-environment jsdom
/**
 * O erro que chega ao operador — e tudo que ele deixou de chegar.
 *
 * Esta tela pode gastar dinheiro na conta de um cliente. Quem está diante dela
 * precisa saber três coisas quando uma leitura não volta: o que aconteceu, o
 * que fazer agora, e como quem for investigar encontra a ocorrência. Nada
 * disso é "Endpoint não encontrado (404) em https://…", que era o que a tela
 * mostrava.
 *
 * As provas abaixo estão em três blocos:
 *
 *  1. o mapeador — status vira frase, e o status que ninguém previu também;
 *  2. o vazamento — uma bateria de erros REAIS deste sistema (o texto do
 *     cliente HTTP, o `detail` das rotas do inventário, uma pilha de exceção)
 *     atravessa o mapeador e nada do que veio neles sobrevive;
 *  3. a tela e o hook — a frase, o próximo passo e o código copiável.
 *
 * ⚠️ O bloco 2 é o que envelhece pior se for escrito como lista de palavras
 * proibidas, e por isso ele NÃO é só isso: a prova principal é que a saída
 * pertence a um vocabulário fechado. Uma palavra nova no servidor não abre
 * buraco nenhum, porque nada do servidor é impresso.
 */
import React from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ETAPAS,
  FRASES_DE_FALHA,
  type MotivoDeFalha,
  descreverFalha,
  ehFraseConhecida,
  motivoDaFalha,
  novoCodigoDeOcorrencia,
  ocorrenciaDaFrase,
  statusDe,
} from '@/components/trafego/inventario/erros';
import { FalhaDoInventario } from '@/components/trafego/inventario/EstadosDoInventario';
import { horaExata } from '@/components/trafego/inventario/formato';

// ── dublê do cliente HTTP ───────────────────────────────────────────────────

const api = vi.hoisted(() => ({
  inventario: vi.fn(),
  atualizarConta: vi.fn(),
}));

vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: api }));

// Importado DEPOIS do mock, de propósito: o hook fala com o cliente HTTP, e o
// que interessa aqui é a tradução do erro, não a rede.
const { useInventario, usePedirLeituraDaConta } = await import('@/hooks/useInventario');

const FORMATO_DO_CODIGO = /^VOLC-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}$/;

/** O instante do 429, no fuso de quem lê a tela — nunca em UTC. */
const PROXIMA_LEITURA = '2026-08-25T14:32:07.000Z';
const PROXIMA_LEITURA_LOCAL = horaExata(PROXIMA_LEITURA) as string;

/** Um `QueryClient` que não repete nem espera — o teste mede tradução, não rede. */
function envolver() {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0, gcTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={cliente}>{children}</QueryClientProvider>
  );
}

let consoleSilenciado: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  api.inventario.mockReset();
  api.atualizarConta.mockReset();
  // `registrarDetalhe` grava o detalhe técnico no console de propósito — é o
  // outro lado da moeda de não mostrá-lo na tela. Aqui ele só não deve sujar a
  // saída da suíte.
  consoleSilenciado = vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  consoleSilenciado.mockRestore();
  cleanup();
});

// ── 1 · o mapeador ──────────────────────────────────────────────────────────

describe('status vira frase de operação', () => {
  it('cada status conhecido cai no motivo que descreve o que houve', () => {
    expect(motivoDaFalha({ status: 0 })).toBe('sem_resposta');
    expect(motivoDaFalha({ status: 400 })).toBe('pedido_invalido');
    expect(motivoDaFalha({ status: 401 })).toBe('sessao_expirada');
    expect(motivoDaFalha({ status: 403 })).toBe('sem_permissao');
    expect(motivoDaFalha({ status: 404 })).toBe('indisponivel_nesta_versao');
    expect(motivoDaFalha({ status: 429 })).toBe('leitura_recente_demais');
    expect(motivoDaFalha({ status: 500 })).toBe('sistema_fora_do_ar');
    expect(motivoDaFalha({ status: 503 })).toBe('sistema_fora_do_ar');
  });

  it('erro sem status nenhum é "não falei com o sistema", não "deu ruim"', () => {
    // `fetch` que nem chegou a receber resposta, erro nascido antes da rede,
    // uma string jogada num `throw`: para quem opera, os três são o mesmo fato.
    expect(motivoDaFalha(new TypeError('Failed to fetch'))).toBe('sem_resposta');
    expect(motivoDaFalha(undefined)).toBe('sem_resposta');
    expect(motivoDaFalha('deu errado')).toBe('sem_resposta');
    expect(statusDe({ status: 'quatrocentos' })).toBeNull();
  });

  it('⚠️ o status que ninguém previu NÃO ganha uma causa inventada', () => {
    // Um proxy no meio do caminho, um WAF, um status novo: a tentação é chamar
    // tudo de "o registro não respondeu" e mandar o operador esperar passar.
    // Isso é diagnóstico inventado — o produto inteiro recusa fazer isso com
    // um dado, e não vai começar a fazer com um erro.
    for (const status of [418, 451, 499]) {
      expect(motivoDaFalha({ status })).toBe('nao_prevista');
    }
    const oc = descreverFalha({ status: 418 }, 'inventario');
    expect(oc.mensagem).toBe(FRASES_DE_FALHA.nao_prevista.mensagem);
    expect(oc.proximoPasso).toContain('código desta ocorrência');
  });

  it('a saída pertence SEMPRE ao vocabulário fechado — de 100 a 599', () => {
    const frases = new Set(
      (Object.keys(FRASES_DE_FALHA) as MotivoDeFalha[]).map((m) => FRASES_DE_FALHA[m].mensagem),
    );
    for (let status = 100; status <= 599; status += 1) {
      const oc = descreverFalha({ status, message: 'texto que jamais pode chegar à tela' }, 'inventario');
      expect(frases.has(oc.mensagem)).toBe(true);
      expect(oc.proximoPasso).toBe(FRASES_DE_FALHA[oc.motivo].proximoPasso);
    }
  });

  it('todo motivo diz o que fazer agora — nunca só o que aconteceu', () => {
    for (const motivo of Object.keys(FRASES_DE_FALHA) as MotivoDeFalha[]) {
      const frase = FRASES_DE_FALHA[motivo];
      expect(frase.mensagem.length).toBeGreaterThan(0);
      // Uma frase curta sem saída transfere para o operador a tarefa de
      // adivinhar se ele pode mexer na campanha. É o mesmo defeito de
      // "nenhum resultado" como estado vazio.
      expect(frase.proximoPasso.length).toBeGreaterThan(20);
    }
  });
});

// ── 2 · o vazamento ─────────────────────────────────────────────────────────

/**
 * Erros REAIS deste sistema, copiados das duas pontas que os produzem.
 *
 * Os quatro primeiros são texto que `pautadorApi.request()` monta hoje; os
 * outros são `detail` que as rotas do inventário emitem hoje. Todos chegavam à
 * tela do operador sem passar por lugar nenhum.
 */
const ERROS_DE_VERDADE: unknown[] = [
  {
    status: 0,
    message:
      'Não foi possível conectar ao backend Pautador Pro em https://pautador-api.vercel.app. ' +
      'Verifique: (1) o backend está rodando nessa porta; (2) VITE_PAUTADOR_API_URL aponta ' +
      'para o backend certo; (3) CORS libera a origem do front (PAUTADOR_ALLOWED_ORIGINS).',
  },
  {
    status: 404,
    message:
      'Endpoint não encontrado (404) em https://pautador-api.vercel.app. ' +
      'VITE_PAUTADOR_API_URL pode apontar para outro serviço.',
  },
  {
    status: 503,
    message:
      'não consegui ler o snapshot do inventário: APIError({"code":"42P01","message":' +
      '"relation \\"public.volc_campaign_snapshot\\" does not exist"})',
  },
  {
    status: 503,
    message:
      'Supabase não configurado no backend — sem snapshot de onde ler o inventário. ' +
      'A tela não inventa dado de conta.',
  },
  {
    status: 500,
    message:
      'Traceback (most recent call last):\n' +
      '  File "/var/task/app/trafego/inventario.py", line 214, in montar_inventario\n' +
      '    raise RuntimeError("cursor inválido")',
  },
  {
    status: 400,
    message: 'cursor inválido: não é base64 do payload esperado',
  },
  {
    status: 502,
    message: 'GAQL recusada pela conta 801-785-1692 (customer_id fora do escopo)',
  },
  new TypeError('Failed to fetch'),
  'erro em texto solto',
  null,
];

/** O que não pode aparecer na tela do operador, em nenhuma hipótese. */
const VOCABULARIO_DE_MAQUINA = [
  'http', 'vercel', 'VITE_', 'PAUTADOR_ALLOWED_ORIGINS', 'CORS',
  'PostgREST', 'snapshot', 'payload', 'cursor', 'GAQL', 'SQLSTATE',
  'Traceback', 'APIError', 'RuntimeError', 'relation', 'volc_campaign',
  'Supabase', '.py', '42P01', 'customer_id', 'Endpoint', 'backend',
];

describe('nada do erro cru atravessa', () => {
  it('nenhum erro real deste sistema deixa rastro na frase, no passo ou na cópia', () => {
    for (const erro of ERROS_DE_VERDADE) {
      const oc = descreverFalha(erro, 'inventario');
      const tudo = [oc.mensagem, oc.proximoPasso, oc.complemento ?? '', oc.paraCopiar]
        .join(' ')
        .toLowerCase();
      for (const proibido of VOCABULARIO_DE_MAQUINA) {
        expect(tudo).not.toContain(proibido.toLowerCase());
      }
    }
  });

  it('nem por dentro de um parâmetro chamado "motivo"', () => {
    // O caminho lateral: o componente recebe TEXTO, não o erro. Se ele
    // confiasse no texto, bastaria alguém passar `error.message` adiante para
    // o vazamento voltar por uma porta que ninguém estava olhando.
    const oc = ocorrenciaDaFrase(
      'Endpoint não encontrado (404) em https://pautador-api.vercel.app.',
      'inventario',
    );
    expect(oc.mensagem).toBe(FRASES_DE_FALHA.nao_prevista.mensagem);
    expect(oc.paraCopiar).not.toContain('Endpoint');
    expect(ehFraseConhecida('Endpoint não encontrado (404)')).toBe(false);
    expect(ehFraseConhecida(FRASES_DE_FALHA.sistema_fora_do_ar.mensagem)).toBe(true);
  });

  it('o único fato do servidor que passa é um INSTANTE, e vem de campo próprio', () => {
    // O 429 do inventário responde a pergunta que vem logo depois de "esta
    // conta foi lida há pouco tempo": quando posso pedir de novo. Um instante
    // não tem como carregar caminho de arquivo nem pilha de exceção.
    const oc = descreverFalha(
      {
        status: 429,
        message: 'LimiteExcedido: proxima varredura de 801-785-1692 em app/trafego/sincronizador.py',
        corpo: { mensagem: 'não olhe para mim', proxima_em: PROXIMA_LEITURA, intervalo_s: 900 },
      },
      'leitura_de_conta',
    );
    expect(oc.mensagem).toBe(FRASES_DE_FALHA.leitura_recente_demais.mensagem);
    expect(oc.complemento).toContain(PROXIMA_LEITURA_LOCAL);
    expect(oc.complemento).not.toContain('não olhe para mim');
    expect(oc.complemento).not.toContain('sincronizador');
  });
});

// ── 3 · o código copiável ───────────────────────────────────────────────────

describe('o código da ocorrência', () => {
  it('tem formato estável e alfabeto sem caractere que se confunde ao ditar', () => {
    for (let i = 0; i < 200; i += 1) {
      const codigo = novoCodigoDeOcorrencia();
      expect(codigo).toMatch(FORMATO_DO_CODIGO);
      // `0/O`, `1/I/L` saem do alfabeto porque o código vai ser lido em voz
      // alta e digitado de novo do outro lado.
      expect(codigo.slice(5)).not.toMatch(/[01OIL]/);
    }
  });

  it('o texto copiado leva o que permite achar a ocorrência do outro lado', () => {
    const oc = descreverFalha({ status: 503 }, 'inventario', {
      id: 'VOLC-ABC234',
      agora: new Date('2026-08-25T10:11:12.000Z'),
    });
    expect(oc.paraCopiar).toContain('VOLC-ABC234');
    expect(oc.paraCopiar).toContain(FRASES_DE_FALHA.sistema_fora_do_ar.mensagem);
    expect(oc.paraCopiar).toContain(ETAPAS.inventario);
    expect(oc.paraCopiar).toContain(oc.quando);
    expect(oc.quando).not.toBe('');
  });

  it('quando o servidor der um identificador, é o DELE que a tela mostra', () => {
    // Enquanto nenhuma rota emite um, o código nasce aqui e o par (instante,
    // etapa) é o que liga tela e log. No dia em que o servidor emitir, os dois
    // lados passam a falar do mesmo identificador sem nenhuma tela mudar.
    const oc = descreverFalha(
      { status: 500, corpo: { correlation_id: 'req-9f3a21' } },
      'inventario',
    );
    expect(oc.id).toBe('req-9f3a21');
  });

  it('um campo de id carregando texto longo não vira porta de vazamento', () => {
    const oc = descreverFalha(
      { status: 500, corpo: { request_id: 'Traceback (most recent call last): File "/var/task/app.py"' } },
      'inventario',
    );
    expect(oc.id).toMatch(FORMATO_DO_CODIGO);
  });
});

// ── 4 · a tela ──────────────────────────────────────────────────────────────

describe('a tela da falha', () => {
  it('mostra frase curta, próximo passo e código — e não o texto cru', () => {
    render(<FalhaDoInventario motivo="Erro interno do backend (500) em /api/trafego/inventario" />);

    expect(screen.getByRole('heading', { level: 2, name: 'Não consegui ler o inventário' })).toBeTruthy();
    expect(screen.getByText(FRASES_DE_FALHA.nao_prevista.mensagem)).toBeTruthy();
    expect(screen.getByText(FRASES_DE_FALHA.nao_prevista.proximoPasso)).toBeTruthy();
    expect(screen.queryByText(/api\/trafego/)).toBeNull();
    expect(screen.queryByText(/500/)).toBeNull();

    const codigo = screen.getByText(FORMATO_DO_CODIGO);
    expect(codigo.textContent).toMatch(FORMATO_DO_CODIGO);
  });

  it('a falha é anunciada — quem não olhou para a tela precisa saber que ela mudou', () => {
    render(<FalhaDoInventario ocorrencia={descreverFalha({ status: 503 }, 'inventario')} />);
    const alerta = screen.getByRole('alert');
    expect(alerta.textContent).toContain(FRASES_DE_FALHA.sistema_fora_do_ar.mensagem);
  });

  it('o código NÃO muda a cada render — um identificador que dança não acha nada', () => {
    const { rerender } = render(<FalhaDoInventario motivo={null} />);
    const primeiro = screen.getByText(FORMATO_DO_CODIGO).textContent;
    rerender(<FalhaDoInventario motivo={null} />);
    expect(screen.getByText(FORMATO_DO_CODIGO).textContent).toBe(primeiro);
  });

  it('copiar é BOTÃO, e ele entrega a ocorrência inteira', async () => {
    const escrever = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: escrever },
      configurable: true,
    });

    const oc = descreverFalha({ status: 503 }, 'inventario', { id: 'VOLC-ABC234' });
    render(<FalhaDoInventario ocorrencia={oc} />);

    const botao = screen.getByRole('button', { name: 'copiar código' });
    fireEvent.click(botao);

    await waitFor(() => expect(escrever).toHaveBeenCalledTimes(1));
    expect(escrever.mock.calls[0][0]).toContain('VOLC-ABC234');
    expect(escrever.mock.calls[0][0]).toContain(ETAPAS.inventario);

    // ⚠️ O nome acessível do botão NÃO muda para "copiado". Trocar o texto do
    // botão troca a identidade do controle debaixo da mão de quem está com o
    // foco nele; a confirmação vive na região viva ao lado.
    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toContain('Código copiado'),
    );
    expect(screen.getByRole('button', { name: 'copiar código' })).toBe(botao);
  });

  it('quando o navegador não deixa copiar, o operador é avisado e o código continua legível', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('NotAllowedError')) },
      configurable: true,
    });
    // Sem plano B disponível: é o cenário de contexto inseguro.
    Object.defineProperty(document, 'execCommand', { value: undefined, configurable: true });

    const oc = descreverFalha({ status: 503 }, 'inventario', { id: 'VOLC-ABC234' });
    render(<FalhaDoInventario ocorrencia={oc} />);
    fireEvent.click(screen.getByRole('button', { name: 'copiar código' }));

    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toContain('Não consegui copiar'),
    );
    // O botão nunca foi o único caminho para o dado.
    expect(screen.getByText('VOLC-ABC234')).toBeTruthy();
  });
});

// ── 5 · o hook ──────────────────────────────────────────────────────────────

describe('a fronteira traduz antes de a tela ver', () => {
  it('motivoDaFalha é frase de operação, nunca o texto do cliente HTTP', async () => {
    api.inventario.mockRejectedValue({
      status: 404,
      message: 'Endpoint não encontrado (404) em https://pautador-api.vercel.app. VITE_PAUTADOR_API_URL pode apontar para outro serviço.',
    });

    const { result } = renderHook(() => useInventario(), { wrapper: envolver() });
    await waitFor(() => expect(result.current.falhou).toBe(true));

    expect(result.current.motivoDaFalha).toBe(FRASES_DE_FALHA.indisponivel_nesta_versao.mensagem);
    expect(result.current.ocorrencia?.id).toMatch(FORMATO_DO_CODIGO);
  });

  it('o detalhe técnico não some: ele vai para o console, não para a tela', async () => {
    api.inventario.mockRejectedValue({ status: 500, message: 'Traceback (most recent call last)' });
    const { result } = renderHook(() => useInventario(), { wrapper: envolver() });
    await waitFor(() => expect(result.current.falhou).toBe(true));
    expect(consoleSilenciado).toHaveBeenCalled();
  });
});

describe('pedido de leitura de uma conta', () => {
  it('⚠️ leitura ACEITA deixou de ser anunciada como recusa', async () => {
    // O contrato do cliente promete `{aceito, motivo}`; a rota devolve
    // `{escopo, custo, resultado, escrita_permitida}`. Com o teste antigo
    // (`if (resposta.aceito)`), `undefined` caía no ramo da recusa e TODA
    // leitura bem-sucedida virava "o servidor recusou o pedido e não disse por
    // quê". O operador conclui que o botão não funciona e clica de novo — e
    // cada clique custa cota da conta de anúncio do cliente.
    api.atualizarConta.mockResolvedValue({
      escopo: { customer_id: '8017851692', janela: 'LAST_30_DAYS', contas: 1 },
      custo: { consultas_gaql: 5, duracao_ms: 812 },
      resultado: { campanhas: 12 },
      escrita_permitida: false,
    });

    const { result } = renderHook(() => usePedirLeituraDaConta(), { wrapper: envolver() });
    result.current.pedir('8017851692');

    await waitFor(() => expect(result.current.recados['8017851692']).toBeTruthy());
    expect(result.current.recados['8017851692']).toContain('leitura pedida');
    expect(result.current.recados['8017851692']).not.toContain('recusou');
  });

  it('a recusa explícita é dita sem repetir o texto do servidor', async () => {
    api.atualizarConta.mockResolvedValue({ aceito: false, motivo: 'LimiteExcedido em sincronizador.py' });
    const { result } = renderHook(() => usePedirLeituraDaConta(), { wrapper: envolver() });
    result.current.pedir('8017851692');

    await waitFor(() => expect(result.current.recados['8017851692']).toBeTruthy());
    const recado = result.current.recados['8017851692'];
    expect(recado).not.toContain('sincronizador');
    expect(recado).not.toContain('LimiteExcedido');
    expect(recado).toContain('Código da ocorrência: VOLC-');
  });

  it('a falha traz o código dentro da frase — o cabeçalho da conta imprime uma linha só', async () => {
    api.atualizarConta.mockRejectedValue({
      status: 429,
      message: 'LimiteExcedido: 900s em app/trafego/sincronizador.py',
      corpo: { proxima_em: PROXIMA_LEITURA, intervalo_s: 900 },
    });

    const { result } = renderHook(() => usePedirLeituraDaConta(), { wrapper: envolver() });
    result.current.pedir('8017851692');

    await waitFor(() => expect(result.current.recados['8017851692']).toBeTruthy());
    const recado = result.current.recados['8017851692'];
    expect(recado).toContain(FRASES_DE_FALHA.leitura_recente_demais.mensagem);
    expect(recado).toContain(PROXIMA_LEITURA_LOCAL);
    expect(recado).toMatch(/Código da ocorrência: VOLC-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}\./);
    expect(recado).not.toContain('sincronizador');
    expect(recado).not.toContain('.py');
  });
});
