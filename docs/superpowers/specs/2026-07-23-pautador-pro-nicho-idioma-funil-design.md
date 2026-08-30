# Pautador Pro — Direcionamento de Nicho, Idioma e Qualidade de Funil

- **Data:** 2026-07-23
- **Autor:** Tarcisio + Claude
- **Status:** Aprovado (design) — pronto para plano de implementação
- **Escopo:** `webgo/backend` (entity-first) + `webgo/src` (frontend `/pautador-pro`) + Supabase (`src/sql`)

---

## 1. Contexto — como o sistema funciona hoje (state-of-art)

O `/pautador-pro` roda **100% no backend Python** (fluxo *entity-first*). O n8n só é usado, opcionalmente, para a **mineração de volume real** (Google Ads + DataForSEO); ele **não** participa da descoberta nem da construção de funil. A unidade do Kanban é uma **ENTIDADE** (RUT, INSS, IPVA…); keywords (`seed_queries`), dores (`pains`) e funil são subordinados.

Pipeline real:

1. **Descoberta (run inicial)** — `POST /api/pautador/entities/discovery` → `EntityDiscoveryOrchestrator.run` ([entities/orchestrator.py:126](../../../backend/app/entities/orchestrator.py)) chama o Gemini com `ENTITY_DISCOVERY_SYSTEM_PROMPT` + `build_entity_discovery_mission` ([entities/prompts.py:111](../../../backend/app/entities/prompts.py)).
2. **Normaliza + score + dedup + persiste** — `_norm_item` valida (Pydantic), gera slug, computa score de arbitragem, deduplica e grava em `pautador_entities` (`vertical`), `pautador_entity_opportunities` (`temporal_window`), `pautador_pains`, `pautador_seed_queries`.
3. **(Opcional) Mineração** — `POST /entities/{id}/mine` dispara webhook n8n (volume/CPC real) ou `EntityMineOrchestrator` (Gemini).
4. **Funil** — `POST /entity-opportunities/{id}/funnel` → `EntityFunnelOrchestrator.run` ([entities/orchestrator.py:259](../../../backend/app/entities/orchestrator.py)) mapeia a entidade e chama o **Arquiteto de Funil** (`FunnelProOrchestrator` + prompt verbatim em [n8n_prompts/funnel_builder.py](../../../backend/app/n8n_prompts/funnel_builder.py)); `apply_roles_and_slugs` atribui papéis/slugs por posição.
5. **Card "ready"** — gera DOCX + task no ClickUp.

**`GeminiClient` é stateless** ([llm/gemini.py:25](../../../backend/app/llm/gemini.py)): client HTTP novo por chamada, `system_instruction` + 1 turno de usuário, `temperature=0.9`, **sem histórico e sem cache**.

**Regra de lockstep** ([entities/schemas.py:1-5]): qualquer coluna nova exige edição casada em **SQL** (`src/sql/v7_xx`), **Pydantic** (`entities/schemas.py`), **tipos do front** (`src/types/pautadorEntity.ts`) e o **whitelist do router** (`routers/entities.py` `_OPP_COLS`, **não** o `_OPP_COLUMNS` legado de `supabase_service.py`).

---

## 2. Objetivos (R1–R9) e causa-raiz

| # | Objetivo | Causa-raiz | Âncora |
|---|----------|-----------|--------|
| R1 | Selecionar nicho(s) para foco/profundidade | System prompt **obriga** dispersão ("DIVERSIFIQUE… nunca concentre"); não há input de nicho | `entities/prompts.py:36/98/111` |
| R2 | Filtrar Sazonal vs Evergreen | Existe só como **saída** (`temporal_window`), não como filtro de entrada | `entities/schemas.py:46`, `prompts.py:142` |
| R3 | Corrigir vazamento de idioma | **Não é cache** (client stateless). Idioma é "detectado" pelo LLM e o funil usa `entity.language` obsoleto → cai pro PT | `prompts.py:133`, `funnel_pro/orchestrator.py:71` |
| R4 | Incluir introdução + fechamento nas páginas | Schema de saída do arquiteto **não tem campo** de intro/closing | `funnel_builder.py:818`, `page_factory.py:90` |
| R5 | Remover datas dos títulos | `([ano])` é injetado de propósito nos templates de H1 | `funnel_builder.py:342/495` |
| R6 | Reduzir tom alarmista/promessas | Núcleo do prompt = "4 MEDOS UNIVERSAIS"/"COMPULSÃO"/stats exageradas | `funnel_builder.py:45-69` |
| R7 | IA revisora invisível | Não existe revisor no fluxo de entidade | `entities/orchestrator.py:287` |
| R8 | Profundidade + relevância das páginas de solução | Nada força mínimo de H2/proíbe "linguiça"/testa relevância; papel por posição | `funnel_builder.py:507`, `funnel_roles.py:19` |
| R9 | Nunca entregar em branco | Inputs magros → fallback silencioso de 5 páginas genéricas; funil interno não usa base semântica | `funnel_pro/orchestrator.py:41/88` |

---

## 3. Decisões travadas

1. **Nicho = tabela nova `pautador_niches`** (extensível pelo usuário), não o enum fixo.
2. **Enforcement = prompt forte + descarte pós-geração** (não só viés).
3. **R9 (refinado pelo usuário):** o funil **sempre é criado** quando o card é arrastado para "em funil". O arquiteto se apoia no **stack semântico da descoberta inicial do Gemini** (descrição, dores + descrições, seed queries, aliases, sistemas relacionados, inteligência cultural) como **base primária**; os números das KWs mineradas são **sinal secundário**, nunca portão. Sem branco, sem bloqueio.
4. **R7 = backstop completo** (factual + idioma R3 + sem datas R5 + tom R6 + relevância/profundidade R8), **auto-corrige e re-emite**, invisível, **fail-open**.

---

## 4. Arquitetura da mudança

### 4.A — Modelo de dados

**Nova migração `src/sql/v7_11_pautador_niches.sql`:**

```sql
create table if not exists public.pautador_niches (
  id                bigserial primary key,
  slug              text not null unique,
  label             text not null,
  guidance          text not null default '',           -- injetado no prompt de descoberta
  allowed_verticals text[] not null default '{}',        -- rede de segurança do descarte
  is_active         boolean not null default true,
  sort_order        int not null default 0,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
-- RLS: espelhar pautador_countries (SELECT p/ authenticated; writes via service-role).

insert into public.pautador_niches (slug,label,guidance,allowed_verticals,sort_order) values
 ('beneficios_sociais','Benefícios sociais','Programas de transferência de renda, auxílios, bolsas, pensões e amparo social — foco em quem recebe/solicita. NÃO incluir tributos, documentos ou serviços administrativos genéricos.', array['gov_beneficios'],10),
 ('servicos_governo','Serviços do governo','Órgãos, sistemas, documentos, obrigações e serviços públicos (emissão, consulta, agendamento, cadastros). NÃO confundir com benefícios de renda.', array['gov_beneficios'],20),
 ('educacao','Educação','Matrículas, bolsas, financiamento estudantil, vestibulares, cursos e certificações.', array['educacao'],30),
 ('emprego','Emprego','Carreira, trabalho, vagas, trabalho por/em aplicativos, direitos trabalhistas, concursos e qualificação.', array['empregos_concursos'],40),
 ('financas','Finanças','Crédito, empréstimo, financiamento, investimentos, seguros, impostos e apps financeiros.', array['financas','credito','seguros'],50),
 ('aplicativos','Aplicativos','Apps de alto uso e dúvidas utilitárias (como funciona, cadastro, recuperar acesso, tarifas), com ângulo informacional de publisher.', array['tecnologia'],60)
on conflict (slug) do nothing;
```

**Coluna nova em `pautador_entities`:** `niche_slug text null` (na mesma migração v7_11) — registra a qual nicho a entidade pertence (tag do LLM), habilita descarte exato e análise.

**Contrato de request** (`backend/app/entities/schemas.py`, `EntityDiscoveryRequest`):

```python
niches: List[str] = Field(default_factory=list)   # slugs; [] = comportamento atual (diversificado)
seasonality: Optional[Literal["evergreen", "seasonal"]] = None
```

**Saída de entidade** (`EntitySpec`/`EntityCardEntity` + schema JSON do LLM): `niche_slug: Optional[str]`.

**Páginas do funil (R4):** `intro_section: str` e `closing_section: str` são adicionados **dentro do jsonb `funnel_architecture.pages`** — **sem migração** (a coluna já é jsonb). Refletir nos tipos TS e no schema de saída do arquiteto.

**Lockstep a tocar:** `src/sql/v7_11_*`, `entities/schemas.py`, `src/types/pautadorEntity.ts`, `routers/entities.py` (`_OPP_COLS` + o insert de `pautador_entities` para incluir `niche_slug`).

### 4.B — Descoberta (R1, R2, R3-idioma)

`build_entity_discovery_mission(..., niches: Optional[list]=None, seasonality: Optional[str]=None, forced_language: Optional[str]=None)`:

- **R1:** quando `niches` preenchido → **remover** o bloco "DIVERSIFIQUE/nunca concentre" (`prompts.py:36/98/~140`) e injetar *"Foque EXCLUSIVAMENTE nestes nichos e vá FUNDO"* + o `guidance` de cada nicho selecionado. Instruir o modelo a preencher `entity.niche_slug` com um dos slugs fornecidos. `niches` vazio → comportamento atual intacto.
- **R2:** `seasonality` → diretriz forte no mission (`evergreen`→priorizar `Perene`; `seasonal`→priorizar `Sazonal/Evento`).
- **R3:** substituir *"detecte o idioma"* ([prompts.py:133](../../../backend/app/entities/prompts.py)) por *"IDIOMA NATIVO OBRIGATÓRIO: {forced_language}"* como regra inviolável.

`EntityDiscoveryOrchestrator.run`:
- Resolver `forced_language` via `resolve_country` ([data/countries.py](../../../backend/app/data/countries.py)).
- Resolver os nichos selecionados (label/guidance/allowed_verticals) via `SupabaseService`; fallback para constantes-seed quando Supabase off.
- **Descarte pós-geração:** dropar entidades com `niche_slug` fora do conjunto selecionado (fallback: `vertical` fora da união de `allowed_verticals`); e, se `seasonality` setado, dropar `temporal_window` incompatível. Emitir `warnings` nos descartes. **Não** há refil automático em v1 (documentar como follow-up).

`entities/mock.py`: mocks de descoberta honram `niches`/`seasonality`/`forced_language` (senão runs sem chave violam R1/R2/R3 em silêncio).

### 4.C — Arquiteto de funil (R3-idioma, R4, R5, R6, R8, R9)

- **R3:** `FunnelProOrchestrator` recebe o `forced_language` e interpola como **restrição dura** no template (`Lingua {forced_language}` + regra no system message). Parar de depender de `entity.language`.
- **R4:** schema de saída do arquiteto ([funnel_builder.py:818-857](../../../backend/app/n8n_prompts/funnel_builder.py)) ganha, por página, `intro_section` (introdução provocativa que engaja, antes dos H2) e `closing_section` (fecha a solução **daquela** página, **sem** CTA "leia a próxima"). O campo estrutural `hook_to_next_page`/`next_page_slug` **permanece** apenas como metadado de link interno (para slugs), **não** renderizado como CTA no fechamento. `page_factory.py` propaga intro/closing para o writing job e para a `FunnelPage`.
- **R5:** remover tokens `([ano])` dos templates de H1 (`funnel_builder.py:342/495/~123`) + regra *"PROIBIDO ano/data em qualquer `h1_title`"*. `data_atual` segue disponível para raciocínio interno de frescor, nunca em título.
- **R6:** reescrever `psychology_engine` (`funnel_builder.py:45-69`) para frame **informacional/benefício**; suavizar as `FORMULAs` de hook (`~537-589`); trocar exemplos com stats exageradas. `tone_voice` alvo = *"informativo, confiável, útil; persuasão por clareza e benefício, não por medo"*. Lista de frases banidas (ex.: "em 30 segundos", "elimina X%", "garantido", percentuais sem fonte) para o revisor checar (R7).
- **R8:** no prompt, exigir mínimo de H2 substantivos por página de solução (≥4) + instrução anti-"linguiça" + autoquestionamento *"esta página é necessária?"*. Validação de relevância real fica no **revisor** (funde/derruba página desnecessária — ex.: página só de "como entrar em contato").
- **R9:** `EntityFunnelOrchestrator` monta `opp_like`/`cluster_like` enriquecidos com o **stack semântico**: `description`, `concrete_pain`, `gold_reason`, `pains` (nome+descrição+`user_goal`), `seed_queries`, `aliases`, `related_systems`. `_supporting_data`/`_user_questions` ([funnel_pro/orchestrator.py:41/57](../../../backend/app/agents/funnel_pro/orchestrator.py)) **nunca** colapsam para `- {main_keyword}`: usam a base semântica. **Remover** o fallback silencioso de 5 páginas genéricas; se o arquiteto vier vazio, **re-tentar uma vez** enfatizando a base semântica. Números minerados são secundários.

### 4.D — IA revisora (R7)

- Novo agente `backend/app/agents/funnel_pro/reviewer.py` (Gemini, prompt próprio).
- **Entrada:** funil construído (páginas com intro/H2/closing, títulos, `funnel_strategy`), idioma-alvo forçado, e fatos da entidade (`official_source`, `related_systems`, `description`, sinais de processo automático vs manual).
- **Saída:** funil corrigido (mesmo schema) + lista de mudanças (apenas para logs).
- **Valida & repara:** correção factual/processual (ex.: cadastro automático vs manual do caso RUI), idioma == locale, sem ano em títulos (R5), tom/frases banidas (R6), relevância + profundidade (R8 — pode **fundir/derrubar/reordenar** páginas).
- **Ordem crítica:** roda em `EntityFunnelOrchestrator.run` **depois** de `architect.run` e **antes** de `apply_roles_and_slugs` ([entities/orchestrator.py:287→293](../../../backend/app/entities/orchestrator.py)) — senão o mapa de papéis/slugs e os links internos dessincronizam.
- **Fail-open:** se o revisor falhar/timeout, entrega o funil original do arquiteto. **Invisível:** só logs, nada exposto ao usuário final.

### 4.E — Frontend (`webgo/src`)

- `lib/pautadorApi.ts`: `entityDiscovery` params += `niches`, `seasonality`; novo `niches()` (GET `/api/pautador/niches`) e `createNiche()` (POST).
- `hooks/pautador/useEntityPautador.ts`: estado de nichos selecionados + sazonalidade; `runDiscovery` os envia.
- `pages/pautador-pro/PautadorProPage.tsx`: **multiselect de nichos** (carregado da API) + **toggle Evergreen/Sazonal** ao lado do `CountryCombobox`; modal "+ novo nicho" (padrão `AddCountryModal`).
- `types/pautadorEntity.ts`: `niche_slug` na entidade + params de request + campos intro/closing na página.

### 4.F — Endpoints de nicho (backend)

- `GET /api/pautador/niches` → lista `is_active` (fallback seed).
- `POST /api/pautador/niches` → cria nicho (atende "criar novas categorias").
- `SupabaseService`: métodos `list_niches` / `insert_niche`.

---

## 5. Critérios de aceitação

- **R1:** rodar descoberta com `niches=['financas']` retorna entidades majoritariamente/somente de finanças; `niches=[]` mantém o comportamento diversificado atual. Entidades fora do nicho são descartadas com warning.
- **R2:** `seasonality='evergreen'` favorece `Perene`; `'seasonal'` favorece `Sazonal/Evento`.
- **R3:** rodar Brasil logo após um país de língua espanhola (e vice-versa) → descoberta **e** funil saem 100% no idioma correto do país-alvo. Rep. Dominicana sai em espanhol.
- **R4:** cada página do funil tem `intro_section` e `closing_section` renderizados no DOCX; o fechamento não contém CTA para a próxima página.
- **R5:** nenhum `h1_title` contém ano/data.
- **R6:** ausência das frases banidas; tom informacional (validado pelo revisor).
- **R7:** o revisor roda antes de `apply_roles_and_slugs`, corrige o caso factual, e falha *open* sem bloquear entrega.
- **R8:** páginas de solução com ≥4 H2 substantivos; página desnecessária (ex.: só "contato/telefone") é fundida/removida.
- **R9:** entidades de baixo volume/difusas (ex.: "Implante Dentário Gratuito"/BR, "Che Róga Porã"/PY) geram funil **não vazio**, apoiado na base semântica.
- **Regressão:** `backend/tests/test_api_kw_funnel.py` e `test_funnel_roles.py` continuam passando; `vite build`/`tsc` sem erros.

---

## 6. Ordem de implementação (fases + dependências)

- **Fase 0 — Contratos & dados** (barreira; tudo depende): v7_11 (tabela + seed + `niche_slug`), `entities/schemas.py`, `src/types/pautadorEntity.ts`, whitelist/insert em `routers/entities.py`.
- **Fase 1 — Descoberta** (R1/R2/R3-lang): `prompts.py`, `entities/orchestrator.py` (discovery), `mock.py`, endpoints de niches + `SupabaseService`.
- **Fase 2 — Arquiteto** (R3-lang/R4/R5/R6/R8/R9): `funnel_builder.py`, `page_factory.py`, `funnel_pro/orchestrator.py`, `entities/orchestrator.py` (funnel).
- **Fase 3 — Revisor** (R7): novo agente + wiring antes de `apply_roles_and_slugs` (depende da Fase 2).
- **Fase 4 — DOCX** (R4): composer em `routers/entities.py` + `docx/funnel_briefing.py` renderiza intro/closing (depende da Fase 2).
- **Fase 5 — Frontend** (depende da Fase 0/1): api client, hook, seletores, tipos, modal de nicho. Paralelizável com Fases 2–4 após a Fase 0.
- **Fase 6 — Verificação:** testes de regressão + novos testes (filtro de nicho, forçar idioma, guard de branco, revisor); `vite build`/`tsc`; rodar.

**Conflitos de arquivo a respeitar:** `entities/orchestrator.py` (Fases 1 e 2/3) e `routers/entities.py` (Fases 0/1/4) são tocados por várias fases → sequenciar essas edições por fase (mesmo dono por vez), nunca dois agentes no mesmo arquivo em paralelo.

---

## 7. Riscos & mitigações

- **Whitelist errado** → coluna nova cai silenciosamente: usar `_OPP_COLS` (entity-first), nunca `_OPP_COLUMNS` (legado).
- **Drift de schema/tipos:** lockstep SQL + Pydantic + TS + router.
- **Idioma forçado em país multilíngue:** confirmar cobertura de `resolve_country`; permitir override futuro via request.
- **Revisor reordenando páginas depois de slugs:** garantir ordem (revisor antes de `apply_roles_and_slugs`).
- **Mocks/fallbacks ignorando novos inputs:** atualizar `mock.py` e o fallback do arquiteto.
- **Prompt-only a 0.9 reintroduz ano/tom banido:** revisor (R7) é o backstop determinístico.
- **R9 skip vs build:** decisão do usuário = **sempre build** com base semântica (nunca segurar o card).

---

## 8. Fora de escopo (v1)

- Refil automático quando o descarte de nicho deixa menos que `count`.
- Forçar mineração antes do funil.
- Alterações no fluxo legado *keyword-first* (`/discovery`, `/mine`, `/funnel`) e no `CriticValidatorAgent` de seeds.
- Mudanças no workflow n8n externo de mineração.
