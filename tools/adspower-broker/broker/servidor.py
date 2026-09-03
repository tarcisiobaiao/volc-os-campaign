"""A porta HTTP do broker: loopback, Bearer próprio, duas rotas e nada mais.

## Por que só duas rotas

`POST /v1/operacoes` e `GET /v1/saude`. Não existe rota que receba `user_id`,
não existe rota que execute comando, não existe proxy genérico para a Local API.
A ausência é o contrato: um broker com um endpoint `POST /proxy` teria toda a
allowlist de operações contornável por quem já passou pelo Bearer.

## Por que o corpo é lido cru e validado à mão

Mesmo motivo documentado em `backend/app/asset_vault/rotas.py`: um validador que
ecoa o valor recusado publica, na resposta de erro, exatamente o que a recusa
existia para impedir. Aqui não há Pydantic — a validação é explícita e as
mensagens citam CAMPO, nunca valor.

## O log

`log_message` é anulado. O padrão do `BaseHTTPRequestHandler` imprime a linha de
requisição inteira em stderr; num broker, isso significaria imprimir a query e,
com ela, qualquer identificador que alguém tenha posto lá.
"""
from __future__ import annotations

import hmac
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import urlparse

from app.visual_proof import dominio as dom
from broker.configuracao import ConfiguracaoDoBroker
from broker.execucao import ExecutorDoBroker

log = logging.getLogger("volc.broker.http")

LIMITE_DE_CORPO = 64 * 1024


class _Manipulador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    config: ConfiguracaoDoBroker
    executor: ExecutorDoBroker

    def log_message(self, *_args: Any) -> None:  # noqa: D102
        return

    # ── infraestrutura ───────────────────────────────────────────────────────

    def _responder(self, status: int, corpo: dict[str, Any]) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def _erro(self, status: int, codigo: str, mensagem: str) -> None:
        self._responder(status, {"codigo": codigo, "mensagem": mensagem})

    def _autorizado(self) -> bool:
        """`compare_digest` porque comparar tokens com `==` vaza por tempo."""
        cabecalho = self.headers.get("Authorization", "")
        partes = cabecalho.split(None, 1)
        if len(partes) != 2 or partes[0].lower() != "bearer":
            return False
        return hmac.compare_digest(partes[1].strip(), self.config.token_de_autenticacao)

    def _exigir_auth(self) -> bool:
        if self._autorizado():
            return True
        # 401 sem `WWW-Authenticate` com realm: um realm nomeado conta ao
        # varredor qual serviço está atrás da porta.
        self._erro(401, "sem_credencial",
                   "credencial ausente ou inválida para este broker.")
        return False

    # ── rotas ────────────────────────────────────────────────────────────────

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/v1/saude":
            self._erro(404, "rota_inexistente", "este broker só expõe /v1/saude e /v1/operacoes.")
            return
        if not self._exigir_auth():
            return
        self._responder(200, self.config.saude())

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/v1/operacoes":
            self._erro(404, "rota_inexistente", "este broker só expõe /v1/saude e /v1/operacoes.")
            return
        if not self._exigir_auth():
            return

        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho > LIMITE_DE_CORPO:
            self._erro(413, "corpo_grande", "o corpo do pedido excede o limite do broker.")
            return
        try:
            bruto = json.loads(self.rfile.read(tamanho).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._erro(400, "corpo_invalido", "o corpo do pedido não é JSON válido.")
            return
        if not isinstance(bruto, dict):
            self._erro(400, "corpo_invalido", "o corpo do pedido precisa ser um objeto JSON.")
            return

        try:
            pedido = pedido_de_dicionario(bruto)
        except dom.PayloadRecusado as exc:
            self._erro(400, "payload_invalido", str(exc))
            return

        recibo = self.executor.executar(
            pedido, consumidor=self.headers.get("X-Volc-Consumidor", "http"))
        # 200 para tudo que produziu recibo — inclusive recusa. O estado do
        # RECIBO é a resposta; um 403 sem corpo faria o chamador perder o motivo.
        self._responder(200, recibo.para_dicionario())


def pedido_de_dicionario(bruto: dict[str, Any]) -> dom.AdsPowerBrokerRequest:
    """Converte o JSON no contrato, recusando campo desconhecido.

    `extra=forbid` na mão: um campo que o broker ignora em silêncio é um campo
    que quem chamou acha que enviou. `localizador` está entre os proibidos de
    propósito — o broker resolve pela allowlist, e aceitar um endereço vindo do
    chamador transformaria o broker na porta do cofre.
    """
    conhecidos = {
        "pedido_id", "chave_idempotencia", "operacao", "perfil", "owner_sub",
        "ativo_id", "timeout_s", "url_alvo", "dominio_esperado", "viewport", "timezone",
    }
    desconhecidos = sorted(set(bruto) - conhecidos)
    if desconhecidos:
        raise dom.PayloadRecusado(
            f"campo(s) que este broker não conhece: {', '.join(desconhecidos)}")

    perfil_bruto = bruto.get("perfil")
    if not isinstance(perfil_bruto, dict):
        raise dom.PayloadRecusado("o pedido precisa de um objeto `perfil`.")
    campos_de_perfil = {
        "ativo_id", "perfil_logico", "owner_sub", "provider", "credencial_nome_logico"}
    extras = sorted(set(perfil_bruto) - campos_de_perfil)
    if extras:
        raise dom.PayloadRecusado(
            f"campo(s) que o perfil não aceita: {', '.join(extras)}. O broker resolve "
            "a referência pela própria allowlist.")

    viewport_bruto = bruto.get("viewport")
    viewport = None
    if isinstance(viewport_bruto, dict):
        try:
            viewport = dom.Viewport(
                largura=int(viewport_bruto.get("largura", 0)),
                altura=int(viewport_bruto.get("altura", 0)))
        except (TypeError, ValueError):
            raise dom.PayloadRecusado("viewport inválido.") from None

    try:
        perfil = dom.BrowserProfileReference(
            ativo_id=str(perfil_bruto.get("ativo_id", "")),
            perfil_logico=str(perfil_bruto.get("perfil_logico", "")),
            owner_sub=str(perfil_bruto.get("owner_sub", "")),
            provider=str(perfil_bruto.get("provider", "")),
            credencial_nome_logico=str(perfil_bruto.get("credencial_nome_logico", "")),
        )
        return dom.AdsPowerBrokerRequest(
            pedido_id=str(bruto.get("pedido_id", "")),
            chave_idempotencia=str(bruto.get("chave_idempotencia", "")),
            operacao=str(bruto.get("operacao", "")),
            perfil=perfil,
            owner_sub=str(bruto.get("owner_sub", "")),
            ativo_id=str(bruto.get("ativo_id", "")),
            timeout_s=int(bruto.get("timeout_s", 45)),
            url_alvo=bruto.get("url_alvo"),
            dominio_esperado=bruto.get("dominio_esperado"),
            viewport=viewport,
            timezone=bruto.get("timezone"),
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, dom.PayloadRecusado):
            raise
        raise dom.PayloadRecusado("o pedido não respeita o contrato do broker.") from None


class ServidorDoBroker:
    """Sobe o broker. O preflight já aconteceu em `configuracao.carregar`."""

    def __init__(self, config: ConfiguracaoDoBroker, executor: ExecutorDoBroker):
        self.config = config
        manipulador = type("_ManipuladorLigado", (_Manipulador,),
                           {"config": config, "executor": executor})
        self._servidor = ThreadingHTTPServer(
            (config.bind_host, config.bind_porta), manipulador)
        self._thread: Optional[threading.Thread] = None

    @property
    def porta(self) -> int:
        return int(self._servidor.server_address[1])

    @property
    def base(self) -> str:
        return f"http://{self.config.bind_host}:{self.porta}"

    def __enter__(self) -> "ServidorDoBroker":
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.parar()

    def servir_para_sempre(self) -> None:  # pragma: no cover - caminho de processo
        self._servidor.serve_forever()

    def parar(self) -> None:
        self._servidor.shutdown()
        self._servidor.server_close()
        if self._thread:
            self._thread.join(timeout=5)


__all__ = ["ServidorDoBroker", "pedido_de_dicionario"]
