# Redesign V2 — QA

Registro vivo desta rodada local. Sem mutação externa.
Servidor: Vite em `http://127.0.0.1:8081/` (8080 ocupada). Sem sessão. Sem dados externos.

## Gates

| gate | resultado | nota |
|---|---|---|
| testes focais `src/components/sistema` + `bancada/__tests__` | **84/84 passed** | primitivos e contrato da Bancada |
| `npm run build` | **verde** | ~2m44s |
| `npm test` completo | **1873 passed, 57 failed, 3 skipped** | baselines herdados, não mascarados |
| `git diff --check` | limpo | — |
| `python3 scripts/verificar_segredos.py` | limpo | — |
| grafo `--check` | após `atualizar_grafo_volc_os.py` | nunca `graphify update .` |

## Falhas herdadas do `npm test` (não mascarar)

15 arquivos. Leitura honesta:

- QG espera `P05-T11` vs `P05-T12` (roadmap, não pele)
- `FilaDeAtencao` sem Router
- timeouts Meta/onboarding
- galeria de packs precisa Router (Links de trabalho alheio)
- `meta-sem-formula-legada` espera “Retorno excedente (%)”

Nenhuma dessas falhas foi “consertada” para verde falso.

## QA visual localhost

Viewports: 375, 768, 1024, 1440. Temas claro e escuro onde o produto os expõe.

### O que o produto realmente pinta

- `/login` é superfície de identidade **sempre noturna** (`className="login-root dark"`). Não existe light mode de workspace nesta rota. Capturas antigas rotuladas `login-light-*` eram o mesmo cromo escuro (macOS `prefers-color-scheme: dark`) e foram apagadas para não mentir.
- `*` (404) usa tokens semânticos. Light = canvas mineral. Dark = canvas carvão. Os dois foram forçados via CDP (`document.documentElement.classList` + `localStorage.theme`) porque o headless sozinho não hidratava o `next-themes` a tempo.
- Rotas protegidas sem sessão redirecionam para `/login`. Prova: `/trafego?rede=meta` → `/login` (`protected-redirect.txt`). Nenhum dado Meta/Google foi lido.

### Screenshots em `docs/design/redesign-v2-screens/`

| arquivo | o que prova |
|---|---|
| `login-identity-{375,768,1024,1440}.png` | identidade noturna, CTA aurora-action visível, campos com label |
| `login-focus-email-1440.png` | anel/glow de foco no email |
| `not-found-qa-v2-light-{375,768,1024,1440}.png` | canvas mineral, tinta escura, CTA visível, sem overflow |
| `not-found-qa-v2-dark-{375,768,1024,1440}.png` | interpretação escura completa do 404 |
| `not-found-reduced-motion-1440.png` | 404 com `prefers-reduced-motion: reduce` |
| `trafego-unauth-redirect-1440.png` | contrato de sessão: hub Meta vira login |
| `protected-redirect.txt` | pathname comprovado |

### Checagens manuais / instrumentadas

| checagem | resultado |
|---|---|
| skip link | presente no `Layout`; login/404 não usam shell (inventário) |
| focus ring | visível no email do login (captura) |
| reduced motion | 404 recapturado com emulate reduce |
| loading / erro / vazio / bloqueado / demo | cobertos por `EstadoOperacional` + testes 84/84; páginas autenticadas não fotografadas |
| CTA primária | Entrar e Voltar ao início com massa visual |
| copy | sem “online”, sem “tempo real” falso nas superfícies tocadas |
| teclado | atalho ⌘K da paleta não abre sem sessão (`CommandPalette` retorna `null` se `!user`) — correto |
| overflow mobile | 375px de login e 404 sem barra horizontal aparente nas capturas |

### Limitação real

O shell autenticado (sidebar, dashboard, hub, campanhas, criativos, settings) não foi fotografado. Fazer login puxaria sessão e leituras externas, o que esta rodada proíbe. A revisão dessas rotas é de código (tokens, estados, decks) + testes focais, não de screenshot logado.

## Baselines herdados

Testes de contrato visual da Bancada (`contrato-visual.test.ts`, `chip-de-estado.test.tsx`, `acao-dominante.test.tsx`) permanecem. As 57 falhas do suite completo estão listadas acima.

## Árvore

Esta rodada não reverte nem commita trabalho alheio (packs Meta, backend `GET /{pack_id}`, `CreativePackPage`). A árvore permanece suja por esses arquivos depois do commit do Design System V2.
