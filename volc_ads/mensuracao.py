"""Autoridade ÚNICA de prontidão de mensuração — por conta, canal, objetivo e lance.

## O problema que este módulo resolve

Até aqui, "a conta mede?" era decidida em três lugares que não se conheciam:

    backend/app/trafego/plano_mensuracao.py   lê os três recursos que decidem a
                                              meta efetiva, aplica o default
                                              documentado de `primary_for_goal`
                                              e separa ausência de zero.
    backend/app/trafego/prontidao.py          transforma isso nos quatro
                                              portões e recusa Smart Bidding em
                                              `exigir_para_criacao`.
    volc_ads/campanha/pmax.py                 tem a SUA checagem, sobre um
                                              recibo próprio, com regras
                                              próprias.

Três implementações da mesma frase produzem três respostas para a mesma conta.
E não é hipótese: elas **já divergiam** em 06/09/2026, no ponto que mais importa.

    `plano_mensuracao.AcaoDeConversao.primaria` é TRI-ESTADO, porque
    `primary_for_goal` tem *presence* no proto v25 e a doc oficial diz que
    ausente **vale true**. `primaria_efetiva` aplica esse default e diz que o
    está aplicando.

    `brief.AcaoDeConversao.primaria_para_meta` é `bool`, preenchido em
    `pmax.ler_mensuracao` por `bool(ca.primary_for_goal)`. Para uma ação em que
    o campo não veio, isso responde `False` — o veredito EXATAMENTE invertido no
    caso que a outra metade do sistema documentou como o caso perigoso.

    E `brief.AcaoDeConversao.valida_para_lance` exige
    `include_in_conversions_metric`, que está DEPRECIADO em favor de
    `primary_for_goal`. Um campo depreciado decidindo sozinho, em silêncio, é a
    definição de autoridade que ninguém escolheu.

Este módulo é a quarta coisa que passa a existir para as três primeiras
pararem de decidir: **elas medem, ele decide.**

## Por que ele mora em `volc_ads/` e não em `backend/app/`

A dependência do repositório aponta sempre `backend → volc_ads`; o contrário não
existe (medido: zero `from app.` em `volc_ads/`). Uma autoridade em
`backend/app/trafego/` seria inalcançável para `volc_ads/campanha/pmax.py`, e
"única" viraria "única do lado do servidor".

E ele é **stdlib pura**: nenhum import de `google.ads`, de `app.` ou de
`volc_ads.campanha`. É isso que permite ao backend importá-lo no topo — do mesmo
jeito que já importa `prontidao` — sem arrastar o SDK para o boot.

## Como as três fontes entram

Elas não entram. O que entra é um `Leitura`: fatos normalizados, com estado de
leitura e procedência. Cada lado escreve o seu adaptador (`de_plano`,
`de_recibo`) e a decisão acontece uma vez só, aqui.

## O que ele NUNCA faz

**Não cria nem altera `ConversionAction`.** Ele lê o que outros leram. A
proposta de ação nova continua sendo `plano_mensuracao.propor_acao_nova`, que
também não cria — e a criação segue recusada em `CODIGO_CRIACAO_RECUSADA`.

**Não devolve `True` por falta de evidência contrária.** Ausência de leitura é
`INDETERMINADA`, e `INDETERMINADA` recusa. Fail-closed é a regra do arquivo
inteiro, e cada ramo abaixo a repete de propósito.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence, Tuple

# ═══════════════════════════════════════════════════════════════════════════
# OS ESTADOS
# ═══════════════════════════════════════════════════════════════════════════

#: Provado: existe ação, ela vale para este objetivo e o sinal chegou recente.
PRONTA = "PRONTA"
#: Provado que NÃO: leu-se o bastante para afirmar que a conta não sustenta.
NAO_PRONTA = "NAO_PRONTA"
#: Ninguém leu, ou a leitura não concluiu. ⚠️ RECUSA — não saber não autoriza.
INDETERMINADA = "INDETERMINADA"
#: A estratégia pedida não aprende de conversão. A pergunta não se aplica.
NAO_APLICAVEL = "NAO_APLICAVEL"

ESTADOS: Tuple[str, ...] = (PRONTA, NAO_PRONTA, INDETERMINADA, NAO_APLICAVEL)

#: Os únicos estados que deixam Smart Bidding nascer.
ESTADOS_QUE_AUTORIZAM: Tuple[str, ...] = (PRONTA, NAO_APLICAVEL)


# ═══════════════════════════════════════════════════════════════════════════
# O OBJETIVO — a terceira coordenada da chave
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ "Objetivo" aqui é o que o LANCE persegue, e não o `advertising_channel_type`
# nem a meta comercial do briefing. Ele existe como coordenada própria porque
# duas estratégias podem exigir a mesma medição e objetivos diferentes exigem
# provas diferentes: contagem não prova valor, e valor não se deduz de contagem.

#: O lance não aprende de conversão nenhuma.
OBJETIVO_CLIQUE = "CLIQUE"
#: O lance aprende pela CONTAGEM de conversões.
OBJETIVO_CONVERSAO = "CONVERSAO"
#: O lance aprende pelo VALOR de cada conversão.
OBJETIVO_VALOR = "VALOR_DE_CONVERSAO"

OBJETIVOS: Tuple[str, ...] = (OBJETIVO_CLIQUE, OBJETIVO_CONVERSAO,
                              OBJETIVO_VALOR)

#: Estratégia → objetivo. ⚠️ FECHADA, e é isso que a torna um portão.
#:
#: A versão anterior deste raciocínio (em `prontidao.py`) tratava estratégia
#: desconhecida como "aprende por contagem" — fail-closed no papel e ABERTO na
#: prática: com a medição PRONTA, a string `ESTRATEGIA_INVENTADA` atravessava.
#: Aqui, o que não está no mapa não tem objetivo, e sem objetivo não há
#: exigência que se possa cumprir.
OBJETIVO_POR_ESTRATEGIA: Mapping[str, str] = {
    "MANUAL_CPC": OBJETIVO_CLIQUE,
    "MAXIMIZE_CONVERSIONS": OBJETIVO_CONVERSAO,
    "TARGET_CPA": OBJETIVO_CONVERSAO,
    "MAXIMIZE_CONVERSION_VALUE": OBJETIVO_VALOR,
    "TARGET_ROAS": OBJETIVO_VALOR,
}

ESTRATEGIAS_CONHECIDAS: Tuple[str, ...] = tuple(sorted(OBJETIVO_POR_ESTRATEGIA))

#: Os canais que esta autoridade sabe adjudicar. Um canal fora daqui não recebe
#: veredito frouxo: recebe `CANAL_DESCONHECIDO`, que recusa.
CANAIS: Tuple[str, ...] = ("SEARCH", "DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX")

#: Apelido de tela. `PMAX` nunca é valor de contrato (ADR-18); é traduzido aqui
#: pela mesma razão que `campanha/perfil.py` o traduz na fronteira dele.
APELIDOS_DE_CANAL: Mapping[str, str] = {"PMAX": "PERFORMANCE_MAX"}

#: A partir de quantos dias uma conversão deixa de provar que o sinal CHEGA.
#: Mesmo número de `plano_mensuracao.JANELA_DE_RECENCIA_DIAS`, e ele está
#: repetido aqui de propósito: este módulo não pode importar o backend, e um
#: número que muda de um lado sem o outro é pior que um número declarado duas
#: vezes com a razão escrita. O teste `test_janela_de_recencia_e_a_mesma`
#: cobra a igualdade.
JANELA_DE_RECENCIA_DIAS = 30

#: A partir de quando uma LEITURA que se DATA deixa de ser fresca.
#:
#: ⚠️ Fora dela o veredito é `INDETERMINADA`, nunca `NAO_PRONTA`: uma leitura
#: velha não afirma que a conta parou de medir, afirma que ninguém olhou hoje.
#:
#: ⚠️ E ela só se aplica a quem SE DATA. `ReciboDeMensuracao` carrega `lido_em`
#: e cai sob esta janela (é a mesma de `pmax.IDADE_MAXIMA_DA_MENSURACAO`).
#: `PlanoDeMensuracao` NÃO carrega o instante da própria leitura — ele carrega a
#: data da última CONVERSÃO, que é outro fato. Exigir data de quem não a tem
#: transformaria a autoridade num portão que nunca abre para o canal que hoje
#: cria; e um portão que nunca abre não protege, só esconde a decisão. Quem não
#: se data responde às outras duas perguntas — QUEM leu (`procedencia`) e quão
#: recente é o SINAL (`dias_desde_a_ultima`) — e a falta da data vira AVISO
#: nomeado, nunca silêncio.
IDADE_MAXIMA_DA_LEITURA = timedelta(hours=24)


# ═══════════════════════════════════════════════════════════════════════════
# OS ESTADOS DE LEITURA — ausência NUNCA é zero
# ═══════════════════════════════════════════════════════════════════════════
#
# Os mesmos nomes de `plano_mensuracao.ESTADOS_DE_LEITURA`, pelo mesmo motivo:
# o operador e o banco já leem estas palavras, e um segundo vocabulário para o
# mesmo fato obrigaria a tela a traduzir — que é onde a tradução erra.

NAO_COLETADO = "nao_coletado"      # ninguém perguntou
COM_DADOS = "com_dados"            # perguntou e veio
VAZIO_CONFIRMADO = "vazio_confirmado"  # perguntou, respondeu, e não há
PARCIAL = "parcial"                # respondeu pela metade; NÃO prova ausência
FALHOU = "falhou"                  # perguntou e quebrou

ESTADOS_DE_LEITURA: Tuple[str, ...] = (
    NAO_COLETADO, COM_DADOS, VAZIO_CONFIRMADO, PARCIAL, FALHOU)

#: Os que NÃO concluem. ⚠️ `PARCIAL` mora aqui: leitura truncada não prova
#: ausência, e tratá-la como `VAZIO_CONFIRMADO` é como uma consulta que bateu no
#: teto vira "a conta não tem nada".
ESTADOS_SEM_CONCLUSAO: Tuple[str, ...] = (NAO_COLETADO, PARCIAL, FALHOU)


# ═══════════════════════════════════════════════════════════════════════════
# OS CÓDIGOS DE BLOQUEIO
# ═══════════════════════════════════════════════════════════════════════════
#
# Código estável + frase para humano. O código é o que o teste, o ledger e a
# tela comparam; a frase é o que o operador lê. Uma resposta que só tem a frase
# obriga o teste a casar texto, e aí a mensagem não pode mais ser melhorada.

SEM_LEITURA = "SEM_LEITURA"
LEITURA_PARCIAL = "LEITURA_PARCIAL"
LEITURA_FALHOU = "LEITURA_FALHOU"
LEITURA_VELHA = "LEITURA_VELHA"
SEM_DATA_DE_LEITURA = "SEM_DATA_DE_LEITURA"
SEM_PROCEDENCIA = "SEM_PROCEDENCIA"
SEM_ACAO_DE_CONVERSAO = "SEM_ACAO_DE_CONVERSAO"
ACAO_EM_ESTADO_INVALIDO = "ACAO_EM_ESTADO_INVALIDO"
ACAO_NAO_PRIMARIA = "ACAO_NAO_PRIMARIA"
META_NAO_BIDDABLE = "META_NAO_BIDDABLE"
OBJETIVO_INCOMPATIVEL = "OBJETIVO_INCOMPATIVEL"
SEM_VALOR_DECLARADO = "SEM_VALOR_DECLARADO"
SINAL_NAO_COMPROVADO = "SINAL_NAO_COMPROVADO"
SINAL_ANTIGO = "SINAL_ANTIGO"
SINAL_SEM_DATA = "SINAL_SEM_DATA"
ESTRATEGIA_DESCONHECIDA = "ESTRATEGIA_DESCONHECIDA"
ESTRATEGIA_FORA_DO_CANAL = "ESTRATEGIA_FORA_DO_CANAL"
CANAL_DESCONHECIDO = "CANAL_DESCONHECIDO"
#: ⚠️ OS DOIS CÓDIGOS DO CAMPO DEPRECIADO, e eles dizem coisas diferentes.
#:
#: `include_in_conversions_metric` está DEPRECIADO em favor de
#: `primary_for_goal`, e mesmo assim continua sendo o campo que decide se a ação
#: entra na métrica `conversions` que o lance otimiza. Ou seja: ele ainda tem
#: efeito, e fingir que não teria produziria uma autorização que a conta não
#: honra.
#:
#: O que esta autoridade proíbe é ele decidir **em silêncio**. Quando ele é a
#: causa da recusa, a recusa DIZ que a causa é um campo depreciado
#: (`FORA_DA_METRICA_DE_CONVERSOES`); quando ele apenas discorda do campo
#: vigente sem mudar o veredito, a discordância vira AVISO
#: (`CAMPO_DEPRECADO_DIVERGENTE`) — porque é ela que explica por que o painel do
#: Google mostra uma coisa e este sistema mostra outra.
FORA_DA_METRICA_DE_CONVERSOES = "FORA_DA_METRICA_DE_CONVERSOES"
CAMPO_DEPRECADO_DIVERGENTE = "CAMPO_DEPRECADO_DIVERGENTE"


@dataclass(frozen=True)
class Bloqueio:
    """Uma razão nomeada para o veredito não ser `PRONTA`."""

    codigo: str
    causa: str
    #: De onde veio o fato que produziu este bloqueio.
    fonte: str = ""

    def para_json(self) -> dict:
        return {"codigo": self.codigo, "causa": self.causa,
                "fonte": self.fonte}


# ═══════════════════════════════════════════════════════════════════════════
# A ENTRADA NORMALIZADA
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AcaoLida:
    """Uma `ConversionAction` como esta autoridade precisa dela.

    ⚠️ `primaria` e `incluida_em_metricas` são AMBOS `Optional[bool]`, e os três
    valores de cada um importam.

    `primary_for_goal` tem *presence* no proto v25 e a doc oficial diz que
    **ausente vale `true`**; `None` aqui significa "não declarado", e quem
    aplica o default é `primaria_efetiva` — que diz, no nome, que está
    aplicando. Ler isto com `bool(...)` devolve `False` para uma ação que o
    Google trata como primária.

    `include_in_conversions_metric` está DEPRECIADO. Ele nunca decide sozinho
    (ver `ACAO_NAO_PRIMARIA` × `CAMPO_DEPRECADO_SEM_AUTORIDADE` em `avaliar`);
    quando discorda de `primary_for_goal`, a discordância vira achado.
    """

    id: str
    nome: str = ""
    categoria: str = ""
    tipo: str = ""
    status: str = ""
    #: ⚠️ TRI-ESTADO. `None` = o campo não veio.
    primaria: Optional[bool] = None
    #: ⚠️ TRI-ESTADO, e DEPRECIADO. Nunca decide sozinho.
    incluida_em_metricas: Optional[bool] = None
    #: A ação carrega valor por conversão? `None` = `value_settings` não lido.
    carrega_valor: Optional[bool] = None
    #: Conversões medidas na janela. ⚠️ `None` = ninguém mediu; `0.0` = mediu e
    #: deu zero. Colapsar os dois faz uma conta nunca consultada parecer uma
    #: conta sem conversão.
    conversoes_na_janela: Optional[float] = None
    #: Dias desde a última conversão. `None` NUNCA vira um número grande.
    dias_desde_a_ultima: Optional[int] = None

    @property
    def primaria_efetiva(self) -> bool:
        """O default documentado, aplicado onde ele é dito em voz alta.

        > "By default, `primary_for_goal` will be true if not set."
        """
        return True if self.primaria is None else bool(self.primaria)

    @property
    def ativa(self) -> bool:
        return str(self.status or "").strip().upper() == "ENABLED"

    @property
    def deprecado_discorda(self) -> bool:
        """O campo depreciado diz o contrário do vigente? Isso é informação.

        Só quando os DOIS foram lidos. Um `None` de qualquer lado é ausência, e
        ausência não discorda de nada.
        """
        if self.primaria is None or self.incluida_em_metricas is None:
            return False
        return bool(self.primaria) != bool(self.incluida_em_metricas)

    def para_json(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "categoria": self.categoria,
            "tipo": self.tipo,
            "status": self.status,
            "primaria": self.primaria,
            "primaria_efetiva": self.primaria_efetiva,
            "incluida_em_metricas": self.incluida_em_metricas,
            "carrega_valor": self.carrega_valor,
            "conversoes_na_janela": self.conversoes_na_janela,
            "dias_desde_a_ultima": self.dias_desde_a_ultima,
            "ativa": self.ativa,
            "deprecado_discorda": self.deprecado_discorda,
        }


@dataclass(frozen=True)
class Leitura:
    """Os fatos lidos da conta, com estado e procedência.

    ⚠️ `estado` e `acoes` são coisas diferentes e as duas são obrigatórias.
    `acoes=()` com `estado=vazio_confirmado` é o fato caro "a conta não tem
    ação de conversão"; `acoes=()` com `estado=nao_coletado` é "ninguém
    perguntou". Só o primeiro conclui.

    ⚠️ `procedencia` é obrigatória quando o estado conclui. Um fato sem dono não
    é evidência: ele não pode ser reconferido, e um bloqueio que ninguém
    consegue reconferir envelhece em silêncio.
    """

    estado: str = NAO_COLETADO
    acoes: Tuple[AcaoLida, ...] = ()
    #: Quem leu, e como. Ex.: `volc_ads.campanha.pmax.ler_mensuracao (v25)`.
    procedencia: str = ""
    #: Quando a leitura aconteceu, ISO-8601 com fuso. Vazio = não declarado.
    lido_em: str = ""
    #: A meta efetiva já resolvida por quem leu os três recursos que decidem.
    #: `None` = não resolvida — o que NÃO é o mesmo que "não é biddable".
    meta_biddable: Optional[bool] = None
    #: A causa, quando o estado não conclui.
    causa: str = ""

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS_DE_LEITURA:
            raise ValueError(
                f"estado de leitura {self.estado!r} não existe; conhecidos: "
                f"{', '.join(ESTADOS_DE_LEITURA)}")
        object.__setattr__(self, "acoes", tuple(self.acoes))
        if self.estado in ESTADOS_SEM_CONCLUSAO and not str(self.causa).strip():
            raise ValueError(
                "leitura que não conclui precisa dizer por quê: ignorância "
                "anônima é indistinguível de silêncio")

    @property
    def concluiu(self) -> bool:
        return self.estado in (COM_DADOS, VAZIO_CONFIRMADO)

    def para_json(self) -> dict:
        return {
            "estado": self.estado,
            "procedencia": self.procedencia,
            "lido_em": self.lido_em,
            "meta_biddable": self.meta_biddable,
            "causa": self.causa,
            "acoes": [a.para_json() for a in self.acoes],
        }


def leitura_ausente(causa: str = "") -> Leitura:
    """A leitura que ninguém fez. Existe como valor para não existir como `None`."""
    return Leitura(
        estado=NAO_COLETADO,
        causa=(causa or
               "a mensuração desta conta não foi lida nesta chamada. Não ter "
               "lido não é o mesmo que a conta não medir."))


# ═══════════════════════════════════════════════════════════════════════════
# O VEREDITO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Veredito:
    """A resposta da autoridade para UMA chave (conta, canal, objetivo, lance).

    Frozen: ele vira resposta HTTP, entra no plano e é comparado por teste. Um
    objeto mutável deixaria alguém "melhorar" um veredito já apresentado — o
    mesmo motivo pelo qual `prontidao.Prontidao` é frozen.
    """

    estado: str
    customer_id: str
    canal: str
    objetivo: str
    estrategia_lance: str
    bloqueios: Tuple[Bloqueio, ...] = ()
    #: A ação que sustentaria o lance, quando existe uma.
    acao_eleita: Optional[AcaoLida] = None
    #: Achados que não bloqueiam e que ninguém deveria descobrir depois.
    avisos: Tuple[Bloqueio, ...] = ()
    leitura: Leitura = field(default_factory=leitura_ausente)

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS:
            raise ValueError(f"estado {self.estado!r} não existe")
        object.__setattr__(self, "bloqueios", tuple(self.bloqueios))
        object.__setattr__(self, "avisos", tuple(self.avisos))
        if self.estado == PRONTA and self.bloqueios:
            raise ValueError(
                "veredito PRONTA com bloqueio é contradição: a tela não teria "
                "como saber qual das duas metades é verdade")
        if self.estado in (NAO_PRONTA, INDETERMINADA) and not self.bloqueios:
            raise ValueError(
                f"veredito {self.estado} sem bloqueio nomeado. Uma recusa sem "
                "razão é infalsificável e não ensina nada a quem a recebe")

    @property
    def autoriza(self) -> bool:
        """Este veredito deixa o lance pedido NASCER?

        ⚠️ Só `PRONTA` e `NAO_APLICAVEL`. `INDETERMINADA` recusa, e essa é a
        linha inteira deste módulo: falha de leitura do Google não é permissão.
        """
        return self.estado in ESTADOS_QUE_AUTORIZAM

    @property
    def codigos(self) -> Tuple[str, ...]:
        return tuple(b.codigo for b in self.bloqueios)

    def resumo(self) -> str:
        if not self.bloqueios:
            return ""
        return "; ".join(b.causa for b in self.bloqueios)

    def para_json(self) -> dict:
        return {
            "estado": self.estado,
            "autoriza": self.autoriza,
            "customer_id": self.customer_id,
            "canal": self.canal,
            "objetivo": self.objetivo,
            "estrategia_lance": self.estrategia_lance,
            "bloqueios": [b.para_json() for b in self.bloqueios],
            "avisos": [a.para_json() for a in self.avisos],
            "acao_eleita": (None if self.acao_eleita is None
                            else self.acao_eleita.para_json()),
            "leitura": self.leitura.para_json(),
        }


class MensuracaoNaoProvada(RuntimeError):
    """O lance pedido exige prova que esta conta não tem. Nada foi enviado."""

    def __init__(self, veredito: "Veredito") -> None:
        super().__init__(_frase_da_recusa(veredito))
        self.veredito = veredito


def _frase_da_recusa(v: "Veredito") -> str:
    return (
        f"{v.estrategia_lance} em {v.canal} exige mensuração provada e ela "
        f"está {v.estado}: {v.resumo() or 'sem razão registrada'}. "
        "Nada foi enviado ao Google. Suba em MANUAL_CPC — que não aprende de "
        "conversão e por isso não depende desta prova — ou conserte a medição "
        "antes.")


# ═══════════════════════════════════════════════════════════════════════════
# A DECISÃO
# ═══════════════════════════════════════════════════════════════════════════


def canonizar_canal(canal: Any) -> str:
    bruto = str(canal or "").strip().upper()
    return APELIDOS_DE_CANAL.get(bruto, bruto)


def objetivo_de(estrategia_lance: Any) -> Optional[str]:
    """O objetivo que esta estratégia persegue, ou `None` se ela é desconhecida."""
    return OBJETIVO_POR_ESTRATEGIA.get(
        str(estrategia_lance or "").strip().upper())


def _idade_da_leitura(lido_em: str, agora: Optional[datetime]) -> Optional[timedelta]:
    """Quanto tempo faz. `None` quando a data não é legível — que NÃO é zero."""
    texto = str(lido_em or "").strip()
    if not texto:
        return None
    try:
        quando = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    referencia = agora or datetime.now(timezone.utc)
    if referencia.tzinfo is None:
        referencia = referencia.replace(tzinfo=timezone.utc)
    return referencia - quando


def avaliar(
    *,
    customer_id: Any,
    canal: Any,
    estrategia_lance: Any,
    leitura: Optional[Leitura] = None,
    lances_do_canal: Optional[Sequence[str]] = None,
    exige_valor_declarado: bool = False,
    agora: Optional[datetime] = None,
) -> Veredito:
    """O veredito para uma chave. **Não fala com o Google e não escreve nada.**

    A ordem das recusas é deliberada e vai do que é decidido no PEDIDO para o
    que é decidido no MUNDO:

      1. canal conhecido        — sem canal, não há contrato a cobrar;
      2. estratégia conhecida   — sem objetivo, não há exigência a cumprir;
      3. estratégia do canal    — o canal declara o que aceita;
      4. objetivo sem conversão — `MANUAL_CPC` sai por `NAO_APLICAVEL`;
      5. leitura concluída      — ausência, parcial e falha recusam ANTES de
                                  qualquer conclusão sobre a conta;
      6. frescor e procedência  — leitura velha ou anônima não decide;
      7. os fatos da conta      — ação, estado, primária, objetivo, valor, sinal.

    Nenhum passo posterior pode "consertar" um anterior: quem não sabe qual é o
    objetivo não tem como saber se a conta o sustenta.

    `exige_valor_declarado` existe porque a prova de VALOR tem duas fontes
    legítimas e este módulo só enxerga uma. Quando `carrega_valor` não foi lido
    (`None`), quem chama pode declarar que existe regra de valor no perfil de
    mensuração — e assume a declaração no lugar da leitura.
    """
    conta = str(customer_id or "").strip()
    nome_do_canal = canonizar_canal(canal)
    estrategia = str(estrategia_lance or "MANUAL_CPC").strip().upper()
    lida = leitura or leitura_ausente()
    bloqueios: list[Bloqueio] = []
    avisos: list[Bloqueio] = []

    def veredito(estado: str, *, acao: Optional[AcaoLida] = None) -> Veredito:
        return Veredito(
            estado=estado, customer_id=conta, canal=nome_do_canal,
            objetivo=objetivo_de(estrategia) or "",
            estrategia_lance=estrategia,
            bloqueios=tuple(bloqueios), avisos=tuple(avisos),
            acao_eleita=acao, leitura=lida)

    # ── 1. o canal ─────────────────────────────────────────────────────────
    if nome_do_canal not in CANAIS:
        bloqueios.append(Bloqueio(
            CANAL_DESCONHECIDO,
            f"{nome_do_canal or '(canal ausente)'} não é um canal que esta "
            f"autoridade saiba adjudicar (conhecidos: {', '.join(CANAIS)}). "
            "Sem saber o canal, não há contrato de mensuração a cobrar.",
            fonte="volc_ads.mensuracao.CANAIS"))
        return veredito(INDETERMINADA)

    # ── 2. a estratégia ────────────────────────────────────────────────────
    objetivo = objetivo_de(estrategia)
    if objetivo is None:
        bloqueios.append(Bloqueio(
            ESTRATEGIA_DESCONHECIDA,
            f"{estrategia} não é uma estratégia de lance que esta autoridade "
            f"saiba classificar (conhecidas: {', '.join(ESTRATEGIAS_CONHECIDAS)}). "
            "Sem saber se ela aprende de conversão, de valor ou de nenhum dos "
            "dois, não há como dizer o que ela exige — e não conhecer nunca "
            "autoriza.",
            fonte="volc_ads.mensuracao.OBJETIVO_POR_ESTRATEGIA"))
        return veredito(INDETERMINADA)

    # ── 3. a estratégia é DESTE canal? ─────────────────────────────────────
    #
    # ⚠️ A lista vem de fora, e é de propósito: quem declara o que um canal
    # aceita é o módulo do canal (`display.LANCES_PERMITIDOS` e irmãos). Copiar
    # a lista aqui criaria a segunda verdade que este módulo existe para
    # eliminar. Quando ela não é passada, este passo simplesmente não roda —
    # e não rodar é diferente de aprovar: os passos seguintes continuam.
    if lances_do_canal is not None:
        aceitos = tuple(str(x).strip().upper() for x in lances_do_canal)
        if estrategia not in aceitos:
            bloqueios.append(Bloqueio(
                ESTRATEGIA_FORA_DO_CANAL,
                f"{nome_do_canal} aceita "
                f"{', '.join(aceitos) or '(nenhuma estratégia declarada)'} e o "
                f"pedido traz {estrategia}. O canal recusa o objetivo antes de "
                "a conta ser consultada.",
                fonte=f"perfil de {nome_do_canal}"))
            return veredito(NAO_PRONTA)

    # ── 4. o lance que não aprende ─────────────────────────────────────────
    #
    # ⚠️ `MANUAL_CPC` sai por `NAO_APLICAVEL`, e não por `PRONTA`. Recusá-lo
    # porque a conta não mede transformaria uma conta sem conversão numa conta
    # sem campanha — e o canário pausado existe para colher veredito de política
    # sem depender de medição. O portão é sobre APRENDER, não sobre nascer.
    if objetivo == OBJETIVO_CLIQUE:
        return veredito(NAO_APLICAVEL)

    # ── 5. a leitura concluiu? ─────────────────────────────────────────────
    if lida.estado == NAO_COLETADO:
        bloqueios.append(Bloqueio(
            SEM_LEITURA, lida.causa or "a mensuração não foi lida.",
            fonte=lida.procedencia))
        return veredito(INDETERMINADA)
    if lida.estado == PARCIAL:
        bloqueios.append(Bloqueio(
            LEITURA_PARCIAL,
            (lida.causa or "a leitura da mensuração não terminou") +
            ". Uma leitura truncada NÃO prova que a conta não mede: a parte "
            "não lida pode conter exatamente a ação que faltava.",
            fonte=lida.procedencia))
        return veredito(INDETERMINADA)
    if lida.estado == FALHOU:
        bloqueios.append(Bloqueio(
            LEITURA_FALHOU,
            (lida.causa or "a leitura da mensuração falhou") +
            ". Uma indisponibilidade do Google não vira uma autorização do VOLC.",
            fonte=lida.procedencia))
        return veredito(INDETERMINADA)

    # ── 6. frescor e procedência da LEITURA ────────────────────────────────
    if not str(lida.procedencia or "").strip():
        bloqueios.append(Bloqueio(
            SEM_PROCEDENCIA,
            "a leitura da mensuração chegou sem dizer quem a fez. Um fato sem "
            "dono não pode ser reconferido, e um bloqueio que ninguém consegue "
            "reconferir envelhece em silêncio.",
            fonte="(ausente)"))
        return veredito(INDETERMINADA)

    idade = _idade_da_leitura(lida.lido_em, agora)
    if idade is None:
        # ⚠️ AVISO, e não bloqueio — ver `IDADE_MAXIMA_DA_LEITURA`. A fonte que
        # não se data ainda respondeu QUEM leu e quão recente é o SINAL; são
        # essas duas que decidem. O aviso existe para que "esta leitura não se
        # data" nunca vire uma ausência silenciosa no dossiê.
        avisos.append(Bloqueio(
            SEM_DATA_DE_LEITURA,
            f"a leitura da mensuração não declara QUANDO aconteceu "
            f"({lida.lido_em!r}); a janela de {int(IDADE_MAXIMA_DA_LEITURA.total_seconds() // 3600)}h "
            "não pôde ser aplicada a ela. O frescor do SINAL continua sendo "
            "exigido abaixo.",
            fonte=lida.procedencia))
    elif idade > IDADE_MAXIMA_DA_LEITURA:
        # ⚠️ NÃO RETORNA AQUI, e o `return` que existia era um FAIL-OPEN.
        #
        # Achado da revisão adversarial de 06/09/2026, reproduzido: `LEITURA_VELHA`
        # saía antecipadamente E estava em `pmax.AVISOS_DE_MENSURACAO`. Numa conta
        # SEM NENHUMA ação de conversão, o recibo fresco produzia
        # `SEM_ACAO_DE_CONVERSAO` → `r.erro` → campanha bloqueada; o MESMO recibo
        # 25h mais velho produzia só `LEITURA_VELHA` → `r.aviso` → `r.ok=True` e o
        # payload seguia para o `validate_only`. Ou seja: quanto mais VELHA a
        # leitura, mais permissivo o canal — o oposto exato do que a idade
        # significa.
        #
        # A idade continua sendo um bloqueio nomeado; o que ela deixa de fazer é
        # esconder os fatos da conta que vêm no passo 7. Os dois viajam juntos, e
        # quem classifica erro × aviso decide sobre a lista inteira.
        bloqueios.append(Bloqueio(
            LEITURA_VELHA,
            f"a mensuração foi lida há {int(idade.total_seconds() // 3600)}h, "
            f"além do limite de {int(IDADE_MAXIMA_DA_LEITURA.total_seconds() // 3600)}h. "
            "Uma leitura velha continua sendo uma leitura, e por isso ela não "
            "esconde o que a conta respondeu — mas descreve o passado.",
            fonte=lida.procedencia))

    # ── 7. os fatos da conta ───────────────────────────────────────────────
    #
    # ⚠️ Daqui para baixo a leitura CONCLUIU. O que não se sustentar aqui é
    # `NAO_PRONTA` — provado que não —, e não `INDETERMINADA`.
    #
    # ⚠️ E daqui para baixo NÃO HÁ MAIS SAÍDA ANTECIPADA por bloqueio, exceto
    # quando o bloqueio apaga o próprio universo do que se poderia dizer a
    # seguir (sem ação, sem ação ativa, sem ação primária, sem ação na métrica).
    # A razão é operacional: fechar um bloqueio não abre o portão, e uma lista
    # que para na primeira razão faz o operador consertar uma coisa por vez sem
    # nunca ver o tamanho do caminho. Foi assim que "a ação não carrega valor"
    # ficou invisível atrás de "o sinal não tem data".

    if not lida.acoes:
        bloqueios.append(Bloqueio(
            SEM_ACAO_DE_CONVERSAO,
            "a conta não tem nenhuma ação de conversão. Em lance automático a "
            "campanha otimizaria para nada e gastaria o orçamento inteiro "
            "aprendendo o que ninguém mediu.",
            fonte=lida.procedencia))
        return veredito(NAO_PRONTA)

    # A discordância entre o campo vigente e o depreciado vira ACHADO, sempre —
    # inclusive quando não muda o veredito. Ela é a coisa que ninguém deveria
    # descobrir depois, por telefone, com a campanha no ar.
    for a in lida.acoes:
        if a.deprecado_discorda:
            avisos.append(Bloqueio(
                CAMPO_DEPRECADO_DIVERGENTE,
                f"a ação #{a.id} ({a.nome or 'sem nome'}) tem "
                f"primary_for_goal={a.primaria} e "
                f"include_in_conversions_metric={a.incluida_em_metricas}. O "
                "segundo está DEPRECIADO e não elege a ação sozinho; a "
                "divergência fica registrada porque ela muda o que o painel do "
                "Google mostra ao lado do que este sistema decide.",
                fonte=lida.procedencia))

    ativas = tuple(a for a in lida.acoes if a.ativa)
    if not ativas:
        estados = ", ".join(sorted({a.status or "(sem status)"
                                    for a in lida.acoes}))
        bloqueios.append(Bloqueio(
            ACAO_EM_ESTADO_INVALIDO,
            f"a conta tem {len(lida.acoes)} ação(ões) de conversão e nenhuma "
            f"ENABLED (estados lidos: {estados}). Uma ação que não está ativa "
            "não recebe conversão nenhuma.",
            fonte=lida.procedencia))
        return veredito(NAO_PRONTA)

    # ⚠️ `primaria_efetiva`, e NÃO `bool(primary_for_goal)`. O campo tem
    # presence em v25 e ausente vale `true`; ler com `bool(...)` devolve o
    # veredito invertido justamente na ação que o Google trata como primária.
    primarias = tuple(a for a in ativas if a.primaria_efetiva)
    if not primarias:
        bloqueios.append(Bloqueio(
            ACAO_NAO_PRIMARIA,
            f"nenhuma das {len(ativas)} ações ativas é primária da meta "
            "(primary_for_goal). Uma ação não primária não participa do "
            "objetivo que o lance persegue.",
            fonte=lida.procedencia))
        return veredito(NAO_PRONTA)

    # ⚠️ O CAMPO DEPRECIADO PODE RECUSAR — DESDE QUE DIGA QUE FOI ELE.
    #
    # `include_in_conversions_metric` está depreciado e continua sendo o que
    # tira a ação da métrica `conversions` que o lance otimiza. Uma ação
    # explicitamente FORA dela não alimenta o aprendizado, por mais primária que
    # seja — então a recusa é real. O que muda em relação ao código anterior é
    # que ela deixa de ser anônima: `False` explícito recusa com nome próprio, e
    # `None` (campo não lido) NÃO recusa, porque não lido nunca foi um `False`.
    metrificadas = tuple(a for a in primarias
                         if a.incluida_em_metricas is not False)
    if not metrificadas:
        bloqueios.append(Bloqueio(
            FORA_DA_METRICA_DE_CONVERSOES,
            f"as {len(primarias)} ações primárias estão com "
            "include_in_conversions_metric=false, e uma ação fora dessa métrica "
            "não entra na contagem que o lance otimiza. ⚠️ Este campo está "
            "DEPRECIADO em favor de primary_for_goal — a recusa vem dele, e "
            "está dita em voz alta em vez de aparecer como 'nenhuma ação "
            "válida'.",
            fonte=lida.procedencia))
        return veredito(NAO_PRONTA)
    primarias = metrificadas

    # A meta efetiva já resolvida por quem leu os três recursos que decidem.
    # `None` é ausência da resposta, e ausência aqui não é "não é biddable".
    if lida.meta_biddable is False:
        bloqueios.append(Bloqueio(
            META_NAO_BIDDABLE,
            "nenhuma meta desta campanha é biddable no nível que manda. As "
            "ações existem e não são o que o lance persegue.",
            fonte=lida.procedencia))

    # ── o sinal CHEGA? ─────────────────────────────────────────────────────
    #
    # ⚠️ Três exigências, e nenhuma opcional: contagem lida, contagem positiva e
    # RECÊNCIA. Sem a terceira, uma conversão de 2019 autorizaria Smart Bidding
    # hoje — reproduzido pela revisão de 02/09/2026 do lado do plano.
    elegiveis: Tuple[AcaoLida, ...] = ()
    medidas = tuple(a for a in primarias if a.conversoes_na_janela is not None)
    if not medidas:
        bloqueios.append(Bloqueio(
            SINAL_NAO_COMPROVADO,
            f"das {len(primarias)} ações elegíveis, ninguém mediu o volume. "
            "⚠️ Isto é ausência de medição, e NÃO 'zero conversões': as duas "
            "pedem atos opostos — uma pede uma leitura, a outra pede conserto "
            "da medição.",
            fonte=lida.procedencia))
    else:
        positivas = tuple(a for a in medidas
                          if (a.conversoes_na_janela or 0) > 0)
        if not positivas:
            bloqueios.append(Bloqueio(
                SINAL_NAO_COMPROVADO,
                f"as {len(medidas)} ações elegíveis foram medidas e o volume "
                f"medido é zero em {JANELA_DE_RECENCIA_DIAS} dias. Este é um "
                "fato confirmado, não uma falha de leitura.",
                fonte=lida.procedencia))
        else:
            datadas = tuple(a for a in positivas
                            if a.dias_desde_a_ultima is not None)
            if not datadas:
                bloqueios.append(Bloqueio(
                    SINAL_SEM_DATA,
                    f"as {len(positivas)} ações com conversão não declaram "
                    "QUANDO receberam a última. Sem a data não se sabe se a "
                    "conversão é de ontem ou de sete anos atrás — e é a de "
                    "agora que o lance vai aprender.",
                    fonte=lida.procedencia))
            else:
                recentes = tuple(a for a in datadas
                                 if (a.dias_desde_a_ultima or 0)
                                 <= JANELA_DE_RECENCIA_DIAS)
                if not recentes:
                    bloqueios.append(Bloqueio(
                        SINAL_ANTIGO,
                        "a conversão mais recente das ações elegíveis é mais "
                        f"velha que {JANELA_DE_RECENCIA_DIAS} dias. Uma "
                        "conversão antiga prova que a medição já funcionou, "
                        "não que ela funciona agora.",
                        fonte=lida.procedencia))
                else:
                    elegiveis = recentes

    # ── e só então o VALOR ─────────────────────────────────────────────────
    #
    # ⚠️ Sobre as PRIMÁRIAS, e não sobre as que sobreviveram ao sinal: a
    # pergunta "esta conta tem ação que carrega valor?" é independente de a
    # conta estar recebendo conversão hoje, e responder as duas separadamente é
    # o que faz o operador ver os dois consertos de uma vez.
    if objetivo == OBJETIVO_VALOR:
        com_valor = tuple(a for a in primarias if a.carrega_valor is True)
        indefinidas = tuple(a for a in primarias if a.carrega_valor is None)
        if com_valor:
            elegiveis = tuple(a for a in elegiveis if a.carrega_valor is True)
            if not elegiveis and not bloqueios:
                # ⚠️ VALOR NUMA AÇÃO, SINAL NOUTRA — e a autoridade não tinha
                # estado para isso. `com_valor` é calculado sobre as primárias e
                # o filtro roda sobre as que sobreviveram ao sinal; quando as
                # duas listas são disjuntas, `elegiveis` esvaziava SEM bloqueio e
                # a eleição fazia `sorted(())[0]` — um `IndexError` que escapa do
                # `except PortaoFechado` da rota e vira 500 em vez de 409.
                # Reproduzido pela revisão adversarial de 06/09/2026.
                bloqueios.append(Bloqueio(
                    SEM_VALOR_DECLARADO,
                    f"{estrategia} otimiza pelo VALOR, e nesta conta o valor e o "
                    "sinal estão em ações DIFERENTES: as ações que carregam "
                    "valor não receberam conversão recente, e as que receberam "
                    "não carregam valor. Otimizar valor sobre a segunda é "
                    "otimizar por zero; sobre a primeira, é otimizar sem sinal.",
                    fonte=lida.procedencia))
        elif indefinidas and exige_valor_declarado:
            # Quem chama declarou regra de valor no perfil de mensuração e
            # assume a declaração no lugar da leitura. O aviso registra que a
            # prova veio de DECLARAÇÃO, e não de `value_settings`.
            avisos.append(Bloqueio(
                SEM_VALOR_DECLARADO,
                "nenhuma das ações válidas tem `value_settings` lido; a regra "
                "de valor do perfil de mensuração foi aceita no lugar da "
                "leitura.",
                fonte=lida.procedencia))
        else:
            bloqueios.append(Bloqueio(
                SEM_VALOR_DECLARADO,
                f"{estrategia} otimiza pelo VALOR de cada conversão e nenhuma "
                "das ações válidas tem `value_settings` com valor padrão "
                "positivo ou `always_use_default_value`"
                + (" (o campo não foi lido para nenhuma delas)"
                   if len(indefinidas) == len(primarias) else "") +
                ". Otimizar valor sobre conversões sem valor é otimizar por "
                "zero — use MAXIMIZE_CONVERSIONS ou configure o valor das "
                "ações.",
                fonte=lida.procedencia))
            elegiveis = ()

    if bloqueios:
        # ⚠️ Leitura velha mantém o veredito INDETERMINADA mesmo quando os fatos
        # da conta também bloqueiam: a idade é uma dúvida sobre a LEITURA, e
        # `NAO_PRONTA` afirmaria sobre a CONTA com base num retrato de ontem.
        # Os dois bloqueios viajam juntos; o estado é o mais humilde dos dois.
        velha = any(b.codigo == LEITURA_VELHA for b in bloqueios)
        return veredito(INDETERMINADA if velha else NAO_PRONTA)

    # A eleita: a mais recente entre as que sobraram, com desempate estável pelo
    # id. Empate resolvido por sorteio faria duas provas do mesmo pedido
    # gerarem planos diferentes — e o selo cobre o plano.
    if not elegiveis:
        # ⚠️ REDE DE SEGURANÇA, e ela é fail-CLOSED. Chegar aqui sem candidata e
        # sem bloqueio significa que um ramo novo esvaziou a lista sem dizer por
        # quê — e a resposta honesta para isso é recusar, nunca eleger.
        bloqueios.append(Bloqueio(
            SINAL_NAO_COMPROVADO,
            "nenhuma ação sobreviveu a todas as exigências deste objetivo, e o "
            "motivo não foi registrado por nenhum ramo. Recusa por construção: "
            "não saber qual ação sustentaria o lance nunca autoriza.",
            fonte=lida.procedencia))
        return veredito(NAO_PRONTA)

    eleita = sorted(elegiveis,
                    key=lambda a: (a.dias_desde_a_ultima or 0, a.id))[0]
    return veredito(PRONTA, acao=eleita)


def exigir(
    *,
    customer_id: Any,
    canal: Any,
    estrategia_lance: Any,
    leitura: Optional[Leitura] = None,
    lances_do_canal: Optional[Sequence[str]] = None,
    exige_valor_declarado: bool = False,
    agora: Optional[datetime] = None,
) -> Veredito:
    """`avaliar`, e LEVANTA quando o veredito não autoriza.

    É este o ponto em que Smart Bidding sem prontidão comprovada morre
    localmente — antes do segredo, antes do ledger e antes da rede. Devolve o
    veredito quando pode seguir, para que quem chama registre a prova em vez de
    recalcular.
    """
    v = avaliar(
        customer_id=customer_id, canal=canal,
        estrategia_lance=estrategia_lance, leitura=leitura,
        lances_do_canal=lances_do_canal,
        exige_valor_declarado=exige_valor_declarado, agora=agora)
    if not v.autoriza:
        raise MensuracaoNaoProvada(v)
    return v


# ═══════════════════════════════════════════════════════════════════════════
# OS ADAPTADORES — cada fonte escreve o seu, a decisão continua sendo uma
# ═══════════════════════════════════════════════════════════════════════════


def de_recibo(recibo: Any, *, janela_dias: int = JANELA_DE_RECENCIA_DIAS) -> Leitura:
    """`brief.ReciboDeMensuracao` → `Leitura`.

    ⚠️ Recibo não íntegro NÃO vira leitura vazia. Vira `FALHOU`: um recibo
    montado à mão é uma tentativa de autoatestado, e tratá-lo como "a conta não
    tem ação" o transformaria numa recusa educada em vez de um defeito.

    ⚠️ `primaria` sai como TRI-ESTADO mesmo vindo de um `bool`. O recibo de hoje
    perde a presença do campo em `pmax.ler_mensuracao`
    (`bool(ca.primary_for_goal)`); enquanto essa leitura não preservar o
    tri-estado, `True` continua sendo `True` e `False` chega aqui como `False`
    — e é por isso que `_LEITURA_COLAPSOU_PRESENCA` viaja como aviso na
    procedência, para o achado não sumir.
    """
    if recibo is None:
        return leitura_ausente()
    if not bool(getattr(recibo, "integro", False)):
        return Leitura(
            estado=FALHOU,
            causa=("o recibo de mensuração não foi emitido por uma leitura "
                   "desta execução: a impressão não confere. Ninguém se "
                   "autoatesta."),
            procedencia=str(getattr(recibo, "coletor", "") or ""),
            lido_em=str(getattr(recibo, "lido_em", "") or ""))

    acoes = []
    for a in tuple(getattr(recibo, "acoes", ()) or ()):
        acoes.append(AcaoLida(
            id=str(getattr(a, "resource_name", "") or "").rsplit("/", 1)[-1],
            nome=str(getattr(a, "nome", "") or ""),
            categoria=str(getattr(a, "categoria", "") or ""),
            tipo=str(getattr(a, "tipo", "") or ""),
            status=str(getattr(a, "status", "") or ""),
            primaria=getattr(a, "primaria_para_meta", None),
            incluida_em_metricas=getattr(a, "inclui_em_conversoes", None),
            carrega_valor=getattr(a, "carrega_valor", None),
            conversoes_na_janela=getattr(a, "conversoes_ultimos_30d", None),
            # ⚠️ O recibo não traz a data da última conversão. `None` é
            # honesto: ele produz `SINAL_ANTIGO` com a frase "não declara
            # QUANDO", que é exatamente o estado da leitura de hoje.
            dias_desde_a_ultima=getattr(a, "dias_desde_a_ultima", None),
        ))
    return Leitura(
        estado=(COM_DADOS if acoes else VAZIO_CONFIRMADO),
        acoes=tuple(acoes),
        procedencia=str(getattr(recibo, "coletor", "") or ""),
        lido_em=str(getattr(recibo, "lido_em", "") or ""),
        meta_biddable=None,
    )


def de_plano(plano: Any, *, lido_em: str = "") -> Leitura:
    """`app.trafego.plano_mensuracao.PlanoDeMensuracao` → `Leitura`.

    Tipado como `Any` de propósito: este módulo não importa o backend, e o
    adaptador só usa atributos. A direção da dependência continua sendo
    `backend → volc_ads`, sempre.

    ⚠️ O plano já resolveu a meta efetiva com os três recursos que decidem, e é
    ele quem sabe se ela é biddable. Recalcular aqui criaria a segunda verdade
    que este módulo existe para eliminar — por isso `meta_biddable` é
    transportado, não deduzido.

    ⚠️ `lido_em` vem de FORA, e tem de vir: `PlanoDeMensuracao` não carrega o
    instante da própria leitura — ele carrega a data da última CONVERSÃO, que é
    outro fato e envelhece por outro motivo. Quem leu sabe quando leu
    (`/subir` já marca `lido_em_do_plano = _agora_iso()` antes das cinco
    consultas), e passar isso é declarar a procedência temporal em vez de
    inventá-la a partir de um campo vizinho.
    """
    if plano is None:
        return leitura_ausente()

    estado_bruto = str(getattr(plano, "acoes_estado", "") or NAO_COLETADO)
    # O vocabulário do plano tem dois estados a mais (`inelegivel`,
    # `nao_suportado`) que aqui não concluem nem falham: eles dizem que a
    # pergunta não cabia. Tratá-los como `VAZIO_CONFIRMADO` afirmaria ausência
    # sobre uma pergunta que ninguém fez.
    mapa = {
        "com_dados": COM_DADOS,
        "vazio_confirmado": VAZIO_CONFIRMADO,
        "parcial": PARCIAL,
        "falhou": FALHOU,
        "nao_coletado": NAO_COLETADO,
    }
    estado = mapa.get(estado_bruto, NAO_COLETADO)

    frescor = getattr(plano, "frescor", None)
    dias = getattr(frescor, "dias_desde_a_ultima", None)
    contagem = getattr(frescor, "conversoes_na_janela", None)
    acao_do_frescor = str(getattr(frescor, "conversion_action_id", "") or "")

    meta = getattr(plano, "meta_efetiva", None)
    biddable = getattr(meta, "metas_biddable", None)
    meta_biddable = None if biddable is None else bool(biddable)

    acoes = []
    for a in tuple(getattr(plano, "acoes", ()) or ()):
        identidade = str(getattr(a, "id", "") or "")
        # ⚠️ O frescor tem SUJEITO: ele se refere a UMA ação. Espalhá-lo por
        # todas faria uma conta com uma ação viva e nove mortas parecer uma
        # conta com dez ações vivas.
        do_frescor = bool(acao_do_frescor) and identidade == acao_do_frescor
        acoes.append(AcaoLida(
            id=identidade,
            nome=str(getattr(a, "nome", "") or ""),
            categoria=str(getattr(a, "categoria", "") or ""),
            tipo=str(getattr(a, "tipo", "") or ""),
            status=str(getattr(a, "status", "") or ""),
            primaria=getattr(a, "primaria", None),
            incluida_em_metricas=getattr(a, "incluida_em_metricas", None),
            # O plano não lê `value_settings` (dito em voz alta na docstring de
            # `prontidao.exigir_para_criacao`). `None` = não lido, e é quem
            # chama que declara a regra de valor do perfil.
            carrega_valor=None,
            conversoes_na_janela=(contagem if do_frescor else None),
            dias_desde_a_ultima=(dias if do_frescor else None),
        ))

    causa = ""
    if estado in ESTADOS_SEM_CONCLUSAO:
        causa = (str(getattr(frescor, "causa", "") or "")
                 or f"a leitura das ações de conversão está {estado_bruto}")
    return Leitura(
        estado=estado, acoes=tuple(acoes),
        procedencia=("app.trafego.plano_mensuracao.PlanoDeMensuracao "
                     f"v{getattr(plano, 'versao', '?')}"),
        lido_em=str(lido_em or ""),
        meta_biddable=meta_biddable, causa=causa)
