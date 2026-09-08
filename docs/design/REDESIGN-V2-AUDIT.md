# Redesign V2 — diagnóstico e decisões

Base de partida: `c08bdf573475079fd26904deb33bd088bfa34d44` em `execution/volc-os-operacao-80-20`.
Autoridade antiga: `design.md` (Inter + Space Grotesk, canvas `#F3F5F7`, primary `#0D47A1`).

## Leitura de produto

VOLC OS é uma bancada operacional para profissionais de mídia paga e criação que precisam observar, decidir, preparar, aprovar e agir com confiança. A linguagem é de um control room editorial e energético, não de uma apresentação minimalista nem de um clone do Meta Ads Manager.

A interface herdada parecia deck institucional: superfícies quase iguais, ação primária tímida, tipografia de apresentação, estados falsos (ponto verde “tempo real”, “Online”, “Dados atualizados” sem prova) e decks pretos no meio do canvas claro.

Dials usados, sem ajuste:

- DESIGN_VARIANCE: 5
- MOTION_INTENSITY: 4
- VISUAL_DENSITY: 7

## O que foi retirado de propósito

- Inter e Space Grotesk como famílias de produto
- Navy institucional `#0D47A1` como ação padrão do workspace
- Canvas quase branco colado no cartão
- Glass no header mobile do shell
- Sidebar em gradiente de card
- Afirmação “Online” no perfil
- Ponto pulsante de “tempo real” no Dashboard e na Incubadora
- Selo “Dados atualizados” sem horário
- Decks de comando pretos (Hub, Bancada, cockpit) no tema claro
- `alert()` nativo em Projetos (mesmo texto, agora toast)
- Ponto verde pulsante em Integrações e no rodapé de convite do login
- `transition: all` nos primitivos tocados
- Loops decorativos no 404 e no selo de convite

## O que entrou

- `PRODUCT.md` como contrato de fluxos, verdade dos dados e taxonomia de ações
- `design.md` V2: control room mineral, teal `#0A5461`, Outfit + IBM Plex Sans + IBM Plex Mono
- Tokens reais em `src/index.css` e Tailwind (`raised`, `demo`, motion, z-index)
- Primitivos: botão com massa, campo com read-only distinto, abas no poço, tabela com cabeçalho, alerta com tons
- Shell: skip link preservado, header sólido, sidebar `bg-sidebar`
- `CabecalhoDePagina`, `EstadoOperacional`, `VerdadeDoDado`, `Campo`
- Estados de erro/vazio/bloqueio aplicados em Dashboard, Relatórios, Projetos, Campanha, Custos, Usuários, Cofre, Pautador, Redator, Funil, Config
- Laboratório de criativos de volta ao shell
- Decks minerais: `traffic-hub-command`, `bancada-command-deck`, `campaign-cockpit-hero` usam card/muted/foreground
- Login permanece superfície de identidade noturna (`login-root dark`); 404 usa tokens e existe nos dois temas
- Aurora só em identidade, progresso e orientação — não em títulos de workspace

## O que não mudou

Rotas do inventário, query params, payloads, eventos analíticos, regras de OPERATOR, contratos HTTP, backend, Meta, Google, Supabase, n8n, geração paga.

O desvio silencioso de OPERATOR em `ProtectedRoute` permanece: é contrato de segurança existente, não pele.

Rotas `/trafego/meta/packs` e `/trafego/meta/packs/:packId` aparecem na worktree por trabalho alheio desta mesma árvore. Não foram inventadas nem revistas por esta rodada.

## Contraste

Tokens semânticos de success/warning/verified/info/destructive do tema claro foram preservados (já medidos para AA). Canvas, tinta secundária e primary foram recalibrados para hierarquia e 4,5:1. Dark mode recebeu o mesmo teal em luminosidade própria, não inversão do navy.

Login e 404 usam `gradient-aurora-action` (metade profunda) porque a aurora completa reprova AA sob texto branco.

## Precedência

1. `PRODUCT.md` — contrato de produto
2. `design.md` — autoridade visual (raiz)
3. `docs/DESIGN.md` — ponteiro
4. `src/index.css` + `tailwind.config.ts` — tokens consumidos
5. `.impeccable/design.json` — derivado de máquina, nunca autoridade
