#!/usr/bin/env python3
"""Inventaria o parque externo motor-imagem sem modificá-lo.

O snapshot é evidência, não cópia de autoridade. Ele registra código, contratos,
skins, fontes e artefatos finais da PRENSA com hashes e gates disponíveis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_ROOT = Path("/Users/mac/Desktop/Volc Mídia Global/motor-imagem")
EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".toml", ".yaml", ".yml"}
GRAPHIC_TYPES = {"grafico", "colunas", "medidor", "tabela"}
ATMOSPHERE_TYPES = {"texture", "vinheta", "vazamento", "scrim", "veu"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def image_dimensions(path: Path) -> list[int] | None:
    try:
        with path.open("rb") as stream:
            header = stream.read(24)
            if header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR":
                return list(struct.unpack(">II", header[16:24]))
            if header[:2] != b"\xff\xd8":
                return None
            stream.seek(2)
            while True:
                marker_start = stream.read(1)
                if not marker_start:
                    return None
                if marker_start != b"\xff":
                    continue
                marker = stream.read(1)
                while marker == b"\xff":
                    marker = stream.read(1)
                if marker in {b"\xd8", b"\xd9"}:
                    continue
                length_raw = stream.read(2)
                if len(length_raw) != 2:
                    return None
                length = struct.unpack(">H", length_raw)[0]
                if marker and marker[0] in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                    payload = stream.read(5)
                    if len(payload) != 5:
                        return None
                    height, width = struct.unpack(">HH", payload[1:5])
                    return [width, height]
                stream.seek(length - 2, 1)
    except OSError:
        return None


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def all_layers(spec: dict) -> list[dict]:
    layers = list(spec.get("layers") or [])
    for slide in spec.get("slides") or []:
        layers.extend(slide.get("layers") or [])
    return [item for item in layers if isinstance(item, dict)]


def classify_spec(spec: dict) -> tuple[str, list[str], list[str]]:
    assets = [item for item in spec.get("assets") or [] if isinstance(item, dict)]
    layers = all_layers(spec)
    asset_kinds = sorted({str(item.get("kind")) for item in assets if item.get("kind")})
    layer_types = sorted({str(item.get("type")) for item in layers if item.get("type")})
    if any(item.get("ia_gerada") is True or item.get("kind") == "photo_ia" for item in assets):
        mode = "prensa_hybrid_llm_asset"
    elif assets:
        mode = "existing_asset_plus_prensa"
    elif set(layer_types) & GRAPHIC_TYPES:
        mode = "deterministic_graphics_and_typography"
    else:
        mode = "typography_only"
    return mode, asset_kinds, layer_types


def artifact_kind(stem: str) -> str:
    if stem.startswith("bg_"):
        return "source_asset"
    if stem.startswith(("cmp_", "web_")):
        return "comparison_evidence"
    if stem in {"falso_traco", "post_monstro_poc"}:
        return "adversarial_fixture"
    return "rendered_output"


def family_for(stem: str, spec_ids: list[str]) -> str:
    normalized = re.sub(r"(?:\.dossier|\.titanium|\.fxd|\.fx)?_s\d+$", "", stem)
    normalized = re.sub(r"_run[a-z]$", "", normalized)
    for spec_id in sorted(spec_ids, key=len, reverse=True):
        if normalized == spec_id or normalized.startswith(spec_id + "__"):
            return spec_id
    return normalized


def sidecar_summary(path: Path) -> dict | None:
    data = read_json(path)
    if not isinstance(data, dict):
        return None
    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    return {
        "path": path.name,
        "ok": data.get("ok"),
        "passed": data.get("passed"),
        "status": data.get("status"),
        "checks_total": len(checks),
        "checks_failed": sum(1 for check in checks if isinstance(check, dict) and check.get("passed") is False),
        "sha256": sha256(path),
    }


def build_snapshot(root: Path) -> dict:
    if not root.is_dir():
        raise SystemExit(f"motor-imagem não encontrado: {root}")

    files = list(iter_files(root))
    component_stats: dict[str, dict] = defaultdict(lambda: {"files": 0, "bytes": 0})
    extension_counts = Counter()
    source_files = []
    for path in files:
        rel = path.relative_to(root)
        component = rel.parts[0]
        size = path.stat().st_size
        component_stats[component]["files"] += 1
        component_stats[component]["bytes"] += size
        extension_counts[path.suffix.lower() or "[no_extension]"] += 1
        if path.suffix.lower() in SOURCE_SUFFIXES and "out" not in rel.parts and "out_antes_costura" not in rel.parts:
            source_files.append(path)

    poc = root / "compartilhado" / "prensa-poc"
    specs = []
    for path in sorted(poc.glob("spec_*.json")):
        data = read_json(path)
        if not isinstance(data, dict) or not data.get("spec_id"):
            continue
        mode, asset_kinds, layer_types = classify_spec(data)
        specs.append({
            "spec_id": data["spec_id"],
            "source": path.name,
            "schema_version": data.get("schema_version"),
            "skin": (data.get("skin") or {}).get("id"),
            "skin_version": (data.get("skin") or {}).get("versao"),
            "production_mode": mode,
            "asset_kinds": asset_kinds,
            "layer_types": layer_types,
            "slides": len(data.get("slides") or []) or 1,
            "sha256": sha256(path),
        })
    spec_ids = [item["spec_id"] for item in specs]
    spec_mode = {item["spec_id"]: item["production_mode"] for item in specs}

    out = poc / "out"
    artifacts = []
    output_images = (
        sorted(p for p in out.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"})
        if out.is_dir() else []
    )
    for path in output_images:
        stem = path.stem
        family = family_for(stem, spec_ids)
        sidecars = {}
        for label, suffix in (("verdict", ".veredito.json"), ("pixel_gate", ".pixelgate.json")):
            candidate = path.with_name(path.stem + suffix)
            if candidate.exists():
                sidecars[label] = sidecar_summary(candidate)
        artifacts.append({
            "file": path.name,
            "family": family,
            "kind": artifact_kind(stem),
            "production_mode": spec_mode.get(family, "support_or_unmapped"),
            "dimensions": image_dimensions(path),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "sidecars": sidecars,
        })

    skins = []
    for path in sorted(poc.glob("tokens_*.json")):
        data = read_json(path)
        if not isinstance(data, dict):
            continue
        fonts = data.get("fonts") if isinstance(data.get("fonts"), list) else []
        effects = data.get("efeitos") if isinstance(data.get("efeitos"), dict) else {}
        skins.append({
            "file": path.name,
            "id": data.get("id") or data.get("skin_id") or path.stem.removeprefix("tokens_"),
            "version": data.get("versao") or data.get("version"),
            "font_files": sorted({str(font.get("file")) for font in fonts if isinstance(font, dict) and font.get("file")}),
            "effects": sorted(effects),
            "sha256": sha256(path),
        })

    historical = poc / "out_antes_costura"
    historical_images = sorted(
        p for p in historical.glob("*") if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ) if historical.is_dir() else []
    historical_identical = 0
    for path in historical_images:
        current = out / path.name
        if current.exists() and sha256(current) == sha256(path):
            historical_identical += 1

    family_counts = Counter(a["family"] for a in artifacts if a["kind"] == "rendered_output")
    mode_counts = Counter(a["production_mode"] for a in artifacts if a["kind"] == "rendered_output")
    pixel_ready = sum(
        1 for a in artifacts
        if (a["sidecars"].get("pixel_gate") or {}).get("passed") is True
    )
    verdict_ok = sum(
        1 for a in artifacts
        if (a["sidecars"].get("verdict") or {}).get("ok") is True
    )
    source_fingerprint = hashlib.sha256(
        "\n".join(f"{p.relative_to(root)}:{sha256(p)}" for p in sorted(source_files)).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": 1,
        "snapshot_date": "2026-08-26",
        "source_root": str(root),
        "read_only": True,
        "source_fingerprint_sha256": source_fingerprint,
        "summary": {
            "files_scanned": len(files),
            "source_files_hashed": len(source_files),
            "specs": len(specs),
            "skins": len(skins),
            "images_in_prensa_out": len(artifacts),
            "rendered_outputs": sum(a["kind"] == "rendered_output" for a in artifacts),
            "source_assets": sum(a["kind"] == "source_asset" for a in artifacts),
            "comparison_evidence": sum(a["kind"] == "comparison_evidence" for a in artifacts),
            "adversarial_fixtures": sum(a["kind"] == "adversarial_fixture" for a in artifacts),
            "outputs_with_pixel_gate_passed": pixel_ready,
            "outputs_with_verdict_ok": verdict_ok,
        },
        "components": dict(sorted(component_stats.items())),
        "extensions": dict(sorted(extension_counts.items())),
        "production_modes": dict(sorted(mode_counts.items())),
        "rendered_families": dict(sorted(family_counts.items())),
        "historical_output": {
            "path": str(historical),
            "images": len(historical_images),
            "byte_identical_to_current_same_name": historical_identical,
            "purpose": "before_after_evidence_not_current_authority",
        },
        "specs": specs,
        "skins": skins,
        "artifacts": artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(build_snapshot(args.root), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
