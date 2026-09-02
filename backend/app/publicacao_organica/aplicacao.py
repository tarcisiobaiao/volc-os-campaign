"""A orquestracao: quem chama o banco, quem chama a porta, e em que ordem.

## A ordem existe para que um processo morto nao produza post fantasma

    1. criar job          -> o banco monta o SNAPSHOT e devolve o recibo
    2. liberar            -> o dono declara que pode sair
    3. reivindicar        -> lease + fencing; ninguem mais pega este job
    4. despachar          -> UMA chamada a porta, a partir do SNAPSHOT
    5. concluir           -> transicao atomica + recibo imutavel, com o fencing
    6. reconciliar        -> consulta o control plane e fecha o estado

O passo 4 e o unico que fala com o mundo. Ele acontece DEPOIS do 3 e ANTES do 5,
e as duas fronteiras importam: sem o 3, dois consumidores despacham o mesmo job;
sem o 5 com fencing, um consumidor que dormiu escreve por cima de quem assumiu.

## O que este modulo NUNCA faz

- **Nao rele a peca.** O texto e as imagens saem do `snapshot` devolvido por
  `reivindicar`. Reler o master aqui seria abrir a porta que a v14_01 fecha:
  uma versao nova criada depois da aprovacao mudaria o que sai.
- **Nao carimba a propria aprovacao.** `autorizacao_id` e uma linha que ja
  existia, criada por outra requisicao. O erro do Hub de Trafego — a rota que
  publica assinando a propria autorizacao — nao se repete aqui.
- **Nao transforma incerteza em desfecho.** `DesfechoIncerto` vira o estado
  `indeterminado`, e so a reconciliacao o resolve.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from app.publicacao_organica import dominio as dom
from app.publicacao_organica.portas import (
    DesfechoIncerto,
    FalhaDoControlPlane,
    PortaDePublicacao,
    ReciboExterno,
    SolicitacaoExterna,
)

log = logging.getLogger("volc.publicacao_organica")


class PublicacaoIndisponivel(Exception):
    """O banco da publicacao nao esta acessivel. NAO e "nenhum job"."""


class OperacaoRecusada(Exception):
    """Uma guarda recusou, e o motivo cabe na tela."""

    def __init__(self, mensagem: str, *, codigo: str, status: int = 409) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.status = status


class JobNaoEncontrado(Exception):
    """O job nao existe — ou nao e deste dono, que da a MESMA resposta."""


@dataclass(frozen=True)
class Autor:
    sub: str
    email: str


class Repositorio(Protocol):
    """O que a aplicacao precisa do banco. Uma funcao governada por metodo."""

    @property
    def configurado(self) -> bool: ...

    async def registrar_destino(self, payload: dict[str, Any], chave: str,
                                autor: Autor) -> dict[str, Any]: ...

    async def criar_job(self, payload: dict[str, Any], chave: str,
                        autor: Autor) -> dict[str, Any]: ...

    async def liberar(self, job_id: str, autor: Autor) -> dict[str, Any]: ...

    async def reivindicar(self, job_id: str, consumidor: str,
                          lease_segundos: int) -> dict[str, Any]: ...

    async def concluir_despacho(self, job_id: str, fencing: int, chave: str,
                                desfecho: str, recibo: dict[str, Any],
                                autor: Autor) -> dict[str, Any]: ...

    async def reconciliar(self, job_id: str, chave: str,
                          observacao: dict[str, Any], autor: Autor) -> dict[str, Any]: ...

    async def cancelar(self, job_id: str, motivo: str, autor: Autor) -> dict[str, Any]: ...

    async def listar_destinos(self, owner_sub: str) -> list[dict[str, Any]]: ...

    async def listar_jobs(self, owner_sub: str, estado: str | None,
                          limite: int) -> list[dict[str, Any]]: ...

    async def detalhar_job(self, job_id: str, owner_sub: str) -> dict[str, Any] | None: ...

    async def fila(self, limite: int) -> list[dict[str, Any]]: ...


#: Quanto tempo o lease dura. Generoso o bastante para uma chamada HTTP lenta,
#: curto o bastante para que um processo morto nao trave o job por horas.
LEASE_SEGUNDOS: int = 120


class CasosDeUso:
    """A aplicacao. Recebe o repositorio e a porta; nao constroi nenhum dos dois."""

    def __init__(self, repositorio: Repositorio, porta: PortaDePublicacao | None,
                 *, consumidor: str = "volc-despachante") -> None:
        self._repo = repositorio
        self._porta = porta
        self._consumidor = consumidor

    # -- leitura ------------------------------------------------------------

    async def destinos(self, autor: Autor) -> dict[str, Any]:
        self._exigir_banco()
        linhas = await self._repo.listar_destinos(autor.sub)
        # ⚠️ O INAPTO NAO E FILTRADO. Ele vem com `apto: false` e `motivo`, e a
        # tela o mostra desabilitado. Esconder o destino sem adapter tornaria
        # impossivel cumprir a guarda do ADR ("MultiPost nunca mascara a
        # ausencia de adapter oficial"): ninguem veria a lacuna.
        return {"destinos": linhas}

    async def jobs(self, autor: Autor, *, estado: str | None = None,
                   limite: int = 50) -> dict[str, Any]:
        self._exigir_banco()
        linhas = await self._repo.listar_jobs(autor.sub, estado, limite)
        return {"jobs": [self._com_leitura(j) for j in linhas]}

    async def job(self, job_id: str, autor: Autor) -> dict[str, Any]:
        self._exigir_banco()
        linha = await self._repo.detalhar_job(job_id, autor.sub)
        if linha is None:
            # ⚠️ MESMA RESPOSTA PARA "nao existe" E "nao e seu". A diferenca
            # revelaria a existencia do job alheio.
            raise JobNaoEncontrado(job_id)
        return self._com_leitura(linha)

    @staticmethod
    def _com_leitura(linha: dict[str, Any]) -> dict[str, Any]:
        """Acrescenta como o estado deve ser APRESENTADO — decidido no servidor.

        A regra "nunca verde para estado parcial" mora em `dominio`, e nao no
        CSS: um `className` condicional espalhado por componentes envelhece sem
        que ninguem perceba, e o sintoma e um operador confiando num verde.
        """
        leitura = dom.leitura_do_estado(str(linha.get("estado", "")))
        return {
            **linha,
            "leitura": {
                "rotulo": leitura.rotulo,
                "tom": leitura.tom,
                "proxima_acao": leitura.proxima_acao,
                "incerto": leitura.estado in dom.ESTADOS_INCERTOS,
                "terminal": leitura.estado in dom.ESTADOS_TERMINAIS,
            },
        }

    # -- escrita ------------------------------------------------------------

    async def registrar_destino(self, payload: dict[str, Any], autor: Autor,
                                chave: str | None = None) -> dict[str, Any]:
        self._exigir_banco()
        dom.recusar_chave_sensivel(payload, "destino")
        chave_final = chave or dom.chave_derivada(
            "dest", payload.get("ativo_id"), payload.get("plataforma"),
            payload.get("provedor", "postiz"))
        return await self._repo.registrar_destino(payload, chave_final, autor)

    async def criar_job(self, pedido: dom.PedidoDePublicacao, autor: Autor,
                        chave: str | None = None) -> dict[str, Any]:
        """Cria a intencao. Nada sai daqui para o control plane."""
        self._exigir_banco()
        chave_final = chave or dom.chave_de_idempotencia(pedido)
        if not dom.forma_de_chave_valida(chave_final):
            raise OperacaoRecusada(
                "chave de idempotencia fora da forma aceita",
                codigo="chave_invalida", status=400)
        return await self._repo.criar_job(pedido.como_payload(), chave_final, autor)

    async def liberar(self, job_id: str, autor: Autor) -> dict[str, Any]:
        self._exigir_banco()
        return await self._repo.liberar(job_id, autor)

    async def cancelar(self, job_id: str, motivo: str, autor: Autor) -> dict[str, Any]:
        self._exigir_banco()
        return await self._repo.cancelar(job_id, motivo, autor)

    # -- o passo que fala com o mundo ---------------------------------------

    async def despachar(self, job_id: str, autor: Autor) -> dict[str, Any]:
        """Reivindica, chama a porta UMA vez, conclui com o fencing recebido."""
        self._exigir_banco()
        self._exigir_porta()

        claim = await self._repo.reivindicar(job_id, self._consumidor, LEASE_SEGUNDOS)
        if not claim.get("reivindicado"):
            raise OperacaoRecusada(
                str(claim.get("motivo") or "este job nao pode ser despachado agora"),
                codigo="nao_reivindicado", status=409)

        fencing = int(claim["fencing"])
        snapshot = claim.get("solicitacao") or {}
        solicitacao = self._solicitacao_do_snapshot(snapshot)

        desfecho: str
        recibo: dict[str, Any]
        try:
            externo = await self._enviar(solicitacao)
            desfecho, recibo = "sucesso", externo.como_recibo()
        except DesfechoIncerto as exc:
            # ⚠️ AQUI MORA A DIFERENCA ENTRE UM POST DUPLICADO E UM ESTADO
            # HONESTO. Nao sabemos se chegou; nao inventamos recibo e nao
            # declaramos falha.
            desfecho, recibo = "indeterminado", {"erro": dom.sanitizar_erro(str(exc))}
            log.warning("publicacao organica: desfecho incerto no job %s", job_id)
        except FalhaDoControlPlane as exc:
            desfecho, recibo = "falha", {
                "erro": dom.sanitizar_erro(str(exc)),
                "permanente": exc.permanente,
            }
        except dom.PedidoRecusado as exc:
            # O recibo do provedor trazia material de credencial. Isso NAO vira
            # sucesso: o recibo e a prova, e uma prova que nao pode ser gravada
            # deixa o desfecho incerto.
            desfecho, recibo = "indeterminado", {
                "erro": "o control plane devolveu um recibo que este contrato recusa gravar",
                "codigo": exc.codigo,
            }

        chave = dom.chave_derivada("desp", job_id, fencing)
        return await self._repo.concluir_despacho(
            job_id, fencing, chave, desfecho, recibo, autor)

    async def _enviar(self, solicitacao: SolicitacaoExterna) -> ReciboExterno:
        assert self._porta is not None  # garantido por _exigir_porta
        if solicitacao.modo == "draft":
            return await self._porta.criar_rascunho(solicitacao)
        if solicitacao.modo == "schedule":
            return await self._porta.agendar(solicitacao)
        if solicitacao.modo == "now":
            # O consentimento ja foi exigido no banco (CHECK + funcao governada)
            # e no dominio. Chegar aqui com modo `now` significa que um humano
            # disse sim para ESTE job.
            return await self._porta.publicar_agora(solicitacao)
        raise FalhaDoControlPlane(f"modo desconhecido no snapshot: {solicitacao.modo}")

    @staticmethod
    def _solicitacao_do_snapshot(snapshot: dict[str, Any]) -> SolicitacaoExterna:
        """Traduz o snapshot IMUTAVEL no pedido externo. Sem reler nada."""
        destino = snapshot.get("destino") or {}
        quando = snapshot.get("quando") or {}
        corpo = snapshot.get("corpo") or {}

        referencia = destino.get("referencia_externa")
        if not referencia:
            raise OperacaoRecusada(
                "o snapshot deste job nao tem referencia de canal; ele nao pode ser despachado",
                codigo="destino_sem_referencia", status=409)

        instante = quando.get("instante_utc")
        if isinstance(instante, str) and instante:
            # O banco devolve `+00:00`; a API do Postiz quer ISO UTC. Trocar o
            # sufixo e suficiente e nao recalcula nada — recalcular aqui seria a
            # segunda implementacao da conversao que a v14_01 evita ter.
            instante = instante.replace("+00:00", "Z").replace(" ", "T")

        return SolicitacaoExterna(
            referencia_do_canal=str(referencia),
            modo=str(quando.get("modo") or "draft"),
            texto=str(corpo.get("texto") or ""),
            instante_utc=instante or None,
            imagens=tuple(str(u) for u in (corpo.get("imagens") or [])),
            plataforma=str(destino.get("plataforma") or ""),
        )

    # -- reconciliacao ------------------------------------------------------

    async def reconciliar(self, job_id: str, autor: Autor) -> dict[str, Any]:
        """Pergunta ao control plane o que aconteceu e fecha (ou nao) o estado."""
        self._exigir_banco()
        self._exigir_porta()
        assert self._porta is not None

        linha = await self._repo.detalhar_job(job_id, autor.sub)
        if linha is None:
            raise JobNaoEncontrado(job_id)

        referencia = _ultima_referencia(linha)
        if not referencia:
            # Sem referencia externa nao ha o que perguntar. Isso acontece com um
            # job que ficou `indeterminado` num timeout ANTES de qualquer id — e
            # e o caso mais delicado: nao sabemos nem o que procurar.
            observacao = {
                "estado_externo": "DESCONHECIDO",
                "nota": "o job nao tem referencia externa conhecida; "
                        "a conferencia precisa ser feita no painel do control plane",
            }
        else:
            try:
                achado = await self._porta.consultar(str(referencia))
            except DesfechoIncerto as exc:
                raise OperacaoRecusada(
                    dom.sanitizar_erro(
                        f"nao foi possivel conferir agora: {exc}"),
                    codigo="reconciliacao_indisponivel", status=503) from exc
            except FalhaDoControlPlane as exc:
                raise OperacaoRecusada(
                    dom.sanitizar_erro(f"o control plane recusou a consulta: {exc}"),
                    codigo="reconciliacao_recusada", status=502) from exc

            if achado is None:
                # ⚠️ NAO ENCONTRAR NAO REPROVA E NAO APAGA. O job continua onde
                # esta e a observacao registra que nao achamos.
                observacao = {
                    "estado_externo": "DESCONHECIDO",
                    "nota": "o control plane nao devolveu este post na janela consultada",
                }
            else:
                observacao = achado.como_recibo()

        chave = dom.chave_derivada(
            "recon", job_id, observacao.get("estado_externo"),
            observacao.get("url_publicada"), observacao.get("publicado_em"))
        return await self._repo.reconciliar(job_id, chave, observacao, autor)

    # -- prontidao ----------------------------------------------------------

    async def prontidao(self) -> dict[str, Any]:
        """Nunca levanta: prontidao que falha e uma resposta, nao um 500."""
        if self._porta is None:
            return {
                "pronto": False,
                "fonte": "sem-adaptador",
                "detalhe": "nenhum control plane configurado neste ambiente",
            }
        try:
            p = await self._porta.prontidao()
        except Exception as exc:  # noqa: BLE001 — prontidao nunca derruba a rota
            return {"pronto": False, "fonte": "erro", "detalhe": dom.sanitizar_erro(str(exc))}
        return {
            "pronto": p.pronto, "fonte": p.fonte, "detalhe": p.detalhe,
            "canais_visiveis": p.canais_visiveis,
        }

    # -- guardas ------------------------------------------------------------

    def _exigir_banco(self) -> None:
        if not self._repo.configurado:
            # Falha FECHADA. Um control plane sem banco nao e um control plane
            # vazio — e a tela precisa distinguir "nao ha jobs" de "nao sei".
            raise PublicacaoIndisponivel(
                "a publicacao organica nao tem banco configurado neste ambiente")

    def _exigir_porta(self) -> None:
        if self._porta is None:
            raise OperacaoRecusada(
                "nenhum control plane esta configurado; nada pode ser despachado",
                codigo="sem_control_plane", status=503)


def _ultima_referencia(linha: dict[str, Any]) -> str | None:
    recibos = linha.get("recibos") or []
    for recibo in reversed(recibos):
        if isinstance(recibo, dict) and recibo.get("referencia_externa"):
            return str(recibo["referencia_externa"])
    return None
