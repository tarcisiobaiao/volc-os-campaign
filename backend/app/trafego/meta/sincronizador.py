"""Hermetic orchestration contract for a complete Meta hierarchy read."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Protocol

from . import dominio as dom
from .adaptador import AdaptadorMetaSomenteLeitura, ErroDeLeituraMeta
from .credenciais import (
    CredencialIndisponivel,
    ReferenciaDeCredencial,
    ResolvedorDeSegredo,
    exigir_pronta_para_leitura,
)


@dataclass(frozen=True)
class PedidoDeSync:
    conta_ativo_id: str
    conta_externa: str
    referencia: ReferenciaDeCredencial
    janela: str

    def __post_init__(self) -> None:
        if not self.conta_ativo_id.strip() or not self.janela.strip():
            raise dom.ContratoMetaInvalido("pedido de sync incompleto")
        dom.conta_canonica(self.conta_externa)


class RepositorioDeSync(Protocol):
    async def sucesso_por_chave(self, chave: str) -> dom.ReciboDeSync | None: ...

    async def aplicar_leitura_completa(
        self,
        *,
        run_id: str,
        conta_ativo_id: str,
        leitura: dom.LeituraDaHierarquia,
        chave: str,
        iniciado_em: datetime,
        concluido_em: datetime,
    ) -> dom.ReciboDeSync: ...

    async def registrar_falha(
        self,
        *,
        run_id: str,
        conta_ativo_id: str,
        conta_externa: str,
        chave: str,
        iniciado_em: datetime,
        concluido_em: datetime,
        codigo: str,
        mensagem_segura: str,
    ) -> dom.ReciboDeSync: ...


def chave_de_idempotencia(pedido: PedidoDeSync) -> str:
    conta = dom.conta_canonica(pedido.conta_externa)
    material = f"META_ADS:{pedido.conta_ativo_id}:{conta}:{pedido.janela.strip()}"
    return "meta_sync_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


async def sincronizar_conta(
    pedido: PedidoDeSync,
    *,
    adaptador: AdaptadorMetaSomenteLeitura,
    resolvedor: ResolvedorDeSegredo,
    repositorio: RepositorioDeSync,
    relogio: Callable[[], datetime] = _agora,
    gerar_run_id: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> dom.ReciboDeSync:
    """Read all pages before persisting and mark absence only on full success.

    ``aplicar_leitura_completa`` is deliberately one repository operation: its
    implementation owns the transaction.  A network or parsing failure happens
    before it and therefore cannot damage the last good projection.
    """
    chave = chave_de_idempotencia(pedido)
    anterior = await repositorio.sucesso_por_chave(chave)
    if anterior is not None:
        return replace(anterior, repetido=True)

    iniciado = dom.instante_utc(relogio(), campo="iniciado_em")
    run_id = gerar_run_id()
    uuid.UUID(run_id)
    try:
        exigir_pronta_para_leitura(pedido.referencia)
        segredo = await resolvedor.resolver(pedido.referencia)
        leitura = await adaptador.ler_hierarquia(pedido.conta_externa, segredo)
        concluido = dom.instante_utc(relogio(), campo="concluido_em")
        return await repositorio.aplicar_leitura_completa(
            run_id=run_id,
            conta_ativo_id=pedido.conta_ativo_id,
            leitura=leitura,
            chave=chave,
            iniciado_em=iniciado,
            concluido_em=concluido,
        )
    except ErroDeLeituraMeta as exc:
        codigo, mensagem = exc.codigo, exc.mensagem_segura
    except CredencialIndisponivel as exc:
        codigo, mensagem = exc.codigo, "resolucao de credencial indisponivel"
    concluido = dom.instante_utc(relogio(), campo="concluido_em")
    return await repositorio.registrar_falha(
        run_id=run_id,
        conta_ativo_id=pedido.conta_ativo_id,
        conta_externa=dom.conta_canonica(pedido.conta_externa),
        chave=chave,
        iniciado_em=iniciado,
        concluido_em=concluido,
        codigo=codigo,
        mensagem_segura=mensagem,
    )
