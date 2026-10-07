"""O perfil do run pode ligar o fluxo editorial v2 por funil — e, por padrão, não liga.

Contrato entre trilhas (decisão 1): a flag `editorial_v2` nasce desligada no
`config.yaml` do motor, e o perfil do funil pode ligá-la. "Não enviar" é o
padrão: o perfil de hoje sai byte a byte igual, e o motor segue no fluxo atual.

Formato combinado com o motor: chave `editorial_v2` na RAIZ do perfil (como
`teto_usd`), booleana, presente só quando verdadeira.
"""
from __future__ import annotations

import json

import pytest

from app.redator import montar_perfil
from app.redator.perfil import perfil_para_log
from app.seguranca import cifrar, gerar_chave

ARQ = {"pages": [{"position": 1}],
       "writing_jobs": [{"writer_briefing": {"keywords": "cursos senac"}}]}


@pytest.fixture
def wp(monkeypatch):
    monkeypatch.setenv("VOLC_SEGREDO_KEY", gerar_chave())
    return {"wp_url": "https://creditoup.com.br", "wp_username": "redator",
            "wp_app_password_enc": cifrar("abcd EFGH ijkl MNOP"),
            "post_type": "rec", "lp_post_type": "r"}


def test_por_padrao_a_flag_nao_vai(wp):
    p = montar_perfil(perfil_wp=wp, arquitetura=ARQ)
    assert "editorial_v2" not in p
    assert set(p) == {"site", "wordpress", "tema"}     # o perfil de sempre


def test_ligada_vai_na_raiz_do_perfil(wp):
    p = montar_perfil(perfil_wp=wp, arquitetura=ARQ, editorial_v2=True)
    assert p["editorial_v2"] is True


def test_so_true_de_verdade_liga(wp):
    """Um valor "verdadeiro por acaso" (string, 1) não liga um fluxo que muda
    prompts e passos: o motor só vê a flag quando alguém disse True."""
    for valor in (False, None, "sim", 1):
        p = montar_perfil(perfil_wp=wp, arquitetura=ARQ, editorial_v2=valor)
        assert "editorial_v2" not in p


def test_a_flag_aparece_no_log_e_a_senha_nao(wp):
    p = montar_perfil(perfil_wp=wp, arquitetura=ARQ, editorial_v2=True)
    log = json.dumps(perfil_para_log(p), ensure_ascii=False)
    assert '"editorial_v2": true' in log
    assert "abcd EFGH ijkl MNOP" not in log
