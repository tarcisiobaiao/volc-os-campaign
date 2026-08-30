"""A varredura das contas — o único lugar deste domínio que fala com o Google.

## Por que a varredura sai do caminho de render (ADR-08)

Medido em 24/08/2026: `/api/trafego/alertas` roda ~5 GAQL por conta EM TEMPO DE
RENDER, e o sino e o Layout chamam essa rota — abrir qualquer página do produto
custa rede para o Google. Com sincronização a cada 15 min o custo vira
constante (~1.600 consultas/dia, SPEC §4.4) em vez de proporcional à navegação,
e a tela passa a ler um snapshot em Postgres que responde instantaneamente e
sobrevive a uma queda da API do Google.

## Somente leitura, e isso é verificável

Nada aqui muta conta. `_exigir_leitura()` recusa qualquer GAQL que não comece em
`SELECT` — e recusa antes de a requisição sair da máquina, não depois. A trava
de escrita de `volc_ads/gads/modo.py` NUNCA é aberta por este módulo; ele sequer
importa `mutar`. As duas guardas são independentes de propósito: uma diz o que
pode ser enviado, a outra se pode escrever.

## O que "idempotente" significa aqui, e são duas coisas

1. **Idempotência de estado.** Duas varreduras da mesma conta e janela deixam o
   snapshot no mesmo lugar: as campanhas entram por `upsert` na chave natural
   `(customer_id, campaign_id)`, e as métricas são SUBSTITUÍDAS, nunca somadas
   ao que já estava. Somar seria o defeito clássico — a segunda varredura
   dobraria o custo do mês.

2. **Idempotência de chamada.** Quando o chamador manda uma
   `chave_idempotencia` (o retry do n8n manda a mesma), a segunda chamada
   devolve o registro da primeira **sem tocar no Google**. Sem chave, a proteção
   é o limite de taxa por conta.

## Degradação: a falha de uma conta é dela

Cada conta é varrida dentro do seu próprio `try`. Uma que falha vira
`resultado='falhou'` na tabela de contas, entra em `faltou`, e **as linhas de
campanha dela não são tocadas** — o último snapshot bom continua na tela, com o
carimbo da última leitura BOA, que é mais antiga que a última tentativa. Zerar
ou apagar seria transformar "não consegui ler" em "não tem nada", que são fatos
opostos.

O mesmo vale dentro de uma conta: se a consulta de métricas falhar mas a de
campanhas passar, o resultado é `parcial`, as colunas de entrega **não entram no
upsert** (para não sobrescrever a última medição boa com nulos) e a resposta
declara o que faltou.

## Núcleo comum × canal (ADR-17)

Este módulo lê a camada COMUM da campanha — id, nome, status, veiculação,
canal, estratégia, verba e métricas — e não nomeia nenhuma entidade filha de
canal (o gate da §9.4 é um `rg` por esses nomes, e citá-los aqui daria falso
positivo). As entidades filhas de cada canal são lidas
pelo perfil, resolvido em `resolver_perfil()`, que é o ÚNICO ponto do núcleo
onde o nome de um canal decide alguma coisa. Campanha de canal sem perfil entra
no inventário mesmo assim, com as colunas comuns preenchidas e uma linha em
`faltou` dizendo que as filhas daquele canal não foram lidas — em vez de sumir
ou de ganhar uma tela vazia (ADR-19).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import (Any, Callable, Dict, Iterable, Iterator, List, Optional,
                    Protocol, Sequence, Tuple)

from app.trafego import dominio as dom
from app.trafego import inventario as inv

log = logging.getLogger("volc.trafego.sincronizador")


# ── janelas ─────────────────────────────────────────────────────────────────
#
# Vocabulário FECHADO. A janela entra concatenada no GAQL, e concatenar texto
# livre numa query é injeção — mesmo que o GAQL só tenha SELECT, um `DURING`
# escolhido pelo chamador poderia sangrar para outra cláusula.

JANELAS: Tuple[str, ...] = (
    "TODAY", "YESTERDAY", "LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS",
)
JANELA_PADRAO = "LAST_30_DAYS"


class JanelaInvalida(ValueError):
    """Janela fora do vocabulário. Nada foi enviado à API."""


class EscritaNoSincronizador(RuntimeError):
    """Alguém tentou passar algo que não é leitura pela varredura."""


class LimiteExcedido(RuntimeError):
    """Conta varrida recentemente demais. Traz quando ela libera."""

    def __init__(self, customer_id: str, proxima_em: datetime, intervalo_s: int):
        self.customer_id = customer_id
        self.proxima_em = proxima_em
        self.intervalo_s = intervalo_s
        super().__init__(
            f"a conta {customer_id} foi varrida há menos de {intervalo_s}s. "
            f"A próxima varredura é liberada em {proxima_em.isoformat()}."
        )


# ── GAQL da camada comum ────────────────────────────────────────────────────
#
# ⚠️ SEM `WHERE status != 'REMOVED'`. Campanha removida É um estado de presença
# do contrato (`removida`), e filtrá-la aqui faria uma campanha que existe na
# conta, removida, aparecer como `nao_encontrada` — que afirma outra coisa.
# O preço é ler o histórico inteiro de removidas; o SPEC §4.4 manda reavaliar o
# custo a partir de ~50 campanhas, e é aqui que a decisão mora.
GAQL_CAMPANHAS = """
SELECT campaign.id, campaign.name, campaign.status, campaign.serving_status,
       campaign.advertising_channel_type, campaign.bidding_strategy_type,
       campaign_budget.amount_micros
FROM campaign
"""

# ⚠️ MÉTRICA VEM SEGMENTADA POR DIA: a mesma campanha aparece N vezes e cada
# linha é de UM dia. Ler a última daria o último dia e chamaria de "nunca
# gastou" uma campanha que gastou na segunda. Somar é obrigatório — e é por isso
# que o upsert SUBSTITUI o total em vez de acumular.
GAQL_METRICAS = """
SELECT campaign.id, metrics.impressions, metrics.clicks, metrics.cost_micros
FROM campaign WHERE segments.date DURING {janela}
"""

#: Linhas por página do `search`. O SDK encadeia as páginas sozinho quando o
#: pager é iterado; o tamanho existe para o consumo de memória ser previsível.
PAGINA_GAQL = 1000

#: Teto de páginas por consulta. Uma conta que devolvesse páginas
#: indefinidamente prenderia o worker; o teto transforma isso em resultado
#: parcial declarado, que é o modo de falhar deste sistema.
TETO_DE_PAGINAS = 200


def _exigir_leitura(gaql: str) -> str:
    """Recusa qualquer coisa que não seja um SELECT. Não faz rede.

    O sincronizador é somente leitura por decisão de projeto, e decisão que
    depende de ninguém colar a query errada não é decisão — é esperança. A
    checagem é boba de propósito: qualquer coisa que não comece em SELECT, ou
    que traga `;`, não sai daqui.
    """
    limpo = " ".join(str(gaql or "").split())
    if not limpo.upper().startswith("SELECT"):
        raise EscritaNoSincronizador(
            "a varredura só executa SELECT. O que chegou não é uma leitura: "
            f"{limpo[:80]!r}"
        )
    if ";" in limpo:
        raise EscritaNoSincronizador(
            "GAQL com `;`: a varredura não executa comando encadeado."
        )
    return limpo


# ── retentativa com recuo ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Veredito:
    """O que fazer com um erro que veio da API."""

    retentavel: bool
    espera_sugerida_s: Optional[float] = None
    resumo: str = ""


#: Marcas de erro que NÃO adianta retentar. Cinco tentativas contra um
#: `USER_PERMISSION_DENIED` gastam trinta segundos para chegar à mesma resposta,
#: e atrasam as outras contas da rodada.
_TERMINAIS = (
    "USER_PERMISSION_DENIED", "AUTHENTICATION", "AUTHORIZATION",
    "INVALID_ARGUMENT", "NOT_FOUND", "CUSTOMER_NOT_ENABLED",
    "QUERY_ERROR", "UNRECOGNIZED_FIELD",
)


def classificar_padrao(exc: BaseException) -> Veredito:
    """Reusa o classificador do `volc_ads` quando ele estiver disponível.

    Ele conhece o `retry_apos_s` que a própria API sugere no throttle — esperar
    o que o Google mandou esperar é melhor que adivinhar um backoff. Quando o
    SDK não está instalado (o backend sobe sem ele de propósito), cai numa
    heurística por texto, que erra para o lado de retentar.
    """
    try:
        from volc_ads.gads.errors import Classe, classificar  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — ambiente sem SDK é normal aqui
        texto = f"{type(exc).__name__}: {exc}".upper()
        terminal = any(m in texto for m in _TERMINAIS)
        return Veredito(retentavel=not terminal, resumo=str(exc)[:200])
    try:
        f = classificar(exc)
        return Veredito(
            retentavel=f.classe is not Classe.TERMINAL,
            espera_sugerida_s=getattr(f, "retry_apos_s", None),
            resumo=f.resumo()[:200],
        )
    except Exception:  # noqa: BLE001
        return Veredito(retentavel=True, resumo=str(exc)[:200])


@dataclass(frozen=True)
class PoliticaDeRetentativa:
    """Recuo exponencial com jitter.

    O jitter não é enfeite: sem ele, N contas que tomam throttle ao mesmo tempo
    voltam a bater ao mesmo tempo e o throttle se perpetua. É a mesma política
    de `volc_ads/gads/client.py`, repetida aqui porque a varredura precisa dela
    mesmo num ambiente onde o SDK não está instalado.
    """

    tentativas: int = 4
    base_s: float = 1.0
    fator: float = 2.0
    teto_s: float = 30.0
    jitter: float = 0.25

    def espera(self, tentativa: int, sugerida: Optional[float] = None,
               sorteio: Optional[Callable[[float, float], float]] = None) -> float:
        base = sugerida if sugerida is not None else min(
            self.base_s * (self.fator ** tentativa), self.teto_s)
        rnd = sorteio or random.uniform
        return max(0.0, base * (1 + rnd(-self.jitter, self.jitter)))


def com_recuo(
    fn: Callable[[], Any],
    *,
    politica: Optional[PoliticaDeRetentativa] = None,
    rotulo: str = "",
    dormir: Callable[[float], None] = time.sleep,
    classificar: Callable[[BaseException], Veredito] = classificar_padrao,
    sorteio: Optional[Callable[[float, float], float]] = None,
) -> Any:
    """Executa `fn`, retentando só o que vale a pena retentar.

    `dormir` e `sorteio` são injetáveis porque um teste de backoff que dorme de
    verdade leva trinta segundos e ninguém o roda — teste lento é teste que sai
    da suíte.
    """
    pol = politica or PoliticaDeRetentativa()
    ultimo: Optional[BaseException] = None
    esperas: List[float] = []
    for tentativa in range(pol.tentativas):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — reclassificado logo abaixo
            ultimo = exc
            v = classificar(exc)
            if not v.retentavel or tentativa == pol.tentativas - 1:
                if not v.retentavel:
                    log.warning("[%s] terminal, sem retentativa: %s", rotulo, v.resumo)
                break
            atraso = pol.espera(tentativa, v.espera_sugerida_s, sorteio)
            esperas.append(atraso)
            log.warning("[%s] tentativa %d/%d falhou; aguardando %.1fs: %s",
                        rotulo, tentativa + 1, pol.tentativas, atraso, v.resumo)
            dormir(atraso)
    assert ultimo is not None
    raise ultimo


# ── limite de taxa por conta ────────────────────────────────────────────────

#: Intervalo mínimo entre varreduras da MESMA conta, por origem.
#:
#: ⚠️ NÃO SÃO NÚMEROS MEDIDOS — são escolha de operação. O agendado é curto o
#: bastante para não estorvar o ciclo de 15 min do SPEC §4.4 e longo o bastante
#: para conter um cron em laço. O manual é maior porque quem clica "atualizar"
#: clica de novo quando a tela não muda na hora, e cada clique custa ~2 GAQL na
#: conta de outra pessoa.
INTERVALO_MINIMO_S = {"agendado": 60, "manual": 300}
ORIGENS: Tuple[str, ...] = ("agendado", "manual")


class LimiteDeTaxa:
    """Diz se a conta pode ser varrida agora, consultando o próprio histórico.

    A fonte é o REGISTRO de sincronizações, não uma variável de processo: com
    dois workers, um contador em memória libera o dobro das varreduras sem que
    nada denuncie. O relógio é injetável para o teste não depender de esperar.
    """

    def __init__(self, ler_ultima: Callable[[str], Optional[datetime]],
                 *, agora: Optional[Callable[[], datetime]] = None,
                 intervalos: Optional[Dict[str, int]] = None) -> None:
        self._ler_ultima = ler_ultima
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._intervalos = dict(intervalos or INTERVALO_MINIMO_S)

    def exigir(self, customer_id: str, origem: str) -> None:
        intervalo = int(self._intervalos.get(origem, INTERVALO_MINIMO_S["manual"]))
        ultima = self._ler_ultima(customer_id)
        if ultima is None:
            return
        if ultima.tzinfo is None:
            ultima = ultima.replace(tzinfo=timezone.utc)
        proxima = ultima + timedelta(seconds=intervalo)
        if self._agora() < proxima:
            raise LimiteExcedido(customer_id, proxima, intervalo)


# ── perfil de canal (o ponto de extensão do ADR-19) ─────────────────────────


@dataclass(frozen=True)
class LinhaLida:
    """Uma campanha como a varredura a viu. Canal-agnóstica por construção.

    Nenhum campo aqui nomeia entidade filha de canal — o gate da §9.4 do SPEC
    varre estes módulos atrás desses nomes. O que um canal precisa acrescentar
    entra por `PerfilDeCanal.ler_filhas` e chega como número já traduzido para o
    vocabulário comum (`lance_micros`), não como entidade do canal.
    """

    campaign_id: str
    nome: str = ""
    estado_externo: Optional[str] = None
    veiculacao: Optional[str] = None
    canal_bruto: Optional[str] = None
    estrategia_bruta: Optional[str] = None
    verba_diaria_micros: Optional[int] = None
    lance_micros: Optional[int] = None
    impressoes: Optional[int] = None
    cliques: Optional[int] = None
    custo_micros: Optional[int] = None


class PerfilDeCanal(Protocol):
    """O que um canal injeta na varredura. Declarado, e exercitado por Search.

    Régua do ADR-19: um ponto de extensão só existe se Search o usa HOJE. Este
    tem exatamente um consumidor real (`adaptador_search`) e nenhum
    `NotImplementedError` esperando canal futuro.
    """

    canal: str

    def entidades_filhas(self) -> Tuple[str, ...]:
        """Rótulos das entidades que este perfil lê. Vão para o `faltou`."""

    def ler_filhas(self, buscar: Callable[[str], Iterable[Any]],
                   campaign_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """Campos COMUNS extraídos das entidades filhas, por `campaign_id`."""


_PERFIS: Dict[str, PerfilDeCanal] = {}


def registrar_perfil(perfil: PerfilDeCanal) -> None:
    _PERFIS[str(perfil.canal)] = perfil


def resolver_perfil(canal: Optional[str]) -> Optional[PerfilDeCanal]:
    """O ÚNICO ponto do núcleo em que o nome de um canal decide algo.

    O import de `adaptador_search` mora aqui dentro, e não no topo do arquivo,
    para a dependência apontar sempre canal → núcleo: `adaptador_search` importa
    este módulo, e este módulo não pode importá-lo de volta em tempo de carga.
    """
    if not _PERFIS:
        from app.trafego import adaptador_search  # noqa: F401,PLC0415
    return _PERFIS.get(str(canal or ""))


# ── porta de persistência ───────────────────────────────────────────────────


class RepositorioDeSnapshot(Protocol):
    """Onde o snapshot mora. O núcleo não sabe que é PostgREST.

    ## O contrato com o schema canônico

    Cada método aponta para UMA tabela de
    `supabase/migrations/v9_01_trafego_inventario.sql`. A porta anterior falava
    de `volc_trafego_conta`, `volc_trafego_campanha` e
    `volc_trafego_sincronizacao` — três tabelas que nenhuma migration cria. A
    forma dos métodos mudou junto, porque não era rename: era remodelagem.

    · `rodada_concluida` / `registrar_evento` → `trafego_evento`, append-only.
      A chave de idempotência mora em `chave_de_agrupamento`.

    · `ultima_tentativa` → `trafego_snapshot_conta.tentativa_em`. Alimenta o
      limite de taxa, que consulta o REGISTRO e não um contador de processo:
      com dois workers, um contador em memória libera o dobro das varreduras.

    · `identidades` / `declarar_identidades` → `trafego_campanha`. A IDENTIDADE
      é o que o VOLC declara, e ela é escrita UMA VEZ. `declarar_identidades`
      faz INSERT que IGNORA duplicata — nunca um upsert que reescreve. O gatilho
      `trafego_campanha_identidade_imutavel` recusaria a reescrita de
      `criada_em`, e um upsert cego mandaria `now()` a cada varredura: a segunda
      passada de toda conta explodiria.

    · `espelhos` / `gravar_espelhos` → `trafego_campanha_espelho`. Aqui SIM é
      upsert: o espelho é a leitura corrente e ela se substitui.

    · `gravar_snapshot_de_conta` → `trafego_snapshot_conta`, upsert.
      ⚠️ `tentativa_resultado` só aceita `'ok'` ou `'falhou'` (CHECK do banco).
      O terceiro desfecho da varredura viaja em `tentativa_motivo` — ver
      `dominio.frescor_da_conta`.

    ## ⚠️ QUAIS NULOS VÃO NO PAYLOAD, E QUAIS NÃO VÃO

    O upsert do PostgREST monta o `SET` a partir das chaves ENVIADAS, então
    omitir uma chave preserva o valor antigo e enviá-la com `null` o apaga. As
    duas coisas são necessárias, em colunas diferentes da MESMA linha, e trocá-las
    produz erro silencioso — nada falha, a tela é que passa a mentir:

    · **enviar sempre, mesmo nulo** — `tentativa_motivo` e
      `espelho.presenca`. Elas descrevem a tentativa/leitura DE AGORA. Omitir
      `tentativa_motivo` numa varredura que deu certo deixaria o motivo da falha
      anterior colado na linha, e `dominio.frescor_da_conta` derivaria `parcial`
      para sempre numa conta saudável. Omitir `presenca` deixaria `removida`
      grudada numa campanha que voltou.

    · **omitir quando nulo** — `leitura_boa_em`, `leitura_boa_campanhas`,
      `leitura_boa_duracao_ms` e as quatro colunas de entrega
      (`impressoes`, `cliques`, `custo_micros`, `moeda`, `entrega_lida_em`).
      Elas descrevem a última leitura BOA, que uma tentativa ruim não tem o
      direito de apagar (regra C). Os gatilhos do banco também guardam isso —
      duas travas independentes, de propósito —, mas mandar `null` explícito
      contra um gatilho que preserva é pedir para descobrir qual dos dois vence.

    · `marcar_ausentes` → `trafego_campanha_espelho.presenca`, para as campanhas
      que a conta deixou de responder.

    ## O que a porta NÃO faz

    Não apaga nada. Não existe `DELETE` neste domínio, e a migration nem concede
    o privilégio: presença substitui exclusão, porque "sumiu" é uma conclusão e
    a conclusão erra quando a causa foi uma leitura que falhou.
    """

    async def rodada_concluida(self, chave: str) -> Optional[Dict[str, Any]]:
        """O evento de uma rodada que JÁ DEU CERTO com esta chave, ou `None`."""
        ...

    async def registrar_evento(self, evento: Dict[str, Any]) -> None:
        ...

    async def ultima_tentativa(self, customer_id: str) -> Optional[datetime]:
        ...

    async def identidades(self, customer_id: str) -> Dict[str, Dict[str, Any]]:
        """`campaign_id` → linha de `trafego_campanha`."""
        ...

    async def declarar_identidades(self, linhas: List[Dict[str, Any]]) -> None:
        """INSERT que ignora duplicata. NUNCA upsert — ver a docstring da classe."""
        ...

    async def espelhos(self, customer_id: str) -> Dict[str, Dict[str, Any]]:
        """`volc_campaign_id` → linha de `trafego_campanha_espelho`."""
        ...

    async def gravar_espelhos(self, linhas: List[Dict[str, Any]]) -> None:
        ...

    async def gravar_snapshot_de_conta(self, linha: Dict[str, Any]) -> None:
        ...

    async def marcar_ausentes(self, customer_id: str,
                              vistos: Sequence[str],
                              quando: datetime) -> int:
        """`vistos` são `volc_campaign_id`, não `campaign_id`."""
        ...


# ── identidade ──────────────────────────────────────────────────────────────


#: O espaço de nomes da identidade derivada. É um UUID fixo e arbitrário; o que
#: importa é que ele NUNCA mude, porque mudá-lo cunharia uma segunda identidade
#: para toda campanha já conhecida — o defeito que ADR-02 existe para impedir.
ESPACO_DA_IDENTIDADE = uuid.UUID("5b1d5f3e-7a2c-5f4b-9c88-0a1f2e3d4c5b")


def volc_campaign_id(customer_id: str, campaign_id: str) -> str:
    """Identidade interna 1:1 com a campanha externa, derivada e imutável.

    Derivada, e não sorteada, por um motivo operacional: a varredura precisa ser
    idempotente sem uma ida ao banco por campanha para descobrir se já existe
    identidade. Um UUID sorteado exigiria essa consulta, e um erro nela cunharia
    uma SEGUNDA identidade para a mesma campanha externa — que é exatamente o
    que `volcCampaignId` existe para não deixar acontecer (ADR-02).

    O par `(customer_id, campaign_id)` nunca muda no Google Ads: campanha não
    troca de conta. A identidade herda essa estabilidade.

    ## Por que UUID, e não `gads-<conta>-<campanha>`

    Era essa a forma antes, e ela é mais legível. Mas
    `trafego_campanha.volc_campaign_id` é `uuid` — a string legível seria
    recusada pelo tipo da coluna, na primeira gravação contra o banco real. Um
    UUIDv5 preserva as duas propriedades que importam (derivado do par externo,
    estável para sempre) e cabe na coluna.

    A legibilidade que se perde está guardada: `customer_id` e `campaign_id`
    continuam colunas próprias na mesma linha, e é por elas que se procura.
    """
    cid = "".join(ch for ch in str(customer_id or "") if ch.isdigit())
    kid = "".join(ch for ch in str(campaign_id or "") if ch.isdigit())
    if not cid or not kid:
        raise ValueError(
            "identidade exige conta e campanha; linha sem conta pertence ao "
            f"grupo {inv.SEM_CONTA!r} e não recebe volc_campaign_id derivado."
        )
    return str(uuid.uuid5(ESPACO_DA_IDENTIDADE, f"gads:{cid}:{kid}"))


# ── a varredura ─────────────────────────────────────────────────────────────


@dataclass
class ResultadoDaConta:
    """O que a varredura de UMA conta produziu. É o que vira observabilidade."""

    customer_id: str
    resultado: str = "ok"            # ok | parcial | falhou
    lidas: int = 0
    falhas: int = 0
    duracao_ms: int = 0
    motivo: Optional[str] = None
    faltou: List[Dict[str, str]] = field(default_factory=list)
    consultas: int = 0
    repetida: bool = False
    vazio_confirmado: bool = False

    def json(self) -> Dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "resultado": self.resultado,
            "lidas": self.lidas,
            "falhas": self.falhas,
            "duracao_ms": self.duracao_ms,
            "motivo": self.motivo,
            "faltou": list(self.faltou),
            "consultas": self.consultas,
            "repetida": self.repetida,
        }


def _paginas(resposta: Any) -> Iterator[Any]:
    """Percorre a resposta do `search` página a página.

    O pager do SDK expõe `.pages`, e cada página traz `.results`. Um dublê pode
    entregar só um iterável de linhas — daí o segundo ramo. É um `hasattr` e ele
    está aqui, num lugar só, em vez de espalhado por cada consulta.
    """
    paginas = getattr(resposta, "pages", None)
    if paginas is None:
        yield from (resposta or ())
        return
    vistas = 0
    for pagina in paginas:
        vistas += 1
        yield from (getattr(pagina, "results", pagina) or ())
        if vistas >= TETO_DE_PAGINAS:
            log.warning("teto de %d páginas atingido; resultado é parcial",
                        TETO_DE_PAGINAS)
            break


def leitor_google_ads(customer_id: str, *, login_customer_id: str,
                      servico: Any = None,
                      politica: Optional[PoliticaDeRetentativa] = None,
                      dormir: Callable[[float], None] = time.sleep,
                      ) -> Callable[[str], List[Any]]:
    """Devolve um `buscar(gaql) -> linhas`, com paginação e recuo.

    ⚠️ Import tardio do SDK: o backend sobe em ambiente sem `google-ads`
    instalado de propósito (as rotas do Pautador e do Redator não têm nada a ver
    com isso), e um import no topo derrubaria tudo.
    """
    svc = servico
    if svc is None:
        from volc_ads.gads.client import cliente  # noqa: PLC0415
        svc = cliente(str(login_customer_id)).get_service("GoogleAdsService")

    def buscar(gaql: str) -> List[Any]:
        query = _exigir_leitura(gaql)

        def _rodar() -> List[Any]:
            # ⚠️ SEM `page_size`. Ele existia na `SearchGoogleAdsRequest` até a
            # v20 e foi REMOVIDO na v21 (google-ads 31.x, que é o SDK instalado
            # aqui): passá-lo levanta `TypeError` antes de qualquer requisição
            # sair. Quem pagina agora é o servidor, e `_paginas` já consome o
            # iterador até o fim — o tamanho da página nunca foi decisão nossa,
            # era só um número que dava a impressão de controle.
            #
            # Descoberto na primeira varredura REAL: os testes dublam o serviço,
            # e um dublê aceita qualquer assinatura.
            resposta = svc.search(customer_id=str(customer_id), query=query)
            # Materializa: um gerador que estoura no meio do consumo não pode
            # ser retentado sem duplicar o que já saiu.
            return list(_paginas(resposta))

        return com_recuo(_rodar, politica=politica,
                         rotulo=f"varredura:{customer_id}", dormir=dormir)

    return buscar


def _nome_do_enum(v: Any) -> Optional[str]:
    if v is None:
        return None
    nome = getattr(v, "name", None)
    return str(nome if nome is not None else v)


def _int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def ler_camada_comum(buscar: Callable[[str], Iterable[Any]]) -> List[LinhaLida]:
    """As colunas que toda campanha tem, seja qual for o canal."""
    linhas: List[LinhaLida] = []
    for row in buscar(GAQL_CAMPANHAS):
        c = row.campaign
        orcamento = getattr(row, "campaign_budget", None)
        linhas.append(LinhaLida(
            campaign_id=str(c.id),
            nome=str(getattr(c, "name", "") or ""),
            estado_externo=_nome_do_enum(getattr(c, "status", None)),
            veiculacao=_nome_do_enum(getattr(c, "serving_status", None)),
            canal_bruto=_nome_do_enum(getattr(c, "advertising_channel_type", None)),
            estrategia_bruta=_nome_do_enum(getattr(c, "bidding_strategy_type", None)),
            verba_diaria_micros=_int(getattr(orcamento, "amount_micros", None)),
        ))
    return linhas


def somar_metricas(buscar: Callable[[str], Iterable[Any]],
                   janela: str) -> Dict[str, Dict[str, int]]:
    """Entrega por campanha na janela. SOMA as linhas diárias — ver o GAQL."""
    if janela not in JANELAS:
        raise JanelaInvalida(
            f"janela {janela!r} não existe. As janelas são: {', '.join(JANELAS)}."
        )
    # ⚠️ REGRA B, NA ORIGEM. `int(getattr(m, "impressions", 0) or 0)` — que era
    # o que estava aqui — transforma métrica AUSENTE em zero antes de o dado
    # chegar ao banco. Depois disso não há como distinguir "a campanha não
    # apareceu" de "não conseguimos medir": o zero já foi gravado, e toda a
    # camada acima passa a mostrar um fato que ninguém observou.
    #
    # Zero é resultado. Ausência é ausência. Aqui elas se separam, e é o único
    # lugar onde ainda dá para separá-las.
    def _medida(m: Any, campo: str) -> Optional[int]:
        if not hasattr(m, campo):
            return None
        bruto = getattr(m, campo)
        if bruto is None:
            return None
        try:
            return int(bruto)
        except (TypeError, ValueError):
            return None

    def _somar(atual: Optional[int], novo: Optional[int]) -> Optional[int]:
        """Soma preservando a ausência.

        Se QUALQUER linha do relatório não trouxe a medida, o total daquela
        campanha é desconhecido — somar as que vieram daria um número menor que
        o real, com cara de medida boa. Melhor não responder do que responder
        baixo.
        """
        if atual is None or novo is None:
            return None
        return atual + novo

    saida: Dict[str, Dict[str, Optional[int]]] = {}
    vistos: set = set()
    for row in buscar(GAQL_METRICAS.format(janela=janela)):
        chave = str(row.campaign.id)
        m = row.metrics
        if chave not in vistos:
            vistos.add(chave)
            saida[chave] = {
                "impressoes": _medida(m, "impressions"),
                "cliques": _medida(m, "clicks"),
                "custo_micros": _medida(m, "cost_micros"),
            }
            continue
        d = saida[chave]
        d["impressoes"] = _somar(d["impressoes"], _medida(m, "impressions"))
        d["cliques"] = _somar(d["cliques"], _medida(m, "clicks"))
        d["custo_micros"] = _somar(d["custo_micros"], _medida(m, "cost_micros"))
    return saida


# ── eventos: o diário que torna `horas_ligada` derivável ────────────────────
#
# ⚠️ O gatilho `trafego_snapshot_registra_tentativa` já apenda um evento por
# TENTATIVA de leitura de conta — esse diário o banco escreve sozinho, e
# duplicá-lo aqui criaria duas linhas para o mesmo fato. O que este módulo
# apenda é o que o banco não tem como saber: a MUDANÇA DE ESTADO de uma
# campanha, que só quem comparou a leitura nova com a antiga observou.
#
# É deste diário que `alertas.horas_ligada()` sai. Sem ele, "ligada há 22 horas"
# exigiria uma consulta à conta em tempo de render — que é exatamente o custo
# que esta fase inteira existe para eliminar.

PRODUTOR = "backend:trafego.sincronizador"


def evento_de_estado(*, volc_id: str, customer_id: str, campaign_id: str,
                     de: Optional[str], para: Optional[str],
                     quando: datetime) -> Dict[str, Any]:
    """Uma transição observada, na forma de `trafego_evento`.

    `de=None` é a PRIMEIRA vez que vimos esta campanha, e não "estava desligada".
    A distinção é o que faz `horas_ligada` significar "a conta responde ENABLED
    desde que começamos a olhar" em vez de inventar uma data de criação.
    """
    from app.trafego import alertas  # noqa: PLC0415 — só pelo nome da chave

    return {
        "ocorrido_em": quando.isoformat(),
        "tipo": alertas.TIPO_ESTADO,
        "chave_de_agrupamento": alertas.chave_de_estado(volc_id),
        "produtor": PRODUTOR,
        "sujeito_tipo": "campanha",
        "sujeito_id": str(campaign_id),
        "customer_id": customer_id,
        "volc_campaign_id": volc_id,
        "carga": {"de": de, "para": para},
    }


def chave_da_rodada(chave_idempotencia: str) -> str:
    """O endereço da memória de idempotência dentro de `trafego_evento`.

    Prefixada para não colidir com a chave de agrupamento das transições de
    estado: as duas moram na mesma coluna opaca, e uma colisão faria uma
    varredura ser considerada "já feita" por causa de uma campanha.
    """
    return f"trafego.sincronizacao.rodada:{chave_idempotencia}"


async def sincronizar_conta(
    conta: Dict[str, Any],
    repo: RepositorioDeSnapshot,
    *,
    buscar: Callable[[str], Iterable[Any]],
    janela: str = JANELA_PADRAO,
    origem: str = "agendado",
    chave_idempotencia: Optional[str] = None,
    limite: Optional[LimiteDeTaxa] = None,
    agora: Optional[datetime] = None,
) -> ResultadoDaConta:
    """Varre UMA conta e grava o snapshot. Somente leitura na conta.

    A ordem das gravações é deliberada, e são três degraus:

    1. **identidade** (`trafego_campanha`), porque o espelho tem FK para ela;
    2. **espelho** (`trafego_campanha_espelho`), a leitura corrente;
    3. **snapshot da conta** (`trafego_snapshot_conta`), o carimbo.

    Se o processo morrer no meio, o snapshot fica com dados novos e carimbo
    antigo — a tela mostra "velho" sobre dado bom. A ordem inversa mostraria
    "recente" sobre dado velho, que é a mentira que este módulo inteiro existe
    para não contar.
    """
    if janela not in JANELAS:
        raise JanelaInvalida(
            f"janela {janela!r} não existe. As janelas são: {', '.join(JANELAS)}."
        )
    if origem not in ORIGENS:
        raise ValueError(f"origem {origem!r} não existe. Use: {', '.join(ORIGENS)}.")

    cid = "".join(ch for ch in str(conta.get("customer_id") or "") if ch.isdigit())
    if not cid:
        raise ValueError("varredura sem customer_id: não há onde procurar.")

    agora = agora or datetime.now(timezone.utc)
    res = ResultadoDaConta(customer_id=cid)

    if chave_idempotencia:
        # ⚠️ SÓ SUCESSO É MEMORIZADO — e agora por CONSTRUÇÃO, não por
        # inspeção. O evento de rodada só é apendado no fim do caminho feliz,
        # então a existência dele já significa "deu certo". A versão anterior
        # gravava sempre e conferia o campo `resultado` depois; bastava alguém
        # esquecer a conferência para uma conta que caiu por timeout ficar
        # permanentemente sem snapshot, com o log dizendo "repetida".
        #
        # Idempotência existe para não repetir TRABALHO FEITO. Uma falha não é
        # trabalho feito; é justamente o que o retry veio refazer.
        anterior = await repo.rodada_concluida(chave_da_rodada(chave_idempotencia))
        if anterior:
            carga = anterior.get("carga") or {}
            res.repetida = True
            res.resultado = str(carga.get("resultado") or "ok")
            res.lidas = int(carga.get("lidas") or 0)
            res.falhas = int(carga.get("falhas") or 0)
            res.duracao_ms = int(carga.get("duracao_ms") or 0)
            return res

    if limite is not None:
        limite.exigir(cid, origem)

    inicio = time.monotonic()
    try:
        linhas = await asyncio.to_thread(ler_camada_comum, buscar)
        res.consultas += 1
    except Exception as exc:  # noqa: BLE001 — a conta degrada, a rodada segue
        res.resultado = "falhou"
        res.falhas = 1
        res.motivo = f"{type(exc).__name__}: {exc}"[:300]
        res.duracao_ms = int((time.monotonic() - inicio) * 1000)
        log.warning("varredura da conta %s falhou: %s", cid, res.motivo)
        # ⚠️ NÃO toca no espelho: o último snapshot bom continua na tela, com a
        # idade visível. Apagar transformaria "não consegui ler" em "não tem
        # nada". E `leitura_boa_*` não vai no payload — o gatilho
        # `trafego_snapshot_preserva_ultima_boa` guarda o que já havia, sem
        # depender de este código lembrar.
        await repo.gravar_snapshot_de_conta({
            "customer_id": cid,
            "nome": conta.get("nome"),
            "tentativa_em": agora.isoformat(),
            "tentativa_resultado": "falhou",
            "tentativa_motivo": res.motivo,
            "tentativa_duracao_ms": res.duracao_ms,
        })
        return res

    # Entrega. Falhar aqui NÃO derruba a conta: o inventário fica com o estado e
    # a verba (que vieram) e sem os números (que não vieram), declarados como
    # `null` e não como zero.
    entrega: Dict[str, Dict[str, int]] = {}
    entrega_lida_em: Optional[datetime] = None
    try:
        entrega = await asyncio.to_thread(somar_metricas, buscar, janela)
        entrega_lida_em = agora
        res.consultas += 1
    except Exception as exc:  # noqa: BLE001
        res.resultado = "parcial"
        res.falhas += 1
        res.faltou.append({
            "escopo": f"entrega({janela})",
            "motivo": f"{type(exc).__name__}: {exc}"[:200],
        })
        log.warning("entrega da conta %s não voltou: %s", cid, exc)

    # As entidades filhas de cada canal, pelo perfil. O núcleo não sabe o que
    # elas são: recebe campos comuns já traduzidos.
    por_canal: Dict[Optional[str], List[str]] = {}
    for l in linhas:
        por_canal.setdefault(inv.canal_canonico(l.canal_bruto), []).append(l.campaign_id)

    extras: Dict[str, Dict[str, Any]] = {}
    for canal, ids in por_canal.items():
        perfil = resolver_perfil(canal)
        if perfil is None:
            res.faltou.append({
                "escopo": f"filhas({canal or 'canal desconhecido'})",
                "motivo": (
                    f"não há adaptador de leitura para {canal or 'este canal'}; "
                    f"{len(ids)} campanha(s) entram com as colunas comuns e sem "
                    f"lance"
                ),
            })
            if res.resultado == "ok":
                res.resultado = "parcial"
            continue
        try:
            extras.update(await asyncio.to_thread(perfil.ler_filhas, buscar, ids))
            res.consultas += 1
        except Exception as exc:  # noqa: BLE001
            res.resultado = "parcial"
            res.falhas += 1
            res.faltou.append({
                "escopo": f"filhas({canal})",
                "motivo": f"{type(exc).__name__}: {exc}"[:200],
            })

    # ── 1. IDENTIDADE — declarada uma vez, nunca reescrita ──────────────────
    conhecidas = await repo.identidades(cid)
    novas: List[Dict[str, Any]] = []
    for l in linhas:
        if l.campaign_id in conhecidas:
            continue
        novas.append({
            "volc_campaign_id": volc_campaign_id(cid, l.campaign_id),
            "customer_id": cid,
            "campaign_id": l.campaign_id,
            # A varredura DESCOBRE campanhas; ela não as cria. `descoberta` é a
            # procedência honesta, e declará-la aqui é o que impede a linha de
            # nascer `desconhecida` e ficar assim para sempre — o gatilho de
            # imutabilidade só admite a primeira declaração.
            "procedencia": inv.DESCOBERTA,
            "procedencia_declarada_por": PRODUTOR,
            "procedencia_declarada_em": agora.isoformat(),
            "criada_por": PRODUTOR,
        })
    if novas:
        await repo.declarar_identidades(novas)

    # ── 2. ESPELHO — a leitura corrente, com as transições observadas ───────
    antes = await repo.espelhos(cid)
    moeda = conta.get("moeda") or None
    para_gravar: List[Dict[str, Any]] = []
    vistos: List[str] = []
    transicoes: List[Dict[str, Any]] = []

    for l in linhas:
        extra = extras.get(l.campaign_id) or {}
        volc_id = (conhecidas.get(l.campaign_id, {}).get("volc_campaign_id")
                   or volc_campaign_id(cid, l.campaign_id))
        volc_id = str(volc_id)
        vistos.append(volc_id)

        estado_novo = l.estado_externo
        estado_antigo = (antes.get(volc_id) or {}).get("estado_externo")
        if str(estado_antigo or "") != str(estado_novo or ""):
            transicoes.append(evento_de_estado(
                volc_id=volc_id, customer_id=cid, campaign_id=l.campaign_id,
                de=estado_antigo, para=estado_novo, quando=agora))

        canal_no_espelho = dom.canal_para_espelho(l.canal_bruto)
        if canal_no_espelho == "UNKNOWN" and dom.texto_ou_nulo(
                l.canal_bruto) not in (None, "UNKNOWN"):
            # A substituição é DECLARADA, e não silenciosa. Sem esta linha, um
            # enum novo do Google apareceria na tela como "UNKNOWN" e ninguém
            # saberia que a conta tinha respondido outra coisa.
            res.faltou.append({
                "escopo": f"canal({l.campaign_id})",
                "motivo": (f"a conta respondeu canal {l.canal_bruto!r}, que não "
                           f"está no vocabulário canônico; o espelho gravou "
                           f"UNKNOWN para não recusar a varredura inteira"),
            })
            if res.resultado == "ok":
                res.resultado = "parcial"

        linha: Dict[str, Any] = {
            "volc_campaign_id": volc_id,
            "lido_em": agora.isoformat(),
            "nome": dom.texto_ou_nulo(l.nome),
            "estado_externo": dom.texto_ou_nulo(l.estado_externo),
            "veiculacao": dom.texto_ou_nulo(l.veiculacao),
            # ⚠️ Passa pela normalização em vez de ir cru: a CHECK de canal é
            # fechada nos quinze nomes do enum, e o Google acrescenta valores
            # sem avisar. Um enum novo recusaria o INSERT e derrubaria a
            # varredura da conta inteira — que apareceria como "sincronização
            # falhou" numa conta que respondeu perfeitamente.
            "canal": canal_no_espelho,
            # `estrategia` só não pode ser VAZIA (a lista é aberta de propósito:
            # a conta responde TARGET_ROAS, MAXIMIZE_CLICKS e mais meia dúzia).
            "estrategia": dom.texto_ou_nulo(l.estrategia_bruta),
            "verba_diaria_micros": l.verba_diaria_micros,
            "lance_micros": extra.get("lance_micros", l.lance_micros),
            # A URL de destino vem do PERFIL: no Search ela mora no anúncio, em
            # Performance Max moraria no asset group, e o núcleo não sabe a
            # diferença. Chega aqui já traduzida para o vocabulário comum.
            #
            # ⚠️ Só entra no payload quando o perfil a declarou. `extra` sem a
            # chave significa "não perguntei", e gravar `None` aí apagaria a
            # última URL boa numa varredura em que a leitura do anúncio falhou —
            # a regra C, na coluna que a reconciliação mais precisa.
            **({"url_final": extra["url_final"]} if "url_final" in extra else {}),
            # ⚠️ NULO É O CASO NORMAL, e não um esquecimento. A CHECK do banco
            # aceita os seis estados OU nulo, e nenhum dos seis nomeia "está lá,
            # sem ressalva". Gravar `presente` aqui — que era o que este código
            # fazia — seria recusado pela constraint na primeira gravação real.
            "presenca": (inv.REMOVIDA
                         if (l.estado_externo or "").upper() == "REMOVED"
                         else None),
        }
        if entrega_lida_em is not None:
            m = entrega.get(l.campaign_id) or {}
            # Campanha sem linha de métrica na janela é ZERO MEDIDO, não
            # ausência: a conta respondeu e ela não apareceu no leilão.
            linha["impressoes"] = m.get("impressoes", 0)
            linha["cliques"] = m.get("cliques", 0)
            linha["custo_micros"] = m.get("custo_micros", 0)
            linha["moeda"] = dom.moeda_iso(moeda)
            linha["entrega_lida_em"] = entrega_lida_em.isoformat()
        para_gravar.append(linha)

    # ⚠️ Sem `entrega_lida_em`, as colunas de entrega NÃO entram no payload — o
    # upsert monta o SET a partir das chaves enviadas, então omitir preserva a
    # última medição boa em vez de sobrescrevê-la com nulos. O gatilho
    # `trafego_espelho_preserva_ultima_boa` faz a mesma guarda do lado do banco:
    # duas travas independentes para a mesma regra, que é o ponto.
    if para_gravar:
        await repo.gravar_espelhos(para_gravar)

    # O diário depois do espelho: um evento sobre uma linha que não existe é
    # forense sobre nada. (`trafego_evento` não tem FK de propósito, mas a
    # ordem certa continua sendo a ordem certa.)
    for evento in transicoes:
        await repo.registrar_evento(evento)

    # `nao_encontrada` só depois de uma leitura BOA da camada comum. Numa
    # varredura que falhou, ninguém pode afirmar ausência.
    ausentes = await repo.marcar_ausentes(cid, vistos, agora)

    res.lidas = len(linhas)
    res.vazio_confirmado = not linhas
    res.duracao_ms = int((time.monotonic() - inicio) * 1000)

    # ── 3. CARIMBO ─────────────────────────────────────────────────────────
    # ⚠️ `tentativa_resultado` é 'ok' mesmo quando a varredura foi PARCIAL: a
    # CHECK do banco só admite 'ok' e 'falhou'. O terceiro desfecho viaja em
    # `tentativa_motivo`, e `dominio.frescor_da_conta` o lê de volta como
    # `parcial`. Uma coluna a mais seria a alternativa; um valor fora da CHECK
    # seria uma gravação recusada em produção e verde no teste.
    motivo = (res.faltou[0]["motivo"] if res.faltou else None)
    if res.resultado == "parcial" and res.faltou:
        motivo = f"{res.faltou[0]['escopo']}: {res.faltou[0]['motivo']}"
    await repo.gravar_snapshot_de_conta({
        "customer_id": cid,
        "nome": conta.get("nome"),
        "tentativa_em": agora.isoformat(),
        "tentativa_resultado": "ok",
        "tentativa_motivo": motivo,
        "tentativa_duracao_ms": res.duracao_ms,
        "leitura_boa_em": agora.isoformat(),
        "leitura_boa_campanhas": res.lidas,
        "leitura_boa_duracao_ms": res.duracao_ms,
    })

    if chave_idempotencia:
        await repo.registrar_evento(_evento_de_rodada(
            res, cid, janela, origem, chave_idempotencia, agora,
            ausentes=ausentes))
    return res


def _evento_de_rodada(res: ResultadoDaConta, cid: str, janela: str, origem: str,
                      chave: str, agora: datetime,
                      ausentes: int = 0) -> Dict[str, Any]:
    """A memória de idempotência E a observabilidade, na mesma linha.

    Quanto durou, quantas entidades, quantas falhas, qual conta — e o que
    faltou. Sem isto, "a varredura está lenta" é opinião (SPEC §10.2).

    ⚠️ Ele só é escrito no caminho de sucesso. Ver o comentário em
    `sincronizar_conta`: a existência do evento É a afirmação "esta chave já
    rodou e deu certo", e uma afirmação que depende de alguém conferir um campo
    depois não é garantia.
    """
    return {
        "ocorrido_em": agora.isoformat(),
        "tipo": "trafego.sincronizacao.rodada",
        "chave_de_agrupamento": chave_da_rodada(chave),
        "produtor": PRODUTOR,
        "sujeito_tipo": "conta",
        "sujeito_id": cid,
        "customer_id": cid,
        "carga": {
            "janela": janela,
            "origem": origem,
            "duracao_ms": res.duracao_ms,
            "resultado": res.resultado,
            "lidas": res.lidas,
            "falhas": res.falhas,
            "consultas": res.consultas,
            "faltou": res.faltou,
            "marcadas_ausentes": ausentes,
        },
    }


async def sincronizar(
    contas: Sequence[Dict[str, Any]],
    repo: RepositorioDeSnapshot,
    *,
    fabrica_de_busca: Callable[[Dict[str, Any]], Callable[[str], Iterable[Any]]],
    janela: str = JANELA_PADRAO,
    origem: str = "agendado",
    chave_idempotencia: Optional[str] = None,
    limite: Optional[LimiteDeTaxa] = None,
    agora: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Varre várias contas, uma a uma, com isolamento entre elas.

    Serial e não concorrente de propósito: a quota do Google Ads é por
    credencial, e disparar N contas em paralelo troca "uma conta lenta" por
    "todas throttled". Com as 3 contas da casa e ~2,4 s de descoberta (E-07), o
    ganho do paralelo não paga o risco.
    """
    resultados: List[ResultadoDaConta] = []
    faltou: List[Dict[str, Any]] = []
    for conta in contas:
        cid = str(conta.get("customer_id") or "")
        chave = (f"{chave_idempotencia}:{cid}" if chave_idempotencia else None)
        try:
            r = await sincronizar_conta(
                conta, repo, buscar=fabrica_de_busca(conta), janela=janela,
                origem=origem, chave_idempotencia=chave, limite=limite,
                agora=agora)
        except LimiteExcedido as exc:
            faltou.append({"customer_id": cid, "escopo": "conta",
                           "motivo": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 — nenhuma conta derruba a rodada
            log.exception("varredura da conta %s explodiu", cid)
            faltou.append({"customer_id": cid, "escopo": "conta",
                           "motivo": f"{type(exc).__name__}: {exc}"[:300]})
            continue
        resultados.append(r)
        for f in r.faltou:
            faltou.append({"customer_id": cid, **f})
        if r.resultado == "falhou":
            faltou.append({"customer_id": cid, "escopo": "conta",
                           "motivo": r.motivo or "varredura falhou"})

    return {
        "contas": [r.json() for r in resultados],
        "faltou": faltou,
        "parcial": bool(faltou),
        "janela": janela,
        "origem": origem,
    }


def chave_de_janela(customer_id: str, janela: str, agora: datetime,
                    minutos: int = 15) -> str:
    """Chave de idempotência derivada do balde de tempo do agendamento.

    Serve ao scheduler: dois disparos no mesmo balde de 15 min são a mesma
    intenção, e o segundo não deve custar quota. Quem quiser forçar manda a
    própria chave — ou usa a origem `manual`, que tem limite de taxa próprio.
    """
    balde = int(agora.timestamp() // (minutos * 60))
    cru = f"{customer_id}|{janela}|{balde}".encode("utf-8")
    return hashlib.sha1(cru).hexdigest()  # noqa: S324 — chave, não segredo


# ═══════════════════════════════════════════════════════════════════════════
# A PORTA DE PERSISTÊNCIA — e o defeito que ela fecha
#
# Aqui vivia `RepositorioSupabase`, que escrevia em `volc_trafego_conta`,
# `volc_trafego_campanha` e `volc_trafego_sincronizacao`. As três NÃO EXISTEM:
# nenhuma migration deste repositório as cria. Contra o banco real, toda
# varredura terminava em 404 do PostgREST — e a suíte passava, porque o
# repositório era dublado em 100% dos testes.
#
# Não era um rename pendente. `volc_trafego_campanha` misturava o que o VOLC
# DECLARA (identidade, procedência) com o que a conta RESPONDEU (nome, estado,
# entrega) na mesma linha; o schema canônico separa em `trafego_campanha` e
# `trafego_campanha_espelho`, e a separação é o conserto de E-08 — foi um
# gatilho de espelho sobrescrevendo uma declaração da aplicação que tornou a
# procedência inalcançável em `campaigns`.
#
# A classe foi REMOVIDA, e não reapontada. Reapontá-la criaria uma segunda
# camada de acesso concorrendo com `app/trafego/persistencia.py` (Frente A), e
# duas camadas sobre o mesmo schema divergem como as duas regras de frescor
# divergiram.
#
# O que fica é a PORTA (`RepositorioDeSnapshot`, acima, com o mapeamento tabela
# a tabela) e UMA função de fábrica — o ponto de troca.
# ═══════════════════════════════════════════════════════════════════════════

#: ESQUEMA CANÔNICO — seis tabelas:
#:   trafego_linhagem · trafego_campanha · trafego_campanha_espelho ·
#:   trafego_snapshot_conta · trafego_vinculo · trafego_evento
SCHEMA_CANONICO = "supabase/migrations/v9_01_trafego_inventario.sql"

#: As tabelas que a varredura pode escrever. `trafego_linhagem` e
#: `trafego_vinculo` NÃO estão aqui: linhagem e vínculo são decisões humanas
#: (ADR-09), e uma varredura que as escrevesse estaria confirmando sozinha o que
#: o contrato manda um operador confirmar.
TABELAS_DA_VARREDURA: Tuple[str, ...] = (
    "trafego_campanha", "trafego_campanha_espelho", "trafego_snapshot_conta",
    "trafego_evento",
)


#: Os métodos que `RepositorioDeSnapshot` exige. Existe como dado, e não só
#: como `Protocol`, porque `Protocol` sem `runtime_checkable` não verifica nada
#: em tempo de execução — e o que falha em produção não é a anotação, é a
#: chamada de um método que não existe.
METODOS_DO_REPOSITORIO: Tuple[str, ...] = (
    "rodada_concluida", "registrar_evento", "ultima_tentativa",
    "identidades", "declarar_identidades", "espelhos", "gravar_espelhos",
    "gravar_snapshot_de_conta", "marcar_ausentes",
)


class PortaIncompativel(RuntimeError):
    """A implementação de acesso não satisfaz a porta que a varredura usa."""


def conferir_porta(repo: Any) -> Any:
    """Recusa uma implementação incompleta ANTES da primeira gravação.

    ⚠️ Sem isto, a incompatibilidade aparece no meio de uma varredura, como um
    `AttributeError` numa conta — depois de o GAQL já ter sido gasto, e com
    metade do snapshot escrito. Conferir na fábrica troca uma falha parcial e
    cara por uma mensagem que diz exatamente o que falta.
    """
    faltando = [m for m in METODOS_DO_REPOSITORIO if not callable(getattr(repo, m, None))]
    if faltando:
        raise PortaIncompativel(
            f"{type(repo).__name__} não satisfaz `RepositorioDeSnapshot`: "
            f"faltam {', '.join(faltando)}. A porta e o mapeamento tabela a "
            f"tabela estão documentados na docstring da classe, neste arquivo."
        )
    return repo


def fabricar_repositorio(base: str, chave: str) -> RepositorioDeSnapshot:
    """O ÚNICO ponto de troca entre a varredura e o acesso a dados.

    ⚠️ Ponto de integração declarado. A implementação vive em
    `app/trafego/persistencia.py` (Frente A) e não é importada no topo deste
    arquivo: o núcleo não depende da infraestrutura em tempo de carga.

    Enquanto `persistencia.py` não existir, esta função LEVANTA com o nome do
    arquivo que falta. O silêncio seria pior — o defeito que esta rodada fecha é
    exatamente uma camada de acesso que parecia existir e não existia.

    O nome longo (`RepositorioDeSnapshotSupabase`) é o canônico lá, simétrico
    com a porta que ele satisfaz; o curto é um apelido de compatibilidade que a
    outra frente deixou para a troca não exigir um commit único. Tentamos o
    longo primeiro, e é ele que deve sobreviver.
    """
    try:
        from app.trafego import persistencia  # noqa: PLC0415
    except ImportError as exc:
        raise inv.PersistenciaAusente(
            "não há camada de acesso ao snapshot: `app/trafego/persistencia.py` "
            f"não está instalada. O schema canônico é {SCHEMA_CANONICO} e a "
            "porta que ela precisa satisfazer é "
            "`sincronizador.RepositorioDeSnapshot`."
        ) from exc

    classe = getattr(persistencia, "RepositorioDeSnapshotSupabase", None) \
        or getattr(persistencia, "RepositorioSupabase", None)
    if classe is None:
        raise inv.PersistenciaAusente(
            "`app/trafego/persistencia.py` existe mas não expõe "
            "`RepositorioDeSnapshotSupabase`."
        )
    return conferir_porta(classe(base, chave))
