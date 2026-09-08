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
    # ── a classe de segredo que o trilho Meta introduz ──────────────────────
    #
    # ⚠️ Estes padroes entraram em 08/09/2026 porque a varredura anterior saia
    # LIMPA num repositorio que estava prestes a receber token de sistema da
    # Meta. Um gate que so conhece as chaves de ontem da uma resposta verde
    # sobre um risco que ele nao olhou — e verde sem cobertura e pior do que
    # vermelho, porque ninguem procura depois.
    #
    # Token de usuario de sistema / acesso da Graph API. O prefixo `EAA` e
    # estavel; o comprimento minimo evita casar palavra comum em base64.
    "meta-graph-token": re.compile(rb"\bEAA[A-Za-z0-9]{60,}"),
    # App secret da Meta declarado inline (32 hex). So dispara com o NOME ao
    # lado, senao qualquer md5 do repositorio viraria falso positivo.
    "meta-app-secret": re.compile(
        rb"(?:app_secret|APP_SECRET|meta_app_secret)\s*[:=]\s*['\"]?[0-9a-f]{32}\b", re.I),
    # Chave de API do n8n (JWT proprio da instancia) declarada inline.
    "n8n-api-key": re.compile(
        rb"(?:N8N_API_KEY|n8n_api_key)\s*[:=]\s*['\"][^'\"\n]{20,}['\"]", re.I),
    # Access token de plataforma Supabase (`sbp_`), que NAO e a service role e
    # por isso escapava do padrao acima.
    "supabase-access-token": re.compile(rb"\bsbp_[0-9a-f]{40,}"),
}
REPLACEMENTS = {
    "jwt": b"[REDACTED_JWT]",
    "google-api-key": b"[REDACTED_GOOGLE_API_KEY]",
    "openai-key": b"[REDACTED_OPENAI_KEY]",
    "hardcoded-service-role": b"SUPABASE_SERVICE_ROLE_KEY=[REDACTED_SERVICE_ROLE]",
    "meta-graph-token": b"[REDACTED_META_GRAPH_TOKEN]",
    "meta-app-secret": b"app_secret=[REDACTED_META_APP_SECRET]",
    "n8n-api-key": b"N8N_API_KEY=[REDACTED_N8N_API_KEY]",
    "supabase-access-token": b"[REDACTED_SUPABASE_ACCESS_TOKEN]",
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
