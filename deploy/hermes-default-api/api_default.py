"""Superfície API do profile `default` do Hermes para a Bia do VOLC. Rodar NA VPS.

Decisão de 15/10/2026 (Tarcisio): a Bia do VOLC é a MESMA Bia do Telegram
(profile `default`: mesma identidade, memória e modelo), com sessão web
separada. Este script liga SÓ a superfície `api_server` desse profile, sem
ferramentas, e não toca no resto.

Interpretador: /usr/local/lib/hermes-agent/venv/bin/python (PyYAML + código do Hermes).

    preflight   só leitura: serviço, PID, Telegram, hashes, toolsets, sessões, portas
    ensaio      edita CÓPIAS e restaura; prova que a edição e o rollback são exatos
    aplicar     backup → edição mínima → restart só do hermes-gateway → gates;
                qualquer gate falho → rollback automático (restaura e reinicia)
    verificar   só leitura: os gates de depois
    reverter <dir-de-backup>   restaura os dois arquivos e reinicia

O que muda (e nada mais):
  /root/.hermes/.env         + API_SERVER_ENABLED=true, API_SERVER_HOST=127.0.0.1,
                               API_SERVER_PORT=8642, API_SERVER_KEY=<gerada, nunca impressa>
  /root/.hermes/config.yaml  + platform_toolsets.api_server: []   (inserção textual de UMA
                               linha; comentários e formato preservados; conferido por
                               igualdade do YAML inteiro, salvo a chave nova)

O que NÃO muda: Telegram (token, toolsets, sessões), memória, skills, SOUL,
modelo, MCPs, outros platform_toolsets, unit do systemd. NUNCA usa
`hermes gateway restart --system` (reescreve a unit); usa `systemctl restart
hermes-gateway`, a unit existente do profile default.

Nunca imprime segredo: a chave é gerada e lida em memória; o recibo leva só
sha256 de arquivos e presença de chaves.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, "/usr/local/lib/hermes-agent")

import yaml  # noqa: E402

CASA = Path("/root/.hermes")
ENV = CASA / ".env"
CONFIG = CASA / "config.yaml"
ESTADO = CASA / "gateway_state.json"
BACKUPS = CASA / "backups-bia"
UNIT = "hermes-gateway"
PORTA = 8642
NOVAS_ENV = {"API_SERVER_ENABLED": "true", "API_SERVER_HOST": "127.0.0.1", "API_SERVER_PORT": str(PORTA)}


# ── leitura ────────────────────────────────────────────────────────────────

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def env_dict(texto: str) -> dict:
    out = {}
    for l in texto.splitlines():
        if "=" in l and not l.lstrip().startswith("#"):
            k, v = l.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def sh(*args: str) -> str:
    return subprocess.run(list(args), capture_output=True, text=True).stdout.strip()


def main_pid() -> str:
    return sh("systemctl", "show", "-p", "MainPID", "--value", UNIT)


def gateway_state() -> dict:
    try:
        return json.loads(ESTADO.read_text())
    except Exception:  # noqa: BLE001
        return {}


def toolsets(cfg: dict, plataforma: str) -> list:
    from hermes_cli.tools_config import _get_platform_tools
    return sorted(_get_platform_tools(cfg, plataforma))


def processos_gateway() -> int:
    linhas = sh("ps", "-eo", "args").splitlines()
    return sum(1 for l in linhas if "hermes_cli.main gateway run" in l and "grep" not in l)


def ouvintes(porta: int) -> list:
    return sorted({l.split()[3] for l in sh("ss", "-ltnH").splitlines()
                   if len(l.split()) > 3 and l.split()[3].endswith(f":{porta}")})


def sessoes() -> dict:
    import sqlite3
    c = sqlite3.connect(f"file:{CASA / 'state.db'}?mode=ro", uri=True)
    por_source = dict(c.execute("select source, count(*) from sessions group by source").fetchall())
    ativas_tg = c.execute("select id, message_count from sessions where source='telegram' "
                          "and ended_at is null order by started_at").fetchall()
    return {"por_source": por_source,
            "telegram_ativas": [{"id_sha": hashlib.sha256(i.encode()).hexdigest()[:12],
                                 "mensagens": n} for i, n in ativas_tg]}


def foto() -> dict:
    cfg = yaml.safe_load(CONFIG.read_text()) or {}
    env = env_dict(ENV.read_text())
    g = gateway_state()
    return {
        "unit_ativa": sh("systemctl", "is-active", UNIT),
        "main_pid": main_pid(),
        "gateway_state": g.get("gateway_state"),
        "gateway_state_pid": g.get("pid"),
        "telegram": (g.get("platforms") or {}).get("telegram", {}).get("state"),
        "active_agents": g.get("active_agents"),
        "processos_gateway_run": processos_gateway(),
        "sha_config": sha(CONFIG),
        "sha_env": sha(ENV),
        "env_api_server": sorted(k for k in env if k.startswith("API_SERVER_")),
        "env_telegram_presente": bool(env.get("TELEGRAM_BOT_TOKEN")),
        "toolsets_telegram": toolsets(cfg, "telegram"),
        "toolsets_api_server": toolsets(cfg, "api_server"),
        "mcp_servers": len(cfg.get("mcp_servers") or {}),
        "platform_toolsets_api_server": (cfg.get("platform_toolsets") or {}).get("api_server", "AUSENTE"),
        "ouvintes_8642": ouvintes(PORTA),
        "profiles": sh("bash", "-lc", "ls /root/.hermes/profiles 2>/dev/null || true").split(),
        "sessoes": sessoes(),
    }


# ── edição ─────────────────────────────────────────────────────────────────

def editar_config(texto: str) -> str:
    """Insere `  api_server: []` como 1º filho de `platform_toolsets:`. Uma linha."""
    linhas = texto.splitlines(keepends=True)
    idx = next((i for i, l in enumerate(linhas) if l.rstrip() == "platform_toolsets:"), None)
    if idx is None:
        raise SystemExit("RECUSADO: config.yaml sem bloco platform_toolsets: no topo")
    filho = next((l for l in linhas[idx + 1:] if l.strip()), "")
    recuo = filho[: len(filho) - len(filho.lstrip())] or "  "
    linhas.insert(idx + 1, f"{recuo}api_server: []\n")
    return "".join(linhas)


def conferir_config(antes: str, depois: str) -> None:
    a, d = yaml.safe_load(antes) or {}, yaml.safe_load(depois) or {}
    esperado = copy.deepcopy(a)
    esperado.setdefault("platform_toolsets", {})["api_server"] = []
    if d != esperado:
        raise SystemExit("RECUSADO: a edição do config.yaml mudou mais que platform_toolsets.api_server")
    if toolsets(a, "telegram") != toolsets(d, "telegram"):
        raise SystemExit("RECUSADO: os toolsets do Telegram mudariam")
    if toolsets(d, "api_server") != []:
        raise SystemExit("RECUSADO: api_server não resolveria para zero toolsets")


def editar_env(texto: str) -> str:
    atual = env_dict(texto)
    for k, v in NOVAS_ENV.items():
        if k in atual and atual[k] != v:
            raise SystemExit(f"RECUSADO: {k} já existe com outro valor no .env do default")
    if "API_SERVER_CORS_ORIGINS" in atual:
        raise SystemExit("RECUSADO: API_SERVER_CORS_ORIGINS presente (navegador não pode falar com o Hermes)")
    novas = {k: v for k, v in NOVAS_ENV.items() if k not in atual}
    if "API_SERVER_KEY" not in atual:
        novas["API_SERVER_KEY"] = secrets.token_urlsafe(48)
    base = texto if texto.endswith("\n") else texto + "\n"
    return base + "\n# Bia VOLC (15/10/2026): API Server só em loopback, sem ferramentas\n" + \
        "".join(f"{k}={v}\n" for k, v in novas.items())


def conferir_env(antes: str, depois: str) -> None:
    a, d = env_dict(antes), env_dict(depois)
    for k, v in a.items():
        if d.get(k) != v:
            raise SystemExit(f"RECUSADO: a edição do .env alteraria {k}")
    extras = set(d) - set(a)
    if not extras <= set(NOVAS_ENV) | {"API_SERVER_KEY"}:
        raise SystemExit("RECUSADO: a edição do .env acrescentaria chave inesperada")


# ── gates de depois ─────────────────────────────────────────────────────────

def http(caminho: str, chave: str | None) -> tuple[int, str]:
    req = urllib.request.Request(f"http://127.0.0.1:{PORTA}{caminho}")
    if chave:
        req.add_header("Authorization", f"Bearer {chave}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, type(e).__name__


def gates(antes: dict, prazo_s: int = 120) -> dict:
    fim = time.time() + prazo_s
    ultimo: dict = {}
    while time.time() < fim:
        f = foto()
        chave = env_dict(ENV.read_text()).get("API_SERVER_KEY", "")
        st_h, _ = http("/health", None)
        st_t, corpo_t = http("/v1/toolsets", chave)
        st_m, _ = http("/v1/models", None)
        try:
            dados = json.loads(corpo_t)
            linhas = dados.get("data", dados) if isinstance(dados, dict) else dados
            habilitados = [x.get("name") for x in linhas if isinstance(x, dict) and x.get("enabled")]
        except Exception:  # noqa: BLE001
            habilitados = ["<ilegivel>"]
        st_c, corpo_c = http("/v1/capabilities", chave)
        try:
            modelo = json.loads(corpo_c).get("model")
        except Exception:  # noqa: BLE001
            modelo = None
        ultimo = {
            "unit_ativa": f["unit_ativa"] == "active",
            "pid_novo": f["main_pid"] not in ("", "0", antes["main_pid"]),
            "telegram_igual_antes": f["telegram"] == antes["telegram"] and f["telegram"] is not None,
            "gateway_running": f["gateway_state"] == antes["gateway_state"],
            "um_so_gateway": f["processos_gateway_run"] == 1,
            "loopback_8642": f["ouvintes_8642"] == [f"127.0.0.1:{PORTA}"],
            "health_200": st_h == 200,
            "toolsets_api_zero": st_t == 200 and habilitados == [],
            "models_sem_chave_401": st_m in (401, 403),
            "toolsets_telegram_iguais": f["toolsets_telegram"] == antes["toolsets_telegram"],
            "mcp_zero": f["mcp_servers"] == 0,
            "modelo": modelo,
            "foto": f,
        }
        if all(v for k, v in ultimo.items() if k not in ("foto", "modelo")):
            ultimo["ok"] = True
            return ultimo
        time.sleep(4)
    ultimo["ok"] = False
    return ultimo


def restaurar(pasta: Path) -> None:
    shutil.copy2(pasta / "config.yaml", CONFIG)
    shutil.copy2(pasta / ".env", ENV)


def reiniciar() -> None:
    subprocess.run(["systemctl", "restart", UNIT], check=True)


def esperar_telegram(antes: dict, prazo_s: int = 120) -> bool:
    fim = time.time() + prazo_s
    while time.time() < fim:
        f = foto()
        if f["unit_ativa"] == "active" and f["telegram"] == antes["telegram"] and f["processos_gateway_run"] == 1:
            return True
        time.sleep(4)
    return False


# ── comandos ───────────────────────────────────────────────────────────────

def cmd_preflight() -> int:
    f = foto()
    f["projecao"] = {}
    texto = CONFIG.read_text()
    cfg_novo = yaml.safe_load(editar_config(texto))
    f["projecao"]["toolsets_api_server_com_vazio"] = toolsets(cfg_novo, "api_server")
    f["projecao"]["toolsets_telegram_iguais"] = toolsets(cfg_novo, "telegram") == f["toolsets_telegram"]
    print(json.dumps(f, ensure_ascii=False, indent=1))
    return 0


def cmd_ensaio() -> int:
    tmp = BACKUPS / f"ensaio-{time.strftime('%Y%m%d-%H%M%S')}"
    tmp.mkdir(parents=True, mode=0o700)
    orig_c, orig_e = sha(CONFIG), sha(ENV)
    shutil.copy2(CONFIG, tmp / "config.yaml")
    shutil.copy2(ENV, tmp / ".env")
    copia_c, copia_e = tmp / "config.copia.yaml", tmp / "env.copia"
    shutil.copy2(CONFIG, copia_c)
    shutil.copy2(ENV, copia_e)
    novo_c, novo_e = editar_config(copia_c.read_text()), editar_env(copia_e.read_text())
    conferir_config(copia_c.read_text(), novo_c)
    conferir_env(copia_e.read_text(), novo_e)
    copia_c.write_text(novo_c)
    copia_e.write_text(novo_e)
    editado = (sha(copia_c) != orig_c) and (sha(copia_e) != orig_e)
    shutil.copy2(tmp / "config.yaml", copia_c)   # o "rollback" das cópias
    shutil.copy2(tmp / ".env", copia_e)
    exato = sha(copia_c) == orig_c and sha(copia_e) == orig_e
    intocado = sha(CONFIG) == orig_c and sha(ENV) == orig_e
    shutil.rmtree(tmp)
    print(json.dumps({"edicao_aplicada_na_copia": editado, "rollback_exato": exato,
                      "arquivos_reais_intocados": intocado}, indent=1))
    return 0 if (editado and exato and intocado) else 1


def cmd_aplicar() -> int:
    antes = foto()
    if antes["unit_ativa"] != "active" or antes["telegram"] is None:
        print("RECUSADO: gateway do default não está ativo com Telegram; nada alterado"); return 2
    if antes["active_agents"]:
        print(f"RECUSADO: {antes['active_agents']} agente(s) ativo(s) agora; tente num momento quieto"); return 3
    if antes["platform_toolsets_api_server"] != "AUSENTE" or antes["env_api_server"]:
        print("RECUSADO: superfície API já configurada; use verificar"); return 4
    if antes["ouvintes_8642"]:
        print("RECUSADO: porta 8642 ocupada"); return 5
    carimbo = time.strftime("%Y%m%d-%H%M%S")
    pasta = BACKUPS / carimbo
    pasta.mkdir(parents=True, mode=0o700)
    shutil.copy2(CONFIG, pasta / "config.yaml")
    shutil.copy2(ENV, pasta / ".env")
    os.chmod(pasta / ".env", 0o600)
    recibo = {"carimbo": carimbo, "backup": str(pasta), "antes": antes}
    novo_c, novo_e = editar_config(CONFIG.read_text()), editar_env(ENV.read_text())
    conferir_config(CONFIG.read_text(), novo_c)
    conferir_env(ENV.read_text(), novo_e)
    CONFIG.write_text(novo_c)
    ENV.write_text(novo_e)
    os.chmod(ENV, 0o600)
    recibo["sha_depois"] = {"config": sha(CONFIG), "env": sha(ENV)}
    reiniciar()
    g = gates(antes)
    recibo["gates"] = g
    if not g.get("ok"):
        restaurar(pasta)
        reiniciar()
        recibo["rollback"] = {"executado": True, "telegram_ok": esperar_telegram(antes),
                              "sha_config_restaurado": sha(CONFIG) == antes["sha_config"],
                              "sha_env_restaurado": sha(ENV) == antes["sha_env"]}
    (pasta / "recibo.json").write_text(json.dumps(recibo, ensure_ascii=False, indent=1))
    print(json.dumps(recibo, ensure_ascii=False, indent=1))
    return 0 if g.get("ok") else 1


def cmd_verificar() -> int:
    f = foto()
    antes = {**f, "main_pid": "-"}
    g = gates(antes, prazo_s=5)
    g.pop("pid_novo", None)
    print(json.dumps(g, ensure_ascii=False, indent=1))
    return 0


def cmd_reverter(pasta: str) -> int:
    antes = foto()
    restaurar(Path(pasta))
    reiniciar()
    ok = esperar_telegram(antes)
    print(json.dumps({"restaurado_de": pasta, "telegram_ok": ok, "depois": foto()}, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"preflight": cmd_preflight, "ensaio": cmd_ensaio, "aplicar": cmd_aplicar,
              "verificar": cmd_verificar}.get(c, lambda: cmd_reverter(sys.argv[2]) if c == "reverter"
                                              else (print(__doc__) or 2))())
