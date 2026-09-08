"""O compositor determinístico: onde a fotografia real entra nos pixels finais.

## A promessa que este arquivo existe para tornar verdadeira

"A fotografia entra na peça sem ser regerada."

Ela não é verdadeira no endpoint de edição do provider. `POST /v1/images/edits`
recebe a imagem como REFERÊNCIA e devolve uma imagem nova, inteira, redesenhada:
o rosto muda, o logotipo muda, o texto da camiseta muda. Chamar isso de
"preservar a foto" é a frase mais fácil de escrever e a mais cara de descobrir,
porque o operador só vê a diferença depois de pagar.

Aqui os pixels da fotografia são COLADOS. O modelo produz o entorno — fundo,
clima, área livre para texto — e este módulo junta os dois com aritmética, sem
provider no meio. É por isso que ele é determinístico: mesma foto, mesmo fundo,
mesmo formato, mesmos bytes, em qualquer máquina.

## Por que a caixa da foto é dado e não improviso

`REGIOES` declara, por proporção, onde a fotografia vive e onde o texto pode
viver. Um recorte "inteligente" por saliência erraria de formas diferentes a
cada execução e tornaria impossível responder "por que esta peça saiu assim?".
A caixa fixa é pior na média e melhor no que importa: ela é reproduzível, é
auditável e cabe num recibo.

Cada região é declarada em FRAÇÕES do canvas final, e não em pixels, porque o
mesmo layout precisa servir 1080x1080 e 1200x628 sem uma tabela por dimensão.

## O que vai para o recibo, e por que cada campo

Sem `crop`, `escala` e `posicao` gravados, "esta peça foi composta ou recortada
de outra?" não tem resposta — e era exatamente essa a lacuna: o único registro
existente era um rótulo fechado de cinco valores em `criativo_rendition.
enquadramento`, sem lugar para a caixa.

`compositor` e `compositor_versao` viajam junto porque mudar a régua muda a
peça: duas execuções do mesmo pedido em versões diferentes produzem bytes
diferentes, e sem a versão gravada a diferença vira mistério.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field

#: Quem compôs. Vira `criativo_rendition.compositor`.
COMPOSITOR = "volc-hibrido"

#: A régua. Mudar qualquer número de `REGIOES` ou a ordem das operações abaixo
#: EXIGE subir esta versão: ela é o que explica por que a mesma entrada produziu
#: bytes diferentes em duas datas.
COMPOSITOR_VERSAO = "1.0.0"


@dataclass(frozen=True)
class Regiao:
    """Uma caixa em frações do canvas final. `(0,0)` é o canto superior esquerdo."""

    x: float
    y: float
    largura: float
    altura: float

    def em_pixels(self, largura: int, altura: int) -> tuple[int, int, int, int]:
        esquerda = int(round(self.x * largura))
        topo = int(round(self.y * altura))
        direita = int(round((self.x + self.largura) * largura))
        base = int(round((self.y + self.altura) * altura))
        # Pelo menos um pixel: uma caixa de altura zero produziria um `crop`
        # vazio e um `paste` silenciosamente inócuo.
        return esquerda, topo, max(direita, esquerda + 1), max(base, topo + 1)


@dataclass(frozen=True)
class Layout:
    """Onde a foto vive e onde o texto pode viver, para uma proporção."""

    foto: Regiao
    texto: Regiao
    descricao: str


#: O layout por SLOT. Fechado e explícito.
#:
#: A escolha de cada um segue a mesma regra: a fotografia ocupa o bloco que o
#: olho encontra primeiro na proporção, e a área de texto fica no espaço que
#: sobra, longe das margens que as plataformas cobrem com interface.
REGIOES: dict[str, Layout] = {
    "1x1": Layout(
        foto=Regiao(0.0, 0.0, 1.0, 0.62),
        texto=Regiao(0.08, 0.66, 0.84, 0.26),
        descricao="Foto no topo, texto na faixa inferior.",
    ),
    "4x5": Layout(
        foto=Regiao(0.0, 0.0, 1.0, 0.64),
        texto=Regiao(0.08, 0.68, 0.84, 0.24),
        descricao="Foto no topo, texto na faixa inferior.",
    ),
    "9x16": Layout(
        # Mais alto e centralizado na vertical: em stories, as faixas superior e
        # inferior somem debaixo da interface do aplicativo.
        foto=Regiao(0.0, 0.10, 1.0, 0.58),
        texto=Regiao(0.08, 0.70, 0.84, 0.18),
        descricao="Foto no meio, fora das faixas cobertas pela interface.",
    ),
    "1.91x1": Layout(
        # Paisagem curta: dividir na horizontal preserva mais da fotografia que
        # uma faixa de 30% de altura.
        foto=Regiao(0.0, 0.0, 0.48, 1.0),
        texto=Regiao(0.53, 0.18, 0.40, 0.64),
        descricao="Foto à esquerda, texto à direita.",
    ),
}

#: Usado quando o slot não tem layout declarado. Não é chute: é a mesma divisão
#: do 1x1, que é a proporção mais neutra, e o rótulo diz que foi ela.
LAYOUT_PADRAO = REGIOES["1x1"]


class ComposicaoIndisponivel(RuntimeError):
    """Falta Pillow. O chamador decide entre falhar ou seguir sem composição."""


@dataclass(frozen=True)
class Composta:
    """Os bytes finais e a história completa de como a foto entrou neles."""

    conteudo: bytes
    mime: str
    largura: int
    altura: int
    #: A caixa recortada da FOTO ORIGINAL, em pixels dela: (x, y, l, a).
    crop: tuple[int, int, int, int]
    #: O fator aplicado à foto para cobrir a região.
    escala: float
    #: Onde a região da foto começa no canvas final, em pixels: (x, y).
    posicao: tuple[int, int]
    #: A região da foto no canvas final, em pixels: (x, y, l, a).
    regiao: tuple[int, int, int, int]
    compositor: str = COMPOSITOR
    compositor_versao: str = COMPOSITOR_VERSAO
    transformacoes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.conteudo).hexdigest()


def layout_de(slot: str) -> Layout:
    return REGIOES.get(slot, LAYOUT_PADRAO)


def _pillow():
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - ambiente sem Pillow
        raise ComposicaoIndisponivel(
            "composição híbrida exige Pillow, que não está disponível"
        ) from e
    return Image


def compor(
    *,
    fundo: bytes,
    foto: bytes,
    slot: str,
    largura: int,
    altura: int,
) -> Composta:
    """Cola a fotografia real sobre o fundo gerado, na região do slot.

    O `fundo` já chega na medida final (é a saída de `enquadramento.enquadrar`).
    A `foto` chega normalizada (é a saída de `studio/anexo.normalizar`).

    As operações, nesta ordem exata — trocá-la muda os bytes e exige subir
    `COMPOSITOR_VERSAO`:

      1. a região da foto é convertida de frações para pixels do canvas final;
      2. a foto é escalada por `cover`: o fator é o MAIOR entre os dois
         necessários, de modo que ela cubra a região inteira sem deformar;
      3. o excedente é recortado do CENTRO, e a caixa recortada é registrada em
         coordenadas da foto original;
      4. o resultado é colado na região;
      5. o arquivo sai em PNG.

    PNG e não JPEG: o hash do conteúdo é a identidade do asset, e um
    recodificador com perdas faria o mesmo pedido produzir bytes diferentes
    conforme a versão da libjpeg. É a mesma escolha de `enquadramento.py`, e as
    duas precisam concordar.
    """
    if largura <= 0 or altura <= 0:
        raise ValueError(f"medida final não positiva: {largura}x{altura}")

    Image = _pillow()
    layout = layout_de(slot)
    esquerda, topo, direita, base = layout.foto.em_pixels(largura, altura)
    regiao_l = direita - esquerda
    regiao_a = base - topo

    with Image.open(io.BytesIO(fundo)) as base_img, Image.open(io.BytesIO(foto)) as foto_img:
        base_img.load()
        foto_img.load()
        tela = base_img.convert("RGB")
        if tela.size != (largura, altura):
            # O fundo deveria chegar na medida; se não chegou, ajustar aqui é
            # melhor que compor sobre um canvas de outro tamanho e produzir uma
            # peça fora da dimensão pedida sem ninguém notar.
            tela = tela.resize((largura, altura), Image.LANCZOS)

        origem = foto_img.convert("RGB")
        foto_l, foto_a = origem.size

        # (2) `cover`: o maior dos dois fatores. O menor deixaria borda vazia.
        escala = max(regiao_l / foto_l, regiao_a / foto_a)
        inter_l = max(regiao_l, int(round(foto_l * escala)))
        inter_a = max(regiao_a, int(round(foto_a * escala)))
        redimensionada = origem.resize((inter_l, inter_a), Image.LANCZOS)

        # (3) recorte centralizado, registrado em coordenadas da FOTO ORIGINAL,
        #     que é o sistema em que a pergunta "que pedaço da minha foto foi
        #     usado?" faz sentido.
        corte_x = (inter_l - regiao_l) // 2
        corte_y = (inter_a - regiao_a) // 2
        recortada = redimensionada.crop(
            (corte_x, corte_y, corte_x + regiao_l, corte_y + regiao_a)
        )
        crop_na_origem = (
            int(round(corte_x / escala)),
            int(round(corte_y / escala)),
            int(round(regiao_l / escala)),
            int(round(regiao_a / escala)),
        )

        tela.paste(recortada, (esquerda, topo))

        saida = io.BytesIO()
        tela.save(saida, format="PNG", optimize=True)
        conteudo = saida.getvalue()

    return Composta(
        conteudo=conteudo,
        mime="image/png",
        largura=largura,
        altura=altura,
        crop=crop_na_origem,
        escala=round(escala, 6),
        posicao=(esquerda, topo),
        regiao=(esquerda, topo, regiao_l, regiao_a),
        transformacoes=(
            f"regiao {slot} {esquerda},{topo} {regiao_l}x{regiao_a}",
            f"cover {foto_l}x{foto_a}->{inter_l}x{inter_a}",
            f"crop centralizado ->{regiao_l}x{regiao_a}",
            "paste sobre fundo gerado",
        ),
    )


def instrucao_de_fundo(slot: str) -> str:
    """O que dizer ao modelo para que o fundo receba a foto sem brigar com ela.

    O modelo NÃO recebe a fotografia neste modo. Mandá-la como referência faria
    ele desenhar uma pessoa parecida, e a peça final teria duas — a desenhada e
    a colada. O que ele recebe é a instrução de deixar a região vazia.
    """
    layout = layout_de(slot)
    foto = layout.foto
    return (
        "Esta arte recebe uma fotografia real depois da geração. "
        f"Deixe a região que vai de {foto.x:.0%} a {(foto.x + foto.largura):.0%} da "
        f"largura e de {foto.y:.0%} a {(foto.y + foto.altura):.0%} da altura como "
        "fundo liso e contínuo, sem pessoas, sem objetos em primeiro plano e sem "
        "elementos que precisem ficar visíveis. "
        f"{layout.descricao} "
        "Concentre a composição fora dessa região."
    )
