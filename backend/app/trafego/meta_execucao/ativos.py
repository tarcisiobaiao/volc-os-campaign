"""Read-only resolver for account-scoped assets used by the PAUSED recipe."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx

from app.trafego.meta import dominio as dom
from app.trafego.meta.adaptador import AdaptadorMetaSomenteLeitura, ErroDeLeituraMeta
from app.trafego.meta.credenciais import SegredoEfemero

from .contrato import ErroDeNascimentoMeta, ReferenciasMetaResolvidas


@dataclass(frozen=True)
class AtivoDeCriacaoMeta:
    referencia_opaca: str
    nome: str
    tipo: str
    id_mascarado: str | None = None
    largura: int | None = None
    altura: int | None = None
    preview_disponivel: bool = False

    def publico(self) -> Mapping[str, Any]:
        return {
            "referencia_opaca": self.referencia_opaca,
            "nome": self.nome,
            "tipo": self.tipo,
            "id_mascarado": self.id_mascarado,
            "largura": self.largura,
            "altura": self.altura,
            "preview_disponivel": self.preview_disponivel,
        }


@dataclass(frozen=True, repr=False)
class _AtivoResolvido:
    publico: AtivoDeCriacaoMeta
    id_externo: str
    preview_url: str | None = None

    def __repr__(self) -> str:
        return "_AtivoResolvido(<oculto>)"


class ResolvedorAtivosMeta:
    def __init__(self, cliente: httpx.AsyncClient, *, max_paginas: int = 20) -> None:
        self._cliente = cliente
        self._max_paginas = max_paginas
        self._leitor = AdaptadorMetaSomenteLeitura(
            cliente, api_version="v26.0", max_paginas_por_edge=max_paginas)

    async def _conta(self, account_ref: str, segredo: SegredoEfemero) -> dom.ContaMetaDescoberta:
        contas = await self._leitor.descobrir_contas(segredo)
        try:
            conta = self._leitor.resolver_referencia_opaca(contas, account_ref)
        except dom.ContratoMetaInvalido as exc:
            raise ErroDeNascimentoMeta("META_ACCOUNT_REFERENCE_UNKNOWN", str(exc)) from None
        if conta.status != "1":
            raise ErroDeNascimentoMeta(
                "META_ACCOUNT_NOT_ACTIVE", "a conta Meta selecionada nao esta ativa")
        if conta.moeda != "BRL":
            raise ErroDeNascimentoMeta(
                "META_CURRENCY_UNSUPPORTED", "o primeiro canario aceita somente conta BRL")
        return conta

    async def _listar(
        self,
        url: str,
        segredo: SegredoEfemero,
        *,
        fields: str,
    ) -> list[Mapping[str, Any]]:
        cursor: str | None = None
        saida: list[Mapping[str, Any]] = []
        for _ in range(self._max_paginas):
            params: dict[str, Any] = {"fields": fields, "limit": 100}
            if cursor:
                params["after"] = cursor
            try:
                resposta = await self._cliente.get(
                    url,
                    params=params,
                    headers={"Authorization": segredo.cabecalho_bearer()},
                )
            except httpx.HTTPError:
                raise ErroDeNascimentoMeta(
                    "META_ASSET_READ_FAILED", "nao foi possivel ler os ativos Meta") from None
            if resposta.status_code >= 400:
                raise ErroDeNascimentoMeta(
                    "META_ASSET_READ_FAILED",
                    f"a Meta recusou a leitura de ativos (HTTP {resposta.status_code})",
                )
            try:
                corpo = resposta.json()
            except ValueError:
                corpo = None
            if not isinstance(corpo, Mapping) or not isinstance(corpo.get("data"), list):
                raise ErroDeNascimentoMeta(
                    "META_ASSET_RESPONSE_INVALID", "a Meta devolveu inventario de ativos invalido")
            for item in corpo["data"]:
                if isinstance(item, Mapping):
                    saida.append(item)
            paging = corpo.get("paging")
            if not isinstance(paging, Mapping) or not paging.get("next"):
                return saida
            cursors = paging.get("cursors")
            proximo = cursors.get("after") if isinstance(cursors, Mapping) else None
            if not isinstance(proximo, str) or not proximo or proximo == cursor:
                raise ErroDeNascimentoMeta(
                    "META_ASSET_PAGINATION_INVALID", "a paginacao dos ativos Meta nao avancou")
            cursor = proximo
        raise ErroDeNascimentoMeta(
            "META_ASSET_PAGINATION_LIMIT", "o inventario de ativos excedeu o limite seguro")

    async def _inventario_interno(
        self, account_ref: str, segredo: SegredoEfemero,
    ) -> tuple[dom.ContaMetaDescoberta, list[_AtivoResolvido], list[_AtivoResolvido]]:
        try:
            conta = await self._conta(account_ref, segredo)
        except ErroDeLeituraMeta as exc:
            raise ErroDeNascimentoMeta(exc.codigo, exc.mensagem_segura) from None
        base = f"https://graph.facebook.com/v26.0/act_{conta.id_externo}"
        paginas_raw = await self._listar(
            f"{base}/promote_pages", segredo, fields="id,name")
        imagens_raw = await self._listar(
            f"{base}/adimages", segredo, fields="hash,name,width,height,url_128,url")
        paginas: list[_AtivoResolvido] = []
        for item in paginas_raw:
            try:
                externo = dom.id_externo(item.get("id"), campo="page.id")
            except dom.ContratoMetaInvalido:
                continue
            paginas.append(_AtivoResolvido(
                publico=AtivoDeCriacaoMeta(
                    referencia_opaca=dom.referencia_opaca_objeto(
                        conta.id_externo, "page", externo),
                    nome=dom.texto_opcional(item.get("name")) or "Pagina sem nome",
                    tipo="page",
                    id_mascarado=dom.mascarar_id(externo),
                ),
                id_externo=externo,
            ))
        imagens: list[_AtivoResolvido] = []
        for item in imagens_raw:
            image_hash = str(item.get("hash") or "").strip()
            if not image_hash:
                continue
            preview_url = str(item.get("url_128") or item.get("url") or "").strip() or None
            # image hashes are not numeric, so the opaque handle is derived
            # from a stable digest and never exposes the provider hash.
            digest = hashlib.sha256(
                f"META_ADS:{conta.id_externo}:image_asset:{image_hash}".encode("utf-8")
            ).hexdigest()[:24]
            imagens.append(_AtivoResolvido(
                publico=AtivoDeCriacaoMeta(
                    referencia_opaca=f"metaasset_{digest}",
                    nome=dom.texto_opcional(item.get("name")) or "Imagem sem nome",
                    tipo="image_asset",
                    largura=_inteiro_opcional(item.get("width")),
                    altura=_inteiro_opcional(item.get("height")),
                    preview_disponivel=preview_url is not None,
                ),
                id_externo=image_hash,
                preview_url=preview_url,
            ))
        return conta, paginas, imagens

    async def inventariar(
        self, account_ref: str, segredo: SegredoEfemero,
    ) -> Mapping[str, Any]:
        conta, paginas, imagens = await self._inventario_interno(account_ref, segredo)
        return {
            "ok": True,
            "api_version": "v26.0",
            "account_ref": conta.referencia_opaca,
            "conta": conta.publico(),
            "paginas": [item.publico.publico() for item in paginas],
            "imagens": [item.publico.publico() for item in imagens],
            "receita": "OUTCOME_TRAFFIC_WEBSITE_LPV_STATIC_PAUSED",
        }

    async def resolver(
        self,
        *,
        account_ref: str,
        page_ref: str,
        asset_ref: str,
        segredo: SegredoEfemero,
    ) -> ReferenciasMetaResolvidas:
        return await self.resolver_lote(
            account_ref=account_ref,
            page_ref=page_ref,
            asset_refs=(asset_ref,),
            segredo=segredo,
        )

    async def resolver_lote(
        self,
        *,
        account_ref: str,
        page_ref: str,
        asset_refs: Sequence[str],
        segredo: SegredoEfemero,
    ) -> ReferenciasMetaResolvidas:
        referencias = tuple(dict.fromkeys(str(item or "").strip() for item in asset_refs))
        if not referencias or len(referencias) > 10 or any(not item for item in referencias):
            raise ErroDeNascimentoMeta(
                "META_STATIC_BATCH_INVALID",
                "o lote precisa declarar entre 1 e 10 referencias de imagem",
            )
        conta, paginas, imagens = await self._inventario_interno(account_ref, segredo)
        pagina = next((item for item in paginas if item.publico.referencia_opaca == page_ref), None)
        if pagina is None:
            raise ErroDeNascimentoMeta(
                "META_PAGE_REFERENCE_UNKNOWN", "a pagina nao pertence a conta Meta selecionada")
        imagens_por_ref = {item.publico.referencia_opaca: item for item in imagens}
        faltantes = [referencia for referencia in referencias if referencia not in imagens_por_ref]
        if faltantes:
            raise ErroDeNascimentoMeta(
                "META_ASSET_REFERENCE_UNKNOWN",
                "uma imagem do lote nao pertence a conta Meta selecionada",
            )
        primeira = imagens_por_ref[referencias[0]]
        return ReferenciasMetaResolvidas(
            account_id=conta.id_externo,
            page_id=pagina.id_externo,
            image_hash=primeira.id_externo,
            image_hashes_by_ref={
                referencia: imagens_por_ref[referencia].id_externo
                for referencia in referencias
            },
        )

    async def preview_url(
        self,
        *,
        account_ref: str,
        asset_ref: str,
        segredo: SegredoEfemero,
    ) -> str:
        _, _, imagens = await self._inventario_interno(account_ref, segredo)
        imagem = next(
            (item for item in imagens if item.publico.referencia_opaca == asset_ref), None)
        if imagem is None:
            raise ErroDeNascimentoMeta(
                "META_ASSET_REFERENCE_UNKNOWN", "a imagem nao pertence a conta Meta selecionada")
        if not imagem.preview_url:
            raise ErroDeNascimentoMeta(
                "META_ASSET_PREVIEW_UNAVAILABLE", "a Meta nao devolveu previa para esta imagem")
        return imagem.preview_url


def _inteiro_opcional(valor: Any) -> int | None:
    if valor in (None, ""):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None
