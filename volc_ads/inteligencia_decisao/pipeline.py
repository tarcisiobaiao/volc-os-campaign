"""Pipeline determinístico: observação até proposta bloqueada.

Todas as funções recebem fotografia e relógio explícitos. Não há I/O, relógio
oculto, rede, chave, SDK de anúncios ou caminho de mutação.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from volc_ads.inteligencia_search import conflitos_de_negativa

from .contratos import EventoDeDecisao, PropostaTipada
from .critica import PortaCritica, executar_critica
from .politicas import avaliar_regras, parametros_do_perfil


VERSAO_CONTRATO = 1
VERSAO_OBSERVACAO = 1
API_NAMESPACE = "v25"
RELEASE_BASELINE = "v25.1"
ESTADOS_FONTE = {"completa", "parcial"}
METRICAS = (
    "impressions",
    "clicks",
    "cost_micros",
    "conversions",
    "conversion_value_micros",
)
METRICAS_JANELA = (
    "search_impression_share",
    "search_budget_lost_impression_share",
    "search_rank_lost_impression_share",
)
EIXOS = ("conta", "campanha", "orcamento", "grupo", "anuncio", "keyword", "segmentacao", "conversao", "leilao")


def _dt(valor: object) -> datetime | None:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _dia(valor: object) -> date | None:
    try:
        return date.fromisoformat(str(valor))
    except ValueError:
        return None


def _hash(*partes: object) -> str:
    bruto = "|".join(str(p) for p in partes).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()


def _hash_canonico(valor: object) -> str:
    def canonico(item: object) -> object:
        if isinstance(item, Mapping):
            return {str(k): canonico(v) for k, v in sorted(item.items(), key=lambda par: str(par[0]))}
        if isinstance(item, (list, tuple)):
            valores = [canonico(v) for v in item]
            return sorted(valores, key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False, default=str))
        return item
    bruto = json.dumps(canonico(valor), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _somar_anulavel(linhas: Sequence[Mapping[str, Any]], campo: str) -> int | float | None:
    valores = [linha.get(campo) for linha in linhas]
    if not valores or any(
        valor is None or isinstance(valor, bool) or not isinstance(valor, (int, float))
        for valor in valores
    ):
        return None
    return sum(valores)


def _ratio_ou_nulo(valor: object) -> int | float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not 0 <= valor <= 1:
        return None
    return valor


def _media_anulavel(linhas: Sequence[Mapping[str, Any]], campo: str) -> float | None:
    valores = [linha.get(campo) for linha in linhas]
    if not valores or any(valor is None for valor in valores):
        return None
    return round(sum(valores) / len(valores), 6)


def _validar(observacao: Mapping[str, Any], agora: datetime) -> dict[str, Any]:
    erros: list[str] = []
    faltantes: list[str] = []
    if observacao.get("observation_version") != VERSAO_OBSERVACAO:
        erros.append("versão de observação desconhecida")
    if observacao.get("api_namespace") != API_NAMESPACE:
        erros.append("namespace Google Ads precisa ser v25")
    if observacao.get("release_baseline") != RELEASE_BASELINE:
        erros.append("baseline documental precisa ser v25.1")
    for campo in ("scenario_id", "source", "lido_em", "janela", "campaign", "daily_metrics", "window_metrics", "normalization_manifest"):
        if campo not in observacao:
            faltantes.append(campo)

    lido = _dt(observacao.get("lido_em"))
    if lido is None:
        faltantes.append("lido_em válido")
    elif lido > agora:
        erros.append("lido_em está no futuro em relação ao replay as-of")

    janela = observacao.get("janela") if isinstance(observacao.get("janela"), Mapping) else {}
    inicio, fim = _dia(janela.get("inicio")), _dia(janela.get("fim"))
    estado_fonte_preliminar = (
        observacao.get("source", {}).get("estado") if isinstance(observacao.get("source"), Mapping) else None
    )
    if inicio is None or fim is None:
        faltantes.append("janela completa")
    elif inicio > fim:
        erros.append("janela invertida")
    elif fim > agora.date():
        erros.append("janela contém futuro em relação ao replay as-of")
    elif lido and estado_fonte_preliminar:
        if estado_fonte_preliminar == "completa" and lido.date() <= fim:
            erros.append("fonte completa foi lida antes do fechamento da janela")

    campanha = observacao.get("campaign") if isinstance(observacao.get("campaign"), Mapping) else {}
    inicio_campanha = _dt(campanha.get("start_date_time"))
    if inicio_campanha is None:
        faltantes.append("campaign.start_date_time")
    elif inicio_campanha > agora:
        erros.append("campaign.start_date_time está no futuro")

    parametros = parametros_do_perfil(observacao.get("policy_profile_id"))
    if parametros is None:
        faltantes.append("policy_profile_id versionado")

    manifesto = observacao.get("normalization_manifest") if isinstance(observacao.get("normalization_manifest"), Mapping) else {}
    conversao_valor = manifesto.get("conversion_value") if isinstance(manifesto.get("conversion_value"), Mapping) else {}
    if conversao_valor.get("source_field") != "metrics.conversions_value" or conversao_valor.get("target_field") != "conversion_value_micros":
        faltantes.append("normalization_manifest.conversion_value lineage")

    janela_metricas = observacao.get("window_metrics") if isinstance(observacao.get("window_metrics"), Mapping) else {}
    if janela_metricas.get("source_grain") != "campaign_window_without_segments_date":
        faltantes.append("window_metrics.source_grain")
    for campo in METRICAS_JANELA:
        if campo not in janela_metricas:
            faltantes.append(f"window_metrics.{campo}")
            continue
        valor = janela_metricas.get(campo)
        if valor is not None and (
            isinstance(valor, bool) or not isinstance(valor, (int, float)) or not 0 <= valor <= 1
        ):
            erros.append(f"window_metrics.{campo} precisa ser razão numérica entre 0 e 1 ou null")

    linhas = observacao.get("daily_metrics")
    if not isinstance(linhas, list):
        faltantes.append("daily_metrics em lista")
        linhas = []
    datas: set[date] = set()
    for indice, linha in enumerate(linhas):
        if not isinstance(linha, Mapping):
            erros.append(f"daily_metrics[{indice}] não é objeto")
            continue
        dia = _dia(linha.get("date"))
        if dia is None:
            faltantes.append(f"daily_metrics[{indice}].date")
        elif dia > agora.date():
            erros.append(f"daily_metrics[{indice}] vaza futuro")
        elif inicio and fim and not inicio <= dia <= fim:
            erros.append(f"daily_metrics[{indice}] está fora da janela")
        elif dia in datas:
            erros.append(f"daily_metrics[{indice}] duplica a data")
        else:
            datas.add(dia)
        for metrica in METRICAS:
            if metrica not in linha:
                faltantes.append(f"daily_metrics[{indice}].{metrica}")
            else:
                valor = linha.get(metrica)
                if valor is not None and (
                    isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor < 0
                ):
                    erros.append(f"daily_metrics[{indice}].{metrica} precisa ser número não negativo ou null")

    for colecao in ("daily_metrics", "quality", "search_terms", "negatives", "external_revenue"):
        for indice, linha in enumerate(observacao.get(colecao, []) or []):
            if not isinstance(linha, Mapping):
                continue
            for campo in ("customer_id", "campaign_id"):
                declarado = linha.get(campo)
                esperado = campanha.get(campo)
                if declarado is not None and str(declarado) != str(esperado):
                    erros.append(f"{colecao}[{indice}].{campo} mistura entidade")
    componentes_qualidade = {"ABOVE_AVERAGE", "AVERAGE", "BELOW_AVERAGE"}
    for indice, linha in enumerate(observacao.get("quality", []) or []):
        if not isinstance(linha, Mapping):
            continue
        for campo in ("customer_id", "campaign_id", "ad_group_id", "criterion_id", "resource_name"):
            if not linha.get(campo):
                faltantes.append(f"quality[{indice}].{campo}")
        score = linha.get("quality_score")
        if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 10:
            faltantes.append(f"quality[{indice}].quality_score válido (1..10)")
        for campo in ("ad_relevance", "landing_page_experience", "expected_ctr"):
            if linha.get(campo) not in componentes_qualidade:
                faltantes.append(f"quality[{indice}].{campo} conhecido")
    for indice, linha in enumerate(observacao.get("negatives", []) or []):
        if not isinstance(linha, Mapping):
            continue
        for campo in ("customer_id", "campaign_id", "criterion_id", "resource_name", "keyword_text", "level", "match_type"):
            if not linha.get(campo):
                faltantes.append(f"negatives[{indice}].{campo}")
        nivel = str(linha.get("level") or "").upper()
        match_type = str(linha.get("match_type") or "").upper()
        if nivel not in {"CAMPAIGN", "AD_GROUP"}:
            faltantes.append(f"negatives[{indice}].level conhecido")
        if match_type not in {"EXACT", "PHRASE", "BROAD"}:
            faltantes.append(f"negatives[{indice}].match_type conhecido")
        if nivel == "AD_GROUP" and not linha.get("ad_group_id"):
            faltantes.append(f"negatives[{indice}].ad_group_id")
    for indice, linha in enumerate(observacao.get("search_terms", []) or []):
        if not isinstance(linha, Mapping) or linha.get("valor_negocio") != "valioso":
            continue
        for campo in ("customer_id", "campaign_id", "ad_group_id", "search_term", "motivo_valor", "evidencia_ref"):
            if not linha.get(campo):
                faltantes.append(f"search_terms[{indice}].{campo}")
    for indice, linha in enumerate(observacao.get("external_revenue", []) or []):
        if not isinstance(linha, Mapping):
            continue
        dia = _dia(linha.get("date"))
        if dia is None:
            faltantes.append(f"external_revenue[{indice}].date")
        elif dia > agora.date() or (inicio and fim and not inicio <= dia <= fim):
            erros.append(f"external_revenue[{indice}] está fora da janela/as-of")

    rotina = observacao.get("routine") if isinstance(observacao.get("routine"), Mapping) else {}
    heartbeat = _dt(rotina.get("last_success_at"))
    if rotina.get("last_success_at") and heartbeat is None:
        faltantes.append("routine.last_success_at válido")
    elif heartbeat and (heartbeat > agora or (lido and heartbeat > lido)):
        erros.append("routine.last_success_at vaza futuro da fotografia")

    estado_fonte = observacao.get("source", {}).get("estado") if isinstance(observacao.get("source"), Mapping) else None
    if estado_fonte not in ESTADOS_FONTE:
        erros.append("source.estado desconhecido")
    parcial = estado_fonte == "parcial" or bool(faltantes)
    idade_s = int((agora - lido).total_seconds()) if lido and lido <= agora else None
    stale = idade_s is not None and idade_s > 36 * 3600
    return {
        "estado": "invalida" if erros else "parcial" if parcial else "stale" if stale else "atual",
        "erros": erros,
        "faltantes": sorted(set(faltantes)),
        "lido_em": lido.isoformat().replace("+00:00", "Z") if lido else None,
        "idade_s": idade_s,
        "janela": {"inicio": str(janela.get("inicio") or ""), "fim": str(janela.get("fim") or "")},
    }


def _features(observacao: Mapping[str, Any], agora: datetime) -> dict[str, Any]:
    linhas = sorted(
        [linha for linha in observacao.get("daily_metrics", []) if isinstance(linha, Mapping)],
        key=lambda linha: str(linha.get("date") or ""),
    )
    janela_metricas = observacao.get("window_metrics") if isinstance(observacao.get("window_metrics"), Mapping) else {}
    feature = {
        "impressoes": _somar_anulavel(linhas, "impressions"),
        "cliques": _somar_anulavel(linhas, "clicks"),
        "custo_micros": _somar_anulavel(linhas, "cost_micros"),
        "conversoes": _somar_anulavel(linhas, "conversions"),
        "valor_conversao_micros": _somar_anulavel(linhas, "conversion_value_micros"),
        # Ratios de share são consultados no grão campanha+janela, sem
        # segments.date. Média de percentuais diários não reconstrói a janela.
        "impression_share": _ratio_ou_nulo(janela_metricas.get("search_impression_share")),
        "lost_budget": _ratio_ou_nulo(janela_metricas.get("search_budget_lost_impression_share")),
        "lost_rank": _ratio_ou_nulo(janela_metricas.get("search_rank_lost_impression_share")),
    }
    receita = [linha for linha in observacao.get("external_revenue", []) if isinstance(linha, Mapping)]
    receita_total = _somar_anulavel(receita, "revenue_micros")
    cliques = feature["cliques"]
    rpc = None if receita_total is None or cliques in (None, 0) else round(receita_total / cliques)
    custo = feature["custo_micros"]
    feature["receita_micros"] = receita_total
    feature["rpc_externo_micros"] = rpc
    feature["margem_micros"] = None if receita_total is None or custo is None else receita_total - custo

    qualidade = [q for q in observacao.get("quality", []) if isinstance(q, Mapping)]
    parametros = parametros_do_perfil(observacao.get("policy_profile_id")) or {}
    minimo = parametros.get("quality_healthy_min")
    componentes = [
        q.get(campo)
        for q in qualidade
        for campo in ("ad_relevance", "landing_page_experience", "expected_ctr")
    ]
    identidade_completa = bool(qualidade) and all(
        q.get("customer_id") and q.get("campaign_id") and q.get("criterion_id") and q.get("ad_group_id") and q.get("resource_name")
        for q in qualidade
    )
    scores = [q.get("quality_score") for q in qualidade]
    scores_validos = bool(scores) and all(
        isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 10 for v in scores
    )
    componentes_validos = bool(componentes) and all(
        v in {"ABOVE_AVERAGE", "AVERAGE", "BELOW_AVERAGE"} for v in componentes
    )
    feature["quality_observations"] = qualidade
    feature["quality_feature_volc"] = None if not scores_validos or not componentes_validos or not identidade_completa else {
        "criterios": len(scores),
        "minimo_observado": min(scores),
        "maximo_observado": max(scores),
        "nome": "feature VOLC de qualidade por keyword",
    }
    feature["qualidade_saudavel"] = None if not qualidade or not scores_validos or not componentes_validos or not identidade_completa or minimo is None else (
        all(v >= minimo for v in scores) and "BELOW_AVERAGE" not in componentes
    )

    campanha = observacao.get("campaign") if isinstance(observacao.get("campaign"), Mapping) else {}
    inicio = _dt(campanha.get("start_date_time"))
    feature["idade_campanha_horas"] = None if inicio is None else round(
        (agora - inicio).total_seconds() / 3600, 2
    )

    custos = [linha.get("cost_micros") for linha in linhas]
    feature["cost_spike_ratio"] = None
    if len(custos) >= 3 and all(c is not None for c in custos):
        base = statistics.median(custos[:-1])
        feature["cost_spike_ratio"] = None if base <= 0 else round(custos[-1] / base, 3)

    rotina = observacao.get("routine") if isinstance(observacao.get("routine"), Mapping) else {}
    heartbeat = _dt(rotina.get("last_success_at"))
    feature["routine_age_hours"] = None if heartbeat is None or heartbeat > agora else round((agora - heartbeat).total_seconds() / 3600, 2)
    def com_escopo(linha: Mapping[str, Any]) -> dict[str, Any]:
        return {"customer_id": campanha.get("customer_id"), "campaign_id": campanha.get("campaign_id"), **linha}
    feature["negative_conflicts"] = conflitos_de_negativa(
        [com_escopo(t) for t in observacao.get("search_terms", []) if isinstance(t, Mapping)],
        [com_escopo(n) for n in observacao.get("negatives", []) if isinstance(n, Mapping)],
    )
    return feature


def _evento(
    observacao: Mapping[str, Any],
    tipo: str,
    severidade: str,
    refs: Iterable[str],
) -> EventoDeDecisao:
    scenario = str(observacao.get("scenario_id"))
    janela = observacao.get("janela") or {}
    entidade = f"synthetic:{observacao.get('campaign', {}).get('customer_id')}:{observacao.get('campaign', {}).get('campaign_id')}"
    dedup = _hash(tipo, entidade, janela.get("inicio"), janela.get("fim"))
    return EventoDeDecisao(
        evento_id=f"evt-{dedup[:16]}",
        tipo=tipo,
        entidade=entidade,
        observado_em=str(observacao.get("lido_em")),
        janela_inicio=str(janela.get("inicio")),
        janela_fim=str(janela.get("fim")),
        evidencia_refs=tuple(refs),
        severidade=severidade,
        dedup_key=dedup,
    )


def _detectar_eventos(
    observacao: Mapping[str, Any],
    validacao: Mapping[str, Any],
    features: Mapping[str, Any],
) -> list[EventoDeDecisao]:
    if validacao.get("estado") in ("invalida", "parcial", "stale"):
        return []
    eventos: list[EventoDeDecisao] = []
    parametros = parametros_do_perfil(observacao.get("policy_profile_id"))
    if parametros is None:
        return []
    if features.get("idade_campanha_horas") is not None and 0 <= features["idade_campanha_horas"] <= parametros["onboarding_max_age_hours"] and features.get("impressoes") == 0:
        eventos.append(_evento(observacao, "campaign_onboarding_no_delivery", "atencao", ("daily_metrics.impressions", "campaign.start_date_time")))
    if (
        features.get("lost_budget") is not None
        and features["lost_budget"] > parametros["share_loss_min"]
        and features.get("qualidade_saudavel") is True
    ):
        eventos.append(_evento(observacao, "budget_limited_with_healthy_quality", "atencao", ("window_metrics.search_budget_lost_impression_share", "quality")))
    if (
        features.get("lost_rank") is not None
        and features["lost_rank"] > parametros["share_loss_min"]
        and features.get("qualidade_saudavel") is False
    ):
        eventos.append(_evento(observacao, "rank_limited_with_poor_quality", "atencao", ("window_metrics.search_rank_lost_impression_share", "quality")))
    if features.get("negative_conflicts"):
        eventos.append(_evento(observacao, "valuable_term_blocked_by_negative", "alta", ("search_terms", "negatives")))
    ratio = features.get("cost_spike_ratio")
    if ratio is not None and ratio >= parametros["cost_spike_ratio_min"]:
        eventos.append(_evento(observacao, "cost_spike", "alta", ("daily_metrics.cost_micros",)))
    idade_rotina = features.get("routine_age_hours")
    if idade_rotina is not None and idade_rotina > parametros["routine_max_age_hours"]:
        eventos.append(_evento(observacao, "routine_stale", "alta", ("routine.last_success_at",)))
    return eventos


def _evidencia(
    observacao: Mapping[str, Any],
    validacao: Mapping[str, Any],
    rotulo: str,
    campo: str,
    valor: object,
    *,
    origem: str = "conta",
) -> dict[str, Any]:
    return {
        "rotulo": rotulo,
        "valor": None if valor is None else str(valor),
        "campo": campo,
        "janela": f"{validacao.get('janela', {}).get('inicio')} a {validacao.get('janela', {}).get('fim')}",
        "leitura": None if validacao.get("lido_em") is None else {
            "lido_em": validacao.get("lido_em"),
            "idade_s": validacao.get("idade_s"),
        },
        "origem": origem,
    }


def _fatores(observacao: Mapping[str, Any], features: Mapping[str, Any]) -> dict[str, list[dict[str, str]]]:
    saida: dict[str, list[dict[str, str]]] = {"favorece": [], "limita": [], "desconhecido": []}
    def incluir(grupo: str, chave: str, frase: str, evidencia: str) -> None:
        saida[grupo].append({"chave": chave, "frase": frase, "evidencia": evidencia})
    qualidade = features.get("qualidade_saudavel")
    if qualidade is True:
        incluir("favorece", "qualidade", "Quality Score e componentes estão saudáveis nesta fotografia.", "quality")
    elif qualidade is False:
        incluir("limita", "qualidade", "Quality Score ou componente abaixo da média limita rank.", "quality")
    else:
        incluir("desconhecido", "qualidade", "Qualidade não foi medida por inteiro.", "quality")
    if features.get("lost_budget") is not None and features["lost_budget"] > 0:
        incluir("favorece", "demanda", "Há impression share perdido por orçamento.", "window_metrics.search_budget_lost_impression_share")
    if features.get("lost_rank") is not None and features["lost_rank"] > 0:
        incluir("limita", "rank", "Há impression share perdido por rank.", "window_metrics.search_rank_lost_impression_share")
    margem = features.get("margem_micros")
    if margem is None:
        incluir("desconhecido", "margem", "Receita ou custo ausente impede calcular margem.", "external_revenue")
    elif margem > 0:
        incluir("favorece", "margem", "A margem externa desta janela é positiva.", "external_revenue")
    else:
        incluir("limita", "margem", "A margem externa desta janela não sustenta escala.", "external_revenue")
    if features.get("negative_conflicts"):
        incluir("limita", "negativa", "Uma negativa existente bloqueia termo marcado como valioso.", "search_terms+negatives")
    cooldown = _dt(observacao.get("last_action", {}).get("cooldown_until"))
    agora = _dt(observacao.get("as_of"))
    if cooldown and agora and cooldown > agora:
        incluir("limita", "cooldown", "A regra ainda está em carência sobre este alvo.", "last_action.cooldown_until")
    return saida


def _conflitos(
    observacao: Mapping[str, Any],
    validacao: Mapping[str, Any],
    features: Mapping[str, Any],
    eventos: Sequence[EventoDeDecisao],
) -> list[dict[str, Any]]:
    conflitos: list[dict[str, Any]] = []
    def incluir(codigo: str, efeito: str, motivo: str, politicas: tuple[str, ...], refs: tuple[str, ...]) -> None:
        conflitos.append({
            "codigo": codigo,
            "efeito": efeito,
            "motivo": motivo,
            "politicas": list(politicas),
            "evidencia_refs": list(refs),
            "resolucao": "mantém proposta bloqueada até revisão humana",
        })
    tipos = {e.tipo for e in eventos}
    if validacao.get("estado") != "atual":
        incluir("health_gate", "veta_todas", "Frescor ou completude não permitem proposta.", ("ads_health_eventos",), ("source", "lido_em", "janela"))
    if "budget_limited_with_healthy_quality" in tipos and (features.get("margem_micros") is None or features.get("margem_micros") <= 0):
        incluir("margin_gate", "veta_escala", "Demanda existe, mas a margem não sustenta aumento de gasto.", ("orakul_escala_com_guardas",), ("external_revenue", "daily_metrics.cost_micros"))
    cooldown = _dt(observacao.get("last_action", {}).get("cooldown_until"))
    agora = _dt(observacao.get("as_of"))
    if "budget_limited_with_healthy_quality" in tipos and cooldown and agora and cooldown > agora:
        incluir("cooldown_gate", "veta_escala", f"A carência termina em {cooldown.isoformat().replace('+00:00', 'Z')}.", ("orakul_escala_com_guardas",), ("last_action.cooldown_until",))
    if tipos.intersection({"cost_spike", "routine_stale"}):
        incluir("ads_health_gate", "veta_mudanca_de_gasto", "Saúde de custo ou rotina precisa ser resolvida antes da decisão.", ("ads_health_eventos", "orakul_escala_com_guardas"), ("daily_metrics.cost_micros", "routine.last_success_at"))
    return conflitos


def _health_gate(validacao: Mapping[str, Any], eventos: Sequence[EventoDeDecisao]) -> dict[str, str]:
    estado = str(validacao.get("estado"))
    if estado == "invalida":
        return {"estado": "bloqueado", "rotulo": "fotografia inválida", "motivo": "A observação viola o contrato ou contém futuro."}
    if estado == "parcial":
        return {"estado": "parcial", "rotulo": "leitura parcial", "motivo": "Campos ausentes permanecem ausentes e bloqueiam proposta."}
    if estado == "stale":
        return {"estado": "stale", "rotulo": "leitura antiga", "motivo": "A fotografia ultrapassou o frescor aceito pelo perfil sintético."}
    if any(e.tipo in ("cost_spike", "routine_stale") for e in eventos):
        return {"estado": "bloqueado", "rotulo": "saúde pede atenção", "motivo": "Ocorrências de saúde vetam mudança de gasto."}
    return {"estado": "liberado", "rotulo": "evidência utilizável", "motivo": "A fotografia está atual e inteira para este replay."}


def _marcar_politicas(avaliacoes: list[dict[str, Any]], eventos: Sequence[EventoDeDecisao]) -> None:
    mapeamento = {
        "campaign_onboarding_no_delivery": "nexus_guardiao_72h",
        "budget_limited_with_healthy_quality": "orakul_escala_com_guardas",
        "rank_limited_with_poor_quality": "search_rank_quality_first",
        "valuable_term_blocked_by_negative": "search_negativa_bidirecional",
        "cost_spike": "ads_health_eventos",
        "routine_stale": "ads_health_eventos",
    }
    por_tipo = {mapeamento[e.tipo] for e in eventos if e.tipo in mapeamento}
    for avaliacao in avaliacoes:
        if avaliacao["regra_id"] in por_tipo and avaliacao["suficiencia"] == "suficiente":
            avaliacao["disparou"] = True
            avaliacao["resultado"] = "evento tipado emitido"
        elif avaliacao["suficiencia"] == "suficiente":
            avaliacao["resultado"] = "condição não observada"
        else:
            avaliacao["resultado"] = "evidência insuficiente"


def _propostas(
    observacao: Mapping[str, Any],
    validacao: Mapping[str, Any],
    features: Mapping[str, Any],
    eventos: Sequence[EventoDeDecisao],
    conflitos: Sequence[Mapping[str, Any]],
    politicas: Sequence[Mapping[str, Any]],
) -> tuple[list[PropostaTipada], list[dict[str, Any]]]:
    if validacao.get("estado") != "atual":
        return [], []
    vetos = {str(c.get("efeito")) for c in conflitos}
    avaliacao_por_regra = {str(p.get("regra_id")): p for p in politicas}
    tipadas: list[PropostaTipada] = []
    caixa: list[dict[str, Any]] = []
    for evento in eventos:
        configuracao: tuple[str, str, str, str, str | None, str | None, str] | None = None
        if evento.tipo == "budget_limited_with_healthy_quality" and not vetos.intersection({"veta_escala", "veta_todas", "veta_mudanca_de_gasto"}):
            configuracao = ("orakul_escala_com_guardas", "orcamento", "Revisar aumento de orçamento", "Há demanda perdida por verba e qualidade saudável; o tamanho do passo continua humano.", str(observacao.get("campaign", {}).get("budget_micros")), None, "alta")
        elif evento.tipo == "rank_limited_with_poor_quality":
            configuracao = ("search_rank_quality_first", "estrutura", "Revisar qualidade antes do lance", "Rank limita a entrega e a qualidade está ruim; aumentar preço não é o primeiro remédio.", "qualidade abaixo da média", "revisão de anúncio, keyword e landing page", "alta")
        elif evento.tipo == "valuable_term_blocked_by_negative":
            conflito = features["negative_conflicts"][0]
            configuracao = ("search_negativa_bidirecional", "estrutura", "Revisar negativa conflitante", "Um termo valioso observado está bloqueado por negativa existente.", str(conflito.get("negative_keyword")), None, "evidência completa para revisão; confiança estatística não calculada")
        if configuracao is None:
            continue
        regra, alvo, titulo, frase, antes, depois, confianca = configuracao
        avaliacao = avaliacao_por_regra.get(regra)
        if not avaliacao or not (
            avaliacao.get("aplicavel") is True
            and avaliacao.get("suficiencia") == "suficiente"
            and avaliacao.get("disparou") is True
        ):
            continue
        proposta_id = f"prop-{_hash(evento.evento_id, regra, alvo)[:16]}"
        bloqueio = "Laboratório sintético sem executor, aprovação ou trava de escrita aberta."
        valores_por_ref = {
            "window_metrics.search_budget_lost_impression_share": features.get("lost_budget"),
            "window_metrics.search_rank_lost_impression_share": features.get("lost_rank"),
            "quality": {
                "quality_feature_volc": features.get("quality_feature_volc"),
                "qualidade_saudavel": features.get("qualidade_saudavel"),
            },
            "search_terms": features.get("negative_conflicts"),
            "negatives": features.get("negative_conflicts"),
        }
        evidencias = tuple(
            _evidencia(
                observacao,
                validacao,
                ref.split(".")[-1].replace("_", " "),
                ref,
                valores_por_ref.get(ref),
            )
            for ref in evento.evidencia_refs
        )
        tipada = PropostaTipada(
            proposta_id=proposta_id,
            idempotency_key=_hash_canonico({
                "contrato": VERSAO_CONTRATO,
                "regra": regra,
                "regra_versao": avaliacao.get("versao"),
                "alvo": evento.entidade,
                "antes": antes,
                "depois": depois,
                "evidencias": evidencias,
                "fotografia": {
                    "lido_em": observacao.get("lido_em"),
                    "janela": observacao.get("janela"),
                    "features": features,
                },
            }),
            evento_id=evento.evento_id,
            regra_chave=regra,
            regra_versao=1,
            operacao=alvo,
            alvo=evento.entidade,
            antes=antes,
            depois=depois,
            evidencias=evidencias,
            confianca=confianca,
            bloqueios=(bloqueio,),
        )
        tipadas.append(tipada)
        caixa.append({
            "id": proposta_id,
            "alvo": alvo,
            "titulo": titulo,
            "frase": frase,
            "eixo": "orcamento" if alvo == "orcamento" else "keyword",
            "evidencias": list(evidencias),
            "confianca": confianca,
            "amostra": {
                "n": features.get("cliques"),
                "unidade": "cliques observados",
                "janela": f"{validacao['janela']['inicio']} a {validacao['janela']['fim']}",
                "insuficiente": avaliacao.get("suficiencia") != "suficiente",
                "motivo": avaliacao.get("motivo_suficiencia"),
                "faltantes": list(avaliacao.get("faltantes") or []),
            },
            "diff": {
                "linhas": [{"rotulo": alvo, "antes": antes, "depois": depois, "delta": None}],
                "inalterado": ["estado da campanha", "demais estruturas"],
                "gasto_diario": None,
            },
            "aprovacao": {"estado": "nao_submetida", "por": None, "em": None, "impressao": None, "motivo": None, "vale_ate": None},
            "bloqueio": {"dependencia": bloqueio, "destrava": "endpoint"},
        })
    return tipadas, caixa


def _degrau(eixo: str, estado: str, palavra: str, frase: str, evidencias: list[dict[str, Any]] | None = None, impedimento: str | None = None) -> dict[str, Any]:
    return {"eixo": eixo, "estado": estado, "palavra": palavra, "frase": frase, "motivo_da_conta": [], "evidencias": evidencias or [], "impedimento": impedimento, "propostas": []}


def _diagnostico(
    observacao: Mapping[str, Any],
    validacao: Mapping[str, Any],
    features: Mapping[str, Any],
) -> dict[str, Any]:
    campanha = observacao.get("campaign") or {}
    checks = campanha.get("checks") or {}
    perfil = parametros_do_perfil(observacao.get("policy_profile_id")) or {}
    leitura = None if validacao.get("lido_em") is None else {"lido_em": validacao["lido_em"], "idade_s": validacao.get("idade_s")}
    if validacao.get("estado") in ("invalida", "parcial", "stale"):
        motivo = "A fotografia não está atual e completa para fechar este degrau."
        degraus = [_degrau(eixo, "nao_apurado", "não apurado", motivo, impedimento=motivo) for eixo in EIXOS]
    else:
        status = campanha.get("status")
        conta_status = campanha.get("account_status")
        cobranca = checks.get("billing_active")
        conta_apurada = conta_status is not None and cobranca is not None
        conta_ok = conta_status == "ENABLED" and cobranca is True
        degraus = [
            _degrau(
                "conta",
                "ok" if conta_ok else "bloqueia" if conta_apurada else "nao_apurado",
                "conta ativa" if conta_ok else "conta bloqueada" if conta_apurada else "conta não apurada",
                "A conta e a cobrança foram observadas." if conta_apurada else "Status da conta ou cobrança não foi observado.",
                impedimento=None if conta_apurada else "campo ausente",
            ),
            _degrau(
                "campanha",
                "ok" if status == "ENABLED" else "bloqueia" if status is not None else "nao_apurado",
                "ligada" if status == "ENABLED" else "não ativa" if status is not None else "campanha não apurada",
                f"Estado observado: {status}." if status is not None else "Estado da campanha não foi observado.",
                impedimento=None if status is not None else "campo ausente",
            ),
        ]
        if (
            features.get("impressoes") == 0
            and features.get("idade_campanha_horas") is not None
            and perfil.get("onboarding_max_age_hours") is not None
            and 0 <= features["idade_campanha_horas"] <= perfil["onboarding_max_age_hours"]
        ):
            degraus.append(_degrau("orcamento", "nao_apurado", "causa indeterminada", "Sem impressões não prova que orçamento é a causa.", impedimento="Nenhuma causa primária foi observada."))
        elif features.get("lost_budget") is not None and features["lost_budget"] > 0:
            degraus.append(_degrau("orcamento", "limita", "perda por verba", "A conta mediu impression share perdido por orçamento.", [_evidencia(observacao, validacao, "perda por orçamento", "search_budget_lost_impression_share", features.get("lost_budget"))]))
        elif features.get("lost_budget") is not None:
            degraus.append(_degrau("orcamento", "ok", "sem limite medido", "Não há perda por orçamento nesta fotografia."))
        else:
            degraus.append(_degrau("orcamento", "nao_apurado", "perda por verba não apurada", "A perda por orçamento não foi medida para a janela.", impedimento="campo ausente"))
        for eixo, chave, rotulo in (("grupo", "groups_enabled", "grupos"), ("anuncio", "ads_approved", "anúncios")):
            valor = checks.get(chave)
            degraus.append(_degrau(
                eixo,
                "ok" if valor is True else "bloqueia" if valor is False else "nao_apurado",
                f"{rotulo} apurados" if valor is True else f"{rotulo} com bloqueio observado" if valor is False else f"{rotulo} não apurados",
                f"{rotulo.capitalize()} foram observados e estão aptos." if valor is True else f"{rotulo.capitalize()} foram observados como não aptos." if valor is False else f"Não há prova completa de {rotulo}.",
                impedimento="condição observada como falsa" if valor is False else "campo ausente" if valor is None else None,
            ))
        if features.get("negative_conflicts"):
            degraus.append(_degrau("keyword", "limita", "negativa conflitante", "Uma negativa existente limita termo valioso observado."))
        else:
            valor = checks.get("keywords_enabled")
            degraus.append(_degrau(
                "keyword",
                "ok" if valor is True else "bloqueia" if valor is False else "nao_apurado",
                "keywords apuradas" if valor is True else "keywords com bloqueio observado" if valor is False else "keywords não apuradas",
                "Keywords ativas foram observadas." if valor is True else "Keywords foram observadas como não aptas." if valor is False else "Não há prova completa das keywords.",
                impedimento="condição observada como falsa" if valor is False else "campo ausente" if valor is None else None,
            ))
        for eixo, chave, rotulo in (("segmentacao", "targeting_valid", "segmentação"), ("conversao", "conversion_tracking", "conversão")):
            valor = checks.get(chave)
            degraus.append(_degrau(
                eixo,
                "ok" if valor is True else "bloqueia" if valor is False else "nao_apurado",
                f"{rotulo} apurada" if valor is True else f"{rotulo} com bloqueio observado" if valor is False else f"{rotulo} não apurada",
                f"{rotulo.capitalize()} foi observada e está apta." if valor is True else f"{rotulo.capitalize()} foi observada como não apta." if valor is False else f"Não há prova completa de {rotulo}.",
                impedimento="condição observada como falsa" if valor is False else "campo ausente" if valor is None else None,
            ))
        if features.get("lost_rank") is not None and features["lost_rank"] > 0:
            degraus.append(_degrau("leilao", "limita", "perda por rank", "A conta mediu impression share perdido por rank.", [_evidencia(observacao, validacao, "perda por rank", "search_rank_lost_impression_share", features.get("lost_rank"))]))
        elif features.get("impressoes") == 0:
            degraus.append(_degrau("leilao", "nao_apurado", "sem leilão observado", "Nenhuma impressão confirma entrada em leilão.", impedimento="sem entrega observada"))
        else:
            degraus.append(_degrau("leilao", "ok", "leilão observado", "A campanha entrou em leilão nesta fotografia."))
    return {
        "versao": 1,
        "volc_campaign_id": f"lab::{observacao.get('scenario_id')}",
        "customer_id": str(campanha.get("customer_id") or "synthetic"),
        "nome_campanha": str(campanha.get("name") or "Campanha sintética"),
        "moeda": campanha.get("currency"),
        "janela": f"{validacao.get('janela', {}).get('inicio')} a {validacao.get('janela', {}).get('fim')}",
        "leitura": leitura,
        "degraus": degraus,
        "parcial": any(d["estado"] == "nao_apurado" for d in degraus),
    }


def _veredito(
    validacao: Mapping[str, Any],
    eventos: Sequence[EventoDeDecisao],
    conflitos: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    estado = validacao.get("estado")
    tipos = {e.tipo for e in eventos}
    codigos = {str(c.get("codigo")) for c in conflitos}
    if estado == "invalida":
        return {"tipo": "bloqueado", "titulo": "Fotografia inválida", "resumo": "O replay detectou contrato inválido ou vazamento de futuro."}
    if estado == "parcial":
        return {"tipo": "nao_apurado", "titulo": "Leitura parcial não autoriza decisão", "resumo": "Ausências permanecem nulas e nenhuma proposta é emitida."}
    if estado == "stale":
        return {"tipo": "nao_apurado", "titulo": "Leitura antiga não autoriza decisão", "resumo": "O diagnóstico preserva a fotografia, mas bloqueia recomendação."}
    if "ads_health_gate" in codigos:
        return {"tipo": "bloqueado", "titulo": "Saúde bloqueia a decisão", "resumo": "Spike de custo ou rotina parada precisa ser investigado primeiro."}
    if "budget_limited_with_healthy_quality" in tipos and codigos.intersection({"margin_gate", "cooldown_gate"}):
        return {"tipo": "bloqueado", "titulo": "Escala bloqueada por guardas", "resumo": "Demanda existe, mas margem ou cooldown vetam aumento."}
    if "valuable_term_blocked_by_negative" in tipos:
        return {"tipo": "limitado", "titulo": "Termo valioso bloqueado por negativa", "resumo": "O caminho inverso de governança pede revisão humana da negativa."}
    if "budget_limited_with_healthy_quality" in tipos:
        return {"tipo": "limitado", "titulo": "Demanda limitada por orçamento", "resumo": "Qualidade saudável favorece revisar verba, sem definir o tamanho do passo."}
    if "rank_limited_with_poor_quality" in tipos:
        return {"tipo": "limitado", "titulo": "Rank limitado por qualidade", "resumo": "Qualidade vem antes de qualquer proposta de lance."}
    if "campaign_onboarding_no_delivery" in tipos:
        return {"tipo": "indeterminado", "titulo": "Sem entrega, causa indeterminada", "resumo": "NEXUS protege as primeiras 72 horas e não inventa remédio."}
    return {"tipo": "observado", "titulo": "Nenhum impedimento dominante", "resumo": "A fotografia não disparou política deste corte."}


def executar_pipeline(
    observacao: Mapping[str, Any],
    *,
    agora: datetime,
    critico: PortaCritica | None = None,
) -> dict[str, Any]:
    """Executa a cadeia causal sem alterar a entrada ou qualquer sistema externo."""

    foto = deepcopy(dict(observacao))
    foto["as_of"] = agora.isoformat().replace("+00:00", "Z")
    validacao = _validar(foto, agora)
    features = _features(foto, agora)
    politicas = avaliar_regras(features, foto, agora=agora)
    eventos = _detectar_eventos(foto, validacao, features)
    _marcar_politicas(politicas, eventos)
    regra_por_evento = {
        "campaign_onboarding_no_delivery": "nexus_guardiao_72h",
        "budget_limited_with_healthy_quality": "orakul_escala_com_guardas",
        "rank_limited_with_poor_quality": "search_rank_quality_first",
        "valuable_term_blocked_by_negative": "search_negativa_bidirecional",
        "cost_spike": "ads_health_eventos",
        "routine_stale": "ads_health_eventos",
    }
    politicas_disparadas = {p["regra_id"] for p in politicas if p.get("disparou") is True}
    eventos = [e for e in eventos if regra_por_evento.get(e.tipo) in politicas_disparadas]
    conflitos = _conflitos(foto, validacao, features, eventos)
    health = _health_gate(validacao, eventos)
    fatores = _fatores(foto, features)
    tipadas, propostas_ui = _propostas(foto, validacao, features, eventos, conflitos, politicas)
    diagnostico = _diagnostico(foto, validacao, features)
    veredito = _veredito(validacao, eventos, conflitos)
    leitura_caixa = diagnostico["leitura"] if validacao.get("estado") == "atual" else None
    caixa = {"versao": 1, "volc_campaign_id": diagnostico["volc_campaign_id"], "propostas": propostas_ui, "leitura": leitura_caixa}
    evidencias_publicas = [
        {"ref": "source", "fonte": foto.get("source"), "janela": foto.get("janela"), "lido_em": foto.get("lido_em")},
        {"ref": "campaign", "customer_id": foto.get("campaign", {}).get("customer_id"), "campaign_id": foto.get("campaign", {}).get("campaign_id"), "status": foto.get("campaign", {}).get("status"), "channel": foto.get("campaign", {}).get("channel"), "bidding": foto.get("campaign", {}).get("bidding")},
    ]
    contexto_tempo = {"observado_em": foto.get("lido_em"), "janela": foto.get("janela"), "evidencia_ref": "scenario_id:" + str(foto.get("scenario_id"))}
    timeline = [
        {"ordem": 1, "tipo": "observacao", "estado": "recebida", "texto": "Fotografia sintética recebida, sem consulta externa."},
        {"ordem": 2, "tipo": "validacao_frescor", "estado": validacao["estado"], "texto": "Contrato, janela, anulabilidade e futuro foram conferidos."},
        {"ordem": 3, "tipo": "features", "estado": "calculadas", "texto": "Features foram calculadas em Python, sem zero-fill."},
        {"ordem": 4, "tipo": "politicas", "estado": "avaliadas", "texto": f"{len(politicas)} políticas versionadas foram avaliadas."},
        {"ordem": 5, "tipo": "conflitos", "estado": "arbitrados", "texto": f"{len(conflitos)} conflitos foram avaliados antes da decisão."},
        {"ordem": 6, "tipo": "diagnostico", "estado": veredito["tipo"], "texto": veredito["titulo"]},
        {"ordem": 7, "tipo": "proposta", "estado": "bloqueada" if tipadas else "nao_emitida", "texto": "Toda proposta nasce sem autorização e sem executor."},
        {"ordem": 8, "tipo": "replay_eval", "estado": "pronto_para_comparacao", "texto": "Saída pronta para comparação com o esperado dourado."},
    ]
    timeline = [{**item, **contexto_tempo} for item in timeline]
    contexto_critica = {
        "scenario_id": foto.get("scenario_id"),
        "veredito": veredito,
        "health_gate": health,
        "fatores": fatores,
        "politicas": [{k: p[k] for k in ("regra_id", "versao", "resultado")} for p in politicas],
        "conflitos": conflitos,
        "evidencias": evidencias_publicas,
    }
    critica = executar_critica(critico, contexto_critica)
    return {
        "versao_contrato": VERSAO_CONTRATO,
        "scenario_id": foto.get("scenario_id"),
        "rotulo": foto.get("label"),
        "estado_da_leitura": validacao["estado"],
        "health_gate": health,
        "veredito": veredito,
        "fatores": fatores,
        "politicas": politicas,
        "conflitos": conflitos,
        "eventos": [evento.serializar() for evento in eventos],
        "diagnostico": diagnostico,
        "caixa_de_propostas": caixa,
        "propostas_tipadas": [p.serializar() for p in tipadas],
        "execucao": {"estado": "bloqueada", "autorizacao": None, "aplicacao": None, "recibo": None, "mutacoes_executadas": 0},
        "evidencias": evidencias_publicas,
        "features": features,
        "timeline": timeline,
        "critica": critica,
        "autoridade": {"calculadora": "python_puro", "llm": "critico_explicador", "decisao": "politicas_versionadas", "mutacao": "inexistente"},
        "api_google_ads": {"namespace": "v25", "minor_documentada_localmente": "v25.1", "v25_2": "nao_afirmada"},
        "marcas": ["PROTÓTIPO", "DADOS SINTÉTICOS"],
    }
