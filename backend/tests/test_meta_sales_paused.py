"""Hermetic dispatch contract, not remote provider acceptance evidence."""
from dataclasses import replace
from datetime import timedelta
import json

import httpx
import pytest

from test_meta_contrato_v2 import _plano_v2, _conjunto, _variacao, _referencias, c2, receitas
from test_meta_paused_birth import RegistroEmMemoria, autorizacao, formulario
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao.compilador import compilar_plano_v2
from app.trafego.meta_execucao.contrato import DESTINO_SHOP_CONTA_NAO_ELEGIVEL
from app.trafego.meta_execucao.executor import ExecutorMetaPausado, ErroRemotoMeta


def sales_plan(mode, event, advantage):
    lifetime, cbo = mode.endswith("lifetime"), mode.startswith("cbo")
    period = receitas.PERIODO_TOTAL if lifetime else receitas.PERIODO_DIARIO
    measurement = c2.MensuracaoMeta(proposito=receitas.MENSURACAO_OTIMIZACAO,
        source_kind=c2.FONTE_PIXEL, source_ref="metapixel_0123456789",
        standard_event=event if event != "CUSTOM" else None,
        custom_conversion_ref="metacc_0123456789ab" if event == "CUSTOM" else None)
    audience = replace(_conjunto().publico, expansao_advantage=advantage)
    adset = _conjunto("canary", mensuracao=measurement, publico=audience,
        orcamento=None if cbo else c2.OrcamentoMeta(nivel=receitas.ORCAMENTO_NO_CONJUNTO,
            periodo=period, amount_minor=1000),
        fim=_conjunto().programacao.start_time+timedelta(days=3) if lifetime else None)
    plan = _plano_v2(recipe_id="WEB_SALES_CONVERSION", conjuntos=(adset,),
        anuncios=(c2.AnuncioMeta(variacao=_variacao(), adset_key="canary"),),
        orcamento_campanha=c2.OrcamentoMeta(nivel=receitas.ORCAMENTO_NA_CAMPANHA,
            periodo=period, amount_minor=1000) if cbo else None)
    refs = c2.ReferenciasDePublicoResolvidas(measurement_source_ids={"metapixel_0123456789":"555"},
        custom_conversion_ids={"metacc_0123456789ab":"777"} if event == "CUSTOM" else {})
    return compilar_plano_v2(plan, replace(_referencias(),
        shop_redirect_proof=DESTINO_SHOP_CONTA_NAO_ELEGIVEL), refs)


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["abo_daily","cbo_daily","abo_lifetime","cbo_lifetime"])
@pytest.mark.parametrize("event", ["CONTENT_VIEW", "CUSTOM"])
@pytest.mark.parametrize("advantage", [False, True])
async def test_sales_exact_event_budget_and_advantage_validate_before_each_paused_create(mode,event,advantage):
    compiled = sales_plan(mode,event,advantage)
    objects, validated, acts = {}, {}, []
    def graph(request):
        if request.method == "GET":
            return httpx.Response(200,json=objects[request.url.path.rsplit("/",1)[-1]])
        payload = {}
        for key,value in formulario(request).items():
            try: payload[key] = json.loads(value)
            except ValueError: payload[key] = value
        path = request.url.path
        if "execution_options" in payload:
            payload.pop("execution_options")
            validated[path] = payload
            acts.append(("validate",path))
            return httpx.Response(200,json={"success":True})
        assert payload == validated[path]
        acts.append(("create",path))
        if path.endswith("/adsets"):
            expected = {"pixel_id":"555", **({"custom_conversion_id":"777"} if event == "CUSTOM" else {"custom_event_type":event})}
            assert payload["promoted_object"] == expected
            assert payload["targeting"]["targeting_automation"]["advantage_audience"] == int(advantage)
        identifier = str(1001+len(objects))
        payload.update(id=identifier,account_id="1234567890")
        if path.endswith("/ads"):
            payload["campaign_id"] = objects[str(payload["adset_id"])]["campaign_id"]
            payload["creative"] = {"id":str(payload["creative"]["creative_id"])}
        objects[identifier] = payload
        return httpx.Response(200,json={"id":identifier})
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as client:
        result = await ExecutorMetaPausado(client,registro=RegistroEmMemoria()).criar_pausada(
            compiled,SegredoEfemero("fake-token"),autorizacao(compiled.plano_sha256))
    assert result.desfecho == "CREATED_PAUSED"
    assert len(objects)==4
    assert all(obj["status"] == "PAUSED" for obj in objects.values() if "object_story_spec" not in obj)
    assert [kind for kind,_ in acts] == ["validate","create"]*4
    assert receitas.WEB_SALES_CONVERSION.prova == "FIELD_SHAPE_ONLY"


@pytest.mark.anyio
async def test_sales_dependent_validation_rejection_never_creates_rejected_adset():
    compiled = sales_plan("abo_daily","CONTENT_VIEW",False)
    created=[]
    def graph(request):
        if request.method == "GET":
            return httpx.Response(200,json=dict(compiled.operacoes[0].payload,id="1001",account_id="1234567890"))
        payload=formulario(request)
        if request.url.path.endswith("/adsets"):
            assert "execution_options" in payload
            return httpx.Response(400,json={"error":{"code":100,"message":"ineligible event"}})
        if "execution_options" in payload:
            return httpx.Response(200,json={"success":True})
        created.append(payload)
        return httpx.Response(200,json={"id":"1001"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as client:
        with pytest.raises(ErroRemotoMeta):
            await ExecutorMetaPausado(client,registro=RegistroEmMemoria()).criar_pausada(
                compiled,SegredoEfemero("fake-token"),autorizacao(compiled.plano_sha256))
    assert len(created)==1 and created[0]["status"]=="PAUSED"
