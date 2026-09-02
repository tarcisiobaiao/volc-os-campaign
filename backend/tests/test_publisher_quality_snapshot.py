from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.publisher_quality import (
    SnapshotInput,
    build_publisher_surface_snapshot,
    deterministic_json,
)
from backend.app.publisher_quality.fetch import validate_public_https_target


def _fixture_payload() -> dict:
    return {
        "site_id": "site-fg",
        "project_id": "proj-volc",
        "canonical_url": "https://example.com/artigo/",
        "page_type": "article",
        "template_key": "single-post",
        "content_category": "beneficios",
        "ad_layout_version": "ads-v1",
        "device_class": "mobile",
        "html": """
        <html><head>
          <link rel="canonical" href="https://example.com/artigo/" />
          <script async src="https://securepubads.g.doubleclick.net/tag/js/gpt.js"></script>
          <script async src="https://securepubads.g.doubleclick.net/tag/js/gpt.js"></script>
          <script>window.dataLayer = window.dataLayer || [];
          dataLayer.push({event:'page_context', page_type:'article', template_key:'single-post', email:'reader@example.com'});
          googletag.defineSlot('/1234567/site/home_top', ['fluid', [300,250], [320,100]], 'div-gpt-top');
          googletag.defineSlot('/1234567/site/home_mid', ['fluid'], 'div-gpt-mid');
          googletag.pubads().enableSingleRequest();
          googletag.pubads().refresh();
          </script>
        </head><body>
          <div id="div-gpt-top" data-ad-slot="top" style="min-height:0px"></div>
          <div id="div-gpt-mid" data-ad-slot="mid" data-ad-placement="btf"></div>
          <div id="div-gpt-mid" data-ad-slot="mid-copy"></div>
        </body></html>
        """,
        "ad_manifest": {
            "slots": [
                {
                    "slot_id": "top",
                    "page_role": "LP",
                    "placement": "hero",
                    "sizes": ["300x250"],
                    "min_height_px": 250,
                    "refresh_eligible": False,
                    "source_key": "newsletter",
                },
                {
                    "slot_id": "manifest-only",
                    "page_role": "LP",
                    "placement": "footer",
                    "sizes": [],
                    "min_height_px": 0,
                    "refresh_eligible": False,
                    "source_key": "",
                },
            ]
        },
    }


def test_snapshot_preserves_absence_statuses_and_never_collapses_to_zero_false_or_empty_list():
    payload = _fixture_payload()
    payload.pop("content_category")
    payload["html"] = "<html><head></head><body><div id='ad-without-size'></div></body></html>"

    snapshot = build_publisher_surface_snapshot(SnapshotInput.from_mapping(payload))

    assert snapshot["page"]["content_category"]["status"] == "absent_confirmed"
    assert "value" not in snapshot["page"]["content_category"]
    first_slot = snapshot["slots"][0]
    assert first_slot["accepted_sizes"]["status"] in {"absent_confirmed", "unavailable"}
    assert "value" not in first_slot["accepted_sizes"]
    assert first_slot["reserved_dimensions"]["status"] in {"absent_confirmed", "unavailable"}
    assert "value" not in first_slot["reserved_dimensions"]


def test_snapshot_detects_required_publisher_risks_and_manifest_dom_divergence():
    snapshot = build_publisher_surface_snapshot(SnapshotInput.from_mapping(_fixture_payload()))
    codes = {finding["code"] for finding in snapshot["findings"]}

    assert "GPT_LOADER_DUPLICATED" in codes
    assert "DIV_ID_DUPLICATED" in codes
    assert "SLOT_WITHOUT_RESERVED_SPACE" in codes
    assert "FLUID_ATF" in codes
    assert "BTF_WITHOUT_LAZY_LOAD_EVIDENCE" in codes
    assert "REFRESH_WITHOUT_OBSERVABLE_POLICY" in codes
    assert "POSSIBLE_PERSONAL_DATA_IN_DATALAYER" in codes
    assert "ADMANIFEST_DOM_DIVERGENCE" in codes
    assert snapshot["page"]["canonical_url"]["value"] == "https://example.com/artigo/"
    assert snapshot["page"]["host"]["value"] == "example.com"
    assert snapshot["page"]["path"]["value"] == "/artigo/"


def test_snapshot_json_is_deterministic(tmp_path: Path):
    payload = _fixture_payload()
    one = build_publisher_surface_snapshot(SnapshotInput.from_mapping(payload))
    two = build_publisher_surface_snapshot(SnapshotInput.from_mapping(payload))

    assert deterministic_json(one) == deterministic_json(two)
    parsed = json.loads(deterministic_json(one))
    assert parsed["schema"] == "PublisherSurfaceSnapshot"


def test_public_https_target_validation_fails_closed_for_ssrf_vectors():
    bad_urls = [
        "http://example.com/",
        "https://localhost/",
        "https://127.0.0.1/admin",
        "https://10.0.0.5/",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/",
    ]
    for url in bad_urls:
        with pytest.raises(ValueError):
            validate_public_https_target(url)


def test_public_https_target_validation_accepts_public_https_without_fetching():
    result = validate_public_https_target("https://example.com/news?utm_source=x#frag")
    assert result == "https://example.com/news"
