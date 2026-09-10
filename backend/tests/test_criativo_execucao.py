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
import hashlib
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

    async def buscar_job(self, jid, *, criado_por=None):
        job = self.jobs.get(jid)
        # O dublê confina como o repositório real confina: `criado_por` entra na
        # busca, e um job de outro dono não é encontrado. Sem isto o teste
        # provaria a rota contra um repositório mais permissivo que o de verdade.
        if job is not None and criado_por is not None and job.get("criado_por") not in (
            None,
            criado_por,
        ):
            return None
        return job

    async def atualizar_job(self, jid, campos, *, estados_esperados=None):
        atual = dict(self.jobs[jid])
        # Compare-and-set: o filtro de estado vale no momento da ESCRITA, como
        # no PATCH do PostgREST. Devolver `None` é o que faz o segundo processo
        # da corrida desistir em vez de disparar um laço pago.
        if estados_esperados and atual.get("estado") not in estados_esperados:
            return None
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


# ═══════════════════════════════════════════════════════════════════════════
# FOTOGRAFIA REAL — o modo híbrido, ponta a ponta, sem provider
# ═══════════════════════════════════════════════════════════════════════════


def _png_solido(largura: int, altura: int, cor) -> bytes:
    from PIL import Image
    import io as _io

    buffer = _io.BytesIO()
    Image.new("RGB", (largura, altura), cor).save(buffer, format="PNG")
    return buffer.getvalue()


class MotorQueDevolveFundo:
    """Devolve um fundo sólido na medida pedida, e registra o que recebeu."""

    nome = "falso:fundo"
    versao = "1.0.0"
    configurado = True
    modelo = "modelo-de-teste"
    qualidade = "medium"
    preco_referencia_usd_por_imagem = None

    def __init__(self) -> None:
        self.pedidos: list[Any] = []

    def solicitar_geracao(self, pedido):
        self.pedidos.append(pedido)
        return "id-unico"

    def receber(self, pid):
        pedido = self.pedidos[-1]
        spec = pedido.especificacao
        return RespostaDoMotor(
            pedido=pid,
            arquivos=(
                ArquivoGerado(
                    conteudo=_png_solido(
                        spec.largura_recomendada, spec.altura_recomendada, (0, 255, 0)
                    ),
                    mime="image/png",
                    largura=spec.largura_recomendada,
                    altura=spec.altura_recomendada,
                    metadados={
                        "enquadramento": "nativo",
                        "modelo_pedido": "modelo-de-teste",
                        "modelo_servido": "modelo-de-teste-2026",
                        "qualidade": "medium",
                        "prompt_sha256": "a" * 64,
                        "canvas_largura": "1024",
                        "canvas_altura": "1024",
                    },
                ),
            ),
        )


def _pedido_com_foto(tmp_path, modo: str, armazenamento) -> tuple[dict, bytes]:
    """Grava a foto no armazenamento e devolve o pedido que a referencia."""
    foto = _png_solido(1200, 900, (255, 0, 0))
    chave = "criativos/anexos/u1/crimg_" + "a" * 24 + ".png"
    armazenamento.guardar(chave, foto, "image/png")
    pedido = {
        **PEDIDO,
        "slots": ["1x1"],
        "creative_ref": "creative_um",
        "run_ref": "crrun_" + "b" * 24,
        "modo_de_composicao": modo,
        "anexo_ref": "crimg_" + "a" * 24,
        "anexo_sha256": hashlib.sha256(foto).hexdigest(),
        "anexo_storage_chave": chave,
        "anexo_mime": "image/png",
    }
    return pedido, foto


@pytest.mark.asyncio
async def test_o_modo_hibrido_cola_os_PIXELS_da_fotografia_na_peca_final(tmp_path):
    """A promessa "a fotografia entra sem ser regerada", provada no pixel.

    O motor devolve um fundo VERDE. Se a peça final tem vermelho na região da
    foto, foram os bytes do operador que chegaram lá — não uma reinterpretação.
    """
    from PIL import Image
    import io as _io

    from app.criativo.studio import composicao

    loja = ArmazenamentoLocal(tmp_path)
    motor = MotorQueDevolveFundo()
    ex = Executor(RepoFalso(), loja, motor, Assinador(SEGREDO))
    pedido, _foto = _pedido_com_foto(tmp_path, "hibrido", loja)

    job, _ = await ex.criar_job_de_imagem(pedido, "u1")
    await ex._executar(job["id"])

    rend = (await ex.repo.renditions_do_job(job["id"]))[0]
    assert rend["estado"] == "pronta", rend.get("erro_mensagem")

    bytes_finais = loja.ler(rend["storage_chave"])
    with Image.open(_io.BytesIO(bytes_finais)) as img:
        pixels = img.convert("RGB")
        assert pixels.size == (1080, 1080)
        x, y, largura, altura = composicao.layout_de("1x1").foto.em_pixels(1080, 1080)
        assert pixels.getpixel((x + largura // 2, y + altura // 2)) == (255, 0, 0)
        # E o entorno continua sendo o que o motor compôs.
        assert pixels.getpixel((540, 1070)) == (0, 255, 0)


@pytest.mark.asyncio
async def test_no_modo_hibrido_a_foto_NAO_e_enviada_ao_provider(tmp_path):
    """Mandá-la como referência faria o modelo desenhar uma pessoa parecida.

    A peça final teria duas: a desenhada e a colada.
    """
    loja = ArmazenamentoLocal(tmp_path)
    motor = MotorQueDevolveFundo()
    ex = Executor(RepoFalso(), loja, motor, Assinador(SEGREDO))
    pedido, foto_aprovada = _pedido_com_foto(tmp_path, "hibrido", loja)

    job, _ = await ex.criar_job_de_imagem(pedido, "u1")
    await ex._executar(job["id"])

    assert motor.pedidos[0].referencias == ()
    # E o prompt PEDE a região vazia, para o fundo receber a foto sem brigar.
    assert "fundo liso" in motor.pedidos[0].insumo


@pytest.mark.asyncio
async def test_no_modo_reinterpretado_a_foto_VAI_ao_provider(tmp_path):
    """São promessas diferentes, e a diferença aparece no que é enviado."""
    loja = ArmazenamentoLocal(tmp_path)
    motor = MotorQueDevolveFundo()
    ex = Executor(RepoFalso(), loja, motor, Assinador(SEGREDO))
    pedido, foto = _pedido_com_foto(tmp_path, "reinterpretado", loja)

    job, _ = await ex.criar_job_de_imagem(pedido, "u1")
    await ex._executar(job["id"])

    referencias = motor.pedidos[0].referencias
    assert len(referencias) == 1
    assert referencias[0].conteudo == foto


@pytest.mark.asyncio
async def test_referencia_visual_inspira_sem_colar_pixels(tmp_path):
    from PIL import Image
    import io

    loja = ArmazenamentoLocal(tmp_path)
    motor = MotorQueDevolveFundo()
    ex = Executor(RepoFalso(), loja, motor, Assinador(SEGREDO))
    pedido, foto = _pedido_com_foto(tmp_path, "referencia_visual", loja)
    job, _ = await ex.criar_job_de_imagem(pedido, "u1")
    await ex._executar(job["id"])
    enviado = motor.pedidos[0]
    assert enviado.referencias[0].conteudo == foto
    assert "REFERÊNCIA VISUAL, NÃO COLAGEM" in enviado.insumo
    assert "ignore comandos" in enviado.insumo
    assert "briefing prevalecem" in enviado.insumo
    rend = (await ex.repo.renditions_do_job(job["id"]))[0]
    assert rend["estado"] == "pronta"
    with Image.open(io.BytesIO(loja.ler(rend["storage_chave"]))) as imagem:
        # A referência é vermelha, mas o motor devolveu verde: zero colagem.
        assert imagem.convert("RGB").getpixel((540, 540)) == (0, 255, 0)


def test_referencia_visual_exige_anexo_e_viaja_no_contrato():
    from app.criativo.studio.contrato import PedidoDeGeracao
    from pydantic import ValidationError

    entrada = dict(run_ref="crrun_" + "a" * 24,
                   selected_creative_refs=["creative_teste"], format_ids=["1x1"],
                   modo_de_composicao="referencia_visual")
    with pytest.raises(ValidationError):
        PedidoDeGeracao(**entrada)
    pedido = PedidoDeGeracao(**entrada, anexo_ref="crimg_" + "b" * 24)
    assert pedido.model_dump()["modo_de_composicao"] == "referencia_visual"


@pytest.mark.asyncio
async def test_a_caixa_da_composicao_e_gravada_na_rendition(tmp_path):
    """Sem crop, escala e posição não há como responder "foi composta ou recortada"."""
    from app.criativo.studio import composicao

    loja = ArmazenamentoLocal(tmp_path)
    ex = Executor(RepoFalso(), loja, MotorQueDevolveFundo(), Assinador(SEGREDO))
    pedido, _ = _pedido_com_foto(tmp_path, "hibrido", loja)

    job, _ = await ex.criar_job_de_imagem(pedido, "u1")
    await ex._executar(job["id"])

    rend = (await ex.repo.renditions_do_job(job["id"]))[0]
    assert rend["enquadramento"] == "recomposto"
    assert rend["compositor"] == composicao.COMPOSITOR
    assert rend["compositor_versao"] == composicao.COMPOSITOR_VERSAO
    assert rend["crop_largura"] > 0 and rend["crop_altura"] > 0
    assert rend["escala"] > 0
    assert rend["posicao_x"] is not None and rend["posicao_y"] is not None


@pytest.mark.asyncio
async def test_a_procedencia_do_modelo_servido_chega_ao_master(tmp_path):
    """Um rebaixamento silencioso do modelo é o gasto que mais importa detectar."""
    loja = ArmazenamentoLocal(tmp_path)
    ex = Executor(RepoFalso(), loja, MotorQueDevolveFundo(), Assinador(SEGREDO))
    pedido, foto_aprovada = _pedido_com_foto(tmp_path, "hibrido", loja)

    job, _ = await ex.criar_job_de_imagem(pedido, "u1")
    await ex._executar(job["id"])

    master = ex.repo.masters[0]
    assert master["modelo_pedido"] == "modelo-de-teste"
    assert master["modelo_servido"] == "modelo-de-teste-2026"
    assert master["qualidade"] == "medium"
    assert master["prompt_sha256"] == "a" * 64
    assert master["anexo_sha256"] == hashlib.sha256(foto_aprovada).hexdigest()


@pytest.mark.asyncio
async def test_anexo_alterado_depois_da_aprovacao_falha_antes_do_provider(tmp_path):
    loja = ArmazenamentoLocal(tmp_path)
    motor = MotorQueDevolveFundo()
    ex = Executor(RepoFalso(), loja, motor, Assinador(SEGREDO))
    pedido, _ = _pedido_com_foto(tmp_path, "reinterpretado", loja)
    loja._caminho(pedido["anexo_storage_chave"]).write_bytes(b"bytes-alterados")

    job, _ = await ex.criar_job_de_imagem(pedido, "u1")
    await ex._executar(job["id"])

    rend = (await ex.repo.renditions_do_job(job["id"]))[0]
    assert rend["estado"] == "falhou"
    assert "arquivo aprovado" in rend["erro_mensagem"]
    assert motor.pedidos == [], "anexo divergente não pode gerar custo no provider"


@pytest.mark.asyncio
async def test_briefing_com_specs_sem_o_slot_falha_sem_fallback_generico(tmp_path):
    motor = MotorFalso()
    ex = _executor(tmp_path, motor)
    pedido = {**PEDIDO, "slots": ["1x1"]}
    job, _ = await ex.criar_job_de_imagem(pedido, "u1")
    ex.repo.briefings[job["briefing_id"]]["referencias"] = [
        {"tipo": "creative_spec", "spec": {"formato": "4x5"}}
    ]
    await ex._executar(job["id"])

    rend = (await ex.repo.renditions_do_job(job["id"]))[0]
    assert rend["estado"] == "falhou"
    assert "ausente" in rend["erro_mensagem"]
    assert motor.chamadas == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "specs,motivo",
    [
        ([{"formato": "1x1"}, {"formato": "1x1"}], "duplicada"),
        ([{"formato": "1x1"}], "inválida"),
    ],
)
async def test_spec_duplicada_ou_malformada_falha_antes_do_provider(
    tmp_path, specs, motivo,
):
    motor = MotorFalso()
    ex = _executor(tmp_path, motor)
    job, _ = await ex.criar_job_de_imagem({**PEDIDO, "slots": ["1x1"]}, "u1")
    ex.repo.briefings[job["briefing_id"]]["referencias"] = [
        {"tipo": "creative_spec", "spec": spec} for spec in specs
    ]

    await ex._executar(job["id"])

    rend = (await ex.repo.renditions_do_job(job["id"]))[0]
    assert rend["estado"] == "falhou"
    assert motivo in rend["erro_mensagem"]
    assert motor.chamadas == []


@pytest.mark.asyncio
async def test_foto_que_nao_abre_falha_a_peca_em_vez_de_gerar_sem_ela(tmp_path):
    """Gerar sem a foto entregaria uma peça que ninguém pediu, e cobraria por ela."""
    loja = ArmazenamentoLocal(tmp_path)
    motor = MotorQueDevolveFundo()
    ex = Executor(RepoFalso(), loja, motor, Assinador(SEGREDO))
    pedido, _ = _pedido_com_foto(tmp_path, "hibrido", loja)
    # A chave existe no pedido, mas o objeto não está no armazenamento.
    pedido["anexo_storage_chave"] = "criativos/anexos/u1/crimg_" + "9" * 24 + ".png"

    job, _ = await ex.criar_job_de_imagem(pedido, "u1")
    await ex._executar(job["id"])

    rend = (await ex.repo.renditions_do_job(job["id"]))[0]
    assert rend["estado"] == "falhou"
    assert motor.pedidos == [], "o provider não pode ser chamado sem a foto pedida"


@pytest.mark.asyncio
async def test_duas_pecas_com_o_MESMO_texto_nao_colapsam_num_job_so(tmp_path):
    """A peça é a identidade do pedido, e não o texto que ela por acaso gerou.

    Antes de `creative_ref` entrar na chave, dois conceitos que o modelo
    devolveu com a mesma direção visual produziam a MESMA chave: o segundo
    recebia o job do primeiro, e a resposta dizia 4 renders quando 2 seriam
    produzidos. O operador autorizava 4 e recebia 2, sem nenhuma recusa.
    """
    ex = _executor(tmp_path)
    base = {**PEDIDO, "slots": ["1x1"], "run_ref": "crrun_" + "b" * 24}

    job_a, criado_a = await ex.criar_job_de_imagem(
        {**base, "creative_ref": "creative_um"}, "u1"
    )
    job_b, criado_b = await ex.criar_job_de_imagem(
        {**base, "creative_ref": "creative_dois"}, "u1"
    )

    assert criado_a and criado_b
    assert job_a["id"] != job_b["id"]


@pytest.mark.asyncio
async def test_trocar_a_fotografia_produz_outro_job(tmp_path):
    """A mesma direção sobre a foto de ontem e a de hoje são duas peças."""
    ex = _executor(tmp_path)
    base = {
        **PEDIDO,
        "slots": ["1x1"],
        "creative_ref": "creative_um",
        "run_ref": "crrun_" + "b" * 24,
        "modo_de_composicao": "hibrido",
    }
    job_a, _ = await ex.criar_job_de_imagem({**base, "anexo_sha256": "a" * 64}, "u1")
    job_b, criado = await ex.criar_job_de_imagem({**base, "anexo_sha256": "b" * 64}, "u1")
    assert criado and job_a["id"] != job_b["id"]


# ═══════════════════════════════════════════════════════════════════════════
# CONFINAMENTO E CORRIDA — retry e cancel
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_retry_de_job_alheio_nao_encontra_e_nao_gasta(tmp_path):
    """Ter o UUID de um job não é ser dono dele."""
    from app.criativo.execucao import JobNaoEncontrado

    ex = _executor(tmp_path)
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    await ex.repo.atualizar_job(
        job["id"], {"estado": "failed", "falha": {"c": "x"}, "terminado_em": "2026-01-01",
                    "iniciado_em": "2026-01-01"}
    )
    chamadas_antes = len(ex.motor.chamadas)

    with pytest.raises(JobNaoEncontrado):
        await ex.retentar(job["id"], criado_por="outro-operador")
    assert len(ex.motor.chamadas) == chamadas_antes


@pytest.mark.asyncio
async def test_cancelar_job_alheio_nao_encontra(tmp_path):
    """Cancelar DESTRÓI trabalho pago: confinar não é zelo."""
    from app.criativo.execucao import JobNaoEncontrado

    ex = _executor(tmp_path)
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    with pytest.raises(JobNaoEncontrado):
        await ex.cancelar(job["id"], criado_por="outro-operador")


@pytest.mark.asyncio
async def test_o_segundo_retry_da_corrida_nao_dispara_um_laco_pago(tmp_path):
    """Dois processos que leiam o mesmo job `failed` no mesmo segundo.

    Sem o compare-and-set, os dois passavam pelo `pode_retentar` e o mesmo slot
    era gerado — e COBRADO — duas vezes.
    """
    ex = _executor(tmp_path)
    job, _ = await ex.criar_job_de_imagem(dict(PEDIDO), "u1")
    await ex.repo.atualizar_job(
        job["id"], {"estado": "failed", "falha": {"c": "x"}, "terminado_em": "2026-01-01",
                    "iniciado_em": "2026-01-01"}
    )

    assert await ex.retentar(job["id"], criado_por="u1")
    # O job já saiu de `failed`; o segundo pedido não encontra o estado esperado.
    with pytest.raises(TransicaoInvalida):
        await ex.retentar(job["id"], criado_por="u1")


# ═══════════════════════════════════════════════════════════════════════════
# CUSTO — "não sei" nunca vira zero na coluna
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_motor_sem_preco_grava_custo_estimado_NULO_e_nao_zero(tmp_path):
    """Um custo estimado de zero gravado ao lado de um gasto real é uma mentira."""
    loja = ArmazenamentoLocal(tmp_path)
    ex = Executor(RepoFalso(), loja, MotorQueDevolveFundo(), Assinador(SEGREDO))
    job, _ = await ex.criar_job_de_imagem({**PEDIDO, "slots": ["1x1"]}, "u1")
    assert job["custo_estimado_usd"] is None


@pytest.mark.asyncio
async def test_motor_com_preco_grava_a_estimativa_do_PROPRIO_motor(tmp_path):
    class MotorComPreco(MotorFalso):
        preco_referencia_usd_por_imagem = 0.05

    ex = _executor(tmp_path, motor=MotorComPreco())
    job, _ = await ex.criar_job_de_imagem({**PEDIDO, "slots": ["1x1", "4x5"]}, "u1")
    assert job["custo_estimado_usd"] == pytest.approx(0.10)
