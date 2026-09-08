"""No provider calls: previews and management proposals never dispatch changes."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.routers import meta_local, trafego_meta_validacao
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta.gestao import PedidoDeGestaoMeta, planejar_gestao
from app.trafego.meta_execucao.compilador import TRACKING_GAM_ADSET_ID
from app.trafego.meta_execucao.tracking import apresentar_tracking


def pedido(**patch):
    return PedidoDeGestaoMeta.model_validate(dict(
        conta_ref="metaacct_teste", campanha_ref="metaobj_campanha",
        referencia="metaobj_conjunto", entidade="conjunto", acao="PAUSAR", **patch))


class Repo:
    def __init__(self):
        self.campanha = {"meta_campaign_id": "uuid-c", "entity_ref": "metaobj_campanha", "nome": "Campanha"}
        self.conjunto = {"meta_campaign_id": "uuid-c", "entity_ref": "metaobj_conjunto", "nome": "Conjunto", "status": "ACTIVE", "external_id": "DO_NOT_EXPOSE"}

    async def detalhe(self, tipo, ref, conta):
        assert conta == "metaacct_teste"
        return {"estado": "COM_SNAPSHOT", "item": self.campanha if tipo == "campanhas" else self.conjunto}


@pytest.mark.asyncio
async def test_pause_is_proposal_only_and_never_echoes_raw_identifiers():
    repo = Repo()
    original = deepcopy(repo.conjunto)
    r = await planejar_gestao(repo, pedido(), ator="admin")
    assert r["executavel"] is False and r["persistida"] is False
    assert r["efeito_externo"] == "NENHUM"
    assert r["antes"]["daily_budget"] is None
    assert r["depois"] == {"status": "PAUSED"}
    assert "DO_NOT_EXPOSE" not in str(r)
    assert repo.conjunto == original


@pytest.mark.asyncio
async def test_other_campaign_is_refused():
    repo = Repo()
    repo.conjunto["meta_campaign_id"] = "other"
    with pytest.raises(ValueError, match="Conjunto não encontrado"):
        await planejar_gestao(repo, pedido(), ator="admin")


@pytest.mark.asyncio
async def test_changed_snapshot_or_actor_changes_hash():
    repo = Repo()
    a = await planejar_gestao(repo, pedido(), ator="admin")
    b = await planejar_gestao(repo, pedido(), ator="other")
    repo.conjunto["daily_budget"] = "5000"
    c = await planejar_gestao(repo, pedido(), ator="admin")
    assert len({r["plano_sha256"] for r in (a,b,c)}) == 3


@pytest.mark.asyncio
async def test_copy_preserves_history_and_demands_tracking_recompile():
    p = pedido().model_dump()
    p.update(acao="DUPLICAR_CONJUNTO", nome="Cópia")
    r = await planejar_gestao(Repo(), PedidoDeGestaoMeta(**p), ator="admin")
    assert r["depois"]["status"] == "PAUSED"
    assert r["depois"]["incluir_anuncios"] is True
    assert any("novo ID" in x for x in r["requisitos_para_executar"])


@pytest.mark.parametrize("patch", [
    {"acao": "ATIVAR"}, {"status": "ACTIVE"},
    {"acao": "ORCAMENTO_DIARIO", "valor_minor": 0},
    {"acao": "ORCAMENTO_DIARIO", "valor_minor": True},
    {"acao": "ORCAMENTO_DIARIO", "valor_minor": 12.5},
    {"acao": "LANCE", "estrategia": "COST_CAP"},
    {"acao": "LANCE", "estrategia": "LOWEST_COST_WITHOUT_CAP", "valor_minor": 100},
    {"acao": "PAUSAR", "valor_minor": 100},
    {"acao": "DUPLICAR_CONJUNTO", "entidade": "campanha", "nome": "Cópia"},
])
def test_invalid_intents_are_rejected(patch):
    data = pedido().model_dump()
    data.update(patch)
    with pytest.raises(ValidationError):
        PedidoDeGestaoMeta(**data)


def test_tracking_preserves_query_fragment_and_dynamic_macros():
    r = apresentar_tracking("https://example.com/page?lang=pt#conteudo")
    assert r["template"] == TRACKING_GAM_ADSET_ID
    assert r["previa_url"] == f"https://example.com/page?lang=pt&{TRACKING_GAM_ADSET_ID}#conteudo"
    assert r["prova"] == "TEMPLATE_LOCAL"


@pytest.mark.parametrize("query", ["utm_campaign=old", "%75tm_campaign=old", "UTM_CONTENT=old", "placement="])
def test_preflight_blocks_conflicts_without_silently_removing_them(query):
    r = apresentar_tracking("https://example.com/?" + query)
    assert not r["destino_valido"]
    assert r["previa_url"] is None
    assert r["erro"]["codigo"] == "META_DESTINATION_TRACKING_CONFLICT"


def test_routes_never_resolve_meta_token(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("Meta token must not be touched")
    monkeypatch.setattr(meta_local, "_credencial_salva", forbidden)
    monkeypatch.setattr(trafego_meta_validacao, "_credencial_salva", forbidden)
    monkeypatch.setattr(meta_local, "_repositorio_read_model", lambda: Repo())
    app = FastAPI()
    app.include_router(meta_local.router)
    app.include_router(trafego_meta_validacao.router)
    app.dependency_overrides[exigir_admin] = lambda: Identidade("admin", "test@example.com", "ADMIN", "sessao")
    client = TestClient(app, headers={"host": "localhost"})
    assert client.get("/api/trafego/meta/local/criacao/tracking").status_code == 200
    r = client.post("/api/trafego/meta/local/gestao/planejar", json=pedido().model_dump())
    assert r.status_code == 200 and r.json()["executavel"] is False
    assert client.post("/api/trafego/meta/local/gestao/executar", json={}).status_code == 404
    denied = client.get("/api/trafego/meta/local/criacao/tracking", headers={"host": "evil.example"})
    assert denied.status_code in {403, 404}
