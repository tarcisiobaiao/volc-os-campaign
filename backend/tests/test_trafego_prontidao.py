"""Os quatro portões: G0 nascer, G1 medir, G2 observar, G3 ativar.

⚠️ O teste central deste arquivo é o que NÃO acontece: `smart_bidding_eligible`
não pode virar `True` por ausência de bloqueio conhecido. Um sistema que conclui
"elegível" porque não encontrou problema está afirmando algo sobre o mundo a
partir do que ele não olhou — e o custo desse erro é uma campanha em lance
automático otimizando para um sinal que nunca chega.
"""
from __future__ import annotations

import pytest

from app.trafego import prontidao as pr


def test_g0_nao_implica_g1():
    """Nascer com recibo não diz nada sobre medir."""
    r = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "123"}})
    assert r.campaign_birth == pr.PRONTO
    assert r.measurement_readiness == pr.NAO_PRONTO
    assert r.smart_bidding_eligible is False


def test_conversion_action_lida_nao_vira_meta_efetiva():
    """⚠️ Ler um recurso PRÓXIMO não é ler o recurso.

    A GAQL consulta `conversion_action`. A meta EFETIVA exige
    `customer_conversion_goal`, `campaign_conversion_goal` e sobretudo
    `conversion_goal_campaign_config.goal_config_level`, que diz se quem manda é
    a conta ou a campanha. Declarar PRONTO com o que se tem seria afirmar mais
    do que se leu.
    """
    r = pr.avaliar(recibo_registrado=True, metas_da_conta={
        "primaria": {"id": "1"},
        "acoes": [{"id": "1", "primaria": True}, {"id": "2", "primaria": True}]})
    assert r.conversion_goal_status == pr.PARCIAL
    assert any("não lida" in b for b in r.activation_blockers)


def test_as_oito_primarias_nao_viram_uma():
    """Medido na conta real: 9 ações ENABLED, 8 primárias. Nenhuma some."""
    acoes = [{"id": str(i), "nome": f"a{i}", "categoria": "PURCHASE",
              "primaria": i < 8} for i in range(9)]
    r = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": acoes[0], "acoes": acoes})
    assert len(r.notas["conversion_actions_primarias"]) == 8


def test_g2_governa_g3():
    """Elegível a otimizar sem conseguir observar seria autorizar às cegas."""
    r = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "1"}},
                   data_manager_operante=True,
                   coleta_pos_criacao_provada=False)
    assert r.smart_bidding_eligible is False
    assert any("observabilidade" in b for b in r.activation_blockers)


def test_meta_ausente_e_meta_nao_lida_sao_estados_diferentes():
    """⚠️ Colapsar os dois faria falha de leitura parecer conta sem meta."""
    nao_lida = pr.avaliar(recibo_registrado=True, metas_da_conta=None)
    sem_meta = pr.avaliar(recibo_registrado=True, metas_da_conta={"primaria": None})
    assert nao_lida.conversion_goal_status == pr.INDETERMINADO
    assert sem_meta.conversion_goal_status == pr.NAO_PRONTO
    assert nao_lida.measurement_readiness == pr.INDETERMINADO
    assert sem_meta.measurement_readiness == pr.NAO_PRONTO


def test_smart_bidding_nunca_liga_por_ausencia_de_bloqueio():
    """Nenhuma combinação sem Data Manager operante libera Smart Bidding."""
    for metas in ({"primaria": {"id": "1"}}, {"primaria": None}, None):
        for coleta in (True, False):
            r = pr.avaliar(recibo_registrado=True, metas_da_conta=metas,
                           data_manager_operante=False,
                           coleta_pos_criacao_provada=coleta)
            assert r.smart_bidding_eligible is False, (metas, coleta)


def test_smart_bidding_exige_meta_E_sinal():
    """Ter meta sem sinal não é meia medição — é nenhuma."""
    so_meta = pr.avaliar(recibo_registrado=True,
                         metas_da_conta={"primaria": {"id": "1"}},
                         data_manager_operante=False)
    so_sinal = pr.avaliar(recibo_registrado=True,
                          metas_da_conta={"primaria": None},
                          data_manager_operante=True)
    # ⚠️ "Completo" agora exige os QUATRO portões, e não só G1.
    completo = pr.avaliar(recibo_registrado=True,
                          metas_da_conta={"primaria": {"id": "1"}},
                          data_manager_operante=True,
                          coleta_pos_criacao_provada=True)
    assert so_meta.smart_bidding_eligible is False
    assert so_sinal.smart_bidding_eligible is False
    # Continua False: a meta lida é PARCIAL, não PRONTO — ver o teste acima.
    assert completo.smart_bidding_eligible is False


def test_manual_cpc_nao_e_bloqueio_mas_tambem_nao_e_prontidao():
    r = pr.avaliar(recibo_registrado=True, metas_da_conta={"primaria": {"id": "1"}},
                   estrategia_lance="MANUAL_CPC")
    assert "MANUAL_CPC" not in " ".join(r.activation_blockers)
    assert r.smart_bidding_eligible is False
    assert "não autoriza ativação" in r.notas["manual_cpc"]


def test_lance_automatico_sem_sinal_vira_bloqueio_nomeado():
    r = pr.avaliar(recibo_registrado=True, metas_da_conta={"primaria": {"id": "1"}},
                   estrategia_lance="MAXIMIZE_CONVERSIONS")
    assert any("MAXIMIZE_CONVERSIONS" in b for b in r.activation_blockers)


def test_prontidao_e_imutavel():
    """O veredito não pode ser 'melhorado' depois de apresentado."""
    r = pr.avaliar(recibo_registrado=True, metas_da_conta=None)
    with pytest.raises(Exception):
        r.smart_bidding_eligible = True  # type: ignore[misc]


def test_json_carrega_os_cinco_vereditos():
    j = pr.avaliar(recibo_registrado=True, metas_da_conta=None).para_json()
    for campo in ("campaign_birth", "conversion_goal_status",
                  "measurement_readiness", "data_manager_status",
                  "observability_status", "smart_bidding_eligible",
                  "activation_blockers"):
        assert campo in j


# ═══════════════════════════════════════════════════════════════════════════
# Microfechamento de 01/09/2026 — o que a revisão focal exigiu separar
# ═══════════════════════════════════════════════════════════════════════════

def test_plano_pronto_nao_e_campanha_nascida():
    """⚠️ Os dois já foram um campo só, e o relatório disse 'nasceu' sem campanha.

    `/provar` não cria nada. Um campo chamado `campaign_birth` saindo PRONTO ali
    afirma um fato sobre o mundo — que existe campanha e recibo — a partir de um
    fato sobre o plano.
    """
    r = pr.avaliar(plano_valido=True, recibo_registrado=False,
                   metas_da_conta={"primaria": {"id": "1"}})
    assert r.creation_plan_ready == pr.PRONTO
    assert r.campaign_birth == pr.NAO_PRONTO
    assert "ainda NÃO nasceu" in r.notas["campaign_birth"]


def test_sinal_de_conversao_nao_e_data_manager():
    """Conta que converte por tag tem sinal, e não usa Data Manager.

    Exigir Data Manager para declarar medição diria despreparo onde não há.
    """
    por_tag = pr.avaliar(recibo_registrado=True,
                         metas_da_conta={"primaria": {"id": "1"}},
                         fontes_de_sinal_observadas=["google_tag"],
                         data_manager_operante=False)
    assert por_tag.conversion_signal_status == pr.PRONTO
    assert por_tag.data_manager_status == pr.NAO_PRONTO
    # ⚠️ TUPLA. `Prontidao` congela as coleções em `__post_init__`: `frozen`
    # sozinho impedia rebind e não impedia `r.activation_blockers.append(...)`
    # num veredito já apresentado. `para_json` segue emitindo lista.
    assert por_tag.signal_sources == ("google_tag",)
    # Data Manager ausente não entra em activation_blockers por si só.
    assert not any("Data Manager" in b for b in por_tag.activation_blockers)


def test_lista_de_fontes_vazia_e_nao_comprovado_e_nao_inexistente():
    r = pr.avaliar(recibo_registrado=True, metas_da_conta={"primaria": {"id": "1"}})
    assert r.conversion_signal_status == pr.NAO_PRONTO
    assert r.signal_sources == ()
    assert "não comprovado" in r.notas["conversion_signal"]


def test_estado_real_de_hoje_continua_fail_closed():
    """Sem fonte comprovada e com meta apenas PARCIAL, nada libera."""
    r = pr.avaliar(plano_valido=True, recibo_registrado=False,
                   metas_da_conta={"primaria": {"id": "1"},
                                   "acoes": [{"id": "1", "primaria": True}]})
    assert r.measurement_readiness == pr.NAO_PRONTO
    assert r.smart_bidding_eligible is False
