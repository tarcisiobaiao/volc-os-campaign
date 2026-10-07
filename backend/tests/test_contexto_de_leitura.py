"""A leitura medida na validação chega ao arquiteto como DADO, e fica gravada.

## O que mudou, e por quê

Antes, a tensão da validação descia colada no fim do direcionamento do admin,
como um bloco de INSTRUÇÃO:

    "Mantenha o tom informacional e útil que este briefing já pede — a
     observação existe para você acertar o ângulo, nunca para aumentar a
     temperatura do texto."

Dois defeitos num lugar só: (1) a frase mandava o arquiteto achatar o texto por
regra, e não por fato; (2) ia pelo canal do admin, que é cortado em 4.000
caracteres — uma direção longa cortava a observação no meio ou inteira.

Agora ela é dado: uma linha em `<supporting_data>`, e o mesmo conteúdo gravado
em `funnel_architecture.contexto_de_leitura` (formato do contrato entre
trilhas), para o motor levar adiante sem reinterpretar.

Nada aqui chama LLM: o cliente do arquiteto e o do revisor são falsos.
"""
from __future__ import annotations

import os
import sys

# offline/mock ANTES de importar o app (padrão dos demais testes do projeto)
for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"
os.environ["PAUTADOR_KW_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from typing import Any, Dict, List, Optional

import pytest

from app.agents.base import AgentContext
from app.agents.funnel_pro.orchestrator import FunnelProOrchestrator
from app.agents.funnel_pro.reviewer import FunnelReviewer
from app.config import Settings, get_settings
from app.entities import orchestrator as ent_orq
from app.entities.orchestrator import EntityFunnelOrchestrator, contexto_de_leitura
from app.llm.mock import MockEngine
from app.motor_pautas.psique import TENSOES

get_settings.cache_clear()

FRASE_ASCENSAO = TENSOES["ascensao"]["pergunta"]
INSTRUCAO_ANTIGA = "nunca para aumentar a temperatura"


def _ctx() -> AgentContext:
    s = Settings(gemini_api_key=None, google_api_key=None, supabase_url=None,
                 supabase_service_role_key=None)
    return AgentContext(settings=s, engine=MockEngine(), grounding=None)


def _validacao(tensao: str = "ascensao") -> Dict[str, Any]:
    """O formato que a coluna de validação grava no card (`validacao.ficha`)."""
    return {
        "ficha": {
            "n_perguntas": 4,
            "tensao_dominante": tensao,
            "distribuicao_de_tensao": {tensao: 3} if tensao != "nenhuma" else {},
            "intensidade": 0.78,
            "perguntas": [
                {"pergunta": "Quem tem direito ao curso gratuito do Senac?",
                 "resposta_literal": "Pessoas com renda familiar de até 2 salários mínimos."},
                {"pergunta": "Como me inscrever no Senac?", "resposta_literal": ""},
                {"pergunta": "   ", "resposta_literal": "descartada: pergunta vazia"},
            ],
        }
    }


def _entity() -> Dict[str, Any]:
    return {
        "id": 501, "run_id": "run-1", "canonical_name": "Senac",
        "full_name": "Serviço Nacional de Aprendizagem Comercial",
        "description": "Rede de educação profissional com oferta por estado.",
        "aliases": ["senac cursos gratuitos"], "related_systems": ["PSG"],
        "official_source": "Senac", "country": "Brasil", "country_code": "BR",
        "language": None, "native_language": None,
    }


def _arquitetura_do_llm() -> Dict[str, Any]:
    return {
        "funnel_strategy": {
            "avatar_summary": "Quem busca curso gratuito e não sabe onde o Senac do estado publica",
            "tone_voice": "Jornalismo de serviço: direto, concreto, com o ganho do leitor à frente",
            "total_pages": 2,
        },
        "pages": [
            {"page_number": 1, "page_type": "LANDING PAGE", "h1_title": "Cursos gratuitos do Senac",
             "slug": "cursos-senac", "intro_section": ["Abrir com quem tem direito"],
             "emotional_objective": "Mostrar o caminho", "main_content_structure": ["H2: Quem tem direito"],
             "closing_section": ["Levar ao guia do estado"], "hook_to_next_page": "Ver como achar a turma no seu estado",
             "next_page_slug": "senac-por-estado", "target_keywords": ["cursos senac"],
             "editorial": {"reader_question": "O Senac tem curso de graça?", "useful_delivery": "Quem tem direito",
                           "cta_label": "Ver cursos gratuitos",
                           "links": [{"target": "senac-por-estado", "reason": "a oferta é estadual"}]}},
            {"page_number": 2, "page_type": "HUB", "h1_title": "Senac por estado",
             "slug": "senac-por-estado", "intro_section": ["Explicar a oferta estadual"],
             "emotional_objective": "Orientar", "main_content_structure": ["H2: Onde cada estado publica"],
             "closing_section": ["Canal oficial"], "hook_to_next_page": "", "next_page_slug": "",
             "target_keywords": ["senac por estado"],
             "editorial": {"reader_question": "Onde vejo as vagas do meu estado?",
                           "useful_delivery": "Onde cada regional publica", "cta_label": "Ver a oferta do seu estado",
                           "links": []}},
        ],
    }


class _ClienteDoArquiteto:
    """Registra o que o arquiteto recebeu e devolve uma arquitetura válida."""

    def __init__(self) -> None:
        self.chamadas: List[Dict[str, str]] = []

    async def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        self.chamadas.append({"system": system, "user": user})
        return _arquitetura_do_llm()


def _bloco(texto: str, tag: str) -> str:
    ini = texto.index(f"<{tag}>") + len(tag) + 2
    return texto[ini:texto.index(f"</{tag}>")]


async def _revisor_que_devolve_igual(self, architect_output, *, entity_facts, forced_language):
    return {"funnel_strategy": architect_output.get("funnel_strategy") or {},
            "pages": architect_output.get("pages") or [], "changes": []}


# ── o formato do dado ──────────────────────────────────────────────────────

def test_contexto_de_leitura_sai_no_formato_do_contrato():
    ctx = contexto_de_leitura(_validacao())
    assert ctx == {
        "perguntas_paa": ["Quem tem direito ao curso gratuito do Senac?",
                          "Como me inscrever no Senac?"],
        "tensao": {"frase": FRASE_ASCENSAO, "evidencia": "validacao:3/4"},
    }


def test_a_intensidade_nao_viaja():
    """PRIOR COM DÍVIDA: veio de um desfecho contaminado por `spend`. Um número
    desses no prompt vira régua de ênfase sem ter sido medido para isso."""
    bruto = json.dumps(contexto_de_leitura(_validacao()), ensure_ascii=False)
    assert "0.78" not in bruto and "intensidade" not in bruto


def test_sem_validacao_nao_ha_contexto():
    assert contexto_de_leitura(None) is None
    assert contexto_de_leitura({}) is None
    assert contexto_de_leitura({"ficha": {}}) is None


def test_entidade_fria_leva_so_as_perguntas():
    """Tensão `nenhuma` é informação, não falha: as perguntas reais seguem."""
    ctx = contexto_de_leitura(_validacao("nenhuma"))
    assert ctx == {"perguntas_paa": ["Quem tem direito ao curso gratuito do Senac?",
                                     "Como me inscrever no Senac?"]}


def test_tensao_desconhecida_nao_inventa_frase():
    ctx = contexto_de_leitura(_validacao("tensao_que_nao_existe"))
    assert "tensao" not in ctx


# ── o arquiteto recebe DADO, não instrução ─────────────────────────────────

def _rodar_arquiteto(monkeypatch, *, admin_direction: Optional[str] = None,
                     validacao: Optional[Dict[str, Any]] = None):
    cliente = _ClienteDoArquiteto()
    monkeypatch.setattr(FunnelProOrchestrator, "_gemini", lambda self: cliente)
    monkeypatch.setattr(FunnelReviewer, "review", _revisor_que_devolve_igual)
    resultado = asyncio.run(EntityFunnelOrchestrator(_ctx()).run(
        _entity(), [], [{"query": "cursos gratuitos senac"}],
        admin_direction=admin_direction, validacao=validacao))
    assert len(cliente.chamadas) == 1
    return cliente.chamadas[0], resultado


def test_o_arquiteto_recebe_a_tensao_como_dado(monkeypatch):
    chamada, _ = _rodar_arquiteto(monkeypatch, validacao=_validacao())
    user = chamada["user"]

    dados = _bloco(user, "supporting_data")
    assert FRASE_ASCENSAO in dados
    assert "validacao:3/4" in dados

    # a instrução de achatar sumiu do prompt inteiro
    assert INSTRUCAO_ANTIGA not in chamada["system"] + user
    assert "observacao_de_leitura" not in user
    # sem texto do admin, não nasce bloco de admin só para carregar a tensão
    assert "DIRECIONAMENTO DO ADMIN" not in user


def test_as_perguntas_reais_seguem_no_canal_de_perguntas(monkeypatch):
    chamada, _ = _rodar_arquiteto(monkeypatch, validacao=_validacao())
    perguntas = _bloco(chamada["user"], "user_questions")
    assert "Quem tem direito ao curso gratuito do Senac?" in perguntas


def test_a_direcao_do_admin_chega_intacta(monkeypatch):
    """O canal do admin volta a ser só do admin: a tensão não disputa mais os
    4.000 caracteres dele."""
    texto = "Recorte para quem trabalha de dia e procura curso noturno."
    chamada, _ = _rodar_arquiteto(monkeypatch, admin_direction=texto, validacao=_validacao())
    admin = chamada["user"][chamada["user"].index("<DIRECIONAMENTO DO ADMIN>"):]
    assert texto in admin
    assert FRASE_ASCENSAO not in admin


def test_sem_validacao_o_prompt_nao_ganha_linha_de_leitura(monkeypatch):
    chamada, resultado = _rodar_arquiteto(monkeypatch, validacao=None)
    assert "Tensão" not in _bloco(chamada["user"], "supporting_data")
    assert resultado.get("contexto_de_leitura") is None


def test_supporting_data_sem_contexto_fica_byte_a_byte_igual():
    """Card sem validação: o `<supporting_data>` é o mesmo de antes."""
    opp = {"reasoning": "R", "variations": ["a"], "expansion_hooks": ["h"]}
    esperado = ("- Contexto/descrição: R\n- Variações/aliases: a\n"
                "- Ganchos/dores/sistemas relacionados: h")
    assert FunnelProOrchestrator._supporting_data(None, opp) == esperado
    so_perguntas = {**opp, "contexto_de_leitura": {"perguntas_paa": ["x?"]}}
    assert FunnelProOrchestrator._supporting_data(None, so_perguntas) == esperado


def test_o_resultado_leva_o_contexto_para_ser_gravado(monkeypatch):
    _, resultado = _rodar_arquiteto(monkeypatch, validacao=_validacao())
    assert resultado["contexto_de_leitura"] == contexto_de_leitura(_validacao())


# ── o que fica gravado no card ─────────────────────────────────────────────

class _SupaDoFunil:
    """O mínimo que a rota de funil usa, registrando o que ela grava."""

    enabled = True

    def __init__(self, validacao: Optional[Dict[str, Any]]) -> None:
        self.validacao = validacao
        self.atualizacoes: List[Dict[str, Any]] = []

    async def get_entity_opportunity(self, opp_id):
        return {"id": opp_id, "entity_id": 501, "country_code": "BR",
                "insights": None, "validacao": self.validacao}

    async def get_entity(self, entity_id):
        return _entity()

    async def list_entity_cards(self, country_code):
        return [{"id": 42, "pains": [], "seed_queries": [{"query": "cursos gratuitos senac"}]}]

    async def insert_funnel_hypotheses(self, rows):
        return rows

    async def update_entity_opportunity(self, opp_id, values):
        self.atualizacoes.append(values)
        return values

    async def update_entity(self, entity_id, values):
        return values


def _rodar_rota(monkeypatch, *, revisor_cliente, validacao) -> Dict[str, Any]:
    from app.entities.schemas import EntityFunnelRequest
    from app.routers import entities as rota

    supa = _SupaDoFunil(validacao)
    monkeypatch.setattr(rota, "SupabaseService", lambda settings: supa)
    monkeypatch.setattr(rota, "_ctx", lambda engine, model: _ctx())
    monkeypatch.setattr(FunnelProOrchestrator, "_gemini", lambda self: _ClienteDoArquiteto())
    monkeypatch.setattr(FunnelReviewer, "_gemini", lambda self: revisor_cliente)

    resposta = asyncio.run(rota.entity_funnel(42, EntityFunnelRequest(persist=True)))
    assert resposta.persisted is True
    gravado = [a for a in supa.atualizacoes if "funnel_architecture" in a]
    assert gravado, "a rota não gravou a arquitetura"
    return gravado[-1]["funnel_architecture"]


class _RevisorQueReescreveTom:
    """Um revisor como o antigo: corrige idioma E achata o tom."""

    async def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        arq = json.loads(_bloco(user, "funil_arquitetado"))
        fs = dict(arq["funnel_strategy"])
        fs["tone_voice"] = "Informacional e útil"
        return {
            "funnel_strategy": fs,
            "pages": arq["pages"],
            "changes": ["Traduzido intro_section da P2 para pt-BR"],
            "achados": [{"pagina": 1, "campo": "hook_to_next_page",
                         "trecho": "Ver como achar a turma no seu estado",
                         "motivo": "confirmar que o destino mostra a oferta por estado",
                         "evidencia": "editorial.links[0].reason"}],
        }


def test_a_arquitetura_gravada_tem_contexto_e_revisao(monkeypatch):
    arq = _rodar_rota(monkeypatch, revisor_cliente=_RevisorQueReescreveTom(),
                      validacao=_validacao())

    assert arq["contexto_de_leitura"] == contexto_de_leitura(_validacao())

    revisao = arq["revisao_arquitetura"]
    assert revisao["changes"] == ["Traduzido intro_section da P2 para pt-BR"]
    campos = [a.get("campo") for a in revisao["achados"]]
    assert "hook_to_next_page" in campos
    # a tentativa de reescrever o tom virou ACHADO, não mudança aplicada
    assert "funnel_strategy.tone_voice" in campos

    # tom e público do arquiteto continuam no plano
    fs = arq["funnel_strategy"]
    assert fs["tone_voice"] == _arquitetura_do_llm()["funnel_strategy"]["tone_voice"]
    assert fs["avatar_summary"] == _arquitetura_do_llm()["funnel_strategy"]["avatar_summary"]
    # e descem a cada briefing de página, que é o que o motor lê
    for job in arq["writing_jobs"]:
        assert job["writer_briefing"]["tone"] == fs["tone_voice"]


def test_sem_validacao_a_arquitetura_nao_ganha_contexto(monkeypatch):
    arq = _rodar_rota(monkeypatch, revisor_cliente=_RevisorQueReescreveTom(), validacao=None)
    assert "contexto_de_leitura" not in arq
    assert "revisao_arquitetura" in arq


class _RevisorQueCai:
    async def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        raise RuntimeError("400 Bad Request for url 'https://llm.example/v1?key=SEGREDO-FALSO-123'")


def test_revisao_que_nao_aconteceu_fica_dita_e_sem_segredo(monkeypatch):
    """Revisor fora do ar: o funil sai (fail-open), mas a arquitetura diz que
    NÃO foi revisada — e não carrega a mensagem crua da exceção, que no cliente
    Gemini traz a URL com a chave."""
    arq = _rodar_rota(monkeypatch, revisor_cliente=_RevisorQueCai(), validacao=_validacao())

    revisao = arq["revisao_arquitetura"]
    assert revisao["estado"] == "nao_revisado"
    assert revisao["changes"] == [] and revisao["achados"] == []
    assert "SEGREDO-FALSO-123" not in json.dumps(arq, ensure_ascii=False)
