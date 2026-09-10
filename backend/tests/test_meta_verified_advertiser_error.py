"""Provider diagnostics must identify verification blockers without leaking ids."""
from __future__ import annotations

import json

import httpx
import pytest

from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao.executor import (
    ErroRemotoMeta,
    ExecutorMetaPausado,
    _codigo_numerico_do_provedor,
)
from test_meta_paused_birth import (
    TOKEN, RegistroEmMemoria, autorizacao, compilado, formulario, transport_sucesso,
)


@pytest.mark.parametrize("valor,esperado", [
    (100, "100"), (3858634, "3858634"), ("3858634", "3858634"),
    (0, "0"), (None, None), (True, None), (100.0, None),
    ("100 access_token=secret", None), ("act_123456789", None),
    ("1234567890123456", None), (2_147_483_648, None), ("-100", None),
])
def test_only_structured_numeric_codes_bypass_text_redaction(valor, esperado):
    assert _codigo_numerico_do_provedor(valor) == esperado


@pytest.mark.asyncio
@pytest.mark.parametrize("validacao", [True, False])
async def test_verified_advertiser_rejection_is_actionable_and_private(validacao):
    error = {
        "code": 100, "error_subcode": 3858634,
        "error_user_title": "O anunciante está ausente",
        "error_user_msg": "Forneça um anunciante verificado act_1234567890123456",
        "message": "Invalid parameter access_token=EAAfixtureToken123456789",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(400, json={"error": error}),
    )) as client:
        operation = compilado().operacoes[1]
        payload = {"execution_options": ["validate_only"]} if validacao else {"status": "PAUSED"}
        with pytest.raises(ErroRemotoMeta) as caught:
            await ExecutorMetaPausado(client)._post(
                operation, payload, SegredoEfemero(TOKEN), exige_id=not validacao)
    exc = caught.value
    assert exc.codigo == "META_VERIFIED_ADVERTISER_REQUIRED"
    assert exc.detalhe_provedor["code"] == "100"
    assert exc.detalhe_provedor["error_subcode"] == "3858634"
    assert "100/3858634" in str(exc)
    assert "Gerenciador de Anúncios" in str(exc)
    assert "Não alteramos o público" in str(exc)
    serialized = json.dumps(exc.detalhe_provedor) + str(exc)
    assert "1234567890123456" not in serialized
    assert "EAAfixtureToken" not in serialized
    assert exc.retryable is False
    assert exc.criacao_descartada is True


@pytest.mark.asyncio
async def test_same_message_with_different_subcode_is_not_misclassified():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(400, json={"error": {
            "code": 100, "error_subcode": 1885183,
            "message": "O anunciante está ausente",
        }}),
    )) as client:
        with pytest.raises(ErroRemotoMeta) as caught:
            await ExecutorMetaPausado(client)._post(
                compilado().operacoes[1], {"execution_options": ["validate_only"]},
                SegredoEfemero(TOKEN), exige_id=False)
    assert caught.value.codigo == "META_REMOTE_VALIDATION_FAILED"
    assert caught.value.detalhe_provedor["error_subcode"] == "1885183"


@pytest.mark.asyncio
async def test_advertiser_rejection_preserves_partial_campaign_and_stops_dependents():
    requests = []
    success = transport_sucesso(requests)

    async def respond(request):
        if request.method == "POST" and request.url.path.endswith("/adsets"):
            assert "execution_options" in formulario(request)
            return httpx.Response(400, json={"error": {
                "code": 100, "error_subcode": 3858634,
                "message": "Invalid parameter",
            }})
        return await success.handle_async_request(request)

    ledger = RegistroEmMemoria()
    plan = compilado()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ErroRemotoMeta) as caught:
            await ExecutorMetaPausado(client, registro=ledger).criar_pausada(
                plan, SegredoEfemero(TOKEN), autorizacao(plan.plano_sha256))
    exc = caught.value
    assert exc.codigo == "META_VERIFIED_ADVERTISER_REQUIRED"
    assert exc.objetos_criados == ("campaign",)
    assert exc.detalhe_provedor["error_subcode"] == "3858634"
    assert exc.retryable is False
    assert "PAUSED ja criados: campaign" in str(exc)
    assert [edge for method, edge, data in requests if method == "POST" and
            "execution_options" not in data] == ["campaigns"]
    assert ledger.eventos == [
        ("preparar", "campaign"), ("fechar", "campaign"), ("readback", "campaign")]
