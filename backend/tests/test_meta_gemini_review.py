import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

_path = Path(__file__).resolve().parents[2] / "scripts/meta_gemini_review.py"
_spec = importlib.util.spec_from_file_location("meta_gemini_review", _path)
review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review)


def answer(lane, **overrides):
    return {"modelVersion": review.MODEL, "candidates": [{"finishReason": "STOP", "content": {"parts": [{"thought": True, "text": "PRIVATE_THOUGHT"}, {"text": json.dumps({"status": "ok", "lane": lane, "findings": []}), "thoughtSignature": "PRIVATE_SIGNATURE"}]}, "groundingMetadata": {"webSearchQueries": ["site:developers.facebook.com flexible ads"], "groundingChunks": [{"web": {"uri": "https://developers.facebook.com/docs/marketing-api/", "title": "Meta"}}], "groundingSupports": []}}], **overrides}


def test_exact_model_high_search_and_no_secret_payload():
    payload = review.payload("master", "creative_contract")
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "high"}
    assert payload["tools"] == [{"google_search": {}}]
    assert "includeThoughts" not in json.dumps(payload)
    result = review.receipt(answer("creative_contract"), "creative_contract")
    assert result["status"] == "ok"
    assert "PRIVATE_" not in json.dumps(result)


def test_model_mismatch_and_missing_search_cannot_pass():
    assert review.receipt(answer("creative_contract", modelVersion="gemini-other"), "creative_contract")["status"] == "model_mismatch"
    data = answer("creative_contract")
    data["candidates"][0].pop("groundingMetadata")
    assert review.receipt(data, "creative_contract")["status"] == "ungrounded"


def test_three_calls_are_bounded_to_two_and_key_never_in_receipt():
    active = peak = count = 0
    async def handler(request):
        nonlocal active, peak, count
        count += 1
        active += 1
        peak = max(peak, active)
        assert request.headers["x-goog-api-key"] == "SECRET_TEST_KEY"
        assert "SECRET_TEST_KEY" not in str(request.url)
        lane = json.loads(request.content)["contents"][0]["parts"][0]["text"].splitlines()[0].split(": ")[1]
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json=answer(lane))
    result = asyncio.run(review.review_round("SECRET_TEST_KEY", "master", transport=httpx.MockTransport(handler)))
    assert count == 3 and peak == 2 and result["calls_attempted"] == 3
    assert result["status"] == "ok" and "SECRET_TEST_KEY" not in json.dumps(result)


def test_auth_failure_does_not_retry_or_start_remaining_lanes():
    count = 0
    async def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(403, json={"error": {"message": "PRIVATE_ERROR"}})
    result = asyncio.run(review.review_round("secret", "master", transport=httpx.MockTransport(handler)))
    assert count == 1 and result["status"] == "partial"
    assert sum(x["status"] == "not_called_after_failure" for x in result["lanes"]) == 2
    assert "PRIVATE_ERROR" not in json.dumps(result)


def test_feedback_is_sanitized_context_not_code_or_identifiers():
    safe = "Distinguish asset_feed_spec from creative_asset_groups_spec. Existing tests prove parent validation. https://developers.facebook.com/docs/marketing-api/"
    assert safe in json.dumps(review.payload("master", "creative_contract", safe))
    for unsafe in ("account 1234567890123", "x@example.com", "```python", "import os", "https://localhost/test", "https://developers.facebook.com/docs/?token=abc", "/Users/private/file"):
        with pytest.raises(ValueError):
            review.checked_feedback(unsafe)


def test_invalid_visible_response_is_kept_but_thought_is_discarded():
    data = answer("creative_contract")
    data["candidates"][0]["content"]["parts"][1]["text"] = '{"status":"ok"'
    result = review.receipt(data, "creative_contract")
    assert result["status"] == "invalid_output"
    assert result["visible_output"] == '{"status":"ok"'
    assert "PRIVATE_" not in json.dumps(result)


def test_nonofficial_citations_never_satisfy_evidence_policy():
    for url in ("https://developers.facebook.com.evil.test/docs", "https://example.com/meta", "http://developers.facebook.com/docs"):
        assert not review.official_meta_url(url)
    assert review.official_meta_url("https://developers.facebook.com/docs/marketing-api/")
    assert review.official_meta_url("https://www.facebook.com/business/help/123")


def test_truncated_response_is_diagnostic_never_accepted():
    data = answer("creative_contract")
    data["candidates"][0]["finishReason"] = "MAX_TOKENS"
    result = review.receipt(data, "creative_contract")
    assert result["status"] == "incomplete_response" and result["visible_output"]
    assert "review" not in result and "PRIVATE_" not in json.dumps(result)


def test_single_authorized_lane_makes_exactly_one_call():
    count = 0
    async def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json=answer("arbitrage_measurement"))
    result = asyncio.run(review.review_round("secret", "master", round_number=2, lanes=["arbitrage_measurement"], transport=httpx.MockTransport(handler)))
    assert count == result["calls_attempted"] == 1
    assert [lane["lane"] for lane in result["lanes"]] == ["arbitrage_measurement"]
