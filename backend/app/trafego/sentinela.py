"""A sentinela de entrega de Search — o veredito único, e o que ele AFIRMA.

## O defeito que este módulo conserta

Medido em 03/09/2026, contra o cenário real da conta Crédito Up, com o
diagnóstico persistido v12 exatamente como estava em `34dc7b4`:

    conta        nao_apurado   "A coleta v12 não trouxe evidência suficiente"
    campanha     ok            "ligada sem bloqueio nestes campos"
    keyword      ok            "A conta observou keyword habilitado"
    leilao       limita        "A conta mediu zero impressões nesta janela"

As duas keywords desse retrato tinham lance de R$ 0,50 contra uma estimativa de
primeira página de R$ 3,20 e Quality Score 3. Os três números estavam no
payload — `effective_cpc_bid_micros`, `position_estimates.first_page_cpc_micros`
e `quality_info.quality_score` são colhidos pelo coletor e atravessam a
allowlist de `diagnostico_persistido.CAMINHOS_ITEM` — e nenhum deles era LIDO.
O degrau saía `ok` porque `primary_status` dizia `ELIGIBLE`, que é verdade e não
é a pergunta: elegível quer dizer "pode ir a leilão", não "vai".

E o degrau `conta` saía `nao_apurado` não porque a leitura falhou, mas porque
não existia lugar nenhum onde `customer.status` pudesse ser guardado. A conta
estava suspensa, o sistema não tinha campo para isso, e o operador lia
"não foi possível apurar" — que soa como problema nosso — em vez de
"a conta está suspensa", que é o único fato que importava.

Este módulo é a resposta às oito perguntas do incidente:

  1. o que aconteceu?              → `status`
  2. em qual nível?                → `escopo`
  3. qual evidência sustenta?      → `evidencias`
  4. qual o frescor dela?          → `frescor` + `observado_em`
  5. qual causa tem prioridade?    → `causa_primaria`, por `PRECEDENCIA`
  6. qual próximo ato reversível?  → `proximo_ato`
  7. o que permanece desconhecido? → `desconhecidos`
  8. qual alerta já foi emitido?   → `Incidente`, por `consolidar()`

## O que este módulo NÃO faz

Nenhuma função daqui chama o Google Ads. Não há import de `volc_ads` nem de
`google.ads`, e `mutacao_externa` é um campo `False` constante no veredito —
declarado, e não presumido, porque "nada foi aplicado" é uma afirmação que o
operador precisa LER, não deduzir da ausência de um botão.

## Vocabulário: convertido, não duplicado

O projeto já tem a escada causal (`EIXOS` em `diagnostico_persistido`, e
`EixoDeEntrega` em `src/types/diagnostico.ts`) e já tem o vocabulário de
ausência (`nao_apurado`, `EstadoDaColeta`, `FrescorDoDiagnostico`). A sentinela
NÃO os substitui: ela lê os degraus que aquele contrato já produz e responde a
pergunta que ele não responde — *qual das causas manda, e o que fazer agora*.
`CONVERSAO_DO_EIXO` é o mapa explícito entre os dois vocabulários.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: Versão do contrato da sentinela. Sobe quando um consumidor precisa saber.
VERSAO_SENTINELA = 1


# ── escopos ─────────────────────────────────────────────────────────────────
#
# Em qual nível o fato foi observado. Não é organização: um problema de conta e
# um problema de keyword pedem ações em telas diferentes, por pessoas
# diferentes, e achatá-los num "campanha com problema" perde justamente a
# informação que decide quem age.

ESCOPO_CONTA = "account"
ESCOPO_CAMPANHA = "campaign"
ESCOPO_GRUPO = "ad_group"
ESCOPO_ANUNCIO = "ad"
ESCOPO_KEYWORD = "keyword"
ESCOPO_MEDICAO = "measurement"
ESCOPO_DESTINO = "destination"

ESCOPOS: Tuple[str, ...] = (
    ESCOPO_CONTA, ESCOPO_CAMPANHA, ESCOPO_GRUPO, ESCOPO_ANUNCIO,
    ESCOPO_KEYWORD, ESCOPO_MEDICAO, ESCOPO_DESTINO,
)


# ── estados ─────────────────────────────────────────────────────────────────

ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED"
ACCESS_UNAVAILABLE = "ACCESS_UNAVAILABLE"
POLICY_BLOCKED = "POLICY_BLOCKED"
POLICY_REVIEW = "POLICY_REVIEW"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
#: ⚠️ NÃO está na lista sugerida pela missão, e é necessário.
#:
#: "Campanha PAUSED com zero gasto não é falha" é uma regra invariante, e sem um
#: estado para ela a campanha desligada teria de sair `HEALTHY` (falso verde) ou
#: `NO_DELIVERY` (falso alarme). Os dois são erros que a missão proíbe pelo nome.
#: Este estado é a conversão direta do `campanha/bloqueia/desligada` que
#: `diagnostico_persistido._degraus_observados` já emite — vocabulário existente
#: promovido, não vocabulário novo inventado.
CAMPAIGN_OFF = "CAMPAIGN_OFF"
ADS_NOT_READY = "ADS_NOT_READY"
NO_DELIVERY = "NO_DELIVERY"
LIMITED_BY_BUDGET = "LIMITED_BY_BUDGET"
LIMITED_BY_RANK = "LIMITED_BY_RANK"
KEYWORD_STRUCTURE_RISK = "KEYWORD_STRUCTURE_RISK"
MEASUREMENT_NOT_READY = "MEASUREMENT_NOT_READY"
LOW_DEMAND = "LOW_DEMAND"
LEARNING = "LEARNING"
OBSERVING = "OBSERVING"
HEALTHY = "HEALTHY"

#: A ordem causal. Um diagnóstico inferior NUNCA esconde um superior.
#:
#: A regra que a lista codifica, degrau a degrau:
#:
#: · a conta vem antes de tudo — uma conta suspensa faz lance, orçamento e
#:   Quality Score virarem detalhe histórico. Foi exatamente esta linha que
#:   faltou no incidente Crédito Up;
#: · não poder ler vem antes de qualquer conclusão sobre o que foi lido
#:   (`DATA_UNAVAILABLE` acima de `NO_DELIVERY`): coleta velha com zero métricas
#:   é desconhecimento, não ausência de entrega;
#: · a campanha desligada vem antes dos degraus internos dela: sem campanha
#:   ligada, "sem anúncio apto" e "lance baixo" não explicam nada;
#: · `ADS_NOT_READY` vem antes de `NO_DELIVERY` e de qualquer coisa de lance:
#:   sem anúncio apto o leilão nem começa, e mandar mexer em lance ali é mandar
#:   consertar o telhado de uma casa sem parede;
#: · `OBSERVING` fica no fim porque ele é a AUSÊNCIA de conclusão madura, não
#:   uma conclusão; e `HEALTHY` é o último de todos, alcançável só quando
#:   nenhuma das quinze linhas acima disse alguma coisa.
PRECEDENCIA: Tuple[str, ...] = (
    ACCOUNT_BLOCKED,
    ACCESS_UNAVAILABLE,
    POLICY_BLOCKED,
    POLICY_REVIEW,
    DATA_UNAVAILABLE,
    CAMPAIGN_OFF,
    ADS_NOT_READY,
    NO_DELIVERY,
    LIMITED_BY_BUDGET,
    LIMITED_BY_RANK,
    KEYWORD_STRUCTURE_RISK,
    MEASUREMENT_NOT_READY,
    LOW_DEMAND,
    LEARNING,
    OBSERVING,
    HEALTHY,
)

#: Estados que afirmam que a operação precisa de alguém. `HEALTHY`, `OBSERVING`,
#: `LEARNING` e `CAMPAIGN_OFF` não são incidentes: os dois primeiros dizem que
#: ainda não há conclusão, o terceiro que a máquina está fazendo o que deve, e o
#: quarto que alguém desligou de propósito.
ESTADOS_DE_INCIDENTE: frozenset = frozenset({
    ACCOUNT_BLOCKED, ACCESS_UNAVAILABLE, POLICY_BLOCKED, POLICY_REVIEW,
    DATA_UNAVAILABLE, ADS_NOT_READY, NO_DELIVERY, LIMITED_BY_BUDGET,
    LIMITED_BY_RANK, KEYWORD_STRUCTURE_RISK, MEASUREMENT_NOT_READY, LOW_DEMAND,
})

SEV_CRITICA = "critica"
SEV_ALTA = "alta"
SEV_MEDIA = "media"
SEV_BAIXA = "baixa"
SEV_INFORMATIVA = "informativa"

SEVERIDADE: Dict[str, str] = {
    ACCOUNT_BLOCKED: SEV_CRITICA,
    ACCESS_UNAVAILABLE: SEV_CRITICA,
    POLICY_BLOCKED: SEV_CRITICA,
    #: ⚠️ Revisão em andamento NÃO é crítica e NÃO é aprovação. É a única
    #: severidade honesta para um veredito que o Google ainda não deu.
    POLICY_REVIEW: SEV_MEDIA,
    DATA_UNAVAILABLE: SEV_MEDIA,
    CAMPAIGN_OFF: SEV_INFORMATIVA,
    ADS_NOT_READY: SEV_ALTA,
    NO_DELIVERY: SEV_ALTA,
    LIMITED_BY_BUDGET: SEV_MEDIA,
    LIMITED_BY_RANK: SEV_MEDIA,
    KEYWORD_STRUCTURE_RISK: SEV_BAIXA,
    MEASUREMENT_NOT_READY: SEV_MEDIA,
    LOW_DEMAND: SEV_BAIXA,
    LEARNING: SEV_INFORMATIVA,
    OBSERVING: SEV_INFORMATIVA,
    HEALTHY: SEV_INFORMATIVA,
}

#: O mapa entre a escada existente e a sentinela. Documentado como dado para que
#: uma divergência entre os dois vocabulários seja visível em vez de implícita.
CONVERSAO_DO_EIXO: Dict[str, str] = {
    "conta": ESCOPO_CONTA,
    "campanha": ESCOPO_CAMPANHA,
    "orcamento": ESCOPO_CAMPANHA,
    "grupo": ESCOPO_GRUPO,
    "anuncio": ESCOPO_ANUNCIO,
    "keyword": ESCOPO_KEYWORD,
    "segmentacao": ESCOPO_CAMPANHA,
    "conversao": ESCOPO_MEDICAO,
    "leilao": ESCOPO_CAMPANHA,
}


def ordem_da_causa(status: str) -> int:
    """A posição causal de um status. Desconhecido vai para o FIM, nunca o topo.

    ⚠️ Ir para o fim e não para o topo é deliberado, e é o oposto do que a
    intuição pede: um status que esta versão não conhece não pode vencer um
    `ACCOUNT_BLOCKED` observado. Quem trata o desconhecido é `evidencia_dubia`,
    que rebaixa a leitura inteira para `DATA_UNAVAILABLE` — no lugar certo da
    ordem, e não por atalho aqui.
    """
    try:
        return PRECEDENCIA.index(status)
    except ValueError:
        return len(PRECEDENCIA)


def severidade_de(status: str) -> str:
    """A severidade de um status. Desconhecido nunca é `informativa`."""
    return SEVERIDADE.get(status, SEV_MEDIA)


# ── estados observados na conta de anúncio ──────────────────────────────────
#
# ⚠️ Listas ABERTAS pela borda certa. O enum do Google ganha valores, e a regra
# aqui é: o que reconhecemos como bloqueio bloqueia; o que reconhecemos como
# saudável só vale se for EXATAMENTE reconhecido; e o que não reconhecemos vira
# desconhecido, nunca verde. É a contraprova 18.

#: `customer.status` que impedem a conta inteira de veicular.
CONTA_BLOQUEADA: frozenset = frozenset({"SUSPENDED", "CANCELED", "CLOSED"})
#: O único `customer.status` que autoriza seguir a leitura.
CONTA_HABILITADA: frozenset = frozenset({"ENABLED"})

#: `campaign.status` que dizem "desligada por decisão", não "com problema".
CAMPANHA_DESLIGADA: frozenset = frozenset({"PAUSED", "REMOVED"})

#: `ad_group_ad.policy_summary.approval_status` reprovado.
ANUNCIO_REPROVADO: frozenset = frozenset({"DISAPPROVED"})
#: `review_status` que dizem "o Google ainda não decidiu".
ANUNCIO_EM_REVISAO: frozenset = frozenset({
    "REVIEW_IN_PROGRESS", "UNDER_APPEAL", "ELIGIBLE_MAY_SERVE",
})
ANUNCIO_APROVADO: frozenset = frozenset({"APPROVED", "APPROVED_LIMITED"})

# ── `ad_group_criterion.primary_status_reasons`, conferido no descriptor ─────
#
# ⚠️ ESTES NOMES SÃO VERIFICADOS CONTRA O SDK, NÃO ESCRITOS DE MEMÓRIA.
#
# A primeira versão deste bloco carregava quatro nomes que NÃO EXISTEM no enum
# `AdGroupCriterionPrimaryStatusReasonEnum` da v25 —
# `AD_GROUP_CRITERION_LOW_QUALITY_SCORE`, `BELOW_FIRST_PAGE_BID`,
# `AD_GROUP_CRITERION_LOW_SEARCH_VOLUME` e `AD_GROUP_CRITERION_POLICY_DISAPPROVED`.
# Nomes inventados não quebram nada de forma visível: eles simplesmente NUNCA
# casam, e a causa que dependia deles some em silêncio. `KW_BAIXA_QUALIDADE` a
# partir do motivo declarado pela conta nunca teria disparado.
#
# `testes_vocabulario_google.py` fixa cada conjunto contra o descriptor
# protobuf instalado, e falha se alguém escrever um nome que a API não tem.

#: Lance abaixo do necessário para a primeira página. O único nome real.
KW_ABAIXO_DA_PRIMEIRA_PAGINA: frozenset = frozenset({
    "AD_GROUP_CRITERION_BELOW_FIRST_PAGE_BID",
})
#: Raramente servida. `PAUSED_DUE_TO_LOW_ACTIVITY` é a forma que a conta usa
#: quando ela mesma pausou o critério por baixa atividade — o efeito para o
#: operador é o mesmo: a keyword não disputa.
KW_RARAMENTE_SERVIDA: frozenset = frozenset({
    "AD_GROUP_CRITERION_RARELY_SERVED",
    "AD_GROUP_CRITERION_PAUSED_DUE_TO_LOW_ACTIVITY",
})
KW_REPROVADA: frozenset = frozenset({"AD_GROUP_CRITERION_DISAPPROVED"})
#: ⚠️ `AD_GROUP_CRITERION_LOW_QUALITY`, sem `_SCORE`. O sufixo era invenção.
KW_BAIXA_QUALIDADE: frozenset = frozenset({"AD_GROUP_CRITERION_LOW_QUALITY"})
#: Em revisão de política: nem aprovada, nem reprovada.
KW_EM_REVISAO: frozenset = frozenset({
    "AD_GROUP_CRITERION_UNDER_REVIEW", "AD_GROUP_CRITERION_PENDING_REVIEW",
})
#: Aprovada com restrição. Não é verde, pela mesma razão de `APPROVED_LIMITED`.
KW_RESTRITA: frozenset = frozenset({"AD_GROUP_CRITERION_RESTRICTED"})
#: ⚠️ `ELIGIBLE` é o único valor positivo de `AdGroupCriterionPrimaryStatusEnum`
#: (UNSPECIFIED, UNKNOWN, ELIGIBLE, PAUSED, REMOVED, PENDING, NOT_ELIGIBLE).
#: `ENABLED` fica na lista como tolerância a um servidor que ainda mande o
#: valor de `ad_group_criterion.status`, e NÃO porque o enum o tenha.
KW_HABILITADA: frozenset = frozenset({"ELIGIBLE", "ENABLED"})

#: Estratégias de lance que dependem de conversão medida para funcionar.
#: Fora desta lista, `MEASUREMENT_NOT_READY` não se aplica — dizer que um
#: `MANUAL_CPC` está "sem medição para Smart Bidding" seria alarme sem objeto.
ESTRATEGIAS_SMART_BIDDING: frozenset = frozenset({
    "MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE",
    "TARGET_CPA", "TARGET_ROAS", "TARGET_IMPRESSION_SHARE",
})


# ── a política do guardião ──────────────────────────────────────────────────


@dataclass(frozen=True)
class PoliticaDoGuardiao:
    """Os limites do guardião — versionados, justificados e configuráveis.

    ⚠️ Nenhum número aqui é universal, e é por isso que eles são um objeto e não
    constantes soltas. Uma conta nova de bairro e uma conta com R$ 300 mil/mês
    não têm o mesmo direito de silêncio, e a missão proíbe explicitamente
    inventar limite universal de impressão, clique, CPA ou gasto.

    O que cada limite vale, e por quê:

    · `horas_de_carencia` — antes disso a campanha está NASCENDO. Google não
      promete entrega imediata; alertar aqui é o alarme do primeiro dia que
      ninguém lê no trigésimo. Seis horas é o menor valor que ainda cobre um
      ciclo de aprovação de anúncio observado.
    · `horas_para_incidente` — o mesmo 24 que `dominio.HORAS_ATE_ALERTAR` já usa
      no sino. Se este número divergir daquele, a mesma campanha aparece no sino
      e não na sentinela, e não existe resposta certa entre as duas telas.
    · `horas_do_guardiao` — o fim da janela das primeiras 72 horas. Depois
      dela a campanha entra em operação contínua e o vocabulário muda.
    · `quality_score_baixo` — 4 é o topo do balde baixo na própria escala do
      Google (1–10). Não é opinião nossa sobre qualidade.
    · `minimo_para_proporcao` — abaixo disto não se emite proporção. "100% das
      keywords" com uma keyword é verdade aritmética e mentira operacional.
    """

    versao: int = 1
    horas_de_carencia: float = 6.0
    horas_para_incidente: float = 24.0
    horas_do_guardiao: float = 72.0
    quality_score_baixo: int = 4
    minimo_para_proporcao: int = 3
    #: Quantas leituras históricas o consolidador pode olhar para trás.
    leituras_de_historico: int = 8

    def __post_init__(self) -> None:
        if not (0 <= self.horas_de_carencia <= self.horas_para_incidente
                <= self.horas_do_guardiao):
            raise ValueError(
                "as janelas do guardião precisam ser crescentes: "
                "carência ≤ incidente ≤ guardião"
            )
        if not 1 <= self.quality_score_baixo <= 10:
            raise ValueError("quality_score_baixo vive na escala 1–10 do Google")


POLITICA_PADRAO = PoliticaDoGuardiao()

JANELA_NASCIMENTO = "nascimento"
JANELA_ATE_24H = "ate_24h"
JANELA_24_72H = "24_72h"
JANELA_APOS_72H = "apos_72h"
#: ⚠️ Não é uma janela: é a confissão de que não sabemos a idade. Vale um estado
#: próprio porque "ligada há tempo desconhecido" e "ligada há 1 hora" autorizam
#: decisões opostas, e `merece_alerta` em `dominio.py` já recusa alertar sem
#: esse número exatamente por isso.
JANELA_INDETERMINADA = "indeterminada"

JANELAS: Tuple[str, ...] = (
    JANELA_NASCIMENTO, JANELA_ATE_24H, JANELA_24_72H, JANELA_APOS_72H,
    JANELA_INDETERMINADA,
)


def janela_do_guardiao(
    horas_ligada: Optional[float],
    politica: PoliticaDoGuardiao = POLITICA_PADRAO,
) -> str:
    """Em que fase da vida a campanha está.

    `None` NÃO vira zero. Uma campanha que já estava ligada antes de o diário
    existir tem estado conhecido e antiguidade desconhecida; chamá-la de
    "recém-nascida" faria uma campanha parada há um mês parecer em carência.
    """
    # ⚠️ `NaN` entra aqui como número e sai como "campanha madura": toda
    # comparação com `NaN` é falsa, então a cascata inteira cai no `else` final
    # e `apos_72h` abre `NO_DELIVERY` sobre uma idade que ninguém conhece.
    # `NaN` é a forma numérica de "não sei", e é tratado como tal.
    if horas_ligada is None or horas_ligada != horas_ligada:
        return JANELA_INDETERMINADA
    if horas_ligada < 0:
        return JANELA_INDETERMINADA
    if horas_ligada < politica.horas_de_carencia:
        return JANELA_NASCIMENTO
    if horas_ligada < politica.horas_para_incidente:
        return JANELA_ATE_24H
    if horas_ligada < politica.horas_do_guardiao:
        return JANELA_24_72H
    return JANELA_APOS_72H


def janela_madura(
    janela: str, politica: PoliticaDoGuardiao = POLITICA_PADRAO,
) -> bool:
    """A janela já autoriza afirmar que a campanha DEVERIA ter entregado?

    Só depois da carência de incidente. Antes disso, zero impressões é o
    esperado, e transformá-lo em incidente é o alarmismo que a missão proíbe.
    """
    return janela in {JANELA_24_72H, JANELA_APOS_72H}


# ── evidência ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Evidencia:
    """Um fato observado, com a procedência colada.

    Espelha `EvidenciaDeCampo` do diagnóstico já existente: `rotulo` é o que o
    operador lê, `campo` é o nome de máquina, e `valor=None` é "a conta não
    respondeu este campo" — jamais `'0'`.
    """

    rotulo: str
    campo: str
    valor: Optional[str]
    #: Quando o fato foi lido. Sem isto, o número não deveria estar na tela.
    observado_em: Optional[str] = None
    #: `conta` (lido na conta), `derivado` (conta nossa sobre dois fatos lidos)
    #: ou `declarado` (o que o VOLC registrou, e pode estar velho).
    origem: str = "conta"

    def json(self) -> Dict[str, Any]:
        return {
            "rotulo": self.rotulo, "campo": self.campo, "valor": self.valor,
            "observado_em": self.observado_em, "origem": self.origem,
        }


@dataclass(frozen=True)
class Causa:
    """Uma causa candidata, antes de a precedência decidir quem manda."""

    status: str
    escopo: str
    #: A frase que o operador lê. Uma linha, em linguagem de operação.
    frase: str
    evidencias: Tuple[Evidencia, ...] = ()
    #: O que a conta de anúncio disse com as próprias palavras
    #: (`primary_status_reasons`). Separado da nossa inferência de propósito.
    motivo_da_conta: Tuple[str, ...] = ()
    #: A contagem que sustenta a frase, quando ela é sobre um conjunto.
    #: `None` quando a causa não é quantitativa. NUNCA um percentual sozinho.
    denominador: Optional["Denominador"] = None
    #: O próximo ato REVERSÍVEL sugerido. Nunca uma mutação.
    proximo_ato: Optional[str] = None

    @property
    def severidade(self) -> str:
        return severidade_de(self.status)

    def json(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "escopo": self.escopo,
            "severidade": self.severidade,
            "frase": self.frase,
            "evidencias": [e.json() for e in self.evidencias],
            "motivo_da_conta": list(self.motivo_da_conta),
            "denominador": self.denominador.json() if self.denominador else None,
            "proximo_ato": self.proximo_ato,
        }


@dataclass(frozen=True)
class Denominador:
    """Um numerador com o denominador colado, e o que ficou de fora.

    ⚠️ `fora_da_conta` não é detalhe de implementação: é a contraprova 8. Uma
    keyword sem `first_page_cpc` medido não pode entrar no denominador de
    "abaixo da primeira página" — nem como sim, nem como não. Ela é
    desconhecida, e o desconhecido tem um campo próprio para não se disfarçar
    de medida.
    """

    rotulo: str
    quantos: int
    de_quantos: int
    #: Observados que NÃO puderam ser classificados por falta de dado.
    fora_da_conta: int = 0
    unidade: str = "keywords"
    #: ⚠️ A política viaja COM o denominador, e não como argumento de método.
    #:
    #: `Causa.json()` chamava `Denominador.json()` sem política, e a serialização
    #: usava o padrão: com `minimo_para_proporcao=4`, a frase respeitava a
    #: política e omitia o percentual, enquanto o JSON publicava `100%` para o
    #: mesmo dado. Duas respostas para a mesma pergunta, no mesmo objeto.
    minimo_para_proporcao: int = POLITICA_PADRAO.minimo_para_proporcao

    def __post_init__(self) -> None:
        if self.quantos < 0 or self.de_quantos < 0 or self.fora_da_conta < 0:
            raise ValueError("denominador não admite contagem negativa")
        if self.quantos > self.de_quantos:
            raise ValueError(
                "o numerador não pode exceder o denominador: "
                f"{self.quantos} de {self.de_quantos}"
            )

    def proporcao(
        self, politica: Optional[PoliticaDoGuardiao] = None,
    ) -> Optional[float]:
        """A proporção, ou `None` quando a amostra não a sustenta.

        Devolver `None` em vez de `0.0` é o ponto: uma amostra pequena demais
        não produz "0%", produz "não dá para dizer".

        Sem argumento, usa o mínimo que o PRÓPRIO denominador carrega — de modo
        que a serialização não possa discordar da frase.
        """
        minimo = (
            self.minimo_para_proporcao if politica is None
            else politica.minimo_para_proporcao
        )
        if self.de_quantos < max(1, minimo):
            return None
        return self.quantos / self.de_quantos

    def frase(self, politica: Optional[PoliticaDoGuardiao] = None) -> str:
        """A contagem em português, sempre com o denominador visível."""
        base = f"{self.quantos} de {self.de_quantos} {self.unidade} {self.rotulo}"
        p = self.proporcao(politica)
        if p is not None:
            base = f"{base} ({p * 100:.0f}%)"
        if self.fora_da_conta:
            base = (
                f"{base}; {self.fora_da_conta} sem dado suficiente, "
                "fora desta conta"
            )
        return base

    def json(self) -> Dict[str, Any]:
        return {
            "rotulo": self.rotulo,
            "quantos": self.quantos,
            "de_quantos": self.de_quantos,
            "fora_da_conta": self.fora_da_conta,
            "unidade": self.unidade,
            "proporcao": self.proporcao(),
            "frase": self.frase(),
        }


# ── recomendações do Google, adjudicadas ────────────────────────────────────

ADJ_NOVA = "nova"
ADJ_REVISADA = "revisada"
ADJ_ACEITA_COMO_HIPOTESE = "aceita_como_hipotese"
ADJ_REJEITADA = "rejeitada"
ADJ_SUPERADA = "superada"

ADJUDICACOES: Tuple[str, ...] = (
    ADJ_NOVA, ADJ_REVISADA, ADJ_ACEITA_COMO_HIPOTESE, ADJ_REJEITADA, ADJ_SUPERADA,
)


@dataclass(frozen=True)
class RecomendacaoAdjudicada:
    """Uma recomendação do Google, registrada e julgada — nunca aplicada.

    Coletar não é concordar. `impacto_informado` é o que a plataforma DIZ que
    aconteceria, e viaja rotulado como declaração dela, não como medida nossa:
    optimization score não é saúde econômica, e o impacto estimado pelo Google
    não é ground truth.

    `proximo_ato` nunca é "aplicar". Aplicar e dispensar recomendação estão
    fora do escopo desta lane, e `mutacao_externa=False` no veredito é a
    declaração de que nada saiu.
    """

    tipo: str
    alvo: Optional[str]
    #: O que o Google informou de impacto, como texto — nunca convertido em
    #: número nosso, porque a unidade dele é dele.
    impacto_informado: Optional[str]
    observado_em: Optional[str]
    frescor: str
    evidencia: Tuple[Evidencia, ...] = ()
    adjudicacao: str = ADJ_NOVA
    #: Quanta confiança a evidência VOLC dá a ela. `baixa` é o default honesto:
    #: uma recomendação recém-lida não foi confrontada com nada nosso.
    confianca: str = "baixa"
    proximo_ato: str = (
        "revisar com evidência do VOLC antes de qualquer ato; "
        "esta lane não aplica nem dispensa recomendação"
    )

    def __post_init__(self) -> None:
        if self.adjudicacao not in ADJUDICACOES:
            raise ValueError(f"adjudicação fora do contrato: {self.adjudicacao!r}")

    def json(self) -> Dict[str, Any]:
        return {
            "tipo": self.tipo,
            "alvo": self.alvo,
            "impacto_informado": self.impacto_informado,
            "observado_em": self.observado_em,
            "frescor": self.frescor,
            "evidencia": [e.json() for e in self.evidencia],
            "adjudicacao": self.adjudicacao,
            "confianca": self.confianca,
            "proximo_ato": self.proximo_ato,
            "aplicada": False,
        }


#: O desfecho da coleta de recomendações. `None` para a lista quando a coleta
#: não aconteceu ou falhou — e `[]` SÓ quando a conta respondeu e não havia
#: nenhuma. É a contraprova 6, e a diferença entre as duas é a diferença entre
#: "o Google não sugeriu nada" e "não perguntamos ao Google".
COLETA_NAO_EXECUTADA = "nao_executada"
COLETA_FALHOU = "falhou"
COLETA_VAZIO_CONFIRMADO = "vazio_confirmado"
COLETA_COM_DADOS = "com_dados"


@dataclass(frozen=True)
class QuadroDeRecomendacoes:
    """As recomendações E o estado da apuração delas, juntos.

    Separar os dois seria oferecer uma lista vazia sem dizer se ela significa
    "não há" ou "não perguntei".
    """

    estado_da_coleta: str = COLETA_NAO_EXECUTADA
    #: `None` = não apurado. `[]` = apurado, e o Google não sugeriu nada.
    itens: Optional[Tuple[RecomendacaoAdjudicada, ...]] = None
    impedimento: Optional[str] = None

    @property
    def apurado(self) -> bool:
        return self.estado_da_coleta in {COLETA_COM_DADOS, COLETA_VAZIO_CONFIRMADO}

    def json(self) -> Dict[str, Any]:
        return {
            "estado_da_coleta": self.estado_da_coleta,
            "apurado": self.apurado,
            "itens": None if self.itens is None else [i.json() for i in self.itens],
            "quantidade": None if self.itens is None else len(self.itens),
            "impedimento": self.impedimento,
        }


# ── redundância de keywords, sem LLM ────────────────────────────────────────

_NAO_PALAVRA = re.compile(r"[^\w\s]+", re.UNICODE)
_ESPACOS = re.compile(r"\s+")


def normalizar_texto(texto: str) -> str:
    """Minúsculas, sem acento, sem pontuação, espaços colapsados.

    Determinística e sem modelo: a missão proíbe depender de LLM para agrupar
    redundância, e com razão — um agrupador que muda de opinião entre duas
    execuções produz um relatório que não se pode auditar.
    """
    decomposto = unicodedata.normalize("NFD", texto or "")
    sem_acento = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    limpo = _NAO_PALAVRA.sub(" ", sem_acento.lower())
    return _ESPACOS.sub(" ", limpo).strip()


def intencao_canonica(texto: str) -> str:
    """A chave de intenção: tokens únicos, em ordem estável.

    ⚠️ Só colapsa ORDEM e REPETIÇÃO. "credito consignado" e "consignado credito"
    são a mesma intenção com as palavras trocadas; "credito consignado" e
    "credito pessoal" NÃO são, e nada aqui as junta. A missão é explícita:
    palavras parecidas que podem representar intenções diferentes não são
    duplicatas, e um agrupador que as junta apaga uma disputa real.
    """
    tokens = [t for t in normalizar_texto(texto).split(" ") if t]
    return " ".join(sorted(set(tokens)))


@dataclass(frozen=True)
class ClusterDeIntencao:
    """Um grupo de keywords que disputam a mesma intenção."""

    intencao: str
    #: (texto, match_type) de cada keyword do grupo, na ordem observada.
    variantes: Tuple[Tuple[str, Optional[str]], ...]

    @property
    def redundante(self) -> bool:
        """Mais de uma keyword distinta na mesma intenção.

        Distinta pelo PAR (texto, match_type): a mesma frase em EXACT e em
        PHRASE são duas linhas de conta que disputam o mesmo leilão, e é isso
        que "redundante" quer dizer aqui.
        """
        return len(set(self.variantes)) > 1

    def json(self) -> Dict[str, Any]:
        return {
            "intencao": self.intencao,
            "variantes": [
                {"texto": t, "match_type": m} for t, m in self.variantes
            ],
            "redundante": self.redundante,
        }


def agrupar_por_intencao(
    keywords: Sequence[Mapping[str, Any]],
) -> Tuple[ClusterDeIntencao, ...]:
    """Agrupa keywords por intenção canônica. Sem modelo, sem rede, sem opinião.

    Cada item aceita `texto` e `match_type`. Keyword sem texto NÃO entra em
    cluster nenhum: agrupar pelo vazio juntaria todas as keywords sem texto num
    "cluster" que não descreve intenção nenhuma.
    """
    grupos: Dict[str, List[Tuple[str, Optional[str]]]] = {}
    for kw in keywords:
        texto = kw.get("texto")
        if not texto:
            continue
        chave = intencao_canonica(str(texto))
        if not chave:
            continue
        match = kw.get("match_type")
        grupos.setdefault(chave, []).append(
            (str(texto), None if match is None else str(match))
        )
    return tuple(
        ClusterDeIntencao(intencao=chave, variantes=tuple(variantes))
        for chave, variantes in sorted(grupos.items())
    )


# ── a leitura de keywords, com denominadores ────────────────────────────────


@dataclass(frozen=True)
class LeituraDeKeywords:
    """As contagens de keywords, cada uma com o denominador que a sustenta."""

    observadas: int = 0
    habilitadas: int = 0
    aptas: int = 0
    abaixo_da_primeira_pagina: int = 0
    #: Observadas cujo lance OU estimativa de primeira página não veio.
    sem_dado_de_lance: int = 0
    baixa_qualidade: int = 0
    #: ⚠️ Observadas que NÃO puderam ser classificadas quanto a qualidade —
    #: nem pelo número, nem por um motivo declarado pela conta.
    #:
    #: A versão anterior contava aqui toda keyword sem `quality_score`,
    #: INCLUSIVE as que a conta já tinha classificado com
    #: `AD_GROUP_CRITERION_LOW_QUALITY`. A mesma keyword ficava no numerador de
    #: `baixa_qualidade` E fora do universo medido, e o denominador saía "1 de
    #: 2, 1 fora" quando o correto era "1 de 3".
    sem_dado_de_qualidade: int = 0
    raramente_servidas: int = 0
    reprovadas: int = 0
    #: Em revisão de política: nem aprovadas, nem reprovadas.
    em_revisao: int = 0
    #: Aprovadas com restrição. Não é verde, pelo mesmo motivo de APPROVED_LIMITED.
    restritas: int = 0
    #: Observadas sem NENHUM estado conclusivo.
    sem_dados: int = 0
    clusters: Tuple[ClusterDeIntencao, ...] = ()

    @property
    def clusters_redundantes(self) -> int:
        return sum(1 for c in self.clusters if c.redundante)

    @property
    def medidas_para_lance(self) -> int:
        """O denominador honesto de "abaixo da primeira página"."""
        return max(0, self.observadas - self.sem_dado_de_lance)

    @property
    def medidas_para_qualidade(self) -> int:
        """O denominador honesto de "baixa qualidade".

        Uma keyword classificada por MOTIVO DECLARADO conta como medida mesmo
        sem o número: o Google dizendo `AD_GROUP_CRITERION_LOW_QUALITY` é
        evidência mais forte que a ausência do campo.
        """
        return max(0, self.observadas - self.sem_dado_de_qualidade)

    def json(self) -> Dict[str, Any]:
        return {
            "observadas": self.observadas,
            "habilitadas": self.habilitadas,
            "aptas": self.aptas,
            "abaixo_da_primeira_pagina": self.abaixo_da_primeira_pagina,
            "sem_dado_de_lance": self.sem_dado_de_lance,
            "medidas_para_lance": self.medidas_para_lance,
            "baixa_qualidade": self.baixa_qualidade,
            "sem_dado_de_qualidade": self.sem_dado_de_qualidade,
            "medidas_para_qualidade": self.medidas_para_qualidade,
            "raramente_servidas": self.raramente_servidas,
            "reprovadas": self.reprovadas,
            "em_revisao": self.em_revisao,
            "restritas": self.restritas,
            "sem_dados": self.sem_dados,
            "clusters_redundantes": self.clusters_redundantes,
            "clusters": [c.json() for c in self.clusters],
        }


def _inteiro(valor: Any) -> Optional[int]:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(str(valor))
    except (TypeError, ValueError):
        return None


def _motivos(valor: Any) -> Tuple[str, ...]:
    """Os motivos declarados pela conta, em MAIÚSCULAS e na ordem observada.

    Tupla e não conjunto: a ordem em que o Google listou os motivos é
    informação (o primeiro costuma ser o dominante), e ela vai inteira para
    `Causa.motivo_da_conta`. Quem precisa de teste de pertinência usa `_tem`.
    """
    if valor is None:
        return ()
    if isinstance(valor, (list, tuple)):
        return tuple(str(v).upper() for v in valor if v is not None)
    return (str(valor).upper(),)


def _tem(motivos: Sequence[str], conjunto: frozenset) -> bool:
    """Algum motivo declarado pertence ao conjunto reconhecido."""
    return any(m in conjunto for m in motivos)


def ler_keywords(
    keywords: Sequence[Mapping[str, Any]],
    politica: PoliticaDoGuardiao = POLITICA_PADRAO,
) -> LeituraDeKeywords:
    """Conta as keywords por estado, sem deixar ausência virar medida.

    Cada item aceita: `primary_status`, `primary_status_reasons`, `texto`,
    `match_type`, `lance_micros`, `primeira_pagina_micros`, `quality_score`.

    A regra que este corpo inteiro protege: uma keyword cujo lance OU cuja
    estimativa de primeira página não veio NÃO entra em `abaixo_da_primeira_
    pagina` nem no seu complemento. Ela é contada em `sem_dado_de_lance`, e o
    denominador de lance encolhe. Empurrá-la para o lado "não está abaixo"
    produziria exatamente o falso verde que este módulo existe para impedir.
    """
    observadas = len(keywords)
    habilitadas = aptas = abaixo = sem_lance = 0
    baixa_qualidade = sem_qualidade = raramente = reprovadas = sem_dados = 0
    em_revisao = restritas = 0

    for kw in keywords:
        primary = kw.get("primary_status")
        primary_txt = None if primary is None else str(primary).upper()
        motivos = _motivos(kw.get("primary_status_reasons"))

        if primary_txt is None:
            sem_dados += 1
        elif primary_txt in KW_HABILITADA:
            habilitadas += 1

        if _tem(motivos, KW_REPROVADA):
            reprovadas += 1
        if _tem(motivos, KW_RARAMENTE_SERVIDA):
            raramente += 1
        # ⚠️ `KW_EM_REVISAO` e `KW_RESTRITA` foram criados, verificados contra o
        # SDK — e nunca consultados. Uma keyword `ELIGIBLE` com motivo
        # `AD_GROUP_CRITERION_UNDER_REVIEW` contava como apta e o veredito saía
        # `HEALTHY`. Constante correta e nunca lida é o mesmo defeito de
        # `first_page_cpc_micros`: o sinal existe e é jogado fora.
        if _tem(motivos, KW_EM_REVISAO):
            em_revisao += 1
        if _tem(motivos, KW_RESTRITA):
            restritas += 1

        lance = _inteiro(kw.get("lance_micros"))
        primeira = _inteiro(kw.get("primeira_pagina_micros"))
        if lance is None or primeira is None:
            sem_lance += 1
        elif lance < primeira:
            abaixo += 1

        qs = _inteiro(kw.get("quality_score"))
        declarada_baixa = _tem(motivos, KW_BAIXA_QUALIDADE)
        if qs is not None and qs <= politica.quality_score_baixo:
            baixa_qualidade += 1
        elif declarada_baixa:
            # Um motivo declarado pela conta VALE mesmo sem o número, e a
            # keyword fica DENTRO do universo medido — classificá-la e ao mesmo
            # tempo declará-la sem dado a contaria duas vezes.
            baixa_qualidade += 1
        elif qs is None:
            sem_qualidade += 1

        # Apta = habilitada, com lance acima da estimativa, e sem NENHUM motivo
        # negativo declarado pela conta — inclusive revisão e restrição.
        if (
            primary_txt in KW_HABILITADA
            and lance is not None and primeira is not None and lance >= primeira
            and not _tem(
                motivos,
                KW_REPROVADA | KW_RARAMENTE_SERVIDA | KW_EM_REVISAO
                | KW_RESTRITA | KW_BAIXA_QUALIDADE,
            )
        ):
            aptas += 1

    return LeituraDeKeywords(
        observadas=observadas, habilitadas=habilitadas, aptas=aptas,
        abaixo_da_primeira_pagina=abaixo, sem_dado_de_lance=sem_lance,
        baixa_qualidade=baixa_qualidade, sem_dado_de_qualidade=sem_qualidade,
        raramente_servidas=raramente, reprovadas=reprovadas,
        em_revisao=em_revisao, restritas=restritas, sem_dados=sem_dados,
        clusters=agrupar_por_intencao(keywords),
    )


# ── a leitura que a sentinela recebe ────────────────────────────────────────


@dataclass(frozen=True)
class LeituraDaConta:
    """O que se sabe da conta. `status=None` é "não lemos", não "está bem"."""

    customer_id: str
    status: Optional[str] = None
    #: `True` quando a própria API recusou a leitura (permissão, token, escopo).
    acesso_negado: bool = False
    motivo_do_acesso: Optional[str] = None
    observado_em: Optional[str] = None


@dataclass(frozen=True)
class LeituraDaCampanha:
    """O estado da campanha, como a conta respondeu."""

    status: Optional[str] = None
    primary_status: Optional[str] = None
    primary_status_reasons: Tuple[str, ...] = ()
    serving_status: Optional[str] = None
    bidding_strategy_type: Optional[str] = None
    horas_ligada: Optional[float] = None
    orcamento_diario_micros: Optional[int] = None


@dataclass(frozen=True)
class LeituraDeMetricas:
    """As métricas medidas. `None` é "não medido" — jamais zero."""

    impressoes: Optional[int] = None
    cliques: Optional[int] = None
    custo_micros: Optional[int] = None
    conversoes: Optional[float] = None
    perda_por_orcamento: Optional[float] = None
    perda_por_rank: Optional[float] = None


@dataclass(frozen=True)
class LeituraDeAnuncios:
    """Os anúncios do grupo, já classificados pela política do Google."""

    observados: int = 0
    aptos: int = 0
    reprovados: int = 0
    em_revisao: int = 0
    #: `APPROVED_LIMITED` — aprovado COM restrição de veiculação.
    #:
    #: ⚠️ Campo próprio porque ele é um estado CONHECIDO. Empurrá-lo para
    #: `sem_estado` trocaria "a conta aprovou com restrição" por "não sei o que
    #: a conta disse" — que é perder informação que já temos, e é o espelho do
    #: erro oposto de contá-lo como aprovado.
    limitados: int = 0
    sem_estado: int = 0
    motivos: Tuple[str, ...] = ()


@dataclass(frozen=True)
class LeituraDeMedicao:
    """A prontidão de mensuração, CONSUMIDA de quem já a apura.

    ⚠️ Este módulo não reimplementa `trafego.prontidao`. Ele recebe o veredito
    dela — `PRONTO`/`PARCIAL`/`NAO_PRONTO`/`INDETERMINADO`/`NAO_APLICAVEL` — e
    o converte em causa. Duas implementações da mesma pergunta é como o portão
    e a tela passam a discordar sem que exista resposta certa entre os dois.
    """

    #: O estado de `trafego.prontidao`. `None` = ninguém apurou.
    conversion_goal_status: Optional[str] = None
    #: `None` = não apurado. Nunca `[]` para dizer "não sei".
    metas_observadas: Optional[int] = None
    impedimento: Optional[str] = None


@dataclass(frozen=True)
class LeituraDoDestino:
    """O recibo de destino pago, apenas CONSUMIDO.

    `backend/app/landing_policy/**` é ownership de outra frente. A sentinela lê
    o veredito que ela grava e nunca o recalcula.

    ## `nao_consultado` e `ausente` são fatos diferentes

    ⚠️ Esta distinção nasceu de um defeito medido nesta própria lane. Com um só
    estado para "não tem recibo", `ausente` era o default — e como ele produz
    `DATA_UNAVAILABLE`, que está acima de `OBSERVING` na ordem causal, TODA
    campanha passava a ter o destino como causa primária. Uma campanha recém-
    criada em carência saía `DATA_UNAVAILABLE@destination` em vez de
    `OBSERVING`. Era o mesmo defeito do eixo `conta`, com outra roupa: um degrau
    que ninguém preenche sequestrando o veredito de todas as campanhas.

    · `nao_consultado` — esta leitura não perguntou ao portão de destino. NÃO é
      causa, e vai para `desconhecidos`; rebaixa a evidência para `parcial`, de
      modo que `HEALTHY` continua inalcançável;
    · `ausente` — perguntamos, e não existe recibo. Isso É causa, porque
      ausência de recibo não é aprovação.
    """

    #: `apto` | `reprovado` | `em_revisao` | `ausente` | `nao_consultado`
    estado: str = "nao_consultado"
    motivo: Optional[str] = None
    observado_em: Optional[str] = None


@dataclass(frozen=True)
class LeituraParaSentinela:
    """Tudo o que a sentinela precisa, já normalizado e sem rede."""

    customer_id: str
    volc_campaign_id: str
    conta: LeituraDaConta
    campanha: LeituraDaCampanha = field(default_factory=LeituraDaCampanha)
    metricas: LeituraDeMetricas = field(default_factory=LeituraDeMetricas)
    keywords: LeituraDeKeywords = field(default_factory=LeituraDeKeywords)
    anuncios: LeituraDeAnuncios = field(default_factory=LeituraDeAnuncios)
    medicao: LeituraDeMedicao = field(default_factory=LeituraDeMedicao)
    destino: LeituraDoDestino = field(default_factory=LeituraDoDestino)
    recomendacoes: QuadroDeRecomendacoes = field(default_factory=QuadroDeRecomendacoes)
    #: `com_dados`|`vazio_confirmado`|`parcial`|`inelegivel`|`nao_suportado`|
    #: `falhou`|`None` — o mesmo vocabulário do ledger v12.
    estado_da_coleta: Optional[str] = None
    #: `recente`|`velho`|`nao_apurado` — o mesmo vocabulário do inventário.
    frescor: str = "nao_apurado"
    observado_em: Optional[str] = None
    janela_inicio: Optional[str] = None
    janela_fim: Optional[str] = None
    #: Enum da conta que esta versão não reconhece. Rebaixa a leitura inteira.
    #: É a contraprova 18: erro futuro do Google é falha conservadora, não verde.
    valores_desconhecidos: Tuple[str, ...] = ()


# ── o veredito ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Veredito:
    """A resposta da sentinela para UMA campanha, num instante."""

    versao: int
    customer_id: str
    volc_campaign_id: str
    escopo: str
    status: str
    severidade: str
    observado_em: Optional[str]
    janela_inicio: Optional[str]
    janela_fim: Optional[str]
    janela_do_guardiao: str
    frescor: str
    #: `apurada` | `parcial` | `ausente` — o estado da PROVA, separado do estado
    #: da campanha. Um veredito com prova parcial não vale o mesmo que um com
    #: prova completa, e achatar os dois é como uma leitura meia-boca vira
    #: conclusão firme.
    estado_da_evidencia: str
    causa_primaria: Optional[Causa]
    causas_secundarias: Tuple[Causa, ...]
    desconhecidos: Tuple[str, ...]
    recomendacoes: QuadroDeRecomendacoes
    proximo_ato: Optional[str]
    chave: str
    #: Sempre `False`, sempre declarado. Ver o docblock do módulo.
    mutacao_externa: bool = False

    @property
    def incidente(self) -> bool:
        return self.status in ESTADOS_DE_INCIDENTE

    def json(self) -> Dict[str, Any]:
        return {
            "versao": self.versao,
            "customer_id": self.customer_id,
            "volc_campaign_id": self.volc_campaign_id,
            "escopo": self.escopo,
            "status": self.status,
            "severidade": self.severidade,
            "incidente": self.incidente,
            "observado_em": self.observado_em,
            "janela_inicio": self.janela_inicio,
            "janela_fim": self.janela_fim,
            "janela_do_guardiao": self.janela_do_guardiao,
            "frescor": self.frescor,
            "estado_da_evidencia": self.estado_da_evidencia,
            "causa_primaria": self.causa_primaria.json() if self.causa_primaria else None,
            "causas_secundarias": [c.json() for c in self.causas_secundarias],
            "desconhecidos": list(self.desconhecidos),
            "recomendacoes": self.recomendacoes.json(),
            "proximo_ato": self.proximo_ato,
            "chave": self.chave,
            "mutacao_externa": self.mutacao_externa,
        }


def chave_do_incidente(
    *, customer_id: str, volc_campaign_id: str, escopo: str, status: str,
) -> str:
    """A identidade determinística de um incidente.

    ⚠️ A JANELA NÃO ENTRA NA CHAVE, e isso é a contraprova 13. Duas leituras da
    mesma condição em janelas diferentes são o MESMO incidente continuando —
    incluir a janela criaria um incidente novo a cada coleta e inundaria o
    operador com o mesmo fato repetido, que é exatamente o que `§8` proíbe.
    A janela viaja no incidente como `ultima_janela`, onde ela informa sem
    fragmentar a identidade.

    O `escopo` entra porque o mesmo status em níveis diferentes são problemas
    diferentes: `DATA_UNAVAILABLE` na conta e na campanha pedem ações distintas.
    """
    partes = (customer_id, volc_campaign_id, escopo, status)
    return hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()[:32]


def _iso(valor: Optional[datetime]) -> Optional[str]:
    return None if valor is None else valor.astimezone(timezone.utc).isoformat()


def _ev(rotulo: str, campo: str, valor: Any, quando: Optional[str],
        origem: str = "conta") -> Evidencia:
    if valor is None:
        texto = None
    elif isinstance(valor, bool):
        texto = "sim" if valor else "não"
    elif isinstance(valor, (list, tuple)):
        texto = ", ".join(str(v) for v in valor) or None
    else:
        texto = str(valor)
    return Evidencia(
        rotulo=rotulo, campo=campo, valor=texto, observado_em=quando, origem=origem,
    )


def _micros_para_texto(micros: Optional[int]) -> Optional[str]:
    if micros is None:
        return None
    return f"{micros / 1_000_000:.2f}"


# ── as causas candidatas ────────────────────────────────────────────────────


def _causas_da_conta(leitura: LeituraParaSentinela) -> List[Causa]:
    conta = leitura.conta
    quando = conta.observado_em or leitura.observado_em
    causas: List[Causa] = []

    if conta.acesso_negado:
        causas.append(Causa(
            status=ACCESS_UNAVAILABLE, escopo=ESCOPO_CONTA,
            frase=(
                "A conta de anúncio recusou a leitura: sem autorização não há "
                "diagnóstico, e a ausência de números aqui não afirma nada "
                "sobre a campanha."
            ),
            evidencias=(
                _ev("acesso", "api.authorization", "negado", quando),
                _ev("motivo", "api.error", conta.motivo_do_acesso, quando),
            ),
            proximo_ato=(
                "conferir credencial e permissão da conta antes de qualquer "
                "leitura de campanha; nenhuma conclusão de entrega vale até lá"
            ),
        ))
        # ⚠️ SEM `return` AQUI, e isso é o ponto.
        #
        # A versão anterior retornava, e com isso um `status=SUSPENDED` JÁ
        # OBSERVADO junto de uma falha de acesso posterior saía como
        # `ACCESS_UNAVAILABLE` — uma causa da posição 2 escondendo a da posição
        # 1. Era o defeito de origem desta lane cometido de novo: a ordem de
        # AVALIAÇÃO decidindo o veredito em vez de `PRECEDENCIA`. Um fato
        # observado não deixa de existir porque a leitura seguinte falhou.
        if conta.status is None:
            return causas

    status = None if conta.status is None else str(conta.status).upper()
    if status is None:
        causas.append(Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_CONTA,
            frase=(
                "O estado da conta de anúncio não foi observado. Sem ele, "
                "nenhum degrau acima sustenta conclusão."
            ),
            evidencias=(_ev("estado da conta", "customer.status", None, quando),),
            proximo_ato="coletar customer.status antes de concluir sobre a campanha",
        ))
    elif status in CONTA_BLOQUEADA:
        causas.append(Causa(
            status=ACCOUNT_BLOCKED, escopo=ESCOPO_CONTA,
            frase=(
                f"A conta de anúncio está {status}. Enquanto ela estiver assim, "
                "nada desta campanha vai a leilão — lance, orçamento e Quality "
                "Score são história, não causa."
            ),
            evidencias=(
                _ev("estado da conta", "customer.status", status, quando),
            ),
            proximo_ato=(
                "tratar a conta no painel do Google antes de qualquer ajuste de "
                "campanha; nenhum ato de lance ou verba muda este estado"
            ),
        ))
    elif status not in CONTA_HABILITADA:
        # ⚠️ Contraprova 18. Um `customer.status` que esta versão não conhece
        # NÃO é `ENABLED`. Ele rebaixa a leitura, e nunca a promove.
        causas.append(Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_CONTA,
            frase=(
                f"A conta respondeu o estado {status!r}, que esta versão da "
                "sentinela não reconhece. Nada acima disto sustenta conclusão."
            ),
            evidencias=(
                _ev("estado da conta", "customer.status", status, quando),
            ),
            proximo_ato=(
                "conferir o estado da conta no painel do Google e atualizar o "
                "vocabulário da sentinela"
            ),
        ))
    return causas


def _causas_do_destino(leitura: LeituraParaSentinela) -> List[Causa]:
    destino = leitura.destino
    quando = destino.observado_em or leitura.observado_em
    if destino.estado == "reprovado":
        return [Causa(
            status=POLICY_BLOCKED, escopo=ESCOPO_DESTINO,
            frase=(
                "O recibo de destino pago reprovou a página. Enquanto o destino "
                "não for apto, ajustar campanha não resolve."
            ),
            evidencias=(
                _ev("destino", "landing_policy.recibo.estado", "reprovado", quando),
                _ev("motivo", "landing_policy.recibo.motivo", destino.motivo, quando),
            ),
            proximo_ato="tratar o destino pela frente de landing policy; esta lane só lê o recibo",
        )]
    if destino.estado == "em_revisao":
        return [Causa(
            status=POLICY_REVIEW, escopo=ESCOPO_DESTINO,
            frase=(
                "O destino está em revisão. Não está aprovado e não está "
                "reprovado — afirmar qualquer um dos dois seria inventar veredito."
            ),
            evidencias=(
                _ev("destino", "landing_policy.recibo.estado", "em_revisao", quando),
            ),
            proximo_ato="aguardar o veredito do recibo de destino antes de concluir",
        )]
    if destino.estado == "ausente":
        return [Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_DESTINO,
            frase=(
                "Não há recibo de destino pago para esta campanha. Ausência de "
                "recibo não é aprovação."
            ),
            evidencias=(
                _ev("destino", "landing_policy.recibo", None, quando),
            ),
            proximo_ato="pedir o recibo de destino à frente de landing policy",
        )]
    return []


def _causas_dos_anuncios(
    leitura: LeituraParaSentinela,
    politica: PoliticaDoGuardiao = POLITICA_PADRAO,
) -> List[Causa]:
    ads = leitura.anuncios
    quando = leitura.observado_em
    causas: List[Causa] = []

    if ads.reprovados and ads.aptos == 0:
        causas.append(Causa(
            status=POLICY_BLOCKED, escopo=ESCOPO_ANUNCIO,
            frase="Todos os anúncios observados estão reprovados por política.",
            evidencias=(
                _ev("reprovados", "ad_group_ad.policy_summary.approval_status",
                    ads.reprovados, quando),
            ),
            motivo_da_conta=ads.motivos,
            denominador=Denominador(
                rotulo="reprovados por política", quantos=ads.reprovados,
                de_quantos=ads.observados, unidade="anúncios",
                minimo_para_proporcao=politica.minimo_para_proporcao,
            ),
            proximo_ato="revisar a política do anúncio antes de mexer em lance ou verba",
        ))
        return causas

    if ads.limitados and ads.aptos == 0 and not ads.reprovados:
        causas.append(Causa(
            status=POLICY_BLOCKED, escopo=ESCOPO_ANUNCIO,
            frase=(
                f"A conta aprovou {ads.limitados} de {ads.observados} anúncios "
                "COM restrição de veiculação — não é o mesmo que aprovados."
            ),
            evidencias=(
                _ev("aprovados com limite",
                    "ad_group_ad.policy_summary.approval_status",
                    ads.limitados, quando),
            ),
            motivo_da_conta=ads.motivos,
            denominador=Denominador(
                rotulo="aprovados com restrição", quantos=ads.limitados,
                de_quantos=ads.observados, unidade="anúncios",
                minimo_para_proporcao=politica.minimo_para_proporcao,
            ),
            proximo_ato=(
                "conferir a restrição declarada pela conta antes de mexer em lance"
            ),
        ))
        return causas

    if ads.em_revisao and ads.aptos == 0 and not ads.reprovados:
        causas.append(Causa(
            status=POLICY_REVIEW, escopo=ESCOPO_ANUNCIO,
            frase=(
                "Os anúncios estão em revisão. Não estão aprovados e não estão "
                "reprovados."
            ),
            evidencias=(
                _ev("em revisão", "ad_group_ad.policy_summary.review_status",
                    ads.em_revisao, quando),
            ),
            motivo_da_conta=ads.motivos,
            denominador=Denominador(
                rotulo="em revisão", quantos=ads.em_revisao,
                de_quantos=ads.observados, unidade="anúncios",
                minimo_para_proporcao=politica.minimo_para_proporcao,
            ),
            proximo_ato="aguardar a revisão do Google; não há ato de lance que a acelere",
        ))
        return causas

    if ads.observados == 0:
        if leitura.estado_da_coleta == "com_dados":
            causas.append(Causa(
                status=ADS_NOT_READY, escopo=ESCOPO_ANUNCIO,
                frase="A coleta completa observou zero anúncios nesta campanha.",
                evidencias=(_ev("anúncios observados", "ad_group_ad", 0, quando),),
                denominador=Denominador(
                    rotulo="aptos", quantos=0, de_quantos=0, unidade="anúncios",
                    minimo_para_proporcao=politica.minimo_para_proporcao,
                ),
                proximo_ato=(
                    "criar ao menos um anúncio apto no grupo antes de qualquer "
                    "ajuste de lance"
                ),
            ))
        else:
            causas.append(Causa(
                status=DATA_UNAVAILABLE, escopo=ESCOPO_ANUNCIO,
                frase="Nenhum anúncio foi observado, e a coleta não foi completa.",
                evidencias=(_ev("anúncios observados", "ad_group_ad", None, quando),),
                proximo_ato="repetir a coleta antes de concluir sobre os anúncios",
            ))
        return causas

    if ads.aptos == 0 and ads.sem_estado == ads.observados:
        causas.append(Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_ANUNCIO,
            frase="Os anúncios vieram sem estado conclusivo.",
            evidencias=(
                _ev("sem estado", "ad_group_ad.primary_status",
                    ads.sem_estado, quando),
            ),
            proximo_ato="repetir a coleta dos anúncios antes de concluir",
        ))
        return causas

    if ads.aptos == 0:
        causas.append(Causa(
            status=ADS_NOT_READY, escopo=ESCOPO_ANUNCIO,
            frase="Nenhum anúncio apto para exibição neste grupo.",
            evidencias=(
                _ev("aptos", "ad_group_ad.primary_status", 0, quando),
                _ev("observados", "ad_group_ad", ads.observados, quando),
            ),
            motivo_da_conta=ads.motivos,
            denominador=Denominador(
                rotulo="aptos", quantos=0, de_quantos=ads.observados,
                unidade="anúncios",
                minimo_para_proporcao=politica.minimo_para_proporcao,
            ),
            proximo_ato=(
                "tornar ao menos um anúncio apto antes de qualquer ajuste de "
                "lance: sem anúncio o leilão não começa"
            ),
        ))
    return causas


def _causas_da_campanha(
    leitura: LeituraParaSentinela, janela: str, politica: PoliticaDoGuardiao,
) -> List[Causa]:
    camp = leitura.campanha
    met = leitura.metricas
    quando = leitura.observado_em
    causas: List[Causa] = []

    status = None if camp.status is None else str(camp.status).upper()

    if status is None:
        causas.append(Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_CAMPANHA,
            frase="A linha da campanha não trouxe o estado dela.",
            evidencias=(_ev("estado", "campaign.status", None, quando),),
            proximo_ato="repetir a coleta da campanha antes de concluir",
        ))
        return causas

    if status in CAMPANHA_DESLIGADA:
        # ⚠️ Contraprova 2. Uma campanha desligada com zero gasto é o esperado.
        # Nada abaixo desta linha pode emitir NO_DELIVERY para ela.
        causas.append(Causa(
            status=CAMPAIGN_OFF, escopo=ESCOPO_CAMPANHA,
            frase=(
                f"A campanha está {status}. Não gastar é o comportamento "
                "esperado de uma campanha desligada, e não é incidente."
            ),
            evidencias=(
                _ev("estado", "campaign.status", status, quando),
                _ev("custo", "metrics.cost_micros",
                    _micros_para_texto(met.custo_micros), quando),
            ),
            motivo_da_conta=camp.primary_status_reasons,
            proximo_ato=(
                "nenhum: se a pausa foi intencional, não há o que fazer; "
                "religar é decisão de operação, não de sentinela"
            ),
        ))
        return causas

    if status not in {"ENABLED"}:
        causas.append(Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_CAMPANHA,
            frase=(
                f"A campanha respondeu o estado {status!r}, que esta versão não "
                "reconhece."
            ),
            evidencias=(_ev("estado", "campaign.status", status, quando),),
            motivo_da_conta=camp.primary_status_reasons,
            proximo_ato="conferir o estado no painel e atualizar o vocabulário",
        ))
        return causas

    # A partir daqui a campanha está declaradamente ligada.
    primary = None if camp.primary_status is None else str(camp.primary_status).upper()

    if primary in {"NOT_ELIGIBLE", "REMOVED", "ENDED"}:
        causas.append(Causa(
            status=NO_DELIVERY, escopo=ESCOPO_CAMPANHA,
            frase=(
                "A própria conta observou um estado principal que impede "
                "veiculação."
            ),
            evidencias=(
                _ev("estado principal", "campaign.primary_status", primary, quando),
            ),
            motivo_da_conta=camp.primary_status_reasons,
            proximo_ato="tratar o motivo declarado pela conta antes de qualquer ajuste",
        ))
        return causas

    if primary == "LEARNING":
        causas.append(Causa(
            status=LEARNING, escopo=ESCOPO_CAMPANHA,
            frase="A conta observou a campanha em aprendizado.",
            evidencias=(
                _ev("estado principal", "campaign.primary_status", primary, quando),
            ),
            motivo_da_conta=camp.primary_status_reasons,
            proximo_ato="não mexer: alterar lance em aprendizado reinicia o aprendizado",
        ))

    # Zero entrega — só vira incidente com maturidade E frescor.
    if met.impressoes is None:
        causas.append(Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_CAMPANHA,
            frase="As impressões não foram medidas nesta janela.",
            evidencias=(_ev("impressões", "metrics.impressions", None, quando),),
            proximo_ato="repetir a coleta de desempenho antes de concluir sobre entrega",
        ))
    elif met.impressoes == 0:
        if not janela_madura(janela, politica):
            causas.append(Causa(
                status=OBSERVING, escopo=ESCOPO_CAMPANHA,
                frase=(
                    "A campanha está ligada e ainda dentro da janela de "
                    f"observação ({janela}). Zero impressões aqui é esperado, "
                    "não incidente."
                ),
                evidencias=(
                    _ev("impressões", "metrics.impressions", 0, quando),
                    _ev("horas ligada", "trafego_evento.estado",
                        camp.horas_ligada, quando, origem="derivado"),
                ),
                proximo_ato=(
                    "observar até o fim da carência antes de concluir; "
                    f"a política em vigor espera {politica.horas_para_incidente:.0f}h"
                ),
            ))
        else:
            causas.append(Causa(
                status=NO_DELIVERY, escopo=ESCOPO_CAMPANHA,
                frase=(
                    "A campanha está ligada, madura e a conta mediu zero "
                    "impressões nesta janela."
                ),
                evidencias=(
                    _ev("impressões", "metrics.impressions", 0, quando),
                    _ev("cliques", "metrics.clicks", met.cliques, quando),
                    _ev("custo", "metrics.cost_micros",
                        _micros_para_texto(met.custo_micros), quando),
                    _ev("horas ligada", "trafego_evento.estado",
                        camp.horas_ligada, quando, origem="derivado"),
                ),
                motivo_da_conta=camp.primary_status_reasons,
                proximo_ato=(
                    "conferir anúncio apto, destino e lance nesta ordem; "
                    "nenhum ato foi aplicado por esta leitura"
                ),
            ))

    # Orçamento: perda MEDIDA. Ausência de medida não é ausência de perda.
    if met.perda_por_orcamento is not None and met.perda_por_orcamento > 0:
        causas.append(Causa(
            status=LIMITED_BY_BUDGET, escopo=ESCOPO_CAMPANHA,
            frase="A conta mediu perda de participação por orçamento.",
            evidencias=(
                _ev("perda por orçamento",
                    "metrics.search_budget_lost_impression_share",
                    met.perda_por_orcamento, quando),
                _ev("orçamento diário", "campaign_budget.amount_micros",
                    _micros_para_texto(camp.orcamento_diario_micros), quando),
            ),
            proximo_ato=(
                "avaliar verba diária contra a perda medida; proposta reversível, "
                "nenhum ato aplicado"
            ),
        ))
    return causas


def _causas_das_keywords(
    leitura: LeituraParaSentinela, politica: PoliticaDoGuardiao,
) -> List[Causa]:
    kw = leitura.keywords
    met = leitura.metricas
    quando = leitura.observado_em
    causas: List[Causa] = []

    if kw.observadas == 0:
        if leitura.estado_da_coleta == "com_dados":
            causas.append(Causa(
                status=NO_DELIVERY, escopo=ESCOPO_KEYWORD,
                frase="A coleta completa observou zero keywords nesta campanha.",
                evidencias=(_ev("keywords observadas", "keyword_view", 0, quando),),
                proximo_ato="conferir se o grupo tem keywords antes de olhar lance",
            ))
        else:
            causas.append(Causa(
                status=DATA_UNAVAILABLE, escopo=ESCOPO_KEYWORD,
                frase="Nenhuma keyword observada, e a coleta não foi completa.",
                evidencias=(_ev("keywords observadas", "keyword_view", None, quando),),
                proximo_ato="repetir a coleta de keywords antes de concluir",
            ))
        return causas

    # Lance abaixo da primeira página — com denominador honesto.
    medidas = kw.medidas_para_lance
    if kw.abaixo_da_primeira_pagina and medidas:
        den = Denominador(
            rotulo="com lance abaixo da estimativa de primeira página",
            quantos=kw.abaixo_da_primeira_pagina, de_quantos=medidas,
            fora_da_conta=kw.sem_dado_de_lance,
            minimo_para_proporcao=politica.minimo_para_proporcao,
        )
        causas.append(Causa(
            status=LIMITED_BY_RANK, escopo=ESCOPO_KEYWORD,
            frase=den.frase(politica),
            evidencias=(
                _ev("abaixo da primeira página",
                    "ad_group_criterion.effective_cpc_bid_micros < "
                    "position_estimates.first_page_cpc_micros",
                    kw.abaixo_da_primeira_pagina, quando, origem="derivado"),
                _ev("keywords medidas para lance", "ad_group_criterion",
                    medidas, quando),
                _ev("sem dado de lance", "ad_group_criterion",
                    kw.sem_dado_de_lance, quando),
            ),
            denominador=den,
            proximo_ato=(
                "avaliar lance contra a estimativa de primeira página; "
                "proposta reversível, nenhum ato aplicado"
            ),
        ))
    elif met.perda_por_rank is not None and met.perda_por_rank > 0:
        causas.append(Causa(
            status=LIMITED_BY_RANK, escopo=ESCOPO_CAMPANHA,
            frase="A conta mediu perda de participação por classificação.",
            evidencias=(
                _ev("perda por rank",
                    "metrics.search_rank_lost_impression_share",
                    met.perda_por_rank, quando),
            ),
            proximo_ato="avaliar lance e qualidade; proposta reversível, nenhum ato aplicado",
        ))

    # ⚠️ Em revisão vem ANTES de reprovada e antes de qualquer causa de lance:
    # o Google ainda não decidiu, e afirmar aprovado ou reprovado seria inventar
    # veredito. Sem esta causa, uma keyword `ELIGIBLE` com
    # `AD_GROUP_CRITERION_UNDER_REVIEW` saía como campanha saudável.
    if kw.em_revisao:
        causas.append(Causa(
            status=POLICY_REVIEW, escopo=ESCOPO_KEYWORD,
            frase=(
                f"{kw.em_revisao} de {kw.observadas} keywords estão em revisão "
                "de política: não estão aprovadas e não estão reprovadas."
            ),
            evidencias=(
                _ev("em revisão", "ad_group_criterion.primary_status_reasons",
                    kw.em_revisao, quando),
            ),
            denominador=Denominador(
                rotulo="em revisão de política", quantos=kw.em_revisao,
                de_quantos=kw.observadas,
                minimo_para_proporcao=politica.minimo_para_proporcao,
            ),
            proximo_ato=(
                "aguardar o veredito do Google; não há ato de lance que o acelere"
            ),
        ))

    if kw.restritas:
        causas.append(Causa(
            status=POLICY_BLOCKED, escopo=ESCOPO_KEYWORD,
            frase=(
                f"{kw.restritas} de {kw.observadas} keywords estão aprovadas "
                "COM restrição — não é o mesmo que aprovadas."
            ),
            evidencias=(
                _ev("restritas", "ad_group_criterion.primary_status_reasons",
                    kw.restritas, quando),
            ),
            denominador=Denominador(
                rotulo="aprovadas com restrição", quantos=kw.restritas,
                de_quantos=kw.observadas,
                minimo_para_proporcao=politica.minimo_para_proporcao,
            ),
            proximo_ato="revisar a restrição declarada antes de mexer em lance",
        ))

    if kw.reprovadas:
        causas.append(Causa(
            status=POLICY_BLOCKED, escopo=ESCOPO_KEYWORD,
            frase="A conta reprovou keywords por política.",
            evidencias=(
                _ev("reprovadas", "ad_group_criterion.primary_status_reasons",
                    kw.reprovadas, quando),
            ),
            denominador=Denominador(
                rotulo="reprovadas por política", quantos=kw.reprovadas,
                de_quantos=kw.observadas,
                minimo_para_proporcao=politica.minimo_para_proporcao,
            ),
            proximo_ato="revisar as keywords reprovadas antes de mexer em lance",
        ))

    riscos: List[Evidencia] = []
    frases: List[str] = []
    den_risco: Optional[Denominador] = None
    if kw.baixa_qualidade:
        d = Denominador(
            rotulo="com Quality Score baixo", quantos=kw.baixa_qualidade,
            # ⚠️ Sem `max(...)`: `medidas_para_qualidade` já inclui as
            # classificadas por motivo declarado, e o `max` existia só para
            # tapar a contagem dupla que o `elif` anterior produzia.
            de_quantos=kw.medidas_para_qualidade,
            fora_da_conta=kw.sem_dado_de_qualidade,
            minimo_para_proporcao=politica.minimo_para_proporcao,
        )
        frases.append(d.frase(politica))
        den_risco = d
        riscos.append(_ev("baixa qualidade",
                          "ad_group_criterion.quality_info.quality_score",
                          kw.baixa_qualidade, quando))
    if kw.raramente_servidas:
        d = Denominador(
            rotulo="raramente servidas", quantos=kw.raramente_servidas,
            de_quantos=kw.observadas,
            minimo_para_proporcao=politica.minimo_para_proporcao,
        )
        frases.append(d.frase(politica))
        den_risco = den_risco or d
        riscos.append(_ev("raramente servidas",
                          "ad_group_criterion.primary_status_reasons",
                          kw.raramente_servidas, quando))
    if kw.clusters_redundantes:
        d = Denominador(
            rotulo="disputando a mesma intenção que outra",
            quantos=sum(
                len(set(c.variantes)) for c in kw.clusters if c.redundante
            ),
            de_quantos=kw.observadas,
            minimo_para_proporcao=politica.minimo_para_proporcao,
        )
        frases.append(
            f"{kw.clusters_redundantes} grupo(s) de intenção com mais de uma "
            f"variante — {d.frase(politica)}"
        )
        den_risco = den_risco or d
        riscos.append(_ev("clusters redundantes",
                          "ad_group_criterion.keyword.text (normalizado)",
                          kw.clusters_redundantes, quando, origem="derivado"))

    if riscos:
        causas.append(Causa(
            status=KEYWORD_STRUCTURE_RISK, escopo=ESCOPO_KEYWORD,
            frase="; ".join(frases),
            evidencias=tuple(riscos),
            denominador=den_risco,
            proximo_ato=(
                "revisar a estrutura de keywords com termos de busca reais; "
                "esta lane NÃO propõe negativa sem search term observado"
            ),
        ))
    return causas


def _causas_da_medicao(leitura: LeituraParaSentinela) -> List[Causa]:
    med = leitura.medicao
    camp = leitura.campanha
    quando = leitura.observado_em
    estrategia = (
        None if camp.bidding_strategy_type is None
        else str(camp.bidding_strategy_type).upper()
    )
    if estrategia not in ESTRATEGIAS_SMART_BIDDING:
        # Sem Smart Bidding, prontidão de mensuração não é causa de não entrega.
        return []

    if med.conversion_goal_status is None:
        return [Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_MEDICAO,
            frase=(
                f"A estratégia {estrategia} depende de conversão medida, e a "
                "prontidão de mensuração não foi apurada."
            ),
            evidencias=(
                _ev("estratégia", "campaign.bidding_strategy_type", estrategia, quando),
                _ev("prontidão", "trafego.prontidao.conversion_goal_status",
                    None, quando),
            ),
            proximo_ato="apurar a prontidão de mensuração antes de concluir",
        )]

    estado = str(med.conversion_goal_status).upper()
    if estado in {"NAO_PRONTO", "PARCIAL"}:
        return [Causa(
            status=MEASUREMENT_NOT_READY, escopo=ESCOPO_MEDICAO,
            frase=(
                f"A estratégia {estrategia} depende de conversão medida, e a "
                f"prontidão de mensuração está {estado}."
            ),
            evidencias=(
                _ev("estratégia", "campaign.bidding_strategy_type", estrategia, quando),
                _ev("prontidão", "trafego.prontidao.conversion_goal_status",
                    estado, quando),
                _ev("metas observadas", "customer_conversion_goal",
                    med.metas_observadas, quando),
                _ev("impedimento", "trafego.prontidao", med.impedimento, quando),
            ),
            proximo_ato=(
                "tratar a medição antes de julgar o lance: Smart Bidding sem "
                "conversão medida otimiza contra um sinal que não existe"
            ),
        )]
    if estado == "INDETERMINADO":
        return [Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_MEDICAO,
            frase=(
                f"A prontidão de mensuração está INDETERMINADO para {estrategia}. "
                "Não saber não é estar pronto."
            ),
            evidencias=(
                _ev("prontidão", "trafego.prontidao.conversion_goal_status",
                    estado, quando),
            ),
            proximo_ato="apurar a prontidão de mensuração antes de concluir",
        )]
    return []


def _causa_de_coleta(leitura: LeituraParaSentinela) -> List[Causa]:
    """A coleta em si é evidência. Falha, atraso e ausência são três estados."""
    quando = leitura.observado_em
    estado = leitura.estado_da_coleta

    if estado is None:
        return [Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_CAMPANHA,
            frase="Esta campanha nunca teve coleta de diagnóstico.",
            evidencias=(_ev("coleta", "trafego_google_inteligencia_coleta",
                            None, quando),),
            proximo_ato="rodar a coleta desta campanha antes de qualquer conclusão",
        )]
    if estado == "falhou":
        return [Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_CAMPANHA,
            frase=(
                "A última coleta desta campanha FALHOU. Os campos vazios abaixo "
                "são ausência de leitura, não ausência de entrega."
            ),
            evidencias=(_ev("coleta", "trafego_google_inteligencia_coleta.estado",
                            "falhou", quando),),
            proximo_ato="repetir a coleta; nada aqui afirma que a campanha esteja bem",
        )]
    if leitura.frescor == "velho":
        return [Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_CAMPANHA,
            frase=(
                "A última coleta é velha demais para sustentar diagnóstico. "
                "Zero medido numa leitura antiga não afirma zero agora."
            ),
            evidencias=(
                _ev("frescor", "coleta.coletada_em", "velho", quando),
            ),
            proximo_ato="repetir a coleta antes de concluir sobre entrega",
        )]
    if leitura.frescor == "nao_apurado":
        return [Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_CAMPANHA,
            frase="A coleta não trouxe carimbo de leitura; não há como datar o retrato.",
            evidencias=(_ev("frescor", "coleta.coletada_em", None, quando),),
            proximo_ato="repetir a coleta; um número sem data não é medição",
        )]
    if estado in {"inelegivel", "nao_suportado", "parcial", "vazio_confirmado"}:
        return [Causa(
            status=DATA_UNAVAILABLE, escopo=ESCOPO_CAMPANHA,
            frase=f"A coleta terminou em {estado}: o retrato não está completo.",
            evidencias=(_ev("coleta", "trafego_google_inteligencia_coleta.estado",
                            estado, quando),),
            proximo_ato="completar a coleta antes de concluir",
        )]
    return []


def _desconhecidos(leitura: LeituraParaSentinela) -> Tuple[str, ...]:
    """O que continua sem resposta. Dito, e não escondido num campo nulo."""
    faltando: List[str] = []
    if leitura.conta.status is None and not leitura.conta.acesso_negado:
        faltando.append("customer.status: o estado da conta não foi observado")
    if leitura.campanha.horas_ligada is None:
        faltando.append(
            "horas_ligada: não sabemos desde quando a campanha está ligada, "
            "e por isso a janela do guardião é indeterminada"
        )
    if leitura.metricas.impressoes is None:
        faltando.append("metrics.impressions: não medido nesta janela")
    if leitura.keywords.sem_dado_de_lance:
        faltando.append(
            f"{leitura.keywords.sem_dado_de_lance} keyword(s) sem lance ou sem "
            "estimativa de primeira página — fora do denominador de lance"
        )
    if leitura.keywords.sem_dado_de_qualidade:
        faltando.append(
            f"{leitura.keywords.sem_dado_de_qualidade} keyword(s) sem Quality "
            "Score observado"
        )
    if not leitura.recomendacoes.apurado:
        faltando.append(
            "recomendações do Google: "
            f"coleta em {leitura.recomendacoes.estado_da_coleta} — "
            "isto NÃO significa zero recomendações"
        )
    if leitura.destino.estado == "ausente":
        faltando.append("recibo de destino pago: ausente — ausência não é aprovação")
    elif leitura.destino.estado == "nao_consultado":
        faltando.append(
            "recibo de destino pago: não consultado por esta leitura — isto NÃO "
            "afirma que o destino esteja apto"
        )
    if leitura.medicao.conversion_goal_status is None:
        faltando.append("prontidão de mensuração: não apurada")
    for valor in leitura.valores_desconhecidos:
        faltando.append(f"valor não reconhecido da conta: {valor}")
    return tuple(faltando)


def _estado_da_evidencia(leitura: LeituraParaSentinela) -> str:
    """O estado da PROVA — derivado do MESMO lugar que lista os desconhecidos.

    ⚠️ A versão anterior repetia à mão uma lista de condições que já viviam em
    `_desconhecidos`, e as duas divergiam: com uma keyword sem Quality Score, a
    mesma resposta trazia `desconhecidos: ["1 keyword(s) sem Quality Score
    observado"]` E `estado_da_evidencia: "apurada"` — dizia não saber e
    declarava prova completa, no mesmo objeto.

    Derivar de `_desconhecidos` torna a contradição **impossível de escrever**:
    se há algo que não sabemos, a prova não está completa, por construção.
    Acrescentar um desconhecido novo passa a rebaixar a evidência sozinho,
    sem ninguém precisar lembrar de atualizar dois lugares.
    """
    if leitura.estado_da_coleta is None or leitura.frescor != "recente":
        return "ausente"
    if leitura.estado_da_coleta != "com_dados":
        return "parcial"
    return "parcial" if _desconhecidos(leitura) else "apurada"


def avaliar(
    leitura: LeituraParaSentinela,
    politica: PoliticaDoGuardiao = POLITICA_PADRAO,
) -> Veredito:
    """O veredito da sentinela. Puro: sem rede, sem relógio, sem I/O.

    A ordem das chamadas abaixo NÃO decide nada — quem decide é `PRECEDENCIA`,
    aplicada uma vez sobre o conjunto inteiro de causas. Deixar a ordem de
    avaliação decidir seria voltar ao defeito original, em que o primeiro `if`
    que casasse virava o veredito.
    """
    janela = janela_do_guardiao(leitura.campanha.horas_ligada, politica)

    candidatas: List[Causa] = []
    candidatas += _causas_da_conta(leitura)
    candidatas += _causa_de_coleta(leitura)
    candidatas += _causas_do_destino(leitura)
    candidatas += _causas_da_campanha(leitura, janela, politica)
    candidatas += _causas_dos_anuncios(leitura, politica)
    candidatas += _causas_das_keywords(leitura, politica)
    candidatas += _causas_da_medicao(leitura)

    # ⚠️ Campanha desligada CALA os degraus internos dela. Sem esta linha, uma
    # campanha pausada com keywords baratas sairia com veredito de lance, e o
    # operador mexeria em lance de uma campanha que ninguém ligou.
    if any(c.status == CAMPAIGN_OFF for c in candidatas):
        candidatas = [
            c for c in candidatas
            if c.status == CAMPAIGN_OFF or c.escopo in {ESCOPO_CONTA, ESCOPO_DESTINO}
        ]

    ordenadas = sorted(
        candidatas,
        key=lambda c: (ordem_da_causa(c.status), ESCOPOS.index(c.escopo)
                       if c.escopo in ESCOPOS else len(ESCOPOS)),
    )

    if ordenadas:
        primaria: Optional[Causa] = ordenadas[0]
        secundarias = tuple(ordenadas[1:])
        status = primaria.status
        escopo = primaria.escopo
        proximo = primaria.proximo_ato
    else:
        primaria = None
        secundarias = ()
        escopo = ESCOPO_CAMPANHA
        # ⚠️ `HEALTHY` só é alcançável aqui: nenhuma das quinze causas disse
        # nada E a prova está completa. Evidência parcial NUNCA sai saudável.
        if _estado_da_evidencia(leitura) == "apurada":
            status = HEALTHY
            proximo = "nenhum ato necessário nesta janela"
        else:
            status = DATA_UNAVAILABLE
            proximo = "completar a evidência antes de declarar saúde"

    return Veredito(
        versao=VERSAO_SENTINELA,
        customer_id=leitura.customer_id,
        volc_campaign_id=leitura.volc_campaign_id,
        escopo=escopo,
        status=status,
        severidade=severidade_de(status),
        observado_em=leitura.observado_em,
        janela_inicio=leitura.janela_inicio,
        janela_fim=leitura.janela_fim,
        janela_do_guardiao=janela,
        frescor=leitura.frescor,
        estado_da_evidencia=_estado_da_evidencia(leitura),
        causa_primaria=primaria,
        causas_secundarias=secundarias,
        desconhecidos=_desconhecidos(leitura),
        recomendacoes=leitura.recomendacoes,
        proximo_ato=proximo,
        chave=chave_do_incidente(
            customer_id=leitura.customer_id,
            volc_campaign_id=leitura.volc_campaign_id,
            escopo=escopo, status=status,
        ),
        mutacao_externa=False,
    )


# ── incidentes: identidade, idempotência, resolução e reabertura ────────────


@dataclass(frozen=True)
class Incidente:
    """O mesmo fato, ao longo do tempo — e uma linha só no quadro do operador.

    ⚠️ `ocorrencias` conta LEITURAS que viram o fato, não alertas emitidos. É a
    diferença entre "isto continua acontecendo há 12 coletas" e "mandei 12
    e-mails", e só a primeira é informação.
    """

    chave: str
    customer_id: str
    volc_campaign_id: str
    escopo: str
    status: str
    severidade: str
    primeira_vez_em: str
    ultima_vez_em: str
    ocorrencias: int = 1
    #: A janela do guardião da ÚLTIMA leitura. Informa sem fragmentar a chave.
    ultima_janela: Optional[str] = None
    resolvido_em: Optional[str] = None
    reconhecido_em: Optional[str] = None
    reconhecido_por: Optional[str] = None
    #: Quantas vezes já foi resolvido e voltou. Histórico preservado.
    reaberturas: int = 0
    frase: Optional[str] = None

    @property
    def aberto(self) -> bool:
        return self.resolvido_em is None

    def json(self) -> Dict[str, Any]:
        return {
            "chave": self.chave,
            "customer_id": self.customer_id,
            "volc_campaign_id": self.volc_campaign_id,
            "escopo": self.escopo,
            "status": self.status,
            "severidade": self.severidade,
            "primeira_vez_em": self.primeira_vez_em,
            "ultima_vez_em": self.ultima_vez_em,
            "ocorrencias": self.ocorrencias,
            "ultima_janela": self.ultima_janela,
            "resolvido_em": self.resolvido_em,
            "reconhecido_em": self.reconhecido_em,
            "reconhecido_por": self.reconhecido_por,
            "reaberturas": self.reaberturas,
            "aberto": self.aberto,
            "frase": self.frase,
        }


def incidente_do_veredito(veredito: Veredito, quando: str) -> Optional[Incidente]:
    """O incidente que este veredito abre — ou `None` quando não é incidente."""
    if not veredito.incidente:
        return None
    return Incidente(
        chave=veredito.chave,
        customer_id=veredito.customer_id,
        volc_campaign_id=veredito.volc_campaign_id,
        escopo=veredito.escopo,
        status=veredito.status,
        severidade=veredito.severidade,
        primeira_vez_em=quando,
        ultima_vez_em=quando,
        ocorrencias=1,
        ultima_janela=veredito.janela_do_guardiao,
        frase=veredito.causa_primaria.frase if veredito.causa_primaria else None,
    )


def consolidar(
    anteriores: Sequence[Incidente],
    atuais: Sequence[Incidente],
    quando: str,
) -> Tuple[Incidente, ...]:
    """Funde o que já existia com o que a leitura de agora viu.

    As quatro transições, e por que nenhuma delas pode ser omitida:

    · **repetição** — a mesma chave nas duas listas: `primeira_vez_em` é
      PRESERVADO, `ultima_vez_em` avança, `ocorrencias` sobe. É o que impede a
      mesma condição de inundar o operador (contraprova 13);
    · **resolução** — chave que existia e não veio agora: ganha `resolvido_em`.
      Sumir com ela apagaria a prova de que o problema existiu;
    · **reabertura** — chave resolvida que voltou: `primeira_vez_em` do
      ORIGINAL é mantido, `resolvido_em` é limpo e `reaberturas` sobe. O
      histórico é preservado, e é ele que distingue "problema novo" de
      "problema que já voltou três vezes" (contraprova 14);
    · **nova** — chave que nunca existiu: entra como está.

    O reconhecimento (`reconhecido_em`/`por`) atravessa a repetição: um
    operador que já disse "estou ciente" não precisa dizer de novo a cada
    coleta. Ele NÃO atravessa a reabertura: um problema que voltou é um fato
    novo, e presumir ciência sobre ele seria silenciar o alerta em nome do
    conforto.
    """
    por_chave: Dict[str, Incidente] = {i.chave: i for i in anteriores}
    vistos = {i.chave for i in atuais}
    saida: Dict[str, Incidente] = {}

    for atual in atuais:
        antigo = por_chave.get(atual.chave)
        if antigo is None:
            saida[atual.chave] = atual
            continue
        if antigo.resolvido_em is not None:
            saida[atual.chave] = replace(
                antigo,
                status=atual.status,
                severidade=atual.severidade,
                ultima_vez_em=quando,
                ultima_janela=atual.ultima_janela,
                ocorrencias=antigo.ocorrencias + 1,
                resolvido_em=None,
                reaberturas=antigo.reaberturas + 1,
                reconhecido_em=None,
                reconhecido_por=None,
                frase=atual.frase,
            )
            continue
        saida[atual.chave] = replace(
            antigo,
            status=atual.status,
            severidade=atual.severidade,
            ultima_vez_em=quando,
            ultima_janela=atual.ultima_janela,
            ocorrencias=antigo.ocorrencias + 1,
            frase=atual.frase,
        )

    for chave, antigo in por_chave.items():
        if chave in vistos:
            continue
        saida[chave] = (
            antigo if antigo.resolvido_em is not None
            else replace(antigo, resolvido_em=quando)
        )

    return tuple(
        sorted(
            saida.values(),
            key=lambda i: (
                i.resolvido_em is not None,
                ordem_da_causa(i.status),
                i.chave,
            ),
        )
    )
