"""Provas das rotas de catálogo: nada carrega sozinho, nada achata estado.

O que se prova aqui é a FRONTEIRA. A classificação tri-state e os cinco
estados de leitura estão provados em `test_meta_catalogos_selecionaveis.py`;
aqui a pergunta é se a rota os entrega inteiros ao navegador — ou se os
simplifica no caminho, que é o defeito que `A11` e `A12` proíbem.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import meta_local
from app.seguranca.identidade import Identidade, exigir_admin


def _cliente() -> TestClient:
    app = FastAPI()
    app.include_router(meta_local.router)
    app.dependency_overrides[exigir_admin] = lambda: Identidade(
        sub="operador-meta", email="admin@volc", papel="ADMIN", origem="sessao")
    return TestClient(app, headers={"host": "localhost"})


class _Credencial:
    token = "token-meta-falso-seguro"


@pytest.fixture(autouse=True)
def _local(monkeypatch):
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    monkeypatch.setattr(meta_local, "_credencial_salva", lambda *_: _Credencial())


def _dublar(monkeypatch, **envelopes: Any) -> dict[str, int]:
    """Substitui os leitores do adaptador e CONTA as chamadas."""
    chamadas: dict[str, int] = {nome: 0 for nome in envelopes}

    for nome, envelope in envelopes.items():
        def fabricar(nome=nome, envelope=envelope):
            async def leitor(self, *args: Any, **kwargs: Any) -> Any:
                chamadas[nome] += 1
                if isinstance(envelope, Exception):
                    raise envelope
                return envelope
            return leitor
        monkeypatch.setattr(
            meta_local.AdaptadorMetaSomenteLeitura, nome, fabricar(), raising=False)
    return chamadas


ENVELOPE_VAZIO = {
    "ok": True, "catalogo": "custom_audiences", "estado": "VAZIO_COMPLETO",
    "motivo": None, "retryable": False, "items": [], "total": 0,
    "invalidos": 0, "desconhecidos": 0, "completo": True, "paginas_lidas": 1,
    "observado_em": "2026-09-08T00:00:00+00:00", "ttl_s": 300,
    "expira_em": "2026-09-08T00:05:00+00:00", "estado_do_catalogo": "VIGENTE",
}


def test_nenhum_catalogo_e_lido_sem_a_conta_escolhida(monkeypatch) -> None:
    """Montar a página não pode disparar leitura da Meta."""
    chamadas = _dublar(monkeypatch, catalogo_de_publicos=ENVELOPE_VAZIO)
    resposta = _cliente().post(
        "/api/trafego/meta/local/catalogos/publicos", json={"referencia_opaca": "x"})
    # Referência curta demais: o DTO recusa ANTES de qualquer leitura.
    assert resposta.status_code == 422
    assert chamadas["catalogo_de_publicos"] == 0


def test_catalogo_de_publicos_entrega_o_envelope_inteiro(monkeypatch) -> None:
    _dublar(monkeypatch, catalogo_de_publicos=ENVELOPE_VAZIO)
    corpo = _cliente().post(
        "/api/trafego/meta/local/catalogos/publicos",
        json={"referencia_opaca": "metaacct_exemplo01"}).json()
    # ⚠️ Os cinco estados precisam sobreviver à rota. Um `{"items": [...]}`
    # achatado faria "li tudo e está vazio" virar indistinguível de "não
    # consegui ler".
    for chave in ("estado", "motivo", "retryable", "completo",
                  "paginas_lidas", "observado_em", "ttl_s", "estado_do_catalogo"):
        assert chave in corpo, chave
    assert corpo["estado"] == "VAZIO_COMPLETO"
    assert corpo["completo"] is True


def test_pixel_e_conversao_viajam_separados(monkeypatch) -> None:
    """Achatá-los faria o seletor oferecer um no lugar do outro."""
    _dublar(
        monkeypatch,
        catalogo_de_fontes_de_mensuracao={**ENVELOPE_VAZIO, "catalogo": "measurement_sources"},
        catalogo_de_conversoes_personalizadas={**ENVELOPE_VAZIO, "catalogo": "custom_conversions"},
    )
    corpo = _cliente().post(
        "/api/trafego/meta/local/catalogos/mensuracao",
        json={"referencia_opaca": "metaacct_exemplo01"}).json()
    assert corpo["fontes"]["catalogo"] == "measurement_sources"
    assert corpo["conversoes"]["catalogo"] == "custom_conversions"
    assert "items" not in corpo  # nada de lista única achatada


def test_conta_de_outro_ator_devolve_404(monkeypatch) -> None:
    from app.trafego.meta import dominio as dom

    _dublar(
        monkeypatch,
        catalogo_de_publicos=dom.ContratoMetaInvalido(
            "referencia opaca Meta desconhecida para este operador"))
    resposta = _cliente().post(
        "/api/trafego/meta/local/catalogos/publicos",
        json={"referencia_opaca": "metaacct_deoutroator"})
    assert resposta.status_code == 404


def test_geografia_exige_termo_e_devolve_chaves_do_catalogo(monkeypatch) -> None:
    envelope = {
        **ENVELOPE_VAZIO, "catalogo": "geolocations",
        "items": [{"key": "264443", "name": "Curitiba", "type": "city",
                   "country_code": "BR", "region": "Parana"}],
        "total": 1, "estado": "COM_ITENS",
    }
    chamadas = _dublar(monkeypatch, catalogo_de_geolocalizacoes=envelope)
    cliente = _cliente()
    # Termo curto demais é recusado no DTO, sem leitura.
    assert cliente.post(
        "/api/trafego/meta/local/catalogos/geografia",
        json={"referencia_opaca": "metaacct_exemplo01", "termo": "a"},
    ).status_code == 422
    assert chamadas["catalogo_de_geolocalizacoes"] == 0

    corpo = cliente.post(
        "/api/trafego/meta/local/catalogos/geografia",
        json={"referencia_opaca": "metaacct_exemplo01", "termo": "Curitiba"}).json()
    assert corpo["items"][0]["key"] == "264443"


def test_as_rotas_de_catalogo_nao_escrevem_nada() -> None:
    """`A13`/`A45`: catálogo é leitura; nenhuma delas tem efeito externo."""
    catalogos = [
        rota for rota in meta_local.router.routes if "catalogos" in getattr(rota, "path", "")]
    assert len(catalogos) == 3
    for rota in catalogos:
        assert set(rota.methods) == {"POST"}  # POST por causa do corpo, não por escrever
        for proibido in ("criar", "registrar", "persistir", "ativar", "aprovar"):
            assert proibido not in rota.path
