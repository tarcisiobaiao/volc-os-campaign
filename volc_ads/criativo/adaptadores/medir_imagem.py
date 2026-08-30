"""Mede formato e dimensão a partir dos BYTES — só stdlib, sem Pillow.

## Por que medir aqui, e não no validador

`criativo/validacao.py:29-32` já declarou o dono: "Não abre arquivo, não mede
pixel e não fala com o Google. Ele julga o que já foi medido; medir é trabalho
do adaptador, que é quem tem os bytes." Este arquivo é esse adaptador para o
caso mais comum — bytes que já estão na mão, sem motor nenhum no meio.

## Por que NÃO usar Pillow

Pillow está instalado no `backend/.venv` (12.3.0) e **não está declarado em
`backend/requirements.txt`**. Depender dele aqui criaria uma dependência que o
ambiente de produção pode não ter — e o modo de falha seria o pior possível:
`_medir` devolveria `(None, None, None)` em silêncio, todo asset chegaria sem
medida, e a validação de geometria que esta fatia existe para ligar ficaria
inerte sem que ninguém percebesse. Um cabeçalho de PNG tem 24 bytes e a
stdlib lê os três formatos que a API v25 aceita.

## A regra que este arquivo NÃO pode quebrar

Dimensão desconhecida é `None`, **nunca** `0`. E isso não é teórico: o helper
de teste do próprio repo (`campanha/testes_display.py:718`) produz
`b"\\x89PNG\\r\\n\\x1a\\n" + b"\\x00" * 64` — um PNG cuja assinatura é válida e
cujo IHDR é todo zero. Um medidor ingênuo leria `largura=0, altura=0` e
`Asset.__post_init__` (`contrato.py:189`) recusaria o asset com a mensagem
errada ("medida ausente é None, nunca 0"), culpando quem mediu em vez de dizer
a verdade: o cabeçalho não trouxe dimensão utilizável.

Por isso a leitura é em duas perguntas separadas, e elas podem ter respostas
diferentes:

    QUE FORMATO É?   assinatura do arquivo → `mime`
    QUE TAMANHO TEM? cabeçalho do formato  → `largura`/`altura`

Um arquivo pode ser reconhecidamente PNG (`mime` preenchido) e ter dimensão
`None` porque o IHDR não veio, veio truncado ou veio zerado. As duas respostas
viajam separadas porque são fatos separados.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# Assinaturas. Fonte: as especificações dos três formatos que
# `criativo/requisitos.yaml:padroes.imagem.mimes` declara aceitos pela API v25
# (`image/png`, `image/jpeg`, `image/gif`).
_PNG = b"\x89PNG\r\n\x1a\n"
_GIF87, _GIF89 = b"GIF87a", b"GIF89a"
_JPEG = b"\xff\xd8"

# Marcadores que NAO tem payload: depois deles vem outro marcador, e nao um
# comprimento.
#
# ⚠️ `0xD9` (EOI) faltava aqui, e a falta produzia NUMERO ERRADO em vez de
# ausencia — que e o unico modo de falha que este arquivo nao pode ter. Sem ele
# o parser lia os dois bytes seguintes ao EOI como se fossem um comprimento e
# saltava para fora do arquivo, devolvendo o SOF ANTERIOR. Medido em
# 27/08/2026 sobre `FFD8 + SOF(1200x628) + FFD9 + SOF(300x250) + SOS`: nosso
# medidor dizia 1200x628 e o Pillow lia 300x250 — e o portao de geometria mais
# o `confirmada: true` eram emitidos sobre o numero errado.
#
# `0x01` e TEM (temporario aritmetico), `0xD8` e SOI, `0xD0..0xD7` sao os RSTn.
_SEM_PAYLOAD = frozenset({0x01, 0xD8, 0xD9})

# Marcadores SOF do JPEG que carregam dimensão. C4 (Huffman), C8 (extensão
# JPEG) e CC (aritmética) ocupam a mesma faixa e NÃO são SOF — lê-los como se
# fossem devolveria lixo com cara de medida.
_SOF = (
    frozenset(range(0xC0, 0xC4))
    | frozenset(range(0xC5, 0xC8))
    | frozenset(range(0xC9, 0xCC))
    | frozenset(range(0xCD, 0xD0))
)


@dataclass(frozen=True)
class Medida:
    """O que os bytes revelaram. Cada campo é `None` quando não revelaram.

    `bytes_totais` é o único que quase sempre se sabe — mas é `None` quando o
    conteúdo é vazio, porque "arquivo de zero byte" é ausência de arquivo, não
    um arquivo que mede zero.
    """

    mime: str | None = None
    largura: int | None = None
    altura: int | None = None
    bytes_totais: int | None = None

    @property
    def dimensionada(self) -> bool:
        return self.largura is not None and self.altura is not None


def _positivos(largura: int, altura: int) -> tuple[int, int] | None:
    """Converte medida não-positiva em ausência.

    Zero e negativo num cabeçalho de imagem não são medidas: são cabeçalho
    corrompido, truncado ou sintético. Devolvê-los como número faria o resto do
    sistema tratar "não deu para ler" como "li e deu zero".
    """
    if largura <= 0 or altura <= 0:
        return None
    return largura, altura


def _do_png(dados: bytes) -> tuple[int, int] | None:
    # IHDR é obrigatoriamente o primeiro chunk: 8 de assinatura, 4 de tamanho,
    # 4 do literal "IHDR", e aí largura e altura em big-endian.
    if len(dados) < 24 or dados[12:16] != b"IHDR":
        return None
    largura, altura = struct.unpack(">II", dados[16:24])
    return _positivos(largura, altura)


def _do_gif(dados: bytes) -> tuple[int, int] | None:
    # Logical Screen Descriptor, logo após os 6 bytes de assinatura, em
    # little-endian — o GIF é o único dos três que não é big-endian.
    if len(dados) < 10:
        return None
    largura, altura = struct.unpack("<HH", dados[6:10])
    return _positivos(largura, altura)


def _do_jpeg(dados: bytes) -> tuple[int, int] | None:
    """Caminha os segmentos ate o SOS. O ULTIMO SOF vence. Nao decodifica nada."""
    achado: tuple[int, int] | None = None
    i, n = 2, len(dados)
    while i + 3 < n:
        if dados[i] != 0xFF:
            # Fora de sincronia. Um JPEG bem formado tem 0xFF em toda fronteira
            # de segmento; sem isso, qualquer avanco seria chute. O que ja foi
            # lido de um SOF bem formado continua valendo.
            return achado
        marcador = dados[i + 1]
        if marcador == 0xFF:  # preenchimento legítimo entre segmentos
            i += 1
            continue
        if marcador in _SEM_PAYLOAD or 0xD0 <= marcador <= 0xD7:
            i += 2
            continue
        if marcador == 0xDA:
            # Start of Scan: daqui em diante sao dados comprimidos, e nenhum
            # SOF vira depois. Devolve o ultimo SOF visto — ou None, se nao
            # houve nenhum.
            return achado
        (tamanho,) = struct.unpack(">H", dados[i + 2:i + 4])
        if tamanho < 2:
            # Segmento com comprimento impossivel: nao da para saber onde ele
            # acaba, entao a caminhada para. Mas o que JA foi lido de um SOF bem
            # formado continua valendo — ate o ciclo 3 este ramo devolvia `None`
            # e jogava fora uma medida legitima. Medido: `SOF(600x314)` seguido
            # de um segmento com `length=0` devolvia ausencia enquanto o Pillow
            # lia 600x314. Recusar o legitimo tambem e um defeito.
            return achado
        if marcador in _SOF:
            # length(2) precision(1) height(2) width(2) — altura ANTES da
            # largura, ao contrário dos outros dois formatos.
            #
            # ⚠️ DUAS GUARDAS, e a primeira versão desta correção tinha a
            # errada. Ela exigia `tamanho >= 7` — o mínimo aritmético para os
            # campos que se quer ler. Mas `tamanho` é declarado PELO PRÓPRIO
            # SEGMENTO, então bastava declarar 7 para a leitura voltar a
            # invadir o segmento seguinte. Medido em 27/08/2026: um arquivo de
            # 11 bytes saía como `1200x628`, e `SOF length=7` seguido de APP0
            # saía como `16x65504` — que são o marcador `\xff\xe0` e o
            # comprimento dele. A guarda neutralizou a testemunha, não o
            # defeito.
            #
            #   1. O SPEC manda: um SOF vale `8 + 3·Nf` bytes, com `Nf >= 1`
            #      componentes. Mínimo real: 11. `7` é um segmento impossível,
            #      e um segmento impossível não é fonte de medida.
            #   2. O SEGMENTO tem de CABER: `tamanho` declarado maior que o
            #      arquivo é cabeçalho corrompido ou truncado, e ler os bytes
            #      que por acaso estão ali devolveria número sem origem.
            _MIN_SOF = 11
            if tamanho < _MIN_SOF or i + 2 + tamanho > n:
                return None
            altura, largura = struct.unpack(">HH", dados[i + 5:i + 9])
            # ⚠️ NAO retorna aqui: guarda e CONTINUA ate o SOS.
            #
            # Com dois SOF bem formados, parar no primeiro devolvia a dimensao
            # do primeiro enquanto o decodificador de referencia (Pillow) usa o
            # ULTIMO — medido em 27/08/2026: nosso 1200x628 contra 300x250 do
            # Pillow, sobre o mesmo arquivo. O numero nao descrevia o arquivo, e
            # o portao de geometria era emitido sobre ele.
            achado = _positivos(largura, altura)
        i += 2 + tamanho
    return achado


#: Os formatos cuja ASSINATURA este módulo sabe reconhecer.
#:
#: A distinção importa e é sutil: `mime_de()` devolver `None` para um arquivo
#: destes três NÃO é "não apurei" — é "olhei a assinatura e não é nenhum deles".
#: Quem confere uma procedência precisa saber a diferença, senão trata refutação
#: como ausência e deixa passar a declaração falsa.
FORMATOS_RECONHECIDOS: frozenset[str] = frozenset(
    {"image/png", "image/jpeg", "image/gif"})


def mime_de(dados: bytes) -> str | None:
    """O formato pela assinatura. `None` quando não é um dos três aceitos."""
    if dados.startswith(_PNG):
        return "image/png"
    if dados.startswith(_JPEG):
        return "image/jpeg"
    if dados.startswith(_GIF87) or dados.startswith(_GIF89):
        return "image/gif"
    return None


def medir(dados: bytes) -> Medida:
    """Formato e dimensão dos bytes. Ausência de resposta é `None`, nunca 0."""
    if not dados:
        return Medida()

    mime = mime_de(dados)
    par: tuple[int, int] | None = None
    if mime == "image/png":
        par = _do_png(dados)
    elif mime == "image/gif":
        par = _do_gif(dados)
    elif mime == "image/jpeg":
        par = _do_jpeg(dados)

    return Medida(
        mime=mime,
        largura=par[0] if par else None,
        altura=par[1] if par else None,
        bytes_totais=len(dados),
    )
