"""
ENTITY-FIRST API router (mounted at /api/pautador).

  POST  /entities/discovery                       -> descobre ENTIDADES por país (persiste, dedup, runs ADD)
  GET   /entity-opportunities?country=CO          -> cards do Kanban (entidade + dores + queries + funis)
  PATCH /entity-opportunities/{id}/status         -> move card no Kanban
  POST  /entity-opportunities/{id}/validate       -> valida a ENTIDADE como oportunidade
  POST  /entities/{id}/mine                       -> aprofunda a entidade (dores/keywords)
  POST  /entity-opportunities/{id}/funnel         -> hipótese de funil centrada na entidade
  GET   /entity-opportunities/{id}/briefing.html  -> briefing do funil renderizado (nova aba, Ctrl+P vira PDF)
  GET   /entity-opportunities/{id}/briefing.docx  -> o MESMO briefing como arquivo do Word

Persistence is service-role (server-side). Without Supabase it runs "dry"
(returns ephemeral cards). Discovery NEVER deletes existing cards (runs add);
the same entity across runs is deduped (country_code + slug + alias overlap).
"""
from __future__ import annotations

import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from fastapi.responses import HTMLResponse, Response

from app.agents.base import AgentContext
from app.config import get_settings
from app.data.niches import SEED_NICHES
from app.entities.normalize import entity_keys, find_matching_entity, identity_keys
from app.entities.prompts import EXCLUDE_LIST_MAX
from app.entities.orchestrator import (
    EntityDiscoveryOrchestrator,
    EntityEnrichOrchestrator,
    EntityFunnelOrchestrator,
    EntityMineOrchestrator,
)
from app.entities.schemas import (
    EntityCard,
    EntityValidateBatchRequest,
    EntityDiscoveryRequest,
    EntityDiscoveryResponse,
    EntityEnrichRequest,
    EntityFunnelRequest,
    EntityFunnelResponse,
    EntityCompleteRequest,
    EntityDisplayTitleRequest,
    EntityDuplicateRequest,
    EntityInsightsRequest,
    EntityTaskDescriptionRequest,
    EntityListResponse,
    EntityManualCreateRequest,
    EntityMineRequest,
    EntityMineResponse,
    EntityStatusUpdateRequest,
    QuestionChoiceRequest,
)
from app.llm import get_engine, get_grounding
from app.services.supabase_service import SupabaseService

log = logging.getLogger("pautador.entities")

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
router = APIRouter(prefix="/api/pautador", tags=["pautador-entities"], dependencies=[Depends(exigir_usuario)])

_OPP_COLS = [
    "gold_tier", "strategic_stage", "score", "estimated_volume", "ecpm_band", "roi_signal",
    "cpc_min", "cpc_max", "cpc_currency", "volume_level", "rpm_level",
    "competition_level", "confidence_level", "temporal_window", "concrete_pain",
    "gold_reason",
    # v7_15 · SEGUNDO EIXO (a pessoa LÊ?) — ao lado do score, não no lugar dele.
    "respostas", "resposta_em_uma_frase", "ignorancia_level", "engajamento_level", "opacidade_level",
    "reading_blocked", "reading_reason", "reading_strength",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_funnels(hyps: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Canonicalize funnel hypotheses to the DB/card shape (funnel_title/
    funnel_summary). The LLM/orchestrator speaks title/summary; every API
    RESPONSE emits funnel_title/funnel_summary so the frontend sees one shape."""
    out: List[Dict[str, Any]] = []
    for h in hyps or []:
        title = h.get("funnel_title") or h.get("title")
        if not title:
            continue
        out.append(
            {
                "funnel_title": title,
                "funnel_summary": h.get("funnel_summary") or h.get("summary"),
                "pages": h.get("pages") or [],
            }
        )
    return out


def _ctx(engine: Optional[str], model: Optional[str]) -> AgentContext:
    settings = get_settings()
    return AgentContext(
        settings=settings,
        engine=get_engine(settings, override=engine, model=model),
        grounding=get_grounding(settings),
    )


def _card_from_item(item: Dict[str, Any], ephemeral: bool = True) -> Dict[str, Any]:
    """Build an EntityCard dict from an orchestrator item (dry / not persisted)."""
    e = item["entity"]
    o = item["opportunity"]
    return {
        "id": None,
        "entity_id": None,
        "country_code": e.get("country_code"),
        "status": "discovered",
        "kanban_stage": "discovered",
        **{k: o.get(k) for k in _OPP_COLS},
        "entity": {
            "id": None,
            "canonical_name": e["canonical_name"],
            "full_name": e.get("full_name"),
            "slug": e["slug"],
            "country_code": e.get("country_code") or "",
            "country": e.get("country"),
            "entity_type": e.get("entity_type"),
            "entity_category": e.get("entity_category"),
            "vertical": e.get("vertical"),
            "official_source": e.get("official_source"),
            "related_systems": e.get("related_systems") or [],
            "aliases": e.get("aliases") or [],
            "description": e.get("description"),
            "language": e.get("language"),
            "niche_slug": e.get("niche_slug"),
        },
        "pains": item.get("pains") or [],
        "seed_queries": item.get("seed_queries") or [],
        # dry and persisted cards share the canonical funnel shape
        "funnel_hypotheses": _norm_funnels(item.get("funnel_hypotheses")),
        "ephemeral": ephemeral,
    }


def _card_from_rows(opp: Dict[str, Any]) -> Dict[str, Any]:
    """Build an EntityCard dict from persisted rows (list_entity_cards output)."""
    ent = opp.get("entity") or {}
    return {
        "id": opp.get("id"),
        "entity_id": opp.get("entity_id"),
        "run_id": opp.get("run_id"),
        "country_code": opp.get("country_code"),
        "status": opp.get("status") or "discovered",
        "kanban_stage": opp.get("kanban_stage") or "discovered",
        **{k: opp.get(k) for k in _OPP_COLS},
        "insights": opp.get("insights"),
        # v7_14: corpo da task no ClickUp (≠ insights, que é prompt do agente).
        "task_description": opp.get("task_description"),
        # v7_12: rótulo do card escrito pelo admin (diferencia cópias da mesma
        # entidade). Ausente em ambientes onde a migração ainda não rodou.
        "display_title": opp.get("display_title"),
        "clickup_task_url": opp.get("clickup_task_url"),
        "funnel_completed": bool(opp.get("funnel_completed")),
        "entity": {
            "id": ent.get("id"),
            "canonical_name": ent.get("canonical_name"),
            "full_name": ent.get("full_name"),
            "slug": ent.get("slug"),
            "country_code": ent.get("country_code") or opp.get("country_code") or "",
            "country": ent.get("country"),
            "entity_type": ent.get("entity_type"),
            "entity_category": ent.get("entity_category"),
            "vertical": ent.get("vertical"),
            "official_source": ent.get("official_source"),
            "related_systems": ent.get("related_systems") or [],
            "aliases": ent.get("aliases") or [],
            "description": ent.get("description"),
            "language": ent.get("language"),
            "niche_slug": ent.get("niche_slug"),
        },
        "pains": opp.get("pains") or [],
        "seed_queries": opp.get("seed_queries") or [],
        "funnel_hypotheses": opp.get("funnel_hypotheses") or [],
        "ephemeral": False,
    }


def _opp_row(item_opp: Dict[str, Any], entity_id: int, run_id: Optional[int], country_code: str) -> Dict[str, Any]:
    row = {k: item_opp.get(k) for k in _OPP_COLS}
    row.update(
        {
            "entity_id": entity_id,
            "run_id": run_id,
            "country_code": country_code,
            "status": "discovered",
            "kanban_stage": "discovered",
            "notes": {"score_source": item_opp.get("score_source")},
        }
    )
    return row


@router.get("/niches")
async def list_niches() -> Dict[str, Any]:
    """Catálogo de nichos selecionáveis (R1). Tenta Supabase; sem tabela/config,
    cai para as constantes-seed (mesmo padrão de GET /countries)."""
    supa = SupabaseService(get_settings())
    if supa.enabled:
        try:
            rows = await supa.list_niches()
            if rows:
                return {"niches": rows, "source": "supabase"}
        except Exception:  # noqa: BLE001
            pass
    return {"niches": SEED_NICHES, "source": "seed"}


def _is_duplicate_slug_error(exc: Exception) -> bool:
    """Heurística p/ detectar violação de `UNIQUE(slug)` do PostgREST/Postgres
    (HTTP 409 + código `23505`/mensagem `duplicate key value violates unique
    constraint`). httpx não inclui o corpo da resposta em `str(exc)` por
    padrão, então inspeciona também `exc.response.text` quando disponível
    (`httpx.HTTPStatusError`)."""
    text = str(exc)
    resp = getattr(exc, "response", None)
    if resp is not None:
        text += " " + (getattr(resp, "text", "") or "")
    text = text.lower()
    return "duplicate" in text or "unique" in text or "23505" in text


def _is_unknown_column_error(exc: Exception, column: str) -> bool:
    """Coluna que o PostgREST não conhece (migração ainda não rodada): responde
    400 + `PGRST204` "Could not find the 'x' column ... in the schema cache".
    Mesma inspeção de corpo do `_is_duplicate_slug_error`."""
    text = str(exc)
    resp = getattr(exc, "response", None)
    if resp is not None:
        text += " " + (getattr(resp, "text", "") or "")
    text = text.lower()
    return column.lower() in text and ("pgrst204" in text or "could not find" in text or "schema cache" in text)


@router.post("/niches", dependencies=[Depends(exigir_admin)])
async def create_niche(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Cria um nicho novo (form '+ nicho' do front). Exige Supabase — o catálogo
    seed é somente-leitura/fallback, não há onde persistir sem a tabela."""
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")
    row = {
        "slug": payload.get("slug"),
        "label": payload.get("label"),
        "guidance": payload.get("guidance") or "",
        "allowed_verticals": payload.get("allowed_verticals") or [],
        "sort_order": payload.get("sort_order") or 0,
    }
    if not row["slug"] or not row["label"]:
        raise HTTPException(status_code=422, detail="slug e label são obrigatórios.")
    try:
        niche = await supa.insert_niche(row)
    except Exception as exc:  # noqa: BLE001
        if _is_duplicate_slug_error(exc):
            raise HTTPException(status_code=409, detail="Nicho com esse slug já existe.")
        raise HTTPException(status_code=502, detail=f"Não foi possível criar o nicho: {exc}")
    if not niche:
        raise HTTPException(status_code=502, detail="Não foi possível criar o nicho.")
    return {"niche": niche}


@router.post("/entities/discovery", response_model=EntityDiscoveryResponse)
async def entities_discovery(req: EntityDiscoveryRequest) -> EntityDiscoveryResponse:
    settings = get_settings()
    ctx = _ctx(req.engine, req.model)
    supa = SupabaseService(settings)

    persist = req.persist if req.persist is not None else (settings.pautador_persist_default and supa.enabled)
    persist = bool(persist and supa.enabled)
    warnings: List[str] = []
    run_id: Optional[int] = None

    # 0a) Entidades JÁ existentes do país (QUALQUER etapa: descoberta, validação,
    #     funil, ou inputadas manualmente em Pronto) -> vão no prompt como exclusão,
    #     pra o agente trazer só NOVAS e não gastar token com o que já foi buscado.
    #
    #     UMA entrada por ENTIDADE ("CadÚnico (Cadastro Único; CadUnico)"), não uma por
    #     nome: com a lista achatada, cada entidade consumia ~6 slots do teto do prompt
    #     e a maior parte do board ficava invisível pro modelo — que então "descobria"
    #     o que já existia. Entidades do(s) nicho(s) pedido(s) vêm primeiro, pra serem
    #     as últimas a cair caso o teto seja atingido (são as mais prováveis de repetir).
    exclude_names: List[str] = []
    if supa.enabled and (req.country_code or "").strip():
        try:
            existing_pre = await supa.list_entities(req.country_code.upper())
            wanted_niches = {s for s in (req.niches or []) if s}
            if wanted_niches:
                existing_pre = sorted(
                    existing_pre,
                    key=lambda e: 0 if (e.get("niche_slug") in wanted_niches) else 1,
                )
            seen_ex: set = set()
            for e in existing_pre:
                primary = str(e.get("canonical_name") or "").strip()
                if not primary or primary.lower() in seen_ex:
                    continue
                seen_ex.add(primary.lower())
                variants: List[str] = []
                seen_v = {primary.lower()}
                for v in [e.get("full_name"), *(e.get("aliases") or [])]:
                    v = str(v or "").strip()
                    if v and v.lower() not in seen_v:
                        seen_v.add(v.lower())
                        variants.append(v)
                exclude_names.append(
                    f"{primary} ({'; '.join(variants[:3])})" if variants else primary
                )
            if len(exclude_names) > EXCLUDE_LIST_MAX:
                warnings.append(
                    f"Lista de exclusão truncada: {len(exclude_names)} entidades no board, "
                    f"{EXCLUDE_LIST_MAX} enviadas ao agente — repetições ficam possíveis."
                )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Lista de exclusão não carregada: {exc}")

    # 0b) Marca uma RUN 'running' ANTES da orquestração (trabalho pesado do LLM).
    #     Assim a UX sabe que há uma descoberta ON neste país mesmo se o usuário
    #     sair da tela e voltar — o front lê pautador_runs e anima o Kanban.
    if persist:
        try:
            run = await supa.create_run(
                {
                    "country": req.country,
                    "country_code": (req.country_code or "").upper() or None,
                    "native_language": req.native_language,
                    "phase": "discovery", "status": "running",
                    "requested_count": req.count, "started_at": _now(),
                }
            )
            run_id = run.get("id") if run else None
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Run (running) não registrada: {exc}")

    try:
        result = await EntityDiscoveryOrchestrator(ctx).run(
            req.country, req.country_code, req.native_language, req.count,
            exclude_entities=exclude_names,
            niches=req.niches, seasonality=req.seasonality,
        )
    except Exception as exc:  # noqa: BLE001
        # destrava a animação: marca a run como falha antes de propagar o erro
        if run_id:
            try:
                await supa.update_run(run_id, {"status": "failed", "error_message": str(exc)[:400], "completed_at": _now()})
            except Exception:  # noqa: BLE001
                pass
        raise HTTPException(status_code=502, detail=f"Falha na descoberta de entidades: {exc}")
    warnings.extend(result.get("warnings") or [])

    # Mock só é resultado LEGÍTIMO quando não há chave de LLM configurada (modo
    # demo). Se havia chave e mesmo assim voltou mock, as duas tentativas do
    # agente falharam: são entidades de exemplo, genéricas, e persistir isso
    # planta card falso no board (e ainda entra na exclusão das próximas runs).
    # Devolve o resultado visível, mas NÃO persiste, e marca a run como falha.
    if result.get("engine") == "mock" and settings.resolved_gemini_key:
        warnings.append(
            "Agente falhou nas duas tentativas — resultado veio do gerador de exemplo "
            "e NÃO foi salvo no board. Dispare a descoberta de novo."
        )
        if run_id:
            try:
                await supa.update_run(
                    run_id,
                    {"status": "failed", "error_message": "fallback mock (LLM falhou 2x)",
                     "completed_at": _now()},
                )
            except Exception:  # noqa: BLE001
                pass
        return EntityDiscoveryResponse(
            country=req.country,
            country_code=(req.country_code or "").upper() or None,
            native_language=result["meta"].get("native_language"),
            engine="mock", model=result.get("model"), items=[],
            cultural_intelligence=None, personas=[], insights=None,
            persisted=False, created_count=0, merged_count=0, warnings=warnings,
        )

    code = (result["meta"].get("country_code") or req.country_code or "").upper()
    cards: List[Dict[str, Any]] = []
    created = merged = 0

    if not persist:
        cards = [_card_from_item(it) for it in result["entities"]]
        return EntityDiscoveryResponse(
            country=req.country, country_code=code or None, native_language=result["meta"].get("native_language"),
            engine=result["engine"], model=result.get("model"), items=[EntityCard(**c) for c in cards],
            cultural_intelligence=result.get("cultural_intelligence"), personas=result.get("personas") or [],
            insights=result.get("insights"), persisted=False, created_count=0, merged_count=0,
            warnings=warnings + ["Modo dry: cards não persistidos (Supabase indisponível)."],
        )

    # 1b) auto-clean: entidades rejeitadas há mais de 21 dias somem do país
    if code:
        try:
            purged = await supa.purge_rejected_entities(code, days=21)
            if purged:
                warnings.append(f"{purged} entidade(s) rejeitada(s) há +21 dias removida(s).")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Limpeza de rejeitados falhou: {exc}")

    # 2) dedup vs existing entities of this country (runs ADD, never delete)
    existing = await supa.list_entities(code) if code else []

    for item in result["entities"]:
        e = item["entity"]
        cand_keys = entity_keys(e["canonical_name"], e.get("full_name"), e.get("aliases"))
        cand_keys.add(e["slug"])
        # identidade do card (nome/slug) separada dos aliases: alias↔alias não
        # basta pra fundir duas entidades — ver find_matching_entity.
        cand_identity = identity_keys(e["canonical_name"], e.get("full_name"), e["slug"])
        match = find_matching_entity(cand_keys, existing, candidate_identity_keys=cand_identity)
        try:
            if not match:
                # may still exist concurrently -> insert, re-fetch on UNIQUE race
                ent_row = {
                    "run_id": run_id, "country_code": code, "country": req.country,
                    "canonical_name": e["canonical_name"], "full_name": e.get("full_name"),
                    "slug": e["slug"], "entity_type": e.get("entity_type"),
                    "entity_category": e.get("entity_category"), "vertical": e.get("vertical"),
                    "official_source": e.get("official_source"),
                    "related_systems": e.get("related_systems") or [], "aliases": e.get("aliases") or [],
                    "description": e.get("description"), "language": e.get("language"), "source": "agent",
                }
                # niche_slug (coluna da migração v7_11) só é enviada quando a
                # entidade REALMENTE tem nicho (run opt-in) — se vier None/vazio
                # (runs diversificadas, default), a chave é OMITIDA: sem isso,
                # ambientes onde a v7_11 ainda não rodou têm TODA run persistida
                # rejeitada (502) pelo PostgREST por coluna desconhecida.
                if e.get("niche_slug"):
                    ent_row["niche_slug"] = e["niche_slug"]
                try:
                    match = await supa.insert_entity(ent_row)
                except Exception:  # noqa: BLE001 — UNIQUE(country_code,slug) race
                    match = await supa.get_entity_by_slug(code, e["slug"])
                if not match:
                    raise RuntimeError("não foi possível criar/obter a entidade")
                existing.append(match)  # so later items in the batch dedup too
                is_new_entity = True
            else:
                is_new_entity = False
                new_aliases = list(dict.fromkeys([*(match.get("aliases") or []), *(e.get("aliases") or [])]))
                await supa.update_entity(match["id"], {"aliases": new_aliases})

            entity_id = match["id"]
            # one opportunity card per entity (idempotent; re-fetch on UNIQUE race)
            opp = await supa.get_opportunity_by_entity(entity_id)
            if opp:
                opp_id = opp.get("id")
                merged += 1
            else:
                try:
                    opp = await supa.insert_entity_opportunity(_opp_row(item["opportunity"], entity_id, run_id, code))
                except Exception:  # noqa: BLE001 — UNIQUE(entity_id) race
                    opp = await supa.get_opportunity_by_entity(entity_id)
                opp_id = opp.get("id") if opp else None
                created += 1
                # O funil NÃO é criado na descoberta — só na etapa "Funil" (arquiteto).

            # add NEW pains/seed_queries (dedup vs DB)
            await _persist_pains_queries(supa, entity_id, opp_id, item)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Entidade '{e.get('canonical_name')}' não persistida: {exc}")

    # 3) reload the country's cards
    try:
        rows = await supa.list_entity_cards(code) if code else []
        cards = [_card_from_rows(o) for o in rows]
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Releitura de cards falhou: {exc}")

    # 4) finaliza a RUN -> 'completed' com a inteligência produzida (encerra a animação)
    if run_id:
        try:
            await supa.update_run(
                run_id,
                {
                    "status": "completed", "country_code": code or None,
                    "native_language": result["meta"].get("native_language"),
                    "produced_count": len(result["entities"]),
                    "engine": result["engine"], "model": result.get("model"),
                    "cultural_intelligence": result.get("cultural_intelligence"),
                    "personas": result.get("personas"), "insights": result.get("insights"),
                    "completed_at": _now(),
                },
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Run não finalizada: {exc}")

    return EntityDiscoveryResponse(
        run_id=run_id, country=req.country, country_code=code or None,
        native_language=result["meta"].get("native_language"), engine=result["engine"], model=result.get("model"),
        items=[EntityCard(**c) for c in cards], cultural_intelligence=result.get("cultural_intelligence"),
        personas=result.get("personas") or [], insights=result.get("insights"),
        persisted=True, created_count=created, merged_count=merged, warnings=warnings,
    )


@router.post("/entities/manual")
async def create_manual_entity(req: EntityManualCreateRequest) -> Dict[str, Any]:
    """Cria uma entidade MANUALMENTE (default direto em 'Pronto'), p/ sincronizar
    funis já existentes do país. NÃO dispara ClickUp (isso só acontece no arraste
    p/ Pronto via /status). Dedup por (country_code, slug)."""
    # entity_name_key (e não normalize_entity_slug): esta última colapsaria
    # "Aposentadoria pelo INSS" no slug 'inss', que já pertence a outra entidade —
    # a criação manual era descartada em silêncio como "já existia".
    from app.entities.normalize import entity_name_key

    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")
    code = (req.country_code or "").upper()
    name = (req.canonical_name or "").strip()
    if not code or not name:
        raise HTTPException(status_code=422, detail="country_code e canonical_name são obrigatórios.")
    slug = entity_name_key(name) or "entidade"

    # entidade (dedup por country_code+slug; re-fetch em corrida de UNIQUE)
    ent = await supa.get_entity_by_slug(code, slug)
    already_existed = ent is not None
    if not ent:
        ent_row = {
            "country_code": code, "country": req.country, "canonical_name": name,
            "full_name": req.full_name, "slug": slug, "entity_type": req.entity_type,
            "entity_category": req.entity_category, "official_source": req.official_source,
            "related_systems": [], "aliases": req.aliases or [], "description": req.description,
            "language": req.native_language, "status": req.status, "source": "manual",
        }
        try:
            ent = await supa.insert_entity(ent_row)
        except Exception:  # noqa: BLE001 — UNIQUE(country_code,slug) race
            ent = await supa.get_entity_by_slug(code, slug)
    if not ent:
        raise HTTPException(status_code=502, detail="Não foi possível criar a entidade.")
    entity_id = ent["id"]

    # oportunidade (card) — direto no status pedido (default 'ready'), SEM ClickUp
    opp = await supa.get_opportunity_by_entity(entity_id)
    if opp:
        opp = await supa.update_entity_opportunity(
            opp["id"], {"status": req.status, "kanban_stage": req.status}
        ) or opp
    else:
        opp_row = {
            "entity_id": entity_id, "country_code": code,
            "status": req.status, "kanban_stage": req.status,
            "notes": {"manual": True},
        }
        try:
            opp = await supa.insert_entity_opportunity(opp_row)
        except Exception:  # noqa: BLE001 — UNIQUE(entity_id) race
            opp = await supa.get_opportunity_by_entity(entity_id)
    if not opp:
        raise HTTPException(status_code=502, detail="Não foi possível criar a oportunidade.")
    try:
        await supa.update_entity(entity_id, {"status": req.status})
    except Exception:  # noqa: BLE001
        pass

    rows = await supa.list_entity_cards(code)
    card = next((c for c in rows if c.get("id") == opp.get("id")), None)
    if not card:
        raise HTTPException(status_code=502, detail="Card não encontrado após criação.")
    return {"card": EntityCard(**_card_from_rows(card)).model_dump(), "already_existed": already_existed}


@router.post("/entities/enrich")
async def enrich_manual_entity(req: EntityEnrichRequest) -> Dict[str, Any]:
    """Input manual em 'Descobertas': o operador dá só o NOME; o agente SECUNDÁRIO
    preenche o card (metadados + oportunidade + volume estimado + dores + queries) e
    persiste em 'discovered'. Dedup por (country_code, slug)."""
    settings = get_settings()
    supa = SupabaseService(settings)
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")
    code = (req.country_code or "").upper()
    name = (req.canonical_name or "").strip()
    if not code or not name:
        raise HTTPException(status_code=422, detail="country_code e canonical_name são obrigatórios.")

    ctx = _ctx(req.engine, req.model)
    result = await EntityEnrichOrchestrator(ctx).run(req.country, code, req.native_language, name)
    item = result.get("item")
    warnings = list(result.get("warnings") or [])
    if not item:
        raise HTTPException(status_code=502, detail="Não foi possível enriquecer a entidade. " + " ".join(warnings[:2]))

    e = item["entity"]
    slug = e["slug"]
    ent = await supa.get_entity_by_slug(code, slug)
    already_existed = ent is not None
    if not ent:
        ent_row = {
            "run_id": None, "country_code": code, "country": req.country,
            "canonical_name": e["canonical_name"], "full_name": e.get("full_name"), "slug": slug,
            "entity_type": e.get("entity_type"), "entity_category": e.get("entity_category"),
            "vertical": e.get("vertical"), "official_source": e.get("official_source"),
            "related_systems": e.get("related_systems") or [],
            "aliases": e.get("aliases") or [], "description": e.get("description"),
            "language": e.get("language"), "status": "discovered", "source": "manual",
        }
        try:
            ent = await supa.insert_entity(ent_row)
        except Exception:  # noqa: BLE001 — UNIQUE(country_code,slug) race
            ent = await supa.get_entity_by_slug(code, slug)
    if not ent:
        raise HTTPException(status_code=502, detail="Não foi possível criar a entidade.")
    entity_id = ent["id"]

    opp = await supa.get_opportunity_by_entity(entity_id)
    if not opp:
        try:
            opp = await supa.insert_entity_opportunity(_opp_row(item["opportunity"], entity_id, None, code))
        except Exception:  # noqa: BLE001 — UNIQUE(entity_id) race
            opp = await supa.get_opportunity_by_entity(entity_id)
    if not opp:
        raise HTTPException(status_code=502, detail="Não foi possível criar a oportunidade.")
    opp_id = opp.get("id")
    try:
        await _persist_pains_queries(supa, entity_id, opp_id, item)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Dores/queries não persistidas: {exc}")

    rows = await supa.list_entity_cards(code)
    card = next((c for c in rows if c.get("id") == opp_id), None)
    if not card:
        raise HTTPException(status_code=502, detail="Card não encontrado após enriquecer.")
    return {
        "card": EntityCard(**_card_from_rows(card)).model_dump(),
        "already_existed": already_existed, "engine": result.get("engine"), "warnings": warnings,
    }


async def _persist_pains_queries(supa: SupabaseService, entity_id: int, opp_id: Optional[int], item: Dict[str, Any]) -> None:
    existing_pains = await supa.existing_pain_set(entity_id)
    pain_rows, seen_p = [], set(existing_pains)
    for p in item.get("pains") or []:
        key = str(p.get("pain_name", "")).lower().strip()
        if not key or key in seen_p:
            continue
        seen_p.add(key)
        pain_rows.append({"entity_id": entity_id, "opportunity_id": opp_id, "pain_name": p.get("pain_name"),
                          "pain_description": p.get("pain_description"), "user_goal": p.get("user_goal"),
                          "intent": p.get("intent"), "severity": p.get("severity")})
    await supa.insert_pains(pain_rows)

    existing_q = await supa.existing_seed_query_set(entity_id)
    q_rows, seen_q = [], set(existing_q)
    for q in item.get("seed_queries") or []:
        key = str(q.get("query", "")).lower().strip()
        if not key or key in seen_q:
            continue
        seen_q.add(key)
        q_rows.append({"entity_id": entity_id, "opportunity_id": opp_id, "query": q.get("query"),
                       "query_type": q.get("query_type"), "intent": q.get("intent"),
                       "score": q.get("score"), "source": q.get("source")})
    await supa.insert_seed_queries(q_rows)


@router.get("/entity-opportunities", response_model=EntityListResponse)
async def list_entity_opportunities(country: str = Query(..., description="country_code, ex: CO")) -> EntityListResponse:
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        return EntityListResponse(items=[], source="none")
    try:
        rows = await supa.list_entity_cards(country.upper())
        return EntityListResponse(items=[EntityCard(**_card_from_rows(o)) for o in rows], source="supabase")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Supabase error: {exc}")


async def _briefing_model(supa: SupabaseService, opp_row: Dict[str, Any]):
    """Monta o MODELO do briefing a partir da oportunidade.

    O briefing tem duas saídas (o `.docx` anexado na task do ClickUp e a página
    HTML que o operador abre em nova aba) — mas UMA montagem. Se cada saída
    remontasse o par card+funil por conta própria, o anexo e a tela poderiam
    discordar sobre o mesmo card.

    Devolve `None` quando a entidade sumiu: sem entidade não há briefing, e
    inventar um esqueleto vazio seria entregar um documento que mente.
    """
    from datetime import datetime, timezone

    from app.docx import build_briefing_model

    opp_id = opp_row.get("id")
    entity = await supa.get_entity(opp_row["entity_id"]) if opp_row.get("entity_id") else None
    if not entity:
        return None

    # card completo (dores/queries/funis) p/ o composer
    cards = await supa.list_entity_cards(opp_row.get("country_code") or "")
    card = next((c for c in cards if c.get("id") == opp_id), None) or {}
    card.setdefault("entity", entity)
    card["insights"] = opp_row.get("insights")

    # funil: usa a arquitetura RICA persistida; se não houver, degrada p/ hipóteses
    arch = opp_row.get("funnel_architecture") or {}
    if arch.get("pages"):
        funnel = {**arch, "funnel_hypotheses": card.get("funnel_hypotheses") or []}
    else:
        hyps = card.get("funnel_hypotheses") or []
        funnel = {
            "funnel_strategy": {}, "pages": [], "writing_jobs": [],
            "funnel_hypotheses": [
                {"title": h.get("funnel_title"), "summary": h.get("funnel_summary"), "pages": h.get("pages") or []}
                for h in hyps
            ],
        }

    # a data da capa é a data de GERAÇÃO. Antes só o ano era passado e o mês
    # ficava no default do compositor (julho), então todo briefing saía datado
    # de julho — uma data inventada na capa de um documento de trabalho.
    agora = datetime.now(timezone.utc)
    return card, build_briefing_model(card, funnel, month=agora.month, year=agora.year)


async def _dispatch_clickup_briefing(settings, supa: SupabaseService, opp_row: Dict[str, Any]) -> Dict[str, Any]:
    """DESLIGADO no VOLC O.S. — herança do webgo, e a decisão foi concentrar tudo aqui.

    A função continua existindo, e devolvendo a mesma forma de sempre, porque
    ela tem três chamadores e o contrato deles não muda: `dispatched: False`
    com um `reason` já era o caminho normal quando o ClickUp não estava
    configurado. Apagar a função obrigaria a mexer nos três; devolver o no-op
    mantém o comportamento idêntico ao de uma instância sem credencial.

    ## Por que saiu

    O anexo saiu primeiro: documentação em cópia nasce desatualizada no instante
    em que o funil muda. Depois saiu a task inteira — o VOLC O.S. concentra o
    log e o trabalho, e um gerenciador externo dividiria a verdade em dois
    lugares sem ninguém saber qual vale.

    Medido antes de cortar: **0 de 20 cards** tinham `clickup_task_id`. Nenhum
    dado se perdeu porque nunca houve dado.

    As COLUNAS `clickup_task_id` / `clickup_task_url` ficam no banco. Estão
    vazias, e derrubar coluna é destrutivo por um ganho de nada.
    """
    return {"dispatched": False, "reason": "clickup_desligado_no_volc_os"}


@router.patch("/entity-opportunities/{opp_id}/status")
async def update_entity_status(opp_id: int, req: EntityStatusUpdateRequest) -> Dict[str, Any]:
    settings = get_settings()
    supa = SupabaseService(settings)
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")
    prev = await supa.get_entity_opportunity(opp_id)
    prev_status = (prev or {}).get("status")
    values: Dict[str, Any] = {"status": req.status, "kanban_stage": req.status}
    if req.status in ("validating", "ready", "rejected") and req.reviewed_by:
        values["reviewed_by"] = req.reviewed_by
        values["reviewed_at"] = _now()
    row = await supa.update_entity_opportunity(opp_id, values)
    if not row:
        raise HTTPException(status_code=404, detail="Oportunidade de entidade não encontrada.")
    # mirror onto the entity status
    if row.get("entity_id"):
        try:
            await supa.update_entity(row["entity_id"], {"status": req.status})
        except Exception:  # noqa: BLE001
            pass
    out: Dict[str, Any] = {"opportunity": row}
    # O disparo automático para o ClickUp saiu daqui. O VOLC O.S. concentra o
    # log e a documentação; ver `_dispatch_clickup_briefing` para o porquê e
    # para o número que sustentou a decisão (0 de 20 cards tinham task).
    return out


@router.post("/entity-opportunities/{opp_id}/question-choice")
async def record_question_choice(opp_id: int, req: QuestionChoiceRequest) -> Dict[str, Any]:
    """Registra QUAL PERGUNTA vamos atacar (arraste DESCOBERTAS -> EM VALIDAÇÃO).

    A entidade não tem uma pergunta, tem várias — e é por isso que rotular a
    ENTIDADE não funcionou (33,3% de estabilidade contra 23,5% de acaso). Aqui o
    objeto é a pergunta, que é a unidade do gerador de funil.

    NÃO calcula nota, NÃO ordena, NÃO bloqueia: o card move de qualquer forma, e
    é o front que move. Um registro que trava o trabalho deixa de ser preenchido
    em uma semana.
    """
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")
    opp = await supa.get_entity_opportunity(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Oportunidade de entidade não encontrada.")

    candidatas = opp.get("respostas")
    candidatas = candidatas if isinstance(candidatas, list) else []
    escolhida: Dict[str, Any] = {}
    descartadas = list(candidatas)
    if req.outcome == "chosen":
        i = req.chosen_index
        if not isinstance(i, int) or not (0 <= i < len(candidatas)):
            raise HTTPException(
                status_code=422,
                detail=f"chosen_index {i} fora das {len(candidatas)} perguntas candidatas.",
            )
        escolhida = candidatas[i] if isinstance(candidatas[i], dict) else {}
        descartadas = [c for j, c in enumerate(candidatas) if j != i]

    row = {
        "opportunity_id": opp_id,
        "entity_id": opp.get("entity_id"),
        "country_code": opp.get("country_code") or "",
        "outcome": req.outcome,
        "chosen_index": req.chosen_index if req.outcome == "chosen" else None,
        "chosen_frase": escolhida.get("frase"),
        "chosen_engajamento": escolhida.get("engajamento_level"),
        "chosen_ignorancia": escolhida.get("ignorancia_level"),
        "custom_frase": (req.custom_frase or "").strip() or None,
        "custom_engajamento": req.custom_engajamento,
        "custom_ignorancia": req.custom_ignorancia,
        # em `custom` as TRÊS foram recusadas; em `skipped`/`entity_rejected`
        # nenhuma foi escolhida — nos três casos o contrafactual são todas.
        "rejected": descartadas,
        "notes": (req.notes or "").strip() or None,
        "chosen_by": req.chosen_by or None,
    }
    try:
        saved = await supa.insert_question_choice(row)
    except Exception as exc:  # noqa: BLE001
        # a v7_17 pode não ter rodado: o REGISTRO falha, o ARRASTE não. Perder o
        # movimento do card por causa do ledger inverteria a prioridade.
        raise HTTPException(status_code=502, detail=f"Não foi possível registrar a escolha: {exc}")
    return {"choice": saved, "candidatas": len(candidatas)}


async def _briefing_ou_404(opp_id: int):
    """Carrega a oportunidade e devolve o modelo do briefing, ou 404 explicando
    o que faltou. Sem Supabase não há briefing: o documento é feito do que está
    persistido, não de exemplo."""
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")
    row = await supa.get_entity_opportunity(opp_id)
    if not row:
        raise HTTPException(status_code=404, detail="Oportunidade de entidade não encontrada.")
    montado = await _briefing_model(supa, row)
    if montado is None:
        raise HTTPException(
            status_code=404,
            detail="A entidade deste card não foi encontrada — sem entidade não há briefing.",
        )
    return montado[1]


@router.get("/entity-opportunities/{opp_id}/briefing.html", response_class=HTMLResponse)
async def read_briefing_html(opp_id: int) -> HTMLResponse:
    """O briefing renderizado — é esta a página que o operador abre em nova aba.

    Sai do MESMO modelo do `.docx`: o anexo da task continua existindo e virou
    um botão de exportar (`briefing.docx`), não foi substituído.

    Leitura autenticada pelo portão do router (`exigir_usuario`), como todas as
    chave protege o que escreve ou gasta LLM). É o que torna a nova aba possível:
    navegação de topo não carrega cabeçalho `X-API-Key`.
    """
    from app.docx import render_briefing_html

    model = await _briefing_ou_404(opp_id)
    # URL RELATIVA: `briefing.docx` é irmã de `briefing.html` no mesmo caminho,
    # então o botão de exportar continua certo atrás de proxy ou sub-path.
    return HTMLResponse(content=render_briefing_html(model, docx_url="briefing.docx"))


@router.get("/entity-opportunities/{opp_id}/briefing.docx")
async def read_briefing_docx(opp_id: int) -> Response:
    """O mesmo briefing como arquivo do Word — o botão "exportar" da página."""
    from app.docx.funnel_briefing import render_docx

    model = await _briefing_ou_404(opp_id)
    return Response(
        content=render_docx(model),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{model.nome_arquivo_docx}"'},
    )


@router.patch("/entity-opportunities/{opp_id}/complete", dependencies=[Depends(exigir_admin)])
async def set_funnel_completed(opp_id: int, req: EntityCompleteRequest) -> Dict[str, Any]:
    """Baixa do admin: marca (ou desmarca) que o funil foi criado pelo redator.
    Marcado => o card some da coluna Pronto por padrão (não é excluído)."""
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")
    row = await supa.update_entity_opportunity(
        opp_id,
        {"funnel_completed": req.completed, "funnel_completed_at": _now() if req.completed else None},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Oportunidade de entidade não encontrada.")
    return {"opportunity": row}


@router.patch("/entity-opportunities/{opp_id}/insights")
async def save_entity_insights(opp_id: int, req: EntityInsightsRequest) -> Dict[str, Any]:
    """Persiste as anotações livres do usuário (aba Insights) por card."""
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")
    row = await supa.update_entity_opportunity(opp_id, {"insights": req.insights})
    if not row:
        raise HTTPException(status_code=404, detail="Oportunidade de entidade não encontrada.")
    return {"opportunity": row}


@router.patch("/entity-opportunities/{opp_id}/task-description")
async def save_entity_task_description(
    opp_id: int, req: EntityTaskDescriptionRequest
) -> Dict[str, Any]:
    """Descrição da tarefa (v7_14) — vira o corpo da task no ClickUp.

    Distinta de `insights`, que é direcionamento do AGENTE de funil. Nenhuma das
    duas entra no DOCX do briefing.
    """
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")
    value = (req.task_description or "").strip() or None
    try:
        row = await supa.update_entity_opportunity(opp_id, {"task_description": value})
    except Exception as exc:  # noqa: BLE001
        if _is_unknown_column_error(exc, "task_description"):
            raise HTTPException(
                status_code=503,
                detail="Coluna task_description ausente — rode a migração v7_14 no Supabase.",
            )
        raise HTTPException(status_code=502, detail=f"Não foi possível salvar a descrição: {exc}")
    if not row:
        raise HTTPException(status_code=404, detail="Oportunidade de entidade não encontrada.")
    return {"opportunity": row}


@router.patch("/entity-opportunities/{opp_id}/display-title")
async def save_entity_display_title(opp_id: int, req: EntityDisplayTitleRequest) -> Dict[str, Any]:
    """Renomeia o CARD (não a entidade). Vazio volta a exibir o canonical_name."""
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")
    value = (req.display_title or "").strip() or None
    try:
        row = await supa.update_entity_opportunity(opp_id, {"display_title": value})
    except Exception as exc:  # noqa: BLE001
        if _is_unknown_column_error(exc, "display_title"):
            raise HTTPException(
                status_code=503,
                detail="Coluna display_title ausente — rode a migração v7_12 no Supabase.",
            )
        raise HTTPException(status_code=502, detail=f"Não foi possível renomear o card: {exc}")
    if not row:
        raise HTTPException(status_code=404, detail="Oportunidade de entidade não encontrada.")
    return {"opportunity": row}


async def _next_free_entity_slug(supa: SupabaseService, country_code: str, base_slug: str) -> str:
    """Primeiro `{base}-vN` livre em (country_code, slug).

    O slug base nunca é reusado: a cópia é uma entidade nova e
    `uq_pautador_entities_country_slug` proíbe repetir.
    """
    base = (base_slug or "entidade").strip() or "entidade"
    for n in range(2, 100):
        candidate = f"{base}-v{n}"
        if not await supa.get_entity_by_slug(country_code, candidate):
            return candidate
    raise HTTPException(status_code=409, detail="Limite de cópias desta entidade atingido (99).")


@router.post("/entity-opportunities/{opp_id}/duplicate")
async def duplicate_entity_card(
    opp_id: int, req: Optional[EntityDuplicateRequest] = Body(default=None)
) -> Dict[str, Any]:
    """Duplica um card JÁ minerado para rodar a MESMA entidade em outro site.

    O banco tem UMA oportunidade por entidade (`uq_pautador_entity_opportunities_entity`),
    então a cópia é uma entidade nova (slug `-v2`, `-v3`…) levando junto as dores e
    seed queries — que é o token de mineração que se quer reaproveitar.

    A cópia nasce em 'mining' e LIMPA do que é específico do site anterior:
    sem insights (que agora dirige o agente de funil), sem funil, sem task do
    ClickUp e sem baixa dada.
    """
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")

    opp = await supa.get_entity_opportunity(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Oportunidade de entidade não encontrada.")
    entity = await supa.get_entity(opp.get("entity_id")) if opp.get("entity_id") else None
    if not entity:
        raise HTTPException(status_code=404, detail="Entidade do card não encontrada.")

    code = (opp.get("country_code") or entity.get("country_code") or "").upper()
    warnings: List[str] = []
    display_title = ((req.display_title if req else "") or "").strip()

    new_slug = await _next_free_entity_slug(supa, code, entity.get("slug") or "")
    ent_row = {
        "run_id": entity.get("run_id"), "country_code": code, "country": entity.get("country"),
        "canonical_name": entity.get("canonical_name"), "full_name": entity.get("full_name"),
        "slug": new_slug, "entity_type": entity.get("entity_type"),
        "entity_category": entity.get("entity_category"), "vertical": entity.get("vertical"),
        "official_source": entity.get("official_source"),
        "related_systems": entity.get("related_systems") or [],
        "aliases": entity.get("aliases") or [], "description": entity.get("description"),
        "language": entity.get("language"), "status": "mining", "source": entity.get("source") or "agent",
    }
    if entity.get("niche_slug"):
        ent_row["niche_slug"] = entity["niche_slug"]
    try:
        new_entity = await supa.insert_entity(ent_row)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Não foi possível criar a cópia da entidade: {exc}")
    if not new_entity:
        raise HTTPException(status_code=502, detail="Não foi possível criar a cópia da entidade.")

    opp_row: Dict[str, Any] = {
        "entity_id": new_entity["id"], "run_id": opp.get("run_id"), "country_code": code,
        "status": "mining", "kanban_stage": "mining",
        **{k: opp.get(k) for k in _OPP_COLS},
    }
    if display_title:
        opp_row["display_title"] = display_title
    async def _rollback_entity() -> None:
        """A entidade é criada ANTES do card. Se o card não nascer, a entidade
        ficaria órfã: invisível no Kanban (que é dirigido pelas oportunidades),
        mas viva no dedup e na lista de exclusão da descoberta."""
        try:
            await supa.delete_entity(new_entity["id"])
        except Exception:  # noqa: BLE001 — best-effort; o erro original é o que importa
            pass

    new_opp = None
    try:
        new_opp = await supa.insert_entity_opportunity(opp_row)
    except Exception as exc:  # noqa: BLE001
        # migração v7_12 ausente: duplicar é útil demais pra falhar pelo rótulo
        if display_title and _is_unknown_column_error(exc, "display_title"):
            opp_row.pop("display_title", None)
            try:
                new_opp = await supa.insert_entity_opportunity(opp_row)
            except Exception as exc2:  # noqa: BLE001
                await _rollback_entity()
                raise HTTPException(status_code=502, detail=f"Não foi possível criar o card da cópia: {exc2}")
            warnings.append("Nome de exibição não salvo — rode a migração v7_12 no Supabase.")
        else:
            await _rollback_entity()
            raise HTTPException(status_code=502, detail=f"Não foi possível criar o card da cópia: {exc}")
    if not new_opp:
        await _rollback_entity()
        raise HTTPException(status_code=502, detail="Não foi possível criar o card da cópia.")

    # dores e seed queries: o material minerado que a cópia reaproveita
    src_cards = await supa.list_entity_cards(code)
    src = next((c for c in src_cards if c.get("id") == opp_id), {})
    new_eid, new_oid = new_entity["id"], new_opp["id"]
    pain_rows = [
        {"entity_id": new_eid, "opportunity_id": new_oid, "pain_name": p.get("pain_name"),
         "pain_description": p.get("pain_description"), "user_goal": p.get("user_goal"),
         "intent": p.get("intent"), "severity": p.get("severity")}
        for p in (src.get("pains") or []) if p.get("pain_name")
    ]
    query_rows = [
        {"entity_id": new_eid, "opportunity_id": new_oid, "query": q.get("query"),
         "query_type": q.get("query_type"), "intent": q.get("intent"),
         "score": q.get("score"), "source": q.get("source")}
        for q in (src.get("seed_queries") or []) if q.get("query")
    ]
    try:
        await supa.insert_pains(pain_rows)
        await supa.insert_seed_queries(query_rows)
    except Exception as exc:  # noqa: BLE001
        # o card já existe e é utilizável; a mineração pode ser refeita
        warnings.append(f"Dores/queries não copiadas: {exc}")

    cards = await supa.list_entity_cards(code)
    row = next((c for c in cards if c.get("id") == new_oid), None)
    if not row:
        raise HTTPException(status_code=502, detail="Cópia criada, mas não foi possível recarregá-la.")
    return {"card": _card_from_rows(row), "warnings": warnings}


@router.delete("/entity-opportunities/{opp_id}", dependencies=[Depends(exigir_admin)])
async def delete_entity_opportunity(opp_id: int) -> Dict[str, Any]:
    """Exclui o card (entidade + oportunidade + dores/queries/funis por cascade).
    Usado na aba Rejeitado para o usuário remover manualmente."""
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado.")
    opp = await supa.get_entity_opportunity(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Oportunidade de entidade não encontrada.")
    entity_id = opp.get("entity_id")
    if entity_id:
        await supa.delete_entity(entity_id)  # cascade remove a oportunidade e filhos
    else:
        await supa.delete("pautador_entity_opportunities", {"id": f"eq.{opp_id}"})
    return {"deleted": True, "opportunity_id": opp_id, "entity_id": entity_id}


@router.post("/entity-opportunities/{opp_id}/validate")
async def validate_entity(opp_id: int, body: Optional[EntityStatusUpdateRequest] = Body(default=None)) -> Dict[str, Any]:
    """Valida UM card. É a exceção cara — prefira `/validate-batch`.

    A base de US$ 0,012 por chamada domina na cauda curta: os dois nós lotáveis
    (histórico e tráfego) pagam a base inteira para um card só. O relatório
    devolve `custo_individual_estimado_usd` justamente para isso ficar visível.
    """
    req = EntityStatusUpdateRequest(status="validating", reviewed_by=body.reviewed_by if body else None)
    resultado = await update_entity_status(opp_id, req)
    relatorio = await _medir_eixos([opp_id], modo="individual")
    return {**resultado, "validacao": relatorio}


@router.get("/entity-opportunities/{opp_id}/axes")
async def entity_axes(opp_id: int) -> Dict[str, Any]:
    """Os eixos JÁ GRAVADOS deste card. Barato, sem efeito, para acompanhar.

    A medição leva ~30s e o POST só responde no fim — mas a escrita é
    INCREMENTAL: cada eixo grava assim que é medido. Este GET existe para a
    tela ler esse progresso do banco em vez de fingir um.

    Não é enfeite: é a arquitetura de gravação idempotente ficando visível. O
    mesmo mecanismo que faz re-arrastar refazer só o que falta é o que faz a
    barra de volume preencher quando o histórico volta, e não antes.
    """
    settings = get_settings()
    supa = SupabaseService(settings)
    if not supa.enabled:
        return {"eixos": [], "total": 0}
    linhas = await supa.select(
        "pautador_entity_axes",
        {"opportunity_id": f"eq.{opp_id}",
         "select": "eixo,nivel,proveniencia,motivo_ausencia,medido_em",
         "order": "medido_em.asc"},
    )
    return {"eixos": linhas, "total": len(linhas)}


@router.post("/entity-opportunities/validate-batch")
async def validate_entities_batch(body: EntityValidateBatchRequest) -> Dict[str, Any]:
    """Valida a coluna inteira numa passada. **Este é o caminho padrão.**

    O histórico e o tráfego de domínio são lotáveis: 20 cards numa chamada
    pagam a base uma vez em vez de vinte. O relatório traz os dois números —
    o que foi pago e o que teria custado card a card.
    """
    settings = get_settings()
    supa = SupabaseService(settings)
    if not supa.enabled:
        raise HTTPException(status_code=503, detail="Supabase não configurado")

    ids = list(body.opportunity_ids or [])
    if not ids and body.country_code:
        linhas = await supa.select(
            "pautador_entity_opportunities",
            {"country_code": f"eq.{body.country_code.upper()}",
             "status": f"eq.{body.status or 'validating'}",
             "select": "id", "limit": str(body.limite or 50)},
        )
        ids = [int(r["id"]) for r in linhas]
    if not ids:
        return {"validacao": {"cards": 0, "custo_usd": 0.0}, "aviso": "nenhum card selecionado"}

    return {"validacao": await _medir_eixos(
        ids, modo="lote", engine=body.engine, model=body.model, refazer=bool(body.refazer))}


async def _medir_eixos(opportunity_ids: List[int], *, modo: str,
                       engine: Optional[str] = None, model: Optional[str] = None,
                       refazer: bool = False) -> Dict[str, Any]:
    """Preenche os eixos e grava. Nunca levanta: medir é acessório ao arraste.

    Se a medição falhar, o card já mudou de coluna e o operador não fica preso
    — o erro volta no corpo, não como 500.
    """
    from app.validacao import Validador

    settings = get_settings()
    supa = SupabaseService(settings)
    try:
        rel = await Validador(settings, supa, engine=engine, model=model).validar(
            opportunity_ids, modo=modo, refazer=refazer)
        return rel.json()
    except Exception as exc:  # noqa: BLE001
        log.exception("validação falhou para %s", opportunity_ids)
        return {"cards": 0, "custo_usd": 0.0, "erros": [str(exc)[:300]]}


async def _dispatch_n8n_kw(settings, entity: Dict[str, Any], opp_id: Optional[int]) -> tuple[bool, Optional[str]]:
    """Dispara o webhook do n8n com a entidade + geo (do dataset 195) + linkagem.
    O flow n8n minera e escreve o resultado direto no Supabase (async)."""
    import httpx

    from app.data.countries import resolve_country

    geo = resolve_country(entity.get("country"), code=entity.get("country_code")) or {}
    payload = {
        "entity_id": entity.get("id"),
        "opportunity_id": opp_id,
        "run_id": entity.get("run_id"),
        "country": entity.get("country"),
        "country_code": geo.get("country_code") or entity.get("country_code"),
        "nicho": entity.get("canonical_name") or entity.get("full_name"),
        "objective": entity.get("description") or f"Mineração de KW da entidade {entity.get('canonical_name')}",
        "geo_target": geo.get("google_ads_geo_target"),
        "language_code": geo.get("language_code"),
        "language_short": geo.get("language_short"),
        "language_constant": geo.get("language_constant"),
    }
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.post(settings.pautador_n8n_kw_webhook_url, json=payload)
            resp.raise_for_status()
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"Falha ao disparar o webhook n8n: {exc}"


@router.post("/entities/{entity_id}/mine", response_model=EntityMineResponse)
async def mine_entity(entity_id: int, body: Optional[EntityMineRequest] = Body(default=None)) -> EntityMineResponse:
    settings = get_settings()
    supa = SupabaseService(settings)
    ctx = _ctx(body.engine if body else None, body.model if body else None)

    entity = None
    from_db = False
    if supa.enabled:
        entity = await supa.get_entity(entity_id)
        from_db = entity is not None
    if not entity and body and body.entity:
        entity = {**body.entity, "id": entity_id}
    if not entity:
        raise HTTPException(status_code=404, detail="Entidade não encontrada. Forneça 'entity' no corpo (dry).")

    # --- n8n: dispara o webhook (o flow externo minera e grava no Supabase) ---
    dispatch_warn = None
    if settings.pautador_n8n_kw_webhook_url and from_db:
        opp_wh = await supa.get_opportunity_by_entity(entity_id)
        opp_id_wh = opp_wh.get("id") if opp_wh else None
        ok, dispatch_warn = await _dispatch_n8n_kw(settings, entity, opp_id_wh)
        if ok:
            try:
                if opp_id_wh:
                    await supa.update_entity_opportunity(opp_id_wh, {"status": "mining", "kanban_stage": "mining"})
                await supa.update_entity(entity_id, {"status": "mining"})
            except Exception:  # noqa: BLE001
                pass
            return EntityMineResponse(
                entity_id=entity_id, opportunity_id=opp_id_wh, pains=[], seed_queries=[],
                services_used=["n8n:webhook"], engine="n8n", mode="n8n", dispatched=True,
                persisted=False, warnings=[],
            )

    result = await EntityMineOrchestrator(ctx).run(entity)
    warnings = list(result.get("warnings") or [])
    if dispatch_warn:
        warnings.append(dispatch_warn)
    persisted = False
    opp_id = None

    persist_pref = body.persist if (body and body.persist is not None) else settings.pautador_persist_default
    if persist_pref and supa.enabled and from_db:
        try:
            opp = await supa.get_opportunity_by_entity(entity_id)
            opp_id = opp.get("id") if opp else None
            await _persist_pains_queries(supa, entity_id, opp_id, result)
            if opp_id:
                await supa.update_entity_opportunity(opp_id, {"status": "mining", "kanban_stage": "mining"})
            await supa.update_entity(entity_id, {"status": "mining"})
            persisted = True
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Persistência falhou (rodou v7_03?): {exc}")

    return EntityMineResponse(
        entity_id=entity_id, opportunity_id=opp_id, pains=result["pains"], seed_queries=result["seed_queries"],
        services_used=result.get("services_used") or [], engine=result.get("engine") or "mock",
        persisted=persisted, warnings=warnings,
    )


@router.post("/entity-opportunities/{opp_id}/funnel", response_model=EntityFunnelResponse)
async def entity_funnel(opp_id: int, body: Optional[EntityFunnelRequest] = Body(default=None)) -> EntityFunnelResponse:
    settings = get_settings()
    supa = SupabaseService(settings)
    ctx = _ctx(body.engine if body else None, body.model if body else None)

    entity = None
    entity_id = None
    pains: List[Dict[str, Any]] = []
    seed_queries: List[Dict[str, Any]] = []
    from_db = False
    # v7_12: o que o admin escreveu na aba Insights DESTE card vira direcionamento
    # do arquiteto de funil. Card sem texto => prompt idêntico ao de antes.
    admin_direction: Optional[str] = None
    # O que a coluna de validação mediu. `None` quando o card pulou a etapa —
    # e aí o arquiteto recebe exatamente o que recebia antes.
    validacao: Optional[Dict[str, Any]] = None

    if supa.enabled:
        opp = await supa.get_entity_opportunity(opp_id)
        if opp:
            from_db = True
            admin_direction = opp.get("insights")
            validacao = opp.get("validacao")
            entity_id = opp.get("entity_id")
            entity = await supa.get_entity(entity_id) if entity_id else None
            if entity_id:
                cards = await supa.list_entity_cards(opp.get("country_code") or "")
                for c in cards:
                    if c.get("id") == opp_id:
                        pains = c.get("pains") or []
                        seed_queries = c.get("seed_queries") or []
                        break
    if not entity and body and body.entity:
        entity = body.entity
        entity_id = entity.get("id")
    if not entity:
        raise HTTPException(status_code=404, detail="Entidade/oportunidade não encontrada. Forneça 'entity' no corpo (dry).")

    # A validação desce como CONTEXTO. Sem ela (card que pulou a coluna), o
    # arquiteto recebe exatamente o que recebia antes — nada muda.
    result = await EntityFunnelOrchestrator(ctx).run(
        entity, pains, seed_queries, admin_direction=admin_direction,
        validacao=validacao,
    )
    warnings = list(result.get("warnings") or [])
    persisted = False

    persist_pref = body.persist if (body and body.persist is not None) else settings.pautador_persist_default
    if persist_pref and supa.enabled and from_db:
        try:
            rows = [
                {"entity_id": entity_id, "opportunity_id": opp_id, "country_code": entity.get("country_code"),
                 "funnel_title": h.get("title"), "funnel_summary": h.get("summary"), "pages": h.get("pages") or []}
                for h in result["funnel_hypotheses"] if h.get("title")
            ]
            await supa.insert_funnel_hypotheses(rows)
            # guarda a arquitetura RICA (pages c/ H2 + writing_jobs) p/ o DOCX do briefing
            architecture = {
                "funnel_strategy": result.get("funnel_strategy") or {},
                "pages": result.get("pages") or [],
                "writing_jobs": result.get("writing_jobs") or [],
            }
            await supa.update_entity_opportunity(
                opp_id,
                {"status": "funnel", "kanban_stage": "funnel", "funnel_architecture": architecture},
            )
            if entity_id:
                await supa.update_entity(entity_id, {"status": "funnel"})
            persisted = bool(rows)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Persistência falhou (rodou v7_03?): {exc}")

    return EntityFunnelResponse(
        entity_id=entity_id or 0, opportunity_id=opp_id,
        funnel_hypotheses=_norm_funnels(result["funnel_hypotheses"]),
        funnel_strategy=result.get("funnel_strategy"),
        pages=result.get("pages") or [],
        writing_jobs=result.get("writing_jobs") or [],
        services_used=result.get("services_used") or [], engine=result.get("engine") or "mock",
        persisted=persisted, warnings=warnings,
    )
