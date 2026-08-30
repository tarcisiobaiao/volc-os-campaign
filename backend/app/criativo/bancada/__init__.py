"""O executor portatil do Estudio Criativo.

`contrato` nao conhece infraestrutura. `deposito` e a fila duravel. `operario` e
quem trabalha. `adaptadores/` sao os motores. Trocar o despachante local por
Cloud Run Job ou worker permanente nao toca nenhum dos tres primeiros.
"""

from .contrato import (
    Artefato,
    Encomenda,
    EstadoDoTrabalho,
    FalhaDoMotor,
    MedidaDeAudio,
    Recibo,
    SaidaPedida,
    TransicaoProibida,
    Validacao,
)
from .deposito import DepositoDeTrabalhos, Trabalho
from .operario import DespachanteLocal, Operario

__all__ = [
    "Artefato", "DepositoDeTrabalhos", "DespachanteLocal", "Encomenda",
    "EstadoDoTrabalho", "FalhaDoMotor", "MedidaDeAudio", "Operario", "Recibo",
    "SaidaPedida", "Trabalho", "TransicaoProibida", "Validacao",
]
