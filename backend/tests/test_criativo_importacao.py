"""A importação privada de mídia, provada sem rede, sem banco e sem a Meta.

## O que estas provas afirmam

Cada regra de `SPEC.json → media_contract.zip.rules` tem aqui pelo menos um
teste que a REPRODUZ — o ataque é montado, executado, e o resultado é medido.
Uma regra escrita num comentário e não exercitada é uma regra que não existe:
ela não sobrevive à primeira refatoração de quem não leu o comentário.

O caso mais importante é o último bloco: um dublê de `httpx.AsyncClient` que
LEVANTA se alguém o construir, e um `socket.socket.connect` que levanta se
alguém tentar abrir conexão. Com os dois armados, o `POST` completo roda e
responde 200. É assim que "importar arquivo não chama Meta" deixa de ser
afirmação e vira medida.

## Hermetismo

Nada aqui toca `httpx` de verdade, Supabase, disco fora do `tmp_path` ou o
provedor de identidade. O banco é um dublê que **transcreve as CHECKs da
migration** — se o router montar uma linha que o Postgres recusaria, o dublê
recusa primeiro, e o defeito aparece na suíte em vez de aparecer no deploy.
"""

from __future__ import annotations

import io
import re
import socket
import struct
import time
import zipfile
from typing import Any

import pytest

from app.criativo import importacao as imp

# ═══════════════════════════════════════════════════════════════════════════
# Fábricas de bytes de verdade
# ═══════════════════════════════════════════════════════════════════════════


def _png(largura: int = 8, altura: int = 8, *, texto: str | None = None) -> bytes:
    from PIL import Image, PngImagePlugin

    img = Image.new("RGB", (largura, altura), (200, 30, 30))
    info = PngImagePlugin.PngInfo()
    if texto:
        info.add_text("Comment", texto)
    buf = io.BytesIO()
    img.save(buf, "PNG", pnginfo=info)
    return buf.getvalue()


def _png_ruidoso(lado: int = 64) -> bytes:
    """PNG que NÃO comprime: cor sólida vira 100 bytes e não serve de teto."""
    import os as _os

    from PIL import Image

    buf = io.BytesIO()
    Image.frombytes("RGB", (lado, lado), _os.urandom(lado * lado * 3)).save(buf, "PNG")
    return buf.getvalue()


def _jpeg(largura: int = 16, altura: int = 16, *, descricao: str | None = None) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (largura, altura), (10, 120, 200))
    buf = io.BytesIO()
    if descricao:
        exif = img.getexif()
        exif[0x010E] = descricao  # ImageDescription — o lugar mais fácil de ver
        img.save(buf, "JPEG", exif=exif.tobytes())
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def _webp(largura: int = 16, altura: int = 16) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), (5, 200, 90)).save(buf, "WEBP")
    return buf.getvalue()


def _box(tipo: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + tipo + payload


def _mp4(
    *, largura: int = 1080, altura: int = 1920, duracao_ms: int = 15_000,
    amostras: int = 450, localizacao: bool = False,
) -> bytes:
    """Um MP4 mínimo, com os boxes que `medir_mp4` lê. Sem codec, sem ffmpeg."""
    ftyp = _box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isomiso2mp41")
    mvhd = _box(b"mvhd", b"\x00\x00\x00\x00" + b"\x00" * 8
                + struct.pack(">II", 1000, duracao_ms) + b"\x00" * 80)
    tkhd = _box(b"tkhd", b"\x00\x00\x00\x00" + b"\x00" * 20 + b"\x00" * 52
                + struct.pack(">II", largura << 16, altura << 16))
    stsz = _box(b"stsz", b"\x00\x00\x00\x00" + struct.pack(">II", 0, amostras))
    stbl = _box(b"stbl", stsz)
    minf = _box(b"minf", stbl)
    mdia = _box(b"mdia", minf)
    trak = _box(b"trak", tkhd + mdia)
    filhos = mvhd + trak
    if localizacao:
        filhos += _box(b"udta", _box(b"\xa9xyz", b"\x00\x0b\x15+25.0-46.6/"))
    moov = _box(b"moov", filhos)
    mdat = _box(b"mdat", b"\x00" * 512)
    return ftyp + moov + mdat


def _pdf() -> bytes:
    """Bytes de PDF de verdade — a assinatura é o que importa."""
    return b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


def _gif() -> bytes:
    return b"GIF89a" + struct.pack("<HH", 4, 4) + b"\x00" * 20


# ── ZIPs, incluindo os maliciosos ───────────────────────────────────────────


def _zip(entradas: list[tuple[Any, bytes]], *, compressao: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compressao) as zf:
        for nome, dados in entradas:
            zf.writestr(nome, dados)
    return buf.getvalue()


def _zip_com_symlink() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("foto.png", _png())
        zi = zipfile.ZipInfo("atalho.png")
        # `S_IFLNK | 0777` nos 16 bits altos — como o `zip` do Unix grava.
        zi.external_attr = (0o120777 & 0xFFFF) << 16
        zf.writestr(zi, "/etc/passwd")
    return buf.getvalue()


def _marcar_como_criptografado(dados: bytes) -> bytes:
    """Liga o bit 0 de `flag_bits` no cabeçalho local E no diretório central.

    ⚠️ Feito nos BYTES e não pela API: `zipfile` não escreve ZIP com senha, e
    depender de qual campo interno ele preserva amarraria a prova ao detalhe de
    implementação da stdlib. Um atacante também mexe nos bytes.
    """
    saida = bytearray(dados)
    local = saida.find(b"PK\x03\x04")
    central = saida.find(b"PK\x01\x02")
    assert local >= 0 and central >= 0, "ZIP de prova sem os dois cabeçalhos"
    saida[local + 6] |= 0x01
    saida[central + 8] |= 0x01
    return bytes(saida)


# ═══════════════════════════════════════════════════════════════════════════
# 1. OS LIMITES SÃO OS DA SPEC, E SÓ DÁ PARA APERTÁ-LOS
# ═══════════════════════════════════════════════════════════════════════════


def test_os_limites_padrao_sao_exatamente_os_da_spec():
    """Os seis números de `media_contract.zip`, transcritos sem arredondamento."""
    p = imp.LIMITES_PADRAO
    assert p.entradas_max == 50
    assert p.comprimido_bytes_max == 104_857_600
    assert p.expandido_bytes_max == 262_144_000
    assert p.razao_de_expansao_max == 100
    assert p.imagem_bytes_max == 26_214_400
    assert p.video_bytes_max == 209_715_200


def test_limite_injetado_aperta_mas_nunca_afrouxa():
    """Um chamador pode pedir menos. Pedir mais é silenciosamente cortado.

    Sem isto, os limites parametrizados seriam uma porta: bastaria alguém
    construir `Limites(expandido_bytes_max=10**12)` para a defesa sumir.
    """
    frouxo = imp.Limites(expandido_bytes_max=10**12, entradas_max=10_000)
    assert frouxo.expandido_bytes_max == imp.TETO_EXPANDIDO_BYTES
    assert frouxo.entradas_max == imp.TETO_ENTRADAS

    apertado = imp.Limites(expandido_bytes_max=1024, entradas_max=2)
    assert apertado.expandido_bytes_max == 1024
    assert apertado.entradas_max == 2


def test_limite_nao_positivo_e_recusado():
    with pytest.raises(ValueError):
        imp.Limites(entradas_max=0)


# ═══════════════════════════════════════════════════════════════════════════
# 2. O ARCHIVE MALICIOSO CAI INTEIRO
# ═══════════════════════════════════════════════════════════════════════════


def test_zipbomb_pela_razao_de_expansao_derruba_o_archive():
    """8 MB de zeros num ZIP de poucos KB: razão ~1000:1, teto 100:1.

    ⚠️ A recusa acontece pelo DIRETÓRIO CENTRAL, antes de um byte ser
    descomprimido — que é o ponto inteiro da regra "limite agregado antes de
    alocar". Se ela dependesse de expandir para medir, a bomba já teria
    explodido quando o número aparecesse.
    """
    bomba = _zip([("zeros.bin", b"\x00" * (8 * 1024 * 1024))])
    assert len(bomba) < 100 * 1024, "o ZIP de prova precisa ser MUITO menor que a saída"
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(bomba)
    assert e.value.codigo == imp.ARCHIVE_RAZAO_DE_EXPANSAO


def test_expansao_acima_do_teto_agregado_derruba_o_archive():
    """O agregado vale mesmo quando a razão é honesta (dados incompressíveis)."""
    import os as _os

    ruido = _os.urandom(64 * 1024)
    arquivo = _zip([("a.bin", ruido)], compressao=zipfile.ZIP_STORED)
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(arquivo, limites=imp.Limites(expandido_bytes_max=1024))
    assert e.value.codigo == imp.ARCHIVE_EXPANSAO_GRANDE_DEMAIS


def test_traversal_derruba_o_archive():
    arquivo = _zip([("ok.png", _png()), ("../../fora.png", _png())])
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(arquivo)
    assert e.value.codigo == imp.ARCHIVE_TRAVERSAL


def test_caminho_absoluto_derruba_o_archive():
    arquivo = _zip([("/etc/cron.d/x.png", _png())])
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(arquivo)
    assert e.value.codigo == imp.ARCHIVE_CAMINHO_ABSOLUTO


def test_caminho_com_unidade_do_windows_derruba_o_archive():
    arquivo = _zip([("C:/Windows/x.png", _png())])
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(arquivo)
    assert e.value.codigo == imp.ARCHIVE_CAMINHO_ABSOLUTO


def test_symlink_derruba_o_archive():
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(_zip_com_symlink())
    assert e.value.codigo == imp.ARCHIVE_SYMLINK


def test_archive_aninhado_derruba_o_archive():
    """ZIP dentro de ZIP: cada camada respeita o teto, o produto final não."""
    dentro = _zip([("bomba.bin", b"\x00" * (1024 * 1024))])
    fora = _zip([("foto.png", _png()), ("dentro.zip", dentro)], compressao=zipfile.ZIP_STORED)
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(fora)
    assert e.value.codigo == imp.ARCHIVE_ANINHADO


def test_gzip_aninhado_tambem_derruba_o_archive():
    """A regra é ARCHIVE, não `.zip`: gzip/xz/7z/rar contam igual."""
    fora = _zip([("x.gz", b"\x1f\x8b\x08\x00" + b"\x00" * 32)])
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(fora)
    assert e.value.codigo == imp.ARCHIVE_ANINHADO


def test_entrada_criptografada_derruba_o_archive():
    """Conteúdo que não pode ser inspecionado não entra — nem parcialmente."""
    arquivo = _marcar_como_criptografado(_zip([("segredo.png", _png())]))
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(arquivo)
    assert e.value.codigo == imp.ARCHIVE_CRIPTOGRAFADO


def test_duplicata_de_caminho_normalizado_derruba_o_archive():
    """`a/Foto.JPG` e `a/foto.jpg` são o mesmo destino num FS indiferente a caixa."""
    arquivo = _zip([("a/Foto.JPG", _jpeg()), ("a/foto.jpg", _jpeg(32, 32))])
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(arquivo)
    assert e.value.codigo == imp.ARCHIVE_CAMINHO_DUPLICADO


def test_entradas_demais_derruba_o_archive():
    arquivo = _zip([(f"f{i}.png", _png()) for i in range(6)])
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(arquivo, limites=imp.Limites(entradas_max=5))
    assert e.value.codigo == imp.ARCHIVE_ENTRADAS_DEMAIS


def test_zip_comprimido_grande_demais_e_recusado_antes_de_abrir():
    arquivo = _zip([("a.png", _png())])
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(arquivo, limites=imp.Limites(comprimido_bytes_max=16))
    assert e.value.codigo == imp.ARCHIVE_COMPRIMIDO_GRANDE_DEMAIS


def test_zip_ilegivel_e_recusado_sem_estourar():
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(b"PK\x03\x04nao-sou-um-zip")
    assert e.value.codigo == imp.ARCHIVE_ILEGIVEL


def test_zip_sem_arquivo_dentro_e_recusado():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("pasta/", b"")
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(buf.getvalue())
    assert e.value.codigo == imp.ARCHIVE_VAZIO


def test_o_orcamento_agregado_corta_no_meio_e_nao_no_fim():
    """A unidade do orçamento, isolada: ele acusa no bloco que passa.

    ⚠️ Ele existe mesmo com `zipfile` já cortando a saída no `file_size`
    declarado (medido em `test_a_stdlib_corta_no_tamanho_declarado`). Depender
    do corte da stdlib amarraria a defesa a um detalhe de implementação que
    ninguém desta casa controla.
    """
    orcamento = imp.Orcamento(expandido_max=1000, comprimido=10, razao_max=100)
    orcamento.cobrar(600)
    assert orcamento.gasto == 600
    with pytest.raises(imp.ArchiveMalicioso) as e:
        orcamento.cobrar(600)
    assert e.value.codigo == imp.ARCHIVE_EXPANSAO_GRANDE_DEMAIS


def test_o_orcamento_acusa_a_razao_antes_do_teto_absoluto():
    orcamento = imp.Orcamento(expandido_max=10**9, comprimido=10, razao_max=100)
    with pytest.raises(imp.ArchiveMalicioso) as e:
        orcamento.cobrar(1001)
    assert e.value.codigo == imp.ARCHIVE_RAZAO_DE_EXPANSAO


def test_ler_com_teto_aborta_antes_de_alocar_o_corpo_inteiro():
    """`stream e limite agregado antes de alocar` — a unidade que faz isso."""

    class FluxoInfinito:
        def __init__(self) -> None:
            self.lidos = 0

        def read(self, n: int) -> bytes:
            self.lidos += n
            return b"\x00" * n

    fluxo = FluxoInfinito()
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.ler_com_teto(fluxo, 100_000, codigo=imp.ARCHIVE_COMPRIMIDO_GRANDE_DEMAIS,
                         mensagem="grande demais")
    assert e.value.codigo == imp.ARCHIVE_COMPRIMIDO_GRANDE_DEMAIS
    # Cortou perto do teto — não leu "até acabar" (o fluxo nunca acaba).
    assert fluxo.lidos <= 100_000 + 64 * 1024


def _zip_que_mente_o_tamanho() -> bytes:
    """Um ZIP cujo tamanho descomprimido declarado é MENOR que o real.

    O tamanho aparece em dois lugares (cabeçalho local +22, diretório central
    +24) e os dois são patchados: o `zipfile` lê do diretório central, mas um
    leitor que só olhasse o local também precisa ver a mentira.
    """
    arquivo = bytearray(_zip([("a.bin", b"\x00" * 4096)]))
    local = arquivo.find(b"PK\x03\x04")
    central = arquivo.find(b"PK\x01\x02")
    arquivo[local + 22:local + 26] = struct.pack("<I", 8)
    arquivo[central + 24:central + 28] = struct.pack("<I", 8)
    return bytes(arquivo)


def test_a_stdlib_corta_no_tamanho_declarado_e_acusa_o_crc():
    """O que o `zipfile` faz SOZINHO, medido — e por isso não confiado.

    Ele corta a saída no tamanho DECLARADO e, ao ver que o CRC não fecha,
    levanta `BadZipFile`. É proteção real, não é contrato público, e uma suíte
    que não a mede não perceberia se ela mudasse — que é a razão de `Orcamento`
    continuar no laço de expansão.
    """
    with zipfile.ZipFile(io.BytesIO(_zip_que_mente_o_tamanho())) as zf:
        with pytest.raises(zipfile.BadZipFile):
            zf.open("a.bin").read()


def test_zip_que_mente_o_tamanho_vira_recusa_e_nao_500():
    """⚠️ Sem tratamento, o `BadZipFile` acima subiria e a rota devolveria 500.

    O servidor se acusaria de um defeito do arquivo que alguém mandou. A recusa
    do ARCHIVE é o desfecho certo, e ela tem nome.
    """
    with pytest.raises(imp.ArchiveMalicioso) as e:
        imp.importar_zip(_zip_que_mente_o_tamanho())
    assert e.value.codigo == imp.ARCHIVE_ILEGIVEL


# ═══════════════════════════════════════════════════════════════════════════
# 3. MÍDIA NÃO SUPORTADA É RESULTADO POR ENTRADA
# ═══════════════════════════════════════════════════════════════════════════


def test_extensao_jpg_com_bytes_de_pdf_e_recusada_pela_assinatura():
    """O MIME sai dos BYTES. A extensão não entra na decisão."""
    entrada = imp.inspecionar_bytes(0, "contrato.jpg", _pdf())
    assert entrada.estado == imp.REJECTED
    assert entrada.motivo_recusa == imp.MIME_NAO_SUPORTADO
    assert entrada.mime_detectado is None
    assert entrada.content_hash is None


def test_gif_e_reconhecido_e_ainda_assim_recusado():
    """Reconhecer para recusar COM NOME é melhor que não reconhecer.

    `detectar_mime` devolve `image/gif`; `MIMES_ACEITOS` não o contém
    (`armazenamento.py:62-64`). O operador recebe "GIF não é aceito", e não
    "arquivo desconhecido".
    """
    assert imp.detectar_mime(_gif()) == "image/gif"
    entrada = imp.inspecionar_bytes(0, "banner.gif", _gif())
    assert entrada.estado == imp.REJECTED
    assert entrada.motivo_recusa == imp.MIME_NAO_SUPORTADO
    assert "image/gif" in (entrada.detalhe or "")


def test_arquivo_vazio_e_ausencia_e_nao_um_arquivo_de_zero_byte():
    entrada = imp.inspecionar_bytes(0, "vazio.png", b"")
    assert entrada.estado == imp.REJECTED
    assert entrada.motivo_recusa == imp.ENTRADA_VAZIA
    assert entrada.bytes is None  # ausência é NULL, nunca 0


def test_lote_parcial_entrega_as_boas_e_nomeia_a_recusada():
    """Um ZIP de 3 com 1 PDF disfarçado entrega 2 e registra 1 recusa nomeada."""
    arquivo = _zip([
        ("boa1.png", _png()),
        ("mentira.jpg", _pdf()),
        ("boa2.jpg", _jpeg()),
    ])
    lote = imp.importar_zip(arquivo, nome_arquivo="lote.zip")
    assert lote.estado == imp.PARTIAL_BATCH
    assert len(lote.entradas) == 3
    assert len(lote.aceitas) == 2
    recusadas = [e for e in lote.entradas if not e.aceita]
    assert len(recusadas) == 1
    assert recusadas[0].motivo_recusa == imp.MIME_NAO_SUPORTADO
    assert recusadas[0].nome_normalizado == "mentira.jpg"


def test_lote_com_todas_recusadas_nao_e_parcial_e_sim_recusado():
    lote = imp.importar_zip(_zip([("a.jpg", _pdf()), ("b.gif", _gif())]))
    assert lote.estado == imp.REJECTED
    assert [e.motivo_recusa for e in lote.entradas] == [
        imp.MIME_NAO_SUPORTADO, imp.MIME_NAO_SUPORTADO]


def test_imagem_acima_do_teto_de_bytes_cai_sozinha():
    grande, pequena = _png_ruidoso(64), _jpeg()
    assert len(grande) > 2000 > len(pequena), "as pecas de prova precisam ser desiguais"
    lote = imp.importar_zip(
        _zip([("grande.png", grande), ("ok.jpg", pequena)]),
        limites=imp.Limites(imagem_bytes_max=2000),
    )
    motivos = {e.nome_normalizado: e.motivo_recusa for e in lote.entradas}
    assert motivos["grande.png"] == imp.IMAGEM_GRANDE_DEMAIS
    assert motivos["ok.jpg"] is None
    assert lote.estado == imp.PARTIAL_BATCH


# ═══════════════════════════════════════════════════════════════════════════
# 4. DECODIFICAÇÃO: TETO DE PIXEL E PRAZO
# ═══════════════════════════════════════════════════════════════════════════


def test_decodificacao_que_passa_do_prazo_recusa_a_entrada():
    """Um decodificador que trava não pode travar o request.

    O dublê dorme 2s com prazo de 0,05s. O que se mede é que a entrada volta
    `DECODIFICACAO_EXPIROU` — e volta RÁPIDO.
    """

    def dorminhoco(dados: bytes, mime: str, *, pixels_max: int):
        time.sleep(2.0)
        return imp.MedidaDeImagem(1, 1)

    comeco = time.monotonic()
    entrada = imp.inspecionar_bytes(
        0, "lenta.png", _png(), limites=imp.Limites(prazo_s=0.05),
        decodificador=dorminhoco,
    )
    gasto = time.monotonic() - comeco
    assert entrada.estado == imp.REJECTED
    assert entrada.motivo_recusa == imp.DECODIFICACAO_EXPIROU
    assert gasto < 1.5, "o prazo não cortou: a rota ficaria presa na thread"


def test_o_teto_de_pixel_recusa_pelo_CABECALHO_sem_alocar_raster():
    """Pillow de verdade, teto de 1 pixel: a recusa vem de `Image.open`.

    ⚠️ A prova é que `load()` NUNCA roda. Um teto conferido depois do `load()`
    já pagou a alocação que ele existe para evitar — a bomba de descompressão
    explodiria antes de o número ser lido.
    """
    entrada = imp.inspecionar_bytes(
        0, "grande.png", _png(64, 64), limites=imp.Limites(imagem_pixels_max=1),
    )
    assert entrada.estado == imp.REJECTED
    assert entrada.motivo_recusa == imp.PIXELS_DEMAIS


def test_pixels_demais_e_um_motivo_diferente_de_arquivo_corrompido():
    """Dois defeitos, dois motivos: o operador age diferente em cada um."""
    def quebrado(dados: bytes, mime: str, *, pixels_max: int):
        raise ValueError("cabeçalho ilegível")

    entrada = imp.inspecionar_bytes(0, "x.png", _png(), decodificador=quebrado)
    assert entrada.motivo_recusa == imp.DECODIFICACAO_FALHOU


def test_png_com_assinatura_valida_e_miolo_zerado_nao_vira_medida_zero():
    """O PNG sintético da casa (`medir_imagem` docstring) não pode virar 0x0."""
    entrada = imp.inspecionar_bytes(
        0, "falso.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    assert entrada.estado == imp.REJECTED
    assert entrada.largura is None and entrada.altura is None


# ═══════════════════════════════════════════════════════════════════════════
# 5. SANEAMENTO E O HASH DOS BYTES FINAIS
# ═══════════════════════════════════════════════════════════════════════════


def test_o_hash_cobre_os_bytes_FINAIS_e_o_insumo_guarda_os_recebidos():
    """A regra `hash sobre bytes finais exatos enviados`, medida nos dois lados."""
    import hashlib

    recebidos = _jpeg(descricao="LAT -25.42 LON -49.27 // camera do cliente")
    entrada = imp.inspecionar_bytes(0, "foto.jpg", recebidos)
    assert entrada.estado == imp.INSPECTED
    finais = entrada.conteudo
    assert finais is not None and finais != recebidos

    assert entrada.content_hash == "sha256:" + hashlib.sha256(finais).hexdigest()
    assert entrada.insumo_hash == "sha256:" + hashlib.sha256(recebidos).hexdigest()
    assert entrada.content_hash != entrada.insumo_hash
    assert entrada.bytes == len(finais)


def test_exif_com_localizacao_nao_sobrevive_ao_saneamento():
    marca = b"LAT -25.42 LON -49.27"
    recebidos = _jpeg(descricao=marca.decode())
    assert marca in recebidos, "o JPEG de prova precisa MESMO carregar o EXIF"
    entrada = imp.inspecionar_bytes(0, "foto.jpg", recebidos)
    assert marca not in (entrada.conteudo or b"")


def test_o_jpeg_saneado_continua_abrindo_com_os_mesmos_pixels():
    """Saneamento tira metadado. Ele não pode tirar imagem."""
    from PIL import Image

    recebidos = _jpeg(48, 32, descricao="camera")
    entrada = imp.inspecionar_bytes(0, "foto.jpg", recebidos)
    antes = Image.open(io.BytesIO(recebidos))
    depois = Image.open(io.BytesIO(entrada.conteudo or b""))
    assert antes.size == depois.size == (48, 32)
    assert list(antes.convert("RGB").getdata()) == list(depois.convert("RGB").getdata())


def test_texto_livre_de_png_nao_sobrevive_e_os_pixels_sim():
    from PIL import Image

    recebidos = _png(12, 10, texto="cliente: Banco Exemplo — interno")
    assert b"Banco Exemplo" in recebidos
    entrada = imp.inspecionar_bytes(0, "peca.png", recebidos)
    finais = entrada.conteudo or b""
    assert b"Banco Exemplo" not in finais
    assert list(Image.open(io.BytesIO(recebidos)).convert("RGB").getdata()) == \
        list(Image.open(io.BytesIO(finais)).convert("RGB").getdata())


def test_webp_saneado_continua_sendo_um_webp_valido():
    from PIL import Image

    recebidos = _webp(24, 18)
    entrada = imp.inspecionar_bytes(0, "peca.webp", recebidos)
    assert entrada.estado == imp.INSPECTED
    assert Image.open(io.BytesIO(entrada.conteudo or b"")).size == (24, 18)


def test_o_saneamento_e_deterministico():
    """Dois saneamentos dos mesmos bytes dão o MESMO hash.

    É disto que a dedup depende: recodificar com Pillow faria o hash variar com
    a versão instalada, e "hash idêntico reusa master" deixaria de casar entre
    duas máquinas.
    """
    dados = _jpeg(descricao="x")
    assert imp.sanear(dados, "image/jpeg") == imp.sanear(dados, "image/jpeg")
    duas = imp.sanear(imp.sanear(dados, "image/jpeg"), "image/jpeg")
    assert duas == imp.sanear(dados, "image/jpeg"), "sanear tem de ser idempotente"


def test_o_nome_interno_e_opaco_e_nao_carrega_o_nome_do_usuario():
    entrada = imp.inspecionar_bytes(
        0, "Proposta Banco Exemplo — confidencial.png", _png())
    interno = entrada.nome_interno or ""
    assert "banco" not in interno.lower()
    assert "confidencial" not in interno.lower()
    assert re.fullmatch(r"0000-[0-9a-f]{32}\.png", interno)
    # O nome original sobrevive como METADADO, saneado — nunca como endereço.
    assert entrada.nome_normalizado == "Proposta_Banco_Exemplo_confidencial.png"


# ═══════════════════════════════════════════════════════════════════════════
# 6. VÍDEO
# ═══════════════════════════════════════════════════════════════════════════


def test_mp4_e_medido_pelos_boxes_sem_ffprobe():
    entrada = imp.inspecionar_bytes(0, "reels.mp4", _mp4())
    assert entrada.estado == imp.INSPECTED
    assert entrada.mime_detectado == "video/mp4"
    assert (entrada.largura, entrada.altura) == (1080, 1920)
    assert entrada.duracao_ms == 15_000


def test_mp4_com_localizacao_e_recusado_em_vez_de_remendado():
    """Sem muxer, remover `udta` invalidaria os offsets de `stco`. Recusa-se."""
    entrada = imp.inspecionar_bytes(0, "ferias.mp4", _mp4(localizacao=True))
    assert entrada.estado == imp.REJECTED
    assert entrada.motivo_recusa == imp.VIDEO_COM_LOCALIZACAO


def test_video_longo_demais_e_recusado():
    entrada = imp.inspecionar_bytes(
        0, "filme.mp4", _mp4(duracao_ms=60_000),
        limites=imp.Limites(video_duracao_ms_max=30_000))
    assert entrada.motivo_recusa == imp.VIDEO_LONGO_DEMAIS


def test_video_com_amostras_demais_e_recusado():
    entrada = imp.inspecionar_bytes(
        0, "x.mp4", _mp4(amostras=90_000),
        limites=imp.Limites(video_frames_max=1_000))
    assert entrada.motivo_recusa == imp.VIDEO_FRAMES_DEMAIS


def test_video_com_pixels_demais_e_recusado():
    entrada = imp.inspecionar_bytes(
        0, "x.mp4", _mp4(largura=7680, altura=4320))
    assert entrada.motivo_recusa == imp.PIXELS_DEMAIS


def test_quicktime_nao_passa_por_mp4():
    """`ftyp qt  ` compartilha o container e não está em `MIMES_ACEITOS`."""
    bruto = bytearray(_mp4())
    bruto[8:12] = b"qt  "
    entrada = imp.inspecionar_bytes(0, "x.mp4", bytes(bruto))
    assert entrada.motivo_recusa == imp.MIME_NAO_SUPORTADO


def test_mp4_sem_duracao_declara_ausencia_e_nao_zero():
    medida = imp.medir_mp4(_mp4(duracao_ms=0))
    assert medida.duracao_ms is None


# ═══════════════════════════════════════════════════════════════════════════
# 7. UPLOAD INDIVIDUAL — OS MESMOS LIMITES
# ═══════════════════════════════════════════════════════════════════════════


def test_o_limite_agregado_vale_no_upload_individual():
    """Sem isto, 50 partes multipart contornariam o teto do ZIP."""
    lote = imp.importar_individual(
        [imp.ArquivoRecebido(f"f{i}.png", _png(32, 32)) for i in range(4)],
        limites=imp.Limites(expandido_bytes_max=100),
    )
    assert lote.estado == imp.REJECTED
    assert lote.motivo_recusa == imp.ARCHIVE_EXPANSAO_GRANDE_DEMAIS


def test_entradas_demais_no_upload_individual():
    lote = imp.importar_individual(
        [imp.ArquivoRecebido(f"f{i}.png", _png()) for i in range(4)],
        limites=imp.Limites(entradas_max=3),
    )
    assert lote.motivo_recusa == imp.ARCHIVE_ENTRADAS_DEMAIS


def test_duplicata_normalizada_no_upload_individual():
    lote = imp.importar_individual([
        imp.ArquivoRecebido("Foto.JPG", _jpeg()),
        imp.ArquivoRecebido("foto.jpg", _jpeg(32, 32)),
    ])
    assert lote.motivo_recusa == imp.ARCHIVE_CAMINHO_DUPLICADO


def test_upload_individual_sem_arquivo_e_recusado():
    assert imp.importar_individual([]).motivo_recusa == imp.ARCHIVE_VAZIO


def test_upload_individual_aceita_e_mede():
    lote = imp.importar_individual([imp.ArquivoRecebido("a.png", _png(20, 10))])
    assert lote.estado == imp.INSPECTED
    assert lote.origem == imp.ORIGEM_INDIVIDUAL
    assert (lote.entradas[0].largura, lote.entradas[0].altura) == (20, 10)


# ═══════════════════════════════════════════════════════════════════════════
# 8. AS ROTAS — HERMÉTICAS, E SEM A META
# ═══════════════════════════════════════════════════════════════════════════

DONO = "11111111-1111-4111-8111-111111111111"
OUTRO = "22222222-2222-4222-8222-222222222222"

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


class BancoDublê:
    """Um banco em memória que TRANSCREVE as CHECKs das migrations.

    ⚠️ Ele recusa o que o Postgres recusaria. Sem isso, um teste hermético
    passaria com uma linha que o banco real rejeita — e a suíte verde diria que
    a lane funciona enquanto o primeiro POST em produção devolvia 23514.

    As CHECKs transcritas: `criativo_job_procedencia_valida` e as duas de
    custódia do `importado` (v11_04 §1-2), `criativo_master_procedencia_completa`
    e `criativo_master_hash_forma` (v11_01:416-417, 432-433),
    `criativo_master_slot_ux` (v11_01:410), `criativo_briefing_formatos_nao_vazio`
    (v11_04 §3) e o vocabulário fechado de
    `criativo_importacao_entrada.estado` (v11_04 §5).
    """

    def __init__(self) -> None:
        self.projetos: list[dict] = []
        self.briefings: list[dict] = []
        self.jobs: dict[str, dict] = {}
        self.por_chave: dict[str, str] = {}
        self.masters: dict[str, dict] = {}
        self.lotes: dict[str, dict] = {}
        self.entradas: list[dict] = []
        self._seq = 0

    def _id(self) -> str:
        self._seq += 1
        return f"{self._seq:08x}-0000-4000-8000-000000000000"

    async def criar_projeto(self, titulo, objetivo, brand_pack_id, dono_id,
                            origem="standalone"):
        assert origem in ("standalone", "trafego", "conteudo", "importado")
        assert (titulo or "").strip(), "criativo_projeto_titulo_nao_vazio"
        linha = {"id": self._id(), "titulo": titulo, "origem": origem,
                 "dono_id": dono_id}
        self.projetos.append(linha)
        return linha

    async def criar_briefing(self, linha):
        assert linha["modo"] in (
            "typography_only", "deterministic_graphics", "full_llm",
            "photo_preserved", "prensa_hybrid", "full_llm_then_prensa",
            "observado", "importado"), "criativo_briefing_modo_valido"
        assert (linha["modo"] in ("observado", "importado")
                or len(linha["formatos_pedidos"]) >= 1), \
            "criativo_briefing_formatos_nao_vazio"
        linha = {**linha, "id": self._id()}
        self.briefings.append(linha)
        return linha

    async def criar_job_idempotente(self, linha):
        p = linha["procedencia_execucao"]
        assert p in ("volc_os", "observado", "importado"), \
            "criativo_job_procedencia_valida"
        if p == "importado":
            assert linha.get("custo_real_usd") is None, \
                "criativo_job_importado_sem_custo_proprio"
            assert linha.get("origem_externa") is not None, \
                "criativo_job_importado_com_origem"
        assert len(linha["idempotency_key"]) >= 16, "criativo_job_idem_forma"
        assert linha["motor"] and linha["motor_versao"]
        if linha["estado"] in ("succeeded", "partial", "failed", "cancelled"):
            assert linha.get("terminado_em"), "criativo_job_terminal_carimbado"
        existente = self.por_chave.get(linha["idempotency_key"])
        if existente:
            return self.jobs[existente], False
        gravado = {**linha, "id": self._id()}
        self.jobs[gravado["id"]] = gravado
        self.por_chave[linha["idempotency_key"]] = gravado["id"]
        return gravado, True

    async def criar_master(self, linha):
        from app.criativo.persistencia import ConflitoDeChave

        assert _HASH.match(linha["content_hash"]), "criativo_master_hash_forma"
        assert linha["motor"].strip() and linha["insumo_hash"].strip(), \
            "criativo_master_procedencia_completa"
        assert linha["motor_versao"], "motor_versao NOT NULL"
        assert linha["storage_chave"].strip(), "criativo_master_storage_nao_vazia"
        for medida in ("largura", "altura", "bytes_totais", "duracao_ms"):
            valor = linha.get(medida)
            assert valor is None or valor > 0, f"criativo_master_{medida}: 0 não é ausência"
        chave = (linha["job_id"], linha["slot"], linha.get("versao", 1))
        if any((m["job_id"], m["slot"], m.get("versao", 1)) == chave
               for m in self.masters.values()):
            raise ConflitoDeChave()
        gravado = {**linha, "id": self._id(), "criado_em": "2026-09-07T00:00:00Z"}
        self.masters[gravado["id"]] = gravado
        return gravado

    async def master_do_dono_por_hash(self, content_hash, *, criado_por):
        for m in self.masters.values():
            job = self.jobs.get(str(m["job_id"]))
            # ⚠️ O `!inner` do PostgREST, reproduzido: sem job do dono, a linha
            # simplesmente NÃO existe para este chamador.
            if not job or job.get("criado_por") != criado_por:
                continue
            if m["content_hash"] == content_hash:
                return m
        return None

    async def masters_do_job(self, job_id):
        return [m for m in self.masters.values() if str(m["job_id"]) == str(job_id)]

    async def buscar_job(self, job_id, *, criado_por=None):
        job = self.jobs.get(str(job_id))
        if job is None:
            return None
        if criado_por is not None and job.get("criado_por") != criado_por:
            return None
        return job

    async def criar_lote(self, linha):
        assert linha["origem"] in ("UPLOAD_INDIVIDUAL", "UPLOAD_ZIP")
        assert (linha["criado_por"] or "").strip()
        assert linha.get("bytes_comprimidos") is None or linha["bytes_comprimidos"] > 0
        assert linha["estado"] in imp.ESTADOS, \
            "criativo_importacao_lote_estado_valido"
        assert linha["estado"] != imp.REJECTED or linha.get("motivo_recusa"), \
            "criativo_importacao_lote_recusado_com_motivo"
        gravado = {**linha, "id": self._id(), "criado_em": "2026-09-07T00:00:00Z"}
        self.lotes[gravado["id"]] = gravado
        return gravado

    async def criar_entradas(self, linhas):
        vistos = set()
        for l in linhas:
            assert l["estado"] in imp.ESTADOS, "estado fora do vocabulário fechado"
            assert l.get("content_hash") is None or _HASH.match(l["content_hash"])
            assert l.get("bytes") is None or l["bytes"] > 0
            if l["estado"] == imp.REJECTED:
                assert l.get("master_id") is None, \
                    "criativo_importacao_entrada_recusada_sem_master"
                assert l.get("motivo_recusa"), \
                    "criativo_importacao_entrada_recusada_com_motivo"
            chave = (l["lote_id"], l["indice"])
            assert chave not in vistos, "criativo_importacao_entrada_indice_ux"
            vistos.add(chave)
            self.entradas.append(dict(l))
        return list(linhas)

    async def lote_do_dono(self, lote_id, *, criado_por):
        lote = self.lotes.get(str(lote_id))
        if lote is None or lote.get("criado_por") != criado_por:
            return None
        return lote

    async def entradas_do_lote(self, lote_id):
        return sorted((e for e in self.entradas if str(e["lote_id"]) == str(lote_id)),
                      key=lambda e: e["indice"])


class ClienteHTTPQueFalhaSeUsado:
    """Um `httpx.AsyncClient` que não existe para ser usado.

    Construí-lo já é a falha: qualquer caminho que tente falar com a Meta, com o
    Supabase ou com qualquer host passa por aqui e explode com um nome que diz o
    que aconteceu.
    """

    def __init__(self, *a: Any, **kw: Any) -> None:
        raise AssertionError(
            "esta lane não pode abrir cliente HTTP: importar arquivo não chama a Meta")


@pytest.fixture
def banco() -> BancoDublê:
    return BancoDublê()


@pytest.fixture
def cliente(monkeypatch, tmp_path, banco):
    from fastapi.testclient import TestClient

    from app.criativo.armazenamento import ArmazenamentoLocal
    from app.main import app
    from app.routers import criativos_importacao as rota
    from app.seguranca.identidade import Identidade, exigir_admin

    monkeypatch.setenv("CRIATIVO_URL_SECRET", "x" * 48)
    monkeypatch.setenv("CRIATIVO_STORAGE_DIR", str(tmp_path / "acervo"))
    loja = ArmazenamentoLocal(tmp_path / "acervo")

    def identidade_de(sub: str):
        return lambda: Identidade(sub=sub, email="op@volc", papel="ADMIN",
                                  origem="sessao")

    app.dependency_overrides[rota.obter_porta] = lambda: banco
    app.dependency_overrides[rota.obter_armazenamento] = lambda: loja
    app.dependency_overrides[exigir_admin] = identidade_de(DONO)
    c = TestClient(app)
    c.loja = loja  # type: ignore[attr-defined]
    c.como = lambda sub: app.dependency_overrides.__setitem__(  # type: ignore[attr-defined]
        exigir_admin, identidade_de(sub))
    try:
        yield c
    finally:
        for chave in (rota.obter_porta, rota.obter_armazenamento):
            app.dependency_overrides.pop(chave, None)
        app.dependency_overrides.pop(exigir_admin, None)


def _multipart(arquivos, campos=None):
    fronteira = "----volcprovaT07"
    partes = []
    for nome, conteudo, tipo in arquivos:
        partes.append(
            f"--{fronteira}\r\n".encode()
            + f'Content-Disposition: form-data; name="arquivo"; filename="{nome}"\r\n'.encode()
            + f"Content-Type: {tipo}\r\n\r\n".encode()
            + conteudo + b"\r\n"
        )
    for chave, valor in (campos or {}).items():
        partes.append(
            f"--{fronteira}\r\n".encode()
            + f'Content-Disposition: form-data; name="{chave}"\r\n\r\n'.encode()
            + valor.encode() + b"\r\n"
        )
    partes.append(f"--{fronteira}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={fronteira}"


def _enviar(cliente, arquivos, campos=None):
    corpo, tipo = _multipart(arquivos, campos)
    return cliente.post("/api/criativos/importacoes", content=corpo,
                        headers={"Content-Type": tipo})


# ── a prova central: nada sai daqui ─────────────────────────────────────────


def test_importar_arquivo_NAO_chama_a_meta_nem_abre_socket(cliente, monkeypatch, banco):
    """A28/A27, medida: o POST completo roda com a rede detonada.

    Dois dublês armados ao mesmo tempo:
      * `httpx.AsyncClient` levanta ao ser CONSTRUÍDO — cobre `Repositorio._req`,
        `ArmazenamentoSupabase` e qualquer adaptador da Meta;
      * `socket.socket.connect` levanta — cobre qualquer biblioteca que
        contornasse o `httpx`.

    O `TestClient` não passa por nenhum dos dois: ele fala com a aplicação por
    `ASGITransport`, sem socket e por um `httpx.Client` já construído.
    """
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", ClienteHTTPQueFalhaSeUsado)

    def sem_rede(self, *a, **kw):
        raise AssertionError("esta lane não pode abrir conexão de rede")

    monkeypatch.setattr(socket.socket, "connect", sem_rede)

    r = _enviar(cliente, [("peca.png", _png(40, 20), "image/png")])
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["registroRemoto"]["estado"] == "NAO_INICIADO"
    assert len(banco.masters) == 1


def test_a_lane_nao_importa_nenhum_modulo_da_meta():
    """A prova ESTÁTICA que acompanha a dinâmica.

    O dublê de rede prova que nada saiu NESTE caminho. Esta prova é mais larga:
    o módulo não tem sequer a referência, então nenhum ramo futuro pode chamar
    a Meta sem que o import apareça na revisão.
    """
    import ast
    import pathlib as _pl

    # ⚠️ Caminho derivado de `__file__`, não do diretório corrente: um teste que
    # só passa quando rodado da raiz do repositório é um teste que some.
    raiz = _pl.Path(__file__).resolve().parents[2]
    fonte = (raiz / "backend/app/routers/criativos_importacao.py").read_text()
    alvos = []
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.ImportFrom) and no.module:
            alvos.append(no.module)
        elif isinstance(no, ast.Import):
            alvos += [a.name for a in no.names]
    suspeitos = [a for a in alvos if "meta" in a.lower() or "trafego" in a.lower()]
    assert suspeitos == [], f"a lane de importação não pode importar {suspeitos}"


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("multipart") is not None,
    reason="`python-multipart` presente: a razão de o leitor ser próprio deixou de valer",
)
def test_a_rota_le_multipart_sem_a_dependencia_que_o_backend_nao_declara():
    """⚠️ `File(...)` levanta AO MONTAR A ROTA quando falta `python-multipart`.

    O modo de falha não seria "upload não funciona": `app.main` deixaria de
    importar e TODO o backend responderia erro. Esta prova mede que a
    dependência de fato não está lá, e que montar uma rota com `File(...)`
    quebraria agora — que é por que o leitor de multipart é próprio.
    """
    from fastapi import FastAPI, File, UploadFile

    app_de_prova = FastAPI()
    with pytest.raises(RuntimeError, match="python-multipart"):
        @app_de_prova.post("/x")
        async def _(a: UploadFile = File(...)):  # pragma: no cover
            return {}


def test_o_dto_declara_que_o_registro_remoto_nao_comecou(cliente):
    corpo = _enviar(cliente, [("a.png", _png(), "image/png")]).json()
    assert corpo["registroRemoto"]["estado"] == "NAO_INICIADO"
    assert "não envia nada para a Meta" in corpo["registroRemoto"]["explicacao"]


# ── o ciclo canônico e as CHECKs ────────────────────────────────────────────


def test_o_job_nasce_importado_com_origem_externa_e_sem_custo(cliente, banco):
    r = _enviar(cliente, [("peca.png", _png(40, 20), "image/png")])
    assert r.status_code == 201, r.text
    job = next(iter(banco.jobs.values()))
    assert job["procedencia_execucao"] == "importado"
    assert job["origem_externa"]["tipo"] == "UPLOAD_INDIVIDUAL"
    assert "custo_real_usd" not in job, "custo ausente é AUSÊNCIA, nem sequer a coluna"
    assert job["criado_por"] == DONO
    assert banco.briefings[0]["modo"] == "importado"
    assert banco.briefings[0]["formatos_pedidos"] == []
    assert banco.projetos[0]["origem"] == "importado"


def test_o_master_carrega_procedencia_completa_e_o_hash_dos_bytes_finais(cliente, banco):
    import hashlib

    recebidos = _jpeg(descricao="camera do cliente")
    r = _enviar(cliente, [("foto.jpg", recebidos, "image/jpeg")])
    assert r.status_code == 201, r.text
    master = next(iter(banco.masters.values()))
    assert master["motor"] == imp.MOTOR and master["motor_versao"] == imp.MOTOR_VERSAO
    assert master["insumo_hash"] == "sha256:" + hashlib.sha256(recebidos).hexdigest()
    assert master["content_hash"] != master["insumo_hash"]
    # E os bytes guardados são EXATAMENTE os que o hash descreve.
    guardados = cliente.loja.ler(master["storage_chave"])
    assert master["content_hash"] == "sha256:" + hashlib.sha256(guardados).hexdigest()
    assert b"camera do cliente" not in guardados


def test_o_master_nao_afirma_conteudo_sintetico_sem_evidencia(cliente, banco):
    _enviar(cliente, [("a.png", _png(), "image/png")])
    assert next(iter(banco.masters.values()))["sintetico"] is False


def test_o_preview_e_url_assinada_e_nunca_o_caminho(cliente):
    corpo = _enviar(cliente, [("a.png", _png(), "image/png")]).json()
    url = corpo["entradas"][0]["previewUrl"]
    assert url.startswith("/api/criativos/arquivo/")
    assert "criativos/" not in url.split("/api/criativos/arquivo/")[1]


# ── a política é chamada, e o bloqueio é EXIBIDO ────────────────────────────


class DetectorDePixelDeProva:
    """Cobre as duas capacidades exigidas, para o portão não sair indisponível."""

    nome = "detector-de-prova"
    versao = "1"

    def __init__(self) -> None:
        from app.criativo.politica import inspecao

        self.capacidades = tuple(inspecao.CAPACIDADES_EXIGIDAS)

    def inspecionar(self, bytes_da_peca: bytes, *, mime: str):
        from app.criativo.politica.inspecao import LeituraDePixel

        return LeituraDePixel(texto="", rotulos=())


def test_human_upload_sem_licenca_sai_BLOCKED_BY_POLICY_com_RIGHTS_UNKNOWN(cliente):
    """O comportamento correto do portão, EXIBIDO em vez de contornado.

    Com o detector de pixel registrado, a regra 1 de `gate.avaliar`
    (portão indisponível) não dispara e a decisão sai da regra de DIREITOS —
    que é o que esta lane precisa mostrar: ninguém provou que temos direito
    sobre estes bytes.
    """
    from app.criativo.politica import inspecao

    inspecao.limpar_detectores_de_pixel()
    inspecao.registrar_detector_de_pixel(DetectorDePixelDeProva())
    try:
        corpo = _enviar(cliente, [("a.png", _png(), "image/png")]).json()
    finally:
        inspecao.limpar_detectores_de_pixel()

    entrada = corpo["entradas"][0]
    assert entrada["politica"]["decisao"] == "BLOCKED_BY_POLICY"
    assert "RIGHTS_UNKNOWN" in entrada["politica"]["motivos"]
    assert entrada["politica"]["liberaMidiaPaga"] is False
    # Guardado, com dono e hash — e NÃO liberado para mídia paga.
    assert entrada["estado"] == "POLICY_PENDING"
    assert entrada["masterId"]
    assert corpo["estado"] == "POLICY_PENDING"


def test_sem_detector_de_pixel_o_portao_sai_indisponivel_e_isso_aparece(cliente):
    """"Não consegui olhar" ≠ "não tem nada" — e o DTO não esconde a diferença."""
    from app.criativo.politica import inspecao

    inspecao.limpar_detectores_de_pixel()
    corpo = _enviar(cliente, [("a.png", _png(), "image/png")]).json()
    entrada = corpo["entradas"][0]
    assert entrada["politica"]["decisao"] == "GATE_UNAVAILABLE"
    assert entrada["politica"]["liberaMidiaPaga"] is False
    assert entrada["estado"] == "POLICY_PENDING"


# ── ZIP pela rota ───────────────────────────────────────────────────────────


def test_zip_e_reconhecido_pelos_bytes_e_nao_pela_extensao(cliente, banco):
    arquivo = _zip([("a.png", _png()), ("b.jpg", _jpeg())])
    r = _enviar(cliente, [("lote.bin", arquivo, "application/octet-stream")])
    assert r.status_code == 201, r.text
    assert r.json()["origem"] == "UPLOAD_ZIP"
    assert len(banco.masters) == 2


def test_zip_com_traversal_e_recusado_e_a_tentativa_fica_registrada(cliente, banco):
    """Recusar em silêncio deixaria a auditoria sem a linha mais importante."""
    arquivo = _zip([("ok.png", _png()), ("../fora.png", _png())])
    # ⚠️ 400 E corpo: um cliente ingênuo não pode ler 200 como "deu certo", e
    # tirar o corpo tiraria do operador a única prova do que aconteceu.
    r = _enviar(cliente, [("lote.zip", arquivo, "application/zip")])
    assert r.status_code == 400, r.text
    corpo = r.json()
    assert corpo["estado"] == "REJECTED"
    assert corpo["referencia"], "a tentativa recusada precisa ser abrível pelo GET"
    assert corpo["motivoRecusa"] == imp.ARCHIVE_TRAVERSAL
    assert corpo["entradas"] == []
    # Nada virou patrimônio, e a tentativa existe.
    assert banco.masters == {} and banco.jobs == {}
    assert len(banco.lotes) == 1
    assert next(iter(banco.lotes.values()))["job_id"] is None


def test_lote_parcial_pela_rota_nomeia_a_entrada_recusada(cliente, banco):
    arquivo = _zip([("boa.png", _png()), ("mentira.jpg", _pdf())])
    corpo = _enviar(cliente, [("lote.zip", arquivo, "application/zip")]).json()
    assert corpo["estado"] == "PARTIAL_BATCH"
    por_nome = {e["nome"]: e for e in corpo["entradas"]}
    assert por_nome["mentira.jpg"]["estado"] == "REJECTED"
    assert por_nome["mentira.jpg"]["motivoRecusa"] == imp.MIME_NAO_SUPORTADO
    assert por_nome["mentira.jpg"]["masterId"] is None
    assert por_nome["boa.png"]["masterId"]
    assert len(banco.masters) == 1


def test_zip_junto_com_arquivo_solto_e_pedido_invalido(cliente):
    r = _enviar(cliente, [
        ("lote.zip", _zip([("a.png", _png())]), "application/zip"),
        ("solto.png", _png(), "image/png"),
    ])
    assert r.status_code == 400
    assert r.json()["detail"]["codigo"] == "ESTUDIO.importacao_pedido_invalido"


def test_envio_sem_arquivo_e_recusado(cliente):
    r = _enviar(cliente, [], campos={"projetoTitulo": "vazio"})
    assert r.status_code == 400
    assert r.json()["detail"]["codigo"] == "ESTUDIO.importacao_sem_arquivo"


def test_corpo_que_nao_e_multipart_e_recusado(cliente):
    r = cliente.post("/api/criativos/importacoes", content=b"{}",
                     headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["detail"]["codigo"] == "ESTUDIO.importacao_pedido_invalido"


# ── dedup por hash, sem atravessar o dono ───────────────────────────────────


def test_hash_identico_do_MESMO_dono_reusa_o_master(cliente, banco):
    png = _png(30, 30)
    primeiro = _enviar(cliente, [("a.png", png, "image/png")]).json()
    segundo = _enviar(cliente, [("copia.png", png, "image/png")]).json()
    assert len(banco.masters) == 1, "os mesmos bytes não podem virar dois masters"
    assert primeiro["entradas"][0]["masterId"] == segundo["entradas"][0]["masterId"]


def test_hash_identico_de_OUTRA_conta_nao_e_reusado(cliente, banco):
    """A metade que a regra exige: a peça alheia não vale por ter o mesmo hash.

    ⚠️ O master de outro dono nem aparece na consulta (`!inner` + filtro de
    `criado_por`), então o segundo operador cria o PRÓPRIO master e passa pelo
    portão de política de novo — o recibo do primeiro não é herdado.
    """
    png = _png(30, 30)
    _enviar(cliente, [("a.png", png, "image/png")])
    cliente.como(OUTRO)
    segundo = _enviar(cliente, [("a.png", png, "image/png")]).json()
    assert len(banco.masters) == 2
    donos = {banco.jobs[str(m["job_id"])]["criado_por"] for m in banco.masters.values()}
    assert donos == {DONO, OUTRO}
    assert segundo["entradas"][0]["politica"] is not None


def test_o_mesmo_envio_do_mesmo_operador_e_o_mesmo_job(cliente, banco):
    png = _png(30, 30)
    primeiro = _enviar(cliente, [("a.png", png, "image/png")])
    segundo = _enviar(cliente, [("a.png", png, "image/png")])
    assert len(banco.jobs) == 1, "reenvio não é execução nova"
    # O par 200/201 é o que torna a idempotência VISÍVEL para o cliente.
    assert primeiro.status_code == 201
    assert segundo.status_code == 200
    assert segundo.headers["X-Criativo-Importacao"] == "replay"


def test_os_estados_de_entrada_gravados_estao_no_vocabulario_fechado(cliente, banco):
    """O que a lane grava tem de caber na CHECK da v11_04, sempre."""
    _enviar(cliente, [("boa.png", _png(), "image/png"),
                      ("mentira.jpg", _pdf(), "image/jpeg")])
    assert {e["estado"] for e in banco.entradas} <= imp.ESTADOS
    assert {l["estado"] for l in banco.lotes.values()} <= imp.ESTADOS
    # ⚠️ E nenhuma delas é RECEIVED/QUARANTINED: as duas são fases de memória
    # dentro da requisição, e gravá-las inventaria progresso que ninguém lê.
    assert not ({e["estado"] for e in banco.entradas}
                & {imp.RECEIVED, imp.QUARANTINED})


# ── GET: posse e 404 idêntico ───────────────────────────────────────────────


def test_get_devolve_status_e_preview_para_o_dono(cliente):
    criado = _enviar(cliente, [("a.png", _png(24, 12), "image/png")]).json()
    r = cliente.get(f"/api/criativos/importacoes/{criado['referencia']}")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["referencia"] == criado["referencia"]
    assert corpo["entradas"][0]["previewUrl"].startswith("/api/criativos/arquivo/")
    assert corpo["entradas"][0]["largura"] == 24
    assert corpo["registroRemoto"]["estado"] == "NAO_INICIADO"


def test_get_de_outra_conta_e_o_MESMO_404_de_inexistente(cliente):
    """Um status diferente seria um oráculo de existência."""
    criado = _enviar(cliente, [("a.png", _png(), "image/png")]).json()
    cliente.como(OUTRO)

    alheio = cliente.get(f"/api/criativos/importacoes/{criado['referencia']}")
    inexistente = cliente.get(
        "/api/criativos/importacoes/99999999-9999-4999-8999-999999999999")
    assert alheio.status_code == inexistente.status_code == 404
    assert alheio.json() == inexistente.json()


def test_get_com_referencia_malformada_e_404_e_nao_503(cliente):
    """`_uuid_ou_404`: id inválido não pode virar "o Estúdio está fora do ar"."""
    r = cliente.get("/api/criativos/importacoes/nao-e-uuid")
    assert r.status_code == 404
    assert r.json()["detail"]["codigo"] == "ESTUDIO.importacao_inexistente"


def test_get_de_lote_recusado_tambem_respeita_o_dono(cliente):
    arquivo = _zip([("../fora.png", _png())])
    criado = _enviar(cliente, [("lote.zip", arquivo, "application/zip")]).json()
    assert cliente.get(
        f"/api/criativos/importacoes/{criado['referencia']}").status_code == 200
    cliente.como(OUTRO)
    assert cliente.get(
        f"/api/criativos/importacoes/{criado['referencia']}").status_code == 404


def test_a_posse_final_e_do_JOB_e_nao_da_coluna_do_lote(cliente, banco):
    """A coluna `criado_por` do lote é cópia; o job é a autoridade.

    Aqui o lote é adulterado para apontar para o job de OUTRO dono — o cenário
    de uma cópia que divergiu. A rota tem de continuar recusando.
    """
    criado = _enviar(cliente, [("a.png", _png(), "image/png")]).json()
    lote = banco.lotes[criado["referencia"]]
    banco.jobs[str(lote["job_id"])]["criado_por"] = OUTRO
    r = cliente.get(f"/api/criativos/importacoes/{criado['referencia']}")
    assert r.status_code == 404


# ── armazenamento ───────────────────────────────────────────────────────────


def test_os_bytes_ficam_no_acervo_privado_e_a_chave_e_derivada_do_hash(cliente, banco):
    _enviar(cliente, [("Proposta Banco X.png", _png(16, 16), "image/png")])
    master = next(iter(banco.masters.values()))
    chave = master["storage_chave"]
    assert "banco" not in chave.lower(), "a chave não pode carregar o nome do usuário"
    assert master["content_hash"].removeprefix("sha256:")[:32] in chave
    assert cliente.loja.existe(chave)


def test_o_armazenamento_que_recusa_derruba_so_a_entrada(cliente, banco):
    """A política do armazenamento é PRÓPRIA, e a recusa dela não é 500.

    `ArmazenamentoLocal.guardar` aplica `conferir_upload` com o teto de imagem
    (armazenamento.py:124-137, 283-296). Quando ele recusa, a entrada cai com
    motivo e o lote continua respondendo.
    """
    from app.criativo.armazenamento import ArquivoRecusado

    class LojaQueRecusa:
        nome = "recusa"

        def guardar(self, chave, dados, mime):
            raise ArquivoRecusado("arquivo acima do limite de 25 MB")

    from app.main import app
    from app.routers import criativos_importacao as rota

    app.dependency_overrides[rota.obter_armazenamento] = lambda: LojaQueRecusa()
    try:
        r = _enviar(cliente, [("a.png", _png(), "image/png")])
    finally:
        app.dependency_overrides[rota.obter_armazenamento] = lambda: cliente.loja

    assert r.status_code == 400, "nada entrou: o pedido não produziu patrimônio"
    corpo = r.json()

    assert corpo["estado"] == "REJECTED"
    assert corpo["entradas"][0]["motivoRecusa"] == "ARMAZENAMENTO_RECUSOU"
    assert banco.masters == {}
