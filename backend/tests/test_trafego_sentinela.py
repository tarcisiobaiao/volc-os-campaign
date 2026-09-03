"""As contraprovas da Search Delivery Sentinel + Guardião 72h.

Cada `prova_` abaixo nasceu VERMELHA contra o código de `34dc7b4`. Nenhuma delas
usa rede, relógio real, credencial ou identificador verdadeiro: os customer ids
e campaign ids são sintéticos, no formato do Google e sem correspondência com
conta nenhuma.

O caso que originou a missão está em `prova_01_...`: conta suspensa, campanha
ligada, keywords com lance abaixo da primeira página e zero gasto. Antes deste
pacote, o diagnóstico dizia `keyword: ok` e `conta: nao_apurado`.
"""
from __future__ import annotations

import pytest

from app.trafego import sentinela as s


# ── fixtures sintéticas ─────────────────────────────────────────────────────
#
# ⚠️ Nenhum dado real. `9990001111` é sintético e não corresponde a conta alguma.

CUSTOMER = "9990001111"
CAMPANHA = "cmp.search:prova"
AGORA = "2026-09-03T12:00:00+00:00"


def conta(status="ENABLED", **kw):
    return s.LeituraDaConta(
        customer_id=CUSTOMER, status=status, observado_em=AGORA, **kw
    )


def campanha(**kw):
    base = dict(
        status="ENABLED", primary_status="ELIGIBLE", serving_status="SERVING",
        bidding_strategy_type="MANUAL_CPC", horas_ligada=120.0,
        orcamento_diario_micros=50_000_000,
    )
    base.update(kw)
    return s.LeituraDaCampanha(**base)


def metricas(**kw):
    base = dict(impressoes=1000, cliques=40, custo_micros=25_000_000,
                conversoes=3.0, perda_por_orcamento=0.0, perda_por_rank=0.0)
    base.update(kw)
    return s.LeituraDeMetricas(**base)


def anuncios(**kw):
    base = dict(observados=2, aptos=2, reprovados=0, em_revisao=0, sem_estado=0)
    base.update(kw)
    return s.LeituraDeAnuncios(**base)


def kw(texto, *, lance=3_000_000, primeira=1_000_000, qs=8,
       primary="ELIGIBLE", motivos=(), match="PHRASE"):
    return {
        "texto": texto, "match_type": match, "primary_status": primary,
        "primary_status_reasons": list(motivos),
        "lance_micros": lance, "primeira_pagina_micros": primeira,
        "quality_score": qs,
    }


def recomendacoes_apuradas(n=0):
    return s.QuadroDeRecomendacoes(
        estado_da_coleta=(s.COLETA_COM_DADOS if n else s.COLETA_VAZIO_CONFIRMADO),
        itens=tuple(
            s.RecomendacaoAdjudicada(
                tipo="KEYWORD", alvo=f"customers/{CUSTOMER}/recommendations/{i}",
                impacto_informado="+12 cliques/semana (informado pelo Google)",
                observado_em=AGORA, frescor="recente",
            ) for i in range(n)
        ),
    )


def leitura(**kw_):
    base = dict(
        customer_id=CUSTOMER, volc_campaign_id=CAMPANHA,
        conta=conta(), campanha=campanha(), metricas=metricas(),
        keywords=s.ler_keywords([kw("credito consignado")]),
        anuncios=anuncios(),
        medicao=s.LeituraDeMedicao(conversion_goal_status="PRONTO",
                                   metas_observadas=2),
        destino=s.LeituraDoDestino(estado="apto", observado_em=AGORA),
        recomendacoes=recomendacoes_apuradas(0),
        estado_da_coleta="com_dados", frescor="recente", observado_em=AGORA,
        janela_inicio="2026-08-27", janela_fim="2026-09-03",
    )
    base.update(kw_)
    return s.LeituraParaSentinela(**base)


# ── 1. suspensão da conta vence tudo ────────────────────────────────────────


def test_01_conta_suspensa_vence_keywords_limitadas():
    """O caso Crédito Up. Antes: `keyword: ok`, `conta: nao_apurado`."""
    v = s.avaliar(leitura(
        conta=conta("SUSPENDED"),
        keywords=s.ler_keywords([
            kw("credito consignado", lance=500_000, primeira=3_200_000, qs=3),
            kw("emprestimo consignado", lance=500_000, primeira=3_100_000, qs=3),
        ]),
        metricas=metricas(impressoes=0, cliques=0, custo_micros=0, conversoes=0.0),
    ))

    assert v.status == s.ACCOUNT_BLOCKED
    assert v.escopo == s.ESCOPO_CONTA
    assert v.severidade == s.SEV_CRITICA
    assert v.incidente is True

    # O lance continua no dossiê — como evidência secundária, nunca como veredito.
    secundarios = {c.status for c in v.causas_secundarias}
    assert s.LIMITED_BY_RANK in secundarios
    assert v.causa_primaria is not None
    assert "SUSPENDED" in v.causa_primaria.frase
    # E o próximo ato NÃO manda mexer em lance.
    assert "lance" not in (v.proximo_ato or "").split("nenhum ato")[0].lower() or \
        "não muda este estado" in (v.proximo_ato or "")


@pytest.mark.parametrize("status", ["SUSPENDED", "CANCELED", "CLOSED"])
def test_01b_todo_estado_bloqueante_da_conta_vence(status):
    v = s.avaliar(leitura(conta=conta(status),
                          metricas=metricas(impressoes=0, custo_micros=0)))
    assert v.status == s.ACCOUNT_BLOCKED


# ── 2. campanha pausada não vira falso alarme ───────────────────────────────


def test_02_campanha_pausada_com_zero_gasto_nao_e_no_delivery():
    v = s.avaliar(leitura(
        campanha=campanha(status="PAUSED"),
        metricas=metricas(impressoes=0, cliques=0, custo_micros=0, conversoes=0.0),
    ))
    assert v.status == s.CAMPAIGN_OFF
    assert v.incidente is False
    assert v.severidade == s.SEV_INFORMATIVA
    assert s.NO_DELIVERY not in {c.status for c in v.causas_secundarias}
    assert s.NO_DELIVERY != v.status


def test_02b_campanha_pausada_cala_o_lance():
    """Pausada com keyword baratíssima NÃO produz veredito de lance."""
    v = s.avaliar(leitura(
        campanha=campanha(status="PAUSED"),
        keywords=s.ler_keywords([kw("x", lance=1, primeira=9_000_000)]),
        metricas=metricas(impressoes=0, custo_micros=0),
    ))
    assert v.status == s.CAMPAIGN_OFF
    assert s.LIMITED_BY_RANK not in {c.status for c in v.causas_secundarias}


# ── 3. carência: recém-criada é OBSERVING ───────────────────────────────────


def test_03_campanha_dentro_da_carencia_e_observing():
    v = s.avaliar(leitura(
        campanha=campanha(horas_ligada=2.0),
        metricas=metricas(impressoes=0, cliques=0, custo_micros=0, conversoes=0.0),
    ))
    assert v.janela_do_guardiao == s.JANELA_NASCIMENTO
    assert v.status == s.OBSERVING
    assert v.incidente is False


def test_03b_entre_a_carencia_e_24h_ainda_e_observing():
    v = s.avaliar(leitura(
        campanha=campanha(horas_ligada=12.0),
        metricas=metricas(impressoes=0, custo_micros=0),
    ))
    assert v.janela_do_guardiao == s.JANELA_ATE_24H
    assert v.status == s.OBSERVING


def test_03c_as_quatro_janelas_do_guardiao():
    p = s.POLITICA_PADRAO
    assert s.janela_do_guardiao(1.0, p) == s.JANELA_NASCIMENTO
    assert s.janela_do_guardiao(10.0, p) == s.JANELA_ATE_24H
    assert s.janela_do_guardiao(48.0, p) == s.JANELA_24_72H
    assert s.janela_do_guardiao(200.0, p) == s.JANELA_APOS_72H
    # ⚠️ `None` NÃO é zero: idade desconhecida tem janela própria.
    assert s.janela_do_guardiao(None, p) == s.JANELA_INDETERMINADA
    assert s.janela_madura(s.JANELA_INDETERMINADA, p) is False
    assert s.janela_madura(s.JANELA_NASCIMENTO, p) is False
    assert s.janela_madura(s.JANELA_24_72H, p) is True
    assert s.janela_madura(s.JANELA_APOS_72H, p) is True


def test_03d_a_politica_do_guardiao_e_versionada_e_configuravel():
    p = s.PoliticaDoGuardiao(versao=2, horas_de_carencia=1.0,
                             horas_para_incidente=4.0, horas_do_guardiao=48.0)
    assert s.janela_do_guardiao(2.0, p) == s.JANELA_ATE_24H
    assert s.janela_do_guardiao(10.0, p) == s.JANELA_24_72H
    with pytest.raises(ValueError):
        s.PoliticaDoGuardiao(horas_de_carencia=99.0, horas_para_incidente=1.0)


# ── 4. madura, fresca e sem entrega → NO_DELIVERY ───────────────────────────


def test_04_madura_fresca_e_zero_impressoes_e_no_delivery():
    v = s.avaliar(leitura(
        campanha=campanha(horas_ligada=48.0),
        metricas=metricas(impressoes=0, cliques=0, custo_micros=0, conversoes=0.0),
    ))
    assert v.status == s.NO_DELIVERY
    assert v.escopo == s.ESCOPO_CAMPANHA
    assert v.severidade == s.SEV_ALTA
    assert v.janela_do_guardiao == s.JANELA_24_72H
    assert v.incidente is True
    assert v.mutacao_externa is False


def test_04b_idade_desconhecida_nao_vira_no_delivery():
    """Sem saber há quanto tempo está ligada, não se afirma que parou."""
    v = s.avaliar(leitura(
        campanha=campanha(horas_ligada=None),
        metricas=metricas(impressoes=0, custo_micros=0),
    ))
    assert v.status != s.NO_DELIVERY
    assert v.status == s.OBSERVING
    assert any("horas_ligada" in d for d in v.desconhecidos)


# ── 5. coleta velha → DATA_UNAVAILABLE, nunca NO_DELIVERY ───────────────────


def test_05_coleta_velha_com_zero_metricas_e_data_unavailable():
    v = s.avaliar(leitura(
        frescor="velho",
        campanha=campanha(horas_ligada=200.0),
        metricas=metricas(impressoes=0, cliques=0, custo_micros=0, conversoes=0.0),
    ))
    assert v.status == s.DATA_UNAVAILABLE
    assert v.status != s.NO_DELIVERY
    assert v.estado_da_evidencia == "ausente"


def test_05b_coleta_falhou_nao_vira_ausencia_de_entrega():
    v = s.avaliar(leitura(
        estado_da_coleta="falhou",
        metricas=s.LeituraDeMetricas(),
    ))
    assert v.status == s.DATA_UNAVAILABLE
    assert v.causa_primaria is not None
    assert "FALHOU" in v.causa_primaria.frase


def test_05c_campanha_sem_coleta_nenhuma_e_data_unavailable():
    v = s.avaliar(leitura(estado_da_coleta=None, frescor="nao_apurado",
                          metricas=s.LeituraDeMetricas()))
    assert v.status == s.DATA_UNAVAILABLE
    assert v.status != s.HEALTHY


# ── 6. falha na coleta de recomendações ≠ zero recomendações ────────────────


def test_06_falha_de_recomendacoes_nao_vira_zero():
    quadro = s.QuadroDeRecomendacoes(
        estado_da_coleta=s.COLETA_FALHOU, itens=None,
        impedimento="a chamada de recomendações não retornou",
    )
    v = s.avaliar(leitura(recomendacoes=quadro))

    assert v.recomendacoes.apurado is False
    assert v.recomendacoes.itens is None          # ⚠️ NÃO é []
    assert v.recomendacoes.json()["quantidade"] is None
    assert any("recomendações" in d for d in v.desconhecidos)
    # E a evidência inteira é rebaixada: não se declara saúde sem saber.
    assert v.status != s.HEALTHY


def test_06b_vazio_confirmado_e_diferente_de_falha():
    quadro = s.QuadroDeRecomendacoes(
        estado_da_coleta=s.COLETA_VAZIO_CONFIRMADO, itens=(),
    )
    assert quadro.apurado is True
    assert quadro.json()["quantidade"] == 0
    assert quadro.itens == ()


def test_06c_nao_executada_tambem_nao_e_zero():
    quadro = s.QuadroDeRecomendacoes()
    assert quadro.estado_da_coleta == s.COLETA_NAO_EXECUTADA
    assert quadro.apurado is False
    assert quadro.json()["quantidade"] is None


# ── 7. 100% abaixo da primeira página, com denominador ──────────────────────


def test_07_todas_as_keywords_abaixo_da_primeira_pagina_tem_denominador():
    leitura_kw = s.ler_keywords([
        kw("credito consignado", lance=500_000, primeira=3_200_000),
        kw("emprestimo pessoal", lance=400_000, primeira=2_900_000),
        kw("financiamento imobiliario", lance=600_000, primeira=4_000_000),
    ])
    assert leitura_kw.observadas == 3
    assert leitura_kw.abaixo_da_primeira_pagina == 3
    assert leitura_kw.medidas_para_lance == 3

    v = s.avaliar(leitura(keywords=leitura_kw, conta=conta("ENABLED")))
    causa = next(c for c in [v.causa_primaria, *v.causas_secundarias]
                 if c and c.status == s.LIMITED_BY_RANK)
    assert causa.denominador is not None
    assert causa.denominador.quantos == 3
    assert causa.denominador.de_quantos == 3
    assert "3 de 3" in causa.denominador.frase()
    assert "100%" in causa.denominador.frase()


def test_07b_nenhum_percentual_sem_denominador():
    d = s.Denominador(rotulo="abaixo", quantos=1, de_quantos=1)
    # Amostra menor que o mínimo da política → sem proporção, e a frase o diz.
    assert d.proporcao() is None
    assert "%" not in d.frase()
    assert "1 de 1" in d.frase()
    with pytest.raises(ValueError):
        s.Denominador(rotulo="impossível", quantos=5, de_quantos=2)


# ── 8. keyword sem dado não entra no denominador medido ─────────────────────


def test_08_keyword_sem_dado_fica_fora_do_denominador():
    leitura_kw = s.ler_keywords([
        kw("com dado a", lance=500_000, primeira=3_000_000),
        kw("com dado b", lance=500_000, primeira=3_000_000),
        kw("sem estimativa", lance=500_000, primeira=None),
        kw("sem lance", lance=None, primeira=3_000_000),
    ])
    assert leitura_kw.observadas == 4
    assert leitura_kw.sem_dado_de_lance == 2
    assert leitura_kw.abaixo_da_primeira_pagina == 2
    # ⚠️ O denominador é 2, não 4: as duas sem dado não entram nem como sim nem
    # como não. Empurrá-las para "não está abaixo" seria o falso verde.
    assert leitura_kw.medidas_para_lance == 2

    v = s.avaliar(leitura(keywords=leitura_kw))
    causa = next(c for c in [v.causa_primaria, *v.causas_secundarias]
                 if c and c.status == s.LIMITED_BY_RANK)
    assert causa.denominador.de_quantos == 2
    assert causa.denominador.fora_da_conta == 2
    assert "fora desta conta" in causa.denominador.frase()
    assert any("sem lance ou sem estimativa" in d for d in v.desconhecidos)


# ── 9. nenhum anúncio apto vem ANTES de ajuste de lance ─────────────────────


def test_09_sem_anuncio_apto_vence_o_lance():
    v = s.avaliar(leitura(
        anuncios=anuncios(observados=2, aptos=0, reprovados=0, em_revisao=0,
                          sem_estado=0),
        keywords=s.ler_keywords([
            kw("a", lance=100_000, primeira=5_000_000),
            kw("b", lance=100_000, primeira=5_000_000),
            kw("c", lance=100_000, primeira=5_000_000),
        ]),
        metricas=metricas(impressoes=0, custo_micros=0),
        campanha=campanha(horas_ligada=100.0),
    ))
    assert v.status == s.ADS_NOT_READY
    assert v.escopo == s.ESCOPO_ANUNCIO
    assert s.ordem_da_causa(s.ADS_NOT_READY) < s.ordem_da_causa(s.LIMITED_BY_RANK)
    assert s.ordem_da_causa(s.ADS_NOT_READY) < s.ordem_da_causa(s.NO_DELIVERY)
    assert v.causa_primaria.denominador.de_quantos == 2
    assert "lance" in (v.proximo_ato or "")   # diz para NÃO começar pelo lance


def test_09b_zero_anuncios_observados_com_coleta_completa_e_ads_not_ready():
    v = s.avaliar(leitura(
        anuncios=anuncios(observados=0, aptos=0),
        metricas=metricas(impressoes=0, custo_micros=0),
        campanha=campanha(horas_ligada=100.0),
    ))
    assert v.status == s.ADS_NOT_READY


# ── 10. policy review não afirma aprovado nem reprovado ─────────────────────


def test_10_anuncio_em_revisao_nao_e_aprovado_nem_reprovado():
    v = s.avaliar(leitura(
        anuncios=anuncios(observados=1, aptos=0, reprovados=0, em_revisao=1,
                          sem_estado=0),
        metricas=metricas(impressoes=0, custo_micros=0),
        campanha=campanha(horas_ligada=100.0),
    ))
    assert v.status == s.POLICY_REVIEW
    assert v.status not in {s.POLICY_BLOCKED, s.HEALTHY}
    assert v.severidade == s.SEV_MEDIA
    assert "revisão" in v.causa_primaria.frase


def test_10b_anuncio_reprovado_e_policy_blocked():
    v = s.avaliar(leitura(
        anuncios=anuncios(observados=1, aptos=0, reprovados=1, em_revisao=0),
        metricas=metricas(impressoes=0, custo_micros=0),
    ))
    assert v.status == s.POLICY_BLOCKED
    assert v.severidade == s.SEV_CRITICA


# ── 11. recibo de destino ausente ───────────────────────────────────────────


def test_11_recibo_de_destino_ausente_nao_e_aprovacao():
    v = s.avaliar(leitura(destino=s.LeituraDoDestino(estado="ausente")))
    assert v.status == s.DATA_UNAVAILABLE
    assert v.escopo == s.ESCOPO_DESTINO
    assert any("ausência não é aprovação" in d for d in v.desconhecidos)


def test_11b_destino_reprovado_vence_campanha_e_keyword():
    v = s.avaliar(leitura(
        destino=s.LeituraDoDestino(estado="reprovado", motivo="política de destino",
                                   observado_em=AGORA),
        keywords=s.ler_keywords([kw("a", lance=1, primeira=9_000_000)]),
        metricas=metricas(impressoes=0, custo_micros=0),
        campanha=campanha(horas_ligada=100.0),
    ))
    assert v.status == s.POLICY_BLOCKED
    assert v.escopo == s.ESCOPO_DESTINO
    assert s.ordem_da_causa(s.POLICY_BLOCKED) < s.ordem_da_causa(s.NO_DELIVERY)


def test_11c_conta_suspensa_vence_ate_o_destino_reprovado():
    v = s.avaliar(leitura(
        conta=conta("SUSPENDED"),
        destino=s.LeituraDoDestino(estado="reprovado", observado_em=AGORA),
    ))
    assert v.status == s.ACCOUNT_BLOCKED


# ── 12. Smart Bidding sem conversão medida ──────────────────────────────────


def test_12_smart_bidding_sem_meta_e_measurement_not_ready():
    v = s.avaliar(leitura(
        campanha=campanha(bidding_strategy_type="MAXIMIZE_CONVERSIONS"),
        medicao=s.LeituraDeMedicao(conversion_goal_status="NAO_PRONTO",
                                   metas_observadas=0,
                                   impedimento="nenhuma meta primária observada"),
    ))
    assert v.status == s.MEASUREMENT_NOT_READY
    assert v.escopo == s.ESCOPO_MEDICAO


def test_12b_manual_cpc_nao_gera_alarme_de_mensuracao():
    """Sem Smart Bidding, prontidão de mensuração não é causa de não entrega."""
    v = s.avaliar(leitura(
        campanha=campanha(bidding_strategy_type="MANUAL_CPC"),
        medicao=s.LeituraDeMedicao(conversion_goal_status="NAO_PRONTO",
                                   metas_observadas=0),
    ))
    assert v.status != s.MEASUREMENT_NOT_READY


def test_12c_prontidao_indeterminada_nao_e_pronta():
    v = s.avaliar(leitura(
        campanha=campanha(bidding_strategy_type="TARGET_CPA"),
        medicao=s.LeituraDeMedicao(conversion_goal_status="INDETERMINADO"),
    ))
    assert v.status == s.DATA_UNAVAILABLE
    assert v.status != s.HEALTHY


# ── 13. duas leituras iguais = UM incidente ─────────────────────────────────


def test_13_duas_leituras_iguais_nao_criam_dois_incidentes():
    v1 = s.avaliar(leitura(conta=conta("SUSPENDED")))
    v2 = s.avaliar(leitura(conta=conta("SUSPENDED"),
                           janela_inicio="2026-09-01", janela_fim="2026-09-03"))

    # ⚠️ Mesma chave apesar da janela diferente: a janela NÃO entra na identidade.
    assert v1.chave == v2.chave

    i1 = s.incidente_do_veredito(v1, "2026-09-03T12:00:00+00:00")
    i2 = s.incidente_do_veredito(v2, "2026-09-03T18:00:00+00:00")
    consolidado = s.consolidar([i1], [i2], "2026-09-03T18:00:00+00:00")

    assert len(consolidado) == 1
    unico = consolidado[0]
    assert unico.ocorrencias == 2
    assert unico.primeira_vez_em == "2026-09-03T12:00:00+00:00"
    assert unico.ultima_vez_em == "2026-09-03T18:00:00+00:00"
    assert unico.aberto is True


def test_13b_escopos_diferentes_sao_incidentes_diferentes():
    a = s.chave_do_incidente(customer_id=CUSTOMER, volc_campaign_id=CAMPANHA,
                             escopo=s.ESCOPO_CONTA, status=s.DATA_UNAVAILABLE)
    b = s.chave_do_incidente(customer_id=CUSTOMER, volc_campaign_id=CAMPANHA,
                             escopo=s.ESCOPO_CAMPANHA, status=s.DATA_UNAVAILABLE)
    assert a != b


def test_13c_o_reconhecimento_atravessa_a_repeticao():
    base = s.Incidente(
        chave="k", customer_id=CUSTOMER, volc_campaign_id=CAMPANHA,
        escopo=s.ESCOPO_CONTA, status=s.ACCOUNT_BLOCKED, severidade=s.SEV_CRITICA,
        primeira_vez_em="2026-09-01T00:00:00+00:00",
        ultima_vez_em="2026-09-01T00:00:00+00:00",
        reconhecido_em="2026-09-01T01:00:00+00:00", reconhecido_por="operador",
    )
    atual = s.replace(base, ultima_vez_em="2026-09-02T00:00:00+00:00",
                      reconhecido_em=None, reconhecido_por=None)
    out = s.consolidar([base], [atual], "2026-09-02T00:00:00+00:00")
    assert out[0].reconhecido_por == "operador"
    assert out[0].ocorrencias == 2


# ── 14. resolvido e recorrente reabre preservando histórico ─────────────────


def test_14_incidente_resolvido_e_recorrente_reabre_com_historico():
    i = s.Incidente(
        chave="k", customer_id=CUSTOMER, volc_campaign_id=CAMPANHA,
        escopo=s.ESCOPO_CAMPANHA, status=s.NO_DELIVERY, severidade=s.SEV_ALTA,
        primeira_vez_em="2026-09-01T00:00:00+00:00",
        ultima_vez_em="2026-09-01T06:00:00+00:00", ocorrencias=3,
        reconhecido_em="2026-09-01T02:00:00+00:00", reconhecido_por="operador",
    )

    # some da leitura → resolve, e a prova de que existiu é preservada
    resolvido = s.consolidar([i], [], "2026-09-02T00:00:00+00:00")
    assert len(resolvido) == 1
    assert resolvido[0].resolvido_em == "2026-09-02T00:00:00+00:00"
    assert resolvido[0].aberto is False
    assert resolvido[0].primeira_vez_em == "2026-09-01T00:00:00+00:00"
    assert resolvido[0].ocorrencias == 3

    # volta → reabre, com o first_seen ORIGINAL e o contador de reaberturas
    de_novo = s.replace(i, primeira_vez_em="2026-09-05T00:00:00+00:00",
                        ultima_vez_em="2026-09-05T00:00:00+00:00", ocorrencias=1,
                        reconhecido_em=None, reconhecido_por=None)
    reaberto = s.consolidar(resolvido, [de_novo], "2026-09-05T00:00:00+00:00")
    assert len(reaberto) == 1
    r = reaberto[0]
    assert r.aberto is True
    assert r.resolvido_em is None
    assert r.primeira_vez_em == "2026-09-01T00:00:00+00:00"   # histórico preservado
    assert r.reaberturas == 1
    assert r.ocorrencias == 4
    # ⚠️ Reabertura NÃO herda o "estou ciente": é um fato novo.
    assert r.reconhecido_por is None


def test_14b_incidente_ja_resolvido_nao_e_resolvido_de_novo():
    i = s.Incidente(
        chave="k", customer_id=CUSTOMER, volc_campaign_id=CAMPANHA,
        escopo=s.ESCOPO_CAMPANHA, status=s.NO_DELIVERY, severidade=s.SEV_ALTA,
        primeira_vez_em="2026-09-01T00:00:00+00:00",
        ultima_vez_em="2026-09-01T00:00:00+00:00",
        resolvido_em="2026-09-02T00:00:00+00:00",
    )
    out = s.consolidar([i], [], "2026-09-09T00:00:00+00:00")
    assert out[0].resolvido_em == "2026-09-02T00:00:00+00:00"


def test_14c_nada_saudavel_vira_incidente():
    v = s.avaliar(leitura())
    assert v.status == s.HEALTHY
    assert s.incidente_do_veredito(v, AGORA) is None


# ── 15/16. recomendações registradas, jamais aplicadas ──────────────────────


def test_15_recomendacao_e_registrada_e_adjudicada_nunca_aplicada():
    v = s.avaliar(leitura(recomendacoes=recomendacoes_apuradas(2)))
    assert v.recomendacoes.apurado is True
    assert len(v.recomendacoes.itens) == 2
    for item in v.recomendacoes.itens:
        assert item.adjudicacao == s.ADJ_NOVA
        assert item.confianca == "baixa"
        assert item.json()["aplicada"] is False
        assert "não aplica nem dispensa" in item.proximo_ato
        assert "informado pelo Google" in (item.impacto_informado or "")
    assert v.mutacao_externa is False


def test_15b_adjudicacao_fora_do_contrato_e_recusada():
    with pytest.raises(ValueError):
        s.RecomendacaoAdjudicada(
            tipo="X", alvo=None, impacto_informado=None,
            observado_em=None, frescor="recente", adjudicacao="aplicada",
        )


def test_16_nenhum_metodo_mutavel_e_alcancavel_pelo_dominio():
    """Prova por AST, não por busca de texto.

    ⚠️ A primeira versão desta prova varria o texto do arquivo e falhava por
    causa do próprio docblock, que CITA `google.ads` para dizer que ele não é
    importado. Um teste que não distingue código de comentário não prova nada
    sobre o que o módulo executa. Esta versão percorre a árvore sintática:
    nenhum import, nenhuma chamada e nenhum atributo do módulo alcança a rede
    ou um método mutável do Google Ads.
    """
    import ast
    import inspect

    arvore = ast.parse(inspect.getsource(s))

    modulos_proibidos = {
        "google", "googleads", "google.ads", "volc_ads", "requests", "httpx",
        "urllib", "urllib.request", "socket", "aiohttp",
    }
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                raiz = alias.name.split(".")[0]
                assert alias.name not in modulos_proibidos and raiz not in modulos_proibidos, (
                    f"import proibido no domínio da sentinela: {alias.name}"
                )
        if isinstance(no, ast.ImportFrom):
            nome = no.module or ""
            raiz = nome.split(".")[0]
            assert nome not in modulos_proibidos and raiz not in modulos_proibidos, (
                f"import proibido no domínio da sentinela: {nome}"
            )

    # Nenhum NOME executável de método mutável do Google Ads.
    mutaveis = {
        "ApplyRecommendation", "DismissRecommendation", "MutateGoogleAds",
        "apply_recommendation", "dismiss_recommendation", "mutate",
        "mutate_campaigns", "mutate_ad_group_criteria", "mutate_campaign_budgets",
    }
    for no in ast.walk(arvore):
        if isinstance(no, ast.Attribute):
            assert no.attr not in mutaveis, f"atributo mutável alcançável: {no.attr}"
        if isinstance(no, ast.Name):
            assert no.id not in mutaveis, f"nome mutável alcançável: {no.id}"

    # E o veredito declara a não-mutação, em vez de deixá-la implícita.
    assert s.avaliar(leitura()).mutacao_externa is False


# ── 17. saudável com evidência fresca ───────────────────────────────────────


def test_17_campanha_saudavel_com_evidencia_fresca_e_healthy():
    v = s.avaliar(leitura())
    assert v.status == s.HEALTHY
    assert v.severidade == s.SEV_INFORMATIVA
    assert v.estado_da_evidencia == "apurada"
    assert v.causa_primaria is None
    assert v.incidente is False
    assert v.mutacao_externa is False


def test_17b_evidencia_parcial_nunca_sai_healthy():
    """Sem `customer.status`, a campanha impecável NÃO é declarada saudável."""
    v = s.avaliar(leitura(conta=s.LeituraDaConta(customer_id=CUSTOMER, status=None)))
    assert v.status == s.DATA_UNAVAILABLE
    assert v.status != s.HEALTHY
    assert v.escopo == s.ESCOPO_CONTA


# ── 18. enum futuro/desconhecido → falha conservadora ───────────────────────


def test_18_status_de_conta_desconhecido_nao_vira_verde():
    v = s.avaliar(leitura(conta=conta("QUANTUM_SUSPENDED_2031")))
    assert v.status == s.DATA_UNAVAILABLE
    assert v.status != s.HEALTHY
    assert v.escopo == s.ESCOPO_CONTA
    assert "QUANTUM_SUSPENDED_2031" in v.causa_primaria.frase


def test_18b_status_de_campanha_desconhecido_nao_vira_verde():
    v = s.avaliar(leitura(campanha=campanha(status="HIBERNATING")))
    assert v.status == s.DATA_UNAVAILABLE
    assert v.status != s.HEALTHY


def test_18c_ordem_da_causa_manda_desconhecido_para_o_fim():
    assert s.ordem_da_causa("PALAVRA_QUE_NAO_EXISTE") == len(s.PRECEDENCIA)
    assert s.ordem_da_causa(s.ACCOUNT_BLOCKED) == 0
    assert s.severidade_de("PALAVRA_QUE_NAO_EXISTE") == s.SEV_MEDIA


# ── acesso negado ───────────────────────────────────────────────────────────


def test_19_acesso_negado_vence_tudo_menos_conta_bloqueada():
    v = s.avaliar(leitura(
        conta=s.LeituraDaConta(customer_id=CUSTOMER, status=None,
                               acesso_negado=True,
                               motivo_do_acesso="USER_PERMISSION_DENIED"),
        metricas=s.LeituraDeMetricas(),
    ))
    assert v.status == s.ACCESS_UNAVAILABLE
    assert v.severidade == s.SEV_CRITICA
    assert s.ordem_da_causa(s.ACCESS_UNAVAILABLE) < s.ordem_da_causa(s.DATA_UNAVAILABLE)
    assert s.ordem_da_causa(s.ACCOUNT_BLOCKED) < s.ordem_da_causa(s.ACCESS_UNAVAILABLE)


# ── redundância de keywords, sem LLM ────────────────────────────────────────


def test_20_redundancia_agrupa_ordem_e_repeticao():
    clusters = s.agrupar_por_intencao([
        {"texto": "crédito consignado", "match_type": "PHRASE"},
        {"texto": "consignado credito", "match_type": "BROAD"},
        {"texto": "CRÉDITO  CONSIGNADO", "match_type": "EXACT"},
    ])
    assert len(clusters) == 1
    assert clusters[0].redundante is True
    assert len(clusters[0].variantes) == 3


def test_20b_intencoes_diferentes_nao_sao_duplicatas():
    """`credito consignado` e `credito pessoal` NÃO são a mesma intenção."""
    clusters = s.agrupar_por_intencao([
        {"texto": "credito consignado", "match_type": "PHRASE"},
        {"texto": "credito pessoal", "match_type": "PHRASE"},
        {"texto": "credito imobiliario", "match_type": "PHRASE"},
    ])
    assert len(clusters) == 3
    assert all(not c.redundante for c in clusters)


def test_20c_normalizacao_e_deterministica():
    assert s.normalizar_texto("Crédito  CONSIGNADO!") == "credito consignado"
    assert s.intencao_canonica("consignado credito") == \
        s.intencao_canonica("credito consignado")
    assert s.intencao_canonica("credito credito consignado") == \
        s.intencao_canonica("credito consignado")
    # duas execuções, mesma saída
    assert s.intencao_canonica("a b c") == s.intencao_canonica("c b a")


def test_20d_keyword_sem_texto_nao_entra_em_cluster():
    clusters = s.agrupar_por_intencao([
        {"texto": None, "match_type": "PHRASE"},
        {"texto": "", "match_type": "PHRASE"},
        {"texto": "credito", "match_type": "PHRASE"},
    ])
    assert len(clusters) == 1
    assert clusters[0].intencao == "credito"


def test_20e_redundancia_vira_causa_com_denominador():
    leitura_kw = s.ler_keywords([
        kw("credito consignado", match="PHRASE"),
        kw("consignado credito", match="BROAD"),
        kw("emprestimo", match="EXACT"),
    ])
    assert leitura_kw.clusters_redundantes == 1
    v = s.avaliar(leitura(keywords=leitura_kw))
    causa = next(
        (c for c in [v.causa_primaria, *v.causas_secundarias]
         if c and c.status == s.KEYWORD_STRUCTURE_RISK), None,
    )
    assert causa is not None
    assert causa.denominador is not None
    assert "de 3" in causa.frase


def test_20f_nenhuma_negativa_e_proposta():
    """A lane NÃO propõe negativa sem search term observado."""
    leitura_kw = s.ler_keywords([
        kw("a b", match="PHRASE"), kw("b a", match="BROAD"), kw("c", match="EXACT"),
    ])
    v = s.avaliar(leitura(keywords=leitura_kw))
    causa = next(c for c in [v.causa_primaria, *v.causas_secundarias]
                 if c and c.status == s.KEYWORD_STRUCTURE_RISK)
    assert "negativa" in causa.proximo_ato
    assert "NÃO propõe negativa" in causa.proximo_ato


# ── contrato do veredito ────────────────────────────────────────────────────


def test_21_o_contrato_carrega_os_campos_exigidos():
    v = s.avaliar(leitura(conta=conta("SUSPENDED")))
    j = v.json()
    for campo in (
        "escopo", "status", "severidade", "observado_em", "janela_inicio",
        "janela_fim", "frescor", "estado_da_evidencia", "causa_primaria",
        "causas_secundarias", "desconhecidos", "recomendacoes", "proximo_ato",
        "chave", "mutacao_externa", "janela_do_guardiao", "incidente",
    ):
        assert campo in j, f"contrato sem {campo}"
    assert j["mutacao_externa"] is False
    assert j["causa_primaria"]["evidencias"]
    assert j["escopo"] in s.ESCOPOS


def test_21b_a_precedencia_e_total_e_sem_duplicata():
    assert len(set(s.PRECEDENCIA)) == len(s.PRECEDENCIA)
    assert s.PRECEDENCIA[0] == s.ACCOUNT_BLOCKED
    assert s.PRECEDENCIA[-1] == s.HEALTHY
    # todo estado tem severidade declarada
    for estado in s.PRECEDENCIA:
        assert estado in s.SEVERIDADE
    # HEALTHY, OBSERVING, LEARNING e CAMPAIGN_OFF nunca são incidente
    for calmo in (s.HEALTHY, s.OBSERVING, s.LEARNING, s.CAMPAIGN_OFF):
        assert calmo not in s.ESTADOS_DE_INCIDENTE


def test_21c_a_ordem_de_avaliacao_nao_decide_o_veredito():
    """Conta suspensa vence mesmo sendo avaliada junto de tudo o mais."""
    v = s.avaliar(leitura(
        conta=conta("SUSPENDED"),
        campanha=campanha(status="PAUSED"),
        destino=s.LeituraDoDestino(estado="reprovado"),
        anuncios=anuncios(aptos=0, reprovados=2, observados=2),
        metricas=s.LeituraDeMetricas(),
        estado_da_coleta="falhou",
    ))
    assert v.status == s.ACCOUNT_BLOCKED
