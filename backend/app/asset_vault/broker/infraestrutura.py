"""O mundo externo do broker: o ambiente injetado e o socket de loopback.

Duas implementacoes, e so duas:

* `SegredoDoAmbiente` — le o Bearer de uma variavel que o `op run` preencheu.
  Ele NAO fala com o 1Password. Quem fala e o `op`, do lado de fora deste
  processo, e a diferenca e a razao de o broker nao precisar de nenhuma
  permissao do cofre: ele recebe uma variavel, confere que ela foi resolvida e
  falha fechado quando nao foi.

* `ClienteLocalApi` — uma chamada HTTP em loopback, com a chave no cabecalho,
  sem redirecionamento e com limite de tempo.

## Por que `follow_redirects=False` nao e detalhe

`httpx` segue redirecionamento por padrao e REPETE os cabecalhos quando o
destino e o mesmo host. Um `302` vindo de um processo local que se passe pela
Local API levaria o `Authorization` junto para onde ele apontasse. Um broker que
segue redirecionamento nao tem allowlist de destino nenhuma — tem a allowlist
que o outro lado quiser.

## Por que a chave nao vai na query string

Query string aparece em log de acesso, em historico e em qualquer proxy no
caminho. Cabecalho tambem pode ser logado, mas nao por padrao — e o cabecalho e
o que a documentacao da Local API define para a API key.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Mapping

import httpx

from app.asset_vault.broker import dominio as dom

log = logging.getLogger("volc.cofre.broker")

#: O nome da variavel que o `op run` preenche. Ele e publico de proposito: o
#: NOME nao e segredo, e escreve-lo aqui evita que cada operador invente o seu.
VARIAVEL_DO_BEARER = "VOLC_ADSPOWER_API_KEY"
#: A referencia `op://` correspondente, quando o operador quiser que o recibo
#: registre QUAL referencia foi usada. So a forma e um digest entram no recibo.
#: Ela vem por ambiente, e nunca por argv, pela mesma razao que o segredo.
VARIAVEL_DA_REFERENCIA = "VOLC_ADSPOWER_REFERENCIA"


class SegredoDoAmbiente:
    """O Bearer que o 1Password injetou neste processo — e mais nada.

    ⚠️ Trancar o 1Password interrompe o acesso, e a interrupcao acontece AQUI:
    com o cofre trancado, `op run` nao resolve e a variavel chega ausente ou com
    a referencia literal. `dominio.exigir_bearer` distingue os dois casos e
    devolve `blocked/segredo_ausente` ou `blocked/segredo_nao_resolvido` — nunca
    um modo degradado.
    """

    def __init__(self, ambiente: Mapping[str, str] | None = None,
                 nome_da_variavel: str = VARIAVEL_DO_BEARER,
                 nome_da_referencia: str = VARIAVEL_DA_REFERENCIA):
        self._ambiente = ambiente if ambiente is not None else os.environ
        self._nome = nome_da_variavel
        self._nome_referencia = nome_da_referencia

    @property
    def nome_da_variavel(self) -> str:
        return self._nome

    @property
    def origem(self) -> str:
        return "ambiente_injetado_por_op_run"

    def bearer(self) -> dom.Segredo:
        return dom.exigir_bearer(self._ambiente.get(self._nome),
                                 nome_da_variavel=self._nome)

    def referencia_declarada(self) -> str | None:
        bruto = (self._ambiente.get(self._nome_referencia) or "").strip()
        return bruto or None


class ClienteLocalApi:
    """Uma pergunta em loopback, autenticada, limitada no tempo e no ritmo."""

    def __init__(self, endereco: str, *, intervalo_minimo_s: float = dom.INTERVALO_MINIMO_S,
                 relogio=time.monotonic, dormir=asyncio.sleep):
        self._endereco = dom.exigir_endereco_de_loopback(endereco)
        self._intervalo = float(intervalo_minimo_s)
        self._relogio = relogio
        self._dormir = dormir
        self._ultima: float | None = None

    async def _respeitar_ritmo(self) -> None:
        """A Local API documenta ~1 chamada/segundo.

        Estourar o limite devolve um erro que o broker leria como "AdsPower fora
        do ar" — e um diagnostico errado custa mais do que a espera.

        ⚠️ A espera e `asyncio.sleep`, e nao `time.sleep`: dentro de uma corotina
        um `time.sleep` para o loop inteiro, e o "limite de ritmo" de uma chamada
        vira congelamento de todas as outras.
        """
        if self._ultima is None or self._intervalo <= 0:
            self._ultima = self._relogio()
            return
        falta = self._intervalo - (self._relogio() - self._ultima)
        if falta > 0:
            await self._dormir(falta)
        self._ultima = self._relogio()

    async def chamar(self, acao: dom.Acao, parametros: Mapping[str, str],
                     bearer: dom.Segredo, timeout_s: float) -> Any:
        if acao.muta:
            # Cinto e suspensorio: o catalogo ja nao publica acao mutante, e
            # mesmo assim o transporte recusa. A camada que abre o socket e a
            # ultima que pode dizer nao.
            raise dom.BrokerRecusado(
                f"o transporte recusa a acao {acao.nome}: ela muta, e esta versao do "
                "broker so pergunta.",
                estado="blocked/exige_checkpoint")
        await self._respeitar_ritmo()
        cabecalhos = {
            # `.revelar()` acontece EXATAMENTE aqui, e em nenhum outro lugar do
            # broker. Procure por `.revelar(` para auditar.
            "Authorization": f"Bearer {bearer.revelar()}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._endereco,
                timeout=timeout_s,
                follow_redirects=False,
                trust_env=False,  # nenhum HTTP_PROXY do ambiente entra no caminho
            ) as cliente:
                resposta = await cliente.request(
                    acao.metodo, acao.caminho, params=dict(parametros), headers=cabecalhos)
        except httpx.TimeoutException as exc:
            raise dom.AcessoIndisponivel(
                f"a Local API nao respondeu em {timeout_s:g}s.",
                estado="falha/tempo_esgotado") from exc
        except httpx.HTTPError as exc:
            # Nao repassa `str(exc)`: a mensagem do httpx carrega a URL, e a URL
            # carrega os parametros. Etiqueta por classe, e o detalhe no log.
            log.warning("broker: falha de transporte em %s (%s)", acao.nome, type(exc).__name__)
            raise dom.AcessoIndisponivel(
                "nao foi possivel falar com a Local API do AdsPower nesta maquina. "
                "O cliente esta aberto e a Local API ligada?",
                estado="blocked/local_api_ausente") from exc

        if resposta.is_redirect:
            raise dom.AcessoIndisponivel(
                "a Local API respondeu com redirecionamento, e o broker nao segue "
                "redirecionamento: seguir levaria o cabecalho de autorizacao junto.",
                estado="falha/resposta_ilegivel")
        if resposta.status_code in (401, 403):
            raise dom.AcessoIndisponivel(
                "a Local API recusou a chave. Ela pode ter sido rotacionada no cliente "
                "AdsPower, ou o `op run` injetou a referencia de outro item.",
                estado="blocked/segredo_nao_resolvido")
        if resposta.status_code >= 400:
            raise dom.AcessoIndisponivel(
                f"a Local API respondeu HTTP {resposta.status_code} para {acao.nome}.",
                estado="blocked/local_api_ausente")
        try:
            return resposta.json()
        except ValueError as exc:
            raise dom.AcessoIndisponivel(
                "a Local API respondeu algo que nao e JSON.",
                estado="falha/resposta_ilegivel") from exc
