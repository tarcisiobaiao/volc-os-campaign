"""Intake de mídia importada — os bytes antes de virarem patrimônio.

## O que este módulo é, e o que ele deliberadamente NÃO é

Ele responde UMA pergunta: *estes bytes podem entrar no acervo privado, e o que
eles são de fato?* Não guarda arquivo, não fala com banco, não emite recibo de
política e — sobretudo — **não chama a Meta**. A rota de importação é declarada
na SPEC como `"importação privada; não chama Meta"`
(`docs/specs/meta-operator-go-live-v1/SPEC.json` → `proposed_routes`), e a única
forma de essa frase ser verdade é o caminho inteiro não ter para onde ligar.
Por isso aqui não há `httpx`, não há `fastapi` e não há `Repositorio`: um módulo
sem transporte não tem como adquirir um por descuido.

## Por que a inspeção acontece ANTES de qualquer alocação

`SPEC.json → media_contract.zip.rules` abre com *"stream e limite agregado antes
de alocar/decodificar; limites aplicados também em upload individual"*. A ordem
não é estilística. Um ZIP de 40 KB pode declarar 40 GB de saída; quem chama
`ZipFile.extractall()` descobre isso quando a memória acaba. Aqui a ordem é:

    1. quanto entrou COMPRIMIDO?              (o chamador já mediu, e o teto vale)
    2. quantas entradas o diretório central declara?
    3. quanto ele DIZ que vai expandir, e em que razão?
    4. cada entrada é estruturalmente honesta? (nome, flags, atributos)
    5. só então: ler os bytes, com orçamento agregado que corta no meio
    6. só então: detectar MIME pelos BYTES
    7. só então: decodificar, com teto de pixel e prazo

Cada degrau só é pago se o anterior passou. É o oposto de "extrai e depois vê".

## As duas classes de recusa, e por que elas NÃO são a mesma

**O ARCHIVE inteiro cai** quando o container ataca quem o abre: traversal,
caminho absoluto, symlink, archive aninhado, entrada criptografada, caminho
duplicado depois de normalizado, bomba de expansão. `media_contract.zip.rules`:
*"arquivo malicioso invalida o archive"*. Aceitar "as outras nove entradas
estavam boas" seria deixar o atacante escolher quanto do lote ele contamina.

**A ENTRADA cai sozinha** quando o conteúdo simplesmente não serve: um PDF com
nome `.jpg`, um GIF (formato reconhecido e não aceito), uma imagem grande demais.
A mesma regra: *"mídia não suportada é resultado por entrada, nunca silêncio"*.
Silêncio aqui seria devolver 9 de 10 arquivos sem dizer o que houve com o
décimo — e o operador só descobriria na hora de montar o anúncio.

## MIME vem dos BYTES. Sempre.

Nem a extensão, nem o `Content-Type` da parte multipart entram na decisão. As
duas são declarações de quem envia. `test_criativo_mime_medido.py` já custou uma
rodada inteira desta casa para provar o mesmo ponto do outro lado (um motor que
gravava PNG e declarava JPEG chegava a `rendered` com todos os gates verdes).
Aqui a declaração do cliente nem é lida.

## O hash cobre os bytes FINAIS — os que sairiam daqui para o provedor

`media_contract.zip.rules`: *"gerar nomes internos opacos; descartar
EXIF/localização desnecessários; referência hash sobre bytes finais exatos
enviados"*. Se o saneamento muda um byte, o hash muda junto; do contrário a
dedup ("hash idêntico reusa master autorizado") apontaria para bytes que ninguém
mais tem.

E o saneamento é feito **no container, sem recodificar pixel**. Recodificar com
Pillow seria mais curto e teria um defeito caro: a saída depende da versão do
Pillow instalado, então o mesmo arquivo importado em duas máquinas produziria
dois hashes — e a dedup, que é a razão de o hash existir, deixaria de casar.
Retirar segmentos APPn de um JPEG e chunks auxiliares de um PNG é determinístico
e preserva os pixels bit a bit.

## Vídeo não é saneado, e isso está DITO em vez de escondido

Um MP4 carrega localização em `moov/udta` (`©xyz`, `loci`). Removê-la exige
remultiplexar: `stco`/`co64` guardam offsets ABSOLUTOS do arquivo, e tirar bytes
antes do `mdat` quebra todos eles. Sem um muxer, a alternativa honesta não é
"passar o vídeo com a localização dentro": é **recusar a entrada** e dizer por
quê. Vídeo sem esses boxes passa intacto, e o hash cobre exatamente esses bytes.
"""

from __future__ import annotations

import io
import posixpath
import re
import struct
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as _PrazoDoFuturo
from dataclasses import dataclass
from typing import Any, BinaryIO, Callable, Iterable, Protocol

from app.criativo.armazenamento import (
    MIMES_ACEITOS,
    MIMES_DE_IMAGEM,
    MIMES_DE_VIDEO,
    nome_seguro,
    sha256_de,
)

# ─────────────────────────────────────────────────────────────────────────────
# Vocabulário fechado — o mesmo da SPEC, sem tradução
# ─────────────────────────────────────────────────────────────────────────────
#
# Os nomes ficam em inglês porque são o CONTRATO declarado em
# `SPEC.json → media_contract.pipeline` / `.failures`. Traduzi-los aqui faria a
# CHECK do banco, o DTO da tela e o documento de aceite falarem três línguas
# sobre o mesmo estado — e a conferência "o estado gravado está no vocabulário?"
# viraria uma tabela de-para que alguém teria de manter.

RECEIVED = "RECEIVED"
QUARANTINED = "QUARANTINED"
INSPECTED = "INSPECTED"
IMPORTED_PRIVATE = "IMPORTED_PRIVATE"
POLICY_PENDING = "POLICY_PENDING"
READY_FOR_REGISTRATION = "READY_FOR_REGISTRATION"
REJECTED = "REJECTED"
PARTIAL_BATCH = "PARTIAL_BATCH"

#: Todo estado que pode ser gravado. A CHECK de
#: `criativo_importacao_entrada.estado` (v11_04) usa exatamente esta lista.
#:
#: ⚠️ `RECEIVED` e `QUARANTINED` NUNCA são persistidos nesta fatia, e isso é
#: declarado em vez de descoberto: a importação inteira acontece dentro de UMA
#: requisição, então as duas são fases de memória — os bytes chegaram, e ainda
#: não foram decodificados. Gravar linha para elas produziria estado que nenhum
#: leitor jamais veria e faria a tela oferecer um "acompanhar progresso" que não
#: existe. Elas ficam no vocabulário porque são o contrato da SPEC e porque a
#: fatia de registro remoto (outro ato, outra autorização) vai precisar delas.
ESTADOS: frozenset[str] = frozenset({
    RECEIVED, QUARANTINED, INSPECTED, IMPORTED_PRIVATE, POLICY_PENDING,
    READY_FOR_REGISTRATION, REJECTED, PARTIAL_BATCH,
})

ORIGEM_INDIVIDUAL = "UPLOAD_INDIVIDUAL"
ORIGEM_ZIP = "UPLOAD_ZIP"
ORIGENS: frozenset[str] = frozenset({ORIGEM_INDIVIDUAL, ORIGEM_ZIP})

#: Procedência de EXECUÇÃO do job que hospeda a mídia importada.
#:
#: ⚠️ Nem `volc_os` nem `observado`, e a distinção é a razão de a v11_04 existir.
#: `volc_os` afirma que este servidor RODOU um motor — e importar não é produzir
#: (regra F do cabeçalho de `v11_01_estudio_criativo.sql`). `observado` afirma
#: que lemos um build que JÁ EXISTIA no nosso próprio pipeline
#: (`video_observado.py` linhas 1-20). Um arquivo que um humano subiu não é
#: nenhum dos dois: ninguém rodou nada e não há build para observar.
PROCEDENCIA_EXECUCAO = "importado"

#: `criativo_briefing.modo` do briefing que hospeda a importação. Ver a CHECK
#: `criativo_briefing_formatos_nao_vazio` (v11_01:232-234): `observado` era a
#: única exceção a "todo briefing declara formatos", e a v11_04 acrescenta
#: `importado` pelo mesmo motivo — quem importa não PEDE formato, recebe o que
#: o arquivo é.
MODO_DE_PRODUCAO = "importado"

#: `criativo_master.motor` / `.motor_versao`. NOT NULL e não-vazios por
#: `criativo_master_procedencia_completa` (v11_01:432-433). "Quem produziu isto?"
#: tem de ter resposta mesmo quando a resposta é "ninguém aqui: veio de fora".
MOTOR = "importacao"
MOTOR_VERSAO = "v11_04"


# ─────────────────────────────────────────────────────────────────────────────
# Limites
# ─────────────────────────────────────────────────────────────────────────────


#: Os tetos do produto, transcritos de `SPEC.json → media_contract.zip`.
#:
#: `limits_source` da própria SPEC diz o que eles são: *"limites de segurança do
#: produto; confrontar limite real do provedor e usar o mais restritivo"*. Ou
#: seja: NÃO são os limites da Meta. Quando a receita de registro remoto chegar,
#: ela compara e aperta — nunca afrouxa.
TETO_ENTRADAS = 50
TETO_COMPRIMIDO_BYTES = 104_857_600
TETO_EXPANDIDO_BYTES = 262_144_000
TETO_RAZAO_DE_EXPANSAO = 100
TETO_IMAGEM_BYTES = 26_214_400
TETO_VIDEO_BYTES = 209_715_200

#: Tetos de DECODIFICAÇÃO. Não vêm da SPEC (ela pede "limite de pixels e
#: timeout" sem número) e por isso estão declarados aqui, com a razão de cada um.
#:
#: `TETO_IMAGEM_PIXELS`: o padrão anti-bomba do Pillow é 89.478.485 px
#: (`Image.MAX_IMAGE_PIXELS`). 50 Mpx fica abaixo dele de propósito — a saída
#: deste produto é peça de anúncio, e 50 Mpx já é ~4x a maior peça que qualquer
#: formato do `criativo_formato` pede. Um teto NOSSO, mais apertado que o da
#: biblioteca, é o que impede a defesa de depender da versão instalada.
TETO_IMAGEM_PIXELS = 50_000_000
#: 4K (3840×2160). Acima disso não é criativo de mídia paga, é master de edição.
TETO_VIDEO_PIXELS = 8_294_400
#: 10 minutos. Vídeo de anúncio vive em dezenas de segundos.
TETO_VIDEO_DURACAO_MS = 600_000
#: 10 min a 60 fps. Serve para barrar um contêiner que declara milhões de
#: amostras num arquivo curto — o análogo em vídeo da bomba de expansão.
TETO_VIDEO_FRAMES = 36_000
#: Prazo de parede da decodificação/medição de UMA entrada.
TETO_PRAZO_S = 5.0


@dataclass(frozen=True)
class Limites:
    """Os tetos efetivos de uma importação.

    ⚠️ Eles são parâmetro para poder APERTAR, nunca para afrouxar. `__post_init__`
    corta qualquer valor acima do teto do produto, então um chamador (ou um
    teste) pode pedir 1 MB de expansão máxima e não pode pedir 1 TB.

    A alternativa — constantes fixas — deixaria as regras de orçamento agregado
    sem prova barata: provar o corte no meio do stream exigiria montar um ZIP de
    250 MB em cada rodada da suíte. Uma defesa que só é exercitável com um
    arquivo gigante acaba não sendo exercitada.
    """

    entradas_max: int = TETO_ENTRADAS
    comprimido_bytes_max: int = TETO_COMPRIMIDO_BYTES
    expandido_bytes_max: int = TETO_EXPANDIDO_BYTES
    razao_de_expansao_max: int = TETO_RAZAO_DE_EXPANSAO
    imagem_bytes_max: int = TETO_IMAGEM_BYTES
    video_bytes_max: int = TETO_VIDEO_BYTES
    imagem_pixels_max: int = TETO_IMAGEM_PIXELS
    video_pixels_max: int = TETO_VIDEO_PIXELS
    video_duracao_ms_max: int = TETO_VIDEO_DURACAO_MS
    video_frames_max: int = TETO_VIDEO_FRAMES
    prazo_s: float = TETO_PRAZO_S

    _TETOS = {
        "entradas_max": TETO_ENTRADAS,
        "comprimido_bytes_max": TETO_COMPRIMIDO_BYTES,
        "expandido_bytes_max": TETO_EXPANDIDO_BYTES,
        "razao_de_expansao_max": TETO_RAZAO_DE_EXPANSAO,
        "imagem_bytes_max": TETO_IMAGEM_BYTES,
        "video_bytes_max": TETO_VIDEO_BYTES,
        "imagem_pixels_max": TETO_IMAGEM_PIXELS,
        "video_pixels_max": TETO_VIDEO_PIXELS,
        "video_duracao_ms_max": TETO_VIDEO_DURACAO_MS,
        "video_frames_max": TETO_VIDEO_FRAMES,
        "prazo_s": TETO_PRAZO_S,
    }

    def __post_init__(self) -> None:
        for nome, teto in self._TETOS.items():
            valor = getattr(self, nome)
            if valor is None or valor <= 0:
                raise ValueError(f"limite {nome} precisa ser positivo")
            if valor > teto:
                object.__setattr__(self, nome, teto)


LIMITES_PADRAO = Limites()


# ─────────────────────────────────────────────────────────────────────────────
# Recusas
# ─────────────────────────────────────────────────────────────────────────────


class ArchiveMalicioso(ValueError):
    """O container atacou quem o abriu. Invalida o lote INTEIRO.

    Carrega `codigo` porque a tela precisa dizer O QUE foi encontrado — "ZIP
    recusado" sozinho manda o operador adivinhar entre sete defeitos diferentes.
    """

    def __init__(self, codigo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.codigo = codigo


class PrazoEsgotado(TimeoutError):
    """A decodificação passou do prazo de parede e foi abandonada."""


# Recusas de ARCHIVE (matam o lote)
ARCHIVE_ILEGIVEL = "ARCHIVE_ILEGIVEL"
ARCHIVE_VAZIO = "ARCHIVE_VAZIO"
ARCHIVE_ENTRADAS_DEMAIS = "ARCHIVE_ENTRADAS_DEMAIS"
ARCHIVE_COMPRIMIDO_GRANDE_DEMAIS = "ARCHIVE_COMPRIMIDO_GRANDE_DEMAIS"
ARCHIVE_EXPANSAO_GRANDE_DEMAIS = "ARCHIVE_EXPANSAO_GRANDE_DEMAIS"
ARCHIVE_RAZAO_DE_EXPANSAO = "ARCHIVE_RAZAO_DE_EXPANSAO"
ARCHIVE_TRAVERSAL = "ARCHIVE_TRAVERSAL"
ARCHIVE_CAMINHO_ABSOLUTO = "ARCHIVE_CAMINHO_ABSOLUTO"
ARCHIVE_SYMLINK = "ARCHIVE_SYMLINK"
ARCHIVE_ANINHADO = "ARCHIVE_ANINHADO"
ARCHIVE_CRIPTOGRAFADO = "ARCHIVE_CRIPTOGRAFADO"
ARCHIVE_CAMINHO_DUPLICADO = "ARCHIVE_CAMINHO_DUPLICADO"
ARCHIVE_NOME_INVALIDO = "ARCHIVE_NOME_INVALIDO"

# Recusas de ENTRADA (o lote sobrevive, a entrada não)
ENTRADA_VAZIA = "ENTRADA_VAZIA"
MIME_NAO_SUPORTADO = "MIME_NAO_SUPORTADO"
IMAGEM_GRANDE_DEMAIS = "IMAGEM_GRANDE_DEMAIS"
VIDEO_GRANDE_DEMAIS = "VIDEO_GRANDE_DEMAIS"
PIXELS_DEMAIS = "PIXELS_DEMAIS"
DECODIFICACAO_FALHOU = "DECODIFICACAO_FALHOU"
DECODIFICACAO_EXPIROU = "DECODIFICACAO_EXPIROU"
VIDEO_LONGO_DEMAIS = "VIDEO_LONGO_DEMAIS"
VIDEO_FRAMES_DEMAIS = "VIDEO_FRAMES_DEMAIS"
VIDEO_COM_LOCALIZACAO = "VIDEO_COM_LOCALIZACAO"


# ─────────────────────────────────────────────────────────────────────────────
# Detecção de tipo pelos BYTES
# ─────────────────────────────────────────────────────────────────────────────

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
_GIF87, _GIF89 = b"GIF87a", b"GIF89a"
_RIFF = b"RIFF"
_WEBP = b"WEBP"

#: `ftyp` no offset 4 é o cabeçalho de todo arquivo da família ISO-BMFF.
#: A marca (`brand`) diz qual: `isom`/`mp4x`/`avc1`/`M4V ` são MP4;
#: `qt  ` é QuickTime e NÃO é aceito, mesmo compartilhando o container.
_MARCAS_MP4 = (
    b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42",
    b"avc1", b"M4V ", b"dash", b"mmp4",
)

#: Assinaturas de ARCHIVE. Achar qualquer uma DENTRO de um ZIP é archive
#: aninhado — o vetor clássico de bomba em camadas, onde cada nível respeita o
#: limite do nível de cima e o produto final não respeita nada.
_ASSINATURAS_DE_ARCHIVE: tuple[tuple[bytes, str], ...] = (
    (b"PK\x03\x04", "zip"),
    (b"PK\x05\x06", "zip"),
    (b"PK\x07\x08", "zip"),
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"Rar!\x1a\x07", "rar"),
    (b"\x04\x22\x4d\x18", "lz4"),
    (b"\x28\xb5\x2f\xfd", "zstd"),
)


def detectar_mime(dados: bytes) -> str | None:
    """O tipo real, lido da assinatura. `None` quando não é nenhum conhecido.

    ⚠️ Devolver `None` NÃO é "não apurei": é "olhei os bytes e não reconheci".
    A diferença é a mesma que `medir_imagem.FORMATOS_RECONHECIDOS` já registra
    em `volc_ads/criativo/adaptadores/medir_imagem.py`, e ela importa porque
    tratar refutação como ausência é o que deixa a declaração falsa passar.

    O GIF é reconhecido de propósito, e não está em `MIMES_ACEITOS`
    (`armazenamento.py:62-64`). Reconhecer para RECUSAR com nome é melhor que
    não reconhecer: o operador que subiu um GIF recebe "GIF não é aceito" em vez
    de "arquivo desconhecido".
    """
    if dados.startswith(_PNG):
        return "image/png"
    if dados.startswith(_JPEG):
        return "image/jpeg"
    if dados.startswith(_GIF87) or dados.startswith(_GIF89):
        return "image/gif"
    if len(dados) >= 12 and dados[:4] == _RIFF and dados[8:12] == _WEBP:
        return "image/webp"
    if len(dados) >= 12 and dados[4:8] == b"ftyp":
        marca = dados[8:12]
        if marca in _MARCAS_MP4:
            return "video/mp4"
        return None
    return None


def tipo_de_archive(dados: bytes) -> str | None:
    """O formato de compactação dos bytes, ou `None` se não for um archive."""
    for assinatura, nome in _ASSINATURAS_DE_ARCHIVE:
        if dados.startswith(assinatura):
            return nome
    return None


def e_zip(dados: bytes) -> bool:
    """ZIP pela assinatura local — nunca pela extensão nem pelo `Content-Type`."""
    return dados.startswith(b"PK\x03\x04") or dados.startswith(b"PK\x05\x06")


# ─────────────────────────────────────────────────────────────────────────────
# Nomes: o normalizado (para o humano) e o opaco (para a máquina)
# ─────────────────────────────────────────────────────────────────────────────

_SEPARADOR = re.compile(r"[\\/]+")


def normalizar_caminho(nome: str) -> str:
    """A forma canônica de um caminho de ZIP, para detectar DUPLICATA.

    Três normalizações, e cada uma fecha um jeito diferente de escrever o mesmo
    arquivo duas vezes: `\\` vira `/` (ZIP do Windows), `./a` e `a//b` colapsam
    (`posixpath.normpath`), e `Foto.JPG` casa com `foto.jpg` (`casefold`, porque
    o destino pode ser um sistema de arquivos que não distingue caixa).

    ⚠️ Esta função NÃO decide segurança. `..` sobrevive a ela de propósito: quem
    recusa traversal é `_conferir_estrutura_da_entrada`, e uma normalização que
    já tivesse apagado o `..` esconderia o ataque da checagem que existe para
    encontrá-lo.
    """
    bruto = unicodedata.normalize("NFKC", nome or "")
    bruto = _SEPARADOR.sub("/", bruto)
    limpo = posixpath.normpath(bruto).lstrip("/")
    return limpo.casefold()


_EXTENSAO_DO_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "video/mp4": "mp4",
}


def extensao_do_mime(mime: str) -> str:
    """A extensão vem do MIME MEDIDO, nunca do nome que o cliente mandou."""
    return _EXTENSAO_DO_MIME.get(mime, "bin")


def nome_opaco(indice: int, content_hash: str, mime: str) -> str:
    """O nome interno. Deriva do índice e do HASH — nunca do nome do usuário.

    `media_contract.zip.rules`: *"gerar nomes internos opacos"*. O nome que o
    operador digitou é dado de terceiro: ele pode conter marca de cliente, nome
    de pessoa, ou simplesmente uma frase que ninguém quer ver num log de proxy.
    Ele sobrevive como METADADO (`nome_normalizado`), e não como endereço.
    """
    curto = content_hash.removeprefix("sha256:")[:32]
    return f"{indice:04d}-{curto}.{extensao_do_mime(mime)}"


# ─────────────────────────────────────────────────────────────────────────────
# Saneamento: tirar metadado sem tocar em pixel
# ─────────────────────────────────────────────────────────────────────────────


def _jpeg_sem_metadados(dados: bytes) -> bytes:
    """Remove APPn (0xE0-0xEF) e COM (0xFE). Preserva a imagem bit a bit.

    APP1 é onde moram EXIF (com GPS) e XMP; APP2 leva ICC; APP13 leva IPTC, que
    frequentemente carrega autoria e localização. Nenhum deles é necessário para
    exibir a imagem, e todos são texto controlado por quem enviou o arquivo.

    A caminhada para no SOS (0xDA): dali em diante são dados comprimidos, e
    procurar marcador dentro deles produziria recorte no meio da imagem. Mesmo
    raciocínio de `medir_imagem._do_jpeg`.
    """
    if not dados.startswith(_JPEG[:2]):
        return dados
    saida = bytearray(dados[:2])
    i, n = 2, len(dados)
    while i + 1 < n:
        if dados[i] != 0xFF:
            # Fora de sincronia: o resto vai inteiro. Melhor devolver um arquivo
            # que ainda abre do que cortar às cegas.
            saida += dados[i:]
            return bytes(saida)
        marcador = dados[i + 1]
        if marcador == 0xFF:
            saida.append(0xFF)
            i += 1
            continue
        if marcador in (0xD8,) or 0xD0 <= marcador <= 0xD7:
            saida += dados[i:i + 2]
            i += 2
            continue
        if marcador == 0xDA:
            saida += dados[i:]
            return bytes(saida)
        if i + 4 > n:
            saida += dados[i:]
            return bytes(saida)
        (tamanho,) = struct.unpack(">H", dados[i + 2:i + 4])
        if tamanho < 2 or i + 2 + tamanho > n:
            saida += dados[i:]
            return bytes(saida)
        descartar = 0xE0 <= marcador <= 0xEF or marcador == 0xFE
        if not descartar:
            saida += dados[i:i + 2 + tamanho]
        i += 2 + tamanho
    saida += dados[i:]
    return bytes(saida)


#: Os chunks de PNG que ficam. Tudo que não está aqui sai — inclusive `eXIf`,
#: `tEXt`, `iTXt`, `zTXt` (texto livre do autor) e os chunks de APNG, que
#: transformariam uma "imagem" em animação sem ninguém ter pedido.
_PNG_CHUNKS_PRESERVADOS = frozenset({
    b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"sRGB", b"gAMA", b"cHRM",
})


def _png_so_criticos(dados: bytes) -> bytes:
    if not dados.startswith(_PNG):
        return dados
    saida = bytearray(_PNG)
    i, n = len(_PNG), len(dados)
    while i + 8 <= n:
        (tamanho,) = struct.unpack(">I", dados[i:i + 4])
        tipo = dados[i + 4:i + 8]
        fim = i + 12 + tamanho  # tamanho + tipo(4) + dados + crc(4)
        if tamanho > n or fim > n:
            # Chunk que não cabe: cabeçalho corrompido. Devolve o original, e
            # quem decide é o decodificador — inventar um arquivo "consertado"
            # seria pior que passar o que veio.
            return dados
        if tipo in _PNG_CHUNKS_PRESERVADOS:
            saida += dados[i:fim]
        i = fim
        if tipo == b"IEND":
            break
    return bytes(saida)


#: Chunks RIFF/WebP de metadado. `EXIF` e `XMP ` levam câmera e GPS; `ICCP` é
#: perfil de cor e não é necessário para o pixel.
_WEBP_CHUNKS_DESCARTADOS = frozenset({b"EXIF", b"XMP ", b"ICCP"})


def _webp_sem_metadados(dados: bytes) -> bytes:
    if len(dados) < 12 or dados[:4] != _RIFF or dados[8:12] != _WEBP:
        return dados
    corpo = bytearray()
    i, n = 12, len(dados)
    while i + 8 <= n:
        tipo = dados[i:i + 4]
        (tamanho,) = struct.unpack("<I", dados[i + 4:i + 8])
        fim = i + 8 + tamanho + (tamanho & 1)  # chunks RIFF são pareados
        if fim > n:
            return dados
        if tipo not in _WEBP_CHUNKS_DESCARTADOS:
            corpo += dados[i:fim]
        i = fim
    if not corpo:
        return dados
    return bytes(_RIFF + struct.pack("<I", len(corpo) + 4) + _WEBP + corpo)


def sanear(dados: bytes, mime: str) -> bytes:
    """Os bytes que sairiam daqui para o provedor. É sobre ELES que o hash cai.

    Vídeo passa intacto: ver o cabeçalho do módulo — remover `udta` de um MP4
    desloca o `mdat` e invalida os offsets absolutos de `stco`/`co64`. Um MP4
    com localização é RECUSADO, não remendado.
    """
    if mime == "image/jpeg":
        return _jpeg_sem_metadados(dados)
    if mime == "image/png":
        return _png_so_criticos(dados)
    if mime == "image/webp":
        return _webp_sem_metadados(dados)
    return dados


# ─────────────────────────────────────────────────────────────────────────────
# Decodificação com prazo
# ─────────────────────────────────────────────────────────────────────────────


def com_prazo(fn: Callable[[], Any], *, segundos: float) -> Any:
    """Roda `fn` numa thread e desiste depois de `segundos`.

    ⚠️ O QUE ISTO NÃO FAZ: matar a thread. CPython não tem como interromper
    código nativo (e o decodificador É nativo). O que esta função garante é que
    o REQUEST não fica preso — a entrada é recusada com `DECODIFICACAO_EXPIROU`
    e o operador recebe resposta.

    A thread abandonada é aceitável porque ela é limitada pelos tetos que já
    rodaram ANTES: os bytes cabem em `imagem_bytes_max` e a dimensão foi lida do
    CABEÇALHO e conferida contra `imagem_pixels_max` antes de qualquer `load()`.
    O prazo é a terceira barreira, não a única.
    """
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        futuro = executor.submit(fn)
        try:
            return futuro.result(timeout=segundos)
        except _PrazoDoFuturo as e:
            raise PrazoEsgotado(f"decodificação passou de {segundos}s") from e
    finally:
        # `wait=False`: esperar a thread perdida derrotaria o prazo inteiro.
        executor.shutdown(wait=False, cancel_futures=True)


@dataclass(frozen=True)
class MedidaDeImagem:
    largura: int | None
    altura: int | None


class DecodificadorDeImagem(Protocol):
    """Quem abre os bytes e diz se eles são mesmo uma imagem."""

    def __call__(self, dados: bytes, mime: str, *, pixels_max: int) -> MedidaDeImagem:
        ...


class PixelsDemais(ValueError):
    """O cabeçalho declarou mais pixel que o teto — recusado ANTES de alocar.

    Pública de propósito: um decodificador injetado (outro motor, um dublê de
    teste) precisa de um jeito de dizer "grande demais" que não se confunda com
    "arquivo corrompido". Sem ela, os dois virariam `DECODIFICACAO_FALHOU` e a
    tela não saberia dizer ao operador se ele deve reduzir a imagem ou trocá-la.
    """


def decodificar_com_pillow(
    dados: bytes, mime: str, *, pixels_max: int
) -> MedidaDeImagem:
    """Abre o cabeçalho, confere o teto de pixel, e SÓ ENTÃO decodifica.

    A ordem é a defesa. `Image.open` lê só o cabeçalho: é ali que a dimensão
    aparece, e é ali — antes de qualquer alocação de raster — que uma imagem de
    60.000x60.000 é recusada. `load()` depois disso já sabe quanto vai custar.

    Pillow está em `backend/requirements.txt` (linha 35) por decisão registrada:
    ele é capacidade de produto, não ferramenta de teste.
    """
    from PIL import Image  # noqa: PLC0415 — import tardio, como no resto da casa

    with Image.open(io.BytesIO(dados)) as img:
        largura, altura = img.size
        if largura <= 0 or altura <= 0:
            raise ValueError("cabeçalho sem dimensão utilizável")
        if largura * altura > pixels_max:
            raise PixelsDemais(f"{largura}x{altura} acima de {pixels_max} px")
        # Só agora os pixels saem do disco/memória comprimida. Um arquivo que
        # mente sobre o próprio conteúdo cai aqui, e cair aqui é o ponto.
        img.load()
        return MedidaDeImagem(largura=largura, altura=altura)


# ─────────────────────────────────────────────────────────────────────────────
# Medição de MP4 — caminhada de boxes, sem ffprobe
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MedidaDeVideo:
    """Ausência é `None`, nunca 0 — regra B de `v11_01_estudio_criativo.sql`."""

    largura: int | None = None
    altura: int | None = None
    duracao_ms: int | None = None
    frames: int | None = None
    tem_localizacao: bool = False


#: Boxes que CONTÊM outros boxes. Descer em qualquer coisa fora desta lista
#: leria payload como se fosse estrutura.
_BOXES_CONTAINER = frozenset({b"moov", b"trak", b"mdia", b"minf", b"stbl", b"udta"})

#: Boxes que declaram localização geográfica.
_BOXES_DE_LOCALIZACAO = frozenset({b"\xa9xyz", b"loci", b"gps "})

#: Orçamento de caminhada. Um MP4 forjado pode declarar milhares de boxes
#: aninhados; sem teto, a "medição" vira o próprio ataque.
_MAX_BOXES = 4096
_MAX_PROFUNDIDADE = 8


def medir_mp4(dados: bytes) -> MedidaDeVideo:
    """Duração, dimensão, amostras e presença de localização — só stdlib.

    `ffprobe` mediria melhor e não está garantido neste servidor
    (`video_observado.py:981` já registra a mesma ausência). Ler os boxes cobre
    o que esta fatia precisa decidir e não adiciona dependência de sistema.
    """
    estado: dict[str, Any] = {
        "duracao_ms": None, "largura": None, "altura": None,
        "frames": None, "localizacao": False, "boxes": 0,
    }
    _andar_boxes(dados, 0, len(dados), 0, estado)
    return MedidaDeVideo(
        largura=estado["largura"],
        altura=estado["altura"],
        duracao_ms=estado["duracao_ms"],
        frames=estado["frames"],
        tem_localizacao=bool(estado["localizacao"]),
    )


def _andar_boxes(dados: bytes, inicio: int, fim: int, nivel: int,
                 estado: dict[str, Any]) -> None:
    if nivel > _MAX_PROFUNDIDADE:
        return
    i = inicio
    while i + 8 <= fim:
        estado["boxes"] += 1
        if estado["boxes"] > _MAX_BOXES:
            return
        (tamanho,) = struct.unpack(">I", dados[i:i + 4])
        tipo = dados[i + 4:i + 8]
        corpo = i + 8
        if tamanho == 1:
            if corpo + 8 > fim:
                return
            (tamanho,) = struct.unpack(">Q", dados[corpo:corpo + 8])
            corpo += 8
        elif tamanho == 0:
            tamanho = fim - i
        if tamanho < 8 or i + tamanho > fim:
            # Box que não cabe: parar. Continuar seria ler offset inventado.
            return
        proximo = i + tamanho
        if tipo in _BOXES_DE_LOCALIZACAO:
            estado["localizacao"] = True
        elif tipo in _BOXES_CONTAINER:
            _andar_boxes(dados, corpo, proximo, nivel + 1, estado)
        elif tipo == b"meta":
            # `meta` é FullBox: 4 bytes de versão/flags antes dos filhos.
            _andar_boxes(dados, corpo + 4, proximo, nivel + 1, estado)
        elif tipo == b"mvhd":
            _ler_mvhd(dados[corpo:proximo], estado)
        elif tipo == b"tkhd":
            _ler_tkhd(dados[corpo:proximo], estado)
        elif tipo == b"stsz":
            _ler_stsz(dados[corpo:proximo], estado)
        i = proximo


def _ler_mvhd(payload: bytes, estado: dict[str, Any]) -> None:
    if len(payload) < 4:
        return
    versao = payload[0]
    try:
        if versao == 1 and len(payload) >= 32:
            escala, duracao = struct.unpack(">IQ", payload[20:32])
        elif versao == 0 and len(payload) >= 20:
            escala, duracao = struct.unpack(">II", payload[12:20])
        else:
            return
    except struct.error:
        return
    if escala <= 0 or duracao <= 0:
        # Ausência, não zero. Um `duration=0` de contêiner fragmentado é
        # "não sei", e gravar 0 faria a validação ler "mediu e deu zero".
        return
    estado["duracao_ms"] = int(duracao * 1000 // escala) or None


def _ler_tkhd(payload: bytes, estado: dict[str, Any]) -> None:
    # `width`/`height` são os ÚLTIMOS 8 bytes do payload em qualquer versão
    # (16.16 fixed-point). Ler pelo fim evita duplicar o cálculo de offset das
    # duas versões, que é onde este parser erraria em silêncio.
    if len(payload) < 8:
        return
    largura_fixa, altura_fixa = struct.unpack(">II", payload[-8:])
    largura, altura = largura_fixa >> 16, altura_fixa >> 16
    if largura <= 0 or altura <= 0:
        return
    # A maior trilha vence: um MP4 tem trilha de áudio com 0x0 e a de vídeo com
    # a dimensão real.
    if (estado["largura"] or 0) * (estado["altura"] or 0) < largura * altura:
        estado["largura"], estado["altura"] = largura, altura


def _ler_stsz(payload: bytes, estado: dict[str, Any]) -> None:
    if len(payload) < 12:
        return
    (contagem,) = struct.unpack(">I", payload[8:12])
    if contagem <= 0:
        return
    estado["frames"] = max(estado["frames"] or 0, contagem)


# ─────────────────────────────────────────────────────────────────────────────
# O resultado
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EntradaInspecionada:
    """Uma entrada, e tudo que os bytes dela revelaram.

    `conteudo` são os bytes FINAIS (já saneados) e existe só em memória: ele
    NUNCA vai para o banco. `content_hash` é o hash DELES, e é isso que amarra o
    registro aos bytes que sairiam daqui.
    """

    indice: int
    nome_normalizado: str
    estado: str
    mime_detectado: str | None = None
    bytes: int | None = None
    content_hash: str | None = None
    insumo_hash: str | None = None
    largura: int | None = None
    altura: int | None = None
    duracao_ms: int | None = None
    motivo_recusa: str | None = None
    detalhe: str | None = None
    conteudo: bytes | None = None

    @property
    def aceita(self) -> bool:
        return self.estado == INSPECTED

    @property
    def nome_interno(self) -> str | None:
        if not (self.content_hash and self.mime_detectado):
            return None
        return nome_opaco(self.indice, self.content_hash, self.mime_detectado)

    def sem_conteudo(self) -> "EntradaInspecionada":
        """A mesma entrada, sem os bytes. É esta que sobe para persistência."""
        return EntradaInspecionada(**{**self.__dict__, "conteudo": None})


@dataclass(frozen=True)
class LoteInspecionado:
    origem: str
    nome_arquivo_original: str | None
    bytes_comprimidos: int | None
    entradas: tuple[EntradaInspecionada, ...] = ()
    motivo_recusa: str | None = None
    detalhe: str | None = None

    @property
    def entradas_total(self) -> int:
        return len(self.entradas)

    @property
    def aceitas(self) -> tuple[EntradaInspecionada, ...]:
        return tuple(e for e in self.entradas if e.aceita)

    @property
    def estado(self) -> str:
        """O estado do LOTE deriva das entradas — ele não é declarado.

        Um campo separado poderia divergir da lista (lote `INSPECTED` com zero
        entradas aceitas), e a tela leria o campo.
        """
        if self.motivo_recusa:
            return REJECTED
        if not self.entradas:
            return REJECTED
        aceitas = len(self.aceitas)
        if aceitas == 0:
            return REJECTED
        if aceitas < len(self.entradas):
            return PARTIAL_BATCH
        return INSPECTED


# ─────────────────────────────────────────────────────────────────────────────
# Orçamento agregado
# ─────────────────────────────────────────────────────────────────────────────


class OrcamentoEstourado(ArchiveMalicioso):
    """O agregado passou do teto no meio da leitura."""


@dataclass
class Orcamento:
    """Quanto ainda pode ser lido, no lote INTEIRO.

    Ele é mutável e compartilhado de propósito: um teto por arquivo não impede
    50 arquivos de 25 MB. O que a SPEC pede é *limite agregado*, e agregado
    significa um só contador atravessando todas as entradas.
    """

    expandido_max: int
    comprimido: int
    razao_max: int
    gasto: int = 0

    def cobrar(self, quantos: int) -> None:
        self.gasto += quantos
        if self.gasto > self.expandido_max:
            raise OrcamentoEstourado(
                ARCHIVE_EXPANSAO_GRANDE_DEMAIS,
                f"expansão passou de {self.expandido_max} bytes",
            )
        if self.comprimido > 0 and self.gasto > self.comprimido * self.razao_max:
            raise OrcamentoEstourado(
                ARCHIVE_RAZAO_DE_EXPANSAO,
                f"razão de expansão passou de {self.razao_max}:1",
            )


_BLOCO = 64 * 1024


def ler_com_teto(fluxo: BinaryIO, teto: int, *, codigo: str, mensagem: str) -> bytes:
    """Lê um stream em blocos e ABORTA no byte que passa do teto.

    ⚠️ `fluxo.read()` sem argumento aloca o corpo inteiro ANTES de qualquer
    checagem — é a alocação que a regra da SPEC manda evitar. Aqui o corte
    acontece com `teto + 1` bytes na memória, não com o payload inteiro.
    """
    pedacos: list[bytes] = []
    total = 0
    while True:
        bloco = fluxo.read(_BLOCO)
        if not bloco:
            break
        total += len(bloco)
        if total > teto:
            raise ArchiveMalicioso(codigo, mensagem)
        pedacos.append(bloco)
    return b"".join(pedacos)


# ─────────────────────────────────────────────────────────────────────────────
# Inspeção de UMA entrada
# ─────────────────────────────────────────────────────────────────────────────


def inspecionar_bytes(
    indice: int,
    nome: str,
    dados: bytes,
    *,
    limites: Limites = LIMITES_PADRAO,
    decodificador: DecodificadorDeImagem = decodificar_com_pillow,
    medidor_de_video: Callable[[bytes], MedidaDeVideo] = medir_mp4,
) -> EntradaInspecionada:
    """Um arquivo, do byte cru ao veredito. Nunca levanta por conteúdo ruim.

    Recusa de CONTEÚDO vira `EntradaInspecionada(estado=REJECTED, motivo=...)`,
    porque *"mídia não suportada é resultado por entrada, nunca silêncio"*.
    Quem levanta é só o que ataca o container, e isso acontece no chamador.
    """
    normalizado = nome_seguro(nome)

    def recusa(codigo: str, detalhe: str | None = None) -> EntradaInspecionada:
        return EntradaInspecionada(
            indice=indice, nome_normalizado=normalizado, estado=REJECTED,
            motivo_recusa=codigo, detalhe=detalhe,
            bytes=len(dados) or None,
        )

    if not dados:
        # Zero byte é ausência de arquivo, não um arquivo que mede zero.
        return EntradaInspecionada(
            indice=indice, nome_normalizado=normalizado, estado=REJECTED,
            motivo_recusa=ENTRADA_VAZIA, bytes=None,
        )

    mime = detectar_mime(dados)
    if mime is None or mime not in MIMES_ACEITOS:
        return recusa(
            MIME_NAO_SUPORTADO,
            f"assinatura lida: {mime or 'desconhecida'}"
            f" (a extensão do arquivo não é considerada)",
        )

    if mime in MIMES_DE_IMAGEM and len(dados) > limites.imagem_bytes_max:
        return recusa(IMAGEM_GRANDE_DEMAIS,
                      f"{len(dados)} bytes acima de {limites.imagem_bytes_max}")
    if mime in MIMES_DE_VIDEO and len(dados) > limites.video_bytes_max:
        return recusa(VIDEO_GRANDE_DEMAIS,
                      f"{len(dados)} bytes acima de {limites.video_bytes_max}")

    # O saneamento vem ANTES da medição e do hash: o que vale é o arquivo final.
    finais = sanear(dados, mime)
    if not finais:
        return recusa(DECODIFICACAO_FALHOU, "saneamento produziu arquivo vazio")

    largura = altura = duracao_ms = None
    if mime in MIMES_DE_IMAGEM:
        try:
            medida = com_prazo(
                lambda: decodificador(finais, mime,
                                      pixels_max=limites.imagem_pixels_max),
                segundos=limites.prazo_s,
            )
        except PrazoEsgotado as e:
            return recusa(DECODIFICACAO_EXPIROU, str(e))
        except PixelsDemais as e:
            return recusa(PIXELS_DEMAIS, str(e))
        except Exception as e:  # noqa: BLE001 — decodificador de terceiro
            return recusa(DECODIFICACAO_FALHOU, type(e).__name__)
        largura, altura = medida.largura, medida.altura
    else:
        try:
            medida_v = com_prazo(lambda: medidor_de_video(finais),
                                 segundos=limites.prazo_s)
        except PrazoEsgotado as e:
            return recusa(DECODIFICACAO_EXPIROU, str(e))
        except Exception as e:  # noqa: BLE001
            return recusa(DECODIFICACAO_FALHOU, type(e).__name__)
        if medida_v.tem_localizacao:
            # Ver o cabeçalho: sem muxer, remover é quebrar o arquivo. Recusar é
            # a única saída que não vaza a localização nem entrega lixo.
            return recusa(VIDEO_COM_LOCALIZACAO,
                          "o MP4 declara localização e este servidor não "
                          "remultiplexa para removê-la")
        if (medida_v.duracao_ms or 0) > limites.video_duracao_ms_max:
            return recusa(VIDEO_LONGO_DEMAIS,
                          f"{medida_v.duracao_ms} ms acima de "
                          f"{limites.video_duracao_ms_max}")
        if (medida_v.frames or 0) > limites.video_frames_max:
            return recusa(VIDEO_FRAMES_DEMAIS,
                          f"{medida_v.frames} amostras acima de "
                          f"{limites.video_frames_max}")
        if (medida_v.largura or 0) * (medida_v.altura or 0) > limites.video_pixels_max:
            return recusa(PIXELS_DEMAIS,
                          f"{medida_v.largura}x{medida_v.altura} acima de "
                          f"{limites.video_pixels_max} px")
        largura, altura = medida_v.largura, medida_v.altura
        duracao_ms = medida_v.duracao_ms

    return EntradaInspecionada(
        indice=indice,
        nome_normalizado=normalizado,
        estado=INSPECTED,
        mime_detectado=mime,
        bytes=len(finais) or None,
        # O hash dos bytes FINAIS. Se o saneamento tirou um APP1, este número já
        # é diferente do `insumo_hash` — e é este que a dedup usa.
        content_hash=sha256_de(finais),
        # O hash do que ENTROU. `criativo_master.insumo_hash` é NOT NULL
        # (v11_01:382-385) e pergunta "o que foi mandado para o motor?"; numa
        # importação, o insumo é o próprio arquivo recebido.
        insumo_hash=sha256_de(dados),
        largura=largura,
        altura=altura,
        duracao_ms=duracao_ms,
        conteudo=finais,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Lote individual
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ArquivoRecebido:
    """Uma parte de upload, já lida. `nome` é o que o cliente declarou."""

    nome: str
    dados: bytes


def importar_individual(
    arquivos: Iterable[ArquivoRecebido],
    *,
    limites: Limites = LIMITES_PADRAO,
    decodificador: DecodificadorDeImagem = decodificar_com_pillow,
    medidor_de_video: Callable[[bytes], MedidaDeVideo] = medir_mp4,
) -> LoteInspecionado:
    """Upload individual — com OS MESMOS limites do ZIP.

    A SPEC é explícita: *"limites aplicados também em upload individual"*. Sem
    isto, quem quisesse contornar o teto agregado do ZIP mandaria 50 partes
    multipart e o teto não existiria.
    """
    itens = list(arquivos)
    if not itens:
        return LoteInspecionado(
            origem=ORIGEM_INDIVIDUAL, nome_arquivo_original=None,
            bytes_comprimidos=None, motivo_recusa=ARCHIVE_VAZIO,
            detalhe="nenhum arquivo na requisição",
        )
    if len(itens) > limites.entradas_max:
        return LoteInspecionado(
            origem=ORIGEM_INDIVIDUAL, nome_arquivo_original=None,
            bytes_comprimidos=None, motivo_recusa=ARCHIVE_ENTRADAS_DEMAIS,
            detalhe=f"{len(itens)} arquivos acima de {limites.entradas_max}",
        )

    total = sum(len(a.dados) for a in itens)
    if total > limites.expandido_bytes_max:
        return LoteInspecionado(
            origem=ORIGEM_INDIVIDUAL, nome_arquivo_original=None,
            bytes_comprimidos=total, motivo_recusa=ARCHIVE_EXPANSAO_GRANDE_DEMAIS,
            detalhe=f"{total} bytes acima de {limites.expandido_bytes_max}",
        )

    # Duplicata de caminho normalizado vale aqui também: duas partes chamadas
    # `Foto.JPG` e `foto.jpg` são o mesmo destino, e aceitar as duas faria uma
    # sobrescrever a outra em qualquer sistema de arquivos indiferente a caixa.
    vistos: set[str] = set()
    for a in itens:
        chave = normalizar_caminho(a.nome)
        if chave in vistos:
            return LoteInspecionado(
                origem=ORIGEM_INDIVIDUAL, nome_arquivo_original=None,
                bytes_comprimidos=total,
                motivo_recusa=ARCHIVE_CAMINHO_DUPLICADO,
                detalhe=f"caminho repetido depois de normalizado: {chave}",
            )
        vistos.add(chave)

    entradas = tuple(
        inspecionar_bytes(i, a.nome, a.dados, limites=limites,
                          decodificador=decodificador,
                          medidor_de_video=medidor_de_video)
        for i, a in enumerate(itens)
    )
    return LoteInspecionado(
        origem=ORIGEM_INDIVIDUAL,
        nome_arquivo_original=nome_seguro(itens[0].nome) if len(itens) == 1 else None,
        bytes_comprimidos=total,
        entradas=entradas,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Lote por ZIP
# ─────────────────────────────────────────────────────────────────────────────

#: Bit 0 do campo de flags gerais: entrada criptografada.
_FLAG_CRIPTOGRAFADO = 0x1
#: Bits 12-13: Strong Encryption / Central Directory Encryption.
_FLAG_CRIPTOGRAFIA_FORTE = 0x40
#: `S_IFLNK` nos 16 bits altos de `external_attr` (ZIP criado em Unix).
_MODO_SYMLINK = 0xA000
_MASCARA_TIPO = 0xF000

_UNIDADE_WINDOWS = re.compile(r"^[A-Za-z]:")


def _conferir_estrutura_da_entrada(zi: zipfile.ZipInfo, vistos: set[str]) -> str:
    """Tudo que dá para saber SEM descomprimir um byte. Levanta ou devolve a chave.

    A ordem é do mais barato para o mais caro, e do mais grave para o menos:
    cifra e symlink primeiro porque decidem se sequer faz sentido olhar o nome.
    """
    nome = zi.filename or ""
    if not nome or "\x00" in nome:
        raise ArchiveMalicioso(ARCHIVE_NOME_INVALIDO,
                              "entrada com nome vazio ou com byte nulo")

    if zi.flag_bits & (_FLAG_CRIPTOGRAFADO | _FLAG_CRIPTOGRAFIA_FORTE):
        # Não é "pede senha": é conteúdo que NÃO PODE ser inspecionado. Aceitar
        # o que não se consegue olhar é exatamente o que o portão de política
        # chama de `GATE_UNAVAILABLE`, e aqui não há sequer o que registrar.
        raise ArchiveMalicioso(
            ARCHIVE_CRIPTOGRAFADO,
            f"entrada criptografada: {nome_seguro(nome)}",
        )

    modo = (zi.external_attr >> 16) & _MASCARA_TIPO
    if modo == _MODO_SYMLINK:
        # O alvo do link é texto controlado pelo atacante. Seguir vira leitura
        # de `/etc/passwd`; não seguir e guardar vira um "arquivo" que aponta
        # para fora do acervo.
        raise ArchiveMalicioso(ARCHIVE_SYMLINK,
                               f"entrada é symlink: {nome_seguro(nome)}")

    if nome.startswith("/") or nome.startswith("\\") or _UNIDADE_WINDOWS.match(nome):
        raise ArchiveMalicioso(ARCHIVE_CAMINHO_ABSOLUTO,
                               f"caminho absoluto: {nome_seguro(nome)}")

    partes = _SEPARADOR.sub("/", unicodedata.normalize("NFKC", nome)).split("/")
    if any(p == ".." for p in partes):
        raise ArchiveMalicioso(ARCHIVE_TRAVERSAL,
                               f"caminho sobe diretório: {nome_seguro(nome)}")

    chave = normalizar_caminho(nome)
    if not chave or chave == ".":
        raise ArchiveMalicioso(ARCHIVE_NOME_INVALIDO,
                              "entrada sem nome utilizável")
    if chave in vistos:
        # Duas entradas para o mesmo destino: a segunda sobrescreve a primeira e
        # o que fica no acervo depende da ordem de extração. Um ZIP que não sabe
        # dizer qual dos dois arquivos é o arquivo não é um lote confiável.
        raise ArchiveMalicioso(
            ARCHIVE_CAMINHO_DUPLICADO,
            f"caminho repetido depois de normalizado: {chave}",
        )
    vistos.add(chave)
    return chave


def importar_zip(
    dados_do_zip: bytes,
    *,
    nome_arquivo: str | None = None,
    limites: Limites = LIMITES_PADRAO,
    decodificador: DecodificadorDeImagem = decodificar_com_pillow,
    medidor_de_video: Callable[[bytes], MedidaDeVideo] = medir_mp4,
) -> LoteInspecionado:
    """Expande um ZIP com orçamento agregado e recusa fechada do container.

    Levanta `ArchiveMalicioso` quando o CONTAINER ataca; devolve lote com
    entradas recusadas quando é só conteúdo que não serve.
    """
    comprimido = len(dados_do_zip)
    if comprimido > limites.comprimido_bytes_max:
        raise ArchiveMalicioso(
            ARCHIVE_COMPRIMIDO_GRANDE_DEMAIS,
            f"{comprimido} bytes acima de {limites.comprimido_bytes_max}",
        )

    try:
        zf = zipfile.ZipFile(io.BytesIO(dados_do_zip))
    except (zipfile.BadZipFile, OSError) as e:
        raise ArchiveMalicioso(ARCHIVE_ILEGIVEL, "arquivo não é um ZIP legível") from e

    with zf:
        # ⚠️ `infolist()` lê o DIRETÓRIO CENTRAL, não o conteúdo. Todas as
        # decisões abaixo saem daí, antes de um único byte ser descomprimido.
        infos = [zi for zi in zf.infolist() if not zi.is_dir()]
        if not infos:
            raise ArchiveMalicioso(ARCHIVE_VAZIO, "o ZIP não tem arquivo dentro")
        if len(infos) > limites.entradas_max:
            raise ArchiveMalicioso(
                ARCHIVE_ENTRADAS_DEMAIS,
                f"{len(infos)} entradas acima de {limites.entradas_max}",
            )

        declarado = sum(int(zi.file_size or 0) for zi in infos)
        if declarado > limites.expandido_bytes_max:
            raise ArchiveMalicioso(
                ARCHIVE_EXPANSAO_GRANDE_DEMAIS,
                f"o diretório central declara {declarado} bytes, acima de "
                f"{limites.expandido_bytes_max}",
            )
        if comprimido > 0 and declarado > comprimido * limites.razao_de_expansao_max:
            raise ArchiveMalicioso(
                ARCHIVE_RAZAO_DE_EXPANSAO,
                f"o diretório central declara razão "
                f"{declarado // max(comprimido, 1)}:1, acima de "
                f"{limites.razao_de_expansao_max}:1",
            )

        vistos: set[str] = set()
        for zi in infos:
            _conferir_estrutura_da_entrada(zi, vistos)

        # Só agora se descomprime. E mesmo agora, com orçamento: o diretório
        # central é declaração de quem montou o ZIP, e uma declaração pode
        # mentir. `zipfile` corta a saída no `file_size` declarado, mas depender
        # disso amarraria a defesa ao detalhe de implementação da stdlib.
        orcamento = Orcamento(
            expandido_max=limites.expandido_bytes_max,
            comprimido=comprimido,
            razao_max=limites.razao_de_expansao_max,
        )
        conteudos: list[tuple[str, bytes]] = []
        for zi in infos:
            try:
                with zf.open(zi, "r") as fluxo:
                    pedacos: list[bytes] = []
                    while True:
                        bloco = fluxo.read(_BLOCO)
                        if not bloco:
                            break
                        orcamento.cobrar(len(bloco))
                        pedacos.append(bloco)
            except (zipfile.BadZipFile, OSError, EOFError) as e:
                # ⚠️ CRC que nao bate, entrada truncada, metodo de compressao que
                # a stdlib nao tem. Sem este `except`, um ZIP com o tamanho
                # descomprimido ADULTERADO (medido: a stdlib corta na mentira e
                # depois levanta `Bad CRC-32`) subia como excecao nao tratada e
                # a rota respondia 500 — o servidor se acusando de um defeito do
                # arquivo que alguem mandou.
                raise ArchiveMalicioso(
                    ARCHIVE_ILEGIVEL,
                    f"entrada ilegivel: {nome_seguro(zi.filename)}",
                ) from e
            bruto = b"".join(pedacos)
            aninhado = tipo_de_archive(bruto)
            if aninhado is not None:
                # Archive dentro de archive: cada camada respeita o limite da
                # camada de cima e o produto final não respeita nenhum.
                raise ArchiveMalicioso(
                    ARCHIVE_ANINHADO,
                    f"entrada {nome_seguro(zi.filename)} é um archive "
                    f"({aninhado}) dentro do ZIP",
                )
            conteudos.append((zi.filename, bruto))

    entradas = tuple(
        inspecionar_bytes(i, nome, bruto, limites=limites,
                          decodificador=decodificador,
                          medidor_de_video=medidor_de_video)
        for i, (nome, bruto) in enumerate(conteudos)
    )
    return LoteInspecionado(
        origem=ORIGEM_ZIP,
        nome_arquivo_original=nome_seguro(nome_arquivo) if nome_arquivo else None,
        bytes_comprimidos=comprimido,
        entradas=entradas,
    )


def lote_recusado(
    origem: str, nome_arquivo: str | None, bytes_comprimidos: int | None,
    erro: ArchiveMalicioso,
) -> LoteInspecionado:
    """O lote que não sobreviveu ao container, em forma persistível.

    ⚠️ Ele existe porque recusar em silêncio é pior que recusar: o operador
    precisa saber que subiu algo, o que foi encontrado, e que nada entrou.
    """
    return LoteInspecionado(
        origem=origem,
        nome_arquivo_original=nome_seguro(nome_arquivo) if nome_arquivo else None,
        bytes_comprimidos=bytes_comprimidos,
        motivo_recusa=erro.codigo,
        detalhe=str(erro),
    )
