"""Agendas cron da missão: execuções/dia e intervalos (base do modelo de cadência)."""
from __future__ import annotations

import pytest

from volc_dil.fundacao.capacidade.cron import CronInvalido, a_cada, ler


@pytest.mark.parametrize(
    "expr, n, cobertura",
    [
        ("7 6-23 * * *", 18, (6, 23)),  # Google Ads D0 (documentado)
        ("17 6,14 * * *", 2, (6, 14)),  # Google Ads D-1
        ("23 */4 * * *", 6, (0, 20)),  # termos/keywords
        ("15 6-22/2 * * *", 9, (6, 22)),  # JoinAds intraday
        ("20 6 * * *", 1, (6, 6)),  # JoinAds D-7..D-1
        ("*/15 * * * *", 96, (0, 23)),
        ("*/10 * * * *", 144, (0, 23)),
        ("0 * * * *", 24, (0, 23)),
    ],
)
def test_execucoes_por_dia(expr, n, cobertura):
    ag = ler(expr)
    assert ag.execucoes_por_dia == n
    assert ag.janela_coberta_h() == cobertura
    assert sum(ag.intervalos_min()) == 1440  # os intervalos fecham o dia


def test_intervalos_d0_documentado_tem_buraco_noturno():
    iv = ler("7 6-23 * * *").intervalos_min()
    assert iv[0] == 7 * 60  # de 23:07 até 06:07: 7 h sem leitura
    assert set(iv[1:]) == {60}


def test_a_cada_gera_expressoes_validas():
    assert a_cada(10) == "*/10 * * * *"
    assert a_cada(60) == "0 * * * *"
    assert a_cada(240) == "0 */4 * * *"
    assert ler(a_cada(15)).execucoes_por_dia == 96
    with pytest.raises(CronInvalido):
        a_cada(7)
    with pytest.raises(CronInvalido):
        a_cada(300)


@pytest.mark.parametrize("expr", ["7 6-23 * * 1-5", "61 * * * *", "* * *", "5-2 * * * *", "*/0 * * * *", "a * * * *"])
def test_recusa_fora_do_subconjunto(expr):
    with pytest.raises(CronInvalido):
        ler(expr)
