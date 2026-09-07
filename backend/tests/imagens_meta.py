"""Bytes de imagem REAIS para os testes do gate técnico Meta.

## Por que este módulo existe

Até 07/09/2026 as fixtures serviam `b"bytes-imagem-meta"` com
`content-type: image/jpeg` e o caminho inteiro — compilar, validar, aprovar,
criar — ficava verde. Não era descuido do teste: era o defeito F01 sendo
exercitado com sucesso. O gate lia o cabeçalho, conferia o tamanho e selava
`AUTHORIZED` / `READY_FOR_PAID_MEDIA` sobre dezessete bytes de ASCII.

Com a decodificação real em `ativos._decodificar_imagem`, uma fixture que não é
imagem passa a ser recusada — como deve. Estas funções produzem imagens de
verdade, geradas pelo Pillow que já é dependência declarada
(`backend/requirements.txt`), para que os testes de caminho feliz continuem
medindo o caminho feliz em vez de medirem a ausência do gate.

⚠️ Os bytes são gerados, não fixos em base64. Um blob colado envelhece em
silêncio: ninguém percebe quando ele deixa de descrever o que o nome promete.
"""
from __future__ import annotations

import io


def png(largura: int = 1080, altura: int = 1080, cor: tuple[int, int, int] = (18, 22, 33)) -> bytes:
    """Um PNG real e decodificável, com a dimensão pedida."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (largura, altura), cor).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg(largura: int = 1200, altura: int = 628, cor: tuple[int, int, int] = (9, 40, 90)) -> bytes:
    """Um JPEG real e decodificável."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (largura, altura), cor).save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()


def png_truncado() -> bytes:
    """Cabeçalho válido, pixels incompletos.

    Abre e mede — e é por isso que ele existe: prova que a conferência não para
    no cabeçalho. Só a decodificação completa o recusa.
    """
    return png(64, 64)[: 24 + 40]


def bomba_de_pixels() -> bytes:
    """Um PNG REAL, pequeno no fio e enorme na memória.

    12000x12000 em branco comprime para cerca de 157 KiB — passa folgado no teto
    de 12 MB de bytes — e declara 144 milhões de pixels. É o ataque que o limite
    de bytes não alcança, e por isso o teto de pixels é cobrado a partir do
    cabeçalho, antes de qualquer `load()`.
    """
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("L", (12000, 12000), 255).save(buffer, format="PNG", compress_level=9)
    return buffer.getvalue()


#: O corpo que reproduz F01: não é imagem nenhuma, e o cabeçalho HTTP mente.
NAO_E_IMAGEM = b"NOT_AN_IMAGE"
