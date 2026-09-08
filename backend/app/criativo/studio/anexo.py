"""A fotografia real que o operador anexa — validada nos BYTES, nunca no rótulo.

## O que este módulo recusa, e por que cada recusa existe

Um upload de imagem que chega de um browser é a superfície mais barata de
atacar num produto que depois passa esses bytes para um decodificador, para um
compositor e para um provider pago. As sete recusas abaixo não são zelo: cada
uma corresponde a uma classe de defeito com nome próprio.

  `MIME declarado ≠ MIME dos bytes`
      O `Content-Type` do multipart é escrito pelo cliente. Confiar nele grava
      um executável sob extensão `.png` dentro do diretório que a rota de
      preview serve. A assinatura de bytes é a única fonte.

  `formato fora da allowlist`
      Denylist não fecha: o conjunto de coisas perigosas é aberto. O provider
      aceita PNG, JPEG e WebP, e é essa a lista.

  `arquivo grande demais`
      Antes do decodificador, porque conferir o resto de um payload de 900 MB já
      significa tê-lo carregado.

  `área de pixels grande demais`
      É a decompression bomb. Um PNG de 40 KB pode declarar 30000x30000 no
      cabeçalho; o arquivo passa em qualquer teto de BYTES e explode em ~3,6 GB
      quando alguém chama `.convert()`. O teto que importa é o de PIXELS, e ele
      é conferido no cabeçalho ANTES de decodificar.

  `arquivo truncado`
      Um JPEG cortado pela metade decodifica "com sucesso" no Pillow e produz
      metade cinza. Uma peça paga composta sobre metade cinza é pior que uma
      recusa.

  `dimensão mínima`
      Uma foto de 60x40 esticada para 1080x1350 é lixo com procedência. Recusar
      cedo é mais barato que gerar e descartar.

  `dono diferente`
      Confinamento por operação: um `asset_ref` é uma referência opaca, mas
      referência opaca não é autorização. Quem lê confere o dono.

## O que sai daqui

Bytes NORMALIZADOS, não os bytes que chegaram. O EXIF é removido e a orientação
é aplicada aos pixels, nessa ordem — as duas coisas juntas, porque aplicar a
orientação sem remover o EXIF gira a imagem duas vezes na próxima biblioteca que
respeitar a tag, e remover sem aplicar entrega a foto deitada.

O EXIF de uma foto de celular carrega GPS, número de série do aparelho e, com
frequência, o nome de quem tirou. Nada disso precisa existir num arquivo que vai
para um provider externo, e a hora de tirar é aqui.

⚠️ O `content_sha256` publicado é o dos bytes NORMALIZADOS, porque é sobre eles
que a autorização de gasto é assinada e é eles que o compositor usa. Publicar o
hash do arquivo original faria a autorização cobrir bytes que ninguém processa.
"""

from __future__ import annotations

import hashlib
import io
import re
import secrets
from dataclasses import dataclass

from app.criativo.importacao import detectar_mime

#: O que o `gpt-image-2` aceita como imagem de entrada, e o que o compositor
#: sabe abrir. As duas listas coincidem; se um dia divergirem, a interseção é
#: que vale, e o lugar de escrever isso é aqui.
MIMES_ACEITOS: frozenset[str] = frozenset({"image/png", "image/jpeg", "image/webp"})

#: 25 MB. Uma foto de celular moderna dá 3 a 8 MB; 25 MB é folga de uma ordem de
#: grandeza e ainda barra um upload que só pode ser engano ou ataque.
TETO_DE_BYTES = 25 * 1024 * 1024

#: 50 megapixels. Uma câmera de 48 MP cabe; 30000x30000 (900 MP, ~3,6 GB
#: descomprimidos) não. É o teto que barra a decompression bomb, e ele é
#: conferido no CABEÇALHO, antes de qualquer decodificação.
TETO_DE_PIXELS = 50_000_000

#: Abaixo disto a foto não sustenta nenhum dos formatos do catálogo.
LADO_MINIMO = 320

_EXTENSAO_POR_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

_REF_VALIDA = re.compile(r"^crimg_[a-f0-9]{24}$")


class AnexoRecusado(ValueError):
    """Upload que não passa na política. Vira 400, nunca 500.

    A mensagem é escrita para o operador e não cita caminho de disco, nome de
    biblioteca nem traceback: ela é renderizada na tela.
    """


@dataclass(frozen=True)
class AnexoNormalizado:
    """O que sobra depois da política: bytes limpos e a identidade deles."""

    ref: str
    conteudo: bytes
    mime: str
    largura: int
    altura: int
    content_sha256: str
    bytes_originais: int
    exif_removido: bool
    orientacao_aplicada: bool

    @property
    def extensao(self) -> str:
        return _EXTENSAO_POR_MIME[self.mime]


def nova_ref() -> str:
    """Uma referência opaca, sorteada, sem relação com dono nem com conteúdo.

    Sorteada e não derivada do hash de propósito: uma ref derivada do conteúdo
    permitiria a quem tem a foto descobrir se ela já existe no sistema de outra
    pessoa, o que é um oráculo de existência de graça.
    """
    return "crimg_" + secrets.token_hex(12)


def ref_valida(ref: str) -> bool:
    return bool(_REF_VALIDA.match(ref or ""))


def _pillow():
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - ambiente sem Pillow
        raise AnexoRecusado(
            "Este servidor não consegue processar imagens agora."
        ) from e
    return Image


def normalizar(dados: bytes, *, mime_declarado: str | None = None) -> AnexoNormalizado:
    """A política inteira, em ordem de custo crescente.

    Cada passo só roda depois que o anterior passou, e a ordem é a ordem do
    preço: bytes, assinatura, cabeçalho, decodificação. Trocá-la significaria
    decodificar para descobrir que o arquivo era grande demais.
    """
    if not dados:
        raise AnexoRecusado("O arquivo chegou vazio.")
    if len(dados) > TETO_DE_BYTES:
        raise AnexoRecusado(
            f"A imagem passa do limite de {TETO_DE_BYTES // (1024 * 1024)} MB."
        )

    real = detectar_mime(dados)
    if real is None:
        raise AnexoRecusado("Não foi possível reconhecer este arquivo como imagem.")
    if real not in MIMES_ACEITOS:
        raise AnexoRecusado(
            "Envie a imagem em PNG, JPEG ou WebP; este formato não é aceito."
        )
    # O rótulo do cliente só é conferido CONTRA os bytes; ele nunca decide.
    if mime_declarado and mime_declarado.split(";")[0].strip().lower() != real:
        raise AnexoRecusado("O conteúdo do arquivo não corresponde ao tipo declarado.")

    Image = _pillow()
    # ⚠️ A guarda embutida do Pillow (`DecompressionBombError`) tem teto próprio
    # e é global do processo. Confiar nela faria a política deste produto
    # depender de uma configuração de biblioteca que ninguém declara. O teto
    # daqui é explícito e é conferido no CABEÇALHO, que `Image.open` lê sem
    # decodificar os pixels.
    try:
        with Image.open(io.BytesIO(dados)) as cabecalho:
            largura, altura = cabecalho.size
    except Exception as e:  # noqa: BLE001 — qualquer falha de abertura é recusa
        raise AnexoRecusado("Este arquivo de imagem parece corrompido.") from e

    if largura * altura > TETO_DE_PIXELS:
        raise AnexoRecusado(
            f"A imagem tem {largura}x{altura} pixels, acima do limite que este "
            "servidor processa."
        )
    if min(largura, altura) < LADO_MINIMO:
        raise AnexoRecusado(
            f"A imagem precisa ter pelo menos {LADO_MINIMO} pixels no menor lado; "
            f"esta tem {min(largura, altura)}."
        )

    try:
        with Image.open(io.BytesIO(dados)) as img:
            # `load()` força a decodificação COMPLETA. Sem ele, um JPEG truncado
            # atravessa a validação e só quebra — ou pior, sai metade cinza —
            # dentro do compositor, depois de o provider já ter sido pago.
            img.load()
            tinha_exif = bool(img.getexif())
            from PIL import ImageOps  # noqa: PLC0415

            # `exif_transpose` aplica a orientação AOS PIXELS e remove a tag.
            # Fazer só um dos dois gira a foto duas vezes na próxima biblioteca
            # que respeitar a tag, ou entrega a foto deitada.
            reto = ImageOps.exif_transpose(img)
            orientou = reto.size != img.size or tinha_exif
            reto = reto.convert("RGBA" if real == "image/png" else "RGB")

            saida = io.BytesIO()
            if real == "image/png":
                reto.save(saida, format="PNG", optimize=True)
            elif real == "image/webp":
                reto.save(saida, format="WEBP", quality=95, method=4)
            else:
                reto.save(saida, format="JPEG", quality=95, optimize=True)
            limpos = saida.getvalue()
            final_l, final_a = reto.size
    except AnexoRecusado:
        raise
    except Exception as e:  # noqa: BLE001
        raise AnexoRecusado("Não foi possível preparar esta imagem.") from e

    return AnexoNormalizado(
        ref=nova_ref(),
        conteudo=limpos,
        mime=real,
        largura=final_l,
        altura=final_a,
        content_sha256=hashlib.sha256(limpos).hexdigest(),
        bytes_originais=len(dados),
        exif_removido=tinha_exif,
        orientacao_aplicada=orientou,
    )


def chave_de_anexo(dono_id: str, ref: str, extensao: str) -> str:
    """Onde o anexo mora, com o DONO no primeiro nível.

    O dono entra na chave para que uma policy de bucket por prefixo consiga
    existir no dia em que o adaptador remoto for ligado. Uma chave sem dono
    obriga toda autorização a ser feita na aplicação, e uma autorização que só
    existe na aplicação é a que some quando alguém acrescenta uma rota nova.

    ⚠️ A conferência de posse NÃO é a chave. Ela é feita na leitura, contra a
    coluna de dono. A chave é defesa em profundidade, não a porta.
    """
    limpo = re.sub(r"[^a-z0-9-]", "", (dono_id or "").lower())[:64] or "sem-dono"
    if not ref_valida(ref):
        raise AnexoRecusado("referência de anexo inválida")
    return f"criativos/anexos/{limpo}/{ref}.{extensao.lstrip('.')}"
