# Duplicar entidade minerada + insights dirigindo o funil

**Data:** 2026-07-27 · **Área:** Pautador Pro (entity-first)

## Problema

1. A mesma entidade é usada em **sites diferentes**, e cada site precisa do seu funil e da sua
   task no ClickUp. Hoje o card é único por entidade, então rodar o segundo site significa
   minerar tudo de novo — token já gasto, jogado fora.
2. O admin às vezes sabe o direcionamento que o funil deve ter, mas não tem onde dizer isso.
   O campo **Insights** do card já existe e é o lugar natural, só que hoje ele é anotação
   passiva: não chega ao agente.

## Restrições do banco que definem o desenho

- `uq_pautador_entities_country_slug UNIQUE (country_code, slug)`
- `uq_pautador_entity_opportunities_entity UNIQUE (entity_id)` — **uma oportunidade por
  entidade**. Logo, um segundo card exige uma segunda linha de entidade.
- `pautador_entity_pains` e `pautador_entity_seed_queries` são ligados por `entity_id`
  (únicos por `entity_id + lower(nome/query)`), então a cópia leva os filhos junto.

## Decisões (acordadas)

| Tema | Decisão |
| --- | --- |
| Identificação da cópia | Campo **nome de exibição** por card, editável pelo admin. Não toca em `canonical_name` (que alimenta o tema do agente de funil e o título do DOCX). |
| Onde mora | `pautador_entity_opportunities.display_title` (mesma linha do `insights`). |
| ClickUp | Título da task vira `"{entidade} - {país} - {nome de exibição}"` quando houver nome; sem nome, idêntico a hoje. |
| Insights na cópia | Nasce **vazio**. Como o campo passa a dirigir o funil, herdar o texto aplicaria o direcionamento do site A no funil do site B sem ninguém perceber. |
| Estágio da cópia | Sempre `mining` ("Em mineração"). |

## Feature 1 — Duplicar

**Migração `v7_12`** (aditiva, idempotente): `ADD COLUMN IF NOT EXISTS display_title text`.
Defensiva no padrão do `niche_slug`: se a migração ainda não rodou, a duplicação funciona e
devolve um warning, em vez de estourar 502 pelo PostgREST.

**Endpoint** `POST /api/pautador/entity-opportunities/{opp_id}/duplicate`, body
`{ "display_title": "Site XPTO" }` (opcional). O backend:

1. Carrega a oportunidade, a entidade e o card completo (dores + seed queries).
2. Cria a entidade cópia: todos os metadados iguais, `slug` no primeiro sufixo livre
   (`-v2`, `-v3`, …), `status = "mining"`.
3. Cria a oportunidade cópia: métricas da mineração preservadas
   (`score`, `gold_tier`, `strategic_stage`, `estimated_volume`, `ecpm_band`, `roi_signal`,
   `cpc_*`, `*_level`, `temporal_window`, `concrete_pain`, `gold_reason`),
   `status/kanban_stage = "mining"`, `display_title` informado,
   `insights = NULL`, sem `clickup_task_id/url`, sem `funnel_architecture`,
   `funnel_completed = false`.
4. Copia dores e seed queries apontando para a entidade nova.
5. Devolve o card no mesmo formato de `list_entity_cards`.

**Front:** botão direito no card (Radix ContextMenu — já é dependência) → "Duplicar para
outro site" → diálogo pede o nome de exibição → card aparece em "Em mineração". O nome de
exibição também é editável depois, no drawer. O card exibe o nome de exibição como título e
o `canonical_name` como subtítulo.

Botão direito não conflita com o arraste: o `PointerSensor` do dnd-kit só ativa com
`button === 0`.

**Efeito colateral avaliado e aceito:** a entidade passa a existir duas vezes na tabela. A
lista de exclusão da descoberta deduplica por `canonical_name`, então o prompt não repete; e
`find_matching_entity` casa com a primeira ocorrência, então runs futuras não criam uma
terceira.

## Feature 2 — Insights dirigindo o funil

O endpoint do funil já carrega a linha da oportunidade, onde o `insights` está. O texto
desce por `EntityFunnelOrchestrator` → `FunnelProOrchestrator` e entra como bloco
`## DIRECIONAMENTO DO ADMIN` no **user message** do arquiteto.

**Não** no system message: `FUNNEL_ARCHITECT_SYSTEM_MESSAGE` é o prompt do n8n copiado
*ipsis litteris* (declarado assim no código) — alterá-lo arrisca o funil inteiro. O bloco no
fim da missão tem o mesmo efeito e é isolável.

- Texto vazio ⇒ prompt idêntico ao de hoje, byte a byte.
- Limite de 4000 caracteres, para uma anotação longa não empurrar o resto do contexto.
- O revisor de funil (backstop factual) **não** recebe o direcionamento: ele valida fatos da
  entidade, e misturar instrução de estilo ali enfraquece a checagem.
- Fallback determinístico (sem chave Gemini) ignora o direcionamento — não há como aplicar.

**Zero mudança de front no disparo** (o `insights` já é salvo e o funil já é acionado pelo
id da oportunidade). Muda só o texto de ajuda do campo, que hoje diz "anotações livres" e
passa a avisar que o conteúdo vira direcionamento do agente de funil.

## Achado durante a implementação (fora do escopo original)

A verificação viva mostrou a cópia nascendo com **0 seed queries** — mas as 15 linhas
*estavam* no banco. Causa: o PostgREST do Supabase corta toda resposta em
`db-max-rows` (1000 neste projeto) e **ignora um `limit` maior** — `limit=5000`
devolve 1000 linhas, sem erro.

Não era bug da duplicação: `list_entity_cards` já truncava em produção. BR tem 1309
seed queries, então **309 sumiam do board** — sempre as dos cards mais recentes
(justamente os recém-minerados). Corrigido com `select_all` paginado
(`SupabaseService`), usado em `list_entities` e nos filhos de `list_entity_cards`.
Depois da correção, a API devolve 1309/1309 queries e 434/434 dores.

## Testes

- Cópia nasce em `mining`, com `insights` vazio, sem ClickUp e sem funil.
- Colisão de slug resolve para o próximo sufixo livre.
- Dores e seed queries chegam na entidade nova.
- Bloco de direcionamento presente com texto e **ausente** quando vazio.
- Título da task do ClickUp com e sem nome de exibição.
- Suíte existente (170 testes) verde.
