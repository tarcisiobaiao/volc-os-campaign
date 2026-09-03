"""O substituto do driver CDP, e a fronteira exata do que ele prova.

## O que este adaptador prova

Que o broker sabe: pegar o `ws.puppeteer` que a Local API devolveu, falar com
o endpoint de depuração por rede de verdade (socket, timeout, cancelamento),
receber URL final, cadeia de redirecionamentos, console, rede e bytes de
imagem, e transformar tudo isso num artefato com hash.

## O que ele NÃO prova

Que o VOLC consegue dirigir um Chromium real por CDP. `Page.navigate`,
`Page.captureScreenshot`, `Runtime.consoleAPICalled` e `Network.responseReceived`
não são falados aqui. O driver real é `broker.adspower.NavegadorNaoImplementado`,
que RECUSA — e essa recusa é o checkpoint externo, escrito em código para não
depender de alguém lembrar de contá-lo.

O `ws://` é traduzido para `http://` porque o duplê é um servidor HTTP comum: o
handshake de WebSocket não acrescentaria prova nenhuma sobre o broker, e
acrescentaria uma implementação de protocolo que ninguém revisou.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Optional
from urllib.parse import urlparse

from app.visual_proof import dominio as dom
from broker.adspower import CapturaBruta


class NavegadorViaDuple:
    """Implementa a porta `broker.adspower.Navegador` contra o duplê HTTP."""

    def __init__(self, *, chave: str):
        self._chave = chave

    def capturar(self, *, ws_endpoint: str, url: str, viewport: dom.Viewport,
                 timezone: Optional[str], timeout_s: float) -> CapturaBruta:
        partes = urlparse(ws_endpoint)
        if partes.scheme not in ("ws", "wss") or not partes.hostname or not partes.port:
            raise ValueError("endpoint de depuração em forma inesperada.")
        alvo = f"http://{partes.hostname}:{partes.port}/__fake__/navegar"
        corpo = json.dumps({
            "url": url,
            "viewport": viewport.para_dicionario(),
            "timezone": timezone,
        }).encode("utf-8")
        pedido = urllib.request.Request(alvo, data=corpo, method="POST", headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._chave}",
        })
        with urllib.request.urlopen(pedido, timeout=timeout_s) as resposta:  # noqa: S310
            dados = json.loads(resposta.read(8_000_000).decode("utf-8"))
        return CapturaBruta(
            url_final=str(dados.get("url_final") or url),
            redirecionamentos=tuple(dados.get("redirecionamentos") or ()),
            status_http=dados.get("status_http"),
            console=tuple(dados.get("console") or ()),
            rede=tuple(dados.get("rede") or ()),
            imagem=bytes.fromhex(str(dados.get("imagem_hex") or "")),
            mime=str(dados.get("mime") or "image/png"),
        )


__all__ = ["NavegadorViaDuple"]
