from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.routers import trafego_meta_validacao as routes
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from app.trafego.meta_execucao.registro import RegistroSagaMetaSupabase

HASH = "a" * 64


def receipt(**changes):
    return dict(validation_id="00000000-0000-4000-8000-000000000001", plan_sha256=HASH,
                actor_id="actor-one", coverage="INDEPENDENT_ROOTS_ONLY", steps_validated=["campaign"],
                steps_pending=["adset"], operations_total=2, objects_created=0, accepted=True,
                validated_at=datetime.now(timezone.utc).isoformat()) | changes


def service(row):
    class Service:
        enabled = True
        base = "https://database.agenciavolc.com.br"
        select = AsyncMock(return_value=[] if row is None else [row])
        rpc = AsyncMock(side_effect=AssertionError("read must never write RPC"))
    return Service()


@pytest.mark.asyncio
async def test_lookup_exact_actor_hash_is_read_only_without_write_gate(monkeypatch):
    monkeypatch.delenv("META_CREATE_LEDGER_WRITE_ENABLED", raising=False)
    svc = service(receipt())
    got = await RegistroSagaMetaSupabase(svc).buscar_validacao(plano_sha256=HASH, ator="actor-one", janela_da_validacao_s=1800)
    assert got["plan_sha256"] == HASH and "actor_id" not in got
    assert svc.select.call_args.args[1]["actor_id"] == "eq.actor-one"
    assert svc.select.call_args.args[1]["plan_sha256"] == f"eq.{HASH}"
    assert svc.select.call_args.args[1]["limit"] == 1
    svc.rpc.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes,code", [
    ({"actor_id": "other-actor"}, "META_VALIDATION_RECEIPT_INVALID"),
    ({"plan_sha256": "b" * 64}, "META_VALIDATION_RECEIPT_INVALID"),
    ({"validated_at": (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()}, "META_VALIDATION_RECEIPT_STALE"),
    ({"validated_at": (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}, "META_VALIDATION_RECEIPT_STALE"),
    ({"validated_at": "2026-09-08T12:00:00"}, "META_VALIDATION_RECEIPT_INVALID"),
    ({"objects_created": 1}, "META_VALIDATION_RECEIPT_INVALID"),
])
async def test_lookup_refuses_cross_owner_bad_and_stale_evidence(changes, code):
    with pytest.raises(ErroDeNascimentoMeta) as caught:
        await RegistroSagaMetaSupabase(service(receipt(**changes))).buscar_validacao(
            plano_sha256=HASH, ator="actor-one", janela_da_validacao_s=1800)
    assert caught.value.codigo == code


@pytest.mark.asyncio
async def test_helper_absent_and_stale_proof_never_claims_registered(monkeypatch):
    svc = service(None)
    monkeypatch.setattr(routes, "_registro_saga", lambda: RegistroSagaMetaSupabase(svc))
    monkeypatch.setattr(routes, "_credencial_salva", lambda: pytest.fail("no Meta token read"))
    result = await routes._prova_de_validacao_do_hash(HASH, ator="actor-one")
    assert result == {"registrada": False, "recibo": None}
    svc.select.return_value = [receipt(validated_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat())]
    result = await routes._prova_de_validacao_do_hash(HASH, ator="actor-one")
    assert result["registrada"] is False
    assert result["codigo"] == "META_VALIDATION_RECEIPT_STALE"


@pytest.mark.asyncio
async def test_helper_uses_authenticated_actor_and_current_window(monkeypatch):
    lookup = AsyncMock(return_value=receipt())
    monkeypatch.setattr(routes, "_registro_saga", lambda: type("Registry", (), {"buscar_validacao": lookup})())
    result = await routes._prova_de_validacao_do_hash(HASH, ator="actor-two")
    assert result["registrada"] is True
    assert lookup.call_args.kwargs == {"plano_sha256": HASH, "ator": "actor-two", "janela_da_validacao_s": 1800}


@pytest.mark.parametrize("field,value,code", [
    ("idade_s", None, "META_VALIDATION_RECEIPT_STALE"),
    ("idade_s", -1, "META_VALIDATION_RECEIPT_STALE"),
    ("idade_s", True, "META_VALIDATION_RECEIPT_STALE"),
    ("idade_s", "0", "META_VALIDATION_RECEIPT_STALE"),
    ("objects_created", None, "META_VALIDATION_NOT_CLEAN"),
    ("objects_created", False, "META_VALIDATION_NOT_CLEAN"),
    ("ja_consumido", None, "META_VALIDATION_RECEIPT_ALREADY_USED"),
])
def test_approval_preflight_never_turns_missing_evidence_into_zero(field, value, code):
    from app.routers.trafego_meta_criacao import _exigir_validacao_utilizavel
    row = receipt(idade_s=0, ja_consumido=False)
    row[field] = value
    with pytest.raises(ErroDeNascimentoMeta) as caught:
        _exigir_validacao_utilizavel(row, ator="actor-one", plano_sha256=HASH)
    assert caught.value.codigo == code
