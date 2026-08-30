# Pautador Pro — Nicho, Idioma e Qualidade de Funil — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar direcionamento de nicho e sazonalidade à descoberta do Pautador Pro, corrigir o vazamento de idioma, e elevar a qualidade do funil (intro/fechamento, sem datas, tom informacional, revisor invisível, profundidade e grounding semântico anti-branco) — sem quebrar o fluxo atual.

**Architecture:** Fluxo *entity-first* 100% no backend Python (`webgo/backend`). Descoberta e funil chamam o Gemini via `GeminiClient` (stateless). Mudanças concentradas em: contratos (SQL/Pydantic/TS), prompt de descoberta, prompt do arquiteto de funil, um novo agente revisor, e os seletores no frontend.

**Tech Stack:** FastAPI + Pydantic v2 + httpx (Gemini) no backend; React + Vite + TypeScript no frontend; Supabase/Postgres (PostgREST via `SupabaseService`); pytest.

**Spec:** `docs/superpowers/specs/2026-07-23-pautador-pro-nicho-idioma-funil-design.md` (fonte da verdade — consulte para contexto e critérios de aceitação).

## Global Constraints

- **Lockstep de contrato:** toda coluna nova exige edição casada em SQL (`src/sql/v7_xx`), Pydantic (`backend/app/entities/schemas.py`), tipos do front (`src/types/pautadorEntity.ts`) e whitelist do router (`backend/app/routers/entities.py` `_OPP_COLS`). **Nunca** use `_OPP_COLUMNS` de `supabase_service.py` (é da tabela legada `pautador_opportunities`).
- **Backward-compatible:** com `niches=[]` e `seasonality=None`, a descoberta se comporta EXATAMENTE como hoje (diversificada). Nenhum comportamento atual pode regredir.
- **Sistema vivo = entity-first.** Não tocar no fluxo legado keyword-first (`agents/orchestrator.py`, `agents/mining/*`, `/discovery` `/mine` `/funnel` do `routers/pautador.py`) nem no `CriticValidatorAgent` de seeds.
- **`GeminiClient` é stateless** — não existe cache para "resetar"; idioma é corrigido forçando o locale nos prompts, não limpando estado.
- **Temperatura 0.9:** edições só-de-prompt (datas R5, tom R6) são reforçadas pelo revisor (R7) como backstop determinístico; nunca confie só no prompt.
- **Revisor R7 é invisível** (só logs) e **fail-open** (se falhar/timeout, entrega o funil original). Deve rodar **antes** de `apply_roles_and_slugs`.
- **Valores de idioma (R3):** locale forçado vem de `resolve_country(...)["native_language"]` (`backend/app/data/countries.py`) — é o locale COMPLETO (ex.: Brasil→`pt-BR`, Rep. Dominicana→`es-DO`). NÃO use `language_code`/`language_short` (só o ISO de 2 letras `pt`/`es`). Confirmado na Task 5.
- **Valores de sazonalidade:** request `seasonality ∈ {"evergreen","seasonal"}`; mapeia para `temporal_window` (`evergreen`→`Perene`; `seasonal`→`Sazonal`/`Evento`).
- **Idioma da base de código:** PT-BR em comentários, mensagens e prompts.

---

## File Structure

- `src/sql/v7_11_pautador_niches.sql` — **Create**: tabela `pautador_niches` + seed + coluna `pautador_entities.niche_slug`.
- `backend/app/entities/schemas.py` — **Modify**: `EntityDiscoveryRequest` (+`niches`,`seasonality`); `EntitySpec`/`EntityCardEntity` (+`niche_slug`).
- `src/types/pautadorEntity.ts` — **Modify**: params de request + `niche_slug` + campos de página `intro_section`/`closing_section`.
- `backend/app/data/niches.py` — **Create**: constantes-seed dos nichos (fallback quando Supabase off) + helpers de resolução.
- `backend/app/services/supabase_service.py` — **Modify**: `list_niches` / `insert_niche`.
- `backend/app/routers/entities.py` — **Modify**: endpoints `GET/POST /niches`; threading de `niches`/`seasonality`; whitelist+insert de `niche_slug`; render de intro/closing no DOCX (Task 11).
- `backend/app/entities/prompts.py` — **Modify**: system prompt + `build_entity_discovery_mission` (nicho, sazonalidade, idioma forçado).
- `backend/app/entities/orchestrator.py` — **Modify**: `EntityDiscoveryOrchestrator` (resolver nicho/idioma, descarte); `EntityFunnelOrchestrator` (grounding semântico, idioma, wiring do revisor).
- `backend/app/entities/mock.py` — **Modify**: mocks honram nicho/sazonalidade/idioma.
- `backend/app/n8n_prompts/funnel_builder.py` — **Modify**: intro/closing no schema, remover `[ano]`, tom informacional, min H2/anti-linguiça.
- `backend/app/agents/funnel_pro/orchestrator.py` — **Modify**: idioma forçado; grounding semântico; remover fallback genérico silencioso.
- `backend/app/agents/funnel_pro/page_factory.py` — **Modify**: propagar intro/closing.
- `backend/app/agents/funnel_pro/reviewer.py` — **Create**: agente revisor R7.
- `backend/app/docx/funnel_briefing.py` — **Modify**: render de intro/closing.
- `src/lib/pautadorApi.ts` — **Modify**: `entityDiscovery` params; `niches()`/`createNiche()`.
- `src/hooks/pautador/useEntityPautador.ts` — **Modify**: estado de nicho/sazonalidade; `runDiscovery`.
- `src/pages/pautador-pro/PautadorProPage.tsx` — **Modify**: multiselect de nicho + toggle sazonal + modal "+ nicho".

---

## PHASE 0 — Contratos & dados (barreira — tudo depende)

### Task 1: Migração SQL v7_11 (nichos + coluna niche_slug)

**Files:**
- Create: `src/sql/v7_11_pautador_niches.sql`

**Interfaces:**
- Produces: tabela `public.pautador_niches(id, slug, label, guidance, allowed_verticals text[], is_active, sort_order, created_at, updated_at)`; coluna `public.pautador_entities.niche_slug text`.

- [ ] **Step 1: Escrever a migração** (idempotente; siga o padrão de RLS/grants das migrações `src/sql/v7_03`…`v7_10` — leia uma delas antes para copiar o estilo de policy e grant usado no projeto).

```sql
-- v7_11_pautador_niches.sql — nichos selecionáveis (R1) + tag de nicho na entidade
create table if not exists public.pautador_niches (
  id                bigserial primary key,
  slug              text not null unique,
  label             text not null,
  guidance          text not null default '',
  allowed_verticals text[] not null default '{}',
  is_active         boolean not null default true,
  sort_order        int not null default 0,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

alter table public.pautador_entities
  add column if not exists niche_slug text;

insert into public.pautador_niches (slug,label,guidance,allowed_verticals,sort_order) values
 ('beneficios_sociais','Benefícios sociais','Programas de transferência de renda, auxílios, bolsas, pensões e amparo social — foco em quem recebe/solicita. NÃO incluir tributos, documentos ou serviços administrativos genéricos.', array['gov_beneficios'],10),
 ('servicos_governo','Serviços do governo','Órgãos, sistemas, documentos, obrigações e serviços públicos (emissão, consulta, agendamento, cadastros). NÃO confundir com benefícios de renda.', array['gov_beneficios'],20),
 ('educacao','Educação','Matrículas, bolsas, financiamento estudantil, vestibulares, cursos e certificações.', array['educacao'],30),
 ('emprego','Emprego','Carreira, trabalho, vagas, trabalho por/em aplicativos, direitos trabalhistas, concursos e qualificação.', array['empregos_concursos'],40),
 ('financas','Finanças','Crédito, empréstimo, financiamento, investimentos, seguros, impostos e apps financeiros.', array['financas','credito','seguros'],50),
 ('aplicativos','Aplicativos','Apps de alto uso e dúvidas utilitárias (como funciona, cadastro, recuperar acesso, tarifas), com ângulo informacional de publisher.', array['tecnologia'],60)
on conflict (slug) do nothing;
```

- [ ] **Step 2: Adicionar RLS + grants** espelhando `pautador_countries` (SELECT para `authenticated`/`anon` conforme o padrão do projeto; writes via service-role). Copie o bloco de `alter table ... enable row level security` + `create policy` da migração de `pautador_countries` e adapte o nome da tabela.

- [ ] **Step 3: Verificar idempotência** — reler o arquivo: todo DDL usa `if not exists` / `on conflict do nothing`; rodar duas vezes não quebra. (Sem runner de SQL no CI — verificação é revisão do DDL.)

- [ ] **Step 4: Commit**

```bash
git add src/sql/v7_11_pautador_niches.sql
git commit -m "feat(pautador-pro): migração v7_11 pautador_niches + niche_slug (R1)"
```

**Nota ao operador:** esta migração precisa ser aplicada no Supabase manualmente (como as anteriores), no mesmo lockstep dos demais `v7_xx`. O `GET /api/pautador/niches` cai para as constantes-seed quando a tabela não existe — mas isso **não** cobre o fluxo inteiro: uma run de descoberta **persistida** com um nicho selecionado (`niches=[...]`) grava `pautador_entities.niche_slug`, que só existe a partir desta migração, e falha (502) sem ela. Runs diversificadas (`niches=[]`, comportamento padrão) continuam seguras pré-migração — o insert de `pautador_entities` omite `niche_slug` quando a entidade não tem nicho (ver `routers/entities.py`). Aplique a v7_11 **antes de** (ou junto com) este deploy.

---

### Task 2: Contratos Pydantic + TS (request, niche_slug, intro/closing)

**Files:**
- Modify: `backend/app/entities/schemas.py`
- Modify: `src/types/pautadorEntity.ts`
- Test: `backend/tests/test_entity_contracts.py` (Create)

**Interfaces:**
- Consumes: nada.
- Produces: `EntityDiscoveryRequest.niches: List[str]`, `EntityDiscoveryRequest.seasonality: Optional[Literal["evergreen","seasonal"]]`; `EntitySpec.niche_slug: Optional[str]` (e o mirror em `EntityCardEntity`). No TS: `EntityDiscoveryParams` com `niches?: string[]; seasonality?: 'evergreen'|'seasonal'`; `EntityCard`/entity com `niche_slug?: string|null`; página do funil com `intro_section?: string; closing_section?: string`.

- [ ] **Step 1: Escrever o teste** `backend/tests/test_entity_contracts.py`

```python
from app.entities.schemas import EntityDiscoveryRequest, EntitySpec

def test_discovery_request_accepts_niches_and_seasonality():
    r = EntityDiscoveryRequest(country="Brasil", niches=["financas"], seasonality="evergreen")
    assert r.niches == ["financas"]
    assert r.seasonality == "evergreen"

def test_discovery_request_defaults_are_backward_compatible():
    r = EntityDiscoveryRequest(country="Brasil")
    assert r.niches == []
    assert r.seasonality is None

def test_seasonality_rejects_invalid():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EntityDiscoveryRequest(country="Brasil", seasonality="quarterly")

def test_entity_spec_has_niche_slug():
    e = EntitySpec(canonical_name="RUT", niche_slug="servicos_governo")  # ajuste kwargs obrigatórios conforme o schema real
    assert e.niche_slug == "servicos_governo"
```

- [ ] **Step 2: Rodar o teste — deve FALHAR** (`cd backend && python -m pytest tests/test_entity_contracts.py -v`) com erro de campo inexistente.

- [ ] **Step 3: Implementar os campos** em `entities/schemas.py` (ler o arquivo primeiro; `EntityDiscoveryRequest` fica ~linha 85, `EntitySpec.vertical` ~linha 22). Adicionar `niches`/`seasonality` no request; `niche_slug: Optional[str] = None` em `EntitySpec` e no card. Se existir um modelo Pydantic de página de funil, adicionar `intro_section`/`closing_section`; se páginas forem `dict`/jsonb livre, apenas garantir que os campos passam intactos (documentar).

- [ ] **Step 4: Atualizar `src/types/pautadorEntity.ts`** — adicionar os campos correspondentes (ler o arquivo; manter os nomes idênticos ao backend).

- [ ] **Step 5: Rodar o teste — deve PASSAR** (`python -m pytest tests/test_entity_contracts.py -v`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/entities/schemas.py src/types/pautadorEntity.ts backend/tests/test_entity_contracts.py
git commit -m "feat(pautador-pro): contratos de nicho/sazonalidade + niche_slug + intro/closing (R1/R2/R4)"
```

---

## PHASE 1 — Descoberta (R1, R2, R3-idioma)

### Task 3: Nichos — seed constants, SupabaseService, endpoints

**Files:**
- Create: `backend/app/data/niches.py`
- Modify: `backend/app/services/supabase_service.py`
- Modify: `backend/app/routers/entities.py` (apenas os endpoints novos)
- Test: `backend/tests/test_niches_endpoint.py` (Create)

**Interfaces:**
- Produces: `app.data.niches.SEED_NICHES: list[dict]` (mesmos 6 slugs/label/guidance/allowed_verticals da migração) e `resolve_niches(slugs, db_rows=None) -> list[dict]`. `SupabaseService.list_niches() -> list[dict]`, `SupabaseService.insert_niche(payload) -> dict`. Router: `GET /api/pautador/niches` → `{niches:[...], source:"supabase"|"seed"}`; `POST /api/pautador/niches` (body: slug,label,guidance,allowed_verticals) → `{niche:{...}}`.

- [ ] **Step 1: Escrever `backend/app/data/niches.py`** com `SEED_NICHES` (espelhando a migração) + `resolve_niches(slugs, db_rows=None)` que filtra por slug, usando `db_rows` quando fornecido senão `SEED_NICHES`.

- [ ] **Step 2: Escrever o teste** `backend/tests/test_niches_endpoint.py` usando o `TestClient` do FastAPI (siga o padrão de `backend/tests/test_api_kw_funnel.py`). Assert: `GET /api/pautador/niches` retorna ≥6 nichos com `source` em `{supabase,seed}`; cada item tem `slug,label,guidance,allowed_verticals`.

- [ ] **Step 3: Rodar — FALHA** (404 no endpoint).

- [ ] **Step 4: Implementar** `list_niches`/`insert_niche` em `SupabaseService` (siga o padrão de `select`/`insert` já usado; tabela `pautador_niches`, filtro `is_active=eq.true`, `order=sort_order.asc`). No `routers/entities.py`, adicionar os dois endpoints; `GET` tenta Supabase e faz fallback para `SEED_NICHES` (fonte `"seed"`); `POST` exige Supabase (503 se off) e usa `require_api_key` como os outros mutadores.

- [ ] **Step 5: Rodar — PASSA.**

- [ ] **Step 6: Commit** `feat(pautador-pro): tabela de nichos com fallback seed + endpoints GET/POST /niches (R1)`

---

### Task 4: Prompt de descoberta — nicho, sazonalidade, idioma forçado

**Files:**
- Modify: `backend/app/entities/prompts.py`
- Test: `backend/tests/test_discovery_mission.py` (Create)

**Interfaces:**
- Consumes: nada novo.
- Produces: assinatura nova `build_entity_discovery_mission(country, count=20, today="", exclude_entities=None, market_tier="", niches=None, seasonality=None, forced_language=None) -> str` (`niches` = lista de dicts resolvidos com `label`/`guidance`).

- [ ] **Step 1: Escrever o teste** `backend/tests/test_discovery_mission.py`:

```python
from app.entities.prompts import build_entity_discovery_mission

def test_mission_without_niche_keeps_diversification():
    m = build_entity_discovery_mission("Brasil")
    assert "DIVERSIFIQUE" in m or "diversif" in m.lower()

def test_mission_with_niche_focuses_and_injects_guidance():
    niches = [{"slug":"financas","label":"Finanças","guidance":"Crédito, empréstimo, investimentos."}]
    m = build_entity_discovery_mission("Brasil", niches=niches)
    assert "Finanças" in m
    assert "Crédito, empréstimo, investimentos." in m
    assert "diversif" not in m.lower()  # a diversificação obrigatória some quando há nicho

def test_mission_seasonality_evergreen_bias():
    m = build_entity_discovery_mission("Brasil", seasonality="evergreen")
    assert "Perene" in m

def test_mission_forces_language():
    m = build_entity_discovery_mission("República Dominicana", forced_language="es-DO")
    assert "es-DO" in m
    assert "detecte" not in m.lower()  # não pede mais para o modelo detectar
```

- [ ] **Step 2: Rodar — FALHA.**

- [ ] **Step 3: Implementar** (ler `prompts.py` inteiro primeiro):
  - Estender a assinatura de `build_entity_discovery_mission`.
  - Quando `niches` preenchido: montar um bloco `## 🎯 NICHOS-ALVO (FOCO EXCLUSIVO)` com os `label`+`guidance`, instruir *"Traga SOMENTE tópicos destes nichos e vá FUNDO neles"*, instruir o modelo a preencher `entity.niche_slug` com um dos slugs fornecidos, e **suprimir** a linha "DIVERSIFIQUE as verticais / NÃO concentre" (que hoje vem do system prompt e é repetida no mission ~linha 137-139) — no mission, substituir por foco; no `ENTITY_DISCOVERY_SYSTEM_PROMPT`, tornar a regra 2 condicional NÃO é possível (prompt é constante) → em vez disso, no mission adicionar override explícito: *"IGNORE qualquer instrução anterior de diversificar: nesta run o foco é EXCLUSIVO nos nichos acima."*
  - Quando `seasonality`: adicionar diretriz forte (`evergreen`→"priorize `temporal_window`=Perene"; `seasonal`→"priorize Sazonal/Evento e janelas reais").
  - Quando `forced_language`: substituir a linha `IDIOMA NATIVO: (detecte…)` por `IDIOMA NATIVO OBRIGATÓRIO: {forced_language} — todos os campos de idioma nativo DEVEM sair em {forced_language}; NÃO use outro idioma.`
  - Adicionar `niche_slug` ao schema JSON de saída documentado no system prompt (campo dentro de `entity`).

- [ ] **Step 4: Rodar — PASSA.**

- [ ] **Step 5: Commit** `feat(pautador-pro): mission de descoberta com foco de nicho, sazonalidade e idioma forçado (R1/R2/R3)`

---

### Task 5: Orchestrator de descoberta + mocks + threading no router

**Files:**
- Modify: `backend/app/entities/orchestrator.py` (apenas `EntityDiscoveryOrchestrator` + `_norm_item`)
- Modify: `backend/app/entities/mock.py`
- Modify: `backend/app/routers/entities.py` (endpoint discovery: passar `niches`/`seasonality`; insert de `niche_slug` + whitelist)
- Test: `backend/tests/test_discovery_filter.py` (Create)

**Interfaces:**
- Consumes: `build_entity_discovery_mission(...niches, seasonality, forced_language)` (Task 4); `resolve_niches` + `SupabaseService.list_niches` (Task 3); `resolve_country(...).language_code` (existente); `EntityDiscoveryRequest.niches/seasonality` (Task 2).
- Produces: entidades com `niche_slug` preenchido e filtradas por nicho/sazonalidade; `warnings` com contagem de descartes.

- [ ] **Step 1: Escrever o teste** `backend/tests/test_discovery_filter.py` — usar engine mock (sem chave Gemini). Assert: (a) com `niches=["financas"]`, entidades cujo `niche_slug`/`vertical` fora do conjunto são descartadas; (b) com `seasonality="evergreen"`, entidades `temporal_window!="Perene"` são descartadas; (c) `forced_language` é passado para o mission (pode-se checar via warnings/meta ou monkeypatch do builder); (d) sem filtros, nenhuma entidade é descartada (backward-compat). Ajustar o mock em `mock.py` para produzir entidades com verticais/`temporal_window` variados e aceitar os novos parâmetros.

- [ ] **Step 2: Rodar — FALHA.**

- [ ] **Step 3: Implementar:**
  - `EntityDiscoveryOrchestrator.run`: resolver `forced_language = resolve_country(country, code).get("language_code")`; resolver nichos selecionados via `SupabaseService.list_niches()` (fallback `resolve_niches`); passar `niches`/`seasonality`/`forced_language` ao `build_entity_discovery_mission`. Após normalizar, se `niches` setado, descartar entidades cujo `niche_slug` não está no conjunto (fallback: `vertical` fora da união de `allowed_verticals`); se `seasonality`, descartar `temporal_window` incompatível. Acumular `warnings` (`"N entidades descartadas fora do nicho/estação"`).
  - `_norm_item`: propagar `niche_slug` do item do LLM para o dict da entidade.
  - `mock.py`: `mock_entity_discovery` aceita e honra `niches`/`seasonality`/`forced_language`.
  - `routers/entities.py` discovery endpoint: repassar `req.niches`/`req.seasonality` ao orchestrator; adicionar `niche_slug` ao insert de `pautador_entities` e ao whitelist `_OPP_COLS`/colunas de entidade (o que for pertinente à tabela de entidade).

- [ ] **Step 4: Rodar — PASSA.** Rodar também `test_entity_contracts.py` e a suíte de descoberta existente para garantir não-regressão.

- [ ] **Step 5: Commit** `feat(pautador-pro): descoberta com foco de nicho + filtro sazonal + idioma forçado + persist niche_slug (R1/R2/R3)`

---

## PHASE 2 — Arquiteto de funil (R3-idioma, R4, R5, R6, R8, R9)

### Task 6: Prompt do arquiteto — intro/closing, sem datas, tom, profundidade

**Files:**
- Modify: `backend/app/n8n_prompts/funnel_builder.py`
- Test: `backend/tests/test_funnel_prompt.py` (Create)

**Interfaces:**
- Consumes: `build_funnel_architect_user(...)` já recebe `lingua`/`data_atual` (mantém assinatura).
- Produces: schema de saída por página inclui `intro_section` e `closing_section`; H1 sem `[ano]`; regras de tom + lista de frases banidas; regra de min. H2 por página de solução.

- [ ] **Step 1: Escrever o teste** `backend/tests/test_funnel_prompt.py`:

```python
from app.n8n_prompts import funnel_builder as fb

def test_output_schema_has_intro_and_closing():
    sys = fb.FUNNEL_ARCHITECT_SYSTEM_MESSAGE  # ajuste ao nome real da constante
    assert "intro_section" in sys
    assert "closing_section" in sys

def test_no_year_token_in_h1_templates():
    sys = fb.FUNNEL_ARCHITECT_SYSTEM_MESSAGE
    assert "[ano]" not in sys and "{ano}" not in sys

def test_banned_phrases_present():
    sys = fb.FUNNEL_ARCHITECT_SYSTEM_MESSAGE
    assert "PROIBIDO" in sys  # bloco de tom/regra anti-alarmismo
```

- [ ] **Step 2: Rodar — FALHA.**

- [ ] **Step 3: Implementar** (ler o arquivo inteiro; é o prompt verbatim do arquiteto):
  - **R4:** adicionar `intro_section` (introdução provocativa que engaja o leitor, antes dos H2) e `closing_section` (fecha a solução DAQUELA página, sem CTA para a próxima página) ao schema JSON de saída (~linhas 818-857) e às instruções de composição da página (~340-348). Deixar explícito que `hook_to_next_page`/`next_page_slug` continuam como metadado estrutural de link interno, **não** como CTA no `closing_section`.
  - **R5:** remover os tokens `([ano])`/`[ano]` dos templates de H1 (~342, ~495, ~123) e adicionar regra inviolável *"PROIBIDO incluir ano ou data em qualquer `h1_title`"*.
  - **R6:** reescrever o bloco `psychology_engine`/"4 MEDOS UNIVERSAIS" (~45-69) e as `FORMULAs` de hook (~537-589) para um frame **informacional/benefício** (mantém persuasão por clareza/utilidade, corta medo e urgência falsa); trocar exemplos com stats exageradas (ex.: "elimina 73%…", "60% eliminados"). Adicionar bloco `## ⚖️ TOM (PROIBIÇÕES)` com lista de frases/padrões banidos: `"em X segundos"`, percentuais sem fonte, `"garantido"`, linguagem de medo/compulsão.
  - **R8:** exigir mínimo de **4 H2 substantivos** por página de solução + instrução anti-"linguiça" (cada H2 cobre subtópico distinto e útil) + autoquestionamento *"esta página é necessária? Se for rasa (ex.: só 'como entrar em contato'), funda com outra."*

- [ ] **Step 4: Rodar — PASSA.**

- [ ] **Step 5: Commit** `feat(pautador-pro): arquiteto com intro/fechamento, sem datas, tom informacional e profundidade mínima (R4/R5/R6/R8)`

---

### Task 7: funnel_pro — idioma forçado, grounding semântico, sem fallback silencioso

**Files:**
- Modify: `backend/app/agents/funnel_pro/orchestrator.py`
- Modify: `backend/app/agents/funnel_pro/page_factory.py`
- Test: `backend/tests/test_funnel_grounding.py` (Create)

**Interfaces:**
- Consumes: `FunnelProOrchestrator(ctx, model_override=..., forced_language=...)` (novo kwarg opcional); páginas do arquiteto com `intro_section`/`closing_section`.
- Produces: `_supporting_data`/`_user_questions` nunca colapsam para só o main_keyword; `FunnelPage`/writing job carregam `intro_section`/`closing_section`.

- [ ] **Step 1: Escrever o teste** `backend/tests/test_funnel_grounding.py`: (a) `_supporting_data` com cluster vazio mas `opportunity` rico (description, pains, seed_queries) retorna base semântica não-trivial (mais que `- {main_keyword}`); (b) `architect_pages_to_funnel_pages` propaga `intro_section`/`closing_section` para a `FunnelPage`; (c) `forced_language` é interpolado no user prompt (monkeypatch/captura do `complete_json`).

- [ ] **Step 2: Rodar — FALHA.**

- [ ] **Step 3: Implementar:**
  - `FunnelProOrchestrator.__init__` aceita `forced_language`; usa-o no lugar de `opportunity.native_language` ao montar `lingua` para `build_funnel_architect_user` (fallback para `native_language` se não vier).
  - `_supporting_data`/`_user_questions` (~41-66): incorporar `description`, `reasoning`, `pains`(nome+descrição+user_goal), `seed_queries`, `variations`(aliases), `expansion_hooks`(related_systems/pains) — montar base semântica rica; nunca reduzir a `- {main_keyword}`.
  - Remover o fallback silencioso de 5 páginas genéricas (~88-94/121-157): se o arquiteto vier vazio, **re-tentar uma vez** enfatizando a base semântica; se ainda vazio, retornar warning explícito (sem template genérico mascarado).
  - `page_factory.py`: `architect_pages_to_funnel_pages` (~90) e o skeleton do writer (~34-38/68) passam a incluir `intro_section`/`closing_section`.

- [ ] **Step 4: Rodar — PASSA.** Rodar `backend/tests/test_funnel_roles.py` (não-regressão).

- [ ] **Step 5: Commit** `feat(pautador-pro): funil com idioma forçado, grounding semântico anti-branco e intro/fechamento propagados (R3/R4/R9)`

---

### Task 8: EntityFunnelOrchestrator — montar base semântica + idioma

**Files:**
- Modify: `backend/app/entities/orchestrator.py` (apenas `EntityFunnelOrchestrator`)
- Test: `backend/tests/test_entity_funnel_semantic.py` (Create)

**Interfaces:**
- Consumes: `FunnelProOrchestrator(..., forced_language=...)` (Task 7); entidade com `pains`/`seed_queries`/`description`/`aliases`/`related_systems`.
- Produces: `opp_like`/`cluster_like` enriquecidos; `forced_language` resolvido via `resolve_country` da entidade.

- [ ] **Step 1: Escrever o teste** `backend/tests/test_entity_funnel_semantic.py`: com uma entidade de poucos seed_queries mas com `description`+`pains`, o `cluster_like`/`opp_like` passado ao arquiteto contém o material semântico (não vazio) e `forced_language` = locale do país da entidade.

- [ ] **Step 2: Rodar — FALHA.**

- [ ] **Step 3: Implementar** `EntityFunnelOrchestrator.run` (~259-314): resolver `forced_language = resolve_country(entity.country, entity.country_code).language_code` (fallback `entity.language`); enriquecer `opp_like` (`reasoning=description`, `variations=aliases`, `expansion_hooks=related_systems+pains`) e `cluster_like` (keywords=seed_queries, `content_seo_queue`=pains com descrição, incluir `description`/`concrete_pain`/`gold_reason` no material); instanciar `FunnelProOrchestrator(self.ctx, model_override=..., forced_language=forced_language)`.

- [ ] **Step 4: Rodar — PASSA.**

- [ ] **Step 5: Commit** `feat(pautador-pro): funil de entidade apoiado no stack semântico da descoberta + idioma do país (R3/R9)`

---

## PHASE 3 — Revisor invisível (R7)

### Task 9: Agente revisor de funil

**Files:**
- Create: `backend/app/agents/funnel_pro/reviewer.py`
- Test: `backend/tests/test_funnel_reviewer.py` (Create)

**Interfaces:**
- Produces: `class FunnelReviewer` com `async def review(self, built: dict, *, entity_facts: dict, forced_language: str) -> dict` retornando `{"pages": [...], "funnel_strategy": {...}, "changes": [...]}` (mesmo shape de `built`, corrigido). **Fail-open:** em qualquer exceção, retorna `built` inalterado com `changes=[]`.

- [ ] **Step 1: Escrever o teste** `backend/tests/test_funnel_reviewer.py` com um `ctx`/engine mock: (a) revisor devolve o mesmo shape (`pages`/`funnel_strategy`); (b) se o LLM lançar exceção, `review` retorna o `built` original (fail-open) sem propagar; (c) prompt do revisor menciona checagens de idioma, datas, tom e relevância (assert em constante do prompt).

- [ ] **Step 2: Rodar — FALHA.**

- [ ] **Step 3: Implementar** `reviewer.py`: system prompt do revisor (PT-BR) que recebe o funil + fatos da entidade (`official_source`, `related_systems`, `description`, sinais de processo automático vs manual) + `forced_language`, e devolve o funil corrigido com: correção factual/processual, idioma == `forced_language`, sem ano em títulos, tom dentro das proibições, relevância/profundidade (pode fundir/derrubar/reordenar páginas). Usa `GeminiClient.complete_json`. Envolver tudo em try/except → fail-open.

- [ ] **Step 4: Rodar — PASSA.**

- [ ] **Step 5: Commit** `feat(pautador-pro): agente revisor de funil (backstop factual/idioma/datas/tom/relevância), fail-open (R7)`

---

### Task 10: Wiring do revisor antes de apply_roles_and_slugs

**Files:**
- Modify: `backend/app/entities/orchestrator.py` (`EntityFunnelOrchestrator.run`)
- Test: `backend/tests/test_reviewer_wiring.py` (Create)

**Interfaces:**
- Consumes: `FunnelReviewer.review(...)` (Task 9).
- Produces: `built` revisado ANTES de `apply_roles_and_slugs`.

- [ ] **Step 1: Escrever o teste** `backend/tests/test_reviewer_wiring.py`: monkeypatch `FunnelReviewer.review` para marcar as páginas; assert que `apply_roles_and_slugs` recebe as páginas JÁ revisadas (ordem: architect → reviewer → roles/slugs); e que se `review` lançar, o fluxo segue com o `built` do arquiteto (fail-open, sem 500).

- [ ] **Step 2: Rodar — FALHA.**

- [ ] **Step 3: Implementar:** em `EntityFunnelOrchestrator.run`, após `architect.run(...)` e **antes** de `apply_roles_and_slugs`, chamar `FunnelReviewer(self.ctx).review(built, entity_facts=..., forced_language=forced_language)` e usar o resultado. Logar `changes` (nível debug/info) — nunca expor ao usuário. Fail-open já garantido no agente.

- [ ] **Step 4: Rodar — PASSA.** Rodar `test_funnel_roles.py` (garantir slugs/links intactos).

- [ ] **Step 5: Commit** `feat(pautador-pro): revisor roda antes de roles/slugs, invisível e fail-open (R7)`

---

## PHASE 4 — DOCX (R4)

### Task 11: Render de intro/fechamento no briefing DOCX

**Files:**
- Modify: `backend/app/docx/funnel_briefing.py`
- Modify: `backend/app/routers/entities.py` (composer que monta o DOCX a partir de `funnel_architecture.pages`)
- Test: `backend/tests/test_docx_intro_closing.py` (Create)

**Interfaces:**
- Consumes: páginas com `intro_section`/`closing_section`.
- Produces: DOCX renderiza introdução antes dos H2 e fechamento depois.

- [ ] **Step 1: Escrever o teste** `backend/tests/test_docx_intro_closing.py`: montar um `funnel_architecture` com uma página contendo `intro_section`/`closing_section`, gerar o briefing e assert que os textos aparecem no documento (checar via texto dos parágrafos do `python-docx`).

- [ ] **Step 2: Rodar — FALHA.**

- [ ] **Step 3: Implementar:** no `funnel_briefing.py` (ler o compositor; ~182 linhas), renderizar `intro_section` (parágrafo antes da lista de H2) e `closing_section` (parágrafo após), com estilo condizente. Ajustar o ponto em `routers/entities.py` (~548-566) que monta os dados da página para o composer, garantindo que os campos são repassados.

- [ ] **Step 4: Rodar — PASSA.**

- [ ] **Step 5: Commit** `feat(pautador-pro): DOCX renderiza introdução e fechamento das páginas (R4)`

---

## PHASE 5 — Frontend (depende da Fase 0 + Task 3)

### Task 12: Cliente API — params de descoberta + niches()/createNiche()

**Files:**
- Modify: `src/lib/pautadorApi.ts`
- Test: verificação por `tsc`/build (sem unit runner para o client).

**Interfaces:**
- Consumes: endpoints `GET/POST /api/pautador/niches` (Task 3); params `niches`/`seasonality` (Task 5).
- Produces: `pautadorApi.entityDiscovery({..., niches?, seasonality?})`; `pautadorApi.niches()`; `pautadorApi.createNiche(payload)`.

- [ ] **Step 1: Implementar** em `pautadorApi.ts`: estender `entityDiscovery` params com `niches?: string[]; seasonality?: 'evergreen'|'seasonal'`; adicionar `niches(): Promise<{niches: PautadorNiche[]; source: string}>` (GET) e `createNiche(payload): Promise<{niche: PautadorNiche}>` (POST). Definir o tipo `PautadorNiche` em `types/pautadorEntity.ts` (slug,label,guidance,allowed_verticals,is_active,sort_order).

- [ ] **Step 2: Verificar** `cd webgo && npx tsc --noEmit` (ou `npm run build`) sem erros novos.

- [ ] **Step 3: Commit** `feat(pautador-pro): client API para nichos e params de descoberta (R1/R2)`

---

### Task 13: UI — multiselect de nicho + toggle sazonal + modal "+ nicho"

**Files:**
- Modify: `src/hooks/pautador/useEntityPautador.ts`
- Modify: `src/pages/pautador-pro/PautadorProPage.tsx`
- Create: `src/components/pautador-pro/NicheMultiSelect.tsx`
- Create: `src/components/pautador-pro/AddNicheModal.tsx` (padrão de `AddCountryModal.tsx`)
- Test: verificação por `tsc`/build + smoke manual.

**Interfaces:**
- Consumes: `pautadorApi.niches()/createNiche()/entityDiscovery(...)` (Task 12).
- Produces: seleção de nichos + sazonalidade no estado do hook; `runDiscovery` envia `niches`/`seasonality`.

- [ ] **Step 1: Implementar o hook** `useEntityPautador.ts`: estado `selectedNiches: string[]`, `seasonality: 'evergreen'|'seasonal'|null`; carregar `niches()` no mount; `runDiscovery` passa `{niches: selectedNiches, seasonality}` ao `entityDiscovery`.

- [ ] **Step 2: Implementar `NicheMultiSelect.tsx`** (multiselect com os nichos ativos, padrão shadcn já usado no projeto) e `AddNicheModal.tsx` (form slug/label/guidance/verticais → `createNiche`).

- [ ] **Step 3: Integrar na página** `PautadorProPage.tsx`: colocar o multiselect + toggle Evergreen/Sazonal ao lado do `CountryCombobox` (bloco de controles da run ~linha 74-109); botão "+ nicho" abre o modal.

- [ ] **Step 4: Verificar** `npx tsc --noEmit` / `npm run build` sem erros; smoke visual do fluxo.

- [ ] **Step 5: Commit** `feat(pautador-pro): seletor de nicho + sazonalidade + criar nicho na UI (R1/R2)`

---

## PHASE 6 — Verificação final

### Task 14: Regressão + build + acceptance

**Files:** nenhum novo (correções pontuais se algo quebrar).

- [ ] **Step 1: Backend** — `cd backend && python -m pytest -q` (toda a suíte; garantir `test_api_kw_funnel.py` e `test_funnel_roles.py` verdes + os novos testes).
- [ ] **Step 2: Frontend** — `cd webgo && npm run build` (Vite/tsc) sem erros.
- [ ] **Step 3: Acceptance manual** contra a §5 do spec: rodar descoberta com nicho único (foco), Evergreen/Sazonal, e um par Brasil↔país-espanhol (idioma correto nos dois); gerar funil de uma entidade rica e de uma entidade difusa (não-branco); conferir intro/fechamento no DOCX, ausência de datas em títulos e tom moderado.
- [ ] **Step 4: Corrigir** qualquer regressão encontrada (uma correção por commit).
- [ ] **Step 5: Commit** (se houver correções) `test(pautador-pro): regressão verde + acceptance R1-R9`

---

## Self-Review (autor do plano)

- **Cobertura do spec:** R1→T1-T5,T12-T13; R2→T2,T4,T5,T12-T13; R3→T4,T5,T7,T8,T9-T10; R4→T2,T6,T7,T11; R5→T6,T9; R6→T6,T9; R7→T9,T10; R8→T6,T9; R9→T7,T8. Infra/lockstep→T1,T2,T5,T12. Todos cobertos.
- **Sequência de arquivos compartilhados:** `entities/orchestrator.py` só em T5 (discovery), T8/T10 (funnel) — sequenciais. `routers/entities.py` em T3 (endpoints), T5 (discovery+whitelist), T11 (DOCX) — sequenciais. `funnel_builder.py` só T6. Nenhum arquivo é editado por dois agentes em paralelo (SDD é sequencial).
- **Placeholders:** nenhum "TBD"; código completo nas partes mecânicas; nas partes de craft de prompt (T6/T9), direções exatas + âncoras + asserts de teste (o nível honesto, dado que o prompt tem 886 linhas a serem editadas in loco).
- **Consistência de tipos:** `niche_slug`, `intro_section`, `closing_section`, `forced_language`, `seasonality∈{evergreen,seasonal}`, `temporal_window∈{Perene,Sazonal,Evento}` usados de forma idêntica em todas as tasks.
