"""Servidor HTTP que imita a Local API do AdsPower — fielmente e só até onde a
documentação oficial permite afirmar.

## O que é fiel, e por qual fonte (consultada em 02/09/2026)

- `GET /api/v1/browser/start`, com `user_id`, `headless`, `ip_tab`, `open_tabs`
  e o envelope `{"code":0,"data":{"ws":{"selenium","puppeteer"},"debug_port",
  "webdriver"},"msg":"success"}` — https://localapi-doc-en.adspower.com/docs/FFMFMf
- `GET /api/v1/browser/active` com `data.status` em `Active`/`Inactive` —
  https://localapi-doc-en.adspower.com/docs/YjFggL
- `Authorization: Bearer …` como autenticação —
  https://localapi-doc-en.adspower.com/docs/Rdw7Iu
- falha como `{"code":-1,"data":{},"msg":"failed"}` — mesma fonte de start

## O que é INFERIDO, e está marcado como tal

- **`/api/v1/browser/stop`.** A visão geral lista "Close Browser" e "Close
  Browser V2"; o path não apareceu na documentação aberta. O duplê aceita
  `/stop` e `/close` para que a troca não quebre o E2E.
- **A resposta a um Bearer errado.** A documentação não publica se é HTTP 401
  ou HTTP 200 com `code != 0`. Por isso `modo_sem_auth` existe com os dois
  comportamentos, e o cliente do broker precisa recusar nos dois.

## O que NÃO é AdsPower

`/__fake__/*` é território do duplê e está marcado no próprio path. É ali que
mora o substituto do driver CDP — o AdsPower não faz screenshot; quem faz é o
navegador, pelo endpoint de depuração que o `start` devolve. O driver real é
checkpoint externo (`broker.adspower.NavegadorNaoImplementado`).
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

#: PNG 1×1 transparente, válido. Bytes reais para que o SHA-256 do artefato seja
#: um hash de imagem de verdade, e não de uma string qualquer.
PNG_MINIMO = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


@dataclass
class CenarioDeNavegacao:
    """O que o duplê responde para uma URL pedida."""

    url_final: Optional[str] = None          # None => igual à pedida
    redirecionamentos: tuple[str, ...] = ()
    status_http: int = 200
    console: tuple[dict[str, Any], ...] = ()
    rede: tuple[dict[str, Any], ...] = ()
    imagem: bytes = PNG_MINIMO
    atraso_s: float = 0.0


@dataclass
class EstadoDoDuple:
    chave_esperada: str
    perfis_conhecidos: set[str] = field(default_factory=set)
    #: `http_401` ou `code_menos_um` — ver o docstring do módulo.
    modo_sem_auth: str = "http_401"
    atraso_global_s: float = 0.0
    cenarios: dict[str, CenarioDeNavegacao] = field(default_factory=dict)
    cenario_padrao: CenarioDeNavegacao = field(default_factory=CenarioDeNavegacao)
    perfis_ativos: set[str] = field(default_factory=set)
    chamadas: dict[str, int] = field(default_factory=dict)
    autorizacoes_recebidas: list[str] = field(default_factory=list)
    trava: threading.Lock = field(default_factory=threading.Lock)

    def contar(self, caminho: str) -> None:
        with self.trava:
            self.chamadas[caminho] = self.chamadas.get(caminho, 0) + 1


class _Manipulador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    estado: EstadoDoDuple  # injetado pela fábrica

    # Silencia o log padrão: ele imprime a query string inteira em stderr, e a
    # query carrega `user_id`. Um duplê que vaza identificador de perfil no log
    # do teste ensina o hábito errado.
    def log_message(self, *_args: Any) -> None:  # noqa: D102
        return

    # ── infraestrutura ───────────────────────────────────────────────────────

    def _responder(self, status: int, corpo: dict[str, Any] | bytes,
                   tipo: str = "application/json") -> None:
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _envelope(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"code": 0, "data": data, "msg": "success"}

    def _falha(self, msg: str = "failed") -> dict[str, Any]:
        return {"code": -1, "data": {}, "msg": msg}

    def _autorizado(self) -> bool:
        cabecalho = self.headers.get("Authorization", "")
        self.estado.autorizacoes_recebidas.append(cabecalho)
        return cabecalho == f"Bearer {self.estado.chave_esperada}"

    def _recusar_sem_auth(self) -> None:
        if self.estado.modo_sem_auth == "http_401":
            self._responder(401, self._falha("unauthorized"))
        else:
            self._responder(200, self._falha("unauthorized"))

    # ── rotas ────────────────────────────────────────────────────────────────

    def do_GET(self) -> None:  # noqa: N802 - assinatura do BaseHTTPRequestHandler
        partes = urlparse(self.path)
        caminho = partes.path
        consulta = {k: v[0] for k, v in parse_qs(partes.query).items()}
        self.estado.contar(caminho)

        if self.estado.atraso_global_s:
            time.sleep(self.estado.atraso_global_s)

        if not self._autorizado():
            self._recusar_sem_auth()
            return

        if caminho == "/status":
            self._responder(200, self._envelope({}))
            return

        user_id = consulta.get("user_id", "")

        if caminho == "/api/v1/browser/active":
            if user_id not in self.estado.perfis_conhecidos:
                self._responder(200, self._falha("user not found"))
                return
            ativo = user_id in self.estado.perfis_ativos
            dados: dict[str, Any] = {"status": "Active" if ativo else "Inactive"}
            if ativo:
                dados["ws"] = self._ws(user_id)
            self._responder(200, self._envelope(dados))
            return

        if caminho == "/api/v1/browser/start":
            if user_id not in self.estado.perfis_conhecidos:
                self._responder(200, self._falha("user not found"))
                return
            with self.estado.trava:
                self.estado.perfis_ativos.add(user_id)
            self._responder(200, self._envelope({
                "ws": self._ws(user_id),
                "debug_port": str(self.server.server_address[1]),
                "webdriver": "/duple/chromedriver",
            }))
            return

        if caminho in ("/api/v1/browser/stop", "/api/v1/browser/close"):
            with self.estado.trava:
                self.estado.perfis_ativos.discard(user_id)
            self._responder(200, self._envelope({}))
            return

        self._responder(404, self._falha("not found"))

    def do_POST(self) -> None:  # noqa: N802
        partes = urlparse(self.path)
        self.estado.contar(partes.path)
        if partes.path != "/__fake__/navegar":
            self._responder(404, self._falha("not found"))
            return
        if not self._autorizado():
            self._recusar_sem_auth()
            return
        tamanho = int(self.headers.get("Content-Length") or 0)
        try:
            pedido = json.loads(self.rfile.read(tamanho).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._responder(400, self._falha("bad request"))
            return

        url = str(pedido.get("url", ""))
        cenario = self.estado.cenarios.get(url, self.estado.cenario_padrao)
        if cenario.atraso_s:
            time.sleep(cenario.atraso_s)
        self._responder(200, {
            "url_final": cenario.url_final or url,
            "redirecionamentos": list(cenario.redirecionamentos),
            "status_http": cenario.status_http,
            "console": [dict(c) for c in cenario.console],
            "rede": [dict(r) for r in cenario.rede],
            "imagem_hex": cenario.imagem.hex(),
            "mime": "image/png",
        })

    def _ws(self, user_id: str) -> dict[str, str]:
        porta = self.server.server_address[1]
        return {
            "selenium": f"127.0.0.1:{porta}",
            # O `user_id` NÃO entra no path do ws: o duplê não devolve ao broker
            # um identificador que o broker não deve carregar adiante.
            "puppeteer": f"ws://127.0.0.1:{porta}/devtools/browser/duple-{len(user_id)}",
        }


class ServidorFalsoDoAdsPower:
    """Sobe em `127.0.0.1:0` e devolve a porta efetiva. Use como context manager."""

    def __init__(self, estado: EstadoDoDuple):
        self.estado = estado
        manipulador = type("_ManipuladorLigado", (_Manipulador,), {"estado": estado})
        self._servidor = ThreadingHTTPServer(("127.0.0.1", 0), manipulador)
        self._thread: Optional[threading.Thread] = None

    @property
    def porta(self) -> int:
        return int(self._servidor.server_address[1])

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.porta}"

    def __enter__(self) -> "ServidorFalsoDoAdsPower":
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self._servidor.shutdown()
        self._servidor.server_close()
        if self._thread:
            self._thread.join(timeout=5)


__all__ = [
    "CenarioDeNavegacao", "EstadoDoDuple", "PNG_MINIMO", "ServidorFalsoDoAdsPower",
]
