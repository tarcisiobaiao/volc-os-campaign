"""O deposito de trabalhos: durável, com lease e batimento.

## Por que SQLite e nao um dicionario

Porque "durável" e a palavra que separa este executor do anterior. O executor de
hoje e `asyncio.create_task` num processo que a Vercel congela quando a resposta
sai; um dicionario em memoria repetiria o mesmo defeito com outro nome. SQLite e
banco de verdade: sobrevive ao processo morrer, tem transacao, e a mesma consulta
de reivindicacao que aqui usa `BEGIN IMMEDIATE` vira `FOR UPDATE SKIP LOCKED` no
Postgres sem mudar o contrato.

⚠️ Este deposito NAO e a persistencia de producao. As tabelas `criativo_*` do
Supabase continuam sendo a autoridade do dominio. Isto e a fila do executor, que
e outra coisa: a fila e do worker, o dominio e do produto. Confundir os dois foi
o que fez o job virar `asyncio.create_task`.

## Lease e batimento

Reivindicar um trabalho da um `lease` com prazo. O operario bate o coracao
enquanto trabalha. Se o prazo vence sem batimento, o trabalho VOLTA para a fila —
nao e marcado como falho. A diferenca importa: um operario que morreu nao
significa que o pedido e invalido.

⚠️ E por isso que `tentativas` e contado na reivindicacao e nao na criacao. Um
trabalho que volta tres vezes por operario morto e um trabalho que ninguem
conseguiu fazer, e em algum momento isso precisa parar de ser tentado.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .contrato import (
    TERMINAIS,
    Encomenda,
    chave_de_retomada,
    EstadoDoTrabalho,
    SaidaPedida,
    TransicaoProibida,
    pode_ir,
)

_ESQUEMA = """
create table if not exists trabalho (
    id                    text primary key,
    tenant_id             text not null,
    chave_idempotencia    text not null unique,
    -- Linhagem: de qual trabalho terminal este nasceu. `null` no original.
    retoma_de             text references trabalho(id),
    retomada_n            integer not null default 0,
    cancelado_por         text,
    cancelado_motivo      text,
    estado                text not null,
    encomenda_json        text not null,
    tentativa             integer not null default 0,
    max_tentativas        integer not null default 3,
    operario              text,
    lease_ate             text,
    batimento_em          text,
    falha_json            text,
    recibo_json           text,
    criado_em             text not null,
    atualizado_em         text not null,
    -- Carimbo de terminalidade. No Postgres e um CHECK
    -- (`terminal_carimbado`); aqui era simplesmente inexistente.
    terminado_em          text
);
create index if not exists trabalho_fila on trabalho (estado, criado_em);
create index if not exists trabalho_tenant on trabalho (tenant_id, criado_em);
create index if not exists trabalho_retoma on trabalho (retoma_de);

-- A trilha de transicoes, append-only.
--
-- ⚠️ Ela existia so no Postgres da v11_03 (`criativo_render_transicao`). A fila
-- local nao guardava nenhuma: um trabalho que passou por `queued -> claimed ->
-- queued -> claimed -> failed` chegava ao fim indistinguivel de um que falhou de
-- primeira. Provar localmente um comportamento que a producao registra e a fila
-- esquece e provar outra coisa.
create table if not exists transicao (
    id           integer primary key autoincrement,
    trabalho_id  text not null references trabalho(id),
    de           text,
    para         text not null,
    por          text,
    motivo       text,
    em           text not null
);
create index if not exists transicao_trabalho on transicao (trabalho_id, id);
"""


#: Estados cujo AVANCO exige lease vivo. Espelha o gatilho
#: `criativo_render_transicao_valida` da v11_03.
_EXIGEM_LEASE_VIVO: frozenset[EstadoDoTrabalho] = frozenset(
    {EstadoDoTrabalho.RUNNING, EstadoDoTrabalho.VALIDATING}
)

#: Caminho de disco numa mensagem de erro. Os cinco padroes sao os mesmos do
#: CHECK `criativo_render_job_mensagem_sem_caminho`, incluindo os tres bypasses
#: que a auditoria mediu: `device:/var/...` sem espaco antes da barra,
#: `(/Users/...)` com parentese antes e o UNC `\\servidor\share` do Windows.
#: A lacuna L1 do handoff da bancada dizia exatamente isto: a migration barrava,
#: a fila SQLite nao.
_PADROES_DE_CAMINHO: tuple[re.Pattern[str], ...] = (
    re.compile(r"/[^\s'\"/]+/[^\s'\"/]+"),
    re.compile(r"~/"),
    re.compile(r"Traceback \(most recent"),
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"\\\\[^\s]+\\"),
)


def _caminho_na_mensagem(texto: str) -> str | None:
    """O primeiro padrao de caminho encontrado, ou `None`."""
    for padrao in _PADROES_DE_CAMINHO:
        achado = padrao.search(texto)
        if achado:
            return achado.group(0)
    return None


class LeaseVencido(TransicaoProibida):
    """Avanco recusado porque o lease do dono ja venceu.

    Subclasse de `TransicaoProibida` de proposito: todo chamador que ja tratava
    "nao pude avancar" continua tratando, e quem quiser distinguir o motivo tem
    o tipo. Trocar o tipo base faria a correcao de um defeito criar outro.
    """

    def __init__(self, trabalho_id: str, lease_ate: datetime | None) -> None:
        super().__init__(EstadoDoTrabalho.CLAIMED, EstadoDoTrabalho.RUNNING)
        self.trabalho_id = trabalho_id
        self.lease_ate = lease_ate
        self.args = (
            f"lease vencido em {lease_ate.isoformat() if lease_ate else 'nunca renovado'}"
            " — nao avanca sem renovar",
        )


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


@dataclass
class Trabalho:
    id: str
    tenant_id: str
    chave_idempotencia: str
    retoma_de: str | None
    retomada_n: int
    cancelado_por: str | None
    cancelado_motivo: str | None
    estado: EstadoDoTrabalho
    encomenda: Encomenda
    tentativa: int
    max_tentativas: int
    operario: str | None
    lease_ate: datetime | None
    batimento_em: datetime | None
    falha: dict[str, Any] | None
    recibo: dict[str, Any] | None
    criado_em: datetime
    #: Carimbo de terminalidade. `None` enquanto o trabalho nao terminou — e
    #: `None` e ausencia, nao "terminou na epoca zero".
    terminado_em: datetime | None = None

    @property
    def vivo(self) -> bool:
        """O lease ainda vale?

        ⚠️ Lease vencido NAO significa "morto": significa "ninguem garante que
        esta vivo". Tratar ausencia de batimento como execucao ativa foi um dos
        defeitos que a auditoria procurou. Aqui a ausencia e explicita.
        """
        return self.lease_ate is not None and self.lease_ate > _agora()


# ─────────────────────────────────────────────────────────────────────────────
# ACHADO_FENCING — por que `exigir_operario` sozinho nao cerca nada
# ─────────────────────────────────────────────────────────────────────────────
#
# `Operario._ainda_somos_donos` ja dizia, na propria docstring, que "a posse e da
# REIVINDICACAO, nao do nome", e conferia `(operario, tentativa, vivo)`. Mas
# quem GRAVA e este deposito, e aqui a unica pergunta era o nome.
#
# O nome padrao do operario e `worker-<pid>`, e PID repete entre containers.
# Contraprova executada (02/09/2026, SQLite, `Operario` real):
#
#   zumbi reivindica  -> tentativa=1, operario='worker-4242', lease 1s
#   o lease vence     -> devolver_vencidos() devolve para a fila
#   dono vivo         -> tentativa=2, operario='worker-4242'  (mesmo PID)
#   o zumbi acorda e chama transicionar(QUEUED, exigir_operario='worker-4242')
#   ACEITO: o trabalho que o dono vivo esta produzindo volta para `queued`
#
# A cerca existia no chamador e nao existia no portao. Uma guarda que so vale
# quando o chamador se lembra de aplica-la e documentacao.
#
# `exigir_tentativa` e opcional de proposito: um chamador que so sabe o nome
# continua com a garantia antiga, e quem tem o token da reivindicacao — o
# operario, em todas as suas escritas — passa os dois.


class DepositoDeTrabalhos:
    def __init__(self, caminho: str | Path) -> None:
        self.caminho = str(caminho)
        # Cada thread abre a propria conexao. Compartilhar `sqlite3.Connection`
        # entre threads e exatamente o singleton mutavel que este executor existe
        # para nao ter.
        self._local = threading.local()
        with self._con() as c:
            c.executescript(_ESQUEMA)
            self._migrar(c)

    @staticmethod
    def _migrar(c: sqlite3.Connection) -> None:
        """Colunas que nasceram depois. `create table if not exists` nao as traz.

        ⚠️ Uma fila gravada antes desta versao existe no disco de quem ja rodou a
        bancada. Sem isto, o processo subia e morria no primeiro `select` da
        coluna nova — e o modo de falha seria "a bancada parou", nao "falta
        migrar", que e o diagnostico util.
        """
        colunas = {l["name"] for l in c.execute("pragma table_info(trabalho)")}
        if "terminado_em" not in colunas:
            c.execute("alter table trabalho add column terminado_em text")

    def _con(self) -> sqlite3.Connection:
        con = getattr(self._local, "con", None)
        if con is None:
            con = sqlite3.connect(self.caminho, isolation_level=None, timeout=30)
            con.row_factory = sqlite3.Row
            con.execute("pragma journal_mode=WAL")
            con.execute("pragma busy_timeout=30000")
            self._local.con = con
        return con

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
        """Cria, ou devolve o que ja existe com a mesma chave.

        `criado=False` nao e erro: e a idempotencia funcionando. O chamador
        precisa dos dois para nao cobrar duas vezes pelo mesmo pedido.
        """
        chave = chave or encomenda.chave_de_idempotencia()
        agora = _iso(_agora())
        c = self._con()
        try:
            c.execute(
                "insert into trabalho (id, tenant_id, chave_idempotencia, estado,"
                " encomenda_json, max_tentativas, retoma_de, retomada_n, criado_em,"
                " atualizado_em) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    encomenda.tenant_id,
                    chave,
                    EstadoDoTrabalho.QUEUED.value,
                    _serializar(encomenda),
                    max_tentativas,
                    retoma_de,
                    retomada_n,
                    agora,
                    agora,
                ),
            )
        except sqlite3.IntegrityError:
            existente = self.por_chave(chave)
            assert existente is not None
            return existente, False
        achado = self.por_chave(chave)
        assert achado is not None
        return achado, True

    def reivindicar(self, operario: str, *, lease_s: int = 60) -> Trabalho | None:
        """Pega UM trabalho da fila, com exclusao mutua real.

        `BEGIN IMMEDIATE` toma o lock de escrita antes de ler: dois operarios
        concorrentes nunca reivindicam o mesmo trabalho. No Postgres isto vira
        `for update skip locked`, e o contrato daqui nao muda.

        Antes de pegar da fila, devolve para a fila o que tiver lease vencido.
        """
        c = self._con()
        c.execute("begin immediate")
        escolhido: str | None = None
        try:
            self._devolver_vencidos(c)
            # ⚠️ ACHADO ADVERSARIAL. Esgotar a tentativa marcava FAILED e chamava
            # `self.reivindicar` de novo, por recursao. Com mil trabalhos
            # esgotados na frente, a fila estourava `RecursionError`, o erro real
            # era substituido pelo do rollback, e todo POST seguinte virava 500
            # ate alguem apagar o `fila.db` a mao. Agora e laco.
            while True:
                linha = c.execute(
                    "select * from trabalho where estado = ? order by criado_em limit 1",
                    (EstadoDoTrabalho.QUEUED.value,),
                ).fetchone()
                if linha is None:
                    break
                if linha["tentativa"] >= linha["max_tentativas"]:
                    self._enterrar(c, linha["id"], linha["estado"],
                                   linha["tentativa"])
                    continue
                agora = _agora()
                c.execute(
                    "update trabalho set estado=?, operario=?, lease_ate=?,"
                    " batimento_em=?, tentativa=tentativa+1, atualizado_em=?"
                    " where id=?",
                    (EstadoDoTrabalho.CLAIMED.value, operario,
                     _iso(agora + timedelta(seconds=lease_s)), _iso(agora),
                     _iso(agora), linha["id"]),
                )
                self._trilhar(c, linha["id"], linha["estado"],
                              EstadoDoTrabalho.CLAIMED.value, operario)
                escolhido = linha["id"]
                break
            c.execute("commit")
        except Exception:
            # ⚠️ `contextlib_suppress` porque o rollback pode estourar quando ja
            # houve commit interno — e ai a excecao do rollback SUBSTITUIA a
            # excecao real, escondendo a causa de quem for depurar.
            with contextlib_suppress():
                c.execute("rollback")
            raise
        return self.por_id(escolhido) if escolhido else None

    def retomar(
        self, trabalho_id: str, *, tenant_id: str, max_tentativas: int = 3
    ) -> tuple[Trabalho, bool]:
        """Cria um trabalho NOVO a partir de um terminal, com linhagem.

        ⚠️ Nao reaproveita o trabalho antigo. Um `failed` guarda o motivo de ter
        falhado, e reabri-lo apagaria essa historia. O novo carrega `retoma_de` e
        `retomada_n`, e a chave e derivada da original — entao dois cliques na
        MESMA retomada convergem para o mesmo trabalho, e a idempotencia continua
        impedindo duplicacao acidental sem condenar o pedido.
        """
        original = self.por_id(trabalho_id)
        if original is None or original.tenant_id != tenant_id:
            # Mesmo tratamento para "nao existe" e "nao e seu": responder
            # diferente confirmaria a existencia de trabalho alheio.
            raise KeyError(trabalho_id)
        if original.estado not in TERMINAIS:
            raise TransicaoProibida(original.estado, EstadoDoTrabalho.QUEUED)
        if original.estado is EstadoDoTrabalho.RENDERED:
            # Retomar o que deu certo produziria a MESMA peca de novo, pagando
            # de novo. Quem quer outra peca muda o pedido.
            raise TransicaoProibida(original.estado, EstadoDoTrabalho.QUEUED)

        raiz = original.retoma_de or original.id
        n = original.retomada_n + 1
        # ACHADO ADVERSARIAL. `enfileirar` grava `encomenda.tenant_id`, e a
        # encomenda vem de `_desserializar`, que faz `.get(...) or ""`. Uma fila
        # gravada antes do tenant existir produzia retomada com tenant VAZIO: a
        # rota respondia 201 com o id, `por_id(tenant)` devolvia 404 para sempre,
        # e o acompanhamento ficava preso. Conferir um campo e gravar outro e o
        # mesmo conceito em duas fontes, comparadas nunca.
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
        """Produtor real de `cancelled`.

        ⚠️ O estado existia no contrato e NINGUEM o produzia — a auditoria
        chamou isso de "sete estados, seis com funcao". Cancelar confere dono,
        estado e solta o lease, para o operario que estiver com ele descobrir na
        proxima transicao que perdeu o trabalho.
        """
        if not motivo.strip():
            raise ValueError("nao se cancela sem motivo")
        t = self.por_id(trabalho_id)
        if t is None or t.tenant_id != tenant_id:
            raise KeyError(trabalho_id)
        if t.estado in TERMINAIS:
            raise TransicaoProibida(t.estado, EstadoDoTrabalho.CANCELLED)

        c = self._con()
        c.execute("begin immediate")
        try:
            cur = c.execute(
                "update trabalho set estado=?, operario=null, lease_ate=null,"
                " cancelado_por=?, cancelado_motivo=?, atualizado_em=?,"
                " terminado_em=? where id=? and estado not in (?,?,?)",
                (EstadoDoTrabalho.CANCELLED.value, por, motivo.strip()[:280],
                 _iso(_agora()), _iso(_agora()), trabalho_id,
                 EstadoDoTrabalho.RENDERED.value, EstadoDoTrabalho.FAILED.value,
                 EstadoDoTrabalho.CANCELLED.value),
            )
            if (cur.rowcount or 0) == 0:
                c.execute("rollback")
                atual = self.por_id(trabalho_id)
                raise TransicaoProibida(
                    atual.estado if atual else t.estado, EstadoDoTrabalho.CANCELLED
                )
            self._trilhar(c, trabalho_id, t.estado.value,
                          EstadoDoTrabalho.CANCELLED.value, por, motivo.strip()[:280])
            c.execute("commit")
        except TransicaoProibida:
            raise
        except Exception:
            with contextlib_suppress():
                c.execute("rollback")
            raise
        achado = self.por_id(trabalho_id)
        assert achado is not None
        return achado

    def linhagem(self, trabalho_id: str, *, tenant_id: str) -> list[Trabalho]:
        """A cadeia de retomadas, do original ao mais recente."""
        t = self.por_id(trabalho_id)
        if t is None or t.tenant_id != tenant_id:
            raise KeyError(trabalho_id)
        raiz = t.retoma_de or t.id
        while (pai := self.por_id(raiz)) is not None and pai.retoma_de:
            raiz = pai.retoma_de
        linhas = self._con().execute(
            "select * from trabalho where tenant_id=? and (id=? or retoma_de is not null)"
            " order by criado_em",
            (tenant_id, raiz),
        ).fetchall()
        cadeia = [_do_banco(l) for l in linhas]
        ids = {raiz}
        saida = [t for t in cadeia if t.id == raiz]
        mudou = True
        while mudou:
            mudou = False
            for x in cadeia:
                if x.retoma_de in ids and x.id not in ids:
                    ids.add(x.id)
                    saida.append(x)
                    mudou = True
        return saida

    def reivindicar_este(
        self, trabalho_id: str, operario: str, *, lease_s: int = 60
    ) -> Trabalho | None:
        """Reivindica UM trabalho pelo id. `None` se ele nao estiver na fila.

        ⚠️ Existe porque `despachar` precisa do trabalho QUE FOI PEDIDO, e nao do
        mais antigo. Sem isto, o POST devolvia um id e produzia outro.
        """
        c = self._con()
        c.execute("begin immediate")
        try:
            self._devolver_vencidos(c)
            linha = c.execute(
                "select * from trabalho where id=? and estado=?",
                (trabalho_id, EstadoDoTrabalho.QUEUED.value),
            ).fetchone()
            if linha is None:
                c.execute("commit")
                return None
            if linha["tentativa"] >= linha["max_tentativas"]:
                self._enterrar(c, trabalho_id, linha["estado"], linha["tentativa"])
                c.execute("commit")
                return None
            agora = _agora()
            c.execute(
                "update trabalho set estado=?, operario=?, lease_ate=?, batimento_em=?,"
                " tentativa=tentativa+1, atualizado_em=? where id=?",
                (EstadoDoTrabalho.CLAIMED.value, operario,
                 _iso(agora + timedelta(seconds=lease_s)), _iso(agora), _iso(agora),
                 trabalho_id),
            )
            self._trilhar(c, trabalho_id, linha["estado"],
                          EstadoDoTrabalho.CLAIMED.value, operario)
            c.execute("commit")
        except Exception:
            with contextlib_suppress():
                c.execute("rollback")
            raise
        return self.por_id(trabalho_id)

    #: Quem enterra o trabalho esgotado. Vide `DepositoPostgres.RECOLHEDOR`.
    RECOLHEDOR = "recolhedor"

    def _enterrar(self, c: sqlite3.Connection, trabalho_id: str, de: str,
                  tentativa: int) -> None:
        """Tira da fila quem gastou o teto de tentativas, PELO MAPA.

        ⚠️ ACHADO DA SUITE DE CONTRATO. `queued -> failed` nao existe em
        `TRANSICOES`, e este metodo escrevia exatamente isso por SQL cru — o
        deposito desobedecendo o mapa que ele mesmo publica. O Postgres recusa em
        gatilho, e a divergencia so apareceu quando as mesmas assercoes rodaram
        nos dois. O caminho legitimo e `queued -> claimed -> failed`, com autor
        na trilha; a tentativa NAO sobe, porque enterrar nao e tentar.
        """
        agora = _iso(_agora())
        c.execute(
            "update trabalho set estado=?, operario=?, lease_ate=?, batimento_em=?,"
            " atualizado_em=? where id=?",
            (EstadoDoTrabalho.CLAIMED.value, self.RECOLHEDOR,
             _iso(_agora() + timedelta(seconds=60)), agora, agora, trabalho_id),
        )
        self._trilhar(c, trabalho_id, de, EstadoDoTrabalho.CLAIMED.value,
                      self.RECOLHEDOR, "esgotado")
        c.execute(
            "update trabalho set estado=?, falha_json=?, operario=null,"
            " lease_ate=null, atualizado_em=?, terminado_em=? where id=?",
            (
                EstadoDoTrabalho.FAILED.value,
                json.dumps({
                    "codigo": "tentativas_esgotadas",
                    "mensagem": (
                        f"o trabalho foi tentado {tentativa} vezes e nao concluiu"
                    ),
                    "permanente": True,
                }),
                agora, agora, trabalho_id,
            ),
        )
        self._trilhar(c, trabalho_id, EstadoDoTrabalho.CLAIMED.value,
                      EstadoDoTrabalho.FAILED.value, self.RECOLHEDOR,
                      "tentativas_esgotadas")

    @staticmethod
    def _trilhar(c: sqlite3.Connection, trabalho_id: str, de: str, para: str,
                 por: str | None = None, motivo: str | None = None) -> None:
        """Escreve um passo da trilha, na MESMA transacao de quem o causou.

        ⚠️ ACHADO DA SUITE DE CONTRATO. A trilha nascia so em `transicionar`, e
        no Postgres o gatilho esta no UPDATE da tabela — entao o claim e a
        devolucao por lease vencido, que sao UPDATE e nao passam por
        `transicionar`, apareciam la e sumiam aqui. Duas trilhas diferentes para
        a mesma corrida e a mesma dupla verdade de sempre, so que na auditoria.
        """
        c.execute(
            "insert into transicao (trabalho_id, de, para, por, motivo, em)"
            " values (?, ?, ?, ?, ?, ?)",
            (trabalho_id, de, para, por, motivo, _iso(_agora())),
        )

    def _devolver_vencidos(self, c: sqlite3.Connection) -> int:
        """Lease vencido sem batimento volta para a fila.

        Nao marca como falho: um operario que morreu nao torna o pedido invalido.
        A tentativa ja foi contada na reivindicacao, entao isto nao e infinito.
        """
        agora = _iso(_agora())
        # Le ANTES do UPDATE: depois dele o estado de origem ja se perdeu, e a
        # trilha existe para dizer de onde o trabalho veio.
        vencidos = c.execute(
            "select id, estado, operario from trabalho where estado in (?,?,?)"
            " and lease_ate is not null and lease_ate < ?",
            (
                EstadoDoTrabalho.CLAIMED.value,
                EstadoDoTrabalho.RUNNING.value,
                EstadoDoTrabalho.VALIDATING.value,
                agora,
            ),
        ).fetchall()
        cur = c.execute(
            "update trabalho set estado=?, operario=null, lease_ate=null,"
            " atualizado_em=? where estado in (?,?,?) and lease_ate is not null"
            " and lease_ate < ?",
            (
                EstadoDoTrabalho.QUEUED.value,
                agora,
                EstadoDoTrabalho.CLAIMED.value,
                EstadoDoTrabalho.RUNNING.value,
                EstadoDoTrabalho.VALIDATING.value,
                agora,
            ),
        )
        for v in vencidos:
            self._trilhar(c, v["id"], v["estado"], EstadoDoTrabalho.QUEUED.value,
                          v["operario"], "lease_vencido")
        return cur.rowcount or 0

    def devolver_vencidos(self) -> int:
        c = self._con()
        c.execute("begin immediate")
        try:
            n = self._devolver_vencidos(c)
            c.execute("commit")
        except Exception:
            c.execute("rollback")
            raise
        return n

    def bater(self, trabalho_id: str, *, lease_s: int = 60,
              operario: str | None = None, tentativa: int | None = None) -> bool:
        """Renova o lease. `False` quando o trabalho ja saiu das maos deste operario."""
        agora = _agora()
        c = self._con()
        # ⚠️ ACHADO ADVERSARIAL. O UPDATE nao filtrava por `operario`: um
        # operario que JA TINHA PERDIDO o trabalho continuava batendo o coracao,
        # `lease_ate` ficava no futuro, `vivo` dizia `True`, e o trabalho nunca
        # voltava para a fila quando o dono real morria. Ausencia de batimento DO
        # DONO era tratada como execucao ativa.
        # ⚠️ ACHADO ADVERSARIAL (revisão de 2026-08-29). O UPDATE tambem nao
        # filtrava por `lease_ate`: um processo que ficou pausado MAIS TEMPO que o
        # proprio lease voltava a bater e empurrava o prazo para o futuro, desde
        # que o recolhedor ainda nao tivesse passado. O lease deixava de ser prazo
        # e virava sugestao — quem dormiu 10 minutos com lease de 60s ressuscitava
        # a posse por ter acordado antes do `devolver_vencidos`. Renovar so vale
        # para lease QUE AINDA VALE; o vencido espera o recolhedor, como todos.
        cur = c.execute(
            "update trabalho set batimento_em=?, lease_ate=?, atualizado_em=?"
            " where id=? and estado in (?,?,?)"
            " and lease_ate is not null and lease_ate > ?"
            + (" and operario=?" if operario else "")
            # ⚠️ ACHADO_FENCING, segunda metade. Filtrar so por `operario` deixava
            # o zumbi HOMONIMO renovar o lease do dono vivo: `worker-<pid>` repete
            # entre containers, e o batimento e justamente o que diz "ainda estou
            # produzindo". Um zumbi que mantem vivo o trabalho de outro impede o
            # recolhedor de agir quando o dono REAL morre.
            + (" and tentativa=?" if tentativa is not None else ""),
            (
                _iso(agora),
                _iso(agora + timedelta(seconds=lease_s)),
                _iso(agora),
                trabalho_id,
                EstadoDoTrabalho.CLAIMED.value,
                EstadoDoTrabalho.RUNNING.value,
                EstadoDoTrabalho.VALIDATING.value,
                _iso(agora),
            )
            + ((operario,) if operario else ())
            + ((tentativa,) if tentativa is not None else ()),
        )
        return (cur.rowcount or 0) > 0

    def transicionar(
        self,
        trabalho_id: str,
        para: EstadoDoTrabalho,
        *,
        falha: dict[str, Any] | None = None,
        recibo: dict[str, Any] | None = None,
        exigir_operario: str | None = None,
        exigir_tentativa: int | None = None,
    ) -> Trabalho:
        c = self._con()
        c.execute("begin immediate")
        try:
            linha = c.execute(
                "select estado, operario, tentativa, lease_ate from trabalho"
                " where id=?",
                (trabalho_id,),
            ).fetchone()
            if linha is None:
                c.execute("rollback")
                raise KeyError(trabalho_id)
            de = EstadoDoTrabalho(linha["estado"])
            # ⚠️ Quem perdeu o lease nao escreve por cima de quem o tem.
            if exigir_operario is not None and linha["operario"] != exigir_operario:
                c.execute("rollback")
                raise TransicaoProibida(de, para)
            # ⚠️ ACHADO_FENCING. O nome sozinho NAO e cerca: ver a nota no topo
            # do modulo. A tentativa e a metade que diz QUAL VEZ.
            if exigir_tentativa is not None and linha["tentativa"] != exigir_tentativa:
                c.execute("rollback")
                raise TransicaoProibida(de, para)
            if not pode_ir(de, para):
                c.execute("rollback")
                raise TransicaoProibida(de, para)
            # ⚠️ DIVERGENCIA FECHADA (P17-T04). O gatilho
            # `criativo_render_transicao_valida` recusa avancar para `running` ou
            # `validating` com lease vencido — o comentario dele chama isso de
            # ACHADO #8 e diz "a corrida some: quem perdeu o prazo nao anda". A
            # correcao nunca desceu para a fila local, e ali o mesmo dono com
            # lease vencido ha duas horas avancava livremente. Contraprova em
            # `docs/closure/creative-factory-production-spine-v1/contraprovas/
            # contraprova_lease.py`: `claimed -> running -> validating` com
            # `vivo=False`. Local provava um comportamento que a producao proibe.
            if para in _EXIGEM_LEASE_VIVO:
                lease = _dt(linha["lease_ate"])
                if lease is None or lease <= _agora():
                    c.execute("rollback")
                    raise LeaseVencido(trabalho_id, lease)
            # ⚠️ `rendered` exige recibo. Sem isso, "concluido" e opiniao — e
            # "job marcado como concluido sem artifact" e um dos defeitos que a
            # auditoria adversarial procura.
            if para is EstadoDoTrabalho.RENDERED and not recibo:
                c.execute("rollback")
                raise ValueError("nao se conclui um trabalho sem recibo")
            # ⚠️ DIVERGENCIA FECHADA (P17-T04). O Postgres exige recibo COM
            # ARTEFATO: "recibo sem artefato e promessa, nao prova". A fila local
            # aceitava `{"artefatos": []}` e gravava `rendered`. Contraprova em
            # `contraprova_recibo.py`.
            if para is EstadoDoTrabalho.RENDERED and not (recibo or {}).get("artefatos"):
                c.execute("rollback")
                raise ValueError("nao se conclui um trabalho sem recibo COM artefato")
            if para is EstadoDoTrabalho.FAILED and not falha:
                c.execute("rollback")
                raise ValueError("nao se falha um trabalho sem motivo")
            if para is EstadoDoTrabalho.FAILED:
                caminho = _caminho_na_mensagem(str((falha or {}).get("mensagem") or ""))
                if caminho:
                    c.execute("rollback")
                    raise ValueError(
                        "a mensagem de falha nao pode carregar caminho de disco"
                    )
            # ⚠️ Ao sair de execucao, o lease e o dono somem. Antes nao sumiam:
            # um trabalho `queued` ficava com `lease_ate` no futuro e `vivo`
            # dizia `True` para algo que ninguem estava fazendo. E `falha_json`
            # so e apagado quando ha recibo novo — o motivo da tentativa 1 nao
            # pode desaparecer antes da tentativa 2.
            solta = para in TERMINAIS or para is EstadoDoTrabalho.QUEUED
            agora_iso = _iso(_agora())
            # ⚠️ DIVERGENCIA FECHADA (P17-T04). O CHECK
            # `criativo_render_job_falha_coerente` diz `(estado='failed') =
            # (falha_codigo is not null)`: um trabalho que VOLTOU para a fila nao
            # carrega motivo de falha, porque ele nao falhou — ele vai ser
            # tentado de novo. A fila local gravava o motivo na propria linha, e
            # o comentario justificava: "o motivo da tentativa 1 nao pode
            # desaparecer antes da tentativa 2". A intencao esta certa; o lugar,
            # nao. Um campo unico guarda o motivo da ULTIMA devolucao e apaga os
            # anteriores; a trilha guarda TODOS, um por passagem. Agora o motivo
            # transitorio vai para a trilha, e `falha` na linha significa
            # exatamente uma coisa: este trabalho terminou mal.
            falha_na_linha = falha if para is not EstadoDoTrabalho.QUEUED else None
            c.execute(
                "update trabalho set estado=?, falha_json=?,"
                " recibo_json=?, operario=?, lease_ate=?, atualizado_em=?,"
                " terminado_em=? where id=?",
                (
                    para.value,
                    json.dumps(falha_na_linha) if falha_na_linha else None,
                    json.dumps(recibo) if recibo else None,
                    None if solta else linha["operario"],
                    # ⚠️ PRESERVA o lease, nao renova. A versao anterior gravava
                    # `agora + 60s` em toda transicao de execucao — entao passar
                    # de `claimed` para `running` RESSUSCITAVA um lease ja
                    # vencido, e o trabalho abandonado nunca voltava para a fila.
                    # Renovar lease e trabalho do batimento, e o batimento confere
                    # dono; a transicao nao.
                    None if solta else linha["lease_ate"],
                    agora_iso,
                    # Terminal e carimbado; nao-terminal nao e. No Postgres isto
                    # e o CHECK `criativo_render_job_terminal_carimbado`.
                    agora_iso if para in TERMINAIS else None,
                    trabalho_id,
                ),
            )
            # ⚠️ A trilha e escrita DENTRO da mesma transacao da mudanca de
            # estado. Fora dela, um processo que morresse entre as duas escritas
            # deixaria um estado sem trilha — e a trilha existe justamente para
            # o caso em que o processo morre. `por` usa `coalesce` pela mesma
            # razao do gatilho Postgres: fora de execucao o dono ja foi solto, e
            # gravar `new.owner` deixaria autor NULO em todo evento terminal.
            c.execute(
                "insert into transicao (trabalho_id, de, para, por, motivo, em)"
                " values (?, ?, ?, ?, ?, ?)",
                (
                    trabalho_id,
                    de.value,
                    para.value,
                    exigir_operario or linha["operario"],
                    (falha or {}).get("codigo") if falha else None,
                    agora_iso,
                ),
            )
            c.execute("commit")
        except Exception:
            with contextlib_suppress():
                c.execute("rollback")
            raise
        achado = self.por_id(trabalho_id)
        assert achado is not None
        return achado

    # ── leitura ──────────────────────────────────────────────────────────────

    def por_id(self, trabalho_id: str, *, tenant_id: str | None = None) -> Trabalho | None:
        """⚠️ `tenant_id` e opcional AQUI porque o operario, que ja tem o trabalho
        na mao, nao precisa reprovar posse a cada transicao. Toda leitura vinda de
        HTTP passa `tenant_id`, e a rota nunca chama sem ele."""
        if tenant_id is None:
            linha = self._con().execute(
                "select * from trabalho where id=?", (trabalho_id,)
            ).fetchone()
        else:
            linha = self._con().execute(
                "select * from trabalho where id=? and tenant_id=?",
                (trabalho_id, tenant_id),
            ).fetchone()
        return _do_banco(linha) if linha else None

    def listar(self, *, tenant_id: str, limite: int = 50) -> list[Trabalho]:
        linhas = self._con().execute(
            "select * from trabalho where tenant_id=? order by criado_em desc limit ?",
            (tenant_id, limite),
        ).fetchall()
        return [_do_banco(l) for l in linhas]

    def por_chave(self, chave: str, *, tenant_id: str | None = None) -> Trabalho | None:
        """⚠️ `tenant_id` existe para PARIDADE com o Postgres, onde a identidade
        e `(tenant_id, idempotency_key)` e nao a chave sozinha. Aqui a chave ja
        e derivada do conteudo COM o tenant dentro, entao as duas consultas dao o
        mesmo resultado — mas so enquanto ninguem passar `chave=` explicita por
        fora. Deixar a assinatura divergir seria deixar essa diferenca invisivel
        ate alguem passar a chave a mao."""
        if tenant_id is None:
            linha = self._con().execute(
                "select * from trabalho where chave_idempotencia=?", (chave,)
            ).fetchone()
        else:
            linha = self._con().execute(
                "select * from trabalho where chave_idempotencia=? and tenant_id=?",
                (chave, tenant_id),
            ).fetchone()
        return _do_banco(linha) if linha else None

    def trilha(self, trabalho_id: str, *, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """A trilha append-only de um trabalho, do inicio ao fim.

        `tenant_id` confere posse quando a leitura vem de HTTP; o operario, que
        ja tem o trabalho na mao, chama sem ele — a mesma regra de `por_id`.
        """
        if tenant_id is not None and self.por_id(trabalho_id, tenant_id=tenant_id) is None:
            raise KeyError(trabalho_id)
        linhas = self._con().execute(
            "select de, para, por, motivo, em from transicao"
            " where trabalho_id=? order by id",
            (trabalho_id,),
        ).fetchall()
        return [dict(l) for l in linhas]

    def contar_por_estado(self) -> dict[str, int]:
        linhas = self._con().execute(
            "select estado, count(*) n from trabalho group by estado"
        ).fetchall()
        return {r["estado"]: r["n"] for r in linhas}


class contextlib_suppress:
    def __enter__(self) -> None: ...
    def __exit__(self, *_: Any) -> bool:
        return True


def _serializar(e: Encomenda) -> str:
    from dataclasses import asdict

    return json.dumps(asdict(e), sort_keys=True, ensure_ascii=False)


def _desserializar(cru: str) -> Encomenda:
    d = json.loads(cru)
    return Encomenda(
        receita_id=d["receita_id"],
        # ⚠️ `.get` com fallback vazio: uma fila gravada antes do tenant existir
        # nao pode derrubar o processo na leitura. Trabalho sem tenant e trabalho
        # de ninguem, e a consulta por tenant nunca o devolve — que e o
        # comportamento seguro.
        tenant_id=d.get("tenant_id") or "",
        motor_slug=d["motor_slug"],
        modo_slug=d["modo_slug"],
        finalidade_slug=d["finalidade_slug"],
        seed=d["seed"],
        saidas=tuple(SaidaPedida(**s) for s in d["saidas"]),
        parametros=d.get("parametros") or {},
    )


def _dt(v: Any) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


def _do_banco(linha: sqlite3.Row) -> Trabalho:
    return Trabalho(
        id=linha["id"],
        tenant_id=linha["tenant_id"],
        chave_idempotencia=linha["chave_idempotencia"],
        retoma_de=linha["retoma_de"],
        retomada_n=linha["retomada_n"],
        cancelado_por=linha["cancelado_por"],
        cancelado_motivo=linha["cancelado_motivo"],
        estado=EstadoDoTrabalho(linha["estado"]),
        encomenda=_desserializar(linha["encomenda_json"]),
        tentativa=linha["tentativa"],
        max_tentativas=linha["max_tentativas"],
        operario=linha["operario"],
        lease_ate=_dt(linha["lease_ate"]),
        batimento_em=_dt(linha["batimento_em"]),
        falha=json.loads(linha["falha_json"]) if linha["falha_json"] else None,
        recibo=json.loads(linha["recibo_json"]) if linha["recibo_json"] else None,
        criado_em=_dt(linha["criado_em"]),  # type: ignore[arg-type]
        terminado_em=_dt(_talvez(linha, "terminado_em")),
    )


def _talvez(linha: sqlite3.Row, coluna: str) -> Any:
    """Le uma coluna que pode nao existir numa fila antiga ainda nao migrada."""
    try:
        return linha[coluna]
    except (IndexError, KeyError):
        return None
