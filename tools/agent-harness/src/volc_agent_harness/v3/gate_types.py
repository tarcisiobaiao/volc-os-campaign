"""Gates tipados: cada tipo tem schema próprio, nada de argv livre.

A refutação foi decisiva: uma allowlist de executáveis não é fronteira de
segurança, porque ``python`` está nela e um interpretador aceita código
arbitrário. ``python -c "import os;os.remove(x)"`` atravessou as duas guardas.

Argumento livre é o problema. Aqui o gate declara o TIPO, e o tipo constrói o
argv — o autor da missão nunca escreve a linha de comando inteira.

⚠️ CONTENÇÃO — o que este módulo NÃO garante
--------------------------------------------
Análise de argumento não torna código Python ou Node confiável. Um teste que a
missão manda rodar executa com os privilégios do processo. A contenção real vem
de onde o gate roda, não do que ele parece ser: worktree descartável registrada,
cwd fixo nela, ambiente sanitizado, e diff depois da execução.

Enquanto não houver backend de sandbox provado, este módulo **não afirma**
proteção do filesystem externo. Ele reduz superfície e torna a intenção
declarada — nada além disso.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, Literal, Sequence

from .failures import FailureClass, HarnessFailure

#: Flags que cada tipo aceita. O que não está aqui não passa.
FLAGS_PYTEST = frozenset({
    "-q", "-x", "--tb=short", "--tb=long", "--tb=no", "-p", "no:randomly",
    "no:cacheprovider", "--collect-only", "-k", "--maxfail=1",
})
FLAGS_UNITTEST = frozenset({"-v", "discover", "-s", "-p"})

_PROIBIDOS_SEMPRE = (
    "-c", "--command", "-e", "--eval", "--exec", "-i", "--interactive",
    "-delete", "-ok", "--eval-file",
)


def _caminho_contido(valor: str, *, worktree: Path) -> str:
    """Relativo, sem travessia, existente dentro da worktree."""

    if not valor or valor.startswith("-"):
        raise HarnessFailure(
            FailureClass.SPEC_ERROR, "alvo de gate inválido", detalhe=valor)
    p = PurePosixPath(valor)
    if p.is_absolute():
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "gate não aceita caminho absoluto", detalhe=valor)
    if ".." in p.parts:
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "gate não aceita travessia de diretório", detalhe=valor)
    destino = (worktree / p).resolve()
    if worktree.resolve() not in destino.parents and destino != worktree.resolve():
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "alvo de gate escapou da worktree", detalhe=valor)
    return p.as_posix()


def _sem_proibidos(tokens: Sequence[str]) -> None:
    achados = [t for t in tokens if t in _PROIBIDOS_SEMPRE]
    if achados:
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "argumento proibido em gate tipado",
            detalhe=", ".join(achados),
            reproducao=" ".join(tokens)[:160],
        )


@dataclass
class TypedGate:
    """Base. Cada subclasse constrói o argv; a missão nunca o escreve."""

    index: int
    timeout_seconds: int = 600
    kind: ClassVar[str] = "abstract"

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        raise NotImplementedError

    def evidence_inputs(self, *, worktree: Path) -> dict[str, str]:
        return {}

    def as_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items()}
        d["kind"] = self.kind
        return d


@dataclass
class PytestGate(TypedGate):
    targets: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=lambda: ["-q", "-p", "no:cacheprovider"])
    k_expression: str | None = None
    kind: ClassVar[str] = "pytest"

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        interp = toolchain.get("python")
        if not interp or not Path(interp).is_file():
            raise HarnessFailure(
                FailureClass.INFRASTRUCTURE_ERROR,
                "interpretador do toolchain ausente", detalhe=str(interp))
        _sem_proibidos(self.flags)
        desconhecidas = [f for f in self.flags if f not in FLAGS_PYTEST]
        if desconhecidas:
            raise HarnessFailure(
                FailureClass.AUTHORIZATION_BLOCK,
                "flag de pytest fora da allowlist",
                detalhe=", ".join(desconhecidas))
        if not self.targets:
            raise HarnessFailure(
                FailureClass.SPEC_ERROR, "PytestGate sem targets")
        alvos = [_caminho_contido(t, worktree=worktree) for t in self.targets]
        argv = [interp, "-m", "pytest", *alvos, *self.flags]
        if self.k_expression:
            argv += ["-k", self.k_expression]
        return argv

    def collect_argv(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        return self.build(worktree=worktree, toolchain=toolchain) + ["--collect-only"]


@dataclass
class UnittestGate(TypedGate):
    start_dir: str = "."
    pattern: str = "test_*.py"
    kind: ClassVar[str] = "unittest"

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        interp = toolchain.get("python")
        if not interp:
            raise HarnessFailure(
                FailureClass.INFRASTRUCTURE_ERROR, "interpretador ausente")
        alvo = _caminho_contido(self.start_dir, worktree=worktree)
        return [interp, "-m", "unittest", "discover", "-s", alvo, "-p", self.pattern]


def _package_json(worktree: Path) -> dict[str, Any]:
    p = worktree / "package.json"
    if not p.is_file():
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "package.json ausente na worktree", detalhe=str(p))
    return json.loads(p.read_text(encoding="utf-8"))


@dataclass
class NpmScriptGate(TypedGate):
    script: str = ""
    kind: ClassVar[str] = "npm_script"

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        if not self.script:
            raise HarnessFailure(FailureClass.SPEC_ERROR, "NpmScriptGate sem script")
        scripts = _package_json(worktree).get("scripts", {})
        if self.script not in scripts:
            raise HarnessFailure(
                FailureClass.SPEC_ERROR,
                "script não declarado no package.json rastreado",
                detalhe=f"{self.script} não está em {sorted(scripts)}")
        npm = toolchain.get("npm") or shutil.which("npm")
        if not npm:
            raise HarnessFailure(FailureClass.INFRASTRUCTURE_ERROR, "npm ausente")
        # npx e npm exec ficam fora por construção: só `npm run <script>`.
        return [npm, "run", self.script]

    def evidence_inputs(self, *, worktree: Path) -> dict[str, str]:
        import hashlib

        saida = {}
        for nome in ("package.json", "package-lock.json"):
            alvo = worktree / nome
            if alvo.is_file():
                saida[nome] = hashlib.sha256(alvo.read_bytes()).hexdigest()
        return saida


@dataclass
class TypeScriptGate(TypedGate):
    project_targets: list[str] = field(default_factory=list)
    kind: ClassVar[str] = "typescript"

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        tsc = toolchain.get("tsc")
        if not tsc or not Path(tsc).is_file():
            raise HarnessFailure(
                FailureClass.INFRASTRUCTURE_ERROR, "tsc do projeto ausente")
        alvos = [_caminho_contido(t, worktree=worktree) for t in self.project_targets]
        return [tsc, "--noEmit", "--skipLibCheck",
                "--moduleResolution", "bundler", "--module", "ESNext",
                "--target", "ES2020", *alvos]


@dataclass
class BuildGate(TypedGate):
    script: str = "build"
    kind: ClassVar[str] = "build"

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        return NpmScriptGate(index=self.index, script=self.script).build(
            worktree=worktree, toolchain=toolchain)

    def evidence_inputs(self, *, worktree: Path) -> dict[str, str]:
        return NpmScriptGate(index=self.index, script=self.script).evidence_inputs(
            worktree=worktree)


@dataclass
class GitDiffCheckGate(TypedGate):
    kind: ClassVar[str] = "git_diff_check"

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        git = toolchain.get("git") or shutil.which("git")
        if not git:
            raise HarnessFailure(FailureClass.INFRASTRUCTURE_ERROR, "git ausente")
        # Somente leitura por construção. clean, reset e checkout não existem
        # neste tipo — não há como declará-los.
        return [git, "diff", "--check"]


@dataclass
class TrackedScriptGate(TypedGate):
    script_path: str = ""
    args: list[str] = field(default_factory=list)
    kind: ClassVar[str] = "tracked_script"

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        import subprocess

        if not self.script_path:
            raise HarnessFailure(FailureClass.SPEC_ERROR, "TrackedScriptGate sem script")
        rel = _caminho_contido(self.script_path, worktree=worktree)
        rastreado = subprocess.run(
            ["git", "-C", str(worktree), "ls-files", "--error-unmatch", rel],
            capture_output=True, check=False,
        ).returncode == 0
        if not rastreado:
            raise HarnessFailure(
                FailureClass.AUTHORIZATION_BLOCK,
                "script de gate não é rastreado pelo Git",
                detalhe=rel,
                reproducao=f"git ls-files --error-unmatch {rel}")
        _sem_proibidos(self.args)
        for a in self.args:
            if not a.startswith("-"):
                _caminho_contido(a, worktree=worktree)
        interp = toolchain.get("python")
        return [interp, rel, *self.args] if interp else [f"./{rel}", *self.args]

    def evidence_inputs(self, *, worktree: Path) -> dict[str, str]:
        import hashlib

        alvo = worktree / self.script_path
        return {self.script_path: hashlib.sha256(alvo.read_bytes()).hexdigest()} \
            if alvo.is_file() else {}


TIPOS: dict[str, type[TypedGate]] = {
    "pytest": PytestGate,
    "unittest": UnittestGate,
    "npm_script": NpmScriptGate,
    "typescript": TypeScriptGate,
    "build": BuildGate,
    "git_diff_check": GitDiffCheckGate,
    "tracked_script": TrackedScriptGate,
}


def from_spec(index: int, spec: dict[str, Any]) -> TypedGate:
    """Constrói o gate a partir do schema. Não existe tipo GENERIC."""

    kind = spec.get("kind")
    if kind not in TIPOS:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "tipo de gate desconhecido; o schema V3 não oferece gate genérico",
            detalhe=f"{kind!r} não está em {sorted(TIPOS)}")
    campos = {k: v for k, v in spec.items() if k != "kind"}
    return TIPOS[kind](index=index, **campos)
