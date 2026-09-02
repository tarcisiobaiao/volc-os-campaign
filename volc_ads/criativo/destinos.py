"""Os envelopes por destino — e a medição que separa recompor de recortar.

## O buraco que este módulo fecha

`requisitos.yaml` sabe o que o **canal do Google Ads** exige de um arquivo, e
`criativo_ponte.Destino` sabe se um asset pode subir para uma conta real. Nenhum
dos dois responde a pergunta que uma peça multiformato faz primeiro: **quais
envelopes existem, por destino**, e qual deles esta peça está cumprindo.

Sem esse catálogo, "adaptação multidestino" vira o que ela costuma ser na
prática: o mesmo PNG recortado quatro vezes, entregue com quatro nomes de
arquivo diferentes. As quatro dimensões batem, os quatro gates passam, e a
composição é uma só — a do formato original, com as outras três mutiladas nas
bordas.

## Por que a classificação é MEDIDA e não declarada

Um campo `adaptacao="recomposicao"` preenchido por quem gerou a peça é uma
afirmação sobre o próprio trabalho, e o custo de errá-la é zero. Por isso
`classificar_adaptacao()` não aceita rótulo: ela recebe os **bytes** do mestre e
os da variante e devolve um veredito com os números que o sustentam.

O discriminante é físico. Este motor compõe com exatamente duas cores (fundo e
tinta), e o antialias do desenho é uma mistura **convexa** das duas: todo pixel
cai no segmento fundo→tinta, com `t` entre 0 e 1. Uma reamostragem LANCZOS —
que é o que `services/creative_engine/enquadramento.enquadrar` faz num
`cover_crop` — tem lóbulos negativos e produz *overshoot*: pixels na mesma reta,
mas com `t < 0` ou `t > 1`. Medido em 01/09/2026 sobre a peça do golden:

    recomposto  1:1     fora_da_rampa =     0   cores =  254
    recomposto  4:5     fora_da_rampa =     0   cores =  254
    recomposto  9:16    fora_da_rampa =     0   cores =  254
    recorte     4:5     fora_da_rampa =  8525   cores = 2076
    recorte    1.91:1   fora_da_rampa =  7221   cores = 1965
    recorte     9:16    fora_da_rampa = 12460   cores = 2289

## A fronteira, dita antes de alguém descobrir na marra

O discriminante acima só vale enquanto o MESTRE for de duas cores. Numa peça
fotográfica a nuvem de cores não fica sobre reta nenhuma, e overshoot deixa de
ser assinatura de nada. Nesse caso a função devolve `INDETERMINADO` — nunca
`RECOMPOSICAO` por omissão. Não medir não é aprovar.

O mesmo vale para um `resize` por vizinho mais próximo: ele não gera overshoot,
e este medidor o chamaria de recomposição. É por isso que `Adaptacao.evidencia`
carrega também a caixa da tinta e as faixas: quem lê o veredito tem os números
para discordar dele.

## Por que este módulo pode depender de Pillow, e `medir_imagem.py` não

`medir_imagem.py` está no caminho de PRODUÇÃO: sem ele nenhum asset é medido, e
uma dependência não declarada ali faria toda a validação de geometria ficar
inerte em silêncio. Este módulo é **diagnóstico**: o catálogo de envelopes e a
montagem de pacotes são stdlib pura, e só a leitura de pixel precisa de Pillow.
Quando ele falta, `perfilar()` levanta `MedicaoDePixelsIndisponivel` — recusa
nomeada, e não um perfil vazio que o chamador leria como "sem diferença".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .contrato import NaturezaDaProcedencia, TipoDeAsset

# ─────────────────────────────────────────────────────────────────────────────
# Os destinos
# ─────────────────────────────────────────────────────────────────────────────

#: Google Ads — Display e Demand Gen. Publicação por API, conta real.
GOOGLE = "google"
#: Meta — Feed, Explorar e Stories/Reels. Publicação por API, conta real.
META = "meta"
#: Orgânico — o que sai pela mão de quem publica, sem API de anúncio no meio.
ORGANICO = "organico"

DESTINOS: tuple[str, ...] = (GOOGLE, META, ORGANICO)


class DestinoDesconhecido(ValueError):
    """Erro próprio para que a rota distinga pedido inválido de defeito nosso."""

    def __init__(self, destino: str) -> None:
        super().__init__(
            f"destino {destino!r} não existe. Conhecidos: {', '.join(DESTINOS)}"
        )
        self.destino = destino


# ─────────────────────────────────────────────────────────────────────────────
# O envelope
# ─────────────────────────────────────────────────────────────────────────────


def _valor_da_proporcao(rotulo: str) -> float:
    esquerda, direita = rotulo.split(":")
    return float(esquerda) / float(direita)


@dataclass(frozen=True)
class Envelope:
    """Uma medida que um destino aceita, com a fonte do número junto.

    ⚠️ `proporcao` é o rótulo que a especificação da plataforma usa — `1.91:1`,
    e não `21:11`, que é como a matemática reduz `1200/628`. Ele é DADO e não
    derivado porque é vocabulário da indústria; para não virar decoração, o
    `__post_init__` confere o rótulo contra as dimensões e recusa a divergência.
    Um rótulo que ninguém confere é a forma mais barata de mentir sobre formato.
    """

    slug: str
    destino: str
    superficie: str
    tipo: TipoDeAsset
    largura: int
    altura: int
    proporcao: str
    fonte: str

    #: Folga do rótulo contra a medida. Meio por cento é a mesma tolerância que
    #: `enquadramento.rotulo_de_proporcao` usa para escolher rótulo canônico.
    #: `ClassVar` e não campo: é constante do tipo, não dado de instância.
    TOLERANCIA: ClassVar[float] = 0.005

    def __post_init__(self) -> None:
        if self.destino not in DESTINOS:
            raise DestinoDesconhecido(self.destino)
        if self.largura <= 0 or self.altura <= 0:
            raise ValueError(
                f"{self.slug}: {self.largura}x{self.altura} — dimensão ausente é "
                f"recusa, nunca zero"
            )
        if not self.fonte.strip():
            raise ValueError(
                f"{self.slug}: envelope sem fonte. De onde saiu este número?"
            )
        exata = self.largura / self.altura
        try:
            declarada = _valor_da_proporcao(self.proporcao)
        except (ValueError, ZeroDivisionError):
            raise ValueError(
                f"{self.slug}: proporção {self.proporcao!r} não é um rótulo "
                f"`a:b` legível"
            ) from None
        if abs(declarada - exata) / exata > self.TOLERANCIA:
            raise ValueError(
                f"{self.slug}: rótulo {self.proporcao!r} ({declarada:.4f}) não "
                f"descreve {self.largura}x{self.altura} ({exata:.4f})"
            )

    @property
    def slot(self) -> str:
        """O `<ordem>-<tipo>` que a bancada usa como nome de slot.

        A ordem sai do índice no catálogo para que dois envelopes do mesmo tipo
        — 1:1 do Meta e 1:1 do Google, por exemplo — não colidam num arquivo só.
        Ver `bancada/servico._saidas_da_receita`, que já paga esse preço.
        """
        return f"{ENVELOPES.index(self)}-{self.tipo.value}"


#: Os cinco envelopes que a fatia P17-T08 exige: quatro proporções de peça mais
#: o logo que o Demand Gen exige para o lote existir.
#:
#: ⚠️ São medidas de PEÇA, não mínimos de API. O Display aceita 1.91:1 a partir
#: de 600x314; 1200x628 é o tamanho que a própria especificação recomenda, e é o
#: que faz a mesma peça servir também ao Meta em link ads. Onde a plataforma
#: recomenda, a recomendação ganha; onde ela só declara mínimo, o mínimo entra
#: com a fonte dizendo isso.
ENVELOPES: tuple[Envelope, ...] = (
    Envelope(
        slug="meta-feed-1x1",
        destino=META,
        superficie="Feed e Explorar",
        tipo=TipoDeAsset.IMAGEM_MARKETING_QUADRADA,
        largura=1080,
        altura=1080,
        proporcao="1:1",
        fonte="Meta Ads Guide, imagem de feed 1:1 recomendada 1080x1080",
    ),
    Envelope(
        slug="meta-feed-4x5",
        destino=META,
        superficie="Feed vertical",
        tipo=TipoDeAsset.IMAGEM_MARKETING_RETRATO,
        largura=1080,
        altura=1350,
        proporcao="4:5",
        fonte="Meta Ads Guide, imagem de feed 4:5 recomendada 1080x1350",
    ),
    Envelope(
        slug="google-display-191x1",
        destino=GOOGLE,
        superficie="Display e Demand Gen",
        tipo=TipoDeAsset.IMAGEM_MARKETING,
        largura=1200,
        altura=628,
        proporcao="1.91:1",
        fonte="Google Ads, marketing image 1.91:1 recomendada 1200x628",
    ),
    Envelope(
        slug="google-logo-1x1",
        destino=GOOGLE,
        superficie="Demand Gen — logo",
        tipo=TipoDeAsset.LOGO_QUADRADO,
        largura=1200,
        altura=1200,
        proporcao="1:1",
        fonte="Google Ads, logo quadrado 1:1 recomendado 1200x1200 "
               "(mínimo 144x144 pelo Help Center, que também satisfaz os "
               "128x128 do proto). ⚠️ A primeira versão citava 128x128 como "
               "mínimo; `requisitos.yaml:185` é a fonte deste repositório e "
               "diz 144x144.",
    ),
    Envelope(
        slug="organico-reels-9x16",
        destino=ORGANICO,
        superficie="Stories e Reels",
        tipo=TipoDeAsset.IMAGEM_MARKETING_RETRATO_ALTO,
        largura=1080,
        altura=1920,
        proporcao="9:16",
        fonte="Meta e YouTube Shorts, tela cheia 9:16 recomendada 1080x1920",
    ),
    # ⚠️ ACRESCENTADO NO FIM, e a posicao importa: `Envelope.slot` deriva de
    # `ENVELOPES.index(self)`. Inserir no meio renumeraria os slots dos
    # envelopes existentes, e um slot renumerado e um arquivo com outro nome —
    # goldens congelados e chaves de armazenamento ja gravadas deixariam de
    # casar sem que nada acusasse.
    #
    # Este e o PRIMEIRO envelope de video do catalogo. `TipoDeAsset.VIDEO` ja
    # existia no enum desde a v11 e nao tinha nenhum envelope: o tipo estava
    # declarado e o formato, nao. Enquanto isso, uma peca de video nao tinha
    # destino contra o qual ser validada — e "validacao por destino" de video
    # respondia sempre `nao_avaliado`, por ausencia de alvo e nao por decisao.
    Envelope(
        slug="organico-reels-video-9x16",
        destino=ORGANICO,
        superficie="Reels e Shorts — video",
        tipo=TipoDeAsset.VIDEO,
        largura=1080,
        altura=1920,
        proporcao="9:16",
        fonte=(
            "Meta Reels e YouTube Shorts, video vertical de tela cheia 9:16 "
            "recomendado 1080x1920. Mesma geometria do envelope de imagem "
            "`organico-reels-9x16`, e envelope SEPARADO de proposito: a "
            "superficie aceita as duas midias e um pacote precisa saber qual "
            "das duas falta."
        ),
    ),
)

_POR_SLUG: dict[str, Envelope] = {e.slug: e for e in ENVELOPES}


#: Os envelopes por MIDIA. Existem porque geometria igual nao basta para decidir
#: o que preenche o que: `organico-reels-9x16` e `organico-reels-video-9x16` tem
#: os mesmos 1080x1920, e um consumidor que itere `ENVELOPES` sem filtrar produz
#: um PNG "cumprindo" o envelope de video — que nenhum destino aceita.
#:
#: ⚠️ Isto foi medido, nao imaginado: quando o envelope de video entrou no
#: catalogo, a travessia golden de imagem passou a gerar uma peca a mais e a
#: catalogar o MESMO conteudo sob dois papeis. O defeito era da iteracao sem
#: filtro e ja existia; o envelope novo so o tornou visivel.
ENVELOPES_DE_VIDEO: tuple[Envelope, ...] = tuple(
    e for e in ENVELOPES if e.tipo is TipoDeAsset.VIDEO
)
ENVELOPES_DE_IMAGEM: tuple[Envelope, ...] = tuple(
    e for e in ENVELOPES if e.tipo is not TipoDeAsset.VIDEO
)


class EnvelopeDesconhecido(KeyError):
    def __init__(self, slug: str) -> None:
        super().__init__(
            f"envelope {slug!r} não existe. Conhecidos: "
            f"{', '.join(sorted(_POR_SLUG))}"
        )
        self.slug = slug


def envelope_de(slug: str) -> Envelope:
    try:
        return _POR_SLUG[slug]
    except KeyError:
        raise EnvelopeDesconhecido(slug) from None


def envelopes_de_destino(destino: str) -> tuple[Envelope, ...]:
    if destino not in DESTINOS:
        raise DestinoDesconhecido(destino)
    return tuple(e for e in ENVELOPES if e.destino == destino)


# ─────────────────────────────────────────────────────────────────────────────
# O perfil de pixels
# ─────────────────────────────────────────────────────────────────────────────

#: Os três desfechos que `classificar_adaptacao` sabe distinguir, mais o quarto
#: que ela usa quando NÃO sabe. O quarto existe para que "não medi" nunca seja
#: escrito como "recompus".
IDENTICO = "identico"
RECOMPOSICAO = "recomposicao"
CROP_RESIZE = "crop_resize"
INDETERMINADO = "indeterminado"

#: A peça de origem, que não é adaptação de nada. `classificar_adaptacao` NUNCA
#: devolve este rótulo — ele é do catálogo, para a peça em que não houve
#: comparação. Sem ele, o mestre entraria no pacote como `recomposicao`, e "não
#: comparei" viraria "recompus", que é a mentira que este módulo existe para
#: impedir do lado das variantes.
MESTRE = "mestre"

ADAPTACOES: frozenset[str] = frozenset(
    {MESTRE, IDENTICO, RECOMPOSICAO, CROP_RESIZE, INDETERMINADO}
)

#: Acima disto a imagem não é uma composição de duas cores e o discriminante de
#: overshoot não se aplica. `getcolors` devolvendo `None` significa o mesmo.
TETO_DE_CORES_DE_RAMPA = 4096

#: Quanto um pixel pode fugir da reta fundo→tinta e ainda ser considerado uma
#: mistura das duas. 1.5 em unidade RGB é o arredondamento do PNG, não folga.
TOLERANCIA_DA_RETA = 1.5

#: Quanto `t` pode passar de [0, 1] antes de virar overshoot. 2% cobre o
#: arredondamento de canal; o overshoot do LANCZOS é uma ordem acima disso.
TOLERANCIA_DA_RAMPA = 0.02


class MedicaoDePixelsIndisponivel(RuntimeError):
    """Não deu para ler pixel. Recusa nomeada, nunca um perfil vazio.

    Um perfil zerado seria lido pelo chamador como "nenhuma diferença medida",
    que é exatamente o veredito que este módulo existe para não dar de graça.
    """


def _pillow():
    """Importa Pillow sob demanda, como `enquadramento._pillow` já faz."""
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return None
    return Image


@dataclass(frozen=True)
class PerfilDePixels:
    """O que os pixels revelaram sobre a composição.

    `faixas` são as alturas das bandas horizontais que contêm tinta, de cima
    para baixo. Numa peça tipográfica elas são as linhas de texto, e o tamanho
    delas é o tamanho do glifo: recompor mantém o corpo da fonte que o canvas
    pede; recortar o multiplica pelo fator de cover.
    """

    largura: int
    altura: int
    fundo: tuple[int, int, int]
    tinta: tuple[int, int, int]
    cores_distintas: int | None
    tinta_px: int
    caixa_da_tinta: tuple[int, int, int, int] | None
    faixas: tuple[int, ...]
    fora_da_reta: int
    fora_da_rampa: int

    @property
    def de_duas_cores(self) -> bool:
        """A nuvem inteira cabe no segmento fundo→tinta?

        `cores_distintas is None` quer dizer "passou do teto de cores" — que é
        ausência de medida, e não uma resposta negativa qualquer.
        """
        if self.cores_distintas is None:
            return False
        return self.fora_da_reta == 0 and self.fora_da_rampa == 0

    @property
    def margem_esquerda(self) -> int | None:
        return None if self.caixa_da_tinta is None else self.caixa_da_tinta[0]

    def toca_a_borda(self) -> bool:
        """A tinta encosta em alguma borda? É assim que um recorte se denuncia."""
        if self.caixa_da_tinta is None:
            return False
        x0, y0, x1, y1 = self.caixa_da_tinta
        return x0 <= 0 or y0 <= 0 or x1 >= self.largura - 1 or y1 >= self.altura - 1

    def para_json(self) -> dict[str, Any]:
        return {
            "largura": self.largura,
            "altura": self.altura,
            "fundo": list(self.fundo),
            "tinta": list(self.tinta),
            "cores_distintas": self.cores_distintas,
            "tinta_px": self.tinta_px,
            "caixa_da_tinta": (
                None if self.caixa_da_tinta is None else list(self.caixa_da_tinta)
            ),
            "faixas": list(self.faixas),
            "fora_da_reta": self.fora_da_reta,
            "fora_da_rampa": self.fora_da_rampa,
            "de_duas_cores": self.de_duas_cores,
            "toca_a_borda": self.toca_a_borda(),
        }


def _faixas(projecao_y: list[int]) -> tuple[int, ...]:
    """Alturas das corridas contíguas de linhas com tinta."""
    alturas: list[int] = []
    corrente = 0
    for marcado in projecao_y:
        if marcado:
            corrente += 1
        elif corrente:
            alturas.append(corrente)
            corrente = 0
    if corrente:
        alturas.append(corrente)
    return tuple(alturas)


def perfilar(conteudo: bytes) -> PerfilDePixels:
    """Lê os pixels e devolve o perfil. Levanta quando não consegue ler.

    A contagem por COR (e não por pixel) é o que torna isto barato: uma peça
    1080x1920 tem 2 milhões de pixels e algumas centenas de cores, e o laço em
    Python roda sobre as cores. O resto — caixa, projeção, contagem de tinta —
    sai das primitivas em C do Pillow.
    """
    Image = _pillow()
    if Image is None:
        raise MedicaoDePixelsIndisponivel(
            "Pillow ausente: sem leitura de pixel não há veredito de adaptação"
        )
    import io  # noqa: PLC0415

    from PIL import ImageChops  # noqa: PLC0415

    try:
        with Image.open(io.BytesIO(conteudo)) as aberta:
            img = aberta.convert("RGB")
    except Exception as erro:  # noqa: BLE001 — qualquer decodificação recusada
        raise MedicaoDePixelsIndisponivel(
            f"os bytes não abriram como imagem: {type(erro).__name__}"
        ) from erro

    largura, altura = img.size
    fundo = img.getpixel((0, 0))

    cores = img.getcolors(maxcolors=TETO_DE_CORES_DE_RAMPA)
    if cores is None:
        # Passou do teto: não é composição de duas cores, e dizer o contrário
        # seria inventar. `None` aqui é ausência de contagem, não zero cores.
        distintas: int | None = None
        tinta = fundo
    else:
        distintas = len(cores)
        tinta = max(
            (cor for _, cor in cores),
            key=lambda c: sum((c[i] - fundo[i]) ** 2 for i in range(3)),
        )

    chapado = Image.new("RGB", (largura, altura), fundo)
    mascara = (
        ImageChops.difference(img, chapado)
        .convert("L")
        .point(lambda v: 255 if v else 0)
    )
    tinta_px = mascara.histogram()[255]
    caixa = mascara.getbbox()
    projecao_x, projecao_y = mascara.getprojection()
    faixas = _faixas(list(projecao_y))

    fora_da_reta = 0
    fora_da_rampa = 0
    direcao = [tinta[i] - fundo[i] for i in range(3)]
    norma = sum(d * d for d in direcao)
    if cores is not None and norma > 0:
        for quantos, cor in cores:
            delta = [cor[i] - fundo[i] for i in range(3)]
            t = sum(delta[i] * direcao[i] for i in range(3)) / norma
            resto = sum((delta[i] - t * direcao[i]) ** 2 for i in range(3)) ** 0.5
            if resto > TOLERANCIA_DA_RETA:
                fora_da_reta += quantos
            elif t < -TOLERANCIA_DA_RAMPA or t > 1 + TOLERANCIA_DA_RAMPA:
                fora_da_rampa += quantos

    return PerfilDePixels(
        largura=largura,
        altura=altura,
        fundo=fundo,
        tinta=tinta,
        cores_distintas=distintas,
        tinta_px=tinta_px,
        caixa_da_tinta=caixa,
        faixas=faixas,
        fora_da_reta=fora_da_reta,
        fora_da_rampa=fora_da_rampa,
    )


@dataclass(frozen=True)
class Adaptacao:
    """O veredito, e os números que permitem discordar dele."""

    tipo: str
    motivo: str
    evidencia: dict[str, Any]

    def __post_init__(self) -> None:
        if self.tipo not in ADAPTACOES:
            raise ValueError(
                f"{self.tipo!r} não está no vocabulário de adaptação: "
                f"{sorted(ADAPTACOES)}"
            )
        if self.tipo == MESTRE:
            # `MESTRE` é rótulo de catálogo, não veredito de comparação: uma
            # `Adaptacao` só nasce de duas peças comparadas, e chamar o
            # resultado disso de "mestre" apagaria o que foi medido.
            raise ValueError(
                "`mestre` não é veredito de comparação; é o rótulo da peça de "
                "origem no pacote"
            )

    @property
    def recomposta(self) -> bool:
        """⚠️ `INDETERMINADO` responde `False` aqui, e é de propósito: quem não
        conseguiu medir não recompôs — só não sabe."""
        return self.tipo == RECOMPOSICAO


def classificar_adaptacao(mestre: bytes, variante: bytes) -> Adaptacao:
    """Mestre e variante em bytes → como a variante nasceu.

    A ordem das perguntas importa:

      1. bytes idênticos → `IDENTICO`. Nada foi adaptado, e chamar isso de
         recomposição seria o mesmo erro com outro nome.
      2. o MESTRE é de duas cores? Se não, `INDETERMINADO`: o discriminante de
         overshoot não se aplica e não há segundo discriminante aqui.
      3. a variante tem overshoot fora do segmento fundo→tinta? Então houve
         reamostragem: `CROP_RESIZE`.
      4. caso contrário `RECOMPOSICAO` — a tinta foi desenhada de novo no canvas,
         e não esticada a partir de outro.
    """
    if mestre == variante:
        return Adaptacao(
            tipo=IDENTICO,
            motivo="os bytes são os mesmos: nada foi adaptado",
            evidencia={"bytes": len(mestre)},
        )

    perfil_mestre = perfilar(mestre)
    perfil_variante = perfilar(variante)
    evidencia = {
        "mestre": perfil_mestre.para_json(),
        "variante": perfil_variante.para_json(),
    }

    if not perfil_mestre.de_duas_cores:
        return Adaptacao(
            tipo=INDETERMINADO,
            motivo=(
                "o mestre não é uma composição de duas cores; o discriminante "
                "de reamostragem deste módulo não se aplica"
            ),
            evidencia=evidencia,
        )

    if perfil_variante.fora_da_rampa > 0:
        return Adaptacao(
            tipo=CROP_RESIZE,
            motivo=(
                f"{perfil_variante.fora_da_rampa} pixels fora do segmento "
                f"fundo→tinta: overshoot de reamostragem, e o desenho original "
                f"não produz nenhum"
            ),
            evidencia=evidencia,
        )

    return Adaptacao(
        tipo=RECOMPOSICAO,
        motivo=(
            "a tinta é mistura convexa de fundo e tinta em todo pixel: foi "
            "desenhada neste canvas, não reamostrada de outro"
        ),
        evidencia=evidencia,
    )


# ─────────────────────────────────────────────────────────────────────────────
# O pacote de destino
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VarianteEntregue:
    """Uma peça pronta, ligada ao envelope que ela cumpre.

    ⚠️ Não há campo booleano `armazenamento_verificado`. Verificação é o
    resultado de RELER os bytes guardados e conferir o hash, e um booleano que
    alguém preenche é a afirmação sem a conferência — exatamente o defeito que
    `Operario._validar` já teve com `bytes_` e `sha256` declarados pelo motor.
    """

    envelope_slug: str
    conteudo_hash: str
    mime: str | None
    largura: int | None
    altura: int | None
    bytes_totais: int | None
    adaptacao: str
    #: Chave no armazenamento. `None` enquanto ninguém guardou.
    chave_de_armazenamento: str | None = None
    #: Hash recomputado a partir do que foi LIDO de volta. `None` enquanto
    #: ninguém releu — que é diferente de ter relido e divergido.
    relido_hash: str | None = None

    def __post_init__(self) -> None:
        envelope_de(self.envelope_slug)  # levanta se não existir
        if not self.conteudo_hash.startswith("sha256:"):
            raise ValueError(
                f"hash sem algoritmo declarado: {self.conteudo_hash!r}"
            )
        if self.adaptacao not in ADAPTACOES:
            raise ValueError(
                f"{self.adaptacao!r} não está no vocabulário de adaptação"
            )
        for campo in ("largura", "altura", "bytes_totais"):
            valor = getattr(self, campo)
            if valor is not None and valor <= 0:
                raise ValueError(
                    f"{campo}={valor!r}: medida ausente é None, nunca 0"
                )

    @property
    def armazenada(self) -> bool:
        return self.chave_de_armazenamento is not None

    @property
    def armazenamento_verificado(self) -> bool | None:
        """`None` = ninguém releu. `False` = releu e não bateu. Nunca colapsados."""
        if self.relido_hash is None:
            return None
        return self.relido_hash == self.conteudo_hash

    @property
    def na_medida(self) -> bool:
        env = envelope_de(self.envelope_slug)
        return (self.largura, self.altura) == (env.largura, env.altura)


@dataclass(frozen=True)
class PacoteDeDestino:
    """O que um destino recebe — e a declaração de que nada sobe sozinho.

    `publicacao_automatica` é constante e `False`. Ela existe como campo lido
    para que a ausência de publicação seja um FATO conferível pelo teste e pela
    tela, e não uma propriedade do silêncio: "nada chama a API" é verdade até
    alguém acrescentar a chamada, e aí ninguém percebe.
    """

    destino: str
    variantes: tuple[VarianteEntregue, ...]
    natureza: NaturezaDaProcedencia

    #: Nunca `True`. P17-T08 entrega vínculo ao destino, não publicação.
    publicacao_automatica: ClassVar[bool] = False

    def __post_init__(self) -> None:
        if self.destino not in DESTINOS:
            raise DestinoDesconhecido(self.destino)
        for v in self.variantes:
            if envelope_de(v.envelope_slug).destino != self.destino:
                raise ValueError(
                    f"{v.envelope_slug} não é envelope de {self.destino}"
                )

    @property
    def esperados(self) -> tuple[str, ...]:
        return tuple(e.slug for e in envelopes_de_destino(self.destino))

    @property
    def faltando(self) -> tuple[str, ...]:
        entregues = {v.envelope_slug for v in self.variantes}
        return tuple(s for s in self.esperados if s not in entregues)

    @property
    def completo(self) -> bool:
        return not self.faltando and all(v.na_medida for v in self.variantes)

    @property
    def verificado(self) -> bool:
        """Todas as variantes foram relidas do armazenamento e bateram.

        ⚠️ Um pacote vazio responde `False`. `all([])` é `True` em Python, e
        deixá-lo passar diria "tudo verificado" sobre um pacote sem nada dentro.
        """
        if not self.variantes:
            return False
        return all(v.armazenamento_verificado is True for v in self.variantes)

    @property
    def publicavel(self) -> bool:
        """Pode subir para uma conta real deste destino?

        Três perguntas independentes, e todas precisam ser `True`. A natureza é
        a que costuma reprovar: peça de motor local não vira anúncio.
        """
        return self.natureza.publicavel and self.completo and self.verificado

    def para_json(self) -> dict[str, Any]:
        return {
            "destino": self.destino,
            "natureza": self.natureza.value,
            "publicavel": self.publicavel,
            "publicacao_automatica": self.publicacao_automatica,
            "completo": self.completo,
            "verificado": self.verificado,
            "faltando": list(self.faltando),
            "variantes": [
                {
                    "envelope": v.envelope_slug,
                    "conteudo_hash": v.conteudo_hash,
                    "mime": v.mime,
                    "largura": v.largura,
                    "altura": v.altura,
                    "bytes_totais": v.bytes_totais,
                    "adaptacao": v.adaptacao,
                    "chave_de_armazenamento": v.chave_de_armazenamento,
                    "armazenamento_verificado": v.armazenamento_verificado,
                    "na_medida": v.na_medida,
                }
                for v in self.variantes
            ],
        }


def montar_pacotes(
    variantes: tuple[VarianteEntregue, ...] | list[VarianteEntregue],
    *,
    natureza: NaturezaDaProcedencia,
) -> tuple[PacoteDeDestino, ...]:
    """Agrupa as variantes por destino, criando pacote até para destino vazio.

    ⚠️ Destino sem nenhuma variante entra na lista com `variantes=()` e
    `faltando` cheio. Omiti-lo faria "não produzimos nada para o Google" ficar
    indistinguível de "o Google não é destino deste sistema".
    """
    por_destino: dict[str, list[VarianteEntregue]] = {d: [] for d in DESTINOS}
    for v in variantes:
        por_destino[envelope_de(v.envelope_slug).destino].append(v)
    return tuple(
        PacoteDeDestino(
            destino=destino,
            variantes=tuple(por_destino[destino]),
            natureza=natureza,
        )
        for destino in DESTINOS
    )
