"""A trava PRÓPRIA do envio real de conversões: por chamada, nunca global.

## Por que não a trava do forge

`volc_ads/gads/modo.destravar` abre uma porta do PROCESSO inteiro. Enquanto
outra requisição está dentro dela (o `/subir` de campanha, por exemplo), um
envio de conversões que só conferisse `modo.exigir_leitura_apenas` sairia de
verdade junto, sem ninguém ter pedido. (Revisão local W14 no main integrado,
defeito 1, reproduzido com duas threads.)

## Como esta funciona

Dois fatores, e nenhum deles é estado global compartilhado com o forge:

  1. `VOLC_CONVERSOES_PERMITIR_ENVIO=1` no ambiente, conferido na EMISSÃO e de
     novo no USO (a variável do forge não serve);
  2. uma `ChaveDeEnvioReal` emitida no código, com motivo, para a impressão
     EXATA de um envelope, e consumida uma única vez. Quem não tem a chave na
     mão não envia, esteja a trava do forge aberta ou não.

A chave não sabe enviar nada; ela só é exigida por `enviar_de_verdade`, que a
consome antes de qualquer outra coisa.
"""
from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timezone

ENV = "VOLC_CONVERSOES_PERMITIR_ENVIO"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class EnvioRealBloqueado(RuntimeError):
    """Envio real de conversões sem a chave própria válida para este envelope."""


class ChaveDeEnvioReal:
    """Licença de UM envio real, de UM envelope. Não se copia, não se reusa."""

    __slots__ = ("_impressao", "_motivo", "_emitida_em", "_usada", "_trinco")

    def __init__(self, *, _impressao: str, _motivo: str, _token: object) -> None:
        if _token is not _EMISSOR:
            raise EnvioRealBloqueado("a chave só nasce por `emitir_chave`")
        self._impressao = _impressao
        self._motivo = _motivo
        self._emitida_em = datetime.now(timezone.utc)
        self._usada = False
        self._trinco = threading.Lock()

    @property
    def impressao(self) -> str:
        return self._impressao

    @property
    def motivo(self) -> str:
        return self._motivo

    def __copy__(self):  # noqa: D105
        raise EnvioRealBloqueado("chave de envio real não se copia")

    def __deepcopy__(self, memo):  # noqa: D105
        raise EnvioRealBloqueado("chave de envio real não se copia")

    def __reduce__(self):  # noqa: D105
        raise EnvioRealBloqueado("chave de envio real não se serializa")

    def consumir(self, impressao: str) -> None:
        """Confere e gasta a chave, atômico entre threads. Falha fechado."""
        if os.environ.get(ENV) != "1":
            raise EnvioRealBloqueado(
                f"{ENV} não está '1' no ambiente: o envio real de conversões está fechado")
        with self._trinco:
            if self._usada:
                raise EnvioRealBloqueado("esta chave de envio real já foi usada")
            if impressao != self._impressao:
                raise EnvioRealBloqueado(
                    f"a chave é do envelope {self._impressao[:12]}… e o envio é de "
                    f"{str(impressao)[:12]}…; chave não se transfere")
            self._usada = True


_EMISSOR = object()


def emitir_chave(*, impressao: str, motivo: str) -> ChaveDeEnvioReal:
    """A decisão deliberada, no código, de mandar ESTE envelope uma vez."""
    if os.environ.get(ENV) != "1":
        raise EnvioRealBloqueado(
            f"emitir_chave pedido, mas {ENV} não está '1': nenhuma chave foi emitida")
    if not _HEX64.match(str(impressao or "")):
        raise EnvioRealBloqueado("a chave exige a impressão exata do envelope (64 hex)")
    if not motivo or len(motivo.strip()) < 10:
        raise EnvioRealBloqueado("emitir_chave exige um motivo descritivo")
    return ChaveDeEnvioReal(_impressao=impressao, _motivo=motivo.strip(), _token=_EMISSOR)
