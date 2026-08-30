"""Fronteira de isolamento para processos Claude Code do harness.

Este modulo deliberadamente nao executa o CLI. Ele produz um ambiente efemero
e fail-closed que o adapter pode entregar ao subprocesso sem consultar ou
copiar a configuracao pessoal do operador.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .security import sanitized_environment


AUTH_SOURCE_NAME = "VOLC_CLAUDE_CODE_OAUTH_TOKEN"
CHILD_AUTH_NAME = "CLAUDE_CODE_OAUTH_TOKEN"


class ClaudeIsolationNoGo(RuntimeError):
    """O Claude nao pode iniciar sem isolamento ou credencial explicita."""


@dataclass(frozen=True, repr=False)
class ExplicitClaudeAuthentication:
    """Credencial fornecida conscientemente ao harness, nunca descoberta.

    O nome da variavel de entrada e diferente do nome reconhecido pelo Claude
    para impedir que uma sessao pessoal seja herdada por acidente.
    """

    oauth_token: str

    def __post_init__(self) -> None:
        if not self.oauth_token.strip():
            raise ClaudeIsolationNoGo("credencial Claude explicita esta vazia")
        forbidden = ("\n", "\r", "\0")
        if any(character in self.oauth_token for character in forbidden):
            raise ClaudeIsolationNoGo(
                "credencial Claude explicita tem formato invalido"
            )

    def __repr__(self) -> str:
        return "ExplicitClaudeAuthentication(oauth_token=[REDACTED])"

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, str],
        *,
        variable: str = AUTH_SOURCE_NAME,
    ) -> "ExplicitClaudeAuthentication":
        """Carrega somente a entrada nomeada e explicitamente fornecida.

        Nao ha fallback para ``CLAUDE_CODE_OAUTH_TOKEN``, ``ANTHROPIC_API_KEY``
        ou arquivos sob HOME.
        """

        token = source.get(variable)
        if token is None:
            raise ClaudeIsolationNoGo(
                f"NO-GO: autenticacao Claude explicita ausente ({variable})"
            )
        return cls(token)


class RedactedEnvironment(dict[str, str]):
    """Environment mapping cujo repr nunca imprime valores."""

    def __repr__(self) -> str:
        return f"RedactedEnvironment(keys={sorted(self)})"

    __str__ = __repr__


@dataclass(frozen=True, repr=False)
class IsolatedClaudeRuntime:
    home: Path
    config_dir: Path
    environment: RedactedEnvironment

    def __repr__(self) -> str:
        return (
            "IsolatedClaudeRuntime("
            f"home={self.home!s}, config_dir={self.config_dir!s}, "
            "environment=[REDACTED])"
        )


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    path.chmod(0o700)


def _write_empty_settings(config_dir: Path) -> None:
    settings = config_dir / "settings.json"
    settings.write_text("{}\n", encoding="utf-8")
    settings.chmod(0o600)


@contextmanager
def isolated_claude_runtime(
    auth: ExplicitClaudeAuthentication | None,
    *,
    base_environment: Mapping[str, str] | None = None,
    temporary_parent: Path | None = None,
) -> Iterator[IsolatedClaudeRuntime]:
    """Entrega HOME/config efemeros e autenticacao explicitamente injetada.

    Ausencia de ``auth`` e sempre NO-GO. Variaveis Claude/Anthropic pessoais,
    inclusive as que porventura estejam no ambiente de origem, sao removidas
    antes da injecao da unica credencial autorizada.
    """

    if auth is None:
        raise ClaudeIsolationNoGo("NO-GO: autenticacao Claude explicita ausente")

    source = os.environ if base_environment is None else base_environment
    environment = sanitized_environment(source)
    for name in tuple(environment):
        if (
            name.startswith("CLAUDE_")
            or name.startswith("ANTHROPIC_")
            or name == "CODEX_HOME"
            or name == "HOME"
        ):
            environment.pop(name, None)

    parent = temporary_parent.resolve() if temporary_parent is not None else None
    if parent is not None:
        parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="volc-claude-", dir=parent) as temporary:
        runtime_root = Path(temporary).resolve()
        home = runtime_root / "home"
        config_dir = runtime_root / "config"
        _private_directory(home)
        _private_directory(config_dir)
        _write_empty_settings(config_dir)

        isolated = RedactedEnvironment(environment)
        isolated["HOME"] = str(home)
        isolated["CLAUDE_CONFIG_DIR"] = str(config_dir)
        isolated[CHILD_AUTH_NAME] = auth.oauth_token

        yield IsolatedClaudeRuntime(
            home=home,
            config_dir=config_dir,
            environment=isolated,
        )
