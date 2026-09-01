"""A fronteira da Data Manager: monta, valida, e NÃO envia.

## A auditoria que veio antes de uma linha de código

O contrato manda reusar `conversion_queue` e `conversion_batches` se elas já
forem autoridades adequadas. Elas foram auditadas, e não são — e a razão não é
de gosto:

    conversion_queue  (viva, 0 linhas, lida em 22/08/2026)
      batch_id · bucket_weight · conversion_time · conversion_value ·
      created_at · currency_code · gclid · google_error · id ·
      original_bucket · sent_at · status · visit_id

Faltam CINCO coisas sem as quais um envio governado não existe:

  1. **destino** — nenhuma coluna diz conta DONA nem id NUMÉRICO da ação. A
     Data Manager resolve destino por esse par, e uma fila sem ele descreve um
     envio sem endereço;
  2. **conta** — não há `customer_id`. A fila foi desenhada para UMA conta;
  3. **wbraid/gbraid** — só `gclid`. Clique de app e de iOS sem `gclid` não
     cabem, e são exatamente os que mais dependem de upload offline;
  4. **consentimento** — nenhuma coluna. Consentimento viaja COM o evento;
  5. **chave de deduplicação** — `id` é surrogate. Sem `transaction_id`, um
     retry duplica a conversão em vez de substituí-la.

Além disso as duas tabelas **não têm DDL no repositório**: `grep` em
`supabase/migrations/` não as encontra. Elas existem no banco e não são
governadas por este código.

Conclusão registrada: **nenhuma fila nova foi criada nesta entrega, e nenhum
schema foi tocado.** O que falta às tabelas vivas exige migration, e migration é
decisão de dono — está no pacote de autorização. Esta entrega fecha a parte que
não precisa de banco: montar o envelope, validá-lo item a item, e recusar o
envio.

## O que este módulo é

Domínio puro. Zero rede, zero cliente HTTP, zero credencial. `enviar` não
existe como caminho — existe como recusa nomeada.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.trafego import data_manager as dm
from app.trafego import perfil_de_mensuracao as pdm
from app.trafego import plano_mensuracao as pm


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


def _acao(id_numerico="7498530235", owner="1234567890", tipo="WEBPAGE"):
    return pm.AcaoDeConversao(
        id=id_numerico,
        resource_name=f"customers/{owner}/conversionActions/{id_numerico}",
        owner_customer_id=owner, nome="Compra — site",
        categoria="PURCHASE", origem="WEBSITE", tipo=tipo,
        status="ENABLED", primaria=True)


def _plano(acao=None):
    return pm.montar(
        customer_id="5478096539", login_customer_id="6016739364",
        meta_efetiva=pm.MetaEfetiva(
            nivel=pm.NIVEL_CUSTOMER, nivel_estado=pm.COM_DADOS,
            metas_da_conta=(pm.Meta(categoria="PURCHASE", origem="WEBSITE",
                                    biddable=True),),
            metas_da_conta_estado=pm.COM_DADOS,
            metas_da_campanha=(), metas_da_campanha_estado=pm.INELEGIVEL),
        acoes=(acao or _acao(),), acoes_estado=pm.COM_DADOS,
        marcacao=pm.InventarioDeMarcacao(
            estado=pm.COM_DADOS, auto_tagging=True,
            aceitou_termos_de_dados=True))


def _perfil(**mud):
    base = dict(negocio="portal-mundo-mais", intencao="bpc-loas",
                funil=pdm.FUNIL_ACAO, evento="lead-qualificado")
    base.update(mud)
    return pdm.derivar_de_plano(_plano(), **base)


def _evento(**mud):
    base = dict(
        clique=dm.IdentificadorDeClique(tipo=dm.CLIQUE_GCLID, valor="Cj0KEQ_abc"),
        ocorrido_em="2026-09-01T14:32:00-03:00",
        chave_de_deduplicacao="pedido-4711",
        consentimento_do_usuario=dm.CONSENTIMENTO_CONCEDIDO,
    )
    base.update(mud)
    return dm.EventoDeConversao(**base)


def _montar(eventos=None, perfil=None, plano=None):
    return dm.montar_envelope(
        plano=plano or _plano(),
        perfil=perfil or _perfil(),
        eventos=eventos if eventos is not None else (_evento(),))


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 1 — ZERO envio. É o contrato inteiro desta entrega.
# ═══════════════════════════════════════════════════════════════════════════


def test_o_modulo_nao_tem_caminho_de_envio():
    """⚠️ Nenhuma função deste módulo fala com a rede, e a prova é estrutural.

    Um módulo que "não envia porque ninguém chamou" depende de ninguém chamar.
    Aqui não há cliente HTTP, não há URL e não há credencial: o que existe é uma
    recusa nomeada, para que quem procurar o caminho de envio o ENCONTRE — e
    encontre a razão junto.
    """
    import inspect

    fonte = inspect.getsource(dm)
    for proibido in ("httpx", "requests", "urllib", "googleapis.com", "aiohttp"):
        assert proibido not in fonte, proibido


def test_enviar_e_recusa_nomeada_e_nao_ausencia():
    with pytest.raises(dm.EnvioNaoAutorizado) as exc:
        dm.enviar(_montar())
    assert "validateOnly" in str(exc.value)


def test_o_recibo_declara_que_nada_saiu():
    recibo = dm.validar(_montar())
    assert recibo.validate_only is True
    assert recibo.enviado is False
    assert recibo.json()["enviado"] is False


def test_validate_only_nao_pode_ser_desligado():
    """⚠️ Não há parâmetro que o desligue. Um flag seria uma porta."""
    import inspect

    assert "validate_only" not in inspect.signature(dm.validar).parameters


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 2 — destino: conta DONA + id NUMÉRICO, nunca nome
# ═══════════════════════════════════════════════════════════════════════════


def test_o_envelope_endereca_por_dono_e_id_numerico():
    env = _montar()
    assert env.destino.operating_account_id == "1234567890"
    assert env.destino.product_destination_id == "7498530235"
    assert "Compra" not in env.json_canonico()


def test_sem_destino_resolvido_nao_existe_envelope():
    """⚠️ Recusa do ENVELOPE inteiro, e não item a item.

    Item inválido é um evento que não pode ir; destino ausente é não haver para
    onde ir. Deixar o envelope nascer sem destino produziria um pacote
    sintaticamente válido apontando para conta nenhuma — e a Data Manager
    resolve destino por conta dona + id, não por adivinhação.
    """
    sem_acao = pm.montar(customer_id="5478096539",
                         login_customer_id="6016739364",
                         acoes=(), acoes_estado=pm.COM_DADOS)
    assert sem_acao.destino.resolvido is False
    with pytest.raises(dm.DestinoNaoResolvido, match="destino"):
        _montar(plano=sem_acao, perfil=pdm.derivar_de_plano(
            sem_acao, negocio="n", intencao="i", funil=pdm.FUNIL_ACAO,
            evento="e"))


def test_perfil_que_aponta_para_outra_acao_nao_monta_envelope():
    """O perfil diz #X, o plano elegeu #Y: o envio iria para o lugar errado."""
    outro = pdm.derivar_de_plano(
        _plano(_acao("111222333")), negocio="n", intencao="i",
        funil=pdm.FUNIL_ACAO, evento="e")
    with pytest.raises(ValueError, match="ação"):
        _montar(perfil=outro)


def test_acao_de_tipo_nao_aceito_como_destino_e_recusada():
    """Nem toda ConversionAction aceita ingestão offline, e o tipo diz qual."""
    upload = _plano(_acao(tipo="UPLOAD_CLICKS"))
    assert upload.destino.resolvido is True
    naovai = _plano(_acao(tipo="GOOGLE_PLAY_DOWNLOAD"))
    assert naovai.destino.resolvido is False


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 3 — consentimento
# ═══════════════════════════════════════════════════════════════════════════


def test_perfil_sem_consentimento_concedido_nao_monta_envelope():
    """⚠️ Aqui `nao_declarado` NÃO passa, e a assimetria é deliberada.

    Medir por tag do Google não depende de nós declararmos consentimento — o
    site declara. Mandar evento pela Data Manager, sim: somos NÓS que
    afirmamos, no envelope, que havia base para enviar.
    """
    plano = pm.montar(
        customer_id="5478096539", login_customer_id="6016739364",
        meta_efetiva=_plano().meta_efetiva, acoes=(_acao(),),
        acoes_estado=pm.COM_DADOS,
        marcacao=pm.InventarioDeMarcacao(estado=pm.COM_DADOS,
                                         aceitou_termos_de_dados=None))
    perfil = pdm.derivar_de_plano(plano, negocio="n", intencao="i",
                                  funil=pdm.FUNIL_ACAO, evento="e")
    assert perfil.consentimento == pdm.CONSENTIMENTO_NAO_DECLARADO
    with pytest.raises(dm.ConsentimentoInsuficiente):
        _montar(plano=plano, perfil=perfil)


def test_evento_sem_consentimento_do_usuario_e_recusado_ITEM_A_ITEM():
    """⚠️ Falha PARCIAL: um evento sem base não derruba o lote.

    Um lote de mil conversões em que uma não tem consentimento não é um lote
    inválido — são 999 conversões que precisam chegar e uma que não pode ir. O
    tudo-ou-nada aqui perderia as 999 por causa de uma.
    """
    recibo = dm.validar(_montar((
        _evento(chave_de_deduplicacao="a"),
        _evento(chave_de_deduplicacao="b",
                consentimento_do_usuario=dm.CONSENTIMENTO_NEGADO),
        _evento(chave_de_deduplicacao="c"),
    )))
    assert [i.estado for i in recibo.itens] == [
        dm.ITEM_VALIDO, dm.ITEM_RECUSADO, dm.ITEM_VALIDO]
    assert recibo.aceitos == 2 and recibo.recusados == 1
    assert "consentimento" in recibo.itens[1].causa


def test_o_consentimento_de_conta_e_o_do_usuario_sao_campos_diferentes():
    """⚠️ `accepted_customer_data_terms` é da CONTA, e não do visitante.

    Colapsá-los faria o envelope afirmar que o consentimento do usuário foi
    verificado quando o que se leu foi um aceite de termos do anunciante.
    """
    env = _montar()
    j = env.json()
    assert j["consentimento_da_conta"] == pdm.CONSENTIMENTO_CONCEDIDO
    assert j["itens"][0]["consentimento_do_usuario"] == dm.CONSENTIMENTO_CONCEDIDO


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 4 — identificador de clique
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("tipo", [dm.CLIQUE_GCLID, dm.CLIQUE_WBRAID,
                                  dm.CLIQUE_GBRAID])
def test_os_tres_identificadores_de_clique_sao_aceitos(tipo):
    """⚠️ `wbraid` e `gbraid` existem porque nem todo clique tem `gclid`.

    A fila legada (`conversion_queue`) só tem coluna `gclid` — e é justamente o
    tráfego de app e o de iOS com consentimento restrito que dependem dos
    outros dois. Uma fronteira que só aceita `gclid` descarta em silêncio a
    fatia que mais precisa de upload offline.
    """
    recibo = dm.validar(_montar((
        _evento(clique=dm.IdentificadorDeClique(tipo=tipo, valor="X123")),)))
    assert recibo.aceitos == 1


def test_identificador_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="identificador"):
        dm.IdentificadorDeClique(tipo="fbclid", valor="X")


def test_identificador_vazio_e_recusado():
    with pytest.raises(ValueError, match="vazio"):
        dm.IdentificadorDeClique(tipo=dm.CLIQUE_GCLID, valor="   ")


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 5 — event time
# ═══════════════════════════════════════════════════════════════════════════


def test_event_time_sem_fuso_e_recusado():
    """⚠️ Sem offset, "14:32" é um instante diferente em cada servidor.

    O Google atribui a conversão ao clique por janela de tempo. Uma hora sem
    fuso erra a janela inteira, e o erro é silencioso: a conversão é aceita e
    atribuída errado.
    """
    recibo = dm.validar(_montar((
        _evento(ocorrido_em="2026-09-01T14:32:00"),)))
    assert recibo.itens[0].estado == dm.ITEM_RECUSADO
    assert "fuso" in recibo.itens[0].causa


def test_event_time_ilegivel_e_recusado():
    recibo = dm.validar(_montar((_evento(ocorrido_em="ontem à tarde"),)))
    assert recibo.itens[0].estado == dm.ITEM_RECUSADO


def test_event_time_com_fuso_atravessa():
    for quando in ("2026-09-01T14:32:00-03:00", "2026-09-01T17:32:00Z",
                   "2026-09-01T17:32:00+00:00"):
        assert dm.validar(_montar((_evento(ocorrido_em=quando),))).aceitos == 1


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 6 — valor e moeda
# ═══════════════════════════════════════════════════════════════════════════


def test_valor_sem_moeda_e_recusado():
    recibo = dm.validar(_montar((_evento(valor=Decimal("49.90")),)))
    assert recibo.itens[0].estado == dm.ITEM_RECUSADO
    assert "moeda" in recibo.itens[0].causa


def test_moeda_sem_valor_e_recusada():
    recibo = dm.validar(_montar((_evento(moeda="BRL"),)))
    assert recibo.itens[0].estado == dm.ITEM_RECUSADO


def test_valor_e_moeda_juntos_atravessam():
    envelope = _montar((_evento(valor=Decimal("49.90"), moeda="BRL"),))
    assert dm.validar(envelope).aceitos == 1
    # ⚠️ O valor mora no ENVELOPE (o que se manda), e não no recibo (o que se
    # concluiu). Misturá-los faria o recibo virar uma segunda cópia do pacote.
    assert envelope.json()["itens"][0]["valor"] == "49.90"
    assert envelope.json()["itens"][0]["moeda"] == "BRL"


def test_valor_zero_e_MEDIDO_e_nao_ausencia():
    """⚠️ Zero é um valor. `if valor:` o trataria como ausente."""
    envelope = _montar((_evento(valor=Decimal("0"), moeda="BRL"),))
    assert dm.validar(envelope).aceitos == 1
    assert envelope.json()["itens"][0]["valor"] == "0"


def test_valor_negativo_e_recusado():
    recibo = dm.validar(_montar((
        _evento(valor=Decimal("-1"), moeda="BRL"),)))
    assert recibo.itens[0].estado == dm.ITEM_RECUSADO


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 7 — deduplicação e retry seguro
# ═══════════════════════════════════════════════════════════════════════════


def test_evento_sem_chave_de_deduplicacao_e_recusado():
    """⚠️ Sem ela, um retry DUPLICA a conversão em vez de substituí-la.

    É a lacuna que a fila legada tem: `conversion_queue.id` é surrogate, e um
    surrogate novo a cada tentativa não deduplica nada do lado do Google.
    """
    recibo = dm.validar(_montar((_evento(chave_de_deduplicacao=""),)))
    assert recibo.itens[0].estado == dm.ITEM_RECUSADO
    assert "dedup" in recibo.itens[0].causa.lower()


def test_chave_repetida_no_mesmo_envelope_e_recusada():
    """Duas linhas com a mesma chave no MESMO lote é ambiguidade nossa."""
    with pytest.raises(dm.EnvelopeAmbiguo, match="dedup"):
        _montar((_evento(chave_de_deduplicacao="x"),
                 _evento(chave_de_deduplicacao="x")))


def test_o_mesmo_envelope_tem_a_mesma_impressao():
    """Retry seguro: reenviar o mesmo pacote é o MESMO pacote."""
    assert _montar().impressao() == _montar().impressao()


def test_um_evento_a_mais_muda_a_impressao():
    dois = _montar((_evento(chave_de_deduplicacao="a"),
                    _evento(chave_de_deduplicacao="b")))
    assert dois.impressao() != _montar().impressao()


def test_a_impressao_nao_depende_da_ordem_dos_eventos():
    """⚠️ Reordenar não é um pacote novo — ou o retry criaria um segundo lote."""
    a = _montar((_evento(chave_de_deduplicacao="a"),
                 _evento(chave_de_deduplicacao="b")))
    b = _montar((_evento(chave_de_deduplicacao="b"),
                 _evento(chave_de_deduplicacao="a")))
    assert a.impressao() == b.impressao()


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 8 — o envelope é VERSIONADO
# ═══════════════════════════════════════════════════════════════════════════


def test_o_envelope_declara_versao_e_ela_entra_na_impressao():
    env = _montar()
    assert env.versao == dm.VERSAO_DO_ENVELOPE
    assert '"versao":1' in env.json_canonico().replace(" ", "")


def test_o_envelope_carrega_a_chave_do_perfil():
    """Quem auditar o pacote depois precisa saber QUAL medição ele serve."""
    perfil = _perfil()
    assert _montar(perfil=perfil).json()["perfil_chave"] == perfil.chave


def test_lote_vazio_e_recusado():
    """Um envelope sem evento não é um envelope — é um pedido sem conteúdo."""
    with pytest.raises(ValueError, match="vazio"):
        _montar(())


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 9 — o recibo é auditável e não esconde a recusa
# ═══════════════════════════════════════════════════════════════════════════


def test_o_recibo_nomeia_cada_recusa_e_nao_so_conta():
    recibo = dm.validar(_montar((
        _evento(chave_de_deduplicacao="ok"),
        _evento(chave_de_deduplicacao="sem-hora", ocorrido_em="1/9/26"),
        _evento(chave_de_deduplicacao="sem-moeda", valor=Decimal("10")),
    )))
    assert recibo.aceitos == 1 and recibo.recusados == 2
    for item in recibo.itens:
        if item.estado == dm.ITEM_RECUSADO:
            assert item.causa, "recusa anônima é indistinguível de silêncio"


def test_o_recibo_amarra_o_item_a_chave_e_nao_ao_indice():
    """Índice muda quando alguém filtra o lote; a chave é do evento."""
    recibo = dm.validar(_montar((
        _evento(chave_de_deduplicacao="pedido-1"),
        _evento(chave_de_deduplicacao="pedido-2"))))
    assert [i.chave_de_deduplicacao for i in recibo.itens] == [
        "pedido-1", "pedido-2"]


def test_nenhum_identificador_de_clique_aparece_no_recibo():
    """⚠️ `gclid` é dado de usuário; o recibo é objeto de log e de tela."""
    recibo = dm.validar(_montar())
    assert "Cj0KEQ_abc" not in str(recibo.json())
