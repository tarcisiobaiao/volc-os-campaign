"""Broker local entre o 1Password e a Local API do AdsPower (P03-T11).

## O que ele é

Um processo que roda NO HOST ISOLADO, escuta só em loopback, exige autenticação
própria, recebe REFERÊNCIAS lógicas (nunca segredo), resolve o segredo em
memória efêmera, fala com a Local API do AdsPower e devolve um recibo
sanitizado. Ele não devolve valor resolvido, não aceita comando arbitrário e não
tem endpoint que aceite um `user_id` cru vindo do chamador.

## O que ele NÃO é

Não é cofre (o 1Password é), não é inventário (o Cofre de Ativos é), não é
scheduler editorial e não é prova de que a página está correta. E, nesta
entrega, ele **não faz nenhuma chamada real ao AdsPower**: o driver de captura
real (CDP sobre o `ws.puppeteer` devolvido por `/api/v1/browser/start`) é um
checkpoint externo declarado, e o código recusa em vez de fingir — ver
`broker.navegador.NavegadorNaoImplementado`.

## A única dependência VOLC

`app.visual_proof.dominio` — `stdlib`-only de propósito, para poder viajar para
o host isolado sem carregar FastAPI nem httpx. O import abaixo é o bootstrap
dessa dependência, e ele **falha fechado**: um broker sem a política de URL não
sobe, porque um broker sem política de URL é um proxy autenticado para qualquer
endereço que alguém peça.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _preparar_caminho() -> None:
    """Coloca `<repo>/backend` no `sys.path` para achar `app.visual_proof`.

    No host isolado, o pacote de deploy leva as duas árvores lado a lado
    (`tools/adspower-broker/` e `backend/app/visual_proof/`) — ver
    `deploy/adspower-broker/README.md`. Se a política não estiver lá, o
    `ImportError` abaixo derruba o processo na importação, e não na primeira
    navegação.
    """
    raiz = Path(__file__).resolve().parents[3]
    backend = raiz / "backend"
    if backend.is_dir() and str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


_preparar_caminho()

try:
    from app.visual_proof import dominio  # noqa: F401  (reexport intencional)
except ImportError as exc:  # pragma: no cover - falha de empacotamento
    raise ImportError(
        "o broker não encontrou `app.visual_proof.dominio`. Ele não sobe sem a "
        "política de URL: um broker autenticado sem allowlist de destino é um "
        "proxy para qualquer endereço que peçam a ele."
    ) from exc

__all__ = ["dominio"]
