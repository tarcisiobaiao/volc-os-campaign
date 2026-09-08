"""O envelope de canvas do `gpt-image-2` — a documentação oficial virada dado.

## Por que este arquivo existe separado do motor

Porque "que tamanho posso pedir ao provider?" é uma pergunta de CONTRATO, não de
implementação, e ela precisa ser respondível — e testável — sem cliente HTTP,
sem chave e sem gastar. O motor importa daqui; os testes provam daqui; a rota de
capacidades publica daqui. Um `if` escondido dentro do adaptador seria a mesma
regra sem nome e sem prova.

## As quatro regras, e de onde elas vieram

A documentação oficial do `gpt-image-2` diz que `size` aceita tanto um dos oito
valores nomeados quanto uma dimensão arbitrária `LARGURAxALTURA`, e que a
dimensão arbitrária precisa cumprir QUATRO condições simultâneas:

    1. a maior borda tem no máximo 3840 px;
    2. as DUAS bordas são múltiplos de 16 px;
    3. a razão entre a borda maior e a menor não passa de 3:1;
    4. o total de pixels fica entre 655.360 e 8.294.400.

A regra (4) é a que surpreende: existe um PISO. `512x512` (262.144 px) é
recusado, embora seja um tamanho perfeitamente comum em outros provedores.

⚠️ Nenhum dos quatro números foi copiado de comentário de outro projeto. O
`services/creative-studio/upstream/` — a cópia sanitizada do Aprova que vive
neste repositório — afirma os mesmos limites em
`backend/app/utils/image.py`, mas afirmação de código vizinho não é fonte: ela
foi CONFERIDA contra a documentação oficial em 08/09/2026 e coincide. A fonte
está em `FONTE_DO_ENVELOPE`, e ela é o que deve ser reconferido quando o modelo
mudar de versão.

## Por que nenhum formato comercial cabe direto

Os quatro slots do Estúdio são 1080x1080, 1080x1350, 1080x1920 e 1200x628.
Nenhum deles passa na regra (2): 1080/16 = 67,5 e 628/16 = 39,25. Ou seja, o
caminho "pedir a medida final ao provider" simplesmente não existe para este
catálogo — não é uma escolha de economia, é o contrato.

O caminho é: medida comercial -> canvas nativo válido com a MESMA proporção ->
geração -> normalização determinística até a medida exata. `canvas_para` faz o
primeiro passo; `services/creative_engine/enquadramento.py` faz o último.
"""

from __future__ import annotations

from dataclasses import dataclass

FONTE_DO_ENVELOPE = (
    "developers.openai.com/api/docs/guides/image-generation"
    "?image-generation-model=gpt-image-2 e "
    "developers.openai.com/api/reference/python/resources/images/methods/edit; "
    "lido em 08/09/2026 (platform.openai.com/docs respondeu 403 e foi substituído "
    "pelo host atual da mesma documentação)"
)

#: Os oito valores nomeados que a documentação lista para `size`.
#:
#: `auto` é o DEFAULT do provider e está aqui para que o motor possa recusá-lo
#: explicitamente: deixar o provider escolher a proporção é justamente o que
#: produz a peça no formato errado.
CANVASES_NOMEADOS: tuple[str, ...] = (
    "1024x1024",
    "1536x1024",
    "1024x1536",
    "2048x2048",
    "2048x1152",
    "3840x2160",
    "2160x3840",
    "auto",
)

BORDA_MAXIMA = 3840
MULTIPLO_DA_BORDA = 16
RAZAO_MAXIMA = 3.0
PIXELS_MINIMOS = 655_360
PIXELS_MAXIMOS = 8_294_400

#: Teto da borda longa que o motor PEDE por padrão, e que não é regra do
#: provider: é escolha de custo.
#:
#: O preço do `gpt-image-2` é por token e o número de tokens cresce com a área.
#: Gerar em 3840 para depois reduzir a 1080 paga por pixels que serão jogados
#: fora. 1536 é a maior borda dos canvases nomeados de orientação, cobre com
#: folga os 1920 do 9x16 depois da normalização, e mantém o piso de 655.360 px
#: em todas as quatro proporções do catálogo.
BORDA_LONGA_PADRAO = 1536

#: Canvases nomeados por orientação, para o desvio determinístico.
#:
#: Existem porque `canvas_para` pode, para uma proporção extrema, derivar um par
#: que não passa nas quatro regras. Nesse caso o motor NÃO inventa um número e
#: NÃO manda o pedido para ver o que acontece: ele cai para o nomeado da mesma
#: orientação, que a documentação lista literalmente. O desvio é decidido ANTES
#: da chamada, e por geometria — nunca depois, lendo o texto de um erro.
NOMEADO_POR_ORIENTACAO: dict[str, tuple[int, int]] = {
    "quadrado": (1024, 1024),
    "retrato": (1024, 1536),
    "paisagem": (1536, 1024),
}


class CanvasInvalido(ValueError):
    """Uma dimensão que o `gpt-image-2` recusaria. Nunca é enviada."""


@dataclass(frozen=True)
class Canvas:
    """O canvas nativo escolhido, e por qual caminho ele foi escolhido.

    `derivado` distingue os dois desfechos que a interface e o recibo precisam
    contar separados: `True` quando a proporção comercial foi preservada num
    canvas calculado, `False` quando ela não coube e o motor caiu para um
    nomeado — caso em que a normalização final vai recortar bem mais.
    """

    largura: int
    altura: int
    derivado: bool
    motivo: str = ""

    @property
    def size(self) -> str:
        """O literal que vai no campo `size` da requisição."""
        return f"{self.largura}x{self.altura}"

    @property
    def pixels(self) -> int:
        return self.largura * self.altura


def orientacao_de(largura: int, altura: int) -> str:
    if largura == altura:
        return "quadrado"
    return "retrato" if largura < altura else "paisagem"


def tamanho_aceito(largura: int, altura: int) -> bool:
    """As quatro regras oficiais, na ordem em que a documentação as lista.

    É a função que o motor chama antes de montar o corpo da requisição. Ela é
    pura de propósito: um teste prova o envelope inteiro sem tocar na rede.
    """
    if largura <= 0 or altura <= 0:
        return False
    if largura % MULTIPLO_DA_BORDA or altura % MULTIPLO_DA_BORDA:
        return False
    if max(largura, altura) > BORDA_MAXIMA:
        return False
    if max(largura, altura) / min(largura, altura) > RAZAO_MAXIMA:
        return False
    return PIXELS_MINIMOS <= largura * altura <= PIXELS_MAXIMOS


def _para_multiplo(valor: float) -> int:
    return max(MULTIPLO_DA_BORDA, int(round(valor / MULTIPLO_DA_BORDA)) * MULTIPLO_DA_BORDA)


#: Quantos passos de 16 px para cada lado a busca do canvas percorre.
#:
#: A busca existe porque arredondar as DUAS bordas de forma independente estraga
#: a proporção sem necessidade. Medido em 08/09/2026 com o catálogo real:
#:
#:     4x5   1080x1350  arredondamento independente -> 1088x1344 (0,8095, erro 1,19%)
#:                      borda curta derivada da longa -> 1088x1360 (0,8000, erro 0,00%)
#:
#: Um erro de 1,19% de proporção vira 1,19% de recorte na normalização final:
#: perda de composição que o provider não cobrou e que não precisava existir.
_PASSOS_DE_BUSCA = 4


def canvas_para(
    largura_alvo: int, altura_alvo: int, *, borda_longa: int = BORDA_LONGA_PADRAO
) -> Canvas:
    """O canvas nativo mais barato que preserva a proporção do formato pedido.

    O algoritmo é inteiro determinístico e não consulta nada: a mesma entrada
    devolve o mesmo canvas em qualquer máquina, que é o que permite o recibo
    afirmar "esta peça foi composta em 864x1536" sem guardar o número.

    Ordem das operações, e o motivo de cada uma:

      1. escala pela borda LONGA, para não pagar área que será descartada;
      2. sobe essa borda, se preciso, até o PISO de 655.360 px do provider —
         `1080x1080` reduzido a 1024 já passa, mas um formato pequeno não passa,
         e o piso é a regra que mais surpreende quem vem de outro provedor;
      3. varre alguns múltiplos de 16 em volta dessa borda longa e, para cada um,
         DERIVA a borda curta pela proporção pedida. Derivar em vez de arredondar
         os dois lados é o que faz 4x5 sair exato em vez de 1,19% torto;
      4. mantém só os candidatos que passam nas quatro regras oficiais;
      5. escolhe por erro de proporção e, no empate, pela MENOR área — porque a
         área é o que o provider cobra;
      6. se nenhum candidato passar, cai para o canvas NOMEADO da mesma
         orientação, com o motivo registrado.

    O passo 6 é o que impede um valor inventado de chegar ao provider: o desvio é
    decidido por geometria, ANTES da chamada, e nunca lendo o texto de um erro.
    """
    if largura_alvo <= 0 or altura_alvo <= 0:
        raise CanvasInvalido(f"medida não positiva: {largura_alvo}x{altura_alvo}")

    razao = largura_alvo / altura_alvo
    e_paisagem = largura_alvo >= altura_alvo
    longa_alvo = max(largura_alvo, altura_alvo)
    curta_alvo = min(largura_alvo, altura_alvo)

    teto = min(borda_longa, BORDA_MAXIMA)
    # A borda longa que faz a ÁREA alcançar o piso, mantida a proporção:
    # area = longa * (longa / R) = longa^2 / R, com R = longa/curta.
    minima_pelo_piso = (PIXELS_MINIMOS * (longa_alvo / curta_alvo)) ** 0.5
    base = _para_multiplo(max(min(longa_alvo, teto), minima_pelo_piso))

    candidatos: list[tuple[float, int, int, int]] = []
    for passo in range(-_PASSOS_DE_BUSCA, _PASSOS_DE_BUSCA + 1):
        longa = base + passo * MULTIPLO_DA_BORDA
        if longa < MULTIPLO_DA_BORDA:
            continue
        if e_paisagem:
            largura, altura = longa, _para_multiplo(longa / razao)
        else:
            altura, largura = longa, _para_multiplo(longa * razao)
        if not tamanho_aceito(largura, altura):
            continue
        erro = abs((largura / altura) - razao) / razao
        candidatos.append((erro, largura * altura, largura, altura))

    if candidatos:
        _, _, largura, altura = min(candidatos)
        return Canvas(largura=largura, altura=altura, derivado=True)

    nomeado = NOMEADO_POR_ORIENTACAO[orientacao_de(largura_alvo, altura_alvo)]
    return Canvas(
        largura=nomeado[0],
        altura=nomeado[1],
        derivado=False,
        motivo=(
            f"a proporção {largura_alvo}x{altura_alvo} não cabe no envelope do "
            f"provider; usado o canvas nomeado {nomeado[0]}x{nomeado[1]}"
        ),
    )
