"""O revisor da arquitetura aponta; ele não achata o tom.

## O que mudou

O critério 4 do revisor dizia: "Reescreva qualquer trecho que viole essas
proibições para um tom informacional e útil". Era a segunda porta, depois do
arquiteto, por onde o funil perdia voz — e em silêncio: as mudanças iam só para
log `debug`.

Agora:
- o prompt manda APONTAR em `achados` (trecho, motivo, evidência) promessa sem
  sustentação, sem reescrever tom, ângulo ou voz;
- o CÓDIGO garante o que é objetivamente verificável: `funnel_strategy.tone_voice`
  do arquiteto não é trocado pelo revisor (a proposta vira achado), e tom/avatar
  nunca somem do plano;
- `changes` e `achados` voltam no resultado, para serem gravados em
  `funnel_architecture.revisao_arquitetura`.

Cliente do LLM falso em todos os testes.
"""
from __future__ import annotations

import os
import sys

for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"
os.environ["PAUTADOR_KW_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from typing import Any, Dict

from app.agents.base import AgentContext
from app.agents.funnel_pro.reviewer import REVIEWER_SYSTEM_PROMPT, FunnelReviewer
from app.config import Settings, get_settings
from app.llm.mock import MockEngine

get_settings.cache_clear()

TOM = "Jornalismo de serviço: direto, concreto, com o ganho do leitor à frente"
AVATAR = "Quem busca curso gratuito e não sabe onde o Senac do estado publica"


def _ctx() -> AgentContext:
    s = Settings(gemini_api_key="chave-falsa", google_api_key=None, supabase_url=None,
                 supabase_service_role_key=None)
    return AgentContext(settings=s, engine=MockEngine(), grounding=None)


def _arquitetura() -> Dict[str, Any]:
    return {
        "funnel_strategy": {"avatar_summary": AVATAR, "tone_voice": TOM, "total_pages": 1},
        "pages": [{
            "page_number": 1, "page_type": "LANDING PAGE", "h1_title": "Cursos gratuitos do Senac",
            "slug": "cursos-senac", "intro_section": ["Abrir com quem tem direito"],
            "emotional_objective": "Mostrar o caminho", "main_content_structure": ["H2: Quem tem direito"],
            "closing_section": ["Levar ao guia do estado"],
            "hook_to_next_page": "Ver cursos gratuitos", "next_page_slug": "",
            "target_keywords": ["cursos senac"],
        }],
    }


class _Cliente:
    def __init__(self, resposta: Any = None, erro: Exception | None = None) -> None:
        self.resposta = resposta
        self.erro = erro
        self.recebido: Dict[str, str] = {}

    async def complete_json(self, system: str, user: str) -> Any:
        self.recebido = {"system": system, "user": user}
        if self.erro:
            raise self.erro
        return self.resposta


def _revisar(monkeypatch, cliente: _Cliente) -> Dict[str, Any]:
    monkeypatch.setattr(FunnelReviewer, "_gemini", lambda self: cliente)
    return asyncio.run(FunnelReviewer(_ctx()).review(
        _arquitetura(), entity_facts={"official_source": "Senac"}, forced_language="pt-BR"))


# ── o prompt ───────────────────────────────────────────────────────────────

def test_o_prompt_nao_manda_reescrever_para_tom_informacional():
    p = REVIEWER_SYSTEM_PROMPT
    assert "Reescreva qualquer trecho" not in p
    assert "tom informacional e útil" not in p
    # a palavra isolada deixa de ser proibição: avalia-se a promessa
    assert 'a palavra "garantido"' not in p


def test_o_prompt_manda_apontar_em_achados_com_evidencia():
    p = REVIEWER_SYSTEM_PROMPT
    assert '"achados"' in p                      # está no schema de saída
    assert "achados" in p.split("<output_rules>")[0]   # e no critério, não só no schema
    assert "evidência" in p.lower()
    assert "tone_voice" in p


# ── o código ───────────────────────────────────────────────────────────────

def test_o_revisor_nao_troca_o_tom_do_arquiteto(monkeypatch):
    arq = _arquitetura()
    arq["funnel_strategy"]["tone_voice"] = "Informacional e útil"
    r = _revisar(monkeypatch, _Cliente({**arq, "changes": ["Tom suavizado"]}))

    assert r["funnel_strategy"]["tone_voice"] == TOM
    achado = next(a for a in r["achados"] if a.get("campo") == "funnel_strategy.tone_voice")
    assert achado["proposta"] == "Informacional e útil"
    assert achado["trecho"] == TOM
    # o que ele disse ter feito continua registrado, para a tela e para o motor
    assert r["changes"] == ["Tom suavizado"]


def test_tom_e_avatar_nunca_somem_do_plano(monkeypatch):
    arq = _arquitetura()
    arq["funnel_strategy"] = {"avatar_summary": "", "total_pages": 1}   # sumiu o tom, zerou o avatar
    r = _revisar(monkeypatch, _Cliente({**arq, "changes": []}))

    assert r["funnel_strategy"]["tone_voice"] == TOM
    assert r["funnel_strategy"]["avatar_summary"] == AVATAR


def test_o_revisor_pode_refinar_o_avatar(monkeypatch):
    """Corrigir o público com base nos fatos (país, processo) continua valendo —
    o que o código protege é a VOZ, não o conteúdo factual."""
    arq = _arquitetura()
    arq["funnel_strategy"]["avatar_summary"] = AVATAR + " (oferta varia por estado)"
    r = _revisar(monkeypatch, _Cliente({**arq, "changes": ["Avatar precisado"]}))
    assert r["funnel_strategy"]["avatar_summary"] == AVATAR + " (oferta varia por estado)"


def test_achados_do_llm_sao_normalizados(monkeypatch):
    resposta = {
        **_arquitetura(), "changes": [],
        "achados": [
            {"pagina": 1, "campo": "hook_to_next_page", "trecho": "Ver cursos gratuitos",
             "motivo": "o destino precisa mostrar a lista", "evidencia": "editorial.useful_delivery",
             "lixo": "descartado"},
            "prazo de 30 dias sem fonte",
            {"pagina": 2},                      # sem trecho nem motivo: não é achado
            42,
        ],
    }
    r = _revisar(monkeypatch, _Cliente(resposta))

    assert r["achados"] == [
        {"pagina": 1, "campo": "hook_to_next_page", "trecho": "Ver cursos gratuitos",
         "motivo": "o destino precisa mostrar a lista", "evidencia": "editorial.useful_delivery"},
        {"motivo": "prazo de 30 dias sem fonte"},
    ]
    assert r["estado"] == "revisado"


def test_revisao_sem_achados_devolve_lista_vazia(monkeypatch):
    r = _revisar(monkeypatch, _Cliente({**_arquitetura(), "changes": []}))
    assert r["achados"] == []
    assert r["estado"] == "revisado"


def test_falha_do_llm_diz_que_nao_revisou_sem_vazar_a_excecao(monkeypatch):
    erro = RuntimeError("Client error '400' for url 'https://x/v1beta/m:generate?key=SEGREDO-XYZ'")
    r = _revisar(monkeypatch, _Cliente(erro=erro))

    assert r["estado"] == "nao_revisado"
    assert r["changes"] == [] and r["achados"] == []
    assert r["funnel_strategy"]["tone_voice"] == TOM          # fail-open: o original
    bruto = json.dumps({k: r[k] for k in ("estado", "motivo", "changes", "achados")},
                       ensure_ascii=False)
    assert "SEGREDO-XYZ" not in bruto
    assert "RuntimeError" in r["motivo"]


def test_saida_inutilizavel_diz_que_nao_revisou(monkeypatch):
    r = _revisar(monkeypatch, _Cliente({"nada": True}))
    assert r["estado"] == "nao_revisado"
    assert r["motivo"]


def test_sem_chave_diz_que_nao_revisou():
    s = Settings(gemini_api_key=None, google_api_key=None, supabase_url=None,
                 supabase_service_role_key=None)
    ctx = AgentContext(settings=s, engine=MockEngine(), grounding=None)
    r = asyncio.run(FunnelReviewer(ctx).review(
        _arquitetura(), entity_facts={}, forced_language="pt-BR"))
    assert r["estado"] == "nao_revisado"
    assert r["funnel_strategy"]["tone_voice"] == TOM
