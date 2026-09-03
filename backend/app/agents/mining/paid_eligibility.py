"""Elegibilidade paga — a decisão que a mineração NÃO tem o direito de tomar.

## As duas decisões, e por que precisavam ser separadas

    "Vale criar conteúdo sobre este tema?"      → `app.validacao` (o Validador)
    "Quais termos podem entrar num leilão?"     → este módulo

Elas vazavam uma para a outra. `funnel_factory` escolhia de 3 a 10 termos por
sub-intenção em `selected` e exportava `final_campaign`, construída a partir de
`deduped` — a tela mostrava a escolha e a campanha recebia a mineração inteira.
Medido em 2026-09-03 contra `origin/volc-os-v2@34dc7b4`, no funil BPC/LOAS:

    selecionadas : 5      exportadas : 8

E os dois termos que a seleção colocava em primeiro lugar eram
`meu inss login` (480.000) e `inss telefone 135` (300.000): navegacional e
suporte entrando por volume, empurrando a intenção de elegibilidade para fora.
É o mesmo defeito que o Validador já documenta do lado editorial — "73% do eixo
`volume` era gente procurando o telefone do Banco Pan" — aparecendo do lado
pago, onde ninguém tinha olhado.

## Ausência não é zero, e medir não pode custar caro

O caminho antigo lia `kw.get("cpc") or 0`. A consequência, medida:

    'ipva tabela fipe' sem CPC   → APROVADA  "Good Volume + Affordable CPC"
    'ipva tabela fipe' CPC 4,20  → DESCARTADA

Não medir saía mais barato que medir. `Sinal` existe para fechar isso: um
número só entra numa decisão acompanhado do estado que diz de onde ele veio, e
`absent` nunca aceita valor numérico.

O vocabulário de estado não é invenção deste módulo. `app.validacao` já grava
`proveniencia: medido | julgado | ausente` por eixo, com `motivo_ausencia`
junto. Aqui ele é estendido para o que um sinal de leilão precisa distinguir —
notadamente `confirmed_zero`, que o motor antigo não conseguia expressar:
`data_reliability` é lido em `classifier.py` e nunca foi escrito por nenhum
produtor do repositório, então "volume zero confirmado" e "volume ausente"
caíam no mesmo descarte.

## O que este módulo NÃO decide

`ready_for_campaign_plan` diz que o CONJUNTO pode ser preparado com governança.
Não diz que a conta está apta, que o destino pago passou, que a mensuração está
pronta, nem que alguém autorizou gasto. Esses portões são de outras lanes e
continuam independentes — `PORTOES_EXTERNOS` os nomeia justamente para que
nenhum leitor confunda os dois níveis.

E nada aqui cria negativa. Negativa sem search-term evidence e sem revisão de
overblocking é o espelho do defeito, não a correção.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ── estados do dado ─────────────────────────────────────────────────────────
#
# Sete estados, porque seis colapsariam dois casos que decidem diferente.
# `absent` (a chave não veio) e `unknown` (veio um número que não se sabe
# interpretar) levam a caminhos distintos: o primeiro pede medição, o segundo
# pede confirmação. E `confirmed_zero` é o único zero que pode ser lido como
# demanda zero — todo outro zero é ruído com cara de fato.

MEDIDO = "measured"
ZERO_CONFIRMADO = "confirmed_zero"
AUSENTE = "absent"
DESCONHECIDO = "unknown"
NAO_APLICAVEL = "not_applicable"
FALHOU = "failed"
INFERIDO = "inferred"

ESTADOS: Tuple[str, ...] = (
    MEDIDO, ZERO_CONFIRMADO, AUSENTE, DESCONHECIDO, NAO_APLICAVEL, FALHOU, INFERIDO,
)

# Estados em que NÃO existe número. Guardar um valor aqui é o bug que este
# módulo foi escrito para impedir, então o construtor recusa.
ESTADOS_SEM_NUMERO: Tuple[str, ...] = (AUSENTE, DESCONHECIDO, NAO_APLICAVEL, FALHOU)

# A tradução para o vocabulário que `app.validacao` já grava por eixo. Existe
# para que as duas metades do Pautador continuem falando a mesma língua sem que
# nenhuma das duas precise reescrever a outra.
PROVENIENCIA_EQUIVALENTE: Dict[str, str] = {
    MEDIDO: "medido",
    ZERO_CONFIRMADO: "medido",
    INFERIDO: "julgado",
    AUSENTE: "ausente",
    DESCONHECIDO: "ausente",
    NAO_APLICAVEL: "ausente",
    FALHOU: "ausente",
}


class EstadoInvalido(ValueError):
    """Um `Sinal` foi montado com estado e valor que se contradizem."""


@dataclass(frozen=True)
class Sinal:
    """Um número de leilão com o estado que o autoriza a ser lido.

    `valor` só existe quando o estado permite. Não há caminho para "0 porque
    não veio": tentar construir `Sinal(0.0, AUSENTE)` levanta.
    """

    valor: Optional[float]
    estado: str
    fonte: str = "desconhecida"
    frescor: Optional[str] = None
    motivo: Optional[str] = None

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS:
            raise EstadoInvalido(f"estado fora do vocabulário: {self.estado!r}")
        if self.estado in ESTADOS_SEM_NUMERO and self.valor is not None:
            raise EstadoInvalido(f"{self.estado!r} não pode carregar valor ({self.valor!r})")
        if self.estado == ZERO_CONFIRMADO and self.valor != 0:
            raise EstadoInvalido("confirmed_zero exige valor 0")
        if self.estado in (MEDIDO, INFERIDO) and self.valor is None:
            raise EstadoInvalido(f"{self.estado!r} exige valor")
        # Volume, CPC, competição e faixa de lance são grandezas não negativas.
        # Um -100 chegando como `measured` não é uma medição pequena: é um
        # dado corrompido, e aceitá-lo autorizava INCLUDE com
        # `viabilidade="cabe_no_teto"` — o CPC negativo cabe em qualquer teto.
        if self.valor is not None and self.valor < 0:
            raise EstadoInvalido(
                f"valor negativo ({self.valor}) não é medição válida de sinal de leilão"
            )

    @property
    def tem_numero(self) -> bool:
        return self.valor is not None

    @property
    def proveniencia(self) -> str:
        return PROVENIENCIA_EQUIVALENTE[self.estado]

    def como_dicionario(self) -> Dict[str, Any]:
        return {
            "valor": self.valor,
            "estado": self.estado,
            "fonte": self.fonte,
            "frescor": self.frescor,
            "motivo": self.motivo,
            "proveniencia": self.proveniencia,
        }

    @classmethod
    def ausente(cls, motivo: str, *, fonte: str = "desconhecida") -> "Sinal":
        return cls(None, AUSENTE, fonte=fonte, motivo=motivo)

    @classmethod
    def de_bruto(
        cls,
        mapa: Any,
        chave: str,
        *,
        fonte: str,
        medicao_confirmada: bool = False,
        frescor: Optional[str] = None,
    ) -> "Sinal":
        """Lê um campo cru SEM inventar zero.

        A chave que não veio é `absent`. O `0` cru é `unknown` até que alguém
        prove que o termo foi de fato medido — `medicao_confirmada=True` é essa
        prova, e é justamente o que `data_reliability` prometia e nunca
        entregou, porque nenhum produtor do repositório o escrevia.
        """
        if not isinstance(mapa, dict) or chave not in mapa:
            return cls(None, AUSENTE, fonte=fonte, motivo="chave_ausente")
        bruto = mapa.get(chave)
        if bruto is None:
            return cls(None, AUSENTE, fonte=fonte, motivo="valor_nulo")
        try:
            valor = float(bruto)
        except (TypeError, ValueError):
            return cls(None, FALHOU, fonte=fonte, motivo=f"valor_ilegivel:{bruto!r}"[:80])
        if valor < 0:
            return cls(None, FALHOU, fonte=fonte, motivo=f"valor_negativo:{valor}")

        # O ESTADO DECLARADO PELA ORIGEM VENCE O PALPITE DESTA CAMADA.
        #
        # `gold_extractor` grava `<campo>_estado` a partir da PRESENÇA da chave
        # na resposta do Keyword Planner, e `merger` propaga. Quando esse campo
        # chega, ele é a única testemunha que esteve na fonte — aqui já não dá
        # para distinguir um `0` que a API respondeu de um `0` que uma camada
        # intermediária inventou.
        declarado = mapa.get(f"{chave}_estado")
        if declarado in ESTADOS:
            # ⚠️ TODO estado declarado é honrado, não só os que dão certo.
            #
            # A primeira versão desta guarda tratava `absent`, `measured` e
            # `unknown`+0 — e deixava `failed`, `not_applicable` e um `unknown`
            # com valor não-zero CAÍREM no ramo final, que os promovia a
            # `measured`. Uma revisão adversarial reproduziu:
            #
            #     {"volume": 1000, "volume_estado": "failed"}
            #        -> Sinal(1000.0, "measured")  -> decisão INCLUDE
            #
            # Ou seja: declarar que a leitura FALHOU deixava o número entrar
            # como se tivesse sido medido. Honrar só os estados convenientes é
            # não honrar estado nenhum.
            if declarado in ESTADOS_SEM_NUMERO:
                return cls(None, declarado, fonte=fonte,
                           motivo=f"origem_declarou_{declarado}")
            if declarado == ZERO_CONFIRMADO:
                return cls(0.0, ZERO_CONFIRMADO, fonte=fonte, frescor=frescor)
            if valor == 0:
                return cls(0.0, ZERO_CONFIRMADO, fonte=fonte, frescor=frescor)
            return cls(valor, declarado, fonte=fonte, frescor=frescor)

        if valor == 0:
            if medicao_confirmada:
                return cls(0.0, ZERO_CONFIRMADO, fonte=fonte, frescor=frescor)
            # ⚠️ ASSIMETRIA DE CUSTO, DECLARADA.
            #
            # Uma revisão externa apontou, com razão, que `avg_monthly_searches
            # = 0` na resposta do Keyword Planner é RESPOSTA — volume estimado
            # nulo ou insignificante —, e que ler isso como `unknown` perde
            # informação real.
            #
            # O default continua conservador porque os dois erros não custam o
            # mesmo: ler um zero-por-omissão como demanda zero REJEITA um termo
            # que talvez tenha demanda; ler um zero-medido como desconhecido
            # apenas o SEGURA para medição. Segurar é reversível, rejeitar é o
            # que some da tela.
            #
            # E o caminho certo não é adivinhar aqui: é a origem declarar. Com
            # `<campo>_estado` presente, o ramo acima já resolve — este ramo só
            # existe para quem ainda não declara.
            return cls(None, DESCONHECIDO, fonte=fonte, motivo="zero_sem_confirmacao")
        return cls(valor, MEDIDO, fonte=fonte, frescor=frescor)


# ── arquétipos de intenção ──────────────────────────────────────────────────
#
# Léxico determinístico, multi-rótulo, em cima do vocabulário que o motor JÁ
# tem: as QUESTION_WORDS do Gold Miner continuam sendo a fonte do rótulo
# informacional, para não abrir um segundo motor semântico concorrente.
#
# Os treze arquétipos não vieram de um quadro teórico: são os que o par de
# nichos de prova (BPC/LOAS e IPVA) exige para não colapsar, mais os que o
# defeito medido obrigou a nomear — `navegacional` e `suporte_acesso`, os dois
# que entravam por volume.

ARQ_INFORMACIONAL = "informacional"
ARQ_ELEGIBILIDADE = "elegibilidade"
ARQ_PROCEDURAL = "procedural"
ARQ_COMPARACAO = "comparacao"
ARQ_TRANSACIONAL = "transacional"
ARQ_URGENCIA = "urgencia"
ARQ_VALOR_PRECO = "valor_preco"
ARQ_NAVEGACIONAL = "navegacional"
ARQ_SUPORTE_ACESSO = "suporte_acesso"
ARQ_MARCA_ENTIDADE = "marca_entidade"
ARQ_GOVERNO = "governo_institucional"
ARQ_RECORRENCIA = "recorrencia_calendario"
ARQ_DECISAO_OBJECAO = "decisao_objecao"

ARQUETIPOS: Tuple[str, ...] = (
    ARQ_INFORMACIONAL, ARQ_ELEGIBILIDADE, ARQ_PROCEDURAL, ARQ_COMPARACAO,
    ARQ_TRANSACIONAL, ARQ_URGENCIA, ARQ_VALOR_PRECO, ARQ_NAVEGACIONAL,
    ARQ_SUPORTE_ACESSO, ARQ_MARCA_ENTIDADE, ARQ_GOVERNO, ARQ_RECORRENCIA,
    ARQ_DECISAO_OBJECAO,
)

# Arquétipos que NÃO podem ser elegíveis só por volume. Não são proibidos:
# são retidos até que alguém diga, explicitamente, que aquele termo pertence à
# própria marca do anunciante ou tem contexto que o justifique.
ARQUETIPOS_RETIDOS: Tuple[str, ...] = (ARQ_NAVEGACIONAL, ARQ_SUPORTE_ACESSO)

_LEXICO: Dict[str, Tuple[str, ...]] = {
    ARQ_ELEGIBILIDADE: (
        "quem tem direito", "tem direito", "direito a", "quem pode", "posso",
        "requisitos", "criterios", "criterio", "elegivel", "elegibilidade",
        "se enquadra", "condicoes para", "regras para",
    ),
    ARQ_PROCEDURAL: (
        "como ", "passo a passo", "dar entrada", "solicitar", "requerer",
        "fazer o", "tutorial", "onde fazer", "como pedir", "inscricao",
        "cadastrar", "cadastro", "agendar", "agendamento",
    ),
    ARQ_COMPARACAO: (
        " vs ", " x ", "melhor que", "diferenca entre", "comparativo",
        "compara", "ou ", "qual melhor", "vale mais a pena",
    ),
    ARQ_TRANSACIONAL: (
        "contratar", "comprar", "assinar", "cotacao", "orcamento",
        "simular", "simulacao", "solicitar online", "contrate",
    ),
    ARQ_URGENCIA: (
        "urgente", "hoje", "agora", "ultimo dia", "prazo final",
        "vence hoje", "de imediato", "rapido",
    ),
    ARQ_VALOR_PRECO: (
        "valor", "valores", "preco", "precos", "quanto custa", "quanto e",
        "tabela", "custo", "taxa", "aliquota", "desconto", "parcelamento",
        "parcelar", "quanto vou receber",
    ),
    # ⚠️ MARCADORES FRACOS FORAM REMOVIDOS DEPOIS DE MEDIR O ESTRAGO.
    #
    # `"meu "` e `" app"` sozinhos retinham termo comercial legítimo. Medido:
    #
    #     vender meu precatorio       -> HOLD  (navegacional)
    #     simular meu financiamento   -> HOLD  (navegacional, apesar de
    #                                           também ser transacional)
    #     seguro auto app             -> HOLD  (navegacional)
    #
    # Reter demais não é o lado seguro: é o mesmo defeito do outro lado da
    # balança — um motor que segura tudo não separa nada. Ficaram os
    # marcadores que nomeiam um ARTEFATO DE ACESSO, e as formas compostas de
    # portal ("meu inss", "meu gov") que são a convenção brasileira de nome.
    ARQ_NAVEGACIONAL: (
        "login", "acessar", "portal", "site oficial", "aplicativo",
        "baixar app", "app oficial", "area do", "area logada",
        "minha conta", "meu cadastro", "meu inss", "meu gov", "meu beneficio",
        "www", ".gov", ".com", "entrar no", "entrar na",
    ),
    ARQ_SUPORTE_ACESSO: (
        "telefone", "0800", "fone", "contato", "atendimento", "sac",
        "central de", "reclamacao", "ouvidoria", "falar com", "chat",
        # Reproduzido numa revisão adversarial: `ligar para o inss no 135`
        # saía INCLUDE porque nenhum marcador de suporte casava a frase.
        "ligar para", "ligar no", "numero do", "numero de contato", "whatsapp",
        "segunda via de senha", "recuperar senha", "esqueci a senha",
    ),
    ARQ_GOVERNO: (
        "inss", "gov.br", "govbr", "detran", "receita federal", "caixa",
        "ministerio", "prefeitura", "secretaria", "sefaz", "bpc", "loas",
        "ipva", "irpf", "fgts", "pis", "bolsa familia", "cadunico",
    ),
    ARQ_RECORRENCIA: (
        "calendario", "cronograma", "datas", "quando sai", "quando cai",
        "todo ano", "anual", "mensal", "vencimento",
    ),
    ARQ_DECISAO_OBJECAO: (
        "negado", "indeferido", "recusado", "bloqueado", "cancelado",
        "o que fazer", "recorrer", "recurso", "reclamar", "deu errado",
        "nao recebi", "problema com",
    ),
}

# Marcas de terceiro / concorrência. Não é lista de empresas — é a marca
# LINGUÍSTICA de que o termo aponta para outra entidade. Uma lista de nomes
# envelheceria e daria falsa cobertura.
# ⚠️ `" x "` E `" vs "` SAÍRAM DAQUI, E CONTINUAM EM `ARQ_COMPARACAO`.
#
# Comparação não é marca de terceiro. Medido, com os dois marcadores aqui:
#
#     advogado presencial x online  -> HUMAN_REVIEW (marca_terceiro)
#     clt x pj                      -> HUMAN_REVIEW (marca_terceiro)
#
# Nenhum dos dois cita marca de ninguém. Ficaram os marcadores que de fato
# apontam para OUTRA ENTIDADE.
#
# ⚠️ E o léxico NÃO detecta marca que ele não conhece: `jusbrasil consulta`
# passa como INCLUDE. Isso não tem conserto por vocabulário — por isso
# `decidir_keyword` aceita `marcas_de_terceiro`, uma lista que o operador
# declara. Sem ela, a cobertura de marca é declaradamente parcial.
_MARCA_TERCEIRO = (
    "concorrente", "concorrentes", "alternativa a", "alternativas a",
    "parecido com", "similar a", "igual ao", "substituto de", "melhor que ",
)


def _sem_acento(texto: str) -> str:
    norm = unicodedata.normalize("NFD", texto)
    return "".join(c for c in norm if unicodedata.category(c) != "Mn")


def normalizar_termo(termo: Any) -> str:
    """A forma sob a qual dois termos são o MESMO termo POSITIVO.

    Minúscula, espaço colapsado e ACENTO DOBRADO. NÃO ordena palavras:
    `merger._strong_normalize` ordena e é correto para consolidar banco, mas
    aqui fundiria `ipva de sp` com `sp de ipva` — a mesma frase para um banco,
    frases diferentes para um leilão.

    ⚠️ O acento dobra aqui e NÃO dobra em `volc_ads.campanha.criterio.chave`,
    e a assimetria é a regra da casa, não um descuido. Lá o objeto é a
    NEGATIVA, que não expande para variantes próximas: deduplicar `grátis` com
    `gratis` APAGARIA um bloqueio declarado. Aqui o objeto é a keyword
    POSITIVA, onde o Google casa variantes próximas e as duas grafias
    competiriam entre si pelo mesmo leilão.

    Sem isso, `declaração ipva 2026` e `declaracao ipva 2026` — as duas
    grafias que a mineração rotineiramente traz — sobreviviam como keywords
    separadas e somavam volume duas vezes.
    """
    return " ".join(_sem_acento(str(termo or "")).lower().strip().split())


# Importado do motor existente — o rótulo informacional continua saindo da
# mesma lista que o Gold Miner usa, e não de uma segunda cópia divergente.
def _palavras_de_pergunta() -> Tuple[str, ...]:
    from app.agents.mining.classifier import QUESTION_WORDS

    return tuple(QUESTION_WORDS)


def arquetipos(termo: Any) -> Tuple[str, ...]:
    """Os arquétipos de intenção do termo, em ordem canônica e sem repetição.

    Multi-rótulo de propósito: `bpc loas valor 2026` é ao mesmo tempo
    `valor_preco`, `governo_institucional` e `recorrencia_calendario`, e
    reduzir isso a um rótulo só é como o motor antigo perdia a intenção.
    """
    texto = _sem_acento(normalizar_termo(termo))
    if not texto:
        return ()
    acolchoado = f" {texto} "
    achados = set()
    for arq, marcas in _LEXICO.items():
        for marca in marcas:
            if _sem_acento(marca) in acolchoado:
                achados.add(arq)
                break
    for palavra in _palavras_de_pergunta():
        p = _sem_acento(palavra)
        if p and (acolchoado.startswith(f" {p}") or f" {p} " in acolchoado):
            achados.add(ARQ_INFORMACIONAL)
            break
    return tuple(a for a in ARQUETIPOS if a in achados)


def _casa_frase(texto_acolchoado: str, frase: str) -> bool:
    """A frase aparece como sequência de PALAVRAS INTEIRAS no texto."""
    return f" {frase} " in texto_acolchoado


def riscos(
    termo: Any,
    *,
    marcas_proprias: Sequence[str] = (),
    marcas_de_terceiro: Sequence[str] = (),
) -> Dict[str, bool]:
    """Riscos que TIRAM o termo do caminho automático — para os dois lados.

    Nem inclusão automática, nem negativa automática. Um termo de marca ou de
    entidade pública vai para revisão humana com o motivo escrito; a decisão de
    leiloar em cima de uma marca de terceiro é jurídica e comercial, e o motor
    não tem contexto para tomá-la.
    """
    texto = _sem_acento(normalizar_termo(termo))
    acolchoado = f" {texto} "
    # ⚠️ MARCA CASA POR TOKEN, NÃO POR SUBSTRING.
    #
    # `m in texto` fazia `"pan"` casar dentro de `"panasonic"`. Reproduzido:
    # `telefone panasonic assistencia` com `marcas_proprias=["pan"]` virava
    # marca própria, o que DESLIGA o bloqueio de navegacional/suporte — um
    # termo de suporte de terceiro entrava como INCLUDE por coincidência de
    # três letras.
    proprias = {normalizar_termo(m) for m in marcas_proprias if m}
    e_propria = any(m and _casa_frase(acolchoado, m) for m in proprias)
    terceiras = {normalizar_termo(m) for m in marcas_de_terceiro if m}
    arqs = arquetipos(termo)
    return {
        "marca_propria": e_propria,
        "marca_terceiro": (not e_propria) and (
            any(_sem_acento(m) in acolchoado for m in _MARCA_TERCEIRO)
            or any(m and _casa_frase(acolchoado, m) for m in terceiras)
        ),
        "institucional_governo": ARQ_GOVERNO in arqs,
        "navegacional_ou_suporte": bool(set(arqs) & set(ARQUETIPOS_RETIDOS)) and not e_propria,
    }


# ── match type ──────────────────────────────────────────────────────────────
#
# Nenhum match type é universal, e BROAD nunca é proposto automaticamente:
# ampla é exatamente o caminho pelo qual um termo de marca de terceiro entra
# num conjunto que ninguém aprovou.
#
# ⚠️ E NENHUM MATCH TYPE ISOLA. Variantes próximas se aplicam a EXACT E a
# PHRASE — sinônimos, erros de grafia e buscas de mesma intenção —, então
# propor EXACT para um termo curto NÃO impede que ele seja acionado por uma
# busca de suporte ou navegacional. A proposta aqui é de CONTENÇÃO RELATIVA,
# não de estanqueidade, e o alerta correspondente viaja na decisão.
#
# Consequência que fica escrita porque não é fechada aqui: enquanto não
# existir negativa com search-term evidence, os termos que este motor RETÉM
# continuam alcançáveis por variante próxima dos termos que ele INCLUI. Isso
# é bloqueador de lançamento, não de preparação — e está no handoff.

EXACT, PHRASE, BROAD = "EXACT", "PHRASE", "BROAD"


def propor_match_type(termo: Any, arqs: Sequence[str]) -> str:
    palavras = normalizar_termo(termo).split()
    curto_e_decidido = len(palavras) <= 3 and bool(
        {ARQ_TRANSACIONAL, ARQ_ELEGIBILIDADE, ARQ_VALOR_PRECO} & set(arqs)
    )
    return EXACT if curto_e_decidido else PHRASE


#: O alerta que acompanha TODA proposta de match type. Existe para que a tela
#: não leia "EXACT" como "só casa isto".
ALERTA_VARIANTES_PROXIMAS = "match_type_nao_isola_variantes_proximas"


# ── evidência e vazamento de desfecho ───────────────────────────────────────

PRE_LANCAMENTO = "pre_lancamento"
POS_LANCAMENTO = "pos_lancamento"


class VazamentoDeDesfecho(RuntimeError):
    """Evidência posterior ao lançamento foi oferecida como insumo anterior a ele."""


@dataclass(frozen=True)
class Evidencia:
    """Uma prova, com o MOMENTO em que ela passou a existir.

    Search terms e conversões de uma campanha podem ensinar a PRÓXIMA campanha.
    Não podem justificar, retroativamente, a seleção inicial da mesma campanha
    — é a definição de ler o desfecho de volta na entrada.
    """

    fonte: str
    momento: str = PRE_LANCAMENTO
    campanha_ref: Optional[str] = None
    detalhe: str = ""
    frescor: Optional[str] = None

    def como_dicionario(self) -> Dict[str, Any]:
        return {
            "fonte": self.fonte, "momento": self.momento,
            "campanha_ref": self.campanha_ref, "detalhe": self.detalhe,
            "frescor": self.frescor,
        }


def _guardar_vazamento(
    evidencias: Sequence[Evidencia], momento_da_decisao: str, campanha_ref: Optional[str]
) -> None:
    if momento_da_decisao != PRE_LANCAMENTO:
        return
    for ev in evidencias:
        if ev.momento != POS_LANCAMENTO:
            continue
        # ⚠️ FALHA FECHADO. A primeira versão só levantava quando as duas
        # `campanha_ref` batiam — então uma evidência pós-lançamento SEM
        # campanha declarada passava direto para uma decisão pré-lançamento.
        # Reproduzido numa revisão adversarial. Numa guarda contra vazamento,
        # "não sei de qual campanha isto veio" é exatamente o caso que precisa
        # ser barrado: só a menção EXPLÍCITA de outra campanha a libera.
        if ev.campanha_ref is None or ev.campanha_ref == campanha_ref:
            raise VazamentoDeDesfecho(
                f"evidência {ev.fonte!r} é pós-lançamento "
                + (f"da campanha {campanha_ref!r}" if ev.campanha_ref else "sem campanha declarada")
                + " e não pode sustentar uma seleção pré-lançamento. Para usá-la como "
                "prior de OUTRA campanha, declare `campanha_ref` dela."
            )


# ── priors de benchmark: anotam, não decidem ────────────────────────────────


@dataclass(frozen=True)
class PriorDeBenchmark:
    nome: str
    afirmacao: str
    confianca: str          # alta | media | baixa | nenhuma
    bloqueia: bool
    autoriza: bool
    origem: str
    limitacao: str


# O benchmark Webgo (run 20260903T010510Z) é gerador de hipóteses. Os números
# abaixo saíram da errata v2 dele, que corrige a leitura v1 — e a correção é
# justamente a razão pela qual nada aqui bloqueia ou autoriza:
#
#   · "122 episódios sobreviveram aos controles" é declarado FACTUALMENTE
#     ERRADO pela própria errata: 0 dos 122 têm controle pareado utilizável, e
#     o bloqueador registrado nos 122 é literalmente "sem controle pareado
#     utilizavel". Eles passaram critérios internos mínimos, não controles.
#   · O degrau superior de evidência (`razoavel`) NUNCA foi alcançado:
#     fraca 2.347 / nenhuma 1.081 / moderada 122 / razoavel 0.
#   · 35 de 35 playbooks saíram com confiança `baixa`, por critério que o
#     próprio benchmark rotula "ARBITRADA, nao estatistica".
#   · `EXCELLENT` foi rebaixado a NOT_IDENTIFIABLE (contagem inflada 2,00x por
#     partição duplicada; direção inverte contra os controles fortes).
#   · SEARCH e MAXIMIZE_CONVERSIONS não são dois sinais: são a mesma fatia, e
#     SEARCH sobrou como `external_prior`, não como sinal identificado.
#   · E o que mais importa aqui: NÃO EXISTE teste de desfecho no nível de
#     keyword em lugar nenhum daquele pacote. `KEYWORD_OR_MATCH_CHANGE` tem
#     exatamente UM episódio legível. Usar aquilo para validar elegibilidade de
#     keyword seria um erro de categoria que o próprio benchmark recusa.
PRIORS_DE_BENCHMARK: Tuple[PriorDeBenchmark, ...] = (
    PriorDeBenchmark(
        nome="search_como_prior_externo",
        afirmacao="campanhas SEARCH aparecem mais entre as vencedoras do portfólio observado",
        confianca="baixa",
        bloqueia=False,
        autoriza=False,
        origem="webgo/20260903T010510Z refinement-v2 (classificado external_prior)",
        limitacao=(
            "inseparável da estratégia de lance; inverte contra os 3 controles fortes; "
            "seleção não é aleatória — quem escolhe Search escolhe tema, site e operador junto"
        ),
    ),
    PriorDeBenchmark(
        nome="forca_de_anuncio_excellent",
        afirmacao="anúncios EXCELLENT apareceriam mais entre vencedoras",
        confianca="nenhuma",
        bloqueia=False,
        autoriza=False,
        origem="webgo/20260903T010510Z refinement-v2 (rebaixado a not_identifiable)",
        limitacao=(
            "contagem inflada 2,00x por partição duplicada; direção inverte contra controles; "
            "e é score pós-desfecho recomputado pelo Google — usá-lo antes do lançamento "
            "importa o resultado para dentro da entrada"
        ),
    ),
    PriorDeBenchmark(
        nome="match_type_nao_discrimina",
        afirmacao="BROAD/PHRASE/EXACT não separam campanha vencedora de controle",
        confianca="baixa",
        bloqueia=False,
        autoriza=False,
        origem="webgo/20260903T010510Z data/curated/pattern_shares.csv (dimensão tipo_de_correspondencia)",
        limitacao=(
            "resultado NEGATIVO explícito — BROAD sai 'igual ao controle: e o padrao da "
            "operacao, nao sinal' e EXACT 'nao e mais frequente nas vencedoras'. "
            "`propor_match_type` deste módulo é, portanto, POLÍTICA declarada e não "
            "achado importado: nenhum match type aqui cita aquele pacote como prova"
        ),
    ),
    PriorDeBenchmark(
        nome="vazio_de_search_term_nao_e_ausencia_de_demanda",
        afirmacao="resultado vazio de search term nunca se lê como 'sem demanda de busca'",
        confianca="alta",
        bloqueia=False,
        autoriza=False,
        origem="webgo/20260903T010510Z HANDOFF.md (armadilha 4: search_term_view em PMax é GAQL válida com 0 linhas)",
        limitacao=(
            "prior METODOLÓGICO, não de conteúdo: diz como LER um vazio, não o que "
            "incluir. É o mesmo princípio que `Sinal` codifica em `absent` vs "
            "`confirmed_zero`, e a única coisa deste benchmark que o motor de fato aplica"
        ),
    ),
    PriorDeBenchmark(
        nome="padrao_presente_tambem_no_controle_nao_e_sinal",
        afirmacao="um padrão presente nas vencedoras E nos controles é o default da operação",
        confianca="alta",
        bloqueia=False,
        autoriza=False,
        origem="webgo/20260903T010510Z refinement-v2 (filtro de sinal declarado)",
        limitacao=(
            "prior METODOLÓGICO. Só a diferença ENTRE grupos informa, e mesmo ela é "
            "associação: os grupos não foram sorteados"
        ),
    ),
    PriorDeBenchmark(
        nome="ausencia_de_evidencia_de_keyword",
        afirmacao="o benchmark não contém teste de desfecho no nível de keyword",
        confianca="alta",
        bloqueia=False,
        autoriza=False,
        origem="webgo/20260903T010510Z (KEYWORD_OR_MATCH_CHANGE: 1 episódio legível)",
        limitacao=(
            "este é o único prior de confiança alta, e o que ele afirma é uma AUSÊNCIA: "
            "nenhuma regra de elegibilidade de keyword pode citar aquele pacote como validação"
        ),
    ),
)


# ── decisões ────────────────────────────────────────────────────────────────

INCLUDE = "INCLUDE"
EXPERIMENT = "EXPERIMENT"
HOLD = "HOLD"
REJECT = "REJECT"
HUMAN_REVIEW = "HUMAN_REVIEW"

DECISOES: Tuple[str, ...] = (INCLUDE, EXPERIMENT, HOLD, REJECT, HUMAN_REVIEW)

# Portões que NÃO são deste módulo e que continuam valendo depois dele.
PORTOES_EXTERNOS: Tuple[str, ...] = (
    "conta", "destino_pago", "mensuracao", "aprovacao_humana",
)

ESTAGIOS = ("tofu", "mofu", "bofu", "desconhecido")

# Versão da política de seleção. Muda quando o critério muda — é o que permite
# a um conjunto antigo dizer sob qual régua ele foi montado.
SELECTION_POLICY_VERSION = "pautador-paid-keyword-eligibility-v1"


@dataclass
class PaidKeywordDecision:
    """A decisão sobre UM termo, com as razões e os estados que a sustentam."""

    termo: str
    termo_normalizado: str
    #: A grafia ANTES de qualquer reescrita (ano normalizado, por exemplo).
    #: `None` quando o termo chegou como está — um termo que MUDOU antes de
    #: entrar na campanha precisa dizer de onde veio.
    original: Optional[str] = None
    subintencao: Optional[str] = None
    fonte: str = "mineracao"
    estagio: str = "desconhecido"
    arquetipos: Tuple[str, ...] = ()
    match_type: str = PHRASE
    #: ⚠️ O QUE ESTE VOLUME MEDE, E O QUE ELE NÃO MEDE.
    #:
    #: `avg_monthly_searches` é ARREDONDADO, agrega a keyword E SUAS VARIANTES
    #: PRÓXIMAS, e é sempre estatística de correspondência EXATA — "you'll be
    #: shown the same exact match stats whether you use a broad, phrase, or
    #: exact match type" (support.google.com/google-ads/answer/3022575). Não
    #: existe volume "de PHRASE": o número ao lado de um termo PHRASE é o
    #: volume exato do termo e das variantes que o Google junta nele.
    #: Ele também é condicionado a geo, rede e janela de meses do pedido.
    volume: Sinal = field(default_factory=lambda: Sinal.ausente("nao_lido"))
    cpc: Sinal = field(default_factory=lambda: Sinal.ausente("nao_lido"))
    competicao: Sinal = field(default_factory=lambda: Sinal.ausente("nao_lido"))
    lance_topo: Sinal = field(default_factory=lambda: Sinal.ausente("nao_lido"))
    congruencia: str = "nao_avaliada"     # congruente | incongruente | nao_avaliada
    amplitude: str = "media"              # estreita | media | ampla
    riscos: Dict[str, bool] = field(default_factory=dict)
    viabilidade: str = "desconhecida"     # cabe_no_teto | acima_do_teto | desconhecida
    evidencias: List[Evidencia] = field(default_factory=list)
    confianca: str = "baixa"
    decisao: str = HOLD
    motivos: List[str] = field(default_factory=list)
    bloqueadores: List[str] = field(default_factory=list)
    alertas: List[str] = field(default_factory=list)
    selecionada: bool = False

    def como_dicionario(self) -> Dict[str, Any]:
        return {
            "termo": self.termo,
            "termo_normalizado": self.termo_normalizado,
            "original": self.original,
            "fonte": self.fonte,
            "subintencao": self.subintencao,
            "estagio": self.estagio,
            "arquetipos": list(self.arquetipos),
            "match_type": self.match_type,
            "volume": self.volume.como_dicionario(),
            "cpc": self.cpc.como_dicionario(),
            "competicao": self.competicao.como_dicionario(),
            "lance_topo": self.lance_topo.como_dicionario(),
            "congruencia": self.congruencia,
            "amplitude": self.amplitude,
            "riscos": dict(self.riscos),
            "viabilidade": self.viabilidade,
            "evidencias": [e.como_dicionario() for e in self.evidencias],
            "confianca": self.confianca,
            "decisao": self.decisao,
            "situacao": self.situacao,
            "motivos": list(self.motivos),
            "bloqueadores": list(self.bloqueadores),
            "alertas": list(self.alertas),
            "selecionada": self.selecionada,
        }

    @property
    def situacao(self) -> str:
        """O que aconteceu com o termo, dito numa palavra.

        `decisao` responde "este termo é elegível?" e é propriedade do termo.
        `situacao` responde "ele entrou no conjunto?", que é outra pergunta —
        um termo pode ser elegível e ficar de fora por quantidade. Colapsar as
        duas foi como `INCLUDE` acabava listado ao lado de `HOLD` na tela de
        retidos, sem que se pudesse dizer qual dos dois pede medição e qual
        pede só uma vaga.
        """
        if self.selecionada:
            return "SELECIONADO"
        if self.decisao == INCLUDE:
            return "ELEGIVEL_NAO_SELECIONADO"
        return self.decisao

    def identidade(self) -> Tuple[str, str, str, str]:
        """O que define o termo para efeito de aprovação.

        Termo COMO SERÁ EXPORTADO, termo normalizado, match type e
        sub-intenção. Mudar qualquer um dos quatro muda o que está sendo
        aprovado — e a impressão precisa mudar junto.

        ⚠️ `termo` entrou aqui depois que uma revisão adversarial mostrou o
        buraco: a impressão cobria só `termo_normalizado`, e a exportação lê
        `termo`. Trocar `decisao.termo` de `advogado trabalhista` para
        `cassino online` deixava `approved_set_sha256` intacto e mudava o que
        ia para a campanha. Um hash que não cobre o campo exportado não
        congela nada.
        """
        return (self.termo, self.termo_normalizado, self.match_type, self.subintencao or "")


def decidir_keyword(
    bruto: Dict[str, Any],
    *,
    subintencao: Optional[str] = None,
    estagio: str = "desconhecido",
    fonte: str = "mineracao",
    teto_do_dono: Optional[float] = None,
    congruencia: str = "nao_avaliada",
    marcas_proprias: Sequence[str] = (),
    marcas_de_terceiro: Sequence[str] = (),
    evidencias: Optional[Sequence[Evidencia]] = None,
    momento_da_decisao: str = PRE_LANCAMENTO,
    campanha_ref: Optional[str] = None,
    medicao_confirmada: bool = False,
) -> PaidKeywordDecision:
    """A decisão sobre um termo, com razão escrita para cada caminho.

    Nenhum ramo lê um número sem olhar o estado dele antes. Volume alto não
    vence incongruência nem intenção errada, e ausência nunca pontua melhor
    que medição.
    """
    evidencias = list(evidencias or [])
    _guardar_vazamento(evidencias, momento_da_decisao, campanha_ref)

    termo = str(bruto.get("keyword") or bruto.get("termo") or "")
    normalizado = normalizar_termo(termo)
    arqs = arquetipos(termo)
    risco = riscos(termo, marcas_proprias=marcas_proprias, marcas_de_terceiro=marcas_de_terceiro)

    d = PaidKeywordDecision(
        termo=termo,
        termo_normalizado=normalizado,
        original=bruto.get("original"),
        subintencao=subintencao,
        fonte=fonte,
        estagio=estagio if estagio in ESTAGIOS else "desconhecido",
        arquetipos=arqs,
        match_type=propor_match_type(termo, arqs),
        volume=Sinal.de_bruto(bruto, "volume", fonte=fonte, medicao_confirmada=medicao_confirmada),
        cpc=Sinal.de_bruto(bruto, "cpc", fonte=fonte, medicao_confirmada=medicao_confirmada),
        competicao=Sinal.de_bruto(bruto, "competition_index", fonte=fonte),
        lance_topo=Sinal.de_bruto(bruto, "high_bid", fonte=fonte),
        congruencia=congruencia,
        amplitude="ampla" if len(normalizado.split()) <= 2 else "estreita",
        riscos=risco,
        evidencias=evidencias,
    )

    if not normalizado:
        d.decisao = REJECT
        d.motivos.append("termo_vazio")
        return d

    # Viabilidade perante o teto DECLARADO. Sem teto, "desconhecida" — nunca
    # inventada, e nunca confundida com "cabe".
    if teto_do_dono is None:
        d.viabilidade = "desconhecida"
        d.alertas.append("teto_economico_do_dono_nao_declarado")
    elif d.cpc.tem_numero:
        d.viabilidade = "cabe_no_teto" if d.cpc.valor <= teto_do_dono else "acima_do_teto"
    else:
        d.viabilidade = "desconhecida"
        d.alertas.append("cpc_sem_medicao_impede_avaliar_teto")

    # 1. RISCO ANTES DE TUDO. Marca de terceiro e entidade pública saem do
    #    caminho automático — para os dois lados, inclusão e negativa.
    if risco["marca_terceiro"]:
        d.decisao = HUMAN_REVIEW
        d.motivos.append("aponta_para_marca_de_terceiro")
        d.bloqueadores.append("decisao_juridica_e_comercial_nao_e_do_motor")
        # ⚠️ O QUE EXATAMENTE ESTÁ SENDO DECIDIDO — porque as duas coisas têm
        # respostas diferentes na política do Google e são fáceis de colapsar.
        #
        # A política de marcas registradas NÃO restringe "usar marcas como
        # palavras-chave"; ela restringe "usar marcas no TEXTO de um anúncio de
        # concorrente direto". Ou seja, o termo pode ser elegível como keyword e
        # o anúncio ser proibido — e quem revisa precisa saber que está
        # decidindo o primeiro, não o segundo.
        d.alertas.append("elegibilidade_de_keyword_e_de_texto_de_anuncio_sao_decisoes_distintas")
        return d
    # 2. INTENÇÃO ANTES DE VOLUME. É o defeito medido: os dois termos de maior
    #    volume do funil BPC/LOAS eram `meu inss login` e `inss telefone 135`.
    #
    #    O termo navegacional/suporte que TAMBÉM nomeia entidade pública é o
    #    caso de impersonação — vai para revisão humana, não para o descarte
    #    silencioso, porque negativá-lo sozinho também seria decidir demais.
    if risco["navegacional_ou_suporte"]:
        d.decisao = HUMAN_REVIEW if risco["institucional_governo"] else HOLD
        d.motivos.append("intencao_navegacional_ou_suporte")
        d.bloqueadores.append("volume_nao_compra_intencao")
        if risco["institucional_governo"]:
            d.motivos.append("navegacional_para_entidade_publica")
        if d.volume.tem_numero:
            d.alertas.append(f"volume_medido_alto_ignorado:{int(d.volume.valor)}")
        return d

    # ⚠️ ENTIDADE PÚBLICA NO TERMO É ANOTAÇÃO, NÃO VEREDITO.
    #
    # A primeira versão desta regra mandava para revisão humana TODO termo que
    # citasse INSS, DETRAN, IPVA, BPC ou LOAS — e o resultado, medido, foi 8 de
    # 8 termos do funil BPC/LOAS retidos. Um motor que retém tudo não separa
    # nada, e a fronteira que ele defenderia deixa de ser testável.
    #
    # O risco real é de DESTINO, não de vocabulário: quem responde por
    # `government_services` é `landing_policy`, cujo portão continua valendo
    # depois deste. Aqui o sinal fica escrito, viaja no alerta e baixa a
    # confiança — que é o que uma anotação deve fazer.
    if risco["institucional_governo"] and not risco["marca_propria"]:
        d.alertas.append("termo_cita_entidade_publica")
        d.alertas.append("verificar_politica_de_servicos_governamentais_no_destino")

    if d.congruencia == "incongruente":
        d.decisao = REJECT
        d.motivos.append("termo_nao_congruente_com_anuncio_e_pagina")
        return d

    # 3. ZERO CONFIRMADO é o único zero que decide. Todo outro pede medição.
    if d.volume.estado == ZERO_CONFIRMADO:
        d.decisao = REJECT
        d.motivos.append("demanda_zero_confirmada_na_medicao")
        d.confianca = "media"
        return d

    if not d.volume.tem_numero:
        d.decisao = HOLD
        d.motivos.append(f"volume_{d.volume.estado}")
        d.bloqueadores.append("ausencia_de_volume_nao_e_ausencia_de_demanda")
        if not d.cpc.tem_numero:
            d.bloqueadores.append(f"cpc_{d.cpc.estado}")
        return d

    # 4. Volume medido. O que separa INCLUDE de EXPERIMENT é a economia MEDIDA,
    #    não a economia assumida — CPC ausente vira experimento, não desconto.
    if d.congruencia == "nao_avaliada":
        d.alertas.append("congruencia_termo_anuncio_pagina_nao_avaliada")

    if d.cpc.tem_numero:
        d.decisao = INCLUDE
        d.confianca = "media" if d.congruencia == "congruente" else "baixa"
        d.motivos.append("volume_e_cpc_medidos_com_intencao_compativel")
        if d.viabilidade == "acima_do_teto":
            d.decisao = EXPERIMENT
            d.motivos.append("cpc_medido_acima_do_teto_declarado")
    else:
        d.decisao = EXPERIMENT
        d.confianca = "baixa"
        d.motivos.append("volume_medido_mas_cpc_sem_medicao")
        d.bloqueadores.append(f"cpc_{d.cpc.estado}")
        motivo_cpc = bruto.get("cpc_motivo_de_ausencia")
        if motivo_cpc:
            # `average_cpc_micros` só vem com `include_average_cpc=true`, então
            # a ausência dele pode ser "não pedimos", não "não existe".
            d.alertas.append(str(motivo_cpc))
        if not d.lance_topo.tem_numero:
            # Faixa de lance ausente = histórico de leilão recente magro nos
            # últimos 30 dias. NÃO quer dizer que a keyword é gratuita.
            d.alertas.append("faixa_de_lance_ausente_indica_historico_de_leilao_magro")

    if d.amplitude == "ampla":
        d.alertas.append("termo_amplo_pode_puxar_intencao_alheia")
    # Nenhum match type isola: variantes próximas valem para EXACT e PHRASE.
    d.alertas.append(ALERTA_VARIANTES_PROXIMAS)
    return d


# ── o conjunto, e a impressão que o congela ─────────────────────────────────


class ConjuntoCongelado(RuntimeError):
    """Alguém tentou mexer num conjunto já aprovado."""


class HashDivergente(ValueError):
    """A aprovação citou uma impressão que não é a do conjunto apresentado."""


def impressao_de_decisoes(decisoes: Iterable[PaidKeywordDecision]) -> str:
    """SHA-256 do conjunto, com semântica de CONJUNTO — decidida, não acidental.

    A ordem NÃO entra. Duas apresentações do mesmo conjunto aprovam a mesma
    coisa, e a ordenação canônica existe só para tornar a impressão
    reproduzível. Já `termo_normalizado`, `match_type` e `subintencao` entram
    os três: mudar qualquer um muda o que se está aprovando.
    """
    # `set` antes de `sorted`: a docstring promete semântica de CONJUNTO, e
    # `sorted` sobre um gerador preservava duplicatas. Duas decisões com o mesmo
    # (termo, match type, sub-intenção) são a mesma operação para a API — contá-las
    # duas vezes faria a impressão depender de quantas vezes o termo foi minerado.
    identidades = sorted(set(d.identidade() for d in decisoes))
    bruto = json.dumps(
        {"policy": SELECTION_POLICY_VERSION, "keywords": identidades},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


@dataclass
class CampaignKeywordSet:
    """O conjunto literal que pode ser preparado — e nada além disso."""

    candidates: List[PaidKeywordDecision] = field(default_factory=list)
    selected_keywords: List[PaidKeywordDecision] = field(default_factory=list)
    excluded_keywords: List[PaidKeywordDecision] = field(default_factory=list)
    human_review_keywords: List[PaidKeywordDecision] = field(default_factory=list)
    negative_keywords: List[Dict[str, Any]] = field(default_factory=list)
    owner_ceiling: Optional[float] = None
    selection_policy_version: str = SELECTION_POLICY_VERSION
    evidence_snapshot: Dict[str, Any] = field(default_factory=dict)
    approved_set_sha256: Optional[str] = None
    aprovado_por: Optional[str] = None
    blockers: List[str] = field(default_factory=list)
    alertas: List[str] = field(default_factory=list)

    # ── portões que continuam de fora ───────────────────────────────────────
    @property
    def portoes_externos_pendentes(self) -> Dict[str, str]:
        """Este módulo não avalia conta, destino, mensuração nem autorização.

        Devolver "nao_avaliado_aqui" em vez de omitir é deliberado: um campo
        ausente seria lido como "sem pendência".
        """
        return {portao: "nao_avaliado_aqui" for portao in PORTOES_EXTERNOS}

    @property
    def selected_set_sha256(self) -> str:
        return impressao_de_decisoes(self.selected_keywords)

    @property
    def congelado(self) -> bool:
        return self.approved_set_sha256 is not None

    @property
    def ready_for_campaign_plan(self) -> bool:
        """O conjunto pode ser PREPARADO. Não é autorização de lançamento."""
        return bool(self.selected_keywords) and not self.blockers

    def acrescentar(self, decisao: PaidKeywordDecision) -> None:
        if self.congelado:
            raise ConjuntoCongelado(
                f"conjunto aprovado em {self.approved_set_sha256[:12]}… não aceita "
                f"acréscimo de {decisao.termo!r}"
            )
        self.candidates.append(decisao)
        if decisao.decisao == INCLUDE:
            decisao.selecionada = True
            self.selected_keywords.append(decisao)
        elif decisao.decisao == HUMAN_REVIEW:
            self.human_review_keywords.append(decisao)
        else:
            self.excluded_keywords.append(decisao)

    def como_dicionario(self) -> Dict[str, Any]:
        return {
            "candidates": [d.como_dicionario() for d in self.candidates],
            "selected_keywords": [d.como_dicionario() for d in self.selected_keywords],
            "excluded_keywords": [d.como_dicionario() for d in self.excluded_keywords],
            "human_review_keywords": [d.como_dicionario() for d in self.human_review_keywords],
            "negative_keywords": list(self.negative_keywords),
            "owner_ceiling": self.owner_ceiling,
            "selection_policy_version": self.selection_policy_version,
            "evidence_snapshot": dict(self.evidence_snapshot),
            "selected_set_sha256": self.selected_set_sha256,
            "approved_set_sha256": self.approved_set_sha256,
            "aprovado_por": self.aprovado_por,
            "ready_for_campaign_plan": self.ready_for_campaign_plan,
            "portoes_externos_pendentes": self.portoes_externos_pendentes,
            "blockers": list(self.blockers),
            "alertas": list(self.alertas),
        }


def impressao_do_conjunto(conjunto: CampaignKeywordSet) -> str:
    return conjunto.selected_set_sha256


def aprovar(
    conjunto: CampaignKeywordSet, *, aprovado_por: str, hash_conferido: str
) -> CampaignKeywordSet:
    """Congela o conjunto contra a impressão que o humano de fato conferiu.

    `hash_conferido` não é cerimônia: é o que impede aprovar uma tela e
    exportar outra coisa. Divergiu, não aprova.
    """
    atual = conjunto.selected_set_sha256
    if hash_conferido != atual:
        raise HashDivergente(
            f"impressão conferida {hash_conferido[:12]}… difere do conjunto {atual[:12]}…"
        )
    conjunto.approved_set_sha256 = atual
    conjunto.aprovado_por = aprovado_por
    return conjunto


# ── reconciliação com os contratos que já existem ───────────────────────────
#
# ⚠️ ESTE MÓDULO É O TERCEIRO VOCABULÁRIO DE AUSÊNCIA DO REPOSITÓRIO, E ISSO
# PRECISA DE JUSTIFICATIVA, NÃO DE SILÊNCIO.
#
# Os outros dois, ambos legítimos e ambos com dono:
#
#   `app.validacao.orquestrador.Eixo.proveniencia`  medido | julgado | ausente
#       Fala de EIXO EDITORIAL. `PROVENIENCIA_EQUIVALENTE`, no topo deste
#       arquivo, traduz para lá — as duas metades do Pautador continuam
#       falando a mesma língua sem que nenhuma reescreva a outra.
#
#   `app.criativo.bancada.contrato.Ausencia`        nao_medido | nao_apurado |
#       nao_declarado | nao_suportado | nao_aplicavel | sem_custo_de_provider |
#       falhou | mismatch | aguardando_aprovacao
#       Fala de CAMPO DE TRABALHO na bancada de criativos, e distingue coisas
#       que um sinal de leilão não tem (custo de provider, aprovação pendente).
#       `AUSENCIA_EQUIVALENTE` mapeia o que é mapeável e deixa explícito o que
#       não é: `mismatch` — "sei, e está errado" — não tem análogo aqui, e
#       inventar um seria fingir uma medição que este módulo não faz.
#
# O que justifica o terceiro é o eixo: nenhum dos dois expressa
# `confirmed_zero`, e sem ele "demanda medida como zero" e "demanda não medida"
# caem no mesmo lugar — que é literalmente o defeito de `classifier.py` que
# esta sprint fechou.

AUSENCIA_EQUIVALENTE: Dict[str, str] = {
    AUSENTE: "nao_medido",
    DESCONHECIDO: "nao_declarado",
    NAO_APLICAVEL: "nao_aplicavel",
    FALHOU: "falhou",
}


class CriterioIndisponivel(RuntimeError):
    """`volc_ads` não está no path — a conversão para critério não é possível."""


def para_criterios_de_campanha(
    conjunto: CampaignKeywordSet, *, exigir_aprovacao: bool = True
) -> List[Any]:
    """Converte o conjunto SELECIONADO em `volc_ads.campanha.criterio.Criterio`.

    A ponte explícita para o lado pago aterrissa no contrato que JÁ EXISTE, em
    vez de abrir um segundo. `Criterio` é imutável, valida match type, nível e
    origem, e recusa `origem="SEARCH_TERM"` sem evidência medida com janela —
    tudo isso continua valendo e não é reimplementado aqui.

    A importação é preguiçosa de propósito: `volc_ads` mora fora de
    `backend/app` e é consumido por outra lane. Uma dependência dura faria a
    mineração deixar de importar num ambiente onde aquele pacote não está, e
    este módulo não precisa dele para decidir — só para entregar.

    `exigir_aprovacao=True` é o padrão porque é o portão que esta sprint
    existiu para instalar: sem `approved_set_sha256`, não há conjunto literal
    aprovado, e converter seria produzir critérios que ninguém conferiu.

    NENHUMA NEGATIVA É PRODUZIDA AQUI. Negativa exige search-term evidence e
    revisão de overblocking, e as duas coisas moram fora deste módulo.
    """
    try:
        from volc_ads.campanha.criterio import Criterio
    except ImportError as exc:  # pragma: no cover - depende do layout de deploy
        raise CriterioIndisponivel(str(exc)) from exc

    conferir_congelamento(conjunto)
    if exigir_aprovacao and not conjunto.congelado:
        raise ConjuntoCongelado(
            "conjunto sem approved_set_sha256 não vira critério — aprove antes, "
            "ou passe exigir_aprovacao=False para um ensaio explicitamente seco"
        )
    return [
        Criterio(
            texto=d.termo,
            match_type=d.match_type,
            negativa=False,
            nivel="AD_GROUP",
            grupo=d.subintencao,
            origem="PAUTADOR",
            motivo="; ".join(d.motivos) or None,
            aprovado_por=conjunto.aprovado_por,
        )
        for d in conjunto.selected_keywords
    ]


def conferir_congelamento(conjunto: CampaignKeywordSet) -> None:
    """O congelamento é verificado no USO, não só na escrita.

    ⚠️ `aprovar()` sozinho não congela nada, e uma revisão adversarial provou:
    `CampaignKeywordSet` é dataclass mutável e `selected_keywords` é lista, então

        aprovar(conjunto, ...)
        conjunto.selected_keywords.append(decisao_retida)

    passava por cima de `acrescentar()` sem tocar em `approved_set_sha256`, e a
    exportação passava a incluir um termo que ninguém aprovou.

    Nenhuma quantidade de disciplina no construtor resolve isso — Python não
    tem congelamento profundo de graça. O que resolve é toda saída conferir a
    impressão ATUAL contra a aprovada antes de entregar qualquer coisa.
    """
    if not conjunto.congelado:
        return
    atual = conjunto.selected_set_sha256
    if atual != conjunto.approved_set_sha256:
        raise HashDivergente(
            f"o conjunto mudou depois de aprovado: impressão atual {atual[:12]}… "
            f"difere da aprovada {conjunto.approved_set_sha256[:12]}…. "
            "Nada é exportado a partir de um conjunto que divergiu da aprovação."
        )
    if conjunto.negative_keywords:
        # A promessa "nenhuma negativa é criada aqui" precisava de um guarda,
        # não de uma frase: a lista é pública e mutável.
        raise HashDivergente(
            "conjunto aprovado carrega negativas — este motor não cria negativa, "
            "e negativa exige search-term evidence com revisão de overblocking"
        )


def derivar_lista_google_ads(conjunto: CampaignKeywordSet) -> str:
    """A lista que vai para o Google Ads, derivada EXATAMENTE de `selected`.

    Uma função só, usada pelo produtor e pelo teste — é o que impede a
    divergência silenciosa que abriu esta sprint.

    ⚠️ Esta lista é TEXTO PLANO e por construção NÃO carrega match type nem
    sub-intenção. Dois conjuntos aprovados diferentes — mesmo termo em EXACT /
    elegibilidade e em PHRASE / transacional — produzem o mesmo texto aqui,
    com impressões diferentes. Ela é conveniência de colagem, não o portador da
    semântica aprovada: quem carrega a semântica é `para_criterios_de_campanha`,
    que devolve `Criterio` com match type, nível e grupo.
    """
    conferir_congelamento(conjunto)
    return "\n".join(d.termo for d in conjunto.selected_keywords)


# ── política de seleção por sub-intenção ────────────────────────────────────
#
# ⚠️ PROVENIÊNCIA DOS LIMIARES, DECLARADA EM VEZ DE ASSUMIDA.
#
# 20000 / 3 / 10 não foram calibrados aqui nem em lugar nenhum do repositório.
# Eles são cópia literal do nó "🏭 FUNNEL FACTORY" do n8n
# (`backend/n8n_kw_pautador.json`), onde aparecem como `VOLUME_THRESHOLD`,
# `MIN_ITEMS_PER_INTENT` e `MAX_ITEMS_PER_INTENT` sem nenhuma justificativa
# registrada. Classificação honesta: DEFAULT OPERACIONAL PORTADO, não fato
# calibrado.
#
# Esta sprint NÃO os altera — mudar um número sem evidência seria o mesmo erro
# na direção oposta. O que ela faz é (a) nomeá-los, (b) versioná-los em
# `SELECTION_POLICY_VERSION` e (c) gravá-los no `evidence_snapshot`, para que a
# próxima pessoa saiba que está olhando para um default e não para uma medição.

VOLUME_THRESHOLD = 20000
MIN_ITEMS = 3
MAX_ITEMS = 10

POLITICA_DE_SELECAO = {
    "volume_threshold": VOLUME_THRESHOLD,
    "min_items_por_subintencao": MIN_ITEMS,
    "max_items_por_subintencao": MAX_ITEMS,
    "origem": "portado de n8n_kw_pautador.json (nó FUNNEL FACTORY)",
    "classificacao": "default_operacional_portado",
    "calibrado": False,
    "justificativa_registrada": None,
}


def aplicar_politica_de_selecao(
    elegiveis: Sequence[PaidKeywordDecision],
) -> Tuple[List[PaidKeywordDecision], List[PaidKeywordDecision]]:
    """Aplica o corte por volume SOBRE o conjunto já elegível — nunca antes.

    A ordem importa e é o coração da correção: elegibilidade primeiro,
    quantidade depois. Invertida, o corte por volume promove justamente os
    termos navegacionais que a elegibilidade recusaria.

    Termos sem volume medido não podem ser ordenados por volume, e ordenar
    tratando-os como 0 é a coerção que esta sprint fecha — então eles ficam
    depois dos medidos, com o estado preservado.

    ⚠️ Pelo caminho de `funnel_factory` esse ramo não é alcançado hoje:
    `decidir_keyword` devolve HOLD para volume sem número, e só INCLUDE chega
    aqui. Ele fica como guarda para chamadores que passem outro recorte — não
    como comportamento que este pipeline exercite. Dizer o contrário seria
    documentação afirmando cobertura que o teste não tem.
    """
    medidos = sorted(
        [d for d in elegiveis if d.volume.tem_numero],
        key=lambda d: d.volume.valor, reverse=True,
    )
    sem_numero = [d for d in elegiveis if not d.volume.tem_numero]
    ordenados = medidos + sem_numero

    acima = [d for d in ordenados if d.volume.tem_numero and d.volume.valor >= VOLUME_THRESHOLD]
    if len(acima) < MIN_ITEMS:
        escolhidos = ordenados[: min(MAX_ITEMS, len(ordenados))]
    else:
        escolhidos = acima[:MAX_ITEMS]

    ids = {id(d) for d in escolhidos}
    fora = [d for d in ordenados if id(d) not in ids]
    for d in fora:
        d.motivos.append("fora_da_politica_de_selecao_por_volume")
        d.alertas.append("elegivel_mas_nao_selecionado")
    return escolhidos, fora


def montar_conjunto(
    decisoes: Sequence[PaidKeywordDecision],
    selecionadas: Sequence[PaidKeywordDecision],
    *,
    teto_do_dono: Optional[float] = None,
    evidence_snapshot: Optional[Dict[str, Any]] = None,
) -> CampaignKeywordSet:
    """Monta o conjunto SEM reabrir nenhuma decisão já tomada."""
    conhecidas = {id(d) for d in decisoes}
    fantasmas = [d for d in selecionadas if id(d) not in conhecidas]
    if fantasmas:
        # Descartar em silêncio uma seleção que não está entre as decisões
        # produziria um conjunto vazio com o motivo errado
        # (`nenhuma_keyword_elegivel_selecionada`), escondendo um bug do
        # chamador atrás de uma mensagem de negócio plausível.
        raise ValueError(
            "montar_conjunto recebeu seleções que não estão entre as decisões: "
            + ", ".join(repr(d.termo) for d in fantasmas[:5])
        )
    escolhidas = {id(d) for d in selecionadas}
    conjunto = CampaignKeywordSet(
        owner_ceiling=teto_do_dono,
        evidence_snapshot=dict(evidence_snapshot or {}),
    )
    conjunto.evidence_snapshot.setdefault("politica_de_selecao", dict(POLITICA_DE_SELECAO))
    conjunto.evidence_snapshot.setdefault(
        "priors_de_benchmark",
        [
            {"nome": p.nome, "confianca": p.confianca, "bloqueia": p.bloqueia,
             "autoriza": p.autoriza, "origem": p.origem}
            for p in PRIORS_DE_BENCHMARK
        ],
    )

    for d in decisoes:
        conjunto.candidates.append(d)
        if id(d) in escolhidas and d.decisao == INCLUDE:
            d.selecionada = True
            conjunto.selected_keywords.append(d)
        elif d.decisao == HUMAN_REVIEW:
            conjunto.human_review_keywords.append(d)
        else:
            conjunto.excluded_keywords.append(d)

    if teto_do_dono is None:
        conjunto.blockers.append("teto_economico_desconhecido")
    if not conjunto.selected_keywords:
        conjunto.blockers.append("nenhuma_keyword_elegivel_selecionada")

    # ⚠️ CONGRUÊNCIA NÃO AVALIADA BLOQUEIA O CONJUNTO, NÃO A KEYWORD.
    #
    # Uma revisão externa apontou que liberar INCLUDE com congruência
    # `nao_avaliada` expõe o termo a índice de qualidade baixo por relevância
    # de anúncio e página. Está certo — e a resposta correta não é recusar o
    # termo, porque quem avalia congruência de destino é outra lane e ela pode
    # nem ter rodado ainda. A resposta é a mesma regra que vale para o teto:
    # desconhecido não abre o portão. O termo continua elegível; o CONJUNTO
    # não fica pronto enquanto ninguém tiver olhado o destino.
    if any(d.congruencia == "nao_avaliada" for d in conjunto.selected_keywords):
        conjunto.blockers.append("congruencia_nao_avaliada")

    if conjunto.human_review_keywords:
        conjunto.alertas.append(
            f"{len(conjunto.human_review_keywords)}_termos_aguardando_revisao_humana"
        )

    # ⚠️ O QUE FOI RETIDO CONTINUA ALCANÇÁVEL — e isso precisa estar escrito.
    #
    # Reter `meu inss login` do conjunto NÃO impede que uma busca por ele
    # acione um termo INCLUÍDO, porque variantes próximas valem para EXACT e
    # PHRASE. Fechar isso exige negativa, negativa exige search-term evidence,
    # e evidência de search term só existe depois do lançamento. O motor não
    # resolve o círculo — ele o declara.
    retidos_por_intencao = [
        d for d in conjunto.excluded_keywords + conjunto.human_review_keywords
        if d.riscos.get("navegacional_ou_suporte")
    ]
    if retidos_por_intencao and conjunto.selected_keywords:
        conjunto.alertas.append(
            "termos_navegacionais_retidos_seguem_alcancaveis_por_variante_proxima"
            "__negativa_exige_search_term_evidence"
        )

    # Um mesmo termo selecionado em duas sub-intenções vira dois critérios em
    # ad groups diferentes, competindo entre si. Não é erro do motor decidir
    # assim — é informação que o operador precisa ver antes de aprovar.
    vistos: Dict[str, str] = {}
    for d in conjunto.selected_keywords:
        anterior = vistos.get(d.termo_normalizado)
        if anterior is not None and anterior != (d.subintencao or ""):
            conjunto.alertas.append(
                f"termo_em_mais_de_uma_subintencao:{d.termo_normalizado}"
            )
        vistos[d.termo_normalizado] = d.subintencao or ""
    return conjunto


def media_de_cpc(decisoes: Sequence[PaidKeywordDecision]) -> Sinal:
    """A média dos CPCs MEDIDOS — nunca dos zeros que a ausência produzia.

    Média sem proveniência é pior que buraco: o funil IPVA publicava
    `avg_cpc: "0.00"` com dois termos que nunca tiveram CPC nenhum.
    """
    valores = [d.cpc.valor for d in decisoes if d.cpc.estado == MEDIDO]
    if not valores:
        return Sinal.ausente("nenhum_cpc_medido", fonte="derivado")
    return Sinal(round(sum(valores) / len(valores), 2), MEDIDO, fonte="derivado")


def media_de_volume(decisoes: Sequence[PaidKeywordDecision]) -> Sinal:
    valores = [d.volume.valor for d in decisoes if d.volume.estado == MEDIDO]
    if not valores:
        return Sinal.ausente("nenhum_volume_medido", fonte="derivado")
    return Sinal(float(sum(valores)), MEDIDO, fonte="derivado")


__all__ = [
    "MEDIDO", "ZERO_CONFIRMADO", "AUSENTE", "DESCONHECIDO", "NAO_APLICAVEL",
    "FALHOU", "INFERIDO", "ESTADOS", "PROVENIENCIA_EQUIVALENTE",
    "EstadoInvalido", "Sinal",
    "ARQUETIPOS", "ARQUETIPOS_RETIDOS", "arquetipos", "riscos", "normalizar_termo",
    "EXACT", "PHRASE", "BROAD", "propor_match_type",
    "PRE_LANCAMENTO", "POS_LANCAMENTO", "Evidencia", "VazamentoDeDesfecho",
    "PriorDeBenchmark", "PRIORS_DE_BENCHMARK",
    "INCLUDE", "EXPERIMENT", "HOLD", "REJECT", "HUMAN_REVIEW", "DECISOES",
    "PORTOES_EXTERNOS", "SELECTION_POLICY_VERSION",
    "PaidKeywordDecision", "decidir_keyword",
    "CampaignKeywordSet", "ConjuntoCongelado", "HashDivergente",
    "impressao_de_decisoes", "impressao_do_conjunto", "aprovar",
    "conferir_congelamento",
    "derivar_lista_google_ads", "para_criterios_de_campanha",
    "CriterioIndisponivel", "AUSENCIA_EQUIVALENTE",
    "VOLUME_THRESHOLD", "MIN_ITEMS", "MAX_ITEMS", "POLITICA_DE_SELECAO",
    "aplicar_politica_de_selecao", "montar_conjunto",
    "media_de_cpc", "media_de_volume",
]
