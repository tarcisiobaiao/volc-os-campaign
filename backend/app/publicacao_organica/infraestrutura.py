"""O adapter do Supabase — e o filtro que decide o que uma falha pode dizer.

Mesma disciplina de `app/asset_vault/infraestrutura.py`, e pelo mesmo motivo
medido la em 01/09/2026: quando uma CHECK recusa a linha, o Postgres anexa

    DETAIL:  Failing row contains (…, 'falha: Authorization: xoxb-…', …)

— a LINHA INTEIRA, com o valor recusado. Repassar o corpo de erro do PostgREST
para o browser faria a recusa vazar exatamente o que ela existe para conter.

Tres camadas, na mesma ordem:
  1. `details` e `hint` do PostgREST NUNCA saem daqui — nem sao lidos;
  2. `message` sai apenas quando casa uma das frases que ESTE projeto escreveu;
  3. uma varredura final descarta qualquer mensagem com marcador de linha crua
     ou formato de credencial, mesmo que tenha passado por (2).

⚠️ NAO existe caminho de escrita direta em tabela aqui, e nao e por convencao: a
v14_01 revoga ALL de `service_role` nas cinco tabelas. Um `POST /rest/v1/
publicacao_organica_job` responderia 403 — e essa e a intencao.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.publicacao_organica import dominio as dom
from app.publicacao_organica.aplicacao import (
    Autor,
    OperacaoRecusada,
    PublicacaoIndisponivel,
)

log = logging.getLogger("volc.publicacao_organica.infra")

#: SQLSTATEs que as funcoes governadas levantam de proposito, com o status HTTP
#: que cada um significa para quem chamou. Ver a v14_01.
_STATUS_POR_SQLSTATE: dict[str, tuple[int, str]] = {
    "22023": (400, "pedido_invalido"),          # invalid_parameter_value
    "23001": (400, "campo_proibido"),           # restrict_violation / append-only
    "23514": (409, "regra_da_publicacao"),      # check_violation
    "23503": (409, "referencia_inexistente"),   # foreign_key_violation
    "23505": (409, "conflito_de_chave"),        # unique_violation
    "23502": (400, "campo_obrigatorio"),        # not_null_violation
    "40001": (409, "lease_vencido"),            # serialization_failure (fencing)
    "P0002": (404, "nao_encontrado"),           # no_data_found
    "42501": (403, "de_outro_dono"),            # insufficient_privilege
}

_FRASE_FECHADA: dict[str, str] = {
    "pedido_invalido": "A publicacao recusou este pedido: algum campo nao respeita o contrato.",
    "campo_proibido": "A publicacao recusou este pedido por conter um campo que ela nunca guarda.",
    "regra_da_publicacao": "A publicacao recusou este pedido por violar uma regra do fluxo.",
    "referencia_inexistente": "O pedido aponta para uma peca, aprovacao ou destino que nao existe.",
    "conflito_de_chave": "Ja existe uma operacao em conflito com este pedido.",
    "campo_obrigatorio": "Falta um campo obrigatorio neste pedido.",
    "lease_vencido": "Outro consumidor assumiu este job; a sua tentativa nao foi aplicada.",
    "nao_encontrado": "Esse job nao existe.",
    "de_outro_dono": "Este item pertence a outro dono.",
    "desconhecido": "A publicacao nao conseguiu concluir esta operacao.",
}

#: As frases que ESTE projeto escreveu, e por isso auditou. Todas citam campo,
#: caminho ou forma esperada — nenhuma repete um valor recebido.
#: ⚠️ "esta chave de idempotencia ja foi usada" e a frase da v14_01, e ela NAO
#: contem a chave: a gramatica da chave aceita uma senha inteira.
_FRASES_PROPRIAS: tuple[str, ...] = (
    "publicacao organica:",
    "esta chave de idempotencia ja foi usada",
    "e append-only:",
    "campo proibido no Cofre:",
    "recebeu campo(s) que este contrato nao conhece:",
)

_MARCADOR_DE_VAZAMENTO = re.compile(
    r"Failing row contains"
    r"|DETAIL:"
    r"|Key \("
    r"|-----BEGIN"
    r"|eyJ[A-Za-z0-9_-]{20,}\."
    r"|\bop://"
    r"|\bauthorization\b\s*[:=]",
    re.IGNORECASE,
)


def _mensagem_segura(bruta: str | None, codigo: str) -> str:
    if not bruta:
        return _FRASE_FECHADA.get(codigo, _FRASE_FECHADA["desconhecido"])
    uma_linha = " ".join(bruta.split())
    if _MARCADOR_DE_VAZAMENTO.search(uma_linha):
        log.warning("publicacao: mensagem do banco descartada por marcador de vazamento (codigo=%s)", codigo)
        return _FRASE_FECHADA.get(codigo, _FRASE_FECHADA["desconhecido"])
    if any(frase in uma_linha for frase in _FRASES_PROPRIAS):
        return uma_linha[:400]
    return _FRASE_FECHADA.get(codigo, _FRASE_FECHADA["desconhecido"])


class RepositorioSupabase:
    """Fala com as funcoes governadas por `POST /rest/v1/rpc/<funcao>`."""

    def __init__(self, supabase: Any, timeout_s: float = 15.0) -> None:
        self._supa = supabase
        self._timeout = timeout_s

    @property
    def configurado(self) -> bool:
        return bool(getattr(self._supa, "enabled", False))

    # -- ida ao banco -------------------------------------------------------

    async def _rpc(self, funcao: str, argumentos: dict[str, Any]) -> Any:
        if not self.configurado:
            raise PublicacaoIndisponivel("Supabase nao configurado neste ambiente.")
        try:
            return await self._supa.rpc(funcao, argumentos)
        except httpx.HTTPStatusError as exc:
            raise self._traduzir(exc) from exc
        except httpx.HTTPError as exc:
            log.warning("publicacao: falha de rede em %s: %s", funcao, type(exc).__name__)
            raise PublicacaoIndisponivel(
                "Nao foi possivel falar com o banco da publicacao agora.") from exc
        except ValueError as exc:
            log.warning("publicacao: resposta ilegivel em %s", funcao)
            raise PublicacaoIndisponivel(
                "O banco respondeu em um formato inesperado.") from exc

    def _traduzir(self, exc: httpx.HTTPStatusError) -> Exception:
        resposta = exc.response
        corpo: dict[str, Any] = {}
        try:
            lido = resposta.json()
            if isinstance(lido, dict):
                corpo = lido
        except Exception:  # noqa: BLE001 — corpo vazio ou HTML de proxy
            corpo = {}

        sqlstate = str(corpo.get("code") or "")
        status, codigo = _STATUS_POR_SQLSTATE.get(sqlstate, (0, ""))

        if not status:
            if resposta.status_code in (401, 403):
                return PublicacaoIndisponivel(
                    "O banco recusou a autorizacao desta operacao.")
            if resposta.status_code == 404:
                # Funcao ausente: a migration nao foi aplicada. Dizer O QUE
                # faltou evita que o proximo procure rede em vez de schema.
                log.error("publicacao: RPC ausente no banco — a v14_01 nao foi aplicada")
                return PublicacaoIndisponivel(
                    "A publicacao organica ainda nao existe neste banco. "
                    "A migration v14_01 nao foi aplicada.")
            if 500 <= resposta.status_code < 600:
                return PublicacaoIndisponivel("O banco nao respondeu a esta operacao.")
            status, codigo = 400, "desconhecido"

        # ⚠️ Somente `message`. `details` e `hint` sao os campos que carregam a
        # linha recusada, e eles morrem aqui — nem sequer sao lidos.
        return OperacaoRecusada(
            _mensagem_segura(corpo.get("message"), codigo), codigo=codigo, status=status)

    # -- forma da resposta --------------------------------------------------

    @staticmethod
    def _objeto(resposta: Any, o_que: str) -> dict[str, Any]:
        """Uma resposta que nao e objeto NAO vira `{}`: vira indisponibilidade.

        Aceitar forma desconhecida como vazio e como um painel aprende a
        inventar "nenhum job" a partir de um proxy mal configurado.
        """
        if isinstance(resposta, list):
            resposta = resposta[0] if resposta else None
        if isinstance(resposta, dict):
            return resposta
        log.warning("publicacao: %s veio em forma inesperada: %s", o_que, type(resposta).__name__)
        raise PublicacaoIndisponivel(
            "O banco respondeu em um formato que esta API nao reconhece.")

    @staticmethod
    def _lista(bruto: Any, o_que: str) -> list[dict[str, Any]]:
        """Lista com elemento estranho e resposta QUEBRADA, nao lista curta.

        ⚠️ Um filtro `[i for i in bruto if isinstance(i, dict)]` devolveria `[]`
        para `[None]` — a rota responderia 200 com lista vazia sobre um banco que
        respondeu errado. Foi o defeito medido no Cofre em 01/09/2026.
        """
        if isinstance(bruto, list) and len(bruto) == 1 and isinstance(bruto[0], list):
            bruto = bruto[0]
        if bruto is None:
            bruto = []
        if not isinstance(bruto, list):
            raise PublicacaoIndisponivel(f"O banco respondeu {o_que} em forma inesperada.")
        if any(not isinstance(i, dict) for i in bruto):
            log.warning("publicacao: %s trouxe elemento que nao e objeto", o_que)
            raise PublicacaoIndisponivel(f"O banco respondeu {o_que} em forma inesperada.")
        return bruto

    def _recibo(self, bruto: Any, o_que: str) -> dict[str, Any]:
        recibo = self._objeto(bruto, o_que)
        # Ultima peneira antes de o recibo virar resposta HTTP. As funcoes
        # governadas nao colocam material de credencial em recibo nenhum — esta
        # linha e o que garante que continue assim quando alguem adicionar campo.
        dom.recusar_chave_sensivel(recibo, "recibo")
        return recibo

    # -- as operacoes -------------------------------------------------------

    async def registrar_destino(self, payload: dict[str, Any], chave: str,
                                autor: Autor) -> dict[str, Any]:
        return self._recibo(await self._rpc("publicacao_organica_registrar_destino", {
            "p_payload": payload, "p_chave": chave,
            "p_autor_sub": autor.sub, "p_autor_email": autor.email,
        }), "recibo de destino")

    async def criar_job(self, payload: dict[str, Any], chave: str,
                        autor: Autor) -> dict[str, Any]:
        return self._recibo(await self._rpc("publicacao_organica_criar_job", {
            "p_payload": payload, "p_chave": chave,
            "p_autor_sub": autor.sub, "p_autor_email": autor.email,
        }), "recibo de criacao")

    async def liberar(self, job_id: str, autor: Autor) -> dict[str, Any]:
        return self._recibo(await self._rpc("publicacao_organica_liberar", {
            "p_job_id": job_id, "p_autor_sub": autor.sub,
        }), "recibo de liberacao")

    async def reivindicar(self, job_id: str, consumidor: str,
                          lease_segundos: int) -> dict[str, Any]:
        return self._objeto(await self._rpc("publicacao_organica_reivindicar", {
            "p_job_id": job_id, "p_consumidor": consumidor,
            "p_lease_segundos": lease_segundos,
        }), "reivindicacao")

    async def concluir_despacho(self, job_id: str, fencing: int, chave: str,
                                desfecho: str, recibo: dict[str, Any],
                                autor: Autor) -> dict[str, Any]:
        return self._recibo(await self._rpc("publicacao_organica_concluir_despacho", {
            "p_job_id": job_id, "p_fencing": fencing, "p_chave": chave,
            "p_desfecho": desfecho, "p_recibo": recibo,
            "p_autor_sub": autor.sub, "p_autor_email": autor.email,
        }), "recibo de despacho")

    async def reconciliar(self, job_id: str, chave: str, observacao: dict[str, Any],
                          autor: Autor) -> dict[str, Any]:
        return self._recibo(await self._rpc("publicacao_organica_reconciliar", {
            "p_job_id": job_id, "p_chave": chave, "p_observacao": observacao,
            "p_autor_sub": autor.sub, "p_autor_email": autor.email,
        }), "recibo de reconciliacao")

    async def cancelar(self, job_id: str, motivo: str, autor: Autor) -> dict[str, Any]:
        return self._recibo(await self._rpc("publicacao_organica_cancelar", {
            "p_job_id": job_id, "p_motivo": motivo, "p_autor_sub": autor.sub,
        }), "recibo de cancelamento")

    async def listar_destinos(self, owner_sub: str) -> list[dict[str, Any]]:
        return self._lista(
            await self._rpc("publicacao_organica_listar_destinos", {"p_owner_sub": owner_sub}),
            "destinos")

    async def listar_jobs(self, owner_sub: str, estado: str | None,
                          limite: int) -> list[dict[str, Any]]:
        return self._lista(await self._rpc("publicacao_organica_listar_jobs", {
            "p_owner_sub": owner_sub, "p_estado": estado, "p_limite": limite,
        }), "jobs")

    async def detalhar_job(self, job_id: str, owner_sub: str) -> dict[str, Any] | None:
        bruto = await self._rpc("publicacao_organica_detalhar_job", {
            "p_job_id": job_id, "p_owner_sub": owner_sub,
        })
        if isinstance(bruto, list):
            bruto = bruto[0] if bruto else None
        if bruto is None:
            # Job inexistente OU de outro dono — e a mesma resposta de proposito.
            return None
        if not isinstance(bruto, dict):
            raise PublicacaoIndisponivel(
                "O banco respondeu em um formato que esta API nao reconhece.")
        return bruto

    async def fila(self, limite: int) -> list[dict[str, Any]]:
        return self._lista(
            await self._rpc("publicacao_organica_fila", {"p_limite": limite}), "fila")
