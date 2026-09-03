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


# ═══════════════════════════════════════════════════════════════════════════
# O ATO QUE FALTAVA: CONFERIR E APROVAR O CONJUNTO PAGO
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ O MOTOR DECIDIA BEM E NINGUÉM PODIA ASSINAR A DECISÃO.
#
# `paid_eligibility.aprovar()` existe desde a sprint do conjunto pago e, medido
# em 03/09/2026, NÃO TEM CHAMADOR DE PRODUÇÃO: os 9 call sites são todos de
# teste. Quem produz o conjunto (`funnel_factory.py:391`) grava
# `conjunto_pago` SEM `approved_set_sha256`, e `portao_conjunto_pago.py:158`
# recusa exatamente esse estado com `CONJUNTO_PAGO_NAO_APROVADO`.
#
# O efeito é o caminho normal fechado: `/provar` e `/subir` devolvem 409 e a
# campanha Search não nasce. Não faltava motor nem portão — faltava a PORTA
# pela qual um humano confere a impressão e assina.
#
# Estas duas rotas são essa porta, e só ela: nenhuma decide elegibilidade,
# nenhuma cria keyword, nenhuma toca no Google Ads. A primeira MOSTRA o que o
# motor decidiu; a segunda registra que uma pessoa conferiu aquela impressão.

from app.agents.mining.paid_eligibility import (  # noqa: E402
    MEDIDO as _SINAL_MEDIDO,
    CampaignKeywordSet,
    HashDivergente,
    aprovar,
    conjunto_de_dicionario,
)
from app.agents.mining.portao_conjunto_pago import (  # noqa: E402
    N8N_SEM_CONTRATO,
    PortaoDoConjuntoPago,
    conjunto_do_cluster,
    parece_produzido_fora_do_motor,
)
from app.seguranca.identidade import Identidade  # noqa: E402

from pydantic import BaseModel  # noqa: E402

#: Um motivo tem de dizer alguma coisa. "ok", "sim" e "." são assinatura sem
#: declaração — e é a declaração que serve à auditoria depois, quando alguém
#: perguntar por que aquele conjunto foi congelado.
MOTIVO_MINIMO = 10


class AprovacaoConjuntoPagoRequest(BaseModel):
    """O ato humano, por escrito.

    `hash_conferido` não é cerimônia: é o que impede aprovar uma tela e
    exportar outra coisa. Ele viaja no corpo porque o que se aprova é a
    IMPRESSÃO QUE O OPERADOR VIU, não a que o servidor tem no momento do
    clique — se as duas divergirem, `aprovar()` recusa.
    """

    opportunity_id: Optional[int] = None
    run_id: Optional[int] = None
    hash_conferido: str
    motivo: str


def _sinal_para_cpc(sinal: Any) -> Optional[Dict[str, Any]]:
    """`Sinal` → o `Cpc` que a tela conhece, com a ausência preservada.

    ⚠️ O objeto viaja MESMO SEM NÚMERO, com `valor: null`. É a mesma regra de
    `volc_ads/pautador_ponte.Cpc`: quem carrega a procedência é o objeto, e
    "não medido, fonte X" é informação — um `null` no lugar do objeto inteiro
    seria silêncio, e um `0.0` seria a afirmação de que o clique é de graça.

    `moeda` é `null` de propósito: o conjunto pago não declara moeda em lugar
    nenhum, e escrever "BRL" aqui seria inventar a unidade do número.
    """
    if sinal is None:
        return None
    valor = getattr(sinal, "valor", None)
    estado = str(getattr(sinal, "estado", "") or "")
    fonte = str(getattr(sinal, "fonte", "") or "?")
    motivo = getattr(sinal, "motivo", None)
    procedencia = f"estado {estado} · fonte {fonte}"
    if motivo:
        procedencia += f" · {motivo}"
    return {
        "valor": None if valor is None else float(valor),
        "procedencia": procedencia,
        "moeda": None,
        # `measured` no vocabulário do `Sinal` é medição de leilão de verdade,
        # que é o que "medido na conta" quer dizer para quem lê a tela.
        "medido_na_conta": estado == _SINAL_MEDIDO,
    }


def _kw_do_conjunto(d: Any) -> Dict[str, Any]:
    """Uma decisão do conjunto, na forma que `KeywordDoConjuntoPago` declara."""
    volume = getattr(getattr(d, "volume", None), "valor", None)
    motivos = list(getattr(d, "motivos", None) or [])
    return {
        "termo": d.termo,
        "termo_normalizado": d.termo_normalizado,
        "match_type": d.match_type,
        "subintencao": d.subintencao,
        # `int` só quando há número. Volume ausente é `null` — ver o ⚠️ de
        # `src/types/trafego.ts:Cpc.valor`: zero é uma medição.
        "volume": None if volume is None else int(volume),
        "cpc": _sinal_para_cpc(getattr(d, "cpc", None)),
        "motivo": "; ".join(motivos) or None,
    }


def _localizar_conjunto(cluster: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    """Onde, dentro de `factory_output`, mora o conjunto pago deste cluster.

    ⚠️ POR QUE NÃO `conjunto_do_cluster()` AQUI.

    `portao_conjunto_pago.conjunto_do_cluster()` é o portão de DEPOIS da
    aprovação: ele recusa com `CONJUNTO_PAGO_NAO_APROVADO` justamente o estado
    que esta tela existe para mostrar — conjunto minerado, ainda sem selo. Usá-
    lo na leitura fecharia a porta que estamos abrindo.

    O que se reaproveita dele é a guarda que vale nos dois lados
    (`parece_produzido_fora_do_motor`), e o portão inteiro volta a rodar no
    POST, como CONFERÊNCIA, antes de qualquer escrita.

    Devolve o ÍNDICE junto com o dicionário porque `factory_output` é uma lista
    com um item por funil: escrever de volta sem o índice sobrescreveria os
    outros funis do mesmo cluster.
    """
    if parece_produzido_fora_do_motor(cluster):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{N8N_SEM_CONTRATO}: este cluster foi produzido fora do motor "
                "Python de elegibilidade paga e não carrega `conjunto_pago`. "
                "Minere de novo pelo motor antes de aprovar conjunto."
            ),
        )
    itens = [x for x in (cluster.get("factory_output") or []) if isinstance(x, dict)]
    for i, item in enumerate(itens):
        bruto = (item.get("keywords_campanha") or {}).get("conjunto_pago")
        if bruto:
            return i, bruto
    raise HTTPException(
        status_code=404,
        detail=(
            "Este cluster não tem `conjunto_pago` em nenhum funil de "
            "`factory_output`. Não há conjunto para conferir — rode a fábrica "
            "de funis do Pautador antes."
        ),
    )


async def _cluster_do_card(
    supa: SupabaseService, opportunity_id: int, run_id: Optional[int]
) -> Dict[str, Any]:
    """O cluster mais recente do card, conferido contra o `run_id` pedido.

    ⚠️ 404, e não um corpo vazio com `pode_aprovar: false`.

    O corpo de revisão exige `selected_set_sha256` — uma impressão. Devolver um
    corpo sem cluster obrigaria a inventar essa string, e uma tela de
    conferência com impressão inventada é pior que uma tela que não abre.

    `run_id` é CONFERIDO, não usado como filtro: `get_latest_cluster` devolve o
    mais recente do card, e devolver calado o conjunto de outra execução seria
    apresentar para assinatura algo diferente do que o operador pediu.
    """
    if not supa.enabled:
        raise HTTPException(
            status_code=503,
            detail="Supabase não configurado neste backend: não há conjunto para ler.",
        )
    cluster = await supa.get_latest_cluster(opportunity_id)
    if not cluster:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Nenhum cluster de keywords para a oportunidade {opportunity_id}. "
                "Minere a oportunidade antes de aprovar conjunto pago."
            ),
        )
    if run_id is not None and cluster.get("run_id") not in (None, run_id):
        raise HTTPException(
            status_code=409,
            detail=(
                f"O cluster mais recente deste card é da execução "
                f"{cluster.get('run_id')}, e você pediu a {run_id}. Recuso "
                "apresentar um conjunto de outra execução para conferência."
            ),
        )
    return cluster


def _veredito(conjunto: CampaignKeywordSet) -> tuple[bool, Optional[str], List[str]]:
    """Se este conjunto pode ser aprovado, por que não, e o que alertar.

    A autoridade é do servidor: a tela PROJETA este veredito, não o recalcula.
    Recalcular no navegador é como nasceram as duas réguas de severidade do
    cockpit.
    """
    alertas = list(conjunto.alertas or [])
    selecionado = conjunto.selected_set_sha256

    if not conjunto.selected_keywords:
        return False, (
            "O conjunto não tem nenhuma keyword selecionada. Aprovar um conjunto "
            "vazio congelaria uma campanha sem termo — reveja a seleção."
        ), alertas
    if conjunto.blockers:
        return False, (
            "Há bloqueador em aberto: " + ", ".join(conjunto.blockers)
            + ". Bloqueador é nomeado de propósito — o portão diz qual falta em "
            "vez de escolher um número plausível."
        ), alertas
    if conjunto.approved_set_sha256 == selecionado:
        return False, (
            f"Este conjunto já está aprovado na impressão {selecionado[:12]}… "
            f"por {conjunto.aprovado_por or 'alguém não identificado'}. "
            "Aprovar de novo não mudaria nada."
        ), alertas
    if conjunto.approved_set_sha256:
        # Aprovado ANTES e alterado depois. É re-aprovável — a doutrina do
        # portão é "mude a seleção e aprove de novo, a impressão nova é o que
        # autoriza" — mas o operador precisa saber que está trocando um selo,
        # não colocando o primeiro.
        alertas.append(
            f"Este conjunto já tinha sido aprovado em "
            f"{conjunto.approved_set_sha256[:12]}… e MUDOU desde então. Aprovar "
            f"agora substitui aquele selo pela impressão {selecionado[:12]}…."
        )
    return True, None, alertas


def _corpo_da_revisao(
    opportunity_id: int, cluster: Dict[str, Any], conjunto: CampaignKeywordSet
) -> Dict[str, Any]:
    pode, porque_nao, alertas = _veredito(conjunto)
    return {
        "opportunity_id": opportunity_id,
        "cluster_id": cluster.get("id"),
        "selecionadas": [_kw_do_conjunto(d) for d in conjunto.selected_keywords],
        "excluidas": [_kw_do_conjunto(d) for d in conjunto.excluded_keywords],
        "em_revisao_humana": [_kw_do_conjunto(d) for d in conjunto.human_review_keywords],
        # `negative_keywords` é `List[Dict]` no motor e `string[]` no contrato da
        # tela. O motor NÃO cria negativa (`conferir_congelamento` levanta se
        # houver), então esta lista é vazia na prática — a conversão existe para
        # não estourar caso um registro antigo traga alguma.
        "negativas": [
            str(n.get("termo") or n.get("texto") or n) if isinstance(n, dict) else str(n)
            for n in (conjunto.negative_keywords or [])
        ],
        # ⚠️ RECALCULADA das decisões, nunca lida do registro — é a propriedade
        # `selected_set_sha256`. Ler o hash gravado seria pedir ao registro que
        # atestasse a si mesmo.
        "selected_set_sha256": conjunto.selected_set_sha256,
        "approved_set_sha256": conjunto.approved_set_sha256,
        "aprovado_por": conjunto.aprovado_por,
        "selection_policy_version": conjunto.selection_policy_version,
        "blockers": list(conjunto.blockers or []),
        "alertas": alertas,
        "pode_aprovar": pode,
        "porque_nao": porque_nao,
    }


@router.get("/opportunities/{opportunity_id}/conjunto-pago")
async def revisar_conjunto_pago(
    opportunity_id: int = Path(..., ge=1),
    run_id: Optional[int] = None,
) -> Dict[str, Any]:
    """O conjunto pago apresentado para CONFERÊNCIA. Leitura pura.

    Não decide elegibilidade, não reordena, não completa nada: o que sai daqui
    é o que o motor gravou, reidratado, com a impressão recalculada. É essa
    impressão que o operador confere e devolve em `hash_conferido`.
    """
    supa = SupabaseService(get_settings())
    cluster = await _cluster_do_card(supa, opportunity_id, run_id)
    _, bruto = _localizar_conjunto(cluster)
    try:
        conjunto = conjunto_de_dicionario(bruto)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"O `conjunto_pago` gravado está ilegível: {exc}",
        ) from exc
    return _corpo_da_revisao(opportunity_id, cluster, conjunto)


@router.post("/opportunities/{opportunity_id}/conjunto-pago/aprovar")
async def aprovar_conjunto_pago(
    opportunity_id: int = Path(..., ge=1),
    body: AprovacaoConjuntoPagoRequest = Body(...),
    identidade: Identidade = Depends(exigir_usuario),
) -> Dict[str, Any]:
    """O ato humano: congela o conjunto contra a impressão que foi conferida.

    ⚠️ `aprovado_por` é a IDENTIDADE AUTENTICADA, nunca um campo do corpo. Um
    aprovador que viaja no corpo é um aprovador que o cliente escolhe, e uma
    assinatura escolhida pelo assinado não é assinatura.
    """
    if body.opportunity_id is not None and body.opportunity_id != opportunity_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"O corpo declara a oportunidade {body.opportunity_id} e a URL "
                f"pede a {opportunity_id}. Recuso adivinhar qual das duas você "
                "quis aprovar."
            ),
        )

    motivo = (body.motivo or "").strip()
    if len(motivo) < MOTIVO_MINIMO:
        raise HTTPException(
            status_code=422,
            detail=(
                "Escreva por que este conjunto pode ser congelado (ao menos "
                f"{MOTIVO_MINIMO} caracteres). O motivo é o que responde, daqui "
                "a três meses, por que estes termos e não outros foram ao "
                "leilão — 'ok' não responde."
            ),
        )

    supa = SupabaseService(get_settings())
    cluster = await _cluster_do_card(supa, opportunity_id, body.run_id)
    indice, bruto = _localizar_conjunto(cluster)
    try:
        conjunto = conjunto_de_dicionario(bruto)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"O `conjunto_pago` gravado está ilegível: {exc}",
        ) from exc

    pode, porque_nao, _ = _veredito(conjunto)
    if not pode:
        raise HTTPException(status_code=409, detail=porque_nao)

    try:
        aprovar(
            conjunto,
            aprovado_por=identidade.email or identidade.sub,
            hash_conferido=body.hash_conferido,
        )
    except HashDivergente as exc:
        # ⚠️ 409 e NADA congelado. A impressão que o operador conferiu não é a
        # do conjunto que está no banco agora: o conjunto mudou entre a tela e
        # o clique. Aprovar assim seria assinar um documento e arquivar outro.
        raise HTTPException(
            status_code=409,
            detail=(
                f"{exc} — o conjunto mudou entre a sua conferência e este "
                "clique, então a assinatura não vale para ele. Abra a revisão "
                "de novo, confira a impressão nova e aprove a partir dela. "
                "Nada foi congelado."
            ),
        ) from exc

    aprovado_em = _now()

    # ── a escrita ───────────────────────────────────────────────────────────
    # ⚠️ O ARRAY INTEIRO VOLTA, COM OS OUTROS FUNIS INTACTOS.
    #
    # `factory_output` é jsonb ARRAY com um item por funil, e o PostgREST não
    # faz `jsonb_set` por caminho: o PATCH substitui a coluna. Então a escrita é
    # read-modify-write do array LIDO nesta mesma requisição, trocando apenas
    # `[indice].keywords_campanha.conjunto_pago`. Mandar `[item]` — só o funil
    # aprovado — apagaria os demais.
    itens = [dict(x) for x in (cluster.get("factory_output") or []) if isinstance(x, dict)]
    campanha = dict(itens[indice].get("keywords_campanha") or {})
    campanha["conjunto_pago"] = conjunto.como_dicionario()
    # O ato humano fica FORA de `conjunto_pago`: `conjunto_de_dicionario` só lê
    # os campos do contrato, e o instante/motivo não são parte da impressão —
    # incluí-los ali seria misturar o que o hash cobre com o que ele não cobre.
    campanha["aprovacao_humana"] = {
        "aprovado_por": conjunto.aprovado_por,
        "aprovado_em": aprovado_em,
        "motivo": motivo,
        "hash_conferido": body.hash_conferido,
    }
    itens[indice] = {**itens[indice], "keywords_campanha": campanha}

    # ⚠️ A CONFERÊNCIA ANTES DA ESCRITA, PELO PORTÃO DE VERDADE.
    #
    # `conjunto_do_cluster` é o mesmo portão que `/provar` e `/subir` usam. Se
    # ele não abrir sobre o registro que estamos prestes a gravar, então esta
    # aprovação não destravaria nada — e gravá-la deixaria o operador achando
    # que destravou. Roda ANTES do PATCH: falhou, nada foi escrito.
    try:
        conjunto_do_cluster({**cluster, "factory_output": itens})
    except PortaoDoConjuntoPago as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A aprovação não destravaria o portão de campanha ({exc.codigo}): "
                f"{exc.detalhe} Nada foi gravado."
            ),
        ) from exc

    try:
        linhas = await supa.patch(
            "pautador_keyword_clusters",
            {"id": f"eq.{cluster.get('id')}"},
            {"factory_output": itens},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"A aprovação não foi gravada (o conjunto segue sem selo): {exc}",
        ) from exc
    if not linhas:
        raise HTTPException(
            status_code=502,
            detail=(
                f"O PATCH em `pautador_keyword_clusters#{cluster.get('id')}` não "
                "devolveu linha nenhuma: a aprovação NÃO foi gravada. O conjunto "
                "segue sem selo."
            ),
        )

    return {
        "opportunity_id": opportunity_id,
        "cluster_id": cluster.get("id"),
        "approved_set_sha256": conjunto.approved_set_sha256,
        "aprovado_por": conjunto.aprovado_por,
        "aprovado_em": aprovado_em,
        "n_selecionadas": len(conjunto.selected_keywords),
        "motivo": motivo,
    }
