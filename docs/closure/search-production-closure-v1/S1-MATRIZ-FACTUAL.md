# S1 · Matriz factual — o que separa `/subir` do fechamento produtivo

*Sprint `sprint/search-production-closure-v1` · base `f45e810` · 2026-08-31*
*Missão read-only: nenhum arquivo de produto foi editado para produzir este documento.*

## 1. Baselines medidos (comando + contagem, nunca "verde")

| Gate | Comando | Resultado |
|---|---|---|
| Focal backend | `pytest tests/test_trafego_diagnostico_v12.py …_rota.py …_canario.py …_canal_de_criacao.py test_intencao.py test_intencao_regras_canonicas.py -q -p no:randomly` | **165 passed** |
| Suíte backend | `./scripts/gates-backend.sh` | **1619 passed, 53 skipped** |
| Tipos frontend | `npx tsc --noEmit -p tsconfig.app.json` | **76 erros** (baseline herdado do webgo; **zero** na superfície trafego/diagnóstico) |
| Ciclo SQL v10 | `./scripts/provar-ciclo-v10.sh` | **ciclo completo verde** (aplicar → reverter → reaplicar) |

⚠️ O worktree não tinha `backend/.venv`; ele foi ligado por symlink ao venv do repositório
principal (único com `google-ads`) e excluído localmente via `.git/info/exclude`. Sem isso
o gate oficial sai com `exit 2` — é o `FileNotFoundError` que travou os supervisores de 29/08.

## 2. Matriz: já existe / parcial / falta / contradiz

| Elo da transação produtiva | Estado | Prova |
|---|---|---|
| Schema do ledger (19 tabelas, máquinas de estado, idempotência, RLS+FORCE, zero policies, DELETE para ninguém) | **JÁ EXISTE** | `v10_01_intencao_e_lote.sql`, `v10_02_autogestao.sql`; ciclo verde |
| `trafego_recibo` com `desfecho ∈ (em_voo, sucesso, erro, sem_resposta)` | **JÁ EXISTE** | v10_01:791-860 |
| `trafego_lote_item.id_externo` + `id_externo_lido_em` + `volc_campaign_id` | **JÁ EXISTE** | v10_01:539-545, CHECK "id externo sem carimbo" |
| Chave de idempotência derivada do conteúdo | **JÁ EXISTE** | `lote.py:216`; `test_lote_idempotencia.py` (21 testes) |
| Máquina de estados em Python espelhando o SQL | **JÁ EXISTE** | `lote.py:69-177`; `test_lote.py` (31 testes) |
| Modelo de intenção validado | **JÁ EXISTE** | `intencao.py:119-172`; 59 testes |
| Aprovação humana como pré-condição de execução do lote | **JÁ EXISTE** (no SQL) | gatilho `trafego_lote_estado_valido`, v10_01:1170 |
| Frontend: timeout → `indeterminado`, **sem** CTA de reenvio | **JÁ EXISTE** | `Lancamento.tsx:165-169`, 390-397; `indeterminado` fora da lista de estados com "Voltar e ajustar" (`:400`) |
| Frontend: ausência ≠ zero medido | **JÁ EXISTE** | `NovaCampanhaPage.tsx:299-309`; `useDiagnosticoDeEntrega.ts:34-60` (404/501 ≠ falha) |
| Tipos TS de ledger (`Recibo`, `Aprovacao`, `ItemDoLote.recibo_em_voo`) | **JÁ EXISTE, ÓRFÃO** | `src/types/diagnostico.ts:246-444`; consumidos só por `QuadroDoLote.tsx`, sem rota |
| Rota de diagnóstico persistido | **JÁ EXISTE** | `trafego_diagnostico.py`; montada em `main.py:178`; rota React em `App.tsx:131` |
| Writer Python do ledger v10 | **FALTA (nada)** | `lote.py`/`intencao.py` têm zero I/O e **zero importadores** em `backend/app/` |
| Persistência de intenção/blueprint/lote/item | **FALTA** | `persistencia.py` só escreve as 6 tabelas do inventário v9, com guarda explícita (`:1109`) |
| Recibo `em_voo` **antes** do mutate | **FALTA** | `/subir` chama `sb.subir` em `trafego.py:2344`; primeira escrita local só em `:2394` |
| Aprovação humana persistida | **FALTA** | `identidade.sub` só entra no JSON de resposta (`trafego.py:2367-2375`), nunca no banco |
| Reconciliação do resultado remoto | **PARCIAL** | só pré-checagem GAQL *antes* (`canario.campanhas_com_marca/destino`); nada relê *depois* |
| ID externo → identidade interna | **PARCIAL e frágil** | `_registrar_campanha` grava em `campaigns` (legado), **best-effort**: falha vira aviso (`:2446`) e **não tem nenhum teste** |
| Contrato TS de `/subir` | **CONTRADIZ** | `pautadorApi.ts:867` devolve `Record<string, unknown>` enquanto `Recibo` tipado existe e é ignorado |
| Roadmap P05-T07 | **CONTRADIZ** | descrição diz faltar rota de diagnóstico que existe desde a v12 |
| v10_01/v10_02 aplicadas no Supabase oficial | **NÃO — e não autorizado nesta sessão** | `README.md:510` "NENHUMA APLICADA" |

## 3. O defeito que a investigação provou (reproduzido, não inferido)

As três camadas de defesa contra "timeout mas criou" vivem **todas** dentro de
`IF NEW.estado IS DISTINCT FROM OLD.estado` no gatilho `trafego_item_estado_valido`
(v10_01:1321). Elas guardam `-> falhou` e `indeterminado -> criando`.

**Abrir um recibo — o ato que precede a chamada ao Google — não passa por gatilho nenhum.**

Reprodução em Postgres descartável (v9_01..v9_04 + v10_01 + v10_02 aplicadas):

```
item em `criando`, recibo tentativa=1 `em_voo` (chamada 1 nunca respondeu)
INSERT trafego_recibo tentativa=2 'em_voo'   → ACEITO
→ recibos em voo simultâneos para o mesmo item: 2
```

Consequência operacional: duas chamadas de criação podem estar em voo para o **mesmo
plano, na mesma conta**. O índice `(idempotency_key, operacao) WHERE desfecho='sucesso'`
impede registrar dois sucessos — ou seja, se as duas criarem, **a segunda campanha fica
invisível para o sistema**, disputando o mesmo leilão. O dano não é apenas duplicar: é
duplicar e perder o rastro da duplicata.

Isso é exatamente a falha que o `trafego_recibo` foi escrito para fechar (v10_01:773-790),
e a guarda está ausente na única fronteira que importa.

## 4. Decisão A vs B — e por que a prova decide

- **(A) várias chamadas PostgREST independentes** — cada requisição é uma transação
  própria. A verificação "existe recibo em aberto?" e o `INSERT` do novo recibo ficam em
  transações diferentes, sem cadeado entre elas: uma janela TOCTOU que nenhuma disciplina
  de chamador fecha, porque o segundo processo não vê a intenção do primeiro.
- **(B) RPC transacional única** — uma função que trava o item (`FOR UPDATE`), confere as
  pré-condições e abre o recibo no mesmo `BEGIN/COMMIT` torna a janela inexistente.

**Escolha: B**, e a justificativa não é economia de round-trip — é que a invariante
provada ausente na seção 3 **não é expressável na camada de aplicação sobre PostgREST**.
Uma nova migration é obrigatória, e a prova disso é a reprodução acima, não a suposição.

## 5. Fronteira da transação produtiva

```text
                        ┌── tudo abaixo numa transação de banco ──┐
intenção ─ blueprint ─ lote ─ item ─ validações                    │  RPC 1  abrir
                        └─────────────────────────────────────────┘

                        ┌── uma transação; trava o item FOR UPDATE ┐
aprovação humana ─ recusa se houver recibo não resolvido ─ item→criando ─ recibo em_voo
                        └──────────────────────────────────────────┘  RPC 2  despachar
                                          │
                                    COMMIT  ← o recibo já existe no banco
                                          │
                            ══════ FRONTEIRA GOOGLE ADS ══════
                                          │
        ┌─────────────────┬───────────────┼──────────────┐
     sucesso            erro          sem resposta    processo morre
        │                 │               │               │
        └── RPC 3 fechar ─┴───────────────┘         recibo FICA em_voo
              (id_externo + carimbo)                 (é a verdade)
                                                          │
                                              RPC 4 reconciliar
                                        (verificação achou=true/false/NULL)
```

Estados do resultado remoto, mantidos distintos ponta a ponta:
`não iniciado` (item `planejado`) · `em_voo` (recibo aberto) · `sucesso confirmado`
(recibo `sucesso` + `id_externo` carimbado) · `falha confirmada` (recibo `erro`, e item só
vai a `falhou` se nenhum recibo estiver aberto) · `indeterminado` (recibo `sem_resposta`
ou aberto; item `indeterminado`) · `reconciliado` (`trafego_verificacao.achou` não nulo).

## 6. Ownership desta sprint

**Escrita (writer único por arquivo):**

| Arquivo | Missão | Natureza |
|---|---|---|
| `supabase/migrations/v10_03_recibo_atomico.sql` + `_rollback.sql` | S2 | novo |
| `backend/app/trafego/ledger.py` | S3 | novo |
| `backend/app/routers/trafego.py` (só `subir()` e `_registrar_campanha`) | S3 | cirúrgico |
| `src/lib/pautadorApi.ts` (só `subirCampanha`) · `src/components/trafego/Lancamento.tsx` | S4 | cirúrgico |
| `backend/tests/test_trafego_ledger.py`, `scripts/provar-ciclo-v10.sh` | S2/S5 | novo/extensão |

**Proibido tocar:** `lote.py`, `intencao.py` (domínio puro, 111 testes, espelham o SQL) ·
`persistencia.py` (guarda de tabelas do inventário) · `v10_01/v10_02.sql` (aplicadas em
cluster de prova; campo novo exige migration nova) · `reconciliacao.py`,
`trafego_inventario.py`, `diagnostico_persistido.py` (outros fluxos) ·
`QuadroDoLote.tsx`, `laboratorio/**` (órfão e sintético).

## 7. Fronteiras externas que permanecem fechadas

Aplicar migration no Supabase oficial · qualquer escrita no Supabase oficial · mutate ou
`validate_only` real contra o Google Ads · tocar Crédito Up · ativar campanha · n8n · push
· deploy. Nenhuma foi executada; o pacote de preflight sai em S5.
