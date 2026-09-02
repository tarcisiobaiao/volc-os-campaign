"""A suite de CONTRATO do deposito: as mesmas assercoes nos dois adapters.

## Por que este arquivo existe

O P17-T04 pede "uma unica porta escolhe o deposito por ambiente; o mesmo
contrato de claim, lease, heartbeat, idempotencia, transicao e recibo passa nos
dois adapters SEM DUPLA VERDADE". Um `Protocol` sozinho nao prova nada: ele
garante que os metodos existem, nao que fazem a mesma coisa. Quatro divergencias
reais viveram anos sob assinaturas identicas — lease vencido que avancava,
`rendered` sem artefato, mensagem com caminho de disco, trilha inexistente.

Cada prova aqui roda DUAS vezes: uma contra SQLite, uma contra um cluster
Postgres descartavel com a v11_03 aplicada. Uma prova que so passa num dos dois
e uma divergencia, e o parametro no nome do teste diz qual.

## O que este arquivo NAO faz

Nao fala com o Supabase oficial. Nao aplica migration em lugar nenhum alem do
cluster que ele mesmo cria e destroi. Nao chama motor, provider nem rede.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from app.criativo.bancada.contrato import (
    Encomenda,
    EstadoDoTrabalho,
    SaidaPedida,
    TransicaoProibida,
)
from app.criativo.bancada.deposito import DepositoDeTrabalhos, LeaseVencido
from app.criativo.bancada.porta import Deposito, DepositoIndisponivel, escolher_deposito

pytest_plugins = ["tests.conftest_postgres"]


# ─────────────────────────────────────────────────────────────────────────────
# Os dois depositos, sob o mesmo nome
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(params=["sqlite", "postgres"])
def deposito(request: pytest.FixtureRequest, tmp_path) -> Deposito:
    """O mesmo teste, os dois depositos.

    ⚠️ O parametro entra no NOME do teste de proposito: quando um dos dois
    quebra, o relatorio ja diz qual, sem ninguem precisar reler a fixture.
    """
    if request.param == "sqlite":
        return DepositoDeTrabalhos(tmp_path / "fila.db")
    dsn = request.getfixturevalue("dsn_postgres")
    from app.criativo.bancada.deposito_postgres import DepositoPostgres

    d = DepositoPostgres(dsn)
    # Cada teste comeca com a fila vazia; o cluster e da sessao inteira.
    with d._con().cursor() as cur:  # noqa: SLF001
        cur.execute(
            "truncate public.criativo_render_validacao,"
            " public.criativo_render_artefato, public.criativo_render_recibo,"
            " public.criativo_render_transicao, public.criativo_render_job cascade"
        )
    return d


def encomenda(*, tenant: str = "tenant-A", seed: int = 7, motor: str = "m") -> Encomenda:
    return Encomenda(
        receita_id="receita-contrato",
        tenant_id=tenant,
        motor_slug=motor,
        modo_slug="typography_only",
        finalidade_slug="google_display",
        seed=seed,
        saidas=(SaidaPedida("1x1", 1080, 1080, "imagem", "image/png"),),
        parametros={"titulo": "contrato"},
    )


def recibo_valido(**extra: Any) -> dict[str, Any]:
    """Um recibo que os DOIS depositos aceitam: com artefato, bytes e hash reais."""
    base = {
        "produzido_por": "op-A",
        "motor_slug": "m",
        "motor_versao": "1",
        "seed": 7,
        "versoes": {"motor": "1"},
        "parametros": {"titulo": "contrato"},
        "assinatura_determinista": "a" * 64,
        "iniciado_em": "2026-09-01T00:00:00+00:00",
        "terminado_em": "2026-09-01T00:00:01+00:00",
        "artefatos": [{
            "slot": "1x1", "caminho": "/nao-lido", "mime": "image/png",
            "bytes_": 128, "sha256": "b" * 64, "largura": 1080, "altura": 1080,
            "duracao_s": None,
        }],
        "validacoes": [{"gate": "hash_confere", "resultado": "PASS",
                        "detalhe": {"bytes": 128}, "bloqueante": True}],
        "audio": None,
        "custo_estimado_usd": None,
        "custo_real_usd": None,
    }
    base.update(extra)
    return base


def ate_validating(d: Deposito, *, operario: str = "op-A", lease_s: int = 60):
    d.enfileirar(encomenda())
    t = d.reivindicar(operario, lease_s=lease_s)
    assert t is not None
    d.transicionar(t.id, EstadoDoTrabalho.RUNNING, exigir_operario=operario)
    d.transicionar(t.id, EstadoDoTrabalho.VALIDATING, exigir_operario=operario)
    return t


# ─────────────────────────────────────────────────────────────────────────────
# 1. idempotencia
# ─────────────────────────────────────────────────────────────────────────────


def test_o_mesmo_pedido_nao_vira_dois_trabalhos(deposito: Deposito) -> None:
    a, criado_a = deposito.enfileirar(encomenda())
    b, criado_b = deposito.enfileirar(encomenda())
    assert criado_a is True and criado_b is False
    assert a.id == b.id, "o mesmo pedido pagou duas vezes"


def test_dois_inquilinos_com_o_mesmo_pedido_sao_dois_trabalhos(deposito: Deposito) -> None:
    a, _ = deposito.enfileirar(encomenda(tenant="tenant-A"))
    b, criado = deposito.enfileirar(encomenda(tenant="tenant-B"))
    assert criado is True
    assert a.id != b.id, "um inquilino leria o artefato do outro"


def test_a_leitura_por_id_nao_atravessa_inquilino(deposito: Deposito) -> None:
    a, _ = deposito.enfileirar(encomenda(tenant="tenant-A"))
    assert deposito.por_id(a.id, tenant_id="tenant-B") is None
    assert deposito.por_id(a.id, tenant_id="tenant-A") is not None


# ─────────────────────────────────────────────────────────────────────────────
# 2. claim exclusivo
# ─────────────────────────────────────────────────────────────────────────────


def test_dois_operarios_concorrentes_nao_pegam_o_mesmo_trabalho(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda(seed=1))
    largada = threading.Barrier(2)
    pegos: list[Any] = []
    trava = threading.Lock()

    def disputar(nome: str) -> None:
        largada.wait(timeout=5)
        t = deposito.reivindicar(nome, lease_s=60)
        with trava:
            pegos.append((nome, t.id if t else None))

    fios = [threading.Thread(target=disputar, args=(f"op-{n}",)) for n in "AB"]
    for f in fios:
        f.start()
    for f in fios:
        f.join(timeout=10)

    ids = [i for _, i in pegos if i is not None]
    assert len(ids) == 1, f"dois claims para um trabalho: {pegos}"


def test_reivindicar_este_pega_o_pedido_e_nao_o_mais_antigo(deposito: Deposito) -> None:
    velho, _ = deposito.enfileirar(encomenda(seed=1))
    novo, _ = deposito.enfileirar(encomenda(seed=2))
    pego = deposito.reivindicar_este(novo.id, "op-A", lease_s=60)
    assert pego is not None and pego.id == novo.id
    assert deposito.por_id(velho.id).estado is EstadoDoTrabalho.QUEUED


# ─────────────────────────────────────────────────────────────────────────────
# 3. lease
# ─────────────────────────────────────────────────────────────────────────────


def test_lease_vencido_volta_para_a_fila_sem_virar_falha(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=-1)
    assert t is not None
    devolvidos = deposito.devolver_vencidos()
    assert devolvidos == 1
    depois = deposito.por_id(t.id)
    assert depois.estado is EstadoDoTrabalho.QUEUED, "lease vencido virou falha"
    assert depois.operario is None and depois.lease_ate is None
    assert depois.falha is None, "um operario que morreu invalidou o pedido"


def test_lease_vencido_nao_avanca_para_running(deposito: Deposito) -> None:
    """A divergencia que o P17-T04 fechou: o Postgres recusava, o SQLite deixava."""
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=-1)
    with pytest.raises((LeaseVencido, TransicaoProibida)):
        deposito.transicionar(t.id, EstadoDoTrabalho.RUNNING, exigir_operario="op-A")
    assert deposito.por_id(t.id).estado is EstadoDoTrabalho.CLAIMED


def test_o_batimento_so_renova_lease_que_ainda_vale(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=-1)
    assert deposito.bater(t.id, lease_s=60, operario="op-A") is False, (
        "quem dormiu mais que o proprio lease ressuscitou a posse"
    )


def test_o_batimento_nao_e_de_quem_nao_e_dono(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=60)
    assert deposito.bater(t.id, lease_s=60, operario="op-B") is False
    assert deposito.bater(t.id, lease_s=60, operario="op-A") is True


def test_a_transicao_nao_renova_o_lease(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=60)
    antes = deposito.por_id(t.id).lease_ate
    time.sleep(0.05)
    deposito.transicionar(t.id, EstadoDoTrabalho.RUNNING, exigir_operario="op-A")
    assert deposito.por_id(t.id).lease_ate == antes, (
        "a transicao empurrou o prazo; renovar e trabalho do batimento"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. posse
# ─────────────────────────────────────────────────────────────────────────────


def test_quem_nao_e_dono_nao_transiciona(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=60)
    with pytest.raises(TransicaoProibida):
        deposito.transicionar(t.id, EstadoDoTrabalho.RUNNING, exigir_operario="op-B")
    assert deposito.por_id(t.id).estado is EstadoDoTrabalho.CLAIMED


def test_o_dono_some_quando_o_trabalho_sai_de_execucao(deposito: Deposito) -> None:
    t = ate_validating(deposito)
    final = deposito.transicionar(
        t.id, EstadoDoTrabalho.RENDERED, recibo=recibo_valido(), exigir_operario="op-A"
    )
    assert final.operario is None and final.lease_ate is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. transicao
# ─────────────────────────────────────────────────────────────────────────────


def test_transicao_fora_do_mapa_e_recusada(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=60)
    with pytest.raises(TransicaoProibida):
        deposito.transicionar(t.id, EstadoDoTrabalho.RENDERED,
                              recibo=recibo_valido(), exigir_operario="op-A")


def test_terminal_nao_volta(deposito: Deposito) -> None:
    t = ate_validating(deposito)
    deposito.transicionar(t.id, EstadoDoTrabalho.RENDERED,
                          recibo=recibo_valido(), exigir_operario="op-A")
    with pytest.raises(TransicaoProibida):
        deposito.transicionar(t.id, EstadoDoTrabalho.QUEUED)


def test_terminal_e_carimbado(deposito: Deposito) -> None:
    t = ate_validating(deposito)
    assert deposito.por_id(t.id).terminado_em is None, "carimbou antes de terminar"
    final = deposito.transicionar(t.id, EstadoDoTrabalho.RENDERED,
                                  recibo=recibo_valido(), exigir_operario="op-A")
    assert final.terminado_em is not None


# ─────────────────────────────────────────────────────────────────────────────
# 6. recibo
# ─────────────────────────────────────────────────────────────────────────────


def test_nao_se_conclui_sem_recibo(deposito: Deposito) -> None:
    t = ate_validating(deposito)
    with pytest.raises(ValueError):
        deposito.transicionar(t.id, EstadoDoTrabalho.RENDERED, exigir_operario="op-A")


def test_nao_se_conclui_com_recibo_de_zero_artefatos(deposito: Deposito) -> None:
    """"Recibo sem artefato e promessa, nao prova." O SQLite aceitava."""
    t = ate_validating(deposito)
    with pytest.raises(ValueError):
        deposito.transicionar(t.id, EstadoDoTrabalho.RENDERED,
                              recibo=recibo_valido(artefatos=[]), exigir_operario="op-A")
    assert deposito.por_id(t.id).estado is EstadoDoTrabalho.VALIDATING


def test_nao_se_falha_sem_motivo(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=60)
    with pytest.raises(ValueError):
        deposito.transicionar(t.id, EstadoDoTrabalho.FAILED, exigir_operario="op-A")


@pytest.mark.parametrize("mensagem", [
    "No space left on device:/var/folders/ab/cd",
    "erro ao abrir (/Users/mac/peca.png)",
    "falha em C:\\Windows\\Temp\\x",
    "falha em \\\\servidor\\share\\x",
    "nao achei ~/config",
    "Traceback (most recent call last):",
])
def test_a_falha_nao_carrega_caminho_de_disco(deposito: Deposito, mensagem: str) -> None:
    """Lacuna L1 do handoff da bancada: a migration barrava, a fila nao."""
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=60)
    with pytest.raises(ValueError):
        deposito.transicionar(
            t.id, EstadoDoTrabalho.FAILED,
            falha={"codigo": "x", "mensagem": mensagem, "permanente": True},
            exigir_operario="op-A",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. trilha
# ─────────────────────────────────────────────────────────────────────────────


def test_a_trilha_guarda_todas_as_passagens(deposito: Deposito) -> None:
    """Um trabalho que voltou para a fila nao pode chegar ao fim indistinguivel
    de um que falhou de primeira."""
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=60)
    deposito.transicionar(t.id, EstadoDoTrabalho.RUNNING, exigir_operario="op-A")
    deposito.transicionar(t.id, EstadoDoTrabalho.QUEUED,
                          falha={"codigo": "transitoria", "mensagem": "tenta de novo",
                                 "permanente": False},
                          exigir_operario="op-A")
    t2 = deposito.reivindicar("op-B", lease_s=60)
    deposito.transicionar(t2.id, EstadoDoTrabalho.RUNNING, exigir_operario="op-B")

    trilha = deposito.trilha(t.id)
    passos = [(p["de"], p["para"]) for p in trilha]
    assert passos == [
        ("queued", "claimed"), ("claimed", "running"),
        ("running", "queued"), ("queued", "claimed"), ("claimed", "running"),
    ], f"trilha incompleta: {passos}"


def test_a_trilha_nao_atravessa_inquilino(deposito: Deposito) -> None:
    t, _ = deposito.enfileirar(encomenda(tenant="tenant-A"))
    with pytest.raises(KeyError):
        deposito.trilha(t.id, tenant_id="tenant-B")


# ─────────────────────────────────────────────────────────────────────────────
# 8. retomada e cancelamento
# ─────────────────────────────────────────────────────────────────────────────


def test_retomar_cria_trabalho_novo_com_linhagem(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=60)
    deposito.transicionar(t.id, EstadoDoTrabalho.FAILED,
                          falha={"codigo": "x", "mensagem": "nao deu",
                                 "permanente": True},
                          exigir_operario="op-A")
    novo, criado = deposito.retomar(t.id, tenant_id="tenant-A")
    assert criado is True
    assert novo.id != t.id, "a retomada apagou a historia da falha"
    assert novo.retoma_de == t.id and novo.retomada_n == 1
    assert deposito.por_id(t.id).falha is not None


def test_dois_cliques_na_mesma_retomada_convergem(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=60)
    deposito.transicionar(t.id, EstadoDoTrabalho.FAILED,
                          falha={"codigo": "x", "mensagem": "nao deu",
                                 "permanente": True},
                          exigir_operario="op-A")
    a, criado_a = deposito.retomar(t.id, tenant_id="tenant-A")
    b, criado_b = deposito.retomar(t.id, tenant_id="tenant-A")
    assert a.id == b.id and criado_a is True and criado_b is False


def test_nao_se_retoma_o_que_deu_certo(deposito: Deposito) -> None:
    t = ate_validating(deposito)
    deposito.transicionar(t.id, EstadoDoTrabalho.RENDERED,
                          recibo=recibo_valido(), exigir_operario="op-A")
    with pytest.raises(TransicaoProibida):
        deposito.retomar(t.id, tenant_id="tenant-A")


def test_retomada_cruzada_de_inquilino_e_recusada(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda(tenant="tenant-A"))
    t = deposito.reivindicar("op-A", lease_s=60)
    deposito.transicionar(t.id, EstadoDoTrabalho.FAILED,
                          falha={"codigo": "x", "mensagem": "nao deu",
                                 "permanente": True},
                          exigir_operario="op-A")
    with pytest.raises(KeyError):
        deposito.retomar(t.id, tenant_id="tenant-B")


def test_cancelar_exige_motivo_e_solta_o_lease(deposito: Deposito) -> None:
    deposito.enfileirar(encomenda())
    t = deposito.reivindicar("op-A", lease_s=60)
    with pytest.raises(ValueError):
        deposito.cancelar(t.id, tenant_id="tenant-A", por="humano", motivo="   ")
    final = deposito.cancelar(t.id, tenant_id="tenant-A", por="humano",
                              motivo="mudou o briefing")
    assert final.estado is EstadoDoTrabalho.CANCELLED
    assert final.operario is None and final.lease_ate is None
    assert final.cancelado_por == "humano"


def test_nao_se_cancela_o_que_ja_terminou(deposito: Deposito) -> None:
    t = ate_validating(deposito)
    deposito.transicionar(t.id, EstadoDoTrabalho.RENDERED,
                          recibo=recibo_valido(), exigir_operario="op-A")
    with pytest.raises(TransicaoProibida):
        deposito.cancelar(t.id, tenant_id="tenant-A", por="humano", motivo="tarde demais")


# ─────────────────────────────────────────────────────────────────────────────
# 9. tentativas
# ─────────────────────────────────────────────────────────────────────────────


def test_tentativa_e_contada_na_reivindicacao(deposito: Deposito) -> None:
    """Um trabalho que volta tres vezes por operario morto e um trabalho que
    ninguem conseguiu fazer, e em algum momento isso precisa parar."""
    deposito.enfileirar(encomenda(), max_tentativas=2)
    for _ in range(2):
        t = deposito.reivindicar("op-A", lease_s=-1)
        assert t is not None
        deposito.devolver_vencidos()
    assert deposito.reivindicar("op-A", lease_s=60) is None, "tentou uma quarta vez"
    # E o trabalho fica visivel como falho, nao desaparecido.
    (unico,) = deposito.listar(tenant_id="tenant-A")
    assert unico.estado is EstadoDoTrabalho.FAILED
    assert unico.falha["codigo"] == "tentativas_esgotadas"


# ─────────────────────────────────────────────────────────────────────────────
# 10. a porta
# ─────────────────────────────────────────────────────────────────────────────


def test_a_porta_escolhe_sqlite_por_ausencia(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CRIATIVO_DEPOSITO", raising=False)
    d = escolher_deposito(caminho_sqlite=tmp_path / "f.db")
    assert isinstance(d, DepositoDeTrabalhos)


def test_a_porta_nao_cai_de_postgres_para_sqlite(monkeypatch) -> None:
    """Fallback silencioso e um trabalho reivindicado num banco e concluido no
    outro."""
    monkeypatch.setenv("CRIATIVO_DEPOSITO", "postgres")
    monkeypatch.delenv("CRIATIVO_DEPOSITO_DSN", raising=False)
    with pytest.raises(DepositoIndisponivel):
        escolher_deposito()


def test_a_porta_recusa_deposito_desconhecido(monkeypatch) -> None:
    monkeypatch.setenv("CRIATIVO_DEPOSITO", "redis")
    with pytest.raises(DepositoIndisponivel):
        escolher_deposito()


def test_os_dois_adapters_cumprem_a_porta(deposito: Deposito) -> None:
    assert isinstance(deposito, Deposito)
