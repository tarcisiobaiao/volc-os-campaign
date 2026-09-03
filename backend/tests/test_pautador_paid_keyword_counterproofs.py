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
from app.agents.mining.funnel_factory import funnel_factory

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

    item = funnel_factory(BPC_LOAS, today=HOJE)[0]
    conjunto = item["keywords_campanha"]["conjunto_pago"]
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

    item = funnel_factory(BPC_LOAS, today=HOJE)[0]
    decisoes = {d.termo: d for d in item["keywords_campanha"]["conjunto_pago"].candidates}

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

    item = funnel_factory(IPVA, today=HOJE)[0]
    decisoes = {d.termo: d for d in item["keywords_campanha"]["conjunto_pago"].candidates}
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

    item = funnel_factory(IPVA, today=HOJE)[0]
    decisoes = {d.termo: d for d in item["keywords_campanha"]["conjunto_pago"].candidates}
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
    texto = item["funnel_context"]["sub_intencoes_raw"][0]["keywords_text"]
    linha = next(l for l in texto.splitlines() if "ipva 2026 tabela" in l)
    assert "Vol: 0," not in linha and "CPC: 0.00" not in linha


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
    item = funnel_factory(
        _funil("Só navegacional", "inss", [_sub("NAVEGACIONAL", [_kw("meu inss login", 480000, 0.05)])]),
        today=HOJE,
    )[0]
    visao = ponte(editorial, item["keywords_campanha"]["conjunto_pago"])

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

    item = funnel_factory(BPC_LOAS, today=HOJE)[0]
    decisoes = {d.termo: d for d in item["keywords_campanha"]["conjunto_pago"].candidates}
    alvo = decisoes["bpc loas advogado x concorrente"]
    assert alvo.decisao != INCLUDE
    assert alvo.decisao == HUMAN_REVIEW or alvo.riscos.get("marca_terceiro")
    assert "bpc loas advogado x concorrente" not in _exportadas(item)


def test_G2_termo_de_marca_nao_e_negativado_automaticamente():
    """G. Nem incluído automaticamente, NEM negativado automaticamente.

    Auto-negativa é o espelho do defeito, não a correção: bloqueia demanda real
    sem evidência de search term e sem revisão de overblocking.
    """
    item = funnel_factory(BPC_LOAS, today=HOJE)[0]
    conjunto = item["keywords_campanha"]["conjunto_pago"]
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
    item = funnel_factory(funil, today=HOJE)[0]
    candidatos = item["keywords_campanha"]["conjunto_pago"].candidates
    subintencoes = {d.subintencao for d in candidatos if d.termo_normalizado == "bpc loas"}
    assert subintencoes == {"ELEGIBILIDADE", "NAVEGACIONAL"}


# ── I, J, O: o conjunto aprovado é literal ──────────────────────────────────


def _conjunto_bpc():
    return funnel_factory(BPC_LOAS, today=HOJE)[0]["keywords_campanha"]["conjunto_pago"]


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
    item = funnel_factory(IPVA, today=HOJE)[0]  # owner_ceiling nunca declarado
    conjunto = item["keywords_campanha"]["conjunto_pago"]
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
    bpc = funnel_factory(BPC_LOAS, today=HOJE)[0]["keywords_campanha"]["conjunto_pago"]
    ipva = funnel_factory(IPVA, today=HOJE)[0]["keywords_campanha"]["conjunto_pago"]

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
