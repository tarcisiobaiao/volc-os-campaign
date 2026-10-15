"""Gestão de campanhas no ar sobre o ledger v10_02 — casos de uso, rotas e infraestrutura.

Sem rede e sem banco: ledger em memória e conta Google de mentira
(`gestao_dubles.py`). A prova de que as LINHAS montadas aqui passam nas CHECKs e
gatilhos reais é feita à parte, reproduzindo `LedgerEmMemoria.ops` em SQL no
banco descartável (ver o relatório da rodada).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

import gestao_dubles as D  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.routers import trafego_gestao as rota  # noqa: E402
from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario  # noqa: E402
from app.trafego.gestao.application import autonomia, erros as E  # noqa: E402
from app.trafego.gestao.application import payload as P  # noqa: E402
from app.trafego.gestao.application.casos_de_uso import (  # noqa: E402
    GoogleRecusou, campos_divergentes, conferir_contra_regra, janela_da_regra)
from app.trafego.gestao.application.efeito import conferir_efeito  # noqa: E402
from app.trafego.gestao.infrastructure import conta_google as CG  # noqa: E402
from app.trafego.gestao.infrastructure import repositorio_postgrest as RP  # noqa: E402
from volc_ads.gestao import acoes as A, ledger as motor  # noqa: E402

CID, CAMP = D.CASA, D.CAMPANHA
ORC = {"tipo": "orcamento.diario", "campaign_id": CAMP, "amount_micros": 36_000_000,
       "origem": "operador"}
QUANDO = "2026-10-15T12:00:00+00:00"


def _pedido(payload):
    """A ida como `propor` a faz: o autor autenticado carimba a origem operador."""
    return P.pedido_do_payload(payload, autor="op@volc", quando=QUANDO)


def _diff(p):
    return {"valor_atual": p["valor_atual"], "valor_proposto": p["valor_proposto"]}


async def _proposta_aprovada(g):
    r = await g.propor(CID, ORC, motivo="CPA estável, verba limitando", autor="op@volc")
    p = r["proposta"]
    await g.aprovar(p["proposta_id"], "aprovada", motivo=None, aprovador="admin@volc",
                    diff_apresentado=_diff(p))
    return p


# ═══ payload: ida e volta para os 15 tipos ═════════════════════════════════

_RN_REC = f"customers/{CID}/recommendations/abc123"
_CASOS = [
    ({"tipo": "status", "nivel": "campanha", "ident": CAMP, "status": "PAUSED"},
     {"existe": True, "status": "ENABLED"}),
    ({"tipo": "status", "nivel": "anuncio", "ident": "190000000001~780000000001",
      "status": "ENABLED"}, {"existe": True, "status": "PAUSED"}),
    ({**ORC, "budget_id": D.BUDGET}, D.antes_orcamento()),
    ({**ORC, "budget_id": D.BUDGET, "compartilhado_ciente": True},
     D.antes_orcamento(compartilhado=True, campanhas_no_orcamento=3)),
    ({"tipo": "lance.alvo", "campaign_id": CAMP, "estrategia": "MAXIMIZE_CONVERSIONS",
      "alvo": "tcpa", "valor": 25_000_000, "origem": "operador"}, {"tcpa_micros": 20_000_000, "moeda": "BRL"}),
    ({"tipo": "lance.alvo", "campaign_id": CAMP, "estrategia": "TARGET_ROAS",
      "alvo": "troas", "valor": 4.5}, {"troas": 4.0}),
    ({"tipo": "lance.estrategia", "campaign_id": CAMP, "nova": "TARGET_SPEND",
      "teto_cpc_micros": 2_000_000, "origem": "operador"}, {"estrategia": "MANUAL_CPC"}),
    ({"tipo": "negativa.keyword", "escopo": "grupo", "alvo": "193210441352",
      "termos": [{"texto": "grátis", "correspondencia": "PHRASE"}, {"texto": "pdf"}]},
     {"negativas_existentes": 0, "chaves": []}),
    ({"tipo": "lista.criar", "tipo_lista": "NEGATIVE_PLACEMENTS", "nome": "Lixo display",
      "itens": [{"tipo": "site", "valor": "exemplo.com.br"}], "campanhas": [int(CAMP)]},
     {"listas_com_mesmo_nome": []}),
    ({"tipo": "lista.adicionar", "shared_set_id": 777, "tipo_lista": "NEGATIVE_KEYWORDS",
      "itens": [{"texto": "vagas", "correspondencia": "BROAD"}]},
     {"existe": True, "tipo": "NEGATIVE_KEYWORDS", "status": "ENABLED", "chaves": []}),
    ({"tipo": "lista.anexar", "shared_set_id": 777, "campanhas": [int(CAMP), 123]},
     {"campanhas_vinculadas": []}),
    ({"tipo": "exclusao.placement", "escopo": "conta",
      "itens": [{"tipo": "youtube_video", "valor": "dQw4w9WgXcQ"}]}, {"chaves": []}),
    ({"tipo": "exclusao.ip", "escopo": "campanha", "campaign_id": CAMP,
      "ips": ["203.0.113.7", "198.51.100.0/24"]}, {"ips_existentes": []}),
    ({"tipo": "programacao.anuncios", "campaign_id": CAMP,
      "janelas": [{"dia": "MONDAY", "inicio": "08:00", "fim": "12:00", "modificador": 1.2}],
      "remover": [111]}, {"janelas": [{"criterion_id": 111, "dia": "MONDAY", "inicio":
                                        "00:00", "fim": "06:00", "modificador": None}]}),
    ({"tipo": "ajuste.dispositivo", "campaign_id": CAMP, "dispositivo": "MOBILE",
      "modificador": 1.3}, {"existe": True, "canal": "SEARCH", "modificador": None}),
    ({"tipo": "ajuste.horario", "campaign_id": CAMP, "criterion_id": 555, "modificador": 0.8},
     {"existe": True, "canal": "SEARCH", "modificador": 1.0}),
    ({"tipo": "recomendacao.aplicar", "recurso": _RN_REC}, {"existe": True}),
    ({"tipo": "recomendacao.dispensar", "recurso": _RN_REC}, {"existe": True}),
]


def test_os_15_tipos_do_contrato_estao_nos_9_grupos():
    assert len(P.GRUPOS) == 9 and len(P.TIPOS) == 15 and len(set(P.TIPOS)) == 15
    assert {c[0]["tipo"] for c in _CASOS} == set(P.TIPOS)


@pytest.mark.parametrize("payload,antes", _CASOS, ids=[c[0]["tipo"] for c in _CASOS])
def test_ida_e_volta_a_proposta_reconstroi_a_mesma_acao(payload, antes):
    """O que se aplica sai do diff aprovado: acao_da_proposta(proposta(a)) == a."""
    acao = _pedido(payload).acao
    linha = json.loads(json.dumps(motor.proposta(acao, CID, antes,
                                                 datetime.now(timezone.utc))))  # como o jsonb
    assert P.acao_da_proposta(linha) == acao
    assert P.customer_id_da_proposta(linha) == CID


def test_payload_recusa_tipo_desconhecido_e_campo_faltando():
    with pytest.raises(E.AcaoInvalida, match="desconhecido"):
        P.pedido_do_payload({"tipo": "campanha.remover"})
    with pytest.raises(E.AcaoInvalida, match="amount_micros"):
        P.pedido_do_payload({"tipo": "orcamento.diario", "campaign_id": CAMP})
    with pytest.raises(E.AcaoInvalida, match="REMOVED"):
        P.pedido_do_payload({"tipo": "status", "nivel": "campanha", "ident": CAMP,
                             "status": "REMOVED"})
    with pytest.raises(E.AcaoInvalida, match="inteiro"):
        _pedido({**ORC, "amount_micros": 36.5})


def test_orcamento_sem_budget_id_e_completado_pelo_estado():
    pedido = _pedido(ORC)
    assert pedido.completar is not None
    final = pedido.completar(D.antes_orcamento())
    assert (final.budget_id, final.amount_micros) == (D.BUDGET, 36_000_000)


# ═══ propor ═════════════════════════════════════════════════════════════════


async def test_propor_le_o_antes_e_grava_evidencia_diagnostico_e_proposta():
    g, led, conta = D.gestao_de_teste()
    r = await g.propor(CID, ORC, motivo="CPA estável, verba limitando", autor="op@volc")
    p = r["proposta"]
    assert not r["ja_existia"] and p["estado"] == "aguardando_aprovacao"
    assert p["operacao"] == "orcamento.diario" and p["delta_pct"] == 20.0
    assert p["valor_atual"]["verba_diaria_micros"] == 30_000_000
    proposto = dict(p["valor_proposto"])
    origem = proposto.pop("origem_valor")
    assert proposto == {"verba_diaria_micros": 36_000_000, "budget_id": D.BUDGET}
    # A origem é carimbada pelo servidor com o autor autenticado, não pela tela.
    assert origem["origem"] == "operador" and origem["evidencia"].startswith("operador:op@volc@")
    assert p["volc_campaign_id"] and p["criada_por"] == "humano:op@volc"
    ev = led.evidencias[r["evidencia_id"]]
    assert ev["suficiencia"] == "suficiente" and ev["moeda"] == "BRL"
    assert ev["volc_campaign_id"] == p["volc_campaign_id"]
    diag = led.diagnosticos[r["diagnostico_id"]]
    assert diag["explicacao"] == "CPA estável, verba limitando"
    assert [t for t, *_ in led.ops] == ["insert"] * 3


async def test_propor_e_idempotente_pela_chave_do_conteudo():
    g, led, _ = D.gestao_de_teste()
    a = await g.propor(CID, ORC, motivo="m1", autor="op")
    b = await g.propor(CID, ORC, motivo="m2", autor="outro")
    assert b["ja_existia"] and b["proposta"]["proposta_id"] == a["proposta"]["proposta_id"]
    assert len(led.propostas) == 1 and len(led.evidencias) == 1
    # Contrato §3.2: "já existia" tem o MESMO formato da proposta nova.
    assert set(b) == set(a) == {"proposta", "evidencia_id", "diagnostico_id", "ja_existia"}
    assert (b["evidencia_id"], b["diagnostico_id"]) == (a["evidencia_id"], a["diagnostico_id"])


def _vivas(led):
    return [p for p in led.propostas.values()
            if p["estado"] in ("aguardando_aprovacao", "aprovada")]


def test_chave_da_tentativa_e_deterministica_e_cabe_na_check():
    import re

    base = "gestao:recomendacao.dispensar:" + "f" * 40
    assert motor.chave_da_tentativa(base, 1) == base
    assert motor.chave_da_tentativa(base, 2) == f"{base}:t2"
    check = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
    assert check.match(motor.chave_da_tentativa(base, 100))
    with pytest.raises(ValueError):
        motor.chave_da_tentativa(base, 0)


async def test_proposta_recusada_nao_prende_o_operador():
    """A divergência 1: recusada sobre o mesmo "antes" devolvia a velha para sempre."""
    g, led, _ = D.gestao_de_teste()
    a = await g.propor(CID, ORC, motivo="m1", autor="op")
    pa = a["proposta"]
    await g.aprovar(pa["proposta_id"], "recusada", motivo="caro agora", aprovador="adm",
                    diff_apresentado=_diff(pa))
    b = await g.propor(CID, ORC, motivo="m2", autor="op")
    pb = b["proposta"]
    assert not b["ja_existia"] and pb["proposta_id"] != pa["proposta_id"]
    assert pb["idempotency_key"] == f"{pa['idempotency_key']}:t2"
    assert pb["estado"] == "aguardando_aprovacao" and b["evidencia_id"] != a["evidencia_id"]
    # A nova está viva: repetir devolve ELA (não a recusada, não uma terceira).
    c = await g.propor(CID, ORC, motivo="m3", autor="op")
    assert c["ja_existia"] and c["proposta"]["proposta_id"] == pb["proposta_id"]
    assert (c["evidencia_id"], c["diagnostico_id"]) == (b["evidencia_id"], b["diagnostico_id"])
    assert len(led.propostas) == 2 and len(_vivas(led)) == 1
    # Recusada de novo → terceira tentativa.
    await g.aprovar(pb["proposta_id"], "recusada", motivo="ainda caro", aprovador="adm",
                    diff_apresentado=_diff(pb))
    d = await g.propor(CID, ORC, motivo="m4", autor="op")
    assert not d["ja_existia"]
    assert d["proposta"]["idempotency_key"] == f"{pa['idempotency_key']}:t3"


async def test_proposta_vencida_e_marcada_expirada_e_nasce_outra():
    g, led, _ = D.gestao_de_teste()
    pa = (await g.propor(CID, ORC, motivo="m", autor="op"))["proposta"]
    led.propostas[pa["proposta_id"]]["expira_em"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    b = await g.propor(CID, ORC, motivo="m", autor="op")
    assert not b["ja_existia"] and b["proposta"]["idempotency_key"].endswith(":t2")
    assert led.propostas[pa["proposta_id"]]["estado"] == "expirada"
    assert len(_vivas(led)) == 1


async def test_aprovada_com_tentativa_sem_resposta_segue_viva_mesmo_vencida():
    """Em voo/sem resposta não verificado: a conta pode ter a mudança. Nada de 2ª proposta."""
    g, led, conta = D.gestao_de_teste()
    p = await _proposta_aprovada(g)
    conta.explodir_na_escrita = True
    with pytest.raises(E.Indisponivel):
        await g.aplicar(p["proposta_id"], executor="adm")
    led.propostas[p["proposta_id"]]["expira_em"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    r = await g.propor(CID, ORC, motivo="de novo", autor="op")
    assert r["ja_existia"] and r["proposta"]["proposta_id"] == p["proposta_id"]
    assert led.propostas[p["proposta_id"]]["estado"] == "aprovada"
    assert len(led.propostas) == 1


async def test_revertida_e_aplicada_nao_seguram_a_idempotencia():
    g, led, conta = D.gestao_de_teste()
    p = await _proposta_aprovada(g)
    ap = (await g.aplicar(p["proposta_id"], executor="adm"))["aplicacao"]
    await g.reverter(ap["aplicacao_id"], motivo="CPA subiu", autor="adm")
    assert led.propostas[p["proposta_id"]]["estado"] == "revertida"
    b = await g.propor(CID, ORC, motivo="tentar de novo", autor="op")  # mesmo "antes": 30M
    assert not b["ja_existia"] and b["proposta"]["idempotency_key"] == \
        f"{p['idempotency_key']}:t2"

    # `aplicada` e a conta voltou ao "antes" por fora: nova decisão humana, nova chave.
    g, led, conta = D.gestao_de_teste()
    p = await _proposta_aprovada(g)
    await g.aplicar(p["proposta_id"], executor="adm")
    conta.mundo[("orcamento.diario", CAMP)]["verba_diaria_micros"] = 30_000_000
    c = await g.propor(CID, ORC, motivo="alguém voltou a verba", autor="op")
    assert not c["ja_existia"] and c["proposta"]["idempotency_key"].endswith(":t2")


async def test_corrida_na_reproposta_deixa_uma_viva():
    """Dois repropõem juntos: os dois calculam `base:t2` e a UNIQUE escolhe um."""
    g, led, _ = D.gestao_de_teste()
    pa = (await g.propor(CID, ORC, motivo="m", autor="op"))["proposta"]
    await g.aprovar(pa["proposta_id"], "recusada", motivo="não", aprovador="adm",
                    diff_apresentado=_diff(pa))
    t2 = f"{pa['idempotency_key']}:t2"
    original = led.proposta_por_chave
    rival = {"proposta_id": "rival", "idempotency_key": t2, "estado": "aguardando_aprovacao",
             "diagnostico_id": None, "alvo_chave": pa["alvo_chave"]}

    async def le_antes_do_rival(chave):
        achou = await original(chave)
        if chave == t2 and achou is None and "rival" not in led.propostas:
            led.propostas["rival"] = dict(rival)  # o outro gravou entre a leitura e o INSERT
        return achou

    led.proposta_por_chave = le_antes_do_rival
    r = await g.propor(CID, ORC, motivo="m", autor="op")
    assert r["ja_existia"] and r["proposta"]["proposta_id"] == "rival"
    assert len(_vivas(led)) == 1


async def test_propor_campanha_nao_importada_e_recusada_sem_gravar():
    g, led, _ = D.gestao_de_teste(importada=False)
    with pytest.raises(E.CampanhaNaoImportada):
        await g.propor(CID, ORC, motivo="m", autor="op")
    assert not led.ops


async def test_propor_sem_regra_vigente():
    g, led, _ = D.gestao_de_teste(regras=[])
    with pytest.raises(E.RegraAusente):
        await g.propor(CID, ORC, motivo="m", autor="op")


async def test_acao_sem_numero_esbarra_na_trava_4a_da_v10_02():
    """Pausar não tem delta, e a regra declara limite: a v10_02 recusaria no INSERT."""
    g, led, _ = D.gestao_de_teste()
    with pytest.raises(E.ForaDaRegra) as exc:
        await g.propor(CID, {"tipo": "status", "nivel": "campanha", "ident": CAMP,
                             "status": "PAUSED"}, motivo="sem conversão", autor="op")
    assert exc.value.codigo == "regra_exige_delta" and not led.ops


async def test_limite_percentual_e_teto_da_regra():
    g, led, _ = D.gestao_de_teste()
    with pytest.raises(E.ForaDaRegra) as exc:
        await g.propor(CID, {**ORC, "amount_micros": 60_000_000}, motivo="m", autor="op")
    assert exc.value.codigo == "limite_pct"
    g2, _, conta2 = D.gestao_de_teste(regras=[D.regra_padrao(teto_orcamento_micros=35_000_000)])
    with pytest.raises(E.ForaDaRegra) as exc2:
        await g2.propor(CID, ORC, motivo="m", autor="op")
    assert exc2.value.codigo == "teto_orcamento" and not led.ops


async def test_evidencia_insuficiente_fica_gravada_e_nao_nasce_proposta():
    g, led, conta = D.gestao_de_teste()
    conta.metricas["custo_micros"] = None
    with pytest.raises(E.EvidenciaInsuficiente) as exc:
        await g.propor(CID, ORC, motivo="m", autor="op")
    ev = led.evidencias[exc.value.detalhe["evidencia_id"]]
    assert ev["suficiencia"] == "insuficiente" and ev["faltantes"] == ["custo_micros"]
    assert not led.propostas and not led.diagnosticos


async def test_estado_que_nao_permite_vira_422():
    g, _, conta = D.gestao_de_teste()
    conta.mundo[("orcamento.diario", CAMP)]["compartilhado"] = True
    with pytest.raises(E.AcaoInvalida, match="compartilhado"):
        await g.propor(CID, ORC, motivo="m", autor="op")


async def test_conta_fora_da_casa_e_403_antes_de_qualquer_leitura():
    g, led, conta = D.gestao_de_teste()
    with pytest.raises(E.ForaDaCasa):
        await g.propor(D.FORA, ORC, motivo="m", autor="op")
    with pytest.raises(E.ForaDaCasa):
        await g.recomendacoes(D.FORA)
    assert not conta.chamadas and not led.ops


# ═══ aprovar / recusar ══════════════════════════════════════════════════════


async def test_aprovar_exige_o_diff_que_a_tela_mostrou():
    g, led, _ = D.gestao_de_teste()
    p = (await g.propor(CID, ORC, motivo="m", autor="op"))["proposta"]
    errado = {**_diff(p), "valor_proposto": {"verba_diaria_micros": 99, "budget_id": 1}}
    with pytest.raises(E.ConflitoDeEstado) as exc:
        await g.aprovar(p["proposta_id"], "aprovada", motivo=None, aprovador="adm",
                        diff_apresentado=errado)
    assert exc.value.codigo == "diff_divergente" and not led.aprovacoes
    with pytest.raises(E.AcaoInvalida):
        await g.aprovar(p["proposta_id"], "aprovada", motivo=None, aprovador="adm",
                        diff_apresentado=None)
    r = await g.aprovar(p["proposta_id"], "aprovada", motivo=None, aprovador="adm",
                        diff_apresentado=_diff(p))
    assert r["proposta"]["estado"] == "aprovada"
    assert r["aprovacao"]["decidida_por"] == "humano:adm"
    de_novo = await g.aprovar(p["proposta_id"], "aprovada", motivo=None, aprovador="adm",
                              diff_apresentado=_diff(p))
    assert de_novo["ja_existia"] and len(led.aprovacoes) == 1
    with pytest.raises(E.ConflitoDeEstado, match="já foi decidida"):
        await g.aprovar(p["proposta_id"], "recusada", motivo="mudei de ideia",
                        aprovador="adm", diff_apresentado={})


async def test_recusa_exige_motivo_e_proposta_vencida_expira():
    g, led, _ = D.gestao_de_teste()
    p = (await g.propor(CID, ORC, motivo="m", autor="op"))["proposta"]
    with pytest.raises(E.AcaoInvalida):
        await g.aprovar(p["proposta_id"], "recusada", motivo=" ", aprovador="a",
                        diff_apresentado={})
    led.propostas[p["proposta_id"]]["expira_em"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with pytest.raises(E.ConflitoDeEstado) as exc:
        await g.aprovar(p["proposta_id"], "aprovada", motivo=None, aprovador="a",
                        diff_apresentado=_diff(p))
    assert exc.value.codigo == "proposta_expirada"
    assert led.propostas[p["proposta_id"]]["estado"] == "expirada"


# ═══ aplicar ════════════════════════════════════════════════════════════════


async def test_aplicar_sem_aprovacao_humana_e_recusado():
    g, led, conta = D.gestao_de_teste()
    p = (await g.propor(CID, ORC, motivo="m", autor="op"))["proposta"]
    with pytest.raises(E.ExigeAprovacaoHumana):
        await g.aplicar(p["proposta_id"], executor="adm")
    assert not led.aplicacoes and not any(c[0] == "aplicar" for c in conta.chamadas)


async def test_aplicar_recusa_quando_o_antes_divergiu_e_nada_sai():
    g, led, conta = D.gestao_de_teste()
    p = await _proposta_aprovada(g)
    conta.mundo[("orcamento.diario", CAMP)]["verba_diaria_micros"] = 31_000_000  # alguém mexeu
    with pytest.raises(E.AntesDivergiu) as exc:
        await g.aplicar(p["proposta_id"], executor="adm")
    assert exc.value.detalhe["campos"] == ["verba_diaria_micros"]
    assert not led.aplicacoes
    assert not any(c[0] in ("validar", "aplicar") for c in conta.chamadas)


async def test_aplicar_grava_em_voo_ensaia_escreve_e_e_idempotente():
    g, led, conta = D.gestao_de_teste()
    p = await _proposta_aprovada(g)
    r = await g.aplicar(p["proposta_id"], executor="adm")
    ap = r["aplicacao"]
    assert r["desfecho"] == "sucesso" and not r["ja_aplicada"]
    assert ap["tentativa"] == 1 and ap["valor_anterior"]["verba_diaria_micros"] == 30_000_000
    assert r["proposta"]["estado"] == "aplicada"
    assert conta.mundo[("orcamento.diario", CAMP)]["verba_diaria_micros"] == 36_000_000
    # em_voo ANTES da chamada; depois o fechamento
    ins = [o for o in led.ops if o[0] == "insert" and o[1] == "trafego_aplicacao"]
    upd = [o for o in led.ops if o[0] == "update" and o[1] == "trafego_aplicacao"]
    assert "desfecho" not in ins[0][2] and upd[0][5]["desfecho"] == "sucesso"
    assert [c[0] for c in conta.chamadas].index("validar") < \
        [c[0] for c in conta.chamadas].index("aplicar")
    assert led.cooldowns  # o gatilho abre a carência
    n = len(conta.chamadas)
    de_novo = await g.aplicar(p["proposta_id"], executor="adm")
    assert de_novo["ja_aplicada"] and len(led.aplicacoes) == 1 and len(conta.chamadas) == n


async def test_aplicar_com_trava_fechada_nao_grava_nem_envia():
    g, led, conta = D.gestao_de_teste(escrita=False)
    p = await _proposta_aprovada(g)
    with pytest.raises(E.EscritaBloqueada):
        await g.aplicar(p["proposta_id"], executor="adm")
    assert not led.aplicacoes and not any(c[0] == "aplicar" for c in conta.chamadas)


async def test_trava_de_codigo_fechada_fecha_a_aplicacao_como_erro():
    g, led, conta = D.gestao_de_teste()
    conta.trava_fechada = True
    p = await _proposta_aprovada(g)
    with pytest.raises(E.EscritaBloqueada):
        await g.aplicar(p["proposta_id"], executor="adm")
    (ap,) = led.aplicacoes.values()
    assert ap["desfecho"] == "erro" and ap["erro_codigo"] == "escrita_bloqueada"
    assert ap["resposta_bruta"]["validate_only"]["desfecho"] == "ok"


async def test_validate_only_recusado_fecha_erro_sem_escrita_real():
    g, led, conta = D.gestao_de_teste()
    conta.validacao_ok = False
    p = await _proposta_aprovada(g)
    with pytest.raises(GoogleRecusou):
        await g.aplicar(p["proposta_id"], executor="adm")
    (ap,) = led.aplicacoes.values()
    assert ap["desfecho"] == "erro" and ap["resposta_bruta"]["fase"] == "validate_only"
    assert not any(c[0] == "aplicar" for c in conta.chamadas)
    assert led.propostas[p["proposta_id"]]["estado"] == "aprovada"


async def test_sem_resposta_bloqueia_reenvio_ate_a_verificacao():
    g, led, conta = D.gestao_de_teste()
    conta.explodir_na_escrita = True
    p = await _proposta_aprovada(g)
    with pytest.raises(E.Indisponivel) as exc:
        await g.aplicar(p["proposta_id"], executor="adm")
    assert exc.value.codigo == "sem_resposta"
    (ap,) = led.aplicacoes.values()
    assert ap["desfecho"] == "sem_resposta"
    with pytest.raises(E.ConflitoDeEstado) as exc2:
        await g.aplicar(p["proposta_id"], executor="adm")
    assert exc2.value.codigo == "verificar_antes"
    # A verificação diz que NÃO entrou → nova tentativa é permitida (linha nova).
    v = await g.verificar(ap["aplicacao_id"], observador="op")
    assert v["confere"] is False
    conta.explodir_na_escrita = False
    r = await g.aplicar(p["proposta_id"], executor="adm")
    assert r["aplicacao"]["tentativa"] == 2 and r["desfecho"] == "sucesso"


async def test_sem_resposta_que_entrou_vira_aplicada_sem_reenviar():
    g, led, conta = D.gestao_de_teste()
    p = await _proposta_aprovada(g)
    conta.explodir_na_escrita = True
    with pytest.raises(E.Indisponivel):
        await g.aplicar(p["proposta_id"], executor="adm")
    conta.mundo[("orcamento.diario", CAMP)]["verba_diaria_micros"] = 36_000_000  # entrou
    (ap,) = led.aplicacoes.values()
    v = await g.verificar(ap["aplicacao_id"], observador="op")
    assert v["confere"] is True and v["proposta"]["estado"] == "aplicada"
    n = len([c for c in conta.chamadas if c[0] == "aplicar"])
    r = await g.aplicar(p["proposta_id"], executor="adm")
    assert r["ja_aplicada"] and len([c for c in conta.chamadas if c[0] == "aplicar"]) == n


async def test_em_voo_orfao_e_fechado_pela_verificacao():
    g, led, conta = D.gestao_de_teste()
    p = await _proposta_aprovada(g)
    aprov = await led.aprovacao_da_proposta(p["proposta_id"])
    velho = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    ap = await led.inserir_aplicacao({"proposta_id": p["proposta_id"],
                                      "aprovacao_id": aprov["aprovacao_id"],
                                      "idempotency_key": p["idempotency_key"], "tentativa": 1,
                                      "enviado_em": velho, "valor_anterior": p["valor_atual"]})
    conta.mundo[("orcamento.diario", CAMP)]["verba_diaria_micros"] = 36_000_000
    v = await g.verificar(ap["aplicacao_id"], observador="op")
    assert v["aplicacao"]["desfecho"] == "sucesso"
    assert v["aplicacao"]["resposta_bruta"]["fechada_por"] == "verificacao"


# ═══ verificar e reverter ═══════════════════════════════════════════════════


async def test_verificar_grava_acompanhamento_tri_estado():
    g, led, conta = D.gestao_de_teste()
    p = await _proposta_aprovada(g)
    ap = (await g.aplicar(p["proposta_id"], executor="adm"))["aplicacao"]
    v = await g.verificar(ap["aplicacao_id"], observador="op")
    ac = v["acompanhamento"]
    assert v["confere"] is True and ac["momento"] == "verificacao"
    assert ac["valor_observado"]["verba_diaria_micros"] == 36_000_000 and ac["motivo"]


async def test_reverter_restaura_o_valor_anterior_e_e_idempotente():
    g, led, conta = D.gestao_de_teste()
    p = await _proposta_aprovada(g)
    ap = (await g.aplicar(p["proposta_id"], executor="adm"))["aplicacao"]
    r = await g.reverter(ap["aplicacao_id"], motivo="CPA subiu 40%", autor="adm")
    assert r["reversao"]["desfecho"] == "sucesso" and r["proposta"]["estado"] == "revertida"
    vr = r["reversao"]["valor_restaurado"]
    assert vr["reversivel"] and vr["passos"][0]["valor"]["verba_diaria_micros"] == 30_000_000
    assert conta.mundo[("orcamento.diario", CAMP)]["verba_diaria_micros"] == 30_000_000
    de_novo = await g.reverter(ap["aplicacao_id"], motivo="de novo", autor="adm")
    assert de_novo["ja_revertida"] and len(led.reversoes) == 1


async def test_reverter_recusa_se_alguem_mexeu_depois():
    g, led, conta = D.gestao_de_teste()
    p = await _proposta_aprovada(g)
    ap = (await g.aplicar(p["proposta_id"], executor="adm"))["aplicacao"]
    conta.mundo[("orcamento.diario", CAMP)]["verba_diaria_micros"] = 50_000_000
    with pytest.raises(E.ConflitoDeEstado) as exc:
        await g.reverter(ap["aplicacao_id"], motivo="piorou", autor="adm")
    assert exc.value.codigo == "estado_mudou_depois" and not led.reversoes


async def test_reverter_sem_trava_nao_queima_a_unica_reversao():
    g, led, conta = D.gestao_de_teste()
    p = await _proposta_aprovada(g)
    ap = (await g.aplicar(p["proposta_id"], executor="adm"))["aplicacao"]
    g._escrita_habilitada = lambda: False
    with pytest.raises(E.EscritaBloqueada):
        await g.reverter(ap["aplicacao_id"], motivo="piorou", autor="adm")
    assert not led.reversoes


async def test_reverter_aplicacao_sem_sucesso_e_recusado():
    g, led, conta = D.gestao_de_teste()
    conta.validacao_ok = False
    p = await _proposta_aprovada(g)
    with pytest.raises(GoogleRecusou):
        await g.aplicar(p["proposta_id"], executor="adm")
    (ap,) = led.aplicacoes.values()
    with pytest.raises(E.ConflitoDeEstado) as exc:
        await g.reverter(ap["aplicacao_id"], motivo="x", autor="adm")
    assert exc.value.codigo == "nada_a_reverter"


# ═══ importar e recomendações ═══════════════════════════════════════════════


async def test_importar_declara_descoberta_e_e_idempotente():
    g, led, conta = D.gestao_de_teste(importada=False)
    r = await g.importar_campanha_externa(CID, CAMP, autor="op@volc")
    c = r["campanha"]
    assert not r["ja_existia"] and c["procedencia"] == "descoberta"
    assert c["procedencia_declarada_por"] == "humano:op@volc"
    from app.trafego.sincronizador import volc_campaign_id
    assert c["volc_campaign_id"] == volc_campaign_id(CID, CAMP)
    assert (await g.importar_campanha_externa(CID, CAMP, autor="op"))["ja_existia"]
    # agora a proposta de nível campanha passa
    assert (await g.propor(CID, ORC, motivo="m", autor="op"))["proposta"]["volc_campaign_id"]


async def test_importar_resolve_procedencia_desconhecida_uma_vez():
    g, led, _ = D.gestao_de_teste(importada=False)
    from app.trafego.sincronizador import volc_campaign_id
    vid = volc_campaign_id(CID, CAMP)
    led.campanhas[vid] = {"volc_campaign_id": vid, "customer_id": CID, "campaign_id": CAMP,
                          "procedencia": "desconhecida", "criada_por": "backend:varredura"}
    r = await g.importar_campanha_externa(CID, CAMP, autor="op")
    assert r["procedencia_resolvida"] and r["campanha"]["procedencia"] == "descoberta"


async def test_importar_campanha_inexistente_ou_removida():
    g, _, conta = D.gestao_de_teste(importada=False)
    with pytest.raises(E.NaoEncontrado):
        await g.importar_campanha_externa(CID, "999", autor="op")
    conta.campanhas[CAMP]["status"] = "REMOVED"
    with pytest.raises(E.ConflitoDeEstado):
        await g.importar_campanha_externa(CID, CAMP, autor="op")


async def test_recomendacao_vira_proposta_mas_a_regra_de_hoje_a_recusa():
    g, _, conta = D.gestao_de_teste()
    (rec,) = await g.recomendacoes(CID)
    conta.mundo[("recomendacao.aplicar", "abc123")] = {"existe": True, "tipo": "CAMPAIGN_BUDGET",
                                                       "dispensada": False}
    with pytest.raises(E.ForaDaRegra) as exc:
        await g.propor(CID, rec["acoes"][0], motivo="o Google sugeriu", autor="op")
    assert exc.value.codigo == "regra_exige_delta"


# ═══ puros ══════════════════════════════════════════════════════════════════


def test_autonomia_e_vazia_por_decisao():
    assert autonomia.NIVEIS_QUE_APLICAM_SEM_HUMANO == frozenset()
    regra_t2 = {"nivel_autonomia": "T2", "acao": {"operacoes_autonomas": ["status"]}}
    assert not autonomia.aplica_sem_humano(regra_t2, "status")


def test_campos_divergentes_ignora_ida_e_volta_do_json():
    assert campos_divergentes({"a": 1, "b": [1, 2]}, {"a": 1.0, "b": [1, 2]}) == []
    assert campos_divergentes({"a": 1}, {"a": 2, "c": None}) == ["a"]


def test_janela_cobre_o_atraso_de_conversao():
    ini, fim = janela_da_regra({"janela_minima_dias": 7, "atraso_conversao_dias": 2},
                               datetime(2026, 10, 8).date())
    assert (ini.isoformat(), fim.isoformat()) == ("2026-09-29", "2026-10-05")


def test_espelho_do_gatilho_de_delta():
    regra = D.regra_padrao(limite_alteracao_pct=None, limite_alteracao_absoluto_micros=10)
    with pytest.raises(E.ForaDaRegra):
        conferir_contra_regra({"delta_pct": 5.0, "delta_absoluto_micros": None}, regra,
                              agora=datetime.now(timezone.utc))


def test_efeito_de_cada_familia():
    assert conferir_efeito(A.AlterarStatus("campanha", CAMP, "PAUSED"),
                           {"existe": True, "status": "PAUSED"})[0] is True
    neg = A.AdicionarNegativas("campanha", CAMP, (A.Termo("grátis"),))
    assert conferir_efeito(neg, {"chaves": [["grátis", "PHRASE"]]})[0] is True
    assert conferir_efeito(neg, {"chaves": []})[0] is False
    assert conferir_efeito(A.AplicarRecomendacao(_RN_REC), {"existe": False})[0] is None
    aj = A.AjustarDispositivo.de(CAMP, "MOBILE", 1.0)
    assert conferir_efeito(aj, {"existe": True, "modificador": None})[0] is True


# ═══ infraestrutura ═════════════════════════════════════════════════════════


def test_gaqls_do_adaptador_estao_no_catalogo_v25():
    from volc_ads.gads import catalogo
    for nivel, gaql in CG._GAQL_METRICAS.items():
        catalogo.exigir_valida(gaql.format(alvo=1, grupo=1, anuncio=2, inicio="2026-10-01",
                                           fim="2026-10-07"))
    catalogo.exigir_valida(CG.GAQL_CAMPANHA.format(campanha=1))
    catalogo.exigir_valida(CG.GAQL_RECOMENDACOES)


def test_somar_metricas_distingue_zero_medido():
    linha = SimpleNamespace(metrics=SimpleNamespace(impressions=10, clicks=2, cost_micros=5_000,
                                                    conversions=1.5, conversions_value=2.0),
                            customer=SimpleNamespace(currency_code="BRL"))
    t = CG.somar_metricas([linha, linha])
    assert (t["impressoes"], t["custo_micros"], t["conversoes"], t["moeda"]) == \
        (20, 10_000, 3.0, "BRL")
    assert t["valor_conversao_micros"] == 4_000_000 and not t["sem_linhas"]
    vazio = CG.somar_metricas([])
    assert vazio["impressoes"] == 0 and vazio["sem_linhas"]


class _Resp:
    def __init__(self, status, corpo):
        self.status_code, self._corpo, self.text = status, corpo, str(corpo)

    def json(self):
        return self._corpo


def test_traduzir_erro_do_postgrest():
    gatilho = RP.traduzir_erro(SimpleNamespace(response=_Resp(400, {
        "code": "23001", "message": "trafego_aplicacao: exige aprovação"})))
    assert isinstance(gatilho, E.BancoRecusou) and gatilho.detalhe["sqlstate"] == "23001"
    assert isinstance(RP.traduzir_erro(SimpleNamespace(response=_Resp(503, "x"))),
                      E.Indisponivel)


async def test_repositorio_monta_as_requisicoes_certas(monkeypatch):
    feitas = []

    async def _req(self, metodo, alvo, **kw):
        feitas.append((metodo, alvo, kw))
        return [{"aplicacao_id": "a1", "proposta_id": "p1"}]

    monkeypatch.setattr(RP.RepositorioGestaoPostgrest, "_req", _req)
    repo = RP.RepositorioGestaoPostgrest("http://banco", "chave")
    await repo.inserir_aplicacao({"proposta_id": "p1", "request_id": None})
    await repo.fechar_aplicacao("a1", {"desfecho": "sucesso"})
    await repo.painel(CID, estado="aprovada", limite=10)
    await repo.diagnostico("d1")
    ins, fecha, painel, diag = feitas
    assert diag[:2] == ("GET", "trafego_diagnostico")
    assert diag[2]["params"]["diagnostico_id"] == "eq.d1"
    assert ins[0] == "POST" and ins[2]["json"] == {"proposta_id": "p1"}
    assert ins[2]["headers"]["Prefer"] == "return=representation"
    assert fecha[0] == "PATCH" and fecha[2]["params"]["desfecho"] == "eq.em_voo"
    assert painel[1] == "trafego_proposta_painel"
    assert painel[2]["params"]["alvo_chave"] == f"like.google_ads:{CID}:*"
    with pytest.raises(E.Indisponivel):
        await RP.RepositorioGestaoPostgrest("", "").proposta("x")


# ═══ rotas ══════════════════════════════════════════════════════════════════

_ADMIN = Identidade(sub="u1", email="adm@volc", papel="ADMIN", origem="sessao")
_OPERADOR = Identidade(sub="u2", email="op@volc", papel="OPERATOR", origem="sessao")


def _app(gestao, quem=_ADMIN, *, sem_identidade=False):
    app = FastAPI()
    app.include_router(rota.router)
    app.dependency_overrides[rota.obter_gestao] = lambda: gestao
    if sem_identidade:
        app.dependency_overrides[get_settings] = lambda: Settings(
            supabase_url="http://auth.invalido", supabase_service_role_key="k")
    else:
        app.dependency_overrides[exigir_usuario] = lambda: quem
    return TestClient(app)


BASE = "/api/trafego/gestao"


def test_rotas_ciclo_completo():
    g, led, conta = D.gestao_de_teste(importada=False)
    c = _app(g)
    imp = c.post(f"{BASE}/campanhas/importar", json={"customer_id": CID, "campaign_id": CAMP})
    assert imp.status_code == 201 and imp.json()["campanha"]["procedencia"] == "descoberta"
    assert c.post(f"{BASE}/campanhas/importar",
                  json={"customer_id": CID, "campaign_id": CAMP}).status_code == 200
    r = c.post(f"{BASE}/propostas", json={"customer_id": CID, "acao": ORC, "motivo": "m"})
    assert r.status_code == 201, r.text
    p = r.json()["proposta"]
    assert c.post(f"{BASE}/propostas", json={"customer_id": CID, "acao": ORC,
                                             "motivo": "m"}).status_code == 200
    painel = c.get(f"{BASE}/propostas", params={"customer_id": CID}).json()
    assert painel["total"] == 1 and painel["propostas"][0]["proximo_passo"] == "aguardar_humano"
    a = c.post(f"{BASE}/propostas/{p['proposta_id']}/aprovar",
               json={"diff_apresentado": _diff(p)})
    assert a.status_code == 200 and a.json()["proposta"]["estado"] == "aprovada"
    ap = c.post(f"{BASE}/propostas/{p['proposta_id']}/aplicar")
    assert ap.status_code == 200 and ap.json()["desfecho"] == "sucesso"
    aid = ap.json()["aplicacao"]["aplicacao_id"]
    assert c.post(f"{BASE}/propostas/{p['proposta_id']}/aplicar").json()["ja_aplicada"]
    v = c.post(f"{BASE}/aplicacoes/{aid}/verificar")
    assert v.status_code == 200 and v.json()["confere"] is True
    rv = c.post(f"{BASE}/aplicacoes/{aid}/reverter", json={"motivo": "piorou"})
    assert rv.status_code == 200 and rv.json()["reversao"]["desfecho"] == "sucesso"
    rec = c.get(f"{BASE}/recomendacoes", params={"customer_id": CID})
    assert rec.status_code == 200 and rec.json()["total"] == 1


def test_rota_recusar_e_erros_mapeados():
    g, led, conta = D.gestao_de_teste()
    c = _app(g)
    p = c.post(f"{BASE}/propostas", json={"customer_id": CID, "acao": ORC,
                                          "motivo": "m"}).json()["proposta"]
    sem = c.post(f"{BASE}/propostas/{p['proposta_id']}/recusar", json={})
    assert sem.status_code == 422 and sem.json()["detail"]["codigo"] == "recusa_sem_motivo"
    ok = c.post(f"{BASE}/propostas/{p['proposta_id']}/recusar", json={"motivo": "caro"})
    assert ok.status_code == 200 and ok.json()["proposta"]["estado"] == "recusada"
    ap = c.post(f"{BASE}/propostas/{p['proposta_id']}/aplicar")
    assert ap.status_code == 409 and ap.json()["detail"]["codigo"] == "exige_aprovacao_humana"
    assert c.post(f"{BASE}/propostas/nao-existe/aplicar").status_code == 404
    pausa = c.post(f"{BASE}/propostas", json={"customer_id": CID, "motivo": "m", "acao": {
        "tipo": "status", "nivel": "campanha", "ident": CAMP, "status": "PAUSED"}})
    assert pausa.status_code == 409 and pausa.json()["detail"]["codigo"] == "regra_exige_delta"
    ruim = c.post(f"{BASE}/propostas", json={"customer_id": CID, "motivo": "m",
                                             "acao": {"tipo": "x"}})
    assert ruim.status_code == 422


def test_rota_repropor_depois_da_recusa_e_201_e_repetir_e_200_com_os_ids():
    g, led, conta = D.gestao_de_teste()
    c = _app(g)
    corpo = {"customer_id": CID, "acao": ORC, "motivo": "m"}
    p = c.post(f"{BASE}/propostas", json=corpo).json()["proposta"]
    assert c.post(f"{BASE}/propostas/{p['proposta_id']}/recusar",
                  json={"motivo": "caro"}).status_code == 200
    nova = c.post(f"{BASE}/propostas", json=corpo)
    assert nova.status_code == 201, nova.text
    assert nova.json()["proposta"]["proposta_id"] != p["proposta_id"]
    de_novo = c.post(f"{BASE}/propostas", json=corpo)
    assert de_novo.status_code == 200 and de_novo.json()["ja_existia"]
    assert {k: de_novo.json()[k] for k in ("evidencia_id", "diagnostico_id")} == \
        {k: nova.json()[k] for k in ("evidencia_id", "diagnostico_id")}
    assert de_novo.json()["evidencia_id"]


def test_rota_divergencia_do_antes_e_409():
    g, led, conta = D.gestao_de_teste()
    c = _app(g)
    p = c.post(f"{BASE}/propostas", json={"customer_id": CID, "acao": ORC,
                                          "motivo": "m"}).json()["proposta"]
    c.post(f"{BASE}/propostas/{p['proposta_id']}/aprovar", json={"diff_apresentado": _diff(p)})
    conta.mundo[("orcamento.diario", CAMP)]["verba_diaria_micros"] = 33_000_000
    r = c.post(f"{BASE}/propostas/{p['proposta_id']}/aplicar")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "antes_divergiu"
    assert not led.aplicacoes


@pytest.mark.parametrize("metodo,caminho,corpo", [
    ("get", "/propostas", None), ("get", "/recomendacoes", None),
    ("post", "/propostas", {"acao": ORC, "motivo": "m"}),
    ("post", "/campanhas/importar", {"campaign_id": CAMP}),
])
def test_rota_conta_fora_da_casa_e_403(metodo, caminho, corpo):
    g, led, conta = D.gestao_de_teste()
    c = _app(g)
    if metodo == "get":
        r = c.get(BASE + caminho, params={"customer_id": D.FORA})
    else:
        r = c.post(BASE + caminho, json={**corpo, "customer_id": D.FORA})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "fora_do_escopo"
    assert not conta.chamadas and not led.ops


def test_rota_por_id_de_proposta_de_conta_fora_da_casa_e_403():
    g, led, conta = D.gestao_de_teste()
    c = _app(g)
    p = c.post(f"{BASE}/propostas", json={"customer_id": CID, "acao": ORC,
                                          "motivo": "m"}).json()["proposta"]
    led.propostas[p["proposta_id"]]["alvo_chave"] = f"google_ads:{D.FORA}:campanha:{CAMP}"
    r = c.post(f"{BASE}/propostas/{p['proposta_id']}/aprovar", json={"diff_apresentado": {}})
    assert r.status_code == 403


@pytest.mark.parametrize("metodo,caminho", [
    ("get", "/propostas?customer_id=1"), ("post", "/propostas/x/aplicar"),
    ("post", "/aplicacoes/x/verificar"), ("post", "/campanhas/importar"),
])
def test_rota_sem_credencial_e_401(metodo, caminho):
    g, *_ = D.gestao_de_teste()
    c = _app(g, sem_identidade=True)
    r = getattr(c, metodo)(BASE + caminho)
    assert r.status_code == 401


@pytest.mark.parametrize("caminho,corpo", [
    ("/propostas/x/aprovar", {"diff_apresentado": {}}),
    ("/propostas/x/recusar", {"motivo": "m"}),
    ("/propostas/x/aplicar", None),
    ("/aplicacoes/x/reverter", {"motivo": "m"}),
])
def test_rota_de_escrita_sem_admin_e_403(caminho, corpo):
    g, led, conta = D.gestao_de_teste()
    c = _app(g, _OPERADOR)
    r = c.post(BASE + caminho, json=corpo) if corpo else c.post(BASE + caminho)
    assert r.status_code == 403 and "administrativo" in r.json()["detail"]
    assert not conta.chamadas and not led.ops


def test_operador_propoe_e_verifica_sem_admin():
    g, *_ = D.gestao_de_teste()
    c = _app(g, _OPERADOR)
    r = c.post(f"{BASE}/propostas", json={"customer_id": CID, "acao": ORC, "motivo": "m"})
    assert r.status_code == 201
    assert r.json()["proposta"]["criada_por"] == "humano:op@volc"


def test_router_registrado_no_main():
    from app.main import app
    caminhos = {getattr(r, "path", "") for r in app.routes}
    for c in ("/propostas", "/propostas/{proposta_id}/aprovar", "/propostas/{proposta_id}/recusar",
              "/propostas/{proposta_id}/aplicar", "/aplicacoes/{aplicacao_id}/verificar",
              "/aplicacoes/{aplicacao_id}/reverter", "/campanhas/importar", "/recomendacoes"):
        assert BASE + c in caminhos, c


# ═══ v17_03: operações sem delta que a regra declara ════════════════════════

from app.trafego.gestao.application import sem_delta as SD  # noqa: E402

_MIGRATION_V17_03 = os.path.join(_RAIZ, "supabase", "migrations",
                                 "v17_03_gestao_operacoes_sem_delta.sql")
_CONTRATO = os.path.join(_RAIZ, "docs", "contracts", "GADS-GESTAO-v1.md")

_LANCE_ANTES = {"existe": True, "campaign_id": int(CAMP), "canal": "SEARCH",
                "estrategia": "MAXIMIZE_CONVERSIONS", "portfolio": None, "moeda": "BRL",
                "teto_cpc_micros": 0, "tcpa_micros": 20_000_000, "troas": 0.0}
_REC_ANTES = {"existe": True, "tipo": "SITELINK_ASSET", "dispensada": False,
              "campanha": None, "orcamento": None, "grupo": None}
#: O "antes" que a conta falsa devolve por tipo, para `propor` (que confere a ação).
_ANTES_PARA_PROPOR = {
    "lance.alvo": _LANCE_ANTES,
    "lance.estrategia": {**_LANCE_ANTES, "estrategia": "MANUAL_CPC", "tcpa_micros": 0},
    "recomendacao.aplicar": _REC_ANTES, "recomendacao.dispensar": _REC_ANTES,
}


def _um_caso_por_tipo():
    vistos, saida = set(), []
    for payload, antes in _CASOS:
        if payload["tipo"] in vistos or (payload["tipo"] == "lance.alvo"
                                         and payload.get("alvo") != "tcpa"):
            continue
        vistos.add(payload["tipo"])
        saida.append((payload, _ANTES_PARA_PROPOR.get(payload["tipo"], antes)))
    return saida


def _no_mundo(conta, payload, antes):
    acao = _pedido(payload).acao
    conta.mundo[(acao.tipo, str(acao.alvo_id))] = json.loads(json.dumps(antes))
    return acao


def _ler(caminho: str) -> str:
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def _sql_da_classe():
    sql = _ler(_MIGRATION_V17_03)
    corpo = sql.split("CREATE FUNCTION public.trafego_operacao_sem_delta_classe", 1)[1]
    corpo = corpo.split("$funcao$;", 1)[0]
    import re
    return dict(re.findall(r"WHEN '([a-z.]+)'\s+THEN '([a-z]+)'", corpo)), sql


def _json_de_referencia(texto: str):
    """O objeto `operacoes_sem_delta` do INSERT de referência (migration ou contrato)."""
    import re
    linhas = [re.sub(r"^-- ?", "", ln) for ln in texto.splitlines()]
    bruto = "\n".join(linhas)
    ini = bruto.index("'{\n", bruto.index("('gestao_manual_google'"))
    fim = bruto.index("}'::jsonb", ini)
    return json.loads(bruto[ini + 1:fim + 1])


def test_vocabulario_sem_delta_e_o_da_migration_e_cobre_os_13():
    classes_sql, sql = _sql_da_classe()
    assert classes_sql == SD.CLASSES and len(SD.CLASSES) == 13
    assert set(SD.CLASSES) | set(SD.MONETARIAS) == set(P.TIPOS)
    assert not set(SD.CLASSES) & set(SD.MONETARIAS)
    assert SD._REC_MONETARIA.pattern in sql  # o mesmo padrão nos dois lados


def test_regra_de_referencia_e_a_mesma_na_migration_no_contrato_e_nos_dubles():
    mig = _json_de_referencia(_ler(_MIGRATION_V17_03))
    contrato = _json_de_referencia(_ler(_CONTRATO))
    assert mig == contrato == D.OPERACOES_SEM_DELTA_REFERENCIA
    assert set(mig) == set(SD.CLASSES)


@pytest.mark.parametrize("tipo", ["CAMPAIGN_BUDGET", "MOVE_UNUSED_BUDGET", "SET_TARGET_CPA",
                                  "LOWER_TARGET_ROAS", "MAXIMIZE_CLICKS_OPT_IN",
                                  "ENHANCED_CPC_OPT_IN", "UK_DST_FEE",
                                  "SPAIN_REGULATORY_OPERATING_COST", "OPERATING_CHARGES"])
def test_recomendacao_monetaria_pelo_padrao(tipo):
    assert SD.recomendacao_monetaria(tipo)


@pytest.mark.parametrize("tipo", ["SITELINK_ASSET", "KEYWORD", "PERFORMANCE_MAX_OPT_IN",
                                  "UPGRADE_LOCAL_CAMPAIGN_TO_PERFORMANCE_MAX", None])
def test_recomendacao_nao_monetaria(tipo):
    assert not SD.recomendacao_monetaria(tipo)


_REF = D.OPERACOES_SEM_DELTA_REFERENCIA


@pytest.mark.parametrize("operacao,nivel,atual,proposto,trecho", [
    ("status", "campanha", {}, {"status": "REMOVED"}, "REMOVED"),
    ("status", "campanha", {}, {}, "ausente"),
    ("status", "keyword", {}, {"status": "PAUSED"}, "nível"),
    ("lance.estrategia", "campanha", {}, {"estrategia": "PORTFOLIO"}, "fora de estrategias"),
    ("lance.estrategia", "campanha", {}, {"estrategia": "TARGET_SPEND",
                                          "teto_cpc_micros": 60_000_000}, "teto_micros"),
    ("ajuste.dispositivo", "campanha", {}, {"dispositivo": "MOBILE", "modificador": 0},
     "fora de"),
    ("ajuste.horario", "campanha", {}, {"criterion_id": 1}, "ausente"),
    ("negativa.keyword", "grupo", {}, {"escopo": "grupo", "adicionar": [{"texto": "x"}] * 51},
     "max_itens"),
    ("negativa.keyword", "grupo", {}, {"escopo": "grupo"}, "sem contagem"),
    ("negativa.keyword", "grupo", {}, {"escopo": "grupo", "adicionar": []}, "item nenhum"),
    ("exclusao.ip", "conta", {}, {"escopo": "loja", "excluir_ips": ["1.2.3.4"]}, "escopo"),
    ("exclusao.ip", "conta", {}, {"excluir_ips": ["1.2.3.4"]}, "escopo"),
    ("lista.criar", "conta", {}, {"itens": [{}], "campanhas": list(range(11))},
     "max_campanhas"),
    ("lista.anexar", "conta", {}, {"anexar": list(range(11))}, "max_itens"),
    ("programacao.anuncios", "campanha", {}, {"criar": [{"modificador": 2.0}], "remover": []},
     "janela"),
    ("programacao.anuncios", "campanha", {}, {"criar": []}, "criar/remover"),
    ("recomendacao.aplicar", "conta", {"tipo": "CAMPAIGN_BUDGET"}, {"aplicar": "r"}, "verba"),
    ("recomendacao.aplicar", "conta", {}, {"aplicar": "r"}, "tipo ausente"),
    ("recomendacao.aplicar", "conta", {"tipo": "KEYWORD"}, {"aplicar": "r"}, "tipos_permitidos"),
])
def test_teto_proprio_recusa(operacao, nivel, atual, proposto, trecho):
    motivo = SD.defeito(_REF[operacao], operacao, nivel, atual, proposto)
    assert motivo and trecho in motivo, motivo


def test_teto_proprio_aceita_o_que_cabe():
    assert SD.defeito(_REF["programacao.anuncios"], "programacao.anuncios", "campanha", {},
                      {"criar": [{"modificador": None}, {"modificador": 1.5}],
                       "remover": [1]}) is None
    assert SD.defeito(_REF["recomendacao.dispensar"], "recomendacao.dispensar", "conta",
                      {"tipo": "CAMPAIGN_BUDGET"}, {"dispensar": "r"}) is None
    assert SD.defeito(_REF["exclusao.ip"], "exclusao.ip", "campanha", {},
                      {"escopo": "campanha", "excluir_ips": ["1.2.3.4"] * 20}) is None


async def test_regra_de_referencia_transforma_os_15_tipos_em_proposta():
    g, led, conta = D.gestao_de_teste(regras=[D.regra_referencia()])
    casos = _um_caso_por_tipo()
    assert {p["tipo"] for p, _ in casos} == set(P.TIPOS)
    for payload, antes in casos:
        _no_mundo(conta, payload, antes)
        r = await g.propor(CID, payload, motivo=f"teste {payload['tipo']}", autor="op@volc")
        p = r["proposta"]
        assert not r["ja_existia"] and p["operacao"] == payload["tipo"]
        if payload["tipo"] in SD.MONETARIAS:
            assert p["delta_pct"] is not None
        else:
            assert p.get("delta_pct") is None and p.get("delta_absoluto_micros") is None
    assert len(led.propostas) == 15


async def test_operacao_fora_da_lista_continua_regra_exige_delta():
    tetos = {k: v for k, v in _REF.items() if k != "exclusao.ip"}
    g, led, conta = D.gestao_de_teste(regras=[D.regra_padrao(operacoes_sem_delta=tetos)])
    payload = next(p for p, _ in _CASOS if p["tipo"] == "exclusao.ip")
    _no_mundo(conta, payload, {"ips_existentes": []})
    with pytest.raises(E.ForaDaRegra) as exc:
        await g.propor(CID, payload, motivo="bots", autor="op")
    assert exc.value.codigo == "regra_exige_delta" and not led.ops
    assert "exclusao.ip" not in exc.value.detalhe["operacoes_sem_delta_da_regra"]
    assert exc.value.detalhe["classe"] == "segmentacao"


async def test_teto_sem_delta_recusa_antes_de_gravar():
    g, led, conta = D.gestao_de_teste(regras=[D.regra_referencia()])
    payload = {"tipo": "exclusao.ip", "escopo": "campanha", "campaign_id": CAMP,
               "ips": [f"203.0.113.{i}" for i in range(1, 22)]}
    _no_mundo(conta, payload, {"ips_existentes": []})
    with pytest.raises(E.ForaDaRegra) as exc:
        await g.propor(CID, payload, motivo="bots", autor="op")
    assert exc.value.codigo == "teto_sem_delta" and not led.ops
    assert exc.value.detalhe["teto"] == {"max_itens": 20, "escopos": ["campanha", "conta"]}
    conta.mundo[("recomendacao.aplicar", "abc123")] = {**_REC_ANTES, "tipo": "CAMPAIGN_BUDGET"}
    with pytest.raises(E.ForaDaRegra) as exc2:
        await g.propor(CID, {"tipo": "recomendacao.aplicar", "recurso": _RN_REC},
                       motivo="o Google sugeriu", autor="op")
    assert exc2.value.codigo == "teto_sem_delta" and "verba" in str(exc2.value)


def test_monetaria_continua_exigindo_delta_e_limite():
    regra = D.regra_referencia()
    agora = datetime.now(timezone.utc)
    sem = {"operacao": "orcamento.diario", "delta_pct": None, "delta_absoluto_micros": None,
           "valor_proposto": {"verba_diaria_micros": 1}}
    with pytest.raises(E.ForaDaRegra) as exc:
        conferir_contra_regra(sem, regra, agora=agora)
    assert exc.value.codigo == "regra_exige_delta" and "monetária" in str(exc.value)
    with pytest.raises(E.ForaDaRegra) as exc2:
        conferir_contra_regra({"operacao": "orcamento.diario", "delta_pct": 80.0,
                               "delta_absoluto_micros": 24_000_000}, regra, agora=agora)
    assert exc2.value.codigo == "limite_pct"
    # nem uma regra adulterada (que o banco recusaria pela CHECK) abre a monetária
    torta = D.regra_padrao(operacoes_sem_delta={"orcamento.diario": {}})
    with pytest.raises(E.ForaDaRegra):
        conferir_contra_regra(sem, torta, agora=agora)


async def test_ciclo_completo_de_uma_pausa_sob_a_regra_de_referencia():
    g, _led, conta = D.gestao_de_teste(regras=[D.regra_referencia()])
    pausa = {"tipo": "status", "nivel": "campanha", "ident": CAMP, "status": "PAUSED"}
    p = (await g.propor(CID, pausa, motivo="sem conversão há 21 dias", autor="op"))["proposta"]
    await g.aprovar(p["proposta_id"], "aprovada", motivo=None, aprovador="adm",
                    diff_apresentado=_diff(p))
    ap = (await g.aplicar(p["proposta_id"], executor="adm"))["aplicacao"]
    assert ap["desfecho"] == "sucesso" and conta.mundo[("status", CAMP)]["status"] == "PAUSED"
    assert (await g.verificar(ap["aplicacao_id"], observador="op"))["confere"] is True
    r = await g.reverter(ap["aplicacao_id"], motivo="voltou a converter", autor="adm")
    assert r["proposta"]["estado"] == "revertida"
    assert conta.mundo[("status", CAMP)]["status"] == "ENABLED"


def test_rota_pausa_vira_proposta_com_a_regra_de_referencia():
    g, _led, conta = D.gestao_de_teste(regras=[D.regra_referencia()])
    c = _app(g)
    pausa = c.post(f"{BASE}/propostas", json={"customer_id": CID, "motivo": "m", "acao": {
        "tipo": "status", "nivel": "campanha", "ident": CAMP, "status": "PAUSED"}})
    assert pausa.status_code == 201, pausa.text
    assert pausa.json()["proposta"]["operacao"] == "status"
    conta.mundo[("recomendacao.aplicar", "abc123")] = {**_REC_ANTES, "tipo": "CAMPAIGN_BUDGET"}
    teto = c.post(f"{BASE}/propostas", json={"customer_id": CID, "motivo": "m", "acao": {
        "tipo": "recomendacao.aplicar", "recurso": _RN_REC}})
    assert teto.status_code == 409 and teto.json()["detail"]["codigo"] == "teto_sem_delta"
