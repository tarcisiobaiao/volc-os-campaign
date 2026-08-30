"""Testes do grafo e da prescrição."""

import datetime
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from motor_pautas.grafo import prescrever as PR
from motor_pautas.grafo.construir import construir, integrar_descobertas
from motor_pautas.grafo.modelo import VAZIO, Grafo

HOJE = datetime.date(2026, 8, 6)


@pytest.fixture(scope="module")
def g():
    return construir(paises_extra=["CA-FR"])


# ── estrutura ───────────────────────────────────────────────────────────────

def test_grafo_une_as_cinco_fontes(g):
    r = g.resumo()
    assert r["nos"]["tensao"] == 7          # a camada que não muda
    assert r["nos"]["arquetipo"] >= 20
    assert r["nos"]["entidade"] >= 70
    assert r["nos"]["evento"] >= 40


def test_no_e_idempotente():
    x = Grafo()
    x.no("a:z", "arquetipo", "z", k=1)
    x.no("a:z", "arquetipo", "z", k=2, j=3)
    assert len(x.nos) == 1
    assert x.nos["a:z"].atributos == {"k": 2, "j": 3}


def test_ligar_no_inexistente_falha_alto():
    x = Grafo()
    x.no("a:z", "arquetipo", "z")
    with pytest.raises(KeyError):
        x.liga("a:z", "p:XX", "explora")


def test_tipos_invalidos_falham():
    x = Grafo()
    with pytest.raises(ValueError):
        x.no("q", "coisa", "q")


# ── a contaminação não pode voltar ──────────────────────────────────────────

def test_grafo_nao_carrega_rpm_da_operacao(g):
    """A taxonomia vem de familias_rpm.json; o `rpm_familia` não.

    Aquele número saiu de uma carteira onde `spend` sozinho previa o desfecho
    com AUC 0,971 — trazê-lo reinjetaria decisão de verba de outra equipe
    disfarçada de propriedade do mundo.
    """
    for n in g.por_tipo("arquetipo"):
        assert "rpm" not in n.atributos
        assert "lucro" not in n.atributos


def test_forca_do_arquetipo_e_presenca_nao_lucro(g):
    """Provado em N países com N nomes diferentes = a tensão atravessa fronteira."""
    f = g.forca_do_arquetipo("a:fundo_verba_trabalhista")
    assert f >= 2


# ── a célula vazia é o produto ──────────────────────────────────────────────

def test_celula_sem_aresta_e_vazia(g):
    assert g.celula("a:fundo_verba_trabalhista", "p:CA-FR") == VAZIO


def test_celulas_vazias_exigem_arquetipo_provado(g):
    """Um país só pode ser sorte; dois é evidência de que a tensão viaja."""
    vazias = g.celulas_vazias(forca_minima=2)
    assert vazias
    for arq, _ in vazias:
        assert g.forca_do_arquetipo(f"a:{arq}") >= 2


def test_celulas_vazias_devolve_rotulos_nao_ids(g):
    """Regressão de um bug de prefixo duplo (`a:a:documento...`)."""
    arq, pais = g.celulas_vazias()[0]
    assert not arq.startswith("a:")
    assert not pais.startswith("p:")


# ── junção evento → entidade ────────────────────────────────────────────────

def test_eventos_ligam_a_entidades(g):
    """Regressão: 54 eventos produziam 2 arestas por falha de junção.

    Duas causas — acento (`saque aniversario` vs `saque aniversário`) e o fato
    de calendário e mapa cobrirem universos diferentes. O evento agora CRIA a
    entidade quando ela não existe, porque um evento oficial sobre algo é a
    evidência de que aquilo existe.
    """
    ligadas = [a for a in g.arestas.values() if a.tipo == "ativa"]
    assert len(ligadas) > 30


def test_evento_sem_arquetipo_nao_cria_entidade_solta(g):
    """Evento que não classifica fica sem aresta, não vira entidade órfã."""
    for n in g.por_tipo("entidade"):
        assert n.atributos.get("arquetipo")


# ── prescrição ──────────────────────────────────────────────────────────────

def test_transpor_pergunta_o_nome_local(g):
    ps = PR.transpor(g, limite=20)
    assert ps
    p = ps[0]
    assert p.acao == "transpor"
    assert "nome local" in p.pergunta
    assert p.falta_descobrir            # honesto sobre o que ainda não sabe


def test_ativar_exige_evento_na_janela(g):
    ps = PR.ativar(g, HOJE, janela_dias=90)
    for p in ps:
        assert p.evento is not None
        assert -30 <= p.evento["dias"] <= 90


def test_prescricao_diversifica_antes_do_teto(g):
    """Regressão: o topo do dia era um arquétipo × cinco países, todos 0,850.

    Células vazias do mesmo arquétipo herdam os mesmos priores de tensão e
    empatam. Cinco linhas que na prática eram uma.
    """
    r = PR.prescrever(g, HOJE, teto_por_acao=5)
    arqs = [p.arquetipo for p in r["transpor"]]
    assert len(set(arqs)) >= 2
    ents = [p.entidade for p in r["ativar"] if p.entidade]
    assert len(ents) == len(set(ents)), "mesma entidade duas vezes no mesmo dia"


def test_teto_e_retidos_sao_reportados(g):
    r = PR.prescrever(g, HOJE, teto_por_acao=3)
    assert len(r["transpor"]) <= 3
    assert r["retidos"]["transpor"] > 0     # o que ficou de fora é dito


# ── integração das descobertas ──────────────────────────────────────────────

def test_descoberta_nova_acende_a_celula():
    x = construir(paises_extra=["CA-FR"])
    antes = len(x.entidades_de("a:fundo_verba_trabalhista", "CA-FR"))
    r = integrar_descobertas(x, [{
        "entidade": "rqap", "pais": "CA-FR",
        "arquetipo": "fundo_verba_trabalhista", "confianca": "media"}])
    assert len(r["novas"]) == 1
    assert len(x.entidades_de("a:fundo_verba_trabalhista", "CA-FR")) == antes + 1


def test_descoberta_repetida_nao_vira_alerta_de_novo():
    """Sem isto o sentinela repete a mesma lista todo dia e morre de tédio."""
    x = construir()
    d = [{"entidade": "cesantias", "pais": "CO",
          "arquetipo": "fundo_verba_trabalhista", "confianca": "alta"}]
    r = integrar_descobertas(x, d)
    assert len(r["conhecidas"]) == 1 and not r["novas"]


def test_descoberta_com_arquetipo_inexistente_e_rejeitada():
    x = construir()
    r = integrar_descobertas(x, [{"entidade": "x", "pais": "BR",
                                  "arquetipo": "inventado"}])
    assert len(r["rejeitadas"]) == 1
    assert "não existe" in r["rejeitadas"][0]["motivo"]


# ── visualização ────────────────────────────────────────────────────────────

def test_mermaid_mostra_aceso_e_apagado(g):
    m = g.para_mermaid("a:fundo_verba_trabalhista", max_paises=8)
    assert "●" in m and "○" in m          # explorado e vazio
    assert "fill:#fff3cd" in m            # a célula vazia é destacada
    assert "a:" not in m                  # rótulos, não IDs
