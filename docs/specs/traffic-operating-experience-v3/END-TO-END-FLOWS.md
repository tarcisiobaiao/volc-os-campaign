# END-TO-END-FLOWS — Search, Display, Demand Gen e Performance Max, do início ao fim

Base factual: `207e91f`. Cada fluxo descreve **a capacidade real observada**, não a desejada.

**A regra que governa o arquivo:** nenhum fluxo tem etapa que não exista. Onde o caminho termina, ele termina — com a causa, a origem e o próximo desbloqueio nomeados.

**Vocabulário dos atos**, e a diferença entre eles:

| Ato | O que é | Rota | Muda a conta? |
|---|---|---|---|
| **planejar** | montar o grafo offline | nenhuma | não |
| **provar** | `validate_only` contra a conta real | `POST /provar` | **não** — "leitura para todos os efeitos" (`trafego.py:2879-2884`) |
| **aprovar** | ato humano: motivo ≥10 + caixa PAUSADA | — | não |
| **criar pausada** | `mutate` real | `POST /subir` | **sim** |
| **ativar** | despausar | ⚠️ **não existe** | — |
| **reconciliar** | ler a conta e fechar o recibo | `POST /reconciliar` | não — **nunca reenvia** |

---

## 0. Entrada comum a todos os fluxos

**Pré-condições, verificadas antes de qualquer parada:**

| Pré-condição | Fonte | Se faltar |
|---|---|---|
| sessão válida | `exigir_usuario` no `APIRouter` (`trafego.py:101`) | 401; a rota nasce fechada |
| projeto com conta vinculada | `cockpit.conta.vinculada` | a Bancada não abre; a antessala explica |
| oportunidade com cluster | `GET /candidatos/{id}` | erro do cockpit |

⚠️ **A conta não é escolha do operador.** `types/trafego.ts:150` — *"a conta vem do PROJETO, não do operador"*. Nenhuma parada pergunta a conta.

⚠️ **Abrir sem `?run=` muda o significado entre duas rotas:** o cockpit trata `run_id` ausente como "o mais recente" (`trafego.py:785`); a leitura da copy trata como `run_id IS NULL` (`:1023`). A Bancada **sempre** resolve `run` na entrada e o carrega na URL.

---

## 1. SEARCH — o único fluxo desenhado para chegar ao fim

**Capacidade real:** planeja, prova, cria pausada. Não ativa.

> 🔴 **BLOQUEANTE, e este fluxo não é executável sem ele.** `/provar` recusa antes da rede quando o conjunto pago não está **aprovado** (`portao_conjunto_pago.py:158-163`, código `NAO_APROVADO`). E **nada no sistema aprova**: `approved_set_sha256` só é atribuído dentro de `paid_eligibility.aprovar()` (`:1179`) ou reidratado de um dicionário que já o tenha (`:883`) — e `aprovar()` **não tem chamador de produção** (`grep` por chamadas → apenas a menção em docstring `:1276` e um `job.aprovar` de outro domínio). `funnel_factory.py:387-391` persiste o conjunto **sem aprovar**.
>
> **Consequência:** no caminho normal descrito abaixo, `/provar` termina em **409 `NAO_APROVADO`** e a campanha não nasce. O fluxo só fecha para um conjunto cujo dicionário persistido já carregue o hash — condição que este repositório não produz por nenhum caminho observável.
>
> A fatia **A0** (`IMPLEMENTATION-SLICES.md`) existe para fechar isso, e **B–I dependem dela**. Registrado como `Q5` promovida a bloqueante em `DECISION-LOG.md §8`.

```
preparar → Bancada(6 paradas) → Revisão → Ignição(destino→copy→prova→escrita) → Recibo
                                                                        └─ 504 → indeterminado → RECONCILIAR
```

### 1.1 Paradas

| # | Parada | Entrada | Evidência ao lado | Ato read-only | Bloqueia? |
|---|---|---|---|---|---|
| 1 | Destino | recibo de landing policy | 5 perguntas, completude da evidência, deriva ao vivo, janela de 24h | reauditoria ao vivo ⚠️ *(a prop existe e nenhum chamador a passa)* | **sim** — único que para tudo sem gastar |
| 2 | Política | `GET /politica/verticais` | severidade por país, o que a vertical exige | — | **deve** — hoje não (§1.5) |
| 3 | Termos | `GET /candidatos/{id}` | elegibilidade, volume, CPC minerado com ressalva, régua de leilão | — | não |
| 4 | Anúncio | `GET`/`POST /copy` | mínimos do RSA, congruência termo→anúncio→página | gerar copy (assíncrono) | não |
| 5 | Economia | manifesto + `GET /trava` | 7 portões, moeda, fuso, meta efetiva, teto do dia | — | sim, via portão de lance |
| 6 | Revisão | tudo acima | o pedido inteiro + bloqueios do servidor | — | — |

### 1.2 A Ignição, degrau a degrau

| Degrau | Ato real | Chamada | Onde para |
|---|---|---|---|
| `destino` | veredito derivado da prop | **nenhuma** | destino não apto ⇒ **zero requisições saem** (`Lancamento.tsx:88-90, 132-135`) |
| `copy` | ⚠️ hoje literal `ok` (`:299`) | nenhuma | **deve** poder reprovar |
| `prova` | `validate_only` | `POST /provar` | teto de **120s** (`TIMEOUT_PROVA_S`, `trafego.py:111`); **uma** requisição, sem subfase |
| `escrita` | `mutate` | `POST /subir` | 409 sem selo; 409 se a impressão divergir |

**O que `/provar` devolve:** `preparo`, `avisos`, `grupos`, `autorizacao`, `destino`, `prontidao` — com `ativacao_incluida: false` explícito (`:3182`). Destino inelegível ⇒ **selo retido**, `plano_impressao` zerado e `selo_retido.motivos` (`:3147-3149`). Sem selo, `/subir` recusa por construção.

**O que `validate_only` cobre e não cobre** (`comum.md:102-123`):

| Cobre | Não cobre |
|---|---|
| forma do request | não devolve IDs reais |
| política | algumas operações o rejeitam (v25.1 acrescentou `VALIDATE_ONLY_GENERATE_PMAX_NOT_SUPPORTED`) |
| | ⚠️ **não existe lista oficial e exaustiva do que ele deixa passar** — a matriz registra a busca e **proíbe preencher por memória** (`fontes.json:946-1130`) |

A Bancada diz isso com essas palavras: *"a prova confere a forma do pedido e a política. Ela não garante que a criação vai passar."*

### 1.3 As três travas da criação

Todas repetidas no servidor:

| Trava | Cliente | Servidor |
|---|---|---|
| motivo ≥10 caracteres úteis ⚠️ | `Lancamento.tsx:561-565` (`.trim()`) | `field_validator` (`trafego.py:3416-3423`) **e** `_exigir_motivo` (`volc_ads/subir.py:936`) — as três usam `strip` |
| caixa "somente PAUSADA" | `:552-560` + segundo `return` em `escrever()` (`:174-177`) | `CanarioRecusado` (`canario.py:147-151`) |
| impressão do pedido | enviada | recalculada e comparada; divergência ⇒ 409 (`trafego.py:3637-3645`) |

⚠️ **O status PAUSED não é negociável pelo cliente.** `SubirEntrada` **não tem campo de status** (`:3398-3431`): não há como pedir outro. O `PAUSED` efetivo é literal do construtor (`volc_ads/campanha/comum.py:207`), e a linha no Postgres nasce `"status": "Paused"` e `"google_ads_status": "PAUSED"` (`trafego.py:5318-5319`).

⚠️ **A trava do motivo nasce satisfeita.** `Lancamento.tsx:99` pré-preenche o campo com `lançamento de "${titulo}"` — 17 caracteres para um título de um. As três guardas de 10 caracteres existem, são medidas em três lugares independentes, e **nenhuma delas pede algo de alguém**. O motivo que vai para o recibo é, por padrão, uma frase da máquina. A Bancada nasce o campo **vazio**, com a exigência escrita ao lado.

E `/subir` **reavalia o destino ao vivo** em vez de confiar no selo: com o mesmo payload e a mesma impressão, um destino trocado depois da prova produz **409 `DERIVA_AO_VIVO`** (`test_barreira3_destino_de_campanha.py:667-677`).

### 1.4 Os quatro desfechos, e o que a tela faz

| Desfecho | Recibo | Ação oferecida |
|---|---|---|
| **409 `NAO_APROVADO`** (antes da rede) | nenhum | 🔴 **hoje é o desfecho do caminho normal.** A tela diz que o conjunto não foi aprovado e **quem aprova** — e não oferece "tentar de novo", porque repetir dá o mesmo 409 |
| `sucesso` | completo, com `id_externo` | ler o recibo; abrir a campanha |
| `erro` → item `falhou` | com código | **reentrável**: corrigir e provar de novo |
| `sem_resposta` → item `indeterminado` | parcial | ⚠️ **reconciliar** — hoje só existe a frase |
| `em_voo` | `registrado: false` | reconciliar; **nunca** ler como sucesso |

**Por que o indeterminado é inevitável:** `comum.md:151-154` — **a API não oferece chave de idempotência** — varredura por `idempotent`/`idempotency` em 70 páginas oficiais retornou zero, com marca de confiança **`[media]`**: alta para o corpus varrido, e o próprio doc ressalva que não é prova de inexistência universal. Um timeout depois do envio é genuinamente ambíguo.

⚠️ **E `partial_failure` não salva:** IDs temporários e `partial_failure` são **mutuamente excludentes por regra oficial** (`comum.md:138-142`), o que o torna inutilizável em criação de estrutura nova com referências temporárias. **A generalização tem exceção:** para Display a matriz registra que **não há exigência oficial de atomicidade** e que `partial_failure` **é utilizável**, salvo quando o request usa IDs temporários (`display.md:46-48`).

### 1.5 Os cinco defeitos deste fluxo que a Bancada corrige

| # | Hoje | Depois |
|---|---|---|
| 1 | `podeLancar` derivado no navegador | `bloqueado`/`bloqueios` do servidor |
| 2 | a Política **não barra** o lançamento (`NovaCampanhaPage.tsx:332-343`) | o veredito de política é pendência do servidor |
| 3 | a tela envia **positivas** e o portão as recusa fechadas | a Bancada envia **só negativas e correspondências** |
| 4 | o degrau `copy` é literal `ok` | lê o estado real |
| 5 | o recibo morre no fechamento do modal | região retornável, com motivo e impressão |

### 1.6 Depois da criação — e o silêncio que vem junto

`sucesso` **não** significa entrega. Três fatos:

1. `campaign.status` é o **único** dos três campos de estado que é gravável; `serving_status` e `primary_status` são *Output only* (`comum.md:338-344`). **Ler `status = ENABLED` não prova entrega.**
2. O coletor contínuo **não alcança PAUSED**: filtra `estado_externo = ENABLED` e `canal = SEARCH` (`volc_ads/inteligencia_google/persistencia.py:77-90`).
3. O coletor que lê PAUSED **existe** (`campanha_por_identidade`, `:111-119`) e **não tem rota HTTP** — só CLI; e `alvo.py:19-23` declara que a autoridade de agenda nunca foi escolhida.

**Consequência medida:** o espelho tinha **zero linhas** para a campanha canário nascida PAUSED (`contrato_canais.py:492-504`).

O Recibo diz isso: *"esta campanha nasceu pausada. O coletor contínuo não alcança campanhas pausadas; a releitura por identidade existe e ainda não tem agenda."* **Não é falha — é o preço da segurança, e o operador precisa saber.**

### 1.7 A janela do canário

`SEARCH` + conta **547-809-6539** (Portal Mundo Mais) + MCC 6016739364 (`canario.py:25-34`). Fora dela, `criavel_pausada` fecha com `fora_da_janela_do_canario`, origem **política**.

| Teto | Valor | Natureza |
|---|---|---|
| orçamento diário | R$ 20,00 | **por pedido** |
| CPC inicial | R$ 1,00 | **por pedido** |
| rede | Search Partners e expansão para Display **recusados** | por pedido (`:164-181`) |

⚠️ `canario.py` **não tem conceito de exposição acumulada**: `grep -niE 'acumulad\|exposicao\|30.4'` → **0**. Não há soma sobre dias, não há leitura de custo real, não há gatilho de aborto. A tela **não** promete um teto acumulado que o sistema não vigia; ela mostra a aritmética e diz que a vigilância é humana.

---

## 2. DISPLAY — prova sim, cria não

**Capacidade real:** planeja, prova, **não cria** — por **política**, não por falta de construtor.

⚠️ **Correção de escopo, e ela resolve uma contradição entre artefatos.** O caminho abaixo é o **alvo da fatia J**, não o comportamento de hoje nem de B–I. Hoje o pedido da página é `PedidoDeProvaSearch` com `canal: 'SEARCH'` literal (`NovaCampanhaPage.tsx:384-414`), e `canal/jornada.ts:645-646` reconhece que não existe formulário para os outros canais. **Até J existir, Display recebe a escada de portões e o CTA "preparar por Search"** — que é o que `SCREEN-CONTRACTS.md §3` e a fatia J especificam. A Bancada de Display é trabalho de J, e J a nomeia.

```
(alvo da fatia J) preparar → Bancada(6 paradas, Anúncio = assets) → Revisão → prova → ⛔ PARA
(hoje e até J)    antessala → escada de 4 portões → CTA "preparar por Search"
```

| Portão | Estado | Bloqueador | Origem |
|---|---|---|---|
| `planejavel` | PERMITIDO | — | — |
| `validavel` | PERMITIDO | — | — |
| `criavel_pausada` | **BLOQUEADO** | `fora_da_janela_do_canario` — **um dos três** bloqueios possíveis do ramo `else` | **politica** |
| `ativavel` | BLOQUEADO | 4 razões | 4 origens |

⚠️ **Correção de leitura.** O construtor de Display **existe e chega a `pode_criar=True`**: monta budget → campanha DISPLAY → geo → idioma → ad group → responsive display ad (`volc_ads/campanha/display.py:676-684`), e o manifesto declara **prova e mutação real verdadeiras** com 5 indisponibilidades que descrevem o que a **primeira fatia** não monta (`plataforma.py:373-405`). O impedimento do portão é a **janela do canário**, que cobre só SEARCH.

A causa que a tela mostra **nomeia a conta e diz que o construtor está pronto** (`contrato_canais.py:946-957`) — porque "não posso ainda" e "não sei fazer" pedem coisas diferentes. ⚠️ Display só sai com **esse código único** quando a escrita está aberta e o portão `validavel` está aberto; nos outros ramos o bloqueador é outro (`test_trafego_contrato_canais.py:701-704`).

**Próximo desbloqueio:** ampliar a janela do canário para incluir DISPLAY, **ou** declarar por que ela não será ampliada. Dono: **política**.

**Travas duras que a parada Anúncio precisa respeitar:**

| Trava | Fonte |
|---|---|
| **não existe guia oficial** de criação de campanha Display na API — varredura de 308 URLs de guia confirmou (`display.md:12-18`); e a especificação de criativo do RDA **só existe no proto** (`display.md:25-27`) | — |
| placement positivo tem **duas fontes oficiais que se contradizem**; a matriz recomenda resolver com `validate_only` antes de codificar | `display.md:196-205` |
| anúncios HTML5 têm **gate de CONTA** (AMPHTML, ou gasto > US$ 9.000 **e** > 90 dias, ou allowlist) — não é trava de código | `display.md:141-146` |
| a mesma trava de `campaign.status` de Search vale aqui, com a mesma marca de confiança | `display.md:70` |

A tela **não** oferece HTML5 sem antes dizer que é um gate de conta que ela não pode abrir.

---

## 3. DEMAND GEN — prova por porta estreita, nunca cria

**Capacidade real:** planeja, prova **atrás de flag**, não cria.

```
antessala → escada de 4 portões → (flag ligada) prova → ⛔ PARA
```

| Portão | Estado | Bloqueador | Origem |
|---|---|---|---|
| `planejavel` | PERMITIDO | — | — |
| `validavel` | **BLOQUEADO** | `demand_gen_experimental_desligado` | **servidor** |
| `criavel_pausada` | **BLOQUEADO** | `mutacao_real_recusada` | **manifesto** |
| `ativavel` | BLOQUEADO | 4 razões | 4 origens |

**A porta experimental** exige **duas** coisas: flag durável **E** sonda local do SDK v25. Ausência, erro de grafia ou qualquer valor diferente de `on` mantêm a superfície fechada (`capacidades.py:134-140`).

⚠️ **A recusa é dura e vem cedo.** `POST /subir` recusa `DEMAND_GEN` com **403 antes** de escopo, canário, ponte, trava e mutate (`trafego.py:3483-3491`). E o cliente HTTP do front aceita **apenas** `PedidoDeProvaSearch` em `subirCampanha` (`pautadorApi.ts:881-887`): pela assinatura, Demand Gen pode ser provado e **não** subido.

**A Bancada não abre por formulário.** A antessala mostra a escada, a causa de cada recusa com origem, e o CTA correto — que é **"preparar por Search"**, não um formulário morto.

**Invariante travado:** Demand Gen com a capacidade estreita ligada expõe a prova HTTP e **continua sem cockpit e sem escrita** (`canal/__tests__/jornada.test.ts:178-188`).

**O que a API permite e não permite** (`demand-gen.md`):

| Permite | Não permite |
|---|---|
| ordem oficial de criação em **cinco passos**, com atomicidade **recomendada** (não obrigatória, ao contrário de PMax) (`:29-34`) | orçamento compartilhado (`:46`) |
| | `ad group` com `type_` (`:54`) |
| | diário abaixo de **5 USD** — validado pela API desde 01/04/2026 (`:60-63`) |

⚠️ Trava de reporting: anúncios do tipo legado *Demand Gen video ad* **aparecem na UI e não são retornados por SearchStream** (`:268-270`). Qualquer contagem da tela declara essa lacuna.

---

## 4. PERFORMANCE MAX — planeja, e para antes da prova

**Capacidade real:** planeja offline. **Não prova, não cria.**

```
antessala → escada de 4 portões → ⛔ PARA em `validavel`
```

| Portão | Estado | Bloqueadores | Origens |
|---|---|---|---|
| `planejavel` | **PERMITIDO** | — | — |
| `validavel` | BLOQUEADO | `PMAX_FORA_DO_EXECUTOR` | **produto** |
| `criavel_pausada` | BLOQUEADO | `PMAX_FORA_DO_EXECUTOR` **+** `pmax_observabilidade_nao_provada` | **produto** + **observabilidade** |
| `ativavel` | BLOQUEADO | 4 razões | 4 origens |

**Por que `planejavel` abre:** o portão pergunta ao **engine antes do manifesto**, e o engine tem `planejar()` (`contrato_canais.py:781-793`). Quando engine e manifesto discordam, o resultado é **`INDETERMINADO`** com `montagem_indeterminada`, origem `construtor` (`:795-806`) — nunca recusa silenciosa.

**Por que há dois códigos em `criavel_pausada`**, e por que isso importa (`:1538-1560`):

> `PMAX_FORA_DO_EXECUTOR` é uma decisão de produto que alguém pode reverter numa tarde. A observabilidade é um fato sobre o que este sistema consegue **reler**. Se o código fosse único, reverter a decisão tornaria PMax criável **sem ninguém conseguir observar** a campanha depois.

Invariante travado: o teste substitui o manifesto por um que sabe criar e **cobra que o portão continue fechado** (`test_trafego_contrato_canais.py:786-792`).

**A observabilidade exige linhagem específica** — `releitura_do_ledger` — e **recusa veredito autoatestado** pela própria execução, mesmo com `provada=True` (`:1090, 1126-1133`). E a rota `GET /canais` **nunca passa `prontidao_pmax`** (`trafego.py:5512-5516`), então na prática ela sai `INDETERMINADO` em toda resposta HTTP.

### 4.1 A expansão de URL — a trava que a tela não pode prometer errado

⚠️ **`Campaign.url_expansion_opt_out` NÃO existe na v25.** A prova é por introspecção do proto instalado (`docs/closure/traffic-creative-operational-closure-v1/verificacao/REVISAO-GEMINI-CONTRATOS.md:74`), e o módulo de observabilidade declara por escrito que a query não seleciona o campo inexistente (`docs/architecture/HANDOFF-PMAX-OBSERVABILITY-V25.md:13-16`).

⚠️ **Correção de procedência:** esta trava **não está** em `docs/growth-engine/`. `grep` na matriz-api → nenhuma menção ao campo. Ela vive nos dois arquivos acima.

**O controle real, em duas partes:**

| Parte | O que é | Fonte |
|---|---|---|
| 1 | **critério `webpage` negativo** é o mecanismo de exclusão — e a final URL do próprio asset group **não pode** ser excluída por ele | `performance-max.md:186-187` |
| 2 | **`asset_automation_settings`**: lista de pares (tipo, `OPTED_IN`/`OPTED_OUT`), **12 tipos** no SDK v25, com dependência que **gera erro se invertida** | `:202-215` |

Enquanto PMax não passar de `planejavel`, a tela **não** oferece controle de expansão. Quando passar, a parada é construída sobre esses dois mecanismos — **nunca** sobre o campo inexistente.

### 4.2 Outras travas de PMax

- `partial_failure` é **explicitamente não suportado** na criação de asset group, e a atomicidade é exigida no mesmo bulk mutate (`performance-max.md:33-37, 43-44`).
- Os papéis de asset lidos pelo contrato são **cinco**, de `PAPEIS_DE_ASSET_PMAX` no brief — **o único canal cuja lista não vem de `perfil.py`** (`brief.py:1032-1038`).
- ⚠️ Defeito conhecido no manifesto: a indisponibilidade declarada ainda afirma que "o engine levanta exceção", **o que deixou de ser verdade** (`plataforma.py:436-447`).

**Próximo desbloqueio:** provar a releitura da estrutura interna (grupos de recursos e assets). **Sem isso, reverter a decisão de produto não abre o portão.**

---

## 5. VIDEO e SHOPPING — fora do contrato

Nenhum dos dois está no contrato de portões (`contrato_canais.py:131`). Existem **só na gramática do frontend** (`canal/jornada.ts:537-603`), e a assimetria é declarada no próprio tipo: `Canal` tem **6** valores e `CanalComManifesto` tem **4** (`types/trafego.ts:1009-1024, 1038-1048`).

| Canal | O que a tela diz | Procedência da afirmação |
|---|---|---|
| **Video** | "observar e analisar" | ⚠️ ver abaixo |
| **Shopping** | "pré-requisito ausente" | ⚠️ ver abaixo |

⚠️ **Correção de procedência — e é uma correção séria.**

A afirmação "a Google Ads API não cria nem atualiza campanha de Video" **não existe em `docs/growth-engine/`**. Não há arquivo de canal para Video nem para Shopping na `matriz-api/` (ela cobre quatro canais), e nenhuma linha declara `advertising_channel_type` de vídeo como não criável.

Onde a afirmação existe: `docs/design/PROMPT-GROK-SPRINT-TRAFEGO-CONTRASTE-E-CRIACAO-POR-CANAL.md:263, 267-271` — **um prompt de briefing de design**. O arquivo **lista a URL oficial de Video** no bloco "Fontes oficiais obrigatórias" (`:97, 129`), então não é correto dizer que a afirmação está sem fonte; o que falta é a **verificação datada contra o proto**, do tipo que a `matriz-api` faz para os outros quatro canais.

O mesmo vale para o pré-requisito Merchant Center de Shopping (`:246, 259`). Na `matriz-api`, a referência é a `ShoppingSetting` (sem `.merchant_id`) em `performance-max.md:19` e `display.md:158`, e como `ShoppingSetting.merchant_id` **apenas** em Demand Gen (`demand-gen.md:231-237`) — **nunca** como campanha Shopping.

Do lado do VOLC, `MATRIZ-DE-CAPACIDADES.md:45` (Video; a `:46` é a de Shopping) registra que o VOLC **inventaria e não lê filhas nem cria** — e a evidência citada é o **manifesto nulo do próprio VOLC**, não um limite declarado da API. Há ainda outras linhas sobre Video em `docs/growth-engine/` (`creative-engine.md:104, 175-177`), então essa também não é a única menção.

**Consequência para a tela.** A frase honesta é sobre o VOLC, não sobre o Google:

> **Video** — "o VOLC inventaria campanhas de vídeo e não as monta. Se a API do Google permite criá-las não foi verificado aqui."
> **Shopping** — "o VOLC não monta campanha Shopping. O vínculo com o Merchant Center é pré-requisito conhecido e não foi verificado nesta base."

**Invariante que já protege isso:** mesmo com um manifesto mentiroso dizendo `sabe_criar: true`, Video **não ganha CTA de criar** — a recusa da API vence (`canal/__tests__/jornada.test.ts:210-222`).

---

## 6. O fluxo de reconciliação

O único fluxo cujo gatilho é uma **falha**.

```
/subir → 504 → SubidaIndeterminada → item `indeterminado`
                                      └→ POST /reconciliar → { achou: true → sucesso | false → falhou | duplicidade → 409 }
```

| Entrada | Regra |
|---|---|
| `item_id` + `customer_id` | obrigatórios |
| `campaign_id` **ou** `marca` | `model_validator` exige um dos dois (`trafego.py:4198-4218`) |

⚠️ **`marca` é o que torna a saída utilizável pelo item que mais precisa dela** — o que **nunca teve id externo** (`:4186-4195`).

**Três proteções que o banco não dá** (`:4497-4522`):

| Situação | Resposta |
|---|---|
| item de outra conta | **409** |
| item inexistente | **404** |
| ≥2 campanhas encontradas | **409 sem carimbar nada**, e a leitura fica registrada com `achou=None` |

**Saída:** `reconciliacao`, `plano_de_mensuracao`, `leitura` + o campo declarativo `reenvio_executado`. A rota **nunca reenvia o mutate** (`:4442-4447`).

O portão de autorização é travado **por comparação com `/subir`**, não contra uma constante — se o portão de subir subir, o teste passa a exigir o novo (`test_trafego_ledger_producao.py:658-667`).

### 6.1 O que falta

**Nada no servidor.** A rota existe, é correta e é testada.

**Tudo no cliente.** `grep -rn 'api/trafego/reconciliar' src/ api/` → **0**. E o produto **manda o operador reconciliar, em texto, sem botão** (`Lancamento.tsx:900-902`), com `proximoAtoSeguro` devolvendo `reconciliar_na_conta` por padrão (`lib/trafego/lancamento.ts:141-147`).

**Contrato alvo:** a região Recibo, no estado `indeterminado`, oferece o ato. E deixa escrito que **reenvio é proibido** (`reenvio_permitido: false` é fixo no tipo) — reconciliar é ler a conta e fechar o recibo, não tentar de novo.

---

## 7. Capacidades inexistentes — a lista fechada

Nenhuma destas ganha formulário, botão cinza ou etapa de progresso.

| Capacidade | Estado | Prova de ausência | Dono |
|---|---|---|---|
| **ativar campanha** | não existe | `grep -rn '"/ativar' backend/` → 0 | produto — ⚠️ **não fechar sem decisão** |
| pausar/despausar por rota | não existe | `grep '@router.post("/pausar'` → 0 | produto |
| alterar lance ou verba | não existe | idem | produto |
| histórico de recibos | não existe | `grep -rn 'router\.get("[^"]*recibo' backend/` → 0 | servidor |
| lotes (`/lotes/{id}`, retomar, cancelar) | não existe | `grep -rn '/lotes/' backend/app/routers/` → 0 — apesar de `lote.py` existir | servidor |
| aprovar proposta | não existe | `grep 'propostas/{.*}/aprovar'` → 0 | servidor |
| `GET /criativos` | não existe | `grep '@router.get("/criativos'` → 0 | servidor |
| criar campanha Video/Shopping | fora do contrato | não estão em `CANAIS` | produto |
| agenda da coleta que alcança PAUSED | não existe | `grep 'APScheduler\|celery'` → 0 | **decisão de autoridade de agenda** |

---

## 8. O próximo ato seguro, por situação

A frase que a tela mostra. Uma por situação, sem sinonímia.

| Situação | Próximo ato seguro |
|---|---|
| destino não apto | "corrigir o destino antes de provar" |
| destino indeterminado | "reauditar o destino ao vivo" |
| vertical fora da matriz | "escolher a vertical, ou pedir a classificação" |
| copy ausente | "escrever a copy — ela ancora nos termos marcados" |
| trava de escrita fechada | "provar agora; criar depende de \<origem\>" |
| prova recusada | "corrigir o que a recusa aponta e provar de novo" |
| prova aprovada | "revisar o pedido e autorizar a criação pausada" |
| criada pausada | "ler o recibo e conferir na conta" |
| **indeterminado** | **"reconciliar na conta — não tente criar de novo"** |
| `em_voo` | "reconciliar; não há recibo registrado" |
| canal sem construtor | "preparar por Search" |
| canal fora da janela | "pedir a ampliação da janela a \<origem\>" |
| capacidade inexistente | **nenhum ato.** O próximo desbloqueio é nomeado, com dono |
