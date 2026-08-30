import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';

// Load environment variables from .env.server
dotenv.config({ path: '.env.server' });

const app = express();
const PORT = process.env.SERVER_PORT || 3001;

// Middleware - CORS with flexible origins for development
const allowedOrigins = process.env.ALLOWED_ORIGINS?.split(',') || [
  'http://localhost:5173',
  'http://localhost:8080',
  'http://localhost:3000'
];

app.use(cors({
  origin: (origin, callback) => {
    // Allow requests with no origin (like mobile apps, curl, Postman)
    if (!origin) return callback(null, true);

    // Check if origin is allowed
    if (allowedOrigins.includes(origin)) {
      callback(null, true);
    } else {
      // In development: allow localhost + rede local (192.168.x.x, 10.x.x.x)
      if (process.env.NODE_ENV !== 'production') {
        const isLocalhost = origin.startsWith('http://localhost:');
        const isLocalNetwork = /^https?:\/\/(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)/.test(origin);
        if (isLocalhost || isLocalNetwork) {
          return callback(null, true);
        }
      }
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true
}));
app.use(express.json());

// Falha rápida de configuração. O servidor NÃO sobe sem credencial: um dev
// server que sobe pela metade responde 500 em tudo e faz perder a tarde
// procurando o erro no lugar errado.
//
// O client em si NÃO é criado aqui. Quem instancia a `service_role` é
// `api/_lib/identidade.js`, sob demanda e uma vez só — o mesmo módulo que a
// Vercel usa. Um client de escopo de módulo aqui seria a segunda cópia da
// credencial no processo, útil para ninguém e fácil de reusar sem portão.
if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
  console.error('❌ SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env.server');
  process.exit(1);
}

// Health check endpoint (root + /api para compatibilidade com Vercel)
app.get('/health', (req, res) => {
  res.json({ status: 'ok', message: 'Server is running' });
});
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', message: 'Server is running' });
});

// =====================================================================
// Rotas nomeadas — espelho EXATO das serverless da Vercel
//
// Cada rota abaixo importa a MESMA `despachar()` que o arquivo em `api/`
// importa, e é fabricada pelo MESMO `criarHandlerExpress` de `api/_lib/host.js`.
// Não há "a versão do dev": a regra existe uma vez só, e o host apenas adapta
// req/res. Se alguém mudar o portão, muda nos dois ambientes junto.
//
// ---------------------------------------------------------------------------
// O QUE HAVIA AQUI ANTES (removido em 24/08/2026)
// ---------------------------------------------------------------------------
//   POST /api/users/query      -> select('*') em public.users por e-mail do corpo
//   POST /api/users/create     -> auth.admin.createUser com role do corpo
//   POST /api/supabase/query   -> QUALQUER tabela, service_role, sem auth
//   POST /api/supabase/insert  -> QUALQUER tabela, service_role, sem auth
//   POST /api/supabase/update  -> QUALQUER tabela, service_role, sem auth
//   POST /api/supabase/delete  -> QUALQUER tabela, service_role, sem auth
//   POST /api/supabase/rpc     -> QUALQUER funcao do banco, service_role, sem auth
//
// Nenhuma delas exigia identidade, e todas respondiam `Access-Control-Allow-
// Origin: *`. Como `service_role` ignora RLS, esses sete endpoints juntos eram
// um cliente Postgres aberto na internet. `/api/supabase/delete` existia SÓ
// aqui, sem par na Vercel — sintoma exato de por que os dois hosts agora
// compartilham a regra em vez de reimplementá-la.
//
// `insert` e `delete` foram removidos sem substituto porque a varredura do
// frontend não achou nenhum consumidor: `secureApi.insert()` e
// `secureApi.delete()` nunca eram chamados. Reintroduzir uma escrita genérica
// "por precaucao" seria reabrir a superfície para um uso que não existe.
//
// Substitutos, com portão e sem identificador de banco vindo da requisição:
//   GET  /api/me                       -> perfil de quem pede (autenticado)
//   POST /api/users                    -> cria usuário (ADMIN)
//   GET  /api/settings                 -> chaves legíveis (autenticado)
//   PUT  /api/settings                 -> chaves graváveis (ADMIN)
//   PUT  /api/settings/exchange-rate   -> cotação + recálculo do mês (ADMIN)
// =====================================================================

app.get('/api/me', criarHandlerExpress(despacharPerfil, { metodos: 'GET', nome: 'me' }));

app.post('/api/users', criarHandlerExpress(despacharUsuarios, { metodos: 'POST', nome: 'users' }));

const handlerConfiguracoes = criarHandlerExpress(
  (entrada) => despacharConfiguracoes({ ...entrada, recurso: 'settings' }),
  { metodos: 'GET,PUT', nome: 'settings' }
);
app.get('/api/settings', handlerConfiguracoes);
app.put('/api/settings', handlerConfiguracoes);

app.put(
  '/api/settings/exchange-rate',
  criarHandlerExpress(
    (entrada) => despacharConfiguracoes({ ...entrada, recurso: 'exchange-rate' }),
    { metodos: 'PUT', nome: 'settings/exchange-rate' }
  )
);

// =====================================================================
// Meta CAPI — wizard multi-tenant (/api/meta-capi/sites)
//
// Espelho EXATO da serverless `api/meta-capi/sites.js` da Vercel: as duas
// importam a mesma `dispatch()` de `api/_lib/metaCapiSites.js`, então dev e
// produção não podem divergir. Aqui só adaptamos req/res do Express.
//
// Estas rotas exigem `Authorization: Bearer <access_token>` e role ADMIN,
// como todas as outras deste arquivo desde 24/08/2026. Foram as PRIMEIRAS a
// exigir — enquanto os proxies /api/supabase/* aceitavam qualquer tabela sem
// autenticação, era por isso que o token da Meta era gravado cifrado e não
// passava por eles. Os proxies morreram; a cifra fica, porque defesa em
// profundidade não se desmonta quando uma camada melhora.
//
// Os imports ficam no fim de propósito: declarações `import` são içadas para o
// topo do módulo pelo próprio ESM, então isto não altera nada acima. O client
// supabase dentro dos libs é criado sob demanda, depois do dotenv.config().
// =====================================================================
import { dispatch as metaCapiDispatch } from '../api/_lib/metaCapiSites.js';
import { criarHandlerExpress } from '../api/_lib/host.js';
import { despacharPerfil } from '../api/_lib/perfil.js';
import { despacharUsuarios } from '../api/_lib/usuarios.js';
import { despacharConfiguracoes } from '../api/_lib/configuracoes.js';

/**
 * Adapta uma rota Express para a `dispatch()` compartilhada.
 * @param {(req: import('express').Request) => any} pickId de onde tirar o id
 */
function metaCapiHandler(pickId) {
  return async (req, res) => {
    try {
      const result = await metaCapiDispatch({
        method: req.method,
        query: req.query || {},
        body: req.body || {},
        authorization: req.headers.authorization,
        id: pickId ? pickId(req) : undefined,
      });

      res.set('Cache-Control', 'no-store');

      if (result.error) {
        const payload = { error: result.error };
        if (result.fields) payload.fields = result.fields;
        return res.status(result.status).json(payload);
      }

      return res.status(result.status).json(result.data);
    } catch (error) {
      // Nunca logar o corpo: o POST carrega `capi_token` em texto puro.
      console.error('[meta-capi] erro não tratado:', error?.message);
      return res.status(500).json({ error: 'Erro interno ao processar a requisição.' });
    }
  };
}

// Forma canônica (id por query/body) — idêntica à da Vercel, é a que o
// frontend deve usar para funcionar nos dois ambientes.
app.get('/api/meta-capi/sites', metaCapiHandler());
app.post('/api/meta-capi/sites', metaCapiHandler());
app.put('/api/meta-capi/sites', metaCapiHandler());
app.patch('/api/meta-capi/sites', metaCapiHandler());
app.delete('/api/meta-capi/sites', metaCapiHandler());

// Forma REST do contrato (§5). Só existe no dev: na Vercel `/sites/:id/check`
// não casa com nenhum arquivo do filesystem router.
app.patch('/api/meta-capi/sites/:id/check', metaCapiHandler((req) => req.params.id));
app.delete('/api/meta-capi/sites/:id', metaCapiHandler((req) => req.params.id));

// Start server
app.listen(PORT, () => {
  console.log(`✅ Secure API server running on port ${PORT}`);
  console.log(`🔒 Protected endpoints available at http://localhost:${PORT}/api/*`);
});
