# Plano de Implementacao - Incubadora de Sites

> **Plano histórico:** preserva decisões de origem; o estado atual deve ser consultado no Mapa Vivo.

## Descobertas da Exploracao

- **Supabase project**: `txvvzpstquqmbhljudfn` (campaign-dashboard-system, sa-east-1)
- **Tabela `users.id`**: tipo `uuid` (NOT `bigint` como no prompt) — FK precisa ser ajustada
- **Funcao `update_updated_at`**: NAO existe — precisa ser criada na migration
- **Zustand**: NAO instalado — o projeto usa Context API (AuthContext) e hooks customizados
- **@dnd-kit**: NAO instalado — precisa instalar para Kanban drag & drop
- **Router**: React Router v6 em `App.tsx`, rotas protegidas com `<ProtectedRoute>`
- **Sidebar**: `Navigation.tsx` com arrays `navigationItems[]` e `configurationItems[]`
- **Layout**: Todas as paginas usam `<Layout>` wrapper
- **Toasts**: `useToast()` hook (shadcn) + sonner
- **Data fetching**: Supabase client direto (`@/lib/supabase`) + services pattern
- **ProtectedRoute**: OPERATORs so acessam `/dashboard/campaign/` e `/settings/campaigns`

## Decisoes de Adaptacao

1. **SEM Zustand** — Usar React Context + hooks, seguindo o pattern existente do projeto
2. **FK `created_by`** — Tipo `uuid` referenciando `public.users(id)`
3. **RLS com `WITH CHECK`** — Policies precisam de `USING` e `WITH CHECK` para INSERT/UPDATE
4. **ProtectedRoute** — Incubadora sera `adminOnly`, nao precisa alterar allowed paths do OPERATOR

## Etapas de Implementacao

### ETAPA 1: Schema SQL (Supabase Migration)
Aplicar uma unica migration com:
- Tabela `incubator_sites` (com `created_by uuid`)
- Tabela `incubator_pipeline_logs`
- Tabela `incubator_articles`
- Indices
- Funcao `update_updated_at()` + triggers
- RLS policies (com `USING` + `WITH CHECK`)
- Realtime publication

### ETAPA 2: Instalar dependencias
- `@dnd-kit/core` + `@dnd-kit/sortable` + `@dnd-kit/utilities` (para Kanban drag & drop)

### ETAPA 3: Types + Constants
Criar `src/types/incubator.ts`:
- Interfaces: `IncubatorSite`, `IncubatorArticle`, `PipelineLog`, `NewSiteFormData`
- Types: `SiteStatus`, `ArticleStatus`, `ExecutionType`, `ExecutionStatus`
- Constants: `STATUS_COLORS`, `STATUS_LABELS`, `KANBAN_COLUMNS`

### ETAPA 4: Service Layer (API)
Criar `src/services/incubatorService.ts`:
- `fetchSites()` — listar todos os sites
- `fetchSiteById(id)` — detalhes de um site
- `createSite(data)` — inserir novo site
- `updateSite(id, data)` — atualizar site
- `updateSiteStatus(id, status)` — mudar status (Kanban drag)
- `deleteSite(id)` — remover site
- `fetchArticles(siteId)` — artigos de um site
- `fetchPipelineLogs(siteId)` — logs de execucao
- `triggerPipeline(site)` — POST webhook n8n

### ETAPA 5: Hooks
Criar em `src/hooks/incubator/`:
- `useIncubatorSites.ts` — fetch + CRUD de sites com estado local
- `useIncubatorDetail.ts` — fetch site + artigos + logs para pagina de detalhe
- `useIncubatorRealtime.ts` — Supabase Realtime subscriptions
- `useTriggerPipeline.ts` — disparo do webhook n8n com loading/error states

### ETAPA 6: Componentes
Criar em `src/components/incubator/`:

**Base:**
- `StatusBadge.tsx` — badge colorido por status do site

**Dashboard:**
- `KpiCards.tsx` — 4 cards de metrica no topo (Total, Gerando, Aguardando, Aprovados)
- `SiteCard.tsx` — card individual com progress bar, status, quick actions
- `SiteGrid.tsx` — grid responsivo de SiteCards

**Kanban:**
- `KanbanBoard.tsx` — board completo com colunas
- `KanbanColumn.tsx` — coluna individual com header + scroll
- `KanbanSiteCard.tsx` — card compacto para arrastar

**Detail:**
- `SiteConfig.tsx` — bloco de configuracao do site
- `SiteProgress.tsx` — barra de progresso artigos
- `PipelineLog.tsx` — timeline de execucoes
- `ArticlesTable.tsx` — tabela de artigos com status

**Modal:**
- `NewSiteModal.tsx` — formulario de criacao (react-hook-form + zod)

### ETAPA 7: Paginas
- `src/pages/incubator/IncubatorPage.tsx` — Pagina principal com tabs Dashboard/Kanban
- `src/pages/incubator/IncubatorDetailPage.tsx` — Pagina de detalhes do site

### ETAPA 8: Rota + Sidebar
- `App.tsx` — Adicionar rotas `/incubator` e `/incubator/:siteId`
- `Navigation.tsx` — Adicionar item "Incubadora" no array `navigationItems` com `adminOnly: true`
- Importar icone `Rocket` do lucide-react

### Ordem de execucao dos arquivos:
1. Migration SQL no Supabase
2. `npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities`
3. `src/types/incubator.ts`
4. `src/services/incubatorService.ts`
5. `src/hooks/incubator/useIncubatorSites.ts`
6. `src/hooks/incubator/useIncubatorDetail.ts`
7. `src/hooks/incubator/useIncubatorRealtime.ts`
8. `src/hooks/incubator/useTriggerPipeline.ts`
9. `src/components/incubator/StatusBadge.tsx`
10. `src/components/incubator/NewSiteModal.tsx`
11. `src/components/incubator/dashboard/KpiCards.tsx`
12. `src/components/incubator/dashboard/SiteCard.tsx`
13. `src/components/incubator/dashboard/SiteGrid.tsx`
14. `src/components/incubator/kanban/KanbanSiteCard.tsx`
15. `src/components/incubator/kanban/KanbanColumn.tsx`
16. `src/components/incubator/kanban/KanbanBoard.tsx`
17. `src/components/incubator/detail/SiteConfig.tsx`
18. `src/components/incubator/detail/SiteProgress.tsx`
19. `src/components/incubator/detail/PipelineLog.tsx`
20. `src/components/incubator/detail/ArticlesTable.tsx`
21. `src/pages/incubator/IncubatorPage.tsx`
22. `src/pages/incubator/IncubatorDetailPage.tsx`
23. `src/App.tsx` (adicionar rotas)
24. `src/components/layout/Navigation.tsx` (adicionar menu item)
