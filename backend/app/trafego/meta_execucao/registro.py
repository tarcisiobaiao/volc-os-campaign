"""Durable saga boundary required before any Meta create request."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Protocol, Sequence

import httpx

from app.services.supabase_service import SupabaseService

from .contrato import ErroDeNascimentoMeta
from .capacidades import ledger_liberado
from .orcamento_aprovado import manifesto_orcamentario


EstadoPassoMeta = Literal["DESPACHAR", "CRIADO", "AMBIGUO"]


@dataclass(frozen=True)
class PassoPreparadoMeta:
    passo_ref: str
    estado: EstadoPassoMeta
    id_externo: str | None = None
    #: A CERCA. Só o `DESPACHAR` recebe token, e só quem o carrega consegue
    #: concluir aquele despacho. Um trabalhador cuja reivindicação foi tomada
    #: por outro processo continua com o token ANTIGO, e é isso que o impede de
    #: fechar, falhar ou anotar por cima de uma conclusão mais nova.
    #:
    #: ⚠️ Ausente nos demais estados de propósito: `CRIADO` não tem conclusão
    #: pendente para cercar, e `AMBIGUO` é justamente o estado de quem NÃO tem
    #: autoridade. Cunhar token neles seria conceder o que eles não têm.
    claim_token: str | None = None

    def __post_init__(self) -> None:
        if not self.passo_ref.strip():
            raise ValueError("passo_ref vazio")
        if self.estado == "CRIADO":
            if not str(self.id_externo or "").isdigit():
                raise ValueError("passo CRIADO precisa de id externo")
        elif self.id_externo is not None:
            raise ValueError("id externo so pertence a passo CRIADO")
        if self.estado == "DESPACHAR":
            if not str(self.claim_token or "").strip():
                raise ValueError("passo DESPACHAR precisa de token de reivindicacao")
        elif self.claim_token is not None:
            raise ValueError("token de reivindicacao so pertence a passo DESPACHAR")


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

    async def fechar_passo(
        self, *, passo_ref: str, id_externo: str, claim_token: str,
    ) -> str | None:
        """Fecha o passo e DEVOLVE o token girado, para anotar o read-back."""
        ...

    async def marcar_ambiguo(self, *, passo_ref: str, claim_token: str) -> None: ...

    async def falhar_passo(
        self, *, passo_ref: str, codigo: str, claim_token: str,
    ) -> None: ...


class RegistroSagaMetaSupabase:
    """Translate the saga protocol to transactional, service-role-only RPCs."""

    def __init__(self, servico: SupabaseService) -> None:
        self._servico = servico

    def _exigir_escrita(self) -> None:
        if not ledger_liberado():
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
            try:
                provider_code = exc.response.json().get("code") if exc.response is not None else None
            except (ValueError, AttributeError):
                provider_code = None
            if status == 404 or provider_code in {"PGRST202", "PGRST204", "42703", "42883"}:
                raise ErroDeNascimentoMeta(
                    "META_CREATE_SCHEMA_REQUIRED",
                    "o banco precisa da migration de aprovação Meta V2 e recarga do schema",
                ) from None
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
        daily_budget_minor: int | None,
        moeda: str,
        expires_at: datetime,
        passos_esperados: Sequence[str],
        validation_id: str,
        janela_da_validacao_s: int,
        nascimento_pausado_confirmado: bool,
        pedido_do_operador: Mapping[str, Any],
        recibos_de_supply: Sequence[Mapping[str, Any]],
        plano_congelado: Mapping[str, Any],
        versao_do_compilador: str,
        snapshot_sha256: str,
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
        recibos = [dict(recibo) for recibo in recibos_de_supply]
        if not recibos or len(recibos) > 10:
            raise ErroDeNascimentoMeta(
                "META_ASSET_SUPPLY_RECEIPTS_INVALID",
                "a aprovação precisa carregar entre 1 e 10 recibos de peça",
            )
        if not plano_congelado:
            raise ErroDeNascimentoMeta(
                "META_PLAN_SNAPSHOT_MISSING",
                "a aprovação precisa congelar o plano despachável antes de existir",
            )
        budget = manifesto_orcamentario(plano_congelado)
        if budget["daily_total_minor"] != daily_budget_minor:
            raise ErroDeNascimentoMeta("META_BUDGET_DIVERGED", "o total diário não corresponde ao plano congelado")
        requires_v2 = (budget["scope"] != "ABO" or len(budget["entries"]) != 1
                       or budget["entries"][0]["step"] != "adset"
                       or daily_budget_minor is None)
        if requires_v2:
            # The helper and approval migration commit atomically. Probe it
            # before INSERT so an old schema cannot create a partial approval.
            authoritative_budget = await self._rpc("trafego_meta_budget_manifest", {"p_snapshot": dict(plano_congelado)})
            if authoritative_budget != budget:
                raise ErroDeNascimentoMeta("META_BUDGET_DIVERGED", "o cálculo persistente de verba diverge do plano")
        result = await self._rpc("trafego_meta_create_approve", {
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
            "p_asset_supply_receipts": recibos,
            # ⚠️ O PLANO DESPACHÁVEL, CONGELADO. É o que permite criar e
            # reconciliar sem recompilar — sem reler a conta, sem rebaixar
            # bytes do CDN e sem depender de a atestação de direitos ainda estar
            # na validade. Não contém token nem segredo.
            "p_compiled_plan": dict(plano_congelado),
            "p_compiler_version": versao_do_compilador,
            "p_snapshot_sha256": snapshot_sha256,
        })
        if requires_v2 and result.get("budget_manifest") != budget:
            raise ErroDeNascimentoMeta("META_CREATE_SCHEMA_REQUIRED", "a aprovação não confirmou o manifesto de orçamento V2")
        return result

    async def manifesto(self, approval_id: str) -> Mapping[str, Any]:
        """A aprovação inteira, do lado do servidor.

        Diferente de `recibo`, que é a projeção sanitizada para o navegador,
        este manifesto carrega o pedido do operador e o `step_ref` de cada
        passo. É o que permite a rota de criação receber apenas o
        `approval_id` e reconstruir o plano sem confiar no cliente.

        ⚠️ E ele carrega o `external_object_id` RESOLVIDO de cada passo fechado
        — só aqui, nunca no recibo. Sem esse campo a recuperação só consegue
        reconstruir identidade por NOME, e esta mesma lane já mediu o preço
        disso: a conta pode ter um homônimo da semana passada, e adotá-lo
        penduraria o AdSet novo na campanha errada. O id veio da resposta do
        NOSSO POST e foi gravado antes de qualquer outra coisa; procedência
        prova mais que coincidência de nome.
        """
        return await self._rpc(
            "trafego_meta_create_approval_manifest", {"p_approval_id": approval_id})

    async def resolver_ausente(
        self, *, passo_ref: str, codigo: str, idade_minima_s: int = 120,
    ) -> None:
        """P0 nunca converte ausência pós-despacho em licença de reenviar."""
        del passo_ref, codigo, idade_minima_s
        raise ErroDeNascimentoMeta(
            "META_AMBIGUOUS_REQUIRES_MANUAL_ADJUDICATION",
            "a ausência após despacho não prova que nada nasceu; o passo permanece ambíguo",
        )

    async def reclamar_orfao(self, *, passo_ref: str, idade_minima_s: int) -> None:
        """Promove um passo IN_FLIGHT ENVELHECIDO para AMBIGUO.

        ## Por que isto não é um retry disfarçado

        Não é. A promoção NÃO despacha nada e não autoriza nenhum POST: ela só
        torna o passo VISÍVEL para a recuperação por leitura, que é read-only.
        Um passo que ninguém consegue enxergar é pior que um passo ambíguo —
        `F03` mediu o preço: a rota respondia `passos_ambiguos: 0`, resposta
        indistinguível de "nada travado", enquanto o objeto podia existir na
        conta.

        ## Por que a idade NÃO é a cerca

        A idade é ELEGIBILIDADE para investigar, e nunca foi prova de que o
        trabalhador morreu: um processo pausado, uma fila drenando devagar ou um
        GC longo produzem o mesmo sintoma. Tratá-la como prova foi o defeito
        medido — o trabalhador antigo voltava com a resposta velha e fechava o
        passo depois da promoção.

        Quem cerca é a autoridade versionada: esta promoção INCREMENTA
        `claim_generation` e apaga o `claim_token`, e a partir daí nenhuma
        escrita do dono anterior é aceita. O limiar de idade continua existindo
        para não tomar a reivindicação de uma chamada que ainda pode estar
        dentro do próprio timeout, e o banco recusa valores fora da faixa.

        ⚠️ E ela funciona com aprovação EXPIRADA de propósito. Expiração fecha
        novo despacho; ela não pode fechar a leitura do que já foi despachado.
        """
        await self._rpc("trafego_meta_create_reclaim_orphan", {
            "p_step_ref": passo_ref, "p_min_age_seconds": int(idade_minima_s),
        })

    async def registrar_readback(
        self,
        *,
        passo_ref: str,
        evidencia: Mapping[str, Any],
        codigo: str | None = None,
        claim_token: str | None = None,
    ) -> None:
        """Grava o read-back — o que CONFIRMOU e o que divergiu — com horário.

        Antes só a divergência ficava registrada (`readback_error`). Um recibo
        que guarda apenas os fracassos não permite responder "isto foi conferido
        e quando", e a resposta HTTP da UI passava a ser o único lugar onde a
        confirmação existia. Uma mensagem de tela não é evidência durável.

        ⚠️ `claim_token` é o token GIRADO que `fechar_passo` devolveu, e a RPC o
        exige enquanto a reivindicação existir. A recuperação chama sem token —
        ela anota sobre um passo cuja reivindicação já foi encerrada, e a
        própria RPC distingue os dois casos.
        """
        await self._rpc("trafego_meta_create_record_readback", {
            "p_step_ref": passo_ref,
            "p_evidence": dict(evidencia),
            "p_error_code": codigo,
            "p_claim_token": claim_token,
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

    async def buscar_validacao(
        self, *, plano_sha256: str, ator: str, janela_da_validacao_s: int,
    ) -> Mapping[str, Any] | None:
        """Read-only evidence for one exact plan AND actor; never launch authority.

        The original ledger grants service_role SELECT. Do not reuse _rpc:
        looking at evidence must not depend on enabling ledger writes.
        """
        if (not re.fullmatch(r"[a-f0-9]{64}", plano_sha256)
                or not isinstance(ator, str) or not 1 <= len(ator.strip()) <= 200
                or not 1 <= janela_da_validacao_s <= 3600):
            raise ErroDeNascimentoMeta("META_VALIDATION_LOOKUP_INVALID", "consulta de validação inválida")
        if not self._servico.enabled or self._servico.base.rstrip("/") != "https://database.agenciavolc.com.br":
            raise ErroDeNascimentoMeta("META_CREATE_LEDGER_UNAVAILABLE", "o Supabase operacional não está disponível")
        columns = ("validation_id,plan_sha256,actor_id,coverage,steps_validated,steps_pending,"
                   "operations_total,objects_created,accepted,validated_at")
        try:
            rows = await self._servico.select("trafego_meta_validation_receipt", {
                "select": columns, "plan_sha256": f"eq.{plano_sha256}",
                "actor_id": f"eq.{ator}", "accepted": "eq.true",
                "order": "validated_at.desc", "limit": 1,
            })
        except (httpx.HTTPError, ValueError):
            raise ErroDeNascimentoMeta("META_VALIDATION_RECEIPT_LOOKUP_UNAVAILABLE", "não foi possível consultar a prova durável") from None
        if not rows:
            return None
        if not isinstance(rows, list):
            raise ErroDeNascimentoMeta("META_VALIDATION_RECEIPT_INVALID", "resposta de validação inválida")
        row = rows[0]
        # Defense in depth: a bad server/proxy response must not cross owners.
        if (not isinstance(row, Mapping) or any(key not in row for key in columns.split(","))
                or row.get("plan_sha256") != plano_sha256
                or row.get("actor_id") != ator or row.get("accepted") is not True
                or row.get("objects_created") != 0
                or row.get("coverage") != "INDEPENDENT_ROOTS_ONLY"):
            raise ErroDeNascimentoMeta("META_VALIDATION_RECEIPT_INVALID", "a prova recebida não corresponde à consulta")
        try:
            validated_at = datetime.fromisoformat(str(row["validated_at"]).replace("Z", "+00:00"))
            if validated_at.tzinfo is None:
                raise ValueError("timestamp sem fuso")
            age = (datetime.now(timezone.utc) - validated_at).total_seconds()
        except (KeyError, ValueError, TypeError):
            raise ErroDeNascimentoMeta("META_VALIDATION_RECEIPT_INVALID", "a prova não informa uma data verificável") from None
        if age < 0 or age > janela_da_validacao_s:
            raise ErroDeNascimentoMeta("META_VALIDATION_RECEIPT_STALE", "valide novamente o plano atual; a prova está fora da janela de validade")
        return {key: row[key] for key in columns.split(",") if key != "actor_id"} | {"idade_s": int(age)}

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
            claim_token=(str(resposta["claim_token"])
                         if resposta.get("claim_token") is not None else None),
        )

    async def fechar_passo(
        self, *, passo_ref: str, id_externo: str, claim_token: str,
    ) -> str | None:
        """Fecha o passo com a autoridade vigente e devolve o token GIRADO.

        ⚠️ O giro fecha a terceira janela. Fechar é uma conclusão; o read-back
        que vem depois é outro ato, sobre um passo que já existe. Se o token
        continuasse o mesmo, uma anotação de leitura atrasada — emitida com a
        autoridade do despacho — poderia pousar sobre uma conclusão mais nova.
        Só quem recebeu ESTA resposta consegue anotar a leitura deste
        fechamento.
        """
        resposta = await self._rpc("trafego_meta_create_close_step", {
            "p_step_ref": passo_ref,
            "p_external_object_id": id_externo,
            "p_claim_token": claim_token,
        })
        girado = resposta.get("claim_token")
        return str(girado) if girado is not None else None

    async def marcar_ambiguo(self, *, passo_ref: str, claim_token: str) -> None:
        await self._rpc("trafego_meta_create_mark_ambiguous", {
            "p_step_ref": passo_ref, "p_claim_token": claim_token,
        })

    async def falhar_passo(
        self, *, passo_ref: str, codigo: str, claim_token: str,
    ) -> None:
        await self._rpc("trafego_meta_create_fail_step", {
            "p_step_ref": passo_ref,
            "p_error_code": codigo,
            "p_claim_token": claim_token,
        })

    async def registrar_despacho_cercado(
        self, *, passo_ref: str, claim_token: str, id_externo: str,
    ) -> Mapping[str, Any]:
        """Grava o id que um trabalhador CERCADO já viu nascer.

        ⚠️ NENHUM BANCO CANCELA UMA REQUISIÇÃO JÁ ENVIADA. Quando a
        reivindicação troca de mãos enquanto o POST está no ar, o trabalhador
        antigo volta com um id REAL e sem autoridade nenhuma. As duas saídas
        erradas são simétricas: deixá-lo concluir sobrescreveria uma conclusão
        mais nova; jogar o id fora perderia a única prova de que o objeto pode
        existir na conta.

        Esta é a terceira saída. O id entra como OBSERVAÇÃO — ao lado da
        identidade concluída, nunca no lugar dela — e o passo fica visível para
        a recuperação por leitura, que é quem decide.
        """
        return await self._rpc("trafego_meta_create_record_fenced_dispatch", {
            "p_step_ref": passo_ref,
            "p_claim_token": claim_token,
            "p_external_object_id": id_externo,
        })

    async def concluir_por_recuperacao(
        self,
        *,
        passo_ref: str,
        id_externo: str,
        evidencia: Mapping[str, Any] | None = None,
        codigo: str | None = None,
    ) -> Mapping[str, Any]:
        """Fecha um passo pela LEITURA, gravando a evidência no mesmo ato.

        A recuperação não tem token de despacho — ela nunca despachou. A
        autoridade dela é outra: ela LEU o objeto e provou o que o despacho não
        conseguiu declarar. Por isso esta RPC supera qualquer reivindicação
        aberta, e por isso ela nunca escreve FAILED: ausência depois do despacho
        continua não provando inexistência.
        """
        return await self._rpc("trafego_meta_create_conclude_by_recovery", {
            "p_step_ref": passo_ref,
            "p_external_object_id": id_externo,
            "p_evidence": dict(evidencia) if evidencia is not None else None,
            "p_error_code": codigo,
        })

    async def recibo(self, approval_id: str) -> Mapping[str, Any]:
        return await self._rpc(
            "trafego_meta_create_receipt", {"p_approval_id": approval_id})
