"""O Assistente falando com a PRENSA envelopada.

## Onde este adaptador se encaixa

O parque de motores deste produto já tem a forma certa: `bancada/porta.py`
define o contrato, `adaptadores/` implementa. Este é mais um adaptador, e não um
caminho paralelo — a PRENSA entra pela mesma porta que o `gpt-image-2` entra, e
o operador escolhe por `modo_de_producao`, que já existe no banco com
`typography_only` e `deterministic_graphics` apontando para o renderer `prensa`.

## Por que HTTP e não import

Porque a PRENSA precisa de um Chrome real para medir tipografia no DOM antes do
screenshot, e o backend deste produto roda serverless. Envelopar em container e
falar HTTP é o que torna as duas coisas verdadeiras ao mesmo tempo. Ver
`services/prensa/README.md`.

## Falha fechada, e o motivo viaja

A escada de gates da PRENSA é fail-closed: reprovou, nenhum PNG é escrito, e o
serviço devolve 422 com o motivo nomeado. Traduzir isso para uma exceção genérica
apagaria justamente a informação que faz o gate valer alguma coisa — então o
motivo do motor chega inteiro em `FalhaDaPrensa.motivo`.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

#: Onde a PRENSA atende. Sem variável configurada o adaptador não inventa um
#: padrão de produção: falha ao ser construído, que é como o resto do parque
#: trata credencial e endereço ausentes.
VARIAVEL_DE_ENDERECO = "PRENSA_URL"
TIMEOUT_SEGUNDOS = 180


class PrensaIndisponivel(RuntimeError):
    """O serviço não está configurado ou não respondeu."""


@dataclass(frozen=True)
class FalhaDaPrensa(RuntimeError):
    """O motor rodou e RECUSOU. Não é erro de transporte — é veredito."""

    codigo: str
    motivo: str


@dataclass(frozen=True)
class PecaImpressa:
    """Um PNG e as duas provas que a PRENSA emite junto com ele."""

    nome: str
    conteudo: bytes
    veredito: dict | None
    pixelgate: dict | None


def endereco() -> str:
    valor = (os.environ.get(VARIAVEL_DE_ENDERECO) or "").strip().rstrip("/")
    if not valor:
        raise PrensaIndisponivel(
            f"{VARIAVEL_DE_ENDERECO} não configurada; suba o serviço com "
            "`docker compose up -d` em services/prensa e aponte a variável para ele"
        )
    return valor


def saude() -> dict:
    """Confere que o serviço sobe E que o navegador existe dentro dele."""
    try:
        with urllib.request.urlopen(f"{endereco()}/saude", timeout=15) as resposta:
            return json.loads(resposta.read())
    except urllib.error.URLError as erro:
        raise PrensaIndisponivel(f"a PRENSA não respondeu: {erro}") from erro


def imprimir(spec: dict, sufixo: str = "") -> list[PecaImpressa]:
    """Manda a spec resolvida e devolve os artefatos com seus recibos."""
    corpo = json.dumps({"spec": spec, "sufixo": sufixo}).encode("utf-8")
    requisicao = urllib.request.Request(
        f"{endereco()}/render", data=corpo,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT_SEGUNDOS) as resposta:
            dados = json.loads(resposta.read())
    except urllib.error.HTTPError as erro:
        # 422 é a PRENSA recusando com motivo; qualquer outra coisa é transporte.
        detalhe = erro.read().decode("utf-8", "replace")[:4000]
        if erro.code == 422:
            try:
                nomeado = json.loads(detalhe).get("detail", {})
            except json.JSONDecodeError:
                nomeado = {}
            raise FalhaDaPrensa(
                codigo=str(nomeado.get("codigo") or "PRENSA_RECUSOU"),
                motivo=str(nomeado.get("erro") or nomeado.get("saida") or detalhe),
            ) from erro
        raise PrensaIndisponivel(f"a PRENSA respondeu HTTP {erro.code}: {detalhe}") from erro
    except urllib.error.URLError as erro:
        raise PrensaIndisponivel(f"a PRENSA não respondeu: {erro}") from erro

    return [
        PecaImpressa(
            nome=artefato["nome"],
            conteudo=base64.b64decode(artefato["png_base64"]),
            veredito=artefato.get("veredito"),
            pixelgate=artefato.get("pixelgate"),
        )
        for artefato in dados.get("artefatos", [])
    ]
