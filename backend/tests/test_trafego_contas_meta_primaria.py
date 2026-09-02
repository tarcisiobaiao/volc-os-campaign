"""`contas.meta_de_conversao` — o leitor legado que colapsava *presence*.

## O defeito, com o caminho e a consequência

`contas.py:206` lia `"primaria": bool(a.primary_for_goal)`.
`conversion_action.primary_for_goal` tem *presence* no proto (conferido contra
o descritor real do SDK v25) e a doc oficial diz, literal: **"By default,
`primary_for_goal` will be true if not set."** Lido com `bool(...)`, o campo
AUSENTE virava `False` — o veredito exatamente invertido, no campo que decide
o que o `maximize_conversions` persegue. Numa conta em que todas as ações têm o
campo ausente, a resposta saía `primaria: None` e o cockpit anunciava
"⚠️ Esta conta não tem ação de conversão primária" sobre uma conta que tem.

O segundo defeito, na mesma função: `contas.py:209` escolhia
`next((a for a in acoes if a["primaria"]), None)` — **a primeira da lista**, sem
`ORDER BY` na GAQL. A meta mostrada podia mudar entre duas leituras idênticas.

## Por que não foi removido

Ele não é caminho morto. Três consumidores de produção, medidos por `rg`:

| consumidor | linha |
|---|---|
| cockpit (`GET` do projeto) | `backend/app/routers/trafego.py:856` |
| `/provar` → `prontidao.avaliar(metas_da_conta=...)` | `backend/app/routers/trafego.py:2758` |
| dossiê do canário | `scripts/dossie_canario_v10.py:191` |

E a saída chega à tela: `src/components/trafego/MesaDeLance.tsx:61` e
`PainelDoLancamento.tsx:40` leem `meta_conversao.primaria`;
`src/pages/trafego/NovaCampanhaPage.tsx:366` manda `primaria.id` adiante.
Remover sem substituto apagaria a única meta que o operador vê antes de lançar.

## Hermeticidade

`buscar` é monkeypatchado no módulo do engine e `socket.connect` levanta. As
linhas são montadas com os **tipos proto reais da v25**: um `SimpleNamespace`
responderia qualquer coisa a `HasField` e a prova mediria o dublê, não o
contrato — que é precisamente o defeito em questão.
"""
from __future__ import annotations

import os
import socket
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.trafego import contas as ct  # noqa: E402
from app.trafego import prontidao as pr  # noqa: E402

pytest.importorskip("google.ads.googleads")

from google.ads.googleads.v25.resources.types import (  # noqa: E402
    conversion_action as ca,
)

CONTA = "5478096539"
MCC = "6016739364"


@pytest.fixture(autouse=True)
def _rede_bloqueada(monkeypatch: pytest.MonkeyPatch):
    """Não é promessa: é `pytest.fail` dentro de `socket.connect`."""
    def recusar_rede(_socket, _address):
        pytest.fail("teste de contas.meta_de_conversao tentou abrir conexão")

    monkeypatch.setattr(socket.socket, "connect", recusar_rede)
    monkeypatch.setattr(socket.socket, "connect_ex", recusar_rede)


def _acao(*, id, primaria, nome="Compra no site", categoria="PURCHASE",
          tipo="WEBPAGE"):
    """⚠️ `primaria=None` deixa o campo AUSENTE — o caso do defeito."""
    a = ca.ConversionAction()
    a.id = id
    a.name = nome
    a.resource_name = f"customers/{CONTA}/conversionActions/{id}"
    a.category = categoria
    a.origin = "WEBSITE"
    a.type_ = tipo
    a.status = "ENABLED"
    if primaria is not None:
        a.primary_for_goal = primaria
    return SimpleNamespace(conversion_action=a)


def _ler(monkeypatch: pytest.MonkeyPatch, linhas):
    import volc_ads.gads.client as cliente

    def _buscar(customer_id, query, *, login_customer_id, **_kw):
        assert customer_id == CONTA
        assert login_customer_id == MCC
        assert "FROM conversion_action" in query
        # Somente leitura: a GAQL não tem verbo de escrita, e o teste confere.
        assert query.strip().upper().startswith("SELECT")
        return list(linhas)

    monkeypatch.setattr(cliente, "buscar", _buscar)
    return ct.meta_de_conversao(CONTA, login_customer_id=MCC)


# ═══════════════════════════════════════════════════════════════════════════
# 1. PRESENCE — ausente ≠ False, e a diferença inverte o veredito
# ═══════════════════════════════════════════════════════════════════════════


def test_campo_ausente_e_primaria_efetiva_e_nao_secundaria(monkeypatch):
    """O caso que o `bool(...)` invertia.

    ⚠️ O par completo: a DECLARAÇÃO continua `None` (a API não disse nada) e o
    EFETIVO é `True` (o default documentado). Colapsar os dois num booleano só
    é o defeito, em qualquer das duas direções.
    """
    saida = _ler(monkeypatch, [_acao(id=7466919994, primaria=None)])
    acao = saida["acoes"][0]
    assert acao["primaria"] is None, (
        "a API não declarou nada; `False` aqui seria inventar uma declaração")
    assert acao["primaria_efetiva"] is True
    assert saida["primaria"] is not None
    assert saida["primaria"]["id"] == "7466919994"
    assert "não tem ação de conversão primária" not in saida["por_que"]


def test_false_declarado_continua_false(monkeypatch):
    """A recíproca. Sem ela, "ausente = true" viraria "tudo é primária"."""
    saida = _ler(monkeypatch, [_acao(id=7466919994, primaria=False)])
    acao = saida["acoes"][0]
    assert acao["primaria"] is False
    assert acao["primaria_efetiva"] is False
    assert saida["primaria"] is None
    assert saida["primarias"] == []
    assert "não tem ação de conversão primária" in saida["por_que"]


def test_true_declarado_continua_true(monkeypatch):
    saida = _ler(monkeypatch, [_acao(id=7466919994, primaria=True)])
    assert saida["acoes"][0]["primaria"] is True
    assert saida["acoes"][0]["primaria_efetiva"] is True
    assert saida["primarias_declaradas"] == 1


def test_as_duas_contagens_sao_diferentes_e_e_isso_que_denuncia_o_default(
        monkeypatch):
    """Declaradas ≠ efetivas. As duas saem separadas de propósito."""
    saida = _ler(monkeypatch, [
        _acao(id=100, primaria=True),
        _acao(id=200, primaria=None),
        _acao(id=300, primaria=False),
    ])
    assert saida["primarias_declaradas"] == 1
    assert saida["primarias_efetivas"] == 2
    assert [a["id"] for a in saida["primarias"]] == ["100", "200"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. ORDEM — a escolha para de depender de como a consulta devolveu
# ═══════════════════════════════════════════════════════════════════════════


def test_a_escolha_e_o_menor_id_e_nao_a_primeira_da_lista(monkeypatch):
    """A MESMA conta, devolvida em duas ordens, tem de dar a MESMA resposta.

    ⚠️ Este é o par que prova a estabilidade. Um teste com uma ordem só passaria
    com a implementação antiga.
    """
    acoes = [_acao(id=900, primaria=True, nome="Zebra"),
             _acao(id=100, primaria=True, nome="Alfa"),
             _acao(id=500, primaria=True, nome="Meio")]
    primeira = _ler(monkeypatch, acoes)
    segunda = _ler(monkeypatch, list(reversed(acoes)))
    assert primeira["primaria"]["id"] == "100"
    assert segunda["primaria"]["id"] == "100"
    assert primeira["primaria"] == segunda["primaria"]


def test_com_varias_primarias_o_texto_para_de_dizer_a_primaria_no_singular(
        monkeypatch):
    """Medido na Portal Mundo Mais: 9 ações ENABLED, 8 primárias.

    Dizer "a ação primária" apagava sete delas.
    """
    saida = _ler(monkeypatch, [_acao(id=100 + i, primaria=(i < 8))
                               for i in range(9)])
    assert saida["primarias_efetivas"] == 8
    assert "8 ações primárias" in saida["por_que"]
    assert "menor id numérico" in saida["por_que"]
    # E ele diz em voz alta que esta leitura NÃO é a meta efetiva.
    assert "goal_config_level" in saida["por_que"]


def test_conta_vazia_nao_vira_conta_sem_primaria_por_engano(monkeypatch):
    """Zero ação e zero primária são a mesma resposta aqui — e ela é honesta."""
    saida = _ler(monkeypatch, [])
    assert saida["acoes"] == []
    assert saida["primaria"] is None
    assert saida["primarias_efetivas"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. O CONSUMIDOR — `prontidao` conta o EFETIVO, e não a declaração
# ═══════════════════════════════════════════════════════════════════════════


def test_prontidao_conta_as_primarias_efetivas(monkeypatch):
    """A saída deste leitor entra em `avaliar(metas_da_conta=...)`.

    ⚠️ Com o veredito invertido, `conversion_actions_primarias` saía VAZIA numa
    conta com ação primária — e a nota ao lado afirmava um número. Dois campos
    da mesma resposta discordando é o desfecho que este assert impede.
    """
    metas = _ler(monkeypatch, [_acao(id=100, primaria=None),
                               _acao(id=200, primaria=True),
                               _acao(id=300, primaria=False)])
    r = pr.avaliar(recibo_registrado=True, metas_da_conta=metas)
    assert r.conversion_goal_status == pr.PARCIAL
    assert "2 ação(ões)" in r.notas["conversion_goal"]
    assert [a["id"] for a in r.notas["conversion_actions_primarias"]] == [
        "100", "200"]


def test_o_recuo_para_dicionario_montado_a_mao_continua_valendo():
    """Chamador que monta `metas_da_conta` sem `primaria_efetiva`.

    ⚠️ Testes e `scripts/dossie_canario_v10.py` fazem isso. Sem o recuo, a
    contagem sairia zero e a nota se contradiria de novo — pelo lado oposto.
    """
    r = pr.avaliar(recibo_registrado=True, metas_da_conta={
        "primaria": {"id": "1"},
        "acoes": [{"id": "1", "primaria": True},
                  {"id": "2", "primaria": False}]})
    assert "1 ação(ões)" in r.notas["conversion_goal"]


def test_o_leitor_legado_nao_decide_quando_ha_plano():
    """A precedência que torna este caminho não-decisório.

    ⚠️ É por isso que o defeito era MÉDIO e não ALTO: com plano presente,
    `avaliar` usa o ramo do plano e ignora `metas_da_conta`. O conserto vale
    para o cockpit, para o dossiê e para o `/provar` sem plano — que são
    exatamente os três lugares onde ele ainda é lido.
    """
    import inspect
    fonte = inspect.getsource(pr.avaliar)
    assert "if plano_de_mensuracao is not None:" in fonte
    assert fonte.index("if plano_de_mensuracao is not None:") < fonte.index(
        "elif metas_da_conta is None:")
