"""Um dono por instante, provado pelo contrato publico da bancada.

## O que este modulo mede, e por que ele nao repete `test_criativo_bancada.py`

O modulo vizinho ja prova posse — mas quase sempre por dentro: ele chama
`_ainda_sou_dono_da_reivindicacao` diretamente, espia a instancia de `Batimento`
com um subclasse-espiao e coloca arquivos na pasta do trabalho a mao. Sao provas
de unidade, e boas: elas matam mutantes que so aparecem quando a bandeira do
batimento e o veredito do deposito discordam.

Aqui a pergunta e outra e a lente e preta: **exercitando so a API publica**
(`enfileirar`, `reivindicar`, `devolver_vencidos`, `cancelar`, `trilha` e
`Operario.trabalhar_uma_vez`), existe algum instante em que dois operarios sao
donos do mesmo trabalho? E, quando o dono muda, o antigo consegue publicar
recibo, apagar arquivo do novo ou deixar o trabalho parecendo vivo?

A trilha append-only — que nasceu nesta branch e que nenhuma prova conferia — e
usada como testemunha: ela e a unica fonte que diz **em que ordem** a posse
mudou, e nao apenas onde ela parou.

⚠️ Nada aqui chama provider externo, Supabase ou rede. Toda escrita cai no
`tmp_path` que o pytest entrega.

## A tecnica do zumbi, e por que `lease_s=-1` nao serve mais

Desde `0efa1f7` o deposito RECUSA `claimed -> running` com lease vencido
(`LeaseVencido`), como o gatilho `criativo_render_transicao_valida` da v11_03
sempre fez. Reivindicar com `lease_s=-1` para fabricar um zumbi passou a produzir
outra coisa: o motor nem chega a rodar, o operario cai no tratamento de falha, e
a prova passaria sem exercitar um unico checkpoint de posse — tautologia verde.

A tecnica correta e a mesma de `test_criativo_bancada.py::_vencer_o_lease`: A
reivindica com lease VALIDO, comeca a produzir de verdade, e so entao o prazo
vence — escrito direto no arquivo da fila, porque o que se simula e a PASSAGEM DO
TEMPO e nao existe (nem deve existir) API de producao para vencer o lease alheio.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.criativo.bancada.contrato import (
    TERMINAIS,
    Artefato,
    Encomenda,
    EstadoDoTrabalho,
    FalhaDoMotor,
    SaidaPedida,
    TransicaoProibida,
)
from app.criativo.bancada.deposito import DepositoDeTrabalhos
from app.criativo.bancada.operario import Operario

LADO = 1080


def _encomenda(*, motor: str = "motor-ownership", seed: int = 7) -> Encomenda:
    return Encomenda(
        receita_id="receita-ownership",
        tenant_id="tenant-ownership",
        motor_slug=motor,
        modo_slug="typography_only",
        finalidade_slug="google_display",
        seed=seed,
        saidas=(SaidaPedida("1x1", LADO, LADO, "imagem", "image/png"),),
        parametros={"titulo": f"prova-{seed}", "apoio": ""},
    )


def _artefato(slot: str, arquivo: Path, conteudo: bytes) -> Artefato:
    arquivo.write_bytes(conteudo)
    return Artefato(
        slot=slot,
        caminho=str(arquivo),
        mime="image/png",
        bytes_=len(conteudo),
        sha256=hashlib.sha256(conteudo).hexdigest(),
        largura=LADO,
        altura=LADO,
    )


def _vencer_o_lease(deposito: DepositoDeTrabalhos, trabalho_id: str) -> None:
    """Faz o lease deste trabalho vencer, sem esperar o relogio.

    ⚠️ Escreve direto no arquivo da fila DE PROPOSITO — vide o cabecalho deste
    modulo. A tecnica e a mesma que `test_criativo_bancada.py` usa; ela esta
    copiada, e nao importada, porque aquele modulo pertence a outra lane nesta
    rodada e importar teste de teste ataria os dois arquivos um ao outro.
    """
    con = sqlite3.connect(deposito.caminho)
    try:
        con.execute(
            "update trabalho set lease_ate=? where id=?",
            (
                (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
                trabalho_id,
            ),
        )
        con.commit()
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────────────
# Motores de prova
# ─────────────────────────────────────────────────────────────────────────────


class _MotorRapido:
    slug = "motor-ownership"
    versao = "teste"

    def __init__(self, etiqueta: str = "novo") -> None:
        self.etiqueta = etiqueta
        self.diretorios: list[Path] = []

    def versoes_congeladas(self) -> dict[str, str]:
        return {"motor": self.etiqueta}

    def produzir(self, encomenda: Encomenda, dir_trabalho: str) -> tuple[Artefato, ...]:
        diretorio = Path(dir_trabalho)
        self.diretorios.append(diretorio)
        return (
            _artefato(
                "1x1",
                diretorio / "1x1.png",
                f"{self.etiqueta}:{encomenda.seed}".encode("ascii"),
            ),
        )


class _MotorPausado(_MotorRapido):
    """Produz o arquivo e PARA, para o teste mexer no relogio no meio."""

    def __init__(self, *, iniciou: threading.Event, liberar: threading.Event) -> None:
        super().__init__("antigo")
        self.iniciou = iniciou
        self.liberar = liberar

    def produzir(self, encomenda: Encomenda, dir_trabalho: str) -> tuple[Artefato, ...]:
        artefatos = super().produzir(encomenda, dir_trabalho)
        self.iniciou.set()
        assert self.liberar.wait(10), "o teste nao liberou o motor pausado"
        return artefatos


class _MotorFalhaTransitoria(_MotorRapido):
    def __init__(self) -> None:
        super().__init__("retry")
        self.chamadas = 0

    def produzir(self, encomenda: Encomenda, dir_trabalho: str) -> tuple[Artefato, ...]:
        self.chamadas += 1
        artefatos = super().produzir(encomenda, dir_trabalho)
        if self.chamadas == 1:
            raise FalhaDoMotor("falha transitoria depois do arquivo", permanente=False)
        return artefatos


class _MotorFalhaPermanente:
    slug = "motor-ownership"
    versao = "teste"

    def versoes_congeladas(self) -> dict[str, str]:
        return {}

    def produzir(self, *_: Any) -> tuple[Artefato, ...]:
        raise FalhaDoMotor("insumo recusado pelo motor", permanente=True)


class _MotorCaiDepoisDeRenderizar(_MotorRapido):
    def produzir(self, encomenda: Encomenda, dir_trabalho: str) -> tuple[Artefato, ...]:
        super().produzir(encomenda, dir_trabalho)
        raise RuntimeError("processo caiu entre render e publicacao")


# ─────────────────────────────────────────────────────────────────────────────
# A testemunha: a trilha append-only
# ─────────────────────────────────────────────────────────────────────────────

_CLAIMED = EstadoDoTrabalho.CLAIMED.value
_QUEUED = EstadoDoTrabalho.QUEUED.value
_TERMINAIS = {e.value for e in TERMINAIS}


def _posse_pela_trilha(trilha: list[dict[str, Any]]) -> list[tuple[str, int, int]]:
    """Reconstroi os intervalos de posse a partir da trilha, e reprova sobreposicao.

    Devolve `(dono, indice_de_entrada, indice_de_saida)` por segmento. Se dois
    donos coexistirem em qualquer instante — um `-> claimed` sem que o anterior
    tenha voltado para a fila ou terminado —, isto levanta `AssertionError`, que
    e o enunciado literal do aceite: um owner por instante.
    """
    segmentos: list[tuple[str, int, int]] = []
    dono: str | None = None
    desde = -1
    for i, passo in enumerate(trilha):
        para, por = passo["para"], passo["por"]
        if para == _CLAIMED:
            assert dono is None, (
                f"passo {i}: `{por}` reivindicou enquanto `{dono}` ainda era dono"
            )
            dono, desde = por, i
        elif para == _QUEUED or para in _TERMINAIS:
            if dono is not None:
                segmentos.append((dono, desde, i))
            dono = None
        else:
            assert dono is not None, f"passo {i}: `{para}` sem dono registrado"
            assert por in (None, dono), (
                f"passo {i}: `{por}` avancou para `{para}` num trabalho de `{dono}`"
            )
    if dono is not None:
        segmentos.append((dono, desde, len(trilha)))
    return segmentos


# ═══════════════════════════════════════════════════════════════════════════
# 1. Disputa concorrente
# ═══════════════════════════════════════════════════════════════════════════


def test_disputa_concorrente_tem_um_unico_dono_por_trabalho(tmp_path: Path):
    """Duas threads largam juntas sobre o mesmo trabalho: exatamente uma vence.

    ⚠️ 25 rodadas, e nao uma. Uma rodada unica passa mesmo com a exclusao mutua
    quebrada: o intervalo entre o `select` e o `update` e de microssegundos, e
    duas threads raramente caem nele por acaso. A `Barrier` empurra as duas para
    a MESMA janela; a repeticao e o que transforma "nao aconteceu" em evidencia.
    """
    for rodada in range(25):
        deposito = DepositoDeTrabalhos(tmp_path / f"fila-{rodada}.db")
        trabalho, _ = deposito.enfileirar(_encomenda(seed=1000 + rodada))
        largada = threading.Barrier(2)

        def disputar(nome: str, _d=deposito, _b=largada):
            _b.wait(timeout=10)
            return _d.reivindicar(nome, lease_s=30)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futuros = [
                pool.submit(disputar, "worker-a"),
                pool.submit(disputar, "worker-b"),
            ]
            resultados = [f.result(timeout=10) for f in futuros]

        vencedores = [r for r in resultados if r is not None]
        assert len(vencedores) == 1, f"rodada {rodada}: {resultados}"
        assert sum(r is None for r in resultados) == 1, f"rodada {rodada}"

        vencedor = vencedores[0]
        assert vencedor.id == trabalho.id
        assert vencedor.operario in {"worker-a", "worker-b"}
        assert vencedor.tentativa == 1, "a tentativa do perdedor foi contada"
        assert vencedor.estado is EstadoDoTrabalho.CLAIMED
        assert vencedor.lease_ate is not None
        assert vencedor.batimento_em is not None
        assert vencedor.vivo is True

        observado = deposito.por_id(trabalho.id)
        assert observado is not None
        assert observado.operario == vencedor.operario
        assert observado.tentativa == vencedor.tentativa

        # A trilha nao pode registrar o claim do perdedor: um claim recusado nao
        # e um evento de posse, e escreve-lo faria a auditoria ver dois donos.
        trilha = deposito.trilha(trabalho.id)
        claims = [p for p in trilha if p["para"] == _CLAIMED]
        assert len(claims) == 1, f"rodada {rodada}: {trilha}"
        assert claims[0]["por"] == vencedor.operario
        assert _posse_pela_trilha(trilha) == [(vencedor.operario, 0, 1)]


def test_a_trilha_registra_um_unico_dono_por_instante_na_troca_de_posse(
    tmp_path: Path,
):
    """O ciclo inteiro A-perde/B-assume, lido pela trilha.

    O estado final ja era conferido por outras provas. O que so a trilha diz e a
    ORDEM: se a posse de B tivesse comecado antes de a de A terminar, o estado
    final seria o mesmo e a auditoria nao teria como saber.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    trabalho, _ = deposito.enfileirar(_encomenda())

    a = deposito.reivindicar("worker-a", lease_s=60)
    assert a is not None
    deposito.transicionar(trabalho.id, EstadoDoTrabalho.RUNNING, exigir_operario="worker-a")

    _vencer_o_lease(deposito, trabalho.id)
    assert deposito.devolver_vencidos() == 1

    b = deposito.reivindicar("worker-b", lease_s=60)
    assert b is not None and b.tentativa == 2

    trilha = deposito.trilha(trabalho.id)
    assert [(p["de"], p["para"], p["por"]) for p in trilha] == [
        (_QUEUED, _CLAIMED, "worker-a"),
        (_CLAIMED, "running", "worker-a"),
        ("running", _QUEUED, "worker-a"),
        (_QUEUED, _CLAIMED, "worker-b"),
    ]
    assert [p["motivo"] for p in trilha][2] == "lease_vencido"

    segmentos = _posse_pela_trilha(trilha)
    assert [dono for dono, _, _ in segmentos] == ["worker-a", "worker-b"]
    # Os intervalos nao se tocam: A sai no passo 2, B entra no passo 3.
    assert segmentos[0][2] <= segmentos[1][1]


# ═══════════════════════════════════════════════════════════════════════════
# 2. O operario atrasado
# ═══════════════════════════════════════════════════════════════════════════


def test_operario_atrasado_nao_publica_nem_apaga_o_diretorio_do_novo_dono(
    tmp_path: Path,
):
    """Dois operarios REAIS, ponta a ponta, dividindo a mesma raiz de trabalho.

    A prova vizinha (`_cenario_de_perda`) coloca um arquivo na pasta a mao para
    representar o novo dono. Aqui B e um `Operario` de verdade que reivindica,
    produz, valida e assina — entao o que A poderia destruir e um artefato
    apontado por um recibo real, que e o dano que importa em producao.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    trabalho, _ = deposito.enfileirar(_encomenda())
    raiz = tmp_path / "trabalhos"  # A e B compartilham a raiz, como em producao

    iniciou, liberar = threading.Event(), threading.Event()
    motor_antigo = _MotorPausado(iniciou=iniciou, liberar=liberar)
    motor_novo = _MotorRapido("novo")

    antigo = Operario(
        deposito, {"motor-ownership": motor_antigo}, raiz, nome="worker-antigo",
        lease_s=60,
    )
    novo = Operario(
        deposito, {"motor-ownership": motor_novo}, raiz, nome="worker-novo",
        lease_s=60,
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        futuro_antigo = pool.submit(antigo.trabalhar_uma_vez)
        assert iniciou.wait(10), "o worker antigo nao chegou a produzir arquivo"
        assert motor_antigo.diretorios and motor_antigo.diretorios[0].is_dir()

        # ⚠️ O prazo vence AGORA, com o motor de A ja rodando. Ver o cabecalho.
        _vencer_o_lease(deposito, trabalho.id)
        assert deposito.devolver_vencidos() == 1

        feito = novo.trabalhar_uma_vez()
        assert feito is not None
        assert feito.estado is EstadoDoTrabalho.RENDERED
        assert feito.recibo is not None
        assert feito.recibo["produzido_por"] == "worker-novo"
        arquivo_do_novo = Path(feito.recibo["artefatos"][0]["caminho"])
        assert arquivo_do_novo.is_file()
        assert arquivo_do_novo.read_bytes().startswith(b"novo:")

        liberar.set()
        resultado_antigo = futuro_antigo.result(timeout=15)

    final = deposito.por_id(trabalho.id)
    assert final is not None
    assert final.estado is EstadoDoTrabalho.RENDERED
    assert final.operario is None, "trabalho terminal nao fica com dono"
    assert final.recibo is not None
    assert final.recibo["produzido_por"] == "worker-novo", (
        "o operario atrasado gravou recibo por cima do trabalho do novo dono"
    )
    assert arquivo_do_novo.is_file(), "o dono antigo apagou o arquivo do novo dono"
    assert arquivo_do_novo.read_bytes().startswith(b"novo:")

    # A saiu de cena levando so o que era dele, e nao inventou estado nenhum.
    assert resultado_antigo is not None
    assert resultado_antigo.recibo == final.recibo
    assert motor_antigo.diretorios[0] != motor_novo.diretorios[0]
    assert not motor_antigo.diretorios[0].exists(), (
        "o diretorio da reivindicacao perdida vazou no disco"
    )
    assert motor_novo.diretorios[0].is_dir()
    assert motor_antigo.diretorios[0].name.startswith("t1-worker-antigo")
    assert motor_novo.diretorios[0].name.startswith("t2-worker-novo")

    _posse_pela_trilha(deposito.trilha(trabalho.id))


def test_claim_antigo_de_MESMO_NOME_nao_conclui_por_cima_da_reivindicacao_nova(
    tmp_path: Path,
):
    """O nome do worker nao e a posse; a REIVINDICACAO e.

    ⚠️ O caso e sutil e o modo de falha e silencioso: quando o mesmo operario
    reivindica de novo, `operario` no banco volta a ser o nome do zumbi. Uma
    guarda que comparasse so o nome deixaria o zumbi se reconhecer como dono e
    concluir apontando para o diretorio da tentativa VELHA — recibo valido,
    arquivo inexistente.

    Ponta a ponta e de proposito: a prova vizinha chama
    `_ainda_sou_dono_da_reivindicacao` diretamente, e uma guarda que existe mas
    nao e consultada no caminho real passaria naquela e cairia nesta.

    ⚠️ E o novo dono precisa estar AINDA PRODUZINDO quando o zumbi acorda. A
    primeira versao desta prova deixava o novo dono concluir antes: ai o zumbi
    encontrava o trabalho em `rendered`, a transicao caia pelo mapa de estados e
    a guarda de posse nem era exercitada. Medido: com
    `_ainda_sou_dono_da_reivindicacao` trocada por uma comparacao SO de nome, as
    9 provas deste modulo continuavam verdes — mutante vivo, prova decorativa.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    trabalho, _ = deposito.enfileirar(_encomenda())
    raiz = tmp_path / "trabalhos"

    iniciou_zumbi, liberar_zumbi = threading.Event(), threading.Event()
    iniciou_vivo, liberar_vivo = threading.Event(), threading.Event()
    motor_zumbi = _MotorPausado(iniciou=iniciou_zumbi, liberar=liberar_zumbi)
    motor_vivo = _MotorPausado(iniciou=iniciou_vivo, liberar=liberar_vivo)
    motor_vivo.etiqueta = "novo"

    zumbi = Operario(deposito, {"motor-ownership": motor_zumbi}, raiz, nome="op-X",
                     lease_s=60)
    vivo = Operario(deposito, {"motor-ownership": motor_vivo}, raiz, nome="op-X",
                    lease_s=60)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futuro_zumbi = pool.submit(zumbi.trabalhar_uma_vez)
        assert iniciou_zumbi.wait(10), "o zumbi nao chegou a produzir"

        _vencer_o_lease(deposito, trabalho.id)
        assert deposito.devolver_vencidos() == 1

        # MESMO nome, outra reivindicacao — e ele ainda esta produzindo quando o
        # zumbi acorda, que e a janela em que o dano seria possivel.
        futuro_vivo = pool.submit(vivo.trabalhar_uma_vez)
        assert iniciou_vivo.wait(10), "o novo dono nao chegou a produzir"
        em_producao = deposito.por_id(trabalho.id)
        assert em_producao is not None
        assert em_producao.operario == "op-X" and em_producao.tentativa == 2
        assert em_producao.vivo is True

        liberar_zumbi.set()
        futuro_zumbi.result(timeout=15)
        liberar_vivo.set()
        feito = futuro_vivo.result(timeout=15)

    assert feito is not None
    assert feito.estado is EstadoDoTrabalho.RENDERED, (
        "o zumbi de mesmo nome atravessou a conclusao do dono atual"
    )
    assert feito.recibo["produzido_por"] == "op-X"

    final = deposito.por_id(trabalho.id)
    assert final is not None
    caminho_do_recibo = Path(final.recibo["artefatos"][0]["caminho"])
    assert caminho_do_recibo.is_file(), (
        "o recibo aponta para um arquivo que nao existe — o zumbi concluiu"
    )
    assert caminho_do_recibo.parent.name == "t2-op-X", caminho_do_recibo
    assert caminho_do_recibo.read_bytes().startswith(b"novo:")
    assert not motor_zumbi.diretorios[0].exists()

    trilha = deposito.trilha(trabalho.id)
    assert [p["para"] for p in trilha].count("rendered") == 1
    _posse_pela_trilha(trilha)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Retry, cancelamento, falha e crash
# ═══════════════════════════════════════════════════════════════════════════


def test_retry_transitorio_usa_diretorio_de_reivindicacao_proprio(tmp_path: Path):
    """Cada tentativa tem pasta propria, e o motivo da devolucao vai a TRILHA.

    ⚠️ A versao colhida desta prova conferia `trabalho.falha["permanente"]` na
    volta para a fila. Desde `0efa1f7` isso e falso por design: o CHECK
    `criativo_render_job_falha_coerente` diz que `falha` na linha significa "este
    trabalho terminou mal", e um trabalho devolvido a fila NAO terminou. O motivo
    da tentativa 1 mora na trilha, que guarda TODAS as passagens em vez de so a
    ultima.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    motor = _MotorFalhaTransitoria()
    operario = Operario(
        deposito, {"motor-ownership": motor}, tmp_path / "trabalhos",
        nome="worker-retry",
    )
    trabalho, _ = deposito.enfileirar(_encomenda(), max_tentativas=3)

    primeira = operario.trabalhar_uma_vez()
    assert primeira is not None
    assert primeira.estado is EstadoDoTrabalho.QUEUED
    assert primeira.falha is None, "trabalho na fila nao carrega falha na linha"
    assert primeira.operario is None
    assert primeira.lease_ate is None
    assert primeira.terminado_em is None, "voltar para a fila nao e terminar"
    assert len(motor.diretorios) == 1
    assert motor.diretorios[0].name.startswith("t1-worker-retry")
    assert not motor.diretorios[0].exists()

    devolucao = [p for p in deposito.trilha(trabalho.id) if p["para"] == _QUEUED][-1]
    assert devolucao["de"] == "running"
    assert devolucao["por"] == "worker-retry"
    assert devolucao["motivo"] == "motor_recusou"

    segunda = operario.trabalhar_uma_vez()
    assert segunda is not None
    assert segunda.estado is EstadoDoTrabalho.RENDERED
    assert len(motor.diretorios) == 2
    assert motor.diretorios[1].name.startswith("t2-worker-retry")
    assert motor.diretorios[0] != motor.diretorios[1]
    assert Path(segunda.recibo["artefatos"][0]["caminho"]).parent == motor.diretorios[1]

    _posse_pela_trilha(deposito.trilha(trabalho.id))


def test_cancelamento_nao_transfere_posse_implicitamente(tmp_path: Path):
    """Cancelar solta o dono — e nao entrega o trabalho a ninguem."""
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    trabalho, _ = deposito.enfileirar(_encomenda())
    claim = deposito.reivindicar("worker-cancelado", lease_s=60)
    assert claim is not None

    cancelado = deposito.cancelar(
        trabalho.id,
        tenant_id="tenant-ownership",
        por="operador",
        motivo="pedido substituido",
    )
    assert cancelado.estado is EstadoDoTrabalho.CANCELLED
    assert cancelado.operario is None
    assert cancelado.lease_ate is None
    assert cancelado.vivo is False
    assert cancelado.terminado_em is not None

    # Ninguem herda: o trabalho nao volta para a fila nem fica reivindicavel.
    assert deposito.reivindicar("outro-worker") is None
    assert deposito.bater(trabalho.id, operario="worker-cancelado") is False

    with pytest.raises(TransicaoProibida):
        deposito.transicionar(
            trabalho.id,
            EstadoDoTrabalho.RUNNING,
            exigir_operario="worker-cancelado",
        )

    trilha = deposito.trilha(trabalho.id)
    assert (trilha[-1]["de"], trilha[-1]["para"]) == (_CLAIMED, "cancelled")
    assert trilha[-1]["por"] == "operador"
    assert trilha[-1]["motivo"] == "pedido substituido"
    assert _posse_pela_trilha(trilha) == [("worker-cancelado", 0, 1)]


def test_falha_permanente_nao_deixa_trabalho_parecendo_vivo(tmp_path: Path):
    """Ausencia de dono e ausencia de lease — nao "provavelmente ainda rodando"."""
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    operario = Operario(
        deposito,
        {"motor-ownership": _MotorFalhaPermanente()},
        tmp_path / "trabalhos",
        nome="worker-falha",
    )
    trabalho, _ = deposito.enfileirar(_encomenda(), max_tentativas=3)

    falho = operario.trabalhar_uma_vez()
    assert falho is not None
    assert falho.estado is EstadoDoTrabalho.FAILED
    assert falho.falha["codigo"] == "motor_recusou"
    assert falho.falha["permanente"] is True
    assert falho.operario is None
    assert falho.lease_ate is None
    assert falho.vivo is False
    assert falho.terminado_em is not None
    assert falho.tentativa == 1, "falha permanente nao consome as outras tentativas"

    assert deposito.reivindicar("outro-worker") is None
    assert deposito.bater(trabalho.id) is False
    _posse_pela_trilha(deposito.trilha(trabalho.id))


def test_crash_entre_render_e_recibo_e_reconciliavel_por_outro_operario(
    tmp_path: Path,
):
    """O processo cai depois de escrever o arquivo e antes de assinar o recibo.

    O invariante nao e "o arquivo sobrevive" — ele NAO deve sobreviver, porque
    nenhum recibo o aponta e um arquivo orfao com nome de slot e exatamente o que
    o proximo dono confundiria com a propria peca. O invariante e: o trabalho
    volta a ser reivindicavel, sem dono, sem lease e sem recibo, e outro operario
    o leva ao fim.
    """
    deposito = DepositoDeTrabalhos(tmp_path / "fila.db")
    motor_quebra = _MotorCaiDepoisDeRenderizar("crash")
    quebra = Operario(
        deposito, {"motor-ownership": motor_quebra}, tmp_path / "trabalhos",
        nome="worker-crash",
    )
    trabalho, _ = deposito.enfileirar(_encomenda(), max_tentativas=3)

    interrompido = quebra.trabalhar_uma_vez()
    assert interrompido is not None
    assert interrompido.id == trabalho.id
    assert interrompido.estado is EstadoDoTrabalho.QUEUED
    assert interrompido.recibo is None
    assert interrompido.operario is None
    assert interrompido.lease_ate is None
    assert interrompido.falha is None, "trabalho na fila nao carrega falha na linha"
    assert not motor_quebra.diretorios[0].exists()

    queda = [p for p in deposito.trilha(trabalho.id) if p["para"] == _QUEUED][-1]
    assert queda["motivo"] == "falha_inesperada"
    assert queda["por"] == "worker-crash"

    recupera = Operario(
        deposito, {"motor-ownership": _MotorRapido("recuperado")},
        tmp_path / "trabalhos", nome="worker-recupera",
    )
    recuperado = recupera.trabalhar_uma_vez()
    assert recuperado is not None
    assert recuperado.id == trabalho.id
    assert recuperado.tentativa == 2
    assert recuperado.estado is EstadoDoTrabalho.RENDERED
    assert recuperado.recibo["produzido_por"] == "worker-recupera"
    assert Path(recuperado.recibo["artefatos"][0]["caminho"]).is_file()

    segmentos = _posse_pela_trilha(deposito.trilha(trabalho.id))
    assert [dono for dono, _, _ in segmentos] == ["worker-crash", "worker-recupera"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. A testemunha tambem precisa poder reprovar
# ═══════════════════════════════════════════════════════════════════════════


def test_a_leitura_da_trilha_acusa_dois_donos_simultaneos():
    """Mata o mutante `_posse_pela_trilha` sempre passa.

    Um verificador que nunca reprova nao verifica nada — e todas as provas acima
    o chamam. Esta e a unica trilha FABRICADA do modulo, e ela existe para provar
    que a testemunha sabe dizer nao.
    """
    trilha_sa = [
        {"de": _QUEUED, "para": _CLAIMED, "por": "a", "motivo": None, "em": "1"},
        {"de": _CLAIMED, "para": _QUEUED, "por": "a", "motivo": "lease_vencido", "em": "2"},
        {"de": _QUEUED, "para": _CLAIMED, "por": "b", "motivo": None, "em": "3"},
    ]
    assert [dono for dono, _, _ in _posse_pela_trilha(trilha_sa)] == ["a", "b"]

    trilha_doente = [
        {"de": _QUEUED, "para": _CLAIMED, "por": "a", "motivo": None, "em": "1"},
        {"de": _QUEUED, "para": _CLAIMED, "por": "b", "motivo": None, "em": "2"},
    ]
    with pytest.raises(AssertionError, match="ainda era dono"):
        _posse_pela_trilha(trilha_doente)

    trilha_intrusa = [
        {"de": _QUEUED, "para": _CLAIMED, "por": "a", "motivo": None, "em": "1"},
        {"de": _CLAIMED, "para": "running", "por": "b", "motivo": None, "em": "2"},
    ]
    with pytest.raises(AssertionError, match="num trabalho de"):
        _posse_pela_trilha(trilha_intrusa)
