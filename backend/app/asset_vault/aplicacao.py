"""Casos de uso do Cofre e a PORTA que eles exigem do mundo externo.

Nada aqui sabe o que e FastAPI, httpx ou PostgREST. O que este arquivo sabe e
que existe um repositorio capaz de listar, detalhar e executar operacoes
governadas — e que qualquer falha dele e uma FALHA, nunca uma lista vazia.

## A distincao que este arquivo existe para preservar

Um painel que responde `[]` quando o banco caiu e pior do que um painel que
responde erro: ele afirma "voce nao tem ativos" com a mesma cara com que
afirmaria "voce tem trinta". `CofreIndisponivel` sobe ate a rota e vira 503 —
e a tela tem um estado proprio para isso, diferente do estado vazio.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.asset_vault import dominio as dom


class CofreIndisponivel(RuntimeError):
    """O banco nao respondeu, ou respondeu o que nao da para interpretar.

    NUNCA vira lista vazia. Ver o docstring do modulo.
    """


class OperacaoRecusada(ValueError):
    """O banco recusou por regra de dominio. A mensagem ja esta sanitizada."""

    def __init__(self, mensagem: str, codigo: str = "operacao_recusada", status: int = 400):
        super().__init__(mensagem)
        self.codigo = codigo
        self.status = status


class AtivoNaoEncontrado(LookupError):
    pass


class RepositorioDoCofre(Protocol):
    """A porta. `infraestrutura.RepositorioSupabase` e a unica implementacao real."""

    @property
    def configurado(self) -> bool: ...

    async def listar(self, **filtros: Any) -> dict[str, Any]: ...

    async def detalhar(self, ativo_id: str) -> dict[str, Any] | None: ...

    async def engines(self) -> list[dict[str, Any]]: ...

    async def postura_credencial(self, ativo_id: str) -> list[dict[str, Any]]: ...

    async def executar(self, funcao: str, argumentos: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Autor:
    """Quem esta operando. Vem de `Identidade`, e viaja para a trilha do banco."""

    sub: str
    email: str


class CasosDeUso:
    """Os oito atos do Cofre, com a validacao acontecendo ANTES da rede."""

    def __init__(self, repositorio: RepositorioDoCofre):
        self._repo = repositorio

    # ── leitura ──────────────────────────────────────────────────────────────

    async def inventario(
        self,
        *,
        cluster: str | None = None,
        kind: str | None = None,
        estado: str | None = None,
        busca: str | None = None,
        incluir_aposentados: bool = False,
    ) -> dict[str, Any]:
        if cluster is not None and cluster not in dom.GAVETAS:
            raise dom.PayloadRecusado(f"gaveta desconhecida: {cluster}")
        if kind is not None and kind not in dom.TIPO_DA_GAVETA:
            raise dom.PayloadRecusado(f"tipo desconhecido: {kind}")
        if estado is not None and estado not in dom.ESTADOS:
            raise dom.PayloadRecusado(f"estado desconhecido: {estado}")
        return await self._repo.listar(
            p_cluster=cluster, p_kind=kind, p_estado=estado,
            p_busca=(busca or None), p_incluir_aposentados=incluir_aposentados,
        )

    async def detalhe(self, ativo_id: str) -> dict[str, Any]:
        dom.exigir_id_de_ativo(ativo_id)
        achado = await self._repo.detalhar(ativo_id)
        if achado is None:
            raise AtivoNaoEncontrado(ativo_id)
        return achado

    async def engines(self) -> list[dict[str, Any]]:
        return await self._repo.engines()

    async def postura(self, ativo_id: str) -> list[dict[str, Any]]:
        dom.exigir_id_de_ativo(ativo_id)
        return await self._repo.postura_credencial(ativo_id)

    async def handoff(self, ativo_id: str) -> dict[str, Any]:
        """Responde o que o proximo componente precisa saber — sem publicar nada.

        Item G da missao, e a fronteira dele importa: esta funcao RESPONDE
        ("quais engines existem, o que produzem, quem recebe a peca, qual
        referencia sera resolvida, qual componente vem depois") e NAO EXECUTA
        ("cria o job, abre o navegador, publica"). O broker do 1Password->AdsPower
        (P03-T11) e a porta do Postiz (P12-T08/T09) sao outras missoes, e o
        contrato entre elas esta em
        `docs/architecture/COFRE-HANDOFF-PRODUCAO-E-PUBLICACAO.md`.

        ⚠️ `referencia_de_acesso` traz provider e NOME LOGICO, nunca o
        localizador. Quem resolve o endereco e o broker, no host isolado, com o
        papel `postgres` — nao esta API e nao o navegador. Um handoff que ja
        viesse com o endereco resolvido transformaria esta rota na porta do
        cofre, que e exatamente o que o ADR recusa.
        """
        detalhe = await self.detalhe(ativo_id)
        credenciais = detalhe.get("credencial") or []
        engines = await self._repo.engines()

        # Um perfil de navegador RELACIONADO e o que o broker vai abrir. Sem ele,
        # o handoff diz que falta — nao inventa um perfil padrao.
        relacoes = detalhe.get("relacoes") or []
        perfis = [r for r in relacoes if str(r.get("tipo")) == "authenticates_through"]

        bloqueios: list[str] = []
        if not credenciais:
            bloqueios.append(
                "nenhuma referencia de acesso registrada: o broker nao teria o que resolver")
        if not perfis:
            bloqueios.append(
                "nenhum perfil de navegador relacionado (authenticates_through): "
                "o QA visual nao saberia qual perfil abrir")
        if detalhe.get("aposentado_em"):
            bloqueios.append("o ativo esta aposentado")
        if not any((c.get("verificacao_estado") == "verified") for c in credenciais):
            bloqueios.append(
                "a referencia de acesso nunca foi verificada com sucesso")

        return {
            "destino": {
                "ativo_id": detalhe.get("ativo_id"),
                "nome": detalhe.get("nome"),
                "kind": detalhe.get("kind"),
                "plataforma": detalhe.get("plataforma"),
                "estado": detalhe.get("estado"),
                "url_publica": detalhe.get("url_publica"),
                "projeto": detalhe.get("projeto"),
                "vertical": detalhe.get("vertical"),
            },
            "referencia_de_acesso": [
                {"provider": c.get("provider"), "nome_logico": c.get("nome_logico"),
                 "estado": c.get("estado"), "verificacao_estado": c.get("verificacao_estado"),
                 "verificado_em": c.get("verificado_em")}
                for c in credenciais
            ],
            "perfis_de_navegador": perfis,
            "engines_disponiveis": [
                {"ativo_id": e.get("ativo_id"), "nome": e.get("nome"),
                 "modalidade": e.get("modalidade"),
                 "estado_operacional": e.get("estado_operacional"),
                 "formatos": e.get("formatos"), "skins": e.get("skins"),
                 "destinos_compativeis": e.get("destinos_compativeis"),
                 "limitacoes": e.get("limitacoes")}
                for e in engines
            ],
            # Nao e uma promessa de que o componente existe: e o nome do que
            # PRECISA existir. Os tres estao em `todo` no Roadmap, e dizer isso
            # aqui evita que alguem chame uma rota que nao nasceu.
            "proximo_componente": {
                "producao_criativa": {"tarefa": "P17", "estado": "fora desta missao"},
                "broker_de_acesso": {"tarefa": "P03-T11", "estado": "todo"},
                "porta_de_publicacao": {"tarefa": "P12-T09", "estado": "todo"},
                "qa_visual": {"tarefa": "P12-T11", "estado": "todo"},
            },
            "pronto_para_handoff": not bloqueios,
            "bloqueios": bloqueios,
        }

    # ── escrita ──────────────────────────────────────────────────────────────

    async def cadastrar(self, payload: dict[str, Any], chave: str, autor: Autor,
                        motivo: str) -> dict[str, Any]:
        dom.exigir_chave_de_idempotencia(chave)
        dom.recusar_chave_sensivel(payload, "ativo")
        return await self._repo.executar("cofre_cadastrar_ativo", {
            "p_payload": payload, "p_chave": chave,
            "p_autor_sub": autor.sub, "p_autor_email": autor.email, "p_motivo": motivo,
        })

    async def revisar(self, ativo_id: str, payload: dict[str, Any], chave: str,
                      autor: Autor, motivo: str) -> dict[str, Any]:
        dom.exigir_id_de_ativo(ativo_id)
        dom.exigir_chave_de_idempotencia(chave)
        dom.recusar_chave_sensivel(payload, "revisao")
        return await self._repo.executar("cofre_revisar_ativo", {
            "p_ativo_id": ativo_id, "p_payload": payload, "p_chave": chave,
            "p_autor_sub": autor.sub, "p_autor_email": autor.email, "p_motivo": motivo,
        })

    async def relacionar(self, payload: dict[str, Any], chave: str, autor: Autor) -> dict[str, Any]:
        dom.exigir_chave_de_idempotencia(chave)
        dom.recusar_chave_sensivel(payload, "relacao")
        return await self._repo.executar("cofre_relacionar", {
            "p_payload": payload, "p_chave": chave,
            "p_autor_sub": autor.sub, "p_autor_email": autor.email,
        })

    async def desfazer_relacao(self, relacao_id: int, motivo: str, chave: str,
                               autor: Autor) -> dict[str, Any]:
        dom.exigir_chave_de_idempotencia(chave)
        return await self._repo.executar("cofre_desfazer_relacao", {
            "p_relacao_id": relacao_id, "p_motivo": motivo, "p_chave": chave,
            "p_autor_sub": autor.sub, "p_autor_email": autor.email,
        })

    async def aposentar(self, ativo_id: str, motivo: str, chave: str, autor: Autor) -> dict[str, Any]:
        dom.exigir_id_de_ativo(ativo_id)
        dom.exigir_chave_de_idempotencia(chave)
        return await self._repo.executar("cofre_aposentar_ativo", {
            "p_ativo_id": ativo_id, "p_motivo": motivo, "p_chave": chave,
            "p_autor_sub": autor.sub, "p_autor_email": autor.email,
        })

    async def reativar(self, ativo_id: str, estado: str, motivo: str, chave: str,
                       autor: Autor) -> dict[str, Any]:
        dom.exigir_id_de_ativo(ativo_id)
        dom.exigir_chave_de_idempotencia(chave)
        if estado == "retired":
            raise dom.PayloadRecusado("reativar exige um estado diferente de retired.")
        return await self._repo.executar("cofre_reativar_ativo", {
            "p_ativo_id": ativo_id, "p_estado": estado, "p_motivo": motivo,
            "p_chave": chave, "p_autor_sub": autor.sub, "p_autor_email": autor.email,
        })

    async def registrar_verificacao(self, payload: dict[str, Any], chave: str,
                                    autor: Autor) -> dict[str, Any]:
        dom.exigir_chave_de_idempotencia(chave)
        dom.recusar_chave_sensivel(payload, "verificacao")
        return await self._repo.executar("cofre_registrar_verificacao", {
            "p_payload": payload, "p_chave": chave,
            "p_autor_sub": autor.sub, "p_autor_email": autor.email,
        })

    async def referenciar_credencial(self, payload: dict[str, Any], chave: str,
                                     autor: Autor) -> dict[str, Any]:
        """A unica porta pela qual um localizador entra no sistema.

        ⚠️ A varredura de chave sensivel roda no payload SEM `localizador`:
        `localizador` esta na lista de proibidas justamente para nao poder
        viajar dentro de nenhum OUTRO documento. Aqui ele e legitimo, e a
        gramatica de `dominio.exigir_localizador` e quem decide se o que chegou
        e endereco ou segredo — recusando sem repetir o valor.
        """
        dom.exigir_chave_de_idempotencia(chave)
        sem_localizador = {k: v for k, v in payload.items() if k != "localizador"}
        dom.recusar_chave_sensivel(sem_localizador, "credencial")
        dom.exigir_localizador(str(payload.get("provider", "")), str(payload.get("localizador", "")))
        return await self._repo.executar("cofre_referenciar_credencial", {
            "p_payload": payload, "p_chave": chave,
            "p_autor_sub": autor.sub, "p_autor_email": autor.email,
        })
