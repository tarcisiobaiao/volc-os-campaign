from copy import deepcopy

import pytest

from app.trafego.meta_execucao.orcamento_aprovado import conferir_orcamento, manifesto_orcamentario
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta


def snapshot(*, cbo=False, lifetime=False, count=2):
    field = "lifetime_budget" if lifetime else "daily_budget"
    campaign = {field: 5000} if cbo else {}
    ops = [{"nome": "campaign", "tipo": "campaign", "payload": campaign}]
    for i in range(count):
        ops.append({"nome": f"adset:s{i}", "tipo": "adset", "payload": {
            **({} if cbo else {field: 1000 * (i + 1)}), "end_time": "2026-10-01T12:00:00Z",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "optimization_goal": "LANDING_PAGE_VIEWS"}})
        ops.extend([{"nome": f"creative:a{i}", "tipo": "creative", "payload": {}},
                    {"nome": f"ad:a{i}", "tipo": "ad", "payload": {}}])
    return {"operacoes": ops}


@pytest.mark.parametrize("cbo,lifetime,total", [(False,False,3000),(True,False,5000),(False,True,None),(True,True,None)])
def test_financial_manifest_preserves_scope_period_and_every_set(cbo,lifetime,total):
    plan = snapshot(cbo=cbo,lifetime=lifetime)
    manifest = manifesto_orcamentario(plan)
    assert manifest["scope"] == ("CBO" if cbo else "ABO")
    assert manifest["daily_total_minor"] == total
    assert len(manifest["adsets"]) == 2
    conferir_orcamento(plan, {"budget_manifest": manifest,"daily_budget_minor":total})
    changed = deepcopy(plan)
    changed["operacoes"][1]["payload"]["end_time"] = "2027-01-01T00:00:00Z"
    with pytest.raises(ErroDeNascimentoMeta,match="manifesto"):
        conferir_orcamento(changed,{"budget_manifest":manifest,"daily_budget_minor":total})


def test_changing_second_abo_budget_cannot_hide_behind_first():
    plan = snapshot()
    manifest = manifesto_orcamentario(plan)
    plan["operacoes"][4]["payload"]["daily_budget"] = 7000
    with pytest.raises(ErroDeNascimentoMeta):
        conferir_orcamento(plan,{"budget_manifest":manifest,"daily_budget_minor":3000})


def test_legacy_manifest_only_allows_original_single_daily_adset():
    plan = snapshot(count=1)
    with pytest.raises(ErroDeNascimentoMeta):
        conferir_orcamento(plan,{"daily_budget_minor":1000})
    plan["operacoes"][1]["nome"] = "adset"
    conferir_orcamento(plan,{"daily_budget_minor":1000})


@pytest.mark.parametrize("amount", [True,0,-1,1.5,"1000",9007199254740992])
def test_invalid_financial_values_fail_closed(amount):
    plan = snapshot()
    plan["operacoes"][1]["payload"]["daily_budget"] = amount
    with pytest.raises(ErroDeNascimentoMeta):
        manifesto_orcamentario(plan)


def test_ten_sets_ten_ads_fit_but_eleventh_ad_does_not():
    plan=snapshot(count=10)
    assert len(plan["operacoes"]) == 31
    assert manifesto_orcamentario(plan)["daily_total_minor"] == 55000
    plan["operacoes"].append({"nome":"ad:extra","tipo":"ad","payload":{}})
    with pytest.raises(ErroDeNascimentoMeta):
        manifesto_orcamentario(plan)


def test_cbo_cannot_also_charge_abo():
    plan=snapshot(cbo=True)
    plan["operacoes"][1]["payload"]["daily_budget"]=1000
    with pytest.raises(ErroDeNascimentoMeta):
        manifesto_orcamentario(plan)


def test_v2_approval_route_compiles_actual_v2_and_seals_every_budget(monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers import trafego_meta_criacao as router, trafego_meta_validacao as validation
    from app.seguranca.identidade import Identidade, exigir_admin
    from app.trafego.meta_execucao.compilador import compilar_plano_v2
    from test_meta_contrato_v2 import _referencias, ASSET, CONTA, PAGINA, INICIO
    payload={"recipe_id":"TRAFFIC_WEBSITE_LPV_STATIC","account_ref":CONTA,"page_ref":PAGINA,
        "campaign_name":"Test V2 approval","destination_url":"https://example.com/offer",
        "special_categories_confirmed":True,
        "adsets":[{"adset_key":f"s{i}","name":f"Set {i}","start_time":INICIO.isoformat(),
            "audience":{"mode":"BROAD","geo":{"countries":["BR"]},"expansion":False},
            "budget":{"nivel":"ADSET","periodo":"DAILY","amount_minor":1000*(i+1)}} for i in range(2)],
        "ads":[{"variation_key":f"a{i}","adset_key":f"s{i}","asset_ref":ASSET,"creative_name":f"Creative {i}",
            "ad_name":f"Ad {i}","message":"Message","headline":"Headline","description":"Description",
            "asset_rights_confirmed":True,"third_party_identity_cleared":True,
            "asset_policy_confirmed_at":datetime.now(timezone.utc).isoformat()} for i in range(2)]}
    dto=validation.PedidoPlanoMetaV2.model_validate(payload)
    compiled=compilar_plano_v2(validation._plano_v2_do_pedido(dto),_referencias())
    captured={}
    class Ledger:
        async def consultar_validacao(self, _):
            return {"plan_sha256":compiled.plano_sha256,"actor_id":"operator","coverage":"INDEPENDENT_ROOTS_ONLY",
                    "accepted":True,"objects_created":0,"idade_s":0}
        async def aprovar(self, **kw):
            captured.update(kw)
            return {"approval_id":"approval-test-123","expires_at":kw["expires_at"].isoformat()}
    async def compile_v2(*args,**kw): return compiled
    async def credential(*args,**kw): return SimpleNamespace(token="fake-test-token")
    monkeypatch.setenv("META_CREATE_LEDGER_WRITE_ENABLED","1")
    monkeypatch.setattr(router,"_registro_saga",Ledger)
    monkeypatch.setattr(router,"_compilar_v2",compile_v2)
    monkeypatch.setattr(router,"credencial_operacional",credential)
    app=FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[exigir_admin]=lambda: Identidade(sub="operator",email="operator@example.com",papel="ADMIN",origem="sessao")
    response=TestClient(app,headers={"host":"localhost"}).post("/api/trafego/meta/local/criacao/aprovar",json={
        "plano":payload,"plano_sha256_esperado":compiled.plano_sha256,"validation_id":"validation-test-123",
        "confirmar_nascimento_pausado":True,"confirmacao_digitada":"CRIAR PAUSADA"})
    assert response.status_code == 200,response.text
    assert captured["daily_budget_minor"] == 3000
    assert len(captured["passos_esperados"]) == 7
    assert response.json()["aprovacao"]["budget_manifest"] == manifesto_orcamentario(compiled.congelar())


def test_missing_v2_schema_returns_named_error_without_secret(monkeypatch):
    import asyncio
    import httpx
    from app.trafego.meta_execucao.registro import RegistroSagaMetaSupabase
    class MissingSchema:
        enabled=True
        async def rpc(self,*args):
            req=httpx.Request("POST","https://database.example.invalid/rest/v1/rpc/test")
            response=httpx.Response(404,json={"code":"PGRST202","message":"sensitive details"},request=req)
            response.raise_for_status()
    monkeypatch.setenv("META_CREATE_LEDGER_WRITE_ENABLED","1")
    with pytest.raises(ErroDeNascimentoMeta) as exc:
        asyncio.run(RegistroSagaMetaSupabase(MissingSchema())._rpc("test",{}))
    assert exc.value.codigo == "META_CREATE_SCHEMA_REQUIRED"
    assert "sensitive" not in str(exc.value)
