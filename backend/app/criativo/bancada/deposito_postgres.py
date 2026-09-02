"""O deposito de trabalhos em Postgres, contra as tabelas da v11_03.

## O que este adapter NAO faz

Nao reimplementa as guardas. Elas ja existem no banco, em gatilho, e sao a
autoridade: `criativo_render_transicao_valida` recusa transicao proibida, lease
vencido, troca de dono no meio e `rendered` sem recibo COM artefato;
`criativo_render_artefato_imutavel` congela o artefato depois de concluido.

Reimplementar essas regras aqui criaria a terceira maquina de estado do projeto.
O adapter traduz — dataclass para linha, linha para dataclass — e converte o erro
do banco no erro tipado que o chamador ja trata (`TransicaoProibida`,
`LeaseVencido`, `ValueError`). Quando as duas versoes divergirem, quem manda e o
banco, e a suite de contrato acusa.

## Por que `for update skip locked`

E o equivalente exato do `BEGIN IMMEDIATE` do SQLite para este uso: dois
operarios concorrentes nunca reivindicam o mesmo trabalho, e o segundo nao fica
esperando o primeiro — ele pega o proximo. O comentario do deposito SQLite ja
prometia essa equivalencia; aqui ela existe.

## Conexao

Uma conexao por thread, como no SQLite e pela mesma razao: compartilhar conexao
entre threads e o singleton mutavel que este executor existe para nao ter.

⚠️ `psycopg` e importado tarde e de proposito. O caminho serverless (Vercel) NAO
fala Postgres direto — ele fala HTTP com o Supabase — e carregar o driver la
seria peso morto num ambiente com limite de bundle. Quem precisa dele e o worker,
que roda fora do processo web e tem o proprio envelope de dependencia
(`backend/requirements-worker.txt`).
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .contrato import (
    TERMINAIS,
    Encomenda,
    EstadoDoTrabalho,
    SaidaPedida,
    TransicaoProibida,
    chave_de_retomada,
)
from .deposito import LeaseVencido, Trabalho, _caminho_na_mensagem

#: O SQLSTATE que os gatilhos da v11_03 levantam. Todos eles usam
#: `integrity_constraint_violation` (23000) de proposito, para que o chamador
#: distinga guarda de negocio de erro de conexao ou de tipo.
_SQLSTATE_GUARDA = "23000"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class DepositoPostgres:
    """Mesma porta, outro deposito. Sem uma regra de negocio propria."""

    def __init__(self, dsn: str, *, autocommit: bool = True) -> None:
        self.dsn = dsn
        self._autocommit = autocommit
        self._local = threading.local()

    # ── conexao ──────────────────────────────────────────────────────────────

    def _con(self) -> Any:
        con = getattr(self._local, "con", None)
        if con is None or getattr(con, "closed", False):
            import psycopg  # noqa: PLC0415
            from psycopg.rows import dict_row  # noqa: PLC0415

            con = psycopg.connect(self.dsn, autocommit=self._autocommit, row_factory=dict_row)
            self._local.con = con
        return con

    def fechar(self) -> None:
        con = getattr(self._local, "con", None)
        if con is not None and not getattr(con, "closed", False):
            con.close()
        self._local.con = None

    # ── escrita ──────────────────────────────────────────────────────────────

    def enfileirar(
        self,
        encomenda: Encomenda,
        *,
        max_tentativas: int = 3,
        chave: str | None = None,
        retoma_de: str | None = None,
        retomada_n: int = 0,
    ) -> tuple[Trabalho, bool]:
        """Cria, ou devolve o que ja existe com a mesma `(tenant, chave)`.

        ⚠️ `on conflict do nothing` e nao `do update`: a idempotencia devolve o
        trabalho que ja existe, sem tocar nele. Um `do update` reescreveria a
        encomenda de um job em andamento — e o gatilho recusaria, transformando
        um replay legitimo em erro.
        """
        chave = chave or encomenda.chave_de_idempotencia()
        con = self._con()
        with con.cursor() as cur:
            cur.execute(
                "insert into public.criativo_render_job"
                " (id, tenant_id, idempotency_key, estado, encomenda, motor_slug,"
                "  modo_slug, finalidade_slug, seed, max_tentativas, retry_of, retry_n)"
                " values (%s,%s,%s,'queued',%s,%s,%s,%s,%s,%s,%s,%s)"
                " on conflict (tenant_id, idempotency_key) do nothing"
                " returning id",
                (
                    str(uuid.uuid4()),
                    encomenda.tenant_id,
                    chave,
                    json.dumps(_encomenda_para_json(encomenda)),
                    encomenda.motor_slug,
                    encomenda.modo_slug,
                    encomenda.finalidade_slug,
                    encomenda.seed,
                    max_tentativas,
                    retoma_de,
                    retomada_n,
                ),
            )
            criado = cur.fetchone() is not None
        achado = self.por_chave(chave, tenant_id=encomenda.tenant_id)
        assert achado is not None
        return achado, criado

    def reivindicar(self, operario: str, *, lease_s: int = 60) -> Trabalho | None:
        con = self._con()
        with con.transaction(), con.cursor() as cur:
            self._devolver_vencidos(cur)
            self._esgotar_tentativas(cur)
            cur.execute(
                "select id from public.criativo_render_job"
                " where estado='queued' order by criado_em"
                " for update skip locked limit 1"
            )
            linha = cur.fetchone()
            if linha is None:
                return None
            escolhido = linha["id"]
            self._marcar_claim(cur, escolhido, operario, lease_s)
        return self.por_id(str(escolhido))

    def reivindicar_este(
        self, trabalho_id: str, operario: str, *, lease_s: int = 60
    ) -> Trabalho | None:
        con = self._con()
        with con.transaction(), con.cursor() as cur:
            self._devolver_vencidos(cur)
            self._esgotar_tentativas(cur)
            cur.execute(
                "select id, tentativa, max_tentativas from public.criativo_render_job"
                " where id=%s and estado='queued' for update skip locked",
                (trabalho_id,),
            )
            linha = cur.fetchone()
            if linha is None:
                return None
            self._marcar_claim(cur, linha["id"], operario, lease_s)
        return self.por_id(trabalho_id)

    @staticmethod
    def _marcar_claim(cur: Any, job_id: Any, operario: str, lease_s: int) -> None:
        agora = _agora()
        cur.execute(
            "update public.criativo_render_job"
            " set estado='claimed', owner=%s, lease_ate=%s, batimento_em=%s,"
            "     tentativa=tentativa+1, atualizado_em=now()"
            " where id=%s",
            (operario, agora + timedelta(seconds=lease_s), agora, job_id),
        )

    @staticmethod
    def _devolver_vencidos(cur: Any) -> int:
        """Lease vencido volta para a fila. Nao marca falha: um operario que
        morreu nao torna o pedido invalido."""
        cur.execute(
            "update public.criativo_render_job"
            " set estado='queued', owner=null, lease_ate=null, atualizado_em=now()"
            " where estado in ('claimed','running','validating')"
            "   and lease_ate is not null and lease_ate < now()"
        )
        return cur.rowcount or 0

    #: Quem enterra o trabalho esgotado. Nome fixo para aparecer na trilha como
    #: autor — e nao como um operario que nunca existiu.
    RECOLHEDOR = "recolhedor"

    @classmethod
    def _esgotar_tentativas(cls, cur: Any) -> int:
        """Quem ja gastou o teto de tentativas sai da fila como `failed`.

        ⚠️ ACHADO DA SUITE DE CONTRATO. `queued -> failed` NAO existe no mapa de
        transicoes — nem aqui nem no `contrato.py`. O SQLite escapava porque
        `reivindicar` escrevia `estado='failed'` por SQL cru, sem passar por
        `transicionar`: o mapa era desobedecido pelo proprio deposito que o
        define. O Postgres nao deixa, porque a guarda esta em gatilho e nao ha
        por onde escapar.

        O caminho legitimo e `queued -> claimed -> failed`, e ele tambem e mais
        honesto: alguem PEGOU o trabalho para enterra-lo, e a trilha registra os
        dois passos com autor. A tentativa NAO e incrementada — enterrar nao e
        tentar.
        """
        cur.execute(
            "select id from public.criativo_render_job"
            " where estado='queued' and tentativa >= max_tentativas for update"
        )
        alvos = [l["id"] for l in cur.fetchall()]
        for alvo in alvos:
            cur.execute(
                "update public.criativo_render_job"
                " set estado='claimed', owner=%s, lease_ate=now() + interval '60 seconds',"
                "     batimento_em=now(), atualizado_em=now() where id=%s",
                (cls.RECOLHEDOR, alvo),
            )
            cur.execute(
                "update public.criativo_render_job"
                " set estado='failed', owner=null, lease_ate=null,"
                "     falha_codigo='tentativas_esgotadas',"
                "     falha_mensagem='o trabalho foi tentado o maximo de vezes',"
                "     falha_permanente=true, terminado_em=now(), atualizado_em=now()"
                " where id=%s",
                (alvo,),
            )
        return len(alvos)

    def devolver_vencidos(self) -> int:
        con = self._con()
        with con.transaction(), con.cursor() as cur:
            return self._devolver_vencidos(cur)

    def bater(
        self, trabalho_id: str, *, lease_s: int = 60, operario: str | None = None
    ) -> bool:
        """Renova o lease. So do dono, e so lease que AINDA VALE.

        As duas condicoes sao as mesmas que o SQLite aprendeu por achado
        adversarial: sem `operario`, um zumbi mantinha vivo o trabalho de outro;
        sem `lease_ate > now()`, quem dormiu mais que o proprio lease ressuscitava
        a posse por ter acordado antes do recolhedor.
        """
        agora = _agora()
        sql = (
            "update public.criativo_render_job"
            " set batimento_em=%s, lease_ate=%s, atualizado_em=now()"
            " where id=%s and estado in ('claimed','running','validating')"
            "   and lease_ate is not null and lease_ate > now()"
        )
        args: list[Any] = [agora, agora + timedelta(seconds=lease_s), trabalho_id]
        if operario:
            sql += " and owner=%s"
            args.append(operario)
        con = self._con()
        with con.cursor() as cur:
            cur.execute(sql, tuple(args))
            return (cur.rowcount or 0) > 0

    def transicionar(
        self,
        trabalho_id: str,
        para: EstadoDoTrabalho,
        *,
        falha: dict[str, Any] | None = None,
        recibo: dict[str, Any] | None = None,
        exigir_operario: str | None = None,
    ) -> Trabalho:
        con = self._con()
        with con.cursor() as cur:
            cur.execute(
                "select estado, owner, lease_ate from public.criativo_render_job"
                " where id=%s for update",
                (trabalho_id,),
            )
            linha = cur.fetchone()
            if linha is None:
                raise KeyError(trabalho_id)
            de = EstadoDoTrabalho(linha["estado"])
            if exigir_operario is not None and linha["owner"] != exigir_operario:
                raise TransicaoProibida(de, para)
            if para is EstadoDoTrabalho.RENDERED and not recibo:
                raise ValueError("nao se conclui um trabalho sem recibo")
            if para is EstadoDoTrabalho.RENDERED and not (recibo or {}).get("artefatos"):
                raise ValueError("nao se conclui um trabalho sem recibo COM artefato")
            if para is EstadoDoTrabalho.FAILED and not falha:
                raise ValueError("nao se falha um trabalho sem motivo")
            if para is EstadoDoTrabalho.FAILED:
                if _caminho_na_mensagem(str((falha or {}).get("mensagem") or "")):
                    raise ValueError(
                        "a mensagem de falha nao pode carregar caminho de disco"
                    )

            # Vide `deposito.py`: motivo de devolucao vive na trilha, nao na
            # linha. Aqui o CHECK `falha_coerente` obriga; la, a paridade.
            falha_na_linha = falha if para is not EstadoDoTrabalho.QUEUED else None
            try:
                with con.transaction():
                    if recibo:
                        self._gravar_recibo(cur, trabalho_id, recibo)
                    solta = para in TERMINAIS or para is EstadoDoTrabalho.QUEUED
                    cur.execute(
                        "update public.criativo_render_job set estado=%s,"
                        " falha_codigo=%s, falha_mensagem=%s, falha_permanente=%s,"
                        " owner=%s, lease_ate=%s,"
                        " terminado_em=%s, atualizado_em=now()"
                        " where id=%s",
                        (
                            para.value,
                            (falha_na_linha or {}).get("codigo"),
                            (falha_na_linha or {}).get("mensagem"),
                            (falha_na_linha or {}).get("permanente"),
                            None if solta else linha["owner"],
                            # PRESERVA o lease, nao renova: renovar e trabalho do
                            # batimento, que confere dono. O gatilho recusaria.
                            None if solta else linha["lease_ate"],
                            _agora() if para in TERMINAIS else None,
                            trabalho_id,
                        ),
                    )
            except Exception as e:  # noqa: BLE001
                self._traduzir(e, de, para, trabalho_id, linha["lease_ate"])
                raise
        achado = self.por_id(trabalho_id)
        assert achado is not None
        return achado

    @staticmethod
    def _traduzir(
        e: Exception, de: EstadoDoTrabalho, para: EstadoDoTrabalho,
        trabalho_id: str, lease_ate: Any,
    ) -> None:
        """Converte a guarda do banco no erro tipado que o chamador ja trata.

        ⚠️ Sem isto, o operario receberia `psycopg.errors.IntegrityError` e cairia
        no `except Exception` generico — o mesmo caminho que apaga diretorio. O
        tipo do erro decide o comportamento; deixar o driver vazar aqui trocaria
        "perdi a posse" por "falha inesperada".
        """
        sqlstate = getattr(e, "sqlstate", None) or getattr(getattr(e, "diag", None), "sqlstate", None)
        if sqlstate != _SQLSTATE_GUARDA:
            return
        texto = str(e)
        if "lease vencido" in texto:
            raise LeaseVencido(trabalho_id, lease_ate) from e
        raise TransicaoProibida(de, para) from e

    @staticmethod
    def _gravar_recibo(cur: Any, trabalho_id: str, recibo: dict[str, Any]) -> None:
        """Escreve recibo + artefatos + validacoes ANTES da transicao.

        ⚠️ A ordem importa e nao e arbitraria: o gatilho de `rendered` procura
        `recibo join artefato`. Gravar depois faria toda conclusao legitima ser
        recusada pelo banco — o job estaria certo e a escrita, na ordem errada.
        """
        cur.execute("select tenant_id from public.criativo_render_job where id=%s",
                    (trabalho_id,))
        tenant = (cur.fetchone() or {}).get("tenant_id")
        cur.execute(
            "insert into public.criativo_render_recibo"
            " (job_id, tenant_id, produzido_por, motor_slug, motor_versao, seed,"
            "  versoes, parametros, assinatura, iniciado_em, terminado_em,"
            "  custo_estimado_usd, custo_real_usd,"
            "  lufs_integrado, true_peak_dbtp, alvo_lufs)"
            " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            " on conflict (job_id) do nothing returning id",
            (
                trabalho_id, tenant,
                recibo.get("produzido_por") or "desconhecido",
                recibo.get("motor_slug") or "desconhecido",
                recibo.get("motor_versao") or "desconhecida",
                recibo.get("seed") or 0,
                json.dumps(recibo.get("versoes") or {}),
                json.dumps(recibo.get("parametros") or {}),
                recibo.get("assinatura_determinista") or "",
                recibo.get("iniciado_em"), recibo.get("terminado_em"),
                recibo.get("custo_estimado_usd"), recibo.get("custo_real_usd"),
                (recibo.get("audio") or {}).get("lufs_integrado"),
                (recibo.get("audio") or {}).get("true_peak_dbtp"),
                (recibo.get("audio") or {}).get("alvo_lufs"),
            ),
        )
        achado = cur.fetchone()
        if achado is None:  # replay: o recibo ja estava la
            return
        recibo_id = achado["id"]
        for a in recibo.get("artefatos") or []:
            cur.execute(
                "insert into public.criativo_render_artefato"
                " (recibo_id, slot, mime, bytes, sha256, largura, altura, duracao_s)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s)",
                (recibo_id, a["slot"], a["mime"], a.get("bytes_") or a.get("bytes"),
                 a["sha256"], a.get("largura"), a.get("altura"), a.get("duracao_s")),
            )
        for v in recibo.get("validacoes") or []:
            cur.execute(
                "insert into public.criativo_render_validacao"
                " (recibo_id, gate, resultado, detalhe, bloqueante)"
                " values (%s,%s,%s,%s,%s)",
                (recibo_id, v["gate"], v["resultado"],
                 json.dumps(v.get("detalhe")) if v.get("detalhe") is not None else None,
                 v["bloqueante"]),
            )

    def retomar(
        self, trabalho_id: str, *, tenant_id: str, max_tentativas: int = 3
    ) -> tuple[Trabalho, bool]:
        original = self.por_id(trabalho_id, tenant_id=tenant_id)
        if original is None:
            # Mesmo tratamento para "nao existe" e "nao e seu".
            raise KeyError(trabalho_id)
        if original.estado not in TERMINAIS:
            raise TransicaoProibida(original.estado, EstadoDoTrabalho.QUEUED)
        if original.estado is EstadoDoTrabalho.RENDERED:
            raise TransicaoProibida(original.estado, EstadoDoTrabalho.QUEUED)

        raiz = original.retoma_de or original.id
        n = original.retomada_n + 1
        from dataclasses import replace  # noqa: PLC0415

        encomenda = replace(original.encomenda, tenant_id=tenant_id)
        return self.enfileirar(
            encomenda,
            max_tentativas=max_tentativas,
            chave=chave_de_retomada(self._chave_raiz(raiz), n),
            retoma_de=original.id,
            retomada_n=n,
        )

    def _chave_raiz(self, raiz_id: str) -> str:
        t = self.por_id(raiz_id)
        return t.chave_idempotencia if t else raiz_id

    def cancelar(
        self, trabalho_id: str, *, tenant_id: str, por: str, motivo: str
    ) -> Trabalho:
        if not motivo.strip():
            raise ValueError("nao se cancela sem motivo")
        t = self.por_id(trabalho_id, tenant_id=tenant_id)
        if t is None:
            raise KeyError(trabalho_id)
        if t.estado in TERMINAIS:
            raise TransicaoProibida(t.estado, EstadoDoTrabalho.CANCELLED)
        con = self._con()
        with con.cursor() as cur:
            cur.execute(
                "update public.criativo_render_job"
                " set estado='cancelled', owner=null, lease_ate=null,"
                "     cancelado_por=%s, cancelado_motivo=%s, cancelado_em=now(),"
                "     terminado_em=now(), atualizado_em=now()"
                " where id=%s and estado not in ('rendered','failed','cancelled')",
                (por, motivo.strip()[:280], trabalho_id),
            )
            if (cur.rowcount or 0) == 0:
                atual = self.por_id(trabalho_id)
                raise TransicaoProibida(
                    atual.estado if atual else t.estado, EstadoDoTrabalho.CANCELLED
                )
        achado = self.por_id(trabalho_id)
        assert achado is not None
        return achado

    # ── leitura ──────────────────────────────────────────────────────────────

    def por_id(self, trabalho_id: str, *, tenant_id: str | None = None) -> Trabalho | None:
        sql = "select * from public.criativo_render_job where id=%s"
        args: list[Any] = [trabalho_id]
        if tenant_id is not None:
            sql += " and tenant_id=%s"
            args.append(tenant_id)
        with self._con().cursor() as cur:
            try:
                cur.execute(sql, tuple(args))
            except Exception:  # noqa: BLE001 — id que nem e uuid nao e "erro do banco"
                self._con().rollback()
                return None
            linha = cur.fetchone()
        return _do_banco(linha) if linha else None

    def por_chave(self, chave: str, *, tenant_id: str | None = None) -> Trabalho | None:
        sql = "select * from public.criativo_render_job where idempotency_key=%s"
        args: list[Any] = [chave]
        if tenant_id is not None:
            sql += " and tenant_id=%s"
            args.append(tenant_id)
        sql += " order by criado_em limit 1"
        with self._con().cursor() as cur:
            cur.execute(sql, tuple(args))
            linha = cur.fetchone()
        return _do_banco(linha) if linha else None

    def listar(self, *, tenant_id: str, limite: int = 50) -> list[Trabalho]:
        with self._con().cursor() as cur:
            cur.execute(
                "select * from public.criativo_render_job where tenant_id=%s"
                " order by criado_em desc limit %s",
                (tenant_id, limite),
            )
            return [_do_banco(l) for l in cur.fetchall()]

    def linhagem(self, trabalho_id: str, *, tenant_id: str) -> list[Trabalho]:
        t = self.por_id(trabalho_id, tenant_id=tenant_id)
        if t is None:
            raise KeyError(trabalho_id)
        raiz = t.retoma_de or t.id
        while (pai := self.por_id(raiz)) is not None and pai.retoma_de:
            raiz = pai.retoma_de
        with self._con().cursor() as cur:
            cur.execute(
                "with recursive cadeia as ("
                "  select * from public.criativo_render_job where id=%s"
                "  union all"
                "  select j.* from public.criativo_render_job j"
                "    join cadeia c on j.retry_of = c.id"
                ") select * from cadeia where tenant_id=%s order by criado_em",
                (raiz, tenant_id),
            )
            return [_do_banco(l) for l in cur.fetchall()]

    def trilha(
        self, trabalho_id: str, *, tenant_id: str | None = None
    ) -> list[dict[str, Any]]:
        if tenant_id is not None and self.por_id(trabalho_id, tenant_id=tenant_id) is None:
            raise KeyError(trabalho_id)
        with self._con().cursor() as cur:
            cur.execute(
                "select de, para, por, motivo, em from public.criativo_render_transicao"
                " where job_id=%s order by id",
                (trabalho_id,),
            )
            return [
                {**l, "em": l["em"].isoformat() if hasattr(l["em"], "isoformat") else l["em"]}
                for l in cur.fetchall()
            ]

    def contar_por_estado(self) -> dict[str, int]:
        with self._con().cursor() as cur:
            cur.execute(
                "select estado, count(*) n from public.criativo_render_job group by estado"
            )
            return {l["estado"]: l["n"] for l in cur.fetchall()}


# ─────────────────────────────────────────────────────────────────────────────
# Traducao
# ─────────────────────────────────────────────────────────────────────────────


def _encomenda_para_json(e: Encomenda) -> dict[str, Any]:
    from dataclasses import asdict  # noqa: PLC0415

    return asdict(e)


def _do_banco(linha: dict[str, Any]) -> Trabalho:
    cru = linha["encomenda"]
    d = json.loads(cru) if isinstance(cru, str) else cru
    encomenda = Encomenda(
        receita_id=d["receita_id"],
        tenant_id=d.get("tenant_id") or "",
        motor_slug=d["motor_slug"],
        modo_slug=d["modo_slug"],
        finalidade_slug=d["finalidade_slug"],
        seed=d["seed"],
        saidas=tuple(SaidaPedida(**s) for s in d["saidas"]),
        parametros=d.get("parametros") or {},
    )
    falha = None
    if linha.get("falha_codigo"):
        falha = {
            "codigo": linha["falha_codigo"],
            "mensagem": linha.get("falha_mensagem"),
            "permanente": linha.get("falha_permanente"),
        }
    return Trabalho(
        id=str(linha["id"]),
        tenant_id=linha["tenant_id"],
        chave_idempotencia=linha["idempotency_key"],
        retoma_de=str(linha["retry_of"]) if linha.get("retry_of") else None,
        retomada_n=linha.get("retry_n") or 0,
        cancelado_por=linha.get("cancelado_por"),
        cancelado_motivo=linha.get("cancelado_motivo"),
        estado=EstadoDoTrabalho(linha["estado"]),
        encomenda=encomenda,
        tentativa=linha.get("tentativa") or 0,
        max_tentativas=linha.get("max_tentativas") or 3,
        operario=linha.get("owner"),
        lease_ate=linha.get("lease_ate"),
        batimento_em=linha.get("batimento_em"),
        falha=falha,
        # ⚠️ O recibo do Postgres vive em tabela propria. Reconstruir o dict
        # inteiro a cada leitura de fila seria caro e enganoso — o que a fila
        # precisa saber e SE existe recibo, e isso o estado `rendered` ja diz,
        # porque o gatilho nao deixa chegar la sem ele. Quem quer o recibo pede
        # o recibo.
        recibo={"_em": "criativo_render_recibo"}
        if linha["estado"] == EstadoDoTrabalho.RENDERED.value
        else None,
        criado_em=linha["criado_em"],
        terminado_em=linha.get("terminado_em"),
    )
