# RESPONSIVE-AND-A11Y — contrato de largura, foco, leitura e movimento

Base factual: `207e91f1da290130e8d02b78c3ba1c8e9a761111`.
Autoridade visual: `design.md` (raiz). Autoridade de produto: `PRODUCT.md`.
Este arquivo especifica o comportamento da **Bancada Guiada**, da **Ignição**, do **Recibo**, do **Hub** e da **página canônica** em 320, 375, 414, 768, 1280, 1440 e 1920px, e o contrato de acessibilidade que o executor precisa satisfazer.

**Alvo declarado:** WCAG 2.2 nível AA. **Nada aqui promete conformidade.** Conformidade é resultado de teste com tecnologia assistiva real; este documento define o contrato e nomeia, em §10, o que só a medição pode responder.

---

## 1. A geometria real da janela — por que a largura da viewport não é a largura do trabalho

Esta é a decisão que muda todo o resto, e ela é medida, não estimada.

O shell não é transparente. `src/components/layout/Navigation.tsx:558` fixa a barra lateral em `w-80` quando aberta e `w-16` quando recolhida — **320px e 64px**. O conteúdo vive em `<main className="flex min-w-0 flex-1 flex-col overflow-hidden">` (`src/components/layout/Layout.tsx:47`), e ainda paga o recuo horizontal da página.

O repositório já tinha medido isso e registrado a conclusão. `src/components/trafego/inventario/densidade.tsx:25-38` fixa `LARGURA_AMPLA = 1440` — e não 1280 — com a justificativa escrita no próprio arquivo:

> "Era 1280 (`xl` do Tailwind) e subiu, porque o número de colunas mudou e a janela **NÃO é a largura da tabela**: a navegação lateral do aplicativo ocupa 320 px e o recuo da página come mais 64 px. Numa janela de 1280 sobram ~900 px para onze colunas."

### 1.1 Correção que este documento aplica ao resto da spec

`EXPERIENCE-ARCHITECTURE.md §4` e `§11` colocam o **Pedido em coluna própria a partir de 1280px**. Contra a geometria acima, isso não fecha:

| Viewport | Nav | Largura útil | − Pedido (340) − vão (24) | Sobra para a coluna de decisão |
|---:|---|---:|---:|---:|
| 1280 | aberta (320) | ~896 | 364 | **~532px** |
| 1280 | recolhida (64) | ~1152 | 364 | ~788px |
| 1440 | aberta (320) | ~1056 | 364 | **~692px** |
| 1440 | recolhida (64) | ~1312 | 364 | ~948px |
| 1920 | aberta (320) | ~1536 | 364 | ~1172px |

Uma coluna de decisão de ~532px não sustenta a mesa de Termos, que é o motivo pelo qual a topologia B (coluna larga) foi escolhida em `EXPERIENCE-ARCHITECTURE.md §3.3`. Espremer a mesa para caber o Pedido inverte a própria decisão de topologia.

**Decisão desta spec, que substitui o limiar de 1280:**

> O Pedido ganha coluna própria quando a **largura disponível para o conteúdo** — não a viewport — for **≥ 1100px**. Abaixo disso ele é digest + gaveta.

O gatilho é uma **container query** sobre o contêiner da Bancada, não uma media query de viewport. Motivo factual: a barra lateral é recolhível pelo operador (`Navigation.tsx:558`), então a mesma viewport produz duas larguras de trabalho diferentes, e uma media query decidiria errado em uma delas.

Equivalências de viewport, para captura e teste:

| Nav | Viewport em que o Pedido vira coluna |
|---|---|
| recolhida (64px) | ≈ **1180px** |
| aberta (320px) | ≈ **1500px** |

⚠️ **Correção de aritmética, e ela conserta uma contradição deste próprio arquivo.** A tabela de §1.1 mede que **1440 com a barra aberta deixa ~1056px** — que é **abaixo** dos 1100px exigidos. Logo:

- em **viewport 1440 com a barra aberta, o Pedido é digest + gaveta**, não coluna;
- em **1440 com a barra recolhida** (~1312px de conteúdo), é coluna;
- a coluna com a barra aberta só aparece a partir de ~**1500px** de viewport.

**A tabela mestra de §2.1 e a captura obrigatória de 1440px seguem esta regra**, e a captura de 1440 deve existir **nos dois estados da barra**, porque eles produzem layouts diferentes.

Se o executor não puder usar container query, o fallback é media query em **1500px** — e ele **perde** o caso da barra recolhida, o que precisa ser declarado na tela. Container query é a forma correta; a media query é degradação conhecida.

Registrado como decisão em `DECISION-LOG.md`.

---

## 2. Os sete pontos de largura

Nenhum destes pode ter **rolagem horizontal de página**. Onde há tabela larga, a rolagem acontece **dentro do contêiner da tabela**, com `overflow-x:auto`, e a página não se move.

### 2.1 Tabela mestra

| Superfície | 320 · 375 · 414 | 768 | 1280 | 1440 | 1920 |
|---|---|---|---|---|---|
| **Cabeçalho de identidade** | kicker + H1 32px + `aurora-rule` + propósito; ação primária vira largura total abaixo do propósito | idem, ação à direita | idem | idem, H1 40px | idem |
| **Mapa de paradas** | faixa rolável horizontalmente **dentro de si**, com a parada atual sempre trazida à vista (`scrollIntoView({block:'nearest', inline:'center'})`); sticky sob o cabeçalho | 6 paradas cabem; sticky | sticky | sticky | sticky |
| **Coluna de decisão** | 1 coluna, 100% da largura, `px-4` | 1 coluna, `px-6` | 1 coluna larga | 1 coluna + Pedido (nav recolhida) | 1 coluna + Pedido |
| **Pedido** | digest de 1 linha no rodapé fixo + gaveta (`role="dialog"`) | digest + gaveta | digest + gaveta (nav aberta) · coluna (nav recolhida) | ⚠️ **digest + gaveta com a nav aberta** (~1056px de conteúdo); **coluna sticky 320–360px** com a nav recolhida | coluna sticky |
| **Mesa de Termos** | **lista**, não tabela — um termo por linha | tabela com rolagem contida | tabela | tabela | tabela |
| **Ignição** | tela cheia, degraus empilhados | tela cheia | tela cheia, painel centrado ≤ 720px | idem | idem |
| **Recibo** | região própria, 1 coluna | região | região, ≤ 760px de medida | idem | idem |
| **Hub · inventário** | `densidade: compacta` — lista de linhas altas | `media` — colunas fundidas | `media` | `ampla` — 11 colunas | `ampla` |
| **Hub · abas** | controle segmentado rolável no eixo x, dentro do poço | segmentado | segmentado | segmentado | segmentado |
| **Página canônica** | 8 seções empilhadas; trilha de ação vira barra inferior | empilhadas | 2 zonas | 2 zonas | 2 zonas |
| **Fila de atenção** | cartões de 1 coluna | 1 coluna | 1 coluna larga | 1 coluna larga | 1 coluna larga |

A densidade do inventário **já está implementada** e a Bancada não a reinventa: `densidade.tsx:40-44` define `compacta` < 768 ≤ `media` < 1440 ≤ `ampla`, e `useDensidade` lê a largura no primeiro render via `useSyncExternalStore` (`:57-59`) exatamente para não piscar layout. O executor consome esse hook; não cria um segundo.

### 2.2 O que muda de **marcação**, não só de CSS

`densidade.tsx:1-18` registra a razão pela qual isto não é `hidden md:table`: emitir as duas marcações faria o leitor de tela ler a tela duas vezes e a prova não saberia qual das duas vale. A Bancada herda a regra:

- **Mesa de Termos** em `compacta` é uma `<ul>` de itens, com `<table>` **ausente do DOM** — não escondida.
- **Pedido** em digest é um `<button aria-expanded>` que abre a gaveta; a coluna sticky **não existe no DOM** nessa faixa.
- Nunca duas versões do mesmo conteúdo simultaneamente no DOM com uma escondida por CSS.

### 2.3 ⚠️ A rede de segurança global que já existe — e que a Bancada não pode herdar

`src/index.css:905-913` declara, **fora de qualquer classe de opt-in**:

```css
@media (max-width: 767px) {
  .rollout-guard .grid-cols-3, … { grid-template-columns: repeat(1, minmax(0, 1fr)); }
  table { display: block; overflow-x: auto; -webkit-overflow-scrolling: touch; }
}
```

As regras de grade são escopadas em `.rollout-guard`. **A regra de `table` não é.** Abaixo de 768px, **toda** `<table>` do produto vira `display: block` com rolagem horizontal própria. O comentário acima dela diz exatamente o que isso é: uma rede de segurança para páginas ainda não migradas, e que "nas páginas redesenhadas eu uso responsividade própria e não dependo disto".

Três consequências que o executor precisa saber:

1. **A regra sozinha impede rolagem horizontal de *página*** — a tabela rola dentro de si. Isso é bom, e é por isso que o produto hoje não quebra no telefone.
2. **`display: block` numa `<table>` remove o contexto de tabela do elemento raiz.** A relação linha↔coluna deixa de ser garantida para tecnologia assistiva, e é justamente essa relação que a mesa de Termos existe para expressar.
3. **Portanto a Bancada não se apoia nela.** Abaixo de 768px a mesa de Termos é uma `<ul>` de verdade (§2.2), com a `<table>` **ausente do DOM** — não uma tabela que a rede de segurança transforma em bloco rolável. É a mesma conclusão de `densidade.tsx`, agora com o motivo mecânico.

Onde a Bancada renderiza `<table>` (≥768px), a rolagem contida é responsabilidade do contêiner próprio, com `overflow-x: auto` declarado ali — não herdado desta regra.

### 2.4 A mesa de Termos abaixo de 768px — restrição declarada

`EXPERIENCE-ARCHITECTURE.md §11` declara que a montagem de uma campanha Search com 23 termos é **desktop-first**. Este documento fixa o que isso significa em comportamento:

No telefone o operador **pode**: ler todos os termos, seu volume e sua correspondência; marcar e desmarcar; ler a evidência de elegibilidade; revisar o Pedido; aprovar; acompanhar.
No telefone o operador **não recebe**: a grade de comparação lado a lado de volume × CPC × correspondência × leilão.

E a tela **diz isso**, com estas palavras e um link:

> "A comparação lado a lado dos 23 termos está no desktop. Aqui você marca, desmarca e lê cada termo — mas não compara colunas."

Isto é uma restrição nomeada, não uma tela quebrada. Nenhum controle fica escondido sem aviso; nenhum controle fica presente e inerte.

---

## 3. Pedido, mesa e regiões fixas — o contrato de comportamento

### 3.1 Pedido
| Faixa | Forma | Regras |
|---|---|---|
| conteúdo ≥ 1100px | coluna `sticky top-[<altura do mapa>]`, 320–360px, com rolagem própria (`max-h-[calc(100dvh-…)] overflow-y-auto`) | nunca ultrapassa a altura da janela; nunca cria rolagem de página |
| conteúdo < 1100px | digest fixo no rodapé (altura 56px) + gaveta | o digest carrega exatamente três fatos: **conta**, **teto do dia**, **o que falta (n)** |

A gaveta é `role="dialog" aria-modal="true"`, fecha com `Esc`, devolve foco ao gatilho, e o conteúdo de trás recebe `inert` enquanto aberta.

O rodapé fixo reserva espaço: o contêiner da Bancada leva `padding-bottom` igual à altura do digest, para que o último controle da parada nunca fique sob ele.

### 3.2 Mesa de termos
- ≥ 768px: `<table>` real, `<caption class="sr-only">`, `scope="col"`/`scope="row"`, cabeçalho fixo dentro do contêiner (`position: sticky; top: 0` no `<thead>`), rolagem no contêiner.
- < 768px: `<ul>` com um item por termo. Cada item é uma linha alta com nome, volume, correspondência e o controle de marcação.
- Em nenhuma faixa a tabela empurra a página lateralmente.

### 3.3 Regiões fixas — o orçamento de altura
Em 320×568 (o pior caso real), as regiões fixas não podem comer a tela:

| Região | Altura | Fixa? |
|---|---|---|
| header do shell | 56px (`h-14`, `Layout.tsx:50`) | sticky |
| cabeçalho de identidade | 180–220px | rola |
| mapa de paradas | 48px no telefone (56 no desktop) | sticky |
| digest do Pedido | 56px | fixo no rodapé |

Sobra útil em 320×568: **568 − 56 − 48 − 56 = 408px**. É pouco, e por isso o cabeçalho de identidade **rola para fora** no telefone: só o mapa e o digest permanecem. Nenhuma terceira região ganha `sticky` no telefone.

### 3.4 Unidades de altura
Usar `dvh`, não `vh`, em qualquer cálculo de altura de janela — a barra de endereço do navegador móvel muda `vh` e produz salto de layout. Onde `dvh` não estiver disponível, `vh` como fallback na mesma declaração.

---

## 4. Foco, ordem do DOM e teclado

### 4.1 O que já existe e a Bancada herda
- **Pular para o conteúdo**: `Layout.tsx:31-36` — `<a href="#conteudo-principal">`, `sr-only` até receber foco. A Bancada garante que `#conteudo-principal` exista e envolva a coluna de decisão.
- **Anel de foco**: `src/index.css:380-384` — `outline: 2px solid hsl(var(--ring) / 0.7); outline-offset: 2px; border-radius: 2px`, em `:focus-visible`. `--ring` é `216 85% 44%` no claro (`:141`) e `214 90% 66%` no escuro (`:229`).
- **Alvo mínimo**: `.touch-target` = `min-h-[44px] min-w-[44px] md:min-h-[40px] md:min-w-[40px]` (`src/index.css:275-277`). ⚠️ O comentário acima dela (`:250-274`) registra que a folha antiga `src/styles/mobile-responsive.css` **nunca foi importada** e que 55 chamadas de `.touch-target` eram no-op — a sonda mediu alvos de 16×16 em controles que o código supunha protegidos. **A Bancada não confia na classe: mede o alvo renderizado.**

### 4.2 Ordem de tabulação
`MOTION-AND-INTERACTION.md §5` fixa a ordem. Este documento adiciona a regra de **equivalência entre ordem visual e ordem do DOM**:

- A ordem do DOM é: cabeçalho → mapa → coluna de decisão → **Pedido** → rodapé.
- Em ≥1100px o Pedido aparece **à direita** da coluna de decisão, mas vem **depois** dela no DOM. Isso é correto: o Pedido é resumo, não pré-requisito da decisão.
- A colocação lateral é feita com **grid** e `grid-column`, nunca com `order` que inverta a leitura — `order` só é permitido quando não separa ordem visual de ordem de leitura (WCAG 1.3.2, 2.4.3).
- Nenhum `tabindex` positivo em lugar nenhum.

### 4.3 Mapa de paradas
- `<nav aria-label="paradas do lançamento">` contendo `<ol>`.
- Parada alcançável: `<Link>` com `aria-current="step"` na atual.
- Parada bloqueada: `<span aria-disabled="true">` + causa ligada por `aria-describedby`. **Nunca** um `<button disabled>` — um destino que não leva a lugar nenhum não deve ter afordância de clique.
- Ao trocar de parada, o foco vai para o `<h2>` da pergunta com `tabIndex={-1}`, e uma região `aria-live="polite"` anuncia "parada 3 de 6 — Termos". Uma vez, não a cada re-render.

### 4.4 Mesa de termos
- `Tab` percorre os controles. **Sem** navegação por setas simulada: a tabela não é uma grade de aplicação e fingir que é quebra a expectativa do leitor de tela.
- `Espaço` marca/desmarca o controle focado.
- O cabeçalho fixo não pode cobrir a linha focada: ao focar uma linha sob o `<thead>` sticky, `scroll-margin-top` igual à altura do cabeçalho.

### 4.4b Três defeitos de alvo e rolagem, medidos

| Defeito | Onde | Consequência |
|---|---|---|
| ⚠️ **a Ignição não rola** — `.ignicao` é `display:grid; grid-template-rows: 1fr auto; overflow:hidden` e o painel usa `justify-center` sem contêiner de rolagem | `Lancamento.tsx:270-271`; `src/index.css:925-928` | em 320×568, com o recibo aberto, o conteúdo que não couber **não é alcançável por rolagem nenhuma** |
| ⚠️ **os blocos da régua de leilão respondem só a mouse** — `onMouseEnter`/`onMouseLeave` são os únicos manipuladores; zero `title`, `tabIndex`, `onFocus`, `onKeyDown`, e só o dominante tem `aria-label` | `ReguaDeLeilao.tsx:149-160` | por teclado e por toque, a régua é uma imagem muda |
| ⚠️ **abaixo de 640px o botão principal fica desabilitado sem razão visível** — a lista "falta:" é `hidden … sm:block`; e no ramo `jaLancou` a razão não aparece em **nenhuma** largura | `NovaCampanhaPage.tsx:454-479` | o diagnóstico de por que não dá para lançar existe só no desktop |

E a lista completa de pendências **nunca é enumerada**: a barra corta em 2 itens e resume o resto como "+N" (`:471-472`), enquanto `pendencias` pode acumular três fontes mais um item por bloqueio do servidor.

### 4.5 Ignição e Recibo
- Ignição: `role="dialog" aria-modal="true"`, foco entra no painel, fundo `inert`, `Esc` fecha **exceto** durante `escrevendo`, e a tela **diz por que não fecha**. Ao fechar, foco volta ao gatilho.
- Escada: `<ol>` com `aria-live="polite"` no contêiner. Cada degrau resolvido anuncia nome + veredito **uma vez**. O cronômetro **não** é anunciado — é `aria-hidden`, porque um contador por segundo torna a região inútil.
- Recibo: região com `id="recibo"`, foco programático na revelação, anúncio "campanha criada, pausada".

### 4.6 Sem atalho global novo
O caminho rápido é o mapa, a parada Revisão e a paleta existente (`src/components/CommandPalette.tsx`). Nenhuma tecla nova é inventada. Qualquer atalho de caractere único, se algum dia existir, precisa de desativação ou remapeamento (WCAG 2.1.4) — hoje não existe nenhum, e é assim que fica.

---

## 5. Leitores de tela — o que a tela precisa dizer

### 5.1 Nome acessível estável
Todo controle tem nome acessível que **não muda com o estado**. "Confirmar e seguir" não vira "Confirmando…" no nome acessível: o rótulo permanece e o estado vai em `aria-busy`. Trocar o nome faz o leitor anunciar um controle novo, e o operador perde o lugar.

### 5.2 Hierarquia de títulos
`h1` uma vez (identidade da campanha) → `h2` a pergunta da parada → `h3` blocos de evidência. Sem salto de nível. Sem `h1` dentro do Pedido ou da gaveta — a gaveta abre com `h2`.

### 5.3 Estado nunca só por cor
Regra de `PRODUCT.md:36` e `design.md:105`. Todo estado combina **glifo + palavra + descrição**. O componente canônico já existe: `src/components/trafego/inventario/Selos.tsx`. O executor usa esse, não recria.

A correspondência única de portão fixada em `VISUAL-DIRECTION.md §5` (`PERMITIDO`/`BLOQUEADO`/`INDETERMINADO`/`NAO_APLICAVEL`) vale também para o leitor de tela: a **palavra** é o portador primário, e a cor é redundância.

### 5.4 Regiões vivas — orçamento
Regiões `aria-live` são caras: cada uma fala por cima da anterior. A Bancada tem exatamente **três**:

| Região | Polidez | O que anuncia |
|---|---|---|
| troca de parada | `polite` | "parada N de 6 — Nome" |
| escada da ignição | `polite` | nome do degrau + veredito, uma vez cada |
| erro de operação | `assertive` (`role="alert"`) | a frase do erro, com o próximo ato |

O Pedido **não** é uma região viva. Ele muda a cada decisão e falaria o tempo todo. O que ele faz é receber `aria-describedby` a partir do controle que o alterou, e o traço visual de 1200ms (`MOTION-AND-INTERACTION.md §2`) é a pista visual equivalente.

### 5.5 Ausência é lida
`—` sozinho não é conteúdo para leitor de tela. Toda ausência tem texto alternativo que nomeia **quem não leu**: `<span aria-label="meta efetiva: ninguém leu">—</span>`, ou melhor, o texto visível já diz. Nunca uma célula vazia, nunca `0` no lugar de ausência.

---

## 6. Contraste

### 6.1 O que já está medido no repositório
`src/components/trafego/inventario/__tests__/acessibilidade-do-inventario.test.tsx` **calcula** o contraste a partir dos tokens reais de `src/index.css` — não confere de olho. Dois invariantes vivos:

- `:447-464` — as caixas de estado passam ≥ 4.5:1 nos dois temas, incluindo os leitos tingidos (painel de falha, aviso parcial, aviso de dado antigo), que o próprio arquivo chama de "os piores do produto".
- `:466-489` — **`--muted-foreground` alcança AA sobre `card`, `background` e `muted`, nos dois temas.**

⚠️ **Armadilha de leitura.** O comentário de cabeçalho desse arquivo (`:10-14`) ainda diz que `--muted-foreground` "só passa na AA quando o fundo é o branco de `--card`". Isso descreve o estado **anterior**. O corpo do teste (`:472-478`) registra que o token foi de 45% para 40% de luminosidade e que a prova **inverteu de sentido**, passando a guardar o invariante em vez do defeito. **Vale o corpo do teste, não o cabeçalho.** Um executor que citar o cabeçalho reintroduz uma compensação (`--foreground/75`) que já foi revertida.

### 6.2 O que a Bancada precisa satisfazer
| Alvo | Razão mínima | Onde |
|---|---|---|
| texto normal (< 18.66px, ou < 24px se não-negrito) | **4.5:1** | todo corpo, metadado, rótulo |
| texto grande | 3:1 | H1, H2 |
| borda de controle, glifo que carrega significado, anel de foco | **3:1** contra o vizinho | `--ring`, bordas de campo, glifos de estado |
| estado desabilitado | isento pela WCAG, **não isento aqui** | precisa continuar legível: a razão adjacente é texto normal e paga 4.5:1 |

Nenhum texto sobre gradiente. Nenhum texto sobre imagem sem leito sólido. Nenhum `text-white/35` — proibido explicitamente, e é o defeito medido hoje em `Lancamento.tsx` (`VISUAL-DIRECTION.md §2`).

### 6.3 Equivalência claro/escuro
`design.md` exige que o escuro seja completo e equivalente, não uma pele reduzida. O contrato:

- Todo token semântico tem par no escuro; nenhuma cor crua (`text-slate-*`, `border-l-rose-*`) sobrevive, porque cor crua não tem par de tema — é a maior dívida visual medida do módulo (`VISUAL-DIRECTION.md §2`).
- Toda captura de aceite existe **nos dois temas**.
- A hierarquia é preservada, não invertida: o que é dominante no claro é dominante no escuro.

---

## 7. Zoom, reflow e tamanho de texto

| Requisito WCAG | Alvo | Contrato |
|---|---|---|
| 1.4.4 Redimensionar texto | 200% | nenhum texto cortado, nenhuma função perdida |
| 1.4.10 Reflow | 320 CSS px (= 1280 a 400%) | **sem rolagem em dois eixos**; a exceção permitida é a mesa de Termos, e ela rola **dentro do contêiner** |
| 1.4.12 Espaçamento de texto | linha 1.5×, parágrafo 2×, letra 0.12em, palavra 0.16em | nada some, nada sobrepõe |

Consequências mecânicas:

- Nenhuma altura fixa em contêiner de texto. `min-height`, nunca `height`, onde há frase.
- Nenhum `overflow: hidden` que corte texto ampliado. Truncar preserva acesso ao valor por expansão ou `title` acessível (`design.md:176`).
- Unidades **relativas** (`rem`) para tipografia. `px` só em borda, raio e traço.
- A mesa de Termos, a 400% de zoom, vira a mesma `<ul>` do telefone — porque 1280 a 400% **é** 320 CSS px, e é a mesma faixa de `densidade: compacta`. Isso não é uma segunda implementação: é a mesma.

---

## 8. Movimento reduzido

`src/index.css:567-604` já implementa a regra universal, e a Bancada herda sem alterar o mecanismo. O que importa registrar, porque é contraintuitivo e o próprio arquivo explica por quê (`:585-597`):

- A regra é **universal** com exceção **nominal**: `[data-motion="essencial"]`, `.animate-spin` e `.animate-progress-indeterminate`.
- `.animate-spin` fica em **1.4s** e `.animate-progress-indeterminate` em **2.4s** — **lentas, não paradas**. Um spinner congelado lê como tela travada, que é pior que o movimento.
- `.reveal` e as animações de entrada terminam **visíveis** (`animation: none; opacity: 1; transform: none`), nunca somem.
- `hover-lift` e `card-hover` perdem o `transform`.

Especialização da Bancada, conforme `MOTION-AND-INTERACTION.md §7`: troca de parada vira crossfade de 120ms sem `translateY`; o marcador do mapa salta; a revelação do recibo vira fade de 150ms sem máscara; o horizonte da ignição fica fixo no `--avanco` do estado atual.

**Regra que fecha a seção:** movimento funcional sobrevive; movimento espacial vira opacidade. E toda captura de aceite existe também em `prefers-reduced-motion: reduce`.

---

## 9. O que é deliberadamente desktop-first — declarado, não escondido

| Capacidade | Faixa em que existe plena | O que o telefone recebe | Por quê |
|---|---|---|---|
| Comparação lado a lado de 23 termos (volume × CPC × correspondência × leilão) | ≥ 768px | lista marcável, sem grade comparativa, **com aviso** | comparar 4 dimensões em 320px produz ou fonte ilegível ou rolagem em dois eixos |
| Pedido persistente em coluna | conteúdo ≥ 1100px | digest de 3 fatos + gaveta | abaixo disso a coluna espremeria a decisão |
| Inventário com 11 colunas | ≥ 1440px | colunas fundidas (768–1439) · lista (< 768) | `densidade.tsx:25-38`, medido |
| Régua de leilão | ≥ 768px | valor + janela + fonte, sem a régua | a régua é comparação espacial |

**Nada nesta tabela é uma funcionalidade removida em silêncio.** Em cada caso a superfície reduzida diz o que não está ali e onde está. Um controle ausente e explicado é honesto; um controle presente e inerte é uma mentira de interface.

E **nada** aqui degrada a segurança: prova, aprovação, criação pausada, recibo e reconciliação funcionam integralmente em 320px. A restrição é de **comparação**, nunca de **autoridade**.

---

## 10. O que este documento NÃO pode afirmar

Limites reais, para que ninguém leia contrato como conformidade:

1. **Nenhuma rota autenticada foi inspecionada em navegador nesta missão.** `MASTER-SPEC.md §7` registra a causa. Todo número de largura aqui vem de código e de geometria, não de tela renderizada com sessão.
2. **Nenhum leitor de tela real foi executado.** VoiceOver, NVDA e JAWS não foram usados. O contrato de §4 e §5 é derivado de norma e do código existente; ele precisa de teste manual antes de qualquer alegação de AA.
3. **Nenhuma medição de contraste foi feita sobre pixels renderizados.** As razões citadas em §6.1 são as que o teste do repositório **calcula a partir dos tokens** — o que é forte, mas não cobre texto sobre leito composto que a Bancada ainda não tem.
4. **`.touch-target` não é prova de alvo.** O histórico em `src/index.css:250-274` mostra que a classe já foi no-op por não estar importada. O aceite exige medição do retângulo renderizado, não a presença da classe.
5. **WCAG 2.2 AA é alvo, não estado.** Os critérios que só a medição fecha estão listados como contraprovas em `EXECUTOR-ACCEPTANCE.md`; até que rodem, o correto é dizer "projetado para AA", nunca "conforme AA".
