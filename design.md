---
colors:
  canvas-light: "#D4DBE3"
  surface-light: "#F4F7FA"
  surface-raised-light: "#FBFCFE"
  surface-subtle-light: "#C5CDD6"
  ink-light: "#13171E"
  ink-muted-light: "#3D4754"
  border-light: "#9AA6B4"
  canvas-dark: "#0D1218"
  surface-dark: "#171E28"
  surface-raised-dark: "#1E2733"
  surface-subtle-dark: "#121821"
  ink-dark: "#E8EEF4"
  ink-muted-dark: "#A8B4C2"
  border-dark: "#3A4656"
  primary: "#0D47A1"
  primary-hover: "#2A2F8F"
  primary-foreground: "#F7FAFF"
  verified: "#006A85"
  success: "#116E52"
  warning: "#885407"
  destructive: "#B33232"
  info: "#05697F"
  demo: "#6B4A1B"
  aurora-blue: "#00D4FF"
  aurora-purple: "#8A2BE2"
  aurora-orange: "#FF3D00"
typography:
  display: "Outfit"
  body: "IBM Plex Sans"
  data: "IBM Plex Mono"
  fallback: "ui-sans-serif, system-ui, sans-serif"
  base-size: "16px"
  base-line-height: "1.5"
rounded:
  control: "8px"
  panel: "10px"
  modal: "14px"
  pill: "999px"
spacing:
  unit: "4px"
  scale: [4, 8, 12, 16, 24, 32, 48]
motion:
  press: "140ms"
  menu: "200ms"
  sheet: "280ms"
  enter: "cubic-bezier(0.22, 1, 0.36, 1)"
  move: "cubic-bezier(0.25, 1, 0.5, 1)"
components:
  button-primary:
    background: "var(--gradient-aurora-action)"
    foreground: "#FFFFFF"
    radius: "8px"
    height: "40px"
  button-secondary:
    background: "var(--secondary)"
    foreground: "var(--secondary-foreground)"
    radius: "8px"
    height: "40px"
  input:
    background: "var(--card)"
    foreground: "var(--foreground)"
    border: "var(--input)"
    radius: "8px"
    height: "40px"
  state-chip:
    radius: "999px"
    height: "24px"
  campaign-row:
    background: "var(--card)"
    border: "var(--border)"
    radius: "0px"
---

## Agent contract (read this first)

If you are about to change any file under `src/`, this file is the only product-UI authority.
`PRODUCT.md` defines meaning and bans. This file defines tokens, components and visual QA.
Do not invent a third language. Do not copy `docs/design/DESIGN-SYSTEM.md` into the workspace.

**Where to read**

| File | Role |
|---|---|
| `design.md` (repository root) | **This file.** Visual authority. Wins any divergence. |
| `PRODUCT.md` | Product contract. Meaning, users, truth states, action types. |
| `docs/DESIGN.md` | Pointer. If it diverges, **this file wins**. |
| `.impeccable/design.json` | Machine mirror. Derived. Never a second spec. |
| `docs/design/DESIGN-SYSTEM.md` | Presentations and external decks. Never product UI. |

**Register.** Product. Control room editorial, not landing page.
Dials for this system: `DESIGN_VARIANCE: 5`, `MOTION_INTENSITY: 4`, `VISUAL_DENSITY: 7`.

VOLC OS is a bench for paid media and creation. The interface must look used every day: obvious actions, readable type, distinct surfaces, honest states.

## Authority and precedence

1. `PRODUCT.md` for meaning, security and data truth.
2. This file for tokens, type, density, motion and component recipes.
3. Implemented CSS variables in `src/index.css` for rendered values.
4. Tailwind maps those variables. Components consume tokens, never raw hex.
5. Historical notes in `docs/design/` are evidence, not current law.

The previous timid contract used Inter, Space Grotesk, near-white canvas and teal-as-action. That language is retired here on purpose. Navy returns only as the VOLC action axis (deep → purple), not as a flat institutional fill.

## Visual concept

**VOLC Control Room.** Mineral graphite canvas, paper-white sidebar, lifted work surfaces, dark readable ink. Primary acts use the VOLC navy→purple action gradient — the same axis as the word Pro in Pautador. Teal is not an action color.

Light mode has real planes: mineral canvas, off-white sidebar, card, raised popover. The sidebar must read brighter than the page.
Dark mode is a complete pairing: off-black canvas, slightly lifted sidebar, navy-lavender action fill — never teal, never neon as operational status.

Brand energy (aurora cyan, purple, orange) appears in:

- the 3px shell edge;
- `aurora-rule` under identity titles;
- the second word of H1 only in QG (`Operacional`), Pautador (`Pro`) and Redator (`Editorial`);
- login, change-password and 404;
- the 2px rail and navy/purple wash of the active sidebar item (same axis as Pro, not a table state).

Aurora is never a table background, warning, progress fill, metric or selected-row color. Nav titles stay solid navy at 14px: clipped aurora text fails AA on the cyan stop.

## Semantic color tokens

Use the CSS variables. Hex below is the normative hue for documentation and `.impeccable/design.json`.

### Light

| Token | Role | Normative |
|---|---|---|
| `--background` | Page canvas, mineral | `#D4DBE3` |
| `--card` | Work surface | `#F4F7FA` |
| `--raised` | Popover, sticky overlay | `#FBFCFE` |
| `--muted` | Wells, group headers | `#C5CDD6` |
| `--foreground` | Ink | `#13171E` |
| `--muted-foreground` | Secondary text | `#3D4754` |
| `--border` | Structural hairline | `#9AA6B4` |
| `--input` | Field outline (3:1 vs card) | measured in CSS |
| `--primary` | Navy for icons, rings, selected ink | `#0D47A1` |
| `--success` | Healthy completed state | `#116E52` |
| `--warning` | Attention, not error | `#885407` |
| `--destructive` | Error, block, irreversible | `#B33232` |
| `--verified` | Source observed | `#006A85` |
| `--info` | Neutral information | `#05697F` |
| `--demo` | Demonstration / fixture | `#6B4A1B` |

### Dark

| Token | Role | Normative |
|---|---|---|
| `--background` | Canvas | `#0D1218` |
| `--card` | Work surface | `#171E28` |
| `--raised` | Overlay | `#1E2733` |
| `--muted` | Wells | `#121821` |
| `--foreground` | Ink | `#E8EEF4` |
| `--muted-foreground` | Secondary | `#A8B4C2` |
| `--primary` | Action ink/fill, lightened navy | `#6B96E6` |

Semantic meanings stay closed: `primary`, `verified`, `success`, `warning`, `destructive`, `info`, `demo`.
`verified` is not success. `demo` is not warning. `destructive` is not a loud primary.

## Contrast

- Body and labels: 4.5:1 against the actual bed (canvas, card, muted well, tinted chip).
- Large text and UI glyphs: 3:1.
- Primary button text vs primary fill: 4.5:1 in both themes.
- Field border vs card: 3:1.
- Measure on the rendered surface, not on the theoretical card.

## Typography

Three families, no fourth.

| Role | Family | Use |
|---|---|---|
| Display | **Outfit** | Page titles, short section titles, identity kickers |
| Body | **IBM Plex Sans** | UI, forms, explanations, navigation |
| Data | **IBM Plex Mono** | IDs, hashes, receipts, timestamps when they must not dance |

Fallbacks: `ui-sans-serif, system-ui, sans-serif` and `ui-monospace, SFMono-Regular, Menlo, monospace`.

Scale:

| Role | Size | Weight | Notes |
|---|---|---|---|
| Page title | 28–36px | 650 | `tracking-tight`, line-height 1.1 |
| Section | 16–20px | 600 | Sentence case |
| Body | 14–16px | 400 | Line-height 1.5 |
| Table dense | 13px | 400 | Tabular nums. Actions stay ≥14px |
| Kicker | 11px | 600 | Uppercase, tracking 0.12em. Navigation aid only |
| Chip word | 13px | 600 | Sentence case. Never muted-on-muted |

No `clamp()` on product headings. No Inter. No Space Grotesk.
Numbers that compare use `tabular-nums` / `.tabular` / IBM Plex Mono when they are identifiers.

## Spacing, radius, shadow, z-index

Spacing unit 4px. Scale: 4, 8, 12, 16, 24, 32, 48.

Radius: control 8, panel 10, modal 14, pill 999. Inner elements are tighter than their container.

Shadows are tinted to the mineral hue. No pure-black glow on light canvas.

| Token | Use |
|---|---|
| none | Filters, chips, unselected rows |
| `--shadow-card` | Work surface on canvas |
| `--shadow-sticky` | Sticky toolbar over content |
| `--shadow-elevated` | Popover, menu |
| `--shadow-modal` | Blocking dialog |

Z-index scale, no `9999`:

| Token | Value | Use |
|---|---|---|
| `--z-base` | 0 | Content |
| `--z-sticky` | 20 | Table header, local toolbar |
| `--z-shell` | 30 | App header |
| `--z-nav` | 40 | Sidebar / drawer backdrop |
| `--z-overlay` | 50 | Drawer, popover |
| `--z-modal` | 60 | Dialog, skip link when focused |
| `--z-toast` | 70 | Toasts |

## Density by screen type

Follow `PRODUCT.md` §9. In CSS, prefer:

- dashboards and inventories: compact rows, 8–12px vertical rhythm;
- wizards: 16–24px between decisions;
- identity surfaces: more air, never presentation-scale type in the workspace.

## Page identity

Every operational page header, in this order:

1. Kicker: 11px uppercase + optional 20×20 icon chip (`bg-primary/10 text-primary`).
2. H1 Outfit 28–36px, ink. Identity rooms may color the second word with `text-aurora` only as listed above. Estúdio never uses aurora text.
3. `aurora-rule w-16` under the H1.
4. One purpose sentence, `text-sm text-muted-foreground`, max ~70ch.
5. At most one primary button in the header.
6. Desktop budget 200–260px so the first work row stays on screen.

Use `CabecalhoDePagina` when touching a header. Do not invent a second stack.

## Base components

**Button.** Primary uses `gradient-aurora-action` (navy → purple), weight 600, min-height 40 desktop / 44 mobile, visible mass. Hover: 1px lift + gradient shift, 140–160ms, only inside `@media (hover: hover) and (pointer: fine)`. Secondary is solid muted, not a pale outline. Outline is tertiary. Destructive is isolated. Press: `scale(0.97)` in 140ms. Disabled: 0.45 opacity, `pointer-events: none`.

**Field.** Label above. Helper before error. Error below, in context, with recovery. Height 40/44. Focus ring uses `--ring`. Disabled is washed out. Read-only keeps ink and a muted bed, never the disabled fade.

**Tabs.** Segmented well: `bg-muted p-1 border`. Selected pill: `bg-card shadow-card`. Never `bg-background` for the selected pill. Never underline tabs.

**Chips.** Glyph + word + description (sr-only if needed). Height 24, radius full. Word uses `text-foreground` or the semantic token, never muted-on-muted.

**Table.** Inventory is a table. Sticky header, hairline rows, selected row tint, expand in place. Account group is a muted header row.

**Card.** Only for an object, a modal surface or a real grouping. No nested `shadow-card`.

**Dialog / sheet / drawer.** Emerge from the trigger. 200–350ms, move curve. Scrim 45–60%.

**Toast.** 3–5s, `aria-live="polite"`, does not steal focus.

## Form, table, dashboard, wizard, creation, settings

- Forms: visible labels, grouped fieldsets, validate on blur, focus first invalid.
- Tables: comparable columns, right-aligned money, sentence-case names.
- Dashboards: one dominant period control, freshness, no identical metric-card grid as the only structure.
- Wizards: step names are verbs, not "Etapa 1". Back is always available.
- Creation benches keep the safety contract visible.
- Settings look like the rest of the product. No orphan admin theme.

## Empty, error, loading, blocked, demo

Use `EstadoOperacional` for page-level states:

| Tone | Use |
|---|---|
| `loading` | Skeleton matching the destination layout |
| `vazio` | Collection exists and is empty |
| `filtro` | Universe has rows, recorte has none |
| `erro` | Recoverable read/write failure + retry |
| `bloqueado` | Permission, policy or lock |
| `demo` | Fixture or exploratory UI |
| `parcial` | Incomplete read, say what is missing |
| `indisponivel` | Source down or not configured |
| `sucesso` | Completed act, no exclamation |

Loading, empty and error are never the same grey box.

## Motion

Purpose: feedback, orientation, continuity. Not decoration.

| Token | Duration | Easing |
|---|---|---|
| `--motion-press` | 100–160ms | enter curve |
| `--motion-menu` | 150–250ms | enter curve |
| `--motion-sheet` | 200–350ms | move curve |

Animate only `transform`, `opacity`, `color`, `background-color`.
Never `width`, `height`, `top`, `left`. Never `transition: all`.
Do not animate keyboard-initiated navigation.
No infinite loops except essential progress (spinner, indeterminate bar).
`prefers-reduced-motion: reduce` kills non-essential motion.
`[data-theme-switching] * { transition: none !important }`.
Hub `/trafego` does not stagger on load.

## Breakpoints

375, 768, 1024, 1440.
Mobile: single column, no horizontal overflow, 44px targets, primary action reachable.
Desktop: sidebar + workspace. Content max width ~1400px on economic pages; inventories may use the full work column.

## Icons

One family per surface. Product already uses Hugeicons via `Icone` plus a few Lucide leftovers.
New work uses `Icone` / Hugeicons. Do not introduce Phosphor or a third family.
Stroke weight stays consistent. Icon-only controls have an accessible name.

## Real content versus demo

Demo, fixture and exploratory Meta/Google surfaces must use `tone="demo"` or `VerdadeDoDado` with `demo`.
Never style demo numbers as live success.
Never hide the word "demonstração".

## Forbidden

- Inter or Space Grotesk as product fonts
- AI purple gradient as action language
- Landing hero on operational routes
- White-on-white surfaces
- Pale outline as the only primary
- Nested elevated cards
- Underline tabs
- Side color stripes thicker than 1px, except the 2px aurora rail on the active nav item
- Glassmorphism in the workspace
- Glow on operational controls
- Invented zeros and fake live dots
- `transition: all`
- Decorative infinite motion
- Raw hex in components
- Copying the presentation design system into the product

## Visual QA

Prove, do not infer:

1. Light and dark on 375, 768, 1024, 1440.
2. Skip link, focus ring, keyboard path, reduced motion.
3. Loading, empty, error, blocked, demo, disabled, read-only.
4. Primary action visible without hunting.
5. No horizontal overflow.
6. Contrast of body, muted, chip, field border and primary button.
7. Copy audit: no vague AI phrasing on screen.

Acceptance name for this system: `VOLC_OS_DESIGN_SYSTEM_V2_LOCAL_READY`.
