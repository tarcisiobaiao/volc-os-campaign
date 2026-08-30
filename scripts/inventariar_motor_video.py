#!/usr/bin/env python3
"""Fotografa o Motor de Vídeo VOLC e sua fábrica de execução sem modificá-los.

O snapshot separa três verdades: código/contrato organizado, renders observados
na fábrica e integração (ainda inexistente) com o VOLC O.S. Segredos nunca são
lidos: o arquivo `.env` é excluído por construção.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_ROOT = Path("/Users/mac/Desktop/Volc Mídia Global/motor-video")
DEFAULT_FACTORY = Path("/Users/mac/volc-factory")
EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".toml", ".yaml", ".yml"}


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


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if path.name == ".env":
            continue
        yield path


def env_names_from_example(root: Path) -> list[str]:
    example = root / ".env.exemplo"
    if not example.exists():
        return []
    names = []
    for raw in example.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name = line.split("=", 1)[0].strip()
        if name and name.replace("_", "").isalnum():
            names.append(name)
    return sorted(set(names))


def probe_video(path: Path, ffprobe_bin: str | None) -> dict:
    base = {"file": path.name, "bytes": path.stat().st_size}
    if not ffprobe_bin:
        return {**base, "probe": "unavailable"}
    try:
        result = subprocess.run(
            [
                ffprobe_bin, "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate",
                "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {**base, "probe": "failed"}
    streams = payload.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    duration = (payload.get("format") or {}).get("duration")
    return {
        **base,
        "probe": "ok",
        "duration_s": round(float(duration), 3) if duration is not None else None,
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": video.get("r_frame_rate"),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
    }


def report_summary(path: Path) -> dict | None:
    data = read_json(path)
    if not isinstance(data, dict):
        return None
    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    return {
        "path": str(path),
        "verdict": data.get("verdict"),
        "checks": len(checks),
        "fails": (data.get("summary") or {}).get("fails") if isinstance(data.get("summary"), dict) else None,
        "warns": (data.get("summary") or {}).get("warns") if isinstance(data.get("summary"), dict) else None,
        "mp4_sha256": data.get("mp4_sha256"),
        "sha256": sha256(path),
    }


def formats_inventory(root: Path, skins: dict) -> list[dict]:
    formats_root = root / "formatos"
    skin_by_format: dict[str, list[str]] = defaultdict(list)
    for skin_id, skin in skins.items():
        runner = str((skin or {}).get("runner") or "")
        for format_dir in sorted(p.name for p in formats_root.iterdir() if p.is_dir()):
            if f"formatos/{format_dir}/" in runner:
                skin_by_format[format_dir].append(skin_id)

    result = []
    for directory in sorted(path for path in formats_root.iterdir() if path.is_dir()):
        makers = sorted(path.name for path in directory.glob("make*.py"))
        design = (directory / "design.md").exists()
        compositor = (directory / "compositor.tsx").exists()
        sound = (directory / "som.py").exists()
        shared = sorted(path.name for path in directory.glob("*COMPARTILHADO*.md"))
        gaps = []
        if not design:
            gaps.append("design_ausente")
        if not makers:
            gaps.append("runner_ausente")
        if not compositor:
            gaps.append("compositor_proprio_ausente")
        if not sound:
            gaps.append("som_proprio_ausente")
        result.append({
            "id": directory.name,
            "design": design,
            "makers": makers,
            "compositor": compositor,
            "sound": sound,
            "shared_notes": shared,
            "contract_skins": sorted(skin_by_format[directory.name]),
            "gaps": gaps,
            "filesystem_complete": not gaps,
        })
    return result


def build_snapshot(root: Path, factory_root: Path | None = None, ffprobe_bin: str | None = None) -> dict:
    if not root.is_dir():
        raise SystemExit(f"motor-video não encontrado: {root}")
    factory_root = factory_root or DEFAULT_FACTORY
    ffprobe_bin = ffprobe_bin if ffprobe_bin is not None else shutil.which("ffprobe")

    files = list(iter_files(root))
    component_stats: dict[str, dict] = defaultdict(lambda: {"files": 0, "bytes": 0})
    extension_counts = Counter()
    source_files = []
    for path in files:
        rel = path.relative_to(root)
        component = rel.parts[0]
        component_stats[component]["files"] += 1
        component_stats[component]["bytes"] += path.stat().st_size
        extension_counts[path.suffix.lower() or "[no_extension]"] += 1
        if path.suffix.lower() in SOURCE_SUFFIXES:
            source_files.append(path)

    map_path = root / "contrato" / "motor" / "mapa.json"
    schema_path = root / "contrato" / "schema" / "contrato.schema.json"
    contract = read_json(map_path)
    schema = read_json(schema_path)
    if not isinstance(contract, dict) or not isinstance(schema, dict):
        raise SystemExit("contrato/motor/mapa.json ou schema do contrato inválido")
    skins = contract.get("skins") if isinstance(contract.get("skins"), dict) else {}
    formats = formats_inventory(root, skins)

    skin_rows = []
    for skin_id, value in sorted(skins.items()):
        value = value if isinstance(value, dict) else {}
        qa = value.get("qa") if isinstance(value.get("qa"), dict) else {}
        skin_rows.append({
            "id": skin_id,
            "composition": value.get("comp"),
            "runner": value.get("runner"),
            "sound": value.get("snd"),
            "voice": value.get("voz_default"),
            "hook_mode": value.get("hook_default"),
            "qa_profile": qa.get("perfil"),
            "qa_retrofit": bool(qa.get("retrofit") or qa.get("verificar")),
            "required_roles": value.get("papeis_obrigatorios") or [],
            "asset_sources": value.get("fontes_assets") or [],
        })

    output_root = factory_root / "out"
    renders = []
    if output_root.is_dir():
        for video_path in sorted(output_root.glob("*.mp4")):
            stem = video_path.stem
            technical = output_root / f"qa_{stem}.json"
            visual = output_root / f"{stem}.qa_visual.json"
            meta = output_root / "meta" / stem
            row = probe_video(video_path, ffprobe_bin)
            row.update({
                "technical_qa": report_summary(technical) if technical.exists() else None,
                "visual_qa": report_summary(visual) if visual.exists() else None,
                "publication_snapshot": meta.is_dir(),
                "publication_files": sorted(path.name for path in meta.glob("*.json")) if meta.is_dir() else [],
            })
            renders.append(row)

    technical_qa = sum(row["technical_qa"] is not None for row in renders)
    visual_qa = sum(row["visual_qa"] is not None for row in renders)
    frozen = sum(row["publication_snapshot"] for row in renders)
    dimensions = Counter(
        f"{row['width']}x{row['height']}" for row in renders if row.get("width") and row.get("height")
    )
    hook_modes = Counter(row["hook_mode"] or "unspecified" for row in skin_rows)
    source_fingerprint = hashlib.sha256(
        "\n".join(f"{p.relative_to(root)}:{sha256(p)}" for p in sorted(source_files)).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": 1,
        "snapshot_date": "2026-08-26",
        "source_root": str(root),
        "factory_root": str(factory_root),
        "read_only": True,
        "secrets_policy": "arquivo .env excluido; somente nomes de variaveis do .env.exemplo",
        "source_fingerprint_sha256": source_fingerprint,
        "summary": {
            "files_scanned": len(files),
            "source_files_hashed": len(source_files),
            "formats": len(formats),
            "filesystem_complete_formats": sum(row["filesystem_complete"] for row in formats),
            "contract_skins": len(skin_rows),
            "contract_niches": len(contract.get("nichos") or {}),
            "contract_voices": len(contract.get("vozes") or {}),
            "contract_global_rules": len(contract.get("regras_globais") or []),
            "observed_final_renders": len(renders),
            "renders_with_technical_qa": technical_qa,
            "renders_with_visual_qa": visual_qa,
            "renders_with_publication_snapshot": frozen,
        },
        "components": dict(sorted(component_stats.items())),
        "extensions": dict(sorted(extension_counts.items())),
        "contract": {
            "version": contract.get("versao"),
            "map_sha256": sha256(map_path),
            "schema_sha256": sha256(schema_path),
            "required_fields": schema.get("required") or [],
            "global_rules": contract.get("regras_globais") or [],
            "reference_costs": contract.get("custos_referencia") or {},
            "publication": contract.get("publicacao") or {},
            "visual_qa": contract.get("qa_visual") or {},
            "locales": contract.get("locales") or {},
        },
        "providers": {
            "configured_variable_names": env_names_from_example(root),
            "secret_values_captured": False,
        },
        "hook_modes": dict(sorted(hook_modes.items())),
        "formats": formats,
        "skins": skin_rows,
        "execution_evidence": {
            "root": str(output_root),
            "dimensions": dict(sorted(dimensions.items())),
            "organized_root_full_render_proven": False,
            "note": "renders observados na fábrica externa; não provam execução integral a partir de motor-video",
            "renders": renders,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--factory-root", type=Path, default=DEFAULT_FACTORY)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(
        build_snapshot(args.root, args.factory_root), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
