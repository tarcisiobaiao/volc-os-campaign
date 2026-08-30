# Pautador Pro — Backend (FastAPI)

Esteira de **arbitragem de atenção** por país, em três fases:

1. **Descobridor de Pautas** — dado um país, descobre **40 oportunidades** (8 Ouro Puro `S` · 14 Ouro `A` · 12 Prata `B` · 6 Experimental).
2. **Minerador de Palavras** — expande uma oportunidade aprovada numa **árvore de keywords** (volume, CPC, competição, intenção).
3. **Construtor de Funis** — monta um **funil de 5 páginas** (avatar, objetivo emocional, subtítulos, ligações).

A regra de ouro: `RPM (receita por mil) > CPC (custo do clique)` →
`OURO = Volume Alto × CPC Baixo × RPM Alto × Competição Baixa`.

Este backend é **independente do frontend** e foi desenhado para ser
deployado como um **segundo projeto Vercel** com *root directory* = `/backend`.

---

## Por que ele "só funciona"

O backend **sobe com zero segredos**:

- Sem chave de LLM → usa o **MockEngine** (gerador determinístico, sem rede) que
  produz dados 100% válidos (distribuição 8/14/12/6, enums corretos).
- Sem Supabase → roda em **modo dry** (retorna os resultados inline, sem persistir).

Conforme as chaves são adicionadas (`GEMINI_API_KEY`, `PERPLEXITY_API_KEY`,
`SUPABASE_*`), ele liga as integrações reais — sem mudar o contrato.

---

## Estrutura

```
backend/
  app/
    main.py                 # FastAPI app + CORS + /health
    config.py               # Settings (pydantic-settings, env-driven)
    schemas.py              # Contratos Pydantic (fonte da verdade compartilhada)
    scoring.py              # Nota de arbitragem (port fiel do Code node n8n) + TDD
    prompts.py              # GOD MODE system prompt (verbatim) + mineração + funil
    llm/
      base.py               # LLMClient / GroundingClient / DiscoveryEngine + extract_json
      engine.py             # LLMEngine (liga client + prompts)
      gemini.py             # GeminiClient (httpx)
      openai_client.py      # OpenAIClient (httpx)
      perplexity.py         # PerplexityGrounding (Sonar Pro)
      mock.py               # MockEngine + MockGrounding (fallback determinístico)
      __init__.py           # get_engine() / get_grounding() (fábrica)
    agents/
      country_research.py   # Fase 1 — grounding (Perplexity)
      persona_archaeology.py# Fase 2 — personas
      attention_flow.py     # Fase 3 — insights
      critic_validator.py   # valida/dedup/distribuição das seeds
      arbitrage_scoring.py  # enriquece + pontua + stats
      keyword_mining.py     # Fase 2 (minerador)
      funnel_builder.py     # Fase 3 (funil)
      orchestrator.py       # DiscoveryOrchestrator
    services/
      supabase_service.py   # PostgREST service-role (server-side only)
    routers/
      pautador.py           # endpoints /api/pautador/*
  api/index.py              # entrypoint ASGI da Vercel
  tests/test_scoring.py     # 13 testes do scoring (reproduz os exemplos do doc)
  requirements.txt
  vercel.json
  .env.example
```

---

## Rodar localmente

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# (opcional) configurar chaves
cp .env.example .env   # edite à vontade — funciona vazio (mock)

# subir a API
uvicorn app.main:app --reload --port 8000
```

- Health: `curl localhost:8000/health`
- Docs interativos: `http://localhost:8000/docs`
- Descoberta (mock): `curl -X POST localhost:8000/api/pautador/discovery -H 'content-type: application/json' -d '{"country":"Reino Unido","native_language":"en-GB","count":40}'`

Testes do scoring (sem dependências extras):

```bash
python tests/test_scoring.py        # 13/13
# ou: pytest tests/
```

---

## Endpoints

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/health` | health do serviço |
| GET | `/api/pautador/health` | health + engine/supabase resolvidos |
| GET | `/api/pautador/countries` | catálogo de países (Supabase ou fallback) |
| POST | `/api/pautador/discovery` | **Fase 1** — gera 40 oportunidades |
| GET | `/api/pautador/runs` | lista execuções |
| GET | `/api/pautador/runs/{id}` | detalhe da execução + oportunidades |
| POST | `/api/pautador/opportunities` | adiciona oportunidade manual |
| PATCH | `/api/pautador/opportunities/{id}/status` | move card / revisa |
| POST | `/api/pautador/opportunities/{id}/mine` | **Fase 2** — árvore de keywords |
| POST | `/api/pautador/opportunities/{id}/funnel` | **Fase 3** — funil de 5 páginas |

---

## A nota de arbitragem (auditável)

Port fiel do Code node do n8n (`scoring.py`), com `Math.round` half-up:

```
base   = volume*0.25 + rpm*0.40 + competição_invertida*0.35
nota   = base × confiança × peso_do_tier         (2 casas)

volume/rpm:    very_high=100 high=75 medium=50 low=25
competição⁻¹:  low=100 medium=50 high=25
confiança:     very_high=1.0 high=0.85 medium=0.7 low=0.5
peso tier:     S=1.5 A=1.2 B=1.0 EXPERIMENTAL=0.9
```

Reproduz exatamente os exemplos do documento (seed_002 → 114.38, seed_005 → 108.75,
seed_003 → 102, seed_001 → 135). Tier S pode ultrapassar 100.

---

## Deploy na Vercel (segundo projeto)

1. Novo projeto na Vercel apontando para o **mesmo repositório**.
2. **Root Directory** = `backend`.
3. Framework Preset = **Other** (a Vercel detecta `requirements.txt` + `api/`). Python 3.12.
4. Variáveis de ambiente (Project → Settings → Environment Variables): ver `.env.example`
   (no mínimo `GEMINI_API_KEY` + `PERPLEXITY_API_KEY` para LLM real e
   `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` para persistência).
5. Deploy. A `vercel.json` reescreve todas as rotas para `api/index.py` (ASGI).
6. No frontend, aponte `VITE_PAUTADOR_API_URL` para a URL deste projeto.

> ⚠️ `SUPABASE_SERVICE_ROLE_KEY` vive **somente** aqui (server-side). Nunca
> use prefixo `VITE_` para ela e nunca a coloque no projeto do frontend.

Antes de persistir, rode a migração `src/sql/v7_01_create_pautador_tables.sql`
no Supabase SQL Editor (projeto `txvvzpstquqmbhljudfn`).
