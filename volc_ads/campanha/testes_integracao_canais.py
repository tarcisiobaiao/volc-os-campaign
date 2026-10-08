"""Integração dos quatro canais: JSON ⇄ configuração, vocabulário, perfil, plano.

O que cada canal decide continua testado no arquivo do canal. Aqui fica o que
ATRAVESSA os canais: a forma JSON (a mesma régua para os quatro), o esquema
que a tela lê, os nomes de estratégia do brief, as faixas de id temporário,
as automações que a tela mostra, o perfil e a projeção do plano.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from .. import automacoes
from . import (
    comum,
    config_json,
    demand_gen,
    demand_gen_config as dgc,
    demand_gen_ops,
    display,
    display_config as dc,
    display_ops,
    perfil,
    plano,
    pmax_config as pc,
    pmax_grafo,
    search_config as sc,
)
from .brief import (
    ESTRATEGIAS_DE_LANCE,
    ConfiguracaoDemandGen,
    ConfiguracaoPMax,
    ImagensPMax,
    RedeDePesquisa,
)
from . import testes_demand_gen as tdg
from . import testes_display as td

CID = "5478096539"


# ═══════════════════════════════════════════════════════════════════════════
# JSON → dataclass: a régua é a do PRÓPRIO dataclass
# ═══════════════════════════════════════════════════════════════════════════

SEARCH_MAX = {
    "lance": {"estrategia": "TARGET_IMPRESSION_SHARE", "local_impressao": "TOP_OF_PAGE",
              "fracao_impressao": 0.6, "teto_cpc": 1.2},
    "rede": {"google_search": True, "parceiros": False, "display_expansion": True},
    "anuncio": {"path1": "cursos", "path2": "senac",
                "fixacoes": [{"texto": "Cursos Senac", "posicao": "HEADLINE_1"}]},
    "programacao": [{"dia": "MONDAY", "inicio": "08:00", "fim": "12:00", "ajuste": 1.2}],
    "dispositivos": [{"dispositivo": "TABLET", "fator": 0}],
    "geo": {"tipo_positivo": "PRESENCE", "tipo_negativo": "PRESENCE", "locais": [1001773]},
    "inicio": "2030-01-01",
    "meta_de_conversao": {"categorias": [{"categoria": "PURCHASE", "origem": "WEBSITE", "lance": False}]},
}


def test_search_de_json_monta_os_aninhados_e_volta_igual():
    cfg = sc.de_json(SEARCH_MAX)
    assert isinstance(cfg.lance, sc.LanceSearch) and cfg.lance.fracao_micros == 600_000
    assert cfg.rede.display_expansion is True
    assert cfg.programacao[0].ajuste == 1.2
    assert cfg.geo.locais == (1001773,)
    assert sc.de_json(config_json.para_json(cfg)) == cfg


def test_display_de_dict_e_inverso_e_julga_tipo():
    cfg = td._cfg_maxima(lance=dc.LanceDisplay("TARGET_SPEND", teto_cpc=0.3))
    assert dc.ConfiguracaoDisplay.de_dict(cfg.para_json()) == cfg
    with pytest.raises(config_json.ConfiguracaoInvalida) as e:
        dc.de_json({"frequencia": [{"impressoes": "3"}]})
    assert e.value.caminho == "configuracao_display.frequencia[0].impressoes"


@pytest.mark.parametrize("dados, caminho", [
    ({"lancee": {}}, "configuracao_search.lancee"),
    ({"lance": {"estrategia": "MANUAL_CPC", "x": 1}}, "configuracao_search.lance.x"),
    ({"programacao": [{"dia": "MONDAY", "inicio": "08:00", "fim": "09:00", "ajusta": 1}]},
     "configuracao_search.programacao[0].ajusta"),
])
def test_chave_desconhecida_e_erro_com_o_caminho(dados, caminho):
    with pytest.raises(config_json.ConfiguracaoInvalida) as e:
        sc.de_json(dados)
    assert e.value.caminho == caminho
    assert "desconhecido" in e.value.mensagem


@pytest.mark.parametrize("dados, caminho", [
    ({"rede": {"google_search": True, "parceiros": 0, "display_expansion": False}},
     "configuracao_search.rede.parceiros"),
    ({"lance": {"estrategia": "TARGET_SPEND", "teto_cpc": "1.0"}},
     "configuracao_search.lance.teto_cpc"),
    ({"geo": {"tipo_positivo": "PRESENCE", "tipo_negativo": "PRESENCE", "locais": [True]}},
     "configuracao_search.geo.locais[0]"),
])
def test_tipo_errado_nao_e_coagido(dados, caminho):
    with pytest.raises(config_json.ConfiguracaoInvalida) as e:
        sc.de_json(dados)
    assert e.value.caminho == caminho


def test_combinacao_recusada_pelo_post_init_vira_erro_no_objeto():
    with pytest.raises(config_json.ConfiguracaoInvalida) as e:
        sc.de_json({"lance": {"estrategia": "TARGET_IMPRESSION_SHARE"}})
    assert e.value.caminho == "configuracao_search.lance"
    assert "TARGET_IMPRESSION_SHARE exige" in e.value.mensagem


def _base_dg():
    return ConfiguracaoDemandGen(upgraded_targeting=False, controles_de_canal=None,
                                 audiencias=None, intencoes=None,
                                 exclusoes_de_audiencia=None)


def test_demand_gen_json_so_aceita_a_parte_v25_e_preserva_a_base():
    cfg = dgc.de_json({"formato": "VIDEO_RESPONSIVO",
                       "video": {"youtube_ids": ["M7lc1UVf-VE"]},
                       "automacoes": {"GENERATE_SHORTER_YOUTUBE_VIDEOS": "OPTED_IN"},
                       "lance": {"estrategia": "TARGET_CPC", "target_cpc": 0.5}}, _base_dg())
    assert isinstance(cfg, dgc.ConfiguracaoDemandGenV25)
    assert cfg.upgraded_targeting is False
    assert cfg.automacoes == (("GENERATE_SHORTER_YOUTUBE_VIDEOS", "OPTED_IN"),)
    with pytest.raises(config_json.ConfiguracaoInvalida) as e:
        dgc.de_json({"upgraded_targeting": True}, _base_dg())
    assert e.value.caminho == "configuracao_demand_gen.upgraded_targeting"


def test_carrossel_por_json_e_recusado_com_o_motivo():
    with pytest.raises(config_json.ConfiguracaoInvalida) as e:
        dgc.de_json({"formato": "CARROSSEL", "carrossel": {"cartoes": [
            {"headline": "a", "marketing": {"nome": "x"}}]}}, _base_dg())
    assert e.value.caminho.endswith("cartoes[0].marketing")
    assert "asset JÁ NA CONTA" in e.value.mensagem


def test_pmax_json_resolve_imagens_do_grupo_pelo_resolvedor():
    base = ConfiguracaoPMax(brand_guidelines_enabled=False, mensuracao=None,
                            sinais=(), negativas=())
    vistos = []

    def resolver(valor, caminho):
        vistos.append((caminho, len(valor)))
        return ImagensPMax()

    cfg = pc.de_json({"grupos_adicionais": [{
        "nome": "g2", "url_final": "https://x.com/a",
        "textos": {"headlines": ["a"], "long_headlines": ["b"], "descriptions": ["c"]},
        "imagens": [{}, {}], "sinais": [],
        "opcoes_de_url": {"parametros_personalizados": [["tema", "a"]]}}],
        "automacoes_optadas": ["AUTOMATED_VIDEO_CRAWL"]}, base, imagens_do_grupo=resolver)
    assert vistos == [("configuracao_pmax.grupos_adicionais[0].imagens", 2)]
    assert cfg.grupos_adicionais[0].opcoes_de_url.parametros_personalizados == (("tema", "a"),)
    assert cfg.grupos_adicionais[0].sinais == ()
    with pytest.raises(config_json.ConfiguracaoInvalida, match="portão"):
        pc.de_json({"grupos_adicionais": [{
            "nome": "g", "url_final": "https://x", "imagens": [], "sinais": None,
            "textos": {"headlines": [], "long_headlines": [], "descriptions": []}}]}, base)


# ═══════════════════════════════════════════════════════════════════════════
# O esquema que a tela lê
# ═══════════════════════════════════════════════════════════════════════════


def test_esquemas_carregam_enums_limites_e_defaults_do_motor():
    s = sc.esquema_json()
    lance = s["$defs"]["LanceSearch"]["properties"]
    assert lance["estrategia"]["enum"] == list(sc.ESTRATEGIAS)
    assert s["$defs"]["AnuncioSearch"]["properties"]["path1"]["maxLength"] == sc.MAX_PATH
    assert s["additionalProperties"] is False

    d = dc.esquema_json()
    exc = d["$defs"]["ExclusoesDisplay"]["properties"]
    assert exc["rotulos_de_conteudo"]["default"] == list(dc.ROTULOS_PADRAO)
    assert exc["rotulos_de_conteudo"]["items"]["enum"] == list(dc.ROTULOS_ACEITOS)
    assert exc["excluir_todos_os_apps"]["default"] is True

    g = dgc.esquema_json()
    assert set(g["properties"]) == set(dgc.campos_v25())
    assert "upgraded_targeting" not in g["properties"]
    assert g["properties"]["formato"]["enum"] == list(dgc.FORMATOS)

    p = pc.esquema_json(esquema_de_imagens={"type": "array", "items": {"title": "envelope"}})
    assert set(p["properties"]) == set(pc.campos_v25())
    imagens = p["$defs"]["AssetGroupPMax"]["properties"]["imagens"]
    assert imagens["items"] == {"title": "envelope"}
    json.dumps(p)  # serializável de ponta a ponta


# ═══════════════════════════════════════════════════════════════════════════
# brief: nomes de estratégia e rede
# ═══════════════════════════════════════════════════════════════════════════


def test_brief_conhece_as_estrategias_pelo_nome_da_api_e_sem_apelido():
    for nome in ("TARGET_SPEND", "TARGET_IMPRESSION_SHARE", "MANUAL_CPM", "TARGET_CPC"):
        assert nome in ESTRATEGIAS_DE_LANCE
    assert "MAXIMIZE_CLICKS" not in ESTRATEGIAS_DE_LANCE
    todas = set(sc.ESTRATEGIAS) | set(dc.ESTRATEGIAS) | set(dgc.ESTRATEGIAS)
    assert todas <= set(ESTRATEGIAS_DE_LANCE)


def test_rede_de_pesquisa_aceita_expansao_declarada_e_recusa_bool_falso():
    assert RedeDePesquisa(True, False, True).display_expansion is True
    with pytest.raises(TypeError):
        RedeDePesquisa(True, 0, False)


def test_demand_gen_pelo_brief_so_monta_maxconv(monkeypatch):
    """Sem `LanceDemandGen`, TARGET_SPEND no brief viraria MaxConv em silêncio."""
    monkeypatch.setattr(demand_gen, "cliente", lambda _l: tdg._cliente_sem_rede())
    _, r = demand_gen.construir(tdg.CID, tdg._brief(estrategia_lance="TARGET_SPEND"),
                                login_customer_id=tdg.MCC)
    assert "estrategia_lance" in {a.campo for a in r.erros}


def test_display_monta_target_spend_pelo_brief(monkeypatch):
    monkeypatch.setattr(display, "cliente", lambda _l: td._cliente_sem_rede())
    ops, r = display.construir(td.CID, td._brief(estrategia_lance="TARGET_SPEND"),
                               login_customer_id="x")
    assert r.ok, r.resumo()
    camp = [o for o in ops if o._pb.WhichOneof("operation") == "campaign_operation"][0]
    assert camp.campaign_operation.create._pb.WhichOneof("campaign_bidding_strategy") == "target_spend"


# ═══════════════════════════════════════════════════════════════════════════
# comum: correções na origem e a tabela de faixas
# ═══════════════════════════════════════════════════════════════════════════


def test_comum_emite_target_cpa_para_display_com_meta_e_maxconv_vazio_sem():
    c = td._cliente_sem_rede()
    com = comum.op_campanha(c, CID, td._brief(tcpa=2.0), "n", "DISPLAY").campaign_operation.create
    assert com._pb.WhichOneof("campaign_bidding_strategy") == "target_cpa"
    assert com.target_cpa.target_cpa_micros == 2_000_000
    sem = comum.op_campanha(c, CID, td._brief(), "n", "DISPLAY").campaign_operation.create
    assert sem._pb.WhichOneof("campaign_bidding_strategy") == "maximize_conversions"
    assert sem.maximize_conversions._pb.ListFields() == []


def test_faixas_por_canal_batem_com_as_constantes_dos_modulos():
    f = {canal: {nome: (a, b) for nome, a, b in faixas}
         for canal, faixas in comum.FAIXAS_POR_CANAL.items()}
    assert f["SEARCH"]["meta_personalizada"][0] == sc.T_META_PERSONALIZADA
    assert f["DISPLAY"]["lista_de_exclusao"][0] == display_ops.T_LISTA_EXCLUSAO
    assert f["DISPLAY"]["video"] == (display_ops.T_VIDEO_BASE,
                                     display_ops.T_VIDEO_BASE - dc.VIDEOS_MAX + 1)
    assert f["DEMAND_GEN"]["asset_nao_imagem"][0] == demand_gen_ops.T_ASSET_DG_BASE
    assert f["DEMAND_GEN"]["lookalike"][0] == demand_gen_ops.T_USER_LIST_BASE
    assert f["DEMAND_GEN"]["audiencia"][0] == demand_gen_ops.T_AUDIENCIA_BASE
    assert f["PERFORMANCE_MAX"]["video"] == (pmax_grafo.T_VIDEO_BASE,
                                             pmax_grafo.T_VIDEO_BASE - pmax_grafo.T_VIDEO_MAX + 1)
    assert f["PERFORMANCE_MAX"]["shared_set"][0] == pmax_grafo.T_SHARED_SET_BASE
    for faixas in comum.FAIXAS_POR_CANAL.values():
        intervalos = sorted((b, a) for _n, a, b in faixas)
        for (b1, a1), (b2, a2) in zip(intervalos, intervalos[1:]):
            assert a1 < b2, "faixas do mesmo canal se sobrepõem"
        assert all(a <= comum.T_ASSET_GROUP_BASE - comum.T_ASSET_GROUP_MAX for _n, a, _b in faixas)


# ═══════════════════════════════════════════════════════════════════════════
# automações: uma fonte para a tela e para os builders
# ═══════════════════════════════════════════════════════════════════════════


def test_automacoes_espelham_os_builders_e_todas_tem_frase():
    assert automacoes.AUTOMACOES_PMAX == pc.AUTOMACOES_PMAX_V25
    assert dict(automacoes.AUTOMACOES_DEMAND_GEN_POR_FORMATO) == dict(dgc.AUTOMACOES_POR_FORMATO)
    for canal in ("DEMAND_GEN", "PERFORMANCE_MAX"):
        for nome in automacoes.recusadas(canal):
            assert automacoes.POR_QUE_RECUSADA.get(nome), nome
    assert automacoes.recusadas("DEMAND_GEN", formato="VIDEO_RESPONSIVO") == \
        automacoes.AUTOMACOES_DEMAND_GEN_VIDEO_RECUSADAS
    assert dgc.POR_QUE_RECUSADA_VIDEO["GENERATE_LANDING_PAGE_TEXT"] == \
        automacoes.POR_QUE_RECUSADA["GENERATE_LANDING_PAGE_TEXT"]


# ═══════════════════════════════════════════════════════════════════════════
# perfil
# ═══════════════════════════════════════════════════════════════════════════


def test_perfil_declara_lances_pelo_brief_como_subconjunto_e_campos_novos():
    for p in perfil.PERFIS.values():
        assert set(p.lances_pelo_brief) <= set(p.lances_permitidos), p.canal
    assert perfil.SEARCH.lances_pelo_brief is sc.ESTRATEGIAS_PELO_BRIEF
    assert perfil.DISPLAY.lances_pelo_brief is dc.ESTRATEGIAS_PELO_BRIEF
    assert perfil.DEMAND_GEN.lances_pelo_brief is dgc.ESTRATEGIAS_PELO_BRIEF
    assert "video_youtube" in perfil.DEMAND_GEN.recursos_criativos
    assert "configuracao.lance" in perfil.SEARCH.campos_operados
    assert "pmax.grupos_adicionais" in perfil.PERFORMANCE_MAX.campos_operados
    assert perfil.DEMAND_GEN.configuracao_no_brief == "demand_gen"


def test_configuracao_de_demand_gen_entra_no_brief_e_duas_fontes_recusam():
    nova = tdg._v25(segmentacao_otimizada=True)
    # sem configuração no brief: entra
    b = tdg._brief(demand_gen=None, keywords=["saque anual"])
    b2, resto = perfil._configuracao_no_brief(perfil.DEMAND_GEN, b, {"configuracao": nova})
    assert b2.demand_gen == nova and "configuracao" not in resto
    # promoção legítima: o brief traz a BASE igual, a V25 vem por cima
    base = ConfiguracaoDemandGen(**{f.name: getattr(nova, f.name)
                                    for f in dataclasses.fields(ConfiguracaoDemandGen)})
    b3, _ = perfil._configuracao_no_brief(perfil.DEMAND_GEN, tdg._brief(demand_gen=base),
                                          {"configuracao": nova})
    assert b3.demand_gen == nova
    # duas V25 diferentes: recusa
    with pytest.raises(perfil.OpcaoIndisponivel, match="Duas fontes"):
        perfil._configuracao_no_brief(perfil.DEMAND_GEN, tdg._brief(demand_gen=tdg._v25()),
                                      {"configuracao": nova})
    _, so_none = perfil._configuracao_no_brief(perfil.DEMAND_GEN, b, {"configuracao": None})
    assert so_none == {}


def test_preparar_repassa_a_configuracao_ao_perfil(monkeypatch):
    from .. import subir

    vistos = {}

    def montar(canal, cid, brief, **kw):
        vistos.update(kw)
        raise RuntimeError("parou aqui")

    monkeypatch.setattr(subir.perfil, "montar", montar)
    cfg = sc.ConfiguracaoSearch()
    p = subir.preparar(CID, object(), login_customer_id="1", canal="SEARCH", configuracao=cfg)
    assert vistos["configuracao"] is cfg
    assert "construir() falhou" in p.recusa_local


# ═══════════════════════════════════════════════════════════════════════════
# plano: códigos, critérios, formatos e lance
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("campo, motivo, codigo", [
    ("lance.teto_cpc", "x", plano.CONFIGURACAO_INVALIDA),
    ("programacao.ajuste", "x", plano.CONFIGURACAO_INVALIDA),
    ("segmentacao.placements", "x", plano.CONFIGURACAO_INVALIDA),
    ("exclusoes.rotulos_de_conteudo", "x", plano.CONFIGURACAO_INVALIDA),
    ("ai_max.listas_de_marca", "x", plano.CONFIGURACAO_INVALIDA),
    ("rede", "divergente", plano.CONFIGURACAO_INVALIDA),
    ("rede", "decisão obrigatória ausente", plano.CONFIGURACAO_AUSENTE),
    ("tcpa", "x", plano.LANCE_NAO_PERMITIDO),
    ("geografia", "x", plano.BLOQUEIO_NAO_CLASSIFICADO),
])
def test_configuracao_invalida_tem_codigo_proprio(campo, motivo, codigo):
    assert plano.classificar(campo, motivo) == codigo
    assert codigo in plano.CODIGOS


def _criterio(**kw):
    from google.ads.googleads.v25.resources.types.campaign_criterion import CampaignCriterion

    return CampaignCriterion(**kw)


def test_plano_projeta_os_criterios_que_as_configuracoes_emitem():
    from google.ads.googleads.v25.common.types import criteria as cr
    from google.ads.googleads.v25.enums.types import day_of_week, device, minute_of_hour

    casos = [
        (_criterio(ad_schedule=cr.AdScheduleInfo(
            day_of_week=day_of_week.DayOfWeekEnum.DayOfWeek.MONDAY, start_hour=8,
            start_minute=minute_of_hour.MinuteOfHourEnum.MinuteOfHour.ZERO, end_hour=12,
            end_minute=minute_of_hour.MinuteOfHourEnum.MinuteOfHour.THIRTY)),
         "ad_schedule", "MONDAY 08:00-12:30"),
        (_criterio(device=cr.DeviceInfo(type_=device.DeviceEnum.Device.TABLET), bid_modifier=0),
         "device", "TABLET bid_modifier=0.0"),
        (_criterio(brand_list=cr.BrandListInfo(shared_set="customers/1/sharedSets/2"), negative=True),
         "brand_list", "customers/1/sharedSets/2"),
        (_criterio(placement=cr.PlacementInfo(url="g1.globo.com")), "placement", "g1.globo.com"),
        (_criterio(topic=cr.TopicInfo(topic_constant="topicConstants/369")), "topic", "topicConstants/369"),
        (_criterio(user_interest=cr.UserInterestInfo(user_interest_category="customers/1/userInterests/92000")),
         "user_interest", "customers/1/userInterests/92000"),
        (_criterio(mobile_application=cr.MobileApplicationInfo(app_id="2-com.x.y")),
         "mobile_application", "2-com.x.y"),
    ]
    for criterio, tipo, valor in casos:
        p = plano._criterio_de(criterio, "campanha")
        assert (p.tipo, p.valor) == (tipo, valor)


def test_plano_le_video_responsivo_e_carrossel_de_demand_gen():
    from google.ads.googleads.v25.common.types import ad_asset, ad_type_infos as ati
    from google.ads.googleads.v25.resources.types.ad import Ad
    from google.ads.googleads.v25.resources.types.ad_group_ad import AdGroupAd

    video = AdGroupAd(ad=Ad(final_urls=["https://x.com/"],
                            demand_gen_video_responsive_ad=ati.DemandGenVideoResponsiveAdInfo(
        headlines=[ad_asset.AdTextAsset(text="H1")],
        long_headlines=[ad_asset.AdTextAsset(text="LH")],
        descriptions=[ad_asset.AdTextAsset(text="D1")],
        videos=[ad_asset.AdVideoAsset(asset="customers/1/assets/-500")],
        logo_images=[ad_asset.AdImageAsset(asset="customers/1/assets/-200")])))
    a = plano._anuncio_de(video)
    assert a.tipo == "demand_gen_video_responsive_ad"
    assert (a.headlines, a.long_headlines, a.descriptions) == (("H1",), ("LH",), ("D1",))
    assert {x.papel for x in a.assets} == {"YOUTUBE_VIDEO", "LOGO"}

    carrossel = AdGroupAd(ad=Ad(demand_gen_carousel_ad=ati.DemandGenCarouselAdInfo(
        headline=ad_asset.AdTextAsset(text="Título"),
        description=ad_asset.AdTextAsset(text="Descrição"),
        logo_image=ad_asset.AdImageAsset(asset="customers/1/assets/9"),
        carousel_cards=[ad_asset.AdDemandGenCarouselCardAsset(asset="customers/1/assets/7")])))
    c = plano._anuncio_de(carrossel)
    assert c.tipo == "demand_gen_carousel_ad"
    assert (c.headlines, c.descriptions) == (("Título",), ("Descrição",))
    assert {x.papel for x in c.assets} == {"DEMAND_GEN_CAROUSEL_CARD", "LOGO"}


def test_plano_le_a_meta_de_target_cpa_avulso(monkeypatch):
    monkeypatch.setattr(display, "cliente", lambda _l: td._cliente_sem_rede())
    ops, r = display.construir(td.CID, td._brief(tcpa=2.0), login_customer_id="x")
    assert r.ok
    p = plano.projetar(canal="DISPLAY", customer_id=td.CID, login_customer_id="x",
                       operacoes=ops, resultado=r,
                       prontidao=plano.Prontidao(monta=True, pode_provar=True, pode_criar=True))
    assert p.orcamento.estrategia_lance == "TARGET_CPA"
    assert p.orcamento.tcpa_micros == 2_000_000
