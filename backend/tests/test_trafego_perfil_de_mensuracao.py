"""A identidade do que uma campanha MEDE — e por que ela não é a da intenção.

## O fato que abre este arquivo

Medido em 02/09/2026, na própria rota, com `_impressao_aprovavel`:

    chave base                : 83e7fe044dc356ce…
    mesma oferta, verba  50   : 928379f2dcf0c957…
    mesma oferta, verba  80   : e5189893fb8ec057…

`chave_intencao` é o sha256 do payload aprovado inteiro — conta, canal, verba,
lance, critérios, copy e destino. Ela é a identidade do LANÇAMENTO, e está certa
no que faz: é dela que saem a marca remota do canário e a chave de idempotência
do ledger. Trocar uma headline PRECISA invalidar a autorização.

Ela não pode ser a identidade da MEDIÇÃO, e erra nas duas direções ao mesmo
tempo:

  - **distingue demais** — a mesma oferta com duas verbas vira duas identidades,
    e as duas campanhas medem exatamente a mesma coisa. Quem procurasse "o
    perfil de mensuração desta oferta" acharia dois, e nenhum seria o dela;
  - **não distingue o que importa** — nada em `chave_intencao` fala de evento de
    negócio, funil, consentimento, regra de valor ou janela. Dois nichos que
    compartilham a estrutura do pedido e diferem só no que medem teriam
    identidades diferentes por acidente (a copy muda) e iguais por acidente
    (se a copy não mudasse).

Acidente não é identidade. Este arquivo prova o contrato que substitui o
acidente por uma decisão declarada.

## O que ele NÃO faz

Nada aqui toca rede, Supabase ou Google. Não há fixture de rede porque não há
uma linha de I/O em `perfil_de_mensuracao.py`: ele é domínio puro, e a prova
disso é que este módulo importa exatamente um símbolo do resto do sistema
(`plano_mensuracao`), para derivar o perfil de um plano já lido.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.trafego import perfil_de_mensuracao as pdm
from app.trafego import plano_mensuracao as pm


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures do domínio — sem rede, sem banco
# ═══════════════════════════════════════════════════════════════════════════


def _acao(id_numerico: str = "7498530235", *,
          owner: str | None = "1234567890",
          categoria: str = "PURCHASE", origem: str = "WEBSITE",
          primaria: bool | None = True) -> pm.AcaoDeConversao:
    return pm.AcaoDeConversao(
        id=id_numerico,
        resource_name=f"customers/{owner or '0'}/conversionActions/{id_numerico}",
        owner_customer_id=owner,
        nome="Compra — site",
        categoria=categoria, origem=origem, tipo="WEBPAGE", status="ENABLED",
        primaria=primaria,
    )


def _meta(*, biddable: bool = True, categoria: str = "PURCHASE",
          origem: str = "WEBSITE") -> pm.MetaEfetiva:
    return pm.MetaEfetiva(
        nivel=pm.NIVEL_CUSTOMER, nivel_estado=pm.COM_DADOS,
        metas_da_conta=(pm.Meta(categoria=categoria, origem=origem,
                                biddable=biddable),),
        metas_da_conta_estado=pm.COM_DADOS,
        metas_da_campanha=(), metas_da_campanha_estado=pm.INELEGIVEL,
    )


def _plano(*, acoes=None, meta=None, chave_intencao="intencao-a",
           customer_id="5478096539") -> pm.PlanoDeMensuracao:
    return pm.montar(
        customer_id=customer_id, login_customer_id="1234567890",
        meta_efetiva=meta or _meta(),
        acoes=acoes if acoes is not None else (_acao(),),
        acoes_estado=pm.COM_DADOS,
        chave_intencao=chave_intencao,
    )


def _perfil(**mudancas) -> pdm.PerfilDeMensuracao:
    base = dict(
        customer_id="5478096539", login_customer_id="1234567890",
        negocio="portal-mundo-mais", intencao="bpc-loas",
        funil=pdm.FUNIL_ACAO, evento="lead-qualificado",
        acao_owner_id="1234567890", acao_id="7498530235",
        semantica="PURCHASE/WEBSITE",
        fonte_do_sinal=pdm.FONTE_CONVERSAO_OBSERVADA,
        consentimento=pdm.CONSENTIMENTO_NAO_DECLARADO,
        regra_de_valor=pdm.RegraDeValor(modo=pdm.VALOR_SEM_VALOR),
        janela=pdm.janela_nao_declarada(),
    )
    base.update(mudancas)
    return pdm.PerfilDeMensuracao(**base)


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 1 — a chave da intenção NÃO serve de identidade de mensuração
# ═══════════════════════════════════════════════════════════════════════════


def test_a_mesma_oferta_com_verbas_diferentes_compartilha_o_perfil():
    """Duas campanhas, dois orçamentos, UMA medição.

    É o caso que `chave_intencao` erra por excesso. O que muda entre elas —
    quanto se gasta — não muda nada sobre o que se mede.
    """
    a = _perfil()
    b = _perfil()  # mesmo negócio, mesma oferta, mesmo evento
    assert a.chave == b.chave
    assert a == b


def test_nichos_diferentes_na_mesma_conta_nao_colidem():
    """BPC/LOAS e IPVA na MESMA conta, com a MESMA ação — chaves diferentes.

    ⚠️ Este é o caso que o sistema anterior não tinha como distinguir. As duas
    ofertas herdam a mesma meta da conta, elegem a mesma `ConversionAction` por
    semântica e apontam para o mesmo destino. Tudo o que o plano guardava era
    igual; a única coisa diferente era o que ninguém estava modelando.
    """
    bpc = _perfil(intencao="bpc-loas")
    ipva = _perfil(intencao="ipva")
    assert bpc.chave != ipva.chave


def test_eventos_de_negocio_diferentes_nao_colidem():
    """Mesma oferta, dois eventos — dois perfis.

    Um "lead qualificado" e uma "matrícula" da mesma oferta são medidas
    diferentes, com valor diferente e janela diferente. Colapsá-las faria a
    otimização perseguir a média de duas coisas que ninguém quis somar.
    """
    assert _perfil(evento="lead-qualificado").chave != _perfil(
        evento="matricula").chave


def test_funis_diferentes_nao_colidem():
    assert _perfil(funil=pdm.FUNIL_DESCOBERTA).chave != _perfil(
        funil=pdm.FUNIL_ACAO).chave


def test_contas_diferentes_nao_colidem():
    """A conta entra na identidade — sem ela, dois clientes se misturariam."""
    assert _perfil(customer_id="5478096539").chave != _perfil(
        customer_id="9999999999").chave


def test_donos_diferentes_da_mesma_acao_nao_colidem():
    """MCC com conversão centralizada: a conta DONA muda o destino real.

    Mandar o evento para a conta errada não é um detalhe de rótulo — é o
    destino inteiro. Duas linhas com o mesmo id numérico e donos diferentes
    descrevem duas medições diferentes.
    """
    assert _perfil(acao_owner_id="1234567890").chave != _perfil(
        acao_owner_id="7777777777").chave


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 2 — o que NÃO entra na identidade
# ═══════════════════════════════════════════════════════════════════════════


def test_a_fonte_do_sinal_nao_muda_a_identidade():
    """⚠️ OBSERVAÇÃO NÃO É IDENTIDADE, e confundi-las quebra as duas.

    O perfil é o que alguém DECIDIU medir: esta oferta, este evento, por esta
    ação, com esta regra de valor. Se a fonte entrasse na chave, o dia em que o
    sinal morresse produziria um perfil NOVO — e o histórico da campanha
    apontaria para um perfil que ninguém criou. Pior: a linha antiga continuaria
    existindo, e as duas descreveriam a mesma medição com identidades opostas.

    É a mesma regra que `PlanoDeMensuracao.impressao` aplica ao frescor, um
    degrau acima: lá o frescor fica fora porque muda de hora em hora; aqui a
    fonte fica fora porque ela descreve o mundo, não a decisão.
    """
    observada = _perfil(fonte_do_sinal=pdm.FONTE_CONVERSAO_OBSERVADA)
    morta = _perfil(fonte_do_sinal=pdm.FONTE_NAO_COMPROVADA)
    assert observada.chave == morta.chave
    # ...e mesmo assim as duas decidem coisas OPOSTAS sobre o lance.
    assert observada.aplicavel_a_smart_bidding is True
    assert morta.aplicavel_a_smart_bidding is False


def test_o_consentimento_nao_muda_a_identidade():
    """A conta aceitar os termos depois não cria um segundo perfil."""
    a = _perfil(consentimento=pdm.CONSENTIMENTO_NAO_DECLARADO)
    b = _perfil(consentimento=pdm.CONSENTIMENTO_CONCEDIDO)
    assert a.chave == b.chave


def test_a_janela_declarada_muda_a_identidade():
    """Mudar a janela de atribuição muda o que se mede — logo, o perfil.

    Trinta dias de clique e noventa dias de clique contam conversões
    diferentes para o mesmo evento. Duas campanhas sob janelas diferentes não
    compartilham medição, e a chave precisa dizer isso.
    """
    trinta = _perfil(janela=pdm.JanelaDeAtribuicao(
        estado=pdm.JANELA_DECLARADA, dias_de_clique=30, modelo="LAST_CLICK"))
    noventa = _perfil(janela=pdm.JanelaDeAtribuicao(
        estado=pdm.JANELA_DECLARADA, dias_de_clique=90, modelo="LAST_CLICK"))
    assert trinta.chave != noventa.chave


def test_janela_nao_declarada_nao_inventa_numero():
    """⚠️ Nenhum default de 30 dias. Ausência é ausência, e ela tem causa."""
    j = pdm.janela_nao_declarada()
    assert j.estado == pdm.JANELA_NAO_DECLARADA
    assert j.dias_de_clique is None
    assert j.modelo is None
    assert j.causa


def test_janela_nao_declarada_com_numero_e_recusada():
    with pytest.raises(ValueError, match="declarada"):
        pdm.JanelaDeAtribuicao(estado=pdm.JANELA_NAO_DECLARADA,
                               dias_de_clique=30)


def test_o_frescor_nao_entra_na_identidade():
    """O perfil não tem campo de frescor, e isso é estrutural.

    ⚠️ Frescor muda de hora em hora sem a medição ter mudado. Se ele entrasse,
    cada leitura produziria um perfil "novo" e a identidade deixaria de
    identificar. É o mesmo raciocínio que `PlanoDeMensuracao.impressao` já
    aplica, e ele precisa valer aqui também.
    """
    campos = set(pdm.PerfilDeMensuracao.__dataclass_fields__)
    assert "frescor" not in campos
    assert "frescor_dias" not in campos
    assert "ultima_conversao_em" not in campos


def test_o_nome_humano_da_acao_nao_entra_na_identidade():
    """⚠️ NUNCA por nome. Renomear a ação no painel não muda o que ela mede.

    E o inverso é pior: duas ações com o mesmo nome em contas diferentes
    viariam a mesma coisa. O contrato é dono + id numérico, e nada mais.
    """
    campos = set(pdm.PerfilDeMensuracao.__dataclass_fields__)
    assert "acao_nome" not in campos
    assert "nome_da_acao" not in campos


def test_derivar_de_plano_nao_aceita_ser_ancorado_em_nome():
    """A derivação lê `acao_alvo.id` e `owner_customer_id`, nunca `nome`."""
    plano = _plano(acoes=(_acao("7498530235"),))
    perfil = pdm.derivar_de_plano(
        plano, negocio="portal-mundo-mais", intencao="bpc-loas",
        funil=pdm.FUNIL_ACAO, evento="lead-qualificado")
    assert perfil.acao_id == "7498530235"
    assert perfil.acao_owner_id == "1234567890"
    # O nome existe no plano e NÃO viajou para o perfil.
    assert plano.acao_alvo is not None and plano.acao_alvo.nome
    assert "Compra" not in perfil.json_canonico()


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 3 — as guardas que impedem uma identidade que mente
# ═══════════════════════════════════════════════════════════════════════════


def test_acao_sem_id_numerico_e_recusada():
    with pytest.raises(ValueError, match="numérico"):
        _perfil(acao_id="minha-conversao")


def test_acao_com_id_e_sem_dono_e_recusada():
    """⚠️ O defeito que a v12_02 já fecha no schema, fechado também aqui.

    Um destino resolvido sem conta dona é um `Destination` sintaticamente
    válido apontando para conta nenhuma. A Data Manager exige que a operating
    account POSSUA a ação; sem o dono, a identidade descreve um envio que não
    tem para onde ir.
    """
    with pytest.raises(ValueError, match="dono"):
        _perfil(acao_owner_id=None)


def test_perfil_sem_evento_e_recusado():
    """Ignorância anônima é indistinguível de silêncio — aqui também."""
    with pytest.raises(ValueError, match="evento"):
        _perfil(evento="")


def test_funil_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="funil"):
        _perfil(funil="meio-do-caminho")


def test_consentimento_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="consentimento"):
        _perfil(consentimento="talvez")


def test_valor_fixo_sem_moeda_e_recusado():
    """Valor sem moeda não é dinheiro — é um número solto.

    A Data Manager exige `currencyCode` junto de `conversionValue`; mandar o
    número sem a moeda faz o Google adotar a da conta, e a conta pode não ser a
    que o operador tinha em mente.
    """
    with pytest.raises(ValueError, match="moeda"):
        pdm.RegraDeValor(modo=pdm.VALOR_FIXO, valor=Decimal("49.90"))


def test_valor_fixo_sem_numero_e_recusado():
    with pytest.raises(ValueError, match="valor"):
        pdm.RegraDeValor(modo=pdm.VALOR_FIXO, moeda="BRL")


def test_sem_valor_com_numero_e_recusado():
    """Declarar "sem valor" e mandar um valor junto afirma as duas coisas."""
    with pytest.raises(ValueError, match="sem_valor"):
        pdm.RegraDeValor(modo=pdm.VALOR_SEM_VALOR, valor=Decimal("10"),
                         moeda="BRL")


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 4 — aplicabilidade: nenhum campo isolado prova prontidão
# ═══════════════════════════════════════════════════════════════════════════


def test_perfil_sem_acao_nao_e_aplicavel_a_smart_bidding():
    """Sem ação eleita não há o que o lance persiga. Falha FECHADO."""
    p = _perfil(acao_id=None, acao_owner_id=None, semantica=None,
                fonte_do_sinal=pdm.FONTE_NAO_COMPROVADA)
    assert p.aplicavel_a_smart_bidding is False


def test_fonte_nao_comprovada_nao_e_aplicavel_a_smart_bidding():
    """⚠️ Caminho declarado não é sinal chegando.

    Auto-tagging ligado prova que a conta CONSEGUE transportar o click ID. Não
    prova que uma conversão chegou. `FONTE_CAMINHO_DECLARADO` existe para
    nomear exatamente essa diferença, e ele não abre o portão.
    """
    assert _perfil(fonte_do_sinal=pdm.FONTE_CAMINHO_DECLARADO
                   ).aplicavel_a_smart_bidding is False
    assert _perfil(fonte_do_sinal=pdm.FONTE_NAO_COMPROVADA
                   ).aplicavel_a_smart_bidding is False


def test_consentimento_negado_nao_e_aplicavel_a_nada():
    """Consentimento negado não é uma ressalva: é uma proibição."""
    p = _perfil(consentimento=pdm.CONSENTIMENTO_NEGADO)
    assert p.aplicavel_a_ativacao is False
    assert p.aplicavel_a_smart_bidding is False


def test_perfil_completo_e_aplicavel_aos_dois():
    """O ramo POSITIVO existe — sem ele os testes acima não provariam nada.

    ⚠️ Um portão que nunca abre passa com qualquer entrada. É o mesmo cuidado
    que `prontidao.avaliar` documenta: sem um ramo alcançável, "está bloqueado"
    seria infalsificável.
    """
    p = _perfil(fonte_do_sinal=pdm.FONTE_CONVERSAO_OBSERVADA,
                consentimento=pdm.CONSENTIMENTO_CONCEDIDO)
    assert p.aplicavel_a_ativacao is True
    assert p.aplicavel_a_smart_bidding is True


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 5 — travessia: json canônico e volta, sem perder decisão
# ═══════════════════════════════════════════════════════════════════════════


def test_ida_e_volta_preserva_a_chave():
    p = _perfil()
    assert pdm.de_json(p.json()).chave == p.chave


def test_de_json_recusa_reconstruir_um_perfil_que_mudaria_de_decisao():
    """⚠️ A chave viaja no JSON e é CONFERIDA na volta.

    Se a reconstrução produzisse outra chave, o perfil lido do banco seria um
    perfil diferente do gravado — e ninguém notaria, porque os dois pareceriam
    perfis válidos.
    """
    dados = _perfil().json()
    dados["evento"] = "outra-coisa"
    with pytest.raises(ValueError, match="chave"):
        pdm.de_json(dados)


def test_o_json_canonico_e_estavel_entre_ordens_de_campo():
    """A chave não pode depender da ordem em que o dicionário foi montado."""
    a = _perfil()
    b = pdm.de_json(dict(reversed(list(a.json().items()))))
    assert a.chave == b.chave


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 6 — derivação a partir do plano lido
# ═══════════════════════════════════════════════════════════════════════════


def test_derivar_sem_acao_eleita_produz_perfil_sem_acao_e_com_causa():
    """A leitura que não elegeu ação produz perfil INCOMPLETO, não ausente.

    ⚠️ `None` aqui seria indistinguível de "ninguém tentou". O perfil existe,
    diz o que se decidiu (negócio, oferta, funil, evento) e diz que a ação
    ficou em aberto — que é exatamente o estado real.
    """
    plano = _plano(meta=_meta(biddable=False))
    assert plano.acao_alvo is None
    perfil = pdm.derivar_de_plano(
        plano, negocio="portal-mundo-mais", intencao="bpc-loas",
        funil=pdm.FUNIL_ACAO, evento="lead-qualificado")
    assert perfil.acao_id is None
    assert perfil.acao_owner_id is None
    assert perfil.aplicavel_a_smart_bidding is False
    assert perfil.chave  # continua tendo identidade


def test_derivar_preserva_a_semantica_e_nao_o_nome():
    plano = _plano(acoes=(_acao(categoria="PURCHASE", origem="WEBSITE"),))
    perfil = pdm.derivar_de_plano(
        plano, negocio="n", intencao="i", funil=pdm.FUNIL_ACAO, evento="e")
    assert perfil.semantica == "PURCHASE/WEBSITE"


def test_derivar_le_a_fonte_do_sinal_do_frescor_e_nao_da_capacidade():
    """⚠️ A fonte sai do que foi OBSERVADO, nunca do que está configurado.

    Um plano com `auto_tagging=True` e ZERO conversão medida tem CAMINHO, não
    fonte. Este teste é o que impede a capacidade de virar prova na travessia
    para o perfil.
    """
    marcacao = pm.InventarioDeMarcacao(
        estado=pm.COM_DADOS, auto_tagging=True,
        conversion_tracking_id="123", conversion_tracking_owner_id="1234567890",
        conversion_tracking_status="CONVERSION_TRACKING_MANAGED_BY_SELF",
    )
    plano = pm.montar(
        customer_id="5478096539", login_customer_id="1234567890",
        meta_efetiva=_meta(), acoes=(_acao(),), acoes_estado=pm.COM_DADOS,
        marcacao=marcacao,
        frescor=pm.Frescor(estado=pm.VAZIO_CONFIRMADO, conversoes_na_janela=0),
    )
    perfil = pdm.derivar_de_plano(
        plano, negocio="n", intencao="i", funil=pdm.FUNIL_ACAO, evento="e")
    assert perfil.fonte_do_sinal == pdm.FONTE_CAMINHO_DECLARADO
    assert perfil.aplicavel_a_smart_bidding is False
