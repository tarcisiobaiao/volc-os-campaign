"""Testes dos mapeadores do DataForSEO.

O cliente HTTP não é testado aqui — não há credencial neste ambiente, e testar
rede com mock prova que o mock funciona. O que importa e é testável são os
MAPEADORES: eles decidem o nível de quatro eixos do motor, e um erro ali entra
silenciosamente na decisão.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from motor_pautas.sensores import dataforseo as D


# ── volume ──────────────────────────────────────────────────────────────────

def test_volume_vira_faixa_nao_numero():
    """Faixa, mesmo tendo o número: a decisão com 12 mil é a mesma com 15 mil."""
    assert D.nivel_volume(250_000) == "massivo"
    assert D.nivel_volume(12_000) == "alto"
    assert D.nivel_volume(3_000) == "medio"
    assert D.nivel_volume(400) == "baixo"
    assert D.nivel_volume(40) == "residual"
    assert D.nivel_volume(None) is None


# ── spread: a correção que a revisão externa exigiu ─────────────────────────

def test_spread_usa_cpc_da_keyword_e_rpm_do_arquetipo():
    """Média nacional deu Pearson −0,266 contra cinco mercados medidos.

    O CPC tem que ser o da keyword naquele país e o RPM o do arquétipo — média
    de país mistura crédito imobiliário com multa de trânsito.
    """
    assert D.nivel_spread(cpc_usd=0.10, receita_por_sessao_usd=0.30) == "excelente"   # 3,0
    assert D.nivel_spread(cpc_usd=0.10, receita_por_sessao_usd=0.15) == "bom"         # 1,5
    assert D.nivel_spread(cpc_usd=0.10, receita_por_sessao_usd=0.10) == "neutro"      # 1,0
    assert D.nivel_spread(cpc_usd=1.00, receita_por_sessao_usd=0.50) == "ruim"        # 0,5


def test_spread_sem_dado_nao_inventa():
    assert D.nivel_spread(None, 0.3) is None
    assert D.nivel_spread(0.1, None) is None
    assert D.nivel_spread(0.0, 0.3) is None      # divisão por zero


# ── vácuo: SERP real em vez de opinião ──────────────────────────────────────

def serp(*dominios):
    return {"items": [{"type": "organic", "domain": d} for d in dominios]}


def test_vacuo_serp_dominado_por_oficial_e_oportunidade():
    s = serp("gov.br", "gov.br", "portal.gov.br")
    assert D.nivel_vacuo(s) == "virgem"


def test_vacuo_com_portais_grandes_e_commodity():
    s = serp("uol.com.br", "globo.com", "terra.com.br", "r7.com",
             "ig.com.br", "gov.br")
    assert D.nivel_vacuo(s, dominios_grandes={"uol", "globo", "terra", "r7"}) == "saturado"


def test_vacuo_poucos_portais_pequenos_e_raso():
    s = serp("gov.br", "blogzinho.com", "outro.com.br")
    assert D.nivel_vacuo(s, dominios_grandes={"uol", "globo"}) == "raso"


def test_vacuo_sem_serp_nao_inventa():
    assert D.nivel_vacuo({"items": []}) is None


# ── reposição: a forma da curva ─────────────────────────────────────────────

def serie(*valores):
    return [{"search_volume": v} for v in valores]


def test_curva_plana_e_reposicao_continua():
    """Gente nova entrando o tempo todo: volume não oscila."""
    n, _ = D.nivel_reposicao(serie(*([1000, 1050, 980, 1020, 990, 1010,
                                      1000, 1030, 970, 1000, 1010, 990] * 2)))
    assert n == "continua"


def test_um_pico_por_ano_e_sazonal_anual():
    """Dois ciclos, porque com um só nada é distinguível — ver
    `test_um_ciclo_nao_sustenta_afirmacao_de_tendencia`."""
    ciclo = [100, 100, 120, 5000, 4000, 200, 100, 100, 100, 100, 100, 120]
    n, prova = D.nivel_reposicao(serie(*(ciclo * 2)))
    assert n == "anual"
    assert prova["amplitude"] > 1.0


def test_picos_mensais_sao_os_mesmos_voltando():
    n, _ = D.nivel_reposicao(serie(*([200, 3000] * 12)))
    assert n == "mesma_gente"


def test_queda_sustentada_e_tema_morrendo():
    """Queda de um ano cheio contra o outro — o que sobrevive a sazonalidade."""
    alto = [5000, 4500, 3800, 3000, 2000, 1200, 800, 700, 600, 500, 450, 400]
    baixo = [200, 180, 160, 150, 140, 130, 120, 110, 100, 90, 80, 50]
    n, prova = D.nivel_reposicao(serie(*(alto + baixo)))
    assert n == "unica"
    assert prova["tendencia"] < -0.6


def test_um_ciclo_nao_sustenta_afirmacao_de_tendencia():
    """12 meses viram AUSENTE, não um nível.

    A mesma série de um ciclo sai `anual` ou `unica` conforme o mês em que a
    janela corta. O mínimo antigo de 6 meses deixava a fase do corte decidir um
    eixo — e o motor tira da fila quem não atinge cobertura, então um nível
    errado aqui é pior que eixo ausente.
    """
    um_ciclo = [100, 100, 120, 5000, 4000, 200, 100, 100, 100, 100, 100, 120]
    assert D.nivel_reposicao(serie(*um_ciclo))[0] is None


def test_serie_curta_demais_nao_produz_nivel():
    assert D.nivel_reposicao(serie(100, 200, 300))[0] is None
    assert D.nivel_reposicao(serie(*([500] * 23)))[0] is None   # 23 < dois ciclos
    assert D.nivel_reposicao(None)[0] is None
    assert D.nivel_reposicao(serie(0, 0, 0, 0, 0, 0, 0))[0] is None


# ── intenção: verificação cruzada, não sobrescrita ──────────────────────────

def test_intencao_confirma_quando_bate():
    assert D.conflito_de_intencao("informational", "nao_sei_se_existe") is None


def test_intencao_levanta_a_mao_quando_diverge():
    m = D.conflito_de_intencao("transactional", "nao_sei_se_existe")
    assert m and "não bate" in m


def test_intencao_nao_sobrescreve_a_declaracao():
    """Trocar julgamento por julgamento sem saber qual está certo não é melhoria.

    A função devolve texto de conflito ou None — nunca um nível corrigido. Se
    algum dia ela passar a devolver um nível de ignorância, alguém transformou
    verificação cruzada em sobrescrita silenciosa.
    """
    from motor_pautas.espaco import IGNORANCIA
    r = D.conflito_de_intencao("transactional", "nao_sei_se_existe")
    assert isinstance(r, str)
    assert r not in IGNORANCIA
    assert D.conflito_de_intencao("informational", "nao_sei_se_existe") is None


def test_dominio_oficial_e_detectado_por_componente():
    """Regressão: `".gov" in "gov.br"` é False — falta o ponto inicial.

    O bug inflava o `vacuo` de todo tema brasileiro, porque o domínio oficial
    não era reconhecido e virava "mais um portal concorrendo".
    """
    assert D._e_oficial("gov.br")
    assert D._e_oficial("www.gov.br")
    assert D._e_oficial("inss.gov.br")
    assert D._e_oficial("gob.mx")
    assert D._e_oficial("service-public.gouv.fr")
    assert not D._e_oficial("governodigital.com.br")   # "governodigital" ≠ "gov"
    assert not D._e_oficial("uol.com.br")


# ── envelope da API ─────────────────────────────────────────────────────────

def test_itens_tolera_envelope_vazio():
    """Dia sem resultado é o caso mais comum e o que menos merece crash."""
    assert D.itens({}) == []
    assert D.itens({"tasks": None}) == []
    assert D.itens({"tasks": [{"status_code": 20000, "result": None}]}) == []


def test_itens_ignora_tarefa_com_erro():
    r = {"tasks": [{"status_code": 40501, "result": [{"items": [{"x": 1}]}]},
                   {"status_code": 20000, "result": [{"items": [{"x": 2}]}]}]}
    assert D.itens(r) == [{"x": 2}]


def test_tarefa_respeita_o_limite_da_api():
    """1000 em volume, 700 em histórico — estourar devolve erro, não trunca."""
    assert len(D.tarefa_volume(["k"] * 5000, location_code=2076,
                               language_code="pt")[0]["keywords"]) == 1000
    assert len(D.tarefa_historico(["k"] * 5000, location_code=2076,
                                  language_code="pt")[0]["keywords"]) == 700


# ── credencial ──────────────────────────────────────────────────────────────

def test_sem_credencial_falha_com_mensagem_acionavel(monkeypatch):
    monkeypatch.delenv("DATAFORSEO_LOGIN", raising=False)
    monkeypatch.delenv("DATAFORSEO_SENHA", raising=False)
    with pytest.raises(D.SemCredencial, match="DATAFORSEO_LOGIN"):
        D.Cliente().chamar("volume_cpc", [])


def test_rpm_do_gam_passado_por_engano_falha_alto():
    """O nome antigo era `rpm_usd`, e RPM por convenção é receita por MIL — o
    número que o GAM mostra. Ligá-lo aqui daria um spread MIL VEZES maior e todo
    tema pareceria excelente. O erro é silencioso por natureza: produz um número
    plausível. Por isso falha alto em vez de calcular."""
    import pytest
    with pytest.raises(ValueError, match="receita por MIL"):
        D.nivel_spread(cpc_usd=0.50, receita_por_sessao_usd=15.0)   # RPM do GAM
    # e o valor certo, convertido, passa
    assert D.nivel_spread(cpc_usd=0.50, receita_por_sessao_usd=15.0/1000*2) == "ruim"


# ── o que as 96 medições reais corrigiram ───────────────────────────────────

def _serie_decrescente():
    """Como a API DEVOLVE de fato: do mês mais RECENTE para o mais antigo.

    Medido em 14/08/2026 numa chamada real de `historical_search_volume`:
    o primeiro item de `saque aniversario fgts` é 2026-06 e o último 2018-11.
    """
    meses = []
    for ano in range(2026, 2018, -1):
        for mes in range(12, 0, -1):
            vol = 0 if (ano, mes) < (2019, 7) else 50_000
            meses.append({"year": ano, "month": mes, "search_volume": vol})
    return meses


def test_janela_48_pega_os_MAIS_RECENTES_apesar_da_ordem_da_api():
    """O bug que a ordem decrescente esconde: `[-48:]` cru pega a pré-história.

    Sem normalizar, a reposição de todo tema seria classificada pelos 48 meses
    mais ANTIGOS — e para uma entidade nascida em 2019 isso é uma fileira de
    zeros classificada como `unica`.
    """
    janela = D.janela_48(_serie_decrescente())
    assert len(janela) == 48
    assert (janela[0]["year"], janela[0]["month"]) < (janela[-1]["year"], janela[-1]["month"])
    assert (janela[-1]["year"], janela[-1]["month"]) == (2026, 12)
    assert all(m["search_volume"] > 0 for m in janela)


def test_nascimento_le_a_serie_inteira_e_acha_o_primeiro_mes_com_volume():
    """Os zeros à esquerda são a data de nascimento, e são exatos.

    `saque aniversario fgts` acende em 2019-07 — o mês da MP do
    saque-aniversário. Varrer o array cru acharia o mês mais recente.
    """
    assert D.nascimento_da_entidade(_serie_decrescente()) == "2019-07"


def test_perda_silenciosa_do_labs_e_detectada():
    """Reproduzido em chamada real: pedi 2 keywords, `items_count` veio 1.

    O status é 20000, não há erro em lugar nenhum, e o item simplesmente não
    está no array. Tratar isso como volume zero mata tema vivo.
    """
    faltantes = D.diff_pedido_devolvido(
        ["saque aniversario fgts", "cesantias"], ["saque aniversario fgts"]
    )
    assert faltantes == ["cesantias"]
    assert D.diff_pedido_devolvido(["A", "b"], ["  a ", "B"]) == []


def test_formato_consumo_e_por_tema_e_nunca_inventa_voz_ou_humano():
    ng = {"items": [{"type": "organic", "domain": d} for d in
                    ["youtube.com", "nimc.gov.ng", "facebook.com", "tiktok.com",
                     "nairaland.com", "legit.ng"]]}
    br = {"items": [{"type": "organic", "domain": d} for d in
                    ["caixa.gov.br", "gov.br", "direito2.com.br", "infomoney.com.br"]]}
    assert D.nivel_formato_consumo(ng)[0] == "video_social"
    assert D.nivel_formato_consumo(br)[0] == "texto_busca"
    # SERP sem orgânicos -> ausente. Quem trata é o chamador, tirando o card da
    # fila: eixo ausente SAI da média geométrica, então silêncio subiria a nota.
    assert D.nivel_formato_consumo({"items": []})[0] is None
    # Uma SERP não enxerga busca por voz nem intermediário físico.
    for serp in (ng, br):
        assert D.nivel_formato_consumo(serp)[0] != "voz_ou_humano"


def test_custo_reproduz_a_fatura_medida():
    """193 itens custaram US$ 0,03516 na fatura. A fórmula tem que dar isso."""
    assert round(D.custo_previsto_labs(193), 5) == 0.03516
    # E o custo lido da resposta soma tasks[].cost, não o envelope.
    assert D.custo({"cost": 99.0, "tasks": [{"cost": 0.01}, {"cost": 0.02}]}) == 0.03


def test_cpc_nulo_vira_binario_de_leilao_nunca_numero():
    """`cpc: null` não é dado faltando — é ausência de leilão (MX: 32 de 32)."""
    sem_leilao = [{"keyword": "a", "search_volume": 2900, "cpc": None},
                  {"keyword": "b", "search_volume": 390, "cpc": None}]
    tem, prova = D.existe_leilao(sem_leilao)
    assert tem is False and prova["share_com_leilao"] == 0.0
    assert D.existe_leilao([])[0] is None


def test_volume_e_do_cluster_nao_da_string_exata():
    """`ds49` sozinho dá 90/mês e dispararia `residual`; o cluster não."""
    cluster = [{"keyword": "subsidio de vivienda ds49", "search_volume": 90},
               {"keyword": "subsidio de vivienda", "search_volume": 33_000},
               {"keyword": "postular subsidio ds49", "search_volume": 1_600}]
    total, prova = D.volume_do_cluster(cluster)
    assert total == 34_690
    assert D.nivel_volume(total) == "alto"
    assert D.nivel_volume(90) == "residual"          # o que a string exata daria
    assert prova["termo_cabeca"] == "subsidio de vivienda"


def _serie_anual(ini_ano, ini_mes, n=48):
    """Coorte anual: pico em janeiro/fevereiro, resto plano."""
    s, a, m = [], ini_ano, ini_mes
    for _ in range(n):
        s.append({"year": a, "month": m,
                  "search_volume": 1_500_000 if m in (1, 2) else 200_000})
        m += 1
        if m > 12:
            m, a = 1, a + 1
    return s


def test_coorte_anual_nao_vira_mesma_gente_na_janela_de_48_meses():
    """O limiar de pico era absoluto e a janela virou fixa — quebrou os dois.

    IPVA, medido: picos em 2023-01, 2024-01, 2025-01, 2025-02, 2026-01,
    2026-02. Seis picos em quatro anos = 1,5/ano. Com `n_picos >= 4` isso saía
    `mesma_gente` — a coorte anual mais limpa do país lida como gente voltando.
    """
    nivel, prova = D.nivel_reposicao(D.janela_48(_serie_anual(2022, 7)))
    assert nivel == "anual", f"saiu {nivel} com {prova['picos_por_ano']} picos/ano"
    assert prova["picos_por_ano"] <= 2.0

    mensal = [{"year": a, "month": m,
               "search_volume": 900_000 if m % 2 else 100_000}
              for a in range(2023, 2027) for m in range(1, 13)]
    assert D.nivel_reposicao(D.janela_48(mensal))[0] == "mesma_gente"


def test_tendencia_nao_depende_do_mes_em_que_a_janela_termina():
    """A MESMA série anual saía `unica` ou `anual` conforme o mês do corte.

    Com `(ultimos3 - primeiros3)`, uma janela que termina logo após o pico
    mede -2,08 e vira "tema morrendo". Como a janela termina sempre no mês
    corrente, o mesmo tema mudaria de eixo entre janeiro e julho sem nada ter
    mudado no mundo. Blocos de 12 meses são invariantes à fase.
    """
    niveis, tendencias = set(), set()
    for ini in ((2023, 1), (2022, 7), (2022, 10), (2023, 4)):
        nivel, prova = D.nivel_reposicao(D.janela_48(_serie_anual(*ini)))
        niveis.add(nivel)
        tendencias.add(prova["tendencia"])
    assert niveis == {"anual"}, f"a fase do corte mudou o nível: {niveis}"
    assert tendencias == {0.0}, f"a fase do corte mudou a tendência: {tendencias}"


def test_queda_real_continua_sendo_detectada():
    """A trava contra falso negativo: tema que morre de verdade ainda sai `unica`."""
    morrendo = []
    a, m = 2022, 7
    for i in range(48):
        base = 1_000_000 if i < 24 else 150_000      # cai pela metade e não volta
        morrendo.append({"year": a, "month": m,
                         "search_volume": base * (3 if m in (1, 2) else 1)})
        m += 1
        if m > 12:
            m, a = 1, a + 1
    assert D.nivel_reposicao(D.janela_48(morrendo))[0] == "unica"


def test_virgem_ambiguo_se_separa_por_estrutura_de_mercado():
    """`virgem` é o topo do eixo e comporta duas leituras opostas.

    Sem dado próprio — que quem está começando não tem, e que por definição não
    existe num país onde nunca se rodou — a separação vem da estrutura pública
    da SERP: há quem pague, e há quem já viva disso?
    """
    from app.motor_pautas.sensores.dataforseo import leitura_do_vazio

    assert leitura_do_vazio("virgem", existe_leilao=True)[0] == "descoberta"
    assert leitura_do_vazio("virgem", existe_leilao=False)[0] == "deserto"
    assert leitura_do_vazio("virgem", existe_leilao=None)[0] == "indeterminado"
    # publisher com tráfego real derruba a virgindade, com ou sem leilão
    assert leitura_do_vazio("virgem", existe_leilao=True,
                            etv_publishers=[23549.0])[0] == "ocupado"
    # casca não conta: ETV 7,2 é presença, não concorrência
    assert leitura_do_vazio("virgem", existe_leilao=True,
                            etv_publishers=[7.2])[0] == "descoberta"
    # e fora do `virgem` a leitura não se aplica
    assert leitura_do_vazio("saturado", existe_leilao=True)[0] == "nao_se_aplica"


# ── a fila de ads NÃO é a régua do volume ──────────────────────────────────

def test_fila_de_ads_nao_pode_ser_a_regua_do_volume():
    """O caso `Cartão para Negativado` (BR), com os 23 termos reais minerados.

    O n8n minerou por `keyword_ideas`, que **expande categoria, não frase** — o
    próprio sensor já dizia isso na lista de endpoints descartados. O resultado
    foi que `banco pan telefone` (consulta do telefone do Banco Pan) entrou na
    fila com 27.100 e virou 73% do eixo `volume` de um tema sobre cartão de
    crédito para negativado.

    Este teste congela os dois números: o que a fila somava, e o que o cluster
    ancorado por CONTENÇÃO soma. Ele não testa um filtro — testa que a fonte
    mudou, que é o conserto.
    """
    from app.motor_pautas.sensores.dataforseo import nivel_volume, volume_do_cluster

    fila_de_ads = [
        {"keyword": "banco pan telefone", "search_volume": 27100},
        {"keyword": "cartão de crédito caixa telefone", "search_volume": 1600},
        {"keyword": "cartão de crédito fácil aprovação com limite", "search_volume": 1300},
        {"keyword": "solicitar cartão caixa poupança", "search_volume": 1300},
        {"keyword": "cartão de crédito online aprovado na hora com limite", "search_volume": 1000},
        {"keyword": "cartão de crédito limite 3 mil na hora", "search_volume": 720},
        {"keyword": "cartão de crédito limite 3 mil para negativado", "search_volume": 720},
        {"keyword": "cartão de crédito para negativado online", "search_volume": 480},
        {"keyword": "cartão para negativado aprovado na hora 2026", "search_volume": 480},
        {"keyword": "banco pan cartão de crédito whatsapp", "search_volume": 110},
    ]
    total_fila, _ = volume_do_cluster(fila_de_ads)
    contato = 27100 + 1600 + 110
    assert total_fila == 34810
    assert contato / total_fila > 0.80, "as consultas de contato dominam a fila"

    # O cluster por CONTENÇÃO: só o que contém a frase-semente. As três
    # consultas de contato somem por construção do fornecedor — `banco pan
    # telefone` não contém "cartão para negativado".
    semente = "cartão para negativado"
    por_contencao = [k for k in fila_de_ads
                     if all(tok in k["keyword"] for tok in ("cartão", "negativado"))]
    total_cluster, _ = volume_do_cluster(por_contencao)
    assert total_cluster == 1680   # 720 + 480 + 480
    assert not any("telefone" in k["keyword"] or "whatsapp" in k["keyword"]
                   for k in por_contencao)

    # E o nível do eixo muda — que é a consequência que importa
    assert nivel_volume(total_fila) != nivel_volume(total_cluster)


def test_termos_do_historico_nao_carrega_a_fila_de_ads():
    """A `reposicao` é propriedade da ENTIDADE. A série mensal tem de vir dos
    nomes curados, nunca de uma keyword que o minerador achou."""
    from app.validacao.orquestrador import Card

    c = Card(opportunity_id=1, entity_id=1, country_code="BR", termo="Cartão para Negativado",
             nomes=["Cartão para Negativado", "cartão para negativados"],
             consultas=["banco pan telefone", "cartão de crédito caixa telefone"])
    termos = c.termos_do_historico()
    assert termos == ["Cartão para Negativado", "cartão para negativados"]
    assert not any("telefone" in t for t in termos)
