"""Mining do Pautador: concorrência limitada, cache live e skip do Prospector.

Tudo hermético: os clientes de Keyword Planner e DataForSEO são dublês locais,
o LLM é um dublê que conta chamadas, e nenhuma linha toca rede. A sobreposição
é medida por eventos e contadores, nunca por `sleep` longo.

As provas, na ordem da missão:

  1-4  seeds concorrem sob o teto, voltam na ordem de entrada, o laço interno
       de cada seed continua sequencial e uma seed que falha não derruba as
       outras — com warnings em ordem determinística;
  5    autocomplete e related correm juntos e voltam no contrato de sempre;
  6-10 cache: hit evita chamada, concorrentes iguais fazem UMA leitura, TTL
       vencido relê, chaves diferentes não colidem, e erro/None/mock não entram;
  11-12 filas vazias pulam o Funnel Prospector; qualquer material o chama.
"""
from __future__ import annotations

import asyncio

import pytest

from app.agents.base import AgentContext
from app.agents.mining import orchestrator as orq
from app.config import Settings
from app.services import leitura_compartilhada as lc

GEO = 2826
LANG = 1000


def _settings(**extra) -> Settings:
    base = dict(
        _env_file=None,
        gemini_api_key="",
        google_api_key="",
        pautador_kw_engine="live",
        pautador_kw_max_loops=2,
        pautador_kw_min_volume_gold=10,
    )
    base.update(extra)
    return Settings(**base)


def _orquestrador(**extra) -> orq.MiningOrchestrator:
    return orq.MiningOrchestrator(
        AgentContext(settings=_settings(**extra), engine=None))


@pytest.fixture(autouse=True)
def _sem_pausa(monkeypatch):
    # A pausa entre laços é de 1 s contra a API real. Aqui ela só atrasaria.
    monkeypatch.setattr(orq, "_PAUSA_ENTRE_LOOPS_S", 0.0)


class _Planner:
    """Dublê de `GoogleAdsKeywordPlannerClient` que mede concorrência.

    Cada seed devolve uma ideia nova com volume, então `extract_gold` continua
    o laço até `max_loops` — duas chamadas por seed com `max_loops=2`.
    """

    enabled = True
    auth_mode = "dublê"
    customer_id = "1000000001"

    chamadas: list = []
    em_curso = 0
    pico = 0
    #: seed -> evento que segura a resposta até o teste liberar
    portas: dict = {}
    falhar: set = set()

    def __init__(self, _settings):
        pass

    @classmethod
    def zerar(cls):
        cls.chamadas = []
        cls.em_curso = 0
        cls.pico = 0
        cls.portas = {}
        cls.falhar = set()

    async def generate_keyword_ideas(self, *, seed_keyword, geo_target,
                                     language_constant, page_size=100):
        cls = type(self)
        cls.chamadas.append(seed_keyword)
        cls.em_curso += 1
        cls.pico = max(cls.pico, cls.em_curso)
        try:
            porta = cls.portas.get(seed_keyword)
            if porta is not None:
                await porta.wait()
            else:
                await asyncio.sleep(0)
            if seed_keyword in cls.falhar:
                raise RuntimeError(f"quota da seed {seed_keyword}")
            return [{"text": f"{seed_keyword} mais",
                     "keywordIdeaMetrics": {"avgMonthlySearches": "500"}}]
        finally:
            cls.em_curso -= 1


@pytest.fixture
def planner(monkeypatch):
    _Planner.zerar()
    monkeypatch.setattr(orq, "GoogleAdsKeywordPlannerClient", _Planner)
    return _Planner


def _seeds(*nomes):
    return [{"seed_keyword": n} for n in nomes]


async def _minerar(o, seeds):
    return await o._keyword_planner(
        seeds=_seeds(*seeds), geo_target=GEO, language_constant=LANG,
        language_code="en", language_short="en", pais_geo="Teste",
        nicho="nicho", engine="live")


# ═══════════════════════════════════════════════════════════════════════════
# 1-4 · concorrência entre seeds
# ═══════════════════════════════════════════════════════════════════════════


async def test_seeds_sobrepoem_mas_nunca_passam_do_teto(planner):
    """Teto 2 com quatro seeds: há sobreposição, e ela nunca chega a 3."""
    o = _orquestrador(pautador_kw_concorrencia_seeds=2)
    runs = await _minerar(o, ["a", "b", "c", "d"])
    assert planner.pico == 2
    # O total de chamadas é o mesmo da execução sequencial: 2 por seed.
    assert len(planner.chamadas) == 8
    assert [r["seed_keyword"] for r in runs] == ["a", "b", "c", "d"]


@pytest.mark.parametrize("pedido,efetivo", [(1, 1), (3, 3), (9, 3), (0, 1)])
async def test_o_teto_configurado_e_limitado_a_tres(planner, pedido, efetivo):
    o = _orquestrador(pautador_kw_concorrencia_seeds=pedido)
    await _minerar(o, ["a", "b", "c", "d", "e"])
    assert planner.pico == efetivo


def test_o_default_e_conservador():
    assert Settings(_env_file=None).pautador_kw_concorrencia_seeds == 2


async def test_a_ordem_final_e_a_de_entrada_mesmo_quando_a_segunda_termina_antes(planner):
    planner.portas["a"] = asyncio.Event()
    o = _orquestrador(pautador_kw_concorrencia_seeds=2)
    tarefa = asyncio.ensure_future(_minerar(o, ["a", "b"]))
    # Deixa "b" terminar os dois laços enquanto "a" está presa na porta.
    for _ in range(50):
        await asyncio.sleep(0)
        if planner.chamadas.count("b mais") == 1 and planner.em_curso == 1:
            break
    assert "b mais" in planner.chamadas, "b deveria ter concluído antes de a"
    planner.portas["a"].set()
    runs = await tarefa
    assert [r["seed_keyword"] for r in runs] == ["a", "b"]
    assert planner.chamadas.index("b mais") < planner.chamadas.index("a mais")


async def test_o_laco_interno_de_uma_seed_continua_sequencial(planner):
    o = _orquestrador(pautador_kw_concorrencia_seeds=3)
    runs = await _minerar(o, ["a"])
    assert planner.chamadas == ["a", "a mais"]
    assert planner.pico == 1
    assert runs[0]["loop_iteration"] == 1


async def test_uma_seed_que_falha_nao_cancela_as_outras_e_o_aviso_e_deterministico(planner):
    planner.falhar = {"a", "c"}
    # "c" é liberada antes de "a": a ordem de conclusão é c, a.
    planner.portas["a"] = asyncio.Event()
    o = _orquestrador(pautador_kw_concorrencia_seeds=3)
    tarefa = asyncio.ensure_future(_minerar(o, ["a", "b", "c"]))
    for _ in range(50):
        await asyncio.sleep(0)
    planner.portas["a"].set()
    runs = await tarefa
    assert [r["seed_keyword"] for r in runs] == ["a", "b", "c"]
    # b segue o laço inteiro; a e c caem no mesmo fallback de sempre.
    assert runs[1]["master_bank"]
    assert runs[0]["master_bank"] == [] and runs[2]["master_bank"] == []
    falhas = [w for w in o.warnings if w.startswith("Keyword Planner falhou")]
    assert falhas == [
        "Keyword Planner falhou para 'a': quota da seed a",
        "Keyword Planner falhou para 'c': quota da seed c",
    ]


async def test_paridade_com_a_execucao_sequencial(planner):
    """Mesmo resultado com teto 1 (o comportamento antigo) e com teto 3."""
    seq = await _minerar(_orquestrador(pautador_kw_concorrencia_seeds=1),
                         ["a", "b", "c"])
    lc_cache().limpar()
    par = await _minerar(_orquestrador(pautador_kw_concorrencia_seeds=3),
                         ["a", "b", "c"])
    assert seq == par


def lc_cache():
    return orq._LEITURA_KEYWORD_PLANNER


# ═══════════════════════════════════════════════════════════════════════════
# 5 · DataForSEO: as duas leituras juntas, no contrato de sempre
# ═══════════════════════════════════════════════════════════════════════════


def _dfs_ok(itens):
    return {"status_code": 20000,
            "tasks": [{"status_code": 20000, "result": [{"items": itens}]}]}


class _DataForSeo:
    enabled = True
    chamadas: list = []
    em_curso = 0
    pico = 0
    resposta_ac = None
    resposta_rel = None
    erro_ac: Exception | None = None
    barreira: asyncio.Event | None = None

    def __init__(self, _settings):
        pass

    @classmethod
    def zerar(cls):
        cls.chamadas = []
        cls.em_curso = 0
        cls.pico = 0
        cls.resposta_ac = _dfs_ok([{"keyword": "ac um"}])
        cls.resposta_rel = _dfs_ok([{"keyword_data": {
            "keyword": "rel um", "keyword_info": {"search_volume": 70}}}])
        cls.erro_ac = None
        cls.barreira = None

    async def _medir(self, nome):
        cls = type(self)
        cls.chamadas.append(nome)
        cls.em_curso += 1
        cls.pico = max(cls.pico, cls.em_curso)
        try:
            if cls.barreira is not None:
                if cls.em_curso == 2:
                    cls.barreira.set()
                await asyncio.wait_for(cls.barreira.wait(), timeout=2)
            else:
                await asyncio.sleep(0)
        finally:
            cls.em_curso -= 1

    async def autocomplete(self, keyword, location_code, language_code):
        await self._medir("autocomplete")
        if type(self).erro_ac is not None:
            raise type(self).erro_ac
        return type(self).resposta_ac

    async def related_keywords(self, keyword, location_code, language_short):
        await self._medir("related")
        return type(self).resposta_rel


@pytest.fixture
def dfs(monkeypatch):
    _DataForSeo.zerar()
    monkeypatch.setattr(orq, "DataForSeoClient", _DataForSeo)
    return _DataForSeo


async def _dataforseo(o, nicho="nicho", location=GEO, lang="en"):
    return await o._dataforseo(nicho=nicho, location_code=location,
                               language_code=lang, language_short=lang,
                               engine="live")


async def test_autocomplete_e_related_correm_juntos_e_voltam_na_posicao_de_sempre(dfs):
    # A barreira só abre quando as DUAS estão em curso ao mesmo tempo. Na
    # versão sequencial, a primeira esperaria 2 s e o teste cairia por timeout.
    dfs.barreira = asyncio.Event()
    ac, rel = await _dataforseo(_orquestrador())
    assert dfs.pico == 2
    assert [k["keyword"] for k in ac] == ["ac um"]
    assert [k["keyword"] for k in rel] == ["rel um"]
    assert ac[0]["source"] == "google_autocomplete"
    assert rel[0]["source"] == "related_keywords_labs"


async def test_falha_de_uma_leitura_preserva_o_fallback_e_o_aviso_de_sempre(dfs):
    dfs.erro_ac = RuntimeError("401 autocomplete")
    o = _orquestrador()
    assert await _dataforseo(o) == ([], [])
    assert o.warnings == ["DataForSEO falhou: 401 autocomplete"]
    # Nenhuma leitura em dobro: uma de cada.
    assert sorted(dfs.chamadas) == ["autocomplete", "related"]


# ═══════════════════════════════════════════════════════════════════════════
# 6-10 · cache live
# ═══════════════════════════════════════════════════════════════════════════


async def test_cache_hit_evita_nova_chamada(planner, dfs):
    o = _orquestrador()
    await _minerar(o, ["a"])
    await _dataforseo(o)
    antes_kp, antes_dfs = len(planner.chamadas), len(dfs.chamadas)

    o2 = _orquestrador()
    runs = await _minerar(o2, ["a"])
    ac, rel = await _dataforseo(o2)
    assert len(planner.chamadas) == antes_kp
    assert len(dfs.chamadas) == antes_dfs
    assert runs[0]["master_bank"] and ac and rel
    assert orq._LEITURA_KEYWORD_PLANNER.telemetria()["hit"] == 2


async def test_concorrentes_iguais_fazem_uma_unica_leitura(planner):
    planner.portas["a"] = asyncio.Event()
    o1, o2 = _orquestrador(), _orquestrador()
    t1 = asyncio.ensure_future(_minerar(o1, ["a"]))
    t2 = asyncio.ensure_future(_minerar(o2, ["a"]))
    for _ in range(10):
        await asyncio.sleep(0)
    planner.portas["a"].set()
    r1, r2 = await asyncio.gather(t1, t2)
    assert planner.chamadas == ["a", "a mais"]
    assert r1 == r2
    tel = orq._LEITURA_KEYWORD_PLANNER.telemetria()
    assert tel["compartilhada"] >= 1


async def test_ttl_vencido_rele(planner, monkeypatch):
    agora = [1000.0]
    cache = lc.LeituraCompartilhada("kp-teste", max_entradas=8,
                                    relogio=lambda: agora[0])
    monkeypatch.setattr(orq, "_LEITURA_KEYWORD_PLANNER", cache)
    o = _orquestrador(pautador_kw_cache_ttl_s=60, pautador_kw_max_loops=1)
    await _minerar(o, ["a"])
    await _minerar(o, ["a"])
    assert planner.chamadas == ["a"]
    agora[0] += 61
    await _minerar(o, ["a"])
    assert planner.chamadas == ["a", "a"]


async def test_geo_idioma_config_e_seed_diferentes_nao_colidem(planner):
    o = _orquestrador(pautador_kw_max_loops=1)

    async def _uma(seed, geo=GEO, lang=LANG):
        await o._keyword_planner(
            seeds=_seeds(seed), geo_target=geo, language_constant=lang,
            language_code="en", language_short="en", pais_geo="T",
            nicho="n", engine="live")

    await _uma("a")
    await _uma("b")
    await _uma("a", geo=2076)
    await _uma("a", lang=1014)
    assert len(planner.chamadas) == 4
    # A seed normalizada é a mesma chave: caixa e espaços não abrem leitura.
    await _uma("  A ")
    assert len(planner.chamadas) == 4

    _Planner.customer_id = "1000000002"
    try:
        await _uma("a")
    finally:
        _Planner.customer_id = "1000000001"
    assert len(planner.chamadas) == 5, "outra conta é outra moeda de CPC"


async def test_dataforseo_location_e_idioma_nao_colidem(dfs):
    o = _orquestrador()
    await _dataforseo(o)
    await _dataforseo(o, location=2076)
    await _dataforseo(o, lang="pt")
    await _dataforseo(o, nicho="outro")
    assert len(dfs.chamadas) == 8


async def test_erro_nao_entra_no_cache(planner):
    planner.falhar = {"a"}
    o = _orquestrador(pautador_kw_max_loops=1)
    await _minerar(o, ["a"])
    planner.falhar = set()
    await _minerar(o, ["a"])
    assert planner.chamadas == ["a", "a"]


async def test_resposta_dataforseo_com_erro_de_tarefa_nao_entra_no_cache(dfs):
    """HTTP 200 com tarefa em erro é resposta PARCIAL, não sucesso medido."""
    dfs.resposta_ac = {"status_code": 20000,
                       "tasks": [{"status_code": 40501, "result": None}]}
    o = _orquestrador()
    await _dataforseo(o)
    await _dataforseo(o)
    assert dfs.chamadas.count("autocomplete") == 2
    assert dfs.chamadas.count("related") == 1


async def test_none_nao_entra_no_cache(dfs):
    dfs.resposta_rel = None
    o = _orquestrador()
    await _dataforseo(o)
    assert o.warnings and o.warnings[0].startswith("DataForSEO falhou")
    await _dataforseo(o)
    assert dfs.chamadas.count("related") == 2


async def test_vazio_medido_e_sucesso_e_entra_no_cache(planner, monkeypatch):
    async def _vazio(self, **_k):
        type(self).chamadas.append("vazio")
        return []

    monkeypatch.setattr(_Planner, "generate_keyword_ideas", _vazio)
    o = _orquestrador()
    await _minerar(o, ["a"])
    await _minerar(o, ["a"])
    assert planner.chamadas == ["vazio"]
    assert not [w for w in o.warnings if "falhou" in w]


async def test_timeout_nao_entra_no_cache(planner):
    async def _lento(self, **_k):
        type(self).chamadas.append("lento")
        raise asyncio.TimeoutError()

    _Planner.generate_keyword_ideas, original = _lento, _Planner.generate_keyword_ideas
    try:
        o = _orquestrador(pautador_kw_max_loops=1)
        await _minerar(o, ["a"])
        await _minerar(o, ["a"])
    finally:
        _Planner.generate_keyword_ideas = original
    assert planner.chamadas == ["lento", "lento"]


async def test_mock_nao_polui_o_cache_live(planner, dfs):
    o = _orquestrador()
    await o._keyword_planner(
        seeds=_seeds("a"), geo_target=GEO, language_constant=LANG,
        language_code="en", language_short="en", pais_geo="T", nicho="n",
        engine="mock")
    await o._dataforseo(nicho="nicho", location_code=GEO, language_code="en",
                        language_short="en", engine="mock")
    assert orq._LEITURA_KEYWORD_PLANNER.telemetria()["entradas"] == 0
    assert orq._LEITURA_DATAFORSEO.telemetria()["entradas"] == 0
    await _minerar(o, ["a"])
    assert planner.chamadas, "o live não pode ser servido pelo mock"


def test_a_chave_nao_carrega_credencial(planner):
    """A chave é um hash; nem login, nem token, nem customer id em claro."""
    chave = orq._chave_keyword_planner(_Planner(None), seed="a",
                                       geo_target=GEO, language_constant=LANG)
    assert len(chave) == 64 and all(c in "0123456789abcdef" for c in chave)
    assert _Planner.customer_id not in chave


# ═══════════════════════════════════════════════════════════════════════════
# 11-12 · Funnel Prospector
# ═══════════════════════════════════════════════════════════════════════════


class _LLM:
    chamadas = 0

    async def complete_json(self, _sistema, _usuario):
        type(self).chamadas += 1
        return {"funis_sugeridos": [{"rank": 1}], "resumo": {}}


def _gold(ads, conteudo):
    return {"summary": {"ads_approved": len(ads), "content_ideas": len(conteudo)},
            "production_ads_queue": ads, "content_seo_queue": conteudo}


async def _prospectar(o, gm):
    return await o._funnel_prospector(
        pais_geo="T", geo_target=GEO, language_code="en", nicho="n",
        objective="o", gold_miner=gm)


async def test_filas_vazias_pulam_o_prospector_sem_chamar_o_llm(monkeypatch):
    _LLM.chamadas = 0
    o = _orquestrador()
    monkeypatch.setattr(o, "_gemini", lambda: _LLM())
    saida = await _prospectar(o, _gold([], []))
    assert _LLM.chamadas == 0
    assert saida["funis_sugeridos"] == []
    assert saida["codigo"] == orq.PROSPECTOR_SEM_MATERIAL
    assert any(w.startswith(orq.PROSPECTOR_SEM_MATERIAL) for w in o.warnings)
    assert "funnel_prospector:sem_material" in o.services_used


@pytest.mark.parametrize("ads,conteudo", [
    ([{"keyword": "k", "volume": 10}], []),
    ([], [{"keyword": "c", "volume": 10}]),
])
async def test_qualquer_material_mantem_a_chamada(monkeypatch, ads, conteudo):
    _LLM.chamadas = 0
    o = _orquestrador()
    monkeypatch.setattr(o, "_gemini", lambda: _LLM())
    saida = await _prospectar(o, _gold(ads, conteudo))
    assert _LLM.chamadas == 1
    assert saida["funis_sugeridos"] == [{"rank": 1}]
    assert "gemini:funnel_prospector" in o.services_used


async def test_run_com_filas_vazias_preserva_metricas_cluster_e_filas(monkeypatch):
    """A rodada inteira, mock, com o Gold Miner devolvendo filas vazias."""
    _LLM.chamadas = 0
    vazio = _gold([], [])
    vazio["summary"] = {"ads_approved": 0, "content_ideas": 0}
    monkeypatch.setattr(orq, "gold_miner_classify", lambda _kws: vazio)
    o = _orquestrador(pautador_kw_engine="mock")
    monkeypatch.setattr(o, "_gemini", lambda: None)
    saida = await o.run({"country": "Reino Unido", "country_code": "GB",
                         "main_keyword": "nicho"})
    assert saida["funis_sugeridos"] == []
    assert saida["factory_output"] == []
    assert saida["production_ads_queue"] == [] and saida["content_seo_queue"] == []
    assert saida["metrics"]["funnels"] == 0
    assert saida["metrics"]["google_ads_keywords"] > 0
    assert saida["cluster"]["main_keyword"] == "nicho"
    assert saida["funnel_prospector"]["codigo"] == orq.PROSPECTOR_SEM_MATERIAL
