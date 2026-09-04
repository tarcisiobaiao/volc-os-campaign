"""Credencial Meta provisoria, restrita ao ambiente local do operador.

O token nunca vai para Supabase, ``.env``, arquivo do repositorio ou storage do
navegador. No macOS ele fica como senha generica no Keychain da sessao local.
Este modulo usa a Security.framework diretamente: assim o segredo nao aparece
nem nos argumentos de um subprocesso ``security``.
"""
from __future__ import annotations

import ctypes
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


SERVICO_KEYCHAIN = "br.com.agenciavolc.volc-os.meta-system-user"
ERR_ITEM_NAO_ENCONTRADO = -25300
ERR_ITEM_DUPLICADO = -25299


class ConfiguracaoLocalIndisponivel(RuntimeError):
    """A configuracao local nao pode ser usada com seguranca neste host."""


class SegredoLocalNaoEncontrado(LookupError):
    """Nao ha token salvo para este operador."""


class ArmazenamentoDeSegredo(Protocol):
    def salvar(self, conta: str, valor: str) -> None: ...
    def ler(self, conta: str) -> str: ...
    def remover(self, conta: str) -> bool: ...


class ChaveiroMacOS:
    """Pequeno adaptador para Generic Password do Keychain.

    Nada e enviado a processo filho. A memoria devolvida pelo Keychain e
    liberada imediatamente depois da copia, e o item e liberado via CFRelease.
    """

    def __init__(self, servico: str = SERVICO_KEYCHAIN) -> None:
        if sys.platform != "darwin":
            raise ConfiguracaoLocalIndisponivel(
                "configuracao provisoria exige o Chaveiro do macOS")
        self._servico = servico.encode("utf-8")
        try:
            self._security = ctypes.CDLL(
                "/System/Library/Frameworks/Security.framework/Security")
            self._core = ctypes.CDLL(
                "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        except OSError as exc:
            raise ConfiguracaoLocalIndisponivel(
                "Security.framework indisponivel neste host") from exc
        self._configurar_assinaturas()

    def _configurar_assinaturas(self) -> None:
        u32 = ctypes.c_uint32
        void = ctypes.c_void_p
        char = ctypes.c_char_p
        self._security.SecKeychainFindGenericPassword.argtypes = [
            void, u32, char, u32, char,
            ctypes.POINTER(u32), ctypes.POINTER(void), ctypes.POINTER(void),
        ]
        self._security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
        self._security.SecKeychainAddGenericPassword.argtypes = [
            void, u32, char, u32, char, u32, void, ctypes.POINTER(void),
        ]
        self._security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
        self._security.SecKeychainItemModifyAttributesAndData.argtypes = [
            void, void, u32, void,
        ]
        self._security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
        self._security.SecKeychainItemDelete.argtypes = [void]
        self._security.SecKeychainItemDelete.restype = ctypes.c_int32
        self._security.SecKeychainItemFreeContent.argtypes = [void, void]
        self._security.SecKeychainItemFreeContent.restype = ctypes.c_int32
        self._core.CFRelease.argtypes = [void]
        self._core.CFRelease.restype = None

    def _encontrar(self, conta: bytes, *, com_senha: bool) -> tuple[int, bytes | None, ctypes.c_void_p]:
        tamanho = ctypes.c_uint32(0)
        dados = ctypes.c_void_p()
        item = ctypes.c_void_p()
        status = self._security.SecKeychainFindGenericPassword(
            None,
            len(self._servico),
            self._servico,
            len(conta),
            conta,
            ctypes.byref(tamanho) if com_senha else None,
            ctypes.byref(dados) if com_senha else None,
            ctypes.byref(item),
        )
        senha: bytes | None = None
        if status == 0 and com_senha and dados.value:
            senha = ctypes.string_at(dados, tamanho.value)
            self._security.SecKeychainItemFreeContent(None, dados)
        return status, senha, item

    @staticmethod
    def _falhou(operacao: str, status: int) -> None:
        raise ConfiguracaoLocalIndisponivel(
            f"Chaveiro recusou {operacao} (OSStatus {status})")

    def salvar(self, conta: str, valor: str) -> None:
        conta_b = conta.encode("utf-8")
        valor_b = valor.encode("utf-8")
        status, _, item = self._encontrar(conta_b, com_senha=False)
        if status == 0:
            try:
                buffer = ctypes.create_string_buffer(valor_b)
                codigo = self._security.SecKeychainItemModifyAttributesAndData(
                    item, None, len(valor_b), ctypes.cast(buffer, ctypes.c_void_p))
            finally:
                self._core.CFRelease(item)
            if codigo != 0:
                self._falhou("atualizar a credencial Meta", codigo)
            return
        if status != ERR_ITEM_NAO_ENCONTRADO:
            self._falhou("procurar a credencial Meta", status)
        item_novo = ctypes.c_void_p()
        buffer = ctypes.create_string_buffer(valor_b)
        codigo = self._security.SecKeychainAddGenericPassword(
            None,
            len(self._servico),
            self._servico,
            len(conta_b),
            conta_b,
            len(valor_b),
            ctypes.cast(buffer, ctypes.c_void_p),
            ctypes.byref(item_novo),
        )
        if item_novo.value:
            self._core.CFRelease(item_novo)
        if codigo == ERR_ITEM_DUPLICADO:
            # Uma corrida rara entre duas abas: a segunda tenta novamente pelo
            # caminho de atualizacao, sem imprimir ou devolver o segredo.
            return self.salvar(conta, valor)
        if codigo != 0:
            self._falhou("salvar a credencial Meta", codigo)

    def ler(self, conta: str) -> str:
        status, senha, item = self._encontrar(conta.encode("utf-8"), com_senha=True)
        if status == ERR_ITEM_NAO_ENCONTRADO:
            raise SegredoLocalNaoEncontrado()
        if status != 0 or senha is None:
            self._falhou("ler a credencial Meta", status)
        try:
            return senha.decode("utf-8")
        finally:
            if item.value:
                self._core.CFRelease(item)

    def remover(self, conta: str) -> bool:
        status, _, item = self._encontrar(conta.encode("utf-8"), com_senha=False)
        if status == ERR_ITEM_NAO_ENCONTRADO:
            return False
        if status != 0:
            self._falhou("procurar a credencial Meta", status)
        try:
            codigo = self._security.SecKeychainItemDelete(item)
        finally:
            self._core.CFRelease(item)
        if codigo != 0:
            self._falhou("remover a credencial Meta", codigo)
        return True


@dataclass(frozen=True)
class CredencialLocal:
    token: str
    salvo_em: str

    def serializar(self) -> str:
        return json.dumps({"token": self.token, "salvo_em": self.salvo_em})

    @classmethod
    def agora(cls, token: str) -> "CredencialLocal":
        return cls(token=token, salvo_em=datetime.now(timezone.utc).isoformat())

    @classmethod
    def de(cls, valor: str) -> "CredencialLocal":
        try:
            corpo = json.loads(valor)
            token = str(corpo["token"])
            salvo_em = str(corpo["salvo_em"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ConfiguracaoLocalIndisponivel(
                "item Meta do Chaveiro tem formato invalido") from exc
        if not token:
            raise ConfiguracaoLocalIndisponivel("item Meta do Chaveiro esta vazio")
        return cls(token=token, salvo_em=salvo_em)


def nome_da_conta_local(sub: str) -> str:
    """Separa a credencial por usuario autenticado sem expor email."""
    return f"supabase-user:{sub}"
