"""O executor portátil: durabilidade, isolamento, determinismo e recibo.

Estas provas existem porque o executor anterior era `asyncio.create_task` dentro
de uma função serverless da Vercel — fire-and-forget num processo que a plataforma
congela quando a resposta sai. Cada teste aqui corresponde a uma forma específica
de o executor mentir sobre o que fez.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from app.criativo.bancada.adaptadores.tipografico import (
    MotorTipografico,
    razao_de_contraste,
)
from app.criativo.bancada.contrato import (
    Artefato,
    Encomenda,
    EstadoDoTrabalho,
    FalhaDoMotor,
    SaidaPedida,
    TransicaoProibida,
    Validacao,
    pode_ir,
)
from app.criativo.bancada.deposito import DepositoDeTrabalhos
from app.criativo.bancada.operario import Operario


def encomenda(seed: int = 7, titulo: str = "Inscrições abertas", **extra: Any) -> Encomenda:
    return Encomenda(
        receita_id=extra.pop("receita_id", "receita-1"),
        tenant_id=extra.pop("tenant_id", "tenant-A"),
        motor_slug=extra.pop("motor_slug", "tipografico-local"),
        modo_slug="typography_only",
        finalidade_slug="google_display",
        seed=seed,
        saidas=extra.pop(
            "saidas", (SaidaPedida("1x1", 1080, 1080, "imagem", "image/png"),)
        ),
        parametros={"titulo": titulo, "apoio": "até 30 de setembro", **extra},
    )


@pytest.fixture
def bancada(tmp_path: Path):
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    operario = Operario(
        deposito, {"tipografico-local": MotorTipografico()}, tmp_path / "trabalhos"
    )
    return deposito, operario


# ═══════════════════════════════════════════════════════════════════════════
# 1. O contrato não conhece infraestrutura
# ═══════════════════════════════════════════════════════════════════════════


def test_o_contrato_nao_importa_infraestrutura():
    """Se um dia alguém precisar de `httpx` aqui, a camada errada está sendo tocada."""
    import ast

    caminho = (
        Path(__file__).resolve().parents[1] / "app/criativo/bancada/contrato.py"
    )
    # ⚠️ Varre a ÁRVORE, não o texto: a primeira versão deste teste procurava a
    # string "import httpx" e batia na própria docstring, que cita o exemplo. Um
    # teste que falha por causa de um comentário treina a pessoa a desligá-lo.
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    modulos: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            modulos.add(no.module.split(".")[0])

    permitidos = {"__future__", "hashlib", "json", "dataclasses", "enum", "typing"}
    assert modulos <= permitidos, (
        f"o contrato importou {sorted(modulos - permitidos)}; ele só pode conhecer "
        "a linguagem, nunca infraestrutura"
    )


def test_transicao_fora_do_mapa_e_recusada():
    assert pode_ir(EstadoDoTrabalho.QUEUED, EstadoDoTrabalho.CLAIMED)
    assert not pode_ir(EstadoDoTrabalho.RENDERED, EstadoDoTrabalho.RUNNING)
    assert not pode_ir(EstadoDoTrabalho.FAILED, EstadoDoTrabalho.QUEUED)


def test_encomenda_sem_seed_nao_compila():
    """`seed` não tem default de propósito: um render sem semente não pode ser
    repetido, e default faria metade dos trabalhos nascer com a mesma semente por
    acidente — parece determinismo e não é."""
    with pytest.raises(TypeError):
        Encomenda(  # type: ignore[call-arg]
            receita_id="r", tenant_id="t", motor_slug="m", modo_slug="x",
            finalidade_slug="y", saidas=(),
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Idempotência e fila
# ═══════════════════════════════════════════════════════════════════════════


def test_mesma_encomenda_nao_cria_dois_trabalhos(bancada):
    deposito, _ = bancada
    t1, criado1 = deposito.enfileirar(encomenda())
    t2, criado2 = deposito.enfileirar(encomenda())
    assert criado1 is True and criado2 is False
    assert t1.id == t2.id


def test_pedido_diferente_cria_trabalho_diferente(bancada):
    deposito, _ = bancada
    t1, _ = deposito.enfileirar(encomenda(seed=7))
    t2, _ = deposito.enfileirar(encomenda(seed=8))
    assert t1.id != t2.id


def test_dois_operarios_nao_reivindicam_o_mesmo_trabalho(bancada):
    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    primeiro = deposito.reivindicar("op-1")
    segundo = deposito.reivindicar("op-2")
    assert primeiro is not None
    assert segundo is None, "dois operários pegaram o mesmo trabalho"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Lease e batimento
# ═══════════════════════════════════════════════════════════════════════════


def test_lease_vencido_volta_para_a_fila_e_nao_vira_falha(bancada):
    """Um operário que morreu não torna o pedido inválido."""
    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    pego = deposito.reivindicar("op-que-morre", lease_s=-1)
    assert pego is not None and pego.estado is EstadoDoTrabalho.CLAIMED
    assert pego.vivo is False, "lease negativo não pode ser considerado vivo"

    devolvidos = deposito.devolver_vencidos()
    assert devolvidos == 1
    de_novo = deposito.por_id(pego.id)
    assert de_novo.estado is EstadoDoTrabalho.QUEUED
    assert de_novo.operario is None
    assert de_novo.tentativa == 1, "a tentativa já foi contada e não se perde"


def test_ausencia_de_batimento_nao_e_execucao_ativa(bancada):
    """Tratar lease vencido como 'ainda rodando' é o defeito que a auditoria procura."""
    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    pego = deposito.reivindicar("op", lease_s=-1)
    assert pego.vivo is False
    assert pego.batimento_em is not None, "houve UM batimento: o da reivindicação"


def test_batimento_renova_o_lease(bancada):
    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    pego = deposito.reivindicar("op", lease_s=1)
    assert deposito.bater(pego.id, lease_s=60) is True
    assert deposito.por_id(pego.id).vivo is True


def test_batimento_e_recusado_depois_que_o_trabalho_termina(bancada):
    deposito, operario = bancada
    deposito.enfileirar(encomenda())
    feito = operario.trabalhar_uma_vez()
    assert feito.estado is EstadoDoTrabalho.RENDERED
    assert deposito.bater(feito.id) is False


def test_tentativas_esgotadas_viram_falha_e_nao_fila_infinita(bancada):
    deposito, _ = bancada
    deposito.enfileirar(encomenda(), max_tentativas=2)
    for _ in range(2):
        pego = deposito.reivindicar("op", lease_s=-1)
        assert pego is not None
        deposito.devolver_vencidos()
    assert deposito.reivindicar("op") is None
    (t,) = [deposito.por_chave(encomenda().chave_de_idempotencia())]
    assert t.estado is EstadoDoTrabalho.FAILED
    assert t.falha["codigo"] == "tentativas_esgotadas"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Nada é "concluído" sem prova
# ═══════════════════════════════════════════════════════════════════════════


def test_nao_se_conclui_trabalho_sem_recibo(bancada):
    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op")
    deposito.transicionar(t.id, EstadoDoTrabalho.RUNNING)
    deposito.transicionar(t.id, EstadoDoTrabalho.VALIDATING)
    with pytest.raises(ValueError, match="sem recibo"):
        deposito.transicionar(t.id, EstadoDoTrabalho.RENDERED)


def test_nao_se_falha_trabalho_sem_motivo(bancada):
    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op")
    with pytest.raises(ValueError, match="sem motivo"):
        deposito.transicionar(t.id, EstadoDoTrabalho.FAILED)


def test_motor_que_nao_produz_artefato_falha(bancada, tmp_path):
    class MotorVazio:
        slug, versao = "vazio", "0"

        def versoes_congeladas(self) -> dict[str, str]:
            return {}

        def produzir(self, *_: Any) -> tuple[Artefato, ...]:
            return ()

    deposito, _ = bancada
    op = Operario(deposito, {"vazio": MotorVazio()}, tmp_path / "t2")
    deposito.enfileirar(encomenda(motor_slug="vazio"))
    feito = op.trabalhar_uma_vez()
    assert feito.estado is EstadoDoTrabalho.FAILED
    assert feito.recibo is None


def test_estado_terminal_nao_volta_atras(bancada):
    deposito, operario = bancada
    deposito.enfileirar(encomenda())
    feito = operario.trabalhar_uma_vez()
    with pytest.raises(TransicaoProibida):
        deposito.transicionar(feito.id, EstadoDoTrabalho.RUNNING)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Determinismo
# ═══════════════════════════════════════════════════════════════════════════


def test_o_mesmo_pedido_produz_os_mesmos_bytes(tmp_path):
    motor = MotorTipografico()
    e = encomenda(seed=42, titulo="Curso Positivo 2027")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a = motor.produzir(e, str(tmp_path / "a"))
    b = motor.produzir(e, str(tmp_path / "b"))
    assert [x.sha256 for x in a] == [x.sha256 for x in b]
    assert [x.bytes_ for x in a] == [x.bytes_ for x in b]


def test_semente_diferente_muda_o_pixel(tmp_path):
    motor = MotorTipografico()
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a = motor.produzir(encomenda(seed=1), str(tmp_path / "a"))
    b = motor.produzir(encomenda(seed=2), str(tmp_path / "b"))
    assert a[0].sha256 != b[0].sha256


def test_recibos_do_mesmo_pedido_tem_a_mesma_assinatura(tmp_path):
    """A assinatura exclui id e carimbo de tempo de propósito: eles mudam sempre e
    tornariam a assinatura inútil para responder "o motor repetiu?"."""
    d1 = DepositoDeTrabalhos(tmp_path / "f1.db")
    d2 = DepositoDeTrabalhos(tmp_path / "f2.db")
    o1 = Operario(d1, {"tipografico-local": MotorTipografico()}, tmp_path / "t1")
    o2 = Operario(d2, {"tipografico-local": MotorTipografico()}, tmp_path / "t2")
    d1.enfileirar(encomenda(seed=99))
    d2.enfileirar(encomenda(seed=99))
    r1 = o1.trabalhar_uma_vez().recibo
    r2 = o2.trabalhar_uma_vez().recibo

    assert r1["trabalho_id"] != r2["trabalho_id"], "são trabalhos diferentes"
    assert r1["assinatura_determinista"] == r2["assinatura_determinista"]


def test_o_recibo_congela_a_versao_da_fonte(tmp_path):
    """Trocar o arquivo da fonte muda o pixel; um recibo que não registrasse isso
    mentiria sobre reprodutibilidade."""
    d = DepositoDeTrabalhos(tmp_path / "f.db")
    o = Operario(d, {"tipografico-local": MotorTipografico()}, tmp_path / "t")
    d.enfileirar(encomenda())
    versoes = o.trabalhar_uma_vez().recibo["versoes"]
    assert len(versoes["fonte_sha256"]) == 64
    assert versoes["fonte_arquivo"].lower().endswith((".ttf", ".otf", ".ttc"))
    assert versoes["pillow"] and versoes["adaptador"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. Concorrência: dois trabalhos não se contaminam
# ═══════════════════════════════════════════════════════════════════════════


def test_dois_trabalhos_simultaneos_nao_compartilham_arquivo(tmp_path):
    """Resposta direta ao defeito medido na fábrica: 21 dos 26 geradores escrevem
    em `clips_registry.json`/`timings.json`/`props.json` na raiz, e por isso dois
    renders simultâneos lá se contaminam."""
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    raiz = tmp_path / "trabalhos"
    deposito.enfileirar(encomenda(seed=11, titulo="Peça A do operador um"))
    deposito.enfileirar(encomenda(seed=22, titulo="Peça B do operador dois"))

    def rodar(n: int):
        op = Operario(
            deposito, {"tipografico-local": MotorTipografico()}, raiz, nome=f"op-{n}"
        )
        return op.trabalhar_uma_vez()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        feitos = [f.result() for f in [pool.submit(rodar, 1), pool.submit(rodar, 2)]]

    assert all(t is not None for t in feitos)
    assert {t.estado for t in feitos} == {EstadoDoTrabalho.RENDERED}
    assert len({t.id for t in feitos}) == 2, "os dois operários pegaram trabalhos distintos"
    # ⚠️ `operario` é o portador do LEASE e some quando o trabalho termina — quem
    # produziu fica no recibo, que é o registro permanente.
    assert all(t.operario is None for t in feitos), "o lease não foi solto no fim"
    assert len({t.recibo["produzido_por"] for t in feitos}) == 2

    caminhos = [Path(t.recibo["artefatos"][0]["caminho"]) for t in feitos]
    assert caminhos[0].parent != caminhos[1].parent, "dois jobs no mesmo diretório"
    assert all(p.exists() for p in caminhos)
    hashes = {t.recibo["artefatos"][0]["sha256"] for t in feitos}
    assert len(hashes) == 2, "os dois artefatos saíram idênticos: houve contaminação"


def test_o_diretorio_de_trabalho_e_exclusivo_do_trabalho(bancada, tmp_path):
    deposito, operario = bancada
    deposito.enfileirar(encomenda(seed=1))
    deposito.enfileirar(encomenda(seed=2))
    a = operario.trabalhar_uma_vez()
    b = operario.trabalhar_uma_vez()
    da = Path(a.recibo["artefatos"][0]["caminho"]).parent
    db = Path(b.recibo["artefatos"][0]["caminho"]).parent
    assert da != db
    # ⚠️ O caminho ganhou um nível (achado #13): a pasta do TRABALHO contém uma
    # pasta por REIVINDICAÇÃO. Sem isso, dois operários que disputam o mesmo
    # trabalho — o que acontece quando um lease vence — produziam no mesmo
    # diretório, e quem perdia o lease apagava o do novo dono. O invariante que
    # este teste protege segue de pé: dois trabalhos nunca dividem caminho.
    assert da.parent.name == a.id and db.parent.name == b.id
    assert not da.is_relative_to(db) and not db.is_relative_to(da)


def test_o_motor_nao_usa_o_random_global(tmp_path):
    """O `random` do módulo é estado compartilhado entre jobs: dois trabalhos
    simultâneos se contaminariam como os geradores da fábrica se contaminam."""
    import random as _r

    motor = MotorTipografico()
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _r.seed(1)
    a = motor.produzir(encomenda(seed=5), str(tmp_path / "a"))
    _r.seed(999999)
    b = motor.produzir(encomenda(seed=5), str(tmp_path / "b"))
    assert a[0].sha256 == b[0].sha256, "mexer no random global mudou o resultado"


# ═══════════════════════════════════════════════════════════════════════════
# 7. Números preservados como números
# ═══════════════════════════════════════════════════════════════════════════


def test_o_contraste_vai_ao_recibo_com_o_numero(bancada):
    """Um gate que só diz "passou" impede a próxima pergunta: passou por quanto?"""
    deposito, operario = bancada
    deposito.enfileirar(encomenda())
    r = operario.trabalhar_uma_vez().recibo
    contraste = [v for v in r["validacoes"] if v["gate"] == "contraste"][0]
    assert contraste["resultado"] == "PASS"
    assert isinstance(contraste["detalhe"]["razao"], float)
    assert contraste["detalhe"]["razao"] >= 4.5
    assert contraste["detalhe"]["piso_aa"] == 4.5
    assert "WCAG" in contraste["detalhe"]["fonte"]


def test_a_razao_de_contraste_segue_a_formula_publica():
    branco, preto = (255, 255, 255), (0, 0, 0)
    assert round(razao_de_contraste(branco, preto), 1) == 21.0
    assert round(razao_de_contraste(branco, branco), 2) == 1.0
    assert razao_de_contraste(preto, branco) == razao_de_contraste(branco, preto)


def test_motor_que_nao_mede_contraste_marca_SKIPPED_e_nao_PASS(bancada, tmp_path):
    """Ausência de medição não é aprovação."""

    class MotorSemMedida:
        slug, versao = "sem-medida", "1"

        def versoes_congeladas(self) -> dict[str, str]:
            return {"adaptador": "1"}

        def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
            import hashlib

            p = Path(d) / "x.png"
            dados = b"\x89PNG\r\n\x1a\n" + b"0" * 64
            p.write_bytes(dados)
            # ⚠️ hash REAL. A primeira versão deste dublê declarava `"0"*64`, e o
            # teste passava — porque o executor acreditava no que o motor dizia.
            # Depois que o executor passou a conferir contra o disco, o dublê
            # mentiroso reprova, que é o comportamento certo.
            return (Artefato("1x1", str(p), "image/png", len(dados),
                             hashlib.sha256(dados).hexdigest(), 1080, 1080),)

    deposito, _ = bancada
    op = Operario(deposito, {"sem-medida": MotorSemMedida()}, tmp_path / "t3")
    deposito.enfileirar(encomenda(motor_slug="sem-medida"))
    r = op.trabalhar_uma_vez().recibo
    contraste = [v for v in r["validacoes"] if v["gate"] == "contraste"][0]
    assert contraste["resultado"] == "SKIPPED"
    assert contraste["bloqueante"] is False


def test_dimensao_diferente_da_pedida_reprova(bancada, tmp_path):
    class MotorTorto:
        slug, versao = "torto", "1"

        def versoes_congeladas(self) -> dict[str, str]:
            return {}

        def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
            import hashlib

            p = Path(d) / "x.png"
            dados = b"x" * 128
            p.write_bytes(dados)
            return (Artefato("1x1", str(p), "image/png", len(dados),
                             hashlib.sha256(dados).hexdigest(), 640, 480),)

    deposito, _ = bancada
    op = Operario(deposito, {"torto": MotorTorto()}, tmp_path / "t4")
    deposito.enfileirar(encomenda(motor_slug="torto"))
    feito = op.trabalhar_uma_vez()
    assert feito.estado is EstadoDoTrabalho.FAILED
    assert feito.falha["codigo"] == "gate_reprovou"


# ═══════════════════════════════════════════════════════════════════════════
# 8. Durabilidade
# ═══════════════════════════════════════════════════════════════════════════


def test_a_fila_sobrevive_ao_processo(tmp_path):
    """`asyncio.create_task` num processo serverless morre com a resposta. Isto não."""
    caminho = tmp_path / "fila.db"
    d1 = DepositoDeTrabalhos(caminho)
    t, _ = d1.enfileirar(encomenda())
    del d1

    d2 = DepositoDeTrabalhos(caminho)
    achado = d2.por_id(t.id)
    assert achado is not None
    assert achado.estado is EstadoDoTrabalho.QUEUED


def test_motor_desconhecido_falha_com_motivo_legivel(bancada):
    deposito, operario = bancada
    deposito.enfileirar(encomenda(motor_slug="motor-que-nao-existe"))
    feito = operario.trabalhar_uma_vez()
    assert feito.estado is EstadoDoTrabalho.FAILED
    assert feito.falha["codigo"] == "motor_desconhecido"
    assert "motor-que-nao-existe" in feito.falha["mensagem"]


def test_falha_permanente_nao_e_retentada(bancada):
    deposito, operario = bancada
    deposito.enfileirar(encomenda(titulo=""))  # sem título: falha permanente
    feito = operario.trabalhar_uma_vez()
    assert feito.estado is EstadoDoTrabalho.FAILED
    assert feito.falha["permanente"] is True
    assert operario.trabalhar_uma_vez() is None, "falha permanente voltou para a fila"


def test_o_motor_recusa_midia_que_nao_produz(tmp_path):
    motor = MotorTipografico()
    (tmp_path / "a").mkdir()
    e = encomenda(saidas=(SaidaPedida("v", 1080, 1920, "video", "video/mp4"),))
    with pytest.raises(FalhaDoMotor) as erro:
        motor.produzir(e, str(tmp_path / "a"))
    assert erro.value.permanente is True


def test_toda_paleta_do_motor_passa_no_proprio_gate_do_motor():
    """Achado desta rodada: a tabela vinha com o comentário "contraste já
    conferido contra o piso AA" e continha `#168B68` (o `success` do DESIGN.md)
    sobre quase-branco — razão 4.114, abaixo do piso. O comentário afirmava uma
    conferência que ninguém tinha feito, e o próprio gate reprovou a peça.
    """
    from app.criativo.bancada.adaptadores.tipografico import PISO_AA, _PALETAS

    for fundo, tinta in _PALETAS:
        r = razao_de_contraste(fundo, tinta)
        assert r >= PISO_AA, f"paleta {fundo}/{tinta} tem contraste {r:.3f}"


def test_toda_semente_produz_peca_que_passa_no_gate(tmp_path):
    """Varre sementes suficientes para tocar todas as paletas. Uma peça que
    reprova depois de renderizada gastou tempo para descobrir o que dava para
    saber antes."""
    deposito = DepositoDeTrabalhos(tmp_path / "f.db")
    operario = Operario(
        deposito, {"tipografico-local": MotorTipografico()}, tmp_path / "t"
    )
    for seed in range(12):
        deposito.enfileirar(encomenda(seed=seed))
    feitos = []
    while (t := operario.trabalhar_uma_vez()) is not None:
        feitos.append(t)
    assert len(feitos) == 12
    reprovados = [t for t in feitos if t.estado is not EstadoDoTrabalho.RENDERED]
    assert reprovados == [], [t.falha for t in reprovados]


# ═══════════════════════════════════════════════════════════════════════════
# 9. A fatia vertical, ponta a ponta pelo HTTP
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    """Sobe SÓ o router de execução criativa, num app próprio.

    ⚠️ A primeira versão desta fixture fazia `from app.main import app`. Importar
    o app inteiro dentro de um teste aquece o cache de `Settings` sem as variáveis
    de segurança que outros testes definem por monkeypatch — e 25 provas de outras
    frentes passaram a receber 503 "Autenticação indisponível". O teste não tinha
    defeito; a fixture tinha, e o dano caiu em quem não mexeu em nada.

    Um app próprio com um router só é o escopo que este teste precisa.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CRIATIVO_BANCADA_DIR", str(tmp_path / "bancada"))
    import app.criativo.bancada.servico as servico

    monkeypatch.setattr(servico, "_BANCADA", None, raising=False)

    from app.routers.criativos_execucao import router
    from app.seguranca.identidade import exigir_usuario

    class _Eu:
        sub, role, email = "usuario-de-teste", "ADMIN", "t@volc"

    local = FastAPI()
    local.include_router(router)
    local.dependency_overrides[exigir_usuario] = lambda: _Eu()
    try:
        yield TestClient(local)
    finally:
        monkeypatch.setattr(servico, "_BANCADA", None, raising=False)


def _pedido(seed: int = 7, titulo: str = "Inscrições abertas 2027") -> dict[str, Any]:
    return {
        "receitaId": "receita-1",
        "motorSlug": "tipografico-local",
        "modoSlug": "typography_only",
        "finalidadeSlug": "google_display",
        "seed": seed,
        "slots": ["1x1", "4x5"],
        "titulo": titulo,
        "apoio": "matrículas até 30 de setembro",
    }


def test_a_maquina_declara_quais_motores_consegue_rodar(cliente):
    r = cliente.get("/api/criativos/bancada/motores")
    assert r.status_code == 200
    slugs = [m["slug"] for m in r.json()["motores"]]
    assert "tipografico-local" in slugs
    versoes = r.json()["motores"][0]["versoes"]
    assert len(versoes["fonte_sha256"]) == 64


def test_fatia_vertical_produz_artefato_real_e_recibo(cliente):
    """Compilar -> despachar -> produzir -> validar -> recibo -> ler o arquivo."""
    criado = cliente.post("/api/criativos/bancada/trabalhos", json=_pedido())
    assert criado.status_code == 201
    t = criado.json()
    assert t["estado"] == "rendered"

    recibo = t["recibo"]
    assert recibo is not None, "não se conclui trabalho sem recibo"
    assert len(recibo["artefatos"]) == 2
    assert {a["slot"] for a in recibo["artefatos"]} == {"1x1", "4x5"}
    assert all(a["bytes"] > 1000 for a in recibo["artefatos"])
    assert all(len(a["sha256"]) == 64 for a in recibo["artefatos"])
    assert recibo["seed"] == 7
    assert recibo["versoes"]["pillow"]
    assert recibo["assinaturaDeterminista"]

    contraste = [v for v in recibo["validacoes"] if v["gate"] == "contraste"][0]
    assert contraste["resultado"] == "PASS"
    assert contraste["detalhe"]["razao"] >= 4.5

    lido = cliente.get(f"/api/criativos/bancada/trabalhos/{t['id']}")
    assert lido.status_code == 200
    assert lido.json()["estado"] == "rendered"

    arquivo = cliente.get(f"/api/criativos/bancada/arquivo/{t['id']}/1x1")
    assert arquivo.status_code == 200
    assert arquivo.headers["content-type"] == "image/png"
    assert arquivo.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(arquivo.content) > 1000


def test_o_mesmo_pedido_pelo_http_nao_produz_de_novo(cliente):
    primeiro = cliente.post("/api/criativos/bancada/trabalhos", json=_pedido())
    segundo = cliente.post("/api/criativos/bancada/trabalhos", json=_pedido())
    assert primeiro.status_code == 201
    assert segundo.status_code == 200
    assert segundo.headers.get("X-Criativo-Idempotente") == "replay"
    assert primeiro.json()["id"] == segundo.json()["id"]


def test_listar_e_cancelar_percorrem_o_deposito_real_pelo_http(cliente):
    """O contrato extraído não pode ficar provado só por dublê de apresentação."""

    from app.criativo.bancada import servico

    deposito, _operario, _despachante = servico.montar()
    enfileirado, criado = deposito.enfileirar(
        encomenda(seed=71, tenant_id="usuario-de-teste")
    )
    assert criado is True

    listagem = cliente.get("/api/criativos/bancada/trabalhos?limite=1")
    assert listagem.status_code == 200
    assert [item["id"] for item in listagem.json()["trabalhos"]] == [enfileirado.id]
    assert listagem.json()["trabalhos"][0]["estado"] == "queued"
    assert listagem.json()["trabalhos"][0]["podeCancelar"] is True

    cancelamento = cliente.post(
        f"/api/criativos/bancada/trabalhos/{enfileirado.id}/cancelar",
        json={"motivo": "briefing substituído"},
    )
    assert cancelamento.status_code == 200
    cancelado = cancelamento.json()
    assert cancelado["id"] == enfileirado.id
    assert cancelado["estado"] == "cancelled"
    assert cancelado["canceladoPor"] == "usuario-de-teste"
    assert cancelado["canceladoMotivo"] == "briefing substituído"
    assert cancelado["podeCancelar"] is False
    assert cancelado["podeRetomar"] is True

    depois = cliente.get("/api/criativos/bancada/trabalhos?limite=1")
    assert depois.status_code == 200
    assert depois.json()["trabalhos"][0]["estado"] == "cancelled"


def test_retomar_e_linhagem_pelo_http_provam_201_replay_200_e_header(cliente):
    """Falha real local, retomada nova e segundo clique convergem no mesmo job."""

    pedido_falho = {**_pedido(seed=72), "motorSlug": "motor-ausente"}
    original = cliente.post(
        "/api/criativos/bancada/trabalhos", json=pedido_falho
    )
    assert original.status_code == 201
    assert original.headers.get("X-Criativo-Idempotente") is None
    original_json = original.json()
    assert original_json["estado"] == "failed"

    path = (
        f"/api/criativos/bancada/trabalhos/{original_json['id']}/retomar"
    )
    primeira = cliente.post(path)
    assert primeira.status_code == 201
    assert primeira.headers.get("X-Criativo-Idempotente") is None
    retomado = primeira.json()
    assert retomado["id"] != original_json["id"]
    assert retomado["estado"] == "failed"
    assert retomado["retomaDe"] == original_json["id"]
    assert retomado["retomadaN"] == 1

    replay = cliente.post(path)
    assert replay.status_code == 200
    assert replay.headers.get("X-Criativo-Idempotente") == "replay"
    assert replay.json() == retomado

    linhagem = cliente.get(
        f"/api/criativos/bancada/trabalhos/{retomado['id']}/linhagem"
    )
    assert linhagem.status_code == 200
    cadeia = linhagem.json()["linhagem"]
    assert [item["id"] for item in cadeia] == [
        original_json["id"],
        retomado["id"],
    ]
    assert [item["retomadaN"] for item in cadeia] == [0, 1]
    assert cadeia[0]["retomaDe"] is None
    assert cadeia[1]["retomaDe"] == cadeia[0]["id"]


def test_determinismo_pelo_http_dois_pedidos_iguais_mesma_assinatura(cliente):
    a = cliente.post("/api/criativos/bancada/trabalhos", json=_pedido(seed=31)).json()
    b = cliente.post("/api/criativos/bancada/trabalhos", json=_pedido(seed=32)).json()
    assert a["recibo"]["assinaturaDeterminista"] != b["recibo"]["assinaturaDeterminista"]
    # mesma semente, mesmo conteúdo -> mesmos hashes de artefato
    ha = {x["slot"]: x["sha256"] for x in a["recibo"]["artefatos"]}
    c = cliente.post(
        "/api/criativos/bancada/trabalhos",
        json={**_pedido(seed=31), "receitaId": "receita-2"},
    ).json()
    hc = {x["slot"]: x["sha256"] for x in c["recibo"]["artefatos"]}
    assert ha == hc, "mesma semente e mesmo conteúdo produziram pixels diferentes"


def test_slot_que_o_executor_nao_conhece_e_recusado_antes_de_produzir(cliente):
    r = cliente.post(
        "/api/criativos/bancada/trabalhos",
        json={**_pedido(), "slots": ["16x9"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["codigo"] == "ESTUDIO.formato_invalido"


def test_pedido_sem_semente_e_recusado(cliente):
    corpo = _pedido()
    del corpo["seed"]
    assert cliente.post("/api/criativos/bancada/trabalhos", json=corpo).status_code == 422


def test_arquivo_de_trabalho_inexistente_e_404_e_nao_vazamento(cliente):
    r = cliente.get("/api/criativos/bancada/arquivo/nao-existe/1x1")
    assert r.status_code == 404
    corpo = r.text.lower()
    for vazamento in ("/users/", "traceback", "sqlite", "criativo_"):
        assert vazamento not in corpo


def test_motor_que_esta_maquina_nao_roda_falha_com_motivo_legivel(cliente):
    r = cliente.post(
        "/api/criativos/bancada/trabalhos",
        json={**_pedido(), "motorSlug": "gemini-imagem"},
    )
    assert r.status_code == 201
    t = r.json()
    assert t["estado"] == "failed"
    assert t["falha"]["codigo"] == "motor_desconhecido"
    assert t["recibo"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 10. Achados da auditoria adversarial de 28/08/2026, noite
# ═══════════════════════════════════════════════════════════════════════════


class MotorMentiroso:
    """Declara um artefato que não escreveu. Existe para provar que o executor
    não acredita no motor."""

    slug, versao = "mentiroso", "1"

    def versoes_congeladas(self) -> dict[str, str]:
        return {"adaptador": "1"}

    def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
        return (
            Artefato("1x1", str(Path(d) / "nunca-escrito.png"), "image/png",
                     4096, "f" * 64, 1080, 1080),
        )


class MotorQueMenteOHash:
    slug, versao = "hash-torto", "1"

    def versoes_congeladas(self) -> dict[str, str]:
        return {"adaptador": "1"}

    def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
        p = Path(d) / "x.png"
        dados = b"\x89PNG\r\n\x1a\n" + b"z" * 200
        p.write_bytes(dados)
        return (Artefato("1x1", str(p), "image/png", len(dados), "f" * 64, 1080, 1080),)


def test_motor_que_declara_arquivo_inexistente_nao_chega_a_rendered(bancada, tmp_path):
    """O executor decidia tudo em cima do que o MOTOR DECLAROU: `bytes_` e
    `sha256` eram valores que o motor escreveu, nunca conferidos contra o disco.
    Um motor mentiroso chegava a `rendered`, com recibo, e a assinatura
    determinista virava o hash de uma ficção."""
    deposito, _ = bancada
    op = Operario(deposito, {"mentiroso": MotorMentiroso()}, tmp_path / "m")
    deposito.enfileirar(encomenda(motor_slug="mentiroso"))
    feito = op.trabalhar_uma_vez()
    assert feito.estado is EstadoDoTrabalho.FAILED
    assert feito.recibo is None


def test_hash_declarado_diferente_do_arquivo_reprova(bancada, tmp_path):
    deposito, _ = bancada
    op = Operario(deposito, {"hash-torto": MotorQueMenteOHash()}, tmp_path / "h")
    deposito.enfileirar(encomenda(motor_slug="hash-torto"))
    feito = op.trabalhar_uma_vez()
    assert feito.estado is EstadoDoTrabalho.FAILED


def test_o_recibo_carrega_o_hash_MEDIDO_do_arquivo(bancada):
    import hashlib

    deposito, operario = bancada
    deposito.enfileirar(encomenda())
    r = operario.trabalhar_uma_vez().recibo
    for a in r["artefatos"]:
        real = hashlib.sha256(Path(a["caminho"]).read_bytes()).hexdigest()
        assert a["sha256"] == real
    conferencia = [v for v in r["validacoes"] if v["gate"] == "hash_confere"]
    assert conferencia and all(v["resultado"] == "PASS" for v in conferencia)


def test_despachar_produz_O_TRABALHO_PEDIDO_e_nao_o_mais_antigo(bancada, tmp_path):
    """`despachar` buscava o id só para levantar KeyError e depois chamava
    `reivindicar()`, que devolve o MAIS ANTIGO da fila. O operador pedia a peça A,
    recebia 201 dizendo `queued` sem recibo, e a máquina produzia a peça B."""
    from app.criativo.bancada.operario import DespachanteLocal

    deposito, operario = bancada
    antigo, _ = deposito.enfileirar(encomenda(seed=1, titulo="PEÇA ANTIGA"))
    novo, _ = deposito.enfileirar(encomenda(seed=2, titulo="PEÇA NOVA"))

    DespachanteLocal(operario).despachar(novo.id)

    assert deposito.por_id(novo.id).estado is EstadoDoTrabalho.RENDERED
    assert deposito.por_id(antigo.id).estado is EstadoDoTrabalho.QUEUED
    produzido = deposito.por_id(novo.id).recibo["parametros"]["titulo"]
    assert produzido == "PEÇA NOVA"


def test_quem_perdeu_o_lease_nao_grava_recibo_por_cima(bancada):
    """O operário que perdeu o trabalho gravava o recibo por cima do de quem o
    pegou, e o arquivo apontado pelo recibo não existia mais."""
    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    a = deposito.reivindicar("op-A", lease_s=-1)
    deposito.devolver_vencidos()
    b = deposito.reivindicar("op-B")
    assert a.id == b.id

    deposito.transicionar(b.id, EstadoDoTrabalho.RUNNING, exigir_operario="op-B")
    deposito.transicionar(b.id, EstadoDoTrabalho.VALIDATING, exigir_operario="op-B")
    with pytest.raises(TransicaoProibida):
        deposito.transicionar(
            b.id, EstadoDoTrabalho.RENDERED, recibo={"x": 1}, exigir_operario="op-A"
        )


def test_quem_nao_e_dono_nao_bate_o_coracao(bancada):
    """O UPDATE não filtrava por `operario`: um operário que já tinha perdido o
    trabalho continuava batendo, `vivo` dizia True, e o trabalho nunca voltava
    para a fila quando o dono real morria."""
    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    deposito.reivindicar("op-A", lease_s=-1)
    deposito.devolver_vencidos()
    b = deposito.reivindicar("op-B")
    assert deposito.bater(b.id, operario="op-A") is False
    assert deposito.bater(b.id, operario="op-B") is True


def test_trabalho_que_volta_para_a_fila_solta_o_lease_e_guarda_o_motivo(bancada):
    """`transicionar` nunca limpava `operario` nem `lease_ate`: um trabalho
    `queued` ficava com lease no futuro e `vivo` dizia True para algo que ninguém
    estava fazendo. E o motivo da tentativa 1 era apagado antes da tentativa 2."""
    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op")
    deposito.transicionar(
        t.id, EstadoDoTrabalho.QUEUED,
        falha={"codigo": "transitoria", "mensagem": "cai e volta", "permanente": False},
        exigir_operario="op",
    )
    de_novo = deposito.por_id(t.id)
    assert de_novo.estado is EstadoDoTrabalho.QUEUED
    assert de_novo.operario is None
    assert de_novo.lease_ate is None
    assert de_novo.vivo is False
    assert de_novo.falha["codigo"] == "transitoria"


def test_trabalho_terminal_solta_o_lease(bancada):
    deposito, operario = bancada
    deposito.enfileirar(encomenda())
    feito = operario.trabalhar_uma_vez()
    assert feito.estado is EstadoDoTrabalho.RENDERED
    assert feito.vivo is False, "trabalho pronto não pode continuar 'vivo'"
    assert feito.operario is None
    assert feito.recibo["produzido_por"]


def test_fila_com_muitos_esgotados_nao_estoura_a_pilha(tmp_path):
    """Esgotar a tentativa marcava FAILED e chamava `reivindicar` por RECURSÃO.
    Com mil esgotados na frente, a fila estourava RecursionError, o erro real era
    substituído pelo do rollback, e todo POST virava 500 até apagar o banco."""
    deposito = DepositoDeTrabalhos(tmp_path / "f.db")
    for i in range(1200):
        deposito.enfileirar(encomenda(seed=i), max_tentativas=0)
    deposito.enfileirar(encomenda(seed=999999, titulo="a boa"))

    pego = deposito.reivindicar("op")
    assert pego is not None, "o trabalho sadio ficou preso atrás dos esgotados"
    assert pego.encomenda.parametros["titulo"] == "a boa"


def test_a_assinatura_muda_quando_o_insumo_muda(bancada, tmp_path):
    """`test_o_recibo_congela_a_versao_da_fonte` provava que o sha256 da fonte
    ESTÁ no recibo, não que a assinatura MUDA quando a fonte muda — e essa é a
    metade que serve para alguma coisa."""
    from app.criativo.bancada.contrato import Recibo

    def recibo_com(versoes: dict[str, str]) -> Recibo:
        return Recibo(
            trabalho_id="t", chave_de_idempotencia="k", produzido_por="op",
            motor_slug="m", motor_versao="1", seed=7, versoes=versoes,
            parametros={"titulo": "x"}, artefatos=(), validacoes=(), audio=None,
            iniciado_em="a", terminado_em="b", custo_estimado_usd=None,
            custo_real_usd=None,
        )

    a = recibo_com({"fonte_sha256": "a" * 64}).assinatura_determinista()
    b = recibo_com({"fonte_sha256": "b" * 64}).assinatura_determinista()
    assert a != b, "trocar a fonte não mudou a assinatura"


def test_a_mensagem_de_falha_nao_leva_caminho_de_disco_para_a_tela(bancada, tmp_path):
    """`str(e)` cru ia direto para a tela e trazia caminho junto:
    "[Errno 28] No space left on device: '/var/folders/.../1x1.png'"."""

    class MotorQueVazaCaminho:
        slug, versao = "vaza", "1"

        def versoes_congeladas(self) -> dict[str, str]:
            return {}

        def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
            raise FalhaDoMotor(
                f"[Errno 28] No space left on device: '{d}/1x1.png'", permanente=True
            )

    deposito, _ = bancada
    op = Operario(deposito, {"vaza": MotorQueVazaCaminho()}, tmp_path / "v")
    deposito.enfileirar(encomenda(motor_slug="vaza"))
    feito = op.trabalhar_uma_vez()
    assert feito.estado is EstadoDoTrabalho.FAILED
    mensagem = feito.falha["mensagem"]
    assert "/var/" not in mensagem and "/private/" not in mensagem
    assert str(tmp_path) not in mensagem
    assert "<caminho>" in mensagem


# ═══════════════════════════════════════════════════════════════════════════
# 11. Retomada, cancelamento, reaper, tenant e canonicalização
# ═══════════════════════════════════════════════════════════════════════════


def test_trabalho_que_falhou_pode_ser_retomado_e_gera_trabalho_novo(bancada):
    """A chave é `unique`, então um `failed` ficava terminal PARA SEMPRE:
    reenviar o mesmo pedido devolvia o mesmo trabalho morto. Cenário real: a
    máquina sobe sem fontes, tudo vira `motor_desconhecido`, o operador conserta,
    reinicia, clica de novo — e recebe o mesmo `failed`, indefinidamente."""
    deposito, operario = bancada
    deposito.enfileirar(encomenda(motor_slug="motor-ausente"))
    falho = operario.trabalhar_uma_vez()
    assert falho.estado is EstadoDoTrabalho.FAILED

    novo, criado = deposito.retomar(falho.id, tenant_id="tenant-A")
    assert criado is True
    assert novo.id != falho.id, "retomar não pode reabrir o trabalho terminal"
    assert novo.retoma_de == falho.id
    assert novo.retomada_n == 1
    assert novo.estado is EstadoDoTrabalho.QUEUED
    # o motivo original continua guardado
    assert deposito.por_id(falho.id).falha["codigo"] == "motor_desconhecido"


def test_falha_transitoria_ambiente_corrigido_retomada_produz(bancada, tmp_path):
    """A prova que a missão pediu: falha → conserto → retomada → rendered."""
    deposito, _ = bancada
    quebrado = Operario(deposito, {}, tmp_path / "sem-motor", nome="op-1")
    deposito.enfileirar(encomenda())
    falho = quebrado.trabalhar_uma_vez()
    assert falho.estado is EstadoDoTrabalho.FAILED

    # ambiente corrigido: o motor passa a existir
    consertado = Operario(
        deposito, {"tipografico-local": MotorTipografico()}, tmp_path / "com-motor",
        nome="op-2",
    )
    novo, _ = deposito.retomar(falho.id, tenant_id="tenant-A")
    feito = consertado.trabalhar_uma_vez()
    assert feito.id == novo.id
    assert feito.estado is EstadoDoTrabalho.RENDERED
    assert feito.recibo["artefatos"]


def test_dois_cliques_na_mesma_retomada_convergem(bancada):
    deposito, operario = bancada
    deposito.enfileirar(encomenda(motor_slug="motor-ausente"))
    falho = operario.trabalhar_uma_vez()
    a, criado_a = deposito.retomar(falho.id, tenant_id="tenant-A")
    b, criado_b = deposito.retomar(falho.id, tenant_id="tenant-A")
    assert criado_a is True and criado_b is False
    assert a.id == b.id, "a idempotência tem de impedir duplicação acidental"


def test_nao_se_retoma_trabalho_que_deu_certo(bancada):
    """Retomar o que deu certo produziria a MESMA peça, pagando de novo."""
    deposito, operario = bancada
    deposito.enfileirar(encomenda())
    pronto = operario.trabalhar_uma_vez()
    with pytest.raises(TransicaoProibida):
        deposito.retomar(pronto.id, tenant_id="tenant-A")


def test_a_linhagem_liga_a_retomada_ao_original(bancada):
    deposito, operario = bancada
    deposito.enfileirar(encomenda(motor_slug="motor-ausente"))
    falho = operario.trabalhar_uma_vez()
    n1, _ = deposito.retomar(falho.id, tenant_id="tenant-A")
    operario.trabalhar_uma_vez()
    n2, _ = deposito.retomar(n1.id, tenant_id="tenant-A")

    cadeia = deposito.linhagem(n2.id, tenant_id="tenant-A")
    assert [t.id for t in cadeia] == [falho.id, n1.id, n2.id]
    assert [t.retomada_n for t in cadeia] == [0, 1, 2]


# ── cancelamento ────────────────────────────────────────────────────────────


def test_cancelar_tem_produtor_real_e_exige_motivo(bancada):
    """`cancelled` existia no contrato e ninguém o produzia: sete estados, seis
    com função."""
    deposito, _ = bancada
    t, _ = deposito.enfileirar(encomenda())
    with pytest.raises(ValueError, match="sem motivo"):
        deposito.cancelar(t.id, tenant_id="tenant-A", por="u", motivo="  ")

    cancelado = deposito.cancelar(
        t.id, tenant_id="tenant-A", por="usuario-1", motivo="pedido errado"
    )
    assert cancelado.estado is EstadoDoTrabalho.CANCELLED
    assert cancelado.cancelado_por == "usuario-1"
    assert cancelado.cancelado_motivo == "pedido errado"
    assert cancelado.operario is None and cancelado.lease_ate is None


def test_trabalho_cancelado_sai_da_fila(bancada):
    deposito, operario = bancada
    t, _ = deposito.enfileirar(encomenda())
    deposito.cancelar(t.id, tenant_id="tenant-A", por="u", motivo="parar")
    assert operario.trabalhar_uma_vez() is None


def test_nao_se_cancela_o_que_ja_terminou(bancada):
    deposito, operario = bancada
    deposito.enfileirar(encomenda())
    pronto = operario.trabalhar_uma_vez()
    with pytest.raises(TransicaoProibida):
        deposito.cancelar(pronto.id, tenant_id="tenant-A", por="u", motivo="tarde")


def test_operario_cancelado_no_meio_nao_conclui(bancada, tmp_path):
    """O trabalho pode ser cancelado enquanto o motor produz. Concluir depois
    ressuscitaria algo que alguém mandou parar."""
    import threading

    deposito, _ = bancada
    pronto_para_cancelar = threading.Event()
    pode_terminar = threading.Event()

    class MotorLento:
        slug, versao = "lento", "1"

        def versoes_congeladas(self) -> dict[str, str]:
            return {"adaptador": "1"}

        def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
            import hashlib

            pronto_para_cancelar.set()
            pode_terminar.wait(timeout=5)
            p = Path(d) / "x.png"
            dados = b"\x89PNG\r\n\x1a\n" + b"q" * 128
            p.write_bytes(dados)
            return (Artefato("1x1", str(p), "image/png", len(dados),
                             hashlib.sha256(dados).hexdigest(), 1080, 1080),)

    op = Operario(deposito, {"lento": MotorLento()}, tmp_path / "lento")
    t, _ = deposito.enfileirar(encomenda(motor_slug="lento"))
    resultado: list[Any] = []
    fio = threading.Thread(target=lambda: resultado.append(op.trabalhar_uma_vez()))
    fio.start()
    assert pronto_para_cancelar.wait(timeout=5)
    deposito.cancelar(t.id, tenant_id="tenant-A", por="u", motivo="mudei de ideia")
    pode_terminar.set()
    fio.join(timeout=10)

    final = deposito.por_id(t.id)
    assert final.estado is EstadoDoTrabalho.CANCELLED
    assert final.recibo is None, "um trabalho cancelado não pode ganhar recibo"


# ── reaper ──────────────────────────────────────────────────────────────────


def test_o_reaper_devolve_leases_vencidos_sem_esperar_um_POST(bancada):
    """`devolver_vencidos` só rodava dentro de `reivindicar`, e `reivindicar` só
    rodava quando OUTRO pedido chegava. Um trabalho abandonado ficava preso até
    alguém, por acaso, mandar outro pedido."""
    import time

    from app.criativo.bancada.operario import Reaper

    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    pego = deposito.reivindicar("op-que-morre", lease_s=-1)
    assert pego.estado is EstadoDoTrabalho.CLAIMED

    with Reaper(deposito, intervalo_s=0.05) as reaper:
        prazo = time.monotonic() + 5
        while time.monotonic() < prazo:
            if deposito.por_id(pego.id).estado is EstadoDoTrabalho.QUEUED:
                break
            time.sleep(0.05)
    assert deposito.por_id(pego.id).estado is EstadoDoTrabalho.QUEUED
    assert reaper.devolvidos >= 1
    assert reaper.vivo is False, "parar() tem de encerrar a thread"


def test_o_reaper_para_com_seguranca_e_e_idempotente():
    from app.criativo.bancada.operario import Reaper

    class DepositoInerte:
        def devolver_vencidos(self) -> int:
            return 0

    r = Reaper(DepositoInerte(), intervalo_s=0.05)
    r.iniciar()
    r.iniciar()
    assert r.vivo is True
    r.parar()
    r.parar()
    assert r.vivo is False
    # ⚠️ `vivo` precisa refletir a THREAD, não a variável. `parar()` zerava `_t`
    # mesmo quando o join expirava, então uma thread vazando sumia da vista.
    import threading

    assert not any(
        t.name == "bancada-reaper" and t.is_alive() for t in threading.enumerate()
    ), "a thread do reaper continuou viva depois de parar()"


# ── tenant ──────────────────────────────────────────────────────────────────


def test_tenants_diferentes_com_o_mesmo_pedido_nao_compartilham_trabalho(bancada):
    deposito, _ = bancada
    a, criado_a = deposito.enfileirar(encomenda(tenant_id="tenant-A"))
    b, criado_b = deposito.enfileirar(encomenda(tenant_id="tenant-B"))
    assert criado_a and criado_b
    assert a.id != b.id
    assert a.chave_idempotencia != b.chave_idempotencia


def test_leitura_por_id_com_tenant_nao_devolve_trabalho_alheio(bancada):
    deposito, _ = bancada
    a, _ = deposito.enfileirar(encomenda(tenant_id="tenant-A"))
    assert deposito.por_id(a.id, tenant_id="tenant-A") is not None
    assert deposito.por_id(a.id, tenant_id="tenant-B") is None


def test_listar_so_traz_o_do_proprio_tenant(bancada):
    deposito, _ = bancada
    deposito.enfileirar(encomenda(tenant_id="tenant-A", seed=1))
    deposito.enfileirar(encomenda(tenant_id="tenant-A", seed=2))
    deposito.enfileirar(encomenda(tenant_id="tenant-B", seed=3))
    assert len(deposito.listar(tenant_id="tenant-A")) == 2
    assert len(deposito.listar(tenant_id="tenant-B")) == 1


def test_nao_se_retoma_nem_cancela_trabalho_de_outro_tenant(bancada, operario_falho=None):
    deposito, operario = bancada
    deposito.enfileirar(encomenda(tenant_id="tenant-A", motor_slug="ausente"))
    falho = operario.trabalhar_uma_vez()
    with pytest.raises(KeyError):
        deposito.retomar(falho.id, tenant_id="tenant-B")
    t, _ = deposito.enfileirar(encomenda(tenant_id="tenant-A", seed=99))
    with pytest.raises(KeyError):
        deposito.cancelar(t.id, tenant_id="tenant-B", por="x", motivo="invasao")


# ── canonicalização ─────────────────────────────────────────────────────────


def test_um_inteiro_e_um_float_inteiro_sao_o_mesmo_pedido():
    """`json.dumps` serializa `1` e `1.0` diferente: dois pedidos semanticamente
    iguais viravam duas chaves e, com motor pago, dois gastos."""
    a = encomenda(escala=1)
    b = encomenda(escala=1.0)
    assert a.chave_de_idempotencia() == b.chave_de_idempotencia()


def test_um_float_de_verdade_continua_distinto():
    assert (
        encomenda(escala=1).chave_de_idempotencia()
        != encomenda(escala=1.5).chave_de_idempotencia()
    )


def test_booleano_nao_vira_inteiro_na_chave():
    """`True` é subclasse de `int` em Python, e `canonizar` precisa preservá-lo.

    ⚠️ A primeira versão deste teste comparava dicionários: `{"x": True} != {"x": 1}`
    é **False** em Python, porque `True == 1`. A asserção passava por acidente e
    não teria pegado o colapso. O que decide a identidade é a chave serializada,
    e é nela que a distinção precisa sobreviver.
    """
    from app.criativo.bancada.contrato import canonizar

    assert type(canonizar({"x": True})["x"]) is bool
    assert (
        encomenda(sinalizador=True).chave_de_idempotencia()
        != encomenda(sinalizador=1).chave_de_idempotencia()
    )


def test_ausencia_nao_colapsa_com_vazio_na_canonicalizacao():
    from app.criativo.bancada.contrato import canonizar

    assert canonizar({"apoio": None}) == {"apoio": None}
    assert canonizar({"apoio": None}) != canonizar({"apoio": ""})


def test_ordem_de_lista_e_significativa_e_nao_e_ordenada():
    from app.criativo.bancada.contrato import canonizar

    assert canonizar([3, 1, 2]) == [3, 1, 2]


# ── fonte empacotada ────────────────────────────────────────────────────────


def test_a_fonte_vem_do_pacote_e_nao_de_caminho_de_maquina():
    """`fonte_sha256` entra na assinatura determinista: fonte resolvida por
    caminho de máquina faz o mesmo pedido dar assinaturas diferentes."""
    from app.criativo.bancada.adaptadores.tipografico import (
        FONTES_EMPACOTADAS,
        MotorTipografico,
    )

    m = MotorTipografico()
    v = m.versoes_congeladas()
    assert FONTES_EMPACOTADAS.is_dir()
    assert (FONTES_EMPACOTADAS / v["fonte_arquivo"]).is_file()
    assert len(v["fonte_sha256"]) == 64


def test_nao_ha_caminho_de_maquina_vivo_no_modulo_do_motor():
    """A docstring antiga dizia "não há caminho absoluto embutido" e a primeira
    pista era `/Users/mac/...`. Este teste varre a ÁRVORE: prosa pode citar o
    defeito histórico; literal vivo, não."""
    import ast

    caminho = (
        Path(__file__).resolve().parents[1]
        / "app/criativo/bancada/adaptadores/tipografico.py"
    )
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    docstrings = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            if (d := ast.get_docstring(no, clean=False)) is not None:
                docstrings.add(d)
    vivos = [
        n.value
        for n in ast.walk(arvore)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and n.value not in docstrings
        and ("/Users/" in n.value or "/home/" in n.value)
    ]
    assert vivos == [], f"caminho de máquina vivo no código: {vivos}"


def test_o_motor_falha_com_motivo_quando_nao_ha_fonte(monkeypatch, tmp_path):
    """Sem fonte, FALHA. Não existe fallback para a bitmap do PIL nem para uma
    Helvetica do sistema achada por acaso: as duas mudariam o pixel sem mudar
    nada do pedido, e o recibo diria "mesmas versões"."""
    import app.criativo.bancada.adaptadores.tipografico as tip

    monkeypatch.setattr(tip, "FONTES_EMPACOTADAS", tmp_path / "vazio")
    monkeypatch.setenv("CRIATIVO_FONTES_DIR", str(tmp_path / "tambem-vazio"))
    with pytest.raises(FalhaDoMotor) as erro:
        tip.MotorTipografico()
    assert erro.value.permanente is True


# ═══════════════════════════════════════════════════════════════════════════
# 12. Provas nascidas do score de mutação (as seis que sobreviveram)
# ═══════════════════════════════════════════════════════════════════════════


def test_bytes_declarados_diferentes_do_arquivo_reprovam(bancada, tmp_path):
    """Sobrevivente do score: nenhuma prova exercia o gate `bytes_conferem`
    sozinho, porque hash errado já derrubava antes."""
    import hashlib

    class MotorQueMenteOTamanho:
        slug, versao = "tamanho-torto", "1"

        def versoes_congeladas(self) -> dict[str, str]:
            return {"adaptador": "1"}

        def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
            p = Path(d) / "x.png"
            dados = b"\x89PNG\r\n\x1a\n" + b"k" * 300
            p.write_bytes(dados)
            # hash CERTO, tamanho ERRADO: só o gate de bytes pode pegar.
            return (Artefato("1x1", str(p), "image/png", 999999,
                             hashlib.sha256(dados).hexdigest(), 1080, 1080),)

    deposito, _ = bancada
    op = Operario(deposito, {"tamanho-torto": MotorQueMenteOTamanho()}, tmp_path / "tt")
    deposito.enfileirar(encomenda(motor_slug="tamanho-torto"))
    feito = op.trabalhar_uma_vez()
    assert feito.estado is EstadoDoTrabalho.FAILED
    assert "bytes_conferem" in (feito.falha["mensagem"] or "")


def test_o_OPERARIO_que_perdeu_o_lease_nao_conclui(bancada, tmp_path):
    """Sobrevivente do score: a prova anterior exercia o DEPÓSITO diretamente. A
    passagem pelo operário — que é onde o defeito morava — não era coberta."""
    import threading

    comecou = threading.Event()
    pode_seguir = threading.Event()

    class MotorLentissimo:
        slug, versao = "lentissimo", "1"

        def versoes_congeladas(self) -> dict[str, str]:
            return {"adaptador": "1"}

        def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
            import hashlib

            comecou.set()
            pode_seguir.wait(timeout=5)
            p = Path(d) / "x.png"
            dados = b"\x89PNG\r\n\x1a\n" + b"w" * 128
            p.write_bytes(dados)
            return (Artefato("1x1", str(p), "image/png", len(dados),
                             hashlib.sha256(dados).hexdigest(), 1080, 1080),)

    deposito, _ = bancada
    op_a = Operario(deposito, {"lentissimo": MotorLentissimo()}, tmp_path / "la",
                    nome="op-A", lease_s=-1)
    t, _ = deposito.enfileirar(encomenda(motor_slug="lentissimo"))

    resultado: list[Any] = []
    fio = threading.Thread(target=lambda: resultado.append(op_a.trabalhar_uma_vez()))
    fio.start()
    assert comecou.wait(timeout=5)

    # o lease de A já nasceu vencido: B reivindica o mesmo trabalho
    deposito.devolver_vencidos()
    b = deposito.reivindicar("op-B")
    assert b is not None and b.id == t.id

    pode_seguir.set()
    fio.join(timeout=10)

    final = deposito.por_id(t.id)
    assert final.operario == "op-B", "B é o dono"
    assert final.recibo is None, "A concluiu por cima do trabalho de B"
    assert final.estado is not EstadoDoTrabalho.RENDERED


def test_trabalho_cancelado_tem_o_diretorio_limpo(bancada, tmp_path):
    """Sobrevivente do score: a prova de cancelamento no meio só olhava o estado,
    e o estado já era garantido pela tabela de transições. O que a guarda do
    operário faz de fato é limpar o diretório e não gravar recibo."""
    import threading

    comecou = threading.Event()
    pode_seguir = threading.Event()
    caminho_visto: list[Path] = []

    class MotorObservavel:
        slug, versao = "observavel", "1"

        def versoes_congeladas(self) -> dict[str, str]:
            return {"adaptador": "1"}

        def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
            import hashlib

            caminho_visto.append(Path(d))
            comecou.set()
            pode_seguir.wait(timeout=5)
            p = Path(d) / "x.png"
            dados = b"\x89PNG\r\n\x1a\n" + b"c" * 128
            p.write_bytes(dados)
            return (Artefato("1x1", str(p), "image/png", len(dados),
                             hashlib.sha256(dados).hexdigest(), 1080, 1080),)

    deposito, _ = bancada
    op = Operario(deposito, {"observavel": MotorObservavel()}, tmp_path / "obs")
    t, _ = deposito.enfileirar(encomenda(motor_slug="observavel"))
    fio = threading.Thread(target=op.trabalhar_uma_vez)
    fio.start()
    assert comecou.wait(timeout=5)
    deposito.cancelar(t.id, tenant_id="tenant-A", por="u", motivo="parar agora")
    pode_seguir.set()
    fio.join(timeout=10)

    assert deposito.por_id(t.id).estado is EstadoDoTrabalho.CANCELLED
    assert deposito.por_id(t.id).recibo is None
    assert caminho_visto and not caminho_visto[0].exists(), (
        "o diretório do trabalho cancelado ficou no disco"
    )


def test_sem_fonte_empacotada_e_sem_env_o_motor_falha_e_nao_cai_no_sistema(
    monkeypatch, tmp_path
):
    """Sobrevivente do score: a prova anterior apontava `CRIATIVO_FONTES_DIR` para
    um diretório inexistente, e a falha acontecia ANTES do ponto onde um fallback
    de sistema entraria. Agora a variável fica ausente, que é o caminho real."""
    import app.criativo.bancada.adaptadores.tipografico as tip

    monkeypatch.setattr(tip, "FONTES_EMPACOTADAS", tmp_path / "sem-nada")
    monkeypatch.delenv("CRIATIVO_FONTES_DIR", raising=False)
    with pytest.raises(FalhaDoMotor) as erro:
        tip.MotorTipografico()
    assert erro.value.permanente is True
    assert "empacotada" in str(erro.value)


def test_cancelar_o_que_ja_terminou_e_barrado_pelo_proprio_UPDATE(bancada):
    """Sobrevivente do score: a guarda em Python é redundante com o `where` do
    UPDATE. Esta prova exercita o árbitro real, contornando a guarda de cima."""
    deposito, operario = bancada
    deposito.enfileirar(encomenda())
    pronto = operario.trabalhar_uma_vez()
    assert pronto.estado is EstadoDoTrabalho.RENDERED

    # ⚠️ A primeira versão desta prova COPIAVA o UPDATE para dentro do teste. Um
    # teste que reescreve a consulta não exercita a consulta: mutar o código de
    # produção não mudava nada aqui. Agora a guarda de cima é neutralizada e o
    # caminho real é percorrido, para o `where` do UPDATE ser o único árbitro.
    import app.criativo.bancada.deposito as dep

    original = dep.TERMINAIS
    dep.TERMINAIS = frozenset()
    try:
        with pytest.raises(TransicaoProibida):
            deposito.cancelar(pronto.id, tenant_id="tenant-A", por="u", motivo="tarde")
    finally:
        dep.TERMINAIS = original
    assert deposito.por_id(pronto.id).estado is EstadoDoTrabalho.RENDERED


def test_por_que_o_mutante_sobrevivente_e_equivalente(bancada):
    """Classificação do único mutante que sobrevive ao score de 95,2%.

    O mutante remove `exigir_operario=self.nome` da transição para `rendered`.
    Ele sobrevive, e a razão é medida aqui: **a máquina de estados já barra o
    caminho antes**. Quem perdeu o lease encontra o trabalho em `claimed` (o novo
    dono acabou de reivindicar), e `claimed → validating` não existe no mapa.

    Isto não é desculpa: é a diferença entre defesa em profundidade e guarda
    única. `exigir_operario` continua no código porque a máquina de estados pode
    ganhar uma transição nova amanhã, e aí ele deixa de ser redundante. Mas
    contá-lo como cobertura seria inflar o score com uma mutação equivalente.
    """
    from app.criativo.bancada.contrato import EstadoDoTrabalho as E
    from app.criativo.bancada.contrato import pode_ir

    # O caminho que o operário perdido tentaria percorrer não existe.
    assert not pode_ir(E.CLAIMED, E.VALIDATING)
    assert not pode_ir(E.CLAIMED, E.RENDERED)
    assert not pode_ir(E.QUEUED, E.RENDERED)
    # O único caminho para `rendered` sai de `validating`.
    for origem in (E.QUEUED, E.CLAIMED, E.RUNNING, E.FAILED, E.CANCELLED, E.RENDERED):
        assert not pode_ir(origem, E.RENDERED), f"{origem.value} alcança rendered"
    assert pode_ir(E.VALIDATING, E.RENDERED)

    # E na prática: A perde o lease, B reivindica, A tenta seguir.
    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    a = deposito.reivindicar("op-A", lease_s=-1)
    deposito.devolver_vencidos()
    b = deposito.reivindicar("op-B")
    assert a.id == b.id

    # A acha o trabalho em `claimed` (de B) e não consegue avançar.
    with pytest.raises(TransicaoProibida):
        deposito.transicionar(a.id, EstadoDoTrabalho.VALIDATING)


# ═══════════════════════════════════════════════════════════════════════════
# 13. Achados da auditoria adversarial final
# ═══════════════════════════════════════════════════════════════════════════


def test_operario_zumbi_nao_dirige_a_maquina_de_estados_do_dono(bancada):
    """`claimed -> running` EXISTE no mapa, e as transições iam sem
    `exigir_operario`. Um operário que já perdera o lease avançava o job do dono
    legítimo; o dono, ao tentar a mesma transição, levava `running -> running`
    proibida, caía no `except` genérico e apagava o próprio diretório."""
    deposito, _ = bancada
    deposito.enfileirar(encomenda())
    a = deposito.reivindicar("op-A", lease_s=-1)
    deposito.devolver_vencidos()
    b = deposito.reivindicar("op-B")
    assert a.id == b.id

    with pytest.raises(TransicaoProibida):
        deposito.transicionar(
            a.id, EstadoDoTrabalho.RUNNING, exigir_operario="op-A"
        )
    assert deposito.por_id(a.id).estado is EstadoDoTrabalho.CLAIMED
    # o dono legítimo segue livre
    deposito.transicionar(b.id, EstadoDoTrabalho.RUNNING, exigir_operario="op-B")
    assert deposito.por_id(b.id).estado is EstadoDoTrabalho.RUNNING


def test_render_que_perde_a_posse_nao_deixa_arquivo_no_disco(bancada, tmp_path):
    """O `rmtree` vinha DEPOIS do `return` do `except TransicaoProibida`, então
    todo render que perdia o lease deixava o arquivo para sempre."""
    import threading

    comecou = threading.Event()
    segue = threading.Event()
    visto: list[Path] = []

    class MotorLento:
        slug, versao = "lento2", "1"

        def versoes_congeladas(self) -> dict[str, str]:
            return {"adaptador": "1"}

        def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
            import hashlib

            visto.append(Path(d))
            comecou.set()
            segue.wait(timeout=5)
            p = Path(d) / "x.png"
            dados = b"\x89PNG\r\n\x1a\n" + b"p" * 128
            p.write_bytes(dados)
            return (Artefato("1x1", str(p), "image/png", len(dados),
                             hashlib.sha256(dados).hexdigest(), 1080, 1080),)

    deposito, _ = bancada
    op = Operario(deposito, {"lento2": MotorLento()}, tmp_path / "l2",
                  nome="op-A", lease_s=-1)
    t, _ = deposito.enfileirar(encomenda(motor_slug="lento2"))
    fio = threading.Thread(target=op.trabalhar_uma_vez)
    fio.start()
    assert comecou.wait(timeout=5)
    deposito.devolver_vencidos()
    deposito.reivindicar("op-B")
    segue.set()
    fio.join(timeout=10)

    assert visto and not visto[0].exists(), "o diretório do render perdido ficou no disco"


def test_o_batimento_acompanha_o_lease_em_vez_de_ser_fixo(bancada):
    """O intervalo era fixo em 5s enquanto `lease_s` era parâmetro: qualquer
    `Operario(lease_s<=5)` era, por construção, uma configuração sem batimento —
    e nada avisava."""
    from app.criativo.bancada.operario import Batimento

    deposito, _ = bancada
    b = Batimento(deposito, "x", operario="op", lease_s=3)
    assert b._intervalo < 3, "o batimento não caberia dentro do lease"
    b2 = Batimento(deposito, "x", operario="op", lease_s=60)
    assert b2._intervalo <= 20


def test_retomada_grava_o_tenant_conferido_e_nao_o_da_encomenda(bancada):
    """`enfileirar` gravava `encomenda.tenant_id`, e a encomenda vem de
    `_desserializar`, que faz `.get(...) or ""`. A rota respondia 201 com o id e
    `por_id(tenant)` devolvia 404 para sempre.

    ⚠️ A primeira versão desta prova usava `tenant_id=""` em TODOS os lugares —
    linha, encomenda e chamada. Isso não reproduzia o defeito relatado: com tudo
    vazio, conferir e gravar davam o mesmo valor por acidente. O cenário real é
    a LINHA pertencer ao tenant A e a ENCOMENDA vir desserializada sem tenant,
    com a chamada autenticada como A.
    """
    import json

    deposito, operario = bancada
    t, _ = deposito.enfileirar(encomenda(tenant_id="tenant-A", motor_slug="motor-ausente"))
    operario.trabalhar_uma_vez()
    assert deposito.por_id(t.id).estado is EstadoDoTrabalho.FAILED

    # A encomenda gravada perde o tenant, como sairia de uma fila anterior ao
    # campo existir. A LINHA continua sendo do tenant A.
    c = deposito._con()
    corpo = json.loads(
        c.execute("select encomenda_json from trabalho where id=?", (t.id,)).fetchone()[0]
    )
    del corpo["tenant_id"]
    c.execute("update trabalho set encomenda_json=? where id=?", (json.dumps(corpo), t.id))
    assert deposito.por_id(t.id).encomenda.tenant_id == "", "o dublê precisa do defeito"
    assert deposito.por_id(t.id).tenant_id == "tenant-A", "a linha continua do dono"

    # O dono real retoma, autenticado como A.
    novo, criado = deposito.retomar(t.id, tenant_id="tenant-A")
    assert criado
    assert novo.tenant_id == "tenant-A", (
        "a retomada nasceu com o tenant da ENCOMENDA (vazio) em vez do conferido"
    )
    assert deposito.por_id(novo.id, tenant_id="tenant-A") is not None, (
        "a rota responderia 201 e por_id daria 404 para sempre"
    )
    assert novo.encomenda.tenant_id == novo.tenant_id
    assert any(x.id == novo.id for x in deposito.listar(tenant_id="tenant-A"))


def test_por_que_a_segunda_mutacao_sobrevivente_e_equivalente(bancada, tmp_path):
    """O mutante remove a conferência de cancelamento antes de `validating`.

    Ele sobrevive porque as correções de 29/08 tornaram o desfecho o mesmo:
    `transicionar(VALIDATING)` leva `exigir_operario`, `cancelled` é terminal,
    então a transição estoura, cai no `_falhar`, e o `rmtree` do ramo de perda de
    posse limpa o diretório. Sem recibo, sem arquivo — nos dois caminhos.

    A guarda fica no código porque ela diz o motivo no log, em vez de registrar
    uma "falha inesperada" que não foi inesperada. Isso é legibilidade de
    operação, não cobertura — e contá-la como cobertura seria inflar o score.
    """
    from app.criativo.bancada.contrato import EstadoDoTrabalho as E
    from app.criativo.bancada.contrato import pode_ir

    # Nenhuma saída de `cancelled`: a máquina de estados já fecha o caminho.
    for destino in E:
        assert not pode_ir(E.CANCELLED, destino), f"cancelled alcança {destino.value}"


# ═══════════════════════════════════════════════════════════════════════════
# 14. A fronteira do despacho: fail-closed, e sem eufemismo
# ═══════════════════════════════════════════════════════════════════════════


def test_ambiente_sem_processo_longo_RECUSA_em_vez_de_cair_no_sqlite(monkeypatch):
    """Eu chamei SQLite local de "fila durável". Na Vercel o disco da função não
    sobrevive à requisição — a afirmação era falsa, e cair nele em silêncio seria
    pior que recusar."""
    from app.criativo.bancada.despacho import (
        DespachoIndisponivel,
        escolher_despachante,
    )

    for ambiente in ("vercel", "lambda", "cloudflare"):
        monkeypatch.setenv("CRIATIVO_AMBIENTE", ambiente)
        with pytest.raises(DespachoIndisponivel) as erro:
            escolher_despachante()
        assert erro.value.ambiente == ambiente
        assert "congelada" in erro.value.motivo or "vida longa" in erro.value.motivo


def test_o_despachante_local_NAO_se_declara_duravel(monkeypatch):
    """A honestidade é do próprio objeto, não de um comentário."""
    from app.criativo.bancada.despacho import escolher_despachante

    monkeypatch.setenv("CRIATIVO_AMBIENTE", "local")
    d = escolher_despachante()
    assert d.duravel is False, "o despachante local não pode se dizer durável"
    assert d.sincrono is True


def test_a_variavel_da_vercel_e_reconhecida_sem_declaracao(monkeypatch):
    from app.criativo.bancada.despacho import ambiente_atual

    monkeypatch.delenv("CRIATIVO_AMBIENTE", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    assert ambiente_atual() == "vercel"


def test_falha_ao_despachar_deixa_o_job_terminal_e_visivel(monkeypatch, tmp_path):
    """`_registrar_indisponibilidade` tinha `contextlib.suppress(Exception)` em
    volta de tudo: uma falha ao registrar a falha virava silêncio, e a rota
    respondia 201 sobre um job que ficaria em `queued` para sempre."""
    from test_criativo_execucao import PEDIDO, MotorFalso, RepoFalso  # noqa: PLC0415

    from app.criativo.armazenamento import ArmazenamentoLocal, Assinador
    from app.criativo.execucao import Executor

    monkeypatch.setenv("CRIATIVO_AMBIENTE", "vercel")
    repo = RepoFalso()
    executor = Executor(repo, ArmazenamentoLocal(tmp_path), MotorFalso(),
                        Assinador("s" * 32))
    job, criado = anyio_run(executor.criar_job_de_imagem, PEDIDO, "usuario-1")
    assert criado is True

    executor.disparar(str(job["id"]))

    final = repo.jobs[job["id"]]
    assert final["estado"] == "failed", "o job ficou órfão em queued"
    assert final["falha"]["codigo"] == "ESTUDIO.despacho_indisponivel"
    assert final["falha"]["permanente"] is False
    assert final["terminado_em"], "terminal sem carimbo"


def anyio_run(fn, *args):
    import anyio

    return anyio.run(fn, *args)


# ═══════════════════════════════════════════════════════════════════════════
# Achado #13 — o operário zumbi: perder o lease precisa PARAR o operário
#
# `Batimento.perdeu_o_trabalho` era escrita e nunca lida. O depósito recusava as
# transições de quem não é mais dono (isso já era provado acima), mas o operário
# seguia até o fim e caía no tratamento de falha — que apaga o diretório do
# trabalho. Como o caminho é `raiz/<id do trabalho>`, e o id é o MESMO para o
# novo dono, quem perdeu o lease apagava o diretório de quem o pegou.
# ═══════════════════════════════════════════════════════════════════════════


class MotorQueTrava:
    """Bloqueia dentro de `produzir` até o teste liberar. Sem sleep arbitrário:
    a coordenação é por evento, então a corrida é determinística."""

    slug, versao = "trava", "1"

    def __init__(self) -> None:
        import threading as _t

        self.entrou = _t.Event()
        self.liberar = _t.Event()
        self.produziu = 0

    def versoes_congeladas(self) -> dict[str, str]:
        return {}

    def produzir(self, encomenda_: Any, diretorio: str) -> tuple[Artefato, ...]:
        self.entrou.set()
        self.liberar.wait(timeout=10)
        self.produziu += 1
        alvo = Path(diretorio) / "1x1.png"
        alvo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        return (
            Artefato(
                slot="1x1", caminho=str(alvo), mime="image/png",
                largura=1080, altura=1080, bytes_=alvo.stat().st_size,
                sha256="0" * 64, duracao_s=None,
            ),
        )


def _cenario_de_perda(tmp_path: Path):
    """A reivindica com lease vencido, B assume, e A ainda está produzindo."""
    import threading

    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    motor = MotorQueTrava()
    raiz = tmp_path / "trabalhos"  # A e B compartilham a raiz, como em produção
    a = Operario(deposito, {"trava": motor}, raiz, nome="op-A", lease_s=-1)
    deposito.enfileirar(encomenda(motor_slug="trava"))
    pego = deposito.reivindicar("op-A", lease_s=-1)
    assert pego is not None

    saida: dict[str, Any] = {}
    fio = threading.Thread(target=lambda: saida.update(t=a.executar(pego)), daemon=True)
    fio.start()
    assert motor.entrou.wait(timeout=10), "o motor nem começou"

    # Enquanto A produz, o lease vence e B assume.
    deposito.devolver_vencidos()
    b = deposito.reivindicar("op-B")
    assert b is not None and b.id == pego.id
    return deposito, motor, raiz, pego, fio, saida


def test_operario_que_perdeu_o_lease_nao_apaga_o_diretorio_do_novo_dono(tmp_path):
    deposito, motor, raiz, pego, fio, _saida = _cenario_de_perda(tmp_path)

    # B começa a trabalhar. A asserção não depende de como a pasta de B se
    # chama: basta que algo colocado por OUTRO dono, dentro da pasta do
    # trabalho, sobreviva à limpeza de A.
    dir_do_trabalho = raiz / pego.id
    dir_do_trabalho.mkdir(parents=True, exist_ok=True)
    arquivo_de_b = dir_do_trabalho / "peca-do-B.png"
    arquivo_de_b.write_bytes(b"bytes que pertencem ao op-B")

    motor.liberar.set()
    fio.join(timeout=10)
    assert not fio.is_alive(), "o operário travou"

    assert arquivo_de_b.exists(), (
        "o operário que perdeu o lease apagou o diretório do novo dono"
    )
    assert arquivo_de_b.read_bytes() == b"bytes que pertencem ao op-B"


def test_operario_que_perdeu_o_lease_nao_muda_estado_nem_grava_recibo(tmp_path):
    deposito, motor, _raiz, pego, fio, saida = _cenario_de_perda(tmp_path)

    antes = deposito.por_id(pego.id)
    assert antes is not None and antes.operario == "op-B"

    motor.liberar.set()
    fio.join(timeout=10)
    assert not fio.is_alive()

    depois = deposito.por_id(pego.id)
    assert depois is not None
    assert depois.operario == "op-B", "A tirou o trabalho das mãos de B"
    assert depois.estado is antes.estado, "A mexeu no estado de um trabalho que não é dele"
    assert depois.recibo is None, "A gravou recibo por cima do trabalho de B"
    devolvido = saida.get("t")
    assert devolvido is not None and devolvido.recibo is None


def test_perda_de_lease_e_detectada_antes_de_gastar_a_validacao(tmp_path):
    """A bandeira deixou de ser morta: ela é consultada e interrompe o fluxo.

    Sem consumo da bandeira o operário seguia para `validating` e só era barrado
    pelo depósito — depois de já ter validado, montado recibo e calculado
    assinatura.
    """
    deposito, motor, _raiz, pego, fio, saida = _cenario_de_perda(tmp_path)
    motor.liberar.set()
    fio.join(timeout=10)

    devolvido = saida.get("t")
    assert devolvido is not None
    # O trabalho volta como o DEPÓSITO o vê, não como A gostaria que fosse.
    assert devolvido.operario == "op-B"
    assert devolvido.estado is not EstadoDoTrabalho.RENDERED


def test_lease_curto_nao_desliga_o_batimento(tmp_path):
    """`lease_s` menor que o intervalo antigo (5s) era, por construção, uma
    configuração sem batimento. O intervalo acompanha o lease."""
    from app.criativo.bancada.operario import Batimento

    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    deposito.enfileirar(encomenda())
    pego = deposito.reivindicar("op-A", lease_s=2)
    assert pego is not None
    with Batimento(deposito, pego.id, operario="op-A", lease_s=2) as b:
        assert b._intervalo <= 1.0, "o batimento é mais lento que o próprio lease"
        deadline = time.monotonic() + 3.0
        while b.batidas < 1 and time.monotonic() < deadline:
            time.sleep(0.05)
    assert b.batidas >= 1, "nenhuma batida dentro de um lease de 2s"
    assert b.perdeu_o_trabalho is False


def _batimento_espiao(monkeypatch):
    """Captura a instância de `Batimento` criada dentro de `executar`.

    Sem isto não dá para isolar a BANDEIRA do veredito do depósito: os dois
    concordam em toda corrida real, e um teste que só olha o desfecho passa
    mesmo com a bandeira ignorada — foi o que o mutation test mostrou.
    """
    import app.criativo.bancada.operario as mod

    criados: list[Any] = []
    original = mod.Batimento

    class Espiao(original):  # type: ignore[misc, valid-type]
        def __init__(self, *a: Any, **k: Any) -> None:
            super().__init__(*a, **k)
            criados.append(self)

    monkeypatch.setattr(mod, "Batimento", Espiao)
    return criados


def test_a_bandeira_do_batimento_sozinha_interrompe_o_operario(tmp_path, monkeypatch):
    """A bandeira deixou de ser código morto — provado sem ajuda do depósito.

    Aqui o depósito CONTINUA dizendo que o trabalho é do op-A: só a bandeira
    do batimento afirma a perda. Se o operário ignorar a bandeira, ele conclui
    e grava recibo. É esta prova que morre quando a leitura da bandeira some.
    """
    criados = _batimento_espiao(monkeypatch)
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    motor = MotorQueTrava()
    op = Operario(deposito, {"trava": motor}, tmp_path / "trabalhos", nome="op-A")
    t, _ = deposito.enfileirar(encomenda(motor_slug="trava"))

    import threading

    saida: dict[str, Any] = {}
    fio = threading.Thread(target=lambda: saida.update(t=op.trabalhar_uma_vez()), daemon=True)
    fio.start()
    assert motor.entrou.wait(timeout=10)

    assert criados, "o batimento não foi criado"
    criados[0].perdeu_o_trabalho = True  # o coração bateu e foi recusado
    motor.liberar.set()
    fio.join(timeout=10)
    assert not fio.is_alive()

    final = deposito.por_id(t.id)
    assert final is not None
    assert final.operario == "op-A", "o depósito nunca deixou de nos dar o trabalho"
    assert final.recibo is None, "a bandeira foi ignorada: gravou recibo assim mesmo"
    assert final.estado is not EstadoDoTrabalho.RENDERED


def test_a_perda_entre_a_validacao_e_o_recibo_e_barrada_antes_de_gravar(tmp_path, monkeypatch):
    """O segundo checkpoint, isolado.

    `versoes_congeladas()` é chamado ao montar o recibo — depois da validação e
    antes da transição para `rendered`. Perder o trabalho exatamente aí só é
    detectado pela conferência que precede a gravação.
    """
    criados = _batimento_espiao(monkeypatch)
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")

    class MotorQuePerdeNoRecibo:
        slug, versao = "perde-no-recibo", "1"

        def versoes_congeladas(self) -> dict[str, str]:
            if criados:
                criados[0].perdeu_o_trabalho = True
            return {"adaptador": "1"}

        def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
            import hashlib

            p = Path(d) / "x.png"
            dados = b"\x89PNG\r\n\x1a\n" + b"r" * 128
            p.write_bytes(dados)
            return (Artefato("1x1", str(p), "image/png", len(dados),
                             hashlib.sha256(dados).hexdigest(), 1080, 1080),)

    op = Operario(deposito, {"perde-no-recibo": MotorQuePerdeNoRecibo()},
                  tmp_path / "trabalhos", nome="op-A")
    t, _ = deposito.enfileirar(encomenda(motor_slug="perde-no-recibo"))
    op.trabalhar_uma_vez()

    final = deposito.por_id(t.id)
    assert final is not None
    assert final.recibo is None, "gravou recibo depois de perder o trabalho"
    assert final.estado is not EstadoDoTrabalho.RENDERED


# ═══════════════════════════════════════════════════════════════════════════
# Achados da revisão adversarial (Codex, 2026-08-29) sobre o fechamento do #13
# ═══════════════════════════════════════════════════════════════════════════


def test_zumbi_nao_reprova_o_trabalho_do_novo_dono(tmp_path, monkeypatch):
    """A saída por gate reprovado não passava pela guarda de posse.

    `reprovou` transicionava para FAILED sem `exigir_operario`: era a única saída
    irreversível sem trava. O checkpoint anterior não alcança este ramo — ele
    roda ANTES da validação, e a perda aqui acontece DURANTE ela. Por isso o
    teste perde o lease dentro de `_validar`, que é a janela real.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")

    class MotorSimples:
        slug, versao = "simples", "1"

        def versoes_congeladas(self) -> dict[str, str]:
            return {}

        def produzir(self, e: Encomenda, d: str) -> tuple[Artefato, ...]:
            import hashlib

            p = Path(d) / "x.png"
            dados = b"\x89PNG\r\n\x1a\n" + b"z" * 128
            p.write_bytes(dados)
            return (Artefato("1x1", str(p), "image/png", len(dados),
                             hashlib.sha256(dados).hexdigest(), 1080, 1080),)

    op = Operario(deposito, {"simples": MotorSimples()}, tmp_path / "t", nome="op-A")
    t, _ = deposito.enfileirar(encomenda(motor_slug="simples"))
    alvo = deposito.reivindicar("op-A")
    assert alvo is not None

    def validar_perdendo_o_lease(self, *_args, **_kw):
        # O trabalho sai das nossas mãos no meio da validação.
        deposito.soltar_por_lease_vencido(alvo.id) if hasattr(
            deposito, "soltar_por_lease_vencido") else None
        import sqlite3 as _s
        con = _s.connect(str(tmp_path / "fila.db"))
        con.execute("update trabalho set operario='op-B' where id=?", (alvo.id,))
        con.commit(); con.close()
        return [Validacao(gate="dimensao", resultado="FAIL",
                          detalhe={"motivo": "reprovado de proposito"},
                          bloqueante=True)]

    monkeypatch.setattr(Operario, "_validar", validar_perdendo_o_lease)
    op.executar(alvo)

    final = deposito.por_id(t.id)
    assert final is not None
    assert final.estado is not EstadoDoTrabalho.FAILED, (
        "o zumbi reprovou o trabalho que já era de op-B"
    )
    assert final.operario == "op-B", "o zumbi soltou o dono do trabalho alheio"


def test_batimento_nao_ressuscita_lease_ja_vencido(tmp_path):
    """`bater()` não filtrava por `lease_ate`: um processo pausado por mais tempo
    que o lease voltava a bater e empurrava o prazo para o futuro, vencendo a
    corrida contra o recolhedor. O lease deixava de ser prazo e virava sugestão.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    deposito.enfileirar(encomenda())
    pego = deposito.reivindicar("op-A", lease_s=-1)  # nasce vencido
    assert pego is not None
    assert deposito.por_id(pego.id).vivo is False

    assert deposito.bater(pego.id, lease_s=60, operario="op-A") is False, (
        "o batimento renovou um lease que já tinha vencido"
    )
    assert deposito.por_id(pego.id).vivo is False, "o lease vencido voltou ao futuro"


def test_a_posse_e_da_reivindicacao_e_nao_do_nome(tmp_path):
    """Mesmo nome, reivindicação nova: o zumbi da anterior não é mais dono.

    `_ainda_sou_dono` comparava só `operario == self.nome`. Quando o MESMO
    operário reivindica de novo (tentativa+1), o zumbi da tentativa antiga
    reconhecia a si mesmo como dono e concluía por cima — gravando recibo que
    aponta para o diretório da tentativa velha.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    deposito.enfileirar(encomenda())
    velho = deposito.reivindicar("op-A", lease_s=-1)
    assert velho is not None
    deposito.devolver_vencidos()
    novo = deposito.reivindicar("op-A")  # mesmo nome, outra reivindicação
    assert novo is not None and novo.tentativa > velho.tentativa

    op = Operario(deposito, {}, tmp_path / "t", nome="op-A")
    from app.criativo.bancada.operario import Batimento

    b = Batimento(deposito, velho.id, operario="op-A", lease_s=60)
    assert op._ainda_sou_dono_da_reivindicacao(velho, b) is False, (
        "o zumbi da tentativa antiga ainda se acha dono"
    )
    assert op._ainda_sou_dono_da_reivindicacao(novo, b) is True
