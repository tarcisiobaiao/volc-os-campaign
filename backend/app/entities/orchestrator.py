"""
Entity-first orchestrators (discovery / mine / funnel). Build entities via
Gemini (discovery model) when a key exists, else deterministic mock. Validate
with Pydantic, normalize slugs, compute auditable scores, and dedup within the
batch. DB-level dedup (across runs) happens in the router/service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.agents.base import AgentContext, BaseAgent
from app.data.countries import resolve_country
from app.data.niches import resolve_niches
from app.entities.mock import (
    mock_entity_discovery,
    mock_entity_enrich,
    mock_entity_funnel,
    mock_entity_mine,
)
from app.entities.normalize import (
    entity_name_key,
    suggest_official_source,
)
from app.entities.prompts import (
    ENTITY_DISCOVERY_SYSTEM_PROMPT,
    ENTITY_ENRICH_SYSTEM_PROMPT,
    ENTITY_FUNNEL_SYSTEM_PROMPT,
    ENTITY_MINE_SYSTEM_PROMPT,
    build_entity_discovery_mission,
    build_entity_enrich_mission,
    build_entity_funnel_mission,
    build_entity_mine_mission,
)
from app.entities.leitura import (
    canonical_levels,
    compute_reading_gate,
    frase_representativa,
    respostas_validas,
)
from app.entities.schemas import EntityDiscoveryItem
from app.entities.scoring import compute_entity_score
from app.services.supabase_service import SupabaseService


def _gemini(settings, model: Optional[str] = None):
    if not settings.resolved_gemini_key:
        return None
    from app.llm.gemini import GeminiClient

    return GeminiClient(settings, model=model or settings.pautador_gemini_model)


def _norm_item(item: Dict[str, Any], country: str, country_code: Optional[str], language: Optional[str]) -> Dict[str, Any]:
    """Validate + normalize one entity item (slug, source, score)."""
    validated = EntityDiscoveryItem(**item)
    ent = validated.entity.model_dump()
    opp = validated.opportunity.model_dump()

    canonical = (ent.get("canonical_name") or "").strip()
    # Fallback com entity_name_key (não normalize_entity_slug): esta última colapsa
    # o nome na sigla que ele contém, então "Pagamento do INSS" e "Aposentadoria
    # pelo INSS" cairiam no MESMO slug 'inss' — e o UNIQUE(country_code, slug)
    # fundiria as duas entidades no banco, independente do dedup por nome.
    slug = ent.get("slug") or entity_name_key(canonical)
    if not slug:
        slug = entity_name_key(canonical) or "entidade"
    ent["slug"] = slug

    # official_source: keep the LLM's, else infer a related acronym (DIAN in "rut dian")
    aliases_text = " ".join(ent.get("aliases") or [])
    ent["official_source"] = suggest_official_source(
        f"{canonical} {aliases_text}", ent.get("official_source")
    )

    score, roi, score_source = compute_entity_score(opp)
    # O portão de LEITURA anda AO LADO do score, nunca no lugar dele: o score diz
    # se o mercado paga, o portão diz se a pessoa lê. Nas 20 entidades medidas a
    # correlação entre os dois ranqueamentos foi −0,092 — onde discordam é
    # exatamente onde há decisão a tomar.
    gate = compute_reading_gate(opp, termo=canonical, country_code=country_code)
    niveis = canonical_levels(opp)

    def _nivel(campo: str) -> Optional[str]:
        """Grava o rótulo canônico quando ele é válido; senão, o CRU do agente.
        A coluna não tem CHECK (perder a entidade por um rótulo torto é o erro
        caro), então o torto precisa ficar visível para se depurar o prompt."""
        canon = niveis.get(campo)
        if canon:
            return canon
        bruto = opp.get(f"{campo}_level")
        return str(bruto).strip() if isinstance(bruto, str) and bruto.strip() else None

    return {
        "entity": {
            "canonical_name": canonical,
            "full_name": ent.get("full_name"),
            "slug": slug,
            "entity_type": ent.get("type"),
            "entity_category": ent.get("category"),
            "vertical": ent.get("vertical"),
            "official_source": ent.get("official_source"),
            "related_systems": ent.get("related_systems") or [],
            "aliases": ent.get("aliases") or [],
            "description": ent.get("description"),
            "country_code": (country_code or "").upper() or None,
            "country": country,
            "language": language,
            "niche_slug": ent.get("niche_slug"),
        },
        "opportunity": {
            "gold_tier": opp.get("gold_tier"),
            "strategic_stage": opp.get("strategic_stage"),
            "score": score,
            "score_source": score_source,
            "estimated_volume": opp.get("estimated_volume"),
            "ecpm_band": opp.get("ecpm_band"),
            "roi_signal": roi,
            "cpc_min": opp.get("cpc_min"),
            "cpc_max": opp.get("cpc_max"),
            "cpc_currency": opp.get("cpc_currency"),
            "volume_level": opp.get("volume_level"),
            "rpm_level": opp.get("rpm_level"),
            "competition_level": opp.get("competition_level"),
            "confidence_level": opp.get("confidence_level"),
            "temporal_window": opp.get("temporal_window"),
            # as três frases (jsonb) + a que sustenta o rótulo vencedor
            "respostas": respostas_validas(opp),
            "resposta_em_uma_frase": frase_representativa(opp, niveis.get("engajamento")),
            "ignorancia_level": _nivel("ignorancia"),
            "engajamento_level": _nivel("engajamento"),
            "opacidade_level": _nivel("opacidade"),
            "reading_blocked": gate["bloqueado"],
            "reading_reason": gate["motivo"],
            "reading_strength": gate["forca"],
            "concrete_pain": opp.get("concrete_pain"),
            "gold_reason": opp.get("gold_reason"),
        },
        "pains": [p.model_dump() for p in validated.pains],
        "seed_queries": [q.model_dump() for q in validated.seed_queries],
        # O funil NÃO nasce na descoberta — é criado só na etapa "Funil" (arquiteto).
        "funnel_hypotheses": [],
    }


def _validation_summary(exc: Exception, limit: int = 4) -> str:
    """Resumo curto e ÚTIL de um erro do Pydantic: campo + motivo.

    A mensagem crua ocupa várias linhas e, cortada no toast, vira só
    "2 validation errors for EntityDiscoveryItem" — que não diz o que faltou.
    """
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return str(exc).splitlines()[0]
    try:
        detalhes = [
            f"{'.'.join(str(p) for p in e.get('loc') or []) or '?'}: {e.get('msg')}"
            for e in errors()[:limit]
        ]
    except Exception:  # noqa: BLE001
        return str(exc).splitlines()[0]
    return "; ".join(detalhes) or str(exc).splitlines()[0]


# Fração mínima dos itens devolvidos que precisa passar no contrato para a
# resposta valer. Aceitar "pelo menos 1" deixaria passar a run de 20 itens em que
# só 1 presta — que é o mesmo prejuízo de uma run vazia, só que silencioso.
MIN_VALID_RATIO = 0.6

# NÃO pedir "de sobra" para compensar os filtros de nicho/sazonalidade: medido em
# BR, pedir 20 leva 81s de geração e pedir 29 leva 130s — acima do timeout, a run
# inteira falha e cai no mock. O ganho (~4 entidades) não paga o risco; se um dia
# for reconsiderado, tem que vir junto com timeout maior.


def _usable_entities(raw: Any, min_ratio: float = MIN_VALID_RATIO) -> bool:
    """A resposta é aproveitável, ou vale gastar uma 2ª chamada?

    Barra três casos que custam a run inteira: resposta vazia, formato fora do
    contrato (o modelo às vezes ignora o aninhamento entity/opportunity) e
    resposta majoritariamente inválida.
    """
    if not isinstance(raw, dict):
        return False
    items = raw.get("entities") or []
    if not items:
        return False
    validos = 0
    for item in items:
        try:
            EntityDiscoveryItem(**item)
            validos += 1
        except Exception:  # noqa: BLE001
            continue
    return validos > 0 and (validos / len(items)) >= min_ratio


class EntityDiscoveryOrchestrator(BaseAgent):
    name = "EntityDiscoveryAgent"
    phase = "discovery"

    async def run(
        self, country: str, country_code: Optional[str], native_language: Optional[str],
        count: int, exclude_entities: Optional[List[str]] = None,
        niches: Optional[List[str]] = None, seasonality: Optional[str] = None,
    ) -> Dict[str, Any]:
        start = self._timer()
        warnings: List[str] = []
        client = _gemini(self.ctx.settings)

        # tier + idioma do país (dataset) -> o agente adapta o MIX de verticais ao
        # eCPM do tier, e o idioma nativo (locale, ex. "pt-BR"/"es-DO") é FORÇADO no
        # prompt em vez de pedir para o modelo "detectar" (corrige vazamento de idioma).
        geo = resolve_country(country, code=country_code) or {}
        forced_language = geo.get("native_language") or None

        # nichos-alvo (R1): resolve os slugs pedidos via Supabase (fallback seed) —
        # niches=[] (padrão) => resolved_niches=[] => comportamento atual (diversificado).
        req_niche_slugs = [s for s in (niches or []) if s]
        resolved_niches: List[Dict[str, Any]] = []
        if req_niche_slugs:
            db_rows: Optional[List[Dict[str, Any]]] = None
            try:
                supa = SupabaseService(self.ctx.settings)
                if supa.enabled:
                    rows = await supa.list_niches()
                    if rows:
                        db_rows = rows
            except Exception as exc:  # noqa: BLE001 — Supabase indisponível: cai pro seed
                warnings.append(f"Nichos do Supabase indisponíveis, usando seed: {exc}")
            resolved_niches = resolve_niches(req_niche_slugs, db_rows=db_rows)

        if client is None:
            engine = "mock"
            raw = mock_entity_discovery(
                country, country_code, native_language, count,
                niches=resolved_niches or None, seasonality=seasonality, forced_language=forced_language,
            )
        else:
            engine = "gemini"
            today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
            mission = build_entity_discovery_mission(
                country, count=count, today=today, exclude_entities=exclude_entities,
                market_tier=geo.get("market_tier") or "",
                niches=resolved_niches or None, seasonality=seasonality, forced_language=forced_language,
            )
            # Uma resposta inaproveitável (erro de chamada, JSON impossível de
            # reparar, ou schema fora do contrato) custa a run inteira: o fallback
            # mock devolve entidades genéricas que os filtros de nicho derrubam,
            # e o operador vê "a descoberta trouxe 1". Como o modelo roda a 0.9,
            # a 2ª tentativa costuma sair correta — mesma tática do arquiteto de
            # funil (R9). Só cai pro mock se as DUAS falharem.
            raw, lang_err = None, None
            for attempt in range(2):
                try:
                    candidate = await client.complete_json(ENTITY_DISCOVERY_SYSTEM_PROMPT, mission)
                except Exception as exc:  # noqa: BLE001
                    lang_err = exc
                    continue
                if _usable_entities(candidate):
                    raw = candidate
                    if attempt:
                        warnings.append("1ª resposta do agente veio fora do contrato; a 2ª foi usada.")
                    break
                lang_err = ValueError("resposta sem entidades utilizáveis (fora do contrato)")
            if raw is None:
                warnings.append(f"Entity discovery (LLM) falhou, usando mock: {lang_err}")
                engine = "mock"
                raw = mock_entity_discovery(
                    country, country_code, native_language, count,
                    niches=resolved_niches or None, seasonality=seasonality, forced_language=forced_language,
                )

        meta = raw.get("meta") or {}
        lang = native_language or meta.get("native_language")
        code = (country_code or meta.get("country_code") or "").upper() or None

        normalized: List[Dict[str, Any]] = []
        by_slug: Dict[str, Dict[str, Any]] = {}
        for item in raw.get("entities") or []:
            try:
                norm = _norm_item(item, country, code, lang)
            except Exception as exc:  # noqa: BLE001
                # detalhe do erro (campos que faltaram), não só a contagem: sem
                # isso um desvio de schema do modelo é indiagnosticável no toast.
                warnings.append(f"Entidade ignorada (inválida): {_validation_summary(exc)}")
                continue
            slug = norm["entity"]["slug"]
            if slug in by_slug:
                # merge into the existing entity in-batch
                existing = by_slug[slug]
                existing["pains"].extend(norm["pains"])
                existing["seed_queries"].extend(norm["seed_queries"])
                existing["funnel_hypotheses"].extend(norm["funnel_hypotheses"])
                existing["entity"]["aliases"] = list(
                    dict.fromkeys([*existing["entity"]["aliases"], *norm["entity"]["aliases"]])
                )
                continue
            by_slug[slug] = norm
            normalized.append(norm)
            if len(norm["pains"]) < 2:
                warnings.append(f"Entidade '{norm['entity']['canonical_name']}' com <2 dores.")
            if len(norm["seed_queries"]) < 3:
                warnings.append(f"Entidade '{norm['entity']['canonical_name']}' com <3 seed queries.")

        # --- descarte por nicho-alvo / sazonalidade (R1/R2) -----------------------
        # Backward-compat: niches=[]/seasonality=None (defaults) -> nenhum bloco roda,
        # nada é descartado (comportamento atual, diversificado).
        if resolved_niches:
            wanted_slugs = {n.get("slug") for n in resolved_niches if n.get("slug")}
            allowed_verticals = {v for n in resolved_niches for v in (n.get("allowed_verticals") or [])}
            kept: List[Dict[str, Any]] = []
            discarded = 0
            for norm in normalized:
                n_slug = norm["entity"].get("niche_slug")
                if n_slug:
                    ok = n_slug in wanted_slugs
                else:
                    # fallback: sem niche_slug do LLM, decide pelo `vertical`
                    ok = (norm["entity"].get("vertical") in allowed_verticals) if allowed_verticals else True
                if ok:
                    kept.append(norm)
                else:
                    discarded += 1
            if discarded:
                warnings.append(f"{discarded} entidade(s) descartada(s) fora do nicho selecionado.")
            normalized = kept

        if seasonality:
            wanted_windows = {"Perene"} if seasonality == "evergreen" else {"Sazonal", "Evento"}
            kept = []
            discarded = 0
            for norm in normalized:
                if norm["opportunity"].get("temporal_window") in wanted_windows:
                    kept.append(norm)
                else:
                    discarded += 1
            if discarded:
                warnings.append(f"{discarded} entidade(s) descartada(s) fora da sazonalidade selecionada.")
            normalized = kept

        self.log(f"Entidades descobertas: {len(normalized)} ({engine}).", step="discover", duration_ms=self._elapsed_ms(start))
        return {
            "meta": {**meta, "country": country, "country_code": code, "native_language": lang},
            "cultural_intelligence": raw.get("cultural_intelligence"),
            "personas": raw.get("personas") or [],
            "insights": raw.get("insights"),
            "entities": normalized,
            "engine": engine,
            "model": client.model if client else "mock",
            "warnings": warnings,
        }


class EntityEnrichOrchestrator(BaseAgent):
    """Agente SECUNDÁRIO: recebe o NOME de 1 entidade (input manual do operador) e
    preenche o mesmo card da descoberta principal (metadados + oportunidade + dores +
    seed queries), pra a entidade cair em 'Descobertas' já completa."""
    name = "EntityEnrichAgent"
    phase = "discovery"

    async def run(self, country: str, country_code: Optional[str], native_language: Optional[str], canonical_name: str) -> Dict[str, Any]:
        start = self._timer()
        warnings: List[str] = []
        client = _gemini(self.ctx.settings)
        if client is None:
            engine = "mock"
            raw = mock_entity_enrich(country, country_code, canonical_name)
        else:
            engine = "gemini"
            today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
            mission = build_entity_enrich_mission(country, canonical_name, today=today)
            try:
                raw = await client.complete_json(ENTITY_ENRICH_SYSTEM_PROMPT, mission)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Enriquecimento (LLM) falhou, usando mock: {exc}")
                engine = "mock"
                raw = mock_entity_enrich(country, country_code, canonical_name)

        code = (country_code or "").upper() or None
        items = raw.get("entities") or []
        item = None
        if items:
            try:
                item = _norm_item(items[0], country, code, native_language)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Item de enriquecimento inválido: {exc}")
        else:
            warnings.append("Enriquecimento não retornou entidade.")

        self.log(
            f"Entidade enriquecida: {item['entity']['canonical_name'] if item else '—'} ({engine}).",
            step="enrich", duration_ms=self._elapsed_ms(start),
        )
        return {"item": item, "engine": engine, "model": client.model if client else "mock", "warnings": warnings}


class EntityMineOrchestrator(BaseAgent):
    name = "EntityMineAgent"
    phase = "mining"

    async def run(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        start = self._timer()
        warnings: List[str] = []
        services: List[str] = []
        client = _gemini(self.ctx.settings)
        if client is None:
            services.append("entity_mine:mock")
            raw = mock_entity_mine(entity)
            engine = "mock"
        else:
            engine = "gemini"
            try:
                raw = await client.complete_json(ENTITY_MINE_SYSTEM_PROMPT, build_entity_mine_mission(entity))
                services.append("gemini:entity_mine")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Entity mine (LLM) falhou, usando mock: {exc}")
                raw = mock_entity_mine(entity)
                services.append("entity_mine:mock")
                engine = "mock"

        pains = [p for p in (raw.get("pains") or []) if isinstance(p, dict) and p.get("pain_name")]
        seed_queries = [q for q in (raw.get("seed_queries") or []) if isinstance(q, dict) and q.get("query")]
        self.log(f"Entidade minerada: {len(pains)} dores, {len(seed_queries)} queries.", step="mine", duration_ms=self._elapsed_ms(start))
        return {"pains": pains, "seed_queries": seed_queries, "services_used": services, "engine": engine, "warnings": warnings}


def _com_tensao(admin_direction: Optional[str],
                validacao: Optional[Dict[str, Any]]) -> Optional[str]:
    """Acrescenta a TENSÃO à direção do arquiteto — como observação, não regra.

    ## O que sobe, e por que só isto

    A tensão é o eixo mais confiável da validação: AC1 de Gwet 0,76 com input
    fixo, contra 0,64 dos eixos de forma. E é o único que diz com que AFLIÇÃO a
    pessoa chega, que é matéria-prima do `emotional_objective` — hoje inferido
    pelo arquiteto sem nenhum dado.

    Sobe a FRASE EM PRIMEIRA PESSOA da tabela (`psique.TENSOES[t]["pergunta"]`),
    não o nome técnico. "tem dinheiro meu parado que eu não sei sacar?" é o que
    a pessoa sentiria ao digitar; `dinheiro_esquecido` é jargão nosso e não
    ajuda quem escreve.

    ## O tom é decisão, não descuido

    O bloco diz "observação" e "você decide se e como usar", e NÃO diz nada como
    "explore a urgência". O arquiteto já teve o núcleo alarmista reescrito para
    um frame informacional/benefício (ver o cabeçalho de `n8n_prompts/
    funnel_builder.py`); mandar intensidade emocional por aqui reintroduziria,
    pela porta dos fundos, exatamente o que aquela reescrita tirou.

    ## O que NÃO sobe

    A `intensidade` da tabela (0,64 a 0,84). Ela é PRIOR COM DÍVIDA — veio de um
    desfecho contaminado por `spend` — e já viaja marcada assim no card. Um
    número desses no prompt vira régua de ênfase sem ter sido medido para isso.

    Sem tensão reconhecida, devolve a direção original intacta. Entidade que
    chega fria é informação, não falha — e o prompt não muda de tamanho à toa.
    """
    ent = (validacao or {}).get("ficha") or {}
    tensao = ent.get("tensao_dominante")
    if not tensao or tensao == "nenhuma":
        return admin_direction

    from app.motor_pautas.psique import TENSOES
    frase = (TENSOES.get(tensao) or {}).get("pergunta")
    if not frase:
        return admin_direction

    n = ent.get("distribuicao_de_tensao", {}).get(tensao)
    total = ent.get("n_perguntas")
    quantas = f" ({n} de {total} perguntas)" if n and total else ""

    bloco = (
        "\n\n<observacao_de_leitura>\n"
        "Medição da coluna de validação, sobre as perguntas reais que as pessoas "
        f"fazem sobre este tema{quantas}. É CONTEXTO, não instrução:\n\n"
        f'A pessoa chega perguntando, em silêncio: "{frase}"\n\n'
        "Você decide se e como isso entra na arquitetura. Mantenha o tom "
        "informacional e útil que este briefing já pede — a observação existe "
        "para você acertar o ângulo, nunca para aumentar a temperatura do texto."
        "\n</observacao_de_leitura>"
    )
    return (admin_direction or "") + bloco


class EntityFunnelOrchestrator(BaseAgent):
    name = "EntityFunnelAgent"
    phase = "funnel"

    async def run(
        self,
        entity: Dict[str, Any],
        pains: List[Dict[str, Any]],
        seed_queries: List[Dict[str, Any]],
        admin_direction: Optional[str] = None,
        validacao: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Roda o ARQUITETO do FUNNEL.json (ipsis litteris) via gemini-3.5-flash,
        no worker Python interno. supporting_data = seed_queries; user_questions = dores.

        `admin_direction` (v7_12) = o que o admin escreveu no campo Insights DESTE card.
        Desce como bloco no fim da missão do arquiteto. Vazio = prompt inalterado."""
        from app.agents.funnel_pro.orchestrator import FunnelProOrchestrator

        start = self._timer()

        # R3: idioma forçado = locale COMPLETO do país da entidade (ex.: "es-DO"),
        # NUNCA o ISO de 2 letras (`language_code`/`language_short`) — ver Global
        # Constraints/Task 5. Fallback preserva entidades sem país resolvível.
        geo = resolve_country(entity.get("country"), code=entity.get("country_code")) or {}
        forced_language = (
            geo.get("native_language") or entity.get("language") or entity.get("native_language")
        )

        # R9: entidade -> opportunity-like + cluster-like para o arquiteto,
        # carregando o MESMO stack semântico da descoberta (description/aliases/
        # related_systems/pains) — o arquiteto nunca deve receber material
        # trivial só porque a mineração (seed_queries) veio curta.
        pain_names = [p.get("pain_name") for p in (pains or []) if p.get("pain_name")]
        expansion_hooks = list(dict.fromkeys([
            *(entity.get("related_systems") or []),
            *pain_names,
            *([entity.get("concrete_pain")] if entity.get("concrete_pain") else []),
        ]))
        opp_like = {
            "id": entity.get("id"),
            "run_id": entity.get("run_id"),
            "country": entity.get("country"),
            "native_language": forced_language,
            "keyword": entity.get("canonical_name"),
            "main_keyword": entity.get("canonical_name") or entity.get("full_name"),
            "persona": entity.get("official_source"),
            "reasoning": entity.get("description"),
            "variations": entity.get("aliases") or [],
            "expansion_hooks": expansion_hooks,
        }
        # ── A VALIDAÇÃO ENTRA PELO CANAL QUE JÁ TEM CONTRATO ────────────────
        #
        # O `<comando>` do arquiteto diz, literalmente: "Integre as
        # `user_questions` obrigatoriamente nos **H2s e FAQs**". Ou seja: este
        # canal alimenta SEÇÃO, nunca ESTRUTURA. A arquitetura de 5 páginas
        # TOFU→BOFU sai do protocolo `Bridge Utility` dele, e nada aqui a toca.
        #
        # O que sobe: as perguntas REAIS do bloco "As pessoas também perguntam"
        # do Google, com a resposta que o modelo escreveu. É estritamente melhor
        # que a `content_seo_queue` de dores, porque é a pergunta como a pessoa
        # digitou, não como nós a nomeamos.
        #
        # ⚠️ O QUE **NÃO** SOBE, E É O PONTO TODO: o `formato_da_pergunta`
        # (`sustenta` / `pede ferramenta` / `não sustenta`) e qualquer contagem
        # de páginas. Isso é leitura da PERGUNTA e vive no card, para o
        # operador. Mandar "4 perguntas → 4 páginas" para cá seria prescrição de
        # estrutura entrando por um canal de conteúdo, e o arquiteto poderia
        # devolver 4 páginas em vez das 5 do protocolo dele. A camada nova
        # ACRESCENTA contexto; ela não legisla sobre o funil.
        perguntas_paa = []
        for q in ((validacao or {}).get("ficha") or {}).get("perguntas") or []:
            pergunta = str(q.get("pergunta") or "").strip()
            if not pergunta:
                continue
            resposta = str(q.get("resposta_literal") or "").strip()
            perguntas_paa.append(
                {"keyword": f"{pergunta} — {resposta}" if resposta else pergunta})

        cluster_like = {
            "keywords": [{"keyword": q.get("query")} for q in (seed_queries or []) if q.get("query")],
            # PAA primeiro (é o que o Google diz que perguntam), dores depois.
            "content_seo_queue": [
                *perguntas_paa,
                *[{"keyword": f"{p.get('pain_name')}: {p.get('pain_description')}" if p.get("pain_description") else p.get("pain_name")}
                  for p in (pains or []) if p.get("pain_name")],
            ],
            "production_ads_queue": [],
        }

        # ── A TENSÃO, como CONTEXTO e nunca como ordem ──────────────────────
        #
        # Ela é a peça mais confiável do motor de validação (AC1 de Gwet 0,76
        # com input fixo, contra 0,64 dos eixos de forma) e é a única que diz
        # com que ALFLIÇÃO a pessoa chega. Isso alimenta o `emotional_objective`
        # do arquiteto, que hoje ele infere sozinho.
        #
        # Desce pelo `admin_direction` — o canal que já existe para "o que o
        # operador quer nesta pauta" — e vai EXPLICITAMENTE marcada como
        # observação, não como regra. O tom é preservado de propósito: o
        # arquiteto já tem um frame informacional/benefício (a versão alarmista
        # foi reescrita), e mandar "a pessoa está desesperada" convidaria de
        # volta o terrorismo que aquela reescrita tirou.
        direcao = _com_tensao(admin_direction, validacao)

        architect = FunnelProOrchestrator(
            self.ctx,
            model_override=self.ctx.settings.pautador_entity_funnel_model,
            forced_language=forced_language,
            admin_direction=direcao,
        )
        built = await architect.run(opp_like, cluster=cluster_like)

        # R7: revisor (backstop determinístico) roda ANTES de apply_roles_and_slugs.
        # Invisível (só logs, nunca no payload de resposta) e fail-open: qualquer
        # falha inesperada aqui (além do fail-open já garantido dentro do próprio
        # agente) preserva o funil ORIGINAL do arquiteto — um funil deve SEMPRE
        # ser entregue. Quando o revisor devolve páginas, pages/writing_jobs
        # canônicos são REGENERADOS a partir da saída revisada, pra ficarem em
        # sincronia caso páginas tenham sido fundidas/derrubadas/reordenadas.
        from app.agents.funnel_pro.page_factory import architect_pages_to_funnel_pages, page_factory
        from app.agents.funnel_pro.reviewer import FunnelReviewer

        entity_facts = {
            "canonical_name": entity.get("canonical_name"),
            "full_name": entity.get("full_name"),
            "official_source": entity.get("official_source"),
            "related_systems": entity.get("related_systems") or [],
            "description": entity.get("description"),
        }
        try:
            reviewed = await FunnelReviewer(self.ctx).review(
                built.get("raw_output") or {"funnel_strategy": built.get("funnel_strategy"), "pages": []},
                entity_facts=entity_facts,
                forced_language=forced_language,
            )
            reviewed_arch = {
                "funnel_strategy": reviewed.get("funnel_strategy") or {},
                "pages": reviewed.get("pages") or [],
            }
            if reviewed_arch["pages"]:
                # R8: o revisor pode fundir/derrubar páginas, deixando
                # `page_number` não-contíguo (ex.: 1,3,4,5). `apply_roles_and_slugs`
                # (via `architect_pages_to_funnel_pages`/`page_factory`) atribui
                # papéis/sufixos de slug a partir de `page_number` -> um gap
                # mislabela o funil (ex.: Pre-sell sumindo). Renumera 1..N na
                # ORDEM atual das páginas revisadas (idempotente/no-op quando já
                # contíguo); slugs são re-derivados por `apply_roles_and_slugs`
                # a partir da posição, não é preciso tocar em `next_page_slug`.
                for _idx, _p in enumerate(reviewed_arch["pages"], start=1):
                    _p["page_number"] = _idx
                built["raw_output"] = reviewed_arch
                built["funnel_strategy"] = reviewed_arch["funnel_strategy"]
                built["pages"] = architect_pages_to_funnel_pages(
                    reviewed_arch, persona_fallback=entity.get("official_source") or ""
                )
                built["writing_jobs"] = page_factory(reviewed_arch)["writingJobs"]
            if reviewed.get("changes"):
                self.log(
                    f"Revisor aplicou {len(reviewed['changes'])} correção(ões).",
                    step="funnel", level="debug",
                )
        except Exception as exc:  # noqa: BLE001 — belt-and-suspenders: revisor nunca deve quebrar a entrega
            self.log(f"Revisor ignorado (falha inesperada): {exc}", step="funnel", level="warning")

        strategy = built.get("funnel_strategy") or {}
        # papéis (LP/Pre-sell/Solução) + sufixos de slug (-pr/-p1/-p2…), com as
        # referências cruzadas reescritas — uma vez, determinístico por posição.
        from app.entities.funnel_roles import apply_roles_and_slugs
        pages, writing_jobs = apply_roles_and_slugs(
            built.get("pages") or [], built.get("writing_jobs") or []
        )
        # 1 hipótese = o funil arquitetado (título + páginas), p/ o card do Kanban
        hyps = [{
            "title": built.get("funnel_name") or f"Funil: {entity.get('canonical_name')}",
            "summary": strategy.get("avatar_summary") or strategy.get("tone_voice") or "",
            "pages": [p.get("page_title") for p in pages if p.get("page_title")],
        }] if pages else []

        engine = "gemini" if any(s.startswith("gemini") for s in built.get("services_used") or []) else "mock"
        self.log(f"Funil arquitetado: {len(pages)} páginas, {len(writing_jobs)} briefings.",
                 step="funnel", duration_ms=self._elapsed_ms(start))
        return {
            "funnel_hypotheses": hyps,
            "pages": pages,
            "writing_jobs": writing_jobs,
            "funnel_strategy": strategy,
            "services_used": built.get("services_used") or [],
            "engine": engine,
            "warnings": built.get("warnings") or [],
        }
