"""Ledger shadow append-only: cadeia de hash, retomada, adulteração, sink restrito e resultado maduro."""
from __future__ import annotations

import json

import pytest

from volc_dil.fundacao.shadow._gerador_provisorio import preparar
from volc_dil.fundacao.shadow.avaliacao import registrar_resultados_maduros
from volc_dil.fundacao.shadow.fluxo import FluxoIndexado
from volc_dil.fundacao.shadow.ledger import (
    LedgerCorrompido,
    LedgerShadow,
    SinkJsonl,
    SinkProibido,
    verificar_cadeia,
)
from volc_dil.fundacao.shadow.motor import executar_replay
from volc_dil.fundacao.shadow.politicas import Manter, RegraMargem


@pytest.fixture(scope="module")
def replay():
    fs, cortes, cfg = preparar("base", passo_horas=12, hora_inicial=7)
    return fs, cortes, cfg


def test_cadeia_append_only_e_retomada(replay, tmp_path):
    fs, cortes, cfg = replay
    led = LedgerShadow(SinkJsonl(tmp_path))
    executar_replay(fs.observacoes, cortes[:4], [Manter(), RegraMargem()], config=cfg, seed=7, ledger=led)
    n = verificar_cadeia(tmp_path / "ledger.jsonl")
    assert n == len(led) == 8
    assert not any(hasattr(led, m) for m in ("apagar", "atualizar", "update", "delete", "remover"))
    e0 = led.entradas[0]
    assert e0["tipo"] == "decisao" and e0["seed"] == 7 and e0["versao_codigo"] and e0["fingerprint_corte"]
    assert all(p["executavel"] is False for e in led.entradas for p in e["propostas"])
    # retomada: um ledger novo sobre o mesmo arquivo continua a cadeia
    led2 = LedgerShadow(SinkJsonl(tmp_path))
    assert led2.ultimo_hash == led.ultimo_hash
    executar_replay(fs.observacoes, cortes[4:5], [Manter()], config=cfg, ledger=led2)
    assert verificar_cadeia(tmp_path / "ledger.jsonl") == 9


def test_adulteracao_e_detectada(replay, tmp_path):
    fs, cortes, cfg = replay
    led = LedgerShadow(SinkJsonl(tmp_path))
    executar_replay(fs.observacoes, cortes[:3], [RegraMargem()], config=cfg, ledger=led)
    arq = tmp_path / "ledger.jsonl"
    linhas = arq.read_text().splitlines()
    e = json.loads(linhas[1])
    e["propostas"][0]["acao"] = "pausar"
    linhas[1] = json.dumps(e, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    arq.write_text("\n".join(linhas) + "\n")
    with pytest.raises(LedgerCorrompido):
        verificar_cadeia(arq)
    with pytest.raises(LedgerCorrompido):
        LedgerShadow(SinkJsonl(tmp_path))  # não continua cadeia quebrada


def test_sink_restrito(tmp_path):
    with pytest.raises(SinkProibido):
        SinkJsonl(tmp_path, "../fora.jsonl")
    with pytest.raises(SinkProibido):
        SinkJsonl(tmp_path / "nao_existe")
    with pytest.raises(SinkProibido):
        SinkJsonl(tmp_path, ".oculto")

    class SinkExterno:
        externo = True

        def anexar(self, linha):  # pragma: no cover
            raise AssertionError

    with pytest.raises(SinkProibido):
        LedgerShadow(SinkExterno())  # type: ignore[arg-type]


def test_resultado_maduro_referencia_a_decisao(replay):
    fs, cortes, cfg = replay
    led = LedgerShadow()
    fi = FluxoIndexado(fs.observacoes)
    res = executar_replay(fi, cortes, [RegraMargem()], config=cfg, ledger=led)
    n_dec = len(led)
    n = registrar_resultados_maduros(led, res, fi, cfg, hora_decisao=7, k_dias=4, verdade=fs.verdade)
    assert n > 0 and len(led) == n_dec + n
    hashes = {e["hash"] for e in led.entradas if e["tipo"] == "decisao"}
    resultados = [e for e in led.entradas if e["tipo"] == "resultado"]
    assert all(r["ref_hash"] in hashes for r in resultados)
    itens = [i for r in resultados for i in r["resultado"]["itens"]]
    assert any(i.get("lucro_realizado_manter_micros") is not None for i in itens)
    assert all(i["contrafactual_pausa_micros"] == 0 for i in itens)
    assert all("verdade_lucro_manter_micros" in i for i in itens)
    with pytest.raises(LedgerCorrompido):
        led.registrar_resultado(ref_hash="0" * 64, as_of_maduro="x", k_dias=1, resultado={})
    with pytest.raises(TypeError):
        led.registrar_resultado(ref_hash=resultados[0]["ref_hash"], as_of_maduro="x", k_dias=1, resultado={"v": 0.5})
