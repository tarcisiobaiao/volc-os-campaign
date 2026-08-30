"""O quarto portão: prova de emissão, para o que uma tag de mídia consegue pedir.

## Por que existe um quarto portão, e por que ele não afrouxa os outros três

`exigir_usuario`, `exigir_admin` e `exigir_servico` cobrem tudo que o navegador
busca por `fetch`, onde dá para mandar `Authorization`. Eles NÃO cobrem
`<img src>` e `<video src>`: essas tags não mandam header nenhum, e nunca vão
mandar.

A saída barata para esse problema é tornar o arquivo público, e é assim que um
bucket privado vira um bucket aberto. A segunda saída barata é pendurar o token
de sessão na query string, e aí uma credencial que vale para a API inteira entra
em log de proxy, em histórico de navegador e em qualquer print de tela.

Este portão é a terceira saída. Ele exige uma prova que **o próprio servidor
emitiu**, com HMAC, escopada a UMA chave de storage e válida por minutos. Um
token vazado não abre outra chave, não abre a API e não sobrevive ao almoço.

## O que ele NÃO é, e isso precisa ficar dito

Ele não é autorização de negócio e não sabe quem é o operador. O que decide se
alguém pode ver um ativo é o endpoint que EMITE o link, e esse endpoint exige
`exigir_usuario`. Confundir os dois faria a assinatura virar uma porta de
entrada permanente; por isso o TTL é curto e o escopo é uma chave só.

É por essa distinção que ele conta como portão em
`tests/test_seguranca_hub.py::GUARDAS`: a rota de arquivo não está sem guarda,
ela está com uma guarda de outra espécie, declarada e auditável. Uma rota que
conferisse o token no corpo da função passaria no teste sem nada declarado, e
isso sim seria o defeito.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Path

from app.criativo.armazenamento import (
    ArquivoRecusado,
    Assinador,
    TokenInvalido,
    segredo_de_assinatura,
)

log = logging.getLogger("volc.seguranca.link")


def _assinador() -> Assinador:
    try:
        return Assinador(segredo_de_assinatura())
    except (RuntimeError, ValueError) as e:
        # Falha FECHADA, como `_config_ou_503` de `identidade.py`: sem material
        # para conferir assinatura, nenhuma requisição é aceita.
        log.error("assinatura de link indisponível: %s", e)
        raise HTTPException(
            status_code=503,
            detail={
                "codigo": "ESTUDIO.sem_configuracao",
                "mensagem": "O servidor está sem chave de assinatura de link.",
            },
        ) from e


async def exigir_link_assinado(
    token: str = Path(...),
    assinador: Assinador = Depends(_assinador),
) -> str:
    """Devolve a chave de storage autorizada, ou 403.

    403 e não 401 de propósito: 401 diz "entre de novo", e não há login que
    conserte um link expirado. 403 com a mensagem certa manda o operador
    recarregar a página, que é o que de fato resolve.
    """
    try:
        return assinador.conferir(token)
    except (TokenInvalido, ArquivoRecusado) as e:
        raise HTTPException(
            status_code=403,
            detail={
                "codigo": "ESTUDIO.link_invalido",
                "mensagem": "Este link expirou ou não é válido. Recarregue a página.",
            },
        ) from e
