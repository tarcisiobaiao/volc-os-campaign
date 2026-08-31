"""
Supabase persistence via PostgREST (service-role key, server-side ONLY).

The service role BYPASSES RLS — this key must never reach the frontend; it
lives only in this backend's env (SUPABASE_SERVICE_ROLE_KEY). All writes by
the agent pipeline go through here.

If Supabase is not configured, SupabaseService.enabled is False and the
router runs in "dry" mode (returns results without persisting).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings

# Columns we persist per table (whitelist — agent dicts carry extra derived keys)
_OPP_COLUMNS = [
    "run_id", "seed_id", "country", "native_language",
    "keyword", "main_keyword", "keyword_pt_translation",
    "tier", "category",
    "volume_estimate", "rpm_potential", "competition_estimate", "confidence",
    "intent", "timing",
    "cpc_estimate_local", "cpc_min", "cpc_max", "cpc_avg", "currency",
    "arbitrage_score", "estimated_roi_signal",
    "persona", "pain_point", "reasoning", "variations", "expansion_hooks",
    "status", "source",
]


class SupabaseService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base = (settings.supabase_url or "").rstrip("/")
        self.key = settings.supabase_service_role_key or ""

    @property
    def enabled(self) -> bool:
        return bool(self.base and self.key)

    def _headers(self, prefer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base}/rest/v1/{path}"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.request(method, url, **kwargs)
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

    # ---- generic ------------------------------------------------------------
    async def insert(self, table: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not rows:
            return []
        data = await self._request(
            "POST", table, headers=self._headers("return=representation"), json=rows
        )
        return data or []

    async def select(self, table: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = await self._request("GET", table, headers=self._headers(), params=params)
        return data or []

    # O PostgREST do Supabase corta toda resposta em `db-max-rows` (1000 neste
    # projeto) e IGNORA um `limit` maior: pedir limit=5000 devolve 1000 linhas
    # sem erro nenhum. Quem precisa do conjunto inteiro tem que paginar.
    PAGE_SIZE = 1000

    async def select_all(
        self, table: str, params: Dict[str, Any], max_rows: int = 50_000
    ) -> List[Dict[str, Any]]:
        """SELECT paginado — devolve TODAS as linhas que casam com `params`.

        Sem isso, uma lista grande é truncada em silêncio: foi assim que as seed
        queries das entidades mais recentes sumiram do card (BR já passa de 1300
        linhas). Ordena por `id` quando o caller não pede outra ordem — offset sem
        ORDER BY estável pode repetir/pular linhas entre páginas.
        """
        page_params = {**params, "order": params.get("order") or "id.asc"}
        page_params.pop("limit", None)
        out: List[Dict[str, Any]] = []
        offset = 0
        while offset < max_rows:
            page = await self.select(
                table, {**page_params, "limit": self.PAGE_SIZE, "offset": offset}
            )
            out.extend(page)
            if len(page) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE
        return out

    async def rpc(self, funcao: str, argumentos: Dict[str, Any]) -> Any:
        """Chama uma função do Postgres via `POST /rest/v1/rpc/<funcao>`.

        É a única forma de fazer várias escritas numa transação só daqui: cada
        requisição PostgREST é uma transação independente, então uma sequência de
        `insert`/`patch` pode parar no meio e deixar metade do fato gravado. Uma
        função é uma requisição, logo um `BEGIN/COMMIT`.

        ⚠️ O erro NÃO é engolido. O corpo de um 4xx do PostgREST carrega o
        SQLSTATE, e é ele que separa "uma guarda do banco recusou" de "o banco
        está fora do ar" — duas situações que exigem reações opostas de quem
        chama. `raise_for_status()` em `_request` preserva a resposta dentro da
        `HTTPStatusError`.
        """
        return await self._request(
            "POST", f"rpc/{funcao}", headers=self._headers(), json=argumentos
        )

    async def patch(self, table: str, match: Dict[str, str], values: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = await self._request(
            "PATCH", table, headers=self._headers("return=representation"),
            params=match, json=values,
        )
        return data or []

    # ---- high-level: runs ---------------------------------------------------
    async def create_run(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self.insert("pautador_runs", [payload])
        return rows[0] if rows else None

    async def update_run(self, run_id: int, values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self.patch("pautador_runs", {"id": f"eq.{run_id}"}, values)
        return rows[0] if rows else None

    async def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        rows = await self.select("pautador_runs", {"id": f"eq.{run_id}", "limit": 1})
        return rows[0] if rows else None

    async def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.select(
            "pautador_runs", {"order": "created_at.desc", "limit": limit}
        )

    # ---- high-level: opportunities -----------------------------------------
    async def insert_opportunities(self, run_id: int, opps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows = []
        for o in opps:
            row = {k: o.get(k) for k in _OPP_COLUMNS if k in o}
            row["run_id"] = run_id
            rows.append(row)
        return await self.insert("pautador_opportunities", rows)

    async def get_opportunity(self, opp_id: int) -> Optional[Dict[str, Any]]:
        rows = await self.select(
            "pautador_opportunities", {"id": f"eq.{opp_id}", "limit": 1}
        )
        return rows[0] if rows else None

    async def list_opportunities(self, run_id: int) -> List[Dict[str, Any]]:
        return await self.select(
            "pautador_opportunities",
            {"run_id": f"eq.{run_id}", "order": "arbitrage_score.desc"},
        )

    async def update_opportunity(self, opp_id: int, values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self.patch("pautador_opportunities", {"id": f"eq.{opp_id}"}, values)
        return rows[0] if rows else None

    # ---- high-level: clusters / funnels ------------------------------------
    async def insert_cluster(self, cluster: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self.insert("pautador_keyword_clusters", [cluster])
        return rows[0] if rows else None

    async def get_latest_cluster(self, opportunity_id: int) -> Optional[Dict[str, Any]]:
        rows = await self.select(
            "pautador_keyword_clusters",
            {"opportunity_id": f"eq.{opportunity_id}", "order": "created_at.desc", "limit": 1},
        )
        return rows[0] if rows else None

    async def insert_funnel_pages(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return await self.insert("pautador_funnels", pages)

    # ---- high-level: ENTITY-FIRST ------------------------------------------
    async def list_entities(self, country_code: str) -> List[Dict[str, Any]]:
        # Paginado de propósito: esta lista alimenta (1) a exclusão do prompt de
        # descoberta e (2) o dedup contra o que já existe. Truncar aqui não "economiza",
        # faz o agente redescobrir o que foi cortado e o dedup deixar passar duplicata.
        return await self.select_all(
            "pautador_entities", {"country_code": f"eq.{country_code}"}
        )

    async def insert_entity(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self.insert("pautador_entities", [row])
        return rows[0] if rows else None

    async def update_entity(self, entity_id: int, values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self.patch("pautador_entities", {"id": f"eq.{entity_id}"}, values)
        return rows[0] if rows else None

    async def get_entity(self, entity_id: int) -> Optional[Dict[str, Any]]:
        rows = await self.select("pautador_entities", {"id": f"eq.{entity_id}", "limit": 1})
        return rows[0] if rows else None

    async def get_entity_by_slug(self, country_code: str, slug: str) -> Optional[Dict[str, Any]]:
        rows = await self.select(
            "pautador_entities",
            {"country_code": f"eq.{country_code}", "slug": f"eq.{slug}", "limit": 1},
        )
        return rows[0] if rows else None

    async def get_opportunity_by_entity(self, entity_id: int) -> Optional[Dict[str, Any]]:
        rows = await self.select(
            "pautador_entity_opportunities", {"entity_id": f"eq.{entity_id}", "limit": 1}
        )
        return rows[0] if rows else None

    async def insert_entity_opportunity(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self.insert("pautador_entity_opportunities", [row])
        return rows[0] if rows else None

    async def update_entity_opportunity(self, opp_id: int, values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self.patch("pautador_entity_opportunities", {"id": f"eq.{opp_id}"}, values)
        return rows[0] if rows else None

    async def get_entity_opportunity(self, opp_id: int) -> Optional[Dict[str, Any]]:
        rows = await self.select(
            "pautador_entity_opportunities", {"id": f"eq.{opp_id}", "limit": 1}
        )
        return rows[0] if rows else None

    # ---- high-level: escolha de PERGUNTA (v7_17) ----------------------------
    async def insert_question_choice(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Grava a escolha. NUNCA faz update: o operador pode revisitar e
        escolher de novo, e a segunda escolha é informação — sobrescrever a
        primeira apagaria o histórico que esta tabela existe para criar."""
        rows = await self.insert("pautador_question_choices", [row])
        return rows[0] if rows else None

    async def latest_question_choice(self, opportunity_id: int) -> Optional[Dict[str, Any]]:
        rows = await self.select(
            "pautador_question_choices",
            {"opportunity_id": f"eq.{opportunity_id}", "order": "chosen_at.desc", "limit": 1},
        )
        return rows[0] if rows else None

    async def existing_seed_query_set(self, entity_id: int) -> set:
        rows = await self.select(
            "pautador_entity_seed_queries", {"entity_id": f"eq.{entity_id}", "select": "query", "limit": 1000}
        )
        return {str(r.get("query", "")).lower().strip() for r in rows}

    async def existing_pain_set(self, entity_id: int) -> set:
        rows = await self.select(
            "pautador_entity_pains", {"entity_id": f"eq.{entity_id}", "select": "pain_name", "limit": 1000}
        )
        return {str(r.get("pain_name", "")).lower().strip() for r in rows}

    async def insert_seed_queries(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return await self.insert("pautador_entity_seed_queries", rows) if rows else []

    async def insert_pains(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return await self.insert("pautador_entity_pains", rows) if rows else []

    async def insert_funnel_hypotheses(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return await self.insert("pautador_entity_funnel_hypotheses", rows) if rows else []

    async def list_entity_cards(self, country_code: str) -> List[Dict[str, Any]]:
        """Kanban cards for a country: opportunities + embedded entity + children."""
        opps = await self.select_all(
            "pautador_entity_opportunities",
            {
                "country_code": f"eq.{country_code}",
                "select": "*,entity:pautador_entities!entity_id(*)",
                "order": "score.desc.nullslast,id.asc",
            },
        )
        if not opps:
            return []
        opp_ids = [str(o["id"]) for o in opps if o.get("id") is not None]
        ent_ids = [str(o["entity_id"]) for o in opps if o.get("entity_id") is not None]
        in_opps = "(" + ",".join(opp_ids) + ")"
        in_ents = "(" + ",".join(ent_ids) + ")"
        # paginado: um país com muitas entidades passa fácil das 1000 linhas de
        # filhos, e o corte silencioso some com as dores/queries dos cards mais
        # recentes (exatamente os recém-minerados/duplicados).
        pains = await self.select_all("pautador_entity_pains", {"entity_id": f"in.{in_ents}"}) if ent_ids else []
        queries = await self.select_all("pautador_entity_seed_queries", {"entity_id": f"in.{in_ents}"}) if ent_ids else []
        funnels = await self.select_all("pautador_entity_funnel_hypotheses", {"opportunity_id": f"in.{in_opps}"}) if opp_ids else []

        def _by(rows, key):
            out: Dict[Any, List[Dict[str, Any]]] = {}
            for r in rows:
                out.setdefault(r.get(key), []).append(r)
            return out

        pains_by = _by(pains, "entity_id")
        queries_by = _by(queries, "entity_id")
        funnels_by = _by(funnels, "opportunity_id")
        for o in opps:
            o["pains"] = pains_by.get(o.get("entity_id"), [])
            o["seed_queries"] = queries_by.get(o.get("entity_id"), [])
            o["funnel_hypotheses"] = funnels_by.get(o.get("id"), [])
        return opps

    async def delete(self, table: str, match: Dict[str, str]) -> None:
        await self._request("DELETE", table, headers=self._headers("return=minimal"), params=match)

    async def delete_entity(self, entity_id: int) -> None:
        """Delete an entity (cascade removes its opportunity/pains/queries/funnels)."""
        await self.delete("pautador_entities", {"id": f"eq.{entity_id}"})

    async def purge_rejected_entities(self, country_code: str, days: int = 21) -> int:
        """Delete entities whose card is 'rejected' for more than `days` (auto-clean)."""
        from datetime import datetime, timezone, timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = await self.select(
            "pautador_entity_opportunities",
            {
                "country_code": f"eq.{country_code}",
                "status": "eq.rejected",
                "updated_at": f"lt.{cutoff}",
                "select": "entity_id",
                "limit": 1000,
            },
        )
        ids = [str(r["entity_id"]) for r in rows if r.get("entity_id") is not None]
        if not ids:
            return 0
        await self.delete("pautador_entities", {"id": f"in.({','.join(ids)})"})
        return len(ids)

    # ---- high-level: nichos (R1) --------------------------------------------
    async def list_niches(self) -> List[Dict[str, Any]]:
        return await self.select(
            "pautador_niches", {"is_active": "eq.true", "order": "sort_order.asc"}
        )

    async def insert_niche(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self.insert("pautador_niches", [payload])
        return rows[0] if rows else None

    # ---- high-level: logs ---------------------------------------------------
    async def insert_logs(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not rows:
            return []
        try:
            return await self.insert("pautador_agent_logs", rows)
        except Exception:  # noqa: BLE001 — logs are best-effort, never fail the request
            return []
