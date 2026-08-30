"""Testes do medidor de imagem — e sobretudo do que ele se RECUSA a medir.

Rodar da raiz do projeto:
    PYTHONPATH=. backend/.venv/bin/python -m pytest volc_ads/criativo/testes_medir_imagem.py -q

Os cabeçalhos aqui são construídos byte a byte, não lidos de arquivo: um teste
que depende de um `.png` no disco prova que o arquivo existe, não que o parser
lê o cabeçalho. E são cabeçalhos REAIS — se o parser quebrar, estes testes
falham, o que é exatamente o que um teste de parser deve fazer.

O grupo que mais importa é o último: `0` não é medida. É o defeito que este
arquivo existe para impedir, e ele tem um caso concreto no próprio repo — o
helper `_png()` de `campanha/testes_display.py:718` produz um PNG de assinatura
válida e IHDR zerado.
"""

from __future__ import annotations

import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from volc_ads.criativo.adaptadores import medir_imagem  # noqa: E402


# ── construtores de cabeçalho de verdade ────────────────────────────────────


def png(largura: int, altura: int, *, cauda: bytes = b"") -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", largura, altura)
        + b"\x08\x06\x00\x00\x00"
        + cauda
    )


def gif(largura: int, altura: int) -> bytes:
    return b"GIF89a" + struct.pack("<HH", largura, altura) + b"\x00" * 7


def jpeg(largura: int, altura: int, *, marcador: int = 0xC0,
         antes: bytes = b"") -> bytes:
    sof = (
        b"\xff" + bytes([marcador])
        + struct.pack(">H", 17)
        + b"\x08"
        + struct.pack(">HH", altura, largura)   # altura ANTES da largura
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    )
    return b"\xff\xd8" + antes + sof


# ── os três formatos aceitos ────────────────────────────────────────────────


def test_png_da_largura_e_altura_do_ihdr():
    m = medir_imagem.medir(png(1200, 628))
    assert m.mime == "image/png"
    assert (m.largura, m.altura) == (1200, 628)
    assert m.dimensionada


def test_gif_e_little_endian_e_nao_se_confunde_com_o_png():
    # 1200 = 0x04B0. Em little-endian são os bytes b0 04; lido como big-endian
    # daria 45060. Se este teste passar com o número certo, a ordem está certa.
    m = medir_imagem.medir(gif(1200, 628))
    assert m.mime == "image/gif"
    assert (m.largura, m.altura) == (1200, 628)


def test_jpeg_le_altura_antes_da_largura():
    # O SOF do JPEG guarda altura ANTES de largura. Trocar as duas passaria
    # despercebido num quadrado — por isso o caso é retangular e assimétrico.
    m = medir_imagem.medir(jpeg(1200, 628))
    assert m.mime == "image/jpeg"
    assert (m.largura, m.altura) == (1200, 628), "altura e largura trocadas"


def test_jpeg_atravessa_segmentos_ate_achar_o_sof():
    # Um JPEG real começa com APP0/EXIF antes do SOF. Um parser que olhasse só
    # o primeiro segmento devolveria None para praticamente todo JPEG do mundo.
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    m = medir_imagem.medir(jpeg(600, 314, antes=app0))
    assert (m.largura, m.altura) == (600, 314)


def test_jpeg_progressivo_tambem_e_sof():
    # 0xC2 é SOF2 (progressivo) e é comuníssimo. Cobrir só 0xC0 deixaria
    # metade dos arquivos reais sem medida.
    m = medir_imagem.medir(jpeg(300, 300, marcador=0xC2))
    assert (m.largura, m.altura) == (300, 300)


def test_marcadores_que_parecem_sof_e_nao_sao_nao_viram_medida():
    # 0xC4 é tabela de Huffman, não SOF. Lê-lo como SOF devolveria dois
    # inteiros quaisquer — medida inventada, que é pior que medida ausente.
    m = medir_imagem.medir(jpeg(300, 300, marcador=0xC4))
    assert m.mime == "image/jpeg"
    assert m.largura is None and m.altura is None


# ── formato desconhecido: mime ausente, não mime errado ─────────────────────


def test_formato_nao_reconhecido_nao_recebe_mime_chutado():
    m = medir_imagem.medir(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    assert m.mime is None
    assert m.largura is None and m.altura is None
    assert m.bytes_totais == 16   # o tamanho é sabido mesmo sem reconhecer


def test_vazio_e_ausencia_inteira_inclusive_de_tamanho():
    m = medir_imagem.medir(b"")
    assert m.mime is None
    assert m.largura is None and m.altura is None
    # Zero byte é ausência de arquivo, não um arquivo que mede zero.
    assert m.bytes_totais is None


# ── o grupo que dá nome ao arquivo: 0 NÃO é medida ──────────────────────────


def test_o_png_sintetico_dos_testes_da_casa_nao_vira_medida_zero():
    # Este é literalmente o `_png()` de `campanha/testes_display.py:718`:
    # assinatura válida, IHDR todo zero. Um medidor ingênuo diria 0x0.
    sintetico = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    m = medir_imagem.medir(sintetico)
    assert m.mime == "image/png", "a assinatura É de PNG e isso é um fato"
    assert m.largura is None, "0 no cabeçalho é ausência de medida, não medida 0"
    assert m.altura is None
    assert not m.dimensionada


def test_dimensao_zero_declarada_tambem_e_ausencia():
    for dados in (png(0, 628), png(1200, 0), gif(0, 0), jpeg(0, 100)):
        m = medir_imagem.medir(dados)
        assert m.largura is None and m.altura is None, (
            f"{m.mime}: dimensão 0 escapou como número")


def test_cabecalho_truncado_nao_inventa_numero():
    # Assinatura completa, IHDR pela metade. `struct.unpack` levantaria; a
    # guarda de tamanho tem de vir antes.
    m = medir_imagem.medir(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\r" + b"IHDR" + b"\x00\x00")
    assert m.mime == "image/png"
    assert m.largura is None and m.altura is None


def test_a_medida_util_sobrevive_ao_lixo_depois_do_cabecalho():
    # Garante que a guarda de truncamento não é agressiva demais: bytes extras
    # depois do IHDR são o caso NORMAL de um PNG de verdade.
    m = medir_imagem.medir(png(600, 314, cauda=b"\xde\xad\xbe\xef" * 40))
    assert (m.largura, m.altura) == (600, 314)


# ── o medidor não conhece canal, e é bom que não conheça ────────────────────


def test_medir_nao_julga_proporcao_nem_dimensao_minima():
    """Uma imagem 1x1 é medida sem reclamação: julgar é de `validacao.py`.

    Se o medidor começasse a reprovar, existiriam duas réguas de geometria — e
    a que o operador desligaria seria justamente a que mede.
    """
    m = medir_imagem.medir(png(1, 1))
    assert (m.largura, m.altura) == (1, 1)
    assert m.dimensionada


def test_sof_que_nao_comporta_a_dimensao_nao_inventa_uma():
    """GUARDA DE REGRESSÃO do achado MÉDIO da revisão adversarial de 27/08.

    Um SOF declara `length=3` — ou seja, o segmento acaba antes de onde a
    altura e a largura deveriam estar. A leitura invadia o segmento SEGUINTE e
    devolvia o marcador e o comprimento dele como se fossem a dimensão:

        Medida(mime='image/jpeg', largura=16, altura=65504, bytes_totais=25)

    Aqueles bytes são `\\xff\\xe0` (APP0) e `\\x00\\x10` (o length dele). Pillow
    recusa o mesmo arquivo com `UnidentifiedImageError`.

    A guarda de fim de buffer não pegava, e é por isso que o defeito passou: os
    bytes EXISTIAM — só não eram desta dimensão. O SOF precisa de 7 bytes
    (length 2 + precisão 1 + altura 2 + largura 2) para responder a pergunta.
    """
    app0_depois = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    curto = (b"\xff\xd8" + b"\xff\xc0" + struct.pack(">H", 3) + b"\x08"
             + app0_depois)
    m = medir_imagem.medir(curto)
    assert m.mime == "image/jpeg", "a assinatura é de JPEG e isso continua sendo fato"
    assert m.largura is None and m.altura is None, (
        f"dimensão inventada do segmento seguinte: {m.largura}x{m.altura}")


def test_o_sof_no_limite_exato_do_SPEC_ainda_mede():
    """A guarda não pode ser agressiva demais: 11 é o mínimo REAL e tem de passar.

    ⚠️ A primeira versão deste teste exigia que `length=7` medisse — e com isso
    CONGELOU O BURACO COMO CONTRATO. O spec do JPEG diz que um SOF vale
    `8 + 3·Nf` bytes com `Nf >= 1`, ou seja, no mínimo 11; `7` é um segmento
    impossível, e o teste anterior obrigava o parser a tratá-lo como fonte de
    medida. A revisão adversarial de 27/08/2026 mostrou que essa exigência era
    o próprio defeito, com outra roupa.
    """
    # Lf(2) + P(1) + Y(2) + X(2) + Nf(1) + 3·Nf = 11 com um componente.
    # ⚠️ O byte `Nf` é fácil de esquecer ao montar a fixture à mão, e esquecê-lo
    # produz um segmento de 10 que a guarda recusa — com razão.
    um_componente = (b"\xff\xd8" + b"\xff\xc0" + struct.pack(">H", 11) + b"\x08"
                     + struct.pack(">HH", 314, 600) + b"\x01"
                     + b"\x01\x11\x00")
    m = medir_imagem.medir(um_componente)
    assert (m.largura, m.altura) == (600, 314)


def test_sof_com_comprimento_impossivel_pelo_spec_nao_mede():
    """GUARDA DE REGRESSÃO do ALTO-A: `tamanho` é declarado pelo próprio segmento.

    Exigir `tamanho >= 7` — o mínimo ARITMÉTICO dos campos que se quer ler —
    é confiar no atacante: basta declarar 7. Reproduzido em 27/08/2026:

        arquivo de 11 bytes      -> Medida(largura=1200, altura=628)
        SOF length=7 + APP0      -> Medida(largura=16, altura=65504)

    `16` e `65504` são o marcador `\xff\xe0` do APP0 seguinte e o comprimento
    dele. O mínimo que vale é o do SPEC: 11.
    """
    onze_bytes = (b"\xff\xd8" + b"\xff\xc0" + struct.pack(">H", 7) + b"\x08"
                  + struct.pack(">HH", 628, 1200))
    m = medir_imagem.medir(onze_bytes)
    assert m.mime == "image/jpeg"
    assert m.largura is None and m.altura is None, (
        f"segmento impossível virou medida: {m.largura}x{m.altura}")

    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    invadindo = (b"\xff\xd8" + b"\xff\xc0" + struct.pack(">H", 7) + b"\x08" + app0)
    m2 = medir_imagem.medir(invadindo)
    assert m2.largura is None and m2.altura is None, (
        f"leu o segmento seguinte como dimensão: {m2.largura}x{m2.altura}")


def test_sof_que_nao_cabe_no_arquivo_nao_mede():
    """`length` maior que o arquivo é cabeçalho truncado, não medida.

    Reproduzido: `length=60000` num arquivo de 11 bytes devolvia `600x314` —
    os bytes estavam lá por acaso, e um número sem origem é pior que ausência.
    """
    truncado = (b"\xff\xd8" + b"\xff\xc0" + struct.pack(">H", 60000) + b"\x08"
                + struct.pack(">HH", 314, 600))
    m = medir_imagem.medir(truncado)
    assert m.mime == "image/jpeg"
    assert m.largura is None and m.altura is None


def test_o_arquivo_de_11_bytes_nao_atravessa_a_ponte():
    """O ALTO-A ponta a ponta: 11 bytes de não-imagem NÃO viram payload.

    Antes da correção este arquivo entrava em `ImagensDisplay.marketing` com
    `confirmada: True` e o CLI saía com 0.
    """
    import sys as _sys
    _sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from volc_ads import criativo_ponte as _ponte
    from volc_ads.criativo.contrato import (
        Asset, LoteDeAssets, Procedencia, TipoDeAsset, hash_de_conteudo)
    from datetime import datetime, timezone

    falso = (b"\xff\xd8" + b"\xff\xc0" + struct.pack(">H", 7) + b"\x08"
             + struct.pack(">HH", 628, 1200))
    medida = medir_imagem.medir(falso)
    assert medida.largura is None, "premissa: o medidor já não é enganado"

    quando = datetime(2026, 8, 27, tzinfo=timezone.utc)
    asset = Asset(
        tipo=TipoDeAsset.IMAGEM_MARKETING,
        procedencia=Procedencia(motor="m", versao_do_motor="1", insumo="i",
                                quando=quando),
        conteudo_hash=hash_de_conteudo(falso), bytes_totais=len(falso),
        mime=medida.mime, largura=medida.largura, altura=medida.altura)
    e = _ponte.imagens_de_display(
        LoteDeAssets(canal="DISPLAY", assets=(asset,)), {asset.identidade: falso})

    # ⚠️ `imagens is None` NÃO discrimina: este lote tem um asset só, e Display
    # exige também a quadrada — um PNG PERFEITO daria `None` pelo mesmo assert.
    # A revisão adversarial mediu isso. O que discrimina é o veredito, e é ele
    # que este teste passa a exigir.
    codigos = {v.codigo for v in e.veredito.violacoes}
    assert "M1.sem_medida" in codigos, (
        f"o arquivo de 11 bytes foi MEDIDO em vez de recusado: {codigos}")
    assert asset in e.veredito.reprovados
    assert e.imagens is None

    # E a contraprova, no mesmo teste: um PNG legítimo NÃO produz M1.
    bom = png(1200, 628, cauda=b"real")
    asset_bom = Asset(
        tipo=TipoDeAsset.IMAGEM_MARKETING,
        procedencia=Procedencia(motor="m", versao_do_motor="1", insumo="i",
                                quando=quando),
        conteudo_hash=hash_de_conteudo(bom), bytes_totais=len(bom),
        mime="image/png", largura=1200, altura=628)
    e2 = _ponte.imagens_de_display(
        LoteDeAssets(canal="DISPLAY", assets=(asset_bom,)),
        {asset_bom.identidade: bom})
    assert "M1.sem_medida" not in {v.codigo for v in e2.veredito.violacoes}, (
        "o teste não distingue o defeito da falta da imagem quadrada")


def _sof(largura: int, altura: int, marcador: int = 0xC0) -> bytes:
    """Um SOF minimo e BEM FORMADO: Lf=11 com um componente."""
    return (b"\xff" + bytes([marcador]) + struct.pack(">H", 11) + b"\x08"
            + struct.pack(">HH", altura, largura) + b"\x01" + b"\x01\x11\x00")


_SOS = b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00"


def test_com_dois_SOF_o_ULTIMO_vence_como_no_decodificador():
    """GUARDA do achado 9 do ciclo 3 da revisao adversarial.

    Parar no primeiro SOF devolvia 1200x628 enquanto o Pillow, sobre o MESMO
    arquivo, devolvia 300x250. O numero nao descrevia o arquivo — e o portao de
    geometria e o `confirmada: true` eram emitidos sobre ele.
    """
    dois = b"\xff\xd8" + _sof(1200, 628) + _sof(300, 250) + _SOS
    m = medir_imagem.medir(dois)
    assert (m.largura, m.altura) == (300, 250), (
        f"o primeiro SOF venceu: {m.largura}x{m.altura}")


def test_um_SOF_so_continua_medindo():
    """A contraprova: a mudanca nao pode quebrar o caso normal."""
    um = b"\xff\xd8" + _sof(600, 314) + _SOS
    m = medir_imagem.medir(um)
    assert (m.largura, m.altura) == (600, 314)


def test_SOF_depois_do_SOS_nao_conta():
    """Depois do Start of Scan sao dados comprimidos; um `\xff\xc0` ali e ruido."""
    depois = b"\xff\xd8" + _sof(600, 314) + _SOS + _sof(9999, 9999)
    m = medir_imagem.medir(depois)
    assert (m.largura, m.altura) == (600, 314)


def test_arquivo_sem_SOF_nenhum_nao_inventa():
    sem = b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9 + _SOS
    m = medir_imagem.medir(sem)
    assert m.mime == "image/jpeg"
    assert m.largura is None and m.altura is None


def test_EOI_no_meio_nao_faz_o_parser_ler_comprimento_que_nao_existe():
    """GUARDA do MEDIO do ciclo 4 — o unico modo de falha que este arquivo
    nao pode ter e devolver NUMERO ERRADO em vez de ausencia.

    `0xD9` (EOI) faltava na lista de marcadores sem payload. O parser lia os
    dois bytes seguintes como comprimento e saltava para fora do arquivo,
    devolvendo o SOF ANTERIOR. Medido: `FFD8 + SOF(1200x628) + FFD9 +
    SOF(300x250) + SOS` dava 1200x628, e o Pillow le 300x250 — e o portao de
    geometria mais o `confirmada: true` eram emitidos sobre o numero errado.
    """
    com_eoi = (b"\xff\xd8" + _sof(1200, 628) + b"\xff\xd9"
               + _sof(300, 250) + _SOS)
    m = medir_imagem.medir(com_eoi)
    assert (m.largura, m.altura) == (300, 250), (
        f"o EOI foi lido como segmento com comprimento: {m.largura}x{m.altura}")


def test_os_marcadores_sem_payload_sao_os_do_spec():
    """SOI, EOI, TEM e os oito RSTn. Um a menos vira leitura de lixo."""
    assert medir_imagem._SEM_PAYLOAD == frozenset({0x01, 0xD8, 0xD9})
    for rst in range(0xD0, 0xD8):
        entre = (b"\xff\xd8" + b"\xff" + bytes([rst]) + _sof(600, 314) + _SOS)
        m = medir_imagem.medir(entre)
        assert (m.largura, m.altura) == (600, 314), f"RST {rst:#x} quebrou"


def test_segmento_com_comprimento_impossivel_nao_apaga_medida_ja_obtida():
    """GUARDA do BAIXO-4: recusar o legitimo tambem e defeito.

    Ate o ciclo 3 o SOF retornava na hora. Ao passar a acumular, um segmento
    posterior com `length=0` passou a devolver `None` e a jogar fora uma medida
    boa: `SOF(600x314)` + `FFE0 0000` dava ausencia, e o Pillow lia 600x314.
    """
    depois = b"\xff\xd8" + _sof(600, 314) + b"\xff\xe0\x00\x00" + _SOS
    m = medir_imagem.medir(depois)
    assert (m.largura, m.altura) == (600, 314), (
        "a medida ja obtida foi descartada por um segmento posterior torto")

    # E sem SOF nenhum antes do segmento torto, continua sendo ausencia.
    sem = b"\xff\xd8" + b"\xff\xe0\x00\x00" + _SOS
    m2 = medir_imagem.medir(sem)
    assert m2.largura is None and m2.altura is None
