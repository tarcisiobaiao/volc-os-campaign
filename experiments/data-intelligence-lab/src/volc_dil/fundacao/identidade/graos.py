"""Matriz de grão honesto entre fontes, como dado — e a recusa tipada de grão mais fino.

Cada célula diz a confiança HOJE (pelo código lido em cada ref; ver
`docs/data-intelligence/fundacao-20261016/03-MATRIZ-DE-ATRIBUICAO.md`) e a confiança
POTENCIAL se a condição em `requer` for cumprida. Pedir um grão cuja confiança hoje é
`nao_atribuivel` (ou que nem está na matriz) levanta `GraoNaoSuportado` — nunca devolve
um número rateado.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Iterable, Optional


class Confianca(str, enum.Enum):
    DETERMINISTICA = "deterministica"  # mesma chave dos dois lados, sem inferência
    PROBABILISTICA = "probabilistica"  # chave aproximada (texto, URL normalizada, semântica diferente)
    NAO_ATRIBUIVEL = "nao_atribuivel"  # não há chave; qualquer número seria rateio


class Fonte(str, enum.Enum):
    GOOGLE_ADS = "google_ads"
    SENSOR = "sensor_raw_events"  # GTM v35 → VOLC Sensor v3 → volc-ingest → raw_events
    FUNIL = "funil"  # campaign_funnel_urls / trafego_vinculo / pautador_funnel_runs
    JOINADS = "joinads"
    GAM = "gam"
    ADSENSE = "adsense"


class Grao(str, enum.Enum):
    CONTA = "conta"
    CAMPANHA = "campanha"
    CAMPANHA_PAIS = "campanha_pais"
    GRUPO_ANUNCIO = "grupo_anuncio"
    ANUNCIO = "anuncio"
    KEYWORD = "keyword"
    TERMO_BUSCA = "termo_busca"
    LANDING = "landing"
    POST_WP = "post_wp"
    SESSAO = "sessao"
    CLIQUE = "clique"
    DISPOSITIVO = "dispositivo"


class GraoTempo(str, enum.Enum):
    DIA = "dia"
    HORA = "hora"


@dataclass(frozen=True)
class Capacidade:
    fontes: frozenset
    grao: Grao
    tempo: GraoTempo
    hoje: Confianca
    potencial: Confianca
    chave: str
    requer: str = ""
    prova: str = ""


class GraoNaoSuportado(Exception):
    """Pedido de junção num grão que as fontes não sustentam. Carrega o grão honesto disponível."""

    def __init__(self, fontes: Iterable[Fonte], grao: Grao, tempo: GraoTempo, motivo: str,
                 suportados: Iterable[tuple[Grao, GraoTempo, Confianca]] = ()):
        self.fontes = tuple(sorted(f.value for f in fontes))
        self.grao = grao
        self.tempo = tempo
        self.motivo = motivo
        self.suportados = tuple(suportados)
        sup = ", ".join(f"{g.value}×{t.value} ({c.value})" for g, t, c in self.suportados) or "nenhum"
        super().__init__(
            f"grão {grao.value}×{tempo.value} não suportado entre {' × '.join(self.fontes)}: "
            f"{motivo}. Grão honesto disponível hoje: {sup}"
        )


def _c(a: Fonte, b: Fonte, grao: Grao, tempo: GraoTempo, hoje: Confianca, potencial: Confianca,
       chave: str, requer: str = "", prova: str = "") -> Capacidade:
    return Capacidade(frozenset({a, b}), grao, tempo, hoje, potencial, chave, requer, prova)


D, P, N = Confianca.DETERMINISTICA, Confianca.PROBABILISTICA, Confianca.NAO_ATRIBUIVEL
G, S, F, J, GAM, ADS = (Fonte.GOOGLE_ADS, Fonte.SENSOR, Fonte.FUNIL, Fonte.JOINADS, Fonte.GAM,
                        Fonte.ADSENSE)
DIA, HORA = GraoTempo.DIA, GraoTempo.HORA

MATRIZ: tuple[Capacidade, ...] = (
    # Google Ads × JoinAds — a única junção econômica viva.
    _c(G, J, Grao.CAMPANHA, DIA, D, D, "campaign.id = custom_value (custom_key=utm_campaign)",
       prova="template utm_campaign={campaignid}; JoinAds 20/20 = id (identity-gap-matrix@043c77f5)"),
    _c(G, J, Grao.CONTA, DIA, D, D, "roll-up das linhas campanha×dia (receita sem chave fica fora)"),
    _c(G, J, Grao.CAMPANHA_PAIS, DIA, P, P, "campanha + geoTargetConstant × país JoinAds",
       requer="mapa geoTarget→ISO; semânticas diferentes (local físico/interesse × geo da requisição)"),
    _c(G, J, Grao.GRUPO_ANUNCIO, DIA, N, D, "{adgroupid} em utm_content ↔ custom_key=utm_content",
       requer="coletar custom_key=utm_content na JoinAds e provar que o key-value chega íntegro"),
    _c(G, J, Grao.KEYWORD, DIA, N, P, "{keyword} texto", requer="JoinAds não tem custom_key utm_term"),
    _c(G, J, Grao.LANDING, DIA, P, P, "url final normalizada ↔ land_uri",
       requer="formato de land_uri verificado; não cruza com campanha (1 custom_key por chamada)"),
    _c(G, J, Grao.SESSAO, DIA, N, N, "nenhuma", prova="receita JoinAds é agregada por dia × chave"),
    _c(G, J, Grao.CLIQUE, DIA, N, N, "nenhuma", prova="JoinAds não expõe click id; API só agregados"),
    _c(G, J, Grao.CAMPANHA, HORA, N, N, "nenhuma", requer="JoinAds sem receita horária demonstrada"),
    # Google Ads × Sensor (tráfego).
    _c(G, S, Grao.CAMPANHA, DIA, N, D, "campaign.id = payload.utm.campaign",
       requer="sensor parar de descartar id numérico (regex de telefone, sensor:73,107-112)",
       prova="vetor-ouro: utmValue('24278665189') == ''"),
    _c(G, S, Grao.GRUPO_ANUNCIO, DIA, N, D, "{adgroupid} = payload.utm.content",
       requer="mesma correção do sensor (ad_group.id também tem >= 10 dígitos)"),
    _c(G, S, Grao.KEYWORD, DIA, P, P, "keyword_texto ↔ payload.utm.term (texto normalizado ≤40)",
       requer="colide entre grupos e tipos de correspondência; não é criterion_id"),
    _c(G, S, Grao.LANDING, DIA, D, D, "host sem www + path sem barra final",
       prova="journey-contract page_identity; cliques Ads ≠ sessões (consentimento/bot/aba)"),
    _c(G, S, Grao.TERMO_BUSCA, DIA, N, N, "nenhuma", prova="termo real não vai para a URL"),
    _c(G, S, Grao.SESSAO, DIA, N, P, "nenhuma", requer="click id persistido (gclid) — decisão de privacidade"),
    _c(G, S, Grao.CLIQUE, DIA, N, D, "gclid", requer="sensor enviar o valor do gclid (hoje só paid=1)"),
    _c(G, S, Grao.DISPOSITIVO, DIA, N, P, "device Ads ↔ viewport", requer="viewport não é device"),
    _c(G, S, Grao.CAMPANHA, HORA, N, D, "campanha × hora", requer="campanha na sessão (ver campanha×dia)"),
    # Sensor × JoinAds.
    _c(S, J, Grao.CAMPANHA, DIA, N, D, "payload.utm.campaign = custom_value", requer="correção do sensor"),
    _c(S, J, Grao.LANDING, DIA, P, P, "path ↔ land_uri", requer="formato de land_uri verificado"),
    _c(S, J, Grao.SESSAO, DIA, N, N, "nenhuma", requer="chave compartilhada impressão↔sessão"),
    # Funil.
    _c(G, F, Grao.CAMPANHA, DIA, N, D, "vínculo declarado datado (trafego_vinculo)",
       requer="vínculo da campanha atual (campaign_funnel_urls 0/17 para 24278665189)"),
    _c(S, F, Grao.LANDING, DIA, D, D, "path ∈ páginas declaradas do funil"),
    _c(S, F, Grao.POST_WP, DIA, P, D, "path → post_id declarado", requer="tabela funil→url→post"),
    _c(J, F, Grao.POST_WP, DIA, D, D, "id_post_wp = paginas_publicadas[].id",
       prova="JoinAds v2 coleta key_value_post (wip/historico-joinads-20261015)"),
    _c(J, F, Grao.LANDING, DIA, P, P, "land_uri ↔ url_wp"),
    # GAM / AdSense — capacidade existe, dado não.
    _c(G, GAM, Grao.CAMPANHA, DIA, N, D, "campaign.id = gam_metrics.utm_campaign_value",
       requer="gam_metrics com linhas (0 no snapshot)"),
    _c(G, ADS, Grao.LANDING, DIA, N, P, "url ↔ adsense_metrics.url", requer="AdSense ativo (suspenso desde fev/2026)"),
)

_INDICE = {(c.fontes, c.grao, c.tempo): c for c in MATRIZ}


def capacidade(a: Fonte, b: Fonte, grao: Grao, tempo: GraoTempo = GraoTempo.DIA) -> Optional[Capacidade]:
    return _INDICE.get((frozenset({a, b}), grao, tempo))


def suportados_hoje(a: Fonte, b: Fonte) -> list[tuple[Grao, GraoTempo, Confianca]]:
    par = frozenset({a, b})
    return [(c.grao, c.tempo, c.hoje) for c in MATRIZ if c.fontes == par and c.hoje is not Confianca.NAO_ATRIBUIVEL]


def exigir_grao(a: Fonte, b: Fonte, grao: Grao, tempo: GraoTempo = GraoTempo.DIA) -> Capacidade:
    """Devolve a capacidade se o grão é sustentado hoje; senão levanta `GraoNaoSuportado`."""
    c = capacidade(a, b, grao, tempo)
    if c is None:
        raise GraoNaoSuportado((a, b), grao, tempo, "nenhuma chave conhecida neste grão",
                               suportados_hoje(a, b))
    if c.hoje is Confianca.NAO_ATRIBUIVEL:
        motivo = f"sem chave hoje ({c.chave})" + (f"; requer: {c.requer}" if c.requer else "")
        raise GraoNaoSuportado((a, b), grao, tempo, motivo, suportados_hoje(a, b))
    return c


def receita_por_sessao(*_args, **_kwargs):
    """Sempre recusa: nenhuma fonte de receita (JoinAds/GAM/AdSense) entrega grão de sessão."""
    raise GraoNaoSuportado((Fonte.JOINADS, Fonte.SENSOR), Grao.SESSAO, GraoTempo.DIA,
                           "receita é agregada por dia × chave; distribuí-la por sessão é rateio",
                           suportados_hoje(Fonte.JOINADS, Fonte.SENSOR))
