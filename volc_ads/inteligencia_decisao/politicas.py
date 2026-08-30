"""Políticas sintéticas versionadas do laboratório.

Os limiares deste arquivo servem exclusivamente ao replay dourado. Eles têm
owner, fonte e versão, não são publicação produtiva e não portam literalmente
nenhuma régua do n8n histórico.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from .contratos import RegraDeOtimizacao, avaliar_suficiencia


FONTE = "decision-lab:calibracao-sintetica-v1"
RESPONSAVEL = "VOLC Decision Intelligence Lab"
PERFIS: dict[str, dict[str, float]] = {
    "lab-calibracao-sintetica-v1": {
        "quality_healthy_min": 7.0,
        "cost_spike_ratio_min": 1.75,
        "routine_max_age_hours": 26.0,
        "onboarding_max_age_hours": 72.0,
        "share_loss_min": 0.0,
    }
}
DETECCOES: dict[str, str] = {
    "nexus_guardiao_72h": "0 <= idade_campanha_horas <= onboarding_max_age_hours e impressoes == 0",
    "orakul_escala_com_guardas": "lost_budget > share_loss_min e qualidade_saudavel == true",
    "search_rank_quality_first": "lost_rank > share_loss_min e qualidade_saudavel == false",
    "search_negativa_bidirecional": "termo valioso conflita com negativa no mesmo escopo",
    "ads_health_eventos": "cost_spike_ratio >= limite ou routine_age_hours > limite",
}


def parametros_do_perfil(chave: object) -> Mapping[str, float] | None:
    perfil = PERFIS.get(str(chave or ""))
    return dict(perfil) if perfil else None


def _regra(
    chave: str,
    titulo: str,
    objetivo: str,
    *,
    janela: int,
    dados: tuple[str, ...],
    cliques: int | None = None,
    impressoes: int | None = None,
    conversoes: float | None = None,
    autonomia: str = "T0",
    acao: Mapping[str, Any] | None = None,
) -> RegraDeOtimizacao:
    return RegraDeOtimizacao(
        chave=chave,
        versao=1,
        titulo=titulo,
        objetivo=objetivo,
        plataformas=("GOOGLE_ADS",),
        canais=("SEARCH",),
        janela_minima_dias=janela,
        atraso_conversao_dias=0,
        frescor_maximo_horas=36,
        dados_obrigatorios=dados,
        cooldown_horas=24,
        confianca_minima=0.6,
        condicao_rollback="Nenhuma aplicação existe no laboratório; futura ação exige recibo reversível.",
        rollback_janela_horas=48,
        responsavel=RESPONSAVEL,
        fonte=FONTE,
        declarada_por="missao-vertical-isolada-2026-08-28",
        amostra_minima_cliques=cliques,
        amostra_minima_impressoes=impressoes,
        amostra_minima_conversoes=conversoes,
        limite_alteracao_pct=20,
        nivel_autonomia=autonomia,
        deteccao={"perfil": "sintetico_v1", "publicavel": False},
        acao=dict(acao or {}),
    )


REGRAS: tuple[RegraDeOtimizacao, ...] = (
    _regra(
        "nexus_guardiao_72h",
        "NEXUS, guardião das primeiras 72 horas",
        "Distinguir ausência de entrega de causa comprovada em campanha nova.",
        janela=1,
        dados=("impressoes", "cliques"),
        impressoes=0,
        autonomia="T0",
        acao={"tipo": "diagnosticar", "mutacao": False},
    ),
    _regra(
        "orakul_escala_com_guardas",
        "ORAKUL, escala governada",
        "Reconhecer demanda limitada por orçamento sem atravessar margem, cooldown ou saúde.",
        janela=3,
        dados=("impressoes", "cliques", "custo_micros", "conversoes", "valor_conversao_micros"),
        cliques=10,
        autonomia="T1",
        acao={"tipo": "propor_orcamento", "mutacao": False},
    ),
    _regra(
        "search_rank_quality_first",
        "Search Intelligence, qualidade antes de lance",
        "Separar perda por rank de evidência de qualidade antes de sugerir preço.",
        janela=3,
        dados=("impressoes", "cliques", "custo_micros"),
        impressoes=100,
        autonomia="T1",
        acao={"tipo": "propor_estrutura", "mutacao": False},
    ),
    _regra(
        "search_negativa_bidirecional",
        "Search Terms, conflito reverso de negativa",
        "Propor revisão de negativa existente quando ela bloqueia termo valioso comprovado.",
        janela=3,
        dados=("impressoes", "cliques", "custo_micros", "conversoes"),
        cliques=1,
        autonomia="T1",
        acao={"tipo": "propor_desnegativacao", "mutacao": False},
    ),
    _regra(
        "ads_health_eventos",
        "Ads Monitor, saúde e rotina",
        "Emitir ocorrência deduplicada para spike de custo ou rotina sem heartbeat.",
        janela=2,
        dados=("impressoes", "custo_micros"),
        impressoes=1,
        autonomia="T0",
        acao={"tipo": "ocorrencia", "mutacao": False},
    ),
)


def avaliar_regras(
    features: Mapping[str, Any],
    observacao: Mapping[str, Any],
    *,
    agora: datetime,
) -> list[dict[str, Any]]:
    evidencia = {
        "impressoes": features.get("impressoes"),
        "cliques": features.get("cliques"),
        "custo_micros": features.get("custo_micros"),
        "conversoes": features.get("conversoes"),
        "valor_conversao_micros": features.get("valor_conversao_micros"),
        "janela_inicio": observacao.get("janela", {}).get("inicio"),
        "janela_fim": observacao.get("janela", {}).get("fim"),
        "colhida_em": observacao.get("lido_em"),
    }
    campanha = observacao.get("campaign") or {}
    saida: list[dict[str, Any]] = []
    for regra in REGRAS:
        aplicavel = regra.aplica_a("GOOGLE_ADS", campanha.get("channel"))
        suficiencia = avaliar_suficiencia(evidencia, regra, agora=agora) if aplicavel else None
        saida.append({
            "regra_id": regra.chave,
            "versao": regra.versao,
            "titulo": regra.titulo,
            "owner": regra.responsavel,
            "fonte": regra.fonte,
            "nivel_autonomia": regra.nivel_autonomia,
            "publicavel": False,
            "aplicavel": aplicavel,
            "suficiencia": suficiencia.veredito if suficiencia else "nao_aplicavel",
            "motivo_suficiencia": suficiencia.motivo if suficiencia else None,
            "faltantes": list(suficiencia.faltantes) if suficiencia else [],
            "objetivo": regra.objetivo,
            "parametros_efetivos": {
                "janela_minima_dias": regra.janela_minima_dias,
                "frescor_maximo_horas": regra.frescor_maximo_horas,
                "amostra_minima_cliques": regra.amostra_minima_cliques,
                "amostra_minima_impressoes": regra.amostra_minima_impressoes,
                "amostra_minima_conversoes": regra.amostra_minima_conversoes,
                "cooldown_horas": regra.cooldown_horas,
                "limite_alteracao_pct": regra.limite_alteracao_pct,
                "perfil": observacao.get("policy_profile_id"),
                **(parametros_do_perfil(observacao.get("policy_profile_id")) or {}),
            },
            "deteccao_efetiva": DETECCOES.get(regra.chave),
            "disparou": False,
            "resultado": "não avaliada",
        })
    return saida


def por_id(avaliacoes: Sequence[Mapping[str, Any]], chave: str) -> dict[str, Any]:
    for avaliacao in avaliacoes:
        if avaliacao.get("regra_id") == chave:
            return dict(avaliacao)
    raise KeyError(chave)
