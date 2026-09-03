from __future__ import annotations

import hashlib
import ipaddress
import socket
from urllib.error import HTTPError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

#: O user-agent padrão do leitor read-only. Fica nomeado porque a checagem de
#: cloaking precisa pedir a MESMA página com outro user-agent, e um literal
#: repetido em dois arquivos é como as duas leituras deixam de ser comparáveis.
USER_AGENT_PADRAO = "VOLC-PublisherSurfaceSnapshot/1.0 read-only"

_PRIVATE_HOSTS = {"localhost", "localhost.localdomain"}


def _ip_is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return bool(
        ip.is_global
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def _host_is_private(host: str) -> bool:
    host = (host or "").strip().strip("[]").lower()
    if not host or host in _PRIVATE_HOSTS:
        return True
    try:
        return not _ip_is_public(host)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return True
    if not infos:
        return True
    for info in infos:
        addr = info[4][0]
        if not _ip_is_public(addr):
            return True
    return False


def validate_public_https_target(url: str) -> str:
    """Fail-closed validation for the optional one-URL public read path.

    This function does not fetch. It normalizes away query/fragment to avoid
    persisting campaign ids or accidental personal identifiers in artifacts.
    Callers must still re-run it after redirects before reading a response.
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https":
        raise ValueError("publisher quality target must be absolute HTTPS")
    if not parsed.hostname:
        raise ValueError("publisher quality target host is absent")
    if parsed.username or parsed.password:
        raise ValueError("publisher quality target must not contain credentials")
    if _host_is_private(parsed.hostname):
        raise ValueError("publisher quality target resolves to a private/local address")
    return urlunparse(("https", parsed.netloc.lower(), parsed.path or "/", "", "", ""))


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        validate_public_https_target(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _RecordingRedirectHandler(_SafeRedirectHandler):
    """Igual ao seguro, e ANOTA cada salto antes de segui-lo.

    A validação continua acontecendo primeiro: um salto para host privado
    levanta antes de virar linha do inventário. Anotar depois de validar é o que
    mantém a cadeia sendo evidência do que foi permitido, não do que foi tentado.
    """

    def __init__(self) -> None:
        super().__init__()
        self.saltos: list[dict[str, object]] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        pedido = super().redirect_request(req, fp, code, msg, headers, newurl)
        self.saltos.append(
            {
                "from": validate_public_https_target(req.full_url),
                "status": int(code),
                "to": validate_public_https_target(newurl),
            }
        )
        return pedido


def fetch_public_https_once(url: str, *, timeout: int = 20, max_bytes: int = 2_000_000) -> dict[str, str]:
    """Read one public HTTPS page without cookies/auth and fail closed on redirects.

    The returned URL is normalized and query/fragment-free. The response body is
    capped so a public read cannot become an unbounded artifact collector.
    """
    safe_url = validate_public_https_target(url)
    request = Request(
        safe_url,
        headers={
            "User-Agent": USER_AGENT_PADRAO,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
        method="GET",
    )
    opener = build_opener(_SafeRedirectHandler, HTTPSHandler)
    with opener.open(request, timeout=timeout) as response:
        final_url = validate_public_https_target(response.geturl())
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            raise ValueError(f"publisher quality target did not return HTML: {content_type}")
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("publisher quality target response exceeds read-only byte cap")
    return {"url": final_url, "html": raw.decode("utf-8", errors="replace")}


def fetch_public_https_chain(
    url: str,
    *,
    user_agent: str = USER_AGENT_PADRAO,
    timeout: int = 20,
    max_bytes: int = 2_000_000,
) -> dict[str, object]:
    """Uma leitura pública, com a CADEIA DE REDIRECIONAMENTO preservada.

    ## Por que isto precisou existir separado de `fetch_public_https_once`

    O leitor de snapshot devolve HTML e URL final; ele descarta os saltos. Para
    o portão de destino pago o salto É a evidência — "redirecionou" e "não
    redirecionou" são achados diferentes, e a política de circumventing systems
    fala explicitamente de redirecionamento. Preservar exige um handler que
    anote, e um handler que anota não deve ser imposto a quem só quer o HTML.

    ## O que muda em relação ao leitor de snapshot, e o que não muda

    Muda: aceita `user_agent` (a checagem de cloaking precisa de duas leituras
    com user-agents diferentes), devolve saltos, status e o sha256 do corpo, e
    tolera resposta de erro HTTP — um destino que devolve 404 ao AdsBot é
    justamente o que a política de "destinations that don't work" descreve, e
    levantar exceção ali apagaria a evidência.

    NÃO muda: a validação fail-closed é a mesma `validate_public_https_target`,
    aplicada na URL inicial, em CADA salto e na URL final. Sem cookies, sem
    autenticação, sem POST, com teto de bytes. Não existe caminho aqui para
    escrever em lugar nenhum.
    """
    safe_url = validate_public_https_target(url)
    handler = _RecordingRedirectHandler()
    opener = build_opener(handler, HTTPSHandler)
    request = Request(
        safe_url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(response.status)
            final_url = validate_public_https_target(response.geturl())
            headers = {k.lower(): v for k, v in response.headers.items()}
            raw = response.read(max_bytes + 1)
    except HTTPError as erro:
        # Resposta de erro ainda é resposta: o corpo é curto e o status é o dado.
        status = int(erro.code)
        final_url = validate_public_https_target(erro.geturl())
        headers = {k.lower(): v for k, v in (erro.headers or {}).items()}
        raw = erro.read(min(max_bytes, 64_000))
    if len(raw) > max_bytes:
        raise ValueError("publisher quality target response exceeds read-only byte cap")
    return {
        "url": safe_url,
        "final_url": final_url,
        "status": status,
        "hops": list(handler.saltos),
        "headers": headers,
        "user_agent": user_agent,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "html": raw.decode("utf-8", errors="replace"),
    }
