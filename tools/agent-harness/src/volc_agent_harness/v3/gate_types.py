"""Gates tipados: cada tipo tem schema próprio, nada de argv livre.

A refutação foi decisiva: uma allowlist de executáveis não é fronteira de
segurança, porque ``python`` está nela e um interpretador aceita código
arbitrário. ``python -c "import os;os.remove(x)"`` atravessou as duas guardas.

Argumento livre é o problema. Aqui o gate declara o TIPO, e o tipo constrói o
argv — o autor da missão nunca escreve a linha de comando inteira, e não existe
campo onde ele possa enfiar uma flag de carregamento de código.

Segunda rodada da mesma refutação: dois tipos selecionam conteúdo que o harness
não escreveu — ``npm_script`` roda o que estiver no ``package.json`` e
``tracked_script`` roda o que estiver no arquivo. Eles saíram do alcance direto
da missão: só existem por ID de catálogo versionado, com digest vinculado e
reconferido antes da execução. Ver :mod:`gate_catalog`.

⚠️ CONTENÇÃO — o que este módulo NÃO garante
--------------------------------------------
Análise de argumento não torna código Python ou Node confiável. Um teste que a
missão manda rodar executa com os privilégios do processo. A contenção real vem
de onde o gate roda, não do que ele parece ser: worktree descartável registrada,
cwd fixo nela, ambiente sanitizado, e diff depois da execução.

Enquanto não houver backend de sandbox provado, este módulo **não afirma**
proteção do filesystem externo. Ele reduz superfície, torna a intenção declarada
e fecha a janela entre compilar e executar — nada além disso. G1b segue aberta.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, Literal, Sequence

from .failures import FailureClass, HarnessFailure

#: Flags que o HARNESS acrescenta. Nenhuma delas vem da missão, e não existe
#: campo por onde a missão possa acrescentar outra.
_PYTEST_FIXAS = ("-p", "no:cacheprovider")

#: Seleção do pytest é expressão de teste, não linha de shell.
_K_VALIDA = re.compile(r"^[A-Za-z0-9_ ()\[\]\.\-]+$")

_PROIBIDOS_SEMPRE = (
    "-c", "--command", "-e", "--eval", "--exec", "-i", "--interactive",
    "-delete", "-ok", "--eval-file", "-p", "--plugin", "--import-mode",
    "--rootdir", "--confcutdir", "-P", "--pythonpath", "--assert",
)


def _sha256_arquivo(alvo: Path) -> str:
    return hashlib.sha256(alvo.read_bytes()).hexdigest() if alvo.is_file() else "<ausente>"


def _caminho_contido(valor: str, *, worktree: Path) -> str:
    """Relativo, sem travessia, contido na worktree."""

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
    #: Tipos que selecionam conteúdo indireto só existem por catálogo.
    exige_catalogo: ClassVar[bool] = False

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        raise NotImplementedError

    def evidence_inputs(self, *, worktree: Path) -> dict[str, str]:
        """Digest dos insumos materiais indiretos deste gate."""

        return {}

    def referenced_paths(self) -> list[str]:
        return []

    def as_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items()}
        d["kind"] = self.kind
        return d


@dataclass
class PytestGate(TypedGate):
    """pytest sem nenhuma porta de carregamento de código vinda da missão.

    A versão anterior aceitava uma lista ``flags`` com allowlist plana, onde
    ``-p`` convivia com os valores ``no:randomly`` e ``no:cacheprovider``. Uma
    allowlist que mistura flag e valor é uma allowlist que ninguém consegue ler:
    o campo sumiu, e o harness passou a construir as flags.
    """

    targets: list[str] = field(default_factory=list)
    traceback: Literal["short", "long", "no", "line"] = "short"
    maxfail: int | None = None
    quiet: bool = True
    k_expression: str | None = None
    kind: ClassVar[str] = "pytest"

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        interp = toolchain.get("python")
        if not interp or not Path(interp).is_file():
            raise HarnessFailure(
                FailureClass.INFRASTRUCTURE_ERROR,
                "interpretador do toolchain ausente", detalhe=str(interp))
        if not self.targets:
            raise HarnessFailure(FailureClass.SPEC_ERROR, "PytestGate sem targets")
        alvos = [_caminho_contido(t, worktree=worktree) for t in self.targets]
        argv = [interp, "-m", "pytest", *alvos, f"--tb={self.traceback}",
                *_PYTEST_FIXAS]
        if self.quiet:
            argv.append("-q")
        if self.maxfail is not None:
            if not 1 <= int(self.maxfail) <= 100:
                raise HarnessFailure(
                    FailureClass.SPEC_ERROR, "maxfail fora de 1..100",
                    detalhe=str(self.maxfail))
            argv.append(f"--maxfail={int(self.maxfail)}")
        if self.k_expression:
            if len(self.k_expression) > 200 or not _K_VALIDA.match(self.k_expression):
                raise HarnessFailure(
                    FailureClass.AUTHORIZATION_BLOCK,
                    "expressão -k fora do alfabeto permitido",
                    detalhe=self.k_expression[:120])
            argv += ["-k", self.k_expression]
        return argv

    def referenced_paths(self) -> list[str]:
        return list(self.targets)

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
        if not re.fullmatch(r"[A-Za-z0-9_*?.\-]+", self.pattern):
            raise HarnessFailure(
                FailureClass.SPEC_ERROR, "pattern de unittest inválido",
                detalhe=self.pattern)
        alvo = _caminho_contido(self.start_dir, worktree=worktree)
        return [interp, "-m", "unittest", "discover", "-s", alvo, "-p", self.pattern]

    def referenced_paths(self) -> list[str]:
        return [self.start_dir]


def _package_json(worktree: Path) -> dict[str, Any]:
    p = worktree / "package.json"
    if not p.is_file():
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "package.json ausente na worktree", detalhe=str(p))
    return json.loads(p.read_text(encoding="utf-8"))


@dataclass
class NpmScriptGate(TypedGate):
    """``npm run <script>``. Conteúdo indireto: só existe por catálogo."""

    script: str = ""
    kind: ClassVar[str] = "npm_script"
    exige_catalogo: ClassVar[bool] = True

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
        saida: dict[str, str] = {}
        for nome in ("package.json", "package-lock.json", "pnpm-lock.yaml",
                     "yarn.lock", "bun.lockb"):
            alvo = worktree / nome
            if alvo.is_file():
                saida[nome] = _sha256_arquivo(alvo)
        # O corpo do script entra separado: a mensagem fica legível quando o
        # `package.json` mudou justamente na linha que o gate executa.
        try:
            corpo = _package_json(worktree).get("scripts", {}).get(self.script, "")
        except HarnessFailure:
            corpo = "<package.json ausente>"
        saida[f"script:{self.script}"] = hashlib.sha256(
            str(corpo).encode("utf-8")).hexdigest()
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

    def referenced_paths(self) -> list[str]:
        return list(self.project_targets)


@dataclass
class BuildGate(TypedGate):
    """Build do projeto. Conteúdo indireto pelo mesmo motivo do npm_script."""

    script: str = "build"
    kind: ClassVar[str] = "build"
    exige_catalogo: ClassVar[bool] = True

    def _delegado(self) -> NpmScriptGate:
        return NpmScriptGate(index=self.index, script=self.script)

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
        return self._delegado().build(worktree=worktree, toolchain=toolchain)

    def evidence_inputs(self, *, worktree: Path) -> dict[str, str]:
        return self._delegado().evidence_inputs(worktree=worktree)


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
    """Script versionado. Conteúdo indireto: só existe por catálogo."""

    script_path: str = ""
    args: list[str] = field(default_factory=list)
    kind: ClassVar[str] = "tracked_script"
    exige_catalogo: ClassVar[bool] = True

    def build(self, *, worktree: Path, toolchain: dict[str, str]) -> list[str]:
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
        if not interp:
            raise HarnessFailure(
                FailureClass.INFRASTRUCTURE_ERROR,
                "interpretador do toolchain ausente para tracked_script")
        return [interp, rel, *self.args]

    def evidence_inputs(self, *, worktree: Path) -> dict[str, str]:
        return {self.script_path: _sha256_arquivo(worktree / self.script_path)}

    def referenced_paths(self) -> list[str]:
        # Os ARGUMENTOS também são caminhos. Devolver só o script deixava passar
        # a lição da lane B3 pela porta dos fundos: um argumento apontando para
        # arquivo inexistente e não declarado em produced_paths não era recusado,
        # e o gate ainda era considerado executável antes do writer.
        return [self.script_path, *(a for a in self.args if not a.startswith("-"))]


TIPOS: dict[str, type[TypedGate]] = {
    "pytest": PytestGate,
    "unittest": UnittestGate,
    "npm_script": NpmScriptGate,
    "typescript": TypeScriptGate,
    "build": BuildGate,
    "git_diff_check": GitDiffCheckGate,
    "tracked_script": TrackedScriptGate,
}


def from_spec(
    index: int, spec: dict[str, Any], *, from_catalog: bool = False
) -> TypedGate:
    """Constrói o gate a partir do schema. Não existe tipo GENERIC.

    ``from_catalog`` é a única porta para os tipos de conteúdo indireto. Uma
    missão que declarar ``npm_script`` ou ``tracked_script`` diretamente recebe
    ``AUTHORIZATION_BLOCK``: ela não escolhe o que roda, escolhe o ID de um gate
    que alguém revisou.
    """

    kind = spec.get("kind")
    if not isinstance(kind, str) or kind not in TIPOS:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "tipo de gate desconhecido; o schema V3 não oferece gate genérico",
            detalhe=f"{kind!r} não está em {sorted(TIPOS)}")
    classe = TIPOS[kind]
    if classe.exige_catalogo and not from_catalog:
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "gate de conteúdo indireto exige catálogo auditado",
            detalhe=f"{kind} só pode ser referenciado por gate_id",
            reproducao=f'use {{"kind": "catalog", "gate_id": "..."}}')
    campos = {k: v for k, v in spec.items() if k != "kind"}
    validos = set(getattr(classe, "__dataclass_fields__", {}))
    desconhecidos = sorted(set(campos) - validos)
    if desconhecidos:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "campo desconhecido em gate tipado",
            detalhe=f"{kind}: {', '.join(desconhecidos)}")
    return classe(index=index, **campos)
