"""Official v26 explicit control, with strict readback and legacy compatibility."""
from copy import deepcopy
from dataclasses import replace
import hashlib

import pytest

from test_meta_paused_birth import compilado, resposta_lida
from app.trafego.meta_execucao.compilador import descongelar_plano, _materia_do_plano, _canonico
from app.trafego.meta_execucao.contrato import DESTINO_SHOP_CONTA_NAO_ELEGIVEL
from app.trafego.meta_execucao.executor import ExecutorMetaPausado, ErroRemotoMeta, _evidencia_do_readback


def test_new_control_does_not_claim_account_ineligibility():
    plan = compilado()
    assert plan.shop_redirect_proof == "EXPLICIT_WEBSITE_SHOP_OPT_OUT"
    assert plan.opt_out_website_explicito and plan.destino_website_provado
    assert plan.publico()["controle_destino"] == "EXPLICIT_OPT_OUT_REQUIRES_READBACK"
    assert descongelar_plano(plan.congelar()).opt_out_website_explicito


@pytest.mark.parametrize("value", ["WEBSITE_AND_SHOP_OPT_OUT", "private-unrecognized", {"token":"never-persist"}])
def test_destination_read_evidence_is_allowlisted(value):
    evidence = _evidencia_do_readback("creative", {"destination_spec":{"destination_type":value}}, conferido=True)
    assert evidence["destination_type_lido"] == (value if value == "WEBSITE_AND_SHOP_OPT_OUT" else None)


@pytest.mark.parametrize("mutation", ["remove", "shop", "existing_post", "other_url"])
def test_marker_alone_cannot_authorize_changed_creative(mutation):
    plan = deepcopy(compilado())
    creative = next(op for op in plan.operacoes if op.tipo_objeto == "creative")
    if mutation == "remove": creative.payload.pop("destination_spec")
    if mutation == "shop": creative.payload["destination_spec"] = {"destination_type":"WEBSITE_AND_SHOP"}
    if mutation == "existing_post": creative.payload["object_story_id"] = "123_456"
    if mutation == "other_url": creative.payload["object_story_spec"]["link_data"]["link"] = "https://other.example/"
    assert not plan.opt_out_website_explicito
    assert not plan.destino_website_provado


@pytest.mark.parametrize("destination", [None, {}, {"destination_type":"WEBSITE_AND_SHOP"}, {"destination_type":"WEBSITE"}])
def test_missing_or_divergent_optout_readback_fails_closed(destination):
    plan = compilado()
    creative = next(op for op in plan.operacoes if op.tipo_objeto == "creative")
    read = resposta_lida("creative","1003")
    read["destination_spec"] = destination
    with pytest.raises(ErroRemotoMeta, match="destination_spec"):
        ExecutorMetaPausado._validar_read_back("creative",read,payload=creative.payload,
            identificador="1003",ids={"campaign":"1001","adset":"1002"},conta_externa="1234567890")


def test_legacy_frozen_snapshot_preserves_old_payload_and_proof():
    plan = deepcopy(compilado())
    for op in plan.operacoes:
        op.payload.pop("destination_spec",None)
    plan = replace(plan,shop_redirect_proof=DESTINO_SHOP_CONTA_NAO_ELEGIVEL)
    identity = hashlib.sha256(_canonico(_materia_do_plano(api_version=plan.api_version,
        account_ref=plan.account_ref,destination_url=plan.destination_url,
        shop_redirect_proof=plan.shop_redirect_proof,
        asset_supply=[s.prova_publica() for s in plan.asset_supply_manifests],operacoes=plan.operacoes)).encode()).hexdigest()
    plan = replace(plan,plano_sha256=identity)
    restored = descongelar_plano(plan.congelar())
    assert restored.shop_redirect_proof == DESTINO_SHOP_CONTA_NAO_ELEGIVEL
    assert restored.destino_website_provado and not restored.opt_out_website_explicito
    assert all("destination_spec" not in op.payload for op in restored.operacoes)


def test_legacy_readback_does_not_require_new_optout():
    payload = deepcopy(next(op.payload for op in compilado().operacoes if op.tipo_objeto == "creative"))
    payload.pop("destination_spec")
    read = resposta_lida("creative","1003");read.pop("destination_spec")
    ExecutorMetaPausado._validar_read_back("creative",read,payload=payload,
        identificador="1003",ids={"campaign":"1001","adset":"1002"},conta_externa="1234567890")
