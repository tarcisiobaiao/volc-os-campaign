# Filtro e Exportação de Relatórios por Operador — /reports

**Data:** 2026-07-06
**Objetivo:** Permitir que o admin filtre a página `/reports` por OPERADOR (campanhas atribuídas exclusivamente a ele via `user_campaigns`) e exporte o relatório em PDF já com o recorte do operador.

## Contexto do sistema (verificado no código)

- `/reports` (`src/pages/Reports.tsx`) já é admin-only via allowlist do `ProtectedRoute` (operadores só acessam `/dashboard/campaign/*` e `/settings/campaigns`).
- Atribuição campanha→operador: tabela `user_campaigns (user_id uuid, campaign_id varchar)` — o `campaign_id` é o ID do Google Ads (string), o mesmo valor usado em `Campaign.id` pelo `supabaseDataService`. Exclusividade (1 operador por campanha) é garantida na atribuição (`usersService.getAssignedCampaigns`).
- Tabela companheira `user_projects (user_id, project_id int)`.
- `useSupabaseData(filters)` já aceita `userProjectIds?: number[]` e `userCampaignIds?: string[]` e aplica esses filtros em `getProjects` e `getCampaignsWithRevenue`. **Gap conhecido:** `getSummary` e `getDailyMetrics` ignoram esses campos (retornam totais globais).
- Operadores = linhas de `public.users` com `role = 'OPERATOR'` (`usersService.getAll()`).
- `Campaign.revenue` já é receita líquida (agregado de `daily_campaign_metrics.revenue_converted_revshare`); `Campaign.investment` = spend.

## Decisões de design

1. **Dropdown "Operador"** ao lado do filtro de projeto, renderizado apenas para admin (`useUserRole().isAdmin()` — cinto e suspensório, a rota já é admin-only). Opção padrão "Todos os Operadores"; itens = usuários `role='OPERATOR'`.

2. **Mecanismo de escopo:** ao selecionar um operador, buscar `usersService.getUserProjects(id)` + `getUserCampaigns(id)` e injetar como `userProjectIds`/`userCampaignIds` nos filtros do `useSupabaseData` (mesmo padrão do `GeneralDashboard`). Fonte de verdade do recorte = campanhas (`user_campaigns`).
   - Operador **sem campanhas atribuídas** → sentinela (`userProjectIds: [-1]`, `userCampaignIds: ['__none__']`) para o relatório zerar (em vez do comportamento legado "array vazio = sem restrição"), mais banner informativo.

3. **Resumo com recorte do operador (client-side):** como `getSummary`/`getDailyMetrics` são globais, quando o filtro de operador está ativo o resumo é recalculado a partir da lista `campaigns` (já filtrada):
   - Investimento = Σ `investment`; Faturamento Líquido = Σ `revenue` (já pós-revshare);
   - Impostos = alíquota vigente × faturamento líquido; **Custos operacionais NÃO são aplicados** no recorte por operador (são custos fixos da empresa, não atribuíveis a um operador) — indicado na UI e no PDF;
   - Lucro Líquido = Faturamento Líquido − Investimento − Impostos; ROI/ROAS derivados.

4. **Tabela de projetos no modo operador:** os valores por projeto são reagregados a partir das campanhas do operador (agrupamento por `projectId`), para não superestimar com totais do projeto inteiro. Nova seção **"Performance por Campanha"** (apenas no modo operador) lista cada campanha do operador.

5. **Gráfico diário no modo operador:** novo `operatorReportService.getDailyMetricsForCampaigns(campaignIds, start, end)` consulta `daily_campaign_metrics` (`.in('campaign_id', …)` em chunks de 200, paginado) e agrega por data — série diária correta do operador. Pizza de distribuição usa os projetos reagregados.

6. **PDF:** cabeçalho ganha linha `Operador: <nome>`, resumo usa os números do recorte, nota sobre custos operacionais, tabela de projetos reagregada e tabela "Campanhas do Operador". Nome do arquivo: `relatorio_operador_<slug>_<período>_<data>.pdf`. Botão de exportar desabilitado enquanto dados carregam (evita exportar dados globais rotulados com operador).

7. **Refresh flows:** os objetos de filtro construídos inline em `handlePeriodChange`/`handleDateRangeChange` passam a incluir os campos do operador (helper único).

## Fora de escopo (YAGNI)

- Cutover para `campaign_members` (v6) — `useUserFilters`/dashboard legado ainda leem `user_campaigns`; este recurso segue a mesma fonte.
- Export CSV; comissões do operador no PDF; filtro de operador para não-admins.
- Correção do gap de `getSummary`/`getDailyMetrics` no service (contornado client-side aqui).
