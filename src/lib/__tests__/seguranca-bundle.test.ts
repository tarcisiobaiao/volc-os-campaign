/**
 * A superfície pública — o bundle e as rotas privilegiadas.
 *
 * ## O que estava medido em 24/08/2026, nesta árvore
 *
 * | defeito | onde | estado |
 * |---|---|---|
 * | proxy aceita QUALQUER tabela, com `service_role`, sem autenticação | `api/supabase/query.js:34` | FECHADO (1A.1a) |
 * | proxy chama QUALQUER função do banco | `api/supabase/rpc.js:34` | FECHADO (1A.1a) |
 * | `select('*')` em `public.users` (que tem `password_hash`) | `api/users/query.js:36` | FECHADO (1A.1a) |
 * | `Access-Control-Allow-Origin: '*'` nos quatro proxies | `api/supabase/query.js:11` | FECHADO (1A.1a) |
 * | a chave do portão do backend viaja no bundle | `src/lib/pautadorApi.ts:37` | ABERTO — fecha em 1A.1b |
 * | e é enviada pelo navegador como `X-API-Key` | `src/lib/pautadorApi.ts:97,682` | ABERTO — fecha em 1A.1b |
 *
 * `public.users` estava com RLS DESABILITADA e zero policies. Ou seja: um
 * `POST /api/supabase/query {table:'users', select:'*'}` de qualquer origem
 * devolvia `password_hash`, `token_primeiro_acesso` e `role` do único ADMIN.
 * CORS não impede isso — `curl` não lê `Access-Control-Allow-Origin`.
 *
 * ## Como a fatia 1A.1a fechou
 *
 * Não colocando um portão dentro do proxy genérico: **removendo o proxy**. Um
 * endpoint que recebe o nome da tabela e o nome da função no corpo continua
 * sendo um cliente Postgres remoto mesmo autenticado — o portão só decidiria
 * QUEM tem o banco inteiro na mão. No lugar entraram rotas nomeadas onde
 * nenhum identificador de banco vem da requisição:
 *
 *   GET  /api/me                      -> `api/_lib/perfil.js`
 *   POST /api/users                   -> `api/_lib/usuarios.js`
 *   GET|PUT /api/settings             -> `api/_lib/configuracoes.js`
 *   PUT  /api/settings/exchange-rate  -> `api/_lib/configuracoes.js`
 *
 * Por isso os testes abaixo verificam DUAS coisas diferentes: que os arquivos
 * antigos não existem mais (§2) e que os novos recusam anônimo antes de tocar
 * no banco (§3). Só a segunda não bastaria — alguém poderia readicionar o
 * proxy amanhã e a suíte continuaria verde.
 *
 * ## O contrato deste arquivo
 *
 * Os testes de §1 que ainda falham são o gate da fatia 1A.1b: a chave do
 * Pautador dentro do bundle. **Este arquivo não fica verde no fim de 1A.1a, e
 * isso está correto.** Declarar 1A.1b pronta com eles vermelhos é que não está.
 *
 * ## O irmão deste arquivo
 *
 * `backend/tests/test_seguranca_hub.py` cobre a outra metade — o portão do
 * FastAPI, o papel consultado pelo `sub`, a falha fechada e a trava de escrita.
 */
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { beforeEach, describe, expect, it, vi } from 'vitest';

// O guarda de identidade responde 503 quando falta configuração — falha
// fechada, e correta. Aqui damos valores falsos para que os testes exercitem o
// PORTÃO, e não o 503. O `createClient` está mockado logo abaixo, então nenhuma
// destas strings chega a lugar nenhum.
process.env.SUPABASE_URL = process.env.SUPABASE_URL || 'http://supabase.invalido';
process.env.SUPABASE_SERVICE_ROLE_KEY =
  process.env.SUPABASE_SERVICE_ROLE_KEY || 'service-role-de-teste';

const RAIZ = fileURLToPath(new URL('../../../', import.meta.url));

// ── varredura de arquivos ──────────────────────────────────────────────────

function arquivos(dir: string, extensoes: string[]): string[] {
  if (!existsSync(dir)) return [];
  const achados: string[] = [];
  for (const nome of readdirSync(dir)) {
    if (nome === 'node_modules' || nome === '.git') continue;
    const caminho = join(dir, nome);
    if (statSync(caminho).isDirectory()) {
      achados.push(...arquivos(caminho, extensoes));
    } else if (extensoes.some((e) => nome.endsWith(e))) {
      achados.push(caminho);
    }
  }
  return achados;
}

const ler = (caminho: string) => readFileSync(caminho, 'utf8');
const curto = (caminho: string) => relative(RAIZ, caminho);

/** Aponta o arquivo e a LINHA — um achado sem linha vira caça ao tesouro. */
function ocorrencias(caminho: string, padrao: RegExp): string[] {
  return ler(caminho)
    .split('\n')
    .map((linha, i) => ({ linha, n: i + 1 }))
    .filter(({ linha }) => padrao.test(linha) && !linha.trimStart().startsWith('*'))
    .map(({ n }) => `${curto(caminho)}:${n}`);
}

// ══════════════════════════════════════════════════════════════════════════
// 1. Nenhuma credencial de backend no que é publicado
// ══════════════════════════════════════════════════════════════════════════

/**
 * A ÚNICA `VITE_*` sensível que pode existir.
 *
 * A anon key é pública POR DESENHO: ela identifica o projeto e quem protege o
 * dado é a RLS do Postgres, não o segredo da chave. Toda as outras entram na
 * lista abaixo se, e somente se, alguém provar o mesmo — o que significa
 * responder "o que um estranho consegue fazer com ela?" com "nada".
 */
const VITE_PERMITIDAS = new Set(['VITE_SUPABASE_ANON_KEY']);

/** Procura JWT e devolve os que têm papel diferente de `anon`. */
function jwtsPrivilegiados(texto: string): string[] {
  const jwt = /eyJ[A-Za-z0-9_-]{10,}\.(eyJ[A-Za-z0-9_-]{10,})\.[A-Za-z0-9_-]{10,}/g;
  const achados: string[] = [];
  for (const casamento of texto.matchAll(jwt)) {
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(Buffer.from(casamento[1], 'base64url').toString('utf8'));
    } catch {
      continue; // não era JWT, era só base64 parecido
    }
    const papel = String(payload.role ?? '');
    if (papel && papel !== 'anon') achados.push(`role=${papel}`);
  }
  return achados;
}

describe('o código-fonte não carrega credencial de backend', () => {
  // O próprio arquivo de teste fala dos nomes proibidos o tempo todo; incluí-lo
  // na varredura faria a suíte acusar a si mesma para sempre.
  const fontes = arquivos(join(RAIZ, 'src'), ['.ts', '.tsx'])
    .filter((a) => !a.includes('__tests__'));

  it('nenhuma VITE_*KEY/SECRET/TOKEN é lida como credencial fora da lista', () => {
    // ⚠️ FALHA HOJE: `VITE_PAUTADOR_API_KEY` (src/lib/pautadorApi.ts:37).
    // Tudo que começa com `VITE_` é substituído pelo VALOR LITERAL no build —
    // "colocar no .env" não esconde nada, publica. A chave que ela carrega é a
    // mesma `PAUTADOR_API_KEY` que é o único portão de 21 rotas do backend, então
    // o bundle entrega o portão inteiro para quem abrir o DevTools.
    //
    // O padrão exige `import.meta.env.` na frente: é a LEITURA que vira valor
    // literal no bundle. Citar o nome numa mensagem de erro não vaza nada, e um
    // teste que confunde as duas coisas é abandonado no primeiro falso positivo.
    const achados: string[] = [];
    for (const arquivo of fontes) {
      ler(arquivo).split('\n').forEach((linha, i) => {
        for (const casamento of linha.matchAll(
          /import\.meta\.env(?:\.|\[['"])(VITE_[A-Z0-9_]*(?:KEY|SECRET|TOKEN))/g,
        )) {
          if (VITE_PERMITIDAS.has(casamento[1])) continue;
          achados.push(`${casamento[1]} em ${curto(arquivo)}:${i + 1}`);
        }
      });
    }
    expect(achados, 'credencial de backend embutida no bundle').toEqual([]);
  });

  it('o navegador não monta o cabeçalho X-API-Key', () => {
    // ⚠️ FALHA HOJE: src/lib/pautadorApi.ts:97 e :682.
    // Um segredo compartilhado com o navegador não é segredo — e enquanto o
    // front o envia, ninguém consegue rotacionar a chave sem quebrar a tela,
    // que é como um vazamento vira permanente.
    const achados = fontes.flatMap((a) => ocorrencias(a, /['"`]X-API-Key['"`]\s*:/i));
    expect(achados, 'o front envia a chave do portão do backend').toEqual([]);
  });

  it('nenhum JWT privilegiado foi colado no código', () => {
    // O acidente clássico: copiar a `service_role` do painel do Supabase para
    // "testar rapidinho" e commitar. Ela ignora RLS — é o banco inteiro.
    const achados = fontes.flatMap((a) =>
      jwtsPrivilegiados(ler(a)).map((r) => `${curto(a)}: ${r}`));
    expect(achados, 'JWT privilegiado no código-fonte').toEqual([]);
  });

  it('o cliente do backend autentica pela sessão do Supabase', () => {
    // ⚠️ FALHA HOJE: `pautadorApi.ts` não menciona `Authorization` nem a sessão.
    // Não basta remover a chave: sem mandar o token da sessão o front fica sem
    // credencial nenhuma, e a "solução" mais provável de quem for consertar a
    // tela depois é reabrir o portão do backend.
    //
    // Duas formas valem, porque as duas já existem nesta casa:
    // montar o header (`src/services/incubatorService.ts:205`) ou pegar a
    // sessão de `@/lib/supabase` e repassar. O que não vale é nenhuma das duas.
    const texto = ler(join(RAIZ, 'src', 'lib', 'pautadorApi.ts'));
    const montaHeader = /['"`]Authorization['"`]\s*:/.test(texto);
    const usaSessao = /getSession|access_token/.test(texto);
    expect(montaHeader || usaSessao,
      'pautadorApi.ts não envia o token da sessão em lugar nenhum').toBe(true);
  });
});

/**
 * O artefato publicado. Conferência A MAIS, não a única.
 *
 * `dist/` é gerado e pode não existir numa checagem limpa — por isso estes
 * testes pulam quando não há build. Nenhum buraco fica descoberto: cada um tem
 * um gêmeo acima que varre `src/` e roda sempre. O valor de varrer o `dist/` é
 * outro: pegar o caso em que a fonte foi limpa e o build antigo continua no ar.
 */
describe('o bundle já construído (dist/)', () => {
  const construidos = arquivos(join(RAIZ, 'dist'), ['.js', '.css', '.html', '.map']);
  const semBuild = construidos.length === 0;

  it.skipIf(semBuild)('nenhum JWT com papel diferente de anon foi embutido', () => {
    // A varredura decodifica o payload em vez de procurar o nome da variável —
    // o que importa é o VALOR ter vazado, e no bundle o nome já não existe.
    const achados = construidos.flatMap((a) =>
      jwtsPrivilegiados(ler(a)).map((r) => `${curto(a)}: ${r}`));
    expect(achados, 'JWT privilegiado publicado no bundle').toEqual([]);
  });

  it.skipIf(semBuild)('o bundle não carrega o cabeçalho X-API-Key', () => {
    // ⚠️ FALHA HOJE (1 ocorrência em dist/assets/index-*.js), e é exatamente o
    // caso que justifica varrer o artefato: enquanto este build estiver
    // publicado, a chave continua indo para o navegador de quem abre o site.
    const achados = construidos.filter((a) => ler(a).includes('X-API-Key')).map(curto);
    expect(achados, 'o bundle publicado ainda manda a chave do backend').toEqual([]);
  });
});

// ══════════════════════════════════════════════════════════════════════════
// 2. Os proxies `service_role` — comportamento, não intenção
// ══════════════════════════════════════════════════════════════════════════

/** Tudo que o cliente falso do Supabase viu. É a prova de que NADA foi tocado. */
const espiao: { chamadas: Array<{ metodo: string; args: unknown[] }> } = { chamadas: [] };

/** Quem o GoTrue falso devolve. `null` = requisição anônima. */
let usuarioDoTeste: { id: string; email: string } | null = null;

function clienteFalso() {
  const consulta: Record<string, unknown> = {};
  const encadeaveis = [
    'select', 'eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'like', 'ilike', 'in',
    'insert', 'update', 'delete', 'order', 'limit', 'single', 'maybeSingle',
  ];
  for (const metodo of encadeaveis) {
    consulta[metodo] = (...args: unknown[]) => {
      espiao.chamadas.push({ metodo, args });
      return consulta;
    };
  }
  // Thenable: `await query` resolve como o supabase-js resolveria.
  consulta.then = (resolver: (v: unknown) => unknown) => resolver({ data: [], error: null });
  return {
    from: (tabela: string) => {
      espiao.chamadas.push({ metodo: 'from', args: [tabela] });
      return consulta;
    },
    rpc: (nome: string, params: unknown) => {
      espiao.chamadas.push({ metodo: 'rpc', args: [nome, params] });
      return Promise.resolve({ data: null, error: null });
    },
    auth: {
      // Anônimo por padrão: sem sessão válida. Os testes que precisam de um
      // usuário sobrescrevem via `comUsuario()`.
      getUser: (...args: unknown[]) => {
        espiao.chamadas.push({ metodo: 'auth.getUser', args });
        return Promise.resolve(
          usuarioDoTeste
            ? { data: { user: usuarioDoTeste }, error: null }
            : { data: { user: null }, error: { message: 'invalid token' } },
        );
      },
      admin: {
        createUser: (...args: unknown[]) => {
          espiao.chamadas.push({ metodo: 'auth.admin.createUser', args });
          return Promise.resolve({ data: { user: { id: 'id-falso' } }, error: null });
        },
        deleteUser: (...args: unknown[]) => {
          espiao.chamadas.push({ metodo: 'auth.admin.deleteUser', args });
          return Promise.resolve({ data: null, error: null });
        },
      },
    },
  };
}

// ⚠️ Com este mock, qualquer toque no banco vira registro no espião em vez de
// requisição de verdade — o único jeito honesto de testar uma rota que carrega
// `service_role` sem tocar em produção.
//
// Note que `api/_lib/identidade.js` cria o client SOB DEMANDA (lazy), e não no
// escopo do módulo como faziam os proxies antigos. Por isso `_resetarClienteParaTeste()`
// existe: sem ele, o primeiro teste fixaria o client em cache e os seguintes
// veriam um espião congelado.
vi.mock('@supabase/supabase-js', () => ({ createClient: () => clienteFalso() }));

type Resposta = {
  statusCode: number;
  corpo: unknown;
  headers: Record<string, string>;
  setHeader: (nome: string, valor: unknown) => void;
  status: (codigo: number) => Resposta;
  json: (corpo: unknown) => Resposta;
  end: () => Resposta;
};

function fabricarRes(): Resposta {
  const headers: Record<string, string> = {};
  const res = {
    statusCode: 0,
    corpo: undefined as unknown,
    headers,
    setHeader(nome: string, valor: unknown) {
      headers[nome.toLowerCase()] = String(valor);
    },
    status(codigo: number) {
      res.statusCode = codigo;
      return res;
    },
    json(corpo: unknown) {
      res.corpo = corpo;
      return res;
    },
    end() {
      return res;
    },
  };
  return res;
}

/**
 * Carrega o handler serverless.
 *
 * O caminho é montado em tempo de execução de propósito: `tsconfig.app.json`
 * não tem `allowJs`, então um `import` literal de `.js` viraria erro de
 * compilação no gate de tipos (`npx tsc --noEmit -p tsconfig.app.json`) — um
 * teste de segurança não pode quebrar o gate que ele deveria reforçar.
 */
async function carregar(caminho: string): Promise<(req: unknown, res: Resposta) => Promise<void>> {
  const especificador = ['..', '..', '..', ...caminho.split('/')].join('/');
  const modulo = await import(/* @vite-ignore */ especificador);
  return modulo.default;
}

/** Uma requisição de fora: sem cookie, sem Bearer, com Origin de terceiro. */
function requisicaoAnonima(corpo: unknown, metodo = 'POST') {
  return {
    method: metodo,
    headers: { origin: 'https://site-de-terceiro.example', 'content-type': 'application/json' },
    body: corpo,
    query: {},
  };
}

/** Requisição com Bearer, para provar o que acontece DEPOIS do portão. */
function requisicaoComToken(corpo: unknown, metodo = 'POST', query: Record<string, unknown> = {}) {
  return {
    method: metodo,
    headers: {
      origin: 'http://localhost:8080',
      'content-type': 'application/json',
      authorization: 'Bearer token-de-teste',
    },
    body: corpo,
    query,
  };
}

/** Os status que significam "recusado". 400 não conta: é validação, não portão. */
const RECUSADO = [401, 403];

beforeEach(async () => {
  espiao.chamadas = [];
  usuarioDoTeste = null;
  // Sem isto o client lazy fica em cache entre os testes e o espião congela.
  const identidade = await import(/* @vite-ignore */ '../../../api/_lib/identidade.js');
  identidade._resetarClienteParaTeste();
});

// ══════════════════════════════════════════════════════════════════════════
// 2. Os proxies genéricos não existem mais — e não podem voltar
// ══════════════════════════════════════════════════════════════════════════

/**
 * Por que testar AUSÊNCIA de arquivo em vez de só testar o portão das rotas
 * novas: um proxy que aceita `{table, select}` continua sendo um cliente
 * Postgres remoto mesmo com Bearer. O portão decidiria apenas QUEM leva o
 * banco inteiro. A correção é a rota não existir, e isto é o que garante que
 * ela não volte num merge do upstream sem alguém reparar.
 */
describe('a superfície genérica com service_role foi removida', () => {
  const REMOVIDOS = [
    'api/supabase/query.js',
    'api/supabase/insert.js',
    'api/supabase/update.js',
    'api/supabase/delete.js',
    'api/supabase/rpc.js',
    'api/users/query.js',
    'api/users/create.js',
  ];

  it('nenhum handler que recebe tabela ou função pelo corpo continua no disco', () => {
    const sobreviventes = REMOVIDOS.filter((rel) => existsSync(join(RAIZ, rel)));
    expect(sobreviventes, 'proxy genérico de volta em api/').toEqual([]);
  });

  it('o Express não registra nenhuma das rotas removidas', () => {
    const express = ler(join(RAIZ, 'server/index.js'));
    const registradas = express
      .split('\n')
      .map((linha, i) => ({ linha, n: i + 1 }))
      .filter(({ linha }) => /^app\.(get|post|put|patch|delete)\(/.test(linha.trim()))
      .filter(({ linha }) => /\/api\/(supabase|users)\/(query|insert|update|delete|rpc|create)/.test(linha))
      .map(({ n }) => `server/index.js:${n}`);
    expect(registradas, 'o dev voltou a expor um proxy que a produção não tem').toEqual([]);
  });

  it('nenhuma rota de api/ lê o nome de uma tabela ou função da requisição', () => {
    // O furo antigo tinha uma assinatura precisa: `supabase.from(table)` onde
    // `table` vinha de `req.body`. Um `.from(TABELA)` com constante de módulo
    // é o formato CORRETO — proibir toda variável obrigaria a repetir o
    // literal e o teste seria abandonado no primeiro falso positivo.
    //
    // Então a regra é: ou é literal, ou é uma constante MAIÚSCULA definida no
    // próprio arquivo como literal. Qualquer outra coisa é suspeita.
    const suspeitas: string[] = [];

    for (const arquivo of arquivos(join(RAIZ, 'api'), ['.js'])) {
      const fonte = ler(arquivo);
      const linhas = fonte.split('\n');

      linhas.forEach((linha, i) => {
        if (linha.trimStart().startsWith('*') || linha.trimStart().startsWith('//')) return;
        // `Buffer.from` / `Array.from` não têm nada a ver com o banco.
        for (const m of linha.matchAll(/(?<!Buffer|Array)\.(from|rpc)\(\s*([A-Za-z_$][\w$]*)/g)) {
          const identificador = m[2];
          const constanteLiteral = new RegExp(
            `const\\s+${identificador}\\s*=\\s*['"\`]`,
          );
          const ehMaiuscula = /^[A-Z][A-Z0-9_]*$/.test(identificador);
          if (ehMaiuscula && constanteLiteral.test(fonte)) return;
          suspeitas.push(`${curto(arquivo)}:${i + 1} -> .${m[1]}(${identificador})`);
        }
      });
    }

    expect(suspeitas, 'identificador de banco escolhido por valor dinâmico').toEqual([]);
  });

  it('o frontend não tem mais cliente de tabela genérica', () => {
    const cliente = ler(join(RAIZ, 'src/lib/secureApi.ts'));
    for (const proibido of ['/api/supabase/', 'table:', 'functionName']) {
      expect(cliente, `secureApi.ts ainda fala em ${proibido}`).not.toContain(proibido);
    }
  });
});

// ══════════════════════════════════════════════════════════════════════════
// 3. As rotas nomeadas — comportamento, não intenção
// ══════════════════════════════════════════════════════════════════════════

describe('GET /api/me — o perfil de quem pede', () => {
  it('sem credencial, recusa antes de tocar no banco', async () => {
    const handler = await carregar('api/me.js');
    const res = fabricarRes();
    await handler(requisicaoAnonima(undefined, 'GET'), res);

    expect(RECUSADO, `respondeu ${res.statusCode}`).toContain(res.statusCode);
    const tocouTabela = espiao.chamadas.filter((c) => c.metodo === 'from');
    expect(tocouTabela, 'a rota consultou uma tabela sem saber quem perguntou').toEqual([]);
  });

  it('não aceita e-mail de terceiro — não existe parâmetro de entrada', async () => {
    // A rota antiga era um oráculo: testava-se e-mail por e-mail quem tem conta.
    const handler = await carregar('api/me.js');
    const res = fabricarRes();
    await handler(requisicaoAnonima({ email: 'admin@agenciavolc.com.br' }, 'GET'), res);

    expect(RECUSADO).toContain(res.statusCode);
    const argumentos = JSON.stringify(espiao.chamadas);
    expect(argumentos, 'o e-mail do corpo chegou ao banco').not.toContain('admin@agenciavolc.com.br');
  });

  it('mesmo autenticado, nunca faz select(*) numa tabela com hash de senha', async () => {
    // Com usuário válido a rota passa do portão e chega ao banco — que é
    // exatamente o momento a observar: o que ela PEDE quando tem permissão.
    usuarioDoTeste = { id: 'uuid-de-teste', email: 'operador@example.com' };
    const handler = await carregar('api/me.js');
    const res = fabricarRes();
    await handler(requisicaoComToken(undefined, 'GET'), res);

    const selects = espiao.chamadas.filter((c) => c.metodo === 'select');
    expect(selects.length, 'nenhum select foi emitido — o teste não provou nada').toBeGreaterThan(0);
    for (const s of selects) {
      const colunas = String(s.args[0] ?? '');
      expect(colunas, 'select(*) numa tabela com password_hash').not.toBe('*');
      for (const sensivel of ['password_hash', 'token_primeiro_acesso', 'token_expiracao']) {
        expect(colunas, `coluna sensível pedida: ${sensivel}`).not.toContain(sensivel);
      }
    }
  });

  it('a whitelist de colunas não contém nenhuma credencial', async () => {
    const { COLUNAS_PERFIL } = await import(/* @vite-ignore */ '../../../api/_lib/identidade.js');
    // `needs_password_change` é um sinalizador booleano de fluxo, não uma
    // credencial — por isso o padrão mira o material que serve para autenticar
    // ou para quebrar senha offline, e não a palavra "password" solta.
    const proibidas = (COLUNAS_PERFIL as string[]).filter((c) =>
      /(hash|secret|senha|(^|_)token(_|$)|_key(_|$))/i.test(c),
    );
    expect(proibidas, 'coluna de credencial na whitelist do perfil').toEqual([]);
  });
});

describe('POST /api/users — o cadastro que cria dono do sistema', () => {
  it('a criação de usuário exige papel administrativo', async () => {
    const handler = await carregar('api/users.js');
    const res = fabricarRes();
    await handler(
      requisicaoAnonima({
        name: 'Intruso', email: 'intruso@example.com',
        password: 'senha-qualquer-123', role: 'ADMIN',
      }),
      res,
    );
    expect(RECUSADO, `respondeu ${res.statusCode}`).toContain(res.statusCode);
    expect(espiao.chamadas.map((c) => c.metodo), 'um usuário foi criado sem identidade')
      .not.toContain('auth.admin.createUser');
  });

  it('um usuário autenticado sem papel ADMIN também é recusado', async () => {
    usuarioDoTeste = { id: 'uuid-operador', email: 'operador@example.com' };
    const handler = await carregar('api/users.js');
    const res = fabricarRes();
    await handler(
      requisicaoComToken({
        name: 'Escalada', email: 'escalada@example.com',
        password: 'senha-qualquer-123', role: 'ADMIN',
      }),
      res,
    );
    // O perfil falso resolve `{data: []}` -> sem cadastro -> 403.
    expect(RECUSADO, `respondeu ${res.statusCode}`).toContain(res.statusCode);
    expect(espiao.chamadas.map((c) => c.metodo)).not.toContain('auth.admin.createUser');
  });

  it('o papel não é gravado em user_metadata, que o próprio usuário edita', () => {
    const fonte = ler(join(RAIZ, 'api/_lib/usuarios.js'));
    const metadata = fonte.match(/user_metadata:\s*\{[^}]*\}/);
    expect(metadata, 'user_metadata sumiu — revisar este teste').not.toBeNull();
    expect(metadata![0], 'o papel voltou para um campo editável pelo usuário')
      .not.toContain('role');
  });
});

describe('/api/settings — a configuração que era um proxy de tabela', () => {
  it('leitura sem credencial é recusada antes do banco', async () => {
    const handler = await carregar('api/settings.js');
    const res = fabricarRes();
    await handler(requisicaoAnonima(undefined, 'GET'), res);

    expect(RECUSADO, `respondeu ${res.statusCode}`).toContain(res.statusCode);
    expect(espiao.chamadas.filter((c) => c.metodo === 'from')).toEqual([]);
  });

  it('escrita sem credencial é recusada antes do banco', async () => {
    const handler = await carregar('api/settings.js');
    const res = fabricarRes();
    await handler(requisicaoAnonima({ settings: [{ key: 'gam_last_update', value: 'x' }] }, 'PUT'), res);

    expect(RECUSADO, `respondeu ${res.statusCode}`).toContain(res.statusCode);
    expect(espiao.chamadas.filter((c) => c.metodo === 'update')).toEqual([]);
  });

  it('a lista de chaves legíveis não contém segredo', async () => {
    const { CHAVES_LEGIVEIS, CHAVES_GRAVAVEIS } =
      await import(/* @vite-ignore */ '../../../api/_lib/configuracoes.js');
    const todas = [...(CHAVES_LEGIVEIS as string[]), ...(CHAVES_GRAVAVEIS as string[])];
    const suspeitas = todas.filter((k) => /(token|secret|key|password|senha|hash)/i.test(k));
    expect(suspeitas, 'chave sensível entrou na lista permitida').toEqual([]);
  });

  it('a cotação não é gravável pela rota genérica de chaves', async () => {
    const { CHAVES_GRAVAVEIS } =
      await import(/* @vite-ignore */ '../../../api/_lib/configuracoes.js');
    // Gravar só a taxa deixaria o mês convertido pela taxa anterior: a RPC que
    // recalcula precisa rodar na mesma transação, e só a rota dedicada a chama.
    expect(CHAVES_GRAVAVEIS as string[]).not.toContain('dollar_exchange_rate');
  });

  it('a cotação sem credencial não chega à RPC', async () => {
    const handler = await carregar('api/settings/exchange-rate.js');
    const res = fabricarRes();
    await handler(requisicaoAnonima({ rate: 1 }, 'PUT'), res);

    expect(RECUSADO, `respondeu ${res.statusCode}`).toContain(res.statusCode);
    expect(espiao.chamadas.filter((c) => c.metodo === 'rpc'), 'uma função do banco rodou sem identidade')
      .toEqual([]);
  });

  it('só existe UMA RPC alcançável, escrita literalmente no servidor', () => {
    const fonte = ler(join(RAIZ, 'api/_lib/configuracoes.js'));
    const chamadas = [...fonte.matchAll(/\.rpc\(\s*([A-Za-z_$][\w$]*|'[^']*')/g)].map((m) => m[1]);
    expect(chamadas.length, 'nenhuma chamada de RPC encontrada — revisar este teste')
      .toBeGreaterThan(0);
    // Cada chamada usa a constante RPC_TAXA, e ela é um literal.
    for (const alvo of chamadas) {
      expect(alvo, 'RPC escolhida por valor dinâmico').toBe('RPC_TAXA');
    }
    expect(fonte).toContain("const RPC_TAXA = 'rpc_set_dollar_exchange_rate'");
  });
});

describe('CORS — nenhuma rota credenciada responde curinga', () => {
  it('nenhum handler devolve Access-Control-Allow-Origin: *', async () => {
    const rotas = [
      ['api/me.js', 'GET'],
      ['api/users.js', 'POST'],
      ['api/settings.js', 'GET'],
      ['api/settings/exchange-rate.js', 'PUT'],
      ['api/meta-capi/sites.js', 'GET'],
    ] as const;

    for (const [arquivo, metodo] of rotas) {
      const handler = await carregar(arquivo);
      const res = fabricarRes();
      await handler(requisicaoAnonima({}, metodo), res);
      expect(res.headers['access-control-allow-origin'], arquivo).not.toBe('*');
    }
  });

  it('origem de terceiro não recebe permissão nenhuma', async () => {
    const handler = await carregar('api/me.js');
    const res = fabricarRes();
    await handler(requisicaoAnonima(undefined, 'GET'), res);
    // Ou o header não vem, ou vem com a origem permitida — nunca com a do terceiro.
    const eco = res.headers['access-control-allow-origin'];
    expect(eco ?? null, 'a origem de terceiro foi ecoada').not.toBe('https://site-de-terceiro.example');
  });
});
