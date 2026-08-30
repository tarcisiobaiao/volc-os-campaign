"""Verificador HTTP de URL — a checagem "essa página existe mesmo?" sem browser.

Por que este módulo existe: o gate factual (`_gate_research`) e os links de
plataforma (`build_platform_links`) precisam saber se uma URL que a pesquisa
trouxe é uma página viva. Isso é uma pergunta de HTTP, não de renderização —
mas estava pendurada em `deps.screenshot.verify_url`, e `deps.screenshot` só
existe quando `run.official_screenshots` está LIGADO. Resultado medido:
desligar os prints (uma flag que se anuncia cosmética e best-effort) passava a
REPROVAR toda página com fato numérico. Aqui a verificação vira um port próprio
(`UrlVerifier`), sempre ligado, e a flag de screenshot volta a ser cosmética.

Contrato, deliberadamente conservador (fail-CLOSED):
  - só `https`;
  - segue redirect; status >= 400 → não verificada;
  - 401/403/405/429 (antibot/paywall/método recusado) → NÃO verificada, mas
    contabilizada à parte, porque a causa é "não deu para saber", não "a página
    não existe" — e o operador precisa ler essa diferença no relatório;
  - se o corpo for HTML, ainda checa os marcadores de página de erro (um HTTP
    200 servindo "página não encontrada" é comum em WordPress mal configurado).

CACHE POR RUN: uma instância vive um run inteiro (montada em `cli.build_deps`)
e memoriza cada URL já vista. É o que mata a visita DUPLICADA por página —
`_write_ctx` roda no `step_write`, DE NOVO no `step_content_gate` e mais uma vez
no `step_publish`; antes, cada passagem subia o Chromium de novo para as MESMAS
URLs, com 20s de timeout cada.

Honestidade de User-Agent: mandamos um UA que diz o que somos. Não fingimos ser
o Chrome de uma pessoa. O preço disso é tomar 403 de sites com antibot — e a
resposta a um 403 é descartar o link (fail-closed), nunca inventar identidade
para furar o bloqueio.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

# UA verdadeiro: identifica a ferramenta e o propósito. Sem impersonation.
USER_AGENT = "FunnelForge-LinkCheck/1.0 (verificacao de link; sem coleta de dados)"

# Trechos que, no <title> ou no corpo, denunciam página de erro/404 mesmo com
# HTTP 200. Mesma lista que o adapter de screenshot usa no seu próprio guard.
ERROR_PAGE_MARKERS = (
    "não existe", "nao existe", "não encontrada", "nao encontrada",
    "not found", "erro 404", "página não", "pagina nao",
)

# Status que significam "não deu para verificar" (e não "não existe").
_INCONCLUSIVE_STATUS = (401, 403, 405, 429)

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]*>")


@dataclass
class VerifierStats:
    """Telemetria do verificador, para o relatório do operador."""
    checked: int = 0          # URLs distintas efetivamente visitadas
    cache_hits: int = 0       # visitas evitadas pelo cache (a correção da visita dupla)
    ok: int = 0
    refused: int = 0          # visitada e reprovada (404 / HTML de erro / não-https)
    inconclusive: int = 0     # 401/403/405/429/timeout — bloqueio, não inexistência
    reasons: dict = field(default_factory=dict)  # url -> motivo, em português


def _strip_html(text: str) -> str:
    """Texto aproximado da página, minúsculo — o bastante para os marcadores.

    Não é um parser: joga fora script/style (onde mora texto que não é da
    página) e depois as tags. Barato de propósito; isto é um farejador de
    página de erro, não um leitor de conteúdo. O `<title>` sobrevive, que é
    justamente onde o "Página não encontrada" costuma estar."""
    return _TAG_RE.sub(" ", _SCRIPT_STYLE_RE.sub(" ", text)).lower()


class HttpUrlVerifier:
    """`UrlVerifier` sobre httpx — sem Playwright, sem Chromium, sem browser.

    `timeout_s` é curto de propósito (8s): esta checagem roda por URL, por
    página; o caminho antigo via Chromium usava 20s MAIS a subida do browser, e
    repetia tudo 2–3 vezes para a mesma URL na mesma página."""

    def __init__(self, *, timeout_s: float = 8.0, client: httpx.Client | None = None,
                 max_body_bytes: int = 20000) -> None:
        self._client = client or httpx.Client(
            timeout=timeout_s, follow_redirects=True,
            headers={"User-Agent": USER_AGENT,
                     "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
        )
        self._max_body = max_body_bytes
        self._cache: dict[str, bool] = {}
        self.stats = VerifierStats()

    def verify_url(self, url: str) -> bool:
        """True somente quando a URL respondeu como página viva e válida."""
        key = (url or "").strip()
        if not key:
            return False
        if key in self._cache:
            self.stats.cache_hits += 1
            return self._cache[key]
        result = self._check(key)
        self._cache[key] = result
        return result

    def bloqueada(self, url: str) -> bool:
        """A URL foi RECUSADA ou apenas não deu para checar?

        ⚠️ Esta distinção existia só na telemetria e não chegava a quem decide.
        `verify_url` devolve `False` nos dois casos, e o gate factual matava a
        página igual — mesmo quando a fonte é legítima e o que aconteceu foi um
        antibot no caminho.

        Medido no run #6: `bancobmg.com.br` (um banco de verdade) responde 200
        para `curl` sem User-Agent e **403 para qualquer UA declarado**,
        inclusive o nosso. É um WAF. A página 4 morreu por causa disso, depois
        de quatro tentativas contra a mesma URL e o mesmo bloqueio: US$ 0,4556
        num veredito que não tinha como mudar.

        `True` aqui significa "não deu para saber" — e "não deu para saber" não
        é a mesma coisa que "não existe".
        """
        chave = (url or "").strip()
        motivo = self.stats.reasons.get(chave, "")
        return "bloqueado" in motivo or "falha de rede" in motivo

    def motivo(self, url: str) -> str:
        """O texto em português do porquê, para o feedback da retentativa."""
        return self.stats.reasons.get((url or "").strip(), "")

    def _check(self, url: str) -> bool:
        if urlparse(url).scheme != "https":
            self.stats.refused += 1
            self.stats.reasons[url] = "não é https"
            return False
        self.stats.checked += 1
        try:
            resp = self._client.get(url)
        except Exception as exc:  # noqa: BLE001 - qualquer falha de rede é fail-closed
            self.stats.inconclusive += 1
            self.stats.reasons[url] = f"falha de rede: {type(exc).__name__}"
            return False
        status = resp.status_code
        if status in _INCONCLUSIVE_STATUS:
            self.stats.inconclusive += 1
            self.stats.reasons[url] = (
                f"bloqueado/indisponível para verificação (HTTP {status})")
            return False
        if status >= 400:
            self.stats.refused += 1
            self.stats.reasons[url] = f"HTTP {status}"
            return False
        content_type = (resp.headers.get("content-type") or "").lower()
        if "html" in content_type:
            body = _strip_html(resp.text[: self._max_body])
            if any(marker in body for marker in ERROR_PAGE_MARKERS):
                self.stats.refused += 1
                self.stats.reasons[url] = "responde 200 com texto de erro/404"
                return False
        self.stats.ok += 1
        return True
