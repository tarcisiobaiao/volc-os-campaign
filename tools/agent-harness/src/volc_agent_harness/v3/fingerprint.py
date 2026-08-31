"""Fingerprint canônico da árvore relevante de um gate.

Por que a árvore inteira, e não a lista de arquivos "do gate"
------------------------------------------------------------
Um teste pytest importa `conftest.py`, plugins e qualquer módulo rastreado que
lhe dê vontade. Um `tsc` lê `tsconfig.json` e o grafo inteiro de imports. Um
script de catálogo importa o que quiser. Calcular o fecho transitivo exato
dessas dependências é um problema de análise estática por linguagem — caro,
incompleto e, o pior, *silenciosamente* incompleto: quando ele erra para menos,
o harness reutiliza uma prova que não vale, e ninguém percebe.

A troca aqui é deliberada e assimétrica:

* **sobreinvalidar custa tempo** — um gate roda de novo sem precisar;
* **reutilizar indevidamente custa a verdade** — uma prova verde passa a atestar
  um experimento que não aconteceu.

Enquanto não houver fechamento preciso e PROVADO do grafo de dependências, o
conservador é a resposta certa. Medido no repositório real: 1894 arquivos,
36 MB, ~225 ms por fingerprint completo. É barato o bastante para rodar nos
quatro pontos de revalidação.

⚠️ O QUE ISTO NÃO FECHA
Sobra janela entre a última medição e o `execve`, e entre o `execve` e a leitura
de cada arquivo pelo processo. Fechar isso exige sandbox ou snapshot imutável da
árvore — é G1b, que segue ABERTA. Este módulo fecha a janela de COMPILAÇÃO até
a EXECUÇÃO, não a janela de execução.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

from .failures import FailureClass, HarnessFailure

#: Versão da forma de calcular. Entra no digest: mudar a receita invalida provas
#: antigas em vez de compará-las com régua diferente.
FINGERPRINT_VERSION = 1

#: Fora do fingerprint por construção. São artefatos do PRÓPRIO harness e caches
#: derivados: se entrassem, cada run invalidaria o run seguinte e o ledger nunca
#: reutilizaria nada — o oposto do que ele existe para fazer.
EXCLUSOES: tuple[str, ...] = (
    ".git/",
    "tools/agent-harness/runs/",
    "tools/agent-harness/evidence-ledger.sqlite",
    "tools/agent-harness/worktree-registry.sqlite",
    ".agent-worktrees/",
    "__pycache__/",
    "node_modules/",
    ".venv/",
    ".venv-adk/",
    ".venv-graphify/",
    ".graphify-cache/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
)

_SUFIXOS_EXCLUIDOS = (".pyc", ".pyo", ".sqlite", ".sqlite-wal", ".sqlite-shm")


def _excluido(rel: str) -> bool:
    if rel.endswith(_SUFIXOS_EXCLUIDOS):
        return True
    for padrao in EXCLUSOES:
        if padrao.endswith("/"):
            if rel.startswith(padrao) or f"/{padrao}" in f"/{rel}":
                return True
        elif rel == padrao or rel.startswith(padrao):
            return True
    return False


def _e_repositorio(tree: Path) -> bool:
    return subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "--git-dir"],
        capture_output=True, check=False,
    ).returncode == 0


def _caminhados(tree: Path) -> list[str]:
    """Varredura do diretório, para árvore que não é repositório Git.

    Sem Git não há como distinguir fonte de artefato, então entra tudo o que as
    exclusões não barram. É MAIS conservador que a lista rastreada — inclui
    untracked — e sobreinvalidar é o lado certo de errar.
    """

    achados: list[str] = []
    for alvo in tree.rglob("*"):
        if alvo.is_dir() and not alvo.is_symlink():
            continue
        rel = alvo.relative_to(tree).as_posix()
        if not _excluido(rel):
            achados.append(rel)
    return achados


def _rastreados(tree: Path) -> list[str]:
    if not _e_repositorio(tree):
        return _caminhados(tree)
    saida = subprocess.run(
        ["git", "-C", str(tree), "ls-files", "-z"],
        capture_output=True, check=False,
    )
    if saida.returncode != 0:
        # É repositório e mesmo assim falhou: isso é infraestrutura quebrada,
        # não "árvore sem git". Não caímos na varredura para não mascarar.
        raise HarnessFailure(
            FailureClass.INFRASTRUCTURE_ERROR,
            "não foi possível listar os arquivos rastreados da worktree",
            detalhe=saida.stderr.decode("utf-8", "replace")[:200],
            reproducao=f"git -C {tree} ls-files",
        )
    return [p.decode("utf-8") for p in saida.stdout.split(b"\0") if p]


def _assert_contido(tree: Path, rel: str) -> None:
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts:
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "caminho de insumo escapa da worktree",
            detalhe=rel,
        )


def _entrada_symlink(tree: Path, rel: str, alvo: Path) -> bytes:
    """Symlink entra pelo DESTINO TEXTUAL, e o destino é validado.

    Seguir o link para hashear conteúdo leria de fora da worktree — e um link
    apontando para `/etc/passwd` viraria "insumo material" do gate. O texto do
    destino é o que o Git versiona, e é o que muda quando alguém repõe o link.
    """

    destino = os.readlink(alvo)
    p = PurePosixPath(destino)
    if p.is_absolute():
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "symlink rastreado aponta para caminho absoluto",
            detalhe=f"{rel} -> {destino}",
        )
    resolvido = (alvo.parent / destino).resolve()
    raiz = tree.resolve()
    if raiz != resolvido and raiz not in resolvido.parents:
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "symlink rastreado escapa da worktree",
            detalhe=f"{rel} -> {destino}",
            reproducao=f"readlink {rel}",
        )
    return b"symlink\0" + destino.encode("utf-8")


def _entrada_arquivo(alvo: Path) -> bytes:
    modo = b"x" if os.access(alvo, os.X_OK) else b"-"
    return b"file\0" + modo + b"\0" + hashlib.sha256(alvo.read_bytes()).digest()


def tree_fingerprint(
    tree: Path,
    *,
    extra_paths: Iterable[str] = (),
    exclusoes: Sequence[str] | None = None,
) -> str:
    """Digest conservador e canônico da árvore relevante.

    Entra: todo arquivo rastreado pelo Git, mais os ``extra_paths`` autorizados
    (produced/untracked que o gate pode observar). De cada um: caminho relativo
    normalizado, bit de execução e conteúdo. Symlink entra pelo destino textual.

    É ESTÁVEL entre worktrees: nada aqui carrega caminho absoluto. Duas árvores
    com o mesmo conteúdo dão o mesmo digest, que é o que permite reuso legítimo
    de prova entre runs.
    """

    tree = Path(tree)
    if exclusoes is not None:
        global EXCLUSOES                                   # noqa: PLW0603
        anteriores, EXCLUSOES = EXCLUSOES, tuple(exclusoes)
        try:
            return tree_fingerprint(tree, extra_paths=extra_paths)
        finally:
            EXCLUSOES = anteriores

    caminhos: set[str] = set()
    for rel in _rastreados(tree):
        if not _excluido(rel):
            caminhos.add(rel)
    for rel in extra_paths:
        _assert_contido(tree, rel)
        if not _excluido(rel):
            caminhos.add(PurePosixPath(rel).as_posix())

    h = hashlib.sha256()
    h.update(f"fingerprint-v{FINGERPRINT_VERSION}".encode())
    h.update(b"\0")
    for rel in sorted(caminhos):
        alvo = tree / rel
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        if alvo.is_symlink():
            h.update(_entrada_symlink(tree, rel, alvo))
        elif alvo.is_file():
            h.update(_entrada_arquivo(alvo))
        else:
            # Ausente é material: um arquivo que sumiu muda o experimento.
            h.update(b"ausente")
        h.update(b"\0")
    return h.hexdigest()
