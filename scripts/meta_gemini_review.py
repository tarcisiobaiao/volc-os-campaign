"""Bounded paid review; reads credentials locally, emits receipts only to stdout.

No retries, writes, model fallback, thought traces, or execution of model output.
Root owns durable run receipts and must save stdout as ROUND-1.json/ROUND-2.json
before any later invocation. A second round requires a new explicit approval.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gemini-3.8-flash"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
RUN = ROOT / ".claude-ads/runs/meta-context-review-20260910"
MASTER = ROOT / "docs/closure/meta-context-review-20260910/MASTER-PROMPT.md"

# Human-authored allowlist: no source code, live identifiers, account data or URLs.
SUMMARY = """
SANITIZED ARCHITECTURE, observed 2026-09-10; implementation claims are not remote proofs:
1. Guided browser flow has durable owner-scoped draft versions and stable ad-set
keys. Ad variations belong to exactly one ad set. Every set must contain an ad;
duplicate local keys and unknown parents are rejected. Draft changes invalidate
compiled-plan approval. Account and Page are selected before final preparation.
2. STATIC images and existing-post modes are distinct from FLEXIBLE_IMAGES. The
flexible contract currently allows sales objectives only, no existing-post refs,
one CTA type per set. Per-set explicit pools contain primary_text/headline each
1..5 strings, optional description 0..5; limits are 2200/255/255 Unicode characters.
Legacy paired copy can be derived into distinct pools. Explicit duplicate entries
count toward limits. Existing images are uploaded separately from campaign create.
3. Flexible groups are emitted on ads as creative_asset_groups_spec and included
in readback. Creative readback includes object_story_spec, object_story_id,
effective_object_story_id, url_tags, asset_feed_spec and degrees_of_freedom_spec.
Existing-post readback compares effective or declared story ID with the selected
post. Local packs preserve image/copy provenance but are not existing social posts.
4. Text generation is separate from image generation. Images use gpt-image-2,
quality medium, an approved visual specification and explicit inner-art text;
external ad copy is separate. Human image review authorizes selected media, not
automatic campaign activation. Optional textual suggestions are reviewed before
applying and never silently mutate the durable draft.
5. Launch performs compilation, validate_only, explicit approval tied to the
plan hash, then PAUSED creation through a durable step ledger. A timeout after
create is ambiguous, requiring reconciliation, not blind retry. Missing durable
receipt after a remote object exists likewise requires readback reconciliation.
The frontend is moving validation into automatic preflight with actionable
failures while preserving the final human approval. Partial creation is possible
across campaign, ad sets, creative objects and ads and must be recoverable.
6. Measurement distinguishes standard pixel events (such as ViewContent), custom
conversions and their dataset/pixel source. Publisher revenue remains at ad-set
granularity. Dynamic tracking uses ad-set IDs in utm_campaign and utm_term, ad ID
in utm_content, campaign ID in a separate parameter. This is a local attribution
contract, not a universal Meta requirement. CAPI delivery/deduplication and
advertiser identity eligibility need separate proofs; do not assume they exist.
7. ABO is used to explore creatives and CBO to expand selected tests. No automatic
profitability thresholds or bid changes are authorized. Reuse should preserve
eligible post/social proof without implying transfer of historical ad metrics.
No source code or account-level evidence is supplied; report missing proof honestly.
""".strip()

LANES = {
    "creative_contract": "Verify flexible creative groups, current supported objectives, text/asset limits, CTA constraints, existing object_story_id reuse and social-proof compatibility. Identify actual API constraints versus local restrictions.",
    "launch_recovery": "Verify automated validate_only preflight limitations, dependency ordering, idempotent partial creation/reconciliation and advertiser identity. Propose minimal human checkpoints without hiding errors or duplicating remote objects.",
    "arbitrage_measurement": "Verify bidding/optimization and CAPI source/event/dedup distinctions for editorial arbitrage. Propose minimum-step UX for context, pools and ABO to CBO reuse. Keep publisher revenue versus conversion value distinct; no invented ROAS optimization entitlement.",
}


def checked_feedback(text: str) -> str:
    """Reject, rather than silently transmit, content outside review authorization."""
    if len(text) > 16000:
        raise ValueError("Feedback exceeds sanitized review limit")
    forbidden = r"(?i)(?:AIza[\w-]{15,}|sk-[\w-]{15,}|eyJ[\w-]{15,}|\b\d{12,}\b|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f-]{23}\b|/Users/|/private/|```|\b(?:access_token|api_key|authorization)\s*[=:])"
    if re.search(forbidden, text) or re.search(r"(?m)^\s*(?:import |from \S+ import |def |class |export |function |const |SELECT |INSERT |CREATE TABLE)", text):
        raise ValueError("Feedback must be a human-authored sanitized architectural summary, not secrets, IDs or code")
    for url in re.findall(r"https?://[^\s<>\"')]+", text):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or not official_meta_url(url):
            raise ValueError("Feedback URLs must be canonical official Meta HTTPS references without query parameters")
    return text.strip()


def official_meta_url(url) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and not parsed.username and not parsed.password and (host == "developers.facebook.com" or (host in {"facebook.com", "www.facebook.com"} and parsed.path.startswith("/business/")))
    except ValueError:
        return False


def payload(master: str, lane: str, feedback: str = "") -> dict:
    feedback = checked_feedback(feedback)
    suffix = f"\n\nINTEGRATOR FEEDBACK — VERIFY AND ADDRESS, DO NOT REPEAT THE FIRST REVIEW:\n{feedback}" if feedback else ""
    return {
        "systemInstruction": {"parts": [{"text": master}]},
        "contents": [{"role": "user", "parts": [{"text": f"LANE: {lane}\nTASK: {LANES[lane]}\n\n{SUMMARY}{suffix}"}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"thinkingConfig": {"thinkingLevel": "high"}, "temperature": 0.3, "maxOutputTokens": 16000},
    }


def receipt(data: dict, lane: str) -> dict:
    """Allowlist provider metadata; never retain thought parts or signatures."""
    version = data.get("modelVersion")
    result = {"lane": lane, "modelVersion": version, "model_verified": version == MODEL}
    usage = data.get("usageMetadata", {})
    result["usage"] = {key: usage[key] for key in ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "toolUsePromptTokenCount", "totalTokenCount") if isinstance(usage.get(key), int)}
    candidates = data.get("candidates", [])
    candidate = candidates[0] if candidates else {}
    grounding = candidate.get("groundingMetadata", {})
    result["grounding"] = {key: grounding.get(key, []) for key in ("webSearchQueries", "groundingChunks", "groundingSupports")}
    result["grounding_verified"] = bool(grounding.get("webSearchQueries") and grounding.get("groundingChunks"))
    result["finishReason"] = candidate.get("finishReason")
    if version != MODEL:
        return {**result, "status": "model_mismatch"}
    text = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", []) if not part.get("thought") and isinstance(part.get("text"), str)).strip()
    if candidate.get("finishReason") != "STOP":
        return {**result, "status": "incomplete_response", "visible_output": text[:80000], "output_sha256": hashlib.sha256(text.encode()).hexdigest()}
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    try:
        output = json.loads(text)
        assert isinstance(output, dict) and output.get("lane") == lane
        assert output.get("status") in {"ok", "partial", "blocked"}
        assert isinstance(output.get("findings"), list) and len(output["findings"]) <= 8
        for finding in output["findings"]:
            assert isinstance(finding, dict)
            assert all(isinstance(finding.get(key), str) for key in ("id", "severity", "confidence", "support", "claim", "current_contract", "proposal", "acceptance_test"))
            assert isinstance(finding.get("sources"), list)
            assert finding["support"] in {"evidence_based", "hypothesis", "unsupported"}
            assert finding["confidence"] in {"high", "medium", "low", "none"}
    except (ValueError, AssertionError, TypeError):
        return {**result, "status": "invalid_output", "output_sha256": hashlib.sha256(text.encode()).hexdigest(), "visible_output": text[:80000]}
    result["official_source_policy_ok"] = all(finding["support"] != "evidence_based" or (finding["sources"] and all(isinstance(source, dict) and official_meta_url(source.get("url")) for source in finding["sources"])) for finding in output["findings"])
    status = "ungrounded" if not result["grounding_verified"] else "ok" if result["official_source_policy_ok"] else "unverified_sources"
    return {**result, "status": status, "review": output}


async def review_round(key: str, master: str, *, round_number: int = 1, transport=None, lanes=None, feedback: str = "") -> dict:
    lanes = tuple(LANES if lanes is None else lanes)
    if not lanes or len(lanes) > 3 or len(set(lanes)) != len(lanes) or any(lane not in LANES for lane in lanes):
        raise ValueError("Invalid bounded lane selection")
    semaphore = asyncio.Semaphore(2)
    stop = asyncio.Event()
    async with httpx.AsyncClient(timeout=240, transport=transport) as client:
        async def call(lane: str) -> dict:
            async with semaphore:
                if stop.is_set():
                    return {"lane": lane, "status": "not_called_after_failure", "attempted": False}
                request = payload(master, lane, feedback)
                digest = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                base = {"lane": lane, "attempted": True, "request_sha256": digest}
                try:
                    response = await client.post(ENDPOINT, headers={"x-goog-api-key": key}, json=request)
                    if response.status_code != 200:
                        stop.set()
                        return {**base, "status": "http_error", "http_status": response.status_code}
                    parsed = receipt(response.json(), lane)
                    if parsed["status"] != "ok":
                        stop.set()
                    return {**base, **parsed}
                except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                    stop.set()
                    return {**base, "status": "transport_or_response_error"}
        results = await asyncio.gather(*(call(lane) for lane in lanes))
    return {"schema_version": 1, "round": round_number, "created_at": datetime.now(timezone.utc).isoformat(), "requested_model": MODEL, "thinking_level": "high", "google_search_requested": True, "concurrency_limit": 2, "round_call_limit": 3, "total_authorized_rounds_limit": 2, "calls_attempted": sum(item["attempted"] for item in results), "status": "ok" if all(item["status"] == "ok" for item in results) else "partial", "lanes": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, choices=(1, 2), default=1)
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--authorize-second-round", action="store_true")
    parser.add_argument("--complete-round-one", action="store_true", help="Only call previously unattempted lanes from a saved partial ROUND-1 receipt; never retries a lane.")
    parser.add_argument("--feedback-file", type=Path, help="Human-authored sanitized feedback for round two; never raw provider output or code.")
    parser.add_argument("--lane", choices=tuple(LANES), action="append", help="Second-round lane subset, useful when only one paid lane is authorized.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    master = MASTER.read_text(encoding="utf-8")
    try:
        feedback = checked_feedback(args.feedback_file.read_text(encoding="utf-8")) if args.feedback_file else ""
    except (OSError, ValueError):
        parser.error("Feedback file missing or outside the sanitized architectural contract.")
    if args.round == 2 and not feedback:
        parser.error("Round two requires explicit integrator feedback; do not repeat an identical prompt.")
    if args.lane and (args.round != 2 or len(set(args.lane)) != len(args.lane)):
        parser.error("Lane subsets are unique and available only for separately authorized round two.")
    if args.dry_run:
        print(json.dumps({lane: payload(master, lane, feedback) for lane in (args.lane or LANES)}, ensure_ascii=False))
        return 0
    if not args.allow_paid or (args.round == 2 and not args.authorize_second_round):
        parser.error("Explicit paid authorization and separate second-round authorization are required.")
    if not (RUN / "RUN-MANIFEST.json").exists():
        parser.error("Create the run manifest before paid research.")
    prior = None
    pending = args.lane
    receipt_path = RUN / f"ROUND-{args.round}.json"
    if args.complete_round_one:
        if args.round != 1 or not receipt_path.exists():
            parser.error("Completing a round requires its first-round receipt.")
        prior = json.loads(receipt_path.read_text(encoding="utf-8"))
        if prior.get("round") != 1 or prior.get("requested_model") != MODEL or len(prior.get("lanes", [])) != 3:
            parser.error("Incompatible prior receipt.")
        pending = [item["lane"] for item in prior["lanes"] if item.get("attempted") is False and item.get("status") == "not_called_after_failure"]
        if not pending or prior.get("calls_attempted", 3) + len(pending) > 3:
            parser.error("No unused calls remain in round one.")
    elif receipt_path.exists():
        parser.error("A receipt already exists for this round; do not repeat paid calls.")
    if args.round == 2 and not (RUN / "ROUND-1.json").exists():
        parser.error("Save first-round receipt before a separately approved second round.")
    sys.path.insert(0, str(ROOT / "backend"))
    from app.config import Settings
    key = Settings(_env_file=(ROOT / ".env.server", ROOT / "backend/.env", ROOT / "backend/.env.local")).resolved_gemini_key
    if not key:
        print(json.dumps({"status": "blocked", "reason": "gemini_key_missing", "calls_attempted": 0}))
        return 2
    result = asyncio.run(review_round(key, master, round_number=args.round, lanes=pending, feedback=feedback))
    result["feedback_sha256"] = hashlib.sha256(feedback.encode()).hexdigest() if feedback else None
    if prior:
        new = {item["lane"]: item for item in result["lanes"]}
        result["lanes"] = [new.get(item["lane"], item) for item in prior["lanes"]]
        result["calls_attempted"] = sum(item["attempted"] for item in result["lanes"])
        result["status"] = "ok" if all(item["status"] == "ok" for item in result["lanes"]) else "partial"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
