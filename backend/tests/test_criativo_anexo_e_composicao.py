"""A fotografia real: o que entra, o que e recusado, e onde ela vai parar nos pixels.

Nenhum teste aqui abre socket, chama provider ou grava fora do `tmp_path` do
pytest. A composicao e provada olhando os PIXELS do resultado, e nao um rotulo:
a promessa "a fotografia entra sem ser regerada" so vale se der para apontar o
pixel dela na peca final.
"""

from __future__ import annotations

import io

import pytest

from app.criativo.studio import anexo as politica
from app.criativo.studio import composicao


def _imagem(largura: int, altura: int, cor=(40, 90, 160), formato="PNG") -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (largura, altura), cor).save(buffer, format=formato)
    return buffer.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# 1. O QUE PASSA
# ═══════════════════════════════════════════════════════════════════════════


def test_um_png_valido_passa_e_ganha_identidade_e_hash():
    a = politica.normalizar(_imagem(900, 700))
    assert politica.ref_valida(a.ref)
    assert a.mime == "image/png"
    assert (a.largura, a.altura) == (900, 700)
    assert len(a.content_sha256) == 64
    int(a.content_sha256, 16)


def test_o_hash_publicado_e_o_dos_bytes_NORMALIZADOS():
    """A autorizacao e assinada contra ele e o compositor usa ele.

    Publicar o hash do arquivo original faria a autorizacao cobrir bytes que
    ninguem processa.
    """
    import hashlib

    original = _imagem(600, 400, formato="JPEG")
    a = politica.normalizar(original)
    assert a.content_sha256 == hashlib.sha256(a.conteudo).hexdigest()


def test_jpeg_e_webp_tambem_passam():
    assert politica.normalizar(_imagem(600, 600, formato="JPEG")).mime == "image/jpeg"
    assert politica.normalizar(_imagem(600, 600, formato="WEBP")).mime == "image/webp"


def test_a_ref_e_sorteada_e_nao_derivada_do_conteudo():
    """Ref derivada do hash seria um oraculo de existencia de graca."""
    bytes_iguais = _imagem(500, 500)
    assert (
        politica.normalizar(bytes_iguais).ref
        != politica.normalizar(bytes_iguais).ref
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. O QUE E RECUSADO — cada recusa e uma classe de defeito com nome
# ═══════════════════════════════════════════════════════════════════════════


def test_arquivo_vazio_e_recusado():
    with pytest.raises(politica.AnexoRecusado):
        politica.normalizar(b"")


def test_arquivo_que_nao_e_imagem_e_recusado_pelos_BYTES():
    """Um executavel com nome de PNG passaria por qualquer checagem de extensao."""
    with pytest.raises(politica.AnexoRecusado):
        politica.normalizar(b"MZ\x90\x00" + b"\x00" * 4096)


def test_gif_e_reconhecido_para_ser_recusado_com_nome():
    """Reconhecer para RECUSAR e melhor que nao reconhecer."""
    with pytest.raises(politica.AnexoRecusado) as capturado:
        politica.normalizar(_imagem(500, 500, formato="GIF"))
    assert "PNG" in str(capturado.value)


def test_mime_declarado_que_nao_bate_com_os_bytes_e_recusado():
    """O `Content-Type` do multipart e escrito pelo cliente."""
    with pytest.raises(politica.AnexoRecusado):
        politica.normalizar(_imagem(500, 500), mime_declarado="image/jpeg")


def test_arquivo_acima_do_teto_de_bytes_e_recusado_antes_de_decodificar():
    grande = b"\x89PNG\r\n\x1a\n" + b"\x00" * (politica.TETO_DE_BYTES + 1)
    with pytest.raises(politica.AnexoRecusado) as capturado:
        politica.normalizar(grande)
    assert "MB" in str(capturado.value)


def test_decompression_bomb_e_recusada_pelo_TETO_DE_PIXELS():
    """Um PNG de poucos KB pode declarar 30000x30000 e explodir em ~3,6 GB.

    O arquivo passa em qualquer teto de BYTES; o teto que barra e o de PIXELS, e
    ele e conferido no cabecalho, antes de decodificar.
    """
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None  # a guarda global do Pillow nao pode ser a nossa
    lados = int((politica.TETO_DE_PIXELS ** 0.5)) + 500
    buffer = io.BytesIO()
    Image.new("L", (lados, lados), 0).save(buffer, format="PNG")

    with pytest.raises(politica.AnexoRecusado) as capturado:
        politica.normalizar(buffer.getvalue())
    assert "pixels" in str(capturado.value)


def test_arquivo_truncado_e_recusado_em_vez_de_virar_metade_cinza():
    """Um JPEG cortado decodifica "com sucesso" e produz metade cinza.

    Uma peca paga composta sobre metade cinza e pior que uma recusa.
    """
    inteiro = _imagem(1200, 900, formato="JPEG")
    with pytest.raises(politica.AnexoRecusado):
        politica.normalizar(inteiro[: len(inteiro) // 2])


def test_imagem_pequena_demais_e_recusada():
    with pytest.raises(politica.AnexoRecusado) as capturado:
        politica.normalizar(_imagem(200, 200))
    assert str(politica.LADO_MINIMO) in str(capturado.value)


# ═══════════════════════════════════════════════════════════════════════════
# 3. EXIF — sai da foto antes de a foto sair daqui
# ═══════════════════════════════════════════════════════════════════════════


def test_o_exif_e_removido_e_a_orientacao_e_aplicada_aos_pixels():
    """GPS, numero de serie e nome do autor nao precisam ir para um provider.

    E aplicar a orientacao SEM remover a tag giraria a imagem duas vezes na
    proxima biblioteca que a respeitasse.
    """
    from PIL import Image

    original = Image.new("RGB", (800, 600), (10, 20, 30))
    exif = original.getexif()
    exif[274] = 6  # Orientation: girar 90 graus
    exif[271] = "FabricanteDaCamera"
    buffer = io.BytesIO()
    original.save(buffer, format="JPEG", exif=exif)

    a = politica.normalizar(buffer.getvalue())
    assert a.exif_removido is True
    # A orientacao 6 troca largura e altura AO SER APLICADA.
    assert (a.largura, a.altura) == (600, 800)
    with Image.open(io.BytesIO(a.conteudo)) as limpa:
        assert not limpa.getexif()
    assert b"FabricanteDaCamera" not in a.conteudo


# ═══════════════════════════════════════════════════════════════════════════
# 4. A CHAVE DE ARMAZENAMENTO
# ═══════════════════════════════════════════════════════════════════════════


def test_a_chave_leva_o_dono_no_primeiro_nivel():
    dono = "11111111-1111-4111-8111-111111111111"
    chave = politica.chave_de_anexo(dono, politica.nova_ref(), "png")
    assert chave.startswith(f"criativos/anexos/{dono}/")


def test_a_chave_recusa_ref_forjada():
    with pytest.raises(politica.AnexoRecusado):
        politica.chave_de_anexo("dono", "../../etc/passwd", "png")


def test_a_chave_nao_carrega_caractere_que_escape_do_diretorio():
    chave = politica.chave_de_anexo("../../etc", politica.nova_ref(), "png")
    assert ".." not in chave


# ═══════════════════════════════════════════════════════════════════════════
# 5. COMPOSICAO — os pixels da foto estao MESMO na peca
# ═══════════════════════════════════════════════════════════════════════════


def _pixel(dados: bytes, x: int, y: int):
    from PIL import Image

    with Image.open(io.BytesIO(dados)) as img:
        return img.convert("RGB").getpixel((x, y))


@pytest.mark.parametrize("slot", ["1x1", "4x5", "9x16", "1.91x1"])
def test_a_fotografia_real_ocupa_a_regiao_declarada(slot):
    from app.criativo import dominio

    formato = dominio.formato_de(slot)
    fundo = _imagem(formato.largura, formato.altura, (0, 255, 0))
    foto = _imagem(1200, 900, (255, 0, 0))

    c = composicao.compor(
        fundo=fundo,
        foto=foto,
        slot=slot,
        largura=formato.largura,
        altura=formato.altura,
    )
    assert (c.largura, c.altura) == (formato.largura, formato.altura)

    x, y, largura, altura = c.regiao
    # O centro da regiao e VERMELHO: sao os pixels da foto, nao uma reinterpretacao.
    assert _pixel(c.conteudo, x + largura // 2, y + altura // 2) == (255, 0, 0)


def test_o_fundo_gerado_sobrevive_fora_da_regiao_da_foto():
    fundo = _imagem(1080, 1080, (0, 255, 0))
    foto = _imagem(1200, 900, (255, 0, 0))
    c = composicao.compor(fundo=fundo, foto=foto, slot="1x1", largura=1080, altura=1080)
    _, y, _, altura = c.regiao
    # Abaixo da regiao da foto continua sendo o que o modelo compos.
    assert _pixel(c.conteudo, 540, min(1079, y + altura + 40)) == (0, 255, 0)


def test_a_composicao_e_deterministica():
    """Mesma entrada, mesmos bytes. E o que permite o recibo afirmar o que afirma."""
    args = dict(
        fundo=_imagem(1080, 1350, (9, 9, 9)),
        foto=_imagem(800, 600, (1, 2, 3)),
        slot="4x5",
        largura=1080,
        altura=1350,
    )
    assert (
        composicao.compor(**args).content_sha256
        == composicao.compor(**args).content_sha256
    )


def test_a_caixa_do_recorte_e_registrada_em_coordenadas_da_FOTO():
    """"Que pedaco da minha foto foi usado?" so faz sentido no sistema da foto."""
    c = composicao.compor(
        fundo=_imagem(1080, 1920, (0, 0, 0)),
        foto=_imagem(1200, 900, (255, 0, 0)),
        slot="9x16",
        largura=1080,
        altura=1920,
    )
    x, y, largura, altura = c.crop
    assert 0 <= x and 0 <= y
    assert x + largura <= 1200 + 1
    assert y + altura <= 900 + 1
    assert c.escala > 0
    assert c.compositor == composicao.COMPOSITOR
    assert c.compositor_versao == composicao.COMPOSITOR_VERSAO


def test_a_foto_nao_e_deformada():
    """`cover` escala pelo lado que falta; `resize` direto esticaria."""
    from PIL import Image

    # Uma foto com listras verticais: deformacao horizontal muda a largura delas.
    origem = Image.new("RGB", (1000, 1000), (255, 255, 255))
    for x in range(0, 1000, 100):
        for y in range(1000):
            for dx in range(50):
                origem.putpixel((x + dx, y), (0, 0, 0))
    buffer = io.BytesIO()
    origem.save(buffer, format="PNG")

    c = composicao.compor(
        fundo=_imagem(1080, 1080, (200, 200, 200)),
        foto=buffer.getvalue(),
        slot="1x1",
        largura=1080,
        altura=1080,
    )
    # A escala e um numero SO: se houvesse deformacao, haveria dois.
    assert isinstance(c.escala, float)
    x, y, largura, altura = c.regiao
    # A regiao 1x1 e mais larga que alta, entao `cover` escala pela largura e
    # recorta a altura: a largura da foto cabe inteira.
    assert c.crop[2] == pytest.approx(1000, abs=2)


def test_todo_slot_do_catalogo_tem_regiao_declarada():
    """Um slot sem layout cairia no padrao sem ninguem perceber."""
    from app.criativo import dominio

    for formato in dominio.FORMATOS:
        assert formato.slot in composicao.REGIOES, (
            f"{formato.slot} nao tem regiao declarada e usaria o layout do 1x1"
        )


def test_a_instrucao_de_fundo_pede_a_regiao_vazia_e_nao_manda_a_foto():
    """No modo hibrido o modelo NAO recebe a fotografia.

    Manda-la como referencia faria ele desenhar uma pessoa parecida, e a peca
    final teria duas: a desenhada e a colada.
    """
    texto = composicao.instrucao_de_fundo("4x5")
    assert "fundo liso" in texto
    assert "sem pessoas" in texto
