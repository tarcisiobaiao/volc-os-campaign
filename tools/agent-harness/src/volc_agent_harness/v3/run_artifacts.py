"""Fronteira única dos artefatos de uma execução.

O ratchet de boot fechava por partes, e a parte que faltava era sempre a mesma:
alguma escrita acontecia FORA do bloco que garante ``failure.json``. Primeiro
foi a criação da worktree e o claim no registry; depois, apontado pelo Sol, o
próprio ``metadata.json`` — escrito logo após ``run_dir.mkdir`` e antes do
``try``, nos dois modos. Uma falha de disco ali deixava o operador com um
diretório vazio e uma linha no terminal.

Corrigir ponto a ponto não resolve a classe do defeito: enquanto a fronteira for
uma convenção sobre onde colocar o ``try``, ela volta a vazar no próximo
artefato que alguém acrescentar. Aqui a fronteira é um objeto: quem cria o
``run_dir`` já entra protegido, e toda escrita passa por ``escrever``.

Regras que este módulo garante:

* falha ANTES de existir ``run_id``/``run_dir`` — nada é inventado, o chamador
  reporta tipado e pronto;
* falha DEPOIS — ``failure.json`` obrigatório, atômico e sanitizado, com classe,
  fase, destino e política de retry;
* nenhum caminho de artefato é anunciado sem existir no disco.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .failures import FailureClass, HarnessFailure, classify_exception


def _sanitizar(valor: Any) -> Any:
    from ..security import redact

    if isinstance(valor, str):
        return redact(valor)
    if isinstance(valor, dict):
        return {k: _sanitizar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sanitizar(v) for v in valor]
    return valor


@dataclass
class RunArtifacts:
    """Dono do ``run_dir``. Nenhuma escrita de execução acontece fora dele."""

    run_dir: Path
    fase: str = "boot"
    escritos: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def marcar(self, fase: str) -> None:
        """Nomeia a fase corrente; é ela que aparece no ``failure.json``."""

        self.fase = fase

    def escrever(self, nome: str, conteudo: Any) -> Path:
        """Escrita ATÔMICA: um artefato meio escrito engana pior que um ausente."""

        destino = self.run_dir / nome
        texto = (conteudo if isinstance(conteudo, str)
                 else json.dumps(conteudo, ensure_ascii=False, indent=2))
        fd, temporario = tempfile.mkstemp(dir=str(self.run_dir), suffix=".parcial")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
                arquivo.write(texto)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            os.replace(temporario, destino)
        except BaseException:
            Path(temporario).unlink(missing_ok=True)
            raise
        if nome not in self.escritos:
            self.escritos.append(nome)
        return destino

    def registrar_falha(self, exc: BaseException) -> dict[str, Any]:
        """``failure.json`` tipado, sanitizado e com a fase onde quebrou."""

        if isinstance(exc, HarnessFailure):
            registro = exc.as_dict()
        else:
            registro = HarnessFailure(
                classify_exception(exc), f"{type(exc).__name__}: {exc}"[:300]
            ).as_dict()
        registro = {k: _sanitizar(v) for k, v in registro.items()}
        registro["fase"] = self.fase
        registro["artefatos_escritos"] = list(self.escritos)
        try:
            self.escrever("failure.json", registro)
        except BaseException:
            # Se nem o artefato de falha conseguimos gravar, o chamador ainda
            # precisa da classe tipada. Não escondemos a falha original.
            return registro
        return registro

    @property
    def failure_path(self) -> Path:
        return self.run_dir / "failure.json"


class fronteira_de_erro:                       # noqa: N801 - lê-se como bloco
    """``with`` que garante ``failure.json`` para tudo que escapar.

    A exceção é reerguida com o caminho do artefato anexado, para que o CLI
    possa CONFERIR que ele existe antes de citá-lo — nunca supor.
    """

    def __init__(self, artefatos: RunArtifacts, fase: str = "boot"):
        self.artefatos = artefatos
        self.fase = fase

    def __enter__(self) -> RunArtifacts:
        self.artefatos.marcar(self.fase)
        return self.artefatos

    def __exit__(self, tipo, exc, _tb) -> bool:
        if exc is None:
            return False
        self.artefatos.registrar_falha(exc)
        alvo = self.artefatos.failure_path
        try:
            exc.run_dir = str(self.artefatos.run_dir)        # type: ignore[attr-defined]
            exc.failure_artifact = str(alvo) if alvo.is_file() else ""
        except AttributeError:                               # exceção com __slots__
            pass
        return False
