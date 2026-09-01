"""A observabilidade de Performance Max chegando ao cockpit sem perder estado.

O que estes testes protegem é uma coisa só, dita de várias formas: os sete
estados de `ObservationState` e os cinco de `CollectionState` **atravessam** a
fronteira HTTP. Traduzi-los para "presente/ausente" — ou pior, para `0` —
perderia cinco distinções, e cada uma delas separa duas decisões opostas.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import trafego
from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario
from app.trafego import pmax_cockpit as pc


# ── coletei nada × coletei e não há ─────────────────────────────────────────


def test_nao_coletado_nao_e_lista_vazia():
    """`None` é "não coletei"; `[]` é "coletei, e a conta não tem campanha de
    Performance Max". A primeira não autoriza conclusão nenhuma."""
    sem = pc.observabilidade_de_pmax(None)
    vazio = pc.observabilidade_de_pmax([])
    assert sem["estado_da_coleta"] == "NOT_COLLECTED"
    assert vazio["estado_da_coleta"] == "PRESENT_EMPTY"
    assert sem["campanhas"] is None
    assert vazio["campanhas"] == []
    assert sem["quantidade"] is None
    assert vazio["quantidade"] == 0


def test_nao_coletado_diz_por_que():
    sem = pc.observabilidade_de_pmax(None)
    assert sem["causa"]
    assert "não sei" in sem["causa"]


def test_a_causa_do_vazio_afirma_que_a_leitura_aconteceu():
    vazio = pc.observabilidade_de_pmax([])
    assert "Zero medido não é leitura ausente" in vazio["causa"]


# ── os sete estados atravessam ──────────────────────────────────────────────


def test_zero_medido_nao_vira_ausencia():
    from volc_ads.observabilidade_pmax.types import ObservationState, ObservedValue

    medido = ObservedValue(value=0, state=ObservationState.MEASURED_ZERO)
    assert pc._valor_observado(medido)["estado"] == "MEASURED_ZERO"
    assert pc._valor_observado(medido)["valor"] == 0


def test_campo_ausente_e_nao_coletado_sao_distinguiveis():
    from volc_ads.observabilidade_pmax.types import ObservationState, ObservedValue

    ausente = ObservedValue(value=None, state=ObservationState.FIELD_ABSENT)
    nao_pedido = ObservedValue(value=None, state=ObservationState.NOT_COLLECTED)
    a = pc._valor_observado(ausente)
    b = pc._valor_observado(nao_pedido)
    assert a["valor"] is b["valor"] is None
    assert a["estado"] != b["estado"]


def test_falha_de_coleta_nao_e_ausencia():
    from volc_ads.observabilidade_pmax.types import ObservationState, ObservedValue

    falhou = ObservedValue(value=None, state=ObservationState.COLLECTION_FAILED,
                           error_message="a API respondeu 500")
    projetado = pc._valor_observado(falhou)
    assert projetado["estado"] == "COLLECTION_FAILED"
    assert projetado["erro"] == "a API respondeu 500"


def test_todos_os_estados_do_modulo_sobrevivem_a_projecao():
    """Nenhum dos sete pode virar outro no caminho."""
    from volc_ads.observabilidade_pmax.types import ObservationState, ObservedValue

    for estado in ObservationState:
        v = ObservedValue(value=None, state=estado)
        assert pc._valor_observado(v)["estado"] == estado.value


def test_observado_ausente_nao_inventa_estado():
    """`None` no lugar de um `ObservedValue` é ignorância, e não zero."""
    assert pc._valor_observado(None)["estado"] == "NOT_COLLECTED"
    assert pc._valor_observado(None)["valor"] is None


# ── o contrato de assets vem do registro, não de uma cópia ──────────────────


def test_os_papeis_obrigatorios_vem_do_modulo_que_os_define():
    from volc_ads.observabilidade_pmax.coverage import PMAX_FIELD_REQUIREMENTS

    r = pc.papeis_obrigatorios()
    assert r["estado"] == "PRESENT"
    assert len(r["papeis"]) == len(PMAX_FIELD_REQUIREMENTS)


def test_os_obrigatorios_incluem_as_duas_imagens_que_pmax_exige():
    r = pc.papeis_obrigatorios()
    obrigatorios = {p["papel"] for p in r["papeis"] if p["obrigatorio"]}
    assert "MARKETING_IMAGE" in obrigatorios
    assert "SQUARE_MARKETING_IMAGE" in obrigatorios


def test_cada_papel_carrega_minimo_e_maximo():
    for papel in pc.papeis_obrigatorios()["papeis"]:
        assert isinstance(papel["minimo"], int)
        assert isinstance(papel["maximo"], int)
        assert papel["descricao"]


# ── um relatório real, projetado ────────────────────────────────────────────


def _relatorio_de_grupo_sem_evidencia():
    """Um relatório montado pelo próprio módulo de cobertura, e não à mão.

    ⚠️ Montá-lo à mão provaria que a projeção funciona sobre o que EU escrevi,
    e não sobre o que o módulo produz — que é a única coisa que importa.

    O grupo é o pior caso honesto: existe, e nada dentro dele foi coletado.
    """
    from volc_ads.observabilidade_pmax.coverage import (
        evaluate_asset_group_coverage,
    )
    from volc_ads.observabilidade_pmax.types import (
        ObservationState,
        ObservedValue,
        PMaxAdStrength,
        PMaxAssetGroupDTO,
        PMaxAssetGroupStatus,
    )

    grupo = PMaxAssetGroupDTO(
        resource_name="customers/1/assetGroups/9",
        id="9",
        campaign_id="123",
        name="grupo sem evidência",
        status=PMaxAssetGroupStatus.ENABLED,
        primary_status=ObservedValue(
            value=None, state=ObservationState.NOT_COLLECTED),
        primary_status_reasons=(),
        ad_strength=ObservedValue(
            value=PMaxAdStrength.PENDING, state=ObservationState.PRESENT),
        asset_coverage=ObservedValue(
            value=None, state=ObservationState.NOT_COLLECTED),
        final_urls=(),
        final_mobile_urls=(),
        path1=ObservedValue(value=None, state=ObservationState.FIELD_ABSENT),
        path2=ObservedValue(value=None, state=ObservationState.FIELD_ABSENT),
        assets=(),
        signals=(),
    )
    return evaluate_asset_group_coverage(grupo)


def test_um_relatorio_real_atravessa_a_projecao_inteiro():
    projetado = pc._grupo_de_recursos(_relatorio_de_grupo_sem_evidencia())
    assert projetado["id"] == "9"
    assert projetado["forca_do_anuncio"]["estado"] == "PRESENT"
    assert projetado["forca_do_anuncio"]["valor"] == "PENDING"
    assert projetado["cobertura"], "os papéis exigidos precisam aparecer"


def test_o_tri_estado_de_completude_sobrevive():
    """⚠️ O tri-estado é o coração do módulo: `None` é "não deu para concluir",
    `False` é "faltam papéis obrigatórios". Colapsar o primeiro no segundo
    transformaria uma leitura incompleta numa acusação — e um `bool()` em
    qualquer ponto da travessia faz exatamente isso."""
    projetado = pc._grupo_de_recursos(_relatorio_de_grupo_sem_evidencia())
    assert projetado["estruturalmente_completo"] in (None, True, False)
    assert projetado["veredito"] in ("INDETERMINATE", "GAPS", "COMPLETE")


def test_a_evidencia_incompleta_e_declarada_ao_lado_da_contagem():
    """Mostrar `quantidade` sem esta marca daria precisão a uma conta que não
    a tem."""
    projetado = pc._grupo_de_recursos(_relatorio_de_grupo_sem_evidencia())
    for cobertura in projetado["cobertura"]:
        assert "evidencia_completa" in cobertura
        assert isinstance(cobertura["quantidade"], int)


# ── a rota ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(trafego.router)
    quem = Identidade(sub="u1", email="op@volc", papel="ADMIN", origem="sessao")
    app.dependency_overrides[exigir_usuario] = lambda: quem
    app.dependency_overrides[exigir_admin] = lambda: quem
    return TestClient(app)


def test_o_cockpit_traz_a_observabilidade_de_pmax(cliente):
    corpo = cliente.get("/api/trafego/canais").json()
    pmax = next(c for c in corpo["canais"] if c["canal"] == "PERFORMANCE_MAX")
    obs = pmax["operacional"]["observabilidade"]
    assert obs["estado_da_coleta"] == "NOT_COLLECTED"
    assert obs["causa"]


def test_o_cockpit_traz_os_assets_exigidos_de_pmax(cliente):
    corpo = cliente.get("/api/trafego/canais").json()
    pmax = next(c for c in corpo["canais"] if c["canal"] == "PERFORMANCE_MAX")
    exigidos = pmax["operacional"]["assets_exigidos"]
    assert exigidos["estado"] == "PRESENT"
    assert any(p["obrigatorio"] for p in exigidos["papeis"])


def test_o_cockpit_nao_le_o_google_para_desenhar_pmax(cliente):
    """Uma coleta viva aqui gastaria quota da conta do cliente a cada
    navegação."""
    corpo = cliente.get("/api/trafego/canais").json()
    assert corpo["fontes"]["leitura_viva_do_google"] is False
