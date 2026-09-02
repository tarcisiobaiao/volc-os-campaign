"""Um Postiz de mentira que fala HTTP de verdade.

## Por que HTTP, e nao um dublê da porta

Um dublê que implementasse `PortaDePublicacao` em Python provaria o NUCLEO e
deixaria o `AdaptadorPostiz` inteiro sem teste — justamente a parte onde moram
os erros que doem: montagem do corpo, traducao de estado, tratamento de timeout,
distincao entre falha e incerteza. Este fake e um `httpx.MockTransport`: ele
responde as MESMAS rotas da API oficial, com os MESMOS nomes de campo, e o
adaptador real e exercitado sem tocar a rede.

O repositorio ja tinha decidido isso uma vez: `shim_de_postgrest()` em
`backend/tests/test_trafego_persistencia.py` e um PostgREST de mentira na frente
de um Postgres de verdade, instalado por monkeypatch. Este arquivo e o mesmo
padrao para o control plane.

## O que ele reproduz da API oficial (lida em 02/09/2026)

- `POST /public/v1/posts` -> `[{postId, integration}]`, com `type` em
  draft|schedule|now e `date` em UTC ISO;
- `GET  /public/v1/posts?startDate&endDate` -> `{posts:[{id, content, state,
  publishDate, releaseURL, integration}]}` — e NAO existe busca por id, como na
  API real;
- `DELETE /public/v1/posts/{id}` -> `{id}`;
- `GET  /public/v1/integrations` -> `[{id, name, identifier, profile, disabled}]`;
- `Authorization` cru (sem "Bearer"), e 401 quando falta ou nao confere;
- 429 quando o limite da janela estoura.

## O que ele reproduz DE PROPOSITO do mundo real

`falhar_com` injeta os desfechos que produzem os defeitos caros: timeout,
500 depois de ter gravado, corpo 2xx ilegivel, e resposta 200 SEM `postId`.
Os tres ultimos sao os que transformam "a API respondeu" em recibo falso quando
o adaptador e otimista.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

Falha = Literal[
    "timeout",
    "erro_de_rede",
    "500_apos_gravar",
    "corpo_ilegivel",
    "sem_post_id",
    "429",
    "401",
    "400",
]


@dataclass
class PostFake:
    id: str
    integration: str
    content: str
    state: str                    # DRAFT | QUEUE | PUBLISHED | ERROR
    publishDate: str
    releaseURL: str | None = None


@dataclass
class ControlPlaneFake:
    """Estado do control plane de mentira, e o transporte que o serve."""

    token: str = "token-de-prova-nao-e-segredo"
    integracoes: list[dict[str, Any]] = field(default_factory=lambda: [
        {"id": "integ-piloto-0001", "name": "Pagina Piloto", "identifier": "facebook",
         "profile": "pagina.piloto", "disabled": False, "picture": None},
        {"id": "integ-desligada-01", "name": "Perfil Desligado", "identifier": "instagram",
         "profile": "perfil.desligado", "disabled": True, "picture": None},
    ])
    posts: dict[str, PostFake] = field(default_factory=dict)

    #: Desfecho injetado para a PROXIMA chamada de escrita. Consumido uma vez.
    falha_na_proxima: Falha | None = None
    #: Chamadas registradas, para provar "o adaptador foi chamado UMA vez".
    chamadas: list[tuple[str, str]] = field(default_factory=list)
    _sequencia: int = 0

    # -- controle do cenario -------------------------------------------------

    def falhar_com(self, falha: Falha) -> None:
        self.falha_na_proxima = falha

    def publicar_de_verdade(self, post_id: str, url: str) -> None:
        """O que acontece quando o horario chega e o Postiz publica sozinho."""
        post = self.posts[post_id]
        post.state = "PUBLISHED"
        post.releaseURL = url
        post.publishDate = _agora()

    def marcar_erro(self, post_id: str) -> None:
        self.posts[post_id].state = "ERROR"

    def chamadas_de_escrita(self) -> list[tuple[str, str]]:
        return [c for c in self.chamadas if c[0] in ("POST", "DELETE")]

    # -- transporte ----------------------------------------------------------

    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._responder)

    def cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transporte())

    def _responder(self, requisicao: httpx.Request) -> httpx.Response:
        caminho = requisicao.url.path
        metodo = requisicao.method
        self.chamadas.append((metodo, caminho))

        # Autenticacao: o header e `Authorization` com o token CRU, sem Bearer.
        recebido = requisicao.headers.get("Authorization", "")
        if recebido != self.token:
            return httpx.Response(401, json={"message": "unauthorized"})

        if not caminho.startswith("/public/v1/"):
            return httpx.Response(404, json={"message": "not found"})

        if metodo == "GET" and caminho == "/public/v1/integrations":
            return httpx.Response(200, json=self.integracoes)

        if metodo == "GET" and caminho == "/public/v1/posts":
            return self._listar(requisicao)

        if metodo == "POST" and caminho == "/public/v1/posts":
            return self._criar(requisicao)

        if metodo == "DELETE" and caminho.startswith("/public/v1/posts/"):
            return self._apagar(caminho.rsplit("/", 1)[-1])

        return httpx.Response(404, json={"message": "not found"})

    # -- rotas ---------------------------------------------------------------

    def _criar(self, requisicao: httpx.Request) -> httpx.Response:
        falha, self.falha_na_proxima = self.falha_na_proxima, None

        if falha == "timeout":
            raise httpx.ReadTimeout("timeout injetado", request=requisicao)
        if falha == "erro_de_rede":
            raise httpx.ConnectError("conexao recusada (injetada)", request=requisicao)
        if falha == "429":
            return httpx.Response(429, json={"message": "rate limit"})
        if falha == "401":
            return httpx.Response(401, json={"message": "unauthorized"})
        if falha == "400":
            # ⚠️ O corpo ECOA o header, como gateways reais fazem. E o cenario da
            # contraprova H: se o adaptador repassasse isso, o token iria para a
            # coluna `ultimo_erro` e de la para a tela.
            return httpx.Response(400, json={
                "message": "invalid request",
                "echo": {"Authorization": self.token},
            })

        corpo = json.loads(requisicao.content or b"{}")
        tipo = corpo.get("type")
        if tipo not in ("draft", "schedule", "now"):
            return httpx.Response(400, json={"message": "invalid type"})
        # A API real exige `date` mesmo em `now` (onde e ignorado).
        if not corpo.get("date"):
            return httpx.Response(400, json={"message": "date is required"})
        if "shortLink" not in corpo or "tags" not in corpo:
            return httpx.Response(400, json={"message": "shortLink and tags are required"})

        itens = corpo.get("posts") or []
        if tipo != "draft" and not itens:
            return httpx.Response(400, json={"message": "posts is required unless draft"})

        # ⚠️ O POST E GRAVADO ANTES DAS FALHAS DE RESPOSTA ABAIXO. E isso que
        # torna `500_apos_gravar` e `corpo_ilegivel` cenarios uteis: o conteudo
        # EXISTE no control plane e o chamador nao sabe.
        criados: list[dict[str, str]] = []
        for item in itens or [{"integration": {"id": "integ-piloto-0001"}, "value": [{"content": ""}]}]:
            integracao = (item.get("integration") or {}).get("id") or ""
            texto = ((item.get("value") or [{}])[0]).get("content") or ""
            self._sequencia += 1
            post_id = f"post-{self._sequencia:04d}"
            self.posts[post_id] = PostFake(
                id=post_id, integration=integracao, content=texto,
                state="DRAFT" if tipo == "draft" else "QUEUE",
                publishDate=corpo["date"],
            )
            criados.append({"postId": post_id, "integration": integracao})

        if falha == "500_apos_gravar":
            return httpx.Response(500, json={"message": "internal"})
        if falha == "corpo_ilegivel":
            return httpx.Response(200, content=b"<html>gateway</html>",
                                  headers={"content-type": "text/html"})
        if falha == "sem_post_id":
            return httpx.Response(200, json=[{"integration": criados[0]["integration"]}])

        return httpx.Response(200, json=criados)

    def _listar(self, requisicao: httpx.Request) -> httpx.Response:
        falha, self.falha_na_proxima = self.falha_na_proxima, None
        if falha == "timeout":
            raise httpx.ReadTimeout("timeout injetado", request=requisicao)
        if falha == "500_apos_gravar":
            return httpx.Response(500, json={"message": "internal"})

        params = requisicao.url.params
        if not params.get("startDate") or not params.get("endDate"):
            return httpx.Response(400, json={"message": "startDate and endDate are required"})

        return httpx.Response(200, json={"posts": [
            {
                "id": p.id,
                "content": p.content,
                "state": p.state,
                "publishDate": p.publishDate,
                "releaseURL": p.releaseURL,
                "settings": {},
                "integration": {
                    "id": p.integration,
                    "providerIdentifier": "facebook",
                    "name": "Pagina Piloto",
                    "picture": None,
                },
            }
            for p in self.posts.values()
        ]})

    def _apagar(self, post_id: str) -> httpx.Response:
        if post_id not in self.posts:
            return httpx.Response(404, json={"message": "not found"})
        del self.posts[post_id]
        return httpx.Response(200, json={"id": post_id})


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def adaptador_hermetico(fake: ControlPlaneFake | None = None):
    """O adaptador REAL apontado para o fake. Import tardio de proposito.

    O import mora aqui dentro para que `fake.py` continue importavel num
    ambiente onde o adaptador real ainda nao esteja completo — e para que este
    modulo nunca puxe `httpx.AsyncClient` de producao por acidente.
    """
    from app.publicacao_organica.adaptadores.postiz import AdaptadorPostiz  # noqa: PLC0415

    plano = fake or ControlPlaneFake()
    return AdaptadorPostiz(
        base_url="http://control-plane-de-prova.local",
        token=plano.token,
        permitir_rede_interna=True,   # o host de prova nao resolve; e hermetico
        cliente=plano.cliente(),
    ), plano
