"""Enquadramento — o envelope nativo do provider e a normalização até a medida pedida.

## O buraco que este arquivo tapa, e que estava documentado há semanas

`volc_ads/criativo/adaptadores/funnelforge_imagem.py` declara, no próprio
cabeçalho, a dependência aberta:

    "para os outros dois, a imagem sai fora de proporção e `validacao.py` a
     reprova com `D3.proporcao`, classe SANEAVEL_EM_CODIGO — que é a verdade:
     falta um passo de recorte determinístico."

Este é o passo. Ele não foi improvisado lá porque recortar sem saber o que
importa na imagem estraga o criativo em silêncio; a saída é não depender de
recorte às cegas, e sim **pedir ao modelo a proporção certa desde o começo**,
deixando o recorte como ajuste fino de poucos por cento.

## Por que três gerações, e não uma imagem recortada em três

Uma peça 1:1, uma 4:5 e uma 9:16 do mesmo briefing não são a mesma composição.
O que cabe no quadrado não cabe na vertical: o assunto muda de tamanho relativo,
a área livre para a headline muda de lugar, e a margem de segurança da
plataforma muda de altura. Recortar uma imagem-mãe entrega três arquivos com
três dimensões e **uma** composição, e a que sobrevive inteira é a do formato
original.

Por isso o motor faz UMA chamada POR FORMATO, cada uma pedindo a proporção
nativa correspondente. As três voltam com enquadramentos genuinamente
diferentes. Medido: `1:1 -> 1024x1024`, `4:5 -> 928x1152`, `9:16 -> 768x1376`
(sonda de 27/08/2026 contra `gemini-3.1-flash-image`).

## O que sobra para o recorte, e por que ele é honesto aqui

O provider entrega a proporção pedida com erro pequeno mas não nulo:
`928/1152 = 0.8056` contra `4/5 = 0.8000`; `768/1376 = 0.5581` contra
`9/16 = 0.5625`. A normalização final é um `cover` centralizado de menos de 1%
de área. Ela é **registrada** (`enquadramento`, `nativo_largura`,
`nativo_altura`), porque "houve recorte?" só é respondível se os três fatos
viverem separados. Um pipeline que devolve `1080x1350` sem dizer de onde veio
apaga a diferença entre compor e esticar.

## Ausência de Pillow não é falha de geração

Se `Pillow` não estiver disponível, a peça **não** é descartada: ela é
preservada na dimensão nativa, com `enquadramento='nativo'` e as medidas reais.
Perder uma imagem paga por causa de uma dependência de imagem seria o pior dos
dois mundos, e mentir que ela tem 1080 de largura seria o outro.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from fractions import Fraction

from volc_ads.criativo.adaptadores.medir_imagem import medir


# ── o envelope do provider ───────────────────────────────────────────────────
#
# As proporções que `gemini-*-image` compõe nativamente. A lista é DADO e não
# `if` porque ela muda quando o modelo muda, e a data de verificação viaja junto
# pelo mesmo motivo que `EspecificacaoDeAsset.fonte_dos_numeros` existe: dá para
# separar num relance o que é verdade medida do que é chute defensável.

RAZOES_NATIVAS: tuple[str, ...] = (
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
)

FONTE_DO_ENVELOPE = (
    "gemini-3.1-flash-image, imageConfig.aspectRatio; "
    "1:1, 4:5 e 9:16 confirmados por sonda em 27/08/2026"
)

# O limiar entre "só escalar" e "recortar", e ele é apertado de propósito.
#
# Com 0.5% de folga, `768x1376 -> 1080x1920` (razão 0.5581 contra 0.5625) caía em
# `resize` e ESTICAVA a peça em 0.8%. Distorção imperceptível continua sendo
# distorção, e o ADR-001 pede "as dimensões pedidas via processamento local
# **sem distorção**". Recortar 0.8% do lado maior preserva a geometria do que o
# modelo compôs; esticar deforma tudo, inclusive rosto e círculo.
_TOLERANCIA_DE_RAZAO = 0.001


def _valor(razao: str) -> float:
    esquerda, direita = razao.split(":")
    return float(esquerda) / float(direita)


def razao_nativa(largura: int, altura: int) -> str:
    """A proporção do envelope mais próxima da pedida.

    Pedir `1080x1350` devolve `"4:5"` porque é exatamente isso; pedir
    `1200x628` devolve `"16:9"` (1.910 contra 1.778) porque o envelope não tem
    1.91:1 e forçar um valor inexistente faria o provider ignorar o campo em
    silêncio, que é o pior desfecho: a peça voltaria quadrada e ninguém saberia
    por quê.
    """
    if largura <= 0 or altura <= 0:
        raise ValueError(f"dimensão não positiva: {largura}x{altura}")
    alvo = largura / altura
    return min(RAZOES_NATIVAS, key=lambda r: abs(_valor(r) - alvo))


# Como a indústria de mídia ESCREVE proporção, que não é como a matemática a
# reduz. `Fraction.limit_denominator` sozinho não serve para rótulo: com teto 8
# ele chama 1080x1920 de `0.56:1`, e com teto 16 chama 1200x628 de `21:11`.
# Nenhum dos dois aparece em qualquer especificação de anúncio. A lista abaixo é
# curada, e um valor fora dela cai para a forma decimal em vez de inventar uma
# fração que ninguém reconhece.
RAZOES_CANONICAS: tuple[str, ...] = (
    "1:1",
    "4:5",
    "5:4",
    "3:4",
    "4:3",
    "2:3",
    "3:2",
    "9:16",
    "16:9",
    "1.91:1",
    "21:9",
    "2:1",
    "1:2",
)


def rotulo_de_proporcao(largura: int, altura: int) -> str:
    """`1080x1350` -> `"4:5"`. Rótulo humano, derivado, nunca digitado.

    Procura primeiro entre as proporções canônicas de mídia; só quando nenhuma
    delas descreve a medida com folga de meio por cento é que o rótulo vira
    decimal. É o oposto de reduzir a fração: `1200x628` sai como `1.91:1`, que é
    o nome que a especificação do Display usa, e não `21:11`.
    """
    if largura <= 0 or altura <= 0:
        raise ValueError(f"dimensão não positiva: {largura}x{altura}")
    exata = largura / altura

    melhor = min(RAZOES_CANONICAS, key=lambda r: abs(_valor(r) - exata))
    if abs(_valor(melhor) - exata) / exata <= 0.005:
        return melhor

    fr = Fraction(largura, altura).limit_denominator(16)
    if abs(float(fr) - exata) / exata <= 0.001:
        return f"{fr.numerator}:{fr.denominator}"
    return f"{exata:.2f}:1"


# ── o resultado da normalização ──────────────────────────────────────────────


@dataclass(frozen=True)
class Enquadrada:
    """Os bytes finais e a história completa de como eles chegaram na medida.

    `nativa_*` é o que o provider entregou; `largura`/`altura` é o que foi
    MEDIDO no arquivo final. Os dois existem separados porque a pergunta que a
    biblioteca precisa responder ("esta peça foi composta neste formato ou
    recortada de outro?") não tem resposta com um par de números só.
    """

    conteudo: bytes
    mime: str | None
    largura: int | None
    altura: int | None
    nativa_largura: int | None
    nativa_altura: int | None
    enquadramento: str
    transformacoes: tuple[str, ...] = ()

    @property
    def bytes_totais(self) -> int:
        return len(self.conteudo)


def _pillow():
    """Importa Pillow sob demanda, ou devolve `None`.

    Import no topo faria o módulo inteiro morrer num ambiente sem a biblioteca,
    e com ele o motor — trocando "a peça saiu na dimensão nativa" por "o job
    falhou". Ver o cabeçalho: a degradação é de acabamento, nunca de patrimônio.
    """
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return None
    return Image


def enquadrar(conteudo: bytes, largura_alvo: int, altura_alvo: int) -> Enquadrada:
    """Entrega os bytes na medida pedida, dizendo exatamente o que foi feito.

    Quatro desfechos possíveis, e cada um recebe um rótulo próprio:

      `nativo`          o provider já entregou na medida exata. Nada foi tocado.
      `resize`          a proporção bateu; só a escala mudou.
      `cover_crop`      a proporção divergiu; houve recorte centralizado.
      `nao_normalizado` a normalização NÃO pôde rodar: a peça ficou na dimensão
                        que o provider entregou, diferente da pedida.

    ⚠️ O último rótulo existe desde 28/08/2026 e é conserto de uma mentira. Antes
    ele reusava `nativo`, e a interface traduz `nativo` como "o motor entregou já
    nesta dimensão, sem redimensionar" — frase exibida ao lado de "Pedido
    1080 x 1920 px" para uma peça de 768 x 1376. O álibi era que o motivo ficava
    em `transformacoes`; esse campo nunca foi renderizado em lugar nenhum.

    "Não intervim" e "não precisei intervir" são fatos diferentes, e a peça que
    saiu fora da medida pedida precisa dizer isso na cara.
    """
    if largura_alvo <= 0 or altura_alvo <= 0:
        raise ValueError(f"alvo não positivo: {largura_alvo}x{altura_alvo}")

    medida = medir(conteudo)
    nativa_l, nativa_a = medida.largura, medida.altura

    # Sem medida não há como decidir recorte. Devolver o original é a única
    # resposta honesta: qualquer transformação seria feita às cegas.
    if nativa_l is None or nativa_a is None:
        return Enquadrada(
            conteudo=conteudo,
            mime=medida.mime,
            largura=None,
            altura=None,
            nativa_largura=None,
            nativa_altura=None,
            enquadramento="nao_normalizado",
            transformacoes=("sem_medida_preserva_original",),
        )

    if (nativa_l, nativa_a) == (largura_alvo, altura_alvo):
        return Enquadrada(
            conteudo=conteudo,
            mime=medida.mime,
            largura=nativa_l,
            altura=nativa_a,
            nativa_largura=nativa_l,
            nativa_altura=nativa_a,
            enquadramento="nativo",
        )

    Image = _pillow()
    if Image is None:
        return Enquadrada(
            conteudo=conteudo,
            mime=medida.mime,
            largura=nativa_l,
            altura=nativa_a,
            nativa_largura=nativa_l,
            nativa_altura=nativa_a,
            enquadramento="nao_normalizado",
            transformacoes=("pillow_ausente_preserva_nativo",),
        )

    razao_nat = nativa_l / nativa_a
    razao_alvo = largura_alvo / altura_alvo
    so_escala = abs(razao_nat - razao_alvo) <= _TOLERANCIA_DE_RAZAO

    try:
        with Image.open(io.BytesIO(conteudo)) as img:
            img = img.convert("RGB")

            if so_escala:
                final = img.resize((largura_alvo, altura_alvo), Image.LANCZOS)
                rotulo = "resize"
                passos = (f"resize {nativa_l}x{nativa_a}->{largura_alvo}x{altura_alvo}",)
            else:
                # `cover`: escala pelo lado que falta e recorta o excedente do
                # centro. Centralizado e não "inteligente" de propósito — um
                # recorte por saliência erraria de formas diferentes a cada
                # execução, e reprodutibilidade vale mais aqui que acerto médio.
                escala = max(largura_alvo / nativa_l, altura_alvo / nativa_a)
                inter_l = max(largura_alvo, int(round(nativa_l * escala)))
                inter_a = max(altura_alvo, int(round(nativa_a * escala)))
                img = img.resize((inter_l, inter_a), Image.LANCZOS)
                esquerda = (inter_l - largura_alvo) // 2
                topo = (inter_a - altura_alvo) // 2
                final = img.crop(
                    (esquerda, topo, esquerda + largura_alvo, topo + altura_alvo)
                )
                rotulo = "cover_crop"
                passos = (
                    f"cover {nativa_l}x{nativa_a}->{inter_l}x{inter_a}",
                    f"crop centralizado ->{largura_alvo}x{altura_alvo}",
                )

            saida = io.BytesIO()
            # PNG e não JPEG: o hash de conteúdo é a identidade do asset, e um
            # recodificador com perdas faria o mesmo pedido produzir bytes
            # diferentes conforme a versão da libjpeg. Peso maior, identidade
            # estável.
            final.save(saida, format="PNG", optimize=True)
            bytes_finais = saida.getvalue()
    except Exception as erro:  # noqa: BLE001
        # Pillow existe mas não deu conta destes bytes. A peça continua válida
        # na medida nativa; descartá-la seria jogar fora uma geração paga.
        return Enquadrada(
            conteudo=conteudo,
            mime=medida.mime,
            largura=nativa_l,
            altura=nativa_a,
            nativa_largura=nativa_l,
            nativa_altura=nativa_a,
            enquadramento="nao_normalizado",
            transformacoes=(f"normalizacao_recusada:{type(erro).__name__}",),
        )

    conferida = medir(bytes_finais)
    return Enquadrada(
        conteudo=bytes_finais,
        mime=conferida.mime or "image/png",
        largura=conferida.largura,
        altura=conferida.altura,
        nativa_largura=nativa_l,
        nativa_altura=nativa_a,
        enquadramento=rotulo,
        transformacoes=passos,
    )
