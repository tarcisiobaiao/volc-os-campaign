# `src/v6/` — Sistema novo de RBAC e comissões (Etapa 4 — consolidado)

Esta pasta contém **toda** a camada de dados e os componentes de
apoio do sistema de roles, memberships e comissões versionadas.

## ⚠️ Status atual — cutover consolidado

A tela oficial passou a ser **`/settings/users`** (arquivo
[`webgo/src/pages/settings/UsersSettings.tsx`](../pages/settings/UsersSettings.tsx)).
Essa rota agora reusa diretamente `UsersTab`, `MembershipsTab` e
`CommissionsTab` desta pasta, com layout simples de 3 abas.

A área `/admin/v6` **continua existindo** apenas como **fallback
técnico** acessível por URL direta, atrás da feature flag
`VITE_USE_V6_ADMIN`. **Não aparece mais no menu lateral**. Serve
como dashboard interno (com `SummaryCards`, `PayoutsMonthly`,
`TopCampaigns` e `SystemStatusCard`) para auditoria e debug — não
para operação cotidiana.

> **Princípio raiz:** esta pasta continua sendo o "modelo novo"
> consolidado. O `/settings/users` é quem **usa** esses componentes.
> Qualquer bug fix de lógica deve ser feito aqui — o consumo é
> automaticamente refletido na tela oficial.

---

## Estrutura

```
src/v6/
├── README.md                       ← este arquivo
├── featureFlag.ts                  ← isV6Enabled() — única função exportada
├── types/
│   └── v6.ts                       ← interfaces espelho do schema v6
├── services/
│   ├── campaignRolesService.ts
│   ├── campaignMembersService.ts
│   ├── campaignCommissionsService.ts
│   └── memberPayoutsService.ts
├── hooks/
│   ├── useCampaignRoles.ts
│   ├── useCampaignMembers.ts
│   ├── useCampaignCommissions.ts
│   └── useMemberPayouts.ts
├── components/
│   ├── V6Header.tsx
│   ├── SummaryCards.tsx
│   ├── MembersTable.tsx
│   ├── CommissionsTimeline.tsx
│   ├── PayoutsMonthly.tsx
│   ├── TopCampaigns.tsx
│   └── SystemStatusCard.tsx
└── pages/
    └── V6AdminPage.tsx             ← rota /admin/v6
```

---

## Regras de isolamento

### O que `src/v6/` PODE importar de fora

- `@/components/ui/*` — primitivos shadcn (Card, Table, Badge, etc.)
- `@/components/layout/Layout` — wrapper visual padrão
- `@/lib/supabase` — cliente Supabase (padrão dominante do projeto)
- `@/contexts/AuthContext` — apenas para identificar admin (`useAuth`)

### O que `src/v6/` NÃO PODE importar

- Qualquer service legado (`@/services/*`)
- Qualquer hook legado (`@/hooks/useUserFilters`, `useUserRole`, ...)
- Qualquer página legada (`@/pages/*`)
- React Query (`@tanstack/react-query`) — apesar de instalado, o
  projeto não usa em nenhum lugar; o padrão dominante é
  `useState`+`useEffect`. **Seguir o padrão dominante.**

### O que pode importar `src/v6/` de fora

Três arquivos autorizados:

1. `webgo/src/App.tsx` — registra a rota `/admin/v6` lazy
   (fallback técnico, atrás de `VITE_USE_V6_ADMIN`)
2. **`webgo/src/pages/settings/UsersSettings.tsx`** — rota oficial.
   Importa `UsersTab`, `MembershipsTab`, `CommissionsTab`. Este é
   o ponto de cutover entre o modelo antigo e o novo.
3. `webgo/src/components/layout/Navigation.tsx` — historicamente
   importava `isV6Enabled`; **hoje não importa mais nada** do v6
   (o item "Comissões v6" foi removido do menu no cutover). Mantido
   aqui por referência histórica.

---

## Feature flag

`VITE_USE_V6_ADMIN=true` no `.env.local`. Default off. Vide
[`featureFlag.ts`](./featureFlag.ts) para detalhes.

**Importante:** Vite só lê variáveis de ambiente no boot do dev
server. Mudar `.env.local` em tempo de execução não funciona —
reinicie o `npm run dev`.

---

## Modo de operação (Etapa 3.C — operacional)

- **Read + Write.** A área agora tem CRUD completo de usuários,
  memberships e comissões. Etapas 3.A e 3.B (read-only) continuam
  na base.
- **Admin only.** Mesmo com a flag ligada, usuários com role
  `OPERATOR` não veem o item de menu (filtro `adminOnly` em
  `Navigation.tsx`), são redirecionados pelo `ProtectedRoute` legado
  se tentarem acessar a rota direto, e bloqueados pelo check interno
  em `V6AdminPage.tsx`.
- **Lazy load.** A página é importada via `React.lazy()` em
  `App.tsx`, então o chunk só é baixado quando a rota é visitada.
  Com a flag off em produção, o código nem é referenciado.

---

## O que NÃO está nesta etapa

A Etapa 3.C é a operação básica funcionando. Os seguintes itens
ficam para etapas futuras:

- **3.D — Read-only UX premium:** filtros por intervalo, drilldown
  por campanha, gráfico Recharts dos payouts mensais, export CSV.
  (Era a antiga 3.B; ficou para depois porque o operacional foi
  priorizado.)
- **Etapa 4 — Cutover:** substituição da UI legada de gestão de
  usuários (`/settings/users`) e descontinuação do dual-write.
  Decisão para depois da 3.C ser validada.
- **Etapa 5 — Limpeza:** drop de `users.commission_percentage`,
  `user_campaigns`, `daily_campaign_metrics.commission_operator`,
  e correção (ou remoção) do trigger legado bugado.

## Múltiplos membros por campanha (regra fundamental do v6)

Uma campanha pode ter **N membros simultaneamente**, cada um com um
role funcional diferente. Por design:

- **Membership não tem exclusividade global por campanha.** A
  constraint UNIQUE de `campaign_members` é
  `(user_id, campaign_id, role_id)` — o mesmo usuário até pode ter
  múltiplos roles na mesma campanha.
- **Comissão é separada de membership.** Diferentes usuários podem
  ter comissões vigentes na mesma campanha simultaneamente. A
  constraint UNIQUE de `campaign_commissions` é
  `(user_id, campaign_id, valid_from)`.

### O que a UI v6 NUNCA deve fazer

- ❌ Marcar uma campanha como "Já atribuída" ou "Ocupada" só porque
  algum outro usuário já é membro dela
- ❌ Bloquear seleção de uma campanha por causa de membership
  alheio
- ❌ Filtrar fora as campanhas que já têm membros

### O que a UI v6 DEVE fazer

- ✅ Mostrar **contexto enriquecido** em cada campanha do dropdown:
  quantos membros tem, quem são, quais comissões estão vigentes
- ✅ Destacar via badge "você já é membro" quando o usuário
  selecionado já tem vínculo com aquela campanha (apenas como
  informação, não como bloqueio)
- ✅ Bloquear apenas duplicata exata real:
  - mesmo (user_id, campaign_id, role_id) já existente em
    `campaign_members`
  - mesma `valid_from` em `campaign_commissions` para o mesmo
    par (user, campaign)

### Onde isso é implementado

| Arquivo | Responsabilidade |
|---|---|
| [`services/lookupsService.ts`](./services/lookupsService.ts) `listCampaignsWithContext()` | Devolve cada campanha já mesclada com seus membros + comissões vigentes |
| [`hooks/useV6Lookups.ts`](./hooks/useV6Lookups.ts) `useV6CampaignsWithContext()` | Hook que cacheia o resultado |
| [`components/forms/CampaignSelector.tsx`](./components/forms/CampaignSelector.tsx) | Combobox reutilizável (Popover + Command) que mostra o contexto sem nunca bloquear |

Os 3 forms (`MembershipForm`, `CommissionForm`, `OnboardingWizard`)
e as 3 tabs (`UsersTab`, `MembershipsTab`, `CommissionsTab`)
**todos** usam esse mesmo `CampaignSelector` + `useV6CampaignsWithContext`.

> **Não confundir com o legado:** o `/settings/users` (tela velha)
> tem uma lógica antiga que filtra campanhas "já atribuídas a outros
> operadores". Isso é uma limitação histórica do modelo legado e
> NÃO foi corrigida (sem cutover). A v6 usa modelo correto desde
> o Etapa 3.C.

## Padrão dual-write (Etapa 3.C)

Mutações de membership escrevem em **duas tabelas** simultaneamente:

| Operação | `campaign_members` (v6) | `user_campaigns` (legado) |
|---|---|---|
| Adicionar | INSERT (idempotente, rola se já existe) | INSERT (idempotente; uma linha por par user/campaign mesmo com múltiplos roles) |
| Atualizar role | UPDATE role_id | (não toca — legado não tem role) |
| Remover | DELETE | DELETE só se não restar nenhum outro role do mesmo par no v6 |

**Por quê:** o `useUserFilters` legado lê de `user_campaigns`. Se
escrevêssemos só no v6, operadores criados pelo v6 perderiam acesso
no app legado. O dual-write preserva a visibilidade até o cutover
do `useUserFilters` (Etapa 4).

**Exceção:** comissões só vivem em `campaign_commissions`. NÃO
escrevemos em `users.commission_percentage` (legado bugado).

## Exceção controlada de isolamento

[`v6OperationsService.ts`](./services/v6OperationsService.ts) é o
**único** arquivo em `src/v6/` que importa de `@/services/`
(`usersService` legado), reutilizando a criação/edição/remoção de
usuário (que envolve `supabase.auth.signUp` + `public.users`).
Autorizado pelo usuário ("Se existir uma forma já usada no sistema
para criar usuário, reutilize"). Documentado no topo do arquivo.

---

## ⚠️ Armadilha do PostgREST: cap silencioso de 1000 linhas

### O que aconteceu

Durante a Etapa 3.A, ao validar os números do `SummaryCards`,
descobrimos que o front mostrava **R$ 539,01** quando o banco tinha
**R$ 91.693,09** de comissão calculada. Causa: o servidor Supabase
aplica `db-max-rows = 1000` no PostgREST, **mesmo quando o client
passa `.limit(100000)`** — o servidor ignora qualquer limite acima
do cap configurado.

Resultado: `daily_campaign_member_payouts` (38 mil linhas) só
devolvia as 1000 linhas mais recentes (~4 dias), e todas as
agregações ficavam capadas.

### Mitigação adotada nesta pasta

Todos os services v6 que leem tabelas potencialmente expansíveis
usam o helper [`_pagination.ts`](./services/_pagination.ts) que
itera com `.range(from, to)` em loop até esgotar os dados.
Ordenação composta com tiebreaker por `id` é obrigatória para
evitar páginas duplicadas/perdidas.

Tabelas blindadas no v6:

- `daily_campaign_member_payouts` (38k+ rows hoje)
- `campaign_members` (306 hoje, cresce com a operação)
- `campaign_commissions` (302 hoje, cresce a cada nova vigência)
- `campaigns` (740 hoje, cresce)
- `users` (5 hoje, futuro-proof)

`campaign_roles` (~4 rows) **não** é paginada — catálogo fixo.

### Aviso para o resto do projeto (legado)

O legado em [`webgo/src/services/supabaseDataService.ts`](../services/supabaseDataService.ts)
mistura dois padrões:

- `.limit(50000)` (vulnerável ao cap; provavelmente capado em
  silêncio em algumas chamadas — vide linhas 812, 865, 1300, 1322,
  1665, 1919, 3814)
- `.range(page * pageSize, …)` (correto — vide linhas 1740, 1958,
  3159, 3274)

**Não foi corrigido** porque esta etapa (3.A) é estritamente
isolada na pasta `src/v6/`. Mas é dívida latente a investigar:
qualquer dashboard legado que dependa de uma tabela com mais de
1000 rows e use só `.limit(...)` pode estar mostrando totais
incorretos há meses sem ninguém perceber.

---

## Bug conhecido do legado (contexto histórico)

Durante a Etapa 2 descobrimos que o trigger
`trigger_calculate_commission_operator` em
`public.daily_campaign_metrics` tem um typo: filtra por
`u.role = 'OPERADOR'` (português) quando o valor real é
`'OPERATOR'` (inglês). Resultado: `commission_operator = 0` em 100%
das ~216 mil linhas históricas.

A página `/admin/v6` mostra isso de forma transparente no card
"Gap vs legado" (Bloco 2). O cálculo novo (v6) é independente e
calcula corretamente — usa `campaign_commissions` em vez de
`user_campaigns + users`.

**Não corrigir o legado nesta etapa.** Decisão consciente: tocar no
trigger é fora do escopo da Etapa 3 e exige alinhamento separado
sobre retroatividade.
