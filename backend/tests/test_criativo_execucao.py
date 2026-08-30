"""As provas da ORQUESTRAÇÃO — a camada que a auditoria adversarial pegou nua.

A revisão de 27/08/2026 encontrou cinco defeitos aqui, três deles críticos, e
apontou a causa: `test_criativo_estudio.py` cobria domínio, armazenamento,
assinador, enquadramento, motor e apresentação, e **zero** linhas do executor.
Criação, retry, cancelamento, fechamento e agregação não tinham um teste.

Este arquivo fecha esse buraco. Cada teste abaixo nomeia o defeito que ele
existe para impedir de voltar, e o repositório é um dublê em memória que aplica
as MESMAS invariantes que a migration aplica no banco: sem isso, um teste verde
aqui provaria só que o Python não estourou, não que o banco aceitaria a escrita.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.criativo import dominio
from app.criativo.armazenamento import ArmazenamentoLocal, Assinador
from app.criativo.execucao import Executor, TransicaoInvalida
from app.criativo.persistencia import ConflitoDeChave
from volc_ads.criativo.porta import (
    ArquivoGerado,
    MotorIndisponivel,
    PedidoRecusado,
    RespostaDoMotor,
)

SEGREDO = "segredo-de-teste-com-mais-de-16-caracteres"


# ═══════════════════════════════════════════════════════════════════════════
# Dublês
# ═══════════════════════════════════════════════════════════════════════════


class RepoFalso:
    """Repositório em memória que aplica as CHECKs que importam.

    ⚠️ As três guardas replicadas abaixo não são decoração. O defeito C1 da
    auditoria (cancelar um lote com peça falhada quebrava o banco) só é
    reproduzível num dublê que RECUSE a escrita incoerente. Um dublê permissivo
    teria deixado o teste passar exatamente no caso que quebrava em produção.
    """

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.briefings: dict[str, dict[str, Any]] = {}
        self.projetos: dict[str, dict[str, Any]] = {}
        self.renditions: dict[tuple[str, str], dict[str, Any]] = {}
        self.masters: list[dict[str, Any]] = []
        self.eventos: list[dict[str, Any]] = []
        self.por_chave: dict[str, str] = {}
        self._n = 0
        self.conflito_de_master = False

    def _id(self, p: str) -> str:
        self._n += 1
        return f"{p}{self._n}"

    # ── guardas do banco, replicadas ─────────────────────────────────────────

    @staticmethod
    def _conferir_job(linha: dict[str, Any]) -> None:
        estado = linha.get("estado")
        # criativo_job_falha_coerente
        if (estado == "failed") != (linha.get("falha") is not None):
            raise AssertionError(
                f"CHECK criativo_job_falha_coerente: estado={estado} "
                f"falha={'presente' if linha.get('falha') else 'ausente'}"
            )
        # criativo_job_ordem_temporal
        if linha.get("terminado_em") and not linha.get("iniciado_em"):
            raise AssertionError("CHECK criativo_job_ordem_temporal: fim sem início")
        # criativo_job_terminal_carimbado
        if estado in ("succeeded", "partial", "failed", "cancelled") and not linha.get(
            "terminado_em"
        ):
            raise AssertionError("CHECK criativo_job_terminal_carimbado")

    @staticmethod
    def _conferir_rendition(linha: dict[str, Any]) -> None:
        if linha["estado"] == "pronta" and not (
            linha.get("storage_chave") and linha.get("content_hash") and linha.get("master_id")
        ):
            raise AssertionError("CHECK criativo_rendition_pronta_tem_arquivo")
        if linha["estado"] == "falhou" and not (
            linha.get("erro_codigo") and linha.get("erro_em") and linha.get("erro_permanente") is not None
        ):
            raise AssertionError("CHECK criativo_rendition_falhou_tem_motivo")

    # ── API usada pelo executor ──────────────────────────────────────────────

    async def criar_projeto(self, titulo, objetivo, brand_pack_id, dono_id, origem="standalone"):
        linha = {"id": self._id("p"), "titulo": titulo}
        self.projetos[linha["id"]] = linha
        return linha

    async def criar_briefing(self, linha):
        linha = {**linha, "id": self._id("b")}
        self.briefings[linha["id"]] = linha
        return linha

    async def buscar_briefing(self, bid):
        return self.briefings.get(bid)

    async def buscar_projeto(self, pid):
        return self.projetos.get(pid)

    async def job_por_chave(self, chave):
        jid = self.por_chave.get(chave)
        return self.jobs.get(jid) if jid else None

    async def criar_job_idempotente(self, linha):
        chave = linha["idempotency_key"]
        if chave in self.por_chave:
            return self.jobs[self.por_chave[chave]], False
        linha = {**linha, "id": self._id("j"), "tentativa": 1, "criado_em": "2026-01-01"}
        self._conferir_job(linha)
        self.jobs[linha["id"]] = linha
        self.por_chave[chave] = linha["id"]
        return linha, True

    async def buscar_job(self, jid):
        return self.jobs.get(jid)

    async def atualizar_job(self, jid, campos):
        atual = dict(self.jobs[jid])
        atual.update(campos)
        self._conferir_job(atual)
        self.jobs[jid] = atual
        return atual

    async def criar_renditions(self, linhas):
        saida = []
        for l in linhas:
            l = {**l, "id": self._id("r")}
            self.renditions[(l["job_id"], l["slot"])] = l
            saida.append(l)
        return saida

    async def renditions_do_job(self, jid):
        return [v for (j, _), v in sorted(self.renditions.items()) if j == jid]

    async def atualizar_rendition(self, jid, slot, campos):
        atual = dict(self.renditions[(jid, slot)])
        atual.update(campos)
        self._conferir_rendition(atual)
        self.renditions[(jid, slot)] = atual
        return atual

    async def criar_master(self, linha):
        if self.conflito_de_master:
            raise ConflitoDeChave()
        linha = {**linha, "id": self._id("m")}
        self.masters.append(linha)
        return linha

    async def masters_do_job(self, jid):
        return [m for m in self.masters if m["job_id"] == jid]

    async def registrar_evento(self, jid, fase, mensagem=None, *, percentual=None,
                               slot=None, detalhe=None):
        e = {"seq": len(self.eventos) + 1, "job_id": jid, "fase": fase,
             "mensagem": mensagem, "percentual": percentual, "slot": slot}
        self.eventos.append(e)
        return e

    async def ultimo_seq(self, jid):
        return len(self.eventos)


class MotorFalso:
    """Motor determinístico que erra sob encomenda, por slot."""

    nome = "falso:teste"
    versao = "1.0.0"
    configurado = True

    def __init__(self, falhar_em: set[str] | None = None, erro=None) -> None:
        self.falhar_em = falhar_em or set()
        self.erro = erro or PedidoRecusado("recusado por política")
        self.chamadas: list[str] = []

    def solicitar_geracao(self, pedido):
        slot = pedido.referencia.split("/")[-1]
        self.chamadas.append(slot)
        if slot in self.falhar_em:
            raise self.erro
        return f"id-{slot}"

    def receber(self, pid):
        slot = pid.removeprefix("id-")
        png = b"\x89PNG\r\n\x1a\n" + slot.encode() + b"\x00" * 64
        return RespostaDoMotor(
            pedido=pid,
            arquivos=(ArquivoGerado(conteudo=png, mime="image/png", largura=10,
                                    altura=10, metadados={"enquadramento": "nativo"}),),
        )


def _executor(tmp_path, motor=None, repo=None):
    return Executor(repo or RepoFalso(), ArmazenamentoLocal(tmp_path),
                    motor or MotorFalso(), Assinador(SEGREDO))


PEDIDO = {
    "projeto_titulo": "Prova", "objetivo": "o", "mensagem": "m",
    "audiencia": None, "brand_pack_id": None, "modo": "full_llm",
    "slots": ["1x1", "4x5", "9x16"], "destinos_pretendidos": [],
}


# ═══════════════════════════════════════════════════════════════════════════
# Criação e idempotência
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_criar_job_grava_uma_peca_por_formato_e_nao_gera_nada(tmp_path):
    ex = _executor(tmp_path)
    job, criado = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    assert criado and job["estado"] == "queued"
    rs = await ex.repo.renditions_do_job(job["id"])
    assert [r["slot"] for r in rs] == ["1x1", "4x5", "9x16"]
    assert all(r["estado"] == "pendente" for r in rs)
    assert ex.motor.chamadas == [], "criar não pode chamar o motor: o POST não espera o render"


@pytest.mark.asyncio
async def test_reenvio_reconhecido_nao_cria_projeto_nem_briefing_orfaos(tmp_path):
    """Cada duplo clique criava um projeto e um briefing sem job."""
    ex = _executor(tmp_path)
    await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    _, criado = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    assert criado is False
    assert len(ex.repo.projetos) == 1
    assert len(ex.repo.briefings) == 1


@pytest.mark.asyncio
async def test_formato_desconhecido_recusa_antes_de_gravar(tmp_path):
    ex = _executor(tmp_path)
    with pytest.raises(dominio.SlotDesconhecido):
        await ex.criar_job_de_imagem({**PEDIDO, "slots": ["42x42"]}, "u1")
    assert ex.repo.jobs == {} and ex.repo.projetos == {}


# ═══════════════════════════════════════════════════════════════════════════
# Execução e falha parcial
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_lote_inteiro_bom_fecha_como_succeeded(tmp_path):
    ex = _executor(tmp_path)
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    await ex._executar(job["id"])
    assert ex.repo.jobs[job["id"]]["estado"] == "succeeded"
    assert len(ex.repo.masters) == 3
    assert ex.repo.jobs[job["id"]]["falha"] is None


@pytest.mark.asyncio
async def test_uma_peca_recusada_nao_derruba_as_outras(tmp_path):
    ex = _executor(tmp_path, MotorFalso(falhar_em={"4x5"}))
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    await ex._executar(job["id"])
    rs = {r["slot"]: r for r in await ex.repo.renditions_do_job(job["id"])}
    assert rs["1x1"]["estado"] == "pronta" and rs["9x16"]["estado"] == "pronta"
    assert rs["4x5"]["estado"] == "falhou"
    assert rs["4x5"]["erro_permanente"] is True
    assert ex.repo.jobs[job["id"]]["estado"] == "partial"
    assert len(ex.repo.masters) == 2


@pytest.mark.asyncio
async def test_nenhuma_peca_produzida_fecha_como_failed_com_falha_tipada(tmp_path):
    ex = _executor(tmp_path, MotorFalso(falhar_em={"1x1", "4x5", "9x16"}))
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    await ex._executar(job["id"])
    linha = ex.repo.jobs[job["id"]]
    assert linha["estado"] == "failed"
    assert linha["falha"]["codigo"] and linha["falha"]["mensagem"]


@pytest.mark.asyncio
async def test_o_erro_do_motor_chega_sanitizado_na_peca(tmp_path):
    ex = _executor(tmp_path, MotorFalso(
        falhar_em={"1x1"}, erro=PedidoRecusado("quebrou em /Users/mac/segredo.py")))
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    await ex._executar(job["id"])
    rs = {r["slot"]: r for r in await ex.repo.renditions_do_job(job["id"])}
    assert "/Users/" not in rs["1x1"]["erro_mensagem"]


@pytest.mark.asyncio
async def test_nenhum_evento_carrega_percentual_inventado(tmp_path):
    ex = _executor(tmp_path)
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    await ex._executar(job["id"])
    assert all(e["percentual"] is None for e in ex.repo.eventos)


# ═══════════════════════════════════════════════════════════════════════════
# Retry — o defeito que cobrava duas vezes
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_retry_so_toca_a_peca_que_faltou(tmp_path):
    ex = _executor(tmp_path, MotorFalso(falhar_em={"4x5"}))
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    await ex._executar(job["id"])
    ex.motor.falhar_em = set()
    ex.motor.chamadas.clear()
    await ex._executar(job["id"])
    assert ex.motor.chamadas == ["4x5"], "retry regerou peça já pronta e cobrou de novo"
    assert ex.repo.jobs[job["id"]]["estado"] == "succeeded"
    assert len(ex.repo.masters) == 3


@pytest.mark.asyncio
async def test_retry_num_job_concluido_e_recusado(tmp_path):
    ex = _executor(tmp_path)
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    await ex._executar(job["id"])
    with pytest.raises(TransicaoInvalida):
        await ex.retentar(job["id"])


@pytest.mark.asyncio
async def test_conflito_de_master_reaproveita_o_arquivo_do_vencedor(tmp_path):
    """C3: o perdedor gravava o hash DA SUA imagem sobre o master do vencedor.

    O resultado era uma peça com duas identidades: a biblioteca mostrava um
    arquivo e a página do job mostrava outro, com os hashes discordando em
    silêncio e nenhum erro em lugar nenhum.
    """
    repo = RepoFalso()
    ex = _executor(tmp_path, repo=repo)
    job, _ = await ex.criar_job_de_imagem({**PEDIDO, "slots": ["1x1"]}, "u1")
    await ex._executar(job["id"])
    vencedor = repo.masters[0]

    # Segunda execução do mesmo slot: o banco recusa o master duplicado.
    await repo.atualizar_rendition(job["id"], "1x1", {"estado": "pendente"})
    repo.conflito_de_master = True
    await ex._executar(job["id"])

    r = repo.renditions[(job["id"], "1x1")]
    assert r["content_hash"] == vencedor["content_hash"]
    assert r["storage_chave"] == vencedor["storage_chave"]
    assert r["master_id"] == vencedor["id"]
    assert len(repo.masters) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Cancelamento — o defeito que acusava o sistema de quebrar
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cancelar_registra_o_pedido_e_ainda_nao_a_confirmacao(tmp_path):
    ex = _executor(tmp_path)
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    atualizado = await ex.cancelar(job["id"])
    assert atualizado["cancelado_pedido_em"] is not None
    assert atualizado.get("cancelado_em") is None, "pedido e confirmação são fatos diferentes"


@pytest.mark.asyncio
async def test_cancelar_lote_que_ja_tem_peca_falhada_nao_acusa_falha_interna(tmp_path):
    """C1, crítico: o PATCH de cancelamento omitia `falha` e a CHECK abortava.

    O operador clicava em interromper e o registro dizia "A produção foi
    interrompida por uma falha interna". Cancelar não é falhar.
    """
    ex = _executor(tmp_path, MotorFalso(falhar_em={"1x1"}))
    job, _ = await ex.criar_job_de_imagem({**PEDIDO, "slots": ["1x1", "4x5"]}, "u1")
    await ex.repo.atualizar_rendition(job["id"], "1x1", {
        "estado": "falhou", "erro_codigo": "MOTOR.recusado", "erro_mensagem": "x",
        "erro_permanente": True, "erro_em": "2026-01-01T00:00:00Z"})
    await ex.repo.atualizar_job(job["id"], {"estado": "running",
                                            "iniciado_em": "2026-01-01T00:00:00Z"})
    await ex._confirmar_cancelamento(job["id"])

    linha = ex.repo.jobs[job["id"]]
    assert linha["estado"] == "failed"
    assert linha["falha"] is not None, "failed sem falha viola a CHECK"
    assert linha["falha"]["codigo"] != "JOB.interrompido", "cancelar virou 'falha interna'"
    assert linha["cancelado_em"] is not None


@pytest.mark.asyncio
async def test_cancelar_job_concluido_e_recusado(tmp_path):
    ex = _executor(tmp_path)
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    await ex._executar(job["id"])
    with pytest.raises(TransicaoInvalida):
        await ex.cancelar(job["id"])


# ═══════════════════════════════════════════════════════════════════════════
# Fechamento — os defeitos que deixavam o job irrecuperável
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_peca_presa_em_gerando_nao_deixa_o_job_como_tijolo(tmp_path):
    """C6: o job fechava como `running` COM `terminado_em`, e virava irrecuperável.

    Retry recusava (`running` não é retentável), cancelar gravava um pedido que
    ninguém confirmava, e a Home listava o job em "Em andamento" para sempre.
    """
    ex = _executor(tmp_path)
    job, _ = await ex.criar_job_de_imagem({**PEDIDO, "slots": ["1x1", "4x5"]}, "u1")
    await ex.repo.atualizar_job(job["id"], {"estado": "running",
                                            "iniciado_em": "2026-01-01T00:00:00Z"})
    await ex.repo.atualizar_rendition(job["id"], "1x1", {"estado": "gerando"})
    await ex._fechar(job["id"])

    linha = ex.repo.jobs[job["id"]]
    assert linha["estado"] in ("failed", "partial"), "job não pode fechar como running"
    assert dominio.pode_retentar(linha["estado"]), "o operador precisa conseguir retentar"
    assert ex.repo.renditions[(job["id"], "1x1")]["estado"] == "falhou"


@pytest.mark.asyncio
async def test_defeito_antes_de_iniciar_nao_deixa_o_job_preso_em_queued(tmp_path):
    """C5: `_encerrar_por_defeito` violava a CHECK e o job ficava `queued` eterno."""
    ex = _executor(tmp_path)
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    assert ex.repo.jobs[job["id"]].get("iniciado_em") is None
    await ex._encerrar_por_defeito(job["id"])
    linha = ex.repo.jobs[job["id"]]
    assert linha["estado"] == "failed"
    assert linha["iniciado_em"] is not None and linha["terminado_em"] is not None
    assert dominio.pode_retentar(linha["estado"])


@pytest.mark.asyncio
async def test_retry_bem_sucedido_limpa_a_falha_do_job(tmp_path):
    """A CHECK `criativo_job_falha_coerente` recusa falha pendurada em sucesso."""
    ex = _executor(tmp_path, MotorFalso(falhar_em={"1x1"}))
    job, _ = await ex.criar_job_de_imagem({**PEDIDO, "slots": ["1x1"]}, "u1")
    await ex._executar(job["id"])
    assert ex.repo.jobs[job["id"]]["falha"] is not None
    ex.motor.falhar_em = set()
    await ex._executar(job["id"])
    assert ex.repo.jobs[job["id"]]["estado"] == "succeeded"
    assert ex.repo.jobs[job["id"]]["falha"] is None


@pytest.mark.asyncio
async def test_motor_indisponivel_e_falha_transitoria_e_nao_permanente(tmp_path):
    """`permanente` decide o retry. Marcar cota esgotada como permanente
    desistiria de um pedido que ia dar certo depois."""
    ex = _executor(tmp_path, MotorFalso(falhar_em={"1x1"},
                                        erro=MotorIndisponivel("cota esgotada")))
    job, _ = await ex.criar_job_de_imagem({**PEDIDO, "slots": ["1x1"]}, "u1")
    await ex._executar(job["id"])
    assert ex.repo.renditions[(job["id"], "1x1")]["erro_permanente"] is False
