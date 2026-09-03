"""As duas rotas que faltavam entre decidir e assinar o conjunto pago.

## O buraco que estas provas guardam

Medido em 03/09/2026: `paid_eligibility.aprovar()` não tinha CHAMADOR DE
PRODUÇÃO — os 9 call sites eram todos de teste. Quem produz o conjunto
(`funnel_factory.py:391`) grava `conjunto_pago` sem `approved_set_sha256`, e
`portao_conjunto_pago.py:158` recusa exatamente esse estado com
`CONJUNTO_PAGO_NAO_APROVADO`. Consequência: `/provar` e `/subir` devolviam 409
e a campanha Search não nascia pelo caminho normal.

O motor decidia bem e ninguém podia assinar a decisão. Estas provas travam a
porta que passou a existir — e travam, principalmente, o que ela RECUSA.

## Hermético de propósito

O Supabase é um dublê (`_SupaFalso`): estas provas medem a rota, não a rede.
Nenhuma delas escreve em `pautador_keyword_clusters` de verdade, e a que
verifica a persistência lê o que a rota MANDARIA gravar.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.agents.mining.paid_eligibility import (
    INCLUDE,
    MEDIDO,
    PHRASE,
    CampaignKeywordSet,
    PaidKeywordDecision,
    Sinal,
)
from app.main import app

client = TestClient(app)

#: O e-mail do dublê de identidade de `conftest.py`. `aprovado_por` tem de sair
#: DAQUI e não do corpo do pedido — assinatura escolhida pelo assinado não é
#: assinatura.
OPERADOR = "teste@agenciavolc.com.br"


def _decisao(termo: str, *, volume: Optional[float], cpc: Optional[float]) -> PaidKeywordDecision:
    """Uma decisão já tomada, reidratável. Ausência entra como ausência.

    `Sinal` recusa `Sinal(0.0, "absent")` por construção, então não há como
    este fixture fabricar um zero de ausência sem que o motor levante — que é
    exatamente a garantia que ele existe para dar.
    """
    return PaidKeywordDecision(
        termo=termo,
        termo_normalizado=termo,
        subintencao="ACESSO",
        match_type=PHRASE,
        volume=(Sinal(volume, MEDIDO, fonte="google_ads")
                if volume is not None else Sinal.ausente("nao_lido")),
        cpc=(Sinal(cpc, MEDIDO, fonte="google_ads")
             if cpc is not None else Sinal.ausente("nao_lido")),
        decisao=INCLUDE,
        motivos=["volume medido e CPC dentro do teto"],
        selecionada=True,
    )


def _conjunto() -> CampaignKeywordSet:
    selecionadas = [
        _decisao("banco pan telefone", volume=27100, cpc=0.93),
        # Sem volume e sem CPC: é ela que prova que ausência viaja como `null`.
        _decisao("banco pan cartão de crédito whatsapp", volume=None, cpc=None),
    ]
    return CampaignKeywordSet(candidates=list(selecionadas),
                              selected_keywords=selecionadas)


def _cluster(conjunto: Optional[CampaignKeywordSet] = None) -> Dict[str, Any]:
    """Um cluster com DOIS funis, e o conjunto pago no segundo.

    Dois de propósito: `factory_output` é um array com um item por funil, e a
    escrita substitui a coluna inteira. Um fixture de um funil só não veria a
    rota apagar o outro.
    """
    conjunto = conjunto or _conjunto()
    return {
        "id": 4,
        "opportunity_id": 73,
        "run_id": 9,
        "factory_output": [
            {"project_name": "funil-sem-conjunto",
             "keywords_campanha": {"lista_google_ads": "outra coisa"}},
            {"project_name": "funil-com-conjunto",
             "keywords_campanha": {
                 "lista_google_ads": "banco pan telefone",
                 "conjunto_pago": conjunto.como_dicionario(),
             }},
        ],
    }


class _SupaFalso:
    """O dublê. Guarda o que a rota mandaria gravar, e não grava nada."""

    ultimo: Dict[str, Any] = {}

    def __init__(self, settings: Any = None) -> None:
        pass

    enabled = True

    async def get_latest_cluster(self, opportunity_id: int) -> Optional[Dict[str, Any]]:
        return _SupaFalso.ultimo.get("cluster")

    async def patch(self, tabela: str, match: Dict[str, str],
                    valores: Dict[str, Any]) -> List[Dict[str, Any]]:
        _SupaFalso.ultimo["patch"] = {"tabela": tabela, "match": match, "valores": valores}
        return [{"id": 4}]


@pytest.fixture(autouse=True)
def supa_falso(monkeypatch):
    _SupaFalso.ultimo = {"cluster": _cluster()}
    monkeypatch.setattr("app.routers.pautador.SupabaseService", _SupaFalso)
    yield
    _SupaFalso.ultimo = {}


def _impressao() -> str:
    return _conjunto().selected_set_sha256


# ── leitura ────────────────────────────────────────────────────────────────
def test_get_devolve_a_impressao_e_o_veredito_do_servidor():
    r = client.get("/api/pautador/opportunities/73/conjunto-pago")
    assert r.status_code == 200, r.text
    corpo = r.json()

    assert corpo["opportunity_id"] == 73
    assert corpo["cluster_id"] == 4
    # ⚠️ A impressão é RECALCULADA das decisões, nunca lida do registro.
    assert corpo["selected_set_sha256"] == _impressao()
    assert corpo["approved_set_sha256"] is None
    assert corpo["aprovado_por"] is None
    assert corpo["pode_aprovar"] is True
    assert corpo["porque_nao"] is None
    assert corpo["blockers"] == []

    termos = [k["termo"] for k in corpo["selecionadas"]]
    assert termos == ["banco pan telefone", "banco pan cartão de crédito whatsapp"]

    medida, ausente = corpo["selecionadas"]
    assert medida["volume"] == 27100
    assert medida["cpc"]["valor"] == 0.93
    assert medida["cpc"]["medido_na_conta"] is True
    # ⚠️ Ausência viaja como `null`, e o objeto de CPC continua viajando com a
    # procedência: "não medido, fonte X" é informação; `0.0` seria a afirmação
    # de que o clique é de graça.
    assert ausente["volume"] is None
    assert ausente["cpc"]["valor"] is None
    assert ausente["cpc"]["medido_na_conta"] is False
    assert ausente["cpc"]["procedencia"]
    # A moeda não é declarada em lugar nenhum do conjunto — e não é inventada.
    assert ausente["cpc"]["moeda"] is None


def test_get_de_conjunto_ja_aprovado_diz_que_nao_ha_o_que_aprovar():
    conjunto = _conjunto()
    conjunto.approved_set_sha256 = conjunto.selected_set_sha256
    conjunto.aprovado_por = "outra.pessoa@agenciavolc.com.br"
    _SupaFalso.ultimo["cluster"] = _cluster(conjunto)

    corpo = client.get("/api/pautador/opportunities/73/conjunto-pago").json()
    assert corpo["pode_aprovar"] is False
    assert "já está aprovado" in corpo["porque_nao"]
    assert corpo["aprovado_por"] == "outra.pessoa@agenciavolc.com.br"


def test_get_sem_cluster_e_404_e_nao_um_corpo_inventado():
    """Um corpo de revisão exige uma impressão. Sem cluster não há impressão, e
    uma tela de conferência com hash inventado é pior que uma que não abre."""
    _SupaFalso.ultimo["cluster"] = None
    r = client.get("/api/pautador/opportunities/73/conjunto-pago")
    assert r.status_code == 404
    assert "Minere a oportunidade" in r.json()["detail"]


# ── o ato ──────────────────────────────────────────────────────────────────
def test_post_com_hash_divergente_recusa_e_nao_congela():
    """⚠️ O conjunto mudou entre a conferência e o clique: a assinatura não vale
    para ele, e NADA pode ser gravado."""
    r = client.post(
        "/api/pautador/opportunities/73/conjunto-pago/aprovar",
        json={"opportunity_id": 73, "hash_conferido": "0" * 64,
              "motivo": "conferi os termos um a um na tela"},
    )
    assert r.status_code == 409, r.text
    assert "reconferir" in r.json()["detail"] or "confira a impressão nova" in r.json()["detail"]
    assert "patch" not in _SupaFalso.ultimo, "gravou apesar do hash divergente"


def test_post_com_motivo_curto_recusa_com_422():
    r = client.post(
        "/api/pautador/opportunities/73/conjunto-pago/aprovar",
        json={"hash_conferido": _impressao(), "motivo": "ok"},
    )
    assert r.status_code == 422, r.text
    assert "por que" in r.json()["detail"]
    assert "patch" not in _SupaFalso.ultimo


def test_post_feliz_congela_assina_e_preserva_os_outros_funis():
    impressao = _impressao()
    r = client.post(
        "/api/pautador/opportunities/73/conjunto-pago/aprovar",
        json={"opportunity_id": 73, "run_id": 9, "hash_conferido": impressao,
              "motivo": "conferi termo a termo contra a LP publicada"},
    )
    assert r.status_code == 200, r.text
    recibo = r.json()

    # O selo é a impressão do conjunto apresentado. Não um hash novo.
    assert recibo["approved_set_sha256"] == impressao
    # ⚠️ E o assinante é a identidade AUTENTICADA, não um campo do corpo.
    assert recibo["aprovado_por"] == OPERADOR
    assert recibo["n_selecionadas"] == 2
    assert recibo["aprovado_em"].endswith("+00:00")
    assert recibo["motivo"] == "conferi termo a termo contra a LP publicada"

    gravado = _SupaFalso.ultimo["patch"]
    assert gravado["tabela"] == "pautador_keyword_clusters"
    assert gravado["match"] == {"id": "eq.4"}
    itens = gravado["valores"]["factory_output"]
    # O array volta INTEIRO: o funil sem conjunto continua lá.
    assert len(itens) == 2
    assert itens[0]["project_name"] == "funil-sem-conjunto"
    assert itens[0]["keywords_campanha"] == {"lista_google_ads": "outra coisa"}
    alvo = itens[1]["keywords_campanha"]
    assert alvo["conjunto_pago"]["approved_set_sha256"] == impressao
    assert alvo["conjunto_pago"]["aprovado_por"] == OPERADOR
    # A lista original do funil não foi perdida no caminho.
    assert alvo["lista_google_ads"] == "banco pan telefone"
    # O ato humano fica FORA da impressão — o hash não cobre motivo nem relógio.
    assert alvo["aprovacao_humana"]["motivo"] == "conferi termo a termo contra a LP publicada"
    assert "motivo" not in alvo["conjunto_pago"]


def test_o_selo_gravado_abre_o_portao_que_provar_e_subir_usam():
    """A prova de que esta rota destrava o caminho, e não só grava um campo.

    Sem ela, "aprovado" seria uma palavra nossa: quem decide é
    `portao_conjunto_pago.conjunto_do_cluster`, o mesmo que `/provar` chama.
    """
    from app.agents.mining.portao_conjunto_pago import conjunto_do_cluster

    antes = _cluster()
    with pytest.raises(Exception) as recusa:
        conjunto_do_cluster(antes)
    assert "CONJUNTO_PAGO_NAO_APROVADO" in str(recusa.value)

    client.post(
        "/api/pautador/opportunities/73/conjunto-pago/aprovar",
        json={"hash_conferido": _impressao(),
              "motivo": "conferido para o canário de Search"},
    )
    depois = {**antes, "factory_output": _SupaFalso.ultimo["patch"]["valores"]["factory_output"]}
    conferido = conjunto_do_cluster(depois)
    assert conferido.approved_set_sha256 == _impressao()
