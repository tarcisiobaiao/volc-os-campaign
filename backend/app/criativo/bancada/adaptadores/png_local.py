"""O motor local de PNG dentro da bancada — o mesmo desenho, sem dependência.

## Por que a bancada precisa de um segundo motor local

`MotorTipografico` já produz pixel real e determinístico, e continua sendo o
motor de tipografia da casa. Ele tem, porém, dois pré-requisitos que nem toda
máquina cumpre:

  1. **Pillow.** Importado dentro de `produzir()` e de `versoes_congeladas()`, e
     ausente de `backend/requirements.txt` — a mesma dependência não declarada
     que `criativo/adaptadores/medir_imagem.py` recusou pagar. Numa máquina sem
     Pillow o motor **se registra** (o `try/except FalhaDoMotor` de
     `servico.montar()` não pega `ImportError`) e falha depois, no meio do
     render.
  2. **Uma fonte.** Sem `fontes/Inter-Variable.ttf` nem `CRIATIVO_FONTES_DIR`,
     ele falha com motivo — corretamente, e ainda assim falha.

Este motor não tem nenhum dos dois: `zlib` e `struct` vêm com o interpretador.
Ele é o piso — o que garante que a bancada consegue produzir **alguma** peça em
qualquer máquina, e portanto que o caminho fila → operário → gate → recibo é
exercitável sem preparação de ambiente.

## Por que ele NÃO redesenha nada

O desenho mora em `volc_ads/criativo/adaptadores/png_local.desenhar`, e este
arquivo o importa. Copiar as trinta linhas para cá produziria dois desenhos que
concordam hoje e divergem no dia em que alguém consertar só um — e a divergência
apareceria como dois sha256 diferentes para o mesmo pedido, que é exatamente o
sintoma mais caro de investigar.

A direção da dependência é a que já existe: `backend/app/criativo/dominio.py`
importa `volc_ads.criativo.contrato` desde a v11. O engine não sabe que o backend
existe, e continua assim.

## Natureza

`natureza = "local"`. Ela é atributo do MOTOR porque quem sabe se um arquivo pode
ser publicado é quem o produziu. `servico.py` a lê e a carimba no envelope, e a
ponte a usa para recusar promoção a produção. Um motor que não a declara vale
`nao_declarada` — nunca `producao`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from volc_ads.criativo.adaptadores.png_local import (
    VERSAO_DO_ADAPTADOR,
    VERSAO_DO_ALGORITMO,
    desenhar,
)
from volc_ads.criativo.contrato import NaturezaDaProcedencia

from ..contrato import Artefato, Encomenda, FalhaDoMotor

SLUG = "png-local"


class MotorPngLocal:
    """Cumpre `bancada.contrato.MotorDeProducao` sem sair da máquina.

    Determinismo: a semente de cada saída sai de `(seed, slot, largura, altura,
    insumo)`. O `seed` da encomenda participa porque a bancada o exige — um
    render sem semente é um render que não pode ser repetido —, e o `slot`
    participa para que duas saídas da MESMA encomenda não saiam idênticas, o que
    faria o catálogo deduplicá-las e o lote perder um papel sem dizer nada.
    """

    slug = SLUG
    versao = VERSAO_DO_ADAPTADOR
    natureza = NaturezaDaProcedencia.LOCAL
    #: O que este motor produz. O catalogo pergunta; ele nao chuta.
    midias = ("imagem",)

    def versoes_congeladas(self) -> dict[str, str]:
        import zlib  # noqa: PLC0415 — só para ler a versão

        return {
            "adaptador": VERSAO_DO_ADAPTADOR,
            "algoritmo": VERSAO_DO_ALGORITMO,
            "zlib": zlib.ZLIB_VERSION,
        }

    def produzir(self, encomenda: Encomenda, dir_trabalho: str) -> tuple[Artefato, ...]:
        destino = Path(dir_trabalho)
        if not destino.is_dir():
            raise FalhaDoMotor(
                f"diretorio de trabalho inexistente: {destino}", permanente=True
            )
        if not encomenda.saidas:
            raise FalhaDoMotor(
                "encomenda sem saida: nao ha o que produzir", permanente=True
            )

        insumo = str(encomenda.parametros.get("insumo") or "").strip()
        if not insumo:
            # Sem insumo o pixel seria o mesmo para qualquer briefing, e a
            # procedência diria que ele veio de um prompt que não existiu.
            raise FalhaDoMotor(
                "sem insumo: gerar a partir de que?", permanente=True
            )

        artefatos: list[Artefato] = []
        for saida in encomenda.saidas:
            if saida.midia != "imagem":
                raise FalhaDoMotor(
                    f"este motor produz imagem; pediram {saida.midia}",
                    permanente=True,
                )
            semente = hashlib.sha256(
                f"{encomenda.seed}|{saida.slot}|{saida.largura}x{saida.altura}"
                f"|{insumo}|{VERSAO_DO_ALGORITMO}".encode("utf-8")
            ).digest()
            try:
                dados = desenhar(saida.largura, saida.altura, semente)
            except ValueError as exc:
                # Dimensão fora do teto: erro do PEDIDO, e retentar o mesmo
                # pedido erra igual.
                raise FalhaDoMotor(str(exc), permanente=True) from exc

            caminho = destino / f"{_nome_de_arquivo(saida.slot)}.png"
            caminho.write_bytes(dados)

            # ⚠️ Medido do DISCO, não das variáveis acima. O operário confere
            # bytes e hash contra o arquivo, e um motor que declarasse o que
            # pretendia escrever — em vez do que escreveu — passaria no gate com
            # uma ficção. O gate existe justamente porque isso já aconteceu.
            do_disco = caminho.read_bytes()
            artefatos.append(Artefato(
                slot=saida.slot,
                caminho=str(caminho),
                mime="image/png",
                bytes_=len(do_disco),
                sha256=hashlib.sha256(do_disco).hexdigest(),
                largura=saida.largura,
                altura=saida.altura,
                duracao_s=None,   # imagem não tem duração; `0.0` seria mentira
            ))
        return tuple(artefatos)


def _nome_de_arquivo(slot: str) -> str:
    """O slot vira nome de arquivo, e nome de arquivo não pode escapar da pasta.

    Sanitizado pelo mesmo motivo que `Operario._pasta_da_reivindicacao`
    sanitiza o nome do operário: o slot vem do pedido, e um separador de caminho
    aí dentro escreveria fora do diretório exclusivo do trabalho — que é a única
    coisa que impede dois renders simultâneos de se contaminarem.
    """
    import re

    limpo = re.sub(r"[^A-Za-z0-9._-]", "-", slot).strip("-.") or "saida"
    return limpo[:96]
