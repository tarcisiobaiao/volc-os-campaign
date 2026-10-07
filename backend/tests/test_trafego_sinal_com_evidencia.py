"""`fontes_de_sinal_observadas` — o campo que transformava alegação em verde.

## O defeito que este arquivo existe para impedir de voltar

Até 02/09/2026, `prontidao.avaliar(fontes_de_sinal_observadas=[...])` aceitava
**qualquer lista não vazia de strings** e a tratava como sinal COMPROVADO:

    fontes = list(fontes_de_sinal_observadas or ())     # prontidao.py:482 (antes)
    ...
    if fontes:
        sinal = PRONTO

A string `"google_tag"` — que nomeia uma CAPACIDADE, não um evento — bastava
para `conversion_signal_status=PRONTO` e, com a meta resolvida, para
`measurement_readiness=PRONTO`. O comentário do próprio campo admitia a coisa:
"quem o passa está AFIRMANDO ter observado algo que este módulo não tem como
conferir". Era a única porta do módulo em que uma afirmação virava veredito, e
ela contradizia a régua que o mesmo módulo aplica ao plano — `Frescor.comprovado`
exige leitura concluída, contagem positiva **e** recência de 30 dias.

Zero chamadores de produção passavam o campo (medido: as quatro chamadas de
`pr.avaliar` em `backend/app/routers/trafego.py` — `:2782`, `:3146`, `:3714`,
`:3780` — não o passam). O risco era o dia em que alguém passasse.

## O par que este arquivo prova

Os dois lados, sempre. Um teste que só provasse a recusa passaria com qualquer
implementação que recusasse tudo — inclusive uma que nunca deixasse nada abrir,
que é o falso vermelho equivalente. Aqui: **alegação sem evidência não vira
PRONTO por via nenhuma**, e **evidência real e recente vira**.
"""
from __future__ import annotations

import dataclasses
import io
import os
import pathlib
import sys

import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.trafego import plano_mensuracao as pm  # noqa: E402
from app.trafego import prontidao as pr  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parents[2]

# `observado_em` é o HOJE no fuso da CONTA — ver `metas_efetivas.hoje_na_conta`.
HOJE = "2026-09-02"


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures — um plano completo, para provar que a evidência velha não o apaga
# ═══════════════════════════════════════════════════════════════════════════


def _acao():
    return pm.AcaoDeConversao(
        id="7466919994",
        resource_name="customers/5478096539/conversionActions/7466919994",
        owner_customer_id="5478096539",
        nome="Compra no site", categoria="PURCHASE", origem="WEBSITE",
        tipo="WEBPAGE", status="ENABLED", primaria=True,
        incluida_em_metricas=True)


def _meta_efetiva():
    return pm.MetaEfetiva(
        nivel=pm.NIVEL_CUSTOMER,
        nivel_estado=pm.COM_DADOS,
        metas_da_conta=(pm.Meta(categoria="PURCHASE", origem="WEBSITE",
                                biddable=True),),
        metas_da_conta_estado=pm.COM_DADOS,
        metas_da_campanha=(),
        metas_da_campanha_estado=pm.INELEGIVEL)


def _plano_com_sinal_provado():
    """Plano em que o FRESCOR prova o sinal — sem nenhuma afirmação de fora."""
    return pm.montar(
        customer_id="5478096539", login_customer_id="6016739364",
        meta_efetiva=_meta_efetiva(),
        acoes=(_acao(),), acoes_estado=pm.COM_DADOS,
        frescor=pm.Frescor(estado=pm.COM_DADOS,
                           ultima_conversao_em="2026-08-31",
                           dias_desde_a_ultima=2, conversoes_na_janela=1.0,
                           conversion_action_id="7466919994"),
        marcacao=pm.InventarioDeMarcacao(
            estado=pm.COM_DADOS, auto_tagging=True,
            conversion_tracking_id="17862729897",
            conversion_tracking_owner_id="5478096539",
            aceitou_termos_de_dados=True,
            acoes_com_tag=("7466919994",)))


def _plano_que_leu_e_nao_achou():
    """A leitura REAL consultou a janela e concluiu que não chegou conversão.

    `vazio_confirmado` é o fato mais caro deste domínio: a ação existe, a janela
    FOI consultada, e nada chegou. Diferente de `nao_coletado` (ninguém
    perguntou) e de `falhou` (perguntou e quebrou).
    """
    return pm.montar(
        customer_id="5478096539", login_customer_id="6016739364",
        meta_efetiva=_meta_efetiva(),
        acoes=(_acao(),), acoes_estado=pm.COM_DADOS,
        frescor=pm.Frescor(estado=pm.VAZIO_CONFIRMADO,
                           conversoes_na_janela=0.0,
                           conversion_action_id="7466919994"),
        marcacao=pm.InventarioDeMarcacao(
            estado=pm.COM_DADOS, auto_tagging=True,
            conversion_tracking_id="17862729897",
            conversion_tracking_owner_id="5478096539",
            aceitou_termos_de_dados=True,
            acoes_com_tag=("7466919994",)))


def _evidencia(**troca):
    campos = dict(fonte="tag do Google no site",
                  ultima_conversao_em="2026-08-31",
                  conversoes_observadas=3,
                  observado_em=HOJE)
    campos.update(troca)
    return pr.SinalObservado(**campos)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O LADO VERMELHO — alegação sem evidência não vira PRONTO por via nenhuma
# ═══════════════════════════════════════════════════════════════════════════


def test_lista_de_strings_alegada_e_recusada_em_voz_alta():
    """`["google_tag"]` era o caso que abria o portão. Agora ele levanta.

    ⚠️ EXCEÇÃO, e não descarte silencioso. Ignorar a alegação em silêncio
    produziria a segunda mentira — o chamador acreditaria que sua fonte entrou
    no veredito, e o veredito diria o contrário sem dizer por quê.
    """
    with pytest.raises(pr.AfirmacaoSemEvidencia) as exc:
        pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "1"}},
                   fontes_de_sinal_observadas=["google_tag"])
    assert "AFIRMAÇÃO" in str(exc.value)
    # A recusa nomeia o que precisa ser trazido, senão ela é só um "não".
    for campo in ("ultima_conversao_em", "conversoes_observadas",
                  "observado_em"):
        assert campo in str(exc.value)


def test_a_alegacao_recusada_nao_produz_pronto_por_nenhuma_outra_via():
    """A recusa não pode ser contornada removendo a lista.

    ⚠️ Este é o assert que fecha o buraco de verdade: sem a evidência, a MESMA
    conta que antes saía `PRONTO` com `["google_tag"]` sai `NAO_PRONTO`.
    """
    r = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "1"}},
                   fontes_de_sinal_observadas=None)
    assert r.conversion_signal_status == pr.NAO_PRONTO
    assert r.signal_sources == ()
    assert r.measurement_readiness != pr.PRONTO
    assert r.smart_bidding_eligible is False


@pytest.mark.parametrize("troca, pedaco", [
    ({"conversoes_observadas": 0}, "Zero medido"),
    ({"conversoes_observadas": -2}, "Zero medido"),
    ({"conversoes_observadas": float("inf")}, "Zero medido"),
    ({"conversoes_observadas": float("nan")}, "Zero medido"),
    ({"conversoes_observadas": "muitas"}, "não numérica"),
    ({"ultima_conversao_em": ""}, "data de última conversão legível"),
    ({"ultima_conversao_em": "ontem"}, "data de última conversão legível"),
    ({"observado_em": ""}, "observado_em"),
    ({"fonte": "   "}, "sem nome"),
    ({"ultima_conversao_em": "2026-09-30"}, "no futuro"),
])
def test_cada_pedaco_que_falta_derruba_a_evidencia_com_a_razao_nomeada(
        troca, pedaco):
    """Peça por peça, e não tudo de uma vez.

    Um teste único que tirasse tudo junto provaria o caso fácil. O que decide é
    que faltando UMA coisa já não há evidência — e que a razão é a certa.
    """
    with pytest.raises(pr.AfirmacaoSemEvidencia) as exc:
        _evidencia(**troca)
    assert pedaco in str(exc.value)


def test_dicionario_incompleto_e_recusado_nomeando_o_que_falta():
    with pytest.raises(pr.AfirmacaoSemEvidencia) as exc:
        pr.evidencia_de_sinal({"fonte": "importação GA4",
                               "conversoes_observadas": 9})
    assert "ultima_conversao_em" in str(exc.value)
    assert "observado_em" in str(exc.value)


def test_os_dias_sao_calculados_e_nao_recebidos():
    """Se o chamador informasse os dias, ele afirmaria recência sem prova.

    ⚠️ É o defeito original com outra roupa: o número que decide a janela não
    pode vir de quem quer passar pela janela.
    """
    campos = {f.name for f in dataclasses.fields(pr.SinalObservado)}
    assert "dias_desde_a_ultima" not in campos
    with pytest.raises(TypeError):
        pr.SinalObservado(fonte="x", ultima_conversao_em="2026-08-31",
                          conversoes_observadas=1, observado_em=HOJE,
                          dias_desde_a_ultima=0)  # type: ignore[call-arg]
    assert _evidencia().dias_desde_a_ultima == 2


def test_evidencia_fora_da_janela_nao_abre_o_portao_e_diz_por_que():
    """Observação VELHA é observação — e não prova que o sinal chega HOJE.

    ⚠️ E ela não levanta no construtor: uma conversão de 2019 é um fato, e
    apagar o fato seria a outra metade do erro. Ela desce para `signal_paths`.
    """
    velha = _evidencia(ultima_conversao_em="2019-01-05")
    assert velha.comprovado is False
    assert velha.dias_desde_a_ultima > pm.JANELA_DE_RECENCIA_DIAS

    r = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "1"}},
                   fontes_de_sinal_observadas=[velha])
    assert r.conversion_signal_status == pr.NAO_PRONTO
    assert r.signal_sources == ()
    assert r.measurement_readiness != pr.PRONTO
    assert any("2019-01-05" in c for c in r.signal_paths)
    assert any("fora da janela" in b for b in r.activation_blockers)
    # ⚠️ E o texto NÃO diz "nenhuma conversão observada": ela foi observada, e
    # parou. As duas frases pedem conversas diferentes.
    assert "FORA da janela" in r.notas["conversion_signal"]
    assert "NENHUMA conversão observada" not in r.notas["conversion_signal"]


def test_evidencia_velha_nao_suprime_mais_a_derivacao_do_plano():
    """Antes, qualquer lista não vazia vencia o plano. Agora só a comprovada.

    ⚠️ Com a regra antiga, uma afirmação velha (ou falsa) APAGAVA a leitura
    real do plano — a pior forma do defeito, porque ela substituía observação
    por alegação em vez de apenas somar-se a ela.
    """
    plano = _plano_com_sinal_provado()
    assert plano.frescor.comprovado is True

    r = pr.avaliar(recibo_registrado=True, metas_da_conta=None,
                   plano_de_mensuracao=plano,
                   fontes_de_sinal_observadas=[
                       _evidencia(ultima_conversao_em="2019-01-05")])
    assert r.conversion_signal_status == pr.PRONTO
    assert any("conversão observada na conta" in f for f in r.signal_sources)


# ═══════════════════════════════════════════════════════════════════════════
# 2. O LADO VERDE — evidência real e recente CONTINUA abrindo o portão
# ═══════════════════════════════════════════════════════════════════════════


def test_evidencia_real_e_recente_produz_pronto():
    """Sem este lado, "está bloqueado" voltaria a ser infalsificável."""
    r = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "1"}},
                   fontes_de_sinal_observadas=[_evidencia()],
                   data_manager_operante=False)
    assert r.conversion_signal_status == pr.PRONTO
    assert r.data_manager_status == pr.NAO_PRONTO
    # A string de saída carrega o que a sustenta, em vez de um rótulo solto.
    assert len(r.signal_sources) == 1
    frase = r.signal_sources[0]
    assert "tag do Google no site" in frase
    assert "2026-08-31" in frase
    assert "3 conversão(ões)" in frase
    assert "há 2 dia(s)" in frase


def test_o_dicionario_equivalente_tambem_serve():
    """Quem vem de JSON não precisa importar a dataclass para ser honesto."""
    r = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "1"}},
                   fontes_de_sinal_observadas=[{
                       "fonte": "upload offline",
                       "ultima_conversao_em": "2026-09-01",
                       "conversoes_observadas": 12,
                       "observado_em": HOJE}])
    assert r.conversion_signal_status == pr.PRONTO
    assert "upload offline" in r.signal_sources[0]


def test_a_borda_da_janela_e_inclusiva_e_o_dia_seguinte_nao():
    """O par na borda. Sem ele, "30 dias" poderia ser 29 ou 31 sem ninguém ver."""
    na_borda = _evidencia(ultima_conversao_em="2026-08-03")   # 30 dias
    passou = _evidencia(ultima_conversao_em="2026-08-02")     # 31 dias
    assert na_borda.dias_desde_a_ultima == pm.JANELA_DE_RECENCIA_DIAS
    assert na_borda.comprovado is True
    assert passou.dias_desde_a_ultima == pm.JANELA_DE_RECENCIA_DIAS + 1
    assert passou.comprovado is False


def test_hoje_mesmo_conta_e_nao_vira_um_dia_atras():
    """`observado_em == ultima_conversao_em` é zero dia, não um."""
    e = _evidencia(ultima_conversao_em=HOJE)
    assert e.dias_desde_a_ultima == 0
    assert e.comprovado is True


# ═══════════════════════════════════════════════════════════════════════════
# 3. O CONTRATO DE SAÍDA e a ausência de produtor
# ═══════════════════════════════════════════════════════════════════════════


def test_signal_sources_continua_sendo_lista_de_strings_no_json():
    """A tela lê `signal_sources: string[]` (`src/types/trafego.ts:588`).

    Trocar a prova de lugar não pode trocar o contrato de quem consome.
    """
    j = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "1"}},
                   fontes_de_sinal_observadas=[_evidencia()]).para_json()
    assert isinstance(j["signal_sources"], list)
    assert all(isinstance(f, str) for f in j["signal_sources"])


def test_nenhum_modulo_de_producao_afirma_fonte_de_sinal():
    """Prova negativa por busca: o campo continua sem produtor.

    ⚠️ Isto não é decoração. Enquanto ninguém o passa, o conserto acima é
    preventivo; no dia em que alguém passar, este teste é o que obriga a
    passagem a trazer evidência — e falha se alguém religar a alegação nua.
    """
    ofensores = []
    for base in (RAIZ / "backend" / "app", RAIZ / "scripts"):
        if not base.exists():
            continue
        for caminho in base.rglob("*.py"):
            texto = io.open(caminho, encoding="utf-8").read()
            for n, linha in enumerate(texto.splitlines(), 1):
                if "fontes_de_sinal_observadas=" not in linha:
                    continue
                # A definição do parâmetro e a derivação do plano não são
                # afirmações de chamador.
                if caminho.name in ("prontidao.py", "perfil_de_mensuracao.py"):
                    continue
                ofensores.append(f"{caminho}:{n}")
    assert ofensores == [], (
        "alguém passou a afirmar fonte de sinal: " + ", ".join(ofensores)
        + ". Se a passagem for legítima, ela precisa trazer `SinalObservado` "
        "com data, contagem e `observado_em` — e este teste precisa passar a "
        "conferir a evidência, não a proibir a chamada.")


# ═══════════════════════════════════════════════════════════════════════════
# 4. A DIREÇÃO QUE FALTAVA — alegação FRESCA contra leitura que CONCLUIU zero
#
# A revisão adversarial reproduziu isto e estava certa: exigir forma da
# evidência fecha a porta da frente, e deixa a de trás aberta. Uma
# `SinalObservado` inteiramente inventada em processo — data de hoje, contagem
# 1, tudo bem-formado — vencia uma leitura real que tinha visto ZERO, porque a
# precedência era "se o chamador trouxe algo, o plano nem é consultado".
#
# `SinalObservado` confere FORMA, não PROCEDÊNCIA. Nada nela pergunta à conta.
# ═══════════════════════════════════════════════════════════════════════════


def test_alegacao_fresca_nao_derruba_leitura_que_consultou_e_nao_achou():
    """O caso exato da refutação: plano com vazio_confirmado + alegação forjada."""
    forjada = _evidencia(fonte="eu digo que vi",
                         ultima_conversao_em=HOJE,
                         conversoes_observadas=1)
    r = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "1"}},
                   fontes_de_sinal_observadas=[forjada],
                   plano_de_mensuracao=_plano_que_leu_e_nao_achou())
    d = r.para_json() if hasattr(r, "para_json") else r

    # O desfecho honesto de uma contradição não é escolher a alegação.
    assert d["conversion_signal_status"] != "PRONTO"
    assert d["conversion_signal_status"] == "INDETERMINADO"
    assert d["measurement_readiness"] != "PRONTO"
    assert d["smart_bidding_eligible"] is not True


def test_a_contradicao_e_dita_em_voz_alta_e_nao_resolvida_em_silencio():
    """Escolher um dos lados calado seria a segunda mentira."""
    forjada = _evidencia(fonte="eu digo que vi",
                         ultima_conversao_em=HOJE,
                         conversoes_observadas=1)
    r = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "1"}},
                   fontes_de_sinal_observadas=[forjada],
                   plano_de_mensuracao=_plano_que_leu_e_nao_achou())
    d = r.para_json() if hasattr(r, "para_json") else r
    texto = json.dumps(d, ensure_ascii=False)
    assert "CONTRADI" in texto.upper()
    # as duas versões ficam na mesa: a da conta e a de quem alegou
    assert "vazio confirmado" in texto
    assert "eu digo que vi" in texto


def test_sem_leitura_conclusiva_a_evidencia_continua_valendo():
    """A guarda é contra DERRUBAR medição, não contra PREENCHER vazio.

    Sem plano nenhum, ninguém consultou a conta — e aí a evidência bem-formada
    do chamador continua sendo a melhor coisa que existe.
    """
    r = pr.avaliar(recibo_registrado=True,
                   metas_da_conta={"primaria": {"id": "1"}},
                   fontes_de_sinal_observadas=[_evidencia()])
    d = r.para_json() if hasattr(r, "para_json") else r
    assert d["conversion_signal_status"] == "PRONTO"


def test_leitura_que_NAO_concluiu_nao_bloqueia_a_evidencia():
    """`nao_coletado` e `falhou` não são conclusão — não há o que contradizer."""
    for estado in (pm.NAO_COLETADO, pm.FALHOU):
        plano = pm.montar(
            customer_id="5478096539", login_customer_id="6016739364",
            meta_efetiva=_meta_efetiva(),
            acoes=(_acao(),), acoes_estado=pm.COM_DADOS,
            frescor=pm.Frescor(estado=estado, causa="ninguém perguntou"),
            marcacao=pm.InventarioDeMarcacao(
                estado=pm.COM_DADOS, auto_tagging=True,
                conversion_tracking_id="17862729897",
                conversion_tracking_owner_id="5478096539",
                aceitou_termos_de_dados=True,
                acoes_com_tag=("7466919994",)))
        r = pr.avaliar(recibo_registrado=True,
                       metas_da_conta={"primaria": {"id": "1"}},
                       fontes_de_sinal_observadas=[_evidencia()],
                       plano_de_mensuracao=plano)
        d = r.para_json() if hasattr(r, "para_json") else r
        assert d["conversion_signal_status"] == "PRONTO", estado
