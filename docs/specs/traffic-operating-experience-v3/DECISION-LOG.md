# DECISION-LOG — o que foi decidido, o que foi recusado, e por quê

Base factual: `207e91f`. Cada decisão tem: **evidência**, **reversibilidade**, **questão em aberto** e **dono futuro**.

---

## 1. Decisões de topologia e forma

### D1 · A Bancada Guiada (B como tela, A como rail, C como modelo)

**Aceita.** Registrada em `EXPERIENCE-ARCHITECTURE.md §3.3`.
**Evidência:** a mesa de Termos compara 23 linhas com volume, CPC e correspondência; uma pergunta por viewport a mata. O Pedido responde "o que estou criando" **durante** a decisão, não depois.
**Reversibilidade:** alta até a fatia G. Depois de G a rota antiga sai.
**Em aberto:** nenhuma.
**Dono:** produto.

### D2 · Seis paradas — nem treze, nem quatro

**Aceita.** `EXPERIENCE-ARCHITECTURE.md §5`.
**Evidência:** das treze de `conversa.ts:36-50`, cinco são degraus da ignição e `ativacao` **não existe como ato**; duas já vêm respondidas (a conta vem do projeto, `types/trafego.ts:150`). E as treze nunca foram executadas por tela nenhuma — `montarConversa` e `ConversaDeCriacao` só aparecem em teste, e `respostas: {}` fixo aparece **7 vezes em 3 arquivos de teste**.
**Reversibilidade:** média.
**Em aberto:** se `conversa.ts` deve ser removido ou virar a fonte declarativa das seis paradas.
**Dono:** executor da fatia B.

### D3 · ⚠️ O limiar do Pedido em coluna passa de 1280 para conteúdo ≥ 1100px

**Aceita — e substitui `EXPERIENCE-ARCHITECTURE.md §4/§11`.**
**Evidência:** a barra lateral é `w-80` (320px) aberta e `w-16` (64px) recolhida (`Navigation.tsx:558`). `densidade.tsx:25-38` já mediu e registrou que **a janela não é a largura do trabalho**: "numa janela de 1280 sobram ~900 px". Com o Pedido a 340px + vão, sobrariam ~532px para a coluna de decisão — que não sustenta a mesa de Termos, o motivo pelo qual a topologia B foi escolhida.
**Decisão:** container query sobre o contêiner da Bancada, não media query de viewport — porque a barra é **recolhível pelo operador**, e a mesma viewport produz duas larguras de trabalho.
**Fallback autorizado:** media query em **1440px**, nunca 1280.
**Reversibilidade:** alta.
**Em aberto:** nenhuma.
**Dono:** executor da fatia B. Detalhe em `RESPONSIVE-AND-A11Y.md §1`.

### D4 · O Hub volta para abas segmentadas, e perde a aba `canais`

**Aceita.**
**Evidência:** o Hub é o **único dos 12 `<TabsList>`** do repositório com vocabulário sublinhado (`HubDeTrafegoPage.tsx:109-115, 570-573`), e `design.md:128-130` bane aba sublinhada como proibição dura — no arquivo que `design.md:136` nomeia como referência a copiar. E `canais`/`criar` respondem à mesma pergunta por caminhos incompatíveis.
**Reversibilidade:** alta; a aba pode voltar.
**Em aberto:** o Hub tem **três** vocabulários de seleção (abas + `aria-pressed` em `EixosDoHub.tsx:53,67` + chips em `:90-101`). A decisão reduz para dois; se dois ainda é demais, é decisão de produto.
**Dono:** executor da fatia J.

---

## 2. Decisões de autoridade

### D5 · A elegibilidade de lançamento sai do navegador

**Aceita.** É a fatia A1.
**Evidência:** `podeLancar = pendencias.length === 0` (`NovaCampanhaPage.tsx:332-343`), enquanto `volc_ads/pautador_ponte.py:266-272` **já calcula** `bloqueado` e `bloqueios` e `projecao.py:157-177` os descarta. `grep -rn 'pode_lancar' backend/ src/` → **0**.
**Reversibilidade:** alta — duas chaves no dict.
**Em aberto:** **D9**, abaixo.
**Dono:** servidor.

### D6 · A ponte para de coagir ausência a zero

**Aceita.** Fatia A2.
**Evidência:** `Sinal(0.0, AUSENTE)` levanta exceção no motor (`paid_eligibility.py:107-109`), a tela sabe renderizar ausência, e `pautador_ponte.py:451-456, 505-506` coage no meio — deixando três ramos de honestidade como código morto.
**Reversibilidade:** alta.
**Em aberto:** confirmar que nenhum consumidor da ponte faz aritmética assumindo número.
**Dono:** servidor.

### D7 · ⚠️ Uma derivação de navegador é autorizada: o teto do dia

**Aceita, sob cinco condições.** `DATA-AND-AUTHORITY-MAP.md §6.2`.
**A tensão:** `tetoDaCampanha` (`LinhaDeCampanha.tsx:151-163`) **recusa** dividir orçamento por lance mesmo com os dois números, porque "calcular aqui um número que a leitura não trouxe seria inventá-lo com aparência de medido". E o Pedido quer mostrar `2 × orçamento`.
**A distinção que torna uma segura:** `tetoDaCampanha` derivaria uma **medida** de campos **lidos**; o teto do dia explica a **consequência** de um número que o operador **está digitando agora**, sob regra publicada. Um é medição; o outro é aritmética sobre entrada.
**As cinco condições:** insumo exclusivamente do operador; rótulo com a regra e a fonte; **nenhum carimbo de frescor**; a linha **desaparece** para campanha existente; as três ressalvas visíveis.
**Reversibilidade:** alta — a linha sai.
**Em aberto:** se o servidor deveria emitir o teto, tornando a derivação desnecessária.
**Dono:** produto.

### D8 · Toda leitura de custo diz "servido"

**Aceita.**
**Evidência:** `metrics.cost_micros` é custo **servido**, não cobrado, e **não existe métrica de custo cobrado na v25** — verificado por introspecção do proto (`comum.md:504-518`). Hoje é apresentado como "gasto" e "custo" sem marcação (`AlertaDeEntrega.tsx:90`).
**Reversibilidade:** alta.
**Dono:** executor da fatia F.

### D9 · ⚠️ QUESTÃO EM ABERTO — qual regra de severidade vale

**Não decidida. Precisa de dono.**
Servidor e cliente **discordam** hoje:

| Lado | Regra |
|---|---|
| servidor | barra só em `severidade == 'bloqueio'` (`pautador_ponte.py:266-272`) |
| cliente | barra em tudo que **não** for `informacao`/`atencao` (`NovaCampanhaPage.tsx:91, 309-310`) — fail-closed |

A1 **expõe** a regra do servidor; não decide qual é a certa. O cliente é mais conservador, o que é a direção correta em caso de dúvida — mas ter duas é pior que ter a errada.
**Dono futuro:** produto + servidor, antes da fatia G.

---

## 3. ⚠️ Correções aos artefatos pré-existentes desta spec

Oito citações não resolviam contra a base, e três contagens estavam erradas. Todas verificadas por comando.

| # | Afirmação anterior | Correção | Verificação |
|---|---|---|---|
| C1 | `estudio/JornadaDoCanal.tsx` citado como existente | **existe só em `85666da`** (sprint não integrada), não em `207e91f` | `find . -name 'JornadaDoCanal*'` → vazio; `git ls-tree 85666da` → existe |
| C2 | `EstudioLigado.tsx@85666da:100` | o arquivo na base tem **64 linhas**; a linha 100 é da versão da sprint | `wc -l` |
| C3 | `docs/closure/traffic-operating-cockpit-v2/**` citado como leitura direta | **não existe na base**; toda citação é de blob lido via `git show` e passa a ser marcada como tal | `ls docs/closure/` |
| C4 | `src/lib/trafego/__tests__/contrato-unico.test.ts` varre âncora interna | **não existe em lugar nenhum**, e **não há teste** que varra âncora interna | `find . -name '*contrato*unico*'` → vazio; `grep -rn 'href="/' src --include='*.test.ts*'` → 0 |
| C5 | `scripts/gate_bancada_fora_do_bundle.py` "continua no fechamento" | **criado pela sprint anterior**, não existe na base. Os gates reais são `projection.test.ts:82-97` e `seguranca-bundle.test.ts` | `find . -name 'gate_bancada*'` → vazio |
| C6 | rota `/qa/trafego/*` listada como existente | **não existe em `App.tsx`** na base; a bancada de QA é da sprint anterior | `grep -n '<Route' src/App.tsx` → 4 rotas de tráfego |
| C7 | `graphify-out/UPDATE_STATUS.json` lido | **`graphify-out/` não existe nesta worktree** — é gitignorado (`.gitignore:72-79`). `--check` aqui devolveria `{"current": false, "reason": "UPDATE_STATUS.json ausente"}`, que é **estado esperado de worktree isolada**, não defasagem | `find . -name 'UPDATE_STATUS*'` → vazio |
| C8 | "nove blocos empilhados" | são **18** blocos | `NovaCampanhaPage.tsx:426-812` |
| C9 | "três definições de copy pronta" | são **duas** regras em **quatro** sítios | `:335`, `:442`, `:652`, `:795-797` |
| C10 | "93 ocorrências de paleta crua" | são **216**, em **6 arquivos** | comando em `CURRENT-STATE-AUDIT.md §11.2` |
| C11 | a divergência de cor é entre `PortoesDoCanal` e `JornadaDoCanal` | é entre **`PortoesDoCanal.tsx:55-79`** e **`PainelDaMensuracao.tsx:67-74`** — `JornadaDoCanal` não existe na base | ambos os arquivos |
| C12 | as origens de recusa são seis | são **oito**: acrescem `mensuracao` e `observabilidade` | `contrato_canais.py:114-126` |
| C13 | `prontidao.ts:424-427` para a regra fail-closed | é `:400-407`, e é o conserto nomeado do defeito `status_wp !== 'draft'` | o arquivo |
| C14 | `src/lib/motion.ts` na tabela de referências | é do projeto externo `nota1000-canvas`, não deste repo. A tabela passa a separar os dois | `ls src/lib/motion.ts` → não existe |

**As contagens que conferem** e permanecem: 235 `text-[11px]`, 19 `text-[10px]`, 2 `text-[9px]`, 12 `border-l-2` (5 neutras, **7 coloridas**), 30 `uppercase` fora de `.kicker`.

---

## 4. ⚠️ A divergência `bg-card` × `bg-background` — adjudicada

**Esta é a divergência que o briefing pediu para resolver.**

### 4.1 O placar real

| Fonte | Diz | Linha |
|---|---|---|
| `design.md` §Surfaces | **proíbe** `bg-background` na pílula, por nome | `:96` |
| `docs/DESIGN.md` | **proíbe** `bg-background` na pílula | `:63` |
| `design.md` §Elevation | manda `bg-background` | `:193` |
| `design.md` §Components | manda `bg-background` | `:201` |
| **o código** | `data-[state=active]:bg-card` | `src/components/ui/tabs.tsx:42` |

**Placar: 2 proibindo × 2 mandando, e o código implementa `bg-card`.**

### 4.2 A adjudicação, e por quê

**Vale `bg-card`.** Três razões independentes, e qualquer uma bastaria:

1. **O contrato prioritário.** `design.md` abre com um "Agent contract (read this first)" (`:65-77`) que declara ser a única autoridade de UI do produto. `§Surfaces` (`:96`) é a seção desse contrato que trata de abas, e proíbe `bg-background` **por nome, com a razão medida**: `--background` **é** o canvas (`#F3F5F7`), então a pílula e a página viram o mesmo cinza.
2. **O código real, com a medição.** `tabs.tsx:42` implementa `data-[state=active]:bg-card … data-[state=active]:shadow-card`, e o poço é `bg-muted` (`:15`) — exatamente o que `§Surfaces` prescreve. E o **próprio arquivo** carrega a medição que fecha o caso (`:26-32`):

> "A pílula selecionada era `bg-background`. Esse token **É** o canvas (`#F3F5F7`), e o poço da lista é `bg-muted` (`#EEF2F6`): **medido, 1,025:1 entre os dois**."

Uma razão de **1,025:1** entre a pílula e o poço é indistinguível a olho nu — a pílula selecionada simplesmente desapareceria. **E não existe nenhuma superfície do produto usando `bg-background` como estado de aba selecionada**: o lado B **não tem implementação**.
3. **Já existe adjudicação escrita.** `docs/design/AUTORIDADE-VISUAL-RECONCILIADA.md:20-27` estabelece a cadeia de cinco níveis com `design.md` (raiz) como **Contrato** que "vence qualquer divergência", e `docs/DESIGN.md` como ponteiro que "ele próprio diz: se divergir da raiz, a raiz vence". E `:111-117` registra que a correção da frase obsoleta de `§Components` foi **proposta e explicitamente não aplicada** — é por isso que `:193` e `:201` ainda carregam o texto antigo.

### 4.3 O que isso implica, e o que fica em aberto

- A Bancada e o Hub usam **`bg-card` + `shadow-card`** no estado selecionado, e `bg-muted` no poço.
- ⚠️ **A medição vale para o tema claro.** No escuro a relação **se inverte**: `--card` é `221 39% 11%` (mais escuro) e `--muted` é `220 18% 14%` (mais claro) — a pílula selecionada fica **mais escura** que o trilho (`src/index.css:167, 187`). Isso não invalida a decisão (a pílula continua distinguível), mas a hierarquia é lida ao contrário. **Questão em aberto.**
- ⚠️ O poço implementado cumpre **parte** da receita: `TabsList` tem `rounded-md bg-muted p-1`, **sem** `border border-border` e com raio `md` onde o contrato pede `rounded-lg` (`tabs.tsx:15`).
- ⚠️ A decisão foi **replicada à mão** em quatro consumidores que redeclaram localmente o que o primitivo já faz por padrão (`FunilPage`, `ConfigRedatorPage`, `V6AdminPage`, `UsersSettings`), e existe uma **terceira implementação de aba feita à mão** no QG (`src/components/qg/QgViewNav.tsx:63-68`).
- ⚠️ O comentário de `tabs.tsx:26-33` afirma **13 arquivos** consumidores; a contagem real é **12**, e o número errado foi propagado para `AUTORIDADE-VISUAL-RECONCILIADA.md:64-65`.

**Dono futuro:** o integrador de curadoria aplica a correção já proposta em `design.md §Components`. **Esta lane não edita `design.md`.**

---

## 5. Outras divergências entre `design.md` e o código

`AUTORIDADE-VISUAL-RECONCILIADA.md:120-123` **já registra a regra** que reconcilia todas elas: os valores do tema claro passaram a ser **derivados por medição de contraste**, e o hex normativo descreve **o matiz, não a luminosidade final**. Com essa regra, não são divergências — são derivações.

| Token | `design.md` | Implementado | Linha |
|---|---|---|---|
| `success` | `#168B68` | `#116E52` | `index.css:63-64` |
| `warning` | `#D9850B` | `#885407` | `:65-66` |
| `verified` | `#009FC7` | `#006A85` | `:70-77` |
| `destructive` | `#C83D3D` | `#B33232` | `:80-83` |
| `ink-muted-light` | `#68717D` | `#5D656F` | `:46` |
| kicker tracking | `0.1em` (`design.md:84`) | `0.16em` | `:398-405` |

⚠️ **Três correções à tabela anterior:**

1. **`info` não tem valor normativo.** `design.md` cita `info` apenas como nome no vocabulário fechado (`:105`), **sem hex** — logo não pode ter sido "escurecido além do normativo".
2. **`--ring` não é a ação primária.** É uma derivada 10 pontos mais clara no claro (`216 85% 44%` contra `--primary: 216 85% 34%`) e 5 pontos mais clara no escuro.
3. **A aurora não bate.** `design.md` publica **três** hexes (blue, purple, orange); o código tem **quatro** stops — `--aurora-deep` **não existe no `design.md`**. E `tailwind.config.ts` **não expõe nenhuma cor aurora**: escrever `text-aurora-blue` **não produz CSS**.

⚠️ E o bloco de `--verified` **contradiz a si mesmo**: o comentário afirma que o token foi escurecido "para 35%", e o valor é **26%** (`index.css:70-77`).

**Dono futuro:** curadoria de design.

---

## 6. Decisões sobre honestidade de capacidade

### D10 · A matriz de capacidade usa o vocabulário real do servidor

**Aceita.**
**Evidência:** o briefing pediu dez eixos por canal. O contrato tem **quatro portões** (`planejavel`, `validavel`, `criavel_pausada`, `ativavel`) e **quatro canais**. Os nomes `observavel`, `analisavel`, `mutavel`, `monitoravel` e `reconciliavel` **não existem** — `grep` zerado.
**Decisão:** `CHANNEL-CAPABILITY-MATRIX.json` registra os quatro portões como autoridade e mapeia os dez eixos pedidos, marcando com `SEM_CONCEITO_NO_CONTRATO` os seis que não existem, com o fato real mais próximo. **Inventar seis vereditos seria a simetria falsa que o briefing proíbe.**
**Reversibilidade:** total.
**Dono:** executor da fatia J.

### D11 · ⚠️ Video e Shopping: a frase muda de sujeito

**Aceita.**
**Evidência:** a afirmação "a Google Ads API não cria nem atualiza campanha de Video" **não está em `docs/growth-engine/`**. Não há arquivo de canal para Video nem Shopping na `matriz-api` (ela cobre quatro canais). A afirmação vive num **prompt de briefing de design** (`PROMPT-GROK-…:263, 267-271`) que **lista a URL oficial** (`:97, 129`) mas **não tem a verificação datada contra o proto** que a `matriz-api` faz para os outros quatro.
**Decisão:** a tela fala do **VOLC**, não do Google. *"O VOLC inventaria campanhas de vídeo e não as monta. Se a API permite criá-las não foi verificado aqui."*
**Reversibilidade:** alta — basta verificar e datar.
**Em aberto:** fazer a verificação e criar `matriz-api/video.md` e `shopping.md`.
**Dono:** quem mantém a `matriz-api`.

### D12 · A graduação para de prometer execução

**Aceita.**
**Evidência:** `graduacao_em_conversoes` é aceito pelo modelo HTTP e **nunca lido, persistido ou executado** — três ocorrências em `backend/`, todas definição ou repasse. E a tela declara que o "motor de gestão" a executa (`MesaDeLance.tsx:219-223`).
**Reversibilidade:** alta.
**Dono:** executor da fatia F.

### D13 · O Recibo diz que a campanha nasce invisível

**Aceita.**
**Evidência:** o coletor contínuo filtra `estado_externo = ENABLED` **e** `canal = SEARCH` (`persistencia.py:77-90`); o que lê PAUSED existe e **não tem rota** (`:111-119`); a autoridade de agenda **nunca foi escolhida** (`alvo.py:19-23`); e o espelho teve **zero linhas** para a campanha canário pausada (`contrato_canais.py:492-504`).
**Decisão:** o Recibo carrega a frase. Não é falha — é o preço da segurança, e o silêncio não pode ser lido como boa notícia.
**Reversibilidade:** a frase sai quando a agenda existir.
**Dono:** plataforma.

---

## 7. O que foi recusado

| Recusado | Por quê |
|---|---|
| **stepper genérico de sete etapas** | `design.md:215`: "Creation is a channel-specific operational bench, not a generic seven-step form" |
| **command center puro** | bom para observar, ruim para comprometer: não tem ordem, e ordem é o que falta |
| **split view puro** | o trabalho é sequencial com evidência local, não comparação lado a lado |
| **terceira linguagem de aba** | o produto já tem duas; o mapa de paradas é um mapa, visualmente distinto |
| **`blur` na troca de ícone** | `design.md:122` nomeia as propriedades animáveis e `filter` não está entre elas |
| **loader de fases fictícias** | `POST /provar` é **uma** requisição, sem subfase observável |
| **botão de reenviar após indeterminação** | `reenvio_permitido` é `false` **fixo no tipo** |
| **formulário para canal sem construtor** | escada de portões com causa, origem e próximo desbloqueio |
| **criar rota de ativação** | não existe, é decisão de produto, e **não é desta lane** |
| **um terceiro design system** | `docs/design/AUTORIDADE-VISUAL-RECONCILIADA.md`: "a dívida era de aplicação, não de contrato" |
| **usar o benchmark Webgo como verdade causal** | é referência de forma |
| **editar `design.md`, o Roadmap ou a curadoria** | a lane emite delta; o integrador aplica |

---

## 8. Questões em aberto — a lista fechada

| # | Questão | Dono | Bloqueia |
|---|---|---|---|
| Q1 | qual regra de severidade vale, a do servidor ou a do cliente (**D9**) | produto + servidor | fatia G |
| Q2 | `limitacao` significa **coisas opostas**: `PortaoDePolitica.tsx:159-165` diz que a campanha sobe; `volc_ads/campanha/conteudo.py:56, 266-269` a põe entre as severidades que **barram** | política | fatia C |
| Q3 | `POST /reconciliar` exige **admin** enquanto o resto exige `exigir_usuario` — o operador não fecha o próprio recibo | produto | fatia I (não bloqueia; a tela declara quem pode) |
| Q4 | não existe **caixa de entrada de recibos abertos**: quem perder o `item_id` perde a saída | servidor | não bloqueia |
| **Q5** 🔴 | **BLOQUEANTE.** Nada no sistema **aprova** o conjunto pago que o portão exige. `approved_set_sha256` só é atribuído dentro de `aprovar()` (`paid_eligibility.py:1179`) ou reidratado de dicionário (`:883`), e **`aprovar()` não tem chamador de produção**; `funnel_factory.py:387-391` persiste sem aprovar. Logo `/provar` termina em **409 `NAO_APROVADO`** no caminho normal (`portao_conjunto_pago.py:158-163`) | produto decide o desenho, servidor implementa | **fatia A0 — e A0 bloqueia B–I** |
| Q6 | `LOW_DEMAND` está declarado em `PRECEDENCIA`, `ESTADOS_DE_INCIDENTE` e `SEVERIDADE`, com verbete no frontend, e **nada o emite** | servidor | não bloqueia |
| Q7 | no tema escuro a pílula selecionada fica **mais escura** que o poço — hierarquia invertida | design | não bloqueia |
| Q8 | quatro conjuntos fechados divergentes de estratégia de lance (front 2, `dominio` 2, `prontidao` 5, brief) | arquitetura | não bloqueia; a fatia F declara qual usa |
| Q9 | `AlertaDeEntrega` declara `impressoes`/`cliques`/`custo` **não-nuláveis** em TS enquanto o backend os zera para `None` | servidor | não bloqueia |
| Q10 | as constantes de dinheiro da `MesaDeLance` são **BRL fixas** enquanto a moeda é da conta | produto | fatia F |
| Q11 | `hub/contrato.ts:63-72` inventa um sexto estado visual `pendente` que não existe no vocabulário do backend | servidor | não bloqueia |
| Q12 | duas verticais reais (`saude`, `jogos_azar`) **não têm `nota`** em `spec.json`, e a rota preenche `descricao` com `regra.get("nota","")` | política | não bloqueia |
| **Q13** | a **correspondência por termo não tem canal** até o servidor: `PedidoDeProva` só tem `match_type` global (`types/trafego.ts:951-956`); a escolha individual vira positiva e é recusada; e a correspondência do conjunto aprovado **participa da identidade** que o portão confere (`paid_eligibility.py:920-929`, `portao_conjunto_pago.py:240-247`), então mudá-la invalida a aprovação. Ou a parada não oferece escolha por termo, ou existe uma operação de "alterar e reaprovar" que não existe | produto | fatia D |
| **Q14** | a revelação do recibo por **máscara radial** e o cabeçalho de 180–220px eram exceções que a spec se autoconcedia contra `design.md:89, 108-122`. **Foram removidas** — a spec agora conforma. A máscara fica como **proposta de emenda** ao `design.md` | curadoria de design | não bloqueia |
| **Q15** | rascunho de **servidor** para as escolhas do operador: exige rota, armazenamento, identidade e concorrência. `STATE-MATRIX.md §7` decidiu `sessionStorage` como contrato desta spec; o rascunho de servidor fica como tarefa própria | servidor | não bloqueia |

---

## 9. Revisão independente

### 9.1 Revisão adversarial interna

Executada: **14 eixos de investigação**, cada um seguido de uma passada de refutação que abriu os arquivos nas linhas citadas e conferiu trecho a trecho.

**Resultado:** 13 relatórios de refutação, com achados classificados em `REFUTADA`, `ERRADA`, `IMPRECISA`, `LINHA ERRADA` e `[LACUNA]`. Todos adjudicados no código. As correções materiais estão em `§3`, `§5` e distribuídas pelos artefatos com a marca ⚠️.

Exemplos de refutações que **mudaram** o conteúdo desta spec:

| Achado | Efeito |
|---|---|
| `em_voo` **nasce no ledger** em `despachar()`, commitado **antes** do mutate — todo lançamento passa por ele | reescreveu a tabela de desfechos |
| o campo `motivo` **nasce pré-preenchido**, satisfazendo por construção as três guardas de 10 caracteres | virou contraprova nova em T-3.11 |
| na largura média a coluna `estrategia` **some** | corrigiu "nenhuma some" |
| `criado_em` **é exibido** em `CartaoCopy.tsx:96` | refutou "o servidor manda e a página nunca exibe" |
| a tela usa `recibo.freshness_window_s` quando ele é finito positivo; só o **backend** ignora | expôs **duas janelas de frescor** |
| `live_verified` fica `true` quando `live_drift` sai `not_applicable` | achado novo, virou contraprova |
| a seleção do operador **não decide** as positivas (`trafego.py:2977-2981`) | mudou a frase da parada Termos |

### 9.1b Revisão cruzada por Codex — **REPROVADO**, e adjudicada

`codex-cli 0.151.0`, execução não-interativa em sandbox **somente leitura**, sobre o snapshot final dos 15 artefatos.

**Veredito devolvido: `REPROVADO — 1 bloqueante, 9 materiais, 1 menor`.**

Todos os doze achados foram **abertos no código e conferidos**. Nenhum foi refutado; **todos foram aceitos e corrigidos**:

| # | Achado | Adjudicação |
|---|---|---|
| 🔴 B1 | "o fluxo Search não consegue chegar à prova" — nada aprova o conjunto pago, logo `/provar` dá 409 no caminho normal | **PROCEDE.** Verificado: `aprovar()` sem chamador; `approved_set_sha256` só atribuído lá dentro. **Q5 promovida a bloqueante; fatia A0 criada; B–I passam a depender dela; `END-TO-END-FLOWS.md §1` deixa de afirmar que Search "chega ao fim" sem a precondição** |
| M1 | correspondência por termo não tem canal válido até o servidor | **PROCEDE.** Virou **Q13**; a parada passa a oferecer só o `match_type` global até haver decisão |
| M2 | "A2 não produz `null` removendo dois `or 0`" — `float(None)` cai no `except` que reatribui `0.0`; `int(None)` levanta `TypeError`; os modelos são não-anuláveis | **PROCEDE.** A fatia A2 foi reescrita com os três passos reais |
| M3 | "A1 não fornece estado por parada" — os avisos não têm parada dona, obrigando o cliente a inventar `codigo → parada` | **PROCEDE.** Criada a fatia **A1b**, com regra alternativa explícita (bloqueio global fecha **só** a Revisão) |
| M4 | reconciliação apresentada como saída operacional, mas o operador recebe **403** | **PROCEDE.** `SCREEN-CONTRACTS.md §14` passa a ter apresentação por perfil, e 403 vira estado de primeira classe |
| M5 | Display exige uma Bancada que nenhuma fatia constrói | **PROCEDE.** `END-TO-END-FLOWS.md §2` separa **alvo da fatia J** de **comportamento até J** |
| M6 | persistência deixa decisão arquitetural binária ao executor | **PROCEDE.** `STATE-MATRIX.md §7` **decide**: `sessionStorage`, com a razão; rascunho de servidor vira **Q15** |
| M7 | o limiar de 1440px está dos dois lados do próprio contrato | **PROCEDE, e era contradição interna real:** a própria tabela mede ~1056px em 1440 com a barra aberta, abaixo dos 1100 exigidos. Corrigido para ~1500px, com a captura de 1440 exigida **nos dois estados da barra** |
| M8 | a fatia J agrega mudanças independentes demais | **PROCEDE.** Dividida em **J1 (autoridade) → J2 (renderizador) → J3 (tokens e abas)**, cada uma com contraprova e rollback próprios |
| M9 | a spec inventa exceções proibidas pela autoridade visual raiz (cabeçalho 180–220px; recibo com `mask-image` a 400ms) | **PROCEDE.** As duas foram **removidas**: cabeçalho volta a 220–280px, e a revelação usa `opacity` + `scale` a 220ms. A máscara vira **Q14**, proposta de emenda |
| m1 | artefatos de execução repetem fatos que o próprio log já refutou (`criado_em`; "três definições") | **PROCEDE.** Corrigido em `SCREEN-CONTRACTS.md §9` |

**Nota sobre o método da revisão:** o próprio relatório registra que a revisão cruzada *de segundo nível* dentro do Codex ficou indisponível pelo sandbox somente leitura, e que as provas foram revalidadas diretamente no snapshot. Isso é uma limitação declarada do harness, não um resultado.

**Rodada corretiva:** **uma**, focal, aplicada a partir destes doze achados. É a que a missão autoriza.

### 9.2 Revisão cruzada de provedor

```
CROSS_PROVIDER_REVIEW_NOT_AVAILABLE (Gemini)
```

Verificado nesta sessão: `gemini -p "responda apenas: OK"` responde

> *"Please set an Auth method in your /Users/mac/.gemini/settings.json or specify one of the following environment variables before running: GEMINI_API_KEY, GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_GENAI_USE_GCA"*

A missão **proíbe** configurar credencial, consertar harness ou substituir por revisão fictícia. Fica registrado literalmente, sem substituto.

`codex-cli 0.151.0` está instalado nesta máquina. A sprint anterior registrou revisão Codex com veredito **REPROVADO e 2 achados bloqueantes** (`HANDOFF.md:59-61, 77-84` no blob de `85666da`) — o que confirma que o harness funciona, e que o resultado dele não é decorativo.

### 9.3 Limitação que nenhuma revisão desta missão remove

**Nenhuma rota autenticada foi aberta em navegador.** Todo diagnóstico visual desta spec é de **código**. É por isso que `EXECUTOR-ACCEPTANCE.md §3.14` condiciona o aceite visual a capturas reais com sessão, e nenhuma fatia é aceita visualmente com captura de fixture.
