#!/usr/bin/env python3
"""volc-cerebro-web — executor tipado do cérebro para a Bia web.

Roda no VPS do Hermes como COMANDO FORÇADO de SSH do usuário de sistema
`volc-cerebro-web` (sem shell interativo, sem forwarding). Lê UM pedido JSON
do stdin e devolve UM JSON no stdout. Só sabe duas coisas:

- `status`: lê o estado git dos três cérebros (`--no-optional-locks`: não
  escreve nem o índice). Sem fetch, sem pull.
- `gravar`: cria UM arquivo NOVO + sidecar `.meta.yaml` na estação de visitante
  `inbox/bia-web/` do cérebro escolhido (convenção de `inbox/_TEMPLATE`).
  Nunca sobrescreve, nunca edita arquivo existente, nunca escreve fora da
  estação, nunca faz commit/push. O usuário do sistema só tem escrita nas três
  estações — o resto do repositório é root:root.

Sem dependências fora da biblioteca padrão. Testado em `backend/tests/test_cerebro_executor.py`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(os.environ.get("VOLC_CEREBROS_RAIZ", "/root/cerebros"))
REPOS = {"volc": "cerebro-volc", "arbitragem": "cerebro-arbitragem", "pessoal": "cerebro-pessoal"}
ESTACAO = Path("inbox") / "bia-web"
TIPOS = {"decisao": "proposta-canonica", "captura": "nota", "pendencia": "nota",
         "referencia": "referencia", "nota": "nota"}
MAX_PEDIDO = 64 * 1024
MAX_TITULO = 120
MAX_CONTEUDO = 20_000
SEGREDOS = re.compile(
    r"(ghp_[A-Za-z0-9]{8,}|github_pat_|\bsk-[A-Za-z0-9_-]{12,}|xox[abp]-|AKIA[0-9A-Z]{12,}"
    r"|BEGIN [A-Z ]*PRIVATE KEY|refresh_token|client_secret|password\s*=|passwd\s*=|token\s*=|api_key\s*="
    r"|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,})", re.I)
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class Recusa(Exception):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(codigo)
        self.codigo, self.mensagem = codigo, mensagem


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args],
                       capture_output=True, text=True, timeout=20,
                       env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0",
                            "HOME": os.environ.get("HOME", "/nonexistent")})
    if r.returncode != 0:
        raise Recusa("git_falhou", f"git {args[0]} falhou em {repo.name}")
    return r.stdout.strip()


def status() -> dict:
    repos = []
    for chave, nome in REPOS.items():
        repo = RAIZ / nome
        item = {"cerebro": chave, "repo": nome}
        try:
            item["branch"] = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
            sha, data = _git(repo, "log", "-1", "--format=%h|%cI").split("|", 1)
            item.update(commit=sha, commit_em=data)
            linhas = [l for l in _git(repo, "status", "--porcelain", "-uall").splitlines() if l.strip()]
            estacao = str(ESTACAO) + "/"
            item["alteracoes"] = sum(1 for l in linhas if estacao not in l)
            item["capturas_web_pendentes"] = sum(1 for l in linhas if estacao in l and not l.endswith(".meta.yaml"))
            try:
                frente, atras = _git(repo, "rev-list", "--left-right", "--count", "HEAD...origin/main").split()
                item.update(a_frente=int(frente), atras=int(atras))
            except Recusa:
                item.update(a_frente=None, atras=None)
            fetch = repo / ".git" / "FETCH_HEAD"
            item["ultima_busca"] = (datetime.fromtimestamp(fetch.stat().st_mtime, timezone.utc).isoformat()
                                    if fetch.exists() else None)
            item["estacao_web"] = (repo / ESTACAO).is_dir()
            item["ok"] = True
        except Recusa as exc:
            item.update(ok=False, erro=exc.codigo)
        repos.append(item)
    return {"ok": True, "op": "status", "repos": repos,
            "verificado_em": datetime.now(timezone.utc).isoformat(), "somente_leitura": True}


def _limpo(texto: str) -> str:
    texto = unicodedata.normalize("NFC", str(texto or ""))
    return "".join(ch for ch in texto if ch in "\n\t" or (ord(ch) >= 32
                   and not 0x202A <= ord(ch) <= 0x202E and not 0x2066 <= ord(ch) <= 0x2069))


def _slug(titulo: str) -> str:
    base = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode().lower()
    return (re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:48].strip("-")) or "captura"


def _yaml(valor) -> str:
    return json.dumps(valor, ensure_ascii=False)  # JSON é YAML válido e sem ambiguidade


def _existente(estacao: Path, request_id: str):
    for meta in estacao.glob("*.meta.yaml"):
        try:
            if f"request_id: {_yaml(request_id)}" in meta.read_text(encoding="utf-8"):
                return meta
        except OSError:
            continue
    return None


def _recibo(repo: Path, conteudo_path: Path, meta_path: Path, ja_existia: bool) -> dict:
    dados = conteudo_path.read_bytes()
    rel = conteudo_path.relative_to(repo).as_posix()
    linhas = _git(repo, "status", "--porcelain", "-uall", "--", str(ESTACAO)).splitlines()
    estado = next((l[:2] for l in linhas if l.endswith(rel)), "  ")
    return {"ok": True, "op": "gravar", "repo": repo.name, "caminho": rel,
            "sidecar": meta_path.relative_to(repo).as_posix(),
            "sha256": hashlib.sha256(dados).hexdigest(), "bytes": len(dados),
            "git": {"estado": estado.strip() or "limpo", "commitado": False, "sincronizado_github": False},
            "ja_existia": ja_existia}


def gravar(p: dict) -> dict:
    destino = p.get("destino")
    if destino not in REPOS:
        raise Recusa("destino_invalido", "Destino precisa ser volc, arbitragem ou pessoal.")
    tipo = p.get("tipo")
    if tipo not in TIPOS:
        raise Recusa("tipo_invalido", "Tipo inválido.")
    request_id = str(p.get("request_id") or "")
    if not UUID.match(request_id):
        raise Recusa("request_id_invalido", "request_id precisa ser UUID.")
    titulo = _limpo(p.get("titulo")).replace("\n", " ").strip()
    conteudo = _limpo(p.get("conteudo")).strip()
    if not titulo or len(titulo) > MAX_TITULO:
        raise Recusa("titulo_invalido", "Título vazio ou longo demais.")
    if not conteudo or len(conteudo) > MAX_CONTEUDO:
        raise Recusa("conteudo_invalido", "Captura vazia ou longa demais.")
    if SEGREDOS.search(conteudo) or SEGREDOS.search(titulo):
        raise Recusa("parece_segredo", "A captura parece conter segredo; não foi gravada.")
    tags = [re.sub(r"[^a-z0-9-]", "", unicodedata.normalize("NFKD", _limpo(t)).encode("ascii", "ignore")
                   .decode().lower().replace(" ", "-"))[:32] for t in (p.get("tags") or [])[:8]]
    origem = p.get("origem") or {}
    origem = {k: str(origem.get(k)) for k in ("conversa_id", "execucao_id")
              if isinstance(origem.get(k), str) and UUID.match(origem.get(k))}

    repo = (RAIZ / REPOS[destino]).resolve()
    estacao = repo / ESTACAO
    if estacao.is_symlink() or not estacao.is_dir() or estacao.resolve().parent.parent != repo:
        raise Recusa("estacao_ausente", f"A estação inbox/bia-web não existe em {repo.name}.")

    anterior = _existente(estacao, request_id)
    if anterior is not None:   # idempotente: mesmo request_id devolve o mesmo arquivo
        return _recibo(repo, anterior.with_name(anterior.name[: -len(".meta.yaml")]), anterior, True)

    agora = datetime.now(timezone.utc).astimezone()
    base = f"{agora:%Y-%m-%d-%H%M}-{_slug(titulo)}"
    for n in range(1, 50):
        nome = f"{base}.md" if n == 1 else f"{base}-{n}.md"
        alvo = estacao / nome
        try:
            fd = os.open(alvo, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
            break
        except FileExistsError:
            continue
    else:
        raise Recusa("nome_esgotado", "Não foi possível escolher um nome livre.")
    corpo = f"# {titulo}\n\n{conteudo}\n".encode("utf-8")
    with os.fdopen(fd, "wb") as f:
        f.write(corpo)
    meta = estacao / f"{nome}.meta.yaml"
    linhas = [
        f"autor: {_yaml('bia-web')}",
        f"data: {_yaml(agora.isoformat(timespec='seconds'))}",
        f"fonte: {_yaml('conversa')}",
        f"tipo: {_yaml(TIPOS[tipo])}",
        f"tipo_bia: {_yaml(tipo)}",
        f"maturidade: {_yaml('draft')}",
        f"destino_sugerido: {_yaml('canônico via /salve no Telegram')}",
        "relacionado: []",
        f"tags: {_yaml([t for t in tags if t])}",
        f"origem: {_yaml('volc-os-web')}",
        f"request_id: {_yaml(request_id)}",
        f"sha256: {_yaml(hashlib.sha256(corpo).hexdigest())}",
    ] + [f"{k}: {_yaml(v)}" for k, v in origem.items()]
    fd = os.open(meta, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    return _recibo(repo, alvo, meta, False)


def main() -> int:
    try:
        bruto = sys.stdin.buffer.read(MAX_PEDIDO + 1)
        if len(bruto) > MAX_PEDIDO:
            raise Recusa("pedido_grande", "Pedido acima de 64 KB.")
        pedido = json.loads(bruto.decode("utf-8") or "{}")
        if not isinstance(pedido, dict):
            raise Recusa("pedido_invalido", "Pedido precisa ser objeto JSON.")
        op = pedido.get("op")
        if op == "status":
            saida = status()
        elif op == "gravar":
            saida = gravar(pedido)
        else:
            raise Recusa("op_desconhecida", "Operação desconhecida.")
    except Recusa as exc:
        saida = {"ok": False, "codigo": exc.codigo, "mensagem": exc.mensagem}
    except (ValueError, UnicodeDecodeError):
        saida = {"ok": False, "codigo": "pedido_invalido", "mensagem": "JSON inválido."}
    except Exception as exc:  # noqa: BLE001 — nunca devolve traceback ao cliente
        saida = {"ok": False, "codigo": "erro_interno", "mensagem": type(exc).__name__}
    sys.stdout.write(json.dumps(saida, ensure_ascii=False) + "\n")
    return 0 if saida.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
