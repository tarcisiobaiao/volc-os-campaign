"""Durable saga boundary required before any Meta create request."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Mapping, Protocol, Sequence

import httpx

from app.services.supabase_service import SupabaseService

from .contrato import ErroDeNascimentoMeta


EstadoPassoMeta = Literal["DESPACHAR", "CRIADO", "AMBIGUO"]


@dataclass(frozen=True)
class PassoPreparadoMeta:
    passo_ref: str
    estado: EstadoPassoMeta
    id_externo: str | None = None

    def __post_init__(self) -> None:
        if not self.passo_ref.strip():
            raise ValueError("passo_ref vazio")
        if self.estado == "CRIADO":
            if not str(self.id_externo or "").isdigit():
                raise ValueError("passo CRIADO precisa de id externo")
        elif self.id_externo is not None:
            raise ValueError("id externo so pertence a passo CRIADO")


class RegistroSagaMeta(Protocol):
    async def preparar_passo(
        self,
        *,
        plano_sha256: str,
        approval_id: str,
        ator: str,
        nome: str,
        payload_sha256: str,
    ) -> PassoPreparadoMeta:
        """Persist and COMMIT the in-flight receipt before returning."""
        ...

    async def fechar_passo(self, *, passo_ref: str, id_externo: str) -> None: ...

    async def marcar_ambiguo(self, *, passo_ref: str) -> None: ...

    async def falhar_passo(self, *, passo_ref: str, codigo: str) -> None: ...


class RegistroSagaMetaSupabase:
    """Translate the saga protocol to transactional, service-role-only RPCs."""

    def __init__(self, servico: SupabaseService) -> None:
        self._servico = servico

    def _exigir_escrita(self) -> None:
        if os.environ.get("META_CREATE_LEDGER_WRITE_ENABLED") != "1":
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_WRITE_BLOCKED",
                "o ledger de criacao Meta permanece fechado neste servidor",
            )
        if not self._servico.enabled:
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_UNAVAILABLE",
                "o Supabase operacional nao esta configurado neste backend",
            )

    async def _rpc(self, funcao: str, argumentos: Mapping[str, Any]) -> Mapping[str, Any]:
        self._exigir_escrita()
        try:
            resposta = await self._servico.rpc(funcao, dict(argumentos))
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else 500
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_REJECTED",
                f"a autoridade persistente recusou a operacao (HTTP {status})",
            ) from None
        except httpx.HTTPError:
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_UNAVAILABLE",
                "a autoridade persistente nao respondeu",
            ) from None
        if not isinstance(resposta, Mapping):
            raise ErroDeNascimentoMeta(
                "META_CREATE_LEDGER_INVALID_RESPONSE",
                "a autoridade persistente devolveu resposta invalida",
            )
        return resposta

    async def registrar_validacao(
        self,
        *,
        plano_sha256: str,
        account_ref: str,
        ator: str,
        cobertura: str,
        passos_validados: Sequence[str],
        passos_pendentes: Sequence[str],
        operacoes_totais: int,
        objetos_criados: int,
    ) -> Mapping[str, Any]:
        """Grava a prova de que a Meta aceitou ESTE plano sob validate_only.

        ⚠️ Sem esta gravação, a única evidência de que a validação aconteceu
        seria o corpo da resposta HTTP — quer dizer, o navegador. Uma aprovação
        que aceitasse essa palavra estaria deixando o cliente inventar o próprio
        recibo verde. O `validation_id` devolvido é opaco e só faz sentido
        dentro do banco: inventar um leva a rota de aprovação a
        META_VALIDATION_RECEIPT_NOT_FOUND.
        """
        return await self._rpc("trafego_meta_create_record_validation", {
            "p_plan_sha256": plano_sha256,
            "p_account_ref": account_ref,
            "p_actor_id": ator,
            "p_coverage": cobertura,
            "p_steps_validated": [str(passo) for passo in passos_validados],
            "p_steps_pending": [str(passo) for passo in passos_pendentes],
            "p_operations_total": int(operacoes_totais),
            "p_objects_created": int(objetos_criados),
        })

    async def aprovar(
        self,
        *,
        plano_sha256: str,
        account_ref: str,
        ator: str,
        daily_budget_minor: int,
        moeda: str,
        expires_at: datetime,
        passos_esperados: Sequence[str],
        validation_id: str,
        janela_da_validacao_s: int,
        nascimento_pausado_confirmado: bool,
        pedido_do_operador: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Registra a aprovação junto do manifesto imutável de passos.

        O manifesto é a lista ordenada de operações do plano compilado. Sem
        ele, uma aprovação válida para quatro operações aceitaria preparar uma
        quinta que o operador nunca viu.

        A aprovação também fixa o recibo durável do `validate_only`, a moeda, a
        contagem de operações, a confirmação humana de nascimento PAUSED e o
        pedido do operador — este último para que a criação possa recompilar o
        plano no servidor em vez de aceitar payload Meta do navegador. Todas as
        verificações são refeitas dentro da RPC: esta camada não é a autoridade,
        é o transporte dela.
        """
        manifesto = [str(passo) for passo in passos_esperados]
        if not manifesto or len(set(manifesto)) != len(manifesto):
            raise ErroDeNascimentoMeta(
                "META_APPROVAL_MANIFEST_INVALID",
                "o manifesto de passos precisa ser não vazio e sem repetição",
            )
        if not nascimento_pausado_confirmado:
            raise ErroDeNascimentoMeta(
                "META_PAUSED_BIRTH_NOT_CONFIRMED",
                "o operador precisa confirmar explicitamente o nascimento PAUSED",
            )
        return await self._rpc("trafego_meta_create_approve", {
            "p_plan_sha256": plano_sha256,
            "p_account_ref": account_ref,
            "p_actor_id": ator,
            "p_daily_budget_minor": daily_budget_minor,
            "p_currency": moeda,
            "p_expires_at": expires_at.isoformat(),
            "p_steps_expected": manifesto,
            "p_validation_id": validation_id,
            "p_validation_max_age_seconds": int(janela_da_validacao_s),
            "p_paused_birth_confirmed": True,
            "p_plan_request": dict(pedido_do_operador),
        })

    async def manifesto(self, approval_id: str) -> Mapping[str, Any]:
        """A aprovação inteira, do lado do servidor.

        Diferente de `recibo`, que é a projeção sanitizada para o navegador,
        este manifesto carrega o pedido do operador e o `step_ref` de cada
        passo. É o que permite a rota de criação receber apenas o
        `approval_id` e reconstruir o plano sem confiar no cliente.
        """
        return await self._rpc(
            "trafego_meta_create_approval_manifest", {"p_approval_id": approval_id})

    async def resolver_ausente(
        self, *, passo_ref: str, codigo: str, idade_minima_s: int = 120,
    ) -> None:
        """Fecha um passo AMBÍGUO cuja ausência foi PROVADA por leitura.

        ⚠️ O único caminho de AMBIGUOUS para FALHO. `falhar_passo` recusa este
        estado de propósito: uma recusa escrita da Meta prova que nada nasceu,
        um silêncio não prova nada, e só a leitura da conta pode desempatar.

        `idade_minima_s` é um piso temporal, não um enfeite: um passo vira
        ambíguo assim que uma segunda chamada reentra nele, e isso pode
        acontecer com a primeira ainda dentro do `await` do POST. Fechar como
        ausente nesse instante gravaria "não existe" sobre um objeto que está
        prestes a nascer. A RPC recusa abaixo de 60 s.
        """
        await self._rpc("trafego_meta_create_resolve_absent", {
            "p_step_ref": passo_ref,
            "p_error_code": codigo,
            "p_idade_minima_s": int(idade_minima_s),
        })

    async def marcar_readback_divergente(self, *, passo_ref: str, codigo: str) -> None:
        """Grava, no passo já CRIADO, que o read-back não confirmou o objeto.

        O recibo fecha antes do read-back de propósito — o id precisa estar
        gravado antes de qualquer outra coisa. O preço é que uma divergência
        posterior deixaria o livro dizendo apenas CREATED. Esta marca é o
        conserto desse preço, sem inverter a ordem que protege o id.
        """
        await self._rpc("trafego_meta_create_flag_readback", {
            "p_step_ref": passo_ref, "p_error_code": codigo,
        })

    async def consultar_validacao(self, validation_id: str) -> Mapping[str, Any]:
        """Lê o recibo de validação ANTES de o Keychain ser aberto.

        A autoridade continua sendo `trafego_meta_create_approve`, que
        reconfere tudo. Esta leitura existe para que um `validation_id`
        inventado, de outra pessoa ou velho pare o pedido sem que o token seja
        lido e sem que a Meta receba uma única requisição.
        """
        return await self._rpc(
            "trafego_meta_create_validation_lookup", {"p_validation_id": validation_id})

    async def preparar_passo(
        self,
        *,
        plano_sha256: str,
        approval_id: str,
        ator: str,
        nome: str,
        payload_sha256: str,
    ) -> PassoPreparadoMeta:
        resposta = await self._rpc("trafego_meta_create_prepare_step", {
            "p_plan_sha256": plano_sha256,
            "p_approval_id": approval_id,
            "p_actor_id": ator,
            "p_step_name": nome,
            "p_payload_sha256": payload_sha256,
        })
        return PassoPreparadoMeta(
            passo_ref=str(resposta.get("step_ref") or ""),
            estado=str(resposta.get("state") or ""),  # type: ignore[arg-type]
            id_externo=(str(resposta["external_object_id"])
                        if resposta.get("external_object_id") is not None else None),
        )

    async def fechar_passo(self, *, passo_ref: str, id_externo: str) -> None:
        await self._rpc("trafego_meta_create_close_step", {
            "p_step_ref": passo_ref, "p_external_object_id": id_externo,
        })

    async def marcar_ambiguo(self, *, passo_ref: str) -> None:
        await self._rpc("trafego_meta_create_mark_ambiguous", {"p_step_ref": passo_ref})

    async def falhar_passo(self, *, passo_ref: str, codigo: str) -> None:
        await self._rpc("trafego_meta_create_fail_step", {
            "p_step_ref": passo_ref, "p_error_code": codigo,
        })

    async def recibo(self, approval_id: str) -> Mapping[str, Any]:
        return await self._rpc(
            "trafego_meta_create_receipt", {"p_approval_id": approval_id})
