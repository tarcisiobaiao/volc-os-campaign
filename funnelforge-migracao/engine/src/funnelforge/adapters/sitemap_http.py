"""Escolha da saída cross-funnel, lendo o sitemap real do site.

A última página de solução precisa recircular para um guia REAL do mesmo site --
relacionado, mas não redundante. Nunca um slug inventado.

## Por que não há mais léxico

Isto aqui era duas listas escritas à mão (`_CORE` com fgts/consignado/saque,
`_BRIDGE` com pis/pasep/inss). Funcionava para UM funil e reprovava todos os
outros: num funil de cartão para negativado, `credito` estava no `_CORE` e
derrubava justamente as páginas do tema; num de entregador de aplicativo,
nenhuma das duas listas pontuava nada e a saída caía no fallback.

A regra nova não precisa de vocabulário nenhum, porque usa uma propriedade que
o site já tem: **um site é uma vertical só**. Então qualquer outra página dele
já é "relacionada" por construção, e o que resta medir é a DIVERSIDADE:

    3+ termos em comum com o tema  -> é a mesma pauta, redundante, fora
    1 a 2 termos                   -> relacionada e diversa, é o alvo
    0 termo                        -> pode ser de outro assunto, fica no fim

Os termos do tema chegam do chamador (`theme`) — e o VOLC O.S. tem material bem
melhor que o H1 para mandar ali: as keywords do card e os apelidos da entidade.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

# Acima de quantos termos em comum a página é a MESMA pauta, e não uma vizinha.
REDUNDANTE_A_PARTIR_DE = 3
_STOP = {
    "como", "de", "do", "da", "e", "o", "a", "em", "no", "na", "pelo", "pela",
    "que", "tem", "ter", "quem", "onde", "ver", "por", "para", "seu", "sua",
    "voce", "você", "quando", "vale", "pode", "onde", "com", "sem", "num",
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9à-ü]{3,}", text.lower())
            if t not in _STOP and not t.isdigit()}


class HttpSitemapProvider:
    """`SitemapProvider` reading the site's WordPress sitemap over HTTP."""

    _CANDIDATE_PATHS = ("/post-sitemap.xml", "/wp-sitemap.xml", "/sitemap.xml")

    def __init__(self, domain: str, client: httpx.Client | None = None):
        self.domain = domain.rstrip("/")
        self._client = client or httpx.Client(timeout=30, follow_redirects=True)

    def _fetch_urls(self) -> list[str]:
        for path in self._CANDIDATE_PATHS:
            try:
                r = self._client.get(self.domain + path)
            except Exception:  # noqa: BLE001 - sitemap is best-effort
                continue
            if r.status_code != 200 or "<loc>" not in r.text:
                continue
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
            if "<sitemapindex" in r.text:
                urls: list[str] = []
                for sm in locs:
                    if not any(k in sm for k in ("post", "rec", "/r-", "/r/")):
                        continue
                    try:
                        rr = self._client.get(sm)
                    except Exception:  # noqa: BLE001
                        continue
                    if rr.status_code == 200:
                        urls += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", rr.text)
                if urls:
                    return urls
                continue
            return locs
        return []

    def _rank(self, urls: list[str], theme: str, exclude_slugs: list[str]) -> list[str]:
        """Ordena as URLs do mesmo domínio por DIVERSIDADE em relação ao tema.

        Sem léxico: o que decide é quantos termos do tema a página repete. Ver o
        cabeçalho do módulo para o porquê de a regra ser essa e não uma lista."""
        theme_tok = _tokens(theme)
        exclude = {s.strip("/").split("/")[-1] for s in exclude_slugs}
        dhost = urlparse(self.domain).netloc.lower()
        scored: list[tuple[float, str]] = []
        seen: set[str] = set()
        for url in urls:
            host = urlparse(url).netloc.lower()
            if host and host != dhost and not host.endswith("." + dhost):
                continue  # same-domain law
            slug = urlparse(url).path.strip("/").split("/")[-1]
            if not slug or slug in exclude or slug in seen:
                continue
            tok = _tokens(slug)
            if not tok:
                continue
            comuns = len(tok & theme_tok)
            if comuns >= REDUNDANTE_A_PARTIR_DE:
                continue  # é a mesma pauta com outro título
            # 1 ou 2 termos em comum é o ponto doce: perto o bastante para o
            # leitor entender por que aquilo apareceu, longe o bastante para
            # não ser a página que ele acabou de ler. Zero em comum ainda vale
            # (o site é uma vertical só), mas vai para o fim da fila.
            score = 1.0 if comuns else 0.3
            seen.add(slug)
            scored.append((score, url))
        scored.sort(key=lambda x: -x[0])
        return [u for _, u in scored]

    def cross_funnel_targets(self, *, theme: str, exclude_slugs: list[str]) -> list[str]:
        return self._rank(self._fetch_urls(), theme, exclude_slugs)
