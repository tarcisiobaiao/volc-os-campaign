# HANDOFF — SEARCH TRACKING CONTROL PLANE V1

**Data:** 2026-09-02
**Branch:** `sprint/search-tracking-control-plane-v1`
**Base:** `26a58c444f20af547b6e4e01267c9f746cf9e438` (= `origin/volc-os-v2`, conferido no preflight)
**Worktree:** `/private/tmp/volc-search-tracking-control-plane-v1`

---

## 1. O estado final, sem enfeite

**O caminho de escrita ganhou portão. O perfil de mensuração existe. A releitura
existe. A fronteira da Data Manager existe e não envia. Produção não foi
alterada.**

- ✅ nenhuma escrita no Supabase oficial
- ✅ nenhum `mutate` no Google Ads
- ✅ nenhum evento enviado pela Data Manager, nem `validateOnly`
- ✅ nenhuma migration aplicada, e **nenhuma escrita**
- ✅ nenhum push, merge, deploy ou ativação
- ✅ nenhuma meta de conversão ou `ConversionAction` alterada ou criada
- ⚠️ **P05-T12 continua `partial`**, e por três razões que continuam de pé — §9

---

## 2. Os quatro fatos que abriram a missão

Todos **medidos** contra o código da base `26a58c4`, não deduzidos.

### 2.1 `/subir` criava em Smart Bidding com a medição reprovada

```
PROVAR diz: smart_bidding_eligible = False
PROVAR diz: bloqueadores = 5
ATOS: ['ler_plano','abrir','despachar','registrar_plano','MUTATE','fechar_sem_resposta']
>>> MUTATE aconteceu? True
```

`/provar` calculava os portões, projetava na resposta, e **`/subir` nunca
chamava `prontidao.avaliar`**. O `estrategia_lance` do corpo atravessava
`Escolha` (`trafego.py:2989`) até o executor sem passar por nada. O risco ficava
contido só porque a campanha nasce PAUSED por literal em `comum.py` e o engine
não tem função de ativação — duas defesas que ninguém escolheu como portão de
lance, e que a primeira pessoa a despausar pelo painel do Google desfaz.

### 2.2 `data_manager_status` saía `PRONTO` sem destino

```
destino resolvido? False
DEFEITO C -> data_manager_status = PRONTO
```

`data_manager_operante` é um booleano que quem chama afirma. Com ele `True` e um
plano sem `acao_alvo` — logo sem `operating_account_id` e sem
`product_destination_id` — o portão abria. Pronto para mandar evento para lugar
nenhum.

### 2.3 `activation_ready` não existia

```
'activation_ready' presente? False
chaves: [activation_blockers, activation_blockers_materiais, campaign_birth,
         conversion_goal_status, conversion_signal_status, creation_plan_ready,
         data_manager_status, measurement_readiness, notas, observability_status,
         plano_de_mensuracao, signal_paths, signal_sources, smart_bidding_eligible]
```

Havia a lista de razões e nenhum campo que respondesse à pergunta. Uma lista
vazia lida como permissão é o default otimista que este sistema recusa em todos
os outros portões — e que aqui entrava pela ausência do campo.

### 2.4 `chave_intencao` não é identidade de medição

```
chave base               83e7fe044dc356ce…
mesma oferta, verba 50   928379f2dcf0c957…
mesma oferta, verba 80   e5189893fb8ec057…
```

Ela é o sha256 do payload aprovado inteiro, e está **certa** no que faz — dela
saem a marca remota do canário e a chave de idempotência do ledger. Como
identidade da MEDIÇÃO ela erra nas duas direções: distingue demais (a mesma
oferta com duas verbas vira dois perfis, e as duas campanhas medem a mesma
coisa) e não distingue o que importa (nada nela fala de evento de negócio,
funil, regra de valor ou janela).

---

## 3. O que foi construído, e o que foi REUSADO

### Reusado, não reescrito

- `pm.eleger_acao_canonica` — a eleição por semântica + id numérico, com
  `primary_for_goal` e seu default documentado. Já estava correta.
- `pm.resolver_destino` — conta dona + id numérico, com as três causas separadas.
- `pm.fontes_de_sinal_observadas` / `caminhos_de_sinal_declarados` — a distinção
  entre prova e capacidade. Reimplementá-la criaria dois lugares onde a mesma
  regra pode divergir.
- `prontidao.avaliar` — os quatro portões existentes, palavra por palavra.
- `persistencia.RepositorioDePlanoDeMensuracao` e a RPC governada.
- `payload` da v12_02 como lugar do perfil — é onde `vinculo` já mora, e a
  própria migration declara o critério ("as colunas são o que se consulta, e o
  payload é o que se audita").

### Construído

| arquivo | o quê |
|---|---|
| `backend/app/trafego/perfil_de_mensuracao.py` | a identidade do que se mede — decisão separada de observação |
| `backend/app/trafego/data_manager.py` | a fronteira `validateOnly`, sem cliente HTTP |
| `backend/app/trafego/prontidao.py` (+) | `activation_ready`, `smart_bidding_ready`, `exigir_para_criacao`, destino no portão da Data Manager |
| `backend/app/trafego/plano_mensuracao.py` (+) | o perfil dentro do plano, e dentro da impressão |
| `backend/app/routers/trafego.py` (+) | o portão em `/subir`, `GET /plano-de-mensuracao`, o portão de conta na reconciliação |
| `src/lib/trafego/portoes.ts` | os sete portões e o perfil, do lado da tela |
| `src/components/trafego/canais/PainelDaMensuracao.tsx` | a verdade operacional, montada em `Lancamento.tsx` |

---

## 4. As decisões que custaram algo, e por quê

### 4.1 O perfil entra na **impressão** do plano, e não só no payload

A RPC é **idempotente pela impressão**, e a impressão não conhecia o perfil.
Duas campanhas da mesma conta, mesma `chave_intencao`, mesma meta e mesma ação —
com perfis diferentes — produziriam a mesma impressão, e a segunda escrita seria
engolida devolvendo o `plano_id` da primeira. É literalmente o defeito que a
docstring de `impressao()` já descreve duas vezes.

E entra **sem reescrever o passado**: a chave `perfil` só existe no corpo do
hash quando há perfil. `{"perfil": null}` e `{}` dão hashes diferentes, e foi
assim que `assets_display` mudou a impressão de todo plano Search em
01/09/2026. Aqui o custo seria maior — tabela append-only e idempotente por
impressão, toda linha gravada deixaria de ser reencontrável **de uma vez**.
Constante de regressão pinada no teste, medida antes de o campo existir:
`b76c89dc1b7275a2a56b371385a8dc8b7eac37d27d527d770521653a35a6a263`.

### 4.2 Os dois portões novos são **propriedades** — e isso não bastou

Campo permitiria escrever a contradição — estado `PRONTO` ao lado de bloqueador
material, ou estado discordando do booleano. A primeira versão tinha os dois
como campos com invariantes de `__post_init__` que os checavam; ela quebrou dois
testes existentes que constroem `Prontidao` diretamente. Derivado, a contradição
entre os DOIS ESTADOS não é expressável.

⚠️ **E a revisão adversarial mostrou que isso resolvia metade do problema.**
`smart_bidding_ready` deriva do booleano — e o booleano continuou sendo **campo**.
`Prontidao(smart_bidding_eligible=True)` produzia `PRONTO` com medição e
observabilidade indeterminadas. Derivar não basta se a FONTE da derivação for
afirmável sem lastro: `__post_init__` passou a exigir as duas provas. Ver
`ADJUDICACAO-CODEX.md` §2.

### 4.3 O portão de escrita olha `measurement_ready`, não `smart_bidding_ready`

`smart_bidding_ready` exige observabilidade **pós-criação**, que por definição
não existe antes de a campanha nascer. Exigi-la no nascimento tornaria
`MANUAL_CPC` a única estratégia possível para sempre — um portão que nunca abre
não protege, esconde a decisão.

### 4.4 `activation_blockers` deixou de sair vazio com tudo medido

E isso é **correção**, não regressão. `contrato_canais._portao_ativavel` já dizia
que ativar está BLOQUEADO por política em todo canal, enquanto `prontidao`
devolvia lista vazia. Dois módulos do mesmo sistema respondiam coisas opostas
sobre o mesmo ato, e o que a tela lia era o vazio. As duas razões novas —
política e plano não persistido — são **não materiais**: nenhuma é sobre medir
ou observar, e por isso nenhuma contradiz `smart_bidding_eligible`.

Um teste existente (`test_com_tudo_provado_o_smart_bidding_fica_elegivel`) foi
atualizado: ele exigia `activation_blockers == ()`, e agora exige
`activation_blockers_materiais == ()` — que é o que "tudo provado" quer dizer.
A mudança está documentada dentro do próprio teste.

### 4.5 Nenhuma fila nova, e nenhum schema

`conversion_queue` e `conversion_batches` foram **auditadas** e recusadas: faltam
destino, conta, `wbraid`/`gbraid`, consentimento e chave de dedup — e as duas não
têm DDL no repositório. A conclusão foi registrada em vez de virar migration:
ver `AUTORIZACAO-UNICA.md` §C, com a recomendação e a razão de eu não a ter
escrito.

---

## 5. Provas — reproduzidas ANTES da correção

| # | defeito | onde a reprodução está |
|---|---|---|
| 1 | `/subir` cria em Smart Bidding sem meta biddable | `test_subir_em_smart_bidding_sem_sinal_nao_chama_o_google` |
| 2 | recusa acontece antes de recibo e plano | `test_a_recusa_acontece_antes_do_recibo_e_do_plano` |
| 3 | Data Manager PRONTO sem destino | `test_data_manager_nao_fica_pronto_sem_destino_resolvido` |
| 4 | `activation_ready` inexistente | `test_os_sete_portoes_estao_na_resposta` |
| 5 | nichos diferentes colidindo | `test_nichos_diferentes_na_mesma_conta_nao_colidem` |
| 6 | ação resolvida por nome | `test_o_nome_humano_da_acao_nao_entra_na_identidade`, `test_derivar_de_plano_nao_aceita_ser_ancorado_em_nome` |
| 7 | `primary_for_goal=false` elegível por engano | reusado de `eleger_acao_canonica`; coberto em `test_perfil_sem_acao_nao_e_aplicavel_a_smart_bidding` |
| 8 | auto-tagging virando conversão | `test_derivar_le_a_fonte_do_sinal_do_frescor_e_nao_da_capacidade`, `test_fonte_nao_comprovada_nao_e_aplicavel_a_smart_bidding` |
| 9 | ausência virando zero | `test_valor_zero_e_MEDIDO_e_nao_ausencia`, `test_ausencia_de_linha_nao_vira_plano_vazio` |
| 10 | falha de API virando ausência | `test_falha_de_leitura_nao_vira_ausencia`, `test_leitura_que_nao_completou_tambem_recusa` |
| 11 | custom goal como goal padrão | reusado de `MetaEfetiva.resolvida`; visível em `textoDaProcedenciaDaMeta` |
| 12 | Data Manager pronto sem destino (fronteira) | `test_sem_destino_resolvido_nao_existe_envelope` |
| 13 | ativação pronta sem plano persistido | `test_ativacao_nao_fica_pronta_sem_plano_persistido` |
| 14 | Smart Bidding pronto sem meta biddable | `test_maximize_conversions_sem_sinal_e_recusado` |
| 15 | resposta vazia da RPC aceita como persistência | já coberto na entrega anterior; preservado |
| 16 | conta externa vinculada | `test_linha_de_outra_conta_nao_e_vinculada_por_prefixo`, `test_linha_de_outra_conta_e_recusada_e_nao_devolvida` |
| 17 | repetição criando segunda linha lógica | `test_o_mesmo_perfil_continua_idempotente`, `test_o_mesmo_envelope_tem_a_mesma_impressao` |
| 18 | verde por configuração na tela | o bloco "verde só com prova" em `painel-da-mensuracao.test.tsx` |

E mais **23** nascidas da revisão adversarial, em
`backend/tests/test_trafego_revisao_adversarial.py` — 15 delas falhavam contra o
código que a revisão reprovou. Ver `ADJUDICACAO-CODEX.md`.

---

## 6. Gates — medidos, com baseline verdadeiro

Baseline medido **nesta worktree**, com os `.env` copiados do repo principal
(sem eles, 7 arquivos de teste de front falham na COLETA — é ambiente, não
regressão).

| gate | baseline (`26a58c4`) | depois | veredito |
|---|---|---|---|
| `pytest backend/tests volc_ads -q` | 2736 passed · 30 skipped · **0 failed** | **2882 passed · 30 skipped · 0 failed** | +146 = as provas novas (123) + as 23 da revisão |
| `npx vitest run` | 1173 passed · 3 skipped (medido na entrega anterior) | **1210 passed · 3 skipped · 0 failed** | +37 provas novas |
| `npx tsc --noEmit -p tsconfig.app.json` | **76 erros** | **76 erros** | igual; **zero** nos arquivos tocados |
| `npm run build` | verde | **verde** | |
| `git diff --check` | — | **limpo** | |
| `scripts/verificar_segredos.py` | — | **nenhum padrão forte** | |
| `scripts/gate_sem_mutacao_google.py` | 3/3 | **3/3** | trava fechada, env não armada, 5 contraprovas focais |
| ciclo SQL v12_02 | 55 · 0 | **não aplicável** | nenhuma migration foi tocada — `git diff` em `supabase/` é vazio |

---

## 7. Ownership — o que foi e o que NÃO foi tocado

**Tocado:** `backend/app/trafego/{perfil_de_mensuracao,data_manager,prontidao,
plano_mensuracao}.py`, `backend/app/routers/trafego.py`,
`backend/tests/test_trafego_{perfil_de_mensuracao,portoes_de_escrita,
plano_com_perfil,plano_relido,data_manager,plano_de_mensuracao}.py`,
`src/{lib/trafego/portoes.ts,types/trafego.ts}`,
`src/components/trafego/{Lancamento.tsx,canais/PainelDaMensuracao.tsx}` + teste,
`docs/closure/search-tracking-control-plane-v1/**`.

**NÃO tocado — conferido por `git diff --stat` em cada caminho:**
`supabase/**` (nenhuma migration), `volc_ads/**` (o motor),
`volc-os-workbook/ROADMAP-VIVO.json`,
`docs/volc-os-graph/curadoria-operacional.json`, `graphify-out/**`, `n8n/**`,
`main`, harness, configuração de produção.

---

## 8. Revisão externa

- **Codex `gpt-5.6-sol` (high):** **REPROVOU** com 2 BLOQUEANTES, 7 IMPORTA e
  1 MENOR. Adjudicação: **os dez procedem**, todos corrigidos, 23 provas novas
  que falhavam contra o código reprovado. Os dois bloqueantes eram a mesma
  família — **conferir a COLUNA e devolver o PAYLOAD** —, e o portão de conta
  que eu tinha acrescentado nesta mesma missão foi o que criou a falsa sensação
  de cobertura. Detalhe completo em `ADJUDICACAO-CODEX.md`.
- **Gemini:** **NÃO DISPONÍVEL** — CLI instalado, sem método de autenticação.
  Registrado em `REVISORES-EXTERNOS.md` dentro dos cinco minutos, sem consertar
  harness. Nenhuma afirmação NOVA de contrato Google foi introduzida por esta
  entrega; as regras aplicadas foram reusadas do código base, que já passou por
  validação Gemini em 01/09/2026.

---

## 9. O que continua aberto — e por que P05-T12 segue `partial`

| item | estado | por quê |
|---|---|---|
| plano real durável | **não existe** | a tabela segue vazia. `/subir` só aceita a conta canário, e nenhum `/subir` autorizado aconteceu. É o primeiro critério de aceite de P05-T12 |
| Data Manager em operação | **não provado** | nenhum evento, nem `validateOnly` contra a API real. A fronteira existe; o caminho de envio, não |
| observabilidade pós-criação | **não exercida** | `coleta_pos_criacao_provada` é literal `False` no único chamador de produção. Logo `observability_ready` e `activation_ready` **não podem** sair `PRONTO` em produção — e isso é honesto, não defeito |
| `MAXIMIZE_CONVERSION_VALUE` | **fechado de propósito** | este sistema não lê `conversion_action.value_settings`, e `/subir` ainda não recebe os eixos de negócio. Duas formas de abrir, com custo, em `AUTORIZACAO-UNICA.md` §D |
| inventário GA4/GTM/UTM | **inexistente** | é a outra metade de P06-T07, e nenhuma linha desta entrega a toca |
| cache da leitura do plano | **aberto** | herdado: o teto de 30 s não cancela a thread, e dez cliques em cinco minutos deixam dez threads órfãs gastando quota. Declarado na entrega anterior, não mitigado nesta |
| `conversion_queue` legada | **legado sem dono** | 0 linhas, sem DDL no repositório, presumido produtor em n8n que ninguém desta missão auditou |

---

## 10. Para o integrador

1. `delta-curadoria.json` traz 7 nós, 10 arestas, **P05-T12 segue `partial`** e
   **P06-T07 vai de `todo` para `partial`** — aplicar só depois do merge.
2. Reconstruir o Mapa Vivo **uma vez** por
   `python3 scripts/atualizar_grafo_volc_os.py` e rodar `--check`.
   ⚠️ **Não rodado nesta missão de propósito:** branch não integrada não marca a
   fonte compartilhada, e Roadmap/curadoria/grafo estão fora do ownership.
   ⚠️ O grafo já estava defasado na base: `UPDATE_STATUS.json` aponta
   `a539dbd`, e `origin/volc-os-v2` está em `26a58c4`.
3. A worktree tem `.env`, `.env.local`, `.env.server` e `backend/.env` copiados
   e `node_modules`/`backend/.venv` symlinkados. Todos gitignored; a árvore está
   limpa. `package.json` e `package-lock.json` conferidos idênticos por `diff`.
4. `AUTORIZACAO-UNICA.md` é o pacote de dono: cinco atos, em ordem de
   dependência, cada um com operação, destino, impacto, rollback e verificação.
5. ⚠️ **A base ANDOU durante esta missão.** `origin/volc-os-v2` saiu de
   `26a58c4` para `36bec04` — 21 commits das lanes Hermes de observabilidade
   PMax, todos em `volc_ads/inteligencia_google/**`, `scripts/`, `docs/` e
   Roadmap/curadoria. **Zero arquivos em comum** com esta branch, conferido por
   `comm -12` sobre as duas listas de arquivos alterados; `git merge-tree
   --write-tree` (que não muta nada) devolve **merge limpo**. Eu **não** rebasei
   nem mergeei: a base declarada da missão era `26a58c4`, e mudá-la
   unilateralmente apagaria a rastreabilidade do que foi medido contra o quê.
   ⚠️ E `36bec04` inclui um `V12-03-REQUIREMENTS.md` da lane PMax — se ele pedir
   schema novo, vale conferir a interação com o `payload` da v12_02 antes de
   aplicar as duas coisas na mesma janela.
