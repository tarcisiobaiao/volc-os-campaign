---
colors:
  canvas-light: "#F3F5F7"
  surface-light: "#FAFBFC"
  surface-subtle-light: "#EEF2F6"
  ink-light: "#1A1C1E"
  ink-muted-light: "#68717D"
  border-light: "#D8DEE6"
  canvas-dark: "#0C111B"
  surface-dark: "#111827"
  surface-subtle-dark: "#172033"
  ink-dark: "#F3F6FA"
  ink-muted-dark: "#9CA8B8"
  border-dark: "#263244"
  primary: "#0D47A1"
  primary-hover: "#0A397F"
  verified: "#009FC7"
  success: "#168B68"
  warning: "#D9850B"
  destructive: "#C83D3D"
  aurora-blue: "#00D4FF"
  aurora-purple: "#8A2BE2"
  aurora-orange: "#FF3D00"
typography:
  display: "Space Grotesk"
  body: "Inter"
  data: "Inter"
  base-size: "16px"
  base-line-height: "1.5"
rounded:
  control: "6px"
  panel: "8px"
  modal: "12px"
spacing:
  unit: "4px"
  scale: [4, 8, 12, 16, 24, 32, 48]
components:
  button-primary:
    background: "#0D47A1"
    foreground: "#F8FAFC"
    border: "#0D47A1"
    radius: "6px"
    height: "40px"
  button-secondary:
    background: "transparent"
    foreground: "#1A1C1E"
    border: "#C8D0DA"
    radius: "6px"
    height: "40px"
  input:
    background: "#FAFBFC"
    foreground: "#1A1C1E"
    border: "#C8D0DA"
    radius: "6px"
    height: "40px"
  state-chip:
    radius: "999px"
    height: "24px"
  campaign-row:
    background: "#FAFBFC"
    border: "#D8DEE6"
    radius: "0px"
---

## Agent contract (read this first)

If you are about to change any file under `src/`, `src/pages/`, `src/components/` or `src/index.css`, this file is the only product-UI authority. Stop and copy the recipes below. Do not invent a third visual language.

**Where to read**

| File | Role |
|---|---|
| `design.md` (repository root) | **This file.** Impeccable / Cursor load it with `PRODUCT.md`. |
| `docs/DESIGN.md` | Pointer plus the same recipes in Portuguese. If it diverges, **this file wins**. |
| `docs/design/DESIGN-SYSTEM.md` | Branded presentations, login, external decks. Never copy into Hub, QG, Pautador, Estúdio or campaign inventory. |
| `PRODUCT.md` | Register (`product`), users, bans. Not a component recipe. |

**Register.** Product. Design serves the task. An operator at 14:00 on a 27-inch monitor by a window is the scene. Light is the default. Familiarity is a feature. Do not import landing-page energy, orchestrated page-load choreography, or presentation-scale type into the workspace.

### Mandatory page identity

Every new or touched operational page header follows this exact stack, in this order:

1. **Kicker** — uppercase 11px, letter-spacing `0.1em`, plus a 20×20 icon chip (`rounded-md bg-primary/10 text-primary`, icon `h-3.5 w-3.5`).
2. **H1** — Space Grotesk, 32–40px, `font-bold tracking-tight leading-[1.05]`, ink (`text-foreground`). Identity rooms may color the **second** H1 word with `text-aurora`: QG (`Operacional`), Pautador (`Pro`), Redator (`Editorial`). Nowhere else — never the campaign title on `/redator/funil/:id`, never Estúdio.
3. **`aurora-rule w-16`** — the 3px identity hairline, immediately under the H1. This is a landmark, not a status color.
4. **Purpose** — one sentence, `text-sm text-muted-foreground text-pretty`, `max-w-3xl` or `70ch`.
5. **At most one primary button** in the header region.
6. **Budget** — 220–280px on desktop so the first operational row is visible without scrolling.

Estúdio Criativo (`src/components/criativos/**`, `src/pages/criativos/**`): never write `text-aurora`, `aurora-blue`, `aurora-purple`, `aurora-orange` or `gradient-aurora` in non-comment source. A test fails the build if you do. The title stays the single ink string **Estúdio Criativo**. The class `aurora-rule` is allowed.

### Surfaces, tabs, chips, inventory

- **Canvas vs card.** `--background` `#F3F5F7` and `--card` `#FAFBFC` are almost the same ink. A work surface that must separate from the canvas uses `bg-card` + `border-border` + `shadow-card`. A flat `bg-card` on the canvas is invisible. Do not “fix” this by painting aurora behind the workspace.
- **Segmented tabs**, not underlines. Well: `rounded-lg border border-border bg-muted p-1` (solid muted — not `/60`, or the well disappears into the canvas). Selected: `bg-card text-foreground shadow-card`. Never `bg-background` for the selected pill: that token *is* the canvas (`#F3F5F7`), so the pill and the page become the same grey. Inactive: `text-muted-foreground`. Never recreate a third tab style (underline, contained pills outside the well, equal-weight bars).
- **Chips.** Glyph + word + optional description. The word uses `text-foreground` or the semantic token (`text-success`, `text-warning`, …), never muted-on-muted. Neutral chips: `bg-muted/50 text-foreground`.
- **Inventory is a table.** Comparable campaigns, tasks or rows are never a grid of identical cards. Account groups are a tinted header row, not a second elevated card.
- **Status on a card** (QG tasks, workbook): a **2px top hairline** in the semantic color. Never a left/right stripe thicker than 1px.
- **Nested cards are always wrong.** Inside a `bg-card` surface, nest hairlines and `bg-muted/20` wells, not another `shadow-card`.

### Aurora, color, type

- Aurora (`#00D4FF / #8A2BE2 / #FF3D00`) is an identity signature: shell edge, `aurora-rule`, the second H1 word on QG / Pautador Pro / Redator, login. It is **never** an operational status, a table background, a warning, a progress fill, or a metric color.
- Semantic vocabulary is closed: `primary` `#0D47A1`, `verified`, `success` `#168B68`, `warning` `#D9850B`, `destructive` `#C83D3D`, `info`. Color is never the only carrier of meaning.
- Two families only: **Space Grotesk** (titles, kickers) and **Inter** (everything else). No third family. No `clamp()` on product headings. Tabular numerals on any number that updates or compares.

### Motion (product, MOTION ~3)

Purpose is feedback, orientation or continuity. Not decoration.

| Token | Value |
|---|---|
| Duration | 150–220ms (press 100–160ms) |
| Enter curve | `cubic-bezier(0.22, 1, 0.36, 1)` |
| Properties | Name them. Never `transition: all` / `transition-all`. |
| Press | `scale(0.96)` on buttons. Not below `0.95`. |
| Hover lift | `translateY(-2px)` and only inside `@media (hover: hover) and (pointer: fine)`. |
| Reduced motion | `prefers-reduced-motion: reduce` disables non-essential motion. |
| Page load | No stagger on high-frequency surfaces (`/trafego` Hub). Occasional rooms (QG, Pautador, Redator, Login) may use `.reveal`. |
| Keyboard | Do not choreograph arrow/tab navigation. Color/shadow ≤160ms is the ceiling. |
| Animate | `transform` and `opacity`; color/background for selected state. Never `width`, `height`, `top`, `left`. |

Live metrics, warning color and spend actions must not pulse or bounce.

### Hard bans (match and refuse)

- Nested elevated cards; identical card grids for comparable inventory.
- Underline tabs; a second tab vocabulary on the same product.
- Left/right color stripes `>1px`; gradient text (except the second identity word on QG, Pautador Pro and Redator); decorative glassmorphism; glow on operational controls.
- Fake KPI heroes; invented zeros; numbers without freshness.
- `transition: all`; hover-lift on touch pointers; page-load theatre on Hub.
- Copying `docs/design/DESIGN-SYSTEM.md` into the workspace.
- Treating `docs/DESIGN.md` as a second spec that can override this file.

Copy Pautador Pro (`/pautador-pro`), QG (`/settings/qg-agentico`) and Hub (`/trafego`) when in doubt. They already implement this contract.

## Overview

VOLC O.S. is an operational mission control for attention, media and arbitrage. Its interface exists to help an operator understand what is happening, what is known, what remains uncertain and what decision is safe to take next. It is a product workspace, not a marketing page and not a decorative dashboard.

The reference scene is an operator at 14:00 on a 27-inch monitor beside a window, checking live media before authorizing spend. Light mode is the default for this scene. Dark mode is complete and equivalent, not a reduced alternate skin.

The visual direction is **VOLC Mission Control**: restrained, dense, calm and unmistakably VOLC. It combines the operational hierarchy of Linear, the clarity and trust of Stripe Dashboard, the domain familiarity of Google Ads and the VOLC signature. Brand energy appears at identity landmarks. Operational workspaces remain quiet.

The interface follows five named rules:

1. **Truth Before Decoration.** Every number exposes freshness and provenance. Absence, failure, stale data and measured zero are different states.
2. **One Dominant Signal.** Each row, panel and step has one primary status or next action. Supporting facts never compete with it.
3. **Identity at the Edge.** The VOLC aurora belongs to shell landmarks, activation moments and identity surfaces. It never becomes a workspace background or an operational status color.
4. **Density With Air.** Comparable information stays compact and aligned. Whitespace separates decisions, not every field.
5. **Consequences Before Actions.** Any action that writes, publishes, changes delivery or can spend money explains scope, consequence, reversibility and approval before it becomes available.

The product hierarchy is always: context, task, filters, workspace, deep detail. A page header must normally fit within 220 to 280 pixels on desktop so the first operational content remains visible without scrolling.

`docs/design/DESIGN-SYSTEM.md` is a sibling reference for branded presentations. It is not the product UI authority. Presentation-scale typography, full-canvas auroras, noise and theatrical composition must not be copied into the operational workspace.

## Colors

The palette uses cool tinted neutrals for approximately ninety percent of the interface. Pure white and absolute black are avoided in the product workspace. `canvas-light` and `canvas-dark` establish the page; `surface-light` and `surface-dark` establish working surfaces; subtle surfaces separate filters, selected rows and secondary regions without creating nested cards.

`primary` is the only default action color. Use it for selected task navigation, the single primary button in a region and links that move the operator forward. `verified` means a source was observed or reconciled. It does not mean success. `success` means a healthy completed state. `warning` means pending attention or a decision that deserves care. `destructive` is reserved for true errors, blocked states and irreversible or high-risk actions.

Operational states must never reuse `aurora-blue`, `aurora-purple` or `aurora-orange`. The aurora trio is a brand signature only. It may appear as a two-pixel shell accent, a focused identity mark, a contained activation surface or a short transition between major product modes. Never place aurora gradients behind tables, forms, metrics, warnings or long reading surfaces.

Color is never the sole carrier of meaning. Every state combines a glyph, a plain-language label and, when necessary, one short explanation. Light and dark themes preserve semantic contrast and hierarchy rather than merely inverting values.

## Typography

Use **Space Grotesk** for page titles, short section titles and a small number of identity landmarks. Use **Inter** for body text, controls, tables, forms, labels and data. Do not introduce a third family.

Page titles use Space Grotesk at 32 to 40 pixels, weight 600 or 650, with tight but readable line height. Section titles use 18 to 24 pixels. Operational body text uses Inter at 14 to 16 pixels. Dense table content may use 13 to 14 pixels, but essential actions and explanatory text never drop below 14 pixels.

Metadata labels may use uppercase Inter or Space Grotesk at 11 to 12 pixels, weight 600, with restrained letter spacing. Uppercase is a navigation aid, not a decorative texture. Do not uppercase paragraphs, actions or status explanations.

Numeric columns use tabular figures and right alignment when comparison matters. Campaign names, destinations and operator-facing explanations remain sentence case and left aligned. Truncation must preserve access to the full value through expansion or an accessible title. Never truncate the primary identity while repeating secondary tags in full.

## Elevation

Elevation communicates ownership and temporary layering, not importance. Most workspace separation uses borders, tinted surfaces and spacing.

The Traffic Hub keeps four distinguishable planes:

1. **Canvas** — the page background (`canvas-light` / `canvas-dark`).
2. **Work surface** — the inventory table, the Create bench, QG scorecards, Estúdio `Secao`. These use `shadow-card` so they separate from the canvas. They are not nested card stacks.
3. **Account group** — a muted tint on the account header, typographically larger than a campaign row, never a second elevated card.
4. **Interactive / selected row** — background tint and an inset primary accent. Rows never float. Frequent keyboard and table navigation is not animated.

Use no shadow for filters, chips and unselected rows. Use a restrained structural shadow for sticky toolbars when they overlap content. Use a medium shadow for popovers and menus. Use the strongest product shadow only for modals that block interaction and require a decision.

Do not stack elevated cards inside elevated cards. Do not add glow to operational controls, metrics or alerts. Selected state is expressed through background tint, border and focus, never by floating the element toward the operator.

**Task tabs** (Campaigns / Prepare / Create / Attention, and QG Agora / Timeline / …) are a segmented control in a muted well. Selected state is a white (`bg-background`) pill with `shadow-card`. Do not use underline tabs.

## Components

**Application shell.** The shell provides identity, primary navigation, account context and global attention. It may carry a restrained VOLC signature at its edge. It must not compete with the current task.

**Page header.** Keep the title, one-sentence purpose, freshness summary and one primary global action within the first desktop viewport. Network, channel and task are not three equal navigation bars: network defines context, task defines the job and channel narrows the inventory.

**Task tabs.** Campaigns, Prepare, Create and Attention (and QG view tabs) are a segmented control in a muted well. Selected pill: `bg-background shadow-card`. Counts are quiet metadata and never replace the task label. Never underline tabs.

**Channel selector.** Channel is a compact filter within the selected network. Canonical Google Ads values are Search, Display, Demand Gen, Performance Max, Video and Shopping. Do not make an unavailable channel look implemented. State capability honestly.

**Filters.** Search and high-frequency filters remain visible and may become sticky with table headers. Advanced filters collapse into one secondary control. Every active filter is removable and the result count states both the visible subset and the universe.

**Account group.** An account header is compact and sticky within long inventories. It shows account identity, freshness, campaign count and the read-only refresh action. It does not create a large empty banner.

**Campaign row.** Use a dense, aligned master row with one primary identity line and one muted metadata line. The row exposes status, campaign, channel, strategy, bid, daily budget, delivery, cost and freshness in a comparable grid. Provenance, reconciliation and linkage become one compact evidence cluster, not repeated colored tags. Active or attention-worthy rows precede history through server authority. Removed history is hidden by default.

**Inline detail.** Expansion answers the immediate question without turning into another dashboard. It shows full identity, external and internal IDs, source, freshness, funnel linkage, reservations and the next safe action. Complex diagnosis and management move to the canonical campaign page.

**Canonical campaign page.** The page follows this order: breadcrumb and identity; delivery and freshness; observed evidence; diagnosis; funnel and lineage; channel-specific structure; history and receipts; action rail. Search, Display, Demand Gen, Performance Max, Video, Shopping and Meta may expose different manifests. Missing capabilities remain explicit and never become fabricated zero values.

**Create studio.** Creation is a channel-specific operational bench, not a generic seven-step form. Search, Display, Demand Gen, Performance Max, Shopping and Video each have their own journey, derived from a typed registry crossed with the backend manifesto, the operator permission and the write lock. Search opens the real cockpit. Video is observe-and-analyze only: the Google Ads API does not create or update Video campaigns. A planned channel shows the next unlock, never a fake form. A disabled or missing action explains the missing prerequisite.

**Attention queue.** Attention groups conditions by operator decision, not by implementation source. Each item states what was observed, why it matters, confidence, freshness and the next safe action. A stale account condition and a campaign delivery condition remain distinct even when shown together.

**Buttons.** Each region has at most one primary button. Secondary and tertiary controls are visually quieter. Destructive controls are isolated and always confirm scope. Button labels use verbs and name the result.

**State chips.** Chips are compact semantic labels, not decoration. One dominant chip is normally enough. When multiple facts matter, render a sentence or evidence cluster instead of a pile of badges.

**Forms.** Labels remain visible. Helper text is concise and appears before an error when it prevents one. Validation occurs at the field and at the workflow boundary. Never rely on placeholder text as a label.

**Empty, loading and failure states.** An empty result after filtering is different from an empty source. Loading preserves layout. A failed read does not erase the last good data without explaining its age. Technical stack traces, database vocabulary and raw API errors do not appear in the operator interface.

## Do's and Don'ts

### Do

- Start every screen from the operator's decision, then reveal implementation detail only when it supports that decision.
- Keep the first operational rows visible in the initial desktop viewport.
- Preserve real data, source, freshness, uncertainty and receipts throughout the UI.
- Hide removed history by default and make its count and disclosure explicit.
- Keep comparable metrics aligned in a dense grid with sticky context on long lists.
- Use one dominant state and one dominant action per region.
- Explain why an action is unavailable and what prerequisite is missing.
- Make light and dark themes equivalent and test both with real content.
- Provide visible keyboard focus, semantic names, logical tab order and reduced motion.
- Use the VOLC aurora sparingly enough that it still feels like a signature.

### Don't

- Do not use nested cards to represent every field or state.
- Do not use colored side stripes thicker than 1px, gradient text (except the QG identity word), glassmorphism or decorative glow in the workspace.
- Do not repeat piles of tags when a single evidence sentence is clearer.
- Do not present a number without freshness or turn absence into zero.
- Do not equate observed, linked, healthy and successful. They are different facts.
- Do not expose PostgREST, GAQL, SQL, internal table names, environment flags or stack traces to the operator.
- Do not make spend, publish, pause, budget, bid or duplication actions feel trivial.
- Do not redesign backend contracts to make a layout easier.
- Do not allow a huge header, empty account banner or expansion panel to push the actual work below the fold.
- Do not copy the presentation design system wholesale into the product UI.
