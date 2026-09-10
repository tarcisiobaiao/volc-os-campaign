import asyncio
import importlib.util
import json
from pathlib import Path

import httpx

_spec = importlib.util.spec_from_file_location("code_review", Path(__file__).resolve().parents[2] / "scripts/meta_gemini_code_review.py")
code = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(code)


def test_allowlist_bundle_has_exact_four_sources_and_scans_clean():
    bundle, files, digest = code.code_bundle()
    assert tuple(item['path'] for item in files) == code.ALLOWLIST
    assert len(files) == 4 and len(digest) == 64
    assert 'FILE: backend/app/routers/trafego_meta_copy.py\n1:' in bundle


def test_one_request_exact_model_no_thoughts_and_no_bundle_in_receipt(monkeypatch):
    requests = []
    async def handler(request):
        requests.append(request)
        body = json.loads(request.content)
        assert body['generationConfig']['thinkingConfig'] == {'thinkingLevel': 'high'}
        assert body['tools'] == [{'google_search': {}}]
        return httpx.Response(200, json={'modelVersion': code.MODEL, 'candidates': [{
            'finishReason': 'STOP', 'content': {'parts': [
                {'thought': True, 'text': 'PRIVATE_THOUGHT'},
                {'text': json.dumps({'status': 'ok', 'findings': [], 'limitations': [], 'conclusion': 'No local defect proven.'}), 'thoughtSignature': 'PRIVATE_SIGNATURE'}]}}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(code.httpx, 'AsyncClient', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    result = asyncio.run(code.run('SECRET_KEY', 'CODE_BUNDLE', [], 'a' * 64))
    assert len(requests) == result['calls_attempted'] == 1 and result['status'] == 'ok'
    assert result['grounding_verified'] is False  # Fine for local-code findings, not API claims.
    output = json.dumps(result)
    assert all(private not in output for private in ('SECRET_KEY', 'CODE_BUNDLE', 'PRIVATE_THOUGHT', 'PRIVATE_SIGNATURE'))


def test_http_failure_is_not_retried_and_body_not_exposed(monkeypatch):
    requests = []
    async def handler(request):
        requests.append(request)
        return httpx.Response(403, json={'error': 'PRIVATE_ERROR'})
    original = httpx.AsyncClient
    monkeypatch.setattr(code.httpx, 'AsyncClient', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    result = asyncio.run(code.run('secret', 'source', [], 'a' * 64))
    assert len(requests) == 1 and result['status'] == 'http_error'
    assert 'PRIVATE_ERROR' not in json.dumps(result)
