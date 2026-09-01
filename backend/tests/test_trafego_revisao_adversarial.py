"""As dez provas nascidas da revisão adversarial de 02/09/2026.

## De onde elas vêm

Codex `gpt-5.6-sol` (effort high) revisou o diff desta missão contra a base
`26a58c4` sob a regra "achado sem contraprova executável é descartado". Ele
devolveu **dez achados, todos com contraprova que roda** — dois BLOQUEANTES,
sete IMPORTA e um MENOR. Adjudiquei um por um: **os dez procedem.**

Cada teste aqui falhava contra o código que a revisão reprovou. Nenhum deles foi
escrito para confirmar a correção depois de ela existir.

## Os dois BLOQUEANTES, e o que eles tinham em comum

Os dois eram a mesma família: **conferir a COLUNA e devolver o PAYLOAD.**

    coluna 5478096539 · payload_devolvido 4820015411 · persistido True
    vinculado True · documento_customer_id 4820015411

A linha do banco tem `customer_id` como coluna e o plano inteiro em `payload`.
Eu conferia a coluna — que é o que a consulta filtrou — e devolvia (ou
regravava) o payload, que ninguém tinha olhado. Uma consulta é uma INTENÇÃO; a
conferência é um FATO, e eu estava conferindo a intenção.

O consenso das duas correções: depois de `pm.do_json`, o plano reconstruído é
confrontado com o pedido E com a linha, e diverge = recusa nomeada.

## Os oito restantes, em uma frase cada

3. `activation_ready` saía `PRONTO` com `campaign_birth = NAO_PRONTO` — ativação
   pronta para uma campanha que não existe;
4. `Prontidao(smart_bidding_eligible=True)` construído à mão produzia
   `smart_bidding_ready = PRONTO` com mensuração indeterminada;
5. estratégia desconhecida atravessava o portão de escrita quando a medição
   estava pronta — o fail-closed só valia no caso já fechado;
6. `RegraDeValor` aceitava valor negativo, e o portão só olhava o modo;
7. `_slug` prometia na docstring que `BPC/LOAS` e `bpc-loas` eram a mesma
   oferta, e produzia duas identidades;
8. a moeda do EVENTO não era validada — `💩` passava como `currencyCode`;
9. o consentimento do usuário mudava o veredito do item e não entrava na
   impressão do envelope: dois lotes com vereditos opostos colidiam;
10. o mesmo instante em dois fusos produzia impressões diferentes, e o retry
    viraria um segundo lote.
"""
from __future__ import annotations

import asyncio
import socket
from decimal import Decimal

import pytest

from app.trafego import data_manager as dm
from app.trafego import perfil_de_mensuracao as pdm
from app.trafego import plano_mensuracao as pm
from app.trafego import prontidao as pr
from app.routers import trafego

import test_trafego_plano_relido as rel
import test_trafego_portoes_de_escrita as pt


@pytest.fixture(autouse=True)
def _rede_bloqueada(monkeypatch: pytest.MonkeyPatch):
    def recusar_rede(_socket, _address):
        pytest.fail("teste da revisão adversarial tentou abrir conexão de rede")

    monkeypatch.setattr(socket.socket, "connect", recusar_rede)
    monkeypatch.setattr(socket.socket, "connect_ex", recusar_rede)


# ═══════════════════════════════════════════════════════════════════════════
# BLOQUEANTE 1 (achado 9) — o GET devolvia payload de outra conta
# ═══════════════════════════════════════════════════════════════════════════


def _repo_com(linha):
    class Repo:
        habilitado = True

        async def vigente_da_conta(self, _cid):
            return linha

        async def vigente_da_campanha(self, _v):
            return linha

    return Repo()


def _ler(monkeypatch, linha, **kw):
    monkeypatch.setattr(trafego, "_repositorio_de_plano", lambda: _repo_com(linha))
    try:
        return asyncio.run(trafego.plano_de_mensuracao_vigente(
            customer_id=kw.get("customer_id", rel.CONTA),
            login_customer_id=kw.get("login_customer_id", rel.MCC),
            campaign_id=kw.get("campaign_id"),
            identidade=rel.IDENTIDADE))
    except Exception as exc:  # noqa: BLE001 — HTTPException é o desfecho esperado
        return exc


def test_payload_de_outra_conta_nao_e_devolvido_mesmo_com_a_coluna_certa(monkeypatch):
    """⚠️ Conferir a COLUNA e devolver o PAYLOAD.

    Reproduzido: coluna `5478096539`, payload da `4820015411`, resposta
    `persistido: True`. A consulta filtrou pela coluna; ninguém olhou o
    conteúdo. Uma consulta é uma intenção — a conferência é um fato.
    """
    linha = rel._linha(rel._plano(customer_id=rel.CONTA))
    linha["payload"] = rel._plano(customer_id=rel.OUTRA_CONTA).para_json()
    saida = _ler(monkeypatch, linha)
    assert isinstance(saida, Exception)
    assert getattr(saida, "status_code", None) == 409
    # ⚠️ E a conta alheia NÃO aparece na mensagem: recusar não é vazar.
    assert rel.OUTRA_CONTA not in str(getattr(saida, "detail", ""))


def test_payload_de_outro_mcc_tambem_e_recusado(monkeypatch):
    """O MCC também endereça: um plano do MCC errado descreve outra hierarquia."""
    plano = pm.montar(customer_id=rel.CONTA, login_customer_id="9999999999",
                      meta_efetiva=rel._meta(), acoes=(rel._acao(),),
                      acoes_estado=pm.COM_DADOS)
    linha = rel._linha(rel._plano())
    linha["payload"] = plano.para_json()
    saida = _ler(monkeypatch, linha)
    assert getattr(saida, "status_code", None) == 409


def test_a_linha_coerente_continua_passando(monkeypatch):
    """O ramo POSITIVO — sem ele a guarda nova só provaria que bloqueia tudo."""
    saida = _ler(monkeypatch, rel._linha(rel._plano()))
    assert not isinstance(saida, Exception), saida
    assert saida["persistido"] is True


# ═══════════════════════════════════════════════════════════════════════════
# BLOQUEANTE 2 (achado 10) — a reconciliação regravava payload alheio
# ═══════════════════════════════════════════════════════════════════════════


def test_reconciliar_nao_grava_documento_de_outra_conta(monkeypatch):
    """⚠️ O recorte por conta olhava a coluna; o que ia para a RPC era o payload.

    Reproduzido: `vinculado True`, `documento_customer_id 4820015411`, e o
    `volc_campaign_id` derivado da conta PEDIDA. A linha gravada apontaria uma
    campanha de uma conta para o plano de outra.
    """
    linha = rel._linha_de_intencao(rel.CHAVE_DA_CASA, customer_id=rel.CONTA)
    linha["payload"] = rel._plano(customer_id=rel.OUTRA_CONTA).para_json()
    linha["payload"]["chave_intencao"] = rel.CHAVE_DA_CASA
    repo = rel.RepoDeReconciliacao([linha])
    saida = rel._reconciliar(monkeypatch, repo)
    assert saida["vinculo"]["vinculado"] is False
    assert repo.gravou == []
    assert "conta" in saida["vinculo"]["porque"].lower()


def test_reconciliar_com_payload_coerente_continua_vinculando(monkeypatch):
    repo = rel.RepoDeReconciliacao([
        rel._linha_de_intencao(rel.CHAVE_DA_CASA, customer_id=rel.CONTA)])
    saida = rel._reconciliar(monkeypatch, repo)
    assert saida["vinculo"]["vinculado"] is True
    assert len(repo.gravou) == 1
    assert repo.gravou[0]["customer_id"] == rel.CONTA


# ═══════════════════════════════════════════════════════════════════════════
# ACHADO 1 — ativação pronta para campanha que não nasceu
# ═══════════════════════════════════════════════════════════════════════════


def test_ativacao_nao_fica_pronta_antes_do_nascimento():
    """⚠️ "Ativar" é DESPAUSAR algo que existe.

    Reproduzido: `campaign_birth=NAO_PRONTO` e `activation_ready=PRONTO`, com
    `activation_blockers` vazio. A própria resposta afirmava que a campanha não
    nasceu e que despausá-la era seguro.
    """
    r = pr.avaliar(
        plano_valido=True, recibo_registrado=False, metas_da_conta=None,
        plano_de_mensuracao=pt._plano(), coleta_pos_criacao_provada=True,
        plano_persistido=True, ativacao_autorizada_por_politica=True)
    assert r.campaign_birth == pr.NAO_PRONTO
    assert r.activation_ready != pr.PRONTO
    assert any("nasceu" in b for b in r.activation_blockers)


def test_nascida_e_medida_e_autorizada_continua_abrindo():
    r = pr.avaliar(
        plano_valido=True, recibo_registrado=True, metas_da_conta=None,
        plano_de_mensuracao=pt._plano(), coleta_pos_criacao_provada=True,
        plano_persistido=True, ativacao_autorizada_por_politica=True)
    assert r.activation_ready == pr.PRONTO


# ═══════════════════════════════════════════════════════════════════════════
# ACHADO 2 — elegibilidade escrita à mão sem evidência
# ═══════════════════════════════════════════════════════════════════════════


def test_elegibilidade_sem_medicao_provada_e_recusada_na_construcao():
    """⚠️ A propriedade derivava do booleano, e o booleano era escrevível.

    Reproduzido: `Prontidao(smart_bidding_eligible=True)` devolvia
    `smart_bidding_ready=PRONTO` com medição e observabilidade INDETERMINADAS.
    Derivar não basta se a fonte da derivação puder ser afirmada sem lastro.
    """
    with pytest.raises(ValueError, match="[Ss]mart [Bb]idding"):
        pr.Prontidao(smart_bidding_eligible=True)


def test_elegibilidade_com_as_duas_provas_e_aceita():
    ok = pr.Prontidao(smart_bidding_eligible=True,
                      measurement_readiness=pr.PRONTO,
                      observability_status=pr.PRONTO)
    assert ok.smart_bidding_ready == pr.PRONTO


# ═══════════════════════════════════════════════════════════════════════════
# ACHADO 3 — estratégia desconhecida falhava ABERTA
# ═══════════════════════════════════════════════════════════════════════════


def test_estrategia_desconhecida_e_recusada_mesmo_com_medicao_provada():
    """⚠️ O fail-closed só valia no caso que já estava fechado.

    Reproduzido: `exigir_para_criacao(estrategia_lance="ESTRATEGIA_INVENTADA")`
    com `measurement_ready=PRONTO` atravessava. A guarda anterior recusava o
    desconhecido só quando a medição já recusava — ou seja, nunca.
    """
    pronta = pt._pronta()
    assert pronta.measurement_ready == pr.PRONTO
    with pytest.raises(pr.EstrategiaDesconhecida):
        pr.exigir_para_criacao(estrategia_lance="ESTRATEGIA_INVENTADA",
                               prontidao=pronta)


def test_target_roas_e_tratado_como_lance_por_VALOR():
    """TARGET_ROAS otimiza pelo valor, e o portão precisa saber disso."""
    with pytest.raises(pr.LanceSemValor):
        pr.exigir_para_criacao(estrategia_lance="TARGET_ROAS",
                               prontidao=pt._pronta())


def test_as_tres_estrategias_do_engine_sao_conhecidas():
    """⚠️ A lista fechada tem de cobrir o que o executor de fato aceita.

    `volc_ads/campanha/brief.py:ESTRATEGIAS_DE_LANCE` são exatamente três. Uma
    classificação que não as cobrisse recusaria o caminho produtivo inteiro.
    """
    from volc_ads.campanha.brief import ESTRATEGIAS_DE_LANCE

    conhecidas = set(pr.ESTRATEGIAS_CONHECIDAS)
    assert set(ESTRATEGIAS_DE_LANCE) <= conhecidas


# ═══════════════════════════════════════════════════════════════════════════
# ACHADO 4 — regra de valor com número impossível
# ═══════════════════════════════════════════════════════════════════════════


def test_regra_de_valor_negativa_e_recusada():
    """Reproduzido: o portão de MaxConvValue atravessava com `valor=-1`."""
    with pytest.raises(ValueError, match="negativo|finito"):
        pdm.RegraDeValor(modo=pdm.VALOR_FIXO, valor=Decimal("-1"), moeda="BRL")


def test_regra_de_valor_nao_finita_e_recusada():
    with pytest.raises(ValueError, match="finito"):
        pdm.RegraDeValor(modo=pdm.VALOR_FIXO, valor=Decimal("NaN"), moeda="BRL")


def test_valor_zero_continua_sendo_um_valor_declarado():
    """⚠️ Zero é uma decisão; negativo é um erro. Não colapsar os dois."""
    assert pdm.RegraDeValor(modo=pdm.VALOR_FIXO, valor=Decimal("0"),
                            moeda="BRL").valor == Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════
# ACHADO 5 — o slug prometia canonicalizar e não canonicalizava
# ═══════════════════════════════════════════════════════════════════════════


def test_separador_nao_canonico_e_RECUSADO_e_nao_silenciosamente_aceito():
    """⚠️ A docstring dizia que `BPC/LOAS` e `bpc-loas` eram a mesma oferta.

    Reproduzido: `bpc/loas` e `bpc-loas` produziam chaves diferentes. Havia duas
    saídas — fundir os separadores ou recusar o que não é canônico — e fundir é
    pior: `x/y` e `x-y` podem ser ofertas genuinamente diferentes, e a fusão
    seria um merge silencioso, que é o defeito oposto e mais caro.

    Recusar deixa o erro visível no primeiro uso, e não seis meses depois.
    """
    with pytest.raises(ValueError, match="canônic|caracteres"):
        pdm.PerfilDeMensuracao(
            customer_id="5478096539", login_customer_id="1234567890",
            negocio="n", intencao="BPC/LOAS", funil=pdm.FUNIL_ACAO, evento="e",
            acao_owner_id=None, acao_id=None, semantica=None,
            regra_de_valor=pdm.regra_sem_valor(),
            janela=pdm.janela_nao_declarada())


def test_maiusculas_e_espacos_continuam_sendo_normalizados():
    """O que a normalização SEMPRE pôde fazer com segurança continua valendo."""
    a = pdm.PerfilDeMensuracao(
        customer_id="5478096539", login_customer_id="1234567890",
        negocio="n", intencao="  BPC-LOAS  ", funil=pdm.FUNIL_ACAO, evento="e",
        acao_owner_id=None, acao_id=None, semantica=None,
        regra_de_valor=pdm.regra_sem_valor(), janela=pdm.janela_nao_declarada())
    assert a.intencao == "bpc-loas"


# ═══════════════════════════════════════════════════════════════════════════
# ACHADO 6 — moeda do evento não validada
# ═══════════════════════════════════════════════════════════════════════════


def _evento(**mud):
    base = dict(
        clique=dm.IdentificadorDeClique(tipo=dm.CLIQUE_GCLID, valor="Cj0KEQ"),
        ocorrido_em="2026-09-01T14:32:00-03:00",
        chave_de_deduplicacao="pedido-1",
        consentimento_do_usuario=dm.CONSENTIMENTO_CONCEDIDO)
    base.update(mud)
    return dm.EventoDeConversao(**base)


def _envelope(eventos):
    from test_trafego_data_manager import _perfil, _plano

    return dm.montar_envelope(plano=_plano(), perfil=_perfil(), eventos=eventos)


def test_moeda_que_nao_e_iso_4217_e_recusada():
    """Reproduzido: `moeda="💩"` saía `valido`, sem causa."""
    recibo = dm.validar(_envelope((_evento(valor=Decimal("10"), moeda="💩"),)))
    assert recibo.itens[0].estado == dm.ITEM_RECUSADO
    assert "ISO" in (recibo.itens[0].causa or "")


def test_moeda_de_tres_letras_atravessa_e_e_normalizada():
    env = _envelope((_evento(valor=Decimal("10"), moeda="brl"),))
    assert dm.validar(env).aceitos == 1
    assert env.json()["itens"][0]["moeda"] == "BRL"


# ═══════════════════════════════════════════════════════════════════════════
# ACHADO 7 — consentimento fora da impressão do envelope
# ═══════════════════════════════════════════════════════════════════════════


def test_consentimentos_opostos_nao_colidem_na_mesma_impressao():
    """⚠️ Ele muda o VEREDITO do item e não entrava na identidade do lote.

    Reproduzido: dois envelopes idênticos exceto pelo consentimento produziam a
    MESMA impressão e vereditos opostos (`valido` × `recusado`). É a mesma
    família do defeito que a impressão do PLANO já tinha corrigido duas vezes:
    o que decide precisa entrar na identidade, ou o segundo é lido como retry
    do primeiro.
    """
    concedido = _envelope((_evento(),))
    negado = _envelope((
        _evento(consentimento_do_usuario=dm.CONSENTIMENTO_NEGADO),))
    assert concedido.impressao() != negado.impressao()
    assert dm.validar(concedido).aceitos == 1
    assert dm.validar(negado).recusados == 1


# ═══════════════════════════════════════════════════════════════════════════
# ACHADO 8 — o mesmo instante em dois fusos
# ═══════════════════════════════════════════════════════════════════════════


def test_o_mesmo_instante_em_fusos_diferentes_e_o_mesmo_lote():
    """⚠️ Reenviar o mesmo lote com a hora escrita em Z criaria um SEGUNDO lote.

    Reproduzido: `2026-09-01T12:00:00-03:00` e `2026-09-01T15:00:00Z` são o
    mesmo instante, os dois eventos saíam válidos, e as impressões diferiam.
    """
    a = _envelope((_evento(ocorrido_em="2026-09-01T12:00:00-03:00"),))
    b = _envelope((_evento(ocorrido_em="2026-09-01T15:00:00Z"),))
    assert dm.validar(a).aceitos == 1 and dm.validar(b).aceitos == 1
    assert a.impressao() == b.impressao()


def test_instantes_de_fato_diferentes_continuam_diferentes():
    """A recíproca — sem ela, canonicalizar poderia estar apagando o tempo."""
    a = _envelope((_evento(ocorrido_em="2026-09-01T12:00:00-03:00"),))
    b = _envelope((_evento(ocorrido_em="2026-09-01T12:00:00Z"),))
    assert a.impressao() != b.impressao()


def test_hora_ilegivel_nao_derruba_a_impressao():
    """⚠️ A impressão não pode depender de o evento ser válido.

    Um lote com uma hora malformada continua sendo um lote com identidade — é a
    validação, item a item, que reprova o evento. Levantar aqui transformaria
    falha parcial em falha total pela porta dos fundos.
    """
    env = _envelope((_evento(ocorrido_em="ontem"),))
    assert env.impressao()
    assert dm.validar(env).recusados == 1
