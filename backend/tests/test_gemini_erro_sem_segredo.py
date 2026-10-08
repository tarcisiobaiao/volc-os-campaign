from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.llm.gemini import GeminiClient


@pytest.mark.asyncio
async def test_erro_http_nao_expoe_api_key(monkeypatch):
    segredo = "chave-que-nao-pode-aparecer"
    settings = Settings(gemini_api_key=segredo)
    cliente = GeminiClient(settings, model="modelo-inexistente")

    class Resposta:
        status_code = 404

        def raise_for_status(self):
            req = httpx.Request("POST", f"https://example.test?key={segredo}")
            resp = httpx.Response(404, request=req)
            raise httpx.HTTPStatusError("404", request=req, response=resp)

    class Http:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, *_args, **_kwargs):
            return Resposta()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: Http())
    with pytest.raises(RuntimeError) as erro:
        await cliente.complete("sistema", "missão")

    texto = str(erro.value)
    assert segredo not in texto
    assert texto == "Gemini HTTP 404 no modelo modelo-inexistente"
