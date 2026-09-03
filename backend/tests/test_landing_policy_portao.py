"""O portão do destino pago: contrato, papéis, fecha-por-ausência e recibo.

Estes testes são o oposto de "o portão roda": eles perguntam se o portão
REPROVA o que precisa reprovar e se ele se recusa a ficar verde quando não
conseguiu olhar. Um portão que só é testado pelo caminho feliz é um carimbo.
"""
from __future__ import annotations

import json
import re

import pytest

from app.landing_policy import (
    PaginaObservada,
    PapelDestino,
    PontoDePortao,
    Veredito,
    avaliar,
    carregar_fontes,
    codigos_conhecidos,
    elegibilidade_de_destino_de_campanha,
    emitir_recibo,
    fonte_do_codigo,
    impressao,
    json_deterministico,
    sem_fonte_oficial,
    severidade,
    versao_da_fonte,
)
from app.landing_policy.contrato import (
    EXIGENCIAS_POR_PONTO,
    HOSTS_OFICIAIS,
    POLICY_CONTRACT_VERSION,
    SEVERIDADE_BLOQUEIO,
    V_DERIVA,
    V_REDIRECIONAMENTO,
)
from app.landing_policy.varredura import VARREDURAS

#: Congelado: comparar frescor exige uma referência estável entre execuções.
AGORA = 1_767_225_600.0  # 2026-01-01T00:00:00Z

CNPJ = "42.724.548/0001-24"

RODAPE_LIMPO = """
<p>Sobre o nosso site: portal informativo independente.</p>
<p>Os conteúdos aqui publicados são de caráter informativo e não possuem vínculo,
parceria ou qualquer ligação com órgãos públicos ou entidades governamentais.</p>
<p>O site é financiado por blocos de anúncios em parceria com o Google Adsense.</p>
<p>Projeto da Volc Negocios Digitais 42.724.548/0001-24.</p>
<a href="/sobre">Sobre</a> <a href="/contato">Contato</a>
<a href="/politica-de-privacidade">Política de Privacidade</a> <a href="/termos">Termos</a>
"""

CORPO_LONGO = " ".join(
    [
        "O texto explica com calma as regras vigentes e como o leitor confere cada",
        "informação no canal oficial, sem prometer resultado nenhum.",
    ]
    * 90
)


def pagina(html: str, **kwargs) -> PaginaObservada:
    base = {
        "url": "https://exemplo.com.br/r/pagina-de-teste/",
        "html": html,
        "status_http": 200,
        "saltos_redirecionamento": [],
        "variantes_sha256": {"user": "a" * 64, "googlebot": "a" * 64},
        "sha256_observado": "a" * 64,
        "sha256_aprovado": "a" * 64,
        "cnpj_esperado": CNPJ,
    }
    base.update(kwargs)
    return PaginaObservada(**base)


#: O recibo que uma página APROVADA carrega na v2. Ele entra em `pagina_limpa`
#: porque, a partir da espinha v2, elegibilidade de campanha sem recibo
#: resolvível reprova — e uma "página limpa" que não conseguisse ficar verde
#: provaria só que a fixture ficou velha.
def recibo_valido(**kwargs) -> dict:
    base = {
        "policy_contract_version": POLICY_CONTRACT_VERSION,
        "policy_source_version": versao_da_fonte(),
        "observed_at_epoch": AGORA - 60,
        "content_sha256": "a" * 64,
        "paid_destination_ready": True,
    }
    base.update(kwargs)
    return base


def pagina_limpa(**kwargs) -> PaginaObservada:
    html = f"<html><body><h1>Guia informativo</h1><p>{CORPO_LONGO}</p>{RODAPE_LIMPO}</body></html>"
    kwargs.setdefault("recibo_de_aprovacao", recibo_valido())
    kwargs.setdefault("avaliado_em_epoch", AGORA)
    return pagina(html, **kwargs)


def codigos(avaliacao) -> set[str]:
    return {a.codigo for a in avaliacao.bloqueios + avaliacao.riscos + avaliacao.observacoes}


# ── a linha de base: o portão consegue aprovar ─────────────────────────────


def test_pagina_limpa_fica_pronta_para_destino_pago():
    """Sem esta prova, todo o resto é um portão que só sabe dizer não.

    Um portão que nunca aprova é indistinguível de um portão quebrado, e a
    operação aprende a ignorá-lo — que é a pior falha possível num portão.
    """
    av = elegibilidade_de_destino_de_campanha(pagina_limpa())
    assert av.bloqueios == [], [a.codigo for a in av.bloqueios]
    assert av.desconhecidos == [], av.desconhecidos
    assert av.paid_destination_ready is True
    assert av.veredito in (Veredito.APROVADO, Veredito.APROVADO_COM_RESSALVAS)


def test_a_mesma_pagina_limpa_sem_recibo_nao_e_elegivel():
    """O simétrico da prova acima, e a mudança de contrato da espinha v2.

    Até a v1, esta MESMA página ficava verde para campanha sem nenhum recibo —
    o portão não tinha como saber se o que estava no ar era o que a casa
    aprovou, e `DERIVA_AO_VIVO` saía `unavailable` nos quatro destinos reais.
    A v2 fecha por ausência também aqui.
    """
    av = elegibilidade_de_destino_de_campanha(pagina_limpa(recibo_de_aprovacao=None))
    assert av.paid_destination_ready is False
    assert "RECIBO_DE_APROVACAO_AUSENTE" in {a.codigo for a in av.bloqueios}


# ── fecha por ausência ─────────────────────────────────────────────────────


def test_verificacao_exigida_indisponivel_impede_o_verde():
    """`unavailable` numa verificação exigida NÃO é 'sem achados'."""
    av = elegibilidade_de_destino_de_campanha(
        pagina_limpa(saltos_redirecionamento=None, variantes_sha256={})
    )
    assert av.paid_destination_ready is False
    assert [d["verificacao"] for d in av.desconhecidos] == [V_REDIRECIONAMENTO]  # noqa: E501
    assert av.veredito is Veredito.INDETERMINADO


def test_sem_hash_aprovado_a_deriva_e_desconhecida_e_nao_limpa():
    av = elegibilidade_de_destino_de_campanha(pagina_limpa(sha256_aprovado=None))
    assert av.paid_destination_ready is False
    assert any(d["verificacao"] == V_DERIVA for d in av.desconhecidos)


def test_varredura_que_explode_vira_failed_e_reprova(monkeypatch):
    """Exceção numa varredura não pode virar 'nada encontrado'."""

    def explode(_pagina):
        raise RuntimeError("parser caiu")

    monkeypatch.setitem(VARREDURAS, "identity", explode)
    av = elegibilidade_de_destino_de_campanha(pagina_limpa())
    assert av.paid_destination_ready is False
    assert any(d["verificacao"] == "identity" and d["status"] == "failed" for d in av.desconhecidos)


def test_antes_de_publicar_redirecionamento_nao_e_exigido():
    """Ausência estrutural não é buraco: antes do ar não há salto para observar."""
    av = avaliar(
        pagina_limpa(saltos_redirecionamento=None, variantes_sha256={}, sha256_observado=None),
        PapelDestino.PAID_DESTINATION,
        PontoDePortao.PRE_PUBLICACAO_WORDPRESS,
    )
    assert av.desconhecidos == [], av.desconhecidos
    assert av.paid_destination_ready is True


def test_no_ponto_da_campanha_tudo_e_exigido():
    assert EXIGENCIAS_POR_PONTO[PontoDePortao.ELEGIBILIDADE_DESTINO_CAMPANHA] >= {
        V_REDIRECIONAMENTO,
        V_DERIVA,
    }


# ── papel ──────────────────────────────────────────────────────────────────


def test_papel_muda_a_severidade_do_mesmo_defeito():
    html = f"<html><body><h1>t</h1><p>{CORPO_LONGO}</p></body></html>"
    pago = avaliar(pagina(html), PapelDestino.PAID_DESTINATION, PontoDePortao.ARTEFATO_DE_GERACAO)
    organico = avaliar(
        pagina(html), PapelDestino.ORGANIC_ARTICLE, PontoDePortao.ARTEFATO_DE_GERACAO
    )
    assert "IDENTIDADE_OPERADOR_AUSENTE" in {a.codigo for a in pago.bloqueios}
    assert "IDENTIDADE_OPERADOR_AUSENTE" not in {a.codigo for a in organico.bloqueios}
    assert "IDENTIDADE_OPERADOR_AUSENTE" in codigos(organico)


def test_papel_nao_pago_nunca_declara_destino_pago_pronto():
    av = avaliar(pagina_limpa(), PapelDestino.ORGANIC_ARTICLE, PontoDePortao.ARTEFATO_DE_GERACAO)
    assert av.veredito is Veredito.APROVADO or av.veredito is Veredito.APROVADO_COM_RESSALVAS
    assert av.paid_destination_ready is False
    assert any("paid_destination" in m for m in av.motivos)


def test_elegibilidade_de_campanha_forca_o_papel_pago():
    """O ponto 3 não aceita papel do chamador — senão o portão é desligável."""
    av = elegibilidade_de_destino_de_campanha(pagina_limpa())
    assert av.papel is PapelDestino.PAID_DESTINATION
    assert av.ponto is PontoDePortao.ELEGIBILIDADE_DESTINO_CAMPANHA


def test_codigo_novo_sem_classificacao_bloqueia_no_papel_estrito():
    assert severidade("CODIGO_QUE_NINGUEM_CLASSIFICOU", PapelDestino.PAID_DESTINATION) == (
        SEVERIDADE_BLOQUEIO
    )
    assert severidade("CODIGO_QUE_NINGUEM_CLASSIFICOU", PapelDestino.CONVERSION_PAGE) == (
        SEVERIDADE_BLOQUEIO
    )


# ── fonte oficial ──────────────────────────────────────────────────────────


def test_todo_codigo_conhecido_tem_fonte_oficial_do_google():
    fontes = carregar_fontes()
    faltando = sorted(c for c in codigos_conhecidos() if not fonte_do_codigo(c, fontes))
    assert faltando == [], f"regra sem fonte oficial: {faltando}"


def test_a_matriz_de_fontes_esta_completa_e_so_cita_o_google():
    fontes = carregar_fontes()
    obrigatorios = {
        "policy",
        "url",
        "consulted_at",
        "applicability",
        "evidence",
        "result",
        "confidence",
        "correction",
    }
    for codigo, regra in fontes["rules"].items():
        faltando = obrigatorios - set(regra)
        assert not faltando, f"{codigo} sem {sorted(faltando)}"
        assert regra["confidence"] in {"high", "medium", "low"}, codigo
        host = re.sub(r"^https://([^/]+)/.*$", r"\1", regra["url"])
        assert host in HOSTS_OFICIAIS, f"{codigo} cita host não oficial: {host}"
        assert regra["url"].startswith("https://"), codigo


def test_a_matriz_nao_carrega_regra_que_o_portao_nao_emite():
    """Fonte para código inexistente é matriz mentindo sobre cobertura."""
    fontes = carregar_fontes()
    sobrando = sorted(set(fontes["rules"]) - set(codigos_conhecidos()))
    assert sobrando == [], f"fonte sem regra correspondente: {sobrando}"


def test_avaliacao_real_nunca_emite_codigo_sem_fonte():
    av = elegibilidade_de_destino_de_campanha(pagina_limpa())
    assert sem_fonte_oficial(av) == []


def test_versao_da_politica_muda_quando_a_matriz_muda():
    fontes = carregar_fontes()
    antes = versao_da_fonte(fontes)
    fontes["rules"]["PAGINA_PONTE"]["correction"] = "outra coisa"
    assert versao_da_fonte(fontes) != antes


# ── recibo ─────────────────────────────────────────────────────────────────


def test_recibo_carrega_tudo_que_o_handoff_precisa_citar():
    av = elegibilidade_de_destino_de_campanha(pagina_limpa())
    recibo = emitir_recibo(
        av, hash_do_conteudo="b" * 64, referencias_de_evidencia=["evidence-public/x.html"]
    )
    for campo in (
        "url",
        "content_sha256",
        "observed_at",
        "policy_source_version",
        "inventory_hashes",
        "identity_result",
        "security_result",
        "verdict",
        "blockers",
        "unknowns",
        "evidence_refs",
        "paid_destination_ready",
        "external_mutation",
    ):
        assert campo in recibo, campo
    assert recibo["content_sha256"] == "b" * 64
    assert recibo["external_mutation"] == {
        "google_ads_mutate": False,
        "wordpress_write": False,
        "appeal_submitted": False,
        "deploy": False,
    }
    for nome in ("external_links", "forms_and_sensitive_data", "claims_and_disclosures"):
        assert len(recibo["inventory_hashes"][nome]["sha256"]) == 64


def test_recibo_e_deterministico_para_o_mesmo_artefato():
    av1 = elegibilidade_de_destino_de_campanha(pagina_limpa())
    av2 = elegibilidade_de_destino_de_campanha(pagina_limpa())
    a = json_deterministico(emitir_recibo(av1, hash_do_conteudo="c" * 64))
    b = json_deterministico(emitir_recibo(av2, hash_do_conteudo="c" * 64))
    assert a == b


def test_hash_de_inventario_muda_quando_o_inventario_muda():
    limpa = elegibilidade_de_destino_de_campanha(pagina_limpa())
    com_link = elegibilidade_de_destino_de_campanha(
        pagina(
            f"<html><body><h1>t</h1><p>{CORPO_LONGO}</p>"
            f'<a href="https://terceiro-desconhecido.example/x">saiba mais aqui</a>'
            f"{RODAPE_LIMPO}</body></html>"
        )
    )
    def h(av):
        return {v.nome: v.hash_inventario() for v in av.verificacoes}["external_links"]

    assert h(limpa) != h(com_link)


def test_recibo_com_bloqueio_nunca_sai_pronto():
    av = elegibilidade_de_destino_de_campanha(
        pagina(f"<html><body><h1>t</h1><p>{CORPO_LONGO}</p></body></html>")
    )
    recibo = emitir_recibo(av, hash_do_conteudo="d" * 64)
    assert recibo["paid_destination_ready"] is False
    assert recibo["verdict"] == Veredito.BLOQUEADO.value
    assert recibo["blockers"]
    assert recibo["not_ready_reasons"]
    for bloqueio in recibo["blockers"]:
        assert bloqueio["policy"]["url"].startswith("https://support.google.com/")


def test_impressao_e_estavel_e_independente_da_ordem_das_chaves():
    assert impressao({"a": 1, "b": [2, 3]}) == impressao({"b": [2, 3], "a": 1})
    assert impressao({"a": 1}) != impressao({"a": 2})


def test_json_do_recibo_e_carregavel():
    av = elegibilidade_de_destino_de_campanha(pagina_limpa())
    texto = json_deterministico(emitir_recibo(av, hash_do_conteudo="e" * 64))
    assert json.loads(texto)["schema"] == "LandingPolicyGateReceipt"


@pytest.mark.parametrize("papel", list(PapelDestino))
def test_todo_papel_e_avaliavel_em_todo_ponto(papel):
    for ponto in PontoDePortao:
        av = avaliar(pagina_limpa(), papel, ponto)
        assert av.papel is papel and av.ponto is ponto
