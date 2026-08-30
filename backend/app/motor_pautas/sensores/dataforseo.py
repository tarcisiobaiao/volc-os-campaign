"""DataForSEO — o sensor que transforma eixo declarado em eixo medido.

## O que isto resolve

O motor tem dez eixos. Quatro deles — `volume`, `spread`, `vacuo` e
`reposicao` — vinham de **declaração de agente**, e são justamente os quatro
onde palpite é mais perigoso, porque parecem objetivos. Um agente que declara
`volume: massivo` soa tão confiante quanto um que mediu.

Estes endpoints medem os quatro. E o `spread` ganha a correção que uma revisão
externa exigiu: CPC **da keyword naquele país**, não média nacional — média de
país dilui o nicho no run-of-network, e foi provavelmente por isso que o teste
do spread estimado deu Pearson −0,266.

## Custo, porque "sempre on" só existe se for barato

    Labs (ideas, related, intent, difficulty)   $0,012/chamada + $0,00012/item
    Google Ads volume + CPC                     $0,06/tarefa, até 1000 keywords
                                                → $0,00006 por keyword
    SERP orgânico                               $0,0006 fila · $0,002 live
    Histórico (700 kw/chamada, desde 2021)      preço de Labs

Um ciclo diário com 1.000 keywords medidas, 50 SERPs e 20 buscas no News custa
cerca de **$0,25**. O custo não é a restrição; a disciplina de só medir o que
mudou é — e é ela que o grafo já impõe.

## O que este módulo NÃO faz

Não decide nada. Ele traduz resposta de API em nível de eixo, e a tradução é
função pura, testável sem rede. O cliente HTTP é fino de propósito: quem
depende de rede é a borda, não a lógica.

⚠️ As funções de rede aqui **não foram exercitadas contra a API real** — não há
credencial neste ambiente. Os mapeadores foram testados com respostas de
exemplo montadas a partir da documentação. Trate a primeira execução real como
parte da validação, não como rotina.
"""

from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass

BASE = "https://api.dataforseo.com/v3"

# Endpoints que interessam. Fila padrão onde dá, porque o sentinela é diário e
# não tem pressa — live custa 3x mais para ganhar segundos que ninguém espera.
EP = {
    # ── os quatro que a coluna "Em validação" usa ───────────────────────────
    # Cluster (não a string exata) → volume e reposição → SERP → audiência.
    "sugestoes":    "/dataforseo_labs/google/keyword_suggestions/live",
    "historico_volume": "/dataforseo_labs/google/historical_search_volume/live",
    "serp":         "/serp/google/organic/live/advanced",
    "trafego_dominio": "/dataforseo_labs/google/bulk_traffic_estimation/live",

    # medição
    "volume_cpc":   "/keywords_data/google_ads/search_volume/live",
    "historico":    "/dataforseo_labs/google/historical_keyword_data/live",
    "intent":       "/dataforseo_labs/google/search_intent/live",
    "dificuldade":  "/dataforseo_labs/google/bulk_keyword_difficulty/live",
    # descoberta
    "ideias":       "/dataforseo_labs/google/keyword_ideas/live",
    "relacionadas": "/dataforseo_labs/google/related_keywords/live",
    # competição
    "concorrentes": "/dataforseo_labs/google/serp_competitors/live",
    # pulso
    "news":         "/serp/google/news/live/advanced",
    "trends":       "/keywords_data/google_trends/explore/live",
    "top_buscas":   "/dataforseo_labs/google/top_searches/live",
    # finalistas — US$ 0,09 FLAT por tarefa. NÃO entram na validação: são dois
    # dos nós que concentram 78% da fatura e só devem tocar quem sobreviveu.
    "trafego_por_lance": "/keywords_data/google_ads/ad_traffic_by_keywords/live",
}

# Endpoints DESCARTADOS por medição — ficam nomeados para ninguém os
# reintroduzir por parecerem óbvios:
#   keyword_ideas        expande CATEGORIA, não frase. De `saque aniversario
#                        fgts` o topo por volume é `calculadora` (7,48M).
#                        Firehose de descoberta, jamais medida da semente.
#   bulk_keyword_difficulty  `null` em 50% da cauda longa — cego no único
#                        regime que interessa.
#   search_intent        o rótulo já vem de graça dentro de `keyword_suggestions`.
#   serp .../live/regular  NÃO é mais barato (US$ 0,0035, igual ao advanced) e
#                        devolve 9 campos por orgânico contra 34.


class SemCredencial(RuntimeError):
    pass


@dataclass
class Cliente:
    login: str | None = None
    senha: str | None = None
    timeout: int = 60

    def __post_init__(self):
        self.login = self.login or os.getenv("DATAFORSEO_LOGIN")
        # `DATAFORSEO_PASSWORD` é o nome que `app.config.Settings` já usa;
        # `DATAFORSEO_SENHA` é o nome antigo deste módulo. Aceitar os dois evita
        # que o sensor fique mudo por divergência de grafia entre camadas.
        self.senha = self.senha or os.getenv("DATAFORSEO_PASSWORD") or os.getenv("DATAFORSEO_SENHA")

    def _auth(self) -> str:
        if not (self.login and self.senha):
            raise SemCredencial(
                "faltam DATAFORSEO_LOGIN e DATAFORSEO_SENHA no ambiente. "
                "Sem elas o módulo continua útil offline — os mapeadores são "
                "funções puras e rodam sobre resposta já baixada.")
        cru = f"{self.login}:{self.senha}".encode()
        return "Basic " + base64.b64encode(cru).decode()

    def chamar(self, endpoint: str, tarefas: list[dict]) -> dict:
        """POST cru. `tarefas` é sempre uma lista, mesmo com um item só."""
        req = urllib.request.Request(
            BASE + EP.get(endpoint, endpoint),
            data=json.dumps(tarefas).encode(),
            headers={"Authorization": self._auth(),
                     "Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            corpo = e.read().decode(errors="replace")[:400]
            raise RuntimeError(f"DataForSEO {e.code} em {endpoint}: {corpo}") from e


def sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ═══════════════════════════════════════════════════════════════════════════
# MAPEADORES — resposta da API → nível de eixo. Funções puras, sem rede.
# ═══════════════════════════════════════════════════════════════════════════

def nivel_volume(busca_mensal: int | None) -> str | None:
    """Volume mensal → faixa do eixo.

    Faixas, não número, mesmo tendo o número: a decisão que o operador toma com
    12.000 buscas é a mesma que ele toma com 15.000, e fingir precisão onde ela
    não muda nada é ruído com cara de rigor.
    """
    if busca_mensal is None:
        return None
    if busca_mensal >= 100_000:
        return "massivo"
    if busca_mensal >= 10_000:
        return "alto"
    if busca_mensal >= 1_000:
        return "medio"
    if busca_mensal >= 100:
        return "baixo"
    return "residual"


# Teto de sanidade para receita por SESSÃO. Cinco dólares numa única sessão
# seria extraordinário em qualquer nicho; RPM de GAM (receita por mil) passa
# disso rotineiramente. É o que separa o valor certo do erro de fator mil.
_TETO_RECEITA_SESSAO_USD = 5.0


def nivel_spread(cpc_usd: float | None,
                 receita_por_sessao_usd: float | None) -> str | None:
    """Receita por SESSÃO ÷ CPC do clique → faixa do eixo.

    ⚠️ O SEGUNDO ARGUMENTO NÃO É RPM. Ele se chamava `rpm_usd`, e uma revisão
    externa apontou a armadilha: RPM, por convenção, é receita por MIL — o
    número que o GAM mostra. Quem ligasse o RPM do Ad Manager aqui produziria
    um spread **mil vezes maior** e todo tema pareceria excelente. O nome
    convidava ao erro que a conta não comete.

    A unidade certa é receita por sessão, comparável ao custo de UM clique. Se
    você só tem RPM do GAM, converta antes:

        receita_por_sessao = (RPM / 1000) * pageviews_por_sessao

    **Esta função é a correção de um erro anterior.** Antes eu usava spread
    médio do país, e testando contra cinco mercados medidos deu Pearson −0,266:
    não previu nada. (Ressalva honesta: n=5, então o número não prova o
    redesenho — o que sustenta é o mecanismo. Média nacional mistura o RPM de
    uma página de crédito imobiliário com o de uma página de multa de trânsito.)

    Aqui o CPC vem da keyword específica naquele país, e a receita vem do SEU
    Ad Manager para aquele arquétipo.
    """
    if not cpc_usd or not receita_por_sessao_usd or cpc_usd <= 0:
        return None
    if receita_por_sessao_usd > _TETO_RECEITA_SESSAO_USD:
        raise ValueError(
            f"receita_por_sessao_usd={receita_por_sessao_usd} é alta demais para "
            f"UMA sessão. Quase certamente é RPM (receita por MIL) do GAM. "
            f"Converta: (RPM / 1000) * pageviews_por_sessao.")
    r = receita_por_sessao_usd / cpc_usd
    if r >= 2.0:
        return "excelente"
    if r >= 1.4:
        return "bom"
    # ⚠️ O CORTE É 1,0, NÃO 0,9.
    #
    # A faixa antiga chamava 0,90 a 1,40 de `neutro` — ou seja, razões de 0,90
    # a 0,99 saíam com valor 0,50 na escala, no meio, sem disparar portão. Mas
    # razão abaixo de 1 é prejuízo ANTES de imposto, produção e tráfego
    # inválido: o clique já custou mais do que a sessão rendeu.
    #
    # 0,9 era política de tolerância, e foi apresentada como aritmética. A
    # aritmética é 1,0.
    if r >= 1.0:
        return "neutro"
    return "ruim"


# Rótulos de domínio de governo, em vários países. Comparados por COMPONENTE,
# não por substring: `".gov" in "gov.br"` é False — falta o ponto inicial —, e
# esse detalhe fazia todo domínio oficial brasileiro nu escapar da detecção.
# Um teste pegou; o bug teria inflado silenciosamente o `vacuo` de todo tema BR.
_ROTULOS_OFICIAIS = {"gov", "gob", "gouv", "govt", "go", "gc", "admin"}


def _e_oficial(dominio: str) -> bool:
    return any(p in _ROTULOS_OFICIAIS for p in dominio.lower().split("."))


def nivel_vacuo(serp: dict, *, dominios_grandes: set[str] | None = None) -> str | None:
    """SERP orgânico → quanta gente já explicou bem.

    Deixa de ser opinião do agente. O sinal é quantos dos dez primeiros são
    portais estabelecidos e quantos são a fonte oficial: SERP tomado por um
    `.gov` e nada mais é oportunidade; SERP com cinco portais grandes é commodity.
    """
    itens = [i for i in (serp.get("items") or []) if i.get("type") == "organic"]
    if not itens:
        return None
    grandes = dominios_grandes or set()
    top = itens[:10]
    n_grandes = sum(1 for i in top if any(d in (i.get("domain") or "") for d in grandes))
    n_oficial = sum(1 for i in top if _e_oficial(i.get("domain") or ""))
    n_portal = len(top) - n_oficial

    if n_portal <= 1:
        return "virgem"
    if n_grandes == 0 and n_portal <= 4:
        return "raso"
    if n_grandes <= 2:
        return "disputado"
    return "saturado"


def nivel_reposicao(monthly_searches: list[dict] | None) -> tuple[str | None, dict]:
    """Série mensal → o eixo de reposição, medido em vez de declarado.

    A forma da curva diz o que a declaração só supunha:

      plana e alta          gente nova entrando o tempo todo  → continua
      um pico anual         uma coorte por ano                → anual
      picos mensais         os mesmos voltando                → mesma_gente
      pico único e queda    aconteceu e acabou                → unica

    Devolve também a evidência, porque um eixo medido sem a série que o
    sustenta volta a ser declaração na primeira vez que alguém duvidar.
    """
    # ⚠️ DOIS CICLOS, NÃO SEIS MESES. O mínimo era 6 e estava errado: com um
    # ciclo só é impossível separar sazonalidade de tendência. A mesma série de
    # 12 meses com um pico anual sai `anual` ou `unica` conforme o mês em que a
    # janela corta — o teste antigo passava por acidente de fase, não por
    # acerto. Entidade com menos de dois anos de série não tem reposição
    # medível; o eixo fica ausente e o motivo vai gravado.
    if not monthly_searches or len(monthly_searches) < 24:
        return None, {}
    v = [float(m.get("search_volume") or 0) for m in monthly_searches]
    if not any(v):
        return None, {}

    media = sum(v) / len(v)
    if media <= 0:
        return None, {}
    pico = max(v)
    vale = min(v)
    amplitude = (pico - vale) / media

    # ⚠️ TENDÊNCIA POR ANO CHEIO, NUNCA POR TRÊS MESES.
    #
    # A versão anterior comparava a média dos 3 últimos meses com a dos 3
    # primeiros. Em série sazonal isso mede a FASE do corte, não a tendência:
    # com a MESMA série anual sintética, só mudando o mês em que a janela
    # termina, o eixo saiu
    #
    #     termina em dezembro (logo após o pico) -> tendencia -2,08 -> `unica`
    #     termina em junho                       -> tendencia  0,00 -> `anual`
    #     termina em março (logo antes do pico)  -> tendencia +2,08 -> `anual`
    #
    # E como a janela é fixa em 48 meses terminando SEMPRE no mês corrente, o
    # mesmo tema medido em janeiro e em julho receberia níveis diferentes —
    # sem nada ter mudado no mundo. Comparar blocos de 12 meses é invariante à
    # fase por construção: cada bloco cobre um ciclo sazonal inteiro.
    # O bloco final contra o bloco INICIAL da janela — não contra o anterior.
    # Comparar com o ano anterior só enxerga queda no último ciclo: um tema que
    # colapsou no meio da janela e ficou baixo tem dois blocos finais iguais e
    # sairia como estável.
    primeiro, ultimo = sum(v[:12]), sum(v[-12:])
    tendencia = ((ultimo - primeiro) / primeiro) if primeiro else 0.0

    # ⚠️ PICO POR ANO, NUNCA PICO ABSOLUTO. Este limiar já esteve errado.
    #
    # A regra original era `n_picos >= 4 -> mesma_gente`, escrita quando a série
    # vinha inteira (92 meses típicos). Ao fixar a janela em 48 meses, "4 picos"
    # passou a significar exatamente "um por ano" — que é a definição de coorte
    # ANUAL, o oposto do que a regra queria dizer.
    #
    # Medido no IPVA: picos em 2023-01, 2024-01, 2025-01, 2025-02, 2026-01,
    # 2026-02. Seis picos, todos em janeiro/fevereiro, 1,50 por ano — a coorte
    # anual mais limpa que existe no país saía como "os mesmos voltando".
    #
    # Um limiar absoluto só é interpretável se a janela for fixa E conhecida;
    # normalizar por ano torna a regra independente da janela, que é o que ela
    # sempre quis dizer.
    n_picos = sum(1 for x in v if x > media * 1.4)
    anos = max(1e-9, len(v) / 12)
    picos_por_ano = n_picos / anos

    prova = {"media": round(media), "amplitude": round(amplitude, 2),
             "tendencia": round(tendencia, 2), "meses": len(v),
             "picos": n_picos, "picos_por_ano": round(picos_por_ano, 2)}

    # queda forte e sustentada: o tema está morrendo, não é perene
    if tendencia < -0.6:
        return "unica", prova
    if amplitude < 0.5:
        return "continua", prova
    # Três ou mais picos por ano é gente voltando (trimestral ou mais denso);
    # um ou dois é uma coorte por ano, com o pico podendo cobrir dois meses.
    if picos_por_ano >= 3.0:
        return "mesma_gente", prova
    return "anual", prova


# Intenção do DataForSEO → o que ela diz sobre o nosso eixo de ignorância.
# NÃO é tradução: `informational` cobre desde "não sei se existe" até "só falta
# a data". Serve como VERIFICAÇÃO CRUZADA — se o agente declarou ignorância
# alta e a API diz `transactional`, alguém está errado e vale olhar.
_INTENT_COMPATIVEL = {
    "informational": {"nao_sei_se_existe", "nao_sei_se_sirvo",
                      "nao_sei_por_que_falhou", "so_falta_um_dado"},
    "navigational":  {"sei_o_que_fazer", "so_falta_um_dado"},
    "commercial":    {"nao_sei_se_sirvo", "nao_preciso_de_nada"},
    "transactional": {"sei_o_que_fazer"},
}


def conflito_de_intencao(intent_api: str | None, ignorancia_declarada: str | None
                         ) -> str | None:
    """Confronta a intenção medida com a ignorância declarada.

    Devolve a mensagem do conflito, ou None quando batem. Não corrige nada —
    sobrescrever a declaração com a API seria trocar um julgamento por outro
    sem saber qual está certo. Levanta a mão, e quem decide é quem lê.
    """
    if not intent_api or not ignorancia_declarada:
        return None
    ok = _INTENT_COMPATIVEL.get(intent_api.lower())
    if ok is None or ignorancia_declarada in ok:
        return None
    return (f"intenção medida «{intent_api}» não bate com ignorância declarada "
            f"«{ignorancia_declarada}» — um dos dois está errado")


# ═══════════════════════════════════════════════════════════════════════════
# MONTAGEM DE TAREFA — o formato que a API espera
# ═══════════════════════════════════════════════════════════════════════════

def tarefa_volume(keywords: list[str], *, location_code: int,
                  language_code: str) -> list[dict]:
    """Até 1000 keywords por tarefa, $0,06 a tarefa. Encha a tarefa."""
    return [{"keywords": keywords[:1000], "location_code": location_code,
             "language_code": language_code, "search_partners": False}]


def tarefa_historico(keywords: list[str], *, location_code: int,
                     language_code: str) -> list[dict]:
    """Até 700 keywords. Histórico mensal desde agosto de 2021."""
    return [{"keywords": keywords[:700], "location_code": location_code,
             "language_code": language_code}]


def tarefa_ideias(seeds: list[str], *, location_code: int, language_code: str,
                  limite: int = 200) -> list[dict]:
    return [{"keywords": seeds[:20], "location_code": location_code,
             "language_code": language_code, "limit": limite,
             "include_serp_info": False}]


def tarefa_serp(keyword: str, *, location_code: int, language_code: str,
                profundidade: int = 10) -> list[dict]:
    """⚠️ `depth` NUNCA implícito. O default da API é 100 e custa US$ 0,0155;
    com 10 cai para US$ 0,0020 — 7,75x — e ainda devolve 9 orgânicos, o AI
    Overview e o PAA completos. Esquecer o parâmetro multiplica a fatura."""
    return [{"keyword": keyword, "location_code": location_code,
             "language_code": language_code, "depth": profundidade}]


def tarefa_sugestoes(semente: str, *, location_code: int, language_code: str,
                     limite: int = 60, so_com_volume: bool = True) -> list[dict]:
    """Expande a SEMENTE em cluster. `filters` corta a CONTA, não só o ruído.

    O filtro é aplicado no servidor ANTES de cobrar: 663 sugestões brutas caem
    para 193 com `search_volume > 0`, e a fatura vai de US$ 0,0916 para
    US$ 0,03516. Filtrar depois de receber paga o preço inteiro.

    `keyword_suggestions` e não `keyword_ideas`: o primeiro expande a FRASE, o
    segundo expande a CATEGORIA e devolve `calculadora` para uma semente de FGTS.
    """
    tarefa: dict = {
        "keyword": semente,
        "location_code": location_code,
        "language_code": language_code,
        "limit": limite,
        "include_serp_info": False,
        "include_seed_keyword": True,
        # ORDENADO POR VOLUME: sem isto, cortar o limite corta linhas
        # arbitrárias e a soma do cluster vira amostra. Medido no mesmo termo,
        # 150 linhas somam 146.560 e as 60 de maior volume somam 142.260 — a
        # cauda inteira vale 2,9% da massa. Cabeça para MEDIR.
        #
        # A cauda não se perde: é onde vive a forma da pergunta escrita pelo
        # usuário, e ela é insumo do `psique.py` e do gerador de copy. Vem de
        # `related_keywords` com depth=3, na MINERAÇÃO — outro nó, outra coluna.
        "order_by": ["keyword_info.search_volume,desc"],
    }
    if so_com_volume:
        tarefa["filters"] = [["keyword_info.search_volume", ">", 0]]
    return [tarefa]


def tarefa_historico_volume(keywords: list[str], *, location_code: int,
                            language_code: str) -> list[dict]:
    """Série mensal do cluster. Lotável — e é o lote que torna isto barato.

    A base de US$ 0,012 por chamada domina na cauda curta: 20 clusters numa
    chamada custam quase o mesmo que um. Por isso o botão de coluna é o caminho
    padrão e o arrasto de card avulso é a exceção cara.
    """
    return [{"keywords": keywords[:700], "location_code": location_code,
             "language_code": language_code}]


def tarefa_trafego(alvos: list[str], *, location_code: int,
                   language_code: str) -> list[dict]:
    """Audiência orgânica dos domínios. Até 1.000 alvos por chamada.

    20 cards x 10 domínios = 200 alvos = US$ 0,036 pela coluna inteira. É o que
    separa portal de verdade de casca: `direito2.com.br` tem ETV 23.549 sobre
    898 keywords, `creditoup.com.br` tem 7,2 sobre 10. Quatro ordens de
    grandeza, e os dois ocupam a mesma linha na SERP.
    """
    return [{"targets": alvos[:1000], "location_code": location_code,
             "language_code": language_code, "item_types": ["organic"]}]


def tarefa_news(keyword: str, *, location_code: int, language_code: str,
                profundidade: int = 20) -> list[dict]:
    """O pulso do lado esquerdo: o que apareceu sobre a entidade nos últimos dias."""
    return [{"keyword": keyword, "location_code": location_code,
             "language_code": language_code, "depth": profundidade}]


# ═══════════════════════════════════════════════════════════════════════════
# EXTRAÇÃO — navegar o envelope da API sem espalhar `[0]["result"][0]` pelo código
# ═══════════════════════════════════════════════════════════════════════════

def itens(resposta: dict) -> list[dict]:
    """Puxa os itens de qualquer resposta, tolerando envelope vazio.

    A API embrulha em tasks[].result[].items[], e cada nível pode vir nulo. Um
    `KeyError` aqui derruba o cron por um dia sem resultado, que é o caso mais
    comum e o menos merecedor de crash.
    """
    out: list[dict] = []
    for t in (resposta.get("tasks") or []):
        if t.get("status_code") not in (20000, None):
            continue
        for r in (t.get("result") or []):
            if isinstance(r, dict):
                out += (r.get("items") or [r])
    return out


def custo(resposta: dict) -> float:
    """Custo REAL desta chamada, somado de `tasks[].cost`.

    ⚠️ Não use o `cost` do envelope nem um contador em arquivo. Um contador
    compartilhado entre processos paralelos reportou de 8x a 25x o consumo
    próprio de cada sonda — o número tem que vir da própria resposta, chamada a
    chamada, dentro do processo que a fez.
    """
    tarefas = resposta.get("tasks") or []
    soma = sum(float(t.get("cost") or 0.0) for t in tarefas if isinstance(t, dict))
    return soma if soma else float(resposta.get("cost") or 0.0)


# ═══════════════════════════════════════════════════════════════════════════
# MEDIDO EM 14/08/2026 — o que a fatura corrigiu na documentação
# Ver `volc_ads/DATAFORSEO-MEDIDO.md`. As funções abaixo existem porque as
# premissas do topo deste arquivo foram testadas contra 96 chamadas reais.
# ═══════════════════════════════════════════════════════════════════════════

# Custo = base + por linha, verificado exato em 5 endpoints Labs diferentes.
CUSTO_BASE_LABS = 0.012
CUSTO_POR_LINHA_LABS = 0.00012
# `keywords_data/google_ads/*` cobra FLAT por tarefa, de 1 a 1000 keywords.
CUSTO_TAREFA_GOOGLE_ADS = 0.09
# SERP com `depth=10`. O default é 100 e custa 7,75x mais pelos mesmos 9
# orgânicos úteis, AI Overview e PAA completos.
CUSTO_SERP_DEPTH_10 = 0.0020


def custo_previsto_labs(linhas: int) -> float:
    """A conta fechada: base + por linha. A BASE DOMINA NA CAUDA CURTA.

    Pedir 10 linhas custa quase o mesmo que pedir 100 — e é por isso que o lote
    é o caminho padrão e o card avulso é a exceção. Validar 20 cards um a um
    paga a base 20 vezes; validar em lote paga uma.
    """
    return CUSTO_BASE_LABS + CUSTO_POR_LINHA_LABS * max(0, linhas)


# ── a perda silenciosa ──────────────────────────────────────────────────────

def diff_pedido_devolvido(pedidas: list[str], devolvidas: list[str]) -> list[str]:
    """O que foi pedido e não voltou. A guarda mais importante deste arquivo.

    O Labs perde keyword SEM AVISAR: `cesantias` (CO) não volta, `status_code`
    vem 20000, não há erro em lugar nenhum e o item simplesmente não está no
    array. O Google Ads tem `cesantias` com 40.500 buscas/mês.

    Quem não compara o pedido contra o devolvido trata buraco de base como
    volume zero — e mata tema vivo com o portão `(volume, residual)`, que é
    exatamente o portão que `PORTOES_EXIGEM_MEDICAO` protegeu contra palpite e
    não protege contra medição ruim.
    """
    vistas = {(k or "").strip().lower() for k in devolvidas}
    return [k for k in pedidas if (k or "").strip().lower() not in vistas]


# ── volume: a unidade é o CLUSTER, nunca a string exata ─────────────────────

def volume_do_cluster(itens: list[dict]) -> tuple[int | None, dict]:
    """Soma o volume mensal do cluster e devolve a prova.

    A string exata mata tema bom por artefato de fraseado: `subsidio de vivienda
    ds49` devolve 90/mês sozinho — `residual`, portão disparado, tema morto — e
    o cluster de `saque aniversario fgts` soma 858.260 contra 74.000 do termo
    exato (11,6x).
    """
    linhas = [i for i in itens if isinstance(i, dict)]
    if not linhas:
        return None, {}
    total = 0
    cabeca, vol_cabeca = None, -1
    for i in linhas:
        v = i.get("search_volume")
        v = int(v) if isinstance(v, (int, float)) else 0
        total += v
        if v > vol_cabeca:
            cabeca, vol_cabeca = i.get("keyword"), v
    return total, {
        "termos_no_cluster": len(linhas),
        "soma_mensal": total,
        "termo_cabeca": cabeca,
        "volume_termo_cabeca": max(0, vol_cabeca),
    }


def termo_cabeca(itens: list[dict]) -> str | None:
    """O termo de MAIOR VOLUME do cluster — a regra fixa de qual SERP medir.

    `formato_consumo` é por tema, mas o tema é um cluster, e o índice de
    facilitador pode divergir entre `how to get nin slip` e `nin slip download`.
    Sem uma regra fixa a medição não é reproduzível. A regra é esta, e o termo
    escolhido vai gravado na evidência.
    """
    _, prova = volume_do_cluster(itens)
    return prova.get("termo_cabeca")


def existe_leilao(itens: list[dict]) -> tuple[bool | None, dict]:
    """`cpc: null` não é dado faltando — é AUSÊNCIA DE LEILÃO.

    É uma categoria que o `espaco.py` não tem: demanda real, zero anunciante.
    Metade das keywords de `2ª via IPTU` com volume de 390 a 2.900/mês tem `cpc`
    nulo; no México foi a regra, 32 de 32 termos.

    Binário de propósito. O VALOR de `keyword_info.cpc` é inutilizável —
    superestima o CPC real em 7,4x e a ordem inverte dentro do próprio cluster,
    então nenhum fator de correção conserta. Mas a PRESENÇA do campo é
    informação boa e já está paga.
    """
    linhas = [i for i in itens if isinstance(i, dict)]
    if not linhas:
        return None, {}
    com_cpc = sum(1 for i in linhas if isinstance(i.get("cpc"), (int, float)) and i["cpc"] > 0)
    return com_cpc > 0, {
        "termos_com_leilao": com_cpc,
        "termos_no_cluster": len(linhas),
        "share_com_leilao": round(com_cpc / len(linhas), 3),
    }


# ── reposição: janela fixa de 48 meses ──────────────────────────────────────

JANELA_MESES = 48


def ordenar_serie(monthly_searches: list[dict] | None) -> list[dict]:
    """Cronológica crescente — do mês mais antigo para o mais recente.

    ⚠️ NÃO É PARANOIA. A API devolve `monthly_searches` em ordem DECRESCENTE:
    medido, o primeiro item de `saque aniversario fgts` é 2026-06 e o último é
    2018-11. Quem fatiar `[-48:]` no array cru pega os 48 meses MAIS ANTIGOS
    e classifica a reposição pela pré-história do tema; quem varrer para achar
    o primeiro mês com volume acha o mais RECENTE e chama isso de data de
    nascimento.

    Os dois erros produzem número plausível, que é o tipo que ninguém confere.
    Por isso a ordenação é explícita e as duas funções abaixo passam por aqui.
    """
    serie = [m for m in (monthly_searches or [])
             if isinstance(m, dict) and m.get("year") and m.get("month")]
    return sorted(serie, key=lambda m: (int(m["year"]), int(m["month"])))


def janela_48(monthly_searches: list[dict] | None) -> list[dict]:
    """Os últimos 48 meses, em ordem crescente. Histórico profundo PIORA a
    sazonalidade.

    2020-2021 quebrou a fase de metade dos temas de coorte. `enem` sobre 92
    meses dá R²=0,41 e sai `continua`; sobre 48 dá R²=0,76 e sai `anual`.

    E a profundidade varia por keyword — 92 meses é típico (medido),
    `inscricao enem` tem 62 e `extrato fgts` tem 100. Nunca assuma janela fixa
    na entrada; fixe na saída.
    """
    return ordenar_serie(monthly_searches)[-JANELA_MESES:]


def nascimento_da_entidade(monthly_searches: list[dict] | None) -> str | None:
    """Os zeros à esquerda são a data de nascimento da entidade, e são exatos.

    `novo rg cin` tem 32 zeros e acende em 2022-04, o mês em que a CIN foi
    criada. `saque aniversario fgts` tem 8 zeros e acende em 2019-07, o mês da
    MP do saque-aniversário — confirmado nesta base.

    É sinal gratuito para `vacuo`: entidade recém-nascida não teve tempo de ser
    explicada por ninguém. Lê a série INTEIRA, não a janela de 48 meses: o
    nascimento costuma estar fora dela.
    """
    for m in ordenar_serie(monthly_searches):
        if (m.get("search_volume") or 0) > 0:
            return f"{int(m['year']):04d}-{int(m['month']):02d}"
    return None


# ── formato de consumo: por TEMA, medido na composição de domínio ───────────
#
# Critério medido, que separou 15 de 15 casos:
#   sobre os domínios ÚNICOS do top-10,
#   (facilitador + social) / únicos >= 0,40  E  oficial <= 0,30
# Acendeu só em NG-nin (0,86/0,29), NG-cac (0,50/0,20) e PH-nbi (0,86/0,14).
#
# ⚠️ ISTO É POR TEMA, NÃO POR PAÍS. A variação intra-Nigéria é maior que a
# variação BR↔NG. É o achado que derruba a ETAPA A do classificador — e é por
# isso que o eixo saiu do prompt do LLM e passou a ser medido aqui.

_SOCIAL = {
    "youtube.com", "youtu.be", "facebook.com", "m.facebook.com", "fb.com",
    "instagram.com", "tiktok.com", "twitter.com", "x.com", "reddit.com",
    "quora.com", "telegram.org", "t.me", "whatsapp.com", "linkedin.com",
    "pinterest.com", "threads.net", "nairaland.com",
}


def _e_social(dominio: str) -> bool:
    d = (dominio or "").lower().lstrip(".")
    return any(d == s or d.endswith("." + s) for s in _SOCIAL)


# Semente da lista de FACILITADORES: domínio comercial de terceiro que ranqueia
# para consulta de documento oficial — quem FAZ o trâmite no lugar do órgão.
#
# São só estes porque só estes têm evidência: o JSON das 96 medições guarda as
# conclusões, não as SERPs cruas. Uma lista escrita à mão para completar seria
# folclore com cara de dado — o mesmo erro da blocklist de palavras.
#
# A lista cresce sozinha: `nivel_formato_consumo` devolve, em toda medição,
# `candidatos_facilitador` — os domínios não-oficiais e não-sociais do top-10 —
# e a razão que o eixo teria se eles contassem. Em vinte cards existe uma lista
# candidata construída por uso, e o operador só confirma.
FACILITADORES_SEMENTE = frozenset({
    "ninbvnportal.com.ng",
})


def nivel_formato_consumo(
    serp: dict, *, facilitadores: set[str] | None = None
) -> tuple[str | None, dict]:
    """Composição de domínio do top-10 → o canal dominante daquele TEMA.

    Devolve `(nivel, prova)`. `None` quando a SERP não tem orgânicos — e aí o
    eixo fica AUSENTE, o que **não** é neutro: eixo ausente sai da média
    geométrica, então o silêncio subiria a nota. Quem trata isso é o chamador,
    tirando o card da fila com o motivo gravado.

    `voz_ou_humano` NUNCA sai daqui, e é honestidade, não limitação: uma SERP
    não enxerga busca por voz nem intermediário físico. Esse nível continua
    sendo declaração humana.

    `facilitadores` é a lista de domínios que EXECUTAM o serviço no lugar do
    órgão (despachante, agente, app de terceiro). Ela é da operação e começa
    vazia: sem ela o detector é conservador — pode deixar passar uma SERP
    dominada por facilitador, mas não produz falso positivo.
    """
    itens = [i for i in (serp.get("items") or [])
             if isinstance(i, dict) and i.get("type") == "organic"]
    if not itens:
        return None, {}

    top = itens[:10]
    unicos: list[str] = []
    for i in top:
        d = (i.get("domain") or "").lower()
        if d and d not in unicos:
            unicos.append(d)
    if not unicos:
        return None, {}

    fac = set(facilitadores) if facilitadores is not None else set(FACILITADORES_SEMENTE)
    n_social = sum(1 for d in unicos if _e_social(d))
    n_fac = sum(1 for d in unicos if d in fac)
    n_oficial = sum(1 for d in unicos if _e_oficial(d))

    r_canal = (n_social + n_fac) / len(unicos)
    r_oficial = n_oficial / len(unicos)

    # A lista de facilitadores cresce do próprio uso. Todo domínio do top-10 que
    # não é oficial nem social é, por estrutura, terceiro comercial disputando
    # uma consulta de trâmite — que é a definição de facilitador. Não vira nível
    # sozinho: vira CANDIDATO, gravado na evidência para o operador confirmar.
    candidatos = [d for d in unicos
                  if d not in fac and not _e_social(d) and not _e_oficial(d)]
    r_se_todos = (n_social + n_fac + len(candidatos)) / len(unicos)

    prova = {
        "dominios_unicos": unicos,
        "n_unicos": len(unicos),
        "social": n_social,
        "facilitador": n_fac,
        "oficial": n_oficial,
        "razao_canal": round(r_canal, 3),
        "razao_oficial": round(r_oficial, 3),
        "criterio": "(facilitador+social)/unicos >= 0.40 e oficial <= 0.30",
        # Quanto o eixo mudaria se TODO terceiro comercial fosse facilitador.
        # É o teto da incerteza desta medição: se ele já não cruza 0,40, a lista
        # incompleta não pode estar escondendo um mercado de vídeo/intermediário.
        "candidatos_facilitador": candidatos,
        "razao_canal_se_todos_candidatos": round(r_se_todos, 3),
        "quase_disparou": bool(r_canal < 0.40 <= r_se_todos and r_oficial <= 0.30),
    }

    if r_canal >= 0.40 and r_oficial <= 0.30:
        return "video_social", prova
    if r_canal <= 0.20:
        return "texto_busca", prova
    return "misto", prova


# ── vácuo: quem já explicou, e quem tem AUDIÊNCIA ──────────────────────────

def nivel_vacuo_com_trafego(
    serp: dict,
    etv_por_dominio: dict[str, float] | None = None,
    *,
    dominios_grandes: set[str] | None = None,
    piso_etv: float = 1000.0,
) -> tuple[str | None, dict]:
    """`nivel_vacuo` com tráfego real, que é o que separa portal de casca.

    Contar domínio responde "quantos apareceram". Contar audiência responde
    "quantos importam", e a diferença é de quatro ordens de grandeza, limpa:
    `direito2.com.br` tem ETV 23.549 sobre 898 keywords; `creditoup.com.br` tem
    **7,2** sobre 10. Os dois ocupam uma linha na SERP; só um é concorrência.

    `bulk_traffic_estimation` lota até 1.000 alvos por chamada — 20 cards x 10
    domínios = 200 alvos = US$ 0,036 pela coluna inteira. É barato porque é
    lotado, e por isso ele vive no lote e não no card avulso.

    ⚠️ ETV não é régua de RECEITA (é volume x CTR-modelo da posição, e 83% do
    ETV de `direito2` vem de UMA página em #38 numa keyword de 9,14M/mês, onde
    o CTR real é ~0). Aqui ele é usado só para o que ele de fato mede: se o
    domínio tem presença orgânica ou é casca.
    """
    itens = [i for i in (serp.get("items") or [])
             if isinstance(i, dict) and i.get("type") == "organic"]
    if not itens:
        return None, {}

    etv = {k.lower(): v for k, v in (etv_por_dominio or {}).items()}
    grandes = dominios_grandes or set()
    top = itens[:10]

    unicos: list[str] = []
    for i in top:
        d = (i.get("domain") or "").lower()
        if d and d not in unicos:
            unicos.append(d)

    oficiais = [d for d in unicos if _e_oficial(d)]
    nao_oficiais = [d for d in unicos if not _e_oficial(d)]

    if etv:
        # Portal com audiência de verdade. Sem ETV medido, todo domínio conta —
        # que é o comportamento antigo, e ele infla `vacuo` para disputado.
        com_audiencia = [d for d in nao_oficiais if etv.get(d, 0.0) >= piso_etv]
    else:
        com_audiencia = nao_oficiais

    n_grandes = sum(1 for d in com_audiencia if any(g in d for g in grandes))
    n_portal = len(com_audiencia)

    prova = {
        "termo": serp.get("keyword"),
        "dominios_unicos": unicos,
        "oficiais": oficiais,
        "portais_com_audiencia": com_audiencia,
        "etv_por_dominio": {d: round(etv.get(d, 0.0), 1) for d in nao_oficiais} or None,
        "piso_etv": piso_etv if etv else None,
        "criterio_audiencia": ("ETV medido >= piso" if etv
                               else "sem ETV — todo domínio conta (conservador)"),
    }

    if n_portal <= 1:
        return "virgem", prova
    if n_grandes == 0 and n_portal <= 4:
        return "raso", prova
    if n_grandes <= 2:
        return "disputado", prova
    return "saturado", prova


def etv_por_dominio(resposta_bulk: dict) -> dict[str, float]:
    """`bulk_traffic_estimation` → {domínio: ETV orgânico}.

    ⚠️ Interseção entre dois portais é evidência de DERROTA COMPARTILHADA, não
    de tema provado: nas 239 keywords que `direito2` e `pautasocial` dividem, os
    dois ranqueiam entre a posição 50 e a 95, e em nenhuma algum chega ao
    top-20. Lido ingenuamente isso marcaria `vacuo` como disputado com o campo
    vazio. Por isso aqui só se lê o ETV do domínio, nunca a interseção.
    """
    out: dict[str, float] = {}
    for item in itens(resposta_bulk):
        alvo = (item.get("target") or "").lower()
        if not alvo:
            continue
        organico = ((item.get("metrics") or {}).get("organic") or {})
        out[alvo] = float(organico.get("etv") or 0.0)
    return out

# ── as DUAS cabeças do cluster ─────────────────────────────────────────────
#
# Descoberta medida: "termo de maior volume" seleciona a consulta que RESOLVE,
# não a que EXPLICA — e em serviço público isso é sistemático, não acidente.
#
#     'ipva 2026'          vacuo=virgem     8 de 9 domínios oficiais
#     'ipva'               vacuo=virgem     8 de 9 domínios oficiais
#     'como calcular ipva' vacuo=disputado  4 de 9 — gringo, serasa, bv, youtube
#
# Quem digita `ipva` quer PAGAR, e o Google devolve a secretaria da fazenda. A
# concorrência editorial — a SERP em que a gente competiria — vive na pergunta.
#
# Então são duas cabeças, porque são duas perguntas:
#
#     cabeca_de_demanda   maior volume entre os NOMES da entidade
#                         -> `volume` e `reposicao` (tamanho e renovação)
#     cabeca_editorial    maior volume entre as CONSULTAS em forma de pergunta
#                         -> `vacuo` e `formato_consumo` (o campo de batalha)
#
# Ambas vão gravadas na evidência. Sem isso a medição não é reproduzível.

# Marcadores de pergunta em pt/es/en. Não é lista de palavras proibidas: é o
# reconhecedor da FORMA interrogativa, que é o que atravessa idioma — a mesma
# tese do `psique.py`. Substantivo não viaja; pergunta viaja.
RX_PERGUNTA = (
    r"(^|\s)("
    r"como|c[oó]mo|how|"
    r"quem|qui[eé]n|who|"
    r"quando|cu[aá]ndo|when|"
    r"qual|quais|cu[aá]l|cu[aá]les|which|"
    r"onde|d[oó]nde|where|"
    r"quanto|quanta|cu[aá]nto|cu[aá]nta|"
    r"por ?que|por ?qu[eé]|why|"
    r"o que|qu[eé]|what|"
    r"vale a pena|merece la pena|worth it|"
    r"passo a passo|paso a paso|step by step|"
    r"tem direito|tiene derecho|eligible|"
    r"funciona|works?"
    r")(\s|$)"
)
_RX_PERGUNTA = re.compile(RX_PERGUNTA, re.IGNORECASE)


def e_pergunta(termo: str) -> bool:
    return bool(_RX_PERGUNTA.search(sem_acento((termo or "").lower())))


def escolher_cabecas(volumes: dict[str, int], *, nomes: list[str],
                     consultas: list[str]) -> tuple[str | None, str | None, dict]:
    """As duas cabeças, com o fallback declarado quando não houver pergunta.

    `volumes` é `{termo: volume mensal medido}` — só entram termos que a API de
    fato devolveu, nunca os que ela perdeu em silêncio.

    Fallback: sem nenhuma consulta em forma de pergunta, a cabeça editorial
    passa a ser a de demanda **e isso vai gravado**. Medir `vacuo` na consulta
    navegacional continua sendo pior que não medir? Não: continua sendo um
    dado, só que sobre outra SERP. O que não pode é ficar invisível.
    """
    def maior(candidatos: list[str]) -> str | None:
        elegiveis = [(t, volumes.get(t, 0)) for t in candidatos if t in volumes]
        if not elegiveis:
            return None
        return max(elegiveis, key=lambda kv: kv[1])[0]

    demanda = maior(nomes) or maior(list(volumes)) or None
    perguntas = [c for c in consultas if e_pergunta(c)]
    editorial = maior(perguntas)
    fallback = editorial is None
    if fallback:
        editorial = maior(consultas) or demanda

    return demanda, editorial, {
        "cabeca_de_demanda": demanda,
        "cabeca_editorial": editorial,
        "regra_demanda": "maior volume entre os nomes da entidade",
        "regra_editorial": ("maior volume entre as consultas em forma de pergunta"
                            if not fallback else
                            "FALLBACK — nenhuma consulta em forma de pergunta no card"),
        "fallback_editorial": fallback,
        "consultas_interrogativas": perguntas,
        "volume_demanda": volumes.get(demanda or "", 0),
        "volume_editorial": volumes.get(editorial or "", 0),
    }


def perguntas_do_paa(serp: dict) -> list[str]:
    """As perguntas do bloco "As pessoas também perguntam".

    É a lista de perguntas que as pessoas fazem sobre o tema, **escrita pelo
    Google**, e ela vem de graça no payload da SERP que já pagamos.

    Por que ela é a fonte certa da cabeça editorial: os `seed_queries` do card
    são o que o DESCOBRIDOR imaginou que se pergunta. Medido no IPVA, eles
    davam `como consultar ipva pelo renavam` — navegacional — e o `vacuo` saía
    `virgem` porque a SERP era 8 de 9 secretarias de fazenda. O PAA da mesma
    SERP traz `Como é calculado o IPVA?`, que é a consulta editorial de fato.

    Conserta a causa (o descobridor não sabe o que se pergunta) em vez do
    sintoma (a cabeça errada), e sem uma chamada nova.
    """
    fora: list[str] = []
    for bloco in (serp.get("items") or []):
        if not isinstance(bloco, dict) or bloco.get("type") != "people_also_ask":
            continue
        for item in (bloco.get("items") or []):
            titulo = (item or {}).get("title") if isinstance(item, dict) else None
            if isinstance(titulo, str) and titulo.strip() and titulo not in fora:
                fora.append(titulo.strip())
    return fora


def cabeca_editorial_do_paa(perguntas: list[str], volumes: dict[str, int]
                            ) -> tuple[str | None, dict]:
    """A pergunta do PAA com maior volume MEDIDO — ou a primeira, se nenhuma foi.

    A primeira do PAA não é escolha arbitrária: o Google as ordena, e a
    primeira é a mais frequente. Sem medição própria, essa ordem é a melhor
    informação disponível — e o fato de não ter havido medição vai gravado.
    """
    if not perguntas:
        return None, {"paa_disponivel": False}
    chave = {" ".join(k.strip().lower().split()): v for k, v in (volumes or {}).items()}
    medidas = [(q, chave.get(" ".join(q.strip().lower().split()), 0)) for q in perguntas]
    com_volume = [(q, v) for q, v in medidas if v > 0]
    if com_volume:
        escolhida, vol = max(com_volume, key=lambda kv: kv[1])
        regra = "pergunta do PAA com maior volume medido"
    else:
        escolhida, vol = perguntas[0], 0
        regra = "primeira pergunta do PAA — nenhuma delas tem volume medido"
    return escolhida, {
        "paa_disponivel": True,
        "paa_perguntas": perguntas,
        "regra_editorial": regra,
        "volume_editorial": vol,
    }


def nivel_densidade(serp: dict, tem_leilao: bool | None = None,
                    *, facilitadores: set[str] | None = None) -> tuple[str | None, dict]:
    """Quantos compradores disputam esta pessoa NESTE estado mental.

    Deixa de ser julgamento de LLM. O eixo pergunta "quantos setores pagariam
    para falar com ela", e a SERP já mostra quem de fato apareceu: domínio
    comercial de terceiro no top-10 é alguém que investiu para estar ali.

    Duas razões para tirar do LLM:

    1. Era o pior dos dois mundos — um palpite sobre DINHEIRO feito por quem
       não vê o mercado, num motor que já decidiu não medir dinheiro.
    2. A SERP já está paga. Contar domínio comercial custa zero.

    ⚠️ PROXY DECLARADO: domínio distinto não é setor distinto. Dois bancos são
    um setor e contam dois. O proxy erra para MAIS, então serve de piso, e os
    domínios vão gravados para quem duvidar conferir.

    `tem_leilao` vem de `existe_leilao()` sobre o mesmo cluster: sem leilão,
    existe demanda e não existe comprador, e isso é `nenhuma` — não `rala`.
    """
    itens = [i for i in (serp.get("items") or [])
             if isinstance(i, dict) and i.get("type") == "organic"]
    if not itens:
        return None, {}

    fac = set(facilitadores) if facilitadores is not None else set(FACILITADORES_SEMENTE)
    unicos: list[str] = []
    for i in itens[:10]:
        d = (i.get("domain") or "").lower()
        if d and d not in unicos:
            unicos.append(d)

    comerciais = [d for d in unicos
                  if not _e_oficial(d) and not _e_social(d) and d not in fac]
    prova = {
        "dominios_comerciais": comerciais,
        "n_comerciais": len(comerciais),
        "n_unicos": len(unicos),
        "existe_leilao": tem_leilao,
        "proxy": "domínio comercial de terceiro no top-10; domínio != setor, "
                 "erra para mais, serve de piso",
    }

    if tem_leilao is False and not comerciais:
        return "nenhuma", prova
    if len(comerciais) >= 3:
        return "densa", prova
    if len(comerciais) >= 1:
        return "media", prova
    return "rala", prova


# ── o `virgem` ambíguo, e como desambiguar SEM dado próprio ────────────────

def leitura_do_vazio(nivel_vacuo: str | None, *, existe_leilao: bool | None,
                     etv_publishers: list[float] | None = None,
                     piso_etv: float = 1000.0) -> tuple[str, str]:
    """`virgem` significa duas coisas OPOSTAS, e a diferença decide tudo.

    ## O problema

    `nivel_vacuo` devolve `virgem` (valor 1,00, o topo) quando a SERP é tomada
    pela fonte oficial e quase não há portal. Mas isso comporta duas leituras
    que apontam para lados contrários:

        ninguém ACHOU ainda            -> é oportunidade
        ninguém CONSEGUIU monetizar    -> é armadilha

    A segunda é exatamente o arquétipo que consumiu R$ 138.814. Hoje quem separa
    as duas é o portão — leitura de LLM, AC1 0,64. Aqui elas se separam por
    ESTRUTURA DE MERCADO, que é pública, não depende de LLM nenhum e não depende
    de histórico próprio.

    ## Por que isso importa para quem está começando

    A recomendação de "puxe seu GAM" tem um paradoxo embutido: o motor existe
    para entrar em nicho e país onde nunca se rodou, e lá não há dado próprio
    por definição. Dado próprio calibra o QUANTO; ele não pode decidir o SE de
    um mercado onde não se esteve.

    Esta leitura é o limite do que dado público indica sem se enganar:

        virgem + há leilão + nenhum publisher com tráfego
            -> `descoberta`   alguém PAGA por essa atenção e ninguém montou
                              conteúdo em cima. É a definição de oportunidade.

        virgem + NÃO há leilão
            -> `deserto`      ninguém paga. O topo do eixo aqui é miragem: não
                              há vácuo a explorar, há mercado que não existe.

        virgem + há publisher COM tráfego
            -> `ocupado`      não é virgem; é um publisher só, e ele já provou
                              que dá para viver ali. Muda a pergunta de "existe?"
                              para "eu ganho dele?".

    ⚠️ HIPÓTESE, e declarada como tal. A ligação entre "há leilão" e "a página
    monetiza" é plausível e NÃO foi medida nesta operação. Isto reporta e não
    decide: não zera índice, não rebaixa nível, não entra em conta. É o número
    que o primeiro funil publicado vai confirmar ou derrubar.
    """
    if nivel_vacuo != "virgem":
        return "nao_se_aplica", ""
    com_trafego = [e for e in (etv_publishers or []) if e and e >= piso_etv]
    if com_trafego:
        return "ocupado", (
            f"{len(com_trafego)} publisher(s) com ETV acima de {piso_etv:.0f} na "
            f"SERP: o vazio é aparente, e alguém já vive disso")
    if existe_leilao is False:
        return "deserto", (
            "SERP sem anúncio: ninguém paga por essa atenção. `virgem` aqui é "
            "ausência de mercado, não espaço livre")
    if existe_leilao is True:
        return "descoberta", (
            "há leilão e nenhum publisher com tráfego: alguém paga por essa "
            "atenção e ninguém montou conteúdo em cima")
    return "indeterminado", "sem medição de leilão para separar deserto de descoberta"
