"""O que o ANÚNCIO e a BUSCA sabem do leitor, levado à arquitetura do funil.

## O buraco que isto fecha (S2 · item 3, 30/09/2026)

O motor já lê `funnel_architecture.contexto_de_busca` (TermosDeBusca, três
estados) e `funnel_architecture.contexto_de_anuncio` (a RSA que traz o leitor à
LP, `presente | ausente`) — `adapters/briefing_volc.py` e `pipeline/inventario.py`.
Mas ninguém os escrevia: o disparo mandava a arquitetura do card como veio, e o
inventário de toda página dizia "o funnel_architecture não trouxe
contexto_de_busca". O que a campanha já tinha medido do leitor não chegava ao
briefing.

## Ausência explícita, nunca inventada

Cada contexto sai SEMPRE, e sempre num estado do contrato:

- sem campanha Search vinculada ao card → `ausente`, com o motivo;
- com campanha e sem leitor do Google Ads nem export → `ausente`, com o motivo;
- consulta que falhou → `ausente`, com a classe do erro (nunca a mensagem crua,
  que pode carregar credencial);
- consulta feita e nada colhido → `vazio_confirmado` (termos) ou `ausente`
  dizendo "nenhuma RSA ativa" (anúncio);
- export do integrador ilegível, ou sem nenhuma linha na janela → `ausente`
  (o arquivo não declara o período que cobre: não confirma vazio) e a API,
  quando há leitor, é a medição.

Nada aqui é lista vazia calada, e nada é inventado: os termos são os do
`search_term_view` (ou do export do integrador, com o sha256 do arquivo como
fonte) e os textos do anúncio são os títulos/descrições das RSAs ATIVAS da
campanha.

## Só leitura

GAQL só tem SELECT, e o leitor usado é o `_query` do
`ColetorGoogleInteligencia`, que recusa qualquer coisa que não comece por SELECT
e se recusa a nascer com a trava de escrita do Google Ads aberta.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

log = logging.getLogger("volc.redator.contexto")

#: A view do inventário de tráfego (uma linha por campanha, com o vínculo ao card).
VIEW_CAMPANHAS = "trafego_inventario_campanha"

#: Janela padrão dos termos: os 30 dias fechados antes de hoje.
DIAS_DA_JANELA = 30

#: Quanto o disparo espera pelo Google Ads antes de declarar ausência.
TIMEOUT_GOOGLE_S = 30.0

#: Pasta opcional com exports de `search_term_view` (`<campaign_id>.json`), o
#: formato que `carregar_termos_de_arquivo` lê. Tem precedência sobre a API.
ENV_PASTA_TERMOS = "VOLC_TERMOS_DE_BUSCA_DIR"

GAQL_RSA = """
  SELECT ad_group_ad.ad.id, ad_group_ad.status,
         ad_group_ad.ad.responsive_search_ad.headlines,
         ad_group_ad.ad.responsive_search_ad.descriptions
  FROM ad_group_ad
  WHERE campaign.id = {campaign_id}
    AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
    AND ad_group_ad.status != 'REMOVED'
"""

#: `(customer_id, gaql) -> linhas` — o formato de `MessageToDict`.
Consulta = Callable[[str, str], List[Dict[str, Any]]]


def busca_ausente(motivo: str) -> Dict[str, Any]:
    return {"estado": "ausente", "janela": None, "coletado_em": None, "fonte": None,
            "termos": [], "motivo_ausencia": motivo}


def anuncio_ausente(motivo: str) -> Dict[str, Any]:
    return {"estado": "ausente", "titulos": [], "descricoes": [], "fonte": "",
            "motivo_ausencia": motivo}


def _textos(ativos: Sequence[Any]) -> List[str]:
    """Os `text` dos assets, sem repetir e na ordem em que aparecem."""
    saida: List[str] = []
    for a in ativos or []:
        t = str((a or {}).get("text") or "").strip() if isinstance(a, dict) else ""
        if t and t not in saida:
            saida.append(t)
    return saida


def anuncio_de_linhas(linhas: Sequence[Dict[str, Any]], *, campaign_id: str) -> Dict[str, Any]:
    """Linhas GAQL de `ad_group_ad` (RSA) → `contexto_de_anuncio`.

    Só a RSA ATIVA (`ENABLED`) é o que o leitor vê. Pausada não traz ninguém à
    LP: contá-la como promessa do anúncio seria descrever um anúncio que não
    roda. Se só há pausadas, o contexto é `ausente` e diz quantas.
    """
    titulos: List[str] = []
    descricoes: List[str] = []
    pausadas = 0
    for linha in linhas or []:
        aga = (linha or {}).get("ad_group_ad") or {}
        if str(aga.get("status") or "").upper() != "ENABLED":
            pausadas += 1
            continue
        rsa = ((aga.get("ad") or {}).get("responsive_search_ad")) or {}
        for t in _textos(rsa.get("headlines")):
            if t not in titulos:
                titulos.append(t)
        for d in _textos(rsa.get("descriptions")):
            if d not in descricoes:
                descricoes.append(d)
    if not (titulos or descricoes):
        extra = f" ({pausadas} fora de veiculação)" if pausadas else ""
        return anuncio_ausente(f"a campanha {campaign_id} não tem RSA ativa{extra}")
    return {"estado": "presente", "titulos": titulos, "descricoes": descricoes,
            "fonte": f"google_ads:campaign/{campaign_id}:ad_group_ad(RSA ENABLED)",
            "motivo_ausencia": None}


def janela_padrao(hoje: Optional[date] = None):
    """Os `DIAS_DA_JANELA` dias fechados antes de hoje (hoje ainda está sendo medido)."""
    from volc_ads.inteligencia_google.modelo import JanelaDeTermos  # noqa: PLC0415

    hoje = hoje or date.today()
    fim = hoje - timedelta(days=1)
    return JanelaDeTermos(fim - timedelta(days=DIAS_DA_JANELA - 1), fim)


async def campanha_search_vinculada(supa: Any, opportunity_id: int) -> Dict[str, Any]:
    """A campanha Search PRESENTE vinculada a este card, ou o motivo de não haver.

    Devolve `{"campanha": {...}}` ou `{"motivo": "..."}`. Mais de uma é ambíguo:
    escolher uma seria decidir por conta própria qual anúncio fala com a LP.
    """
    try:
        linhas = await supa.select(VIEW_CAMPANHAS, {
            "select": "campaign_id,customer_id,canal,presenca,nome",
            "opportunity_id": f"eq.{int(opportunity_id)}",
        }) or []
    except Exception as exc:  # noqa: BLE001 — a leitura do vínculo não derruba o disparo
        return {"motivo": f"o vínculo campanha↔card não pôde ser lido ({type(exc).__name__})"}
    search = [l for l in linhas
              if str(l.get("canal") or "").upper() == "SEARCH"
              and str(l.get("presenca") or "").lower() == "presente"
              and str(l.get("campaign_id") or "").isdigit()]
    if not search:
        return {"motivo": "o card não tem campanha Search presente vinculada "
                          "(funil novo ou campanha removida)"}
    if len(search) > 1:
        ids = ", ".join(str(l["campaign_id"]) for l in search)
        return {"motivo": f"o card tem {len(search)} campanhas Search vinculadas ({ids}); "
                          f"escolher uma seria decidir qual anúncio fala com a LP"}
    return {"campanha": search[0]}


def _termos_de_arquivo(pasta: Optional[str], campaign_id: str, janela: Any):
    """O export do integrador, se houver um para esta campanha. `None` = não há."""
    if not pasta:
        return None
    arquivo = Path(pasta) / f"{campaign_id}.json"
    if not arquivo.is_file():
        return None
    from volc_ads.inteligencia_google.coletor import carregar_termos_de_arquivo  # noqa: PLC0415
    from volc_ads.inteligencia_google.modelo import termos_ausentes  # noqa: PLC0415

    try:
        termos = carregar_termos_de_arquivo(arquivo, janela=janela)
    except Exception as exc:  # noqa: BLE001 — linha fora do formato é ausência dita
        # Não só OSError/ValueError: uma linha com `search_term_view` em texto
        # levantava AttributeError DEPOIS do INSERT do run (S4, 30/09/2026).
        return termos_ausentes(
            f"export de termos {arquivo.name} ilegível ({type(exc).__name__})")
    if termos.estado == "vazio_confirmado":
        # O export não declara que período cobre. Zero linha NA janela de hoje
        # prova só que o arquivo não a cobre, não que a campanha não teve busca:
        # "consulta feita: 0 termos" seria ausência virando dado (S4).
        return termos_ausentes(
            f"o export {arquivo.name} não tem termos na janela {janela.rotulo()}")
    return termos


def _ler_google(consulta: Consulta, customer_id: str, campaign_id: str, janela: Any,
                agora: Optional[datetime]) -> Dict[str, Dict[str, Any]]:
    """Termos e RSA pela API, só leitura. Síncrono: roda numa thread."""
    from volc_ads.inteligencia_google.coletor import coletar_termos_de_busca  # noqa: PLC0415

    termos = coletar_termos_de_busca(consulta, customer_id, campaign_id, janela, agora=agora)
    cid = str(customer_id or "").replace("-", "").strip()
    try:
        linhas = list(consulta(cid, GAQL_RSA.format(campaign_id=campaign_id)))
        anuncio = anuncio_de_linhas(linhas, campaign_id=campaign_id)
    except Exception as exc:  # noqa: BLE001 — ausência dita, nunca silêncio
        anuncio = anuncio_ausente(
            f"a leitura das RSAs da campanha {campaign_id} falhou ({type(exc).__name__})")
    return {"busca": termos.para_json(), "anuncio": anuncio}


class _SemPersistencia:
    """O coletor exige uma persistência; o disparo só usa o `_query` (leitura)."""


def leitor_google_ads() -> Optional[Consulta]:
    """O `_query` de SOMENTE LEITURA do coletor, ou `None` se ele não nasce aqui
    (sem credencial, trava de escrita aberta, biblioteca ausente)."""
    try:
        from volc_ads.inteligencia_google.coletor import ColetorGoogleInteligencia  # noqa: PLC0415

        return ColetorGoogleInteligencia(persistencia=_SemPersistencia())._query  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        log.info("leitor do Google Ads indisponível no disparo: %s", type(exc).__name__)
        return None


async def contextos_do_funil(
    supa: Any, opportunity_id: int, *,
    fabricar_leitor: Optional[Callable[[], Optional[Consulta]]] = None,
    pasta_termos: Optional[str] = None,
    hoje: Optional[date] = None,
    agora: Optional[datetime] = None,
    timeout_s: float = TIMEOUT_GOOGLE_S,
) -> Dict[str, Dict[str, Any]]:
    """`{"contexto_de_busca": ..., "contexto_de_anuncio": ...}`, sempre os dois.

    O leitor do Google só é fabricado quando HÁ campanha vinculada: funil novo
    (o caso comum) não custa nenhuma chamada.

    ⚠️ NUNCA levanta. O disparo lê os contextos DEPOIS de gravar o run; uma
    exceção aqui virava 500 com a linha presa em `queued`, e o card passava a
    responder "Já existe uma execução na fila" (S4, 30/09/2026). Qualquer falha
    inesperada vira `ausente` com a CLASSE do erro, nunca a mensagem crua.
    """
    try:
        return await _contextos_do_funil(
            supa, opportunity_id, fabricar_leitor=fabricar_leitor,
            pasta_termos=pasta_termos, hoje=hoje, agora=agora, timeout_s=timeout_s)
    except Exception as exc:  # noqa: BLE001 — ausência dita, nunca disparo derrubado
        log.warning("contextos do funil indisponíveis no disparo: %s", type(exc).__name__)
        motivo = f"a leitura dos contextos do funil falhou ({type(exc).__name__})"
        return {"contexto_de_busca": busca_ausente(motivo),
                "contexto_de_anuncio": anuncio_ausente(motivo)}


async def _contextos_do_funil(
    supa: Any, opportunity_id: int, *,
    fabricar_leitor: Optional[Callable[[], Optional[Consulta]]],
    pasta_termos: Optional[str],
    hoje: Optional[date],
    agora: Optional[datetime],
    timeout_s: float,
) -> Dict[str, Dict[str, Any]]:
    vinculo = await campanha_search_vinculada(supa, opportunity_id)
    campanha = vinculo.get("campanha")
    if campanha is None:
        motivo = vinculo["motivo"]
        return {"contexto_de_busca": busca_ausente(motivo),
                "contexto_de_anuncio": anuncio_ausente(motivo)}

    campaign_id = str(campanha["campaign_id"])
    customer_id = str(campanha.get("customer_id") or "")
    janela = janela_padrao(hoje)
    pasta = pasta_termos if pasta_termos is not None else os.environ.get(ENV_PASTA_TERMOS)
    do_arquivo = _termos_de_arquivo(pasta, campaign_id, janela)

    # Resolvido AQUI, não na assinatura: o padrão é o leitor real, e quem troca
    # o módulo (teste, outro backend) precisa ser ouvido na hora da chamada.
    consulta = await asyncio.to_thread(fabricar_leitor or leitor_google_ads)
    if consulta is None:
        motivo = (f"a campanha {campaign_id} está vinculada, mas o leitor do Google Ads "
                  f"não está disponível neste backend")
        return {"contexto_de_busca": (do_arquivo.para_json() if do_arquivo is not None
                                      else busca_ausente(motivo)),
                "contexto_de_anuncio": anuncio_ausente(motivo)}
    try:
        lido = await asyncio.wait_for(
            asyncio.to_thread(_ler_google, consulta, customer_id, campaign_id, janela,
                              agora or datetime.now(timezone.utc)),
            timeout=timeout_s)
    except asyncio.TimeoutError:
        motivo = f"a leitura do Google Ads passou de {int(timeout_s)}s"
        lido = {"busca": busca_ausente(motivo), "anuncio": anuncio_ausente(motivo)}
    # O export só vence a API quando TRAZ termos; ilegível ou fora da janela, a
    # API (lida agora) é a medição.
    arquivo_vale = do_arquivo is not None and do_arquivo.estado == "presente"
    busca = do_arquivo.para_json() if arquivo_vale else lido["busca"]
    return {"contexto_de_busca": busca, "contexto_de_anuncio": lido["anuncio"]}


def anexar_contextos(arquitetura: Dict[str, Any],
                     contextos: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Uma CÓPIA da arquitetura com os dois contextos.

    O que foi colhido AGORA com dado (`presente`/`vazio_confirmado`) vence. Se a
    coleta de agora é `ausente` e o card já trazia um contexto, o do card fica —
    a ausência de hoje não apaga uma medição de ontem. Sem nada no card, vai a
    ausência com o motivo.
    """
    saida = dict(arquitetura or {})
    for chave in ("contexto_de_busca", "contexto_de_anuncio"):
        novo = (contextos or {}).get(chave)
        if not isinstance(novo, dict):
            continue
        do_card = saida.get(chave)
        if novo.get("estado") == "ausente" and isinstance(do_card, dict) and do_card:
            continue
        saida[chave] = novo
    return saida
