"""O perfil viaja com o plano — e a identidade do plano tem de saber disso.

## A armadilha que este arquivo fecha antes de ela existir

A tentação óbvia era guardar o perfil de mensuração só em `payload`, que é onde
`vinculo` já mora. Ela produz um defeito silencioso e conhecido desta casa.

A função Postgres `volc_registrar_plano_de_mensuracao` é **idempotente pela
impressão**: mesma impressão devolve a MESMA linha e descarta a segunda escrita.
`PlanoDeMensuracao.impressao()` não conhece o perfil. Logo, duas campanhas da
mesma conta, com a mesma `chave_intencao`, a mesma meta efetiva e a mesma ação
eleita — e perfis de mensuração DIFERENTES — produziriam a mesma impressão, e a
segunda seria engolida devolvendo o `plano_id` da primeira. O banco guardaria
um perfil e o sistema acreditaria ter guardado dois.

É literalmente o mesmo defeito que a própria docstring de `impressao()` já
descreve duas vezes: quando o frescor ficou de fora, dois vereditos opostos
colapsaram numa linha; quando os estados de leitura ficaram de fora, `falhou` e
`vazio_confirmado` colapsaram numa linha.

Então o perfil ENTRA na impressão. E entra de um jeito que não pode reescrever
o passado: quando não há perfil, o corpo do hash tem de ser **byte a byte** o
que era antes — senão toda linha já gravada deixa de ser reencontrável e a
idempotência de todo plano existente quebra de uma vez.
"""
from __future__ import annotations

import pytest

from app.trafego import perfil_de_mensuracao as pdm
from app.trafego import persistencia as pers
from app.trafego import plano_mensuracao as pm


def _acao(id_numerico: str = "7498530235", owner: str = "1234567890"):
    return pm.AcaoDeConversao(
        id=id_numerico,
        resource_name=f"customers/{owner}/conversionActions/{id_numerico}",
        owner_customer_id=owner, nome="Compra — site",
        categoria="PURCHASE", origem="WEBSITE", tipo="WEBPAGE",
        status="ENABLED", primaria=True,
    )


def _meta():
    return pm.MetaEfetiva(
        nivel=pm.NIVEL_CUSTOMER, nivel_estado=pm.COM_DADOS,
        metas_da_conta=(pm.Meta(categoria="PURCHASE", origem="WEBSITE",
                                biddable=True),),
        metas_da_conta_estado=pm.COM_DADOS,
        metas_da_campanha=(), metas_da_campanha_estado=pm.INELEGIVEL,
    )


def _plano(*, perfil=None, chave_intencao="intencao-a", campaign_id=None):
    return pm.montar(
        customer_id="5478096539", login_customer_id="1234567890",
        meta_efetiva=_meta(), acoes=(_acao(),), acoes_estado=pm.COM_DADOS,
        chave_intencao=chave_intencao, campaign_id=campaign_id,
        perfil=perfil,
    )


def _perfil(**mud):
    base = dict(negocio="portal-mundo-mais", intencao="bpc-loas",
                funil=pdm.FUNIL_ACAO, evento="lead-qualificado")
    base.update(mud)
    return pdm.derivar_de_plano(_plano(), **base)


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 1 — a compatibilidade que não pode quebrar
# ═══════════════════════════════════════════════════════════════════════════


def test_plano_sem_perfil_mantem_a_impressao_anterior_byte_a_byte():
    """⚠️ A prova mais importante deste arquivo, e a mais fácil de esquecer.

    A tabela é append-only e idempotente por impressão. Se o corpo do hash
    mudasse para planos SEM perfil, toda linha já gravada deixaria de ser
    reencontrável: `registrar` não acharia a impressão existente, gravaria uma
    segunda linha para a mesma leitura, e a idempotência — a coisa que torna
    seguro chamar isto de dentro de um retry — deixaria de existir para o
    acervo inteiro de uma vez.

    O valor abaixo foi medido contra o código da base `26a58c4`, ANTES de o
    campo `perfil` existir. Ele é uma constante de regressão, não um espelho do
    código: recalculá-lo aqui provaria apenas que a função é determinística.
    """
    impressao_antes_do_perfil = (
        "b76c89dc1b7275a2a56b371385a8dc8b7eac37d27d527d770521653a35a6a263")
    corpo = _plano().impressao()
    assert corpo == impressao_antes_do_perfil, (
        "a impressão de um plano SEM perfil mudou; toda linha gravada antes "
        "desta entrega deixaria de ser reencontrável")


def test_perfil_ausente_nao_aparece_no_corpo_da_impressao():
    """A ausência é ausência de CHAVE, e não uma chave com `null`.

    ⚠️ `{"perfil": null}` e `{}` produzem hashes diferentes. Foi assim que
    `assets_display` mudou a impressão de todo plano Search em 01/09/2026 sem
    uma linha do pedido ter mudado — o campo entrou como `null` e o simples ato
    de declará-lo trocou a identidade.
    """
    assert "perfil" not in _plano().corpo_da_impressao()
    assert "perfil" in _plano(perfil=_perfil()).corpo_da_impressao()


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 2 — perfis diferentes não colidem na porta de escrita
# ═══════════════════════════════════════════════════════════════════════════


def test_perfis_diferentes_produzem_impressoes_diferentes():
    """O defeito que este arquivo existe para impedir.

    Mesma conta, mesma intenção, mesma meta, mesma ação — e dois nichos. Sem o
    perfil na impressão, a RPC devolveria o `plano_id` do primeiro e a segunda
    escrita sumiria em silêncio.
    """
    bpc = _plano(perfil=_perfil(intencao="bpc-loas"))
    ipva = _plano(perfil=_perfil(intencao="ipva"))
    assert bpc.impressao() != ipva.impressao()


def test_o_mesmo_perfil_continua_idempotente():
    """A recíproca: a mesma leitura com o mesmo perfil é a MESMA linha."""
    assert _plano(perfil=_perfil()).impressao() == _plano(
        perfil=_perfil()).impressao()


def test_a_observacao_do_perfil_nao_muda_a_impressao_do_plano():
    """⚠️ A regra do perfil atravessa para cá inteira.

    `fonte_do_sinal` é observação, e o plano já carrega o frescor separado. Se
    a observação do perfil entrasse aqui, o plano ganharia uma segunda via de
    invalidação para o mesmo fato — e as duas poderiam discordar.
    """
    observada = _perfil()
    morta = pdm.PerfilDeMensuracao(
        **{**{k: getattr(observada, k)
              for k in pdm.PerfilDeMensuracao.__dataclass_fields__},
           "fonte_do_sinal": pdm.FONTE_NAO_COMPROVADA})
    assert _plano(perfil=observada).impressao() == _plano(
        perfil=morta).impressao()


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 3 — travessia: grava, relê, e continua sendo o mesmo perfil
# ═══════════════════════════════════════════════════════════════════════════


def test_o_perfil_sobrevive_ao_para_json_e_ao_do_json():
    original = _plano(perfil=_perfil())
    reconstruido = pm.do_json(original.para_json())
    assert reconstruido.perfil is not None
    assert reconstruido.perfil.chave == original.perfil.chave
    assert reconstruido.impressao() == original.impressao()


def test_do_json_sem_perfil_devolve_plano_sem_perfil():
    """Linha antiga, gravada antes desta entrega, continua reconstruível."""
    dados = _plano().para_json()
    assert dados["perfil"] is None
    assert pm.do_json(dados).perfil is None


def test_o_perfil_vai_para_o_payload_da_rpc():
    """⚠️ `payload`, e não coluna nova. A v12_02 já está aplicada em produção.

    Uma coluna exigiria migration nova num schema que a casa acabou de aplicar,
    com backup e onze contraprovas. `payload` é o campo que a própria v12_02
    declara para isso — "as colunas são o que se consulta, e o payload é o que
    se audita" — e é onde `vinculo` já mora.
    """
    plano = _plano(perfil=_perfil())
    doc = pers.documento_de_plano_de_mensuracao(
        plano.para_json(), lido_em="2026-09-02T12:00:00Z")
    assert doc["payload"]["perfil"]["chave"] == plano.perfil.chave
    assert doc["impressao"] == plano.impressao()


def test_o_vinculo_ao_nascimento_preserva_o_perfil():
    """A campanha nasce e o perfil continua sendo o mesmo perfil.

    ⚠️ A impressão MUDA (o `campaign_id` entra nela) e o perfil NÃO muda: é a
    mesma medição, agora com endereço. Se o vínculo recalculasse o perfil, a
    linha pós-nascimento descreveria uma decisão que ninguém tomou.
    """
    antes = _plano(perfil=_perfil())
    depois = pm.vincular_ao_nascimento(antes, campaign_id="24183717006")
    assert depois.perfil is not None
    assert depois.perfil.chave == antes.perfil.chave
    assert depois.impressao() != antes.impressao()


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 4 — o perfil não pode contradizer o plano que o carrega
# ═══════════════════════════════════════════════════════════════════════════


def test_perfil_de_outra_conta_e_recusado():
    """⚠️ Um perfil da conta B num plano da conta A endereça o lugar errado."""
    outro = pdm.derivar_de_plano(
        pm.montar(customer_id="9999999999", login_customer_id="1234567890",
                  meta_efetiva=_meta(), acoes=(_acao(),),
                  acoes_estado=pm.COM_DADOS),
        negocio="n", intencao="i", funil=pdm.FUNIL_ACAO, evento="e")
    with pytest.raises(ValueError, match="conta"):
        _plano(perfil=outro)


def test_perfil_que_aponta_para_outra_acao_e_recusado():
    """O perfil diz "medido por #X" e o plano elegeu #Y. Uma das duas mente."""
    outra = pdm.derivar_de_plano(
        pm.montar(customer_id="5478096539", login_customer_id="1234567890",
                  meta_efetiva=_meta(), acoes=(_acao("111222333"),),
                  acoes_estado=pm.COM_DADOS),
        negocio="n", intencao="i", funil=pdm.FUNIL_ACAO, evento="e")
    assert outra.acao_id == "111222333"
    with pytest.raises(ValueError, match="ação"):
        _plano(perfil=outra)


def test_perfil_sem_acao_convive_com_plano_sem_acao():
    """O caso honesto: nenhuma ação eleita nos dois lados, e nada mente."""
    sem_acao = pm.montar(
        customer_id="5478096539", login_customer_id="1234567890",
        meta_efetiva=pm.meta_efetiva_nao_lida(), acoes=(),
        acoes_estado=pm.NAO_COLETADO)
    perfil = pdm.derivar_de_plano(sem_acao, negocio="n", intencao="i",
                                  funil=pdm.FUNIL_ACAO, evento="e")
    assert perfil.acao_id is None
    montado = pm.montar(
        customer_id="5478096539", login_customer_id="1234567890",
        meta_efetiva=pm.meta_efetiva_nao_lida(), acoes=(),
        acoes_estado=pm.NAO_COLETADO, perfil=perfil)
    assert montado.perfil is perfil
