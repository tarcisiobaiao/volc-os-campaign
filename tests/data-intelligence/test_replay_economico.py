"""Contraprovas do replay econômico v0 (dados SINTÉTICOS).

(a) futuro no caminho da política -> VazamentoDeFuturo
(b) política que trata None como 0 é detectada
(c) moeda misturada -> erro
(d) identidade trocada (mesmo entidade_id, outra conta) -> IdentidadeIncompativel / exclusão explícita
(e) restatement: decisão em t usa a preliminar, não a revisada
(f) reprodutibilidade por seed/fingerprint (inclusive fixture byte a byte)
"""
from __future__ import annotations

import importlib.util
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from volc_dil.contracts import (
    ChaveUnidade,
    Dinheiro,
    IdentidadeIncompativel,
    Maturidade,
    Metrica,
    MoedasDiferentes,
    Snapshot,
    VazamentoDeFuturo,
    agregar,
    contribuicao,
    sha256_arquivo,
)
from volc_dil.replay import (
    Estatica,
    GulosaConservadora,
    Igual,
    Proporcional,
    baselines,
    cenario_mini,
    executar,
    proporcional_ingenua,
    relatorio_cenario,
)
from volc_dil.replay.auditoria import auditar_null_vs_zero
from volc_dil.replay.avaliacao import bytes_relatorio, drawdown_maximo
from volc_dil.replay.cenario import EspecCenario, Mundo, dia_de, repartir
from volc_dil.replay.motor import cortar_as_of
from volc_dil.replay.politicas import Decisao, indexar

LAB = Path(__file__).resolve().parents[2] / "experiments" / "data-intelligence-lab"


def _capturar(espec, politica, **kw):
    casos = []
    ex = executar(espec, politica, observador=lambda s, c: casos.append((s, c)), **kw)
    return ex, casos


# ── (a) vazamento de futuro ────────────────────────────────────────────────

def test_a_corte_que_vaza_futuro_levanta_no_ponto_de_consumo():
    vazador = lambda log, as_of, janela: list(log)  # noqa: E731 — ignora o as_of
    with pytest.raises(VazamentoDeFuturo):
        executar(cenario_mini(), Estatica(), cortar=vazador)


def test_a_snapshot_adulterado_entregue_a_politica_levanta():
    _, casos = _capturar(cenario_mini(), Estatica())
    snap, ctx = casos[6]
    futura = replace(snap.observacoes[0], disponivel_em=ctx.as_of + timedelta(hours=1),
                     observado_em=ctx.as_of + timedelta(hours=1))
    adulterado = Snapshot(as_of=snap.as_of, observacoes=snap.observacoes + (futura,), manifesto=snap.manifesto)
    for p in baselines() + [proporcional_ingenua()]:
        with pytest.raises(VazamentoDeFuturo):
            p.decidir(adulterado, ctx)
    # snapshot de outro as_of (posterior) também é recusado
    posterior = Snapshot.construir(snap.observacoes, ctx.as_of + timedelta(days=1))
    with pytest.raises(VazamentoDeFuturo):
        Igual().decidir(posterior, ctx)


def test_a_corte_padrao_nunca_entrega_futuro():
    _, casos = _capturar(cenario_mini(), Proporcional())
    assert casos
    for snap, ctx in casos:
        assert all(o.disponivel_em <= ctx.as_of for o in snap.observacoes)
        assert snap.as_of == ctx.as_of


# ── (b) null tratado como zero ─────────────────────────────────────────────

def test_b_auditoria_metamorfica_detecta_politica_ingenua():
    espec = replace(cenario_mini(), p_receita_falha_prelim=0.4, p_custo_nao_coletado=0.2)
    _, casos = _capturar(espec, Estatica())
    ingenua = auditar_null_vs_zero(proporcional_ingenua(), casos)
    correta = auditar_null_vs_zero(Proporcional(), casos)
    assert ingenua["snapshots_com_lacuna"] > 0
    assert ingenua["suspeita_null_como_zero"] is True
    assert ingenua["decisoes_que_distinguem_null_de_zero"] == 0
    assert correta["suspeita_null_como_zero"] is False
    assert correta["decisoes_que_distinguem_null_de_zero"] > 0


def test_b_unidade_sem_receita_fica_fora_com_motivo_e_ingenua_nao():
    espec = replace(cenario_mini(), p_receita_nao_coletada=1.0)  # nenhuma receita jamais tem valor
    _, casos = _capturar(espec, Estatica())
    snap, ctx = casos[-1]
    certa = Proporcional().decidir(snap, ctx)
    assert set(certa.excluidas) == set(ctx.unidades)
    assert all("null != 0" in m for m in certa.excluidas.values())
    assert certa.alocacao == dict(ctx.alocacao_atual)  # sem informação, não realoca
    ing = proporcional_ingenua().decidir(snap, ctx)
    assert ing.excluidas == {}
    assert ing.alocacao != certa.alocacao  # ingênua realoca em cima de "receita 0" inventada


def test_b_ingenua_diverge_no_replay_completo():
    espec = cenario_mini()
    a = relatorio_cenario(espec, [executar(espec, Proporcional())])["politicas"][0]
    b = relatorio_cenario(espec, [executar(espec, proporcional_ingenua())])["politicas"][0]
    assert a["decisoes_sha256"] != b["decisoes_sha256"]
    assert a["exclusoes_unidade_dia"] > 0 and b["exclusoes_unidade_dia"] == 0


# ── (c) moeda misturada ────────────────────────────────────────────────────

class _PoolUnico:
    """Política errada: soma os orçamentos de todas as moedas num pool só."""

    nome = "pool_unico"

    def decidir(self, snapshot, ctx):
        total = None
        for u in ctx.unidades:
            v = ctx.alocacao_atual[u]
            total = v if total is None else total + v  # BRL + USD -> MoedasDiferentes
        return Decisao(dict(ctx.alocacao_atual))


class _MoedaTrocada:
    nome = "moeda_trocada"

    def decidir(self, snapshot, ctx):
        aloc = dict(ctx.alocacao_atual)
        usd = next(u for u in ctx.unidades if ctx.moeda_por_unidade[u] == "USD")
        aloc[usd] = Dinheiro(aloc[usd].micros, "BRL")
        return Decisao(aloc)


def test_c_moeda_misturada_e_erro():
    with pytest.raises(MoedasDiferentes):
        executar(cenario_mini(), _PoolUnico())
    with pytest.raises(MoedasDiferentes):
        executar(cenario_mini(), _MoedaTrocada())


def test_c_receita_de_moedas_diferentes_nao_agrega_e_relatorio_separa_moedas():
    _, casos = _capturar(cenario_mini(), Estatica())
    snap, _ = casos[-1]
    receitas = [o for o in snap.filtrar(metrica=Metrica.RECEITA) if o.moeda]
    assert {o.moeda for o in receitas} == {"BRL", "USD"}
    with pytest.raises(MoedasDiferentes):
        agregar(receitas, aceitar_parcial=True)
    rel = relatorio_cenario(cenario_mini(), [executar(cenario_mini(), Igual())])
    assert set(rel["politicas"][0]["por_moeda"]) == {"BRL", "USD"}


# ── (d) identidade trocada ─────────────────────────────────────────────────

def test_d_mesmo_entidade_id_em_outra_conta_e_ignorado_com_nota():
    espec = cenario_mini()
    alvo = Mundo(espec).unidades[0].chave
    impostora = ChaveUnidade("acc-OUTRA", alvo.tipo_entidade, alvo.entidade_id, alvo.grao)

    def cortar_com_impostora(log, as_of, janela):
        base = cortar_as_of(log, as_of, janela)
        extra = [replace(o, unidade=impostora, valor=Dinheiro(o.valor.micros * 50, o.valor.moeda), coleta_id=o.coleta_id + ":imp")
                 for o in base if o.unidade == alvo and o.metrica is Metrica.RECEITA and o.valor is not None]
        return base + extra

    limpo = executar(espec, Proporcional())
    sujo = executar(espec, Proporcional(), cortar=cortar_com_impostora)
    assert [d.alocacao for d in limpo.decisoes] == [d.alocacao for d in sujo.decisoes]
    notas = [n for d in sujo.decisoes for n in d.notas]
    assert any(n.startswith("identidade_incompativel") and "acc-OUTRA" in n for n in notas)

    _, casos = _capturar(espec, Estatica(), cortar=cortar_com_impostora)
    snap, _ = casos[-1]
    rec_imp = next(o for o in snap.observacoes if o.unidade == impostora)
    custo = next(o for o in snap.observacoes
                 if o.unidade == alvo and o.metrica is Metrica.CUSTO and dia_de(o) == dia_de(rec_imp))
    with pytest.raises(IdentidadeIncompativel):
        contribuicao(custo, rec_imp)


# ── (e) restatement ────────────────────────────────────────────────────────

def test_e_decisao_usa_preliminar_e_nao_a_revisada():
    espec = replace(cenario_mini(), p_receita_falha_prelim=0.0, p_receita_nao_coletada=0.0)
    mundo = Mundo(espec)
    ex, casos = _capturar(espec, Proporcional())
    verificados = 0
    for snap, ctx in casos:
        idx = indexar(snap)
        i = (ctx.dia - mundo.espec.inicio).days
        if i < 5:
            continue
        for u in ctx.unidades:
            recente = idx[(u, Metrica.RECEITA, ctx.dia - timedelta(days=2))]
            verdade = mundo.receita_verdadeira(u, i - 2, ex.alocacoes[i - 2][u].micros)
            assert recente.maturidade is Maturidade.PRELIMINAR
            assert recente.valor.micros != verdade  # preliminar ≠ revisão final
            antigo = idx[(u, Metrica.RECEITA, ctx.dia - timedelta(days=4))]
            assert antigo.maturidade is Maturidade.REVISADA
            assert antigo.valor.micros == mundo.receita_verdadeira(u, i - 4, ex.alocacoes[i - 4][u].micros)
            verificados += 1
        assert idx.get((ctx.unidades[0], Metrica.RECEITA, ctx.dia - timedelta(days=1))) is None  # ainda não reportado
    assert verificados > 0
    assert all(d.insumos_preliminares > 0 for d in ex.decisoes[3:])
    gulosa = executar(espec, GulosaConservadora())
    assert all(d.insumos_preliminares == 0 for d in gulosa.decisoes)


def test_e_snapshot_registra_versao_substituida():
    _, casos = _capturar(cenario_mini(), Estatica())
    snap, _ = casos[-1]
    assert snap.manifesto["n_versoes_substituidas"] > 0


# ── (f) reprodutibilidade ──────────────────────────────────────────────────

def test_f_mesma_seed_mesmo_relatorio_byte_a_byte():
    espec = cenario_mini()
    r1 = bytes_relatorio(relatorio_cenario(espec, [executar(espec, p) for p in baselines()]))
    r2 = bytes_relatorio(relatorio_cenario(espec, [executar(espec, p) for p in baselines()]))
    assert r1 == r2
    outra = bytes_relatorio(relatorio_cenario(replace(espec, seed=8), [executar(replace(espec, seed=8), p) for p in baselines()]))
    assert outra != r1


def test_f_fixture_versionada_confere_byte_a_byte():
    spec = importlib.util.spec_from_file_location("replay_gerar_fixture", LAB / "scripts" / "replay_gerar_fixture.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    conteudo, manifesto = mod.construir()
    arq = LAB / "fixtures" / "replay" / "cenario_mini.json"
    assert arq.read_bytes() == conteudo
    gravado = json.loads((LAB / "fixtures" / "replay" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert gravado == manifesto
    assert sha256_arquivo(str(arq)) == gravado["sha256"]
    assert gravado["natureza"] == "sintetico"


def test_f_mundo_igual_para_todas_as_politicas():
    """Números aleatórios comuns: a verdade não depende da ordem de execução das políticas."""
    espec = cenario_mini()
    m1, m2 = Mundo(espec), Mundo(espec)
    u = m1.unidades[1].chave
    a = [m1.eficiencia(u, i) for i in range(espec.n_dias)]
    executar(espec, Igual())
    b = [m2.eficiencia(u, i) for i in reversed(range(espec.n_dias))][::-1]
    assert a == b


# ── utilitários ────────────────────────────────────────────────────────────

def test_repartir_soma_exata_e_drawdown():
    assert sum(repartir(1_000_000_007, [3, 1, 1])) == 1_000_000_007
    assert repartir(10, [0, 0]) == [5, 5]
    assert drawdown_maximo([5, -3, -4, 10, -1]) == 7


def test_orcamento_fecha_por_moeda_em_todas_as_decisoes():
    espec = cenario_mini()
    orc = Mundo(espec).orcamento_total()
    for p in baselines():
        ex = executar(espec, p)
        for a in ex.alocacoes:
            por_moeda = {}
            for v in a.values():
                por_moeda[v.moeda] = por_moeda.get(v.moeda, 0) + v.micros
            assert por_moeda == orc


def test_b_auditoria_nao_confunde_politica_cega_com_null_como_zero():
    _, casos = _capturar(replace(cenario_mini(), p_receita_falha_prelim=0.4), Estatica())
    for p in (Estatica(), Igual()):
        r = auditar_null_vs_zero(p, casos)
        assert r["cega_a_dados"] is True and r["suspeita_null_como_zero"] is False
