"""Detector de colisão e identidade trocada."""
from __future__ import annotations

from datetime import date

from volc_dil.fundacao.identidade import (
    CampanhaRegistrada,
    Confianca,
    Gravidade,
    OrigemValor,
    RegistroCampanhas,
    TemplateCampanha,
    TipoColisao,
    colisoes_de_normalizacao,
    detectar_colisoes_registro,
    detectar_custom_key_substituida,
    interpretar_chave_campanha,
)

NOME = TemplateCampanha.NOME


def _tipos(cols):
    return {(c.tipo, c.gravidade) for c in cols}


def test_mesma_utm_para_duas_campanhas_bloqueia():
    cs = [CampanhaRegistrada("1", "10", "Cursos Tecno", date(2026, 1, 1), template=NOME),
          CampanhaRegistrada("1", "20", "CURSOS  TECNO", date(2026, 3, 1), template=NOME)]
    assert (TipoColisao.MESMA_UTM_DUAS_CAMPANHAS, Gravidade.BLOQUEIA) in _tipos(detectar_colisoes_registro(cs))
    r = RegistroCampanhas(cs).resolver(interpretar_chave_campanha("cursos tecno", OrigemValor.URL_CRUA), date(2026, 4, 1))
    assert r.confianca is Confianca.NAO_ATRIBUIVEL and r.motivo == "colisao_textual"


def test_mesma_utm_sem_sobreposicao_de_validade_nao_colide():
    cs = [CampanhaRegistrada("1", "10", "Cursos Tecno", date(2026, 1, 1), date(2026, 1, 31), template=NOME),
          CampanhaRegistrada("1", "20", "cursos tecno", date(2026, 2, 1), template=NOME)]
    assert detectar_colisoes_registro(cs) == []
    reg = RegistroCampanhas(cs)
    ch = interpretar_chave_campanha("Cursos Tecno", OrigemValor.URL_CRUA)
    assert reg.resolver(ch, date(2026, 1, 15)).campaign_id == "10"
    assert reg.resolver(ch, date(2026, 2, 15)).campaign_id == "20"


def test_campanha_renomeada_informa_com_template_id_e_bloqueia_com_nome():
    por_id = [CampanhaRegistrada("1", "10", "VOLC-TECNO v1", date(2026, 9, 1), date(2026, 9, 30)),
              CampanhaRegistrada("1", "10", "VOLC-TECNO v2", date(2026, 10, 1))]
    assert _tipos(detectar_colisoes_registro(por_id)) == {(TipoColisao.CAMPANHA_RENOMEADA, Gravidade.INFORMA)}
    por_nome = [CampanhaRegistrada("1", "10", "tecno v1", date(2026, 9, 1), date(2026, 9, 30), template=NOME),
                CampanhaRegistrada("1", "10", "tecno v2", date(2026, 10, 1), template=NOME)]
    assert (TipoColisao.CAMPANHA_RENOMEADA, Gravidade.BLOQUEIA) in _tipos(detectar_colisoes_registro(por_nome))
    # o nome antigo, depois da troca, não resolve mais
    reg = RegistroCampanhas(por_nome)
    velho = interpretar_chave_campanha("tecno v1", OrigemValor.URL_CRUA)
    assert reg.resolver(velho, date(2026, 10, 5)).confianca is Confianca.NAO_ATRIBUIVEL


def test_truncamento_no_limite_do_sensor_e_ambiguo():
    base = "campanha de cursos tecnicos do tecno para "  # 42 caracteres
    cs = [CampanhaRegistrada("1", "10", base + "sao paulo", date(2026, 1, 1), template=NOME),
          CampanhaRegistrada("1", "20", base + "rio", date(2026, 1, 1), template=NOME)]
    cols = detectar_colisoes_registro(cs)
    assert (TipoColisao.TRUNCAMENTO_AMBIGUO, Gravidade.BLOQUEIA) in _tipos(cols)
    ch = interpretar_chave_campanha(base + "rio", OrigemValor.URL_CRUA)
    assert ch.recusa.value == "possivelmente_truncado"
    assert RegistroCampanhas(cs).resolver(ch, date(2026, 2, 1)).confianca is Confianca.NAO_ATRIBUIVEL


def test_id_em_duas_contas():
    cs = [CampanhaRegistrada("111", "999", "a", date(2026, 1, 1)),
          CampanhaRegistrada("222", "999", "b", date(2026, 1, 1))]
    assert (TipoColisao.ID_EM_DUAS_CONTAS, Gravidade.BLOQUEIA) in _tipos(detectar_colisoes_registro(cs))


def test_custom_key_substituida_inclusive_grafia_custon():
    linhas = [{"custom_key": "utm_campaign", "custom_value": "20000000011"},
              {"custom_key": "land_uri", "custom_value": "/"},
              {"custon_key": "id_post_wp", "custon_value": "2306"},
              {"custom_value": "sem chave declarada"}]
    cols = detectar_custom_key_substituida(linhas)
    assert [c.envolvidos for c in cols] == [("land_uri",), ("id_post_wp",)]


def test_colisoes_de_normalizacao_caixa_acento_pontuacao():
    grupos = colisoes_de_normalizacao(["Educação", "educacao", "EDUCAÇÃO!", "outra", "20000000011"])
    assert grupos == {"educacao": ("EDUCAÇÃO!", "Educação", "educacao")}
