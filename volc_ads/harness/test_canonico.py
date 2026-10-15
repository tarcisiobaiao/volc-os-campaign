"""Modo canônico do harness: sem rede, sem credencial, sem Gemini real."""
from __future__ import annotations

import json

import pytest
from hypothesis import given, settings, strategies as st

from volc_ads.harness import canonico as cn

MODELO = "gemini-3.8-flash"


def _pedido(**troca) -> cn.Pedido:
    base = dict(
        opportunity_id=106, run_id=28, customer_id="5478096539",
        login_customer_id="6016739364", budget_diario=10.0, cpc_inicial=0.5,
        estrategia_lance="MANUAL_CPC",
        rede={"google_search": True, "search_partners": False, "display_expansion": False},
        vertical="informativo", carimbo_nome="20261014_220000",
        origem_dos_parametros="fixture: parâmetros declarados no teste",
    )
    base.update(troca)
    return cn.Pedido.model_validate(base)


CONTEXTO = {
    "tema": "Gás do Povo", "url_final": "https://site.example/guia/", "status_wp": "publish",
    "pais": "BR", "idioma": "pt", "keywords": ["gás do povo", "gás do povo consulta"],
    "conjunto_aprovado_sha256": "a" * 64, "pagina_texto": "texto da página " * 20,
    "promessa_da_lp": {"titulo": "Gás do Povo"}, "avisos_do_cockpit": [],
}

COPY = {
    "headlines": ["Gás do Povo", "Como Consultar", "Guia de Cadastro"],
    "descriptions": ["Entenda as etapas descritas no guia.", "Veja como consultar o cadastro."],
    "sitelinks": [{"title": "Etapas", "description1": "A ordem", "description2": "Do guia"},
                  {"title": "Consulta", "description1": "Onde ver", "description2": "Seu cadastro"}],
    "callouts": ["Guia independente", "Passo a passo"],
    "lacunas": [],
}


def _gerar(texto=None, servido=MODELO, finish=("STOP",)):
    chamadas = []

    def gerar(prompt, config, *, modelo):
        chamadas.append(prompt)
        return {"requested_model": modelo, "served_model": servido,
                "text": json.dumps(texto or COPY, ensure_ascii=False), "seconds": 1.0,
                "usage": {"prompt_token_count": 1000, "candidates_token_count": 300,
                          "thoughts_token_count": 100},
                "finish_reasons": list(finish), "cost_usd": None,
                "cost_status": "not_reported_by_provider"}
    return gerar, chamadas


def _resposta_ok(request_id="req-1"):
    return 200, {
        "preparo": {"aprovado": True, "n_operacoes": 20, "recusa_local": None,
                    "falha_validacao": None, "autocorrecao": [], "avisos_locais": [],
                    "prova_google": {"request_ids": [request_id], "versao_api": "v25",
                                     "validado_em": "2026-10-14T00:00:00+00:00",
                                     "validate_only": True}},
        "autorizacao": {"plano_impressao": "f" * 64, "elegivel": True, "motivo_elegibilidade": ""},
        "destino": {"elegivel": True},
    }


def _foto(*_a):
    return {"campaigns": [{"id": "1", "status": "ENABLED"}], "ads": []}


def _rodar(tmp_path, *, gerar=None, provar=None, fotografar=_foto, reparar=False, preco=None):
    gerar = gerar or _gerar()[0]
    provar = provar or (lambda corpo: _resposta_ok())
    return cn.executar(_pedido(), tmp_path, modelo=MODELO, preco=preco,
                       contexto_de=lambda p: dict(CONTEXTO), gerar=gerar,
                       provar=provar, fotografar=fotografar, reparar=reparar)


def test_schema_de_saida_nao_tem_keyword_url_ou_dinheiro():
    campos = set(cn.CopyGerada.model_json_schema()["properties"])
    assert campos == {"headlines", "descriptions", "sitelinks", "callouts", "lacunas"}
    with pytest.raises(ValueError):
        cn.CopyGerada.model_validate({**COPY, "keywords": ["outra"]})
    with pytest.raises(ValueError):
        cn.CopyGerada.model_validate({**COPY, "budget_diario": 99})


@settings(max_examples=40, deadline=None)
@given(st.floats(min_value=0.01, max_value=5000, allow_nan=False),
       st.floats(min_value=0.01, max_value=50, allow_nan=False))
def test_dinheiro_do_operador_chega_intacto_e_copy_nao_toca_keywords(verba, cpc):
    corpo = cn.corpo_de_provar(_pedido(budget_diario=verba, cpc_inicial=cpc),
                               cn.CopyGerada.model_validate(COPY))
    assert corpo["budget_diario"] == verba and corpo["cpc_inicial"] == cpc
    # A seleção desce do conjunto aprovado DENTRO da rota: o corpo não a carrega.
    assert "grupos" not in corpo and "criterios" not in corpo and "keywords_fora" not in corpo
    assert corpo["canal"] == "SEARCH" and corpo["estrategia_lance"] == "MANUAL_CPC"


def test_pedido_sem_parametro_financeiro_e_recusado():
    base = _pedido().model_dump()
    for campo in ("budget_diario", "cpc_inicial", "estrategia_lance", "rede"):
        dados = {k: v for k, v in base.items() if k != campo}
        with pytest.raises(ValueError):
            cn.Pedido.model_validate(dados)


def test_prompt_nao_leva_conta_nem_dinheiro():
    texto = cn.instrucao(CONTEXTO)
    for proibido in ("5478096539", "6016739364", "budget", "cpc_inicial", "0.5"):
        assert proibido not in texto


def test_aceite_gera_recibo_com_request_id_e_releitura(tmp_path):
    gerar, chamadas = _gerar()
    r = _rodar(tmp_path, gerar=gerar, preco={"entrada_usd_mi": 1.0, "saida_usd_mi": 2.0,
                                             "fonte": "fixture"})
    assert r["status"] == "validate_only_aceito"
    assert r["provar"]["prova_google"]["request_ids"] == ["req-1"]
    assert r["sem_mudanca_na_conta"] is True
    assert r["identidade"].startswith("substituída")
    assert r["custo_usd_estimado"] == pytest.approx(1000 / 1e6 + 400 * 2 / 1e6)
    assert len(chamadas) == 1


def test_sem_preco_o_custo_e_nulo_nunca_zero(tmp_path):
    r = _rodar(tmp_path)
    assert r["custo_usd_estimado"] is None and r["custo_usd_observado"] is None


def test_retomada_reusa_recibo_sem_nova_chamada_e_detecta_adulteracao(tmp_path):
    _rodar(tmp_path)

    def nunca(*_a, **_k):
        raise AssertionError("retomada não pode gastar de novo")
    again = cn.executar(_pedido(), tmp_path, modelo=MODELO, contexto_de=nunca,
                        gerar=nunca, provar=nunca, fotografar=nunca)
    assert again["status"] == "validate_only_aceito"
    corpo = json.loads((tmp_path / "provar-pedido-1.json").read_text())
    corpo["budget_diario"] = 999.0
    (tmp_path / "provar-pedido-1.json").write_text(json.dumps(corpo))
    with pytest.raises(ValueError, match="artefato alterado"):
        cn.executar(_pedido(), tmp_path, modelo=MODELO, contexto_de=nunca,
                    gerar=nunca, provar=nunca, fotografar=nunca)


def test_texto_recusado_permite_um_reparo_dirigido_e_nunca_terceiro(tmp_path):
    falha = (200, {"preparo": {"aprovado": False, "n_operacoes": 20,
                               "falha_validacao": {"erros": [{"texto": "Guia de Cadastro"}]}},
                   "autorizacao": {}, "destino": {}})
    with pytest.raises(cn.TextoRecusado):
        _rodar(tmp_path, provar=lambda c: falha)
    with pytest.raises(ValueError, match="reparo"):
        _rodar(tmp_path)  # sem --reparar não há segunda chamada
    gerar, chamadas = _gerar()
    with pytest.raises(cn.TextoRecusado):
        _rodar(tmp_path, gerar=gerar, provar=lambda c: falha, reparar=True)
    assert "Guia de Cadastro" in chamadas[0] and "CORRIJA SÓ OS TEXTOS CITADOS" in chamadas[0]
    with pytest.raises(ValueError, match="reparo"):
        _rodar(tmp_path, reparar=True)
    assert json.loads((tmp_path / "journal.json").read_text())["generations_started"] == 2


def test_recusa_do_conjunto_nao_e_reparavel_por_texto(tmp_path):
    recusa = (409, {"detail": {"codigo": "CONJUNTO_PAGO_NAO_APROVADO"}})
    with pytest.raises(RuntimeError):
        _rodar(tmp_path, provar=lambda c: recusa)
    with pytest.raises(ValueError, match="reparo"):
        _rodar(tmp_path, reparar=True)


def test_modelo_divergente_ou_resposta_incompleta_nao_chegam_ao_google(tmp_path):
    def nunca(_c):
        raise AssertionError("não podia chamar /provar")
    with pytest.raises(ValueError, match="diverge"):
        _rodar(tmp_path / "a", gerar=_gerar(servido="gemini-outro")[0], provar=nunca)
    with pytest.raises(ValueError, match="incompleta"):
        _rodar(tmp_path / "b", gerar=_gerar(finish=("MAX_TOKENS",))[0], provar=nunca)


def test_mudanca_na_conta_durante_a_prova_fica_registrada(tmp_path):
    fotos = iter([{"campaigns": [], "ads": []}, {"campaigns": [{"id": "9"}], "ads": []}])
    r = _rodar(tmp_path, fotografar=lambda *_a: next(fotos))
    assert r["sem_mudanca_na_conta"] is False


def test_selo_retido_pelo_destino_continua_com_request_id(tmp_path):
    status, corpo = _resposta_ok("req-destino")
    corpo["autorizacao"] = {"plano_impressao": None, "elegivel": False,
                            "motivo_elegibilidade": "destino em rascunho"}
    corpo["preparo"]["selo_retido"] = {"motivos": ["LP_EM_RASCUNHO"]}
    corpo["destino"] = {"elegivel": False}
    r = _rodar(tmp_path, provar=lambda c: (status, corpo))
    assert r["status"] == "validate_only_aceito"
    assert r["provar"]["plano_impressao"] is None
    assert r["provar"]["selo_retido"] == {"motivos": ["LP_EM_RASCUNHO"]}
    assert r["provar"]["prova_google"]["request_ids"] == ["req-destino"]
