"""
Pautador Pro API router.

Endpoints (mounted at /api/pautador):
  GET    /health
  GET    /countries
  POST   /discovery                          -> Fase 1: descobre 40 oportunidades
  GET    /runs                               -> lista execucoes
  GET    /runs/{id}                          -> detalhe da execucao + oportunidades
  POST   /opportunities                      -> adiciona oportunidade manual
  PATCH  /opportunities/{id}/status          -> move card no Kanban / revisa
  POST   /opportunities/{id}/mine            -> Fase 2: minera arvore de keywords
  POST   /opportunities/{id}/funnel          -> Fase 3: constroi funil de 5 paginas

Persistence is optional: when Supabase is configured the agent pipeline
persists (service-role, RLS-bypassing); otherwise it runs in "dry" mode and
returns results inline. Persistence failures never break the response.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from app.agents.base import AgentContext, LogEntry
from app.agents.funnel_pro.orchestrator import FunnelProOrchestrator
from app.agents.mining.orchestrator import MiningOrchestrator
from app.agents.orchestrator import DiscoveryOrchestrator
from app.config import get_settings
from app.llm import get_engine, get_grounding
from app.schemas import (
    DiscoveryRequest,
    DiscoveryResponse,
    Funnel,
    FunnelRequest,
    FunnelResponse,
    KeywordCluster,
    ManualOpportunityRequest,
    MineRequest,
    MineResponse,
    Opportunity,
    Run,
    StatusUpdateRequest,
)
from app.scoring import enrich_seed
from app.services.supabase_service import SupabaseService

from app.seguranca.identidade import exigir_admin, exigir_usuario

# ---------------------------------------------------------------------------
# PORTÃO DE IDENTIDADE (fatia 1A.1b — 24/08/2026)
# ---------------------------------------------------------------------------
# `dependencies` no router vale para TODAS as rotas daqui, inclusive as que
# alguém adicionar depois. É a diferença entre uma regra e um hábito: com
# portão por rota, a rota nova nasce aberta e ninguém percebe — foi assim que
# este backend chegou a 64 rotas com zero checagem de identidade.
#
# Rotas administrativas sobem o portão no próprio decorador com
# `dependencies=[Depends(exigir_admin)]`. As duas dependências compõem: o
# `exigir_admin` encadeia `exigir_usuario`, então não há caminho que chegue a
# ADMIN sem antes provar identidade.
#
# O que NÃO passa por aqui: `GET /health` e `GET /` (em main.py) e as rotas de
# documentação do FastAPI, que não são APIRoute e não aceitam Depends — elas
# são tratadas em main.py.
router = APIRouter(prefix="/api/pautador", tags=["pautador"], dependencies=[Depends(exigir_usuario)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_context(engine_override: Optional[str], model: Optional[str]) -> AgentContext:
    settings = get_settings()
    engine = get_engine(settings, override=engine_override, model=model)
    grounding = get_grounding(settings)
    return AgentContext(settings=settings, engine=engine, grounding=grounding)


def _logs_to_rows(logs: List[LogEntry], run_id: Optional[int]) -> List[Dict[str, Any]]:
    rows = []
    for e in logs:
        rows.append(
            {
                "run_id": run_id,
                "agent": e.agent,
                "phase": e.phase,
                "level": e.level,
                "step": e.step,
                "message": e.message,
                "payload": e.payload,
                "duration_ms": e.duration_ms,
            }
        )
    return rows


@router.get("/health")
async def health() -> Dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "pautador-pro",
        "engine": settings.resolve_engine(),
        "grounding": bool(settings.perplexity_api_key) and settings.pautador_grounding_enabled,
        "supabase": settings.has_supabase,
        # KW mining readiness (no secrets — booleans + missing key names only)
        "kw_engine": settings.resolve_kw_engine(),
        "google_ads": settings.google_ads_auth_status(),
        "dataforseo": settings.has_dataforseo,
        "clickup": {
            "ready": settings.has_clickup,
            "list_id": bool(settings.clickup_list_id),
            "status": settings.clickup_task_status or None,
        },
    }


@router.get("/countries")
async def countries() -> Dict[str, Any]:
    settings = get_settings()
    supa = SupabaseService(settings)
    if supa.enabled:
        try:
            rows = await supa.select(
                "pautador_countries", {"order": "country_name.asc", "is_active": "eq.true"}
            )
            if rows:
                return {"countries": rows, "source": "supabase"}
        except Exception:  # noqa: BLE001
            pass
    # fallback: the canonical 195 sovereign countries (same dataset as the seed)
    from app.data.countries import fallback_countries

    return {"countries": fallback_countries(), "source": "fallback"}


@router.post("/discovery", response_model=DiscoveryResponse)
async def discovery(req: DiscoveryRequest) -> DiscoveryResponse:
    settings = get_settings()
    ctx = _build_context(req.engine, req.model)
    supa = SupabaseService(settings)

    persist = req.persist if req.persist is not None else (settings.pautador_persist_default and supa.enabled)
    persist = bool(persist and supa.enabled)
    warnings: List[str] = []
    run_id: Optional[int] = None
    run_row: Optional[Dict[str, Any]] = None

    # 1) create run (running)
    if persist:
        try:
            run_row = await supa.create_run(
                {
                    "country": req.country,
                    "country_code": req.country_code,
                    "native_language": req.native_language,
                    "phase": "discovery",
                    "status": "running",
                    "requested_count": req.count,
                    "engine": ctx.engine.name,
                    "model": ctx.engine.model,
                    "started_at": _now(),
                }
            )
            run_id = run_row.get("id") if run_row else None
        except Exception as exc:  # noqa: BLE001
            persist = False
            warnings.append(f"Persistência desativada (create_run falhou): {exc}")

    # 2) run the pipeline (engine failures must mark the run failed, not 500 silently)
    try:
        result = await DiscoveryOrchestrator(ctx).run(req.country, req.native_language, req.count)
    except Exception as exc:  # noqa: BLE001
        if persist and run_id:
            try:
                await supa.update_run(
                    run_id,
                    {"status": "failed", "error_message": str(exc)[:500], "completed_at": _now()},
                )
            except Exception:  # noqa: BLE001
                pass
        raise HTTPException(status_code=502, detail=f"Falha no motor de descoberta: {exc}")
    warnings.extend(result.get("warnings") or [])
    opps = result["opportunities"]

    # 3) persist opportunities + finalize run + logs
    if persist and run_id:
        try:
            rows = await supa.insert_opportunities(run_id, opps)
            # Map strictly by seed_id (the per-run unique key). No positional fallback:
            # PostgREST order is not guaranteed, so rows[i] could belong to a different seed.
            id_by_seed = {r.get("seed_id"): r.get("id") for r in rows if r.get("seed_id")}
            for o in opps:
                o["run_id"] = run_id
                o["id"] = id_by_seed.get(o.get("seed_id"))
            await supa.update_run(
                run_id,
                {
                    "status": "completed",
                    "produced_count": len(opps),
                    "completed_at": _now(),
                    "native_language": result["meta"].get("native_language"),
                    "market_tier": result["meta"].get("market_tier"),
                    "grounding_calls": result["meta"].get("grounding_calls", 0),
                    "cultural_intelligence": result["cultural_intelligence"],
                    "personas": result["personas"],
                    "insights": result["insights"],
                },
            )
            await supa.insert_logs(_logs_to_rows(ctx.logs, run_id))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Persistência parcial (insert falhou): {exc}")

    run_model = Run(
        id=run_id,
        run_uuid=(run_row or {}).get("run_uuid"),
        country=req.country,
        country_code=req.country_code,
        native_language=result["meta"].get("native_language"),
        market_tier=result["meta"].get("market_tier"),
        phase="discovery",
        status="completed",
        requested_count=req.count,
        produced_count=len(opps),
        engine=ctx.engine.name,
        model=ctx.engine.model,
        grounding_calls=result["meta"].get("grounding_calls", 0),
    )

    return DiscoveryResponse(
        run=run_model,
        meta=result["meta"],
        cultural_intelligence=result["cultural_intelligence"],
        personas=result["personas"],
        insights=result["insights"],
        opportunities=[Opportunity(**o) for o in opps],
        stats=result["stats"],
        persisted=bool(persist and run_id),
        warnings=warnings,
    )


@router.get("/runs")
async def list_runs() -> Dict[str, Any]:
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        return {"runs": [], "supabase": False}
    try:
        return {"runs": await supa.list_runs(), "supabase": True}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Supabase error: {exc}")


@router.get("/runs/{run_id}")
async def get_run(run_id: int = Path(..., ge=1)) -> Dict[str, Any]:
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado neste backend.")
    run = await supa.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run não encontrada.")
    opportunities = await supa.list_opportunities(run_id)
    return {
        "run": run,
        "cultural_intelligence": run.get("cultural_intelligence"),
        "personas": run.get("personas"),
        "insights": run.get("insights"),
        "opportunities": opportunities,
    }


@router.post("/opportunities", status_code=201)
async def add_opportunity(req: ManualOpportunityRequest) -> Dict[str, Any]:
    supa = SupabaseService(get_settings())
    enriched = enrich_seed(req.model_dump(), 0)
    # manual cards have no agent seed_id (unique key is run_id + lower(keyword))
    enriched.update({"status": "discovered", "source": "manual", "country": req.country, "seed_id": None})
    if not supa.enabled or not req.run_id:
        return {"opportunity": Opportunity(**enriched).model_dump(), "persisted": False}
    try:
        rows = await supa.insert_opportunities(req.run_id, [enriched])
        return {"opportunity": rows[0] if rows else enriched, "persisted": bool(rows)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Supabase error: {exc}")


@router.patch("/opportunities/{opp_id}/status")
async def update_status(opp_id: int, req: StatusUpdateRequest) -> Dict[str, Any]:
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado neste backend.")
    values: Dict[str, Any] = {"status": req.status}
    if req.status in ("validating", "ready", "rejected") and req.reviewed_by:
        values["reviewed_by"] = req.reviewed_by
        values["reviewed_at"] = _now()
    row = await supa.update_opportunity(opp_id, values)
    if not row:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada.")
    return {"opportunity": row}


async def _resolve_opportunity(
    supa: SupabaseService, opp_id: int, body: Optional[MineRequest]
) -> tuple[Dict[str, Any], bool]:
    """Return (opportunity, from_db). from_db=False means the inline body was used (dry mode)."""
    if supa.enabled:
        op = await supa.get_opportunity(opp_id)
        if op:
            return op, True
    if body and body.opportunity:
        return {**body.opportunity, "id": opp_id}, False
    raise HTTPException(
        status_code=404,
        detail="Oportunidade não encontrada. Forneça 'opportunity' no corpo para modo dry.",
    )


@router.post("/opportunities/{opp_id}/mine", response_model=MineResponse)
async def mine(opp_id: int, body: Optional[MineRequest] = Body(default=None)) -> MineResponse:
    settings = get_settings()
    supa = SupabaseService(settings)
    ctx = _build_context(body.engine if body else None, body.model if body else None)

    op, from_db = await _resolve_opportunity(supa, opp_id, body)
    try:
        result = await MiningOrchestrator(ctx).run(op)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha no Minerador (Fase 2): {exc}")

    cluster = result["cluster"]
    cluster["opportunity_id"] = opp_id
    warnings: List[str] = list(result.get("warnings") or [])
    persisted = False
    persist_pref = body.persist if (body and body.persist is not None) else settings.pautador_persist_default
    # only persist against a real DB opportunity (else the FK to opportunity_id would fail)
    persist = persist_pref and supa.enabled and from_db
    if persist:
        try:
            row = await supa.insert_cluster(
                {
                    "run_id": op.get("run_id"),
                    "opportunity_id": opp_id,
                    "cluster_name": cluster.get("cluster_name"),
                    "main_keyword": cluster.get("main_keyword"),
                    "intent": cluster.get("intent"),
                    "keywords": cluster.get("keywords") or [],
                    "total_volume": cluster.get("total_volume"),
                    "avg_cpc_local": cluster.get("avg_cpc_local"),
                    "currency": cluster.get("currency"),
                    # rich pipeline output (requires migration v7_02)
                    "raw_keywords": result.get("raw_keywords"),
                    "production_ads_queue": result.get("production_ads_queue"),
                    "content_seo_queue": result.get("content_seo_queue"),
                    "funis_sugeridos": result.get("funis_sugeridos"),
                    "factory_output": result.get("factory_output"),
                    "summary": result.get("summary"),
                    "metrics": result.get("metrics"),
                    "services_used": result.get("services_used"),
                    "warnings": warnings,
                    "engine": result.get("engine"),
                }
            )
            await supa.update_opportunity(opp_id, {"status": "mining"})
            await supa.insert_logs(_logs_to_rows(ctx.logs, op.get("run_id")))
            persisted = bool(row)
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"Persistência falhou (rodou a migração v7_02_pautador_kw_funnel_outputs.sql?): {exc}"
            )

    return MineResponse(
        opportunity_id=opp_id,
        cluster=KeywordCluster(**cluster),
        summary=result.get("summary"),
        production_ads_queue=result.get("production_ads_queue") or [],
        content_seo_queue=result.get("content_seo_queue") or [],
        funis_sugeridos=result.get("funis_sugeridos") or [],
        funnel_prospector=result.get("funnel_prospector"),
        factory_output=result.get("factory_output") or [],
        raw_keywords=result.get("raw_keywords") or [],
        metrics=result.get("metrics"),
        services_used=result.get("services_used") or [],
        engine=result.get("engine") or "mock",
        duration_ms=result.get("duration_ms"),
        persisted=persisted,
        warnings=warnings,
    )


@router.post("/opportunities/{opp_id}/funnel", response_model=FunnelResponse)
async def funnel(opp_id: int, body: Optional[FunnelRequest] = Body(default=None)) -> FunnelResponse:
    settings = get_settings()
    supa = SupabaseService(settings)
    ctx = _build_context(body.engine if body else None, body.model if body else None)

    op, from_db = await _resolve_opportunity(supa, opp_id, body)

    # Resolve the mined cluster (supporting_data). For a DB-backed opportunity we
    # REQUIRE a prior mining; for a dry/ephemeral card we accept an inline cluster.
    cluster: Optional[Dict[str, Any]] = None
    if from_db and supa.enabled:
        cluster = await supa.get_latest_cluster(opp_id)
        if not cluster:
            raise HTTPException(
                status_code=409,
                detail="Minere a oportunidade antes de gerar o funil (nenhum cluster encontrado).",
            )
    elif body and body.cluster:
        cluster = body.cluster

    try:
        built = await FunnelProOrchestrator(ctx).run(op, cluster=cluster)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha no Construtor de Funis (Fase 3): {exc}")
    built["opportunity_id"] = opp_id

    warnings: List[str] = list(built.get("warnings") or [])
    persisted = False
    persist_pref = body.persist if (body and body.persist is not None) else settings.pautador_persist_default
    persist = persist_pref and supa.enabled and from_db
    if persist:
        try:
            page_rows = [
                {
                    "opportunity_id": opp_id,
                    "run_id": op.get("run_id"),
                    "funnel_name": built["funnel_name"],
                    "position": p.get("position"),
                    "page_title": p.get("page_title"),
                    "avatar": p.get("avatar"),
                    "stage": p.get("stage", "tofu"),
                    "emotional_goal": p.get("emotional_goal"),
                    "subtitles": p.get("subtitles") or [],
                    "internal_links": p.get("internal_links") or [],
                    "status": "draft",
                    # rich output (requires migration v7_02) — denormalized per page
                    "strategy": built.get("funnel_strategy"),
                    "pages": built.get("pages"),
                    "writing_jobs": built.get("writing_jobs"),
                    "raw_output": built.get("raw_output"),
                    "services_used": built.get("services_used"),
                    "warnings": warnings,
                }
                for p in built["pages"]
            ]
            rows = await supa.insert_funnel_pages(page_rows)
            await supa.update_opportunity(opp_id, {"status": "funnel"})
            await supa.insert_logs(_logs_to_rows(ctx.logs, op.get("run_id")))
            persisted = bool(rows)
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"Persistência falhou (rodou a migração v7_02_pautador_kw_funnel_outputs.sql?): {exc}"
            )

    return FunnelResponse(
        opportunity_id=opp_id,
        funnel=Funnel(
            opportunity_id=opp_id,
            run_id=built.get("run_id"),
            funnel_name=built["funnel_name"],
            pages=built["pages"],
        ),
        funnel_strategy=built.get("funnel_strategy"),
        writing_jobs=built.get("writing_jobs") or [],
        services_used=built.get("services_used") or [],
        persisted=persisted,
        warnings=warnings,
    )
