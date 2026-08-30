"""Coletor read-only Google Ads v25 com persistencia tipada.

Nao chama ApplyRecommendation, DismissRecommendation ou qualquer mutate. A
trava do FORGE e conferida antes da primeira chamada. Cada familia e persistida
mesmo quando volta vazia ou falha, para que silencio nunca pareca sucesso.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from google.protobuf.json_format import MessageToDict

from volc_ads.gads.client import cliente
from volc_ads.gads.modo import estado as estado_escrita

from .modelo import (
    DocumentoColeta, EstadoColeta, EstadoValor, Item, Metrica, metrica_de_dict,
)
from .persistencia import CampanhaAtiva, SupabaseGoogleIntelligence

MCC_PADRAO = "6016739364"
_SEGREDO = re.compile(r"(?i)(authorization|bearer|apikey|token|secret|password)[^\s,;]*")


def _dict_proto(valor: Any) -> dict[str, Any]:
    pb = getattr(valor, "_pb", valor)
    return MessageToDict(
        pb, preserving_proto_field_name=True,
        always_print_fields_with_no_presence=False,
    )


def _sanitizar(valor: Any, limite: int = 900) -> str:
    texto = _SEGREDO.sub("[redigido]", str(valor)).replace("\n", " ")
    return texto[:limite]


def _erro(exc: Exception) -> tuple[str, str, str, list[str]]:
    request_ids: list[str] = []
    request_id = getattr(exc, "request_id", None)
    if request_id:
        request_ids.append(str(request_id))
    codigos: list[str] = []
    mensagens: list[str] = []
    for item in getattr(getattr(exc, "failure", None), "errors", []):
        codigos.append(_sanitizar(getattr(item, "error_code", "GOOGLE_ADS_ERROR"), 200))
        mensagens.append(_sanitizar(getattr(item, "message", item), 500))
    codigo = codigos[0] if codigos else type(exc).__name__
    detalhe = " | ".join(mensagens) if mensagens else _sanitizar(exc)
    return codigo, type(exc).__name__, detalhe, request_ids


class ColetorGoogleInteligencia:
    def __init__(
        self, *, login_customer_id: str = MCC_PADRAO,
        persistencia: SupabaseGoogleIntelligence | None = None,
    ) -> None:
        if estado_escrita().get("escrita_permitida"):
            raise RuntimeError("coleta recusada: trava de escrita do Google Ads esta aberta")
        self.login_customer_id = login_customer_id.replace("-", "")
        self.persistencia = persistencia or SupabaseGoogleIntelligence()
        self.google = cliente(self.login_customer_id)
        self.ga = self.google.get_service("GoogleAdsService")

    def _query(self, customer_id: str, gaql: str) -> list[dict[str, Any]]:
        if not gaql.lstrip().upper().startswith("SELECT"):
            raise RuntimeError("somente SELECT e permitido na coleta")
        saida: list[dict[str, Any]] = []
        for lote in self.ga.search_stream(customer_id=customer_id, query=gaql):
            saida.extend(_dict_proto(linha) for linha in lote.results)
        return saida

    @staticmethod
    def _bucket(modo: str, instante: datetime) -> str:
        if modo == "completa":
            return f"daily:{instante.date().isoformat()}"
        bloco = (instante.hour // 4) * 4
        return f"4h:{instante.date().isoformat()}T{bloco:02d}:00Z"

    def _persistir_familia(
        self, *, tipo: str, customer_id: str, bucket: str,
        campanha: CampanhaAtiva | None,
        produzir: Callable[[], DocumentoColeta],
    ) -> tuple[str, str]:
        try:
            documento = produzir()
        except Exception as exc:
            codigo, classe, detalhe, request_ids = _erro(exc)
            documento = DocumentoColeta.agora(
                tipo_sinal=tipo, estado=EstadoColeta.FALHOU,
                customer_id=customer_id, login_customer_id=self.login_customer_id,
                bucket=bucket, quantidade=None,
                volc_campaign_id=campanha.volc_campaign_id if campanha else None,
                campaign_id=campanha.campaign_id if campanha else None,
                request_ids=request_ids, erro_codigo=codigo,
                erro_classe=classe, erro_detalhe=detalhe,
                payload={"somente_leitura": True},
            )
        coleta_id = self.persistencia.registrar(documento)
        return coleta_id, documento.estado.value

    def _recomendacoes_armazenadas(
        self, customer_id: str, bucket: str,
    ) -> DocumentoColeta:
        linhas = self._query(customer_id, """
          SELECT recommendation.resource_name, recommendation.type,
                 recommendation.dismissed, recommendation.campaign,
                 recommendation.campaigns, recommendation.campaign_budget,
                 recommendation.impact
          FROM recommendation
        """)
        return DocumentoColeta.agora(
            tipo_sinal="RECOMENDACOES_ARMAZENADAS",
            estado=EstadoColeta.COM_DADOS if linhas else EstadoColeta.VAZIO_CONFIRMADO,
            customer_id=customer_id, login_customer_id=self.login_customer_id,
            bucket=bucket, quantidade=len(linhas),
            payload={"somente_leitura": True, "escopo": "conta"},
            itens=[
                Item(
                    "recommendation", linha,
                    linha.get("recommendation", {}).get("resource_name"),
                ) for linha in linhas
            ],
        )

    def _experimentos(self, customer_id: str, bucket: str) -> DocumentoColeta:
        linhas = self._query(customer_id, """
          SELECT experiment.resource_name, experiment.experiment_id, experiment.name,
                 experiment.status, experiment.type,
                 experiment.start_date, experiment.end_date
          FROM experiment
        """)
        return DocumentoColeta.agora(
            tipo_sinal="EXPERIMENTOS",
            estado=EstadoColeta.COM_DADOS if linhas else EstadoColeta.VAZIO_CONFIRMADO,
            customer_id=customer_id, login_customer_id=self.login_customer_id,
            bucket=bucket, quantidade=len(linhas),
            payload={"somente_leitura": True, "escopo": "conta"},
            itens=[
                Item("experiment", linha, linha.get("experiment", {}).get("resource_name"))
                for linha in linhas
            ],
        )

    def _diagnostico(
        self, campanha: CampanhaAtiva, bucket: str, inicio: date, fim: date,
    ) -> DocumentoColeta:
        cid = campanha.customer_id
        campaign_id = campanha.campaign_id
        base = self._query(cid, f"""
          SELECT campaign.id, campaign.name, campaign.status,
                 campaign.primary_status, campaign.primary_status_reasons,
                 campaign.serving_status, campaign.bidding_strategy_type,
                 campaign_budget.amount_micros,
                 campaign_budget.has_recommended_budget,
                 campaign_budget.recommended_budget_amount_micros
          FROM campaign WHERE campaign.id = {campaign_id}
        """)
        if not base:
            return DocumentoColeta.agora(
                tipo_sinal="DIAGNOSTICO_ENTREGA", estado=EstadoColeta.VAZIO_CONFIRMADO,
                customer_id=cid, login_customer_id=self.login_customer_id,
                bucket=bucket, quantidade=0,
                volc_campaign_id=campanha.volc_campaign_id, campaign_id=campaign_id,
                janela_inicio=inicio, janela_fim=fim,
                payload={"motivo": "campanha ausente na resposta", "somente_leitura": True},
            )
        desempenho = self._query(cid, f"""
          SELECT campaign.id, metrics.impressions, metrics.clicks,
                 metrics.cost_micros, metrics.conversions,
                 metrics.all_conversions, metrics.search_impression_share,
                 metrics.search_rank_lost_impression_share,
                 metrics.search_budget_lost_impression_share,
                 metrics.search_top_impression_share,
                 metrics.search_absolute_top_impression_share
          FROM campaign
          WHERE campaign.id = {campaign_id}
            AND segments.date BETWEEN '{inicio.isoformat()}' AND '{fim.isoformat()}'
        """)
        keywords = self._query(cid, f"""
          SELECT ad_group.id, ad_group_criterion.criterion_id,
                 ad_group_criterion.keyword.text,
                 ad_group_criterion.keyword.match_type,
                 ad_group_criterion.primary_status,
                 ad_group_criterion.primary_status_reasons,
                 ad_group_criterion.effective_cpc_bid_micros,
                 ad_group_criterion.position_estimates.first_page_cpc_micros,
                 ad_group_criterion.position_estimates.top_of_page_cpc_micros,
                 ad_group_criterion.quality_info.quality_score,
                 metrics.impressions, metrics.clicks, metrics.cost_micros,
                 metrics.conversions
          FROM keyword_view
          WHERE campaign.id = {campaign_id}
            AND ad_group.status != 'REMOVED'
            AND ad_group_criterion.status != 'REMOVED'
            AND segments.date BETWEEN '{inicio.isoformat()}' AND '{fim.isoformat()}'
        """)
        anuncios = self._query(cid, f"""
          SELECT ad_group_ad.ad.id, ad_group_ad.status,
                 ad_group_ad.primary_status, ad_group_ad.primary_status_reasons,
                 ad_group_ad.ad_strength, ad_group_ad.action_items,
                 ad_group_ad.policy_summary.approval_status,
                 ad_group_ad.policy_summary.review_status
          FROM ad_group_ad
          WHERE campaign.id = {campaign_id}
            AND ad_group_ad.status != 'REMOVED'
        """)

        metricas: list[Metrica] = []
        perf = desempenho[0] if desempenho else {}
        for nome in (
            "impressions", "clicks", "cost_micros", "conversions",
            "all_conversions", "search_impression_share",
            "search_rank_lost_impression_share", "search_budget_lost_impression_share",
            "search_top_impression_share", "search_absolute_top_impression_share",
        ):
            metricas.append(metrica_de_dict(
                perf, ("metrics", nome), recurso_tipo="campaign",
                recurso_externo=campaign_id, nome=nome,
                unidade="micros" if nome == "cost_micros" else None,
                moeda="BRL" if nome == "cost_micros" else None,
            ))
        metricas.append(metrica_de_dict(
            base[0], ("campaign_budget", "amount_micros"),
            recurso_tipo="campaign", recurso_externo=campaign_id,
            nome="daily_budget_micros", unidade="micros", moeda="BRL",
        ))
        estimativas = [
            int(k["ad_group_criterion"]["position_estimates"]["first_page_cpc_micros"])
            for k in keywords
            if k.get("ad_group_criterion", {}).get("position_estimates", {}).get("first_page_cpc_micros") is not None
        ]
        metricas.append(Metrica(
            "campaign", campaign_id, "keyword_count", EstadoValor.MEDIDO,
            valor_numerico=len(keywords), unidade="count",
        ))
        metricas.append(Metrica(
            "campaign", campaign_id, "first_page_cpc_median_micros",
            EstadoValor.MEDIDO if estimativas else EstadoValor.AUSENTE,
            valor_numerico=statistics.median(estimativas) if estimativas else None,
            unidade="micros", moeda="BRL",
        ))

        itens = [Item("campaign", base[0], campaign_id)]
        itens += [Item("keyword", linha, str(linha.get("ad_group_criterion", {}).get("criterion_id", ""))) for linha in keywords]
        itens += [Item("ad", linha, str(linha.get("ad_group_ad", {}).get("ad", {}).get("id", ""))) for linha in anuncios]
        return DocumentoColeta.agora(
            tipo_sinal="DIAGNOSTICO_ENTREGA", estado=EstadoColeta.COM_DADOS,
            customer_id=cid, login_customer_id=self.login_customer_id,
            bucket=bucket, quantidade=len(itens),
            volc_campaign_id=campanha.volc_campaign_id, campaign_id=campaign_id,
            janela_inicio=inicio, janela_fim=fim,
            payload={
                "somente_leitura": True,
                "desempenho_retornou": bool(desempenho),
                "keywords": len(keywords), "anuncios": len(anuncios),
            }, itens=itens, metricas=metricas,
        )

    def _simulacoes(self, campanha: CampanhaAtiva, bucket: str) -> DocumentoColeta:
        linhas = self._query(campanha.customer_id, f"""
          SELECT campaign_simulation.resource_name,
                 campaign_simulation.campaign_id,
                 campaign_simulation.type,
                 campaign_simulation.modification_method,
                 campaign_simulation.start_date,
                 campaign_simulation.end_date,
                 campaign_simulation.budget_point_list.points,
                 campaign_simulation.cpc_bid_point_list.points,
                 campaign_simulation.target_cpa_point_list.points,
                 campaign_simulation.target_impression_share_point_list.points,
                 campaign_simulation.target_roas_point_list.points
          FROM campaign_simulation
          WHERE campaign_simulation.campaign_id = {campanha.campaign_id}
        """)
        return DocumentoColeta.agora(
            tipo_sinal="SIMULACOES_CAMPANHA",
            estado=EstadoColeta.COM_DADOS if linhas else EstadoColeta.VAZIO_CONFIRMADO,
            customer_id=campanha.customer_id,
            login_customer_id=self.login_customer_id, bucket=bucket,
            quantidade=len(linhas), volc_campaign_id=campanha.volc_campaign_id,
            campaign_id=campanha.campaign_id,
            payload={"somente_leitura": True},
            itens=[
                Item("campaign_simulation", linha,
                     linha.get("campaign_simulation", {}).get("resource_name"))
                for linha in linhas
            ],
        )

    def _recomendacoes_geradas(self, campanha: CampanhaAtiva, bucket: str) -> DocumentoColeta:
        cid = campanha.customer_id
        campaign = self._query(cid, f"""
          SELECT campaign.id, campaign.advertising_channel_type,
                 campaign.bidding_strategy_type, campaign_budget.amount_micros
          FROM campaign WHERE campaign.id = {campanha.campaign_id}
        """)
        keywords = self._query(cid, f"""
          SELECT ad_group.id, ad_group.type,
                 ad_group_criterion.keyword.text,
                 ad_group_criterion.keyword.match_type
          FROM keyword_view
          WHERE campaign.id = {campanha.campaign_id}
            AND ad_group.status = 'ENABLED'
            AND ad_group_criterion.status = 'ENABLED'
        """)
        if not campaign or not keywords:
            return DocumentoColeta.agora(
                tipo_sinal="RECOMENDACOES_GERADAS", estado=EstadoColeta.INELEGIVEL,
                customer_id=cid, login_customer_id=self.login_customer_id,
                bucket=bucket, quantidade=None,
                volc_campaign_id=campanha.volc_campaign_id,
                campaign_id=campanha.campaign_id,
                payload={"motivo": "campanha ou keywords habilitadas ausentes", "somente_leitura": True},
            )
        linha = campaign[0]
        request = self.google.get_type("GenerateRecommendationsRequest")
        request.customer_id = cid
        request.recommendation_types.extend([
            self.google.enums.RecommendationTypeEnum.CAMPAIGN_BUDGET,
            self.google.enums.RecommendationTypeEnum.MAXIMIZE_CLICKS_OPT_IN,
            self.google.enums.RecommendationTypeEnum.MAXIMIZE_CONVERSIONS_OPT_IN,
        ])
        request.advertising_channel_type = linha["campaign"]["advertising_channel_type"]
        request.bidding_info.bidding_strategy_type = linha["campaign"]["bidding_strategy_type"]
        request.budget_info.current_budget = int(linha["campaign_budget"]["amount_micros"])
        request.country_codes.append("BR")
        request.language_codes.append("pt")
        request.positive_locations_ids.append(2076)
        por_grupo: dict[str, dict[str, Any]] = {}
        for keyword in keywords:
            gid = str(keyword["ad_group"]["id"])
            grupo = por_grupo.setdefault(gid, {
                "ad_group_type": keyword["ad_group"]["type_"], "keywords": [],
            })
            grupo["keywords"].append(keyword["ad_group_criterion"]["keyword"])
        request.ad_group_info.extend(por_grupo.values())
        response = self.google.get_service("RecommendationService").generate_recommendations(request=request)
        recomendacoes = [_dict_proto(item) for item in response.recommendations]
        return DocumentoColeta.agora(
            tipo_sinal="RECOMENDACOES_GERADAS",
            estado=EstadoColeta.COM_DADOS if recomendacoes else EstadoColeta.VAZIO_CONFIRMADO,
            customer_id=cid, login_customer_id=self.login_customer_id,
            bucket=bucket, quantidade=len(recomendacoes),
            volc_campaign_id=campanha.volc_campaign_id, campaign_id=campanha.campaign_id,
            payload={
                "somente_leitura": True,
                "tipos_solicitados": [
                    "CAMPAIGN_BUDGET", "MAXIMIZE_CLICKS_OPT_IN",
                    "MAXIMIZE_CONVERSIONS_OPT_IN",
                ],
            },
            itens=[Item("generated_recommendation", item) for item in recomendacoes],
        )

    def _forecast(self, campanha: CampanhaAtiva, bucket: str) -> DocumentoColeta:
        cid = campanha.customer_id
        base = self._query(cid, f"""
          SELECT campaign_budget.amount_micros
          FROM campaign WHERE campaign.id = {campanha.campaign_id}
        """)
        keywords = self._query(cid, f"""
          SELECT ad_group.id, ad_group_criterion.keyword.text,
                 ad_group_criterion.keyword.match_type,
                 ad_group_criterion.effective_cpc_bid_micros,
                 ad_group_criterion.position_estimates.first_page_cpc_micros
          FROM keyword_view
          WHERE campaign.id = {campanha.campaign_id}
            AND ad_group.status = 'ENABLED'
            AND ad_group_criterion.status = 'ENABLED'
        """)
        if not base or not keywords:
            return DocumentoColeta.agora(
                tipo_sinal="FORECAST_KEYWORDS", estado=EstadoColeta.INELEGIVEL,
                customer_id=cid, login_customer_id=self.login_customer_id,
                bucket=bucket, quantidade=None,
                volc_campaign_id=campanha.volc_campaign_id,
                campaign_id=campanha.campaign_id,
                payload={"motivo": "campanha ou keywords habilitadas ausentes", "somente_leitura": True},
            )
        bids = [
            int(k["ad_group_criterion"]["effective_cpc_bid_micros"])
            for k in keywords
            if k.get("ad_group_criterion", {}).get("effective_cpc_bid_micros") is not None
        ]
        first_page = [
            int(k["ad_group_criterion"]["position_estimates"]["first_page_cpc_micros"])
            for k in keywords
            if k.get("ad_group_criterion", {}).get("position_estimates", {}).get("first_page_cpc_micros") is not None
        ]
        if not bids:
            return DocumentoColeta.agora(
                tipo_sinal="FORECAST_KEYWORDS", estado=EstadoColeta.INELEGIVEL,
                customer_id=cid, login_customer_id=self.login_customer_id,
                bucket=bucket, quantidade=None,
                volc_campaign_id=campanha.volc_campaign_id,
                campaign_id=campanha.campaign_id,
                payload={"motivo": "lance efetivo ausente", "somente_leitura": True},
            )
        atual = int(statistics.median(bids))
        orcamento = int(base[0]["campaign_budget"]["amount_micros"])
        candidatos = [atual]
        if first_page:
            candidatos.extend((
                int(statistics.median(first_page)),
                sorted(first_page)[round((len(first_page) - 1) * .75)],
            ))
        cenarios = sorted({(bid, orcamento) for bid in candidatos})
        if first_page:
            cenarios.append((int(statistics.median(first_page)), orcamento * 2))

        agrupados: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for keyword in keywords:
            agrupados[str(keyword["ad_group"]["id"])].append(
                keyword["ad_group_criterion"]["keyword"]
            )
        inicio = date.today() + timedelta(days=1)
        fim = inicio + timedelta(days=6)
        planner = self.google.get_service("KeywordPlanIdeaService")
        itens: list[Item] = []
        falhas: list[dict[str, str]] = []
        for bid, budget in cenarios:
            request = self.google.get_type("GenerateKeywordForecastMetricsRequest")
            request.customer_id = cid
            request.currency_code = "BRL"
            request.forecast_period.start_date = inicio.isoformat()
            request.forecast_period.end_date = fim.isoformat()
            request.campaign.geo_target_constants.append(self.ga.geo_target_constant_path(2076))
            request.campaign.language_constants.append(self.ga.language_constant_path(1014))
            estrategia = request.campaign.bidding_strategy.manual_cpc_bidding_strategy
            estrategia.max_cpc_bid_micros = bid
            estrategia.daily_budget_micros = budget
            for grupo in agrupados.values():
                request.campaign.ad_groups.append({"keywords": grupo})
            try:
                response = planner.generate_keyword_forecast_metrics(request=request)
                itens.append(Item("keyword_forecast_scenario", {
                    "max_cpc_micros": str(bid),
                    "daily_budget_micros": str(budget),
                    "period": {"start": inicio.isoformat(), "end": fim.isoformat()},
                    "metrics": _dict_proto(response.campaign_forecast_metrics),
                }, f"{bid}:{budget}"))
            except Exception as exc:
                codigo, classe, detalhe, _ = _erro(exc)
                falhas.append({"codigo": codigo, "classe": classe, "detalhe": detalhe})

        if not itens:
            codigo = falhas[0]["codigo"] if falhas else "FORECAST_SEM_RESPOSTA"
            classe = falhas[0]["classe"] if falhas else "ForecastError"
            detalhe = falhas[0]["detalhe"] if falhas else "nenhum cenario retornou"
            return DocumentoColeta.agora(
                tipo_sinal="FORECAST_KEYWORDS", estado=EstadoColeta.FALHOU,
                customer_id=cid, login_customer_id=self.login_customer_id,
                bucket=bucket, quantidade=None,
                volc_campaign_id=campanha.volc_campaign_id,
                campaign_id=campanha.campaign_id,
                payload={"somente_leitura": True, "cenarios_tentados": len(cenarios)},
                erro_codigo=codigo, erro_classe=classe, erro_detalhe=detalhe,
            )
        return DocumentoColeta.agora(
            tipo_sinal="FORECAST_KEYWORDS",
            estado=EstadoColeta.PARCIAL if falhas else EstadoColeta.COM_DADOS,
            customer_id=cid, login_customer_id=self.login_customer_id,
            bucket=bucket, quantidade=len(itens),
            volc_campaign_id=campanha.volc_campaign_id,
            campaign_id=campanha.campaign_id,
            janela_inicio=inicio, janela_fim=fim,
            payload={
                "somente_leitura": True, "cenarios_tentados": len(cenarios),
                "cenarios_com_resposta": len(itens), "falhas": falhas,
            }, itens=itens,
        )

    def executar(self, *, modo: str = "completa", customer_id: str | None = None) -> dict[str, Any]:
        if modo not in {"frequente", "completa"}:
            raise ValueError("modo precisa ser frequente ou completa")
        agora = datetime.now(timezone.utc)
        bucket = self._bucket(modo, agora)
        inicio = agora.date() - timedelta(days=13)
        fim = agora.date()
        campanhas = self.persistencia.campanhas_search_ativas(customer_id)
        por_conta: dict[str, list[CampanhaAtiva]] = defaultdict(list)
        for campanha in campanhas:
            por_conta[campanha.customer_id].append(campanha)
        resultado: dict[str, Any] = {"modo": modo, "bucket": bucket, "coletas": []}

        for conta, campanhas_conta in sorted(por_conta.items()):
            for tipo, produtor in (
                ("RECOMENDACOES_ARMAZENADAS", lambda c=conta: self._recomendacoes_armazenadas(c, bucket)),
                ("EXPERIMENTOS", lambda c=conta: self._experimentos(c, bucket)),
            ):
                cid, st = self._persistir_familia(
                    tipo=tipo, customer_id=conta, bucket=bucket,
                    campanha=None, produzir=produtor,
                )
                resultado["coletas"].append({"coleta_id": cid, "tipo": tipo, "estado": st, "customer_id": conta})

            for campanha in campanhas_conta:
                familias: list[tuple[str, Callable[[], DocumentoColeta]]] = [
                    ("DIAGNOSTICO_ENTREGA", lambda cp=campanha: self._diagnostico(cp, bucket, inicio, fim)),
                    ("SIMULACOES_CAMPANHA", lambda cp=campanha: self._simulacoes(cp, bucket)),
                ]
                if modo == "completa":
                    familias.extend((
                        ("RECOMENDACOES_GERADAS", lambda cp=campanha: self._recomendacoes_geradas(cp, bucket)),
                        ("FORECAST_KEYWORDS", lambda cp=campanha: self._forecast(cp, bucket)),
                    ))
                for tipo, produtor in familias:
                    coleta_id, st = self._persistir_familia(
                        tipo=tipo, customer_id=conta, bucket=bucket,
                        campanha=campanha, produzir=produtor,
                    )
                    resultado["coletas"].append({
                        "coleta_id": coleta_id, "tipo": tipo, "estado": st,
                        "customer_id": conta, "campaign_id": campanha.campaign_id,
                    })
        resultado["total"] = len(resultado["coletas"])
        return resultado


def executar_coleta(*, modo: str = "completa", customer_id: str | None = None) -> dict[str, Any]:
    return ColetorGoogleInteligencia().executar(modo=modo, customer_id=customer_id)
