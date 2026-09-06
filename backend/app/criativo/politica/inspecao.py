"""A inspeção da peça final: o que este servidor consegue provar, e o que não.

## A regra que organiza este módulo

O portão roda sobre a PEÇA FINAL — os bytes relidos do armazenamento — e sobre
a copy. O prompt é entrada, nunca prova: um prompt limpo não impede o gerador de
desenhar um logotipo, e foi exatamente assim que a peça com marca de banco
apareceu.

## Detectores determinísticos e detectores de pixel

Os detectores de TEXTO (copy, nome do arquivo, prompt) são determinísticos e
rodam sempre: mesma entrada, mesmo achado, hoje e daqui a um ano. É o que faz o
recibo ser reconferível.

Os detectores de PIXEL — OCR e classificador de logotipo — precisam de um motor
externo. Este servidor não tem um instalado, e a diferença entre isso e "a peça
está limpa" é a coisa mais importante deste arquivo:

    ⚠️ AUSÊNCIA DE DETECTOR NÃO É AUSÊNCIA DE MARCA.

Quando nenhum detector de pixel está registrado, a inspeção declara
`resultado="ERROR"` para ele, e o portão devolve `GATE_UNAVAILABLE` — que
BLOQUEIA. Deixar passar seria transformar "não consegui olhar" em "olhei e não
tem nada", que é a frase que produziu o incidente.

Um motor real se registra por `registrar_detector_de_pixel()` sem tocar em mais
nada aqui — é o ponto de extensão declarado.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from . import lexico
from .lexico import Achado
from .recibo import Detector


#: As duas capacidades que a inspeção de pixel precisa ter, e que NÃO são a
#: mesma coisa.
#:
#: ⚠️ Esta separação é o conserto de um fail-open que a revisão adversarial
#: reproduziu. Antes, QUALQUER detector registrado satisfazia "a imagem foi
#: inspecionada". Um OCR sozinho, diante de uma peça que traz só um logotipo
#: DESENHADO, devolve texto vazio — e o vazio virava `PASS`, que virava
#: `CLEAR`. Quer dizer: a peça exata do incidente (envelope com marca de banco,
#: parte texto e parte desenho) passaria, com o portão "funcionando".
#:
#: Ler texto e reconhecer marca são perguntas diferentes, e responder uma não
#: responde a outra.
CAPACIDADE_TEXTO_NA_IMAGEM = "texto_na_imagem"
CAPACIDADE_MARCA_VISUAL = "marca_visual"

CAPACIDADES_EXIGIDAS: tuple[str, ...] = (
    CAPACIDADE_TEXTO_NA_IMAGEM,
    CAPACIDADE_MARCA_VISUAL,
)


class DetectorDePixel(Protocol):
    """Um motor que olha os BYTES e devolve texto e rótulos encontrados.

    `capacidades` declara O QUE ele sabe responder. Um detector que não a
    declara é tratado como cobrindo apenas texto — o lado conservador.
    """

    nome: str
    versao: str
    capacidades: tuple[str, ...]

    def inspecionar(self, bytes_da_peca: bytes, *, mime: str) -> "LeituraDePixel":
        ...


@dataclass(frozen=True)
class LeituraDePixel:
    """O que um detector de pixel viu. `texto` alimenta o léxico."""

    texto: str = ""
    rotulos: tuple[tuple[str, float], ...] = ()


_DETECTORES_DE_PIXEL: list[DetectorDePixel] = []


def registrar_detector_de_pixel(detector: DetectorDePixel) -> None:
    """O ponto de extensão. Um OCR/classificador real entra por aqui."""
    _DETECTORES_DE_PIXEL.append(detector)


def detectores_de_pixel_registrados() -> tuple[DetectorDePixel, ...]:
    return tuple(_DETECTORES_DE_PIXEL)


def limpar_detectores_de_pixel() -> None:
    """Só para teste — produção registra na subida do processo."""
    _DETECTORES_DE_PIXEL.clear()


#: Confiança a partir da qual um rótulo de logotipo/marca bloqueia. Abaixo dela
#: o achado é registrado e mostrado, sem bloquear: um portão que bloqueia por
#: suspeita fraca é um portão que alguém desliga.
LIMIAR_DE_ROTULO = 0.70


def sha256_da_copy(copy: Mapping[str, Any] | None) -> str | None:
    """Identidade da copy aprovada. `None` quando a peça não carrega copy.

    Ordenado e canônico: o recibo precisa amarrar A COPY, e duas serializações
    da mesma copy não podem produzir hashes diferentes.
    """
    if not copy:
        return None
    partes = {str(k): str(v or "") for k, v in copy.items() if v not in (None, "")}
    if not partes:
        return None
    import json

    return hashlib.sha256(json.dumps(
        partes, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Inspecao:
    """O resultado bruto, antes de virar decisão."""

    achados: tuple[Achado, ...]
    detectores: tuple[Detector, ...]
    #: True quando algum detector obrigatório não pôde rodar.
    portao_indisponivel: bool
    motivos: tuple[str, ...]


def inspecionar(
    *,
    bytes_da_peca: bytes | None,
    mime: str,
    copy: Mapping[str, Any] | None,
    nome_do_arquivo: str | None,
    prompt: str | None,
    identidade_propria: Iterable[str] | None,
    exigir_pixel: bool = True,
) -> Inspecao:
    """Roda todos os detectores disponíveis e declara os que não rodaram.

    `exigir_pixel=False` existe para a peça que NÃO TEM bytes para inspecionar
    (uma referência de vídeo do provedor, por exemplo). Ela não afrouxa o
    portão: sem bytes, o caminho correto é o item nem chegar a mídia paga, e
    quem decide isso é a cadeia de suprimento, não este módulo.
    """
    achados: list[Achado] = []
    detectores: list[Detector] = []
    motivos: list[str] = []

    partes: dict[str, Any] = {}
    if copy:
        # Uma string só: a copy é um bloco de texto do ponto de vista do léxico,
        # e concatenar preserva a ordem estável dos campos.
        partes["copy"] = " \n".join(
            str(v or "") for _, v in sorted(copy.items()))
    if nome_do_arquivo:
        partes["filename"] = nome_do_arquivo
    if prompt:
        partes["prompt"] = prompt

    achados.extend(lexico.procurar_em_varios(
        partes, identidade_propria=identidade_propria))
    detectores.append(Detector(
        nome="lexico_identidade", versao=lexico.versao(), deterministico=True,
        resultado="FINDINGS" if achados else "PASS",
    ))

    portao_indisponivel = False
    if exigir_pixel:
        registrados = detectores_de_pixel_registrados()
        # ⚠️ COBERTURA, e não presença. Ver `CAPACIDADES_EXIGIDAS`: um OCR
        # sozinho não fecha a inspeção de pixel, porque logotipo desenhado sem
        # texto sai dele como leitura vazia — e vazio viraria PASS.
        cobertas: set[str] = set()
        for detector in registrados:
            cobertas.update(
                getattr(detector, "capacidades", (CAPACIDADE_TEXTO_NA_IMAGEM,)))
        faltando = [c for c in CAPACIDADES_EXIGIDAS if c not in cobertas]
        if registrados and faltando and bytes_da_peca is not None:
            portao_indisponivel = True
            motivos.extend(f"PIXEL_CAPABILITY_MISSING:{c}" for c in faltando)
        if not registrados or bytes_da_peca is None:
            # ⚠️ ERROR, não PASS. Ver o cabeçalho deste módulo.
            detectores.append(Detector(
                nome="inspecao_de_pixel", versao="ausente",
                deterministico=True, resultado="ERROR"))
            portao_indisponivel = True
            motivos.append(
                "PIXEL_INSPECTION_UNAVAILABLE"
                if registrados else "PIXEL_DETECTOR_NOT_REGISTERED"
            )
        for detector in registrados:
            if bytes_da_peca is None:
                continue
            try:
                leitura = detector.inspecionar(bytes_da_peca, mime=mime)
            except Exception:  # noqa: BLE001 — falha de detector não é aprovação
                detectores.append(Detector(
                    nome=detector.nome, versao=detector.versao,
                    deterministico=True, resultado="ERROR"))
                portao_indisponivel = True
                motivos.append("PIXEL_DETECTOR_FAILED")
                continue
            do_pixel = lexico.procurar(
                leitura.texto, origem="ocr",
                identidade_propria=identidade_propria)
            achados.extend(do_pixel)
            fortes = [r for r, c in leitura.rotulos if c >= LIMIAR_DE_ROTULO]
            for rotulo in fortes:
                achados.append(Achado(
                    classe="ROTULO_VISUAL", termo=rotulo, origem="ocr",
                    posicao=0, peso="alto"))
            detectores.append(Detector(
                nome=detector.nome, versao=detector.versao,
                deterministico=True,
                resultado="FINDINGS" if (do_pixel or fortes) else "PASS",
            ))

    ordenados = tuple(sorted(
        achados, key=lambda a: (a.origem, a.classe, a.termo, a.posicao)))
    return Inspecao(
        achados=ordenados,
        detectores=tuple(detectores),
        portao_indisponivel=portao_indisponivel,
        motivos=tuple(dict.fromkeys(motivos)),
    )
