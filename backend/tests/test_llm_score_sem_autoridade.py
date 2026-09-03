"""LLM_SCORE_HAS_ZERO_DECISION_AUTHORITY — provado por caminho real.

A missão pergunta se dois contratos da DESCOBERTA alcançam a validação e o
ranking entregues nesta lane:

    backend/app/entities/prompts.py   ensina a fórmula de pontuação ao modelo
    backend/app/entities/scoring.py   tem fallback `# fallback: trust the LLM score`

Ambos existem e são reais — este arquivo NÃO os inocenta. Ele prova que o
número que eles produzem **não chega** à decisão desta lane, e registra a
dívida como independente em vez de ampliar ownership sem necessidade.

A prova tem três pernas, e nenhuma delas é leitura de comentário:

  1. o valor: mutação arbitrária de `score` deixa a tese byte-idêntica;
  2. o transporte: a rota de teses não seleciona a coluna `score`;
  3. o código: a Camada 2 não referencia o identificador em lugar nenhum.
"""
from __future__ import annotations

import ast
import itertools
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app.validacao.oportunidade import comparar, tese_do_resumo


def _resumo(**over) -> Dict[str, Any]:
    base = {
        "apto": True, "motivo": None, "indice": 0.72, "cobertura": 1.0,
        "perfil": "alvo", "portoes_disparados": [], "alertas": [],
        "eixos": {
            "volume": {"nivel": "alto", "proveniencia": "medido", "motivo_ausencia": None},
            "engajamento": {"nivel": "sustenta", "proveniencia": "julgado", "motivo_ausencia": None},
            "ignorancia": {"nivel": "nao_sei_se_sirvo", "proveniencia": "julgado", "motivo_ausencia": None},
        },
        "ficha": {
            "share_dado_unico": 0.25, "n_perguntas": 2,
            "perguntas": [
                {"pergunta": "Quem tem direito?", "ramos": 3, "condicoes": 3,
                 "decide_depois": True, "oficial_fecha_sozinho": False},
                {"pergunta": "Quando cai?", "ramos": 1, "condicoes": 0,
                 "decide_depois": False, "oficial_fecha_sozinho": True},
            ],
        },
    }
    base.update(over)
    return base


# ── perna 1 · o VALOR não muda nada ──────────────────────────────────────────

SCORES_ARBITRARIOS = [
    None, 0, -1, 0.0001, 1, 45, 70, 99.9, 100, 140.63, 999999,
    float("inf"), -float("inf"), "140.63", "muito alto", {"n": 1}, [1, 2],
]


@pytest.mark.parametrize("score", SCORES_ARBITRARIOS, ids=lambda s: repr(s)[:18])
def test_score_arbitrario_nao_muda_a_tese(score):
    """Um score inventado, de qualquer tipo ou magnitude, deixa a tese idêntica."""
    limpo = tese_do_resumo(_resumo(), tema="t")
    sujo = tese_do_resumo(_resumo(score=score, score_source="llm"), tema="t")
    assert sujo == limpo, f"score={score!r} alterou a tese"


@pytest.mark.parametrize("campo", [
    "score", "score_source", "roi_signal", "gold_tier", "estimated_volume",
    "ecpm_band", "volume_level", "rpm_level", "competition_level",
    "confidence_level", "ignorancia_level", "engajamento_level", "opacidade_level",
])
def test_nenhum_campo_ordinal_da_descoberta_move_a_tese(campo):
    """Os rótulos ordinais que o descobridor pede ao LLM também não decidem.

    Eles descrevem os MESMOS três eixos que o Validador deriva por aritmética.
    Se um deles vazasse, a derivação teria concorrente."""
    a = tese_do_resumo(_resumo(), tema="t")
    b = tese_do_resumo(_resumo(**{campo: "Muito alto"}), tema="t")
    c = tese_do_resumo(_resumo(**{campo: 999999}), tema="t")
    assert a == b == c, f"{campo!r} alterou a tese"


def test_score_nao_reordena_o_ranking():
    """Dois temas: o de score altíssimo tem evidência pior. O ranking ignora."""
    forte = _resumo(indice=0.80)
    fraco = _resumo(indice=0.40)
    fraco["ficha"]["perguntas"][0].update(ramos=1, condicoes=0, decide_depois=False)

    sem = [tese_do_resumo(forte, tema="forte"), tese_do_resumo(fraco, tema="fraco")]
    com = [
        tese_do_resumo({**forte, "score": 1}, tema="forte"),
        tese_do_resumo({**fraco, "score": 999999}, tema="fraco"),
    ]
    assert [t.tema for t in comparar(sem)[0]] == [t.tema for t in comparar(com)[0]]
    assert comparar(com)[0][0].tema == "forte"


# ── perna 2 · o TRANSPORTE não carrega o campo ───────────────────────────────


class SupaEspiao:
    enabled = True

    def __init__(self, linhas):
        self.linhas = linhas
        self.filtros: List[Dict[str, Any]] = []

    async def select(self, tabela, filtro):
        self.filtros.append(dict(filtro))
        return self.linhas


def test_a_rota_de_teses_nao_seleciona_a_coluna_score(monkeypatch):
    from app.main import app

    supa = SupaEspiao([
        {"id": 1, "validacao": _resumo(), "pautador_entities": {"canonical_name": "x"}},
    ])
    monkeypatch.setattr("app.routers.entities.SupabaseService", lambda *_a, **_k: supa)
    r = TestClient(app).post("/api/pautador/entity-opportunities/teses",
                             json={"opportunity_ids": [1]})
    assert r.status_code == 200
    assert supa.filtros, "a rota não consultou"
    select = supa.filtros[0]["select"]
    assert "score" not in select, f"a rota transporta score: {select!r}"
    assert "roi_signal" not in select


def test_a_rota_ignora_score_mesmo_quando_o_banco_devolve(monkeypatch):
    """Defesa em profundidade: se um dia a coluna voltar no SELECT, a tese
    continua não a lendo."""
    from app.main import app

    def corpo(score):
        supa = SupaEspiao([{
            "id": 1, "validacao": _resumo(), "score": score, "score_source": "llm",
            "pautador_entities": {"canonical_name": "x"},
        }])
        monkeypatch.setattr("app.routers.entities.SupabaseService", lambda *_a, **_k: supa)
        return TestClient(app).post("/api/pautador/entity-opportunities/teses",
                                    json={"opportunity_ids": [1]}).json()

    assert corpo(1)["teses"] == corpo(999999)["teses"]


# ── perna 3 · o CÓDIGO não referencia o identificador ────────────────────────


def test_a_camada_2_nunca_le_score_nem_derivados():
    import app.validacao.oportunidade as mod

    arvore = ast.parse(open(mod.__file__, encoding="utf-8").read())
    literais = {n.value for n in ast.walk(arvore)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    atributos = {n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute)}
    nomes = {n.id for n in ast.walk(arvore) if isinstance(n, ast.Name)}

    for proibido in ("score", "score_source", "roi_signal", "gold_tier",
                     "ecpm_band", "volume_level", "rpm_level",
                     "competition_level", "confidence_level"):
        assert proibido not in literais, f"literal {proibido!r} na Camada 2"
        assert proibido not in atributos, f"atributo {proibido!r} na Camada 2"
        assert proibido not in nomes, f"nome {proibido!r} na Camada 2"


def test_a_camada_2_nao_importa_a_descoberta():
    import app.validacao.oportunidade as mod

    arvore = ast.parse(open(mod.__file__, encoding="utf-8").read())
    modulos = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module:
            modulos.add(no.module)
        elif isinstance(no, ast.Import):
            modulos.update(a.name for a in no.names)
    assert not any(m.startswith("app.entities") for m in modulos), (
        f"a Camada 2 importa a descoberta: {modulos}"
    )


# ── a dívida, registrada e não escondida ─────────────────────────────────────


def test_a_divida_da_descoberta_existe_e_esta_declarada():
    """Este teste FALHA se alguém 'consertar' a descoberta sem atualizar a
    dívida — e falha também se a dívida for apagada sem o conserto.

    Ele não aprova o defeito: ele impede que ele suma do registro em silêncio.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    prompts = (raiz / "backend/app/entities/prompts.py").read_text(encoding="utf-8")
    scoring = (raiz / "backend/app/entities/scoring.py").read_text(encoding="utf-8")

    ensina_formula = "A nota do card é" in prompts
    confia_no_llm = "fallback: trust the LLM score" in scoring

    limitacoes = (raiz / "docs/closure/pautador-psychological-validation-v2/LIMITATIONS.md")
    texto = limitacoes.read_text(encoding="utf-8") if limitacoes.exists() else ""

    if ensina_formula or confia_no_llm:
        assert "DIVIDA-DESCOBERTA-SCORE" in texto, (
            "a descoberta ainda pede nota ao LLM e a dívida não está registrada "
            "em LIMITATIONS.md"
        )
