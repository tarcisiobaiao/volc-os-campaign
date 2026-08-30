"""O perfil do run precisa falhar cedo, e nunca vazar a senha.

Cada teste aqui existe porque a falha oposta é cara: descobrir credencial
ausente no ÚLTIMO passo custa o run inteiro (~US$ 2 e ~45 min de relógio), e uma
senha num log é uma credencial de admin publicada.
"""
from __future__ import annotations

import pytest

from app.redator import PerfilIncompleto, montar_perfil
from app.redator.perfil import perfil_para_log
from app.seguranca import cifrar, gerar_chave

SENHA = "abcd EFGH ijkl MNOP qrst UVWX"

ARQUITETURA = {
    "pages": [{"role": "landing", "position": 1}],
    "writing_jobs": [
        {"writer_briefing": {"keywords": "cartao para negativado, limite garantido"}},
        {"writer_briefing": {"keywords": ["score baixo", "sem consulta ao spc"]}},
    ],
}
ENTIDADE = {
    "canonical_name": "Cartão para Negativado",
    "aliases": ["cartão sem consulta", "cartão pré-pago"],
    "official_source": "Serasa / SPC",
}


@pytest.fixture
def com_chave(monkeypatch):
    monkeypatch.setenv("VOLC_SEGREDO_KEY", gerar_chave())


def _wp(**over):
    base = {
        "wp_url": "https://creditoup.com.br/",
        "wp_username": "redator-volc",
        "wp_app_password_enc": cifrar(SENHA),
        "post_type": "rec",
        "lp_post_type": "r",
    }
    base.update(over)
    return base


def test_perfil_completo(com_chave):
    p = montar_perfil(perfil_wp=_wp(), arquitetura=ARQUITETURA, entidade=ENTIDADE,
                      teto_usd=3.0, teto_pagina_usd=0.8)

    # a barra final do domínio some: o motor concatena caminho em cima disto
    assert p["site"]["domain"] == "https://creditoup.com.br"
    assert p["site"]["post_type"] == "rec" and p["site"]["lp_post_type"] == "r"
    assert p["wordpress"]["app_token"] == SENHA      # decifrada, é o que publica
    assert p["teto_usd"] == 3.0


def test_canal_oficial_vem_da_entidade_nao_de_lista_fixa(com_chave):
    """O ponto inteiro do fim da allowlist: um funil de cartão prefere Serasa,
    não gov.br. A preferência é o `official_source` da entidade — um NOME."""
    p = montar_perfil(perfil_wp=_wp(), arquitetura=ARQUITETURA, entidade=ENTIDADE)
    assert p["tema"]["official_preference"] == ["Serasa / SPC"]


def test_termos_do_tema_juntam_keywords_e_apelidos(com_chave):
    """O motor sozinho teria só o H1 da LP — três palavras para um funil
    inteiro. Aqui ele recebe as keywords de todas as páginas mais os apelidos."""
    p = montar_perfil(perfil_wp=_wp(), arquitetura=ARQUITETURA, entidade=ENTIDADE)
    termos = p["tema"]["termos"]

    assert "cartao para negativado" in termos      # string separada por vírgula
    assert "sem consulta ao spc" in termos         # lista
    assert "Cartão para Negativado" in termos      # nome canônico
    assert "cartão pré-pago" in termos             # apelido
    assert len(termos) == len(set(t.lower() for t in termos)), "termos duplicados"


def test_sem_credencial_falha_antes_de_qualquer_gasto(com_chave):
    with pytest.raises(PerfilIncompleto, match="Application Password"):
        montar_perfil(perfil_wp=_wp(wp_app_password_enc=None), arquitetura=ARQUITETURA)


def test_sem_usuario_ou_url_falha(com_chave):
    with pytest.raises(PerfilIncompleto):
        montar_perfil(perfil_wp=_wp(wp_username=""), arquitetura=ARQUITETURA)
    with pytest.raises(PerfilIncompleto):
        montar_perfil(perfil_wp=_wp(wp_url=""), arquitetura=ARQUITETURA)


def test_card_sem_arquitetura_falha(com_chave):
    with pytest.raises(PerfilIncompleto, match="arquitetura"):
        montar_perfil(perfil_wp=_wp(), arquitetura={"pages": []})


def test_para_log_nunca_devolve_a_senha(com_chave):
    """O perfil é escrito em disco e passa por log. A senha não pode ir junto."""
    p = montar_perfil(perfil_wp=_wp(), arquitetura=ARQUITETURA, entidade=ENTIDADE)
    seguro = perfil_para_log(p)

    texto = str(seguro)
    assert SENHA not in texto
    # Todos os pedaços somem MENOS o último: a máscara revela 4 caracteres de
    # propósito, para o operador reconhecer QUAL credencial está cadastrada sem
    # a tela precisar exibi-la. Reconhecer não é reconstruir.
    for pedaco in SENHA.split()[:-1]:
        assert pedaco not in texto, f"vazou o pedaço {pedaco!r}"
    mascarado = seguro["wordpress"]["app_token"]
    assert mascarado.endswith("UVWX")
    assert mascarado.count("•") == len(SENHA.replace(" ", "")) - 4
    # e o original NÃO foi mutilado — quem chama ainda precisa da senha de verdade
    assert p["wordpress"]["app_token"] == SENHA


def test_sem_entidade_o_perfil_ainda_sai(com_chave):
    """Entidade é opcional: ela só enriquece tema e canal. Um card sem ela roda."""
    p = montar_perfil(perfil_wp=_wp(), arquitetura=ARQUITETURA)
    assert p["tema"]["official_preference"] == []
    assert "cartao para negativado" in p["tema"]["termos"]
