# EXPERIENCE-ARCHITECTURE — arquitetura de informação, navegação e topologia

Base factual: `207e91f1da290130e8d02b78c3ba1c8e9a761111` (ancestral de `origin/volc-os-v2 @ 3331c0c`).

> ⚠️ **Aviso de procedência, aplicado a todo este arquivo.** Citações a `src/components/trafego/estudio/JornadaDoCanal.tsx`, a `EstudioLigado.tsx@85666da:98-109` e a `docs/closure/traffic-operating-cockpit-v2/**` são de **blobs do commit `85666da`** — a sprint `traffic-operating-cockpit-v2`, que **não está integrada nesta base**. Nenhum desses caminhos existe em `207e91f`. A rota `/qa/trafego/*` e `scripts/gate_bancada_fora_do_bundle.py` estão na mesma condição. Verificação e substitutos em `CURRENT-STATE-AUDIT.md §12` e `DECISION-LOG.md §3`.
Autoridade visual: `design.md` na raiz. Autoridade de produto: `PRODUCT.md`.
Este arquivo decide a **forma**. O conteúdo de cada tela está em `SCREEN-CONTRACTS.md`; a origem de cada dado, em `DATA-AND-AUTHORITY-MAP.md`.

---

## 1. A pergunta que esta arquitetura responde

> Como transformar a inteligência já construída em uma jornada simples, segura e intuitiva para preparar, provar e lançar campanhas — sem esconder evidência, incerteza ou consequência?

A resposta curta: **a tela para de ser um formulário longo e passa a ser uma sequência de decisões com a evidência de cada uma ao lado, e um pedido acumulado sempre visível.**

A resposta longa é o resto deste arquivo.

---

## 2. Os dois modos de errar isto, e por que os dois já aconteceram aqui

### 2.1 O modo que está no ar hoje: a página-rolo

`src/pages/trafego/NovaCampanhaPage.tsx` (1.014 linhas) é **uma coluna de 1.152px de largura máxima com dezoito blocos empilhados** (`:487` `max-w-6xl`; inventário bloco a bloco em `CURRENT-STATE-AUDIT.md`), lidos por rolagem, com uma barra fixa no topo cujo "trilho" (`:840-866`) são quatro âncoras `#estagio-N` — não um progresso, um índice.

O efeito medido:

| Defeito | Onde |
|---|---|
| O portão que pode barrar tudo (vertical/certificação) aparece **depois** da copy, que é escrita sob a vertical | `NovaCampanhaPage.tsx:651` (copy) vs `:702-714` (portão) |
| A elegibilidade de lançamento é montada no navegador | `NovaCampanhaPage.tsx:332-343` |
| "Copy pronta" tem **duas** definições espalhadas por **quatro** sítios | `:335`, `:442`, `:652`, `:795-797` |
| O canal é literal | `:414` `canal: 'SEARCH' as const` |
| Orçamento e lance nascem de constantes do navegador | `:115-116` (`'10'`, `'0.12'`) |
| Nenhum carimbo de frescor na leitura do cockpit, nenhum controle de releitura | ausência em `:149-171` |
| 235 ocorrências de texto a 11px em `src/components/trafego` para copy explicativa | contagem em `VISUAL-DIRECTION.md §2` |

A página não é ruim por falta de informação. É ruim porque **toda a informação tem o mesmo peso e nenhuma ordem obrigatória**: o operador pode escrever a copy antes de saber se o destino é apto, e descobrir a trava no fim.

### 2.2 O modo que a sprint anterior tentou: a lista informativa

`sprint/traffic-operating-cockpit-v2 @ 85666da` introduziu `estudio/JornadaDoCanal.tsx` — quatro portões + treze etapas — montada uma vez, na aba **Criar** do Hub (`EstudioLigado.tsx@85666da:98-109` **no blob de `85666da`**; o arquivo nesta base tem 64 linhas), com `respostas: {}` fixo. É um **mapa de um fluxo que nenhuma tela executa**: o cockpit real não importa `conversa.ts`, e a nota da própria tela aponta para "o cockpit da campanha", que usa outro trilho (`NovaCampanhaPage.tsx:840-866`).

Diagnóstico: treze linhas verticais numa aba de leitura não são uma jornada. São uma tabela de conteúdo de um documento que ninguém abre. E somadas ao `<ol>` estático que `EstudioMulticanal.tsx:233-256` já desenhava acima, produziram uma página de mais de 4.000px no mobile (admitido em `REMAINING-RISKS.md@85666da:44-56` **no blob de `85666da`**).

**A lição das duas:** o problema não é falta de etapas nem excesso de etapas. É que **etapa sem decisão é ruído, e decisão sem ordem é armadilha.**

---

## 3. A escolha de topologia

### 3.1 Critérios (nesta ordem)

1. **Consequência antes da ação.** O operador precisa ver o que vai acontecer antes de poder fazer acontecer (`PRODUCT.md:29`, `design.md:59`).
2. **Uma decisão dominante por momento**, sem esconder a evidência que a sustenta.
3. **Densidade honesta.** A mesa de termos compara 23 linhas com volume, CPC e correspondência. Uma pergunta por viewport a mata.
4. **Resumo persistente.** O pedido acumulado precisa estar visível o tempo todo — é ele que responde "o que eu estou criando?" em dez segundos.
5. **Caminho rápido.** Operador experiente relança em minutos; não pode ser obrigado a atravessar seis telas para trocar um lance.
6. **O servidor decide.** Nenhuma topologia pode exigir que o navegador calcule elegibilidade.
7. **Assimetria de canal é fato, não defeito.** Search opera; Display prova; Demand Gen prova por porta estreita; Performance Max só planeja. A forma tem de acomodar isso sem simetria falsa.

### 3.2 Os três candidatos avaliados

| | **A · Guided Mission Control** | **B · Evidence Workbench** | **C · Progressive Launch Canvas** |
|---|---|---|---|
| Topologia | 3 colunas fixas: trilho vertical 220px · decisão · pedido 320px | 1 coluna larga + mapa horizontal fixo no topo + pedido em barra inferior expansível | 1 decisão por viewport + evidência em coluna fixa à direita + ficha que cresce |
| Progresso | trilho vertical com estado por parada | mapa horizontal de 6 paradas, estado por chip | linha determinada fina + nome da parada |
| Resumo | sempre visível, coluna própria | digest de uma linha + gaveta | ficha acumulada, cresce a cada parada |
| Densidade | média (≈700px úteis a 1440) | alta (≈1.100px úteis) | baixa |
| Assinatura VOLC | segmento aurora na parada atual + `aurora-rule` | 2px aurora na borda do mapa | luz do horizonte muda a cada parada |
| Força | contexto máximo, zero rolagem para ver o pedido | mesa de termos cabe inteira; menor distância do estado atual | compromisso progressivo real; o mais "premium" |
| Falha | a mesa de termos fica apertada; três colunas competem | o pedido pode ser ignorado se ficar só no rodapé | lenta para quem já sabe; esconde comparação |

### 3.3 Decisão: **híbrido, nomeado "Bancada Guiada"**

Adota-se **B como tela**, **A como rail de pedido em telas largas**, **C como modelo de interação**.

- **De B:** a coluna de trabalho é larga e única; o mapa de paradas é uma faixa horizontal fixa no topo, com estado por parada — um mapa, não um wizard.
- **De A:** o pedido ganha coluna própria persistente à direita quando a **largura disponível para o conteúdo** for ≥ **1100px** — não a viewport. Abaixo disso ele colapsa no digest + gaveta de B. ⚠️ **Este limiar substitui o `1280px` da redação anterior**, que não fecha contra a geometria do shell (barra lateral de 320px aberta); a medição e o fallback autorizado de 1440px estão em `RESPONSIVE-AND-A11Y.md §1` e `DECISION-LOG.md §D3`.
- **De C:** o *modelo de compromisso* — cada parada tem **uma decisão dominante**, e avançar é um ato explícito que carimba a decisão no pedido. Não se adota a densidade de C (uma pergunta por viewport) nem sua estética.

Rejeita-se explicitamente:
- **Stepper puro** — reintroduz as sete etapas genéricas que `src/components/trafego/canal/jornada.ts:5-9` já derrubou e que `design.md:215` proíbe ("Creation is a channel-specific operational bench, not a generic seven-step form").
- **Command center puro** — bom para observar, ruim para comprometer: não tem ordem, e ordem é o que falta hoje.
- **Split view puro** — a comparação lado a lado não é o trabalho aqui; o trabalho é sequencial com evidência local.

---

## 4. A Bancada Guiada, por região

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ SHELL (Layout.tsx) — sidebar, header, sino, tema. Inalterado.                  │
├───────────────────────────────────────────────────────────────────────────────┤
│ ❶ CABEÇALHO DE IDENTIDADE  (kicker · H1 · aurora-rule · propósito · 1 ação)     │
│    "nova campanha · search" / nome do funil / domínio · país/idioma · vertical  │
│    orçamento de altura: 220–280px — o contrato de design.md:89, sem exceção     │
│    (o mapa ❷ é faixa de NAVEGAÇÃO, e não entra nesse orçamento)                 │
├───────────────────────────────────────────────────────────────────────────────┤
│ ❷ MAPA DAS PARADAS  (sticky, 56px)                                             │
│    Destino ▸ Política ▸ Termos ▸ Anúncio ▸ Economia ▸ Revisão                   │
│    cada parada: glifo de estado + palavra + (contagem, quando existir)          │
├──────────────────────────────────────────────┬────────────────────────────────┤
│ ❸ COLUNA DE DECISÃO                          │ ❹ PEDIDO (conteúdo ≥1100px)    │
│    A parada atual, inteira:                  │    sticky, 320–360px           │
│    · pergunta em H2                          │    o que será criado, agora    │
│    · a decisão (o controle)                  │    · conta · destino · canal   │
│    · a evidência que a sustenta              │    · conjunto · nascimento     │
│    · o que essa decisão causa                │    · otimiza para              │
│    · [voltar]        [confirmar e seguir →]  │    · anúncio · política        │
│                                              │    · TETO REAL DE GASTO        │
│    Abaixo, recolhido: as paradas já          │    · o que falta (do servidor) │
│    confirmadas, reabríveis em um clique      │    · próximo ato               │
├──────────────────────────────────────────────┴────────────────────────────────┤
│ ❺ RODAPÉ DE AÇÃO  (<1280px: digest de uma linha + "ver pedido" → gaveta)        │
└───────────────────────────────────────────────────────────────────────────────┘
                         ↓ ação primária da parada Revisão
┌───────────────────────────────────────────────────────────────────────────────┐
│ ❻ IGNIÇÃO  (tela cheia, `Lancamento.tsx` refeito) — prova → aprovação → criação │
│    A única superfície teatral do produto. Preservada por mérito.               │
└───────────────────────────────────────────────────────────────────────────────┘
                         ↓ ao fechar
┌───────────────────────────────────────────────────────────────────────────────┐
│ ❼ RECIBO  — superfície própria e retornável, não um estado de modal            │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Por que o Pedido é coluna e não rodapé em telas largas

Porque a pergunta "o que estou criando?" é feita **durante** cada decisão, não depois dela. Um rodapé responde quando o operador lembra de olhar; uma coluna responde enquanto ele decide. E porque o item mais importante do pedido — o **teto real de gasto** — muda quando ele mexe no orçamento, e precisa mudar na frente dele.

Abaixo de ~1100px de conteúdo a coluna não cabe sem espremer a mesa de termos, e espremer a mesa de termos é pior. Aí o pedido vira digest + gaveta, e o digest carrega os três fatos que não podem sumir: conta, teto real de gasto, o que falta.

### 4.2 O teto real de gasto — o elemento que a interface hoje não tem

Hoje a tela escreve "orçamento R$ 10 / dia" (`Lancamento.tsx:471`) e o operador lê isso como o teto. Não é. O limite de gasto diário do Google é **2× o orçamento diário médio**, e o mensal é **30,4×** — dois fatos independentes confirmados em `docs/growth-engine/matriz-api/comum.md:455-499`, que também registra: um canário de R$20/dia por 3 dias tem teto defensável de **R$120, não R$60**.

O Pedido mostra, sempre:

```
orçamento           R$ 10,00 / dia          fonte: você, agora
teto do dia         R$ 20,00                regra do Google: 2× o diário
teto de 3 dias      R$ 60,00                3 × teto do dia
```

Isto é inteligência que já existe medida no repositório e nunca chegou à tela. É o exemplo canônico do que esta missão precisa materializar.

⚠️ Restrição correlata que o executor não pode inverter: `metrics.cost_micros` é **custo servido, não cobrado**, e não existe métrica de custo cobrado na API v25 (`comum.md:500-529`). Qualquer leitura de gasto na tela diz "servido" e nunca promete a fatura.

---

## 5. As paradas

Seis. Não treze, não quatro, não sete.

**Por que não treze:** das treze de `src/components/trafego/criacao/conversa.ts:36-50`, cinco (`validacao_local`, `prova`, `aprovacao`, `criacao`, `ativacao`) não são paradas que o operador navega — são degraus da ignição, e `ativacao` não existe como ato neste sistema. Duas (`objetivo`, `conta`) já vêm decididas: a oportunidade traz o funil, e a conta vem do projeto (`types/trafego.ts:150-152` — "a conta vem do PROJETO, não do operador"). Perguntar o que já foi respondido é o defeito que a Bancada existe para não cometer.

**Por que não quatro:** o trilho atual (`origem/keywords/copy/conta`) esconde duas decisões caras dentro de outras — a **vertical de política** vive dentro de nada e aparece solta, e a **economia** (estratégia, lance, verba, graduação) é chamada de "conta e lance", o que subestima a decisão mais consequente da tela.

| # | Parada | Pergunta dominante | Decisão do operador | Evidência que a acompanha |
|---|---|---|---|---|
| 1 | **Destino** | Para onde este clique vai? | nenhuma no caminho feliz; reavaliar quando indeterminado | 5 perguntas do portão, publicação, deriva ao vivo, nota do Google |
| 2 | **Política** | Sob que regra este anúncio é julgado? | vertical (1 de N) + certificações (N) | severidade por país, o que a vertical exige, divergência com o que a entidade classificou |
| 3 | **Termos** | O que esta campanha compra? | manter/remover cada termo · correspondência · exclusões | elegibilidade, volume medido/não medido, CPC minerado com a ressalva, régua de leilão, teto econômico do dono |
| 4 | **Anúncio** | Com que texto ela aparece? | gerar / editar / aceitar | mínimos do RSA, força do anúncio como diagnóstico, congruência termo→anúncio→página |
| 5 | **Economia** | Como ela nasce e quanto pode custar? | estratégia · lance · orçamento · graduação | plano de mensuração, sete portões, moeda e fuso da conta, meta efetiva, teto real de gasto |
| 6 | **Revisão** | Está tudo certo? | nenhuma; confere e dispara a prova | o pedido inteiro, os bloqueios do servidor, o que a prova vai fazer |

### 5.1 A ordem não é estética

- **Destino antes de tudo** porque é a única parada que pode parar a jornada sem gastar nada. `Lancamento.tsx:132-135` já implementa exatamente isso na ignição ("a escada PARA aqui — antes de `/provar`, que é a chamada mais cara do fluxo"). A Bancada sobe essa regra um nível: o operador não deveria chegar à ignição para descobrir.
- **Política antes de Anúncio** porque a copy é escrita sob a vertical (`NovaCampanhaPage.tsx:298`) e provada sob a vertical (`:418`). Hoje a ordem visual é a inversa e o `useRef verticalReposta` (`:253-261`) existe para consertar o sintoma.
- **Termos antes de Anúncio** porque a copy ancora nos termos marcados — a própria tela já sabe disso (`CartaoCopy` recebe `motivoBloqueio: 'Marque as keywords primeiro — é nelas que o texto ancora.'`, `:659-661`).
- **Economia depois de Termos** porque a régua de leilão e o volume selecionado são o que dimensiona a aposta.
- **Revisão sempre existe**, mesmo quando o operador pulou paradas pelo caminho rápido.

### 5.2 Estado de uma parada

Fechado, com glifo + palavra + descrição (nunca só cor):

| Estado | Significa | Pode avançar? |
|---|---|---|
| `confirmada` | o operador confirmou; o pedido carrega o resultado | sim |
| `atual` | a parada aberta agora | — |
| `pendente` | ainda não visitada, e nada a impede | sim, por salto |
| `bloqueada` | o **servidor** declarou um impedimento; a causa é dele | não |
| `indeterminada` | a leitura que sustenta esta parada não chegou | não |
| `não se aplica` | este canal não faz esta pergunta | ignorada na contagem |

Regras duras:

- **Nenhum estado é derivado no navegador.** `bloqueada` vem de `avisos[].severidade` + recibo do portão + `bloqueios` do servidor; `indeterminada` vem de ausência de leitura declarada. Ver `DATA-AND-AUTHORITY-MAP.md`.
- **`indeterminada` nunca vira `pendente`.** Falha de leitura não é permissão (`src/lib/landing-policy/prontidao.ts:424-427`).
- **O progresso conta só o aplicável.** `não se aplica` sai do denominador — é a regra que `conversa.ts:224-230` já implementa e que a Bancada herda.
- **Nunca "etapa 3 de 12" para um canal sem construtor.** Um canal que não monta não tem progresso; tem uma escada de portões e o próximo desbloqueio.

### 5.3 Caminho rápido

Três acessos, todos na mesma tela:

1. **Salto pelo mapa.** Clicar em qualquer parada não-bloqueada abre-a. O pedido não se desfaz.
2. **Revisão direta.** A parada 6 é alcançável a qualquer momento; ela lista o que falta com link para a parada dona.
3. **Relançar.** `?relancar=1` é **escrito** hoje por `QuadroDeOportunidades.tsx:309-315`, e ⚠️ **nunca lido por nenhum consumidor de produção** (`grep -rn 'relancar' src/pages src/hooks` → 0). A Bancada passa a lê-lo e abre em Revisão com o pedido pré-carregado — **ou** o parâmetro sai. Deixá-lo escrito e mudo é o pior dos três estados.

---

## 6. Contrato do Pedido

O Pedido é **projeção**, nunca segunda montagem. Toda linha tem: rótulo, valor, **fonte** e — quando o valor é uma medida — **frescor**.

```
PEDIDO                                        [ver como JSON]   ← só em lab_mode
─────────────────────────────────────────────────────────────
conta          Portal Mundo Mais              projeto #2
               547-809-6539 · BRL · America/Sao_Paulo
destino        creditoup.com.br/cartao…       apto · Google desconhecido
canal          Search                          manifesto do servidor
conjunto       23 termos · 1 grupo · 1 RSA     doutrina P7
nascimento     CPC manual · R$ 0,12            você, agora
               graduação em 30 conversões
orçamento      R$ 10,00 / dia                  você, agora
teto do dia    R$ 20,00                        regra do Google (2×)
otimiza para   —                               ninguém leu a meta efetiva
anúncio        6 títulos · 3 descrições        gerado há 4 min
política       financeiro · sem certificação   você, agora
─────────────────────────────────────────────────────────────
FALTA (2)      · concluir 1 verificação do destino
               · escrever a copy
próximo ato    corrigir o destino antes de provar
```

Regras:

- **Ausência é dita, não escondida.** `—` acompanhado de quem não foi lido. Nunca `0`, nunca em branco.
- **Uma linha que mudou pisca uma vez** (tinta de fundo, 1200ms, sem movimento) — ver `MOTION-AND-INTERACTION.md`.
- **`FALTA` é do servidor.** A lista vem das pendências declaradas (avisos que barram + pendências do destino + bloqueios do canal). O navegador não inventa item nenhum.
- **`próximo ato` é uma frase, não um botão.** O botão vive na parada dona do impedimento.
- **O Pedido nunca mostra número sem frescor** quando o número é medido (`design.md:243`).

---

## 7. Navegação e estado na URL

```
/trafego/nova/:opportunityId?run=<n>&canal=<CANAL>&etapa=<parada>&relancar=1
```

| Parâmetro | Origem | Regra |
|---|---|---|
| `:opportunityId` | rota existente | inalterado |
| `run` | já existe (`NovaCampanhaPage.tsx:96`) | inalterado |
| `canal` | **novo** | canônico (`SEARCH`…), apelido `PMAX` aceito na entrada e traduzido numa fronteira só (`types/trafego.ts:1068-1073`). Ausente ⇒ o canal que o manifesto declara operável para esta oportunidade |
| `etapa` | **novo** | `destino\|politica\|termos\|anuncio\|economia\|revisao`. Ausente ⇒ a primeira parada não confirmada |
| `relancar` | já existe | abre em `revisao` |

Consequências obrigatórias:

- **Recarregar não perde a parada.** Hoje recarregar devolve o topo do rolo.
- **Link de suporte é reproduzível.** "Estou travado" vira uma URL que abre exatamente onde a pessoa está.
- **Nenhum dado pessoal ou identificador de conta na URL.** `customer_id` não entra.
- A navegação entre paradas é **`<Link>`/`navigate`**, jamais `<a href>` para rota interna. ⚠️ **Correção:** não existe hoje varredura que reprove âncora interna — `find . -name '*contrato*unico*'` → vazio, e `grep -rn 'href="/' src --include='*.test.ts*'` → 0. A regra permanece, e a varredura é **criada** pela fatia B (`IMPLEMENTATION-SLICES.md`). Ela tem alvo real: o único caminho do inventário para a página canônica é hoje um `<a href>` cru dentro da expansão (`inventario/LinhaDeCampanha.tsx:681-685`), e o arquivo não importa `react-router` — clicar recarrega o documento inteiro.

---

## 8. Mapa de rotas — antes e depois

| Rota | Hoje | Depois | Motivo |
|---|---|---|---|
| `/trafego` | Hub, 5 abas (`campanhas`, `canais`, `preparar`, `criar`, `atencao`) | **4 abas**: `campanhas`, `preparar`, `criar`, `atencao` | a aba `canais` responde a mesma pergunta que a aba `criar` passou a responder, com um segundo renderizador de portões que **discorda em cor** do primeiro (`canais/PortoesDoCanal.tsx:57-62` pinta BLOQUEADO âmbar; `estudio/JornadaDoCanal.tsx:81-92` pinta vermelho). Um renderizador, um lugar. |
| `/trafego?aba=criar` | `EstudioMulticanal` + `JornadaDoCanal` (duas listas estáticas empilhadas) | **Antessala de canal**: um cartão por canal com os quatro portões, a ação dominante e o próximo desbloqueio. Sem prévia de 13 etapas. | a prévia descreve um fluxo que nenhuma tela executa (`JornadaDoCanal.tsx:232` `respostas: {}`) |
| `/trafego?aba=preparar` | quadro de funis + portão de criação | inalterado em estrutura; ganha a coluna "destino" com o estado do portão de política | o operador escolhe a oportunidade sabendo se ela pode virar campanha |
| `/trafego/nova/:opportunityId` | página-rolo de 9 blocos | **Bancada Guiada** (este documento) | o objeto desta missão |
| — | não existe | `/trafego/nova/:opportunityId` parada `revisao` → **Ignição** (overlay) → **Recibo** (região própria na mesma rota, `#recibo`) | recibo dentro de modal é recibo que não se volta a ler |
| `/trafego/campanhas/:volcCampaignId` | 8 seções na ordem certa | mantém a ordem; ganha **Guardião 72h** como faixa própria acima do veredito e a seção de recibos deixa de ser só uma declaração de ausência **quando** a rota existir | `docs/growth-engine/frontend.md:245` registra `GET …/recibos` como rota inexistente |
| `/trafego/laboratorio/inteligencia/:scenarioId` | bancada de decisão sintética | inalterada, e continua fora do caminho operacional | é laboratório, e declara isso |
| ~~`/qa/trafego/*`~~ | ⚠️ **não existe nesta base** — a bancada visual e `scripts/gate_bancada_fora_do_bundle.py` foram criados pela sprint `85666da`, não integrada | se reintroduzida, o gate vem junto | os gates que existem aqui são `laboratorio/__tests__/projection.test.ts:82-97` e `src/lib/__tests__/seguranca-bundle.test.ts` |

⚠️ **Fora de escopo desta arquitetura, e declarado:** `/settings/campaigns` (`src/App.tsx:105`) é uma segunda lista de campanhas com botões próprios de pausar/ativar que escrevem direto no Supabase. Enquanto ela existir, duas telas podem discordar sobre se uma campanha está rodando. Isto é **dívida nomeada**, não item deste redesign — ver `IMPLEMENTATION-SLICES.md §fora de escopo`.

---

## 9. Onde cada passo da jornada vive

Os quatorze passos do briefing, mapeados:

| # | Passo | Superfície |
|---|---|---|
| 1 | entender o que existe | `/trafego?aba=campanhas` — inventário |
| 2 | entender o que pode virar campanha | `/trafego?aba=preparar` |
| 3 | entender o que o canal permite | `/trafego?aba=criar` — antessala de canal |
| 4 | escolher a oportunidade | `preparar` → ação "montar campanha" |
| 5 | conferir o destino pago | Bancada · parada **Destino** |
| 6 | declarar a política | Bancada · parada **Política** |
| 7 | revisar termos e exclusões | Bancada · parada **Termos** |
| 8 | produzir o anúncio | Bancada · parada **Anúncio** |
| 9 | decidir economia e mensuração | Bancada · parada **Economia** |
| 10 | conferir orçamento e escopo | Bancada · parada **Revisão** + Pedido |
| 11 | provar contra a conta | **Ignição** · degrau `prova` |
| 12 | aprovar e criar pausada | **Ignição** · degraus `aprovação` e `escrita` |
| 13 | confirmar recibo e releitura | **Recibo** (região própria) |
| 14 | acompanhar 72h e receber alertas | `/trafego/campanhas/:id` + fila de atenção + sino |

Nenhum passo mora em dois lugares. Nenhum lugar tem passo que não está nesta lista.

---

## 10. Multicanal: a Bancada deriva do manifesto

A Bancada **não ramifica por `if (canal === …)`**. Ela lê o manifesto do canal (`GET /canais`) e monta as paradas a partir dele — a mesma regra que `src/components/trafego/canal/jornada.ts:5-9` fixou e que `design.md:215` exige.

```
paradas(canal) = PARADAS_CANONICAS
                   .filter(p => manifesto.declara(p))
                   .map(p => ({ ...p, estado: portao(p, contratoDoCanal) }))
```

| Canal | Abre a Bancada? | Paradas | O que a tela mostra quando não abre |
|---|---|---|---|
| **Search** | sim | 6 | — |
| **Display** | sim, **até a prova** | 6, com **Anúncio** = assets de display (papéis, proporções) em vez de RSA | a criação real depende do caminho HTTP de imagens, que hoje não existe no router |
| **Demand Gen** | **não** por formulário | — | escada de portões: `validavel` aberto atrás de flag de servidor, `criavel_pausada` fechado. Ação: "preparar por Search" ou o contrato HTTP tipado |
| **Performance Max** | **não** | — | `planejavel` aberto, `validavel`/`criavel_pausada` bloqueados por decisão de produto registrada. Ação: nenhuma; próximo desbloqueio nomeado |
| **Video** | **não** | — | "observar e analisar" — a API não cria campanha de vídeo |
| **Shopping** | **não** | — | pré-requisito ausente (vínculo Merchant Center) |

**A regra que impede a simetria falsa:** um canal sem construtor **não recebe formulário nem progresso**. Recebe a escada de quatro portões, a causa de cada recusa com sua origem (`operador`/`política`/`produto`/`manifesto`/`servidor`/`construtor`) e a frase do próximo desbloqueio. Botão cinza sem explicação está proibido (`design.md:215`, `PRODUCT.md:24`).

**A regra que impede a promessa falsa:** enquanto `NovaCampanhaPage` montar pedido com `canal: 'SEARCH'` literal, nenhum canal além de Search pode ter CTA que aponte para a Bancada. O CTA "Preparar por Search" de `jornada.ts:798-841` é o comportamento correto e deve sobreviver até a Bancada aceitar canal de verdade.

---

## 11. Mobile

A Bancada é **desktop-first e mobile-honesta**.

| Superfície | ≥1280 | 768–1279 | 320–767 |
|---|---|---|---|
| Bancada — paradas 1, 2, 4, 5, 6 | 3 zonas (conteúdo ≥1100px) | 2 zonas (pedido em gaveta) | 1 coluna, uma parada por vez |
| Bancada — parada 3 (Termos) | mesa completa | mesa completa com rolagem horizontal **contida** | **lista, não tabela**: um termo por linha com volume e correspondência; a comparação fina é declarada como desktop |
| Ignição | tela cheia | tela cheia | tela cheia |
| Recibo | região | região | região |
| `/trafego` inventário | tabela | tabela | linhas compactas (já existe: `useDensidade`) |

Declaração explícita, exigida pelo briefing: **a montagem de uma campanha Search com 23 termos é desktop-first.** No mobile o operador pode ler tudo, revisar o pedido, aprovar e acompanhar; a triagem fina de correspondência por termo é oferecida em forma reduzida e a tela diz que a mesa completa está no desktop. Isto é uma restrição declarada, não uma tela quebrada.

Nenhuma largura pode ter rolagem horizontal de página. Tabelas rolam dentro do próprio contêiner. Ver `RESPONSIVE-AND-A11Y.md`.

---

## 12. O que esta arquitetura recusa

1. **Loader de fases fictícias.** `POST /provar` é **uma** requisição sem subfases observáveis (`MOTION-MAP.md@85666da:27-34` **no blob de `85666da`**). A ignição mostra os degraus que são atos reais — destino (sem chamada), copy (já feita), prova (uma chamada), escrita (uma chamada) — e um cronômetro honesto. Nada de nove passos animados sobre uma chamada.
2. **Progresso por tempo.** Nenhuma barra avança porque o relógio andou.
3. **Segunda linguagem de aba.** O produto já tem duas (segmentada em `ui/tabs.tsx:42`, sublinhada em `HubDeTrafegoPage.tsx:109-115`). A Bancada não cria a terceira: o mapa de paradas é um mapa, visualmente distinto de aba, e o Hub **volta** para a segmentada.
4. **Cartão dentro de cartão.** Hoje há risco real: cartões `card-volc` contendo painéis que também são `card-volc` (`NovaCampanhaPage.tsx:875` × `PainelDoLancamento.tsx:45`).
5. **Grade de cartões iguais** para coisas comparáveis. Termos e campanhas são tabela.
6. **Aurora atrás de dado.** A assinatura marca posição e identidade; nunca fundo de tabela, nunca cor de estado.
7. **Recalcular autoridade no navegador.** Ver `DATA-AND-AUTHORITY-MAP.md` para a lista do que sai do cliente.

---

## 13. Dependências que esta arquitetura cria

Sem estas, a Bancada degrada de forma declarada — não quebra, mas mostra menos:

| Dependência | Sem ela | Onde está registrada |
|---|---|---|
| `projecao.cockpit` serializar `bloqueado`/`bloqueios` | o estado das paradas continua sendo montado no navegador; a tela declara que a elegibilidade é local | `HANDOFF.md@85666da:105-106` **no blob de `85666da`** (M1) — e a ausência confirmada nesta base em `backend/app/trafego/projecao.py:157-177` |
| Frescor na resposta do cockpit | a Bancada não pode carimbar a leitura; mostra "sem carimbo de leitura" | ausência medida em `NovaCampanhaPage.tsx:149-171` |
| `GET …/recibos` | a região Recibo mostra só o recibo da sessão e declara que não há histórico | `docs/growth-engine/frontend.md:245` |
| Caminho HTTP de imagens de Display | Display abre a Bancada e para antes da prova, dizendo por quê | `docs/closure/traffic-creative-operational-closure-v1/backlog-traffic-api-ui.md:90-105` |
| Coletor que lê campanha PAUSED | o Guardião 72h não observa a campanha recém-criada | `docs/closure/hermes-p09-t14-paused-observability-v1/HANDOFF.md:12-16` |

**Nenhuma delas é pré-requisito para começar.** A Bancada nasce declarando o que não sabe — que é exatamente o comportamento que o produto exige de si mesmo.
