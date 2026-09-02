from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.parse import urlparse

STATUSES = {"observed", "absent_confirmed", "unavailable", "not_applicable", "failed"}
SCHEMA_VERSION = "publisher_surface_snapshot.v1"
DETERMINISTIC_OBSERVED_AT = "1970-01-01T00:00:00Z"


@dataclass(frozen=True)
class SnapshotInput:
    site_id: str | None = None
    project_id: str | None = None
    canonical_url: str | None = None
    host: str | None = None
    path: str | None = None
    page_type: str | None = None
    template_key: str | None = None
    content_category: str | None = None
    ad_layout_version: str | None = None
    device_class: str | None = None
    html: str = ""
    ad_manifest: dict[str, Any] | None = None
    data_layer: list[dict[str, Any]] | None = None
    observed_at: str = DETERMINISTIC_OBSERVED_AT
    source: str = "local_artifact"

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "SnapshotInput":
        return cls(
            site_id=payload.get("site_id"),
            project_id=payload.get("project_id"),
            canonical_url=payload.get("canonical_url"),
            host=payload.get("host"),
            path=payload.get("path"),
            page_type=payload.get("page_type"),
            template_key=payload.get("template_key") or payload.get("template"),
            content_category=payload.get("content_category"),
            ad_layout_version=payload.get("ad_layout_version"),
            device_class=payload.get("device_class"),
            html=payload.get("html") or "",
            ad_manifest=payload.get("ad_manifest") or payload.get("adManifest"),
            data_layer=payload.get("data_layer") or payload.get("dataLayer"),
            observed_at=payload.get("observed_at") or DETERMINISTIC_OBSERVED_AT,
            source=payload.get("source") or "local_artifact",
        )


class _SurfaceHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical_href: str | None = None
        self.scripts: list[dict[str, str]] = []
        self.divs: list[dict[str, Any]] = []
        self._in_script = False
        self._script_attrs: dict[str, str] = {}
        self._script_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        amap: dict[str, str] = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "link" and amap.get("rel", "").lower() == "canonical":
            self.canonical_href = amap.get("href") or self.canonical_href
        if tag.lower() == "script":
            self._in_script = True
            self._script_attrs = amap
            self._script_text = []
        if tag.lower() == "div":
            self.divs.append({"id": amap.get("id"), "attrs": amap})

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_script:
            self.scripts.append({**self._script_attrs, "text": "".join(self._script_text)})
            self._in_script = False
            self._script_attrs = {}
            self._script_text = []


def _field(value: Any, *, status: str | None = None, evidence: str = "input", observed_at: str = DETERMINISTIC_OBSERVED_AT) -> dict[str, Any]:
    if status is None:
        status = "observed" if value not in (None, "") else "absent_confirmed"
    item = {"status": status, "evidence": evidence}
    if status == "observed":
        item["value"] = value
        item["observed_at"] = observed_at
    return item


def _finding(code: str, message: str, *, severity: str = "risk", evidence: Any = None) -> dict[str, Any]:
    out = {"code": code, "severity": severity, "message": message}
    if evidence is not None:
        out["evidence"] = evidence
    return out


def _parse_html(html: str) -> _SurfaceHTMLParser:
    parser = _SurfaceHTMLParser()
    parser.feed(html or "")
    return parser


def _canonical_parts(explicit: str | None, html_canonical: str | None) -> tuple[str | None, str | None, str | None, list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    canonical = explicit or html_canonical
    if explicit and html_canonical and explicit.rstrip("/") != html_canonical.rstrip("/"):
        findings.append(_finding("CANONICAL_CONTRADICTORY", "canonical_url input diverges from DOM canonical link", evidence={"input": explicit, "dom": html_canonical}))
    if not canonical:
        findings.append(_finding("CANONICAL_HOST_PATH_ABSENT", "canonical URL, host or path absent", severity="observation"))
        return None, None, None, findings
    parsed = urlparse(canonical)
    if not parsed.scheme or not parsed.netloc:
        findings.append(_finding("CANONICAL_HOST_PATH_ABSENT", "canonical URL is not absolute", evidence=canonical))
        return canonical, None, None, findings
    return canonical, parsed.netloc.lower(), parsed.path or "/", findings


def _script_text(parser: _SurfaceHTMLParser) -> str:
    return "\n".join(s.get("text", "") for s in parser.scripts)


def _gpt_loader_count(parser: _SurfaceHTMLParser) -> int:
    count = 0
    for script in parser.scripts:
        src = script.get("src", "")
        text = script.get("text", "")
        if "securepubads.g.doubleclick.net/tag/js/gpt.js" in src or "googletagservices.com/tag/js/gpt.js" in src:
            count += 1
        if "gpt.js" in text and "securepubads.g.doubleclick.net" in text:
            count += 1
    return count


def _parse_define_slots(text: str) -> dict[str, dict[str, Any]]:
    slots: dict[str, dict[str, Any]] = {}
    pattern = re.compile(r"defineSlot\(\s*(['\"])(?P<unit>.*?)\1\s*,\s*(?P<sizes>.*?)\s*,\s*(['\"])(?P<div>.*?)\4\s*\)", re.S)
    for m in pattern.finditer(text or ""):
        div_id = m.group("div")
        slots[div_id] = {
            "div_id": div_id,
            "ad_unit_path": _sanitize_ad_unit_path(m.group("unit")),
            "accepted_sizes": _sizes_from_js(m.group("sizes")),
            "loader": "gpt.defineSlot",
        }
    return slots


def _sizes_from_js(raw: str) -> list[str]:
    raw = raw or ""
    sizes = [f"{w}x{h}" for w, h in re.findall(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]", raw)]
    if re.search(r"['\"]fluid['\"]", raw, re.I):
        sizes.insert(0, "fluid")
    return list(dict.fromkeys(sizes))


def _sanitize_ad_unit_path(path: str) -> str:
    parts = [p for p in (path or "").split("/") if p]
    if parts and parts[0].isdigit():
        parts[0] = "<network>"
    return "/" + "/".join(parts)


def _parse_style_min_height(style: str) -> int | None:
    m = re.search(r"min-height\s*:\s*(\d+)px", style or "", re.I)
    return int(m.group(1)) if m else None


def _position(attrs: dict[str, str], manifest_slot: dict[str, Any] | None) -> str | None:
    text = " ".join(str(x) for x in [attrs.get("data-ad-position"), attrs.get("data-ad-placement"), attrs.get("class"), attrs.get("id"), (manifest_slot or {}).get("placement")]).lower()
    if any(token in text for token in ["atf", "above", "hero", "top"]):
        return "ATF"
    if any(token in text for token in ["btf", "below", "footer", "mid", "inline"]):
        return "BTF"
    return None


def _manifest_slots(ad_manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for slot in (ad_manifest or {}).get("slots", []) or []:
        key = slot.get("slot_id") or slot.get("slot_key") or slot.get("div_id")
        if key:
            out[str(key)] = dict(slot)
    return out


def _extract_data_layer(payload: SnapshotInput, parser: _SurfaceHTMLParser) -> list[dict[str, Any]]:
    if payload.data_layer is not None:
        return payload.data_layer
    pushes: list[dict[str, Any]] = []
    for obj in re.findall(r"dataLayer\.push\s*\(\s*\{(.*?)\}\s*\)", _script_text(parser), re.S):
        found: dict[str, Any] = {}
        for key, val in re.findall(r"([A-Za-z0-9_]+)\s*:\s*['\"]([^'\"]*)['\"]", obj):
            found[key] = val
        pushes.append(found)
    return pushes


def _data_layer_findings(data_layer: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if len(data_layer) > 25:
        findings.append(_finding("DATALAYER_DANGEROUS_CARDINALITY", "dataLayer has more than 25 observed pushes", evidence={"pushes": len(data_layer)}))
    pii_keys = re.compile(r"(^|_)(email|e_mail|phone|telefone|cpf|cnpj|name|nome|address|endereco|gclid_raw)($|_)", re.I)
    email_val = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
    for idx, item in enumerate(data_layer):
        for key, value in item.items():
            if pii_keys.search(str(key)) or email_val.search(str(value)):
                findings.append(_finding("POSSIBLE_PERSONAL_DATA_IN_DATALAYER", "possible personal data key/value observed in dataLayer contract", evidence={"push_index": idx, "key": str(key)}))
                return findings
    return findings


def build_publisher_surface_snapshot(payload: SnapshotInput) -> dict[str, Any]:
    parser = _parse_html(payload.html)
    text = _script_text(parser)
    canonical, host, path, findings = _canonical_parts(payload.canonical_url, parser.canonical_href)
    host = payload.host or host
    path = payload.path or path
    if canonical and host and urlparse(canonical).netloc.lower() != host.lower():
        findings.append(_finding("CANONICAL_HOST_PATH_CONTRADICTORY", "canonical URL host diverges from declared host", evidence={"canonical_url": canonical, "host": host}))

    define_slots = _parse_define_slots(text)
    manifest_by_key = _manifest_slots(payload.ad_manifest)
    div_counts: dict[str, int] = {}
    for div in parser.divs:
        if div.get("id"):
            div_counts[div["id"]] = div_counts.get(div["id"], 0) + 1
    for div_id, count in sorted(div_counts.items()):
        if count > 1:
            findings.append(_finding("DIV_ID_DUPLICATED", "same div_id appears more than once", evidence={"div_id": div_id, "count": count}))

    loader_count = _gpt_loader_count(parser)
    if loader_count > 1:
        findings.append(_finding("GPT_LOADER_DUPLICATED", "GPT loader observed more than once", evidence={"count": loader_count}))

    data_layer = _extract_data_layer(payload, parser)
    findings.extend(_data_layer_findings(data_layer))

    slots: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    div_by_id = {d.get("id"): d for d in parser.divs if d.get("id")}
    manifest_keys_by_div = {f"div-gpt-{k}": k for k in manifest_by_key}
    all_div_ids = sorted(str(x) for x in (set(define_slots) | set(div_by_id)) if x)
    for div_id in all_div_ids:
        attrs = div_by_id.get(div_id, {}).get("attrs", {})
        slot_key = attrs.get("data-ad-slot") or manifest_keys_by_div.get(div_id) or div_id
        manifest_slot = manifest_by_key.get(slot_key)
        defined = define_slots.get(div_id, {})
        seen_keys.add(slot_key)
        sizes = defined.get("accepted_sizes") or (manifest_slot or {}).get("sizes")
        min_height = _parse_style_min_height(attrs.get("style", ""))
        if min_height is None:
            mh = (manifest_slot or {}).get("min_height_px")
            min_height = mh if isinstance(mh, int) and mh > 0 else None
        pos = _position(attrs, manifest_slot)
        slot = {
            "slot_key": _field(slot_key, evidence="dom_or_manifest", observed_at=payload.observed_at),
            "div_id": _field(div_id, evidence="dom", observed_at=payload.observed_at),
            "ad_unit_path": _field(defined.get("ad_unit_path"), evidence="gpt_defineSlot", observed_at=payload.observed_at) if defined.get("ad_unit_path") else _field(None, evidence="gpt_defineSlot"),
            "accepted_sizes": _field(sizes, evidence="gpt_defineSlot_or_admanifest", observed_at=payload.observed_at) if sizes else _field(None, evidence="gpt_defineSlot_or_admanifest"),
            "breakpoints": _field(None, status="unavailable", evidence="no breakpoint contract observed"),
            "position": _field(pos, evidence="dom_or_manifest", observed_at=payload.observed_at) if pos else _field(None, status="unavailable", evidence="no fold evidence observed"),
            "reserved_dimensions": _field({"min_height_px": min_height}, evidence="dom_style_or_admanifest", observed_at=payload.observed_at) if min_height else _field(None, evidence="dom_style_or_admanifest"),
            "loader_observed": _field(defined.get("loader"), evidence="gpt_defineSlot", observed_at=payload.observed_at) if defined.get("loader") else _field(None, evidence="gpt_defineSlot"),
            "lazy_load_observed": _field("enableLazyLoad" in text or "IntersectionObserver" in text, evidence="script_scan", observed_at=payload.observed_at) if ("enableLazyLoad" in text or "IntersectionObserver" in text) else _field(None, status="absent_confirmed", evidence="script_scan"),
            "refresh_policy_observed": _field(None, status="absent_confirmed", evidence="refresh observed without interval/trigger policy") if "refresh(" in text else _field(None, status="not_applicable", evidence="no refresh call observed"),
        }
        slots.append(slot)
        if not slot_key:
            findings.append(_finding("SLOT_WITHOUT_IDENTITY", "slot has no stable identity", evidence={"div_id": div_id}))
        if not sizes:
            findings.append(_finding("SLOT_WITHOUT_SIZE_OR_BREAKPOINT", "slot has no observed size or breakpoint", evidence={"slot_key": slot_key}))
        if not min_height:
            findings.append(_finding("SLOT_WITHOUT_RESERVED_SPACE", "slot has no positive reserved min-height", evidence={"slot_key": slot_key, "div_id": div_id}))
        if sizes and "fluid" in sizes and pos == "ATF":
            findings.append(_finding("FLUID_ATF", "fluid slot observed above the fold", evidence={"slot_key": slot_key, "div_id": div_id}))
        if pos == "BTF" and not ("enableLazyLoad" in text or "IntersectionObserver" in text):
            findings.append(_finding("BTF_WITHOUT_LAZY_LOAD_EVIDENCE", "below-the-fold slot lacks lazy-load evidence", evidence={"slot_key": slot_key, "div_id": div_id}))

    for key, manifest_slot in sorted(manifest_by_key.items()):
        if key not in seen_keys:
            slots.append({
                "slot_key": _field(key, evidence="admanifest", observed_at=payload.observed_at),
                "div_id": _field(None, status="unavailable", evidence="not observed in DOM"),
                "ad_unit_path": _field(None, status="unavailable", evidence="AdManifest does not carry GAM path"),
                "accepted_sizes": _field(manifest_slot.get("sizes"), evidence="admanifest", observed_at=payload.observed_at) if manifest_slot.get("sizes") else _field(None, evidence="admanifest"),
                "breakpoints": _field(None, status="unavailable", evidence="no breakpoint contract observed"),
                "position": _field(manifest_slot.get("placement"), evidence="admanifest", observed_at=payload.observed_at) if manifest_slot.get("placement") else _field(None, status="unavailable", evidence="admanifest"),
                "reserved_dimensions": _field({"min_height_px": manifest_slot.get("min_height_px")}, evidence="admanifest", observed_at=payload.observed_at) if manifest_slot.get("min_height_px") else _field(None, evidence="admanifest"),
                "loader_observed": _field(None, status="unavailable", evidence="not observed in DOM"),
                "lazy_load_observed": _field(None, status="unavailable", evidence="not observed in DOM"),
                "refresh_policy_observed": _field(None, status="not_applicable", evidence="not observed in DOM"),
            })
            findings.append(_finding("ADMANIFEST_DOM_DIVERGENCE", "AdManifest slot not observed in DOM", evidence={"slot_key": key}))
    for div_id in define_slots:
        dom_key = div_by_id.get(div_id, {}).get("attrs", {}).get("data-ad-slot")
        if manifest_by_key and dom_key and dom_key not in manifest_by_key:
            findings.append(_finding("ADMANIFEST_DOM_DIVERGENCE", "DOM slot not declared by AdManifest", evidence={"slot_key": dom_key, "div_id": div_id}))

    if "refresh(" in text and not re.search(r"refresh_(seconds|interval)|setInterval\s*\(|refreshPolicy|data-ad-refresh-interval", text):
        findings.append(_finding("REFRESH_WITHOUT_OBSERVABLE_POLICY", "GPT refresh call observed without observable timing/trigger policy"))

    page = {
        "site_id": _field(payload.site_id, evidence="input", observed_at=payload.observed_at),
        "project_id": _field(payload.project_id, evidence="input", observed_at=payload.observed_at),
        "host": _field(host, evidence="canonical_or_input", observed_at=payload.observed_at) if host else _field(None, evidence="canonical_or_input"),
        "path": _field(path, evidence="canonical_or_input", observed_at=payload.observed_at) if path else _field(None, evidence="canonical_or_input"),
        "canonical_url": _field(canonical, evidence="dom_or_input", observed_at=payload.observed_at) if canonical else _field(None, evidence="dom_or_input"),
        "page_type": _field(payload.page_type, evidence="input", observed_at=payload.observed_at),
        "template_key": _field(payload.template_key, evidence="input_or_dataLayer", observed_at=payload.observed_at),
        "content_category": _field(payload.content_category, evidence="input_or_dataLayer", observed_at=payload.observed_at),
        "ad_layout_version": _field(payload.ad_layout_version, evidence="input_or_dataLayer", observed_at=payload.observed_at),
        "device_class": _field(payload.device_class, evidence="input", observed_at=payload.observed_at),
    }
    return {
        "schema": "PublisherSurfaceSnapshot",
        "schema_version": SCHEMA_VERSION,
        "source": payload.source,
        "page": page,
        "slots": sorted(slots, key=lambda s: s["slot_key"].get("value", "")),
        "dataLayer": {
            "status": "observed" if data_layer else "absent_confirmed",
            **({"value": data_layer, "observed_at": payload.observed_at} if data_layer else {}),
        },
        "findings": sorted(findings, key=lambda f: (f["code"], json.dumps(f.get("evidence", ""), sort_keys=True))),
    }


def deterministic_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
