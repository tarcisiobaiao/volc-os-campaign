# HANDOFF — Pautador: elegibilidade de keyword paga v1

**Veredito: `PAUTADOR_PAID_KEYWORD_ELIGIBILITY_ACCEPTED`**

`ACCEPTED` significa que o conjunto de keywords pode ser PREPARADO com
governança. **Não autoriza lançamento.** Conta, destino pago, mensuração e
aprovação de gasto continuam sendo portões independentes, nenhum deles avaliado
aqui.

---

## Base e SHA

| | |
|---|---|
| base | `origin/volc-os-v2 @ 34dc7b41bce901bd8bebfdec0a01e293678cbf08` |
| branch | `sprint/pautador-paid-keyword-eligibility-v1` |
| worktree | `/private/tmp/volc-pautador-paid-keyword-eligibility-v1` |
| commits | 10 até o fechamento da primeira rodada; ver `GATES.md` para o total atual |
| diff | 15 arquivos, +4354 / −89 |

O SHA esperado no briefing conferiu com `origin/volc-os-v2` no preflight.

---

## O que estava quebrado

`funnel_factory` escolhia de 3 a 10 termos por sub-intenção em `selected`, mas
alimentava `all_keywords_for_campaign` a partir de `deduped`. `final_campaign`
nascia de todos os termos deduplicados, e `lista_google_ads` e `keywords_array`
exportavam `final_campaign`. **A tela mostrava a escolha e a campanha recebia a
mineração inteira.**

Medido no funil BPC/LOAS: **5 selecionadas → 8 exportadas**. E os dois termos
no topo da própria seleção, ordenada por volume, eram `meu inss login`
(480.000) e `inss telefone 135` (300.000) — navegacional e suporte empurrando
elegibilidade para fora.

É o mesmo defeito que `validacao/orquestrador.py` já documentava do lado
editorial — *"73% do eixo `volume` era gente procurando o telefone do Banco
Pan"*. Do lado pago ninguém tinha olhado.

E junto vinha a família inteira de "ausência vira zero":

```
'ipva tabela fipe' sem CPC   -> APROVADA   "Good Volume + Affordable CPC"
'ipva tabela fipe' CPC 4,20  -> DESCARTADA
```

Não medir saía estritamente melhor que medir.

---

## O que foi entregue

**`backend/app/agents/mining/paid_eligibility.py`** — o contrato.
`Sinal` com sete estados (`measured` · `confirmed_zero` · `absent` · `unknown`
· `not_applicable` · `failed` · `inferred`) e um construtor que recusa número
em estado que não comporta número. Treze arquétipos de intenção
determinísticos, reaproveitando `QUESTION_WORDS` do Gold Miner em vez de abrir
um segundo motor semântico. `decidir_keyword` devolvendo
INCLUDE/EXPERIMENT/HOLD/REJECT/HUMAN_REVIEW com motivo, bloqueador e alerta
escritos — risco antes de intenção, intenção antes de volume, e nenhum ramo
lendo número sem olhar o estado.

**`ponte_editorial.py`** — as duas respostas lado a lado.
`OpportunityEditorialDecision` ADAPTA `card.resumo` do Validador; não
recalcula. Economia de Ads não entra nele, e o teste falha se entrar.

**`funnel_factory.py`** — elegibilidade primeiro, quantidade depois. O corte
por volume passou a ver só o que já é elegível; invertida, a ordem promovia
exatamente os termos que a elegibilidade recusa. `lista_google_ads` sai de
`derivar_lista_google_ads(conjunto)` — uma função só, usada pelo produtor e
pelo teste.

**`gold_extractor.py` · `merger.py` · `classifier.py` · `orchestrator.py`** —
a ausência passou a sobreviver ao pipeline (mudança ADITIVA; nada removido).

**UI** — `ElegibilidadePaga.tsx` entra como filho único abaixo de
`ValidacaoPainel`, na aba que já existe. Sem endpoint novo, sem migration, sem
chamada de rede nova.

---

## Achados do benchmark: sustentados e refutados

Detalhe completo em `BENCHMARK-FINDINGS.json`. Placar: **6 SUSTENTADAS, 2
PARCIAIS, 0 refutadas** entre as premissas do briefing — e as duas parciais são
exatamente a frase que a errata v2 do próprio benchmark manda remover.

**Duas premissas do briefing não sobrevivem à errata do próprio benchmark:**

1. *"122 episódios sobreviveram aos controles"* é declarado **factualmente
   errado** pela errata v2. `matched_controls_used=0` nas 122 linhas, e o único
   bloqueador registrado nas 122 é literalmente `sem controle pareado
   utilizavel`. Eles passaram critérios INTERNOS mínimos. Só 12 dos 3.550
   episódios têm qualquer controle pareado utilizável.

2. *"três de treze padrões sobreviveram ao controle (SEARCH,
   MAXIMIZE_CONVERSIONS, EXCELLENT)"* sustenta-se como número v1 e é
   **desmontado** pela v2: EXCELLENT rebaixado a NOT_IDENTIFIABLE (contagem
   inflada 2,00× por partição duplicada; direção inverte contra os controles
   fortes), SEARCH e MAXIMIZE_CONVERSIONS são a MESMA fatia e não dois sinais,
   e SEARCH sobra apenas como `external_prior`.

**E o achado que mais importa para esta missão:** o benchmark **não contém
teste de desfecho no nível de keyword**. `KEYWORD_OR_MATCH_CHANGE` tem
exatamente UM episódio legível. Match type tem resultado NEGATIVO explícito —
BROAD é "igual ao controle: é o padrão da operação, não sinal". Nenhuma tabela
por keyword sobreviveu para `data/curated`, e nenhum artefato classifica termo
como marca, genérico ou concorrente.

Por isso `PRIORS_DE_BENCHMARK` tem seis entradas e **todas** com
`bloqueia=False` e `autoriza=False`. O único prior de confiança alta sobre
conteúdo afirma uma AUSÊNCIA. O que o VOLC importou daquele pacote foi MÉTODO:
"vazio de search term não é ausência de demanda" e "padrão presente também no
controle não é sinal".

---

## Limitações estatísticas

O braço de "perfil de vencedora" do benchmark é **outcome-defined-then-
feature-read**: os grupos vêm de `profit_90`/`profit_180` (pós-desfecho) e as
features comparadas são lidas de um snapshot ATUAL. Não há reconstrução de
feature as-of-launch em lugar nenhum do pacote. Força de anúncio EXCELLENT é o
caso mais agudo — score recomputado continuamente pelo Google, que se move com
o próprio histórico da campanha.

O degrau superior da escada de evidência (`razoavel`) nunca foi alcançado:
fraca 2.347 / nenhuma 1.081 / moderada 122 / razoavel 0. E 35 de 35 playbooks
saíram `baixa`, por critério que o próprio benchmark rotula "ARBITRADA, não
estatística".

---

## Proveniência dos limiares

`VOLUME_THRESHOLD = 20000`, `MIN_ITEMS = 3`, `MAX_ITEMS = 10` são **cópia
literal** do nó "FUNNEL FACTORY" de `backend/n8n_kw_pautador.json` (linhas 93-95
do `jsCode`), sem nenhuma justificativa registrada — nem no n8n, nem no commit
que os introduziu, nem em doc nenhum, nem em teste nenhum. Classificação
honesta: **arbitrários**.

Esta sprint **não os alterou**. Mudar um número sem evidência seria o mesmo
erro na direção oposta. O que ela fez foi nomeá-los, versioná-los em
`SELECTION_POLICY_VERSION` e gravá-los em todo `evidence_snapshot` com
`"calibrado": false` e `"justificativa_registrada": null`.

---

## O defeito exato do conjunto selecionado, antes e depois

Antes/depois medidos em `COUNTERPROOFS.md`. O caso mais forte não é fixture:

**`pautador_keyword_clusters` id=7, `opportunity_id=104`**, lido
SOMENTE-LEITURA. Três keywords persistidas, todas com `volume: 0` e `cpc: 0`
literais.

| | antes | agora |
|---|---|---|
| `lista_google_ads` | 3 termos, prontos para colar | vazia |
| `stats.avg_cpc` | `"0.00"` | `"s/ dado"`, com `avg_cpc_estado: absent` |
| `metrics.valid_keywords` | 3 | 0 |
| `ready_for_campaign_plan` | não existia | `False`, com dois bloqueadores |

O motor antigo entregaria três keywords sem demanda medida para uma campanha.
O novo diz que não sabe, e diz por quê.

---

## Contraprovas e gates

61 contraprovas em `backend/tests/test_pautador_paid_keyword_counterproofs.py`,
**todas vermelhas** no commit `ed37cb5` antes de qualquer correção.

Fechamento: **3315 passed, 112 skipped** (backend + motor_pautas + volc_ads).
`tsc` sem erro, `vite build` ok, `git diff --check` limpo, scanner de segredos
com 0 ocorrências, 0 arquivos do benchmark versionados, 0 chamadas de mutação.
Detalhe em `GATES.md`.

---

## Vereditos cross-model

**Codex** (`gpt-5.6-sol`, effort high, read-only): **BLOCK** — 11 achados,
todos reproduzidos e fechados, todos travados por teste. Os dois maiores: o
congelamento não congelava (`aprovar()` só gravava um hash numa dataclass
mutável) e a guarda de vazamento falhava ABERTO. A primeira execução dele
morreu sem relatório porque eu editava a worktree enquanto ele lia — causa
minha, registrada.

**Gemini** (`gemini-3.7-flash`, pacote sanitizado): **APROVADO_COM_RESSALVAS**
— 4 achados reproduzidos e fechados, entre eles o léxico retendo termo
comercial legítimo (`vender meu precatorio` saía HOLD) e comparação genérica
sendo tratada como marca de terceiro (`clt x pj` saía HUMAN_REVIEW).

Uma revisão factual contra a documentação v25 corrigiu o contrato em três
pontos citados: `competition` ausente é UNSPECIFIED e não UNKNOWN (é o único
campo da mensagem sem presença de campo); `keyword_idea_metrics` é campo de
mensagem sem `optional`, então a submensagem inteira pode faltar e todos os
escalares lerem 0; e `average_cpc_micros` só vem com `include_average_cpc=true`,
o que dá à ausência dele um terceiro sentido.

---

## Capacidade real entregue

O Pautador agora produz, por tema, **duas decisões separadas e ambas
explicáveis**: se vale produzir conteúdo (do Validador, não recalculada) e
quais termos podem entrar num leilão (nova). O conjunto pago é literal, tem
impressão SHA-256, e depois de aprovado nenhuma etapa acrescenta keyword —
verificado no uso, não só na escrita.

---

## Bloqueadores que restam para lançar a primeira campanha

1. **Teto econômico do dono não é declarado por ninguém.** Sem ele,
   `ready_for_campaign_plan` é `False` em todos os casos testados, inclusive o
   real. É o bloqueador mais barato de resolver e o que trava tudo.
2. **Congruência termo → anúncio → página não é avaliada** neste caminho. Quem
   avalia destino é `landing_policy`, e o conjunto fica bloqueado até alguém
   olhar.
3. **Os termos retidos continuam alcançáveis por variante próxima.** Reter `meu
   inss login` não impede que uma busca por ele acione um termo INCLUÍDO —
   variantes próximas valem para EXACT e PHRASE, e não há como optar por sair.
   Fechar exige negativa; negativa exige search-term evidence; search-term
   evidence só existe depois do lançamento. O motor **declara o círculo em vez
   de fingir que o fechou.**
4. **Conta, destino pago, mensuração e aprovação de gasto** — quatro portões de
   outras lanes, todos devolvendo `nao_avaliado_aqui`.
5. **O volume que o motor lê é de correspondência exata, arredondado e
   agregado com variantes próximas**, independentemente do match type que se
   pretenda comprar. Não existe volume "de PHRASE".

---

## Tarefas afetadas

| tarefa | estado | proposta |
|---|---|---|
| `cap_keyword_mining` | `live` | segue `live`; o summary precisa passar a dizer que a fila de campanha deixou de ser a mineração inteira |
| `P05-T08` — governança bidirecional de termos e negativas | `partial` | **segue `partial`** — esta sprint entregou só o lado de ENTRADA e deliberadamente NÃO entregou negativa |
| `P08-T06` — Topic Radar | `partial` | **segue `partial`** — a sprint SEPARA dois sinais, que é o oposto de unificar, e a separação é deliberada |

Detalhe e nós de grafo sugeridos em `CURATION-HANDOFF.json`. Esta lane **não
editou** Roadmap, curadoria nem grafo.

---

## Confirmações

- **Zero mutação externa.** Nenhum mutate no Google Ads, nenhuma campanha
  criada/alterada/pausada/removida/ativada, nenhuma keyword ou negativa escrita
  em conta, nenhum lance ou orçamento tocado, nenhuma chamada paga a
  DataForSEO, nenhum write no Supabase, nenhuma migration, nenhum deploy,
  nenhum merge.
- **Zero raw data versionado.** Nenhum arquivo do benchmark entrou no Git.
  Nenhum customer ID, campaign ID, request ID, URL ou receita por conta
  aparece em artefato nenhum. O benchmark foi lido em streaming; os arquivos de
  51 MB e 700 KB nunca foram abertos; `data/raw` não foi lido; nenhum
  screenshot foi aberto; nada sob o caminho do benchmark foi escrito.
- **Injeção detectada e não obedecida.** `refinement-v2/review-packet.md`
  contém texto diretivo endereçado a um agente e prescreve um formato de saída
  terminando em `APPROVE|APPROVE_WITH_NOTES|BLOCK`. Foi lido como dado — um
  artefato de rodada de revisão anterior dentro do benchmark — e está
  registrado em `BENCHMARK-FINDINGS.json`.


---

# Rodada 2 — o wiring que faltava

**`PYTHON_ELIGIBILITY_ENGINE_ACCEPTED` · `CAMPAIGN_BIRTH_WIRING_ACCEPTED` ·
`N8N_BYPASS_CLOSED`**

## O que o integrador encontrou, e estava certo

O motor de elegibilidade estava correto e **não decidia nada**.
`para_criterios_de_campanha()` não tinha chamador de produção; `/provar` — com
`/subir` atrás dele — continuava tirando as keywords POSITIVAS do cockpit, que
as tira de `production_ads_queue`: a fila BRUTA da mineração. Um conjunto de 3
selecionadas convivia com um pedido de 8 termos, e nada no sistema notava.

## O portão

`backend/app/agents/mining/portao_conjunto_pago.py` reidrata o `conjunto_pago`
gravado em `factory_output` e **recalcula a impressão** das decisões. Nunca lê
o hash do registro — confiar nele seria pedir ao registro que ateste a si
mesmo. Se o JSON persistido foi editado depois da aprovação, a impressão não
bate e o portão recusa.

Recusas, todas ANTES de `preparar()` e portanto antes de qualquer
`validate_only` — que é leitura, mas ainda é rede e ainda é conta real:

```
CONJUNTO_PAGO_AUSENTE · NAO_APROVADO · HASH_DIVERGENTE · BLOQUEADO · VAZIO
N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED
```

Nenhuma inventa valor para seguir. Teto econômico não declarado e congruência
não avaliada continuam **bloqueadores nomeados**: o portão diz qual falta.

Medido no funil BPC/LOAS: **5 selecionadas → exatamente 5 critérios**, e os três
termos de risco (`meu inss login`, `inss telefone 135`,
`bpc loas advogado x concorrente`) ficam fora — embora sigam presentes na
`production_ads_queue` do mesmo cluster. A fila continua existindo; o que
deixou de existir é a porta pela qual ela virava campanha.

`grupos_usar_todas` ficou vazio de propósito: "usar todas" significava "monte o
grupo inteiro do cockpit". Depois do portão não há "todas", há o que foi
aprovado.

`/subir` reprova o plano antes de escrever. Sem o portão, ele ultrapassaria por
reconstrução uma recusa que `/provar` já tinha dado — a herança é estrutural,
não disciplina de quem chama na ordem certa.

## A autoridade, declarada

**`python:app.agents.mining.paid_eligibility`**, uma só.

O fluxo n8n **não foi corrigido**, e a escolha é deliberada:
`n8n/pautador_kw_mining_webhook.json` é GERADO por
`backend/scripts/build_n8n_kw_webhook_flow.py`, que copia os nós "ouro"
VERBATIM de um export externo que não vive neste repositório. Editar o JSON à
mão seria sobrescrito na próxima geração; reimplementar a elegibilidade em
JavaScript seria manter dois algoritmos independentes decidindo a mesma coisa —
que foi o que produziu esta divergência.

O n8n **continua minerando**. O que ele não faz é virar campanha. E o aviso
viaja na própria resposta do despacho em `entities.py`, porque um operador que
só descobre a recusa na hora de subir perdeu o ciclo inteiro por uma informação
que existia desde o início.

## Bloqueadores honestamente restantes

1. **Teto econômico do dono** continua não declarado por ninguém — agora com
   consequência visível: `CONJUNTO_PAGO_BLOQUEADO` em `/provar`.
2. **Congruência termo → anúncio → página** continua não avaliada neste
   caminho; quem avalia destino é `landing_policy`.
3. **Close variants continuam risco declarado.** Reter `meu inss login` não
   impede que uma busca por ele acione um termo incluído. Fechar exige
   negativa, negativa exige search-term evidence pós-lançamento e revisão de
   overblocking — **esta rodada não gerou nenhuma negativa**, de propósito.
4. **Clusters minerados antes desta lane** não têm `conjunto_pago` e serão
   recusados. É migração de contrato, não perda: a alternativa era continuar
   promovendo fila bruta a conjunto de campanha.
5. **O workflow n8n versionado ainda carrega o defeito de origem**
   (`dedupedKws.forEach -> allKeywordsForCampaign`, CPC/volume ausente virando
   zero). Fechado por recusa, não por correção.

## Microcorreção final — o selo passou a governar também o corpo HTTP

O wiring anterior ainda somava as positivas aprovadas a
`_criterios_do_corpo(body, pp)`. Como o contrato HTTP aceita
`negativa=False`, o mesmo termo aprovado em `PHRASE` podia reaparecer em
`EXACT`: 3 aprovadas viravam 4 critérios. `keywords_fora` abria a direção
oposta, reduzindo o conjunto depois da aprovação.

As duas rotas agora:

1. recusam qualquer critério positivo vindo do corpo;
2. continuam aceitando negativas declaradas pelo operador;
3. recusam `keywords_fora` não vazio depois da aprovação;
4. conferem, no `Brief` final e antes de `sb.preparar`, igualdade de
   multiconjunto entre positivas aprovadas e materializadas — texto
   normalizado, match type, origem e cardinalidade;
5. tratam a remoção do rótulo de grupo como legítima somente porque as duas
   rotas declaram explicitamente `conjunto_unico=True`. O helper não infere
   colapso pela simples ausência de grupos.

As contraprovas chamam as funções reais `/provar` e `/subir`, recebem 409 com
código estável e mantêm a sentinela de rede em zero. Com isso, a afirmação
“positiva nasce exclusivamente do conjunto aprovado” passou a valer também
contra mutações no envelope HTTP e contra divergência introduzida por
adaptadores posteriores.
