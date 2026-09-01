"""Motor de criativo local: PNG de verdade, só stdlib, sem rede e sem crédito.

## Por que ele existe, tendo `falso.py` ao lado

`MotorFalso` é ótimo no que faz — errar sob encomenda — e inútil para o que esta
fatia precisa. Os bytes dele são `sha256(...) * 4`: 128 bytes que **declaram**
`mime="image/png"` e `largura=1200` sem que exista PNG nenhum. Passe-os por
`adaptadores/medir_imagem.medir()`, que é o medidor autoritativo da casa, e o
resultado é `Medida(mime=None, largura=None, altura=None)`.

Isso é exatamente o defeito que esta fatia foi encarregada de fechar: **um asset
que parece produção e não é**. O falso é honesto dentro do teste, onde ninguém
mede os bytes; ele deixa de ser honesto no instante em que o caminho passa a ir
até a ponte, onde os bytes SÃO conferidos.

Este motor produz um PNG que o medidor lê, que o validador julga pela geometria
real e cujo sha256 é o do arquivo. E declara, no próprio dado,
`NaturezaDaProcedencia.LOCAL` — para que a recusa de promovê-lo a produção seja
uma regra do sistema e não uma lembrança de quem estiver operando.

## Por que NÃO usa Pillow

Pela mesma razão que `medir_imagem.py` escreveu no cabeçalho dele e que continua
verdadeira: Pillow **não está em `backend/requirements.txt`**. Um motor "local"
que só roda onde alguém instalou Pillow à mão não é local — é mais uma
dependência não declarada, e o modo de falha seria o pior possível (o motor
existe, aparece na lista, e estoura `ImportError` no meio do render).

`MotorTipografico` (bancada) tem exatamente esse ponto cego hoje: ele importa
Pillow dentro de `produzir()` e de `versoes_congeladas()`, então numa máquina sem
Pillow ele **se registra** e falha depois. Este aqui escreve o PNG com `zlib` e
`struct`, que vêm com o interpretador.

## O que ele desenha, e por que isso é suficiente

Fundo sólido, uma faixa horizontal e uma grade de blocos cheios, tudo derivado do
hash do pedido. Não é uma peça de marketing e o docstring não vai fingir que é:
é uma peça de ENSAIO, com a geometria exata que o canal pede, para que o caminho
inteiro — medida, validação, ponte, recibo — seja exercitado contra um arquivo
real em vez de contra uma promessa. Quem quiser tipografia tem
`bancada/adaptadores/tipografico.py`; quem quiser produção tem motor pago.

Blocos sólidos também não são estética: PNG com paleta e regiões chapadas
comprime a alguns KB, e o logo quadrado do Demand Gen tem teto de 150 KB. Um
ruído bonito estouraria o teto e o motor reprovaria a si mesmo.

## Determinismo — o que é garantido e o que não é

Garantido: **mesmo pedido, mesmo processo, mesmos bytes**. Nada de relógio, nada
de `random` global, nada de id de pedido dentro do pixel — a semente do desenho
sai de `(referência, tipo, insumo, índice, largura, altura)`, e só.

Não garantido, e dito em voz alta: bytes idênticos entre versões diferentes de
`zlib`. O deflate não é normativo sobre a saída, só sobre a leitura. É a mesma
limitação que `MotorTipografico` tem com a versão do Pillow, e o remédio é o
mesmo da casa: a versão participa do recibo (`versoes()`), para que duas
assinaturas diferentes apontem para a causa em vez de virarem mistério.
"""

from __future__ import annotations

import hashlib
import struct
import zlib

from ..contrato import (
    TIPOS_DE_IMAGEM,
    Falha,
    NaturezaDaProcedencia,
    TipoDeAsset,
)
from ..porta import (
    ArquivoGerado,
    MotorIndisponivel,
    PedidoDeGeracao,
    PedidoDesconhecido,
    PedidoRecusado,
    RespostaDoMotor,
)
from . import medir_imagem

VERSAO_DO_ADAPTADOR = "1.0.0"

#: Quanto o desenho muda quando o algoritmo muda. Entra no recibo separado da
#: versão do adaptador porque um conserto de bug que NÃO mexe no pixel não pode
#: invalidar a comparação de duas execuções antigas.
VERSAO_DO_ALGORITMO = "blocos-1"

_MIME = "image/png"

#: Dimensão de recurso quando a especificação não diz nada. 1.91:1, que é o
#: formato mais comum do Display.
_DIMENSAO_PADRAO = (1200, 628)

#: Teto de segurança. 8000×8000 já são 64 milhões de pixels; acima disso o
#: pedido quase certamente é um erro de digitação, e alocar antes de descobrir
#: isso é como o processo morre por memória em vez de recusar com motivo.
_LADO_MAXIMO = 8000

#: Pares (fundo, tinta) em RGB. Poucos e chapados de propósito — ver o cabeçalho.
_PALETAS: tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...] = (
    ((243, 245, 247), (26, 28, 30)),
    ((12, 17, 27), (243, 246, 250)),
    ((13, 71, 161), (248, 250, 252)),
    ((17, 105, 79), (250, 251, 252)),
    ((26, 28, 30), (255, 214, 10)),
)


# ── o PNG, escrito à mão ────────────────────────────────────────────────────


def _chunk(tipo: bytes, corpo: bytes) -> bytes:
    return (
        struct.pack(">I", len(corpo))
        + tipo
        + corpo
        + struct.pack(">I", zlib.crc32(tipo + corpo) & 0xFFFFFFFF)
    )


def escrever_png_paletado(
    largura: int,
    altura: int,
    paleta: tuple[tuple[int, int, int], ...],
    linhas: list[bytearray],
) -> bytes:
    """Um PNG color-type 3 (paleta), 8 bits por pixel, sem chunk de tempo.

    ⚠️ Nenhum `tIME` e nenhum `tEXt`. Os dois são opcionais e os dois carregam
    coisas que mudam entre execuções — é assim que um formato "determinístico"
    deixa de ser, e o sintoma seria um sha256 diferente para o mesmo pixel.

    `linhas` são índices de paleta, uma linha por altura, `largura` bytes cada.
    O filtro é 0 (None) em toda linha: filtro adaptativo comprimiria melhor e
    tornaria a saída dependente da heurística, que é a última coisa que se quer
    quando o hash é a identidade.
    """
    assinatura = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", largura, altura, 8, 3, 0, 0, 0),
    )
    plte = _chunk(b"PLTE", b"".join(bytes(cor) for cor in paleta))
    cru = bytearray()
    for linha in linhas:
        cru.append(0)  # filtro None
        cru.extend(linha)
    idat = _chunk(b"IDAT", zlib.compress(bytes(cru), 9))
    return assinatura + ihdr + plte + idat + _chunk(b"IEND", b"")


# ── o desenho ───────────────────────────────────────────────────────────────


def _semente(pedido: PedidoDeGeracao, indice: int, largura: int, altura: int) -> bytes:
    crua = (
        f"{pedido.referencia}|{pedido.tipo.value}|{pedido.insumo}|"
        f"{indice}|{largura}x{altura}|{VERSAO_DO_ALGORITMO}"
    )
    return hashlib.sha256(crua.encode("utf-8")).digest()


def desenhar(largura: int, altura: int, semente: bytes) -> bytes:
    """Compõe a peça de ensaio e devolve os bytes do PNG.

    Função de módulo, e não método, porque ela é a parte que o adaptador da
    bancada reaproveita. Um segundo desenho, copiado, divergiria do primeiro no
    dia em que alguém consertasse só um — e as duas metades do sistema passariam
    a produzir hashes diferentes para o mesmo pedido.
    """
    if largura < 1 or altura < 1:
        raise ValueError(f"dimensão inválida: {largura}x{altura}")
    if largura > _LADO_MAXIMO or altura > _LADO_MAXIMO:
        raise ValueError(
            f"{largura}x{altura} passa do teto de {_LADO_MAXIMO} por lado"
        )

    fundo, tinta = _PALETAS[semente[0] % len(_PALETAS)]
    paleta = (fundo, tinta)
    IDX_FUNDO, IDX_TINTA = 0, 1

    # A faixa: um retângulo cheio entre 62% e 72% da altura, sempre com ao menos
    # uma linha, para que ela exista mesmo num logo de 144 pixels.
    faixa_de = min(altura - 1, altura * 62 // 100)
    faixa_ate = max(faixa_de + 1, altura * 72 // 100)

    # A grade: 8×8 células no canto superior esquerdo, ocupando 40% do menor
    # lado. Cada célula é acesa por um bit da semente — 64 bits, 8 bytes.
    lado_grade = max(8, min(largura, altura) * 40 // 100)
    celula = max(1, lado_grade // 8)
    margem = max(1, min(largura, altura) // 16)
    bits = int.from_bytes(semente[:8], "big")

    grade: set[tuple[int, int]] = set()
    for cy in range(8):
        for cx in range(8):
            if bits >> (cy * 8 + cx) & 1:
                grade.add((cx, cy))

    linhas: list[bytearray] = []
    for y in range(altura):
        linha = bytearray([IDX_FUNDO]) * largura
        if faixa_de <= y < faixa_ate:
            linha = bytearray([IDX_TINTA]) * largura
        else:
            cy = (y - margem) // celula
            if 0 <= cy < 8 and y >= margem:
                for cx in range(8):
                    if (cx, cy) not in grade:
                        continue
                    x0 = margem + cx * celula
                    x1 = min(largura, x0 + celula)
                    if x0 >= largura:
                        break
                    for x in range(x0, x1):
                        linha[x] = IDX_TINTA
        linhas.append(linha)

    return escrever_png_paletado(largura, altura, paleta, linhas)


def dimensao_para(especificacao, tipo: TipoDeAsset) -> tuple[int, int]:
    """O tamanho que ESTA especificação pede, derivado dela e não de uma tabela.

    A ordem importa e é a mesma de `falso._base_da_especificacao`, pelo mesmo
    motivo: quando a régua não traz dimensão recomendada — e o Display não traz,
    a matriz marca `[NÃO CONFIRMADO]` —, o tamanho tem de sair da PROPORÇÃO mais
    o mínimo. Cair num padrão 1.91:1 produziria uma paisagem no slot quadrado, e
    o motor reprovaria a si mesmo.
    """
    spec = especificacao
    if spec is None:
        return _DIMENSAO_PADRAO
    if spec.largura_recomendada and spec.altura_recomendada:
        return spec.largura_recomendada, spec.altura_recomendada
    if spec.proporcao_alvo is None:
        return _DIMENSAO_PADRAO

    alvo_l, alvo_a = spec.proporcao_alvo
    # O mínimo do canal, com um piso de 320 para as réguas que não declaram
    # largura mínima nenhuma. É o MÍNIMO cravado, sem folga, e isso é uma
    # escolha: a peça é de ensaio e o que ela precisa provar é que a geometria
    # sai da régua. Quem quiser folga passa a especificação com recomendada.
    largura = max(spec.largura_minima or 0, 320)
    altura = round(largura * alvo_a / alvo_l)
    if spec.altura_minima and altura < spec.altura_minima:
        altura = spec.altura_minima
        largura = round(altura * alvo_l / alvo_a)
    return max(1, largura), max(1, altura)


# ── o motor ─────────────────────────────────────────────────────────────────


class MotorLocalDePNG:
    """Cumpre `porta.MotorDeCriativo` sem sair da máquina e sem Pillow.

    `natureza` é atributo do MOTOR e não de cada pedido: um motor que às vezes
    produz produção e às vezes produz ensaio seria um motor cuja saída ninguém
    consegue classificar depois. Quem quiser assets de produção usa outro motor.
    """

    nome = "png-local"
    versao = VERSAO_DO_ADAPTADOR
    tipos_suportados = frozenset(TIPOS_DE_IMAGEM)
    natureza = NaturezaDaProcedencia.LOCAL

    def __init__(self, *, indisponivel: bool = False) -> None:
        #: Existe para que o caminho "motor fora do ar" seja EXERCITÁVEL sem
        #: desligar nada. Sem isso, o único jeito de provar o tratamento de
        #: `MotorIndisponivel` seria com um mock — e o mock provaria o mock.
        self.indisponivel = indisponivel
        self._pedidos: dict[str, PedidoDeGeracao] = {}

    # -- porta --

    def solicitar_geracao(self, pedido: PedidoDeGeracao) -> str:
        if self.indisponivel:
            raise MotorIndisponivel(
                "motor local marcado como fora do ar", pedido=pedido.referencia
            )
        if pedido.tipo not in self.tipos_suportados:
            # Permanente, e a distinção não é cosmética: retentar um vídeo num
            # motor de imagem erra igual todas as vezes, e a cascata precisa
            # saber disso para não queimar orçamento repetindo.
            raise PedidoRecusado(
                f"{pedido.tipo.value} não é imagem; este motor só produz "
                f"{sorted(t.value for t in self.tipos_suportados)}",
                pedido=pedido.referencia,
            )

        # O id sai do CONTEÚDO do pedido, não de um contador. Dois pedidos
        # idênticos convergem para o mesmo id, e o replay de um lote não cria
        # uma segunda linha de procedência para o mesmo arquivo.
        corpo = (
            f"{pedido.referencia}|{pedido.tipo.value}|{pedido.insumo}|"
            f"{pedido.quantidade}|{sorted(pedido.contexto.items())}"
        )
        id_do_pedido = f"png-local-{hashlib.sha256(corpo.encode()).hexdigest()[:16]}"
        self._pedidos[id_do_pedido] = pedido
        return id_do_pedido

    def receber(self, id_do_pedido: str) -> RespostaDoMotor:
        pedido = self._pedidos.get(id_do_pedido)
        if pedido is None:
            raise PedidoDesconhecido(
                f"{id_do_pedido!r} não foi emitido por este motor",
                pedido=id_do_pedido,
            )

        largura, altura = dimensao_para(pedido.especificacao, pedido.tipo)
        arquivos: list[ArquivoGerado] = []
        falhas: list[Falha] = []

        for i in range(pedido.quantidade):
            semente = _semente(pedido, i, largura, altura)
            try:
                dados = desenhar(largura, altura, semente)
            except ValueError as exc:
                falhas.append(Falha(
                    referencia=f"{id_do_pedido}#{i}",
                    motivo=f"o motor local não conseguiu compor: {exc}",
                    codigo="MOTOR.fracassou",
                    tipo=pedido.tipo,
                    permanente=True,
                ))
                continue

            # ⚠️ A medida sai dos BYTES, pelo medidor autoritativo — nunca das
            # variáveis que acabaram de ser usadas para desenhar. Se o escritor
            # de PNG tiver um defeito de cabeçalho, é aqui que ele aparece, e
            # não três camadas adiante como "imagem que a API recusou".
            medida = medir_imagem.medir(dados)
            arquivos.append(ArquivoGerado(
                conteudo=dados,
                mime=medida.mime,
                largura=medida.largura,
                altura=medida.altura,
                # `None`, não `0.0`. O motor não custa dinheiro, mas `0.0` é uma
                # afirmação de custo apurado e um COGS que soma esses zeros fecha
                # bonito e está errado.
                custo_usd=None,
                metadados={"rotulo": f"{pedido.referencia} {pedido.tipo.value} {i}"},
            ))

        return RespostaDoMotor(
            pedido=id_do_pedido,
            arquivos=tuple(arquivos),
            falhas=tuple(falhas),
            custo_usd=None,
        )

    # -- procedência --

    def versoes(self) -> dict[str, str]:
        """O que participa do pixel e pode mudar entre máquinas.

        `zlib` está aqui porque o deflate não é normativo sobre a SAÍDA: duas
        versões podem comprimir os mesmos pixels em bytes diferentes, e o sha256
        mudaria sem que nada do pedido tivesse mudado. Registrar a versão faz a
        divergência apontar para a causa em vez de virar mistério.
        """
        return {
            "adaptador": VERSAO_DO_ADAPTADOR,
            "algoritmo": VERSAO_DO_ALGORITMO,
            "zlib": zlib.ZLIB_VERSION,
            "paletas": str(len(_PALETAS)),
        }
