"""O recibo de política: o que foi inspecionado, por quem, e com que veredito.

## Por que ele é assinado

O recibo autoriza uma peça a ir para mídia paga. Se o navegador pudesse montá-lo,
a autorização seria do navegador — e a parte interessada em subir a campanha
assinaria a própria licença. A assinatura HMAC existe para que um recibo forjado
seja recusado ANTES de qualquer chamada ao provedor.

⚠️ A chave NUNCA é a `service_role`. Ela é derivada, pelo mesmo caminho já
usado para assinar URL de preview (`criativo.armazenamento.segredo_de_assinatura`),
e derivada de propósito: um recibo vazado não pode ser um passo em direção à
credencial do banco.

## Por que ele é imutável

Reavaliar não corrige um recibo: gera outro. O anterior fica com
`superseded_by` e o item passa a apontar para o mais recente. Um recibo que
pudesse ser editado não seria prova de nada — seria um campo.

## O que invalida um recibo

Qualquer mudança nos bytes (`content_sha256`), na copy (`copy_sha256`), na
identidade própria (`identity_ref`), na versão do léxico, ou a expiração da
autorização. É por isso que os três hashes entram na assinatura: um recibo que
não cobrisse a copy autorizaria a peça com qualquer texto ao lado dela.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from .lexico import Achado


#: Os vereditos possíveis. Vocabulário fechado — nada fora daqui é decisão.
CLEAR = "CLEAR"
THIRD_PARTY_IDENTITY_AUTHORIZED = "THIRD_PARTY_IDENTITY_AUTHORIZED"
THIRD_PARTY_IDENTITY_UNVERIFIED = "THIRD_PARTY_IDENTITY_UNVERIFIED"
BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
GATE_UNAVAILABLE = "GATE_UNAVAILABLE"

DECISOES: tuple[str, ...] = (
    CLEAR, THIRD_PARTY_IDENTITY_AUTHORIZED, THIRD_PARTY_IDENTITY_UNVERIFIED,
    BLOCKED_BY_POLICY, GATE_UNAVAILABLE,
)

#: As duas — e apenas as duas — que liberam mídia paga.
DECISOES_QUE_LIBERAM: frozenset[str] = frozenset(
    {CLEAR, THIRD_PARTY_IDENTITY_AUTHORIZED})

#: Versão da função de decisão. Entra no recibo: mudar a regra sem mudar a
#: versão faria dois recibos com o mesmo carimbo significarem coisas diferentes.
VERSAO_DA_DECISAO = "v1"

#: Quanto tempo um recibo vale. Curto de propósito: ele descreve um instante da
#: peça e da autorização, e os dois podem mudar.
VALIDADE = timedelta(hours=24)

_REF = re.compile(r"^cpr_[a-f0-9]{24}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class ReciboInvalido(ValueError):
    """O recibo não confere: forjado, adulterado, expirado ou de outra peça."""

    def __init__(self, codigo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.codigo = codigo


def _canonico(valor: Any) -> bytes:
    return json.dumps(
        valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _segredo() -> bytes:
    from app.criativo.armazenamento import segredo_de_assinatura

    # Derivação própria por cima da já derivada: o material que assina recibo de
    # política não é o mesmo que assina URL de preview. Um vazamento de um não
    # produz o outro.
    return hashlib.sha256(
        ("volc-politica-criativa-v1:" + segredo_de_assinatura()).encode("utf-8")
    ).digest()


@dataclass(frozen=True)
class Detector:
    """Um detector que rodou (ou tentou rodar) sobre a peça.

    ⚠️ `resultado="ERROR"` NÃO é `PASS`. Um detector que não conseguiu rodar
    deixa o portão indisponível, e indisponível bloqueia — porque "não consegui
    olhar" não é "não tem nada".
    """

    nome: str
    versao: str
    deterministico: bool
    resultado: str  # PASS | FINDINGS | ERROR

    def __post_init__(self) -> None:
        if self.resultado not in {"PASS", "FINDINGS", "ERROR"}:
            raise ValueError(f"resultado de detector inválido: {self.resultado!r}")

    def publico(self) -> dict[str, Any]:
        return {
            "nome": self.nome, "versao": self.versao,
            "deterministico": self.deterministico, "resultado": self.resultado,
        }


@dataclass(frozen=True)
class ReciboDePolitica:
    """Imutável por construção. Reavaliar gera outro, nunca edita este."""

    policy_receipt_ref: str
    asset_ref: str
    content_sha256_inspecionado: str
    copy_sha256: str | None
    identity_ref: str
    lexico_versao: str
    decisao: str
    avaliado_em: datetime
    expira_em: datetime
    assinatura_hmac: str
    fn_decisao_versao: str = VERSAO_DA_DECISAO
    avaliador: str = "sistema"
    detectores: tuple[Detector, ...] = ()
    achados: tuple[Achado, ...] = ()
    motivos: tuple[str, ...] = ()
    autorizacoes_consultadas: tuple[str, ...] = ()
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        if not _REF.fullmatch(self.policy_receipt_ref):
            raise ReciboInvalido(
                "POLICY_RECEIPT_REF_INVALID", "referência de recibo inválida")
        if not _SHA256.fullmatch(self.content_sha256_inspecionado):
            raise ReciboInvalido(
                "POLICY_RECEIPT_CONTENT_INVALID",
                "o recibo precisa declarar o sha256 dos bytes inspecionados")
        if self.copy_sha256 is not None and not _SHA256.fullmatch(self.copy_sha256):
            raise ReciboInvalido(
                "POLICY_RECEIPT_COPY_INVALID", "copy_sha256 inválido")
        if self.decisao not in DECISOES:
            raise ReciboInvalido(
                "POLICY_RECEIPT_DECISION_INVALID",
                f"decisão fora do vocabulário fechado: {self.decisao!r}")
        for carimbo, nome in ((self.avaliado_em, "avaliado_em"),
                              (self.expira_em, "expira_em")):
            if carimbo.tzinfo is None or carimbo.utcoffset() is None:
                raise ReciboInvalido(
                    "POLICY_RECEIPT_TIMESTAMP_INVALID",
                    f"{nome} precisa ter fuso declarado")

    # ── identidade assinada ────────────────────────────────────────────────

    def materia_assinada(self) -> Mapping[str, Any]:
        """Tudo que, mudando, precisa invalidar a assinatura.

        ⚠️ `achados` e `detectores` entram. Sem eles, alguém poderia manter a
        assinatura e trocar a lista de marcas encontradas — o recibo diria
        CLEAR sobre uma inspeção que achou um banco.
        """
        return {
            "policy_receipt_ref": self.policy_receipt_ref,
            "asset_ref": self.asset_ref,
            "content_sha256_inspecionado": self.content_sha256_inspecionado,
            "copy_sha256": self.copy_sha256,
            "identity_ref": self.identity_ref,
            "lexico_versao": self.lexico_versao,
            "fn_decisao_versao": self.fn_decisao_versao,
            "decisao": self.decisao,
            "avaliado_em": self.avaliado_em.isoformat(),
            "expira_em": self.expira_em.isoformat(),
            "detectores": [d.publico() for d in self.detectores],
            "achados": [a.publico() for a in self.achados],
            "motivos": list(self.motivos),
            "autorizacoes_consultadas": list(self.autorizacoes_consultadas),
        }

    def libera_midia_paga(self) -> bool:
        return self.decisao in DECISOES_QUE_LIBERAM

    def publico(self) -> dict[str, Any]:
        """Projeção para a tela.

        ⚠️ O texto integral do OCR e o prompt NUNCA entram — só os termos que
        casaram. A posição entra porque o operador precisa saber ONDE está a
        marca para decidir entre autorizar e refazer a peça.
        """
        return {
            **self.materia_assinada(),
            "assinatura_hmac": self.assinatura_hmac,
            "avaliador": self.avaliador,
            "superseded_by": self.superseded_by,
            "libera_midia_paga": self.libera_midia_paga(),
        }


def _referencia(asset_ref: str, content_sha256: str, avaliado_em: datetime) -> str:
    digest = hashlib.sha256(
        f"VOLC_POLICY:{asset_ref}:{content_sha256}:{avaliado_em.isoformat()}"
        .encode("utf-8")
    ).hexdigest()[:24]
    return f"cpr_{digest}"


def emitir(
    *,
    asset_ref: str,
    content_sha256: str,
    copy_sha256: str | None,
    identity_ref: str,
    lexico_versao: str,
    decisao: str,
    detectores: Sequence[Detector],
    achados: Sequence[Achado],
    motivos: Sequence[str],
    autorizacoes_consultadas: Sequence[str] = (),
    avaliado_em: datetime | None = None,
) -> ReciboDePolitica:
    """Assina um recibo novo. Nunca edita um existente."""
    quando = avaliado_em or datetime.now(timezone.utc)
    parcial = ReciboDePolitica(
        policy_receipt_ref=_referencia(asset_ref, content_sha256, quando),
        asset_ref=asset_ref,
        content_sha256_inspecionado=content_sha256,
        copy_sha256=copy_sha256,
        identity_ref=identity_ref,
        lexico_versao=lexico_versao,
        decisao=decisao,
        avaliado_em=quando,
        expira_em=quando + VALIDADE,
        assinatura_hmac="",
        detectores=tuple(detectores),
        achados=tuple(achados),
        motivos=tuple(motivos),
        autorizacoes_consultadas=tuple(autorizacoes_consultadas),
    )
    assinatura = hmac.new(
        _segredo(), _canonico(parcial.materia_assinada()), hashlib.sha256,
    ).hexdigest()
    return ReciboDePolitica(
        **{**parcial.__dict__, "assinatura_hmac": assinatura})


def conferir(
    recibo: ReciboDePolitica,
    *,
    asset_ref: str,
    content_sha256: str,
    copy_sha256: str | None,
    agora: datetime | None = None,
) -> None:
    """Recusa recibo forjado, adulterado, expirado, de outra peça ou outra copy.

    Levanta `ReciboInvalido`. Não devolve booleano de propósito: um chamador que
    esquecesse de olhar o retorno passaria adiante um recibo forjado.
    """
    esperada = hmac.new(
        _segredo(), _canonico(recibo.materia_assinada()), hashlib.sha256,
    ).hexdigest()
    # `compare_digest`: comparação com `==` vaza, pelo tempo, quantos bytes
    # iniciais bateram.
    if not hmac.compare_digest(esperada, recibo.assinatura_hmac or ""):
        raise ReciboInvalido(
            "POLICY_RECEIPT_SIGNATURE_INVALID",
            "o recibo de política não foi emitido por este servidor")
    if recibo.asset_ref != asset_ref:
        raise ReciboInvalido(
            "POLICY_RECEIPT_ASSET_DIVERGED",
            "o recibo de política é de outra peça")
    if recibo.content_sha256_inspecionado != content_sha256:
        raise ReciboInvalido(
            "POLICY_RECEIPT_CONTENT_DIVERGED",
            "os bytes mudaram depois da inspeção; a peça precisa ser reavaliada")
    if recibo.copy_sha256 != copy_sha256:
        raise ReciboInvalido(
            "POLICY_RECEIPT_COPY_DIVERGED",
            "a copy mudou depois da inspeção; a peça precisa ser reavaliada")
    if recibo.superseded_by is not None:
        raise ReciboInvalido(
            "POLICY_RECEIPT_SUPERSEDED",
            "este recibo foi substituído por uma reavaliação mais recente")
    if recibo.expira_em <= (agora or datetime.now(timezone.utc)):
        raise ReciboInvalido(
            "POLICY_RECEIPT_EXPIRED", "o recibo de política expirou")
    if not recibo.libera_midia_paga():
        raise ReciboInvalido(
            f"POLICY_{recibo.decisao}",
            "o recibo de política não libera esta peça para mídia paga")
