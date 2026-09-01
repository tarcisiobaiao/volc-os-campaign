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

from .alvo import (
    MOTIVO_SIMULACAO_SEM_HISTORICO, ORIGEM_ALVO, AlvoColeta, ErroAlvoInvalido,
    conferir_identidade_devolvida, familias_nao_suportadas, motivo_nao_suportado,
    simulacao_elegivel,
)
from .modelo import (
    DocumentoColeta, EstadoColeta, EstadoValor, Item, Metrica, metrica_de_dict,
)
from .persistencia import CampanhaAtiva, SupabaseGoogleIntelligence
from . import pmax as pmax_dominio

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
        cliente_google: Any | None = None,
        tipos_sinal_do_ledger: frozenset[str] | None = None,
    ) -> None:
        if estado_escrita().get("escrita_permitida"):
            raise RuntimeError("coleta recusada: trava de escrita do Google Ads esta aberta")
        self.login_customer_id = login_customer_id.replace("-", "")
        self.persistencia = persistencia or SupabaseGoogleIntelligence()
        self.google = cliente_google or cliente(self.login_customer_id)
        self.ga = self.google.get_service("GoogleAdsService")
        # O vocabulario de `tipo_sinal` que o ledger aceita hoje. Injetavel para
        # que a prova de que a lacuna PMax mora no CHECK do Postgres — e nao
        # neste codigo — possa ser executada sem um banco por perto.
        self.tipos_sinal_do_ledger = (
            pmax_dominio.TIPOS_SINAL_ACEITOS_PELO_LEDGER
            if tipos_sinal_do_ledger is None else frozenset(tipos_sinal_do_ledger)
        )

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
        origem: str | None = None,
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
        if origem is not None:
            # Procedencia vive no payload, nunca na chave de idempotencia: o
            # recibo diz de onde veio sem que repetir a coleta crie outro.
            documento.payload = {**documento.payload, "origem": origem}
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

    def _simulacoes(
        self, campanha: CampanhaAtiva, bucket: str, *,
        elegivel: bool | None = None, sonda: dict[str, Any] | None = None,
    ) -> DocumentoColeta:
        """``elegivel=None`` e ``sonda=None`` preservam a coleta continua.

        So o caminho one-shot investiga o historico da campanha, e so ele pode
        rebaixar ausencia a INELEGIVEL — com prova, nunca por suposicao. Quando
        ha sonda, o retrato dela entra no payload mesmo que ela nao tenha
        enxergado nada: e o que impede uma sonda cega de virar um vazio
        indistinguivel de um vazio observado.
        """

        extra = {} if sonda is None else {"sonda": sonda}
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
        if not linhas and elegivel is False:
            return DocumentoColeta.agora(
                tipo_sinal="SIMULACOES_CAMPANHA", estado=EstadoColeta.INELEGIVEL,
                customer_id=campanha.customer_id,
                login_customer_id=self.login_customer_id, bucket=bucket,
                quantidade=None, volc_campaign_id=campanha.volc_campaign_id,
                campaign_id=campanha.campaign_id,
                payload={
                    "motivo": MOTIVO_SIMULACAO_SEM_HISTORICO,
                    "somente_leitura": True, **extra,
                },
            )
        return DocumentoColeta.agora(
            tipo_sinal="SIMULACOES_CAMPANHA",
            estado=EstadoColeta.COM_DADOS if linhas else EstadoColeta.VAZIO_CONFIRMADO,
            customer_id=campanha.customer_id,
            login_customer_id=self.login_customer_id, bucket=bucket,
            quantidade=len(linhas), volc_campaign_id=campanha.volc_campaign_id,
            campaign_id=campanha.campaign_id,
            payload={"somente_leitura": True, **extra},
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

    # -- caminho one-shot por identidade canonica explicita -------------------

    def _nao_suportado(
        self, tipo: str, campanha: CampanhaAtiva, bucket: str,
    ) -> DocumentoColeta:
        """Conclusao de dominio: a pergunta nao existe para este canal.

        Nao gasta chamada, nao inventa quantidade e nao se confunde com vazio.
        """

        return DocumentoColeta.agora(
            tipo_sinal=tipo, estado=EstadoColeta.NAO_SUPORTADO,
            customer_id=campanha.customer_id,
            login_customer_id=self.login_customer_id, bucket=bucket,
            quantidade=None, volc_campaign_id=campanha.volc_campaign_id,
            campaign_id=campanha.campaign_id,
            payload={
                "motivo": motivo_nao_suportado(campanha.canal),
                "canal": campanha.canal, "somente_leitura": True,
            },
        )

    def _sondar_veiculacao(
        self, campanha: CampanhaAtiva, inicio: date, fim: date,
    ) -> tuple[dict[str, Any], bool | None, date | None]:
        """Sonda read-only: a campanha veiculou na janela, e quando ela comecou?

        Serve so para decidir entre ``vazio_confirmado`` e ``inelegivel`` na
        simulacao — nunca rebaixa por suposicao.

        ⚠️ A sonda le ``campaign``; a familia le ``campaign_simulation``. Sao
        recursos diferentes, entao a sonda PODE falhar sozinha, e a consulta da
        familia terminar bem. Por isso o retrato dela viaja para dentro do
        recibo: uma sonda cega produzindo ``vazio_confirmado`` tem de ser
        distinguivel de um vazio observado com a sonda enxergando. Sem isso os
        dois recibos sairiam byte a byte iguais, ate no ``payload_sha256``, e a
        degradacao seria invisivel no banco.
        """

        cid = campanha.customer_id

        def cega(motivo: str, **extra: Any) -> tuple[dict[str, Any], None, None]:
            return {"estado": motivo, "veiculou_na_janela": None, **extra}, None, None

        try:
            base = self._query(cid, f"""
              SELECT campaign.id, campaign.start_date_time
              FROM campaign WHERE campaign.id = {campanha.campaign_id}
            """)
        except Exception as exc:
            codigo, classe, _, _ = _erro(exc)
            return cega("falhou", erro_codigo=codigo, erro_classe=classe)
        if not base:
            return cega("indeterminado", motivo="campanha ausente na resposta")

        try:
            desempenho = self._query(cid, f"""
              SELECT campaign.id, metrics.impressions
              FROM campaign
              WHERE campaign.id = {campanha.campaign_id}
                AND segments.date BETWEEN '{inicio.isoformat()}' AND '{fim.isoformat()}'
            """)
        except Exception as exc:
            codigo, classe, _, _ = _erro(exc)
            return cega("falhou", erro_codigo=codigo, erro_classe=classe)

        # Relatorio segmentado por data omite dias sem atividade: nenhuma linha
        # na janela inteira e ausencia de veiculacao, nao ausencia de leitura.
        veiculou: bool | None = False
        for linha in desempenho:
            valor = linha.get("metrics", {}).get("impressions")
            if valor is None:
                veiculou = None  # linha veio sem a metrica: nao sabemos
                break
            if int(valor) > 0:
                veiculou = True
                break
        comeco = _data_de_inicio(base[0])
        sonda = {
            "estado": "medido" if veiculou is not None else "indeterminado",
            "veiculou_na_janela": veiculou,
            "inicio_da_campanha": comeco.isoformat() if comeco else None,
            "janela": [inicio.isoformat(), fim.isoformat()],
        }
        return sonda, veiculou, comeco

    def executar_alvo(
        self, alvo: AlvoColeta, *, modo: str = "completa",
    ) -> dict[str, Any]:
        """Coleta uma unica campanha nomeada, em qualquer estado externo.

        Uma execucao, um alvo, sem agenda propria — a escolha da autoridade de
        frequencia continua em aberto em P09-T14 e nao passa por aqui. Reutiliza
        as mesmas familias, o mesmo bucket e a mesma persistencia da coleta
        continua, entao repetir o comando devolve o mesmo recibo.

        ⚠️ Idempotencia por bucket tem um custo declarado: se a campanha MUDAR
        entre duas execucoes do mesmo bucket, a segunda leitura e deduplicada e
        o recibo antigo prevalece (a RPC devolve o id existente sem regravar).
        E o comportamento pedido — nao duplicar observacao — mas quem precisa da
        leitura nova precisa de outro bucket, nao de outra chamada.
        """

        if not isinstance(alvo, AlvoColeta):
            raise ErroAlvoInvalido("alvo precisa ser AlvoColeta")
        if modo not in {"frequente", "completa"}:
            raise ValueError("modo precisa ser frequente ou completa")

        # Fail-closed antes da primeira chamada ao Google: a persistencia
        # resolve, e o coletor reconfere por conta propria o que recebeu.
        campanha = self.persistencia.campanha_por_identidade(alvo)
        conferir_identidade_devolvida(alvo, campanha)

        agora = datetime.now(timezone.utc)
        bucket = self._bucket(modo, agora)
        inicio = agora.date() - timedelta(days=13)
        fim = agora.date()
        sonda, veiculou, comeco = self._sondar_veiculacao(campanha, inicio, fim)
        elegivel = simulacao_elegivel(
            veiculou_na_janela=veiculou, inicio_da_campanha=comeco,
            janela_inicio=inicio,
        )

        familias: list[tuple[str, Callable[[], DocumentoColeta]]] = [
            ("DIAGNOSTICO_ENTREGA", lambda: self._diagnostico(campanha, bucket, inicio, fim)),
            ("SIMULACOES_CAMPANHA", lambda: self._simulacoes(
                campanha, bucket, elegivel=elegivel, sonda=sonda,
            )),
        ]
        if modo == "completa":
            familias.extend((
                ("RECOMENDACOES_GERADAS", lambda: self._recomendacoes_geradas(campanha, bucket)),
                ("FORECAST_KEYWORDS", lambda: self._forecast(campanha, bucket)),
            ))
        nao_suportadas = set(familias_nao_suportadas(campanha.canal))

        resultado: dict[str, Any] = {
            "modo": modo, "bucket": bucket, "origem": ORIGEM_ALVO,
            "customer_id": campanha.customer_id,
            "volc_campaign_id": campanha.volc_campaign_id,
            "campaign_id": campanha.campaign_id,
            "canal": campanha.canal, "estado_externo": campanha.estado_externo,
            "sonda": sonda, "simulacao_elegivel": elegivel,
            "coletas": [],
        }
        for tipo, produtor in familias:
            if tipo in nao_suportadas:
                produtor = lambda t=tipo: self._nao_suportado(t, campanha, bucket)
            coleta_id, estado = self._persistir_familia(
                tipo=tipo, customer_id=campanha.customer_id, bucket=bucket,
                campanha=campanha, produzir=produtor, origem=ORIGEM_ALVO,
            )
            resultado["coletas"].append({
                "coleta_id": coleta_id, "tipo": tipo, "estado": estado,
                "customer_id": campanha.customer_id,
                "campaign_id": campanha.campaign_id,
            })
        resultado["total"] = len(resultado["coletas"])
        return resultado

    # -- observabilidade read-only de Performance Max (P04-T07) ---------------

    def _persistir_pmax(
        self, *, familia: str, campanha: CampanhaAtiva, bucket: str,
        janela: tuple[date, date], produzir: Callable[[], DocumentoColeta],
    ) -> dict[str, Any]:
        """Produz o recibo da familia e o grava — se o ledger tiver onde.

        A leitura acontece de qualquer jeito. O que o CHECK da v12_01 decide e
        se ela vira linha no banco; quando nao vira, a recusa e NOMEADA no
        resultado, com a migration que a destravaria. Um `except` mudo aqui
        transformaria a lacuna num vazio, que e exatamente o que esta coleta
        existe para nao fazer.
        """

        try:
            documento = produzir()
        except Exception as exc:
            codigo, classe, detalhe, request_ids = _erro(exc)
            documento = DocumentoColeta.agora(
                tipo_sinal=pmax_dominio.TIPO_SINAL_POR_FAMILIA[familia],
                familia=familia, estado=EstadoColeta.FALHOU,
                customer_id=campanha.customer_id,
                login_customer_id=self.login_customer_id, bucket=bucket,
                quantidade=None, volc_campaign_id=campanha.volc_campaign_id,
                campaign_id=campanha.campaign_id, request_ids=request_ids,
                erro_codigo=codigo, erro_classe=classe, erro_detalhe=detalhe,
                payload={
                    "somente_leitura": True, "fonte": pmax_dominio.FONTE_GOOGLE_ADS,
                    "canal": pmax_dominio.CANAL_PMAX, "bucket": bucket,
                    "janela_da_execucao": [janela[0].isoformat(), janela[1].isoformat()],
                },
            )
        documento.payload = {**documento.payload, "origem": ORIGEM_ALVO}

        recusa = pmax_dominio.recusa_de_persistencia(
            familia, tipos_aceitos=self.tipos_sinal_do_ledger,
        )
        serializado = documento.serializar()
        coleta_id = None if recusa else self.persistencia.registrar(documento)
        return {
            **serializado,
            "familia": familia,
            "persistido": recusa is None,
            "coleta_id": coleta_id,
            "recusa_de_persistencia": None if recusa is None else recusa.serializar(),
        }

    def executar_alvo_pmax(
        self, alvo: AlvoColeta, *, modo: str = "completa",
    ) -> dict[str, Any]:
        """Fotografa UMA campanha Performance Max nomeada, sem tocar em nada.

        Mesma identidade completa, mesmo bucket, mesma idempotencia e mesmo
        vocabulario de estados da coleta Search. O que muda sao as perguntas:
        aqui elas sao sobre grupos de recursos, assets, sinais, desempenho por
        grupo e a segunda opiniao oficial sobre a forca do anuncio.

        ⚠️ Nao substitui `executar_alvo`, e nao e chamada por ele. Sao duas
        perguntas diferentes sobre a mesma campanha, e juntar as duas faria uma
        familia que cai levar a outra junto.
        """

        if not isinstance(alvo, AlvoColeta):
            raise ErroAlvoInvalido("alvo precisa ser AlvoColeta")
        if modo not in {"frequente", "completa"}:
            raise ValueError("modo precisa ser frequente ou completa")

        # Fail-closed em duas etapas, nesta ordem: primeiro a identidade
        # (a campanha existe, e e desta conta), depois o canal. Nenhuma consulta
        # especifica de PMax sai antes das duas passarem.
        campanha = self.persistencia.campanha_por_identidade(alvo)
        conferir_identidade_devolvida(alvo, campanha)
        canal = pmax_dominio.exigir_canal_pmax(campanha.canal)

        agora = datetime.now(timezone.utc)
        bucket = self._bucket(modo, agora)
        janela = (agora.date() - timedelta(days=13), agora.date())
        comum = {
            "campanha": campanha, "login_customer_id": self.login_customer_id,
            "bucket": bucket, "janela": janela,
        }

        resultado: dict[str, Any] = {
            "modo": modo, "bucket": bucket, "origem": ORIGEM_ALVO,
            "customer_id": campanha.customer_id,
            "volc_campaign_id": campanha.volc_campaign_id,
            "campaign_id": campanha.campaign_id,
            "canal": canal, "estado_externo": campanha.estado_externo,
            "janela": [janela[0].isoformat(), janela[1].isoformat()],
            "coletas": [],
        }

        def registrar(familia: str, produzir: Callable[[], DocumentoColeta]) -> None:
            resultado["coletas"].append(self._persistir_pmax(
                familia=familia, campanha=campanha, bucket=bucket,
                janela=janela, produzir=produzir,
            ))

        cid = campanha.customer_id

        # 1. a campanha, como a API a enxerga. `campanha_lida` distingue tres
        #    coisas que uma lista vazia confundiria: leu e achou, leu e nao
        #    achou, e nao conseguiu ler.
        campanha_lida: bool | None = None
        linhas_campanha: list[dict[str, Any]] = []

        def ler_campanha() -> DocumentoColeta:
            nonlocal campanha_lida, linhas_campanha
            linhas_campanha = self._query(
                cid, pmax_dominio.query_campanha(campanha.campaign_id)
            )
            campanha_lida = bool(linhas_campanha)
            return pmax_dominio.documento_campanha(linhas=linhas_campanha, **comum)

        registrar(pmax_dominio.FAMILIA_CAMPANHA, ler_campanha)

        # 2. os grupos de recursos. `grupos` fica None se a leitura caiu — e e
        #    essa distincao que impede o desempenho de inventar grupos ausentes.
        grupos: list[str] | None = None

        def ler_grupos() -> DocumentoColeta:
            nonlocal grupos
            linhas = self._query(
                cid, pmax_dominio.query_asset_groups(campanha.campaign_id)
            )
            grupos = _ids_de_asset_group(linhas)
            return pmax_dominio.documento_asset_groups(linhas=linhas, **comum)

        registrar(pmax_dominio.FAMILIA_ASSET_GROUPS, ler_grupos)

        # 3. os vinculos asset <-> grupo.
        assets_pedidos: list[str] | None = None

        def ler_vinculos() -> DocumentoColeta:
            nonlocal assets_pedidos
            linhas = self._query(cid, pmax_dominio.query_asset_group_assets(
                cid, campanha.campaign_id,
            ))
            assets_pedidos = _ids_de_asset(linhas)
            return pmax_dominio.documento_asset_group_assets(linhas=linhas, **comum)

        registrar(pmax_dominio.FAMILIA_ASSET_GROUP_ASSETS, ler_vinculos)

        # 4. os assets pedidos, e SOMENTE eles. Sem a lista, a consulta de
        #    assets leria a conta inteira; e uma leitura larga disfarcada de
        #    resposta seria pior que a falha honesta do prerequisito.
        def ler_assets() -> DocumentoColeta:
            if not assets_pedidos:
                # Sem lista nao ha consulta — nem `None` (o prerequisito caiu)
                # nem `[]` (os vinculos vieram sem asset). Quem separa os dois
                # estados e a projecao, que e onde a distincao tem de valer para
                # qualquer chamador, nao so para este.
                return pmax_dominio.documento_assets(
                    linhas=[], pedidos=assets_pedidos, **comum,
                )
            linhas = self._query(cid, pmax_dominio.query_assets(assets_pedidos))
            return pmax_dominio.documento_assets(
                linhas=linhas, pedidos=assets_pedidos, **comum,
            )

        registrar(pmax_dominio.FAMILIA_ASSETS, ler_assets)

        # 5. desempenho na janela declarada, com a segmentacao por canal como
        #    parte que pode cair sozinha e rebaixar a familia a PARCIAL.
        def ler_desempenho() -> DocumentoColeta:
            linhas = self._query(cid, pmax_dominio.query_desempenho(
                campanha.campaign_id, janela[0], janela[1],
            ))
            por_canal: list[dict[str, Any]] | None = None
            falha_por_canal: dict[str, str] | None = None
            try:
                por_canal = self._query(cid, pmax_dominio.query_desempenho_por_canal(
                    campanha.campaign_id, janela[0], janela[1],
                ))
            except Exception as exc:
                codigo, classe, detalhe, _ = _erro(exc)
                falha_por_canal = {
                    "erro_codigo": codigo, "erro_classe": classe,
                    "erro_detalhe": detalhe,
                }
            return pmax_dominio.documento_desempenho(
                linhas=linhas, grupos_conhecidos=grupos, por_canal=por_canal,
                falha_por_canal=falha_por_canal, **comum,
            )

        registrar(pmax_dominio.FAMILIA_DESEMPENHO, ler_desempenho)

        # 6. sinais dos grupos lidos.
        def ler_sinais() -> DocumentoColeta:
            if not grupos:
                # Mesma regra dos assets: `None` e "a estrutura nao foi lida",
                # `[]` e "foi lida e nao tinha grupo". Nenhum dos dois consulta.
                return pmax_dominio.documento_sinais(
                    linhas=[], grupos_conhecidos=grupos, **comum,
                )
            linhas = self._query(cid, pmax_dominio.query_sinais(cid, grupos))
            return pmax_dominio.documento_sinais(
                linhas=linhas, grupos_conhecidos=grupos, **comum,
            )

        registrar(pmax_dominio.FAMILIA_SINAIS, ler_sinais)

        # 7. a segunda opiniao oficial. Nunca aplicada, nunca dispensada.
        def ler_recomendacoes() -> DocumentoColeta:
            if campanha_lida is False:
                return pmax_dominio.documento_recomendacoes(
                    linhas=[], campanha_observada=False, **comum,
                )
            linhas = self._query(cid, pmax_dominio.query_recomendacoes_forca())
            return pmax_dominio.documento_recomendacoes(
                linhas=linhas, campanha_observada=campanha_lida, **comum,
            )

        registrar(pmax_dominio.FAMILIA_RECOMENDACOES, ler_recomendacoes)

        resultado["total"] = len(resultado["coletas"])
        resultado["lacunas"] = [
            coleta["recusa_de_persistencia"] for coleta in resultado["coletas"]
            if coleta["recusa_de_persistencia"] is not None
        ]
        # ⚠️ Veredito AUTOATESTADO, e nomeado como tal. Ele descreve o que esta
        # execucao acredita ter gravado; promover o bloqueador de prontidao
        # exige o mesmo calculo sobre recibos RELIDOS do ledger.
        resultado["prontidao_desta_execucao"] = pmax_dominio.avaliar_prontidao_pmax(
            resultado, agora=datetime.now(timezone.utc),
            linhagem=pmax_dominio.LINHAGEM_EXECUCAO,
        ).serializar()
        return resultado


def _ids_de_asset_group(linhas: list[dict[str, Any]]) -> list[str]:
    vistos: list[str] = []
    for linha in linhas:
        grupo = linha.get("asset_group", {})
        identificador = str(
            grupo.get("id") or pmax_dominio.id_do_recurso(grupo.get("resource_name")) or ""
        )
        if identificador and identificador not in vistos:
            vistos.append(identificador)
    return vistos


def _ids_de_asset(linhas: list[dict[str, Any]]) -> list[str]:
    vistos: list[str] = []
    for linha in linhas:
        vinculo = linha.get("asset_group_asset", {})
        identificador = pmax_dominio.id_do_recurso(vinculo.get("asset"))
        if identificador and identificador not in vistos:
            vistos.append(identificador)
    return vistos


def _data_de_inicio(linha: dict[str, Any]) -> date | None:
    """``campaign.start_date_time`` (v25) chega como data ou data-hora local."""

    bruto = linha.get("campaign", {}).get("start_date_time")
    if not isinstance(bruto, str) or len(bruto) < 10:
        return None
    try:
        return date.fromisoformat(bruto[:10])
    except ValueError:
        return None


def executar_coleta(*, modo: str = "completa", customer_id: str | None = None) -> dict[str, Any]:
    return ColetorGoogleInteligencia().executar(modo=modo, customer_id=customer_id)


def executar_coleta_alvo(
    *, customer_id: str, volc_campaign_id: str, campaign_id: str,
    modo: str = "completa",
) -> dict[str, Any]:
    alvo = AlvoColeta(
        customer_id=customer_id, volc_campaign_id=volc_campaign_id,
        campaign_id=campaign_id,
    )
    return ColetorGoogleInteligencia().executar_alvo(alvo, modo=modo)


def executar_coleta_pmax(
    *, customer_id: str, volc_campaign_id: str, campaign_id: str,
    modo: str = "completa",
) -> dict[str, Any]:
    """Identidade validada ANTES de qualquer credencial ou conexao."""

    alvo = AlvoColeta(
        customer_id=customer_id, volc_campaign_id=volc_campaign_id,
        campaign_id=campaign_id,
    )
    return ColetorGoogleInteligencia().executar_alvo_pmax(alvo, modo=modo)
