"""O contrato do executor, sem uma linha de infraestrutura.

## Por que este arquivo nao importa nada do projeto

Porque a decisao de onde o render roda ainda nao foi tomada. Cloud Run Job,
worker permanente, maquina do operador — as tres sao possiveis, e nenhuma pode
vazar para dentro do dominio. Este modulo importa `dataclasses`, `enum`,
`hashlib` e `typing`. Nada mais. Se um dia alguem precisar acrescentar
`import httpx` aqui, a camada errada esta sendo tocada.

## Os sete estados, e por que sao sete

`queued` -> `claimed` -> `running` -> `validating` -> `rendered`
                                  \\-> `failed`
qualquer um -> `cancelled`

`claimed` existe separado de `running` porque sao perguntas diferentes: "alguem
pegou este trabalho" e "o trabalho comecou a produzir". Um operario que morre
entre os dois deixa um `claimed` sem batimento, e a diferenca e o que permite
retomar sem duplicar render pago.

`validating` existe separado de `rendered` porque um arquivo produzido e um
arquivo aprovado sao coisas distintas. Colapsar os dois faz o gate virar
decoracao: se o estado ja e "pronto" antes do gate rodar, o gate nao decide nada.

## Ausencia

Todo campo que pode nao ter valor e `| None` e nasce `None`. Nao existe `0`
significando "nao medido", nao existe `""` significando "sem motivo" e nao existe
lista vazia significando "nao consultado".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol


class EstadoDoTrabalho(str, Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    VALIDATING = "validating"
    RENDERED = "rendered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Ausencia(str, Enum):
    """Por que um valor nao esta la. Ausencia NOMEADA, nunca `0` nem `"-"`.

    O `contrato` ja dizia, no cabecalho, que todo campo opcional nasce `None`.
    `None` responde "nao tem valor" e nao responde **por que** — e as razoes nao
    sao intercambiaveis: um custo `nao_apurado` vira numero no dia em que alguem
    ligar a apuracao; um custo `sem_custo_de_provider` ja esta respondido e nao
    vira. Colapsar os dois em `None` faz o produto perguntar para sempre uma
    pergunta que ja tem resposta.

    ⚠️ `MISMATCH` nao e ausencia de medida: e medida que CONTRADIZ a declaracao.
    Ele mora aqui porque o consumidor precisa distinguir "nao sei" de "sei, e
    esta errado", e as duas chegam pelo mesmo campo vazio se nao houver nome.
    """

    NAO_MEDIDO = "nao_medido"
    NAO_APURADO = "nao_apurado"
    NAO_DECLARADO = "nao_declarado"
    NAO_SUPORTADO = "nao_suportado"
    NAO_APLICAVEL = "nao_aplicavel"
    SEM_CUSTO_DE_PROVIDER = "sem_custo_de_provider"
    FALHOU = "falhou"
    MISMATCH = "mismatch"
    AGUARDANDO_APROVACAO = "aguardando_aprovacao"


class DeclaracaoIncoerente(ValueError):
    """Um `Declarado` com valor E ausencia, ou sem nenhum dos dois."""


@dataclass(frozen=True)
class Declarado:
    """Um valor que pode nao existir, com a razao nomeada quando nao existe.

    Exatamente UM dos dois lados esta preenchido, e o construtor recusa o resto.
    Sem essa recusa o tipo seria uma sugestao: nada impediria `Declarado(None,
    None)`, que e o mesmo `None` mudo de antes com uma casca em volta.
    """

    valor: Any | None = None
    ausencia: Ausencia | None = None

    def __post_init__(self) -> None:
        if (self.valor is None) == (self.ausencia is None):
            raise DeclaracaoIncoerente(
                "um Declarado tem valor OU ausencia nomeada, nunca os dois nem nenhum"
            )

    @staticmethod
    def de(valor: Any | None, quando_ausente: Ausencia) -> Declarado:
        """Constroi a partir de um valor que pode ser `None`."""
        return (
            Declarado(ausencia=quando_ausente)
            if valor is None
            else Declarado(valor=valor)
        )

    @property
    def presente(self) -> bool:
        return self.valor is not None


#: Estados a partir dos quais nao ha mais transicao. Um trabalho terminal nunca
#: volta: retomar um `failed` cria trabalho NOVO, com nova tentativa, para que o
#: historico de quantas vezes se tentou nao seja apagado pela retomada.
TERMINAIS: frozenset[EstadoDoTrabalho] = frozenset(
    {EstadoDoTrabalho.RENDERED, EstadoDoTrabalho.FAILED, EstadoDoTrabalho.CANCELLED}
)

#: Transicoes permitidas. Fora daqui, `TransicaoProibida`.
TRANSICOES: dict[EstadoDoTrabalho, frozenset[EstadoDoTrabalho]] = {
    EstadoDoTrabalho.QUEUED: frozenset(
        {EstadoDoTrabalho.CLAIMED, EstadoDoTrabalho.CANCELLED}
    ),
    EstadoDoTrabalho.CLAIMED: frozenset(
        {
            EstadoDoTrabalho.RUNNING,
            EstadoDoTrabalho.FAILED,
            EstadoDoTrabalho.CANCELLED,
            # de volta para a fila quando o lease vence sem batimento
            EstadoDoTrabalho.QUEUED,
        }
    ),
    EstadoDoTrabalho.RUNNING: frozenset(
        {
            EstadoDoTrabalho.VALIDATING,
            EstadoDoTrabalho.FAILED,
            EstadoDoTrabalho.CANCELLED,
            EstadoDoTrabalho.QUEUED,
        }
    ),
    EstadoDoTrabalho.VALIDATING: frozenset(
        {EstadoDoTrabalho.RENDERED, EstadoDoTrabalho.FAILED, EstadoDoTrabalho.CANCELLED}
    ),
    EstadoDoTrabalho.RENDERED: frozenset(),
    EstadoDoTrabalho.FAILED: frozenset(),
    EstadoDoTrabalho.CANCELLED: frozenset(),
}


class TransicaoProibida(ValueError):
    def __init__(self, de: EstadoDoTrabalho, para: EstadoDoTrabalho) -> None:
        super().__init__(f"transicao proibida: {de.value} -> {para.value}")
        self.de, self.para = de, para


def pode_ir(de: EstadoDoTrabalho, para: EstadoDoTrabalho) -> bool:
    return para in TRANSICOES[de]


# ─────────────────────────────────────────────────────────────────────────────
# A encomenda
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SaidaPedida:
    """Uma peca que o trabalho deve produzir."""

    slot: str
    largura: int
    altura: int
    midia: str
    mime: str


def canonizar(valor: Any) -> Any:
    """Normaliza um valor antes de ele entrar na chave de identidade.

    ⚠️ ACHADO ADVERSARIAL. `json.dumps` serializa `1` como `1` e `1.0` como
    `1.0`: dois pedidos semanticamente iguais viravam duas chaves e, com um motor
    pago, dois gastos. `True` tambem e `int` em Python e precisa sobreviver como
    booleano, entao a ordem dos `isinstance` abaixo importa.

    Nao mexe em `None`: ausencia continua sendo ausencia, e colapsa-la com `""`
    ou `0` seria trocar um defeito por outro.
    """
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, float):
        # `1.0` -> `1`; `1.5` continua float. `is_integer` cobre `-0.0` tambem.
        return int(valor) if valor.is_integer() else valor
    if isinstance(valor, dict):
        return {k: canonizar(v) for k, v in sorted(valor.items())}
    if isinstance(valor, (list, tuple)):
        # A ORDEM de uma lista e significativa (cenas, camadas): nao ordena.
        return [canonizar(v) for v in valor]
    return valor


@dataclass(frozen=True)
class Encomenda:
    """O que o operario recebe. Congelada: um trabalho nao muda de pedido.

    ⚠️ `seed` nao tem default. Um render sem semente e um render que nao pode ser
    repetido, e "reproduzivel" e a promessa central do recibo. Deixar default aqui
    faria a metade dos trabalhos nascer com a mesma semente por acidente, o que e
    pior que nenhuma: parece determinismo e nao e.
    """

    receita_id: str
    #: Dono do trabalho. Entra na chave de identidade: dois inquilinos com o
    #: mesmo pedido sao dois trabalhos, nao um compartilhado.
    tenant_id: str
    motor_slug: str
    modo_slug: str
    finalidade_slug: str
    seed: int
    saidas: tuple[SaidaPedida, ...]
    #: Parametros que o motor entende. O que o motor NAO entende nao entra aqui:
    #: parametro exposto que o motor ignora e mentira de interface.
    parametros: dict[str, Any] = field(default_factory=dict)

    def chave_de_idempotencia(self) -> str:
        """Deriva a chave do CONTEUDO do pedido, nao de um contador.

        Dois pedidos identicos tem a mesma chave e o segundo nao paga de novo.
        Um pedido que difere em um pixel tem chave diferente, porque produz outra
        coisa. `sort_keys` porque a ordem de um dicionario nao pode mudar a
        identidade do trabalho.
        """
        corpo = {
            # ⚠️ `tenant` primeiro e sempre. Sem ele, dois inquilinos com o mesmo
            # pedido compartilhavam o mesmo trabalho — e o segundo lia o artefato
            # do primeiro.
            "tenant": self.tenant_id,
            "receita": self.receita_id,
            "motor": self.motor_slug,
            "modo": self.modo_slug,
            "finalidade": self.finalidade_slug,
            "seed": self.seed,
            "saidas": [asdict(s) for s in self.saidas],
            "parametros": canonizar(self.parametros),
        }
        cru = json.dumps(corpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(cru.encode("utf-8")).hexdigest()


def chave_de_retomada(chave_original: str, n: int) -> str:
    """A chave da n-esima retomada de um trabalho.

    ⚠️ ACHADO ADVERSARIAL. `chave_idempotencia` e `unique`, entao um trabalho que
    falhava ficava `failed` PARA SEMPRE: reenviar o mesmo pedido devolvia o mesmo
    trabalho terminal. Cenario real: a maquina sobe sem fontes, todo pedido vira
    `motor_desconhecido`, o operador instala a fonte, reinicia, clica de novo — e
    recebe o mesmo `failed`, indefinidamente.

    Derivar a chave da original mais o numero da retomada resolve os dois lados:
    a retomada NASCE (chave nova) e dois cliques na mesma retomada convergem
    (mesma chave, mesmo `n`).
    """
    if n < 1:
        raise ValueError("a primeira retomada e n=1")
    return hashlib.sha256(f"{chave_original}:retomada:{n}".encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# O recibo
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Enquadramento:
    """A dimensao NATIVA do motor, a ALVO do pedido, e o que ligou uma a outra.

    ⚠️ O recibo guardava so a dimensao final. Com isso, `1080x1920` significava a
    mesma coisa quando o motor desenhou nativamente nesse tamanho e quando ele
    desenhou `1024x1024` e alguem esticou — e a segunda peca tem pixel deformado
    que nenhum campo acusava. A operacao e nomeada porque `resize` e `crop`
    perdem coisas diferentes: um deforma, o outro corta conteudo fora do quadro.
    """

    largura_nativa: int
    altura_nativa: int
    largura_alvo: int
    altura_alvo: int
    #: `nenhuma` | `resize` | `crop` | `letterbox` | `pillarbox`
    operacao: str

    @property
    def houve_transformacao(self) -> bool:
        return self.operacao != "nenhuma"


@dataclass(frozen=True)
class MedidaDeVideo:
    """Numeros de video LIDOS DO ARQUIVO. Nenhum deles e declaracao do motor.

    `fps_num`/`fps_den` guardam a fracao em vez do float porque `30000/1001` (o
    NTSC de 29,97) nao sobrevive a um `round(2)` — e a diferenca entre 29,97 e 30
    e exatamente o que faz uma peca dessincronizar num corte longo.
    """

    codec_video: str
    codec_audio: str | None
    largura: int
    altura: int
    fps_num: int
    fps_den: int
    quadros: int
    duracao_s: float
    #: `None` quando o arquivo nao tem faixa de audio. Uma faixa muda NAO conta
    #: como ausencia: ela existe e mede `-inf` LUFS, que e outro fato.
    sample_rate: int | None
    canais: int | None
    #: Quem mediu. Entra no recibo porque duas versoes de ffprobe podem discordar.
    fonte: str

    @property
    def fps(self) -> float:
        return self.fps_num / self.fps_den if self.fps_den else 0.0


@dataclass(frozen=True)
class InsumoSanitizado:
    """O briefing como o recibo INTERNO o guarda: legivel, sem os identificadores.

    ⚠️ Isto NAO e o hash, e nao substitui o hash. O relatorio da rodada anterior
    registrou a confusao com todas as letras: "nao confunda 'prompt nao exposto
    publicamente' com 'prompt sanitizado e auditavel'". Um hash identifica e nao
    pode ser lido; um texto sanitizado pode ser lido por um auditor e nao carrega
    e-mail, telefone, documento nem valor. As duas coisas respondem perguntas
    diferentes e por isso as duas estao aqui.

    ⚠️ E isto NAO sai pela API publica. `fronteira_publica` continua devolvendo
    estado + impressao digital; quem le o recibo interno e o operador da casa.
    """

    #: `ausente` | `vazio` | `sanitizado`
    estado: str
    #: O texto legivel, ja sem identificadores. `None` nos dois primeiros estados.
    texto: str | None
    #: sha256 do insumo COMPLETO, antes de qualquer corte. E o que responde
    #: "e o mesmo briefing?" mesmo depois de o texto ter sido reduzido.
    hash_do_completo: str | None
    #: Quais regras casaram, e quantas vezes cada uma. Sem isto, o auditor nao
    #: sabe se `<numero>` apareceu porque havia um numero ou porque o texto ja
    #: dizia "<numero>".
    substituicoes: dict[str, int]
    versao_do_sanitizador: str
    truncado: bool


@dataclass(frozen=True)
class Procedencia:
    """De onde a peca veio: modo, finalidade, dono, provider, modelo, licenca.

    Estava espalhada: `modo_slug` e `finalidade_slug` viviam so na `Encomenda`,
    `natureza` so no envelope, e provider/modelo/licenca em lugar nenhum. Um
    recibo que nao carrega isso obriga quem audita a ir buscar o trabalho, e o
    trabalho pode ter sido apagado.
    """

    receita_id: str
    tenant_id: str
    modo_slug: str
    finalidade_slug: str
    #: `local` | `producao` | `nao_declarada` — quem sabe se pode publicar e quem
    #: produziu.
    natureza: str
    #: Nome do provider externo. `SEM_CUSTO_DE_PROVIDER`/`NAO_APLICAVEL` para
    #: motor local; `NAO_DECLARADO` quando ha provider e o motor nao o diz.
    provider: Declarado
    #: Identificador do modelo do provider (ex.: familia e versao).
    modelo: Declarado
    #: Licenca sob a qual a peca pode circular.
    licenca: Declarado
    #: Se a peca exige aviso de conteudo gerado por IA no destino.
    disclosure: Declarado
    brand_pack: Declarado


@dataclass(frozen=True)
class Custo:
    """Estimado, real e a razao de cada ausencia — separados de proposito.

    ⚠️ ACHADO HERDADO. Os dois campos eram literais `None` no construtor do
    recibo, sem produtor nenhum. Enquanto o motor e local e gratuito, `None` e
    honesto; no dia em que entrar um motor pago, ligar o provider sem ligar a
    apuracao faria todo trabalho nascer com custo nulo permanente. Nomear a
    ausencia e o que impede esse `None` de virar `0.0` por descuido.
    """

    estimado_usd: Declarado
    real_usd: Declarado
    #: Quem apurou. `None` quando ninguem apurou.
    apurado_por: str | None = None


@dataclass(frozen=True)
class RegistroDeStorage:
    """Onde o artefato foi guardado, e se alguem releu de la.

    `verificado` so pode ser `True` depois de uma RELEITURA que conferiu bytes e
    sha256. Um artefato apresentado como verificado antes disso e a forma mais
    barata de mentir sobre patrimonio.
    """

    slot: str
    chave: Declarado
    #: MESMO vocabulario da `MaquinaDeArmazenamento` e do gatilho SQL —
    #: `LOCAL`, `UPLOADED_UNVERIFIED`, `VERIFIED_OK`, `VERIFIED_MISMATCH` — mais
    #: os tres desfechos em que NADA subiu: `NAO_PUBLICADO` (nao ha loja),
    #: `BUCKET_AUSENTE` e `INDISPONIVEL`.
    #:
    #: ⚠️ Traduzir para portugues aqui faria a mesma maquina existir com dois
    #: vocabularios, e a proxima divergencia entre banco e aplicacao apareceria
    #: como discussao de traducao. `armazenamento_verificado` ja escreveu essa
    #: regra; este campo a obedece.
    estado: str
    #: sha256 relido do armazenamento. `None` enquanto nao houve releitura.
    sha256_relido: Declarado
    bytes_relidos: Declarado
    lido_em: str | None = None

    @property
    def verificado(self) -> bool:
        return self.estado == "VERIFIED_OK"


@dataclass(frozen=True)
class Aprovacao:
    """A decisao humana. `AGUARDANDO_APROVACAO` nao e reprovacao nem aprovacao."""

    #: `aguardando` | `aprovado` | `reprovado`
    estado: str
    por: str | None = None
    em: str | None = None
    motivo: str | None = None

    @property
    def liberado(self) -> bool:
        return self.estado == "aprovado"


@dataclass(frozen=True)
class DestinoDoRecibo:
    """Para onde a peca serve — e o veredito do requisito daquele destino."""

    slug: str
    #: `serve` — casa todos os envelopes que o destino espera.
    #: `serve_parcialmente` — casa pelo menos um, e `motivos` diz quais faltam.
    #: `nao_serve` — nao casa nenhum.
    #: `nao_avaliado` — ninguem perguntou (catalogo ausente, medida ausente).
    #:
    #: ⚠️ `serve_parcialmente` existe porque as duas perguntas sao diferentes:
    #: "esta peca serve a este destino?" e "o lote deste destino esta completo?".
    #: A segunda tem dono proprio (`PacoteDeDestino.completo`), e responder a
    #: primeira com `nao_serve` faria uma peca legitima parecer imprestavel.
    veredito: str
    #: Motivos legiveis quando nao serve. Lista vazia com veredito `serve` e a
    #: unica combinacao em que vazio significa "nada a apontar".
    motivos: tuple[str, ...] = ()


@dataclass(frozen=True)
class Artefato:
    """Um arquivo produzido, com o que basta para conferir que e ele mesmo."""

    slot: str
    caminho: str
    mime: str
    bytes_: int
    sha256: str
    largura: int | None
    altura: int | None
    #: Segundos. `None` para imagem, e `None` tambem para video nao medido —
    #: as duas ausencias sao diferentes de `0.0`.
    duracao_s: float | None = None
    #: Medida tecnica LIDA DO ARQUIVO quando ele e video. `None` para imagem
    #: (`NAO_APLICAVEL`) e `None` tambem quando ninguem mediu (`NAO_MEDIDO`) —
    #: o `Recibo.video_ausente_porque` separa as duas.
    video: MedidaDeVideo | None = None
    #: O que aconteceu entre a dimensao NATIVA do motor e a dimensao ALVO do
    #: pedido. `None` significa que o motor nao declarou enquadramento.
    enquadramento: Enquadramento | None = None


@dataclass(frozen=True)
class MedidaDeAudio:
    """Numeros de audio preservados como NUMEROS.

    ⚠️ O legado mede LUFS integrado e true peak e o VOLC O.S. reduzia os dois a
    PASS/FAIL. Um gate que so diz "passou" impede a proxima pergunta: passou por
    quanto? A margem e o que decide se vale remixar.
    """

    lufs_integrado: float | None
    true_peak_dbtp: float | None
    alvo_lufs: float | None
    tolerancia_lufs: float | None
    fonte: str


@dataclass(frozen=True)
class Validacao:
    """O veredito de um gate sobre um artefato."""

    gate: str
    resultado: str  # PASS | WARN | FAIL | SKIPPED
    detalhe: dict[str, Any] | None
    bloqueante: bool


@dataclass(frozen=True)
class Recibo:
    """A prova do que aconteceu. Sem ele, `rendered` e opiniao.

    Guarda o suficiente para repetir: semente, versoes, parametros e hashes. Se
    dois recibos do mesmo pedido tiverem `assinatura_determinista` igual, o motor
    e reprodutivel para aquele pedido. Se diferirem, o recibo diz exatamente onde.
    """

    trabalho_id: str
    chave_de_idempotencia: str
    #: Quem produziu. `Trabalho.operario` e o portador do LEASE e some quando o
    #: trabalho termina; isto e o registro permanente de quem fez.
    produzido_por: str
    motor_slug: str
    motor_versao: str
    seed: int
    #: Versoes congeladas do que participou do render. Nome -> versao.
    versoes: dict[str, str]
    parametros: dict[str, Any]
    artefatos: tuple[Artefato, ...]
    validacoes: tuple[Validacao, ...]
    audio: MedidaDeAudio | None
    iniciado_em: str
    terminado_em: str
    #: Estimativa declarada. `None` quando o motor nao declara — nunca `0.0`.
    #: ⚠️ MANTIDO por compatibilidade de leitura: `custo` abaixo e a fonte, e
    #: carrega a RAZAO da ausencia que estes dois numeros nao sabem carregar.
    custo_estimado_usd: float | None
    #: Custo apurado. `None` enquanto ninguem apurou.
    custo_real_usd: float | None

    # ── Campos acrescentados pelo contrato produtivo ────────────────────────
    # Nenhum tem default, e isso e deliberado: o construtor unico do recibo mora
    # em `operario.py`, e um default aqui deixaria um campo do contrato nascer
    # vazio sem ninguem decidir nada. Preencher com `Declarado(ausencia=...)` e
    # uma decisao; esquecer nao pode ser.

    #: Modo, finalidade, dono, provider, modelo, licenca, disclosure, brand pack.
    procedencia: Procedencia
    #: O briefing sanitizado e auditavel, mais o hash do insumo COMPLETO.
    insumo: InsumoSanitizado
    #: Tudo que entrou no render e pode mudar o pixel sem mudar o pedido: fonte,
    #: leito sonoro, template. Nome -> sha256. Entra na assinatura determinista.
    hashes_de_entrada: dict[str, str]
    #: Qual tentativa produziu este recibo. Vivia so na linha do trabalho, e a
    #: linha some quando alguem limpa a fila.
    tentativa: int
    #: Custo com a razao nomeada de cada ausencia.
    custo: Custo
    #: Segundos entre o inicio e o fim do trabalho. `iniciado_em`/`terminado_em`
    #: sao strings e obrigavam todo consumidor a reparsear duas datas para
    #: responder "quanto demorou".
    duracao_do_trabalho_s: float
    #: Onde cada artefato foi guardado e se alguem releu de la.
    storage: tuple[RegistroDeStorage, ...]
    #: Para que destinos a peca serve, com veredito por destino.
    destinos: tuple[DestinoDoRecibo, ...]
    #: A decisao humana. Nasce `aguardando`.
    aprovacao: Aprovacao
    #: Por que nao ha `MedidaDeAudio`, quando nao ha. `None` quando ha.
    audio_ausente_porque: Ausencia | None
    #: Por que nao ha `MedidaDeVideo` nos artefatos, quando nao ha.
    video_ausente_porque: Ausencia | None

    def assinatura_determinista(self) -> str:
        """Hash do que DEVE ser igual entre duas execucoes do mesmo pedido.

        Exclui `trabalho_id` e os carimbos de tempo de proposito: eles mudam
        sempre e mudariam a assinatura sempre, tornando-a inutil para responder
        "o motor repetiu?".
        """
        # `produzido_por` fica de fora: qual operario fez nao muda o pixel, e
        # incluir tornaria a assinatura diferente a cada maquina.
        corpo = {
            "chave": self.chave_de_idempotencia,
            "motor": f"{self.motor_slug}@{self.motor_versao}",
            "seed": self.seed,
            "versoes": self.versoes,
            # ⚠️ ACRESCENTADO. A assinatura respondia "o motor repetiu?" olhando
            # so para o pedido e para as versoes declaradas. Uma FONTE trocada no
            # disco muda o pixel sem mudar nenhuma das duas coisas, e a
            # assinatura nao acusava — o proprio ADR registra o caso: vendorizar
            # uma familia sem o eixo italico faria o Chrome inclinar o romano, e
            # "a assinatura determinista nao acusaria".
            #
            # Incluir os hashes de entrada muda a assinatura de todo recibo
            # existente. Isso e o sistema funcionando: as assinaturas antigas
            # respondiam a pergunta errada.
            "hashes_de_entrada": self.hashes_de_entrada,
            "parametros": self.parametros,
            "artefatos": [
                {"slot": a.slot, "sha256": a.sha256, "bytes": a.bytes_,
                 "largura": a.largura, "altura": a.altura}
                for a in sorted(self.artefatos, key=lambda a: a.slot)
            ],
        }
        cru = json.dumps(corpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(cru.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# As portas
# ─────────────────────────────────────────────────────────────────────────────


class FalhaDoMotor(Exception):
    """Falha tipada. `permanente` decide se retentar tem sentido."""

    def __init__(self, mensagem: str, *, permanente: bool) -> None:
        super().__init__(mensagem)
        self.permanente = permanente


class MotorDeProducao(Protocol):
    """O que um motor precisa saber fazer para o operario o usar.

    Recebe um diretorio de trabalho EXCLUSIVO daquele trabalho. Nao pode escrever
    em nenhum outro lugar: 21 dos 26 geradores da fabrica escrevem em arquivos
    compartilhados na raiz, e por isso dois renders simultaneos la se contaminam.
    """

    slug: str
    versao: str

    def versoes_congeladas(self) -> dict[str, str]:
        """Tudo que participa do render e pode mudar o resultado."""
        ...

    def produzir(self, encomenda: Encomenda, dir_trabalho: str) -> tuple[Artefato, ...]:
        ...


class Despachante(Protocol):
    """Onde o trabalho vai rodar. A unica coisa que sabe de infraestrutura.

    Local hoje. Cloud Run Job, worker permanente ou fila externa depois — sem que
    `Encomenda`, `Recibo` ou `MotorDeProducao` mudem uma linha.
    """

    def despachar(self, trabalho_id: str) -> None: ...
