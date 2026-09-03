"""CONTRAPROVAS DO CAMINHO REAL — o conjunto aprovado e o nascimento da campanha.

O motor de elegibilidade estava correto e não decidia nada:
`para_criterios_de_campanha()` não tinha chamador de produção, e `/provar` —
com `/subir` atrás dele — continuava tirando as keywords positivas do cockpit,
que as tira de `production_ads_queue`, a fila BRUTA da mineração.

Um conjunto de 3 selecionadas convivia com um pedido de 8 termos, e nada no
sistema notava a diferença. Estes testes exercem o portão que fecha isso, e
todos exercem o caminho REAL — `portao_conjunto_pago`, o mesmo módulo que
`/provar` e `/subir` chamam antes de montar qualquer coisa.

⚠️ Nenhum teste aqui alcança a rede. A recusa acontece ANTES de `preparar()`,
portanto antes de qualquer `validate_only` — que é leitura, mas ainda é rede e
ainda é conta real.
"""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.agents.mining import portao_conjunto_pago as portao
from app.agents.mining.funnel_factory import funnel_factory_com_conjuntos
from app.agents.mining.paid_eligibility import aprovar, impressao_do_conjunto

HOJE = datetime(2026, 9, 3, tzinfo=timezone.utc)


# ── o funil BPC/LOAS: 8 termos brutos, 3 elegíveis e selecionados ───────────


def _kw(termo, volume=None, cpc=None):
    bruto = {"keyword": termo}
    if volume is not None:
        bruto["volume"] = volume
    if cpc is not None:
        bruto["cpc"] = cpc
    return bruto


BPC_LOAS = {
    "funis_sugeridos": [
        {
            "rank": 1, "nome_funil": "BPC LOAS", "keyword_ancora": "bpc loas",
            "volume_ancora": 90000, "metricas": {}, "justificativa": "", "tags": [],
            "sub_intencoes": [
                {
                    "tipo": "ELEGIBILIDADE", "descricao": "", "volume_sub": 100000,
                    "keywords": [
                        _kw("bpc loas quem tem direito", 90000, 1.10),
                        _kw("bpc loas valor 2026", 60000, 0.90),
                        _kw("bpc loas como dar entrada", 40000, 1.30),
                        _kw("bpc loas prazo analise", 9000, 0.70),
                        _kw("bpc loas negado o que fazer", 5000, 1.80),
                        _kw("meu inss login", 480000, 0.05),
                        _kw("inss telefone 135", 300000, 0.02),
                        _kw("bpc loas advogado x concorrente", 1200, 6.40),
                    ],
                }
            ],
        }
    ]
}

TERMOS_BRUTOS = {k["keyword"] for k in BPC_LOAS["funis_sugeridos"][0]["sub_intencoes"][0]["keywords"]}
assert len(TERMOS_BRUTOS) == 8


def _cluster(*, aprovado: bool, teto: float | None = 5.0, congruencia: str = "congruente"):
    """Um cluster como ele é PERSISTIDO — `factory_output` cru, do jeito que
    `pautador_keyword_clusters` guarda e que `pp.carregar` devolve."""
    ai = copy.deepcopy(BPC_LOAS)
    fila, conjuntos = funnel_factory_com_conjuntos(ai, today=HOJE, teto_do_dono=teto)
    conjunto = conjuntos[0]
    for d in conjunto.candidates:
        d.congruencia = congruencia
    if congruencia == "congruente":
        # avaliada e congruente: o bloqueador correspondente sai. Quando ela
        # NÃO foi avaliada o bloqueador fica, que é o ponto do test_6c.
        conjunto.blockers = [b for b in conjunto.blockers if b != "congruencia_nao_avaliada"]
    if aprovado:
        aprovar(conjunto, aprovado_por="operador", hash_conferido=impressao_do_conjunto(conjunto))
    fila[0]["keywords_campanha"]["conjunto_pago"] = conjunto.como_dicionario()
    return {"id": 1, "opportunity_id": 104, "factory_output": fila,
            "production_ads_queue": [{"keyword": t} for t in sorted(TERMOS_BRUTOS)]}


def _cinco_selecionadas():
    """O caso de cinco: elegibilidade + política, com o teto declarado.

    Os três de maior volume passam o corte por volume; `prazo analise` e
    `negado o que fazer` são elegíveis e ficariam de fora por quantidade — a
    política é afrouxada aqui para que o conjunto tenha exatamente 5, que é o
    número que o integrador pediu para ver virar 5 critérios.
    """
    from app.agents.mining import paid_eligibility as pe

    ai = copy.deepcopy(BPC_LOAS)
    original = pe.VOLUME_THRESHOLD
    try:
        pe.VOLUME_THRESHOLD = 1  # todo elegível passa o corte
        fila, conjuntos = funnel_factory_com_conjuntos(ai, today=HOJE, teto_do_dono=10.0)
    finally:
        pe.VOLUME_THRESHOLD = original
    conjunto = conjuntos[0]
    for d in conjunto.candidates:
        d.congruencia = "congruente"
    conjunto.blockers = [b for b in conjunto.blockers if b != "congruencia_nao_avaliada"]
    aprovar(conjunto, aprovado_por="operador", hash_conferido=impressao_do_conjunto(conjunto))
    fila[0]["keywords_campanha"]["conjunto_pago"] = conjunto.como_dicionario()
    return {"factory_output": fila}, conjunto


# ── 1 · /provar recusa conjunto não aprovado, ANTES da rede ────────────────


def test_1_provar_recusa_conjunto_nao_aprovado():
    """Aprovação é o que separa uma lista minerada de um conjunto de campanha."""
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.criterios_do_cluster(_cluster(aprovado=False))
    assert e.value.codigo == portao.NAO_APROVADO


def test_1b_provar_recusa_cluster_sem_conjunto_nenhum():
    # Sem fila e sem factory_output não há assinatura de produtor externo —
    # é simplesmente ausência, e o código tem de dizer ausência.
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.criterios_do_cluster({"id": 1, "opportunity_id": 104})
    assert e.value.codigo == portao.CONJUNTO_AUSENTE
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.criterios_do_cluster(None)
    assert e.value.codigo == portao.CONJUNTO_AUSENTE


# ── 2 · /provar recusa hash divergente ─────────────────────────────────────


def test_2_provar_recusa_hash_divergente():
    """O JSON persistido foi editado depois da aprovação.

    A impressão é RECALCULADA das decisões reidratadas, nunca lida do
    registro — confiar no hash gravado seria pedir ao registro que ateste a si
    mesmo.
    """
    cluster = _cluster(aprovado=True)
    conjunto = cluster["factory_output"][0]["keywords_campanha"]["conjunto_pago"]
    conjunto["selected_keywords"][0]["termo"] = "cassino online"
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.criterios_do_cluster(cluster)
    assert e.value.codigo == portao.HASH_DIVERGENTE


def test_2b_acrescimo_posterior_a_aprovacao_invalida_o_selo():
    """Mutação após a aprovação invalida o selo — inclusive acréscimo."""
    cluster = _cluster(aprovado=True)
    conjunto = cluster["factory_output"][0]["keywords_campanha"]["conjunto_pago"]
    conjunto["selected_keywords"].append(dict(conjunto["human_review_keywords"][0]))
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.criterios_do_cluster(cluster)
    assert e.value.codigo == portao.HASH_DIVERGENTE


# ── 3 · 5 selecionadas = 5 critérios reais ─────────────────────────────────


def test_3_cinco_selecionadas_produzem_cinco_criterios():
    cluster, conjunto = _cinco_selecionadas()
    assert len(conjunto.selected_keywords) == 5, [d.termo for d in conjunto.selected_keywords]
    _c, criterios = portao.criterios_do_cluster(cluster)
    assert len(criterios) == 5
    assert [c.texto for c in criterios] == [d.termo for d in conjunto.selected_keywords]
    assert all(c.negativa is False for c in criterios)
    assert all(c.origem == "PAUTADOR" for c in criterios)


def test_3b_a_selecao_por_grupo_desce_do_conjunto():
    """`keywords_por_grupo` é o que impede o construtor de montar o grupo
    INTEIRO a partir do cockpit — a fila bruta — quando `usar_todas` sumiu."""
    cluster, conjunto = _cinco_selecionadas()
    c, _ = portao.criterios_do_cluster(cluster)
    por_grupo = portao.keywords_por_grupo(c)
    assert sum(len(v) for v in por_grupo.values()) == 5
    assert set(por_grupo) == {"ELEGIBILIDADE"}


# ── 4 · os 8 brutos jamais reaparecem; navegacionais não vazam ─────────────


def test_4_os_oito_brutos_nunca_reaparecem_no_pedido():
    cluster, _ = _cinco_selecionadas()
    _c, criterios = portao.criterios_do_cluster(cluster)
    textos = {c.texto for c in criterios}
    assert len(textos) == 5
    assert textos < TERMOS_BRUTOS, "o conjunto tem de ser subconjunto ESTRITO dos brutos"
    assert TERMOS_BRUTOS - textos == {
        "meu inss login", "inss telefone 135", "bpc loas advogado x concorrente",
    }


def test_4b_navegacionais_retidos_nao_vazam_pela_production_ads_queue():
    """O cluster CARREGA a fila bruta com os oito termos. Ela não é caminho.

    `production_ads_queue` continua no registro — é fila de mineração, e
    mineração pode ser ampla. O que deixou de existir é a porta pela qual ela
    virava conjunto de campanha.
    """
    cluster, _ = _cinco_selecionadas()
    cluster["production_ads_queue"] = [{"keyword": t} for t in sorted(TERMOS_BRUTOS)]
    _c, criterios = portao.criterios_do_cluster(cluster)
    textos = {c.texto for c in criterios}
    for retido in ("meu inss login", "inss telefone 135"):
        assert retido in {k["keyword"] for k in cluster["production_ads_queue"]}
        assert retido not in textos


# ── 5 · n8n configurado não contorna o contrato ────────────────────────────


def test_5_cluster_produzido_pelo_n8n_falha_fechado():
    """O fluxo n8n grava cluster com fila e SEM `conjunto_pago`.

    Ele continua minerando. O que ele não faz é virar campanha — e o erro diz
    o nome disso em vez de deixar a fila bruta passar por conjunto aprovado.
    """
    cluster_n8n = {
        "id": 9, "opportunity_id": 104,
        "production_ads_queue": [{"keyword": t} for t in sorted(TERMOS_BRUTOS)],
        "factory_output": [{"keywords_campanha": {
            "lista_google_ads": "\n".join(sorted(TERMOS_BRUTOS)),
            "keywords_array": [{"keyword": t} for t in sorted(TERMOS_BRUTOS)],
        }}],
    }
    assert portao.parece_produzido_fora_do_motor(cluster_n8n) is True
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.criterios_do_cluster(cluster_n8n)
    assert e.value.codigo == portao.N8N_SEM_CONTRATO == "N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED"


def test_5b_cluster_do_motor_python_nao_e_confundido_com_n8n():
    assert portao.parece_produzido_fora_do_motor(_cluster(aprovado=True)) is False


def test_5c_autoridade_operacional_e_unica_e_nomeada():
    assert portao.AUTORIDADE == "python:app.agents.mining.paid_eligibility"


# ── 6 · CPC/volume ausente nunca vira zero, nem na reidratação ─────────────


def test_6_cpc_e_volume_ausentes_sobrevivem_a_reidratacao():
    """A reidratação é o ponto onde a ausência morreria de novo: um `None`
    lido de JSON vira `0` em qualquer leitor descuidado."""
    from app.agents.mining.paid_eligibility import AUSENTE, conjunto_de_dicionario

    ai = {"funis_sugeridos": [{
        "rank": 1, "nome_funil": "IPVA", "keyword_ancora": "ipva", "volume_ancora": 1,
        "metricas": {}, "justificativa": "", "tags": [],
        "sub_intencoes": [{"tipo": "VALOR", "descricao": "", "volume_sub": 1, "keywords": [
            {"keyword": "ipva 2026 tabela"},
            {"keyword": "ipva 2026 consulta placa", "volume": 55000, "cpc": 0.40},
        ]}]}]}
    fila, conjuntos = funnel_factory_com_conjuntos(ai, today=HOJE, teto_do_dono=5.0)
    reidratado = conjunto_de_dicionario(conjuntos[0].como_dicionario())
    sem_dado = next(d for d in reidratado.candidates if d.termo == "ipva 2026 tabela")
    assert sem_dado.volume.estado == AUSENTE and sem_dado.volume.valor is None
    assert sem_dado.cpc.estado == AUSENTE and sem_dado.cpc.valor is None


def test_6b_teto_nao_declarado_continua_bloqueador_nomeado():
    """Nenhum valor é inventado para destravar: falta teto, o portão diz qual."""
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.criterios_do_cluster(_cluster(aprovado=True, teto=None))
    assert e.value.codigo == portao.BLOQUEADO
    assert "teto_economico_desconhecido" in e.value.bloqueadores


def test_6c_congruencia_nao_avaliada_continua_bloqueador_nomeado():
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.criterios_do_cluster(_cluster(aprovado=True, congruencia="nao_avaliada"))
    assert e.value.codigo == portao.BLOQUEADO
    assert "congruencia_nao_avaliada" in e.value.bloqueadores


# ── 7 · /subir não ultrapassa uma recusa herdada de /provar ────────────────


def test_7_subir_herda_a_recusa_de_provar():
    """As duas rotas chamam o MESMO portão sobre o MESMO cluster.

    A recusa é herdada estruturalmente, não por disciplina de quem chama na
    ordem certa: `/subir` reprova o plano antes de escrever, e se montasse a
    `Escolha` pelo caminho antigo ultrapassaria, por reconstrução, uma recusa
    que `/provar` já tinha dado.
    """
    import inspect

    from app.routers import trafego

    fonte = inspect.getsource(trafego)
    assert fonte.count("portao_pago.criterios_do_cluster(") == 2, (
        "as duas rotas precisam passar pelo portão"
    )
    assert fonte.count("portao_pago.keywords_por_grupo(") == 2
    assert fonte.count("except portao_pago.PortaoDoConjuntoPago as exc:") == 2
    # e nenhuma delas pode voltar a montar o grupo inteiro do cockpit
    assert "grupos_usar_todas=frozenset(g.tipo for g in body.grupos if g.usar_todas)" not in fonte


def test_7b_o_portao_roda_antes_de_qualquer_rede():
    """A ordem no código: portão, depois cockpit, depois `preparar()`."""
    import inspect

    from app.routers import trafego

    fonte = inspect.getsource(trafego)
    portao_i = fonte.index("portao_pago.criterios_do_cluster(")
    preparar_i = fonte.index("sb.preparar(")
    assert portao_i < preparar_i, "o portão tem de vir antes da chamada ao Google"


# ── 8 · zero mutate ────────────────────────────────────────────────────────


def test_8_o_portao_nao_alcanca_o_google():
    """Nenhum caminho do portão importa cliente Google nem chama mutate."""
    import ast
    import inspect

    from app.agents.mining import portao_conjunto_pago

    # AST e não substring: a docstring do módulo FALA de `validate_only` para
    # explicar por que a recusa vem antes dele. Um teste que confunde a
    # explicação com a chamada proíbe documentar o próprio invariante.
    arvore = ast.parse(inspect.getsource(portao_conjunto_pago))

    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module.split(".")[0])
    for rede in ("httpx", "requests", "urllib", "socket", "google", "googleads"):
        assert rede not in importados, f"o portão importa {rede!r}"

    nomes = {
        no.attr for no in ast.walk(arvore) if isinstance(no, ast.Attribute)
    } | {
        no.id for no in ast.walk(arvore) if isinstance(no, ast.Name)
    }
    for proibido in ("mutate", "validate_only", "MutateOperation", "GoogleAdsClient"):
        assert proibido not in nomes, f"{proibido!r} é referenciado como código no portão"


def test_8b_nenhuma_negativa_nasce_deste_caminho():
    """Esta rodada não gera negativa. Close variants seguem risco declarado."""
    cluster, _ = _cinco_selecionadas()
    conjunto, criterios = portao.criterios_do_cluster(cluster)
    assert conjunto.negative_keywords == []
    assert all(c.negativa is False for c in criterios)


# ── mutação PÓS-APROVAÇÃO pelo corpo HTTP ──────────────────────────────────
#
# Ligar o conjunto à rota não fechou o portão: as duas rotas montavam
#
#     criterios = tuple(criterios_do_conjunto) + tuple(_criterios_do_corpo(...))
#
# e `_criterios_do_corpo` devolve `body.criterios`, que aceita `negativa=False`.
# Reproduzido contra o funil BPC/LOAS antes da correção:
#
#     approved_match=PHRASE  body_match=EXACT
#     positive_count=4       duplicate_count_for_term=2
#
# O corpo produzia uma QUARTA positiva e trocava o match type DEPOIS de
# `approved_set_sha256` ter sido emitido. Segunda variante: `keywords_fora`
# retirava selecionada aprovada — 3 viravam 2.


def _corpo(texto, *, match_type="PHRASE", negativa=False, grupo="ELEGIBILIDADE",
           nivel="AD_GROUP", origem="MANUAL"):
    from volc_ads import pautador_ponte as pp

    return pp.Criterio(texto=texto, match_type=match_type, negativa=negativa,
                       nivel=nivel, grupo=grupo, origem=origem)


def test_M1_positiva_do_corpo_e_recusada_antes_da_rede():
    """Positiva adicional pelo corpo é recusada — fechado, não filtrado."""
    _c, aprovados = portao.criterios_do_cluster(_cluster(aprovado=True))
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.somente_negativas_do_corpo([_corpo("termo novo do corpo")])
    assert e.value.codigo == portao.POSITIVA_DO_CORPO == "CRITERIO_POSITIVO_DO_CORPO_RECUSADO"
    assert len(aprovados) == 3


def test_M2_mesma_keyword_com_outro_match_type_e_recusada():
    """A forma exata do bloqueante: mesmo termo, match type diferente.

    Sem cobrir match type a recusa seria contornável por uma linha — foi
    assim que o corpo passou por cima de PHRASE com EXACT.
    """
    _c, aprovados = portao.criterios_do_cluster(_cluster(aprovado=True))
    alvo = aprovados[0]
    assert alvo.match_type == "PHRASE"
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.somente_negativas_do_corpo([_corpo(alvo.texto, match_type="EXACT")])
    assert e.value.codigo == portao.POSITIVA_DO_CORPO


def test_M3_negativa_declarada_pelo_operador_continua_possivel():
    """Fechar a positiva não pode fechar a negativa: ela é caminho legítimo,
    com todas as regras de evidência e procedência que `Criterio` já impõe."""
    passou = portao.somente_negativas_do_corpo(
        [_corpo("gratis", match_type="BROAD", negativa=True, nivel="CAMPAIGN", grupo=None)]
    )
    assert len(passou) == 1 and passou[0].negativa is True


def test_M4_keywords_fora_que_retira_selecionada_e_recusada():
    conjunto, aprovados = portao.criterios_do_cluster(_cluster(aprovado=True))
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.recusar_keywords_fora([aprovados[0].texto], conjunto)
    assert e.value.codigo == portao.KEYWORDS_FORA == "KEYWORDS_FORA_APOS_APROVACAO_RECUSADA"
    assert aprovados[0].texto in e.value.detalhe, "o erro precisa NOMEAR o que foi atingido"


def test_M5_keywords_fora_sem_efeito_tambem_nao_e_silenciada():
    """Aceitar um campo que não faz nada é como o operador acredita ter
    excluído algo que continua no pedido."""
    conjunto, _ = portao.criterios_do_cluster(_cluster(aprovado=True))
    with pytest.raises(portao.PortaoDoConjuntoPago) as e:
        portao.recusar_keywords_fora(["termo que nao esta no conjunto"], conjunto)
    assert e.value.codigo == portao.KEYWORDS_FORA


def test_M6_keywords_fora_vazia_continua_passando():
    conjunto, _ = portao.criterios_do_cluster(_cluster(aprovado=True))
    assert portao.recusar_keywords_fora([], conjunto) == []
    assert portao.recusar_keywords_fora(["", "  "], conjunto) == []


def test_M7_positivas_do_brief_sao_EXATAMENTE_as_aprovadas():
    """Não subconjunto. Igualdade de MULTICONJUNTO sobre
    (texto normalizado, match type, grupo, origem)."""
    _c, aprovados = portao.criterios_do_cluster(_cluster(aprovado=True))

    class BriefFalso:
        def __init__(self, crits):
            self.criterios = list(crits)

    # idêntico passa
    assert portao.conferir_positivas_do_brief(BriefFalso(aprovados), aprovados) is None

    # sobrando, faltando e duplicata exata recusam
    for rotulo, crits in (
        ("sobrando", list(aprovados) + [_corpo("extra")]),
        ("faltando", list(aprovados[:2])),
        ("duplicata", list(aprovados) + [aprovados[0]]),
        ("outro match", [_corpo(c.texto, match_type="EXACT", origem="PAUTADOR") for c in aprovados]),
        ("outro grupo", [_corpo(c.texto, grupo="OUTRO", origem="PAUTADOR") for c in aprovados]),
        ("outra origem", [_corpo(c.texto, origem="MANUAL") for c in aprovados]),
    ):
        with pytest.raises(portao.PortaoDoConjuntoPago, match=portao.POSITIVAS_DIVERGENTES):
            portao.conferir_positivas_do_brief(BriefFalso(crits), aprovados)

    # O grupo só pode desaparecer quando a rota declara explicitamente a
    # topologia `conjunto_unico=True`; ausência sozinha não prova colapso.
    sem_grupo = [
        _corpo(c.texto, match_type=c.match_type, grupo=None, origem=c.origem)
        for c in aprovados
    ]
    with pytest.raises(portao.PortaoDoConjuntoPago, match=portao.POSITIVAS_DIVERGENTES):
        portao.conferir_positivas_do_brief(BriefFalso(sem_grupo), aprovados)
    assert portao.conferir_positivas_do_brief(
        BriefFalso(sem_grupo), aprovados, grupo_colapsado=True
    ) is None

    parcial = list(sem_grupo)
    parcial[0] = aprovados[0]
    with pytest.raises(portao.PortaoDoConjuntoPago, match=portao.POSITIVAS_DIVERGENTES):
        portao.conferir_positivas_do_brief(
            BriefFalso(parcial), aprovados, grupo_colapsado=True
        )


def test_M8_negativa_no_brief_nao_conta_como_positiva_divergente():
    """A pós-condição olha só as positivas — negativa declarada não a quebra."""
    _c, aprovados = portao.criterios_do_cluster(_cluster(aprovado=True))

    class BriefFalso:
        def __init__(self, crits):
            self.criterios = list(crits)

    com_negativa = list(aprovados) + [
        _corpo("gratis", match_type="BROAD", negativa=True, nivel="CAMPAIGN", grupo=None)
    ]
    assert portao.conferir_positivas_do_brief(BriefFalso(com_negativa), aprovados) is None


def test_M9_as_duas_rotas_aplicam_as_tres_guardas():
    """`/provar` e `/subir`: só negativas do corpo, `keywords_fora` recusada,
    e a pós-condição sobre o brief FINAL — cada uma nas duas rotas."""
    import inspect

    from app.routers import trafego

    fonte = inspect.getsource(trafego)
    assert fonte.count("portao_pago.somente_negativas_do_corpo(") == 2
    assert fonte.count("portao_pago.recusar_keywords_fora(") == 2
    assert fonte.count("portao_pago.conferir_positivas_do_brief(") == 2
    assert fonte.count("grupo_colapsado=True") == 2
    # e o caminho antigo, que somava o corpo cru, não existe mais
    assert "tuple(criterios_do_conjunto) + tuple(_criterios_do_corpo(body, pp))" not in fonte
    assert "keywords_fora=list(body.keywords_fora)" not in fonte


def test_M10_as_recusas_acontecem_antes_da_rede():
    """As três guardas rodam antes de `sb.preparar()`, em ambas as rotas."""
    import inspect

    from app.routers import trafego

    fonte = inspect.getsource(trafego)
    preparar = [i for i in range(len(fonte)) if fonte.startswith("sb.preparar(", i)]
    assert len(preparar) == 2
    for marca in ("portao_pago.somente_negativas_do_corpo(",
                  "portao_pago.recusar_keywords_fora(",
                  "portao_pago.conferir_positivas_do_brief("):
        ocorrencias = [i for i in range(len(fonte)) if fonte.startswith(marca, i)]
        assert len(ocorrencias) == 2, marca
        for guarda, rede in zip(ocorrencias, preparar):
            assert guarda < rede, f"{marca} depois da rede"


def test_M11_o_bloqueante_original_nao_reproduz_mais():
    """A contraprova do integrador, ponta a ponta.

    Antes: approved_match=PHRASE · body_match=EXACT · positive_count=4 ·
    duplicate_count_for_term=2. Agora a montagem nem chega a acontecer.
    """
    _c, aprovados = portao.criterios_do_cluster(_cluster(aprovado=True))
    assert len(aprovados) == 3
    alvo = aprovados[0]
    injecao = [_corpo(alvo.texto, match_type="EXACT")]
    with pytest.raises(portao.PortaoDoConjuntoPago):
        criterios = tuple(aprovados) + tuple(portao.somente_negativas_do_corpo(injecao))
        del criterios  # inalcançável: a linha acima recusa


class _SubirSemRede:
    chamadas_preparar = 0

    @staticmethod
    def resolver_provador(_canal):
        return "SEARCH", object()

    @staticmethod
    def resolver_construtor(_canal):
        return "SEARCH", object()

    @classmethod
    def preparar(cls, *_args, **_kwargs):
        cls.chamadas_preparar += 1
        pytest.fail("uma recusa do conjunto aprovado alcançou a rede Google")


@pytest.mark.parametrize("nome_rota", ["provar", "subir"])
@pytest.mark.parametrize("mutacao", ["positiva", "keywords_fora"])
def test_M12_rotas_reais_recusam_mutacao_antes_da_rede(
    monkeypatch, nome_rota, mutacao
):
    """Executa as FUNÇÕES DE ROTA, não apenas helpers ou inspeção de fonte."""
    from fastapi import HTTPException
    from app.routers import trafego
    from volc_ads import pautador_ponte as pp

    cluster = _cluster(aprovado=True)
    _conjunto, aprovados = portao.criterios_do_cluster(cluster)
    dados = {
        "opportunity_id": 1,
        "customer_id": "5478096539",
        "login_customer_id": "6016739364",
    }
    if mutacao == "positiva":
        dados["criterios"] = [{
            "texto": aprovados[0].texto,
            "match_type": "EXACT",
            "negativa": False,
            "origem": "MANUAL",
        }]
        codigo = portao.POSITIVA_DO_CORPO
    else:
        dados["keywords_fora"] = [aprovados[0].texto]
        codigo = portao.KEYWORDS_FORA

    if nome_rota == "subir":
        dados.update({
            "motivo": "contraprova hermética do conjunto aprovado",
            "plano_impressao": "f" * 64,
            "confirmar_criacao_pausada": True,
        })
        corpo = trafego.SubirEntrada(**dados)
    else:
        corpo = trafego.ProvarEntrada(**dados)

    monkeypatch.setattr(
        pp, "carregar", lambda *_a, **_k: SimpleNamespace(cluster=cluster)
    )
    monkeypatch.setattr(pp, "montar_cockpit", lambda *_a, **_k: object())
    monkeypatch.setattr(
        pp, "montar_brief",
        lambda *_a, **_k: pytest.fail("a recusa atravessou a montagem do brief"),
    )
    monkeypatch.setattr(
        trafego, "_no_escopo", lambda *_a: ("5478096539", "6016739364")
    )
    monkeypatch.setattr(trafego, "_ponte", lambda: (pp, _SubirSemRede))
    monkeypatch.setattr(trafego.canario, "exigir", lambda **_k: "FORGE-TESTE")
    monkeypatch.setattr(trafego.escopo, "conta_da_casa", lambda *_a: None)
    _SubirSemRede.chamadas_preparar = 0

    with pytest.raises(HTTPException) as erro:
        asyncio.run(
            getattr(trafego, nome_rota)(
                corpo, identidade=SimpleNamespace(papel="admin")
            )
        )

    assert erro.value.status_code == 409
    assert erro.value.detail["codigo"] == codigo
    assert erro.value.detail["nada_foi_criado"] is True
    assert _SubirSemRede.chamadas_preparar == 0
