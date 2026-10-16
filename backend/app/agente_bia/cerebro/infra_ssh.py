"""Cliente do executor do cérebro: UM `ssh` por pedido, comando forçado do lado de lá.

O cliente não escolhe comando nenhum: o `authorized_keys` do usuário
`volc-cerebro-web` força `/usr/local/sbin/volc-cerebro-web`. Aqui só se manda
o JSON do pedido pelo stdin e se lê o JSON da resposta. Host desconhecido,
chave errada ou VPS fora → `CerebroIndisponivel`, nunca detalhe interno.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

_DESTINO = re.compile(r"^[a-z_][a-z0-9_-]{0,31}@[A-Za-z0-9.-]{1,253}$")
TETO_S = 30.0


class CerebroIndisponivel(Exception):
    def __init__(self, codigo: str = "cerebro_indisponivel"):
        super().__init__(codigo)
        self.codigo = codigo


class CerebroRecusou(Exception):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(codigo)
        self.codigo, self.mensagem = codigo, mensagem


class ExecutorCerebroSSH:
    def __init__(self, destino: Optional[str], chave: Optional[str], *, programa: str = "ssh") -> None:
        self.destino = destino if destino and _DESTINO.match(destino) else None
        self.chave = chave if chave and os.path.isfile(chave) else None
        self._programa = programa

    @property
    def configurado(self) -> bool:
        return bool(self.destino and self.chave)

    async def _pedir(self, pedido: Dict[str, Any]) -> Dict[str, Any]:
        if not self.configurado:
            raise CerebroIndisponivel("cerebro_nao_configurado")
        args = [self._programa, "-i", self.chave, "-T",
                "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
                "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=10", self.destino]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            saida, _erro = await asyncio.wait_for(
                proc.communicate(json.dumps(pedido, ensure_ascii=False).encode("utf-8")), TETO_S)
        except (OSError, asyncio.TimeoutError) as exc:
            log.warning("cerebro executor inalcançável: %s", type(exc).__name__)
            raise CerebroIndisponivel() from exc
        try:
            resposta = json.loads(saida.decode("utf-8").strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            log.warning("cerebro executor sem resposta JSON (rc=%s)", proc.returncode)
            raise CerebroIndisponivel() from exc
        if not isinstance(resposta, dict):
            raise CerebroIndisponivel()
        if not resposta.get("ok"):
            raise CerebroRecusou(str(resposta.get("codigo") or "recusado"),
                                 str(resposta.get("mensagem") or "O executor recusou o pedido."))
        return resposta

    async def status(self) -> Dict[str, Any]:
        return await self._pedir({"op": "status"})

    async def gravar(self, **campos: Any) -> Dict[str, Any]:
        return await self._pedir({"op": "gravar", **campos})
