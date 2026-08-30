// @vitest-environment jsdom
// @vitest-environment-options { "url": "http://localhost:8080" }
/**
 * O fluxo de login, de ponta a ponta, com o cliente Supabase DE VERDADE.
 *
 * ---------------------------------------------------------------------------
 * POR QUE ESTE ARQUIVO EXISTE
 * ---------------------------------------------------------------------------
 * Em 24/08/2026, depois do commit 4a08ef2, um usuário existente — cadastrado em
 * `auth.users`, cadastrado em `public.users`, papel ADMIN — passou a ver
 * "Acesso concedido" seguido de "o email não está cadastrado". As duas frases
 * na mesma sessão, em sequência, contando histórias opostas.
 *
 * Nenhuma delas era verdade: a primeira apareceu antes de qualquer autorização
 * ser verificada, e a segunda era o texto que `AuthContext` mostrava para
 * QUALQUER falha — rede, 500, 503, 401 ou 403. Um `catch` que não distingue os
 * motivos transforma "não consegui perguntar" em "a pessoa não existe".
 *
 * O cliente Supabase aqui é o real, não um dublê. O que está falso é só a rede:
 * `fetch` responde pelo GoTrue e por `/api/me`. Isso importa porque metade dos
 * defeitos deste fluxo vive na máquina de estados do `auth-js` — o lock, a
 * ordem dos eventos, a reentrância — e um dublê de `supabase.auth` esconderia
 * exatamente a parte que quebrou.
 */
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

vi.stubEnv('VITE_SUPABASE_URL', 'https://gotrue.teste');
vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'anon-de-teste');
vi.stubEnv('VITE_API_URL', '');

const EMAIL = 'tarcisio@agenciavolc.com.br';

/**
 * Armazenamento em memória.
 *
 * O jsdom deste ambiente não expõe `localStorage` (origem opaca), e o
 * `supabase-js` guarda a sessão exatamente ali — sem isso não há como testar
 * "recarregar a página preserva a sessão", que é um dos aceites.
 */
function instalarArmazenamento() {
  const mapa = new Map<string, string>();
  const memoria = {
    getItem: (k: string) => (mapa.has(k) ? mapa.get(k)! : null),
    setItem: (k: string, v: string) => void mapa.set(k, String(v)),
    removeItem: (k: string) => void mapa.delete(k),
    clear: () => mapa.clear(),
    key: (i: number) => [...mapa.keys()][i] ?? null,
    get length() { return mapa.size; },
  };
  Object.defineProperty(globalThis, 'localStorage', { value: memoria, configurable: true, writable: true });
  if (typeof window !== 'undefined') {
    Object.defineProperty(window, 'localStorage', { value: memoria, configurable: true, writable: true });
  }
  return memoria;
}

let armazenamento = instalarArmazenamento();

const PERFIL = {
  id: 'perfil-legado-ad77fa75',
  name: 'Tarcísio',
  email: EMAIL,
  role: 'ADMIN' as const,
  needs_password_change: false,
  first_login: false,
  commission_percentage: 0,
};

function sessaoFalsa() {
  const agora = Math.floor(Date.now() / 1000);
  return {
    access_token: 'access-token-de-teste',
    refresh_token: 'refresh-de-teste',
    token_type: 'bearer',
    expires_in: 3600,
    expires_at: agora + 3600,
    // Os ids de auth.users e public.users são legados e NÃO coincidem neste
    // sistema. O teste reflete isso de propósito: a resolução tem de funcionar
    // por e-mail, e um teste que usasse o mesmo id nos dois esconderia a
    // regressão no dia em que alguém "simplificasse" a busca.
    user: {
      id: 'auth-uuid-diferente-do-perfil',
      email: EMAIL,
      aud: 'authenticated',
      role: 'authenticated',
      app_metadata: {},
      user_metadata: {},
      created_at: new Date().toISOString(),
    },
  };
}

/** O que o `/api/me` falso vai responder na próxima chamada. */
let respostaDoMe: { status: number; corpo: unknown };
/** Toda chamada a `/api/me`, com o cabeçalho Authorization que chegou. */
let chamadasAoMe: Array<{ autorizacao: string | null }>;

function instalarRede() {
  chamadasAoMe = [];
  respostaDoMe = { status: 200, corpo: PERFIL };

  globalThis.fetch = vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
    const url = String(typeof entrada === 'string' ? entrada : entrada instanceof URL ? entrada.href : (entrada as Request).url);
    const cabecalhos = new Headers(init?.headers as HeadersInit | undefined);

    if (url.includes('/api/me')) {
      chamadasAoMe.push({ autorizacao: cabecalhos.get('authorization') });
      if (respostaDoMe.status === 0) throw new TypeError('Failed to fetch');
      return new Response(JSON.stringify(respostaDoMe.corpo), {
        status: respostaDoMe.status,
        headers: { 'content-type': 'application/json' },
      });
    }

    // GoTrue
    if (url.includes('/token?grant_type=password')) {
      return new Response(JSON.stringify(sessaoFalsa()), {
        status: 200, headers: { 'content-type': 'application/json' },
      });
    }
    if (url.includes('/logout')) return new Response('{}', { status: 204 });
    if (url.includes('/user')) {
      return new Response(JSON.stringify(sessaoFalsa().user), {
        status: 200, headers: { 'content-type': 'application/json' },
      });
    }
    return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } });
  }) as unknown as typeof fetch;
}

/** Mostra o estado do contexto como texto, para o teste ler sem adivinhação. */
function fabricarSonda(useAuth: typeof import('@/contexts/AuthContext').useAuth) {
  return function Sonda({ aoEntrar }: { aoEntrar: (fn: () => Promise<void>) => void }) {
    const auth = useAuth();
    React.useEffect(() => {
      aoEntrar(() => auth.signIn(EMAIL, 'senha-de-teste'));
    }, [auth, aoEntrar]);
    return (
      <div>
        <span data-testid="perfil">{auth.userProfile ? auth.userProfile.role : 'sem-perfil'}</span>
        <span data-testid="nao-autorizado">{auth.unauthorizedUser ?? 'nenhum'}</span>
        <span data-testid="carregando">{auth.loading ? 'sim' : 'nao'}</span>
        <span data-testid="usuario">{auth.user ? auth.user.email : 'sem-usuario'}</span>
        <span data-testid="sessao">{auth.session ? 'presente' : 'ausente'}</span>
        <span data-testid="falha">{auth.falha ? auth.falha.tipo : 'nenhuma'}</span>
      </div>
    );
  };
}

async function montar() {
  const { AuthProvider, useAuth } = await import('@/contexts/AuthContext');
  const Sonda = fabricarSonda(useAuth);
  let entrar!: () => Promise<void>;
  render(
    <AuthProvider>
      <Sonda aoEntrar={(fn) => { entrar = fn; }} />
    </AuthProvider>,
  );
  await waitFor(() => expect(screen.getByTestId('carregando').textContent).toBe('nao'));
  return { entrar: () => entrar() };
}

beforeEach(() => {
  vi.resetModules();
  armazenamento.clear();
  instalarRede();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('login de um usuário que existe', () => {
  it('entra no sistema e instala o perfil', async () => {
    const { entrar } = await montar();
    await entrar();

    await waitFor(() => expect(screen.getByTestId('perfil').textContent).toBe('ADMIN'));
    expect(screen.getByTestId('nao-autorizado').textContent).toBe('nenhum');
    expect(screen.getByTestId('usuario').textContent).toBe(EMAIL);
  });

  it('manda o access_token da sessão em TODA chamada a /api/me', async () => {
    const { entrar } = await montar();
    await entrar();

    await waitFor(() => expect(chamadasAoMe.length).toBeGreaterThan(0));
    for (const chamada of chamadasAoMe) {
      expect(chamada.autorizacao, 'chamou /api/me sem Authorization')
        .toBe('Bearer access-token-de-teste');
    }
  });

  it('não dispara uma enxurrada de chamadas duplicadas', async () => {
    // getSession inicial, INITIAL_SESSION, SIGNED_IN e TOKEN_REFRESHED podem
    // todos querer o perfil. Sem coordenação, cada um abre uma requisição — e
    // basta uma falhar para o `catch` derrubar a sessão de todas.
    const { entrar } = await montar();
    await entrar();
    await waitFor(() => expect(screen.getByTestId('perfil').textContent).toBe('ADMIN'));
    await new Promise((r) => setTimeout(r, 120));

    expect(chamadasAoMe.length, `/api/me chamado ${chamadasAoMe.length} vezes`)
      .toBeLessThanOrEqual(1);
  });
});

/**
 * `signIn` REJEITA quando a senha estava certa mas o acesso não foi concedido.
 * É de propósito: é isso que impede a tela de comemorar antes da autorização.
 * O teste captura o motivo e depois confere o estado que sobrou.
 */
async function entrarEsperandoFalha(entrar: () => Promise<void>) {
  try {
    await entrar();
    throw new Error('signIn resolveu, mas a autorização deveria ter falhado');
  } catch (erro) {
    if (erro instanceof Error && erro.message.startsWith('signIn resolveu')) throw erro;
    return erro as import('@/contexts/AuthContext').ErroDeAutorizacao;
  }
}

describe('os motivos de falha não podem virar todos a mesma frase', () => {
  it('403 SEM_CADASTRO — e só ele — marca o usuário como não cadastrado', async () => {
    respostaDoMe = { status: 403, corpo: { error: 'sem cadastro', codigo: 'SEM_CADASTRO' } };
    const { entrar } = await montar();
    const erro = await entrarEsperandoFalha(entrar);

    expect(erro.falha.tipo).toBe('sem_cadastro');
    expect(erro.falha.podeTentarNovamente).toBe(false);
    await waitFor(() => expect(screen.getByTestId('nao-autorizado').textContent).toBe(EMAIL));
    expect(screen.getByTestId('perfil').textContent).toBe('sem-perfil');
  });

  it('erro de rede NÃO diz que o usuário não existe', async () => {
    respostaDoMe = { status: 0, corpo: null };
    const { entrar } = await montar();
    const erro = await entrarEsperandoFalha(entrar);

    expect(erro.falha.tipo).toBe('indisponivel');
    expect(erro.falha.podeTentarNovamente, 'rede caída deve permitir tentar de novo').toBe(true);
    expect(screen.getByTestId('nao-autorizado').textContent,
      'a rede caiu e o sistema respondeu que a pessoa não existe').toBe('nenhum');
    // A sessão FICA guardada: tentar de novo não pode exigir digitar a senha.
    await waitFor(() => expect(screen.getByTestId('sessao').textContent).toBe('presente'));
    // Mas o acesso NÃO é concedido — `user` sem perfil passaria pelas
    // restrições de OPERATOR no ProtectedRoute.
    expect(screen.getByTestId('usuario').textContent).toBe('sem-usuario');
  });

  it('500 do servidor NÃO diz que o usuário não existe', async () => {
    respostaDoMe = { status: 500, corpo: { error: 'Não foi possível verificar as permissões.' } };
    const { entrar } = await montar();
    const erro = await entrarEsperandoFalha(entrar);

    expect(erro.falha.tipo).toBe('indisponivel');
    expect(screen.getByTestId('nao-autorizado').textContent).toBe('nenhum');
    expect(screen.getByTestId('usuario').textContent).toBe('sem-usuario');
  });

  it('503 de configuração NÃO diz que o usuário não existe', async () => {
    respostaDoMe = { status: 503, corpo: { error: 'backend mal configurado', codigo: 'CONFIG_AUSENTE' } };
    const { entrar } = await montar();
    const erro = await entrarEsperandoFalha(entrar);

    expect(erro.falha.tipo).toBe('indisponivel');
    expect(erro.falha.codigo).toBe('CONFIG_AUSENTE');
    expect(screen.getByTestId('nao-autorizado').textContent).toBe('nenhum');
  });

  it('401 encerra a sessão e pede login de novo, sem acusar cadastro', async () => {
    respostaDoMe = { status: 401, corpo: { error: 'Sessão inválida ou expirada.', codigo: 'SESSAO_INVALIDA' } };
    const { entrar } = await montar();
    const erro = await entrarEsperandoFalha(entrar);

    expect(erro.falha.tipo).toBe('sessao_invalida');
    expect(screen.getByTestId('perfil').textContent).toBe('sem-perfil');
    expect(screen.getByTestId('nao-autorizado').textContent,
      'sessão expirada não é ausência de cadastro').toBe('nenhum');
  });
});

describe('recarregar a página', () => {
  it('preserva a sessão e reinstala o perfil sem novo login', async () => {
    const primeira = await montar();
    await primeira.entrar();
    await waitFor(() => expect(screen.getByTestId('perfil').textContent).toBe('ADMIN'));

    // Recarregar = desmontar tudo e montar de novo, com o localStorage intacto.
    // Recarregar não limpa o armazenamento — é justamente o ponto.
    cleanup();
    vi.resetModules();
    chamadasAoMe = [];

    await montar();
    await waitFor(() => expect(screen.getByTestId('perfil').textContent).toBe('ADMIN'));
    expect(screen.getByTestId('nao-autorizado').textContent).toBe('nenhum');
  });
});

/**
 * Lê um arquivo do repositório.
 *
 * `import.meta.url` não serve aqui: este arquivo roda em jsdom com a URL do
 * ambiente definida (`http://localhost:8080`), então `import.meta.url` é uma
 * URL http e `fileURLToPath` recusa. O `cwd` do vitest é a raiz do projeto.
 */
async function lerFonte(caminhoRelativo: string): Promise<string> {
  const { readFileSync } = await import('node:fs');
  const { join } = await import('node:path');
  return readFileSync(join(process.cwd(), caminhoRelativo), 'utf8');
}

describe('a tela não comemora antes da autorização', () => {
  it('signIn só resolve depois que /api/me respondeu 200', async () => {
    // A prova mecânica do aceite: enquanto `/api/me` está pendente, `signIn`
    // continua pendente. Como o toast de "Acesso concedido" está DEPOIS do
    // `await signIn(...)` em Login.tsx, ele não tem como aparecer antes.
    let liberar!: () => void;
    const pendente = new Promise<void>((r) => { liberar = r; });

    const redeOriginal = globalThis.fetch;
    globalThis.fetch = (async (entrada: RequestInfo | URL, init?: RequestInit) => {
      if (String(entrada).includes('/api/me')) {
        await pendente;
      }
      return redeOriginal(entrada as RequestInfo, init);
    }) as typeof fetch;

    const { entrar } = await montar();

    let resolveu = false;
    const promessa = entrar().then(() => { resolveu = true; });

    await new Promise((r) => setTimeout(r, 150));
    expect(resolveu, 'signIn resolveu com /api/me ainda pendente').toBe(false);
    expect(screen.getByTestId('perfil').textContent).toBe('sem-perfil');

    liberar();
    await promessa;
    expect(resolveu).toBe(true);
    await waitFor(() => expect(screen.getByTestId('perfil').textContent).toBe('ADMIN'));
  });

  it('Login.tsx só chama o toast de sucesso DEPOIS do await signIn', async () => {
    // Guarda de ordem no código-fonte. Um teste de render provaria o mesmo,
    // mas esta versão sobrevive a refatorações da coreografia visual e falha
    // exatamente no dia em que alguém mover o toast para cima do await.
    const fonte = await lerFonte('src/pages/Login.tsx');
    const posAwait = fonte.indexOf('await signIn(email, password)');
    // A CHAMADA, não a menção: o comentário logo acima do await cita a frase
    // ao explicar o defeito, e casar por texto solto acharia o comentário.
    const posToast = fonte.search(/toast\(\{\s*title:\s*["']Acesso concedido["']/);
    expect(posAwait, 'o await signIn sumiu — revisar este teste').toBeGreaterThan(0);
    expect(posToast, 'o toast de sucesso sumiu — revisar este teste').toBeGreaterThan(0);
    expect(posToast, 'o toast de sucesso voltou para antes da autorização')
      .toBeGreaterThan(posAwait);
  });
});

describe('o lock do auth-js não pode ser tocado de dentro do callback', () => {
  it('AuthContext não chama getSession() em lugar nenhum', async () => {
    // `_notifyAllSubscribers` aguarda cada subscriber DENTRO do lock de sessão,
    // e `getSession()` pede o mesmo lock; o caminho reentrante do
    // `_acquireLock` faz `await last`, onde `last` é a promise que está
    // esperando o callback. Espera circular.
    //
    // O jsdom NÃO reproduz isso (não tem `navigator.locks`), então este teste
    // estático é a única defesa automatizada que resta. Não relaxe para "não
    // chama dentro do callback": a chamada pode migrar para uma função
    // auxiliar e o teste pararia de ver.
    const fonte = await lerFonte('src/contexts/AuthContext.tsx');
    const chamadas = fonte
      .split('\n')
      .map((linha, i) => ({ linha, n: i + 1 }))
      .filter(({ linha }) => /supabase\.auth\.getSession\s*\(/.test(linha))
      .filter(({ linha }) => !linha.trimStart().startsWith('*') && !linha.trimStart().startsWith('//'))
      .map(({ n }) => `src/contexts/AuthContext.tsx:${n}`);

    expect(chamadas, 'getSession() de volta no AuthContext').toEqual([]);
  });

  it('o callback de onAuthStateChange não é async', async () => {
    const fonte = await lerFonte('src/contexts/AuthContext.tsx');
    const assinatura = fonte.match(/onAuthStateChange\(\s*(async\s*)?\(/);
    expect(assinatura, 'onAuthStateChange sumiu — revisar este teste').not.toBeNull();
    expect(assinatura![1], 'o callback voltou a ser async: ele roda com o lock tomado')
      .toBeUndefined();
  });

  it('secureApi.me aceita o token explícito, sem consultar a sessão', async () => {
    const fonte = await import('@/lib/secureApi');
    expect(fonte.secureApi.me.length, 'me() perdeu o parâmetro de token').toBe(1);
  });
});
