"""O adaptador HTTP real para o Postiz. Nao e importado por nenhum teste de rede.

## O contrato, e a data em que ele foi lido

Tudo aqui vem da documentacao oficial consultada em 02/09/2026:

- https://docs.postiz.com/public-api/introduction
- https://docs.postiz.com/public-api/posts/create
- https://docs.postiz.com/public-api/posts/list
- https://docs.postiz.com/public-api/posts/delete
- https://docs.postiz.com/public-api/integrations/list

O corpo de `POST /posts` exige `type`, `date`, `shortLink`, `tags` e — quando
`type` nao e `draft` — `posts[]` com `{integration:{id}, value:[{content}]}`.
A resposta e `[{postId, integration}]`. `GET /posts` devolve `state` em
`QUEUE|PUBLISHED|ERROR|DRAFT` e `releaseURL`.

⚠️ DIVERGENCIA REGISTRADA, NAO RESOLVIDA POR ADIVINHACAO: a pagina de criacao
diz "limit of 30 requests per hour" e a introducao diz "90 requests per hour
(100 for the cloud) ... only the create post endpoint", ajustavel por
`API_LIMIT` (default 90 na referencia de configuracao). As duas paginas sao
oficiais e discordam. O adaptador trata 429 como falha NAO permanente e nao
assume nenhum dos dois numeros.

## O segredo, e o unico que existe aqui

`POSTIZ_API_TOKEN` — e so ele. Este modulo nao importa `app.config` para
alcancar o Supabase, nao conhece `service_role`, e um teste de contencao
(`test_publicacao_organica_segredos.py`) falha se isso mudar. A regra do ADR
("O Postiz nao recebe a service_role do Supabase") vira controle aqui, e nao
continua sendo linha de markdown.

## SSRF e egresso

`base_url` e conferida contra uma allowlist de esquema e host ANTES da primeira
chamada. Sem isso, uma variavel de ambiente trocada transformaria este adaptador
num proxy para a rede interna — com o token junto.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from datetime import datetime, timezone
from typing import Any, Final
from urllib.parse import urlparse

import httpx

from app.publicacao_organica import dominio as dom
from app.publicacao_organica.portas import (
    Canal,
    DesfechoIncerto,
    FalhaDoControlPlane,
    Prontidao,
    ReciboExterno,
    SolicitacaoExterna,
)

log = logging.getLogger("volc.publicacao_organica.postiz")

#: Traducao do vocabulario do Postiz para o nosso. Um estado que o Postiz
#: acrescentar amanha cai em `DESCONHECIDO` — que e honesto — em vez de virar
#: `PUBLISHED` por um `else` otimista.
_ESTADO_EXTERNO: Final[dict[str, str]] = {
    "DRAFT": "DRAFT",
    "QUEUE": "QUEUE",
    "PUBLISHED": "PUBLISHED",
    "ERROR": "ERROR",
}

_TIMEOUT_PADRAO: Final[float] = 20.0


def _endereco_privado(host: str) -> bool:
    """True quando o host resolve para rede privada, loopback ou link-local."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        # Nao resolveu: nao podemos afirmar que e publico. Fail-closed.
        return True
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:  # pragma: no cover — defensivo
            return True
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


def validar_base_url(base_url: str, *, permitir_rede_interna: bool = False) -> str:
    """Recusa esquema e destino que este adaptador nao deve alcancar.

    ⚠️ `permitir_rede_interna` existe porque a instalacao pretendida do Postiz e
    self-hosted numa rede fechada — `http://postiz:5000` e o caso NORMAL, nao um
    ataque. Mas ele e um SIM explicito por configuracao, e nunca o padrao: sem
    ele, uma `POSTIZ_BASE_URL` trocada por engano (ou de proposito) apontaria o
    token para 169.254.169.254 e este processo entregaria a credencial da nuvem.
    """
    partes = urlparse(base_url)
    if partes.scheme not in ("http", "https"):
        raise FalhaDoControlPlane(
            f"POSTIZ_BASE_URL precisa ser http ou https; recebi '{partes.scheme}'"
        )
    if not partes.hostname:
        raise FalhaDoControlPlane("POSTIZ_BASE_URL sem host")
    if partes.scheme == "http" and not permitir_rede_interna:
        raise FalhaDoControlPlane(
            "POSTIZ_BASE_URL em http exige POSTIZ_PERMITIR_REDE_INTERNA declarado — "
            "token em texto claro so dentro de rede confiavel e por decisao escrita"
        )
    if not permitir_rede_interna and _endereco_privado(partes.hostname):
        raise FalhaDoControlPlane(
            "POSTIZ_BASE_URL aponta para rede privada/loopback e "
            "POSTIZ_PERMITIR_REDE_INTERNA nao foi declarado"
        )
    return base_url.rstrip("/")


class AdaptadorPostiz:
    """Implementa `PortaDePublicacao` contra a API publica oficial."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_s: float = _TIMEOUT_PADRAO,
        permitir_rede_interna: bool = False,
        cliente: httpx.AsyncClient | None = None,
    ) -> None:
        if not token or not token.strip():
            # Fail-closed: um adaptador sem token nao e um adaptador silencioso.
            raise FalhaDoControlPlane("POSTIZ_API_TOKEN ausente neste ambiente")
        self._base = validar_base_url(base_url, permitir_rede_interna=permitir_rede_interna)
        self._token = token.strip()
        self._timeout = timeout_s
        self._permitir_rede_interna = permitir_rede_interna
        # ⚠️ REDIRECT E VETOR DE SSRF, e o `False` aqui e EXPLICITO por isso.
        # Ele ja e o padrao do httpx, mas padrao nao e decisao: um dia alguem
        # troca, e a validacao de destino passa a valer so para o PRIMEIRO salto.
        # Apontado por revisao adversarial cruzada em 02/09/2026.
        if cliente is not None and getattr(cliente, "follow_redirects", False):
            raise FalhaDoControlPlane(
                "o cliente injetado segue redirects; a validacao de destino so "
                "vale para o primeiro salto e o token viajaria junto")
        # `cliente` existe para o E2E hermetico injetar um transporte de teste.
        # Em producao e sempre None, e cada chamada abre e fecha o proprio
        # cliente — como o resto deste backend faz (nenhum pool compartilhado).
        self._cliente = cliente

    # -- infraestrutura -----------------------------------------------------

    def _cabecalhos(self) -> dict[str, str]:
        # A doc oficial mostra o token CRU no header `Authorization`, sem
        # prefixo Bearer. Acrescentar "Bearer " quebraria a autenticacao.
        return {"Authorization": self._token, "Content-Type": "application/json"}

    async def _chamar(self, metodo: str, caminho: str, **kwargs: Any) -> Any:
        # ⚠️ REVALIDACAO A CADA CHAMADA, e nao so na construcao. `validar_base_url`
        # resolve o DNS UMA vez; um nome que resolvia para endereco publico pode
        # passar a resolver para 127.0.0.1 depois (DNS rebinding), e o adaptador
        # entregaria o token para a rede interna. Revalidar nao fecha a janela
        # inteira — entre esta linha e o `connect()` ainda ha um intervalo, e so
        # um transporte com pinagem de IP o fecharia — mas reduz a janela de
        # "horas" (a vida do objeto) para "milissegundos". A limitacao esta
        # declarada em POSTIZ-OPERATIONS.md, e nao escondida.
        validar_base_url(self._base, permitir_rede_interna=self._permitir_rede_interna)
        url = f"{self._base}/public/v1{caminho}"
        try:
            if self._cliente is not None:
                resposta = await self._cliente.request(
                    metodo, url, headers=self._cabecalhos(), timeout=self._timeout, **kwargs
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout,
                                              follow_redirects=False) as cliente:
                    resposta = await cliente.request(
                        metodo, url, headers=self._cabecalhos(), **kwargs
                    )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            # ⚠️ O PEDIDO PODE TER CHEGADO. Esta e a linha que impede um timeout
            # de virar "falhou" e convidar o operador a reenviar.
            log.warning("postiz: desfecho incerto em %s %s: %s", metodo, caminho, type(exc).__name__)
            raise DesfechoIncerto(
                f"o control plane nao respondeu a tempo ({type(exc).__name__}); "
                "o pedido pode ter chegado"
            ) from exc

        if 300 <= resposta.status_code < 400:
            # Com `follow_redirects=False` o 3xx chega ate aqui. Ele NAO e
            # seguido: o destino do `Location` nao passou por `validar_base_url`,
            # e segui-lo levaria o token para um endereco que ninguem conferiu.
            raise FalhaDoControlPlane(
                f"o control plane respondeu {resposta.status_code} (redirect); "
                "este adaptador nao segue redirect — confira POSTIZ_BASE_URL",
                status=resposta.status_code, permanente=True,
            )
        if resposta.status_code >= 500:
            # 5xx depois de o servidor ter recebido o corpo tambem e incerteza:
            # ele pode ter gravado o post e falhado ao responder.
            raise DesfechoIncerto(
                f"o control plane respondeu {resposta.status_code}; o pedido pode ter sido aceito"
            )
        if resposta.status_code == 429:
            raise FalhaDoControlPlane(
                "o control plane recusou por limite de requisicoes; tente mais tarde",
                status=429, permanente=False,
            )
        if resposta.status_code >= 400:
            raise FalhaDoControlPlane(
                dom.sanitizar_erro(
                    f"o control plane recusou ({resposta.status_code}): {resposta.text}"
                ),
                status=resposta.status_code, permanente=True,
            )

        if resposta.status_code == 204 or not resposta.content:
            return None
        try:
            return resposta.json()
        except ValueError as exc:
            # Corpo ilegivel depois de 2xx: pode ter gravado. Incerteza, nao falha.
            raise DesfechoIncerto(
                "o control plane respondeu 2xx com corpo ilegivel"
            ) from exc

    # -- escrita ------------------------------------------------------------

    def _corpo_de_criacao(self, pedido: SolicitacaoExterna, tipo: str) -> dict[str, Any]:
        """Monta o corpo de `POST /posts` exatamente como a doc oficial pede."""
        if tipo == "schedule" and not pedido.instante_utc:
            raise FalhaDoControlPlane("agendar exige instante UTC; o job nao tem um")

        # `date` e obrigatorio no schema mesmo quando `type` e `now` (a doc diz
        # que ele e IGNORADO nesse caso). Mandar o agora evita um 400 por campo
        # ausente sem afirmar um agendamento que nao existe.
        data = pedido.instante_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        corpo: dict[str, Any] = {
            "type": tipo,
            "date": data,
            "shortLink": False,
            "tags": [],
        }
        # ⚠️ `posts` e obrigatorio quando `type` != 'draft', e a doc permite
        # omitir no draft. Mandamos sempre: um draft sem conteudo nao serve de
        # rascunho para ninguem, e o Postiz o aceita.
        corpo["posts"] = [{
            "integration": {"id": pedido.referencia_do_canal},
            "value": [{
                "content": pedido.texto,
                **({"image": [{"path": u} for u in pedido.imagens]} if pedido.imagens else {}),
            }],
            **({"settings": {"__type": pedido.plataforma}} if pedido.plataforma else {}),
        }]
        return corpo

    async def _criar(self, pedido: SolicitacaoExterna, tipo: str) -> ReciboExterno:
        bruto = await self._chamar("POST", "/posts", json=self._corpo_de_criacao(pedido, tipo))

        # A resposta documentada e `[{postId, integration}]`. Uma resposta que
        # nao tem `postId` NAO vira sucesso vazio: sem referencia externa nao ha
        # recibo, e a funcao governada recusaria de qualquer forma.
        itens = bruto if isinstance(bruto, list) else [bruto] if isinstance(bruto, dict) else []
        externo = next(
            (str(i.get("postId")) for i in itens
             if isinstance(i, dict) and i.get("postId")), None)
        if not externo:
            raise DesfechoIncerto(
                "o control plane respondeu sem identificador de post; "
                "o conteudo pode ter sido criado"
            )

        sanitizado = _sanitizar_corpo({"resposta": itens, "tipo": tipo})
        estado = {"draft": "DRAFT", "schedule": "QUEUE", "now": "QUEUE"}[tipo]
        return ReciboExterno(
            referencia_externa=externo,
            estado_externo=estado,
            bruto=sanitizado,
        )

    async def criar_rascunho(self, pedido: SolicitacaoExterna) -> ReciboExterno:
        return await self._criar(pedido, "draft")

    async def agendar(self, pedido: SolicitacaoExterna) -> ReciboExterno:
        return await self._criar(pedido, "schedule")

    async def publicar_agora(self, pedido: SolicitacaoExterna) -> ReciboExterno:
        return await self._criar(pedido, "now")

    # -- leitura ------------------------------------------------------------

    async def consultar(self, referencia_externa: str, *,
                        janela_horas: int = 168) -> ReciboExterno | None:
        """Encontra o post pela LISTA — porque nao existe busca por id.

        A doc oficial nao documenta `GET /posts/{id}`. A consulta e por janela de
        data e devolve `posts[]`; filtramos aqui pela referencia que ja temos.
        Inventar `/posts/{id}` daria 404 em producao e um diagnostico errado.
        """
        agora = datetime.now(timezone.utc)
        inicio = agora.timestamp() - janela_horas * 3600
        params = {
            "startDate": datetime.fromtimestamp(inicio, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            # A janela vai para a FRENTE tambem: um post agendado para amanha
            # esta no futuro, e uma janela que termina agora nao o encontraria.
            "endDate": datetime.fromtimestamp(agora.timestamp() + janela_horas * 3600,
                                              timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        bruto = await self._chamar("GET", "/posts", params=params)

        posts = bruto.get("posts") if isinstance(bruto, dict) else bruto
        if not isinstance(posts, list):
            raise DesfechoIncerto("o control plane respondeu a consulta em forma inesperada")

        achado = next(
            (p for p in posts
             if isinstance(p, dict) and str(p.get("id")) == str(referencia_externa)), None)
        if achado is None:
            # ⚠️ NAO ENCONTRAR NAO E FALHA E NAO APAGA NADA. Devolvemos None e
            # quem chamou mantem o estado. Doutrina de publicacao.py:1112.
            return None

        estado = _ESTADO_EXTERNO.get(str(achado.get("state", "")).upper(), "DESCONHECIDO")
        url = achado.get("releaseURL") or None
        publicado = achado.get("publishDate") if estado == "PUBLISHED" else None
        return ReciboExterno(
            referencia_externa=str(achado.get("id")),
            estado_externo=estado,
            url_publicada=str(url) if url else None,
            publicado_em=str(publicado) if publicado else None,
            bruto=_sanitizar_corpo({"post": achado}),
        )

    async def cancelar(self, referencia_externa: str) -> bool:
        """`DELETE /posts/{id}`. ⚠️ A doc diz que apaga TODOS do mesmo grupo."""
        await self._chamar("DELETE", f"/posts/{referencia_externa}")
        return True

    async def listar_canais(self) -> list[Canal]:
        bruto = await self._chamar("GET", "/integrations")
        if not isinstance(bruto, list):
            raise DesfechoIncerto("o control plane respondeu integracoes em forma inesperada")
        canais: list[Canal] = []
        for item in bruto:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            canais.append(Canal(
                referencia_externa=str(item["id"]),
                nome=str(item.get("name") or ""),
                plataforma=str(item.get("identifier") or ""),
                perfil=str(item["profile"]) if item.get("profile") else None,
                desativado=bool(item.get("disabled")),
            ))
        return canais

    async def prontidao(self) -> Prontidao:
        """⚠️ PROXY, e o resultado diz isso.

        A API publica do Postiz nao documenta endpoint de health. `GET
        /integrations` e a chamada autenticada de menor efeito colateral, e por
        isso serve de sonda — mas chamar o resultado de "health check" seria
        afirmar uma capacidade que a API nao oferece.
        """
        try:
            canais = await self.listar_canais()
        except (FalhaDoControlPlane, DesfechoIncerto) as exc:
            return Prontidao(
                pronto=False, fonte="proxy:/integrations",
                detalhe=dom.sanitizar_erro(str(exc)),
            )
        return Prontidao(
            pronto=True, fonte="proxy:/integrations",
            detalhe="a API respondeu a listagem de integracoes; nao ha endpoint "
                    "de health oficial nesta versao do Postiz",
            canais_visiveis=len(canais),
        )


def _sanitizar_corpo(documento: Any) -> dict[str, Any]:
    """Poda o corpo do provedor para o que cabe num recibo, e recusa segredo.

    Duas coisas acontecem aqui, e as duas importam:
      1. campos de material de credencial derrubam a construcao do recibo
         (`dominio.recusar_chave_sensivel` RECUSA, nao remove — remover faria
         quem chamou acreditar que gravou o que mandou);
      2. o documento e reduzido: um corpo de provedor inteiro nao cabe numa
         coluna e nao ajuda ninguem seis meses depois.
    """
    podado = _podar(documento, profundidade=0)
    if not isinstance(podado, dict):
        podado = {"resposta": podado}
    dom.recusar_chave_sensivel(podado, "recibo-externo")
    return podado


def _podar(valor: Any, *, profundidade: int) -> Any:
    if profundidade > 4:
        return "[profundidade cortada]"
    if isinstance(valor, dict):
        return {str(k): _podar(v, profundidade=profundidade + 1)
                for k, v in list(valor.items())[:30]}
    if isinstance(valor, (list, tuple)):
        return [_podar(v, profundidade=profundidade + 1) for v in list(valor)[:10]]
    if isinstance(valor, str):
        return dom.sanitizar_erro(valor) if len(valor) > 200 else valor
    if isinstance(valor, (int, float, bool)) or valor is None:
        return valor
    return str(valor)[:200]
