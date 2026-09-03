"""CONTRAPROVAS — o conjunto pago não pode herdar a mineração inteira.

Este arquivo nasce VERMELHO de propósito. Cada teste aqui reproduz um defeito
observado no caminho `mineração → funil → campanha` ANTES de qualquer correção,
e afirma o comportamento correto. Nenhum deles descreve código que já funciona.

## O defeito de origem

`funnel_factory` escolhe de 3 a 10 termos por sub-intenção em `selected` — e
exporta `final_campaign`, que é construída a partir de `deduped`. Os dois
conjuntos divergem sem aviso: a tela mostra a escolha, a campanha recebe a
mineração inteira. Medido no probe de abertura desta sprint:

    selecionadas : 5
    exportadas   : 8   (`lista_google_ads` com 8 linhas)

E o mesmo caminho trata ausência como zero, o que inverte o sinal econômico:

    'ipva tabela fipe' sem CPC   -> APROVADA  "Good Volume + Affordable CPC"
    'ipva tabela fipe' CPC 4,20  -> DESCARTADA

Não medir sai mais barato que medir. É o defeito que `Sinal` existe para fechar.

## A fronteira que estas contraprovas defendem

Oportunidade editorial e elegibilidade paga são DUAS decisões. A primeira já
tem dono — `app.validacao` — e não é reescrita aqui. A segunda não existia, e
não pode nascer herdando a primeira: tema apto a virar conteúdo não autoriza
termo a entrar em leilão, e `ready_for_campaign_plan` não autoriza campanha.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agents.mining.classifier import gold_miner_classify
from app.agents.mining.funnel_factory import funnel_factory, funnel_factory_com_conjuntos

HOJE = datetime(2026, 9, 3, tzinfo=timezone.utc)


# ── fixtures de dois nichos que NÃO podem colapsar ──────────────────────────
#
# BPC/LOAS (benefício assistencial federal) e IPVA (imposto estadual sobre
# veículo) são o par de prova: mesma língua, mesma origem institucional,
# intenções e riscos completamente diferentes. Se o motor os funde, ele não
# está lendo intenção — está lendo volume.


def _kw(termo, volume=None, cpc=None):
    """Uma keyword crua. Volume/CPC OMITIDOS quando ausentes — não zerados."""
    bruto = {"keyword": termo}
    if volume is not None:
        bruto["volume"] = volume
    if cpc is not None:
        bruto["cpc"] = cpc
    return bruto


def _funil(nome, ancora, sub_intencoes, rank=1):
    return {
        "funis_sugeridos": [
            {
                "rank": rank,
                "nome_funil": nome,
                "keyword_ancora": ancora,
                "volume_ancora": 90000,
                "metricas": {},
                "justificativa": "",
                "tags": [],
                "sub_intencoes": sub_intencoes,
            }
        ]
    }


def _sub(tipo, keywords, volume_sub=100000, descricao=""):
    return {"tipo": tipo, "descricao": descricao, "volume_sub": volume_sub, "keywords": keywords}


BPC_LOAS = _funil(
    "BPC LOAS",
    "bpc loas",
    [
        _sub(
            "ELEGIBILIDADE",
            [
                _kw("bpc loas quem tem direito", 90000, 1.10),
                _kw("bpc loas valor 2026", 60000, 0.90),
                _kw("bpc loas como dar entrada", 40000, 1.30),
                _kw("bpc loas prazo analise", 9000, 0.70),
                _kw("bpc loas negado o que fazer", 5000, 1.80),
                _kw("meu inss login", 480000, 0.05),
                _kw("inss telefone 135", 300000, 0.02),
                _kw("bpc loas advogado x concorrente", 1200, 6.40),
            ],
        )
    ],
)

IPVA = _funil(
    "IPVA",
    "ipva 2026",
    [
        _sub(
            "VALOR",
            [
                _kw("ipva 2026 tabela"),  # sem volume e sem CPC
                _kw("ipva 2026 parcelamento", 12000),  # sem CPC
                _kw("ipva 2026 consulta placa", 55000, 0.40),
                _kw("detran ipva 2026 boleto", 33000, 0.35),
                _kw("ipva 2026 desconto a vista", 21000, 0.55),
            ],
        )
    ],
)


def _item_e_conjunto(ai):
    """A fila JSON-safe e o conjunto vivo, da MESMA construção.

    O router serializa `factory_output` para o Supabase e para a tela, então
    `keywords_campanha.conjunto_pago` viaja como dicionário. O domínio e
    estas contraprovas precisam do objeto — e ele é o mesmo de que aquele
    dicionário saiu, nunca uma segunda montagem.
    """
    fila, conjuntos = funnel_factory_com_conjuntos(ai, today=HOJE)
    return fila[0], conjuntos[0]


def _selecionadas(item):
    return [k["keyword"] for sub in item["funnel_context"]["sub_intencoes_raw"] for k in sub["keywords"]]


def _exportadas(item):
    return [k["keyword"] for k in item["keywords_campanha"]["keywords_array"]]


# ── A e B: o conjunto exportado É o conjunto selecionado ────────────────────


def test_A_selecionadas_nao_viram_o_conjunto_inteiro():
    """A. Cinco keywords selecionadas não podem virar oito no conjunto exportado.

    Reproduzido em 2026-09-03 contra `funnel_factory` de origin/volc-os-v2:
    `selected` devolvia 5, `keywords_array` devolvia 8. As três a mais nunca
    passaram por escolha nenhuma — entraram porque `all_keywords_for_campaign`
    é alimentada de `deduped`.
    """
    item = funnel_factory(BPC_LOAS, today=HOJE)[0]
    assert sorted(_exportadas(item)) == sorted(_selecionadas(item))


def test_B_selected_e_final_campaign_nao_divergem_em_silencio():
    """B. `lista_google_ads` não pode ter mais linhas que a seleção."""
    item = funnel_factory(BPC_LOAS, today=HOJE)[0]
    linhas = [linha for linha in item["keywords_campanha"]["lista_google_ads"].splitlines() if linha.strip()]
    assert len(linhas) == len(_selecionadas(item))


def test_N_lista_google_ads_deriva_exatamente_de_selected():
    """N. `keywords_campanha.lista_google_ads` é derivada de `selected_keywords`.

    Não "quase": exatamente. Mesmo conjunto, sem acréscimo e sem perda.
    """
    from app.agents.mining.paid_eligibility import derivar_lista_google_ads

    item, conjunto = _item_e_conjunto(BPC_LOAS)
    assert item["keywords_campanha"]["lista_google_ads"] == derivar_lista_google_ads(conjunto)


# ── C: volume não compra intenção ───────────────────────────────────────────


def test_C_navegacional_de_alto_volume_nao_entra_automaticamente():
    """C. `meu inss login` com 480.000 buscas não vira keyword paga sozinha.

    Este é o defeito que o próprio Validador já documenta do lado editorial
    (`orquestrador.py`: "73% do eixo volume era gente procurando o telefone do
    Banco Pan"). Do lado pago ele continuava aberto: os dois termos de maior
    volume do funil BPC/LOAS são navegacional e suporte, e eram justamente os
    dois primeiros da lista exportada.
    """
    from app.agents.mining.paid_eligibility import INCLUDE

    item, conjunto = _item_e_conjunto(BPC_LOAS)
    decisoes = {d.termo: d for d in conjunto.candidates}

    for termo in ("meu inss login", "inss telefone 135"):
        assert decisoes[termo].decisao != INCLUDE, f"{termo!r} entrou por volume"
        assert termo not in _exportadas(item)


def test_C2_navegacional_perde_para_intencao_mesmo_com_volume_maior():
    """C. O termo de elegibilidade, com 1/5 do volume, sobrevive ao navegacional."""
    item = funnel_factory(BPC_LOAS, today=HOJE)[0]
    exportadas = _exportadas(item)
    assert "bpc loas quem tem direito" in exportadas
    assert "meu inss login" not in exportadas


# ── D e E: ausência não é zero ──────────────────────────────────────────────


def test_D_cpc_ausente_nao_vira_zero():
    """D. CPC ausente não vira 0 nem "barato"."""
    from app.agents.mining.paid_eligibility import AUSENTE

    _item, conjunto = _item_e_conjunto(IPVA)
    decisoes = {d.termo: d for d in conjunto.candidates}
    cpc = decisoes["ipva 2026 tabela"].cpc
    assert cpc.estado == AUSENTE
    assert cpc.valor is None


def test_D2_ausencia_nunca_pontua_melhor_que_medicao():
    """D. Não medir não pode sair mais barato que medir.

    Reproduzido: o MESMO termo era aprovado para Ads com o motivo "Good Volume
    + Affordable CPC" quando o CPC era desconhecido, e descartado quando o CPC
    medido era R$ 4,20. A ausência valia 0,00 e 0,00 passa em `cpc <= 0.60`.
    """
    sem_cpc = gold_miner_classify([{"keyword": "ipva tabela fipe", "volume": 8000}], today=HOJE)
    aprovadas = [k["keyword"] for k in sem_cpc["production_ads_queue"]]
    assert "ipva tabela fipe" not in aprovadas, (
        "CPC ausente foi lido como CPC barato: " f"{sem_cpc['production_ads_queue']}"
    )


def test_E_volume_ausente_nao_vira_zero_nem_sem_demanda():
    """E. Volume ausente não vira 0 nem "sem demanda"."""
    from app.agents.mining.paid_eligibility import AUSENTE

    _item, conjunto = _item_e_conjunto(IPVA)
    decisoes = {d.termo: d for d in conjunto.candidates}
    volume = decisoes["ipva 2026 tabela"].volume
    assert volume.estado == AUSENTE
    assert volume.valor is None


def test_E2_zero_confirmado_e_ausente_sao_estados_distintos():
    """E. `confirmed_zero` e `absent` não podem colapsar no mesmo destino.

    Hoje colapsam: `data_reliability` é LIDO em `classifier.py:162` e nunca é
    ESCRITO por nenhum produtor do repositório, então a regra R3 ("vol=0
    confirmed") nunca distingue nada — os dois estados caem no mesmo descarte.
    """
    from app.agents.mining.paid_eligibility import AUSENTE, ZERO_CONFIRMADO, Sinal

    ausente = Sinal.de_bruto({}, "volume", fonte="keyword_planner")
    confirmado = Sinal.de_bruto(
        {"volume": 0}, "volume", fonte="keyword_planner", medicao_confirmada=True
    )
    assert ausente.estado == AUSENTE
    assert confirmado.estado == ZERO_CONFIRMADO
    assert ausente.estado != confirmado.estado


def test_E3_zero_sem_confirmacao_nao_e_zero_confirmado():
    """E. Um `0` cru, sem prova de que o termo foi medido, é `unknown`."""
    from app.agents.mining.paid_eligibility import DESCONHECIDO, Sinal

    assert Sinal.de_bruto({"volume": 0}, "volume", fonte="merge").estado == DESCONHECIDO


def test_D3_media_de_cpc_nao_e_publicada_a_partir_de_ausencia():
    """D. `avg_cpc` não pode sair "0.00" quando nenhum CPC foi medido.

    Reproduzido: o funil IPVA publicava `stats.avg_cpc == "0.00"` com dois
    termos sem CPC nenhum. Uma média sem proveniência é pior que um buraco.
    """
    item = funnel_factory(IPVA, today=HOJE)[0]
    stats = item["keywords_campanha"]["stats"]
    assert stats["avg_cpc"] != "0.00"
    assert stats.get("avg_cpc_estado") is not None


def test_D4_o_humano_nao_le_zero_onde_o_dado_falta():
    """D. O texto que vai à tela não pode escrever "Vol: 0, CPC: 0.00" para
    um termo sem medição nenhuma. Foi assim que a ausência virou fato."""
    item = funnel_factory(IPVA, today=HOJE)[0]
    sub = item["funnel_context"]["sub_intencoes_raw"][0]
    superficies = [
        sub["keywords_text"],
        sub.get("keywords_retidas_text", ""),
        item["keywords_campanha"]["lista_clickup"],
    ]
    linhas = [
        l for texto in superficies for l in texto.splitlines() if "ipva 2026 tabela" in l
    ]
    assert linhas, "o termo retido sumiu de toda superfície legível"
    for linha in linhas:
        assert "Vol: 0" not in linha and "0.00" not in linha, linha


# ── F: as duas decisões são independentes ───────────────────────────────────


def test_F_tema_editorial_apto_com_todas_as_keywords_retidas():
    """F. Tema editorial apto e nenhuma keyword paga elegível é um estado VÁLIDO.

    É o caso mais comum de um tema institucional: vale escrever, não vale
    leiloar. O contrato precisa conseguir dizer isso sem contradição.
    """
    from app.agents.mining.ponte_editorial import OpportunityEditorialDecision, ponte

    editorial = OpportunityEditorialDecision.do_resumo(
        {
            "apto": True,
            "motivo": None,
            "indice": 0.71,
            "cobertura": 0.9,
            "perfil": "produzir",
            "sensores": {"limpos": True},
            "eixos": {"volume": {"nivel": "alto", "proveniencia": "medido", "motivo_ausencia": None}},
            "alertas": [],
        },
        tema="bpc loas",
    )
    _item, conjunto = _item_e_conjunto(
        _funil("Só navegacional", "inss", [_sub("NAVEGACIONAL", [_kw("meu inss login", 480000, 0.05)])])
    )
    visao = ponte(editorial, conjunto)

    assert visao["vale_produzir_conteudo"] is True
    assert visao["apto_para_midia_paga"] is False
    assert visao["conjunto_selecionado"] == []


def test_F2_editorial_nao_carrega_economia_de_ads():
    """F. O índice editorial não pode ser contaminado por spread/CPC.

    `app.validacao` declara `spread` como eixo sem medição ("CPC é comprável").
    A ponte lê o resumo editorial; ela não recalcula nem injeta economia paga.
    """
    from app.agents.mining.ponte_editorial import OpportunityEditorialDecision

    resumo = {"apto": True, "indice": 0.71, "cobertura": 0.9, "perfil": "produzir",
              "sensores": {"limpos": True}, "eixos": {}, "alertas": [], "motivo": None}
    editorial = OpportunityEditorialDecision.do_resumo(resumo, tema="bpc loas")
    assert editorial.indice == 0.71
    campos = editorial.como_dicionario()
    for proibido in ("cpc", "spread", "avg_cpc", "bid", "lance", "orcamento"):
        assert proibido not in campos, f"economia de Ads vazou para o objeto editorial: {proibido}"


# ── G: marca e concorrente não entram por expansão ──────────────────────────


def test_G_termo_de_concorrente_nao_entra_por_expansao():
    """G. Termo de concorrente exige decisão explícita — nunca expansão."""
    from app.agents.mining.paid_eligibility import HUMAN_REVIEW, INCLUDE

    item, conjunto = _item_e_conjunto(BPC_LOAS)
    decisoes = {d.termo: d for d in conjunto.candidates}
    alvo = decisoes["bpc loas advogado x concorrente"]
    assert alvo.decisao != INCLUDE
    assert alvo.decisao == HUMAN_REVIEW or alvo.riscos.get("marca_terceiro")
    assert "bpc loas advogado x concorrente" not in _exportadas(item)


def test_G2_termo_de_marca_nao_e_negativado_automaticamente():
    """G. Nem incluído automaticamente, NEM negativado automaticamente.

    Auto-negativa é o espelho do defeito, não a correção: bloqueia demanda real
    sem evidência de search term e sem revisão de overblocking.
    """
    _item, conjunto = _item_e_conjunto(BPC_LOAS)
    assert conjunto.negative_keywords == [], "o motor criou negativa sem search-term evidence"


# ── H: normalização não pode fundir intenções diferentes ────────────────────


def test_H_deduplicacao_nao_funde_sub_intencoes_distintas():
    """H. `bpc loas` em ELEGIBILIDADE e `BPC LOAS ` em NAVEGACIONAL não são um.

    Reproduzido: `deduplicate_keywords` normaliza com `lower().strip()` e, no
    passo `final_campaign`, colapsa entre sub-intenções — o par acima virava UMA
    linha rotulada NAVEGACIONAL, e a intenção de elegibilidade sumia da campanha
    sem aparecer em `keywords_removidas`.
    """
    funil = _funil(
        "H",
        "bpc loas",
        [
            _sub("ELEGIBILIDADE", [_kw("bpc loas", 100, 1.00)], volume_sub=100),
            _sub("NAVEGACIONAL", [_kw("BPC LOAS ", 900, 0.01)], volume_sub=900),
        ],
    )
    _item, conjunto = _item_e_conjunto(funil)
    candidatos = conjunto.candidates
    subintencoes = {d.subintencao for d in candidatos if d.termo_normalizado == "bpc loas"}
    assert subintencoes == {"ELEGIBILIDADE", "NAVEGACIONAL"}


# ── I, J, O: o conjunto aprovado é literal ──────────────────────────────────


def _conjunto_bpc():
    return _item_e_conjunto(BPC_LOAS)[1]


def test_I_hash_muda_se_o_termo_muda():
    from app.agents.mining.paid_eligibility import impressao_do_conjunto

    a = _conjunto_bpc()
    b = _conjunto_bpc()
    assert impressao_do_conjunto(a) == impressao_do_conjunto(b)
    b.selected_keywords[0].termo_normalizado = "outro termo"
    assert impressao_do_conjunto(b) != impressao_do_conjunto(a)


def test_I2_hash_muda_se_o_match_type_muda():
    from app.agents.mining.paid_eligibility import impressao_do_conjunto

    a = _conjunto_bpc()
    b = _conjunto_bpc()
    b.selected_keywords[0].match_type = "EXACT" if b.selected_keywords[0].match_type != "EXACT" else "PHRASE"
    assert impressao_do_conjunto(b) != impressao_do_conjunto(a)


def test_I3_hash_muda_se_a_subintencao_muda():
    from app.agents.mining.paid_eligibility import impressao_do_conjunto

    a = _conjunto_bpc()
    b = _conjunto_bpc()
    b.selected_keywords[0].subintencao = "OUTRA"
    assert impressao_do_conjunto(b) != impressao_do_conjunto(a)


def test_O_ordem_nao_muda_o_hash_e_isso_e_decidido():
    """O. A semântica é de CONJUNTO, decidida e testada — não acidente.

    Duas ordens do mesmo conjunto aprovam a mesma coisa. O que a ordem canônica
    faz é tornar a impressão reproduzível; ela não é parte do que se aprova.
    """
    from app.agents.mining.paid_eligibility import impressao_do_conjunto

    a = _conjunto_bpc()
    b = _conjunto_bpc()
    b.selected_keywords.reverse()
    assert impressao_do_conjunto(b) == impressao_do_conjunto(a)


def test_J_depois_de_aprovado_nada_acrescenta_keyword():
    """J. Após aprovação, nenhuma etapa posterior pode acrescentar keyword."""
    from app.agents.mining.paid_eligibility import (
        ConjuntoCongelado,
        PaidKeywordDecision,
        aprovar,
        impressao_do_conjunto,
    )

    conjunto = _conjunto_bpc()
    aprovado = aprovar(conjunto, aprovado_por="operador", hash_conferido=impressao_do_conjunto(conjunto))
    assert aprovado.approved_set_sha256 == aprovado.selected_set_sha256

    with pytest.raises(ConjuntoCongelado):
        aprovado.acrescentar(
            PaidKeywordDecision(termo="termo novo", termo_normalizado="termo novo", subintencao="X")
        )


def test_J2_aprovacao_recusa_hash_divergente():
    """J. Aprovar exige conferir a impressão do que se está aprovando."""
    from app.agents.mining.paid_eligibility import HashDivergente, aprovar

    with pytest.raises(HashDivergente):
        aprovar(_conjunto_bpc(), aprovado_por="operador", hash_conferido="0" * 64)


# ── K e L: o benchmark é prior, não regra ───────────────────────────────────


def test_K_prior_de_baixa_confianca_nao_vira_regra_dura():
    """K. Nenhum padrão com confiança baixa pode bloquear ou autorizar sozinho.

    O benchmark Webgo fecha com 35/35 playbooks em confiança baixa e nenhuma
    sequência sobrevivendo ao controle. Um prior nesse estado anota; não decide.
    """
    from app.agents.mining.paid_eligibility import PRIORS_DE_BENCHMARK

    assert PRIORS_DE_BENCHMARK, "os priors precisam ser declarados, não implícitos"
    for prior in PRIORS_DE_BENCHMARK:
        assert prior.confianca in ("alta", "media", "baixa", "nenhuma")
        if prior.confianca != "alta":
            assert prior.bloqueia is False, f"{prior.nome} bloqueia com confiança {prior.confianca}"
            assert prior.autoriza is False, f"{prior.nome} autoriza com confiança {prior.confianca}"


def test_L_evidencia_pos_lancamento_nao_justifica_selecao_inicial():
    """L. Search term de uma campanha não pode virar feature pré-lançamento dela."""
    from app.agents.mining.paid_eligibility import Evidencia, VazamentoDeDesfecho, decidir_keyword

    pos = Evidencia(fonte="search_term_view", momento="pos_lancamento", campanha_ref="camp-1")
    with pytest.raises(VazamentoDeDesfecho):
        decidir_keyword(
            {"keyword": "bpc loas quem tem direito", "volume": 90000, "cpc": 1.10},
            subintencao="ELEGIBILIDADE",
            evidencias=[pos],
            momento_da_decisao="pre_lancamento",
            campanha_ref="camp-1",
        )


# ── M: desconhecido não abre o portão ───────────────────────────────────────


def test_M_desconhecido_nao_produz_ready_for_campaign_plan():
    """M. Sem teto econômico do dono, o conjunto não fica pronto — fica bloqueado."""
    _item, conjunto = _item_e_conjunto(IPVA)  # owner_ceiling nunca declarado
    assert conjunto.owner_ceiling is None
    assert conjunto.ready_for_campaign_plan is False
    assert "teto_economico_desconhecido" in conjunto.blockers


def test_M2_ready_for_campaign_plan_nao_autoriza_campanha():
    """M. O portão diz que o CONJUNTO está preparável — nada além disso.

    Conta, destino pago, mensuração e aprovação continuam sendo portões de
    outras lanes, e o objeto tem que dizer isso em voz alta.
    """
    from app.agents.mining.paid_eligibility import PORTOES_EXTERNOS

    conjunto = _conjunto_bpc()
    assert set(PORTOES_EXTERNOS) >= {"conta", "destino_pago", "mensuracao", "aprovacao_humana"}
    for portao in PORTOES_EXTERNOS:
        assert conjunto.portoes_externos_pendentes[portao] == "nao_avaliado_aqui"


# ── separação semântica entre nichos ────────────────────────────────────────


def test_dois_nichos_nao_colapsam_no_mesmo_conjunto():
    """BPC/LOAS e IPVA não compartilham cluster, intenção nem conjunto pago."""
    bpc = _item_e_conjunto(BPC_LOAS)[1]
    ipva = _item_e_conjunto(IPVA)[1]

    from app.agents.mining.paid_eligibility import impressao_do_conjunto

    assert impressao_do_conjunto(bpc) != impressao_do_conjunto(ipva)
    termos_bpc = {d.termo_normalizado for d in bpc.selected_keywords}
    termos_ipva = {d.termo_normalizado for d in ipva.selected_keywords}
    assert termos_bpc.isdisjoint(termos_ipva)


def test_arquetipos_separam_governo_de_imposto_estadual():
    """Elegibilidade a benefício e valor de imposto não são a mesma intenção."""
    from app.agents.mining.paid_eligibility import arquetipos

    assert "elegibilidade" in arquetipos("bpc loas quem tem direito")
    assert "valor_preco" in arquetipos("ipva 2026 tabela")
    assert "navegacional" in arquetipos("meu inss login")
    assert "suporte_acesso" in arquetipos("inss telefone 135")
    assert arquetipos("bpc loas quem tem direito") != arquetipos("ipva 2026 tabela")


# ── reconciliação com o contrato de critério que já existe ──────────────────


def test_conjunto_aprovado_vira_criterio_do_contrato_existente():
    """A ponte paga aterrissa em `volc_ads.campanha.criterio.Criterio`.

    Não num segundo contrato paralelo. `Criterio` já valida match type, nível e
    origem, e já recusa `SEARCH_TERM` sem evidência medida — nada disso é
    reimplementado do lado da mineração.
    """
    from app.agents.mining.paid_eligibility import (
        aprovar,
        impressao_do_conjunto,
        para_criterios_de_campanha,
    )

    conjunto = _conjunto_bpc()
    aprovar(conjunto, aprovado_por="operador", hash_conferido=impressao_do_conjunto(conjunto))
    criterios = para_criterios_de_campanha(conjunto)

    assert [c.texto for c in criterios] == [d.termo for d in conjunto.selected_keywords]
    assert all(c.origem == "PAUTADOR" for c in criterios)
    assert all(c.negativa is False for c in criterios), "o motor criou negativa sozinho"
    assert all(c.nivel == "AD_GROUP" for c in criterios)
    assert all(c.aprovado_por == "operador" for c in criterios)


def test_conjunto_nao_aprovado_nao_vira_criterio():
    """J. Sem impressão aprovada não há critério — nem por engano."""
    from app.agents.mining.paid_eligibility import (
        ConjuntoCongelado,
        para_criterios_de_campanha,
    )

    with pytest.raises(ConjuntoCongelado):
        para_criterios_de_campanha(_conjunto_bpc())


# ── E (fechamento da cadeia): a ausência sobrevive ao primeiro salto ────────


def test_E4_gold_extractor_distingue_metrica_ausente_de_zero_medido():
    """E. Sem estado na ORIGEM, `absent` e `confirmed_zero` são irrecuperáveis.

    Reproduzido: uma keyword sem bloco `keywordIdeaMetrics` e outra com zeros
    MEDIDOS saíam byte a byte idênticas de `extract_gold` — volume 0, cpc 0.0,
    competition_index 0 — e nenhuma camada a jusante podia recuperar a
    diferença, nem `Sinal.de_bruto`, que existe para preservá-la.
    """
    from app.agents.mining.gold_extractor import extract_gold

    saida = extract_gold(
        {
            "results": [
                {"text": "termo sem metricas", "keywordIdeaMetrics": {}},
                {
                    "text": "termo com zero medido",
                    "keywordIdeaMetrics": {"avgMonthlySearches": 0, "averageCpcMicros": 0},
                },
            ],
            "loop_iteration": 0,
            "seed_keyword": "s",
            "master_bank": [],
        }
    )
    banco = {k["keyword"]: k for k in saida["master_bank"]}
    assert banco["termo sem metricas"]["volume_estado"] == "absent"
    assert banco["termo com zero medido"]["volume_estado"] == "measured"
    assert banco["termo sem metricas"]["cpc_estado"] == "absent"
    assert banco["termo com zero medido"]["cpc_estado"] == "measured"


def test_E5_merger_propaga_estado_e_nunca_promove_a_medido():
    """E. Banco sem estado declarado não vira `measured` por omissão."""
    from app.agents.mining.merger import final_classifier

    saida = final_classifier(
        [
            {
                "seed_keyword": "s",
                "loop_iteration": 0,
                "master_bank": [
                    {"keyword": "com estado", "volume": 0, "volume_estado": "measured"},
                    {"keyword": "sem estado", "volume": 0},
                ],
            }
        ]
    )
    fila = {k["keyword"]: k for k in saida["build_queue"]}
    assert fila["com estado"]["volume_estado"] == "measured"
    assert fila["sem estado"]["volume_estado"] == "unknown"


def test_E6_estado_da_origem_vence_o_palpite_da_camada():
    """E. Com `<campo>_estado` presente, `Sinal` para de adivinhar."""
    from app.agents.mining.paid_eligibility import AUSENTE, ZERO_CONFIRMADO, Sinal

    ausente = Sinal.de_bruto(
        {"volume": 0, "volume_estado": "absent"}, "volume", fonte="keyword_planner"
    )
    medido_zero = Sinal.de_bruto(
        {"volume": 0, "volume_estado": "measured"}, "volume", fonte="keyword_planner"
    )
    assert ausente.estado == AUSENTE and ausente.valor is None
    assert medido_zero.estado == ZERO_CONFIRMADO and medido_zero.valor == 0


def test_E7_classifier_nao_aprova_com_cpc_declarado_ausente():
    """D. Um `0` declarado ausente não passa mais em `cpc <= 0.60`."""
    from app.agents.mining.classifier import gold_miner_classify

    saida = gold_miner_classify(
        [{"keyword": "termo caro sem preco", "volume": 8000, "cpc": 0, "cpc_estado": "absent"}],
        today=HOJE,
    )
    assert [k["keyword"] for k in saida["production_ads_queue"]] == []


# ── rodada corretiva: achados reproduzidos das revisões cruzadas ────────────


def test_R1_lexico_nao_retem_termo_comercial_legitimo():
    """Revisão externa: `"meu "` e `" app"` sozinhos retinham termo comercial.

    Reproduzido antes da correção: `vender meu precatorio`,
    `simular meu financiamento` e `seguro auto app` saíam HOLD por
    navegacional. Reter demais é o mesmo defeito do outro lado da balança.
    """
    from app.agents.mining.paid_eligibility import INCLUDE, decidir_keyword

    for termo in ("vender meu precatorio", "simular meu financiamento", "seguro auto app"):
        d = decidir_keyword({"keyword": termo, "volume": 50000, "cpc": 2.0}, subintencao="X")
        assert d.decisao == INCLUDE, f"{termo!r} retido indevidamente: {d.motivos}"


def test_R2_comparacao_nao_e_marca_de_terceiro():
    """Revisão externa: `" x "` em `_MARCA_TERCEIRO` mandava comparação genérica
    para revisão humana. `clt x pj` não cita marca de ninguém."""
    from app.agents.mining.paid_eligibility import INCLUDE, decidir_keyword

    for termo in ("advogado presencial x online", "clt x pj"):
        d = decidir_keyword({"keyword": termo, "volume": 50000, "cpc": 2.0}, subintencao="X")
        assert d.decisao == INCLUDE
        assert d.riscos["marca_terceiro"] is False


def test_R3_marca_de_terceiro_declarada_pelo_operador_e_respeitada():
    """G. O léxico não conhece marca que ninguém declarou — e diz isso.

    `jusbrasil consulta` passava como INCLUDE porque nenhum marcador
    relacional aparece nele. A cobertura por vocabulário é declaradamente
    parcial; a lista do operador é o que a completa.
    """
    from app.agents.mining.paid_eligibility import HUMAN_REVIEW, INCLUDE, decidir_keyword

    sem_lista = decidir_keyword({"keyword": "jusbrasil consulta", "volume": 9000, "cpc": 1.0}, subintencao="X")
    com_lista = decidir_keyword(
        {"keyword": "jusbrasil consulta", "volume": 9000, "cpc": 1.0},
        subintencao="X",
        marcas_de_terceiro=["jusbrasil"],
    )
    assert sem_lista.decisao == INCLUDE
    assert com_lista.decisao == HUMAN_REVIEW


def test_R4_dedup_funde_campos_em_vez_de_descartar_medicao():
    """Revisão interna: a troca em bloco jogava fora o CPC medido do perdedor.

    Entrada concreta, numa sub-intenção só: a grafia de maior volume não tinha
    CPC, a de menor volume tinha CPC medido. O vencedor levava tudo, o CPC
    sumia, e a decisão caía de INCLUDE para EXPERIMENT por um dado que a
    mineração TINHA.
    """
    from app.agents.mining.paid_eligibility import INCLUDE, MEDIDO

    funil = _funil(
        "dup",
        "ipva",
        [
            _sub(
                "VALOR",
                [
                    {"keyword": "ipva 2026 consulta", "volume": 30000},
                    {"keyword": "IPVA 2026 Consulta", "volume": 28000, "cpc": 0.40},
                ],
            )
        ],
    )
    _item, conjunto = _item_e_conjunto(funil)
    assert len(conjunto.candidates) == 1
    d = conjunto.candidates[0]
    assert d.volume.valor == 30000 and d.volume.estado == MEDIDO
    assert d.cpc.valor == 0.40 and d.cpc.estado == MEDIDO
    assert d.decisao == INCLUDE


def test_R5_reescrita_de_ano_nao_produz_termo_malformado():
    """Revisão interna: `replace` cego transformava `irpf 2025/2026` em
    `irpf 2026/2026` — uma keyword que não é de ninguém, exportada assim."""
    funil = _funil(
        "ano",
        "irpf",
        [
            _sub(
                "VALOR",
                [
                    {"keyword": "declaracao irpf 2025/2026", "volume": 40000, "cpc": 0.80},
                    {"keyword": "calendario pis 2025", "volume": 50000, "cpc": 0.10},
                    {"keyword": "tabela 12025 codigo", "volume": 25000, "cpc": 0.30},
                ],
            )
        ],
    )
    _item, conjunto = _item_e_conjunto(funil)
    termos = {d.termo for d in conjunto.candidates}
    assert "declaracao irpf 2025/2026" in termos, "o ano composto foi reescrito"
    assert "calendario pis 2026" in termos, "o ano isolado não foi normalizado"
    assert "tabela 12025 codigo" in termos, "dígitos internos foram reescritos"


def test_R6_proveniencia_da_reescrita_chega_a_saida():
    """Revisão interna: `original` era escrito e lido por ninguém."""
    funil = _funil("ano", "pis", [_sub("VALOR", [{"keyword": "calendario pis 2025", "volume": 50000, "cpc": 0.10}])])
    item, conjunto = _item_e_conjunto(funil)
    assert conjunto.candidates[0].original == "calendario pis 2025"
    assert item["keywords_campanha"]["keywords_array"][0]["original"] == "calendario pis 2025"


def test_R7_normalizacao_dobra_acento_para_keyword_positiva():
    """Revisão interna: as duas grafias sobreviviam e somavam volume duas vezes.

    A regra da casa já estava escrita em `volc_ads.campanha.criterio.chave`: o
    acento se preserva na NEGATIVA (que não expande para variantes próximas) e
    se dobra na keyword POSITIVA (onde as duas grafias competiriam entre si).
    """
    from app.agents.mining.paid_eligibility import normalizar_termo

    assert normalizar_termo("Declaração IPVA 2026") == normalizar_termo("declaracao ipva 2026")


def test_R8_congruencia_nao_avaliada_bloqueia_o_conjunto_nao_a_keyword():
    """M. Desconhecido não abre o portão — e não recusa o termo tampouco."""
    from app.agents.mining.paid_eligibility import INCLUDE

    _item, conjunto = _item_e_conjunto(BPC_LOAS)
    assert conjunto.selected_keywords, "o termo continua elegível"
    assert all(d.decisao == INCLUDE for d in conjunto.selected_keywords)
    assert "congruencia_nao_avaliada" in conjunto.blockers
    assert conjunto.ready_for_campaign_plan is False


def test_R9_exposicao_por_variante_proxima_fica_escrita():
    """Revisão externa: reter `meu inss login` não impede que uma busca por ele
    acione um termo INCLUÍDO — variantes próximas valem para EXACT e PHRASE.

    O motor não fecha isso (negativa exige search-term evidence, que só existe
    depois do lançamento). Ele declara.
    """
    _item, conjunto = _item_e_conjunto(BPC_LOAS)
    assert any("variante_proxima" in a for a in conjunto.alertas)
    assert all(
        "match_type_nao_isola_variantes_proximas" in d.alertas
        for d in conjunto.selected_keywords
    )


def test_R10_estado_sobrevive_ate_production_ads_queue():
    """Codex: os estados morriam no classificador, e `production_ads_queue` é
    consumida direto por `volc_ads.pautador_ponte` para montar o Brief."""
    from app.agents.mining.classifier import gold_miner_classify

    saida = gold_miner_classify(
        [{"keyword": "termo titan", "volume": 90000, "cpc": 0, "cpc_estado": "absent"}],
        today=HOJE,
    )
    fila = saida["production_ads_queue"]
    assert fila and fila[0]["cpc_estado"] == "absent"
    assert fila[0]["volume_estado"] == "measured"


def test_R11_impressao_tem_semantica_de_conjunto_de_verdade():
    """Revisão interna: `sorted` sobre gerador preservava duplicatas, então a
    impressão dependia de quantas vezes o termo foi minerado."""
    from app.agents.mining.paid_eligibility import impressao_de_decisoes

    conjunto = _conjunto_bpc()
    uma = impressao_de_decisoes(conjunto.selected_keywords)
    duas = impressao_de_decisoes(list(conjunto.selected_keywords) + list(conjunto.selected_keywords))
    assert uma == duas
