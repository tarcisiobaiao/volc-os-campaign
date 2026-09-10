"""Image-only flexible Ads: grouping, immutable approvals and strict readback."""
from copy import deepcopy
from dataclasses import replace
import json

import httpx
import pytest

from app.trafego.meta_execucao.compilador import compilar_plano_v2, descongelar_plano
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from app.trafego.meta_execucao.executor import ExecutorMetaPausado, ErroRemotoMeta
from test_meta_contrato_v2 import _plano_v2, _conjunto, _variacao, _referencias, c2


def flexible():
    measurement = c2.MensuracaoMeta(proposito="OPTIMIZE", source_kind="PIXEL",
        source_ref="metapixel_0123456789", standard_event="CONTENT_VIEW")
    adset = _conjunto(mensuracao=measurement)
    base = _plano_v2(recipe_id="WEB_SALES_CONVERSION", conjuntos=(adset,))
    ads = tuple(c2.AnuncioMeta(replace(_variacao(f"v{i}"), message=f"Texto {i}"), adset.adset_key) for i in range(3))
    return replace(base, anuncios=ads, creative_mode="FLEXIBLE_IMAGES")


def compile_case():
    return compilar_plano_v2(flexible(), _referencias(),
        c2.ReferenciasDePublicoResolvidas(measurement_source_ids={"metapixel_0123456789":"555"}))


def test_one_flexible_ad_per_adset_retains_every_approved_group_and_snapshot():
    compiled = compile_case()
    ads = [op for op in compiled.operacoes if op.tipo_objeto == "ad"]
    creatives = [op for op in compiled.operacoes if op.tipo_objeto == "creative"]
    assert len(ads) == len(creatives) == 1
    groups = ads[0].payload["creative_asset_groups_spec"]["groups"]
    assert len(groups) == 3
    assert [g["texts"][0]["text"] for g in groups] == ["Texto 0", "Texto 1", "Texto 2"]
    assert ads[0].payload["status"] == "PAUSED"
    assert "asset_feed_spec" not in creatives[0].payload
    assert compiled.destino_website_provado
    frozen = descongelar_plano(compiled.congelar())
    assert frozen.plano_sha256 == compiled.plano_sha256
    assert frozen.operacoes[-1].payload["creative_asset_groups_spec"] == ads[0].payload["creative_asset_groups_spec"]


def test_flexible_groups_change_approval_identity():
    plan = flexible()
    changed = replace(plan, anuncios=(replace(plan.anuncios[0], variacao=replace(plan.anuncios[0].variacao, message="Outra copy")), *plan.anuncios[1:]))
    refs = c2.ReferenciasDePublicoResolvidas(measurement_source_ids={"metapixel_0123456789":"555"})
    assert compilar_plano_v2(plan, _referencias(), refs).plano_sha256 != compilar_plano_v2(changed, _referencias(), refs).plano_sha256


def test_flexible_rejects_traffic_mixed_cta_and_existing_post():
    with pytest.raises(ErroDeNascimentoMeta, match="Vendas"):
        replace(_plano_v2(), creative_mode="FLEXIBLE_IMAGES")
    plan = flexible()
    with pytest.raises(ErroDeNascimentoMeta, match="mesmo botão"):
        replace(plan, anuncios=(replace(plan.anuncios[0], variacao=replace(plan.anuncios[0].variacao, call_to_action_type="SIGN_UP")), *plan.anuncios[1:]))
    with pytest.raises(ErroDeNascimentoMeta, match="existentes"):
        replace(plan, anuncios=(replace(plan.anuncios[0], variacao=replace(plan.anuncios[0].variacao, existing_post_ref="metapost_"+"a"*32)), *plan.anuncios[1:]))


def test_readback_accepts_provider_metadata_but_rejects_any_missing_group():
    payload = deepcopy(dict(compile_case().operacoes[-1].payload))
    payload["adset_id"] = "222"
    payload["creative"] = {"creative_id":"333"}
    data = dict(deepcopy(payload), id="444", account_id="123", campaign_id="111", creative={"id":"333"})
    data["creative_asset_groups_spec"]["groups"][0]["group_uuid"] = "provider-metadata"
    def verify():
        ExecutorMetaPausado._validar_read_back("ad", data, payload=payload, identificador="444", ids={"campaign":"111"}, conta_externa="123")
    verify()
    data["creative_asset_groups_spec"]["groups"].pop()
    with pytest.raises(ErroRemotoMeta, match="creative_asset_groups_spec"):
        verify()


def test_flexible_two_adsets_never_cross_group_images_or_names():
    plan = flexible()
    second = replace(plan.conjuntos[0], adset_key="second", nome="Segundo conjunto")
    other = c2.AnuncioMeta(replace(_variacao("other"), message="Somente no segundo"), "second")
    plan = replace(plan, conjuntos=(*plan.conjuntos, second), anuncios=(*plan.anuncios, other))
    compiled = compilar_plano_v2(plan, _referencias(), c2.ReferenciasDePublicoResolvidas(measurement_source_ids={"metapixel_0123456789":"555"}))
    ads = [op for op in compiled.operacoes if op.tipo_objeto == "ad"]
    assert len(ads) == 2
    assert [len(op.payload["creative_asset_groups_spec"]["groups"]) for op in ads] == [3, 1]
    assert ads[1].payload["adset_id"] == "$adset:second.id"


def test_v2_dto_and_summary_preserve_grouping_decision():
    from app.routers.trafego_meta_validacao import PedidoPlanoMetaV2, _plano_v2_do_pedido as parse, _resumo_v2
    from test_meta_rotas_v2 import _corpo
    body = _corpo(recipe_id="WEB_SALES_CONVERSION", creative_mode="FLEXIBLE_IMAGES")
    body["adsets"][0]["measurement"] = {"purpose":"OPTIMIZE", "source_kind":"PIXEL", "source_ref":"metapixel_0123456789", "standard_event":"CONTENT_VIEW"}
    body["ads"].append(dict(body["ads"][0], variation_key="v2", creative_name="Criativo 2", ad_name="Anuncio 2"))
    parsed = parse(PedidoPlanoMetaV2.model_validate(body))
    assert parsed.creative_mode == "FLEXIBLE_IMAGES"
    summary = _resumo_v2(parsed)
    assert summary["total_anuncios_emitidos"] == 1
    assert summary["total_grupos_de_imagem"] == 2
    assert summary["conjuntos"][0]["anuncios"] == ["v1"]


@pytest.mark.anyio
async def test_flexible_ledger_saga_validates_exact_groups_before_paused_dispatch():
    from app.trafego.meta.credenciais import SegredoEfemero
    from test_meta_paused_birth import RegistroEmMemoria, autorizacao, formulario
    compiled = compile_case()
    objects, validated, calls = {}, {}, []
    def graph(request):
        if request.method == "GET":
            return httpx.Response(200, json=objects[request.url.path.rsplit("/", 1)[-1]])
        payload = {}
        for key, value in formulario(request).items():
            try: payload[key] = json.loads(value)
            except ValueError: payload[key] = value
        path = request.url.path
        if "execution_options" in payload:
            payload.pop("execution_options")
            validated[path] = deepcopy(payload)
            return httpx.Response(200, json={"success": True})
        assert payload == validated[path]
        calls.append(path)
        identifier = str(1000 + len(objects))
        payload.update(id=identifier, account_id="1234567890")
        if path.endswith("/ads"):
            assert len(payload["creative_asset_groups_spec"]["groups"]) == 3
            payload["campaign_id"] = "1000"
            payload["creative"] = {"id":str(payload["creative"]["creative_id"])}
        objects[identifier] = payload
        return httpx.Response(200, json={"id":identifier})
    ledger = RegistroEmMemoria()
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as client:
        result = await ExecutorMetaPausado(client, registro=ledger).criar_pausada(
            compiled, SegredoEfemero("fake-token"), autorizacao(compiled.plano_sha256))
    assert result.desfecho == "CREATED_PAUSED"
    assert len(calls) == 4
    assert sum(event == "readback" for event, _ in ledger.eventos) == 4
