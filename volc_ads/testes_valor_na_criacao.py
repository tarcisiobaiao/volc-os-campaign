"""W5 na CRIAÇÃO de campanha: verba e lance do payload precisam de origem.

`preparar()` real, com o builder Search real e a RPC de `validate_only`
dublada. A prova que importa é a negativa: sem `ValorMonetario` que autorize,
ou com CPC de SERP, o ensaio nem sai — `validar_mutacoes` não é chamada e não
há selo.
"""
from __future__ import annotations

import pytest

from volc_ads import subir as sb
from volc_ads.campanha import search
from volc_ads.campanha.testes_criterio import CID, _brief, _cliente_sem_rede
from volc_ads.gestao.valor import (ValorMonetario, ValorSemAutoridade, dinheiro_nas_operacoes,
                                   exigir_dinheiro_autorizado, micros_declarados,
                                   valores_do_operador)

JUST = "orçamento e CPC definidos pelo operador"


@pytest.fixture(autouse=True)
def _sem_credencial(monkeypatch):
    monkeypatch.setattr(search, "cliente", lambda _login: _cliente_sem_rede())


@pytest.fixture
def chamadas(monkeypatch):
    feitas = []

    def validar(customer_id, operacoes, *, login_customer_id, request_ids=None):
        feitas.append(list(operacoes))
        return None

    monkeypatch.setattr(sb, "validar_mutacoes", validar)
    return feitas


def _do_operador(brief):
    return valores_do_operador(brief, sub="u2", papel="OPERATOR",
                               quando="2026-10-15T12:00:00+00:00", justificativa=JUST)


def test_payload_de_criacao_tem_verba_e_lance():
    brief = _brief()
    ops, _ = sb.perfil.montar("SEARCH", CID, brief, login_customer_id=CID)
    achados = dict(dinheiro_nas_operacoes(ops))
    assert brief.micros(brief.budget_diario) in achados.values()
    assert any("amount_micros" in c for c in achados)  # o orçamento
    assert micros_declarados(brief) >= set(achados.values())


def test_criacao_sem_origem_nao_ensaia(chamadas):
    preparo = sb.preparar(CID, _brief(), login_customer_id=CID, canal="SEARCH")
    assert preparo.selo is None and chamadas == []
    assert preparo.recusa_local.startswith("valor_sem_autoridade")


@pytest.mark.parametrize("origem", ["serp", "ferramenta_externa"])
def test_criacao_com_cpc_externo_nao_ensaia(chamadas, origem):
    brief = _brief()
    externos = [ValorMonetario(m, origem, f"{origem}: sugerido") for m in micros_declarados(brief)]
    preparo = sb.preparar(CID, brief, login_customer_id=CID, canal="SEARCH", valores=externos)
    assert preparo.selo is None and chamadas == []
    assert "anotação" in preparo.recusa_local


def test_criacao_com_numero_que_ninguem_declarou_nao_ensaia(chamadas):
    """O operador declarou a verba, mas o CPC do payload não é dele."""
    brief = _brief()
    so_verba = _do_operador({"budget_diario": brief.budget_diario})
    preparo = sb.preparar(CID, brief, login_customer_id=CID, canal="SEARCH", valores=so_verba)
    assert preparo.selo is None and chamadas == []
    assert "não tem origem" in preparo.recusa_local


def test_criacao_com_valores_do_operador_ensaia_e_sela(chamadas):
    brief = _brief()
    preparo = sb.preparar(CID, brief, login_customer_id=CID, canal="SEARCH",
                          valores=_do_operador(brief))
    assert len(chamadas) == 1 and preparo.selo is not None


def test_justificativa_curta_nao_autoriza_criacao():
    brief = _brief()
    ops, _ = sb.perfil.montar("SEARCH", CID, brief, login_customer_id=CID)
    curtos = valores_do_operador(brief, sub="u2", papel="OPERATOR",
                                 quando="2026-10-15T12:00:00+00:00", justificativa="ok")
    with pytest.raises(ValorSemAutoridade, match="justificativa"):
        exigir_dinheiro_autorizado(ops, curtos)
