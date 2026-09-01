"""A fronteira da Data Manager API: monta o pacote, valida, e NÃO envia.

## A auditoria que veio antes de uma linha de código

O contrato manda reusar `conversion_queue` e `conversion_batches` se elas já
forem autoridades adequadas. Foram auditadas em 02/09/2026 contra o inventário
vivo do Supabase (`docs/volc-os-graph/volc-os-graph.json`, leitura de
22/08/2026, as duas com **0 linhas**):

    conversion_queue
      batch_id · bucket_weight · conversion_time · conversion_value ·
      created_at · currency_code · gclid · google_error · id ·
      original_bucket · sent_at · status · visit_id

Faltam CINCO coisas sem as quais um envio governado não existe:

  1. **destino** — nenhuma coluna diz conta DONA nem id NUMÉRICO da ação;
  2. **conta** — não há `customer_id`; a fila foi desenhada para UMA conta;
  3. **wbraid/gbraid** — só `gclid`, e é o tráfego de app e o de iOS com
     consentimento restrito que mais dependem dos outros dois;
  4. **consentimento** — nenhuma coluna; consentimento viaja COM o evento;
  5. **chave de deduplicação** — `id` é surrogate, e um surrogate novo a cada
     tentativa não deduplica nada do lado do Google.

E as duas **não têm DDL neste repositório**: `grep` em `supabase/migrations/`
não as encontra. Elas existem no banco e não são governadas por este código.

**Nenhuma fila nova foi criada, e nenhum schema foi tocado.** O que falta às
tabelas vivas exige migration, e migration é decisão de dono. O que esta entrega
fecha é a parte que não precisa de banco: montar o envelope, validá-lo item a
item e recusar o envio.

## Zero envio, e a recusa é estrutural

Não há cliente HTTP, URL ou credencial neste arquivo — há uma prova disso em
`test_trafego_data_manager.py`, que lê o próprio fonte. Um módulo que "não envia
porque ninguém chamou" depende de ninguém chamar. `enviar()` existe para que
quem procurar o caminho o ENCONTRE, e encontre a razão junto.

## O que ele NÃO decide

Ele não escolhe meta de campanha. A Data Manager transporta dados e eventos; a
meta que o lance persegue mora em `conversion_goal_campaign_config`, e trocá-la
é outro ato, com outra API e outra autorização. Confundir os dois faria "o
evento chegou" parecer "a campanha passou a perseguir isto".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Sequence, Tuple

from app.trafego import perfil_de_mensuracao as pdm
from app.trafego import plano_mensuracao as pm

#: A versão do ENVELOPE. Ela entra na impressão: mudar a forma do pacote sem
#: mudar este número faria dois pacotes de formatos diferentes colidirem na
#: mesma identidade, e o segundo seria lido como retry do primeiro.
VERSAO_DO_ENVELOPE = 1


# ═══════════════════════════════════════════════════════════════════════════
# IDENTIFICADOR DE CLIQUE
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ TRÊS, e não um. `gclid` é o caso comum de web; `wbraid` e `gbraid` existem
# porque em iOS com consentimento restrito e em tráfego de app o `gclid` não é
# anexado. Uma fronteira que só aceita `gclid` descarta em silêncio exatamente a
# fatia que mais depende de upload offline — e é a lacuna da fila legada.

CLIQUE_GCLID = "gclid"
CLIQUE_WBRAID = "wbraid"
CLIQUE_GBRAID = "gbraid"

IDENTIFICADORES = (CLIQUE_GCLID, CLIQUE_WBRAID, CLIQUE_GBRAID)


@dataclass(frozen=True)
class IdentificadorDeClique:
    """O que liga esta conversão a um clique. Exatamente um por evento."""

    tipo: str
    valor: str

    def __post_init__(self) -> None:
        if self.tipo not in IDENTIFICADORES:
            raise ValueError(
                f"identificador de clique {self.tipo!r} desconhecido; use um de "
                f"{IDENTIFICADORES}")
        if not str(self.valor or "").strip():
            raise ValueError(
                f"identificador {self.tipo} vazio: um evento sem clique não "
                "tem a que ser atribuído")
        object.__setattr__(self, "valor", str(self.valor).strip())


# ═══════════════════════════════════════════════════════════════════════════
# CONSENTIMENTO DO USUÁRIO — o do EVENTO, não o da conta
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ `accepted_customer_data_terms` é o aceite do ANUNCIANTE, no nível da conta,
# e ele é pré-requisito. O consentimento do VISITANTE é outro fato, viaja com o
# evento e não é conhecível no instante do plano. Colapsar os dois faria o
# envelope afirmar que o consentimento do usuário foi verificado quando o que se
# leu foi um aceite de termos do anunciante.

CONSENTIMENTO_CONCEDIDO = "concedido"
CONSENTIMENTO_NEGADO = "negado"
CONSENTIMENTO_NAO_DECLARADO = "nao_declarado"

CONSENTIMENTOS_DE_EVENTO = (CONSENTIMENTO_CONCEDIDO, CONSENTIMENTO_NEGADO,
                            CONSENTIMENTO_NAO_DECLARADO)


# ═══════════════════════════════════════════════════════════════════════════
# ERROS — nomeados, porque cada um pede uma ação diferente
# ═══════════════════════════════════════════════════════════════════════════


class FronteiraRecusou(RuntimeError):
    """Base. Nada saiu, e nada ia sair."""


class DestinoNaoResolvido(FronteiraRecusou):
    """Não há conta dona + id numérico. Não existe para onde mandar."""


class ConsentimentoInsuficiente(FronteiraRecusou):
    """A conta não declarou base para ingestão de dados."""


class EnvelopeAmbiguo(FronteiraRecusou):
    """Duas linhas do mesmo lote reivindicam a mesma identidade."""


class EnvioNaoAutorizado(FronteiraRecusou):
    """O caminho de envio não existe nesta entrega, e a razão é dita."""


# ═══════════════════════════════════════════════════════════════════════════
# O EVENTO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class EventoDeConversao:
    """Uma conversão a enviar — antes de qualquer validação.

    ⚠️ O dataclass aceita quase tudo de propósito: a validação acontece em
    `validar`, item a item, para que um evento ruim produza uma RECUSA NOMEADA
    no recibo em vez de uma exceção que derruba o lote inteiro. Um lote de mil
    conversões com uma hora malformada não é um lote inválido — são 999
    conversões que precisam chegar e uma que precisa ser consertada.
    """

    clique: IdentificadorDeClique
    #: ISO-8601 **com offset**. Ver `_hora_valida`.
    ocorrido_em: str
    #: O `transaction_id` do anunciante. É ele que torna o retry seguro.
    chave_de_deduplicacao: str
    valor: Optional[Decimal] = None
    moeda: Optional[str] = None
    consentimento_do_usuario: str = CONSENTIMENTO_NAO_DECLARADO


# ═══════════════════════════════════════════════════════════════════════════
# O ENVELOPE
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Envelope:
    """O pacote endereçado: destino, perfil, versão e os eventos.

    Frozen porque a impressão é derivada do conteúdo — e é ela que torna o
    retry seguro. Um objeto mutável deixaria alguém acrescentar um evento a um
    pacote cuja identidade já foi registrada.
    """

    versao: int
    destino: pm.DestinoDataManager
    customer_id: str
    login_customer_id: str
    perfil_chave: str
    consentimento_da_conta: str
    itens: Tuple[EventoDeConversao, ...]

    def corpo_da_impressao(self) -> Dict[str, Any]:
        """A identidade do PACOTE — e ela não depende da ordem dos eventos.

        ⚠️ Reordenar não é um pacote novo. Se a ordem entrasse, um retry que
        relesse a fila numa ordem diferente produziria outra impressão, e o
        Google receberia o mesmo lote duas vezes com identidades distintas.
        As chaves de deduplicação são ordenadas antes de entrar.

        ⚠️ E o identificador de clique NÃO entra: ele é dado de usuário, e a
        impressão vai para log, tela e recibo. A chave de deduplicação já
        identifica o evento, e é dela que a identidade do lote é feita.
        """
        return {
            "versao": self.versao,
            "customer_id": self.customer_id,
            "login_customer_id": self.login_customer_id,
            "operating_account_id": self.destino.operating_account_id,
            "product_destination_id": self.destino.product_destination_id,
            "perfil_chave": self.perfil_chave,
            "itens": sorted(
                ({"dedup": e.chave_de_deduplicacao,
                  "ocorrido_em": e.ocorrido_em,
                  "clique_tipo": e.clique.tipo,
                  "valor": None if e.valor is None else str(e.valor),
                  "moeda": e.moeda}
                 for e in self.itens),
                key=lambda d: d["dedup"]),
        }

    def json_canonico(self) -> str:
        return json.dumps(self.corpo_da_impressao(), ensure_ascii=False,
                          sort_keys=True, separators=(",", ":"))

    def impressao(self) -> str:
        return hashlib.sha256(self.json_canonico().encode("utf-8")).hexdigest()

    def json(self) -> Dict[str, Any]:
        return {
            "versao": self.versao,
            "impressao": self.impressao(),
            "customer_id": self.customer_id,
            "login_customer_id": self.login_customer_id,
            "destino": self.destino.json(),
            "perfil_chave": self.perfil_chave,
            "consentimento_da_conta": self.consentimento_da_conta,
            "itens": [
                {
                    "chave_de_deduplicacao": e.chave_de_deduplicacao,
                    "ocorrido_em": e.ocorrido_em,
                    # ⚠️ O TIPO do identificador, e nunca o VALOR. `gclid` é
                    # dado de usuário e este JSON vai para tela e log.
                    "clique_tipo": e.clique.tipo,
                    "valor": None if e.valor is None else str(e.valor),
                    "moeda": e.moeda,
                    "consentimento_do_usuario": e.consentimento_do_usuario,
                }
                for e in self.itens
            ],
        }


def montar_envelope(*, plano: pm.PlanoDeMensuracao,
                    perfil: pdm.PerfilDeMensuracao,
                    eventos: Sequence[EventoDeConversao]) -> Envelope:
    """O pacote, endereçado por conta DONA + id NUMÉRICO da ação eleita.

    ⚠️ As recusas aqui são de ENVELOPE, e não de item. A diferença: item
    inválido é um evento que não pode ir; destino ausente é não haver para onde
    ir, e consentimento de conta ausente é não haver base para mandar nada.
    Deixar o envelope nascer nesses casos produziria um pacote sintaticamente
    válido apontando para conta nenhuma.
    """
    if perfil.customer_id != plano.customer_id:
        raise ValueError(
            f"o perfil é da conta {perfil.customer_id} e o plano é da conta "
            f"{plano.customer_id}")
    alvo = None if plano.acao_alvo is None else plano.acao_alvo.id
    if perfil.acao_id is not None and perfil.acao_id != alvo:
        raise ValueError(
            f"o perfil diz que a ação que mede é #{perfil.acao_id} e o plano "
            f"elegeu {('#' + alvo) if alvo else 'nenhuma'}: o envio iria para "
            "o lugar errado")

    if not plano.destino.resolvido:
        raise DestinoNaoResolvido(
            "não há destino de ingestão offline para esta campanha: "
            + (plano.destino.causa or "causa não registrada")
            + " A Data Manager resolve destino por conta DONA + id NUMÉRICO da "
              "ação, e mandar para a conta errada não dá erro — dá silêncio.")

    if not perfil.aplicavel_a_envio_offline:
        raise ConsentimentoInsuficiente(
            "o perfil de mensuração não autoriza ingestão offline: o "
            f"consentimento da conta é {perfil.consentimento!r} e o envio exige "
            "'concedido'. Medir por tag do Google não depende de nós declararmos "
            "consentimento — o site declara. Mandar evento pela Data Manager, "
            "sim: somos nós que afirmamos que havia base para enviar.")

    lote = tuple(eventos)
    if not lote:
        raise ValueError(
            "envelope vazio: um pacote sem evento não é um pacote, é um pedido "
            "sem conteúdo")

    chaves = [str(e.chave_de_deduplicacao or "").strip() for e in lote]
    repetidas = {c for c in chaves if c and chaves.count(c) > 1}
    if repetidas:
        raise EnvelopeAmbiguo(
            "duas linhas do mesmo lote têm a mesma chave de dedup "
            f"({', '.join(sorted(repetidas))}). No mesmo pacote isso é "
            "ambiguidade NOSSA: o Google trataria a segunda como correção da "
            "primeira, e ninguém saberia qual das duas sobreviveu.")

    return Envelope(
        versao=VERSAO_DO_ENVELOPE,
        destino=plano.destino,
        customer_id=plano.customer_id,
        login_customer_id=plano.login_customer_id,
        perfil_chave=perfil.chave,
        consentimento_da_conta=perfil.consentimento,
        itens=lote,
    )


# ═══════════════════════════════════════════════════════════════════════════
# VALIDAÇÃO — item a item, com falha PARCIAL
# ═══════════════════════════════════════════════════════════════════════════

ITEM_VALIDO = "valido"
ITEM_RECUSADO = "recusado"


@dataclass(frozen=True)
class ItemValidado:
    """O veredito de UM evento. `causa` é obrigatória quando ele foi recusado."""

    chave_de_deduplicacao: str
    estado: str
    causa: Optional[str] = None

    def __post_init__(self) -> None:
        if self.estado not in (ITEM_VALIDO, ITEM_RECUSADO):
            raise ValueError(f"estado de item {self.estado!r} desconhecido")
        if self.estado == ITEM_RECUSADO and not str(self.causa or "").strip():
            raise ValueError(
                "recusa anônima é indistinguível de silêncio: um item recusado "
                "precisa dizer por quê")

    def json(self) -> Dict[str, Any]:
        return {"chave_de_deduplicacao": self.chave_de_deduplicacao,
                "estado": self.estado, "causa": self.causa}


@dataclass(frozen=True)
class ReciboDeValidacao:
    """O que a validação concluiu — e a declaração de que nada saiu."""

    envelope_impressao: str
    itens: Tuple[ItemValidado, ...]
    #: ⚠️ Literais, e não parâmetros. Não há como ligar o envio nesta entrega,
    #: e um flag que o ligasse seria uma porta que a ausência dele fecha.
    validate_only: bool = True
    enviado: bool = False

    @property
    def aceitos(self) -> int:
        return sum(1 for i in self.itens if i.estado == ITEM_VALIDO)

    @property
    def recusados(self) -> int:
        return sum(1 for i in self.itens if i.estado == ITEM_RECUSADO)

    def json(self) -> Dict[str, Any]:
        return {
            "envelope_impressao": self.envelope_impressao,
            "validate_only": self.validate_only,
            "enviado": self.enviado,
            "aceitos": self.aceitos,
            "recusados": self.recusados,
            "itens": [i.json() for i in self.itens],
        }


def _hora_valida(bruto: str) -> Optional[str]:
    """`None` quando a hora serve; a causa quando não serve.

    ⚠️ EXIGE OFFSET. Sem ele, "14:32" é um instante diferente em cada servidor,
    e o Google atribui a conversão ao clique por janela de tempo. O erro é
    silencioso: a conversão é aceita e atribuída errado.
    """
    texto = str(bruto or "").strip()
    if not texto:
        return "o evento não diz quando ocorreu"
    try:
        quando = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return (f"`{texto}` não é uma data ISO-8601 legível "
                "(esperado AAAA-MM-DDTHH:MM:SS±HH:MM)")
    if quando.tzinfo is None or quando.utcoffset() is None:
        return (f"`{texto}` não declara fuso. Sem offset a hora é um instante "
                "diferente em cada servidor, e a atribuição do clique erra a "
                "janela sem dar erro")
    return None


def _valor_valido(valor: Optional[Decimal],
                  moeda: Optional[str]) -> Optional[str]:
    """⚠️ Zero é um valor MEDIDO. `if valor:` o trataria como ausente."""
    tem_valor = valor is not None
    tem_moeda = bool(str(moeda or "").strip())
    if tem_valor and not tem_moeda:
        return ("valor sem moeda não é dinheiro: a Data Manager exige "
                "currencyCode junto de conversionValue, e sem ele o Google "
                "adota a moeda da conta")
    if tem_moeda and not tem_valor:
        return "moeda declarada sem valor: não há o que converter"
    if tem_valor:
        try:
            numero = Decimal(str(valor))
        except (InvalidOperation, ValueError, TypeError):
            return f"valor {valor!r} não é um número representável"
        if not numero.is_finite() or numero < 0:
            return f"valor {valor!r} precisa ser finito e não negativo"
    return None


def validar(envelope: Envelope) -> ReciboDeValidacao:
    """Confere cada evento e devolve o recibo. **Nada é enviado.**

    ⚠️ FALHA PARCIAL POR ITEM, e não tudo-ou-nada. Um lote de mil conversões em
    que uma tem hora malformada não é um lote inválido: são 999 conversões que
    precisam chegar e uma que precisa ser consertada. O tudo-ou-nada perderia
    as 999 por causa de uma — e, pior, o operador consertaria a errada.
    """
    vereditos = []
    for evento in envelope.itens:
        chave = str(evento.chave_de_deduplicacao or "").strip()
        causa: Optional[str] = None

        if not chave:
            causa = ("evento sem chave de dedup (`transaction_id`): sem ela um "
                     "retry DUPLICA a conversão em vez de substituí-la")
        elif evento.consentimento_do_usuario != CONSENTIMENTO_CONCEDIDO:
            causa = (
                "o consentimento do usuário para este evento é "
                f"{evento.consentimento_do_usuario!r}, e o envio exige "
                "'concedido'. Ausência de declaração não é permissão.")
        else:
            causa = (_hora_valida(evento.ocorrido_em)
                     or _valor_valido(evento.valor, evento.moeda))

        vereditos.append(ItemValidado(
            chave_de_deduplicacao=chave or "(sem chave)",
            estado=ITEM_RECUSADO if causa else ITEM_VALIDO,
            causa=causa))

    return ReciboDeValidacao(envelope_impressao=envelope.impressao(),
                             itens=tuple(vereditos))


def enviar(envelope: Envelope) -> None:
    """O caminho de envio — que **não existe**, e diz por quê.

    ⚠️ Ele existe como função para que quem procurar o envio o ENCONTRE, com a
    razão junto, em vez de concluir que basta acrescentar um POST. Um
    módulo que "não envia porque ninguém chamou" depende de ninguém chamar.

    Para abrir esta porta faltam, nesta ordem:

      1. autorização de dono para gastar quota e alterar dados de conversão;
      2. um lugar durável para a fila — `conversion_queue` não serve: não tem
         destino, não tem conta, não tem wbraid/gbraid, não tem consentimento e
         não tem chave de dedup (auditoria no cabeçalho deste módulo);
      3. o recibo assíncrono da própria Data Manager, que é por lote e chega
         depois — e sem lugar para guardá-lo, um envio aceito e um envio
         perdido ficam indistinguíveis.
    """
    raise EnvioNaoAutorizado(
        f"o envelope {envelope.impressao()[:12]}… está montado e validado, e "
        "esta entrega é validateOnly: nenhum evento é enviado. Faltam, nesta "
        "ordem, autorização de dono, uma fila durável com destino/conta/"
        "consentimento/dedup, e um lugar para o recibo assíncrono do lote.")
