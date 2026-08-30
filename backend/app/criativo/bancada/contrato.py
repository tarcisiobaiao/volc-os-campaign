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
    custo_estimado_usd: float | None
    #: Custo apurado. `None` enquanto ninguem apurou.
    custo_real_usd: float | None

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
