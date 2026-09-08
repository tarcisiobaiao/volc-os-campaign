"""O selo que amarra a autorização de gasto ao plano exato que foi lido.

## O buraco que este módulo fecha

A autorização de gasto tinha três campos — modelo, total de renders e teto — e
o servidor reconferia os três. Isso impede autorizar 2 imagens e produzir 9,
mas **não** impede autorizar 2 imagens de um conjunto e produzir 2 imagens de
outro conjunto:

    o operador lê o plano  {peça A, peça B} × {1x1}  = 2 renders, modelo X
    um POST manda          {peça C, peça D} × {1x1}  = 2 renders, modelo X

Modelo igual, total igual: as três conferências passam, e o lote que roda não é
o lote que a pessoa leu. A recusa por conteúdo não existia porque nenhum dos três
campos descreve QUAL conteúdo.

## Duas peças, e cada uma responde uma pergunta diferente

`assinatura_do_plano` responde **"é o mesmo plano?"**. É um sha256 do conteúdo
canônico do plano — as refs selecionadas, os formatos, o modelo, a qualidade, o
total, a estimativa e o hash do anexo. O servidor recalcula o plano no mesmo
POST e recalcula a assinatura; divergiu, recusa.

`emitir_selo`/`conferir_selo` respondem **"ainda vale?"**. A assinatura sozinha
não expira: uma aba aberta há seis horas continua com o hash certo, porque o
plano dela continua sendo aquele plano. O selo é um HMAC do par
`(assinatura, instante de expiração)` emitido pelo servidor; o cliente devolve o
selo inteiro e não consegue esticar o prazo, porque esticar muda o corpo e
invalida o MAC.

⚠️ Um `expira_em` viajando como campo comum, sem MAC, seria decoração: o cliente
manda o timestamp que quiser. É por isso que aqui existe um segredo.

## Por que um assinador próprio, e não `armazenamento.Assinador`

Aquele assina CHAVE DE ARQUIVO e chama `conferir_chave` nas duas pontas, que
exige o formato `criativos/...`. Uma assinatura de plano não é uma chave de
arquivo, e reusar a classe obrigaria a inventar uma chave falsa para satisfazer
uma validação que não tem nada a ver com o assunto. O segredo é o mesmo; o
vocabulário, não.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Iterable

#: Quanto tempo um plano conferido continua autorizável.
#:
#: Dez minutos é o intervalo entre ler um plano e clicar em gerar, com folga
#: para reler. Não é um controle de segurança contra quem tem sessão válida —
#: essa pessoa pode pedir um plano novo a qualquer momento. É proteção contra a
#: aba esquecida aberta: o preço, o catálogo de formatos e o próprio motor podem
#: ter mudado desde que aquele número foi desenhado na tela.
TTL_PADRAO_S = 600


class SeloInvalido(ValueError):
    """Selo ausente, malformado, com MAC errado ou vencido."""


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).decode("ascii").rstrip("=")


def _deb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def assinatura_do_plano(
    *,
    run_ref: str,
    creative_refs: Iterable[str],
    format_ids: Iterable[str],
    modelo: str | None,
    qualidade: str | None,
    total_de_renders: int,
    custo_estimado_usd: float | None,
    anexo_sha256: str | None,
    modo_de_composicao: str | None,
) -> str:
    """O sha256 do conteúdo do plano. Mesmo plano, mesma assinatura.

    As listas entram ORDENADAS porque escolher `[A, B]` e `[B, A]` é a mesma
    escolha, e uma assinatura sensível à ordem transformaria um reordenamento de
    checkbox em "o plano mudou" — a recusa mais confusa que esta tela poderia
    dar.

    `custo_estimado_usd` entra porque o preço é parte do que a pessoa leu: se o
    motor passar a publicar (ou deixar de publicar) preço entre o plano e o
    clique, o consentimento não cobre mais o mesmo fato.

    `anexo_sha256` entra porque trocar a fotografia depois de conferir o plano
    muda a peça inteira, e essa troca não mexe em nenhum dos outros campos.
    """
    material: dict[str, Any] = {
        "v": 1,
        "run_ref": run_ref,
        "creative_refs": sorted(set(creative_refs)),
        "format_ids": sorted(set(format_ids)),
        "modelo": modelo or "",
        "qualidade": qualidade or "",
        "total_de_renders": int(total_de_renders),
        # `repr` de float varia entre plataformas; a string com 6 casas é a mesma
        # precisão que `PlanoDeGeracao` já arredonda.
        "custo_estimado_usd": (
            None if custo_estimado_usd is None else f"{float(custo_estimado_usd):.6f}"
        ),
        "anexo_sha256": anexo_sha256 or "",
        "modo_de_composicao": modo_de_composicao or "",
    }
    cru = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(cru.encode("utf-8")).hexdigest()


def _mac(segredo: bytes, alvo: bytes) -> bytes:
    return hmac.new(segredo, alvo, hashlib.sha256).digest()


def emitir_selo(assinatura: str, *, segredo: str, ttl_s: int = TTL_PADRAO_S) -> str:
    """O selo que o cliente devolve junto com a autorização."""
    if not segredo or len(segredo) < 16:
        raise ValueError("segredo de assinatura ausente ou curto demais")
    corpo = json.dumps(
        {"a": assinatura, "e": int(time.time()) + max(1, ttl_s)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    alvo = _b64(corpo)
    return f"{alvo}.{_b64(_mac(segredo.encode('utf-8'), alvo.encode()))}"


def conferir_selo(token: str, *, segredo: str) -> str:
    """Devolve a assinatura selada, ou levanta. Nunca devolve algo não conferido."""
    if not segredo or len(segredo) < 16:
        raise ValueError("segredo de assinatura ausente ou curto demais")
    try:
        alvo, assinatura_do_mac = token.split(".", 1)
    except (ValueError, AttributeError):
        raise SeloInvalido("selo malformado") from None

    # `compare_digest` e não `==`: comparação curto-circuitada vaza, pelo tempo,
    # quantos bytes iniciais bateram, e isso basta para forjar um MAC byte a byte.
    if not hmac.compare_digest(
        _b64(_mac(segredo.encode("utf-8"), alvo.encode())), assinatura_do_mac
    ):
        raise SeloInvalido("selo com assinatura inválida")

    try:
        dados: dict[str, Any] = json.loads(_deb64(alvo))
    except (ValueError, json.JSONDecodeError):
        raise SeloInvalido("selo malformado") from None

    # Comparação em ponto flutuante e não `int() < int()`: truncar os dois lados
    # cria uma janela de até um segundo em que um selo vencido ainda passa, e um
    # teste de expiração intermitente é pior que nenhum.
    if float(dados.get("e", 0)) < time.time():
        raise SeloInvalido("selo expirado")

    valor = str(dados.get("a", ""))
    if len(valor) != 64:
        raise SeloInvalido("selo sem assinatura de plano")
    return valor
