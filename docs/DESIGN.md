---
name: VOLC O.S.
description: Ponteiro. A autoridade de UI de produto é design.md na raiz.
colors:
  canvas-light: "#F3F5F7"
  surface-light: "#FAFBFC"
  ink-light: "#1A1C1E"
  ink-muted-light: "#68717D"
  border-light: "#D8DEE6"
  primary: "#0D47A1"
  success: "#168B68"
  warning: "#D9850B"
  destructive: "#C83D3D"
  aurora-blue: "#00D4FF"
  aurora-purple: "#8A2BE2"
  aurora-orange: "#FF3D00"
typography:
  display: "Space Grotesk"
  body: "Inter"
---

# Este arquivo não governa a UI

A autoridade do produto é **`design.md` na raiz do repositório**. O loader do
Impeccable acha `PRODUCT.md` na raiz e, portanto, carrega `design.md` da raiz,
não este arquivo.

Se este texto divergir da raiz, **a raiz vence**. Não implemente a partir daqui.
Não restaure "aurora fora do workspace", abas sublinhadas, cartão branco sem
sombra, nem `transition: all`.

O restante desta página existe só para quem ainda faz grep em `docs/DESIGN.md`
e precisa das receitas certas, não das regras antigas que desfaziam o visual.

## Contrato para agentes (leia antes de tocar `src/`)

Registro **product**. Cena: operador às 14h, monitor 27", perto da janela.
Claro é o padrão. Familiaridade é vantagem. Não importe energia de landing page.

### Identidade de página (obrigatória)

1. Kicker 11px caixa-alta + chip 20×20 (`bg-primary/10 text-primary`).
2. H1 Space Grotesk 32–40px, tinta. Salas de identidade podem colorir a
   **segunda** palavra com `text-aurora`: QG (`Operacional`), Pautador (`Pro`),
   Redator (`Editorial`). Em nenhum outro lugar — nunca o título da campanha em
   `/redator/funil/:id`, nunca o Estúdio.
3. `aurora-rule w-16` imediatamente sob o H1.
4. Uma frase de propósito em `text-muted-foreground text-pretty`.
5. No máximo um botão primário no header.
6. Orçamento 220–280px no desktop.

Estúdio Criativo: o código em `src/components/criativos` e `src/pages/criativos`
não pode conter `text-aurora`, `aurora-blue`, `aurora-purple`, `aurora-orange`
nem `gradient-aurora`. O título permanece **Estúdio Criativo** em tinta.
`aurora-rule` é permitido.

### Superfícies, abas, chips, inventário

- Canvas `#F3F5F7` e card `#FAFBFC` são quase a mesma tinta. Superfície de
  trabalho usa `bg-card` + `border-border` + `shadow-card`.
- Abas segmentadas num poço **sólido** `rounded-lg border bg-muted p-1`
  (não `/60` — o poço some no canvas). Selecionada: `bg-card shadow-card`.
  Nunca `bg-background` no pílula: esse token é o canvas. Nunca sublinhado.
- Chip: glifo + palavra + descrição. Palavra em `text-foreground` (ou token
  semântico), nunca muted-sobre-muted.
- Inventário é **tabela**, não grade de cartões.
- Estado no cartão: hairline de 2px no **topo**. Nunca faixa lateral >1px.
- Cartão dentro de cartão é sempre erro.

### Aurora e motion

Aurora é marco de identidade (shell, `aurora-rule`, segunda palavra do H1 do
QG / Pautador Pro / Redator, login). Nunca cor de estado operacional, fundo de
tabela, preenchimento de progresso ou alerta. Salas ocasionais (QG, Pautador,
Redator, Login) podem usar `.reveal`.

Motion de produto: 150–220ms, `cubic-bezier(0.22, 1, 0.36, 1)`, propriedades
nomeadas (nunca `transition: all`), `scale(0.96)` no press, hover-lift só em
`@media (hover: hover) and (pointer: fine)`, sem stagger de load no Hub
`/trafego`, respeitar `prefers-reduced-motion`. Não coreografar setas do teclado.

Receita completa, tokens e bans: `design.md` na raiz.
