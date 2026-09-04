from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers import meta_local
from app.routers.meta_local import _mascarar_id
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta.configuracao_local import CredencialLocal, nome_da_conta_local


def test_credencial_serializa_para_o_chaveiro_sem_perder_carimbo() -> None:
    credencial = CredencialLocal.agora("token-de-prova-que-nao-e-real")
    reconstruida = CredencialLocal.de(credencial.serializar())
    assert reconstruida == credencial
    assert json.loads(credencial.serializar())["token"] == "token-de-prova-que-nao-e-real"


def test_resposta_publica_mascara_ids_e_conta_local_nao_usa_email() -> None:
    assert _mascarar_id("act_123456789") == "••••6789"
    assert _mascarar_id(None) is None
    assert nome_da_conta_local("uuid-seguro") == "supabase-user:uuid-seguro"


class _ChaveiroEmMemoria:
    def __init__(self) -> None:
        self.itens: dict[str, str] = {}

    def salvar(self, conta: str, valor: str) -> None:
        self.itens[conta] = valor

    def ler(self, conta: str) -> str:
        return self.itens[conta]

    def remover(self, conta: str) -> bool:
        return self.itens.pop(conta, None) is not None


def _cliente() -> TestClient:
    app = FastAPI()
    app.include_router(meta_local.router)
    quem = Identidade(sub="u-meta", email="admin@volc", papel="ADMIN", origem="sessao")
    app.dependency_overrides[exigir_admin] = lambda: quem
    return TestClient(app, headers={"host": "localhost"})


def _leitura_valida() -> dict[str, Any]:
    return {
        "ok": True,
        "api_version": "v26.0",
        "ator": {"nome": "System User", "id_mascarado": "••••1234"},
        "contas": [],
        "contas_acessiveis": 0,
    }


def test_rota_valida_antes_de_salvar_e_nunca_devolve_token(monkeypatch) -> None:
    chaveiro = _ChaveiroEmMemoria()

    async def testar(token: str) -> dict[str, Any]:
        assert token == "token-de-sistema-meta-valido"
        assert not chaveiro.itens
        return _leitura_valida()

    monkeypatch.setattr(meta_local, "_chaveiro", lambda: chaveiro)
    monkeypatch.setattr(meta_local, "_testar_token", testar)
    resposta = _cliente().post(
        "/api/trafego/meta/local/configuracao",
        json={"token": "token-de-sistema-meta-valido"},
    )
    assert resposta.status_code == 200
    assert chaveiro.itens
    assert "token-de-sistema-meta-valido" not in resposta.text


def test_token_recusado_nao_e_persistido(monkeypatch) -> None:
    chaveiro = _ChaveiroEmMemoria()

    async def recusar(_: str) -> dict[str, Any]:
        raise HTTPException(status_code=422, detail="Token recusado")

    monkeypatch.setattr(meta_local, "_chaveiro", lambda: chaveiro)
    monkeypatch.setattr(meta_local, "_testar_token", recusar)
    resposta = _cliente().post(
        "/api/trafego/meta/local/configuracao",
        json={"token": "token-de-sistema-meta-recusado"},
    )
    assert resposta.status_code == 422
    assert chaveiro.itens == {}


def test_atalho_provisorio_recusa_host_nao_local(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    cliente = _cliente()
    resposta = cliente.get(
        "/api/trafego/meta/local/configuracao",
        headers={"host": "volc.example.com"},
    )
    assert resposta.status_code == 404
