"""Normalização de UTM: equivalência byte a byte com o JavaScript real do sensor/wrapper.

Os vetores foram gerados executando as funções extraídas do HTML versionado em
`wip/historico-measurement-20261015` (918e9571) — ver o gerador e o recibo em
`docs/data-intelligence/fundacao-20261016/receipts/identidade/`.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from volc_dil.fundacao.identidade import (
    LIMITE_CHECAGEM_PII,
    MotivoDescarte,
    UtmSessao,
    diagnosticar_utm_sensor_v3,
    limpar_utm_ingest,
    normalizar_utm_sensor_v3,
    normalizar_valor_wrapper_v2,
    parse_query_urlsearchparams,
    utm_da_pagina_sensor_v3,
)

RAIZ = Path(__file__).resolve().parents[3]
VETORES = RAIZ / "docs/data-intelligence/fundacao-20261016/receipts/identidade/vetores_utm_sensor_v3.json"
SHA_SENSOR = "cb01822420e22b41066632510269376899da20653d7ace5c3b50d91507ca41e4"
SHA_WRAPPER = "bbd4c82193fe9c8883a1cec93cf88d4e273aa53dfae4324aa9c37cba7aded699"


@pytest.fixture(scope="module")
def vetores():
    return json.loads(VETORES.read_text(encoding="utf-8"))


def test_vetores_vem_do_codigo_lido(vetores):
    assert vetores["fontes"]["sensor"]["sha256"] == SHA_SENSOR
    assert vetores["fontes"]["wrapper"]["sha256"] == SHA_WRAPPER
    assert len(vetores["vetores"]) >= 60
    assert vetores["vetores_aleatorios"]["n"] == 3000


def test_vetores_nomeados_sensor_e_wrapper(vetores):
    divergencias = [
        (v["entrada"], normalizar_utm_sensor_v3(v["entrada"]), v["sensor_v3"],
         normalizar_valor_wrapper_v2(v["entrada"]), v["wrapper_v2"])
        for v in vetores["vetores"]
        if normalizar_utm_sensor_v3(v["entrada"]) != v["sensor_v3"]
        or normalizar_valor_wrapper_v2(v["entrada"]) != v["wrapper_v2"]
    ]
    assert divergencias == []


def test_vetores_aleatorios_3000(vetores):
    itens = vetores["vetores_aleatorios"]["itens"]
    ruins = [v["entrada"] for v in itens
             if normalizar_utm_sensor_v3(v["entrada"]) != v["sensor_v3"]
             or normalizar_valor_wrapper_v2(v["entrada"]) != v["wrapper_v2"]]
    assert ruins == []


def test_cenarios_campaign_com_sessionstorage(vetores):
    for c in vetores["cenarios_campaign"]:
        arm = json.loads(c["armazenado"]) if c["armazenado"] else None
        utm, novo = utm_da_pagina_sensor_v3(urlsplit(c["href"]).query, arm)
        esperado_depois = json.loads(c["armazenado_depois"]) if c["armazenado_depois"] else None
        assert utm.como_payload() == c["utm"], c["href"]
        assert novo == esperado_depois, c["href"]


def test_campaign_id_real_e_descartado_como_pii():
    # A contradição do roadmap em uma linha: o sensor LÊ utm_campaign, mas o id de 11 dígitos
    # casa a regex de telefone/CPF e vira ''.
    assert diagnosticar_utm_sensor_v3("20000000011") == ("", MotivoDescarte.PII)
    assert normalizar_valor_wrapper_v2("20000000011") == ""
    # Até 9 dígitos sobrevive; 10 já cai.
    assert normalizar_utm_sensor_v3("200000001") == "200000001"
    assert normalizar_utm_sensor_v3("2000000001") == ""
    # Prefixo textual não salva: a regex não é ancorada.
    assert normalizar_utm_sensor_v3("c20000000011") == ""


def test_url_real_do_template_perde_campaign_e_content():
    url = ("https://site.exemplo/r/guia-exemplo/?utm_source=google&utm_medium=cpc"
           "&utm_campaign=20000000011&utm_term=cursos%20tecnicos&utm_content=165432109876"
           "&utm_device=m&vc_match=e&gclid=SINTETICO")
    utm, armazenado = utm_da_pagina_sensor_v3(urlsplit(url).query)
    assert utm == UtmSessao(source="google", medium="cpc", term="cursos_tecnicos", paid=1)
    assert utm.campaign is None and utm.content is None
    assert "SINTETICO" not in json.dumps(armazenado)  # o valor do gclid nunca sai


def test_teto_200_descarta_no_sensor_mas_trunca_no_wrapper():
    v = "a" * (LIMITE_CHECAGEM_PII + 1)
    assert diagnosticar_utm_sensor_v3(v) == ("", MotivoDescarte.LONGO_DEMAIS)
    assert normalizar_valor_wrapper_v2(v) == "a" * 40
    assert normalizar_utm_sensor_v3("a" * LIMITE_CHECAGEM_PII) == "a" * 40


def test_corte_em_unidades_utf16_como_o_javascript():
    assert normalizar_utm_sensor_v3("🎓" * 30) == "🎓" * 20  # 40 unidades = 20 emojis
    assert normalizar_utm_sensor_v3("x" * 39 + "🎓") == "x" * 39 + "\ud83c"  # par partido, como no JS


def test_espaco_do_javascript_nao_e_o_do_python():
    assert normalizar_utm_sensor_v3("a﻿b") == "a_b"  # JS \s inclui U+FEFF
    assert normalizar_utm_sensor_v3("a\x1cb") == "a\x1cb"  # Python \s incluiria U+001C
    assert normalizar_utm_sensor_v3("١٢٣٤٥٦٧٨٩٠١") == "١٢٣٤٥٦٧٨٩٠١"  # \d do JS é só ASCII


def test_urlsearchparams_mais_vira_espaco_e_primeiro_valor_vence():
    q = parse_query_urlsearchparams("?utm_campaign=Cursos+Tecno&utm_campaign=b&gclid=")
    assert q == {"utm_campaign": "Cursos Tecno", "gclid": ""}


def test_gclid_vazio_ainda_marca_pago():
    utm, _ = utm_da_pagina_sensor_v3("gclid=")
    assert utm.paid == 1


def test_ingest_preserva_utm_normalizada_e_derruba_chave_invalida():
    utm, _ = utm_da_pagina_sensor_v3("utm_source=google&utm_medium=cpc&utm_term=bolsa+tecno&gbraid=1")
    payload = dict(utm.como_payload())
    payload["9ruim"] = "x"
    assert limpar_utm_ingest(payload) == {"source": "google", "medium": "cpc", "term": "bolsa_tecno", "paid": 1}
