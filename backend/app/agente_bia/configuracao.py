"""Configuração da Bia, validada antes de qualquer uso.

## O que esta leitura recusa

- flag diferente de "1" → a superfície não existe (404);
- base do Hermes em http fora do loopback → recusada: a chave do profile
  viajaria em texto claro. Fora do loopback, só https;
- base com caminho, query, fragmento ou credencial embutida → recusada;
- origem CORS com curinga, caminho ou sem esquema → recusada;
- limites fora da faixa → presos à faixa, nunca acima do teto absoluto.

Sem base ou sem chave do Hermes, a configuração continua válida e o motor fica
`None`: conversa e histórico funcionam, envio responde 503. O Hermes fora do
ar não pode derrubar a leitura do que já foi conversado.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlsplit

from app.agente_bia import dominio as dom
from app.config import Settings


class ConfiguracaoInvalida(ValueError):
    pass


@dataclass(frozen=True)
class ConfiguracaoDaBia:
    ligada: bool
    hermes_base_url: Optional[str]
    hermes_chave: Optional[str]
    origens: Tuple[str, ...]
    timeout_s: float
    limite_por_minuto: int
    max_caracteres: int

    @property
    def motor_configurado(self) -> bool:
        return bool(self.hermes_base_url and self.hermes_chave)


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validar_base_hermes(url: str) -> str:
    partes = urlsplit(url.strip())
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise ConfiguracaoInvalida("BIA_HERMES_BASE_URL precisa de esquema http(s) e host")
    if partes.username or partes.password:
        raise ConfiguracaoInvalida("BIA_HERMES_BASE_URL não pode carregar credencial")
    if partes.path not in ("", "/") or partes.query or partes.fragment:
        raise ConfiguracaoInvalida("BIA_HERMES_BASE_URL é só origem (sem caminho)")
    if partes.scheme == "http" and not _loopback(partes.hostname):
        raise ConfiguracaoInvalida(
            "BIA_HERMES_BASE_URL em http só no loopback (túnel); fora dele, https")
    return f"{partes.scheme}://{partes.netloc}"


def validar_origem(origem: str) -> str:
    o = origem.strip()
    if "*" in o:
        raise ConfiguracaoInvalida("BIA_ALLOWED_ORIGINS não aceita curinga")
    partes = urlsplit(o)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise ConfiguracaoInvalida(f"origem inválida: {o!r}")
    if partes.path not in ("",) or partes.query or partes.fragment or partes.username:
        raise ConfiguracaoInvalida(f"origem é esquema+host+porta, sem caminho: {o!r}")
    return f"{partes.scheme}://{partes.netloc}".lower()


def ler(settings: Settings) -> ConfiguracaoDaBia:
    ligada = (settings.bia_enabled or "").strip() == "1"
    base = (settings.bia_hermes_base_url or "").strip() or None
    chave = (settings.bia_hermes_api_key or "").strip() or None
    origens = tuple(validar_origem(o) for o in (settings.bia_allowed_origins or "").split(",")
                    if o.strip())
    return ConfiguracaoDaBia(
        ligada=ligada,
        hermes_base_url=validar_base_hermes(base) if base else None,
        hermes_chave=chave,
        origens=origens,
        timeout_s=max(5.0, min(float(settings.bia_hermes_timeout_s or 120.0), 300.0)),
        limite_por_minuto=max(1, min(int(settings.bia_limite_por_minuto or 6), 30)),
        max_caracteres=max(1, min(int(settings.bia_max_caracteres or 4000),
                                  dom.MAX_ENTRADA_ABSOLUTO)),
    )
