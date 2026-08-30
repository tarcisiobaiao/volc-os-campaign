"""
extract_json — reparo de deslizes de fechamento do modelo.

Caso real (Pautador Pro, descoberta BR com 2 nichos): o Gemini devolve o JSON
INTEIRO (finishReason=STOP, ~66k chars, 20 entidades) mas emite um `]` a mais
antes do fecho do objeto raiz:

    }
  ]
  ]      <- este
}

O parser desistia e uma geração de ~19k tokens virava lixo -> fallback pro mock
-> a descoberta "trazia 1 entidade". Aconteceu em 2 de 3 chamadas nesse cenário.

Run:  cd backend && pytest tests/test_extract_json_repair.py -v
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

import pytest

from app.llm.base import extract_json


def test_json_valido_continua_intacto():
    payload = {"entities": [{"canonical_name": "CadÚnico", "aliases": ["a", "b"]}], "meta": {"n": 1}}
    assert extract_json(json.dumps(payload)) == payload


def test_dict_passa_direto():
    assert extract_json({"entities": []}) == {"entities": []}


def test_cercas_de_codigo():
    assert extract_json('```json\n{"entities": []}\n```') == {"entities": []}


def test_colchete_extra_no_fim_e_reparado():
    """O caso REAL que derrubava a descoberta."""
    quebrado = '{\n  "entities": [\n    {"canonical_name": "CadÚnico"}\n  ]\n  ]\n}'
    with pytest.raises(Exception):
        json.loads(quebrado)  # o parser padrão desiste
    assert extract_json(quebrado) == {"entities": [{"canonical_name": "CadÚnico"}]}


def test_chave_extra_no_fim_e_reparada():
    quebrado = '{"entities": [{"a": 1}]}}'
    assert extract_json(quebrado) == {"entities": [{"a": 1}]}


def test_fechamento_trocado_no_meio_e_descartado():
    quebrado = '{"entities": [{"a": 1}], "meta": {"b": 2]}'
    assert extract_json(quebrado) == {"entities": [{"a": 1}], "meta": {"b": 2}}


def test_saida_truncada_fecha_o_que_ficou_aberto():
    """MAX_TOKENS no meio: melhor entregar as entidades completas do que zero.
    A última (parcial) é descartada depois pela validação de cada item."""
    truncado = '{"entities": [{"canonical_name": "A"}, {"canonical_name": "B"}'
    out = extract_json(truncado)
    assert [e["canonical_name"] for e in out["entities"]] == ["A", "B"]


def test_truncado_no_meio_de_uma_string():
    truncado = '{"entities": [{"canonical_name": "A"}, {"canonical_name": "Cadastro Únic'
    out = extract_json(truncado)
    assert out["entities"][0]["canonical_name"] == "A"


def test_colchete_dentro_de_string_nao_conta():
    """Reparo tem que respeitar literais: um `]` dentro de texto não é fechamento."""
    payload = '{"entities": [{"description": "usa o campo [obrigatório] do form"}]}'
    assert extract_json(payload)["entities"][0]["description"] == "usa o campo [obrigatório] do form"


def test_escape_dentro_de_string():
    payload = r'{"entities": [{"description": "aspas \" e colchete ] no meio"}]}'
    assert extract_json(payload)["entities"][0]["description"] == 'aspas " e colchete ] no meio'


def test_lixo_irreparavel_ainda_levanta():
    with pytest.raises(ValueError):
        extract_json("desculpe, não consigo ajudar com isso")


def test_texto_vazio_levanta():
    with pytest.raises(ValueError):
        extract_json("   ")
