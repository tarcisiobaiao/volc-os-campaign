# Inventário de rotas do VOLC O.S. — matriz auditável

Gerado na revisão visual global de 2026-08-29, a partir de `src/App.tsx` na
base `9885459`. **42 declarações de rota**: 38 rotas reais, 2 redirects
permanentes, 1 condicional por feature flag e o catch-all.

Cada linha foi verificada abrindo o componente de página correspondente; as
referências `arquivo:linha` apontam para onde o estado está implementado.
"Delegado" significa que a página repassa o estado a um componente filho, e a
verificação parou ali.

## Como ler as colunas de estado

- **loading** — existe algo além de tela em branco enquanto a leitura acontece.
- **vazio** — a página distingue "não há nada" de "o filtro não achou nada".
- **erro** — a falha de leitura tem tratamento próprio, e não vira "vazio".
- **permissão** — a rota nega acesso explicando, ou desvia em silêncio.

## Matriz

| rota | finalidade | layout | protegida | loading | vazio | erro | ação primária |
|---|---|---|---|---|---|---|---|
| /login | autenticar o operador na sessao | nenhum (superficie de identidade, aurora permitida) | publica | sim (Login.tsx:331 spinner no botao) | n/a | sim (toast Login.tsx:106 e :121) | Entrar |
| /change-password | trocar a senha provisoria no primeiro acesso | nenhum (superficie de identidade) | protegida | sim (ChangePassword.tsx:262) | n/a | sim (toast ChangePassword.tsx:121) | Alterar senha |
| / | dashboard geral de receita, custo e lucro (so ADMIN; OPERATOR e desviado por OperatorRedirect) | Layout | protegida | sim (GeneralDashboard.tsx:646, tela cheia) | sim (:1314 "Nenhuma campanha encontrada"; :737 "Sem dados") | sim (:656) | conferir P&L do periodo / Atualizar |
| /test | diagnostico tecnico do ambiente (React, Tailwind, Supabase, env vars) | NENHUM | protegida | parcial (SimpleTest.tsx:60, so texto no H1) | NAO | sim mas cru (:127-132) | "Ir para o Dashboard Completo" (:171, link morto para /dashboard) |
| /dashboard/projects | cadastrar e editar projetos | Layout | protegida | sim (via useSupabaseData, ProjectsSettings.tsx:177) | sim (:892-898) | NAO em pagina — so alert() nativo (:386, :444, :485) | Novo projeto |
| /dashboard/campaign/:campaignId | metricas e orientacao de uma campanha | Layout | protegida (rota liberada ao OPERATOR) | sim (CampaignDetailDashboard.tsx:317) | sim (:344 "Campanha nao encontrada") | sim (:330) | conferir a campanha |
| /dashboard/project/:projectId | dashboard financeiro de um projeto | Layout | protegida | sim (ProjectDashboard.tsx:981) | sim (:1471) | sim (:993) + "nao encontrado" com debug (:1019) | analisar o projeto |
| /reports | relatorio consolidado e exportacao em PDF | Layout | protegida (ADMIN) | sim (Reports.tsx:1175, tela cheia) | NAO — nenhum empty state na pagina | sim (:1185) | Gerar PDF |
| /settings/projects | mesma pagina de /dashboard/projects (2a URL) | Layout | protegida | sim | sim (:892) | NAO em pagina (alert) | Novo projeto |
| /settings/campaigns | listar, pausar e ativar campanhas (home do OPERATOR) | Layout | protegida (liberada ao OPERATOR) | sim (CampaignsSettings.tsx:540) | sim (:719-721) | sim (prop na :475) | Pausar / ativar campanha |
| /settings/costs | categorias de custo operacional e imposto do mes | Layout | protegida | sim (CostsSettings.tsx:512) | sim (:1034) | NAO em pagina — so toast (:111) | Nova categoria / lancar custo |
| /settings/integrations | sites que enviam conversoes pela Meta CAPI | Layout | protegida | sim (IntegrationsSettings.tsx:141) | sim (SiteList.tsx:47) | sim (:88-116, com traducao do erro de schema) | Salvar site |
| /settings/users | usuarios, vinculos por campanha e comissoes | Layout | protegida (ADMIN; nega em :61-79) | delegado as abas v6 | delegado | delegado | Cadastrar usuario |
| /settings/cofre-ativos | inventario de ativos, custodia e credenciais | Layout | protegida (ADMIN; nega em AssetVaultPage.tsx:9-21) | NAO | NAO | NAO (nao ha leitura: fixture) | inspecionar um ativo |
| /settings/qg-agentico/tarefas/:taskId | detalhe e evidencia de uma tarefa do roadmap | Layout | protegida | sim (QgTaskPage.tsx:41) | sim (:49 "Tarefa nao encontrada") | sim (:43) + banner de leitura velha (:46) | ler a evidencia da tarefa |
| /settings/qg-agentico | QG Operacional: roadmap vivo, agora/timeline/kanban/lista/grafo/execucoes/inbox | Layout | protegida | sim (QGAgenticoPage.tsx:118) | sim (:126 catalogo vazio; :137 vazio-apos-filtro) | sim (:119) + stale banner (:101) | abrir uma tarefa |
| /settings/qd-agentico | redirect permanente para /settings/qg-agentico | n/a | n/a (Navigate, App.tsx:112) | n/a | n/a | n/a | n/a |
| /incubator | pipeline de criacao de sites para AdSense | Layout | protegida | sim (IncubatorPage.tsx:149 e :163) | sim (SiteGrid.tsx:14-21; KanbanColumn.tsx:54) | NAO | Novo Site |
| /incubator/:siteId | detalhe do site, schedule e titulos | Layout | protegida | sim (IncubatorDetailPage.tsx:171) | n/a | sim (:179-190) | disparar / pausar o pipeline |
| /pautador-pro | descoberta de entidades por pais, dores e keywords | Layout | protegida | sim (PautadorProPage.tsx:190) + skeleton de descoberta (:193) | sim (:195-206) | NAO | Disparar descoberta |
| /redator | quadro de funis: o que espera escrita, o que esta vivo | Layout | protegida | sim (RedatorPage.tsx:149) | sim (QuadroDeFunis.tsx:222 e :233) | sim mas cru, paragrafo vermelho sem glifo nem retry (:146) | Escrever o funil de um card |
| /redator/config | ler a doutrina e a configuracao do motor de redacao | Layout | protegida | sim (ConfigRedatorPage.tsx:114) | n/a | sim, paragrafo vermelho cru (:113) | leitura (somente leitura) |
| /redator/funil/:runId | matriz da execucao de um funil | Layout | protegida | sim (FunilPage.tsx:223) | sim para endereco invalido (:225-230) | sim, paragrafo vermelho cru (:224) + erro do run (:316) | publicar / reler no WordPress |
| /redator/funil/:runId/p/:n | uma pagina do funil, com prova e publicacao | Layout | protegida | sim (PaginaDoFunilPage.tsx:144) | n/a | sim, paragrafo cru (:143, :421, :536) | Publicar a pagina no WordPress |
| /trafego | Hub de Trafego: inventario, oportunidades e atencao | Layout | protegida | sim (esqueleto por aba; QuadroDeOportunidades.tsx:159) | sim (:213 e :480 "Nenhum funil publicado ainda") | sim, com distincao falhou-com-dado-bom (:161 e :165-170) | Atualizar tudo / preparar campanha |
| /trafego/laboratorio/inteligencia/:scenarioId | laboratorio de decisao por cenario | Layout | protegida | delegado (DecisionIntelligenceLabPage.tsx:21) | delegado | delegado (:23) | escolher o cenario |
| /trafego/campanhas/:volcCampaignId | pagina canonica da campanha (entrega, evidencia, diagnostico) | Layout | protegida | sim (CampanhaCanonPage.tsx:76 e skeleton :401-410) | sim, "nao encontrada" distinta de indisponivel (:82 / :95) | sim (:86, EstadoIndisponivel) | diagnosticar / agir sobre a campanha |
| /trafego/nova/:opportunityId | cockpit de criacao de campanha Search | Layout | protegida | sim (NovaCampanhaPage.tsx:452, Esqueleto) | n/a | sim (:447-451, bloco destrutivo com borda) | Lancar a campanha |
| /criativos | home do Estudio Criativo | Layout | protegida (+ Suspense com spinner, App.tsx:68-81) | sim (EstudioHomePage.tsx:123, :153, :178, :198, :220) | sim (:133, :163, :208) | sim (:108) | criar uma peca |
| /criativos/novo | mesma home com o seletor de tipo ja aberto | Layout | protegida | sim | sim | sim | escolher imagem ou video |
| /criativos/imagens/novo | briefing de imagem em etapas | Layout | protegida | sim no envio (:329-337) | n/a (formulario) | sim (:301-310, com codigo da falha) | Gerar as pecas |
| /criativos/videos/novo | briefing de video a partir de um build observado | Layout | protegida | sim (BriefingDeVideoPage.tsx:51, :71) | sim (:107 "Nenhum build observado neste ambiente") | sim (:73) + Indisponivel (:82) | escolher o build |
| /criativos/videos/:buildSlug | leitura de um build de video | Layout | protegida | sim (LeituraDeVideoPage.tsx:32) | n/a | sim (:34) | ler o build |
| /criativos/jobs/:creativeJobId | acompanhar um trabalho criativo peca a peca | Layout | protegida | sim (JobPage.tsx:85, :162) | n/a | sim (:101, :169, :231) | Interromper / preencher as pecas que faltaram |
| /criativos/laboratorio | montar a RECEITA que varias pecas reusam | NENHUM | protegida | sim (LaboratorioPage.tsx:55) | NAO | sim (:57-64, com aoTentarDeNovo) | montar a receita |
| /criativos/templates | redirect permanente para /criativos/laboratorio | n/a | n/a (Navigate, App.tsx:146) | n/a | n/a | n/a | n/a |
| /criativos/biblioteca | biblioteca de ativos produzidos | Layout | protegida | sim (BibliotecaPage.tsx:117) | sim, com vazio e vazio-apos-filtro separados (:129 e :136) | sim (:120) | filtrar e abrir um ativo |
| /criativos/assets/:assetId | detalhe, versoes e uso de um ativo | Layout | protegida | sim (AtivoPage.tsx:48) | n/a (detalhe) | sim (:64-77) | decidir sobre o ativo |
| /criativos/aprovacoes | fila de pecas aguardando decisao | Layout | protegida | sim (AprovacoesPage.tsx:137) | sim (:151-154) | sim (:139-145) | aprovar / pedir ajuste / rejeitar |
| /criativos/brand-packs | brand packs disponiveis para os briefings | Layout | protegida | sim (BrandPacksPage.tsx:63) | sim (:145) | sim (:64-68) | criar brand pack |
| /admin/v6 | fallback tecnico de RBAC (memberships, comissoes, payouts) | Layout | protegida + feature flag isV6Enabled() | delegado (V6AdminPage.tsx:134-142); Suspense da rota tem fallback={null} | delegado | delegado (:143, :148) + ForbiddenView (:42) | gerir memberships e comissoes |
| * | 404, rota nao encontrada | NENHUM | PUBLICA (fora do ProtectedRoute) | n/a | n/a | n/a | Voltar ao inicio (<a href="/">, recarrega a app) |

## O que a matriz revelou

### Estado ausente, não "não se aplica"

| rota | falta | consequência |
|---|---|---|
| `/reports` | **vazio** | nenhum estado vazio na página inteira |
| `/settings/cofre-ativos` | **loading, vazio e erro** | serve fixture; não há leitura para falhar — ainda |
| `/incubator` | **erro** | uma leitura que falha vira "nenhum item" |
| `/pautador-pro` | **erro** | idem |
| `/criativos/laboratorio` | **vazio** | — |
| `/test` | **vazio** | e o loading é só texto no H1 |
| `/dashboard/projects` · `/settings/projects` | **erro em página** | usa `alert()` nativo com a mensagem crua do Postgres |
| `/settings/costs` | **erro em página** | só um toast, com a mensagem crua do banco |

### Permissão negada não é um estado, é um desvio

`ProtectedRoute.tsx:48` redireciona o OPERATOR para `/settings/campaigns` em
cerca de 25 rotas, **sem dizer nada**. O `design.md` pede o contrário:
*"Explain why an action is unavailable and what prerequisite is missing."*
Duas rotas fazem certo e servem de modelo: `/settings/users` (nega em `:61-79`)
e `/settings/cofre-ativos` (`AssetVaultPage.tsx:9-21`).

### Três rotas sem o shell

`/test`, `/criativos/laboratorio` e o catch-all `*` não usam `<Layout>`. Nas
duas primeiras é engano: perdem menu, sino de alertas e seletor de tema. No 404
é decisão discutível — ele está **fora** do `ProtectedRoute`, então um visitante
não autenticado recebe a página de erro do produto em vez de ser mandado ao
login.

### Duas URLs para a mesma página

`/dashboard/projects` e `/settings/projects` montam `ProjectsSettings`. O menu
lateral aponta para a primeira; a segunda é a que parece canônica pelo padrão
das outras rotas de configuração.

### Import morto

`src/App.tsx:12` importa `Index` e nenhuma `<Route>` a monta. Fora do App,
`src/pages/trafego/TrafegoPage.tsx` e `src/pages/dashboard/CampaignDashboard.tsx`
também não têm consumidor.
