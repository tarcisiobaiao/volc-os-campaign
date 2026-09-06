"""O veredito de RELER a campanha depois de criada — sete estados, e nenhum sinônimo.

## O problema que este módulo resolve

Até 06/09/2026 o resultado de reler a conta era um `Optional[bool]` chamado
`achou` (`routers/trafego.py`, `/reconciliar`) mais um quarto ramo fora do tipo
(um 409 de duplicidade consumada). Três valores soltos para uma pergunta que tem
sete respostas — e as sete pedem atos diferentes do operador:

    encontrado congruente   a campanha existe e é a que o plano descreve.
    encontrado divergente   existe, e NÃO é a que o plano descreve. ⚠️ Isto não
                            é sucesso, e o `True` de `achou` dizia que era.
    ausência provada        a leitura terminou, foi completa, e não há.
    leitura parcial         a leitura não terminou. ⚠️ NÃO prova ausência.
    falha                   a leitura quebrou. Também não prova ausência.
    não suportado           este canal não tem essa entidade. PMax não tem
                            anúncio, e `sem_anuncios: true` afirmava ausência
                            onde o fato é inexistência estrutural.
    ambíguo                 mais de um candidato. Decisão humana, nunca retry.

`achou=False` colapsava os quatro do meio: "não achei", "não terminei de
procurar", "quebrei procurando" e "aqui não existe isso para procurar" viravam a
mesma resposta — e a única saída óbvia para ela é *tentar de novo*, que é
exatamente o ato errado em três dos quatro casos.

## As duas regras absolutas

**Read-back NUNCA reenvia criação.** Este módulo é somente leitura, e não tem
função que crie, mute ou reenvie. A releitura existe para descobrir o que já
aconteceu; transformá-la num gatilho de retry é como uma resposta perdida vira
duas campanhas.

**Divergência NUNCA vira sucesso.** `DIVERGENTE` é um estado próprio e
`bloqueia` é `True` nele. Um status diferente de PAUSED, uma `final_url` que não
é a LP aprovada ou uma automação `OPTED_IN` onde o plano pediu `OPTED_OUT` são
achados que impedem a ativação — não detalhes de um sucesso.

## Vocabulário

Os nomes seguem o que o repositório já usa: `EstadoColeta`
(`volc_ads/inteligencia_google/modelo.py`) e `ObservationState`
(`volc_ads/observabilidade_pmax/types.py`). ⚠️ Deliberadamente NÃO se chama
`Veredito`: `sincronizador.Veredito` já existe e classifica RETENTATIVA de
requisição, que é outra pergunta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple


class EstadoDaReleitura(str, Enum):
    """As sete respostas possíveis de reler um objeto na conta."""

    #: Existe, e o que se leu bate com o que o plano descreve.
    CONGRUENTE = "congruente"
    #: Existe, e NÃO bate. ⚠️ Bloqueia — nunca é sucesso.
    DIVERGENTE = "divergente"
    #: A leitura terminou, foi completa, e não há. É uma conclusão.
    AUSENCIA_PROVADA = "ausencia_provada"
    #: A leitura não terminou (teto, paginação, corte). ⚠️ Não prova ausência.
    LEITURA_PARCIAL = "leitura_parcial"
    #: A leitura quebrou. Também não prova ausência.
    FALHA = "falha"
    #: Este canal não tem esta entidade. PMax não tem anúncio nem ad group.
    NAO_SUPORTADO = "nao_suportado"
    #: Mais de um candidato para a mesma identidade. Decisão humana.
    AMBIGUO = "ambiguo"


ESTADOS: Tuple[str, ...] = tuple(e.value for e in EstadoDaReleitura)

#: Os estados que NÃO permitem concluir nada sobre a conta.
#:
#: ⚠️ `AUSENCIA_PROVADA` não está aqui, e `LEITURA_PARCIAL` está. É essa a linha
#: inteira do módulo: uma leitura que bateu no teto é indistinguível de "conta
#: limpa" para quem só olha o tamanho da lista, e é essa confusão que libera a
#: segunda campanha.
ESTADOS_SEM_CONCLUSAO: Tuple[str, ...] = (
    EstadoDaReleitura.LEITURA_PARCIAL.value,
    EstadoDaReleitura.FALHA.value,
    EstadoDaReleitura.AMBIGUO.value,
)

#: Os estados que impedem ativação. `NAO_SUPORTADO` fica de fora de propósito:
#: ele descreve o CANAL, não a campanha, e bloquear por ele faria PMax nunca
#: poder ser ativado por não ter anúncio — que é o desenho dele.
ESTADOS_QUE_BLOQUEIAM: Tuple[str, ...] = (
    EstadoDaReleitura.DIVERGENTE.value,
    EstadoDaReleitura.LEITURA_PARCIAL.value,
    EstadoDaReleitura.FALHA.value,
    EstadoDaReleitura.AMBIGUO.value,
)

#: Os objetos que se relê. PMax é o único canal sem `grupo` e sem `anuncio`.
CAMPANHA = "campanha"
GRUPO = "grupo"
ANUNCIO = "anuncio"
ASSET_GROUP = "asset_group"
ASSET = "asset"

OBJETOS: Tuple[str, ...] = (CAMPANHA, GRUPO, ANUNCIO, ASSET_GROUP, ASSET)

#: De onde veio o corte, quando houve corte. ⚠️ `paginas` e `linhas` são tetos
#: DIFERENTES e a distinção é a correção de 06/09/2026: um limita quantas
#: páginas o pager percorre, o outro quantos registros a consulta devolve.
#: Chamar os dois de "páginas" fazia a evidência de um descrever o outro.
TETO_DE_PAGINAS = "paginas"
TETO_DE_LINHAS = "linhas"

TETOS: Tuple[str, ...] = (TETO_DE_PAGINAS, TETO_DE_LINHAS)


@dataclass(frozen=True)
class VereditoDaReleitura:
    """O que se leu sobre UM objeto, e o que isso significa.

    Frozen: ele entra no recibo, na resposta HTTP e no dossiê. Um objeto
    mutável deixaria alguém "melhorar" um veredito já apresentado.
    """

    canal: str
    objeto: str
    estado: EstadoDaReleitura
    #: O id na conta do Google, quando existe. `None` NÃO é "não existe": é
    #: "não foi lido" — e os estados dizem qual dos dois.
    id_externo: Optional[str] = None
    #: O que o plano dizia que deveria estar lá.
    esperado: Mapping[str, Any] = field(default_factory=dict)
    #: O que a conta respondeu.
    lido: Mapping[str, Any] = field(default_factory=dict)
    #: Os campos em que `esperado` e `lido` discordam. Vazio em CONGRUENTE.
    campos_divergentes: Tuple[str, ...] = ()
    #: Quantos candidatos a leitura encontrou. ⚠️ `None` = não contado; `0` =
    #: contado e não há. Colapsar os dois é o que faz truncamento virar
    #: ausência.
    quantidade: Optional[int] = None
    #: Por que, quando o estado não conclui. Obrigatória nesses casos.
    causa: str = ""
    #: Qual teto foi atingido, quando foi. `None` = nenhum.
    teto_atingido: Optional[str] = None
    #: A consulta que produziu esta leitura, para reconferência.
    consulta: str = ""
    #: Quem leu.
    procedencia: str = ""

    def __post_init__(self) -> None:
        if self.objeto not in OBJETOS:
            raise ValueError(
                f"objeto {self.objeto!r} não existe; conhecidos: "
                f"{', '.join(OBJETOS)}")
        if self.teto_atingido is not None and self.teto_atingido not in TETOS:
            raise ValueError(
                f"teto {self.teto_atingido!r} não existe; são {', '.join(TETOS)}"
                " — e eles são DIFERENTES: um conta páginas, o outro conta "
                "linhas.")
        object.__setattr__(self, "campos_divergentes",
                           tuple(self.campos_divergentes))
        if (self.estado is EstadoDaReleitura.DIVERGENTE
                and not self.campos_divergentes):
            raise ValueError(
                "divergência sem campo divergente nomeado: um bloqueio que não "
                "diz o que discorda é infalsificável e não ensina nada.")
        if (self.estado is EstadoDaReleitura.CONGRUENTE
                and self.campos_divergentes):
            raise ValueError(
                "congruente com campo divergente é contradição: a tela não "
                "teria como saber qual das duas metades é verdade.")
        if (self.estado.value in ESTADOS_SEM_CONCLUSAO
                and not str(self.causa).strip()):
            raise ValueError(
                f"{self.estado.value} sem causa: ignorância anônima é "
                "indistinguível de silêncio.")
        if (self.estado is EstadoDaReleitura.LEITURA_PARCIAL
                and self.teto_atingido is None
                and "teto" in str(self.causa).lower()):
            raise ValueError(
                "leitura parcial que fala de teto sem dizer QUAL teto. Página "
                "e linha são cortes diferentes, e a evidência tem de nomear o "
                "que de fato foi contado.")

    # ── as perguntas que a rota e a tela fazem ─────────────────────────────

    @property
    def concluiu(self) -> bool:
        """A leitura foi longe o bastante para afirmar alguma coisa?"""
        return self.estado.value not in ESTADOS_SEM_CONCLUSAO

    @property
    def bloqueia(self) -> bool:
        """Este veredito impede seguir? ⚠️ `DIVERGENTE` bloqueia, sempre."""
        return self.estado.value in ESTADOS_QUE_BLOQUEIAM

    @property
    def prova_ausencia(self) -> bool:
        """⚠️ SÓ `AUSENCIA_PROVADA`. É a propriedade mais importante daqui.

        Nenhum outro estado prova que não existe — nem `LEITURA_PARCIAL`, nem
        `FALHA`, nem `NAO_SUPORTADO`. Quem decide reenviar consulta ESTA
        propriedade, e nunca o tamanho de uma lista.
        """
        return self.estado is EstadoDaReleitura.AUSENCIA_PROVADA

    @property
    def sucesso(self) -> bool:
        """⚠️ SÓ `CONGRUENTE`. Divergência nunca vira sucesso."""
        return self.estado is EstadoDaReleitura.CONGRUENTE

    def para_json(self) -> Dict[str, Any]:
        return {
            "canal": self.canal,
            "objeto": self.objeto,
            "estado": self.estado.value,
            "id_externo": self.id_externo,
            "esperado": dict(self.esperado),
            "lido": dict(self.lido),
            "campos_divergentes": list(self.campos_divergentes),
            "quantidade": self.quantidade,
            "causa": self.causa or None,
            "teto_atingido": self.teto_atingido,
            "consulta": self.consulta or None,
            "procedencia": self.procedencia or None,
            "concluiu": self.concluiu,
            "bloqueia": self.bloqueia,
            "prova_ausencia": self.prova_ausencia,
            "sucesso": self.sucesso,
        }


# ═══════════════════════════════════════════════════════════════════════════
# A COMPOSIÇÃO — vários objetos, um veredito de conjunto
# ═══════════════════════════════════════════════════════════════════════════


def compor(vereditos: Tuple[VereditoDaReleitura, ...]) -> EstadoDaReleitura:
    """O estado do CONJUNTO, pelo pior de seus objetos.

    A ordem de gravidade não é alfabética nem histórica — ela é a ordem em que
    as respostas mudam o que o operador deve fazer:

      1. `DIVERGENTE`      existe algo errado na conta. Pare e olhe.
      2. `AMBIGUO`         existem dois. Decisão humana, nunca retry.
      3. `LEITURA_PARCIAL` não sei o bastante. Leia de novo.
      4. `FALHA`           não consegui ler. Conserte a leitura.
      5. `AUSENCIA_PROVADA` li tudo e não há.
      6. `NAO_SUPORTADO`   não há o que ler aqui.
      7. `CONGRUENTE`      está como deveria.

    ⚠️ `NAO_SUPORTADO` fica ACIMA de `CONGRUENTE` de propósito: um conjunto em
    que a única leitura possível foi "este canal não tem isso" não é um conjunto
    congruente — não se leu nada que pudesse ser congruente.

    Conjunto vazio devolve `FALHA`: um read-back que não produziu veredito
    nenhum não leu nada, e "não li nada" nunca é "está tudo certo".
    """
    if not vereditos:
        return EstadoDaReleitura.FALHA
    ordem = (
        EstadoDaReleitura.DIVERGENTE,
        EstadoDaReleitura.AMBIGUO,
        EstadoDaReleitura.LEITURA_PARCIAL,
        EstadoDaReleitura.FALHA,
        EstadoDaReleitura.AUSENCIA_PROVADA,
        EstadoDaReleitura.NAO_SUPORTADO,
        EstadoDaReleitura.CONGRUENTE,
    )
    presentes = {v.estado for v in vereditos}
    for estado in ordem:
        if estado in presentes:
            return estado
    return EstadoDaReleitura.FALHA


def resumo(vereditos: Tuple[VereditoDaReleitura, ...]) -> Dict[str, Any]:
    """O corpo que a rota devolve: o conjunto, seus objetos e o próximo ato."""
    estado = compor(vereditos)
    bloqueia = any(v.bloqueia for v in vereditos)
    return {
        "estado": estado.value,
        "bloqueia": bloqueia,
        # ⚠️ NUNCA "reenviar". Read-back não reenvia criação — em nenhum
        # desfecho, nem mesmo em `AUSENCIA_PROVADA`. Quem decide criar de novo é
        # a rota de criação, com autorização humana e ledger próprios.
        "proximo_ato": _proximo_ato(estado),
        "reenvio_por_readback": False,
        "objetos": [v.para_json() for v in vereditos],
    }


def _proximo_ato(estado: EstadoDaReleitura) -> str:
    return {
        EstadoDaReleitura.CONGRUENTE:
            "nada a fazer: o que está na conta é o que o plano descreve.",
        EstadoDaReleitura.DIVERGENTE:
            "abra a campanha na conta e compare os campos divergentes. A "
            "ativação fica bloqueada até a divergência ser explicada ou "
            "desfeita por ato autorizado.",
        EstadoDaReleitura.AUSENCIA_PROVADA:
            "a leitura foi completa e não encontrou o objeto. Se a criação era "
            "esperada, ela não aconteceu — a decisão de criar de novo é da "
            "rota de criação, com autorização humana.",
        EstadoDaReleitura.LEITURA_PARCIAL:
            "leia de novo. ⚠️ Esta leitura NÃO prova que o objeto não existe: a "
            "parte não lida da conta pode contê-lo.",
        EstadoDaReleitura.FALHA:
            "conserte a leitura e repita. Uma indisponibilidade do Google não é "
            "uma afirmação sobre a conta.",
        EstadoDaReleitura.NAO_SUPORTADO:
            "nada a fazer: este canal não tem esta entidade. Procure o fato "
            "equivalente no objeto que ele tem.",
        EstadoDaReleitura.AMBIGUO:
            "há mais de um candidato para a mesma identidade. Isto é decisão "
            "humana: nenhuma repetição automática é autorizada.",
    }[estado]
