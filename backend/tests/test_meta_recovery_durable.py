"""Recuperação durável do nascimento Meta: snapshot congelado e órfão visível.

## Os dois defeitos que estas provas fecham

`F02` (P0) — `/reconciliar` RECOMPILAVA o plano. Recompilar é abrir o Keychain,
reler a conta inteira, rebaixar os bytes da peça do CDN e depender de a
atestação de direitos ainda estar na validade. O preço estava medido: a
atestação vale uma hora e a aprovação vale quinze minutos, então um passo
ambíguo só era recuperável dentro de uma janela que fecha sessenta minutos
depois de um clique feito ANTES de aprovar. Passada a janela, a recuperação
histórica era impossível — embora os objetos pudessem existir na conta.

`F03` (P0) — a rota filtrava `state == "AMBIGUOUS"` e nada mais. Um passo
órfão em `IN_FLIGHT` era invisível, e a resposta dizia `passos_ambiguos: 0` —
indistinguível de "nada travado".

## O que estas provas NÃO afirmam

Nada sobre a conta Meta. Todo tráfego é dublê. O que se prova é que a
recuperação deixou de depender do presente, e que ela nunca vira um caminho
para reenviar.
"""
from __future__ import annotations

import asyncio
import copy

import pytest

from app.trafego.meta_execucao.compilador import (
    SnapshotMetaInvalido,
    descongelar_plano,
)
from test_meta_criacao_pausada_rotas import (  # type: ignore[import-not-found]
    CENARIO,
    IDS_CRIADOS,
    _abrir,
    _aprovar,
    _cenario_limpo,  # noqa: F401 — fixture autouse, aplicada por importação
    _cliente,
    _LedgerEmMemoria,
    _plano_para_envio,
)


# ---------------------------------------------------------------------------
# O SNAPSHOT EXISTE, É ÍNTEGRO E É SERVER-ONLY
# ---------------------------------------------------------------------------

def test_aprovar_congela_o_plano_despachavel(monkeypatch) -> None:
    """A aprovação passa a guardar o plano, não só o pedido do operador."""
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    resposta = asyncio.run(_aprovar(cliente, ledger, _plano_para_envio()))
    assert resposta.status_code == 200, resposta.text

    aprovacao = next(iter(ledger.aprovacoes.values()))
    congelado = aprovacao["plano_congelado"]
    assert congelado["compiler_version"] == "meta-compilador-v2"
    assert aprovacao["snapshot_sha256"] == aprovacao["plano_sha256"]
    # O snapshot é DESPACHÁVEL: endpoints resolvidos e payloads prontos.
    assert [op["nome"] for op in congelado["operacoes"]] == list(
        aprovacao["passos_esperados"])
    assert all(op["endpoint"].startswith("/act_") for op in congelado["operacoes"])
    # ⚠️ E ele NÃO carrega segredo. Identidade resolvida do provedor sim —
    # sem ela não seria despachável — token, nunca.
    texto = str(congelado)
    assert "Bearer" not in texto
    assert "token-meta-falso" not in texto


def test_snapshot_adulterado_nao_vira_payload(monkeypatch) -> None:
    """Uma linha editada no banco é recusada pela identidade recalculada.

    ⚠️ É a razão inteira de `descongelar_plano` recalcular o hash em vez de
    lê-lo: um snapshot é uma autorização de gasto guardada num banco. Se ele
    pudesse ser editado por fora e ainda assim despachar, a aprovação deixaria
    de descrever o que nasce.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    asyncio.run(_aprovar(_cliente(), ledger, _plano_para_envio()))
    congelado = next(iter(ledger.aprovacoes.values()))["plano_congelado"]

    adulterado = copy.deepcopy(congelado)
    for operacao in adulterado["operacoes"]:
        if operacao["tipo"] == "adset":
            operacao["payload"]["daily_budget"] = 99_999_999
    with pytest.raises(SnapshotMetaInvalido) as erro:
        descongelar_plano(adulterado)
    assert erro.value.codigo == "META_PLAN_SNAPSHOT_TAMPERED"

    # E o snapshot íntegro continua descongelando para o MESMO plano.
    assert descongelar_plano(congelado).plano_sha256 == congelado["plano_sha256"]


# ---------------------------------------------------------------------------
# F02 — RECUPERAR NÃO FAZ MAIS PERGUNTAS SOBRE O PRESENTE
# ---------------------------------------------------------------------------

def test_reconciliar_nao_recompila_nem_rele_a_conta(monkeypatch) -> None:
    """A prova direta de F02: a recuperação não toca inventário nem CDN.

    A armadilha é o ponto. Se a rota voltasse a chamar `_compilar`, ela abriria
    o cliente HTTP para ler `/me/adaccounts`, `/promote_pages`, `/adimages` e os
    bytes da peça — e a armadilha dispararia. As leituras que SOBRAM são as da
    própria reconciliação: ela lê os objetos na conta, e é para isso que existe.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    aprovacao = asyncio.run(_aprovar(cliente, ledger, _plano_para_envio())).json()
    aid = aprovacao["aprovacao"]["approval_id"]

    # A saga despachou a campanha e o passo ficou AMBÍGUO.
    ledger.passos["passo-campaign"] = {
        "approval_id": aid, "nome": "campaign", "ordinal": 1,
        "state": "AMBIGUOUS", "id_externo": None, "codigo": None,
        "readback": None, "prepared_at": "2026-09-05T12:00:00+00:00",
    }

    CENARIO.gets.clear()
    resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar",
                            json={"approval_id": aid})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["efeito_externo"] == "NENHUM"

    lidas = list(CENARIO.gets)
    assert not any("/adimages" in url for url in lidas), lidas
    assert not any("/promote_pages" in url for url in lidas), lidas
    assert not any("/me/adaccounts" in url for url in lidas), lidas
    assert not any("fbcdn.net" in url for url in lidas), lidas


def test_reconciliar_funciona_com_a_atestacao_de_direitos_vencida(monkeypatch) -> None:
    """O caso exato de F02: um despacho de duas horas atrás.

    Antes, a recompilação reemitia o recibo de política a partir do carimbo
    gravado no `plan_request`, e um carimbo de duas horas atrás parava a rota em
    `META_ASSET_POLICY_RECEIPT_EXPIRED` — ANTES de ela conseguir LER o que já
    podia existir na conta. Ler não precisa dessa pergunta.
    """
    from datetime import datetime, timedelta, timezone

    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    aprovacao = asyncio.run(_aprovar(cliente, ledger, _plano_para_envio())).json()
    aid = aprovacao["aprovacao"]["approval_id"]

    # O tempo passa: a atestação que o operador fez vence.
    vencida = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    pedido = ledger.aprovacoes[aid]["pedido_do_operador"]
    pedido["asset_policy_confirmed_at"] = vencida
    for variacao in pedido.get("variations", []):
        variacao["asset_policy_confirmed_at"] = vencida

    ledger.passos["passo-campaign"] = {
        "approval_id": aid, "nome": "campaign", "ordinal": 1,
        "state": "AMBIGUOUS", "id_externo": None, "codigo": None,
        "readback": None, "prepared_at": "2026-09-05T12:00:00+00:00",
    }

    resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar",
                            json={"approval_id": aid})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["passos_ambiguos"] == 1


def test_aprovacao_legada_sem_snapshot_nao_e_recompilada_em_silencio(monkeypatch) -> None:
    """Ausência de snapshot vira recusa NOMEADA, nunca reconstrução.

    Recompilar a partir da conta de hoje produziria outro plano com cara do
    mesmo — o que `MASTER-SPEC.json` proíbe em
    `immutable_dispatch.migration_compatibility`. A operação antiga continua
    legível e segue por adjudicação manual, com os IDs que o recibo já guarda.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    aprovacao = asyncio.run(_aprovar(cliente, ledger, _plano_para_envio())).json()
    aid = aprovacao["aprovacao"]["approval_id"]

    # Uma aprovação nascida antes desta versão.
    ledger.aprovacoes[aid]["plano_congelado"] = None
    ledger.passos["passo-campaign"] = {
        "approval_id": aid, "nome": "campaign", "ordinal": 1,
        "state": "AMBIGUOUS", "id_externo": None, "codigo": None,
        "readback": None, "prepared_at": "2026-09-05T12:00:00+00:00",
    }

    for rota, corpo in (
        ("reconciliar", {"approval_id": aid}),
        ("criar-pausada", {
            "approval_id": aid,
            "plano_sha256_esperado": aprovacao["aprovacao"]["plano_sha256"]}),
    ):
        resposta = cliente.post(
            f"/api/trafego/meta/local/criacao/{rota}", json=corpo)
        assert resposta.status_code == 409, (rota, resposta.text)
        assert resposta.json()["detail"]["codigo"] == "META_LEGACY_RECOVERY_REQUIRED"

    # ⚠️ E o RECIBO continua legível: perder o caminho automático não pode
    # apagar o histórico.
    recibo = cliente.post("/api/trafego/meta/local/criacao/recibo",
                          json={"approval_id": aid})
    assert recibo.status_code == 200, recibo.text
    assert recibo.json()["recibo"]["approval_id"] == aid


# ---------------------------------------------------------------------------
# F03 — O PASSO ÓRFÃO ENTRA NA RECUPERAÇÃO
# ---------------------------------------------------------------------------

def _aprovacao_com_orfao(monkeypatch, ledger, *, jovem: bool):
    cliente = _cliente()
    aprovacao = asyncio.run(_aprovar(cliente, ledger, _plano_para_envio())).json()
    aid = aprovacao["aprovacao"]["approval_id"]
    ledger.passos["passo-campaign"] = {
        "approval_id": aid, "nome": "campaign", "ordinal": 1,
        # O processo caiu entre o POST e o registro da conclusão.
        "state": "IN_FLIGHT", "id_externo": None, "codigo": None,
        "readback": None, "jovem": jovem,
        "prepared_at": "2999-01-01T00:00:00+00:00" if jovem else "2026-09-05T12:00:00+00:00",
    }
    return cliente, aid


def test_passo_in_flight_orfao_entra_na_reconciliacao(monkeypatch) -> None:
    """Antes a rota dizia `passos_ambiguos: 0` sobre um despacho sem conclusão.

    Essa resposta é indistinguível de "nada travado", enquanto o objeto pode
    existir na conta — e o índice de gêmeo entre aprovações trata IN_FLIGHT como
    reivindicação viva, então o órfão bloqueava PERMANENTEMENTE qualquer
    aprovação futura de criar aquele objeto.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente, aid = _aprovacao_com_orfao(monkeypatch, ledger, jovem=False)

    resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar",
                            json={"approval_id": aid})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["passos_promovidos"] == ["campaign"]
    assert corpo["passos_ambiguos"] == 1
    assert ledger.passos["passo-campaign"]["state"] == "AMBIGUOUS"
    # ⚠️ Promover NÃO despacha. A recuperação continua sendo leitura.
    assert corpo["efeito_externo"] == "NENHUM"
    assert not any(evento[0] == "preparar" for evento in ledger.eventos[2:])


def test_orfao_jovem_nao_e_promovido_mas_tambem_nao_e_escondido(monkeypatch) -> None:
    """Um passo recém-preparado pode ter trabalhador vivo por trás.

    Promovê-lo abriria uma corrida contra a saga em curso. Mas silenciá-lo
    devolveria a mesma resposta enganosa por outra porta — por isso ele APARECE
    em `passos_em_voo` mesmo sem ser promovido.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente, aid = _aprovacao_com_orfao(monkeypatch, ledger, jovem=True)

    resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar",
                            json={"approval_id": aid})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["passos_promovidos"] == []
    assert corpo["passos_ambiguos"] == 0
    assert corpo["passos_em_voo"] == ["campaign"]
    assert ledger.passos["passo-campaign"]["state"] == "IN_FLIGHT"


def test_ausencia_apos_o_despacho_nunca_libera_reenvio(monkeypatch) -> None:
    """A leitura não encontrou o objeto — e isso não prova que ele não existe."""
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente, aid = _aprovacao_com_orfao(monkeypatch, ledger, jovem=False)
    CENARIO.listagens = {"campaigns": []}

    resposta = cliente.post("/api/trafego/meta/local/criacao/reconciliar",
                            json={"approval_id": aid})
    assert resposta.status_code == 200, resposta.text
    conclusoes = resposta.json()["conclusoes"]
    assert conclusoes and all(
        item["conclusao"] == "PERMANECE_AMBIGUO" for item in conclusoes)
    assert ledger.passos["passo-campaign"]["state"] == "AMBIGUOUS"
    # Nenhum POST saiu, e o passo NÃO foi fechado como falho — fechar seria
    # autorizar um reenvio sobre um objeto que pode existir.
    assert not any(evento[0] == "falhar" for evento in ledger.eventos)


# ---------------------------------------------------------------------------
# DESPACHAR USA O SNAPSHOT — E A REVOGAÇÃO CONTINUA VALENDO
# ---------------------------------------------------------------------------

def test_criar_pausada_despacha_o_snapshot_sem_reler_a_biblioteca(monkeypatch) -> None:
    """Criar deixa de reler a conta para reconstruir o que já foi aprovado."""
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    aprovacao = asyncio.run(_aprovar(cliente, ledger, _plano_para_envio())).json()

    CENARIO.gets.clear()
    resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
        "approval_id": aprovacao["aprovacao"]["approval_id"],
        "plano_sha256_esperado": aprovacao["aprovacao"]["plano_sha256"],
    })
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["desfecho"] == "CREATED_PAUSED"

    lidas = list(CENARIO.gets)
    assert not any("/adimages" in url for url in lidas), lidas
    assert not any("fbcdn.net" in url for url in lidas), lidas


def test_revogar_o_destino_da_conta_recusa_o_despacho_com_nome_proprio(
    monkeypatch,
) -> None:
    """A revogação passa a ser um mecanismo, e não um acidente de hash.

    ⚠️ Antes, retirar a conta da lista de conferidas bloqueava o despacho porque
    a RECOMPILAÇÃO mudava o hash. Funcionava por acidente, com a mensagem
    errada — e o mesmo mecanismo quebrava a recuperação histórica junto. Agora
    a pergunta é feita explicitamente, e é a ÚNICA pergunta sobre o presente que
    o despacho ainda faz.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    aprovacao = asyncio.run(_aprovar(cliente, ledger, _plano_para_envio())).json()

    monkeypatch.delenv("META_SHOP_REDIRECT_CLEARED", raising=False)
    resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
        "approval_id": aprovacao["aprovacao"]["approval_id"],
        "plano_sha256_esperado": aprovacao["aprovacao"]["plano_sha256"],
    })
    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["detail"]["codigo"] == "META_SHOP_REDIRECT_REVOKED"
    # Nada foi despachado.
    assert not any(evento[0] == "preparar" for evento in ledger.eventos)


def test_recuperacao_continua_disponivel_com_a_criacao_fechada(monkeypatch) -> None:
    """Fechar a criação não pode fechar a saída de um incidente.

    `/reconciliar` e `/recibo` dependem só da autoridade do LEDGER; a flag de
    criação governa o POST que faz nascer objeto. Confundir as duas deixaria o
    operador sem caminho de saída exatamente quando ele mais precisa.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente, aid = _aprovacao_com_orfao(monkeypatch, ledger, jovem=False)

    monkeypatch.delenv("META_CREATE_PAUSED_ENABLED", raising=False)

    recibo = cliente.post("/api/trafego/meta/local/criacao/recibo",
                          json={"approval_id": aid})
    assert recibo.status_code == 200, recibo.text
    reconciliar = cliente.post("/api/trafego/meta/local/criacao/reconciliar",
                               json={"approval_id": aid})
    assert reconciliar.status_code == 200, reconciliar.text
    assert reconciliar.json()["passos_promovidos"] == ["campaign"]

    # E criar continua fechado.
    criar = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
        "approval_id": aid, "plano_sha256_esperado": "a" * 64})
    assert criar.status_code == 409
    assert criar.json()["detail"]["codigo"] == "META_CREATE_PAUSED_BLOCKED"


# ---------------------------------------------------------------------------
# EVIDÊNCIA DE READ-BACK — o positivo também fica gravado
# ---------------------------------------------------------------------------

def test_read_back_positivo_vira_evidencia_duravel(monkeypatch) -> None:
    """Antes só o fracasso ficava registrado.

    Uma confirmação que existe apenas no corpo da resposta HTTP existe apenas no
    navegador — e mensagem de tela não é recibo.
    """
    ledger = _LedgerEmMemoria()
    _abrir(monkeypatch, ledger)
    cliente = _cliente()
    aprovacao = asyncio.run(_aprovar(cliente, ledger, _plano_para_envio())).json()
    resposta = cliente.post("/api/trafego/meta/local/criacao/criar-pausada", json={
        "approval_id": aprovacao["aprovacao"]["approval_id"],
        "plano_sha256_esperado": aprovacao["aprovacao"]["plano_sha256"],
    })
    assert resposta.status_code == 200, resposta.text

    passo = ledger.passos["passo-campaign"]
    assert passo["state"] == "CREATED"
    assert passo["id_externo"] == IDS_CRIADOS["campaign"]
    evidencia = passo["readback_evidencia"]
    assert evidencia["matched"] is True
    assert evidencia["status"] == "PAUSED"
    assert passo["readback_at"]
    # A evidência é uma PROJEÇÃO sanitizada, não uma cópia do payload.
    assert "object_story_spec" not in evidencia
    assert IDS_CRIADOS["campaign"] not in str(evidencia)
