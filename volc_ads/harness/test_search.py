"""Contraprovas herméticas: sem chave, DNS, Google ou inferência."""
import json
from types import SimpleNamespace

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from volc_ads.campanha import search
from volc_ads.campanha.testes_search import _cliente_sem_rede
from volc_ads.gads.client import _CapturarRequestId
from volc_ads.harness.search import Entrada, Proposta, config_geracao, executar, instrucao, preparar, sha


def entrada(**trocas):
    valores = dict(customer_id="1234567890", login_customer_id="0987654321",
                   tema="Cursos", slug="cursos", url_final="https://example.com/guia/",
                   pagina_texto="Guia independente sobre cursos e regras. " * 4,
                   keywords=["curso gratuito", "regra de renda"],
                   origem_keywords="fixture hermética; não é aprovação de mídia",
                   budget_diario=20.0, cpc_inicial=0.6, carimbo="teste")
    valores.update(trocas)
    return Entrada(**valores)


def proposta():
    return dict(grupos=[dict(nome="Cursos", keyword_indices=[0, 1],
                            headlines=["Cursos Gratuitos", "Regras de Renda", "Guia de Cursos"],
                            descriptions=["Confira cursos e regras no guia independente.",
                                          "Saiba onde procurar os cursos no seu estado."],
                            hipotese="pergunta de acesso")],
                sitelinks=["Regras de Renda", "Cursos no Estado"],
                callouts=["Guia Independente", "Fontes Oficiais"], lacunas=[])


def resposta():
    return dict(text=json.dumps(proposta()), served_model="gemini-teste",
                finish_reasons=["STOP"], usage=None)


@pytest.fixture
def sem_rede(monkeypatch):
    monkeypatch.setattr(search, "cliente", lambda _: _cliente_sem_rede())


@given(st.permutations([0, 1, 2, 3]))
def test_particao_preserva_conjunto_em_qualquer_ordem(indices):
    p = proposta()
    p["grupos"][0]["keyword_indices"] = list(indices)
    Proposta(**p).conferir_conjunto(entrada(keywords=["a", "b", "c", "d"]))


@pytest.mark.parametrize("indices", [[0], [0, 0], [0, 2], [True, 0], [-1, 0]])
def test_modelo_nao_inventa_omite_ou_duplica_keyword(indices):
    p = proposta()
    p["grupos"][0]["keyword_indices"] = indices
    with pytest.raises(ValueError):
        Proposta(**p).conferir_conjunto(entrada())


@pytest.mark.parametrize("campo", ["budget_diario", "cpc_inicial", "negativas", "target_roas"])
def test_modelo_nao_decide_financas_ou_negativas(campo):
    with pytest.raises(ValidationError):
        Proposta(**(proposta() | {campo: 9999}))


def test_descricao_de_91_caracteres_e_recusada_pelo_schema_tecnico():
    p = proposta()
    p["grupos"][0]["descriptions"][0] = "a" * 91
    with pytest.raises(ValidationError):
        Proposta(**p)
    schema = config_geracao().response_json_schema
    assert schema["$defs"]["Grupo"]["properties"]["descriptions"]["items"]["maxLength"] == 90


@given(st.floats(min_value=1, max_value=300, allow_nan=False, allow_infinity=False))
@settings(deadline=None)
def test_valores_do_operador_chegam_ao_payload(valor):
    # Sem fixture de rede por exemplo do Hypothesis: cliente local explícito.
    with pytest.MonkeyPatch.context() as m:
        m.setattr(search, "cliente", lambda _: _cliente_sem_rede())
        e = entrada(budget_diario=valor, cpc_inicial=valor)
        ops, r = preparar(e, Proposta(**proposta()))
        assert r.ok
        budget = next(o.campaign_budget_operation.create for o in ops
                      if o._pb.WhichOneof("operation") == "campaign_budget_operation")
        group = next(o.ad_group_operation.create for o in ops
                     if o._pb.WhichOneof("operation") == "ad_group_operation")
        assert budget.amount_micros == round(valor * 1_000_000)
        assert group.cpc_bid_micros == round(valor * 1_000_000)


def test_retomada_sem_nova_chamada_e_recibo_autentico(sem_rede, tmp_path):
    chamadas = []

    def gerar(*args, **kwargs):
        chamadas.append("gemini")
        return resposta()

    def validar(cid, ops, **kwargs):
        chamadas.append("google")
        kwargs["request_ids"].append("request-real-no-teste")
        camp = next(o.campaign_operation.create for o in ops
                    if o._pb.WhichOneof("operation") == "campaign_operation")
        assert camp.status.name == "PAUSED"

    r = executar(entrada(), tmp_path, modelo="gemini-teste", gerar=gerar, validar=validar)
    assert r["google_request_ids"] == ["request-real-no-teste"]
    assert executar(entrada(), tmp_path, modelo="gemini-teste", gerar=gerar, validar=validar) == r
    assert chamadas == ["gemini", "google"]
    assert not r["policy_approval_proven"]
    (tmp_path / "payload.json").write_text("[]")
    with pytest.raises(ValueError, match="artefato alterado"):
        executar(entrada(), tmp_path, modelo="gemini-teste", gerar=gerar, validar=validar)
    assert chamadas == ["gemini", "google"]


def test_queda_apos_chamada_nao_repete_e_sem_modelo_fallback(tmp_path):
    chamadas = []

    def falhar(*args, **kwargs):
        chamadas.append(1)
        raise ConnectionError("token-que-nao-deve-ir-ao-recibo")

    with pytest.raises(ConnectionError):
        executar(entrada(), tmp_path, modelo="teste", gerar=falhar)
    assert "token-que" not in (tmp_path / "erro.json").read_text()
    with pytest.raises(ValueError, match="sem repetição"):
        executar(entrada(), tmp_path, modelo="teste", gerar=falhar)
    assert len(chamadas) == 1


def test_teto_de_duas_geracoes_e_sem_validate_em_saida_incompleta(tmp_path):
    chamadas = []

    def incompleto(*args, **kwargs):
        chamadas.append(1)
        return resposta() | {"finish_reasons": ["MAX_TOKENS"]}

    for reparar in [False, True]:
        with pytest.raises(ValueError, match="incompleta"):
            executar(entrada(), tmp_path, modelo="gemini-teste", gerar=incompleto, reparar=reparar,
                     validar=lambda *a, **k: pytest.fail("não deveria chamar Google"))
    with pytest.raises(ValueError, match="sem repetição"):
        executar(entrada(), tmp_path, modelo="gemini-teste", gerar=incompleto, reparar=True)
    assert len(chamadas) == 2


def test_entrada_diferente_nao_reaproveita_run(sem_rede, tmp_path):
    executar(entrada(), tmp_path, modelo="gemini-teste", gerar=lambda *a, **k: resposta(),
             validar=lambda *a, **k: None)
    with pytest.raises(ValueError, match="entrada/modelo mudou"):
        executar(entrada(cpc_inicial=9.0), tmp_path, modelo="gemini-teste")


def test_google_request_id_sem_credenciais():
    ids = []
    chamada = SimpleNamespace(trailing_metadata=lambda: [
        ("authorization", "NAO-GRAVAR"), ("request-id", "abc"),
    ])
    assert _CapturarRequestId(ids).intercept_unary_unary(lambda *a: chamada, None, None) is chamada
    assert ids == ["abc"]


def test_sha_independente_da_ordem_das_chaves():
    assert sha({"a": 1, "b": 2}) == sha({"b": 2, "a": 1})


def test_prompt_nao_compartilha_contas_e_parametros_financeiros():
    e = entrada()
    prompt = instrucao(e)
    contexto = json.loads(prompt.split("ENTRADA:\n", 1)[1])
    assert "budget_diario" not in contexto
    assert "cpc_inicial" not in contexto
    assert e.customer_id not in prompt
    assert e.login_customer_id not in prompt
    assert contexto["keywords"] == e.keywords


def test_modelo_divergente_nao_chega_ao_google(tmp_path):
    with pytest.raises(ValueError, match="modelo servido diverge"):
        executar(entrada(), tmp_path, modelo="gemini-teste", gerar=lambda *a, **k:
                 resposta() | {"served_model": "gemini-teste-outro"},
                 validar=lambda *a, **k: pytest.fail("não deveria chamar Google"))


def test_captura_offline_preserva_fonte_e_nao_sobrescreve(tmp_path, monkeypatch):
    from volc_ads.harness import capture
    linhas = [SimpleNamespace(
        campaign=SimpleNamespace(id=1), ad_group=SimpleNamespace(id=2),
        ad_group_criterion=SimpleNamespace(keyword=SimpleNamespace(
            text="curso gratuito", match_type=SimpleNamespace(name="PHRASE"))),
    )]
    monkeypatch.setattr(capture, "snapshot", lambda *a: {"campaigns": [], "ads": []})
    monkeypatch.setattr(capture, "buscar", lambda *a, **k: iter(linhas))
    monkeypatch.setattr(capture, "fetch_public_https_chain", lambda url: {
        "url": url, "final_url": url, "status": 200, "sha256": "a" * 64,
        "html": "<html><head><script>segredo</script></head><body><nav>menu</nav>"
                "<main>" + "Guia independente com cursos e regras. " * 5 + "</main></body></html>",
    })
    kwargs = dict(customer_id="1234567890", login_customer_id="0987654321",
                  url="https://example.com/guia/", tema="Cursos", slug="cursos", budget=20.0, cpc=0.6)
    e = capture.capturar(tmp_path, **kwargs)
    assert e.keywords == ["curso gratuito"]
    assert "segredo" not in e.pagina_texto and "menu" not in e.pagina_texto
    assert json.loads((tmp_path / "input.json").read_text())["cpc_inicial"] == 0.6
    with pytest.raises(ValueError, match="não sobrescreva"):
        capture.capturar(tmp_path, **kwargs)


def test_sdk_serializa_json_schema_sem_additional_properties_invalido():
    import httpx
    from google import genai
    from google.genai import types

    corpos = []

    def transporte(req):
        corpos.append(json.loads(req.content))
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": json.dumps(proposta())}],
                                         "role": "model"}, "finishReason": "STOP"}],
            "modelVersion": "gemini-3.8-flash",
        })

    with httpx.Client(transport=httpx.MockTransport(transporte)) as http:
        with genai.Client(api_key="fixture-sem-chave-real", http_options=types.HttpOptions(
            httpx_client=http, retry_options=types.HttpRetryOptions(attempts=1),
        )) as cliente:
            r = cliente.models.generate_content(model="gemini-3.8-flash", contents="fixture",
                                                 config=config_geracao())
            Proposta.model_validate_json(r.text)
    assert len(corpos) == 1
    config = corpos[0]["generationConfig"]
    assert "responseSchema" not in config
    assert config["responseJsonSchema"]["additionalProperties"] is False
    assert "additional_properties" not in json.dumps(corpos[0])
