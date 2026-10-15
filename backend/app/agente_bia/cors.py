"""CORS exato para `/api/agent/*`, e só para ele.

O CORS global do backend vem de `PAUTADOR_ALLOWED_ORIGINS`, cujo padrão é `*`.
Mudar o global mexeria em todas as outras rotas; por isso a Bia tem o seu,
montado POR FORA do global (último `add_middleware` = mais externo):

- preflight de origem fora da lista → 403, sem `Access-Control-Allow-Origin`;
- requisição com `Origin` fora da lista → 403 antes de chegar à rota;
- origem da lista → ACAO com A MESMA origem (nunca `*`), `Vary: Origin`;
- sem `Origin` (servidor, curl) → segue, e qualquer ACAO do global é retirado.

CORS não é autenticação (o Bearer continua obrigatório); é a segunda cerca
contra um site de terceiros usando o navegador do operador.
"""
from __future__ import annotations

import json
from typing import Callable, Iterable, Optional, Tuple

from app.agente_bia import configuracao

PREFIXO = "/api/agent"
METODOS = "GET, POST"
CABECALHOS = "Authorization, Content-Type"


def _origens() -> Tuple[str, ...]:
    from app.config import get_settings
    try:
        return configuracao.ler(get_settings()).origens
    except configuracao.ConfiguracaoInvalida:
        return ()


class CorsExatoDaBia:
    def __init__(self, app, origens: Optional[Callable[[], Iterable[str]]] = None) -> None:
        self.app = app
        # Resolvida a CADA requisição pelo nome do módulo: a configuração pode
        # mudar (e os testes trocam a fonte) sem reconstruir a pilha.
        self._origens = origens

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not str(scope.get("path", "")).startswith(PREFIXO):
            await self.app(scope, receive, send)
            return

        cabecalhos = {k.decode("latin-1").lower(): v.decode("latin-1")
                      for k, v in scope.get("headers") or []}
        origem = cabecalhos.get("origin")
        permitidas = {o.lower() for o in (self._origens or _origens)()}
        permitida = origem is not None and origem.lower() in permitidas

        if scope.get("method") == "OPTIONS" and "access-control-request-method" in cabecalhos:
            if not permitida:
                await _responder(send, 403, [], {"detail": "origem não permitida"})
                return
            await _responder(send, 204, [
                (b"access-control-allow-origin", origem.encode("latin-1")),
                (b"access-control-allow-methods", METODOS.encode()),
                (b"access-control-allow-headers", CABECALHOS.encode()),
                (b"access-control-max-age", b"600"),
                (b"vary", b"Origin"),
            ], None)
            return

        if origem is not None and not permitida:
            await _responder(send, 403, [], {"detail": "origem não permitida"})
            return

        async def enviar(msg):
            if msg["type"] == "http.response.start":
                hs = [(k, v) for k, v in msg.get("headers", [])
                      if k.lower() not in (b"access-control-allow-origin",
                                           b"access-control-allow-credentials",
                                           b"access-control-expose-headers")]
                if permitida:
                    hs.append((b"access-control-allow-origin", origem.encode("latin-1")))
                    hs.append((b"vary", b"Origin"))
                msg = {**msg, "headers": hs}
            await send(msg)

        await self.app(scope, receive, enviar)


async def _responder(send, status: int, headers, corpo) -> None:
    dados = b"" if corpo is None else json.dumps(corpo).encode()
    hs = list(headers)
    if corpo is not None:
        hs.append((b"content-type", b"application/json"))
    hs.append((b"content-length", str(len(dados)).encode()))
    await send({"type": "http.response.start", "status": status, "headers": hs})
    await send({"type": "http.response.body", "body": dados})
