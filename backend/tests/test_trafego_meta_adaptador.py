from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from app.trafego.meta import adaptador as adp
from app.trafego.meta.credenciais import SegredoEfemero


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_base_url_fora_do_host_oficial_e_recusada():
    with pytest.raises(ValueError, match="graph.facebook.com"):
        adp.AdaptadorMetaSomenteLeitura(
            None, base_url="https://evil.invalid")  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_le_hierarquia_paginada_so_com_get_bearer_e_cursor():
    chamadas: list[httpx.Request] = []

    def responder(req: httpx.Request) -> httpx.Response:
        chamadas.append(req)
        edge = req.url.path.rsplit("/", 1)[-1]
        params = parse_qs(req.url.query.decode())
        after = params.get("after", [None])[0]
        if edge == "campaigns" and after is None:
            return httpx.Response(200, json={
                "data": [{"id": "10", "name": "C1", "status": "PAUSED",
                          "effective_status": "PAUSED", "objective": "OUTCOME_TRAFFIC"}],
                "paging": {"next": "https://nao-segue.example/roubo",
                           "cursors": {"after": "cursor-1"}},
            })
        if edge == "campaigns":
            return httpx.Response(200, json={"data": []})
        if edge == "adsets":
            return httpx.Response(200, json={"data": [
                {"id": "20", "campaign_id": "10", "name": "S1",
                 "status": "PAUSED", "effective_status": "PAUSED",
                 "optimization_goal": "LANDING_PAGE_VIEWS"}]})
        if edge == "ads":
            return httpx.Response(200, json={"data": [
                {"id": "30", "adset_id": "20", "name": "A1",
                 "status": "PAUSED", "effective_status": "PAUSED",
                 "creative": {"id": "40"}}]})
        if edge == "adcreatives":
            return httpx.Response(200, json={"data": [
                {"id": "40", "name": "CR1", "object_story_id": "page_99"}]})
        raise AssertionError(edge)

    token = "segredo-que-nao-pode-ir-na-url"
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        leitura = await adp.AdaptadorMetaSomenteLeitura(cliente).ler_hierarquia(
            "act_123", SegredoEfemero(token))

    assert leitura.paginas_lidas == 5
    assert leitura.contagens == {
        "campaign": 1, "adset": 1, "ad": 1, "creative": 1}
    assert leitura.anuncios[0].creative_id_externo == "40"
    assert all(req.method == "GET" for req in chamadas)
    assert all(req.url.host == "graph.facebook.com" for req in chamadas)
    assert all(token not in str(req.url) for req in chamadas)
    assert all("access_token" not in parse_qs(req.url.query.decode()) for req in chamadas)
    assert all(req.headers["authorization"] == f"Bearer {token}" for req in chamadas)


@pytest.mark.anyio
@pytest.mark.parametrize(("status", "codigo", "retryable"), [
    (401, "META_AUTHENTICATION_FAILED", False),
    (403, "META_PERMISSIONS_INSUFFICIENT", False),
    (404, "META_ACCOUNT_INACCESSIBLE", False),
    (429, "META_RATE_LIMIT", True),
    (503, "META_REMOTE_FAILURE", True),
])
async def test_erros_http_sao_tipados_e_nao_repetem_corpo(status, codigo, retryable):
    material = "token-vazado-pelo-provedor"

    def responder(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": material}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        with pytest.raises(adp.ErroDeLeituraMeta) as erro:
            await adp.AdaptadorMetaSomenteLeitura(cliente).ler_hierarquia(
                "123", SegredoEfemero("outro-segredo"))
    assert erro.value.codigo == codigo
    assert erro.value.retryable is retryable
    assert material not in str(erro.value)


@pytest.mark.anyio
async def test_timeout_e_retryable_sem_conteudo_sensivel():
    def responder(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("segredo-no-timeout", request=req)

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        with pytest.raises(adp.ErroDeLeituraMeta) as erro:
            await adp.AdaptadorMetaSomenteLeitura(cliente).ler_hierarquia(
                "123", SegredoEfemero("token"))
    assert erro.value.codigo == "META_TRANSPORT_FAILURE"
    assert erro.value.retryable is True
    assert "segredo-no-timeout" not in str(erro.value)


@pytest.mark.anyio
async def test_paging_next_sem_cursor_e_recusado_sem_seguir_url():
    chamadas = 0

    def responder(req: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        return httpx.Response(200, json={
            "data": [], "paging": {"next": "https://evil.invalid/token"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        with pytest.raises(adp.ErroDeLeituraMeta) as erro:
            await adp.AdaptadorMetaSomenteLeitura(cliente).ler_hierarquia(
                "123", SegredoEfemero("token"))
    assert chamadas == 1
    assert erro.value.codigo == "META_INVALID_PAGINATION"
