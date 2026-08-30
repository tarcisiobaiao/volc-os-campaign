"""O worker precisa falhar sem sujeira, e nunca deixar a senha no disco.

Estes testes exercitam as BLINDAGENS, não o caminho feliz — o caminho feliz
custa US$ 2 e 45 minutos, e quem prova ele é um run de verdade. O que dá para
provar barato é o que acontece quando algo dá errado, que é justamente onde um
worker costuma vazar arquivo, processo ou credencial.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.redator import worker


class _SupaFalso:
    """Registra os patches que o worker mandaria para o Supabase."""

    def __init__(self) -> None:
        self.patches: list[dict] = []
        self.linhas: list[dict] = []

    async def patch(self, tabela, match, valores):
        self.patches.append({"tabela": tabela, "match": match, **valores})
        return []

    async def select(self, tabela, params):
        return list(self.linhas)

    @property
    def status_gravados(self) -> list[str]:
        return [p["status"] for p in self.patches if "status" in p]


ARQ = {"pages": [{"role": "landing", "position": 1}]}
PERFIL = {
    "site": {"domain": "https://exemplo.com.br", "post_type": "rec", "lp_post_type": "r"},
    "wordpress": {"url": "https://exemplo.com.br", "user": "u", "app_token": "SENHA-SECRETA-XYZ"},
    "tema": {"termos": ["a"], "official_preference": []},
}


def test_resumo_do_estado_conta_o_que_a_tela_precisa():
    """A única regra de negócio do módulo: o que é etapa feita e página pronta."""
    estado = {
        "run_id": "cartao-negativado-20260815-101010",
        "plan": {"pages": [{"page_number": 1}, {"page_number": 2}, {"page_number": 3}]},
        "step_status": {
            "research_p1": {"status": "OK", "cost_usd": 0.15},
            "write_p1": {"status": "RETRIED", "cost_usd": 0.20},
            "build_p1": {"status": "OK"},
            "research_p2": {"status": "OK", "cost_usd": 0.12},
            "write_p2": {"status": "FAILED"},
            "research_p3": {"status": "OK", "cost_usd": 0.10},
        },
    }
    r = worker.resumo_do_estado(estado)

    assert r["run_id"] == "cartao-negativado-20260815-101010"
    assert r["paginas_planejadas"] == 3
    # só a p1 chegou ao build; página sem build não tem artefato nenhum
    assert r["paginas_geradas"] == 1
    assert r["custo_usd"] == pytest.approx(0.57)
    # RETRIED conta como concluída: ela entregou, só custou mais tentativas
    assert r["etapas_concluidas"] == 5
    assert r["etapas_falhadas"] == ["write_p2"]


def test_estado_vazio_nao_inventa_numero():
    r = worker.resumo_do_estado({"plan": {"pages": []}, "step_status": {}})
    assert r["paginas_planejadas"] is None
    assert r["paginas_geradas"] is None
    assert r["custo_usd"] is None


def test_achar_run_dir_prefere_a_pasta_definitiva(tmp_path: Path):
    """O motor cria `_pending-<carimbo>` e renomeia para `<slug>-<carimbo>`.
    Se as duas existirem no momento da leitura, a definitiva é a certa."""
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "_pending-20260815-101010").mkdir()
    (runs / "cartao-negativado-20260815-101010").mkdir()
    (runs / "outro-funil-20260101-000000").mkdir()

    achada = worker._achar_run_dir(tmp_path, "20260815-101010")
    assert achada is not None and achada.name == "cartao-negativado-20260815-101010"

    assert worker._achar_run_dir(tmp_path, "20991231-235959") is None


def test_ler_estado_tolera_arquivo_ausente_ou_quebrado(tmp_path: Path):
    """O motor grava com write-then-rename, então o arquivo nunca fica pela
    metade — mas pode não existir ainda. Ler no meio não pode explodir."""
    assert worker._ler_estado(tmp_path) is None
    (tmp_path / "state.json").write_text("{ isto não é json", encoding="utf-8")
    assert worker._ler_estado(tmp_path) is None
    (tmp_path / "state.json").write_text('{"run_id": "x"}', encoding="utf-8")
    assert worker._ler_estado(tmp_path) == {"run_id": "x"}


def test_motor_ausente_falha_na_linha_e_nao_na_api(monkeypatch, tmp_path: Path):
    """Motor não instalado tem que virar `failed` com instrução — nunca exceção
    subindo para a rota, que derrubaria a requisição do operador."""
    monkeypatch.setattr(worker, "raiz_do_motor", lambda: tmp_path / "nao-existe")
    supa = _SupaFalso()

    asyncio.run(worker.executar(supa=supa, run_row_id=7, arquitetura=ARQ, perfil=PERFIL))

    assert supa.status_gravados[-1] == "failed"
    erro = [p for p in supa.patches if p.get("erro")][-1]["erro"]
    assert "comando do motor não existe" in erro
    assert "pip install" in erro          # a mensagem diz COMO resolver


def test_a_senha_nunca_sobra_no_disco(monkeypatch, tmp_path: Path):
    """O perfil com a senha decifrada vai para arquivo temporário. Se ele
    sobrevivesse a uma falha, uma credencial de admin ficaria em /tmp."""
    monkeypatch.setattr(worker, "raiz_do_motor", lambda: tmp_path / "nao-existe")
    temporarios_criados: list[Path] = []
    original = worker.tempfile.mkdtemp

    def espiao(*a, **k):
        d = original(*a, **k)
        temporarios_criados.append(Path(d))
        return d

    monkeypatch.setattr(worker.tempfile, "mkdtemp", espiao)

    asyncio.run(worker.executar(supa=_SupaFalso(), run_row_id=8,
                                arquitetura=ARQ, perfil=PERFIL))

    assert temporarios_criados, "o worker nem chegou a criar o temporário"
    for d in temporarios_criados:
        assert not d.exists(), f"o diretório com a senha sobreviveu: {d}"


def test_reconciliar_fecha_o_que_ficou_orfao_de_um_reinicio():
    """Sem isto, um reinício do backend deixa linhas eternamente 'escrevendo':
    a tela mostra trabalho que não existe e o disparo recusa por duplicata."""
    supa = _SupaFalso()
    supa.linhas = [{"id": 11, "status": "running"}, {"id": 12, "status": "queued"}]

    n = asyncio.run(worker.reconciliar(supa))

    assert n == 2
    assert supa.status_gravados == ["failed", "failed"]
    assert "reiniciado" in supa.patches[0]["erro"]


def test_reconciliar_nao_mata_run_vivo(monkeypatch):
    """Um run que ESTE processo está tocando não é órfão."""
    supa = _SupaFalso()
    supa.linhas = [{"id": 21, "status": "running"}]
    monkeypatch.setitem(worker._em_execucao, 21, object())

    n = asyncio.run(worker.reconciliar(supa))

    assert n == 0 and supa.patches == []


def test_cancelar_run_que_nao_existe_devolve_falso():
    assert asyncio.run(worker.cancelar(999)) is False


def test_artefatos_lista_o_que_saiu(tmp_path: Path):
    (tmp_path / "p1.elementor.json").write_text("{}")
    (tmp_path / "state.json").write_text("{}")
    (tmp_path / "subpasta").mkdir()

    a = worker._artefatos(tmp_path)
    assert a["pasta"] == tmp_path.name
    assert "p1.elementor.json" in a["arquivos"]
    assert "subpasta" not in a["arquivos"]      # só arquivo, não diretório
