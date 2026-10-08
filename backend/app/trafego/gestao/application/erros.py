"""As recusas da gestão, tipadas — o router decide o HTTP só olhando a classe.

Sem import de `volc_ads` aqui, de propósito: o router importa este módulo no
topo, e o pacote do motor puxa o SDK do Google. Se este arquivo o importasse, o
backend inteiro deixaria de subir num ambiente sem o SDK — a mesma razão pela
qual `routers/trafego.py` importa o motor tarde.

Cada classe carrega `codigo` (estável, para o front decidir o que mostrar) e,
quando faz sentido, `detalhe` (dados para a tela, nunca texto para parsear).
"""
from __future__ import annotations

from typing import Any, Optional


class ErroDeGestao(RuntimeError):
    """Base. `status` é a sugestão de HTTP; o router é quem decide."""

    status = 400
    codigo = "gestao"

    def __init__(self, mensagem: str, *, codigo: Optional[str] = None,
                 detalhe: Any = None) -> None:
        super().__init__(mensagem)
        if codigo:
            self.codigo = codigo
        self.detalhe = detalhe

    def corpo(self) -> dict:
        saida = {"codigo": self.codigo, "mensagem": str(self)}
        if self.detalhe is not None:
            saida["detalhe"] = self.detalhe
        return saida


class AcaoInvalida(ErroDeGestao):
    """O payload não monta uma ação, ou o estado lido não a permite (AcaoRecusada)."""

    status = 422
    codigo = "acao_invalida"


class ForaDaCasa(ErroDeGestao):
    """Conta fora da árvore do MCC da casa (`escopo.conta_da_casa`). Nada foi lido nem gravado.

    403 e não 409: não é estado que muda, é fronteira que não se negocia.
    """

    status = 403
    codigo = "fora_do_escopo"


class NaoEncontrado(ErroDeGestao):
    status = 404
    codigo = "nao_encontrado"


class ConflitoDeEstado(ErroDeGestao):
    """A proposta/aplicação não está num estado que permita o pedido."""

    status = 409
    codigo = "estado_invalido"


class AntesDivergiu(ConflitoDeEstado):
    """O "antes" relido na conta não é o "antes" que o humano aprovou.

    Aplicar mesmo assim seria aplicar uma decisão a um mundo que ela não viu —
    e o reverso, que sai do `valor_anterior`, restauraria um estado que ninguém
    aprovou como ponto de partida.
    """

    codigo = "antes_divergiu"


class RegraAusente(ConflitoDeEstado):
    """Não há versão vigente da regra pedida. A proposta não tem contra o que ser medida."""

    codigo = "regra_ausente"


class CampanhaNaoImportada(ConflitoDeEstado):
    """Proposta de nível campanha exige a identidade em `trafego_campanha`."""

    codigo = "campanha_nao_importada"


class EvidenciaInsuficiente(ConflitoDeEstado):
    codigo = "evidencia_insuficiente"


class ForaDaRegra(ConflitoDeEstado):
    """Espelho de `trafego_proposta_respeita_regra`: limite, teto ou delta ausente."""

    codigo = "fora_da_regra"


class ExigeAprovacaoHumana(ConflitoDeEstado):
    """T1: sem `trafego_aprovacao` com decisão `aprovada`, nada sai."""

    codigo = "exige_aprovacao_humana"


class EmCarencia(ConflitoDeEstado):
    codigo = "em_carencia"


class EscritaBloqueada(ConflitoDeEstado):
    """A trava de dois fatores (`modo.destravar` + FORGE_PERMITIR_ESCRITA=1) está fechada.

    É 409 e não 503: o processo funciona, ele só não está autorizado a escrever.
    A aplicação fica registrada como `erro` — nada saiu para o Google.
    """

    codigo = "escrita_bloqueada"


class BancoRecusou(ConflitoDeEstado):
    """Um gatilho/CHECK da v10_02 disparou. `detalhe.sqlstate` diz qual família."""

    codigo = "banco_recusou"


class Indisponivel(ErroDeGestao):
    """Banco ou Google não responderam. NÃO significa que algo foi recusado."""

    status = 503
    codigo = "indisponivel"
