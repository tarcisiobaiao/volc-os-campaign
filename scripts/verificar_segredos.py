#!/usr/bin/env python3
"""Falha quando padrões fortes de segredo aparecem no working tree, sem imprimi-los."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {
    ".git", ".venv", ".venv-graphify", "node_modules", "dist",
    "graphify-out", "entregaveis",
}
PATTERNS = {
    "private-key": re.compile(rb"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "jwt": re.compile(rb"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
    "google-api-key": re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    "openai-key": re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}"),
    "hardcoded-service-role": re.compile(
        rb"(?:SUPABASE_SERVICE_ROLE_KEY|supabaseKey)\s*=\s*['\"][^'\"\n]{32,}['\"]",
        re.I,
    ),
}
REPLACEMENTS = {
    "jwt": b"[REDACTED_JWT]",
    "google-api-key": b"[REDACTED_GOOGLE_API_KEY]",
    "openai-key": b"[REDACTED_OPENAI_KEY]",
    "hardcoded-service-role": b"SUPABASE_SERVICE_ROLE_KEY=[REDACTED_SERVICE_ROLE]",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--redact", action="store_true",
        help="substitui tokens textuais reconhecidos; chaves privadas exigem intervenção manual",
    )
    return parser.parse_args()


def files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    found = []
    for raw in result.stdout.splitlines():
        path = ROOT / raw
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.stat().st_size > 5_000_000:
            continue
        found.append(path)
    return found


def main() -> None:
    options = parse_args()
    findings: list[tuple[str, str]] = []
    for path in files():
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        updated = raw
        for rule, pattern in PATTERNS.items():
            if pattern.search(raw):
                findings.append((str(path.relative_to(ROOT)), rule))
                if options.redact and rule in REPLACEMENTS:
                    updated = pattern.sub(REPLACEMENTS[rule], updated)
        if options.redact and updated != raw:
            path.write_bytes(updated)
    if findings:
        label = "Segredos textuais redigidos" if options.redact else "Possíveis segredos encontrados"
        print(f"{label} (valores ocultos):")
        for path, rule in findings:
            print(f"- {path}: {rule}")
        if not options.redact or any(rule == "private-key" for _path, rule in findings):
            raise SystemExit(1)
        return
    print("Secret scan: nenhum padrão forte encontrado no working tree.")


if __name__ == "__main__":
    main()
