"""Adaptadores da prova visual — e o alcance honesto de cada um.

## O que existe aqui, e o que isso significa para produção

| Adaptador | Estado real |
|---|---|
| `RepositorioEmMemoria` | **hermético.** Coordena dentro de UM processo. Não sobrevive a reinício e não é visto por um segundo worker. |
| `BrokerHttp` | **escrito, não exercido contra broker real.** Fala com o broker por loopback, com Bearer próprio. |
| `LeitorSemPersistencia` | **é o que a rota do Cofre usa hoje**, e ele declara `nao_persistido` de propósito. |

⚠️ **Não existe tabela de `VisualProofJob` no Supabase oficial.** Nenhuma
migration foi escrita nem aplicada nesta entrega, e essa ausência é um FATO que
a API precisa dizer — não um detalhe a esconder atrás de uma lista vazia. É por
isso que `LeitorSemPersistencia` existe com nome próprio em vez de um
repositório em memória plugado no FastAPI: um repositório em memória numa API
com mais de um worker responderia coisas diferentes a cada requisição, e a
pessoa concluiria que o job "sumiu".

## Por que a configuração vem de `os.environ` e não de `app.config.Settings`

`backend/app/config.py` está fora da propriedade desta missão. Ler o ambiente
direto é a alternativa que não invade arquivo de outro dono; a dívida está
nomeada no handoff, e a mudança certa é registrar as duas variáveis em
`Settings` quando alguém tocar aquele arquivo por outro motivo.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from app.visual_proof import aplicacao as app
from app.visual_proof import dominio as dom

log = logging.getLogger("volc.prova_visual.infra")

VAR_ENDERECO = "VOLC_BROKER_URL"
VAR_TOKEN = "VOLC_BROKER_TOKEN"


# ─────────────────────────────────────────────────────────────────────────────
# Repositório
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _Registro:
    job: dom.VisualProofJob
    impressao: str
    lease_ate: float = 0.0
    lease_de: str = ""
    ordem: int = 0


class RepositorioEmMemoria:
    """Jobs com idempotência e lease, dentro de um processo.

    ⚠️ Alcance honesto: um `dict` com `Lock` prova a SEMÂNTICA (mesma chave não
    duplica, dois consumidores não executam junto) e não prova DURABILIDADE. Em
    produção, a sede do lease tem de ser o banco. Trocar isto por uma tabela é
    trocar a implementação desta classe, não o contrato — que é o motivo de a
    porta existir em `aplicacao.RepositorioDeJobs`.
    """

    def __init__(self, *, relogio: Callable[[], float] = time.monotonic):
        self._por_id: dict[str, _Registro] = {}
        self._por_chave: dict[str, str] = {}
        self._trava = threading.Lock()
        self._relogio = relogio
        self._sequencia = 0

    def criar(self, job: dom.VisualProofJob, impressao: str) -> dom.VisualProofJob:
        with self._trava:
            existente_id = self._por_chave.get(job.chave_idempotencia)
            if existente_id is not None:
                registro = self._por_id[existente_id]
                if registro.impressao != impressao:
                    raise app.ConflitoDeIdempotencia(
                        "esta chave de idempotência já foi usada com uma entrada "
                        "diferente. O QA visual recusa em vez de escolher qual das duas "
                        "conferir.")
                return registro.job
            self._sequencia += 1
            self._por_id[job.job_id] = _Registro(
                job=job, impressao=impressao, ordem=self._sequencia)
            self._por_chave[job.chave_idempotencia] = job.job_id
            return job

    def obter(self, job_id: str) -> Optional[dom.VisualProofJob]:
        with self._trava:
            registro = self._por_id.get(job_id)
            return registro.job if registro else None

    def salvar(self, job: dom.VisualProofJob) -> None:
        with self._trava:
            registro = self._por_id.get(job.job_id)
            if registro is None:
                raise app.JobNaoEncontrado(job.job_id)
            registro.job = job

    def reivindicar(self, job_id: str, consumidor: str, lease_s: int) -> None:
        with self._trava:
            registro = self._por_id.get(job_id)
            if registro is None:
                raise app.JobNaoEncontrado(job_id)
            agora = self._relogio()
            if registro.lease_ate > agora and registro.lease_de != consumidor:
                raise app.JobEmExecucao(
                    "outro consumidor está executando este job de prova visual.")
            registro.lease_ate = agora + lease_s
            registro.lease_de = consumidor

    def liberar(self, job_id: str) -> None:
        with self._trava:
            registro = self._por_id.get(job_id)
            if registro is not None:
                registro.lease_ate = 0.0
                registro.lease_de = ""

    def ultimo_do_ativo(self, ativo_id: str, owner_sub: str) -> Optional[dom.VisualProofJob]:
        with self._trava:
            candidatos = [
                r for r in self._por_id.values()
                if r.job.ativo_id == ativo_id and r.job.owner_sub == owner_sub
            ]
        if not candidatos:
            return None
        return max(candidatos, key=lambda r: r.ordem).job


# ─────────────────────────────────────────────────────────────────────────────
# Broker por HTTP
# ─────────────────────────────────────────────────────────────────────────────


class BrokerHttp:
    """Cliente do broker. Loopback, Bearer próprio, e nenhum segredo de volta.

    ⚠️ **Escrito e testado contra o broker hermético desta entrega; nunca
    exercido contra um broker rodando ao lado de um AdsPower real.**
    """

    def __init__(self, *, endereco: Optional[str] = None, token: Optional[str] = None,
                 timeout_s: float = 60.0,
                 abridor: Optional[Callable[[urllib.request.Request, float], Any]] = None,
                 ambiente: Optional[Mapping[str, str]] = None):
        env = ambiente if ambiente is not None else os.environ
        self._endereco = (endereco if endereco is not None else env.get(VAR_ENDERECO, "")).strip().rstrip("/")
        self._token = (token if token is not None else env.get(VAR_TOKEN, "")).strip()
        self._timeout = timeout_s
        self._abridor = abridor or (
            lambda pedido, timeout: urllib.request.urlopen(pedido, timeout=timeout))  # noqa: S310

    @property
    def configurado(self) -> bool:
        """Endereço E token. Um sem o outro é configuração pela metade.

        Aceitar endereço sem token faria o plano de controle tentar, receber 401
        e reportar `indeterminate` — quando a resposta honesta é "este ambiente
        não tem broker".
        """
        return bool(self._endereco and self._token)

    def executar(self, pedido: dom.AdsPowerBrokerRequest, *,
                 consumidor: str) -> dom.AdsPowerBrokerReceipt:
        if not self.configurado:
            raise app.BrokerIndisponivel(
                f"o broker não está configurado neste ambiente ({VAR_ENDERECO} e "
                f"{VAR_TOKEN} precisam existir).")
        corpo = json.dumps(pedido.para_dicionario()).encode("utf-8")
        requisicao = urllib.request.Request(
            f"{self._endereco}/v1/operacoes", data=corpo, method="POST", headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}",
                "X-Volc-Consumidor": consumidor,
            })
        try:
            with self._abridor(requisicao, self._timeout) as resposta:
                bruto = json.loads(resposta.read(1_000_000).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise app.BrokerIndisponivel(
                f"o broker respondeu HTTP {exc.code} a esta operação.") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            log.warning("prova visual: falha ao falar com o broker: %s", type(exc).__name__)
            raise app.BrokerIndisponivel(
                "não foi possível falar com o broker do AdsPower agora.") from None
        return recibo_de_dicionario(bruto)


def recibo_de_dicionario(bruto: Any) -> dom.AdsPowerBrokerReceipt:
    """Lê o recibo sem confiar na forma — e sem aceitar campo sensível.

    Um broker comprometido (ou uma versão futura desatenta) poderia devolver
    `localizador` ou `user_id` no recibo. A varredura abaixo recusa o recibo
    inteiro em vez de guardar o campo "só porque veio".
    """
    if not isinstance(bruto, dict):
        raise app.BrokerIndisponivel("o broker respondeu em um formato desconhecido.")
    proibidos = {"localizador", "user_id", "api_key", "apikey", "cookie", "cookies",
                 "proxy", "authorization", "token", "senha", "password"}
    encontrados = sorted(set(bruto) & proibidos)
    if encontrados:
        raise app.BrokerIndisponivel(
            f"o broker devolveu campo(s) que este contrato proíbe: {', '.join(encontrados)}.")

    artefato_bruto = bruto.get("artefato")
    artefato = None
    if isinstance(artefato_bruto, dict) and artefato_bruto.get("sha256"):
        artefato = dom.VisualProofArtifact(
            referencia=str(artefato_bruto.get("referencia", "")),
            sha256=str(artefato_bruto.get("sha256", "")),
            bytes_=int(artefato_bruto.get("bytes", 0)),
            mime=str(artefato_bruto.get("mime", "image/png")),
            criado_em=str(artefato_bruto.get("criado_em", "")))

    return dom.AdsPowerBrokerReceipt(
        recibo_id=str(bruto.get("recibo_id", "")),
        pedido_id=str(bruto.get("pedido_id", "")),
        chave_idempotencia=str(bruto.get("chave_idempotencia", "")),
        operacao=str(bruto.get("operacao", "")),
        perfil_logico=str(bruto.get("perfil_logico", "")),
        owner_sub=str(bruto.get("owner_sub", "")),
        ativo_id=str(bruto.get("ativo_id", "")),
        estado=str(bruto.get("estado", "falhou")),
        motivo_codigo=str(bruto.get("motivo_codigo", "desconhecido")),
        motivo=str(bruto.get("motivo", "")),
        iniciado_em=str(bruto.get("iniciado_em", "")),
        concluido_em=str(bruto.get("concluido_em", "")),
        duracao_ms=int(bruto.get("duracao_ms", 0)),
        adspower_code=bruto.get("adspower_code"),
        url_final=bruto.get("url_final"),
        status_http=bruto.get("status_http"),
        redirecionamentos=tuple(bruto.get("redirecionamentos") or ()),
        artefato=artefato,
        console_resumo=dict(bruto.get("console_resumo") or {}),
        rede_resumo=dict(bruto.get("rede_resumo") or {}),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Leitor para a rota do Cofre
# ─────────────────────────────────────────────────────────────────────────────


class LeitorSemPersistencia:
    """O leitor que a API usa hoje — e ele DIZ que não há onde guardar.

    Este é o adaptador honesto para o estado real de 02/09/2026: não existe
    tabela de `VisualProofJob` no Supabase oficial, e nenhuma migration foi
    escrita nesta entrega. Devolver `None` sem explicação faria a tela mostrar
    "QA não executado", que é uma afirmação diferente e mais otimista.
    """

    def estado_da_persistencia(self) -> tuple[str, str]:
        return ("ausente",
                "não existe persistência de VisualProofJob: nenhuma migration foi "
                "escrita nem aplicada. Nada foi executado, e nada seria guardado.")

    def ultimo_job(self, ativo_id: str, owner_sub: str) -> Optional[dict[str, Any]]:
        return None


class LeitorEmMemoria:
    """Ponte entre o repositório hermético e a rota. Só para teste e piloto local."""

    def __init__(self, repositorio: RepositorioEmMemoria):
        self._repo = repositorio

    def estado_da_persistencia(self) -> tuple[str, str]:
        return ("disponivel", "repositório em memória — não sobrevive a reinício.")

    def ultimo_job(self, ativo_id: str, owner_sub: str) -> Optional[dict[str, Any]]:
        job = self._repo.ultimo_do_ativo(ativo_id, owner_sub)
        return job.para_dicionario() if job else None


__all__ = [
    "BrokerHttp", "LeitorEmMemoria", "LeitorSemPersistencia", "RepositorioEmMemoria",
    "VAR_ENDERECO", "VAR_TOKEN", "recibo_de_dicionario",
]
