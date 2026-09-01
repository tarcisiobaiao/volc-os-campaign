"""O perfil de mensuração: a identidade do que uma campanha MEDE.

## Por que ele não é a `chave_intencao`

`chave_intencao` é o sha256 do payload aprovado inteiro — conta, canal, verba,
lance, critérios, copy e destino (`routers/trafego.py:_impressao_aprovavel`).
Ela é a identidade do **lançamento**, e está certa no que faz: dela saem a marca
remota do canário e a chave de idempotência do ledger. Trocar uma headline
PRECISA invalidar a autorização.

Ela não pode ser a identidade da **medição**, e erra nas duas direções ao mesmo
tempo. Medido em 02/09/2026, chamando a própria rota:

    chave base               83e7fe044dc356ce…
    mesma oferta, verba 50   928379f2dcf0c957…
    mesma oferta, verba 80   e5189893fb8ec057…

  - **distingue demais** — a mesma oferta com duas verbas vira duas identidades,
    e as duas campanhas medem exatamente a mesma coisa;
  - **não distingue o que importa** — nada nela fala de evento de negócio,
    funil, regra de valor ou janela de atribuição. Dois nichos da mesma conta
    (BPC/LOAS e IPVA) herdam a mesma meta, elegem a mesma `ConversionAction` por
    semântica e apontam para o mesmo destino: tudo o que o plano guardava era
    igual, e a única coisa diferente era o que ninguém estava modelando.

Acidente não é identidade. Este módulo substitui o acidente por uma decisão
declarada.

## A regra que organiza tudo aqui

**A identidade é o que alguém DECIDIU. As observações são o que se LEU.**

Só a decisão entra na `chave`:

    negócio · oferta/intenção · funil · evento · conta operacional ·
    conta DONA da ação · id NUMÉRICO da ação · semântica ·
    regra de valor · janela e modelo de atribuição

O que se leu — fonte do sinal comprovada, consentimento — fica FORA. Não por
economia: se a fonte entrasse, o dia em que o sinal morresse produziria um
perfil NOVO, o histórico da campanha apontaria para um perfil que ninguém
criou, e a linha antiga continuaria existindo descrevendo a mesma medição com
identidade oposta. É a mesma regra que `PlanoDeMensuracao.impressao` aplica ao
frescor, um degrau acima.

## ⚠️ NUNCA por nome humano

Não existe campo de nome aqui, e a ausência é o contrato. Renomear a ação no
painel não muda o que ela mede; e duas ações homônimas em contas diferentes
mediriam coisas diferentes com o mesmo rótulo. O endereço é **conta dona + id
numérico**, que é exatamente o que a Data Manager exige como destino.

## O que este módulo NÃO faz

Não lê o Google, não escreve no banco, não decide portão. Ele é domínio puro:
recebe um `PlanoDeMensuracao` já lido e os eixos de negócio que um humano
declarou, e devolve identidade e aplicabilidade. Quem decide portão é
`prontidao.py`; quem persiste é `persistencia.py`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Mapping, Optional

from app.trafego import plano_mensuracao as pm

#: A versão do CONTRATO de identidade. Ela entra na chave de propósito: mudar
#: o que compõe a identidade sem mudar este número faria dois perfis diferentes
#: colidirem na mesma chave, e a colisão seria silenciosa.
VERSAO_DO_PERFIL = 1


# ═══════════════════════════════════════════════════════════════════════════
# FUNIL — o degrau da jornada que esta campanha ataca
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ Três valores, e nenhum "outro". Um enum aberto viraria campo de texto
# livre, e campo de texto livre não identifica: "fundo", "Fundo" e "fundo de
# funil" seriam três perfis para a mesma coisa.

FUNIL_DESCOBERTA = "descoberta"
FUNIL_CONSIDERACAO = "consideracao"
FUNIL_ACAO = "acao"

FUNIS = (FUNIL_DESCOBERTA, FUNIL_CONSIDERACAO, FUNIL_ACAO)


# ═══════════════════════════════════════════════════════════════════════════
# FONTE DO SINAL — observação, e por isso FORA da identidade
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ TRÊS estados, e a distinção entre os dois primeiros é a que este projeto
# já pagou para aprender. Auto-tagging ligado, tag configurada e importação
# declarada dizem por onde a conversão PODERIA chegar; nenhuma delas diz que
# alguma chegou. Empilhá-las como prova fazia uma conta com `auto_tagging=True`
# e ZERO conversão medida sair com Smart Bidding elegível — carregando, na
# lista ao lado, o bloqueador que dizia que nenhuma conversão chegou.

#: Nada comprovado e nenhum caminho declarado: não há por onde medir.
FONTE_NAO_COMPROVADA = "nao_comprovada"
#: Existe via (tag, importação, auto-tagging, destino offline) e NENHUMA
#: conversão observada. É problema de instrumentação, não de configuração.
FONTE_CAMINHO_DECLARADO = "caminho_declarado"
#: Uma conversão foi OBSERVADA e é recente. É a única prova, e ela é agnóstica
#: ao caminho: vale para tag do Google, importação GA4 e upload offline.
FONTE_CONVERSAO_OBSERVADA = "conversao_observada"

FONTES = (FONTE_NAO_COMPROVADA, FONTE_CAMINHO_DECLARADO,
          FONTE_CONVERSAO_OBSERVADA)

#: As fontes que PROVAM sinal. Uma tupla de um elemento, e ela é assim de
#: propósito: qualquer crescimento aqui precisa passar por esta linha.
FONTES_COMPROVADAS = (FONTE_CONVERSAO_OBSERVADA,)


# ═══════════════════════════════════════════════════════════════════════════
# CONSENTIMENTO — observação, e por isso FORA da identidade
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ O ÚNICO sinal de consentimento que este sistema lê hoje é
# `customer.accepted_customer_data_terms`, que é do NÍVEL DA CONTA e é
# pré-requisito de enhanced conversions e de upload de dados de usuário. Ele
# NÃO é o consentimento por usuário: esse viaja com o evento, no envelope da
# Data Manager, e não é conhecível no instante do plano.
#
# Chamar o primeiro de "consentimento" sem dizer isto faria a tela afirmar que
# o consentimento do visitante foi verificado — e ele não foi.

CONSENTIMENTO_CONCEDIDO = "concedido"
CONSENTIMENTO_NEGADO = "negado"
CONSENTIMENTO_NAO_DECLARADO = "nao_declarado"
CONSENTIMENTO_NAO_APLICAVEL = "nao_aplicavel"

CONSENTIMENTOS = (CONSENTIMENTO_CONCEDIDO, CONSENTIMENTO_NEGADO,
                  CONSENTIMENTO_NAO_DECLARADO, CONSENTIMENTO_NAO_APLICAVEL)


# ═══════════════════════════════════════════════════════════════════════════
# REGRA DE VALOR
# ═══════════════════════════════════════════════════════════════════════════

VALOR_SEM_VALOR = "sem_valor"
VALOR_FIXO = "fixo"
VALOR_POR_EVENTO = "por_evento"

MODOS_DE_VALOR = (VALOR_SEM_VALOR, VALOR_FIXO, VALOR_POR_EVENTO)


@dataclass(frozen=True)
class RegraDeValor:
    """Quanto vale uma conversão deste perfil — e em que moeda.

    ⚠️ `valor` sem `moeda` não é dinheiro, é um número solto. A Data Manager
    exige `currencyCode` junto de `conversionValue`; mandar o número sozinho faz
    o Google adotar a moeda da conta, que pode não ser a que o operador tinha em
    mente — e a diferença só aparece no relatório, semanas depois, como um ROAS
    que ninguém consegue explicar.
    """

    modo: str
    #: `Decimal`, nunca `float`: dinheiro que passa por float binário deixa de
    #: ser o mesmo dinheiro em máquinas diferentes.
    valor: Optional[Decimal] = None
    #: ISO-4217, três letras maiúsculas.
    moeda: Optional[str] = None

    def __post_init__(self) -> None:
        if self.modo not in MODOS_DE_VALOR:
            raise ValueError(
                f"modo de valor {self.modo!r} desconhecido; use um de "
                f"{MODOS_DE_VALOR}")
        if self.modo == VALOR_FIXO:
            if self.valor is None:
                raise ValueError(
                    "regra de valor FIXO sem valor: o modo afirma que existe um "
                    "número e não há número nenhum")
            if not self.moeda:
                raise ValueError(
                    "regra de valor FIXO sem moeda: valor sem moeda não é "
                    "dinheiro, e a Data Manager exige currencyCode junto de "
                    "conversionValue")
        if self.modo == VALOR_SEM_VALOR and (self.valor is not None
                                             or self.moeda):
            raise ValueError(
                "regra sem_valor carregando valor ou moeda: as duas afirmações "
                "não podem valer ao mesmo tempo")
        if self.moeda is not None:
            texto = str(self.moeda).strip()
            if len(texto) != 3 or not texto.isalpha():
                raise ValueError(
                    f"moeda {self.moeda!r} não é um código ISO-4217 de três "
                    "letras")
            object.__setattr__(self, "moeda", texto.upper())
        if self.valor is not None:
            try:
                numero = (self.valor if isinstance(self.valor, Decimal)
                          else Decimal(str(self.valor)))
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise ValueError(
                    f"valor {self.valor!r} não é um número representável") from exc
            # ⚠️ FINITO E NÃO NEGATIVO, e a revisão adversarial de 02/09/2026
            # mostrou por que a checagem tem de morar AQUI: `data_manager`
            # recusava `-1` no evento, e o portão de MAXIMIZE_CONVERSION_VALUE
            # olhava só o MODO — então uma regra com valor `-1` abria o lance
            # por valor. A regra é o contrato; validá-la só na hora do envio é
            # validar tarde demais.
            #
            # ⚠️ Zero CONTINUA passando: zero é uma decisão declarada, negativo
            # é um erro, e colapsar os dois apagaria a distinção que o modo
            # `sem_valor` já existe para carregar.
            if not numero.is_finite() or numero < 0:
                raise ValueError(
                    f"valor {self.valor!r} precisa ser finito e não negativo: "
                    "uma conversão não vale menos que nada")
            object.__setattr__(self, "valor", numero)

    def json(self) -> Dict[str, Any]:
        return {
            "modo": self.modo,
            # `str` do `Decimal`, e não `float`: a travessia preserva a casa
            # decimal exata que alguém escreveu.
            "valor": None if self.valor is None else str(self.valor),
            "moeda": self.moeda,
        }


def regra_sem_valor() -> RegraDeValor:
    """O default HONESTO: ninguém declarou valor, e o perfil diz isso."""
    return RegraDeValor(modo=VALOR_SEM_VALOR)


# ═══════════════════════════════════════════════════════════════════════════
# JANELA E ATRIBUIÇÃO
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ Esta entrega NÃO lê a janela de atribuição do Google. Por isso os estados
# aqui não são os sete de leitura: eles seriam uma promessa de leitura que não
# acontece. São dois, e os dois dizem a verdade — alguém declarou, ou ninguém
# declarou.

JANELA_DECLARADA = "declarada"
JANELA_NAO_DECLARADA = "nao_declarada"

ESTADOS_DE_JANELA = (JANELA_DECLARADA, JANELA_NAO_DECLARADA)


@dataclass(frozen=True)
class JanelaDeAtribuicao:
    """A janela e o modelo de atribuição que esta medição usa.

    ⚠️ Nenhum default de 30 dias. Trinta dias é o padrão do Google para muitas
    ações e NÃO é o padrão de todas; escrevê-lo aqui afirmaria uma configuração
    que ninguém conferiu, e a conta de conversões sairia errada exatamente onde
    o operador confiaria nela.
    """

    estado: str
    dias_de_clique: Optional[int] = None
    dias_de_engajamento: Optional[int] = None
    modelo: Optional[str] = None
    causa: Optional[str] = None

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS_DE_JANELA:
            raise ValueError(
                f"estado de janela {self.estado!r} desconhecido; use um de "
                f"{ESTADOS_DE_JANELA}")
        tem_numero = any(v is not None for v in
                         (self.dias_de_clique, self.dias_de_engajamento,
                          self.modelo))
        if self.estado == JANELA_NAO_DECLARADA and tem_numero:
            raise ValueError(
                "janela não declarada carregando número ou modelo: o estado "
                "diz que ninguém declarou e os campos afirmam o contrário")
        if self.estado == JANELA_DECLARADA and not tem_numero:
            raise ValueError(
                "janela declarada e vazia: declarar sem dizer o quê é o mesmo "
                "que não declarar, com a aparência de ter declarado")
        for campo in ("dias_de_clique", "dias_de_engajamento"):
            valor = getattr(self, campo)
            if valor is not None and (not isinstance(valor, int)
                                      or isinstance(valor, bool)
                                      or valor <= 0):
                raise ValueError(f"{campo}={valor!r} precisa ser inteiro > 0")

    def json(self) -> Dict[str, Any]:
        return {
            "estado": self.estado,
            "dias_de_clique": self.dias_de_clique,
            "dias_de_engajamento": self.dias_de_engajamento,
            "modelo": self.modelo,
            "causa": self.causa,
        }


def janela_nao_declarada(causa: Optional[str] = None) -> JanelaDeAtribuicao:
    return JanelaDeAtribuicao(
        estado=JANELA_NAO_DECLARADA,
        causa=causa or (
            "ninguém declarou janela nem modelo de atribuição para esta "
            "medição, e este sistema não os lê do Google nesta entrega."))


# ═══════════════════════════════════════════════════════════════════════════
# O PERFIL
# ═══════════════════════════════════════════════════════════════════════════


#: Os caracteres que um eixo de negócio pode ter depois de normalizado.
_CARACTERES_DO_SLUG = set("abcdefghijklmnopqrstuvwxyz0123456789-")


def _slug(valor: Any, campo: str) -> str:
    """Normaliza um eixo de negócio — e RECUSA o que não é canônico.

    `strip().lower()` porque " BPC-LOAS " e "bpc-loas" são a mesma oferta: caixa
    e espaço em volta não carregam decisão nenhuma.

    ⚠️ E aqui a normalização PARA. A primeira versão prometia na docstring que
    "BPC/LOAS" e "bpc-loas" eram a mesma oferta e produzia duas identidades — a
    revisão adversarial de 02/09/2026 reproduziu (`bpc/loas` ≠ `bpc-loas`).
    Havia duas saídas, e a escolhida é a segunda:

      1. **fundir separadores** (`/` → `-`). Isso é um MERGE silencioso: `x/y` e
         `x-y` podem ser ofertas genuinamente diferentes, e fundi-las é o defeito
         oposto ao que este módulo combate — e mais caro, porque some com uma
         das duas em vez de duplicar;
      2. **recusar o que não é canônico.** O erro aparece no primeiro uso, com o
         nome do campo e o caractere ofensor, e não seis meses depois num
         relatório que não fecha.

    Quem escreve "BPC/LOAS" recebe uma recusa que diz o que escrever.
    """
    texto = str(valor or "").strip().lower()
    if not texto:
        raise ValueError(
            f"perfil sem {campo}: um eixo em branco não identifica nada, e "
            "identidade anônima é indistinguível de silêncio")
    fora = sorted(set(texto) - _CARACTERES_DO_SLUG)
    if fora:
        raise ValueError(
            f"{campo}={valor!r} não é canônico: os caracteres {fora!r} não são "
            "aceitos. Use apenas letras minúsculas, dígitos e hífen — "
            "normalizar separadores automaticamente fundiria ofertas que podem "
            "ser diferentes, e um merge silencioso é pior que uma recusa.")
    return texto


@dataclass(frozen=True)
class PerfilDeMensuracao:
    """O que esta campanha mede, de quem é a ação, e sob que contrato.

    Frozen porque a chave é derivada do conteúdo: um objeto mutável deixaria
    alguém "melhorar" um perfil depois de a chave ter sido gravada, e as duas
    coisas deixariam de descrever o mesmo perfil.
    """

    # ── decisão: entra na identidade ────────────────────────────────────────
    customer_id: str
    login_customer_id: str
    #: O negócio/projeto. Uma conta pode servir a mais de um.
    negocio: str
    #: A oferta ou intenção — `bpc-loas`, `ipva`. É o eixo que impede dois
    #: nichos da mesma conta de colidirem silenciosamente.
    intencao: str
    funil: str
    #: O evento de NEGÓCIO — `lead-qualificado`, `matricula`. Diferente da
    #: semântica do Google (`PURCHASE/WEBSITE`), que descreve a ação técnica.
    evento: str
    #: ⚠️ A conta DONA da ação, que numa hierarquia com conversão centralizada
    #: no MCC não é a conta que roda a campanha. É ela que a Data Manager exige
    #: como operating account.
    acao_owner_id: Optional[str]
    #: O id NUMÉRICO. Nunca o nome, nunca o resource_name.
    acao_id: Optional[str]
    #: `CATEGORIA/ORIGEM` da ação eleita, quando há uma.
    semantica: Optional[str]
    regra_de_valor: RegraDeValor
    janela: JanelaDeAtribuicao

    # ── observação: NÃO entra na identidade ─────────────────────────────────
    fonte_do_sinal: str = FONTE_NAO_COMPROVADA
    consentimento: str = CONSENTIMENTO_NAO_DECLARADO
    #: Por que a ação ficou em aberto, quando ficou. Excludente com `acao_id`.
    causa_sem_acao: Optional[str] = None

    versao: int = VERSAO_DO_PERFIL

    def __post_init__(self) -> None:
        object.__setattr__(self, "negocio", _slug(self.negocio, "negócio"))
        object.__setattr__(self, "intencao", _slug(self.intencao, "intenção"))
        object.__setattr__(self, "evento", _slug(self.evento, "evento"))

        for campo in ("customer_id", "login_customer_id"):
            valor = str(getattr(self, campo) or "").strip()
            if not valor.isdigit():
                raise ValueError(f"perfil sem {campo} numérico")
            object.__setattr__(self, campo, valor)

        if self.funil not in FUNIS:
            raise ValueError(
                f"funil {self.funil!r} desconhecido; use um de {FUNIS}")
        if self.fonte_do_sinal not in FONTES:
            raise ValueError(
                f"fonte do sinal {self.fonte_do_sinal!r} desconhecida; use um "
                f"de {FONTES}")
        if self.consentimento not in CONSENTIMENTOS:
            raise ValueError(
                f"consentimento {self.consentimento!r} desconhecido; use um de "
                f"{CONSENTIMENTOS}")

        if self.acao_id is not None:
            if not str(self.acao_id).strip().isdigit():
                raise ValueError(
                    f"ação {self.acao_id!r} sem id numérico não é endereçável: "
                    "o destino da Data Manager é o ID, nunca o nome")
            # ⚠️ A MESMA guarda que a v12_02 impõe no schema
            # (`trafego_plano_destino_e_do_dono_da_acao`), aqui na fronteira do
            # domínio. Um id sem dono produz um destino sintaticamente válido
            # apontando para conta nenhuma — e a Data Manager exige que a
            # operating account POSSUA a ação.
            if not str(self.acao_owner_id or "").strip().isdigit():
                raise ValueError(
                    "ação eleita sem conta dona: sem o dono, a identidade "
                    "descreve um envio que não tem para onde ir")
        elif self.acao_owner_id is not None:
            raise ValueError(
                "conta dona sem ação eleita: dono de coisa nenhuma não "
                "endereça nada")

        # Excludência, no mesmo desenho de `PlanoDeMensuracao`.
        if self.acao_id is not None and self.causa_sem_acao:
            raise ValueError(
                "ação eleita e causa de não eleger ao mesmo tempo: a tela não "
                "teria como saber qual das duas é verdade")

    # ── identidade ──────────────────────────────────────────────────────────

    def corpo_da_identidade(self) -> Dict[str, Any]:
        """Só o que foi DECIDIDO. Nunca o que foi observado.

        ⚠️ `fonte_do_sinal` e `consentimento` estão fora, e a ausência é o
        contrato — ver o cabeçalho do módulo. `causa_sem_acao` também: ela é
        prosa que explica uma ausência já descrita por `acao_id is None`.
        """
        return {
            "versao": self.versao,
            "customer_id": self.customer_id,
            "login_customer_id": self.login_customer_id,
            "negocio": self.negocio,
            "intencao": self.intencao,
            "funil": self.funil,
            "evento": self.evento,
            "acao_owner_id": self.acao_owner_id,
            "acao_id": self.acao_id,
            "semantica": self.semantica,
            "regra_de_valor": self.regra_de_valor.json(),
            # ⚠️ O ESTADO e a CAUSA da janela ficam fora: eles dizem como se
            # sabe, e não o que se mede. Dois perfis com 30 dias de clique
            # medem a mesma coisa, tenha um deles causa registrada ou não.
            "janela": {
                "dias_de_clique": self.janela.dias_de_clique,
                "dias_de_engajamento": self.janela.dias_de_engajamento,
                "modelo": self.janela.modelo,
            },
        }

    def json_canonico(self) -> str:
        return json.dumps(self.corpo_da_identidade(), ensure_ascii=False,
                          sort_keys=True, separators=(",", ":"))

    @property
    def chave(self) -> str:
        return hashlib.sha256(self.json_canonico().encode("utf-8")).hexdigest()

    # ── aplicabilidade ──────────────────────────────────────────────────────

    @property
    def aplicavel_a_ativacao(self) -> bool:
        """Existe algo que meça esta campanha, e nada proíbe medi-lo?

        ⚠️ Não é "pode ativar". É um dos insumos do portão de ativação, e o
        portão mora em `prontidao.py`. Um perfil aplicável e uma campanha sem
        observabilidade continuam produzindo ativação BLOQUEADA.
        """
        return (self.acao_id is not None
                and self.consentimento != CONSENTIMENTO_NEGADO)

    @property
    def aplicavel_a_smart_bidding(self) -> bool:
        """Além de existir a medida, ela está de fato CHEGANDO?

        ⚠️ Falha FECHADO por construção: a única fonte que abre é
        `FONTE_CONVERSAO_OBSERVADA`, e capacidade declarada nunca vira prova.
        """
        return (self.aplicavel_a_ativacao
                and self.fonte_do_sinal in FONTES_COMPROVADAS)

    @property
    def aplicavel_a_envio_offline(self) -> bool:
        """A ingestão offline exige mais: consentimento CONCEDIDO, não silêncio.

        ⚠️ Aqui `nao_declarado` NÃO passa, e a assimetria com `ativacao` é
        deliberada. Medir por tag do Google não depende de nós declararmos
        consentimento — o site declara. Mandar evento pela Data Manager, sim:
        somos nós que afirmamos, no envelope, que havia base para enviar.
        """
        return (self.acao_id is not None
                and self.consentimento == CONSENTIMENTO_CONCEDIDO)

    # ── travessia ───────────────────────────────────────────────────────────

    def json(self) -> Dict[str, Any]:
        return {
            "versao": self.versao,
            "customer_id": self.customer_id,
            "login_customer_id": self.login_customer_id,
            "negocio": self.negocio,
            "intencao": self.intencao,
            "funil": self.funil,
            "evento": self.evento,
            "acao_owner_id": self.acao_owner_id,
            "acao_id": self.acao_id,
            "semantica": self.semantica,
            "regra_de_valor": self.regra_de_valor.json(),
            "janela": self.janela.json(),
            "fonte_do_sinal": self.fonte_do_sinal,
            "consentimento": self.consentimento,
            "causa_sem_acao": self.causa_sem_acao,
            "aplicavel_a_ativacao": self.aplicavel_a_ativacao,
            "aplicavel_a_smart_bidding": self.aplicavel_a_smart_bidding,
            "aplicavel_a_envio_offline": self.aplicavel_a_envio_offline,
            "chave": self.chave,
        }


def de_json(dados: Mapping[str, Any]) -> PerfilDeMensuracao:
    """A linha gravada volta a ser perfil — RECONSTRUÍDA e CONFERIDA.

    ⚠️ A chave viaja no JSON e é comparada com a recalculada. Sem esta
    conferência, um documento adulterado — ou uma mudança futura na derivação —
    produziria um perfil diferente do que foi gravado, e ninguém notaria: os
    dois pareceriam perfis perfeitamente válidos. É a mesma guarda que
    `plano_mensuracao.do_json` já impõe sobre a impressão.
    """
    valor = dados.get("regra_de_valor") or {}
    janela = dados.get("janela") or {}
    perfil = PerfilDeMensuracao(
        customer_id=dados.get("customer_id"),
        login_customer_id=dados.get("login_customer_id"),
        negocio=dados.get("negocio"),
        intencao=dados.get("intencao"),
        funil=dados.get("funil"),
        evento=dados.get("evento"),
        acao_owner_id=dados.get("acao_owner_id"),
        acao_id=dados.get("acao_id"),
        semantica=dados.get("semantica"),
        regra_de_valor=RegraDeValor(
            modo=valor.get("modo", VALOR_SEM_VALOR),
            valor=(None if valor.get("valor") in (None, "")
                   else Decimal(str(valor["valor"]))),
            moeda=valor.get("moeda"),
        ),
        janela=JanelaDeAtribuicao(
            estado=janela.get("estado", JANELA_NAO_DECLARADA),
            dias_de_clique=janela.get("dias_de_clique"),
            dias_de_engajamento=janela.get("dias_de_engajamento"),
            modelo=janela.get("modelo"),
            causa=janela.get("causa"),
        ),
        fonte_do_sinal=dados.get("fonte_do_sinal", FONTE_NAO_COMPROVADA),
        consentimento=dados.get("consentimento", CONSENTIMENTO_NAO_DECLARADO),
        causa_sem_acao=dados.get("causa_sem_acao"),
        versao=int(dados.get("versao") or VERSAO_DO_PERFIL),
    )
    declarada = dados.get("chave")
    if declarada and declarada != perfil.chave:
        raise ValueError(
            "a chave do perfil reconstruído não bate com a gravada "
            f"({declarada[:12]}… ≠ {perfil.chave[:12]}…): o documento descreve "
            "uma medição diferente da que foi registrada")
    return perfil


# ═══════════════════════════════════════════════════════════════════════════
# DERIVAÇÃO A PARTIR DO PLANO LIDO
# ═══════════════════════════════════════════════════════════════════════════


def fonte_do_plano(plano: pm.PlanoDeMensuracao) -> str:
    """A fonte OBSERVADA — reusando a distinção que `plano_mensuracao` já faz.

    ⚠️ Reuso, e não uma segunda regra. `fontes_de_sinal_observadas` e
    `caminhos_de_sinal_declarados` já carregam a separação entre prova e
    capacidade, e ela custou caro para ser aprendida. Reimplementá-la aqui
    criaria dois lugares onde a mesma distinção pode divergir.
    """
    if pm.fontes_de_sinal_observadas(plano):
        return FONTE_CONVERSAO_OBSERVADA
    if pm.caminhos_de_sinal_declarados(plano):
        return FONTE_CAMINHO_DECLARADO
    return FONTE_NAO_COMPROVADA


def consentimento_do_plano(plano: pm.PlanoDeMensuracao) -> str:
    """O consentimento DE CONTA, e ele diz o que é em voz alta.

    ⚠️ `accepted_customer_data_terms` é o aceite dos termos de dados do
    cliente, no nível da CONTA. Ele não é o consentimento do visitante — esse
    viaja com o evento. Um `None` aqui é "ninguém leu", e vira
    `nao_declarado`, nunca `negado`: tratar ignorância como recusa fecharia a
    ingestão offline de contas que aceitaram os termos e que ninguém consultou.
    """
    aceite = plano.marcacao.aceitou_termos_de_dados
    if aceite is True:
        return CONSENTIMENTO_CONCEDIDO
    if aceite is False:
        return CONSENTIMENTO_NEGADO
    return CONSENTIMENTO_NAO_DECLARADO


def derivar_de_plano(
        plano: pm.PlanoDeMensuracao, *,
        negocio: str,
        intencao: str,
        funil: str,
        evento: str,
        regra_de_valor: Optional[RegraDeValor] = None,
        janela: Optional[JanelaDeAtribuicao] = None,
        consentimento: Optional[str] = None,
) -> PerfilDeMensuracao:
    """O perfil desta campanha: eixos DECLARADOS + ação lida do plano.

    ⚠️ Os quatro eixos de negócio são obrigatórios e não têm default. Um
    default aqui — `evento="conversao"`, digamos — faria dois nichos diferentes
    voltarem a colidir, que é exatamente o defeito que este módulo existe para
    consertar, só que com a aparência de estar consertado.

    ⚠️ Um plano SEM ação eleita produz perfil COM identidade e SEM ação. `None`
    seria indistinguível de "ninguém tentou": o perfil existe, diz o que se
    decidiu, e diz que a ação ficou em aberto — que é o estado real.
    """
    alvo = plano.acao_alvo
    return PerfilDeMensuracao(
        customer_id=plano.customer_id,
        login_customer_id=plano.login_customer_id,
        negocio=negocio,
        intencao=intencao,
        funil=funil,
        evento=evento,
        acao_owner_id=None if alvo is None else alvo.owner_customer_id,
        acao_id=None if alvo is None else alvo.id,
        semantica=None if alvo is None else alvo.semantica,
        regra_de_valor=regra_de_valor or regra_sem_valor(),
        janela=janela or janela_nao_declarada(),
        fonte_do_sinal=fonte_do_plano(plano),
        consentimento=(consentimento if consentimento is not None
                       else consentimento_do_plano(plano)),
        causa_sem_acao=(None if alvo is not None
                        else (plano.acao_alvo_causa or
                              "nenhuma ação de conversão foi eleita para esta "
                              "campanha.")),
    )
