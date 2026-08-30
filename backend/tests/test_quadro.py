"""O quadro do Redator — as regras que decidem em que coluna cada coisa cai.

Roda contra o Supabase de verdade (só leitura). Por isso as asserções são sobre
INVARIANTES, nunca sobre a contagem do dia: "nenhum card aparece em duas
colunas" continua verdade amanhã; "há 4 interrompidos" não.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ⚠️ Sem isto, estes testes PULAM na suíte inteira: os módulos herméticos
# gravam "" em SUPABASE_URL no import e ninguém restaura. Ver o cabeçalho
# de `tests/conftest.py` — 4 destes sumiam em silêncio, medido em 18/08/2026.
# ⚠️ NÃO use `usefixtures` aqui: `quadro` é fixture de MÓDULO e roda antes
# de qualquer fixture de função. Ela pede `ambiente_real_modulo` por
# parâmetro — só a dependência explícita ordena duas fixtures do mesmo
# escopo. Ver o cabeçalho de `tests/conftest.py`.


ROTA = "/api/publicacao/redator/quadro"


@pytest.fixture(scope="module")
def quadro(ambiente_real_modulo) -> dict:
    r = TestClient(app).get(ROTA)
    if r.status_code == 503:
        pytest.skip("Supabase não configurado neste ambiente")
    assert r.status_code == 200, r.text
    return r.json()


def test_as_quatro_colunas_e_os_totais_existem(quadro: dict):
    for k in ("prontos", "escrevendo", "escritos", "interrompidos"):
        assert isinstance(quadro[k], list)
    for k in ("gasto_usd", "runs", "paginas_no_ar"):
        assert k in quadro["totais"]


def test_um_card_pronto_nunca_tem_run_vivo_ou_concluido(quadro: dict):
    """A invariante que define a primeira coluna. Quebrada, o operador dispara
    um segundo funil para um card que já tem um — e paga ~US$ 2 para publicar
    páginas duplicadas no mesmo site.
    """
    ocupados = {f["opportunity_id"] for f in quadro["escrevendo"] + quadro["escritos"]}
    prontos = {c["opportunity_id"] for c in quadro["prontos"]}
    assert prontos & ocupados == set()


def test_um_run_aparece_em_uma_coluna_so(quadro: dict):
    ids = [f["id"] for f in quadro["escrevendo"] + quadro["escritos"] + quadro["interrompidos"]]
    assert len(ids) == len(set(ids))


def test_interrompido_nao_bloqueia_o_card(quadro: dict):
    """Falhou é justamente o caso em que se quer tentar de novo. Um run
    `failed` NÃO pode tirar o card da fila — senão um erro transitório de rede
    aposenta a pauta para sempre.

    ⚠️ Este teste PULA quando os dados não têm o caso. É deliberado: a
    alternativa que escrevi primeiro era uma tautologia (`x not in y or x in
    y`), que passa sempre e não observa nada. Um pulo declarado é honesto;
    um verde vazio mente.
    """
    so_fracassaram = ({f["opportunity_id"] for f in quadro["interrompidos"]}
                      - {f["opportunity_id"] for f in quadro["escrevendo"] + quadro["escritos"]})
    if not so_fracassaram:
        pytest.skip("nenhum card cujo único histórico é fracasso — regra não exercitada hoje")
    prontos = {c["opportunity_id"] for c in quadro["prontos"]}
    # Pelo menos um deles tem de continuar disponível. Se NENHUM estiver, ou
    # todos saíram de `ready` (legítimo) ou existe uma regra escondida
    # bloqueando por fracasso (o defeito).
    assert so_fracassaram & prontos, (
        "cards que só fracassaram sumiram da fila — confira se `failed` está "
        "entrando no conjunto de ocupados")


def test_prontos_sempre_tem_paginas_planejadas(quadro: dict):
    """`ready` sem arquitetura não é disparável: o motor não teria o que
    escrever, e a descoberta custaria uma requisição de disparo rejeitada."""
    for c in quadro["prontos"]:
        assert c["paginas"] > 0
        assert c["titulo"]


def test_todo_funil_tem_titulo_humano(quadro: dict):
    """`display_title` está NULO em todos os cards de hoje. Sem a cadeia de
    recuo pela entidade, o quadro inteiro diria "card #73"."""
    for f in quadro["escrevendo"] + quadro["escritos"] + quadro["interrompidos"]:
        assert f["titulo"]


def test_o_gasto_acumulado_inclui_os_fracassos(quadro: dict):
    """Dinheiro gasto é dinheiro gasto. Somar só os runs bem-sucedidos faria o
    custo por funil parecer menor do que é — e é esse número que precisa ser
    confrontado com a receita do AdSense."""
    soma_visivel = sum((f["custo_usd"] or 0) for f in
                       quadro["escrevendo"] + quadro["escritos"] + quadro["interrompidos"])
    assert quadro["totais"]["gasto_usd"] == pytest.approx(soma_visivel, abs=0.01)
    if quadro["interrompidos"]:
        gasto_fracassado = sum((f["custo_usd"] or 0) for f in quadro["interrompidos"])
        if gasto_fracassado > 0:
            assert quadro["totais"]["gasto_usd"] > sum(
                (f["custo_usd"] or 0) for f in quadro["escritos"])


def test_paginas_no_ar_conta_publicacao_e_nao_geracao(quadro: dict):
    """Uma página "gerada" que não subiu não existe para a campanha."""
    total = sum(f["paginas_publicadas"] for f in
                quadro["escrevendo"] + quadro["escritos"] + quadro["interrompidos"])
    assert quadro["totais"]["paginas_no_ar"] == total
