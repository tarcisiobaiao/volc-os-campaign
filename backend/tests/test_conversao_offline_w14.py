"""W14 — conversões de volta ao Google com o valor que nós medimos.

Herméticos: nenhuma rede, nenhuma credencial, nenhum banco. A Data Manager é
`httpx.MockTransport` ou um dublê; o registro é um dublê que imita as regras de
unicidade da v25_01 (a prova das regras no banco é a suíte
`tools/freedom-lab/db/suites/v25_w14.sh`).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.trafego import data_manager as dm
from app.trafego import perfil_de_mensuracao as pdm
from app.trafego import plano_mensuracao as pm
from app.trafego.conversao_offline.application import destino as de
from app.trafego.conversao_offline.application import enviar as en
from app.trafego.conversao_offline.application import portas
from app.trafego.conversao_offline.application import preparar as pr
from app.trafego.conversao_offline.domain import evento as ev
from app.trafego.conversao_offline.domain import valor as vl
from app.trafego.conversao_offline.infrastructure import data_manager_http as dmh
from app.trafego.conversao_offline.infrastructure import registro_postgrest as rp

BRT = timezone(timedelta(hours=-3))
CONTA = "5478096539"          # Portal Mundo Mais (creditoup.com.br)
MCC = "6016739364"
ACAO = "900000001"         # sintético: a ação de importação ainda não existe
HOJE = date(2026, 10, 15)
DIA = date(2026, 10, 10)
COORTE = vl.Coorte(DIA, "cup-bpc-loas", "creditoup.com.br")
LIDA = datetime(2026, 10, 15, 9, 0, tzinfo=BRT)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures e dublês
# ═══════════════════════════════════════════════════════════════════════════


TAG = "7000000001"           # a ação da tag do site, com o valor fixo de 10


def _plano_lido(owner=CONTA, tipo_offline="UPLOAD_CLICKS", status_offline="ENABLED",
                primaria_offline=False):
    """A conta como seria lida: a tag primária (valor fixo) e a ação offline Secondary."""
    tag = pm.AcaoDeConversao(
        id=TAG, resource_name=f"customers/{owner}/conversionActions/{TAG}",
        owner_customer_id=owner, nome="Lead — tag do site",
        categoria="PURCHASE", origem="WEBSITE", tipo="WEBPAGE",
        status="ENABLED", primaria=True)
    offline = pm.AcaoDeConversao(
        id=ACAO, resource_name=f"customers/{owner}/conversionActions/{ACAO}",
        owner_customer_id=owner, nome="Receita medida — offline",
        categoria="PURCHASE", origem="WEBSITE", tipo=tipo_offline,
        status=status_offline, primaria=primaria_offline)
    return pm.montar(
        customer_id=CONTA, login_customer_id=MCC,
        meta_efetiva=pm.MetaEfetiva(
            nivel=pm.NIVEL_CUSTOMER, nivel_estado=pm.COM_DADOS,
            metas_da_conta=(pm.Meta(categoria="PURCHASE", origem="WEBSITE", biddable=True),),
            metas_da_conta_estado=pm.COM_DADOS,
            metas_da_campanha=(), metas_da_campanha_estado=pm.INELEGIVEL),
        acoes=(tag, offline), acoes_estado=pm.COM_DADOS,
        marcacao=pm.InventarioDeMarcacao(estado=pm.COM_DADOS, auto_tagging=True,
                                         aceitou_termos_de_dados=True))


def _plano():
    return de.plano_para_acao_offline(_plano_lido(), ACAO)


def _perfil(regra=None, janela=None, consentimento=pdm.CONSENTIMENTO_CONCEDIDO, plano=None):
    return pdm.derivar_de_plano(
        plano or _plano(), negocio="creditoup", intencao="bpc-loas",
        funil=pdm.FUNIL_ACAO, evento="receita-de-sessao",
        regra_de_valor=regra or pdm.RegraDeValor(modo=pdm.VALOR_POR_EVENTO),
        janela=janela or pdm.JanelaDeAtribuicao(estado=pdm.JANELA_DECLARADA,
                                                dias_de_clique=90, modelo="DATA_DRIVEN"),
        consentimento=consentimento)


def _politica(**mud):
    base = dict(fonte_de_receita="joinads", maturidade_minima_dias=3,
                max_defasagem_cambio_dias=3, aceitar_rateio_de_coorte=True)
    base.update(mud)
    return vl.PoliticaDeValor(**base)


def _moeda(codigo="BRL", conta=CONTA):
    return vl.MoedaDaConta(codigo=codigo, lida_em=LIDA, customer_id=conta)


def _receita(valor="12.00", moeda="USD", coorte=COORTE, fonte="joinads", grao=vl.GRAO_COORTE):
    return vl.ReceitaDatada(fonte=fonte, observacao_id=77, coorte=coorte,
                            receita=None if valor is None else Decimal(valor), moeda=moeda,
                            coletado_em=datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc),
                            grao=grao)


def _cot(taxa="5.4100", modo="exata", par="USD/BRL", defasagem=0):
    return vl.CotacaoResolvida(par=par, modo=modo,
                               taxa=None if taxa is None else Decimal(taxa),
                               cotacao_id=501, data_cotacao=DIA,
                               as_of=datetime(2026, 10, 10, 13, 10, tzinfo=BRT),
                               fonte="bcb_ptax", defasagem_dias=defasagem)


def _clique(n=1, gclid=None, consent=dm.CONSENTIMENTO_CONCEDIDO, quando=None, coorte=COORTE):
    return ev.CliqueObservado(
        visita_ref=f"visita-{n}",
        clique=dm.IdentificadorDeClique(tipo=dm.CLIQUE_GCLID, valor=gclid or f"Cj0KEQ-{n}"),
        visitado_em=quando or datetime(2026, 10, 10, 10, n, tzinfo=BRT),
        coorte=coorte, consentimento=consent)


class Cliques:
    def __init__(self, cliques, sessoes=4):
        self._c, self._s = list(cliques), sessoes
        self.pedidos = []

    def cliques(self, *, customer_id, de, ate):
        self.pedidos.append((customer_id, de, ate))
        return list(self._c)

    def sessoes_da_coorte(self, coorte):
        return self._s


class Receita:
    def __init__(self, linha):
        self.linha = linha
        self.pedidos = []

    def receita_vigente(self, *, fonte, coorte, conhecido_ate):
        self.pedidos.append((fonte, coorte, conhecido_ate))
        return self.linha


class Cambio:
    def __init__(self, cot):
        self.cot = cot
        self.pedidos = []

    def resolver(self, *, data, par, max_defasagem_dias, conhecido_ate):
        self.pedidos.append((data, par, max_defasagem_dias, conhecido_ate))
        return self.cot


class RegistroMemoria:
    """Imita a v25_01: lote real vivo único por impressão e por transaction_id."""

    def __init__(self):
        self.decisoes, self.lotes, self.itens = [], {}, []

    def envios_reais_vivos(self, *, operating_account_id, product_destination_id, transaction_ids):
        out = {}
        for it in self.itens:
            if (it["modo"] == "real" and it["estado"] in portas.ESTADOS_VIVOS
                    and it["transaction_id"] in transaction_ids):
                out[it["transaction_id"]] = portas.EnvioAnterior(
                    it["lote_id"], it["estado"], it["valor_impressao"])
        return out

    def envios_reais_por_coorte(self, *, operating_account_id, product_destination_id, coortes):
        out = {}
        for it in self.itens:
            if it["modo"] != "real" or it["estado"] not in portas.ESTADOS_VIVOS:
                continue
            d = next(d for d in self.decisoes if d["estado"] == "elegivel"
                     and d["transaction_id"] == it["transaction_id"]
                     and d["valor_impressao"] == it["valor_impressao"])
            k = vl.Coorte(date.fromisoformat(d["coorte_data"]), d["coorte_campanha"],
                          d["coorte_dominio"])
            if k in coortes:
                antes = out.get(k, portas.EnvioDaCoorte(0, Decimal(0)))
                out[k] = portas.EnvioDaCoorte(antes.itens + 1, antes.soma + Decimal(d["valor"]))
        return out

    def registrar_decisoes(self, *, rodada, customer_id, operating_account_id,
                           product_destination_id, decisoes):
        self.decisoes.extend(dict(d, rodada=rodada) for d in decisoes)

    def abrir_lote(self, *, modo, impressao, customer_id, login_customer_id,
                   operating_account_id, product_destination_id, itens,
                   aprovacao=None, validacao_lote_id=None):
        if modo == "real":
            val = self.lotes.get(validacao_lote_id)
            if not val or val["estado"] != "aceito" or val["impressao"] != impressao:
                raise en.ValidacaoAusente("sem validate_only aceito")
            validados = sorted((it["transaction_id"], it["valor_impressao"]) for it in self.itens
                               if it["lote_id"] == validacao_lote_id)
            if validados != sorted(itens):
                raise en.ValidacaoAusente("itens diferentes dos validados")
            elegiveis = {(d["transaction_id"], d["valor_impressao"]) for d in self.decisoes
                         if d["estado"] == "elegivel"}
            if not set(itens) <= elegiveis:
                raise en.ValidacaoAusente("item sem decisão elegível com o mesmo valor")
            # O mesmo envelope sem resposta é reenviado: o lote velho vira `reenviado`.
            for lid, l in self.lotes.items():
                if l["modo"] == "real" and l["impressao"] == impressao and l["estado"] == "sem_resposta":
                    self.fechar_lote(lote_id=lid, estado="reenviado", request_id=None, resposta={})
            for l in self.lotes.values():
                if (l["modo"] == "real" and l["impressao"] == impressao
                        and l["estado"] not in ("recusado", "falha", "reenviado")):
                    raise en.JaEnviado("23505 envelope")
            vivos = self.envios_reais_vivos(operating_account_id=operating_account_id,
                                            product_destination_id=product_destination_id,
                                            transaction_ids=[t for t, _ in itens])
            if vivos:
                raise en.JaEnviado("23505 transaction_id")
        lote_id = len(self.lotes) + 1
        self.lotes[lote_id] = dict(modo=modo, impressao=impressao, estado="em_voo",
                                   aprovacao=aprovacao, request_id=None)
        for t, v in itens:
            self.itens.append(dict(lote_id=lote_id, modo=modo, transaction_id=t,
                                   valor_impressao=v, estado="em_voo"))
        return portas.LoteRegistrado(lote_id, impressao, modo, "em_voo")

    def ler_lote(self, lote_id):
        l = self.lotes.get(lote_id)
        return None if l is None else portas.LoteRegistrado(
            lote_id, l["impressao"], l["modo"], l["estado"], l["request_id"])

    def fechar_lote(self, *, lote_id, estado, request_id, resposta):
        self.lotes[lote_id].update(estado=estado, request_id=request_id, resposta=resposta)
        for it in self.itens:
            if it["lote_id"] == lote_id:
                it["estado"] = estado


class Transporte:
    def __init__(self, resposta=None):
        self.corpos = []
        self.resposta = resposta or portas.RespostaDeIngestao(
            respondeu=True, aceito=True, status_http=200, request_id="req-w14")

    def ingerir(self, corpo):
        self.corpos.append(json.loads(json.dumps(corpo)))
        return self.resposta

    def status(self, request_id):
        return portas.StatusDoPedido(estado="SUCCESS", corpo={"requestId": request_id})


def _preparar(cliques=None, linha="padrao", cot="padrao", registro=None, perfil=None,
              politica=None, moeda=None, sessoes=4, conhecido_ate=None, retomar_incertos=False,
              plano=None, rodada="rodada-1"):
    registro = registro or RegistroMemoria()
    fonte_c = Cliques(cliques if cliques is not None else [_clique(1), _clique(2)], sessoes)
    fonte_r = Receita(_receita() if linha == "padrao" else linha)
    fonte_x = Cambio(_cot() if cot == "padrao" else cot)
    preparo = pr.preparar_lote(
        plano=plano or _plano(), perfil=perfil or _perfil(plano=plano),
        moeda_da_conta=moeda or _moeda(),
        politica=politica or _politica(), de=DIA, ate=DIA, hoje=HOJE,
        conhecido_ate=conhecido_ate, rodada=rodada,
        cliques=fonte_c, receita=fonte_r, cambio=fonte_x, registro=registro,
        retomar_incertos=retomar_incertos)
    return preparo, registro, fonte_c, fonte_r, fonte_x


def _calc(**mud):
    base = dict(receita=_receita(), cotacao=_cot(), moeda_da_conta=_moeda(),
                sessoes_da_coorte=4, politica=_politica(), hoje=HOJE)
    base.update(mud)
    return vl.calcular_valor(**base)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O VALOR — medido, ou pulado. Nunca 10, nunca 0.
# ═══════════════════════════════════════════════════════════════════════════


def test_valor_e_receita_convertida_e_rateada_com_proveniencia():
    v = _calc()
    # 12.00 USD × 5.41 / 4 sessões = 16.23 BRL
    assert v.valor == Decimal("16.23") and v.moeda == "BRL"
    assert v.estimado is True
    p = v.proveniencia
    assert p["metodo"] == "rateio_uniforme_por_sessao" and p["sessoes_da_coorte"] == 4
    assert p["receita"]["observacao_id"] == 77 and p["receita"]["valor_original"] == "12.00"
    assert p["cambio"]["cotacao_id"] == 501 and p["cambio"]["modo"] == "exata"
    assert p["moeda_da_conta"]["customer_id"] == CONTA


@pytest.mark.parametrize("mud,motivo", [
    (dict(receita=None), vl.PULO_RECEITA_AUSENTE),
    (dict(receita=_receita(valor=None)), vl.PULO_RECEITA_AUSENTE),
    (dict(receita=_receita(valor="0")), vl.PULO_RECEITA_ZERO),
    (dict(receita=_receita(valor="-1")), vl.PULO_RECEITA_INVALIDA),
    (dict(receita=_receita(fonte="gam")), vl.PULO_FONTE_NAO_ELEITA),
    (dict(hoje=DIA + timedelta(days=2)), vl.PULO_RECEITA_IMATURA),
    (dict(politica=_politica(aceitar_rateio_de_coorte=False)), vl.PULO_GRAO_SEM_ACEITE),
    (dict(sessoes_da_coorte=None), vl.PULO_COORTE_SEM_SESSOES),
    (dict(sessoes_da_coorte=0), vl.PULO_COORTE_SEM_SESSOES),
    (dict(cotacao=None), vl.PULO_SEM_COTACAO),
    (dict(cotacao=_cot(taxa=None, modo="defasada", defasagem=17)), vl.PULO_SEM_COTACAO),
    (dict(cotacao=_cot(taxa=None, modo="sem_cotacao")), vl.PULO_SEM_COTACAO),
    (dict(cotacao=_cot(modo="anterior", defasagem=5)), vl.PULO_CAMBIO_DEFASADO),
    (dict(cotacao=_cot(par="EUR/BRL")), vl.PULO_PAR_ERRADO),
    (dict(receita=_receita(valor="0.01"), sessoes_da_coorte=1000), vl.PULO_VALOR_ARREDONDA_ZERO),
])
def test_sem_valor_medido_o_evento_e_pulado_com_motivo(mud, motivo):
    r = _calc(**mud)
    assert isinstance(r, vl.Pulo), r
    assert r.motivo == motivo and r.detalhe


def test_cotacao_anterior_dentro_da_defasagem_vale():
    assert _calc(cotacao=_cot(modo="anterior", defasagem=2)).valor == Decimal("16.23")


def test_mesma_moeda_nao_pede_cambio():
    v = _calc(receita=_receita(valor="40.00", moeda="BRL"), cotacao=None)
    assert v.valor == Decimal("10.00")  # 40/4: o número vem da receita, não de constante
    assert v.proveniencia["cambio"] == {"modo": vl.CAMBIO_MOEDA_LOCAL}


def test_grao_por_sessao_nao_e_estimado_e_nao_divide():
    v = _calc(receita=_receita(grao=vl.GRAO_SESSAO), politica=_politica(aceitar_rateio_de_coorte=False))
    assert v.valor == Decimal("64.92") and v.estimado is False
    assert v.proveniencia["metodo"] == "observado_por_sessao"


def test_dinheiro_em_float_e_recusado():
    with pytest.raises(TypeError):
        vl.ReceitaDatada(fonte="joinads", observacao_id=1, coorte=COORTE, receita=12.5,
                         moeda="USD", coletado_em=datetime.now(timezone.utc))


def test_politica_nao_tem_default_financeiro():
    with pytest.raises(TypeError):
        vl.PoliticaDeValor()  # fonte, maturidade e defasagem são obrigatórias
    assert _politica(aceitar_rateio_de_coorte=False).aceitar_rateio_de_coorte is False
    assert vl.PoliticaDeValor(fonte_de_receita="joinads", maturidade_minima_dias=3,
                              max_defasagem_cambio_dias=3).aceitar_rateio_de_coorte is False


def test_impressao_do_valor_muda_com_o_valor_e_com_a_origem():
    a = _calc()
    assert a.impressao() == _calc().impressao()
    assert a.impressao() != _calc(receita=_receita(valor="12.04")).impressao()
    assert a.impressao() != _calc(cotacao=_cot(taxa="5.4101")).impressao()


# ═══════════════════════════════════════════════════════════════════════════
# 1b. O DESTINO — a ação de importação, nunca a tag
# ═══════════════════════════════════════════════════════════════════════════


def test_plano_lido_elege_a_tag_e_o_destino_offline_e_a_acao_de_importacao():
    lido = _plano_lido()
    assert lido.acao_alvo.id == TAG  # o lance persegue a tag (valor fixo): é o defeito
    plano = _plano()
    assert plano.destino.product_destination_id == ACAO
    assert plano.destino.tipo_da_acao == "UPLOAD_CLICKS"
    assert lido.acao_alvo.id == TAG  # o plano lido não muda


@pytest.mark.parametrize("acao_id,lido", [
    ("Receita medida — offline", None),
    ("999", None),
    (TAG, None),
    (ACAO, "pausada"),
])
def test_destino_offline_invalido_e_recusado(acao_id, lido):
    plano = _plano_lido(status_offline="PAUSED") if lido else _plano_lido()
    with pytest.raises(de.AcaoOfflineInvalida):
        de.plano_para_acao_offline(plano, acao_id)


def test_preparo_recusa_destino_que_nao_e_importacao():
    """Sem a derivação, o plano lido mandaria o valor para a TAG — recusado."""
    with pytest.raises(de.AcaoOfflineInvalida):
        pr.preparar_lote(plano=_plano_lido(), perfil=_perfil(plano=_plano_lido()),
                         moeda_da_conta=_moeda(), politica=_politica(), de=DIA, ate=DIA,
                         hoje=HOJE, conhecido_ate=None, rodada="r",
                         cliques=Cliques([_clique(1)]), receita=Receita(_receita()),
                         cambio=Cambio(_cot()), registro=RegistroMemoria())


# ═══════════════════════════════════════════════════════════════════════════
# 2. O PREPARO — decisões gravadas, envelope só com valor medido
# ═══════════════════════════════════════════════════════════════════════════


def test_preparo_feliz_monta_envelope_com_valor_na_moeda_da_conta():
    preparo, registro, *_ = _preparar()
    assert preparo.resumo()["elegiveis"] == 2
    (lote,) = preparo.lotes
    assert lote.recibo_local.recusados == 0
    assert {e.valor for e in lote.envelope.itens} == {Decimal("16.23")}
    assert {e.moeda for e in lote.envelope.itens} == {"BRL"}
    assert lote.envelope.destino.operating_account_id == CONTA
    assert lote.envelope.destino.product_destination_id == ACAO
    assert len(registro.decisoes) == 2 and all(d["rodada"] == "rodada-1" for d in registro.decisoes)


def test_sem_receita_nada_vai_e_tudo_fica_registrado():
    preparo, registro, *_ = _preparar(linha=None)
    assert preparo.lotes == ()
    assert preparo.resumo()["pulados"] == {vl.PULO_RECEITA_AUSENTE: 2}
    assert [d["estado"] for d in registro.decisoes] == ["pulado", "pulado"]
    assert all(d["valor"] is None for d in registro.decisoes)


def test_sem_cotacao_nada_vai():
    preparo, *_ = _preparar(cot=_cot(taxa=None, modo="sem_cotacao"))
    assert preparo.lotes == () and preparo.resumo()["pulados"] == {vl.PULO_SEM_COTACAO: 2}


def test_perfil_com_valor_fixo_e_recusado_antes_de_ler_qualquer_coisa():
    fixo = pdm.RegraDeValor(modo=pdm.VALOR_FIXO, valor=Decimal("10"), moeda="BRL")
    fonte = Cliques([_clique(1)])
    with pytest.raises(pr.ValorFixoRecusado):
        pr.preparar_lote(plano=_plano(), perfil=_perfil(regra=fixo), moeda_da_conta=_moeda(),
                         politica=_politica(), de=DIA, ate=DIA, hoje=HOJE, conhecido_ate=None,
                         rodada="r", cliques=fonte, receita=Receita(_receita()),
                         cambio=Cambio(_cot()), registro=RegistroMemoria())
    assert fonte.pedidos == []


def test_perfil_sem_valor_e_recusado():
    with pytest.raises(pr.RegraDeValorIncompativel):
        _preparar(perfil=_perfil(regra=pdm.RegraDeValor(modo=pdm.VALOR_SEM_VALOR)))


def test_moeda_lida_de_outra_conta_e_recusada():
    with pytest.raises(pr.MoedaDeOutraConta):
        _preparar(moeda=_moeda(conta="1111111111"))


def test_consentimento_da_conta_nao_concedido_recusa_o_lote():
    with pytest.raises(dm.ConsentimentoInsuficiente):
        _preparar(perfil=_perfil(consentimento=pdm.CONSENTIMENTO_NAO_DECLARADO))


def test_visitante_sem_consentimento_e_pulado():
    preparo, *_ = _preparar(cliques=[_clique(1, consent=dm.CONSENTIMENTO_NAO_DECLARADO), _clique(2)])
    assert preparo.resumo()["pulados"] == {ev.PULO_SEM_CONSENTIMENTO: 1}
    assert len(preparo.lotes[0].envelope.itens) == 1


def test_janela_nao_declarada_e_clique_expirado_sao_pulados():
    preparo, *_ = _preparar(perfil=_perfil(janela=pdm.JanelaDeAtribuicao(
        estado=pdm.JANELA_NAO_DECLARADA, causa="não lida")))
    assert preparo.resumo()["pulados"] == {ev.PULO_JANELA_NAO_DECLARADA: 2}
    velho = _clique(3, quando=datetime(2026, 6, 1, 10, 0, tzinfo=BRT))
    preparo, *_ = _preparar(cliques=[velho])
    assert preparo.resumo()["pulados"] == {ev.PULO_CLIQUE_EXPIRADO: 1}


def test_clique_repetido_vale_uma_vez():
    preparo, *_ = _preparar(cliques=[_clique(1, gclid="G"), _clique(2, gclid="G")])
    assert preparo.resumo()["elegiveis"] == 1
    assert preparo.resumo()["pulados"] == {pr.PULO_CLIQUE_REPETIDO: 1}


def test_receita_e_cambio_sao_lidos_uma_vez_por_coorte():
    _, _, _, fonte_r, fonte_x = _preparar(cliques=[_clique(i) for i in range(1, 6)])
    assert len(fonte_r.pedidos) == 1 and len(fonte_x.pedidos) == 1
    assert fonte_x.pedidos[0][1] == "USD/BRL" and fonte_r.pedidos[0][0] == "joinads"


def test_transaction_id_e_estavel_e_nao_carrega_o_gclid():
    a, *_ = _preparar()
    b, *_ = _preparar()
    assert [d.transaction_id for d in a.decisoes] == [d.transaction_id for d in b.decisoes]
    for d in a.decisoes:
        assert "Cj0KEQ" not in d.transaction_id
        assert "Cj0KEQ" not in json.dumps(d.json())


def test_mais_de_2000_eventos_viram_mais_de_um_lote():
    preparo, *_ = _preparar(cliques=[_clique(i, quando=datetime(2026, 10, 10, 10, 0, tzinfo=BRT) + timedelta(seconds=i))
                                     for i in range(2001)], sessoes=2001)
    assert [len(l.itens) for l in preparo.lotes] == [2000, 1]


# ═══════════════════════════════════════════════════════════════════════════
# 3. IDEMPOTÊNCIA — o que já foi mandado não vai de novo
# ═══════════════════════════════════════════════════════════════════════════


def _envio_real_feito(registro, preparo):
    lote = preparo.lotes[0]
    (val,) = en.validar_no_google(lotes=[lote], transporte=Transporte(), registro=registro)
    registro.abrir_lote(modo="real", impressao=lote.envelope.impressao(), customer_id=CONTA,
                        login_customer_id=MCC, operating_account_id=CONTA,
                        product_destination_id=ACAO, itens=list(lote.itens),
                        aprovacao={"x": 1}, validacao_lote_id=val.lote_id)


def test_reexecucao_depois_do_envio_real_pula_como_ja_enviado():
    registro = RegistroMemoria()
    primeiro, *_ = _preparar(registro=registro)
    _envio_real_feito(registro, primeiro)
    segundo, *_ = _preparar(registro=registro)
    assert segundo.lotes == ()
    assert segundo.resumo()["pulados"] == {ev.PULO_JA_ENVIADO: 2}


def test_receita_revista_depois_do_envio_nao_vira_ajuste_silencioso():
    registro = RegistroMemoria()
    primeiro, *_ = _preparar(registro=registro)
    _envio_real_feito(registro, primeiro)
    segundo, *_ = _preparar(registro=registro, linha=_receita(valor="20.00"))
    assert segundo.lotes == ()
    assert segundo.resumo()["pulados"] == {ev.PULO_AJUSTE_NAO_AUTORIZADO: 2}


# ═══════════════════════════════════════════════════════════════════════════
# 4. O CORPO de events:ingest
# ═══════════════════════════════════════════════════════════════════════════


def test_corpo_segue_o_contrato_da_data_manager():
    preparo, *_ = _preparar(cliques=[_clique(1)])
    corpo = ev.corpo_ingestao(preparo.lotes[0].envelope, validate_only=True)
    assert corpo["validateOnly"] is True
    assert corpo["destinations"] == [{
        "operatingAccount": {"accountType": "GOOGLE_ADS", "accountId": CONTA},
        "loginAccount": {"accountType": "GOOGLE_ADS", "accountId": MCC},
        "productDestinationId": ACAO}]
    (e,) = corpo["events"]
    assert e["adIdentifiers"] == {"gclid": "Cj0KEQ-1"}
    assert e["currency"] == "BRL" and e["eventSource"] == "WEB"
    assert e["eventTimestamp"] == "2026-10-10T10:01:00-03:00"
    assert e["transactionId"].startswith("volc-w14-")
    assert e["consent"] == {"adUserData": "CONSENT_GRANTED"}
    assert '"conversionValue":16.23' in json.dumps(corpo, separators=(",", ":"))
    assert "encoding" not in corpo and "userData" not in e


def test_corpo_exige_validate_only_explicito():
    preparo, *_ = _preparar(cliques=[_clique(1)])
    with pytest.raises(TypeError):
        ev.corpo_ingestao(preparo.lotes[0].envelope, validate_only=None)


def test_valor_que_muda_na_serializacao_e_recusado():
    with pytest.raises(ValueError):
        ev._numero_json(Decimal("0.1000000000000000055511151231257827"))
    assert ev._numero_json(Decimal("16.23")) == 16.23


# ═══════════════════════════════════════════════════════════════════════════
# 5. validateOnly — o único modo exercitado
# ═══════════════════════════════════════════════════════════════════════════


def test_validar_no_google_manda_validate_only_true_e_registra():
    preparo, registro, *_ = _preparar()
    t = Transporte()
    (res,) = en.validar_no_google(lotes=list(preparo.lotes), transporte=t, registro=registro)
    assert [c["validateOnly"] for c in t.corpos] == [True]
    assert res.estado == "aceito" and res.modo == "validate_only"
    assert registro.lotes[res.lote_id]["estado"] == "aceito"
    assert registro.lotes[res.lote_id]["impressao"] == preparo.lotes[0].envelope.impressao()


def test_validate_only_sem_resposta_nao_vira_falha():
    preparo, registro, *_ = _preparar()
    t = Transporte(portas.RespostaDeIngestao(respondeu=False, aceito=False, erro={"tipo": "Timeout"}))
    (res,) = en.validar_no_google(lotes=list(preparo.lotes), transporte=t, registro=registro)
    assert res.estado == "sem_resposta"


def test_validate_only_recusado_pelo_google_fica_recusado():
    preparo, registro, *_ = _preparar()
    t = Transporte(portas.RespostaDeIngestao(respondeu=True, aceito=False, status_http=400,
                                             erro={"message": "INVALID_ARGUMENT"}))
    (res,) = en.validar_no_google(lotes=list(preparo.lotes), transporte=t, registro=registro)
    assert res.estado == "recusado"


# ═══════════════════════════════════════════════════════════════════════════
# 6. O envio real — travado
# ═══════════════════════════════════════════════════════════════════════════


def _aprovacao(impressao):
    return en.AprovacaoDeEnvio(impressao=impressao, aprovado_por="Tarcisio",
                               aprovado_em=datetime(2026, 10, 15, 16, 0, tzinfo=BRT),
                               referencia="teste")


def _validado():
    preparo, registro, *_ = _preparar()
    (val,) = en.validar_no_google(lotes=list(preparo.lotes), transporte=Transporte(), registro=registro)
    return preparo.lotes[0], registro, val


def test_envio_real_com_trava_fechada_nao_chama_nada(monkeypatch):
    from volc_ads.gads import modo
    monkeypatch.delenv("FORGE_PERMITIR_ESCRITA", raising=False)
    lote, registro, val = _validado()
    t = Transporte()
    lotes_antes = dict(registro.lotes)
    with pytest.raises(modo.EscritaBloqueada):
        en.enviar_de_verdade(lote=lote, aprovacao=_aprovacao(lote.envelope.impressao()),
                             validacao_lote_id=val.lote_id, transporte=t, registro=registro)
    assert t.corpos == [] and registro.lotes == lotes_antes


def test_so_a_variavel_de_ambiente_nao_destrava(monkeypatch):
    from volc_ads.gads import modo
    monkeypatch.setenv("FORGE_PERMITIR_ESCRITA", "1")
    lote, registro, val = _validado()
    t = Transporte()
    with pytest.raises(modo.EscritaBloqueada):
        en.enviar_de_verdade(lote=lote, aprovacao=_aprovacao(lote.envelope.impressao()),
                             validacao_lote_id=val.lote_id, transporte=t, registro=registro)
    assert t.corpos == []


@pytest.fixture
def destravado(monkeypatch):
    from volc_ads.gads import modo
    monkeypatch.setenv("FORGE_PERMITIR_ESCRITA", "1")
    with modo.destravar("teste hermético do envio real W14 com transporte falso"):
        yield


def test_envio_real_exige_aprovacao_do_mesmo_envelope(destravado):
    lote, registro, val = _validado()
    t = Transporte()
    with pytest.raises(en.AprovacaoInvalida):
        en.enviar_de_verdade(lote=lote, aprovacao=_aprovacao("f" * 64),
                             validacao_lote_id=val.lote_id, transporte=t, registro=registro)
    assert t.corpos == []


def test_envio_real_exige_validate_only_aceito(destravado):
    preparo, registro, *_ = _preparar()
    lote = preparo.lotes[0]
    t = Transporte()
    with pytest.raises(en.ValidacaoAusente):
        en.enviar_de_verdade(lote=lote, aprovacao=_aprovacao(lote.envelope.impressao()),
                             validacao_lote_id=999, transporte=t, registro=registro)
    assert t.corpos == []


def test_envio_real_completo_no_duble_e_no_maximo_uma_vez(destravado):
    lote, registro, val = _validado()
    t = Transporte()
    res = en.enviar_de_verdade(lote=lote, aprovacao=_aprovacao(lote.envelope.impressao()),
                               validacao_lote_id=val.lote_id, transporte=t, registro=registro)
    assert res.estado == "aceito" and [c["validateOnly"] for c in t.corpos] == [False]
    assert registro.lotes[res.lote_id]["aprovacao"]["aprovado_por"] == "Tarcisio"
    with pytest.raises(en.JaEnviado):
        en.enviar_de_verdade(lote=lote, aprovacao=_aprovacao(lote.envelope.impressao()),
                             validacao_lote_id=val.lote_id, transporte=t, registro=registro)
    assert len(t.corpos) == 1


def test_aprovacao_anonima_nao_existe():
    with pytest.raises(en.AprovacaoInvalida):
        en.AprovacaoDeEnvio(impressao="a" * 64, aprovado_por=" ",
                            aprovado_em=datetime.now(timezone.utc), referencia="x")


def test_reconciliar_fecha_o_mesmo_lote_sem_reenviar(destravado):
    lote, registro, val = _validado()
    t = Transporte()
    res = en.enviar_de_verdade(lote=lote, aprovacao=_aprovacao(lote.envelope.impressao()),
                               validacao_lote_id=val.lote_id, transporte=t, registro=registro)
    assert en.reconciliar(lote_id=res.lote_id, transporte=t, registro=registro) == "sucesso"
    assert len(t.corpos) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 7. Transporte HTTP (MockTransport — nenhuma rede)
# ═══════════════════════════════════════════════════════════════════════════


def _http(handler, token="tok"):
    return dmh.TransporteHttp(obter_token=lambda: token,
                              cliente=httpx.Client(transport=httpx.MockTransport(handler)))


def test_http_200_e_aceito_com_request_id_e_avisos():
    vistos = []

    def h(req):
        vistos.append(req)
        return httpx.Response(200, json={"requestId": "abc", "fieldWarnings": [{"fieldPath": "x"}]})

    r = _http(h).ingerir({"validateOnly": True, "events": []})
    assert r.aceito and r.request_id == "abc" and r.avisos == ({"fieldPath": "x"},)
    (req,) = vistos
    assert str(req.url) == "https://datamanager.googleapis.com/v1/events:ingest"
    assert req.headers["Authorization"] == "Bearer tok"
    assert json.loads(req.content)["validateOnly"] is True


def test_http_4xx_e_recusa_e_5xx_ou_rede_e_ignorancia():
    r = _http(lambda req: httpx.Response(400, json={"error": {"message": "bad"}})).ingerir({})
    assert r.respondeu and not r.aceito and r.erro == {"message": "bad"}
    r = _http(lambda req: httpx.Response(503, json={})).ingerir({})
    assert not r.respondeu

    def cai(req):
        raise httpx.ConnectError("sem rede", request=req)

    r = _http(cai).ingerir({})
    assert not r.respondeu and r.erro["tipo"] == "ConnectError"


def test_http_sem_token_nao_sai():
    chamadas = []
    t = _http(lambda req: chamadas.append(req) or httpx.Response(200, json={}), token="")
    with pytest.raises(portas.NaoSaiu):
        t.ingerir({})
    assert chamadas == []


def test_http_status_agrega_destinos():
    def h(req):
        assert req.url.params["requestId"] == "abc"
        return httpx.Response(200, json={"requestStatusPerDestination": [
            {"requestStatus": "SUCCESS"}, {"requestStatus": "FAILURE"}]})

    assert _http(h).status("abc").estado == "PARTIAL_SUCCESS"
    assert dmh.agregar(["SUCCESS"]) == "SUCCESS"
    assert dmh.agregar(["PROCESSING", "SUCCESS"]) == "PROCESSING"
    assert dmh.agregar(["FAILED"]) == "FAILURE"
    for estranho in ([], ["OUTRO"], [None]):
        with pytest.raises(dmh.StatusDesconhecido):
            dmh.agregar(estranho)


# ═══════════════════════════════════════════════════════════════════════════
# 8. Registro PostgREST (MockTransport)
# ═══════════════════════════════════════════════════════════════════════════


def _reg(handler):
    return rp.RegistroPostgrest(httpx.Client(base_url="https://lab.invalid/rest/v1",
                                             transport=httpx.MockTransport(handler)))


def test_registro_traduz_23505_em_ja_enviado():
    r = _reg(lambda req: httpx.Response(409, json={"code": "23505", "message": "duplicate"}))
    with pytest.raises(en.JaEnviado):
        r.abrir_lote(modo="real", impressao="a" * 64, customer_id=CONTA, login_customer_id=MCC,
                     operating_account_id=CONTA, product_destination_id=ACAO,
                     itens=[("volc-w14-" + "1" * 40, "c" * 64)], aprovacao={"x": 1},
                     validacao_lote_id=1)


def test_registro_abre_lote_pela_rpc_com_o_contrato_da_v25():
    vistos = []

    def h(req):
        vistos.append(req)
        return httpx.Response(200, json=42)

    l = _reg(h).abrir_lote(modo="validate_only", impressao="a" * 64, customer_id=CONTA,
                           login_customer_id=MCC, operating_account_id=CONTA,
                           product_destination_id=ACAO, itens=[("t", "v")])
    assert l.lote_id == 42 and l.estado == "em_voo"
    (req,) = vistos
    assert req.url.path == "/rest/v1/rpc/conversao_offline_abrir_lote"
    p = json.loads(req.content)["p"]
    assert p["itens"] == [{"transaction_id": "t", "valor_impressao": "v"}]
    assert p["aprovacao"] is None and p["validacao_lote_id"] is None


def test_registro_grava_decisoes_sem_descartar_duplicata():
    vistos = []
    preparo, *_ = _preparar()

    def h(req):
        vistos.append(req)
        return httpx.Response(201)

    _reg(h).registrar_decisoes(rodada="r", customer_id=CONTA, operating_account_id=CONTA,
                               product_destination_id=ACAO,
                               decisoes=[d.json() for d in preparo.decisoes])
    (req,) = vistos
    assert "ignore-duplicates" not in req.headers["Prefer"]
    linhas = json.loads(req.content)
    assert {l["estado"] for l in linhas} == {"elegivel"}
    assert all("Cj0KEQ" not in json.dumps(l) for l in linhas)


def test_registro_le_o_enviado_por_coorte_pela_view():
    vistos = []

    def h(req):
        vistos.append(req.url.params)
        return httpx.Response(200, json=[{"itens_vivos": 2, "soma_valor": 24.68}])

    out = _reg(h).envios_reais_por_coorte(operating_account_id=CONTA, product_destination_id=ACAO,
                                          coortes=[COORTE, COORTE])
    assert out[COORTE] == portas.EnvioDaCoorte(2, Decimal("24.68"))
    (q,) = vistos
    assert q["coorte_data"] == "eq.2026-10-10" and q["coorte_campanha"] == "eq.cup-bpc-loas"


def test_registro_le_envios_vivos_so_reais():
    def h(req):
        q = req.url.params
        assert q["modo"] == "eq.real" and q["estado"].startswith("in.(em_voo")
        return httpx.Response(200, json=[{"lote_id": 3, "estado": "aceito",
                                          "valor_impressao": "c" * 64, "transaction_id": "t1"}])

    out = _reg(h).envios_reais_vivos(operating_account_id=CONTA, product_destination_id=ACAO,
                                     transaction_ids=["t1", "t2"])
    assert out["t1"].lote_id == 3 and "t2" not in out


# ═══════════════════════════════════════════════════════════════════════════
# 9. Estrutura — o pacote não tem atalho para a rede nem para o valor fixo
# ═══════════════════════════════════════════════════════════════════════════


def test_dominio_e_aplicacao_nao_falam_com_a_rede():
    import inspect

    from app.trafego.conversao_offline.domain import evento, valor
    from app.trafego.conversao_offline.application import enviar, preparar, portas as p
    for mod in (evento, valor, enviar, preparar, p):
        fonte = inspect.getsource(mod)
        for proibido in ("import httpx", "import requests", "urllib", "googleapis.com"):
            assert proibido not in fonte, (mod.__name__, proibido)


def test_validar_no_google_escreve_validate_only_true_literal():
    import ast
    import inspect

    arvore = ast.parse(inspect.getsource(en.validar_no_google))
    valores = [k.value for k in ast.walk(arvore)
               if isinstance(k, ast.keyword) and k.arg == "validate_only"]
    assert valores and all(isinstance(v, ast.Constant) and v.value is True for v in valores)


# ═══════════════════════════════════════════════════════════════════════════
# 10. Revisão adversarial W14, ciclo 1 — cada achado vira um teste
# ═══════════════════════════════════════════════════════════════════════════


def _receita_coletada(dias, confirmado=None):
    return vl.ReceitaDatada(
        fonte="joinads", observacao_id=78, coorte=COORTE, receita=Decimal("12.00"), moeda="USD",
        coletado_em=datetime.combine(DIA + timedelta(days=dias), datetime.min.time(), timezone.utc),
        confirmado_em=None if confirmado is None else datetime.combine(
            DIA + timedelta(days=confirmado), datetime.min.time(), timezone.utc))


@pytest.mark.parametrize("hoje", [DIA + timedelta(days=4), DIA + timedelta(days=30)])
def test_nuvem2_receita_estavel_sem_versao_nova_amadurece_pelo_calendario(hoje):
    # O diário do W12 não cria versão quando o número não muda: `coletado_em`
    # fica em D+1 para sempre. Sem prova de releitura, vale a idade do dia.
    r = _calc(receita=_receita_coletada(1), hoje=hoje)
    assert isinstance(r, vl.ValorMedido)
    assert r.proveniencia["auditoria_da_maturidade"]["base"] == "calendario"


def test_confirmacao_registrada_da_a_base_da_observacao():
    r = _calc(receita=_receita_coletada(1, confirmado=4))
    assert r.proveniencia["auditoria_da_maturidade"]["base"] == "observacao_confirmada"


def test_b1_coletor_que_parou_cedo_com_confirmacao_conhecida_e_pulado():
    r = _calc(receita=_receita_coletada(1, confirmado=1))
    assert isinstance(r, vl.Pulo) and r.motivo == vl.PULO_OBSERVACAO_IMATURA


def test_confirmacao_nova_nao_muda_a_impressao_do_valor():
    a = _calc(receita=_receita_coletada(1, confirmado=4))
    b = _calc(receita=_receita_coletada(1, confirmado=9))
    c = _calc(receita=_receita_coletada(1))
    assert a.impressao() == b.impressao() == c.impressao()


def test_nuvem2_mais_cliques_que_sessoes_pula_a_coorte_inteira():
    # A sonda do revisor: 64,92 de receita, 2 sessões e 6 cliques mandavam 194,76.
    preparo, *_ = _preparar(cliques=[_clique(n) for n in range(1, 7)], sessoes=2)
    assert preparo.lotes == ()
    assert preparo.resumo()["pulados"] == {pr.PULO_CLIQUES_ACIMA_DAS_SESSOES: 6}


@pytest.mark.parametrize("receita, taxa, sessoes", [
    ("10.01", "1", 3), ("64.92", "1", 4), ("12.00", "5.4100", 7), ("0.07", "1", 3),
    ("99999.99", "5.4321", 11), ("1.00", "3.3333", 3), ("5.05", "1.0001", 5),
])
def test_nuvem2_soma_enviada_por_coorte_nunca_passa_da_receita(receita, taxa, sessoes):
    preparo, *_ = _preparar(cliques=[_clique(n) for n in range(1, sessoes + 1)],
                            linha=_receita(valor=receita), cot=_cot(taxa=taxa), sessoes=sessoes)
    soma = sum((d.valor.valor for d in preparo.decisoes if d.estado == ev.ELEGIVEL), Decimal(0))
    assert soma <= Decimal(receita) * Decimal(taxa)
    for d in preparo.decisoes:
        if d.estado == ev.ELEGIVEL:
            assert Decimal(d.valor.proveniencia["teto_da_coorte"]) <= Decimal(receita) * Decimal(taxa)


def test_nuvem2_coorte_ja_enviada_trava_mesmo_sem_o_clique_antigo_na_leitura(destravado):
    registro = RegistroMemoria()
    primeiro, *_ = _preparar(registro=registro, cliques=[_clique(1)])
    _real(registro, primeiro.lotes[0])
    # O clique 1 não volta nesta leitura (janela por data UTC, por exemplo).
    segundo, *_ = _preparar(registro=registro, rodada="rodada-2", cliques=[_clique(3)], sessoes=1)
    assert segundo.lotes == ()
    assert segundo.resumo()["pulados"] == {pr.PULO_COORTE_JA_RATEADA: 1}


def test_decisao_leva_a_coorte_para_o_registro():
    preparo, *_ = _preparar()
    j = preparo.decisoes[0].json()
    assert (j["coorte_data"], j["coorte_campanha"], j["coorte_dominio"]) == (
        "2026-10-10", "cup-bpc-loas", "creditoup.com.br")


def test_conhecido_ate_no_passado_limita_o_hoje():
    preparo, *_ = _preparar(conhecido_ate=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc))
    assert preparo.lotes == ()
    assert preparo.resumo()["pulados"] == {vl.PULO_RECEITA_IMATURA: 2}


def test_cotacao_anterior_sem_defasagem_declarada_e_pulada():
    r = _calc(cotacao=_cot(modo="anterior", defasagem=None))
    assert isinstance(r, vl.Pulo) and r.motivo == vl.PULO_DEFASAGEM_DESCONHECIDA


def test_cliques_sao_ordenados_pelo_instante_e_nao_pelo_texto():
    # Mesmo gclid em duas visitas: 10:30-03:00 é 13:30Z; 11:00Z é ANTES.
    tarde = _clique(1, gclid="Cj0KEQ-x", quando=datetime(2026, 10, 10, 10, 30, tzinfo=BRT))
    cedo = ev.CliqueObservado(visita_ref="visita-utc", clique=tarde.clique,
                              visitado_em=datetime(2026, 10, 10, 11, 0, tzinfo=timezone.utc),
                              coorte=COORTE, consentimento=dm.CONSENTIMENTO_CONCEDIDO)
    preparo, *_ = _preparar(cliques=[tarde, cedo])
    (eleita,) = [d for d in preparo.decisoes if d.estado == ev.ELEGIVEL]
    assert eleita.visita_ref == "visita-utc"


def _real(registro, lote, transporte=None):
    (val,) = en.validar_no_google(lotes=[lote], transporte=Transporte(), registro=registro)
    return en.enviar_de_verdade(lote=lote, aprovacao=_aprovacao(lote.envelope.impressao()),
                                validacao_lote_id=val.lote_id,
                                transporte=transporte or Transporte(), registro=registro)


def test_b2_clique_novo_de_coorte_ja_rateada_nao_vai(destravado):
    registro = RegistroMemoria()
    primeiro, *_ = _preparar(registro=registro)
    _real(registro, primeiro.lotes[0])
    segundo, *_ = _preparar(registro=registro, rodada="rodada-2",
                            cliques=[_clique(1), _clique(2), _clique(3)], sessoes=5)
    assert segundo.lotes == ()
    # O divisor mudou (4 → 5): os dois já enviados seriam ajuste; o novo, rateio duplo.
    assert segundo.resumo()["pulados"] == {ev.PULO_AJUSTE_NAO_AUTORIZADO: 2,
                                           pr.PULO_COORTE_JA_RATEADA: 1}


def test_envio_sem_resposta_prende_e_so_volta_com_o_mesmo_envelope(destravado):
    registro = RegistroMemoria()
    primeiro, *_ = _preparar(registro=registro)
    calado = Transporte(portas.RespostaDeIngestao(respondeu=False, aceito=False))
    res = _real(registro, primeiro.lotes[0], calado)
    assert res.estado == "sem_resposta"

    parado, *_ = _preparar(registro=registro, rodada="rodada-2")
    assert parado.lotes == () and parado.resumo()["pulados"] == {pr.PULO_ENVIO_INCERTO: 2}

    # Valor mudou: nem com retomar volta (seria ajuste às cegas).
    outro, *_ = _preparar(registro=registro, rodada="rodada-3", retomar_incertos=True,
                          linha=_receita(valor="20.00"))
    assert outro.lotes == ()

    retomado, *_ = _preparar(registro=registro, rodada="rodada-4", retomar_incertos=True)
    (lote,) = retomado.lotes
    assert lote.envelope.impressao() == primeiro.lotes[0].envelope.impressao()
    novo = _real(registro, lote)
    assert novo.estado == "aceito"
    assert registro.lotes[res.lote_id]["estado"] == "reenviado"


@pytest.mark.parametrize("falha, estado", [
    (portas.NaoSaiu("sem credencial"), "recusado"),
    (TimeoutError("caiu no meio"), "sem_resposta"),
])
def test_excecao_no_transporte_nunca_deixa_lote_em_voo(falha, estado):
    preparo, registro, *_ = _preparar()

    class Quebra(Transporte):
        def ingerir(self, corpo):
            raise falha

    with pytest.raises(type(falha)):
        en.validar_no_google(lotes=list(preparo.lotes), transporte=Quebra(), registro=registro)
    (lote,) = registro.lotes.values()
    assert lote["estado"] == estado


def test_resposta_do_google_vai_ao_registro_sem_o_gclid():
    preparo, registro, *_ = _preparar()
    t = Transporte(portas.RespostaDeIngestao(
        respondeu=True, aceito=False, status_http=400,
        erro={"message": "gclid Cj0KEQ-1 inválido", "detalhes": ["Cj0KEQ-2"]}))
    en.validar_no_google(lotes=list(preparo.lotes), transporte=t, registro=registro)
    (lote,) = registro.lotes.values()
    assert "Cj0KEQ" not in json.dumps(lote["resposta"])
    assert "[clique]" in json.dumps(lote["resposta"])


def test_acao_primaria_so_com_aceite_e_a_aprovacao_declara(destravado):
    with pytest.raises(de.AcaoOfflineInvalida):
        de.plano_para_acao_offline(_plano_lido(primaria_offline=True), ACAO)
    plano = de.plano_para_acao_offline(_plano_lido(primaria_offline=True), ACAO,
                                       permitir_acao_primaria=True)
    preparo, registro, *_ = _preparar(plano=plano)
    (lote,) = preparo.lotes
    assert lote.destino_primario is True
    (val,) = en.validar_no_google(lotes=[lote], transporte=Transporte(), registro=registro)
    t = Transporte()
    with pytest.raises(en.AprovacaoInvalida):
        en.enviar_de_verdade(lote=lote, aprovacao=_aprovacao(lote.envelope.impressao()),
                             validacao_lote_id=val.lote_id, transporte=t, registro=registro)
    assert t.corpos == []
    ok = en.AprovacaoDeEnvio(impressao=lote.envelope.impressao(), aprovado_por="Tarcisio",
                             aprovado_em=datetime(2026, 10, 15, 16, 0, tzinfo=BRT),
                             referencia="teste", destino_primario=True)
    assert en.enviar_de_verdade(lote=lote, aprovacao=ok, validacao_lote_id=val.lote_id,
                                transporte=t, registro=registro).estado == "aceito"


def test_aprovacao_sem_declarar_destino_primario_e_recusada():
    with pytest.raises(en.AprovacaoInvalida):
        en.AprovacaoDeEnvio(impressao="a" * 64, aprovado_por="Tarcisio",
                            aprovado_em=datetime.now(timezone.utc), referencia="x",
                            destino_primario=None)


@pytest.mark.parametrize("resp", [
    httpx.Response(302, headers={"Location": "https://accounts.google.com/"}),
    httpx.Response(200, text="<html>login</html>"),
    httpx.Response(200, json=["nao", "e", "objeto"]),
])
def test_http_fora_de_2xx_json_e_ignorancia_e_nao_aceite(resp):
    r = _http(lambda req: resp).ingerir({})
    assert not r.respondeu and not r.aceito


def test_http_credencial_que_explode_nao_sai():
    def explode():
        raise OSError("sem arquivo de credencial")

    chamadas = []
    t = dmh.TransporteHttp(obter_token=explode, cliente=httpx.Client(
        transport=httpx.MockTransport(lambda req: chamadas.append(req) or httpx.Response(200))))
    with pytest.raises(portas.NaoSaiu):
        t.ingerir({})
    assert chamadas == []


def test_reconciliar_usa_o_request_id_do_proprio_lote(destravado):
    lote, registro, val = _validado()
    vistos = []

    class T(Transporte):
        def status(self, request_id):
            vistos.append(request_id)
            return super().status(request_id)

    t = T()
    res = en.enviar_de_verdade(lote=lote, aprovacao=_aprovacao(lote.envelope.impressao()),
                               validacao_lote_id=val.lote_id, transporte=t, registro=registro)
    en.reconciliar(lote_id=res.lote_id, transporte=t, registro=registro)
    assert vistos == ["req-w14"]
    with pytest.raises(ValueError):
        en.reconciliar(lote_id=val.lote_id, transporte=t, registro=registro)
