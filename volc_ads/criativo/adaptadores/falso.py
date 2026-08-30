"""Motor de criativo falso — determinístico, de graça, e capaz de errar sob encomenda.

## Por que um falso, e por que ELE é o primeiro adaptador

Porque o ciclo inteiro precisa rodar sem gastar. `copy/mock.py` existe pela
mesma razão e ensinou a mesma lição: um mock que só sabe acertar prova metade
do sistema. Os caminhos que importam — proporção errada, arquivo pesado demais,
geração recusada, medida ausente — nunca são exercitados se o falso for
otimista, e são exatamente os caminhos onde o dinheiro vaza.

Por isso este motor erra **sob encomenda**: o teste declara qual defeito quer
em qual índice do pedido, e o motor entrega aquilo, sempre igual.

## Determinismo, e por que o conteúdo não depende do id do pedido

Os bytes saem de `(referência, tipo, insumo, índice)` — nunca do id do pedido
nem do relógio. É isso que permite provar a deduplicação: dois pedidos
idênticos, em dois motores diferentes, produzem o MESMO hash, e o catálogo
tem de reconhecer o reencontro em vez de criar um segundo asset.
"""

from __future__ import annotations

import hashlib
from enum import Enum

from ..contrato import Falha, TipoDeAsset, e_binario
from ..porta import (
    ArquivoGerado,
    GeracaoPendente,
    MotorIndisponivel,
    PedidoDeGeracao,
    PedidoDesconhecido,
    RespostaDoMotor,
)

_MIME_PADRAO = "image/png"
_DIMENSAO_PADRAO = (1200, 628)
_DURACAO_PADRAO = 15.0


class Defeito(Enum):
    """O que se pede ao motor falso para estragar."""

    NENHUM = "nenhum"
    PEQUENO_DEMAIS = "pequeno_demais"        # abaixo da dimensão mínima
    PROPORCAO_ERRADA = "proporcao_errada"    # cabe no mínimo, proporção não bate
    PESADO_DEMAIS = "pesado_demais"          # estoura o teto de bytes
    SEM_MEDIDA = "sem_medida"                # largura/altura desconhecidas
    MIME_ERRADO = "mime_errado"              # formato fora da lista
    CURTO_DEMAIS = "curto_demais"            # vídeo abaixo da duração mínima
    TEXTO_LONGO = "texto_longo"              # estoura o limite de caractere
    RECUSADO = "recusado"                    # não vira arquivo: vira falha


def _base_da_especificacao(spec) -> tuple[int, int]:
    """O tamanho "certo" para uma especificação, derivado da PROPORÇÃO.

    Antes isto olhava só `dimensao_recomendada` e caía num padrão 1.91:1 quando
    ela faltava — o que fazia o falso produzir uma paisagem no slot quadrado e
    reprovar sozinho. Nem toda especificação oficial traz recomendada (o Display
    não traz: a matriz marca como `[NÃO CONFIRMADO]`), mas todas trazem
    proporção e mínimo, e é deles que o tamanho tem de sair.
    """
    if spec is None:
        return _DIMENSAO_PADRAO
    if spec.largura_recomendada and spec.altura_recomendada:
        return spec.largura_recomendada, spec.altura_recomendada
    if spec.proporcao_alvo is None:
        return _DIMENSAO_PADRAO

    largura_alvo, altura_alvo = spec.proporcao_alvo
    largura = max(spec.largura_minima or 0, _DIMENSAO_PADRAO[0])
    altura = round(largura * altura_alvo / largura_alvo)
    if spec.altura_minima and altura < spec.altura_minima:
        altura = spec.altura_minima
        largura = round(altura * largura_alvo / altura_alvo)
    return largura, altura


class MotorFalso:
    """Cumpre `porta.MotorDeCriativo` sem sair da máquina.

    `defeitos` mapeia índice dentro do pedido para o estrago desejado; os
    índices não citados saem válidos. `pendencias` é quantas vezes `receber`
    deve responder "ainda não" antes de entregar — é o que exercita o contrato
    de dois passos contra um motor que, por dentro, é síncrono.
    """

    nome = "falso"
    versao = "1"
    tipos_suportados = frozenset(TipoDeAsset)

    def __init__(
        self,
        *,
        defeitos: dict[int, Defeito] | None = None,
        pendencias: int = 0,
        indisponivel: bool = False,
    ) -> None:
        self.defeitos = dict(defeitos or {})
        self.pendencias = pendencias
        self.indisponivel = indisponivel
        self._pedidos: dict[str, PedidoDeGeracao] = {}
        self._faltam: dict[str, int] = {}
        self._contador = 0
        self.chamadas: list[PedidoDeGeracao] = []   # o que o teste inspeciona

    # -- porta --

    def solicitar_geracao(self, pedido: PedidoDeGeracao) -> str:
        if self.indisponivel:
            raise MotorIndisponivel("motor falso configurado como fora do ar")
        self._contador += 1
        id_do_pedido = f"falso-{self._contador:03d}"
        self._pedidos[id_do_pedido] = pedido
        self._faltam[id_do_pedido] = self.pendencias
        self.chamadas.append(pedido)
        return id_do_pedido

    def receber(self, id_do_pedido: str) -> RespostaDoMotor:
        pedido = self._pedidos.get(id_do_pedido)
        if pedido is None:
            raise PedidoDesconhecido(
                f"{id_do_pedido!r} não foi emitido por este motor", pedido=id_do_pedido
            )
        if self._faltam[id_do_pedido] > 0:
            self._faltam[id_do_pedido] -= 1
            raise GeracaoPendente("ainda gerando", pedido=id_do_pedido)

        arquivos: list[ArquivoGerado] = []
        falhas: list[Falha] = []
        for i in range(pedido.quantidade):
            defeito = self.defeitos.get(i, Defeito.NENHUM)
            if defeito is Defeito.RECUSADO:
                falhas.append(Falha(
                    referencia=f"{id_do_pedido}#{i}",
                    motivo="motor falso recusou este item sob encomenda",
                    codigo="MOTOR.recusado",
                    tipo=pedido.tipo,
                    permanente=True,
                ))
                continue
            arquivos.append(self._arquivo(pedido, i, defeito))

        return RespostaDoMotor(
            pedido=id_do_pedido,
            arquivos=tuple(arquivos),
            falhas=tuple(falhas),
            custo_usd=0.0,
        )

    # -- fabricação --

    def _semente(self, pedido: PedidoDeGeracao, indice: int) -> bytes:
        crua = f"{pedido.referencia}|{pedido.tipo.value}|{pedido.insumo}|{indice}"
        return hashlib.sha256(crua.encode("utf-8")).digest()

    def _arquivo(
        self, pedido: PedidoDeGeracao, indice: int, defeito: Defeito
    ) -> ArquivoGerado:
        if not e_binario(pedido.tipo):
            return self._texto(pedido, indice, defeito)

        spec = pedido.especificacao
        semente = self._semente(pedido, indice)

        if pedido.tipo is TipoDeAsset.VIDEO:
            duracao = (spec.duracao_minima_s if spec and spec.duracao_minima_s
                       else _DURACAO_PADRAO)
            if defeito is Defeito.CURTO_DEMAIS:
                duracao = max(0.5, duracao / 4)
            return ArquivoGerado(
                conteudo=semente * 4,
                mime="video/mp4" if defeito is not Defeito.MIME_ERRADO else "video/avi",
                duracao_s=duracao,
                metadados={"rotulo": f"{pedido.referencia} vídeo {indice}"},
            )

        largura, altura = self._dimensao(spec, defeito)
        conteudo = semente * 4
        if defeito is Defeito.PESADO_DEMAIS:
            teto = (spec.bytes_maximos if spec and spec.bytes_maximos else 1024)
            conteudo = semente + b"\x00" * teto

        return ArquivoGerado(
            conteudo=conteudo,
            mime=_MIME_PADRAO if defeito is not Defeito.MIME_ERRADO else "image/bmp",
            largura=largura,
            altura=altura,
            metadados={"rotulo": f"{pedido.referencia} {pedido.tipo.value} {indice}"},
        )

    def _dimensao(self, spec, defeito: Defeito) -> tuple[int | None, int | None]:
        if defeito is Defeito.SEM_MEDIDA:
            # A ausência de medida é o caso mais traiçoeiro e por isso está aqui:
            # é o que um motor real que devolve só bytes produz por padrão.
            return None, None

        largura, altura = base = _base_da_especificacao(spec)

        if defeito is Defeito.PEQUENO_DEMAIS:
            if spec is not None and spec.largura_minima:
                largura = max(1, spec.largura_minima // 2)
                altura = max(1, round(largura * (base[1] / base[0])))
            else:
                largura, altura = max(1, largura // 8), max(1, altura // 8)
        elif defeito is Defeito.PROPORCAO_ERRADA:
            # Cresce a altura mantendo a largura: continua acima do mínimo, mas
            # a proporção sai da tolerância. É o erro que o motor real comete
            # quando o tamanho pedido não é um dos que ele aceita.
            altura = round(altura * 1.4) + 1
        return largura, altura

    def _texto(
        self, pedido: PedidoDeGeracao, indice: int, defeito: Defeito
    ) -> ArquivoGerado:
        spec = pedido.especificacao
        base = f"{pedido.referencia} {pedido.tipo.value} {indice}"
        if defeito is Defeito.TEXTO_LONGO:
            teto = (spec.caracteres_maximos if spec and spec.caracteres_maximos else 30)
            base = (base + " ") * (teto // max(1, len(base)) + 2)
        elif spec is not None and spec.caracteres_maximos:
            base = base[: spec.caracteres_maximos]
        return ArquivoGerado(texto=base, metadados={"rotulo": base[:40]})
