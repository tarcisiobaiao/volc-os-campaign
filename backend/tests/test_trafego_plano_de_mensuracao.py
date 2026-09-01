"""O plano canônico de mensuração — e o portão que ele torna FALSIFICÁVEL.

## Por que este arquivo existe, e por que ele começa pelo par

Antes desta entrega, `smart_bidding_eligible` era `False` por construção: o ramo
`PRONTO` de `conversion_goal_status` era inalcançável, porque a leitura
disponível era uma GAQL sobre `conversion_action` e ela trava o teto em
`PARCIAL`. Isso tornava a afirmação "Smart Bidding está bloqueado"
**infalsificável** — qualquer teste que a escrevesse passaria com QUALQUER
entrada, inclusive com uma conta perfeitamente medida.

Um teste que não pode falhar não prova nada. O primeiro bloco daqui é o PAR: a
mesma função, com a evidência completa, devolve `True`; tirando UMA peça de cada
vez, devolve `False` — e cada `False` vem com a razão nomeada. É o par que vira
prova, nunca um lado sozinho.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.trafego import plano_mensuracao as pm  # noqa: E402
from app.trafego import prontidao as pr  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures fiéis — o que a API de fato devolve, e não o que seria cômodo
# ═══════════════════════════════════════════════════════════════════════════

HOJE = "2026-09-01"


def _meta(categoria="PURCHASE", origem="WEBSITE", biddable=True, campaign=None):
    return pm.Meta(categoria=categoria, origem=origem, biddable=biddable,
                   campaign=campaign)


def _acao(id="7466919994", categoria="PURCHASE", origem="WEBSITE",
          tipo="WEBPAGE", status="ENABLED", primaria=True,
          owner="5478096539", nome="Compra no site"):
    return pm.AcaoDeConversao(
        id=id,
        resource_name=f"customers/{owner or '0'}/conversionActions/{id}",
        owner_customer_id=owner,
        nome=nome, categoria=categoria, origem=origem, tipo=tipo,
        status=status, primaria=primaria, incluida_em_metricas=True)


def _meta_efetiva(*, nivel=pm.NIVEL_CUSTOMER, conta=(("PURCHASE", "WEBSITE", True),),
                  campanha=(), estado_conta=pm.COM_DADOS,
                  estado_campanha=pm.INELEGIVEL, estado_nivel=pm.COM_DADOS,
                  custom=None, campaign_id=None):
    return pm.MetaEfetiva(
        nivel=nivel,
        nivel_estado=estado_nivel,
        metas_da_conta=tuple(_meta(c, o, b) for c, o, b in conta),
        metas_da_conta_estado=estado_conta,
        metas_da_campanha=tuple(_meta(c, o, b, campaign="customers/1/campaigns/2")
                                for c, o, b in campanha),
        metas_da_campanha_estado=estado_campanha,
        campaign_id=campaign_id,
        custom_conversion_goal=custom,
    )


def _frescor_bom():
    return pm.Frescor(estado=pm.COM_DADOS, ultima_conversao_em="2026-08-30",
                      dias_desde_a_ultima=2, conversoes_na_janela=1.0,
                      conversion_action_id="7466919994")


def _marcacao_boa():
    return pm.InventarioDeMarcacao(
        estado=pm.COM_DADOS, auto_tagging=True,
        conversion_tracking_id="17862729897",
        conversion_tracking_owner_id="5478096539",
        conversion_tracking_status="CONVERSION_TRACKING_MANAGED_BY_SELF",
        aceitou_termos_de_dados=True,
        acoes_com_tag=("7466919994",))


def _plano_completo():
    """Uma conta em que TUDO está provado. Ela precisa existir para o par."""
    return pm.montar(
        customer_id="5478096539", login_customer_id="6016739364",
        meta_efetiva=_meta_efetiva(),
        acoes=(_acao(),), acoes_estado=pm.COM_DADOS,
        frescor=_frescor_bom(), marcacao=_marcacao_boa())


# ═══════════════════════════════════════════════════════════════════════════
# 1. O PAR FALSIFICÁVEL — o portão de Smart Bidding pode FALHAR
# ═══════════════════════════════════════════════════════════════════════════


def test_com_tudo_provado_o_smart_bidding_fica_elegivel():
    """O lado que faltava. Sem ele, "está bloqueado" passa com qualquer entrada.

    ⚠️ Exige as QUATRO provas juntas: meta efetiva resolvida com ação eleita
    (G1 meta), fonte de sinal comprovada (G1 sinal), releitura pós-criação
    provada (G2) — e é só então que G3 abre.
    """
    plano = _plano_completo()
    assert plano.completo, plano.bloqueadores

    r = pr.avaliar(
        recibo_registrado=True,
        metas_da_conta=None,
        plano_de_mensuracao=plano,
        coleta_pos_criacao_provada=True,
    )
    assert r.conversion_goal_status == pr.PRONTO
    assert r.conversion_signal_status == pr.PRONTO
    assert r.measurement_readiness == pr.PRONTO
    assert r.observability_status == pr.PRONTO
    assert r.smart_bidding_eligible is True, r.activation_blockers
    assert r.activation_blockers == ()


@pytest.mark.parametrize("peca", ["meta", "acao", "sinal", "observacao"])
def test_tirar_uma_peca_derruba_o_smart_bidding_com_razao_nomeada(peca):
    """A recíproca, peça por peça. Cada `False` tem de vir com a causa.

    ⚠️ Parametrizado de propósito: um teste único que tirasse tudo de uma vez
    provaria que "faltando tudo, bloqueia" — que é o caso fácil. O que decide é
    que faltando UMA coisa já bloqueia, e que a razão nomeada é a certa.
    """
    if peca == "meta":
        # A conta não tem meta biddable: existe objetivo nenhum a perseguir.
        plano = pm.montar(
            customer_id="5478096539", login_customer_id="6016739364",
            meta_efetiva=_meta_efetiva(conta=(("PURCHASE", "WEBSITE", False),)),
            acoes=(_acao(),), acoes_estado=pm.COM_DADOS,
            frescor=_frescor_bom(), marcacao=_marcacao_boa())
        observacao = True
    elif peca == "acao":
        # Há meta biddable, e nenhuma ação PRIMÁRIA que a meça.
        plano = pm.montar(
            customer_id="5478096539", login_customer_id="6016739364",
            meta_efetiva=_meta_efetiva(),
            acoes=(_acao(primaria=False),), acoes_estado=pm.COM_DADOS,
            frescor=_frescor_bom(), marcacao=_marcacao_boa())
        observacao = True
    elif peca == "sinal":
        # Nada comprova que conversão chega: sem tag, sem GA4, sem auto-tagging,
        # sem destino, e o frescor não foi lido.
        plano = pm.montar(
            customer_id="5478096539", login_customer_id="6016739364",
            meta_efetiva=_meta_efetiva(),
            acoes=(_acao(tipo="LEAD_FORM_SUBMIT"),), acoes_estado=pm.COM_DADOS,
            frescor=pm.frescor_nao_lido(),
            marcacao=pm.InventarioDeMarcacao(estado=pm.NAO_COLETADO,
                                             causa="ninguém inventariou"))
        observacao = True
    else:
        plano = _plano_completo()
        observacao = False

    r = pr.avaliar(recibo_registrado=True, metas_da_conta=None,
                   plano_de_mensuracao=plano,
                   coleta_pos_criacao_provada=observacao)
    assert r.smart_bidding_eligible is False
    assert r.activation_blockers, "bloqueou sem dizer por quê"


def test_o_par_nao_e_o_mesmo_teste_duas_vezes():
    """A guarda contra a prova infalsificável, escrita como teste.

    ⚠️ Se algum dia `smart_bidding_eligible` voltar a ser `False` por
    construção, o teste de cima quebra E este também — e este diz por quê, em
    vez de deixar alguém concluir que o portão "ficou mais seguro".
    """
    completo = pr.avaliar(recibo_registrado=True, metas_da_conta=None,
                          plano_de_mensuracao=_plano_completo(),
                          coleta_pos_criacao_provada=True)
    vazio = pr.avaliar(recibo_registrado=True, metas_da_conta=None,
                       plano_de_mensuracao=None)
    assert completo.smart_bidding_eligible != vazio.smart_bidding_eligible, (
        "os dois lados deram o mesmo veredito: o portão voltou a ser "
        "infalsificável, e qualquer teste sobre ele passa com qualquer entrada")


# ═══════════════════════════════════════════════════════════════════════════
# 2. `primary_for_goal` — o tri-estado que inverte o veredito
# ═══════════════════════════════════════════════════════════════════════════


def test_primary_for_goal_ausente_vale_true_como_a_doc_diz():
    """> "By default, `primary_for_goal` will be true if not set."

    ⚠️ O campo tem *presence* no proto v25 (conferido contra o descritor real).
    Lê-lo com `bool(...)` devolveria `False` para uma ação que o Google trata
    como primária — o veredito EXATAMENTE invertido, no campo que decide o
    lance.
    """
    ausente = _acao(primaria=None)
    assert ausente.primaria is None, "o que foi LIDO continua sendo 'não veio'"
    assert ausente.primaria_efetiva is True, "o default documentado não foi aplicado"

    declarada_falsa = _acao(primaria=False)
    assert declarada_falsa.primaria_efetiva is False


def test_acao_nao_primaria_nao_e_eleita_mesmo_casando_a_semantica():
    """O defeito que a leitura VIVA da conta real expôs em 01/09/2026.

    Medido na Portal Mundo Mais: a única meta biddable é DOWNLOAD/APP, e a única
    ação com essa semântica tem `primary_for_goal=false` DECLARADO. A primeira
    versão da eleição caía num `primarias or candidatas` — o default otimista —
    e elegia essa ação, saindo com a mensuração "resolvida".

    A doc não deixa margem: "If a conversion action's `primary_for_goal` bit is
    false, the conversion action is non-biddable for all campaigns **regardless**
    of their customer or campaign conversion goal."
    """
    alvo, causa = pm.eleger_acao_canonica(
        [_acao(categoria="DOWNLOAD", origem="APP",
               tipo="ANDROID_INSTALLS_ALL_OTHER_APPS", primaria=False)],
        [_meta("DOWNLOAD", "APP", True)])
    assert alvo is None, "elegeu uma ação que o lance não pode perseguir"
    assert "primária" in (causa or ""), causa
    assert "DOWNLOAD/APP" in (causa or ""), (
        "a causa não diz QUAL objetivo ficou sem ação, e sem isso ela não é "
        "acionável")


def test_uma_acao_hidden_nao_e_eleita():
    """`HIDDEN` existe no enum e não é `ENABLED`."""
    alvo, causa = pm.eleger_acao_canonica(
        [_acao(status="HIDDEN")], [_meta()])
    assert alvo is None
    assert "habilitada" in (causa or "")


# ═══════════════════════════════════════════════════════════════════════════
# 3. Reuso por SEMÂNTICA, nunca por nicho, campanha ou nome
# ═══════════════════════════════════════════════════════════════════════════


def test_a_eleicao_ignora_o_nome_e_casa_a_semantica():
    """Nome é rótulo humano: muda sem aviso e chega traduzido."""
    alvo, _ = pm.eleger_acao_canonica(
        [_acao(id="1", nome="Compra — Nicho Pet"),
         _acao(id="2", categoria="SIGNUP", nome="Compra — Nicho Moda")],
        [_meta("PURCHASE", "WEBSITE", True)])
    assert alvo is not None and alvo.id == "1", (
        "a eleição seguiu o nome em vez da semântica do evento")


def test_duas_acoes_da_mesma_semantica_desempatam_pelo_id_e_nao_pelo_nome():
    """⚠️ Ordenar por nome faria a eleição mudar quando alguém renomeasse."""
    alvo, _ = pm.eleger_acao_canonica(
        [_acao(id="900", nome="aaa"), _acao(id="100", nome="zzz")], [_meta()])
    assert alvo is not None and alvo.id == "100"


def test_chave_semantica_nao_carrega_nicho_nem_campanha():
    assert pm.chave_semantica("purchase", "website") == "PURCHASE/WEBSITE"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Nenhuma ConversionAction é criada — e uma nova nasce Secondary
# ═══════════════════════════════════════════════════════════════════════════


def test_o_modulo_nunca_cria_acao_de_conversao():
    """Não há caminho, aqui, que produza uma ação criada.

    ⚠️ Teste de AUSÊNCIA, e por isso ele confere o objeto e não a intenção: uma
    proposta marcada como criada é recusada com exceção, e não silenciosamente
    ignorada. Um `return None` seria absorvido pelo caminho normal de "não achei
    ação" e a tentativa passaria despercebida.
    """
    with pytest.raises(pm.CriacaoDeAcaoRecusada):
        pm.PropostaDeAcaoNova(categoria="PURCHASE", origem="WEBSITE",
                              nome_sugerido="x", tipo="WEBPAGE", criada=True)


def test_a_proposta_nasce_secondary():
    p = pm.propor_acao_nova("PURCHASE", "WEBSITE", nome_sugerido="Compra")
    assert p.primary_for_goal is False
    assert p.criada is False
    assert p.aprovacao_explicita is None


def test_promover_a_primaria_exige_aprovacao_nomeada():
    p = pm.propor_acao_nova("PURCHASE", "WEBSITE", nome_sugerido="Compra")
    with pytest.raises(ValueError):
        p.promover("   ")
    promovida = p.promover("dono da operação, 01/09/2026")
    assert promovida.primary_for_goal is True
    assert promovida.aprovacao_explicita == "dono da operação, 01/09/2026"
    assert promovida.criada is False, "promover não é criar"


def test_primaria_sem_aprovacao_e_recusada_na_construcao():
    with pytest.raises(ValueError):
        pm.PropostaDeAcaoNova(categoria="PURCHASE", origem="WEBSITE",
                              nome_sugerido="x", tipo="WEBPAGE",
                              primary_for_goal=True)


def test_uma_semantica_sem_acao_nao_vira_criacao_automatica():
    """A conta não tem a ação; o plano diz isso e NÃO propõe criar sozinho."""
    plano = pm.montar(
        customer_id="5478096539", login_customer_id="6016739364",
        meta_efetiva=_meta_efetiva(conta=(("SUBSCRIBE_PAID", "WEBSITE", True),)),
        acoes=(_acao(),), acoes_estado=pm.COM_DADOS)
    assert plano.acao_alvo is None
    assert plano.proposta_de_acao is None, (
        "o plano propôs uma ação sozinho — criar é ato separado, com aprovação")
    assert "SUBSCRIBE_PAID/WEBSITE" in (plano.acao_alvo_causa or "")


# ═══════════════════════════════════════════════════════════════════════════
# 5. Data Manager: dono + id numérico, NUNCA nome
# ═══════════════════════════════════════════════════════════════════════════


def test_destino_e_resolvido_por_dono_e_id_numerico():
    d = pm.resolver_destino(_acao(id="7466919994", owner="5478096539",
                                  tipo="WEBPAGE"))
    assert d.resolvido is True
    assert d.operating_account_id == "5478096539"
    assert d.product_destination_id == "7466919994"


def test_sem_dono_o_destino_e_recusado_com_causa():
    """> "the operating account must be the Google Ads account that owns the
    conversion action"

    ⚠️ Enviar para a conta errada não dá erro de permissão: dá SILÊNCIO, e a
    conversão não chega em lugar nenhum.
    """
    d = pm.resolver_destino(_acao(owner=None))
    assert d.resolvido is False
    assert "conta" in (d.causa or "").lower()
    assert d.product_destination_id is None


def test_tipo_fora_dos_tres_aceitos_e_recusado():
    d = pm.resolver_destino(_acao(tipo="ANDROID_INSTALLS_ALL_OTHER_APPS"))
    assert d.resolvido is False
    assert "ANDROID_INSTALLS_ALL_OTHER_APPS" in (d.causa or "")


def test_destino_resolvido_sem_id_numerico_e_impossivel_de_construir():
    """A guarda vale no objeto, e não só no banco."""
    with pytest.raises(ValueError):
        pm.DestinoDataManager(resolvido=True, operating_account_id="5478096539",
                              product_destination_id="Compra no site")


def test_owner_customer_de_recurso_invalido_vira_none_e_nao_string_vazia():
    """⚠️ `""` viajando como dono produziria um destino sintaticamente válido
    apontando para conta nenhuma."""
    assert pm.customer_id_do_recurso(None) is None
    assert pm.customer_id_do_recurso("") is None
    assert pm.customer_id_do_recurso("customers//conversionActions/1") is None
    assert pm.customer_id_do_recurso(
        "customers/5478096539/conversionActions/1") == "5478096539"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Os sete estados sobrevivem — null, zero, vazio, inelegível, não suportado,
#    falha
# ═══════════════════════════════════════════════════════════════════════════


def test_o_vocabulario_de_estados_nao_divergiu_do_engine():
    """Uma segunda grafia divergiria no primeiro estado novo.

    ⚠️ Este teste é a única coisa que impede as duas camadas de descrever a
    mesma leitura com palavras diferentes.
    """
    ec = pytest.importorskip("volc_ads.inteligencia_google.modelo").EstadoColeta
    do_engine = {e.value for e in ec}
    daqui = set(pm.ESTADOS_DE_LEITURA) - {pm.NAO_COLETADO}
    assert daqui == do_engine, (
        f"os vocabulários divergiram: só aqui={daqui - do_engine}, "
        f"só no engine={do_engine - daqui}")


def test_nao_coletado_e_vazio_confirmado_sao_estados_diferentes():
    nao_lido = pm.frescor_nao_lido()
    assert nao_lido.estado == pm.NAO_COLETADO
    assert nao_lido.conversoes_na_janela is None
    assert nao_lido.comprovado is False

    zero_medido = pm.Frescor(estado=pm.VAZIO_CONFIRMADO,
                             conversoes_na_janela=0.0)
    assert zero_medido.conversoes_na_janela == 0.0
    assert zero_medido.comprovado is False
    assert nao_lido.estado != zero_medido.estado


def test_leitura_sem_conclusao_nao_pode_carregar_contagem():
    """Um número ali seria precisão inventada sobre o que ninguém mediu."""
    with pytest.raises(ValueError):
        pm.Frescor(estado=pm.FALHOU, conversoes_na_janela=0.0, causa="caiu")


def test_leitura_sem_conclusao_exige_causa():
    with pytest.raises(ValueError):
        pm.Frescor(estado=pm.FALHOU)


def test_vazio_confirmado_com_data_de_ultima_conversao_e_contradicao():
    with pytest.raises(ValueError):
        pm.Frescor(estado=pm.VAZIO_CONFIRMADO, conversoes_na_janela=0.0,
                   ultima_conversao_em="2026-08-30")


def test_metas_que_mandam_nulo_nao_e_lista_vazia():
    """`None` = não se sabe qual nível manda. `[]` = manda e não há nenhuma."""
    sem_nivel = _meta_efetiva(nivel=pm.NIVEL_DESCONHECIDO)
    assert sem_nivel.metas_que_mandam is None
    assert sem_nivel.metas_biddable is None
    assert sem_nivel.resolvida is False

    com_nivel_sem_meta = _meta_efetiva(conta=())
    assert com_nivel_sem_meta.metas_que_mandam == ()
    assert com_nivel_sem_meta.metas_biddable == ()


def test_estado_de_leitura_invalido_e_recusado():
    with pytest.raises(ValueError):
        pm.montar(customer_id="1234567890", login_customer_id="1234567890",
                  acoes_estado="mais_ou_menos")


def test_leitura_sem_conclusao_trazendo_acoes_e_contradicao():
    with pytest.raises(ValueError):
        pm.montar(customer_id="1234567890", login_customer_id="1234567890",
                  acoes=(_acao(),), acoes_estado=pm.FALHOU)


# ═══════════════════════════════════════════════════════════════════════════
# 7. O nível governa — e UNKNOWN não vira CUSTOMER
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("nivel", [pm.NIVEL_NAO_ESPECIFICADO,
                                   pm.NIVEL_DESCONHECIDO, None])
def test_nivel_indefinido_nao_e_heranca_da_conta(nivel):
    """A tentação confortável: "o comum é herdar, então trate como CUSTOMER".

    ⚠️ Isso decidiria, aqui, uma coisa que ninguém leu. `UNSPECIFIED` e
    `UNKNOWN` existem no enum v25 e não afirmam herança nenhuma.
    """
    m = _meta_efetiva(nivel=nivel,
                      estado_nivel=pm.COM_DADOS if nivel else pm.FALHOU)
    assert m.nivel_decidido is False
    assert m.metas_que_mandam is None, (
        "as metas da conta foram devolvidas sem se saber que a conta manda")


def test_com_nivel_campaign_as_metas_da_conta_nao_decidem():
    """O caso medido na 24195821946, ao contrário: quando a campanha manda."""
    m = _meta_efetiva(nivel=pm.NIVEL_CAMPAIGN,
                      conta=(("PURCHASE", "WEBSITE", True),),
                      campanha=(("DOWNLOAD", "APP", True),),
                      estado_campanha=pm.COM_DADOS,
                      campaign_id="24195821946")
    biddable = m.metas_biddable
    assert biddable is not None
    assert [x.semantica for x in biddable] == ["DOWNLOAD/APP"]


def test_meta_customizada_tira_as_duas_listas_do_comando():
    """> "custom conversion goals do not respect primary_for_goal"

    Concluir pelas listas com um custom goal ativo daria uma resposta confiante
    e errada — que é pior que "não sei".
    """
    m = _meta_efetiva(custom="customers/1/customConversionGoals/9")
    assert m.usa_meta_customizada is True
    assert m.metas_que_mandam is None
    assert m.resolvida is False

    plano = pm.montar(customer_id="5478096539", login_customer_id="6016739364",
                      meta_efetiva=m, acoes=(_acao(),),
                      acoes_estado=pm.COM_DADOS)
    assert any("customizada" in b for b in plano.bloqueadores), plano.bloqueadores


def test_nivel_lido_com_dados_e_ausente_e_contradicao():
    with pytest.raises(ValueError):
        pm.MetaEfetiva(nivel=None, nivel_estado=pm.COM_DADOS,
                       metas_da_conta=(), metas_da_conta_estado=pm.COM_DADOS,
                       metas_da_campanha=(),
                       metas_da_campanha_estado=pm.INELEGIVEL)


# ═══════════════════════════════════════════════════════════════════════════
# 8. O plano: impressão, bloqueadores e o que ele NUNCA afirma
# ═══════════════════════════════════════════════════════════════════════════


def test_o_plano_sem_leitura_nenhuma_nao_afirma_nada():
    p = pm.montar(customer_id="5478096539", login_customer_id="6016739364")
    assert p.completo is False
    assert p.acao_alvo is None
    assert p.destino.resolvido is False
    assert p.frescor.estado == pm.NAO_COLETADO
    assert p.marcacao.estado == pm.NAO_COLETADO
    assert len(p.bloqueadores) >= 3, "não nomeou tudo o que falta"


def test_plano_sem_acao_e_sem_causa_e_impossivel():
    """Ignorância anônima é indistinguível de silêncio."""
    with pytest.raises(ValueError):
        pm.PlanoDeMensuracao(
            customer_id="5478096539", login_customer_id="6016739364",
            meta_efetiva=pm.meta_efetiva_nao_lida(),
            acao_alvo=None, acao_alvo_causa=None)


def test_a_impressao_ignora_o_frescor_e_muda_com_a_acao():
    """⚠️ Frescor muda de hora em hora sem o plano ter mudado.

    Incluí-lo faria cada leitura gravar um plano "novo": o histórico viraria
    ruído e a idempotência da gravação deixaria de existir.
    """
    base = _plano_completo()
    outro_frescor = pm.montar(
        customer_id="5478096539", login_customer_id="6016739364",
        meta_efetiva=_meta_efetiva(), acoes=(_acao(),),
        acoes_estado=pm.COM_DADOS,
        frescor=pm.Frescor(estado=pm.COM_DADOS,
                           ultima_conversao_em="2026-07-01",
                           dias_desde_a_ultima=62, conversoes_na_janela=1.0,
                           conversion_action_id="7466919994"),
        marcacao=_marcacao_boa())
    assert base.impressao() == outro_frescor.impressao()

    outra_acao = pm.montar(
        customer_id="5478096539", login_customer_id="6016739364",
        meta_efetiva=_meta_efetiva(), acoes=(_acao(id="999"),),
        acoes_estado=pm.COM_DADOS, frescor=_frescor_bom(),
        marcacao=_marcacao_boa())
    assert base.impressao() != outra_acao.impressao()


def test_a_impressao_separa_contas_diferentes():
    a = _plano_completo()
    b = pm.montar(customer_id="1234567890", login_customer_id="6016739364",
                  meta_efetiva=_meta_efetiva(), acoes=(_acao(),),
                  acoes_estado=pm.COM_DADOS, frescor=_frescor_bom(),
                  marcacao=_marcacao_boa())
    assert a.impressao() != b.impressao()


def test_fontes_de_sinal_saem_de_prova_e_nao_de_default():
    sem_nada = pm.montar(customer_id="5478096539",
                         login_customer_id="6016739364")
    assert pm.fontes_de_sinal_observadas(sem_nada) == ()

    fontes = pm.fontes_de_sinal_observadas(_plano_completo())
    assert "tag do Google no site" in fontes
    assert "conversão observada na janela consultada" in fontes


def test_marcacao_nao_lida_nao_vira_fonte_de_sinal():
    """⚠️ `auto_tagging=None` não é uma conta sem auto-tagging."""
    plano = pm.montar(
        customer_id="5478096539", login_customer_id="6016739364",
        meta_efetiva=_meta_efetiva(), acoes=(_acao(),),
        acoes_estado=pm.COM_DADOS,
        marcacao=pm.InventarioDeMarcacao(estado=pm.NAO_COLETADO,
                                         causa="ninguém inventariou"))
    assert not any("auto-tagging" in f
                   for f in pm.fontes_de_sinal_observadas(plano))


# ═══════════════════════════════════════════════════════════════════════════
# 9. `Prontidao` é de fato imutável — e não só contra rebind
# ═══════════════════════════════════════════════════════════════════════════


def test_o_veredito_nao_pode_ser_melhorado_depois_de_apresentado():
    """⚠️ `frozen=True` impede rebind e NÃO impede mutação do que o atributo
    aponta. Antes desta entrega, `r.activation_blockers.append(...)` alterava um
    veredito já apresentado — exatamente o que a docstring da classe diz que ela
    existe para impedir.
    """
    r = pr.avaliar(recibo_registrado=False, metas_da_conta=None)
    with pytest.raises(AttributeError):
        r.activation_blockers.append("apaguei o problema")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        r.signal_sources.append("inventei uma fonte")  # type: ignore[attr-defined]


def test_o_ramo_antigo_continua_intacto_quando_nao_ha_plano():
    """Quem não passa plano continua recebendo o veredito de antes, palavra por
    palavra — inclusive o PARCIAL e o bloqueio nomeado."""
    r = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "1"},
                                   "acoes": [{"id": "1", "primaria": True}]})
    assert r.conversion_goal_status == pr.PARCIAL
    assert any("meta de conversão efetiva não lida" in b
               for b in r.activation_blockers)
