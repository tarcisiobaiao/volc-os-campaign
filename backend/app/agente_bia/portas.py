"""O que a aplicação da Bia precisa do mundo. Só contratos.

Duas portas, e nenhuma delas conhece HTTP do navegador:

- `Ledger` guarda conversas, execuções e eventos. A implementação real é o
  Supabase oficial por RPCs nomeadas (`infra_ledger.py`), onde o banco é quem
  garante idempotência, concorrência, limite por minuto e transições.
- `Motor` fala com o Hermes (`infra_hermes.py`). Recebe só o id da sessão e o
  texto: não existe parâmetro para modelo, provider, profile, instruções,
  ferramentas ou URL — e por isso nenhum caminho os leva até lá.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence


# ── registros ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Conversa:
    id: str
    titulo: Optional[str]
    criada_em: str
    atualizada_em: str


@dataclass(frozen=True)
class Execucao:
    id: str
    conversa_id: str
    request_id: str
    estado: str
    entrada: str
    resposta: Optional[str]
    erro_codigo: Optional[str]
    contexto: Optional[Dict[str, Any]]
    criada_em: str
    terminada_em: Optional[str]


@dataclass(frozen=True)
class Historico:
    conversa: Conversa
    execucoes: Sequence[Execucao]


#: Resultados de `Ledger.reservar`. O banco decide; a aplicação traduz.
RESERVA_NOVA = "nova"
RESERVA_REPETIDA = "repetida"
RESERVA_CONFLITO = "conflito"            # mesmo request_id, outro conteúdo/conversa
RESERVA_LIMITE = "limite"                # passou do limite por minuto
RESERVA_OCUPADO = "ocupado"              # já há execução em voo deste usuário
RESERVA_INCERTA = "bloqueada_incerta"    # a conversa tem execução incerta
RESERVA_SEM_CONVERSA = "conversa_inexistente"


@dataclass(frozen=True)
class Reserva:
    resultado: str
    execucao: Optional[Execucao] = None


@dataclass(frozen=True)
class Preparo:
    """O que o executor precisa para mandar UMA execução ao Hermes."""
    sessao_motor: str
    entrada: str
    contexto: Optional[Dict[str, Any]]


# ── ledger ──────────────────────────────────────────────────────────────────

class Ledger(Protocol):
    async def criar_conversa(self, dono: str, sessao_motor: str, titulo: Optional[str]) -> Conversa: ...

    async def listar_conversas(self, dono: str, limite: int) -> List[Conversa]: ...

    async def historico(self, dono: str, conversa_id: str) -> Optional[Historico]: ...

    async def execucao(self, dono: str, execucao_id: str) -> Optional[Execucao]: ...

    async def reservar(self, dono: str, conversa_id: str, request_id: str, entrada: str,
                       impressao: str, limite_por_minuto: int,
                       contexto: Optional[Mapping[str, Any]]) -> Reserva: ...

    async def iniciar(self, dono: str, execucao_id: str) -> Optional[Preparo]:
        """queued → running. None quando a execução não está mais `queued`."""

    async def concluir(self, dono: str, execucao_id: str, estado: str,
                       resposta: Optional[str], erro_codigo: Optional[str],
                       detalhe: Mapping[str, Any]) -> Execucao: ...

    async def expirar(self, dono: str, segundos: int) -> int:
        """queued/running mais velhos que `segundos` viram `uncertain`. Nunca reenvia."""

    async def para_reconciliar(self, dono: str, execucao_id: str) -> Optional[Preparo]:
        """Sessão e entrada de uma execução `uncertain`. None se não for o caso."""

    async def reconciliar(self, dono: str, execucao_id: str, estado: str,
                          resposta: Optional[str], detalhe: Mapping[str, Any]) -> Execucao: ...

    async def registrar_evento(self, dono: str, execucao_id: str, tipo: str,
                               detalhe: Mapping[str, Any]) -> None: ...


# ── motor (Hermes) ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RespostaDoMotor:
    texto: str
    modelo: Optional[str] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None
    duracao_ms: Optional[int] = None


@dataclass(frozen=True)
class MensagemDoMotor:
    papel: str               # user | assistant | tool
    texto: str
    #: a mensagem é chamada ou resultado de ferramenta (role=tool ou tool_calls)
    ferramenta: bool = False


class FalhaDoMotor(Exception):
    """Base. `codigo` é da lista pública de `dominio.CODIGOS_DE_ERRO`."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


class MotorRecusou(FalhaDoMotor):
    """O Hermes recusou ANTES de rodar o agente (4xx, conexão recusada). Nada aconteceu."""


class MotorIncerto(FalhaDoMotor):
    """Pode ter rodado: timeout, conexão caída no meio, 5xx, resposta ilegível."""


class Motor(Protocol):
    async def verificar_sem_ferramentas(self) -> None:
        """Portão de cada envio: Hermes vivo e NENHUM toolset habilitado. Levanta MotorRecusou."""

    async def garantir_sessao(self, sessao_motor: str, titulo: str) -> None:
        """Cria a sessão se não existir. Idempotente pelo id."""

    async def conversar(self, sessao_motor: str, texto: str) -> RespostaDoMotor: ...

    async def mensagens(self, sessao_motor: str) -> List[MensagemDoMotor]:
        """Read-back da sessão. Não chama o modelo."""
