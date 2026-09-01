"""O plano canônico de mensuração — decidido ANTES de a campanha nascer.

## O fato que obriga este módulo a existir

Não é uma preocupação abstrata. Em 01/09/2026, a campanha 24195821946 (Portal
Mundo Mais) nasceu com `goal_config_level=CUSTOMER` — herdando as metas da
conta — e o ÚNICO `campaign_conversion_goal` com `biddable=true` era
DOWNLOAD/APP, enquanto a conta declarava oito ações primárias de PURCHASE.

Em `MANUAL_CPC` isso não muda o lance e ninguém percebe. Sob qualquer Smart
Bidding, a campanha otimizaria para um objetivo que ninguém escolheu — e
otimizar para o objetivo ERRADO é pior que otimizar para nada, porque parece
funcionar: as conversões sobem, só que são as conversões de outra coisa.

Uma campanha que nasce sem plano de mensuração declarado é uma campanha que
ninguém consegue ativar com segurança depois. O plano precisa dizer, ANTES do
nascimento, **qual ação a campanha persegue, de quem é essa ação, por onde o
sinal chega e quão fresco ele é** — e precisa impedir ativação e Smart Bidding
enquanto isso não estiver provado.

## O que este módulo NÃO faz

Não fala com o Google, não abre cliente, não emite GAQL e não escreve no
Supabase. Ele é o VOCABULÁRIO e as REGRAS; quem lê é `metas_efetivas.py`, quem
grava é `persistencia.py`. A separação é a mesma de `contrato_canais.py`: o que
não foi observado chega ausente e sai dizendo que não foi observado.

⚠️ **E ele nunca cria ConversionAction.** Nem por nicho, nem por campanha, nem
"porque não achou nenhuma". A `ConversionAction` é o objeto que o Data Manager
usa como destino e que o lance usa como alvo: criá-la automaticamente
espalharia ações órfãs por conta de cliente, cada uma com 14 dias de período de
teste em que a conversão aparece no relatório e **não** é usada para lance. O
que este módulo faz é PROPOR — e a proposta nasce `Secondary`.

## Os sete estados de uma leitura, e por que sete

    nao_coletado      ninguém pediu este dado. É `null`, e não é zero
    com_dados         pedimos, leu, e veio coisa
    vazio_confirmado  pedimos, leu, e a resposta é ZERO. Zero medido é um fato
    parcial           leu alguma coisa verdadeira, e não o bastante para decidir
    inelegivel        a pergunta não cabe NESTE recurso agora (ex.: campanha que
                      ainda não existe não tem `campaign_conversion_goal`)
    nao_suportado     a API não oferece este dado
    falhou            pedimos, e a leitura quebrou

⚠️ Colapsar `nao_coletado` em `vazio_confirmado` faria uma leitura que ninguém
fez parecer uma conta sem meta — e as duas levam a decisões opostas: uma pede
uma leitura, a outra pede que alguém configure a conta. Colapsar `falhou` em
`vazio_confirmado` é a mesma mentira com a rede como álibi.

Os seis últimos são LITERALMENTE os de `volc_ads.inteligencia_google.modelo
.EstadoColeta` — mesma grafia, mesmos valores — porque descrevem a mesma coisa
em duas camadas, e duas grafias divergiriam no primeiro estado novo. Há um
teste que quebra se elas divergirem.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ═══════════════════════════════════════════════════════════════════════════
# ESTADOS DE LEITURA
# ═══════════════════════════════════════════════════════════════════════════

#: ⚠️ `null`. Ninguém pediu. NÃO é zero, NÃO é vazio e NÃO é falha.
NAO_COLETADO = "nao_coletado"
COM_DADOS = "com_dados"
#: Zero MEDIDO. A leitura aconteceu e a resposta é "não há nenhum".
VAZIO_CONFIRMADO = "vazio_confirmado"
PARCIAL = "parcial"
#: A pergunta não cabe neste recurso agora — e caberá depois.
INELEGIVEL = "inelegivel"
NAO_SUPORTADO = "nao_suportado"
FALHOU = "falhou"

ESTADOS_DE_LEITURA: Tuple[str, ...] = (
    NAO_COLETADO, COM_DADOS, VAZIO_CONFIRMADO, PARCIAL,
    INELEGIVEL, NAO_SUPORTADO, FALHOU,
)

#: Os estados em que NÃO se pode concluir nada sobre o mundo a partir da lista
#: devolvida. `vazio_confirmado` fica de fora de propósito: ele é conclusão.
ESTADOS_SEM_CONCLUSAO: Tuple[str, ...] = (
    NAO_COLETADO, INELEGIVEL, NAO_SUPORTADO, FALHOU,
)

# ═══════════════════════════════════════════════════════════════════════════
# NÍVEL DA META — `conversion_goal_campaign_config.goal_config_level`
# ═══════════════════════════════════════════════════════════════════════════
#
# Provado contra os descritores reais do SDK v25 em 01/09/2026:
#     GoalConfigLevel = UNSPECIFIED | UNKNOWN | CUSTOMER | CAMPAIGN
#
# ⚠️ `UNSPECIFIED` e `UNKNOWN` EXISTEM e não são `CUSTOMER`. Tratá-los como
# herança da conta — que seria o palpite confortável, porque é o caso comum —
# afirmaria uma herança que a API não declarou. Eles viram `nivel_conhecido =
# False`, e o plano fica sem meta efetiva resolvida.

NIVEL_CUSTOMER = "CUSTOMER"
NIVEL_CAMPAIGN = "CAMPAIGN"
NIVEL_NAO_ESPECIFICADO = "UNSPECIFIED"
NIVEL_DESCONHECIDO = "UNKNOWN"

NIVEIS: Tuple[str, ...] = (
    NIVEL_CUSTOMER, NIVEL_CAMPAIGN, NIVEL_NAO_ESPECIFICADO, NIVEL_DESCONHECIDO,
)

#: Os únicos dois níveis que dizem QUEM manda. Os outros dois dizem que a
#: pergunta não foi respondida.
NIVEIS_DECIDIDOS: Tuple[str, ...] = (NIVEL_CUSTOMER, NIVEL_CAMPAIGN)

# ═══════════════════════════════════════════════════════════════════════════
# DESTINOS DE DATA MANAGER
# ═══════════════════════════════════════════════════════════════════════════
#
# Os tipos de `ConversionAction` que a Data Manager API aceita como destino.
# Fora desta lista, o `productDestinationId` é recusado — e recusado LÁ, depois
# de o evento ter saído daqui. Recusar aqui é mais barato e diz por quê.

TIPOS_DE_DESTINO_ACEITOS: Tuple[str, ...] = (
    "WEBPAGE",       # multi-source (tag do Google + enhanced conversions)
    "UPLOAD_CLICKS", # offline / enhanced conversions for leads
    "STORE_SALES",
)

# ═══════════════════════════════════════════════════════════════════════════
# SEMÂNTICA DE EVENTO — como uma ação canônica é reencontrada
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ POR SEMÂNTICA, E NUNCA POR NICHO OU CAMPANHA.
#
# A tentação é óbvia e errada: "cada nicho tem a sua ação de compra". Isso
# produz N ações PURCHASE na mesma conta, cada uma com o seu período de teste
# de 14 dias, cada uma competindo pela mesma meta de conta, e nenhuma com massa
# de conversão suficiente para o lance aprender. A identidade de uma ação de
# conversão é o EVENTO que ela mede — `(category, origin)` —, não o produto que
# ela vendeu nem a campanha que a gerou.


def chave_semantica(categoria: str, origem: str) -> str:
    """A identidade de um evento: categoria + origem, e nada mais.

    ⚠️ Nome NÃO entra. Nome é rótulo humano, muda sem aviso, chega traduzido e
    já provou não ser identidade: o aceite desta tarefa exige, com todas as
    letras, que o destino seja resolvido por dono + id numérico e "nunca por
    nome". Usar nome como chave de reuso reintroduziria a mesma falha um degrau
    antes.
    """
    return f"{str(categoria or '').strip().upper()}/{str(origem or '').strip().upper()}"


# ═══════════════════════════════════════════════════════════════════════════
# UMA META
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Meta:
    """Uma meta de conversão — de conta ou de campanha, mesma forma.

    Provado contra o SDK v25: `CustomerConversionGoal` tem exatamente
    `(resource_name, category, origin, biddable)` e `CampaignConversionGoal`
    tem os mesmos mais `campaign`. Não há mais campo nenhum, e inventar um aqui
    criaria um contrato que a API não sustenta.

    ⚠️ `biddable` NÃO tem presence no proto. Isso significa que, no nível do
    protobuf, `False` e "não veio" são indistinguíveis — e por isso a distinção
    é carregada pelo ESTADO da leitura que produziu esta lista, nunca por este
    campo. Um `biddable=False` daqui é sempre um falso MEDIDO.
    """

    categoria: str
    origem: str
    biddable: bool
    #: Presente só nas metas de campanha. `None` no nível de conta — e isso é
    #: um fato do recurso, não uma lacuna: `CustomerConversionGoal` não tem
    #: campo `campaign`.
    campaign: Optional[str] = None

    def __post_init__(self) -> None:
        if not str(self.categoria or "").strip():
            raise ValueError("meta sem categoria não é meta")
        if not str(self.origem or "").strip():
            raise ValueError("meta sem origem não é meta")

    @property
    def semantica(self) -> str:
        return chave_semantica(self.categoria, self.origem)

    def json(self) -> Dict[str, Any]:
        return {
            "categoria": self.categoria,
            "origem": self.origem,
            "biddable": self.biddable,
            "campaign": self.campaign,
            "semantica": self.semantica,
        }


# ═══════════════════════════════════════════════════════════════════════════
# UMA AÇÃO DE CONVERSÃO — com DONO
# ═══════════════════════════════════════════════════════════════════════════


def customer_id_do_recurso(resource_name: Optional[str]) -> Optional[str]:
    """`customers/1234567890/...` → `1234567890`.

    ⚠️ `None` quando não dá para extrair, e NUNCA string vazia. Um `""` viajando
    como owner produziria um `Destination` sintaticamente válido apontando para
    conta nenhuma — e a Data Manager só recusaria isso depois de o evento sair.
    """
    texto = str(resource_name or "").strip()
    if not texto.startswith("customers/"):
        return None
    resto = texto[len("customers/"):]
    numero = resto.split("/", 1)[0].strip()
    return numero if numero.isdigit() else None


@dataclass(frozen=True)
class AcaoDeConversao:
    """A identidade COMPLETA de uma `ConversionAction`.

    ## Por que `owner_customer_id` está aqui, e não é opcional de verdade

    A Data Manager exige que a operating account seja a conta que **possui** a
    conversion action, e o `productDestinationId` é o ID NUMÉRICO dela. Numa
    hierarquia de MCC com conversion tracking centralizado, a conta que RODA a
    campanha e a conta que POSSUI a ação são diferentes — e mandar o evento
    para a conta errada não dá erro de permissão: dá silêncio, e a conversão
    não chega em lugar nenhum.

    ⚠️ `primaria` é `Optional[bool]` e os TRÊS valores importam.
    `primary_for_goal` tem *presence* no proto v25 (provado contra o descritor
    real em 01/09/2026): ele pode vir ausente. E a doc oficial diz que **ausente
    vale `true`**. Ler isso com `bool(a.primary_for_goal)` — que é o que o
    código anterior fazia — devolve `False` para uma ação que o Google trata
    como primária, ou seja, o veredito EXATAMENTE invertido no caso que mais
    importa. Aqui `None` significa "não declarado", e quem aplica o default
    documentado é `primaria_efetiva`, que diz que está aplicando.
    """

    #: O id NUMÉRICO, como texto. É ele que vira `productDestinationId`.
    id: str
    resource_name: str
    #: Extraído de `conversion_action.owner_customer`. `None` = não lido.
    owner_customer_id: Optional[str]
    nome: str
    categoria: str
    origem: str
    tipo: str
    status: str
    #: ⚠️ TRI-ESTADO. `None` = o campo não veio. Ver `primaria_efetiva`.
    primaria: Optional[bool] = None
    #: Depreciado em favor de `primary_for_goal`, e ainda PRESENTE em v25.
    #: Ler os dois e não colapsá-los: uma conta antiga pode ter os dois
    #: discordando, e a discordância é informação.
    incluida_em_metricas: Optional[bool] = None

    def __post_init__(self) -> None:
        if not str(self.id or "").strip().isdigit():
            raise ValueError(
                "ação de conversão sem id numérico não é endereçável: o "
                "destino do Data Manager é o ID, nunca o nome")
        if not str(self.resource_name or "").strip():
            raise ValueError("ação de conversão sem resource_name")

    @property
    def primaria_efetiva(self) -> bool:
        """O default documentado, aplicado ONDE ele é dito em voz alta.

        > "By default, `primary_for_goal` will be true if not set."

        Esta propriedade existe separada de `primaria` para que ninguém
        confunda "o Google trata como primária" com "a API declarou primária".
        A primeira decide o lance; a segunda é o que se leu.
        """
        return True if self.primaria is None else bool(self.primaria)

    @property
    def semantica(self) -> str:
        return chave_semantica(self.categoria, self.origem)

    @property
    def aceita_como_destino(self) -> bool:
        return str(self.tipo or "").strip().upper() in TIPOS_DE_DESTINO_ACEITOS

    def json(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "resource_name": self.resource_name,
            "owner_customer_id": self.owner_customer_id,
            "nome": self.nome,
            "categoria": self.categoria,
            "origem": self.origem,
            "tipo": self.tipo,
            "status": self.status,
            "primaria": self.primaria,
            "primaria_efetiva": self.primaria_efetiva,
            "incluida_em_metricas": self.incluida_em_metricas,
            "semantica": self.semantica,
            "aceita_como_destino": self.aceita_como_destino,
        }


# ═══════════════════════════════════════════════════════════════════════════
# O DESTINO DE DATA MANAGER
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class DestinoDataManager:
    """Para onde uma conversão offline iria — resolvido por DONO + ID numérico.

    ⚠️ NUNCA por nome. O aceite desta tarefa é literal nisso, e o motivo é
    operacional: nome de ação de conversão se repete entre contas, é editável
    no painel sem aviso e chega traduzido. Um destino resolvido por nome erra
    de conta no dia em que alguém renomeia — e erra em silêncio.

    `resolvido=False` NÃO é falha: é a resposta honesta quando falta o dono, o
    id, ou o tipo não é aceito. Ele carrega a causa e nada é enviado.
    """

    resolvido: bool
    #: A conta que POSSUI a ação — não a que roda a campanha.
    operating_account_id: Optional[str] = None
    #: O id NUMÉRICO da `ConversionAction`.
    product_destination_id: Optional[str] = None
    conversion_action_resource: Optional[str] = None
    tipo_da_acao: Optional[str] = None
    causa: Optional[str] = None

    def __post_init__(self) -> None:
        if self.resolvido:
            if not self.operating_account_id:
                raise ValueError(
                    "destino resolvido sem conta dona: a Data Manager exige "
                    "que a operating account seja quem possui a ação")
            if not str(self.product_destination_id or "").isdigit():
                raise ValueError(
                    "destino resolvido sem id numérico: `productDestinationId` "
                    "é o ID da ConversionAction, nunca o nome")
        elif not str(self.causa or "").strip():
            raise ValueError("destino não resolvido sem causa nomeada")

    def json(self) -> Dict[str, Any]:
        return {
            "resolvido": self.resolvido,
            "operating_account_id": self.operating_account_id,
            "product_destination_id": self.product_destination_id,
            "conversion_action_resource": self.conversion_action_resource,
            "tipo_da_acao": self.tipo_da_acao,
            "causa": self.causa,
        }


def resolver_destino(acao: Optional[AcaoDeConversao]) -> DestinoDataManager:
    """O destino de Data Manager de uma ação — ou a razão de não haver um."""
    if acao is None:
        return DestinoDataManager(
            resolvido=False,
            causa=("nenhuma ação de conversão foi eleita para esta campanha, "
                   "e sem ação eleita não há destino para conversão offline."))
    if not acao.owner_customer_id:
        return DestinoDataManager(
            resolvido=False,
            conversion_action_resource=acao.resource_name,
            tipo_da_acao=acao.tipo,
            causa=("não se leu de qual conta esta ação de conversão é. A "
                   "conversão offline precisa ser enviada para a conta DONA da "
                   "ação, e enviá-la para a conta errada não dá erro: dá "
                   "silêncio."))
    if not acao.aceita_como_destino:
        return DestinoDataManager(
            resolvido=False,
            operating_account_id=acao.owner_customer_id,
            conversion_action_resource=acao.resource_name,
            tipo_da_acao=acao.tipo,
            causa=(f"a ação eleita é do tipo {acao.tipo}, e a ingestão offline "
                   f"só aceita "
                   f"{', '.join(TIPOS_DE_DESTINO_ACEITOS)} como destino."))
    return DestinoDataManager(
        resolvido=True,
        operating_account_id=acao.owner_customer_id,
        product_destination_id=acao.id,
        conversion_action_resource=acao.resource_name,
        tipo_da_acao=acao.tipo,
    )


# ═══════════════════════════════════════════════════════════════════════════
# A META EFETIVA — duas leituras e um nível
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MetaEfetiva:
    """Qual meta esta campanha EFETIVAMENTE persegue.

    ⚠️ Não existe um recurso único "effective goals". São DUAS leituras
    (`customer_conversion_goal` e `campaign_conversion_goal`) mais um terceiro
    recurso que diz qual delas manda (`conversion_goal_campaign_config
    .goal_config_level`). Resolver com uma só é o defeito que esta tarefa
    existe para consertar: a leitura anterior era sobre `conversion_action`,
    que não é nenhuma das três.

    ⚠️ E o nível governa. Com `goal_config_level=CUSTOMER`, as metas da
    campanha existem no recurso e NÃO decidem — foi exatamente esse o caso
    medido na 24195821946.
    """

    nivel: Optional[str]
    nivel_estado: str
    metas_da_conta: Tuple[Meta, ...]
    metas_da_conta_estado: str
    metas_da_campanha: Tuple[Meta, ...]
    metas_da_campanha_estado: str
    campaign_id: Optional[str] = None
    #: `conversion_goal_campaign_config.custom_conversion_goal` — o resource
    #: name de uma meta CUSTOMIZADA, quando a campanha usa uma.
    #:
    #: ⚠️ Quando isto vem preenchido, as duas listas acima param de decidir, e a
    #: doc oficial diz por quê: "custom conversion goals do **not** respect
    #: `primary_for_goal`". A meta efetiva passa a morar num terceiro recurso
    #: (`custom_conversion_goal`), que esta entrega NÃO lê. Concluir a partir
    #: das listas com um custom goal ativo daria uma resposta confiante e
    #: errada — que é pior que `não sei`.
    custom_conversion_goal: Optional[str] = None
    causa: Optional[str] = None

    def __post_init__(self) -> None:
        for nome in ("nivel_estado", "metas_da_conta_estado",
                     "metas_da_campanha_estado"):
            valor = getattr(self, nome)
            if valor not in ESTADOS_DE_LEITURA:
                raise ValueError(f"{nome}={valor!r} não é estado de leitura")
        if self.nivel is not None and self.nivel not in NIVEIS:
            raise ValueError(f"nível {self.nivel!r} não existe no enum v25")
        if self.nivel_estado == COM_DADOS and self.nivel is None:
            raise ValueError(
                "nível lido com dados e ausente ao mesmo tempo")

    @property
    def nivel_decidido(self) -> bool:
        """O nível diz quem manda? `UNSPECIFIED` e `UNKNOWN` NÃO dizem."""
        return self.nivel in NIVEIS_DECIDIDOS

    @property
    def usa_meta_customizada(self) -> bool:
        return bool(str(self.custom_conversion_goal or "").strip())

    @property
    def metas_que_mandam(self) -> Optional[Tuple[Meta, ...]]:
        """As metas do nível que governa — ou `None` se ninguém sabe qual é.

        ⚠️ `None`, e não `()`. Uma tupla vazia significaria "o nível manda e não
        há meta nenhuma", que é uma conclusão sobre a conta. Não saber qual
        nível manda não autoriza conclusão nenhuma.
        """
        if not self.nivel_decidido:
            return None
        # ⚠️ Meta customizada tira as duas listas do comando. Devolver a lista
        # do nível aqui seria devolver a resposta de outra pergunta com a cara
        # da resposta certa.
        if self.usa_meta_customizada:
            return None
        if self.nivel == NIVEL_CAMPAIGN:
            if self.metas_da_campanha_estado in ESTADOS_SEM_CONCLUSAO:
                return None
            return self.metas_da_campanha
        if self.metas_da_conta_estado in ESTADOS_SEM_CONCLUSAO:
            return None
        return self.metas_da_conta

    @property
    def metas_biddable(self) -> Optional[Tuple[Meta, ...]]:
        """As metas que o lance de fato persegue. `None` = não se sabe."""
        mandam = self.metas_que_mandam
        if mandam is None:
            return None
        return tuple(m for m in mandam if m.biddable)

    @property
    def resolvida(self) -> bool:
        """Sabemos, com prova, qual objetivo a campanha persegue?

        Exige nível decidido E ao menos uma meta `biddable` no nível que manda.
        ⚠️ Nenhum ramo aqui devolve `True` por ausência de contradição.
        """
        biddable = self.metas_biddable
        return bool(biddable)

    def json(self) -> Dict[str, Any]:
        biddable = self.metas_biddable
        mandam = self.metas_que_mandam
        return {
            "nivel": self.nivel,
            "nivel_estado": self.nivel_estado,
            "nivel_decidido": self.nivel_decidido,
            "custom_conversion_goal": self.custom_conversion_goal,
            "usa_meta_customizada": self.usa_meta_customizada,
            "campaign_id": self.campaign_id,
            "metas_da_conta": [m.json() for m in self.metas_da_conta],
            "metas_da_conta_estado": self.metas_da_conta_estado,
            "metas_da_campanha": [m.json() for m in self.metas_da_campanha],
            "metas_da_campanha_estado": self.metas_da_campanha_estado,
            # ⚠️ `null` sobrevive à fronteira HTTP: "não sei qual nível manda" e
            # "o nível manda e a lista é vazia" chegam diferentes na tela.
            "metas_que_mandam": (None if mandam is None
                                 else [m.json() for m in mandam]),
            "metas_biddable": (None if biddable is None
                               else [m.json() for m in biddable]),
            "resolvida": self.resolvida,
            "causa": self.causa,
        }


def meta_efetiva_nao_lida(causa: Optional[str] = None) -> MetaEfetiva:
    """O padrão de ignorância: ninguém leu nada, e a resposta diz isso."""
    return MetaEfetiva(
        nivel=None,
        nivel_estado=NAO_COLETADO,
        metas_da_conta=(),
        metas_da_conta_estado=NAO_COLETADO,
        metas_da_campanha=(),
        metas_da_campanha_estado=NAO_COLETADO,
        causa=(causa or
               "as metas efetivas não foram lidas nesta sessão. Ausência de "
               "leitura não é ausência de meta."),
    )


# ═══════════════════════════════════════════════════════════════════════════
# FRESCOR DO SINAL
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Frescor:
    """Quão recente é a última conversão que chegou — e para qual ação.

    ⚠️ `conversoes_na_janela=0` com `estado=vazio_confirmado` é um FATO caro e
    útil: a ação existe, a janela foi consultada e nada chegou. É diferente de
    `nao_coletado` (ninguém perguntou) e de `falhou` (perguntou e quebrou), e as
    três levam a ações diferentes — configurar, medir, ou consertar a leitura.

    ⚠️ `dias_desde_a_ultima=None` NUNCA vira um número grande. "Faz muito tempo"
    e "não sei" são coisas diferentes, e um `999` no lugar de `null` viraria um
    gráfico com cara de dado.
    """

    estado: str
    #: A janela consultada, QUANDO a leitura é de janela. ⚠️ Hoje ela é sempre
    #: `None`, e isso é honesto: o frescor vem de
    #: `metrics.conversion_last_conversion_date`, que é a data da última
    #: conversão e NÃO uma contagem de período. Um `30` aqui afirmaria um
    #: recorte que ninguém aplicou — e faria a tela dizer "nos últimos 30 dias"
    #: sobre um número que não tem 30 dias nenhum por trás.
    janela_dias: Optional[int] = None
    ultima_conversao_em: Optional[str] = None
    dias_desde_a_ultima: Optional[int] = None
    conversoes_na_janela: Optional[float] = None
    #: A ação a que este frescor se refere. Frescor sem sujeito não decide nada.
    conversion_action_id: Optional[str] = None
    causa: Optional[str] = None

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS_DE_LEITURA:
            raise ValueError(f"estado {self.estado!r} não é estado de leitura")
        if self.estado in ESTADOS_SEM_CONCLUSAO and self.conversoes_na_janela is not None:
            raise ValueError(
                "leitura sem conclusão não pode carregar contagem: seria um "
                "número inventado com cara de medição")
        if self.estado == VAZIO_CONFIRMADO and self.ultima_conversao_em:
            raise ValueError(
                "vazio confirmado com data de última conversão é contradição")
        if self.estado in ESTADOS_SEM_CONCLUSAO and not str(self.causa or "").strip():
            raise ValueError("leitura sem conclusão precisa dizer por quê")

    @property
    def comprovado(self) -> bool:
        """Chegou conversão de verdade nesta janela?

        ⚠️ Exige `com_dados` E contagem positiva. `vazio_confirmado` é uma
        conclusão válida e é justamente a conclusão de que NÃO chegou.
        """
        return (self.estado == COM_DADOS
                and (self.conversoes_na_janela or 0) > 0)

    def json(self) -> Dict[str, Any]:
        return {
            "estado": self.estado,
            "janela_dias": self.janela_dias,
            "ultima_conversao_em": self.ultima_conversao_em,
            "dias_desde_a_ultima": self.dias_desde_a_ultima,
            "conversoes_na_janela": self.conversoes_na_janela,
            "conversion_action_id": self.conversion_action_id,
            "comprovado": self.comprovado,
            "causa": self.causa,
        }


def frescor_nao_lido(causa: Optional[str] = None) -> Frescor:
    return Frescor(
        estado=NAO_COLETADO,
        causa=(causa or
               "o frescor do sinal não foi consultado nesta sessão. Não saber "
               "quando chegou a última conversão não é o mesmo que não ter "
               "chegado nenhuma."),
    )


# ═══════════════════════════════════════════════════════════════════════════
# INVENTÁRIO DE MARCAÇÃO — auto-tagging, click ids, GA4/GTM e consentimento
# ═══════════════════════════════════════════════════════════════════════════

#: Os identificadores de clique que a Data Manager aceita em `adIdentifiers`.
#: Três, e cada um cobre um caminho diferente: `gclid` é o clássico, `gbraid` e
#: `wbraid` são os de iOS com privacidade — um para app, outro para web.
CLICK_IDS: Tuple[str, ...] = ("gclid", "gbraid", "wbraid")


@dataclass(frozen=True)
class InventarioDeMarcacao:
    """Por onde o sinal PODE chegar nesta conta — inventariado, não presumido.

    ⚠️ Cada campo é tri-estado (`None` = não lido) porque a conclusão muda com
    a ignorância: uma conta com `auto_tagging_enabled=None` não é uma conta sem
    auto-tagging; é uma conta que ninguém leu. `marcacao.py` já recusa
    `marcacao_gclid=True` quando o auto-tagging está LIGADO — e uma leitura
    ausente lida como `False` faria essa recusa deixar de acontecer.
    """

    estado: str
    auto_tagging: Optional[bool] = None
    #: `customer.conversion_tracking_setting.conversion_tracking_id`
    conversion_tracking_id: Optional[str] = None
    #: ⚠️ QUEM é o dono do tracking. Numa hierarquia com tracking centralizado,
    #: é este customer que possui as ações — e não o que roda a campanha.
    conversion_tracking_owner_id: Optional[str] = None
    cross_account_conversion_tracking_id: Optional[str] = None
    conversion_tracking_status: Optional[str] = None
    #: `accepted_customer_data_terms` — o consentimento de dados do cliente,
    #: que é pré-requisito de enhanced conversions e de upload de user data.
    aceitou_termos_de_dados: Optional[bool] = None
    enhanced_conversions_for_leads: Optional[bool] = None
    #: Ids das ações cujo `type` vem do Google Analytics 4, Firebase ou
    #: analytics de terceiro. Presença aqui é evidência de IMPORTAÇÃO — uma
    #: fonte de sinal que não depende de tag nossa.
    acoes_de_ga4: Tuple[str, ...] = ()
    #: Ids das ações cujo `type` é de página (`WEBPAGE`, `WEBPAGE_CODELESS`):
    #: evidência de tag do Google no site, que é o caminho de GTM.
    #:
    #: ⚠️ Derivado de `type`, e NÃO de `conversion_action.tag_snippets`. O
    #: segundo seria a evidência mais direta e é uma mensagem repetida cuja
    #: seletividade em GAQL não foi provada nesta entrega — e um campo não
    #: provado derruba a consulta inteira, na conta do cliente, em produção.
    acoes_com_tag: Tuple[str, ...] = ()
    click_ids_suportados: Tuple[str, ...] = CLICK_IDS
    causa: Optional[str] = None

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS_DE_LEITURA:
            raise ValueError(f"estado {self.estado!r} não é estado de leitura")
        for c in self.click_ids_suportados:
            if c not in CLICK_IDS:
                raise ValueError(f"click id {c!r} não existe no contrato")

    def json(self) -> Dict[str, Any]:
        return {
            "estado": self.estado,
            "auto_tagging": self.auto_tagging,
            "conversion_tracking_id": self.conversion_tracking_id,
            "conversion_tracking_owner_id": self.conversion_tracking_owner_id,
            "cross_account_conversion_tracking_id":
                self.cross_account_conversion_tracking_id,
            "conversion_tracking_status": self.conversion_tracking_status,
            "aceitou_termos_de_dados": self.aceitou_termos_de_dados,
            "enhanced_conversions_for_leads": self.enhanced_conversions_for_leads,
            "acoes_de_ga4": list(self.acoes_de_ga4),
            "acoes_com_tag": list(self.acoes_com_tag),
            "click_ids_suportados": list(self.click_ids_suportados),
            "causa": self.causa,
        }


def inventario_nao_lido(causa: Optional[str] = None) -> InventarioDeMarcacao:
    return InventarioDeMarcacao(
        estado=NAO_COLETADO,
        causa=(causa or
               "a marcação da conta — auto-tagging, tracking, GA4 e "
               "consentimento — não foi inventariada nesta sessão."),
    )


# ═══════════════════════════════════════════════════════════════════════════
# A REGRA QUE NÃO SE DOBRA: NENHUMA AÇÃO É CRIADA AUTOMATICAMENTE
# ═══════════════════════════════════════════════════════════════════════════

CODIGO_CRIACAO_RECUSADA = "criacao_de_acao_recusada"

_POR_QUE_NAO_CRIAMOS = (
    "criar ação de conversão automaticamente por nicho ou por campanha "
    "espalharia ações órfãs pela conta do cliente, cada uma com o seu período "
    "de teste de 14 dias em que a conversão aparece no relatório e não é usada "
    "para lance, e nenhuma com massa suficiente para o lance aprender. A ação "
    "canônica é reencontrada pela semântica do evento; criar uma nova é um ato "
    "separado, com aprovação explícita.")


class CriacaoDeAcaoRecusada(RuntimeError):
    """Levantada quando alguém tenta criar ação de conversão por aqui.

    ⚠️ Uma exceção, e não um `return None` — porque `None` seria absorvido pelo
    caminho normal de "não achei ação" e a tentativa passaria despercebida. A
    recusa precisa ser barulhenta: ela é uma das dez linhas de aceite desta
    tarefa, e o dia em que alguém a contornar não pode ser silencioso.
    """

    def __init__(self, motivo: str = "") -> None:
        self.motivo = motivo
        super().__init__(f"{_POR_QUE_NAO_CRIAMOS} {motivo}".strip())


@dataclass(frozen=True)
class PropostaDeAcaoNova:
    """Uma ação de conversão que alguém PODERIA criar — e que ninguém criou.

    ⚠️ `primary_for_goal` nasce `False` sempre. A doc oficial diz que o default
    da API é `true` quando o campo não é setado; uma ação nova entrando como
    primária mudaria o objetivo de TODA campanha da conta que herda as metas,
    no mesmo instante e sem ninguém decidir isso. Aqui ela nasce Secondary, e
    promovê-la é outro ato — com `aprovacao_explicita`.
    """

    categoria: str
    origem: str
    nome_sugerido: str
    tipo: str
    #: ⚠️ Sempre `False` sem aprovação separada. Ver `promover`.
    primary_for_goal: bool = False
    aprovacao_explicita: Optional[str] = None
    #: A ação é PROPOSTA. Nada foi enviado ao Google — e este campo existe para
    #: que a proposta nunca possa ser confundida com um recibo.
    criada: bool = False

    def __post_init__(self) -> None:
        if self.criada:
            raise CriacaoDeAcaoRecusada(
                "uma proposta nunca sai deste módulo marcada como criada.")
        if self.primary_for_goal and not str(self.aprovacao_explicita or "").strip():
            raise ValueError(
                "ação nova como primária exige aprovação explícita nomeada: "
                "promovê-la muda o objetivo de toda campanha da conta que "
                "herda as metas, no mesmo instante.")

    def promover(self, aprovacao: str) -> "PropostaDeAcaoNova":
        """A promoção a primária — um segundo ato, com nome de quem aprovou."""
        if not str(aprovacao or "").strip():
            raise ValueError("promoção sem aprovação nomeada não é aprovação")
        return PropostaDeAcaoNova(
            categoria=self.categoria,
            origem=self.origem,
            nome_sugerido=self.nome_sugerido,
            tipo=self.tipo,
            primary_for_goal=True,
            aprovacao_explicita=str(aprovacao).strip(),
        )

    def json(self) -> Dict[str, Any]:
        return {
            "categoria": self.categoria,
            "origem": self.origem,
            "nome_sugerido": self.nome_sugerido,
            "tipo": self.tipo,
            "primary_for_goal": self.primary_for_goal,
            "aprovacao_explicita": self.aprovacao_explicita,
            "criada": self.criada,
            "por_que_nao_criamos": _POR_QUE_NAO_CRIAMOS,
        }


def eleger_acao_canonica(
        acoes: Sequence[AcaoDeConversao],
        metas_biddable: Optional[Sequence[Meta]],
) -> Tuple[Optional[AcaoDeConversao], Optional[str]]:
    """Qual ação já existente esta campanha persegue — por SEMÂNTICA.

    Devolve `(acao, causa_de_nao_eleger)`. Exatamente um dos dois é `None`.

    ⚠️ A eleição casa a `(category, origin)` de uma meta `biddable` com a de uma
    ação `ENABLED`. Não usa nome, não usa nicho, não usa "a primeira da lista" e
    não cria nada. Quando nenhuma casa, a resposta é a causa — e a causa é
    acionável, porque diz qual semântica ficou sem dono.
    """
    if metas_biddable is None:
        return None, ("não se sabe qual meta esta campanha persegue, e sem isso "
                      "não há como dizer qual ação de conversão é a dela.")
    if not metas_biddable:
        return None, ("nenhuma meta de conversão desta campanha é biddable: em "
                      "lance automático ela otimizaria para nada.")
    habilitadas = [a for a in acoes if str(a.status or "").upper() == "ENABLED"]
    if not habilitadas:
        return None, ("a conta não tem ação de conversão habilitada. Uma "
                      "campanha em lance automático aprenderia do que não "
                      "existe.")
    alvo = {m.semantica for m in metas_biddable}
    candidatas = [a for a in habilitadas if a.semantica in alvo]
    if not candidatas:
        return None, (
            "nenhuma ação de conversão habilitada corresponde ao objetivo desta "
            "campanha (" + ", ".join(sorted(alvo)) + "). A ação que mede este "
            "evento não existe nesta conta, e criá-la é um ato separado.")
    # ⚠️ SÓ A PRIMÁRIA EFETIVA ELEGE. Não há fallback para "a primeira que
    # casou", e este é o ponto em que a primeira versão desta função estava
    # errada — ela caía em `primarias or candidatas`, o default otimista que
    # esta casa recusa.
    #
    # A doc oficial não deixa margem: "If a conversion action's
    # `primary_for_goal` bit is false, the conversion action is **non-biddable
    # for all campaigns regardless** of their customer conversion goal or
    # campaign conversion goal." Uma ação não-biddable eleita como alvo seria
    # um alvo que o lance NÃO persegue — o plano diria "medido por #X" e o
    # Google não estaria medindo nada por #X.
    #
    # Medido ao vivo em 01/09/2026 na Portal Mundo Mais: a única meta biddable
    # da conta é DOWNLOAD/APP, e a única ação com essa semântica
    # (#7498530235, ANDROID_INSTALLS_ALL_OTHER_APPS) tem
    # `primary_for_goal=false` DECLARADO. Com o fallback, o plano elegia essa
    # ação e saía dizendo que a mensuração estava resolvida. Sem ele, ele diz a
    # verdade: existe objetivo, e não existe ação biddable que o meça.
    primarias = [a for a in candidatas if a.primaria_efetiva]
    if not primarias:
        return None, (
            "o objetivo desta campanha (" + ", ".join(sorted(alvo)) + ") existe "
            "na conta, e a única ação que o mede está marcada como NÃO primária "
            "— o que a torna não-biddable em toda campanha, qualquer que seja a "
            "meta. Na prática o lance automático não teria o que perseguir.")
    # O desempate é o id numérico, que é estável: ordenar por nome faria a
    # eleição mudar quando alguém renomeasse a ação no painel.
    if len(primarias) > 1:
        return sorted(primarias, key=lambda a: int(a.id))[0], None
    return primarias[0], None


def propor_acao_nova(categoria: str, origem: str, *,
                     nome_sugerido: str,
                     tipo: str = "WEBPAGE") -> PropostaDeAcaoNova:
    """Uma PROPOSTA — nunca uma criação. Nasce Secondary, sempre."""
    return PropostaDeAcaoNova(
        categoria=str(categoria).strip().upper(),
        origem=str(origem).strip().upper(),
        nome_sugerido=str(nome_sugerido).strip(),
        tipo=str(tipo).strip().upper(),
        primary_for_goal=False,
    )


# ═══════════════════════════════════════════════════════════════════════════
# O PLANO
# ═══════════════════════════════════════════════════════════════════════════

#: A versão do CONTRATO do plano. Ela entra na impressão: um plano gravado sob
#: um contrato antigo não deve colidir com um gravado sob o novo só porque os
#: campos que mudaram não estavam na chave.
VERSAO_DO_PLANO = 1

@dataclass(frozen=True)
class PlanoDeMensuracao:
    """O plano canônico: o que a campanha persegue, de quem é, e por onde mede.

    Frozen porque ele vira resposta HTTP, entra no dossiê e é gravado com
    impressão. Um objeto mutável deixaria alguém "melhorar" um plano depois de
    ele ter sido apresentado — e a impressão deixaria de valer.

    ⚠️ `campaign_id=None` é o caso NORMAL: o plano existe ANTES do nascimento.
    Ele não deixa de ser um plano por a campanha não existir ainda; é
    justamente esse o ponto. O que muda com `campaign_id` é a meta de campanha
    poder ser lida — antes disso ela é `inelegivel`, e não `vazio_confirmado`.
    """

    customer_id: str
    login_customer_id: str
    meta_efetiva: MetaEfetiva
    acoes: Tuple[AcaoDeConversao, ...] = ()
    acoes_estado: str = NAO_COLETADO
    acao_alvo: Optional[AcaoDeConversao] = None
    acao_alvo_causa: Optional[str] = None
    destino: DestinoDataManager = field(
        default_factory=lambda: DestinoDataManager(
            resolvido=False,
            causa="o destino de conversão offline não foi resolvido."))
    frescor: Frescor = field(default_factory=frescor_nao_lido)
    marcacao: InventarioDeMarcacao = field(default_factory=inventario_nao_lido)
    campaign_id: Optional[str] = None
    #: A intenção que originou a campanha, quando há uma. Serve para reencontrar
    #: o plano depois — não para escolher meta.
    chave_intencao: Optional[str] = None
    proposta_de_acao: Optional[PropostaDeAcaoNova] = None
    versao: int = VERSAO_DO_PLANO

    def __post_init__(self) -> None:
        if not str(self.customer_id or "").strip().isdigit():
            raise ValueError("plano sem customer_id numérico")
        if not str(self.login_customer_id or "").strip().isdigit():
            raise ValueError("plano sem login_customer_id numérico")
        if self.acoes_estado not in ESTADOS_DE_LEITURA:
            raise ValueError(
                f"acoes_estado={self.acoes_estado!r} não é estado de leitura")
        if self.acao_alvo is not None and self.acao_alvo_causa:
            raise ValueError(
                "ação eleita e causa de não eleger ao mesmo tempo: a tela não "
                "teria como saber qual das duas é verdade")
        if self.acao_alvo is None and not str(self.acao_alvo_causa or "").strip():
            raise ValueError(
                "plano sem ação eleita e sem dizer por quê. Ignorância anônima "
                "é indistinguível de silêncio.")

    # ── o veredito ──────────────────────────────────────────────────────────

    @property
    def completo(self) -> bool:
        """O plano prova o que precisa provar para autorizar Smart Bidding?

        Exige as QUATRO coisas, e nenhuma delas é derivada de ausência:
        meta efetiva resolvida, ação eleita, destino com dono+id, e frescor
        comprovado. Faltando uma, o plano existe e não autoriza.
        """
        return bool(
            self.meta_efetiva.resolvida
            and self.acao_alvo is not None
            and self.destino.resolvido
            and self.frescor.comprovado
        )

    @property
    def bloqueadores(self) -> Tuple[str, ...]:
        """Por que este plano ainda não autoriza — em linguagem operacional.

        ⚠️ Todas as razões, e não só a primeira. Fechar uma não abre o portão, e
        uma lista que para na primeira faria o operador consertar uma coisa por
        vez sem nunca ver o tamanho do caminho.
        """
        razoes: List[str] = []
        if not self.meta_efetiva.nivel_decidido:
            razoes.append(
                "não se sabe se quem manda na meta desta campanha é a conta ou "
                "a própria campanha: o nível de configuração não foi lido, e "
                "sem ele as duas listas de meta são apenas listas.")
        elif self.meta_efetiva.usa_meta_customizada:
            razoes.append(
                "esta campanha usa uma meta de conversão CUSTOMIZADA. Uma meta "
                "customizada não segue a marcação de primária das ações, e o "
                "que ela persegue está declarado num recurso que este sistema "
                "ainda não lê. Concluir pelas metas de conta e de campanha "
                "daria uma resposta confiante e errada.")
        elif self.meta_efetiva.metas_biddable is None:
            razoes.append(
                "o nível que manda foi lido, e as metas desse nível não. Falta "
                "exatamente a metade que decide.")
        elif not self.meta_efetiva.metas_biddable:
            razoes.append(
                "nenhuma meta desta campanha é biddable. Em lance automático "
                "ela otimizaria para nada e gastaria o orçamento inteiro "
                "aprendendo o que ninguém mediu.")
        if self.acao_alvo is None:
            razoes.append(self.acao_alvo_causa or
                          "nenhuma ação de conversão foi eleita.")
        elif not self.destino.resolvido:
            razoes.append(self.destino.causa or
                          "o destino de conversão offline não foi resolvido.")
        if not self.frescor.comprovado:
            if self.frescor.estado == VAZIO_CONFIRMADO:
                razoes.append(
                    "a ação de conversão desta campanha não recebeu NENHUMA "
                    "conversão na janela consultada. O sinal existe como "
                    "configuração e não como fato.")
            elif self.frescor.estado in ESTADOS_SEM_CONCLUSAO:
                razoes.append(
                    "ninguém mediu quando chegou a última conversão desta "
                    "ação. Não saber não é o mesmo que não ter chegado — e as "
                    "duas pedem coisas diferentes.")
        return tuple(razoes)

    # ── identidade ──────────────────────────────────────────────────────────

    def impressao(self) -> str:
        """A impressão do plano — estável, e sobre o que DECIDE.

        ⚠️ Entram só os campos que mudam a decisão: conta, campanha, nível,
        metas que mandam, ação eleita e destino. Frescor NÃO entra: ele muda a
        cada hora sem que o plano tenha mudado, e incluí-lo faria cada leitura
        gravar um plano "novo" — o histórico viraria ruído e a idempotência
        deixaria de existir.
        """
        mandam = self.meta_efetiva.metas_que_mandam
        corpo = {
            "versao": self.versao,
            "customer_id": self.customer_id,
            "login_customer_id": self.login_customer_id,
            "campaign_id": self.campaign_id,
            "chave_intencao": self.chave_intencao,
            "nivel": self.meta_efetiva.nivel,
            "metas_que_mandam": (
                None if mandam is None
                else sorted(f"{m.semantica}:{'B' if m.biddable else 'N'}"
                            for m in mandam)),
            "acao_alvo": (None if self.acao_alvo is None else {
                "id": self.acao_alvo.id,
                "owner": self.acao_alvo.owner_customer_id,
            }),
            "destino": {
                "resolvido": self.destino.resolvido,
                "operating_account_id": self.destino.operating_account_id,
                "product_destination_id": self.destino.product_destination_id,
            },
        }
        canonico = json.dumps(corpo, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"))
        return hashlib.sha256(canonico.encode("utf-8")).hexdigest()

    def para_json(self) -> Dict[str, Any]:
        return {
            "versao": self.versao,
            "customer_id": self.customer_id,
            "login_customer_id": self.login_customer_id,
            "campaign_id": self.campaign_id,
            "chave_intencao": self.chave_intencao,
            "meta_efetiva": self.meta_efetiva.json(),
            "acoes": [a.json() for a in self.acoes],
            "acoes_estado": self.acoes_estado,
            "acao_alvo": None if self.acao_alvo is None else self.acao_alvo.json(),
            "acao_alvo_causa": self.acao_alvo_causa,
            "destino": self.destino.json(),
            "frescor": self.frescor.json(),
            "marcacao": self.marcacao.json(),
            "proposta_de_acao": (None if self.proposta_de_acao is None
                                 else self.proposta_de_acao.json()),
            "completo": self.completo,
            "bloqueadores": list(self.bloqueadores),
            "impressao": self.impressao(),
        }


def montar(
    *,
    customer_id: str,
    login_customer_id: str,
    meta_efetiva: Optional[MetaEfetiva] = None,
    acoes: Optional[Sequence[AcaoDeConversao]] = None,
    acoes_estado: str = NAO_COLETADO,
    frescor: Optional[Frescor] = None,
    marcacao: Optional[InventarioDeMarcacao] = None,
    campaign_id: Optional[str] = None,
    chave_intencao: Optional[str] = None,
) -> PlanoDeMensuracao:
    """O plano, montado do que foi REALMENTE observado — e nada além.

    ⚠️ Todo argumento do mundo é opcional e ausente por padrão. Ausência produz
    o estado de ignorância com causa, nunca um veredito. Este é o mesmo desenho
    de `contrato_canais.contrato`, e pelo mesmo motivo: um default otimista aqui
    seria uma afirmação sobre a conta a partir do que ninguém olhou.
    """
    metas = meta_efetiva or meta_efetiva_nao_lida()
    lista = tuple(acoes or ())
    if acoes_estado not in ESTADOS_DE_LEITURA:
        raise ValueError(f"acoes_estado={acoes_estado!r} não é estado de leitura")
    if acoes_estado in ESTADOS_SEM_CONCLUSAO and lista:
        raise ValueError(
            "leitura sem conclusão trazendo ações: o estado diz que não se "
            "pode concluir e a lista afirma o contrário")

    if acoes_estado in ESTADOS_SEM_CONCLUSAO:
        alvo, causa = None, (
            "as ações de conversão da conta não foram lidas nesta sessão, e "
            "sem elas não há como dizer qual é a desta campanha.")
    else:
        alvo, causa = eleger_acao_canonica(lista, metas.metas_biddable)

    return PlanoDeMensuracao(
        customer_id=str(customer_id).strip(),
        login_customer_id=str(login_customer_id).strip(),
        meta_efetiva=metas,
        acoes=lista,
        acoes_estado=acoes_estado,
        acao_alvo=alvo,
        acao_alvo_causa=causa,
        destino=resolver_destino(alvo),
        frescor=frescor or frescor_nao_lido(),
        marcacao=marcacao or inventario_nao_lido(),
        campaign_id=(str(campaign_id).strip() if campaign_id else None),
        chave_intencao=chave_intencao,
    )


def fontes_de_sinal_observadas(
        plano: PlanoDeMensuracao) -> Tuple[str, ...]:
    """As fontes de sinal que este plano COMPROVOU — nunca as que ele supõe.

    ⚠️ Lista vazia significa "nenhuma foi comprovada NESTA leitura", e não "a
    conta não tem nenhuma". É o mesmo contrato que `prontidao.avaliar` já impõe
    em `signal_sources`, e esta função existe para alimentá-lo com prova em vez
    de com um literal escrito à mão na rota.
    """
    fontes: List[str] = []
    if plano.frescor.comprovado:
        fontes.append("conversão observada na janela consultada")
    m = plano.marcacao
    if m.estado not in ESTADOS_SEM_CONCLUSAO:
        if m.acoes_com_tag:
            fontes.append("tag do Google no site")
        if m.acoes_de_ga4:
            fontes.append("importação do Google Analytics 4")
        if m.auto_tagging is True:
            fontes.append("auto-tagging ligado (gclid anexado pelo Google)")
    if plano.destino.resolvido:
        fontes.append("destino de conversão offline resolvido")
    return tuple(fontes)
