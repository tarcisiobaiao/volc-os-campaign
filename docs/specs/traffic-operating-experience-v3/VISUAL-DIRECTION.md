# VISUAL-DIRECTION — direção visual, tipografia, superfície, cor e anti-referências

Autoridade: `design.md` (raiz), com a cadeia de cinco níveis já estabelecida em `docs/design/AUTORIDADE-VISUAL-RECONCILIADA.md:20-27`.

> ⚠️ **Três correções a este arquivo**, verificadas por comando e detalhadas em `DECISION-LOG.md §3` e `§5`: (a) a divergência de cor de portão é entre `canais/PortoesDoCanal.tsx:55-79` e `canais/PainelDaMensuracao.tsx:67-74` — **`estudio/JornadaDoCanal.tsx` não existe nesta base**; (b) a paleta crua não são 93 ocorrências, são **216** em 6 arquivos; (c) `src/lib/motion.ts` é do projeto externo `nota1000-canvas`, não deste repositório. As demais contagens (235 · 19 · 2 · 12 · 30) **conferem**. Este arquivo **não cria um terceiro sistema visual**; ele decide como a Bancada Guiada usa o que já existe, corrige o que está fora do contrato e nomeia o único lugar onde a ambição pede mais do que o contrato hoje descreve.

Todos os valores citados vêm do **código** (`src/index.css`, `tailwind.config.ts`), não do front-matter de `design.md`. Onde os dois divergem, a divergência está registrada em §7.

---

## 1. Registro `impeccable shape`

**Contexto carregado**
- `PRODUCT.md` (36 linhas) — usuários, propósito, anti-referências, princípios, acessibilidade.
- `design.md` (253 linhas, raiz) — contrato de UI do produto, incluindo o "Agent contract" (`:65-77`), a identidade de página obrigatória (`:80-91`), superfícies/abas/chips/inventário (`:93-100`), aurora/cor/tipo (`:102-106`), motion (`:108-124`) e as proibições duras (`:126-134`).
- `src/index.css` (978 linhas) e `tailwind.config.ts` — os tokens realmente implementados.

**Register:** `product`. Confirmado pelo campo em `PRODUCT.md:5` e pela cena: superfície autenticada, operador em tarefa, densidade e familiaridade são feature. O design **serve** o produto; não é o produto.

**Cena (frase que força o tema):** *um operador às 14h, num monitor de 27 polegadas ao lado de uma janela, conferindo evidência antes de autorizar o primeiro gasto de uma campanha que nasce pausada.* → **claro é o padrão**; escuro é completo e equivalente, nunca uma pele reduzida.

**Estratégia de cor:** `Restrained` — neutros levemente tingidos em ~90% da superfície, um azul primário como única cor de ação, vocabulário semântico fechado para estado. A superfície **não** sobe para `Committed`: o momento de ignição (§6.3) é a única exceção, e ela é contida numa tela própria.

**Referências adicionais que a implementação deverá usar**
| Referência | O que herdar | Onde |
|---|---|---|
| Login | a ideia de **luz como estado** (intensidade acompanha progresso real, laranja só no sucesso) e o painel de falha com `role="alert"` e código real | `src/pages/Login.tsx:184-236`; CSS `src/index.css:614-740` |
| BootSplash | a técnica de **máscara radial `--hole`** para revelar conteúdo a partir de um ponto | `src/components/BootSplash.tsx:42,69-71`; CSS `src/index.css:868-880` |
| Ignição atual | a escada de degraus com veredito por degrau e o horizonte guiado por `--avanco` | `src/components/trafego/Lancamento.tsx:672-716`; CSS `src/index.css:925-978` |
| QG Agêntico | a pilha de identidade de página completa e as abas segmentadas com roving tabindex | `src/pages/settings/QGAgenticoPage.tsx:71-99` |
| Pautador Pro / Redator | a mesma pilha, e a régua de medida | `src/pages/PautadorProPage.tsx:110-129`; `src/pages/RedatorPage.tsx:79-108` |
| Estúdio Criativo | a regra dos três planos e a `Secao` | `src/components/criativos/comum/Painel.tsx:34-77` |
| Ação desabilitada com razão adjacente | o modelo de "consequência antes da ação" | `src/components/trafego/lote/QuadroDoLote.tsx:305-335` |
| nota1000-canvas | apenas a **forma** da transição de rota (entrada/saída assimétricas, `AnimatePresence mode="wait"`, `MotionConfig reducedMotion="user"`), reafinada para 150–220ms | `nota1000-canvas/src/components/shell/PageTransition.tsx`, `src/lib/motion.ts` |

**Decisões de `design.md` preservadas sem discussão**
1. Identidade de página obrigatória: kicker + chip 20×20 → H1 Space Grotesk 32–40 → `aurora-rule w-16` → propósito → no máximo uma ação primária (`design.md:82-89`).
2. Aurora é assinatura de identidade; **nunca** estado operacional, fundo de tabela, cor de alerta ou preenchimento de progresso (`design.md:104`).
3. Vocabulário semântico fechado: `primary`, `verified`, `success`, `warning`, `destructive`, `info` — e cor nunca é o único portador de significado (`design.md:105`).
4. Duas famílias, só: Space Grotesk e Inter. Numerais tabulares em qualquer número que compara ou atualiza (`design.md:106`).
5. Inventário é tabela, nunca grade de cartões iguais (`design.md:98`).
6. Cartão dentro de cartão é sempre errado (`design.md:100`).
7. Abas são controle segmentado em poço `bg-muted`, selecionado `bg-card shadow-card`; **nunca** sublinhado (`design.md:96`).
8. Motion 150–220ms, curva de entrada `cubic-bezier(0.22,1,0.36,1)`, propriedades nomeadas, `scale(0.96)` no press, hover-lift só em ponteiro fino, sem stagger de carregamento no Hub (`design.md:110-122`).
9. `docs/design/DESIGN-SYSTEM.md` é sistema de apresentação e **não** governa esta superfície (`design.md:75`).

**Conflitos entre o design system atual e a ambição desta superfície** — os quatro reais, com a resolução adotada:

| # | Conflito | Resolução |
|---|---|---|
| C1 | `design.md:82-84` torna o **kicker obrigatório** na identidade de página; a disciplina anti-slop de Hallmark trata sobrancelha por seção como o tell mais recorrente (uma a cada três seções, no máximo) | O kicker existe **uma vez** no cabeçalho da página (contrato de `design.md`) e **no máximo uma vez por região maior** (Pedido, Ignição, Recibo). **Proibido** kicker por bloco de evidência. Na prática: ≤4 kickers na Bancada inteira. Gate mecânico em `EXECUTOR-ACCEPTANCE.md`. |
| C2 | `design.md:120` proíbe stagger de carregamento no Hub; a Bancada quer que a **troca de parada** seja perceptível | Stagger de página continua proibido. A troca de parada é uma **transição de conteúdo** (crossfade 80ms out / 160ms in), não um stagger de entrada. `.reveal` sai de `/trafego/nova` inteiramente. |
| C3 | `design.md` não tokeniza raio de modal (12px) e o código expõe a escada shadcn 8/6/4 (`--radius: 0.5rem`, `tailwind.config.ts:92-96`) | A Bancada usa a escada do código. Raios concêntricos: painel 8px com padding 8px ⇒ elemento interno 4px (`rounded-lg` > `rounded-sm`). Nenhum raio novo é criado. |
| C4 | `design.md:193,201` ainda dizem que a pílula selecionada é `bg-background`; `design.md:96` e o código dizem `bg-card` (`src/components/ui/tabs.tsx:42`) | Vale `design.md:96` + código. `bg-background` **é** o canvas (`#F3F5F7`): a pílula sumiria na página. Divergência registrada em `DECISION-LOG.md`. |

---

## 2. Auditoria anti-AI-slop do estado atual (`hallmark audit`)

Alvo: `src/pages/trafego/**` e `src/components/trafego/**` na base `207e91f`. Contagens medidas por varredura, excluindo testes.

### Critical — entrega como slop

```
[critical] Underline tabs — src/pages/trafego/HubDeTrafegoPage.tsx:109-115 (aplicado em :574-607)
  o Hub, que design.md:136 nomeia como referência a copiar, usa o vocabulário
  de aba que design.md:96 e :130 proíbem por nome
  → voltar ao controle segmentado de src/components/ui/tabs.tsx:42 (poço bg-muted, pílula bg-card shadow-card)

[critical] Side-stripe colorida >1px — 12 ocorrências de border-l-2
  Lancamento.tsx:319,333,376 · PainelDaMensuracao.tsx:238,255 · PlanoDeMensuracao.tsx:188
  PortoesDoCanal.tsx:100 · VereditoDaSentinela.tsx:226 · VereditoDePolitica.tsx:144
  MesaDeLance.tsx:181 · LinhaDeCampanha.tsx:572 · ItemDeAtencao.tsx:183
  as neutras (border-border) são citação e passam; border-warning/60, border-destructive/60,
  border-l-rose-400 e border-l-violet-400 são faixas coloridas de 2px — design.md:99,130
  → hairline de 1px em toda a volta, ou fundo tingido, ou glifo à esquerda. Para estado
    num cartão: hairline de 2px no TOPO, que é o que design.md:99 autoriza

[critical] Métrica-herói com tratamento de identidade — NovaCampanhaPage.tsx:593
  `text-outline font-display text-4xl md:text-5xl` no "volume/mês selecionado":
  tipografia de escala de apresentação + .text-outline (assinatura de marca) sobre um número
  → o volume é um dado de dimensionamento, não um herói. 17px semibold tabular na régua
    de leilão, com a janela e a fonte ao lado

[critical] Paleta crua fora do vocabulário fechado — 93 ocorrências em canais/
  PainelDeCanais.tsx (49) · PortoesDoCanal.tsx (21) · PainelDaMensuracao.tsx (13) · PlanoDeMensuracao.tsx (10)
  text-slate-*, border-l-rose-400, border-l-violet-400, text-rose-700, dark:text-slate-300
  sem equivalência de tema escuro e fora de design.md:105
  → tokens semânticos. Esta é a maior dívida visual medida do módulo
```

### Major — parece gerado

```
[major] Teatro de carregamento em página operacional — design.md:120,132
  NovaCampanhaPage.tsx:493,522,548,684,696,703,875 (todo Cartao é `reveal card-volc`)
  Lancamento.tsx:693 (cada Degrau é .reveal --i, dentro de um modal que re-renderiza a cada estado)
  → .reveal sai de /trafego/nova. A ignição usa transição de estado, não entrada encenada

[major] Hover-lift em superfície não interativa — 8 sites de card-volc
  PortaoDePolitica.tsx:56 · PainelDoLancamento.tsx:45 · VereditoDePolitica.tsx:80
  JaNoAr.tsx:46 · NovaCampanhaPage.tsx:522,875,1002
  .card-volc (index.css:427-439) sobe translateY(-3px) em 250ms com borda primary a cada
  passagem do mouse, em painéis que não são clicáveis — e 250ms/-3px viola design.md:114-118
  → painel estático não reage ao mouse. Reservar o lift para linha/cartão clicável, a -2px,
    200ms, dentro de @media (hover:hover) and (pointer:fine)

[major] Glassmorphism decorativo em cromo operacional — design.md:130
  NovaCampanhaPage.tsx:437 barra fixa `bg-background/85 backdrop-blur-md`
  GrupoDeConta.tsx:296 `backdrop-blur-[2px]` no cabeçalho de conta
  → bg-card sólido + shadow-card, que é o que design.md:189 chama de "restrained
    structural shadow for sticky toolbars"

[major] Piso tipográfico rompido — 235 ocorrências de text-[11px] para copy explicativa
  + 19 de text-[10px] + 2 de text-[9px] (NovaCampanhaPage.tsx:855 nos numerais do trilho,
  ReguaDeLeilao.tsx:190)
  design.md:172: "essential actions and explanatory text never drop below 14px"
  → escala de §3. Nenhum texto que decide abaixo de 14px; nada abaixo de 12px

[major] Uppercase como textura — 30 ocorrências fora de .kicker, a 10–12px
  BancadaDeDecisao.tsx:84,232,271,297-299,326,331-338,417 · PainelDaMensuracao.tsx:91,117,231,248,293
  PlanoDeMensuracao.tsx:44,75,128,178 · cabeçalhos de tabela a text-[10px] uppercase
  design.md:174: "Uppercase is a navigation aid, not a decorative texture"
  → caixa de sentença. Uppercase só no .kicker

[major] Controle desabilitado sem razão visível — NovaCampanhaPage.tsx:461-465, 470-479
  "Lançar outra" desabilita sem dizer por quê; "Lançar campanha" mostra o motivo
  apenas de `sm:` para cima (`hidden … sm:block`) — invisível justamente no mobile
  → design.md:215. Modelo correto já existe em QuadroDoLote.tsx:305-335 (parágrafo de
    razão ligado por aria-describedby)

[major] Segunda assinatura de identidade fora do shell — laboratorio/bancada.css:18-25
  `.di-assinatura` desenha 2px de var(--gradient-aurora) dentro do laboratório
  → aurora pertence à borda do shell e aos marcos de identidade (design.md:104)

[major] Animação de propriedade de layout — bancada.css:113-120 anima filter: blur
  PainelDoRun.tsx:128, Acompanhamento.tsx:88, QgTimeline.tsx:105-108 animam width
  design.md:122: "Never width, height, top, left". O primitivo ui/progress.tsx:18-21 já
  usa translateX e ninguém em trafego o consome
  → scaleX / translateX, ou o primitivo
```

### Minor

```
[minor] mix-blend-difference a 10px — ReguaDeLeilao.tsx:176
[minor] H1 abaixo do contrato — CampanhaCanonPage.tsx:101,118,157 usa text-2xl md:text-3xl
        (design.md:83 pede 32–40px)
[minor] Contraste e piso dentro da ignição — Lancamento.tsx:645,711,771,796-801
        texto text-white/35–60 a 10–11px sobre fundo escuro animado
[minor] Risco de cartão aninhado — NovaCampanhaPage.tsx:551,684-708: cartões card-volc
        recebendo painéis que também são card-volc
```

```
Resumo — 4 critical · 8 major · 4 minor
Veredito — reads as AI-generated. Não pelo que falta: pelo empate. Quatro linguagens de
superfície convivem (card-volc, rounded-md+border, bg-muted well, slate cru), o piso
tipográfico está rompido em 256 lugares, e a única superfície com hierarquia forte —
a ignição — é a que o operador vê por último.
```

---

## 3. Tipografia da Bancada

Duas famílias, sem terceira. Space Grotesk carrega **título e kicker**; Inter carrega **todo o resto**, inclusive número.

| Papel | Família / tamanho / peso | Onde |
|---|---|---|
| Kicker | Space Grotesk 11px / 600 / `letter-spacing: 0.16em` / uppercase | `.kicker`, `src/index.css:398-405`. Máximo 4 na Bancada (§C1) |
| H1 — identidade da campanha | Space Grotesk **32px** (`md:40px`) / 700 / `tracking-tight` / `leading-[1.05]` | cabeçalho da página |
| H2 — pergunta da parada | Space Grotesk **22px** (`md:24px`) / 600 / `tracking-tight` | topo da coluna de decisão |
| H3 — bloco de evidência | Inter **15px** / 600 | dentro da parada |
| Corpo operacional | Inter **14px** / 400 / `line-height: 1.5` / `text-pretty` | **piso absoluto de leitura** |
| Metadado que acompanha um valor legível | Inter **13px** / 400 | fonte, janela, "lido há 6 min" |
| Rótulo de coluna repetido | Inter **12px** / 500 | cabeçalho de tabela — **em caixa de sentença** |
| Números que comparam | Inter, `font-variant-numeric: tabular-nums`, alinhados à direita | já forçado em `th,td,[data-numeric],.tabular` (`index.css:369-372`) |
| Valor destacado no Pedido | Inter **17px** / 600 / tabular | teto de gasto, conjunto, orçamento |

**Regras duras**
- **Nada abaixo de 12px.** `text-[9px]`, `text-[10px]` e `text-[11px]` desaparecem de `/trafego/nova` e da ignição.
- **Nenhum texto que sustenta decisão abaixo de 14px.** Causa de bloqueio, exigência de portão, ressalva de CPC minerado, próximo ato: 14px.
- **`text-wrap: balance` em título; `text-pretty` em explicação.** Medida de leitura 65–75ch (`max-w-[70ch]`).
- **`clamp()` proibido em título de produto** (`design.md:106`).
- **Truncar preserva acesso ao valor inteiro** por expansão ou `title` acessível (`design.md:176`).

---

## 4. Superfícies e planos

Quatro planos. Nunca cinco, nunca cartão aninhado.

| Plano | Tratamento | Onde na Bancada |
|---|---|---|
| **Canvas** | `--background` `210 20% 96%` (`index.css:17`) | a página |
| **Superfície de trabalho** | `bg-card` + `border-border` + `shadow-card` (`index.css:125-127`) | a parada aberta; o Pedido; o cartão de recibo |
| **Agrupamento interno** | hairline 1px + poço `bg-muted/20`; **sem sombra** | blocos de evidência dentro da parada |
| **Linha selecionada / interativa** | fundo tingido + acento primário inset; **não flutua** | termo marcado na mesa; parada no mapa |

- `.card-volc` (`index.css:427-439`) **não é usado** na Bancada. Ele carrega hover-lift de 250ms e −3px, fora do contrato. A superfície de trabalho é `bg-card border border-border shadow-card rounded-lg`, sem hover.
- Raios concêntricos: contêiner `rounded-lg` (8px) com `p-2` (8px) ⇒ filho `rounded-sm` (4px). Contêiner com `p-5`/`p-6` trata o filho como superfície independente e escolhe o raio pelo próprio papel.
- Sombra é **posse e camada temporária**, não importância: poço e hairline separam dentro da superfície; sombra só distingue a superfície do canvas, o popover do conteúdo e o modal de tudo.
- Imagens (miniatura de asset em Display/Demand Gen) recebem `outline: 1px solid rgba(0,0,0,.1)` no claro e `rgba(255,255,255,.1)` no escuro, com `outline-offset: -1px` — nunca um neutro tingido.

---

## 5. Cor

**Estratégia:** `Restrained`. Neutros tingidos ~90%; `--primary` `216 85% 34%` (`index.css:27`) como única cor de ação; semântica fechada para estado.

| Token | Valor implementado | Significa | Nunca |
|---|---|---|---|
| `--primary` | `216 85% 34%` :27 | ação padrão, seleção, link que avança | estado, sucesso |
| `--verified` | `192 100% 26%` :80 | **observado / reconciliado** | sucesso |
| `--success` | `162 73% 25%` :66 | estado saudável concluído | "está tudo bem" por ausência |
| `--warning` | `36 90% 28%` :68 | atenção pendente, decisão que pede cuidado | erro |
| `--destructive` | `0 56% 45%` :85 | erro real, bloqueio, ato irreversível | atenção |
| `--info` | `191 92% 26%` :83 | contexto declarado | evidência |
| `--muted-foreground` | `214 9% 40%` :47 | metadado, ausência, ignorância | texto que decide |
| aurora | `191/214/271/14` :89-92 | **identidade** | estado, fundo, progresso, métrica |

**A gramática de estado — glifo + palavra + descrição, sempre.** Nenhum estado é comunicado só por cor (`PRODUCT.md:36`). O `Chip` de `src/components/trafego/inventario/Selos.tsx` já implementa isso e é o componente canônico.

**A regra que hoje está quebrada em dois lugares:** dois renderizadores de portão discordam de cor para o mesmo veredito — `canais/PortoesDoCanal.tsx:57-62` pinta `BLOQUEADO` de âmbar e `INDETERMINADO` de ardósia; `canais/PainelDaMensuracao.tsx:67-74` pinta `BLOQUEADO` de vermelho e `INDETERMINADO` de âmbar. A Bancada fixa **uma** correspondência e um renderizador:

| Estado do portão | Tom | Glifo | Palavra |
|---|---|---|---|
| `PERMITIDO` | `success` | check | permitido |
| `BLOQUEADO` | `destructive` | cadeado | bloqueado |
| `INDETERMINADO` | `warning` | interrogação em círculo | não se sabe |
| `NAO_APLICAVEL` | neutro | traço | não se aplica |

E a regra inegociável de `src/lib/trafego/portoes.ts:112-116`: **só `PRONTO`/`PERMITIDO` pinta positivo.** `PARCIAL` e `INDETERMINADO` são amarelos de "não sei", não degraus para o verde.

### 5.1 Onde a aurora pode aparecer nesta superfície — lista exaustiva

1. `aurora-rule w-16` sob o H1 da página (contrato de identidade, `design.md:85`).
2. Um segmento de **3px** marcando a parada atual no mapa — aurora marcando **posição**, que é identidade, não estado.
3. `hairline-aurora` de 1px no topo do cartão de **Recibo**, uma vez, quando a campanha passa a existir.
4. A tela de **Ignição**, que é a exceção documentada e contida (`index.css:925-978`).

Fora destes quatro: proibida. Nada de aurora atrás de tabela, de número, de aviso, de barra de progresso ou de fundo de parada.

---

## 6. Os três gestos que fazem isto parecer feito, não gerado

O "WOW" não vem de mais efeito. Vem de três decisões de composição que nenhum dashboard genérico toma.

### 6.1 A calha de evidência
Cada bloco de decisão tem uma calha esquerda de **24px** que carrega só duas coisas: o glifo de estado e, quando o valor é medido, um tique de frescor. O texto começa sempre na mesma coluna. O efeito é um ritmo vertical de instrumento — e um lugar fixo para o olho conferir "isto foi medido?" sem ler.

### 6.2 O marcador de parada
O mapa não usa pílula nem sublinhado. A parada atual recebe um segmento aurora de 3px e a coluna de decisão recebe um hairline aurora de 1px na borda esquerda, **apenas enquanto aquela parada está aberta**. Quando a parada muda, o segmento desliza (`transform: translateX`, 200ms) e o hairline troca. É o único elemento da tela que se move sozinho, e ele diz exatamente uma coisa: onde você está.

### 6.3 A revelação do recibo
Quando a criação fecha com sucesso, o cartão de recibo entra com **`opacity` + `scale(.98→1)`**, a **220ms** — o teto do contrato de movimento. ⚠️ **Correção:** a redação anterior especificava máscara radial a 400ms; `design.md:108-122` fixa 150–220ms e não lista `mask-image` entre as propriedades animáveis, e esta spec não se autoconcede exceção à autoridade raiz. A máscara fica como proposta de emenda (`DECISION-LOG.md §8 Q14`). Sob `prefers-reduced-motion`, fade de 150ms. Acontece **uma vez por campanha criada**, e é o único momento em que o produto comemora — porque é o único momento em que algo passou a existir na conta.

Nada além destes três. Sem brilho em controle, sem gradiente em texto, sem pulsação, sem cursor decorativo, sem partícula.

---

## 7. Divergências entre `design.md` e o código — a tabela que o executor deve consultar

Os valores semânticos no código foram escurecidos por medição de contraste, com a justificativa inline. **Vale o código.**

| Token | `design.md` front-matter | Implementado | Linha |
|---|---|---|---|
| `success` | `#168B68` | `#116E52` | `index.css:66` |
| `warning` | `#D9850B` | `#885407` | `:68` |
| `verified` | `#009FC7` | `#006A85` | `:80` |
| `destructive` | `#C83D3D` | `#B33232` | `:85` |
| `ink-muted-light` | `#68717D` | `#5D656F` | `:47` |
| kicker tracking | `0.1em` (`design.md:84`) | `0.16em` | `:398-405` |
| pílula de aba selecionada | `bg-background` (`design.md:193,201`) | `bg-card` (`design.md:96` + código) | `ui/tabs.tsx:42` |
| raio de modal | `12px` (front-matter) | não tokenizado; escada 8/6/4 | `tailwind.config.ts:92-96` |

---

## 8. Anti-referências desta superfície

Recusar por correspondência, sem discussão:

- Dashboard genérico com faixa de KPIs grandes no topo (`PRODUCT.md:21`).
- Grade de cartões idênticos para termos, canais ou campanhas.
- Cartão elevado dentro de cartão elevado.
- Faixa colorida lateral maior que 1px.
- Texto com gradiente ou contorno fora dos quatro marcos de identidade.
- Glassmorphism ou blur em cromo de trabalho.
- Brilho (`shadow-glow`) em qualquer controle operacional.
- Sombra colorida ou brilho em métrica.
- Barra de progresso animando `width`.
- `transition: all` / `transition-all`.
- Uppercase fora do `.kicker`.
- Emoji como ícone de estado.
- Toast celebratório para ação cujo efeito está visível.
- "Ops!", exclamação em mensagem de sucesso, humor em erro.
- Número sem frescor; ausência desenhada como zero; lista vazia desenhada como "tudo certo".
