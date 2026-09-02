"""Os casos de uso do broker e as PORTAS que eles exigem do mundo externo.

Nada aqui sabe o que e httpx, `op` ou AdsPower. O que este arquivo sabe e que
existe uma fonte capaz de entregar um Bearer ativo, uma porta capaz de fazer
uma pergunta em loopback, e um relogio.

## A ordem das recusas, e por que ela e a ordem

    verificacao ligada -> acao -> perfil -> parametros -> timeout -> chave
    -> segredo -> rede

O segredo e o PENULTIMO passo de proposito. Pedir a chave antes de saber se o
pedido e legitimo faz o 1Password mostrar um prompt de aprovacao para uma acao
que ia ser recusada de qualquer jeito — e um prompt que aparece sem motivo
ensina quem opera a aprovar sem ler.

## O que este broker nao faz

Nao resolve `op://`. Quem resolve e o `op run` que o envolve, fora deste
processo. O broker so confere que a injecao ACONTECEU (o valor chegou, e nao a
referencia literal) e falha fechado quando nao aconteceu — que e exatamente o
que trancar o 1Password produz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from app.asset_vault.broker import dominio as dom

FERRAMENTA = "cofre-broker-adspower"
TAREFA = "P03-T11"


class FonteDeSegredo(Protocol):
    """De onde vem o Bearer. A unica implementacao real le do ambiente."""

    @property
    def nome_da_variavel(self) -> str: ...

    @property
    def origem(self) -> str: ...

    def bearer(self) -> dom.Segredo: ...

    def referencia_declarada(self) -> str | None: ...


class PortaLocalApi(Protocol):
    """A porta para o AdsPower. Recebe o Segredo, nunca o texto da chave."""

    async def chamar(self, acao: dom.Acao, parametros: Mapping[str, str],
                     bearer: dom.Segredo, timeout_s: float) -> Any: ...


class Relogio(Protocol):
    def agora(self) -> datetime: ...


class RelogioDoSistema:
    def agora(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Pedido:
    """Um pedido ao broker.

    ⚠️ Nao ha campo para segredo nem para localizador, e a ausencia e o
    contrato: um `Pedido` e construido a partir de argv, e o que entra em argv
    aparece em `ps`, no historico do shell e no log do supervisor.
    """

    acao: str
    chave_idempotencia: str
    perfil: str | None = None
    parametros: Mapping[str, Any] = field(default_factory=dict)
    timeout_s: float | None = None


@dataclass
class Registro:
    """Idempotencia do broker: mesma chave + mesma entrada devolve o recibo.

    ⚠️ LACUNA NOMEADA: este registro vive no processo. Um sidecar reiniciado
    esquece o que fez, e a segunda chamada com a mesma chave conta como nova.
    A durabilidade mora no Cofre — o recibo vira verificacao por
    `POST /api/cofre/ativos/{id}/verificacoes`, que e idempotente no banco.
    Prometer durabilidade aqui seria prometer o que este processo nao tem.
    """

    _por_chave: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)

    def consultar(self, chave: str, digital: str) -> dict[str, Any] | None:
        achado = self._por_chave.get(chave)
        if achado is None:
            return None
        digital_gravada, recibo = achado
        if digital_gravada != digital:
            # Mesma semantica do Cofre: mesma chave com entrada diferente e
            # CONFLITO, nao operacao nova. A frase nao repete a chave.
            raise dom.BrokerRecusado(
                "esta chave de idempotencia ja foi usada para um pedido diferente. "
                "Reusar a chave com outra entrada esconderia duas operacoes numa so.",
                estado="falha/conflito_de_idempotencia")
        return recibo

    def gravar(self, chave: str, digital: str, recibo: dict[str, Any]) -> None:
        self._por_chave[chave] = (digital, recibo)


class Broker:
    """Os atos do broker. Todos perguntam; nenhum muta."""

    def __init__(self, *, endereco: str, perfis_permitidos: tuple[str, ...],
                 fonte: FonteDeSegredo, porta: PortaLocalApi,
                 registro: Registro | None = None, relogio: Relogio | None = None):
        # O endereco e validado na CONSTRUCAO: um broker apontado para fora da
        # maquina nao deve chegar a existir, muito menos a receber um pedido.
        self._endereco = dom.exigir_endereco_de_loopback(endereco)
        self._perfis = tuple(p for p in perfis_permitidos if p)
        self._fonte = fonte
        self._porta = porta
        self._registro = registro if registro is not None else Registro()
        self._relogio = relogio if relogio is not None else RelogioDoSistema()

    @property
    def endereco(self) -> str:
        return self._endereco

    async def executar(self, pedido: Pedido) -> dict[str, Any]:
        acao = dom.exigir_acao(pedido.acao)
        perfil = None
        if acao.exige_perfil:
            perfil = dom.exigir_perfil(pedido.perfil, self._perfis)
        elif pedido.perfil:
            raise dom.BrokerRecusado(
                f"a acao {acao.nome} nao age sobre um perfil especifico; nao envie --perfil.")
        parametros = dom.exigir_parametros(acao, dict(pedido.parametros or {}))
        if perfil is not None:
            parametros["user_id"] = perfil
        timeout_s = dom.exigir_timeout(pedido.timeout_s)
        chave = dom.exigir_chave_de_idempotencia(pedido.chave_idempotencia)

        digital = dom.impressao_digital(acao.nome, perfil, parametros, self._endereco)
        anterior = self._registro.consultar(chave, digital)
        if anterior is not None:
            # Replay VISIVEL. Devolver o recibo antigo sem dizer que e replay
            # faria um retry parecer uma segunda observacao.
            repetido = dict(anterior)
            repetido["idempotente"] = True
            return repetido

        # Somente aqui o segredo entra em cena. Ver o docstring do modulo.
        bearer = self._fonte.bearer()

        inicio = self._relogio.agora()
        estado = "ok"
        resultado: dict[str, Any] = {}
        try:
            bruto = await self._porta.chamar(acao, parametros, bearer, timeout_s)
            resultado = dom.projetar_resposta(acao, bruto)
        except dom.AcessoIndisponivel as exc:
            estado = exc.estado
            resultado = {"indisponivel": str(exc)}
        fim = self._relogio.agora()

        recibo = self._recibo(
            acao=acao, perfil=perfil, parametros=parametros, chave=chave,
            digital=digital, estado=estado, resultado=resultado,
            inicio=inicio, fim=fim, timeout_s=timeout_s)

        # Ultima peneira antes de o recibo existir para qualquer outro codigo.
        dom.recusar_vazamento(recibo)
        self._registro.gravar(chave, digital, recibo)
        return recibo

    def _recibo(self, *, acao: dom.Acao, perfil: str | None, parametros: Mapping[str, str],
                chave: str, digital: str, estado: str, resultado: Mapping[str, Any],
                inicio: datetime, fim: datetime, timeout_s: float) -> dict[str, Any]:
        """O recibo: o que aconteceu, e nada que alguem possa usar.

        `bearer` aparece como POSTURA — presente, de onde veio, com que nome —
        e nunca como valor. E o mesmo desenho de `referencia_de_acesso` no
        handoff do Cofre: suficiente para conferir que a chave certa foi usada,
        insuficiente para alguem pegar.
        """
        return {
            "ferramenta": FERRAMENTA,
            "tarefa": TAREFA,
            "run_id": digital[:16],
            "acao": acao.nome,
            "muta": acao.muta,
            "descricao": acao.descricao,
            "endereco": self._endereco,
            "perfil": perfil,
            "parametros": dict(parametros),
            "bearer": {
                "presente": True,
                "origem": self._fonte.origem,
                "nome_da_variavel": self._fonte.nome_da_variavel,
            },
            "referencia": dom.forma_da_referencia(self._fonte.referencia_declarada()),
            "chave_idempotencia": chave,
            "idempotente": False,
            "estado": estado,
            "codigo_de_saida": dom.ESTADOS.get(estado, dom.ESTADOS["falha/interna"]),
            "timeout_s": timeout_s,
            "duracao_ms": max(0, int((fim - inicio).total_seconds() * 1000)),
            "observado_em": inicio.isoformat(timespec="seconds"),
            "resultado": dict(resultado),
            # O recibo do broker vira verificacao no Cofre. Dizer isso aqui evita
            # que alguem invente um alvo diferente e a trilha fique ilegivel.
            "vira_verificacao_como": {
                "rota": "POST /api/cofre/ativos/{ativo_id}/verificacoes",
                "alvo": "credencial",
                "procedencia": "live_observation",
            },
        }
