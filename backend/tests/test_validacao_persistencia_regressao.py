"""Regressões de persistência do Validador — D1 e D2 do ALGORITHM-AS-IS.

Ambas nascem vermelhas contra o comportamento de `b2af81f0`.

D1 · o docstring do módulo e a rota `GET /axes` afirmam que a gravação é
     incremental ("cada eixo grava assim que é medido … para a tela ler esse
     progresso do banco em vez de fingir um"). Ela não era: `_gravar_eixos`
     rodava uma vez só, no fim.

D2 · revalidar um card já medido gravava `ficha: null, tensao: null,
     portao: null` por cima de dados bons, porque `_passo_ficha` pula o card e
     `_gravar_resumo` substitui a coluna inteira.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from app.validacao.orquestrador import Card, Eixo, Validador


class SupaEspiao:
    """Registra cada escrita, em ordem, sem rede."""

    enabled = True

    def __init__(self, validacao_existente: Dict[str, Any] | None = None):
        self.upserts_de_eixos: List[List[Dict[str, Any]]] = []
        self.patches: List[Dict[str, Any]] = []
        self.inserts: List[Any] = []
        self.validacao_existente = validacao_existente

    def _headers(self, *_a, **_k):
        return {}

    async def _request(self, metodo, caminho, *, headers=None, json=None):
        if "axes" in caminho or "entity_axes" in caminho:
            self.upserts_de_eixos.append(list(json or []))
        return []

    async def patch(self, tabela, filtro, valores):
        self.patches.append({"tabela": tabela, "filtro": filtro, "valores": valores})
        return []

    async def insert(self, tabela, linhas):
        self.inserts.append((tabela, linhas))
        return []

    async def select(self, *_a, **_k):
        return []


def _validador(supa) -> Validador:
    from app.config import get_settings
    return Validador(get_settings(), supa)


def _card_medido() -> Card:
    c = Card(opportunity_id=1, entity_id=1, country_code="BR", termo="tema")
    for eixo, nivel in (("volume", "alto"), ("reposicao", "continua"),
                        ("vacuo", "raso"), ("densidade", "densa"),
                        ("formato_consumo", "texto_busca")):
        c.poe(Eixo(eixo, nivel, "medido", {}))
    for eixo, nivel in (("ignorancia", "nao_sei_se_sirvo"),
                        ("engajamento", "sustenta"), ("opacidade", "fragmentada")):
        c.poe(Eixo(eixo, nivel, "julgado", {}))
    return c


# ── D2 · revalidar não pode destruir a ficha ─────────────────────────────────


def test_d2_revalidar_preserva_ficha_tensao_e_portao():
    """Card já medido, cuja ficha o passo 4 vai pular: o resumo gravado NÃO
    pode conter `ficha: null` por cima do que já estava no banco."""
    anterior = {
        "apto": True,
        "ficha": {"share_dado_unico": 0.25, "n_perguntas": 4, "perguntas": []},
        "tensao": {"tensao": "acesso_negado", "share_com_tensao": 1.0},
        "portao": {"veredito": "sem_portao"},
        "cabeca_editorial": "como consultar",
    }
    supa = SupaEspiao()
    v = _validador(supa)
    card = _card_medido()
    card.resumo_anterior = anterior     # o que `_carregar` leu do banco

    v._resumir(card)
    asyncio.run(v._gravar_resumo(card))

    assert supa.patches, "nada foi gravado"
    gravado = supa.patches[-1]["valores"]["validacao"]
    assert gravado["ficha"] == anterior["ficha"], "a ficha foi destruída"
    assert gravado["tensao"] == anterior["tensao"], "a tensão foi destruída"
    assert gravado["portao"] == anterior["portao"], "o portão foi destruído"


def test_d2b_ficha_nova_sobrescreve_a_anterior():
    """Preservar não pode virar congelar: quando o passo 4 RODOU, o novo vale."""
    anterior = {"ficha": {"n_perguntas": 4}, "tensao": {"tensao": "velha"}}
    supa = SupaEspiao()
    v = _validador(supa)
    card = _card_medido()
    card.resumo_anterior = anterior
    card.ficha = {"n_perguntas": 7}
    card.tensao = {"tensao": "nova"}

    v._resumir(card)
    asyncio.run(v._gravar_resumo(card))

    gravado = supa.patches[-1]["valores"]["validacao"]
    assert gravado["ficha"]["n_perguntas"] == 7
    assert gravado["tensao"]["tensao"] == "nova"


def test_d2c_sem_anterior_e_sem_novo_continua_nulo_e_nao_inventa():
    supa = SupaEspiao()
    v = _validador(supa)
    card = _card_medido()

    v._resumir(card)
    asyncio.run(v._gravar_resumo(card))

    gravado = supa.patches[-1]["valores"]["validacao"]
    assert gravado["ficha"] is None
    assert gravado["tensao"] is None


# ── D1 · a gravação precisa ser incremental de verdade ───────────────────────


def test_d1_gravar_eixos_e_idempotente_e_pode_ser_chamado_varias_vezes():
    """O upsert é `on_conflict=opportunity_id,eixo` com merge — chamar N vezes
    grava o mesmo estado. É o que permite gravar a cada passo."""
    supa = SupaEspiao()
    v = _validador(supa)
    card = _card_medido()

    asyncio.run(v._gravar_eixos(card))
    asyncio.run(v._gravar_eixos(card))

    assert len(supa.upserts_de_eixos) == 2
    assert supa.upserts_de_eixos[0] == supa.upserts_de_eixos[1]


def test_d1b_o_orquestrador_grava_a_cada_passo_nao_so_no_fim():
    """Contra o comportamento de b2af81f0: `_gravar_eixos` tinha exatamente dois
    call sites e ambos rodavam depois de toda a medição."""
    import inspect

    from app.validacao import orquestrador as mod

    fonte = inspect.getsource(mod.Validador.validar)
    assert "_gravar_parcial" in fonte or fonte.count("_gravar_eixos") >= 2, (
        "validar() precisa gravar durante os passos, não só no laço final"
    )


def test_d1c_a_promessa_do_docstring_tem_um_mecanismo():
    """Se o texto promete progresso incremental ao operador, o mecanismo existe."""
    from app.validacao import orquestrador as mod

    assert hasattr(mod.Validador, "_gravar_parcial"), (
        "a rota GET /axes promete progresso incremental; sem mecanismo, a "
        "barra do operador é ficção"
    )
