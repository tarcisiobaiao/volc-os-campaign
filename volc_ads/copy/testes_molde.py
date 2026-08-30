"""O portão de MOLDE — a cota medida contra a faixa dos aprovados.

Rode com:  backend/.venv/bin/python -m volc_ads.copy.testes_molde

## O buraco que o C8 fecha

`FAIXAS_15` sai de 6.651 headlines aprovados e servindo, e `ciclo._cotas_fora()`
já comparava o medido contra ela — mas o resultado ia para o DIÁRIO, nunca para
um `Achado`. A seção 6 do `PROMPT.md` afirma que anúncio EXCELLENT cobre 6,44
mecânicas distintas contra 5,76 do GOOD; o prompt sabia, o contrato media, e
nada obrigava.

Medido em 18/08/2026, card 74 (Maquininha de Cartão): `dois_blocos` = **9 de
15** contra faixa de **3–4**. Nove títulos no molde `Assunto: Verbo`, 6,4× a
taxa do corpus. O único aviso do sistema foi que o modelo declarou 4.

## Por que estas provas existem, e não só um pytest

A operação roda em SETE países (BR MX CO CL PE AR ES), em português e espanhol,
e um portão de molde que só funcione em pt seria pior que nenhum: passaria a
falsa sensação de cobertura. Metade das provas abaixo é sobre idioma.

⚠️ NENHUMA chamada de rede, nenhuma chave lida, nenhum token gasto.
"""
from __future__ import annotations

import sys

from .contrato import (
    Alvo,
    Classe,
    Pedido,
    _c8_faixa_medida,
    faixas,
    indices_por_marcador,
    medir,
)


def _pedido(idioma: str = "pt", n: int = 15) -> Pedido:
    return Pedido(n_headlines=n, idioma=idioma)


def _conjunto(headlines: list[str]) -> dict:
    return {"headlines": headlines}


def _c8(headlines: list[str], idioma: str = "pt") -> list:
    return _c8_faixa_medida(_conjunto(headlines), _pedido(idioma, len(headlines)))


# ── o caso real, que motivou o portão ───────────────────────────────────────

CARD_74 = [
    "{KeyWord:Maquininha de Cartão}", "Leitor Mercado Pago: Guia",
    "Maquininha Ton: Regras 2026", "Opções de Aparelho: Confira",
    "Aparelhos PagBank: 5 Anos", "Dúvidas de Maquininha Ton?",
    "Modelos da Point: Conheça", "Minizinha NFC ou Modelo Smart?",
    "Veja Guia de Maquininhas", "Modelo Smart: Entenda Aqui",
    "InfiniteSmart: Como Funciona", "Aparelhos Ton sem Vitalícia",
    "Compare Leitores de Cartão", "Comparativo Mercado Pago 2026",
    "Regras da Minizinha: Saiba",
]


def prova_o_caso_que_motivou() -> str:
    """9 de 15 no molde `X: Y`, contra uma faixa de 3–4."""
    achados = _c8(CARD_74)
    codigos = {a.codigo for a in achados}
    assert codigos == {"C8.cota_estourada"}, codigos

    dois = [a for a in achados if "dois_blocos" in a.detalhe]
    assert len(dois) == 5, f"esperava 5 excedentes de dois_blocos, veio {len(dois)}"
    # Todo achado aponta um TÍTULO. Achado de conjunto viraria pendência e o
    # texto subiria torto — a cascata só sabe regenerar asset.
    assert all(isinstance(a.alvo, Alvo) and a.alvo.tipo == "headline" for a in achados)
    assert all(a.classe is Classe.FORMA_REESCREVER for a in achados)
    return f"{len(achados)} achados · dois_blocos 9/15 contra faixa 3–4"


def prova_aponta_o_excedente_e_nao_o_primeiro() -> str:
    """Os que ficam são os PRIMEIROS; o excedente é do teto para a frente.

    Importa porque o modelo capricha no começo da lista: mandar reescrever o
    primeiro título com dois-pontos jogaria fora o melhor deles.
    """
    onde = indices_por_marcador(CARD_74, "pt")["dois_blocos"]
    achados = [a for a in _c8(CARD_74) if "dois_blocos" in a.detalhe]
    apontados = {a.alvo.indice for a in achados}
    teto = faixas(15)["dois_blocos"][1]
    assert apontados == set(onde[teto:]), f"{apontados} != {set(onde[teto:])}"
    assert not (apontados & set(onde[:teto])), "apontou um dos que deviam ficar"
    return f"mantém os {teto} primeiros, aponta os {len(apontados)} seguintes"


def prova_um_a_mais_nao_reprova() -> str:
    """⚠️ A faixa é MEDIDA, não é lei. Um acima do teto é ruído.

    Reprovar por 1 faria a cascata gastar uma geração de LLM para trocar um
    título que os aprovados reais também teriam.
    """
    teto = faixas(15)["dois_blocos"][1]
    base = [f"Guia de Maquininha {i}" for i in range(15)]
    for i in range(teto + 1):
        base[i] = f"Maquininha: Guia {i}"
    assert medir(base, "pt")["dois_blocos"] == teto + 1
    # Só sobre ESTE marcador: o conjunto sintético dispara outros, e perguntar
    # "nenhum achado" testaria o fixture, não o portão.
    assert not [a for a in _c8(base) if "dois_blocos" in a.detalhe], \
        "um acima do teto não pode reprovar"

    base[teto + 1] = f"Aparelho: Guia {teto + 1}"
    assert [a for a in _c8(base) if "dois_blocos" in a.detalhe], \
        "dois acima do teto TEM de reprovar"
    return f"teto {teto}: {teto + 1} passa, {teto + 2} reprova"


def prova_sem_verbo_nao_tem_teto() -> str:
    """⚠️ DECISÃO DE POLÍTICA, não de distribuição.

    `sem_verbo` é o complemento de `leitura ∪ verbo`. Limitar o teto dele é
    exigir um PISO de verbo — e `verbo` aqui é verbo de EXECUÇÃO (solicitar,
    consultar, cadastrar), que num portal informativo é justamente o que parece
    prometer serviço. O excesso de `sem_verbo` é o lado SEGURO do desvio.
    """
    mudos = [f"Maquininha de Cartao Modelo {i}" for i in range(15)]
    m = medir(mudos, "pt")
    teto = faixas(15)["sem_verbo"][1]
    assert m["sem_verbo"] == 15 > teto, m["sem_verbo"]
    assert not [a for a in _c8(mudos) if "sem_verbo" in a.detalhe], \
        "sem_verbo não pode reprovar — empurraria para verbo de execução"
    return f"15 títulos sem verbo, teto {teto}, e o portão não reprova"


def prova_conjunto_incompleto_nao_e_julgado() -> str:
    """Distribuição de conjunto incompleto não é distribuição — é um pedaço.

    Com 13 de 15 a cascata ainda vai preencher duas vagas. Quem raciocina sobre
    vaga é `orcamento_restante()`; reprovar aqui mandaria regenerar um título
    que talvez já esteja certo, e faltar título já é achado do C2.
    """
    parcial = CARD_74[:13]
    assert _c8_faixa_medida(_conjunto(parcial), _pedido("pt", 15)) == []
    assert _c8_faixa_medida(_conjunto(parcial), _pedido("pt", 13)) != []
    return "13 de 15 não julga; 13 de 13 julga"


# ── idioma: a metade que importa para sete países ───────────────────────────

def prova_o_molde_atravessa_idioma() -> str:
    """Dois-pontos é MECANISMO, não vocabulário — vale em qualquer língua.

    A operação roda em BR MX CO CL PE AR ES. Um portão de molde que só
    funcionasse em português seria pior que nenhum: daria falsa cobertura.
    """
    es = [
        "Máquina de Tarjeta: Guía", "Lector Mercado Pago: Guía",
        "Máquina Ton: Reglas 2026", "Opciones de Equipo: Mira",
        "Equipos PagBank: 5 Años", "Máquina Ton: Dudas",
        "Modelos Point: Conoce", "Minizinha NFC o Smart",
        "Guía de Máquinas", "Modelo Smart: Entiende",
        "InfiniteSmart: Cómo Va", "Equipos Ton sin Cuota",
        "Compara Lectores", "Comparativo Mercado Pago",
        "Reglas Minizinha: Sabe",
    ]
    achados = _c8(es, "es")
    dois = [a for a in achados if "dois_blocos" in a.detalhe]
    assert dois, "o molde `X: Y` em espanhol tem de reprovar igual"
    return f"espanhol: {len(dois)} excedentes de `X: Y`"


def prova_pergunta_em_espanhol_e_contada() -> str:
    """`¿` abre pergunta em espanhol, e `RX_PERG` cobre os dois sinais.

    Sem isso, um conjunto todo interrogativo em espanhol passaria como se não
    tivesse pergunta nenhuma — e a cota de `pergunta` existe justamente para
    impedir 15 perguntas seguidas.
    """
    todas = [f"¿Cuál Máquina Elegir {i}?" for i in range(15)]
    assert medir(todas, "es")["pergunta"] == 15
    assert [a for a in _c8(todas, "es") if "pergunta" in a.detalhe]

    # E a mesma frase sem os sinais NÃO é pergunta.
    nenhuma = [f"Cual Maquina Elegir {i}" for i in range(15)]
    assert medir(nenhuma, "es")["pergunta"] == 0
    return "¿…? contado em es; sem sinal, não conta"


def prova_contraste_depende_do_idioma() -> str:
    """⚠️ `o` é contraste em espanhol e ARTIGO em português.

    Uma regex só produziria 100% de falso positivo em pt — e o portão passaria
    a reprovar todo conjunto português por "excesso de contraste".
    """
    pt = [f"O Guia de Maquininha {i}" for i in range(15)]
    assert medir(pt, "pt")["contraste"] == 0, "o artigo português virou contraste"
    assert not [a for a in _c8(pt, "pt") if "contraste" in a.detalhe]

    es = [f"Tarjeta o Efectivo {i}" for i in range(15)]
    assert medir(es, "es")["contraste"] == 15
    assert [a for a in _c8(es, "es") if "contraste" in a.detalhe]
    return "pt: 0 falsos positivos · es: 15 contrastes reais"


def prova_dki_conta_pelo_fallback_em_qualquer_idioma() -> str:
    """A tag DKI é sintaxe do Google, não da língua.

    `{KeyWord:...}` tem de ser reconhecida igual em pt e es — é ela que decide
    o comprimento efetivo, e contar errado aprova título que estoura no leilão.
    """
    for idioma, texto in (("pt", "{KeyWord:Maquininha}"), ("es", "{KeyWord:Máquina}")):
        conj = [texto] * 15
        assert medir(conj, idioma)["dki"] == 15, idioma
        assert [a for a in _c8(conj, idioma) if "dki" in a.detalhe], idioma
    return "DKI reconhecida em pt e es"


def prova_idioma_desconhecido_nao_explode() -> str:
    """País novo entra sem regra de contraste, e isso não pode derrubar nada.

    `medir()` cai no padrão `en` quando o idioma não tem regex própria. O
    portão continua valendo para os marcadores que são mecanismo puro — que é
    a maioria — em vez de recusar-se a olhar.
    """
    conj = [f"Card Machine: Guide {i}" for i in range(15)]
    achados = _c8(conj, "tlh")           # idioma inexistente, de propósito
    assert [a for a in achados if "dois_blocos" in a.detalhe], \
        "mecanismo puro tem de continuar valendo em idioma sem regra"
    return "idioma sem regra: mecanismo puro continua julgando"


def prova_faixa_escala_com_o_numero_de_titulos() -> str:
    """Anúncio com 10 títulos não usa a faixa de 15.

    As faixas do `PROMPT.md` são declaradas "em {n_headlines} títulos". Usar a
    de 15 num conjunto de 10 reprovaria distribuição correta.
    """
    f15, f10 = faixas(15), faixas(10)
    assert f10["dois_blocos"][1] < f15["dois_blocos"][1], (f10, f15)
    dez = [f"Maquininha: Guia {i}" for i in range(10)]
    assert _c8(dez, "pt"), "10 títulos todos no mesmo molde tem de reprovar"
    return f"15 títulos: teto {f15['dois_blocos'][1]} · 10 títulos: teto {f10['dois_blocos'][1]}"


PROVAS = [
    ("o caso que motivou", prova_o_caso_que_motivou),
    ("aponta o excedente", prova_aponta_o_excedente_e_nao_o_primeiro),
    ("um a mais não reprova", prova_um_a_mais_nao_reprova),
    ("sem_verbo não tem teto", prova_sem_verbo_nao_tem_teto),
    ("conjunto incompleto", prova_conjunto_incompleto_nao_e_julgado),
    ("molde atravessa idioma", prova_o_molde_atravessa_idioma),
    ("pergunta em espanhol", prova_pergunta_em_espanhol_e_contada),
    ("contraste por idioma", prova_contraste_depende_do_idioma),
    ("DKI em qualquer idioma", prova_dki_conta_pelo_fallback_em_qualquer_idioma),
    ("idioma sem regra", prova_idioma_desconhecido_nao_explode),
    ("faixa escala", prova_faixa_escala_com_o_numero_de_titulos),
]


def main() -> int:
    print("═" * 78)
    print("PORTÃO DE MOLDE (C8) — sem rede, sem chave, sem token.")
    print("═" * 78)
    falhas = 0
    for nome, prova in PROVAS:
        try:
            detalhe = prova()
        except Exception as exc:  # noqa: BLE001 — o runner reporta tudo
            falhas += 1
            print(f"✗ {nome:<26} {type(exc).__name__}: {exc}")
            continue
        print(f"✓ {nome:<26} {detalhe}")
    print("─" * 78)
    print(f"{len(PROVAS) - falhas}/{len(PROVAS)} provas passaram")
    print("═" * 78)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
