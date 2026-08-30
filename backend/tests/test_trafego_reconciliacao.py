"""A reconciliação: **este funil já tem campanha?**

As fixtures são a realidade medida em 26/08/2026 no Supabase oficial, porque um
teste de reconciliação montado com dados inventados prova que a regra funciona
sobre o que imaginamos. Os nomes reais aparecem nas FIXTURES; a regra não os
conhece, e `test_a_regra_nao_conhece_nenhum_nome` prova isso mecanicamente.

O que a conta `8017851692` (Crédito Up) tem hoje, e o que o quadro respondia:

    run 7  / opp 74   maquininha       → `campaigns` tem linha, com funnel_run_id
    run 9  / opp 65   fgts             → `campaigns` NÃO tem linha nenhuma
    run 6  / opp 73   permalink de rascunho

Duas campanhas ENABLED, três removidas. O quadro reconhecia a primeira e
oferecia "montar campanha" para a segunda.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.trafego import reconciliacao as rec  # noqa: E402

LP_FGTS = "https://creditoup.com.br/r/fgts-saque-aniversario/"
LP_MAQ = "https://creditoup.com.br/r/maquininha-de-cartao-menor-taxa"
CONTA = "8017851692"
OUTRA_CONTA = "5478096539"


def _funil(opp: int, run: int | None, lp: str | None, **kw) -> rec.Funil:
    base = dict(opportunity_id=opp, run_id=run, project_id=2,
                customer_id=CONTA, lp_url=lp)
    base.update(kw)
    return rec.Funil(**base)


def _campanha(kid: str, nome: str, **kw) -> rec.CampanhaConhecida:
    base = dict(volc_campaign_id=f"gads-{CONTA}-{kid}", campaign_id=kid,
                customer_id=CONTA, nome=nome, estado_externo="ENABLED",
                canal="SEARCH", historico=False)
    base.update(kw)
    return rec.CampanhaConhecida(**base)


# As cinco campanhas reais da conta, com os nomes exatos que a varredura leu.
UNIVERSO_REAL = [
    _campanha("24155134757",
              f"BR - 20260819_131546 / Maquininha de Cartão / {LP_MAQ}/"),
    _campanha("24153000001",
              f"BR - 20260819_123824 / Maquininha de Cartão / {LP_MAQ}/",
              estado_externo="REMOVED", historico=True),
    _campanha("24156134066",
              f"BR BR - 20260819_222608 / FGTS Saque-Aniversário / {LP_FGTS}"),
    _campanha("24156373085",
              f"BR - 20260819_200614 / FGTS Saque-Aniversário / {LP_FGTS}",
              estado_externo="REMOVED", historico=True),
    _campanha("24161105437",
              f"BR BR - 20260819_215205 / FGTS Saque-Aniversário / {LP_FGTS}",
              estado_externo="REMOVED", historico=True),
]

#: O que `campaigns` tem hoje: uma linha, para o run 7.
LEGADO_REAL = {7: {"24155134757"}}


# ═══════════════════════════════════════════════════════════════════════════
# 1. NORMALIZAÇÃO — a mesma do gatilho que já vive no banco
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bruta, esperado", [
    ("https://creditoup.com.br/r/x/", "creditoup.com.br/r/x"),
    ("http://www.creditoup.com.br/r/x", "creditoup.com.br/r/x"),
    ("  https://CreditoUp.com.br/r/x/  ", "CreditoUp.com.br/r/x"),
    ("https://creditoup.com.br/r/x", "creditoup.com.br/r/x"),
])
def test_normalizacao_e_a_do_gatilho_clean_funnel_url(bruta, esperado):
    """`TRIM` → tira esquema → tira `www.` → tira barra final. Sem lowercase.

    Reproduz `clean_funnel_url`, que é a chave do join custo × receita. Usar
    outra normalização faria dois lugares do sistema discordarem sobre o que é
    "a mesma página".
    """
    assert rec.url_normalizada(bruta) == esperado


def test_normalizacao_nao_baixa_o_caso():
    """O caminho de uma URL é sensível a maiúsculas em servidor Unix.

    `/r/FGTS` e `/r/fgts` podem ser páginas diferentes; casá-las seria vincular
    o funil errado. O gatilho do banco também não baixa, e a omissão dele é
    deliberada.
    """
    assert rec.url_normalizada("https://x.com/r/FGTS") != \
        rec.url_normalizada("https://x.com/r/fgts")


def test_permalink_de_rascunho_nao_normaliza():
    """`?post_type=r&p=2152` é o que o WP devolve para rascunho.

    A única parte estável dele é `?post_type=r`, igual para todo funil não
    publicado. Comparar por ele casaria funis diferentes entre si.
    """
    assert rec.url_normalizada("https://creditoup.com.br/?post_type=r&p=2152") is None
    assert rec.url_normalizada("https://creditoup.com.br/algo?p=99") is None


def test_url_sai_do_terceiro_campo_da_taxonomia():
    nome = f"BR - 20260819_131546 / Maquininha de Cartão / {LP_MAQ}/"
    assert rec.url_no_nome(nome) == "creditoup.com.br/r/maquininha-de-cartao-menor-taxa"


def test_nome_escrito_a_mao_nao_produz_url():
    """Um nome sem segmento com cara de URL não dispara a regra.

    Ela não casa errado: ela não casa.
    """
    assert rec.url_no_nome("Campanha institucional 2026") is None
    assert rec.url_no_nome("") is None
    assert rec.url_no_nome(None) is None


def test_tema_com_barra_nao_desloca_a_extracao():
    """Procura-se o segmento que PARECE URL, e não a posição 3.

    Um tema com ` / ` dentro empurraria a URL para a quarta posição, e ler por
    índice devolveria o pedaço errado do tema como se fosse endereço.
    """
    nome = f"BR - 001 / FGTS / Saque / {LP_FGTS}"
    assert rec.url_no_nome(nome) == "creditoup.com.br/r/fgts-saque-aniversario"


# ═══════════════════════════════════════════════════════════════════════════
# 2. OS CINCO ESTADOS, COM OS DADOS REAIS
# ═══════════════════════════════════════════════════════════════════════════


def test_funil_com_campanha_ativa_deixa_de_ser_pronto_para_montar():
    """O defeito que a U0.2 fecha, no caso que o expôs.

    `campaigns` não tem linha para este run. Pela regra antiga o quadro
    respondia `campanhas_lancadas: 0` e convidava a montar — enquanto uma
    campanha do mesmo termo gastava na conta.
    """
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), UNIVERSO_REAL,
                        legado_por_run=LEGADO_REAL)
    assert r.estado == rec.CORRESPONDENCIA_PROVAVEL
    assert r.pode_montar is False
    assert r.exige_confirmacao_humana is True
    assert r.acao_permitida == rec.CONFIRMAR_VINCULO

    presentes = [c for c in r.candidatas if c.presente]
    assert len(presentes) == 1
    assert presentes[0].campanha.estado_externo == "ENABLED"
    # E a regra que a trouxe viaja junto: sugestão sem regra visível não é
    # oferecida (SPEC 3.2).
    assert [s.regra for s in presentes[0].sinais] == [rec.REGRA_URL_NO_NOME]


def test_funil_ja_reconhecido_continua_reconhecido():
    """O outro funil da mesma conta, que a regra antiga acertava por sorte.

    Ele tem linha em `campaigns` com `funnel_run_id`. A regra nova o alcança por
    DOIS caminhos independentes — a URL no nome e o lançamento declarado — e os
    dois viajam como evidência.
    """
    r = rec.reconciliar(_funil(74, 7, LP_MAQ), UNIVERSO_REAL,
                        legado_por_run=LEGADO_REAL)
    assert r.estado == rec.CORRESPONDENCIA_PROVAVEL
    assert r.pode_montar is False

    presentes = [c for c in r.candidatas if c.presente]
    assert len(presentes) == 1
    assert {s.regra for s in presentes[0].sinais} == {
        rec.REGRA_URL_NO_NOME, rec.REGRA_LANCAMENTO_DECLARADO}


def test_historico_nao_gera_conflito():
    """A FGTS tem TRÊS campanhas: duas removidas e uma ligada.

    Contá-las todas daria conflito, e conflito bloquearia o operador por causa
    da própria história de relançamento — que aconteceu cinco vezes com motivo
    declarado (E-05). O que disputa o leilão é o que está no ar.
    """
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), UNIVERSO_REAL,
                        legado_por_run=LEGADO_REAL)
    assert len(r.candidatas) == 3
    assert sum(1 for c in r.candidatas if c.presente) == 1
    assert r.estado == rec.CORRESPONDENCIA_PROVAVEL


def test_duas_candidatas_presentes_geram_conflito():
    """Escolher em silêncio seria vincular à campanha errada com confiança.

    O erro só apareceria semanas depois, na atribuição de receita — e sem nada
    na tela dizendo que houve escolha.
    """
    universo = UNIVERSO_REAL + [
        _campanha("24199999999",
                  f"BR - 20260820_090000 / FGTS Saque-Aniversário / {LP_FGTS}")]
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), universo,
                        legado_por_run=LEGADO_REAL)
    assert r.estado == rec.CONFLITO
    assert r.acao_permitida == rec.ABRIR_REVISAO
    assert r.pode_montar is False
    assert r.pode_relancar is False
    assert sum(1 for c in r.candidatas if c.presente) == 2


def test_so_historico_permite_relancamento_declarado():
    """Relançar é legítimo. Convite automático não é.

    A diferença está em `pode_relancar` sem `pode_montar`: a ação existe e exige
    motivo, em vez de aparecer como o mesmo botão de sempre.
    """
    universo = [c for c in UNIVERSO_REAL if c.historico]
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), universo,
                        legado_por_run=LEGADO_REAL)
    assert r.estado == rec.SOMENTE_HISTORICO
    assert r.pode_relancar is True
    assert r.pode_montar is False
    assert r.acao_permitida == rec.RELANCAR_DECLARADO


def test_sem_candidata_libera_a_montagem():
    """Só aqui a montagem abre — e a prova foi feita, não pulada."""
    r = rec.reconciliar(_funil(99, 42, "https://creditoup.com.br/r/inedito/"),
                        UNIVERSO_REAL, legado_por_run=LEGADO_REAL)
    assert r.estado == rec.SEM_CAMPANHA
    assert r.pode_montar is True
    assert r.exige_confirmacao_humana is False
    assert r.candidatas == ()


def test_vinculo_confirmado_vence_a_sugestao():
    """Alguém já respondeu a pergunta. Reabri-la a cada carregamento
    transformaria uma decisão registrada em sugestão perpétua."""
    universo = [
        dataclasses_replace(c, vinculo_id="v-1", vinculo_opportunity_id=65,
                            vinculo_run_id=9)
        if not c.historico and "FGTS" in c.nome else c
        for c in UNIVERSO_REAL
    ]
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), universo,
                        legado_por_run=LEGADO_REAL)
    assert r.estado == rec.VINCULADA
    assert r.acao_permitida == rec.ABRIR_O_QUE_EXISTE
    assert r.exige_confirmacao_humana is False
    assert r.pode_montar is False


def dataclasses_replace(obj, **kw):
    import dataclasses
    return dataclasses.replace(obj, **kw)


# ═══════════════════════════════════════════════════════════════════════════
# 3. AS FRONTEIRAS QUE A REGRA NÃO PODE ATRAVESSAR
# ═══════════════════════════════════════════════════════════════════════════


def test_conta_e_pre_requisito_e_nao_sinal():
    """Comparar URL entre contas casaria o funil de um cliente com a campanha
    de outro. A mesma URL, na conta errada, não é candidata."""
    universo = [
        rec.CampanhaConhecida(
            volc_campaign_id=f"gads-{OUTRA_CONTA}-1", campaign_id="1",
            customer_id=OUTRA_CONTA,
            nome=f"BR - 001 / Tema / {LP_FGTS}", estado_externo="ENABLED"),
    ]
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), universo)
    assert r.estado == rec.SEM_CAMPANHA
    assert r.candidatas == ()


def test_prova_impedida_exige_confirmacao_mesmo_liberando_a_montagem():
    """"Não tive como provar" não pode passar por "provei e não há".

    Montar continua liberado, e isso é deliberado: quase todo funil NOVO começa
    em rascunho, e bloquear aqui bloquearia trabalho legítimo — que é o jeito de
    a prova virar obstáculo e o operador aprender a contorná-la.

    O que muda é a CONFIRMAÇÃO: quando nenhuma regra pôde comparar, a tela avisa
    em vez de convidar.
    """
    rascunho = rec.reconciliar(
        _funil(73, 6, "https://creditoup.com.br/?post_type=r&p=2152"),
        UNIVERSO_REAL, legado_por_run=LEGADO_REAL)
    assert rascunho.estado == rec.SEM_CAMPANHA
    assert rascunho.pode_montar is True
    assert rascunho.exige_confirmacao_humana is True, (
        "a prova não pôde ser feita e a tela não tem como saber")

    # E o oposto: prova COMPLETA que não achou nada não incomoda ninguém.
    limpo = rec.reconciliar(
        _funil(99, 42, "https://creditoup.com.br/r/inedito/"),
        UNIVERSO_REAL, legado_por_run=LEGADO_REAL)
    assert limpo.estado == rec.SEM_CAMPANHA
    assert limpo.pode_montar is True
    assert limpo.exige_confirmacao_humana is False


def test_linhagem_ausente_nao_poe_ressalva_em_todo_cartao():
    """Nenhuma campanha tem linhagem hoje.

    Marcar isso como impedimento poria ressalva em 100% dos cartões no primeiro
    dia — e uma ressalva que aparece sempre é uma ressalva que o operador
    aprende a ignorar antes de ela significar alguma coisa.
    """
    r = rec.reconciliar(_funil(99, 42, "https://creditoup.com.br/r/inedito/"),
                        UNIVERSO_REAL, legado_por_run=LEGADO_REAL)
    linhagem = [s for s in r.sinais_ausentes
                if s["regra"] == rec.REGRA_LINHAGEM]
    assert linhagem and linhagem[0]["impede_prova"] is False


def test_o_motivo_nao_afirma_comparacao_que_nao_houve():
    """Relatar prova onde só houve silêncio é a mesma classe de defeito que
    `sem_campanha` sem ressalva.

    Se nenhuma campanha da conta tem URL — nem lida do anúncio, nem declarada no
    nome, porque nasceram à mão fora da taxonomia —, não houve comparação por
    URL. Dizer "a comparação usou a URL do nome" descreveria um trabalho que não
    aconteceu, e o operador leria isso como prova.
    """
    a_mao = [_campanha("1", "Campanha institucional"),
             _campanha("2", "Promo verão")]
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), a_mao)
    assert r.estado == rec.SEM_CAMPANHA
    ausente = [s for s in r.sinais_ausentes
               if s["regra"] == rec.REGRA_URL_DA_CONTA][0]
    assert ausente["impede_prova"] is True
    assert "ouve comparação por URL" in ausente["motivo"]
    assert r.exige_confirmacao_humana is True

    # E quando ALGUMA foi comparada pelo nome, o motivo diz quantas — em vez de
    # afirmar genericamente que a comparação aconteceu.
    com_nome = UNIVERSO_REAL
    r2 = rec.reconciliar(_funil(99, 42, "https://creditoup.com.br/r/inedito/"),
                         com_nome, legado_por_run=LEGADO_REAL)
    ausente2 = [s for s in r2.sinais_ausentes
                if s["regra"] == rec.REGRA_URL_DA_CONTA][0]
    assert ausente2["impede_prova"] is False
    assert "de 5 foram comparadas" in ausente2["motivo"], ausente2["motivo"]


def test_projeto_sem_conta_nao_libera_montagem_em_silencio():
    """"Não consegui provar" não pode passar por "provei e não há".

    Sem conta declarada não há onde procurar. O estado continua sendo
    `sem_campanha`, mas `sinais_ausentes` diz por quê — e é isso que permite à
    tela avisar em vez de convidar.
    """
    r = rec.reconciliar(_funil(65, 9, LP_FGTS, customer_id=None),
                        UNIVERSO_REAL)
    assert r.estado == rec.SEM_CAMPANHA
    regras = {s["regra"] for s in r.sinais_ausentes}
    assert "conta_do_projeto" in regras
    assert r.exige_confirmacao_humana is True


def test_funil_em_rascunho_declara_o_sinal_ausente():
    """`?post_type=r&p=2152` — o run 6 real está exatamente assim."""
    r = rec.reconciliar(
        _funil(73, 6, "https://creditoup.com.br/?post_type=r&p=2152"),
        UNIVERSO_REAL, legado_por_run=LEGADO_REAL)
    assert r.estado == rec.SEM_CAMPANHA
    regras = {s["regra"] for s in r.sinais_ausentes}
    assert rec.REGRA_URL_DA_CONTA in regras


def test_url_da_conta_prevalece_sobre_a_do_nome_e_nao_soma():
    """Quando a varredura colheu a URL do anúncio, ela é o sinal — e sozinha.

    As duas não somam: a URL do nome é a ORIGEM da URL do anúncio (nós a
    escrevemos ali no lançamento). Contá-las como sinais independentes faria uma
    composição futura somar o mesmo fato duas vezes.
    """
    universo = [_campanha("1", "nome escrito a mao, sem url",
                          url_final=LP_FGTS)]
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), universo)
    sinais = [s.regra for s in r.candidatas[0].sinais]
    assert sinais == [rec.REGRA_URL_DA_CONTA]


def test_a_url_preservada_nao_se_apresenta_como_observacao_atual():
    """O espelho não guarda QUANDO a URL foi lida.

    O gatilho da v9_04 a preserva entre varreduras, e o carimbo `lido_em` é da
    varredura, não da coluna. Não há como distinguir "o anúncio aponta para cá
    hoje" de "apontava quando a URL foi lida pela última vez".

    Enquanto `url_final_lida_em` não existir, a força é `historica`: sustenta a
    candidata e não fecha o vínculo sozinha. Chamá-la de `forte` seria promover
    a força em silêncio — no degrau exato que uma composição futura usaria para
    dispensar a confirmação humana.
    """
    assert rec.FORCA_DA_REGRA[rec.REGRA_URL_DA_CONTA] == rec.HISTORICA
    assert rec.HISTORICA != rec.FORTE

    universo = [_campanha("1", "x", url_final=LP_FGTS,
                          lido_em="2026-08-01T10:00:00+00:00")]
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), universo)
    sinal = r.candidatas[0].sinais[0]
    assert sinal.forca == rec.HISTORICA
    # E a evidência DIZ por que não é forte, em vez de deixar o leitor deduzir.
    assert "carimbo" in sinal.evidencia["por_que_nao_e_forte"]
    # A confirmação humana continua obrigatória de qualquer modo.
    assert r.exige_confirmacao_humana is True
    assert r.pode_montar is False

    ambas = [_campanha("1", f"BR - 001 / Tema / {LP_FGTS}", url_final=LP_FGTS)]
    r2 = rec.reconciliar(_funil(65, 9, LP_FGTS), ambas)
    assert [s.regra for s in r2.candidatas[0].sinais] == [rec.REGRA_URL_DA_CONTA]


def test_correspondencia_provavel_nunca_grava_vinculo():
    """O módulo é puro: ele não tem como gravar nada.

    A prova é estrutural, não de comportamento — `reconciliacao.py` não importa
    banco, rede nem framework, então não existe caminho por onde uma sugestão
    vire fato sem passar pelo router e pela confirmação humana.
    """
    import app.trafego.reconciliacao as modulo
    fonte = open(modulo.__file__, encoding="utf-8").read()
    for proibido in ("httpx", "requests", "psycopg", "supabase", "fastapi",
                     "persistencia", "sincronizador"):
        assert proibido not in fonte, (
            f"`reconciliacao.py` cita {proibido!r}: ele deixou de ser domínio "
            f"puro e passou a poder gravar")


# ═══════════════════════════════════════════════════════════════════════════
# 3b. O QUE A AUDITORIA ADVERSARIAL ENCONTROU
# ═══════════════════════════════════════════════════════════════════════════


def test_marcacao_na_url_do_anuncio_nao_derruba_a_regra_forte():
    """A URL do anúncio quase sempre carrega UTM; a `lp_url` do funil nunca.

    Comparando com a query string, a regra MAIS FORTE do contrato erra
    exatamente onde ela mais vale: numa campanha real, com destino certo. O
    resultado seria `sem_campanha` — o valor que LIBERA a montagem.
    """
    com_utm = [_campanha(
        "1", "nome escrito a mao",
        url_final=LP_FGTS + "?utm_source=google&utm_medium=cpc&gclid=abc")]
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), com_utm)
    assert r.estado == rec.CORRESPONDENCIA_PROVAVEL
    assert [x.regra for x in r.candidatas[0].sinais] == [rec.REGRA_URL_DA_CONTA]

    # E o fragmento também não derruba.
    ancora = [_campanha("1", "x", url_final=LP_FGTS + "#form")]
    assert rec.reconciliar(_funil(65, 9, LP_FGTS), ancora).estado == \
        rec.CORRESPONDENCIA_PROVAVEL


def test_a_normalizacao_do_join_continua_sendo_a_do_gatilho():
    """As duas coexistem de propósito: são perguntas diferentes.

    `url_normalizada` é a chave do join custo × receita e PRESERVA a query —
    igual ao gatilho `clean_funnel_url`. `destino_comparavel` é a da
    reconciliação, e a tira.
    """
    com = "https://x.com/r/a?utm_source=g"
    assert rec.url_normalizada(com) == "x.com/r/a?utm_source=g"
    assert rec.destino_comparavel(com) == "x.com/r/a"


def test_conta_nunca_varrida_nao_libera_montagem_em_silencio():
    """Universo vazio não é prova de ausência: é ausência de prova.

    "A conta está vazia" e "esta conta nunca foi varrida" chegam aqui idênticos
    — uma lista sem nada — e só o primeiro poderia liberar a montagem.
    """
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), [])
    assert r.estado == rec.SEM_CAMPANHA
    assert r.pode_montar is True
    assert r.exige_confirmacao_humana is True
    assert "varredura_da_conta" in {x["regra"] for x in r.sinais_ausentes}


def test_dois_runs_da_mesma_oportunidade_nao_trocam_de_veredito():
    """Uma oportunidade pode ter mais de um run — é o caso normal quando o funil
    é reprocessado —, e os dois viram cartões separados no quadro.

    Chaveando só pela oportunidade, o segundo sobrescreve o primeiro e um cartão
    passa a exibir o veredito do outro. Nada na tela denunciaria: os dois
    pareceriam coerentes.
    """
    a = _funil(65, 9, LP_FGTS)
    b = _funil(65, 99, "https://creditoup.com.br/r/pagina-nova/")
    mapa = rec.reconciliar_muitos([a, b], UNIVERSO_REAL,
                                  legado_por_run=LEGADO_REAL)
    assert len(mapa) == 2, mapa
    assert mapa[(65, 9)].estado == rec.CORRESPONDENCIA_PROVAVEL
    assert mapa[(65, 99)].estado == rec.SEM_CAMPANHA
    assert mapa[(65, 99)].pode_montar is True


def test_a_evidencia_da_url_carrega_a_data_da_leitura():
    """Uma URL de três semanas atrás e uma de agora sustentam a mesma regra com
    forças diferentes.

    O gatilho da v9_04 PRESERVA `url_final` quando a leitura não a trouxe, e o
    espelho não distingue "lida agora" de "preservada". `lido_em` é o que existe
    para dizer de quando é a observação — sem ele a evidência afirmaria
    atualidade que ninguém verificou.
    """
    universo = [_campanha("1", "x", url_final=LP_FGTS,
                          lido_em="2026-08-25T08:29:02-03:00")]
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), universo)
    sinal = r.candidatas[0].sinais[0]
    assert sinal.regra == rec.REGRA_URL_DA_CONTA
    assert sinal.evidencia["lido_em"] == "2026-08-25T08:29:02-03:00"


# ═══════════════════════════════════════════════════════════════════════════
# 4. NENHUM HARDCODE — a prova mecânica
# ═══════════════════════════════════════════════════════════════════════════


def test_a_regra_nao_conhece_nenhum_nome():
    """Nem "FGTS", nem "Maquininha", nem id de campanha, nem de conta.

    O conserto tinha de valer para a próxima campanha que ninguém previu — e uma
    regra que cita o caso que a motivou conserta um caso, não uma classe.
    """
    import ast

    import app.trafego.reconciliacao as modulo

    arvore = ast.parse(open(modulo.__file__, encoding="utf-8").read())

    # Documentar o caso que motivou a regra é obrigação; CODIFICÁ-LO é o
    # defeito. Por isso a prova tira as docstrings pela árvore sintática, e não
    # por prefixo de linha: um `#` no começo da linha não distingue comentário
    # de texto dentro de uma string de três aspas.
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                           ast.ClassDef)):
            corpo = getattr(no, "body", [])
            if (corpo and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and isinstance(corpo[0].value.value, str)):
                corpo.pop(0)

    codigo = ast.unparse(arvore)
    for proibido in ("FGTS", "Maquininha", "creditoup", "8017851692",
                     "24155134757", "24156134066"):
        assert proibido not in codigo, (
            f"a regra CODIFICA {proibido!r} — ela conserta um caso, não uma "
            f"classe, e a próxima campanha que ninguém previu volta a passar")


def test_renomear_a_campanha_nao_muda_o_veredito():
    """A prova viva de que a regra não é por nome.

    Trocar o rótulo humano da campanha, preservando a URL, mantém tudo — e
    trocar a URL, preservando o rótulo, desfaz.
    """
    outro_nome = [
        _campanha("24156134066", f"qualquer coisa / {LP_FGTS}"),
    ]
    r = rec.reconciliar(_funil(65, 9, LP_FGTS), outro_nome)
    assert r.estado == rec.CORRESPONDENCIA_PROVAVEL

    outra_url = [
        _campanha("24156134066",
                  "BR BR - 20260819_222608 / FGTS Saque-Aniversário / "
                  "https://creditoup.com.br/r/outra-pagina/"),
    ]
    r2 = rec.reconciliar(_funil(65, 9, LP_FGTS), outra_url)
    assert r2.estado == rec.SEM_CAMPANHA


def test_vocabulario_bate_com_o_do_frontend():
    """Os cinco estados que `src/components/trafego/hub/contrato.ts` declara.

    O front já foi escrito contra eles. Um nome diferente aqui faria a tela cair
    no ramo `default` e mostrar "sem campanha" para tudo — que é exatamente o
    defeito que esta rodada fecha, chegando pela outra ponta.
    """
    assert set(rec.ESTADOS) == {
        "vinculada", "correspondencia_provavel", "conflito", "sem_campanha",
        "somente_historico"}


def test_a_ordem_das_candidatas_e_estavel():
    """Evidência que muda de ordem entre duas leituras parece ter mudado de
    conteúdo."""
    import random
    baralhado = list(UNIVERSO_REAL)
    random.Random(7).shuffle(baralhado)
    a = rec.reconciliar(_funil(65, 9, LP_FGTS), UNIVERSO_REAL,
                        legado_por_run=LEGADO_REAL)
    b = rec.reconciliar(_funil(65, 9, LP_FGTS), baralhado,
                        legado_por_run=LEGADO_REAL)
    assert [c.campanha.volc_campaign_id for c in a.candidatas] == \
           [c.campanha.volc_campaign_id for c in b.candidatas]
