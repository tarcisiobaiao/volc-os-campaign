# PRD + SPEC EXECUTÁVEL — página `/redator`

**Versão:** 1.0 · **Data:** 2026-08-17 · **Branch de referência:** `sync/webgov6`
**Escopo:** a página de acompanhamento e configuração do motor de redação (funnelforge) dentro do VOLC O.S.

Tudo neste documento que é afirmado como fato foi medido nesta sessão (arquivo aberto, código rodado, ou consulta ao Postgres de produção via `ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149`). Onde não medi, está escrito **não verificado**.

---

# 1. O PROBLEMA

Hoje o operador dispara o redator por um popup (`src/components/pautador-pro/entity/DispararRedatorDialog.tsx`) e, durante os ~45 minutos e ~US$ 2,55 que o motor leva para escrever um funil, a única coisa que ele consegue ver são quatro números escalares — porque `worker.resumo_do_estado` calcula o dicionário completo de etapas (`backend/app/redator/worker.py:130-157`) e o filtro `_COLUNAS = {"run_id","paginas_planejadas","paginas_geradas","custo_usd"}` (`worker.py:267`) o joga fora antes de gravar, e a tabela `pautador_funnel_runs` (13 colunas, confirmadas no banco) não tem onde guardá-lo. Consequência medida: o operador não sabe em qual das 11 etapas o motor está, não sabe que `research_p1` sozinho pode ficar 186.662 ms sem escrever nada no estado (medido no run de referência), e não sabe que 79,5% do dinheiro já saiu quando a coluna de redação da última página fecha — que é exatamente a informação que decide se vale a pena cancelar. Pior: quando o run termina, o que ele produziu **desaparece** — o motor recebe do WordPress um objeto com `id`, `slug`, `link` e `status` e extrai só o `id` (`funnelforge-migracao/engine/src/funnelforge/pipeline/steps.py:2504-2554`), então as 5 a 7 URLs publicadas precisam ser **redigitadas à mão** no `FunnelUrlsEditor` para que a receita do AdSense consiga ser atribuída à campanha. E a doutrina editorial que decide a qualidade de tudo isso (`funnelforge-migracao/engine/src/funnelforge/pipeline/doctrine.py`, 11 prompts `.jinja` somando 1.167 linhas) só é editável por `ssh` + editor de texto, sem histórico, sem trava e sem volta atrás — e já se contradiz sozinha: rodei `banned_cta_execution_hit` sobre os 6 `APPROVED_CTA_EXEMPLARS` e o exemplar **aprovado** `'Como fazer a solicitação pelo app >>>'` devolve `'solicit'`, ou seja, é reprovado pelo próprio gate da LP.

---

# 2. O QUE A PÁGINA FAZ

A `/redator` é a tela do **segundo nó da esteira** — PAUTA → **FUNIL** → CAMPANHA → RESULTADO. Ela existe para transformar os 45 minutos mais caros da operação, que hoje são uma caixa-preta, numa superfície onde o operador vê onde o motor está, quanto já custou, o que ainda vai custar, e o que já saiu do outro lado. O objeto central é uma **matriz páginas × etapas**: cada linha é uma página do funil (com seu papel — LP, PRESELL, SOLUTION — e seu slug), cada coluna é uma das 11 etapas do pipeline na ordem exata em que `pipeline.py:256-352` as executa, e cada célula é um `StepResult` real do motor, com status, tentativas, modelo, custo em dólar, latência e a lista de issues. A altura do preenchimento de cada célula é o **custo real daquela célula**, normalizado pela mais cara do run — o que faz a mesma grade que responde "onde estou" responder também "para onde foi o dinheiro", sem um segundo gráfico. Isso é legítimo porque o número é `cost_usd`, gravado passo a passo pelo próprio motor (`domain/models.py:237`), e porque a informação é dramática: no run de referência `write_p7` custou US$ 0,27271 contra US$ 0,00260 de `image_p4` — 105× — e 21 das 54 células de grade custaram exatamente zero.

A página também é o lugar onde o funil **vira ativo**: ela lista as páginas publicadas com URL clicável e status do WordPress, e é ela que grava, no fim do run, o contrato de dados que o módulo de Google Ads vai consumir amanhã sem precisar de migração — a lista `paginas_publicadas`, montada **a partir da resposta REST do WordPress**, nunca reconstruída a partir do slug do card (que `_slug_com_sufixo`, `dedupe_slugs` e o próprio WordPress podem alterar). Por fim, ela abriga a **configuração do motor** em três baldes com permissões diferentes: doutrina editorial e parâmetros de máquina que o operador pode editar livremente; prompts de redação que ele pode editar com trava de marcadores obrigatórios; e contratos de máquina (schema do juiz, vocabulário do declarador, HTML dos botões Gutenberg) que aparecem em **somente leitura, com o motivo escrito na tela** — porque escondê-los faria o operador procurar e concluir que faltou.

---

# 3. FORA DE ESCOPO

| Não faz | Por quê |
|---|---|
| **Criar campanha no Google Ads.** | É o próximo módulo (`/campanhas`). Decisão já tomada pelo operador: páginas separadas por motor. O `volc_ads/` existe, é substancial, e tem **zero** referência a Supabase (medido: `grep -rn "supabase\|psycopg" volc_ads/` → nenhuma ocorrência). O que esta página faz é gravar o contrato que aquele módulo vai ler. |
| **Arquitetar o funil / escolher o tema.** | É o Pautador Pro (`/pautador-pro`). A `/redator` recebe um `opportunity_id` que já tem `funnel_architecture`, e o disparo já recusa card sem arquitetura com 409 (`backend/app/routers/publicacao.py:470-482`). |
| **Editar o conteúdo das páginas geradas.** | A superfície de revisão é o rascunho do WordPress — página renderizada, com o tema, invisível para o público. Está escrito e argumentado em `publicacao.py:386-409` e na tela em `DispararRedatorDialog.tsx:192-197`. Reimplementar um editor aqui seria construir um WordPress pior. |
| **Rodar dois funis em paralelo.** | `MAX_SIMULTANEOS = 1` (`worker.py:58`), deliberado: dois runs custam o dobro e o gargalo é a API do LLM. A tela mostra a fila, não a multiplica. |
| **Mostrar RPM / CPC / ROAS.** | Esses números só existem depois que a campanha nasce e recebe clique. A linha do funil mostra o nó RESULTADO como **não ligado** enquanto `campaigns.funnel_run_id` for nulo — inventar um estado ali seria a única desonestidade possível na faixa. |
| **Editar o bloco `routing` do `config.yaml`.** | Único bloco cujo erro de edição não degrada: **apaga**. Chave ausente levanta `ValueError` em `pagespec.py` e nenhuma página é construída. Não aparece nem em somente leitura editável — aparece como texto. |
| **Substituir o `FunnelUrlsEditor`.** | Ele continua existindo como ferramenta de **correção**. O que muda é que ele deixa de ser a única porta de entrada das URLs. |

---

# 4. A EXPERIÊNCIA

### 4.1 Primeiro acesso — estado vazio absoluto

O operador entra em `/redator` (rota nova; hoje `src/App.tsx:43-73` tem 16 rotas e **nenhuma** `/redator`). Confirmei no banco: `select count(*) from pautador_funnel_runs` = **0**. Nenhum run jamais completou. Então o estado vazio não é hipótese decorativa — é o primeiro estado que qualquer pessoa vai ver.

A tela mostra:

```
▸ MOTOR DE REDAÇÃO
Redator
▔▔▔▔

Nenhum funil foi escrito ainda.

O redator escreve a partir de um card que já passou por "Em funil"
no Pautador Pro. Ele leva ~45 min e custa ~US$ 2,10 num funil de
5 páginas (medido em campo).

[ ir para o Pautador Pro → ]
```

Sem ilustração, sem skeleton animado. O botão leva para `/pautador-pro`, que é a única forma legítima de produzir um run.

### 4.2 Lista de execuções (estado com histórico)

Quando existem runs, `/redator` é uma lista, mais nova primeiro, com uma linha por run: card, site, status, páginas (`paginas_geradas` / `paginas_planejadas`), custo, duração, e a hora. Cinco status possíveis, travados pela constraint do banco (`src/sql/pautador/02_publicacao_por_projeto.sql:155-156`): `queued`, `running`, `done`, `failed`, `cancelled`.

Um alerta honesto obrigatório nesta lista: `paginas_geradas` conta **build**, não publicação (`worker.py:143-147` — conta `build_p{n}` em OK/RETRIED/FALLBACK, e nada no worker olha `publish_p{n}`). Então a coluna se chama **"construídas"**, não "publicadas", e a contagem de publicadas vem de `paginas_publicadas` (coluna nova, §7).

### 4.3 Disparo

O disparo continua no `DispararRedatorDialog` do Pautador Pro — não se muda o gatilho. O que muda: ao confirmar, a tela **navega para `/redator/run/{id}`** em vez de fechar o popup. Os quatro 409 de pré-voo já existentes seguem valendo e cada um tem texto pronto em `publicacao.py:470-508`:

| Situação | HTTP | Texto na tela |
|---|---|---|
| Card sem `funnel_architecture` | 409 | "Este card ainda não tem arquitetura de funil. Passe por 'Em funil' antes." |
| Projeto sem WordPress | 409 | "Este projeto não tem WordPress configurado." |
| Sem Application Password | 409 | "Este projeto não tem Application Password cadastrado." |
| `conexao_ok != true` | 409 | "Teste a conexão deste site antes de gerar o funil (engrenagem na página do projeto)." |
| Já existe run `queued`/`running` para o par | 200 + `aviso` | "Já existe uma execução na fila para este card neste site." → navega para o run existente. |

### 4.4 O run rodando — a tela principal

Ordem vertical, do topo:

1. **Cabeçalho**: `.kicker` `MOTOR DE REDAÇÃO`, título `Redator`, `.aurora-rule` de 4rem, e à direita um selo `↻ 3s · ao vivo` que pisca no momento exato em que o polling traz mudança (e some quando o run fecha).
2. **A linha do funil** (§4.7).
3. **120px de respiro** — a régua `xl` que `docs/design/DESIGN-SYSTEM.md:51-56` pede e que **não existe como token** (confirmei: `tailwind.config.ts` não tem chave `spacing`; o `extend` só tem `fontFamily`, `colors`, `borderRadius`, `keyframes`, `animation`, `backgroundImage`, `boxShadow`). Usar `mt-[120px]` arbitrário.
4. **Identificação**: título do card → domínio do site, com `.hairline` embaixo.
5. **O cartão de custo** (§4.6) — o único bloco da página com aurora + grão atrás.
6. **A matriz** (§5).
7. **O que já saiu**: por página, `paginas_publicadas` (URL clicável + `status_wp`) e `artefatos.arquivos`.

### 4.5 Os quatro estados de tempo, e o que a tela diz em cada um

| Estado | O que o operador vê |
|---|---|
| **`queued`** | Matriz inteiramente em "pendente" (linha-base pontilhada). Texto: *"Na fila. Um funil por vez — `MAX_SIMULTANEOS = 1`."* Botão cancelar ativo. |
| **`running` e o custo mudou nos últimos 3 min** | Normal. Célula corrente com cursor + cronômetro. |
| **`running` e o custo NÃO muda há > 3 min** | Rótulo obrigatório ao lado do número: `— sem cobrança há 3:12`. Sem isso a tela parece travada. É verdade, não desculpa: `research_p1` levou 186.662 ms (3min07s) no run de referência, e o `state.json` só é reescrito nos 15 pontos de `_checkpoint` de `pipeline.py`. |
| **`running` e o `state.json` ainda não existe** | Os primeiros segundos: `_achar_run_dir` devolve `None` até o motor criar a pasta (`worker.py:100-114`). Texto: *"O motor está subindo. A primeira etapa é a pesquisa, e ela leva de 1 a 3 minutos."* |

### 4.6 Erros — a maior parte do tempo de tela

**a) `funnel_graph = FAILED` — a matriz nasce inteiramente vermelha com zero etapas executadas.**
`pipeline.py:234-252` escreve `blocked_pN` para **todas** as páginas antes de qualquer gasto e retorna. O texto importa mais que a cor:

> **O portão de grafo barrou o funil antes de gastar.** Nenhuma página foi escrita e nada foi cobrado. Motivo: `terminal_no_exit` — a solução terminal não tem saída cross-funnel. Isso economizou ~US$ 2,10.

**b) Página bloqueada no meio (`blocked_pN`).**
Existem duas checagens de `_page_blocked` no laço (`pipeline.py:308` e `pipeline.py:338`). Quando `blocked_pN` aparece, **toda a cauda da linha** (build, widget, content_gate, publish) é pintada como *cancelada pelo portão* com o motivo vindo da issue `fail_closed` — nunca como pendente, porque essas chaves jamais vão aparecer. Só 4 chaves são existenciais (`_page_blocked`, `pipeline.py:407-433`): `research_pN`, `write_pN`, `judge_pN`, `content_gate_pN`, mais o run-level `funnel_graph`. `seo_pN = FAILED` **não** bloqueia — a página publica assim mesmo, e a tela precisa desenhar os dois FAILED de forma diferente.

**c) Teto de gasto estourado (`budget_pN`).**
`pipeline.py:352-364`: escreve `budget_pN` FAILED e, se `exc.escopo == "run"`, **quebra o laço**. Texto: *"O teto de US$ X,XX do run acabou na página N. As páginas seguintes não foram tentadas."*

**d) O motor não está instalado.**
`MotorIndisponivel` (`worker.py:82-92`) → run vira `failed` com a mensagem que já traz o comando de conserto. A tela mostra a mensagem inteira em `<pre>` — é a única classe de erro em que o texto cru ajuda.

**e) O motor saiu com código ≠ 0.**
`worker.py:263-269` grava `erro` com os **últimos 800 caracteres do stdout**. A tela mostra 240 caracteres com "ver tudo" atrás de um `<details>`, porque esse campo é stdout de um subprocesso e pode carregar caminho de arquivo temporário. **Não verificado:** se o stdout do motor pode conter a senha do WordPress — o worker registra `perfil_para_log` mascarado (`backend/app/redator/perfil.py:153-162`), mas não auditei todo o log do motor. Até auditar, a rota trunca e o front não renderiza o `erro` cru sem `<details>` fechado.

**f) Run órfão de reinício do backend.**
`worker.reconciliar` fecha runs abertos que não estão neste processo. A tela mostra `cancelled` com o motivo real: *"(o processo não estava neste backend)"* — texto já produzido em `publicacao.py:590-592`.

### 4.7 A linha do funil

Faixa de 56px, quatro nós, `.hairline` de 1px atravessando, `.crosshair` (`src/index.css:311-321`) em cada nó. O trecho já percorrido é `.hairline-aurora`; o restante é `.hairline` cinza. Cada nó tem um `.kicker` e **um número real, nunca um adjetivo**:

| Nó | Fonte do dado | Quando não há dado |
|---|---|---|
| PAUTA | do card | — |
| FUNIL | `paginas_publicadas.length` / `paginas_planejadas` | `—` |
| CAMPANHA | `lp_url` quando o run terminou; `campaigns.campaign_id` quando existir a aresta de volta | **`não ligada`** |
| RESULTADO | `daily_campaign_metrics` | **`—`** |

Ressuscitar `.crosshair` aqui é deliberado: medi 8 usos em **2** arquivos, ambos fora do produto (`src/pages/Login.tsx`, `src/pages/NotFound.tsx`).

### 4.8 Run terminado (`done`)

O cursor some, o cronômetro vira duração total, o cartão de custo congela no número final com o aviso de subestimação (§5.6), e a seção "o que já saiu" ganha peso: uma linha por página publicada com `p{N} · papel · <url clicável> · [rascunho]`, e um botão por página `abrir no WordPress →`.

---

# 5. A MATRIZ — o coração

## 5.1 Os eixos

**Linhas = páginas do plano**, na ordem de `plan.pages[].page_number`. Cada linha carrega: número, `role`, slug, `h1_title`, `engajamento`. O campo `role` **existe no plano** — confirmei no `state.json` de referência: `p1 role=LP`, `p2-p4 role=PRESELL` (com `page_type` HUB), `p5-p7 role=SOLUTION`. A tela deve usar `role`, com fallback para `derive_role(slug)` (`domain/models.py:18-20`: `-pr` → PRESELL, `-p<N>` → SOLUTION, senão LP) — **nunca** `page_type`, que diz "HUB" onde o papel é PRESELL.

Tamanho de produção: `config.yaml:16-19` tem `presell_hubs: 1` e `lp_direct_solutions: 2` → **5 linhas** (1 LP + 1 PRESELL + 3 SOLUTION). O run de referência é de julho, rodou com 3 hubs → 7 linhas. **O layout precisa aguentar 5 e 7 sem virar duas telas.**

**Colunas = 11 etapas**, na ordem exata do laço `pipeline.py:256-352`:

| # | Chave | Onde é escrita | Paga? |
|---|---|---|---|
| 1 | `research_pN` | `pipeline.py:262-269` | sim |
| 2 | `write_pN` | `pipeline.py:271-278` | sim |
| 3 | `judge_pN` | dentro de `step_write` → `steps.py:763`, mesmo checkpoint do write | sim |
| 4 | `seo_pN` | `pipeline.py:280-282` | sim |
| 5 | `image_pN` | `pipeline.py:284-293` | sim (centavos) |
| 6 | `image_gen_pN` | `_record_image_generation`, `steps.py:1489-1531` | sim (a imagem) |
| 7 | `screenshot_pN` | `pipeline.py:295-304` | não |
| 8 | `build_pN` | `pipeline.py:315-318` | não |
| 9 | `widget_pN` | `pipeline.py:320-330` | sim |
| 10 | `content_gate_pN` | `pipeline.py:332-337` | não |
| 11 | `publish_pN` | `pipeline.py:347-352` | não |

`image` e `image_gen` são **duas colunas, não uma**: `image_pN` é a chamada de texto que escreve o prompt em inglês; `image_gen_pN` é a imagem de verdade. Uni-las esconde justamente a que pesa.

**Faixa run-level, acima da matriz** (não é linha de página): `extract`, `engajamento`, `expand_presell_hubs`, `funnel_graph`, `contract_advisory`. E duas chaves de exceção que precisam de tratamento explícito: `budget_pN` (segue a convenção `_pN`) e **`page_N`** — que **quebra** a convenção (`pipeline.py:369,384` usam `f"page_{page.page_number}"`, sem o `p`). Um parser ingênuo de `split('_p')` coloca a exceção da página 5 como um passo do funil. **O parse tem de ser regex `_p(\d+)$` com caso especial `^page_(\d+)$`.**

## 5.2 A máscara de aplicabilidade — calculada no servidor

Ausência de chave é ambígua por construção: significa ao mesmo tempo "não se aplica", "a flag está desligada", "ainda não chegou" e "a página morreu antes". A tela **não pode** desambiguar sozinha. O backend calcula, por página, a lista `aplicaveis: string[]` a partir do papel + flags do run:

| Coluna | Condição de aplicabilidade | Evidência |
|---|---|---|
| `research`, `write`, `seo`, `build`, `content_gate` | sempre | — |
| `judge` | `role != LP` | LP dá `return` antes de `_judge_page` (`steps.py:1250` vs `:1339`). Confirmado: o run de referência tem `judge_p2..judge_p7`, **não tem** `judge_p1`. |
| `image` | `role == LP` **ou** `run.featured_image` | `pipeline.py:290-292` |
| `image_gen` | `image` aplicável **e** `deps.image_gen`/`image_proc` presentes **e** `image_wanted` | `steps.py:1437` |
| `screenshot` | `deps.screenshot != None` (flag `official_screenshots` + playwright) **e** `role == SOLUTION` | `pipeline.py:300`, `steps.py:1637-1641`. Confirmado: só `screenshot_p5/6/7`. |
| `widget` | `run.widgets_enabled` **e** `role == SOLUTION` **e** `engajamento != 'dado_unico'` | `steps.py:2106-2118`. Confirmado: só `widget_p5/6/7`. |
| `publish` | `publish=True` **e** `deps.publisher != None` | `pipeline.py:347` |

No run de referência isso produz **9 ausências estruturais** de 63 posições (7×9 com o alfabeto antigo): `judge_p1`, `screenshot_p1..p4`, `widget_p1..p4`. Não são falha — são vazio verdadeiro.

## 5.3 O que é uma célula

Retângulo de **34×26px** (24×22 no mobile), sem canto arredondado, sem borda. O que existe é uma **linha-base de 1px** na largura toda; o estado é lido pela forma do que sobe dessa base.

Payload de uma célula (projeção de `StepResult`, `domain/models.py:227-238`):

```jsonc
"write_p4": {
  "status": "RETRIED",
  "tentativas": 2,
  "modelo": "gemini-3.5-flash",
  "custo_usd": 0.18208380,
  "latencia_ms": 86384,
  "issues": [ {"code": "...", "message": "..."} ]
}
```

`artifact_path` **não entra**: é campo morto — declarado em `models.py:233` e nunca escrito em lugar nenhum do motor; no run de referência os 55 passos têm `artifact_path: null`. Artefato é por **página**, via a coluna `artefatos`.

## 5.4 Os sete estados, e como cada um se comunica sem cor

Cor sozinha está descartada **por medição**, não por princípio. Calculei o contraste WCAG 2.x dos tokens semânticos de `src/index.css` sobre `--card`:

| token | claro (`--card: 0 0% 100%`) | escuro (`--card: 220 22% 9%`) |
|---|---|---|
| `--success` | **3,03:1** | 8,02:1 |
| `--warning` | **2,38:1** | 9,07:1 |
| `--info` | **2,76:1** | 9,54:1 |
| `--destructive` | 5,24:1 | **4,29:1** |
| `--primary` | 8,09:1 | 9,84:1 |

Três dos cinco reprovam o piso de 4,5:1 no tema claro, e `--warning` reprova até o piso de 3:1 para elemento não-textual. Pior: a razão de luminância entre `warning` e `success` no tema claro é **1,32** — praticamente a mesma clareza, que é o par exato que um protanope/deuteranope confunde. E os números **invertem** entre os temas, então nenhum esquema baseado em hue é estável. Portanto: **geometria primeiro, glifo redundante, cor em último e só em dois estados.**

| Estado | Geometria | Glifo | `aria-label` | Cor |
|---|---|---|---|---|
| **NÃO SE APLICA** | nada — nem base. Um ponto de 1px no centro | `·` | "não se aplica a esta página" | `--muted-foreground/25` |
| **PENDENTE** | só a linha-base, **pontilhada** | — | "pendente" | mono |
| **RODANDO** | linha-base sólida + **cursor**: segmento de 6px com `--gradient-aurora` percorrendo a largura em 1,4s por `translateX`; grão por cima. Acima, o cronômetro em `tabular` (`0:47`) | — | "em andamento há 47 segundos" | aurora |
| **OK** | bloco **cheio**, altura ∝ custo (§5.5) | `◆` | "concluído" | mono |
| **RETENTADO** | bloco cheio + `.val-hachura` 45° por cima + sufixo `×2`/`×3` em 8px `tabular` | `◆` | "concluído com 2 tentativas" | mono |
| **FALHOU** | bloco **vazado** (contorno 1px) + **diagonal** de 1px canto a canto. A linha inteira cai para `opacity: .35` | `×` | "falhou" | `--destructive` |
| **PULADO** | bloco **vazado, sem diagonal** | `⌀` | "pulado" | mono |
| **CANCELADA PELO PORTÃO** | bloco vazado + `.val-hachura` diagonal fina, sem glifo | `—` | "cancelada: a página foi bloqueada antes" | mono |

O enum do motor tem 5 valores (`domain/models.py:215-224`): `OK`, `RETRIED`, `FALLBACK`, `FAILED`, `SKIPPED`. `FALLBACK` desenha como OK com o **modelo em destaque** no tooltip (passou, mas num modelo diferente do configurado — `runner.py:139-146`). Colapsar `SKIPPED` em `FAILED` estaria mentindo sobre uma distinção que o motor faz de propósito e que os portões respeitam: `_page_blocked` só dispara em `FAILED`.

**Duas ligações obrigatórias entre células:**

1. **widget SKIPPED → content_gate.** `steps.py:2188-2200`: se `widgets_enabled` + `role == SOLUTION` + arquétipo ≠ `None` e o widget não terminou OK, o gate acrescenta `required_widget_missing` — e o gate **é** existencial. Um "amarelo tranquilo" seguido de um "vermelho misterioso" é a mesma história contada duas vezes. A tela liga as duas com um traço fino de 1px.
2. **`blocked_pN` → cauda da linha.** Ver §4.6b.

**`screenshot_pN = OK` não significa "tem print".** Medido: `screenshot_p5`, `p6`, `p7` são todos OK, mas `state.screenshots` tem **só a chave `'5'`**, com 1 arquivo (`p5-oficial-wwwcaixagovbr-1.webp`). `steps.py:1689-1691` grava o OK fora do `if shots:`. A célula de screenshot mostra a **contagem de prints**, não só o status: `◆2`, `◆1`, `◆0`.

## 5.5 A altura é o custo — a uma coisa memorável

`altura_px = 2 + round(22 * (custo_da_celula / custo_da_celula_mais_cara_do_run))`, com piso de 2px. Por que isso é honesto e não enfeite, medido no run de referência (`funnelforge-migracao/referencia/run-fgts-producao/state.json`, total US$ 2,5472343):

| família | US$ | % |
|---|---|---|
| `write` | 1,0639 | 41,8% |
| `research` | 0,9603 | 37,7% |
| `widget` | 0,2881 | 11,3% |
| `judge` | 0,1396 | 5,5% |
| `seo` | 0,0515 | 2,0% |
| `extract` | 0,0239 | 0,9% |
| `image` | 0,0199 | 0,8% |
| `build` / `publish` / `screenshot` | **0,0000** cada | 0% |

As duas primeiras colunas formam um paredão à esquerda; as quatro últimas são um fio. A forma da grade **ensina** que 79,5% do dinheiro já saiu quando a redação da última página fecha — que é a informação que decide se vale a pena cancelar. Uma grade de quadrados idênticos esconderia isso.

E as retentativas viram coisa que se **vê**: `write_p4` (2 tentativas, US$ 0,18208), `write_p5` (2, US$ 0,23057), `write_p7` (3, US$ 0,27271). Custo por tentativa ≈ US$ 0,091 / 0,115 / 0,091 → o excedente pago só por retentativa foi **US$ 0,388 = 15,2% do run**. Célula alta e limpa e célula alta e hachurada dizem coisas opostas sobre o dinheiro.

**Passo de custo zero fica com 2px, e isso é verdade** — `build`, `publish`, `screenshot`, `content_gate` montam `StepResult` sem telemetria por construção (`steps.py:1866`, `:1691`, `:2226`, `:2552-2554`). Nesses casos o tooltip **omite** custo/latência/modelo, e não escreve "US$ 0,00", que sugeriria medição.

## 5.6 O aviso de subestimação — obrigatório

O total exibido é **menor que a fatura**, por dois defeitos do motor que não se conserta na tela:

- `_widget_skip` (`steps.py:1942-1948`) monta um StepResult zerado sem copiar custo/latência/tentativas do `res` que o runner devolveu. Medido no run de referência: `widget_p5` está gravado com `cost_usd: 0.0`, `latency_ms: 0`, `attempts: 0`, `model_used: ''`, com as issues `widget_rejected` e `ampersand_in_script` — trabalho que **foi pago** e aparece como zero.
- `declarar_engajamento` (`steps.py:2620-2631`) sempre grava custo, tokens, modelo e tentativas zerados.

Rótulo fixo abaixo do número: **"custo contabilizado — não inclui tentativas descartadas de widget/engajamento"**. A tela **não compensa** o número por conta própria.

## 5.7 O comportamento ao vivo

**O motor não emite "em andamento".** Não existe status RUNNING em lugar nenhum do código: uma chave só aparece quando o passo **termina**. Então "rodando" é inferência da tela, com regra determinística:

> a célula corrente é a **primeira coluna aplicável sem chave**, na **página não bloqueada de menor número**.

O cronômetro conta desde o instante em que o front observou aquela célula virar corrente (não desde o início do run) e é **obrigatório**, não enfeite: sem ele, os 3min07s de `research_p1` fazem a tela parecer travada.

**Cadência real medida** no run de referência: o `run_id` termina em `-20260721-115510` (início 11:55:10) e o `mtime` do `state.json` é 12:27:22 → 1932s de relógio para 55 células = **1,7 célula/min**. Soma das latências: 1326s = 69% do relógio. Mediana de passo 6,9s, máximo 186,7s. Com polling de 3s são ~644 consultas por run e ~48 momentos de mudança: **~93% das consultas não trazem nada**. Daí o `versao` (hash) + ETag/304 no contrato (§8).

**`prefers-reduced-motion`**: o cursor some e sobra o cronômetro — que é o dado. `src/index.css:392-396` já tem o bloco, mas ele cobre só as classes utilitárias; qualquer `@keyframes` novo escrito inline (como fazem `EntityKanbanBoard.tsx:80-82` e `ValidacaoPainel.tsx:88-90`) **tem de repetir a guarda**.

## 5.8 Clicar numa célula

Desktop: popover ancorado. Mobile: `Sheet` de baixo. Conteúdo:

```
write_p4 · página 4 · quem-tem-direito-antecipar-fgts-pr3 (PRESELL)

status      RETENTADO — 2 tentativas
modelo      gemini-3.5-flash
custo       US$ 0,182084   (US$ 0,0910 por tentativa)
latência    1min 26s
tokens      29.306 entrada · 16.573 saída

issues      (nenhuma)

Esta etapa é EXISTENCIAL: se falhar, a página não é
construída nem publicada.
```

Regras de honestidade no popover:
- Se a coluna é de custo zero por construção, as linhas `custo`, `latência`, `modelo` e `tokens` **não aparecem**.
- Se a célula é `NÃO SE APLICA`, o popover mostra **o motivo específico**, não um genérico: *"screenshot só roda em páginas SOLUTION"*, *"widget não roda quando o engajamento é `dado_unico`"*, *"a LP não passa pelo juiz — o critério 6 julga hrefs e o roteamento da LP é determinístico"*.
- Se a célula é existencial, a última linha diz isso. Se não é, diz o contrário: *"Esta etapa NÃO bloqueia: a página publica mesmo se ela falhar."*
- Toda `issue` aparece como `code` em `.kicker` + `message` em texto corrido. Nunca só o code.

## 5.9 Mobile

A matriz **não vira lista**. 9 colunas visíveis × 24px + 8 vãos de 2px + rótulo de 34px = 266px, cabe nos 343px de conteúdo de um 375px; com 11 colunas o container ganha `overflow-x: auto` e cabeçalho `sticky`. O que se perde é o número dentro da célula, recuperável por toque — a forma e o glifo continuam legíveis, que é o que a leitura de relance precisa.

## 5.10 Tokens e reuso (o que NÃO reinventar)

**Usar:** `.kicker` (245 usos em 62 arquivos — a primitiva mais usada do produto), `tabular` (253/57), `.font-display` (132/41), `.reveal` (97/38), `.hairline` (20/16), `.crosshair` (8/2 — ressuscitar), o bloco AURORA de duas camadas de `EntityKanbanBoard.tsx:47-83` (copiar **inteiro**, incluindo o ladrilho de grão de 90px fixo — sem `width`/`height` no SVG o grão estica e vira grão graúdo em card alto), `.val-hachura` de `ValidacaoPainel.tsx:72-76`, e a pista de dispersão de `Esgotamento` (`ValidacaoPainel.tsx:287-324`) como base da régua de custo.

**Não usar:** `.text-aurora` (gradiente em texto sobre número que muda a cada 3s é ilegível), `Progress` (`src/components/ui/progress.tsx:19` — `rounded-full` chapado, sem grão), `AnimatedGradient` (**quebrado**: a classe `animate-background-gradient` e a var `--background-gradient-speed` não existem nem em `tailwind.config.ts` nem em `src/index.css` — renderiza círculos estáticos), `LoadingSpinner`.

**Divergências assumidas como decididas** (o código já decidiu; a `/redator` não reabre): `--radius: 0.5rem` (`src/index.css:81`) contra os 0px de `docs/design/DESIGN-SYSTEM.md:47`; sombras `--shadow-card`/`--shadow-elevated` tingidas de azul contra `docs/design/DESIGN-SYSTEM.md:105`. **O que falta e precisa ser criado:** a escala de espaço 16/32/64/120 — não existe token, usar arbitrário.

Números **sempre** em `tabular`. O custo em **quatro casas decimais**, não duas: as células vão de US$ 0,0026 a US$ 0,2727 e duas casas apagariam metade da matriz.

---

# 6. CONFIGURAÇÃO NA TELA

**Duas telas, não uma:** `/redator/config/doutrina` (o que o motor diz) e `/redator/config/motor` (com que ferramenta e a que preço). Misturar as duas é o que cria a ilusão de que renomear um critério do juiz é uma escolha de estilo.

## 6.1 Balde A — livre para editar

| Campo | Onde vive hoje | Efeito colateral que a tela mostra na hora da edição |
|---|---|---|
| `BANNED_FEAR` (9), `BANNED_OFFICIAL` (6), `BANNED_CTA_FIRST_PERSON` (7), `BANNED_CTA_EXECUTION` (7), `REQUIRED_COMPLIANCE_ANCHORS` (5), `APPROVED_CTA_EXEMPLARS` (6), `COMPLIANCE_NOTICE_TEXT` | `pipeline/doctrine.py` (contagens medidas rodando o módulo) | "muda 4 prompts (`redator_p1`, `redator_pages`, `redator_presell`, `judge`) + os validadores `calm_utility`/`cta_style` + o gate da LP + o rodapé que o enhancer reposiciona — **por construção, numa edição só**" |
| 9 passos de LLM: `model`, `fallbacks`, `temperature`, `web_search` | `config.yaml:146-173` | soma do custo estimado contra os tetos |
| 4 flags de run: `hero_image`, `featured_image`, `official_screenshots`, `widgets_enabled` + `screenshots_max_per_page`, `publish_status` | `config.yaml:22-29` | "desligar `widgets_enabled` apaga a coluna `widget` da matriz" |
| Tetos: `budget.max_usd_per_run`, `max_usd_per_page`, `image_price_usd` | `config.yaml` + já sobreponíveis por run (`config/perfil.py`) | **zero em qualquer teto desliga aquele teto** |
| Forma do grafo: `presell_hubs`, `lp_direct_solutions` | `config.yaml:16-19` | "muda o número de LINHAS da matriz: hoje 5" |
| Limiares de unicidade: `jaccard_threshold`, `opening_line_threshold`, `hub_distinction_threshold` | `config.yaml:142-145` | — |
| Retentativa: `research_max_attempts`, `research_backoff_s`, `research_backoff_max_s`, `run.max_retries` | `config.yaml:3-10` | "o backoff **geral** do Runner (2,0s/30,0s) NÃO está no config — é default de construtor em `runner.py:57-60`" |
| **`run.image_model` / `run.image_quality`** | `config.yaml:26-27` | aviso permanente: "isto é a **geração da imagem** e é OUTRA coisa de `steps.image.model`, que é o modelo de TEXTO que escreve o prompt em inglês" |

**Trava do balde A:** só a checagem cruzada obrigatória da doutrina (§6.4c) e a validação de tipo. Nada mais.

## 6.2 Balde B — editável com trava

| Campo | Trava obrigatória no salvamento |
|---|---|
| `redator_p1.jinja` (116 linhas) | render com contexto-fantoche + presença das **8 chaves do schema JSON** e das contagens **4 sections / 5 faq / 3 cta_texts** — `lp_template.py:31-71` exige `len(sections)==4` e `len(cta_texts)==3` |
| `redator_pages.jinja` (209 linhas, o maior) | os blocos `<!-- wp:buttons -->` **completos** (abertura e fechamento), a linha `{% include "blocks_gutenberg.jinja" %}`, e `{{ compliance_notice_text }}` |
| `redator_presell.jinja` (126 linhas) | idem + a regra dos ~4 primeiros parágrafos planos top-level |
| `seo.jinja`, `image_prompt.jinja`, `image_prompt_lp.jinja`, `blocks_gutenberg.jinja` | render + suíte de prompts |
| lista `validators` de cada passo (`config.yaml:161`) | **checkboxes a partir do registro real de 33 nomes** (`checks.py:1470-1502`), nunca campo de texto |
| `ads.paragraph_anchors` / `ads.slots` (`config.yaml:118-137`) | ao mudar, exigir revisão da prosa de `redator_presell.jinja:37`, que hoje diz "§1 e §3" **escrito à mão** |

**Por que a trava do botão é a mais importante:** os validadores `cta_style`, `no_trailing_buttons`, `bridge_before_cta` e `cta_destination_congruent` só enxergam âncoras **dentro** de `wp:buttons` (`checks.py:61-94`). Trocar o HTML do botão por outra coisa faz os quatro devolverem lista vazia — ou seja, **aprovarem tudo, em silêncio**. Portão que some é pior que portão que reprova.

## 6.3 Balde C — somente leitura, com o motivo escrito

Aparecem na tela, em `<pre>`, com um cabeçalho explicando por quê. Esconder é pior: o operador vai procurar e achar que faltou.

| Item | Motivo escrito na tela |
|---|---|
| `judge.jinja` — os 7 nomes de critério | "estes nomes são lidos **por nome** pelo Python em `steps.py:757`; score ausente conta como 0 (fail-closed) e reprova toda página" |
| `extractor.jinja` — os 9 campos de `pages[]` | "viram kwargs de `Page(**p)` em `steps.py:86` — renomear é `TypeError` no meio do run" |
| `declarador_engajamento.jinja` — o vocabulário fechado de 5 rótulos | "rótulo fora do mapa gera `engajamento_nao_resolvido` (`checks.py:1282-1296`) e reprova a página" |
| `redator_widget.jinja` — a seção REGRAS TÉCNICAS | "é espelho declarado do sanitizador Python; afrouxar aqui não afrouxa `sanitize_widget_block` — o widget é descartado em silêncio" |
| HTML literal dos 3 botões Gutenberg e o par `<!-- wp:html -->` | "é o que os regex de validação procuram (`checks.py:67`, `:822`, `:1625`)" |
| bloco `routing` do `config.yaml` | "chave ausente levanta `ValueError` e **nenhuma** página é construída" |

## 6.4 Onde é guardado, e como se volta atrás

Três tabelas novas. O padrão de segurança já existe no repositório para o segredo do WordPress: RLS ligada e **zero policy**, só `service_role` atravessa (`src/sql/pautador/02_publicacao_por_projeto.sql:179-183`).

```sql
create table public.redator_prompt_versions (
    id          bigserial primary key,
    nome        text not null,          -- 'redator_p1' | 'doctrine' | ...
    corpo       text not null,
    hash        text not null,          -- sha256 do corpo
    autor       text not null,
    notas       text,
    criado_em   timestamptz not null default now()
);
create table public.redator_config_versions (
    id          bigserial primary key,
    patch       jsonb not null,         -- só as chaves sobrepostas
    hash        text not null,
    autor       text not null,
    notas       text,
    criado_em   timestamptz not null default now()
);
create table public.redator_perfil_ativo (
    id          bigserial primary key,
    project_id  integer references public.projects(id),  -- NULL = escopo global
    prompts     jsonb not null default '{}'::jsonb,      -- {nome: prompt_version_id}
    config_id   bigint references public.redator_config_versions(id),
    atualizado_em timestamptz not null default now()
);
```

**Escopo global × por projeto tem de existir desde o começo**, porque o `config.yaml` de produção hoje carrega a identidade de **um** cliente para todos os projetos: `config.yaml:31-37` traz domínio `creditoup.com.br`, CNPJ `42.724.548/0001-24`, autor "Equipe Crédito Up". O `aplicar_perfil` sobrepõe `domain` e os post types (medido em `config/perfil.py:69-71`), mas **não toca CNPJ nem autor** — e o `cnpj` vai para o ctx e é usado pelo validador `identity`.

**Versão nova é linha nova, nunca `UPDATE`.** A ativação é um ponteiro; voltar atrás é apontar o ponteiro para a versão anterior — uma linha, não uma edição de texto de volta. Diff de texto puro basta: os 11 prompts somam **1.167 linhas** (medido com `wc -l`).

**Como o motor enxerga a versão editada:** por **arquivo**, a cada run. Os prompts são carregados por `PackageLoader("funnelforge","prompts")` (`prompts/__init__.py:7-11`), o processo é novo a cada disparo (`worker.py:212-218`) e não há cache entre runs. Faltam **dois pontos de injeção**, ambos cirúrgicos:

1. `run-volc` ganha `--config <caminho>` e repassa para `load_settings(config_path=...)` — a assinatura **já aceita** o parâmetro (`config/settings.py:292`); só o chamador não usa (`cli.py:178` chama `aplicar_perfil(load_settings(), dados_perfil)`).
2. `prompts/__init__.py` troca o loader por `ChoiceLoader([FileSystemLoader(os.environ.get("FUNNELFORGE_PROMPTS_DIR")), PackageLoader(...)])`, com a variável setada pelo worker no env do subprocesso — que **já passa env customizado** (`worker.py:217`).

**Nunca sobrescrever o pacote instalado** (`src/funnelforge/prompts/`): a edição viraria estado invisível fora do git e o próximo `git pull` apagaria o trabalho do operador sem aviso. **Nunca reescrever o `config.yaml` da raiz**: hoje a janela de concorrência está fechada por acidente (`MAX_SIMULTANEOS = 1`, `worker.py:58`) e não por desenho. **Nunca `chdir` por run**: `runs_dir` é `Path("runs")` relativo (`cli.py:68`) e o `_phrase_registry.json` compartilhado é o que impede duas páginas de funis diferentes de abrirem com a mesma frase — está escrito em `worker.py:25-30`.

**Config editada vai por `--config`; perfil por `--perfil`.** Misturar as duas transforma o perfil num segundo `config.yaml` paralelo — exatamente a mistura de donos que `config/perfil.py` foi escrito para desfazer.

## 6.5 O portão de salvamento

Quatro checagens, todas baratas e todas já existentes como código:

- **(a)** renderizar o template com contexto-fantoche; falhar em `TemplateSyntaxError`/`UndefinedError`.
- **(b)** conferir a lista de marcadores obrigatórios daquele prompt (§6.2). Marcador ausente → **recusa o salvamento**, não avisa.
- **(c)** se a edição for em doutrina: rodar `banned_cta_execution_hit` sobre `APPROVED_CTA_EXEMPLARS` e **recusar** se algum exemplar aprovado virar banido. Isto não é hipótese: o casamento é regex com stemming ancorado em `\b` (`doctrine.py:78-98`), e verbos curtos e comuns viram bloqueio em massa.
- **(d)** rodar a suíte do motor. Medido nesta sessão: **615 passed in 5,14s**.

**Botão "Testar sem gastar"** = (a)+(b)+(c)+(d) sob demanda, com o resultado na tela. É o único jeito honesto de o operador saber que a edição dele não quebrou nada antes de queimar US$ 2,55 e 32 minutos.

## 6.6 O painel de marcadores obrigatórios

Ao lado do editor de prompt, com estado **ao vivo** (presente/ausente). Para `redator_p1`: as 8 chaves do schema e as contagens 4/5/3. Para `redator_pages`/`presell`: os `wp:buttons` completos, o `{% include %}` e o `{{ compliance_notice_text }}`. Para `redator_widget`: o par `<!-- wp:html -->` e a palavra literal `NONE`.

## 6.7 Defeitos que a tela precisa flagrar no dia 1

1. **A doutrina se contradiz hoje, antes de qualquer edição.** Medido: `banned_cta_execution_hit('Como fazer a solicitação pelo app >>>')` → `'solicit'`. É exemplar **APROVADO** em `doctrine.py:140` e é reprovado pelo gate da LP com o código `cta_execution`. Dar ao operador o poder de editar essas listas sem antes consertar isso é institucionalizar a contradição. **A tela mostra um alerta permanente até o conserto.**
2. **A doutrina de falsa oficialidade entra completa na LP e no juiz** (`{% for f in banned_official %}`, 6 frases) **e está escrita à mão e incompleta** nos dois prompts interiores (`redator_pages.jinja:22`, `redator_presell.jinja:23`).
3. **Cinco dos nove arquétipos de widget são inalcançáveis**: `ENGAJAMENTO_PARA_ARQUETIPO` (`steps.py:1997-2003`) tem 5 chaves e alcança 4 arquétipos; o catálogo de `redator_widget.jinja:27-43` lista 9. Merece uma sub-tela própria de 5 linhas.
4. **`seo.jinja:38` manda "máximo 155 caracteres" e o validador só reprova acima de 160** (`checks.py:523-535`); o limite de 60 do SEO Title **não tem validador nenhum**.

## 6.8 O que fica de fora até virar trabalho de motor

Cinco números que só existem em Python e que o operador vai querer mexer no primeiro mês: **400 palavras de corpo mínimo** (`checks.py:271`), **≥3 H2 de conteúdo** (`checks.py:396`), **160 caracteres de metadescription** (`checks.py:530`), **nota de corte 7 do juiz** (`steps.py:757`), **3 termos do limiar cross-funnel** (`adapters/sitemap_http.py:33`). Expor exige antes movê-los para o config — é trabalho de motor, não de front. A tela os mostra em somente leitura com a etiqueta *"hardcoded em Python — mover para o config antes de expor"*.

---

# 7. O ELO COM A CAMPANHA

## 7.1 O que está errado no ponto de partida

**`campaigns.lp_path` NÃO é o elo — é uma coluna órfã.** Medido: `grep -rn "lp_path"` no repositório inteiro (excluindo `node_modules`/`.git`) devolve **uma** linha, e é documentação (`docs/VOLC-DELTA.md:264`). Li o `prosrc` de `enrich_campaign_with_google_ads` no banco de produção: ela **não escreve `lp_path`**. As 3 campanhas do projeto 1 têm valor porque alguém digitou.

**O elo real já existe e move dinheiro: `campaign_funnel_urls`.** Confirmado no banco: 17 linhas, 3 campanhas, todas do projeto 1. Para a campanha `23524108985` são 1 URL `/r/` (a LP) + 6 URLs `/rec/` — exatamente a lista que um run do redator produz. Os três triggers da tabela (lidos de `pg_trigger`):

- `trigger_clean_funnel_url` (BEFORE INSERT/UPDATE) → `clean_funnel_url()`
- `trigger_funnel_url_change` (AFTER INSERT/UPDATE/DELETE)
- `trigger_campaign_funnel_urls_revenue_calculation` (AFTER INSERT/UPDATE/DELETE)

**A chave do join custo × receita é igualdade de string exata**, e a normalização é imposta por `clean_funnel_url`, cujo corpo eu li:

```
TRIM(TRAILING '/' FROM
  REGEXP_REPLACE(REGEXP_REPLACE(TRIM(NEW.url), '^https?://','', 'i'), '^www\.','', 'i'))
```

**Correção importante:** essa função **não faz lowercase**. Ela remove esquema, `www.` e barra final, e apara espaços — só isso. Um host em maiúscula **não** é normalizado e faria a receita ir a zero em silêncio.

Formato medido nos dois lados, e eles batem byte a byte:
`portalmundomais.com/rec/como-baixar-rg-digital-govbr` · `portalmundomais.com/r/senai-cursos-gratuitos-2026`

E ele é **diferente** de `campaigns.lp_path`, que no banco é `/r/senai-cursos-gratuitos-2026/` — path com barra inicial **e** final. **Não unifique os dois por estética:** o de `campaign_funnel_urls` é chave de join; mexer nele quebra a receita.

## 7.2 O contrato que esta página grava HOJE

### Coluna nova: `pautador_funnel_runs.paginas_publicadas jsonb not null default '[]'::jsonb`

Um objeto por página, gravado **apenas a partir da resposta REST do WordPress**, nunca reconstruído:

```jsonc
{
  "page_number": 1,
  "role": "LP",
  "post_type": "r",
  "post_id": 4821,
  "slug": "senai-cursos-gratuitos-2026",        // o que o WP DEVOLVEU
  "url_absoluta": "https://portalmundomais.com/r/senai-cursos-gratuitos-2026/", // campo `link`, VERBATIM
  "url_join": "portalmundomais.com/r/senai-cursos-gratuitos-2026",
  "status_wp": "draft",
  "publicado_em": "2026-08-17T14:22:31Z"
}
```

**Por que verbatim e não montado:** o slug é mutável em três pontos independentes — `_slug_com_sufixo` (`adapters/briefing_volc.py:132-141`), `dedupe_slugs` (`steps.py:287-300`) e o próprio WordPress, que acrescenta `-2` quando o slug já existe e só conta isso na resposta REST. O `worker.py:27-30` documenta que por isso **fixa o timestamp** em vez de adivinhar o slug.

**`url_join` é espelho, não fonte.** Ele existe para a tela exibir e para conferência. Quem normaliza de verdade é o trigger `clean_funnel_url` no `INSERT` em `campaign_funnel_urls` — duas implementações da mesma regra são duas chances de divergir.

### Coluna nova: `pautador_funnel_runs.lp_url text`

A URL absoluta da LP, desnormalizada. Não é redundância inútil: é o campo que o módulo de campanha lê para preencher `Brief.url_final` (que exige `https`) sem varrer o jsonb. Uma campanha tem uma LP; o resto do funil é destino de navegação, não de anúncio.

### Quem escreve, em três saltos

1. **O motor.** Novo campo `RunState.published: dict[int, PaginaPublicada]` (`domain/models.py:267-297` hoje **não tem** campo de publicação). `step_publish` já recebe o `result` completo em `steps.py:2504` e hoje só extrai o `post_id` — passa a gravar o objeto inteiro. Vai para `state.json` de graça, porque `state.json` é `RunState.to_json()`.
2. **O worker.** `resumo_do_estado` (`worker.py:130-157`) projeta `estado["published"]` e `_COLUNAS` (`worker.py:267`) passa a incluir `paginas_publicadas` e `lp_url`.
3. **A API.** `RunDoRedator` (`publicacao.py:416-427`) expõe os dois.

### Aresta de volta: `campaigns.funnel_run_id bigint references public.pautador_funnel_runs(id)`

Confirmado no banco que **não existe** hoje. É ela que fecha o ciclo — `campaigns` → run → `opportunity_id` → card. A direção é essa (a campanha aponta para o run) porque um run pode gerar várias campanhas: Search, Display e retomadas. Sem ela, responder "aquele tema deu certo?" por SQL é impossível.

### Colunas novas de suporte (§8)

`passos jsonb`, `paginas jsonb`, `passos_hash text`, `teto_usd numeric(12,6)`, `teto_pagina_usd numeric(12,6)`.

**Achado colateral:** `DispararEntrada` **aceita** `teto_usd` e `teto_pagina_usd` (`publicacao.py:410-412`) e os repassa ao perfil (`publicacao.py:544`), mas eles **não são persistidos** — a tabela tem 13 colunas e nenhuma delas. A régua de custo precisa do teto; hoje ele é esquecido no instante do disparo.

## 7.3 A cadeia completa, com a chave de cada salto

| # | De → Para | Chave | Estado hoje |
|---|---|---|---|
| 1 | card → run | `pautador_funnel_runs.opportunity_id` (FK) | ✅ existe |
| 2 | run → site | `pautador_funnel_runs.project_id` (FK) + `project_wordpress` | ✅ existe |
| 3 | run → páginas publicadas | **`paginas_publicadas[].url_absoluta`**, verbatim do WP | ❌ **quebrado** — o `result` é descartado (`steps.py:2517`) |
| 4 | run → LP | **`lp_url`** | ❌ não existe |
| 5 | LP → campanha | `campaigns.campaign_id` (id numérico do Google Ads, varchar; medido: `23524108985`) + **`campaigns.funnel_run_id`** | ❌ **manual**; `lp_path` não serve |
| 6 | campanha → URLs do funil | `campaign_funnel_urls.campaign_id` (FK) + `url` | ⚠️ existe, mas **digitado à mão** no `FunnelUrlsEditor` |
| 7 | URL → receita | `adsense_metrics.url` **= igualdade de string** `campaign_funnel_urls.url` | ✅ **sólido** |
| 8 | receita → dashboard | `daily_campaign_metrics.revenue_converted` por `campaign_id` | ✅ existe |
| 9 | campanha → custo | `utm_campaign = {campaignid}` via `final_url_suffix` → `auto_create_campaign_from_gam` | ✅ existe |

**Ordem obrigatória e contra-intuitiva:** `campaign_funnel_urls.campaign_id` é FK para `campaigns.campaign_id`, e `campaigns` hoje nasce por `auto_create_campaign_from_gam` — ou seja, **depois do primeiro clique pago**. O run termina muito antes disso. Portanto **o run NÃO pode gravar em `campaign_funnel_urls`**; ele grava em `paginas_publicadas`, e o módulo de campanha **copia** quando a campanha nascer. É por isso que o contrato mora no run.

## 7.4 O que o módulo de campanha vai ter de consertar (fora do escopo desta página, documentado aqui)

1. **`enrich_campaign_with_google_ads` quebra silenciosamente com a taxonomia nova.** Li o `prosrc` no banco: `extracted_url := regexp_replace(campaign_name, '^[^/]*/ [^/]* / ', '', 'g')`, depois `IF position('.' in extracted_url) > 0 THEN ... INSERT INTO campaigns ...` — **e não há `ELSE`**. Fora do `IF`, ela sempre grava `INSERT INTO sync_logs (... 'success', 'Dados sincronizados')`. Como `volc_ads/campanha/taxonomia.py` põe um **slug sem ponto** no terceiro campo (`D2 - 104 / Pis Pasep [Display] / pis-pasep-entenda-tudo`, medido em `taxonomia.py:71-92`), o resultado seria: log verde e **zero linha em `campaigns`**.
2. **Três convenções de nome vivas ao mesmo tempo**, e a que o construtor emite não é nenhuma das duas formalizadas: `volc_ads/campanha/search.py:27` faz `base = f"{brief.prefixo_nome} {brief.pais} {ts} {brief.nicho[:28]}"`.
3. **Recomendação:** parar de derivar o `project_id` do nome. Ele passa a vir de `funnel_run_id`, que já o tem. O nome volta a ser leitura humana.
4. **Portão obrigatório:** campanha só pode ser criada a partir de um run cujas páginas estejam `status_wp = "publish"`. Hoje o funil inteiro sobe como rascunho (`config.yaml:22`, `publish_status: draft`, reforçado por `set_status` como última escrita em `steps.py:2536-2537`). Apontar campanha para rascunho é gastar mutate e arriscar reprovação de política contra um 404.

## 7.5 Defeito de identidade de URL dentro do motor

`index_decision_for` (`steps.py:303-310`, chamado em `:1784`) monta `canonical = f"{settings.site.domain}/{settings.site.post_type}/{page.slug}"` para **toda** página. Mas a LP é publicada em `lp_post_type` (`r`), não `post_type` (`rec`) — o próprio `step_publish` distingue os dois ao escolher `yoast_pt` (`steps.py:2518-2520`). Resultado: a LP publicada em `/r/<slug>` declara canonical `/rec/<slug>`, uma URL que não existe. É defeito de SEO hoje e sintoma do problema de fundo: **não há uma função única no motor que responda "qual é a URL desta página"**. O contrato de elo deve criar essa função, e `index_decision_for` deve passar a usá-la.

---

# 8. CONTRATO DE API

## 8.1 O que já existe (não mexer, exceto onde marcado)

| Rota | Arquivo | Mudança necessária |
|---|---|---|
| `POST /api/publicacao/redator/disparar` | `publicacao.py:458` | persistir `teto_usd`/`teto_pagina_usd` na linha |
| `POST /api/publicacao/redator/runs/{run_row_id}/cancelar` | `publicacao.py:567` | nenhuma |
| `GET /api/publicacao/redator/runs?opportunity_id=` | `publicacao.py:599` | acrescentar campos a `RunDoRedator` |
| `GET /api/publicacao/destinos` | `publicacao.py:332` | nenhuma |

## 8.2 Migração de banco — `src/sql/pautador/04_redator_matriz.sql`

> ⚠️ Existe um `src/sql/volc-sync/04_*` **bloqueado** por dois defeitos destrutivos (`src/sql/volc-sync/README.md`). Este arquivo é de outra pasta e não tem relação — mas o nome colide visualmente. Usar `src/sql/pautador/04_redator_matriz.sql` e nunca `src/sql/volc-sync/04_*`.

```sql
begin;

alter table public.pautador_funnel_runs
  add column if not exists passos              jsonb  not null default '{}'::jsonb,
  add column if not exists paginas             jsonb  not null default '[]'::jsonb,
  add column if not exists paginas_publicadas  jsonb  not null default '[]'::jsonb,
  add column if not exists lp_url              text,
  add column if not exists passos_hash         text,
  add column if not exists teto_usd            numeric(12,6),
  add column if not exists teto_pagina_usd     numeric(12,6);

comment on column public.pautador_funnel_runs.passos is
  'Projeção de RunState.step_status. Chaves <tipo>_p<N>, mais as run-level '
  '(extract, engajamento, funnel_graph) e as de exceção (budget_pN, page_N — '
  'esta ÚLTIMA sem o "p", ver pipeline.py:369).';
comment on column public.pautador_funnel_runs.paginas_publicadas is
  'Uma entrada por página, montada a partir da RESPOSTA REST do WordPress. '
  'url_absoluta é o campo `link` verbatim. url_join é ESPELHO para exibição: '
  'a normalização de verdade é o trigger clean_funnel_url em '
  'campaign_funnel_urls (remove esquema, www e barra final; NÃO faz lowercase).';

alter table public.campaigns
  add column if not exists funnel_run_id bigint
    references public.pautador_funnel_runs(id) on delete set null;

create index if not exists campaigns_funnel_run_idx
  on public.campaigns (funnel_run_id) where funnel_run_id is not null;

commit;
```

RLS de `pautador_funnel_runs` já está ligada com zero policy (`02_publicacao_por_projeto.sql:179-183`) — colunas novas herdam isso. **Toda rota nova nasce com a mesma disciplina: passa pelo backend com `service_role`, nunca pelo client Supabase do browser.**

## 8.3 `GET /api/publicacao/redator/runs/{run_row_id}` — **NOVA**

A rota da página do run. Suporta `If-None-Match`.

**Request:** `GET /api/publicacao/redator/runs/42`
**Headers opcionais:** `If-None-Match: "a3f9…"`

**Response 200:**

```jsonc
{
  "run": {
    "id": 42,
    "opportunity_id": 118,
    "project_id": 1,
    "run_id": "senai-cursos-gratuitos-2026-20260817-142201",
    "status": "running",
    "modo": "publicado",
    "custo_usd": 2.0242,
    "paginas_planejadas": 5,
    "paginas_geradas": 3,
    "teto_usd": 3.00,
    "teto_pagina_usd": 0.60,
    "erro": null,
    "criado_em": "2026-08-17T14:22:01Z",
    "atualizado_em": "2026-08-17T14:44:19Z",
    "lp_url": null
  },
  "colunas": [
    {"chave":"research","rotulo":"pesquisa","paga":true,"existencial":true},
    {"chave":"write","rotulo":"redação","paga":true,"existencial":true},
    {"chave":"judge","rotulo":"juiz","paga":true,"existencial":true},
    {"chave":"seo","rotulo":"seo","paga":true,"existencial":false},
    {"chave":"image","rotulo":"prompt img","paga":true,"existencial":false},
    {"chave":"image_gen","rotulo":"imagem","paga":true,"existencial":false},
    {"chave":"screenshot","rotulo":"print","paga":false,"existencial":false},
    {"chave":"build","rotulo":"montar","paga":false,"existencial":false},
    {"chave":"widget","rotulo":"widget","paga":true,"existencial":false},
    {"chave":"content_gate","rotulo":"portão","paga":false,"existencial":true},
    {"chave":"publish","rotulo":"publicar","paga":false,"existencial":false}
  ],
  "paginas": [
    {
      "numero": 1, "papel": "LP", "slug": "senai-cursos-gratuitos-2026",
      "h1": "Cursos gratuitos do SENAI 2026", "engajamento": null,
      "aplicaveis": ["research","write","seo","image","image_gen","build","content_gate","publish"],
      "bloqueada": false,
      "url_prevista": "https://portalmundomais.com/r/senai-cursos-gratuitos-2026",
      "publicada": null
    }
  ],
  "run_level": {
    "extract": {"status":"OK","tentativas":1,"custo_usd":0.0239,"issues":[]}
  },
  "celulas": {
    "write_p4": {
      "status":"RETRIED","tentativas":2,"modelo":"gemini-3.5-flash",
      "custo_usd":0.18208380,"latencia_ms":86384,
      "prompt_tokens":29306,"completion_tokens":16573,
      "issues":[]
    }
  },
  "totais": {
    "custo_usd": 2.0242,
    "custo_por_pagina_construida": 0.4148,
    "custo_por_pagina": {"1":0.2439,"2":0.2362,"3":0.2986},
    "subestimado": true,
    "motivo_subestimacao": "widget SKIPPED e engajamento gravam telemetria zerada (steps.py:1942, :2624)"
  },
  "em_andamento": "write_p4",
  "sem_cobranca_ha_ms": 187204,
  "artefatos": {"pasta":"senai-…-20260817-142201","arquivos":["p1.elementor.json","report.md"]},
  "versao": "a3f9c21e4b…"
}
```

**Response 304 Not Modified** quando `If-None-Match` bate com `versao`. Medido: ~93% das consultas de polling não trazem mudança — sem isto o polling de 3s é 644 requisições por run com 596 desperdiçadas.

**404** se a linha não existe. **`versao`** = `sha256` do dicionário `passos` serializado com chaves ordenadas; é o mesmo valor gravado em `passos_hash`.

**Regra de honestidade no serializador:** para colunas com `paga:false`, os campos `custo_usd`, `latencia_ms`, `modelo`, `prompt_tokens` e `completion_tokens` são **omitidos**, não zerados. O front nunca precisa decidir se um zero é medição ou ausência.

## 8.4 `POST /api/publicacao/redator/runs/{run_row_id}/publicar` — **NOVA** (ver §11.1)

Promove rascunhos a publicados. Sem ela, o módulo de Google Ads não tem para onde apontar.

**Request:**
```jsonc
{ "paginas": [1,2,3,4,5] }   // ou {"todas": true}
```

**Response 200:**
```jsonc
{
  "publicadas": [
    {"page_number":1,"post_id":4821,"status_wp":"publish",
     "url_absoluta":"https://portalmundomais.com/r/senai-cursos-gratuitos-2026/"}
  ],
  "falhas": [{"page_number":3,"erro":"401 do WordPress"}]
}
```

**409** se o run não está `done`. **409** se `paginas_publicadas` está vazio. Atualiza `status_wp` **e** `url_absoluta` a partir da resposta do WP (o link pode mudar ao sair de draft — **não verificado** se muda nesta instalação; por isso relê e regrava em vez de assumir).

## 8.5 Rotas de configuração — **NOVAS**

| Rota | Faz |
|---|---|
| `GET /api/publicacao/redator/config` | Devolve os 3 baldes: `{doutrina:{...}, motor:{...}, somente_leitura:[{nome, corpo, motivo, referencia}]}`, mais `ativo:{prompts:{}, config_id}` e o escopo. |
| `GET /api/publicacao/redator/config/versoes?nome=redator_p1` | Histórico: `[{id, hash, autor, notas, criado_em}]`, mais novo primeiro. |
| `POST /api/publicacao/redator/config/validar` | Body `{nome, corpo}`. Roda (a)+(b)+(c). Response `{ok, erros:[{tipo,mensagem}], marcadores:[{marcador,presente}]}`. **Não grava.** |
| `POST /api/publicacao/redator/config/testar` | Roda a suíte do motor. Response `{ok, passaram, falharam, duracao_s, saida}`. Timeout 120s. |
| `POST /api/publicacao/redator/config/salvar` | Body `{nome, corpo, notas}`. Roda (a)+(b)+(c)+(d); **recusa com 422** se qualquer uma falhar. Insere linha nova e move o ponteiro. Response `{version_id, hash}`. |
| `POST /api/publicacao/redator/config/ativar` | Body `{nome, version_id, project_id?}`. Move só o ponteiro. |

**Autorização:** só ADMIN. **Não verificado:** qual é o mecanismo de papel/role em uso hoje no backend — não auditei `backend/app/` fora de `redator/` e `routers/publicacao.py`. Precisa ser confirmado antes de implementar.

## 8.6 Mudanças no worker

```python
# worker.py:267 — passa a ser
_COLUNAS = {"run_id", "paginas_planejadas", "paginas_geradas", "custo_usd",
            "passos", "paginas", "paginas_publicadas", "lp_url", "passos_hash"}
```

E `_acompanhar` (`worker.py:278-300`) compara por **hash** (`passos_hash`), não pelo dicionário inteiro: `if valores and valores != ultimo` continua valendo, mas `valores["passos_hash"]` entra na comparação — assim uma etapa que não altera custo nem contagem de páginas **passa a gerar escrita**, que é exatamente o que hoje não acontece. `passos` sozinho pesa 12,6KB (6,6% dos 191,9KB do `state.json`); a ~48 rajadas por run isso é irrelevante. `drafts` (108KB) e `facts` (36KB) **nunca** vão para o banco nem para o browser.

## 8.7 Rota do front

`src/App.tsx`: acrescentar `<Route path="/redator" …>` e `<Route path="/redator/run/:runId" …>`, ambas dentro de `<ProtectedRoute>`, seguindo o padrão das 16 rotas existentes (`App.tsx:43-73`).

---

# 9. CRITÉRIOS DE ACEITE

1. `GET /api/publicacao/redator/runs/{id}` responde 200 com `celulas`, `paginas`, `colunas` e `versao` para um run gravado; responde 404 para id inexistente.
2. Reenviando `If-None-Match` com o valor de `versao` recebido, a mesma rota responde **304** com corpo vazio.
3. `pautador_funnel_runs` tem as colunas `passos`, `paginas`, `paginas_publicadas`, `lp_url`, `passos_hash`, `teto_usd`, `teto_pagina_usd`, todas com `not null default` onde aplicável, e `campaigns.funnel_run_id` existe com FK para `pautador_funnel_runs(id)`.
4. `_COLUNAS` inclui `passos` e a gravação acontece **sempre que `passos_hash` muda**, mesmo quando `custo_usd`, `paginas_planejadas` e `paginas_geradas` não mudam.
5. Para o `state.json` de `funnelforge-migracao/referencia/run-fgts-producao`, `resumo_do_estado` produz 55 chaves em `passos`, `custo_usd == 2.547234` (6 casas) e `paginas_geradas == 7`.
6. A máscara `aplicaveis` do mesmo run **não** inclui `judge` na página 1, nem `screenshot`/`widget` nas páginas 1 a 4, e **inclui** os três nas páginas 5 a 7 — 9 exclusões estruturais no total.
7. O parser de chaves classifica `write_p3` → `("write", 3)`, `image_gen_p2` → `("image_gen", 2)`, `blocked_p2` → `("blocked", 2)`, `budget_p5` → `("budget", 5)`, `page_5` → `("page", 5)` **na linha da página 5**, e `funnel_graph` → run-level.
8. Renderizando o payload do run de referência, a matriz mostra 7 linhas × 11 colunas; as células de `judge_p1`, `screenshot_p1..4` e `widget_p1..4` recebem `data-estado="nao-se-aplica"` e `aria-label` contendo "não se aplica".
9. Nenhum dos sete estados de célula é distinguível **apenas** por cor: cada um tem `data-estado` distinto, geometria distinta e `aria-label` distinto. Um teste que remova todo `color`/`background-color` ainda distingue os sete.
10. As cores `--success`, `--warning` e `--info` **não aparecem** em nenhuma regra que codifique estado de célula (elas reprovam 4,5:1 no tema claro: 3,03 / 2,38 / 2,76 medidos).
11. A altura do bloco de `write_p7` (US$ 0,27271335) é ≥ 10× a de `image_p4` (US$ 0,0025980) na mesma matriz.
12. Células de colunas com `paga:false` (`build`, `publish`, `screenshot`, `content_gate`) **não** exibem a string `US$` em nenhum lugar — nem na célula, nem no popover.
13. O total de custo exibido vem acompanhado do rótulo de subestimação sempre que existir ao menos um `widget_pN` com status `SKIPPED` ou um `engajamento` no `passos`.
14. Com o run em `running` e a célula corrente inalterada há > 180s, a tela exibe o rótulo `sem cobrança há M:SS`.
15. Quando existe `blocked_pN`, todas as células aplicáveis à direita da coluna que falhou naquela linha recebem `data-estado="cancelada"`, e nenhuma delas fica em `pendente`.
16. Quando `funnel_graph` está FAILED, a tela exibe o texto de portão barato (contendo "antes de gastar") e **não** exibe o texto genérico de erro do motor.
17. Com `prefers-reduced-motion: reduce`, nenhum elemento da matriz tem `animation` ativa; o cronômetro continua atualizando.
18. Em viewport de 375px o `document.body` **não** rola horizontalmente com uma matriz de 7×11.
19. `step_publish` grava `RunState.published[page_number]` com `post_id`, `slug`, `url_absoluta` e `status_wp` vindos da resposta do WordPress; `url_absoluta` é byte a byte o campo `link` devolvido.
20. `url_join` de cada página, submetido a `clean_funnel_url`, resulta **nele mesmo** (idempotência) — sem esquema, sem `www.`, sem barra final.
21. `lp_url` é preenchido com a `url_absoluta` da página cujo `role == "LP"`, e é `null` quando nenhuma página com esse papel publicou.
22. A tela mostra cada URL publicada como link `<a href>` clicável com o `status_wp` ao lado.
23. `POST /api/publicacao/redator/config/salvar` com `redator_p1` sem a contagem "3 strings" no corpo responde **422** e **não** insere linha em `redator_prompt_versions`.
24. `POST .../config/salvar` com `BANNED_CTA_EXECUTION` acrescido de `"consultar"` responde 422 citando os exemplares aprovados que passariam a ser banidos.
25. `GET /api/publicacao/redator/config` devolve `judge`, `extractor`, `declarador_engajamento` e as REGRAS TÉCNICAS do widget no balde `somente_leitura`, cada um com `motivo` e `referencia` não vazios; e `routing` **não** aparece em nenhum balde editável.
26. `POST .../config/ativar` com um `version_id` anterior restaura o corpo daquela versão sem alterar nenhuma linha de `redator_prompt_versions`.
27. Nenhuma rota nova usa o client Supabase do browser: `grep -rn "campaign_funnel_urls\|pautador_funnel_runs" src/services src/lib` não retorna nova ocorrência de `pautador_funnel_runs`.
28. O campo `erro` do run nunca é renderizado cru: sempre truncado em 240 caracteres com o restante dentro de um `<details>` fechado.
29. `npx tsc --noEmit -p tsconfig.app.json` não acrescenta **nenhum** erro além dos 76 herdados do webgo documentados em `CLAUDE.md`.
30. `cd funnelforge-migracao/engine && .venv/bin/python -m pytest -q` continua em **615 passed** ou mais, nunca menos.

---

# 10. OS TESTES

## 10.1 Motor (`funnelforge-migracao/engine/tests/`, pytest — hoje 615 passed em 5,14s)

| Teste | Trava |
|---|---|
| `test_publish_grava_url_do_wordpress` | Critério 19. Publisher falso devolve `{"id":4821,"slug":"x-2","link":"https://d/r/x-2/","status":"draft"}`; assere `state.published[1].url_absoluta == "https://d/r/x-2/"` e `slug == "x-2"` (o `-2` do WP, não o slug do plano). |
| `test_publish_nao_reconstroi_url_a_partir_do_slug_do_plano` | Critério 19. Publisher devolve slug **diferente** do plano; falha se a URL gravada usar o slug do plano. |
| `test_url_join_e_idempotente_sob_clean_funnel_url` | Critério 20. Reimplementa a regra medida do trigger (remove `^https?://`, `^www\.`, trailing `/`, **sem lowercase**) e assere ponto fixo. |
| `test_lp_url_usa_lp_post_type_e_nao_post_type` | Critério 21 + §7.5. Trava o defeito de `index_decision_for`: LP tem de sair em `/r/`, nunca `/rec/`. |
| `test_canonical_da_lp_usa_a_mesma_funcao_de_url` | §7.5. Falha enquanto `index_decision_for` montar canonical com `post_type` para a LP. |
| `test_widget_skip_preserva_telemetria` | §5.6. Assere que `_widget_skip` copia `cost_usd`/`latency_ms`/`attempts` do `res`. **Falha hoje** — é o teste que prova o defeito. |
| `test_engajamento_preserva_telemetria` | §5.6. Idem para `steps.py:2620-2631`. **Falha hoje.** |
| `test_exemplares_aprovados_nao_sao_banidos` | Critério 24 + §6.7.1. `banned_cta_execution_hit` sobre os 6 `APPROVED_CTA_EXEMPLARS` tem de devolver `None` em todos. **Falha hoje** (`'Como fazer a solicitação pelo app >>>'` → `'solicit'`). |
| `test_banned_official_completo_nos_quatro_prompts` | §6.7.2. Renderiza os 4 redatores e assere que as 6 frases de `BANNED_OFFICIAL` aparecem em todos. **Falha hoje** em `redator_pages` e `redator_presell`. |
| `test_run_volc_aceita_config_explicito` | §6.4. Chama `run-volc --config <tmp>` e assere que `load_settings` recebeu o caminho. |
| `test_choiceloader_prefere_o_diretorio_do_env` | §6.4. Com `FUNNELFORGE_PROMPTS_DIR` apontando para um `.jinja` fantoche, `render()` devolve o fantoche; sem a var, devolve o do pacote. |
| `test_todos_os_arquetipos_do_catalogo_sao_alcancaveis` | §6.7.3. Assere que os 9 arquétipos de `redator_widget.jinja:27-43` são alcançáveis por `ENGAJAMENTO_PARA_ARQUETIPO`. **Falha hoje** (4 de 9). |
| `test_seo_prompt_e_validador_concordam` | §6.7.4. Extrai o número do prompt e compara com o limiar de `seo_limits`. **Falha hoje** (155 vs 160). |

## 10.2 Backend (`backend/tests/`, pytest — hoje 10 testes em `test_redator_worker.py`)

| Teste | Trava |
|---|---|
| `test_resumo_do_estado_projeta_a_matriz_do_run_real` | Critério 5. Carrega o `state.json` de referência e assere 55 chaves, `custo_usd == 2.547234`, `paginas_geradas == 7`. |
| `test_colunas_inclui_passos_e_paginas_publicadas` | Critério 4. Assere as 9 chaves de `_COLUNAS`. |
| `test_acompanhar_grava_quando_so_o_hash_muda` | Critério 4. Dois `state.json` com o mesmo custo e `step_status` diferente → duas chamadas a `_atualizar`. **Falha hoje.** |
| `test_acompanhar_nao_grava_quando_nada_muda` | Contrapartida: 10 leituras idênticas → 1 escrita. |
| `test_mascara_de_aplicabilidade_do_run_real` | Critério 6. As 9 exclusões exatas, nomeadas uma a uma. |
| `test_mascara_usa_role_e_nao_page_type` | §5.1. Página com `page_type == "HUB"` e `role == "PRESELL"` não pode receber `widget` como aplicável. |
| `test_mascara_exclui_widget_quando_engajamento_e_dado_unico` | §5.2. |
| `test_parse_de_chave_cobre_page_N_e_image_gen` | Critério 7. Os 5 casos da tabela, incluindo `page_5` → linha da página 5. |
| `test_rota_detalhe_devolve_304_com_etag` | Critério 2. |
| `test_rota_detalhe_404_para_id_inexistente` | Critério 1. |
| `test_serializador_omite_custo_em_coluna_nao_paga` | Critério 12. As chaves `custo_usd`/`latencia_ms`/`modelo` **ausentes** em `build_p1`, não zeradas. |
| `test_teto_usd_e_persistido_no_disparo` | §7.2. Dispara com `teto_usd=3.0` e assere a coluna gravada. **Falha hoje.** |
| `test_lp_url_derivada_da_pagina_com_papel_lp` | Critério 21. |
| `test_publicar_recusa_run_que_nao_terminou` | §8.4. 409 quando `status != "done"`. |
| `test_config_salvar_recusa_prompt_sem_marcador` | Critério 23. Assere 422 **e** zero linha inserida. |
| `test_config_salvar_recusa_doutrina_que_bane_exemplar_aprovado` | Critério 24. Com `"consultar"` adicionado, 422 citando os exemplares. |
| `test_config_lista_somente_leitura_com_motivo` | Critério 25. Os 4 itens presentes, `motivo`/`referencia` não vazios, `routing` ausente dos editáveis. |
| `test_config_ativar_nao_altera_versoes` | Critério 26. |
| `test_erro_do_run_e_truncado` | Critério 28. Erro de 800 chars → 240 na resposta. |

## 10.3 Front (vitest)

⚠️ `vitest.config.ts` hoje usa `environment: 'node'` e `include: ['src/**/*.{test,spec}.{ts,tsx}']`. Testes de componente exigem `jsdom` — acrescentar `environmentMatchGlobs` ou um segundo projeto, e instalar `jsdom` + `@testing-library/react`. **Esse setup é pré-requisito, não detalhe.**

| Teste | Trava |
|---|---|
| `matriz/parseChave.test.ts` | Critério 7, no lado do front (o parse é duplicado por necessidade de render). |
| `matriz/estadoDaCelula.test.ts` | Critérios 8 e 15. Tabela-verdade completa: (aplicável × presente × status × bloqueada) → um dos sete `data-estado`. |
| `matriz/semCor.test.tsx` | **Critério 9.** Renderiza uma matriz com os sete estados, coleta `data-estado` + `aria-label` + a geometria (`data-forma`), e assere que os sete são mutuamente distintos **ignorando toda propriedade de cor**. |
| `matriz/tokensProibidos.test.tsx` | Critério 10. Falha se o HTML renderizado contiver `--success`, `--warning` ou `--info`. |
| `matriz/alturaProporcionalAoCusto.test.tsx` | Critério 11. |
| `matriz/colunaNaoPagaOmiteCusto.test.tsx` | Critério 12. Falha se `US$` aparecer numa célula de `build`/`publish`/`screenshot`/`content_gate`. |
| `matriz/avisoDeSubestimacao.test.tsx` | Critério 13. |
| `matriz/semCobrancaHa.test.tsx` | Critério 14. Com timers falsos, 181s sem mudança → o rótulo aparece. |
| `matriz/caudaCancelada.test.tsx` | Critério 15. |
| `matriz/reducedMotion.test.tsx` | Critério 17. Com `matchMedia` mockado, nenhum `animation` ativo; o cronômetro continua. |
| `matriz/funnelGraphFailed.test.tsx` | Critério 16. |
| `run/urlClicavel.test.tsx` | Critério 22. |
| `run/erroTruncado.test.tsx` | Critério 28. |
| `run/estadoVazio.test.tsx` | §4.1. Sem runs → o texto do Pautador Pro, não um skeleton. |

## 10.4 Integração

| Teste | Trava |
|---|---|
| `test_ciclo_run_ate_campanha` (backend, banco de teste) | §7.3. Insere run com `paginas_publicadas`; insere `campaigns` com `funnel_run_id`; copia as URLs para `campaign_funnel_urls`; assere que **cada** `url_join` gravado bate byte a byte com o valor pós-trigger. |
| `test_join_de_receita_encontra_as_urls` | §7.1. Insere linhas em `adsense_metrics` com as mesmas URLs e assere que `aggregate_adsense_funnel_revenue` devolve receita > 0. |
| `test_url_com_www_ou_barra_final_ainda_bate` | §7.1. Grava `https://www.d.com/r/x/` e assere que o trigger normaliza para `d.com/r/x`. |
| `test_url_com_host_em_maiuscula_NAO_bate` | §7.1. **Documenta o defeito medido**: `clean_funnel_url` não faz lowercase. Este teste registra o comportamento atual; se um dia a função ganhar `lower()`, ele quebra e alguém revisa a decisão. |
| `test_matriz_do_run_de_referencia_ponta_a_ponta` | Critérios 5, 6, 7, 8. Copia o `state.json` de referência para uma pasta de run falsa, roda `_acompanhar` uma vez, lê a rota nova e assere o payload completo. |
| `test_config_editada_chega_ao_motor` (lento, sem LLM) | §6.4. Grava versão de prompt, ativa, dispara com LLM falso, e assere que o corpo renderizado veio do diretório de override. |

---

# 11. DECISÕES QUE DEPENDEM DO OPERADOR

**11.1 — `POST .../publicar` (draft → publish) entra na v1 ou fica para o módulo de campanha?**
Sem ela, o funil fica em rascunho e a campanha não tem para onde apontar; com ela, a `/redator` ganha uma ação que escreve no site do cliente.
→ *Recomendação: entra na v1, por página e com confirmação — sem isso o elo com o Google Ads nasce quebrado no dia da entrega.*

**11.2 — Consertar a contradição do CTA (`'Como fazer a solicitação pelo app >>>'`) tirando o exemplar ou tirando `solicit` da lista de banidos?**
São duas leituras diferentes do que é "verbo de execução de serviço".
→ *Recomendação: tirar o exemplar da lista de aprovados — a regra do validador é a que protege de reprovação de política, e é ela que deve mandar.*

**11.3 — Escopo de configuração na v1: só global, ou já global + por projeto?**
O modelo de dados suporta os dois desde o começo (§6.4); a pergunta é se a **tela** já expõe o seletor.
→ *Recomendação: modelo com os dois, tela só com global na v1 — o segundo site ainda não existe, e um seletor sem alternativa confunde.*

**11.4 — Quem pode salvar prompt?**
Prompt editável é superfície de injeção: quem edita controla o que o modelo faz com o artigo. Os prompts já carregam defesa anti-injeção para o **conteúdo** (`redator_widget.jinja:22`, `declarador_engajamento.jinja:44`), mas nada protege do lado do editor.
→ *Recomendação: só ADMIN, com autor e timestamp gravados em toda linha. **Não verificado** qual é o mecanismo de papel do backend hoje — confirmar antes de implementar.*

**11.5 — Quatro casas decimais no custo assusta ou informa?**
Duas casas apagariam metade da matriz (as células vão de US$ 0,0026 a US$ 0,2727), mas `US$ 2,0242` é incomum numa tela de gestão.
→ *Recomendação: quatro casas na célula e no total ao vivo, duas casas no histórico da lista de runs.*

**11.6 — A régua de custo mostra o teto do run, o teto por página, ou os dois?**
São dois eventos diferentes: o teto de página aborta uma página, o teto de run quebra o laço (`pipeline.py:352-364`).
→ *Recomendação: o teto do run na régua principal e o teto de página como um traço fino dentro de cada linha da matriz.*

**11.7 — Consertar `enrich_campaign_with_google_ads` agora ou junto com o módulo de campanha?**
Ela hoje não quebra nada (as 3 campanhas usam o formato antigo), mas quebrará em silêncio no dia em que a taxonomia nova subir a primeira campanha.
→ *Recomendação: acrescentar um `ELSE` que grave `sync_logs` com status `'warning'` **agora**, num patch de 4 linhas — o conserto de fundo (parar de derivar `project_id` do nome) fica para o módulo de campanha.*

**11.8 — Versionar `doctrine.py` como texto Python ou como dados?**
Hoje é módulo Python; versionar o arquivo inteiro dá diff limpo, mas permite executar código.
→ *Recomendação: versionar como **dados** (as 6 listas + o texto de compliance em JSON) e gerar o módulo — prompt editável já é superfície de injeção suficiente sem somar execução arbitrária.*

**11.9 — O run de referência é de 21/07 e não representa a produção.**
Ele rodou com 3 hubs (7 páginas) e **não tem** `content_gate_pN`, `image_gen_pN` nem `blocked_pN` — confirmei listando as 55 chaves. A produção terá 5 linhas e duas colunas a mais.
→ *Recomendação: rodar um funil real de 5 páginas com a config atual **antes** de fechar o layout, e usar esse `state.json` como fixture dos testes — o de julho fica só como caso histórico.*

**11.10 — Os defeitos de telemetria (`widget` SKIPPED e `engajamento` zerados) entram no mesmo PR ou em um anterior?**
São conserto no motor, não na tela, e enquanto existirem o número exibido é menor que a fatura.
→ *Recomendação: PR anterior e separado — dois testes que hoje falham (`test_widget_skip_preserva_telemetria`, `test_engajamento_preserva_telemetria`) e uma linha de código cada.*

---

## Anexo — o que NÃO foi verificado

- A fórmula de origem de `ecpm`, `cpc`, `rps` e `roas` em `daily_campaign_metrics`: as colunas chegam prontas de processo externo (n8n) que não está neste repositório.
- O mecanismo de papel/role do backend (§8.5, §11.4): não auditei `backend/app/` fora de `redator/` e `routers/publicacao.py`.
- Se o campo `link` do WordPress muda ao promover um post de `draft` para `publish` nesta instalação (§8.4).
- Se o stdout do motor, que vai para `pautador_funnel_runs.erro` truncado em 800 caracteres (`worker.py:266`), pode carregar a senha do WordPress em alguma trilha de exceção (§4.6e).
- O conteúdo de `volc_ads/` além de `README.md`, `campanha/taxonomia.py` e `campanha/search.py:27` — e note que o diretório inteiro está **untracked** no git (`git status`: `?? volc_ads/`), então um `git clean` o apaga.
