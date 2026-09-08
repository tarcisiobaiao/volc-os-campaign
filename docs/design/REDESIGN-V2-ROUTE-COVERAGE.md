# Redesign V2 — cobertura de rotas

Inventário cruzado com `src/App.tsx` e `docs/design/INVENTARIO-DE-ROTAS.md`.
Revisão = herda tokens/shell/primitivos. Toque extra = estado ou cromo local.

| rota | revisão | toque extra | estados críticos |
|---|---|---|---|
| /login | tokens + fontes + botão aurora-action | identidade noturna (`login-root dark`); toggle 44×44; convite sem pulso | loading no botão, toast/alerta de erro |
| /change-password | tokens + fontes | identidade | loading, toast |
| / | tokens + header sem pulso falso | DataStatus honesto; erro via EstadoOperacional | loading, erro com CTA, vazio existente |
| /test | tokens | diagnóstico técnico, sem shell de propósito | parcial |
| /dashboard/projects | tokens + primitivos | `alert()` → toast (mesmo texto) | loading, vazio, erro via toast |
| /dashboard/campaign/:campaignId | tokens + EstadoOperacional | — | loading, vazio, erro |
| /dashboard/project/:projectId | tokens + primitivos | — | loading, vazio, erro |
| /reports | tokens + empty + CTA de erro | EstadoOperacional vazio e erro | loading, erro, vazio |
| /settings/projects | mesma página de /dashboard/projects | toast | idem |
| /settings/campaigns | tokens + primitivos | — | loading, vazio, erro |
| /settings/costs | tokens + erro de página | EstadoOperacional + `reloadNonce` | loading, vazio, erro em página |
| /settings/integrations | tokens + primitivos | pulso verde falso removido | loading, vazio, erro |
| /settings/users | tokens + EstadoOperacional | permissão já explícita | bloqueio, delegado às abas |
| /settings/cofre-ativos | tokens + EstadoOperacional | permissão explícita; fixture | sem leitura remota |
| /settings/qg-agentico | tokens + primitivos | — | loading, vazio, erro, stale |
| /settings/qg-agentico/tarefas/:taskId | tokens | — | loading, vazio, erro |
| /settings/qd-agentico | redirect | sem UI | n/a |
| /incubator | tokens + erro + kicker honesto | hook `error` passou a pintar | loading, vazio via grid, erro |
| /incubator/:siteId | tokens | — | loading, erro |
| /pautador-pro | tokens + EstadoOperacional | vazio/bloqueio; erro de descoberta ainda local | loading, vazio |
| /redator | tokens + EstadoOperacional | erro deixa de ser parágrafo cru | loading, vazio, erro |
| /redator/config | tokens + EstadoOperacional | — | loading, erro |
| /redator/funil/:runId | tokens + EstadoOperacional | endereço inválido distinto | loading, vazio, erro |
| /redator/funil/:runId/p/:n | tokens | erros locais preservados | loading, erro |
| /trafego | tokens + primitivos + deck mineral | query `rede`/`nivel` intacta | loading, vazio, erro, parcial |
| /trafego?rede=meta | mesma página | query preservada | demo/config via componentes existentes |
| /trafego/meta/nova | tokens | — | loading, erro, bloqueio |
| /trafego/meta/assistente-criativo | tokens | — | loading, operação |
| /trafego/meta/assistente-criativo/:projectRef | tokens | — | idem |
| /trafego/meta/:tipo/:objetoId | tokens | — | loading, vazio, erro |
| /trafego/laboratorio/inteligencia/:scenarioId | tokens | delegado | delegado |
| /trafego/campanhas/:volcCampaignId | tokens + deck mineral | — | loading, vazio, erro |
| /trafego/nova/:opportunityId | tokens + deck mineral | — | loading, erro |
| /dashboard/campaign/...?rede=meta | tokens via router | — | existentes |
| /settings/campaigns?rede=meta | tokens | — | existentes |
| /criativos | tokens + Layout | estados do Estúdio | loading, vazio, erro |
| /criativos/novo | mesma home | — | idem |
| /criativos/imagens/novo | tokens | — | envio, erro |
| /criativos/videos/novo | tokens | — | vazio, erro, indisponível |
| /criativos/videos/:buildSlug | tokens | — | loading, erro |
| /criativos/jobs/:creativeJobId | tokens | — | loading, erro |
| /criativos/laboratorio | tokens + **volta ao Layout** | vazio ainda do catálogo | loading, erro |
| /criativos/templates | redirect | n/a | n/a |
| /criativos/biblioteca | tokens | vazio e filtro | loading, vazio, erro |
| /criativos/assets/:assetId | tokens | — | loading, erro |
| /criativos/aprovacoes | tokens | — | loading, vazio, erro |
| /criativos/brand-packs | tokens | — | loading, vazio, erro |
| /admin/v6 | tokens se flag | Suspense com spinner + sr-only (worktree; `App.tsx` misturado com packs alheios) | delegado |
| * | tokens + 404 identidade | light mineral e dark via classe `dark` | n/a |

## Fora desta rodada (trabalho alheio na mesma árvore)

`/trafego/meta/packs` e `/trafego/meta/packs/:packId` existem no working tree e não entram na cobertura V2. Não foram revertidas.

## Pendências honestas

- `/test` e diagnóstico sem shell
- `/admin/v6` só existe com feature flag
- OPERATOR continua desviado em silêncio (contrato de segurança)
- `CampaignDashboard.tsx` parece morto (não importado)
- `Lancamento.tsx` permanece overlay escuro de cerimônia
- Pautador: erro de descoberta ainda é local, não page-error genérico
- Shell autenticado (sidebar + dashboard) não foi fotografado: sem sessão e sem dados externos
