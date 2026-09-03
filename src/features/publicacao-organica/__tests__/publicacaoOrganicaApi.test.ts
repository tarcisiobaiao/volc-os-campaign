/**
 * O CLIENTE HTTP, sozinho — sem tela e sem rede.
 *
 * ## Por que este arquivo existe
 *
 * ⚠️ DEFEITO MEDIDO (revisão de 02/09/2026): os 27 testes de tela substituem
 * este módulo inteiro por `vi.spyOn(api, …)`. Com isso, `pedir`, `autorizacao`,
 * `falhaDaResposta`, `endereco` e a leitura da idempotência NUNCA executavam, e
 * duas mutações provadas passavam com a suíte 44/44 verde:
 *
 *   (a) trocar a recusa por sessão ausente por `return {}` — o cliente passaria
 *       a chamar as rotas ANÔNIMO, e todas elas têm `Depends(exigir_admin)`;
 *   (b) deixar de traduzir rede caída em 503 — e "não consegui perguntar" viraria
 *       "não há nada", que é a mentira que a tela inteira existe para evitar.
 *
 * Aqui `fetch` é uma função de mentira e a sessão é uma variável. Nenhum byte
 * sai desta máquina: o que se prova é o que este módulo DECIDE.
 *
 * ## A ginástica do módulo
 *
 * `API_BASE` é lido de `import.meta.env` no momento do import. Por isso cada
 * cenário faz `vi.resetModules()` + `vi.stubEnv` e importa de novo — é a única
 * forma de exercitar o ramo "sem endereço configurado" sem mexer no módulo.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * A sessão que o cliente vai encontrar. `vi.hoisted` porque `vi.mock` é içado
 * para o topo do arquivo: uma `const` comum ainda não existiria quando a
 * fábrica do mock roda.
 */
const estado = vi.hoisted(() => ({
  sessao: { access_token: 'tok-de-teste' } as { access_token: string } | null,
}));

vi.mock('@/lib/supabase', () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: estado.sessao } }) } },
}));

const BASE = 'https://api.exemplo.test';
const PREFIXO = '/api/publicacao-organica';

type Api = typeof import('../publicacaoOrganicaApi');

/** Recarrega o módulo com um endereço de API — `''` é o ambiente sem base. */
async function carregar(base: string = `${BASE}/`): Promise<Api> {
  vi.resetModules();
  vi.stubEnv('VITE_PAUTADOR_API_URL', base);
  return import('../publicacaoOrganicaApi');
}

/** Uma resposta de mentira, com o mínimo que `pedir` toca. */
function resposta(
  { status = 200, corpo = {} as unknown, headers = {} as Record<string, string>, ilegivel = false } = {},
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (nome: string) => headers[nome] ?? null },
    json: async () => {
      if (ilegivel) throw new SyntaxError('Unexpected token < in JSON at position 0');
      return corpo;
    },
  } as unknown as Response;
}

/**
 * Espera a RECUSA e devolve o erro já tipado.
 *
 * ⚠️ `promessa.catch((e) => e)` devolveria a união "recibo ou erro", e um teste
 * escrito assim passaria despercebido se a chamada resolvesse: `erro.codigo`
 * seria `undefined` e a comparação com `undefined` nunca aconteceria porque o
 * `expect` compara com um literal. Aqui, resolver é falha explícita.
 */
async function recusa(promessa: Promise<unknown>): Promise<InstanceType<Api['ErroDaPublicacao']>> {
  try {
    await promessa;
  } catch (erro) {
    return erro as InstanceType<Api['ErroDaPublicacao']>;
  }
  throw new Error('a chamada resolveu quando devia ter recusado');
}

let fetchFalso: ReturnType<typeof vi.fn>;

beforeEach(() => {
  estado.sessao = { access_token: 'tok-de-teste' };
  fetchFalso = vi.fn(async () => resposta({ corpo: { jobs: [] } }));
  vi.stubGlobal('fetch', fetchFalso);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

/** Todas as chamadas do cliente, cada uma pronta para ser disparada. */
function todasAsChamadas(api: Api): Array<[string, () => Promise<unknown>]> {
  return [
    ['listarDestinos', () => api.listarDestinos()],
    ['listarJobs', () => api.listarJobs()],
    ['detalharJob', () => api.detalharJob('job-1')],
    ['prontidao', () => api.prontidao()],
    ['criarJob', () => api.criarJob({
      peca_id: 'p', peca_versao: 1, autorizacao_id: 'a', destino_id: 'd',
      modo: 'draft', timezone: 'America/Sao_Paulo', texto: 'oi',
    })],
    ['liberar', () => api.liberar('job-1')],
    ['despachar', () => api.despachar('job-1')],
    ['reconciliar', () => api.reconciliar('job-1')],
    ['cancelar', () => api.cancelar('job-1', 'mudei de ideia')],
  ];
}

// ─────────────────────────────────────────────────────────────────────────────

describe('sem sessão — nenhuma rota deste cliente vira anônima', () => {
  /**
   * ⚠️ A MUTAÇÃO (a). Trocar o `throw` de `autorizacao()` por `return {}` fazia
   * o cliente mandar TODAS as chamadas sem `Authorization`. Nenhum teste caía,
   * porque nenhum teste chamava o cliente de verdade. O que este teste afirma é
   * o mais barato de perder e o mais caro de descobrir em produção: sem token,
   * ninguém sequer sai da máquina.
   */
  it('toda chamada levanta 401 `sessao_ausente` e NÃO chega a chamar fetch', async () => {
    const api = await carregar();
    estado.sessao = null;

    for (const [nome, chamar] of todasAsChamadas(api)) {
      const erro = await chamar().then(() => null, (e: unknown) => e);
      expect(erro, `${nome} devia ter levantado`).toBeInstanceOf(api.ErroDaPublicacao);
      const falha = erro as InstanceType<Api['ErroDaPublicacao']>;
      expect(falha.status, nome).toBe(401);
      expect(falha.codigo, nome).toBe('sessao_ausente');
      expect(falha.semSessao, nome).toBe(true);
      // A frase é para o humano: "entre de novo", não um erro de rede.
      expect(falha.message, nome).toMatch(/sessão expirou/i);
    }
    expect(fetchFalso, 'nenhuma rota pode ser chamada sem credencial').not.toHaveBeenCalled();
  });

  it('sessão sem access_token conta como sessão ausente', async () => {
    const api = await carregar();
    estado.sessao = {} as { access_token: string };
    await expect(api.listarJobs()).rejects.toMatchObject({ codigo: 'sessao_ausente', status: 401 });
    expect(fetchFalso).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('a credencial e o endereço que saem daqui', () => {
  it('manda o Bearer da sessão e JSON em toda chamada', async () => {
    const api = await carregar();
    await api.listarDestinos();
    const [, init] = fetchFalso.mock.calls[0] as [string, RequestInit];
    const cabecalhos = init.headers as Record<string, string>;
    expect(cabecalhos.Authorization).toBe('Bearer tok-de-teste');
    expect(cabecalhos['Content-Type']).toBe('application/json');
  });

  it('monta o endereço com o prefixo, e só com os filtros preenchidos', async () => {
    const api = await carregar();
    await api.listarJobs({ estado: 'pronto', limite: 10 });
    expect(fetchFalso.mock.calls[0][0]).toBe(`${BASE}${PREFIXO}/jobs?estado=pronto&limite=10`);

    // ⚠️ Filtro vazio não vira `?estado=`: o backend trataria a string vazia
    // como um estado, e a lista voltaria vazia por um filtro que ninguém pediu.
    fetchFalso.mockClear();
    await api.listarJobs({ estado: '', limite: undefined });
    expect(fetchFalso.mock.calls[0][0]).toBe(`${BASE}${PREFIXO}/jobs`);
  });

  it('a barra final do endereço configurado não vira barra dupla', async () => {
    const api = await carregar(`${BASE}/`); // com a barra final, como num .env real
    await api.prontidao();
    expect(fetchFalso.mock.calls[0][0]).toBe(`${BASE}${PREFIXO}/prontidao`);
  });

  it('o identificador do job é escapado no caminho', async () => {
    const api = await carregar();
    await api.detalharJob('job 1/2');
    expect(fetchFalso.mock.calls[0][0]).toBe(`${BASE}${PREFIXO}/jobs/job%201%2F2`);
  });

  it('sem VITE_PAUTADOR_API_URL não há pergunta nenhuma — e a tela sabe disso', async () => {
    const api = await carregar('');
    expect(api.publicacaoConfigurada()).toBe(false);
    await expect(api.listarJobs()).rejects.toMatchObject({ codigo: 'sem_base', status: 503 });
    // ⚠️ `sem_base` é 503 de propósito: é indisponibilidade de ambiente, e a
    // tela mostra a mesma família de aviso — nunca uma fila vazia.
    const erro = await recusa(api.listarJobs());
    expect(erro.indisponivel).toBe(true);
    expect(fetchFalso).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('rede caída é INDISPONIBILIDADE, nunca lista vazia', () => {
  /**
   * ⚠️ A MUTAÇÃO (b). Um `catch` que devolvesse `{ jobs: [] }` — ou que deixasse
   * o `TypeError` do `fetch` subir cru — apagaria a diferença entre "não há
   * publicação" e "não consegui perguntar". A tela tem estados separados para as
   * duas coisas, e eles só funcionam se o cliente traduzir a queda em 503.
   */
  it('fetch que rejeita vira ErroDaPublicacao 503 — e não resolve', async () => {
    const api = await carregar();
    fetchFalso.mockRejectedValue(new TypeError('Failed to fetch'));

    const resultado = await api.listarJobs().then(
      (v) => ({ resolveu: true, valor: v as unknown }),
      (e) => ({ resolveu: false, valor: e as unknown }),
    );
    expect(resultado.resolveu, 'rede caída não pode virar resposta').toBe(false);
    expect(resultado.valor).toBeInstanceOf(api.ErroDaPublicacao);
    const erro = resultado.valor as InstanceType<Api['ErroDaPublicacao']>;
    expect(erro.status).toBe(503);
    expect(erro.codigo).toBe('publicacao_indisponivel');
    expect(erro.indisponivel).toBe(true);
    expect(erro.message).toMatch(/não foi possível falar com a publicação/i);
  });

  it('a queda de rede não vaza a mensagem do runtime para a tela', async () => {
    const api = await carregar();
    fetchFalso.mockRejectedValue(new TypeError('request to https://api.exemplo.test failed, ECONNREFUSED 10.0.0.7:8000'));
    const erro = await recusa(api.despachar('job-1'));
    expect(erro.message).not.toMatch(/ECONNREFUSED|10\.0\.0\.7/);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('os códigos que a tela precisa distinguir', () => {
  it('401 é sessão, e a frase manda entrar de novo', async () => {
    const api = await carregar();
    fetchFalso.mockResolvedValue(resposta({ status: 401, corpo: { detail: { codigo: 'x', mensagem: 'y' } } }));
    const erro = await recusa(api.listarJobs());
    expect(erro.status).toBe(401);
    expect(erro.codigo).toBe('sessao_expirada');
    expect(erro.semSessao).toBe(true);
    expect(erro.semPermissao).toBe(false);
  });

  it('403 é PAPEL, não sessão — são telas diferentes', async () => {
    const api = await carregar();
    fetchFalso.mockResolvedValue(resposta({ status: 403 }));
    const erro = await recusa(api.listarJobs());
    expect(erro.codigo).toBe('sem_permissao');
    expect(erro.semPermissao).toBe(true);
    expect(erro.semSessao).toBe(false);
    expect(erro.message).toMatch(/exclusiva para administradores/i);
  });

  it('409 é conflito de ESTADO, e o código vem do corpo do backend', async () => {
    const api = await carregar();
    fetchFalso.mockResolvedValue(resposta({
      status: 409,
      corpo: { detail: { codigo: 'transicao_invalida', mensagem: 'este job já saiu de rascunho' } },
    }));
    const erro = await recusa(api.liberar('job-1'));
    expect(erro.status).toBe(409);
    expect(erro.conflito).toBe(true);
    expect(erro.codigo).toBe('transicao_invalida');
    expect(erro.message).toBe('este job já saiu de rascunho');
    expect(erro.indisponivel).toBe(false);
  });

  it('o corpo `{detail:{codigo,mensagem}}` é lido — é ele que fala com o humano', async () => {
    const api = await carregar();
    fetchFalso.mockResolvedValue(resposta({
      status: 400,
      corpo: {
        detail: {
          codigo: 'horario_invalido',
          mensagem: "o horario local precisa ser 'AAAA-MM-DD HH:MM' — sem fuso no texto",
        },
      },
    }));
    const erro = await recusa(api.criarJob({
      peca_id: 'p', peca_versao: 1, autorizacao_id: 'a', destino_id: 'd',
      modo: 'schedule', timezone: 'America/Sao_Paulo', horario_local: 'amanhã', texto: 'oi',
    }));
    expect(erro.codigo).toBe('horario_invalido');
    expect(erro.message).toMatch(/AAAA-MM-DD HH:MM/);
    expect(erro.status).toBe(400);
  });

  it('detail em forma estranha não vira frase nenhuma inventada', async () => {
    const api = await carregar();
    // `detail` como string é o formato padrão do FastAPI quando alguém levanta
    // `HTTPException("texto")` sem o dicionário do módulo.
    fetchFalso.mockResolvedValue(resposta({ status: 422, corpo: { detail: 'coisa crua do servidor' } }));
    const erro = await recusa(api.listarJobs());
    expect(erro.codigo).toBe('resposta_sem_detalhe');
    expect(erro.message).not.toContain('coisa crua do servidor');
  });

  it('500 sem corpo legível vira indisponibilidade, não recusa', async () => {
    const api = await carregar();
    fetchFalso.mockResolvedValue(resposta({ status: 500, ilegivel: true }));
    const erro = await recusa(api.reconciliar('job-1'));
    expect(erro.codigo).toBe('publicacao_indisponivel');
    expect(erro.indisponivel).toBe(true);
    expect(erro.status).toBe(500);
  });

  it('a página de erro de um proxy no meio não chega ao operador', async () => {
    const api = await carregar();
    // ⚠️ O corpo é HTML: `json()` levanta. Devolver o texto cru entregaria nome
    // e versão do servidor para a tela — e daí para um print de tela.
    fetchFalso.mockResolvedValue(resposta({ status: 502, ilegivel: true }));
    const erro = await recusa(api.listarJobs());
    expect(erro.message).not.toMatch(/<html|nginx/i);
    expect(erro.message).toMatch(/não foi possível falar com a publicação/i);
  });

  it('200 com corpo ilegível é `resposta_ilegivel`, e não um recibo vazio', async () => {
    const api = await carregar();
    fetchFalso.mockResolvedValue(resposta({ status: 200, ilegivel: true }));
    const erro = await recusa(api.despachar('job-1'));
    expect(erro.codigo).toBe('resposta_ilegivel');
    expect(erro.status).toBe(200);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('idempotência — o CORPO manda, o header só reforça', () => {
  /**
   * ⚠️ O comentário que estava aqui dizia que "o header é a única forma de saber
   * que um 200 foi replay". É falso duas vezes: `rotas._responder` deriva o
   * header DO CORPO (`recibo["idempotente"]`), e o `CORSMiddleware` de
   * `backend/app/main.py` não declara `expose_headers` — num pedido
   * cross-origin, que é o do operador, `headers.get(...)` devolve `null`.
   * Confiar no header significaria dizer "job criado" a cada replay.
   */
  it('o corpo diz replay e o header nem existe (o caso do CORS): ainda é replay', async () => {
    const api = await carregar();
    fetchFalso.mockResolvedValue(resposta({
      corpo: { job_id: 'job-1', estado: 'rascunho', idempotente: true },
      headers: {}, // o navegador não entrega o header sem `expose_headers`
    }));
    const recibo = await api.criarJob({
      peca_id: 'p', peca_versao: 1, autorizacao_id: 'a', destino_id: 'd',
      modo: 'draft', timezone: 'America/Sao_Paulo', texto: 'oi',
    });
    expect(recibo.idempotente).toBe(true);
  });

  it('o corpo diz que é novo, mesmo sem header', async () => {
    const api = await carregar();
    fetchFalso.mockResolvedValue(resposta({ corpo: { job_id: 'job-1', idempotente: false } }));
    expect((await api.liberar('job-1')).idempotente).toBe(false);
  });

  it('sem o campo no corpo, o header entra como reforço', async () => {
    const api = await carregar();
    fetchFalso.mockResolvedValue(resposta({
      corpo: { job_id: 'job-1' },
      headers: { 'X-Publicacao-Idempotente': 'replay' },
    }));
    expect((await api.despachar('job-1')).idempotente).toBe(true);

    fetchFalso.mockResolvedValue(resposta({
      corpo: { job_id: 'job-1' },
      headers: { 'X-Publicacao-Idempotente': 'novo' },
    }));
    expect((await api.despachar('job-1')).idempotente).toBe(false);
  });

  it('sem campo e sem header, a tela não afirma nada sobre replay', async () => {
    const api = await carregar();
    fetchFalso.mockResolvedValue(resposta({ corpo: { job_id: 'job-1' } }));
    expect((await api.despachar('job-1')).idempotente).toBeUndefined();
  });

  it('quando os dois falam, o corpo tem a palavra final', async () => {
    const api = await carregar();
    fetchFalso.mockResolvedValue(resposta({
      corpo: { job_id: 'job-1', idempotente: false },
      headers: { 'X-Publicacao-Idempotente': 'replay' },
    }));
    expect((await api.reconciliar('job-1')).idempotente).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('o que sai no corpo de cada escrita', () => {
  it('criar manda POST com o corpo de `corpoDoPedido`, e nada além dele', async () => {
    const api = await carregar();
    await api.criarJob({
      peca_id: 'p', peca_versao: 3, autorizacao_id: 'a', destino_id: 'd',
      modo: 'now', timezone: 'America/Sao_Paulo', texto: 'oi',
      confirmo_publicacao_imediata: true,
    });
    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE}${PREFIXO}/jobs`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      peca_id: 'p', peca_versao: 3, autorizacao_id: 'a', destino_id: 'd',
      modo: 'now', timezone: 'America/Sao_Paulo', texto: 'oi',
      imagens: [], confirmo_publicacao_imediata: true,
    });
    // ⚠️ Nenhuma chave de idempotência sai daqui: ela é derivada no backend, e
    // `JobEntrada` é `extra="forbid"` — mandar uma faria o pedido voltar 400.
    expect(JSON.parse(String(init.body))).not.toHaveProperty('chave');
  });

  it('cancelar manda o motivo, e cada ato tem a sua rota', async () => {
    const api = await carregar();
    await api.cancelar('job-1', 'peça errada');
    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE}${PREFIXO}/jobs/job-1/cancelar`);
    expect(JSON.parse(String(init.body))).toEqual({ motivo: 'peça errada' });

    for (const [nome, chamar] of [
      ['liberar', () => api.liberar('job-1')],
      ['despachar', () => api.despachar('job-1')],
      ['reconciliar', () => api.reconciliar('job-1')],
    ] as Array<[string, () => Promise<unknown>]>) {
      fetchFalso.mockClear();
      await chamar();
      const [rota, opcoes] = fetchFalso.mock.calls[0] as [string, RequestInit];
      expect(rota, nome).toBe(`${BASE}${PREFIXO}/jobs/job-1/${nome}`);
      expect(opcoes.method, nome).toBe('POST');
    }
  });
});
