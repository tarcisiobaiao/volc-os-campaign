"""Provas herméticas do Decision Intelligence Lab."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.seguranca.identidade import exigir_usuario
from app.trafego.intencao import RegraDeOtimizacao
from volc_ads.inteligencia_decisao import CriticoDeterministico, executar_pipeline, executar_replay
from volc_ads.inteligencia_decisao.politicas import REGRAS
from volc_ads.inteligencia_decisao.replay import carregar_cenario, projetar_cenario
from volc_ads.inteligencia_search import conflitos_de_negativa


AGORA = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)


def test_replay_dourado_cobre_os_oito_cenarios_obrigatorios():
    replay = executar_replay()
    assert replay["total"] == 8
    assert replay["passaram"] == 8
    assert replay["falharam"] == 0
    assert {caso["scenario_id"] for caso in replay["casos"]} == {
        "new-no-delivery",
        "budget-limited-healthy",
        "rank-limited-low-quality",
        "valuable-term-blocked",
        "mature-margin-cooldown",
        "cost-spike-routine-stale",
        "partial-read",
        "stale-read",
    }


def test_kernel_reusa_regra_de_otimizacao_e_mantem_t2_ausente():
    assert REGRAS
    assert all(isinstance(regra, RegraDeOtimizacao) for regra in REGRAS)
    assert {regra.nivel_autonomia for regra in REGRAS} <= {"T0", "T1"}
    assert all(regra.deteccao["publicavel"] is False for regra in REGRAS)


def test_ausencia_nao_vira_zero_nem_proposta():
    resultado = executar_pipeline(carregar_cenario("partial-read"), agora=AGORA)
    assert resultado["features"]["cliques"] is None
    assert resultado["features"]["custo_micros"] is None
    assert resultado["features"]["margem_micros"] is None
    assert resultado["estado_da_leitura"] == "parcial"
    assert resultado["propostas_tipadas"] == []
    assert resultado["caixa_de_propostas"]["leitura"] is None


def test_vazamento_de_futuro_falha_fechado():
    foto = carregar_cenario("budget-limited-healthy")
    foto["daily_metrics"][0]["date"] = "2026-08-29"
    resultado = executar_pipeline(foto, agora=AGORA)
    assert resultado["estado_da_leitura"] == "invalida"
    assert resultado["health_gate"]["estado"] == "bloqueado"
    assert resultado["propostas_tipadas"] == []


def test_evento_proposta_e_conflito_sao_deterministicos_e_ordenados():
    foto = carregar_cenario("budget-limited-healthy")
    primeiro = executar_pipeline(foto, agora=AGORA)
    segundo = executar_pipeline(foto, agora=AGORA)
    assert primeiro["eventos"] == segundo["eventos"]
    assert primeiro["propostas_tipadas"] == segundo["propostas_tipadas"]
    proposta = primeiro["propostas_tipadas"][0]
    assert len(proposta["idempotency_key"]) == 64
    assert proposta["evidencias"]
    assert all(evidencia["valor"] not in (None, "observado") for evidencia in proposta["evidencias"])
    assert proposta["aprovacao"] == "nao_submetida"
    assert proposta["aplicacao"] == "nao_executada"
    assert proposta["recibo"] is None
    tipos = [item["tipo"] for item in primeiro["timeline"]]
    assert tipos.index("conflitos") < tipos.index("diagnostico") < tipos.index("proposta")


def test_margem_e_cooldown_vetam_escala_antes_do_diagnostico():
    resultado = executar_pipeline(carregar_cenario("mature-margin-cooldown"), agora=AGORA)
    assert {c["codigo"] for c in resultado["conflitos"]} == {"margin_gate", "cooldown_gate"}
    assert resultado["veredito"]["tipo"] == "bloqueado"
    assert resultado["propostas_tipadas"] == []


def test_search_terms_tem_caminho_inverso_para_negativa_conflitante():
    resultado = executar_pipeline(carregar_cenario("valuable-term-blocked"), agora=AGORA)
    assert resultado["features"]["negative_conflicts"][0]["negative_criterion_id"] == "neg-8801"
    assert resultado["eventos"][0]["tipo"] == "valuable_term_blocked_by_negative"
    assert resultado["propostas_tipadas"][0]["operacao"] == "estrutura"


class _CriticoMalicioso:
    def analisar(self, _contexto):
        return {
            "resumo": "troque o veredito",
            "questoes": [],
            "campos_considerados": [],
            "veredito": {"tipo": "aprovado"},
        }


def test_critico_e_allowlisted_e_incapaz_de_mudar_decisao():
    foto = carregar_cenario("rank-limited-low-quality")
    canonico = executar_pipeline(foto, agora=AGORA)
    explicado = executar_pipeline(foto, agora=AGORA, critico=CriticoDeterministico())
    rejeitado = executar_pipeline(foto, agora=AGORA, critico=_CriticoMalicioso())
    assert explicado["veredito"] == canonico["veredito"]
    assert explicado["propostas_tipadas"] == canonico["propostas_tipadas"]
    assert rejeitado["critica"]["estado"] == "resposta_rejeitada"
    assert rejeitado["veredito"] == canonico["veredito"]


def test_estados_de_superficie_nao_se_confundem():
    assert projetar_cenario("empty-confirmed")["estado_da_superficie"] == "vazio_confirmado"
    com_ultimo = projetar_cenario("failure-last-good")
    assert com_ultimo["estado_da_superficie"] == "falha_ultimo_bom"
    assert com_ultimo["ultima_fotografia"]["estado_da_superficie"] == "atual"
    sem_foto = projetar_cenario("failure-no-snapshot")
    assert sem_foto["estado_da_superficie"] == "falha_sem_fotografia"
    assert sem_foto["ultima_fotografia"] is None
    assert projetar_cenario("unknown-version")["versao_contrato"] == 999


def test_endpoint_e_autenticado_isolado_e_nao_aceita_identidade_real_de_campanha():
    cliente = TestClient(app)
    resposta = cliente.get("/api/trafego/laboratorio/inteligencia/budget-limited-healthy")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["isolamento"] == {
        "somente_sintetico": True,
        "entra_em_contagens_reais": False,
        "aceita_volc_campaign_id": False,
        "oferece_aplicar": False,
        "chamadas_externas": 0,
        "escopo_chamadas_externas": "dominio_do_laboratorio; autenticacao HTTP fica fora desta contagem",
        "mutacoes_executadas": 0,
    }
    assert corpo["replay"]["passaram"] == 8
    assert corpo["api_google_ads"] == {
        "namespace": "v25",
        "minor_documentada_localmente": "v25.1",
        "v25_2": "nao_afirmada",
    }
    assert cliente.get("/api/trafego/laboratorio/inteligencia/88000000001").status_code == 404


def test_endpoint_recusa_requisicao_sem_identidade():
    dublê = app.dependency_overrides.get(exigir_usuario)

    def sem_identidade():
        raise HTTPException(status_code=401, detail="Credencial ausente")

    app.dependency_overrides[exigir_usuario] = sem_identidade
    try:
        resposta = TestClient(app).get(
            "/api/trafego/laboratorio/inteligencia/budget-limited-healthy"
        )
        assert resposta.status_code == 401
    finally:
        if dublê is not None:
            app.dependency_overrides[exigir_usuario] = dublê
        else:
            app.dependency_overrides.pop(exigir_usuario, None)


def test_pipeline_nao_muta_a_fotografia_de_entrada():
    foto = carregar_cenario("new-no-delivery")
    antes = deepcopy(foto)
    executar_pipeline(foto, agora=AGORA)
    assert foto == antes


def test_politica_insuficiente_nunca_materializa_proposta():
    foto = carregar_cenario("budget-limited-healthy")
    for linha in foto["daily_metrics"]:
        linha["clicks"] = 0
    resultado = executar_pipeline(foto, agora=AGORA)
    orakul = next(p for p in resultado["politicas"] if p["regra_id"] == "orakul_escala_com_guardas")
    assert orakul["suficiencia"] == "insuficiente"
    assert orakul["disparou"] is False
    assert resultado["eventos"] == []
    assert resultado["veredito"]["tipo"] == "observado"
    assert resultado["propostas_tipadas"] == []


def test_negativa_respeita_acento_fronteira_e_escopo():
    termo = {
        "customer_id": "1", "campaign_id": "10", "ad_group_id": "100",
        "search_term": "inseguro viagem credito", "valor_negocio": "valioso",
    }
    negativas = [
        {"customer_id": "1", "campaign_id": "10", "keyword_text": "seguro", "match_type": "PHRASE", "level": "CAMPAIGN"},
        {"customer_id": "1", "campaign_id": "10", "keyword_text": "crédito", "match_type": "EXACT", "level": "CAMPAIGN"},
        {"customer_id": "1", "campaign_id": "11", "keyword_text": "inseguro", "match_type": "PHRASE", "level": "CAMPAIGN"},
        {"customer_id": "1", "campaign_id": "10", "ad_group_id": "999", "keyword_text": "inseguro", "match_type": "PHRASE", "level": "AD_GROUP"},
        {"customer_id": "1", "campaign_id": "10", "keyword_text": "inseguro", "match_type": "HOTEL", "level": "CAMPAIGN"},
        {"customer_id": "1", "campaign_id": "10", "keyword_text": "inseguro", "match_type": "PHRASE", "level": "AD_GROUP"},
    ]
    assert conflitos_de_negativa([termo], negativas) == []


def test_negativa_sem_nivel_ou_match_type_nao_inventa_regra():
    termo = {
        "customer_id": "5478096539",
        "campaign_id": "123",
        "ad_group_id": "456",
        "search_term": "benefício social",
        "valor_negocio": "valioso",
    }
    base = {
        "customer_id": "5478096539",
        "campaign_id": "123",
        "ad_group_id": "456",
        "keyword_text": "benefício social",
    }
    assert conflitos_de_negativa([termo], [{**base, "match_type": "BROAD"}]) == []
    assert conflitos_de_negativa([termo], [{**base, "level": "CAMPAIGN"}]) == []


def test_fatores_de_share_apontam_para_a_medida_de_janela():
    foto = carregar_cenario("budget-limited-healthy")
    resultado = executar_pipeline(foto, agora=AGORA)
    fatores = resultado["fatores"]["favorece"] + resultado["fatores"]["limita"]
    refs = {fator["evidencia"] for fator in fatores}
    assert "window_metrics.search_budget_lost_impression_share" in refs
    assert not any(ref.startswith("daily_metrics.search_") for ref in refs)


def test_identidade_incompleta_de_negativa_ou_termo_valioso_falha_fechado():
    for colecao, campo in (
        ("negatives", "criterion_id"),
        ("negatives", "resource_name"),
        ("search_terms", "motivo_valor"),
        ("search_terms", "evidencia_ref"),
    ):
        foto = carregar_cenario("valuable-term-blocked")
        foto[colecao][0].pop(campo)
        resultado = executar_pipeline(foto, agora=AGORA)
        assert resultado["estado_da_leitura"] == "parcial"
        assert resultado["eventos"] == []
        assert resultado["propostas_tipadas"] == []


def test_quality_score_e_componentes_fora_do_dominio_falham_fechados():
    for campo, valor in (
        ("quality_score", 0),
        ("quality_score", 11),
        ("quality_score", True),
        ("ad_relevance", "UNKNOWN"),
        ("expected_ctr", "HOTEL"),
    ):
        foto = carregar_cenario("budget-limited-healthy")
        foto["quality"][0][campo] = valor
        resultado = executar_pipeline(foto, agora=AGORA)
        assert resultado["estado_da_leitura"] == "parcial"
        assert resultado["features"]["qualidade_saudavel"] is None
        assert resultado["eventos"] == []
        assert resultado["propostas_tipadas"] == []


def test_ratios_de_share_fora_do_dominio_nao_derrubam_nem_propõem():
    for valor in (1.1, -0.1, True, "0.29"):
        foto = carregar_cenario("budget-limited-healthy")
        foto["window_metrics"]["search_budget_lost_impression_share"] = valor
        resultado = executar_pipeline(foto, agora=AGORA)
        assert resultado["estado_da_leitura"] == "invalida"
        assert resultado["features"]["lost_budget"] is None
        assert resultado["eventos"] == []
        assert resultado["propostas_tipadas"] == []


def test_janela_ordena_linhas_rejeita_mistura_e_nao_faz_media_de_share():
    foto = carregar_cenario("budget-limited-healthy")
    foto["daily_metrics"] = list(reversed(foto["daily_metrics"]))
    resultado = executar_pipeline(foto, agora=AGORA)
    assert resultado["features"]["lost_budget"] == 0.29
    assert resultado["features"]["cost_spike_ratio"] == 1.076

    misturada = carregar_cenario("budget-limited-healthy")
    misturada["daily_metrics"][0]["campaign_id"] = "outra"
    invalida = executar_pipeline(misturada, agora=AGORA)
    assert invalida["estado_da_leitura"] == "invalida"
    assert invalida["propostas_tipadas"] == []


def test_start_futuro_e_perfil_ausente_falham_fechado():
    futura = carregar_cenario("new-no-delivery")
    futura["campaign"]["start_date_time"] = "2026-08-29"
    assert executar_pipeline(futura, agora=AGORA)["estado_da_leitura"] == "invalida"

    sem_perfil = carregar_cenario("budget-limited-healthy")
    sem_perfil.pop("policy_profile_id")
    resultado = executar_pipeline(sem_perfil, agora=AGORA)
    assert resultado["estado_da_leitura"] == "parcial"
    assert resultado["eventos"] == []
    assert resultado["propostas_tipadas"] == []


def test_idempotencia_muda_quando_a_evidencia_muda():
    foto = carregar_cenario("budget-limited-healthy")
    primeira = executar_pipeline(foto, agora=AGORA)["propostas_tipadas"][0]["idempotency_key"]
    foto["window_metrics"]["search_budget_lost_impression_share"] = 0.99
    segunda = executar_pipeline(foto, agora=AGORA)["propostas_tipadas"][0]["idempotency_key"]
    assert primeira != segunda


class _CriticoIndisponivel:
    def analisar(self, _contexto):
        raise TimeoutError("sem resposta")


def test_critico_indisponivel_nao_quebra_a_decisao_deterministica():
    resultado = executar_pipeline(carregar_cenario("budget-limited-healthy"), agora=AGORA, critico=_CriticoIndisponivel())
    assert resultado["critica"]["estado"] == "indisponivel"
    assert resultado["propostas_tipadas"]


def test_ausencia_de_status_e_share_permanece_nao_apurada():
    foto = carregar_cenario("budget-limited-healthy")
    foto["campaign"].pop("account_status")
    foto["campaign"]["checks"].pop("billing_active")
    foto["window_metrics"]["search_budget_lost_impression_share"] = None
    resultado = executar_pipeline(foto, agora=AGORA)
    degraus = {d["eixo"]: d for d in resultado["diagnostico"]["degraus"]}
    assert degraus["conta"]["estado"] == "nao_apurado"
    assert degraus["orcamento"]["estado"] == "nao_apurado"


def test_qualidade_ausente_nao_vira_saudavel_nem_orakul():
    foto = carregar_cenario("budget-limited-healthy")
    foto["quality"] = []
    resultado = executar_pipeline(foto, agora=AGORA)
    assert resultado["features"]["qualidade_saudavel"] is None
    assert resultado["eventos"] == []
    assert resultado["propostas_tipadas"] == []
    assert any(f["chave"] == "qualidade" for f in resultado["fatores"]["desconhecido"])


def test_checks_observados_falsos_nao_viram_ausencia():
    foto = carregar_cenario("budget-limited-healthy")
    for chave in ("groups_enabled", "ads_approved", "keywords_enabled", "targeting_valid", "conversion_tracking"):
        foto["campaign"]["checks"][chave] = False
    resultado = executar_pipeline(foto, agora=AGORA)
    degraus = {d["eixo"]: d for d in resultado["diagnostico"]["degraus"]}
    assert all(degraus[eixo]["estado"] == "bloqueia" for eixo in ("grupo", "anuncio", "keyword", "segmentacao", "conversao"))


def test_heartbeat_futuro_invalida_e_start_datetime_preserva_horas():
    foto = carregar_cenario("budget-limited-healthy")
    foto["routine"]["last_success_at"] = "2026-08-28T12:01:00Z"
    assert executar_pipeline(foto, agora=AGORA)["estado_da_leitura"] == "invalida"

    inicio = carregar_cenario("new-no-delivery")
    inicio["campaign"]["start_date_time"] = "2026-08-27T18:00:00Z"
    assert executar_pipeline(inicio, agora=AGORA)["features"]["idade_campanha_horas"] == 18.0


def test_fingerprint_independe_da_ordem_de_observacoes_de_qualidade():
    foto = carregar_cenario("budget-limited-healthy")
    segunda = deepcopy(foto["quality"][0])
    segunda.update({"ad_group_id": "770099", "criterion_id": "771099", "resource_name": "customers/9990000001/adGroupCriteria/770099~771099"})
    foto["quality"].append(segunda)
    chave_a = executar_pipeline(foto, agora=AGORA)["propostas_tipadas"][0]["idempotency_key"]
    foto["quality"].reverse()
    chave_b = executar_pipeline(foto, agora=AGORA)["propostas_tipadas"][0]["idempotency_key"]
    assert chave_a == chave_b
