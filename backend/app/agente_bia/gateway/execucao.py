"""Plano de execução futuro: proposta → aprovação → execução → read-back → recibo.

ESTE ARQUIVO NÃO EXECUTA NADA. Ele fixa o contrato para que a evolução não
precise reinventar a fronteira, e recusa todas as operações na V1.

## Quem faz o quê na evolução (ADR-BIA-HERMES-VOLC-V1)

- Hermes: interface conversacional e coordenadora. Pode PROPOR.
- VOLC Agent Gateway (este pacote): capacidades tipadas. Leitura na V1; na
  próxima fase, `registrar_proposta` grava intenção, sem efeito externo.
- Worker interno (Codex SDK/app-server, futuro): missões delimitadas sobre
  repositório, com escopo e recibo próprios. NUNCA exposto como ferramenta do
  Hermes, e nunca um shell genérico disfarçado de capacidade.
- Execution plane: o ÚNICO componente que pode mutar (Google Ads, GTM,
  WordPress, verba, lance), depois de aprovação humana vinculada ao payload
  exato, com read-back e recibo. Os ledgers existentes (`trafego/ledger.py`,
  v10_02) são o modelo.

Autonomia não é decidida por prompt: é um dado do execution plane, por ação e
por conta, com o humano como aprovador.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class ExecucaoDesabilitada(PermissionError):
    """Na V1 toda operação do plano de execução é recusada."""


@dataclass(frozen=True)
class PropostaDeAcao:
    acao: str                    # nome da ação tipada do execution plane
    alvo: Mapping[str, Any]      # referência interna, nunca credencial
    payload_sha256: str          # a aprovação se vincula a ESTE payload
    justificativa: str


@dataclass(frozen=True)
class Aprovacao:
    proposta_sha256: str
    aprovado_por: str            # auth UUID do humano
    expira_em: str


@dataclass(frozen=True)
class Recibo:
    proposta_sha256: str
    estado: str                  # sucesso | falha | incerto
    read_back: Mapping[str, Any]


class PlanoDeExecucao(Protocol):
    async def propor(self, proposta: PropostaDeAcao) -> str: ...
    async def aprovar(self, aprovacao: Aprovacao) -> None: ...
    async def executar(self, proposta_sha256: str) -> Recibo: ...


class WorkerInterno(Protocol):
    """Interface do worker futuro (Codex). Missão delimitada, nunca comando livre."""
    async def abrir_missao(self, missao_tipada: Mapping[str, Any]) -> str: ...


class PlanoDesabilitado:
    """A única implementação na V1. Recusa tudo, sempre."""

    async def propor(self, proposta: PropostaDeAcao) -> str:
        raise ExecucaoDesabilitada("Bia V1 é modo consulta: proposta não é registrada")

    async def aprovar(self, aprovacao: Aprovacao) -> None:
        raise ExecucaoDesabilitada("Bia V1 é modo consulta: não há aprovação")

    async def executar(self, proposta_sha256: str) -> Recibo:
        raise ExecucaoDesabilitada("Bia V1 é modo consulta: nenhuma ação operacional")
