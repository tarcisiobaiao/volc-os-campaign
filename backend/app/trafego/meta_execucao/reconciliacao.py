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

## Identidade vem do LIVRO primeiro, da conta depois

O id que a Meta devolveu ao nosso POST é gravado antes de qualquer outra coisa
— `fechar_passo` acontece antes do read-back, de propósito. Quando ele existe,
ele É a identidade: procedência prova mais que qualquer coincidência de nome.
O manifesto interno (server-only, `service_role`) devolve esse id ao
reconciliador; o recibo do navegador continua dizendo apenas `has_external_id`.

A leitura por NOME continua existindo para o passo que ficou AMBÍGUO, onde id
nenhum chegou a ser gravado. Ela é o caminho fraco, e por isso carrega as três
camadas descritas abaixo. Ela percorre o manifesto inteiro em ordem porque os
ids dos passos anteriores são o que prova o pertencimento dos seguintes.

Isso muda um caso inteiro: um `AdCreative` com id conhecido PODE ser conferido,
porque a conferência não depende do `created_time` que a Marketing API não
expõe. Um `AdCreative` SEM id conhecido continua sem poder ser adotado por
nome, e permanece manual.

## Ter o ID e ter CONFERIDO são fatos diferentes

Um passo pode estar `CREATED`, com id gravado, e nunca ter sido conferido —
porque o processo caiu entre o fechamento e a leitura, ou porque a gravação da
evidência falhou. Antes esse passo era invisível para a recuperação, e a rota
respondia `passos_ambiguos: 0` sobre um objeto que existe na conta e que
ninguém olhou. Zero ambíguos com zero leituras é indistinguível de "está tudo
certo", e não é a mesma coisa.

## Identidade: por que o nome NÃO basta

O nome é o único traço do plano que a Meta devolve numa listagem, então a busca
começa por ele. Mas ele é uma pista fraca, e tratá-lo como conclusão foi um
defeito real desta lane, apontado na revisão adversarial:

> a conta já contém uma campanha PAUSED chamada "Campanha X" com a mesma
> receita; o POST novo falha antes de criar qualquer coisa; a reconciliação
> encontra exatamente a campanha antiga, valida todos os campos dela e fecha o
> passo com o id errado. O AdSet novo passa a nascer sob a campanha da semana
> passada.

A unicidade de nome que o contrato garante vale **dentro do lote**, nunca dentro
da conta. Então a identidade aqui tem três camadas, e as três precisam passar:

1. **nome** — encontra exatamente um candidato na aresta certa da conta certa;
2. **`_validar_read_back` completo** — o mesmo do executor, sem afrouxar nada;
3. **correlação temporal** — o `created_time` do objeto tem de ser posterior ao
   `prepared_at` do recibo. Um objeto que já existia antes de o passo ser
   preparado não pode ter nascido deste despacho.

`AdCreative` não expõe `created_time` na Marketing API. A consequência está
codificada e é deliberada: **um criativo nunca é fechado por leitura**. Ele
permanece ambíguo, porque a leitura não consegue prová-lo — e inventar a prova
seria pior do que não tê-la.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import httpx

from app.trafego.meta.credenciais import SegredoEfemero

from .compilador import OperacaoMeta, PlanoCompiladoMeta, resolver_dependencias
from .executor import (
    CAMPOS_DE_LEITURA,
    ErroRemotoMeta,
    ExecutorMetaPausado,
    _evidencia_do_readback,
)


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
#: O passo JÁ estava CRIADO no livro e a leitura PELO ID confirmou o objeto.
#: Diferente de `CRIADO`: lá a leitura DESCOBRE o id percorrendo a conta; aqui
#: ela confirma um id que já era nosso. O que falta gravar é a EVIDÊNCIA, nunca
#: o id — reescrevê-lo daria à leitura autoridade sobre o que a criação já
#: registrou.
CONFIRMADO = "CONFIRMADO"
#: O objeto existe pelo id registrado e NÃO é o objeto aprovado. Existir não é
#: estar aceito: não autoriza substituir, reenviar nem ativar.
DIVERGENTE = "DIVERGENTE"

#: Folga de relógio entre o nosso `prepared_at` e o `created_time` da Meta. Os
#: dois carimbos vêm de máquinas diferentes; exigir precisão absoluta recusaria
#: objetos legítimos por causa de alguns segundos de deriva.
FOLGA_DE_RELOGIO = timedelta(minutes=5)

#: Tipos cujo `created_time` a Marketing API devolve. `AdCreative` não está
#: aqui e a ausência é o ponto: sem carimbo de nascimento não há como provar
#: que o criativo encontrado nasceu deste despacho, e um criativo antigo com o
#: mesmo nome seria adotado em silêncio.
TIPOS_COM_NASCIMENTO = frozenset({"campaign", "adset", "ad"})


@dataclass(frozen=True)
class ConclusaoDoPasso:
    """O que a leitura conseguiu provar sobre um passo do manifesto."""

    passo: str
    tipo: str
    conclusao: str
    #: Só existe quando a leitura identificou o objeto. Nunca sai numa
    #: resposta HTTP.
    id_externo: str | None = None
    #: Frase de operador dizendo por que a leitura não decidiu. Vocabulário
    #: fechado e sem texto do provedor.
    motivo: str | None = None
    #: Código da divergência, quando `conclusao == DIVERGENTE`. Vocabulário do
    #: executor (`META_READBACK_DIVERGENT`), nunca texto do provedor.
    codigo: str | None = None
    #: A projeção SANITIZADA da leitura — a MESMA que a saga grava. Fica aqui,
    #: e não o corpo cru, para que nenhum id, `page_id` ou `image_hash`
    #: atravesse a fronteira do módulo por descuido: a rota só pode repassar o
    #: que já passou por `_evidencia_do_readback`.
    evidencia: Mapping[str, Any] | None = None


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
        preparados_em: Mapping[str, str] | None = None,
        ids_conhecidos: Mapping[str, str] | None = None,
        confirmados: Sequence[str] = (),
    ) -> tuple[ConclusaoDoPasso, ...]:
        """Conclui, por leitura, o que existe na conta para cada passo do plano.

        Percorre o manifesto inteiro em ordem porque os ids dos passos
        anteriores são o que prova o pertencimento dos seguintes. Só os passos
        em `passos_ambiguos` viram conclusão acionável; os demais servem para
        montar o encadeamento e são devolvidos como contexto.

        `preparados_em` traz o `prepared_at` de cada passo do ledger. É ele que
        separa "este objeto nasceu do nosso despacho" de "a conta já tinha um
        objeto com este nome" — e sem essa separação a reconciliação adota um
        objeto antigo e a saga passa a pendurar filhos nele.

        `ids_conhecidos` traz o `external_object_id` que o livro já gravou, e é
        ele que muda o caminho: com id, a leitura CONFERE; sem id, ela PROCURA.
        `confirmados` diz quais passos já têm read-back confirmado no livro —
        esses não são relidos, só emprestam a identidade aos filhos.
        """
        ambiguos = set(passos_ambiguos)
        carimbos = dict(preparados_em or {})
        conhecidos = {k: v for k, v in dict(ids_conhecidos or {}).items() if v}
        ja_confirmados = set(confirmados)
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
            conhecido = conhecidos.get(operacao.chave, "")
            if conhecido and operacao.chave in ja_confirmados:
                # ⚠️ ID DURÁVEL + read-back JÁ CONFERIDO no livro. Reler não
                # acrescentaria prova nenhuma, e listar a conta para "achar de
                # novo" trocaria um id de procedência por um homônimo. O passo
                # não vira conclusão: ele só empresta a identidade aos filhos.
                ids[operacao.chave] = conhecido
                continue
            if conhecido:
                conclusao, identificado = await self._conferir_por_id(
                    operacao, conhecido, payload=payload, ids=ids,
                    conta_externa=plano.conta_externa, segredo=segredo)
                if identificado:
                    ids[operacao.chave] = conhecido
                conclusoes.append(conclusao)
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
            # ⚠️ NOME IGUAL NÃO PROVA NASCIMENTO.
            #
            # A unicidade de nome é garantida dentro do LOTE, pelo contrato —
            # nunca dentro da conta. Uma campanha antiga, homônima e com a mesma
            # receita passaria por todo o read-back, e fechar o passo com o id
            # dela penduraria o AdSet novo numa campanha de outra semana.
            #
            # O que desempata é o instante: um objeto que já existia antes de o
            # recibo ser preparado não pode ter nascido deste despacho.
            recusa = self._sem_correlacao_temporal(
                operacao.tipo_objeto, dados, carimbos.get(operacao.chave))
            if recusa is not None:
                conclusoes.append(ConclusaoDoPasso(
                    operacao.chave, operacao.tipo_objeto, INDETERMINADO, motivo=recusa))
                continue
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
                operacao.chave, operacao.tipo_objeto, CRIADO,
                id_externo=identificador,
                # ⚠️ A LEITURA DA RECUPERAÇÃO TAMBÉM É EVIDÊNCIA. Sem ela o
                # passo fechava CREATED sem `readback_at` — indistinguível do
                # passo cujo id foi gravado e nunca conferido, que é exatamente
                # o estado do qual a recuperação existe para sair.
                evidencia=_evidencia_do_readback(
                    operacao.tipo_objeto, dados, conferido=True)))
        del ambiguos  # o filtro é da rota; aqui devolvemos o quadro inteiro
        return tuple(conclusoes)

    async def _conferir_por_id(
        self,
        operacao: OperacaoMeta,
        identificador: str,
        *,
        payload: Mapping[str, Any],
        ids: Mapping[str, str],
        conta_externa: str,
        segredo: SegredoEfemero,
    ) -> tuple[ConclusaoDoPasso, bool]:
        """Lê o objeto PELO ID durável e o confronta com o plano aprovado.

        Devolve a conclusão e se o id pode ser emprestado aos filhos como pai.

        ⚠️ Este caminho NÃO pergunta `created_time` a ninguém, e a diferença
        para a busca por nome não é folga. Lá o nome é a única pista e o instante
        é o que separa o nosso objeto de um homônimo; aqui o id veio da resposta
        do NOSSO POST e foi gravado antes de qualquer outra coisa. Procedência
        prova mais que carimbo — e é por isso que um `AdCreative`, que a
        Marketing API não carimba, pode ser conferido por id e continua sem
        poder ser adotado por nome.

        ⚠️ E a conferência é a MESMA do executor, sem afrouxar nada:
        `_validar_read_back` cobre conta, tipo, PAUSED, nome, campos críticos e
        o PAI (`campaign_id`, `adset_id`, `creative.id`) — e o pai vem de `ids`,
        que nesta ordem já foi semeado com o id durável dele.
        """
        try:
            dados = await self._ler_por_id(
                operacao.tipo_objeto, identificador, segredo)
        except _LeituraIncompleta as exc:
            # ⚠️ Não conseguir ler NÃO é o objeto não existir. O passo mantém o
            # id, permanece recuperável e nada é gravado: registrar divergência
            # aqui marcaria como divergente um objeto que ninguém olhou.
            return ConclusaoDoPasso(
                operacao.chave, operacao.tipo_objeto, INDETERMINADO,
                motivo=exc.motivo), False
        try:
            ExecutorMetaPausado._validar_read_back(
                operacao.tipo_objeto, dados,
                payload=payload, identificador=identificador,
                ids=ids, conta_externa=conta_externa)
        except ErroRemotoMeta as exc:
            return ConclusaoDoPasso(
                operacao.chave, operacao.tipo_objeto, DIVERGENTE,
                id_externo=identificador, codigo=exc.codigo,
                evidencia=_evidencia_do_readback(
                    operacao.tipo_objeto, dados, conferido=False),
                motivo=("o objeto existe pelo id registrado e divergiu do plano "
                        f"aprovado ({exc.codigo})"),
            ), False
        return ConclusaoDoPasso(
            operacao.chave, operacao.tipo_objeto, CONFIRMADO,
            id_externo=identificador,
            evidencia=_evidencia_do_readback(
                operacao.tipo_objeto, dados, conferido=True)), True

    async def _ler_por_id(
        self, tipo: str, identificador: str, segredo: SegredoEfemero,
    ) -> Mapping[str, Any]:
        """UM GET no objeto, com a máscara EXATA do read-back da criação.

        ⚠️ `CAMPOS_DE_LEITURA`, a mesma do executor, e não uma reduzida:
        reconciliar com menos campos do que a criação exigiu seria confirmar por
        um critério mais frouxo do que o que teria barrado o objeto ao nascer.
        """
        campos = CAMPOS_DE_LEITURA.get(tipo)
        if campos is None:
            raise _LeituraIncompleta("tipo de objeto Meta desconhecido")
        if not identificador.isdigit() or len(identificador) > 40:
            # ⚠️ O id vem do ledger, que já o restringe a `^[0-9]{1,40}$`. Esta
            # é a segunda conferência, e ela não é decorativa: um id com barra
            # ou `?` viraria OUTRO caminho na Graph, e o cabeçalho Authorization
            # — o token — viajaria junto.
            raise _LeituraIncompleta("o id registrado não tem a forma de um id da Meta")
        try:
            resposta = await self._cliente.get(
                f"{self._base}/{self._versao}/{identificador}",
                params={"fields": campos},
                headers={"Authorization": segredo.cabecalho_bearer()},
            )
        except httpx.HTTPError:
            raise _LeituraIncompleta("a Meta não respondeu à leitura do objeto") from None
        try:
            corpo = resposta.json()
        except (ValueError, TypeError):
            raise _LeituraIncompleta("a Meta devolveu um corpo ilegível") from None
        if (
            resposta.status_code >= 400
            or not isinstance(corpo, Mapping)
            or isinstance(corpo.get("error"), Mapping)
        ):
            # ⚠️ Objeto que não responde não é objeto que não existe: pode ter
            # sido apagado, ou a permissão da conta pode ter mudado. O passo
            # continua CRIADO, com o id gravado.
            raise _LeituraIncompleta("a Meta recusou a leitura deste objeto")
        return corpo

    @staticmethod
    def _sem_correlacao_temporal(
        tipo: str, dados: Mapping[str, Any], preparado_em: str | None,
    ) -> str | None:
        """Devolve o motivo da recusa, ou `None` quando a correlação se sustenta."""
        if tipo not in TIPOS_COM_NASCIMENTO:
            # AdCreative não expõe `created_time`. Sem carimbo não há prova, e
            # sem prova o passo permanece ambíguo — nunca é fechado por leitura.
            return ("a Meta não informa o instante de criação deste tipo de objeto, "
                    "então a leitura não prova que ele nasceu deste despacho")
        nascimento = _instante(dados.get("created_time"))
        if nascimento is None:
            return "o objeto encontrado não trouxe instante de criação"
        preparo = _instante(preparado_em)
        if preparo is None:
            return "o recibo não registrou quando o passo foi preparado"
        if nascimento < preparo - FOLGA_DE_RELOGIO:
            return ("o objeto encontrado já existia antes deste despacho; "
                    "é outro objeto com o mesmo nome")
        return None

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


def _instante(valor: Any) -> datetime | None:
    """Converte um carimbo ISO-8601 num instante com fuso, ou devolve `None`.

    A Meta usa `+0000` sem dois-pontos; o Postgres devolve `+00:00`. Os dois
    precisam virar o mesmo instante, senão a comparação recusaria objetos
    legítimos por causa do formato.
    """
    texto = str(valor or "").strip()
    if not texto:
        return None
    texto = texto.replace("Z", "+00:00")
    if len(texto) >= 5 and texto[-5] in "+-" and texto[-3] != ":":
        texto = f"{texto[:-2]}:{texto[-2:]}"
    try:
        instante = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return instante if instante.tzinfo is not None else instante.replace(tzinfo=timezone.utc)


def _proxima_pagina(corpo: Mapping[str, Any]) -> str | None:
    paginacao = corpo.get("paging")
    if not isinstance(paginacao, Mapping):
        return None
    proxima = paginacao.get("next")
    return str(proxima) if isinstance(proxima, str) and proxima else None
