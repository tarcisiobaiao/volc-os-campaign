"""Provas da autocorreção de política.

## O caso real, medido no card 65 em 19/08/2026

`validate_only` contra a conta real recusou um mutate de 114 operações por DUAS
keywords — os 15 títulos, 4 descrições, sitelinks e callouts passaram:

    NON_FAMILY_SAFE  · 'como sacar o fgts na caixa'                        isentável
    PERSONAL_LOANS   · 'saldo bloqueado fgts empréstimo como desbloquear'  isentável

A API marcou as DUAS como `is_exemptible=True`, e mesmo assim elas não merecem
o mesmo destino. É essa diferença que este módulo carrega — e é ela que estes
testes trancam.

Rodar:
    backend/.venv/bin/python -m pytest volc_ads/testes_politica_auto.py -q
"""
from __future__ import annotations

import pytest

from volc_ads.gads.errors import ChavePolitica, ErroGads, FalhaGads, Politica
from volc_ads.politica_auto import ISENTAR_SOZINHO, decidir, podar


def _erro(nome: str, texto: str, *, isentavel: bool | None = True,
          formato: str = "violacao") -> ErroGads:
    return ErroGads(
        campo_codigo="policy_violation_error", valor_codigo="POLICY_ERROR",
        mensagem="A policy was violated.", gatilho=texto,
        politica=Politica(formato=formato, isentavel=isentavel,
                          chave=ChavePolitica(nome, texto) if formato == "violacao" else None),
    )


# ── o caso do card 65, inteiro ──────────────────────────────────────────────

def test_o_caso_real_separa_as_duas_keywords():
    """NON_FAMILY_SAFE sobre uma consulta de utilidade pública é ruído de
    classificador — isenta. PERSONAL_LOANS sobre uma keyword que contém
    'empréstimo' é a política nomeando a categoria do texto — remove."""
    d = decidir(FalhaGads(erros=(
        _erro("NON_FAMILY_SAFE", "como sacar o fgts na caixa"),
        _erro("PERSONAL_LOANS", "saldo bloqueado fgts empréstimo como desbloquear"),
    )))

    assert [c.policy_name for c in d.isentar] == ["NON_FAMILY_SAFE"]
    assert d.remover == ("saldo bloqueado fgts empréstimo como desbloquear",)
    assert d.acionavel


# ── a regra: o padrão é REMOVER ─────────────────────────────────────────────

def test_isentavel_fora_da_allowlist_e_REMOVIDA():
    """⚠️ O coração do módulo. `is_exemptible=True` NÃO basta: pedir isenção é
    afirmar que o anúncio não é daquela categoria. Quando a política nomeia o
    que o texto realmente toca, isentar troca "barrado agora" por "reprovado
    depois de veicular" — a mesma doutrina do portão de política."""
    d = decidir(FalhaGads(erros=(_erro("QUALQUER_POLITICA_NOVA", "texto x"),)))

    assert d.isentar == ()
    assert d.remover == ("texto x",)
    assert "removida em vez de isentada" in " ".join(d.diario)


def test_nao_isentavel_e_removida():
    d = decidir(FalhaGads(erros=(_erro("X", "y", isentavel=False),)))
    assert d.remover == ("y",) and d.isentar == ()
    assert "não é isentável" in " ".join(d.diario)


def test_a_allowlist_e_curta_e_nasce_do_medido():
    """Uma lista inventada de dez nomes daria impressão de cobertura onde há
    palpite. Só entra política vista numa recusa real."""
    assert ISENTAR_SOZINHO == frozenset({"NON_FAMILY_SAFE"})


def test_formato_achado_nao_e_tratado_aqui():
    """`achado` traz TÓPICOS, não chave — o remédio é outro campo. Tratar
    errado faria a API aceitar a requisição e não isentar nada."""
    d = decidir(FalhaGads(erros=(_erro("X", "y", formato="achado"),)))
    assert d.isentar == () and d.remover == ()
    assert d.sem_remedio and "formato achado" in " ".join(d.sem_remedio)


def test_o_diario_diz_o_que_foi_feito_com_cada_uma():
    """Sem isto o operador vê a campanha subir e não sabe o que saiu."""
    d = decidir(FalhaGads(erros=(
        _erro("NON_FAMILY_SAFE", "a"), _erro("PERSONAL_LOANS", "b"),
    )))
    assert len(d.diario) == 2
    assert any("isenção pedida" in l for l in d.diario)
    assert any("removida" in l for l in d.diario)


def test_falha_sem_politica_nao_decide_nada():
    d = decidir(FalhaGads(erros=(ErroGads(campo_codigo="quota_error",
                                          valor_codigo="RESOURCE_EXHAUSTED",
                                          mensagem="x"),)))
    assert not d.acionavel and d.resumo() == "nada a fazer"


# ── a poda ──────────────────────────────────────────────────────────────────

def test_podar_tira_so_as_que_violaram():
    ficaram, sairam = podar(["fgts saque", "empréstimo fgts", "consultar fgts"],
                            ("empréstimo fgts",))
    assert ficaram == ["fgts saque", "consultar fgts"]
    assert sairam == ["empréstimo fgts"]


@pytest.mark.parametrize("variacao", [
    "EMPRÉSTIMO FGTS", "  empréstimo fgts  ", "Empréstimo Fgts",
])
def test_podar_ignora_caixa_e_espaco(variacao):
    """⚠️ O `violating_text` volta do Google normalizado. Comparação exata
    deixaria a keyword no brief, a próxima validação reprovaria igual, e o
    motor pareceria não ter feito nada."""
    ficaram, sairam = podar(["fgts saque", variacao], ("empréstimo fgts",))
    assert ficaram == ["fgts saque"] and len(sairam) == 1


def test_podar_sem_alvo_nao_mexe():
    ficaram, sairam = podar(["a", "b"], ())
    assert ficaram == ["a", "b"] and sairam == []


# ── a fronteira com o preparo ───────────────────────────────────────────────

def test_preparar_faz_UMA_passada_e_nunca_um_laco():
    """Um laço gastaria quota contra uma parede e esconderia o padrão de quem
    precisa lê-lo."""
    import inspect

    from volc_ads import subir

    fonte = inspect.getsource(subir.preparar)
    # só as CHAMADAS, não as menções em comentário
    chamadas = [l for l in fonte.splitlines()
                if "politica_auto.decidir(" in l and not l.strip().startswith("#")]
    assert len(chamadas) == 1, chamadas
    assert "while" not in fonte
    # e a revalidação acontece UMA vez depois da correção
    revalidacoes = [l for l in fonte.splitlines()
                    if "validar_mutacoes(" in l and not l.strip().startswith("#")]
    assert len(revalidacoes) == 2, revalidacoes


def test_a_autocorrecao_pode_ser_desligada():
    """Quem quiser ver a recusa CRUA — depuração, ou um teste de contrato —
    precisa de um jeito de desligar."""
    import inspect

    from volc_ads import subir

    assert "autocorrigir" in inspect.signature(subir.preparar).parameters
    assert inspect.signature(subir.preparar).parameters["autocorrigir"].default is True


def test_o_diario_da_autocorrecao_sobrevive_ao_SUCESSO():
    """⚠️ Medido na primeira execução real: a autocorreção tirou uma keyword,
    o payload passou de 114 para 113 operações, o selo saiu — e o diário voltou
    VAZIO, porque só o retorno de FALHA o carregava.

    É a pior forma de sucesso: a que não deixa rastro. O operador aprovaria
    uma campanha sem saber que uma keyword foi removida e outra isentada."""
    import inspect

    from volc_ads import subir

    fonte = inspect.getsource(subir.preparar)
    # o retorno com selo é o último `return Preparo(` da função
    trecho = fonte.rsplit("return Preparo(", 1)[1]
    assert "autocorrecao=autocorrecao" in trecho, (
        "o caminho de SUCESSO voltou a descartar o diário da autocorreção")


def test_a_isencao_encontra_a_operacao_pelo_TEXTO_e_nao_pelo_indice():
    """Os índices mudam quando uma keyword sai da remontagem; o texto não.
    Casar por índice aplicaria a isenção na operação errada — em silêncio."""
    import inspect

    from volc_ads import subir

    fonte = inspect.getsource(subir._com_isencoes)
    assert "violating_text" in fonte
    assert "keyword.text" in fonte
