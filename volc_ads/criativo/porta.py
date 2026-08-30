"""A porta do motor de criativo — e nada além dela.

Nenhum `requests`, nenhum `httpx`, nenhuma chave. Este arquivo descreve o que
um motor de imagem ou vídeo tem de saber fazer; quem sabe FAZER mora em
`adaptadores/`, e é injetado. É o mesmo desenho de `copy/ciclo.py`, que recebe
o cliente do LLM em vez de construí-lo, e pelo mesmo motivo: assim o ciclo
inteiro roda contra um motor falso, de graça, e os testes provam comportamento
em vez de provar que a rede estava no ar.

## Por que a porta tem DOIS passos, e não `gerar() -> bytes`

Porque os motores reais desta operação não são todos síncronos. O gerador de
imagem do FunnelForge devolve os bytes na mesma chamada; o Veo devolve uma
operação de longa duração que leva minutos; um render de Remotion é um processo
externo que termina quando termina. Uma porta com um passo só obrigaria os
lentos a bloquear a thread por minutos, ou obrigaria os rápidos a inventar uma
fila que não existe.

`solicitar_geracao` devolve um id; `receber` devolve o resultado ou levanta
`GeracaoPendente`. Motor síncrono cumpre o contrato guardando o resultado
debaixo do id — custa uma linha e não mente sobre latência.

## Erro tipado com `permanente`, que é o campo que importa

`permanente=False` significa "retentar o mesmo insumo pode dar certo" (rede,
cota, fila). `permanente=True` significa "retentar o mesmo insumo vai errar
igual" — prompt recusado por política, formato não suportado, id inexistente.

A distinção é a mesma que `copy/ciclo.py` já paga para manter: retentar política
não é ineficiência, é chamar atenção. Sem ela, uma cascata de retry queima cota
repetindo um prompt que o motor já disse que nunca vai aceitar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .contrato import EspecificacaoDeAsset, Falha, TipoDeAsset


# ── o pedido ────────────────────────────────────────────────────────────────


@dataclass
class PedidoDeGeracao:
    """O que se pede ao motor. É contra isto que a resposta é conferida.

    `especificacao` viaja junto porque o motor precisa dela para escolher o
    tamanho de saída — pedir "uma imagem" e descobrir depois que veio 1024x1024
    quando o slot exige 1.91:1 é pagar duas vezes pela mesma imagem.
    """

    referencia: str                  # o que este pedido serve: tema, campanha, slot
    tipo: TipoDeAsset
    insumo: str                      # o prompt, ou o briefing textual
    quantidade: int = 1
    especificacao: EspecificacaoDeAsset | None = None
    contexto: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.referencia.strip():
            raise ValueError("pedido sem referência: para o que serve este criativo?")
        if not self.insumo.strip():
            raise ValueError("pedido sem insumo: gerar a partir de quê?")
        if self.quantidade < 1:
            raise ValueError(f"quantidade {self.quantidade} — pedir zero não é pedir")
        if self.especificacao is not None and self.especificacao.tipo is not self.tipo:
            raise ValueError(
                f"pedido de {self.tipo.value} com especificação de "
                f"{self.especificacao.tipo.value}"
            )


# ── a resposta ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ArquivoGerado:
    """Um arquivo cru saído do motor, com o que o motor conseguiu medir.

    As medidas são `None` quando o motor não sabe — e vários não sabem: a API
    de imagens devolve bytes, não dimensões. O adaptador mede se puder; o que
    não foi medido chega aqui como ausência, e `validacao.py` cobra.
    """

    conteudo: bytes | None = None
    texto: str | None = None
    mime: str | None = None
    largura: int | None = None
    altura: int | None = None
    duracao_s: float | None = None
    custo_usd: float | None = None
    metadados: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (self.conteudo is None) == (self.texto is None):
            raise ValueError("arquivo gerado tem bytes OU texto, nunca os dois nem nenhum")


@dataclass(frozen=True)
class RespostaDoMotor:
    """O que uma geração produziu: o que saiu bom e o que não saiu.

    `falhas` existe para que uma encomenda de 5 imagens com 1 recusada devolva
    4 arquivos e 1 falha, em vez de uma exceção que joga fora as 4.
    """

    pedido: str
    arquivos: tuple[ArquivoGerado, ...] = ()
    falhas: tuple[Falha, ...] = ()
    custo_usd: float | None = None

    @property
    def vazia(self) -> bool:
        return not self.arquivos


# ── erros ───────────────────────────────────────────────────────────────────


class ErroDoMotor(Exception):
    """Base de tudo que dá errado do outro lado da porta."""

    codigo = "MOTOR.desconhecido"
    permanente = False

    def __init__(self, motivo: str, *, pedido: str = "") -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.pedido = pedido

    def como_falha(self, tipo: TipoDeAsset | None = None) -> Falha:
        """Converte a exceção em dado, para que o lote sobreviva a ela."""
        return Falha(
            referencia=self.pedido or "-",
            motivo=self.motivo,
            codigo=self.codigo,
            tipo=tipo,
            permanente=self.permanente,
        )


class MotorIndisponivel(ErroDoMotor):
    """Rede, cota, fila cheia. Retentar depois pode dar certo."""

    codigo = "MOTOR.indisponivel"
    permanente = False


class PedidoRecusado(ErroDoMotor):
    """O motor olhou o insumo e disse não. Retentar o mesmo insumo erra igual."""

    codigo = "MOTOR.recusado"
    permanente = True


class GeracaoPendente(ErroDoMotor):
    """Ainda não terminou. Não é falha — é 'volte depois'."""

    codigo = "MOTOR.pendente"
    permanente = False


class GeracaoFracassada(ErroDoMotor):
    """Terminou mal e não vai melhorar sozinha."""

    codigo = "MOTOR.fracassou"
    permanente = True


class PedidoDesconhecido(ErroDoMotor):
    """`receber` com um id que este motor nunca emitiu."""

    codigo = "MOTOR.id_desconhecido"
    permanente = True


# ── a porta ─────────────────────────────────────────────────────────────────


@runtime_checkable
class MotorDeCriativo(Protocol):
    """O contrato que todo motor de imagem, vídeo ou texto cumpre.

    `nome` e `versao` não são decoração: eles viram a `Procedencia` do asset, e
    sem procedência o asset não entra no catálogo. Um motor que não sabe se
    identificar produz criativo órfão, e criativo órfão não ensina nada quando
    performa.
    """

    nome: str
    versao: str
    tipos_suportados: frozenset[TipoDeAsset]

    def solicitar_geracao(self, pedido: PedidoDeGeracao) -> str:
        """Aceita o pedido e devolve o id pelo qual ele será cobrado depois."""
        ...

    def receber(self, id_do_pedido: str) -> RespostaDoMotor:
        """O resultado, ou `GeracaoPendente` enquanto não houver."""
        ...
