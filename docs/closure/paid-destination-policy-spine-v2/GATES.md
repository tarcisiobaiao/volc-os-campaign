# GATES — o que foi medido, com o comando que produziu o número

Um número sem o comando que o produziu não é evidência. Cada linha abaixo tem o
comando exato e a saída real.

Base: `origin/volc-os-v2` @ `34dc7b41bce901bd8bebfdec0a01e293678cbf08`
Branch: `sprint/paid-destination-policy-spine-v2`
Worktree: `/private/tmp/volc-paid-destination-policy-spine-v2`

---

## 1 · Suíte do backend

```bash
cd backend && PYTHONPATH=<raiz> <backend/.venv/bin/python> -m pytest tests/ -q -p no:randomly
```

| | resultado |
|---|---|
| **base** `34dc7b4` | `3064 passed, 112 skipped` |
| **HEAD** | `3188 passed, 112 skipped` |
| delta | **+124 provas, zero falhas novas** |

O interpretador é `backend/.venv/bin/python` — é o único com `fastapi`, `httpx`
**e** `google-ads`. `scripts/gates-backend.sh` documenta por que a escolha do
interpretador muda o resultado em 28 testes, e por que rodar com o errado produz
"falhas herdadas" que não existem.

## 2 · Suíte do motor

```bash
cd funnelforge-migracao/engine && .venv/bin/python -m pytest tests/ -q -p no:randomly
```

| | resultado |
|---|---|
| **base** `34dc7b4` | `726 passed` |
| **HEAD** | `748 passed` |
| delta | **+22 provas, zero falhas novas** |

⚠️ **O venv do motor não existia em lugar nenhum desta máquina** quando a sprint
começou. `backend/app/redator/worker._executavel()` documenta o comando de
criação, e ele nunca havia sido rodado aqui: a suíte do motor não era executável
neste ambiente. Foi criado com o comando que o próprio `worker.py` prescreve
(`python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`). Não é harness
novo — é o ambiente documentado, finalmente montado.

## 3 · TypeScript

```bash
npx tsc --noEmit -p tsconfig.app.json 2>&1 | grep -c "error TS"
```

| | erros |
|---|---|
| **base** | 76 |
| **HEAD** | 76 |
| delta | **zero** |

Os 76 são herdados do webgo e estão nomeados em `CLAUDE.md`
(`supabaseDataService.ts` 31, `ProjectDashboard.tsx` 12, `AddOpportunityModal.tsx` 8…).
Nenhum é desta sprint.

⚠️ `npx tsc --noEmit` **sem** `-p tsconfig.app.json` roda sobre zero arquivos e
sai 0 — um gate que sempre passa. O `-p` não é detalhe.

## 4 · Vitest

```bash
npx vitest run
```

| | resultado |
|---|---|
| **base** | `7 arquivos falhando · 2 testes falhando · 1282 passando` |
| **HEAD** | `7 arquivos falhando · 2 testes falhando · 1313 passando` |
| delta | **+31 provas, zero falhas novas** |

Os sete arquivos que falham, nomeados:

- `src/components/trafego/inventario/__tests__/` — **cinco**, do Terminal 1
- `src/components/trafego/hub/__tests__/u0-hub-multicanal.test.tsx` — Terminal 1
- `src/components/settings/meta-capi/__tests__/wizard-smoke.test.tsx` — Meta CAPI, sem relação

**Nenhum é desta sprint**, e nenhum está no ownership dela. A baseline do vitest
não estava verde antes e continua não estando; o que esta sprint garante é
**delta zero**.

## 5 · Zero mutação no Google Ads

```bash
PYTHONPATH=. <python> scripts/gate_sem_mutacao_google.py
```

```
ok · 1/3 FORGE_PERMITIR_ESCRITA não está armada
ok · 2/3 a trava de escrita está fechada
ok · 3/3 as 5 contraprovas focais da rota passaram, com sentinela no executor
         e conferência de ordem
```

O próprio gate declara o limite da afirmação, e ele é repetido aqui sem
suavização:

> na rota produtiva testada, nenhuma mutação foi chamada sem recibo `em_voo`
> persistido antes. Este gate **NÃO** inspeciona rede, **NÃO** contém processos
> e **NÃO** fala sobre caminhos fora da rota testada (o CLI de `volc_ads`, por
> exemplo).

## 6 · Autoridade do Supabase

```bash
python3 scripts/verificar_autoridade_supabase.py
→ ✓ Supabase oficial: https://database.agenciavolc.com.br
```

## 7 · Paridade da matriz de política

```bash
PYTHONPATH=backend <python> -c "from app.landing_policy.contrato import codigos_conhecidos, carregar_fontes; ..."
→ codigos: 42 · fontes: 42 · sem fonte: [] · fonte sem codigo: []
```

Toda regra que o portão pode emitir tem entrada na matriz, com URL de host
oficial do Google, e nenhuma entrada da matriz descreve regra que não existe —
a matriz não mente sobre cobertura nos dois sentidos. Travado por
`test_landing_policy_portao.py::test_todo_codigo_conhecido_tem_fonte_oficial_do_google`
e `::test_a_matriz_nao_carrega_regra_que_o_portao_nao_emite`.

## 8 · Delta de veredito sobre a evidência preservada

```bash
PYTHONPATH=backend <python> scripts/auditar_landing_policy.py --evidencia --saida <fora do pacote>
```

Sobre os **mesmos bytes** de
`docs/closure/hermes-redator-google-ads-policy-incident-v1/evidence-public/`,
sem uma única requisição de rede:

| | bloqueios | prontos |
|---|---:|---:|
| contrato v1 | 19 | 0 |
| contrato v2 | **34** | 0 |
| delta | **+15, nenhum perdido** | — |

Detalhe por destino em `GATE-RECEIPTS-V2.json`.

## 9 · Auditoria de ownership

```bash
git status --porcelain -- <cada caminho proibido>
```

Confirmado intacto, um a um: `volc_ads/inteligencia_google/`,
`backend/app/trafego/diagnostico_persistido.py`, `.../alertas.py`,
`.../inventario.py`, `backend/app/routers/trafego_diagnostico.py`,
`.../trafego_inventario.py`, `src/components/trafego/diagnostico/`,
`src/components/trafego/inventario/`, `src/lib/diagnostico/`,
`src/types/diagnostico.ts`, `volc-os-workbook/`, `docs/volc-os-graph/`,
`supabase/migrations/`, `src/sql/`.

**Zero migration. Zero coluna nova. Zero tabela nova.** O registro de aprovação
reusa `pautador_funnel_runs.paginas_publicadas jsonb`, que já existe e já é o
contrato declarado com o módulo de campanha.

## 10 · Contenção externa

Nenhuma chamada externa foi executada por esta sprint, com uma exceção
declarada e autorizada:

| ato | executado? |
|---|---|
| mutate no Google Ads | **não** |
| ativação ou retomada de campanha | **não** |
| recurso/apelação ao Google | **não** |
| escrita ou publicação no WordPress | **não** |
| escrita ou migração no Supabase | **não** |
| deploy | **não** |
| envio de formulário | **não** |
| acesso autenticado a qualquer serviço | **não** |
| **leitura pública GET** | **sim — 4 requisições** |

As quatro: dois destinos `/r/` × dois user-agents, com pausa de 3 s, sem cookie,
sem autenticação, sem formulário. Autorizadas pela seção 12 do briefing e por
`AUTORIZACAO-EXTERNA.md`. Resultado em `LIVE-READ-SUMMARY.json`.

Os testes são herméticos: a barreira 3 faz `monkeypatch` de
`fetch_public_https_chain` e tem fixture `_rede_bloqueada` autouse; o portão do
motor tem `test_gate_da_lp_e_hermetico`.

---

## O que estes gates NÃO provam

- Que a conta do Google está segura. Ela não está — a suspensão não foi tratada
  por esta sprint, e a notificação literal continua não lida.
- Que qualquer página foi aprovada pelo Google. O portão lê HTML; ele não lê a
  decisão do revisor.
- Que o caminho que efetivamente causou o incidente está coberto. `canario.exigir`
  restringe a criação a um `customer_id`, e a conta suspensa mostrava campanhas
  que a tabela local não registrava — o que **sugere um caminho de criação fora
  de `/subir`**. Não foi possível determinar isso lendo código. Ver
  `REMAINING-RISKS.md` §5.
- Que a invocação do motor por terminal está barrada. Ela não está, por
  construção — ver `REMAINING-RISKS.md` §1.1.
