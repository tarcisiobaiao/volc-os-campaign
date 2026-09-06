"""Adaptador de OCR para o portão de política — o motor que ainda falta.

## Por que ele existe escrito, se o motor não está instalado

O seam (`registrar_detector_de_pixel`) estava declarado e vazio, e "o que
faltaria" vivia só numa frase de runbook. Uma frase não compila, não tem
assinatura conferida e não diz o que fazer quando o motor aparece.

Este arquivo é o adaptador exato: assinatura conferida contra o Protocol,
decodificação pelo Pillow que JÁ existe, e o contrato de resultado que o recibo
espera. Quando `pytesseract` e o binário `tesseract` existirem no host, ele
passa a funcionar sem que ninguém precise reprojetar nada.

## O que ele NÃO resolve, e está declarado

OCR lê TEXTO. Ele não pontua logotipo desenhado sem texto, e o incidente que
originou esta lane era um envelope com marca — parte texto, parte desenho. Por
isso `rotulos` volta vazio aqui: preencher com um escore inventado faria o
portão comparar contra `LIMIAR_DE_ROTULO` um número que ninguém mediu.

Fechar a metade visual exige um classificador de marca/logo, com escore
calibrado, e essa decisão tem custo e política de envio de bytes a terceiro —
está registrada no runbook RB-08 e não é tomada aqui.
"""
from __future__ import annotations

import io
import logging

from ..inspecao import CAPACIDADE_TEXTO_NA_IMAGEM, LeituraDePixel

log = logging.getLogger(__name__)

#: Idiomas do OCR. Português primeiro: a copy e as peças são em pt-BR, e o
#: inglês entra porque marca e termo de afiliação aparecem nos dois.
IDIOMAS = "por+eng"


class MotorDeOcrIndisponivel(RuntimeError):
    """O motor não está instalado. ⚠️ NÃO é "a peça está limpa"."""


class DetectorOcrTesseract:
    """Lê o texto impresso na peça FINAL, a partir dos bytes já relidos.

    ⚠️ `inspecionar` é SÍNCRONO de propósito: é o Protocol que o portão declara,
    e o portão roda dentro de uma requisição async. Um adaptador async aqui
    obrigaria o portão a virar async ou a abrir um event loop dentro de outro.
    """

    nome = "ocr.tesseract"

    #: ⚠️ SÓ texto. Declarar `marca_visual` aqui seria mentir: `image_to_string`
    #: devolve string vazia para um logotipo desenhado sem letra, e o portão
    #: leria esse vazio como "olhei e não tem nada". Enquanto esta tupla não
    #: tiver `marca_visual`, o portão continua em GATE_UNAVAILABLE mesmo com o
    #: OCR instalado e funcionando — que é a resposta certa.
    capacidades = (CAPACIDADE_TEXTO_NA_IMAGEM,)

    def __init__(self, versao: str) -> None:
        # A versão vem de quem construiu, e vem do BINÁRIO — não de um literal.
        # Ela entra no recibo, e um recibo que declara versão errada não pode
        # ser reconferido depois.
        self.versao = versao

    @classmethod
    def se_disponivel(cls) -> "DetectorOcrTesseract | None":
        """O construtor honesto: devolve `None` quando o motor não existe.

        Nunca levanta para o chamador de boot. Quem chama registra o que voltar,
        e `None` significa que ninguém é registrado — o portão continua fechado.
        """
        try:
            import pytesseract  # type: ignore[import-not-found]

            versao = str(pytesseract.get_tesseract_version())
        except Exception as exc:  # noqa: BLE001 — ausência é o caso esperado
            log.info(
                "detector de pixel OCR indisponível (%s); o portão de política "
                "permanece bloqueando por GATE_UNAVAILABLE", type(exc).__name__)
            return None
        return cls(versao=versao)

    def inspecionar(self, bytes_da_peca: bytes, *, mime: str) -> LeituraDePixel:
        """Texto encontrado na imagem. Falha levanta — nunca vira leitura vazia.

        ⚠️ Levantar é o contrato: o portão captura e marca o detector como
        `ERROR`, o que produz `GATE_UNAVAILABLE`. Devolver `LeituraDePixel()`
        numa falha diria que a peça foi inspecionada e está limpa.
        """
        try:
            import pytesseract  # type: ignore[import-not-found]
            from PIL import Image
        except Exception as exc:  # noqa: BLE001
            raise MotorDeOcrIndisponivel(
                "o motor de OCR sumiu depois do registro") from exc
        with Image.open(io.BytesIO(bytes_da_peca)) as imagem:
            texto = pytesseract.image_to_string(imagem, lang=IDIOMAS)
        return LeituraDePixel(
            texto=str(texto or ""),
            # ⚠️ VAZIO, e declarado. OCR não pontua logotipo desenhado sem
            # texto; inventar um escore aqui faria o portão comparar contra
            # `LIMIAR_DE_ROTULO` um número que ninguém mediu.
            rotulos=(),
        )


def registrar_detectores_disponiveis() -> tuple[str, ...]:
    """Registra o que existir de verdade. Devolve os nomes registrados.

    Tupla vazia significa que o portão continua em `GATE_UNAVAILABLE` — e isso
    é um estado correto e declarado, não uma falha de boot.
    """
    from ..inspecao import registrar_detector_de_pixel

    registrados: list[str] = []
    ocr = DetectorOcrTesseract.se_disponivel()
    if ocr is not None:
        registrar_detector_de_pixel(ocr)
        registrados.append(f"{ocr.nome}@{ocr.versao}")
    return tuple(registrados)
