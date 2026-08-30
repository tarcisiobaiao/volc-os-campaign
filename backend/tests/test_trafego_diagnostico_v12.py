from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from app.trafego.diagnostico_persistido import (
    CampanhaNaoEncontradaError,
    IdentificadorInvalidoError,
    ServicoIndisponivelError,
    SupabaseRepositorioDiagnostico,
    obter_diagnostico_campanha,
    validar_volc_campaign_id,
)
from app.trafego import inventario


def _dump(modelo: Any) -> Dict[str, Any]:
    return modelo.model_dump() if hasattr(modelo, "model_dump") else modelo.dict()


class Repo:
    def __init__(
        self,
        *,
        campanha: Optional[Dict[str, Any]] = None,
        coleta: Optional[Dict[str, Any]] = None,
        itens: Optional[List[Dict[str, Any]]] = None,
        metricas: Optional[List[Dict[str, Any]]] = None,
        falhar: Optional[str] = None,
    ) -> None:
        self._campanha = campanha
        self._coleta = coleta
        self._itens = itens or []
        self._metricas = metricas or []
        self.falhar = falhar

    async def campanha(self, _id: str):
        if self.falhar == "campanha":
            raise ServicoIndisponivelError("db")
        return self._campanha

    async def coleta(self, _id: str):
        if self.falhar == "coleta":
            raise ServicoIndisponivelError("db")
        return self._coleta

    async def itens(self, _id: str):
        if self.falhar == "itens":
            raise ServicoIndisponivelError("db")
        return self._itens

    async def metricas(self, _id: str):
        if self.falhar == "metricas":
            raise ServicoIndisponivelError("db")
        return self._metricas


CAMPANHA = {
    "volc_campaign_id": "cmp.search:01",
    "customer_id": "8017851692",
    "campaign_id": "24156373085",
    "nome": "Search de prova",
    "moeda": None,
}
AGORA_RECENTE = datetime(2026, 8, 28, 12, 10, tzinfo=timezone.utc)


def coleta(estado: str = "com_dados") -> Dict[str, Any]:
    return {
        "coleta_id": "coleta-01",
        "estado": estado,
        "customer_id": "8017851692",
        "volc_campaign_id": "cmp.search:01",
        "campaign_id": "24156373085",
        "janela_inicio": "2026-08-20",
        "janela_fim": "2026-08-27",
        "coletada_em": "2026-08-28T12:00:00Z",
        "quantidade": 3,
        "erro_codigo": "COLLECT_ERROR" if estado == "falhou" else None,
        "erro_classe": None,
    }


ITENS = [
    {
        "tipo_item": "campaign",
        "recurso_externo": "24156373085",
        "payload": {
            "campaign": {
                "status": "ENABLED",
                "primary_status": "ELIGIBLE",
                "serving_status": "SERVING",
                "primary_status_reasons": [],
                "secret_token": "NAO_PODE_VAZAR",
            },
            "url_final": "https://segredo.invalid",
        },
    },
    {
        "tipo_item": "keyword",
        "recurso_externo": "keyword-resource",
        "payload": {
            "ad_group_criterion": {
                "primary_status": "ELIGIBLE",
                "keyword": {"text": "texto fora da allowlist", "match_type": "EXACT"},
            },
        },
    },
    {
        "tipo_item": "ad",
        "recurso_externo": "ad-resource",
        "payload": {"ad_group_ad": {"status": "ENABLED", "primary_status": "ELIGIBLE"}},
    },
]

METRICAS = [
    {
        "recurso_tipo": "campaign", "recurso_externo": "24156373085",
        "nome": "impressions", "estado_valor": "medido", "valor_numerico": 0,
        "valor_texto": None, "unidade": None, "moeda": None,
    },
    {
        "recurso_tipo": "campaign", "recurso_externo": "24156373085",
        "nome": "daily_budget_micros", "estado_valor": "medido",
        "valor_numerico": 10_000_000, "valor_texto": None,
        "unidade": "micros", "moeda": "BRL",
    },
    {
        "recurso_tipo": "campaign", "recurso_externo": "24156373085",
        "nome": "search_budget_lost_impression_share", "estado_valor": "ausente",
        "valor_numerico": None, "valor_texto": None, "unidade": None, "moeda": None,
    },
    {
        "recurso_tipo": "campaign", "recurso_externo": "24156373085",
        "nome": "campo_futuro_secreto", "estado_valor": "medido",
        "valor_numerico": 999, "valor_texto": "NAO_PODE_VAZAR",
        "unidade": None, "moeda": None,
    },
]


def test_contraprova_envelope_bate_com_frontend():
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta(), itens=ITENS, metricas=METRICAS),
        agora=AGORA_RECENTE,
    ))
    dados = _dump(resposta)
    assert set(dados) == {"versao", "diagnostico", "propostas"}
    assert dados["versao"] == 1
    assert dados["diagnostico"]["volc_campaign_id"] == "cmp.search:01"
    assert dados["diagnostico"]["estado_coleta"] == "com_dados"
    assert dados["diagnostico"]["frescor"] == "recente"
    assert len(dados["diagnostico"]["degraus"]) == 9
    assert dados["propostas"] == {
        "versao": 1, "volc_campaign_id": "cmp.search:01",
        "propostas": [],
        "leitura": {"lido_em": "2026-08-28T12:00:00+00:00", "idade_s": 600},
    }


def test_contraprova_campanha_existente_sem_coleta_nao_vira_404():
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01", Repo(campanha=CAMPANHA),
    ))
    dados = _dump(resposta)
    assert dados["diagnostico"]["janela"] == "coleta ainda não executada"
    assert dados["diagnostico"]["estado_coleta"] is None
    assert dados["diagnostico"]["frescor"] == "nao_apurado"
    assert dados["diagnostico"]["leitura"] is None
    assert all(d["estado"] == "nao_apurado" for d in dados["diagnostico"]["degraus"])
    assert "coleta ainda não executada" in dados["diagnostico"]["degraus"][0]["impedimento"]


def test_contraprova_campanha_inexistente_e_404_sem_consultar_coleta():
    with pytest.raises(CampanhaNaoEncontradaError):
        asyncio.run(obter_diagnostico_campanha("cmp.search:01", Repo()))


def test_contraprova_falha_do_banco_nao_vira_404_ou_ausencia():
    with pytest.raises(ServicoIndisponivelError):
        asyncio.run(obter_diagnostico_campanha(
            "cmp.search:01", Repo(campanha=CAMPANHA, falhar="coleta"),
        ))


@pytest.mark.parametrize(
    "estado,trecho",
    [
        ("vazio_confirmado", "não devolveu a linha-base"),
        ("inelegivel", "inelegível"),
        ("nao_suportado", "não suportado"),
        ("falhou", "terminou em falhou"),
    ],
)
def test_contraprova_estados_terminais_nao_viram_sucesso(estado: str, trecho: str):
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01", Repo(campanha=CAMPANHA, coleta=coleta(estado)),
        agora=AGORA_RECENTE,
    ))
    dados = _dump(resposta)
    assert dados["diagnostico"]["estado_coleta"] == estado
    assert all(d["estado"] == "nao_apurado" for d in dados["diagnostico"]["degraus"])
    assert trecho in dados["diagnostico"]["degraus"][0]["impedimento"]
    if estado == "falhou":
        assert dados["propostas"]["leitura"] is None
        assert dados["diagnostico"]["leitura"] is None


def test_contraprova_estado_parcial_permanece_parcial_e_conservador():
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta("parcial"), itens=ITENS[:1], metricas=METRICAS[:1]),
        agora=AGORA_RECENTE,
    ))
    dados = _dump(resposta)["diagnostico"]
    assert dados["estado_coleta"] == "parcial"
    assert dados["parcial"] is True
    assert any(d["estado"] == "nao_apurado" for d in dados["degraus"])
    # Ausência de ads/keywords numa coleta parcial não afirma zero observado.
    assert next(d for d in dados["degraus"] if d["eixo"] == "anuncio")["estado"] == "nao_apurado"


@pytest.mark.parametrize(
    "estado",
    [
        "com_dados", "vazio_confirmado", "parcial", "inelegivel",
        "nao_suportado", "falhou",
    ],
)
def test_contraprova_os_seis_estados_v12_atravessam_o_json(estado: str):
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta(estado)),
        agora=AGORA_RECENTE,
    ))
    assert _dump(resposta)["diagnostico"]["estado_coleta"] == estado


def test_contraprova_zero_medido_nao_vira_ausente():
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta(), itens=ITENS, metricas=METRICAS),
        agora=AGORA_RECENTE,
    ))
    leilao = next(d for d in _dump(resposta)["diagnostico"]["degraus"] if d["eixo"] == "leilao")
    assert leilao["estado"] == "limita"
    assert leilao["evidencias"][0]["valor"] == "0"
    assert "zero impressões" in leilao["frase"]


def test_contraprova_null_de_estado_da_campanha_nunca_vira_ok():
    item_parcial = {
        "tipo_item": "campaign",
        "recurso_externo": "24156373085",
        "payload": {"campaign": {"status": "ENABLED"}},
    }
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta("parcial"), itens=[item_parcial]),
        agora=AGORA_RECENTE,
    ))
    campanha = next(
        d for d in _dump(resposta)["diagnostico"]["degraus"]
        if d["eixo"] == "campanha"
    )
    assert campanha["estado"] == "nao_apurado"
    assert any(e["valor"] is None for e in campanha["evidencias"])


def test_contraprova_stale_e_tipado_e_falha_fechado():
    agora_velho = (
        datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
        + timedelta(seconds=inventario.SEGUNDOS_PARA_VELHO + 1)
    )
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta(), itens=ITENS, metricas=METRICAS),
        agora=agora_velho,
    ))
    dados = _dump(resposta)
    assert dados["diagnostico"]["estado_coleta"] == "com_dados"
    assert dados["diagnostico"]["frescor"] == "velho"
    assert all(d["estado"] == "nao_apurado" for d in dados["diagnostico"]["degraus"])
    assert dados["diagnostico"]["parcial"] is True
    assert dados["propostas"]["leitura"] is None


def test_contraprova_entidade_pausada_nao_bloqueia_outra_elegivel():
    mistos = [
        ITENS[0],
        {
            "tipo_item": "ad",
            "payload": {"ad_group_ad": {"status": "PAUSED", "primary_status": "NOT_ELIGIBLE"}},
        },
        {
            "tipo_item": "ad",
            "payload": {"ad_group_ad": {"status": "ENABLED", "primary_status": "ELIGIBLE"}},
        },
        {
            "tipo_item": "keyword",
            "payload": {"ad_group_criterion": {"primary_status": "PAUSED"}},
        },
        {
            "tipo_item": "keyword",
            "payload": {"ad_group_criterion": {"primary_status": "ELIGIBLE"}},
        },
    ]
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta(), itens=mistos),
        agora=AGORA_RECENTE,
    ))
    degraus = {d["eixo"]: d for d in _dump(resposta)["diagnostico"]["degraus"]}
    assert degraus["anuncio"]["estado"] == "ok"
    assert degraus["keyword"]["estado"] == "ok"


@pytest.mark.parametrize(
    "alteracao",
    [
        {"recurso_tipo": "keyword"},
        {"recurso_externo": "99999999999"},
        {"valor_numerico": None, "valor_texto": "NAO_PODE_VAZAR"},
    ],
)
def test_contraprova_metrica_allowlisted_exige_tipo_grao_e_recurso(alteracao):
    metrica = {**METRICAS[0], **alteracao}
    with pytest.raises(ServicoIndisponivelError):
        asyncio.run(obter_diagnostico_campanha(
            "cmp.search:01",
            Repo(campanha=CAMPANHA, coleta=coleta(), itens=ITENS, metricas=[metrica]),
            agora=AGORA_RECENTE,
        ))


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("volc_campaign_id", "cmp.search:outra"),
        ("customer_id", "5478096539"),
        ("campaign_id", "24155134757"),
    ],
)
def test_contraprova_identidade_da_coleta_precisa_bater_com_a_campanha(campo, valor):
    coleta_inconsistente = {**coleta(), campo: valor}
    with pytest.raises(ServicoIndisponivelError):
        asyncio.run(obter_diagnostico_campanha(
            "cmp.search:01",
            Repo(campanha=CAMPANHA, coleta=coleta_inconsistente),
            agora=AGORA_RECENTE,
        ))


def test_contraprova_item_de_campanha_precisa_bater_com_a_identidade_canonica():
    item_inconsistente = {**ITENS[0], "recurso_externo": "24155134757"}
    with pytest.raises(ServicoIndisponivelError):
        asyncio.run(obter_diagnostico_campanha(
            "cmp.search:01",
            Repo(campanha=CAMPANHA, coleta=coleta(), itens=[item_inconsistente]),
            agora=AGORA_RECENTE,
        ))


def test_contraprova_metrica_fora_da_allowlist_nao_pode_injetar_moeda():
    metrica_bruta = {
        "recurso_tipo": "keyword", "recurso_externo": "segredo",
        "nome": "campo_futuro_secreto", "estado_valor": "medido",
        "valor_numerico": None, "valor_texto": "NAO_PODE_VAZAR",
        "unidade": None, "moeda": "USD",
    }
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta(), itens=ITENS, metricas=[metrica_bruta]),
        agora=AGORA_RECENTE,
    ))
    dados = _dump(resposta)
    assert dados["diagnostico"]["moeda"] is None
    assert "NAO_PODE_VAZAR" not in json.dumps(dados, ensure_ascii=False)


def test_contraprova_raw_fora_da_allowlist_nao_vaza():
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta(), itens=ITENS, metricas=METRICAS),
        agora=AGORA_RECENTE,
    ))
    serializado = json.dumps(_dump(resposta), ensure_ascii=False)
    assert "NAO_PODE_VAZAR" not in serializado
    assert "segredo.invalid" not in serializado
    assert "texto fora da allowlist" not in serializado
    assert "campo_futuro_secreto" not in serializado


def test_contraprova_id_usa_validacao_canonica():
    assert validar_volc_campaign_id("A.b:c-1_2") == "A.b:c-1_2"
    with pytest.raises(IdentificadorInvalidoError):
        validar_volc_campaign_id("id/com/barra")
    with pytest.raises(IdentificadorInvalidoError):
        validar_volc_campaign_id("x" * 121)


def test_contraprova_repositorio_consulta_so_relacoes_reais_v12():
    chamadas: List[tuple[str, Dict[str, Any]]] = []

    class Supa:
        enabled = True

        async def select(self, tabela: str, params: Dict[str, Any]):
            chamadas.append((tabela, params))
            if tabela == "trafego_inventario_campanha":
                return [CAMPANHA]
            if tabela == "trafego_google_inteligencia_coleta":
                return [coleta()]
            return []

    repo = SupabaseRepositorioDiagnostico(Supa())
    asyncio.run(repo.campanha("cmp.search:01"))
    asyncio.run(repo.coleta("cmp.search:01"))
    asyncio.run(repo.itens("coleta-01"))
    asyncio.run(repo.metricas("coleta-01"))
    assert [c[0] for c in chamadas] == [
        "trafego_inventario_campanha",
        "trafego_google_inteligencia_coleta",
        "trafego_google_inteligencia_item",
        "trafego_google_inteligencia_metrica",
    ]
    assert all("select" in params and "*" not in params["select"] for _, params in chamadas)


def test_contraprova_erro_postgrest_nao_e_engolido():
    class Supa:
        enabled = True

        async def select(self, _tabela: str, _params: Dict[str, Any]):
            raise RuntimeError("db offline")

    with pytest.raises(ServicoIndisponivelError):
        asyncio.run(SupabaseRepositorioDiagnostico(Supa()).coleta("cmp.search:01"))


def test_contraprova_request_nao_importa_nem_chama_google_ads():
    raiz = Path(__file__).resolve().parents[1]
    fonte = (raiz / "app/trafego/diagnostico_persistido.py").read_text()
    router = (raiz / "app/routers/trafego_diagnostico.py").read_text()
    codigo = fonte + router
    assert "from google" not in codigo
    assert "import google" not in codigo
    assert ".mutate(" not in codigo
    assert "validate_only" not in codigo
    assert "trafego_campanha_diagnosticos" not in codigo
    assert "trafego_campanhas_inventario" not in codigo
