"""Provas do juiz de sentido.

Nenhuma delas fala com o Google nem gasta token: o cliente é um dublê que
devolve o JSON combinado. O que se prova aqui é o CONTRATO — que o juiz nunca
derruba a geração, que ele endereça o asset certo, e que a fronteira entre
código e LLM está onde foi decidida.

Rodar:
    backend/.venv/bin/python -m pytest volc_ads/copy/testes_juiz_semantico.py -q
"""
from __future__ import annotations

import json

import pytest

from volc_ads.copy import juiz_semantico as js
from volc_ads.copy.contrato import Classe


class _Dubl:
    """Cliente que devolve o que lhe mandarem, e registra o que recebeu."""

    def __init__(self, resposta: str):
        self.resposta = resposta
        self.sistema = ""
        self.usuario = ""

    def gerar(self, sistema: str, usuario: str) -> str:
        self.sistema, self.usuario = sistema, usuario
        return self.resposta


ANUNCIO = {
    "headlines": ["Point Pro 3 Mercado Pago", "Minizinha NFC 2: 0,58%"],
    "descriptions": ["PagBank tem 5 anos de garantia."],
    "sitelinks": [{"texto": "Opções InfiniteSmart", "descricao1": "Compare"}],
    "snippet": {"header": "Modelos", "valores": ["T3 Smart"]},
}


def _resp(*obs) -> str:
    return json.dumps({"observacoes": list(obs)})


# ── o juiz não pode derrubar a geração ──────────────────────────────────────
#
# Quando ele roda, os ~140 s de cascata já estão pagos. Um juiz que explode e
# leva a copy junto é pior que juiz nenhum.

@pytest.mark.parametrize("resposta", [
    "isto não é JSON",
    "",
    "{}",
    '{"observacoes": "não é lista"}',
    "```json\n{quebrado\n```",
])
def test_resposta_ruim_do_juiz_nao_derruba(resposta):
    assert js.julgar(_Dubl(resposta), ANUNCIO,
                     fatos_texto="", nicho="x", regras=[]) == []


def test_transporte_que_explode_vira_lista_vazia():
    class _Explode:
        def gerar(self, sistema, usuario):
            raise RuntimeError("rede caiu")

    assert js.julgar(_Explode(), ANUNCIO, fatos_texto="", nicho="x", regras=[]) == []


def test_cerca_de_markdown_e_tolerada():
    """Modelo devolve ```json … ``` o tempo todo; recusar isso é fragilidade."""
    obs = js.julgar(
        _Dubl('```json\n' + _resp({"campo": "headline[0]", "regra": "ancoragem",
                                   "severidade": "erro", "motivo": "m",
                                   "trecho": "t"}) + '\n```'),
        ANUNCIO, fatos_texto="", nicho="x", regras=[])
    assert len(obs) == 1 and obs[0].campo == "headline[0]"


# ── o que o juiz VÊ ─────────────────────────────────────────────────────────

def test_o_prompt_carrega_o_anuncio_inteiro_e_os_fatos():
    d = _Dubl(_resp())
    js.julgar(d, ANUNCIO, fatos_texto="f1: Ton cobra 0,57%", nicho="Maquininha",
              regras=[{"id": "editorial.maiusculas.alternada", "titulo": "Maiúsculas"}])
    for esperado in ("Point Pro 3 Mercado Pago", "Opções InfiniteSmart",
                     "T3 Smart", "Ton cobra 0,57%", "Maquininha",
                     "editorial.maiusculas.alternada"):
        assert esperado in d.usuario, f"{esperado!r} não chegou ao juiz"


def test_o_sistema_proibe_o_juiz_de_contar():
    """A fronteira: sentido é dele, contagem é do código."""
    d = _Dubl(_resp())
    js.julgar(d, ANUNCIO, fatos_texto="", nicho="x", regras=[])
    assert "NÃO conta caracteres" in d.sistema
    assert "NOME PRÓPRIO OU ALEGAÇÃO" in d.sistema


def test_o_sistema_ensina_que_marca_nao_e_grito():
    d = _Dubl(_resp())
    js.julgar(d, ANUNCIO, fatos_texto="", nicho="x", regras=[])
    assert "PagBank" in d.sistema and "é marca" in d.sistema


# ── a tradução para a cascata ───────────────────────────────────────────────

def test_so_erro_vira_achado_acionavel():
    """`aviso` fica para a tela: a cascata tem 2 regenerações por asset, e
    gastar uma delas com conselho é trocar seis por meia dúzia."""
    obs = js.julgar(_Dubl(_resp(
        {"campo": "headline[0]", "regra": "ancoragem", "severidade": "erro",
         "motivo": "sem fato", "trecho": "x"},
        {"campo": "headline[1]", "regra": "estilo", "severidade": "aviso",
         "motivo": "poderia melhorar", "trecho": "y"},
    )), ANUNCIO, fatos_texto="", nicho="x", regras=[])
    assert len(obs) == 2

    achados = js.como_achados(obs)
    assert len(achados) == 1
    assert achados[0].classe is Classe.FORMA_REESCREVER
    assert str(achados[0].alvo) == "headline[0]"


def test_o_conserto_sugerido_viaja_para_a_regeneracao():
    achados = js.como_achados(js.julgar(_Dubl(_resp(
        {"campo": "description[0]", "regra": "ancoragem", "severidade": "erro",
         "motivo": "valor sem fato", "trecho": "5 anos",
         "conserto": "cite o fato f3 ou tire o número"},
    )), ANUNCIO, fatos_texto="", nicho="x", regras=[]))
    assert "cite o fato f3" in achados[0].detalhe


def test_campo_ilegivel_nao_vira_achado_sem_alvo():
    """Achado sem alvo faz a cascata refazer o CONJUNTO — queima os bons."""
    achados = js.como_achados(js.julgar(_Dubl(_resp(
        {"campo": "isso não é um endereço", "regra": "x", "severidade": "erro",
         "motivo": "m", "trecho": "t"},
    )), ANUNCIO, fatos_texto="", nicho="x", regras=[]))
    assert achados and achados[0].alvo is None, (
        "alvo ilegível tem de ficar explícito, não virar endereço inventado")


# ── a fronteira com o contrato determinístico ───────────────────────────────

def test_juiz_ligado_desliga_c7_e_c8():
    """Dois juízes para a mesma pergunta produzem veredito contraditório."""
    import inspect

    from volc_ads.copy import contrato

    fonte = inspect.getsource(contrato.checar)
    assert "if not semantico_ativo:" in fonte
    assert "_c8_faixa_medida" in fonte.split("if not semantico_ativo:")[1]
    assert "_c7_fato" in fonte.split("if not semantico_ativo:")[1]


def test_o_que_e_exato_continua_em_codigo_sempre():
    """Caracteres e contagem NUNCA saem do código: é onde o LLM perde."""
    import inspect

    from volc_ads.copy import contrato

    antes = inspect.getsource(contrato.checar).split("if not semantico_ativo:")[0]
    for exato in ("_c1_estrutura", "_c2_contagem", "_c4_chars", "_c6_contagem_final"):
        assert exato in antes, f"{exato} tem de rodar com ou sem juiz semântico"


# ── o juiz precisa VER o valor ──────────────────────────────────────────────
#
# ⚠️ Defeito real de 19/08/2026: o juiz recebeu `_fatos_texto`, que devolve só
# ids e tipos ("n1 numero · n2 numero · …"). Ele viu dez fatos sem um único
# valor e reprovou as OITO alegações da copy — todas ancoradas, todas com
# fonte. O juiz acertou; a entrada é que era lixo.
#
# Um juiz de ancoragem sem os valores é um gerador de falso positivo caro:
# 181 s de cascata, oito reescritas pedidas sem motivo.

def test_fatos_do_juiz_carregam_valor_e_fonte():
    from types import SimpleNamespace

    from volc_ads.copy import encomendar as em

    enc = SimpleNamespace(fatos=[
        SimpleNamespace(id="n1", tipo="numero",
                        texto="0.58% — Minizinha NFC 2 (vigente desde 2026-01-01)",
                        fonte="https://pagseguro.uol.com.br/"),
        SimpleNamespace(id="n4", tipo="numero",
                        texto="0.57% — Maquininhas Ton", fonte="https://www.ton.com.br"),
    ])
    txt = em._fatos_para_juiz(enc)
    for esperado in ("0.58%", "0.57%", "Minizinha NFC 2", "pagseguro.uol.com.br", "n1", "n4"):
        assert esperado in txt, f"{esperado!r} não chegaria ao juiz"


def test_a_linha_curta_continua_curta_para_a_regeneracao():
    """`_fatos_texto` NÃO deve engordar: ela é reinjetada a cada asset."""
    from types import SimpleNamespace

    from volc_ads.copy import encomendar as em

    enc = SimpleNamespace(fatos=[
        SimpleNamespace(id="n1", tipo="numero", texto="0.58% — Minizinha", fonte="x"),
    ])
    curta = em._fatos_texto(enc)
    assert "0.58%" not in curta, "a linha curta virou longa — custa token por asset"
    assert "n1" in curta


def test_as_duas_funcoes_nao_sao_a_mesma():
    """Trocar uma pela outra foi o defeito. Que fique difícil repetir."""
    from types import SimpleNamespace

    from volc_ads.copy import encomendar as em

    enc = SimpleNamespace(fatos=[
        SimpleNamespace(id="n1", tipo="numero", texto="0.58% — Minizinha", fonte="x"),
    ])
    assert em._fatos_texto(enc) != em._fatos_para_juiz(enc)


# ── cobertura do termo e quantidade de assets ───────────────────────────────
#
# ⚠️ Medido no card 74 em 19/08/2026: o Google devolveu nota Médio com dois
# itens sem check — "Inclua palavras-chave bastante usadas nos títulos" e
# "Adicione mais sitelinks". As causas eram medíveis: o termo dominante das
# keywords aparecia em 1 de 15 títulos, e o engine pedia 4 sitelinks (o mínimo
# aceito) quando a régua do Google vira em 6.

def test_pede_seis_sitelinks_nao_o_minimo():
    from volc_ads.copy.contrato import Pedido

    p = Pedido()
    assert p.n_sitelinks >= 6, "o Google conta a partir de 6, não de 4"
    assert p.n_callouts >= 6
    assert p.n_snippet >= 6


def test_raiz_do_termo_sai_das_keywords_e_nao_do_nicho():
    """O nicho é como a casa chama; a raiz é o que as pessoas digitam."""
    from volc_ads.copy.render import Encomenda

    class _E(Encomenda):
        pass

    # 7 de 10 contêm "maquininha" — é a distribuição real do card 74.
    kws = ["maquininha mercado pago", "maquininha ton", "maquininha de cartão",
           "maquininha stone", "maquininha pagseguro", "maquininha moderninha",
           "maquininha de cartão no celular", "moderninha pro 2",
           "mercado pago point mini", "qual o melhor app para passar cartão"]
    from types import SimpleNamespace
    falso = SimpleNamespace(keywords=kws)
    raiz = Encomenda.raiz_do_termo(falso)
    assert raiz == "maquininha", raiz


def test_cluster_sem_termo_dominante_desliga_a_exigencia():
    """Exigir cobertura de um termo inventado é pior que não exigir nada."""
    from types import SimpleNamespace

    from volc_ads.copy.render import Encomenda

    diverso = SimpleNamespace(keywords=["saque fgts", "bolsa familia",
                                        "cadastro unico", "seguro desemprego"])
    assert Encomenda.raiz_do_termo(diverso) == ""


def test_c9_e_declarada_como_regra_do_google_nao_do_corpus():
    """Número emprestado não pode virar número medido."""
    import inspect

    from volc_ads.copy import contrato

    doc = inspect.getdoc(contrato._c9_cobertura_do_termo) or ""
    assert "NÃO vem do corpus" in doc
    assert "Ad Strength" in doc or "Google" in doc


# ── COBERTURA DO TERMO: o card 65 passou na régua antiga e o Google deu RUIM ──
#
# ⚠️ Medido em 19/08/2026, DEPOIS do conserto do card 74. As 82 keywords do
# card 65 e os 15 títulos que a cascata entregou:
#
#   `fgts` em 4 de 15 títulos · `min_titulos_com_termo` era 4 → passou raspando
#   Google: "Inclua palavras-chave bastante usadas nos títulos" sem check
#   Ad Strength: RUIM  (o card 74 tinha dado Médio com 1 de 15)
#
# Duas causas, e as duas viraram teste aqui.

_KWS_65 = [
    "fgts consulta", "consultar fgts pelo cpf", "aplicativo fgts", "caixa fgts",
    "consultar fgts online", "fgts liberado como consultar",
    "consultar saque aniversário", "saque-aniversário fgts calendário",
    "saque aniversário fgts 2026", "saque-aniversário fgts 2026",
    "calendário fgts 2026", "saque fgts 2026", "quando cai o saque aniversário",
    "saque aniversário fgts calendário 2026", "fui demitido saque aniversário",
    "valor do saque aniversário",
]
_TITULOS_65 = [
    "FGTS Saque-Aniversário 2026", "Saque-Aniversário: Opções",
    "Modalidade: Elegibilidade", "Quem Não Tem Direito ao FGTS",
    "O Que Muda no FGTS em 2026?", "Nova Escolha: Prazo Regular",
    "Cálculo de Valores da Opção", "Como Funciona Essa Opção?",
    "Aniversário ou Rescisão?", "Diretrizes Atuais da Opção",
    "Guia Prático da Modalidade", "Atenção ao Bloqueio do Saldo",
    "Elegibilidade do Trabalhador", "Vantagens da Modalidade",
    "{KeyWord:Saque-Aniversário FGTS}",
]


def _enc(kws):
    from types import SimpleNamespace
    return SimpleNamespace(keywords=list(kws))


def test_o_hifen_separa_palavra_e_aniversario_volta_a_contar():
    """⚠️ `split()` deixava `saque-aniversario` como UM token, e `aniversario`
    — em 46 das 82 keywords do card 65 — nunca era contado. `2026` subia ao
    pódio no lugar dele. O hífen é separador na busca, não parte da palavra."""
    from volc_ads.copy.render import Encomenda

    raizes = Encomenda.raizes_do_termo(_enc(_KWS_65))
    assert "aniversario" in raizes, raizes
    assert "saque" in raizes


def test_ano_nao_e_raiz():
    """`2026` aparecia em 31 das 82 keywords. Um título com o ano não
    demonstra relevância como um com o assunto — o Google procura o ASSUNTO."""
    from volc_ads.copy.render import Encomenda

    raizes = Encomenda.raizes_do_termo(_enc(_KWS_65))
    assert not any(r.isdigit() for r in raizes), raizes


def test_a_variedade_REPROVA_a_copy_que_o_google_reprovou():
    """⚠️ ESTE TESTE JÁ COBROU A COISA ERRADA.

    A versão anterior exigia que a régua de RAIZ reprovasse o card 65 — e ela
    reprovava. O problema é que consertar a raiz não consertou a nota: com a
    raiz em 15 de 15 títulos, medido na campanha 24161105437 em 19/08/2026, o
    Google devolveu o MESMO AVERAGE e os MESMOS dois itens.

    Quem tem de reprovar aquele anúncio é a VARIEDADE: ele espelhava 7 das 82
    keywords do grupo."""
    from volc_ads.copy.contrato import Pedido, _c11_variedade_de_keywords

    p = Pedido(n_headlines=len(_TITULOS_65), keywords_do_grupo=tuple(_KWS_65))
    achados = _c11_variedade_de_keywords({"headlines": _TITULOS_65}, p)
    assert achados, "a variedade deixou passar o anúncio que o Google reprovou"
    assert any("espelha" in a.detalhe for a in achados), achados


def test_repetir_a_raiz_no_teto_nao_satisfaz_a_variedade():
    """O caso exato que subiu e tirou AVERAGE: 15 de 15 títulos com o termo, e
    ainda assim quase nenhuma keyword espelhada. Se a régua nova aprovasse
    isto, ela seria a antiga com outro nome."""
    from volc_ads.copy.contrato import Pedido, _c11_variedade_de_keywords

    monotonos = ["Saque-Aniversário FGTS: Regras", "Como Funciona o Saque FGTS?",
                 "Saque-Aniversário do FGTS", "{KeyWord:FGTS Saque Aniversário}",
                 "Saque do Seu FGTS", "Saque-Aniversário FGTS 2026",
                 "Conheça o Saque-Aniversário", "Calendário FGTS: Como Funciona",
                 "Tire Dúvidas do FGTS 2026", "Saque-Aniversário ou Rescisão?",
                 "Saque o FGTS Passo a Passo", "Regras para Sacar FGTS",
                 "Regras do Saque-Aniversário", "Saque-Aniversário: O que Muda?",
                 "Calendário Saque-Aniversário"]
    p = Pedido(n_headlines=15, keywords_do_grupo=tuple(_KWS_65))
    assert _c11_variedade_de_keywords({"headlines": monotonos}, p), (
        "esta copy tirou AVERAGE de verdade — a régua nova tem de reprová-la")


def test_a_regua_antiga_deixava_passar():
    """Documenta o defeito: com uma raiz e piso 4, aquele mesmo anúncio passava.
    É o que torna este arquivo uma regressão de verdade."""
    from volc_ads.copy.contrato import Pedido, _c9_cobertura_do_termo

    antiga = Pedido(raiz_do_termo="fgts", min_titulos_com_termo=4,
                    fracao_titulos_com_termo=0.0)
    assert _c9_cobertura_do_termo({"headlines": _TITULOS_65}, antiga) == []


def test_a_variedade_escala_com_o_numero_de_titulos():
    """Mais títulos, mais buscas espelhadas — um título novo que repete o que já
    foi dito não acrescenta nada ao que o Google mede."""
    from volc_ads.copy.contrato import Pedido, _c11_variedade_de_keywords

    kws = ("consultar fgts pelo cpf", "aplicativo fgts", "caixa fgts",
           "calendário fgts 2026", "valor do saque aniversário")
    espelham = ["Consultar FGTS pelo CPF", "Aplicativo FGTS Oficial",
                "Caixa FGTS: Acesse", "Calendário FGTS 2026",
                "Valor do Saque Aniversário"]
    p = Pedido(n_headlines=5, keywords_do_grupo=kws)
    assert _c11_variedade_de_keywords({"headlines": espelham}, p) == []

    # Quinze títulos, mas só cinco espelham busca: os outros dez repetem o que
    # já foi dito. O teto é o número de títulos ENTREGUES, não o pedido — quem
    # cobra quantidade é a C2, e cobrar duas vezes trava a cascata.
    kws15 = kws + tuple(f"prazo do saque {i}" for i in range(10))
    p15 = Pedido(n_headlines=15, keywords_do_grupo=kws15)
    repetidos = espelham + ["Consulte o FGTS Agora"] * 10
    assert _c11_variedade_de_keywords({"headlines": repetidos}, p15)


def test_a_variedade_nao_cobra_mais_keywords_do_que_existem():
    """Cobrar o impossível trava a cascata refazendo para sempre."""
    from volc_ads.copy.contrato import Pedido, _c11_variedade_de_keywords

    p = Pedido(n_headlines=15, keywords_do_grupo=("fgts consulta",),
               fracao_vocabulario=0.0)
    assert _c11_variedade_de_keywords(
        {"headlines": ["FGTS Consulta"] + ["outro"] * 14}, p) == []


def test_sem_keywords_declaradas_a_variedade_fica_calada():
    """Quem chama sem a lista (testes antigos, outros caminhos) não pode receber
    achado — a checagem não teria contra o que medir."""
    from volc_ads.copy.contrato import Pedido, _c11_variedade_de_keywords

    assert _c11_variedade_de_keywords({"headlines": ["qualquer coisa"]},
                                      Pedido(n_headlines=1)) == []


def test_cobertura_boa_passa_sem_reclamar():
    from volc_ads.copy.contrato import Pedido, _c9_cobertura_do_termo

    p = Pedido(raizes_do_termo=("fgts", "saque", "aniversario"))
    bons = ["Saque-Aniversário do FGTS", "Consultar FGTS pelo CPF",
            "Calendário do Saque FGTS", "Aniversário: Quem Tem Direito",
            "FGTS Liberado: Como Ver", "Saque FGTS pelo Aplicativo",
            "Valor do Saque-Aniversário", "Quando Cai o Saque",
            "Aniversário ou Rescisão no FGTS", "Guia do Saque",
            "Consulta de Saldo", "Prazo Regular", "Bloqueio do Saldo",
            "Vantagens da Escolha", "{KeyWord:Saque-Aniversário FGTS}"]
    assert _c9_cobertura_do_termo({"headlines": bons}, p) == []


def test_o_prompt_ensina_variedade_e_nao_repeticao():
    """⚠️ O prompt pedia "o termo em pelo menos N títulos", e o modelo entrega o
    que se pede: entregou 15 de 15 e tirou AVERAGE. Agora ele pede que cada
    título espelhe uma BUSCA DIFERENTE."""
    import pathlib

    md = pathlib.Path(__file__).resolve().parent / "PROMPT.md"
    t = md.read_text(encoding="utf-8")
    assert "{raizes_do_termo}" in t
    assert "{min_titulos_com_termo}" not in t, (
        "o marcador da régua refutada voltou ao prompt")
    baixo = t.lower()
    assert "variedade, não repetição" in baixo or "variedade, nao repeticao" in baixo
    assert "busca diferente" in baixo


# ── auto-declaração não pode queimar o orçamento do que é publicável ────────
#
# ⚠️ Medido no card 65 em 19/08/2026, na SEGUNDA geração. A C9 gerou o achado
# certo — "os termos aparecem em 7 de 15 títulos, e são precisos 9" — e a
# cascata morreu antes de corrigi-lo. O diário:
#
#     → C4: a passada 2 foi teatro (C4.chars). Refaz a passada 1 inteira (1/1)
#     · mentira de conjunto (C6.divergencia): não há versão por asset
#     ✗ ancoragem mentiu de novo e o teto de refazer (1) estourou
#
# Um erro de contagem que a PRÓPRIA TELA já rotulava como "não afeta o anúncio"
# consumiu o único refazer, e o defeito que o Google pune subiu para a conta.

def test_a_lista_de_auto_declaracao_e_explicita():
    from volc_ads.copy.contrato import AUTO_DECLARACAO

    assert AUTO_DECLARACAO == frozenset({"C4.chars", "C6.divergencia", "C6.ausente"})


def test_auto_declaracao_nao_dispara_refazer():
    """O coração do conserto: elas continuam sendo relatadas, e param de gastar
    o refazer que a cobertura de termo precisa."""
    import inspect

    from volc_ads.copy import ciclo

    fonte = inspect.getsource(ciclo.gerar)
    assert "a.codigo not in AUTO_DECLARACAO" in fonte, (
        "a auto-declaração voltou a consumir o orçamento de refazer")


def test_fato_inexistente_CONTINUA_refazendo():
    """A separação não pode afrouxar o que importa: afirmação sem fato por trás
    é defeito publicável e mantém o refazer."""
    from volc_ads.copy.contrato import AUTO_DECLARACAO

    for serio in ("C7.fato_inexistente", "C5.mecanica", "C3.desalinhada"):
        assert serio not in AUTO_DECLARACAO


# ── o Google pede keyword nas DESCRIÇÕES também ─────────────────────────────
#
# ⚠️ Não é dedução: `ad_group_ad.action_items` da conta devolveu, em
# 19/08/2026, "Try including more keywords in your descriptions." A C9 olhava
# só títulos — metade do pedido passava sem ninguém olhar.

def test_descricoes_sem_termo_sao_reprovadas():
    from volc_ads.copy.contrato import Pedido, _c9_cobertura_do_termo

    p = Pedido(raizes_do_termo=("fgts", "saque"))
    dados = {
        "headlines": ["Saque FGTS"] * 15,
        "descriptions": ["Entenda as regras da modalidade.",
                         "Confira os requisitos exigidos.",
                         "Planeje seu resgate com segurança.",
                         "Veja o que muda na demissão."],
    }
    achados = _c9_cobertura_do_termo(dados, p)
    assert any(a.codigo == "C9.cobertura_desc" for a in achados)
    assert "descrições" in achados[0].detalhe


def test_descricoes_com_termo_passam():
    from volc_ads.copy.contrato import Pedido, _c9_cobertura_do_termo

    p = Pedido(raizes_do_termo=("fgts", "saque"))
    dados = {
        "headlines": ["Saque FGTS"] * 15,
        "descriptions": ["Entenda as regras do saque do FGTS.",
                         "Requisitos para o saque-aniversário do FGTS.",
                         "Planeje seu resgate com segurança.",
                         "O que muda no FGTS em caso de demissão."],
    }
    assert _c9_cobertura_do_termo(dados, p) == []


def test_titulo_e_descricao_sao_checados_de_forma_INDEPENDENTE():
    """Títulos bons não compensam descrições ruins — o Google lista os dois
    itens separadamente."""
    from volc_ads.copy.contrato import Pedido, _c9_cobertura_do_termo

    p = Pedido(raizes_do_termo=("fgts",))
    so_titulos = {"headlines": ["FGTS aqui"] * 15,
                  "descriptions": ["genérico"] * 4}
    codigos = {a.codigo for a in _c9_cobertura_do_termo(so_titulos, p)}
    assert codigos == {"C9.cobertura_desc"}, codigos


def test_a_raiz_do_termo_nao_conta_no_teto_de_repeticao():
    """O caso real do card 65: 11 títulos com 'fgts' não podem virar pendência."""
    from volc_ads.copy.contrato import Pedido, _forma

    # As 11 caudas são distintas de propósito: só a raiz pode repetir.
    caudas = ["Como Sacar", "Pelo Aplicativo", "Regras Novas", "Prazo Final",
              "Vale a Pena?", "Antecipação", "Tabela Anual", "Demissão",
              "Consulta Rápida", "Débito Automático", "Extrato"]
    titulos = [f"FGTS: {c}" for c in caudas] + [
        "Consulta pelo CPF", "Calendário 2026", "Quem Tem Direito", "Passo a Passo"]
    p = Pedido(n_headlines=len(titulos), raizes_do_termo=("fgts", "saque", "aniversario"))
    repeticoes = [a for a in _forma({"headlines": titulos}, p) if a.codigo == "F.repeticao"]
    assert repeticoes == [], f"a raiz do termo ainda conta: {repeticoes}"


def test_o_teto_continua_valendo_para_o_resto_do_vocabulario():
    """A exceção é para a raiz do termo, não uma licença para repetir qualquer
    coisa. Título repetitivo é o que a política 14848296 realmente combate."""
    from volc_ads.copy.contrato import Pedido, _forma

    titulos = [f"Guia Completo Número {i}" for i in range(6)] + ["Consulta pelo CPF"]
    p = Pedido(n_headlines=len(titulos), raizes_do_termo=("fgts",))
    repetidas = {a.detalhe.split("'")[1]
                 for a in _forma({"headlines": titulos}, p) if a.codigo == "F.repeticao"}
    assert "guia" in repetidas and "completo" in repetidas, repetidas


def test_sem_raiz_declarada_nada_muda():
    """Quem chama sem `raizes_do_termo` (o caminho antigo, e os testes velhos)
    tem de ver o teto exatamente como antes — a exceção não pode virar buraco."""
    from volc_ads.copy.contrato import Pedido, _forma

    titulos = [f"FGTS: Título Número {i}" for i in range(6)]
    p = Pedido(n_headlines=len(titulos))
    assert [a for a in _forma({"headlines": titulos}, p) if a.codigo == "F.repeticao"]


def test_o_prompt_ensina_a_mesma_excecao_que_o_contrato_aplica():
    """⚠️ O motor já brigou consigo mesmo uma vez: o prompt ensinava uma frase
    que o sanitizador proibia. Se o contrato abre exceção para a raiz e o prompt
    não conta isso ao modelo, ele continua evitando repetir o termo — e a
    cobertura que o Google cobra nunca chega."""
    from volc_ads.copy import prompt as _p
    import inspect

    fonte = inspect.getsource(_p)
    i = fonte.index("política 14848296")
    trecho = fonte[i:i + 400].lower()
    assert "exceção" in trecho or "excecao" in trecho, (
        "o prompt ensina o teto de repetição sem contar a exceção da raiz")


# ── C10: o portão do lançamento, rodado dentro da cascata ───────────────────
#
# ⚠️ DOIS JULGADORES COM RÉGUAS DIFERENTES SOBRE O MESMO TEXTO.
#
# Card 65, 19/08/2026. A copy saiu da cascata com ZERO achado de contrato — 13
# de 15 títulos com o termo, 4 de 4 descrições, o melhor resultado até então —
# e o `/provar` a reprovou na hora:
#
#     [erro] description: Repetição de palavra dentro do mesmo texto (14848296)
#            → "Guia completo SOBRE o FGTS... tire suas dúvidas SOBRE as regras"
#
# O portão do lançamento cobrava uma regra que o contrato da copy não cobrava.
# A cascata declarava pronto, o operador clicava, e a reprovação chegava depois
# de a geração estar paga — sem ninguém para consertar, porque a cascata já
# tinha terminado.

def test_c10_pega_a_descricao_que_o_provar_reprovou():
    """O caso real, palavra por palavra: 'sobre' duas vezes no mesmo texto."""
    from volc_ads.copy.contrato import Pedido, _c10_portao_do_lancamento

    d = {"headlines": ["FGTS: Como Sacar"],
         "descriptions": ["Guia completo sobre o FGTS Saque-Aniversário. "
                          "Tire suas dúvidas sobre as regras de 2026."]}
    p = Pedido(n_headlines=1, n_descriptions=1,
               raizes_do_termo=("fgts", "saque", "aniversario"))
    achados = _c10_portao_do_lancamento(d, p)
    assert len(achados) == 1, achados
    assert achados[0].alvo.tipo == "description" and achados[0].alvo.indice == 0
    assert achados[0].classe.value == "forma_reescrever", "a cascata precisa refazer"


def test_c10_esta_no_caminho_do_checar():
    """De nada adianta a checagem existir se `checar()` não a chama — foi
    exatamente assim que a regra do portão ficou fora da cascata."""
    from volc_ads.copy.contrato import Pedido, checar

    d = {"headlines": ["FGTS: Como Sacar"],
         "descriptions": ["Guia completo sobre o FGTS. Tire dúvidas sobre regras."],
         "sitelinks": [{"title": "Consulta", "description1": "Veja aqui",
                        "description2": "Passo a passo"}],
         "callouts": ["Gratuito"], "snippet": {"header": "Modelos", "values": ["Anual"]},
         "ancoragem": {}, "auditoria": {}}
    codigos = {a.codigo for a in checar(d, Pedido(n_headlines=1, n_descriptions=1,
                                                  n_sitelinks=1, n_callouts=1,
                                                  n_snippet=1),
                                        semantico_ativo=True)}
    assert any(c.startswith("C10.") for c in codigos), codigos


def test_c10_ignora_aviso_e_so_barra_erro():
    """Aviso não impede lançar. Virar achado faria a cascata gastar rodadas
    para calar um alerta que não bloqueia nada."""
    from volc_ads.copy.contrato import Pedido, _c10_portao_do_lancamento

    # 'guia' em 6 títulos dispara repetição ENTRE itens, que o spec marca aviso.
    d = {"headlines": [f"Guia de FGTS Número {i}" for i in range(6)]}
    p = Pedido(n_headlines=6)
    for a in _c10_portao_do_lancamento(d, p):
        assert "repeticao.entre" not in a.codigo, f"aviso virou achado: {a}"


def test_c10_nao_briga_com_a_c9_pela_raiz_do_termo():
    """A C9 manda repetir o termo. Se a C10 o proibisse, a cascata oscilaria
    entre as duas até esgotar o teto de refazer — e a cobertura, que é o motivo
    de tudo isto existir, seria a primeira coisa a cair."""
    from volc_ads.copy.contrato import Pedido, _c10_portao_do_lancamento

    d = {"headlines": [f"FGTS: {c}" for c in
                       ("Como Sacar", "Pelo Aplicativo", "Regras Novas",
                        "Prazo Final", "Antecipação", "Tabela Anual")]}
    p = Pedido(n_headlines=6, raizes_do_termo=("fgts",))
    achados = [a for a in _c10_portao_do_lancamento(d, p) if "repeticao" in a.codigo]
    assert achados == [], achados


def test_c10_usa_o_spec_e_nao_uma_copia_da_regra():
    """Reimplementar a regra aqui recriaria o defeito num nível abaixo: as duas
    cópias divergiriam na primeira vez que o `spec.json` mudasse."""
    import inspect

    from volc_ads.copy import contrato

    fonte = inspect.getsource(contrato._c10_portao_do_lancamento)
    assert "Validador" in fonte, "a C10 tem de rodar o validador do spec"
    assert "limite_ocorrencias" not in fonte, "reimplementou a regra em vez de usá-la"


def test_pais_e_vertical_chegam_da_encomenda_ao_pedido():
    """O `spec.json` decide QUAIS regras valem por país × vertical. Se o Pedido
    nascer com o padrão em vez do que a encomenda declarou, a cascata julga com
    um conjunto de regras e o `/provar` com outro — que é o defeito original."""
    import inspect

    from volc_ads.copy import render

    fonte = inspect.getsource(render.Encomenda.pedido)
    assert "pais=self.pais" in fonte and "vertical=self.vertical" in fonte


def test_c10_usa_o_mesmo_criterio_de_barrar_que_o_portao():
    """⚠️ A primeira versão desta checagem lia `severidade == "erro"` do spec
    cru e passou a barrar `editorial.maiusculas.tudo_caixa_alta` — que o portão
    real REBAIXA a aviso de propósito, porque a exceção de sigla é lista fechada
    e 'Resolução CCFGTS 1.130/2025' fica de fora dela.

    A C10 virou mais dura que o portão que ela existe para espelhar, e a cascata
    passaria a refazer copy por causa de uma sigla legítima. O critério tem de
    vir de `campanha/search.py`, não de uma cópia local."""
    from volc_ads.copy.contrato import Pedido, _c10_portao_do_lancamento

    d = {"descriptions": ["Conteudo apoiado na Lei 8.036/90 e na "
                          "Resolucao CCFGTS 1.130/2025. Fontes citadas."]}
    achados = _c10_portao_do_lancamento(d, Pedido(n_descriptions=1))
    assert not any("caixa_alta" in a.codigo for a in achados), achados


def test_o_criterio_de_barrar_vem_do_search_e_nao_de_uma_copia():
    import inspect

    from volc_ads.copy import contrato

    fonte = inspect.getsource(contrato._barra_o_lancamento)
    assert "from ..campanha.search import" in fonte
    assert "_SO_AVISO" in fonte and "_SEVERIDADE_BARRA" in fonte


# ── o alvo que some entre ACHAR e CONSERTAR ─────────────────────────────────
#
# ⚠️ Medido no card 65 em 19/08/2026. A C10 passou a endereçar valor de snippet
# por índice — a primeira checagem a fazer isso — e a cascata morreu inteira:
#
#     IndexError: list assignment index out of range
#     contrato.py:178 → sn.setdefault("values", [])[self.indice] = texto
#
# O caminho das listas já parava em `indice >= len(seq)`; o do snippet não. A
# assimetria era latente havia meses, esperando alguém endereçar um snippet.
#
# A causa real é temporal: uma correção de EXCESSO encurta a lista antes de a
# regeneração deste achado rodar, e o índice passa a apontar para fora.

def test_escrever_em_indice_que_sumiu_nao_derruba_a_geracao():
    from volc_ads.copy.contrato import Alvo

    d = {"snippet": {"header": "Modelos", "values": ["a", "b"]}}
    Alvo("snippet", 7).escrever(d, "novo")       # índice fora
    assert d["snippet"]["values"] == ["a", "b"]

    d2 = {"headlines": ["x"]}
    Alvo("headline", 5).escrever(d2, "novo")     # o caminho que já era guardado
    assert d2["headlines"] == ["x"]


def test_o_header_do_snippet_continua_sendo_escrito():
    """O guarda de índice não pode calar o header, que não tem índice."""
    from volc_ads.copy.contrato import Alvo

    d = {"snippet": {"header": "velho", "values": []}}
    Alvo("snippet", 0, "header").escrever(d, "novo")
    assert d["snippet"]["header"] == "novo"


def test_conserto_que_nao_pegou_aparece_no_diario():
    """Anotar 'trocou' quando nada foi trocado é a pior forma de sucesso: a que
    não deixa rastro. O diário é o que o operador lê para saber o que houve."""
    import inspect

    from volc_ads.copy import ciclo

    fonte = inspect.getsource(ciclo._regenerar)
    assert "alvo.ler(dados) != novo" in fonte, (
        "a escrita não é conferida — um alvo que sumiu viraria sucesso silencioso")


def test_o_vocabulario_cobrado_e_o_RECORRENTE_e_nao_o_transcrito():
    """⚠️ A primeira versão da C11 cobrava metade de TODO o vocabulário das
    keywords. Medido no card 65 em 19/08/2026: 32 de 64, e a cascata entregou 18
    e desistiu — porque as que faltavam eram `1331`, `www`, `gov`, `meu`, `nao`,
    `tenho`, `voltei`. É o jeito de UMA pessoa digitar, não vocabulário do
    nicho, e não cabe em título de 30 caracteres.

    Regra insatisfazível não é rigor: é a cascata queimando rodada atrás de
    rodada, o mesmo defeito que a cota de dígitos do C8 já produziu."""
    from volc_ads.copy.contrato import medir_variedade

    kws = ["saque fgts", "saque fgts 2026", "consultar fgts",
           "consultar fgts pelo cpf", "www fgts gov br meu extrato 1331"]
    d = {"headlines": ["Saque FGTS 2026"], "descriptions": ["Consultar FGTS"]}

    todo = medir_variedade(d, kws, min_keywords_por_palavra=1)
    recorrente = medir_variedade(d, kws, min_keywords_por_palavra=2)
    assert recorrente["vocabulario"] < todo["vocabulario"]
    for lixo in ("www", "1331", "meu", "extrato"):
        assert lixo not in recorrente["vocabulario_ausente"], (
            f"{lixo!r} aparece em UMA keyword e está sendo cobrado")
    assert "consultar" in recorrente["vocabulario_ausente"] + ["consultar"] and \
        "fgts" not in recorrente["vocabulario_ausente"], (
        "o corte não pode derrubar palavra que aparece em várias keywords")


def test_o_corte_do_vocabulario_chega_da_configuracao():
    """Se a C11 ignorar `min_keywords_por_palavra`, o corte não existe na
    prática — e a regra volta a ser a impossível."""
    from volc_ads.copy.contrato import Pedido, _c11_variedade_de_keywords

    kws = tuple(["saque fgts"] * 2 + [
        "consultar fgts pelo cpf",
        "www fgts gov br meu extrato 1331",
        "quanto tempo demora liberacao do saldo retido"])
    d = {"headlines": ["Saque FGTS", "Consultar FGTS pelo CPF"],
         "descriptions": ["Guia do saque."]}
    apertado = Pedido(n_headlines=2, keywords_do_grupo=kws,
                      min_keywords_por_palavra=1, keywords_por_titulo=0.0)
    frouxo = Pedido(n_headlines=2, keywords_do_grupo=kws,
                    min_keywords_por_palavra=2, keywords_por_titulo=0.0)
    assert _c11_variedade_de_keywords(d, apertado)
    assert _c11_variedade_de_keywords(d, frouxo) == []
