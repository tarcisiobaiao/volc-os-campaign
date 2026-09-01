# HANDOFF — SEARCH MEASUREMENT OPERATIONAL CLOSURE V1

**Data:** 2026-09-01
**Branch:** `sprint/search-measurement-operational-v1`
**Base:** `812ab0d4ab3091072e695f52db6e117f04aa2ce7` (= `origin/volc-os-v2`, conferido)
**Worktree:** `/private/tmp/volc-search-measurement-operational-v1`
**Commits:** `57028f2` · `11d5c6b` · `2aaa752` · `3837892`

---

## 1. O estado final, sem enfeite

**Código operacional pronto. Persistence path provado em ambiente descartável.
Pacote de aplicação pronto. Produção NÃO foi alterada.**

- ✅ nenhuma escrita no Supabase oficial
- ✅ nenhum `mutate` no Google Ads, Data Manager ou GTM
- ✅ nenhum push, merge, deploy ou ativação
- ✅ nenhuma meta ou ação de conversão alterada
- ✅ a v12_02 **continua não aplicada** — e por isso **P05-T12 continua `partial`**

---

## 2. O fato que abre a missão

`RepositorioDePlanoDeMensuracao` (`backend/app/trafego/persistencia.py:959`) e o
tradutor puro `documento_de_plano_de_mensuracao` (`persistencia.py:411`) tinham
**zero chamadores de produção**. A migration v12_02 existia, a RPC governada
existia, o domínio existia, a tela existia — e **nada gravava**. O plano de
mensuração era calculado em `/provar`, projetado na resposta HTTP e descartado.
`/subir` sequer o montava.

O efeito: a campanha nascia e o que se sabia sobre a medição dela no instante da
decisão não sobrevivia à requisição.

---

## 3. A ordem que passou a valer

```
guardas → canário → escopo → reprova (selo) → idempotência remota (LEITURA)
        → LER o plano                          ← novo
        → ledger.abrir → ledger.despachar
        → GRAVAR o plano (RPC governada)       ← novo · falhou aqui, o Google NÃO é chamado
        → sb.subir   (a ÚNICA chamada que muta)
        → conferir a conta do resource_name    ← novo
        → fechar_sucesso (declara identidade em trafego_campanha)
        → VINCULAR o plano ao campaign_id      ← novo
```

**Por que a leitura vem antes do `abrir` e a gravação depois do `despachar`:** a
leitura são cinco consultas GAQL com teto de 30 s e pode falhar; rodá-la depois
do `abrir` faria um timeout deixar um recibo `em_voo` órfão para uma chamada que
nunca saiu. A gravação é rápida e é a última coisa antes da rede, porque é ela
que o contrato manda ser obrigatória.

**Leitura que não completa NÃO recusa a criação.** Ela produz o plano de
ignorância com causa, que a v12_02 aceita e que mantém os portões de ativação
fechados. A campanha nasce pausada; recusar transformaria uma indisponibilidade
do Google numa indisponibilidade do VOLC.

**O vínculo é REVINCULAÇÃO, não releitura.** A linha pós-nascimento é a mesma
observação com endereço: `chave_intencao`, `lido_em` e os seis estados de leitura
preservados; `versao` sobe; a impressão inclui o `campaign_id`, então a linha
nova entra ao lado da antiga — append-only respeitado, sem `UPDATE`.
`payload.vinculo.observado_antes_do_nascimento` carrega a ressalva que impede a
linha de mentir depois: `metas_da_campanha_estado='inelegivel'` numa linha com
`campaign_id` descreve o instante da leitura, não a campanha.

---

## 4. As 15 contraprovas da missão

| # | prova | onde | estado |
|---|---|---|---|
| 1 | persistência falha ⇒ Google não é chamado | `test_plano_que_nao_grava_impede_o_mutate`, `test_recusa_de_guarda_do_schema_tambem_impede_o_mutate`, `test_repositorio_desabilitado_e_recusa_e_nao_permissao`, `test_rpc_que_responde_sem_plano_id_impede_o_mutate` | ✅ |
| 2 | plano depois do mutate ⇒ teste falha | `test_o_plano_e_gravado_antes_do_mutate_e_nao_depois`, `test_a_sequencia_inteira_dos_atos_e_a_declarada` | ✅ |
| 3 | sucesso ⇒ vínculo com campaign_id, mesma intenção | `test_sucesso_vincula_o_mesmo_plano_ao_campaign_id`, `test_exatamente_uma_intencao_une_o_pre_e_o_pos_nascimento`, `test_o_vinculo_e_linha_nova_e_nunca_um_update` | ✅ |
| 4 | resposta ausente ⇒ nenhum campaign_id inventado | `test_indeterminado_nao_inventa_campaign_id_no_plano`, `test_excecao_desconhecida_depois_do_mutate_nao_vincula` | ✅ |
| 5 | reconciliação ⇒ vínculo correto, sem segunda intenção | `test_reconciliar_vincula_o_mesmo_plano_a_campanha_descoberta`, `test_reconciliar_recusa_campanha_que_nao_carrega_a_marca_da_intencao` | ✅ |
| 6 | repetição idempotente ⇒ zero segunda campanha | `test_repetir_subir_de_verdade_nao_cria_segunda_campanha`, `test_gravar_o_mesmo_plano_duas_vezes_devolve_a_mesma_linha` | ✅ |
| 7 | contas diferentes ⇒ zero colisão | `test_a_mesma_leitura_em_contas_diferentes_produz_impressoes_diferentes`, `test_a_chave_de_intencao_carrega_a_conta_e_por_isso_nao_colide` | ✅ |
| 8 | intenções diferentes ⇒ zero compartilhamento | `test_intencoes_diferentes_nao_compartilham_plano`, `test_por_intencao_nao_devolve_o_plano_de_outra_intencao` | ✅ |
| 9 | owner ≠ conta operacional ⇒ preservado | `test_o_dono_da_acao_diferente_da_conta_operacional_atravessa_intacto`, `test_o_vinculo_nao_reescreve_o_dono_da_acao` | ✅ |
| 10 | Data Manager resolvido ⇒ continua não pronto | `test_destino_resolvido_nao_torna_o_data_manager_pronto`, `test_a_prova_declara_data_manager_nao_operante` | ✅ |
| 11 | sinal observado ≠ caminho declarado | `test_fonte_observada_e_caminho_declarado_nao_se_confundem`, `test_zero_medido_e_ausencia_nao_viram_a_mesma_coluna` | ✅ |
| 12 | PMax bloqueado pelos DOIS motivos | `test_pmax_continua_fora_do_executor`, `test_a_observabilidade_de_pmax_continua_nao_provada`, `test_os_dois_bloqueios_de_pmax_sao_independentes`, `test_o_plano_persistido_nao_abre_a_criacao_de_pmax` | ✅ |
| 13 | front não vira null em zero nem falha em ausência | `plano-de-mensuracao.test.tsx` (12), `lancamento.test.tsx` (dinheiro), `lancamento.test.ts` (falha ≠ indeterminação) | ✅ |
| 14 | migration ausente ⇒ falha fechado e didática | `test_migration_ausente_recusa_com_o_nome_do_que_falta`, `test_o_repositorio_traduz_pgrst202_em_migration_ausente`, `test_uma_guarda_do_schema_nao_e_confundida_com_migration_ausente` | ✅ |
| 15 | zero mutação externa | fixture autouse `_rede_bloqueada` (socket) em todo o arquivo + `scripts/gate_sem_mutacao_google.py` 3/3 | ✅ |

Arquivo: `backend/tests/test_trafego_plano_persistido.py` — **52 provas**, escritas
**antes** da correção (36 falhavam na primeira execução).

---

## 5. Gates — medidos, com baseline verdadeiro

O baseline foi remedido **com os arquivos de env presentes** (`git stash` na
própria worktree), porque a primeira medição rodou sem eles e escondia 23 testes.

| gate | baseline (812ab0d) | depois | veredito |
|---|---|---|---|
| `pytest backend/tests volc_ads -q` | 2682 passed · 30 skipped · **0 failed** | 2734 passed · 30 skipped · **0 failed** | +52 = exatamente as provas novas |
| `npx vitest run` (sozinho) | 1156 passed · 5 skipped · 0 failed | 1173 passed · 3 skipped · **0 failed** | +15 provas novas; 2 `skipIf(semBuild)` passaram a rodar porque `dist/` existe, e passam |
| `npx tsc --noEmit -p tsconfig.app.json` | 76 erros | **76 erros** | igual; **zero** erro nos arquivos tocados |
| `bash scripts/provar-ciclo-v12_02.sh` | 55 · 0 | **55 · 0** | migration não foi alterada |
| `npm run build` | verde | **verde** | |
| `git diff --check` | — | **limpo** | |
| `scripts/verificar_segredos.py` | — | **nenhum padrão forte** | |
| `scripts/gate_sem_mutacao_google.py` | — | **3/3** | trava fechada, env não armada, 5 contraprovas focais |

⚠️ **Nota de ambiente (não é regressão):** a worktree nasce sem os `.env`
(gitignored). Sem eles, `src/lib/supabase.ts:7` levanta no import e 7 arquivos de
teste de front falham na COLETA. Copiados do repo principal; `package.json` e
`package-lock.json` conferidos idênticos por `diff`.

---

## 6. Defeitos reproduzidos e consertados no caminho

Nenhum foi procurado; todos apareceram provando o caminho produtivo.

1. **`campaign_id` sem `customer_id`.** `_campaign_id_do_recibo` fazia
   `rsplit('/', 1)[-1]` e descartava o segmento `customers/<conta>` — a única
   prova de que a campanha criada é da conta em que se pediu para criá-la. Como
   `volc_campaign_id = uuid5(gads:<conta>:<campanha>)`, um resource_name de
   outra conta cunharia identidade com a conta do escopo e o id alheio.
2. **A conferência de conta chegava tarde.** Mesmo com (1) corrigido, ela
   acontecia só no vínculo do plano — depois de `_fechar_recibo_com_sucesso` já
   ter carimbado o par errado no ledger.
3. **`_registrar_campanha` tinha a segunda derivação.** O commit `11d5c6b`
   afirmou que a duplicação tinha saído; ela não tinha. Saiu em `3837892`.
4. **O 504 mandava reconciliar sem dar a chave.** `ReconciliarEntrada` exige
   `campaign_id` OU `marca`, e o item que mais precisa de reconciliação é o que
   não tem `campaign_id`.
5. **`registrar()` devolvia `None` sem levantar** com RPC 200 + corpo vazio, e
   `/subir` seguia para o Google.
6. **O 503 não dizia que o recibo ficou `em_voo`.**
7. **A reconciliação ligava qualquer campanha da mesma conta.**
8. **`textoDaMetaEfetiva`** emitia veredito de uma lista vazia sem olhar o estado
   da leitura: falha virava "nenhuma meta é perseguível".
9. **`textoDaFonteDoSinal`** tinha `?? 'nenhuma ação foi eleita'` sobre ignorância.
10. **O destino colapsava três situações num booleano**, e "resolvido" era lido
    como "a ingestão offline funciona".
11. **`Number(x ?? 0).toFixed(2)` no dinheiro** do retângulo imediatamente acima
    do checkbox de confirmação.
12. **`do_json` prometia "inverso exato"** e recalcula os derivados; e
    `click_ids_suportados=[]` voltava como o default completo por um `or`.
13. **Falha de gravação seria lida pelo front como indeterminação** — "pode haver
    campanha criada" sobre uma chamada que nunca saiu.

Os itens 5, 6, 7 e 12 vieram da revisão adversarial (Codex Sol), que **reprovou**
a primeira integração. Os quatro foram conferidos por mim e todos eram reais.

---

## 7. Revisão final — uma rodada, como mandado

- **Codex Sol (gpt-5.6-sol, high):** REPROVOU com 4 bloqueantes + 2 `IMPORTA` +
  6 contraprovas fracas. Adjudicação: **todos procedentes**, todos corrigidos em
  `3837892`. Ele também confirmou "nada encontrado" em idempotência e nos
  `except Exception` novos.
- **Gemini 3 Flash (fact-check dos contratos Google):** 12 de 14 afirmações
  **CORRETAS**. Duas em disputa, nenhuma muda comportamento:
  - `goal_config_level = UNSPECIFIED` — Gemini diz que funcionalmente equivale a
    CUSTOMER; o código o trata como "não decide". Falha na direção **segura**
    (produz "não sei", nunca autoriza Smart Bidding). Comportamento anterior a
    esta missão; **não alterado**.
  - o modo de falha da Data Manager ao mandar para a conta errada — a prosa deste
    repositório diz "silêncio", Gemini aponta erro de posse
    (`OPERATING_ACCOUNT_LOGIN_ACCOUNT_MISMATCH`). O CHECK
    `trafego_plano_destino_e_do_dono_da_acao` fecha a porta nas duas leituras.
    A prosa **nova** desta missão foi ajustada para não repetir a afirmação
    disputada; a antiga foi deixada como está.
- **Claude (lead):** adjudicação acima, mais um experimento próprio que refutou um
  achado de investigador — ver §8.

---

## 8. Um achado de investigador que era falso, decidido por experimento

Um investigador afirmou que a **invariante 6** da v12_02 obrigaria uma releitura
real no Google para o revínculo: "só se pode gravar `campaign_id` não nulo se
`metas_da_campanha_estado` deixar de ser `inelegivel`".

**Falso.** O CHECK é
`(campaign_id is not null OR metas_da_campanha_estado = 'inelegivel')` — com
`campaign_id` preenchido, o primeiro disjunto já satisfaz. Medido em cluster
descartável (v9_01 + v12_02 aplicadas), 01/09/2026:

- `campaign_id='24183717006'` + `metas_da_campanha_estado='inelegivel'` → **INSERT 0 1**
- `campaign_id=null` + `metas_da_campanha_estado='nao_coletado'` → **recusado** por
  `trafego_plano_campanha_inexistente_nao_tem_meta`

A invariante é **unidirecional**. É isso que torna a revinculação sem releitura
executável, e é por isso que **nenhuma migration precisou de correção**.

---

## 9. O que continua aberto

| item | estado | por quê |
|---|---|---|
| v12_02 em produção | **não aplicada** | exige autorização de dono — ver `APLICACAO-V12-02.md` |
| P05-T12 | **partial** | o primeiro critério de aceite é "persistido no Supabase oficial" |
| Data Manager | **não provado em operação** | nenhum evento, nem `validateOnly`, nesta missão |
| coleta PMax | **não implementada** | fora de escopo; os dois bloqueios seguem independentes |
| Smart Bidding no caminho de escrita | **sem portão** | `search.py:57` permite `MAXIMIZE_CONVERSIONS`; G3 só é avaliado por `/provar`. Risco baixo porque a campanha nasce PAUSED por literal e não existe função de ativação. Declarado para decisão do dono — ver `delta-curadoria.json` |
| `intencao_id` instável entre `/provar` e `/subir` | **aberto** | `rotulo` vem de `plano.brief.titulo`, recomputado no `/subir`. Não afeta o plano (que se ancora em `chave_intencao`); afeta a idempotência do ledger. Domínio de P10 |
| `contaDoVeredito` nunca limpo | **aberto** | `src/pages/trafego/NovaCampanhaPage.tsx` — fora do ownership desta missão |

---

## 10. Ownership — o que foi e o que NÃO foi tocado

**Tocado:** `backend/app/trafego/{plano_mensuracao,persistencia}.py`,
`backend/app/routers/trafego.py`, `backend/tests/{test_trafego_plano_persistido,
test_trafego_ledger,test_trafego_ledger_producao}.py`,
`src/{types/trafego.ts,lib/trafego/{canais,lancamento}.ts}`,
`src/components/trafego/{Lancamento.tsx,canais/PlanoDeMensuracao.tsx}` + testes,
`docs/closure/search-measurement-operational-v1/**`.

**NÃO tocado:** `volc_ads/inteligencia_google/**` (lane Hermes P09-T14),
`supabase/migrations/**` (nenhuma migration alterada), harness, n8n, `main`,
`volc-os-workbook/ROADMAP-VIVO.json`, `docs/volc-os-graph/curadoria-operacional.json`,
o grafo, configuração de produção.

---

## 11. Para o integrador

1. `delta-curadoria.json` traz 7 nós, 10 arestas e o delta de evidência de
   **P05-T12** (segue `partial`) — aplicar só depois do merge.
2. Reconstruir o Mapa Vivo **uma vez** por
   `python3 scripts/atualizar_grafo_volc_os.py` e rodar `--check`.
   ⚠️ **Não rodado nesta missão de propósito:** trabalho em branch não integrada
   não marca a fonte compartilhada, e o Roadmap/curadoria/grafo estão fora do
   ownership declarado.
3. A worktree tem `.env`, `.env.local`, `.env.server`, `backend/.env` copiados e
   `node_modules`/`backend/.venv` symlinkados. Todos gitignored; a árvore está
   limpa.
4. `APLICACAO-V12-02.md` é o pacote para o dono aplicar a migration.
