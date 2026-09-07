"""Read-only resolver for account-scoped assets used by the PAUSED recipe."""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import httpx

from app.trafego.meta import dominio as dom
from app.trafego.meta.adaptador import AdaptadorMetaSomenteLeitura, ErroDeLeituraMeta
from app.trafego.meta.credenciais import SegredoEfemero

from .contrato import (
    DESTINO_SHOP_NAO_PROVADO,
    ORIGEM_BIBLIOTECA,
    ORIGEM_MINIATURA,
    PROVAS_DE_DESTINO_WEBSITE,
    DeclaracaoPoliticaAtivoMeta,
    ErroDeNascimentoMeta,
    ManifestoSupplyMeta,
    ReferenciasMetaResolvidas,
)


#: Teto de bytes do corpo. Cobrado DURANTE a leitura, não depois: um corpo de
#: 4 GiB não pode ser carregado inteiro na memória para só então ser recusado
#: por tamanho.
LIMITE_DE_BYTES = 12_000_000

#: Teto de pixels DECLARADOS no cabeçalho, cobrado ANTES de decodificar.
#:
#: ⚠️ O limite de bytes não alcança este ataque, e a diferença é medida: um PNG
#: branco de 12000x12000 ocupa ~157 KiB comprimido — passa folgado no teto de
#: bytes — e declara 144 milhões de pixels, que a decodificação materializaria
#: como centenas de MiB de memória. Por isso a dimensão é lida do cabeçalho
#: (`Image.open` é preguiçoso) e julgada antes de qualquer `load()`.
LIMITE_DE_PIXELS = 40_000_000

#: Formatos que esta receita aceita, do nome do decodificador para o MIME
#: canônico. Vocabulário fechado: o que o decodificador reconhecer fora desta
#: lista é recusado, não traduzido por adivinhação.
FORMATOS_ACEITOS: Mapping[str, str] = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}

#: Versão da matéria canônica do recibo de supply. Entra no hash: mudar a forma
#: do recibo sem mudar a versão faria dois recibos diferentes colidirem.
VERSAO_DO_RECIBO_DE_SUPPLY = "meta-supply-v2"

#: A finalidade a que o recibo se vincula. Não é decoração: um recibo emitido
#: para inspeção interna não autoriza mídia paga, e o campo é o que permite
#: recusar essa confusão por nome.
FINALIDADE_DO_RECIBO = "PAID_MEDIA_META_FACEBOOK"


@dataclass(frozen=True)
class MedidaDaPeca:
    """O que os BYTES revelaram — nunca o que o inventário declarou."""

    mime: str
    largura: int
    altura: int
    bytes_totais: int
    content_sha256: str


def _decodificar_imagem(conteudo: bytes) -> tuple[str, int, int]:
    """Decodifica de verdade e devolve (mime, largura, altura).

    ## Por que o cabeçalho `Content-Type` não bastava

    O gate anterior lia `Content-Type`, conferia o tamanho total e hasheava. O
    cabeçalho é uma AFIRMAÇÃO de quem serve os bytes; ele não é os bytes. Um
    corpo com o literal ``NOT_AN_IMAGE`` rotulado ``image/png`` era selado como
    `AUTHORIZED` / `READY_FOR_PAID_MEDIA`, e o recibo passava a afirmar uma
    inspeção que nunca aconteceu. Esse é o defeito F01, reproduzido
    hermeticamente pelo probe P02 do pacote.

    ## A ordem das perguntas, e por que ela é essa

    1. ABRIR. `Image.open` lê só o cabeçalho. Se os bytes não forem uma imagem
       reconhecível, ele levanta aqui — antes de qualquer alocação grande.
    2. MEDIR E JULGAR O TAMANHO. `size` sai do cabeçalho, sem decodificar. É
       aqui que a bomba de descompressão morre: declarar 144 milhões de pixels
       custa 157 KiB no fio e centenas de MiB na memória.
    3. DECODIFICAR. Só depois de o tamanho ser aceitável é que `load()` desenha
       os pixels. É o que separa "tem cabeçalho de PNG" de "é um PNG inteiro":
       um arquivo truncado abre e mede, mas não carrega.

    ⚠️ O que isto prova é FORMA, nunca CONTEÚDO. Que os bytes são uma imagem
    real destas dimensões — não que ela esteja livre de marca, logotipo ou
    identidade de terceiro. Essa é outra pergunta, feita pela atestação humana,
    e nenhuma das duas substitui a outra.
    """
    try:  # pragma: no cover - ausência de Pillow é falha de ambiente, não de dados
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        # ⚠️ FECHA. Sem decodificador não existe gate técnico, e responder
        # "CLEAR por falta de motor" seria exatamente a mentira que o gate
        # existe para impedir.
        raise ErroDeNascimentoMeta(
            "META_ASSET_DECODER_UNAVAILABLE",
            "o decodificador de imagem não está disponível neste servidor; "
            "a peça não pode ser conferida",
        ) from exc

    import warnings

    bomba = ErroDeNascimentoMeta(
        "META_ASSET_PIXELS_EXCEEDED",
        "a peça declara mais pixels do que este servidor decodifica com segurança")

    try:
        with warnings.catch_warnings():
            # ⚠️ O aviso de bomba do Pillow é SILENCIADO de propósito, e o teto
            # que decide é o desta receita (LIMITE_DE_PIXELS), não o padrão da
            # biblioteca. Deixar o aviso virar exceção aqui faria uma bomba ser
            # reportada como "não decodificável" — causa errada para o
            # operador, e um limite que muda quando o Pillow muda.
            #
            # O erro DURO do Pillow continua valendo: ele dispara acima do
            # dobro do limite padrão e é traduzido para o mesmo código nomeado.
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(conteudo)) as cabecalho:
                formato = str(cabecalho.format or "")
                largura, altura = cabecalho.size
    except Image.DecompressionBombError as exc:
        raise bomba from exc
    except ErroDeNascimentoMeta:
        raise
    except Exception as exc:
        raise ErroDeNascimentoMeta(
            "META_ASSET_BYTES_NOT_DECODABLE",
            "os bytes da peça não são uma imagem decodificável",
        ) from exc

    if formato not in FORMATOS_ACEITOS:
        raise ErroDeNascimentoMeta(
            "META_ASSET_FORMAT_UNSUPPORTED",
            "o formato da peça não pertence aos formatos aceitos nesta receita")
    if largura <= 0 or altura <= 0:
        # Cabeçalho corrompido ou sintético. Zero não é medida.
        raise ErroDeNascimentoMeta(
            "META_ASSET_BYTES_NOT_DECODABLE",
            "o cabeçalho da peça não trouxe dimensão utilizável")
    if largura * altura > LIMITE_DE_PIXELS:
        raise bomba

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(conteudo)) as imagem:
                # AGORA sim os pixels são desenhados. Um arquivo truncado abre,
                # mede e falha aqui — que é o ponto. E chegar até aqui já provou
                # que a dimensão cabe no teto desta receita.
                imagem.load()
                if imagem.size != (largura, altura):
                    raise ErroDeNascimentoMeta(
                        "META_ASSET_BYTES_NOT_DECODABLE",
                        "a dimensão decodificada não confere com o cabeçalho da peça")
    except Image.DecompressionBombError as exc:  # pragma: no cover - o teto já barrou
        raise bomba from exc
    except ErroDeNascimentoMeta:
        raise
    except Exception as exc:
        raise ErroDeNascimentoMeta(
            "META_ASSET_BYTES_TRUNCATED",
            "os bytes da peça não decodificam por inteiro",
        ) from exc

    return FORMATOS_ACEITOS[formato], largura, altura


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
    #: Qual URL a biblioteca deu. `url` é a peça; `url_128` é miniatura — e o
    #: manifesto precisa dizer qual delas foi medida.
    origem_dos_bytes: str = ORIGEM_BIBLIOTECA

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
    ) -> tuple[
        dom.ContaMetaDescoberta,
        list[_AtivoResolvido],
        list[_AtivoResolvido],
        list[_AtivoResolvido],
        str | None,
    ]:
        try:
            conta = await self._conta(account_ref, segredo)
        except ErroDeLeituraMeta as exc:
            raise ErroDeNascimentoMeta(exc.codigo, exc.mensagem_segura) from None
        base = f"https://graph.facebook.com/v26.0/act_{conta.id_externo}"
        paginas_raw = await self._listar(
            f"{base}/promote_pages", segredo, fields="id,name")
        imagens_raw = await self._listar(
            f"{base}/adimages", segredo, fields="hash,name,width,height,url_128,url")
        # ⚠️ O inventário de vídeo é ACESSÓRIO e não pode derrubar a receita
        # estática. Um token sem permissão de leitura de vídeo, ou uma edge
        # indisponível, não podem impedir compilar e validar uma campanha feita
        # só de imagens. A indisponibilidade vira lista vazia e é declarada
        # separadamente por `videos_indisponiveis`.
        #
        # Somente campos comprovados na referência oficial do nó Video: o título
        # se chama `name`, e `status` não aparece entre os campos legíveis desta
        # edge — por isso a prontidão do vídeo não é afirmada aqui.
        # https://developers.facebook.com/docs/marketing-api/reference/video/
        videos_indisponivel: str | None = None
        try:
            videos_raw = await self._listar(
                f"{base}/advideos", segredo,
                fields="id,name,created_time,updated_time,picture")
        except ErroDeNascimentoMeta as exc:
            videos_raw = []
            videos_indisponivel = exc.codigo
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
            # `url` representa a peça da biblioteca; `url_128` é apenas a
            # miniatura. O manifesto de conteúdo nunca pode hashear a miniatura
            # e afirmar que ela são os bytes aprovados do image_hash.
            #
            # ⚠️ Quando só a miniatura existe, os bytes ainda são lidos e
            # medidos — mas o manifesto DECLARA que a medida é da miniatura.
            # Ler e mentir sobre a origem seria pior que não ler.
            da_biblioteca = str(item.get("url") or "").strip()
            preview_url = da_biblioteca or str(item.get("url_128") or "").strip() or None
            origem = ORIGEM_BIBLIOTECA if da_biblioteca else ORIGEM_MINIATURA
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
                origem_dos_bytes=origem,
            ))
        videos: list[_AtivoResolvido] = []
        for item in videos_raw:
            try:
                externo = dom.id_externo(item.get("id"), campo="video.id")
            except dom.ContratoMetaInvalido:
                continue
            thumb = str(item.get("picture") or "").strip() or None
            videos.append(_AtivoResolvido(
                publico=AtivoDeCriacaoMeta(
                    referencia_opaca=dom.referencia_opaca_objeto(
                        conta.id_externo, "video", externo),
                    nome=dom.texto_opcional(item.get("name")) or "Vídeo sem nome",
                    tipo="video_asset",
                    id_mascarado=dom.mascarar_id(externo),
                    preview_disponivel=thumb is not None,
                ),
                id_externo=externo,
                preview_url=thumb,
            ))
        return conta, paginas, imagens, videos, videos_indisponivel

    async def inventariar(
        self, account_ref: str, segredo: SegredoEfemero,
    ) -> Mapping[str, Any]:
        conta, paginas, imagens, videos, videos_indisponivel = await self._inventario_interno(
            account_ref, segredo)
        return {
            "ok": True,
            "api_version": "v26.0",
            "account_ref": conta.referencia_opaca,
            "conta": conta.publico(),
            "paginas": [item.publico.publico() for item in paginas],
            "imagens": [item.publico.publico() for item in imagens],
            "videos": [item.publico.publico() for item in videos],
            # `null` = leitura de vídeo bem-sucedida. Um código aqui declara que
            # a lista está vazia por falha de leitura, não por ausência de peça.
            "videos_indisponiveis": videos_indisponivel,
            "receita": "OUTCOME_TRAFFIC_LPV_STATIC_PAUSED",
        }

    async def resolver(
        self,
        *,
        account_ref: str,
        page_ref: str,
        asset_ref: str,
        segredo: SegredoEfemero,
        ator: str,
        prova_de_destino: str = DESTINO_SHOP_NAO_PROVADO,
    ) -> ReferenciasMetaResolvidas:
        return await self.resolver_lote(
            account_ref=account_ref,
            page_ref=page_ref,
            asset_refs=(asset_ref,),
            segredo=segredo,
            ator=ator,
            prova_de_destino=prova_de_destino,
        )

    async def resolver_lote(
        self,
        *,
        account_ref: str,
        page_ref: str,
        asset_refs: Sequence[str],
        segredo: SegredoEfemero,
        ator: str,
        declaracoes: Mapping[str, DeclaracaoPoliticaAtivoMeta] | None = None,
        prova_de_destino: str = DESTINO_SHOP_NAO_PROVADO,
    ) -> ReferenciasMetaResolvidas:
        """Resolve conta, Página e peças. NÃO inventa a prova de destino.

        ⚠️ `prova_de_destino` nasce `UNPROVEN` e o resolvedor NUNCA a promove
        sozinho. Não existe, na evidência oficial desta lane, uma leitura
        estabelecida que prove que o clique da conta não pode ser redirecionado
        para uma Shop: `OFFICIAL-META-API-EVIDENCE.json` marca a fonte
        `META-SHOP` como `RESEARCH_REQUIRED` e `remote_behavior_proven: false`.

        Ler uma aresta inventada e chamar o silêncio dela de prova seria a
        mesma falha que o resto deste módulo evita em `videos_indisponiveis`:
        confundir "não consegui ler" com "não existe". Enquanto a leitura
        oficial não for estabelecida, quem chama fica com `UNPROVEN`, a
        compilação e o `validate_only` continuam abertos e apenas o DESPACHO é
        recusado — que é exatamente o que C01 manda.
        """
        if prova_de_destino not in PROVAS_DE_DESTINO_WEBSITE:
            raise ErroDeNascimentoMeta(
                "META_SHOP_REDIRECT_PROOF_INVALID",
                "a prova de destino website-only não pertence ao vocabulário fechado",
            )
        referencias = tuple(dict.fromkeys(str(item or "").strip() for item in asset_refs))
        if not referencias or len(referencias) > 10 or any(not item for item in referencias):
            raise ErroDeNascimentoMeta(
                "META_STATIC_BATCH_INVALID",
                "o lote precisa declarar entre 1 e 10 referencias de imagem",
            )
        conta, paginas, imagens, _, _ = await self._inventario_interno(account_ref, segredo)
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
        declaracoes = dict(declaracoes or {})
        if set(declaracoes) != set(referencias):
            raise ErroDeNascimentoMeta(
                "META_ASSET_POLICY_RECEIPT_MISSING",
                "cada peça do lote precisa de confirmação própria de direitos e identidade",
            )
        manifestos: dict[str, ManifestoSupplyMeta] = {}
        for referencia in referencias:
            manifestos[referencia] = await self._manifestar_imagem(
                imagens_por_ref[referencia], declaracoes[referencia],
                # ⚠️ A conta é a REFERÊNCIA OPACA já resolvida, e o ator vem da
                # sessão do servidor. Nenhum dos dois pode chegar pelo corpo do
                # pedido: quem quer subir a campanha não assina a própria
                # autorização.
                account_ref=conta.referencia_opaca,
                ator=ator,
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
            page_permission_proven=True,
            placement_identity_mode="FACEBOOK_ONLY_PAGE_PROVEN",
            shop_redirect_proof=prova_de_destino,
            asset_supply_manifests=manifestos,
        )

    async def _ler_bytes_da_peca(self, ativo: _AtivoResolvido) -> tuple[bytes, str]:
        """Baixa os bytes com teto cobrado DURANTE a leitura.

        ⚠️ A versão anterior fazia `await cliente.get(url)` e só então conferia
        `len(conteudo) > 12_000_000`. Nessa ordem o corpo inteiro já está na
        memória quando o limite é aplicado: o teto protegia o resto do sistema,
        não este processo. Aqui a leitura é interrompida no pedaço que
        ultrapassa o teto, e o que veio antes é descartado.

        O redirecionamento também deixa de ser silencioso. Um 3xx tem status
        abaixo de 400 e corpo vazio, então a checagem antiga o rejeitava como
        "imagem inválida" — mensagem errada para a causa real, e uma que o
        operador não consegue agir.
        """
        if not ativo.preview_url:
            raise ErroDeNascimentoMeta(
                "META_ASSET_BYTES_UNAVAILABLE",
                "a biblioteca Meta não devolveu uma URL para conferir os bytes da peça",
            )
        partes = urlparse(ativo.preview_url)
        host = (partes.hostname or "").lower()
        if partes.scheme != "https" or not host.endswith(".fbcdn.net"):
            raise ErroDeNascimentoMeta(
                "META_ASSET_BYTES_HOST_REJECTED",
                "os bytes da peça não vieram do CDN Meta permitido",
            )
        pedacos: list[bytes] = []
        total = 0
        try:
            async with self._cliente.stream("GET", ativo.preview_url) as resposta:
                if 300 <= resposta.status_code < 400:
                    # Seguir o desvio levaria os bytes para fora da allowlist
                    # que acabou de ser conferida.
                    raise ErroDeNascimentoMeta(
                        "META_ASSET_BYTES_REDIRECT_REFUSED",
                        "a leitura dos bytes da peça foi redirecionada para fora do CDN permitido",
                    )
                if resposta.status_code >= 400:
                    raise ErroDeNascimentoMeta(
                        "META_ASSET_BYTES_READ_FAILED",
                        "o CDN Meta recusou a leitura dos bytes da peça",
                    )
                tipo = resposta.headers.get("content-type", "").split(";", 1)[0].lower()
                async for pedaco in resposta.aiter_bytes():
                    total += len(pedaco)
                    if total > LIMITE_DE_BYTES:
                        raise ErroDeNascimentoMeta(
                            "META_ASSET_BYTES_TOO_LARGE",
                            "os bytes da peça excedem o limite seguro deste servidor",
                        )
                    pedacos.append(pedaco)
        except ErroDeNascimentoMeta:
            raise
        except httpx.HTTPError:
            raise ErroDeNascimentoMeta(
                "META_ASSET_BYTES_READ_FAILED", "não foi possível ler os bytes da peça") from None
        conteudo = b"".join(pedacos)
        if not conteudo:
            raise ErroDeNascimentoMeta(
                "META_ASSET_BYTES_EMPTY", "o CDN Meta devolveu um corpo vazio para a peça")
        return conteudo, tipo

    async def _manifestar_imagem(
        self,
        ativo: _AtivoResolvido,
        declaracao: DeclaracaoPoliticaAtivoMeta,
        *,
        account_ref: str,
        ator: str,
    ) -> ManifestoSupplyMeta:
        """Lê os bytes, DECODIFICA e sela a correspondência peça↔image_hash.

        ## O que mudou, e por quê

        Antes o gate lia `Content-Type`, conferia tamanho e hasheava — e o
        recibo dizia `AUTHORIZED` / `READY_FOR_PAID_MEDIA` sobre bytes que
        ninguém tinha aberto. Agora a imagem é decodificada de verdade
        (`_decodificar_imagem`) e as dimensões vêm da MEDIÇÃO. As dimensões que
        a biblioteca declara continuam viajando ao lado, para que a divergência
        seja visível — mas elas não substituem mais a medida.

        ## O recibo é do SERVIDOR, e a quem ele se vincula

        Ator e conta entram na matéria canônica. Sem eles o recibo descreveria
        só "estes bytes foram vistos alguma vez", e um recibo assim não sabe
        dizer *quem* atestou nem *sobre qual conta*. A identidade do ator vem da
        sessão, nunca do corpo do pedido: quem quer subir a campanha não pode
        assinar a própria autorização.

        ⚠️ Copy e destino NÃO entram aqui, e a ausência é deliberada: eles já são
        selados pelo `plano_sha256`, que cobre os payloads inteiros. Repeti-los
        no recibo de supply criaria um segundo recibo por variação para a mesma
        peça — e o compilador emite um manifesto por `asset_ref`, não por texto.
        A invalidação por mudança de copy continua acontecendo, pelo hash do
        plano, e há contraprova disso.

        ## Estabilidade

        `policy_receipt_ref` é DERIVADO da matéria: mesma peça, mesmo ator,
        mesma conta e mesma atestação produzem sempre a mesma referência.
        Compilar, validar e aprovar reusam o mesmo recibo, e por isso o hash do
        plano não muda entre os três atos. Nenhum `now()` entra aqui — um
        carimbo novo a cada chamada mudaria o plano validado por acidente.
        Renovar é um ato explícito do operador (nova atestação), e ele muda a
        revisão de propósito.
        """
        agora = datetime.now(timezone.utc)
        confirmado = declaracao.confirmada_em.astimezone(timezone.utc)
        if confirmado > agora + timedelta(minutes=5) or confirmado < agora - timedelta(hours=1):
            raise ErroDeNascimentoMeta(
                "META_ASSET_POLICY_RECEIPT_EXPIRED",
                "a confirmação de direitos/identidade da peça expirou; confira novamente",
            )
        # ⚠️ MINIATURA NÃO CERTIFICA A PEÇA, e rotular honestamente não bastava.
        #
        # A versão anterior media os 128px, declarava `rendition=THUMBNAIL_128` e
        # `measured_on_original=false` — e mesmo assim emitia
        # `AUTHORIZED` / `READY_FOR_PAID_MEDIA` com `image_hash_bound=true`.
        # Nenhum consumidor lia o rótulo, então o recibo continuava afirmando
        # que a peça foi conferida. É a mesma classe de mentira que F01: um selo
        # sobre uma inspeção que não aconteceu.
        #
        # A recusa é NOMEADA e acionável: o operador precisa de uma peça cuja
        # biblioteca devolva a imagem, não a miniatura dela.
        if ativo.origem_dos_bytes != ORIGEM_BIBLIOTECA:
            raise ErroDeNascimentoMeta(
                "META_ASSET_ONLY_THUMBNAIL_AVAILABLE",
                "a biblioteca Meta devolveu apenas a miniatura desta peça; "
                "não é possível certificar a imagem que seria veiculada",
            )
        conteudo, tipo_declarado = await self._ler_bytes_da_peca(ativo)
        mime, largura, altura = _decodificar_imagem(conteudo)
        # O cabeçalho pode mentir; agora existe com o que confrontá-lo. Um
        # `image/png` que decodifica como JPEG é peça errada ou entrega errada,
        # e nos dois casos o recibo não pode afirmar qual das duas é.
        if tipo_declarado and tipo_declarado != mime:
            raise ErroDeNascimentoMeta(
                "META_ASSET_MIME_DIVERGED",
                "o tipo declarado pelo CDN não confere com o formato decodificado da peça",
            )
        content_sha = hashlib.sha256(conteudo).hexdigest()
        materia = {
            "versao": VERSAO_DO_RECIBO_DE_SUPPLY,
            "finalidade": FINALIDADE_DO_RECIBO,
            "account_ref": account_ref,
            "actor_id": ator,
            "asset_ref": ativo.publico.referencia_opaca,
            "content_sha256": content_sha,
            "item_sha256": content_sha,
            "provider_image_hash": ativo.id_externo,
            "mime_type": mime,
            "byte_size": len(conteudo),
            "width": largura,
            "height": altura,
            "declared_width": ativo.publico.largura,
            "declared_height": ativo.publico.altura,
            "rendition": ativo.origem_dos_bytes,
            "policy_state": "AUTHORIZED",
            "confirmed_at": confirmado.isoformat(),
            "lifecycle": "READY_FOR_PAID_MEDIA",
        }
        canonico = json.dumps(
            materia, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        supply_sha = hashlib.sha256(canonico).hexdigest()
        # Derivado da MESMA matéria: a referência não pode descrever menos do
        # que o manifesto que ela identifica.
        policy_ref = "metapolicy_" + supply_sha[:24]
        return ManifestoSupplyMeta(
            asset_ref=ativo.publico.referencia_opaca,
            content_sha256=content_sha,
            item_sha256=content_sha,
            supply_sha256=supply_sha,
            policy_receipt_ref=policy_ref,
            policy_state="AUTHORIZED",
            policy_expires_at=confirmado + timedelta(hours=1),
            lifecycle="READY_FOR_PAID_MEDIA",
            provider_image_hash=ativo.id_externo,
            mime_type=mime,
            width=largura,
            height=altura,
            declared_width=ativo.publico.largura,
            declared_height=ativo.publico.altura,
            byte_size=len(conteudo),
            rendition=ativo.origem_dos_bytes,
        )

    async def preview_url(
        self,
        *,
        account_ref: str,
        asset_ref: str,
        segredo: SegredoEfemero,
    ) -> str:
        _, _, imagens, videos, _ = await self._inventario_interno(account_ref, segredo)
        ativo = next(
            (item for item in [*imagens, *videos]
             if item.publico.referencia_opaca == asset_ref), None)
        if ativo is None:
            raise ErroDeNascimentoMeta(
                "META_ASSET_REFERENCE_UNKNOWN", "a peça nao pertence a conta Meta selecionada")
        if not ativo.preview_url:
            raise ErroDeNascimentoMeta(
                "META_ASSET_PREVIEW_UNAVAILABLE", "a Meta nao devolveu previa para esta peça")
        return ativo.preview_url


def _inteiro_opcional(valor: Any) -> int | None:
    if valor in (None, ""):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None
