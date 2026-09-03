# MOTION-AND-INTERACTION — gramática de movimento, microinterações, teclado e foco

Autoridade: `design.md:108-124`. Este arquivo é a especificação executável daquele contrato para a Bancada Guiada, a Ignição e o Recibo.

> ⚠️ **Correção de contagem:** `transition-all` / `transition: all` têm **zero ocorrências reais** em todo o `src/` — os dois matches são um comentário e uma regex de teste. O item 1 de `§8` já está satisfeito, e é um **invariante a preservar**, não um defeito a corrigir.

**A regra que governa o arquivo inteiro:** movimento comunica estado, orientação ou continuidade. Se você não consegue dizer numa frase o que uma transição informa, ela não existe.

---

## 1. Tokens

Já implementados; a Bancada usa estes e não cria outros.

```css
/* curvas */
--ease-entrada:  cubic-bezier(0.22, 1, 0.36, 1);   /* a curva da casa, index.css:284-287 */
--ease-saida:    cubic-bezier(0.7,  0, 0.84, 0);
--ease-troca:    cubic-bezier(0.65, 0, 0.35, 1);

/* durações */
--dur-press:     120ms   /* pressão de botão */
--dur-estado:    180ms   /* hover, foco, cor de estado, troca de glifo */
--dur-parada:    200ms   /* troca de parada, deslize do marcador */
--dur-camada:    220ms   /* overlay entra */
--dur-saida:     165ms   /* overlay sai — 75% da entrada */
--dur-recibo:    220ms   /* revelação do recibo — no teto do contrato, não acima dele */
```

Saídas são **75%** da entrada. Nenhuma duração operacional passa de 220ms.

**Propriedades animáveis nesta superfície:** `transform`, `opacity`, `background-color` (estado selecionado e o traço "isto mudou").

⚠️ **`mask-image` é a única propriedade fora da lista de `design.md:122`, e ela NÃO é adotada por conta própria.** A revelação do recibo usa **`opacity` + `transform: scale`** dentro dos 220ms do contrato. A máscara radial fica como **proposta de emenda** a `design.md`, com dono nomeado em `DECISION-LOG.md §8 Q14` — porque a autoridade raiz "vence qualquer divergência", e uma spec de execução não pode se autoconceder exceção a ela.
**Proibidas:** `width`, `height`, `top`, `left`, `margin`, `padding`, `filter`, e `transition: all` / `transition-all` em qualquer forma.

---

## 2. A gramática

| Evento | O que se move | Duração / curva | Reduced motion |
|---|---|---|---|
| **Entrada da página** | nada encenado. O conteúdo está lá. | — | — |
| **Avanço de parada** | conteúdo sai `opacity 1→0` (80ms, `--ease-saida`); entra `opacity 0→1` + `translateY(6px→0)` (160ms, `--ease-entrada`, 40ms de atraso). Altura **nunca** anima. | 200ms total | crossfade 120ms, sem `translateY` |
| **Retorno de parada** | idêntico, `translateY(-6px→0)` — a direção diz que se voltou | 200ms | idem |
| **Marcador do mapa** | o segmento aurora desliza `transform: translateX` até a parada atual | 200ms `--ease-entrada` | salta sem transição |
| **Validação de campo** | cor da borda + glifo entra `scale(.25→1)` + `opacity` | 180ms `--ease-entrada` | glifo aparece instantâneo |
| **Bloqueio** | **nada.** O bloqueio aparece no primeiro quadro. | 0ms | 0ms |
| **Erro** | **nada.** Aparece pronto, com `role="alert"`. | 0ms | 0ms |
| **Sucesso** | **silêncio.** A mudança de estado é o retorno. Sem toast, sem check comemorativo. | — | — |
| **Atualização de evidência** | o valor faz crossfade (150ms `opacity`); o carimbo de frescor troca junto. `tabular-nums` impede reflow. | 150ms | igual (é opacidade) |
| **Alteração do resumo** | a linha alterada no Pedido recebe `background-color` tingido que desvanece em 1200ms. **Sem movimento, sem salto.** | 1200ms linear | traço estático de 1200ms, sem transição |
| **Prova em curso** | o degrau `prova` mostra spinner funcional + cronômetro real em segundos | contínuo | spinner desacelera, não para |
| **Criação pausada** | o degrau `escrita` resolve: glifo troca `scale(.25→1)`; o horizonte sobe de `--avanco: .85` para `1` | 200ms / 400ms | `--avanco` salta |
| **Revelação do recibo** | `opacity` 0→1 + `scale(.98→1)` a partir do cartão | 220ms `--ease-entrada` | fade 150ms, sem `scale` |
| **Overlay (ignição, gaveta, folha)** | `opacity` + `scale(.98→1)`; backdrop `opacity` | 220ms entra / 165ms sai | `opacity` 150ms, sem `scale` |

### 2.1 O que nunca acontece

1. **Nenhuma fase fictícia.** `POST /provar` é **uma** requisição sem subfases observáveis (`MOTION-MAP.md@85666da:27-34`, **blob de `85666da`** — a pasta não existe nesta base; confirmado aqui por `grep -rn 'subfase' backend/ src/` → 0). A escada mostra os quatro atos que existem — destino (nenhuma chamada), copy (já feita), prova (uma chamada), escrita (uma chamada) — e um cronômetro real. Nada avança porque o tempo passou.
2. **Nenhuma barra determinada sem denominador real.** Se o total é desconhecido, não há barra: há um contador do que já foi lido.
3. **Nenhum `.reveal` em `/trafego/nova`.** Ele sai do cockpit e da ignição (hoje em `NovaCampanhaPage.tsx:493,522,548,684,696,703,875` e `Lancamento.tsx:693`).
4. **Nenhum hover-lift em painel estático.** `.card-volc` não é usado na Bancada.
5. **Nenhuma pulsação, brilho ou laço infinito** — exceto o spinner funcional e o horizonte da ignição, que respira apenas enquanto uma chamada real está aberta.
6. **Nada anima em navegação por teclado ou por tabela.** Cor e sombra até 160ms é o teto (`design.md:122`).

### 2.2 Uma exceção deliberada ao catálogo de microinterações

A receita corrente de troca contextual de ícone pede `scale 0.25→1` + `opacity` + `blur 4px→0`. **O `blur` não é adotado.** `design.md:122` nomeia as propriedades animáveis e `filter` não está entre elas; a mesma decisão remove `@keyframes di-reveal` de `laboratorio/bancada.css:113-120`, que hoje anima `filter: blur(4px)`. A troca de ícone usa `scale` + `opacity`, com os dois ícones no DOM (um absoluto) fazendo crossfade — o que também dá saída, não só entrada.

---

## 3. Microinterações por controle crítico

Formato: gatilho → o que muda → duração/curva → acessibilidade.

**Botão primário** (`Confirmar e seguir`, `Provar contra a conta`, `Criar campanha pausada`)
Hover → `background-color` (180ms) e, só em `@media (hover:hover) and (pointer:fine)`, `translateY(-1px)`. Press → `scale(0.96)` (120ms) — exatamente 0.96, nunca abaixo de 0.95. Loading → o rótulo é substituído por rótulo + spinner no mesmo botão, largura reservada. Foco → anel instantâneo, **nunca** transicionado.

**Ação desabilitada**
Nunca desabilita em silêncio. `disabled` + `aria-disabled` + um parágrafo adjacente com a razão, ligado por `aria-describedby`. O modelo já existe: `src/components/trafego/lote/QuadroDoLote.tsx:305-335`. O contra-modelo a corrigir: `NovaCampanhaPage.tsx:461-479`, onde a razão só aparece de `sm:` para cima.

**Caixa de marcação de termo** (mesa de Termos)
Clique → o estado local muda no mesmo quadro (otimista **local**: nada sai para a rede). O Pedido atualiza a contagem e a linha alterada recebe o traço de 1200ms. Alvo de toque ≥40×40px estendido por pseudo-elemento; sem sobreposição entre alvos vizinhos.

**Seletor de correspondência por termo**
`Select` nativo estilizado no invólucro; abre com o Popover do sistema. Trocar não move a linha nem reordena a mesa.

**Campo numérico** (lance, orçamento, graduação)
Altura idêntica à do botão (44px mobile / 40px desktop). Borda **1px em todos os estados** — foco usa `outline`, nunca `border-width`, para não deslocar layout. Validação **no blur**, revalidação a cada mudança depois do primeiro blur. A ajuda tem altura reservada de uma linha para que o erro não empurre a página. O valor formatado nunca é reescrito enquanto o campo tem foco.

**Escolha de nascimento** (CPC manual × Maximizar conversões)
Cartão inteiro clicável, `aria-pressed`; alvo é o cartão, não o rádio de 12px — já correto em `MesaDeLance.tsx:246-254`. Trocar reescreve, na mesma tela e sem animação, o que decorre da escolha (correspondência, teto, graduação).

**Divulgação progressiva** (evidência do bloco, observações, avançados)
`<details>`/`<summary>` ou botão com `aria-expanded` + `aria-controls`. **Nunca modal.** Abrir não anima altura: o conteúdo aparece com `opacity` 150ms.

**Tooltip**
Hover 800ms de atraso; **foco 0ms**. Deve ser sobrevoável, persistente e dispensável por `Esc` (WCAG 1.4.13). Nunca carrega informação que decide — se decide, é texto na tela.

**Spinner**
Atraso de 150ms antes de aparecer; mínimo de 300ms visível uma vez aparecido. Onde a forma do conteúdo é conhecida, esqueleto em vez de spinner. O esqueleto preserva o layout final.

**Toast**
Só para **falha** e para efeito que o operador não vê. Nunca para sucesso visível. Empilha num canto fixo; toast novo não empurra conteúdo nem move os existentes.

**Confirmação**
Reservada ao ato irreversível. A criação pausada mantém as duas travas atuais e elas são corretas: motivo com no mínimo 10 caracteres, que vai para o recibo, e a caixa "autorizo somente a criação PAUSADA" (`Lancamento.tsx:540-565`). As duas condições ficam escritas ao lado do botão, não só implícitas no `disabled`.

---

## 4. Os oito estados de todo elemento interativo

Nenhum componente da Bancada entra em produção com menos de oito.

| Estado | Tratamento | Regra |
|---|---|---|
| Padrão | base | — |
| Hover | deslocamento sutil de cor; lift só em ponteiro fino | dentro de `@media (hover:hover) and (pointer:fine)` |
| Foco | `outline: 2px solid hsl(var(--ring)/.7)`, `outline-offset: 2px` | `:focus-visible`, **instantâneo**, ≥3:1 |
| Ativo | `scale(0.96)` | 120ms |
| Desabilitado | opacidade reduzida + cursor + `aria-disabled` + **razão adjacente** | nunca sozinho |
| Carregando | rótulo trocado + spinner no lugar, largura reservada, `aria-busy` | não bloqueia o campo |
| Erro | borda semântica + glifo + mensagem abaixo + `aria-invalid` + `aria-describedby` | nunca só cor |
| Sucesso | mudança de estado do próprio objeto | sem celebração |

Regra de geometria: **a espessura da borda é constante em todos os estados.** O anel de foco nasce como `outline: 2px solid transparent` para que ativá-lo não desloque nada.

---

## 5. Teclado e foco

**Ordem de tabulação da Bancada:** pular-para-conteúdo → shell → cabeçalho de identidade → mapa de paradas → coluna de decisão (na ordem visual) → ação primária da parada → Pedido → rodapé.

**Mapa de paradas.** É navegação, não aba: `<nav aria-label="paradas do lançamento">` com `<ol>`. Cada parada alcançável é um `<Link>`; a atual leva `aria-current="step"`. Parada **bloqueada não é botão desabilitado**: é um `<span>` com `aria-disabled="true"` e a causa ligada por `aria-describedby` — um link que não leva a lugar nenhum não deve parecer clicável.

**Troca de parada.** Ao entrar numa parada, o foco vai para o `<h2>` da pergunta (`tabIndex={-1}`), não para o primeiro campo — o operador precisa ler antes de digitar. Anúncio por `aria-live="polite"` de uma linha: "parada 3 de 6 — Termos".

**Ignição.** `role="dialog" aria-modal="true"`; foco entra no painel; o conteúdo de trás recebe `inert`; `Esc` fecha **exceto** durante `escrevendo` (já correto em `Lancamento.tsx:107,120-126`) e a tela diz por que não fecha. Ao fechar, o foco volta ao botão que abriu.

**Escada da ignição.** É `<ol>` com `aria-live="polite"` no contêiner; cada degrau resolvido anuncia nome + veredito, uma vez. Sem anúncio por segundo do cronômetro.

**Recibo.** Ao ser revelado, recebe foco programático e o anúncio "campanha criada, pausada". É uma região com `id="recibo"`, alcançável por link direto.

**Mesa de Termos.** Tabela real com `<caption>` em `sr-only`, `scope` nos cabeçalhos, cabeçalho fixo. Navegação por `Tab` entre controles; **sem** navegação por setas simulada — a tabela não é grade de aplicação. Marcar/desmarcar por `Espaço` no controle focado.

**Sem atalho global novo.** O caminho rápido é o mapa, a parada Revisão e a paleta de comandos existente (`src/components/CommandPalette.tsx`), que ganha as entradas "ir para revisão", "abrir o pedido" e "abrir a campanha criada". O produto não inventa um segundo vocabulário de teclas.

---

## 6. Detalhes de acabamento

- **Raios concêntricos:** `raio externo = raio interno + padding`. Superfície `rounded-lg` (8px) com `p-2` ⇒ filho `rounded-sm` (4px). Padding maior que 24px trata as camadas como superfícies independentes.
- **Alinhamento óptico:** botão com ícone à direita usa `pr` = `pl − 2px`. Glifo de play/seta recebe ajuste no próprio SVG, não margem no componente.
- **Numerais tabulares** em tudo que compara ou atualiza — já forçado em `th, td, [data-numeric], .tabular` (`index.css:369-372`).
- **`text-wrap: balance`** em título; **`text-pretty`** em explicação; medida 65–75ch.
- **`-webkit-font-smoothing: antialiased`** na raiz (já em `index.css:312-319`).
- **Alvo mínimo 40×40px** (44 no toque), estendido por pseudo-elemento quando o visível é menor; alvos vizinhos nunca se sobrepõem. A classe `.touch-target` já existe (`index.css:275-277`).
- **`will-change` só durante a animação**, e só em `transform`/`opacity`.
- **Transições são interrompíveis:** estados interativos usam `transition`, não `@keyframes`. Sequências de uma passada (revelação do recibo) usam `@keyframes`.

---

## 7. Movimento reduzido

`@media (prefers-reduced-motion: reduce)` — o produto já tem a regra universal em `index.css:567-604`, com a exceção `[data-motion="essencial"]`. A Bancada herda e especializa:

| Elemento | Comportamento reduzido |
|---|---|
| Troca de parada | crossfade 120ms, sem `translateY` |
| Marcador do mapa | salta, sem transição |
| Revelação do recibo | fade 150ms, sem máscara |
| Horizonte da ignição | fixo no `--avanco` do estado atual; sem respiração |
| Traço "isto mudou" no Pedido | tinta estática por 1200ms, sem transição |
| Spinner e barra indeterminada | **continuam**, desacelerados (`animate-spin` 1.4s) |
| Esqueleto | estático |
| Anel de foco | inalterado — nunca foi animado |

Regra: **movimento funcional sobrevive; movimento espacial vira opacidade.**

---

## 8. Contrato mecânico de verificação

Checável por varredura ou por captura; a lista executável está em `EXECUTOR-ACCEPTANCE.md`.

1. `transition-all` / `transition: all`: **0** ocorrências em `src/pages/trafego` e `src/components/trafego`.
2. Animação de `width`/`height`/`top`/`left`/`filter` nas superfícies desta spec: **0**.
3. `.reveal` em `/trafego/nova` e na ignição: **0**.
4. `card-volc` nas superfícies desta spec: **0**.
5. `backdrop-blur` em cromo operacional: **0**.
6. `text-[9px]`, `text-[10px]`, `text-[11px]`: **0** nas superfícies desta spec.
7. `border-l-2`/`border-r-2` colorida: **0**.
8. Todo `disabled` tem `aria-describedby` apontando para texto visível.
9. Toda transição declara propriedades nomeadas.
10. Toda animação com deslocamento espacial tem ramo em `prefers-reduced-motion`.
11. Nenhum anel de foco dentro de uma declaração de `transition`.
12. Captura em `prefers-reduced-motion: reduce` é legível e completa em todas as paradas.
