"""Trava de somente-leitura — garantia estrutural, não promessa.

Enquanto estamos validando localmente, nenhuma linha do forge pode alterar
uma conta real. Isso não é convenção nem revisão de código: qualquer tentativa
de mutação real levanta exceção antes de a requisição sair da máquina.

A trava é fechada por padrão. Destravar exige:
  1. Chamar `destravar()` explicitamente no código, com justificativa; e
  2. A variável de ambiente FORGE_PERMITIR_ESCRITA=1 presente.

Dois fatores de propósito: um `destravar()` esquecido num script não basta,
e a variável de ambiente sozinha também não. Só a intenção deliberada,
declarada nos dois lugares, abre a porta.

`validate_only` NÃO é considerado escrita — a API valida e descarta, nada é
criado. É justamente o que queremos poder rodar à vontade.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

_ENV = "FORGE_PERMITIR_ESCRITA"

_destravado_no_codigo = False
_motivo = ""


class EscritaBloqueada(RuntimeError):
    """Tentativa de mutação real com a trava fechada."""


def escrita_permitida() -> bool:
    return _destravado_no_codigo and os.environ.get(_ENV) == "1"


def exigir_leitura_apenas(operacao: str) -> None:
    """Chamado por qualquer caminho que fosse alterar uma conta real."""
    if not escrita_permitida():
        raise EscritaBloqueada(
            f"'{operacao}' bloqueada: o forge está em modo somente-leitura.\n"
            f"Para liberar seria preciso destravar() no código E {_ENV}=1 "
            f"no ambiente. Nenhum dos dois está ativo — nada foi enviado."
        )


@contextmanager
def destravar(motivo: str):
    """Abre a trava dentro de um bloco, e só se o ambiente também permitir.

    Uso deliberado:
        with destravar("subir campanha canário na Crédito Up"):
            ...
    """
    global _destravado_no_codigo, _motivo
    if not motivo or len(motivo.strip()) < 10:
        raise ValueError("destravar() exige um motivo descritivo")
    anterior, anterior_motivo = _destravado_no_codigo, _motivo
    _destravado_no_codigo, _motivo = True, motivo.strip()
    try:
        if os.environ.get(_ENV) != "1":
            raise EscritaBloqueada(
                f"destravar('{motivo}') pedido, mas {_ENV} não está definido "
                f"como '1'. A trava permanece fechada."
            )
        yield
    finally:
        _destravado_no_codigo, _motivo = anterior, anterior_motivo


def estado() -> dict:
    return {
        "escrita_permitida": escrita_permitida(),
        "destravado_no_codigo": _destravado_no_codigo,
        "env_presente": os.environ.get(_ENV) == "1",
        "motivo": _motivo,
    }
