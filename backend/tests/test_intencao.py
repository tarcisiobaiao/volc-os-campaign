"""A intenção e a regra de otimização — contra o SQL da v10_02, não contra si.

As doze declarações obrigatórias de uma regra existem porque cada uma impede um
acidente conhecido de automação de mídia. As provas aqui exercitam justamente as
recusas: uma regra que aceita tudo não protege nada, e a prova de que ela recusa
é mais valiosa que a prova de que ela aceita.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.trafego import intencao as it  # noqa: E402
from app.trafego import plataforma as plat  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parents[2]
V10_02 = RAIZ / "supabase" / "migrations" / "v10_02_autogestao.sql"

AGORA = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)

_REGRA = dict(
    chave="pausar_termo_sem_conversao", versao=1,
    titulo="Pausar termo sem conversão", objetivo="eficiencia",
    plataformas=("GOOGLE_ADS",), canais=("SEARCH",),
    janela_minima_dias=7, atraso_conversao_dias=3, frescor_maximo_horas=24,
    dados_obrigatorios=("cliques", "custo_micros", "conversoes"),
    cooldown_horas=48, confianca_minima=0.8,
    condicao_rollback="cpa subiu mais de 30 por cento em 72h",
    rollback_janela_horas=72, responsavel="tarcisio",
    fonte="legado_n8n:pausa_termo", declarada_por="tarcisio",
    amostra_minima_cliques=30, limite_alteracao_pct=20.0,
)


def regra(**mudanca):
    return it.RegraDeOtimizacao(**{**_REGRA, **mudanca})


# ═══════════════════════════════════════════════════════════════════════════
# 1. O VOCABULÁRIO BATE COM O DA MIGRATION
# ═══════════════════════════════════════════════════════════════════════════


def test_plataformas_sao_as_do_manifesto():
    assert it.PLATAFORMAS == plat.PLATAFORMAS


def test_canais_batem_com_a_check_da_regra():
    sql = V10_02.read_text(encoding="utf-8")
    trecho = sql[sql.index("CONSTRAINT trafego_regra_canais_validos"):]
    trecho = trecho[:trecho.index("]::text[])")]
    do_sql = set(re.findall(r"'([A-Z_*]+)'", trecho))
    assert do_sql == set(it.CANAIS)


def test_t2_nao_existe_nem_aqui_nem_na_check():
    """⚠️ A máquina aplicando sozinha não está aprovada (ADR-11), e a ausência é
    o registro dessa decisão — não um valor recusado por engano.

    Se alguém alargar o vocabulário num dos dois lados, este teste quebra antes
    de a automação ganhar autorização para aplicar sozinha.
    """
    sql = V10_02.read_text(encoding="utf-8")
    trecho = sql[sql.index("CONSTRAINT trafego_regra_nivel_conhecido"):]
    trecho = trecho[:trecho.index("),")]
    do_sql = set(re.findall(r"'(T\d)'", trecho))
    assert do_sql == set(it.NIVEIS_DE_AUTONOMIA) == {"T0", "T1"}
    with pytest.raises(it.ErroDeIntencao, match="T2"):
        regra(nivel_autonomia="T2")


def test_toda_medida_exigivel_tem_coluna_na_evidencia():
    """Uma regra que exige o que ninguém mede nunca dispara, e o sintoma é
    silêncio — a regra simplesmente não roda, e ninguém descobre por quê."""
    sql = V10_02.read_text(encoding="utf-8")
    tabela = sql[sql.index("CREATE TABLE public.trafego_evidencia"):]
    tabela = tabela[:tabela.index("CREATE INDEX trafego_evidencia_campanha_ix")]
    for medida in it.MEDIDAS:
        assert re.search(rf"^\s+{medida}\s", tabela, re.MULTILINE), medida


# ═══════════════════════════════════════════════════════════════════════════
# 2. A INTENÇÃO
# ═══════════════════════════════════════════════════════════════════════════

_INTENCAO = dict(intencao_id="int-1", plataforma="GOOGLE_ADS",
                 conta_externa="8017851692", objetivo="leads",
                 rotulo="FGTS agosto", declarada_por="tarcisio",
                 declarada_com_base_em="pauta 812 · volume 4.4k/mês")


def test_intencao_completa_passa():
    i = it.IntencaoDeCampanha(**_INTENCAO)
    assert i.campaign_lineage_id is None  # a linhagem pode vir depois


def test_intencao_sem_base_declarada_e_recusada():
    """Intenção sem base é palpite com carimbo de decisão — e é exatamente ela
    que ninguém consegue auditar seis meses depois."""
    with pytest.raises(it.ErroDeIntencao, match="palpite"):
        it.IntencaoDeCampanha(**{**_INTENCAO, "declarada_com_base_em": "  "})


def test_teto_de_verba_sem_moeda_e_recusado():
    """R$ 50 e US$ 50 não são o mesmo teto, e o motor compararia o número com um
    limite em outra unidade."""
    with pytest.raises(it.ErroDeIntencao, match="moeda"):
        it.IntencaoDeCampanha(**{**_INTENCAO,
                                 "verba_diaria_teto_micros": 50_000_000})


def test_teto_com_moeda_passa():
    i = it.IntencaoDeCampanha(**{**_INTENCAO, "verba_diaria_teto_micros": 50_000_000,
                                 "moeda": "BRL"})
    assert i.moeda == "BRL"


def test_plataforma_inventada_e_recusada():
    with pytest.raises(it.ErroDeIntencao, match="plataforma"):
        it.IntencaoDeCampanha(**{**_INTENCAO, "plataforma": "TIKTOK_ADS"})


# ═══════════════════════════════════════════════════════════════════════════
# 3. AS DUAS RECUSAS MAIS CARAS DA REGRA
# ═══════════════════════════════════════════════════════════════════════════


def test_regra_sem_amostra_minima_e_recusada():
    """Sem piso, a regra dispara sobre 1 clique e chama isso de diagnóstico — a
    forma mais comum de uma automação de mídia matar uma campanha nova."""
    with pytest.raises(it.ErroDeIntencao, match="amostra mínima"):
        regra(amostra_minima_cliques=None, amostra_minima_impressoes=None,
              amostra_minima_conversoes=None)


def test_regra_sem_limite_de_alteracao_e_recusada():
    """Sem limite, um erro de sinal multiplica o orçamento em vez de dividi-lo,
    e ninguém percebe até a fatura."""
    with pytest.raises(it.ErroDeIntencao, match="limite de alteração"):
        regra(limite_alteracao_pct=None, limite_alteracao_absoluto_micros=None)


def test_qualquer_uma_das_amostras_basta():
    assert regra(amostra_minima_cliques=None,
                 amostra_minima_impressoes=1000).amostra_minima_impressoes == 1000


def test_teto_sem_moeda_e_recusado():
    with pytest.raises(it.ErroDeIntencao, match="par indivisível"):
        regra(teto_orcamento_micros=100_000_000)


@pytest.mark.parametrize("campo", ["responsavel", "condicao_rollback", "fonte"])
def test_declaracao_obrigatoria_vazia_e_recusada(campo):
    """Regra sem dono não tem quem a aposente quando ela passa a errar — e uma
    regra que erra em silêncio gasta verba todo dia."""
    with pytest.raises(it.ErroDeIntencao):
        regra(**{campo: "  "})


def test_dado_obrigatorio_sem_coluna_e_recusado():
    with pytest.raises(it.ErroDeIntencao, match="nunca dispara"):
        regra(dados_obrigatorios=("roas_incremental",))


def test_confianca_fora_da_faixa_e_recusada():
    with pytest.raises(it.ErroDeIntencao, match="confiança"):
        regra(confianca_minima=0)
    with pytest.raises(it.ErroDeIntencao, match="confiança"):
        regra(confianca_minima=1.5)


def test_coringa_de_canal_vale_para_qualquer_canal():
    r = regra(canais=("*",))
    assert r.aplica_a("GOOGLE_ADS", "PERFORMANCE_MAX")
    assert r.aplica_a("GOOGLE_ADS", None)


def test_canal_desconhecido_nao_casa_com_regra_especifica():
    """Canal `None` — espelho que não trouxe o canal — só casa com o coringa.
    Deixá-lo casar seria aplicar uma regra de Search a algo que talvez seja PMax.
    """
    assert regra().aplica_a("GOOGLE_ADS", "SEARCH")
    assert not regra().aplica_a("GOOGLE_ADS", None)
    assert not regra().aplica_a("META_ADS", "SEARCH")


# ═══════════════════════════════════════════════════════════════════════════
# 4. O CONTRATO COM O AGENTE G
# ═══════════════════════════════════════════════════════════════════════════


def _canonica(**mudanca):
    base = {k: (list(v) if isinstance(v, tuple) else v)
            for k, v in _REGRA.items()}
    base.update(mudanca)
    return base


def test_json_canonico_vira_regra():
    r = it.validar_regra_canonica(_canonica())
    assert r.chave == "pausar_termo_sem_conversao" and r.canais == ("SEARCH",)


def test_campo_desconhecido_e_recusado_e_nao_ignorado():
    """⚠️ Ignorar seria pior que recusar: uma regra migrada do n8n com
    `max_budget` (em vez de `teto_orcamento_micros`) passaria calada e rodaria
    SEM TETO — o oposto do que o arquivo pretendia dizer."""
    with pytest.raises(it.ErroDeIntencao, match="max_budget"):
        it.validar_regra_canonica(_canonica(max_budget=100))


def test_campo_obrigatorio_ausente_e_recusado():
    bruta = _canonica()
    del bruta["responsavel"]
    with pytest.raises(it.ErroDeIntencao, match="responsavel"):
        it.validar_regra_canonica(bruta)


# ═══════════════════════════════════════════════════════════════════════════
# 5. SUFICIÊNCIA DE EVIDÊNCIA — as cinco perguntas
# ═══════════════════════════════════════════════════════════════════════════

_EVIDENCIA = dict(janela_inicio="2026-08-15", janela_fim="2026-08-22",
                  colhida_em="2026-08-26T09:00:00Z",
                  cliques=120, custo_micros=45_000_000, conversoes=3)


def avaliar(**mudanca):
    return it.avaliar_suficiencia({**_EVIDENCIA, **mudanca}, regra(), agora=AGORA)


def test_evidencia_completa_e_suficiente():
    assert avaliar().suficiente


def test_medida_ausente_e_insuficiente_e_diz_qual():
    """Ausência não vira zero: zero seria uma afirmação que ninguém observou."""
    s = avaliar(conversoes=None)
    assert not s.suficiente and s.faltantes == ("conversoes",)
    assert "não trouxe conversoes" in s.motivo


def test_zero_medido_e_diferente_de_nao_medido():
    """`conversoes = 0` é um fato: a campanha rodou e não converteu. É
    exatamente a evidência que a regra existe para agir sobre."""
    assert avaliar(conversoes=0).suficiente


def test_janela_curta_e_insuficiente():
    s = avaliar(janela_inicio="2026-08-21", janela_fim="2026-08-22")
    assert not s.suficiente and s.faltantes == ("janela",)


def test_atraso_de_conversao_ainda_nao_cumprido_e_insuficiente():
    """Conversão que ainda vai chegar não é conversão que não houve — sem o
    atraso, toda campanha nova parece um fracasso."""
    s = avaliar(janela_fim="2026-08-25", janela_inicio="2026-08-15",
                colhida_em="2026-08-26T09:00:00Z")
    assert not s.suficiente and s.faltantes == ("atraso_conversao",)


def test_amostra_abaixo_do_piso_e_insuficiente():
    s = avaliar(cliques=4)
    assert not s.suficiente and s.faltantes == ("cliques",)
    assert "abaixo da amostra mínima" in s.motivo


def test_evidencia_velha_e_insuficiente():
    """Decidir hoje com dado de três semanas atrás é decidir sobre um mundo que
    não existe mais."""
    # A janela e antiga o bastante para o atraso de conversao ja estar cumprido:
    # o que reprova aqui e SO o frescor. Sem esse cuidado o teste passaria pelo
    # ramo errado e a guarda de frescor nunca teria sido exercitada.
    s = it.avaliar_suficiencia(
        {**_EVIDENCIA, "janela_inicio": "2026-07-20",
         "janela_fim": "2026-07-27", "colhida_em": "2026-08-01T09:00:00Z"},
        regra(), agora=AGORA)
    assert not s.suficiente and s.faltantes == ("frescor",)


def test_evidencia_sem_carimbo_e_insuficiente():
    s = avaliar(colhida_em=None)
    assert not s.suficiente and s.faltantes == ("colhida_em",)


def test_agora_e_parametro_e_nao_relogio_escondido():
    """Uma função que lê o relógio por conta própria não é testável, e a única
    forma de exercitar o ramo do atraso de conversão seria esperar três dias."""
    assert "agora" in it.avaliar_suficiencia.__code__.co_varnames


# ═══════════════════════════════════════════════════════════════════════════
# 6. O PRÓXIMO PASSO DA PROPOSTA
# ═══════════════════════════════════════════════════════════════════════════

_PROPOSTA = {"estado": "aguardando_aprovacao",
             "expira_em": "2026-08-27T12:00:00Z"}


def passo(**mudanca):
    return it.proximo_passo_da_proposta({**_PROPOSTA, **mudanca}, agora=AGORA)


def test_aplicacao_em_voo_manda_verificar_e_nunca_reaplicar():
    """Mesmo ramo do lote, mesma razão: um orçamento dobrado duas vezes é um
    orçamento quadruplicado."""
    assert passo(aplicacao_desfecho="em_voo", aprovacao_decisao="aprovada",
                 estado="aprovada") == "verificar"


def test_proposta_nova_aguarda_humano():
    assert passo() == "aguardar_humano"


def test_aprovada_e_no_prazo_pode_aplicar():
    assert passo(aprovacao_decisao="aprovada", estado="aprovada") == "aplicar"


def test_vencida_expira_antes_de_aplicar():
    """A ordem dos ramos importa: uma proposta aprovada E vencida tem de expirar,
    não aplicar — o `antes` que o humano viu já não é o `antes` da conta."""
    assert passo(aprovacao_decisao="aprovada",
                 expira_em="2026-08-25T12:00:00Z") == "expirar"


def test_aplicada_vira_acompanhamento():
    assert passo(estado="aplicada") == "acompanhar"


def test_recusada_nao_pede_nada():
    assert passo(estado="recusada", aprovacao_decisao="recusada") == "nada"


def test_todo_passo_esta_no_vocabulario_e_bate_com_a_view():
    sql = V10_02.read_text(encoding="utf-8")
    trecho = sql[sql.index("END AS proximo_passo") - 900:
                 sql.index("END AS proximo_passo")]
    do_sql = set(re.findall(r"THEN '([a-z_]+)'", trecho))
    do_sql |= set(re.findall(r"ELSE '([a-z_]+)'", trecho))
    assert do_sql == set(it.PASSOS)


# ═══════════════════════════════════════════════════════════════════════════
# 7. T1 — A MÁQUINA RECOMENDA, O HUMANO APLICA
# ═══════════════════════════════════════════════════════════════════════════

_P = {"proposta_id": "p1", "expira_em": "2026-08-27T12:00:00Z"}


def test_aprovacao_de_outra_proposta_nao_autoriza():
    """Sem esta conferência, bastaria apontar para qualquer aprovação existente
    e a trava viraria decoração — um `NOT NULL` que qualquer uuid satisfaz."""
    pode, por_que = it.pode_aplicar(
        _P, {"proposta_id": "p2", "decisao": "aprovada"}, agora=AGORA)
    assert pode is False and "outra proposta" in por_que


def test_recusa_humana_nao_autoriza():
    pode, por_que = it.pode_aplicar(
        _P, {"proposta_id": "p1", "decisao": "recusada"}, agora=AGORA)
    assert pode is False and "T1" in por_que


def test_proposta_vencida_nao_aplica():
    pode, por_que = it.pode_aplicar(
        {**_P, "expira_em": "2026-08-25T12:00:00Z"},
        {"proposta_id": "p1", "decisao": "aprovada"}, agora=AGORA)
    assert pode is False and "expirou" in por_que


def test_cooldown_ativo_bloqueia():
    """Sem esta guarda a regra briga consigo mesma: sobe e desce o mesmo
    orçamento a cada rodada, e a plataforma reaprende do zero toda vez."""
    pode, por_que = it.pode_aplicar(
        _P, {"proposta_id": "p1", "decisao": "aprovada"}, agora=AGORA,
        cooldown_ate=(AGORA + timedelta(hours=5)).isoformat())
    assert pode is False and "carência" in por_que


def test_aprovada_no_prazo_e_sem_carencia_aplica():
    pode, por_que = it.pode_aplicar(
        _P, {"proposta_id": "p1", "decisao": "aprovada"}, agora=AGORA,
        cooldown_ate=(AGORA - timedelta(hours=1)).isoformat())
    assert pode is True and por_que is None


# ═══════════════════════════════════════════════════════════════════════════
# REGRESSÃO · achados da auditoria adversarial de 26/08/2026
# ═══════════════════════════════════════════════════════════════════════════


def test_janela_ausente_nao_e_janela_suficiente():
    """⚠️ A omissão atravessava o teto e o registro dizia que ele foi conferido.

    `if inicio is not None and fim is not None:` pulava as checagens de janela
    mínima e de atraso de conversão INTEIRAS quando a janela não vinha — e a
    função seguia para a amostra e podia devolver "suficiente", numa regra que
    declara `janela_minima_dias`. É a mesma família do delta ausente passando
    como "dentro do limite".
    """
    ev = {"cliques": 500, "custo_micros": 90, "conversoes": 12,
          "colhida_em": "2026-08-26T00:00:00Z"}
    r = it.avaliar_suficiencia(ev, regra(janela_minima_dias=7))
    assert r.veredito == "insuficiente"
    assert "janela_inicio" in r.faltantes or "janela_fim" in r.faltantes


def test_nao_existe_regra_sem_janela_minima():
    """Por que a guarda acima pode exigir a janela SEMPRE.

    Eu ia escrever "regra sem janela mínima aceita evidência sem janela" — e o
    domínio recusou construir a regra. `janela_minima_dias` é no mínimo 1, e uma
    regra sem nenhuma amostra mínima também não nasce. Isso torna a exigência da
    janela incondicional, e é melhor prova que um `if` defensivo.
    """
    import pytest
    with pytest.raises(it.ErroDeIntencao, match="janela mínima abaixo de 1 dia"):
        regra(janela_minima_dias=0)
    with pytest.raises(it.ErroDeIntencao, match="amostra mínima"):
        regra(amostra_minima_cliques=None, amostra_minima_impressoes=None,
              amostra_minima_conversoes=None)


def test_janela_como_date_nao_some():
    """⚠️ `datetime` é subclasse de `date`; o contrário não vale.

    Um `date` puro caía no `return None` de `_para_datetime` e virava "janela
    ausente" — em silêncio, na função que decide se uma recomendação tem lastro.

    ⚠️⚠️ `agora=` é obrigatório aqui, e a primeira versão deste teste não o
    passava. Ele passou no dia em que foi escrito e começou a falhar no dia
    seguinte: a regra aceita 24 h de frescor, `colhida_em` é fixo, e o relógio
    real andou. Um teste com relógio dentro não mede o código — mede a data.
    """
    from datetime import date as _date, datetime as _dt, timezone as _tz
    assert it._para_datetime(_date(2026, 8, 1)) is not None
    ev = {"cliques": 500, "custo_micros": 90, "conversoes": 12,
          "colhida_em": "2026-08-26T00:00:00Z",
          "janela_inicio": _date(2026, 8, 1), "janela_fim": _date(2026, 8, 20)}
    r = it.avaliar_suficiencia(
        ev, regra(janela_minima_dias=7, atraso_conversao_dias=0,
                  amostra_minima_cliques=30),
        agora=_dt(2026, 8, 26, 10, 0, tzinfo=_tz.utc))
    assert r.veredito == "suficiente", r.motivo


def test_nenhum_teste_de_suficiencia_depende_do_relogio_real():
    """A guarda de regressão do defeito acima.

    Qualquer teste que afirme `suficiente` sobre uma evidência de data fixa e
    NÃO passe `agora=` é uma bomba-relógio: ele verde hoje e vermelho depois de
    `frescor_maximo_horas`. Esta prova varre o próprio arquivo.
    """
    import inspect, re, pathlib
    fonte = pathlib.Path(__file__).read_text()
    corpos = re.findall(r"\ndef (test_\w+)\(\):\n(.*?)(?=\ndef |\Z)", fonte, re.S)
    culpados = []
    for nome, corpo in corpos:
        if "avaliar_suficiencia" not in corpo:
            continue
        if 'veredito == "suficiente"' not in corpo:
            continue
        if "agora=" not in corpo:
            culpados.append(nome)
    assert not culpados, (
        f"testes que afirmam suficiência sem fixar `agora=`: {culpados}. "
        f"Eles passam hoje e falham depois do frescor da regra.")
