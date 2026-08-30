"""O lote: vocabulário, máquina de estados e resumo — contra o SQL de verdade.

As provas aqui comparam a DECLARAÇÃO em Python com o que o banco de fato impõe,
não com outra declaração em Python. É a mesma disciplina de
`test_trafego_plataforma.py`: um manifesto que só concorda consigo mesmo não
prova nada.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.trafego import lote as lo  # noqa: E402
from app.trafego import plataforma as plat  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parents[2]
V10_01 = RAIZ / "supabase" / "migrations" / "v10_01_intencao_e_lote.sql"


def _array_do_gatilho(nome_funcao: str) -> set:
    """Extrai o `permitidas CONSTANT text[] := ARRAY[...]` de uma função.

    Ler o SQL é o ponto: se a lista fosse repetida aqui à mão, este arquivo
    provaria que uma cópia concorda com outra cópia.
    """
    sql = V10_01.read_text(encoding="utf-8")
    inicio = sql.index(f"FUNCTION public.{nome_funcao}()")
    trecho = sql[inicio:]
    bloco = trecho[trecho.index("permitidas CONSTANT text[] := ARRAY["):]
    bloco = bloco[:bloco.index("];")]
    return set(re.findall(r"'([a-z_]+->[a-z_]+)'", bloco))


def _vocabulario_da_check(nome_constraint: str) -> set:
    sql = V10_01.read_text(encoding="utf-8")
    inicio = sql.index(f"CONSTRAINT {nome_constraint}")
    trecho = sql[inicio:inicio + 1200]
    bloco = trecho[trecho.index("IN ("):]
    bloco = bloco[:bloco.index("))")]
    return set(re.findall(r"'([a-z_]+)'", bloco))


# ═══════════════════════════════════════════════════════════════════════════
# 1. AS DUAS DEFINIÇÕES DA MESMA REGRA TÊM DE CONCORDAR
# ═══════════════════════════════════════════════════════════════════════════


def test_transicoes_do_lote_batem_com_o_gatilho():
    """Se divergirem, a tela oferece um botão que o banco recusa — ou pior,
    permite em Python uma transição que o gatilho barra no meio da execução."""
    do_sql = _array_do_gatilho("trafego_lote_estado_valido")
    do_python = {f"{de}->{para}" for de, para in lo.TRANSICOES_DO_LOTE}
    assert do_python == do_sql, (
        f"só em Python: {sorted(do_python - do_sql)} · "
        f"só no SQL: {sorted(do_sql - do_python)}")


def test_transicoes_do_item_batem_com_o_gatilho():
    do_sql = _array_do_gatilho("trafego_item_estado_valido")
    do_python = {f"{de}->{para}" for de, para in lo.TRANSICOES_DO_ITEM}
    assert do_python == do_sql, (
        f"só em Python: {sorted(do_python - do_sql)} · "
        f"só no SQL: {sorted(do_sql - do_python)}")


def test_estados_batem_com_as_checks():
    assert set(lo.ESTADOS_DO_LOTE) == _vocabulario_da_check(
        "trafego_lote_estado_conhecido")
    assert set(lo.ESTADOS_DO_ITEM) == _vocabulario_da_check(
        "trafego_item_estado_conhecido")


def test_toda_transicao_usa_estado_do_vocabulario():
    """Uma transição para um estado que a CHECK não aceita é código morto que
    parece regra: ela nunca dispara, e ninguém descobre por quê."""
    for de, para in lo.TRANSICOES_DO_ITEM:
        assert de in lo.ESTADOS_DO_ITEM and para in lo.ESTADOS_DO_ITEM
    for de, para in lo.TRANSICOES_DO_LOTE:
        assert de in lo.ESTADOS_DO_LOTE and para in lo.ESTADOS_DO_LOTE


def test_as_plataformas_sao_as_mesmas_do_manifesto():
    """`lote.py` não importa `plataforma.py` — mas as duas listas têm de ser a
    mesma, senão a chave de idempotência aceitaria uma plataforma que o núcleo
    não reconhece."""
    assert set(lo.SIGLA_DA_PLATAFORMA) == set(plat.PLATAFORMAS)


# ═══════════════════════════════════════════════════════════════════════════
# 2. A MÁQUINA DE ESTADOS
# ═══════════════════════════════════════════════════════════════════════════


def test_indeterminado_nao_vai_direto_para_falhou_sem_passar_por_verificacao():
    """`indeterminado -> falhou` EXISTE na tabela, e tem de existir: depois de
    uma verificação que respondeu "não existe", o item de fato falhou.

    O que impede o atalho perigoso não é a tabela — é o gatilho
    `trafego_item_estado_valido`, que recusa `falhou` enquanto houver recibo
    em voo. `provar-ciclo-v10.sh` exercita essa recusa contra o Postgres.
    """
    assert lo.transicao_permitida("indeterminado", "falhou")
    assert lo.transicao_permitida("indeterminado", "criada_pausada")
    assert lo.transicao_permitida("criando", "indeterminado")


def test_criada_pausada_nunca_vira_ativa_direto():
    """ADR-11: nada sobe ativo. O caminho passa por verificação, e só depois por
    canário ou ativação."""
    assert not lo.transicao_permitida("criada_pausada", "ativa")
    assert not lo.transicao_permitida("criada_pausada", "canario")
    assert lo.transicao_permitida("criada_pausada", "verificada")


def test_aprovado_e_o_unico_caminho_para_criando():
    entradas = {de for de, para in lo.TRANSICOES_DO_ITEM if para == "criando"}
    # `falhou` e `indeterminado` reabrem a tentativa; o primeiro envio só sai de
    # `aprovado`. Nenhum dos três é `planejado` ou `validado_local`.
    assert entradas == {"aprovado", "falhou", "indeterminado"}


def test_lote_so_executa_depois_de_aprovado():
    entradas = {de for de, para in lo.TRANSICOES_DO_LOTE if para == "executando"}
    assert entradas == {"aprovado", "interrompido", "concluido_com_falhas"}


def test_estados_terminais_sao_derivados_e_nao_escritos_a_mao():
    assert set(lo.estados_terminais(alvo="item")) == {"cancelada", "revertida"}
    assert set(lo.estados_terminais(alvo="lote")) == {
        "recusado", "cancelado", "revertido"}


def test_estado_inventado_devolve_falso_em_vez_de_explodir():
    assert lo.transicao_permitida("voando", "criando") is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. PLANEJAR
# ═══════════════════════════════════════════════════════════════════════════

_PLANOS = [
    {"nome": "FGTS · exato", "verba_diaria_micros": 50_000_000},
    {"nome": "FGTS · frase", "verba_diaria_micros": 30_000_000},
]


def _planejar(**kw):
    base = dict(intencao_id="int-1", blueprint_id="bp-1",
                plataforma="GOOGLE_ADS", conta_externa="8017851692",
                canal="SEARCH", planos=_PLANOS)
    base.update(kw)
    return lo.planejar(**base)


def test_planejar_e_deterministico():
    """A propriedade que faz a retomada funcionar depois de uma queda que
    perdeu tudo o que estava em memória."""
    assert _planejar().chaves == _planejar().chaves


def test_planos_iguais_em_ordens_diferentes_nao_colidem():
    """Duas campanhas idênticas de propósito no mesmo lote continuam sendo
    duas — a ordem entra na derivação."""
    lote = _planejar(planos=[_PLANOS[0], dict(_PLANOS[0])])
    assert len(set(lote.chaves)) == 2


def test_quota_orcada_e_declaracao_e_nao_medida():
    lote = _planejar(quota_por_item=3)
    assert lote.quota_orcada == 6
    # Sem declaração, NULL — e não zero. Zero afirmaria "não vai consumir nada".
    assert _planejar().quota_orcada is None


def test_lote_vazio_e_recusado():
    with pytest.raises(lo.ErroDeLote):
        _planejar(planos=[])


def test_rotulos_em_numero_diferente_sao_recusados():
    with pytest.raises(lo.ErroDeLote, match="rótulos"):
        _planejar(rotulos=["um"])


def test_concorrencia_zero_travaria_o_lote():
    with pytest.raises(lo.ErroDeLote, match="concorrência"):
        _planejar(limite_concorrencia=0)


# ═══════════════════════════════════════════════════════════════════════════
# 4. PODE EXECUTAR
# ═══════════════════════════════════════════════════════════════════════════


def test_sem_aprovacao_humana_nao_executa():
    pode, por_que = lo.pode_executar({"estado": "aprovado"})
    assert pode is False and "aprovação humana" in por_que


def test_com_aprovacao_executa():
    pode, por_que = lo.pode_executar(
        {"estado": "aprovado", "aprovado_em": "2026-08-26T10:00:00Z"})
    assert pode is True and por_que is None


def test_lote_cancelado_nao_executa_mesmo_aprovado():
    pode, por_que = lo.pode_executar({
        "estado": "aprovado", "aprovado_em": "2026-08-26T10:00:00Z",
        "cancelado_em": "2026-08-26T11:00:00Z"})
    assert pode is False and "cancelado" in por_que


def test_lote_em_preparando_nao_pula_para_executando():
    pode, _ = lo.pode_executar(
        {"estado": "preparando", "aprovado_em": "2026-08-26T10:00:00Z"})
    assert pode is False


# ═══════════════════════════════════════════════════════════════════════════
# 5. RESULTADO E RESUMO
# ═══════════════════════════════════════════════════════════════════════════


def _erro(item="i1"):
    return lo.ErroDeItem(item_id=item, codigo="POLICY_VIOLATION",
                         mensagem="anúncio reprovado", carimbo="2026-08-26T10:00:00Z")


def test_item_indeterminado_nao_deixa_o_lote_concluir():
    """⚠️ A prova mais importante deste arquivo depois da idempotência.

    Chamar de "concluído com falhas" um lote com item indeterminado é a forma
    mais silenciosa de a duplicidade escapar: ninguém verifica um lote encerrado.
    """
    r = lo.ResultadoDoLote(criados=("a",), falhas=(_erro(),),
                           indeterminados=("c",))
    assert r.estado_do_lote == "interrompido"


def test_falhas_sem_indeterminado_concluem_com_falhas():
    r = lo.ResultadoDoLote(criados=("a",), falhas=(_erro(),), indeterminados=())
    assert r.estado_do_lote == "concluido_com_falhas"


def test_tudo_certo_conclui():
    r = lo.ResultadoDoLote(criados=("a",), falhas=(), indeterminados=())
    assert r.estado_do_lote == "concluido"


def test_erro_sem_mensagem_e_recusado():
    with pytest.raises(lo.ErroDeLote, match="esconde a causa"):
        lo.ErroDeItem(item_id="i", codigo="X", mensagem="  ",
                      carimbo="2026-08-26T10:00:00Z")


def test_erro_sem_carimbo_e_recusado():
    with pytest.raises(lo.ErroDeLote, match="carimbo"):
        lo.ErroDeItem(item_id="i", codigo="X", mensagem="falhou", carimbo="")


def test_resumo_diz_primeiro_o_que_exige_alguem():
    """Um resumo que começa por "12 criadas" faz o "1 indeterminada" sumir no
    meio da frase — e é justamente essa a linha que precisa de olho."""
    itens = [
        {"item_id": "a", "estado": "ativa"},
        {"item_id": "b", "estado": "indeterminado"},
    ]
    texto = lo.resumo_humano(
        {"lote_id": "L1", "canal": "SEARCH", "conta_externa": "8017851692",
         "estado": "interrompido", "aprovado_em": "2026-08-26T10:00:00Z"}, itens)
    assert texto.index("verificação") < texto.index("criada(s)")
    assert "não sabemos se a chamada criou" in texto


def test_resumo_avisa_quando_falta_aprovacao():
    texto = lo.resumo_humano(
        {"lote_id": "L1", "estado": "aguardando_aprovacao"},
        [{"item_id": "a", "estado": "planejado"}])
    assert "sem aprovação humana" in texto


def test_resumo_grita_duplicidade():
    itens = [{"item_id": "a", "estado": "criada_pausada",
              "ultima_verificacao_quantidade": 2}]
    texto = lo.resumo_humano({"lote_id": "L1", "estado": "executando"}, itens)
    assert "MAIS DE UMA campanha" in texto and "travado" in texto


# ═══════════════════════════════════════════════════════════════════════════
# REGRESSÃO · o plano de retomada não pode descartar item em silêncio
# ═══════════════════════════════════════════════════════════════════════════


def test_o_plano_de_retomada_expoe_um_balde_para_cada_acao():
    """⚠️ `ACOES` tem oito valores; o plano expunha cinco.

    `ativar_canario`, `ativar` e `preparar` eram calculados por `proxima_acao` e
    jogados fora. Um item cujo próximo passo fosse `ativar_canario` sumia do
    plano inteiro, e o operador via um roteiro com menos itens do que o lote tem
    — sem nada dizendo que faltava alguém.
    """
    from app.trafego import lote as lt
    baldes = set(lt._CAMPOS_DE_BALDE)
    acoes = set(lt.ACOES)
    # `nada` vira `concluidos`; o resto tem nome igual.
    assert (acoes - {"nada"}) <= baldes, f"ações sem balde: {acoes - {'nada'} - baldes}"
    assert "concluidos" in baldes


def test_a_conta_do_plano_de_retomada_fecha():
    """Todo item que entra sai em exatamente um balde."""
    from app.trafego import lote as lt
    linhas = [
        {"item_id": f"i{n}", "estado": e, "proxima_acao": None,
         "recibo_em_voo": False, "encontradas_na_conta": None}
        for n, e in enumerate(
            ["planejado", "aprovado", "criando", "indeterminado",
             "criada_pausada", "verificada", "canario", "ativa", "falhou"])
    ]
    plano = lt.retomada(linhas)
    somados = sum(len(getattr(plano, c)) for c in lt._CAMPOS_DE_BALDE)
    assert somados == len(linhas), f"{somados} de {len(linhas)} itens no plano"
