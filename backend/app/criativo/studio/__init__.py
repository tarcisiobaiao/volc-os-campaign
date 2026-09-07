"""Fachada do Estúdio para o Assistente Criativo Meta.

A estratégia é decidida em `app.criativo.agente`; a mídia é produzida e guardada
pelo parque em `app.criativo.execucao` e `app.criativo.bancada`. Este pacote é a
ponte entre os dois, e não é dono de nenhum dos lados.

⚠️ Este `__init__` exporta SÓ o contrato, que é pydantic puro. `adaptador.py`
importa `app.criativo.dominio`, que por sua vez importa `volc_ads` — um pacote
que mora fora de `backend/` e que um ambiente mínimo pode não ter no path.
Reexportá-lo aqui faria `from app.criativo.studio import PedidoDeGeracao`
arrastar essa dependência para quem só queria um modelo de request, e foi
exatamente assim que um teste hermético do agente parou de coletar sozinho.
Quem precisa do adaptador importa `app.criativo.studio.adaptador` direto,
de dentro da função, como `obter_motor` já faz em `routers/criativos.py`.
"""

from .contrato import (
    MAX_RENDERS_POR_PEDIDO,
    Bloqueio,
    BriefingDeImagem,
    Linhagem,
    PedidoDeGeracao,
    PlanoDeGeracao,
)

__all__ = [
    "MAX_RENDERS_POR_PEDIDO",
    "Bloqueio",
    "BriefingDeImagem",
    "Linhagem",
    "PedidoDeGeracao",
    "PlanoDeGeracao",
]
