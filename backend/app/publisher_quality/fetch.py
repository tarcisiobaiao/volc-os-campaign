from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

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


def fetch_public_https_once(url: str, *, timeout: int = 20, max_bytes: int = 2_000_000) -> dict[str, str]:
    """Read one public HTTPS page without cookies/auth and fail closed on redirects.

    The returned URL is normalized and query/fragment-free. The response body is
    capped so a public read cannot become an unbounded artifact collector.
    """
    safe_url = validate_public_https_target(url)
    request = Request(
        safe_url,
        headers={
            "User-Agent": "VOLC-PublisherSurfaceSnapshot/1.0 read-only",
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
