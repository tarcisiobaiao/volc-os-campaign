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
import signal
import tempfile
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
CABECA_ENV = "# Bia VOLC (15/10/2026): API Server só em loopback, sem ferramentas"
LINHA_CONFIG = "api_server: []"


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
    try:
        c = sqlite3.connect(f"file:{CASA / 'state.db'}?mode=ro", uri=True, timeout=5)
    except Exception as exc:  # noqa: BLE001
        return {"erro": type(exc).__name__}
    por_source = dict(c.execute("select source, count(*) from sessions group by source").fetchall())
    ativas_tg = c.execute("select id, message_count from sessions where source='telegram' "
                          "and ended_at is null order by started_at").fetchall()
    c.close()
    return {"por_source": por_source,
            "telegram_ativas": [{"id_sha": hashlib.sha256(i.encode()).hexdigest()[:12],
                                 "mensagens": n} for i, n in ativas_tg]}


def foto() -> dict:
    try:
        return _foto()
    except Exception as exc:  # noqa: BLE001 — foto falha vira dado, nunca exceção no meio do aplicar
        return {"erro_foto": f"{type(exc).__name__}"}


def _estado_mtime() -> float:
    try:
        return ESTADO.stat().st_mtime
    except OSError:
        return 0.0


def _foto() -> dict:
    cfg = yaml.safe_load(CONFIG.read_text()) or {}
    env = env_dict(ENV.read_text())
    g = gateway_state()
    return {
        "unit_ativa": sh("systemctl", "is-active", UNIT),
        "unit_execstart_gateway_run": "gateway run" in sh("systemctl", "show", "-p", "ExecStart", "--value", UNIT),
        "gateway_state_mtime": _estado_mtime(),
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

def escrever_atomico(p: Path, texto: str) -> None:
    """Escreve em arquivo temporário 0600 no MESMO diretório e troca por rename."""
    fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.bia-", dir=str(p.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def desfazer_config(texto: str) -> str:
    """Remove só a linha inserida (`  api_server: []` logo abaixo de `platform_toolsets:`)."""
    linhas = texto.splitlines(keepends=True)
    for i, l in enumerate(linhas[:-1]):
        if l.rstrip() == "platform_toolsets:" and linhas[i + 1].strip() == LINHA_CONFIG:
            del linhas[i + 1]
            return "".join(linhas)
    return texto


def desfazer_env(texto: str) -> str:
    """Remove só o bloco anexado (cabeça + chaves API_SERVER_* que ele trouxe)."""
    linhas = texto.splitlines(keepends=True)
    if not any(l.rstrip() == CABECA_ENV for l in linhas):
        return texto
    saida, no_bloco = [], False
    for l in linhas:
        if l.rstrip() == CABECA_ENV:
            no_bloco = True
            if saida and saida[-1].strip() == "":
                saida.pop()  # a linha em branco que o editar_env acrescentou antes da cabeça
            continue
        if no_bloco and l.split("=", 1)[0].strip() in set(NOVAS_ENV) | {"API_SERVER_KEY"}:
            continue
        no_bloco = False
        saida.append(l)
    return "".join(saida)

def editar_config(texto: str) -> str:
    """Insere `  api_server: []` como 1º filho de `platform_toolsets:`. Uma linha."""
    linhas = texto.splitlines(keepends=True)
    idx = next((i for i, l in enumerate(linhas) if l.rstrip() == "platform_toolsets:"), None)
    if idx is None:
        raise SystemExit("RECUSADO: config.yaml sem bloco platform_toolsets: no topo")
    filho = next((l for l in linhas[idx + 1:] if l.strip()), "")
    recuo = filho[: len(filho) - len(filho.lstrip())] or "  "
    linhas.insert(idx + 1, f"{recuo}{LINHA_CONFIG}\n")
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
    return base + f"\n{CABECA_ENV}\n" + \
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


def gates(antes: dict, prazo_s: int = 120, desde: float = 0.0, exigir_pid_novo: bool = True) -> dict:
    fim = time.time() + prazo_s
    ultimo: dict = {}
    while time.time() < fim:
        f = foto()
        if "erro_foto" in f:
            ultimo = {"foto": f}
            time.sleep(4)
            continue
        try:
            chave = env_dict(ENV.read_text()).get("API_SERVER_KEY", "")
        except OSError:
            chave = ""
        st_h, _ = http("/health", None)
        st_t, corpo_t = http("/v1/toolsets", chave)
        st_m, _ = http("/v1/models", None)
        try:
            dados = json.loads(corpo_t)
            linhas = dados.get("data") if isinstance(dados, dict) else dados
            if not isinstance(linhas, list) or not linhas:
                raise ValueError("toolsets fora do contrato")
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
            "pid_novo": (not exigir_pid_novo) or f["main_pid"] not in ("", "0", antes["main_pid"]),
            # O estado tem de ser do processo NOVO e escrito depois do restart:
            # logo após o restart o arquivo ainda carrega o connected do morto.
            "estado_do_pid_atual": str(f["gateway_state_pid"]) == f["main_pid"],
            "estado_fresco": f["gateway_state_mtime"] > desde,
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
        if all(v for k, v in ultimo.items() if k not in ("foto", "modelo", "estado_fresco")) and \
                ultimo["estado_fresco"]:
            ultimo["ok"] = True
            return ultimo
        time.sleep(4)
    ultimo["ok"] = False
    return ultimo


def restaurar(pasta: Path) -> dict:
    """Desfaz SÓ a edição (não sobrescreve o arquivo inteiro: preserva o que o
    gateway ou o dono tenham escrito depois do backup). Confere contra o backup."""
    c_atual, e_atual = CONFIG.read_text(), ENV.read_text()
    c_novo, e_novo = desfazer_config(c_atual), desfazer_env(e_atual)
    escrever_atomico(CONFIG, c_novo)
    escrever_atomico(ENV, e_novo)
    b_c, b_e = (pasta / "config.yaml").read_text(), (pasta / ".env").read_text()
    return {
        "config_igual_backup": c_novo == b_c,
        "env_igual_backup": e_novo == b_e,
        "config_yaml_equivalente": (yaml.safe_load(c_novo) or {}) == (yaml.safe_load(b_c) or {}),
        "env_sem_api_server": not any(k.startswith("API_SERVER_") for k in env_dict(e_novo)),
        "env_chaves_do_backup_intactas": all(env_dict(e_novo).get(k) == v for k, v in env_dict(b_e).items()),
    }


def reiniciar() -> int:
    return subprocess.run(["systemctl", "restart", UNIT]).returncode


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
    copia_c.write_text(desfazer_config(copia_c.read_text()))   # o MESMO rollback do aplicar
    copia_e.write_text(desfazer_env(copia_e.read_text()))
    exato = sha(copia_c) == orig_c and sha(copia_e) == orig_e
    intocado = sha(CONFIG) == orig_c and sha(ENV) == orig_e
    shutil.rmtree(tmp)
    print(json.dumps({"edicao_aplicada_na_copia": editado, "rollback_exato": exato,
                      "arquivos_reais_intocados": intocado}, indent=1))
    return 0 if (editado and exato and intocado) else 1


def cmd_aplicar() -> int:
    antes = foto()
    if "erro_foto" in antes:
        print(f"RECUSADO: não consegui ler o estado ({antes['erro_foto']}); nada alterado"); return 2
    if antes["unit_ativa"] != "active" or antes["telegram"] != "connected":
        print("RECUSADO: gateway do default não está ativo com Telegram connected; nada alterado"); return 2
    if antes["processos_gateway_run"] != 1 or not antes["unit_execstart_gateway_run"]:
        print("RECUSADO: não há exatamente um `gateway run` sob a unit; nada alterado"); return 2
    if str(antes["gateway_state_pid"]) != antes["main_pid"]:
        print("RECUSADO: gateway_state.json não é do processo atual; nada alterado"); return 2
    if antes["mcp_servers"] != 0:
        print("RECUSADO: há MCP configurado no default; a superfície API não seria isolada"); return 2
    if antes["active_agents"]:
        print(f"RECUSADO: {antes['active_agents']} agente(s) ativo(s) agora; tente num momento quieto"); return 3
    if antes["platform_toolsets_api_server"] != "AUSENTE" or antes["env_api_server"]:
        print("RECUSADO: superfície API já configurada; use verificar"); return 4
    if antes["ouvintes_8642"]:
        print("RECUSADO: porta 8642 ocupada"); return 5

    texto_c, texto_e = CONFIG.read_text(), ENV.read_text()
    novo_c, novo_e = editar_config(texto_c), editar_env(texto_e)
    conferir_config(texto_c, novo_c)   # tudo conferido ANTES de qualquer escrita
    conferir_env(texto_e, novo_e)

    carimbo = time.strftime("%Y%m%d-%H%M%S")
    pasta = BACKUPS / carimbo
    pasta.mkdir(parents=True, mode=0o700)
    (pasta / "config.yaml").write_text(texto_c)
    (pasta / ".env").write_text(texto_e)
    os.chmod(pasta / ".env", 0o600)
    os.chmod(pasta / "config.yaml", 0o600)
    recibo: dict = {"carimbo": carimbo, "backup": str(pasta), "antes": antes}

    def gravar_recibo() -> None:
        escrever_atomico(pasta / "recibo.json", json.dumps(recibo, ensure_ascii=False, indent=1))

    # SIGHUP/SIGINT/SIGTERM viram exceção: a queda do SSH ou um Ctrl-C no meio
    # nunca deixam a configuração meio aplicada sem rollback.
    def _sinal(signum, _frame):
        raise KeyboardInterrupt(f"sinal {signum}")
    for sg in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(sg, _sinal)

    ok = False
    try:
        if sha(CONFIG) != antes["sha_config"] or sha(ENV) != antes["sha_env"]:
            raise RuntimeError("arquivos mudaram entre a leitura e a escrita")
        escrever_atomico(CONFIG, novo_c)
        escrever_atomico(ENV, novo_e)
        recibo["sha_depois"] = {"config": sha(CONFIG), "env": sha(ENV)}
        desde = time.time()
        recibo["restart_rc"] = reiniciar()
        g = gates(antes, desde=desde)
        recibo["gates"] = g
        ok = bool(g.get("ok"))
    except BaseException as exc:  # noqa: BLE001 — qualquer falha leva ao rollback abaixo
        recibo["excecao"] = type(exc).__name__
        ok = False
    finally:
        if not ok:
            rb: dict = {"executado": True}
            try:
                rb["conferencia"] = restaurar(pasta)
                desde = time.time()
                rb["restart_rc"] = reiniciar()
                g2 = gates({**antes, "main_pid": "-"}, prazo_s=150, desde=desde, exigir_pid_novo=False)
                # Depois do rollback não há API: só o Telegram e a unit importam.
                rb["telegram_ok"] = bool(g2.get("unit_ativa") and g2.get("estado_do_pid_atual")
                                         and g2.get("estado_fresco") and g2.get("telegram_igual_antes")
                                         and g2.get("um_so_gateway"))
                rb["sha_config_igual_antes"] = sha(CONFIG) == antes["sha_config"]
                rb["sha_env_igual_antes"] = sha(ENV) == antes["sha_env"]
            except BaseException as exc2:  # noqa: BLE001
                rb["excecao_no_rollback"] = type(exc2).__name__
            recibo["rollback"] = rb
        try:
            gravar_recibo()
        except BaseException:  # noqa: BLE001
            pass
    print(json.dumps(recibo, ensure_ascii=False, indent=1, default=str))
    return 0 if ok else 1


def cmd_verificar() -> int:
    """Gates contra o `antes` do último recibo do aplicar (toolsets do Telegram,
    estado do Telegram). Sai != 0 se qualquer gate falhar."""
    recibos = sorted(BACKUPS.glob("*/recibo.json"))
    if not recibos:
        print("SEM RECIBO do aplicar: nada a comparar"); return 2
    antes = json.loads(recibos[-1].read_text())["antes"]
    g = gates({**antes, "main_pid": "-"}, prazo_s=10, desde=0.0, exigir_pid_novo=False)
    g["comparado_com"] = str(recibos[-1])
    print(json.dumps(g, ensure_ascii=False, indent=1, default=str))
    return 0 if g.get("ok") else 1


def cmd_reverter(pasta: str) -> int:
    p = Path(pasta)
    if not ((p / "config.yaml").is_file() and (p / ".env").is_file()):
        print("RECUSADO: o backup não tem config.yaml e .env; nada alterado"); return 2
    antes = foto()
    conf = restaurar(p)
    desde = time.time()
    rc = reiniciar()
    g = gates({**antes, "main_pid": "-"}, prazo_s=150, desde=desde, exigir_pid_novo=False)
    ok = bool(g.get("unit_ativa") and g.get("estado_do_pid_atual") and g.get("estado_fresco")
              and g.get("telegram_igual_antes") and g.get("um_so_gateway"))
    print(json.dumps({"restaurado_de": pasta, "conferencia": conf, "restart_rc": rc, "telegram_ok": ok},
                     ensure_ascii=False, indent=1, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"preflight": cmd_preflight, "ensaio": cmd_ensaio, "aplicar": cmd_aplicar,
              "verificar": cmd_verificar}.get(c, lambda: cmd_reverter(sys.argv[2]) if c == "reverter"
                                              else (print(__doc__) or 2))())
