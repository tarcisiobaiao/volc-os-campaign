from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from volc_ads.inteligencia_google.modelo import (
    DocumentoColeta, EstadoColeta, EstadoValor, Metrica,
)
from volc_ads.inteligencia_google.persistencia import (
    ErroPersistenciaGoogle, SupabaseGoogleIntelligence,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/v12_01_google_inteligencia_coletas.sql"


def documento(**trocas):
    base = dict(
        tipo_sinal="EXPERIMENTOS",
        estado=EstadoColeta.VAZIO_CONFIRMADO,
        customer_id="8017851692",
        login_customer_id="6016739364",
        competencia=date(2026, 8, 29),
        coletada_em=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        bucket="daily:2026-08-29",
        quantidade=0,
    )
    base.update(trocas)
    return DocumentoColeta(**base)


def test_zero_medido_nao_e_ausencia():
    metrica = Metrica(
        "campaign", "24156373085", "clicks", EstadoValor.MEDIDO,
        valor_numerico=0,
    ).serializar()
    assert metrica["estado_valor"] == "medido"
    assert metrica["valor_numerico"] == "0"


def test_ausencia_nao_pode_carregar_zero():
    with pytest.raises(ValueError, match="nao medida"):
        Metrica(
            "campaign", "24156373085", "clicks", EstadoValor.AUSENTE,
            valor_numerico=0,
        )


def test_vazio_confirmado_e_falha_tem_quantidades_opostas():
    vazio = documento().serializar()
    falha = documento(
        estado=EstadoColeta.FALHOU, quantidade=None,
        erro_codigo="TIMEOUT", erro_classe="TimeoutError", erro_detalhe="tempo esgotado",
    ).serializar()
    assert vazio["quantidade"] == 0
    assert vazio["erro_codigo"] is None
    assert falha["quantidade"] is None
    assert falha["erro_codigo"] == "TIMEOUT"


def test_falha_nao_pode_se_disfarcar_de_vazio():
    with pytest.raises(ValueError, match="nao pode inventar quantidade"):
        documento(
            estado=EstadoColeta.FALHOU, quantidade=0,
            erro_codigo="X", erro_classe="Erro",
        )


def test_idempotencia_e_por_escopo_tipo_bucket_e_versao():
    a = documento().serializar()["chave_idempotencia"]
    b = documento(
        coletada_em=datetime(2026, 8, 29, 23, tzinfo=timezone.utc),
    ).serializar()["chave_idempotencia"]
    c = documento(bucket="daily:2026-08-30").serializar()["chave_idempotencia"]
    assert a == b
    assert a != c


def test_serializacao_preserva_bucket_para_identidade_da_rodada():
    assert documento(bucket="4h:2026-08-29T20:00Z").serializar()["bucket"] == (
        "4h:2026-08-29T20:00Z"
    )


def test_falha_nao_memoriza_fracasso_e_esconde_retry_bem_sucedido():
    falha = documento(
        estado=EstadoColeta.FALHOU, quantidade=None,
        erro_codigo="TIMEOUT", erro_classe="TimeoutError",
    ).serializar()["chave_idempotencia"]
    sucesso = documento().serializar()["chave_idempotencia"]
    assert falha != sucesso


def test_persistencia_recusa_outro_supabase(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "nao-vazia")
    with pytest.raises(ErroPersistenciaGoogle, match="autoridade recusada"):
        SupabaseGoogleIntelligence("https://projeto-legado.supabase.co")


def test_migration_blinda_rls_append_only_e_semantica():
    sql = MIGRATION.read_text()
    for tabela in (
        "trafego_google_inteligencia_coleta",
        "trafego_google_inteligencia_item",
        "trafego_google_inteligencia_metrica",
    ):
        assert f"ALTER TABLE public.{tabela} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE public.{tabela} FORCE ROW LEVEL SECURITY" in sql
        assert f"REVOKE ALL ON public.{tabela} FROM PUBLIC, anon, authenticated" in sql
    assert "estado = 'vazio_confirmado' AND quantidade = 0" in sql
    assert "estado IN ('inelegivel', 'nao_suportado', 'falhou') AND quantidade IS NULL" in sql
    assert "estado_valor = 'medido'" in sql
    assert "e append-only" in sql


def test_coletor_nao_contem_mutacao_google():
    source = (ROOT / "volc_ads/inteligencia_google/coletor.py").read_text()
    proibidos = (
        ".mutate_", "apply_recommendation", "dismiss_recommendation",
        "FORGE_PERMITIR_ESCRITA=1",
    )
    assert not [token for token in proibidos if token in source.lower()]


# ---------------------------------------------------------------------------
# P09-T14 — caminho one-shot por identidade canonica explicita (campanha PAUSED)
#
# O scan continuo parte de `estado_externo = ENABLED`, entao o canario — que
# nasce PAUSED — some da observabilidade. As provas abaixo cobrem os dois lados:
# o caminho novo alcanca a PAUSED nomeada, e o scan continuo NAO foi ampliado.
# ---------------------------------------------------------------------------

CANARIO = {
    "volc_campaign_id": "a7f1c0de-0000-4000-8000-000000000001",
    "campaign_id": "24156373085",
    "customer_id": "8017851692",
    "nome": "VOLC | Canario | Credito Up",
    "canal": "SEARCH",
    "estado_externo": "PAUSED",
}
LIGADA = {
    "volc_campaign_id": "b2e4c0de-0000-4000-8000-000000000002",
    "campaign_id": "24156373099",
    "customer_id": "8017851692",
    "nome": "VOLC | Search | Credito Up",
    "canal": "SEARCH",
    "estado_externo": "ENABLED",
}
PMAX = {
    "volc_campaign_id": "c3d5c0de-0000-4000-8000-000000000003",
    "campaign_id": "24156373100",
    "customer_id": "8017851692",
    "nome": "VOLC | PMax | Credito Up",
    "canal": "PERFORMANCE_MAX",
    "estado_externo": "PAUSED",
}


def _alvo(linha=CANARIO, **trocas):
    from volc_ads.inteligencia_google.alvo import AlvoColeta

    dados = {
        "customer_id": linha["customer_id"],
        "volc_campaign_id": linha["volc_campaign_id"],
        "campaign_id": linha["campaign_id"],
    }
    dados.update(trocas)
    return AlvoColeta(**dados)


# --- dublê do Google Ads: protos reais, zero rede, zero mutacao --------------


def _row():
    from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

    return GoogleAdsRow()


def linha_campanha(campaign_id, *, nome="canario", inicio=None, orcamento=50_000_000):
    row = _row()
    row.campaign.id = int(campaign_id)
    row.campaign.name = nome
    if inicio is not None:
        row.campaign.start_date_time = inicio
    row.campaign_budget.amount_micros = orcamento
    return row


def linha_desempenho(campaign_id, *, impressoes=0, cliques=0):
    row = _row()
    row.campaign.id = int(campaign_id)
    row.metrics.impressions = impressoes
    row.metrics.clicks = cliques
    return row


def linha_simulacao(campaign_id):
    row = _row()
    row.campaign_simulation.campaign_id = int(campaign_id)
    row.campaign_simulation.resource_name = (
        f"customers/8017851692/campaignSimulations/{campaign_id}~CPC_BID~UNIFORM~1~2"
    )
    return row


def classificar_gaql(gaql: str) -> str:
    """Espelha as consultas reais do coletor, sem adivinhar por substring frouxa."""

    normal = " ".join(gaql.split())
    recurso = normal.split(" FROM ")[1].split(" ")[0].strip()
    if recurso != "campaign":
        if recurso == "keyword_view":
            return (
                "keywords_habilitadas"
                if "ad_group.status = 'ENABLED'" in normal
                else "keywords_diagnostico"
            )
        return recurso
    if "segments.date" in normal:
        return "campanha_desempenho"
    if "campaign.start_date_time" in normal:
        return "campanha_inicio"
    if "campaign.advertising_channel_type" in normal:
        return "campanha_para_recomendacao"
    if "campaign.name" in normal:
        return "campanha_base"
    return "campanha_orcamento"


class RegistroGoogle:
    def __init__(self):
        self.consultas: list[tuple[str, str]] = []
        self.servicos: list[str] = []
        self.tipos: list[str] = []
        self.enums_pedidos: list[str] = []
        self.chamadas_planner: list[int] = []
        self.chamadas_recomendacao: list[str] = []
        self.atributos_desconhecidos: list[str] = []


class _Lote:
    def __init__(self, results):
        self.results = results


class _GoogleAdsServiceDuble:
    def __init__(self, respostas, registro):
        self._respostas = respostas
        self._registro = registro

    def search_stream(self, *, customer_id, query):
        if not query.lstrip().upper().startswith("SELECT"):
            raise AssertionError("o coletor enviou algo que nao e SELECT")
        chave = classificar_gaql(query)
        self._registro.consultas.append((customer_id, chave))
        resposta = self._respostas.get(chave, [])
        if isinstance(resposta, Exception):
            raise resposta
        return [_Lote(list(resposta))]

    def geo_target_constant_path(self, identificador):
        return f"geoTargetConstants/{identificador}"

    def language_constant_path(self, identificador):
        return f"languageConstants/{identificador}"

    def __getattr__(self, nome):
        # Qualquer superficie fora das tres acima — inclusive `mutate` — cai
        # aqui, fica registrada e explode. Silencio nao passa por prova.
        self._registro.atributos_desconhecidos.append(f"GoogleAdsService.{nome}")
        raise AttributeError(nome)


class _PlannerDuble:
    """KeywordPlanIdeaService: um cenario responde, os seguintes falham.

    E assim que PARCIAL nasce no `_forecast` real — parte respondeu, parte nao.
    """

    def __init__(self, registro, sucessos=1, erro=None):
        self._registro = registro
        self._restantes = sucessos
        self._erro = erro or ConnectionError("cenario recusado pelo transporte")

    def generate_keyword_forecast_metrics(self, *, request):
        from google.ads.googleads.v25.services.types.keyword_plan_idea_service import (
            GenerateKeywordForecastMetricsResponse,
        )

        self._registro.chamadas_planner.append(
            request.campaign.bidding_strategy.manual_cpc_bidding_strategy.max_cpc_bid_micros
        )
        if self._restantes <= 0:
            raise self._erro
        self._restantes -= 1
        resposta = GenerateKeywordForecastMetricsResponse()
        resposta.campaign_forecast_metrics.clicks = 12.0
        resposta.campaign_forecast_metrics.cost_micros = 3_400_000
        return resposta

    def __getattr__(self, nome):
        self._registro.atributos_desconhecidos.append(f"KeywordPlanIdeaService.{nome}")
        raise AttributeError(nome)


class _RecommendationServiceDuble:
    def __init__(self, registro, quantidade=1):
        self._registro = registro
        self._quantidade = quantidade

    def generate_recommendations(self, *, request):
        from google.ads.googleads.v25.services.types.recommendation_service import (
            GenerateRecommendationsResponse,
        )

        self._registro.chamadas_recomendacao.append(request.customer_id)
        resposta = GenerateRecommendationsResponse()
        for _ in range(self._quantidade):
            resposta.recommendations.append({"type_": "CAMPAIGN_BUDGET"})
        return resposta

    def __getattr__(self, nome):
        self._registro.atributos_desconhecidos.append(f"RecommendationService.{nome}")
        raise AttributeError(nome)


class ClienteGoogleDuble:
    # Lista branca deliberada: qualquer superficie nova precisa ser adicionada
    # aqui A MAO. E essa friccao — nao o grep de substring — que torna dificil
    # um caminho de escrita entrar sem alguem decidir que ele entra.
    SERVICOS_PREVISTOS = frozenset({
        "GoogleAdsService", "KeywordPlanIdeaService", "RecommendationService",
    })
    TIPOS_PREVISTOS = frozenset({
        "GenerateRecommendationsRequest", "GenerateKeywordForecastMetricsRequest",
    })

    def __init__(self, respostas=None, *, cenarios_com_resposta=1, recomendacoes=1):
        self.respostas = dict(respostas or {})
        self.registro = RegistroGoogle()
        self._cenarios_com_resposta = cenarios_com_resposta
        self._recomendacoes = recomendacoes

    def get_service(self, nome):
        self.registro.servicos.append(nome)
        if nome == "GoogleAdsService":
            return _GoogleAdsServiceDuble(self.respostas, self.registro)
        if nome == "KeywordPlanIdeaService":
            return _PlannerDuble(self.registro, self._cenarios_com_resposta)
        if nome == "RecommendationService":
            return _RecommendationServiceDuble(self.registro, self._recomendacoes)
        raise AssertionError(f"servico fora da lista branca: {nome}")

    def get_type(self, nome):
        self.registro.tipos.append(nome)
        if nome == "GenerateRecommendationsRequest":
            from google.ads.googleads.v25.services.types.recommendation_service import (
                GenerateRecommendationsRequest,
            )

            return GenerateRecommendationsRequest()
        if nome == "GenerateKeywordForecastMetricsRequest":
            from google.ads.googleads.v25.services.types.keyword_plan_idea_service import (
                GenerateKeywordForecastMetricsRequest,
            )

            return GenerateKeywordForecastMetricsRequest()
        raise AssertionError(f"tipo fora da lista branca: {nome}")

    @property
    def enums(self):
        import types as _types

        from google.ads.googleads.v25.enums.types.recommendation_type import (
            RecommendationTypeEnum,
        )

        self.registro.enums_pedidos.append("RecommendationTypeEnum")
        return _types.SimpleNamespace(
            RecommendationTypeEnum=RecommendationTypeEnum.RecommendationType
        )

    def __getattr__(self, nome):
        self.registro.atributos_desconhecidos.append(f"cliente.{nome}")
        raise AttributeError(nome)


# --- dublê de persistencia: honra o filtro do scan continuo ------------------


class PersistenciaDuble:
    """Imita a RPC `volc_registrar_google_inteligencia`, inclusive no que dói.

    A RPC faz `IF existente IS NOT NULL THEN RETURN existente` (v12_01:204-209):
    numa chave repetida ela devolve o id antigo e **nao regrava**. Um duble que
    guardasse o documento descartado deixaria passar teste que afirma conteudo
    que nunca chegou ao banco. Por isso `enviados` (o que o coletor mandou) e
    `documentos` (o que ficou gravado) sao listas diferentes.
    """

    def __init__(self, inventario):
        self.inventario = list(inventario)
        self.enviados = []
        self.documentos = []
        self.por_chave: dict[str, str] = {}
        self.identidades_pedidas = []
        self.campanha_devolvida = None

    def campanhas_search_ativas(self, customer_id=None):
        from volc_ads.inteligencia_google.persistencia import CampanhaAtiva

        return [
            CampanhaAtiva(
                volc_campaign_id=linha["volc_campaign_id"],
                campaign_id=linha["campaign_id"],
                customer_id=linha["customer_id"],
                nome=linha["nome"],
                canal=linha["canal"],
                estado_externo=linha["estado_externo"],
            )
            for linha in self.inventario
            if linha["estado_externo"] == "ENABLED"
            and linha["canal"] == "SEARCH"
            and (customer_id is None or linha["customer_id"] == customer_id)
        ]

    def campanha_por_identidade(self, alvo):
        from volc_ads.inteligencia_google.alvo import (
            ErroAlvoDivergente, conferir_identidade_devolvida,
        )
        from volc_ads.inteligencia_google.persistencia import CampanhaAtiva

        self.identidades_pedidas.append(alvo)
        if self.campanha_devolvida is not None:
            return self.campanha_devolvida
        achadas = [
            linha for linha in self.inventario
            if linha["volc_campaign_id"] == alvo.volc_campaign_id
            and linha["campaign_id"] == alvo.campaign_id
            and linha["customer_id"] == alvo.customer_id
        ]
        if len(achadas) != 1:
            raise ErroAlvoDivergente("alvo nao resolve para exatamente uma campanha")
        linha = achadas[0]
        conferir_identidade_devolvida(alvo, linha)
        return CampanhaAtiva(
            volc_campaign_id=linha["volc_campaign_id"],
            campaign_id=linha["campaign_id"],
            customer_id=linha["customer_id"],
            nome=linha["nome"],
            canal=linha["canal"],
            estado_externo=linha["estado_externo"],
        )

    def registrar(self, documento):
        serializado = documento.serializar()
        chave = serializado["chave_idempotencia"]
        self.enviados.append(serializado)
        if chave in self.por_chave:
            return self.por_chave[chave]  # a RPC devolve o id e NAO regrava
        identificador = f"coleta-{len(self.por_chave) + 1:03d}"
        self.por_chave[chave] = identificador
        self.documentos.append(serializado)
        return identificador

    def recibos(self, tipo_sinal=None):
        return [
            documento for documento in self.documentos
            if tipo_sinal is None or documento["tipo_sinal"] == tipo_sinal
        ]


def coletor(respostas=None, inventario=(CANARIO, LIGADA, PMAX), **opcoes):
    from volc_ads.inteligencia_google.coletor import ColetorGoogleInteligencia

    persistencia = PersistenciaDuble(inventario)
    google = ClienteGoogleDuble(respostas, **opcoes)
    return ColetorGoogleInteligencia(
        persistencia=persistencia, cliente_google=google,
    ), persistencia, google


def linha_keyword(*, ad_group_id=555, texto="credito consignado", lance=1_200_000,
                  primeira_pagina=900_000):
    row = _row()
    row.ad_group.id = ad_group_id
    row.ad_group.type_ = "SEARCH_STANDARD"
    row.ad_group_criterion.keyword.text = texto
    row.ad_group_criterion.keyword.match_type = "PHRASE"
    row.ad_group_criterion.effective_cpc_bid_micros = lance
    row.ad_group_criterion.position_estimates.first_page_cpc_micros = primeira_pagina
    return row


def linha_campanha_para_recomendacao(campaign_id, *, orcamento=50_000_000):
    row = _row()
    row.campaign.id = int(campaign_id)
    row.campaign.advertising_channel_type = "SEARCH"
    row.campaign.bidding_strategy_type = "MANUAL_CPC"
    row.campaign_budget.amount_micros = orcamento
    return row


RESPOSTAS_CANARIO_NOVO = {
    "campanha_base": [linha_campanha(CANARIO["campaign_id"])],
    "campanha_inicio": [
        linha_campanha(CANARIO["campaign_id"], inicio=date.today().isoformat())
    ],
    "campanha_desempenho": [],
    "keywords_diagnostico": [],
    "keywords_habilitadas": [],
    "ad_group_ad": [],
    "campaign_simulation": [],
    "campanha_orcamento": [linha_campanha(CANARIO["campaign_id"])],
    "campanha_para_recomendacao": [],
}


def por_tipo(persistencia):
    return {
        documento["tipo_sinal"]: documento["estado"]
        for documento in persistencia.documentos
    }


# --- 1. o scan continuo nao foi ampliado ------------------------------------


def test_scan_continuo_consulta_apenas_enabled_no_postgrest(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "chave-de-teste")
    supabase = SupabaseGoogleIntelligence("https://database.agenciavolc.com.br")
    pedidos = []

    def _falso_request(path, *, method="GET", body=None):
        pedidos.append((method, path))
        return []

    monkeypatch.setattr(supabase, "_request", _falso_request)
    supabase.campanhas_search_ativas("8017851692")

    assert len(pedidos) == 1
    metodo, path = pedidos[0]
    assert metodo == "GET"
    assert "estado_externo=eq.ENABLED" in path
    assert "canal=eq.SEARCH" in path


def test_scan_continuo_nao_alcanca_campanha_pausada():
    motor, persistencia, google = coletor(RESPOSTAS_CANARIO_NOVO)
    alcancadas = persistencia.campanhas_search_ativas()

    assert [c.campaign_id for c in alcancadas] == [LIGADA["campaign_id"]]
    assert CANARIO["campaign_id"] not in [c.campaign_id for c in alcancadas]
    assert google.registro.consultas == []


def test_coleta_continua_de_enabled_continua_funcionando():
    respostas = {
        "campanha_base": [linha_campanha(LIGADA["campaign_id"], nome="ligada")],
        "campanha_desempenho": [
            linha_desempenho(LIGADA["campaign_id"], impressoes=0, cliques=0)
        ],
        "keywords_diagnostico": [],
        "ad_group_ad": [],
        "campaign_simulation": [linha_simulacao(LIGADA["campaign_id"])],
        "recommendation": [],
        "experiment": [],
    }
    motor, persistencia, _ = coletor(respostas)
    resultado = motor.executar(modo="frequente")

    campanhas_tocadas = {
        documento["campaign_id"] for documento in persistencia.documentos
        if documento["campaign_id"]
    }
    assert campanhas_tocadas == {LIGADA["campaign_id"]}
    assert por_tipo(persistencia)["DIAGNOSTICO_ENTREGA"] == "com_dados"
    assert por_tipo(persistencia)["SIMULACOES_CAMPANHA"] == "com_dados"
    assert por_tipo(persistencia)["RECOMENDACOES_ARMAZENADAS"] == "vazio_confirmado"
    assert resultado["total"] == len(persistencia.documentos)


def test_scan_continuo_nao_ganhou_agenda_nova_no_caminho_do_alvo():
    """O one-shot nao pode disparar as familias de conta nem varrer a carteira."""

    motor, persistencia, _ = coletor(RESPOSTAS_CANARIO_NOVO)
    motor.executar_alvo(_alvo(), modo="frequente")

    tipos = {documento["tipo_sinal"] for documento in persistencia.documentos}
    assert "RECOMENDACOES_ARMAZENADAS" not in tipos
    assert "EXPERIMENTOS" not in tipos
    assert {
        documento["campaign_id"] for documento in persistencia.documentos
    } == {CANARIO["campaign_id"]}


# --- 2. a PAUSED nomeada e coletavel ----------------------------------------


def test_campanha_pausada_explicita_entra_na_coleta():
    respostas = dict(RESPOSTAS_CANARIO_NOVO)
    respostas["campanha_desempenho"] = [
        linha_desempenho(CANARIO["campaign_id"], impressoes=0, cliques=0)
    ]
    motor, persistencia, _ = coletor(respostas)
    resultado = motor.executar_alvo(_alvo(), modo="frequente")

    assert resultado["estado_externo"] == "PAUSED"
    assert resultado["campaign_id"] == CANARIO["campaign_id"]
    assert resultado["volc_campaign_id"] == CANARIO["volc_campaign_id"]
    diagnostico = persistencia.recibos("DIAGNOSTICO_ENTREGA")
    assert len(diagnostico) == 1
    assert diagnostico[0]["estado"] == "com_dados"
    assert diagnostico[0]["campaign_id"] == CANARIO["campaign_id"]
    assert diagnostico[0]["volc_campaign_id"] == CANARIO["volc_campaign_id"]
    assert diagnostico[0]["payload"]["origem"] == "alvo_explicito"


def test_alvo_e_read_only_de_ponta_a_ponta():
    motor, persistencia, google = coletor(RESPOSTAS_CANARIO_NOVO)
    motor.executar_alvo(_alvo(), modo="frequente")

    assert google.registro.servicos == ["GoogleAdsService"]
    assert google.registro.tipos == []
    assert google.registro.atributos_desconhecidos == []
    assert all(
        documento["payload"].get("somente_leitura") is True
        for documento in persistencia.documentos
    )


# --- 3. os seis estados semanticos permanecem distintos ---------------------


def test_ausencia_de_simulacao_em_campanha_nova_e_inelegivel():
    motor, persistencia, _ = coletor(RESPOSTAS_CANARIO_NOVO)
    motor.executar_alvo(_alvo(), modo="frequente")

    simulacao = persistencia.recibos("SIMULACOES_CAMPANHA")[0]
    assert simulacao["estado"] == "inelegivel"
    assert simulacao["quantidade"] is None
    assert "desempenho passado" in simulacao["payload"]["motivo"]


def test_campanha_antiga_sem_simulacao_permanece_vazio_confirmado():
    """Sem prova de que a janela cobre a vida inteira, nao se afirma inelegivel."""

    respostas = dict(RESPOSTAS_CANARIO_NOVO)
    respostas["campanha_inicio"] = [
        linha_campanha(CANARIO["campaign_id"], inicio="2020-01-01")
    ]
    motor, persistencia, _ = coletor(respostas)
    motor.executar_alvo(_alvo(), modo="frequente")

    simulacao = persistencia.recibos("SIMULACOES_CAMPANHA")[0]
    assert simulacao["estado"] == "vazio_confirmado"
    assert simulacao["quantidade"] == 0


def test_sonda_cega_nao_produz_vazio_indistinguivel_de_vazio_observado():
    """A sonda le `campaign`; a familia le `campaign_simulation`.

    São recursos diferentes: a sonda PODE falhar sozinha e a consulta da familia
    terminar bem. Sem o retrato dela no recibo, os dois vazios sairiam byte a
    byte iguais — inclusive `payload_sha256` — e a degradacao de INELEGIVEL para
    VAZIO_CONFIRMADO ficaria invisivel no banco.
    """

    cega = dict(RESPOSTAS_CANARIO_NOVO)
    cega["campanha_inicio"] = RuntimeError("FIELD_NOT_SELECTABLE")
    motor, p_cega, _ = coletor(cega)
    motor.executar_alvo(_alvo(), modo="frequente")
    recibo_cego = p_cega.recibos("SIMULACOES_CAMPANHA")[0]

    antiga = dict(RESPOSTAS_CANARIO_NOVO)
    antiga["campanha_inicio"] = [
        linha_campanha(CANARIO["campaign_id"], inicio="2020-01-01 08:00:00")
    ]
    motor, p_antiga, _ = coletor(antiga)
    motor.executar_alvo(_alvo(), modo="frequente")
    recibo_observado = p_antiga.recibos("SIMULACOES_CAMPANHA")[0]

    # os dois sao vazio_confirmado — e precisam ser distinguiveis mesmo assim
    assert recibo_cego["estado"] == recibo_observado["estado"] == "vazio_confirmado"
    assert recibo_cego["payload_sha256"] != recibo_observado["payload_sha256"]
    assert recibo_cego["payload"]["sonda"]["estado"] == "falhou"
    assert recibo_cego["payload"]["sonda"]["erro_codigo"] == "RuntimeError"
    assert recibo_cego["payload"]["sonda"]["veiculou_na_janela"] is None
    assert recibo_observado["payload"]["sonda"]["estado"] == "medido"
    assert recibo_observado["payload"]["sonda"]["veiculou_na_janela"] is False


def test_inelegivel_carrega_o_retrato_da_sonda_que_o_justificou():
    motor, persistencia, _ = coletor(RESPOSTAS_CANARIO_NOVO)
    motor.executar_alvo(_alvo(), modo="frequente")

    sonda = persistencia.recibos("SIMULACOES_CAMPANHA")[0]["payload"]["sonda"]
    assert sonda["estado"] == "medido"
    assert sonda["veiculou_na_janela"] is False
    assert sonda["inicio_da_campanha"] == date.today().isoformat()
    assert len(sonda["janela"]) == 2


def test_coleta_continua_nao_ganhou_sonda_nem_marca_de_origem():
    """O contínuo tem de sair byte a byte igual ao que saía antes."""

    respostas = {
        "campanha_base": [linha_campanha(LIGADA["campaign_id"], nome="ligada")],
        "campanha_desempenho": [linha_desempenho(LIGADA["campaign_id"], impressoes=3)],
        "keywords_diagnostico": [],
        "ad_group_ad": [],
        "campaign_simulation": [],
        "recommendation": [],
        "experiment": [],
    }
    motor, persistencia, google = coletor(respostas)
    motor.executar(modo="frequente")

    simulacao = persistencia.recibos("SIMULACOES_CAMPANHA")[0]
    assert simulacao["estado"] == "vazio_confirmado"
    assert simulacao["payload"] == {"somente_leitura": True}
    assert all("origem" not in d["payload"] for d in persistencia.documentos)
    assert "campanha_inicio" not in [chave for _, chave in google.registro.consultas]


def test_simulacao_presente_vence_a_heuristica_de_elegibilidade():
    respostas = dict(RESPOSTAS_CANARIO_NOVO)
    respostas["campaign_simulation"] = [linha_simulacao(CANARIO["campaign_id"])]
    motor, persistencia, _ = coletor(respostas)
    motor.executar_alvo(_alvo(), modo="frequente")

    simulacao = persistencia.recibos("SIMULACOES_CAMPANHA")[0]
    assert simulacao["estado"] == "com_dados"
    assert simulacao["quantidade"] == 1


def test_familia_de_plano_de_palavras_fora_de_search_e_nao_suportada():
    respostas = {
        "campanha_base": [linha_campanha(PMAX["campaign_id"], nome="pmax")],
        "campanha_inicio": [
            linha_campanha(PMAX["campaign_id"], inicio=date.today().isoformat())
        ],
        "campanha_desempenho": [],
        "keywords_diagnostico": [],
        "ad_group_ad": [],
        "campaign_simulation": [],
    }
    motor, persistencia, google = coletor(respostas)
    motor.executar_alvo(_alvo(PMAX), modo="completa")

    estados = por_tipo(persistencia)
    assert estados["RECOMENDACOES_GERADAS"] == "nao_suportado"
    assert estados["FORECAST_KEYWORDS"] == "nao_suportado"
    for tipo in ("RECOMENDACOES_GERADAS", "FORECAST_KEYWORDS"):
        recibo = persistencia.recibos(tipo)[0]
        assert recibo["quantidade"] is None
        assert "PERFORMANCE_MAX" in recibo["payload"]["motivo"]
    # NAO_SUPORTADO e conclusao de dominio: nenhuma chamada foi gasta com ela.
    assert "keywords_habilitadas" not in [
        chave for _, chave in google.registro.consultas
    ]


@pytest.mark.parametrize("canal_sem_informacao", ("UNKNOWN", "UNSPECIFIED"))
def test_canal_desconhecido_nao_vira_nao_suportado(canal_sem_informacao):
    """`UNKNOWN`/`UNSPECIFIED` sao "a conta nao disse", nao "nao e SEARCH".

    Concluir NAO_SUPORTADO a partir deles gravaria quantidade nula, sem erro,
    sobre uma campanha que pode ser SEARCH — e ninguem reprocessaria. O
    vocabulario nao tem "nao sei", entao o alvo inteiro falha fechado.
    """

    from volc_ads.inteligencia_google.alvo import ErroAlvoDivergente

    cego = dict(CANARIO, canal=canal_sem_informacao)
    motor, persistencia, google = coletor(RESPOSTAS_CANARIO_NOVO, inventario=(cego,))
    with pytest.raises(ErroAlvoDivergente, match=canal_sem_informacao):
        motor.executar_alvo(_alvo(), modo="completa")

    assert persistencia.documentos == []
    assert google.registro.consultas == []


def test_search_sem_keywords_habilitadas_e_inelegivel_nao_nao_suportado():
    motor, persistencia, _ = coletor(RESPOSTAS_CANARIO_NOVO)
    motor.executar_alvo(_alvo(), modo="completa")

    estados = por_tipo(persistencia)
    assert estados["RECOMENDACOES_GERADAS"] == "inelegivel"
    assert estados["FORECAST_KEYWORDS"] == "inelegivel"


def test_erro_de_rede_vira_falhou_e_nunca_vazio():
    respostas = dict(RESPOSTAS_CANARIO_NOVO)
    respostas["campanha_base"] = ConnectionError("conexao recusada pelo transporte")
    respostas["campanha_inicio"] = ConnectionError("conexao recusada pelo transporte")
    respostas["campaign_simulation"] = ConnectionError("conexao recusada")
    motor, persistencia, _ = coletor(respostas)
    motor.executar_alvo(_alvo(), modo="frequente")

    for tipo in ("DIAGNOSTICO_ENTREGA", "SIMULACOES_CAMPANHA"):
        recibo = persistencia.recibos(tipo)[0]
        assert recibo["estado"] == "falhou"
        assert recibo["quantidade"] is None
        assert recibo["erro_codigo"] == "ConnectionError"
        assert recibo["erro_classe"] == "ConnectionError"


def test_falha_de_uma_familia_nao_contamina_a_outra():
    respostas = dict(RESPOSTAS_CANARIO_NOVO)
    respostas["campaign_simulation"] = ConnectionError("so a simulacao caiu")
    respostas["campanha_desempenho"] = [
        linha_desempenho(CANARIO["campaign_id"], impressoes=0)
    ]
    motor, persistencia, _ = coletor(respostas)
    motor.executar_alvo(_alvo(), modo="frequente")

    estados = por_tipo(persistencia)
    assert estados["DIAGNOSTICO_ENTREGA"] == "com_dados"
    assert estados["SIMULACOES_CAMPANHA"] == "falhou"


RESPOSTAS_CANARIO_COM_KEYWORDS = dict(
    RESPOSTAS_CANARIO_NOVO,
    keywords_habilitadas=[
        linha_keyword(texto="credito consignado"),
        linha_keyword(texto="emprestimo consignado", lance=1_800_000,
                      primeira_pagina=1_500_000),
    ],
    campanha_para_recomendacao=[
        linha_campanha_para_recomendacao(CANARIO["campaign_id"])
    ],
)


def test_forecast_com_cenario_recusado_e_parcial_de_verdade():
    """PARCIAL nasce no `_forecast` real: parte respondeu, parte nao."""

    motor, persistencia, google = coletor(
        RESPOSTAS_CANARIO_COM_KEYWORDS, cenarios_com_resposta=1,
    )
    motor.executar_alvo(_alvo(), modo="completa")

    forecast = persistencia.recibos("FORECAST_KEYWORDS")[0]
    assert forecast["estado"] == "parcial"
    assert forecast["quantidade"] == 1
    assert forecast["payload"]["cenarios_tentados"] > 1
    assert forecast["payload"]["falhas"]
    assert forecast["erro_codigo"] is None  # parcial nao e falha
    assert len(google.registro.chamadas_planner) == forecast["payload"]["cenarios_tentados"]


def test_forecast_sem_nenhum_cenario_respondendo_e_falhou():
    motor, persistencia, _ = coletor(
        RESPOSTAS_CANARIO_COM_KEYWORDS, cenarios_com_resposta=0,
    )
    motor.executar_alvo(_alvo(), modo="completa")

    forecast = persistencia.recibos("FORECAST_KEYWORDS")[0]
    assert forecast["estado"] == "falhou"
    assert forecast["quantidade"] is None
    assert forecast["erro_codigo"] == "ConnectionError"


def test_recomendacoes_geradas_reais_produzem_com_dados():
    motor, persistencia, google = coletor(
        RESPOSTAS_CANARIO_COM_KEYWORDS, recomendacoes=2,
    )
    motor.executar_alvo(_alvo(), modo="completa")

    recibo = persistencia.recibos("RECOMENDACOES_GERADAS")[0]
    assert recibo["estado"] == "com_dados"
    assert recibo["quantidade"] == 2
    assert google.registro.chamadas_recomendacao == [CANARIO["customer_id"]]


def test_modo_completa_e_read_only_com_lista_branca_de_superficie():
    """A prova de zero mutacao precisa cobrir o modo DEFAULT do CLI.

    Em `frequente` as duas familias que falam com outros servicos nem rodam;
    era possivel declarar "read-only de ponta a ponta" sem nunca ter tocado
    RecommendationService nem KeywordPlanIdeaService.
    """

    motor, persistencia, google = coletor(RESPOSTAS_CANARIO_COM_KEYWORDS)
    motor.executar_alvo(_alvo(), modo="completa")

    assert set(google.registro.servicos) == {
        "GoogleAdsService", "RecommendationService", "KeywordPlanIdeaService",
    }
    assert set(google.registro.servicos) <= ClienteGoogleDuble.SERVICOS_PREVISTOS
    assert set(google.registro.tipos) == {
        "GenerateRecommendationsRequest", "GenerateKeywordForecastMetricsRequest",
    }
    assert set(google.registro.tipos) <= ClienteGoogleDuble.TIPOS_PREVISTOS
    assert google.registro.atributos_desconhecidos == []
    assert all(
        documento["payload"].get("somente_leitura") is True
        for documento in persistencia.documentos
    )


def test_seis_estados_semanticos_permanecem_distintos():
    vistos = set()

    respostas_com_dados = dict(RESPOSTAS_CANARIO_NOVO)
    respostas_com_dados["campanha_desempenho"] = [
        linha_desempenho(CANARIO["campaign_id"], impressoes=0)
    ]
    respostas_com_dados["campaign_simulation"] = [
        linha_simulacao(CANARIO["campaign_id"])
    ]
    motor, persistencia, _ = coletor(respostas_com_dados)
    motor.executar_alvo(_alvo(), modo="completa")
    vistos.update(por_tipo(persistencia).values())

    motor, persistencia, _ = coletor(RESPOSTAS_CANARIO_NOVO)
    motor.executar_alvo(_alvo(), modo="completa")
    vistos.update(por_tipo(persistencia).values())

    respostas_pmax = {
        "campanha_base": [linha_campanha(PMAX["campaign_id"])],
        "campanha_inicio": [linha_campanha(PMAX["campaign_id"], inicio="2020-01-01")],
        "campanha_desempenho": [],
        "keywords_diagnostico": [],
        "ad_group_ad": [],
        "campaign_simulation": [],
    }
    motor, persistencia, _ = coletor(respostas_pmax)
    motor.executar_alvo(_alvo(PMAX), modo="completa")
    vistos.update(por_tipo(persistencia).values())

    respostas_falha = dict(RESPOSTAS_CANARIO_NOVO)
    respostas_falha["campanha_base"] = ConnectionError("caiu")
    motor, persistencia, _ = coletor(respostas_falha)
    motor.executar_alvo(_alvo(), modo="frequente")
    vistos.update(por_tipo(persistencia).values())

    # PARCIAL vem do `_forecast` REAL, com um cenario respondendo e o resto nao.
    # Montar o documento a mao aqui seria `vistos.add("parcial")` disfarcado.
    motor, persistencia, _ = coletor(
        RESPOSTAS_CANARIO_COM_KEYWORDS, cenarios_com_resposta=1,
    )
    motor.executar_alvo(_alvo(), modo="completa")
    estados_parciais = por_tipo(persistencia)
    assert estados_parciais["FORECAST_KEYWORDS"] == "parcial"
    vistos.update(estados_parciais.values())

    assert vistos >= {
        "com_dados", "vazio_confirmado", "parcial", "inelegivel",
        "nao_suportado", "falhou",
    }


def test_zero_medido_atravessa_o_coletor_como_zero():
    respostas = dict(RESPOSTAS_CANARIO_NOVO)
    respostas["campanha_desempenho"] = [
        linha_desempenho(CANARIO["campaign_id"], impressoes=0, cliques=0)
    ]
    motor, persistencia, _ = coletor(respostas)
    motor.executar_alvo(_alvo(), modo="frequente")

    metricas = {
        metrica["nome"]: metrica
        for metrica in persistencia.recibos("DIAGNOSTICO_ENTREGA")[0]["metricas"]
    }
    assert metricas["impressions"]["estado_valor"] == "medido"
    assert metricas["impressions"]["valor_numerico"] == "0"
    # E o que nao foi medido continua ausente, sem virar zero.
    assert metricas["search_impression_share"]["estado_valor"] == "ausente"
    assert metricas["search_impression_share"]["valor_numerico"] is None


# --- 4. identidade e conta: fail-closed -------------------------------------


def test_identidade_malformada_e_recusada_na_construcao():
    from volc_ads.inteligencia_google.alvo import ErroAlvoInvalido

    with pytest.raises(ErroAlvoInvalido):
        _alvo(campaign_id="nao-e-numero")
    with pytest.raises(ErroAlvoInvalido):
        _alvo(customer_id="123")
    with pytest.raises(ErroAlvoInvalido):
        _alvo(volc_campaign_id="")


def test_alvo_exige_conta_identidade_interna_e_id_externo():
    from volc_ads.inteligencia_google.alvo import AlvoColeta

    with pytest.raises(TypeError):
        AlvoColeta(customer_id="8017851692", campaign_id="24156373085")


def test_campanha_inexistente_falha_fechado_sem_tocar_o_google():
    from volc_ads.inteligencia_google.alvo import ErroAlvoDivergente

    motor, persistencia, google = coletor(RESPOSTAS_CANARIO_NOVO)
    with pytest.raises(ErroAlvoDivergente):
        motor.executar_alvo(_alvo(campaign_id="99999999999"), modo="frequente")

    assert persistencia.documentos == []
    assert google.registro.consultas == []


def test_conta_divergente_e_recusada_mesmo_se_a_persistencia_mentir():
    from volc_ads.inteligencia_google.alvo import ErroAlvoDivergente
    from volc_ads.inteligencia_google.persistencia import CampanhaAtiva

    motor, persistencia, google = coletor(RESPOSTAS_CANARIO_NOVO)
    persistencia.campanha_devolvida = CampanhaAtiva(
        volc_campaign_id=CANARIO["volc_campaign_id"],
        campaign_id=CANARIO["campaign_id"],
        customer_id="9999999999",
        nome=CANARIO["nome"],
        canal="SEARCH",
        estado_externo="PAUSED",
    )
    with pytest.raises(ErroAlvoDivergente, match="customer_id divergente"):
        motor.executar_alvo(_alvo(), modo="frequente")

    assert persistencia.documentos == []
    assert google.registro.consultas == []


def test_id_externo_trocado_dentro_da_mesma_conta_e_recusado():
    from volc_ads.inteligencia_google.alvo import ErroAlvoDivergente
    from volc_ads.inteligencia_google.persistencia import CampanhaAtiva

    motor, persistencia, google = coletor(RESPOSTAS_CANARIO_NOVO)
    persistencia.campanha_devolvida = CampanhaAtiva(
        volc_campaign_id=CANARIO["volc_campaign_id"],
        campaign_id=LIGADA["campaign_id"],
        customer_id=CANARIO["customer_id"],
        nome=CANARIO["nome"],
        canal="SEARCH",
        estado_externo="PAUSED",
    )
    with pytest.raises(ErroAlvoDivergente, match="campaign_id divergente"):
        motor.executar_alvo(_alvo(), modo="frequente")

    assert persistencia.documentos == []
    assert google.registro.consultas == []


def test_persistencia_filtra_pelos_tres_identificadores(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "chave-de-teste")
    supabase = SupabaseGoogleIntelligence("https://database.agenciavolc.com.br")
    pedidos = []

    def _falso_request(path, *, method="GET", body=None):
        pedidos.append(path)
        return [dict(CANARIO)]

    monkeypatch.setattr(supabase, "_request", _falso_request)
    campanha = supabase.campanha_por_identidade(_alvo())

    assert campanha.campaign_id == CANARIO["campaign_id"]
    assert campanha.estado_externo == "PAUSED"
    path = pedidos[0]
    assert f"volc_campaign_id=eq.{CANARIO['volc_campaign_id']}" in path
    assert f"campaign_id=eq.{CANARIO['campaign_id']}" in path
    assert f"customer_id=eq.{CANARIO['customer_id']}" in path
    # o caminho do alvo nao pode herdar o filtro do scan continuo
    assert "estado_externo=eq.ENABLED" not in path


def test_persistencia_recusa_alvo_ambiguo_ou_ausente(monkeypatch):
    from volc_ads.inteligencia_google.alvo import ErroAlvoDivergente

    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "chave-de-teste")
    supabase = SupabaseGoogleIntelligence("https://database.agenciavolc.com.br")

    monkeypatch.setattr(supabase, "_request", lambda *a, **k: [])
    with pytest.raises(ErroAlvoDivergente, match="nenhuma campanha"):
        supabase.campanha_por_identidade(_alvo())

    monkeypatch.setattr(
        supabase, "_request", lambda *a, **k: [dict(CANARIO), dict(CANARIO)]
    )
    with pytest.raises(ErroAlvoDivergente, match="mais de uma"):
        supabase.campanha_por_identidade(_alvo())


def test_persistencia_recusa_linha_que_nao_bate_com_o_pedido(monkeypatch):
    from volc_ads.inteligencia_google.alvo import ErroAlvoDivergente

    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "chave-de-teste")
    supabase = SupabaseGoogleIntelligence("https://database.agenciavolc.com.br")
    intruso = dict(CANARIO, customer_id="9999999999")
    monkeypatch.setattr(supabase, "_request", lambda *a, **k: [intruso])

    with pytest.raises(ErroAlvoDivergente, match="customer_id divergente"):
        supabase.campanha_por_identidade(_alvo())


# --- 5. idempotencia ---------------------------------------------------------


def test_retry_do_alvo_e_idempotente():
    respostas = dict(RESPOSTAS_CANARIO_NOVO)
    respostas["campanha_desempenho"] = [
        linha_desempenho(CANARIO["campaign_id"], impressoes=0)
    ]
    motor, persistencia, _ = coletor(respostas)

    primeira = motor.executar_alvo(_alvo(), modo="frequente")
    chaves_primeira = [d["chave_idempotencia"] for d in persistencia.enviados]
    segunda = motor.executar_alvo(_alvo(), modo="frequente")
    chaves_segunda = [
        d["chave_idempotencia"] for d in persistencia.enviados[len(chaves_primeira):]
    ]

    assert chaves_primeira == chaves_segunda
    assert [c["coleta_id"] for c in primeira["coletas"]] == [
        c["coleta_id"] for c in segunda["coletas"]
    ]
    # o retry mandou tudo de novo e o banco guardou uma vez so
    assert len(persistencia.enviados) == 2 * len(chaves_primeira)
    assert len(persistencia.documentos) == len(chaves_primeira)


def test_leitura_nova_no_mesmo_bucket_e_descartada_e_isso_esta_provado():
    """O custo declarado da idempotencia por bucket, medido em vez de prometido.

    Se a campanha MUDAR entre duas execucoes do mesmo bucket, a segunda leitura
    e deduplicada e o recibo antigo prevalece — a RPC devolve o id existente sem
    regravar. E o comportamento pedido (nao duplicar observacao), mas quem
    precisa da leitura nova precisa de outro bucket, nao de outra chamada.
    """

    respostas = dict(RESPOSTAS_CANARIO_NOVO)
    respostas["campanha_desempenho"] = [
        linha_desempenho(CANARIO["campaign_id"], impressoes=0)
    ]
    motor, persistencia, google = coletor(respostas)
    motor.executar_alvo(_alvo(), modo="frequente")
    gravado = persistencia.recibos("DIAGNOSTICO_ENTREGA")[0]
    assert gravado["payload"]["keywords"] == 0

    # operador sobe keywords no canario; nova leitura, mesmo bucket
    google.respostas["keywords_diagnostico"] = [linha_keyword(), linha_keyword()]
    motor.executar_alvo(_alvo(), modo="frequente")

    enviados = [d for d in persistencia.enviados if d["tipo_sinal"] == "DIAGNOSTICO_ENTREGA"]
    assert enviados[1]["payload"]["keywords"] == 2       # o coletor LEU o novo
    assert len(persistencia.recibos("DIAGNOSTICO_ENTREGA")) == 1
    assert persistencia.recibos("DIAGNOSTICO_ENTREGA")[0]["payload"]["keywords"] == 0
    assert enviados[0]["chave_idempotencia"] == enviados[1]["chave_idempotencia"]


def test_falha_e_sucesso_do_mesmo_alvo_nao_se_apagam():
    respostas_falha = dict(RESPOSTAS_CANARIO_NOVO)
    respostas_falha["campanha_base"] = ConnectionError("caiu")
    motor, persistencia, google = coletor(respostas_falha)
    motor.executar_alvo(_alvo(), modo="frequente")

    google.respostas["campanha_base"] = [linha_campanha(CANARIO["campaign_id"])]
    google.respostas["campanha_desempenho"] = [
        linha_desempenho(CANARIO["campaign_id"], impressoes=0)
    ]
    motor.executar_alvo(_alvo(), modo="frequente")

    diagnosticos = persistencia.recibos("DIAGNOSTICO_ENTREGA")
    assert [d["estado"] for d in diagnosticos] == ["falhou", "com_dados"]
    assert len({d["chave_idempotencia"] for d in diagnosticos}) == 2


# --- 6. zero mutacao e zero agenda concorrente ------------------------------


def test_pacote_de_inteligencia_nao_contem_mutacao_google():
    proibidos = (
        ".mutate_", "apply_recommendation", "dismiss_recommendation",
        "forge_permitir_escrita=1", "mutate_operation",
    )
    for arquivo in sorted((ROOT / "volc_ads/inteligencia_google").glob("*.py")):
        source = arquivo.read_text().lower()
        achados = [token for token in proibidos if token in source]
        assert not achados, f"{arquivo.name}: {achados}"
    cli = (ROOT / "scripts/coletar_google_inteligencia.py").read_text().lower()
    assert not [token for token in proibidos if token in cli]


def test_caminho_do_alvo_nao_cria_segundo_scheduler():
    """Uma execucao, um alvo — verificado na ARVORE, nao no texto.

    Grep de substring reprovaria um comentario que explica por que nao ha
    scheduler, e aprovaria `getattr(time, "sl" + "eep")()`. O que decide e a
    estrutura: import de modulo de agendamento, chamada de espera, ou laco
    infinito. Comentario nenhum produz isso.
    """

    import ast

    MODULOS = {
        "threading", "sched", "schedule", "apscheduler", "croniter", "crontab",
        "signal", "asyncio", "time", "multiprocessing", "subprocess",
    }
    CHAMADAS = {"sleep", "every", "enter", "enterabs", "alarm", "set_wakeup_fd"}

    for caminho in (
        "volc_ads/inteligencia_google/alvo.py",
        "volc_ads/inteligencia_google/coletor.py",
        "volc_ads/inteligencia_google/persistencia.py",
        "volc_ads/inteligencia_google/modelo.py",
        "scripts/coletar_google_inteligencia.py",
    ):
        arvore = ast.parse((ROOT / caminho).read_text())
        importados, chamadas, lacos = set(), set(), 0
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados.update(a.name.split(".")[0] for a in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                importados.add(no.module.split(".")[0])
            elif isinstance(no, ast.Call):
                alvo_chamado = no.func
                nome = getattr(alvo_chamado, "attr", None) or getattr(
                    alvo_chamado, "id", None
                )
                if nome in CHAMADAS:
                    chamadas.add(nome)
                # `getattr` com nome COMPUTADO burlaria qualquer varredura de
                # texto. Só é proibido em `coletor.py`, o único módulo que
                # segura o cliente Google; nos outros não há o que alcançar.
                if (
                    nome == "getattr"
                    and caminho.endswith("coletor.py")
                    and len(no.args) > 1
                    and not isinstance(no.args[1], ast.Constant)
                ):
                    chamadas.add("getattr-com-nome-computado")
            elif isinstance(no, ast.While):
                if not (isinstance(no.test, ast.Constant) and no.test.value is False):
                    lacos += 1

        assert not (importados & MODULOS), f"{caminho}: importa {importados & MODULOS}"
        assert not chamadas, f"{caminho}: chama {chamadas}"
        assert lacos == 0, f"{caminho}: {lacos} laco(s) while"

    # E o CLI nao ganhou nenhuma opcao de repeticao/intervalo.
    cli = (ROOT / "scripts/coletar_google_inteligencia.py").read_text()
    for bandeira in ("--intervalo", "--repetir", "--loop", "--daemon", "--watch"):
        assert bandeira not in cli


def test_dominio_do_alvo_nao_alcanca_a_superficie_google():
    """`alvo.py` é domínio puro: sem cliente Google, não há o que mutar nele."""

    import ast

    arvore = ast.parse((ROOT / "volc_ads/inteligencia_google/alvo.py").read_text())
    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module)
    assert not [m for m in importados if m.startswith(("google", "volc_ads.gads"))]
    assert not [m for m in importados if m in {"urllib", "urllib.request", "http"}]


def test_cli_exige_a_identidade_completa_para_o_alvo():
    import subprocess
    import sys

    def executar(*argumentos):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/coletar_google_inteligencia.py"),
             *argumentos],
            capture_output=True, text=True, cwd=str(ROOT),
        )

    parcial = executar("--campaign-id", "24156373085")
    assert parcial.returncode != 0
    assert "identidade" in (parcial.stderr + parcial.stdout).lower()

    ajuda = executar("--help")
    assert ajuda.returncode == 0
    assert "--volc-campaign-id" in ajuda.stdout
    assert "--campaign-id" in ajuda.stdout


def test_identidade_e_validada_antes_de_qualquer_credencial_ou_rede(monkeypatch):
    """A ordem importa: identidade ruim explode antes de abrir conexao alguma."""

    from volc_ads.inteligencia_google import executar_coleta_alvo
    from volc_ads.inteligencia_google.alvo import ErroAlvoInvalido

    monkeypatch.delenv("VITE_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    # Sem env de Supabase, chegar na persistencia levantaria
    # ErroPersistenciaGoogle. Ver ErroAlvoInvalido prova que nem chegou la.
    with pytest.raises(ErroAlvoInvalido):
        executar_coleta_alvo(
            customer_id=CANARIO["customer_id"],
            volc_campaign_id=CANARIO["volc_campaign_id"],
            campaign_id="nao-e-numero",
            modo="frequente",
        )


# --- 7. o dominio do alvo nao pode divergir da projecao de saude -------------


INVENTARIO_SQL = ROOT / "supabase/migrations/v9_01_trafego_inventario.sql"


def test_identidade_interna_obedece_o_contrato_do_banco_e_preserva_caixa():
    """A regra certa e a do banco, nao a de outro modulo Python.

    `volc_campaign_id` e PK textual case-sensitive; rebaixar a caixa aqui
    produziria um filtro PostgREST que nao casa com a linha e devolveria
    "nenhuma campanha no inventario" para uma campanha que existe. Um teste que
    so compara duas implementacoes Python nao pega isso: as duas podem estar
    erradas juntas.
    """

    import re as _re

    sql = INVENTARIO_SQL.read_text()
    achado = _re.search(r"CHECK \(volc_campaign_id ~ '(\^[^']+\$)'\)", sql)
    assert achado, "o CHECK de volc_campaign_id sumiu da migration"
    contrato = _re.compile(achado.group(1))

    from volc_ads.inteligencia_google.alvo import (
        ErroAlvoInvalido, normalizar_id_interno,
    )

    aceitos = (
        CANARIO["volc_campaign_id"],
        CANARIO["volc_campaign_id"].upper(),
        "A7F1C0DE-0000-4000-8000-000000000001",
        "volc.campanha_1:2",
        "Z9",
    )
    for valor in aceitos:
        assert contrato.fullmatch(valor), f"amostra fora do contrato do banco: {valor}"
        # preserva a caixa: identico ao que o banco guardaria
        assert normalizar_id_interno(valor) == valor

    for valor in ("", "-comeca-com-hifen", "com espaco", "acentuação", "a" * 121):
        assert not contrato.fullmatch(valor)
        with pytest.raises(ErroAlvoInvalido):
            normalizar_id_interno(valor)


def test_identidade_em_caixa_alta_encontra_a_campanha(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "chave-de-teste")
    supabase = SupabaseGoogleIntelligence("https://database.agenciavolc.com.br")
    maiuscula = CANARIO["volc_campaign_id"].upper()
    linha = dict(CANARIO, volc_campaign_id=maiuscula)
    pedidos = []

    def _falso_request(path, *, method="GET", body=None):
        pedidos.append(path)
        return [linha]

    monkeypatch.setattr(supabase, "_request", _falso_request)
    campanha = supabase.campanha_por_identidade(_alvo(volc_campaign_id=maiuscula))

    assert f"volc_campaign_id=eq.{maiuscula}" in pedidos[0]
    assert campanha.volc_campaign_id == maiuscula


def test_conta_e_id_externo_continuam_alinhados_com_a_saude():
    """Conta e ID externo NAO tem divergencia de caixa; aqui a paridade vale."""

    from volc_ads.inteligencia_google import alvo as dominio
    from volc_ads.inteligencia_google import saude

    for valor in ("8017851692", "801-785-1692", " 6016739364 "):
        assert dominio.normalizar_conta(valor) == saude._normalizar_google_id(
            valor, "customer_id"
        )
    for valor in ("24156373085", " 24156373085 "):
        assert dominio.normalizar_id_externo(valor) == saude._normalizar_campaign_id(
            valor, "campaign_id"
        )


# --- 12. o estado da conta viaja com o diagnostico --------------------------
#
# ⚠️ Medido em 03/09/2026, contra `34dc7b4`: NENHUMA consulta do VOLC-OS lia
# `customer.status`. `backend/app/trafego/contas.py` descobre contas com
# `WHERE customer_client.status = 'ENABLED'` — uma conta suspensa desaparece da
# lista sem linha e sem explicacao — e `GAQL_CONTA` nem seleciona o campo. Foi
# assim que o incidente Credito Up (conta suspensa por politica, campanhas Search
# sem gasto) chegou ao operador como `conta: nao_apurado`.


def linha_conta(customer_id, *, status="ENABLED", nome="conta de prova"):
    row = _row()
    row.customer.id = int(customer_id)
    row.customer.status = status
    row.customer.descriptive_name = nome
    row.customer.currency_code = "BRL"
    return row


def linha_meta(*, categoria="PURCHASE", origem="WEBSITE", biddable=True):
    row = _row()
    row.customer_conversion_goal.category = categoria
    row.customer_conversion_goal.origin = origem
    row.customer_conversion_goal.biddable = biddable
    return row


RESPOSTAS_COM_CONTA = {
    "campanha_base": [linha_campanha(LIGADA["campaign_id"], nome="ligada")],
    "campanha_desempenho": [
        linha_desempenho(LIGADA["campaign_id"], impressoes=0, cliques=0)
    ],
    "keywords_diagnostico": [linha_keyword()],
    "ad_group_ad": [],
    "campaign_simulation": [],
    "recommendation": [],
    "experiment": [],
    "customer": [linha_conta(LIGADA["customer_id"], status="SUSPENDED")],
    "customer_conversion_goal": [linha_meta()],
}


def _diagnostico_de(persistencia):
    return [
        d for d in persistencia.documentos
        if d["tipo_sinal"] == "DIAGNOSTICO_ENTREGA"
    ][0]


def test_o_coletor_pergunta_o_estado_da_conta():
    """A consulta existe, e e SELECT."""
    _motor, _persistencia, google = coletor(RESPOSTAS_COM_CONTA)
    _motor.executar(modo="frequente")

    chaves = [chave for _cid, chave in google.registro.consultas]
    assert "customer" in chaves, (
        "o coletor nao pergunta o estado da conta; foi assim que a suspensao "
        "do Credito Up ficou invisivel"
    )
    assert "customer_conversion_goal" in chaves


def test_conta_suspensa_chega_ao_ledger_como_item_de_conta():
    _motor, persistencia, _google = coletor(RESPOSTAS_COM_CONTA)
    _motor.executar(modo="frequente")

    documento = _diagnostico_de(persistencia)
    contas = [i for i in documento["itens"] if i["tipo_item"] == "account"]
    assert len(contas) == 1
    assert contas[0]["payload"]["customer"]["status"] == "SUSPENDED"
    # ⚠️ E o item da conta e o PRIMEIRO: `ordinal` e a ordem de leitura, e o
    # consumidor le a conta antes de concluir sobre a campanha.
    assert contas[0]["ordinal"] == 0
    assert documento["payload"]["conta_retornou"] is True


def test_metas_de_conversao_chegam_ao_ledger():
    _motor, persistencia, _google = coletor(RESPOSTAS_COM_CONTA)
    _motor.executar(modo="frequente")

    documento = _diagnostico_de(persistencia)
    metas = [i for i in documento["itens"] if i["tipo_item"] == "conversion_goal"]
    assert len(metas) == 1
    assert metas[0]["payload"]["customer_conversion_goal"]["category"] == "PURCHASE"
    assert documento["payload"]["metas_retornaram"] is True
    assert documento["payload"]["metas"] == 1


def test_conta_que_nao_respondeu_e_declarada_e_nao_deduzida():
    """Zero itens de conta pode ser "nao havia" ou "nao perguntei". O payload diz."""
    respostas = dict(RESPOSTAS_COM_CONTA, customer=[], customer_conversion_goal=[])
    _motor, persistencia, _google = coletor(respostas)
    _motor.executar(modo="frequente")

    documento = _diagnostico_de(persistencia)
    assert [i for i in documento["itens"] if i["tipo_item"] == "account"] == []
    assert documento["payload"]["conta_retornou"] is False
    assert documento["payload"]["metas_retornaram"] is False


def test_a_consulta_de_conta_nao_precisa_de_migration():
    """`tipo_item` e um CHECK ABERTO na v12_01; `tipo_sinal` e fechado.

    Esta prova amarra a decisao de arquitetura ao arquivo que a sustenta: o
    estado da conta viaja dentro de `DIAGNOSTICO_ENTREGA`, que ja e um dos doze
    `tipo_sinal` aceitos, como um `tipo_item` novo — que a migration permite sem
    alteracao nenhuma.
    """
    from pathlib import Path

    sql = Path("supabase/migrations/v12_01_google_inteligencia_coletas.sql").read_text(
        encoding="utf-8"
    )
    assert "CONSTRAINT trafego_google_item_tipo CHECK (btrim(tipo_item) <> '')" in sql
    assert "'DIAGNOSTICO_ENTREGA'" in sql
