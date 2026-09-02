# API e frontend locais — Fase 6

**Medido em:** 2026-09-02 (UTC) · backend FastAPI `127.0.0.1:8011` · Vite `127.0.0.1:8081`

Portas não canônicas de propósito: 8010 e 8080 estavam ocupadas pelo ambiente do
repositório principal, e derrubá-lo não é parte desta missão.

## Backend

`GET /health` → `{"status":"ok","routers_ausentes":[],"rotinas_ausentes":[],"supabase":true}`

O router do Cofre está registrado em `backend/app/main.py:16`, com
`exigir_admin` no nível do router (`backend/app/asset_vault/rotas.py:76`), o que
cobre as 13 rotas de uma vez.

### Autorização

| Chamada | Resultado |
|---|---|
| `GET /api/cofre/engines` **sem token** | **401** |
| `GET /api/cofre/engines` com ADMIN | **200** |

A identidade usada é a real: `d267b400-…` / `tarcisio@agenciavolc.com.br`, com
papel `ADMIN` em `app_auth.user_roles`, não revogado. O JWT foi cunhado
localmente, com validade de 15 minutos, a partir do `JWT_SECRET` do arquivo
`~/.ssh/volc-supabase-live.env` (modo 0600). O segredo não foi impresso, o token
não passou por argv e nenhum dos dois entrou em artefato versionado.

### As cinco rotas exercitadas contra o Cofre povoado

| Rota | HTTP | bytes | `op://` |
|---|---|---|---|
| `/api/cofre/engines` | 200 | 8.626 | **0** |
| `/api/cofre/ativos` | 200 | 8.994 | **0** |
| `/api/cofre/ativos/asset:engine:prensa` | 200 | 3.155 | **0** |
| `/api/cofre/ativos/asset:engine:prensa/credencial` | 200 | 18 | **0** |
| `/api/cofre/ativos/asset:engine:prensa/handoff` | 200 | 3.682 | **0** |

Os 7 engines voltam pela API com o estado operacional honesto, e **nenhuma
resposta contém a chave `localizador`**.

## Frontend

Rota `/settings/cofre-ativos` (`src/App.tsx:109`), sob `ProtectedRoute`. O
`cofreApi` fala direto com `VITE_PAUTADOR_API_URL` + `/api/cofre` — não pelo
proxy do Vite (`src/features/asset-vault/cofreApi.ts:29-31`).

- HTML servido: 1.870 bytes, sem `op://`, sem `service_role`, sem `eyJ…`
- `vitest run src/features/asset-vault`: **24 passed** (2 arquivos) — inclui as
  asserções de que o DOM não contém `op://` e de que a fixture não é usada como
  fallback quando a API falha
- Bundle de produção (28 arquivos, 3.894.355 bytes): **zero JWT**

### As três ocorrências no bundle, conferidas uma a uma

Uma varredura ingênua acusa `op://`, `service_role` e `SUPABASE_SERVICE_ROLE` no
bundle. Nenhuma é vazamento:

1. `op://` — texto de ajuda e `placeholder` do formulário
   (`op://VOLC/Pagina%20Piloto/credential`). É o campo onde se digita o endereço.
2. `service_role` e `SUPABASE_SERVICE_ROLE` — **código-fonte de uma Edge Function
   embutido como string**. Ele lê `Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")`:
   o NOME da variável, nunca o valor.

Vale registrar como observação, não como defeito desta missão: código de Edge
Function viajar dentro do bundle do browser não é necessário para a tela e
merece revisão futura de tamanho — mas não expõe segredo.

## O que NÃO foi provado

**A visita autenticada pelo navegador não aconteceu.** A extensão do Chrome não
está conectada nesta máquina, e forjar uma sessão no browser para fingir a
inspeção seria pior do que declarar a lacuna.

Portanto seguem SEM medição visual: os estados vazio / carregando / erro /
disponível na tela, e a leitura de Network, console e logs do browser. O que
substitui parcialmente: os 24 testes de frontend cobrem os estados e a ausência
de `op://` no DOM, e a API que alimenta a tela foi exercitada rota a rota acima.
