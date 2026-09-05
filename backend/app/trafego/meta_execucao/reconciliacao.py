"""Reconciliação por LEITURA de uma saga Meta que ficou ambígua.

## O problema que este módulo resolve

Depois que a saga despacha um `POST` e o transporte cai, ninguém sabe se o
objeto nasceu. `executor.criar_pausada` marca o passo AMBIGUO, recusa retentar
e para o lote — o que é a decisão certa e, sozinha, um beco sem saída: o
recibo fica aberto para sempre e o operador não tem como saber se existe uma
campanha órfã na conta.

`REMAINING-RISKS.md` da lane anterior registrou isto como o risco 3, com a
frase "no dia em que `create_paused` for autorizado, é a primeira coisa a
construir". Este é esse módulo.

## O que ele pode e o que ele nunca faz

Ele **só lê**. Nenhum método aqui emite `POST`, `DELETE` ou qualquer mutação na
Meta. A única escrita que a reconciliação produz acontece no ledger, pela rota
que consome este resultado, e apenas em duas direções nomeadas:

    encontrado e conferido  → o passo AMBIGUO fecha como CRIADO
    ausência PROVADA        → o passo AMBIGUO fecha como FALHO

Qualquer outra coisa — listagem que não terminou, dois objetos com o mesmo
nome, read-back divergente, erro de leitura — devolve `INDETERMINADO`, e o
passo **permanece AMBIGUO**. Não conseguir provar a ausência não é o mesmo que
provar a ausência, e tratar os dois casos igual é exatamente o caminho para
reenviar um pedido que já criou uma campanha.

## Por que ele relê a saga inteira, e não só o passo ambíguo

O ledger, de propósito, nunca devolve `external_object_id` (o recibo diz apenas
`has_external_id`). Então a reconciliação não tem os ids dos passos anteriores
— e sem eles não daria para conferir `campaign_id` do conjunto nem `adset_id`
do anúncio, que é justamente o que prova pertencimento.

A saída é reconstruir o estado a partir da CONTA: percorrer o manifesto em
ordem, achar cada objeto pelo nome aprovado, e usar o id encontrado como pai do
passo seguinte. É mais leitura, e é a única forma de o read-back da
reconciliação ser tão exigente quanto o read-back da criação.

## Identidade: por que o nome basta aqui

O nome do objeto entra no `plano_sha256` (ele é parte do payload compilado), é
único dentro do lote por contrato (`META_STATIC_BATCH_DUPLICATE_NAME`) e é o
único traço do plano que a Meta devolve numa listagem. Encontrar **exatamente
um** objeto com aquele nome na conta certa é uma pista, não a conclusão: a
conclusão vem do `_validar_read_back` completo, o mesmo que a saga usa.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import httpx

from app.trafego.meta.credenciais import SegredoEfemero

from .compilador import PlanoCompiladoMeta, resolver_dependencias
from .executor import CAMPOS_DE_LEITURA, ErroRemotoMeta, ExecutorMetaPausado


#: Quantas páginas a leitura percorre antes de desistir. Um teto é obrigatório:
#: sem ele uma conta grande faria a rota rodar indefinidamente. Bater no teto
#: NÃO vira "não encontrei" — vira `INDETERMINADO`, porque a parte não lida da
#: conta poderia conter o objeto.
MAXIMO_DE_PAGINAS = 25

#: Tamanho de página pedido à Graph. Alto de propósito: menos páginas significa
#: menos chances de bater no teto acima e perder a prova de ausência.
TAMANHO_DA_PAGINA = 200

CRIADO = "CRIADO"
AUSENTE = "AUSENTE"
INDETERMINADO = "INDETERMINADO"


@dataclass(frozen=True)
class ConclusaoDoPasso:
    """O que a leitura conseguiu provar sobre um passo do manifesto."""

    passo: str
    tipo: str
    conclusao: str
    #: Só existe quando `conclusao == CRIADO`. Nunca sai numa resposta HTTP.
    id_externo: str | None = None
    #: Frase de operador dizendo por que a leitura não decidiu. Vocabulário
    #: fechado e sem texto do provedor.
    motivo: str | None = None


class ReconciliadorMetaSomenteLeitura:
    """Percorre o plano aprovado contra a conta real, sem escrever nada nela."""

    def __init__(
        self,
        cliente: httpx.AsyncClient,
        *,
        api_version: str = "v26.0",
        base_url: str = "https://graph.facebook.com",
    ) -> None:
        partes = urlparse(base_url)
        if partes.scheme != "https" or partes.hostname != "graph.facebook.com":
            raise ValueError("base Meta precisa ser https://graph.facebook.com")
        if api_version != "v26.0":
            raise ValueError("a reconciliacao P0 esta fixada em v26.0")
        self._cliente = cliente
        self._base = base_url.rstrip("/")
        self._versao = api_version

    async def conciliar(
        self,
        plano: PlanoCompiladoMeta,
        segredo: SegredoEfemero,
        *,
        passos_ambiguos: Sequence[str],
    ) -> tuple[ConclusaoDoPasso, ...]:
        """Conclui, por leitura, o que existe na conta para cada passo do plano.

        Percorre o manifesto inteiro em ordem porque os ids dos passos
        anteriores são o que prova o pertencimento dos seguintes. Só os passos
        em `passos_ambiguos` viram conclusão acionável; os demais servem para
        montar o encadeamento e são devolvidos como contexto.
        """
        ambiguos = set(passos_ambiguos)
        ids: dict[str, str] = {}
        conclusoes: list[ConclusaoDoPasso] = []
        for operacao in plano.operacoes:
            nome_aprovado = str(operacao.payload.get("name") or "")
            try:
                # ⚠️ A resolução de dependências pode faltar um pai que a leitura
                # não achou. Nesse caso o passo não é decidível: sem o id do pai
                # não há como conferir pertencimento.
                payload = resolver_dependencias(operacao.payload, ids)
            except KeyError:
                conclusoes.append(ConclusaoDoPasso(
                    operacao.chave, operacao.tipo_objeto, INDETERMINADO,
                    motivo="o objeto pai não foi localizado na conta",
                ))
                continue
            try:
                encontrados = await self._listar_por_nome(
                    operacao.endpoint, operacao.tipo_objeto, nome_aprovado, segredo)
            except _LeituraIncompleta as exc:
                conclusoes.append(ConclusaoDoPasso(
                    operacao.chave, operacao.tipo_objeto, INDETERMINADO,
                    motivo=exc.motivo,
                ))
                continue
            if len(encontrados) > 1:
                # Dois objetos com o mesmo nome aprovado é ambiguidade REAL na
                # conta. Escolher um seria inventar o recibo.
                conclusoes.append(ConclusaoDoPasso(
                    operacao.chave, operacao.tipo_objeto, INDETERMINADO,
                    motivo="a conta tem mais de um objeto com este nome",
                ))
                continue
            if not encontrados:
                conclusoes.append(ConclusaoDoPasso(
                    operacao.chave, operacao.tipo_objeto, AUSENTE,
                    motivo="a listagem completa da conta não tem este objeto",
                ))
                continue
            dados = encontrados[0]
            identificador = str(dados.get("id") or "")
            try:
                ExecutorMetaPausado._validar_read_back(
                    operacao.tipo_objeto,
                    dados,
                    payload=payload,
                    identificador=identificador,
                    ids=ids,
                    conta_externa=plano.conta_externa,
                )
            except ErroRemotoMeta as exc:
                # Achou um objeto com o nome certo que NÃO é o objeto aprovado.
                # Isso não fecha nada: nem prova que o nosso nasceu, nem que não.
                conclusoes.append(ConclusaoDoPasso(
                    operacao.chave, operacao.tipo_objeto, INDETERMINADO,
                    motivo=f"o objeto encontrado divergiu do plano aprovado ({exc.codigo})",
                ))
                continue
            ids[operacao.chave] = identificador
            conclusoes.append(ConclusaoDoPasso(
                operacao.chave, operacao.tipo_objeto, CRIADO, id_externo=identificador))
        del ambiguos  # o filtro é da rota; aqui devolvemos o quadro inteiro
        return tuple(conclusoes)

    async def _listar_por_nome(
        self,
        endpoint: str,
        tipo: str,
        nome: str,
        segredo: SegredoEfemero,
    ) -> list[Mapping[str, Any]]:
        """Lista a aresta da conta e devolve os objetos com o nome exato.

        Levanta `_LeituraIncompleta` quando a listagem não pôde ser esgotada —
        e é essa distinção que separa "não existe" de "não consegui olhar".
        """
        campos = CAMPOS_DE_LEITURA.get(tipo)
        if campos is None:
            raise _LeituraIncompleta("tipo de objeto Meta desconhecido")
        url = f"{self._base}/{self._versao}{endpoint}"
        parametros: dict[str, Any] | None = {"fields": campos, "limit": TAMANHO_DA_PAGINA}
        achados: list[Mapping[str, Any]] = []
        for _ in range(MAXIMO_DE_PAGINAS):
            try:
                resposta = await self._cliente.get(
                    url,
                    params=parametros,
                    headers={"Authorization": segredo.cabecalho_bearer()},
                )
            except httpx.HTTPError:
                raise _LeituraIncompleta("a Meta não respondeu à leitura da conta") from None
            try:
                corpo = resposta.json()
            except (ValueError, TypeError):
                raise _LeituraIncompleta("a Meta devolveu um corpo ilegível") from None
            if (
                resposta.status_code >= 400
                or not isinstance(corpo, Mapping)
                or isinstance(corpo.get("error"), Mapping)
            ):
                raise _LeituraIncompleta("a Meta recusou a leitura da conta")
            dados = corpo.get("data")
            if not isinstance(dados, (list, tuple)):
                raise _LeituraIncompleta("a listagem da conta veio sem dados")
            for item in dados:
                if isinstance(item, Mapping) and str(item.get("name") or "") == nome:
                    achados.append(item)
            proxima = _proxima_pagina(corpo)
            if proxima is None:
                return achados
            # ⚠️ A URL de paginação vem da Meta. Ela é seguida SÓ se continuar
            # apontando para a Graph: um `next` para outro host levaria o
            # cabeçalho Authorization — o token — para fora da Meta.
            partes = urlparse(proxima)
            if partes.scheme != "https" or partes.hostname != "graph.facebook.com":
                raise _LeituraIncompleta("a paginação apontou para fora da Meta")
            url, parametros = proxima, None
        raise _LeituraIncompleta("a conta tem mais páginas do que esta leitura percorre")


class _LeituraIncompleta(RuntimeError):
    """A conta não pôde ser lida até o fim: nada aqui prova ausência."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


def _proxima_pagina(corpo: Mapping[str, Any]) -> str | None:
    paginacao = corpo.get("paging")
    if not isinstance(paginacao, Mapping):
        return None
    proxima = paginacao.get("next")
    return str(proxima) if isinstance(proxima, str) and proxima else None
