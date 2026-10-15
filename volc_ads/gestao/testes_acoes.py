"""Cada ação contra o proto v25 REAL: operação, leitura do "antes", conferência e reverso.

Nada de dublê de proto. O `get_type` é o do SDK 33.0.0 (v25.2) sem credencial,
e o "antes" é interpretado a partir de `GoogleAdsRow` de verdade — é assim que
um nome de campo errado aparece aqui e não na conta.
"""
from __future__ import annotations

import pytest
from google.ads.googleads.client import GoogleAdsClient

from volc_ads.gads import catalogo
from volc_ads.gestao import acoes as A
from volc_ads.gestao.acoes import AcaoRecusada
from volc_ads.gestao.valor import ValorMonetario


def OP(micros):
    """Valor digitado pelo operador — a origem que as ações de verba/lance exigem."""
    return ValorMonetario(micros, "operador", "operador:teste/operador@2026-10-15T00:00:00+00:00",
                          "valor digitado no teste")

CID = "5478096539"
CAMP = 24278665189
AG = 199085896206


def _get_type():
    c = GoogleAdsClient.__new__(GoogleAdsClient)
    c.version = "v25"
    c.use_proto_plus = True
    return c.get_type


GT = _get_type()


def _ops(acao, temp=None):
    contador = iter(range(-1, -100, -1))
    ops = acao.operacoes(GT, CID, temp or (lambda: next(contador)))
    for op in ops:  # serializa: campo inexistente no proto quebraria aqui
        type(op).serialize(op)
    return ops


def _qual(op):
    return op._pb.WhichOneof("operation")


def _linha(**campos):
    r = GT("GoogleAdsRow")
    for caminho, valor in campos.items():
        alvo = r
        partes = caminho.split("__")
        for p in partes[:-1]:
            alvo = getattr(alvo, p)
        setattr(alvo, partes[-1], valor)
    return r


# ── 1. status ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("nivel, ident, campo_op, rn", [
    ("campanha", CAMP, "campaign_operation", f"customers/{CID}/campaigns/{CAMP}"),
    ("grupo", AG, "ad_group_operation", f"customers/{CID}/adGroups/{AG}"),
    ("anuncio", f"{AG}~826462028814", "ad_group_ad_operation",
     f"customers/{CID}/adGroupAds/{AG}~826462028814"),
    ("asset_group", 6543210, "asset_group_operation", f"customers/{CID}/assetGroups/6543210"),
])
def teste_status_vira_update_com_mascara_so_no_status(nivel, ident, campo_op, rn):
    (op,) = _ops(A.AlterarStatus(nivel, ident, "PAUSED"))
    assert _qual(op) == campo_op
    sub = getattr(op, campo_op)
    assert sub.update.resource_name == rn
    assert sub.update.status.name == "PAUSED"
    assert list(sub.update_mask.paths) == ["status"]


def teste_status_removed_nao_e_gestao():
    with pytest.raises(AcaoRecusada, match="REMOVED"):
        A.AlterarStatus("campanha", CAMP, "REMOVED")


def teste_anuncio_exige_grupo_e_anuncio():
    with pytest.raises(AcaoRecusada, match="ad_group_id"):
        A.AlterarStatus("anuncio", "826462028814", "PAUSED")


def teste_status_confere_estado():
    a = A.AlterarStatus("campanha", CAMP, "PAUSED")
    antes = a.interpretar_antes(([_linha(campaign__id=CAMP, campaign__status="ENABLED")],))
    assert antes == {"existe": True, "status": "ENABLED"}
    a.conferir(antes)
    assert a.reverso(antes) == (A.AlterarStatus("campanha", CAMP, "ENABLED"),)
    with pytest.raises(AcaoRecusada, match="já está"):
        a.conferir({"existe": True, "status": "PAUSED"})
    with pytest.raises(AcaoRecusada, match="REMOVED"):
        a.conferir({"existe": True, "status": "REMOVED"})
    with pytest.raises(AcaoRecusada, match="não existe"):
        a.conferir(a.interpretar_antes(([],)))


# ── 2. orçamento ────────────────────────────────────────────────────────────


def _antes_orcamento(**troca):
    a = A.AlterarOrcamento(CAMP, 15886629542, OP(35_000_000))
    linha = _linha(campaign__id=CAMP, campaign_budget__id=15886629542,
                   campaign_budget__amount_micros=30_000_000, campaign_budget__period="DAILY",
                   campaign_budget__explicitly_shared=troca.get("compartilhado", False),
                   campaign_budget__reference_count=troca.get("n", 1),
                   customer__currency_code="BRL")
    return a, a.interpretar_antes(([linha],))


def teste_orcamento_muda_so_amount_micros():
    a, antes = _antes_orcamento()
    (op,) = _ops(a)
    b = op.campaign_budget_operation
    assert b.update.resource_name == f"customers/{CID}/campaignBudgets/15886629542"
    assert b.update.amount_micros == 35_000_000
    assert list(b.update_mask.paths) == ["amount_micros"]
    assert antes["verba_diaria_micros"] == 30_000_000 and antes["total_micros"] is None
    a.conferir(antes)
    (rev,) = a.reverso(antes)
    assert rev.amount_micros == 30_000_000


def teste_orcamento_compartilhado_so_com_ciencia():
    a, antes = _antes_orcamento(compartilhado=True, n=3)
    with pytest.raises(AcaoRecusada, match="compartilhado por 3"):
        a.conferir(antes)
    A.AlterarOrcamento(CAMP, 15886629542, OP(35_000_000), compartilhado_ciente=True).conferir(antes)


def teste_orcamento_recusa_estado_divergente_e_periodo_total():
    a, antes = _antes_orcamento()
    with pytest.raises(AcaoRecusada, match="outro estado"):
        A.AlterarOrcamento(CAMP, 1, OP(35_000_000)).conferir(antes)
    with pytest.raises(AcaoRecusada, match="não diário"):
        a.conferir({**antes, "total_micros": 900_000_000, "periodo": "CUSTOM_PERIOD"})
    with pytest.raises(AcaoRecusada, match="já está"):
        A.AlterarOrcamento(CAMP, 15886629542, OP(30_000_000)).conferir(antes)


@pytest.mark.parametrize("valor", [0, -10_000, 35_000_001, 1.5, True])
def teste_orcamento_recusa_micros_invalidos(valor):
    with pytest.raises(AcaoRecusada):
        A.AlterarOrcamento(CAMP, 1, OP(valor))


# ── 3. alvo de lance ────────────────────────────────────────────────────────


def _antes_lance(estrategia="TARGET_SPEND", **campos):
    linha = _linha(campaign__id=CAMP, campaign__advertising_channel_type=campos.pop("canal", "SEARCH"),
                   campaign__bidding_strategy_type=estrategia, customer__currency_code="BRL",
                   **campos)
    return A.TrocarEstrategia(CAMP, "MANUAL_CPC").interpretar_antes(([linha],))


def teste_teto_de_cpc_do_maximizar_cliques_vai_no_target_spend():
    antes = _antes_lance(campaign__target_spend__cpc_bid_ceiling_micros=1_000_000)
    a = A.AlterarAlvoDeLance.do_estado(antes, "teto_cpc", OP(1_500_000))
    (op,) = _ops(a)
    c = op.campaign_operation
    assert c.update.target_spend.cpc_bid_ceiling_micros == 1_500_000
    assert c.update._pb.WhichOneof("campaign_bidding_strategy") == "target_spend"
    assert list(c.update_mask.paths) == ["target_spend.cpc_bid_ceiling_micros"]
    a.conferir(antes)
    assert a.reverso(antes)[0].valor == 1_000_000


@pytest.mark.parametrize("estrategia, alvo, valor, caminho", [
    ("MAXIMIZE_CONVERSIONS", "tcpa", 8_000_000, "maximize_conversions.target_cpa_micros"),
    ("MAXIMIZE_CONVERSION_VALUE", "troas", 3.5, "maximize_conversion_value.target_roas"),
    ("TARGET_CPA", "tcpa", 8_000_000, "target_cpa.target_cpa_micros"),
    ("TARGET_ROAS", "troas", 2.0, "target_roas.target_roas"),
])
def teste_alvo_vai_no_campo_da_estrategia(estrategia, alvo, valor, caminho):
    lance = valor if alvo == "troas" else OP(valor)
    (op,) = _ops(A.AlterarAlvoDeLance(CAMP, estrategia, alvo, lance))
    assert list(op.campaign_operation.update_mask.paths) == [caminho]
    grupo, campo = caminho.split(".")
    assert getattr(getattr(op.campaign_operation.update, grupo), campo) == valor


@pytest.mark.parametrize("estrategia, alvo", [
    ("MAXIMIZE_CONVERSIONS", "teto_cpc"),  # só em portfólio
    ("MANUAL_CPC", "tcpa"),
    ("TARGET_SPEND", "tcpa"),
])
def teste_alvo_sem_campo_na_estrategia_e_recusado(estrategia, alvo):
    with pytest.raises(AcaoRecusada, match="não tem alvo"):
        A.AlterarAlvoDeLance(CAMP, estrategia, alvo, OP(1_000_000))


def teste_alvo_nao_troca_estrategia_por_tras():
    a = A.AlterarAlvoDeLance(CAMP, "MAXIMIZE_CONVERSIONS", "tcpa", OP(8_000_000))
    with pytest.raises(AcaoRecusada, match="TrocarEstrategia"):
        a.conferir(_antes_lance("TARGET_SPEND"))
    with pytest.raises(AcaoRecusada, match="portfólio"):
        A.AlterarAlvoDeLance.do_estado(
            _antes_lance("TARGET_SPEND", campaign__bidding_strategy=
                         f"customers/{CID}/biddingStrategies/9"), "teto_cpc", OP(1_000_000))


def teste_alvo_zero_limpa_so_onde_e_opcional():
    A.AlterarAlvoDeLance(CAMP, "MAXIMIZE_CONVERSIONS", "tcpa", OP(0))
    with pytest.raises(AcaoRecusada):
        A.AlterarAlvoDeLance(CAMP, "TARGET_CPA", "tcpa", OP(0))
    with pytest.raises(AcaoRecusada):
        A.AlterarAlvoDeLance(CAMP, "TARGET_ROAS", "troas", 0)


# ── 4. troca de estratégia ──────────────────────────────────────────────────


@pytest.mark.parametrize("acao, oneof, caminho", [
    (A.TrocarEstrategia(CAMP, "MAXIMIZE_CONVERSIONS"), "maximize_conversions",
     "maximize_conversions.target_cpa_micros"),
    (A.TrocarEstrategia(CAMP, "MAXIMIZE_CONVERSIONS", tcpa=OP(8_000_000)),
     "maximize_conversions", "maximize_conversions.target_cpa_micros"),
    (A.TrocarEstrategia(CAMP, "MAXIMIZE_CONVERSION_VALUE", troas=4.0),
     "maximize_conversion_value", "maximize_conversion_value.target_roas"),
    (A.TrocarEstrategia(CAMP, "MANUAL_CPC"), "manual_cpc", "manual_cpc.enhanced_cpc_enabled"),
    (A.TrocarEstrategia(CAMP, "TARGET_SPEND"), "target_spend", "target_spend.cpc_bid_ceiling_micros"),
    (A.TrocarEstrategia(CAMP, "PORTFOLIO", portfolio=f"customers/{CID}/biddingStrategies/77"),
     "bidding_strategy", "bidding_strategy"),
])
def teste_troca_marca_o_oneof_mesmo_sem_alvo(acao, oneof, caminho):
    """Submensagem vazia não registra presença; sem `SetInParent` a troca some."""
    (op,) = _ops(acao)
    assert op.campaign_operation.update._pb.WhichOneof("campaign_bidding_strategy") == oneof
    assert list(op.campaign_operation.update_mask.paths) == [caminho]


def teste_troca_recusa_parametro_de_outra_estrategia():
    with pytest.raises(AcaoRecusada, match="tcpa_micros"):
        A.TrocarEstrategia(CAMP, "TARGET_SPEND", tcpa=OP(8_000_000))
    with pytest.raises(AcaoRecusada, match="não é escrita"):
        A.TrocarEstrategia(CAMP, "TARGET_CPA")


def teste_troca_respeita_o_canal():
    a = A.TrocarEstrategia(CAMP, "MANUAL_CPC")
    with pytest.raises(AcaoRecusada, match="PERFORMANCE_MAX não aceita"):
        a.conferir(_antes_lance("MAXIMIZE_CONVERSIONS", canal="PERFORMANCE_MAX"))
    with pytest.raises(AcaoRecusada, match="já está"):
        A.TrocarEstrategia(CAMP, "TARGET_SPEND").conferir(_antes_lance("TARGET_SPEND"))


def teste_reverso_da_troca_volta_estrategia_e_alvo_anteriores():
    antes = _antes_lance(campaign__target_spend__cpc_bid_ceiling_micros=1_000_000)
    (rev,) = A.TrocarEstrategia(CAMP, "MAXIMIZE_CONVERSIONS", tcpa=OP(8_000_000)).reverso(antes)
    assert (rev.nova, rev.teto_cpc_micros, rev.tcpa_micros) == ("TARGET_SPEND", 1_000_000, 0)
    port = f"customers/{CID}/biddingStrategies/9"
    (rev,) = A.TrocarEstrategia(CAMP, "MANUAL_CPC").reverso(
        _antes_lance("TARGET_SPEND", campaign__bidding_strategy=port))
    assert (rev.nova, rev.portfolio) == ("PORTFOLIO", port)
    assert A.TrocarEstrategia(CAMP, "MANUAL_CPC").reverso(_antes_lance("TARGET_CPA")) == ()


# ── 5. negativas e listas ───────────────────────────────────────────────────


def teste_negativa_de_campanha_e_de_grupo():
    t = (A.Termo("gratis"), A.Termo("curso senac gratuito", "EXACT"))
    ops = _ops(A.AdicionarNegativas("campanha", CAMP, t))
    assert [_qual(o) for o in ops] == ["campaign_criterion_operation"] * 2
    c = ops[1].campaign_criterion_operation.create
    assert (c.campaign, c.negative, c.keyword.text, c.keyword.match_type.name) == (
        f"customers/{CID}/campaigns/{CAMP}", True, "curso senac gratuito", "EXACT")
    (op,) = _ops(A.AdicionarNegativas("grupo", AG, (A.Termo("download pdf", "BROAD"),)))
    g = op.ad_group_criterion_operation.create
    assert (g.ad_group, g.negative, g.keyword.match_type.name) == (
        f"customers/{CID}/adGroups/{AG}", True, "BROAD")


@pytest.mark.parametrize("texto, motivo", [
    ("", "vazia"), ("a" * 81, "80"), ("um dois três quatro cinco seis sete oito nove dez onze", "10"),
    ("curso grátis!", "caractere"), ("vaga, emprego", "caractere"),
])
def teste_termo_invalido_e_recusado_local(texto, motivo):
    with pytest.raises(AcaoRecusada, match=motivo):
        A.Termo(texto)


def teste_negativa_duplicada_e_recusada_sem_diferenciar_caixa():
    a = A.AdicionarNegativas("campanha", CAMP, (A.Termo("Gratis"),))
    linha = _linha(campaign__id=CAMP, campaign_criterion__keyword__text="gratis",
                   campaign_criterion__keyword__match_type="PHRASE")
    antes = a.interpretar_antes(([linha],))
    with pytest.raises(AcaoRecusada, match="já existente"):
        a.conferir(antes)
    with pytest.raises(AcaoRecusada, match="repetido"):
        A.AdicionarNegativas("campanha", CAMP, (A.Termo("x"), A.Termo("X")))


def teste_lista_compartilhada_liga_itens_e_vinculo_pelo_id_temporario():
    a = A.CriarListaCompartilhada("NEGATIVE_KEYWORDS", "Lista  VOLC", (A.Termo("emprego"),
                                  A.Termo("vagas", "EXACT")), (CAMP,))
    ops = _ops(a)
    assert [_qual(o) for o in ops] == ["shared_set_operation", "shared_criterion_operation",
                                       "shared_criterion_operation", "campaign_shared_set_operation"]
    rn = f"customers/{CID}/sharedSets/-1"
    s = ops[0].shared_set_operation.create
    assert (s.resource_name, s.name, s.type_.name) == (rn, "Lista VOLC", "NEGATIVE_KEYWORDS")
    assert all(o.shared_criterion_operation.create.shared_set == rn for o in ops[1:3])
    v = ops[3].campaign_shared_set_operation.create
    assert (v.campaign, v.shared_set) == (f"customers/{CID}/campaigns/{CAMP}", rn)
    with pytest.raises(AcaoRecusada, match="AdicionarNaLista"):
        a.conferir({"listas_com_mesmo_nome": [42]})


def teste_lista_de_placements_so_leva_placement():
    ops = _ops(A.CriarListaCompartilhada("NEGATIVE_PLACEMENTS", "P", (
        A.Placement("site", "https://www.Exemplo.com.br/"), A.Placement("youtube_canal", "UC" + "a" * 22))))
    assert ops[1].shared_criterion_operation.create.placement.url == "exemplo.com.br"
    assert ops[2].shared_criterion_operation.create.youtube_channel.channel_id == "UC" + "a" * 22
    with pytest.raises(AcaoRecusada, match="só leva"):
        A.CriarListaCompartilhada("NEGATIVE_PLACEMENTS", "P", (A.Termo("x"),))
    with pytest.raises(AcaoRecusada, match="não gerido"):
        A.CriarListaCompartilhada("BRANDS", "P", (A.Termo("x"),))


def teste_adicionar_e_anexar_lista_existente():
    ops = _ops(A.AdicionarNaLista(55, "NEGATIVE_KEYWORDS", (A.Termo("x"),)))
    assert ops[0].shared_criterion_operation.create.shared_set == f"customers/{CID}/sharedSets/55"
    a = A.AnexarLista(55, (CAMP, 1))
    assert [o.campaign_shared_set_operation.create.campaign for o in _ops(a)] == [
        f"customers/{CID}/campaigns/{CAMP}", f"customers/{CID}/campaigns/1"]
    with pytest.raises(AcaoRecusada, match="já anexada"):
        a.conferir({"campanhas_vinculadas": [1]})
    lista = A.AdicionarNaLista(55, "NEGATIVE_KEYWORDS", (A.Termo("x"),))
    with pytest.raises(AcaoRecusada, match="é NEGATIVE_PLACEMENTS"):
        lista.conferir({"existe": True, "status": "ENABLED", "tipo": "NEGATIVE_PLACEMENTS"})


# ── 6–7. exclusões ──────────────────────────────────────────────────────────


def teste_placement_na_campanha_e_na_conta():
    itens = (A.Placement("site", "exemplo-ruim.com.br"), A.Placement("app", "2-com.exemplo.jogo"),
             A.Placement("youtube_video", "dQw4w9WgXcQ"))
    ops = _ops(A.ExcluirPlacements("campanha", itens, campaign_id=CAMP))
    c = [o.campaign_criterion_operation.create for o in ops]
    assert all(x.negative for x in c)
    assert (c[0].placement.url, c[1].mobile_application.app_id, c[2].youtube_video.video_id) == (
        "exemplo-ruim.com.br", "2-com.exemplo.jogo", "dQw4w9WgXcQ")
    ops = _ops(A.ExcluirPlacements("conta", itens[:1]))
    assert _qual(ops[0]) == "customer_negative_criterion_operation"
    assert ops[0].customer_negative_criterion_operation.create.placement.url == "exemplo-ruim.com.br"


@pytest.mark.parametrize("tipo, valor", [
    ("site", "não é domínio"), ("app", "com.sem.prefixo"), ("youtube_canal", "UCcurto"),
    ("youtube_video", "longo-demais-123"), ("tiktok", "x"),
])
def teste_placement_invalido(tipo, valor):
    with pytest.raises(AcaoRecusada):
        A.Placement(tipo, valor)


def teste_placement_ja_excluido_e_recusado():
    a = A.ExcluirPlacements("conta", (A.Placement("site", "exemplo.com"),))
    linha = _linha(customer_negative_criterion__type_="PLACEMENT",
                   customer_negative_criterion__placement__url="exemplo.com")
    with pytest.raises(AcaoRecusada, match="já excluído"):
        a.conferir(a.interpretar_antes(([linha],)))


@pytest.mark.parametrize("canal, recusa", [
    ("PERFORMANCE_MAX", "Performance Max"), ("DISPLAY", None), ("DEMAND_GEN", None),
])
def teste_exclusao_de_placement_por_campanha_respeita_o_canal(canal, recusa):
    a = A.ExcluirPlacements("campanha", (A.Placement("site", "exemplo.com"),), campaign_id=CAMP)
    assert len(a.consultas_antes(CID)) == 2
    antes = a.interpretar_antes(([], [_linha(campaign__id=CAMP,
                                              campaign__advertising_channel_type=canal)]))
    assert antes["canal"] == canal
    if recusa:
        with pytest.raises(AcaoRecusada, match=recusa):
            a.conferir(antes)
    else:
        a.conferir(antes)


def teste_exclusao_por_campanha_inexistente_e_recusada():
    a = A.ExcluirPlacements("campanha", (A.Placement("site", "exemplo.com"),), campaign_id=CAMP)
    with pytest.raises(AcaoRecusada, match="não encontrada"):
        a.conferir(a.interpretar_antes(([], [])))


def teste_ip_na_campanha_e_na_conta():
    ops = _ops(A.ExcluirIps("campanha", ("203.0.113.7", "198.51.100.0/24", "2001:db8::1"),
                            campaign_id=CAMP))
    assert [o.campaign_criterion_operation.create.ip_block.ip_address for o in ops] == [
        "203.0.113.7", "198.51.100.0/24", "2001:db8::1"]
    assert all(o.campaign_criterion_operation.create.negative for o in ops)
    (op,) = _ops(A.ExcluirIps("conta", ("203.0.113.9",)))
    assert op.customer_negative_criterion_operation.create.ip_block.ip_address == "203.0.113.9"


@pytest.mark.parametrize("ip", ["10.0.0.0/16", "999.1.1.1", "2001:db8::/48", "abc"])
def teste_ip_invalido_ou_faixa_larga(ip):
    with pytest.raises(AcaoRecusada):
        A.ExcluirIps("campanha", (ip,), campaign_id=CAMP)


def teste_ip_respeita_limite_de_500_com_o_que_ja_existe():
    a = A.ExcluirIps("campanha", ("203.0.113.7",), campaign_id=CAMP)
    with pytest.raises(AcaoRecusada, match="500"):
        a.conferir({"ips_existentes": [f"10.0.{i // 250}.{i % 250}" for i in range(500)]})
    with pytest.raises(AcaoRecusada, match="campaign_id"):
        A.ExcluirIps("conta", ("1.1.1.1",), campaign_id=CAMP)


# ── 8. programação e ajustes ────────────────────────────────────────────────


def teste_programacao_cria_janela_com_minuto_enum_e_ajuste():
    a = A.ProgramarAnuncios(CAMP, (A.Janela("MONDAY", "06:15", "23:45", 1.1),
                                   A.Janela("SATURDAY", "08:00", "24:00")))
    ops = _ops(a)
    s = ops[0].campaign_criterion_operation.create
    assert (s.ad_schedule.day_of_week.name, s.ad_schedule.start_hour, s.ad_schedule.start_minute.name,
            s.ad_schedule.end_hour, s.ad_schedule.end_minute.name) == (
        "MONDAY", 6, "FIFTEEN", 23, "FORTY_FIVE")
    assert s.bid_modifier == pytest.approx(1.1)  # float32 no proto
    assert not ops[1].campaign_criterion_operation.create._pb.HasField("bid_modifier")
    assert ops[1].campaign_criterion_operation.create.ad_schedule.end_hour == 24


@pytest.mark.parametrize("janelas, motivo", [
    ((A.Janela("MONDAY", "06:00", "12:00"), A.Janela("MONDAY", "11:45", "13:00")), "sobrepostas"),
    (tuple(A.Janela("MONDAY", f"{h:02d}:00", f"{h:02d}:30") for h in range(7)), "6 janelas"),
])
def teste_programacao_recusa_sobreposicao_e_excesso(janelas, motivo):
    with pytest.raises(AcaoRecusada, match=motivo):
        A.ProgramarAnuncios(CAMP, janelas)


@pytest.mark.parametrize("ini, fim, mod", [("06:10", "07:00", None), ("08:00", "08:00", None),
                                            ("24:15", "24:30", None), ("06:00", "07:00", 0.0),
                                            ("06:00", "07:00", 11.0)])
def teste_janela_invalida(ini, fim, mod):
    with pytest.raises(AcaoRecusada):
        A.Janela("MONDAY", ini, fim, mod)


def _linha_janela(cid, dia, hi, mi, hf, mf, mod=None):
    campos = dict(campaign__id=CAMP, campaign_criterion__criterion_id=cid,
                  campaign_criterion__ad_schedule__day_of_week=dia,
                  campaign_criterion__ad_schedule__start_hour=hi,
                  campaign_criterion__ad_schedule__start_minute=mi,
                  campaign_criterion__ad_schedule__end_hour=hf,
                  campaign_criterion__ad_schedule__end_minute=mf)
    if mod is not None:
        campos["campaign_criterion__bid_modifier"] = mod
    return _linha(**campos)


def teste_substituir_programacao_remove_as_atuais_e_reverso_as_recria():
    base = A.ProgramarAnuncios(CAMP, (A.Janela("MONDAY", "00:00", "01:00"),))
    antes = base.interpretar_antes(([
        _linha_janela(11, "TUESDAY", 9, "ZERO", 18, "THIRTY", 1.25),
        _linha_janela(12, "WEDNESDAY", 9, "FIFTEEN", 18, "ZERO")],))
    assert antes["janelas"][0] == {"criterion_id": 11, "dia": "TUESDAY", "inicio": "09:00",
                                   "fim": "18:30", "modificador": 1.25}
    assert antes["janelas"][1]["modificador"] is None
    a = A.ProgramarAnuncios.substituindo(antes, CAMP, (A.Janela("TUESDAY", "10:00", "12:00"),))
    a.conferir(antes)
    ops = _ops(a)
    assert [o.campaign_criterion_operation.remove for o in ops[:2]] == [
        f"customers/{CID}/campaignCriteria/{CAMP}~11", f"customers/{CID}/campaignCriteria/{CAMP}~12"]
    criado = f"customers/{CID}/campaignCriteria/{CAMP}~901"
    remover, recriar = a.reverso(antes, (criado,))
    assert remover.recursos == (criado,)
    assert [j.json() for j in recriar.janelas] == [
        {"dia": "TUESDAY", "inicio": "09:00", "fim": "18:30", "modificador": 1.25},
        {"dia": "WEDNESDAY", "inicio": "09:15", "fim": "18:00", "modificador": None}]


def teste_programacao_nova_nao_pode_sobrepor_a_que_fica():
    antes = {"janelas": [{"criterion_id": 11, "dia": "TUESDAY", "inicio": "09:00",
                          "fim": "18:00", "modificador": None}]}
    with pytest.raises(AcaoRecusada, match="sobrepostas"):
        A.ProgramarAnuncios(CAMP, (A.Janela("TUESDAY", "17:00", "19:00"),)).conferir(antes)
    with pytest.raises(AcaoRecusada, match="não existe"):
        A.ProgramarAnuncios(CAMP, remover=(99,)).conferir(antes)


def teste_ajuste_de_dispositivo_e_update_no_criterio_que_nasce_com_a_campanha():
    a = A.AjustarDispositivo.de(CAMP, "MOBILE", 1.2)
    (op,) = _ops(a)
    u = op.campaign_criterion_operation
    assert u.update.resource_name == f"customers/{CID}/campaignCriteria/{CAMP}~30001"
    assert list(u.update_mask.paths) == ["bid_modifier"]
    assert u.update.bid_modifier == pytest.approx(1.2)
    sem = a.interpretar_antes(([_linha(campaign__id=CAMP, campaign__advertising_channel_type="SEARCH",
                                       campaign_criterion__criterion_id=30001)],))
    assert sem["modificador"] is None  # 0.0 lido do proto seria −100%: presença decide
    a.conferir(sem)
    (rev,) = a.reverso(sem)
    assert (rev.dispositivo, rev.modificador) == ("MOBILE", 1.0)
    assert A.AjustarDispositivo.de(CAMP, "TABLET", 0).modificador == 0.0
    with pytest.raises(AcaoRecusada, match="PMax"):
        a.conferir({**sem, "canal": "PERFORMANCE_MAX"})
    with pytest.raises(AcaoRecusada):
        A.AjustarDispositivo.de(CAMP, "MOBILE", 0.05)
    with pytest.raises(AcaoRecusada, match="dispositivo"):
        A.AjustarDispositivo.de(CAMP, "SMARTWATCH", 1.1)


def teste_modificador_lido_e_float32_arredondado():
    """1.2 gravado volta 1.2000000476837158; sem arredondar, `já está` nunca bate."""
    a = A.AjustarDispositivo.de(CAMP, "MOBILE", 1.2)
    linha = _linha(campaign__id=CAMP, campaign__advertising_channel_type="SEARCH",
                   campaign_criterion__criterion_id=30001, campaign_criterion__bid_modifier=1.2)
    assert linha.campaign_criterion.bid_modifier != 1.2
    antes = a.interpretar_antes(([linha],))
    assert antes["modificador"] == 1.2
    with pytest.raises(AcaoRecusada, match="já está"):
        a.conferir(antes)


def teste_ajuste_de_horario_e_reverso():
    a = A.AjustarHorario(CAMP, 11, 1.3)
    (op,) = _ops(a)
    assert op.campaign_criterion_operation.update.resource_name.endswith(f"{CAMP}~11")
    (rev,) = a.reverso({"existe": True, "canal": "SEARCH", "modificador": 0.8})
    assert (rev.criterion_id, rev.modificador) == (11, 0.8)
    with pytest.raises(AcaoRecusada):
        A.AjustarHorario(CAMP, 11, 0)


# ── reverso de criação ──────────────────────────────────────────────────────


def teste_remover_criados_ordena_vinculo_antes_da_lista_e_recusa_campanha():
    rs = (f"customers/{CID}/sharedSets/5", f"customers/{CID}/sharedCriteria/5~9",
          f"customers/{CID}/campaignSharedSets/{CAMP}~5")
    a = A.RemoverCriados(rs)
    ops = _ops(a)
    assert [_qual(o) for o in ops] == ["campaign_shared_set_operation",
                                       "shared_criterion_operation", "shared_set_operation"]
    with pytest.raises(AcaoRecusada, match="só remove o que ela cria"):
        A.RemoverCriados((f"customers/{CID}/campaigns/{CAMP}",))
    with pytest.raises(AcaoRecusada, match="outra conta"):
        A.RemoverCriados(("customers/1/campaignCriteria/2~3",)).operacoes(GT, CID, lambda: -1)


def teste_criacoes_revertem_pelos_resource_names_criados():
    criado = (f"customers/{CID}/campaignCriteria/{CAMP}~123",)
    for a in (A.AdicionarNegativas("campanha", CAMP, (A.Termo("x"),)),
              A.ExcluirIps("campanha", ("1.2.3.4",), campaign_id=CAMP),
              A.ExcluirPlacements("campanha", (A.Placement("site", "a.com"),), campaign_id=CAMP)):
        assert a.reverso({}, criado) == (A.RemoverCriados(criado),)
        assert a.reverso({}, ()) == ()  # nada criado, nada a desfazer


# ── 9. recomendações ────────────────────────────────────────────────────────

REC = f"customers/{CID}/recommendations/NzkzMDgwNzU5MS0xMDEtMTc5MTM2NDUwOTM3Mi0rMjQyNzg2NjUxODk"


def teste_recomendacao_monta_operacao_do_recommendation_service_e_nao_do_mutate():
    ap = A.AplicarRecomendacao(REC)
    op = ap.operacao_de_recomendacao(GT)
    assert type(op).__name__ == "ApplyRecommendationOperation" and op.resource_name == REC
    dis = A.DispensarRecomendacao(REC).operacao_de_recomendacao(GT)
    assert type(dis).__name__ == "DismissRecommendationOperation" and dis.resource_name == REC
    with pytest.raises(AcaoRecusada, match="não é GoogleAdsService.Mutate"):
        ap.operacoes(GT, CID, lambda: -1)
    assert ap.reverso({"existe": True}) == () and ap.motivo_sem_reverso
    with pytest.raises(AcaoRecusada, match="inválido"):
        A.AplicarRecomendacao("recommendations/x")


def teste_recomendacao_le_e_confere_o_antes():
    ap = A.AplicarRecomendacao(REC)
    antes = ap.interpretar_antes(([_linha(recommendation__resource_name=REC,
                                          recommendation__type_="SITELINK_ASSET",
                                          recommendation__dismissed=True)],))
    assert antes["tipo"] == "SITELINK_ASSET"
    with pytest.raises(AcaoRecusada, match="dispensada"):
        ap.conferir(antes)


def teste_api_v25_nao_tem_validate_only_para_recomendacao():
    """O fato que decide o desenho: ensaio de recomendação não existe."""
    for nome in ("ApplyRecommendationRequest", "DismissRecommendationRequest"):
        assert "validate_only" not in type(GT(nome)).meta.fields
        assert "partial_failure" in type(GT(nome)).meta.fields
    assert "validate_only" in type(GT("MutateGoogleAdsRequest")).meta.fields


# ── toda GAQL de "antes" passa pelo catálogo do servidor ────────────────────

TODAS = [
    A.AlterarStatus("campanha", CAMP, "PAUSED"), A.AlterarStatus("grupo", AG, "PAUSED"),
    A.AlterarStatus("anuncio", f"{AG}~1", "PAUSED"), A.AlterarStatus("asset_group", 1, "PAUSED"),
    A.AlterarOrcamento(CAMP, 1, OP(10_000)), A.AlterarAlvoDeLance(CAMP, "TARGET_SPEND", "teto_cpc", OP(10_000)),
    A.TrocarEstrategia(CAMP, "MANUAL_CPC"),
    A.AdicionarNegativas("campanha", CAMP, (A.Termo("x"),)),
    A.AdicionarNegativas("grupo", AG, (A.Termo("x"),)),
    A.CriarListaCompartilhada("NEGATIVE_KEYWORDS", "L", (A.Termo("x"),)),
    A.AdicionarNaLista(5, "NEGATIVE_KEYWORDS", (A.Termo("x"),)), A.AnexarLista(5, (CAMP,)),
    A.ExcluirPlacements("campanha", (A.Placement("site", "a.com"),), campaign_id=CAMP),
    A.ExcluirPlacements("conta", (A.Placement("site", "a.com"),)),
    A.ExcluirIps("campanha", ("1.2.3.4",), campaign_id=CAMP), A.ExcluirIps("conta", ("1.2.3.4",)),
    A.ProgramarAnuncios(CAMP, (A.Janela("MONDAY", "00:00", "01:00"),)),
    A.AjustarDispositivo.de(CAMP, "MOBILE", 1.1), A.AjustarHorario(CAMP, 11, 1.1),
    A.AplicarRecomendacao(REC), A.DispensarRecomendacao(REC),
]


@pytest.mark.parametrize("acao", TODAS, ids=lambda a: f"{a.tipo}:{a.alvo_nivel}")
def teste_gaql_do_antes_so_seleciona_o_que_o_servidor_aceita(acao):
    for q in acao.consultas_antes(CID):
        assert catalogo.invalidos(q) == (), q


@pytest.mark.parametrize("acao", TODAS, ids=lambda a: f"{a.tipo}:{a.alvo_nivel}")
def teste_alvo_nivel_cabe_na_check_da_v10_02(acao):
    assert acao.alvo_nivel in {"conta", "campanha", "grupo", "conjunto", "asset_group",
                               "anuncio", "keyword"}
