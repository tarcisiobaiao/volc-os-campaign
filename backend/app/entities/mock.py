"""
Deterministic ENTITY-FIRST mock — country-aware. Produces schema-valid entity
discovery output (entities + opportunity + pains + seed_queries + funnel
hypotheses + cultural intelligence + personas) so the whole entity flow works
end-to-end before a real LLM key exists. Clearly marked engine='mock'.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# country_code -> list of (canonical, full_name, official_source, related_systems, type, category)
_CATALOG: Dict[str, List[tuple]] = {
    "CO": [
        ("RUT", "Registro Único Tributario", "DIAN", ["MUISCA"], "tax_registry", "identificacao_fiscal"),
        ("SISBÉN", "Sistema de Identificación de Potenciales Beneficiarios", "DNP", ["SISBEN IV"], "benefit_program", "saude"),
        ("ADRES", "Administradora de los Recursos del Sistema de Salud", "ADRES", [], "agency", "saude"),
        ("RUNT", "Registro Único Nacional de Tránsito", "RUNT", [], "system", "transito"),
        ("DIAN", "Dirección de Impuestos y Aduanas Nacionales", "DIAN", ["MUISCA"], "agency", "tributario"),
    ],
    "MX": [
        ("CURP", "Clave Única de Registro de Población", "RENAPO", [], "document", "identificacao"),
        ("RFC", "Registro Federal de Contribuyentes", "SAT", [], "tax_registry", "identificacao_fiscal"),
        ("SAT", "Servicio de Administración Tributaria", "SAT", [], "agency", "tributario"),
        ("IMSS", "Instituto Mexicano del Seguro Social", "IMSS", [], "agency", "saude"),
    ],
    "AR": [
        ("ANSES", "Administración Nacional de la Seguridad Social", "ANSES", ["Mi ANSES"], "agency", "previdencia"),
        ("AFIP", "Administración Federal de Ingresos Públicos", "AFIP", [], "agency", "tributario"),
        ("CUIL", "Código Único de Identificación Laboral", "ANSES", [], "document", "trabalho"),
    ],
    "BR": [
        ("Bolsa Família", "Programa Bolsa Família", "MDS", ["CadÚnico"], "benefit_program", "assistencia_social"),
        ("FGTS", "Fundo de Garantia do Tempo de Serviço", "Caixa", ["FGTS app"], "benefit_program", "trabalho"),
        ("INSS", "Instituto Nacional do Seguro Social", "INSS", ["Meu INSS"], "agency", "previdencia"),
        ("CPF", "Cadastro de Pessoas Físicas", "Receita Federal", ["gov.br"], "document", "identificacao_fiscal"),
        ("Pé-de-Meia", "Programa Pé-de-Meia", "MEC", ["Caixa Tem"], "benefit_program", "educacao"),
    ],
    "GB": [
        ("Universal Credit", "Universal Credit", "DWP", [], "benefit_program", "assistencia_social"),
        ("HMRC", "His Majesty's Revenue and Customs", "HMRC", [], "agency", "tributario"),
        ("NHS", "National Health Service", "NHS", [], "agency", "saude"),
        ("DVLA", "Driver and Vehicle Licensing Agency", "DVLA", [], "agency", "transito"),
    ],
    "PT": [
        ("NIF", "Número de Identificação Fiscal", "Finanças", ["Portal das Finanças"], "tax_registry", "identificacao_fiscal"),
        ("Segurança Social", "Segurança Social Direta", "Segurança Social", [], "agency", "previdencia"),
        ("SNS", "Serviço Nacional de Saúde", "SNS", ["SNS 24"], "agency", "saude"),
    ],
    "GT": [
        ("NIT", "Número de Identificación Tributaria", "SAT", [], "tax_registry", "identificacao_fiscal"),
        ("IGSS", "Instituto Guatemalteco de Seguridad Social", "IGSS", [], "agency", "saude"),
        ("RENAP", "Registro Nacional de las Personas", "RENAP", ["DPI"], "agency", "identificacao"),
    ],
    "US": [
        ("IRS", "Internal Revenue Service", "IRS", [], "agency", "tributario"),
        ("Social Security", "Social Security Administration", "SSA", [], "agency", "previdencia"),
        ("DMV", "Department of Motor Vehicles", "DMV", [], "agency", "transito"),
    ],
}

_GENERIC = [
    ("Imposto de Renda", "Declaração de Imposto de Renda", "Receita", [], "tax_registry", "tributario"),
    ("Previdência", "Sistema de Previdência Social", "Previdência", [], "agency", "previdencia"),
    ("Documento de Identidade", "Documento Nacional de Identidade", "Registro Civil", [], "document", "identificacao"),
    ("Saúde Pública", "Sistema de Saúde Público", "Ministério da Saúde", [], "agency", "saude"),
]

_TIERS = [("S", "S1 · Ponte de utilidade"), ("A", "A1 · Problema-solução"), ("B", "B2 · Documentos"), ("EXPERIMENTAL", "EXP · Experimental")]
_TIER_LEVELS = {
    "S": ("Alto", "Muito alto", "Baixa", "Muito alto"),
    "A": ("Alto", "Alto", "Média", "Alto"),
    "B": ("Médio", "Médio", "Baixa", "Alto"),
    "EXPERIMENTAL": ("Baixo", "Alto", "Baixa", "Médio"),
}
_TIMINGS = ["Perene", "Sazonal", "Evento", "Perene"]


def _slugify(name: str) -> str:
    # mesma chave de identidade da descoberta real (ver entity_name_key): assim o
    # fallback mock não gera dois nomes distintos colapsados no mesmo slug.
    from app.entities.normalize import entity_name_key

    return entity_name_key(name)


def _pains(canonical: str, source: Optional[str]) -> List[Dict[str, Any]]:
    return [
        {"pain_name": f"Atualizar {canonical}", "pain_description": f"Usuário precisa atualizar dados no {canonical}.", "user_goal": "manter cadastro em dia", "intent": "informational", "severity": "high"},
        {"pain_name": f"Consultar {canonical}", "pain_description": f"Usuário quer consultar a situação do {canonical}.", "user_goal": "verificar status", "intent": "task_completion", "severity": "high"},
        {"pain_name": f"Recuperar acesso ({source or canonical})", "pain_description": f"Usuário perdeu acesso ao portal {source or canonical}.", "user_goal": "recuperar login", "intent": "task_completion", "severity": "medium"},
    ]


def _seed_queries(canonical: str, source: Optional[str]) -> List[Dict[str, Any]]:
    base = canonical.lower()
    src = (source or "").lower()
    return [
        {"query": f"como consultar {base}", "query_type": "seed", "intent": "informational"},
        {"query": f"actualizar {base} {src}".strip(), "query_type": "variation", "intent": "task_completion"},
        {"query": f"descargar {base} {src}".strip(), "query_type": "long_tail", "intent": "task_completion"},
        {"query": f"{base} {src}".strip(), "query_type": "official", "intent": "navigational"},
    ]


def _funnels(canonical: str, source: Optional[str]) -> List[Dict[str, Any]]:
    return [
        {
            "title": f"Guia principal sobre o {canonical}",
            "summary": f"Funil utilitário sobre consulta, atualização, download e correção de dados do {canonical}.",
            "pages": [
                f"Guia principal do {canonical}",
                f"Como consultar o {canonical}",
                f"Como atualizar o {canonical}",
                f"Como baixar o {canonical} atualizado",
                f"Erros comuns no portal {source or canonical}",
            ],
        }
    ]


# v7_15 · SEGUNDO EIXO (a pessoa LÊ?). O mock varia os três níveis DE PROPÓSITO e
# inclui um `dado_unico` e um `nao_preciso_de_nada`: são os dois portões, e sem eles
# no ciclo o caminho do bloqueio nunca roda offline. A frase acompanha o rótulo — é
# ela que o teste literal manda escrever ANTES de rotular.
_LEITURA = [
    ("É uma lista de registros com data e valor, e ela se lê num relance.",
     "so_falta_um_dado", "dado_unico", "clara"),
    ("Depende de há quanto tempo você contribui, do seu vínculo atual e da faixa de renda.",
     "nao_sei_se_sirvo", "sustenta", "fragmentada"),
    ("Quase ninguém sabe que esse direito existe — e ele vale para mais gente do que se imagina.",
     "nao_sei_se_existe", "sustenta", "ilegivel"),
    ("O pedido costuma ser negado por três motivos, e cada um tem um caminho de correção diferente.",
     "nao_sei_por_que_falhou", "sustenta", "regra_mudou"),
    ("São sete passos, do cadastro no portal até a emissão do comprovante.",
     "sei_o_que_fazer", "sustenta", "ilegivel"),
    ("É curiosidade — não muda nada na vida de quem pergunta.",
     "nao_preciso_de_nada", "sustenta", "clara"),
]


def mock_entity_discovery(
    country: str, country_code: Optional[str], native_language: Optional[str], count: int,
    niches: Optional[List[Dict[str, Any]]] = None, seasonality: Optional[str] = None,
    forced_language: Optional[str] = None,
) -> Dict[str, Any]:
    """Mock country-aware. Honra (sem depender de) `niches`/`seasonality`/`forced_language`
    (R1/R2/R3): tagueia `entity.niche_slug` quando o `vertical` sorteado bate com algum
    dos nichos pedidos, e usa `forced_language` como fallback do idioma no meta — mas
    SEMPRE mantém vertical/temporal_window variados (o descarte por nicho/sazonalidade é
    responsabilidade do orchestrator, não do mock)."""
    code = (country_code or "").upper()
    catalog = _CATALOG.get(code) or _GENERIC
    lang = native_language or forced_language or ""

    # nicho selecionado -> primeiro slug cujo allowed_verticals contenha o vertical
    # sorteado (pra demonstrar o campo niche_slug preenchido pelo "LLM"; verticais sem
    # match ficam com niche_slug=None, o que aciona o fallback por `vertical` no
    # orchestrator).
    niche_by_vertical: Dict[str, str] = {}
    for n in (niches or []):
        slug = n.get("slug")
        if not slug:
            continue
        for v in (n.get("allowed_verticals") or []):
            niche_by_vertical.setdefault(v, slug)

    entities: List[Dict[str, Any]] = []
    for i in range(min(count, max(1, count))):
        canonical, full_name, source, systems, etype, category = catalog[i % len(catalog)]
        tier, stage = _TIERS[i % len(_TIERS)]
        vol, rpm, comp, conf = _TIER_LEVELS[tier]
        suffix = "" if i < len(catalog) else f" ({i + 1})"
        canonical_i = canonical + suffix
        vertical = ["gov_beneficios", "financas", "carros_transito", "seguros", "saude", "empregos_concursos"][i % 6]
        entities.append(
            {
                "entity": {
                    "canonical_name": canonical_i,
                    "full_name": full_name,
                    "slug": _slugify(canonical_i),
                    "type": etype,
                    "category": category,
                    "vertical": vertical,
                    "niche_slug": niche_by_vertical.get(vertical),
                    "official_source": source,
                    "related_systems": list(systems),
                    "aliases": [full_name, f"{canonical} {country}"],
                    "description": f"[mock] {full_name} — entidade de {category} relevante em {country}.",
                },
                "opportunity": {
                    "gold_tier": tier,
                    "strategic_stage": stage,
                    "estimated_volume": {"S": 60000, "A": 22000, "B": 6000, "EXPERIMENTAL": 1500}.get(tier, 5000) - (i % 5) * 300,
                    "ecpm_band": {"S": "premium", "A": "medio", "B": "baixo", "EXPERIMENTAL": "baixo"}.get(tier, "medio"),
                    "cpc_min": 0.2 + (i % 5) * 0.1,
                    "cpc_max": 1.5 + (i % 5) * 0.3,
                    "cpc_currency": "USD",
                    "volume_level": vol,
                    "rpm_level": rpm,
                    "competition_level": comp,
                    "confidence_level": conf,
                    "temporal_window": _TIMINGS[i % len(_TIMINGS)],
                    # v7_16: TRÊS frases, e a MODA é o rótulo. Duas concordam e a
                    # terceira diverge de propósito — é o caso que exercita a moda
                    # sem cair no desempate.
                    "respostas": [
                        {"frase": f"[mock] {_LEITURA[i % len(_LEITURA)][0]}",
                         "engajamento_level": _LEITURA[i % len(_LEITURA)][2],
                         "ignorancia_level": _LEITURA[i % len(_LEITURA)][1]},
                        {"frase": f"[mock] Outra pergunta plausível sobre o {canonical}.",
                         "engajamento_level": _LEITURA[i % len(_LEITURA)][2],
                         "ignorancia_level": _LEITURA[(i + 2) % len(_LEITURA)][1]},
                        {"frase": f"[mock] Uma terceira pergunta sobre o {canonical}.",
                         "engajamento_level": _LEITURA[(i + 1) % len(_LEITURA)][2],
                         "ignorancia_level": _LEITURA[(i + 1) % len(_LEITURA)][1]},
                    ],
                    "ignorancia_level": _LEITURA[i % len(_LEITURA)][1],
                    "opacidade_level": _LEITURA[i % len(_LEITURA)][3],
                    "concrete_pain": f"[mock] Dores recorrentes de uso/atualização do {canonical} em {country}.",
                    "gold_reason": f"[mock] {canonical} é entidade obrigatória/recorrente, com múltiplas dores pesquisáveis e potencial evergreen.",
                },
                "pains": _pains(canonical, source),
                "seed_queries": _seed_queries(canonical, source),
                "funnel_hypotheses": _funnels(canonical, source),
            }
        )

    return {
        "meta": {
            "country": country,
            "country_code": code or None,
            "native_language": lang,
            "market_tier": "medium_value",
            "seasonality": seasonality,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "cultural_intelligence": {
            "key_institutions": list({e["entity"]["official_source"] for e in entities if e["entity"]["official_source"]}),
            "main_benefits_programs": [e["entity"]["canonical_name"] for e in entities[:5]],
            "unique_cultural_pains": [f"[mock] Dor cultural específica de {country} #{i+1}" for i in range(3)],
            "upcoming_events": [f"[mock] Mudança regulatória em {country} #{i+1}" for i in range(2)],
            "digital_friction_apps": [s for e in entities for s in e["entity"]["related_systems"]][:5],
        },
        "personas": [
            {"name": f"Persona {i+1}", "demographics": f"[mock] {25+i*5} anos", "core_pain": f"[mock] dor com {entities[i % len(entities)]['entity']['canonical_name']}", "digital_literacy": ["low", "medium", "high"][i % 3], "typing_style": "[mock] busca descritiva", "main_systems": [entities[i % len(entities)]['entity']['canonical_name']]}
            for i in range(min(8, len(entities)))
        ],
        "insights": {
            "market_observation": f"[mock] {country} concentra dor em entidades de utilidade pública.",
            "untapped_angle": "[mock] Funis utilitários por entidade (consulta/atualização/download).",
            "recommended_deep_dive": "[mock] Aprofundar entidades de identificação fiscal e benefícios.",
            "cultural_warning": f"[mock] Respeite os nomes oficiais dos órgãos de {country}.",
        },
        "entities": entities,
    }


def mock_entity_enrich(country: str, country_code: Optional[str], canonical_name: str) -> Dict[str, Any]:
    """Enriquece 1 entidade inputada manualmente (mesmo shape de 1 item da descoberta)."""
    canonical = (canonical_name or "Entidade").strip()
    vol, rpm, comp, conf = _TIER_LEVELS.get("A", ("Médio", "Médio", "Média", "Alto"))
    item = {
        "entity": {
            "canonical_name": canonical,
            "full_name": canonical,
            "slug": _slugify(canonical),
            "type": "system",
            "category": "utilidade",
            "vertical": "outros",
            "official_source": None,
            "related_systems": [],
            "aliases": [f"{canonical} {country}"],
            "description": f"[mock] {canonical} — entidade de utilidade em {country} (inputada manualmente).",
        },
        "opportunity": {
            "gold_tier": "A",
            "strategic_stage": "A1 · Enriquecida",
            "estimated_volume": 12000,
            "ecpm_band": "medio",
            "cpc_min": 0.3, "cpc_max": 2.0, "cpc_currency": "USD",
            "volume_level": vol, "rpm_level": rpm, "competition_level": comp,
            "confidence_level": conf, "temporal_window": _TIMINGS[0],
            "respostas": [
                {"frase": f"[mock] {_LEITURA[1][0]}", "engajamento_level": _LEITURA[1][2], "ignorancia_level": _LEITURA[1][1]},
                {"frase": f"[mock] Outra pergunta sobre o {canonical}.", "engajamento_level": _LEITURA[1][2], "ignorancia_level": _LEITURA[3][1]},
                {"frase": f"[mock] Uma terceira sobre o {canonical}.", "engajamento_level": _LEITURA[2][2], "ignorancia_level": _LEITURA[2][1]},
            ],
            "ignorancia_level": _LEITURA[1][1],
            "opacidade_level": _LEITURA[1][3],
            "concrete_pain": f"[mock] Dores recorrentes de uso/consulta do {canonical} em {country}.",
            "gold_reason": f"[mock] {canonical} inputada manualmente; enriquecida com termos padrão.",
        },
        "pains": _pains(canonical, None),
        "seed_queries": _seed_queries(canonical, None),
        "funnel_hypotheses": [],
    }
    return {"entities": [item]}


def mock_entity_mine(entity: Dict[str, Any]) -> Dict[str, Any]:
    canonical = entity.get("canonical_name") or "entidade"
    source = entity.get("official_source")
    extra_pains = _pains(canonical, source) + [
        {"pain_name": f"Corrigir dados no {canonical}", "pain_description": f"Usuário precisa corrigir informações no {canonical}.", "user_goal": "corrigir cadastro", "intent": "task_completion", "severity": "high"},
        {"pain_name": f"Prazos do {canonical}", "pain_description": f"Usuário busca prazos/calendário do {canonical}.", "user_goal": "saber prazos", "intent": "informational", "severity": "medium"},
    ]
    base = canonical.lower()
    extra_sq = _seed_queries(canonical, source) + [
        {"query": f"{base} paso a paso", "query_type": "long_tail", "intent": "informational"},
        {"query": f"{base} requisitos", "query_type": "informational", "intent": "informational"},
        {"query": f"{base} en linea", "query_type": "transactional", "intent": "transactional"},
    ]
    return {"pains": extra_pains, "seed_queries": extra_sq}


def mock_entity_funnel(entity: Dict[str, Any]) -> Dict[str, Any]:
    return {"funnel_hypotheses": _funnels(entity.get("canonical_name") or "entidade", entity.get("official_source"))}
