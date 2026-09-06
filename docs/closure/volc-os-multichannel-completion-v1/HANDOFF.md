# Handoff — VOLC OS Multichannel Completion

**Veredito geral:** `MULTICHANNEL_COMPLETION_PARTIAL`

Vereditos por faixa, cada um com a evidência que o sustenta:

> ⚠️ **CORREÇÃO DE 06/09/2026 — o topo deste arquivo dizia que o portão de
> política estava "somente em Display".**
>
> Estava errado desde a rodada 2, e o próprio arquivo se contradizia: a seção
> "Rodada 2" abaixo registra "T12 nos três canais — portão em Display, Demand
> Gen e PMax, antes da ponte e da rede". A linha da tabela de tarefas não
> acompanhou, e é ela que quem abre o handoff lê primeiro.
>
> O fato, medido no código em 06/09/2026: `_recibos_de_politica_das_pecas`
> (`routers/trafego.py`) é chamado nos três montadores — Display (via
> `_imagens_de_display`), Demand Gen e Performance Max — sempre ANTES da ponte
> do Estúdio e antes de qualquer chamada de rede.
> `backend/tests/test_trafego_paridade_multicanal.py::test_o_portao_criativo_roda_antes_da_ponte_em_todo_canal`
> passou a cobrar isso por árvore sintática, canal a canal.

| Veredito | Sustentado? | Por quê |
|---|---|---|
| `META_P0_LOCAL_CONTRACT_ACCEPTED` | **não** | C01 continua aberto. O canário Meta está bloqueado por `shop_redirect_proof`, e o bloqueio é a decisão certa — não a conclusão da tarefa. |
| `CREATIVE_SUPPLY_CHAIN_P0_LOCAL_ACCEPTED` | **parcial** | O núcleo existe e está ligado nos TRÊS canais (⚠️ correção: a versão anterior dizia "ligado em Display", e isso já era falso quando foi escrito — a rodada 2 ligou os três, e a linha de baixo desta mesma tabela dizia isso). Falta o detector de pixel. |
| `GOOGLE_DISPLAY_LOCAL_READY_FOR_REMOTE_VALIDATION` | **não** | ⚠️ **Correção do texto anterior.** Dizer "sim, com ressalva" estava errado: com o portão estrito e sem detector de pixel registrado, NENHUMA peça Display chega ao `validate_only`. Um canal cujo ato seguinte é impossível não está pronto para ele. O payload está provado localmente; a capacidade, não. |
| `GOOGLE_DEMAND_GEN_LOCAL_READY_FOR_REMOTE_VALIDATION` | **não** | T06 não implementado. Só as automações foram fechadas. |
| `GOOGLE_PMAX_LOCAL_READY_FOR_REMOTE_VALIDATION` | **não** | T08 não implementado; PMax segue fora da rota tipada. T09 está inteiro. |
| `MULTICHANNEL_OPERATOR_UI_LOCAL_ACCEPTED` | **não** | A UI não foi tocada. T13 permanece aberto. |

## Base, HEAD e as fontes congeladas

⚠️ **Correção do texto anterior**, que confundia dois SHAs diferentes:

| | SHA | O que é |
|---|---|---|
| Base | `5cb654fbf1dbc226a995b0c60a37310c2aa4eb4c` | ponto de partida da missão |
| **HEAD de runtime** | `dbedab27980237ae6ff93478c3ae67d88dd566bd` | último commit que mudou **código**; é o SHA em que o grafo foi construído e em que as suítes foram medidas |
| **HEAD documental** | `88bf5f1956b6f6ffb8bfe7e6c2a6d2f10bdf5a72` | commit final da rodada, só documentação |

A versão anterior deste arquivo citava apenas `316d211` como "HEAD", que era o
commit de memória — nem o runtime medido, nem o final. Os três são distintos e
cada número responde a uma pergunta diferente.

- Branch: `execution/volc-os-operacao-80-20` · árvore limpa · **zero push**
- `origin/execution/volc-os-operacao-80-20` permanece em `5cb654f`
- ⚠️ O upstream configurado da branch local é `origin/volc-os-v2`, **não** a
  branch operacional. Nenhum push ou pull foi executado.

### Os quatro SHAs dos specs de origem

Faltavam no handoff anterior. São eles que dizem contra o que este trabalho foi
adjudicado:

| Pacote | SHA | Path |
|---|---|---|
| Hermes — Meta + Creative P0 (autoridade adjudicadora) | `a875f1f02437f98e317d20bcd5c050cbaf281d57` | `docs/specs/meta-creative-p0-reconciliation-v1/` |
| Astra — Meta Completion | `2766e49aed7055f24cd97932e9995406a409826b` | `docs/specs/meta-completion-v1/` |
| Fable — Creative Supply Chain | `5d2cbd0006b7d794e685ebf67d3d79e6a879e12c` | `docs/specs/creative-supply-chain-v1/` |
| Fable — Google Multichannel | `8b067f6d7a63997c8a43c9cbbf4933fda68bd0ef` | `docs/specs/google-multichannel-completion-v1/` |

## O que foi feito, por tarefa

| Tarefa | Estado | Evidência |
|---|---|---|
| P0-RT-01 (C01 website-only/Shop) | **CONTRADITED → corrigido** | `5cb654f` emitia `destination_spec` não provado; removido do payload e da máscara, substituído por `shop_redirect_proof` por conta |
| P0-RT-02 (AssetSupplyManifest) | IMPLEMENTED | já em `5cb654f`; validado |
| P0-RT-03 (ambiguidade sem retry) | IMPLEMENTED | `resolver_ausente` levanta por construção |
| P0-RT-04 (separação de flags) | IMPLEMENTED + estendido | terceira autorização, por conta |
| P0-RT-05 (Page/Instagram/placements) | IMPLEMENTED | já em `5cb654f`; validado |
| T01 política por canal | **feito** | teto por canal; CPC/rede só Search; janela ≠ autorização |
| T02 paridade /provar × /subir | **feito** | mesmos montadores; portão pago só Search; `tcpa` em micros; teto/moeda no ledger |
| T03 Display PAUSED + control_spec | **feito** | 3 objetos PAUSED; dois booleanos `false` |
| T09 trava de URL PMax | **feito** | 5 automações OPTED_OUT; PAGE_FEED excluído |
| T12 gate de política | **feito nos TRÊS canais** ⚠️ correção | léxico, recibo HMAC, `supply_sha256` na chave |
| T06 Demand Gen | **parcial** | 3 automações OPTED_OUT; mutação não aberta |
| T04, T08, T13, T14 | **não feitos** | ver runbooks |
| T05, T07, T10, T11 | **externos** | RB-04 a RB-07 |

## Gates

| Gate | Resultado |
|---|---|
| pytest `backend/tests` + `volc_ads` | **4701 passam, 3 falham** — as 3 herdadas da base (baseline: 3893 passam, 3 falham) |
| TypeScript (`-p tsconfig.app.json`) | **77 erros = baseline**, ratchet mantido |
| Vitest | 16 falham / 1661 passam — **todas herdadas** (`src/` não foi tocado) |
| `npm run build` | ✅ |
| `git diff --check` | ✅ |
| `scripts/verificar_segredos.py` | ✅ nenhum padrão forte |
| `scripts/verificar_autoridade_supabase.py` | ✅ `https://database.agenciavolc.com.br` |
| Migration em PostgreSQL descartável | ✅ apply → uso → RLS/grants → rollback → reapply |
| Grafo `--check` | ✅ `current: true` em `dbedab2` |

**Falhas herdadas (idênticas antes e depois):** duas por dossiê congelado do
canário defasado, uma dependente de dados em `test_trafego.py`.

## Revisores

- **Codex `gpt-5.6-sol`** (read-only): 12 achados. 7 corrigidos, 3 refutados, 2
  registrados. Achado blocker real: a copy é lista e as listas sumiam do portão.
- **Gemini**: ⚠️ `gemini-3.1-pro` **não existe** neste endpoint (404). Usado
  `gemini-3-pro-preview`. A busca web devolveu HTTP 500 em todas as tentativas,
  então nenhuma citação foi aberta — as marcadas `COMPROVADA` foram lembradas,
  não verificadas. Achado útil aproveitado: `GENERATE_IMAGE_EXTRACTION`.

## Atos externos ainda necessários

Ver `RUNBOOKS-ATOS-EXTERNOS.md`. Em resumo: migration Meta, `validate_only`
real (⚠️ com plano novo — o recibo antigo ficou obsoleto), `create_paused`,
canários Display/Demand Gen/PMax, migration v12_03, e o detector de pixel.

## Confirmação literal

zero push · zero deploy · zero Meta/Google real · zero Supabase oficial ·
zero migration oficial · zero n8n · zero WordPress · zero ativação.

---

# Rodada 2 — fechamento local (06/09/2026)

Base da rodada: `88bf5f1` · commits: `c7ade55` (runtime) + este.

## O que fechou

| Item | Estado | Evidência |
|---|---|---|
| T12 nos três canais | **fechado** | portão em Display, Demand Gen e PMax, antes da ponte e da rede; canal declarado em cada caminho |
| Duplicidade por destino PMax | **fechado** | `_AUTORIDADE_DE_URL` por canal; PMax lê `asset_group.final_urls`; truncamento levanta em vez de virar ausência |
| Detector de pixel | **inventariado e recusado** | não existe motor no servidor; adaptador escrito e não registrado; portão segue `GATE_UNAVAILABLE` |

## O que NÃO fechou, e por quê

Estas quatro não couberam nesta rodada. Não estão começadas pela metade —
estão intocadas, e o mapa de cada uma existe:

| Tarefa | Estado | Bloqueador factual |
|---|---|---|
| T04 mensuração para Smart Bidding | **não feito** | a autoridade existe em `plano_mensuracao.py` + `prontidao.py` (servidor) e uma segunda, só de PMax, em `volc_ads/campanha/pmax.py::_checar_mensuracao`. Falta unificá-las numa precondição por conta E objetivo válida para Display/DG/PMax. |
| T06 Demand Gen tipado | **não feito** | falta `permite_mutacao_real`, entrada em `subir.CONSTRUTORES_POR_CANAL`, e a tradução de `BUDGET_BELOW_PER_DAY_MINIMUM`. O portão criativo já está ligado. |
| T08 PMax tipado | **não feito** | falta `construtor`/`validador` no perfil e `/provar` aceitar `canal=PERFORMANCE_MAX`. `ConfiguracaoPMaxEntrada` e `assets_pmax` já existem no modelo HTTP (`PlanejarPMaxEntrada`). |
| T13 UI multicanal | **não feito** | `src/` permanece intocado nas duas rodadas. |
| T14 read-back por canal | **não feito** | o contrato existe: Protocol `PerfilDeCanal` em `sincronizador.py` (`canal`, `entidades_filhas()`, `ler_filhas(buscar, campaign_ids)`); faltam `adaptador_display.py` e `adaptador_demand_gen.py`, irmãos de `adaptador_search.py`. |

## Detector de pixel — o inventário, para não ser refeito

Medido, não suposto. **Não existe motor utilizável neste servidor.**

- venv: só `pillow`. Sem `pytesseract`, `easyocr`, `opencv`, `rapidocr`,
  `paddleocr`, `torch`, `transformers`, `ultralytics`.
- `app/llm/` (Gemini, OpenAI) é **text-only**: `complete(system, user) -> str`,
  payload só `parts[{text}]`, sem `inline_data`.
- `visual_proof` valida URL, host e metadados de captura — não lê pixel.
- `landing_policy` e `publisher_quality` são léxico e HTTP.
- o Pillow existente MEDE dimensão e DESENHA texto; nunca lê.

O adaptador está escrito em `criativo/politica/detectores/ocr_tesseract.py`,
com assinatura conferida contra o Protocol e registro que só ocorre se o motor
existir. Para ligá-lo: instalar `pytesseract` + binário `tesseract` no host e
chamar `registrar_detectores_disponiveis()` no startup.

⚠️ E OCR fecha só metade: ele lê texto, não pontua logotipo desenhado. O
incidente que originou a lane era um envelope com marca — parte texto, parte
desenho. A metade visual exige classificador com escore calibrado e uma decisão
de política sobre enviar bytes de criativo a terceiro (RB-08).

---

# Rodada 3 — núcleo multicanal local (06/09/2026)

Base da rodada: `6aad83c48ed354b56239fbc7d127b723a6c38728` ·
branch `execution/volc-os-operacao-80-20` · árvore limpa na abertura ·
`origin/execution/volc-os-operacao-80-20` no MESMO SHA · `88bf5f1` ancestral ·
upstream local aponta para `origin/volc-os-v2` e **não foi tocado** ·
**zero push**.

Specs de origem, pelos SHAs congelados (os quatro conferidos com
`git cat-file -t` nesta rodada: todos existem e são `commit`):

| Pacote | SHA |
|---|---|
| Google Multichannel | `8b067f6d7a63997c8a43c9cbbf4933fda68bd0ef` |
| Meta Completion | `2766e49aed7055f24cd97932e9995406a409826b` |
| Creative Supply Chain | `5d2cbd0006b7d794e685ebf67d3d79e6a879e12c` |
| Contrato mestre (Hermes) | `a875f1f02437f98e317d20bcd5c050cbaf281d57` |

## As três correções do checkpoint

### 1. O topo dizia que o portão criativo estava só em Display

Corrigido no cabeçalho e na linha de T12 desta mesma página. O fato medido: o
portão roda nos três canais, sempre antes da ponte e antes da rede.
`test_trafego_paridade_multicanal.py` passou a cobrar isso por árvore, canal a
canal — um teste de comportamento seguiria verde no dia em que alguém
acrescentasse um quarto caminho ao lado.

### 2. Teto de paginação × teto de linhas

Eram dois tetos com o mesmo nome, e a evidência de um descrevia o outro.

| Antes | Depois | O que ele de fato conta |
|---|---|---|
| `canario.MAXIMO_DE_PAGINAS_DE_DESTINO = 50`, usado como `lidas > 50 * 1000` | `canario.TETO_DE_LINHAS_DE_DESTINO = 50_000` | LINHAS. `servico.search(...)` devolve um iterador de registros, e o `* 1000` era um tamanho de página assumido — `page_size` saiu da requisição na v21, e quem decide é o servidor do Google. |
| `sincronizador.TETO_DE_PAGINAS = 200` | igual | PÁGINAS de verdade: ele percorre `.pages` do pager. |
| `sincronizador.PAGINA_GAQL = 1000` | igual, com aviso escrito | **campo morto**: `buscar` não passa `page_size`. Ele fica como constante de teste, agora com o aviso de que não descreve comportamento nenhum. |

O nome antigo continua resolvendo por um ciclo, marcado como depreciado.
`test_o_teto_de_paginas_e_o_de_linhas_sao_tetos_DIFERENTES` cobra os dois.

⚠️ **E a correção achou um defeito maior que a nomenclatura.** O teto de páginas
de `sincronizador._paginas` truncava com `log.warning` + `break` e devolvia a
lista parcial como se fosse completa; `sincronizar_conta` seguia para
`marcar_ausentes` e para `vazio_confirmado`. Ou seja: **uma leitura truncada
PROVAVA ausência no espelho**, em silêncio. Agora ela levanta `LeituraTruncada`,
a rodada vira `parcial`, o motivo entra em `faltou` e nada é marcado como
ausente. `test_leitura_truncada_nao_marca_ninguem_como_ausente` reproduz o
defeito e a correção.

### 3. Vereditos que misturavam ACCEPTED com ressalva

Os vereditos desta rodada estão declarados abaixo, e nenhum deles mistura: cada
um é `ACCEPTED` **ou** `PARTIAL`, e todo `PARTIAL` tem um bloqueador factual
único.

### 4. (correção não pedida, encontrada ao conferir) `origin/execution`

O texto anterior dizia que `origin/execution/volc-os-operacao-80-20` permanecia
em `5cb654f`. Medido em 06/09/2026: ele está em `6aad83c`, o mesmo SHA do HEAD
local no início desta rodada. Continua sem push nesta rodada.

## O que fechou nesta rodada

| Tarefa | Estado | Evidência |
|---|---|---|
| **T04** mensuração | **fechada** | `volc_ads/mensuracao.py` é a autoridade única por (conta, canal, objetivo, estratégia). `prontidao.exigir_para_criacao` e `pmax._checar_mensuracao` viraram fronteiras dela; as listas de estratégia de `prontidao.py` viraram projeção derivada em import. |
| **T06** Demand Gen | **fechada no que é local** | perfil/validador/construtor já existiam; `/subir` passou a resolver o canal pelo manifesto (e não por um `if canal == "DEMAND_GEN"` literal), `BUDGET_BELOW_PER_DAY_MINIMUM` deixou de não existir no código, e `permite_mutacao_real` continua separado da capacidade local (`VOLC_DEMAND_GEN_VALIDATE_ONLY`). |
| **T08** PMax | **fechada no que é local** | construtor/validador no perfil, `PROVADORES_POR_CANAL`, manifesto do Hub, `/provar` com contrato tipado (`pmax` + `assets_pmax`) e mensuração LIDA NO SERVIDOR. `permite_mutacao_real` segue `False`. |
| **T13** interface | **fechada** | aba Multicanal no Hub com os treze eixos por canal, uma CTA dominante, bloqueado visível e explicável, e o primitivo `Eixo` distinguindo ausente / medido-e-vazio / não-lido. |
| **T14** read-back | **fechada** | sete estados tipados, adaptadores de varredura para os três canais, releitura por canal com objetos próprios, e truncamento que não prova ausência. |

## O defeito mais caro que esta rodada encontrou

**A trava de canal existia só no backend.** `perfil.DISPLAY.permite_mutacao_real`
é `True` desde T03; o que impedia Display de nascer era
`canario.CANAIS_COM_CRIACAO_AUTORIZADA`, que mora em `backend/app/trafego/` e
que `volc_ads.subir` **não importa** (a dependência aponta sempre
`backend → volc_ads`). A única guarda de canal do executor era
`_recusar_canal_sem_mutacao`, que lê só o perfil.

Consequência medida: um script in-process com

    with modo.destravar("..."):   # + FORGE_PERMITIR_ESCRITA=1
        subir.subir(preparo_display, motivo="...")

criaria uma campanha Display real **sem passar pela janela do canário**. A rota
HTTP recusava; o executor, não. Uma trava que só existe num dos dois caminhos
que chegam ao `mutate` não é uma trava — é uma convenção.

Correção: `volc_ads/autorizacao_de_canal.py` declara o conjunto uma vez,
`canario.py` o REFERENCIA (`is`, não `==`, e o teste cobra a identidade do
objeto) e `subir._recusar_canal_sem_mutacao` passou a cobrá-lo.

## Divergências adjudicadas contra o spec

| Ponto | Spec | Código | Adjudicação |
|---|---|---|---|
| Automações de Demand Gen | work breakdown pede `asset_automation_settings` no nível da CAMPANHA | emitidas em `AdGroupAd.ad_group_ad_asset_automation_settings` | **o código vence.** O campo de campanha não governa `DemandGenMultiAssetAd`; emitir ali deixaria as três LIGADAS no objeto que de fato as consulta. Conferido no proto v25 instalado. |
| `permite_mutacao_real` de Demand Gen | T06 do spec pede `True` + `CONSTRUTORES_POR_CANAL += DEMAND_GEN` | continua `False` | **a missão vence.** As contraprovas desta rodada exigem, literalmente, que DG e PMax continuem fechados e que Search siga sendo o único canal autorizado a criar. Abrir a mutação seria contrariar a instrução desta rodada para cumprir um spec de outra. |
| Quinta automação de PMax | não está em nenhum dos specs congelados | `GENERATE_IMAGE_EXTRACTION` emitida | **o código vence**, e já vencia: ela veio da revisão de contrato de API e sobreviveu à conferência no proto v25. O comentário do builder dizia "as QUATRO automações" com cinco na tupla — corrigido. |

## Limitações desta rodada (nomeadas, não escondidas)

1. **PMax só prova com a porta experimental ligada.** `VOLC_PMAX_VALIDATE_ONLY`
   nasce desligada, como a de Demand Gen. Nenhuma prova real foi feita: a
   missão proíbe `validate_only` real.
2. **O recibo de mensuração de PMax não carrega volume nem recência.**
   `pmax.ler_mensuracao` lê identidade e `value_settings`, não `metrics`. A
   autoridade responde `SINAL_NAO_COMPROVADO` com a causa exata ("ninguém mediu
   o volume") — que é verdade, e é o que o próprio builder já dizia como aviso.
   Ler o frescor exigiria uma segunda GAQL contra a conta, que esta rodada não
   está autorizada a exercitar.
3. **O teto diário de Demand Gen no canário (R$ 20,00) pode estar abaixo do piso
   que a API exige.** O piso depende da moeda e da conta e só a API o conhece;
   este sistema não inventa um. O bloqueio legível já existe e transporta o
   valor que a API devolver — mas ele só aparece num `validate_only` real, que
   esta rodada não faz.
4. **Nenhuma prova remota.** Zero Google, zero Meta, zero `validate_only`, zero
   criação, zero ativação, zero push.

## Confirmação literal desta rodada

zero push · zero merge/rebase/amend/tag · zero deploy · zero Google ou Meta
real · zero `validate_only` real · zero criação · zero ativação · zero Supabase
oficial · zero migration oficial · zero n8n · zero WordPress · origin e upstream
intocados.
