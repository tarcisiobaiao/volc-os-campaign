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


# ═══════════════════════════════════════════════════════════════════════════
# As contraprovas do DIAGNÓSTICO PERSISTIDO — os falsos verdes medidos em
# `34dc7b4`, cada um com o input exato que os produzia.
# ═══════════════════════════════════════════════════════════════════════════

import asyncio  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from app.trafego.diagnostico_persistido import (  # noqa: E402
    obter_diagnostico_campanha,
)

CAMPANHA_PERSISTIDA = {
    "volc_campaign_id": "cmp.search:01", "customer_id": "9990001111",
    "campaign_id": "24156373085", "nome": "Search de prova", "moeda": "BRL",
}
AGORA_RECENTE = datetime(2026, 8, 28, 12, 10, tzinfo=timezone.utc)


def coleta_persistida(estado="com_dados"):
    return {
        "coleta_id": "c1", "estado": estado, "customer_id": "9990001111",
        "volc_campaign_id": "cmp.search:01", "campaign_id": "24156373085",
        "janela_inicio": "2026-08-20", "janela_fim": "2026-08-27",
        "coletada_em": "2026-08-28T12:00:00Z", "quantidade": 3,
        "erro_codigo": None, "erro_classe": None,
    }


def item_conta(status="ENABLED"):
    return {"tipo_item": "account", "recurso_externo": "9990001111",
            "payload": {"customer": {"status": status, "id": "9990001111"}}}


def item_campanha(**campos):
    base = {"status": "ENABLED", "primary_status": "ELIGIBLE",
            "serving_status": "SERVING", "primary_status_reasons": []}
    base.update(campos)
    return {"tipo_item": "campaign", "recurso_externo": "24156373085",
            "payload": {"campaign": base}}


def item_keyword(ref="k1", *, lance=3_000_000, primeira=1_000_000, qs=8,
                 primary="ELIGIBLE", texto="credito consignado", match="PHRASE"):
    criterio = {"primary_status": primary, "primary_status_reasons": [],
                "keyword": {"match_type": match, "text": texto}}
    if lance is not None:
        criterio["effective_cpc_bid_micros"] = lance
    if primeira is not None:
        criterio["position_estimates"] = {"first_page_cpc_micros": primeira}
    if qs is not None:
        criterio["quality_info"] = {"quality_score": qs}
    return {"tipo_item": "keyword", "recurso_externo": ref,
            "payload": {"ad_group_criterion": criterio}}


def item_anuncio(ref="a1", *, status="ENABLED", primary="ELIGIBLE",
                 aprovacao="APPROVED", revisao="REVIEWED"):
    return {"tipo_item": "ad", "recurso_externo": ref, "payload": {"ad_group_ad": {
        "status": status, "primary_status": primary, "primary_status_reasons": [],
        "policy_summary": {"approval_status": aprovacao, "review_status": revisao},
    }}}


def item_meta(categoria="PURCHASE", biddable=True):
    return {"tipo_item": "conversion_goal", "recurso_externo": categoria,
            "payload": {"customer_conversion_goal": {
                "category": categoria, "origin": "WEBSITE", "biddable": biddable}}}


def metrica(nome, valor):
    return {"recurso_tipo": "campaign", "recurso_externo": "24156373085",
            "nome": nome, "estado_valor": "medido", "valor_numerico": valor,
            "valor_texto": None, "unidade": None, "moeda": None}


class RepoPersistido:
    def __init__(self, itens, metricas, *, estado="com_dados", transicoes=None):
        self._itens, self._metricas = itens, metricas
        self._estado, self._transicoes = estado, transicoes

    async def campanha(self, _): return CAMPANHA_PERSISTIDA
    async def coleta(self, _): return coleta_persistida(self._estado)
    async def itens(self, _): return self._itens
    async def metricas(self, _): return self._metricas
    async def transicoes(self, _): return self._transicoes or []


def diagnosticar(itens, metricas, **kw):
    return asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01", RepoPersistido(itens, metricas, **kw), agora=AGORA_RECENTE,
    ))


def por_eixo(resposta):
    return {d.eixo: d for d in resposta.diagnostico.degraus}


def test_p01_conta_suspensa_aparece_no_degrau_conta():
    """Antes: `conta: nao_apurado` para SEMPRE — não havia campo para o fato."""
    r = diagnosticar(
        [item_conta("SUSPENDED"), item_campanha()],
        [metrica("impressions", 0)],
    )
    conta_ = por_eixo(r)["conta"]
    assert conta_.estado == "bloqueia"
    assert "SUSPENDED" in conta_.frase
    assert r.sentinela.status == "ACCOUNT_BLOCKED"
    assert r.sentinela.severidade == "critica"


def test_p01b_a_escada_deixou_de_estar_permanentemente_suspensa():
    """Com `conta` preenchido, o degrau 0 para de suspender a escada inteira.

    ⚠️ `conta` é o primeiro eixo da ordem causal. Enquanto ele saía
    `nao_apurado`, `vereditoDaEscada` no frontend devolvia
    `{tipo:'nao_apurado', eixo:'conta'}` em TODA campanha e `degrausConfiaveis`
    devolvia lista vazia — a tela nunca mentia de verde porque nunca
    diagnosticava nada.
    """
    r = diagnosticar(
        [item_conta("ENABLED"), item_campanha(), item_keyword(), item_anuncio(),
         item_meta()],
        [metrica("impressions", 1000), metrica("clicks", 30),
         metrica("cost_micros", 20_000_000)],
    )
    assert por_eixo(r)["conta"].estado == "ok"
    assert por_eixo(r)["conta"].estado != "nao_apurado"


def test_p02_perda_por_rank_deixa_de_sair_como_orcamento_ok_e_calado():
    """0% de perda por orçamento e 90% por classificação — dados medidos.

    O ramo `ok` do orçamento dizia "A conta mediu zero de perda de participação
    por orçamento" e NENHUM degrau mencionava rank, embora
    `search_rank_lost_impression_share` estivesse na allowlist desde a v12.
    """
    r = diagnosticar(
        [item_conta(), item_campanha(), item_keyword(), item_anuncio()],
        [metrica("impressions", 10), metrica("clicks", 0),
         metrica("search_budget_lost_impression_share", 0.0),
         metrica("search_rank_lost_impression_share", 0.9001)],
    )
    orcamento = por_eixo(r)["orcamento"]
    assert orcamento.estado == "ok"
    assert "leilão" in orcamento.frase          # aponta para onde a causa está
    campos = {e.campo for e in orcamento.evidencias}
    assert "metrics.search_rank_lost_impression_share" in campos
    assert "LIMITED_BY_RANK" in {
        c["status"] for c in
        ([r.sentinela.causa_primaria] if r.sentinela.causa_primaria else [])
        + r.sentinela.causas_secundarias
    }


def test_p03_estado_desconhecido_nao_produz_impedimento_falso():
    """`ENABLED` + `MISCONFIGURED` + `SUSPENDED`: três valores reais, presentes.

    O `else` devolvia `impedimento="primary_status e serving_status ausentes"` —
    factualmente falso, porque os dois campos vieram.
    """
    r = diagnosticar(
        [item_conta(), item_campanha(primary_status="MISCONFIGURED",
                                     serving_status="SUSPENDED")],
        [metrica("impressions", 0)],
    )
    campanha_ = por_eixo(r)["campanha"]
    assert campanha_.estado == "bloqueia"
    assert campanha_.impedimento is None
    assert "ausentes" not in (campanha_.impedimento or "")


def test_p03b_valor_realmente_fora_do_vocabulario_se_nomeia():
    r = diagnosticar(
        [item_conta(), item_campanha(primary_status="HIBERNATING",
                                     serving_status="SERVING")],
        [metrica("impressions", 0)],
    )
    campanha_ = por_eixo(r)["campanha"]
    assert campanha_.estado == "nao_apurado"
    assert "HIBERNATING" in campanha_.frase
    assert "vocabulário" in (campanha_.impedimento or "")


def test_p04_anuncio_reprovado_deixa_de_sair_como_ok():
    """`ENABLED` + `ELIGIBLE` + `DISAPPROVED` saía como `anuncio: ok, presente`."""
    r = diagnosticar(
        [item_conta(), item_campanha(),
         item_anuncio(aprovacao="DISAPPROVED", revisao="REVIEWED")],
        [metrica("impressions", 0)],
    )
    anuncio = por_eixo(r)["anuncio"]
    assert anuncio.estado == "bloqueia"
    assert anuncio.estado != "ok"
    assert "reprov" in anuncio.frase.lower()


def test_p04b_aprovado_com_limite_nao_e_verde():
    r = diagnosticar(
        [item_conta(), item_campanha(), item_anuncio(aprovacao="APPROVED_LIMITED")],
        [metrica("impressions", 0)],
    )
    assert por_eixo(r)["anuncio"].estado == "limita"


def test_p04c_em_revisao_nao_e_aprovado_nem_reprovado():
    r = diagnosticar(
        [item_conta(), item_campanha(),
         item_anuncio(aprovacao="UNKNOWN", revisao="REVIEW_IN_PROGRESS")],
        [metrica("impressions", 0)],
    )
    anuncio = por_eixo(r)["anuncio"]
    assert anuncio.estado == "nao_apurado"
    assert anuncio.palavra == "em revisão"


def test_p05_keyword_abaixo_da_primeira_pagina_deixa_de_sair_ok():
    """Lance R$ 0,50 contra estimativa de R$ 3,20, `primary_status=ELIGIBLE`."""
    r = diagnosticar(
        [item_conta(), item_campanha(),
         item_keyword("k1", lance=500_000, primeira=3_200_000, qs=3),
         item_keyword("k2", lance=500_000, primeira=3_100_000, qs=3, texto="consignado credito", match="BROAD")],
        [metrica("impressions", 0)],
    )
    keyword = por_eixo(r)["keyword"]
    assert keyword.estado == "bloqueia"
    assert keyword.estado != "ok"
    assert "2" in keyword.frase          # o denominador está na frase
    valores = {e.rotulo: e.valor for e in keyword.evidencias}
    assert valores["com lance abaixo da 1ª página"] == "2 de 2"


def test_p06_coleta_parcial_nao_produz_degrau_ok():
    """`parcial=True` era bandeira de envelope; os degraus saíam `ok` mesmo assim."""
    r = diagnosticar(
        [item_conta(), item_campanha(), item_anuncio(), item_meta()],
        [metrica("impressions", 1000)],
        estado="parcial",
    )
    estados = {d.eixo: d.estado for d in r.diagnostico.degraus}
    assert "ok" not in estados.values()
    assert all(
        e in {"nao_apurado", "limita", "bloqueia"} for e in estados.values()
    )


def test_p07_metas_de_conversao_preenchem_o_eixo_conversao():
    r = diagnosticar(
        [item_conta(), item_campanha(), item_meta("PURCHASE", True)],
        [metrica("impressions", 100)],
    )
    assert por_eixo(r)["conversao"].estado == "ok"

    sem_meta = diagnosticar(
        [item_conta(), item_campanha()], [metrica("impressions", 100)],
    )
    assert por_eixo(sem_meta)["conversao"].estado == "limita"
    assert "zero metas" in por_eixo(sem_meta)["conversao"].frase


def test_p08_o_veredito_da_sentinela_viaja_no_envelope():
    r = diagnosticar(
        [item_conta("SUSPENDED"), item_campanha(),
         item_keyword(lance=500_000, primeira=3_200_000)],
        [metrica("impressions", 0)],
        transicoes=[{"ocorrido_em": "2026-08-20T12:00:00Z",
                     "de": "PAUSED", "para": "ENABLED"}],
    )
    assert r.versao == 2
    assert r.sentinela is not None
    assert r.sentinela.status == "ACCOUNT_BLOCKED"
    assert r.sentinela.janela_do_guardiao == "apos_72h"
    assert r.sentinela.mutacao_externa is False
    assert r.sentinela.proximo_ato
    assert r.sentinela.chave


def test_p09_horas_ligada_vem_do_mesmo_diario_que_o_sino_usa():
    """Sem transições, a janela é indeterminada — e NÃO "recém-criada"."""
    sem = diagnosticar(
        [item_conta(), item_campanha()], [metrica("impressions", 0)],
    )
    assert sem.sentinela.janela_do_guardiao == "indeterminada"
    assert sem.sentinela.status != "NO_DELIVERY"

    nova = diagnosticar(
        [item_conta(), item_campanha(), item_anuncio(), item_keyword(), item_meta()],
        [metrica("impressions", 0)],
        transicoes=[{"ocorrido_em": "2026-08-28T10:00:00Z",
                     "de": "PAUSED", "para": "ENABLED"}],
    )
    assert nova.sentinela.janela_do_guardiao == "nascimento"
    assert nova.sentinela.status == "OBSERVING"


def test_p10_recomendacoes_nao_lidas_nao_viram_zero():
    r = diagnosticar([item_conta(), item_campanha()], [metrica("impressions", 0)])
    assert r.sentinela.recomendacoes["apurado"] is False
    assert r.sentinela.recomendacoes["quantidade"] is None
    assert any("recomendações" in d for d in r.sentinela.desconhecidos)


def test_p11_recomendacoes_com_falha_de_leitura_nao_viram_zero():
    class RepoQueFalhaNasRecomendacoes(RepoPersistido):
        async def recomendacoes(self, _customer_id):
            raise RuntimeError("PostgREST fora do ar")

    r = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        RepoQueFalhaNasRecomendacoes(
            [item_conta(), item_campanha()], [metrica("impressions", 0)]
        ),
        agora=AGORA_RECENTE,
    ))
    assert r.sentinela.recomendacoes["estado_da_coleta"] == "falhou"
    assert r.sentinela.recomendacoes["itens"] is None
    assert r.sentinela.recomendacoes["quantidade"] is None


def test_p12_recomendacoes_lidas_sao_adjudicadas_e_nunca_aplicadas():
    class RepoComRecomendacoes(RepoPersistido):
        async def recomendacoes(self, _customer_id):
            coleta = {"estado": "com_dados", "coletada_em": "2026-08-28T12:00:00Z"}
            linhas = [{
                "recurso_externo": "customers/9990001111/recommendations/abc",
                "payload": {"recommendation": {
                    "type": "KEYWORD", "dismissed": False,
                    "impact": {"base_metrics": {"clicks": 10}},
                }},
            }]
            return coleta, linhas

    r = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        RepoComRecomendacoes(
            [item_conta(), item_campanha()], [metrica("impressions", 0)]
        ),
        agora=AGORA_RECENTE,
    ))
    rec = r.sentinela.recomendacoes
    assert rec["estado_da_coleta"] == "com_dados"
    assert rec["quantidade"] == 1
    item = rec["itens"][0]
    assert item["adjudicacao"] == "nova"
    assert item["aplicada"] is False
    assert "informado pelo Google" in item["impacto_informado"]
    assert "não aplica nem dispensa" in item["proximo_ato"]


def test_p13_o_itens_e_o_metricas_paginam_em_vez_de_truncar():
    """`select_all` existia e não era chamado; o PostgREST corta em 1000."""
    from app.trafego.diagnostico_persistido import SupabaseRepositorioDiagnostico

    chamadas = []

    class Supa:
        enabled = True

        async def select(self, tabela, params):
            chamadas.append(("select", tabela))
            return []

        async def select_all(self, tabela, params):
            chamadas.append(("select_all", tabela))
            return []

    repo = SupabaseRepositorioDiagnostico(Supa())
    asyncio.run(repo.itens("c1"))
    asyncio.run(repo.metricas("c1"))
    assert [c[0] for c in chamadas] == ["select_all", "select_all"]


def test_p14_destino_nao_consultado_nao_sequestra_o_veredito():
    """O defeito que esta lane cometeu e consertou dentro de si mesma.

    Com um só estado para "não tem recibo", `ausente` era o default da ponte —
    e como `ausente` produz `DATA_UNAVAILABLE`, que está acima de `OBSERVING`,
    TODA campanha passava a ter o destino como causa primária. Era o mesmo
    defeito do eixo `conta`: um degrau que ninguém preenche sequestrando o
    veredito de todas as campanhas.
    """
    nova = diagnosticar(
        [item_conta(), item_campanha(), item_anuncio(), item_keyword(), item_meta()],
        [metrica("impressions", 0)],
        transicoes=[{"ocorrido_em": "2026-08-28T10:00:00Z",
                     "de": "PAUSED", "para": "ENABLED"}],
    )
    assert nova.sentinela.status == "OBSERVING"
    assert nova.sentinela.escopo != "destination"
    # E o não-consultado continua DITO, em vez de escondido.
    assert any("não consultado" in d for d in nova.sentinela.desconhecidos)
    # ⚠️ E a evidência continua parcial: ninguém sai saudável por engano.
    assert nova.sentinela.estado_da_evidencia == "parcial"


def test_p14b_destino_consultado_e_ausente_continua_sendo_causa():
    """`ausente` (perguntei, não há) É causa. Ausência não é aprovação."""
    leitura_ = s.LeituraParaSentinela(
        customer_id=CUSTOMER, volc_campaign_id=CAMPANHA,
        conta=conta(), campanha=campanha(), metricas=metricas(),
        keywords=s.ler_keywords([kw("a")]), anuncios=anuncios(),
        medicao=s.LeituraDeMedicao(conversion_goal_status="PRONTO"),
        destino=s.LeituraDoDestino(estado="ausente"),
        recomendacoes=recomendacoes_apuradas(0),
        estado_da_coleta="com_dados", frescor="recente", observado_em=AGORA,
    )
    v = s.avaliar(leitura_)
    assert v.status == s.DATA_UNAVAILABLE
    assert v.escopo == s.ESCOPO_DESTINO


# ═══════════════════════════════════════════════════════════════════════════
# AS CONTRAPROVAS DA REVISÃO ADVERSARIAL (Codex gpt-5.6-sol, 03/09/2026).
#
# Doze achados, todos com reprodução executada pelo revisor. Cada `test_r*`
# abaixo é a contraprova dele, incorporada com o input exato que ele usou.
# Nenhuma foi enfraquecida para passar: o código foi consertado.
# ═══════════════════════════════════════════════════════════════════════════


def test_r01_payload_bruto_de_impacto_nao_vaza_na_resposta():
    """BLOQUEANTE 1. `_texto(impacto)` serializava o dicionário inteiro."""
    import json as _json

    from app.trafego.diagnostico_persistido import _recomendacoes

    class RepoImpacto:
        async def recomendacoes(self, _customer_id):
            return (
                {"estado": "com_dados", "coletada_em": AGORA, "quantidade": 1},
                [{
                    "recurso_externo": "recommendations/sintetica",
                    "payload": {"recommendation": {
                        "type": "KEYWORD", "dismissed": False,
                        "impact": {
                            "secret_token": "NAO_PODE_VAZAR",
                            "base_metrics": {
                                "clicks": 10, "campo_futuro": "TAMBEM_NAO_PODE"
                            },
                        },
                    }},
                }],
            )

    quadro = asyncio.run(_recomendacoes(RepoImpacto(), CUSTOMER))
    corpo = _json.dumps(quadro.json(), ensure_ascii=False)
    assert "NAO_PODE_VAZAR" not in corpo
    assert "TAMBEM_NAO_PODE" not in corpo
    assert "secret_token" not in corpo
    # e o que a allowlist permite CONTINUA aparecendo
    assert "clicks=10" in corpo
    assert "informado pelo Google" in corpo


def test_r01b_impacto_sem_campo_permitido_e_none_e_nao_zero():
    from app.trafego.diagnostico_persistido import _impacto_permitido

    assert _impacto_permitido({"so_campo_desconhecido": 1}) is None
    assert _impacto_permitido(None) is None
    assert _impacto_permitido("texto solto") is None


def test_r02_keyword_em_revisao_nao_pode_ser_healthy():
    """BLOQUEANTE 2. `KW_EM_REVISAO` foi criado, validado e nunca consultado."""
    kws = s.ler_keywords([kw("x", motivos=("AD_GROUP_CRITERION_UNDER_REVIEW",))])
    assert kws.em_revisao == 1
    assert kws.aptas == 0
    v = s.avaliar(leitura(keywords=kws))
    assert v.status != s.HEALTHY
    assert s.POLICY_REVIEW in {
        c.status for c in [v.causa_primaria, *v.causas_secundarias] if c
    }


def test_r02b_keyword_restrita_tambem_nao_e_verde():
    kws = s.ler_keywords([kw("x", motivos=("AD_GROUP_CRITERION_RESTRICTED",))])
    assert kws.restritas == 1
    assert kws.aptas == 0
    v = s.avaliar(leitura(keywords=kws))
    assert v.status != s.HEALTHY


def test_r03_aprovacao_desconhecida_nao_vira_anuncio_apto_nem_healthy():
    """BLOQUEANTE 3. Apto era "ausência de reprovação", não aprovação lida."""
    from app.trafego.diagnostico_persistido import _anuncios_para_sentinela

    ads = _anuncios_para_sentinela([{"campos": {
        "ad_group_ad.status": "ENABLED",
        "ad_group_ad.primary_status": "ELIGIBLE",
        "ad_group_ad.primary_status_reasons": [],
        "ad_group_ad.policy_summary.approval_status": "UNKNOWN",
        "ad_group_ad.policy_summary.review_status": "REVIEWED",
    }}])
    assert ads.aptos == 0
    assert ads.sem_estado == 1
    v = s.avaliar(leitura(anuncios=ads))
    assert v.status != s.HEALTHY


def test_r03b_aprovado_de_verdade_continua_apto():
    """A correção não pode transformar um anúncio bom em problema."""
    from app.trafego.diagnostico_persistido import _anuncios_para_sentinela

    ads = _anuncios_para_sentinela([{"campos": {
        "ad_group_ad.status": "ENABLED",
        "ad_group_ad.primary_status": "ELIGIBLE",
        "ad_group_ad.primary_status_reasons": [],
        "ad_group_ad.policy_summary.approval_status": "APPROVED",
        "ad_group_ad.policy_summary.review_status": "REVIEWED",
    }}])
    assert ads.aptos == 1
    assert ads.sem_estado == 0


def test_r04_falso_verde_com_quality_score_ausente():
    """ALTO 4. A resposta dizia não saber E declarava prova completa."""
    v = s.avaliar(leitura(keywords=s.ler_keywords([kw("x", qs=None)])))
    assert v.estado_da_evidencia == "parcial"
    assert v.status != s.HEALTHY


def test_r04b_evidencia_e_desconhecidos_nao_podem_se_contradizer():
    """A invariante estrutural que torna o achado 4 impossível de reescrever."""
    cenarios = [
        leitura(),
        leitura(keywords=s.ler_keywords([kw("x", qs=None)])),
        leitura(conta=s.LeituraDaConta(customer_id=CUSTOMER, status=None)),
        leitura(campanha=campanha(horas_ligada=None)),
        leitura(recomendacoes=s.QuadroDeRecomendacoes()),
        leitura(destino=s.LeituraDoDestino(estado="nao_consultado")),
        leitura(keywords=s.ler_keywords([kw("x", lance=None)])),
    ]
    for l in cenarios:
        v = s.avaliar(l)
        if v.estado_da_evidencia == "apurada":
            assert v.desconhecidos == (), (
                f"prova apurada com desconhecidos: {v.desconhecidos}"
            )
        if v.desconhecidos:
            assert v.estado_da_evidencia != "apurada"


def test_r06_quantidade_positiva_sem_itens_nao_vira_vazio_confirmado():
    """ALTO 6. Itens perdidos viravam "o Google não sugeriu nada"."""
    from app.trafego.diagnostico_persistido import _recomendacoes

    class RepoItensPerdidos:
        async def recomendacoes(self, _customer_id):
            return ({"estado": "com_dados", "coletada_em": AGORA,
                     "quantidade": 1}, [])

    quadro = asyncio.run(_recomendacoes(RepoItensPerdidos(), CUSTOMER))
    assert quadro.apurado is False
    assert quadro.estado_da_coleta != s.COLETA_VAZIO_CONFIRMADO
    assert quadro.itens is None
    assert "linhas perdidas" in (quadro.impedimento or "")


def test_r06b_vazio_declarado_e_vazio_lido_continua_vazio_confirmado():
    from app.trafego.diagnostico_persistido import _recomendacoes

    class RepoVazioDeVerdade:
        async def recomendacoes(self, _customer_id):
            return ({"estado": "vazio_confirmado", "coletada_em": AGORA,
                     "quantidade": 0}, [])

    quadro = asyncio.run(_recomendacoes(RepoVazioDeVerdade(), CUSTOMER))
    assert quadro.apurado is True
    assert quadro.estado_da_coleta == s.COLETA_VAZIO_CONFIRMADO
    assert quadro.itens == ()


def test_r07_conta_suspensa_observada_vence_falha_de_acesso():
    """ALTO 7. Um `return` fazia a ordem de AVALIAÇÃO decidir o veredito."""
    v = s.avaliar(leitura(conta=s.LeituraDaConta(
        customer_id=CUSTOMER, status="SUSPENDED", acesso_negado=True,
        motivo_do_acesso="USER_PERMISSION_DENIED", observado_em=AGORA,
    )))
    assert v.status == s.ACCOUNT_BLOCKED
    # e a falha de acesso NÃO some: ela vira causa secundária
    assert s.ACCESS_UNAVAILABLE in {c.status for c in v.causas_secundarias}


def test_r07b_acesso_negado_sem_status_continua_access_unavailable():
    v = s.avaliar(leitura(
        conta=s.LeituraDaConta(customer_id=CUSTOMER, status=None,
                               acesso_negado=True,
                               motivo_do_acesso="USER_PERMISSION_DENIED"),
        metricas=s.LeituraDeMetricas(),
    ))
    assert v.status == s.ACCESS_UNAVAILABLE


def test_r09_motivo_low_quality_entra_no_denominador_classificado_uma_vez():
    """MÉDIO 9. A keyword ficava no numerador E fora do universo medido."""
    kws = s.ler_keywords([
        kw("a", qs=None, motivos=("AD_GROUP_CRITERION_LOW_QUALITY",)),
        kw("b", qs=8),
        kw("c", qs=9),
    ])
    assert kws.baixa_qualidade == 1
    assert kws.sem_dado_de_qualidade == 0
    assert kws.medidas_para_qualidade == 3

    v = s.avaliar(leitura(keywords=kws))
    causa = next(
        c for c in [v.causa_primaria, *v.causas_secundarias]
        if c and c.status == s.KEYWORD_STRUCTURE_RISK
    )
    assert causa.denominador.de_quantos == 3
    assert causa.denominador.fora_da_conta == 0
    assert causa.denominador.proporcao() == pytest.approx(1 / 3)


def test_r09b_keyword_sem_score_e_sem_motivo_continua_fora_da_conta():
    kws = s.ler_keywords([kw("a", qs=None), kw("b", qs=8), kw("c", qs=9)])
    assert kws.baixa_qualidade == 0
    assert kws.sem_dado_de_qualidade == 1
    assert kws.medidas_para_qualidade == 2


def test_r10_politica_customizada_nao_some_na_serializacao():
    """MÉDIO 10. A frase respeitava a política e o JSON publicava 100%."""
    kws = s.ler_keywords([
        kw("a", lance=1, primeira=10), kw("b", lance=1, primeira=10),
        kw("c", lance=1, primeira=10),
    ])
    v = s.avaliar(leitura(keywords=kws),
                  s.PoliticaDoGuardiao(minimo_para_proporcao=4))
    causa = next(c for c in [v.causa_primaria, *v.causas_secundarias]
                 if c and c.status == s.LIMITED_BY_RANK)
    d = causa.json()["denominador"]
    assert d["proporcao"] is None
    assert "%" not in d["frase"]
    # e a frase da causa concorda com o JSON
    assert "%" not in causa.frase


def test_r11_horas_nan_nao_viram_campanha_madura_com_incidente():
    """MÉDIO 11. Toda comparação com NaN é falsa; a cascata caía em apos_72h."""
    v = s.avaliar(leitura(
        campanha=campanha(horas_ligada=float("nan")),
        metricas=metricas(impressoes=0, cliques=0, custo_micros=0),
    ))
    assert v.janela_do_guardiao == s.JANELA_INDETERMINADA
    assert v.status != s.NO_DELIVERY


def test_r11b_horas_negativas_tambem_sao_indeterminadas():
    assert s.janela_do_guardiao(-5.0) == s.JANELA_INDETERMINADA


def test_r12_as_fixturas_desta_lane_sao_sinteticas():
    """BAIXO 12. Identificador operacional real numa fixture nova.

    ⚠️ O id real NÃO é escrito aqui: ele é lido do brief que já o documenta, e
    procurado nos arquivos desta lane. Colar o número no teste para provar que
    ele não está nos outros arquivos seria espalhá-lo mais um lugar.
    """
    import re
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    brief = raiz / "volc_ads" / "briefs" / "fgts_saque_aniversario.py"
    if not brief.exists():
        pytest.skip("o brief que documenta o id operacional não está aqui")

    achado = re.search(
        r"""CUSTOMER_ID\s*=\s*["'](\d{8,12})""", brief.read_text(encoding="utf-8")
    )
    if achado is None:
        pytest.skip("o brief não declara CUSTOMER_ID nesta versão")
    real = achado.group(1)

    # `9990001111` é sintético e não corresponde a conta alguma.
    assert CUSTOMER == "9990001111"
    assert real != CUSTOMER

    desta_lane = [
        Path(__file__),
        raiz / "backend" / "tests" / "test_trafego_sentinela_vocabulario.py",
        raiz / "backend" / "app" / "trafego" / "sentinela.py",
        raiz / "src" / "lib" / "diagnostico" / "sentinela.ts",
        raiz / "src" / "components" / "trafego" / "diagnostico"
             / "VereditoDaSentinela.tsx",
        raiz / "src" / "components" / "trafego" / "diagnostico" / "__tests__"
             / "veredito-da-sentinela.test.tsx",
    ]
    sujos = [
        str(f.relative_to(raiz)) for f in desta_lane
        if f.exists() and real in f.read_text(encoding="utf-8")
    ]
    assert not sujos, f"identificador operacional real em: {sujos}"


# ── três achados extras, encontrados na verificação das correções ────────────


def test_r13_aprovacao_ausente_e_tao_desconhecida_quanto_unknown():
    """A ausência do campo era MAIS permissiva que `UNKNOWN`.

    ⚠️ Um veredito de política que a conta não deu e um veredito que não
    coletamos são a mesma ignorância — e a versão anterior fazia justamente a
    leitura mais otimista das duas no caso em que tínhamos menos direito a ela.
    """
    from app.trafego.diagnostico_persistido import _anuncios_para_sentinela

    def linha(**extra):
        campos = {
            "ad_group_ad.status": "ENABLED",
            "ad_group_ad.primary_status": "ELIGIBLE",
            "ad_group_ad.primary_status_reasons": [],
            "ad_group_ad.policy_summary.review_status": "REVIEWED",
        }
        campos.update(extra)
        return {"campos": campos}

    ausente = _anuncios_para_sentinela([linha()])
    desconhecido = _anuncios_para_sentinela([
        linha(**{"ad_group_ad.policy_summary.approval_status": "UNKNOWN"}),
    ])
    assert ausente.aptos == 0
    assert ausente.sem_estado == 1
    assert (ausente.aptos, ausente.sem_estado) == (
        desconhecido.aptos, desconhecido.sem_estado
    )


def test_r14_aprovado_com_limite_e_estado_conhecido_e_nao_ignorancia():
    """`APPROVED_LIMITED` não é apto E não é desconhecido."""
    from app.trafego.diagnostico_persistido import _anuncios_para_sentinela

    ads = _anuncios_para_sentinela([{"campos": {
        "ad_group_ad.status": "ENABLED",
        "ad_group_ad.primary_status": "ELIGIBLE",
        "ad_group_ad.primary_status_reasons": [],
        "ad_group_ad.policy_summary.approval_status": "APPROVED_LIMITED",
        "ad_group_ad.policy_summary.review_status": "REVIEWED",
    }}])
    assert ads.limitados == 1
    assert ads.aptos == 0
    assert ads.sem_estado == 0       # ⚠️ NÃO é ignorância

    v = s.avaliar(leitura(anuncios=ads))
    assert v.status == s.POLICY_BLOCKED
    assert v.status != s.HEALTHY
    assert "restrição" in v.causa_primaria.frase


def test_r15_todo_denominador_respeita_a_politica_em_uso():
    """Nenhum denominador pode publicar percentual que a política proíbe."""
    politica = s.PoliticaDoGuardiao(minimo_para_proporcao=99)
    cenarios = [
        leitura(anuncios=anuncios(observados=3, aptos=0, reprovados=3)),
        leitura(anuncios=anuncios(observados=3, aptos=0, em_revisao=3)),
        leitura(anuncios=anuncios(observados=3, aptos=0)),
        leitura(keywords=s.ler_keywords([
            kw("a", lance=1, primeira=9), kw("b", lance=1, primeira=9),
            kw("c", lance=1, primeira=9),
        ])),
        leitura(keywords=s.ler_keywords([
            kw("a", qs=1), kw("b", qs=1), kw("c", qs=1),
        ])),
        leitura(keywords=s.ler_keywords([
            kw("a b", match="PHRASE"), kw("b a", match="BROAD"), kw("c"),
        ])),
    ]
    for l in cenarios:
        v = s.avaliar(l, politica)
        for causa in [v.causa_primaria, *v.causas_secundarias]:
            if causa is None or causa.denominador is None:
                continue
            j = causa.denominador.json()
            assert j["proporcao"] is None, (
                f"{causa.status}: proporção publicada apesar de "
                f"minimo_para_proporcao=99 ({j})"
            )
            assert "%" not in j["frase"], f"{causa.status}: {j['frase']}"
            assert "%" not in causa.frase, f"{causa.status}: {causa.frase}"


def test_r16_healthy_continua_alcancavel():
    """A correção do achado 4 não pode ter tornado HEALTHY impossível.

    ⚠️ Um estado que nenhuma entrada alcança é um teste que não pode falhar, e
    um teste que não pode falhar não prova nada. `_estado_da_evidencia` passou a
    derivar de `_desconhecidos`; esta prova garante que existe caminho completo.
    """
    v = s.avaliar(leitura())
    assert v.status == s.HEALTHY
    assert v.estado_da_evidencia == "apurada"
    assert v.desconhecidos == ()
    assert v.incidente is False


def test_r15b_nenhum_denominador_e_construido_sem_a_politica():
    """Prova ESTRUTURAL, por AST: nenhum `Denominador(...)` esquece a política.

    ⚠️ `test_r15` cobre os cenários que sabe montar; este cobre os que ninguém
    lembrou de montar. Um construtor novo sem `minimo_para_proporcao` volta a
    publicar percentual que a política em uso proíbe, e a frase e o JSON voltam
    a discordar — que foi exatamente o achado 10.
    """
    import ast
    import inspect

    arvore = ast.parse(inspect.getsource(s))
    faltando = [
        no.lineno for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and getattr(no.func, "id", "") == "Denominador"
        and "minimo_para_proporcao" not in {k.arg for k in no.keywords}
    ]
    assert not faltando, (
        f"Denominador sem minimo_para_proporcao nas linhas {faltando} de "
        "sentinela.py"
    )
