"""A coluna "Em validação" — onde o palpite vira medição.

O card entra com estimativa do Gemini e sai com os eixos preenchidos: uns
medidos, outros julgados, e os que não deram, ausentes com o motivo escrito.
**Ele não é aprovado nem reprovado aqui.**

## A fronteira, que não é negociável

    API mede o mundo      volume · reposicao · vacuo · formato_consumo
    LLM lê a pessoa       ignorancia · engajamento · opacidade · densidade · producao

Nenhuma API mede o tamanho do buraco de conhecimento que a pessoa carrega, nem
quanto tempo de atenção a resposta exige. E nenhum LLM mede a composição de
domínio de uma SERP. Duas fontes declarando o mesmo eixo é a disputa que já
aconteceu neste banco, onde duas funções de conversão de moeda brigavam pela
mesma coluna e vencia a ordem alfabética do nome do trigger.

## `spread` não está no ESCOPO desta etapa

O pautador responde **"vale a pena escrever sobre isso?"**: demanda humana,
opacidade institucional, espaço editorial, tamanho e renovação do público.
`spread` responde **"vale a pena comprar clique para isso?"** — é razão de
compra, e decisão de compra pertence a onde o dinheiro sai, no engine de Ads.

Lá vivem as duas metades da razão: `ad_traffic_by_keywords` com lance real (6%
de erro medido) e o RPM do GAM. Nenhuma das duas é chamada por esta coluna, nem
agora nem depois.

O eixo não é declarado ausente: ele simplesmente não faz parte do escopo, que
`espaco.ESCOPO_PAUTADOR` nomeia. A diferença importa — eixo ausente convida
alguém a medi-lo; escopo declarado obriga a contestar a decisão. E a cobertura
passa a dividir pelos NOVE: card completo dá 1,0, não 0,9.

## O lote é o caminho padrão

A base de US$ 0,012 por chamada domina na cauda curta: pedir 10 linhas custa
quase o mesmo que pedir 100. Validar 20 cards um a um paga a base 20 vezes nos
dois nós lotáveis (histórico e tráfego). O relatório diz os dois números, para
ninguém arrastar card a card sem saber o que está pagando.

## Escrita incremental e idempotente

Cada eixo grava assim que é medido. Se a chamada morrer no passo 4, os passos 2
e 3 já estão salvos e re-arrastar refaz só o que falta. Medição paga não se
perde por timeout — e é por isso que isto vive na API do sistema e não num
webhook fire-and-forget.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.config import Settings
from app.motor_pautas import espaco
from app.motor_pautas.sensores import dataforseo as S
from app.services.supabase_service import SupabaseService
from app.validacao.cliente import ClienteDataForSEO, itens_de, localidade, resultados

log = logging.getLogger("pautador.validacao")

TABELA_EIXOS = "pautador_entity_axes"
TABELA_RUNS = "pautador_validation_runs"
TABELA_OPPS = "pautador_entity_opportunities"
TABELA_SEEDS = "pautador_entity_seed_queries"

# Teto de keywords por chamada de histórico (limite da API).
LOTE_HISTORICO = 700
# Termos por card que entram na medição. São os que a entidade JÁ TRAZ —
# nome canônico, apelidos e as consultas do descobridor. Tipicamente 5 a 10.
TERMOS_POR_CARD = 20

MEDIDOS_PELA_API = ("volume", "reposicao", "vacuo", "formato_consumo", "densidade")


def _chave(termo: str) -> str:
    """A chave com que um termo é procurado na resposta da API.

    Existe porque a API normaliza: `IPVA` volta `ipva`. Uma função só, usada
    dos dois lados, é o que impede a divergência silenciosa — foi ter DUAS
    normalizações (uma no contraste pedido×devolvido, outra na busca) que
    produziu `volume: residual` num tema de 301.000 buscas/mês.
    """
    return " ".join((termo or "").strip().lower().split())
# Os três que saem da FICHA por derivação. `densidade` virou medido pela SERP e
# `producao` saiu do escopo — o LLM deixou de opinar sobre dinheiro e sobre
# capacidade da equipe, e ficou só com o que ele de fato enxerga.
DERIVADOS_DA_FICHA = ("ignorancia", "engajamento", "opacidade")


# ── o eixo, como ele é gravado ──────────────────────────────────────────────


@dataclass
class Eixo:
    eixo: str
    nivel: Optional[str]
    proveniencia: str                 # medido | julgado | ausente
    evidencia: Dict[str, Any] = field(default_factory=dict)
    motivo_ausencia: Optional[str] = None

    @classmethod
    def medido(cls, eixo: str, nivel: Optional[str], prova: Dict[str, Any],
               *, motivo: str = "sem_dado") -> "Eixo":
        if not nivel:
            return cls.ausente(eixo, motivo, prova)
        return cls(eixo, nivel, "medido", prova)

    @classmethod
    def julgado(cls, eixo: str, nivel: Optional[str], prova: Dict[str, Any]) -> "Eixo":
        if not nivel:
            return cls.ausente(eixo, "llm_nao_declarou", prova)
        return cls(eixo, nivel, "julgado", prova)

    @classmethod
    def ausente(cls, eixo: str, motivo: str, prova: Optional[Dict] = None) -> "Eixo":
        return cls(eixo, None, "ausente", prova or {}, motivo)

    def linha(self, opportunity_id: int) -> Dict[str, Any]:
        return {
            "opportunity_id": opportunity_id,
            "eixo": self.eixo,
            "nivel": self.nivel,
            "proveniencia": self.proveniencia,
            "evidencia": self.evidencia,
            "motivo_ausencia": self.motivo_ausencia,
        }


@dataclass
class Card:
    opportunity_id: int
    entity_id: Optional[int]
    country_code: str
    termo: str
    descricao: str = ""
    # Os NOMES da entidade (canônico + apelidos) e as CONSULTAS que o
    # descobridor já produziu. Nenhum dos dois é comprado: já estão no card.
    nomes: List[str] = field(default_factory=list)
    consultas: List[str] = field(default_factory=list)
    volumes: Dict[str, int] = field(default_factory=dict)
    cabeca_demanda: Optional[str] = None
    cabeca_editorial: Optional[str] = None
    prova_cabecas: Dict[str, Any] = field(default_factory=dict)
    portao: Dict[str, Any] = field(default_factory=dict)
    tensao: Dict[str, Any] = field(default_factory=dict)
    leilao: Dict[str, Any] = field(default_factory=dict)
    cluster_medido: List[dict] = field(default_factory=list)
    # O cluster vindo de `keyword_suggestions` (contenção da frase). Vazio
    # quando a chamada falhou — e aí o volume cai para os nomes, declarado.
    cluster_sugerido: List[dict] = field(default_factory=list)
    ficha: Dict[str, Any] = field(default_factory=dict)
    serp: Dict[str, Any] = field(default_factory=dict)
    eixos: Dict[str, Eixo] = field(default_factory=dict)
    resumo: Dict[str, Any] = field(default_factory=dict)

    def poe(self, eixo: Eixo) -> None:
        self.eixos[eixo.eixo] = eixo

    def termos_do_historico(self) -> List[str]:
        """Só os NOMES CURADOS. A série mensal serve à `reposicao`, e reposição
        é propriedade da ENTIDADE — não da fila minerada.

        ## O defeito que isto conserta

        Isto era `nomes + consultas`. E `consultas` é a FILA DE ADS do n8n,
        lavada em `pautador_entity_seed_queries`. Somado ao fato de que
        `keyword_suggestions` nunca foi chamado aqui, a consequência era:

            o eixo `volume` não estava CONTAMINADO pela fila de ads — ele ERA
            a fila de ads.

        Medido em `Cartão para Negativado` (BR): das 23 keywords mineradas,
        `banco pan telefone` sozinha valia 27.100 de um total de 37.350 —
        **73% do eixo `volume` era gente procurando o telefone do Banco Pan.**

        A causa está no fornecedor, e o diagnóstico já estava escrito neste
        repositório sem ninguém aplicar (`sensores/dataforseo.py`, lista de
        endpoints descartados): o nó do n8n chama `googleads:generateKeywordIdeas`,
        e `keyword_ideas` **expande CATEGORIA, não frase** — "firehose de
        descoberta, jamais medida da semente".

        A fila de ads continua existindo e continua servindo ao que ela é boa:
        descobrir keyword de anúncio e alimentar a cabeça EDITORIAL. Ela só
        deixa de ser a régua do volume.
        """
        vistos: List[str] = []
        for t in self.nomes:
            t = (t or "").strip()
            if t and t.lower() not in {v.lower() for v in vistos}:
                vistos.append(t)
        return vistos or [self.termo]

    @property
    def dominios(self) -> List[str]:
        vistos: List[str] = []
        for i in (self.serp.get("items") or []):
            if not isinstance(i, dict) or i.get("type") != "organic":
                continue
            d = (i.get("domain") or "").lower()
            if d and d not in vistos:
                vistos.append(d)
        return vistos[:10]


@dataclass
class Relatorio:
    lote_id: str
    modo: str
    cards: List[Card] = field(default_factory=list)
    custo_usd: float = 0.0
    custo_individual_estimado_usd: float = 0.0
    endpoints: List[dict] = field(default_factory=list)
    keywords_pedidas: int = 0
    keywords_devolvidas: int = 0
    faltantes: List[str] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)
    duracao_ms: int = 0

    @property
    def economia_do_lote(self) -> float:
        return round(max(0.0, self.custo_individual_estimado_usd - self.custo_usd), 6)

    def json(self) -> Dict[str, Any]:
        return {
            "lote_id": self.lote_id,
            "modo": self.modo,
            "cards": len(self.cards),
            "custo_usd": round(self.custo_usd, 6),
            "custo_por_card_usd": round(self.custo_usd / max(1, len(self.cards)), 6),
            "custo_individual_estimado_usd": round(self.custo_individual_estimado_usd, 6),
            "economia_do_lote_usd": self.economia_do_lote,
            "keywords_pedidas": self.keywords_pedidas,
            "keywords_devolvidas": self.keywords_devolvidas,
            "faltantes": self.faltantes,
            "erros": self.erros,
            "duracao_ms": self.duracao_ms,
            "resultados": [
                {
                    "opportunity_id": c.opportunity_id,
                    "termo": c.termo,
                    "cabeca_editorial": c.cabeca_editorial,
                    **c.resumo,
                }
                for c in self.cards
            ],
        }


# ── o fluxo ─────────────────────────────────────────────────────────────────


class Validador:
    def __init__(self, settings: Settings, supa: SupabaseService,
                 *, engine: Optional[str] = None, model: Optional[str] = None):
        self.settings = settings
        self.supa = supa
        self.cliente = ClienteDataForSEO(settings)
        self.engine = engine
        self.model = model

    async def validar(self, opportunity_ids: Sequence[int], *,
                      modo: str = "lote", refazer: bool = False) -> Relatorio:
        inicio = time.monotonic()
        rel = Relatorio(lote_id=str(uuid.uuid4()), modo=modo)

        cards = await self._carregar(opportunity_ids)
        rel.cards = cards
        if not cards:
            return rel

        if not self.cliente.habilitado:
            rel.erros.append(
                "DATAFORSEO_LOGIN/PASSWORD ausentes — nenhum eixo pôde ser medido")
            for c in cards:
                await self._sem_medicao(c)
            rel.duracao_ms = int((time.monotonic() - inicio) * 1000)
            return rel

        if not refazer:
            await self._marcar_ja_medidos(cards)

        # 0 · o CLUSTER, por card, semeado pelos NOMES CURADOS -> volume
        await self._passo_cluster(cards, rel)
        # 1 · histórico EM LOTE sobre os NOMES -> a série que a reposição usa
        await self._passo_historico(cards, rel)
        # 2 · SERP, por card, na cabeça EDITORIAL -> formato_consumo
        await self._passo_serp(cards)
        # 3 · tráfego dos domínios EM LOTE -> vacuo
        await self._passo_trafego(cards)
        # A PONTE DE TENSÃO agora é do LLM, não de regex.
        #
        # `psique.ler` casava SUBSTANTIVO — e a tese que ele deveria executar
        # diz o contrário: a ponte entre países é a FORMA DA PERGUNTA. Ligado
        # ao caminho, ele provou a própria falha: `cesantias` não lia, e
        # "como saber se tenho dinheiro esquecido" saía `protecao_familiar`
        # porque `como saber s[ei]` colidiu com `esquecid` e o desempate
        # interno é por intensidade.
        #
        # A tabela das 7 tensões continua sendo o ativo — ela veio dos ganchos
        # dos vencedores medidos. O que muda é quem lê: o LLM classifica cada
        # pergunta contra a tabela, em vocabulário fechado, e o número continua
        # vindo da tabela. Ver a seção 9 de `ficha_de_resposta.md`.

        # 4 · A FICHA — uma chamada, duas passadas, e os eixos saem por
        #     aritmética. Substitui o classificador de 648 linhas E o portão
        #     dedicado de 155: o portão virou consequência das contagens.
        await self._passo_ficha(cards, rel)

        # 5 · posicionar, resumir, gravar
        for c in cards:
            await self._gravar_eixos(c)
            self._resumir(c)
            await self._gravar_resumo(c)

        self._contabilizar(cards, rel)
        rel.duracao_ms = int((time.monotonic() - inicio) * 1000)
        await self._gravar_run(rel)
        return rel

    # ── carga ───────────────────────────────────────────────────────────────

    async def _carregar(self, ids: Sequence[int]) -> List[Card]:
        if not ids or not self.supa.enabled:
            return []
        lista = ",".join(str(int(i)) for i in ids)
        linhas = await self.supa.select(
            TABELA_OPPS,
            {"id": f"in.({lista})",
             "select": "id,entity_id,country_code,pautador_entities(canonical_name,"
                       "full_name,aliases,description)"},
        )
        # As consultas que o descobridor já escreveu. São elas que dão a cabeça
        # EDITORIAL — e elas vêm em forma de pergunta ("como consultar ipva
        # pelo renavam"), que é exatamente o que a expansão comprada não
        # garantia dar.
        consultas: Dict[int, List[str]] = {}
        try:
            for r in await self.supa.select_all(
                TABELA_SEEDS, {"opportunity_id": f"in.({lista})",
                               "select": "opportunity_id,query"}):
                q = (r.get("query") or "").strip()
                if q:
                    consultas.setdefault(int(r["opportunity_id"]), []).append(q)
        except Exception as exc:  # noqa: BLE001 — sem seeds o card ainda mede
            log.warning("seed_queries indisponíveis: %s", str(exc)[:160])
        cards: List[Card] = []
        for r in linhas:
            ent = r.get("pautador_entities") or {}
            if isinstance(ent, list):
                ent = ent[0] if ent else {}
            nome = (ent.get("canonical_name") or ent.get("full_name") or "").strip()
            if not nome:
                continue
            aliases = [a for a in (ent.get("aliases") or []) if isinstance(a, str)]
            opp_id = int(r["id"])
            cards.append(Card(
                opportunity_id=opp_id,
                entity_id=r.get("entity_id"),
                country_code=(r.get("country_code") or "").upper(),
                termo=nome,
                descricao=(ent.get("description") or "")[:400],
                nomes=[nome, *aliases][:6],
                consultas=consultas.get(opp_id, [])[:12],
            ))
        return cards

    async def _marcar_ja_medidos(self, cards: List[Card]) -> None:
        """Re-arrastar refaz só o que falta. Medição paga não se repaga."""
        ids = ",".join(str(c.opportunity_id) for c in cards)
        linhas = await self.supa.select(
            TABELA_EIXOS,
            {"opportunity_id": f"in.({ids})",
             "select": "opportunity_id,eixo,nivel,proveniencia,evidencia,motivo_ausencia"},
        )
        por_id = {c.opportunity_id: c for c in cards}
        for r in linhas:
            c = por_id.get(int(r["opportunity_id"]))
            if c is None or r.get("proveniencia") == "ausente":
                continue      # ausente sempre se retenta: pode ter sido falha de rede
            c.poe(Eixo(r["eixo"], r.get("nivel"), r["proveniencia"],
                       r.get("evidencia") or {}, r.get("motivo_ausencia")))

    async def _sem_medicao(self, card: Card) -> None:
        for eixo in MEDIDOS_PELA_API:
            card.poe(Eixo.ausente(eixo, "sem_credencial_dataforseo"))
        await self._gravar_eixos(card)
        self._resumir(card)
        await self._gravar_resumo(card)

    # ── passo 1 · o cluster não é comprado ────────────────────────────────
    #
    # `keyword_suggestions` SAIU desta coluna. Era o nó mais caro (US$ 0,030 de
    # US$ 0,046 por card) e comprava uma expansão que a MINERAÇÃO vai comprar de
    # novo — a mesma keyword paga duas vezes, em duas colunas.
    #
    # O cluster da validação passa a ser o que a entidade JÁ TRAZ: nome
    # canônico, apelidos e as consultas do descobridor. Cinco a dez termos, e
    # eles resolvem o que a expansão resolvia: `subsidio de vivienda ds49`
    # sozinho dá 90/mês e dispararia `residual` por artefato de fraseado; com os
    # apelidos ao lado, não.
    #
    # E a cauda longa — onde vive a pergunta escrita pelo usuário — não se
    # perde: ela é insumo do `psique.py` e do gerador de copy, e vem do
    # `related_keywords` com depth=3, na mineração. Cabeça para MEDIR, cauda
    # para ESCREVER: chamadas diferentes, em colunas diferentes.

    # ── passo 2 · histórico em lote -> volume + reposicao ───────────────────

    async def _passo_cluster(self, cards: List[Card], rel: Relatorio) -> None:
        """O cluster que vira o eixo `volume`, semeado pelo NOME CURADO.

        ## Por que este passo existe

        O eixo `volume` era a soma de `nomes + consultas`, e `consultas` é a
        fila de ads do n8n. Medido em `Cartão para Negativado`: 73% do eixo era
        `banco pan telefone`. A fila vem de `keyword_ideas`, que **expande
        categoria, não frase** — o próprio sensor já dizia isso na lista de
        endpoints descartados, e ninguém tinha ligado os pontos.

        `keyword_suggestions` expande a FRASE: devolve o que CONTÉM a semente.
        A contaminação por consulta de contato cai para 0,00–0,26% medido em 4
        clusters, 3 mercados e 2 idiomas — sem filtro, sem limiar e sem uma
        única palavra dependente de idioma. É o fornecedor que garante, não uma
        regra nossa.

        ## O custo, declarado

        `keyword_suggestions` é UMA SEMENTE POR TAREFA: não lota, e por isso
        custa por card (~US$ 0,035 com o filtro de volume aplicado no servidor).
        Foi exatamente por isso que ele saiu desta coluna um dia. A troca é
        deliberada: três centavos contra um eixo que mentia 73%.

        Semeia com o PRIMEIRO nome canônico apenas. Os apelidos entram no
        histórico e na escolha das cabeças; como semente, cada um seria outra
        tarefa paga para medir a mesma entidade.
        """
        alvos = [c for c in cards if localidade(c.country_code) and "volume" not in c.eixos]
        if not alvos:
            return

        pedidos = []
        for c in alvos:
            code, lang = localidade(c.country_code)
            semente = (c.nomes[0] if c.nomes else c.termo)
            pedidos.append(("sugestoes", S.tarefa_sugestoes(
                semente, location_code=code, language_code=lang)))
        respostas = await self.cliente.em_paralelo(pedidos, limite=5)

        for card, resp in zip(alvos, respostas):
            linhas = []
            for i in S.itens(resp):
                kw = i.get("keyword")
                vol = (i.get("keyword_info") or {}).get("search_volume")
                if kw and isinstance(vol, (int, float)):
                    linhas.append({"keyword": kw, "search_volume": int(vol)})
            card.cluster_sugerido = linhas
            if not linhas:
                # Sem sugestões o volume NÃO fica ausente: ele cai para os nomes
                # medidos pelo histórico, e a prova do eixo diz que foi assim.
                log.info("sem sugestões para %s — cluster cai para os nomes", card.termo)

    async def _passo_historico(self, cards: List[Card], rel: Relatorio) -> None:
        """Uma chamada por (país, idioma), com os clusters de todos os cards.

        É aqui que o lote paga: a base de US$ 0,012 é cobrada uma vez em vez de
        uma por card.
        """
        por_mercado: Dict[tuple, List[Card]] = {}
        for c in cards:
            loc = localidade(c.country_code)
            if loc is None:
                c.poe(Eixo.ausente("volume", "pais_sem_location_code"))
                c.poe(Eixo.ausente("reposicao", "pais_sem_location_code"))
                continue
            if "volume" in c.eixos and "reposicao" in c.eixos:
                continue
            por_mercado.setdefault(loc, []).append(c)

        for (code, lang), grupo in por_mercado.items():
            pedidas: List[str] = []
            dono: Dict[str, Card] = {}
            for c in grupo:
                for t in c.termos_do_historico()[:TERMOS_POR_CARD]:
                    if t not in dono:          # primeiro card fica com o termo
                        dono[t] = c
                        pedidas.append(t)

            devolvidas: List[str] = []
            # ⚠️ CHAVE NORMALIZADA. A API devolve a keyword em MINÚSCULAS: pedir
            # `IPVA` traz de volta `ipva`. Indexar por string crua fazia todo
            # alias capitalizado sumir da medição SEM ser contado como perdido —
            # `diff_pedido_devolvido` já comparava sem caixa, e a busca em
            # `series` não. Medido: IPVA com 301.000/mês virou 30/mês
            # `residual`, e o portão de volume matou o tema por artefato.
            series: Dict[str, list] = {}
            for i in range(0, len(pedidas), LOTE_HISTORICO):
                fatia = pedidas[i:i + LOTE_HISTORICO]
                resp = await self.cliente.chamar("historico_volume", S.tarefa_historico_volume(
                    fatia, location_code=code, language_code=lang))
                for item in itens_de(resp):
                    kw = item.get("keyword")
                    if not kw:
                        continue
                    devolvidas.append(kw)
                    series[_chave(kw)] = (
                        (item.get("keyword_info") or {}).get("monthly_searches") or [])

            rel.keywords_pedidas += len(pedidas)
            rel.keywords_devolvidas += len(devolvidas)
            faltantes = S.diff_pedido_devolvido(pedidas, devolvidas)
            rel.faltantes.extend(faltantes)
            perdidas_por_card: Dict[int, List[str]] = {}
            for kw in faltantes:
                c = dono.get(kw)
                if c:
                    perdidas_por_card.setdefault(c.opportunity_id, []).append(kw)

            for c in grupo:
                self._volume_e_reposicao(c, series, perdidas_por_card)

    def _volume_e_reposicao(self, card: Card, series: Dict[str, list],
                            perdidas: Dict[int, List[str]]) -> None:
        termos = card.termos_do_historico()[:TERMOS_POR_CARD]
        # O termo original é preservado na evidência; a BUSCA é normalizada.
        medidos = [t for t in termos if _chave(t) in series]
        perdidos = perdidas.get(card.opportunity_id, [])

        if not medidos:
            # ⚠️ NUNCA `residual`. O Labs devolve status 20000 e simplesmente
            # não põe o item no array — `cesantias` tem 40.500 buscas/mês e não
            # volta. Chamar buraco de base de volume zero mata tema vivo.
            motivo = "buraco_de_base" if perdidos else "sem_serie"
            card.poe(Eixo.ausente("volume", motivo, {"pedidas": termos, "faltantes": perdidos}))
            card.poe(Eixo.ausente("reposicao", motivo, {"pedidas": termos}))
            return

        # ── O CLUSTER, e de onde ele vem ─────────────────────────────────
        #
        # `card.cluster_sugerido` vem de `keyword_suggestions`, semeado pelos
        # NOMES CURADOS. Ele é ancorado por CONTENÇÃO — o fornecedor devolve
        # keywords que CONTÊM a frase-semente —, e é isso que torna
        # `banco pan telefone` estruturalmente impossível dentro do cluster de
        # `cartão para negativado`. Não é regra que a gente escreveu: é
        # construção do endpoint.
        #
        # Medido em 4 clusters, 3 mercados, 2 idiomas, 800 termos: contaminação
        # por consulta de contato de 0,00% (BR), 0,00% (BR), 0,07% (CO) e
        # 0,26% (MX). Nenhum filtro, nenhum limiar, nenhuma lista por idioma.
        #
        # Sem sugestões (falha da chamada, país sem cobertura), cai para os
        # NOMES medidos pelo histórico — piso honesto, e a prova diz qual foi.
        if card.cluster_sugerido:
            cluster_medido = card.cluster_sugerido
            fonte_cluster = "dataforseo_labs/keyword_suggestions (contenção da frase)"
        else:
            cluster_medido = [
                {"keyword": t,
                 "search_volume": next(
                     (m.get("search_volume")
                      for m in S.ordenar_serie(series[_chave(t)])[-1:]), 0)}
                for t in medidos
            ]
            fonte_cluster = "historical_search_volume sobre os nomes (sem sugestões)"
        card.volumes = {k["keyword"]: int(k["search_volume"] or 0) for k in cluster_medido}
        card.cluster_medido = cluster_medido
        # AS DUAS CABEÇAS, sobre volume MEDIDO — nunca sobre o que a API perdeu.
        card.cabeca_demanda, card.cabeca_editorial, card.prova_cabecas = S.escolher_cabecas(
            card.volumes, nomes=card.nomes, consultas=card.consultas)
        total, prova = S.volume_do_cluster(cluster_medido)
        prova.update({
            "termos_pedidos": len(termos),
            "termos_medidos": len(medidos),
            "faltantes": perdidos,
            "fonte": fonte_cluster,
            "fonte_da_serie": "dataforseo_labs/historical_search_volume",
        })
        if perdidos:
            prova["aviso"] = (
                f"{len(perdidos)} termo(s) não voltaram da API sem erro declarado — "
                f"o volume abaixo é PISO, não total")
        prova.update(card.prova_cabecas)
        card.poe(Eixo.medido("volume", S.nivel_volume(total), prova))

        # Reposição: a série do termo de cabeça, nos últimos 48 meses.
        cabeca = (card.cabeca_demanda
                  if _chave(card.cabeca_demanda or "") in series
                  else max(medidos, key=lambda t: card.volumes.get(t, 0)))
        janela = S.janela_48(series[_chave(cabeca)])
        nivel, prova_rep = S.nivel_reposicao(janela)
        prova_rep.update({
            "termo": cabeca,
            "regra_do_termo": "cabeça de DEMANDA — maior volume entre os nomes",
            "janela_meses": len(janela),
            "serie_completa_meses": len(series[_chave(cabeca)]),
            "nascimento_da_entidade": S.nascimento_da_entidade(series[_chave(cabeca)]),
        })
        card.poe(Eixo.medido("reposicao", nivel, prova_rep, motivo="serie_curta"))

    # ── passo 2 · SERP em DUAS fases, e a segunda é a que vale ────────────
    #
    # Fase A · SERP na cabeça de DEMANDA, só para colher o PAA.
    # Fase B · SERP na cabeça EDITORIAL, tirada do PAA — e é dela que saem
    #          `vacuo` e `formato_consumo`.
    #
    # Por que duas: os `seed_queries` são o que o DESCOBRIDOR imaginou que se
    # pergunta. Medido no IPVA, isso dava `como consultar ipva pelo renavam` —
    # navegacional — e o `vacuo` saía `virgem` porque a SERP era 8 de 9
    # secretarias de fazenda. O PAA da mesma SERP traz `Como é calculado o
    # IPVA?`, que é a consulta editorial de verdade.
    #
    # Custa US$ 0,002 a mais por card e conserta a CAUSA (o descobridor não
    # sabe o que se pergunta) em vez do sintoma (a cabeça errada).

    async def _passo_serp(self, cards: List[Card]) -> None:
        alvos = [c for c in cards
                 if localidade(c.country_code)
                 and not ("formato_consumo" in c.eixos and "vacuo" in c.eixos)]
        for c in cards:
            if not localidade(c.country_code):
                c.poe(Eixo.ausente("formato_consumo", "pais_sem_location_code"))
                c.poe(Eixo.ausente("vacuo", "pais_sem_location_code"))
        if not alvos:
            return

        # ── fase A: colher o PAA ──────────────────────────────────────────
        pedidos = []
        for c in alvos:
            code, lang = localidade(c.country_code)
            termo = c.cabeca_demanda or c.termo
            pedidos.append(("serp", S.tarefa_serp(termo, location_code=code,
                                                  language_code=lang, profundidade=10)))
        respostas = await self.cliente.em_paralelo(pedidos, limite=5)

        for card, resp in zip(alvos, respostas):
            blocos = resultados(resp)
            serp_demanda = blocos[0] if blocos else {}
            perguntas = S.perguntas_do_paa(serp_demanda)
            escolhida, prova_paa = S.cabeca_editorial_do_paa(perguntas, card.volumes)
            if escolhida:
                card.cabeca_editorial = escolhida
                card.prova_cabecas.update(prova_paa)
            else:
                # Sem PAA, fica a regra anterior (consulta interrogativa do
                # descobridor), e o fallback vai declarado na evidência.
                card.prova_cabecas.update(prova_paa)
                card.prova_cabecas["regra_editorial"] = (
                    "FALLBACK — SERP sem bloco PAA; usada a consulta do descobridor")
            # A SERP da demanda serve de rede: se a fase B falhar, é ela que
            # responde `vacuo` e `formato_consumo` em vez de deixá-los ausentes.
            card.serp = serp_demanda

        # ── fase B: a SERP que decide ─────────────────────────────────────
        pedidos_b, alvos_b = [], []
        for c in alvos:
            code, lang = localidade(c.country_code)
            termo = c.cabeca_editorial or c.cabeca_demanda or c.termo
            if termo == (c.cabeca_demanda or c.termo):
                continue          # mesma SERP — não paga duas vezes pelo mesmo
            pedidos_b.append(("serp", S.tarefa_serp(termo, location_code=code,
                                                    language_code=lang, profundidade=10)))
            alvos_b.append(c)
        if pedidos_b:
            respostas_b = await self.cliente.em_paralelo(pedidos_b, limite=5)
            for card, resp in zip(alvos_b, respostas_b):
                blocos = resultados(resp)
                if blocos:
                    card.serp = blocos[0]

        for card in alvos:
            nivel, prova = S.nivel_formato_consumo(card.serp)
            prova["termo_medido"] = card.cabeca_editorial
            prova.update(card.prova_cabecas)
            card.poe(Eixo.medido("formato_consumo", nivel, prova,
                                 motivo="serp_sem_organicos"))

    # ── passo 4 · tráfego dos domínios em lote -> vacuo ────────────────────

    async def _passo_trafego(self, cards: List[Card]) -> None:
        por_mercado: Dict[tuple, List[Card]] = {}
        for c in cards:
            loc = localidade(c.country_code)
            if loc is None or "vacuo" in c.eixos:
                continue
            por_mercado.setdefault(loc, []).append(c)

        for (code, lang), grupo in por_mercado.items():
            alvos: List[str] = []
            for c in grupo:
                for d in c.dominios:
                    if d not in alvos:
                        alvos.append(d)
            etv: Dict[str, float] = {}
            if alvos:
                resp = await self.cliente.chamar("trafego_dominio", S.tarefa_trafego(
                    alvos, location_code=code, language_code=lang))
                etv = S.etv_por_dominio(resp)
            for c in grupo:
                # `existe_leilao` estava escrito, testado e desligado — as duas
                # auditorias pegaram. Ele não vira eixo: `cpc: null` é REGIME de
                # mercado (demanda real, zero anunciante — regra no México, 32
                # de 32), e o espaço de eixos não tem essa categoria. Entra como
                # insumo de `densidade` e como rótulo no card.
                tem_leilao, prova_leilao = S.existe_leilao(c.cluster_medido)
                c.leilao = {"existe": tem_leilao, **prova_leilao}

                # `densidade` deixa de ser palpite de LLM sobre DINHEIRO num
                # motor que decidiu não medir dinheiro. A SERP já está paga e
                # mostra quem investiu para estar ali.
                nivel_d, prova_d = S.nivel_densidade(c.serp, tem_leilao)
                c.poe(Eixo.medido("densidade", nivel_d, prova_d,
                                  motivo="serp_sem_organicos"))

                nivel, prova = S.nivel_vacuo_com_trafego(c.serp, etv)
                prova["alvos_no_lote"] = len(alvos)
                nasc = (c.eixos.get("reposicao").evidencia.get("nascimento_da_entidade")
                        if c.eixos.get("reposicao") else None)
                if nasc:
                    prova["nascimento_da_entidade"] = nasc
                c.poe(Eixo.medido("vacuo", nivel, prova, motivo="serp_sem_organicos"))

    # ── passo 4 · A FICHA: uma chamada, duas passadas, eixos derivados ────

    async def _passo_ficha(self, cards: List[Card], rel: Relatorio) -> None:
        """O LLM conta oito observáveis; o Python deriva três eixos e o portão.

        MEDIDO no desenho anterior: no formulário de nove eixos, `Registrato` —
        o arquétipo de consulta em base própria — disparava o portão **1 vez em
        5**. As outras quatro saía `sequencial`, porque o modelo descrevia os
        PASSOS da consulta. Isolado num prompt só dele, 5 de 5.

        Aqui o portão não é perguntado: `ramos <= 1` e `condicoes == 0` e nada a
        decidir depois **é** `dado_unico`. Não há o que o modelo perder de vista.
        """
        from app.validacao import julgamento as J
        from app.validacao.ficha import (N_MINIMO_PARA_PORTAO,
                                         veredito_de_passadas)
        from app.validacao.portao import (
            LIMITROFE, NOTA_DE_REPLICACAO, PORTAO, PROMOCAO_REPLICADA)

        pendentes = [c for c in cards
                     if any(e not in c.eixos for e in J.DERIVADOS_DA_FICHA)]
        if not pendentes:
            return
        try:
            lidas = await J.ler_fichas(pendentes, settings=self.settings,
                                       engine=self.engine, model=self.model)
        except Exception as exc:  # noqa: BLE001 — a ficha não derruba a medição
            log.warning("ficha falhou: %s", str(exc)[:200])
            rel.erros.append(f"ficha: {str(exc)[:200]}")
            return

        for c in pendentes:
            r = lidas.get(c.opportunity_id) or {}
            niveis = r.get("niveis") or {}
            ent = r.get("entidade") or {}
            cmp = r.get("comparacao") or {}
            c.ficha = {**ent, "comparacao": cmp, "porques": r.get("porques") or {}}
            if ent.get("tensao_dominante"):
                c.tensao = {
                    "tensao": ent["tensao_dominante"],
                    "distribuicao": ent.get("distribuicao_de_tensao"),
                    "share_com_tensao": ent.get("share_com_tensao"),
                    # PRIOR COM DÍVIDA: a intensidade veio do desfecho `lucro`,
                    # contaminado por `spend`. Gravada para o dia em que houver
                    # régua limpa; não entra em conta nenhuma hoje.
                    "intensidade_prior": ent.get("intensidade"),
                    "porque": (r.get("porques") or {}).get("tensao", ""),
                }

            for eixo in J.DERIVADOS_DA_FICHA:
                if eixo in c.eixos:
                    continue
                nivel = niveis.get(eixo)
                if not nivel:
                    # `paa_ausente` != `ficha_invalida`: o Google não devolveu
                    # perguntas, versus o modelo devolveu ficha quebrada. Achatar
                    # os dois esconde que a entidade nunca chegou a ser lida.
                    c.poe(Eixo.ausente(eixo, r.get("motivo") or "ficha_invalida",
                                       {"comparacao": cmp}))
                    continue
                # `julgado`, e não `medido`: a CONTAGEM é do LLM. O que a
                # derivação garante é que o nível não oscila dada a contagem —
                # não que a contagem esteja certa.
                c.poe(Eixo(eixo, nivel, "julgado", {
                    "regra": f"ficha.nivel_{eixo}",
                    "derivado_da_pergunta": ent.get("pergunta_mais_rica"),
                    "distribuicao_da_entidade": ent.get("distribuicao"),
                    "share_dado_unico": ent.get("share_dado_unico"),
                    "porque": (r.get("porques") or {}).get(eixo, ""),
                    "fonte": r.get("fonte"),
                    "estavel_entre_passadas": cmp.get("estavel"),
                }))

            # ── o portão, sobre a DISTRIBUIÇÃO da entidade ───────────────
            #
            # A assimetria inverteu de lado, e o custo mandou. Sobre UMA
            # pergunta, qualquer disparo isolado rebaixava. Sobre a ENTIDADE,
            # matar por uma pergunta de lookup é o erro caro: toda entidade
            # rica tem uma pergunta de data no PAA, e o `DIRPF` provou isso —
            # congelado em "Quando libera a declaração de 2026?" ele disparava
            # o portão e morria, com a contagem certa e o objeto errado.
            share = ent.get("share_dado_unico")
            # Quantas perguntas sustentam esse share. Sem isso, uma SERP sem
            # bloco de PAA vira "todas as perguntas esgotam" com n=1.
            n_perg = int(ent.get("n_perguntas") or 0)
            vereditos = cmp.get("vereditos") or []
            # Stake afirmado sem prova NÃO rebaixa — força o humano a olhar.
            # A brecha veio da auditoria externa e é real: como `stake` não cai
            # por falta de citação (rebaixar dispararia o portão), curiosidade
            # pura marcada `stake=true` com `stake_qual` vazio passaria limpa.
            # O conserto é recusar o automático, não inverter o valor.
            sem_prova = int(ent.get("stake_sem_prova") or 0)
            shares = [s for s in (cmp.get("shares") or []) if s is not None]
            if share is None:
                veredito = None
            elif sem_prova:
                # Stake afirmado e não sustentado: nada automático.
                veredito = LIMITROFE
            else:
                # A unanimidade mora no SHARE, não no rótulo. Comparar rótulo
                # por passada era frágil por aritmética: com 4 perguntas o share
                # anda de 0,25 em 0,25 e os limiares caem dentro dessa banda,
                # então metade dos movimentos de UMA pergunta trocava o veredito
                # sem que a medição tivesse mudado.
                veredito = veredito_de_passadas(shares or [share], n_perg)

            perguntas = ent.get("perguntas") or []
            mais_rica = next((q for q in perguntas
                              if q.get("pergunta") == ent.get("pergunta_mais_rica")), {})
            esgotam = [q for q in perguntas if q.get("engajamento") == "dado_unico"]
            c.portao = {
                "veredito": veredito,
                # ── o que as N passadas concordaram, pergunta a pergunta ────
                #
                # O veredito da entidade pode bater por compensação. Isto é o
                # que de fato se repetiu, e é o número para acompanhar sem
                # refazer o experimento de calibração (AC1 de Gwet, com input
                # fixo: ignorância 0,81 · tensão 0,76 · opacidade e engajamento
                # 0,64). Se ele despencar em produção, o modelo mudou embaixo.
                "concordancia_por_pergunta": cmp.get("concordancia_por_pergunta"),
                "perguntas_instaveis": cmp.get("perguntas_instaveis") or [],
                # Das citações que o modelo deu, quantas estão MESMO no texto
                # que ele escreveu. Mede, não barra — ainda.
                "citacoes_conferidas": ent.get("citacoes_conferidas"),
                "n_citacoes": ent.get("n_citacoes"),
                "stake_sem_prova": sem_prova,
                # Roteamento de formato. Reporta e NÃO decide: não zera índice,
                # não rebaixa nível, não entra em `posicionar()`. O portão segue
                # sendo o portão; isto diz o que produzir quando ele não dispara,
                # e o que TERIA sido possível quando dispara.
                "formatos": ent.get("formatos"),
                "share_dado_unico": share,
                "distribuicao": ent.get("distribuicao"),
                "n_perguntas": ent.get("n_perguntas"),
                # O QUE A TELA MOSTRA: o share de cada passada, cru. É isto que
                # substituiu o rótulo — `0,75 · 1,00 · 1,00` diz tudo que o
                # rótulo dizia e não inventa fronteira que a aritmética não tem.
                "shares_por_passada": shares,
                "share_min": min(shares) if shares else None,
                "share_max": max(shares) if shares else None,
                "consulta_dominante": ent.get("pergunta_mais_rica", ""),
                "resposta_literal": mais_rica.get("resposta_literal", ""),
                "decisao_que_sobra": ("nenhuma" if not mais_rica.get("decide_depois")
                                      else (r.get("porques") or {}).get("decisao_apos_resposta", "")),
                "porque": (f"{len(esgotam)} de {len(perguntas)} perguntas do PAA "
                           f"se esgotam em segundos"
                           + (f" — e entre as {len(shares)} passadas isso variou "
                              f"de {min(shares):.0%} a {max(shares):.0%}"
                              if len(set(shares)) > 1 else "")
                           + ("" if n_perg >= N_MINIMO_PARA_PORTAO else
                              f" — e {n_perg} pergunta(s) é pouco para o portão "
                              f"disparar, então o máximo daqui é limítrofe")),
                "divergencia": (f"as passadas leram share {cmp.get('shares')}"
                                if veredito == LIMITROFE and len(set(vereditos)) > 1
                                else (f"esgotam: {'; '.join(q['pergunta'] for q in esgotam)}"
                                      if veredito == LIMITROFE else "")),
                "fonte": r.get("fonte", ""),
                "promocao_replicada": PROMOCAO_REPLICADA,
                "nota_de_replicacao": (NOTA_DE_REPLICACAO
                                       if veredito == PORTAO and not PROMOCAO_REPLICADA else ""),
                # ── PAA ausente: SINAL, e hipótese declarada como tal ───────
                #
                # A auditoria externa sustenta que consulta navegacional ou
                # transacional não gera bloco de perguntas porque o Google
                # entende que a pessoa quer um balcão, não uma explicação — o
                # que seria o MESMO estado que o portão existe para detectar.
                #
                # ⚠️ NÃO MEDIMOS ISSO. O teste que a auditoria propôs (filtrar
                # SERPs já coletadas por PAA vazio e cruzar com o domínio do
                # 1º orgânico) citou um arquivo que não contém SERPs. Então o
                # sinal fica GRAVADO e NÃO decide: ele não zera índice, não
                # rebaixa nível e não entra em conta. Vira número no dia em que
                # houver a medição, e some no dia em que ela refutar.
                "sinal_paa_ausente": r.get("motivo") == "paa_ausente",
                "nota_paa_ausente": (
                    "a SERP não devolveu bloco de perguntas. Há hipótese de que "
                    "isso indique intenção navegacional — o mesmo estado que o "
                    "portão detecta — mas ela NÃO foi medida e não decide nada aqui."
                    if r.get("motivo") == "paa_ausente" else ""),
            }

    # ── posicionar e resumir ───────────────────────────────────────────────

    def _resumir(self, card: Card) -> None:
        niveis = {e.eixo: e.nivel for e in card.eixos.values() if e.nivel}
        medidos = {e.eixo for e in card.eixos.values() if e.proveniencia == "medido"}
        try:
            pos = espaco.posicionar(card.termo, pais=card.country_code or "??",
                                    medidos=medidos,
                                    escopo=espaco.ESCOPO_PAUTADOR, **niveis)
        except ValueError as exc:
            card.resumo = {"apto": False, "motivo": "nivel_fora_do_vocabulario",
                           "erro": str(exc)[:200]}
            return

        # ⚠️ O PORTÃO DE CANAL, EM CÓDIGO.
        #
        # `PORTOES_EXIGEM_MEDICAO` cobre `spread` e `volume` — impede que
        # palpite mate tema. `formato_consumo` não tem essa proteção e tem o
        # problema oposto: eixo ausente SAI da média geométrica, então NÃO
        # medir o canal SOBE a nota. Silêncio seria o movimento mais lucrativo
        # do formulário inteiro.
        #
        # Sem SERP não há como saber se o funil fecha naquele mercado. O card
        # sai da fila com o motivo gravado — continua visível, arrastável e
        # inteiro; o que ele perde é o direito de ser ranqueado antes que
        # alguém meça o canal.
        canal = card.eixos.get("formato_consumo")
        apto, motivo = True, None
        if canal is None or canal.proveniencia == "ausente":
            apto = False
            motivo = "canal_nao_medido"

        # O PORTÃO, em três estados. O terceiro é o único que não inventa.
        #
        # `limitrofe` NÃO é escotilha: ele tira o card da fila exatamente como o
        # portão tira. A escotilha removida do classificador (o S4) RESGATAVA o
        # tema — subia o nível e o devolvia à fila. Este recusa a fingir certeza
        # que a medição não tem, e a consequência é a mesma.
        from app.validacao.portao import LIMITROFE, PORTAO

        veredito = (card.portao or {}).get("veredito")
        if veredito == PORTAO:
            apto, motivo = False, "portao_engajamento"
        elif veredito == LIMITROFE:
            apto, motivo = False, "portao_limitrofe"

        # QUALQUER portão do motor tira da fila — não só os dois acima.
        #
        # Sem isto, um tema com `volume: residual` saía `apto: true` com
        # `indice: 0.0` e `perfil: descartar`: o card dizia "na fila" e o motor
        # dizia "morto", sobre o mesmo objeto. É a contradição que `perfil()`
        # foi corrigido para não cometer, reaparecendo uma camada acima.
        disparados = pos.portoes_disparados()
        if disparados and apto:
            apto, motivo = False, f"portao_{disparados[0]}"

        # AS DUAS COORDENADAS DO QUADRANTE. Sem elas o gráfico é o rótulo
        # redesenhado: o ponto só poderia ir ao centro da célula, e aí ele não
        # acrescenta nada a `perfil`. Os dois métodos já existem no motor —
        # gravá-los é o que separa um plano de uma palavra.
        h = pos.familia("demanda_humana")
        ec = pos.familia("economia")
        pos_c = pos.familia("posicao")

        # ── SENSORES LIMPOS: a evidência tem buraco?
        #
        # Não é "zero faltantes" — isso é insatisfazível e eu medi por quê: o
        # Labs não carrega fraseado de cauda longa, e os 6 cards do teste têm
        # de 1 a 3 termos que ele simplesmente não tem. Exigir zero seria a
        # mesma regra que não dispara nunca.
        #
        # O que importa é a medição não repousar num FRAGMENTO: os quatro
        # sensores devolveram nível, e a maioria do cluster pedido voltou.
        prova_vol = (card.eixos.get("volume").evidencia
                     if card.eixos.get("volume") else {}) or {}
        pedidos = int(prova_vol.get("termos_pedidos") or 0)
        obtidos = int(prova_vol.get("termos_medidos") or 0)
        api_medidos = sum(1 for e in MEDIDOS_PELA_API
                          if (card.eixos.get(e) and
                              card.eixos[e].proveniencia == "medido"))
        fracao = (obtidos / pedidos) if pedidos else 0.0
        sensores = {
            "api_medidos": api_medidos,
            "api_total": len(MEDIDOS_PELA_API),
            "termos_pedidos": pedidos,
            "termos_medidos": obtidos,
            "fracao_do_cluster": round(fracao, 2),
            "limpos": api_medidos == len(MEDIDOS_PELA_API) and fracao >= 2 / 3,
        }

        card.resumo = {
            "apto": apto,
            "motivo": motivo,
            "sensores": sensores,
            "demanda_humana": round(h, 4) if h is not None else None,
            "economia": round(ec, 4) if ec is not None else None,
            "posicao": round(pos_c, 4) if pos_c is not None else None,
            "indice": round(pos.indice, 4) if pos.indice is not None else None,
            "cobertura": round(pos.cobertura, 2),
            "perfil": pos.perfil(),
            "portoes_disparados": pos.portoes_disparados(),
            "alertas": pos.alertas,
            "eixos": {e.eixo: {"nivel": e.nivel, "proveniencia": e.proveniencia,
                               "motivo_ausencia": e.motivo_ausencia}
                      for e in card.eixos.values()},
            "portao": card.portao or None,
            "tensao": card.tensao or None,
            "ficha": card.ficha or None,
            "leilao": card.leilao or None,
            "cabeca_demanda": card.cabeca_demanda,
            "cabeca_editorial": card.cabeca_editorial,
        }

    # ── persistência ───────────────────────────────────────────────────────

    async def _gravar_eixos(self, card: Card) -> None:
        if not self.supa.enabled or not card.eixos:
            return
        linhas = [e.linha(card.opportunity_id) for e in card.eixos.values()]
        try:
            await self.supa._request(
                "POST", f"{TABELA_EIXOS}?on_conflict=opportunity_id,eixo",
                headers=self.supa._headers("resolution=merge-duplicates,return=minimal"),
                json=linhas,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("gravar eixos opp=%s: %s", card.opportunity_id, str(exc)[:200])

    async def _gravar_resumo(self, card: Card) -> None:
        if not self.supa.enabled or not card.resumo:
            return
        from datetime import datetime, timezone

        valores = {**card.resumo,
                   "validado_em": datetime.now(timezone.utc).isoformat()}
        try:
            await self.supa.patch(TABELA_OPPS, {"id": f"eq.{card.opportunity_id}"},
                                  {"validacao": valores})
        except Exception as exc:  # noqa: BLE001
            log.warning("gravar resumo opp=%s: %s", card.opportunity_id, str(exc)[:200])

    async def _gravar_run(self, rel: Relatorio) -> None:
        if not self.supa.enabled:
            return
        try:
            await self.supa.insert(TABELA_RUNS, [{
                "lote_id": rel.lote_id,
                "modo": rel.modo,
                "opportunity_ids": [c.opportunity_id for c in rel.cards],
                "custo_usd": round(rel.custo_usd, 6),
                "custo_individual_estimado_usd": round(rel.custo_individual_estimado_usd, 6),
                "endpoints": rel.endpoints,
                "keywords_pedidas": rel.keywords_pedidas,
                "keywords_devolvidas": rel.keywords_devolvidas,
                "faltantes": rel.faltantes[:200],
                "erros": rel.erros[:50],
                "duracao_ms": rel.duracao_ms,
            }])
        except Exception as exc:  # noqa: BLE001
            log.warning("gravar run: %s", str(exc)[:200])

    # ── contabilidade ──────────────────────────────────────────────────────

    def _contabilizar(self, cards: List[Card], rel: Relatorio) -> None:
        rel.custo_usd = self.cliente.custo_total
        rel.endpoints = [
            {"endpoint": c.endpoint, "custo_usd": c.custo_usd, "ok": c.ok,
             "itens": c.itens, **({"erro": c.erro} if c.erro else {})}
            for c in self.cliente.chamadas
        ]
        rel.erros.extend(c.erro for c in self.cliente.chamadas if c.erro)

        # O que a MESMA validação teria custado card a card. Só os dois nós
        # lotáveis mudam: histórico e tráfego pagariam a base US$ 0,012 uma vez
        # por card em vez de uma por mercado. Sugestões e SERP são por card nos
        # dois modos.
        n = max(1, len(cards))
        lotaveis = [c for c in self.cliente.chamadas
                    if c.endpoint in ("historico_volume", "trafego_dominio")]
        base_paga = S.CUSTO_BASE_LABS * len(lotaveis)
        base_individual = S.CUSTO_BASE_LABS * 2 * n     # histórico + tráfego por card
        rel.custo_individual_estimado_usd = round(
            rel.custo_usd - base_paga + base_individual, 6)
