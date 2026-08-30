from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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
    "customer_id": "customer-test",
    "nome": "Search de prova",
    "moeda": None,
}


def coleta(estado: str = "com_dados") -> Dict[str, Any]:
    return {
        "coleta_id": "coleta-01",
        "estado": estado,
        "customer_id": "customer-test",
        "volc_campaign_id": "cmp.search:01",
        "campaign_id": "external-test",
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
        "recurso_externo": "campaign-resource",
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
        "nome": "impressions", "estado_valor": "medido", "valor_numerico": 0,
        "valor_texto": None, "unidade": None, "moeda": None,
    },
    {
        "nome": "daily_budget_micros", "estado_valor": "medido",
        "valor_numerico": 10_000_000, "valor_texto": None,
        "unidade": "micros", "moeda": "BRL",
    },
    {
        "nome": "search_budget_lost_impression_share", "estado_valor": "ausente",
        "valor_numerico": None, "valor_texto": None, "unidade": None, "moeda": None,
    },
    {
        "nome": "campo_futuro_secreto", "estado_valor": "medido",
        "valor_numerico": 999, "valor_texto": "NAO_PODE_VAZAR",
        "unidade": None, "moeda": None,
    },
]


def test_contraprova_envelope_bate_com_frontend():
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta(), itens=ITENS, metricas=METRICAS),
        agora=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
    ))
    dados = _dump(resposta)
    assert set(dados) == {"versao", "diagnostico", "propostas"}
    assert dados["versao"] == 1
    assert dados["diagnostico"]["volc_campaign_id"] == "cmp.search:01"
    assert len(dados["diagnostico"]["degraus"]) == 9
    assert dados["propostas"] == {
        "versao": 1, "volc_campaign_id": "cmp.search:01",
        "propostas": [],
        "leitura": {"lido_em": "2026-08-28T12:00:00+00:00", "idade_s": 86400},
    }


def test_contraprova_campanha_existente_sem_coleta_nao_vira_404():
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01", Repo(campanha=CAMPANHA),
    ))
    dados = _dump(resposta)
    assert dados["diagnostico"]["janela"] == "coleta ainda não executada"
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
    ))
    dados = _dump(resposta)
    assert all(d["estado"] == "nao_apurado" for d in dados["diagnostico"]["degraus"])
    assert trecho in dados["diagnostico"]["degraus"][0]["impedimento"]
    if estado == "falhou":
        assert dados["propostas"]["leitura"] is None
        assert dados["diagnostico"]["leitura"] is None


def test_contraprova_estado_parcial_permanece_parcial_e_conservador():
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta("parcial"), itens=ITENS[:1], metricas=METRICAS[:1]),
    ))
    dados = _dump(resposta)["diagnostico"]
    assert dados["parcial"] is True
    assert any(d["estado"] == "nao_apurado" for d in dados["degraus"])
    # Ausência de ads/keywords numa coleta parcial não afirma zero observado.
    assert next(d for d in dados["degraus"] if d["eixo"] == "anuncio")["estado"] == "nao_apurado"


def test_contraprova_zero_medido_nao_vira_ausente():
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta(), itens=ITENS, metricas=METRICAS),
    ))
    leilao = next(d for d in _dump(resposta)["diagnostico"]["degraus"] if d["eixo"] == "leilao")
    assert leilao["estado"] == "limita"
    assert leilao["evidencias"][0]["valor"] == "0"
    assert "zero impressões" in leilao["frase"]


def test_contraprova_raw_fora_da_allowlist_nao_vaza():
    resposta = asyncio.run(obter_diagnostico_campanha(
        "cmp.search:01",
        Repo(campanha=CAMPANHA, coleta=coleta(), itens=ITENS, metricas=METRICAS),
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
