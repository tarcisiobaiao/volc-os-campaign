# Bia V1 no VOLC O.S. (P09-T04 / P09-T06)

**Estado (15/10/2026): IMPLEMENTADO E PROVADO no ambiente local do operador.** As migrations v20_01 e v27_01 estão aplicadas no Supabase oficial. A superfície API do profile `default` do Hermes está ligada (loopback, sem ferramentas). A prova real ponta a ponta está em [provas/PROVA-REAL-20261015.md](provas/PROVA-REAL-20261015.md). O FastAPI não está em produção: o widget funciona onde o FastAPI roda, hoje o Mac do operador.

Caminho: navegador (sessão Supabase, ADMIN) → FastAPI `/api/agent/*` → ledger `agente_bia` (Supabase oficial, RPC nomeada) → túnel SSH local → Hermes v0.18.0, **profile `default`** (a mesma Bia do Telegram), sessão web própria, superfície `api_server` sem ferramentas. Contexto VOLC só leitura (`volc_get_campaign_context`), invocado pelo servidor e injetado como dado.

| Documento | Para quê |
|---|---|
| [ADR](../architecture/ADR-BIA-HERMES-VOLC-V1.md) | decisão de topologia, persistência e Gateway; evolução Hermes → Gateway → Codex → execution plane |
| [THREAT-MODEL.md](THREAT-MODEL.md) | ameaças, mitigações e a prova de cada uma |
| [CONTRATO-ROTAS.md](CONTRATO-ROTAS.md) | `/api/agent/*`: portões, códigos, recibo, estados |
| [CATALOGO-TOOLS.md](CATALOGO-TOOLS.md) | capacidades do VOLC Agent Gateway |
| [RUNBOOK-IMPLANTACAO.md](RUNBOOK-IMPLANTACAO.md) | checkpoints CP1 (banco), CP2 (Hermes), CP3 (túnel), CP4 (prova real) |
| [RUNBOOK-ROLLBACK-ROTACAO.md](RUNBOOK-ROLLBACK-ROTACAO.md) | desligar, reverter, rotacionar, reter |
| [HANDOFF-INTEGRADOR.md](HANDOFF-INTEGRADOR.md) | o que o integrador aplica em roadmap, curadoria e grafo depois do merge |
| `provas/PROVA-REAL-20261015.md` | recibo da prova real (gates, roteiro, defeitos achados e corrigidos) |
| `provas/` | recibos: suíte do lab v27_01 (66/66, modo garantido, `producao_acessada: false`) e protocolo oficial em banco descartável (aplicar, rollback recusado com dado, reverter) |

## Código

| Camada | Onde |
|---|---|
| Migration candidata | `supabase/migrations/v27_01_agente_bia.sql` (+ `v27_01_rollback.sql`), suíte `tools/freedom-lab/db/suites/v27_bia.sh` |
| Backend | `backend/app/agente_bia/`, registrado em `backend/app/main.py`; flags em `backend/app/config.py` |
| Front | `src/features/bia/`, montado (lazy, com flag) em `src/components/layout/Layout.tsx`; cliente via `src/lib/secureApi.ts` |
| Hermes (checkpoint) | `deploy/hermes-default-api/api_default.py` (preflight, ensaio, aplicar com rollback automático, verificar, reverter) |
| Prova real | `scripts/bia_prova_real.py` |

## Flags

| Variável | Onde | Padrão |
|---|---|---|
| `VITE_BIA_ENABLED` | front, só visibilidade | `false` |
| `BIA_ENABLED` | backend; só `"1"` abre | vazio (404) |
| `BIA_HERMES_BASE_URL` / `BIA_HERMES_API_KEY` | backend, segredo | vazio (envio 503) |
| `BIA_ALLOWED_ORIGINS` | backend; origens exatas | vazio |
| `BIA_HERMES_TIMEOUT_S` / `BIA_LIMITE_POR_MINUTO` / `BIA_MAX_CARACTERES` | backend | 120 / 6 / 4000 |
