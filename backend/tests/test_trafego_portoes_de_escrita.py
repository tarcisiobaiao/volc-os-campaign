"""Os SETE portões, e o único deles que fecha o caminho de ESCRITA.

## Os dois fatos que abrem este arquivo

Ambos medidos em 02/09/2026, na worktree, contra o código da base
`26a58c4` — não deduzidos.

**1. `/subir` cria em Smart Bidding com a medição reprovada.**

    PROVAR diz: smart_bidding_eligible = False
    PROVAR diz: bloqueadores = 5
    ATOS: ['ler_plano','abrir','despachar','registrar_plano','MUTATE',…]
    >>> MUTATE aconteceu? True

`/provar` calcula os portões e os projeta na resposta. `/subir` **nunca chama
`prontidao.avaliar`**: ele lê o plano, grava o plano e chama o Google. O
`estrategia_lance` do corpo atravessa `Escolha` (`trafego.py:2989`) até o
executor sem passar por portão nenhum. O risco fica contido só porque a
campanha nasce PAUSED por literal e não existe função de ativação no engine —
duas defesas que ninguém escolheu como portão de lance, e que a primeira pessoa
a despausar pelo painel do Google desfaz.

**2. `data_manager_status` sai `PRONTO` sem destino resolvido.**

    destino resolvido? False
    data_manager_status = PRONTO

`data_manager_operante` é um booleano que quem chama afirma. Com ele `True` e
um plano sem `acao_alvo` — logo sem `destino.operating_account_id` e sem
`destino.product_destination_id` — o portão abre. Pronto para mandar evento
para lugar nenhum.

**3. `activation_ready` não existe.** Havia `activation_blockers`, que é a
lista de razões, e nenhum campo que respondesse a pergunta. Uma lista vazia
lida como permissão é exatamente o default otimista que esta casa recusa.

## O que este arquivo NÃO faz

Nenhuma linha toca rede. A fixture `_rede_bloqueada` é `pytest.fail` dentro de
`socket.connect`, no mesmo desenho de `test_trafego_plano_persistido.py`.
"""
from __future__ import annotations

import asyncio
import socket

import pytest
from fastapi import HTTPException

from app.trafego import canario
from app.trafego import perfil_de_mensuracao as pdm
from app.trafego import plano_mensuracao as pm
from app.trafego import prontidao as pr
from app.routers import trafego

import test_trafego_plano_persistido as base
from test_trafego_canario import _instalar_portas_hermeticas, _payload_da_rota


@pytest.fixture(autouse=True)
def _rede_bloqueada(monkeypatch: pytest.MonkeyPatch):
    def recusar_rede(_socket, _address):
        pytest.fail("teste dos portões tentou abrir conexão de rede")

    monkeypatch.setattr(socket.socket, "connect", recusar_rede)
    monkeypatch.setattr(socket.socket, "connect_ex", recusar_rede)


@pytest.fixture(autouse=True)
def _leituras_vivas_desligadas(monkeypatch: pytest.MonkeyPatch):
    """As duas portas que `/provar` abre para o Google, fechadas.

    ⚠️ `_subir` roda `/provar` de verdade para obter o selo, e `/provar` lê o
    plano (cinco GAQL) e as metas da conta. `contas.meta_de_conversao` desce até
    `volc_ads.gads.client.cliente`, que é `lru_cache` e REFRESCA o token no
    `load_from_storage` — ou seja, fala com o Google antes de qualquer consulta.
    Sem estes dois dublês, `_rede_bloqueada` derruba o teste pelo motivo errado.

    Quem precisa de um plano de verdade instala o seu em `base._montar`, que
    sobrescreve o primeiro depois que `/provar` já rodou.
    """
    from app.trafego import contas as ct

    async def sem_plano(*_a, **_k):
        return None

    def sem_metas(*_a, **_k):
        raise RuntimeError("leitura de metas desligada neste arquivo de teste")

    monkeypatch.setattr(trafego, "_plano_de_mensuracao", sem_plano)
    monkeypatch.setattr(ct, "meta_de_conversao", sem_metas)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures do domínio
# ═══════════════════════════════════════════════════════════════════════════


def _acao(id_numerico: str = "7498530235", *, owner: str = "1234567890",
          categoria: str = "PURCHASE", origem: str = "WEBSITE"):
    return pm.AcaoDeConversao(
        id=id_numerico,
        resource_name=f"customers/{owner}/conversionActions/{id_numerico}",
        owner_customer_id=owner, nome="Compra — site",
        categoria=categoria, origem=origem, tipo="WEBPAGE", status="ENABLED",
        primaria=True,
    )


def _meta(*, biddable: bool = True):
    return pm.MetaEfetiva(
        nivel=pm.NIVEL_CUSTOMER, nivel_estado=pm.COM_DADOS,
        metas_da_conta=(pm.Meta(categoria="PURCHASE", origem="WEBSITE",
                                biddable=biddable),),
        metas_da_conta_estado=pm.COM_DADOS,
        metas_da_campanha=(), metas_da_campanha_estado=pm.INELEGIVEL,
    )


def _frescor_vivo():
    return pm.Frescor(estado=pm.COM_DADOS, ultima_conversao_em="2026-08-31",
                      dias_desde_a_ultima=2, conversoes_na_janela=14.0,
                      conversion_action_id="7498530235")


def _frescor_morto():
    return pm.Frescor(estado=pm.VAZIO_CONFIRMADO, conversoes_na_janela=0,
                      conversion_action_id="7498530235")


def _marcacao():
    return pm.InventarioDeMarcacao(
        estado=pm.COM_DADOS, auto_tagging=True,
        conversion_tracking_id="123", conversion_tracking_owner_id="1234567890",
        conversion_tracking_status="CONVERSION_TRACKING_MANAGED_BY_SELF",
        aceitou_termos_de_dados=True, fuso="America/Sao_Paulo",
    )


def _plano(*, medindo: bool = True, com_acao: bool = True):
    return pm.montar(
        customer_id=canario.CONTA, login_customer_id="1234567890",
        meta_efetiva=_meta(biddable=com_acao),
        acoes=(_acao(),) if com_acao else (),
        acoes_estado=pm.COM_DADOS,
        frescor=_frescor_vivo() if medindo else _frescor_morto(),
        marcacao=_marcacao(),
    )


def _pronta(**mudancas):
    """A prontidão que abre TUDO — o ramo positivo, sem o qual nada prova nada."""
    argumentos = dict(
        plano_valido=True,
        recibo_registrado=True,
        metas_da_conta=None,
        plano_de_mensuracao=_plano(),
        plano_persistido=True,
        coleta_pos_criacao_provada=True,
        data_manager_operante=False,
        ativacao_autorizada_por_politica=True,
    )
    argumentos.update(mudancas)
    return pr.avaliar(**argumentos)


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 1 — os sete portões existem, e são sete
# ═══════════════════════════════════════════════════════════════════════════


PORTOES = (
    "creation_plan_ready", "campaign_birth", "measurement_ready",
    "observability_ready", "activation_ready", "smart_bidding_ready",
    "data_manager_ready",
)


def test_os_sete_portoes_estao_na_resposta():
    """Cada pergunta tem campo próprio. "Pronto" sem sujeito é palavra vazia."""
    j = pr.avaliar(recibo_registrado=False, metas_da_conta=None).para_json()
    for portao in PORTOES:
        assert portao in j, f"portão ausente: {portao}"


def test_todo_portao_e_um_dos_cinco_estados():
    j = _pronta().para_json()
    for portao in PORTOES:
        assert j[portao] in pr.ESTADOS, (portao, j[portao])


def test_o_default_de_todo_portao_e_indeterminado_e_nunca_pronto():
    """⚠️ Não saber não é estar pronto. Sem entrada, nenhum portão abre."""
    j = pr.avaliar(recibo_registrado=False, metas_da_conta=None).para_json()
    for portao in PORTOES:
        assert j[portao] != pr.PRONTO, portao


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 2 — Data Manager PRONTO sem destino (defeito 2, reproduzido)
# ═══════════════════════════════════════════════════════════════════════════


def test_data_manager_nao_fica_pronto_sem_destino_resolvido():
    """O defeito medido: `operante=True` + destino não resolvido = PRONTO.

    ⚠️ "Operante" descreve a NOSSA fila; "destino resolvido" descreve para ONDE
    o evento vai. Sem o segundo, pronto significa pronto para mandar para lugar
    nenhum — e a Data Manager resolve destino por conta dona + id numérico, de
    modo que um destino ausente não é um detalhe de configuração, é o endereço.
    """
    sem_acao = _plano(com_acao=False)
    assert sem_acao.destino.resolvido is False
    r = pr.avaliar(recibo_registrado=True, metas_da_conta=None,
                   plano_de_mensuracao=sem_acao, data_manager_operante=True)
    assert r.data_manager_ready != pr.PRONTO
    assert any("destino" in b.lower() for b in r.activation_blockers)


def test_data_manager_pronto_exige_os_dois_e_o_ramo_existe():
    com_acao = _plano()
    assert com_acao.destino.resolvido is True
    assert pr.avaliar(recibo_registrado=True, metas_da_conta=None,
                      plano_de_mensuracao=com_acao,
                      data_manager_operante=True).data_manager_ready == pr.PRONTO
    assert pr.avaliar(recibo_registrado=True, metas_da_conta=None,
                      plano_de_mensuracao=com_acao,
                      data_manager_operante=False).data_manager_ready != pr.PRONTO


def test_data_manager_nao_pronto_nao_bloqueia_conta_que_mede_por_tag():
    """⚠️ Sinal ≠ Data Manager, e a doutrina não muda com o portão novo.

    Uma conta que converte por tag do Google mede perfeitamente e nunca vai ter
    ingestão offline operante. Exigi-la declararia despreparo onde não há.
    """
    r = _pronta(data_manager_operante=False)
    assert r.data_manager_ready != pr.PRONTO
    assert r.measurement_ready == pr.PRONTO
    assert r.activation_ready == pr.PRONTO


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 3 — ativação: portão próprio, e fecha sem plano persistido
# ═══════════════════════════════════════════════════════════════════════════


def test_ativacao_nao_fica_pronta_sem_plano_persistido():
    """⚠️ Plano CALCULADO não é plano GRAVADO.

    `/provar` calcula e mostra; nada sobrevive à requisição. Ativar com base num
    plano que não existe no banco é ativar com base numa tela — e semanas
    depois ninguém consegue dizer o que o operador viu quando decidiu.
    """
    assert _pronta(plano_persistido=False).activation_ready != pr.PRONTO
    assert any("persistid" in b.lower()
               for b in _pronta(plano_persistido=False).activation_blockers)


def test_ativacao_nao_fica_pronta_sem_observabilidade():
    assert _pronta(coleta_pos_criacao_provada=False).activation_ready != pr.PRONTO


def test_ativacao_nao_fica_pronta_sem_medicao():
    assert _pronta(plano_de_mensuracao=_plano(medindo=False)
                   ).activation_ready != pr.PRONTO


def test_ativacao_nao_fica_pronta_sem_autorizacao_de_politica():
    """⚠️ Falha FECHADO no default. Medir bem não autoriza despausar.

    A autorização em vigor cobre criar pausada e nada além; ativar é outro ato.
    O default de `ativacao_autorizada_por_politica` é `False` justamente para
    que uma chamada que esqueça o parâmetro não produza permissão.
    """
    assert _pronta(ativacao_autorizada_por_politica=False
                   ).activation_ready != pr.PRONTO


def test_ativacao_pronta_existe_e_e_alcancavel():
    """O ramo POSITIVO. Sem ele, "está bloqueado" passaria com qualquer entrada."""
    assert _pronta().activation_ready == pr.PRONTO


def test_ativacao_pronta_com_bloqueador_material_e_impossivel_por_construcao():
    """⚠️ Não há como ESCREVER a contradição — o estado é derivado.

    "Ativação PRONTA" ao lado de um bloqueador material afirmaria duas coisas
    opostas sobre o mesmo mundo, e a lista de bloqueadores é justamente o que a
    tela mostra embaixo do estado. Uma guarda que DETECTA isso é mais fraca que
    um tipo em que a contradição não é expressável: aqui `activation_ready` é
    propriedade, e nenhum construtor a recebe.
    """
    assert "activation_ready" not in pr.Prontidao.__dataclass_fields__
    assert "smart_bidding_ready" not in pr.Prontidao.__dataclass_fields__
    r = pr.Prontidao(
        # ⚠️ `campaign_birth` entrou no portão em 02/09/2026 (revisão
        # adversarial): ativar é despausar algo que existe. Sem ele aqui, o
        # veredito sairia INDETERMINADO por FALTA de nascimento, e o teste
        # provaria a coisa errada — ele existe para provar que o bloqueador
        # MATERIAL fecha a porta, e não que a campanha não nasceu.
        campaign_birth=pr.PRONTO,
        measurement_readiness=pr.PRONTO, observability_status=pr.PRONTO,
        plano_persistido=True, ativacao_autorizada_por_politica=True,
        activation_blockers=("nenhuma conversão observada",),
        activation_blockers_materiais=("nenhuma conversão observada",))
    assert r.activation_ready == pr.NAO_PRONTO


def test_o_estado_e_o_booleano_do_smart_bidding_nao_podem_divergir():
    """A mesma proteção, do outro lado: derivado do bool, nunca escrito."""
    assert pr.Prontidao(smart_bidding_eligible=True,
                        measurement_readiness=pr.PRONTO,
                        observability_status=pr.PRONTO
                        ).smart_bidding_ready == pr.PRONTO
    assert pr.Prontidao(smart_bidding_eligible=False,
                        measurement_readiness=pr.NAO_PRONTO,
                        observability_status=pr.PRONTO
                        ).smart_bidding_ready == pr.NAO_PRONTO


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 4 — Smart Bidding: portão independente do de ativação
# ═══════════════════════════════════════════════════════════════════════════


def test_smart_bidding_e_ativacao_sao_portoes_independentes():
    """⚠️ Um não implica o outro, nas DUAS direções.

    Sem política, ativação fecha e a medição continua provada — logo Smart
    Bidding continua elegível como VEREDITO sobre o lance. Sem sinal, Smart
    Bidding fecha mesmo com política liberada.
    """
    sem_politica = _pronta(ativacao_autorizada_por_politica=False)
    assert sem_politica.activation_ready != pr.PRONTO
    assert sem_politica.smart_bidding_ready == pr.PRONTO

    sem_sinal = _pronta(plano_de_mensuracao=_plano(medindo=False))
    assert sem_sinal.smart_bidding_ready != pr.PRONTO


def test_smart_bidding_ready_distingue_nao_pronto_de_indeterminado():
    """⚠️ O booleano não conseguia. `False` colapsava duas conclusões opostas.

    "Lemos a conta e não há sinal" pede instrumentação; "não conseguimos ler"
    pede tentar de novo. O booleano dizia a mesma coisa nos dois casos.
    """
    lido = _pronta(plano_de_mensuracao=_plano(medindo=False))
    nao_lido = _pronta(plano_de_mensuracao=None, metas_da_conta=None)
    assert lido.smart_bidding_ready == pr.NAO_PRONTO
    assert nao_lido.smart_bidding_ready == pr.INDETERMINADO
    # O booleano antigo continua existindo e continua valendo o mesmo.
    assert lido.smart_bidding_eligible is False
    assert nao_lido.smart_bidding_eligible is False


def test_smart_bidding_ready_e_o_booleano_nunca_discordam():
    for r in (_pronta(), _pronta(plano_de_mensuracao=_plano(medindo=False)),
              _pronta(coleta_pos_criacao_provada=False), _pronta(plano_de_mensuracao=None)):
        assert (r.smart_bidding_ready == pr.PRONTO) is r.smart_bidding_eligible


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 5 — o portão de ESCRITA: `exigir_para_criacao`
# ═══════════════════════════════════════════════════════════════════════════


def test_manual_cpc_atravessa_sem_exigir_sinal():
    """MANUAL_CPC não aprende de conversão. Exigi-la seria bloquear por nada."""
    pr.exigir_para_criacao(
        estrategia_lance="MANUAL_CPC",
        prontidao=_pronta(plano_de_mensuracao=_plano(medindo=False)))


def test_maximize_conversions_sem_sinal_e_recusado():
    with pytest.raises(pr.LanceSemMedicao) as exc:
        pr.exigir_para_criacao(
            estrategia_lance="MAXIMIZE_CONVERSIONS",
            prontidao=_pronta(plano_de_mensuracao=_plano(medindo=False)))
    assert "MAXIMIZE_CONVERSIONS" in str(exc.value)


def test_maximize_conversions_com_sinal_provado_atravessa():
    """O ramo POSITIVO do portão de escrita."""
    pr.exigir_para_criacao(estrategia_lance="MAXIMIZE_CONVERSIONS",
                           prontidao=_pronta())


def test_leitura_que_nao_completou_tambem_recusa():
    """⚠️ INDETERMINADO fecha o portão de escrita, e não o abre.

    Uma falha de leitura do Google não é permissão. O plano de ignorância deixa
    a campanha NASCER (pausada, com os portões fechados) e não deixa ela nascer
    APRENDENDO.
    """
    with pytest.raises(pr.LanceSemMedicao):
        pr.exigir_para_criacao(estrategia_lance="MAXIMIZE_CONVERSIONS",
                               prontidao=_pronta(plano_de_mensuracao=None))


def test_maximize_conversion_value_exige_mais_que_conversao():
    """⚠️ Valor não é conversão, e este sistema não lê `value_settings`.

    MaxConvValue otimiza sobre o VALOR de cada conversão. Nada nas cinco
    leituras GAQL desta casa diz que a ação eleita carrega valor — e otimizar
    sobre um valor que ninguém conferiu é perseguir um número que pode ser zero
    em todas as linhas. A recusa nomeia exatamente essa lacuna.
    """
    with pytest.raises(pr.LanceSemValor) as exc:
        pr.exigir_para_criacao(estrategia_lance="MAXIMIZE_CONVERSION_VALUE",
                               prontidao=_pronta())
    assert "valor" in str(exc.value).lower()


def test_valor_declarado_no_perfil_abre_maximize_conversion_value():
    """O ramo positivo existe: quem DECLARA a regra de valor atravessa."""
    from decimal import Decimal
    perfil = pdm.derivar_de_plano(
        _plano(), negocio="portal-mundo-mais", intencao="bpc-loas",
        funil=pdm.FUNIL_ACAO, evento="lead-qualificado",
        regra_de_valor=pdm.RegraDeValor(modo=pdm.VALOR_FIXO,
                                        valor=Decimal("49.90"), moeda="BRL"))
    pr.exigir_para_criacao(estrategia_lance="MAXIMIZE_CONVERSION_VALUE",
                           prontidao=_pronta(perfil=perfil))


def test_estrategia_desconhecida_falha_fechada():
    """⚠️ O que não se reconhece é tratado como quem aprende de conversão.

    Uma lista de exceções que cresce sozinha por omissão é a porta pela qual a
    próxima estratégia entra sem portão.
    """
    with pytest.raises(pr.LanceSemMedicao):
        pr.exigir_para_criacao(estrategia_lance="TARGET_ROAS",
                               prontidao=_pronta(
                                   plano_de_mensuracao=_plano(medindo=False)))


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 6 — ponta a ponta: /subir recusa antes de qualquer efeito
# ═══════════════════════════════════════════════════════════════════════════


def _subir(monkeypatch, *, estrategia: str, plano):
    mudancas = {"estrategia_lance": estrategia}
    _instalar_portas_hermeticas(monkeypatch)
    prova = asyncio.run(trafego.provar(
        trafego.ProvarEntrada(**_payload_da_rota(**mudancas)),
        identidade=base.IDENTIDADE))
    impressao = prova["autorizacao"]["plano_impressao"]

    diario: list = []
    ledger = base.LedgerDeTeste(diario=diario)
    repo = base.RepoDePlanoDeTeste(diario=diario)

    def subir_dublado(*_a, **_k):
        diario.append(("MUTATE", {}))
        return base._recibo_do_executor("SUCESSO")

    base._montar(monkeypatch, ledger=ledger, repo_plano=repo,
                 subir=subir_dublado, plano=plano, diario=diario)
    corpo = trafego.SubirEntrada(**{
        **_payload_da_rota(**mudancas),
        "motivo": "canário pausado com aprovação humana",
        "plano_impressao": impressao,
        "confirmar_criacao_pausada": True,
    })
    try:
        saida = asyncio.run(trafego.subir(corpo, identidade=base.IDENTIDADE))
    except HTTPException as exc:
        saida = exc
    return saida, base._atos(diario)


def test_subir_em_smart_bidding_sem_sinal_nao_chama_o_google(monkeypatch):
    """O DEFEITO CENTRAL, fechado.

    Antes: `/provar` dizia `smart_bidding_eligible=False` com 5 bloqueadores, e
    `/subir` criava a campanha do mesmo jeito. O `MUTATE` está no diário
    medido, não em prosa.
    """
    saida, atos = _subir(monkeypatch, estrategia="MAXIMIZE_CONVERSIONS",
                         plano=_plano(medindo=False))
    assert "MUTATE" not in atos
    assert isinstance(saida, HTTPException)
    assert saida.status_code == 409


def test_a_recusa_acontece_antes_do_recibo_e_do_plano(monkeypatch):
    """⚠️ ANTES de `abrir`, e a ordem não é estética.

    Abrir recibo para uma chamada que nunca sai deixa um `em_voo` órfão, e a
    camada 4 da v10_03 passa a bloquear o item até alguém reconciliar uma
    tentativa que não existiu.
    """
    _, atos = _subir(monkeypatch, estrategia="MAXIMIZE_CONVERSIONS",
                     plano=_plano(medindo=False))
    assert "abrir" not in atos
    assert "despachar" not in atos
    assert "registrar_plano" not in atos


def test_a_recusa_diz_qual_estrategia_e_o_que_falta(monkeypatch):
    saida, _ = _subir(monkeypatch, estrategia="MAXIMIZE_CONVERSIONS",
                      plano=_plano(medindo=False))
    detalhe = str(saida.detail)
    assert "MAXIMIZE_CONVERSIONS" in detalhe
    assert "MANUAL_CPC" in detalhe   # o caminho de saída, dito na recusa
    assert "Nada foi enviado" in detalhe


def test_manual_cpc_continua_nascendo_com_a_medicao_reprovada(monkeypatch):
    """⚠️ O portão é sobre APRENDER, não sobre nascer.

    Recusar MANUAL_CPC porque a conta não mede transformaria uma conta sem
    conversão numa conta sem campanha — e o canário pausado existe justamente
    para colher veredito de política sem depender de medição.
    """
    saida, atos = _subir(monkeypatch, estrategia="MANUAL_CPC",
                         plano=_plano(medindo=False))
    assert "MUTATE" in atos


def test_subir_em_smart_bidding_com_sinal_provado_chama_o_google(monkeypatch):
    """O ramo POSITIVO ponta a ponta — sem ele o portão seria infalsificável."""
    _, atos = _subir(monkeypatch, estrategia="MAXIMIZE_CONVERSIONS",
                     plano=_plano(medindo=True))
    assert "MUTATE" in atos


# ═══════════════════════════════════════════════════════════════════════════
# CONTRAPROVAS DA MISSÃO MULTICANAL (06/09/2026)
# ═══════════════════════════════════════════════════════════════════════════


def test_nenhuma_rota_de_ativacao_existe_no_APP_INTEIRO():
    """CONTRAPROVA 13: não existe rota que ative, despause ou publique campanha.

    ⚠️ O teste anterior com este nome montava DOIS routers de Meta e dizia "app
    inteiro". Este monta `app.main:app`, que é o app de verdade, e varre TODAS
    as rotas — as que existiam, as que entraram nesta missão e as que alguém
    acrescentar depois.

    A varredura é por CAMINHO e por NOME DE FUNÇÃO, porque as duas formas de
    introduzir uma ativação são diferentes: um `POST /ativar` novo, ou um
    `POST /estado` que aceita `ENABLED` no corpo. A segunda não aparece na URL,
    e por isso o teste também cobra que nenhuma rota nomeie ativação.
    """
    from app.main import app

    proibidos = ("ativar", "activate", "enable", "despausar", "unpause",
                 "resume", "retomar", "publicar-campanha")

    #: As DUAS exceções, nomeadas uma a uma e com o motivo. ⚠️ Uma lista de
    #: exceções que crescesse por prefixo (`/api/criativos/*`) seria a porta
    #: pela qual a próxima ativação entraria sem ninguém decidir. Cada entrada
    #: aqui é um caminho literal, e acrescentar uma exige escrever por quê.
    FORA_DO_ESCOPO = {
        # Retoma um TRABALHO da bancada criativa (uma fila local de renderização
        # de peça). Não fala com Google nem com Meta, e não tem campanha.
        "/api/criativos/bancada/trabalhos/{trabalho_id}/retomar",
        # Reativa um ATIVO no cofre (um arquivo arquivado). Também não é
        # campanha, e também não sai desta casa.
        "/api/cofre/ativos/{ativo_id}/reativacao",
    }

    achadas = []
    for rota in app.routes:
        caminho = str(getattr(rota, "path", ""))
        if caminho in FORA_DO_ESCOPO:
            continue
        nome = str(getattr(rota, "name", "")).lower()
        for palavra in proibidos:
            if palavra in caminho.lower() or palavra in nome:
                achadas.append((caminho, nome, palavra))
    assert not achadas, (
        "existe rota que pode ativar campanha: "
        + "; ".join(f"{c} ({n}) casou {p}" for c, n, p in achadas))

    # ⚠️ E a varredura precisa ter visto o app INTEIRO, não um router solto: um
    # `app` vazio passaria neste teste com folga.
    assert len(app.routes) > 100, (
        f"o app montou só {len(app.routes)} rotas — a varredura não cobriu o "
        "sistema, e um verde aqui não provaria nada")


def test_smart_bidding_sem_medicao_bloqueia_em_TODO_canal():
    """CONTRAPROVA 7: a recusa é da autoridade, e ela vale para os quatro canais.

    ⚠️ O portão vivia só no caminho de Search. A autoridade única
    (`volc_ads.mensuracao`) é consultada por canal, e um canal que não declara
    a estratégia pedida recusa ANTES de a conta ser consultada.
    """
    from volc_ads import mensuracao as mens

    for canal in mens.CANAIS:
        v = mens.avaliar(customer_id="5478096539", canal=canal,
                         estrategia_lance="MAXIMIZE_CONVERSIONS")
        assert v.autoriza is False, canal
        assert v.estado == mens.INDETERMINADA, canal
        assert mens.SEM_LEITURA in v.codigos, canal

    # E MANUAL_CPC continua nascendo nos canais que o aceitam — o portão é
    # sobre APRENDER, não sobre nascer.
    livre = mens.avaliar(customer_id="5478096539", canal="SEARCH",
                         estrategia_lance="MANUAL_CPC")
    assert livre.autoriza is True
    assert livre.estado == mens.NAO_APLICAVEL


def test_estrategia_fora_do_canal_recusa_antes_de_consultar_a_conta():
    """PMax não tem MANUAL_CPC, e Demand Gen só tem MAXIMIZE_CONVERSIONS."""
    from volc_ads import mensuracao as mens

    v = mens.avaliar(customer_id="5478096539", canal="DEMAND_GEN",
                     estrategia_lance="TARGET_ROAS",
                     lances_do_canal=("MAXIMIZE_CONVERSIONS",))
    assert v.estado == mens.NAO_PRONTA
    assert mens.ESTRATEGIA_FORA_DO_CANAL in v.codigos
    # ⚠️ NÃO houve leitura: a recusa é do PEDIDO, e ela vem antes do mundo.
    assert v.leitura.estado == mens.NAO_COLETADO


def test_a_autoridade_de_mensuracao_nao_cria_conversion_action():
    """A missão proíbe criar ou alterar conversion action. Prova por árvore."""
    import ast
    import inspect

    from volc_ads import mensuracao as mens

    arvore = ast.parse(inspect.getsource(mens))
    chamadas = {
        no.func.attr if isinstance(no.func, ast.Attribute)
        else getattr(no.func, "id", "")
        for no in ast.walk(arvore) if isinstance(no, ast.Call)
    }
    for proibida in ("mutar", "mutate", "criar_acao", "propor_acao_nova",
                     "validar_mutacoes", "destravar"):
        assert proibida not in chamadas, f"a autoridade chama {proibida}"


def test_a_janela_de_recencia_e_a_mesma_dos_dois_lados():
    """Um número declarado duas vezes com a razão escrita — e cobrado."""
    from volc_ads import mensuracao as mens

    assert mens.JANELA_DE_RECENCIA_DIAS == pm.JANELA_DE_RECENCIA_DIAS


def test_as_listas_de_estrategia_sao_projecao_da_autoridade():
    """Elas deixaram de decidir; ficaram como projeção derivada em import."""
    from volc_ads import mensuracao as mens

    assert set(pr.ESTRATEGIAS_CONHECIDAS) == set(mens.OBJETIVO_POR_ESTRATEGIA)
    assert pr.ESTRATEGIAS_CONHECIDAS is mens.ESTRATEGIAS_CONHECIDAS
    for e in pr.ESTRATEGIAS_SEM_APRENDIZADO:
        assert mens.OBJETIVO_POR_ESTRATEGIA[e] == mens.OBJETIVO_CLIQUE
    for e in pr.ESTRATEGIAS_QUE_EXIGEM_VALOR:
        assert mens.OBJETIVO_POR_ESTRATEGIA[e] == mens.OBJETIVO_VALOR


def test_o_campo_deprecado_recusa_com_NOME_PROPRIO_e_nunca_em_silencio():
    """CONTRAPROVA T04: `include_in_conversions_metric` não decide calado.

    Ele está DEPRECIADO e continua tirando a ação da métrica que o lance
    otimiza — então a recusa é real. O que muda é que ela deixa de aparecer
    como "nenhuma ação válida" e passa a dizer que veio de um campo depreciado.
    """
    from datetime import datetime, timedelta, timezone

    from volc_ads import mensuracao as mens

    agora = datetime(2026, 9, 6, tzinfo=timezone.utc)
    leitura = mens.Leitura(
        estado=mens.COM_DADOS, procedencia="teste",
        lido_em=(agora - timedelta(hours=1)).isoformat(), meta_biddable=True,
        acoes=(mens.AcaoLida(id="9", status="ENABLED", primaria=True,
                             incluida_em_metricas=False,
                             conversoes_na_janela=5.0, dias_desde_a_ultima=1),))
    v = mens.avaliar(customer_id="1", canal="DISPLAY",
                     estrategia_lance="MAXIMIZE_CONVERSIONS",
                     leitura=leitura, agora=agora)
    assert v.estado == mens.NAO_PRONTA
    assert mens.FORA_DA_METRICA_DE_CONVERSOES in v.codigos
    (b,) = [x for x in v.bloqueios
            if x.codigo == mens.FORA_DA_METRICA_DE_CONVERSOES]
    assert "DEPRECIADO" in b.causa

    # ⚠️ E `None` (campo não lido) NÃO recusa: não lido nunca foi um `False`.
    lido_parcial = mens.Leitura(
        estado=mens.COM_DADOS, procedencia="teste",
        lido_em=(agora - timedelta(hours=1)).isoformat(), meta_biddable=True,
        acoes=(mens.AcaoLida(id="9", status="ENABLED", primaria=True,
                             incluida_em_metricas=None,
                             conversoes_na_janela=5.0, dias_desde_a_ultima=1),))
    assert mens.avaliar(customer_id="1", canal="DISPLAY",
                        estrategia_lance="MAXIMIZE_CONVERSIONS",
                        leitura=lido_parcial, agora=agora).estado == mens.PRONTA


def test_primary_for_goal_ausente_vale_TRUE_e_nao_inverte_o_veredito():
    """O default documentado, aplicado — e o bug que ele desfaz.

    `pmax.ler_mensuracao` lia `bool(ca.primary_for_goal)`, que devolve `False`
    para uma ação em que o campo NÃO VEIO. A autoridade aplica o default oficial
    ("ausente vale true") e diz que está aplicando.
    """
    from datetime import datetime, timedelta, timezone

    from volc_ads import mensuracao as mens

    agora = datetime(2026, 9, 6, tzinfo=timezone.utc)
    acao = mens.AcaoLida(id="9", status="ENABLED", primaria=None,
                         conversoes_na_janela=5.0, dias_desde_a_ultima=1)
    assert acao.primaria_efetiva is True
    v = mens.avaliar(
        customer_id="1", canal="DISPLAY",
        estrategia_lance="MAXIMIZE_CONVERSIONS",
        leitura=mens.Leitura(
            estado=mens.COM_DADOS, procedencia="teste",
            lido_em=(agora - timedelta(hours=1)).isoformat(),
            meta_biddable=True, acoes=(acao,)),
        agora=agora)
    assert v.estado == mens.PRONTA


def test_ausencia_de_medicao_e_zero_medido_sao_bloqueios_DIFERENTES():
    """CONTRAPROVA T04: ausência distinta de zero, na frase que o operador lê."""
    from datetime import datetime, timedelta, timezone

    from volc_ads import mensuracao as mens

    agora = datetime(2026, 9, 6, tzinfo=timezone.utc)
    quando = (agora - timedelta(hours=1)).isoformat()

    def _v(contagem):
        return mens.avaliar(
            customer_id="1", canal="DISPLAY",
            estrategia_lance="MAXIMIZE_CONVERSIONS",
            leitura=mens.Leitura(
                estado=mens.COM_DADOS, procedencia="teste", lido_em=quando,
                meta_biddable=True,
                acoes=(mens.AcaoLida(id="9", status="ENABLED", primaria=True,
                                     conversoes_na_janela=contagem,
                                     dias_desde_a_ultima=1),)),
            agora=agora)

    nao_medido = _v(None).resumo()
    medido_zero = _v(0.0).resumo()
    assert "ninguém mediu o volume" in nao_medido
    assert "volume medido é zero" in medido_zero
    assert "ninguém mediu o volume" not in medido_zero, (
        "zero medido virou 'ninguém mediu' — os dois estados colapsaram")


def test_recibo_VELHO_nao_transforma_erro_de_mensuracao_em_aviso():
    """CONTRAPROVA: quanto mais velha a leitura, NÃO mais permissivo o canal.

    ⚠️ Fail-open reproduzido pela revisão adversarial de 06/09/2026.
    `LEITURA_VELHA` era uma saída ANTECIPADA em `avaliar` E estava na lista de
    avisos de PMax. Numa conta SEM nenhuma ação de conversão: recibo fresco →
    `SEM_ACAO_DE_CONVERSAO` → `r.erro` → campanha bloqueada; o MESMO recibo 25h
    mais velho → só `LEITURA_VELHA` → `r.aviso` → `r.ok=True` e o payload seguia
    para o `validate_only`.

    A idade continua sendo um bloqueio nomeado; o que ela deixou de fazer é
    ESCONDER o que a conta respondeu.
    """
    from datetime import datetime, timedelta, timezone

    from volc_ads import mensuracao as mens

    agora = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)

    def _v(horas: int):
        return mens.avaliar(
            customer_id="1", canal="PERFORMANCE_MAX",
            estrategia_lance="MAXIMIZE_CONVERSIONS",
            leitura=mens.Leitura(
                estado=mens.VAZIO_CONFIRMADO, acoes=(), procedencia="teste",
                lido_em=(agora - timedelta(hours=horas)).isoformat()),
            agora=agora)

    fresco, velho = _v(1), _v(25)
    assert mens.SEM_ACAO_DE_CONVERSAO in fresco.codigos
    # ⚠️ O FATO DA CONTA SOBREVIVE À IDADE — era ele que sumia.
    assert mens.SEM_ACAO_DE_CONVERSAO in velho.codigos
    assert mens.LEITURA_VELHA in velho.codigos
    assert velho.autoriza is False


def test_valor_e_sinal_em_acoes_diferentes_recusa_em_vez_de_estourar():
    """CONTRAPROVA: `avaliar` sempre devolve Veredito — nunca um IndexError.

    ⚠️ Reproduzido pela revisão adversarial: com valor numa ação e sinal noutra,
    `elegiveis` esvaziava SEM bloqueio e a eleição fazia `sorted(())[0]`. Um
    `IndexError` escapa do `except PortaoFechado` da rota e vira 500 — quando a
    resposta certa é 409 com o bloqueio nomeado.
    """
    from volc_ads import mensuracao as mens

    com_valor_sem_sinal = mens.AcaoLida(
        id="1", status="ENABLED", carrega_valor=True, conversoes_na_janela=0.0)
    com_sinal_sem_valor = mens.AcaoLida(
        id="2", status="ENABLED", carrega_valor=False,
        conversoes_na_janela=5.0, dias_desde_a_ultima=2)

    v = mens.avaliar(
        customer_id="1", canal="SEARCH", estrategia_lance="TARGET_ROAS",
        leitura=mens.Leitura(estado=mens.COM_DADOS, procedencia="teste",
                             acoes=(com_valor_sem_sinal, com_sinal_sem_valor)))
    assert v.estado == mens.NAO_PRONTA
    assert mens.SEM_VALOR_DECLARADO in v.codigos
    assert "ações DIFERENTES" in v.resumo()

    # E `exigir` levanta a exceção TIPADA, que a rota traduz em 409.
    with pytest.raises(mens.MensuracaoNaoProvada):
        mens.exigir(customer_id="1", canal="SEARCH",
                    estrategia_lance="TARGET_ROAS",
                    leitura=mens.Leitura(
                        estado=mens.COM_DADOS, procedencia="teste",
                        acoes=(com_valor_sem_sinal, com_sinal_sem_valor)))
