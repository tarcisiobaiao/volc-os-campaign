"""Configura o profile `volcweb` do Hermes v0.18.0 para a Bia. Rodar NA VPS, à mão.

⚠️ CHECKPOINT EXTERNO. Só com autorização explícita do Tarcisio, e DEPOIS de:

    hermes profile create volcweb --no-skills --no-alias \
        --description "Bia VOLC — consulta, sem ferramentas"
    hermes -p volcweb setup model        # provedor/modelo do profile, interativo

O que faz (em /root/.hermes/profiles/volcweb, nunca no default):
  .env         API_SERVER_ENABLED=true, API_SERVER_HOST=127.0.0.1,
               API_SERVER_PORT=8643, API_SERVER_KEY gerada se ausente (NÃO imprime)
  config.yaml  platform_toolsets.api_server = []   (ver nota)
               mcp_servers = {}
               gateway.api_server.max_concurrent_runs = 1

O que RECUSA (sai sem alterar nada):
  - profile inexistente ou sem config.yaml;
  - qualquer credencial de plataforma de mensagem no .env do volcweb
    (TELEGRAM_*, DISCORD_*, SLACK_*, WHATSAPP_*): o profile não pode competir
    com o Telegram do default;
  - rodar apontando para o profile default.

Backup: cada arquivo tocado ganha `<arquivo>.bak-bia-<timestamp>` antes da
escrita. Rollback: copiar o .bak de volta (ver RUNBOOK-ROLLBACK-ROTACAO.md).

⚠️ Nota sobre toolsets (medida em 15/10/2026 na v0.18.0 instalada, com
HERMES_HOME temporário e sem tocar em profile nenhum):
`_get_platform_tools({"platform_toolsets": {"api_server": []}}, "api_server")`
devolve conjunto VAZIO. Um nome inexistente (ex.: ["nenhum"]) volta como
toolset "habilitado" fantasma — por isso a lista é vazia, não um marcador.
Ainda assim, configuração é intenção: a PROVA é `smoke_hermes.py`, que exige
`GET /v1/toolsets` sem nenhum toolset habilitado antes de qualquer uso, e o
read-back da sessão sem `tool_calls` depois da primeira inferência.
"""
from __future__ import annotations

import os
import secrets
import shutil
import sys
import time
from pathlib import Path

import yaml  # o venv do Hermes tem PyYAML: /usr/local/lib/hermes-agent/venv/bin/python

PERFIL = "volcweb"
CASA = Path("/root/.hermes/profiles") / PERFIL
PROIBIDAS = ("TELEGRAM_", "DISCORD_", "SLACK_", "WHATSAPP_", "SIGNAL_", "MATRIX_")


def _falhar(msg: str) -> None:
    print(f"RECUSADO: {msg} — nada foi alterado.")
    sys.exit(2)


def _backup(p: Path, carimbo: str) -> None:
    if p.exists():
        shutil.copy2(p, p.with_name(p.name + f".bak-bia-{carimbo}"))


def main() -> None:
    if os.environ.get("HERMES_HOME", "").rstrip("/") in ("", "/root/.hermes") and not CASA.is_dir():
        _falhar(f"profile {PERFIL} não existe em {CASA}")
    config = CASA / "config.yaml"
    env = CASA / ".env"
    if not config.exists():
        _falhar("config.yaml do volcweb ausente (rode o setup do profile antes)")

    linhas = env.read_text().splitlines() if env.exists() else []
    chaves = {l.split("=", 1)[0].strip() for l in linhas if "=" in l and not l.lstrip().startswith("#")}
    plataformas = sorted(k for k in chaves if k.startswith(PROIBIDAS))
    if plataformas:
        _falhar(f"o volcweb tem credencial de plataforma de mensagem: {plataformas}")

    carimbo = time.strftime("%Y%m%d-%H%M%S")
    _backup(env, carimbo)
    _backup(config, carimbo)

    novas = {"API_SERVER_ENABLED": "true", "API_SERVER_HOST": "127.0.0.1", "API_SERVER_PORT": "8643"}
    if "API_SERVER_KEY" not in chaves:
        novas["API_SERVER_KEY"] = secrets.token_urlsafe(48)
    mantidas = [l for l in linhas if l.split("=", 1)[0].strip() not in novas]
    env.write_text("\n".join(mantidas + [f"{k}={v}" for k, v in novas.items()]) + "\n")
    os.chmod(env, 0o600)

    dados = yaml.safe_load(config.read_text()) or {}
    dados.setdefault("platform_toolsets", {})["api_server"] = []
    dados["mcp_servers"] = {}
    dados.setdefault("gateway", {}).setdefault("api_server", {})["max_concurrent_runs"] = 1
    config.write_text(yaml.safe_dump(dados, allow_unicode=True, sort_keys=False))
    os.chmod(config, 0o600)

    print("OK: volcweb configurado (chave NÃO impressa; backups .bak-bia-%s)." % carimbo)
    print("Próximo passo: hermes -p volcweb gateway run (foreground) e smoke_hermes.py.")


if __name__ == "__main__":
    main()
