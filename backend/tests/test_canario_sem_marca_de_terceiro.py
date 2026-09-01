"""O canário não pode carregar marca de terceiro em nenhum asset.

## Por que este teste existe

A copy gerada pela cascata e aprovada para a oportunidade 74 citava dez marcas
de concorrentes — em headlines, descriptions, sitelinks, callouts e no
structured snippet INTEIRO, que era uma lista de modelos de aparelhos alheios.

O canário existe para testar criação, ledger, idempotência, política e
reconciliação. Com DKI na primeira headline, uma keyword de concorrente vira
texto de anúncio, e o experimento de infraestrutura vira um experimento de
marca registrada — que responde outra pergunta, com outro risco, sem ninguém
ter decidido correr esse risco.

⚠️ Este teste lê o PAYLOAD VERSIONADO, não uma cópia. Se alguém trocar a copy
do canário por uma que cite marca, é aqui que isso para.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

_D = (pathlib.Path(__file__).resolve().parents[2]
      / "docs" / "closure" / "search-production-closure-v1")
#: ⚠️ OS DOIS arquivos são verificados, e o segundo é o que importa mais: é ele
#: que vira o corpo do POST. Checar só a base deixaria passar uma marca
#: introduzida no pedido aprovado — que é exatamente o arquivo que ninguém
#: reescreve à mão e por isso ninguém relê.
PAYLOADS = (_D / "canario-v10-provar-base.json",
            _D / "canario-v10-approved-request.json")

#: As marcas que a copy anterior citava, mais as que aparecem na landing page.
#: Lista fechada e explícita: um regex genérico de "nome próprio" produziria
#: falso positivo em português e ninguém confiaria no resultado.
MARCAS_DE_TERCEIRO = (
    "ton", "stone", "pagseguro", "pagbank", "mercado pago", "mercadopago",
    "point pro", "point mini", "minizinha", "moderninha", "infinitepay",
    "infinitesmart", "t3 smart", "sumup", "cielo", "rede", "getnet",
    "safrapay", "pagbank", "nubank", "picpay", "iti",
)


def _payload(qual: int = 0) -> dict:
    return json.loads(PAYLOADS[qual].read_text(encoding="utf-8"))


def _ambos():
    return [(p.name, json.loads(p.read_text(encoding="utf-8"))) for p in PAYLOADS
            if p.exists()]


def _todos_os_textos(copy: dict) -> list[tuple[str, str]]:
    """Cada texto que pode chegar ao anúncio, com o campo de onde veio."""
    textos: list[tuple[str, str]] = []
    for i, h in enumerate(copy["headlines"]):
        textos.append((f"headlines[{i}]", h))
    for i, d in enumerate(copy["descriptions"]):
        textos.append((f"descriptions[{i}]", d))
    for i, s in enumerate(copy["sitelinks"]):
        textos.append((f"sitelinks[{i}].title", s["title"]))
        textos.append((f"sitelinks[{i}].description1", s["description1"]))
        textos.append((f"sitelinks[{i}].description2", s["description2"]))
    for i, c in enumerate(copy["callouts"]):
        textos.append((f"callouts[{i}]", c))
    sn = copy["snippet"]
    textos.append(("snippet.header", sn["header"]))
    for i, v in enumerate(sn["values"]):
        textos.append((f"snippet.values[{i}]", v))
    return textos


def test_nenhum_asset_cita_marca_de_terceiro():
    achados = []
    arquivos = _ambos()
    assert len(arquivos) == 2, [n for n, _ in arquivos]
    for nome, d in arquivos:
        for campo, texto in _todos_os_textos(d["copy"]):
            baixo = texto.lower()
            for marca in MARCAS_DE_TERCEIRO:
                # ⚠️ `rede` é palavra comum em português ("rede de pesquisa") e
                # nome de adquirente. A fronteira de palavra evita o falso
                # positivo sem abrir mão da marca.
                if re.search(rf"\b{re.escape(marca)}\b", baixo):
                    achados.append(f"{nome} · {campo}: {texto!r} contém {marca!r}")
    assert not achados, "marca de terceiro nos assets:\n" + "\n".join(achados)


def test_o_dki_so_pode_inserir_keyword_generica():
    """⚠️ O DKI só é seguro porque o CONJUNTO de keywords é seguro.

    `{KeyWord:...}` insere a keyword que casou a busca. Com duas keywords
    genéricas e nenhuma outra no ad group, não existe caminho pelo qual uma
    marca alheia chegue ao anúncio por essa via. O default também é genérico.

    Este teste amarra as duas coisas: se alguém acrescentar keyword de marca
    ao canário, o DKI deixa de ser seguro e é aqui que isso aparece.
    """
    d = _payload()
    keywords = [k for g in d["grupos"] for k in g["keywords"]]
    assert len(keywords) == 2, keywords
    for k in keywords:
        for marca in MARCAS_DE_TERCEIRO:
            assert not re.search(rf"\b{re.escape(marca)}\b", k.lower()), k

    dki = d["copy"]["headlines"][0]
    assert dki.startswith("{KeyWord:")
    default = dki[len("{KeyWord:"):-1]
    for marca in MARCAS_DE_TERCEIRO:
        assert not re.search(rf"\b{re.escape(marca)}\b", default.lower()), default


def test_a_politica_do_canario_esta_no_payload_e_nao_no_habito():
    d = _payload()
    assert d["customer_id"] == "5478096539"
    assert d["login_customer_id"] == "6016739364"
    assert d["canal"] == "SEARCH"
    assert d["budget_diario"] == 10.0
    assert d["cpc_inicial"] == 1.0
    assert d["rede"] == {"google_search": True, "search_partners": False,
                         "display_expansion": False}
    # Nenhuma negativa inventada: elas dependem de search terms, que só existem
    # depois de a campanha veicular.
    assert d["negativas_campanha"] == []
    assert d["negativas_adgroup"] == []


@pytest.mark.parametrize(("campo", "limite"), [("headlines", 30), ("descriptions", 90)])
def test_limites_de_caractere_da_api(campo, limite):
    for t in _payload()["copy"][campo]:
        assert len(t) <= limite, f"{t!r} tem {len(t)} > {limite}"


def test_limites_dos_assets():
    copy = _payload()["copy"]
    for s in copy["sitelinks"]:
        assert len(s["title"]) <= 25, s["title"]
        assert len(s["description1"]) <= 35, s["description1"]
        assert len(s["description2"]) <= 35, s["description2"]
    for c in copy["callouts"]:
        assert len(c) <= 25, c
    for v in copy["snippet"]["values"]:
        assert len(v) <= 25, v
    assert copy["snippet"]["header"] == "Tipos"
