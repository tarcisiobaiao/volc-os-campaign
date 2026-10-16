# Bia V1: handoff para o integrador

Branch `feat/bia-hermes-volc-v1`, worktree `/Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/bia-hermes-volc-v1`, base `a54a77e2` (main).

Esta branch **não** editou `volc-os-workbook/ROADMAP-VIVO.json`, `docs/volc-os-graph/curadoria-operacional.json`, nem o grafo. O grafo estava **defasado** no início da missão (`--check`: `current: false`, digest mudou) e não foi regenerado. Tudo abaixo é delta para o integrador aplicar **uma vez, depois do merge**.

## 1. Roadmap (`ROADMAP-VIVO.json`)

| Tarefa | Estado hoje | Estado proposto | Prova a registrar | Lacuna |
|---|---|---|---|---|
| P09-T04 "Integrar Bia em modo leitura e sugestão" | todo | **partial** (provada em ambiente local; falta FastAPI em produção) | rotas `/api/agent/*` no FastAPI com flag + ADMIN; widget no Layout; ledger v27_01 provado no lab (66/66, garantido) e pelo protocolo; 85 testes herméticos backend + 4 adaptador↔SQL real; 21 front + bundle real sem Hermes | **prova real feita em 15/10/2026** (provas/PROVA-REAL-20261015.md): mesma Bia do Telegram (profile `default`), sessão web separada, 0 ferramentas, 0 mutação; falta o FastAPI implantado fora do Mac (ADR-RUNTIME) para uso além do operador local |
| P09-T06 "Provar um gateway agêntico Google Ads somente leitura" | todo | **partial** | catálogo tipado só leitura; `volc_get_campaign_context` sobre o snapshot do inventário e o fato canônico campanha-dia (ledger antes do fato), com receita e lucro nulos e frescor obrigatório; prova estática de zero caminho de mutação | sem leitura contra o Supabase real; o Hermes não consome a capacidade como ferramenta (decisão da V1: injeção pelo servidor) |
| P09-T05 "Permitir confirmação humana contextual" | todo | todo | interfaces `PropostaDeAcao`/`Aprovacao`/`Recibo`/`PlanoDeExecucao` declaradas e desabilitadas | tudo |

Não promover nada a `done`: os critérios de aceite exigem a prova real (RUNBOOK-IMPLANTACAO, CP4).

## 2. Curadoria (`curadoria-operacional.json`), só se o merge acontecer

| Nó | Campo | De → Para |
|---|---|---|
| `cap_bia_copilot` | `state` | `todo` → `partial` |
| `cap_bia_copilot` | `evidence` | acrescentar: "15/10/2026: V1 no FastAPI (/api/agent/*, ADMIN, flag) e widget no Layout; v27_01 aplicada; mesma Bia do Telegram (profile default, sessão web separada, superfície api_server sem ferramentas). Prova real local: inferência, continuidade, reload, isolamento, 0 ferramentas, 0 mutação." |
| `system:hermes` | `evidence` | **corrigir**: "v0.18.0 (2026.7.1), único profile default (Telegram, hermes-gateway.service, root). Até 15/10/2026 nenhuma API Server escutava; desde 16/10 00:40Z, API Server do default em 127.0.0.1:8642 com platform_toolsets.api_server=[] (zero ferramentas), acessada só por túnel SSH pelo backend VOLC." |
| `concept:ads_agent_gateway` | `state` | `todo` → `partial`; evidência: o catálogo só leitura e a capacidade `volc_get_campaign_context` |
| novo `doc:adr-bia-hermes-v1` | — | `documenta: cap_bia_copilot`, path `docs/architecture/ADR-BIA-HERMES-VOLC-V1.md` |

Não colocar na curadoria: IP, chave, id de sessão nem UUID de usuário.

## 3. Grafo

Depois do merge e da curadoria:

```bash
python3 scripts/atualizar_grafo_volc_os.py
python3 scripts/atualizar_grafo_volc_os.py --check
```

Nós esperados na camada técnica: `backend/app/agente_bia/*`, `src/features/bia/*`, `supabase/migrations/v27_01_*`.

## 4. Conflitos esperados com o main atual

| Arquivo | Natureza | Como resolver |
|---|---|---|
| `backend/app/main.py` | bloco novo depois de `publicacao_organica` (router + `add_middleware(CorsExatoDaBia)`) | manter o bloco e o `add_middleware` **depois** do CORSMiddleware global (o último adicionado é o mais externo) |
| `backend/app/config.py` | 8 campos `bia_*` antes de "Behaviour" | só somar |
| `src/lib/secureApi.ts` | `export class`, método `requisitar`, parser de `detail` | só somar; o comportamento antigo não muda |
| `src/components/layout/Layout.tsx` | import da flag + `React.lazy` + bloco antes do fechamento | só somar |
| `.env.example`, `backend/.env.example` | blocos novos sem valor | só somar |
| **migrations** | a branch `origin/mission/w15-meta-g0y5xz` usa `v26_01_meta_insight_latest_completa.sql` **e `v26_01_rollback.sql`** | por isso esta branch usa **v27_01**. Se outra frente pegar v27 antes, renumerar e recalcular os sha no RUNBOOK |
| checkout oficial | em 15/10 havia mudanças staged de outra sessão (`trafego.py`, `pautadorApi.ts`, `CampanhaCanonPage.tsx`, recomendação em sombra) | nenhum desses arquivos foi tocado aqui |

## 5. Medições de testes (para comparar conjuntos, não contagens)

- **Backend, suíte inteira** (`/usr/local/bin/python3`, FastAPI 0.135.1): branch 37 falhas, base `a54a77e2` 38 falhas, com o mesmo conjunto exceto três instabilidades:
  - `test_meta_copy_context_post[pack-revision]` falha só na suíte inteira e passa 3/3 isolado nas duas árvores;
  - `test_gads_workflows_n8n::test_gate_de_agenda_unica` falha só na base;
  - `test_schema_perfil_meta::test_sql_nao_rastreado…` falha só na cópia sem `.git`.

  `test_conversao_offline_w14.py` não coleta por falta de `hypothesis` no interpretador.
- **Front, suíte inteira:** 26 arquivos e 16 testes falham, **idênticos** aos da base limpa.
- **tsc** (`-p tsconfig.app.json`): 76 erros, todos herdados (o número documentado no CLAUDE.md); zero nos arquivos tocados. ESLint limpo nos arquivos tocados.
- Ambiente: o venv `backend/.venv` do checkout oficial está em arquivos `dataless` do iCloud e trava o import. O `node_modules` desta worktree é symlink para uma instalação `npm ci` do mesmo lockfile fora do Desktop (scratchpad).

## 6. O que continua pendente (fora desta branch)

1. ~~CP1~~, ~~CP2~~, ~~CP3/CP4~~: feitos em 15/10/2026 (ver provas/).
2. Implantar o FastAPI fora do Mac (ADR-RUNTIME), com túnel persistente ou Tailscale Serve até o Hermes; até lá o widget só funciona no ambiente do operador.
3. Migration v27_02 para a reconciliação gravar `hermes_usou_ferramenta` (R8).
4. A v20_02 (linha de base do ledger) continua NÃO aplicada; a âncora dela (695e913a…) já não bate com produção (58e2c430… antes da v27, dfe4bc0c… depois) e precisa ser remedida.
4. Endurecimento do túnel (chave SSH dedicada com `permitopen`).
5. Fase 2: expor o catálogo ao Hermes como MCP, com token por execução, e `registrar_proposta`.

## 6.1 Conflito novo a observar

- `origin/mission/w15-meta-g0y5xz` usa a `v26_01_*`; esta branch usa a v27_01, **já aplicada em produção**. Quem integrar a w15 depois deve conferir a ordem no ledger `volc_ops`, onde só a v27_01 está registrada.

## 7. Nota de secret scan

O `gitleaks` (sobre `a54a77e2..HEAD` e sobre `docs/bia-hermes/provas`) só acusou um JWT **sintético** de teste (`sub` fictício, assinatura "assinatura-falsa"), que estava literal no commit `c84eaea1`. No commit de fechamento ele passou a ser montado em runtime. O histórico não foi reescrito (regra da missão). Não é credencial.
