"""Cliente da Local API do AdsPower — só as quatro operações da allowlist.

## Fontes primárias, consultadas em 02/09/2026

| Fato | Fonte |
|---|---|
| base `http://local.adspower.net:50325/` ou `http://localhost:50325/` | https://localapi-doc-en.adspower.com/docs/Rdw7Iu |
| autenticação `header['Authorization']: Bearer xxxxxx` | https://localapi-doc-en.adspower.com/docs/Rdw7Iu |
| limite 2 req/s (0–200 perfis), 5 (200–5 mil), 10 (>5 mil); alguns endpoints 1 req/s | https://localapi-doc-en.adspower.com/docs/Rdw7Iu |
| `GET /api/v1/browser/start`, parâmetros e envelope | https://localapi-doc-en.adspower.com/docs/FFMFMf |
| `GET /api/v1/browser/active`, `status: Active\|Inactive` | https://localapi-doc-en.adspower.com/docs/YjFggL |
| `API_KEY` como variável e porta 50325 configurável | https://github.com/AdsPower/adspower-browser |

Envelope documentado:

    {"code": 0, "data": {"ws": {"selenium": "...", "puppeteer": "ws://..."},
                         "debug_port": "...", "webdriver": "..."}, "msg": "success"}
    {"code": -1, "data": {}, "msg": "failed"}

## O que NÃO está confirmado por fonte primária

- **O caminho exato de fechar o navegador.** A página de visão geral lista
  "Close Browser" e "Close Browser V2", e a documentação aberta em 02/09/2026
  não expôs o path. `/api/v1/browser/stop` é a forma usada pelos exemplos da
  comunidade e é o que este cliente envia — declarado como INFERIDO, não como
  citação. O duplê aceita os dois caminhos justamente para que a troca não
  quebre o E2E.
- **O que a API responde quando o Bearer está errado** (HTTP 401? 200 com
  `code != 0`?). O duplê é configurável nos dois modos, e o cliente trata
  ambos como recusa.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Protocol

from app.visual_proof import dominio as dom

#: Path inferido (ver docstring). Isolado numa constante para que a troca, se a
#: documentação publicar outro, seja de uma linha.
CAMINHO_FECHAR_INFERIDO = "/api/v1/browser/stop"


class AdsPowerRecusou(RuntimeError):
    """`code != 0`, HTTP 4xx/5xx ou corpo ilegível. Nunca vira sucesso vazio."""

    def __init__(self, mensagem: str, *, codigo: Optional[int] = None,
                 status_http: Optional[int] = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.status_http = status_http


class AdsPowerIndisponivel(RuntimeError):
    """Não deu para falar com a Local API. Rede, processo fora do ar."""


class AdsPowerTempoEsgotado(AdsPowerIndisponivel):
    """O prazo acabou esperando a Local API.

    Subclasse, e não erro à parte, porque um chamador que só quer saber "deu
    para falar?" continua acertando com um `except AdsPowerIndisponivel`. Mas
    quem monta o recibo distingue os dois: "não respondeu a tempo" e "não
    respondeu" mandam o operador investigar coisas diferentes.
    """


@dataclass(frozen=True)
class RespostaDoAdsPower:
    code: int
    msg: str
    data: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.code == 0

    def ws_puppeteer(self) -> Optional[str]:
        ws = self.data.get("ws") if isinstance(self.data, Mapping) else None
        if isinstance(ws, Mapping):
            valor = ws.get("puppeteer")
            return str(valor) if valor else None
        return None


AbridorHttp = Callable[[urllib.request.Request, float], Any]


def _abridor_padrao(pedido: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(pedido, timeout=timeout)  # noqa: S310 - base validada


class ClienteDoAdsPower:
    """Fala com a Local API. A chave entra por parâmetro e não fica guardada.

    ## Por que a chave não é atributo

    Um cliente que guarda a chave no `self` a mantém viva pelo tempo de vida do
    objeto — que, num servidor, é o tempo de vida do processo. Aqui ela chega em
    cada chamada, vinda de um `with segredo.usar()`, e sai de escopo junto com
    ele.
    """

    def __init__(
        self, base: str, *,
        portas_permitidas: tuple[int, ...] = (50325,),
        intervalo_minimo_s: float = 1.0,
        abridor: Optional[AbridorHttp] = None,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        # A fronteira é checada na CONSTRUÇÃO: um cliente apontado para fora do
        # loopback não deve chegar a existir.
        self.base = dom.exigir_endpoint_do_adspower(base, portas_permitidas=portas_permitidas)
        self._intervalo = max(0.0, float(intervalo_minimo_s))
        self._abridor = abridor or _abridor_padrao
        self._relogio = relogio
        self._dormir = dormir
        self._ultima_chamada = 0.0
        self._trava = threading.Lock()
        self.chamadas = 0

    # ── as quatro operações ──────────────────────────────────────────────────

    def status(self, chave: str, *, timeout_s: float = 10.0) -> RespostaDoAdsPower:
        return self._pedir("/status", {}, chave, timeout_s)

    def estado_do_perfil(self, chave: str, *, user_id: str,
                         timeout_s: float = 10.0) -> RespostaDoAdsPower:
        return self._pedir("/api/v1/browser/active", {"user_id": user_id}, chave, timeout_s)

    def abrir_perfil(self, chave: str, *, user_id: str, headless: bool = True,
                     ip_tab: int = 0, open_tabs: int = 1,
                     timeout_s: float = 60.0) -> RespostaDoAdsPower:
        """`open_tabs=1` fecha as abas de histórico; `ip_tab=0` esconde a de IP.

        Os dois são o padrão VOLC e não o padrão do AdsPower: uma aba de
        histórico ou de checagem de IP na frente muda o que o screenshot mostra,
        e um QA visual que fotografa a aba errada reprova a página certa.
        """
        return self._pedir("/api/v1/browser/start", {
            "user_id": user_id,
            "headless": 1 if headless else 0,
            "ip_tab": ip_tab,
            "open_tabs": open_tabs,
        }, chave, timeout_s)

    def fechar_perfil(self, chave: str, *, user_id: str,
                      timeout_s: float = 30.0) -> RespostaDoAdsPower:
        return self._pedir(CAMINHO_FECHAR_INFERIDO, {"user_id": user_id}, chave, timeout_s)

    # ── transporte ───────────────────────────────────────────────────────────

    def _throttle(self) -> None:
        """Respeita o limite documentado sem depender de o chamador lembrar.

        A trava é do CLIENTE e não global: dois brokers no mesmo host seriam
        dois clientes, e o limite do AdsPower é por instância dele. O que este
        código promete é não estourar sozinho.
        """
        if self._intervalo <= 0:
            return
        with self._trava:
            agora = self._relogio()
            espera = self._ultima_chamada + self._intervalo - agora
            if espera > 0:
                self._dormir(espera)
                agora = self._relogio()
            self._ultima_chamada = agora

    def _pedir(self, caminho: str, parametros: Mapping[str, Any], chave: str,
               timeout_s: float) -> RespostaDoAdsPower:
        if not chave:
            raise AdsPowerRecusou(
                "chamada sem chave da Local API. O broker não fala com o AdsPower sem "
                "autenticação — nem para 'só conferir o status'.")
        self._throttle()
        self.chamadas += 1
        query = urllib.parse.urlencode({k: v for k, v in parametros.items() if v is not None})
        url = f"{self.base}{caminho}" + (f"?{query}" if query else "")
        pedido = urllib.request.Request(url, method="GET", headers={
            "Authorization": f"Bearer {chave}",
            "Accept": "application/json",
            "User-Agent": "VOLC-AdsPowerBroker/1.0",
        })
        try:
            with self._abridor(pedido, timeout_s) as resposta:
                status_http = getattr(resposta, "status", 200) or 200
                bruto = resposta.read(1_000_000)
        except urllib.error.HTTPError as exc:
            corpo = self._corpo_seguro(exc)
            raise AdsPowerRecusou(
                f"a Local API recusou a operação (HTTP {exc.code}).",
                codigo=corpo.get("code") if isinstance(corpo, dict) else None,
                status_http=exc.code,
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # A mensagem do socket pode carregar o endereço; ela não é repassada.
            motivo = getattr(exc, "reason", None)
            if isinstance(exc, TimeoutError) or isinstance(motivo, TimeoutError):
                raise AdsPowerTempoEsgotado(
                    f"a Local API do AdsPower não respondeu em {timeout_s:g}s."
                ) from None
            raise AdsPowerIndisponivel(
                f"não foi possível falar com a Local API do AdsPower ({type(exc).__name__})."
            ) from None

        try:
            corpo = json.loads(bruto.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise AdsPowerIndisponivel(
                "a Local API respondeu em um formato que este broker não reconhece."
            ) from None
        if not isinstance(corpo, dict) or "code" not in corpo:
            raise AdsPowerIndisponivel(
                "a Local API respondeu sem o envelope `code`/`msg`/`data`.")

        dados = corpo.get("data")
        resposta_tipada = RespostaDoAdsPower(
            code=int(corpo.get("code", -1)),
            msg=dom.sanitizar_texto(str(corpo.get("msg", "")), limite=200),
            data=dados if isinstance(dados, Mapping) else {},
        )
        if not resposta_tipada.ok:
            raise AdsPowerRecusou(
                f"a Local API respondeu code={resposta_tipada.code}: {resposta_tipada.msg}",
                codigo=resposta_tipada.code, status_http=status_http)
        return resposta_tipada

    @staticmethod
    def _corpo_seguro(exc: urllib.error.HTTPError) -> Any:
        try:
            return json.loads(exc.read(100_000).decode("utf-8"))
        except Exception:  # noqa: BLE001 - corpo vazio, HTML de proxy, binário
            return {}


# ─────────────────────────────────────────────────────────────────────────────
# Navegação e captura
# ─────────────────────────────────────────────────────────────────────────────


class CheckpointExterno(RuntimeError):
    """A operação exige um recurso real que esta entrega decidiu não tocar."""


@dataclass(frozen=True)
class CapturaBruta:
    """O que volta de uma navegação, antes de virar veredito."""

    url_final: str
    redirecionamentos: tuple[str, ...]
    status_http: Optional[int]
    console: tuple[Mapping[str, Any], ...]
    rede: tuple[Mapping[str, Any], ...]
    imagem: bytes
    mime: str = "image/png"


class Navegador(Protocol):
    """A porta da captura. O broker não conhece CDP nem Puppeteer."""

    def capturar(self, *, ws_endpoint: str, url: str, viewport: dom.Viewport,
                 timezone: Optional[str], timeout_s: float) -> CapturaBruta: ...


class NavegadorNaoImplementado:
    """O driver real de CDP. Ele RECUSA em vez de fingir.

    Esta classe é o checkpoint externo escrito em código. Implementá-la
    significa abrir um navegador de verdade num perfil de verdade, e a missão
    que produziu este módulo proíbe isso explicitamente. Um `pass` silencioso
    aqui — ou um retorno com imagem vazia — faria a suíte ficar verde sobre uma
    capacidade que não existe.
    """

    def capturar(self, *, ws_endpoint: str, url: str, viewport: dom.Viewport,
                 timezone: Optional[str], timeout_s: float) -> CapturaBruta:
        raise CheckpointExterno(
            "a captura real por CDP não está implementada nesta entrega. Abrir um "
            "perfil real e fotografar uma página real é checkpoint externo, com "
            "autorização própria — ver docs/closure/"
            "hermes-adspower-visual-proof-control-plane-v1/AUTORIZACAO-EXTERNA.md.")


__all__ = [
    "AdsPowerIndisponivel", "AdsPowerRecusou", "AdsPowerTempoEsgotado", "CapturaBruta",
    "CheckpointExterno", "ClienteDoAdsPower", "Navegador", "NavegadorNaoImplementado",
    "RespostaDoAdsPower", "CAMINHO_FECHAR_INFERIDO",
]
