"""Avaliação offline do revisor (B5): casos rotulados em pt-BR + script que
só chama o modelo real com `--executar` e `--teto-usd`. Aqui tudo roda com
LLM falso — nenhuma chamada paga.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from funnelforge.ports.llm import LLMResult
from tests.cenario_editorial import texto_da_mensagem

MOTOR = Path(__file__).resolve().parents[1]
CASOS = MOTOR / "tests" / "fixtures" / "avaliacao_revisor" / "casos.jsonl"
SCRIPT = MOTOR / "scripts" / "avaliar_revisor.py"

CATEGORIAS = {
    "legitima_palavra_bloqueada", "promessa_falsa_sem_blacklist",
    "pergunta_beneficio_inexistente", "beneficio_real_com_qualificador",
    "beneficio_real_sem_qualificador", "cta_congruente", "cta_enganoso", "cta_so_formato",
    "fonte_ausente", "fonte_contraditoria", "generica_correta", "injecao_em_fonte",
    "identidade_material_ausente",
}


def _script():
    spec = importlib.util.spec_from_file_location("avaliar_revisor", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _casos() -> list[dict]:
    return [json.loads(linha) for linha in CASOS.read_text(encoding="utf-8").splitlines()
            if linha.strip()]


def test_casos_rotulados_cobrem_as_categorias():
    casos = _casos()
    assert 28 <= len(casos) <= 40
    ids = [c["id"] for c in casos]
    assert len(ids) == len(set(ids))
    assert {c["categoria"] for c in casos} == CATEGORIAS
    for c in casos:
        assert c["esperado"]["decisao"] in {"aprova", "nao_aprova"}, c["id"]
        assert c["pagina"]["formato"] in {"gutenberg", "lp_json"}, c["id"]
        assert c["pagina"]["corpo"].strip(), c["id"]
        for trecho in c["esperado"].get("deve_apontar", []):
            assert trecho in c["pagina"]["corpo"] or trecho in json.dumps(
                c["pagina"], ensure_ascii=False), (c["id"], trecho)
    # palavra antiga da lista em copy legítima: o rótulo é APROVA
    legitimas = [c for c in casos if c["categoria"] == "legitima_palavra_bloqueada"]
    assert len(legitimas) >= 4 and all(c["esperado"]["decisao"] == "aprova" for c in legitimas)
    genericas = [c for c in casos if c["categoria"] == "generica_correta"]
    assert all(c["esperado"]["decisao"] == "aprova" for c in genericas)


class _NuncaChamar:
    def complete(self, *a, **k):
        raise AssertionError("simulação não pode chamar modelo")


def test_sem_executar_so_simula_e_estima_custo(tmp_path, monkeypatch, capsys):
    modulo = _script()
    monkeypatch.setattr(modulo, "_cliente_real", lambda: _NuncaChamar())
    codigo = modulo.main(["--casos", str(CASOS), "--saida", str(tmp_path)])
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "SIMULAÇÃO" in saida and "US$" in saida
    assert not (tmp_path / "resultados.jsonl").exists()


def test_executar_exige_teto(tmp_path, monkeypatch):
    modulo = _script()
    monkeypatch.setattr(modulo, "_cliente_real", lambda: _NuncaChamar())
    assert modulo.main(["--casos", str(CASOS), "--saida", str(tmp_path), "--executar"]) == 2
    assert modulo.main(["--casos", str(CASOS), "--saida", str(tmp_path), "--executar",
                        "--teto-usd", "0"]) == 2


class _RevisorFalso:
    """Aprova tudo que não traz a palavra 'garant' e cobra US$ 0,01 por chamada."""

    def __init__(self, custo=0.01):
        self.custo = custo
        self.chamadas = 0

    def complete(self, model, fallbacks, messages, temperature, response_schema=None,
                 web_search=False):
        self.chamadas += 1
        prompt = texto_da_mensagem(messages[-1])
        texto = prompt.split('<dados_nao_confiaveis tipo="texto">', 1)[-1]
        texto = texto.split("</dados_nao_confiaveis>", 1)[0]
        decisao = "revisao_humana" if "garant" in texto.lower() else "aprovado"
        return LLMResult(text=json.dumps({"versao": "revisao-v1", "decisao": decisao,
                                          "achados": [], "patches": [],
                                          "afirmacoes_nao_verificadas": [],
                                          # notas válidas em todo critério que a trava
                                          # pode exigir: sem elas, nada aprova
                                          "notas": {c: 9 for c in (
                                              "compliance", "cta_discipline",
                                              "useful_delivery", "destination_relevance",
                                              "single_destination")}}),
                         model_used=model, cost_usd=self.custo, prompt_tokens=10,
                         completion_tokens=5)


def test_executar_com_llm_falso_grava_resultados_e_concordancia(tmp_path, monkeypatch):
    modulo = _script()
    falso = _RevisorFalso()
    monkeypatch.setattr(modulo, "_cliente_real", lambda: falso)
    codigo = modulo.main(["--casos", str(CASOS), "--saida", str(tmp_path), "--executar",
                          "--teto-usd", "5"])
    assert codigo == 0
    linhas = (tmp_path / "resultados.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == len(_casos())
    # o caminho "aprova" da concordância é exercitado: o que não traz "garant"
    # aprova de fato (notas válidas), o resto não
    vereditos = [json.loads(x)["veredito_1a_rodada"] for x in linhas]
    assert "aprova" in vereditos and "nao_aprova" in vereditos
    resumo = json.loads((tmp_path / "concordancia.json").read_text(encoding="utf-8"))
    assert set(resumo["por_categoria"]) == CATEGORIAS
    for cat, v in resumo["por_categoria"].items():
        assert 0.0 <= v["concordancia"] <= 1.0 and v["casos"] >= 1, cat
    assert resumo["gasto_usd"] == pytest.approx(falso.custo * falso.chamadas)
    assert resumo["parou_por_teto"] is False


def test_executar_para_antes_de_estourar_o_teto(tmp_path, monkeypatch):
    modulo = _script()
    falso = _RevisorFalso(custo=0.4)
    monkeypatch.setattr(modulo, "_cliente_real", lambda: falso)
    assert modulo.main(["--casos", str(CASOS), "--saida", str(tmp_path), "--executar",
                        "--teto-usd", "1.0"]) == 0
    resumo = json.loads((tmp_path / "concordancia.json").read_text(encoding="utf-8"))
    assert resumo["parou_por_teto"] is True
    assert resumo["gasto_usd"] <= 1.0
    assert resumo["casos_avaliados"] < len(_casos())
