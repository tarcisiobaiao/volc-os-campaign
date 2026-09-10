"""Exercise the real saga with multiple parents and non-V1 budgets."""
from dataclasses import replace
from copy import deepcopy
from datetime import datetime, timedelta
import json

import httpx
import pytest

from test_meta_contrato_v2 import _plano_v2, _conjunto, _variacao, _referencias, c2, receitas
from test_meta_paused_birth import RegistroEmMemoria, autorizacao, formulario
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao.compilador import compilar_plano_v2
from app.trafego.meta_execucao.contrato import DESTINO_SHOP_CONTA_NAO_ELEGIVEL
from app.trafego.meta_execucao.executor import ExecutorMetaPausado, ErroRemotoMeta, _inicio_confere


@pytest.mark.anyio
@pytest.mark.parametrize("budget", ["abo_daily", "cbo_daily", "abo_lifetime", "cbo_lifetime"])
@pytest.mark.parametrize("ad_effective_status", ["PAUSED", "CAMPAIGN_PAUSED", "ADSET_PAUSED"])
async def test_two_adsets_real_saga_preserves_parent_and_budget(budget, ad_effective_status):
    lifetime = budget.endswith("lifetime")
    cbo = budget.startswith("cbo")
    period = receitas.PERIODO_TOTAL if lifetime else receitas.PERIODO_DIARIO
    conjuntos = tuple(_conjunto(key, nome=key, orcamento=None if cbo else c2.OrcamentoMeta(
        nivel=receitas.ORCAMENTO_NO_CONJUNTO, periodo=period, amount_minor=amount),
        fim=_conjunto().programacao.start_time + timedelta(days=3) if lifetime else None)
        for key, amount in [("primeiro", 1000), ("segundo", 2300)])
    plan = _plano_v2(conjuntos=conjuntos,
        anuncios=tuple(c2.AnuncioMeta(variacao=_variacao(f"v{i}"), adset_key=c.adset_key)
                       for i, c in enumerate(conjuntos)),
        orcamento_campanha=c2.OrcamentoMeta(nivel=receitas.ORCAMENTO_NA_CAMPANHA,
            periodo=period, amount_minor=4500) if cbo else None)
    compiled = compilar_plano_v2(plan, replace(_referencias(),
        shop_redirect_proof=DESTINO_SHOP_CONTA_NAO_ELEGIVEL))
    objects = {}
    def graph(request):
        if request.method == "GET":
            return httpx.Response(200, json=objects[request.url.path.rsplit("/", 1)[-1]])
        raw = formulario(request)
        if "execution_options" in raw:
            return httpx.Response(200, json={"success": True})
        payload = {}
        for k, v in raw.items():
            try: payload[k] = json.loads(v)
            except ValueError: payload[k] = v
        identifier = str(1001 + len(objects))
        payload.update(id=identifier, account_id="1234567890")
        if request.url.path.endswith("/ads"):
            payload["campaign_id"] = objects[str(payload["adset_id"])]["campaign_id"]
            payload["creative"] = {"id": str(payload["creative"]["creative_id"])}
            payload["effective_status"] = ad_effective_status
        if request.url.path.endswith("/adsets"):
            payload["effective_status"] = "CAMPAIGN_PAUSED"
            # A saved draft's start can elapse before its PAUSED creation.
            # Model the exact provider normalization observed on the incident.
            requested = datetime.fromisoformat(payload["start_time"])
            payload["created_time"] = (requested + timedelta(minutes=78)).isoformat()
            payload["start_time"] = payload["created_time"]
        if request.url.path.endswith("/adcreatives"):
            payload["status"] = "ACTIVE"
        objects[identifier] = payload
        return httpx.Response(200, json={"id": identifier})
    ledger = RegistroEmMemoria()
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as client:
        result = await ExecutorMetaPausado(client, registro=ledger).criar_pausada(
            compiled, SegredoEfemero("fake-test-token"), autorizacao(compiled.plano_sha256))
    assert result.desfecho == "CREATED_PAUSED"
    ads = [v for v in objects.values() if "adset_id" in v]
    assert len(ads) == 2
    assert len({str(v["adset_id"]) for v in ads}) == 2
    assert len(objects) == 7
    assert all(v["status"] == "PAUSED" for v in objects.values() if "object_story_spec" not in v)
    assert sum(1 for event, _ in ledger.eventos if event == "readback") == 7


@pytest.mark.parametrize("read,expected,created,accepted", [
    ("2026-09-09T10:54:04-0300", "2026-09-09T12:36:00+00:00", "2026-09-09T10:54:04-0300", True),
    ("2026-09-09T13:54:04+00:00", "2026-09-09T14:36:00+00:00", "2026-09-09T13:54:04+00:00", False),
    ("2026-09-09T13:54:05+00:00", "2026-09-09T12:36:00+00:00", "2026-09-09T13:54:04+00:00", False),
    ("2026-09-09T13:54:04+00:00", "2026-09-09T12:36:00+00:00", None, False),
    ("2026-09-09T13:54:04", "2026-09-09T12:36:00", "2026-09-09T13:54:04", False),
])
def test_start_normalization_only_accepts_elapsed_start_at_proven_creation(read, expected, created, accepted):
    assert _inicio_confere(read, expected, created) is accepted


@pytest.mark.parametrize("categories,identity,accepted", [
    (["BRAZIL_REGULATION", "VOLUNTARY_VERIFICATION"], "123", True),
    (["BRAZIL_REGULATION"], "123", True),
    (["VOLUNTARY_VERIFICATION"], "123", False),
    (["BRAZIL_REGULATION", "OTHER_REGULATION"], "123", False),
    (["BRAZIL_REGULATION", "VOLUNTARY_VERIFICATION"], "999", False),
])
def test_regulatory_readback_accepts_only_additive_verification_marker(categories, identity, accepted):
    payload, data = _readback_case()
    payload.update(regional_regulated_categories=["BRAZIL_REGULATION"],
        regional_regulation_identities={"universal_beneficiary":"123", "universal_payer":"456"})
    data.update(regional_regulated_categories=categories,
        regional_regulation_identities={"universal_beneficiary":identity, "universal_payer":"456"})
    def check():
        ExecutorMetaPausado._validar_read_back("adset", data, payload=payload,
            identificador="1002", ids={"campaign": "1001"}, conta_externa="1234567890")
    if accepted:
        check()
    else:
        with pytest.raises(ErroRemotoMeta, match="regional_"):
            check()


@pytest.mark.parametrize("effective_status", ["CAMPAIGN_PAUSED", "ADSET_PAUSED"])
def test_inherited_pause_never_substitutes_own_paused_status(effective_status):
    payload, data = _readback_case()
    data.update(configured_status="ACTIVE", effective_status=effective_status)
    with pytest.raises(ErroRemotoMeta, match="no campo status"):
        ExecutorMetaPausado._validar_read_back("adset", data, payload=payload,
            identificador="1002", ids={"campaign": "1001"}, conta_externa="1234567890")


@pytest.mark.parametrize("effective_status", ["ACTIVE", "WITH_ISSUES", "DISAPPROVED", "ADSET_PAUSED"])
def test_adset_still_rejects_unsafe_or_wrong_hierarchy_effective_status(effective_status):
    payload, data = _readback_case()
    data["effective_status"] = effective_status
    with pytest.raises(ErroRemotoMeta, match="no campo effective_status"):
        ExecutorMetaPausado._validar_read_back("adset", data, payload=payload,
            identificador="1002", ids={"campaign": "1001"}, conta_externa="1234567890")


def _readback_case():
    payload = {"name": "Set", "campaign_id": "1001", "status": "PAUSED",
        "billing_event": "IMPRESSIONS", "optimization_goal": "OFFSITE_CONVERSIONS",
        "daily_budget": 1200, "start_time": "2027-01-02T12:00:00+00:00",
        "end_time": "2027-01-05T12:00:00+00:00",
        "promoted_object": {"pixel_id": "777", "custom_event_type": "CONTENT_VIEW"},
        "targeting": {"geo_locations": {"countries": ["BR"], "regions": [{"key": "3847"}]},
                      "publisher_platforms": ["facebook"], "custom_audiences": [{"id": "888"}]}}
    data = dict(deepcopy(payload), id="1002", account_id="1234567890")
    return payload, data


@pytest.mark.parametrize("changed", ["budget", "event", "pixel", "end", "region", "audience"])
def test_v2_readback_refuses_material_changes(changed):
    payload, data = _readback_case()
    if changed == "budget": data["daily_budget"] = "1201"
    if changed == "event": data["promoted_object"]["custom_event_type"] = "PURCHASE"
    if changed == "pixel": data["promoted_object"]["pixel_id"] = "999"
    if changed == "end": data["end_time"] = "2027-01-06T12:00:00+00:00"
    if changed == "region": data["targeting"]["geo_locations"]["regions"][0]["key"] = "0"
    if changed == "audience": data["targeting"]["custom_audiences"][0]["id"] = "0"
    with pytest.raises(ErroRemotoMeta, match="divergiu"):
        ExecutorMetaPausado._validar_read_back("adset", data, payload=payload,
            identificador="1002", ids={"campaign": "1001"}, conta_externa="1234567890")


def test_ad_cannot_be_adopted_into_other_set():
    payload = {"name": "Ad", "status": "PAUSED", "adset_id": "1003", "creative": {"creative_id": "1004"}}
    data = dict(payload, id="1005", account_id="1234567890", campaign_id="1001",
                adset_id="1002", creative={"id": "1004"})
    with pytest.raises(ErroRemotoMeta, match="adset_id"):
        ExecutorMetaPausado._validar_read_back("ad", data, payload=payload, identificador="1005",
            ids={"campaign": "1001", "adset:one": "1002", "adset:two": "1003"}, conta_externa="1234567890")
