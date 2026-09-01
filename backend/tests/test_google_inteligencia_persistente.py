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


class ClienteGoogleDuble:
    def __init__(self, respostas=None):
        self.respostas = dict(respostas or {})
        self.registro = RegistroGoogle()

    def get_service(self, nome):
        self.registro.servicos.append(nome)
        if nome == "GoogleAdsService":
            return _GoogleAdsServiceDuble(self.respostas, self.registro)
        raise AssertionError(f"servico nao previsto nesta prova: {nome}")

    def get_type(self, nome):
        self.registro.tipos.append(nome)
        raise AssertionError(f"tipo nao previsto nesta prova: {nome}")

    def __getattr__(self, nome):
        self.registro.atributos_desconhecidos.append(f"cliente.{nome}")
        raise AttributeError(nome)


# --- dublê de persistencia: honra o filtro do scan continuo ------------------


class PersistenciaDuble:
    def __init__(self, inventario):
        self.inventario = list(inventario)
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
        self.documentos.append(serializado)
        if chave in self.por_chave:
            return self.por_chave[chave]
        identificador = f"coleta-{len(self.por_chave) + 1:03d}"
        self.por_chave[chave] = identificador
        return identificador

    def recibos(self, tipo_sinal=None):
        return [
            documento for documento in self.documentos
            if tipo_sinal is None or documento["tipo_sinal"] == tipo_sinal
        ]


def coletor(respostas=None, inventario=(CANARIO, LIGADA, PMAX)):
    from volc_ads.inteligencia_google.coletor import ColetorGoogleInteligencia

    persistencia = PersistenciaDuble(inventario)
    google = ClienteGoogleDuble(respostas)
    return ColetorGoogleInteligencia(
        persistencia=persistencia, cliente_google=google,
    ), persistencia, google


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

    respostas_parcial = dict(RESPOSTAS_CANARIO_NOVO)
    parcial = documento(
        estado=EstadoColeta.PARCIAL, quantidade=1, tipo_sinal="FORECAST_KEYWORDS",
    ).serializar()
    vistos.add(parcial["estado"])

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
    chaves_primeira = [d["chave_idempotencia"] for d in persistencia.documentos]
    segunda = motor.executar_alvo(_alvo(), modo="frequente")
    chaves_segunda = [
        d["chave_idempotencia"] for d in persistencia.documentos[len(chaves_primeira):]
    ]

    assert chaves_primeira == chaves_segunda
    assert [c["coleta_id"] for c in primeira["coletas"]] == [
        c["coleta_id"] for c in segunda["coletas"]
    ]
    assert len(persistencia.por_chave) == len(chaves_primeira)


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
    """Uma execucao, um alvo. Agenda continua permanece com o n8n."""

    agendadores = (
        "while true", "time.sleep", "threading", "schedule.every", "crontab",
        "apscheduler", "asyncio.sleep", "systemd", "signal.alarm",
    )
    for caminho in (
        "volc_ads/inteligencia_google/alvo.py",
        "volc_ads/inteligencia_google/coletor.py",
        "volc_ads/inteligencia_google/persistencia.py",
        "scripts/coletar_google_inteligencia.py",
    ):
        source = (ROOT / caminho).read_text().lower()
        achados = [token for token in agendadores if token in source]
        assert not achados, f"{caminho}: {achados}"


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


def test_normalizacao_de_identidade_nao_divergiu_da_saude():
    from volc_ads.inteligencia_google import alvo as dominio
    from volc_ads.inteligencia_google import saude

    amostras_conta = ("8017851692", "801-785-1692", " 6016739364 ")
    for valor in amostras_conta:
        assert dominio.normalizar_conta(valor) == saude._normalizar_google_id(
            valor, "customer_id"
        )
    for valor in ("24156373085", " 24156373085 "):
        assert dominio.normalizar_id_externo(valor) == saude._normalizar_campaign_id(
            valor, "campaign_id"
        )
    for valor in (CANARIO["volc_campaign_id"], CANARIO["volc_campaign_id"].upper()):
        assert dominio.normalizar_id_interno(valor) == saude._normalizar_id_interno(
            valor, "volc_campaign_id"
        )
