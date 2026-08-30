"""Testes da ponte Pautador → Brief. Offline, stdlib, sem Supabase e sem rede.

Rode: `backend/.venv/bin/python -m volc_ads.testes_pautador_ponte` da raiz.

## Como a coleta funciona

O `pytest.ini` da raiz inclui arquivos `testes_*`, mas coleta apenas funções
`test_*` e `prova_*`. Os casos legados `teste_*` continuam no runner manual;
a prova de assinatura abaixo usa `test_*`, portanto roda nos dois caminhos.
O `main()` devolve código de saída e mantém o comando documentado coerente.

## De onde vem o fixture

`_LINHA_REAL` é um RECORTE FIEL da linha `pautador_keyword_clusters#4`
(`opportunity_id=73`), lida do Supabase em 18/08/2026 — keywords, volumes, CPCs,
tags e motivos são os valores originais. ACESSO, VALOR e OUTROS estão INTEIROS;
ELEGIBILIDADE está reduzida a 4 das 26 keywords para o arquivo caber na cabeça.

Por isso as asserções sobre ACESSO (5 de 7 kw, volume 30.430, CPC simples 0,72,
ponderado 0,88) e VALOR (5 de 5, volume 1.980, 1,50 e 1,69) são números
MEDIDOS na linha real e não invenções de fixture — os mesmos que
`python -m volc_ads.pautador_ponte 73` imprime hoje.
"""

from __future__ import annotations

import copy as _copy
import traceback
from typing import Any, get_type_hints

from .campanha.brief import Copy
from .pautador_ponte import (
    Escolha,
    Linhas,
    PonteIncompleta,
    montar_brief,
    montar_cockpit,
)

# ── fixture: recorte fiel da linha #4 ────────────────────────────────────────
_ACESSO_ADS = [
    {"keyword": "banco pan telefone", "volume": 27100, "cpc": 0.93,
     "competition": "LOW", "trend_score": -18, "tags": ["VOLUME_TITAN"],
     "reason": "Massive Volume (27k)"},
    {"keyword": "cartão de crédito caixa telefone", "volume": 1600, "cpc": 0.39,
     "competition": "LOW", "trend_score": 6, "tags": ["HIDDEN_GEM"],
     "reason": "Low Competition / Low Cost"},
    {"keyword": "solicitar cartão caixa poupança", "volume": 1300, "cpc": 0.49,
     "competition": "LOW", "trend_score": -41, "tags": ["HIDDEN_GEM"],
     "reason": "Low Competition / Low Cost"},
    {"keyword": "solicitar cartão de crédito banco pan", "volume": 320, "cpc": 1.05,
     "competition": "MEDIUM", "trend_score": 251,
     "tags": ["EXPLOSIVE_TREND", "EXPLOSIVE_MICRO"],
     "reason": "Low volume but 251% growth"},
    {"keyword": "banco pan cartão de crédito whatsapp", "volume": 110, "cpc": 0.76,
     "competition": "LOW", "trend_score": 277,
     "tags": ["EXPLOSIVE_TREND", "EXPLOSIVE_MICRO"],
     "reason": "Low volume but 277% growth"},
]
# As duas de ACESSO que a triagem mandou para conteúdo — a razão de o ad group
# ter 5 keywords e não 7.
_ACESSO_SEO = [
    {"keyword": "como pedir cartão de crédito pan no app", "volume": 390, "cpc": 1.15,
     "competition": "MEDIUM", "trend_score": -33, "tags": ["USER_QUESTION"], "reason": ""},
    {"keyword": "como fazer cartão da caixa online", "volume": 210, "cpc": 0.41,
     "competition": "MEDIUM", "trend_score": -89,
     "tags": ["DECLINING", "USER_QUESTION"], "reason": ""},
]
_VALOR_ADS = [
    {"keyword": "cartão de crédito limite 3 mil na hora", "volume": 720, "cpc": 2.17,
     "competition": "HIGH", "trend_score": 5000,
     "tags": ["EXPLOSIVE_TREND", "SEASONAL", "EXPLOSIVE_MICRO"],
     "reason": "Low volume but 5000% growth"},
    {"keyword": "cartão de crédito limite 3 mil para negativado", "volume": 720,
     "cpc": 1.49, "competition": "HIGH", "trend_score": 302,
     "tags": ["EXPLOSIVE_TREND", "EXPLOSIVE_MICRO"],
     "reason": "Low volume but 302% growth"},
    {"keyword": "cartão de crédito com limite de 2.000 reais", "volume": 260,
     "cpc": 1.33, "competition": "HIGH", "trend_score": 3040,
     "tags": ["EXPLOSIVE_TREND", "SEASONAL", "EXPLOSIVE_MICRO"],
     "reason": "Low volume but 3040% growth"},
    {"keyword": "cartão de crédito limite 7 mil para negativado", "volume": 170,
     "cpc": 1.57, "competition": "MEDIUM", "trend_score": 967,
     "tags": ["EXPLOSIVE_TREND", "EXPLOSIVE_MICRO"],
     "reason": "Low volume but 967% growth"},
    {"keyword": "cartão de crédito limite 2 mil para negativado", "volume": 110,
     "cpc": 0.96, "competition": "HIGH", "trend_score": 667,
     "tags": ["EXPLOSIVE_TREND", "EXPLOSIVE_MICRO"],
     "reason": "Low volume but 667% growth"},
]
# ELEGIBILIDADE, recorte: 2 na fila de anúncio, 2 só em conteúdo. Uma delas
# ("cartão para negativado aprovado na hora 2026") está nas DUAS filas na linha
# real — é uma das 5 contradições da triagem.
_ELEG_ADS = [
    {"keyword": "cartão de crédito para negativado online", "volume": 480, "cpc": 0.95,
     "competition": "MEDIUM", "trend_score": 12, "tags": ["HIDDEN_GEM"],
     "reason": "Low Competition / Low Cost"},
    {"keyword": "cartão para negativado aprovado na hora 2026", "volume": 480,
     "cpc": 1.8, "competition": "HIGH", "trend_score": 90, "tags": ["CHRONO_2026"],
     "reason": "Year-warped keyword"},
]
_ELEG_SEO = [
    {"keyword": "qual banco libera crédito na hora", "volume": 6600, "cpc": 3.52,
     "competition": "HIGH", "trend_score": -6, "tags": ["USER_QUESTION"], "reason": ""},
    {"keyword": "cartão para negativado aprovado na hora 2026", "volume": 480,
     "cpc": 1.8, "competition": "HIGH", "trend_score": 90, "tags": ["CHRONO_2026"],
     "reason": ""},
]
_OUTROS_SEO = [
    {"keyword": "will bank cobra taxa para liberar empréstimo", "volume": 260,
     "cpc": 0, "competition": "LOW", "trend_score": -83,
     "tags": ["DECLINING", "SEASONAL", "SEASONAL_SPIKE"],
     "reason": "Seasonal spike 3.6x avg (M1)"},
    {"keyword": "will bank empréstimo pessoal", "volume": 140, "cpc": 0.32,
     "competition": "HIGH", "trend_score": -83,
     "tags": ["DECLINING", "SEASONAL", "SEASONAL_SPIKE"],
     "reason": "Seasonal spike 3.2x avg (M12)"},
]


def _sub(tipo: str, descricao: str, entradas: list[dict[str, Any]], volume_sub: int) -> dict[str, Any]:
    """Sub-intenção como o funil a escreve: só keyword, volume e cpc — sem tag,
    sem motivo e SEM dizer se a triagem aprovou para anúncio."""
    return {
        "tipo": tipo, "descricao": descricao, "volume_sub": volume_sub,
        "qtd_keywords": len(entradas),
        "keywords": [{"keyword": e["keyword"], "volume": e["volume"], "cpc": e["cpc"]}
                     for e in entradas],
    }


_CLUSTER: dict[str, Any] = {
    "id": 4, "opportunity_id": 73, "engine": "n8n",
    "main_keyword": "Cartão para Negativado",
    "total_volume": 34940, "avg_cpc_local": None, "currency": None,
    "services_used": ["n8n:google_ads", "n8n:dataforseo", "n8n:gemini"],
    "production_ads_queue": _ACESSO_ADS + _VALOR_ADS + _ELEG_ADS,
    "content_seo_queue": _ACESSO_SEO + _ELEG_SEO + _OUTROS_SEO,
    "summary": {"total_analyzed": 100, "ads_approved": 12,
                "breakdown": {"gems": 20, "discards": 63, "titans": 1}},
    "funis_sugeridos": [{
        "rank": 1, "nome_funil": "Cartões e Crédito Fácil para Negativados",
        "sub_intencoes": [
            _sub("ACESSO", "Contatos telefônicos, apps e meios digitais",
                 _ACESSO_ADS[:3] + [_ACESSO_SEO[0]] + _ACESSO_ADS[3:4]
                 + [_ACESSO_SEO[1]] + _ACESSO_ADS[4:], 31030),
            _sub("ELEGIBILIDADE", "Dúvidas sobre quem libera na hora",
                 _ELEG_SEO[:1] + _ELEG_ADS, 7560),
            _sub("VALOR", "Buscas estritas por montantes de limite", _VALOR_ADS, 1980),
            _sub("OUTROS", "Soluções de crédito adjacentes", _OUTROS_SEO, 400),
        ],
    }],
}

_RUN: dict[str, Any] = {
    "id": 6, "opportunity_id": 73, "project_id": 2, "status": "done",
    "lp_url": "https://creditoup.com.br/?post_type=r&p=2152",
    "artefatos": {"carimbo": "20260817-191650"},
    "paginas_publicadas": [
        {"role": "LP", "slug": "cartao-credito-negativado-2", "post_type": "r",
         "url_wp": "https://creditoup.com.br/?post_type=r&p=2152",
         "status_wp": "draft", "page_number": 1},
        {"role": "PRESELL", "slug": "como-conseguir-cartao-negativado-pr-2",
         "post_type": "rec", "url_wp": "https://creditoup.com.br/?post_type=rec&p=2155",
         "status_wp": "draft", "page_number": 2},
    ],
}

_ENTIDADE: dict[str, Any] = {
    "id": 73, "country_code": "BR", "language": "pt-BR", "vertical": "credito",
    "canonical_name": "Cartão para Negativado",
    "slug": "cartao-de-credito-para-negativado", "cpc_currency": "BRL",
}

_WORDPRESS: dict[str, Any] = {
    "project_id": 2, "wp_url": "https://creditoup.com.br",
    "post_type": "rec", "lp_post_type": "r",
}

_ESTADO: dict[str, Any] = {
    "facts": {"1": {
        "resumo": "Guia completo sobre opções de cartão de crédito para negativados.",
        "dados_validados": [
            {"fato": "O Nu Limite Garantido permite aumentar o limite do cartão "
                     "Nubank usando investimentos como garantia.",
             "fonte": "https://nubank.com.br/"},
        ],
        "fatos_verificados": [
            {"valor": "5", "unidade": "%", "fonte_primaria": "https://www.gov.br/",
             "dispositivo": "Medida Provisória nº 1.355/2026",
             "vigente_desde": "2026-05-19", "verificado_em": "2026-08-17"},
        ],
    }},
    "drafts": {"1": {"format": "lp_json", "word_count": 780, "content":
        '{"hero_title": "Cartão para Negativado", "intro": "<p>O Nubank oferece '
        'o Nu Limite Garantido e o Banco Inter tem o CDB Mais Limite.</p>"}'}},
}


def _linhas(**troca: Any) -> Linhas:
    base = {
        "opportunity_id": 73,
        "cluster": _copy.deepcopy(_CLUSTER),
        "run": _copy.deepcopy(_RUN),
        "entidade": _copy.deepcopy(_ENTIDADE),
        "wordpress": _copy.deepcopy(_WORDPRESS),
        "estado_do_run": _copy.deepcopy(_ESTADO),
        "run_dir": "/tmp/nao-existe",
    }
    base.update(troca)
    return Linhas(**base)


def _grupo(c: Any, tipo: str) -> Any:
    return next(g for g in c.grupos if g.tipo == tipo)


def _codigos(avisos: Any) -> set[str]:
    return {a.codigo for a in avisos}


# ── os testes ────────────────────────────────────────────────────────────────
def teste_ad_group_e_a_intersecao_nao_a_sub_intencao() -> None:
    """ACESSO tem 7 keywords no funil e 5 na fila de anúncio. O grupo leva 5, e
    o volume cai de 31.030 declarados para 30.430 reais — números medidos."""
    c = montar_cockpit(_linhas())
    g = _grupo(c, "ACESSO")
    assert len(g.keywords) == 5, len(g.keywords)
    assert g.keywords_declaradas == 7, g.keywords_declaradas
    assert g.volume == 30430, g.volume
    assert g.volume_declarado == 31030, g.volume_declarado
    assert set(g.fora_da_fila) == {
        "como pedir cartão de crédito pan no app",
        "como fazer cartão da caixa online",
    }, g.fora_da_fila


def teste_os_dois_cpcs_do_grupo() -> None:
    """Simples e ponderado divergem porque uma keyword de 27.100 buscas puxa o
    conjunto. Medido em ACESSO: 0,72 e 0,88; em VALOR: 1,50 e 1,69."""
    c = montar_cockpit(_linhas())
    acesso, valor = _grupo(c, "ACESSO"), _grupo(c, "VALOR")
    assert round(acesso.cpc_simples.valor, 2) == 0.72, acesso.cpc_simples
    assert round(acesso.cpc_ponderado.valor, 2) == 0.88, acesso.cpc_ponderado
    assert valor.volume == 1980, valor.volume
    assert round(valor.cpc_simples.valor, 2) == 1.50, valor.cpc_simples
    assert round(valor.cpc_ponderado.valor, 2) == 1.69, valor.cpc_ponderado


def teste_nenhum_cpc_sai_pelado() -> None:
    """Todo CPC carrega procedência, e a moeda do cluster é NULA de verdade —
    nada aqui pode aparecer na tela como medição."""
    c = montar_cockpit(_linhas())
    todos = [k.cpc for g in c.grupos for k in g.keywords]
    todos += [g.cpc_simples for g in c.grupos] + [g.cpc_ponderado for g in c.grupos]
    todos += [d.cpc for d in c.descartadas]
    assert todos
    for cpc in todos:
        assert cpc.moeda is None, cpc
        assert cpc.medido_na_conta is False, cpc
        assert "services_used" in cpc.procedencia, cpc.procedencia
        assert "n8n:dataforseo" in cpc.procedencia, cpc.procedencia
    assert c.procedencia is not None
    assert c.procedencia.moeda_do_cluster is None
    # A moeda BRL existe, mas na OPORTUNIDADE — nunca promovida a moeda do CPC.
    assert c.procedencia.moeda_da_oportunidade == "BRL"


def teste_sub_intencao_sem_keyword_de_anuncio_nao_vira_ad_group() -> None:
    """OUTROS tem keywords só em conteúdo: some da lista de grupos, mas com
    aviso — grupo que desaparece calado faz procurar o que nunca existiu."""
    c = montar_cockpit(_linhas())
    assert {g.tipo for g in c.grupos} == {"ACESSO", "ELEGIBILIDADE", "VALOR"}
    assert "SUB_INTENCAO_SEM_ANUNCIO" in _codigos(c.avisos)


def teste_keyword_nas_duas_filas_e_marcada() -> None:
    c = montar_cockpit(_linhas())
    marcadas = [k.texto for g in c.grupos for k in g.keywords if k.tambem_em_conteudo]
    assert marcadas == ["cartão para negativado aprovado na hora 2026"], marcadas
    assert "KEYWORD_NAS_DUAS_FILAS" in _codigos(c.avisos)
    # E o texto do aviso traz a keyword com acento, não a chave normalizada.
    aviso = next(a for a in c.avisos if a.codigo == "KEYWORD_NAS_DUAS_FILAS")
    assert "negativado aprovado na hora 2026" in aviso.detalhe


def teste_descartadas_explicam_o_motivo() -> None:
    """A `content_seo_queue` vem com `reason` vazio em boa parte das linhas; a
    tela recebe as tags como motivo, nunca uma célula em branco."""
    c = montar_cockpit(_linhas())
    textos = {d.texto for d in c.descartadas}
    assert "qual banco libera crédito na hora" in textos
    # A que está nas duas filas NÃO conta como descartada.
    assert "cartão para negativado aprovado na hora 2026" not in textos
    assert all(d.motivo for d in c.descartadas)
    assert any("tags:" in d.motivo for d in c.descartadas)


def teste_sem_cluster() -> None:
    c = montar_cockpit(_linhas(cluster=None))
    assert c.bloqueado
    assert "SEM_CLUSTER" in _codigos(c.avisos)
    assert c.grupos == ()
    # A origem continua montada: um card sem cluster mas com funil publicado
    # precisa dizer as duas coisas.
    assert c.origem is not None and c.origem.url_final


def teste_cluster_so_com_conteudo() -> None:
    cluster = _copy.deepcopy(_CLUSTER)
    cluster["content_seo_queue"] = cluster["production_ads_queue"] + cluster["content_seo_queue"]
    cluster["production_ads_queue"] = []
    c = montar_cockpit(_linhas(cluster=cluster))
    assert c.bloqueado
    assert "SEM_FILA_DE_ANUNCIO" in _codigos(c.avisos)
    assert c.grupos == ()
    # Nada de lista vazia muda: as descartadas continuam ali para conferência.
    # A contagem é a de keywords ÚNICAS — a fila tem uma repetida, e contar duas
    # vezes a mesma keyword inflaria a triagem na tela.
    unicas = {e["keyword"] for e in cluster["content_seo_queue"]}
    assert len(c.descartadas) == len(unicas), len(c.descartadas)


def teste_sem_sub_intencoes_vira_grupo_unico() -> None:
    cluster = _copy.deepcopy(_CLUSTER)
    cluster["funis_sugeridos"] = []
    c = montar_cockpit(_linhas(cluster=cluster))
    assert [g.tipo for g in c.grupos] == ["SEM_SUB_INTENCAO"]
    assert len(c.grupos[0].keywords) == len(cluster["production_ads_queue"])
    assert {"SEM_SUB_INTENCOES", "KEYWORD_ORFA"} <= _codigos(c.avisos)


def teste_funil_sem_pagina_publicada() -> None:
    run = _copy.deepcopy(_RUN)
    run["lp_url"] = None
    run["paginas_publicadas"] = []
    c = montar_cockpit(_linhas(run=run))
    assert c.bloqueado
    assert "SEM_LP" in _codigos(c.avisos)
    try:
        montar_brief(c)
    except PonteIncompleta as e:
        assert "SEM_LP" in str(e), str(e)
    else:
        raise AssertionError("montar_brief deveria recusar sem LP")


def teste_sem_funil_nenhum() -> None:
    c = montar_cockpit(_linhas(run=None, wordpress=None, estado_do_run=None))
    assert "SEM_FUNIL" in _codigos(c.avisos)
    assert c.origem is None
    # …mas as keywords continuam visíveis: a mineração não deixou de existir.
    assert len(c.grupos) == 3


def teste_run_que_nao_esta_no_disco() -> None:
    """Sem `state.json` não há fatos nem texto da LP — e a tela precisa saber
    que o cruzamento anúncio × página ficou sem lastro."""
    c = montar_cockpit(_linhas(estado_do_run=None))
    assert "SEM_ARTEFATOS" in _codigos(c.avisos)
    assert not c.bloqueado
    assert c.origem is not None
    assert c.origem.fatos == ()
    assert c.origem.texto_da_lp == ""


def teste_fatos_no_formato_do_prompt() -> None:
    c = montar_cockpit(_linhas())
    assert c.origem is not None
    fatos = c.origem.fatos
    assert len(fatos) == 2, fatos
    assert {f.tipo for f in fatos} == {"afirmacao", "numero"}
    numero = next(f for f in fatos if f.tipo == "numero")
    assert "Medida Provisória nº 1.355/2026" in numero.texto
    assert numero.fonte == "https://www.gov.br/"
    assert all(f.id and f.texto and f.fonte for f in fatos)


def teste_lp_em_rascunho_e_url_provisoria() -> None:
    c = montar_cockpit(_linhas())
    assert {"LP_EM_RASCUNHO", "URL_PROVISORIA"} <= _codigos(c.avisos)
    assert not c.bloqueado  # o operador decide; a ponte não decide por ele


def teste_destino_rec_e_bloqueio() -> None:
    """`/rec/` é navegação interna e nunca destino de anúncio."""
    run = _copy.deepcopy(_RUN)
    run["paginas_publicadas"] = [p for p in run["paginas_publicadas"] if p["role"] != "LP"]
    run["lp_url"] = "https://creditoup.com.br/?post_type=rec&p=2155"
    c = montar_cockpit(_linhas(run=run))
    assert "DESTINO_NAO_E_LP" in _codigos(c.avisos)
    assert c.bloqueado


def teste_idioma_ptbr_vira_pt() -> None:
    """`pt_BR` existe no cache com `segmentavel=False`: passá-lo ao Brief
    levantaria ValueError. O Brief tem de sair com `pt` (criterio 1014)."""
    c = montar_cockpit(_linhas())
    assert c.origem is not None
    assert c.origem.idioma_declarado == "pt-BR"
    assert c.origem.idioma == "pt"
    assert "IDIOMA_TROCADO" in _codigos(c.avisos)
    plano = montar_brief(c, Escolha(cpc_inicial=0.20))
    assert plano.brief.idioma_id == 1014, plano.brief.idioma_id
    assert plano.brief.geo_id == 2076, plano.brief.geo_id


def teste_vertical_credito_vira_financeiro_com_portao() -> None:
    c = montar_cockpit(_linhas())
    assert c.origem is not None
    assert c.origem.vertical_declarada == "credito"
    assert c.origem.vertical == "financeiro"
    aviso = next(a for a in c.avisos if a.codigo == "HABILITACAO_EXIGIDA")
    assert "verificacao_servicos_financeiros" in aviso.titulo
    # A severidade do Google vai no texto, mas não bloqueia o Brief: a conta
    # pode já estar verificada, e isso se lê em `customer.*`, não aqui.
    assert aviso.severidade == "atencao"
    assert "bloqueio" in aviso.detalhe


def teste_vertical_desconhecida_nao_vira_informativo_calado() -> None:
    ent = _copy.deepcopy(_ENTIDADE)
    ent["vertical"] = "criptomoedas"
    c = montar_cockpit(_linhas(entidade=ent))
    assert c.origem is not None and c.origem.vertical == "informativo"
    assert "VERTICAL_DESCONHECIDA" in _codigos(c.avisos)


def teste_brief_herda_do_funil() -> None:
    c = montar_cockpit(_linhas())
    plano = montar_brief(c, Escolha(cpc_inicial=0.20, budget_diario=10.0))
    b = plano.brief
    assert b.url_final == "https://creditoup.com.br/?post_type=r&p=2152"
    assert b.nicho == "Cartão para Negativado"
    assert b.slug == "cartao-credito-negativado-2"
    assert b.pais == "BR" and b.vertical == "financeiro"
    # Um ad group por sub-intenção: as keywords vão em `sub_intencoes`, e
    # `keywords` fica vazia porque o `Brief` recusa as duas formas juntas.
    assert b.keywords == []
    assert [s.nome for s in b.sub_intencoes] == ["ACESSO", "ELEGIBILIDADE", "VALOR"]
    assert sum(len(s.keywords) for s in b.sub_intencoes) == 12
    assert [len(g.keywords) for g in b.grupos()] == [5, 2, 5]
    assert len(plano.grupos) == 3
    # Sem lance por grupo declarado, todos herdam o da campanha — e isso é dito.
    assert all(s.cpc_inicial is None for s in b.sub_intencoes)
    assert "GRUPO_SEM_LANCE_PROPRIO" in _codigos(plano.avisos)


def test_carimbo_atravessa_a_escolha_ate_o_brief() -> None:
    """A fronteira é estrita e preserva o nome aprovado até o construtor."""
    carimbo = "20260828_120000"
    escolha = Escolha(cpc_inicial=0.20, carimbo_nome=carimbo)

    assert get_type_hints(Escolha)["carimbo_nome"] == str | None
    assert escolha.carimbo_nome == carimbo
    assert montar_brief(
        montar_cockpit(_linhas()), escolha,
    ).brief.carimbo_nome == carimbo

    try:
        Escolha(carimbo_inexistente=carimbo)  # type: ignore[call-arg]
    except TypeError:
        pass
    else:
        raise AssertionError("Escolha aceitou um parâmetro fora do contrato")


def teste_escolha_de_grupos_e_de_keywords_recalcula() -> None:
    c = montar_cockpit(_linhas())
    plano = montar_brief(c, Escolha(
        grupos=("ACESSO",), keywords_fora=frozenset({"banco pan telefone"}),
        cpc_inicial=0.20,
    ))
    assert len(plano.grupos) == 1
    g = plano.grupos[0]
    assert len(g.keywords) == 4
    # Desmarcar `banco pan telefone` (27.100 buscas a 0,93) derruba o volume de
    # 30.430 para 3.330 E o CPC ponderado de 0,88 para 0,50: a keyword titã era
    # também a cara, e sozinha decidia os dois números do grupo. É exatamente o
    # que a régua de leilão do §5.3 precisa mostrar enquanto o operador marca.
    assert g.volume == 3330, g.volume
    assert round(g.cpc_ponderado.valor, 2) == 0.50, g.cpc_ponderado
    todas = [k for s in plano.brief.sub_intencoes for k in s.keywords]
    assert "banco pan telefone" not in todas
    assert len(todas) == 4


def teste_grupo_unico_sintetico_vira_lista_chapada() -> None:
    """Sem sub-intenção no cluster não há divisão a preservar: o Brief sai com
    `keywords` chapada, e `Brief.grupos()` devolve o grupo-sentinela `—` que faz
    `search.py` manter o nome histórico `AdGroup_{carimbo}`."""
    from .campanha.brief import SEM_SUB_INTENCAO

    cluster = _copy.deepcopy(_CLUSTER)
    cluster["funis_sugeridos"] = []
    c = montar_cockpit(_linhas(cluster=cluster))
    b = montar_brief(c, Escolha(cpc_inicial=0.2)).brief
    assert b.sub_intencoes == []
    assert len(b.keywords) == 12
    assert [g.nome for g in b.grupos()] == [SEM_SUB_INTENCAO]


def teste_lance_por_grupo_e_certificacoes_chegam_ao_brief() -> None:
    """Os dois campos que só o operador pode preencher: lance medido na conta
    por sub-intenção, e o que a conta comprova ter."""
    c = montar_cockpit(_linhas())
    b = montar_brief(c, Escolha(
        cpc_inicial=0.20,
        cpc_por_grupo={"ACESSO": 0.18, "VALOR": 0.42},
        certificacoes=("verificacao_servicos_financeiros",),
    )).brief
    por_nome = {s.nome: s.cpc_inicial for s in b.sub_intencoes}
    assert por_nome == {"ACESSO": 0.18, "ELEGIBILIDADE": None, "VALOR": 0.42}
    assert b.certificacoes == {"verificacao_servicos_financeiros"}


def teste_grupo_inexistente_recusa() -> None:
    c = montar_cockpit(_linhas())
    try:
        montar_brief(c, Escolha(grupos=("INVENTADO",), cpc_inicial=0.2))
    except PonteIncompleta as e:
        assert "INVENTADO" in str(e)
    else:
        raise AssertionError("deveria recusar grupo inexistente")


def teste_escolha_vazia_recusa() -> None:
    c = montar_cockpit(_linhas())
    fora = frozenset(k.texto for g in c.grupos for k in g.keywords)
    try:
        montar_brief(c, Escolha(keywords_fora=fora, cpc_inicial=0.2))
    except PonteIncompleta as e:
        assert "nenhuma keyword" in str(e)
    else:
        raise AssertionError("deveria recusar escolha vazia")


def teste_lance_nao_herda_do_cpc_minerado() -> None:
    """O CPC minerado superestima 7,4× e inverte a ordem. Sem lance declarado o
    Brief fica no default e SAI AVISO — nunca no número minerado."""
    c = montar_cockpit(_linhas())
    plano = montar_brief(c)
    assert "CPC_NAO_DECLARADO" in _codigos(plano.avisos)
    minerados = {round(k.cpc.valor, 2) for g in c.grupos for k in g.keywords}
    assert round(plano.brief.cpc_inicial, 2) not in minerados or plano.brief.cpc_inicial == 0.12
    assert plano.brief.cpc_inicial == 0.12  # o default do Brief, não o do cluster


def teste_copy_vazia_avisa() -> None:
    c = montar_cockpit(_linhas())
    assert "COPY_VAZIA" in _codigos(montar_brief(c, Escolha(cpc_inicial=0.2)).avisos)
    com_copy = montar_brief(c, Escolha(cpc_inicial=0.2),
                            copy=Copy(headlines=["Cartão para Negativado 2026"]))
    assert "COPY_VAZIA" not in _codigos(com_copy.avisos)


def teste_negativa_que_aparece_no_texto_da_lp() -> None:
    """O defeito medido no brief do FGTS: negativar as marcas que a própria LP
    usa como argumento."""
    c = montar_cockpit(_linhas())
    plano = montar_brief(c, Escolha(
        cpc_inicial=0.2, negativas_campanha=("nubank", "inter", "consignado")))
    aviso = next(a for a in plano.avisos if a.codigo == "NEGATIVA_NO_TEXTO_DA_LP")
    assert "nubank" in aviso.detalhe and "inter" in aviso.detalhe
    assert "consignado" not in aviso.detalhe


def teste_porta_avulsa_satisfaz_o_destino() -> None:
    """Colar a URL à mão SATISFAZ o requisito de destino (não o afrouxa), e a
    perda da herança é declarada."""
    run = _copy.deepcopy(_RUN)
    run["lp_url"] = None
    run["paginas_publicadas"] = []
    c = montar_cockpit(_linhas(run=run))
    plano = montar_brief(c, Escolha(
        url_final="https://creditoup.com.br/r/cartao-para-negativado/", cpc_inicial=0.2))
    assert plano.brief.url_final.endswith("/cartao-para-negativado/")
    assert "URL_MANUAL" in _codigos(plano.avisos)


def teste_destino_http_recusado() -> None:
    c = montar_cockpit(_linhas())
    try:
        montar_brief(c, Escolha(url_final="http://creditoup.com.br/x/", cpc_inicial=0.2))
    except PonteIncompleta as e:
        assert "https" in str(e)
    else:
        raise AssertionError("deveria recusar destino sem https")


def teste_bloqueio_nao_tem_valvula_de_escape() -> None:
    """Portão é decisão binária: `montar_brief` não aceita nenhum argumento que
    ignore um bloqueio. Se um dia aceitar, este teste quebra de propósito."""
    import inspect

    nomes = set(inspect.signature(montar_brief).parameters)
    assert nomes == {"cockpit", "escolha", "copy"}, nomes


def teste_triagem_usa_o_denominador_honesto() -> None:
    """`total_analyzed` é 100; somar o breakdown daria outro número porque uma
    keyword carrega várias tags."""
    c = montar_cockpit(_linhas())
    assert c.triagem is not None
    t = c.triagem
    assert t.analisadas == 100
    assert t.aprovadas_anuncio == 12  # o fixture tem 12; a linha real tem 23
    assert t.descartadas == 63
    assert t.volume_da_fila == sum(
        e["volume"] for e in _CLUSTER["production_ads_queue"])
    assert "TRIAGEM_DIVERGE" not in _codigos(c.avisos)


def teste_cockpit_vira_json() -> None:
    d = montar_cockpit(_linhas()).para_json()
    assert d["bloqueado"] is False
    assert d["grupos"][0]["cpc_ponderado"]["procedencia"]
    assert d["grupos"][0]["cpc_ponderado"]["moeda"] is None
    assert d["origem"]["fatos"][0]["fonte"]


def main() -> int:
    testes = [(n, f) for n, f in sorted(globals().items())
              if n.startswith(("teste_", "test_", "prova_")) and callable(f)]
    falhas = 0
    for nome, fn in testes:
        try:
            fn()
            print(f"  ok    {nome}")
        except Exception:  # noqa: BLE001 — o relatório é o produto aqui
            falhas += 1
            print(f"  FALHA {nome}")
            print("        " + traceback.format_exc().replace("\n", "\n        "))
    print(f"\n{len(testes) - falhas}/{len(testes)} passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
