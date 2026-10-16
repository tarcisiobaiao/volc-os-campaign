"""Ponta a ponta sintético: Ads (final URL com UTM) → sensor → volc-ingest → raw_events →
JoinAds (custom_key/utm_campaign) → junção campanha × dia. Nenhum teste lê rede.

O template é o Final URL suffix vivo da campanha 20000000011 (recibo
`043c77f5:.claude-ads/runs/google-ads-recovery-20261015T125729-0300/receipts/d-live-campaign-audit.json:37`).
Premissa do lado JoinAds (confirmada em produção: RECIBO-LEITURAS-20261016 L5, kv numérico = 97–100% do
earnings de domínio 08–16/10, inclusive após o GTM v35): o key-value `utm_campaign` chega à JoinAds com o valor cru
da URL, por um setter que não é o WEBS Wrapper v2 (que descarta o id — ver `test_wrapper_v2_tambem_descarta_o_id`).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from urllib.parse import quote, urlsplit

import pytest

from volc_dil.contracts.money import Dinheiro, MoedasDiferentes
from volc_dil.contracts.vocab import EstadoMedida, MetodoAtribuicao
from volc_dil.fundacao.identidade import (
    CampanhaRegistrada,
    Confianca,
    CustoCampanhaDia,
    EventoSensorReady,
    Grao,
    GraoNaoSuportado,
    GraoTempo,
    ReceitaChaveDia,
    ReceitaDominioDia,
    RegistroCampanhas,
    TemplateCampanha,
    UtmSessao,
    juntar_campanha_dia,
    limpar_utm_ingest,
    normalizar_valor_wrapper_v2,
    para_json,
    receita_por_sessao,
    utm_da_pagina_sensor_v3,
)

SUFIXO = ("utm_source=google&utm_medium=cpc&utm_campaign={campaignid}&utm_term={keyword}"
          "&utm_content={adgroupid}&utm_device={device}&utm_placement={placement}&vc_creative={creative}"
          "&vc_match={matchtype}&vc_network={network}&vc_target={targetid}&vc_loc={loc_physical_ms}"
          "&vc_ext={extensionid}")
CONTA, CAMP, GRUPO = "1000000001", "20000000011", "165432109876"
DIA = date(2026, 10, 10)
SITE = "site.exemplo"
AS_OF = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)  # estado as_of (contrato R1-F5)
LIDO = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
REG = RegistroCampanhas([CampanhaRegistrada(CONTA, CAMP, "CAMPANHA-SINTETICA", date(2026, 9, 21), hosts=(SITE,))])


def juntar(*a, **k):
    k.setdefault("as_of", AS_OF)
    return juntar_campanha_dia(*a, **k)


def clique_ads(campaign=CAMP, adgroup=GRUPO, keyword="cursos tecnicos", gclid=True,
               base="https://site.exemplo/r/guia-exemplo/", sufixo=SUFIXO):
    valores = {"campaignid": campaign, "adgroupid": adgroup, "keyword": keyword, "device": "m",
               "placement": "", "creative": "700000000001", "matchtype": "e", "network": "g",
               "targetid": "kwd-1", "loc_physical_ms": "1001773", "extensionid": ""}
    q = sufixo
    for k, v in valores.items():
        q = q.replace("{" + k + "}", quote(v, safe=""))
    if gclid:
        q += "&gclid=CLIQUE_SINTETICO_NAO_REAL"
    return f"{base}?{q}"


def visita(url, sid, ts, armazenado=None, bot=False):
    """Uma página: sensor (campaign()) → payload → volc-ingest (cleanValue) → linha raw_events."""
    utm, novo = utm_da_pagina_sensor_v3(urlsplit(url).query, armazenado)
    payload_ingest = limpar_utm_ingest(json.loads(json.dumps(utm.como_payload())))
    ev = EventoSensorReady(sid=sid, pid=f"{sid}-{ts.isoformat()}", ts=ts,
                           utm=UtmSessao.de_payload(payload_ingest), bot=bot, host=urlsplit(url).hostname or "")
    return ev, novo


def ts(h, m=0, dia=DIA):
    # 13h UTC = 10h em São Paulo
    return datetime(dia.year, dia.month, dia.day, h, m, tzinfo=timezone.utc)


def usd(x):
    return Dinheiro.de_decimal(x, "USD")


def brl(x):
    return Dinheiro.de_decimal(x, "BRL")


def custo(dia=DIA, valor="42.90", cliques=51, camp=CAMP, estado=EstadoMedida.MEDIDO):
    return CustoCampanhaDia(CONTA, camp, dia, brl(valor) if valor is not None else None, cliques, estado,
                            disponivel_em=AS_OF)


def receita_joinads(valor, dia=DIA, key="utm_campaign", value=CAMP, estado=EstadoMedida.MEDIDO,
                    dominio=SITE, moeda=usd):
    # legado /key-value: grão campaign_day, sem dimensão extra; versão vigente lida em LIDO
    return ReceitaChaveDia(dia, dominio, "key_value", "campaign_day", key, value,
                           moeda(valor) if valor is not None else None, estado, (), LIDO)


def linha(res, camp=CAMP, dia=DIA):
    [l] = [l for l in res.linhas if l.campaign_id == camp and l.dia == dia]
    return l


# ---------------------------------------------------------------- hoje (template por id)

def test_hoje_custo_e_receita_juntam_mas_trafego_e_nao_atribuivel():
    evs = []
    for i in range(3):  # três sessões pagas reais, duas páginas cada
        e1, arm = visita(clique_ads(), f"s{i}", ts(13, i))
        e2, _ = visita("https://site.exemplo/rec/passo-exemplo-pr/", f"s{i}", ts(13, i + 5), arm)
        evs += [e1, e2]
    evs.append(visita("https://site.exemplo/r/guia-exemplo/", "org", ts(14))[0])  # orgânico
    res = juntar(
        [custo()], evs, [receita_joinads("3.40")], REG,
        receitas_dominio=[ReceitaDominioDia(DIA, "site.exemplo", usd("3.50"), disponivel_em=AS_OF)])
    l = linha(res)
    assert l.custo.valor == brl("42.90") and l.custo.estado is EstadoMedida.MEDIDO
    assert l.receita.valor == usd("3.40") and l.metodo_receita is MetodoAtribuicao.AGGREGATE_CAMPAIGN_DATE
    # A contradição do roadmap, executada: 3 sessões pagas chegaram, nenhuma com campanha.
    assert l.sessoes.estado is EstadoMedida.NAO_ATRIBUIVEL and l.sessoes.valor is None
    c = res.cobertura
    assert (c.sessoes_total, c.sessoes_pagas, c.sessoes_resolvidas, c.sessoes_perdidas_pelo_sensor) == (4, 3, 0, 3)
    assert c.fracao_sessoes_pagas_resolvidas == Fraction(0)
    assert c.fracao_receita_com_chave == Fraction(34, 35)
    assert c.receita_sem_chave == usd("0.10")  # explícita, não distribuída
    assert not c.fuso_receita_verificado and c.avisos


def test_wrapper_v2_tambem_descarta_o_id():
    # Se a JoinAds dependesse do WEBS Wrapper v2, o key-value utm_campaign sumiria desde a v35.
    assert normalizar_valor_wrapper_v2(CAMP) == ""
    assert normalizar_valor_wrapper_v2(GRUPO) == ""


def test_valor_do_gclid_nunca_chega_ao_raw_events():
    ev, arm = visita(clique_ads(), "s", ts(13))
    assert ev.utm.paid == 1
    assert "CLIQUE_SINTETICO" not in json.dumps(arm) + repr(ev)


# ---------------------------------------------------------------- template textual (contrafactual)

REG_NOME = RegistroCampanhas([
    CampanhaRegistrada(CONTA, "30", "Cursos Tecno Técnico", date(2026, 1, 1), template=TemplateCampanha.NOME,
                       hosts=(SITE,))])
COMPROVADO = {"trafego_campanha_comprovado": True}  # contrafactual: condição `requer` da matriz provada


def test_utm_com_caixa_acento_espaco_resolve_probabilistico_e_receita_textual_nao_junta():
    url = "https://site.exemplo/r/x/?utm_source=Google&utm_medium=CPC&utm_campaign=" + quote("  CURSOS   tecno técnico ")
    ev, _ = visita(url, "a", ts(13))
    assert ev.utm.campaign == "cursos_tecno_tecnico"
    res = juntar([custo(camp="30")], [ev],
                 [receita_joinads("0.50", value="cursos_tecno_tecnico")], REG_NOME, **COMPROVADO)
    l = linha(res, camp="30")
    assert l.sessoes.valor == 1 and l.confianca_sessoes is Confianca.PROBABILISTICA
    # receita por nome NÃO entra (só determinística); fica no balde explícito
    assert l.receita.estado is EstadoMedida.AUSENTE
    assert [m for _, m in res.receita_nao_atribuida] == [
        "receita_exige_chave_deterministica:nome_declarado_normalizado"]


def test_truncamento_no_limite_do_sensor():
    nome = "Campanha de cursos técnicos do Tecno para São Paulo capital"
    reg = RegistroCampanhas([CampanhaRegistrada(CONTA, "31", nome, date(2026, 1, 1), template=TemplateCampanha.NOME, hosts=(SITE,))])
    ev, _ = visita("https://site.exemplo/r/x/?utm_campaign=" + quote(nome), "t", ts(13))
    assert len(ev.utm.campaign) == 40
    res = juntar([custo(camp="31")], [ev], [], reg, **COMPROVADO)
    assert res.cobertura.sessoes_resolvidas == 0  # truncado no limite: recusado mesmo sem colisão
    assert linha(res, camp="31").sessoes.estado is EstadoMedida.ZERO_CONFIRMADO


def test_sessao_com_duas_campanhas_na_mesma_aba_nao_atribui():
    reg = RegistroCampanhas([
        CampanhaRegistrada(CONTA, "40", "alfa", date(2026, 1, 1), template=TemplateCampanha.NOME, hosts=(SITE,)),
        CampanhaRegistrada(CONTA, "41", "beta", date(2026, 1, 1), template=TemplateCampanha.NOME, hosts=(SITE,))])
    e1, arm = visita("https://site.exemplo/r/x/?utm_campaign=alfa", "m", ts(13))
    e2, _ = visita("https://site.exemplo/r/y/?utm_campaign=beta", "m", ts(13, 2), arm)
    res = juntar([custo(camp="40"), custo(camp="41")], [e1, e2], [], reg, **COMPROVADO)
    assert res.cobertura.sessoes_multicampanha == 1
    assert linha(res, camp="40").sessoes.estado is EstadoMedida.NAO_ATRIBUIVEL


# ---------------------------------------------------------------- receita: chave trocada, ausente, sem chave

def test_custom_key_substituida_e_macro_vao_para_balde_nao_atribuido():
    rs = [receita_joinads("1.00"),
          receita_joinads("0.30", key="land_uri", value="/"),
          receita_joinads("0.20", value="{{campaign.id}}"),
          receita_joinads("0.10", value="99999999999")]  # id desconhecido no registro
    res = juntar([custo()], [], rs, REG)
    assert linha(res).receita.valor == usd("1.00")
    motivos = sorted(m for _, m in res.receita_nao_atribuida)
    assert motivos == ["chave_trocada", "id_nao_registrado_no_dia", "macro_nao_expandida"]
    assert res.cobertura.denominador_receita == "soma_key_value"
    assert res.cobertura.fracao_receita_com_chave == Fraction(100, 160)


def test_receita_ausente_nao_vira_zero_e_zero_confirmado_e_falha_se_distinguem():
    d2, d3, d4 = DIA + timedelta(days=1), DIA + timedelta(days=2), DIA + timedelta(days=3)
    rs = [receita_joinads("0", dia=d2, estado=EstadoMedida.ZERO_CONFIRMADO),
          receita_joinads(None, dia=d3, estado=EstadoMedida.FALHA)]
    res = juntar([custo(), custo(dia=d2), custo(dia=d3), custo(dia=d4, valor=None, cliques=None,
                                                                            estado=EstadoMedida.NAO_COLETADO)],
                              [], rs, REG)
    assert linha(res).receita.estado is EstadoMedida.AUSENTE and linha(res).receita.valor is None
    assert linha(res, dia=d2).receita.estado is EstadoMedida.ZERO_CONFIRMADO
    assert linha(res, dia=d2).receita.valor == usd("0")
    assert linha(res, dia=d3).receita.estado is EstadoMedida.FALHA
    assert linha(res, dia=d4).custo.estado is EstadoMedida.NAO_COLETADO
    assert linha(res, dia=d4).cliques.estado is EstadoMedida.NAO_COLETADO
    assert linha(res).sessoes.estado is EstadoMedida.NAO_ATRIBUIVEL  # matriz: campanha×dia não atribuível hoje
    res2 = juntar([custo()], [], [], REG, trafego_campanha_comprovado=True)
    assert linha(res2).sessoes.estado is EstadoMedida.AUSENTE  # sensor não viu nada no host da campanha


def test_dois_dominios_somam_sem_ultimo_escritor_vencer():
    rs = [receita_joinads("0.40", dominio="site.exemplo"), receita_joinads("0.60", dominio="outro.com.br")]
    res = juntar([custo()], [], rs, REG)
    assert linha(res).receita.valor == usd("1.00")


def test_moedas_misturadas_recusam():
    rs = [receita_joinads("1"), receita_joinads("1", dominio="x.exemplo", moeda=brl)]
    with pytest.raises(MoedasDiferentes):
        juntar([custo()], [], rs, REG)


def test_receita_com_id_em_duas_contas_nao_conta_duas_vezes():
    reg = RegistroCampanhas([CampanhaRegistrada("111", CAMP, "a", date(2026, 1, 1)),
                             CampanhaRegistrada("222", CAMP, "b", date(2026, 1, 1))])
    res = juntar([], [], [receita_joinads("1.00")], reg)
    assert res.linhas == () and [m for _, m in res.receita_nao_atribuida] == ["id_em_mais_de_uma_conta"]


# ---------------------------------------------------------------- tráfego: orgânico, bot, fuso

def test_organico_misturado_e_bot_nao_inflam_campanha():
    reg = RegistroCampanhas([CampanhaRegistrada(CONTA, "50", "tecno", date(2026, 1, 1), template=TemplateCampanha.NOME, hosts=(SITE,))])
    evs = [visita("https://site.exemplo/r/x/?utm_campaign=tecno&utm_source=google&utm_medium=cpc", "p1", ts(13))[0],
           visita("https://site.exemplo/r/x/?utm_campaign=tecno", "bot1", ts(13), bot=True)[0],
           visita("https://site.exemplo/r/x/", "o1", ts(13))[0],
           visita("https://site.exemplo/r/x/?utm_source=newsletter", "o2", ts(13))[0]]
    res = juntar([custo(camp="50")], evs, [], reg, **COMPROVADO)
    assert linha(res, camp="50").sessoes.valor == 1
    c = res.cobertura
    assert (c.sessoes_total, c.sessoes_bot_excluidas, c.sessoes_resolvidas) == (3, 1, 1)
    assert c.fracao_sessoes_resolvidas == Fraction(1, 3)
    assert c.fracao_receita_com_chave is None and c.denominador_receita == "indisponivel"


def test_dia_da_sessao_no_fuso_de_sao_paulo():
    reg = RegistroCampanhas([CampanhaRegistrada(CONTA, "50", "tecno", date(2026, 1, 1), template=TemplateCampanha.NOME, hosts=(SITE,))])
    # 02:30 UTC de 11/10 = 23:30 de 10/10 em São Paulo
    ev = visita("https://site.exemplo/r/x/?utm_campaign=tecno", "n", ts(2, 30, dia=DIA + timedelta(days=1)))[0]
    res = juntar([custo(camp="50")], [ev], [], reg, **COMPROVADO)
    assert linha(res, camp="50", dia=DIA).sessoes.valor == 1


def test_ts_sem_fuso_recusa():
    ev = EventoSensorReady("s", "p", datetime(2026, 10, 10, 13), UtmSessao())
    with pytest.raises(ValueError):
        juntar([], [ev], [], REG)


def test_cobertura_sem_sessoes_e_none_nao_zero():
    res = juntar([custo()], [], [], REG)
    assert res.cobertura.fracao_sessoes_resolvidas is None
    assert res.cobertura.fracao_sessoes_pagas_resolvidas is None


# ---------------------------------------------------------------- recusa de grão

@pytest.mark.parametrize("grao,tempo", [
    (Grao.SESSAO, GraoTempo.DIA), (Grao.CLIQUE, GraoTempo.DIA), (Grao.GRUPO_ANUNCIO, GraoTempo.DIA),
    (Grao.KEYWORD, GraoTempo.DIA), (Grao.TERMO_BUSCA, GraoTempo.DIA), (Grao.CAMPANHA, GraoTempo.HORA),
    (Grao.ANUNCIO, GraoTempo.DIA),
])
def test_junção_recusa_grao_mais_fino(grao, tempo):
    with pytest.raises(GraoNaoSuportado) as e:
        juntar([custo()], [], [receita_joinads("1")], REG, grao=grao, tempo=tempo)
    assert any(g is Grao.CAMPANHA for g, _, _ in e.value.suportados)


def test_pedir_receita_por_sessao_e_erro_tipado_nao_numero():
    ev, _ = visita(clique_ads(), "s", ts(13))
    res = juntar([custo()], [ev], [receita_joinads("3.40")], REG)
    with pytest.raises(GraoNaoSuportado):
        receita_por_sessao(res, ev)


def test_recibo_json_estavel_sem_float():
    ev, _ = visita(clique_ads(), "s", ts(13))
    out = para_json(juntar([custo()], [ev], [receita_joinads("3.40")], REG,
                                        receitas_dominio=[ReceitaDominioDia(DIA, "site.exemplo", usd("3.50"), disponivel_em=AS_OF)]))
    texto = json.dumps(out, sort_keys=True)
    assert "e-" not in texto and json.loads(texto) == out
    assert out["cobertura"]["fracao_receita_com_chave"] == "34/35"
    assert out["linhas"][0]["sessoes"]["estado"] == "nao_atribuivel"
