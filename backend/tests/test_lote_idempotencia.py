"""A idempotência do lote — o caso "a API respondeu timeout mas criou".

Este é o único caso que separa um lote seguro de uma máquina de campanhas
duplicadas gastando verba de verdade. As provas aqui cobrem a metade Python das
quatro camadas de defesa; as outras duas metades — os índices únicos e o gatilho
que recusa `falhou` com recibo em voo — são provadas contra um Postgres real em
`scripts/provar-ciclo-v10.sh`.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.trafego import lote as lo  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parents[2]
V10_01 = RAIZ / "supabase" / "migrations" / "v10_01_intencao_e_lote.sql"

_BASE = dict(intencao_id="int-1", plataforma="GOOGLE_ADS",
             conta_externa="8017851692", canal="SEARCH", ordem=0,
             plano={"nome": "FGTS", "verba_diaria_micros": 50_000_000})


def chave(**mudanca):
    return lo.chave_de_idempotencia(**{**_BASE, **mudanca})


# ═══════════════════════════════════════════════════════════════════════════
# 1. A FORMA DA CHAVE — ela tem de passar na CHECK do banco
# ═══════════════════════════════════════════════════════════════════════════


def test_a_chave_passa_na_check_do_banco():
    """A CHECK é lida do SQL, e não copiada: se ela apertar, este teste acusa.

    O piso de 8 caracteres não é estética — a chave viaja até a conta como
    rótulo e é por ela que a verificação remota reconhece o que já foi criado.
    Uma chave curta colide, e uma colisão aqui é uma campanha adotando o recibo
    de outra.
    """
    sql = V10_01.read_text(encoding="utf-8")
    bruto = re.search(
        r"CONSTRAINT trafego_item_chave_valida\s*\n\s*CHECK \(idempotency_key ~ '([^']+)'",
        sql).group(1)
    padrao = re.compile(bruto)
    for k in (chave(), chave(ordem=9999), chave(plataforma="META_ADS")):
        assert padrao.match(k), f"{k!r} não passa em {bruto}"
        assert len(k) <= 128


def test_a_chave_cabe_num_rotulo_e_nao_tem_espaco():
    k = chave()
    assert " " not in k and len(k) < 64


# ═══════════════════════════════════════════════════════════════════════════
# 2. A PROPRIEDADE QUE FAZ A RETOMADA FUNCIONAR
# ═══════════════════════════════════════════════════════════════════════════


def test_mesma_entrada_mesma_chave():
    """O processo caiu, subiu de novo, recalculou. A chave tem de ser a mesma —
    senão as quatro camadas de defesa deixam de reconhecer o que já foi enviado
    e passam a proteger contra uma duplicidade que não é a que acontece."""
    assert chave() == chave()


def test_ordem_das_chaves_do_dicionario_nao_muda_a_chave():
    """Sem `sort_keys`, o mesmo plano escrito em outra ordem produziria outra
    chave — e a retomada deixaria de reconhecer o próprio plano."""
    a = chave(plano={"nome": "FGTS", "verba_diaria_micros": 1_000_000})
    b = chave(plano={"verba_diaria_micros": 1_000_000, "nome": "FGTS"})
    assert a == b


def test_plano_diferente_chave_diferente():
    """Mudou o conteúdo, é outra coisa — e é a verdade."""
    assert chave() != chave(plano={"nome": "FGTS", "verba_diaria_micros": 1})


@pytest.mark.parametrize("campo,valor", [
    ("intencao_id", "int-2"),
    ("conta_externa", "1234567890"),
    ("canal", "DISPLAY"),
    ("ordem", 1),
    ("plataforma", "META_ADS"),
])
def test_cada_termo_da_identidade_muda_a_chave(campo, valor):
    """Se um deles saísse da derivação, duas campanhas diferentes passariam a
    compartilhar a chave — e a defesa contra duplicidade viraria uma defesa
    contra criação legítima."""
    assert chave() != chave(**{campo: valor})


def test_float_no_plano_e_recusado():
    """`repr(0.1 + 0.2)` não é `'0.3'`: um plano que passe por um `round()` numa
    versão do executor e não passe em outra mudaria de chave sem mudar de
    conteúdo. Dinheiro viaja em micros (int)."""
    with pytest.raises(lo.ErroDeLote, match="float"):
        chave(plano={"verba_diaria": 50.0})
    with pytest.raises(lo.ErroDeLote, match="float"):
        chave(plano={"lances": [{"cpc": 1.5}]})


def test_plataforma_desconhecida_e_recusada():
    with pytest.raises(lo.ErroDeLote, match="plataforma"):
        chave(plataforma="TIKTOK_ADS")


@pytest.mark.parametrize("campo", ["intencao_id", "conta_externa"])
def test_identidade_vazia_e_recusada(campo):
    with pytest.raises(lo.ErroDeLote):
        chave(**{campo: "  "})


def test_plano_vazio_e_recusado():
    with pytest.raises(lo.ErroDeLote, match="plano vazio"):
        chave(plano={})


# ═══════════════════════════════════════════════════════════════════════════
# 3. ⚠️ O CASO INTEIRO: TIMEOUT MAS CRIOU
# ═══════════════════════════════════════════════════════════════════════════


def test_recibo_em_voo_manda_verificar_e_nunca_criar():
    """A prova central deste arquivo.

    O item saiu em `criando`, a chamada não voltou, e o recibo ficou `em_voo`.
    A ação NÃO pode ser `criar` — reenviar sobre uma chamada que talvez tenha
    criado é como nasce a segunda campanha.
    """
    linha = {"item_id": "i1", "estado": "criando",
             "recibo_em_voo_id": "r1", "recibo_em_voo_desde": "2026-08-26T10:00:00Z"}
    assert lo.proxima_acao(linha) == "verificar"


def test_recibo_em_voo_vence_qualquer_outro_estado():
    """Mesmo um item que a aplicação já marcou como `falhou` — se houver recibo
    em voo, a resposta continua sendo verificar. A ordem dos ramos é a ordem da
    segurança."""
    for estado in lo.ESTADOS_DO_ITEM:
        linha = {"item_id": "i", "estado": estado, "recibo_em_voo_id": "r1"}
        assert lo.proxima_acao(linha) == "verificar", estado


def test_indeterminado_sem_recibo_ainda_manda_verificar():
    """O processo morreu ANTES de gravar o recibo. Não há linha em voo, e mesmo
    assim ninguém sabe se a chamada saiu."""
    assert lo.proxima_acao({"item_id": "i", "estado": "indeterminado"}) == "verificar"


def test_verificacao_que_achou_duas_para_o_lote():
    """Duas campanhas para a mesma chave já existem na conta. Qual pausar depende
    de qual já gastou, qual tem histórico e qual está vinculada a um funil —
    não há escolha automática correta."""
    linha = {"item_id": "i", "estado": "criada_pausada",
             "ultima_verificacao_quantidade": 2}
    assert lo.proxima_acao(linha) == "parar_duplicidade"


def test_verificacao_que_nao_conseguiu_ler_nao_libera_criacao():
    """`achou = NULL` é "não consegui verificar". Achatá-lo em `false` seria a
    forma mais cara de errar: uma falha de LEITURA viraria autorização para
    criar de novo."""
    linha = {"item_id": "i", "estado": "indeterminado",
             "ultima_verificacao_achou": None,
             "ultima_verificacao_quantidade": None}
    assert lo.proxima_acao(linha) == "verificar"


def test_so_item_aprovado_e_sem_nada_em_voo_recebe_criar():
    assert lo.proxima_acao({"item_id": "i", "estado": "aprovado"}) == "criar"


def test_retomada_nunca_poe_item_em_voo_no_balde_de_criar():
    """A separação dos baldes é o ponto: juntar `verificar` com `criar` numa
    lista só de "pendentes" é como se cria a segunda campanha."""
    linhas = [
        {"item_id": "a", "estado": "aprovado"},
        {"item_id": "b", "estado": "criando", "recibo_em_voo_id": "r1"},
        {"item_id": "c", "estado": "indeterminado"},
        {"item_id": "d", "estado": "falhou"},
        {"item_id": "e", "estado": "ativa"},
    ]
    plano = lo.retomada(linhas, limite_concorrencia=2)
    assert plano.criar == ("a",)
    assert set(plano.verificar) == {"b", "c"}
    assert plano.decidir_retomada == ("d",)
    assert plano.concluidos == ("e",)
    assert plano.bloqueado is False
    assert plano.limite_concorrencia == 2


def test_duplicidade_bloqueia_o_lote_inteiro():
    """Se uma chave produziu duas campanhas, a derivação ou a conta estão
    fazendo algo que ninguém previu — continuar criando os outros itens é
    continuar sob a mesma suposição errada."""
    plano = lo.retomada([
        {"item_id": "a", "estado": "aprovado"},
        {"item_id": "b", "estado": "verificada",
         "ultima_verificacao_quantidade": 3},
    ])
    assert plano.bloqueado is True
    assert plano.precisa_de_humano == ("b",)


def test_falha_de_um_item_nao_muda_a_acao_dos_outros():
    """Regra C: falha de um item não invalida nem mascara os demais."""
    linhas = [{"item_id": f"i{n}", "estado": "aprovado"} for n in range(5)]
    linhas[2] = {"item_id": "i2", "estado": "falhou"}
    plano = lo.retomada(linhas)
    assert len(plano.criar) == 4 and plano.decidir_retomada == ("i2",)


def test_toda_acao_devolvida_esta_no_vocabulario():
    """Uma ação nova aqui é uma ação nova na view `trafego_item_situacao`, e as
    duas têm de nascer juntas."""
    for estado in lo.ESTADOS_DO_ITEM:
        for em_voo in (None, "r1"):
            for qtd in (None, 0, 1, 2):
                acao = lo.proxima_acao({
                    "item_id": "i", "estado": estado,
                    "recibo_em_voo_id": em_voo,
                    "ultima_verificacao_quantidade": qtd})
                assert acao in lo.ACOES


def test_as_acoes_do_python_sao_as_mesmas_do_case_da_view():
    """A view e a função têm de oferecer o MESMO conjunto de respostas. Uma
    resposta só no SQL apareceria na tela e o executor não saberia tratá-la."""
    sql = V10_01.read_text(encoding="utf-8")
    trecho = sql[sql.index("END AS proxima_acao") - 1400:
                 sql.index("END AS proxima_acao")]
    do_sql = set(re.findall(r"THEN '([a-z_]+)'", trecho))
    do_sql |= set(re.findall(r"ELSE '([a-z_]+)'", trecho))
    assert do_sql == set(lo.ACOES), (
        f"só no SQL: {sorted(do_sql - set(lo.ACOES))} · "
        f"só em Python: {sorted(set(lo.ACOES) - do_sql)}")
