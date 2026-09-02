"""As regras da publicacao organica que nao dependem de banco nem de rede.

## O vocabulario mora aqui E no banco, e um teste compara os dois

`ESTADOS`, `MODOS` e `ESTADOS_EXTERNOS` sao a mesma lista que a v14_01 declara
em CHECK. Quando as duas divergem, o sintoma em producao e um 400 que ninguem
entende — o Python aceita, o banco recusa, e a mensagem fala de constraint. Por
isso `backend/tests/test_publicacao_organica_dominio.py` LE a migration e
compara literalmente, como `test_cofre_ativos.py` ja faz para o Cofre.

## Por que a chave de idempotencia e derivada, e nunca sorteada

Publicar duas vezes nao custa so dinheiro: custa alcance e credibilidade, e nao
tem "desfazer" que devolva quem ja viu. Uma chave sorteada faz TODO reenvio
parecer pedido novo. A chave daqui e o sha256 de
`(peca_id, peca_versao, destino_id, modo, instante_alvo, corpo)` — se o operador
nao mudou nada, a segunda submissao produz a MESMA chave e o banco devolve o
recibo que ja existe. Se ele mudou o texto, a chave muda, e o job novo e outra
coisa — que e a verdade.

## Por que o horario local vira instante NO BANCO, e nao aqui

`zoneinfo` daria a resposta certa neste processo. O problema e que o banco
tambem precisa saber, e duas implementacoes da mesma conversao divergem no dia
em que uma delas roda numa maquina com tzdata velho. A funcao governada
`publicacao_organica_criar_job` converte com `AT TIME ZONE`, e este modulo so
VALIDA a forma antes de gastar uma ida ao banco. Uma validacao local que
recusasse mais do que o banco esconderia casos legitimos; uma que recusasse
menos so adiantaria o erro. Esta recusa menos, de proposito.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# ---------------------------------------------------------------------------
# Vocabulario — espelho do CHECK da v14_01
# ---------------------------------------------------------------------------

#: Estados do job, na ordem em que a operacao os encontra.
ESTADOS: Final[tuple[str, ...]] = (
    "rascunho",
    "pronto",
    "em_voo",
    "rascunho_externo",
    "agendado",
    "publicacao_solicitada",
    "publicado",
    "reconciliado",
    "falha",
    "indeterminado",
    "cancelado",
)

#: Estados em que NADA saiu daqui. A tela pode oferecer cancelamento simples.
ESTADOS_ANTES_DO_EXTERNO: Final[frozenset[str]] = frozenset({"rascunho", "pronto"})

#: Estados que NAO sao sucesso e NAO sao falha. A tela nunca os pinta de verde.
ESTADOS_INCERTOS: Final[frozenset[str]] = frozenset(
    {"em_voo", "publicacao_solicitada", "indeterminado"}
)

#: Estados terminais: nada mais acontece sem um job novo.
ESTADOS_TERMINAIS: Final[frozenset[str]] = frozenset({"reconciliado", "cancelado"})

MODOS: Final[tuple[str, ...]] = ("draft", "schedule", "now")

#: Vocabulario de estado do control plane. `DESCONHECIDO` e nosso, e existe para
#: que uma resposta que nao encaixa vire um valor honesto em vez de virar
#: `ERROR` (que seria acusar o provedor) ou `PUBLISHED` (que seria mentir).
ESTADOS_EXTERNOS: Final[tuple[str, ...]] = (
    "DRAFT",
    "QUEUE",
    "PUBLISHED",
    "ERROR",
    "DESCONHECIDO",
)

PLATAFORMAS: Final[tuple[str, ...]] = (
    "facebook",
    "instagram",
    "youtube",
    "tiktok",
    "linkedin",
    "x",
    "threads",
    "pinterest",
)

PROVEDORES: Final[tuple[str, ...]] = ("postiz", "multipost")

#: Gramatica da chave de idempotencia, identica a CHECK do banco.
_FORMA_DA_CHAVE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")

#: Forma de nome IANA, identica a `publicacao_organica_forma_de_timezone`.
_FORMA_DE_TIMEZONE = re.compile(
    r"^[A-Za-z][A-Za-z0-9+_-]{1,31}(/[A-Za-z0-9+_.-]{1,31}){0,2}$"
)

#: Horario local declarado: `YYYY-MM-DD HH:MM` ou `YYYY-MM-DDTHH:MM`, com
#: segundos opcionais. Sem offset — offset aqui seria um segundo timezone
#: competindo com o campo `timezone`, e duas fontes para a mesma resposta e como
#: o horario errado entra sem ninguem notar.
_FORMA_DE_HORARIO = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$"
)


class PedidoRecusado(ValueError):
    """Entrada que o dominio recusa ANTES de gastar uma ida ao banco."""

    def __init__(self, mensagem: str, *, codigo: str = "pedido_invalido") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


# ---------------------------------------------------------------------------
# Sanitizacao de erro externo
# ---------------------------------------------------------------------------
# ⚠️ ESTA FUNCAO E O UNICO CAMINHO DE UM ERRO DO CONTROL PLANE PARA UMA LINHA.
# O corpo de um 4xx costuma ecoar o request — inclusive o header Authorization
# quando o gateway do meio resolve ser prestativo. A CHECK `prosa_limpa` da
# v14_01 e a ultima peneira; esta e a primeira, e ela existe porque uma linha
# recusada pelo banco vira 500 na tela, e um 500 nao diz ao operador o que
# aconteceu com a publicacao dele.
_PADROES_DE_SEGREDO: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    # ⚠️ O `["\']?` ANTES DO SEPARADOR E CONSERTO DE UM VAZAMENTO REAL, pego pela
    # contraprova H em 02/09/2026. A primeira versao era
    # `\\b(authorization|...)\\b\\s*[:=]\\s*\\S+`, que casa o header cru
    # `Authorization: xoxb-...` e NAO casa a forma JSON
    # `{"Authorization":"xoxb-..."}` — porque entre a palavra e os dois-pontos ha
    # uma aspa. E a forma JSON e justamente a que os gateways devolvem no corpo
    # de um 400. O token passava inteiro para `ultimo_erro` e de la para a tela.
    (re.compile(r"""(?i)\b(authorization|x-api-key|api[-_]?key|apikey|cookie|token|secret|password|senha)\b["']?\s*[:=]\s*["']?[^\s"',}\]]+"""),
     r"\1: [redigido]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"), "bearer [redigido]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(\.[A-Za-z0-9_-]*)?"), "[jwt-redigido]"),
    (re.compile(r"\bop://[^\s\"']+"), "[referencia-redigida]"),
    (re.compile(r"\b(sk|pk|ghp|gho|pos|xox[baprs])[-_][A-Za-z0-9]{8,}"), "[token-redigido]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[chave-redigida]"),
    # Um Set-Cookie inteiro nao ajuda a diagnosticar e carrega sessao.
    (re.compile(r"(?i)set-cookie\s*:\s*\S+"), "set-cookie: [redigido]"),
)

#: Teto de tamanho. Um corpo de erro de 40 KB nao cabe na tela, nao ajuda o
#: operador e enche a coluna. 400 e o mesmo teto que `criativo/dominio.py` usa.
LIMITE_DE_ERRO: Final[int] = 400


def sanitizar_erro(bruto: Any) -> str:
    """Texto de erro seguro para gravar e mostrar. Nunca levanta."""
    if bruto is None:
        return "sem detalhe"
    texto = bruto if isinstance(bruto, str) else repr(bruto)
    texto = " ".join(texto.split())
    for padrao, substituto in _PADROES_DE_SEGREDO:
        texto = padrao.sub(substituto, texto)
    texto = texto[:LIMITE_DE_ERRO]
    return texto or "sem detalhe"


#: Chaves que nunca podem entrar num recibo. A comparacao e sobre a chave
#: NORMALIZADA (minuscula, sem separadores), entao `accessToken`, `ACCESS-TOKEN`
#: e `access token` colapsam no mesmo ramo. Mesma doutrina de
#: `cofre_recusa_chave_sensivel`, que e a segunda camada no banco.
_CHAVES_PROIBIDAS: Final[frozenset[str]] = frozenset({
    "password", "senha", "secret", "segredo", "token", "accesstoken",
    "refreshtoken", "idtoken", "apikey", "apisecret", "clientsecret",
    "privatekey", "authorization", "cookie", "setcookie", "sessionid",
    "credential", "credentials", "localizador", "servicerolekey",
    "servicerole", "anonkey", "jwt", "bearer",
})


def _normalizar_chave(chave: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", chave).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def recusar_chave_sensivel(documento: Any, caminho: str = "recibo") -> None:
    """Percorre o documento INTEIRO e recusa chave de material de credencial.

    Recusa em vez de remover: remover silenciosamente faria o chamador acreditar
    que gravou o que mandou. E a mensagem cita o CAMINHO, nunca o VALOR.
    """
    if isinstance(documento, Mapping):
        for chave, valor in documento.items():
            if _normalizar_chave(str(chave)) in _CHAVES_PROIBIDAS:
                raise PedidoRecusado(
                    f"campo proibido em {caminho}: '{chave}' nunca entra num recibo de publicacao",
                    codigo="campo_proibido",
                )
            recusar_chave_sensivel(valor, f"{caminho}.{chave}")
    elif isinstance(documento, (list, tuple)):
        for i, item in enumerate(documento):
            recusar_chave_sensivel(item, f"{caminho}[{i}]")


# ---------------------------------------------------------------------------
# Validacao do pedido
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PedidoDePublicacao:
    """O que o operador pediu, ja validado na forma. Imutavel."""

    peca_id: str
    peca_versao: int
    autorizacao_id: str
    destino_id: str
    modo: str
    timezone: str
    horario_local: str | None
    corpo: dict[str, Any]
    consentimento_agora: bool

    def como_payload(self) -> dict[str, Any]:
        """O payload exato que vai para a funcao governada.

        ⚠️ A ORDEM DAS CHAVES NAO IMPORTA e isso e proposital: o hash e derivado
        no banco por `jsonb::text`, que canoniza a ordem. Dois clientes que
        montem o mesmo pedido em ordens diferentes produzem o mesmo digest — que
        e exatamente o que um retry precisa.
        """
        payload: dict[str, Any] = {
            "peca_tipo": "master",
            "peca_id": self.peca_id,
            "peca_versao": self.peca_versao,
            "autorizacao_id": self.autorizacao_id,
            "destino_id": self.destino_id,
            "modo": self.modo,
            "timezone": self.timezone,
            "corpo": self.corpo,
        }
        if self.horario_local is not None:
            payload["horario_local"] = self.horario_local
        if self.consentimento_agora:
            payload["consentimento_agora"] = True
        return payload


def validar_timezone(nome: str) -> str:
    """Forma IANA + existencia na tzdata deste processo.

    A existencia e conferida DE NOVO no banco. Conferir aqui nao e redundancia
    inutil: evita uma ida ao banco por erro de digitacao, e a mensagem daqui diz
    o que fazer.
    """
    if not nome or not _FORMA_DE_TIMEZONE.match(nome):
        raise PedidoRecusado(
            "o timezone precisa ser um nome IANA (ex.: America/Sao_Paulo)",
            codigo="timezone_invalido",
        )
    try:
        ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise PedidoRecusado(
            f"timezone IANA desconhecido: {nome}", codigo="timezone_invalido"
        ) from exc
    return nome


def validar_horario_local(texto: str) -> str:
    """`YYYY-MM-DD HH:MM[:SS]`, sem offset. Devolve normalizado com segundos."""
    if not texto or not _FORMA_DE_HORARIO.match(texto):
        raise PedidoRecusado(
            "o horario local precisa ser 'AAAA-MM-DD HH:MM' — sem fuso no texto, "
            "porque o fuso e o campo timezone",
            codigo="horario_invalido",
        )
    normalizado = texto.replace("T", " ")
    if len(normalizado) == 16:
        normalizado += ":00"
    try:
        datetime.strptime(normalizado, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise PedidoRecusado(
            "esse horario local nao existe no calendario", codigo="horario_invalido"
        ) from exc
    return normalizado


def montar_pedido(
    *,
    peca_id: str,
    peca_versao: int,
    autorizacao_id: str,
    destino_id: str,
    modo: str,
    timezone: str,
    horario_local: str | None,
    corpo: dict[str, Any] | None,
    consentimento_agora: bool,
) -> PedidoDePublicacao:
    """Valida a forma e devolve o pedido imutavel. Nao fala com nada."""
    if modo not in MODOS:
        raise PedidoRecusado(
            f"modo deve ser um de {', '.join(MODOS)}", codigo="modo_invalido"
        )

    # ⚠️ ESTA RECUSA E O PORTAO DO `now`, E ELA E DUPLA DE PROPOSITO. O banco
    # tambem recusa (CHECK + funcao governada). Aqui existe para que a mensagem
    # diga o que falta, em vez de o operador receber um 500 vindo de constraint.
    if modo == "now" and not consentimento_agora:
        raise PedidoRecusado(
            "publicar agora exige um consentimento humano explicito e especifico "
            "para este job — marque a confirmacao antes de enviar",
            codigo="consentimento_ausente",
        )
    if consentimento_agora and modo != "now":
        raise PedidoRecusado(
            "o consentimento de publicacao imediata so faz sentido no modo 'now'",
            codigo="consentimento_sem_now",
        )

    tz = validar_timezone(timezone)

    horario: str | None = None
    if modo == "schedule":
        if not horario_local:
            raise PedidoRecusado(
                "agendar exige o horario local declarado", codigo="horario_ausente"
            )
        horario = validar_horario_local(horario_local)
    elif horario_local:
        raise PedidoRecusado(
            f"o modo '{modo}' nao aceita horario local; ele so existe em 'schedule'",
            codigo="horario_inesperado",
        )

    if peca_versao < 1:
        raise PedidoRecusado("a versao da peca comeca em 1", codigo="versao_invalida")

    conteudo = dict(corpo or {})
    recusar_chave_sensivel(conteudo, "corpo")

    return PedidoDePublicacao(
        peca_id=str(peca_id),
        peca_versao=int(peca_versao),
        autorizacao_id=str(autorizacao_id),
        destino_id=str(destino_id),
        modo=modo,
        timezone=tz,
        horario_local=horario,
        corpo=conteudo,
        consentimento_agora=bool(consentimento_agora),
    )


# ---------------------------------------------------------------------------
# Chave de idempotencia
# ---------------------------------------------------------------------------


def chave_de_idempotencia(pedido: PedidoDePublicacao, prefixo: str = "pub") -> str:
    """Derivada do CONTEUDO do pedido. Nunca sorteada.

    ⚠️ O `owner` NAO entra. Dois donos nao podem montar o mesmo pedido — a peca e
    o destino ja sao de um dono so, e o banco recusa cruzar donos. Incluir o
    owner aqui daria a impressao de escopo por dono e esconderia que a defesa
    real e o gatilho da secao 6 da v14_01.
    """
    material = json.dumps(
        {
            "peca": pedido.peca_id,
            "versao": pedido.peca_versao,
            "destino": pedido.destino_id,
            "modo": pedido.modo,
            "horario": pedido.horario_local,
            "tz": pedido.timezone,
            "corpo": pedido.corpo,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{prefixo}-{digest[:40]}"


def chave_derivada(prefixo: str, *partes: Any) -> str:
    """Chave para operacoes subsequentes (despacho, reconciliacao, cancelamento).

    Mesma disciplina: derivada do que a operacao FAZ, para que o retry da mesma
    operacao caia no replay em vez de virar operacao nova.
    """
    material = "|".join(str(p) for p in partes)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    chave = f"{prefixo}-{digest[:40]}"
    if not _FORMA_DA_CHAVE.match(chave):  # pragma: no cover — defensivo
        raise PedidoRecusado("chave de idempotencia malformada", codigo="chave_invalida")
    return chave


def forma_de_chave_valida(chave: str) -> bool:
    return bool(chave) and bool(_FORMA_DA_CHAVE.match(chave))


# ---------------------------------------------------------------------------
# Leitura de estado para a interface
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeituraDeEstado:
    """Como um estado deve ser APRESENTADO. O backend decide, nao o CSS."""

    estado: str
    rotulo: str
    tom: str          # 'neutro' | 'aguardando' | 'atencao' | 'sucesso' | 'falha'
    proxima_acao: str


#: ⚠️ NENHUM ESTADO INCERTO GANHA TOM `sucesso`. Verde para "a API respondeu" e
#: o defeito que a missao existe para nao repetir: quem ve verde para de checar.
#: `agendado` e `rascunho_externo` sao FATOS confirmados pelo control plane e por
#: isso recebem `aguardando` — nao sao publicacao, e nao sao incerteza.
_LEITURAS: Final[dict[str, LeituraDeEstado]] = {
    "rascunho": LeituraDeEstado(
        "rascunho", "Rascunho local", "neutro",
        "Revise e libere para despacho."),
    "pronto": LeituraDeEstado(
        "pronto", "Pronto para despachar", "neutro",
        "Aguardando o despachante assumir."),
    "em_voo": LeituraDeEstado(
        "em_voo", "Em voo", "aguardando",
        "O pedido foi enviado e a resposta ainda nao chegou. Nao reenvie."),
    "rascunho_externo": LeituraDeEstado(
        "rascunho_externo", "Rascunho criado no destino", "aguardando",
        "O rascunho existe no control plane. Reconcilie para confirmar."),
    "agendado": LeituraDeEstado(
        "agendado", "Agendado no destino", "aguardando",
        "Aguardando o horario. Reconcilie depois para confirmar a publicacao."),
    "publicacao_solicitada": LeituraDeEstado(
        "publicacao_solicitada", "Publicacao solicitada", "atencao",
        "O control plane aceitou o pedido; ninguem confirmou que esta no ar. "
        "Reconcilie antes de considerar publicado."),
    "publicado": LeituraDeEstado(
        "publicado", "Publicado (sem prova fechada)", "atencao",
        "O control plane declara publicado. Reconcilie para trazer URL e horario."),
    "reconciliado": LeituraDeEstado(
        "reconciliado", "Publicado e conferido", "sucesso",
        "Nada a fazer. A URL e o horario estao registrados."),
    "falha": LeituraDeEstado(
        "falha", "Falhou", "falha",
        "Leia o erro e crie um job novo — este nao e rearmado."),
    "indeterminado": LeituraDeEstado(
        "indeterminado", "Indeterminado", "atencao",
        "Nao sabemos se publicou. Reconcilie antes de tentar de novo — "
        "reenviar agora pode duplicar o post."),
    "cancelado": LeituraDeEstado(
        "cancelado", "Cancelado", "neutro",
        "Nada a fazer."),
}


def leitura_do_estado(estado: str) -> LeituraDeEstado:
    """Nunca inventa: estado desconhecido vira `atencao`, jamais `sucesso`."""
    conhecido = _LEITURAS.get(estado)
    if conhecido is not None:
        return conhecido
    return LeituraDeEstado(
        estado, f"Estado nao reconhecido ({estado})", "atencao",
        "Este estado nao existe no contrato desta versao. Nao trate como publicado; "
        "confira no painel do control plane antes de qualquer acao.",
    )


def tom_de(estado: str) -> str:
    return leitura_do_estado(estado).tom
