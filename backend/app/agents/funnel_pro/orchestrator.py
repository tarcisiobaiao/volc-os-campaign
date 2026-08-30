"""
Funnel Builder Orchestrator (Fase 3) — wires the n8n funnel-builder workflow:

  FunnelArchitect (Gemini, architect prompt) -> PageFactory (writingJobs)

Input is one mined opportunity + its keyword cluster (supporting_data). The
architect returns {funnel_strategy, pages}; PageFactory turns pages into
writingJobs; the pages are also mapped to the canonical FunnelPage rows used by
the DB + existing drawer. Falls back to a deterministic 5-page funnel when no
Gemini key is configured.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.agents.base import AgentContext, BaseAgent
from app.agents.funnel_pro.page_factory import architect_pages_to_funnel_pages, page_factory
from app.n8n_prompts import FUNNEL_ARCHITECT_SYSTEM_MESSAGE, build_funnel_architect_user


class FunnelProOrchestrator(BaseAgent):
    name = "FunnelBuilderAgent"
    phase = "funnel"

    def __init__(
        self,
        ctx: AgentContext,
        model_override: Optional[str] = None,
        forced_language: Optional[str] = None,
        admin_direction: Optional[str] = None,
    ):
        super().__init__(ctx)
        self.settings = ctx.settings
        self.model_override = model_override
        # R3: locale COMPLETO forçado (ex.: "es-DO") — vem de resolve_country(...)
        # via o caller (EntityFunnelOrchestrator/Task 8). Opcional: mantém
        # compatibilidade com callers legados que não passam esse kwarg.
        self.forced_language = forced_language
        # v7_12: texto escrito pelo admin no campo Insights do card. Vira um bloco
        # no fim da missão do arquiteto. Vazio/ausente = prompt idêntico ao de antes.
        self.admin_direction = admin_direction
        self.services_used: List[str] = []
        self.warnings: List[str] = []

    def _gemini(self):
        if not self.settings.resolved_gemini_key:
            return None
        from app.llm.gemini import GeminiClient

        return GeminiClient(self.settings, model=self.model_override or self.settings.pautador_funnel_gemini_model)

    @staticmethod
    def _supporting_data(cluster: Optional[Dict[str, Any]], opportunity: Dict[str, Any]) -> str:
        """Build the <supporting_data> blob.

        R9 — grounding semântico anti-branco: combina as keywords MINERADAS do
        cluster (quando existem) com a base semântica da própria oportunidade
        (`reasoning`/`description`, `variations`/aliases, `expansion_hooks`
        /sistemas relacionados). Isso garante que o arquiteto SEMPRE recebe
        material rico para se agarrar — nunca colapsa para só
        `- {main_keyword}` enquanto houver qualquer sinal semântico disponível
        (mesmo com cluster vazio, ex.: funil disparado antes/sem mineração).
        """
        lines: List[str] = []

        if cluster:
            ads = cluster.get("production_ads_queue") or []
            for k in ads[:30]:
                lines.append(f"- {k.get('keyword')} (vol: {k.get('volume')}, cpc: {k.get('cpc')})")
            if not ads:
                for k in (cluster.get("keywords") or [])[:30]:
                    lines.append(f"- {k.get('keyword')} (vol: {k.get('volume')}, cpc: {k.get('cpc_local') or k.get('cpc')})")

        reasoning = opportunity.get("reasoning") or opportunity.get("description")
        if reasoning:
            lines.append(f"- Contexto/descrição: {reasoning}")

        variations = [str(v) for v in (opportunity.get("variations") or []) if v]
        if variations:
            lines.append(f"- Variações/aliases: {', '.join(variations[:15])}")

        hooks = [str(h) for h in (opportunity.get("expansion_hooks") or []) if h]
        if hooks:
            lines.append(f"- Ganchos/dores/sistemas relacionados: {', '.join(hooks[:15])}")

        if not lines:
            lines.append(f"- {opportunity.get('main_keyword') or opportunity.get('keyword')}")

        return "\n".join(lines)

    @staticmethod
    def _user_questions(cluster: Optional[Dict[str, Any]], opportunity: Dict[str, Any]) -> str:
        """Build the <user_questions> blob.

        R9 — reforça a fila SEO minerada (`content_seo_queue`) com os ganchos
        semânticos da própria oportunidade (`expansion_hooks`), e só recorre às
        `variations` como último recurso — nunca fica vazia quando há base
        semântica disponível.
        """
        questions: List[str] = []

        if cluster:
            for k in (cluster.get("content_seo_queue") or [])[:15]:
                kw = k.get("keyword")
                if kw:
                    questions.append(str(kw))

        for h in [str(h) for h in (opportunity.get("expansion_hooks") or []) if h][:10]:
            if h not in questions:
                questions.append(h)

        if not questions:
            questions = [str(v) for v in (opportunity.get("variations") or []) if v][:10]

        return "\n".join(f"- {q}" for q in questions) or "(sem perguntas mapeadas)"

    async def run(self, opportunity: Dict[str, Any], cluster: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        start = self._timer()
        pais = opportunity.get("country") or ""
        tema = opportunity.get("main_keyword") or opportunity.get("keyword") or "tema"
        # R3: idioma forçado (locale COMPLETO, ex.: "es-DO") tem prioridade sobre
        # o native_language da oportunidade — fallback preserva callers legados
        # que não passam `forced_language`.
        lingua = self.forced_language or opportunity.get("native_language") or ""
        data_atual = datetime.now(timezone.utc).strftime("%d/%m/%Y")
        supporting = self._supporting_data(cluster, opportunity)
        questions = self._user_questions(cluster, opportunity)

        client = self._gemini()
        if client is None:
            # Sem chave Gemini configurada = modo mock/dry LEGÍTIMO (não é o
            # caso de "arquiteto vazio" do R9) — mantém o fallback determinístico
            # de hoje, já alimentado pela base semântica reforçada acima.
            self.services_used.append("funnel_architect:fallback")
            architect = self._fallback_architect(tema, opportunity)
        else:
            architect, exc_to_report = await self._call_architect_with_retry(
                client, pais=pais, tema=tema, lingua=lingua, data_atual=data_atual,
                supporting=supporting, questions=questions,
            )
            if architect is None:
                # R9 — sem fallback silencioso: um funil SEMPRE é produzido (a
                # estrutura determinística é a rede de segurança final), mas o
                # aviso é explícito e prominente — nunca mascarado.
                if exc_to_report is not None:
                    self.warnings.append(f"Funnel Architect (LLM) falhou, usando fallback: {exc_to_report}")
                else:
                    self.warnings.append(
                        "Arquiteto vazio mesmo com base semântica reforçada — usando estrutura base; revisar."
                    )
                self.services_used.append("funnel_architect:fallback")
                architect = self._fallback_architect(tema, opportunity)

        factory = page_factory(architect)
        pages = architect_pages_to_funnel_pages(architect, persona_fallback=opportunity.get("persona") or "")
        strategy = architect.get("funnel_strategy") or {}

        funnel_name = f"Funil: {tema}"

        self.log(
            f"Funil construído: {len(pages)} páginas, {len(factory['writingJobs'])} writing jobs.",
            step="funnel",
            duration_ms=self._elapsed_ms(start),
            payload={"funnel_name": funnel_name},
        )

        return {
            "opportunity_id": opportunity.get("id"),
            "run_id": opportunity.get("run_id"),
            "funnel_name": funnel_name,
            "funnel_strategy": strategy,
            "pages": pages,
            "writing_jobs": factory["writingJobs"],
            "raw_output": architect,
            "services_used": self.services_used,
            "warnings": self.warnings,
        }

    async def _call_architect_with_retry(
        self,
        client: Any,
        *,
        pais: str,
        tema: str,
        lingua: str,
        data_atual: str,
        supporting: str,
        questions: str,
    ) -> tuple[Optional[Dict[str, Any]], Optional[Exception]]:
        """Chama o Arquiteto (Gemini). R9: se ele vier vazio (`pages` ausente/
        vazio), RE-TENTA UMA VEZ com a MESMA base semântica reforçada (a
        temperatura 0.9 do modelo pode produzir um resultado diferente na 2ª
        chamada — ver Global Constraints do plano). Retorna `(architect, None)`
        em caso de sucesso, ou `(None, exc)`/`(None, None)` para o caller decidir
        o aviso: `exc` presente = falha real de chamada (não insiste, cai direto
        no fallback); `None`/`None` = as duas tentativas vieram vazias.
        """
        for attempt in range(2):
            try:
                user = build_funnel_architect_user(
                    pais=pais, tema=tema, lingua=lingua, data_atual=data_atual,
                    supporting_data=supporting, user_questions=questions,
                    admin_direction=self.admin_direction,
                )
                candidate = await client.complete_json(FUNNEL_ARCHITECT_SYSTEM_MESSAGE, user)
            except Exception as exc:  # noqa: BLE001
                return None, exc
            if isinstance(candidate.get("pages"), list) and candidate["pages"]:
                self.services_used.append(
                    "gemini:funnel_architect" if attempt == 0 else "gemini:funnel_architect_retry"
                )
                return candidate, None
        return None, None

    def _fallback_architect(self, tema: str, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic 5-page architect output (no LLM)."""
        slug_base = (tema or "tema").lower().replace(" ", "-")
        page_types = ["LANDING PAGE", "HUB", "SOLUÇÃO", "SOLUÇÃO", "SOLUÇÃO"]
        objectives = [
            "Nomear a dor e gerar identificação imediata",
            "Qualificar (SE PODE) e mapear as soluções (hub)",
            "Passo a passo da ação principal",
            "Comparar opções e apresentar prova",
            "Ação concreta, documentos e captura",
        ]
        pages = []
        for i in range(5):
            nxt = f"{slug_base}-p{i + 2}" if i < 4 else ""
            pages.append(
                {
                    "page_number": i + 1,
                    "page_type": page_types[i],
                    "h1_title": f"{tema} — página {i + 1}",
                    "slug": f"{slug_base}-p{i + 1}",
                    "emotional_objective": objectives[i],
                    "main_content_structure": [
                        f"H2: Bloco {i + 1}.{j} ({tema})" for j in range(1, 5)
                    ],
                    "hook_to_next_page": "Avançar →" if i < 4 else "Concluir",
                    "next_page_slug": nxt,
                    "target_keywords": list(opportunity.get("variations") or [])[:3] or [tema],
                }
            )
        return {
            "funnel_strategy": {
                "avatar_summary": opportunity.get("persona") or "[mock] Público-alvo do tema",
                "tone_voice": "[mock] Informativo, direto, orientado à ação",
                "total_pages": 5,
            },
            "pages": pages,
        }
