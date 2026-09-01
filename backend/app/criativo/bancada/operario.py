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
    Encomenda,
    EstadoDoTrabalho,
    FalhaDoMotor,
    MedidaDeAudio,
    MotorDeProducao,
    Recibo,
    TransicaoProibida,
    Validacao,
)
from .deposito import DepositoDeTrabalhos, Trabalho

log = logging.getLogger(__name__)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_do_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


#: MIMEs cuja dimensao este operario SABE medir. Um artefato que declara um
#: destes e nao abre nao e "formato desconhecido": e arquivo quebrado.
_MIMES_MENSURAVEIS = frozenset({"image/png", "image/jpeg", "image/gif"})


def _medir_dimensao(caminho: Path) -> tuple[int, int] | None:
    """Largura e altura LIDAS DO ARQUIVO. `None` quando nao da para saber.

    ⚠️ `None` e ausencia de medicao, nunca `(0, 0)`. O medidor le o cabecalho do
    formato com a biblioteca padrao (PNG, GIF, JPEG) e ja recusa o caso classico
    do IHDR todo zero.
    """
    try:
        from volc_ads.criativo.adaptadores.medir_imagem import medir  # noqa: PLC0415

        m = medir(caminho.read_bytes())
    except Exception:  # noqa: BLE001 — medidor ausente ou arquivo ilegivel
        return None
    if m.largura is None or m.altura is None:
        return None
    return (m.largura, m.altura)


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
    ) -> None:
        self.deposito = deposito
        self.motores = motores
        self.raiz = Path(raiz_de_trabalho)
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.nome = nome or f"operario-{uuid.uuid4().hex[:8]}"
        self.lease_s = lease_s

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
                    trabalho.id, EstadoDoTrabalho.RUNNING, exigir_operario=self.nome
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
                    trabalho.id, EstadoDoTrabalho.VALIDATING, exigir_operario=self.nome
                )
                validacoes = self._validar(trabalho.encomenda, artefatos, motor)

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
                    )

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
                    audio=self._audio(motor, trabalho.encomenda),
                    iniciado_em=iniciado,
                    terminado_em=_agora(),
                    custo_estimado_usd=None,
                    custo_real_usd=None,
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
                    exigir_operario=self.nome,
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
                    exigir_operario=self.nome,
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
                exigir_operario=self.nome,
            )
        except TransicaoProibida:
            return self.deposito.por_id(trabalho.id) or trabalho

    # ── validacao ────────────────────────────────────────────────────────────

    def _validar(
        self, encomenda: Encomenda, artefatos: tuple[Artefato, ...],
        motor: MotorDeProducao,
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
            medida = _medir_dimensao(caminho)
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
        return validacoes

    def _audio(self, motor: MotorDeProducao, encomenda: Encomenda) -> MedidaDeAudio | None:
        medir = getattr(motor, "medir_audio", None)
        if not callable(medir):
            return None
        return medir(encomenda)


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
