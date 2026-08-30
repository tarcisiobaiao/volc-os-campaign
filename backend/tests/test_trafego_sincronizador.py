"""A varredura — idempotência, degradação, recuo, limite e somente leitura.

⚠️ NENHUM teste aqui fala com a conta real. O Google Ads entra por dublê, e a
razão não é comodidade: a suíte roda em CI e em máquina de desenvolvedor, e uma
leitura real gastaria quota da conta de um cliente para provar coisas que a
lógica já decide sozinha. O que precisa de conta real é o `validate_only` de
`test_trafego.py`, que é leitura e é gratuito.

As asserções são sobre INVARIANTES: "a conta que falha não perde o snapshot
bom" continua verdade amanhã; "duas campanhas" não.
"""
from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence

import pytest

from app.trafego import adaptador_search as ads
from app.trafego import dominio as dom
from app.trafego import inventario as inv
from app.trafego import sincronizador as sinc

AGORA = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── dublês ──────────────────────────────────────────────────────────────────


def linha_de_campanha(kid: str, *, nome: str = "", status: str = "ENABLED",
                      canal: str = "SEARCH", estrategia: str = "MANUAL_CPC",
                      verba: int = 10_000_000) -> Any:
    return SimpleNamespace(
        campaign=SimpleNamespace(
            id=kid, name=nome or f"campanha {kid}", status=status,
            serving_status="SERVING", advertising_channel_type=canal,
            bidding_strategy_type=estrategia),
        campaign_budget=SimpleNamespace(amount_micros=verba))


def linha_de_metrica(kid: str, impressoes: int, cliques: int, custo: int) -> Any:
    return SimpleNamespace(
        campaign=SimpleNamespace(id=kid),
        metrics=SimpleNamespace(impressions=impressoes, clicks=cliques,
                                cost_micros=custo))


def linha_de_lance(kid: str, grupo: str, micros: int) -> Any:
    return SimpleNamespace(
        campaign=SimpleNamespace(id=kid),
        ad_group=SimpleNamespace(id=grupo, cpc_bid_micros=micros))


class BuscaFalsa:
    """Um `buscar(gaql)` que responde por tipo de consulta e registra tudo.

    Passa cada query pelo `_exigir_leitura` de verdade — assim o dublê não
    esconde uma consulta que o código real recusaria.
    """

    def __init__(self, campanhas=(), metricas=(), lances=(),
                 falhar_em: Sequence[str] = ()) -> None:
        self.campanhas = list(campanhas)
        self.metricas = list(metricas)
        self.lances = list(lances)
        self.falhar_em = tuple(falhar_em)
        self.consultas: List[str] = []

    def __call__(self, gaql: str) -> List[Any]:
        query = sinc._exigir_leitura(gaql)
        self.consultas.append(query)
        for marca in self.falhar_em:
            if marca in query:
                raise RuntimeError(f"a API recusou: {marca}")
        if "FROM ad_group" in query:
            return list(self.lances)
        if "metrics." in query:
            return list(self.metricas)
        return list(self.campanhas)


class RecusadoPeloBanco(RuntimeError):
    """O que o Postgres recusaria — uma CHECK, uma FK ou um gatilho.

    ⚠️ O NOME IMPORTA. O dublê anterior aceitava qualquer dicionário, e por isso
    a suíte ficou verde enquanto o código escrevia em três tabelas que nenhuma
    migration cria, com `presenca='presente'` (fora da CHECK) e
    `tentativa_resultado='parcial'` (idem). Um dublê permissivo não mede o
    banco: mede a nossa imaginação sobre ele.
    """


class RepoFalso:
    """Um dublê que RECUSA o que `v9_01_trafego_inventario.sql` recusaria.

    Ele implementa as quatro tabelas que a varredura escreve, com as CHECK
    constraints e os gatilhos que mudam o resultado:

    · `trafego_campanha` — identidade, com o gatilho de imutabilidade;
    · `trafego_campanha_espelho` — leitura corrente, com a preservação da última
      entrega boa e a recusa de leitura retroativa;
    · `trafego_snapshot_conta` — carimbo, com a preservação da última leitura boa
      e o gatilho que apenda a tentativa no diário;
    · `trafego_evento` — append-only.

    Não é o banco, e não substitui `scripts/testar_migration_descartavel.sh`,
    que roda os gatilhos de verdade num cluster. O que ele garante é mais
    modesto e ainda assim decisivo: **um payload que o banco recusaria falha
    aqui**, em vez de passar e explodir na primeira gravação real.
    """

    #: Os seis do ADR-13. `presente` NÃO está aqui de propósito — no banco o
    #: caso normal é NULO, e gravar a sétima palavra é erro de constraint.
    PRESENCAS = frozenset((
        "removida", "nao_encontrada", "conta_nao_identificada",
        "fora_de_escopo", "sincronizacao_falhou", "legado_nao_reconciliado",
    ))
    RESULTADOS = frozenset(("ok", "falhou"))
    SUJEITOS = frozenset(("campanha", "conta", "linhagem", "vinculo", "sistema"))
    PROCEDENCIAS = frozenset(("volc_os", "descoberta", "legado", "desconhecida"))

    def __init__(self) -> None:
        self.identidade: Dict[str, Dict[str, Any]] = {}   # volc_campaign_id → linha
        self.espelho: Dict[str, Dict[str, Any]] = {}      # volc_campaign_id → linha
        self.snapshot: Dict[str, Dict[str, Any]] = {}     # customer_id → linha
        self.eventos: List[Dict[str, Any]] = []

    # ── helpers de constraint ───────────────────────────────────────────────

    @staticmethod
    def _conta_valida(cid: Any) -> str:
        texto = str(cid or "")
        if not re.fullmatch(r"[0-9]{6,12}", texto):
            raise RecusadoPeloBanco(
                f"trafego_*_customer_id_valido: {texto!r} não é conta")
        return texto

    @staticmethod
    def _uuid(valor: Any, campo: str) -> str:
        texto = str(valor or "")
        try:
            uuid.UUID(texto)
        except (ValueError, AttributeError, TypeError) as exc:
            raise RecusadoPeloBanco(
                f"{campo} é uuid no schema canônico; recebeu {texto!r}") from exc
        return texto

    @staticmethod
    def _dt(valor: Any) -> Optional[datetime]:
        if not valor:
            return None
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

    # ── trafego_evento ──────────────────────────────────────────────────────

    async def registrar_evento(self, evento: Dict[str, Any]) -> None:
        for campo in ("tipo", "chave_de_agrupamento", "produtor"):
            if not str(evento.get(campo) or "").strip():
                raise RecusadoPeloBanco(f"trafego_evento_{campo}_nao_vazio")
        sujeito = evento.get("sujeito_tipo")
        if sujeito is not None and sujeito not in self.SUJEITOS:
            raise RecusadoPeloBanco("trafego_evento_sujeito_conhecido")
        if evento.get("customer_id") is not None:
            self._conta_valida(evento["customer_id"])
        self.eventos.append(copy.deepcopy(evento))

    async def rodada_concluida(self, chave: str) -> Optional[Dict[str, Any]]:
        for e in reversed(self.eventos):
            if e.get("chave_de_agrupamento") == chave:
                return e
        return None

    # ── trafego_snapshot_conta ──────────────────────────────────────────────

    async def ultima_tentativa(self, customer_id: str) -> Optional[datetime]:
        linha = self.snapshot.get(str(customer_id))
        return self._dt(linha.get("tentativa_em")) if linha else None

    async def gravar_snapshot_de_conta(self, linha: Dict[str, Any]) -> None:
        cid = self._conta_valida(linha.get("customer_id"))
        # ⚠️ O PAYLOAD É LITERAL: chave presente com `null` APAGA a coluna,
        # chave ausente PRESERVA. Um dublê que filtrasse nulos aqui esconderia
        # metade do contrato — é justamente a diferença entre `tentativa_motivo`
        # (sempre enviado, para não herdar a falha anterior) e `leitura_boa_*`
        # (omitido, para a tentativa ruim não apagar a última leitura boa).
        nova = dict(linha)

        resultado = nova.get("tentativa_resultado")
        if resultado not in self.RESULTADOS:
            raise RecusadoPeloBanco(
                f"trafego_snapshot_resultado_conhecido: {resultado!r} não é "
                f"'ok' nem 'falhou' — a varredura tem três desfechos e a coluna "
                f"tem dois")
        if resultado == "falhou" and not str(nova.get("tentativa_motivo") or "").strip():
            raise RecusadoPeloBanco("trafego_snapshot_falha_tem_motivo")
        if not nova.get("tentativa_em"):
            raise RecusadoPeloBanco("tentativa_em é NOT NULL")
        if (nova.get("leitura_boa_em") is None) != (nova.get("leitura_boa_campanhas") is None):
            raise RecusadoPeloBanco("trafego_snapshot_leitura_boa_completa")

        anterior = self.snapshot.get(cid)
        if anterior is None:
            self.snapshot[cid] = nova
            await self._diario_da_tentativa(nova)
            return

        # Gatilho `trafego_snapshot_preserva_ultima_boa`.
        if self._dt(nova["tentativa_em"]) < self._dt(anterior["tentativa_em"]):
            raise RecusadoPeloBanco("tentativa retroativa recusada")
        fundida = {**anterior, **nova}
        boa_antiga = self._dt(anterior.get("leitura_boa_em"))
        boa_nova = self._dt(nova.get("leitura_boa_em"))
        if boa_antiga is not None and (boa_nova is None or boa_nova < boa_antiga):
            fundida["leitura_boa_em"] = anterior.get("leitura_boa_em")
            fundida["leitura_boa_campanhas"] = anterior.get("leitura_boa_campanhas")
            fundida["leitura_boa_duracao_ms"] = anterior.get("leitura_boa_duracao_ms")
        self.snapshot[cid] = fundida
        await self._diario_da_tentativa(fundida)

    async def _diario_da_tentativa(self, linha: Dict[str, Any]) -> None:
        """O gatilho `trafego_snapshot_registra_tentativa`, do lado do banco.

        Está aqui porque a ausência dele mudaria uma prova: o teste que conta os
        eventos de uma varredura precisa ver o diário que o BANCO escreve, e não
        só o que a aplicação apenda.
        """
        await self.registrar_evento({
            "ocorrido_em": linha["tentativa_em"],
            "tipo": f"sincronizacao.conta.{linha['tentativa_resultado']}",
            "chave_de_agrupamento": f"sincronizacao.conta:{linha['customer_id']}",
            "produtor": "banco:trafego_snapshot_registra_tentativa",
            "sujeito_tipo": "conta",
            "sujeito_id": linha["customer_id"],
            "customer_id": linha["customer_id"],
            "carga": {"resultado": linha["tentativa_resultado"],
                      "motivo": linha.get("tentativa_motivo")},
        })

    # ── trafego_campanha ────────────────────────────────────────────────────

    async def identidades(self, customer_id: str) -> Dict[str, Dict[str, Any]]:
        return {l["campaign_id"]: dict(l) for l in self.identidade.values()
                if l.get("customer_id") == str(customer_id)}

    async def declarar_identidades(self, linhas: List[Dict[str, Any]]) -> None:
        for l in linhas:
            vid = self._uuid(l.get("volc_campaign_id"), "trafego_campanha.volc_campaign_id")
            self._conta_valida(l.get("customer_id"))
            if not re.fullmatch(r"[0-9]{1,20}", str(l.get("campaign_id") or "")):
                raise RecusadoPeloBanco("trafego_campanha_campaign_id_valido")
            if not str(l.get("criada_por") or "").strip():
                raise RecusadoPeloBanco("trafego_campanha_criador_nao_vazio")
            if l.get("procedencia") not in self.PROCEDENCIAS:
                raise RecusadoPeloBanco("trafego_campanha_procedencia_conhecida")
            if l.get("procedencia") != "desconhecida" and not (
                    str(l.get("procedencia_declarada_por") or "").strip()
                    and l.get("procedencia_declarada_em")):
                raise RecusadoPeloBanco("trafego_campanha_procedencia_tem_autor")
            # INSERT ... ON CONFLICT DO NOTHING: a identidade se declara uma vez.
            # ⚠️ Se isto virasse upsert, o gatilho de imutabilidade recusaria a
            # segunda varredura por causa de `criada_em`.
            self.identidade.setdefault(vid, {**l, "criada_em": l.get(
                "procedencia_declarada_em")})

    # ── trafego_campanha_espelho ────────────────────────────────────────────

    async def espelhos(self, customer_id: str) -> Dict[str, Dict[str, Any]]:
        das_minhas = {vid for vid, l in self.identidade.items()
                      if l.get("customer_id") == str(customer_id)}
        return {vid: dict(l) for vid, l in self.espelho.items() if vid in das_minhas}

    async def gravar_espelhos(self, linhas: List[Dict[str, Any]]) -> None:
        for l in linhas:
            vid = self._uuid(l.get("volc_campaign_id"), "espelho.volc_campaign_id")
            if vid not in self.identidade:
                raise RecusadoPeloBanco(
                    "FK trafego_campanha_espelho → trafego_campanha: espelho sem "
                    "identidade declarada")
            if not l.get("lido_em"):
                raise RecusadoPeloBanco("espelho.lido_em é NOT NULL")
            presenca = l.get("presenca")
            if presenca is not None and presenca not in self.PRESENCAS:
                raise RecusadoPeloBanco(
                    f"trafego_espelho_presenca_conhecida: {presenca!r} não está "
                    f"entre os seis (NULO é o caso normal)")
            tem_numero = any(l.get(c) is not None
                             for c in ("impressoes", "cliques", "custo_micros"))
            if tem_numero and not l.get("entrega_lida_em"):
                raise RecusadoPeloBanco("trafego_espelho_entrega_sem_carimbo")

            anterior = self.espelho.get(vid)
            if anterior is None:
                self.espelho[vid] = dict(l)
                continue
            if self._dt(l["lido_em"]) < self._dt(anterior["lido_em"]):
                raise RecusadoPeloBanco("leitura retroativa recusada")
            # Gatilho `trafego_espelho_preserva_ultima_boa`: o UPSERT monta o SET
            # a partir das chaves enviadas, e a entrega antiga fica com o carimbo
            # DELA quando a tentativa nova não mediu.
            fundida = {**anterior, **l}
            if "entrega_lida_em" not in l and anterior.get("entrega_lida_em"):
                for c in ("impressoes", "cliques", "custo_micros", "moeda",
                          "entrega_lida_em"):
                    fundida[c] = anterior.get(c)
            self.espelho[vid] = fundida

    async def marcar_ausentes(self, customer_id: str, vistos: Sequence[str],
                              quando: datetime) -> int:
        das_minhas = {vid for vid, l in self.identidade.items()
                      if l.get("customer_id") == str(customer_id)}
        n = 0
        for vid in das_minhas:
            linha = self.espelho.get(vid)
            if linha is None or vid in set(vistos):
                continue
            if linha.get("presenca") == inv.NAO_ENCONTRADA:
                continue
            linha["presenca"] = inv.NAO_ENCONTRADA
            linha["lido_em"] = quando.isoformat()
            n += 1
        return n

    # ── apoio para os testes ────────────────────────────────────────────────

    def linha(self, cid: str, campaign_id: str) -> Dict[str, Any]:
        """Identidade + espelho, achatados como a projeção os lê."""
        vid = sinc.volc_campaign_id(cid, campaign_id)
        return {**self.identidade.get(vid, {}), **self.espelho.get(vid, {})}

    def transicoes(self, cid: str, campaign_id: str) -> List[Dict[str, Any]]:
        from app.trafego import alertas as alr

        chave = alr.chave_de_estado(sinc.volc_campaign_id(cid, campaign_id))
        return [e for e in self.eventos if e.get("chave_de_agrupamento") == chave]


CONTA = {"customer_id": "8017851692", "nome": "Crédito Up", "moeda": "BRL",
         "fuso": "America/Sao_Paulo"}


def _busca_completa(**kw: Any) -> BuscaFalsa:
    return BuscaFalsa(
        campanhas=[linha_de_campanha("241"), linha_de_campanha("242")],
        metricas=[linha_de_metrica("241", 1, 0, 0),
                  linha_de_metrica("241", 3, 0, 0),
                  linha_de_metrica("242", 4, 0, 0)],
        lances=[linha_de_lance("241", "g1", 120_000),
                linha_de_lance("242", "g2", 120_000)],
        **kw)


# ── somente leitura ─────────────────────────────────────────────────────────


def test_a_varredura_recusa_o_que_nao_e_select():
    """Decisão que depende de ninguém colar a query errada não é decisão."""
    with pytest.raises(sinc.EscritaNoSincronizador):
        sinc._exigir_leitura("UPDATE campaign SET status = 'PAUSED'")
    with pytest.raises(sinc.EscritaNoSincronizador):
        sinc._exigir_leitura("SELECT campaign.id FROM campaign; DROP TABLE x")
    assert sinc._exigir_leitura(sinc.GAQL_CAMPANHAS).startswith("SELECT")


def test_o_modulo_nao_conhece_caminho_de_escrita():
    """Prova estática: nenhuma menção a `mutar`/`mutate` no sincronizador.

    A trava de `volc_ads/gads/modo.py` continua fechada porque este módulo nem
    sabe abri-la — e as duas guardas são independentes de propósito.
    """
    import pathlib

    fonte = (pathlib.Path(__file__).resolve().parents[1]
             / "app/trafego/sincronizador.py").read_text(encoding="utf-8")
    for proibido in ("mutate", "destravar", "FORGE_PERMITIR_ESCRITA"):
        assert proibido not in fonte, f"o sincronizador cita {proibido!r}"


@pytest.mark.anyio
async def test_a_varredura_nunca_chama_mutate():
    """O dublê explode se alguém tentar mutar — e ninguém tenta."""
    class ServicoQueExplode:
        def mutate(self, *a, **k):
            raise AssertionError("a varredura tentou MUTAR a conta")

        def search(self, **k):
            sinc._exigir_leitura(k["query"])
            return []

    leitor = sinc.leitor_google_ads("8017851692", login_customer_id="6016739364",
                                    servico=ServicoQueExplode())
    repo = RepoFalso()
    r = await sinc.sincronizar_conta(CONTA, repo, buscar=leitor, agora=AGORA)
    assert r.resultado == "ok"


# ── idempotência ────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_idempotencia_de_estado_duas_varreduras_nao_dobram_nada():
    """A segunda varredura SUBSTITUI as métricas. Somar dobraria o custo do mês."""
    repo = RepoFalso()
    for quando in (AGORA, AGORA + timedelta(minutes=20)):
        await sinc.sincronizar_conta(CONTA, repo, buscar=_busca_completa(),
                                     agora=quando)

    assert len(repo.espelho) == 2
    linha = repo.linha("8017851692", "241")
    assert linha["impressoes"] == 4          # 1 + 3 do dia, não 8
    assert linha["custo_micros"] == 0
    assert len(repo.snapshot) == 1
    # A identidade foi DECLARADA uma vez. Se `declarar_identidades` virasse
    # upsert, a segunda varredura reescreveria `criada_em` e o gatilho
    # `trafego_campanha_identidade_imutavel` recusaria a gravação inteira.
    assert len(repo.identidade) == 2


@pytest.mark.anyio
async def test_idempotencia_de_chamada_a_mesma_chave_nao_gasta_quota():
    """O retry do n8n reenvia a mesma chave; a segunda não toca no Google."""
    repo = RepoFalso()
    busca = _busca_completa()
    primeira = await sinc.sincronizar_conta(CONTA, repo, buscar=busca,
                                            chave_idempotencia="abc", agora=AGORA)
    consultas_depois_da_primeira = len(busca.consultas)

    segunda = await sinc.sincronizar_conta(CONTA, repo, buscar=busca,
                                           chave_idempotencia="abc", agora=AGORA)
    assert segunda.repetida is True
    assert segunda.lidas == primeira.lidas
    assert len(busca.consultas) == consultas_depois_da_primeira


def test_chave_derivada_do_balde_de_tempo():
    a = sinc.chave_de_janela("111", "LAST_30_DAYS", AGORA)
    b = sinc.chave_de_janela("111", "LAST_30_DAYS", AGORA + timedelta(minutes=5))
    c = sinc.chave_de_janela("111", "LAST_30_DAYS", AGORA + timedelta(minutes=30))
    assert a == b and a != c


def test_identidade_e_derivada_e_estavel():
    """Sorteada, um erro na consulta cunharia uma SEGUNDA identidade para a
    mesma campanha externa — o que `volcCampaignId` existe para impedir."""
    derivada = sinc.volc_campaign_id("8017851692", "241")
    assert sinc.volc_campaign_id("801-785-1692", "241") == derivada
    # ⚠️ E ela é um UUID. `trafego_campanha.volc_campaign_id` é `uuid`, então a
    # forma legível anterior (`gads-8017851692-241`) seria recusada pelo TIPO da
    # coluna na primeira gravação real — sem nenhum teste acusando.
    assert uuid.UUID(derivada).version == 5
    with pytest.raises(ValueError):
        sinc.volc_campaign_id("", "241")


def test_identidade_nao_muda_entre_processos():
    """Derivada de constante, e não de `hash()` — que muda a cada processo."""
    esperado = str(uuid.uuid5(sinc.ESPACO_DA_IDENTIDADE, "gads:8017851692:241"))
    assert sinc.volc_campaign_id("8017851692", "241") == esperado


# ── paginação ───────────────────────────────────────────────────────────────


def test_paginacao_consome_todas_as_paginas():
    """Ler só a primeira página faria uma conta grande aparecer truncada, e
    nada na resposta diria isso."""
    paginas = [SimpleNamespace(results=[linha_de_campanha(f"{i}{j}")
                                        for j in range(3)])
               for i in range(4)]

    class Pager:
        pages = paginas

    class Servico:
        def __init__(self):
            self.queries: List[str] = []

        def search(self, **k):
            self.queries.append(k["query"])
            # ⚠️ `page_size` NÃO é mais enviado. Ele existia na
            # `SearchGoogleAdsRequest` até a v20 e foi REMOVIDO na v21
            # (google-ads 31.x): passá-lo levanta TypeError antes de a
            # requisição sair. Este dublê EXIGIA o argumento — ou seja, o teste
            # verde provava que o código fazia a chamada que o SDK real recusa.
            # Descoberto na primeira varredura de verdade.
            assert "page_size" not in k, (
                "page_size voltou; a API v21 não o aceita e o SDK levanta"
            )
            return Pager()

    servico = Servico()
    buscar = sinc.leitor_google_ads("111", login_customer_id="6016739364",
                                    servico=servico)
    linhas = buscar(sinc.GAQL_CAMPANHAS)
    assert len(linhas) == 12
    assert servico.queries and servico.queries[0].startswith("SELECT")


def test_paginacao_aceita_dubles_sem_pages():
    class Servico:
        def search(self, **k):
            return [linha_de_campanha("1")]

    buscar = sinc.leitor_google_ads("111", login_customer_id="6016739364",
                                    servico=Servico())
    assert len(buscar(sinc.GAQL_CAMPANHAS)) == 1


# ── recuo e retentativa ─────────────────────────────────────────────────────


def test_recuo_cresce_e_o_terminal_nao_e_retentado():
    esperas: List[float] = []
    tentativas = {"n": 0}

    def falha_transitoria():
        tentativas["n"] += 1
        if tentativas["n"] < 3:
            raise RuntimeError("RESOURCE_EXHAUSTED")
        return "ok"

    resultado = sinc.com_recuo(
        falha_transitoria,
        politica=sinc.PoliticaDeRetentativa(tentativas=4, base_s=1.0, fator=2.0),
        dormir=esperas.append,
        classificar=lambda exc: sinc.Veredito(retentavel=True),
        sorteio=lambda a, b: 0.0)
    assert resultado == "ok"
    assert esperas == [1.0, 2.0]

    gastas = {"n": 0}

    def terminal():
        gastas["n"] += 1
        raise RuntimeError("USER_PERMISSION_DENIED")

    with pytest.raises(RuntimeError):
        sinc.com_recuo(terminal, dormir=esperas.append,
                       classificar=lambda exc: sinc.Veredito(retentavel=False))
    # Cinco tentativas contra uma permissão negada gastam segundos para chegar à
    # mesma resposta e atrasam as outras contas da rodada.
    assert gastas["n"] == 1


def test_o_recuo_respeita_o_atraso_sugerido_pela_api():
    esperas: List[float] = []
    with pytest.raises(RuntimeError):
        sinc.com_recuo(
            lambda: (_ for _ in ()).throw(RuntimeError("throttle")),
            politica=sinc.PoliticaDeRetentativa(tentativas=2),
            dormir=esperas.append,
            classificar=lambda exc: sinc.Veredito(retentavel=True,
                                                  espera_sugerida_s=7.0),
            sorteio=lambda a, b: 0.0)
    assert esperas == [7.0]


def test_o_jitter_existe_para_o_throttle_nao_se_perpetuar():
    pol = sinc.PoliticaDeRetentativa(base_s=10.0, jitter=0.25)
    assert pol.espera(0, sorteio=lambda a, b: a) == pytest.approx(7.5)
    assert pol.espera(0, sorteio=lambda a, b: b) == pytest.approx(12.5)


# ── limite de taxa ──────────────────────────────────────────────────────────


def test_limite_de_taxa_por_conta():
    ultimas = {"111": AGORA - timedelta(seconds=30)}
    limite = sinc.LimiteDeTaxa(ultimas.get, agora=lambda: AGORA)

    limite.exigir("222", "manual")          # nunca varrida: passa
    with pytest.raises(sinc.LimiteExcedido) as exc:
        limite.exigir("111", "manual")
    assert exc.value.proxima_em == AGORA - timedelta(seconds=30) + timedelta(seconds=300)

    ultimas["111"] = AGORA - timedelta(seconds=400)
    limite.exigir("111", "manual")


@pytest.mark.anyio
async def test_o_limite_bloqueia_antes_de_qualquer_consulta():
    repo = RepoFalso()
    busca = _busca_completa()
    limite = sinc.LimiteDeTaxa(lambda _c: AGORA - timedelta(seconds=1),
                               agora=lambda: AGORA)
    with pytest.raises(sinc.LimiteExcedido):
        await sinc.sincronizar_conta(CONTA, repo, buscar=busca, limite=limite,
                                     origem="manual", agora=AGORA)
    assert busca.consultas == []


# ── degradação ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_conta_que_falha_preserva_o_ultimo_snapshot_bom():
    repo = RepoFalso()
    await sinc.sincronizar_conta(CONTA, repo, buscar=_busca_completa(), agora=AGORA)
    antes = copy.deepcopy(repo.espelho)

    depois_de_falhar = await sinc.sincronizar_conta(
        CONTA, repo, buscar=BuscaFalsa(falhar_em=("FROM campaign",)),
        agora=AGORA + timedelta(hours=1))

    assert depois_de_falhar.resultado == "falhou"
    # ⚠️ O CORAÇÃO DA REGRA C: as linhas de espelho não foram tocadas.
    assert repo.espelho == antes

    conta = repo.snapshot["8017851692"]
    assert conta["tentativa_resultado"] == "falhou"
    # A última tentativa é nova; a última leitura BOA continua a antiga.
    assert conta["tentativa_em"] == (AGORA + timedelta(hours=1)).isoformat()
    assert conta["leitura_boa_em"] == AGORA.isoformat()
    assert "recusou" in conta["tentativa_motivo"]


@pytest.mark.anyio
async def test_entrega_que_nao_volta_vira_parcial_e_nao_apaga_a_medicao_boa():
    repo = RepoFalso()
    await sinc.sincronizar_conta(CONTA, repo, buscar=_busca_completa(), agora=AGORA)
    assert repo.linha("8017851692", "241")["impressoes"] == 4

    parcial = await sinc.sincronizar_conta(
        CONTA, repo,
        buscar=BuscaFalsa(campanhas=[linha_de_campanha("241"),
                                     linha_de_campanha("242")],
                          lances=[linha_de_lance("241", "g1", 120_000),
                                  linha_de_lance("242", "g2", 120_000)],
                          falhar_em=("metrics.",)),
        agora=AGORA + timedelta(hours=1))

    assert parcial.resultado == "parcial"
    assert parcial.faltou and "entrega" in parcial.faltou[0]["escopo"]
    # Sobrescrever com nulos apagaria a única medição que existe. O upsert nem
    # recebe as colunas de entrega.
    linha = repo.linha("8017851692", "241")
    assert linha["impressoes"] == 4
    assert linha["entrega_lida_em"] == AGORA.isoformat()
    assert linha["lido_em"] == (AGORA + timedelta(hours=1)).isoformat()

    # ⚠️ E o BANCO só conhece 'ok' e 'falhou'. O terceiro desfecho viaja em
    # `tentativa_motivo`, e `dominio.frescor_da_conta` o lê de volta como
    # `parcial` — sem uma coluna nova e sem um valor que a CHECK recusaria.
    conta = repo.snapshot["8017851692"]
    assert conta["tentativa_resultado"] == "ok"
    assert "entrega" in conta["tentativa_motivo"]
    assert dom.frescor_da_conta(
        resultado=conta["tentativa_resultado"],
        lido_em=datetime.fromisoformat(conta["leitura_boa_em"]),
        campanhas=conta["leitura_boa_campanhas"],
        motivo=conta["tentativa_motivo"],
        agora=AGORA + timedelta(hours=1),
    ) == "parcial"


@pytest.mark.anyio
async def test_campanha_sem_linha_de_metrica_e_zero_medido():
    """Ela não apareceu no leilão. Isso é ZERO, e zero não é ausência."""
    repo = RepoFalso()
    await sinc.sincronizar_conta(
        CONTA, repo,
        buscar=BuscaFalsa(campanhas=[linha_de_campanha("241")],
                          metricas=[], lances=[linha_de_lance("241", "g", 1)]),
        agora=AGORA)
    linha = repo.linha("8017851692", "241")
    assert linha["impressoes"] == 0 and linha["entrega_lida_em"] is not None


@pytest.mark.anyio
async def test_conta_vazia_de_verdade_e_declarada_como_vazia():
    repo = RepoFalso()
    r = await sinc.sincronizar_conta(CONTA, repo, buscar=BuscaFalsa(), agora=AGORA)
    assert r.resultado == "ok" and r.lidas == 0 and r.vazio_confirmado is True
    conta = repo.snapshot["8017851692"]
    # ⚠️ `vazio_confirmado` NÃO é coluna, e não ser é a decisão certa: ele é
    # derivado de "leitura boa com zero campanhas". Uma coluna própria seria uma
    # segunda fonte da mesma verdade, e duas fontes divergem.
    assert conta["leitura_boa_campanhas"] == 0
    assert conta["leitura_boa_em"] == AGORA.isoformat()
    assert dom.frescor_da_conta(
        resultado="ok", lido_em=AGORA, campanhas=conta["leitura_boa_campanhas"],
        agora=AGORA) == "vazio_confirmado"


@pytest.mark.anyio
async def test_campanha_que_some_da_leitura_boa_vira_nao_encontrada():
    repo = RepoFalso()
    await sinc.sincronizar_conta(CONTA, repo, buscar=_busca_completa(), agora=AGORA)

    await sinc.sincronizar_conta(
        CONTA, repo,
        buscar=BuscaFalsa(campanhas=[linha_de_campanha("241")],
                          metricas=[], lances=[linha_de_lance("241", "g", 1)]),
        agora=AGORA + timedelta(hours=1))

    assert repo.linha("8017851692", "242")["presenca"] == inv.NAO_ENCONTRADA
    # ⚠️ NULO, e não `presente`: a CHECK do banco aceita os seis estados OU
    # nulo, e nenhum dos seis nomeia "está lá, sem ressalva". A projeção traduz
    # esse nulo em `presente` na saída — o dublê recusaria a sétima palavra.
    assert repo.linha("8017851692", "241")["presenca"] is None
    assert dom.presenca_projetada(None, conta_falhou=False) == inv.PRESENTE


@pytest.mark.anyio
async def test_campanha_removida_e_removida_nao_nao_encontrada():
    """Ela ESTÁ na conta, marcada como removida — são fatos diferentes."""
    repo = RepoFalso()
    await sinc.sincronizar_conta(
        CONTA, repo,
        buscar=BuscaFalsa(campanhas=[linha_de_campanha("241", status="REMOVED")],
                          metricas=[], lances=[]),
        agora=AGORA)
    assert repo.linha("8017851692", "241")["presenca"] == inv.REMOVIDA


@pytest.mark.anyio
async def test_uma_conta_falha_e_a_rodada_continua():
    repo = RepoFalso()
    contas = [CONTA, {"customer_id": "3849678045", "nome": "PMUNDO+",
                      "moeda": "BRL"}]

    def fabrica(conta):
        if conta["customer_id"] == "3849678045":
            return BuscaFalsa(falhar_em=("FROM campaign",))
        return _busca_completa()

    saida = await sinc.sincronizar(contas, repo, fabrica_de_busca=fabrica,
                                   agora=AGORA)

    assert saida["parcial"] is True
    assert [f["customer_id"] for f in saida["faltou"]] == ["3849678045"]
    assert repo.snapshot["8017851692"]["tentativa_resultado"] == "ok"
    assert repo.snapshot["3849678045"]["tentativa_resultado"] == "falhou"
    assert len(repo.espelho) == 2      # só as da conta que respondeu


# ── observabilidade ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_a_varredura_registra_o_proprio_desempenho():
    """Sem isto, "a varredura está lenta" é opinião."""
    repo = RepoFalso()
    await sinc.sincronizar_conta(CONTA, repo, buscar=_busca_completa(),
                                 janela="LAST_7_DAYS", agora=AGORA,
                                 chave_idempotencia="obs-1")
    registro = repo.eventos[-1]
    assert registro["tipo"] == "trafego.sincronizacao.rodada"
    assert registro["customer_id"] == "8017851692"
    carga = registro["carga"]
    assert carga["janela"] == "LAST_7_DAYS"
    assert carga["origem"] == "agendado"
    assert carga["resultado"] == "ok"
    assert carga["lidas"] == 2
    assert carga["falhas"] == 0
    assert carga["consultas"] == 3        # camada comum + entrega + filhas
    assert carga["duracao_ms"] >= 0
    assert "faltou" in carga


@pytest.mark.anyio
async def test_a_falha_tambem_deixa_registro():
    repo = RepoFalso()
    await sinc.sincronizar_conta(CONTA, repo,
                                 buscar=BuscaFalsa(falhar_em=("FROM campaign",)),
                                 agora=AGORA)
    # ⚠️ A falha NÃO deixa evento de rodada — só sucesso é memorizado (regra D).
    # O que a registra é o diário que o gatilho do banco escreve por tentativa,
    # e ele é uma fonte diferente: um não substitui o outro.
    assert not [e for e in repo.eventos
                if e["tipo"] == "trafego.sincronizacao.rodada"]
    diario = repo.eventos[-1]
    assert diario["tipo"] == "sincronizacao.conta.falhou"
    assert diario["produtor"].startswith("banco:")


@pytest.mark.anyio
async def test_a_varredura_registra_a_transicao_de_estado_de_cada_campanha():
    """O diário de onde `horas_ligada` sai — e sem ele o alerta pediria GAQL.

    A primeira observação vem com `de=None`: não é "estava desligada", é "esta é
    a primeira vez que olhamos". `alertas.horas_ligada` lê isso como "a conta
    responde ENABLED desde este instante", que é a afirmação mais forte que os
    dados sustentam — e nunca uma data de criação inventada.
    """
    repo = RepoFalso()
    await sinc.sincronizar_conta(
        CONTA, repo,
        buscar=BuscaFalsa(campanhas=[linha_de_campanha("241")], metricas=[],
                          lances=[linha_de_lance("241", "g", 1)]),
        agora=AGORA)

    primeira = repo.transicoes("8017851692", "241")
    assert len(primeira) == 1
    assert primeira[0]["carga"] == {"de": None, "para": "ENABLED"}
    assert primeira[0]["sujeito_tipo"] == "campanha"

    # Uma varredura que vê o MESMO estado não apenda nada: o diário registra
    # mudança, e um evento por varredura o encheria de linhas sem informação.
    await sinc.sincronizar_conta(
        CONTA, repo,
        buscar=BuscaFalsa(campanhas=[linha_de_campanha("241")], metricas=[],
                          lances=[linha_de_lance("241", "g", 1)]),
        agora=AGORA + timedelta(hours=1))
    assert len(repo.transicoes("8017851692", "241")) == 1

    # E a mudança de verdade entra.
    await sinc.sincronizar_conta(
        CONTA, repo,
        buscar=BuscaFalsa(campanhas=[linha_de_campanha("241", status="PAUSED")],
                          metricas=[], lances=[linha_de_lance("241", "g", 1)]),
        agora=AGORA + timedelta(hours=2))
    transicoes = repo.transicoes("8017851692", "241")
    assert len(transicoes) == 2
    assert transicoes[-1]["carga"] == {"de": "ENABLED", "para": "PAUSED"}


@pytest.mark.anyio
async def test_uma_varredura_boa_apaga_o_motivo_da_falha_anterior():
    """O nulo que TEM de viajar — e o erro silencioso que ele evita.

    `tentativa_motivo` descreve a tentativa DE AGORA. Se o payload o omitisse
    por ser nulo (o idioma normal do upsert: "não mandei, não mexo"), o motivo
    da falha anterior ficaria colado na linha — e `dominio.frescor_da_conta`
    derivaria `parcial` para sempre numa conta perfeitamente saudável.

    Nada falha nesse cenário. A tela é que passa a mentir, indefinidamente, e é
    por isso que o teste existe.
    """
    repo = RepoFalso()
    await sinc.sincronizar_conta(
        CONTA, repo, buscar=BuscaFalsa(falhar_em=("FROM campaign",)), agora=AGORA)
    assert repo.snapshot["8017851692"]["tentativa_motivo"]

    await sinc.sincronizar_conta(CONTA, repo, buscar=_busca_completa(),
                                 agora=AGORA + timedelta(minutes=20))
    conta = repo.snapshot["8017851692"]
    assert conta.get("tentativa_motivo") is None
    assert dom.frescor_da_conta(
        resultado=conta["tentativa_resultado"],
        lido_em=datetime.fromisoformat(conta["leitura_boa_em"]),
        campanhas=conta["leitura_boa_campanhas"],
        motivo=conta.get("tentativa_motivo"),
        agora=AGORA + timedelta(minutes=20)) == "recente"


@pytest.mark.anyio
async def test_campanha_que_volta_a_ser_encontrada_perde_o_nao_encontrada():
    """O outro nulo que viaja: `presenca`.

    Omitir `presenca` quando ela é nula deixaria `nao_encontrada` grudada numa
    campanha que voltou a aparecer na conta — e a tela mostraria como sumida uma
    campanha que está gastando dinheiro agora.
    """
    repo = RepoFalso()
    completa = dict(campanhas=[linha_de_campanha("241"), linha_de_campanha("242")],
                    metricas=[], lances=[])
    await sinc.sincronizar_conta(CONTA, repo, buscar=BuscaFalsa(**completa),
                                 agora=AGORA)

    # 242 some da conta…
    await sinc.sincronizar_conta(
        CONTA, repo,
        buscar=BuscaFalsa(campanhas=[linha_de_campanha("241")], metricas=[],
                          lances=[]),
        agora=AGORA + timedelta(hours=1))
    assert repo.linha("8017851692", "242")["presenca"] == inv.NAO_ENCONTRADA

    # …e volta.
    await sinc.sincronizar_conta(CONTA, repo, buscar=BuscaFalsa(**completa),
                                 agora=AGORA + timedelta(hours=2))
    assert repo.linha("8017851692", "242")["presenca"] is None
    assert dom.presenca_projetada(
        repo.linha("8017851692", "242")["presenca"], conta_falhou=False
    ) == inv.PRESENTE


@pytest.mark.anyio
async def test_enum_de_canal_desconhecido_nao_derruba_a_conta_inteira():
    """A CHECK de canal é FECHADA, e o Google acrescenta valores ao enum.

    Com o valor cru no payload, um enum novo faria o INSERT ser recusado e a
    varredura da conta INTEIRA falhar — e o sintoma apareceria como
    "sincronização falhou" numa conta que respondeu perfeitamente. É o mesmo
    defeito que a migration evita em `estrategia` deixando a lista aberta.

    A troca por `UNKNOWN` é DECLARADA em `faltou`: perder o rótulo é aceitável,
    perder a conta não é, e trocar em silêncio seria pior que as duas coisas.
    """
    repo = RepoFalso()
    r = await sinc.sincronizar_conta(
        CONTA, repo,
        buscar=BuscaFalsa(campanhas=[linha_de_campanha("241", canal="CANAL_DO_FUTURO")],
                          metricas=[], lances=[]),
        agora=AGORA)

    assert repo.linha("8017851692", "241")["canal"] == "UNKNOWN"
    assert any("CANAL_DO_FUTURO" in f["motivo"] for f in r.faltou)
    assert r.resultado == "parcial", "a troca é uma perda, e ela é declarada"

    # E um canal legítimo continua chegando cru ao espelho.
    await sinc.sincronizar_conta(
        CONTA, repo,
        buscar=BuscaFalsa(campanhas=[linha_de_campanha("242", canal="DISPLAY")],
                          metricas=[], lances=[]),
        agora=AGORA + timedelta(minutes=1))
    assert repo.linha("8017851692", "242")["canal"] == "DISPLAY"


@pytest.mark.anyio
async def test_o_dubles_recusa_o_que_o_banco_recusaria():
    """A prova de que o dublê não é permissivo — senão ele não prova nada.

    Os três payloads abaixo são exatamente os que o código escrevia antes desta
    rodada, e os três seriam recusados pelo Postgres na primeira gravação real.
    """
    repo = RepoFalso()
    vid = sinc.volc_campaign_id("8017851692", "241")
    await repo.declarar_identidades([{
        "volc_campaign_id": vid, "customer_id": "8017851692",
        "campaign_id": "241", "procedencia": "descoberta",
        "procedencia_declarada_por": "t", "procedencia_declarada_em": AGORA.isoformat(),
        "criada_por": "t"}])

    with pytest.raises(RecusadoPeloBanco, match="presenca_conhecida"):
        await repo.gravar_espelhos([{"volc_campaign_id": vid,
                                     "lido_em": AGORA.isoformat(),
                                     "presenca": "presente"}])

    with pytest.raises(RecusadoPeloBanco, match="resultado_conhecido"):
        await repo.gravar_snapshot_de_conta({
            "customer_id": "8017851692", "tentativa_em": AGORA.isoformat(),
            "tentativa_resultado": "parcial"})

    with pytest.raises(RecusadoPeloBanco, match="entrega_sem_carimbo"):
        await repo.gravar_espelhos([{"volc_campaign_id": vid,
                                     "lido_em": AGORA.isoformat(),
                                     "impressoes": 4}])


# ── janela ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_janela_fora_do_vocabulario_e_recusada():
    """A janela entra concatenada no GAQL; texto livre ali é injeção."""
    repo = RepoFalso()
    with pytest.raises(sinc.JanelaInvalida):
        await sinc.sincronizar_conta(CONTA, repo, buscar=_busca_completa(),
                                     janela="DURING LAST_30_DAYS OR 1=1")


@pytest.mark.anyio
async def test_a_janela_escolhida_chega_ao_gaql():
    repo = RepoFalso()
    busca = _busca_completa()
    await sinc.sincronizar_conta(CONTA, repo, buscar=busca, janela="LAST_7_DAYS",
                                 agora=AGORA)
    assert any("LAST_7_DAYS" in q for q in busca.consultas)


# ── canal ───────────────────────────────────────────────────────────────────


def test_vocabulario_canonico_de_canal():
    assert inv.canal_canonico("DISCOVERY") == "DEMAND_GEN"
    assert inv.canal_canonico("PMAX") == "PERFORMANCE_MAX"
    assert inv.canal_canonico("PERFORMANCE_MAX") == "PERFORMANCE_MAX"
    # Canal que o produto não sabe operar sai `null` — devolver o valor cru
    # faria a tela renderizar um canal inexistente no contrato.
    assert inv.canal_canonico("TRAVEL") is None
    assert inv.canal_canonico(None) is None


@pytest.mark.anyio
async def test_canal_sem_adaptador_entra_no_inventario_e_declara_o_que_faltou():
    """Nem some, nem ganha tela vazia (ADR-19): entra com as colunas comuns."""
    repo = RepoFalso()
    r = await sinc.sincronizar_conta(
        CONTA, repo,
        buscar=BuscaFalsa(campanhas=[linha_de_campanha("900", canal="DISPLAY")],
                          metricas=[linha_de_metrica("900", 10, 1, 5000)]),
        agora=AGORA)

    assert r.resultado == "parcial"
    assert any("DISPLAY" in f["escopo"] for f in r.faltou)
    linha = repo.linha("8017851692", "900")
    assert linha["canal"] == "DISPLAY"
    assert linha["lance_micros"] is None      # ausência, não zero
    assert linha["impressoes"] == 10          # a camada comum veio inteira


def test_o_resolvedor_de_perfil_e_o_unico_lugar_que_conhece_search():
    assert sinc.resolver_perfil("SEARCH") is ads.PERFIL
    assert sinc.resolver_perfil("DISPLAY") is None
    assert sinc.resolver_perfil(None) is None


# ── o adaptador de Search ───────────────────────────────────────────────────


def test_o_perfil_search_le_o_lance_e_o_devolve_no_vocabulario_comum():
    busca = BuscaFalsa(lances=[linha_de_lance("241", "g1", 120_000)])
    saida = ads.PERFIL.ler_filhas(busca, ["241"])
    assert saida == {"241": {"lance_micros": 120_000}}
    assert ads.PERFIL.canal == "SEARCH"
    assert ads.PERFIL.entidades_filhas()


def test_lances_divergentes_devolvem_null_em_vez_de_escolher_um():
    """Dois grupos a R$0,12 e R$3,00 não têm "o lance da campanha", e
    `verba ÷ lance` em cima de um deles descreve um teto que não existe."""
    busca = BuscaFalsa(lances=[linha_de_lance("241", "g1", 120_000),
                               linha_de_lance("241", "g2", 3_000_000)])
    assert ads.PERFIL.ler_filhas(busca, ["241"]) == {"241": {"lance_micros": None}}


def test_sem_ids_o_perfil_nao_consulta_nada():
    """`IN ()` é erro de sintaxe no GAQL, e o erro que volta fala de parse."""
    busca = BuscaFalsa()
    assert ads.PERFIL.ler_filhas(busca, []) == {}
    assert busca.consultas == []


def test_campanha_sem_grupo_vivo_fica_com_lance_nulo():
    """Sem grupo vivo não há lance, e sem anúncio vivo não há destino.

    As duas ausências são declaradas, e nenhuma vira zero nem string vazia. O
    dublê responde a consulta de URL com nada — que é o caso de uma campanha
    pausada há meses, sem anúncio ativo.
    """
    busca = BuscaFalsa(lances=[])
    assert ads.PERFIL.ler_filhas(busca, ["241"]) == {
        "241": {"lance_micros": None, "url_final": None}}


def test_o_perfil_lote_os_ids_para_a_url_nao_estourar():
    """Dois lotes de consultas, um por entidade filha — e cada um respeita o teto.

    O perfil lê DUAS entidades: o grupo (lance) e o anúncio (URL final). Cada
    uma é uma varredura própria, e cada uma fatia os ids em lotes de 200 para o
    `IN (...)` não estourar o tamanho prático da URL do `search`. 450 ids viram
    3 lotes por entidade — 6 consultas, não 3.
    """
    ids = [str(i) for i in range(1, sinc.PAGINA_GAQL)]
    busca = BuscaFalsa(lances=[])
    ads.PERFIL.ler_filhas(busca, ids[:450])
    assert len(busca.consultas) == 6      # (200 + 200 + 50) x 2 entidades
    # Conta os ids DENTRO do `IN (...)` — contar vírgulas da consulta inteira
    # somaria as da lista de campos do SELECT.
    def _quantos_ids(consulta: str) -> int:
        dentro = consulta.split("IN (", 1)[1].split(")", 1)[0]
        return len([p for p in dentro.split(",") if p.strip()])

    lotes = [_quantos_ids(c) for c in busca.consultas]
    assert max(lotes) <= ads.LOTE_DE_IDS, f"lote passou do teto: {lotes}"
    assert sorted(lotes) == [50, 50, 200, 200, 200, 200], lotes


# ── schema ──────────────────────────────────────────────────────────────────


def test_o_schema_tem_UMA_fonte_e_ela_e_a_migration():
    """O DDL não pode viver dentro do código de aplicação.

    Havia uma constante `DDL_SNAPSHOT` neste módulo criando tabelas com nomes
    diferentes dos da migration, escrita na mesma rodada por outra frente. Duas
    fontes de schema é pior que nenhuma: a que vence é a que alguém executar
    primeiro, e ninguém revisa a que perdeu.

    Este teste guarda a decisão: o schema mora na migration versionada, que tem
    rollback e foi provada em cluster descartável.
    """
    from pathlib import Path

    import app.trafego.sincronizador as sinc

    assert not hasattr(sinc, "DDL_SNAPSHOT"), (
        "DDL_SNAPSHOT voltou. O schema mora em supabase/migrations/, não numa "
        "string dentro do sincronizador."
    )

    raiz = Path(__file__).resolve().parents[2]
    migration = raiz / sinc.SCHEMA_CANONICO
    assert migration.exists(), f"migration canônica sumiu: {sinc.SCHEMA_CANONICO}"

    sql = migration.read_text(encoding="utf-8")
    for tabela in (
        "trafego_campanha",
        "trafego_linhagem",
        "trafego_snapshot_conta",
        "trafego_campanha_espelho",
        "trafego_vinculo",
        "trafego_evento",
    ):
        assert tabela in sql, f"a migration canônica não cria {tabela}"

    # E ela não pode tocar nas tabelas legadas para fazê-las "parecer adequadas".
    assert "ALTER TABLE public.campaigns" not in sql
    assert "ALTER TABLE public.daily_campaign_metrics" not in sql


@pytest.fixture
def app_de_varredura():
    """App mínimo com o router novo, dublês injetados e portões abertos.

    O router NÃO é registrado em `main.py` por esta frente — quem registra é o
    integrador. Montar o app aqui prova que ele é registrável e que os portões
    de identidade estão nos lugares certos.
    """
    from fastapi import FastAPI

    from app.routers import trafego_inventario as rota
    from app.seguranca.identidade import (Identidade, exigir_admin,
                                          exigir_servico, exigir_usuario)

    repo = RepoFalso()
    buscas: List[BuscaFalsa] = []

    def fabrica(conta):
        b = _busca_completa()
        buscas.append(b)
        return b

    rota.definir_varredura(repo, fabrica)
    rota.definir_contas([CONTA])
    app = FastAPI()
    rota.registrar(app)

    def _abrir(papel: str) -> None:
        ident = Identidade(sub="u1", email="op@volc", papel=papel, origem="sessao")
        app.dependency_overrides[exigir_usuario] = lambda: ident
        app.dependency_overrides[exigir_admin] = lambda: ident
        app.dependency_overrides[exigir_servico] = lambda: Identidade(
            sub="svc", email="", papel="SERVICO", origem="servico")

    yield app, rota, repo, buscas, _abrir
    rota.definir_varredura(None, None)
    rota.definir_contas(None)
    app.dependency_overrides.clear()


def test_atualizacao_manual_declara_custo_e_escopo(app_de_varredura):
    """"Custo declarado" do SPEC §3.4: quantas consultas e quanto demorou."""
    from fastapi.testclient import TestClient

    app, _, repo, _, abrir = app_de_varredura
    abrir("ADMIN")
    with TestClient(app) as cliente:
        r = cliente.post("/api/trafego/inventario/atualizar",
                         json={"customer_id": "8017851692"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["escopo"] == {"customer_id": "8017851692", "nome": "Crédito Up",
                               "janela": "LAST_30_DAYS", "contas": 1}
    assert corpo["custo"]["consultas_gaql"] == 3
    assert corpo["custo"]["duracao_ms"] >= 0
    # Atualizar inventário e mudar campanha são naturezas diferentes, e a
    # segunda não está aprovada (ADR-11).
    assert corpo["escrita_permitida"] is False
    assert repo.snapshot["8017851692"]["tentativa_resultado"] == "ok"


def test_atualizacao_manual_e_limitada_por_conta(app_de_varredura):
    from fastapi.testclient import TestClient

    app, _, repo, buscas, abrir = app_de_varredura
    abrir("ADMIN")
    # Uma tentativa de dez segundos atrás: o limite de taxa lê o CARIMBO em
    # `trafego_snapshot_conta`, e não um contador de processo — com dois
    # workers, um contador em memória libera o dobro das varreduras.
    repo.snapshot["8017851692"] = {
        "customer_id": "8017851692",
        "tentativa_em": (datetime.now(timezone.utc)
                         - timedelta(seconds=10)).isoformat(),
        "tentativa_resultado": "ok"}

    with TestClient(app) as cliente:
        r = cliente.post("/api/trafego/inventario/atualizar",
                         json={"customer_id": "8017851692"})
    assert r.status_code == 429, r.text
    detalhe = r.json()["detail"]
    assert detalhe["intervalo_s"] == sinc.INTERVALO_MINIMO_S["manual"]
    assert detalhe["proxima_em"]
    # Quem clica de novo não gasta quota da conta do cliente.
    assert all(b.consultas == [] for b in buscas)


def test_atualizacao_manual_recusa_conta_fora_da_casa(app_de_varredura):
    """A credencial alcança 39 contas anunciáveis; 36 são de cliente."""
    from fastapi.testclient import TestClient

    app, _, _, _, abrir = app_de_varredura
    abrir("ADMIN")
    with TestClient(app) as cliente:
        r = cliente.post("/api/trafego/inventario/atualizar",
                         json={"customer_id": "6016739364"})
    assert r.status_code == 403, r.text


def test_atualizacao_manual_recusa_janela_inventada(app_de_varredura):
    from fastapi.testclient import TestClient

    app, _, _, _, abrir = app_de_varredura
    abrir("ADMIN")
    with TestClient(app) as cliente:
        r = cliente.post("/api/trafego/inventario/atualizar",
                         json={"customer_id": "8017851692", "janela": "SEMPRE"})
    assert r.status_code == 400
    assert "LAST_30_DAYS" in r.json()["detail"]


def test_contrato_do_scheduler_roda_a_rodada_inteira(app_de_varredura):
    from fastapi.testclient import TestClient

    app, _, repo, _, abrir = app_de_varredura
    abrir("ADMIN")
    with TestClient(app) as cliente:
        r = cliente.post("/api/trafego/inventario/sincronizacoes", json={})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["origem"] == "agendado"
    assert corpo["parcial"] is False
    assert corpo["escrita_permitida"] is False
    assert repo.espelho


def test_o_corpo_do_scheduler_nao_carrega_decisao():
    """O n8n é periferia (ADR-05): dispara, não decide.

    Se um campo de limiar, regra ou ação aparecer neste modelo, a fronteira
    vazou — e é aqui que se percebe, não em revisão de workflow.
    """
    from app.routers.trafego_inventario import PedidoDeSincronizacao

    assert set(PedidoDeSincronizacao.model_fields) == {
        "contas", "janela", "chave_idempotencia"}


def test_o_scheduler_repete_a_chave_sem_gastar_quota(app_de_varredura):
    from fastapi.testclient import TestClient

    app, _, _, buscas, abrir = app_de_varredura
    abrir("ADMIN")
    with TestClient(app) as cliente:
        primeira = cliente.post("/api/trafego/inventario/sincronizacoes",
                                json={"chave_idempotencia": "rodada-1"})
        segunda = cliente.post("/api/trafego/inventario/sincronizacoes",
                               json={"chave_idempotencia": "rodada-1"})
    assert primeira.status_code == segunda.status_code == 200
    assert segunda.json()["contas"][0]["repetida"] is True
    assert buscas[-1].consultas == []


@pytest.mark.anyio
async def test_idempotencia_nao_memoriza_fracasso():
    """Um retry com a mesma chave precisa REFAZER quando a anterior falhou.

    A versão anterior gravava o registro da rodada SEMPRE e conferia o campo
    `resultado` na leitura. Bastava alguém esquecer a conferência para a conta
    que caiu por timeout ficar permanentemente sem snapshot: o n8n reenviava a
    mesma chave — que é o comportamento CORRETO de um retry — e a idempotência
    respondia "já rodei" sem nunca ter conseguido ler nada. O log dizia
    `repetida`, que parece sucesso.

    Agora a memória é o próprio evento, e ele **só é apendado no caminho de
    sucesso**. A garantia deixou de depender de uma condição que alguém pode
    apagar: não há o que conferir, porque não há o que encontrar.

    ⚠️ Este teste era uma inspeção de TEXTO da implementação (`assert '(...)' in
    inspect.getsource(...)`). Ele passava enquanto a string existisse: uma
    reescrita correta o quebrava, e uma reescrita ERRADA que mantivesse a string
    continuaria verde. Agora ele roda a varredura três vezes e olha o efeito.
    """
    repo = RepoFalso()

    caiu = await sinc.sincronizar_conta(
        CONTA, repo, buscar=BuscaFalsa(falhar_em=("FROM campaign",)),
        chave_idempotencia="retry-1", agora=AGORA)
    assert caiu.resultado == "falhou" and caiu.repetida is False

    busca = _busca_completa()
    refeita = await sinc.sincronizar_conta(
        CONTA, repo, buscar=busca, chave_idempotencia="retry-1",
        agora=AGORA + timedelta(minutes=1))

    assert refeita.repetida is False, "o retry depois de uma falha tem de refazer"
    assert refeita.resultado == "ok" and refeita.lidas == 2
    assert busca.consultas, "a segunda tentativa nem chegou a consultar"

    # E depois do sucesso a chave passa a ser memória: a terceira não consulta.
    terceira_busca = _busca_completa()
    terceira = await sinc.sincronizar_conta(
        CONTA, repo, buscar=terceira_busca, chave_idempotencia="retry-1",
        agora=AGORA + timedelta(minutes=2))
    assert terceira.repetida is True
    assert terceira_busca.consultas == []


@pytest.mark.anyio
async def test_a_chave_da_rodada_nao_colide_com_a_do_diario_de_estado():
    """As duas moram na MESMA coluna opaca de `trafego_evento`.

    Sem prefixo, uma campanha cuja chave de agrupamento coincidisse com a de uma
    rodada faria a varredura seguinte se considerar "já feita" — e a conta
    ficaria sem snapshot novo sem nada denunciar.
    """
    from app.trafego import alertas as alr

    vid = sinc.volc_campaign_id("8017851692", "241")
    assert sinc.chave_da_rodada(vid) != alr.chave_de_estado(vid)
    assert sinc.chave_da_rodada("x").startswith("trafego.sincronizacao.rodada:")
