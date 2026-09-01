"""O vocabulário do criativo — asset, procedência, especificação e lote.

Só stdlib. Nenhuma rede, nenhuma credencial, nenhum `google.ads`: este módulo
precisa rodar contra o motor falso sem custo, do mesmo jeito que
`copy/contrato.py` roda contra o mock. Quem fala com motor de imagem ou vídeo é
`porta.py` + `adaptadores/`, injetados.

## Por que existe um contrato de asset, e não um dicionário

Display, Demand Gen e Performance Max não pedem "uma imagem": pedem uma imagem
de proporção declarada, com dimensão mínima, peso máximo e quantidade mínima
por papel. Um dicionário `{"url": ..., "tipo": "imagem"}` atravessa o sistema
inteiro sem que ninguém saiba se aquele arquivo cabe no anúncio — e a resposta
chega da API, depois da geração já ter sido paga.

## As quatro invariantes que este arquivo protege

1. IDENTIDADE INTERNA ≠ ID DO GOOGLE. `identidade` é nossa, derivada do hash do
   conteúdo, e existe antes de qualquer chamada externa. `id_externo` é o
   `resource_name` que a API devolve, e começa `None`. Misturar os dois é como
   perder a procedência do lado das campanhas: quando o Google renumera, ou
   quando o mesmo arquivo sobe em duas contas, o vínculo local sobrevive.

2. PROCEDÊNCIA OBRIGATÓRIA. Nenhum asset se constrói sem dizer quem o gerou e
   de qual insumo. Um banco de criativos sem procedência não responde a
   pergunta que importa depois — "o que produziu o criativo que performou?" —
   e sem essa resposta o aprendizado não fecha.

3. DESCONHECIDO É `None`, NUNCA `0`. Largura zero e duração zero são medidas;
   `None` é ausência de medida. Um validador que trata ausência como zero
   reprova o que não mediu e, pior, aprova o que mediu errado.

4. FALHA É DADO. Um asset que não pôde ser gerado ou medido vira uma `Falha`
   com motivo, dentro do lote. Levantar exceção no meio de um lote de 20
   assets joga fora os 19 que estavam bons.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


# ── tipos de asset ──────────────────────────────────────────────────────────
#
# Os nomes seguem o papel no anúncio, não o formato do arquivo: a mesma imagem
# 1:1 é LOGO num lugar e IMAGEM_MARKETING_QUADRADA em outro, e a exigência de
# dimensão mínima é diferente em cada papel. Nomear pelo papel é o que permite
# a `requisitos.py` declarar quantidade mínima por papel.


class TipoDeAsset(Enum):
    """O papel que o asset cumpre dentro do anúncio."""

    # binários
    IMAGEM_MARKETING = "imagem_marketing"                 # paisagem, 1.91:1
    IMAGEM_MARKETING_QUADRADA = "imagem_marketing_quadrada"   # 1:1
    IMAGEM_MARKETING_RETRATO = "imagem_marketing_retrato"     # 4:5
    IMAGEM_MARKETING_RETRATO_ALTO = "imagem_marketing_retrato_alto"   # 9:16 (Shorts)
    LOGO_QUADRADO = "logo_quadrado"                       # 1:1
    LOGO_PAISAGEM = "logo_paisagem"                       # 4:1
    VIDEO = "video"                                       # YouTube

    # textuais
    HEADLINE = "headline"
    HEADLINE_LONGA = "headline_longa"
    DESCRICAO = "descricao"
    NOME_DA_EMPRESA = "nome_da_empresa"


TIPOS_BINARIOS = frozenset({
    TipoDeAsset.IMAGEM_MARKETING,
    TipoDeAsset.IMAGEM_MARKETING_QUADRADA,
    TipoDeAsset.IMAGEM_MARKETING_RETRATO,
    TipoDeAsset.IMAGEM_MARKETING_RETRATO_ALTO,
    TipoDeAsset.LOGO_QUADRADO,
    TipoDeAsset.LOGO_PAISAGEM,
    TipoDeAsset.VIDEO,
})

TIPOS_TEXTUAIS = frozenset(set(TipoDeAsset) - TIPOS_BINARIOS)

TIPOS_DE_IMAGEM = frozenset(TIPOS_BINARIOS - {TipoDeAsset.VIDEO})


def e_binario(tipo: TipoDeAsset) -> bool:
    return tipo in TIPOS_BINARIOS


# ── procedência ─────────────────────────────────────────────────────────────


class Origem(Enum):
    """De onde o arquivo veio, como classe. O evento específico é a `Procedencia`."""

    GERADO = "gerado"        # saiu de um motor de imagem/vídeo/texto
    HUMANO = "humano"        # alguém subiu à mão
    ESTOQUE = "estoque"      # banco de imagens, Wikimedia, acervo do cliente
    DERIVADO = "derivado"    # recorte, redimensionamento ou variação de outro asset


class NaturezaDaProcedencia(Enum):
    """O arquivo pode ser APRESENTADO como produção? É outra pergunta que `Origem`.

    `Origem` responde "de que classe é este arquivo" — saiu de um motor, veio de
    um humano, é recorte de outro. Nenhuma das quatro responde a pergunta que
    custa dinheiro e credibilidade: **este arquivo pode subir para uma conta
    real?** Um PNG sintético de motor local é `Origem.GERADO` exatamente como o
    banner que a agência pagou, e é essa colisão que permite um asset de ensaio
    atravessar o sistema com cara de produção.

    ## Por que o padrão é `NAO_DECLARADA`, e não `PRODUCAO`

    Porque o padrão é a resposta que o sistema dá a quem não perguntou, e
    "produção" é a resposta cara. Todo `Asset` construído por código que nunca
    ouviu falar deste campo — e há bastante — nasceria publicável por omissão, o
    que é a definição do defeito que este enum existe para fechar.

    `NAO_DECLARADA` não é sinônimo de `FIXTURE`: é ausência de declaração, e a
    ponte a trata como ausência (aviso nomeado), não como fixture (recusa). As
    duas coisas precisam de remédios diferentes: uma pede que alguém declare, a
    outra pede que alguém não publique.
    """

    NAO_DECLARADA = "nao_declarada"   # ninguém disse. NÃO é permissão.
    PRODUCAO = "producao"             # motor/fornecedor de produção; pode subir
    LOCAL = "local"                   # produzido nesta máquina, offline, para ensaio
    FIXTURE = "fixture"               # bytes versionados no repo, para teste e demo

    @property
    def publicavel(self) -> bool:
        """Só `PRODUCAO` é publicável. Derivado, nunca gravado.

        Um booleano `publicavel=True` guardado ao lado sobrevive à edição do
        resto e passa a mentir — é o mesmo motivo pelo qual `Linhagem.confirmada`
        é propriedade e não campo.
        """
        return self is NaturezaDaProcedencia.PRODUCAO


@dataclass(frozen=True)
class Procedencia:
    """Quem gerou, de quê, quando e com qual versão do motor.

    `insumo` é o texto que produziu o asset — o prompt, ou a headline de origem
    quando o asset é textual. Ele é guardado inteiro porque é o único jeito de
    repetir uma geração que deu certo; `insumo_hash` existe para agrupar
    gerações do mesmo prompt sem comparar strings longas.

    `custo_usd` é opcional e fica `None` quando o motor não reporta — não `0.0`.
    Fingir que a imagem foi de graça é o defeito que o `image_pricing` do
    FunnelForge já pagou para aprender.
    """

    motor: str                 # "openai:gpt-image-2", "veo-3.1", "humano:tarcisio"
    versao_do_motor: str       # versão/revisão do motor, ou "" quando não há
    insumo: str                # o prompt, ou o texto de origem
    quando: datetime
    pedido: str = ""           # id do pedido que originou este arquivo
    custo_usd: float | None = None
    nota: str = ""
    #: Este arquivo pode ser apresentado como produção? Ver `NaturezaDaProcedencia`.
    #: O padrão é `NAO_DECLARADA` de propósito: quem não declarou não autorizou.
    natureza: NaturezaDaProcedencia = NaturezaDaProcedencia.NAO_DECLARADA

    def __post_init__(self) -> None:
        # A invariante 2 do cabeçalho mora aqui, e é a única checagem que este
        # dataclass faz: sem motor e sem insumo não há procedência, e sem
        # procedência o asset não entra em catálogo nenhum.
        if not self.motor.strip():
            raise ValueError("procedência sem motor: quem gerou este asset?")
        if not self.insumo.strip():
            raise ValueError(f"procedência de {self.motor!r} sem insumo: gerou a partir de quê?")

    @property
    def insumo_hash(self) -> str:
        return hashlib.sha256(self.insumo.encode("utf-8")).hexdigest()[:16]

    @property
    def publicavel(self) -> bool:
        """Atalho de leitura. A regra mora no enum; aqui é só a projeção."""
        return self.natureza.publicavel


# ── o asset ─────────────────────────────────────────────────────────────────


def hash_de_conteudo(conteudo: bytes | str) -> str:
    """A identidade do arquivo é o conteúdo, não o nome nem a URL.

    Texto é hasheado em UTF-8 para que headline e imagem vivam no mesmo
    catálogo com a mesma regra de duplicidade. O prefixo `sha256:` viaja junto
    porque um hash sem algoritmo declarado é impossível de migrar depois.
    """
    if isinstance(conteudo, str):
        conteudo = conteudo.encode("utf-8")
    return "sha256:" + hashlib.sha256(conteudo).hexdigest()


@dataclass(frozen=True)
class Asset:
    """Um criativo medido, com procedência e identidade própria.

    Os campos de medida (`largura`, `altura`, `duracao_s`, `bytes_totais`,
    `mime`) são `None` quando ninguém mediu. `validacao.py` trata isso como
    violação da classe MEDIR_ANTES — nunca como aprovação por omissão.
    """

    tipo: TipoDeAsset
    procedencia: Procedencia
    conteudo_hash: str
    origem: Origem = Origem.GERADO

    texto: str | None = None          # preenchido só nos tipos textuais
    bytes_totais: int | None = None
    mime: str | None = None
    largura: int | None = None
    altura: int | None = None
    duracao_s: float | None = None

    id_externo: str | None = None     # `resource_name` do Google, quando existir
    derivado_de: str | None = None    # identidade do asset-pai, se for variante
    rotulo: str = ""                  # nome curto para humano, sem valor semântico

    def __post_init__(self) -> None:
        if not self.conteudo_hash.startswith("sha256:"):
            raise ValueError(f"hash sem algoritmo declarado: {self.conteudo_hash!r}")
        if e_binario(self.tipo) and self.texto is not None:
            raise ValueError(f"{self.tipo.value} é binário e não carrega texto")
        if not e_binario(self.tipo) and self.texto is None:
            raise ValueError(f"{self.tipo.value} é textual e chegou sem texto")
        for campo in ("largura", "altura", "bytes_totais"):
            valor = getattr(self, campo)
            if valor is not None and valor <= 0:
                # Zero aqui é quase sempre um `or 0` de alguém que não mediu.
                # Deixar passar transforma "não sei" em "medi e deu zero".
                raise ValueError(f"{campo}={valor!r}: medida ausente é None, nunca 0")
        if self.duracao_s is not None and self.duracao_s <= 0:
            raise ValueError("duracao_s ausente é None, nunca 0")

    @property
    def identidade(self) -> str:
        """Id interno, derivado do conteúdo — existe antes de falar com o Google."""
        return "cri_" + self.conteudo_hash.removeprefix("sha256:")[:20]

    @property
    def proporcao(self) -> float | None:
        """Largura/altura, ou `None` quando falta medida. Nunca 0."""
        if self.largura is None or self.altura is None:
            return None
        return self.largura / self.altura

    @property
    def medido(self) -> bool:
        """Tem as medidas que o seu tipo exige para ser julgado?"""
        if self.tipo is TipoDeAsset.VIDEO:
            return self.duracao_s is not None
        if e_binario(self.tipo):
            return self.largura is not None and self.altura is not None
        return self.texto is not None

    def com_id_externo(self, id_externo: str) -> "Asset":
        """Carimba o id do Google sem mexer na identidade interna."""
        from dataclasses import replace
        return replace(self, id_externo=id_externo)


# ── especificação de canal ──────────────────────────────────────────────────


@dataclass(frozen=True)
class EspecificacaoDeAsset:
    """O que um canal exige de um tipo de asset. Dado, não `if`.

    Todos os limites são opcionais: uma especificação que não sabe o peso
    máximo declara `bytes_maximos=None` e o validador simplesmente não checa
    peso — em vez de inventar um teto que reprovaria arquivo bom.

    `fonte_dos_numeros` viaja junto de propósito. Quando a matriz oficial do
    Agente A entrar, dá para separar num relance o que já é verdade medida do
    que ainda é chute defensável.
    """

    tipo: TipoDeAsset
    quantidade_minima: int = 0
    quantidade_maxima: int | None = None
    # Quantidade que o canal RECOMENDA sem exigir. Existe porque "logo ausente"
    # é aviso e não erro no Display: o proto do SDK escreve "is required" para
    # as imagens de marketing e NÃO escreve para logo, e um portão que reprova
    # localmente o que a API aceita é um portão que alguém desliga.
    quantidade_recomendada: int | None = None

    proporcao_alvo: tuple[int, int] | None = None
    tolerancia_proporcao: float = 0.01

    largura_minima: int | None = None
    altura_minima: int | None = None
    largura_recomendada: int | None = None
    altura_recomendada: int | None = None

    bytes_maximos: int | None = None
    mimes_aceitos: tuple[str, ...] = ()

    duracao_minima_s: float | None = None
    duracao_maxima_s: float | None = None

    caracteres_maximos: int | None = None
    # "Ao menos uma DESCRIPTION precisa ter 60 caracteres ou menos, senão
    # AssetGroupError.SHORT_DESCRIPTION_REQUIRED." É uma exigência do CONJUNTO,
    # não de cada item: quinze descrições de 90 caracteres são todas válidas
    # individualmente e o asset group é recusado assim mesmo.
    caracteres_de_pelo_menos_um: int | None = None

    fonte_dos_numeros: str = ""

    def __post_init__(self) -> None:
        if self.quantidade_maxima is not None and self.quantidade_maxima < self.quantidade_minima:
            raise ValueError(
                f"{self.tipo.value}: máximo {self.quantidade_maxima} < mínimo {self.quantidade_minima}"
            )
        if self.proporcao_alvo is not None:
            largura, altura = self.proporcao_alvo
            if largura <= 0 or altura <= 0:
                raise ValueError(f"{self.tipo.value}: proporção alvo inválida {self.proporcao_alvo}")

    @property
    def obrigatorio(self) -> bool:
        return self.quantidade_minima > 0

    @property
    def proporcao_esperada(self) -> float | None:
        if self.proporcao_alvo is None:
            return None
        return self.proporcao_alvo[0] / self.proporcao_alvo[1]


@dataclass(frozen=True)
class TetoCombinado:
    """Um limite que vale para VÁRIOS tipos somados, não para cada um.

    Existe porque a API tem exatamente isso e um modelo por tipo não consegue
    dizê-lo: no responsive display ad, `marketing_image` e
    `square_marketing_image` dividem um teto de 15, e as duas famílias de logo
    dividem um teto de 5. Quinze paisagens mais uma quadrada passam em qualquer
    checagem por tipo e são recusadas pela API — o payload inteiro, não o
    excedente.
    """

    rotulo: str
    tipos: tuple[TipoDeAsset, ...]
    maximo: int | None = None
    minimo: int = 0
    fonte_dos_numeros: str = ""


@dataclass(frozen=True)
class ExigenciaDeCanal:
    """O conjunto de especificações de um canal (DISPLAY, DEMAND_GEN, ...).

    O canal é `str` e não `Enum` porque a taxonomia canônica dos canais já tem
    dono em `campanha/taxonomia.py`. Dois enums de canal em pacotes diferentes
    é a mesma armadilha de dois medidores: eles divergem, e a divergência só
    aparece no dia em que um canal novo entra.
    """

    canal: str
    especificacoes: tuple[EspecificacaoDeAsset, ...]
    combinados: tuple[TetoCombinado, ...] = ()
    provisorio: bool = True
    fonte: str = ""

    def de(self, tipo: TipoDeAsset) -> EspecificacaoDeAsset | None:
        for spec in self.especificacoes:
            if spec.tipo is tipo:
                return spec
        return None

    @property
    def obrigatorios(self) -> tuple[TipoDeAsset, ...]:
        return tuple(s.tipo for s in self.especificacoes if s.obrigatorio)


# ── achados da validação ────────────────────────────────────────────────────


class Classe(Enum):
    """A classe decide o REMÉDIO — é ela que a cascata consulta, não o código.

    Mesmo desenho de `copy/contrato.py`: o remédio mais barato que resolve. A
    diferença de custo aqui é maior que na copy, porque regerar uma imagem é
    uma chamada paga e recortar é `Pillow` local.
    """

    ESTRUTURA = "estrutura"                    # o asset não é o que o slot pede
    MEDIR_ANTES = "medir_antes"                # falta medida: não dá para julgar
    SANEAVEL_EM_CODIGO = "saneavel_em_codigo"  # recorte, recompressão, conversão
    REGERAR_ASSET = "regerar_asset"            # só uma geração nova resolve
    REESCREVER_TEXTO = "reescrever_texto"      # texto estourou o limite
    GERAR_MAIS = "gerar_mais"                  # quantidade abaixo do mínimo
    CORTAR_EXCEDENTE = "cortar_excedente"      # quantidade acima do máximo


@dataclass(frozen=True)
class Violacao:
    """Uma regra específica que um asset (ou o lote) não cumpre."""

    codigo: str                 # "D1.dimensao_minima", "Q1.faltam", ...
    classe: Classe
    detalhe: str
    severidade: str = "erro"    # erro | aviso
    alvo: str = ""              # identidade do asset, ou o tipo quando é do lote

    def __str__(self) -> str:
        onde = f" @{self.alvo}" if self.alvo else ""
        return f"[{self.severidade}/{self.classe.value}] {self.codigo}{onde}: {self.detalhe}"


@dataclass(frozen=True)
class Falha:
    """Um asset que não existiu — geração recusada, download morto, medida impossível.

    Mora dentro do lote, ao lado dos assets bons. É por isso que um pedido de
    5 imagens com 1 recusada devolve 4 assets e 1 falha, e não uma exceção.
    """

    referencia: str            # id do pedido, nome do arquivo, o que der para citar
    motivo: str
    codigo: str = "F0.desconhecido"
    tipo: TipoDeAsset | None = None
    permanente: bool = False   # True = retentar o mesmo insumo não adianta

    def __str__(self) -> str:
        qual = f" {self.tipo.value}" if self.tipo else ""
        return f"[falha{qual}] {self.codigo} @{self.referencia}: {self.motivo}"


@dataclass(frozen=True)
class LoteDeAssets:
    """O que uma rodada de produção entregou para um canal: o bom e o que faltou."""

    canal: str
    assets: tuple[Asset, ...] = ()
    falhas: tuple[Falha, ...] = ()
    intencao: str = ""          # a que campanha/tema este lote serve

    def do_tipo(self, tipo: TipoDeAsset) -> tuple[Asset, ...]:
        return tuple(a for a in self.assets if a.tipo is tipo)

    def __len__(self) -> int:
        return len(self.assets)

    def resumo(self) -> str:
        linhas = [f"lote {self.canal} · {len(self.assets)} assets · {len(self.falhas)} falhas"]
        contagem: dict[str, int] = {}
        for a in self.assets:
            contagem[a.tipo.value] = contagem.get(a.tipo.value, 0) + 1
        for tipo, n in sorted(contagem.items()):
            linhas.append(f"  {tipo}: {n}")
        for f in self.falhas:
            linhas.append(f"  {f}")
        return "\n".join(linhas)
