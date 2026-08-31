# Relatório de entrega — fechamento produtivo de Search

*Branch `sprint/search-production-closure-v1` · base `f45e810` (tag `harness-v3-supervised-local-accepted`)*

## 1. Commits

| SHA | O quê |
|---|---|
| `807e306` | v10_03: a fronteira atômica + o defeito reproduzido e fechado |
| `609ddcf` | `/subir`: recibo antes da chamada; timeout deixa de virar "falhou" |
| `876d090` | tela lê o desfecho gravado; o id da campanha volta a existir |
| `b8aac8f` | ledger ausente vira recusa, não permissão |

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

1. **D1 ampliado** — aplicar v10_01 (+v10_02 opcional) **e v10_03**.
2. **Reenvio depois de `sem_resposta`** — hoje é impossível por construção. Afrouxar é
   mexer numa guarda de segurança; ver `ROLLBACK-…md` §3.
3. **D4 e D10** continuam sendo pré-condição de qualquer lançamento real.

## 7. Limitação confirmada da invariante — a porta que continua aberta

**A garantia "nenhuma mutação sem recibo" vale para a rota HTTP, não para o processo.**

`volc_ads/subir.py:1310-1352` expõe um CLI que chama `subir()` diretamente:

```bash
python -m volc_ads.subir --subir --conta <id> --mcc <id> --motivo "..."
```

Esse caminho **não passa** pelo ledger, pela política do canário, pelo portão de
escopo nem por qualquer recibo. Ele exige a trava de dois fatores (`destravar()` no
código **e** `FORGE_PERMITIR_ESCRITA=1` no ambiente), que é uma barreira real e
deliberada — mas quem tiver shell e a trava aberta cria campanha sem rastro local,
exatamente o objeto que esta sprint existe para eliminar.

O que **já** protege: `--subir` exige `--conta` explícita, então o default
`CONTA_PROVA = 8017851692` (Crédito Up) só vale para `--dry`, que não escreve.

**Não foi corrigido aqui, de propósito.** `volc_ads/` está fora do ownership
declarado em S1 §6, e a correção é uma decisão de produto entre duas opções:
aposentar o caminho de escrita do CLI, ou fazê-lo atravessar o ledger. Expandir
`allowed_paths` no meio da execução era proibido pelo enquadramento da missão.

Consta como pré-condição operacional em `PREFLIGHT-GOOGLE-ADS-CANARIO.md` §2.

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
