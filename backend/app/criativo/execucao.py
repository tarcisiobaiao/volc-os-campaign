"""O executor de jobs — quem transforma um briefing em peças sem travar o request.

## A regra que este arquivo existe para cumprir

"Não faça o request HTTP esperar o render terminar. Criar job deve responder com
identidade e estado inicial; acompanhamento ocorre por consulta/eventos."

Três formatos a ~11 segundos cada dão ~33 segundos de geração. Um POST que
segura isso morre no timeout do proxy, e o operador que recarrega a página não
tem como saber se pagou ou não. Aqui `criar` grava o job com as peças em
`pendente` e devolve; `executar` roda depois, fora do request.

## O que torna o retry seguro, e por que ele não é um job novo

Retry preenche buraco. Ele percorre APENAS as renditions em `falhou`,
`pendente` ou `cancelada`; uma peça `pronta` não é tocada, não é regerada e não
é cobrada de novo. As três camadas que garantem isso são independentes:

  1. este executor filtra por estado antes de chamar o motor;
  2. `criativo_rendition_slot_ux` impede uma segunda linha para o mesmo slot;
  3. `criativo_master_slot_ux` impede um segundo master para (job, slot, versão).

A terceira é a que sobrevive a um defeito nas outras duas: mesmo que o executor
errasse, o banco recusaria a escrita em vez de duplicar patrimônio pago.

## Cancelamento é cooperativo, e o texto da interface não pode mentir sobre isso

Não há como cancelar uma chamada HTTP que o provider já aceitou: ele vai gerar e
vai cobrar. O que este executor faz é parar ANTES da próxima peça. Por isso o
pedido de cancelamento grava `cancelado_pedido_em` (pedido) e só depois
`cancelado_em` (confirmação), que são fatos diferentes, e a SPEC §16 pede
justamente que a interface os distinga.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from typing import Any

from volc_ads.criativo.porta import (
    ErroDoMotor,
    PedidoDeGeracao,
    RespostaDoMotor,
)

from . import dominio
from .bancada.armazenamento_verificado import (
    EstadoDoArmazenamento,
    publicar_artefato,
)
from .armazenamento import (
    ArmazenamentoDeObjetos,
    Assinador,
    chave_de_asset,
)
from .parque import Resolvedor
from .persistencia import ConflitoDeChave, Repositorio, agora

log = logging.getLogger("volc.criativo")

_EXTENSAO_POR_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "video/mp4": "mp4",
}


class JobNaoEncontrado(LookupError):
    pass


class TransicaoInvalida(ValueError):
    """Ação pedida num estado que não a permite. Vira 409, não 500."""


class Executor:
    """Cria, executa, retenta e cancela jobs de imagem."""

    def __init__(
        self,
        repo: Repositorio,
        armazenamento: ArmazenamentoDeObjetos,
        motor: Any,
        assinador: Assinador,
    ) -> None:
        self.repo = repo
        self.armazenamento = armazenamento
        self.motor = motor
        self.assinador = assinador
        # Um job por vez por processo, para que dois pedidos simultâneos não
        # disparem duas rodadas do MESMO job caso a chave de idempotência ainda
        # não tenha sido gravada. O banco já barra a duplicata; esta trava evita
        # a chamada paga que aconteceria antes dele barrar.
        self._em_voo: set[str] = set()
        self._trava = asyncio.Lock()
        # Traduz o nome que o código usa para o `id` que a FK exige. Falha dele
        # devolve `None`, nunca levanta: um job com procedência mais fraca é pior
        # que um job perfeito e melhor que um pedido perdido.
        self._resolvedor = Resolvedor(repo)

    # ── criação ──────────────────────────────────────────────────────────────

    async def criar_job_de_imagem(
        self, pedido: dict[str, Any], usuario_id: str | None
    ) -> tuple[dict[str, Any], bool]:
        """Grava projeto, briefing, job e as peças pendentes. Não gera nada.

        Devolve `(job, criado)`. `criado=False` é um reenvio reconhecido: nada
        novo foi gravado e nada será cobrado outra vez.
        """
        slots: list[str] = list(dict.fromkeys(pedido.get("slots") or []))
        if not slots:
            raise ValueError("nenhum formato pedido")
        formatos = [dominio.formato_de(s) for s in slots]

        material = {
            "projeto_titulo": pedido.get("projeto_titulo"),
            "objetivo": pedido.get("objetivo"),
            "mensagem": pedido.get("mensagem"),
            "audiencia": pedido.get("audiencia"),
            "brand_pack_id": pedido.get("brand_pack_id"),
            "modo": pedido.get("modo") or "full_llm",
            "slots": slots,
            "motor": self.motor.nome,
            "motor_versao": self.motor.versao,
            "criado_por": usuario_id,
            "destinos_pretendidos": pedido.get("destinos_pretendidos") or [],
            "creative_ref": pedido.get("creative_ref"),
            "run_ref": pedido.get("run_ref"),
            "modo_de_composicao": pedido.get("modo_de_composicao") or "sem_foto",
            "anexo_sha256": pedido.get("anexo_sha256"),
        }
        chave = dominio.chave_de_idempotencia(material)

        # Antes de gravar projeto e briefing: se a chave já existe, este é um
        # reenvio, e criar um projeto órfão a cada duplo clique encheria a
        # biblioteca de projetos vazios que ninguém pediu.
        ja = await self.repo.job_por_chave(chave)
        if ja is not None:
            # ⚠️ O reenvio CONSERTA um job incompleto em vez de devolvê-lo morto.
            #
            # Defeito medido: se o insert do job passou mas a gravação das peças
            # falhou (banco piscou), o job ficava em `queued` com zero rendition.
            # A chave já estava ocupada, então todo reenvio devolvia `200 replay`
            # sem disparar nada, e o retry recusava `queued`. Beco sem saída, com
            # a tela dizendo "este pedido já existia" para um trabalho que nunca
            # existiu de verdade.
            #
            # Aqui o replay é idempotente E curativo: se faltam peças e o job
            # ainda não terminou, elas são criadas e a execução é disparada.
            # Nada é cobrado duas vezes: `_executar` só processa peça pendente.
            if ja["estado"] not in ("succeeded", "partial", "failed"):
                await self._garantir_pecas(str(ja["id"]), formatos)
            return ja, False

        projeto = await self.repo.criar_projeto(
            titulo=(pedido.get("projeto_titulo") or "").strip() or "Projeto sem título",
            objetivo=pedido.get("objetivo"),
            brand_pack_id=pedido.get("brand_pack_id"),
            dono_id=usuario_id,
            origem=pedido.get("origem") or "standalone",
        )
        briefing = await self.repo.criar_briefing(
            {
                "projeto_id": projeto["id"],
                "tipo": "imagem",
                "modo": material["modo"],
                # A coluna texto continua sendo gravada: ela é o que a v11_01
                # sempre gravou e o que as telas leem. `modo_id` é o vínculo com
                # o registro, e nasce ao lado — não no lugar.
                "modo_id": await self._resolvedor.modo(material["modo"]),
                "objetivo": pedido.get("objetivo"),
                "audiencia": pedido.get("audiencia"),
                "mensagem": pedido.get("mensagem"),
                "brand_pack_id": pedido.get("brand_pack_id"),
                "formatos_pedidos": [
                    {
                        "slot": f.slot,
                        "rotulo": f.rotulo,
                        "largura": f.largura,
                        "altura": f.altura,
                    }
                    for f in formatos
                ],
                "destinos_pretendidos": pedido.get("destinos_pretendidos") or [],
                # A fotografia anexada vive em `referencias`, a coluna jsonb que
                # a v11_01 criou para exatamente isto. Uma coluna nova por anexo
                # obrigaria uma migration por tipo de material de entrada, e o
                # briefing e o lugar onde "esta peca usa esta foto" pertence.
                "referencias": _referencias_do_pedido(pedido),
                "criado_por": usuario_id,
            }
        )

        insumo = _insumo_do_briefing(pedido)
        job, criado = await self.repo.criar_job_idempotente(
            {
                "briefing_id": briefing["id"],
                "motor": self.motor.nome,
                "motor_versao": self.motor.versao,
                # `getattr` e não `self.motor.slug`: o Protocol `MotorDeCriativo`
                # declara só `nome` e `versao`, e um adaptador de teste que não
                # conheça `slug` não pode quebrar a criação do job por isso.
                "motor_id": await self._resolvedor.motor(
                    getattr(self.motor, "slug", "") or ""
                ),
                "estado": "queued",
                "idempotency_key": chave,
                "insumo_hash": dominio.hash_de_insumo(insumo),
                "procedencia_execucao": "volc_os",
                # Estimativa declarada, nunca custo medido: o provider reporta
                # tokens, não dólares. `custo_real_usd` fica NULL de propósito.
                "custo_estimado_usd": _estimativa(len(formatos), self.motor),
                # A procedencia do MODELO, separada de `motor`/`motor_versao`.
                # `motor` carrega "openai:gpt-image-2" (identidade do adaptador);
                # `modelo_pedido` carrega "gpt-image-2" (o que foi pedido ao
                # provider). O SERVIDO so existe depois da resposta, e por isso
                # ele nasce nulo aqui e e preenchido pela peca.
                "modelo_pedido": getattr(self.motor, "modelo", None),
                "qualidade": getattr(self.motor, "qualidade", None),
                "modo_de_composicao": pedido.get("modo_de_composicao") or "sem_foto",
                "anexo_sha256": pedido.get("anexo_sha256"),
                # A trilha da AUTORIZACAO, no mesmo insert que a procedencia.
                #
                # ⚠️ Sem estes quatro campos, as colunas existiriam e ficariam
                # sempre nulas: a pergunta "quem autorizou este gasto, quando, e
                # sobre qual plano?" continuaria sem resposta em SQL, e a
                # migration teria criado espaco sem criar prova. `autorizado_por`
                # e `autorizado_em` viajam JUNTOS porque a CHECK exige o par —
                # numero sem carimbo nao e autorizacao.
                "plano_sha256": pedido.get("plano_sha256"),
                "teto_custo_usd": pedido.get("teto_custo_usd"),
                "autorizado_por": usuario_id if pedido.get("plano_sha256") else None,
                "autorizado_em": agora() if pedido.get("plano_sha256") else None,
                "criado_por": usuario_id,
            }
        )
        if not criado:
            # Perdemos a corrida: outra requisição gravou o job com esta chave
            # entre a nossa consulta e o nosso insert. O projeto e o briefing que
            # acabamos de criar não têm dono e ninguém os apagaria (a migration
            # não concede DELETE, por desenho), então cada clique perdedor
            # deixava um par órfão na biblioteca de projetos. Arquivar é a
            # exclusão lógica que o schema prevê.
            with contextlib.suppress(Exception):
                await self.repo.atualizar_projeto(
                    str(projeto["id"]), {"arquivado_em": agora()}
                )
            await self._garantir_pecas(str(job["id"]), formatos)
            return job, False

        await self.repo.criar_renditions(
            [
                {
                    "job_id": job["id"],
                    "slot": f.slot,
                    "estado": "pendente",
                    "largura_pedida": f.largura,
                    "altura_pedida": f.altura,
                    "proporcao_rotulo": f.proporcao,
                }
                for f in formatos
            ]
        )
        await self.repo.registrar_evento(
            job["id"], "aceito", f"Pedido aceito com {len(formatos)} formato(s)."
        )
        return job, True

    async def _garantir_pecas(self, job_id: str, formatos: list[dominio.Formato]) -> None:
        """Cria as peças que faltam para este job. Idempotente.

        Existe porque a criação não é atômica: o job entra numa escrita e as
        peças noutra. Um job sem peça nenhuma é indistinguível de um job pronto
        para nada, e `estado_do_lote([])` devolve `failed` — o operador via um
        trabalho que falhou sem que nada tivesse sido tentado.
        """
        existentes = {r["slot"] for r in await self.repo.renditions_do_job(job_id)}
        faltando = [f for f in formatos if f.slot not in existentes]
        if not faltando:
            return
        await self.repo.criar_renditions(
            [
                {
                    "job_id": job_id,
                    "slot": f.slot,
                    "estado": "pendente",
                    "largura_pedida": f.largura,
                    "altura_pedida": f.altura,
                    "proporcao_rotulo": f.proporcao,
                }
                for f in faltando
            ]
        )

    # ── execução ─────────────────────────────────────────────────────────────

    def disparar(self, job_id: str) -> None:
        """Registra o trabalho na fila DURÁVEL e o entrega ao operário.

        ## O defeito que este método tinha, e por que ele importava tanto

        A versão anterior fazia `asyncio.create_task(...)` e devolvia na hora. Num
        processo de vida longa isso funciona; **este backend é uma função
        serverless na Vercel** (`backend/vercel.json`), e a plataforma congela a
        execução quando a resposta sai. O `POST /jobs` respondia 201 antes de a
        imagem existir, e a task que a produziria era congelada.

        Isso explicava melhor que qualquer outra hipótese os **zero jobs** nas 12
        tabelas operacionais de produção: não é que ninguém tentou — é que o
        mecanismo podia estruturalmente não terminar.

        ## O que ele faz agora

        Enfileira no depósito durável (SQLite hoje, `criativo_render_job` quando a
        v11_03 for aplicada) e pede ao despachante que execute. O despachante
        local é síncrono, e isso é **deliberado**: o `POST` só responde depois de
        o trabalho ter um estado terminal ou ter voltado para a fila. Um pedido
        que responde 201 sobre trabalho que não começou é a mentira que este
        método existia para cometer.

        Quando o executor remoto existir, só o despachante muda.

        ⚠️ Se a fila não puder ser montada, o job **não fica preso em `queued`
        para sempre**: a falha é registrada nele, com motivo, e o operador vê.
        """
        from app.criativo.bancada.despacho import (  # noqa: PLC0415
            DespachoIndisponivel,
            escolher_despachante,
        )

        try:
            despachante = escolher_despachante()
        except DespachoIndisponivel as e:
            # ⚠️ Fail-closed. Sem onde executar de forma aceitavel, o job vira
            # `failed` COM MOTIVO — e se nem isso der certo, a excecao SOBE, para
            # a rota nao responder 201 sobre um pedido que ninguem vai executar.
            log.warning("despacho indisponivel em %s: %s", e.ambiente, e.motivo)
            self._registrar_indisponibilidade(job_id, e.motivo)
            return

        despachante.despachar_job_do_estudio(job_id, self)

    def _registrar_indisponibilidade(self, job_id: str, motivo: str) -> None:
        """Marca o job como falho, e SOBE se não conseguir marcar.

        ## Os dois defeitos que esta função tinha

        1. `contextlib.suppress(Exception)` em volta de tudo. Uma falha ao
           registrar a falha virava silêncio, e a rota respondia 201 sobre um job
           que ficaria em `queued` para sempre. Apagar o registro do próprio
           defeito é o pior lugar para engolir exceção.
        2. `anyio.from_thread.run` só funciona **dentro de uma worker thread do
           anyio**. Chamado do loop principal, ele levanta `RuntimeError` — e o
           `suppress` escondia exatamente isso. A função parecia funcionar e
           nunca gravava nada.

        Agora ela usa `anyio.from_thread.run` **apenas quando há um portal**, e
        cai para `anyio.run` quando não há. E se a gravação falhar, a exceção
        sobe: a rota vira 503, que é a verdade.
        """
        import anyio  # noqa: PLC0415
        import anyio.from_thread  # noqa: PLC0415

        async def marcar() -> None:
            await self.repo.atualizar_job(
                job_id,
                {
                    "estado": "failed",
                    "falha": {
                        "codigo": "ESTUDIO.despacho_indisponivel",
                        "mensagem": motivo,
                        "permanente": False,
                    },
                    # ⚠️ `iniciado_em` junto. O CHECK `criativo_job_ordem_temporal`
                    # recusa fim sem início, e um job que nunca foi despachado não
                    # tem início — mas também não pode ficar sem carimbo terminal.
                    # O instante é o mesmo: a produção começou e acabou aqui.
                    "iniciado_em": agora(),
                    "terminado_em": agora(),
                },
            )

        # ⚠️ DEFEITO CRITICO MEDIDO E FECHADO. A versão anterior tentava
        # `anyio.from_thread.run` e caía para `anyio.run` — e os DOIS estouram
        # quando chamados da thread do event loop, que é exatamente de onde a
        # rota `async def criar_job` chama:
        #
        #     anyio.from_thread.run  -> NoEventLoopError
        #     anyio.run              -> RuntimeError: Already running asyncio
        #
        # Consequência medida: o job NÃO virava `failed`, não recebia
        # `ESTUDIO.despacho_indisponivel`, não recebia carimbo terminal, e a rota
        # devolvia 500 sobre um job órfão em `queued`. O fail-closed existia para
        # impedir precisamente isso e falhava aberto.
        #
        # Uma thread nova nunca tem loop; ali `anyio.run` sempre vale. A exceção
        # sobe, que é o contrato: se nem marcar a falha der certo, a rota vira
        # 503, que é a verdade.
        from app.criativo.bancada.despacho import (  # noqa: PLC0415
            _rodar_corrotina_em_thread,
        )

        _rodar_corrotina_em_thread(marcar)

    async def _executar_protegido(self, job_id: str) -> None:
        async with self._trava:
            if job_id in self._em_voo:
                return
            self._em_voo.add(job_id)
        try:
            await self._executar(job_id)
        except Exception:  # noqa: BLE001
            log.exception("execução do job %s caiu", job_id)
            with contextlib.suppress(Exception):
                await self._encerrar_por_defeito(job_id)
        finally:
            async with self._trava:
                self._em_voo.discard(job_id)

    async def _executar(self, job_id: str) -> None:
        job = await self.repo.buscar_job(job_id)
        if job is None:
            raise JobNaoEncontrado(job_id)
        briefing = await self.repo.buscar_briefing(job["briefing_id"])
        if briefing is None:
            raise JobNaoEncontrado(job["briefing_id"])

        await self.repo.atualizar_job(
            job_id,
            {
                "estado": "running",
                "iniciado_em": job.get("iniciado_em") or agora(),
                # `falha` limpa junto com a transição, e não depois.
                #
                # A CHECK `criativo_job_falha_coerente` exige `falha is null`
                # fora de `failed`. Um job que já tinha falhado e volta a rodar
                # carregava o objeto de falha antigo para dentro de `running`, e
                # a escrita era recusada pelo banco. `retentar()` limpava por
                # conta própria, então o caminho normal passava e só um disparo
                # direto de `_executar` quebrava — o pior tipo de defeito, o que
                # só aparece no caminho de recuperação.
                "falha": None,
                "terminado_em": None,
            },
        )
        await self.repo.registrar_evento(job_id, "iniciando", "Produção iniciada.")

        insumo = _insumo_do_briefing(
            {
                "objetivo": briefing.get("objetivo"),
                "mensagem": briefing.get("mensagem"),
                "audiencia": briefing.get("audiencia"),
                "projeto_titulo": None,
            }
        )

        pendentes = [
            r
            for r in await self.repo.renditions_do_job(job_id)
            if r["estado"] in ("pendente", "falhou", "cancelada")
        ]

        for rend in pendentes:
            atual = await self.repo.buscar_job(job_id)
            if atual and atual.get("cancelado_pedido_em"):
                await self._confirmar_cancelamento(job_id)
                return
            await self._produzir_peca(job_id, briefing, rend, insumo)

        await self._fechar(job_id)

    async def _produzir_peca(
        self, job_id: str, briefing: dict[str, Any], rend: dict[str, Any], insumo: str
    ) -> None:
        slot = rend["slot"]
        formato = dominio.formato_de(slot)
        await self.repo.atualizar_rendition(
            job_id, slot, {"estado": "gerando", "iniciada_em": agora()}
        )
        # `percentual=None` de propósito: o motor de imagem não emite progresso
        # medido, e a SPEC proíbe inventar um número. A interface mostra a fase.
        await self.repo.registrar_evento(
            job_id, "gerando", f"Gerando o formato {formato.rotulo}.", slot=slot
        )

        fotografia = _fotografia_do_briefing(briefing)
        modo = fotografia.get("modo") or "sem_foto"
        chave_do_anexo = fotografia.get("storage_chave")
        foto: bytes | None = None
        if modo != "sem_foto":
            if not chave_do_anexo:
                await self._marcar_falha_da_peca(
                    job_id, slot,
                    _erro_generico(
                        "este pedido pede fotografia e o anexo não está registrado"
                    ),
                )
                return
            foto = await asyncio.to_thread(self._ler_anexo, str(chave_do_anexo))
            if not foto:
                # Gerar sem a foto entregaria uma peça que ninguém pediu, e
                # cobraria por ela. Falhar a peça é mais barato que isso.
                await self._marcar_falha_da_peca(
                    job_id, slot,
                    _erro_generico("a fotografia anexada não pôde ser lida"),
                )
                return

        try:
            resposta = await asyncio.to_thread(
                self._chamar_motor,
                slot,
                formato,
                insumo,
                modo=modo,
                foto=foto,
                foto_mime=fotografia.get("mime"),
            )
        except ErroDoMotor as erro:
            await self._marcar_falha_da_peca(job_id, slot, erro)
            return
        except Exception as erro:  # noqa: BLE001
            log.exception("motor falhou fora do contrato no slot %s", slot)
            await self._marcar_falha_da_peca(
                job_id, slot, _erro_generico(str(erro))
            )
            return

        if resposta.vazia:
            await self._marcar_falha_da_peca(
                job_id, slot, _erro_generico("o motor não devolveu nenhuma peça")
            )
            return

        arquivo = resposta.arquivos[0]
        dados = arquivo.conteudo or b""
        composta = None
        if modo == "hibrido" and foto:
            # O provider devolveu o ENTORNO. Os pixels da fotografia entram
            # AGORA, por aritmética, sem provider no meio: é isto que torna
            # verdadeira a frase "a fotografia entra sem ser regerada".
            from .studio import composicao as compositor  # noqa: PLC0415

            try:
                composta = await asyncio.to_thread(
                    compositor.compor,
                    fundo=dados,
                    foto=foto,
                    slot=slot,
                    largura=formato.largura,
                    altura=formato.altura,
                )
                dados = composta.conteudo
            except Exception as erro:  # noqa: BLE001
                log.exception("composição híbrida falhou no slot %s", slot)
                await self._marcar_falha_da_peca(
                    job_id, slot,
                    _erro_generico(f"não foi possível compor a fotografia: {erro}"),
                )
                return

        content_hash = dominio.hash_de_conteudo(dados)
        mime = arquivo.mime or "image/png"
        extensao = _EXTENSAO_POR_MIME.get(mime, "bin")
        chave = chave_de_asset(
            str(briefing["projeto_id"]), str(job_id), slot, content_hash, extensao
        )

        # ⚠️ ACHADO DO REVISOR ADVERSARIAL. Isto era `guardar(...)` e mais nada:
        # o Executor subia os bytes e, algumas linhas abaixo, marcava a peça
        # `pronta` e o job `succeeded` — com ZERO leituras de volta. "Voltou sem
        # exceção" virava "está lá, íntegro", que é o colapso de
        # `arquivo escrito` em `arquivo verificado` que este projeto proíbe.
        # Um 200 prova que o servidor ACEITOU os bytes, não que os guardou
        # inteiros nem que a próxima leitura devolve os mesmos.
        #
        # `publicar_artefato` sobe E relê, e só chama de verificado depois de
        # comparar bytes e sha256. Divergência é terminal e vira falha da peça —
        # não um `pronta` sobre arquivo que ninguém conferiu.
        try:
            publicacao = publicar_artefato(
                self.armazenamento, chave=chave, dados=dados, mime=mime
            )
        except Exception as erro:  # noqa: BLE001
            log.exception("armazenamento recusou a peça %s", slot)
            await self._marcar_falha_da_peca(
                job_id, slot, _erro_generico(f"não foi possível guardar a peça: {erro}")
            )
            return
        if publicacao.estado is not EstadoDoArmazenamento.VERIFIED_OK:
            # ⚠️ `UPLOADED_UNVERIFIED` (a releitura não concluiu) e
            # `VERIFIED_MISMATCH` (os bytes voltaram diferentes) são desfechos
            # DIFERENTES, e nenhum dos dois é "pronta". O motivo vai junto,
            # porque um estado ruim sem motivo obriga quem lê a adivinhar.
            log.error(
                "peça %s não ficou verificada no armazenamento: %s · %s",
                slot, publicacao.estado.value, publicacao.motivo,
            )
            await self._marcar_falha_da_peca(
                job_id, slot,
                _erro_generico(
                    "a peça subiu mas não passou na conferência de bytes "
                    f"({publicacao.estado.value})"
                ),
            )
            return

        meta = dict(arquivo.metadados or {})
        # `criativo_master_slot_ux` é única em (job, slot, versão). Um conflito
        # aqui significa que ESTA peça já foi produzida e gravada — por um retry
        # que correu em paralelo, ou por uma execução anterior que gravou o
        # master e caiu antes de marcar a rendition. Nos dois casos a resposta
        # certa é reaproveitar o que existe, nunca abortar o lote e nunca gravar
        # um segundo master para o mesmo formato.
        try:
            master = await self.repo.criar_master(
                {
                    "job_id": job_id,
                    "projeto_id": briefing["projeto_id"],
                    "slot": slot,
                    "kind": "imagem",
                    "storage_chave": chave,
                    "content_hash": content_hash,
                    "mime": mime,
                    "bytes_totais": len(dados) or None,
                    "largura": arquivo.largura,
                    "altura": arquivo.altura,
                    "motor": self.motor.nome,
                    "motor_versao": self.motor.versao,
                    # A procedencia do MODELO, na peca e nao so no pedido: um job
                    # retentado produz masters em momentos diferentes, e o modelo
                    # servido pode divergir ENTRE eles. Guardar so no job
                    # responderia "o que foi pedido" e nao "o que gerou ESTE
                    # arquivo".
                    "modelo_pedido": meta.get("modelo_pedido") or None,
                    "modelo_servido": meta.get("modelo_servido") or None,
                    "qualidade": meta.get("qualidade") or None,
                    "prompt_sha256": meta.get("prompt_sha256") or None,
                    "anexo_sha256": fotografia.get("sha256") or None,
                    "insumo_hash": dominio.hash_de_insumo(insumo),
                    # O prompt completo NÃO é guardado: ele é reconstruível a partir
                    # do briefing, e guardá-lo duplicado num campo que a API lê seria
                    # um caminho a mais para ele vazar até o operador.
                    "insumo_sanitizado": None,
                    "brand_pack_id": briefing.get("brand_pack_id"),
                    "sintetico": True,
                    "disclosure": "Imagem gerada por inteligência artificial.",
                "versao": 1,
                }
            )
        except ConflitoDeChave:
            existentes = [
                m for m in await self.repo.masters_do_job(job_id) if m["slot"] == slot
            ]
            if not existentes:
                await self._marcar_falha_da_peca(
                    job_id, slot,
                    _erro_generico("conflito ao registrar a peça, e ela não foi encontrada"),
                )
                return
            master = existentes[0]
            await self.repo.registrar_evento(
                job_id, "peca_reaproveitada",
                f"{formato.rotulo} já estava registrada; nada foi gerado de novo.",
                slot=slot,
            )
            # ⚠️ A rendition passa a apontar para o arquivo DO MASTER QUE VENCEU,
            # e não para os bytes que esta execução acabou de gerar.
            #
            # Escrever `storage_chave`/`content_hash` desta execução por cima
            # daria à peça duas identidades: a biblioteca mostraria a imagem do
            # master e a página do job mostraria a outra, com os dois hashes
            # discordando em silêncio. Os bytes desta execução são descartados —
            # eles foram pagos, mas publicar dois arquivos como se fossem um só
            # é pior que perder um.
            await self.repo.atualizar_rendition(
                job_id, slot,
                {
                    "estado": "pronta",
                    "master_id": master["id"],
                    "largura": master.get("largura"),
                    "altura": master.get("altura"),
                    "bytes_totais": master.get("bytes_totais"),
                    "mime": master.get("mime"),
                    "storage_chave": master.get("storage_chave"),
                    "content_hash": master.get("content_hash"),
                    "concluida_em": agora(),
                    "erro_codigo": None, "erro_mensagem": None,
                    "erro_permanente": None, "erro_em": None,
                },
            )
            return
        await self.repo.atualizar_rendition(
            job_id,
            slot,
            {
                "estado": "pronta",
                "master_id": master["id"],
                "largura": arquivo.largura,
                "altura": arquivo.altura,
                "bytes_totais": len(dados) or None,
                "mime": mime,
                "storage_chave": chave,
                "content_hash": content_hash,
                "nativo_largura": _int_ou_none(meta.get("nativo_largura")),
                "nativo_altura": _int_ou_none(meta.get("nativo_altura")),
                "canvas_largura": _int_ou_none(meta.get("canvas_largura")),
                "canvas_altura": _int_ou_none(meta.get("canvas_altura")),
                # `recomposto` e o rotulo que a v11_01 ja reservou para a peca
                # que passou por um compositor. Deixa-la como `cover_crop` diria
                # que so houve recorte, quando houve colagem de fotografia real.
                "enquadramento": (
                    "recomposto" if composta is not None else meta.get("enquadramento")
                ),
                "transformacoes": (
                    list(composta.transformacoes)
                    if composta is not None
                    else [t for t in (meta.get("transformacoes") or "").split(" | ") if t]
                ),
                **(
                    {
                        "crop_x": composta.crop[0],
                        "crop_y": composta.crop[1],
                        "crop_largura": composta.crop[2],
                        "crop_altura": composta.crop[3],
                        "escala": composta.escala,
                        "posicao_x": composta.posicao[0],
                        "posicao_y": composta.posicao[1],
                        "compositor": composta.compositor,
                        "compositor_versao": composta.compositor_versao,
                    }
                    if composta is not None
                    else {}
                ),
                "concluida_em": agora(),
                "erro_codigo": None,
                "erro_mensagem": None,
                "erro_permanente": None,
                "erro_em": None,
            },
        )
        await self.repo.registrar_evento(
            job_id, "peca_pronta", f"{formato.rotulo} pronta.", slot=slot
        )

    def _chamar_motor(
        self,
        slot: str,
        formato: dominio.Formato,
        insumo: str,
        *,
        modo: str = "sem_foto",
        foto: bytes | None = None,
        foto_mime: str | None = None,
    ) -> RespostaDoMotor:
        """A única chamada ao provider, e o que muda em cada modo.

        `hibrido`   a foto NÃO vai ao provider. Ele recebe a instrução de deixar
                    a região vazia; a fotografia é colada depois, aqui dentro.
                    Mandá-la como referência faria o modelo desenhar uma pessoa
                    parecida, e a peça final teria duas: a desenhada e a colada.

        `reinterpretado`  a foto vai como referência e o modelo redesenha a
                    cena. É outro produto, e a interface diz isso.
        """
        from volc_ads.criativo.porta import ImagemDeReferencia  # noqa: PLC0415

        texto = insumo
        referencias: tuple[Any, ...] = ()
        if modo == "hibrido":
            from .studio.composicao import instrucao_de_fundo  # noqa: PLC0415

            texto = f"{insumo}\n\n{instrucao_de_fundo(slot)}"
        elif modo == "reinterpretado" and foto:
            referencias = (
                ImagemDeReferencia(
                    nome=f"referencia.{_EXTENSAO_POR_MIME.get(foto_mime or '', 'png')}",
                    conteudo=foto,
                    mime=foto_mime or "image/png",
                ),
            )

        pedido = PedidoDeGeracao(
            referencia=f"estudio/{slot}",
            tipo=formato.tipo,
            insumo=texto,
            especificacao=formato.especificacao(),
            contexto={"formato": formato.rotulo},
            referencias=referencias,
        )
        return self.motor.receber(self.motor.solicitar_geracao(pedido))

    def _ler_anexo(self, chave: str) -> bytes | None:
        """Os bytes da fotografia guardada, ou `None` quando ela não abre.

        `None` e não exceção: uma peça produzida sem a foto que o operador
        anexou seria uma peça DIFERENTE da pedida, então quem chama trata a
        ausência como falha da peça — mas a leitura em si não derruba o lote.
        """
        try:
            return self.armazenamento.ler(chave)
        except Exception:  # noqa: BLE001
            log.exception("não foi possível ler o anexo em %s", chave)
            return None

    async def _marcar_falha_da_peca(
        self, job_id: str, slot: str, erro: ErroDoMotor
    ) -> None:
        """A peça falha sozinha. As outras do lote continuam válidas."""
        falha = dominio.Falha(
            codigo=getattr(erro, "codigo", "MOTOR.desconhecido"),
            mensagem=str(erro),
            permanente=bool(getattr(erro, "permanente", False)),
            em=agora(),
        )
        await self.repo.atualizar_rendition(
            job_id,
            slot,
            {
                "estado": "falhou",
                "erro_codigo": falha.codigo,
                "erro_mensagem": falha.mensagem,
                "erro_permanente": falha.permanente,
                "erro_em": falha.em,
            },
        )
        await self.repo.registrar_evento(
            job_id, "peca_falhou", falha.mensagem, slot=slot,
            detalhe={"codigo": falha.codigo, "permanente": falha.permanente},
        )

    async def _fechar(self, job_id: str, *, cancelado: bool = False) -> None:
        """O único lugar que monta o PATCH final de um job.

        Único de propósito: enquanto havia dois, um deles esquecia `falha` e
        quebrava a CHECK exatamente no caso mais incômodo (cancelar um lote que
        já tinha peça falhada). Um caminho só significa que a coerência dos
        campos terminais é escrita uma vez.
        """
        renditions = await self.repo.renditions_do_job(job_id)
        estados = [r["estado"] for r in renditions]
        estado = dominio.estado_do_lote(estados)
        # Uma peça presa em `gerando` (processo morreu no meio) agregaria para
        # `running` junto com `terminado_em`, e o job viraria um tijolo: retry
        # recusa `running`, cancelar grava pedido que ninguém confirma. Fechar
        # um job com peça em voo é declarar a peça perdida, não fingir que ela
        # ainda vive.
        if estado == "running":
            for r in renditions:
                if r["estado"] in ("pendente", "gerando"):
                    await self.repo.atualizar_rendition(
                        job_id, r["slot"],
                        {
                            "estado": "falhou",
                            "erro_codigo": "JOB.interrompido",
                            "erro_mensagem": "A produção parou antes desta peça terminar.",
                            "erro_permanente": False,
                            "erro_em": agora(),
                        },
                    )
            renditions = await self.repo.renditions_do_job(job_id)
            estado = dominio.estado_do_lote([r["estado"] for r in renditions])
        campos: dict[str, Any] = {"estado": estado, "terminado_em": agora()}
        if cancelado:
            campos["cancelado_em"] = agora()
        if estado == "failed":
            primeira = next(
                (r for r in renditions if r.get("erro_codigo")), None
            )
            campos["falha"] = dominio.Falha(
                codigo=(primeira or {}).get("erro_codigo") or "JOB.sem_peca",
                mensagem=(primeira or {}).get("erro_mensagem")
                or "Nenhuma peça foi produzida.",
                permanente=bool((primeira or {}).get("erro_permanente")),
                em=agora(),
            ).para_dict()
        else:
            # A CHECK `criativo_job_falha_coerente` recusa falha fora de
            # `failed`. Limpar aqui é o que permite um retry bem-sucedido apagar
            # a falha de antes em vez de carregá-la para sempre.
            campos["falha"] = None
        await self.repo.atualizar_job(job_id, campos)
        await self.repo.registrar_evento(job_id, "fim", _frase_de_fim(estado, renditions))

    async def _encerrar_por_defeito(self, job_id: str) -> None:
        # `iniciado_em` junto: a CHECK `criativo_job_ordem_temporal` recusa
        # término sem início, e um job que morreu ANTES de marcar o início
        # deixava a escrita abortar. O `contextlib.suppress` de quem chama
        # engolia isso, e o job ficava `queued` para sempre: retry recusa
        # (`pode_retentar('queued')` é falso) e cancelar grava um pedido que
        # ninguém confirma. O handler de defeito era o único que não conseguia
        # registrar o defeito.
        atual = await self.repo.buscar_job(job_id)
        instante = agora()
        await self.repo.atualizar_job(
            job_id,
            {
                "estado": "failed",
                "iniciado_em": (atual or {}).get("iniciado_em") or instante,
                "terminado_em": instante,
                "falha": dominio.Falha(
                    codigo="JOB.interrompido",
                    mensagem="A produção foi interrompida por uma falha interna.",
                    permanente=False,
                    em=agora(),
                ).para_dict(),
            },
        )
        await self.repo.registrar_evento(job_id, "fim", "A produção foi interrompida.")

    # ── retry e cancelamento ─────────────────────────────────────────────────

    async def retentar(
        self, job_id: str, *, criado_por: str | None = None
    ) -> dict[str, Any]:
        """Repõe as peças que faltaram. É um ato que GASTA.

        ⚠️ Duas conferências que não existiam.

        `criado_por` chega até `buscar_job`: sem ele, quem tivesse o UUID de um
        job alheio — de um print, de um log — recolocava o trabalho de outra
        pessoa na fila e fazia o provider cobrá-la. `JobNaoEncontrado` é o mesmo
        404 de "não existe", porque distinguir os dois transforma a rota num
        oráculo de existência de job alheio.

        E a transição é compare-and-set: o filtro de estado viaja no PATCH. Dois
        processos que leiam o mesmo job `failed` no mesmo segundo passavam os
        dois pelo `pode_retentar` e disparavam os dois laços.
        """
        job = await self.repo.buscar_job(job_id, criado_por=criado_por)
        if job is None:
            raise JobNaoEncontrado(job_id)
        if not dominio.pode_retentar(job["estado"]):
            raise TransicaoInvalida(
                f"não há o que retentar num job em '{job['estado']}'"
            )
        atualizado = await self.repo.atualizar_job(
            job_id,
            {
                "estado": "queued",
                "tentativa": int(job.get("tentativa") or 1) + 1,
                "terminado_em": None,
                "falha": None,
                "cancelado_pedido_em": None,
                "cancelado_em": None,
            },
            estados_esperados=list(dominio.ESTADOS_QUE_RETENTAM),
        )
        if atualizado is None:
            # O banco não devolveu linha: outro processo já retomou este job
            # entre a nossa leitura e a nossa escrita. Não disparar é o ponto.
            raise TransicaoInvalida(
                "este trabalho já foi retomado por outra execução"
            )
        prontas = sum(
            1 for r in await self.repo.renditions_do_job(job_id) if r["estado"] == "pronta"
        )
        await self.repo.registrar_evento(
            job_id,
            "retry",
            f"Nova tentativa. As {prontas} peça(s) já prontas serão preservadas."
            if prontas
            else "Nova tentativa.",
        )
        self.disparar(job_id)
        return atualizado or job

    async def cancelar(
        self, job_id: str, *, criado_por: str | None = None
    ) -> dict[str, Any]:
        """Pede o cancelamento. `criado_por` confina: cancelar DESTRÓI trabalho pago."""
        job = await self.repo.buscar_job(job_id, criado_por=criado_por)
        if job is None:
            raise JobNaoEncontrado(job_id)
        if not dominio.pode_cancelar(job["estado"]):
            raise TransicaoInvalida(f"job em '{job['estado']}' não pode ser cancelado")
        atualizado = await self.repo.atualizar_job(
            job_id, {"cancelado_pedido_em": agora()}
        )
        await self.repo.registrar_evento(
            job_id,
            "cancelando",
            "Cancelamento pedido. A peça em produção termina; as seguintes não começam.",
        )
        return atualizado or job

    async def _confirmar_cancelamento(self, job_id: str) -> None:
        """Confirma o cancelamento e fecha o job pelo MESMO caminho de `_fechar`.

        ⚠️ Antes ele montava o PATCH à mão, sem o campo `falha`, e isso quebrava
        num caso concreto: um lote com uma peça já `falhou` e o resto cancelado
        agrega para `failed`, e a CHECK `criativo_job_falha_coerente` exige
        objeto de falha nesse estado. O PATCH abortava, o `except` de cima
        chamava `_encerrar_por_defeito`, e o operador que clicou em interromper
        recebia "A produção foi interrompida por uma falha interna".

        Cancelar não é falhar, e o registro não pode dizer que foi.
        """
        for rend in await self.repo.renditions_do_job(job_id):
            if rend["estado"] in ("pendente", "gerando"):
                await self.repo.atualizar_rendition(
                    job_id, rend["slot"], {"estado": "cancelada"}
                )
        await self._fechar(job_id, cancelado=True)
        await self.repo.registrar_evento(job_id, "fim", "Produção cancelada.")


# Referências fortes às tarefas em voo. Ver `disparar`.
# ⚠️ `_TAREFAS` foi removido junto com o `asyncio.create_task`. Ele existia para
# segurar referência forte a uma task que o coletor de lixo poderia recolher no
# meio — um remendo para um mecanismo que não devia estar ali. Sem task solta,
# não há referência a segurar.


# ─────────────────────────────────────────────────────────────────────────────
# Auxiliares
# ─────────────────────────────────────────────────────────────────────────────


def _referencias_do_pedido(pedido: dict[str, Any]) -> list[dict[str, Any]]:
    """O material de entrada do briefing, em forma de lista tipada.

    Lista e nao campo solto porque `referencias` ja era uma lista e porque um dia
    havera mais de um material (logo, paleta, produto). Cada item se identifica
    pelo `tipo`, entao acrescentar o segundo nao muda a leitura do primeiro.
    """
    chave = pedido.get("anexo_storage_chave")
    if not chave:
        return []
    return [
        {
            "tipo": "fotografia",
            "modo": pedido.get("modo_de_composicao") or "sem_foto",
            "anexo_ref": pedido.get("anexo_ref"),
            "sha256": pedido.get("anexo_sha256"),
            "storage_chave": chave,
            "mime": pedido.get("anexo_mime") or "image/png",
        }
    ]


def _fotografia_do_briefing(briefing: dict[str, Any]) -> dict[str, Any]:
    """A fotografia deste briefing, ou um dicionario vazio.

    Vazio e nao `None` para que quem chama leia `.get("modo")` sem um `if` antes:
    a ausencia de foto e o caso normal, e o caminho normal nao deve ser o que
    precisa de guarda.
    """
    for item in briefing.get("referencias") or []:
        if isinstance(item, dict) and item.get("tipo") == "fotografia":
            return item
    return {}


def _insumo_do_briefing(pedido: dict[str, Any]) -> str:
    partes = [
        (pedido.get("mensagem") or "").strip(),
        (pedido.get("objetivo") or "").strip(),
    ]
    audiencia = (pedido.get("audiencia") or "").strip()
    if audiencia:
        partes.append(f"Público: {audiencia}.")
    return "\n".join(p for p in partes if p) or "Peça publicitária institucional."


def _estimativa(n_pecas: int, motor: Any) -> float | None:
    """A estimativa gravada em `criativo_job.custo_estimado_usd`, ou `None`.

    ⚠️ Duas correções na mesma linha.

    A primeira: o preço vinha do motor GEMINI, importado direto, sem olhar para o
    motor que ia rodar. Com outro provider instalado, a coluna guardava o preço
    de um motor que nunca foi chamado — um número plausível, conferível, e
    errado.

    A segunda: o resultado era sempre `float`. Um motor sem preço publicado — que
    é o caso do `gpt-image-2`, cobrado por token — produziria `0.0`, e um custo
    estimado de zero gravado ao lado de um gasto real é a mentira mais barata de
    contar e a mais cara de descobrir. `None` vira NULL na coluna, que é o que
    "não sei" quer dizer em SQL.
    """
    preco = getattr(motor, "preco_referencia_usd_por_imagem", None)
    if preco is None:
        # Motor legado que publica o preço só como constante de módulo: aceito,
        # porque quem sabe o preço é o motor e não este arquivo.
        preco = getattr(motor, "PRECO_REFERENCIA_USD_POR_IMAGEM", None)
    try:
        valor = float(preco) if preco is not None else 0.0
    except (TypeError, ValueError):
        return None
    if not valor:
        return None
    return round(n_pecas * valor, 6)


def _int_ou_none(valor: Any) -> int | None:
    try:
        n = int(str(valor))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _erro_generico(motivo: str) -> ErroDoMotor:
    erro = ErroDoMotor(motivo)
    erro.codigo = "MOTOR.desconhecido"
    return erro


def _frase_de_fim(estado: str, renditions: list[dict[str, Any]]) -> str:
    prontas = sum(1 for r in renditions if r["estado"] == "pronta")
    total = len(renditions)
    if estado == "succeeded":
        return f"Concluído. {prontas} de {total} peça(s) prontas."
    if estado == "partial":
        return f"Parcial. {prontas} de {total} peça(s) prontas."
    if estado == "cancelled":
        return "Cancelado."
    return "Nenhuma peça foi produzida."


def utc_agora() -> datetime:
    return datetime.now(timezone.utc)
