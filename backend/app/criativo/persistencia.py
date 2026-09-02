"""Persistência do Estúdio sobre o PostgREST do Supabase oficial. Só transporte.

Nenhuma regra de negócio mora aqui: quem decide estado, chave e sanitização é
`dominio.py`, que não importa `httpx` e roda sem rede. Este arquivo traduz.

## Por que PostgREST e não um driver de Postgres

Porque é o que a casa já usa (`app/trafego/persistencia.py`, `app/services/
supabase_service.py`) e porque `backend/requirements.txt` não declara driver
nenhum. Introduzir `psycopg` só para este módulo criaria um segundo caminho
até o mesmo banco, com um segundo conjunto de defeitos, e o `requirements.txt`
diz na primeira linha "keep this lean: Vercel installs it".

## A idempotência é resolvida pelo BANCO, não por consulta prévia

O caminho óbvio seria `SELECT` pela chave e, se não achar, `INSERT`. Ele tem uma
janela: dois cliques quase simultâneos passam os dois pelo `SELECT` vazio e
inserem os dois. Aqui o `INSERT` é tentado direto e o **índice único** decide;
o `23505` que volta não é erro, é a resposta "já existe", e aí o job existente é
lido e devolvido. A janela some porque quem arbitra é a única coisa serializada
do sistema.

## Ausência é `None`, e a tradução não a converte

Os valores atravessam crus: o PostgREST devolve `null` como `None`, e este
arquivo não normaliza nada. Quem garante que a ausência sobreviva até o browser
é `apresentacao._n`, que está no caminho da resposta e tem teste. Um `float(x or
0)` em qualquer uma das duas pontas desfaz, numa linha, toda a disciplina que a
migration protege com CHECK.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

_TABELA_JOB = "criativo_job"
_TABELA_EVENTO = "criativo_job_evento"
_TABELA_MASTER = "criativo_master"
_TABELA_RENDITION = "criativo_rendition"
_TABELA_PROJETO = "criativo_projeto"
_TABELA_BRIEFING = "criativo_briefing"
_TABELA_APROVACAO = "criativo_aprovacao"
_TABELA_BRAND = "criativo_brand_pack"


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ⚠️ `_num`/`_inteiro` foram REMOVIDOS em 27/08/2026.
#
# O cabeçalho deste arquivo os anunciava como a defesa contra `float(x or 0)` na
# fronteira de leitura. Eles não eram chamados por ninguém: `_num` só era usado
# por `_inteiro`, e `_inteiro` por ninguém. A disciplina existia por OMISSÃO (os
# valores atravessam crus, e o PostgREST já devolve `null` como `None`), não
# pelo mecanismo documentado.
#
# Um helper morto descrito como guarda é pior que nenhum helper: a próxima
# pessoa lê o cabeçalho, acredita que há uma barreira, e escreve o `or 0` do
# outro lado. Quem de fato preserva a ausência é `apresentacao._n`, que está no
# caminho e tem teste.


def _sem_embed(linha: dict[str, Any]) -> dict[str, Any]:
    """Tira o embed de posse antes de a linha subir para a apresentacao.

    ⚠️ O embed `criativo_job(criado_por)` existe para FILTRAR no servidor, nao
    para ser devolvido. Deixa-lo passar acrescentaria o identificador do dono a
    todo DTO de ativo — informacao que a tela nao pede e que so aumenta a
    superficie do que vaza se algo mais der errado.
    """
    if "criativo_job" not in linha:
        return linha
    limpa = dict(linha)
    limpa.pop("criativo_job", None)
    return limpa


class ErroDePersistencia(RuntimeError):
    """Falha de transporte ou do banco, já sem detalhe interno."""


class ConflitoDeChave(Exception):
    """Violação de índice ÚNICO. Não é erro: é a resposta 'já existe'."""


class ReferenciaInvalida(Exception):
    """Violação de chave ESTRANGEIRA: o pedido cita algo que não existe.

    Separada de `ConflitoDeChave` porque o PostgREST devolve 409 para as duas, e
    tratá-las como a mesma coisa fazia um `brandPackId` inexistente escapar do
    tratamento do router e virar 500 — o servidor se acusando de um erro do
    cliente.
    """


class Repositorio:
    """HTTP sobre o PostgREST. Nenhuma regra mora aqui."""

    def __init__(self, base: str, chave: str, *, timeout_s: float = 30.0) -> None:
        self.base = (base or "").rstrip("/")
        self._chave = chave or ""
        self.timeout_s = timeout_s

    @property
    def habilitado(self) -> bool:
        return bool(self.base and self._chave)

    # ── transporte ───────────────────────────────────────────────────────────

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        h = {
            "apikey": self._chave,
            "Authorization": f"Bearer {self._chave}",
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    async def _req(self, metodo: str, alvo: str, **kw: Any) -> Any:
        import httpx  # noqa: PLC0415

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as cli:
                r = await cli.request(metodo, f"{self.base}/rest/v1/{alvo}", **kw)
        except httpx.HTTPError as e:
            raise ErroDePersistencia("o banco não respondeu") from e

        corpo = r.text or ""
        if r.status_code in (409, 400):
            # 23505 = unique_violation, 23503 = foreign_key_violation. O
            # PostgREST devolve 409 para as duas, e o código SQL é a única
            # coisa que as distingue.
            if "23503" in corpo:
                raise ReferenciaInvalida()
            if "23505" in corpo or r.status_code == 409:
                raise ConflitoDeChave()
        if r.status_code >= 400:
            # A resposta do PostgREST cita tabela, coluna e constraint. Ela vai
            # para o log do servidor, nunca para o operador (DESIGN.md).
            raise ErroDePersistencia(
                f"{metodo} {alvo} -> {r.status_code}: {(r.text or '')[:400]}"
            )
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    async def _get(self, alvo: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return (await self._req("GET", alvo, headers=self._headers(), params=params)) or []

    async def _inserir(self, alvo: str, linha: dict[str, Any]) -> dict[str, Any]:
        dados = await self._req(
            "POST",
            alvo,
            headers=self._headers("return=representation"),
            content=json.dumps([linha], default=str),
        )
        if not dados:
            raise ErroDePersistencia(f"insert em {alvo} não devolveu linha")
        return dados[0]

    async def _inserir_muitos(
        self, alvo: str, linhas: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not linhas:
            return []
        return (
            await self._req(
                "POST",
                alvo,
                headers=self._headers("return=representation"),
                content=json.dumps(linhas, default=str),
            )
            or []
        )

    async def _atualizar(
        self, alvo: str, params: dict[str, Any], campos: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return (
            await self._req(
                "PATCH",
                alvo,
                headers=self._headers("return=representation"),
                params=params,
                content=json.dumps(campos, default=str),
            )
            or []
        )

    async def _contar(self, alvo: str, params: dict[str, Any]) -> int:
        """Contagem exata, ou EXCEÇÃO. Nunca zero por falha.

        ⚠️ Antes esta função ignorava `status_code` e devolvia `0` para qualquer
        resposta sem `content-range` utilizável. O efeito era o pior possível na
        tela que ela alimenta: a biblioteca listava 60 ativos e dizia
        `total=0, universo=0`, ou seja, afirmava "está vazia" quando a verdade
        era "não consegui contar". A distinção entre filtro sem resultado e
        fonte vazia é exatamente o que estes dois números existem para fazer.
        """
        import httpx  # noqa: PLC0415

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as cli:
                r = await cli.head(
                    f"{self.base}/rest/v1/{alvo}",
                    headers=self._headers("count=exact"),
                    params={**params, "limit": 0},
                )
        except httpx.HTTPError as e:
            raise ErroDePersistencia("o banco não respondeu") from e
        if r.status_code >= 400:
            raise ErroDePersistencia(f"HEAD {alvo} -> {r.status_code}")
        total = (r.headers.get("content-range") or "").rsplit("/", 1)[-1]
        if not total.isdigit():
            raise ErroDePersistencia(f"HEAD {alvo}: contagem ausente na resposta")
        return int(total)

    # ── projeto e briefing ───────────────────────────────────────────────────

    # ── catálogo (parque criativo) ───────────────────────────────────────────
    # Métodos públicos de propósito. A primeira versão do `Resolvedor` chamava
    # `repo._get` direto, com um `# noqa: SLF001` por cima — e o dublê de teste,
    # que não tem método privado nenhum, quebrou 17 provas de uma vez. O `noqa`
    # não era ruído de linter: era o aviso de que a costura estava no lugar errado.

    async def listar_catalogo(
        self, tabela: str, colunas: str, ordem: str
    ) -> list[dict[str, Any]]:
        """Lê uma tabela de domínio inteira. Só as `criativo_*` do parque passam aqui."""
        return await self._get(tabela, {"select": colunas, "order": ordem})

    async def id_por_slug(self, tabela: str, coluna: str, valor: str) -> str | None:
        """`slug` → `id`, ou `None` quando não há linha. Ausência não é erro."""
        linhas = await self._get(
            tabela, {"select": "id", coluna: f"eq.{valor}", "limit": "1"}
        )
        return str(linhas[0]["id"]) if linhas else None

    async def criar_projeto(
        self, titulo: str, objetivo: str | None, brand_pack_id: str | None,
        dono_id: str | None, origem: str = "standalone",
    ) -> dict[str, Any]:
        return await self._inserir(
            _TABELA_PROJETO,
            {
                "titulo": titulo,
                "objetivo": objetivo,
                "brand_pack_id": brand_pack_id,
                "dono_id": dono_id,
                "origem": origem,
            },
        )

    async def atualizar_projeto(self, projeto_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
        linhas = await self._atualizar(
            _TABELA_PROJETO, {"id": f"eq.{projeto_id}"}, campos
        )
        return linhas[0] if linhas else None

    async def criar_briefing(self, linha: dict[str, Any]) -> dict[str, Any]:
        return await self._inserir(_TABELA_BRIEFING, linha)

    async def buscar_projeto(self, projeto_id: str) -> dict[str, Any] | None:
        linhas = await self._get(
            _TABELA_PROJETO, {"id": f"eq.{projeto_id}", "select": "*", "limit": 1}
        )
        return linhas[0] if linhas else None

    async def projetos_por_id(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        """Vários projetos numa consulta. Evita N+1 ao desenhar a biblioteca."""
        if not ids:
            return {}
        linhas = await self._get(
            _TABELA_PROJETO, {"id": f"in.({','.join(sorted(set(ids)))})", "select": "*"}
        )
        return {str(l["id"]): l for l in linhas}

    async def buscar_briefing(self, briefing_id: str) -> dict[str, Any] | None:
        linhas = await self._get(
            _TABELA_BRIEFING, {"id": f"eq.{briefing_id}", "select": "*", "limit": 1}
        )
        return linhas[0] if linhas else None

    # ── job ──────────────────────────────────────────────────────────────────

    async def criar_job_idempotente(
        self, linha: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        """Devolve `(job, foi_criado)`.

        `foi_criado=False` significa que a chave já existia e este é o job de
        antes. O chamador precisa saber a diferença para responder 200 em vez de
        201 e para NÃO disparar uma segunda execução paga.
        """
        try:
            return await self._inserir(_TABELA_JOB, linha), True
        except ConflitoDeChave:
            existente = await self.job_por_chave(linha["idempotency_key"])
            if existente is None:
                # A chave conflitou e o job não aparece: só acontece se alguém
                # apagou entre as duas chamadas. Não inventamos um job novo.
                raise ErroDePersistencia(
                    "conflito de chave sem job correspondente"
                ) from None
            return existente, False

    async def job_por_chave(self, chave: str) -> dict[str, Any] | None:
        linhas = await self._get(
            _TABELA_JOB, {"idempotency_key": f"eq.{chave}", "select": "*", "limit": 1}
        )
        return linhas[0] if linhas else None

    async def buscar_job(
        self, job_id: str, *, criado_por: str | None = None
    ) -> dict[str, Any] | None:
        """⚠️ `criado_por` NAO e opcional por conveniencia — e opcional porque o
        executor, que ja tem o job na mao, nao precisa reprovar posse a cada
        transicao. Toda leitura vinda de HTTP passa o dono, e a rota nunca chama
        sem ele. E a mesma regra que `bancada.deposito.por_id` ja escrevia."""
        params: dict[str, Any] = {"id": f"eq.{job_id}", "select": "*", "limit": 1}
        if criado_por is not None:
            params["criado_por"] = f"eq.{criado_por}"
        linhas = await self._get(_TABELA_JOB, params)
        return linhas[0] if linhas else None

    async def listar_jobs(
        self, *, estados: list[str] | None = None, limite: int = 20,
        criado_por: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "select": "*",
            "order": "criado_em.desc",
            "limit": limite,
        }
        if criado_por is not None:
            params["criado_por"] = f"eq.{criado_por}"
        if estados:
            params["estado"] = f"in.({','.join(estados)})"
        return await self._get(_TABELA_JOB, params)

    async def atualizar_job(self, job_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
        linhas = await self._atualizar(_TABELA_JOB, {"id": f"eq.{job_id}"}, campos)
        return linhas[0] if linhas else None

    async def contar_jobs_por_estado(
        self, *, criado_por: str | None = None
    ) -> dict[str, int]:
        """Contagem por estado, uma consulta por estado.

        Sem `group by` porque o PostgREST não expõe agregação sem uma view, e
        criar view para sete `HEAD` de custo O(índice) é complexidade que não se
        paga. As sete contagens são exatas: nenhuma delas estima.
        """
        estados = (
            "draft", "queued", "running", "partial",
            "succeeded", "failed", "cancelled",
        )
        base: dict[str, Any] = {}
        if criado_por:
            base["criado_por"] = f"eq.{criado_por}"
        saida: dict[str, int] = {}
        for e in estados:
            saida[e] = await self._contar(_TABELA_JOB, {**base, "estado": f"eq.{e}"})
        return saida

    # ── eventos ──────────────────────────────────────────────────────────────

    async def registrar_evento(
        self, job_id: str, fase: str, mensagem: str | None = None,
        *, percentual: float | None = None, slot: str | None = None,
        detalhe: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._inserir(
            _TABELA_EVENTO,
            {
                "job_id": job_id,
                "fase": fase,
                "mensagem": mensagem,
                # Nunca preenchido por conveniência: `None` é o valor correto
                # quando o motor não mede, e a coluna não tem default.
                "percentual": percentual,
                "slot": slot,
                "detalhe": detalhe,
            },
        )

    async def eventos_desde(
        self, job_id: str, desde: int = 0, limite: int = 200
    ) -> list[dict[str, Any]]:
        return await self._get(
            _TABELA_EVENTO,
            {
                "job_id": f"eq.{job_id}",
                "seq": f"gt.{desde}",
                "select": "*",
                "order": "seq.asc",
                "limit": limite,
            },
        )

    async def ultimo_seq(self, job_id: str) -> int:
        linhas = await self._get(
            _TABELA_EVENTO,
            {"job_id": f"eq.{job_id}", "select": "seq", "order": "seq.desc", "limit": 1},
        )
        return int(linhas[0]["seq"]) if linhas else 0

    # ── renditions ───────────────────────────────────────────────────────────

    async def criar_renditions(self, linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return await self._inserir_muitos(_TABELA_RENDITION, linhas)

    async def renditions_do_job(self, job_id: str) -> list[dict[str, Any]]:
        return await self._get(
            _TABELA_RENDITION,
            {"job_id": f"eq.{job_id}", "select": "*", "order": "slot.asc"},
        )

    async def atualizar_rendition(
        self, job_id: str, slot: str, campos: dict[str, Any]
    ) -> dict[str, Any] | None:
        linhas = await self._atualizar(
            _TABELA_RENDITION, {"job_id": f"eq.{job_id}", "slot": f"eq.{slot}"}, campos
        )
        return linhas[0] if linhas else None

    # ── master ───────────────────────────────────────────────────────────────

    async def criar_master(self, linha: dict[str, Any]) -> dict[str, Any]:
        return await self._inserir(_TABELA_MASTER, linha)

    #: O embed que amarra o master ao dono do job, numa consulta só.
    #:
    #: ⚠️ `!inner` e nao embed comum. Sem o `!inner`, o PostgREST devolve a linha
    #: do master com o embed NULO quando o filtro nao casa — isto e, devolve o
    #: ativo alheio com o dono em branco, que e pior que o vazamento original
    #: porque parece filtrado. Com `!inner` a linha some da resposta.
    #:
    #: E o filtro vai no SERVIDOR: filtrar em memoria depois de ler tudo faz o
    #: `limit`/`offset` pagina sobre o conjunto errado, e a contagem mente.
    _EMBED_DONO = "*,criativo_job!inner(criado_por)"

    async def buscar_master_do_dono(
        self, master_id: str, *, criado_por: str
    ) -> dict[str, Any] | None:
        """Um master, e só se o job dele for do `criado_por`.

        ⚠️ `criado_por` e OBRIGATORIO no contrato, e nao um filtro opcional que a
        rota lembra de passar. A versao anterior — `buscar_master(master_id)` —
        nao tinha por onde exigir posse, e as rotas ligavam a identidade a `_`.
        Uma porta que aceita ser chamada sem dono acaba sendo chamada sem dono.

        `criativo_master.job_id` e `not null` e aponta para `criativo_job`, onde
        `criado_por` vive: a posse do ativo SEMPRE resolve pelo job, e nao ha
        ativo orfao para escapar por essa fresta.
        """
        linhas = await self._get(
            _TABELA_MASTER,
            {
                "id": f"eq.{master_id}",
                "select": self._EMBED_DONO,
                "criativo_job.criado_por": f"eq.{criado_por}",
                "limit": 1,
            },
        )
        return _sem_embed(linhas[0]) if linhas else None

    async def versoes_do_master_do_dono(
        self, raiz_id: str, *, criado_por: str
    ) -> list[dict[str, Any]]:
        """A cadeia de versoes, sem atravessar o dono.

        ⚠️ Conferir so o master pedido nao basta: as VERSOES vao para o mesmo DTO,
        e uma raiz compartilhada entregaria a versao de outro dono junto.
        """
        return [
            _sem_embed(l)
            for l in await self._get(
                _TABELA_MASTER,
                {
                    "or": f"(id.eq.{raiz_id},raiz_id.eq.{raiz_id})",
                    "select": self._EMBED_DONO,
                    "criativo_job.criado_por": f"eq.{criado_por}",
                    "order": "versao.desc",
                },
            )
        ]

    async def buscar_master(self, master_id: str) -> dict[str, Any] | None:
        linhas = await self._get(
            _TABELA_MASTER, {"id": f"eq.{master_id}", "select": "*", "limit": 1}
        )
        return linhas[0] if linhas else None

    async def procedencia_dos_jobs(self, ids: list[str]) -> dict[str, str]:
        """`job_id -> procedencia_execucao`, numa consulta.

        Existe porque a biblioteca lista `criativo_master` e a procedencia de
        EXECUCAO mora em `criativo_job`. Sem esta leitura, a camada de
        apresentacao nao tem como saber se o ativo foi produzido aqui ou apenas
        observado, e a tela afirmava autoria por omissao.
        """
        if not ids:
            return {}
        linhas = await self._get(
            _TABELA_JOB,
            {"id": f"in.({','.join(sorted(set(ids)))})",
             "select": "id,procedencia_execucao"},
        )
        return {str(l["id"]): l.get("procedencia_execucao") or "volc_os" for l in linhas}

    async def masters_do_job(self, job_id: str) -> list[dict[str, Any]]:
        return await self._get(
            _TABELA_MASTER, {"job_id": f"eq.{job_id}", "select": "*", "order": "slot.asc"}
        )

    async def versoes_do_master(self, raiz_id: str) -> list[dict[str, Any]]:
        return await self._get(
            _TABELA_MASTER,
            {
                "or": f"(id.eq.{raiz_id},raiz_id.eq.{raiz_id})",
                "select": "*",
                "order": "versao.desc",
            },
        )

    async def listar_masters_do_dono(
        self, *, criado_por: str, **filtros: Any
    ) -> tuple[list[dict[str, Any]], int, int]:
        """A biblioteca do dono. `criado_por` obrigatorio, e o filtro e do SERVIDOR.

        ⚠️ O `universo` tambem passa a ser do dono. Um universo global faria a
        tela dizer "a biblioteca tem N ativos" contando os de outras pessoas —
        vazamento de CONTAGEM, que e menos obvio e igualmente real.
        """
        return await self.listar_masters(criado_por=criado_por, **filtros)

    async def listar_masters(
        self,
        *,
        criado_por: str | None = None,
        busca: str | None = None,
        kind: str | None = None,
        brand_pack_id: str | None = None,
        desde: str | None = None,
        ate: str | None = None,
        limite: int = 60,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Devolve `(linhas, total_do_filtro, universo)`.

        Os dois números existem porque DESIGN.md pede que a contagem declare "o
        subconjunto visível E o universo". Sem o universo, "0 resultados" não
        distingue "o filtro não achou" de "a biblioteca está vazia", e essas
        duas telas precisam ser diferentes.
        """
        params: dict[str, Any] = {
            "select": self._EMBED_DONO if criado_por else "*",
            "order": "criado_em.desc",
            "limit": limite,
            "offset": offset,
            "arquivado_em": "is.null",
        }
        filtro: dict[str, Any] = {"arquivado_em": "is.null"}
        if criado_por:
            params["criativo_job.criado_por"] = f"eq.{criado_por}"
            params["select"] = self._EMBED_DONO
            filtro["select"] = self._EMBED_DONO
            filtro["criativo_job.criado_por"] = f"eq.{criado_por}"
        if kind:
            params["kind"] = filtro["kind"] = f"eq.{kind}"
        if brand_pack_id:
            params["brand_pack_id"] = filtro["brand_pack_id"] = f"eq.{brand_pack_id}"
        if desde:
            params["criado_em"] = filtro["criado_em"] = f"gte.{desde}"
        if ate:
            # `criado_em` já pode estar ocupado por `desde`: o PostgREST aceita
            # a forma `and=(...)` para dois predicados na mesma coluna.
            faixa = f"(criado_em.gte.{desde},criado_em.lte.{ate})" if desde else None
            if faixa:
                params.pop("criado_em", None)
                filtro.pop("criado_em", None)
                params["and"] = filtro["and"] = faixa
            else:
                params["criado_em"] = filtro["criado_em"] = f"lte.{ate}"
        if busca:
            # ⚠️ Antes isto filtrava por `slot`, e só. O campo se chama "Buscar"
            # na tela: digitar o nome do projeto, "natal" ou "black friday"
            # devolvia sempre zero, com o contador dizendo que existiam N peças.
            # Um campo de busca que nunca acha é pior que a ausência dele.
            alvo = busca.replace("*", "").replace(",", " ").replace("(", "").replace(")", "").strip()
            if alvo:
                termo = f"*{alvo}*"
                # `or` do PostgREST: slot OU motor OU hash. O título do projeto
                # vive em outra tabela e entra quando houver embed; declarar o
                # alcance é melhor que fingir busca textual completa.
                expr = f"(slot.ilike.{termo},motor.ilike.{termo},content_hash.ilike.{termo})"
                params["or"] = filtro["or"] = expr

        linhas = [_sem_embed(l) for l in await self._get(_TABELA_MASTER, params)]
        total = await self._contar(_TABELA_MASTER, filtro)
        universo_filtro: dict[str, Any] = {"arquivado_em": "is.null"}
        if criado_por:
            universo_filtro["select"] = self._EMBED_DONO
            universo_filtro["criativo_job.criado_por"] = f"eq.{criado_por}"
        universo = await self._contar(_TABELA_MASTER, universo_filtro)
        return linhas, total, universo

    # ── aprovação ────────────────────────────────────────────────────────────

    async def criar_aprovacao(self, linha: dict[str, Any]) -> dict[str, Any]:
        return await self._inserir(_TABELA_APROVACAO, linha)

    async def revogar_aprovacao(
        self, aprovacao_id: str, ator_id: str
    ) -> dict[str, Any] | None:
        """Marca a decisão como revogada. Não apaga: o histórico é append-only."""
        linhas = await self._atualizar(
            _TABELA_APROVACAO,
            {"id": f"eq.{aprovacao_id}", "revogada_em": "is.null"},
            {"revogada_em": agora(), "revogada_por": ator_id},
        )
        return linhas[0] if linhas else None

    async def aprovacoes_de(
        self, subject_tipo: str, subject_id: str
    ) -> list[dict[str, Any]]:
        return await self._get(
            _TABELA_APROVACAO,
            {
                "subject_tipo": f"eq.{subject_tipo}",
                "subject_id": f"eq.{subject_id}",
                "select": "*",
                "order": "decidido_em.desc",
            },
        )

    async def aprovacoes_vigentes_de(
        self, ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Decisão vigente por master, em UMA consulta.

        Uma consulta por item transformaria a listagem da biblioteca em N+1, e
        com 60 cards isso é 61 viagens ao banco para desenhar uma grade.
        """
        if not ids:
            return {}
        linhas = await self._get(
            _TABELA_APROVACAO,
            {
                "subject_tipo": "eq.master",
                "subject_id": f"in.({','.join(ids)})",
                "revogada_em": "is.null",
                "select": "*",
                "order": "decidido_em.desc",
            },
        )
        saida: dict[str, dict[str, Any]] = {}
        for linha in linhas:
            saida.setdefault(str(linha["subject_id"]), linha)
        return saida

    async def masters_aguardando_revisao(
        self, limite: int = 12, *, criado_por: str | None = None
    ) -> list[dict[str, Any]]:
        """Masters sem decisão vigente.

        Feito em duas consultas e um `set` em Python, e não com `not.in`
        aninhado do PostgREST, porque a forma aninhada silenciosamente devolve
        tudo quando a subconsulta é vazia. Um "aguardando revisão" que lista a
        biblioteca inteira no primeiro dia é pior que uma consulta a mais.
        """
        candidatos = await self._get(
            _TABELA_MASTER,
            {
                "select": self._EMBED_DONO if criado_por else "*",
                **({"criativo_job.criado_por": f"eq.{criado_por}"} if criado_por else {}),
                "arquivado_em": "is.null",
                "order": "criado_em.desc",
                "limit": max(limite * 4, 40),
            },
        )
        if not candidatos:
            return []
        vigentes = await self.aprovacoes_vigentes_de([str(m["id"]) for m in candidatos])
        return [m for m in candidatos if str(m["id"]) not in vigentes][:limite]

    async def masters_aprovados_recentes(
        self, limite: int = 6, *, criado_por: str | None = None
    ) -> list[dict[str, Any]]:
        aprovacoes = await self._get(
            _TABELA_APROVACAO,
            {
                "subject_tipo": "eq.master",
                "decisao": "eq.aprovado",
                "revogada_em": "is.null",
                "select": "subject_id,decidido_em",
                "order": "decidido_em.desc",
                "limit": limite,
            },
        )
        ids = [str(a["subject_id"]) for a in aprovacoes]
        if not ids:
            return []
        linhas = await self._get(
            _TABELA_MASTER,
            {
                "id": f"in.({','.join(ids)})",
                "select": self._EMBED_DONO if criado_por else "*",
                **({"criativo_job.criado_por": f"eq.{criado_por}"} if criado_por else {}),
            },
        )
        ordem = {mid: i for i, mid in enumerate(ids)}
        return sorted(linhas, key=lambda m: ordem.get(str(m["id"]), 999))

    # ── brand packs ──────────────────────────────────────────────────────────

    async def listar_brand_packs(self) -> list[dict[str, Any]]:
        return await self._get(
            _TABELA_BRAND,
            {"select": "*", "ativo": "is.true", "order": "slug.asc,versao.desc"},
        )

    async def contar_assets(self, *, criado_por: str | None = None) -> int:
        """⚠️ `criado_por` chega aqui porque `/resumo` contava a biblioteca de
        TODO MUNDO. Vazamento de CONTAGEM e menos obvio que vazamento de linha e
        igualmente real: a tela dizia "a biblioteca tem N ativos" somando os de
        outras pessoas."""
        filtro: dict[str, Any] = {"arquivado_em": "is.null"}
        if criado_por:
            filtro["select"] = self._EMBED_DONO
            filtro["criativo_job.criado_por"] = f"eq.{criado_por}"
        return await self._contar(_TABELA_MASTER, filtro)
