"""Registrar mídia sob custódia numa conta Meta — um ato PRÓPRIO.

## Por que isto não mora em `ativos.py`

`ativos.py` se declara somente-leitura na primeira linha, e os testes dele
fixam a CONTAGEM de GETs. Um POST que escreve na conta ali dentro tornaria
aquela declaração falsa e faria a prova de leitura passar a cobrir um caminho
de escrita. Dois atos com autoridades opostas precisam de dois módulos.

## Os quatro atos que esta lane mantém separados

Importar um arquivo, registrar mídia numa conta, validar um plano e criar uma
campanha são QUATRO coisas diferentes, com quatro autorizações diferentes.
Este módulo faz exatamente a segunda — e nada mais. Ele não cria Campaign,
AdSet, Ad nem Creative, e não existe endpoint genérico de mutação por onde
alguém pudesse pedir outra coisa.

## O silêncio da rede depois do POST

Um upload que estoura o tempo NÃO é um upload que falhou: o `adimages` pode
ter nascido enquanto ninguém olhava. Reenviar nesse estado criaria um segundo
ativo — e, pior, um segundo `image_hash` para os mesmos bytes. Por isso o
recibo é gravado ANTES do POST, o timeout vira AMBIGUO, e AMBIGUO nunca
reenvia: ele exige leitura.

⚠️ Idempotência por `(conta, sha256 dos bytes)`, e não por nome de arquivo.
Nome é do operador e muda; os bytes são o que a Meta indexa.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlparse

import httpx

from app.trafego.meta import dominio as dom
from app.trafego.meta.credenciais import SegredoEfemero

from .contrato import ErroDeNascimentoMeta


#: Teto de bytes por peça no caminho de REGISTRO.
#:
#: ⚠️ É o mesmo teto do caminho de leitura Meta (`ativos.TETO_DE_IMAGEM_BYTES`,
#: 12 MB) e NÃO o do armazenamento (25 MB). Os dois divergem hoje, e escolher o
#: MAIS RESTRITIVO é a regra do contrato desta missão: "confrontar limite real
#: do provedor e usar o mais restritivo".
TETO_DE_IMAGEM_BYTES = 12 * 1024 * 1024

#: Formatos que este servidor aceita ENVIAR. Deliberadamente mais estreito do
#: que o que ele aceita LER: a leitura descreve o que já existe na conta, o
#: envio cria patrimônio novo, e GIF/WEBP não têm prova de aceitação nesta lane.
MIMES_QUE_PODEM_SER_ENVIADOS: frozenset[str] = frozenset({"image/jpeg", "image/png"})

ESTADO_REGISTRADO = "REGISTERED"
ESTADO_AMBIGUO = "AMBIGUOUS_REGISTRATION"
ESTADO_RECUSADO = "REJECTED"
ESTADO_JA_REGISTRADO = "ALREADY_REGISTERED"


class ErroDeRegistroDeMidia(ErroDeNascimentoMeta):
    """Recusa nomeada do ato de registrar mídia."""


@dataclass(frozen=True)
class PecaParaRegistrar:
    """Bytes JÁ sob nossa custódia, prontos para virar um ativo da conta.

    ⚠️ `content_sha256` é dos BYTES FINAIS EXATOS que serão enviados — não do
    arquivo original, não do que o cliente declarou. É ele que amarra o recibo
    ao que a Meta recebeu.
    """

    master_ref: str
    nome: str
    mime_type: str
    conteudo: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.conteudo, (bytes, bytearray)) or not self.conteudo:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_UPLOAD_EMPTY", "a peça não tem bytes para registrar")
        if len(self.conteudo) > TETO_DE_IMAGEM_BYTES:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_UPLOAD_TOO_LARGE",
                "a peça excede o limite de bytes aceito para registro",
            )
        if self.mime_type not in MIMES_QUE_PODEM_SER_ENVIADOS:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_UPLOAD_FORMAT_UNPROVEN",
                "este servidor só registra JPEG e PNG; outros formatos exigem prova própria",
            )

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.conteudo).hexdigest()


@dataclass(frozen=True)
class ResultadoDoRegistro:
    """O que aconteceu com UMA peça. Vocabulário fechado."""

    master_ref: str
    estado: str
    #: Só existe quando a Meta devolveu — e mesmo assim nunca sai numa resposta
    #: HTTP: o que a rota devolve é a referência opaca derivada dele.
    image_hash: str | None = None
    asset_ref: str | None = None
    motivo: str | None = None
    codigo: str | None = None

    @property
    def utilizavel(self) -> bool:
        return self.estado in {ESTADO_REGISTRADO, ESTADO_JA_REGISTRADO}


class LivroDeRegistroDeMidia(Protocol):
    """A autoridade durável do ato. Sem ela, nada é enviado.

    A forma espelha `RegistroSagaMeta` de propósito: o problema é o mesmo —
    gravar antes do efeito externo, cercar quem conclui, e tratar silêncio como
    ambiguidade em vez de fracasso.
    """

    async def reservar(
        self, *, account_ref: str, content_sha256: str, ator: str, master_ref: str,
    ) -> Mapping[str, Any]:
        """Grava e COMMITA a reserva antes de devolver.

        Devolve ao menos `estado` em {'DESPACHAR','REGISTRADO','AMBIGUO'} e,
        quando REGISTRADO, o `image_hash` já conhecido.
        """
        ...

    async def concluir(
        self, *, reserva_ref: str, image_hash: str, claim_token: str,
    ) -> None: ...

    async def marcar_ambiguo(self, *, reserva_ref: str, claim_token: str) -> None: ...

    async def falhar(
        self, *, reserva_ref: str, codigo: str, claim_token: str,
    ) -> None: ...


def referencia_opaca_de_imagem(conta_externa: str, image_hash: str) -> str:
    """O handle que o navegador verá para uma imagem da conta.

    ⚠️ Precisa ser IDÊNTICO ao que o inventário de leitura produz para a mesma
    imagem. Se o registro devolvesse outro handle, a peça recém-enviada
    apareceria como um segundo item na próxima listagem — e o operador veria
    duas peças onde existe uma.
    """
    conta = dom.conta_canonica(conta_externa)
    digest = hashlib.sha256(
        f"META_ADS:{conta}:image_asset:{image_hash}".encode("utf-8")
    ).hexdigest()[:24]
    return f"metaasset_{digest}"


class RegistradorDeMidiaMeta:
    """Envia bytes sob custódia para `adimages` de UMA conta escolhida."""

    def __init__(
        self,
        cliente: httpx.AsyncClient,
        livro: LivroDeRegistroDeMidia,
        *,
        api_version: str = "v26.0",
        base_url: str = "https://graph.facebook.com",
    ) -> None:
        partes = urlparse(base_url)
        if partes.scheme != "https" or partes.hostname != "graph.facebook.com":
            raise ValueError("base Meta precisa ser https://graph.facebook.com")
        if api_version != "v26.0":
            raise ValueError("o registro de midia esta fixado em v26.0")
        self._cliente = cliente
        self._base = base_url.rstrip("/")
        self._versao = api_version
        self._livro = livro

    async def registrar_imagens(
        self,
        *,
        conta_externa: str,
        pecas: Sequence[PecaParaRegistrar],
        segredo: SegredoEfemero,
        ator: str,
        account_ref: str,
    ) -> tuple[ResultadoDoRegistro, ...]:
        """Registra cada peça, uma a uma, com recibo durável antes do POST.

        ⚠️ UMA A UMA e não em lote: um lote que estoura o tempo deixa TODAS as
        peças ambíguas, e a leitura de reconciliação teria de adivinhar quais
        nasceram. Peça a peça, a ambiguidade fica contida em uma.
        """
        if not pecas:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_UPLOAD_EMPTY_BATCH", "nenhuma peça foi selecionada para registro")
        if len(pecas) > 10:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_UPLOAD_BATCH_TOO_LARGE",
                "registre no máximo 10 peças por confirmação",
            )
        conta = dom.conta_canonica(conta_externa)
        resultados: list[ResultadoDoRegistro] = []
        for peca in pecas:
            resultados.append(await self._registrar_uma(
                conta=conta, account_ref=account_ref, peca=peca,
                segredo=segredo, ator=ator))
        return tuple(resultados)

    async def _registrar_uma(
        self,
        *,
        conta: str,
        account_ref: str,
        peca: PecaParaRegistrar,
        segredo: SegredoEfemero,
        ator: str,
    ) -> ResultadoDoRegistro:
        reserva = await self._livro.reservar(
            account_ref=account_ref,
            content_sha256=peca.content_sha256,
            ator=ator,
            master_ref=peca.master_ref,
        )
        estado = str(reserva.get("estado") or "")

        if estado == "REGISTRADO":
            # ⚠️ Replay: os MESMOS bytes já viraram um ativo desta conta. O
            # certo é devolver o hash que já existe, não enviar de novo — um
            # segundo envio criaria um segundo ativo idêntico e o operador
            # pagaria duas vezes pela mesma peça na biblioteca.
            existente = str(reserva.get("image_hash") or "")
            return ResultadoDoRegistro(
                master_ref=peca.master_ref,
                estado=ESTADO_JA_REGISTRADO,
                image_hash=existente or None,
                asset_ref=referencia_opaca_de_imagem(conta, existente) if existente else None,
                motivo="estes bytes já estavam registrados nesta conta",
            )

        if estado == "AMBIGUO":
            # ⚠️ Um envio anterior ficou sem conclusão registrada. Reenviar
            # aqui é exatamente o que a saga proíbe: o ativo pode existir.
            return ResultadoDoRegistro(
                master_ref=peca.master_ref,
                estado=ESTADO_AMBIGUO,
                motivo=(
                    "um registro anterior destes bytes ficou sem conclusão; "
                    "reconcilie por leitura antes de tentar de novo"
                ),
                codigo="META_ASSET_REGISTRATION_AMBIGUOUS",
            )

        if estado != "DESPACHAR":
            raise ErroDeRegistroDeMidia(
                "META_ASSET_LEDGER_INVALID_STATE",
                "o livro de registro devolveu um estado que este servidor não conhece",
            )

        reserva_ref = str(reserva.get("reserva_ref") or "")
        token = str(reserva.get("claim_token") or "")
        if not reserva_ref or not token:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_LEDGER_INVALID_STATE",
                "a reserva de registro não veio com identidade e cerca",
            )

        url = f"{self._base}/{self._versao}/act_{conta}/adimages"
        try:
            resposta = await self._cliente.post(
                url,
                # ⚠️ O token viaja no CABEÇALHO, nunca no corpo nem na query.
                # Numa query ele entraria em log de proxy e histórico; num
                # corpo multipart ele apareceria em qualquer dump de request.
                #
                # ⚠️ E ele nunca é DESEMBRULHADO aqui: `cabecalho_bearer()` é o
                # único acessor de `SegredoEfemero`, e `__repr__`/`__str__` do
                # tipo devolvem `<oculto>`. Extrair o valor cru para formatar a
                # string à mão reintroduziria a variável que um traceback
                # imprimiria.
                headers={"Authorization": segredo.cabecalho_bearer()},
                files={"source": (peca.nome, peca.conteudo, peca.mime_type)},
            )
        except httpx.TimeoutException:
            await self._livro.marcar_ambiguo(reserva_ref=reserva_ref, claim_token=token)
            return ResultadoDoRegistro(
                master_ref=peca.master_ref,
                estado=ESTADO_AMBIGUO,
                motivo=(
                    "a Meta não respondeu a tempo; a peça pode ter sido registrada. "
                    "Reconcilie por leitura — reenviar duplicaria."
                ),
                codigo="META_ASSET_REGISTRATION_TIMEOUT",
            )
        except httpx.HTTPError:
            # ⚠️ QUALQUER falha de transporte depois do POST é ambígua, não é
            # fracasso. Antes só o timeout era capturado, e uma queda de conexão
            # atravessava `_registrar_uma`, atravessava a rota e deixava a
            # reserva pendurada em DESPACHAR — travando aqueles bytes naquela
            # conta sem nenhum recibo dizendo por quê.
            await self._livro.marcar_ambiguo(reserva_ref=reserva_ref, claim_token=token)
            return ResultadoDoRegistro(
                master_ref=peca.master_ref,
                estado=ESTADO_AMBIGUO,
                motivo=(
                    "a conexão caiu depois do envio; a peça pode ter sido registrada. "
                    "Reconcilie por leitura — reenviar duplicaria."
                ),
                codigo="META_ASSET_REGISTRATION_TRANSPORT",
            )

        # ⚠️ `resposta.json()` PRECISA de guarda. Um 200 com corpo não-JSON
        # levantaria ValueError aqui e deixaria a reserva pendurada — o mesmo
        # dano da queda de conexão, por um caminho diferente.
        try:
            corpo = resposta.json()
        except (ValueError, TypeError):
            corpo = {}

        if resposta.status_code >= 400:
            # ⚠️ SÓ A RECUSA EXPLÍCITA DA META prova que nada nasceu, e "explícita"
            # é 4xx COM objeto de erro do provedor. Um 5xx não prova nada: o
            # multipart já foi encaminhado, e o `adimages` pode ter nascido atrás
            # de um gateway que devolveu 502. Tratar isso como FALHOU era pior do
            # que parecer, porque FALHOU AUTORIZA nova tentativa — o servidor
            # reenviaria os mesmos bytes e criaria um segundo ativo na conta do
            # cliente.
            recusa_do_provedor = (
                400 <= resposta.status_code < 500
                and isinstance(corpo, Mapping)
                and isinstance(corpo.get("error"), Mapping)
            )
            if recusa_do_provedor:
                await self._livro.falhar(
                    reserva_ref=reserva_ref,
                    codigo="META_ASSET_UPLOAD_REJECTED",
                    claim_token=token,
                )
                return ResultadoDoRegistro(
                    master_ref=peca.master_ref,
                    estado=ESTADO_RECUSADO,
                    motivo="a Meta recusou o registro desta peça",
                    codigo="META_ASSET_UPLOAD_REJECTED",
                )
            await self._livro.marcar_ambiguo(reserva_ref=reserva_ref, claim_token=token)
            return ResultadoDoRegistro(
                master_ref=peca.master_ref,
                estado=ESTADO_AMBIGUO,
                motivo=(
                    f"a Meta respondeu {resposta.status_code} sem recusa explícita; "
                    "a peça pode ter sido registrada. Reconcilie por leitura."
                ),
                codigo="META_ASSET_REGISTRATION_INCONCLUSIVE",
            )

        image_hash = _hash_da_resposta(corpo, nome=peca.nome)
        if image_hash is None:
            # A Meta respondeu 200 e não deu para achar o hash. NÃO é sucesso e
            # NÃO é fracasso: o ativo provavelmente existe e nós não sabemos o
            # nome dele. É o caso mais perigoso de todos, e vira AMBIGUO.
            await self._livro.marcar_ambiguo(reserva_ref=reserva_ref, claim_token=token)
            return ResultadoDoRegistro(
                master_ref=peca.master_ref,
                estado=ESTADO_AMBIGUO,
                motivo=(
                    "a Meta aceitou o envio mas não devolveu o identificador da peça; "
                    "reconcilie por leitura"
                ),
                codigo="META_ASSET_REGISTRATION_UNIDENTIFIED",
            )

        # ⚠️ O ID É GRAVADO ANTES DO READ-BACK. Uma queda entre o POST e o
        # INSERT perderia para sempre a única prova de que a peça nasceu.
        await self._livro.concluir(
            reserva_ref=reserva_ref, image_hash=image_hash, claim_token=token)
        return ResultadoDoRegistro(
            master_ref=peca.master_ref,
            estado=ESTADO_REGISTRADO,
            image_hash=image_hash,
            asset_ref=referencia_opaca_de_imagem(conta, image_hash),
        )


def _hash_da_resposta(corpo: Any, *, nome: str) -> str | None:
    """Extrai o `hash` que `adimages` devolve, sem adivinhar.

    A Graph responde `{"images": {"<nome do arquivo>": {"hash": ..., "url": ...}}}`.
    O nome da chave é o nome do arquivo enviado — mas normalizado pelo provedor
    de formas que não estão documentadas aqui. Por isso: tenta o nome exato e,
    se não achar, aceita a ÚNICA entrada quando existe exatamente uma. Com duas
    ou mais entradas e nenhuma correspondência, devolve `None` — escolher uma
    seria inventar a identidade da peça.
    """
    if not isinstance(corpo, Mapping):
        return None
    imagens = corpo.get("images")
    if not isinstance(imagens, Mapping) or not imagens:
        return None
    candidata = imagens.get(nome)
    if not isinstance(candidata, Mapping) and len(imagens) == 1:
        candidata = next(iter(imagens.values()))
    if not isinstance(candidata, Mapping):
        return None
    valor = str(candidata.get("hash") or "").strip()
    # Mesma forma que `ReferenciasMetaResolvidas` cobra do image_hash.
    if not valor or len(valor) < 6 or len(valor) > 160:
        return None
    return valor


class LivroDeRegistroDeMidiaSupabase:
    """Traduz o protocolo do livro para as RPCs transacionais do Supabase.

    ⚠️ Espelha `RegistroSagaMetaSupabase` de propósito, inclusive na recusa
    fechada: sem a autorização do ledger e sem o Supabase configurado, ele
    RECUSA em vez de seguir sem recibo. Um registro sem livro é um upload que
    ninguém consegue reconciliar depois.
    """

    def __init__(self, servico: Any) -> None:
        self._servico = servico

    def _exigir_escrita(self) -> None:
        import os

        if os.environ.get("META_CREATE_LEDGER_WRITE_ENABLED") != "1":
            raise ErroDeRegistroDeMidia(
                "META_ASSET_LEDGER_BLOCKED",
                "o registro durável Meta permanece fechado neste servidor",
            )
        if not getattr(self._servico, "enabled", False):
            raise ErroDeRegistroDeMidia(
                "META_ASSET_LEDGER_UNAVAILABLE",
                "o Supabase operacional não está configurado neste backend",
            )

    async def _rpc(self, funcao: str, argumentos: Mapping[str, Any]) -> Mapping[str, Any]:
        self._exigir_escrita()
        try:
            resposta = await self._servico.rpc(funcao, dict(argumentos))
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else 500
            texto = ""
            try:
                texto = exc.response.text if exc.response is not None else ""
            except Exception:  # pragma: no cover - defensivo
                texto = ""
            # ⚠️ A cerca tem nome próprio na resposta. Sem separá-la aqui, um
            # despacho cercado viraria "o ledger recusou" — e quem lesse isso
            # tentaria de novo, que é exatamente o que a cerca impede.
            if "META_ASSET_CLAIM_FENCED" in texto:
                raise ErroDeRegistroDeMidia(
                    "META_ASSET_CLAIM_FENCED",
                    "outro processo assumiu este registro; a peça pode existir",
                ) from None
            raise ErroDeRegistroDeMidia(
                "META_ASSET_LEDGER_REJECTED",
                f"a autoridade persistente recusou a operação (HTTP {status})",
            ) from None
        except httpx.HTTPError:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_LEDGER_UNAVAILABLE",
                "a autoridade persistente não respondeu",
            ) from None
        if not isinstance(resposta, Mapping):
            raise ErroDeRegistroDeMidia(
                "META_ASSET_LEDGER_INVALID_RESPONSE",
                "a autoridade persistente devolveu resposta inválida",
            )
        return resposta

    async def reservar(
        self, *, account_ref: str, content_sha256: str, ator: str, master_ref: str,
    ) -> Mapping[str, Any]:
        return await self._rpc("trafego_meta_reservar_registro_ativo", {
            "p_account_ref": account_ref,
            "p_content_sha256": content_sha256,
            "p_actor_id": ator,
            "p_master_ref": master_ref,
        })

    async def concluir(
        self, *, reserva_ref: str, image_hash: str, claim_token: str,
    ) -> None:
        await self._rpc("trafego_meta_concluir_registro_ativo", {
            "p_reserva_ref": reserva_ref,
            "p_image_hash": image_hash,
            "p_claim_token": claim_token,
        })

    async def marcar_ambiguo(self, *, reserva_ref: str, claim_token: str) -> None:
        await self._rpc("trafego_meta_marcar_registro_ativo_ambiguo", {
            "p_reserva_ref": reserva_ref,
            "p_claim_token": claim_token,
        })

    async def falhar(self, *, reserva_ref: str, codigo: str, claim_token: str) -> None:
        await self._rpc("trafego_meta_falhar_registro_ativo", {
            "p_reserva_ref": reserva_ref,
            "p_codigo": codigo,
            "p_claim_token": claim_token,
        })
