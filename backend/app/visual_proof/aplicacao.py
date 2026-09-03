"""Casos de uso da prova visual e as PORTAS que eles exigem do mundo.

Nada aqui sabe o que é FastAPI, httpx ou `http.server`. O que este arquivo sabe
é que existe um broker capaz de executar operações governadas, um repositório
capaz de guardar jobs com lease, e um relógio.

## A distinção que este arquivo existe para preservar

**Ausência de QA não é QA negativo.** `qa_visual.estado` distingue
`nao_persistido` (não existe onde guardar), `nao_executado` (existe e ninguém
rodou), `em_execucao`, `indeterminado`, `corrigir` e `aprovado`. Colapsar os
seis num booleano faria a tela mostrar a mesma cara para "nunca conferimos" e
para "conferimos e está errado" — que mandam a pessoa fazer coisas opostas.

**Pronto para receber peça ≠ pronto para publicar.** O primeiro é uma pergunta
sobre o ativo (existe, não está aposentado, tem destino). O segundo é uma
pergunta sobre a cadeia inteira (referência verificada, perfil relacionado,
broker configurado). Um único "pronto" faria a operação mandar peça para uma
página que ninguém consegue abrir.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol, Sequence

from app.visual_proof import dominio as dom


class BrokerIndisponivel(RuntimeError):
    """Não deu para falar com o broker. NUNCA vira 'a página está errada'."""


class AcessoNegado(PermissionError):
    """Quem pediu não é o dono do job. A mensagem não revela se ele existe."""


class JobNaoEncontrado(LookupError):
    pass


class ConflitoDeIdempotencia(ValueError):
    """Mesma chave, entrada diferente. Ver `RegistroDeIdempotencia` no broker."""


class JobEmExecucao(RuntimeError):
    """Outro consumidor tem o lease deste job."""


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────────
# Portas
# ─────────────────────────────────────────────────────────────────────────────


class BrokerDeAdsPower(Protocol):
    """O broker, como o plano de controle o enxerga: um ato e um recibo."""

    @property
    def configurado(self) -> bool: ...

    def executar(self, pedido: dom.AdsPowerBrokerRequest, *,
                 consumidor: str) -> dom.AdsPowerBrokerReceipt: ...


class RepositorioDeJobs(Protocol):
    def criar(self, job: dom.VisualProofJob, impressao: str) -> dom.VisualProofJob: ...

    def obter(self, job_id: str) -> Optional[dom.VisualProofJob]: ...

    def salvar(self, job: dom.VisualProofJob) -> None: ...

    def reivindicar(self, job_id: str, consumidor: str, lease_s: int) -> None: ...

    def liberar(self, job_id: str) -> None: ...

    def ultimo_do_ativo(self, ativo_id: str, owner_sub: str) -> Optional[dom.VisualProofJob]: ...


class LeitorDeProvaVisual(Protocol):
    """A porta que o Cofre usa, e a ÚNICA coisa que ele conhece daqui.

    Ela responde "qual o último job deste ativo" — ou declara honestamente que
    não há onde guardar job nenhum. O Cofre não conhece broker, executor nem
    contrato de operação.
    """

    def estado_da_persistencia(self) -> tuple[str, str]: ...

    def ultimo_job(self, ativo_id: str, owner_sub: str) -> Optional[dict[str, Any]]: ...


@dataclass(frozen=True)
class PedidoDeProvaVisual:
    """O que quem pede o QA precisa informar."""

    ativo_id: str
    owner_sub: str
    url_esperada: str
    dominio_esperado: Optional[str]
    perfil: dom.BrowserProfileReference
    chave_idempotencia: str
    viewport: dom.Viewport = dom.Viewport(largura=1366, altura=768)
    timezone: str = "America/Sao_Paulo"
    classe_de_agente: str = "desktop-chromium"
    timeout_s: int = 45
    conteudo_sha256_esperado: Optional[str] = None

    def impressao(self) -> str:
        return dom.impressao_do_pedido({
            "ativo_id": self.ativo_id,
            "owner_sub": self.owner_sub,
            "url_esperada": self.url_esperada,
            "dominio_esperado": self.dominio_esperado,
            "perfil": self.perfil.para_dicionario(),
            "viewport": self.viewport.para_dicionario(),
            "timezone": self.timezone,
            "classe_de_agente": self.classe_de_agente,
            "timeout_s": self.timeout_s,
            "conteudo_sha256_esperado": self.conteudo_sha256_esperado,
        })


# ─────────────────────────────────────────────────────────────────────────────
# Casos de uso
# ─────────────────────────────────────────────────────────────────────────────


class ControleDeProvaVisual:
    """Os cinco atos: criar, executar, ler, aprovar e cancelar."""

    def __init__(
        self, *, repositorio: RepositorioDeJobs, broker: BrokerDeAdsPower,
        agora: Callable[[], str] = agora_iso,
        resolvedor_de_dns: Optional[Callable[[str], Sequence[str]]] = None,
        lease_s: int = 120,
    ) -> None:
        self._repo = repositorio
        self._broker = broker
        self._agora = agora
        self._dns = resolvedor_de_dns
        self._lease_s = lease_s

    # ── criar ────────────────────────────────────────────────────────────────

    def criar(self, pedido: PedidoDeProvaVisual) -> dom.VisualProofJob:
        """Valida ANTES de existir job. Um job inválido persistido é lixo com id."""
        if pedido.owner_sub != pedido.perfil.owner_sub:
            raise dom.PayloadRecusado(
                "o dono do QA não é o dono do perfil: o Cofre não empresta perfil.")
        dom.exigir_chave_de_idempotencia_visual(pedido.chave_idempotencia)
        url = dom.exigir_url_de_superficie(
            pedido.url_esperada, dominio_esperado=pedido.dominio_esperado,
            resolver=self._dns)

        job = dom.VisualProofJob.novo(
            job_id=f"vpj_{uuid.uuid4().hex[:16]}",
            owner_sub=pedido.owner_sub, ativo_id=pedido.ativo_id, perfil=pedido.perfil,
            url_esperada=url, dominio_esperado=pedido.dominio_esperado,
            viewport=pedido.viewport, timezone=pedido.timezone,
            classe_de_agente=pedido.classe_de_agente,
            chave_idempotencia=pedido.chave_idempotencia, criado_em=self._agora(),
            timeout_s=pedido.timeout_s,
            conteudo_sha256_esperado=pedido.conteudo_sha256_esperado)
        guardado = self._repo.criar(job, pedido.impressao())
        if guardado.estado == "requested":
            guardado.autorizar(em=self._agora())
            self._repo.salvar(guardado)
        return guardado

    # ── executar ─────────────────────────────────────────────────────────────

    def executar(self, job_id: str, *, solicitante: str,
                 consumidor: str = "worker") -> dom.VisualProofJob:
        job = self._exigir_acesso(job_id, solicitante)
        if job.estado in dom.ESTADOS_TERMINAIS:
            # Terminal é terminal. Reexecutar exige job novo, com chave nova —
            # e isso é deliberado: um retry que reabre um job aprovado apagaria
            # o recibo humano que já estava lá.
            return job

        self._repo.reivindicar(job_id, consumidor, self._lease_s)
        try:
            job.iniciar(recibo_id=f"pendente_{uuid.uuid4().hex[:8]}", em=self._agora())
            self._repo.salvar(job)

            if not self._broker.configurado:
                return self._encerrar_tecnico(job, "broker_indisponivel")

            pedido = dom.AdsPowerBrokerRequest(
                pedido_id=f"ped_{uuid.uuid4().hex[:12]}",
                # A chave do broker DERIVA da chave do job e da tentativa: um
                # retry legítimo precisa poder executar, e um retry acidental do
                # mesmo passo não pode duplicar. Sortear aqui publicaria duas
                # vezes; fixar na chave do job travaria o retry legítimo.
                chave_idempotencia=f"{job.chave_idempotencia}#t{job.tentativas}",
                operacao="capturar_superficie", perfil=job.perfil,
                owner_sub=job.owner_sub, ativo_id=job.ativo_id,
                timeout_s=job.timeout_s, url_alvo=job.url_esperada,
                dominio_esperado=job.dominio_esperado, viewport=job.viewport,
                timezone=job.timezone)

            try:
                recibo = self._broker.executar(pedido, consumidor=consumidor)
            except BrokerIndisponivel:
                return self._encerrar_tecnico(job, "broker_indisponivel")

            job.recibo_id = recibo.recibo_id
            if recibo.estado not in ("executado", "replay"):
                return self._encerrar_tecnico(job, recibo.motivo_codigo, recibo=recibo)

            leitura = dom.LeituraDaSuperficie(
                url_final=recibo.url_final or "",
                url_esperada=job.url_esperada,
                dominio_esperado=job.dominio_esperado,
                status_http=recibo.status_http,
                console_erros=int(recibo.console_resumo.get("erros", 0) or 0),
                rede_falhas=int(recibo.rede_resumo.get("falhas", 0) or 0),
                redirecionamentos=len(recibo.redirecionamentos),
                artefato_bytes=recibo.artefato.bytes_ if recibo.artefato else 0,
                conteudo_sha256=recibo.artefato.sha256 if recibo.artefato else None,
                conteudo_sha256_esperado=job.conteudo_sha256_esperado)
            veredito = dom.avaliar_captura(leitura)
            job.registrar_captura(
                url_final=recibo.url_final or "", artefato=recibo.artefato,
                console_resumo=recibo.console_resumo, rede_resumo=recibo.rede_resumo,
                redirecionamentos=recibo.redirecionamentos,
                checagens=veredito.checagens, veredito=veredito, em=self._agora())
            self._repo.salvar(job)
            return job
        finally:
            self._repo.liberar(job_id)

    def _encerrar_tecnico(self, job: dom.VisualProofJob, motivo: str,
                          recibo: Optional[dom.AdsPowerBrokerReceipt] = None
                          ) -> dom.VisualProofJob:
        """Falha do executor → `indeterminate`. Nunca `needs_correction`.

        É o guarda do ADR de distribuição orgânica escrito em código: se o
        AdsPower cair, a página continua sem veredito — e continuar sem veredito
        é diferente de estar errada.
        """
        job.marcar_indeterminado(dom.veredito_de_falha_tecnica(motivo), em=self._agora())
        if recibo is not None:
            job.justificativas.append(dom.sanitizar_texto(recibo.motivo, 200))
        self._repo.salvar(job)
        return job

    # ── ler, aprovar, cancelar ───────────────────────────────────────────────

    def ler(self, job_id: str, *, solicitante: str) -> dom.VisualProofJob:
        return self._exigir_acesso(job_id, solicitante)

    def aprovar(self, job_id: str, *, solicitante: str, revisor: str,
                nota: str) -> dom.VisualProofJob:
        job = self._exigir_acesso(job_id, solicitante)
        job.aprovar(revisor=revisor, nota=nota, em=self._agora())
        self._repo.salvar(job)
        return job

    def pedir_correcao(self, job_id: str, *, solicitante: str, revisor: str,
                       nota: str) -> dom.VisualProofJob:
        job = self._exigir_acesso(job_id, solicitante)
        job.pedir_correcao_humana(revisor=revisor, nota=nota, em=self._agora())
        self._repo.salvar(job)
        return job

    def cancelar(self, job_id: str, *, solicitante: str, motivo: str) -> dom.VisualProofJob:
        job = self._exigir_acesso(job_id, solicitante)
        job.cancelar(motivo, em=self._agora())
        self._repo.salvar(job)
        return job

    def ultimo_do_ativo(self, ativo_id: str, *, solicitante: str
                        ) -> Optional[dom.VisualProofJob]:
        return self._repo.ultimo_do_ativo(ativo_id, solicitante)

    def _exigir_acesso(self, job_id: str, solicitante: str) -> dom.VisualProofJob:
        """Job de outro dono responde IGUAL a job inexistente.

        Distinguir "não existe" de "existe e não é seu" entrega um oráculo de
        enumeração: com ele, alguém descobre quais ativos têm QA rodando sem
        nunca ver um recibo.
        """
        job = self._repo.obter(job_id)
        if job is None or job.owner_sub != solicitante:
            raise AcessoNegado("esse job de prova visual não existe para você.")
        return job


# ─────────────────────────────────────────────────────────────────────────────
# Prontidão — a projeção honesta que a tela consome
# ─────────────────────────────────────────────────────────────────────────────

#: Os seis estados de QA. `nao_persistido` é o de hoje: não existe tabela para
#: `VisualProofJob`, e dizer "não executado" esconderia a diferença entre "ainda
#: não rodamos" e "não há onde guardar se rodássemos".
ESTADOS_DE_QA: tuple[str, ...] = (
    "nao_persistido", "nao_executado", "em_execucao", "indeterminado",
    "corrigir", "aprovado",
)

_ESTADO_DE_QA_POR_JOB: dict[str, str] = {
    "requested": "nao_executado",
    "authorized": "nao_executado",
    "running": "em_execucao",
    "captured": "em_execucao",     # capturado é "esperando gente", não "aprovado"
    "approved": "aprovado",
    "needs_correction": "corrigir",
    "indeterminate": "indeterminado",
    "failed": "indeterminado",
    "cancelled": "nao_executado",
    "expired": "nao_executado",
}


def montar_prontidao(
    *, handoff: dict[str, Any], broker_configurado: bool,
    persistencia: tuple[str, str], job: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compõe Cofre + broker + último job numa resposta que não mente.

    Função PURA: nenhum I/O, nenhum relógio, nenhuma rede. É por isso que ela
    pode morar aqui e ser chamada pela rota do Cofre sem arrastar o executor
    junto — o Cofre continua sem saber o que é um broker.
    """
    destino = dict(handoff.get("destino") or {})
    credenciais = list(handoff.get("referencia_de_acesso") or [])
    perfis = list(handoff.get("perfis_de_navegador") or [])
    bloqueios_do_cofre = list(handoff.get("bloqueios") or [])

    pagina_presente = bool(destino.get("ativo_id"))
    credencial = credenciais[0] if credenciais else None
    credencial_verificada = any(
        (c.get("verificacao_estado") == "verified") for c in credenciais)
    perfil_presente = bool(perfis)
    aposentado = bool(destino.get("estado") == "retired")

    bloqueios: list[dict[str, str]] = []

    def bloquear(codigo: str, mensagem: str, onde: str) -> None:
        bloqueios.append({"codigo": codigo, "mensagem": mensagem, "onde": onde})

    if not pagina_presente:
        bloquear("pagina_ausente",
                 "nenhuma página real está cadastrada no Cofre para este ativo.", "cofre")
    if aposentado:
        bloquear("ativo_aposentado", "o ativo está aposentado.", "cofre")
    if not credenciais:
        bloquear("referencia_ausente",
                 "não há referência de acesso registrada: o broker não teria o que resolver.",
                 "cofre")
    elif not credencial_verificada:
        bloquear("referencia_nao_verificada",
                 "a referência de acesso nunca foi verificada com sucesso.", "cofre")
    if not perfil_presente:
        bloquear("perfil_ausente",
                 "nenhum perfil de navegador relacionado por authenticates_through: "
                 "o QA visual não saberia qual perfil abrir.", "cofre")
    if not broker_configurado:
        bloquear("broker_indisponivel",
                 "o broker do AdsPower não está configurado neste ambiente.", "broker")

    estado_persistencia, motivo_persistencia = persistencia
    if estado_persistencia != "disponivel":
        estado_qa, motivo_qa = "nao_persistido", motivo_persistencia
    elif job is None:
        estado_qa, motivo_qa = "nao_executado", "nenhuma prova visual foi executada ainda."
    else:
        estado_qa = _ESTADO_DE_QA_POR_JOB.get(str(job.get("estado")), "nao_executado")
        motivo_qa = "; ".join(job.get("justificativas") or []) or "sem observações."

    pronto_para_receber_peca = pagina_presente and not aposentado
    pronto_para_publicar = (
        pronto_para_receber_peca and credencial_verificada and perfil_presente)
    pronto_para_qa = pronto_para_publicar and broker_configurado

    return {
        "ativo_id": destino.get("ativo_id"),
        "destino": destino,
        "pagina": {"presente": pagina_presente,
                   "motivo": "" if pagina_presente else
                             "o Cofre não tem página real cadastrada para este ativo."},
        "referencia_de_credencial": {
            "presente": bool(credenciais),
            "verificada": credencial_verificada,
            "provider": (credencial or {}).get("provider"),
            "nome_logico": (credencial or {}).get("nome_logico"),
            "verificacao_estado": (credencial or {}).get("verificacao_estado"),
            "verificado_em": (credencial or {}).get("verificado_em"),
        },
        "perfil_de_navegador": {
            "presente": perfil_presente,
            "rotulo": (perfis[0].get("destino_rotulo") if perfis else None),
            "ativo_id": (perfis[0].get("destino_id") if perfis else None),
        },
        "broker": {
            "estado": "configurado" if broker_configurado else "nao_configurado",
            "motivo": "" if broker_configurado else
                      "o endereço e o token do broker não estão definidos neste ambiente.",
        },
        "qa_visual": {
            "estado": estado_qa,
            "motivo": motivo_qa,
            "job": job,
            "veredito": (job or {}).get("veredito"),
            "artefato": (job or {}).get("artefato"),
        },
        "pronto_para_receber_peca": pronto_para_receber_peca,
        "pronto_para_publicar": pronto_para_publicar,
        "pronto_para_qa": pronto_para_qa,
        "bloqueios": bloqueios,
        "bloqueios_do_cofre": bloqueios_do_cofre,
        "proxima_acao": _proxima_acao(bloqueios, estado_qa),
    }


def _proxima_acao(bloqueios: list[dict[str, str]], estado_qa: str) -> str:
    """Uma frase, e ela aponta para o PRIMEIRO bloqueio — não para todos.

    Uma lista de dez pendências não diz o que fazer agora. O primeiro bloqueio
    da ordem acima é sempre o que destrava os seguintes.
    """
    if bloqueios:
        return {
            "pagina_ausente":
                "Cadastre a página real no Cofre (P03-T02 / P12-T02) — sem ela não há o "
                "que conferir.",
            "ativo_aposentado":
                "Reative o ativo no Cofre antes de pedir QA visual.",
            "referencia_ausente":
                "Registre a referência de acesso da página no Cofre (provider e nome "
                "lógico; o endereço fica no 1Password).",
            "referencia_nao_verificada":
                "Verifique a referência de acesso e registre o resultado no Cofre.",
            "perfil_ausente":
                "Inventarie o perfil AdsPower e relacione-o à página por "
                "authenticates_through (P03-T07).",
            "broker_indisponivel":
                "Suba o broker do AdsPower no host isolado e configure endereço e token "
                "(P03-T11).",
        }.get(bloqueios[0]["codigo"], bloqueios[0]["mensagem"])
    return {
        "nao_persistido":
            "O QA visual ainda não tem onde ser guardado: falta a migração do "
            "VisualProofJob. Nada foi executado.",
        "nao_executado": "Peça a prova visual desta superfície.",
        "em_execucao": "A prova visual está em andamento ou aguardando revisão humana.",
        "indeterminado":
            "A prova visual não conseguiu concluir. Isso NÃO reprova a página — "
            "investigue o executor e rode de novo.",
        "corrigir": "A prova visual encontrou divergência: corrija a superfície publicada.",
        "aprovado": "Aprovada por revisão humana. Nenhuma ação pendente.",
    }.get(estado_qa, "Sem próxima ação definida.")


__all__ = [
    "AcessoNegado", "BrokerDeAdsPower", "BrokerIndisponivel", "ConflitoDeIdempotencia",
    "ControleDeProvaVisual", "ESTADOS_DE_QA", "JobEmExecucao", "JobNaoEncontrado",
    "LeitorDeProvaVisual", "PedidoDeProvaVisual", "RepositorioDeJobs", "agora_iso",
    "montar_prontidao",
]
