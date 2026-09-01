# Relatório de entrega — fechamento produtivo de Search

*Branch `sprint/search-production-closure-v1` · base `f45e810` (tag `harness-v3-supervised-local-accepted`)*

## 1. Commits

| SHA | O quê |
|---|---|
| `807e306` | v10_03: a fronteira atômica + o defeito reproduzido e fechado |
| `609ddcf` | `/subir`: recibo antes da chamada; timeout deixa de virar "falhou" |
| `876d090` | tela lê o desfecho gravado; o id da campanha volta a existir |
| `b8aac8f` | ledger ausente vira recusa, não permissão |

### Continuação de 31/08/2026 — base `d51db0a`

| SHA | O quê |
|---|---|
| `ff61979` | float derrubava `/subir`; a rota passa a ler `recibo.estado`; uma identidade só; `/reconciliar` como rota |
| `c6b6a86` | a prova de concorrência para de passar quando não houve concorrência |
| `ae10e5a` | a tela distingue recusa de ignorância, e mostra o carimbo |
| `9208188` | correções dos 8 achados da 1ª revisão Codex Sol (o crítico: o carimbo entrava na identidade) |
| `2d39ae2` | **v10_04** — a saída do indeterminado passa a existir de fato |
| `8896353` | P05-T11 continua parcial, com evidência precisa |
| `1f115f6` | correções dos 5 achados da 2ª revisão (o alto: minha própria migration apagava guardas) |
| `b4a42fa` | a evidência registra também o defeito que eu introduzi |

## 2. Arquivos

**Novos:** `supabase/migrations/v10_03_recibo_atomico.sql` (992) ·
`supabase/migrations/v10_03_rollback.sql` (91) · `scripts/provar-ledger-v10-03.sh` (386) ·
`backend/app/trafego/ledger.py` (357) · `backend/tests/test_trafego_ledger.py` (481) ·
`src/lib/trafego/lancamento.ts` (101) · `src/lib/trafego/__tests__/lancamento.test.ts` (122) ·
`docs/closure/search-production-closure-v1/*` (5 documentos)

**Alterados:** `backend/app/routers/trafego.py` (só `subir()` + helpers de fechamento) ·
`backend/app/services/supabase_service.py` (+1 método `rpc()`) ·
`src/components/trafego/Lancamento.tsx` · `src/lib/pautadorApi.ts` (1 assinatura) ·
`src/types/trafego.ts` (+4 tipos) · `supabase/migrations/README.md`

**Não tocados, como declarado no ownership de S1:** `lote.py`, `intencao.py`,
`persistencia.py`, `v10_01/v10_02.sql`, `reconciliacao.py`, `trafego_inventario.py`,
`diagnostico_persistido.py`, `QuadroDoLote.tsx`, `laboratorio/**`.

## 3. Gates — comando, contagem antes e depois

| Gate | Comando | Antes | Depois |
|---|---|---|---|
| Backend | `./scripts/gates-backend.sh` | 1619 passed, 53 skipped | **1642 passed, 53 skipped** |
| Frontend | `npm test` | 959 passed, 3 failed, 8 arquivos com erro | **976 passed, 3 failed, 8 arquivos com erro** |
| Tipos | `npx tsc --noEmit -p tsconfig.app.json` | 76 erros | **76 erros** |
| Build | `npm run build` | verde | **verde** |
| SQL v10 | `./scripts/provar-ciclo-v10.sh` | ciclo verde | ciclo verde |
| SQL v10_03 | `./scripts/provar-ledger-v10-03.sh` | *(não existia)* | **56 provas verdes** |
| Higiene | `git diff --check` | limpo | limpo |

### Gates da continuação de 31/08/2026 (baseline `d51db0a`)

| Gate | Comando | Baseline | Depois |
|---|---|---|---|
| Backend + engine | `backend/.venv/bin/python -m pytest backend/tests volc_ads -q` | 2223 passed, 53 skipped | **2261 passed, 53 skipped** |
| SQL ledger | `bash scripts/provar-ledger-v10-03.sh` | 52 provas | **85 provas, 0 falhas** |
| QG focal | `npx vitest run src/features/work-road` | 22 passed, **1 failed** | **23 passed** |
| Frontend | `npx vitest run` | 1106 passed, 1 falha herdada | **1107 passed, 3 skipped** |
| Tipos | `npx tsc --noEmit -p tsconfig.app.json` | 76 erros | **76 erros** |
| Build | `npm run build` | verde | **verde** |
| CLI aposentado | `pytest volc_ads/testes_subir.py` | 3 passed | **6 passed** |

As 3 falhas e os 8 arquivos com erro de coleta do vitest foram medidos **na árvore limpa,
com `git stash`**, e são idênticos antes e depois: herdados, não tocados por esta entrega.
Nenhum dos 76 erros de tipo está na superfície de lançamento ou diagnóstico.

## 4. As invariantes, e onde cada uma é provada

| Invariante | Prova |
|---|---|
| RPC/ledger atômico | `provar-ledger-v10-03.sh` C |
| segunda chamada com mesma chave não duplica | D |
| mesma chave com payload divergente falha fechado | E |
| erro de banco antes do mutate ⇒ zero chamada Google | `test_trafego_ledger.py::test_recusa_do_ledger_impede_qualquer_chamada_que_muta` |
| ledger ausente ⇒ zero chamada Google | `…::test_ledger_nao_configurado_recusa_a_escrita…` |
| recibo `em_voo` existe antes da fronteira | `…::test_o_recibo_em_voo_e_gravado_antes_da_chamada_que_muta` + C2 |
| timeout gera indeterminado, nunca falhou/retry | `…::test_sem_resposta_vira_indeterminado_e_recusa_reenvio` + I |
| erro respondido ≠ ignorância | `…::test_erro_respondido_pelo_google…` + N |
| reconciliação tardia fecha o mesmo recibo | J |
| approval de outra conta/canal/plano recusada | F/G/H |
| external ID resolve para exatamente um item | K |
| campanha só nasce PAUSED | `…::test_a_campanha_que_sai_para_a_conta_nasce_pausada` |
| frontend preserva ausência/zero/falha | `lancamento.test.ts` (17) |
| render não chama Google Ads | `trafego_diagnostico.py` lê só dados persistidos |
| nenhuma credencial no bundle | zero strings com forma de JWT; `SUPABASE_SERVICE_ROLE_KEY` só como nome, 3×, igual ao baseline |
| contrato Python↔SQL | O — e a prova falha quando um nome é trocado (verificado por mutação) |
| rollback local provado | M |
| corrida real: duas sessões, um recibo | P — duas sessões simultâneas na mesma função; uma despacha, uma é recusada pela guarda, e existe **um** recibo em voo |

## 5. Fronteiras externas — o que continua fechado

| Ação | Estado | Destrava com |
|---|---|---|
| Aplicar migration no Supabase oficial | **NÃO EXECUTADA** | `PREFLIGHT-SUPABASE-OFICIAL.md` |
| Qualquer escrita no Supabase oficial | **NÃO EXECUTADA** | idem |
| `validate_only` real contra Google Ads | **NÃO EXECUTADA** | `PREFLIGHT-GOOGLE-ADS-CANARIO.md` §3.1 |
| Mutate real contra Google Ads | **NÃO EXECUTADA** | idem §3.3, após P1–P6 |
| Tocar a Crédito Up | **NÃO EXECUTADA** | fora de escopo permanente |
| Ativar campanha | **NÃO EXECUTADA** | fora de escopo desta sprint |
| n8n externo | **NÃO EXECUTADA** | D10 |
| `git push` | **NÃO EXECUTADO** | D9 (backup remoto) |
| Deploy | **NÃO EXECUTADO** | — |

## 6. Decisões que sobraram para o dono

1. **D1 ampliado e DECIDIDO em 31/08/2026** — aplicar **v10_01, v10_03 e v10_04**. A
   `v10_02` ficou explicitamente fora da janela: é autogestão T1 e não participa do
   caminho `/subir`.
2. **Reenvio depois de `sem_resposta`** — hoje é impossível por construção. Afrouxar é
   mexer numa guarda de segurança; ver `ROLLBACK-…md` §3.
3. **D4 e D10** continuam sendo pré-condição de qualquer lançamento real.

## 6b. Revisão adversarial — o que ela cobriu, e o que ela não pôde cobrir

Lane usada: **Codex GPT-5.6 Sol / high**, modelo diferente do que escreveu (Claude Opus 5),
como o roteamento exige. Escopo: refutar, não confirmar.

**Declaração de disponibilidade parcial, sem fallback silencioso:**

- **DeepSeek: lane INDISPONÍVEL** nesta máquina (binário ausente). Não foi substituída
  por outro provedor — e não fazia falta, porque o roteamento a restringe a microcorreção
  determinística, que esta sprint não teve.
- **Codex: lane disponível, sandbox limitado.** Ela registrou por escrito que (a) os três
  sub-revisores que tentou abrir falharam com `EPERM` ao criar o lock de credenciais e
  (b) **não conseguiu subir o cluster Postgres** por bloqueio de escrita em `/tmp`. Logo,
  todo achado dela sobre SQL sairia como `[NÃO REPRODUZIDO]`. A suíte Python ela rodou, e
  passou.
- A execução foi **encerrada por mim** depois de ~40 min, com a cobertura de SQL
  reconhecidamente impossível naquele sandbox.

**O que a revisão produziu de real:** um achado confirmado — o caminho de escrita do CLI
em `volc_ads/subir.py`. Eu o reproduzi por leitura direta, aceitei, e ele está na §7 e
como pré-condição P7 do preflight.

**Como as categorias que a lane não pôde executar ficaram cobertas:** por prova
executável minha, no cluster descartável — em particular a categoria de concorrência
(prova P: duas sessões simultâneas, uma despacha, uma é recusada, um recibo em voo) e a
de "prova que passa pelo motivo errado", que corrigi duas vezes durante o trabalho (uma
CHECK de quantidade mascarando a guarda anunciada; e a classe 22 tratada em bloco quando
`22023` e `22P02` significam o oposto).

**O que isso deixa em aberto, honestamente:** uma segunda leitura adversarial por modelo
diferente, com permissão de executar os scripts de prova, ainda não aconteceu. Ela não é
substituível pelo que fiz sozinho.

## 7. A porta paralela do CLI — FECHADA em 31/08/2026

**Era a limitação confirmada desta entrega, e deixou de ser.**

`volc_ads/subir.py` expunha `python -m volc_ads.subir --subir`, que chamava `subir()`
direto: sem ledger, sem política do canário, sem portão de escopo e sem recibo. Uma
campanha criada por ali nasce existindo na conta do Google e não existindo no VOLC O.S. —
a que ninguém consegue reconciliar depois, porque não há chave, item nem recibo para
procurar. As quatro camadas contra a segunda campanha vivem no banco, e o atalho passava
por fora de todas.

A trava de dois fatores era uma barreira real, mas o que ela protegia era uma **condição
operacional que dependia de disciplina humana** — e uma pré-condição que depende de
alguém lembrar não é uma garantia.

**Decisão de produto do dono (31/08/2026): a escrita pelo CLI foi aposentada.**

- `--subir` falha fechado com código de saída **2**;
- a recusa acontece **antes** de `preparar()`, que é quem constrói o cliente do Google e
  roda `validate_only`. Recusar depois dele seria recusar tarde: o processo já teria
  autenticado e falado com a API. A ordem é a regra, e é ela que o teste mede;
- a mensagem aponta a porta certa: criação real é `POST /api/trafego/subir`;
- **`--dry` foi preservado** — ele monta o grafo e roda `validate_only`, não escreve nada,
  e continua sendo a forma certa de conferir um plano pelo terminal;
- a biblioteca interna (`subir()`, `preparar()`, os estados do recibo) permanece: é ela
  que o backend usa. O que saiu foi a porta de linha de comando, não o motor;
- **não** foi criada uma segunda implementação do ledger no CLI. Ele deixou de escrever,
  e ponto — um CLI que virasse cliente da rota seria uma terceira superfície para manter.

**Prova:** `volc_ads/testes_subir.py::prova_cli_subir_aposentado_nao_toca_google_nem_com_trava_aberta`
roda com **`FORGE_PERMITIR_ESCRITA=1`** — a trava ambiental aberta — e derruba o teste se
`preparar`, `mutar`, `validar_mutacoes`, `cliente` ou `subir` forem alcançados. Fechar a
porta só com a trava fechada seria fechá-la exatamente quando ela não precisa estar.

## 8. Divergências registradas, não resolvidas em silêncio

- **Convenção de migration.** O `supabase/` deste repo não tem `config.toml`, e a
  convenção viva é `vNN_MM_nome.sql` + `_rollback.sql`, não o `<timestamp>_nome.sql` da
  CLI. A v10_03 segue a do repositório; trocar de convenção no meio de uma série quebraria
  a ordem topológica documentada no README.
- **P05-T07** descreve como faltante uma rota de diagnóstico que existe e está montada
  (`trafego_diagnostico.py`; `main.py:178`; `App.tsx:131`). Correção proposta no
  encerramento.
- **"Nenhuma chamada Google antes do recibo"** foi interpretado como *nenhuma chamada que
  MUTA*. A leitura de idempotência continua antes do recibo, e a razão está no comentário
  em `trafego.py` e em `ledger.py`: abrir o recibo antes dela deixaria um `em_voo` órfão a
  cada falha transitória de leitura, e a camada 4 passaria a bloquear o item até alguém
  reconciliar uma chamada que nunca saiu.
