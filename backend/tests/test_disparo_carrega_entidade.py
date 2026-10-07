"""O disparo do redator carrega a ENTIDADE do card — e o que o arquiteto sabe
do leitor chega ao motor.

## O defeito (pista P1, `publicacao.py:534` × `:603`)

O `select` do card pedia só `id,status,funnel_architecture`. O PostgREST devolve
exatamente as colunas pedidas, então `opps[0].get("entity_id")` era SEMPRE
`None`: a entidade nunca era lida, `tema.official_preference` saía `[]` e os
apelidos da entidade nunca entravam nos termos do tema. Nenhum erro — só um
motor escolhendo canal oficial sem a preferência que o card tinha.

O Supabase aqui é FALSO e imita a projeção do PostgREST: coluna não pedida não
volta. É isso que faz o teste reproduzir o defeito em vez de escondê-lo.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from app.routers import publicacao
from app.seguranca import cifrar, gerar_chave

SENHA = "abcd EFGH ijkl MNOP qrst UVWX"

ARQUITETURA = {
    "funnel_strategy": {
        "avatar_summary": "Quem quer um curso gratuito e não sabe onde o Senac do estado publica",
        "tone_voice": "Jornalismo de serviço, direto, sem pressa artificial",
        "total_pages": 2,
    },
    "pages": [{"position": 1, "page_title": "Cursos Senac"},
              {"position": 2, "page_title": "Por onde começar"}],
    "writing_jobs": [
        {"writer_briefing": {"keywords": "cursos senac, cursos gratuitos senac"}},
        {"writer_briefing": {"keywords": ["senac por estado"]}},
    ],
    "contexto_de_leitura": {
        "perguntas_paa": ["Quem tem direito ao curso gratuito do Senac?"],
        "tensao": {"frase": "isso pode mudar minha vida e é de graça — eu entro?",
                   "evidencia": "validacao:3/4"},
    },
    "revisao_arquitetura": {"changes": ["Traduzido intro_section da P1 para pt-BR"],
                            "achados": []},
}

ENTIDADE = {
    "id": 501,
    "canonical_name": "Senac",
    "full_name": "Serviço Nacional de Aprendizagem Comercial",
    "aliases": ["senac cursos gratuitos"],
    "official_source": "Senac",
}


class _SupaFalso:
    """Registra as consultas e devolve só as colunas pedidas (como o PostgREST)."""

    enabled = True

    def __init__(self, *, card: Dict[str, Any], entidades: List[Dict[str, Any]]) -> None:
        self.card = card
        self.entidades = entidades
        self.selects: List[tuple] = []
        self.inserts: List[tuple] = []
        self.patches: List[tuple] = []

    async def select(self, tabela: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.selects.append((tabela, dict(params)))
        if tabela == "pautador_entity_opportunities":
            linha = dict(self.card)
            campos = params.get("select")
            if campos and campos != "*":
                pedidos = {c.strip() for c in campos.split(",")}
                linha = {k: v for k, v in linha.items() if k in pedidos}
            return [linha]
        if tabela == publicacao.TABELA:            # project_wordpress
            return [{
                "project_id": 9,
                "wp_url": "https://creditoup.com.br/",
                "wp_username": "redator-volc",
                "wp_app_password_enc": cifrar(SENHA),
                "post_type": "rec",
                "lp_post_type": "r",
                "conexao_ok": True,
            }]
        if tabela == publicacao.TABELA_RUNS:       # nenhum run andando
            return []
        if tabela == "pautador_entities":
            alvo = params.get("id")
            return [e for e in self.entidades if f"eq.{e['id']}" == alvo]
        return []

    async def insert(self, tabela: str, linhas: List[Dict[str, Any]]):
        self.inserts.append((tabela, linhas))
        return [{"id": 77, **linhas[0]}]

    async def patch(self, tabela: str, match: Dict[str, Any], valores: Dict[str, Any]):
        self.patches.append((tabela, match, valores))
        return []


@pytest.fixture
def com_chave(monkeypatch):
    monkeypatch.setenv("VOLC_SEGREDO_KEY", gerar_chave())


def _disparar(monkeypatch, supa: _SupaFalso) -> Dict[str, Any]:
    """Roda a rota com o Supabase falso e um worker que só registra o que recebeu."""
    from app.redator import worker as w

    recebido: Dict[str, Any] = {}

    def executar_falso(**kwargs):
        recebido.update(kwargs)
        return asyncio.sleep(0)   # a task criada pela rota termina na hora

    monkeypatch.setattr(publicacao, "_supa", lambda: supa)
    monkeypatch.setattr(w, "executar", executar_falso)

    async def _rodar():
        saida = await publicacao.disparar_redator(
            publicacao.DispararEntrada(opportunity_id=42, project_id=9))
        await asyncio.sleep(0)
        return saida

    saida = asyncio.run(_rodar())
    assert saida.motor_conectado is True
    return recebido


def _card(**over) -> Dict[str, Any]:
    card = {"id": 42, "status": "funnel", "entity_id": 501,
            "funnel_architecture": ARQUITETURA}
    card.update(over)
    return card


def test_o_disparo_pede_entity_id_ao_card(monkeypatch, com_chave):
    supa = _SupaFalso(card=_card(), entidades=[ENTIDADE])
    _disparar(monkeypatch, supa)

    pedido = next(p for t, p in supa.selects if t == "pautador_entity_opportunities")
    campos = {c.strip() for c in pedido["select"].split(",")}
    assert "entity_id" in campos
    # o que já era pedido continua sendo pedido
    assert {"id", "status", "funnel_architecture"} <= campos


def test_o_disparo_carrega_a_entidade_e_ela_chega_ao_perfil(monkeypatch, com_chave):
    supa = _SupaFalso(card=_card(), entidades=[ENTIDADE])
    recebido = _disparar(monkeypatch, supa)

    consultas = [p for t, p in supa.selects if t == "pautador_entities"]
    assert consultas and consultas[0]["id"] == "eq.501"

    tema = recebido["perfil"]["tema"]
    assert tema["official_preference"] == ["Senac"]
    assert "senac cursos gratuitos" in tema["termos"]      # apelido da entidade
    assert "cursos senac" in tema["termos"]                # keyword do card continua


def test_publico_e_tom_do_arquiteto_chegam_ao_motor(monkeypatch, com_chave):
    """O motor recebe a arquitetura INTEIRA do card: tom, avatar e a leitura
    medida viajam juntos, sem ninguém no caminho escolher o que sobra."""
    supa = _SupaFalso(card=_card(), entidades=[ENTIDADE])
    recebido = _disparar(monkeypatch, supa)

    arq = recebido["arquitetura"]
    assert arq["funnel_strategy"]["tone_voice"] == ARQUITETURA["funnel_strategy"]["tone_voice"]
    assert arq["funnel_strategy"]["avatar_summary"] == ARQUITETURA["funnel_strategy"]["avatar_summary"]
    assert arq["contexto_de_leitura"] == ARQUITETURA["contexto_de_leitura"]
    assert arq["revisao_arquitetura"] == ARQUITETURA["revisao_arquitetura"]


def test_entidade_apagada_nao_derruba_o_disparo(monkeypatch, com_chave):
    """`entity_id` apontando para linha que não existe mais: o perfil sai sem
    preferência de canal, como antes — o disparo não vira 500."""
    supa = _SupaFalso(card=_card(), entidades=[])
    recebido = _disparar(monkeypatch, supa)

    assert recebido["perfil"]["tema"]["official_preference"] == []
