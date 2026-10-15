"""O valor de uma conversão: receita medida por nós, na moeda da conta, ou nada.

## A regra que esta entrega existe para impor

O valor fixo de 10 na conta faz o ROAS nativo do Google ser falso: toda
conversão vale o mesmo, gere a sessão R$ 0,02 ou R$ 2,00. Trocar o 10 por
outro número inventado não conserta nada. Por isso este módulo **não tem valor
padrão nenhum**: ou existe receita observada, madura, de UMA fonte, convertida
por uma cotação versionada que o banco resolveu, ou o evento é PULADO com o
motivo nomeado. Nunca 10, nunca 0.

## Grão: sessão × coorte

A receita viva (JoinAds) chega por campanha-dia, não por sessão. Dividir o
total da coorte pelas sessões é RATEIO, uma estimativa. O ADR do ciclo
econômico (`docs/architecture/ADR-CICLO-ECONOMICO-COMPRA-MONETIZACAO.md`)
proíbe chamar isso de receita exata. Aqui o rateio só acontece se a política o
aceitar explicitamente, e a proveniência de cada evento diz `estimado: true`
e `metodo: rateio_uniforme_por_sessao`.

Domínio puro: sem rede, sem banco, sem relógio. `hoje` entra por parâmetro.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, Dict, Mapping, Optional, Union

#: Versão da REGRA de valor. Entra na impressão do valor: mudar a fórmula sem
#: mudar este número faria dois valores de regras diferentes parecerem o mesmo.
VERSAO_DA_REGRA = 1

GRAO_SESSAO = "sessao"
GRAO_COORTE = "coorte_campanha_dia"
GRAOS = (GRAO_SESSAO, GRAO_COORTE)

FONTES_DE_RECEITA = ("joinads", "gam")

#: Os modos de `cambio_resolver` (v23_01) que dão taxa utilizável.
CAMBIO_EXATA = "exata"
CAMBIO_ANTERIOR = "anterior"
MODOS_DE_CAMBIO_ACEITOS = (CAMBIO_EXATA, CAMBIO_ANTERIOR)
#: Valor declarado na proveniência quando receita e conta têm a mesma moeda.
CAMBIO_MOEDA_LOCAL = "moeda_local"

# ── motivos de pulo: cada um pede uma ação diferente ──────────────────────
PULO_RECEITA_AUSENTE = "receita_ausente"
PULO_RECEITA_ZERO = "receita_zero"
PULO_RECEITA_INVALIDA = "receita_invalida"
PULO_RECEITA_IMATURA = "receita_imatura"
PULO_OBSERVACAO_IMATURA = "observacao_coletada_antes_da_maturidade"
PULO_FONTE_NAO_ELEITA = "fonte_de_receita_nao_eleita"
PULO_GRAO_SEM_ACEITE = "rateio_de_coorte_sem_aceite"
PULO_COORTE_SEM_SESSOES = "coorte_sem_sessoes"
PULO_SEM_COTACAO = "sem_cotacao"
PULO_CAMBIO_DEFASADO = "cambio_defasado"
PULO_PAR_ERRADO = "cotacao_de_outro_par"
PULO_VALOR_ARREDONDA_ZERO = "valor_arredonda_para_zero"
PULO_DEFASAGEM_DESCONHECIDA = "defasagem_do_cambio_desconhecida"


def _iso4217(codigo: Optional[str]) -> bool:
    texto = str(codigo or "")
    return len(texto) == 3 and texto.isascii() and texto.isalpha() and texto.isupper()


def _decimal(bruto: Any) -> Optional[Decimal]:
    if bruto is None:
        return None
    if isinstance(bruto, float):
        # float binário já perdeu o dinheiro antes de chegar aqui
        raise TypeError("dinheiro chega como Decimal ou texto, nunca float")
    try:
        numero = bruto if isinstance(bruto, Decimal) else Decimal(str(bruto))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("NaN")
    return numero


# ═══════════════════════════════════════════════════════════════════════════
# O QUE AS PORTAS DEVOLVEM (contratos do W12, sem importar o W12)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Coorte:
    """O grão em que a receita existe: campanha-dia de um domínio.

    É a chave de `joinads_metrics` (`date`, `utm_campaign_value`,
    `joinads_domain`), a mesma que a v23_01 grava em `receita_observacao.chave`.
    """

    data_referencia: date
    utm_campaign_value: str
    dominio: str

    def json(self) -> Dict[str, Any]:
        return {"data_referencia": self.data_referencia.isoformat(),
                "utm_campaign_value": self.utm_campaign_value,
                "dominio": self.dominio}


@dataclass(frozen=True)
class ReceitaDatada:
    """Uma linha VIGENTE de `vw_receita_vigente` (v23_01), como a porta a lê.

    `receita=None` é ausência e continua ausência: a v23_01 grava NULL, nunca
    zero inventado, e este contrato preserva isso.
    """

    fonte: str
    observacao_id: int
    coorte: Coorte
    receita: Optional[Decimal]
    moeda: str
    #: Quando o banco recebeu esta versão (as-of). Não é o `updated_at` da origem.
    coletado_em: datetime
    grao: str = GRAO_COORTE

    def __post_init__(self) -> None:
        if self.fonte not in FONTES_DE_RECEITA:
            raise ValueError(f"fonte de receita {self.fonte!r} desconhecida")
        if self.grao not in GRAOS:
            raise ValueError(f"grão {self.grao!r} desconhecido")
        if not _iso4217(self.moeda):
            raise ValueError(f"moeda da receita {self.moeda!r} não é ISO-4217")
        if self.coletado_em.tzinfo is None:
            raise ValueError("coletado_em sem fuso: o as-of fica ambíguo")
        object.__setattr__(self, "receita", _decimal(self.receita))


@dataclass(frozen=True)
class CotacaoResolvida:
    """O que `cambio_resolver(data, par, defasagem, conhecido_ate)` devolveu.

    `taxa=None` nos modos `defasada` e `sem_cotacao`: o resolver nunca devolve
    constante, e este contrato também não.
    """

    par: str
    modo: str
    taxa: Optional[Decimal] = None
    cotacao_id: Optional[int] = None
    data_cotacao: Optional[date] = None
    as_of: Optional[datetime] = None
    fonte: Optional[str] = None
    defasagem_dias: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "taxa", _decimal(self.taxa))

    def json(self) -> Dict[str, Any]:
        return {
            "par": self.par, "modo": self.modo,
            "taxa": None if self.taxa is None else str(self.taxa),
            "cotacao_id": self.cotacao_id,
            "data_cotacao": None if self.data_cotacao is None else self.data_cotacao.isoformat(),
            "as_of": None if self.as_of is None else self.as_of.isoformat(),
            "fonte": self.fonte, "defasagem_dias": self.defasagem_dias,
        }


@dataclass(frozen=True)
class MoedaDaConta:
    """A moeda da conta DONA da ação, LIDA da conta (`customer.currency_code`).

    ⚠️ Sem default `BRL`. A conta 547-809-6539 provavelmente fatura em real, e
    "provavelmente" é exatamente o que não pode entrar num valor de conversão:
    o Google não converte, ele assume.
    """

    codigo: str
    lida_em: datetime
    customer_id: str

    def __post_init__(self) -> None:
        if not _iso4217(self.codigo):
            raise ValueError(f"moeda da conta {self.codigo!r} não é ISO-4217")
        if self.lida_em.tzinfo is None:
            raise ValueError("lida_em sem fuso")


# ═══════════════════════════════════════════════════════════════════════════
# POLÍTICA — o que o operador decide, sem default financeiro
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PoliticaDeValor:
    """Decisões do operador. Nada aqui tem default que mude dinheiro.

    `fonte_de_receita` é UMA: somar GAM e JoinAds sem prova de não sobreposição
    é dupla contagem (ADR do ciclo econômico). `maturidade_minima_dias` existe
    porque a JoinAds reescreve D-1 a D-3: mandar antes disso é mandar um número
    que muda, e o ajuste por `transactionId` substitui valor sem avisar.
    """

    fonte_de_receita: str
    maturidade_minima_dias: int
    max_defasagem_cambio_dias: int
    aceitar_rateio_de_coorte: bool = False
    versao: int = VERSAO_DA_REGRA

    def __post_init__(self) -> None:
        if self.fonte_de_receita not in FONTES_DE_RECEITA:
            raise ValueError(f"fonte {self.fonte_de_receita!r} desconhecida")
        for nome in ("maturidade_minima_dias", "max_defasagem_cambio_dias"):
            v = getattr(self, nome)
            if type(v) is not int or v < 0:
                raise ValueError(f"{nome} precisa ser inteiro >= 0")
        if type(self.aceitar_rateio_de_coorte) is not bool:
            raise ValueError("aceitar_rateio_de_coorte precisa ser bool explícito")

    def json(self) -> Dict[str, Any]:
        return {"versao": self.versao, "fonte_de_receita": self.fonte_de_receita,
                "maturidade_minima_dias": self.maturidade_minima_dias,
                "max_defasagem_cambio_dias": self.max_defasagem_cambio_dias,
                "aceitar_rateio_de_coorte": self.aceitar_rateio_de_coorte}


# ═══════════════════════════════════════════════════════════════════════════
# RESULTADO — valor com proveniência, ou pulo com motivo
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ValorMedido:
    valor: Decimal
    moeda: str
    estimado: bool
    proveniencia: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.valor, Decimal) or not self.valor.is_finite() or self.valor <= 0:
            raise ValueError("valor medido precisa ser Decimal finito > 0")
        if not _iso4217(self.moeda):
            raise ValueError(f"moeda {self.moeda!r} não é ISO-4217")

    def impressao(self) -> str:
        """Identidade do VALOR (número, moeda e de onde veio).

        É ela que distingue "mesmo evento, mesmo valor" (reexecução, no-op) de
        "mesmo evento, valor novo" (seria um ajuste no Google).
        """
        corpo = {"valor": str(self.valor), "moeda": self.moeda,
                 "proveniencia": self.proveniencia}
        texto = json.dumps(corpo, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), default=str)
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Pulo:
    motivo: str
    detalhe: str

    def __post_init__(self) -> None:
        if not self.motivo or not str(self.detalhe or "").strip():
            raise ValueError("pulo anônimo é indistinguível de silêncio")


Resultado = Union[ValorMedido, Pulo]

_CENTAVO = Decimal("0.01")


def calcular_valor(*, receita: Optional[ReceitaDatada],
                   cotacao: Optional[CotacaoResolvida],
                   moeda_da_conta: MoedaDaConta,
                   sessoes_da_coorte: Optional[int],
                   politica: PoliticaDeValor,
                   hoje: date) -> Resultado:
    """O valor de UMA conversão desta coorte, ou o motivo de não haver valor.

    ⚠️ A ordem das recusas é a ordem do que o operador consegue consertar
    primeiro: sem receita não adianta discutir câmbio.
    """
    if receita is None or receita.receita is None:
        return Pulo(PULO_RECEITA_AUSENTE,
                    "não há receita vigente para esta coorte; ausência não é zero "
                    "e não vira valor padrão")
    if receita.fonte != politica.fonte_de_receita:
        return Pulo(PULO_FONTE_NAO_ELEITA,
                    f"a receita veio de {receita.fonte!r} e a política elegeu "
                    f"{politica.fonte_de_receita!r}; somar fontes sem prova de não "
                    "sobreposição é dupla contagem")
    bruto = receita.receita
    if not bruto.is_finite() or bruto < 0:
        return Pulo(PULO_RECEITA_INVALIDA, f"receita {bruto!r} não é finita e >= 0")
    if bruto == 0:
        return Pulo(PULO_RECEITA_ZERO,
                    "a coorte rendeu zero medido; uma conversão de valor zero "
                    "inflaria a contagem sem dizer nada ao lance")
    referencia = receita.coorte.data_referencia
    idade = (hoje - referencia).days
    if idade < politica.maturidade_minima_dias:
        return Pulo(PULO_RECEITA_IMATURA,
                    f"a coorte tem {idade} dia(s) e a política exige "
                    f"{politica.maturidade_minima_dias}; a fonte ainda reescreve")
    # ⚠️ A maturidade é da OBSERVAÇÃO, não do calendário. Se o coletor parou
    # em D+1, a versão vigente é a de D+1 mesmo que hoje seja D+10: ela ainda
    # é o número imaturo. (Revisão adversarial W14, bloqueante 1.)
    idade_obs = (receita.coletado_em.astimezone(timezone.utc).date() - referencia).days
    if idade_obs < politica.maturidade_minima_dias:
        return Pulo(PULO_OBSERVACAO_IMATURA,
                    f"a versão vigente da receita foi coletada {idade_obs} dia(s) depois da "
                    f"coorte e a política exige {politica.maturidade_minima_dias}; o coletor "
                    "pode ter parado antes de a fonte fechar o número")
    if receita.grao == GRAO_COORTE and not politica.aceitar_rateio_de_coorte:
        return Pulo(PULO_GRAO_SEM_ACEITE,
                    "a receita só existe por campanha-dia; dividi-la por sessão é "
                    "estimativa e exige aceite explícito do operador na política")
    divisor = 1
    if receita.grao == GRAO_COORTE:
        if type(sessoes_da_coorte) is not int or sessoes_da_coorte <= 0:
            return Pulo(PULO_COORTE_SEM_SESSOES,
                        "a coorte não tem contagem de sessões; sem divisor não há "
                        "rateio, e o total inteiro em cada clique multiplicaria a receita")
        divisor = sessoes_da_coorte

    moeda = moeda_da_conta.codigo
    if receita.moeda == moeda:
        taxa = Decimal(1)
        cambio: Dict[str, Any] = {"modo": CAMBIO_MOEDA_LOCAL}
    else:
        par = f"{receita.moeda}/{moeda}"
        if cotacao is None or cotacao.taxa is None or cotacao.modo not in MODOS_DE_CAMBIO_ACEITOS:
            modo = None if cotacao is None else cotacao.modo
            return Pulo(PULO_SEM_COTACAO,
                        f"sem cotação utilizável para {par} em "
                        f"{receita.coorte.data_referencia.isoformat()} (modo {modo!r}); "
                        "nenhuma constante substitui a cotação")
        if cotacao.par != par:
            return Pulo(PULO_PAR_ERRADO,
                        f"a cotação resolvida é {cotacao.par!r} e a conversão pede {par!r}")
        if not cotacao.taxa.is_finite() or cotacao.taxa <= 0:
            return Pulo(PULO_SEM_COTACAO, f"taxa {cotacao.taxa!r} impossível")
        if cotacao.defasagem_dias is None and cotacao.modo != CAMBIO_EXATA:
            return Pulo(PULO_DEFASAGEM_DESCONHECIDA,
                        "cotação anterior sem defasagem declarada; ausência não é zero")
        if (cotacao.defasagem_dias or 0) > politica.max_defasagem_cambio_dias:
            return Pulo(PULO_CAMBIO_DEFASADO,
                        f"a cotação tem {cotacao.defasagem_dias} dia(s) de defasagem e a "
                        f"política aceita {politica.max_defasagem_cambio_dias}")
        taxa = cotacao.taxa
        cambio = cotacao.json()

    valor = (bruto * taxa / Decimal(divisor)).quantize(_CENTAVO, rounding=ROUND_HALF_EVEN)
    if valor <= 0:
        return Pulo(PULO_VALOR_ARREDONDA_ZERO,
                    f"{bruto} {receita.moeda} em {divisor} sessão(ões) dá menos de um "
                    f"centavo de {moeda} por conversão")

    estimado = receita.grao == GRAO_COORTE
    proveniencia = {
        "regra_versao": politica.versao,
        "politica": politica.json(),
        "receita": {
            "fonte": receita.fonte,
            "observacao_id": receita.observacao_id,
            "coorte": receita.coorte.json(),
            "valor_original": str(bruto),
            "moeda_original": receita.moeda,
            "coletado_em": receita.coletado_em.isoformat(),
            "grao": receita.grao,
        },
        "metodo": "rateio_uniforme_por_sessao" if estimado else "observado_por_sessao",
        "estimado": estimado,
        "sessoes_da_coorte": divisor if estimado else None,
        "cambio": cambio,
        "moeda_da_conta": {"codigo": moeda, "customer_id": moeda_da_conta.customer_id,
                           "lida_em": moeda_da_conta.lida_em.isoformat()},
    }
    return ValorMedido(valor=valor, moeda=moeda, estimado=estimado,
                       proveniencia=proveniencia)
