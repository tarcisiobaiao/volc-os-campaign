"""Diagnostico SSH fechado: referencias locais e consultas WordPress read-only."""
from __future__ import annotations

import io
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from dotenv import dotenv_values

FIELDS = (
    "domain", "ssh_alias", "ssh_host", "ssh_user", "ssh_identity_file",
    "remote_root", "wp_config",
)
NAMES = tuple("CREDITOUP_" + field.upper() for field in FIELDS)


def load_settings(path: Path) -> Settings:
    # Seleciona somente as sete referencias, sem executar expansoes de shell
    # nem carregar os demais valores/segredos do arquivo de ambiente.
    selected = []
    seen = set()
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                match = re.match(r"\s*(?:export\s+)?(CREDITOUP_[A-Z_]+)\s*=", line)
                if match and match[1] in NAMES:
                    if match[1] in seen:
                        raise ValueError("Referencia CreditUp duplicada em .env.local.")
                    seen.add(match[1])
                    selected.append(line)
    values = dotenv_values(stream=io.StringIO("".join(selected)), interpolate=False)
    refs = {name.lower(): os.environ.get(name, values.get(name)) for name in NAMES}
    if any(not value for value in refs.values()):
        missing = [name.upper() for name, value in refs.items() if not value]
        raise ValueError("Referencia ausente: " + ", ".join(missing))
    try:
        return Settings(_env_file=None, **refs)
    except ValueError:
        raise ValueError("Configuracao tipada invalida; detalhes e valores ocultos.") from None


def validate(settings: Settings) -> Path:
    for field in ("domain", "ssh_alias", "ssh_host", "ssh_user"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", getattr(settings, "creditoup_" + field) or ""):
            raise ValueError("Referencia de host/alias/usuario invalida.")
    root = PurePosixPath(settings.creditoup_remote_root)
    config = PurePosixPath(settings.creditoup_wp_config)
    if not root.is_absolute() or root == PurePosixPath("/") or ".." in root.parts:
        raise ValueError("Raiz remota invalida.")
    if config != root / "wp-config.php":
        raise ValueError("wp-config.php deve pertencer a raiz remota configurada.")
    key = Path(settings.creditoup_ssh_identity_file).expanduser()
    if not key.is_absolute() or not key.is_file():
        raise ValueError("Chave SSH ausente ou caminho nao absoluto.")
    if key.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("A chave SSH deve permanecer fora do repositorio.")
    if stat.S_IMODE(key.stat().st_mode) not in (0o400, 0o600):
        raise ValueError("Chave SSH exige permissao 400 ou 600.")
    return key


def run(args: list[str], phase: str) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError(phase + ": comando indisponivel ou timeout.") from None
    if result.returncode:
        # stderr remoto pode conter configuracao sensivel; nunca o reproduzir.
        raise ValueError(phase + ": falhou; confira acesso, host conhecido e referencias locais.")
    return result.stdout


def remote_command(settings: Settings) -> str:
    root = shlex.quote(settings.creditoup_remote_root)
    config = shlex.quote(settings.creditoup_wp_config)
    wp = f"wp --allow-root --skip-plugins --skip-themes --path={root}"
    return (
        "set -eu; printf 'HOST='; hostname; printf 'USER='; whoami; "
        f"test -d {root}; test -f {config}; echo CREDITOUP_WORDPRESS_OK; "
        "if command -v wp >/dev/null 2>&1; then "
        f"printf 'WP_CLI='; {wp} cli version; "
        f"printf 'WP_HOME='; {wp} option get home; "
        f"printf 'WP_SITEURL='; {wp} option get siteurl; "
        f"printf 'WP_VERSION='; {wp} core version; "
        "else echo WP_CLI_ABSENT; fi"
    )


def check(settings: Settings) -> list[str]:
    key = validate(settings)
    alias = settings.creditoup_ssh_alias
    resolved = run(["ssh", "-G", alias], "Resolucao do alias")
    entries: dict[str, list[str]] = {}
    for line in resolved.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            entries.setdefault(parts[0], []).append(parts[1])
    if entries.get("hostname") != [settings.creditoup_ssh_host] or entries.get("user") != [settings.creditoup_ssh_user]:
        raise ValueError("Alias SSH diverge de CREDITOUP_SSH_HOST/USER; nenhuma conexao realizada.")
    if str(key.resolve()) not in [str(Path(p).expanduser().resolve()) for p in entries.get("identityfile", [])]:
        raise ValueError("Chave configurada diverge da identidade do alias SSH.")
    options = [
        "BatchMode=yes", "ConnectTimeout=10", "StrictHostKeyChecking=yes",
        "UpdateHostKeys=no", "IdentitiesOnly=yes", "ForwardAgent=no",
        "ClearAllForwardings=yes", "PermitLocalCommand=no", "RemoteCommand=none",
        "ControlMaster=no", "ControlPath=none", "RequestTTY=no",
    ]
    args = ["ssh", "-T", "-i", str(key)]
    for option in options:
        args.extend(["-o", option])
    output = run([*args, alias, remote_command(settings)], "Consulta remota read-only")
    lines = output.splitlines()
    required = ["HOST=wp-arbitragem-volc-01", "USER=" + settings.creditoup_ssh_user, "CREDITOUP_WORDPRESS_OK"]
    if any(line not in lines for line in required):
        raise ValueError("Identidade remota ou raiz WordPress nao confirmada.")
    safe = ["SSH_ALIAS_OK", *required]
    if "WP_CLI_ABSENT" in lines:
        return [*safe, "WP_CLI_ABSENT"]
    for label, pattern in (
        ("WP_CLI", r"WP-CLI [0-9][A-Za-z0-9.\-]*"),
        ("WP_HOME", r"https?://" + re.escape(settings.creditoup_domain) + r"/?"),
        ("WP_SITEURL", r"https?://" + re.escape(settings.creditoup_domain) + r"/?"),
        ("WP_VERSION", r"[0-9][A-Za-z0-9.\-]*"),
    ):
        matches = [line for line in lines if re.fullmatch(label + "=" + pattern, line)]
        if len(matches) != 1:
            raise ValueError(label + ": resposta ausente, divergente ou inesperada (oculta).")
        safe.extend(matches)
    return safe


def main() -> int:
    if len(sys.argv) != 1:
        print("ERRO: este helper nao aceita argumentos nem comandos remotos.", file=sys.stderr)
        return 2
    try:
        for line in check(load_settings(ROOT / ".env.local")):
            print(line)
    except ValueError as exc:
        print("ERRO: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
