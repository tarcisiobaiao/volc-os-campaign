"""O operario: pega um trabalho, produz, valida e assina o recibo.

## O ciclo, e onde cada estado entra

    reivindicar -> CLAIMED
                -> RUNNING     (o motor comecou)
                -> VALIDATING  (o arquivo existe; falta saber se serve)
                -> RENDERED    (com recibo) | FAILED (com motivo)

⚠️ `VALIDATING` nao e cerimonia. Se o trabalho ja fosse `rendered` antes do gate
rodar, o gate nao decidiria nada — e um gate que nao pode reprovar e decoracao.

## Diretorio por trabalho

Cada trabalho recebe um diretorio proprio, criado na hora e nunca reaproveitado.
Isto e a resposta direta ao defeito medido na fabrica: 21 dos 26 geradores
escrevem em `clips_registry.json`, `timings.json` e `props.json` na raiz, e por
isso dois renders simultaneos la se contaminam. Aqui, dois trabalhos nao tem
nenhum caminho em comum para disputar.

## Batimento

Uma thread bate o coracao enquanto o motor trabalha. Se o processo morrer, o
batimento para, o lease vence e o trabalho volta para a fila — sem ninguem
precisar detectar a morte. Ausencia de batimento nao e tratada como execucao
ativa em lugar nenhum.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contrato import (
    Artefato,
    Aprovacao,
    Ausencia,
    Custo,
    Declarado,
    DestinoDoRecibo,
    Encomenda,
    EstadoDoTrabalho,
    FalhaDoMotor,
    InsumoSanitizado,
    MedidaDeAudio,
    MotorDeProducao,
    Procedencia,
    Recibo,
    RegistroDeStorage,
    TransicaoProibida,
    Validacao,
)
from .deposito import DepositoDeTrabalhos, Trabalho
from .sanitizacao import sanitizar_insumo

log = logging.getLogger(__name__)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _intervalo_s(inicio: str, fim: str) -> float:
    """Segundos entre dois carimbos ISO. `0.0` so quando eles sao iguais.

    Nao levanta: um recibo nao pode deixar de existir porque a subtracao de duas
    datas falhou. Quando nao da para ler, devolve `-1.0`, que e um valor
    IMPOSSIVEL para uma duracao e por isso legivel como "nao foi possivel medir"
    — ao contrario de `0.0`, que se confunde com "instantaneo".
    """
    try:
        return max(
            0.0,
            (datetime.fromisoformat(fim) - datetime.fromisoformat(inicio)).total_seconds(),
        )
    except (TypeError, ValueError):
        return -1.0


def _sha256_do_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


#: MIMEs cuja dimensao este operario SABE medir. Um artefato que declara um
#: destes e nao abre nao e "formato desconhecido": e arquivo quebrado.
#:
#: ⚠️ `video/mp4` ENTROU. Enquanto ele nao estava aqui, um artefato de video caia
#: no ramo `SKIPPED` nao-bloqueante — "nao sei medir a dimensao deste formato" —
#: e um mp4 de 640x360 declarando 1080x1920 chegava a `rendered` sem que nada
#: abrisse o arquivo. Era o mesmo defeito que a contraprova de dimensao fechou
#: para imagem, sobrevivendo na midia que ninguem produzia ainda.
_MIMES_MENSURAVEIS = frozenset({"image/png", "image/jpeg", "image/gif", "video/mp4"})

#: MIMEs medidos por `ffprobe` e nao pelo leitor de cabecalho de imagem.
_MIMES_DE_VIDEO = frozenset({"video/mp4"})


def _medir_dimensao(caminho: Path) -> tuple[int, int] | None:
    """Largura e altura LIDAS DO ARQUIVO. `None` quando nao da para saber.

    ⚠️ `None` e ausencia de medicao, nunca `(0, 0)`. O medidor le o cabecalho do
    formato com a biblioteca padrao (PNG, GIF, JPEG) e ja recusa o caso classico
    do IHDR todo zero. Para video a leitura e do `ffprobe`, que tambem devolve
    ausencia em vez de zero.
    """
    try:
        from volc_ads.criativo.adaptadores.medir_imagem import medir  # noqa: PLC0415

        m = medir(caminho.read_bytes())
    except Exception:  # noqa: BLE001 — medidor ausente ou arquivo ilegivel
        return None
    if m.largura is None or m.altura is None:
        return None
    return (m.largura, m.altura)


def _medir_dimensao_de_video(caminho: Path) -> tuple[int, int] | None:
    try:
        from volc_ads.criativo.adaptadores.medir_video import medir  # noqa: PLC0415

        m = medir(str(caminho))
    except Exception:  # noqa: BLE001 — ffprobe ausente ou arquivo ilegivel
        return None
    if m.largura is None or m.altura is None:
        return None
    return (m.largura, m.altura)


def _mime_medido(caminho: Path) -> str | None:
    """O MIME lido da ASSINATURA do arquivo. `None` quando nao da para saber.

    ⚠️ ACHADO ADVERSARIAL (02/09/2026), reproduzido por execucao. O MIME
    percorria o sistema inteiro DECLARADO pelo motor e nunca era medido, com o
    medidor pronto ao lado: `medir_imagem.mime_de` ja le a assinatura, e o
    proprio `Medida.mime` ja vinha preenchido e era descartado.

    Contraprova: um motor que grava PNG e declara `image/jpeg` chegava a
    `rendered` com o gate `dimensao` PASS — porque `_dimensao_do_artefato`
    escolhe o medidor pelo MIME declarado, e um PNG declarado como JPEG cai no
    leitor de imagem, que le PNG. O recibo saia dizendo `image/jpeg`, a chave de
    storage terminava em `.jpg`, o `Content-Type` do upload ia `image/jpeg`, e o
    storage dizia `VERIFIED_OK` — porque a releitura confere BYTES, e os bytes
    estavam certos. Tudo verde sobre um arquivo cujo tipo o sistema inteiro
    descrevia errado.

    O dano nao e interno: um endereco `.jpg` servido com `Content-Type:
    image/jpeg` sobre bytes PNG e o que chega ao navegador do cliente e ao
    upload para o destino.
    """
    try:
        from volc_ads.criativo.adaptadores.medir_imagem import mime_de  # noqa: PLC0415

        return mime_de(caminho.read_bytes())
    except Exception:  # noqa: BLE001 — medidor ausente ou arquivo ilegivel
        return None


def _dimensao_do_artefato(a: Artefato, caminho: Path) -> tuple[int, int] | None:
    """Escolhe o medidor pelo MIME DECLARADO, e mede o ARQUIVO.

    Usar o MIME declarado para escolher o medidor nao e confiar nele: se o
    arquivo nao abrir como o formato declarado, a medida sai `None` e o gate
    reprova por `declarou um formato que sei medir e os bytes nao abrem`.
    """
    if a.mime in _MIMES_DE_VIDEO:
        return _medir_dimensao_de_video(caminho)
    return _medir_dimensao(caminho)


def _mensagem_para_o_operador(e: BaseException) -> str:
    """⚠️ ACHADO ADVERSARIAL. `str(e)` cru ia direto para a tela e trazia caminho
    de disco junto: "[Errno 28] No space left on device: '/var/folders/.../1x1.png'".
    O operador nao precisa do caminho e nao deveria ve-lo; o log precisa e o tem."""
    import re as _re

    texto = str(e) or type(e).__name__
    texto = _re.sub(r"(/|~/)[^\s'\"]{2,}", "<caminho>", texto)
    return texto[:280]


class Batimento:
    """Bate o coracao em segundo plano enquanto o bloco durar."""

    def __init__(self, deposito: DepositoDeTrabalhos, trabalho_id: str,
                 *, operario: str, intervalo_s: float | None = None,
                 lease_s: int = 60) -> None:
        self._d, self._id, self._operario = deposito, trabalho_id, operario
        # ⚠️ O intervalo era FIXO em 5s enquanto `lease_s` era parametro:
        # qualquer `Operario(lease_s<=5)` era, por construcao, uma configuracao
        # SEM batimento — e nada avisava. Agora ele acompanha o lease.
        self._intervalo = intervalo_s if intervalo_s is not None else max(0.2, lease_s / 3)
        self._lease = lease_s
        self._parar = threading.Event()
        self._t: threading.Thread | None = None
        self.batidas = 0
        #: `True` quando o deposito recusou um batimento — o trabalho saiu das
        #: maos deste operario (lease vencido e reivindicado por outro).
        self.perdeu_o_trabalho = False

    def __enter__(self) -> Batimento:
        def laco() -> None:
            while not self._parar.wait(self._intervalo):
                if self._d.bater(self._id, lease_s=self._lease, operario=self._operario):
                    self.batidas += 1
                else:
                    self.perdeu_o_trabalho = True
                    return

        self._t = threading.Thread(target=laco, daemon=True, name=f"batimento-{self._id[:8]}")
        self._t.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self._parar.set()
        if self._t:
            self._t.join(timeout=2)


class Operario:
    """Um trabalhador. Varios podem existir no mesmo processo ou em processos
    diferentes; o deposito e que arbitra quem pega o que."""

    def __init__(
        self,
        deposito: DepositoDeTrabalhos,
        motores: dict[str, MotorDeProducao],
        raiz_de_trabalho: str | Path,
        *,
        nome: str | None = None,
        lease_s: int = 60,
        loja: Any | None = None,
    ) -> None:
        self.deposito = deposito
        self.motores = motores
        self.raiz = Path(raiz_de_trabalho)
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.nome = nome or f"operario-{uuid.uuid4().hex[:8]}"
        self.lease_s = lease_s
        # ⚠️ `None` NAO e "sem armazenamento configurado, tanto faz": e um
        # operario que produz e nao guarda, e o recibo diz isso com nome
        # (`nao_publicado` / `NAO_APLICAVEL`) em vez de deixar `storage` vazio.
        # Quem monta a bancada de producao (`servico.montar`) passa a loja; um
        # operario de teste que so quer exercitar a fila nao precisa dela, e a
        # diferenca fica escrita no recibo em vez de escondida.
        self.loja = loja

    # ── um trabalho ──────────────────────────────────────────────────────────

    def trabalhar_uma_vez(self) -> Trabalho | None:
        """Pega um trabalho da fila e o leva ao fim. `None` se a fila estiver vazia."""
        trabalho = self.deposito.reivindicar(self.nome, lease_s=self.lease_s)
        if trabalho is None:
            return None
        return self.executar(trabalho)

    def executar(self, trabalho: Trabalho) -> Trabalho:
        motor = self.motores.get(trabalho.encomenda.motor_slug)
        if motor is None:
            return self.deposito.transicionar(
                trabalho.id,
                EstadoDoTrabalho.FAILED,
                falha={
                    "codigo": "motor_desconhecido",
                    "mensagem": (
                        f"nenhum motor registrado com o slug "
                        f"`{trabalho.encomenda.motor_slug}`"
                    ),
                    "permanente": True,
                },
            )

        # Diretorio exclusivo POR REIVINDICACAO, nao por trabalho.
        #
        # ⚠️ ACHADO #13. Era `self.raiz / trabalho.id`, e o id NAO muda quando o
        # lease vence e outro operario reivindica o mesmo trabalho: os dois
        # produziam no MESMO caminho. Duas consequencias medidas em teste:
        #   · quem perdia o lease apagava o diretorio de quem o pegou;
        #   · o arquivo que o novo dono validava podia ser o byte que o operario
        #     anterior deixou ali, com o mesmo nome de slot.
        # Com um nivel a mais por reivindicacao, cada operario limpa o que e seu
        # sem alcancar o do outro — os dois invariantes (nao vazar arquivo e nao
        # destruir trabalho alheio) deixam de se contradizer.
        dir_trabalho = self.raiz / trabalho.id / self._pasta_da_reivindicacao(trabalho)
        dir_trabalho.mkdir(parents=True, exist_ok=True)
        iniciado = _agora()

        with Batimento(self.deposito, trabalho.id, operario=self.nome,
                       lease_s=self.lease_s) as batimento:
            try:
                self.deposito.transicionar(
                    trabalho.id, EstadoDoTrabalho.RUNNING,
                    exigir_operario=self.nome, exigir_tentativa=trabalho.tentativa,
                )
                artefatos = motor.produzir(trabalho.encomenda, str(dir_trabalho))

                if not artefatos:
                    raise FalhaDoMotor("o motor nao produziu artefato", permanente=True)

                # ⚠️ A conferencia de cancelamento vem ANTES de `validating`. Na
                # versao anterior ela vinha antes de `rendered`, e nunca era
                # alcancada: `cancelled` e terminal, entao a transicao para
                # `validating` ja estourava `TransicaoProibida`, o fluxo caia no
                # `except Exception` generico e o diretorio ficava no disco.
                if self._foi_cancelado(trabalho.id):
                    log.info("trabalho %s cancelado durante a producao", trabalho.id)
                    self._apagar_nosso_diretorio(dir_trabalho)
                    return self.deposito.por_id(trabalho.id) or trabalho

                # Checkpoint 1 (achado #13): o motor pode ter demorado mais que o
                # lease. ANTES de avançar estado, validar ou montar recibo,
                # pergunta de quem é o trabalho agora. Se não é nosso, saímos sem
                # transição e sem recibo — levando só o que produzimos.
                if not self._ainda_sou_dono_da_reivindicacao(trabalho, batimento):
                    return self._largar(trabalho, dir_trabalho)

                self.deposito.transicionar(
                    trabalho.id, EstadoDoTrabalho.VALIDATING,
                    exigir_operario=self.nome, exigir_tentativa=trabalho.tentativa,
                )
                validacoes = self._validar(
                    trabalho.encomenda, artefatos, motor, str(dir_trabalho)
                )

                reprovou = [v for v in validacoes if v.bloqueante and v.resultado == "FAIL"]
                if reprovou:
                    # ⚠️ ACHADO ADVERSARIAL (revisão de 2026-08-29). Esta era a
                    # ÚNICA saída irreversível sem trava de posse: o zumbi cujo
                    # gate reprovava marcava como falho o trabalho que já era de
                    # outro operário, e ainda soltava o dono. O checkpoint acima
                    # não alcança este ramo — ele roda antes da validação, e a
                    # perda aqui acontece durante ela.
                    if not self._ainda_sou_dono_da_reivindicacao(trabalho, batimento):
                        return self._largar(trabalho, dir_trabalho)
                    return self.deposito.transicionar(
                        trabalho.id,
                        EstadoDoTrabalho.FAILED,
                        falha={
                            "codigo": "gate_reprovou",
                            "mensagem": "; ".join(v.gate for v in reprovou),
                            "permanente": True,
                            "validacoes": [asdict(v) for v in validacoes],
                        },
                        exigir_operario=self.nome,
                        exigir_tentativa=trabalho.tentativa,
                    )

                # A publicacao acontece DEPOIS de os gates aprovarem e ANTES do
                # recibo: subir o que o gate reprovaria seria pagar
                # armazenamento por peca que nao serve, e assinar o recibo antes
                # de publicar faria `storage` nascer sempre vazio.
                storage = self._publicar(trabalho, artefatos)
                medida_de_audio, audio_ausente = self._audio(
                    motor, trabalho.encomenda, str(dir_trabalho)
                )
                custo = self._custo(motor, trabalho.encomenda)
                terminado = _agora()
                recibo = Recibo(
                    trabalho_id=trabalho.id,
                    chave_de_idempotencia=trabalho.chave_idempotencia,
                    produzido_por=self.nome,
                    motor_slug=motor.slug,
                    motor_versao=motor.versao,
                    seed=trabalho.encomenda.seed,
                    versoes=motor.versoes_congeladas(),
                    parametros=dict(trabalho.encomenda.parametros),
                    artefatos=artefatos,
                    validacoes=tuple(validacoes),
                    audio=medida_de_audio,
                    iniciado_em=iniciado,
                    terminado_em=terminado,
                    # ⚠️ Os dois campos antigos continuam existindo e continuam
                    # espelhando `custo` — mas agora TEM produtor, e a razao da
                    # ausencia mora ao lado deles em vez de se perder no `None`.
                    custo_estimado_usd=custo.estimado_usd.valor,
                    custo_real_usd=custo.real_usd.valor,
                    procedencia=self._procedencia(trabalho, motor),
                    insumo=self._insumo(trabalho.encomenda),
                    hashes_de_entrada=self._hashes_de_entrada(
                        motor, trabalho.encomenda, str(dir_trabalho)
                    ),
                    tentativa=trabalho.tentativa,
                    custo=custo,
                    duracao_do_trabalho_s=_intervalo_s(iniciado, terminado),
                    storage=storage,
                    destinos=self._destinos(artefatos),
                    # ⚠️ Nasce `aguardando`, sempre. Um recibo que nascesse
                    # `aprovado` faria o operario aprovar em nome de uma pessoa —
                    # e a aprovacao humana existe justamente porque a maquina nao
                    # pode dar essa resposta.
                    aprovacao=Aprovacao(estado="aguardando"),
                    audio_ausente_porque=audio_ausente,
                    video_ausente_porque=self._video_ausente_porque(artefatos),
                )
                corpo = asdict(recibo)
                corpo["assinatura_determinista"] = recibo.assinatura_determinista()
                # ⚠️ Se o batimento foi recusado no meio, outro operario pode ter
                # reivindicado este trabalho. Concluir aqui gravaria um recibo por
                # cima do trabalho de outro. A transicao falha, e e assim que tem
                # de ser: o deposito e o arbitro, nao a boa vontade do operario.
                # ⚠️ ACHADO ADVERSARIAL. A guarda existia, logava e CONCLUIA
                # assim mesmo — o comentario dizia "a transicao falha" e ela nao
                # falhava. Resultado medido: o operario que PERDEU o lease
                # gravava o recibo por cima do trabalho de quem o pegou, e o
                # arquivo apontado pelo recibo nao existia mais.
                # ⚠️ O trabalho pode ter sido CANCELADO enquanto o motor
                # produzia. Concluir aqui ressuscitaria um trabalho que alguem
                # mandou parar — e `cancelled` e terminal, entao a transicao
                # falharia de qualquer jeito; conferir antes evita gravar um
                # recibo que ninguem vai ler e diz o que aconteceu no log.
                if self._foi_cancelado(trabalho.id):
                    log.info("trabalho %s cancelado durante a validacao", trabalho.id)
                    self._apagar_nosso_diretorio(dir_trabalho)
                    return self.deposito.por_id(trabalho.id) or trabalho
                # Checkpoint 2 (achado #13): última conferência antes de GRAVAR
                # RECIBO. O `exigir_operario` abaixo já recusaria, mas cair no
                # `except` genérico levava ao tratamento de falha — que apagava o
                # diretório do novo dono. Sair aqui é sair pela porta.
                if not self._ainda_sou_dono_da_reivindicacao(trabalho, batimento):
                    return self._largar(trabalho, dir_trabalho)
                return self.deposito.transicionar(
                    trabalho.id, EstadoDoTrabalho.RENDERED, recibo=corpo,
                    exigir_operario=self.nome, exigir_tentativa=trabalho.tentativa,
                )

            except FalhaDoMotor as e:
                log.warning("trabalho %s recusado pelo motor: %s", trabalho.id, e)
                return self._falhar(trabalho, "motor_recusou",
                                    _mensagem_para_o_operador(e), e.permanente,
                                    dir_trabalho)
            except Exception as e:  # noqa: BLE001 — o operario nao pode morrer calado
                log.exception("falha inesperada no trabalho %s", trabalho.id)
                return self._falhar(trabalho, "falha_inesperada",
                                    _mensagem_para_o_operador(e), False, dir_trabalho)

    def _foi_cancelado(self, trabalho_id: str) -> bool:
        t = self.deposito.por_id(trabalho_id)
        return t is not None and t.estado is EstadoDoTrabalho.CANCELLED

    # ── posse ────────────────────────────────────────────────────────────────
    #
    # ⚠️ ACHADO #13. `Batimento.perdeu_o_trabalho` era escrita e nunca lida. O
    # depósito recusava as TRANSIÇÕES de quem não é mais dono, então estado e
    # recibo estavam protegidos — mas o operário seguia produzindo, validando e
    # montando recibo para no fim cair no tratamento de falha, que apaga o
    # diretório. E o diretório é `raiz/<id do trabalho>`: o MESMO caminho que o
    # novo dono está usando. Medido em teste: quem perdeu o lease apagava a peça
    # de quem o pegou.
    #
    # A bandeira sozinha não basta (ela é escrita por outra thread e só vira
    # `True` na próxima batida), então ela é o sinal BARATO e o depósito é a
    # palavra final. As duas juntas: a bandeira evita gastar validação à toa, e a
    # consulta ao depósito decide qualquer coisa irreversível.

    def _dono_agora(self, trabalho_id: str) -> str | None:
        t = self.deposito.por_id(trabalho_id)
        return None if t is None else t.operario

    def _ainda_sou_dono_da_reivindicacao(
        self, trabalho: Trabalho, batimento: Batimento
    ) -> bool:
        """A posse é da REIVINDICAÇÃO, não do nome.

        ⚠️ ACHADO ADVERSARIAL (revisão de 2026-08-29). Comparar só
        `operario == self.nome` deixava o zumbi reconhecer a si mesmo: quando o
        MESMO operário reivindica de novo o mesmo trabalho — e reivindicar sempre
        incrementa `tentativa` —, o zumbi da tentativa anterior via o próprio
        nome no banco, achava que continuava dono e concluía por cima da
        reivindicação nova, gravando recibo que aponta para o diretório velho.

        `(operario, tentativa)` é o token de cerca que o banco já mantinha: nome
        diz QUEM, tentativa diz QUAL VEZ. E um lease vencido não é posse, mesmo
        que o nome ainda esteja lá — é só um recolhedor que ainda não passou.
        """
        if batimento.perdeu_o_trabalho:
            return False
        atual = self.deposito.por_id(trabalho.id)
        if atual is None:
            return False
        return (
            atual.operario == self.nome
            and atual.tentativa == trabalho.tentativa
            and atual.vivo
        )

    @staticmethod
    def _pasta_da_reivindicacao(trabalho: Trabalho) -> str:
        """Um nome de pasta que só esta reivindicação usa.

        Sanitizado de propósito: o nome do operário vem de configuração, e um
        separador de caminho aí dentro escaparia da raiz de trabalho.
        """
        import re as _re

        limpo = _re.sub(r"[^A-Za-z0-9._-]", "-", str(trabalho.operario or "sem-dono"))
        return f"t{trabalho.tentativa}-{limpo[:64]}"

    def _apagar_nosso_diretorio(self, dir_trabalho: Path) -> None:
        """Apaga o diretório DESTA reivindicação, e só ele.

        Seguro por construção: o caminho carrega a tentativa e o operário, então
        ele nunca é o diretório em que outro dono está produzindo. O pai — a
        pasta do trabalho — só some quando fica vazio, para não levar junto o que
        outra reivindicação deixou lá.
        """
        shutil.rmtree(dir_trabalho, ignore_errors=True)
        try:
            dir_trabalho.parent.rmdir()
        except OSError:
            pass  # ainda há outra reivindicação ali dentro; deixa como está

    def _largar(self, trabalho: Trabalho, dir_trabalho: Path) -> Trabalho:
        """Sai de cena sem tocar em estado, recibo ou arquivo do novo dono.

        Levamos embora só o que produzimos: o diretório desta reivindicação não
        é o do novo dono, e ninguém vai lê-lo — nenhum recibo o aponta. Deixá-lo
        seria vazamento; o novo dono continua intacto no diretório dele.

        Não marcamos falha: perder o lease não torna o pedido inválido. O
        trabalho segue com quem o reivindicou, e a volta para a fila continua
        sendo decisão do depósito, pelo vencimento — não deste operário.
        """
        log.warning(
            "trabalho %s: perdemos o lease durante a produção; parando sem concluir",
            trabalho.id,
        )
        self._apagar_nosso_diretorio(dir_trabalho)
        return self.deposito.por_id(trabalho.id) or trabalho

    def _falhar(self, trabalho: Trabalho, codigo: str, mensagem: str,
                permanente: bool, dir_trabalho: Path) -> Trabalho:
        # Falha transitoria devolve para a fila (ainda dentro do teto de
        # tentativas); permanente encerra. Retentar o que nunca vai funcionar
        # gasta o mesmo dinheiro tres vezes.
        falha = {"codigo": codigo, "mensagem": mensagem, "permanente": permanente}
        if not permanente and trabalho.tentativa < trabalho.max_tentativas:
            # ⚠️ Apagar o diretorio so e seguro porque `exigir_operario` garante
            # que ainda somos donos. Sem essa trava, o `rmtree` apagava o
            # diretorio que OUTRO operario estava usando.
            try:
                devolvido = self.deposito.transicionar(
                    trabalho.id, EstadoDoTrabalho.QUEUED, falha=falha,
                    exigir_operario=self.nome, exigir_tentativa=trabalho.tentativa,
                )
            except TransicaoProibida:
                # ⚠️ ACHADO #13. Aqui estava o dano. O `rmtree` era incondicional
                # e o comentario anterior justificava assim: "perder a posse nao
                # apaga o fato de o diretorio ser NOSSO — nos o criamos". A
                # premissa e falsa: o caminho e `raiz/<id do trabalho>`, e o id
                # NAO muda quando outro operario reivindica. O diretorio que
                # apagavamos ja era o de quem estava produzindo agora.
                log.warning("trabalho %s: perdemos a posse antes de devolver a fila",
                            trabalho.id)
                self._apagar_nosso_diretorio(dir_trabalho)
                return self.deposito.por_id(trabalho.id) or trabalho
            self._apagar_nosso_diretorio(dir_trabalho)
            return devolvido
        try:
            return self.deposito.transicionar(
                trabalho.id, EstadoDoTrabalho.FAILED, falha=falha,
                exigir_operario=self.nome, exigir_tentativa=trabalho.tentativa,
            )
        except TransicaoProibida:
            return self.deposito.por_id(trabalho.id) or trabalho

    # ── validacao ────────────────────────────────────────────────────────────

    def _validar(
        self, encomenda: Encomenda, artefatos: tuple[Artefato, ...],
        motor: MotorDeProducao, dir_trabalho: str,
    ) -> list[Validacao]:
        validacoes: list[Validacao] = []
        pedido = {s.slot: s for s in encomenda.saidas}

        for a in artefatos:
            # ⚠️ ACHADO ADVERSARIAL. A primeira versao decidia tudo em cima do que
            # o MOTOR DECLAROU no `Artefato`: `bytes_` e `sha256` eram inteiros e
            # strings que o motor escreveu, nunca conferidos contra o disco. Um
            # motor que devolvesse `bytes_=4096, sha256="f"*64` sem escrever byte
            # nenhum chegava a `rendered`, com recibo, e a
            # `assinatura_determinista` virava o hash de uma ficcao: duas
            # execucoes com bytes diferentes davam a mesma assinatura. A
            # assinatura provava que o motor repetiu a AFIRMACAO, nao o pixel.
            caminho = Path(a.caminho)
            if not caminho.is_file():
                validacoes.append(Validacao(
                    gate="arquivo_no_disco", resultado="FAIL",
                    detalhe={"slot": a.slot,
                             "motivo": "o motor declarou um arquivo que nao existe"},
                    bloqueante=True))
                continue
            medido = caminho.stat().st_size
            if medido != a.bytes_:
                validacoes.append(Validacao(
                    gate="bytes_conferem", resultado="FAIL",
                    detalhe={"declarado": a.bytes_, "medido": medido}, bloqueante=True))
            hash_medido = _sha256_do_arquivo(caminho)
            if hash_medido != a.sha256:
                validacoes.append(Validacao(
                    gate="hash_confere", resultado="FAIL",
                    detalhe={"declarado": a.sha256[:16], "medido": hash_medido[:16]},
                    bloqueante=True))
            else:
                validacoes.append(Validacao(
                    gate="hash_confere", resultado="PASS",
                    detalhe={"sha256": hash_medido, "bytes": medido}, bloqueante=True))

            esperado = pedido.get(a.slot)
            if esperado is None:
                validacoes.append(Validacao(
                    gate="slot_pedido", resultado="FAIL",
                    detalhe={"slot": a.slot, "motivo": "produzido sem ter sido pedido"},
                    bloqueante=True))
                continue
            # ⚠️ ACHADO DESTA RODADA. O gate comparava `a.largura/a.altura` com o
            # pedido — e os DOIS lados eram numeros que o MOTOR escreveu. O
            # arquivo nunca era aberto. Este comentario, tres blocos acima, ja
            # conta que `bytes_` e `sha256` foram movidos para a medida do disco
            # por esse exato motivo; a dimensao ficou para tras.
            #
            # Contraprova em `contraprova_dimensao_declarada.py`: um motor que
            # grava 64x64 e declara 1200x628 chegava a `rendered`, com recibo, e
            # o gate dizia PASS {'pedido': [1200,628], 'produzido': [1200,628]}.
            # A peca nao serve a canal nenhum, e nada acusava.
            medida = _dimensao_do_artefato(a, caminho)
            if medida is None:
                # ⚠️ ACHADO NA PROPRIA CORRECAO. A primeira versao mandava TODO
                # nao-medivel para `SKIPPED` nao-bloqueante, e com isso um motor
                # que gravasse `b"x" * 128` declarando `image/png` e 640x480
                # passava — onde o gate antigo, que so olhava a declaracao,
                # REPROVAVA. Consertar um buraco abrindo outro.
                #
                # A distincao que faltava e entre duas ausencias diferentes:
                # "este medidor nao le mp4" e ausencia legitima; "declarou PNG e
                # os bytes nao abrem como PNG" e DEFEITO, e o mais grave dos
                # dois, porque nem arquivo de imagem ha.
                if a.mime in _MIMES_MENSURAVEIS:
                    validacoes.append(Validacao(
                        gate="dimensao", resultado="FAIL",
                        detalhe={"slot": a.slot,
                                 "pedido": [esperado.largura, esperado.altura],
                                 "declarado": [a.largura, a.altura],
                                 "mime_declarado": a.mime,
                                 "motivo": (
                                     "declarou um formato que sei medir e os bytes"
                                     " nao abrem como esse formato"
                                 )},
                        bloqueante=True))
                else:
                    # Ausencia de medicao NAO e aprovacao, mas tambem nao e
                    # reprovacao: fica SKIPPED, nao-bloqueante, com o motivo.
                    validacoes.append(Validacao(
                        gate="dimensao", resultado="SKIPPED",
                        detalhe={"slot": a.slot,
                                 "pedido": [esperado.largura, esperado.altura],
                                 "declarado": [a.largura, a.altura],
                                 "mime_declarado": a.mime,
                                 "motivo": "nao sei medir a dimensao deste formato"},
                        bloqueante=False))
            else:
                bate = medida == (esperado.largura, esperado.altura)
                validacoes.append(Validacao(
                    gate="dimensao", resultado="PASS" if bate else "FAIL",
                    # ⚠️ O `slot` entra no detalhe: com dois envelopes de mesma
                    # medida no mesmo pedido, nada dizia qual arquivo o gate
                    # julgou. E `declarado` fica como TERCEIRO numero, para o
                    # recibo guardar o que o motor afirmou ao lado do que o disco
                    # tem.
                    detalhe={"slot": a.slot,
                             "pedido": [esperado.largura, esperado.altura],
                             "medido": [medida[0], medida[1]],
                             "declarado": [a.largura, a.altura]},
                    bloqueante=True))
                if (a.largura, a.altura) != medida:
                    # Um motor que mente sobre a propria saida e um motor que nao
                    # se pode usar para decidir mais nada. Gate proprio, para o
                    # recibo distinguir "produziu do tamanho errado" de "mentiu".
                    validacoes.append(Validacao(
                        gate="dimensao_declarada_confere", resultado="FAIL",
                        detalhe={"slot": a.slot, "declarado": [a.largura, a.altura],
                                 "medido": [medida[0], medida[1]]},
                        bloqueante=True))
            # ⚠️ O MIME tambem e afirmacao do motor, e ate aqui ninguem a
            # conferia. Mesmo formato do gate de dimensao, e pelo mesmo motivo:
            # o que o motor DIZ e o que o arquivo E sao perguntas diferentes.
            medido = _mime_medido(caminho)
            if medido is None:
                # Ausencia de medicao nao e aprovacao nem reprovacao. `mime_de`
                # so conhece assinaturas de imagem; um mp4 legitimo cai aqui, e
                # reprovar por isso seria recusar a midia que o sistema produz.
                validacoes.append(Validacao(
                    gate="mime_declarado_confere", resultado="SKIPPED",
                    detalhe={"slot": a.slot, "declarado": a.mime,
                             "motivo": "nao sei ler a assinatura deste formato"},
                    bloqueante=False))
            else:
                validacoes.append(Validacao(
                    gate="mime_declarado_confere",
                    resultado="PASS" if medido == a.mime else "FAIL",
                    detalhe={"slot": a.slot, "declarado": a.mime,
                             "medido": medido},
                    bloqueante=True))

            validacoes.append(Validacao(
                gate="arquivo_nao_vazio",
                resultado="PASS" if a.bytes_ > 0 else "FAIL",
                detalhe={"bytes": a.bytes_}, bloqueante=True))

        faltando = sorted(set(pedido) - {a.slot for a in artefatos})
        if faltando:
            validacoes.append(Validacao(
                gate="cobertura_dos_slots", resultado="FAIL",
                detalhe={"nao_produzidos": faltando}, bloqueante=True))

        medir = getattr(motor, "medir_contraste", None)
        if callable(medir):
            m = medir(encomenda)
            # ⚠️ O NUMERO vai no detalhe. Um gate que so diz "passou" impede a
            # proxima pergunta: passou por quanto? A margem e o que decide se
            # vale ajustar.
            validacoes.append(Validacao(
                gate="contraste", resultado="PASS" if m["razao"] >= m["piso_aa"] else "FAIL",
                detalhe=m, bloqueante=True))
        else:
            # Ausencia de medicao NAO e aprovacao.
            validacoes.append(Validacao(
                gate="contraste", resultado="SKIPPED",
                detalhe={"motivo": "este motor nao mede contraste"}, bloqueante=False))

        # ⚠️ Gates que so o MOTOR sabe julgar — hermetismo do render, quadros
        # contados contra quadros pedidos, fps como fracao, safe zone. Eles nao
        # podem morar aqui: o operario nao sabe se houve sandbox nem quantos
        # quadros o pedido tinha. E nao podem morar so no motor: um gate que o
        # motor guarda para si nao entra no recibo e nao reprova nada.
        #
        # O gancho segue o mesmo padrao de `medir_contraste`, e le o relatorio
        # que o motor deixou no diretorio EXCLUSIVO do trabalho — nao um atributo
        # de instancia, que dois trabalhos simultaneos sobrescreveriam.
        proprios = getattr(motor, "gates", None)
        if callable(proprios):
            try:
                validacoes.extend(proprios(encomenda, dir_trabalho))
            except Exception as exc:  # noqa: BLE001
                # Gate que estoura nao aprova nem reprova a peca: vira FAIL do
                # PROPRIO gate, com o motivo, para nao virar silencio.
                validacoes.append(Validacao(
                    gate="gates_do_motor", resultado="FAIL",
                    detalhe={"motivo": _mensagem_para_o_operador(exc)},
                    bloqueante=True))
        return validacoes

    # ── procedencia, storage e destino ───────────────────────────────────

    def _publicar(
        self, trabalho: Trabalho, artefatos: tuple[Artefato, ...],
    ) -> tuple[RegistroDeStorage, ...]:
        """Sobe cada artefato e RELE do armazenamento antes de dizer qualquer coisa.

        ⚠️ A maquina de verificacao existia e nao tinha consumidor de producao: o
        worker gravava no disco local e ninguem publicava. Um worker em outra
        maquina produzia pecas que a web classificava como perdidas, e a peca
        "pronta" era pronta so no disco de quem a fez.

        Sem loja, o registro sai `NAO_PUBLICADO` — com nome. Nao ha caminho aqui
        que devolva `VERIFIED_OK` sem releitura, e e por isso que a publicacao
        inteira mora atras de `publicar_artefato`, que confere bytes E hash.
        """
        from app.criativo.armazenamento import (  # noqa: PLC0415
            ArmazenamentoIndisponivel,
            ArquivoRecusado,
            BucketAusente,
        )
        from .armazenamento_verificado import (  # noqa: PLC0415
            chave_canonica,
            hash_puro,
            publicar_artefato,
        )

        if self.loja is None:
            return tuple(
                RegistroDeStorage(
                    slot=a.slot,
                    chave=Declarado(ausencia=Ausencia.NAO_APLICAVEL),
                    estado="NAO_PUBLICADO",
                    sha256_relido=Declarado(ausencia=Ausencia.NAO_APLICAVEL),
                    bytes_relidos=Declarado(ausencia=Ausencia.NAO_APLICAVEL),
                )
                for a in artefatos
            )

        registros: list[RegistroDeStorage] = []
        for a in artefatos:
            extensao = Path(a.caminho).suffix.lstrip(".") or "bin"
            try:
                chave = chave_canonica(
                    trabalho.tenant_id, trabalho.id, a.slot, a.sha256, extensao
                )
            except ArquivoRecusado as exc:
                registros.append(RegistroDeStorage(
                    slot=a.slot,
                    chave=Declarado(ausencia=Ausencia.FALHOU),
                    estado="RECUSADO",
                    sha256_relido=Declarado(ausencia=Ausencia.FALHOU),
                    bytes_relidos=Declarado(ausencia=Ausencia.FALHOU),
                    lido_em=None,
                ))
                log.warning("chave recusada para o slot %s: %s", a.slot, exc)
                continue
            # ⚠️ ACHADO ADVERSARIAL, e era bloqueante. A versão anterior lia o
            # arquivo AQUI, depois da validação, e mandava esses bytes para o
            # armazenamento sem reconferi-los contra `a.sha256`. O gate tinha
            # conferido o disco num instante; o upload lia noutro. Reproduzido
            # pelo revisor: trocando o arquivo entre os dois momentos, o storage
            # saía `VERIFIED_OK` com `sha256_relido` diferente do `sha256` do
            # artefato — e a chave, que é content-addressed, continuava montada
            # com o hash ANTIGO. Um endereço passava a servir conteúdo que ele não
            # descreve.
            #
            # A releitura de `publicar_artefato` prova que o armazenamento devolve
            # o que recebeu. Ela não prova, e não pode provar, que o que recebeu é
            # o que o gate aprovou. Essa é a conferência que faltava.
            dados = Path(a.caminho).read_bytes()
            sha_do_upload = hashlib.sha256(dados).hexdigest()
            if sha_do_upload != a.sha256:
                registros.append(RegistroDeStorage(
                    slot=a.slot,
                    chave=Declarado(valor=chave),
                    estado="MISMATCH_LOCAL",
                    sha256_relido=Declarado(ausencia=Ausencia.MISMATCH),
                    bytes_relidos=Declarado(ausencia=Ausencia.MISMATCH),
                    lido_em=None,
                ))
                log.error(
                    "o arquivo do slot %s mudou entre a validacao e o upload; "
                    "nada foi enviado", a.slot,
                )
                continue
            try:
                publicacao = publicar_artefato(
                    self.loja,
                    chave=chave,
                    dados=dados,
                    mime=a.mime,
                )
            except BucketAusente:
                registros.append(self._storage_falho(a.slot, chave, "BUCKET_AUSENTE"))
                continue
            except (ArmazenamentoIndisponivel, ArquivoRecusado, OSError):
                # ⚠️ Nao colapsar em `VERIFIED_MISMATCH`: mismatch e terminal, e
                # carimba-lo por um timeout condenaria artefato possivelmente
                # integro. `INDISPONIVEL` e reconferivel; mismatch nao e.
                registros.append(self._storage_falho(a.slot, chave, "INDISPONIVEL"))
                continue
            registros.append(RegistroDeStorage(
                slot=a.slot,
                chave=Declarado(valor=publicacao.chave),
                estado=str(publicacao.estado.value),
                # ⚠️ SEM o prefixo `sha256:`. A maquina de armazenamento devolve
                # `sha256:<hex>` e `Artefato.sha256` guarda `<hex>` puro; deixar
                # as duas formas conviverem no MESMO recibo faria a pergunta que
                # mais importa — "o que voltou e o que subiu?" — depender de
                # lembrar qual campo carrega prefixo. O CHECK `hash_forma` da
                # v11_03 (`^[0-9a-f]{64}$`) tambem quer a forma pura.
                #
                # ⚠️ O normalizador e o de `armazenamento_verificado`, e nao uma
                # copia local. Havia duas copias, e uma delas nao existia:
                # `Publicacao.para_registro` escrevia na MESMA coluna sem
                # normalizar, e a v11_03 recusava a linha. Uma normalizacao que
                # vale para um dos caminhos nao e normalizacao.
                sha256_relido=Declarado.de(
                    hash_puro(publicacao.sha256_remoto), Ausencia.NAO_MEDIDO
                ),
                bytes_relidos=Declarado.de(
                    publicacao.bytes_remoto, Ausencia.NAO_MEDIDO
                ),
                lido_em=(
                    publicacao.conferido_em.isoformat()
                    if publicacao.conferido_em is not None else None
                ),
            ))
        return tuple(registros)

    @staticmethod
    def _storage_falho(slot: str, chave: str, estado: str) -> RegistroDeStorage:
        return RegistroDeStorage(
            slot=slot,
            chave=Declarado(valor=chave),
            estado=estado,
            # Nenhum byte foi lido. `NAO_MEDIDO` e o nome certo: `0` diria que a
            # releitura aconteceu e trouxe um objeto vazio.
            sha256_relido=Declarado(ausencia=Ausencia.NAO_MEDIDO),
            bytes_relidos=Declarado(ausencia=Ausencia.NAO_MEDIDO),
            lido_em=None,
        )

    @staticmethod
    def _destinos(artefatos: tuple[Artefato, ...]) -> tuple[DestinoDoRecibo, ...]:
        """Contra que destinos declarados esta producao serve — MEDIDO.

        O casamento e por (largura, altura) MEDIDA e por midia, contra o catalogo
        de envelopes. Nao ha caminho aqui em que um destino saia `serve` por
        declaracao do motor: as dimensoes que chegam neste ponto ja passaram pelo
        gate que as leu do arquivo.
        """
        try:
            from volc_ads.criativo.contrato import TipoDeAsset  # noqa: PLC0415
            from volc_ads.criativo.destinos import (  # noqa: PLC0415
                DESTINOS,
                ENVELOPES,
                envelopes_de_destino,
            )
        except Exception:  # noqa: BLE001 — catalogo ausente
            return ()

        def e_video(envelope: Any) -> bool:
            return envelope.tipo is TipoDeAsset.VIDEO

        casados: dict[str, set[str]] = {d: set() for d in DESTINOS}
        for a in artefatos:
            if a.largura is None or a.altura is None:
                continue
            artefato_e_video = a.mime in _MIMES_DE_VIDEO
            for env in ENVELOPES:
                if (env.largura, env.altura) != (a.largura, a.altura):
                    continue
                # ⚠️ Geometria igual NAO basta. `organico-reels-9x16` (imagem) e
                # `organico-reels-video-9x16` (video) tem os MESMOS 1080x1920, e
                # casar so por medida faria um mp4 cumprir o envelope de imagem
                # — e o destino receberia um arquivo que ele nao aceita naquela
                # posicao.
                if e_video(env) != artefato_e_video:
                    continue
                casados[env.destino].add(env.slug)

        saida: list[DestinoDoRecibo] = []
        for destino in DESTINOS:
            esperados = tuple(e.slug for e in envelopes_de_destino(destino))
            entregues = casados[destino]
            faltando = tuple(s for s in esperados if s not in entregues)
            if entregues and not faltando:
                saida.append(DestinoDoRecibo(slug=destino, veredito="serve"))
            elif entregues:
                # ⚠️ NAO e `nao_serve`. Uma peca que casa um envelope do destino
                # SERVE aquele envelope; o que ela nao faz e completar o lote.
                # Colapsar as duas perguntas numa so faria uma peca legitima
                # aparecer como imprestavel, e a pergunta de completude ja tem
                # dono proprio: `PacoteDeDestino.completo`.
                saida.append(DestinoDoRecibo(
                    slug=destino, veredito="serve_parcialmente",
                    motivos=tuple(f"envelope nao produzido: {s}" for s in faltando)))
            else:
                saida.append(DestinoDoRecibo(
                    slug=destino, veredito="nao_serve",
                    motivos=("nenhuma peca desta producao casa um envelope deste destino",)))
        return tuple(saida)

    @staticmethod
    def _procedencia(trabalho: Trabalho, motor: MotorDeProducao) -> Procedencia:
        def gancho(nome: str, quando_ausente: Ausencia) -> Declarado:
            fn = getattr(motor, nome, None)
            if not callable(fn):
                return Declarado(ausencia=quando_ausente)
            try:
                valor = fn()
            except Exception:  # noqa: BLE001
                return Declarado(ausencia=Ausencia.FALHOU)
            return valor if isinstance(valor, Declarado) else Declarado.de(valor, quando_ausente)

        natureza = getattr(motor, "natureza", None)
        e = trabalho.encomenda
        return Procedencia(
            receita_id=e.receita_id,
            tenant_id=e.tenant_id,
            modo_slug=e.modo_slug,
            finalidade_slug=e.finalidade_slug,
            # ⚠️ Um motor que nao declara natureza vale `nao_declarada`, NUNCA
            # `producao`. A regra ja existia no envelope e vale igual aqui.
            natureza=getattr(natureza, "value", None) or "nao_declarada",
            provider=gancho("provider", Ausencia.NAO_DECLARADO),
            modelo=gancho("modelo", Ausencia.NAO_DECLARADO),
            licenca=gancho("licenca", Ausencia.NAO_DECLARADO),
            disclosure=gancho("disclosure", Ausencia.NAO_DECLARADO),
            brand_pack=Declarado.de(
                e.parametros.get("brand_pack_id"), Ausencia.NAO_DECLARADO
            ),
        )

    @staticmethod
    def _custo(motor: MotorDeProducao, encomenda: Encomenda) -> Custo:
        fn = getattr(motor, "custo", None)
        if not callable(fn):
            # ⚠️ `NAO_APURADO` e nao `SEM_CUSTO_DE_PROVIDER`: um motor que nao
            # tem porta de custo pode ser pago. Assumir gratuito por ausencia de
            # implementacao e exatamente como todo trabalho nasceria com custo
            # nulo permanente no dia em que entrasse um provider pago.
            return Custo(
                estimado_usd=Declarado(ausencia=Ausencia.NAO_APURADO),
                real_usd=Declarado(ausencia=Ausencia.NAO_APURADO),
            )
        try:
            valor = fn(encomenda)
        except Exception:  # noqa: BLE001
            return Custo(
                estimado_usd=Declarado(ausencia=Ausencia.FALHOU),
                real_usd=Declarado(ausencia=Ausencia.FALHOU),
            )
        if isinstance(valor, Custo):
            return valor
        return Custo(
            estimado_usd=Declarado(ausencia=Ausencia.NAO_DECLARADO),
            real_usd=Declarado(ausencia=Ausencia.NAO_DECLARADO),
        )

    @staticmethod
    def _hashes_de_entrada(
        motor: MotorDeProducao, encomenda: Encomenda, dir_trabalho: str,
    ) -> dict[str, str]:
        fn = getattr(motor, "hashes_de_entrada", None)
        if not callable(fn):
            return {}
        try:
            valor = fn(encomenda, dir_trabalho)
        except Exception:  # noqa: BLE001
            return {}
        return {str(k): str(v) for k, v in dict(valor or {}).items()}

    @staticmethod
    def _insumo(encomenda: Encomenda) -> InsumoSanitizado:
        p = encomenda.parametros
        return sanitizar_insumo(p.get("insumo") or p.get("prompt") or p.get("briefing"))

    @staticmethod
    def _video_ausente_porque(artefatos: tuple[Artefato, ...]) -> Ausencia | None:
        de_video = [a for a in artefatos if a.mime in _MIMES_DE_VIDEO]
        if not de_video:
            return Ausencia.NAO_APLICAVEL
        if all(a.video is not None for a in de_video):
            return None
        return Ausencia.NAO_MEDIDO

    def _audio(
        self, motor: MotorDeProducao, encomenda: Encomenda, dir_trabalho: str,
    ) -> tuple[MedidaDeAudio | None, Ausencia | None]:
        """Devolve a medida E a razao nomeada quando ela nao existe.

        ⚠️ `MedidaDeAudio` era estrutura MORTA: nenhum motor implementava
        `medir_audio`, e a v11_03 reservou tres colunas numericas que nasceriam
        permanentemente nulas — o "null permanente que parece lacuna de
        preenchimento" que o proprio `PLANO-v11_03.md` diz querer evitar. O
        gancho passa a receber o diretorio do trabalho porque medir audio e medir
        o ARQUIVO; medir o pedido nao mede nada.
        """
        medir = getattr(motor, "medir_audio", None)
        if not callable(medir):
            return (None, Ausencia.NAO_SUPORTADO)
        try:
            medida = medir(encomenda, dir_trabalho)
        except TypeError:
            # Motor com a assinatura antiga de um argumento. Nao e ausencia de
            # audio: e um motor que este operario nao sabe mais chamar.
            return (None, Ausencia.NAO_SUPORTADO)
        except Exception:  # noqa: BLE001
            return (None, Ausencia.FALHOU)
        if medida is None:
            return (None, Ausencia.NAO_MEDIDO)
        return (medida, None)


class Reaper:
    """Devolve para a fila os trabalhos cujo lease venceu, sozinho.

    ⚠️ ACHADO ADVERSARIAL. `devolver_vencidos` so rodava dentro de `reivindicar`,
    e `reivindicar` so rodava quando OUTRO pedido chegava. Um trabalho abandonado
    por um operario morto ficava preso ate alguem, por acaso, mandar outro pedido.
    A promessa "o trabalho volta para a fila" era verdadeira no deposito e falsa
    na operacao.

    Iniciavel e encerravel com seguranca: `parar()` acorda a espera em vez de
    esperar o intervalo inteiro, e `join` tem prazo.
    """

    def __init__(self, deposito: DepositoDeTrabalhos, *, intervalo_s: float = 10.0) -> None:
        self._d = deposito
        self._intervalo = intervalo_s
        self._parar = threading.Event()
        self._t: threading.Thread | None = None
        self.devolvidos = 0
        self.rodadas = 0

    def iniciar(self) -> Reaper:
        if self._t is not None and self._t.is_alive():
            return self
        self._parar.clear()

        def laco() -> None:
            while not self._parar.is_set():
                try:
                    self.devolvidos += self._d.devolver_vencidos()
                    self.rodadas += 1
                except Exception:  # noqa: BLE001 — o reaper nao pode morrer calado
                    log.exception("reaper: falha ao devolver vencidos")
                self._parar.wait(self._intervalo)

        self._t = threading.Thread(target=laco, daemon=True, name="bancada-reaper")
        self._t.start()
        return self

    def parar(self, *, prazo_s: float = 3.0) -> None:
        """⚠️ NAO zera `self._t` quando o join expira. A versao anterior zerava
        sempre, entao uma thread que NAO morreu sumia da vista e `vivo` respondia
        `False` sobre uma thread vazando. Encerrar e uma afirmacao que precisa ser
        verdadeira, nao um desejo."""
        self._parar.set()
        if self._t:
            self._t.join(timeout=prazo_s)
            if not self._t.is_alive():
                self._t = None

    @property
    def vivo(self) -> bool:
        return self._t is not None and self._t.is_alive()

    def __enter__(self) -> Reaper:
        return self.iniciar()

    def __exit__(self, *_: Any) -> None:
        self.parar()


class DespachanteLocal:
    """Executa no mesmo processo, de forma sincrona.

    ⚠️ Isto NAO e producao, e a diferenca esta declarada: nao ha fila externa, nao
    ha maquina separada e nao ha resiliencia a este processo morrer no meio. O que
    ele prova e que o CONTRATO nao depende da infraestrutura — trocar por Cloud Run
    Job ou por worker permanente nao toca `Encomenda`, `Recibo` nem `MotorDeProducao`.
    """

    def __init__(self, operario: Operario) -> None:
        self.operario = operario

    def despachar_job_do_estudio(self, job_id: str, executor: Any) -> None:
        """Executa um job do Estúdio de forma SÍNCRONA e durável.

        ⚠️ Ponte de transição, e declarada como tal. O Estúdio tem o próprio
        `Executor`, com o próprio motor e a própria persistência em
        `criativo_job`; a bancada tem o dela. Unificar os dois é a v11_03
        aplicada mais o adaptador que ainda não existe.

        O que esta ponte já entrega, e é o que importa: **o request não devolve
        antes de o trabalho ter estado terminal**. Não há mais tarefa em memória
        do request governando produção, e um processo que morra no meio deixa o
        job em `running` no banco — visível, retomável — em vez de sumir com a
        task congelada.
        """
        import anyio  # noqa: PLC0415

        anyio.from_thread.run(executor._executar_protegido, job_id)  # noqa: SLF001

    def despachar(self, trabalho_id: str) -> None:
        """⚠️ ACHADO ADVERSARIAL. A primeira versao buscava o id so para levantar
        `KeyError` e depois chamava `reivindicar()`, que devolve o MAIS ANTIGO da
        fila. Com qualquer trabalho parado na frente, o operador pedia a peca A,
        recebia 201 dizendo `queued` sem recibo, e a maquina produzia a peca B de
        outra receita — enquanto a peca A ficava na fila para sempre.
        """
        reivindicado = self.operario.deposito.reivindicar_este(
            trabalho_id, self.operario.nome, lease_s=self.operario.lease_s
        )
        if reivindicado is None:
            # Ja saiu da fila: outro operario pegou, ou o trabalho e um replay
            # que ja terminou. Nao ha nada a fazer, e nao ha erro.
            return
        self.operario.executar(reivindicado)
