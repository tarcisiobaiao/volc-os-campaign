"""Persistência confinada por owner_id; service role nunca decide autorização."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.supabase_service import SupabaseService


class NaoEncontrado(LookupError):
    pass


class RepositorioAgenteCriativo:
    def __init__(self, supabase: SupabaseService):
        if not supabase.enabled:
            raise RuntimeError("banco do Assistente de Criativos não configurado")
        self.db = supabase

    async def criar_operacao(self, row: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("criativo_agente_operacao", [row])
        if not rows:
            raise RuntimeError("o banco não devolveu a operação criada")
        return rows[0]

    async def obter_operacao(self, project_ref: str, owner_id: str) -> dict[str, Any]:
        rows = await self.db.select(
            "criativo_agente_operacao",
            {
                "project_ref": f"eq.{project_ref}",
                "owner_id": f"eq.{owner_id}",
                "limit": 1,
            },
        )
        if not rows:
            raise NaoEncontrado(project_ref)
        return rows[0]

    async def criar_run(self, row: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("criativo_agente_run", [row])
        if not rows:
            raise RuntimeError("o banco não devolveu a run criada")
        return rows[0]

    async def concluir_run(
        self,
        run_ref: str,
        owner_id: str,
        *,
        output: dict[str, Any],
        model: str,
        tentativas: int,
        request_sha256: str,
        knowledge_sha256: str,
    ) -> dict[str, Any]:
        # `status=eq.RUNNING` no filtro é o que impede uma segunda execução de
        # sobrescrever um lote já concluído. Sem ele, um retry tardio — ou uma
        # aba reaberta — trocaria a saída que o operador já aprovou por outra,
        # e as decisões apontariam para um snapshot que não existe mais.
        rows = await self.db.patch(
            "criativo_agente_run",
            {
                "run_ref": f"eq.{run_ref}",
                "owner_id": f"eq.{owner_id}",
                "status": "eq.RUNNING",
            },
            {
                "status": "COMPLETED",
                "output": output,
                "model": model,
                "tentativas": tentativas,
                "request_sha256": request_sha256,
                "knowledge_sha256": knowledge_sha256,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            },
        )
        if not rows:
            raise NaoEncontrado(run_ref)
        await self.db.patch(
            "criativo_agente_operacao",
            {
                "project_ref": f"eq.{rows[0]['project_ref']}",
                "owner_id": f"eq.{owner_id}",
            },
            {
                "status": "READY_FOR_REVIEW",
                "latest_run_ref": run_ref,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return rows[0]

    async def falhar_run(
        self, run_ref: str, owner_id: str, *, error: dict[str, Any]
    ) -> None:
        rows = await self.db.patch(
            "criativo_agente_run",
            {"run_ref": f"eq.{run_ref}", "owner_id": f"eq.{owner_id}"},
            {
                "status": "FAILED",
                "error": error,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if rows:
            await self.db.patch(
                "criativo_agente_operacao",
                {
                    "project_ref": f"eq.{rows[0]['project_ref']}",
                    "owner_id": f"eq.{owner_id}",
                },
                {
                    "status": "FAILED",
                    "latest_run_ref": run_ref,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    async def obter_run(self, run_ref: str, owner_id: str) -> dict[str, Any]:
        rows = await self.db.select(
            "criativo_agente_run",
            {"run_ref": f"eq.{run_ref}", "owner_id": f"eq.{owner_id}", "limit": 1},
        )
        if not rows:
            raise NaoEncontrado(run_ref)
        return rows[0]

    async def listar_runs(self, project_ref: str, owner_id: str) -> list[dict[str, Any]]:
        return await self.db.select(
            "criativo_agente_run",
            {
                "project_ref": f"eq.{project_ref}",
                "owner_id": f"eq.{owner_id}",
                "order": "created_at.desc",
                "limit": 100,
            },
        )
    async def listar_operacoes(
        self, owner_id: str, *, limite: int = 20, offset: int = 0
    ) -> list[dict[str, Any]]:
        """A listagem que faltava — sem ela não existe histórico nem retomada.

        Ordena por `updated_at` e não por `created_at` porque o operador procura
        "o que eu estava mexendo", não "o que eu abri primeiro". Uma operação de
        três semanas atrás que recebeu refinamento hoje é a mais relevante da
        lista, e ordenar pela criação a enterraria.

        Pagina por `offset` porque a tabela é pequena por dono e a alternativa
        (keyset) exigiria expor um cursor opaco na URL sem ganho medido aqui.
        """
        return await self.db.select(
            "criativo_agente_operacao",
            {
                "owner_id": f"eq.{owner_id}",
                "order": "updated_at.desc",
                "limit": limite,
                "offset": offset,
            },
        )

    async def reivindicar_run(self, run_ref: str, owner_id: str) -> dict[str, Any] | None:
        """Toma a run para execução, ou devolve `None` se outro já a tomou.

        Este é o `compare-and-set` que separa criar de executar sem introduzir
        fila nova: o filtro `status=eq.QUEUED` viaja no PRÓPRIO PATCH, então
        quem perde a corrida recebe zero linhas do banco em vez de descobrir o
        conflito depois de já ter chamado — e pago — o modelo.

        Um `select` seguido de `patch` teria a janela entre os dois; aqui não
        existe janela, porque o banco resolve a condição e a escrita no mesmo
        comando.
        """
        rows = await self.db.patch(
            "criativo_agente_run",
            {
                "run_ref": f"eq.{run_ref}",
                "owner_id": f"eq.{owner_id}",
                "status": "eq.QUEUED",
            },
            {
                "status": "RUNNING",
                "claimed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return rows[0] if rows else None

    async def reivindicar_run_abandonada(
        self, run_ref: str, owner_id: str, *, lease_s: int
    ) -> dict[str, Any] | None:
        """Retoma uma run que ficou `RUNNING` sem ninguém do outro lado.

        O processo que reivindicou pode ter morrido — deploy, timeout de
        plataforma, aba fechada no meio. Sem esta porta a run fica `RUNNING`
        para sempre e a operação inteira trava: o operador vê "rodando", o
        modelo nunca foi chamado, e não há botão que resolva.

        O filtro `claimed_at=lt.<corte>` é o que torna a retomada segura: só sai
        da fila quem está parado há mais que o lease, então dois processos
        saudáveis nunca disputam a mesma run.
        """
        corte = datetime.now(timezone.utc) - timedelta(seconds=lease_s)
        rows = await self.db.patch(
            "criativo_agente_run",
            {
                "run_ref": f"eq.{run_ref}",
                "owner_id": f"eq.{owner_id}",
                "status": "eq.RUNNING",
                "claimed_at": f"lt.{corte.isoformat()}",
            },
            {"claimed_at": datetime.now(timezone.utc).isoformat()},
        )
        return rows[0] if rows else None

    async def devolver_run_para_fila(self, run_ref: str, owner_id: str) -> None:
        """Desfaz o claim quando a execução nem chegou a começar.

        Sem isto, uma indisponibilidade de modelo detectada DEPOIS do claim
        deixaria a run presa em `RUNNING` para sempre — visível ao operador como
        "rodando", que é a mentira mais cara desta tela.
        """
        await self.db.patch(
            "criativo_agente_run",
            {
                "run_ref": f"eq.{run_ref}",
                "owner_id": f"eq.{owner_id}",
                "status": "eq.RUNNING",
            },
            {"status": "QUEUED", "claimed_at": None},
        )

    async def registrar_decisao(self, row: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("criativo_agente_decisao", [row])
        if not rows:
            raise RuntimeError("o banco não devolveu a decisão criada")
        return rows[0]

    async def registrar_ponte(self, row: dict[str, Any]) -> dict[str, Any]:
        """Grava de qual peça aprovada saiu um job de mídia.

        Append-only por construção: não existe método de update aqui, e o grant
        da v11_07 também não dá UPDATE a ninguém. Procedência que se reescreve
        não é procedência.
        """
        rows = await self.db.insert("criativo_agente_peca_job", [row])
        if not rows:
            raise RuntimeError("o banco não devolveu a ponte criada")
        return rows[0]

    async def listar_pontes(self, project_ref: str, owner_id: str) -> list[dict[str, Any]]:
        return await self.db.select(
            "criativo_agente_peca_job",
            {
                "project_ref": f"eq.{project_ref}",
                "owner_id": f"eq.{owner_id}",
                "order": "created_at.desc",
                "limit": 200,
            },
        )

    async def ponte_por_peca(
        self, run_ref: str, creative_ref: str, owner_id: str
    ) -> dict[str, Any] | None:
        rows = await self.db.select(
            "criativo_agente_peca_job",
            {
                "run_ref": f"eq.{run_ref}",
                "creative_ref": f"eq.{creative_ref}",
                "owner_id": f"eq.{owner_id}",
                "limit": 1,
            },
        )
        return rows[0] if rows else None

    async def listar_decisoes(self, project_ref: str, owner_id: str) -> list[dict[str, Any]]:
        return await self.db.select(
            "criativo_agente_decisao",
            {
                "project_ref": f"eq.{project_ref}",
                "owner_id": f"eq.{owner_id}",
                "order": "created_at.asc",
                "limit": 1000,
            },
        )

    # ── Anexos do operador ───────────────────────────────────────────────────

    async def registrar_anexo(self, row: dict[str, Any]) -> dict[str, Any]:
        """Grava a fotografia normalizada. Sem consentimento o banco recusa.

        A conferência do consentimento é CHECK de tabela e não `if` de Python:
        uma fotografia de pessoa real armazenada sem declaração é um problema no
        instante em que ela é gravada, e um `if` some quando alguém acrescenta
        uma rota nova.
        """
        rows = await self.db.insert("criativo_agente_anexo", [row])
        if not rows:
            raise RuntimeError("o banco não devolveu o anexo criado")
        return rows[0]

    async def obter_anexo(
        self, anexo_ref: str, owner_id: str
    ) -> dict[str, Any] | None:
        """O anexo DO DONO. Ref opaca não é autorização.

        `owner_id` entra na consulta e não numa checagem posterior: a diferença
        aparece no dia em que alguém esquecer o `if`, e não aparece nunca quando
        o filtro está no `where`.
        """
        rows = await self.db.select(
            "criativo_agente_anexo",
            {
                "anexo_ref": f"eq.{anexo_ref}",
                "owner_id": f"eq.{owner_id}",
                "removido_em": "is.null",
                "limit": 1,
            },
        )
        return rows[0] if rows else None

    async def listar_anexos(
        self, project_ref: str, owner_id: str
    ) -> list[dict[str, Any]]:
        return await self.db.select(
            "criativo_agente_anexo",
            {
                "project_ref": f"eq.{project_ref}",
                "owner_id": f"eq.{owner_id}",
                "removido_em": "is.null",
                "order": "criado_em.desc",
                "limit": 20,
            },
        )

    async def remover_anexo(self, anexo_ref: str, owner_id: str, *, em: str) -> bool:
        """Carimba `removido_em`. NÃO apaga a linha.

        Apagar quebraria a procedência de um job que já usou esta foto: a peça
        continuaria existindo e a pergunta "de qual imagem ela saiu?" perderia a
        resposta. Trocar a foto é um ato do operador; apagar a história não é.
        """
        rows = await self.db.patch(
            "criativo_agente_anexo",
            {
                "anexo_ref": f"eq.{anexo_ref}",
                "owner_id": f"eq.{owner_id}",
                "removido_em": "is.null",
            },
            {"removido_em": em},
        )
        return bool(rows)
