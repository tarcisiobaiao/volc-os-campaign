"""
Portão de LEITURA (v7_15/v7_16) — o segundo eixo da descoberta.

O que importa testar aqui não é aritmética: é que o portão SINALIZE quando deve,
que falta de dado NUNCA vire veredito, e que ele ande AO LADO do arbitrage_score
em vez de no lugar dele.

⚠️ O portão NÃO barra. Foi rebaixado a sugestão por medição — reprovou o critério
de estabilidade declarado antes do teste (6/12 contra >=83%). Por isso o sinal é
lido pelo MOTIVO e não pelo veredito: ver `_sugere_barrar` e o cabeçalho de
`app/entities/leitura.py`.

Run:  cd backend && pytest tests/test_reading_gate.py -v
"""
from __future__ import annotations

from collections import Counter

import os
import sys

for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"
os.environ["PAUTADOR_KW_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.entities.leitura import (
    canonical_levels,
    compute_reading_gate,
    frase_representativa,
    moda_engajamento,
    respostas_validas,
)
from app.entities.mock import mock_entity_discovery
from app.entities.orchestrator import _norm_item
from app.entities.schemas import EntityCard, OpportunitySpec
from app.routers.entities import _OPP_COLS, _card_from_item, _opp_row


def _opp(**kw):
    base = {
        "ignorancia_level": "nao_sei_se_existe",
        "engajamento_level": "sustenta",
        "opacidade_level": "fragmentada",
    }
    base.update(kw)
    return base


def _sugere_barrar(g):
    """O sinal do portão hoje mora no MOTIVO, não no veredito: `bloqueado` é
    sempre False desde que o portão foi rebaixado a sugestão por medição
    (6/12 de estabilidade contra >=83% declarados antes do teste)."""
    return g["motivo"] is not None and g["bloqueado"] is False


def _tres(*niveis):
    return [{"frase": f"frase {i}", "engajamento_level": n} for i, n in enumerate(niveis)]


# ── a MODA das três frases (v7_16) ──────────────────────────────────────────
def test_moda_simples():
    assert moda_engajamento(_tres("dado_unico", "dado_unico", "sequencial")) == "dado_unico"


def test_portao_exige_MAIORIA_dizendo_dado_unico():
    """A regra é "o portão só fecha se a MAIORIA disser dado_unico".

    Ela saía de graça do desempate pelo meio da escala: `dado_unico` era o MENOR
    dos cinco valores, logo nunca era o do meio de três distintos.

    Com a escala colapsada em DOIS estados a regra fica ainda mais direta e não
    depende mais de desempate nenhum: com três votos e dois níveis possíveis,
    sempre há maioria, e `moda == dado_unico` É "a maioria disse dado_unico".
    """
    minoria = _tres("dado_unico", "sustenta", "sustenta")
    assert moda_engajamento(minoria) != "dado_unico"
    g = compute_reading_gate(_opp(respostas=minoria))
    assert g["bloqueado"] is False

    maioria = _tres("dado_unico", "dado_unico", "sustenta")
    assert _sugere_barrar(compute_reading_gate(_opp(respostas=maioria)))


def test_desempate_pelo_meio_ficou_INALCANCAVEL_com_dois_niveis():
    """O que este teste protegia deixou de poder acontecer, e é isso que ele
    passa a guardar.

    ERA: três rótulos distintos empatados em 1 voto cada, desempatados pelo do
    meio da escala (`diagnostico` 1,00 > `condicional` 0,85 > `sequencial` 0,80
    > `comparativo` 0,60). Com DOIS níveis não existem três distintos, e com
    três votos sempre há maioria — o ramo de desempate virou código morto para
    `engajamento`.

    Ele fica no módulo porque `moda_engajamento` é genérica sobre a escala; o
    dia em que a escala voltar a ter três níveis, ele volta a ser alcançado. O
    teste garante que HOJE ele não decide nada.
    """
    from app.motor_pautas.espaco import ENGAJAMENTO

    assert len(ENGAJAMENTO) == 2
    # três votos, dois níveis: sempre maioria, nunca empate
    for a, b, c in [("dado_unico", "dado_unico", "sustenta"),
                    ("sustenta", "sustenta", "dado_unico"),
                    ("sustenta", "sustenta", "sustenta")]:
        moda = moda_engajamento(_tres(a, b, c))
        assert moda == Counter([a, b, c]).most_common(1)[0][0]


def test_moda_ignora_voto_torto_e_frase_vazia():
    votos = _tres("sustenta", "talvez", "sustenta")
    votos.append({"frase": "   ", "engajamento_level": "dado_unico"})
    assert len(respostas_validas({"respostas": votos})) == 2
    assert moda_engajamento(respostas_validas({"respostas": votos})) == "sustenta"


def test_moda_vence_o_rotulo_solto_do_modelo():
    """A moda é calculada aqui, não pedida pronta: pedir aritmética a quem já
    erra a classificação é somar dois erros, e o valor perderia a auditoria
    contra as frases persistidas."""
    opp = _opp(respostas=_tres("sustenta", "sustenta", "dado_unico"),
               engajamento_level="dado_unico")
    assert canonical_levels(opp)["engajamento"] == "sustenta"
    assert compute_reading_gate(opp)["bloqueado"] is False


def test_sem_respostas_cai_no_rotulo_solto():
    assert canonical_levels(_opp(engajamento_level="dado_unico"))["engajamento"] == "dado_unico"


def test_respostas_lixo_nao_explode():
    for lixo in (None, "x", 42, [1, 2], [{"frase": "a"}], [{"engajamento_level": "clara"}]):
        assert compute_reading_gate(_opp(respostas=lixo))["bloqueado"] is False


def test_frase_representativa_e_a_que_sustenta_o_rotulo():
    # O contraste é o teste: a frase representativa tem de sair de DENTRO do
    # rótulo vencedor, nunca da primeira da lista. Com a escala em dois estados
    # o contraste é `dado_unico` contra `sustenta`.
    opp = _opp(respostas=[
        {"frase": "essa esgota", "engajamento_level": "dado_unico"},
        {"frase": "essa é a vencedora", "engajamento_level": "sustenta"},
        {"frase": "essa também", "engajamento_level": "sustenta"},
    ])
    assert canonical_levels(opp)["engajamento"] == "sustenta"
    assert frase_representativa(opp, "sustenta") == "essa é a vencedora"


# ── os dois portões (sinalizam; não barram) ─────────────────────────────────
def test_dado_unico_sugere_barrar():
    """IPVA: 1,8 mi de buscas e a resposta cabe num número. Volume não compensa."""
    g = compute_reading_gate(_opp(engajamento_level="dado_unico", ignorancia_level="so_falta_um_dado", opacidade_level="clara"))
    assert _sugere_barrar(g)
    assert g["motivo"] and "esgota em segundos" in g["motivo"]


def test_sem_stake_sugere_barrar():
    g = compute_reading_gate(_opp(ignorancia_level="nao_preciso_de_nada"))
    assert _sugere_barrar(g)
    assert g["motivo"] and "nada em jogo" in g["motivo"]


def test_motivo_e_frase_legivel_nao_codigo():
    g = compute_reading_gate(_opp(engajamento_level="dado_unico"))
    assert "dado_unico" not in (g["motivo"] or "")


def test_home_equity_passa():
    """tier B, 85 mil buscas, vácuo virgem — o score rebaixou por volume."""
    g = compute_reading_gate(_opp(ignorancia_level="nao_sei_se_existe", engajamento_level="sustenta", opacidade_level="ilegivel"))
    assert g["bloqueado"] is False
    assert g["motivo"] is None
    assert g["forca"] and g["forca"] > 0.6


def test_leitura_separa_ipva_de_home_equity():
    """A ordenação por LEITURA é outra que a por volume — é o ponto do eixo."""
    ipva = compute_reading_gate(_opp(ignorancia_level="so_falta_um_dado", engajamento_level="dado_unico", opacidade_level="clara"))
    home = compute_reading_gate(_opp(ignorancia_level="nao_sei_se_existe", engajamento_level="sustenta", opacidade_level="ilegivel"))
    assert ipva["forca"] < home["forca"]


# ── cada portão depende SÓ do eixo que o define ─────────────────────────────
def test_opacidade_ausente_nao_derruba_o_portao():
    """`opacidade` não participa de portão nenhum. Deixá-la calar o portão em
    silêncio seria a pior falha: a que parece funcionamento normal."""
    g = compute_reading_gate({"engajamento_level": "dado_unico", "ignorancia_level": "so_falta_um_dado"})
    assert _sugere_barrar(g)
    assert g["forca"] is not None            # sai sobre os dois eixos conhecidos


def test_opacidade_torta_nao_derruba_o_portao():
    g = compute_reading_gate(_opp(engajamento_level="dado_unico", opacidade_level="mais_ou_menos"))
    assert _sugere_barrar(g)


def test_engajamento_ausente_nao_dispara_portao_de_engajamento():
    g = compute_reading_gate({"ignorancia_level": "nao_sei_se_existe", "opacidade_level": "clara"})
    assert g["bloqueado"] is False


def test_ignorancia_ausente_nao_impede_portao_de_engajamento():
    g = compute_reading_gate({"engajamento_level": "dado_unico", "opacidade_level": "clara"})
    assert _sugere_barrar(g)


def test_um_portao_nao_precisa_do_outro():
    """`nao_preciso_de_nada` sinaliza mesmo com o engajamento ausente."""
    g = compute_reading_gate({"ignorancia_level": "nao_preciso_de_nada"})
    assert _sugere_barrar(g) and "nada em jogo" in g["motivo"]


# ── falta de dado nunca vira veredito ───────────────────────────────────────
def test_sem_os_tres_niveis_nao_bloqueia():
    """Sem nenhum eixo declarado não há veredito nem força — e o quadrante sai
    `indefinido` como em toda a fase pré-mineração (a família ECONOMIA ainda não
    existe), não `None`: o card não fica com um estado só dele."""
    g = compute_reading_gate({})
    assert g == {"bloqueado": False, "motivo": None, "forca": None, "quadrante": "indefinido"}


def test_nivel_fora_do_vocabulario_nao_bloqueia():
    """Rótulo torto no eixo do portão -> o portão não dispara (mas os outros
    eixos seguem valendo para a força)."""
    g = compute_reading_gate(_opp(engajamento_level="talvez_sim"))
    assert g["bloqueado"] is False
    assert g["forca"] is not None


def test_tipo_errado_nao_explode():
    for lixo in (None, 42, [], {"a": 1}):
        assert compute_reading_gate(_opp(engajamento_level=lixo))["bloqueado"] is False


# ── grafia: acento e separador não podem apagar um portão ───────────────────
def test_acento_e_separador_canonizam():
    assert canonical_levels({"opacidade_level": "Ilegível"})["opacidade"] == "ilegivel"
    # acento e separador dobram num nível VIVO
    assert canonical_levels({"engajamento_level": "Dado Único"})["engajamento"] == "dado_unico"
    # e o vocabulário APOSENTADO atravessa a ponte do legado: `Diagnóstico` era
    # um dos cinco níveis antigos e hoje só existe para LER linha já gravada.
    assert canonical_levels({"engajamento_level": "Diagnóstico"})["engajamento"] == "sustenta"
    assert canonical_levels({"engajamento_level": "dado único"})["engajamento"] == "dado_unico"
    assert canonical_levels({"engajamento_level": "DADO-UNICO"})["engajamento"] == "dado_unico"


def test_dado_unico_com_acento_ainda_sugere():
    g = compute_reading_gate(_opp(engajamento_level="Dado Único"))
    assert _sugere_barrar(g)


def test_sem_aproximacao_semantica():
    """`sequencial` e `dado_unico` mandam CONSTRUIR e NÃO CONSTRUIR o funil. Um
    rótulo que não cai exatamente num nível é dado ausente, nunca o mais parecido."""
    assert canonical_levels({"engajamento_level": "passo a passo"})["engajamento"] is None
    assert canonical_levels({"engajamento_level": "dado unico ou lista"})["engajamento"] is None


# ── contrato: o portão anda AO LADO do score ────────────────────────────────
def test_norm_item_traz_score_e_portao_juntos():
    item = mock_entity_discovery("Brasil", "BR", "pt-BR", 6)["entities"][0]
    norm = _norm_item(item, "Brasil", "BR", "pt-BR")
    o = norm["opportunity"]
    assert o["score"] is not None                 # o eixo econômico continua valendo
    assert o["reading_blocked"] is False          # o portão sugere; não barra
    assert o["reading_reason"]                    # mas a sugestão chega ao card
    assert o["resposta_em_uma_frase"]
    assert o["engajamento_level"] == "dado_unico"


def test_norm_item_grava_rotulo_torto_para_diagnostico():
    """Sem CHECK na coluna: o rótulo torto fica gravado para se depurar o prompt.
    Sem `respostas`, o rótulo solto do agente é o que sobra — e mesmo torto ele
    é persistido, porque perder a entidade por um campo é o erro caro."""
    item = mock_entity_discovery("Brasil", "BR", "pt-BR", 1)["entities"][0]
    item["opportunity"].pop("respostas", None)
    item["opportunity"]["engajamento_level"] = "talvez"
    o = _norm_item(item, "Brasil", "BR", "pt-BR")["opportunity"]
    assert o["engajamento_level"] == "talvez"
    assert o["reading_blocked"] is False


def test_mock_varia_os_rotulos():
    """Rótulo uniforme = classificou o tema do nicho, não a pergunta de cada
    entidade. O mock precisa exercitar o caso saudável — e agora pela MODA, que
    é onde o rótulo da oportunidade passa a nascer."""
    items = mock_entity_discovery("Brasil", "BR", "pt-BR", 12)["entities"]
    niveis = {_norm_item(i, "Brasil", "BR", "pt-BR")["opportunity"]["engajamento_level"] for i in items}
    assert len(niveis) > 1
    assert "dado_unico" in niveis


def test_campos_chegam_na_linha_do_banco_e_no_card():
    item = mock_entity_discovery("Brasil", "BR", "pt-BR", 6)["entities"][1]
    norm = _norm_item(item, "Brasil", "BR", "pt-BR")
    row = _opp_row(norm["opportunity"], entity_id=1, run_id=None, country_code="BR")
    for col in ("ignorancia_level", "engajamento_level", "opacidade_level",
                "resposta_em_uma_frase", "reading_blocked", "reading_reason", "reading_strength"):
        assert col in _OPP_COLS and col in row
    card = EntityCard(**_card_from_item(norm))
    assert card.engajamento_level == "sustenta"
    assert card.resposta_em_uma_frase


def test_opportunity_spec_aceita_os_campos_e_nao_exige_nenhum():
    """Rótulo torto não pode derrubar a validação do item inteiro (perder a
    entidade por um campo é o erro caro), e a ausência tem que ser tolerada."""
    assert OpportunitySpec().ignorancia_level is None
    assert OpportunitySpec(engajamento_level="qualquer_coisa").engajamento_level == "qualquer_coisa"


def test_forca_nao_e_o_indice_de_10_eixos_do_motor():
    """A defesa contra a comparação falsa, nos DOIS regimes do motor.

    Com portão disparado o índice do motor é exatamente 0,0 (portão é decisão
    binária); a força dilui o mesmo `dado_unico` na média e devolve ~0,37. Sem
    portão, o índice exige DUAS famílias e sai None — os nossos três eixos são
    todos `demanda_humana`. Se alguém trocar a conta pela do motor, este teste
    cai antes de os dois números irem parar na mesma tabela."""
    from app.motor_pautas.espaco import posicionar

    barrado = dict(ignorancia="so_falta_um_dado", engajamento="dado_unico", opacidade="clara")
    g = compute_reading_gate({f"{k}_level": v for k, v in barrado.items()})
    p = posicionar("x", pais="BR", **barrado)
    assert p.indice == 0.0             # motor: não construa, ponto
    assert g["forca"] > 0.05           # força: o portão entra diluído, não multiplica
    assert _sugere_barrar(g)           # sugere barrar, mas não barra
    assert g["quadrante"] == "descartar"   # quadrante coerente com o bloqueado

    livre = dict(ignorancia="nao_sei_se_existe", engajamento="sustenta", opacidade="fragmentada")
    g2 = compute_reading_gate({f"{k}_level": v for k, v in livre.items()})
    p2 = posicionar("x", pais="BR", **livre)
    assert p2.indice is None           # uma família só não é índice
    assert g2["forca"] is not None     # mas é força, e essa vale


def test_spread_e_volume_nunca_barram_na_descoberta():
    """Os portões de `spread`/`volume` do motor exigem dado MEDIDO. Nesta fase
    não declaramos nenhum dos dois — e mesmo que alguém declare, `medidos` não é
    passado, então palpite de LLM não mata tema."""
    import inspect

    from app.entities import leitura

    assert "medidos" not in inspect.getsource(leitura.compute_reading_gate)


def test_prompt_traz_vocabulario_e_teste_literal():
    from app.entities.prompts import ENTITY_DISCOVERY_SYSTEM_PROMPT as P

    assert "TESTE LITERAL" in P
    # v7_16: TRÊS frases no schema, e a moda como rótulo da oportunidade
    assert '"respostas"' in P and "escreva TRÊS respostas" in P
    assert "a **MODA** das três acima" in P
    assert "Não tenha medo do rótulo `dado_unico`" in P
    # autoverificação: cada rótulo precisa de PORTA DE ENTRADA própria, não de
    # frase-gatilho. Duas lições pagas com probe:
    #  - versão negativa ("não é sequencial") dizia de onde sair sem dizer para
    #    onde ir, e sem destino o modelo fica onde está;
    #  - `diagnostico` sem condição de entrada é a descrição mais atraente da
    #    lista, e o classificador gravita para lá (foi para onde o Home Equity
    #    fugiu ao deixar de ser `sequencial`).
    assert "O rótulo tem de descrever a FRASE, não o tema da entidade." in P
    assert "não pede nenhuma decisão do leitor" in P
    # trechos curtos de propósito: o prompt quebra linha e um substring longo
    # falharia por causa da largura da coluna, não do conteúdo.
    assert "a resposta muda conforme quem pergunta" in P and "seria diferente?" in P
    assert "caminhos alternativos e a dúvida é escolher entre eles" in P
    assert "pular uma impede a" in P

    # A CAUSA, atacada uma vez em vez de rótulo a rótulo: `sequencial` como balde
    # de "como funciona" e `diagnostico` no Registrato eram o MESMO erro — o
    # modelo rotulava o que sabe sobre a entidade, não a frase que escreveu.
    # Mas a regra é ESCOPADA a engajamento: aplicá-la a `opacidade` destruiu o
    # eixo (clara saltou de 2 p/ 7 em 20), porque opacidade É, por definição,
    # conhecimento sobre a instituição — cobrir o nome remove o insumo.
    assert "Cubra o nome da entidade e leia" in P
    assert "mudaria sem o nome à vista" in P
    assert "`opacidade` é o OPOSTO" in P
    assert "Uma frase clara sobre um assunto espalhado continua `fragmentada`" in P

    # A PRIMEIRA frase ancorada na dor — a dor é o que o funil vai atender. As
    # outras duas amostram o espaço de perguntas, que é onde mora a variância.
    assert "responde a dor que você declarou em `concrete_pain`" in P
    # e o schema tem de gerar a dor ANTES das frases, senão a âncora não existe
    # na hora de escrever
    assert P.index('"concrete_pain"') < P.index('"respostas"')
    # sequencial: a regra dizia "ações em ordem" sem dizer DE QUEM. Nas cinco
    # erradas quem agia era a instituição; na única certa, o leitor.
    assert "ações do LEITOR" in P
    assert "quem age na frase é o banco, o órgão ou o programa" in P
    # diagnostico: exige TENTATIVA, não estado. "dívidas negativadas" (Serasa
    # Limpa Nome) é situação ruim sem tentativa — passava na versão anterior.
    assert "descreve alguém que TENTOU e não conseguiu" in P
    assert "Estar numa situação ruim não basta" in P
    # e a cláusula de opacidade, que nasceu do caso Antecipação FGTS
    assert "Cita mais de uma instituição" in P and "`clara` só quando" in P
    for nivel in ("nao_sei_se_existe", "nao_preciso_de_nada", "diagnostico", "dado_unico",
                  "regra_mudou", "fragmentada", "ilegivel", "clara"):
        assert nivel in P
