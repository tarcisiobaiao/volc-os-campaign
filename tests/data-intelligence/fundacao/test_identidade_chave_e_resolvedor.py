"""Parser de chave de campanha, resolvedor com confiança e matriz de grão (recusa tipada)."""
from __future__ import annotations

from datetime import date

import pytest

from volc_dil.fundacao.identidade import (
    MATRIZ,
    CampanhaRegistrada,
    Confianca,
    Fonte,
    Grao,
    GraoNaoSuportado,
    GraoTempo,
    MotivoRecusa,
    OrigemValor,
    RegistroCampanhas,
    TemplateCampanha,
    capacidade,
    exigir_grao,
    interpretar_campanha_da_sessao,
    interpretar_chave_campanha,
    receita_por_sessao,
    sobrevive_ao_sensor,
)

D1 = date(2026, 10, 10)


@pytest.mark.parametrize("valor,origem,kw,esperado", [
    ("24278665189", OrigemValor.JOINADS, {}, "24278665189"),
    (" 24278665189 ", OrigemValor.URL_CRUA, {}, "24278665189"),
    ("/", OrigemValor.JOINADS, {"custom_key": "land_uri"}, MotivoRecusa.CHAVE_TROCADA),
    ("24278665189", OrigemValor.JOINADS, {"custom_key": "land_uri"}, MotivoRecusa.CHAVE_TROCADA),
    ("/r/guia/", OrigemValor.JOINADS, {}, MotivoRecusa.CHAVE_TROCADA),
    (None, OrigemValor.JOINADS, {}, MotivoRecusa.AUSENTE),
    ("null", OrigemValor.JOINADS, {}, MotivoRecusa.AUSENTE),
    ("{campaignid}", OrigemValor.URL_CRUA, {}, MotivoRecusa.MACRO_NAO_EXPANDIDA),
    ("{{campaign.id}}", OrigemValor.GAM, {}, MotivoRecusa.MACRO_NAO_EXPANDIDA),
    ("Cursos Senac", OrigemValor.URL_CRUA, {}, MotivoRecusa.TEXTUAL_AMBIGUO),
    ("x" * 45, OrigemValor.URL_CRUA, {}, MotivoRecusa.POSSIVELMENTE_TRUNCADO),
    ("0123", OrigemValor.JOINADS, {}, MotivoRecusa.ID_INVALIDO),
    ("1" * 21, OrigemValor.JOINADS, {}, MotivoRecusa.ID_INVALIDO),
    ("١٢٣", OrigemValor.JOINADS, {}, MotivoRecusa.TEXTUAL_AMBIGUO),  # dígito não-ASCII não é id
])
def test_parser_chave(valor, origem, kw, esperado):
    ch = interpretar_chave_campanha(valor, origem, **kw)
    if isinstance(esperado, MotivoRecusa):  # (MotivoRecusa é str-enum: testar antes de str)
        assert ch.campaign_id is None and ch.recusa is esperado
    else:
        assert ch.campaign_id == esperado and ch.recusa is None


def test_sobrevive_ao_sensor():
    assert sobrevive_ao_sensor("24278665189")[0] is False
    assert sobrevive_ao_sensor("cursos senac")[0] is True


def test_sessao_paga_sem_campanha_e_perda_nao_organico():
    perda = interpretar_campanha_da_sessao(None, paid=1, source="google", medium="cpc")
    assert perda.recusa is MotivoRecusa.DESCARTADO_PELO_SENSOR
    perda2 = interpretar_campanha_da_sessao(None, paid=0, source="google", medium="cpc")
    assert perda2.recusa is MotivoRecusa.DESCARTADO_PELO_SENSOR
    organico = interpretar_campanha_da_sessao(None, paid=0, source=None, medium=None)
    assert organico.recusa is MotivoRecusa.AUSENTE


def _reg(*cs):
    return RegistroCampanhas(list(cs))


def test_resolucao_deterministica_por_id_e_validade():
    reg = _reg(CampanhaRegistrada("5478096539", "24278665189", "VOLC-SENAC", date(2026, 9, 21)))
    ch = interpretar_chave_campanha("24278665189", OrigemValor.JOINADS)
    r = reg.resolver(ch, D1)
    assert (r.confianca, r.customer_id, r.campaign_id) == (Confianca.DETERMINISTICA, "5478096539", "24278665189")
    antes = reg.resolver(ch, date(2026, 9, 1))
    assert antes.confianca is Confianca.NAO_ATRIBUIVEL and antes.motivo == "id_nao_registrado_no_dia"


def test_id_em_duas_contas_nao_atribui():
    reg = _reg(CampanhaRegistrada("111111", "999", "a", date(2026, 1, 1)),
               CampanhaRegistrada("222222", "999", "b", date(2026, 1, 1)))
    r = reg.resolver(interpretar_chave_campanha("999", OrigemValor.JOINADS), D1)
    assert r.confianca is Confianca.NAO_ATRIBUIVEL and r.motivo == "id_em_mais_de_uma_conta"


def test_nome_textual_so_probabilistico_e_so_com_template_nome():
    reg = _reg(CampanhaRegistrada("1", "10", "Cursos Senac Técnico", date(2026, 1, 1), template=TemplateCampanha.NOME),
               CampanhaRegistrada("1", "11", "Outra", date(2026, 1, 1)))  # template id: não casa por nome
    r = reg.resolver(interpretar_chave_campanha("cursos  SENAC tecnico", OrigemValor.URL_CRUA), D1)
    assert (r.confianca, r.campaign_id) == (Confianca.PROBABILISTICA, "10")
    r2 = reg.resolver(interpretar_chave_campanha("Outra", OrigemValor.URL_CRUA), D1)
    assert r2.confianca is Confianca.NAO_ATRIBUIVEL and r2.motivo == "texto_sem_mapa_declarado"


def test_resolucao_nunca_carrega_id_quando_nao_atribuivel():
    from volc_dil.fundacao.identidade import Resolucao
    with pytest.raises(ValueError):
        Resolucao(Confianca.NAO_ATRIBUIVEL, "x", "1", "2")
    with pytest.raises(ValueError):
        Resolucao(Confianca.DETERMINISTICA, "x")


# ---------------------------------------------------------------- matriz de grão

def test_matriz_honesta_campanha_dia_e_o_unico_grao_economico():
    c = exigir_grao(Fonte.GOOGLE_ADS, Fonte.JOINADS, Grao.CAMPANHA, GraoTempo.DIA)
    assert c.hoje is Confianca.DETERMINISTICA
    for g in (Grao.SESSAO, Grao.CLIQUE, Grao.GRUPO_ANUNCIO, Grao.KEYWORD):
        with pytest.raises(GraoNaoSuportado):
            exigir_grao(Fonte.GOOGLE_ADS, Fonte.JOINADS, g)
    with pytest.raises(GraoNaoSuportado):
        exigir_grao(Fonte.GOOGLE_ADS, Fonte.JOINADS, Grao.CAMPANHA, GraoTempo.HORA)


def test_recusa_carrega_grao_honesto_disponivel():
    with pytest.raises(GraoNaoSuportado) as e:
        exigir_grao(Fonte.GOOGLE_ADS, Fonte.SENSOR, Grao.CAMPANHA)
    assert "regex de telefone" in e.value.motivo
    disponiveis = {(g, c) for g, _, c in e.value.suportados}
    assert (Grao.LANDING, Confianca.DETERMINISTICA) in disponiveis
    assert (Grao.KEYWORD, Confianca.PROBABILISTICA) in disponiveis


def test_receita_por_sessao_sempre_recusa():
    with pytest.raises(GraoNaoSuportado) as e:
        receita_por_sessao([1, 2, 3], total=10)
    assert e.value.grao is Grao.SESSAO and "rateio" in e.value.motivo


def test_grao_desconhecido_recusa():
    with pytest.raises(GraoNaoSuportado):
        exigir_grao(Fonte.GAM, Fonte.SENSOR, Grao.ANUNCIO)


def test_invariantes_da_matriz():
    ordem = {Confianca.NAO_ATRIBUIVEL: 0, Confianca.PROBABILISTICA: 1, Confianca.DETERMINISTICA: 2}
    chaves = set()
    for c in MATRIZ:
        assert len(c.fontes) == 2
        assert ordem[c.hoje] <= ordem[c.potencial], c
        if c.hoje is Confianca.NAO_ATRIBUIVEL:
            assert c.requer or c.prova, c  # toda impossibilidade diz por quê
        k = (c.fontes, c.grao, c.tempo)
        assert k not in chaves
        chaves.add(k)
    # sessão/clique com receita: impossível hoje E potencialmente (fontes agregadas)
    assert capacidade(Fonte.GOOGLE_ADS, Fonte.JOINADS, Grao.SESSAO).potencial is Confianca.NAO_ATRIBUIVEL
    assert capacidade(Fonte.SENSOR, Fonte.JOINADS, Grao.SESSAO).potencial is Confianca.NAO_ATRIBUIVEL
