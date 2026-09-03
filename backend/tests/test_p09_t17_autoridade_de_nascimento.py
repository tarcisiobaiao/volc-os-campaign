"""P09-T17 — a criação de campanha tem UMA autoridade, e o writer a exige.

## O bypass que este arquivo fecha, medido antes da correção

Reproduzido em 03/09/2026 por
`docs/closure/hermes-p09-t17-campaign-birth-authority-v1/contraprova-vermelha-bypass.py`,
hermético, com adapter falso e contador:

    conta 9999999999 · MCC 1111111111 · status ENABLED no payload
    ledger AUSENTE · identidade AUSENTE · destino AUSENTE · conjunto AUSENTE
    plano de mensuração AUSENTE · idempotência AUSENTE
    validate_only NUNCA rodado (o `Selo` foi forjado)
    → chamadas no adapter: 1 · recibo: ACEITO
    → campanha "criada": customers/9999999999/campaigns/8888888888

`volc_ads.subir.subir` cobrava quatro portas — selo, canal, motivo, trava — e
nenhuma delas era a autoridade canônica. Todos os portões de governança viviam
em `POST /api/trafego/subir`, como convenções DA ROTA. Qualquer módulo, script,
worker ou rota nova que importasse o executor nascia com a capacidade de criar
campanha em qualquer conta, com qualquer verba, sem recibo.

## O que ele prova, e onde as outras provas moram

Aqui: a EMISSÃO da capacidade (`gads/autoridade.emitir` recusa nomeando a prova
que falta), a fidelidade das réplicas de vocabulário, a costura da rota
canônica e o desfecho do fluxo aprovado.

A VERIFICAÇÃO no executor e no writer é provada por
`volc_ads/testes_subir.py` (8 casos novos, com sentinela no writer). Os portões
de governança da rota — ledger, destino, conjunto pago, mensuração,
idempotência — já tinham banco de provas próprio antes desta entrega, e ele NÃO
foi duplicado aqui: ver `COUNTERPROOFS.md` para o mapa de qual arquivo prova o
quê. Duplicar uma guarda é como uma das cópias passa a aceitar o que a outra
recusa.

## Zero rede, zero Supabase, zero Google

`_rede_bloqueada` do módulo base roda em toda função: qualquer socket aberto
derruba o teste. `validate_only` é dublado. Nenhuma credencial é lida.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

import pytest
from fastapi import HTTPException

RAIZ = pathlib.Path(__file__).resolve().parents[2]

# ⚠️ O `conftest.py` põe `backend/` no `sys.path`, e não a RAIZ. Os módulos de
# teste de tráfego importam `volc_ads` no topo e funcionam por ordem de coleta:
# algum arquivo anterior já tinha inserido a raiz. Este arquivo colide
# alfabeticamente antes deles (`test_p09_…` < `test_trafego_…`), então ele
# precisa fazer o próprio bootstrap — senão ele quebra a suíte inteira por um
# motivo que não é o dele.
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

pytest.importorskip("google.ads.googleads")

from app.routers import trafego  # noqa: E402
from app.trafego import canario, prontidao as pr  # noqa: E402
from volc_ads.gads import autoridade as aut  # noqa: E402

import test_trafego_plano_persistido as base  # noqa: E402
from test_trafego_canario import _payload_da_rota  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# A rede bloqueada do módulo base vale aqui também — é a prova 15 rodando em
# toda função, e não uma promessa em prosa.
# ═══════════════════════════════════════════════════════════════════════════

_rede_bloqueada = base._rede_bloqueada
_plano_nao_lido_por_padrao = base._plano_nao_lido_por_padrao


def _provas_completas(**trocas):
    """O conjunto de provas que a rota canônica reúne antes de emitir."""
    campos = dict(
        autoridade=aut.AUTORIDADE_CANONICA,
        conta=canario.CONTA,
        mcc=canario.MCC,
        canal="SEARCH",
        plano_impressao="a" * 64,
        recibo_id="recibo-0001",
        item_id="item-0001",
        idempotency_key="idem-0001",
        aprovador_sub="auth0|tarcisio",
        aprovador_email="operador@example.invalid",
        destino_url="https://portalmundomais.com.br/fgts",
        destino_recibo="b" * 64,
        conjunto_pago_autoridade="python:app.agents.mining.paid_eligibility",
        conjunto_pago_impressao="c" * 64,
        estrategia_lance="MANUAL_CPC",
        mensuracao_veredito="INDETERMINADO",
        orcamento_diario_micros=10_000_000,
        cpc_micros=200_000,
        motivo="canario pausado com aprovacao humana",
    )
    campos.update(trocas)
    return campos


# ═══════════════════════════════════════════════════════════════════════════
# PROVA A — a emissão recusa nomeando a prova que falta
#
# Ausência nunca equivale a aprovação. Cada caso abaixo é uma prova ausente,
# vazia ou incoerente, e nenhum deles produz capacidade.
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("rotulo", "trocas", "pedaco_da_mensagem"),
    [
        # ── autorização humana vinculada ao ato ─────────────────────────────
        ("aprovador sem sub", {"aprovador_sub": ""}, "aprovador_sub"),
        ("aprovador sem e-mail", {"aprovador_email": "   "}, "aprovador_email"),
        # ── ledger/intenção/recibo aberto antes da rede ────────────────────
        ("recibo ausente", {"recibo_id": ""}, "recibo_id"),
        ("item ausente", {"item_id": None}, "item_id"),
        ("chave de idempotência ausente", {"idempotency_key": ""},
         "idempotency_key"),
        # ── destino pago aprovado e recibo vigente ─────────────────────────
        ("destino ausente", {"destino_url": ""}, "destino_url"),
        ("destino sem HTTPS", {"destino_url": "http://exemplo.com.br"},
         "não é HTTPS"),
        ("recibo do destino ausente", {"destino_recibo": ""}, "destino_recibo"),
        # ── keywords positivas aprovadas e seladas ─────────────────────────
        ("conjunto pago sem autoridade", {"conjunto_pago_autoridade": ""},
         "conjunto_pago_autoridade"),
        ("conjunto pago sem selo", {"conjunto_pago_impressao": ""},
         "conjunto_pago_impressao"),
        ("selo do conjunto que não é sha256",
         {"conjunto_pago_impressao": "curto"}, "sha256"),
        # ── identidade da conta ────────────────────────────────────────────
        ("conta ausente", {"conta": ""}, "conta"),
        ("conta que não é dígitos", {"conta": "547-809-6539"},
         "não é um customer id de dígitos"),
        ("MCC ausente", {"mcc": ""}, "mcc"),
        ("MCC que não é dígitos", {"mcc": "MCC-VOLC"},
         "não é um customer id de dígitos"),
        # ── o plano aprovado ───────────────────────────────────────────────
        ("plano sem impressão", {"plano_impressao": ""}, "plano_impressao"),
        ("impressão que não é sha256", {"plano_impressao": "abc"}, "sha256"),
        # ── mensuração coerente ────────────────────────────────────────────
        ("veredito fora do vocabulário", {"mensuracao_veredito": "OK"},
         "fora do vocabulário conhecido"),
        ("veredito ausente", {"mensuracao_veredito": ""},
         "mensuracao_veredito"),
        ("smart bidding sem medição pronta",
         {"estrategia_lance": "MAXIMIZE_CONVERSIONS",
          "mensuracao_veredito": "NAO_PRONTO"}, "aprende de conversão"),
        ("smart bidding com medição indeterminada",
         {"estrategia_lance": "TARGET_CPA",
          "mensuracao_veredito": "INDETERMINADO"}, "aprende de conversão"),
        ("estratégia desconhecida",
         {"estrategia_lance": "ESTRATEGIA_INVENTADA",
          "mensuracao_veredito": "PARCIAL"}, "aprende de conversão"),
        # ── orçamento/limites aprovados ────────────────────────────────────
        ("orçamento zero", {"orcamento_diario_micros": 0}, "menor que o mínimo"),
        ("orçamento negativo", {"orcamento_diario_micros": -1},
         "menor que o mínimo"),
        ("orçamento que não é número", {"orcamento_diario_micros": "vinte"},
         "não é um inteiro de micros"),
        ("CPC negativo", {"cpc_micros": -5}, "menor que o mínimo"),
        # ── nascimento PAUSED, zero ativação implícita ─────────────────────
        ("nascer ENABLED", {"estado_inicial": "ENABLED"}, "nasce PAUSED"),
        ("nascer sem estado", {"estado_inicial": ""}, "estado_inicial"),
        # ── canal ──────────────────────────────────────────────────────────
        ("canal Demand Gen", {"canal": "DEMAND_GEN"},
         "não é um canal que nasce"),
        ("canal PMax", {"canal": "PERFORMANCE_MAX"},
         "não é um canal que nasce"),
        ("canal ausente", {"canal": ""}, "canal"),
        # ── segunda autoridade paralela ────────────────────────────────────
        ("autoridade paralela", {"autoridade": "cli:volc_ads.subir"},
         "não é a autoridade canônica"),
        ("autoridade ausente", {"autoridade": ""}, "autoridade"),
        # ── motivo ─────────────────────────────────────────────────────────
        ("motivo curto", {"motivo": "subir"}, "10 caracteres"),
        ("motivo só de espaços", {"motivo": "          "}, "10 caracteres"),
    ],
)
def test_emitir_recusa_nomeando_a_prova_que_falta(rotulo, trocas,
                                                  pedaco_da_mensagem):
    """Nenhum valor é inventado para destravar: falta prova, a recusa diz qual."""
    with pytest.raises(aut.EmissaoRecusada) as erro:
        aut.emitir(**_provas_completas(**trocas))
    mensagem = str(erro.value)
    assert pedaco_da_mensagem in mensagem, (
        f"{rotulo}: a recusa não nomeou {pedaco_da_mensagem!r} — "
        f"disse {mensagem!r}")
    assert "Google" in mensagem, (
        f"{rotulo}: a recusa não afirma que nada foi enviado ao Google")


def test_o_conjunto_completo_de_provas_emite():
    """A contraprova da contraprova: com tudo no lugar, a capacidade sai.

    Sem este caso, os 34 acima seriam satisfeitos por um `emitir` que recusa
    sempre — um portão que nunca abre não protege, só esconde a decisão.
    """
    autorizacao = aut.emitir(**_provas_completas())
    assert autorizacao.assinatura, "a capacidade saiu sem assinatura"
    assert autorizacao.estado_inicial == "PAUSED"
    assert autorizacao.autoridade == aut.AUTORIDADE_CANONICA
    assert not aut.usada(autorizacao), "nasceu já consumida"


def test_a_projecao_nao_vaza_a_assinatura():
    """O recibo carrega a autorização inteira MENOS a assinatura.

    Devolvê-la numa resposta HTTP daria a quem a lesse uma capacidade
    reaproveitável enquanto o processo vivesse.
    """
    autorizacao = aut.emitir(**_provas_completas())
    projecao = autorizacao.para_json()
    assert "assinatura" not in projecao
    assert autorizacao.assinatura not in json.dumps(projecao)
    # E o conteúdo auditável continua todo lá.
    for campo in ("recibo_id", "item_id", "idempotency_key", "aprovador_sub",
                  "destino_url", "destino_recibo", "conjunto_pago_impressao",
                  "mensuracao_veredito", "orcamento_diario_micros",
                  "estado_inicial"):
        assert campo in projecao, f"a projeção perdeu {campo}"


def test_uma_autorizacao_de_outro_processo_nao_confere():
    """O segredo morre com o processo, então replay de arquivo/fila não vale."""
    autorizacao = aut.emitir(**_provas_completas())
    # Uma cópia idêntica em conteúdo, com assinatura de "outro processo".
    import dataclasses

    de_outro = dataclasses.replace(autorizacao, assinatura="f" * 64)
    with pytest.raises(aut.AutorizacaoInvalida):
        aut.conferir(de_outro, conta=canario.CONTA, mcc=canario.MCC,
                     canal="SEARCH", plano_impressao="a" * 64)


# ═══════════════════════════════════════════════════════════════════════════
# PROVA B — as réplicas de vocabulário são FIÉIS
#
# A capacidade vive em `volc_ads/gads/`, que não pode importar `app.trafego`
# (o backend depende do engine, nunca o contrário). Então ela replica dois
# vocabulários — e uma guarda que discorda da guarda que ela replica é pior
# que nenhuma: dá confiança sem dar proteção.
# ═══════════════════════════════════════════════════════════════════════════


def test_o_vocabulario_de_mensuracao_e_o_mesmo_do_portao():
    assert set(aut.VEREDITOS_DE_MENSURACAO) == set(pr.ESTADOS), (
        "a capacidade e o portão de prontidão discordam sobre quais estados de "
        "mensuração existem. Um estado que só um dos dois conhece é um estado "
        "que atravessa um e morre no outro — ou pior, o contrário.")


def test_as_estrategias_sem_medicao_sao_as_mesmas_do_portao():
    assert set(aut.ESTRATEGIAS_SEM_MENSURACAO) == set(
        pr.ESTRATEGIAS_SEM_APRENDIZADO), (
        "a capacidade e `prontidao.exigir_para_criacao` discordam sobre quais "
        "estratégias dispensam medição. Divergir aqui reabre exatamente o "
        "defeito de 02/09/2026, em que o lance atravessava sem portão.")


def test_os_canais_que_nascem_sao_os_que_o_engine_sabe_montar():
    from volc_ads.campanha import perfil

    assert set(aut.CANAIS_QUE_NASCEM) == set(perfil.canais_que_criam()), (
        "a capacidade autoriza um conjunto de canais diferente do que o engine "
        "sabe construir.")


# ═══════════════════════════════════════════════════════════════════════════
# PROVA C — a rota canônica costura a capacidade, e o fluxo aprovado chega ao
# boundary EXATAMENTE UMA VEZ, PAUSED
# ═══════════════════════════════════════════════════════════════════════════


def _rodar_com_captura(monkeypatch, *, recibo=None, mudancas=None):
    """`/subir` até o fim, capturando o que chegou ao executor.

    O executor é substituído por um dublê que REGISTRA a autorização recebida.
    É o boundary falso: nada é enviado, e o contador é a lista de chamadas.
    """
    from volc_ads import subir as sb

    chamadas: list[dict] = []
    diario: list = []

    def subir_dublado(preparo, *, motivo, autorizacao=None, **_k):
        diario.append(("MUTATE", {}))
        chamadas.append({
            "conta": preparo.customer_id,
            "mcc": preparo.login_customer_id,
            "canal": preparo.canal,
            "motivo": motivo,
            "autorizacao": autorizacao,
            # ⚠️ O ESTADO INICIAL É LIDO DO PAYLOAD que chegaria ao Google, e
            # não do rótulo. É a mesma pergunta que a fronteira faz.
            "estados_no_payload": aut.estados_de_nascimento(preparo.operacoes),
        })
        return recibo if recibo is not None else base._recibo_do_executor("ACEITO")

    impressao = base._impressao_aprovada(monkeypatch)
    ledger = base.LedgerDeTeste(diario=diario)
    repo = base.RepoDePlanoDeTeste(diario=diario)
    base._montar(monkeypatch, ledger=ledger, repo_plano=repo,
                 subir=subir_dublado, diario=diario)
    corpo = base._corpo(impressao, **(mudancas or {}))
    try:
        saida = asyncio.run(trafego.subir(corpo, identidade=base.IDENTIDADE))
    except HTTPException as exc:
        saida = exc
    return saida, chamadas, diario


def test_o_fluxo_aprovado_chega_ao_boundary_uma_vez_e_pausado(monkeypatch):
    """A prova 18: o caminho canônico funciona, e funciona UMA vez.

    ⚠️ Este caso é o que impede a entrega de virar "fechei tudo": um portão que
    nunca abre não protege, só esconde a decisão. Ele exige as três coisas
    juntas — uma chamada, PAUSED, e autorização assinada pela autoridade.
    """
    saida, chamadas, diario = _rodar_com_captura(monkeypatch)

    assert not isinstance(saida, HTTPException), (
        f"o fluxo aprovado foi recusado: {getattr(saida, 'detail', saida)}")
    assert len(chamadas) == 1, (
        f"o boundary foi alcançado {len(chamadas)} vezes; o esperado é UMA")

    chamada = chamadas[0]
    assert chamada["estados_no_payload"] == ("PAUSED",), (
        f"o payload manda nascer {chamada['estados_no_payload']}")

    autorizacao = chamada["autorizacao"]
    assert isinstance(autorizacao, aut.Autorizacao), (
        "o executor foi chamado SEM autorização de nascimento — a rota "
        "voltou a ser uma convenção")
    assert autorizacao.autoridade == aut.AUTORIDADE_CANONICA
    assert autorizacao.estado_inicial == "PAUSED"
    assert autorizacao.conta == canario.CONTA
    assert autorizacao.mcc == canario.MCC

    # E ela NOMEIA cada prova que a rota reuniu, não um booleano.
    assert autorizacao.recibo_id, "a autorização não nomeia o recibo do ledger"
    assert autorizacao.item_id, "a autorização não nomeia o item do ledger"
    assert autorizacao.idempotency_key, "a autorização não nomeia a chave"
    assert autorizacao.aprovador_sub == base.IDENTIDADE.sub
    assert autorizacao.destino_url.startswith("https://")
    assert len(autorizacao.destino_recibo) == 64
    assert len(autorizacao.conjunto_pago_impressao) == 64
    assert autorizacao.conjunto_pago_autoridade.startswith("python:")
    assert autorizacao.mensuracao_veredito in aut.VEREDITOS_DE_MENSURACAO
    assert autorizacao.orcamento_diario_micros == 10_000_000

    # O ledger abriu ANTES do mutate — a ordem que a v10_03 impôs continua.
    atos = base._atos(diario)
    assert atos.index("abrir") < atos.index("MUTATE")
    assert atos.index("despachar") < atos.index("MUTATE")


def test_a_autorizacao_e_do_plano_que_o_selo_provou(monkeypatch):
    """A capacidade aponta a impressão EFETIVA das operações, não o pedido cru."""
    _saida, chamadas, _diario = _rodar_com_captura(monkeypatch)
    autorizacao = chamadas[0]["autorizacao"]
    # Conferir com a mesma função que o writer usa fecha o círculo: se a rota
    # emitisse para outro plano, `conferir` recusaria aqui.
    conferida = aut.conferir(
        autorizacao, conta=canario.CONTA, mcc=canario.MCC, canal="SEARCH",
        plano_impressao=autorizacao.plano_impressao)
    assert conferida is autorizacao


def test_o_recibo_da_resposta_carrega_a_autorizacao_e_nao_a_assinatura(monkeypatch):
    """A prova 16: a tela não consegue declarar sucesso sem recibo canônico.

    O `200` traz a autorização inteira, com recibo, aprovador, destino e
    conjunto pago nomeados — e sem a assinatura. Uma tela que quisesse fingir
    sucesso teria de fabricar esse bloco, e ele nomeia coisas que só existem no
    banco.
    """
    saida, chamadas, _diario = _rodar_com_captura(monkeypatch)
    assert not isinstance(saida, HTTPException)

    recibo = saida["recibo"]
    assert "autorizacao_de_nascimento" in recibo, (
        "a resposta de sucesso não carrega a autorização — a tela não teria "
        "como provar por qual autoridade a campanha nasceu")
    bloco = recibo["autorizacao_de_nascimento"]
    assert bloco["autoridade"] == aut.AUTORIDADE_CANONICA
    assert bloco["estado_inicial"] == "PAUSED"
    assert bloco["recibo_id"]
    assert "assinatura" not in bloco
    assert chamadas[0]["autorizacao"].assinatura not in json.dumps(
        recibo, default=str), "a assinatura vazou na resposta HTTP"
    # A afirmação de que ativação NÃO veio junto continua explícita.
    assert recibo["aprovacao"]["ativacao_incluida"] is False


def test_o_envelope_recusa_demand_gen_antes_de_a_rota_rodar():
    """A prova 14, primeira camada: o payload inválido nem chega à rota.

    `SubirEntrada` herda o contrato estrito de Demand Gen. Um corpo com
    `canal=DEMAND_GEN` e o resto copiado de Search morre na validação do
    envelope — antes de escopo, canário, ponte, cliente, trava ou mutate.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as erro:
        trafego.SubirEntrada(**{
            **_payload_da_rota(canal="DEMAND_GEN"),
            "motivo": "tentativa de criar Demand Gen",
            "plano_impressao": "a" * 64,
            "confirmar_criacao_pausada": True,
        })
    assert "DEMAND_GEN" in str(erro.value), (
        "a recusa do envelope não nomeou o canal")


@pytest.mark.parametrize(
    "canal",
    ["DEMAND_GEN", "PERFORMANCE_MAX", "PMAX", "CANAL_INVENTADO"],
)
def test_canal_sem_criacao_real_morre_nomeado_sem_tocar_o_executor(
        monkeypatch, canal):
    """A prova 14, segunda camada: a rota tem o próprio portão de canal.

    ⚠️ O corpo é montado como SEARCH e o rótulo é TROCADO depois — que é
    exatamente o relabeling contra o qual o resto do fluxo se defende. Assim o
    portão da rota é exercitado sem depender de o envelope ter recusado antes:
    se a validação do envelope mudasse, este caso continuaria provando o portão.

    ⚠️ Os quatro dão **403**, e não 403/422 como eu supus ao escrever este caso.
    Quem responde primeiro é a janela do canário (`canario.exigir`), que só
    opera SEARCH — e ela vem ANTES de `resolver_construtor`, que é quem
    devolveria 422 por canal sem builder. As duas recusas existem e as duas
    nomeiam o canal; a primeira é a que o operador vê. Registrar 422 aqui
    descreveria uma ordem de portões que não é a real.
    """
    status_esperado = 403
    from volc_ads import subir as sb

    chamadas: list = []

    def sentinela(*_a, **_k):
        chamadas.append("MUTATE")
        pytest.fail("um canal sem criação real alcançou o executor")

    monkeypatch.setattr(sb, "subir", sentinela)
    corpo = base._corpo("a" * 64)
    corpo.canal = canal  # relabeling deliberado

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(corpo, identidade=base.IDENTIDADE))

    assert erro.value.status_code == status_esperado, (
        f"{canal}: esperava {status_esperado}, veio {erro.value.status_code}")
    assert canal in str(erro.value.detail), (
        f"{canal}: a recusa não nomeou o canal — o operador não sabe o que "
        f"corrigir. Disse: {erro.value.detail!r}")
    assert not chamadas, f"{canal} alcançou o executor"


def test_o_canal_recusado_nao_e_o_que_o_engine_sabe_criar(monkeypatch):
    """A contraprova da anterior: SEARCH — que o engine cria — NÃO é recusado.

    Sem este caso, o portão de canal seria satisfeito por um `raise` universal.
    """
    _saida, chamadas, _diario = _rodar_com_captura(monkeypatch)
    assert len(chamadas) == 1
    assert chamadas[0]["canal"] == "SEARCH"


# ═══════════════════════════════════════════════════════════════════════════
# PROVA D — os produtores alternativos versionados não escrevem
# ═══════════════════════════════════════════════════════════════════════════


def test_os_workflows_n8n_versionados_nao_mutam_google_ads():
    """A prova 4, metade estática: nenhum workflow chama `:mutate`.

    Os dois fluxos de campanha-dia (D0/D-1) e o de mineração de keywords são os
    únicos versionados que falam com o Google Ads. Todos usam
    `googleAds:search` — que é leitura, e cujo GAQL só tem SELECT.

    ⚠️ Esta prova é ESTÁTICA sobre o JSON versionado. Ela não diz nada sobre o
    que está instalado no n8n vivo, e essa limitação está declarada em
    `REMAINING-RISKS.md`. Um fluxo salvo à mão no servidor não passa por aqui.
    """
    pasta = RAIZ / "n8n"
    assert pasta.is_dir(), "a pasta n8n/ desapareceu"

    endpoints: dict[str, set[str]] = {}
    for arquivo in sorted(pasta.glob("*.json")):
        texto = arquivo.read_text(encoding="utf-8")
        achados = {
            trecho for trecho in ("googleAds:mutate", ":mutate",
                                  "campaigns:mutate", "campaignBudgets:mutate")
            if trecho in texto
        }
        if achados:
            endpoints[arquivo.name] = achados
    assert not endpoints, (
        f"workflow(s) n8n versionados chamam mutate no Google Ads: {endpoints}")


def test_o_produtor_fora_do_motor_de_elegibilidade_e_recusado():
    """A prova 4, a outra metade: cluster sem contrato não vira campanha.

    Um produtor n8n que minerou keywords por fora do motor Python não carrega
    `conjunto_pago`, e o portão recusa com código estável antes de qualquer
    montagem — que é o que impede o pedido de chegar ao ledger.
    """
    from app.agents.mining import portao_conjunto_pago as portao

    cluster_do_n8n = {
        "fabrica": [{"keywords_campanha": {"selected_keywords": ["fgts"]}}],
        "origem": "n8n",
    }
    with pytest.raises(portao.PortaoDoConjuntoPago) as erro:
        portao.conjunto_do_cluster(cluster_do_n8n)
    assert erro.value.codigo in (portao.N8N_SEM_CONTRATO,
                                 portao.CONJUNTO_AUSENTE), (
        f"o portão recusou com um código inesperado: {erro.value.codigo}")
    assert portao.AUTORIDADE in str(erro.value.detalhe) or (
        "conjunto_pago" in str(erro.value.detalhe)), (
        "a recusa não aponta a autoridade operacional nem o campo que falta")


def test_o_cli_de_escrita_continua_aposentado():
    """A prova 1, metade estática: `--subir` recusa antes de tocar em nada.

    A recusa mora ACIMA de qualquer construção em `volc_ads/subir.py:main`, e a
    prova de execução (com a trava ambiental ABERTA) é
    `volc_ads/testes_subir.py::prova_cli_subir_aposentado_nao_toca_google_nem_com_trava_aberta`.
    Aqui só confirmamos que a porta aponta para a autoridade canônica.
    """
    from volc_ads import subir as sb

    assert "/api/trafego/subir" in sb.ESCRITA_PELO_CLI_APOSENTADA
    assert "NADA foi enviado ao Google" in sb.ESCRITA_PELO_CLI_APOSENTADA
    assert aut.AUTORIDADE_CANONICA.endswith("/api/trafego/subir"), (
        "a autoridade canônica mudou de endereço e a mensagem do CLI não")


def test_o_gate_estrutural_existe_e_passa():
    """O scanner de caminhos novos é parte da entrega, não uma sugestão."""
    import subprocess
    import sys

    gate = RAIZ / "scripts" / "gate_autoridade_de_nascimento.py"
    assert gate.is_file(), "o scanner estrutural desapareceu"
    prova = subprocess.run(
        [sys.executable, str(gate)], cwd=str(RAIZ),
        capture_output=True, text=True, check=False,
    )
    assert prova.returncode == 0, (
        f"o scanner estrutural falhou:\n{prova.stdout}\n{prova.stderr}")
    assert "UMA porta" in prova.stdout
