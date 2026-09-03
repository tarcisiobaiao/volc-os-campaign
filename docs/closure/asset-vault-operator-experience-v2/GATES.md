# GATES — asset-vault-operator-experience-v2

Medido em 2026-09-03 na worktree `/private/tmp/volc-asset-vault-operator-experience-v2`.
Branch `sprint/asset-vault-operator-experience-v2`. HEAD de merge `caf4df9e350800e6a26ce236e8e4136b4f9a4a56` + commits desta missão, inclusive a microcorreção de persistência 1Password.

Hallmark · pre-emit critique: P5 H5 E4 S5 R5 V4

## Não negociáveis da missão

| Gate | Resultado |
|---|---|
| Checkout `main` intocado | sim. Worktree isolada |
| `origin/volc-os-v2` = `207e91f1da290130e8d02b78c3ba1c8e9a761111` | sim |
| Candidato `5f54d25cf4375c4a43c6b8b5c819f8937106090d` integrado por merge | sim, pais `207e91f` + `5f54d25` |
| Sem cherry-pick seletivo, rebase ou force push | sim |
| Sem merge em `volc-os-v2` / `main` | sim |
| Sem escrita Supabase / migration / 1Password real / AdsPower / publish / deploy | sim |
| localhost:8080 (PID 38779) vivo e não morto | sim, conferido após os gates |
| Sem fallback de `fixtures.ts` em runtime | sim; imports só em teste e no próprio `fixtures.ts` |
| Sem botão copiar/revelar segredo | sim |
| `op://` contíguo na fonte do operador / `cofreApi.ts` / `AssetVaultPage` | ausente após a microcorreção. Testes detectam o esquema por `charCode` / concatenação, sem literal contíguo na UI |
| PNG de evidência sem `op://` | varridos; zero hits |
| Bundle `dist/` sem `op://` contíguo | zero hits na build desta rodada |
| sessionStorage / localStorage sem pecas nem localizador | contraprovas executáveis no onboarding; rascunho legado é sanitizado na leitura |

## Testes

```
npx vitest run src/features/asset-vault
Test Files  10 passed (10)
Tests       93 passed (93)
```

Inclui: estados 401/403/503/vazio/config, inventário, fronteira de segredo, revisão delta, onboarding, visão vazia ≠ zero saudável, MFA/password/token/OTP recusados, aposentar com confirmação, varredura de fonte, sanitização de rascunho, Fechar/remontar/Concluir sem pecas no storage, mutation com localizador só em memória.

Vitest proporcional desta rodada = o ownership `src/features/asset-vault` (não o monorepo inteiro).

## TypeScript

`npx tsc --noEmit -p tsconfig.app.json`: **zero erros** em `src/features/asset-vault/**` e `src/pages/settings/AssetVaultPage.tsx`. Baseline herdado do monorepo permanece fora deste ownership (dezenas de erros pré-existentes em dashboard/supabaseDataService/etc.) e não foi expandido por esta missão.

## Build

`npx vite build` — **passou** em 18,55 s nesta rodada. Aviso de chunk >500 kB é pré-existente do bundle global, não desta tela.

## git diff --check

`git diff --check 207e91f1da290130e8d02b78c3ba1c8e9a761111` (worktree vs base): **limpo**. Resíduos de trailing whitespace em EXPERIENCE-CONTRACT.md / UX-AS-IS.md e newline extra em Inventario.tsx foram removidos nesta microcorreção.

## npm ci

`package.json` e `package-lock.json` são idênticos a `207e91f1` e internamente consistentes (deps/devDeps sem mismatch). Esta lane não os tocou. `npm ci --dry-run --ignore-scripts` saiu 0 e apenas simularia refresh de `node_modules` contra o mesmo lock (install drift herdado, não delta da lane). Não houve atualização ampla de dependências.

## Visual / a11y (double sanitizado, fora do git)

Portas 4185 (after), 4186 (as-is `caf4df9`), 4187 (dark). API double em 8029 com nomes `Página exemplo` / `Motor exemplo`. Aliases Vite de Auth/Supabase **só em `/tmp/volc-cofre-capture/`**, não no app.

Capturas em `evidence/after/` e `evidence/as-is/`:

- desktop 1440×900 e 1920×1080
- tablet 768
- mobile 414 / 375 / 320
- dark 1440 e 414

Teclado e leitores: provados em jsdom (`getByRole`, `aria-pressed`, `role=status/alert`, `alertdialog` de aposentar). Não houve passe Chrome com Tab.

`prefers-reduced-motion`: classes `motion-reduce:*` no chrome; não houve toggle live.

Overflow: moldura `overflow-x-clip`; header empilha em mobile; abas `flex-1 basis-50%` abaixo de `sm`.

## Hallmark slop (recorte produto)

| # | Gate | Esta superfície |
|---|---|---|
| 1 | Display Inter? | Não — Space Grotesk via token |
| 2 | Gradient text | Não |
| 3 | 3-card feature grid | Não — faixa 3 colunas assimétrica + tabela |
| 4 | Card nested | Inspetor é um painel, não card dentro de card de métrica |
| 10 | `transition: all` | Não no operador |
| 16 | Toast celebratório | Toasts só para recibo/falha invisível |
| 34 | Scroll horizontal 320–1920 | Clip na moldura; gavetas podem scrollar *dentro* |
| 38a | Heading itálico | Não |
| 46 | Métrica inventada | Não — double sanitizado ou “sem amostra” |

Nav/footer/hero (42–45) são do shell global, fora do ownership.

## O que estes gates NÃO provam

Inventário real, segredo resolvido, AdsPower, publicação, deploy.
