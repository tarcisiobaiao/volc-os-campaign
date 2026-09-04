"""O que o Hub sabe fazer, por plataforma e por canal — declarado, não suposto.

## O problema que este módulo resolve

O sistema reconhece quatro canais do Google. Isso não significa que as mesmas
ações existam nos quatro: Search e Display montam, provam e podem chegar ao
executor real; Demand Gen monta e prova, mas não pode chegar à mutação real;
Performance Max planeja fora da porta HTTP genérica.

Sem essa distinção declarada, a tela oferece "criar campanha" por simetria
visual — quatro canais na lista, quatro botões — e o operador descobre a
ausência depois de montar o pedido inteiro, num `ValueError` do engine vazando
como erro 500. O trabalho já foi feito quando a resposta chega.

O manifesto é o que permite a tela derivar cada ação do que EXISTE, em vez de
do que está na lista.

⚠️ E o que existe MUDA. Quando Display ganhou construtor, este arquivo mudou na
mesma entrega — não porque alguém lembrou, mas porque
os testes de coerência entre registros derrubam as duas direções
do descompasso. Um manifesto que envelhece em silêncio é pior que nenhum: ele
esconde capacidade real com a autoridade de um registro.

## Por que a ausência é conteúdo, e não um espaço vazio

O ADR-19 proíbe ponto de extensão sem consumidor: nada de tela por canal sem
implementação, interface com um `NotImplementedError`, tabela sem linhas.

Este módulo não viola isso porque ele **não é uma interface esperando
implementação** — ele é um REGISTRO DE FATOS sobre o que cada canal pode fazer
hoje, e a resposta "não pode" é tão útil quanto "pode". Search e Display o
exercitam: é deles que sai a permissão de criar. Os outros o exercitam pela
negativa: é deles que sai a recusa com mensagem que diz o que existe.

## A regra de acoplamento, e onde ela é verificada

**Nenhum tipo do núcleo importa um tipo de canal.** A dependência aponta sempre
canal → núcleo (ADR-17 §9.4). Este módulo é núcleo: ele nomeia `SEARCH` como
VALOR de um vocabulário, e nunca importa `volc_ads.campanha.search`.

O gate é mecânico e vira teste: procurar `keyword`, `asset_group`, `placement`,
`audience` e `ad_set` nos módulos do núcleo deve dar zero. As hierarquias abaixo
citam "grupo", "anúncio" e "conjunto" como RÓTULOS DE TELA — texto que o
operador lê —, e não como tipos que o núcleo manipula.

## Duas coisas chamadas perfil, e a diferença

| onde | o quê |
|---|---|
| `plataforma.ManifestoDeCanal` | **declaração**: o que este canal pode, e o que não pode |
| `sincronizador.PerfilDeCanal` | **comportamento**: como a varredura lê as entidades filhas |

O primeiro é lido pela tela e pela porta de criação; o segundo é chamado pela
varredura. Um canal pode planejar fora da porta genérica, como PMax hoje.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Protocol, Sequence, Tuple

from app.trafego import dominio as dom

# ═══════════════════════════════════════════════════════════════════════════
# PLATAFORMA
# ═══════════════════════════════════════════════════════════════════════════

#: `MediaPlatform`. Onde a mídia é comprada.
#:
#: Duas, e só duas: a que o sistema opera hoje e a que a operação já declarou
#: como próxima. Uma terceira entra quando houver conta, credencial e leitura —
#: não quando alguém a mencionar.
GOOGLE_ADS = "GOOGLE_ADS"
META_ADS = "META_ADS"

PLATAFORMAS: Tuple[str, ...] = (GOOGLE_ADS, META_ADS)


# ═══════════════════════════════════════════════════════════════════════════
# NÍVEL DE ENTIDADE
# ═══════════════════════════════════════════════════════════════════════════
#
# `EntityLevel`. O que o operador vê ao descer a árvore.
#
# ⚠️ Estes são RÓTULOS DE APRESENTAÇÃO, não tipos do núcleo. O núcleo conhece
# `campanha` e nada abaixo dela; os degraus seguintes existem para a tela saber
# quantos níveis desenhar e como chamá-los.
#
# A tradução importa: no Meta o segundo nível é CONJUNTO, e chamá-lo de "grupo
# de anúncios" faria o operador procurar no painel do Meta uma palavra que não
# existe lá. Cada plataforma usa o nome que a própria plataforma usa.

CAMPANHA = "campanha"
GRUPO = "grupo"
CONJUNTO = "conjunto"
ASSET_GROUP = "asset_group"
ANUNCIO = "anuncio"
CRIATIVO = "criativo"
ASSET = "asset"
KEYWORD = "keyword"

NIVEIS: Tuple[str, ...] = (CAMPANHA, GRUPO, CONJUNTO, ASSET_GROUP, ANUNCIO,
                           CRIATIVO, ASSET, KEYWORD)


# ═══════════════════════════════════════════════════════════════════════════
# CAPACIDADE DE AÇÃO
# ═══════════════════════════════════════════════════════════════════════════
#
# `ActionCapability`. As três são degraus, não sinônimos, e a distância entre
# elas é o desenho inteiro da atuação segura:
#
#     LER      observar a conta. Não muda nada, e é tudo o que o P0 faz.
#     PROPOR   produzir uma proposta versionada, com antes/depois e validação.
#              Continua não mudando nada — mas produz algo que um humano pode
#              autorizar.
#     ESCREVER executar na conta, pela escada: autorização humana → execução
#              idempotente no backend → recibo → releitura → verificação.
#
# **Nenhum canal declara ESCREVER hoje**, e isso não é omissão: o ADR-11 mantém
# que nenhuma regra de bidding, graduação ou automação está aprovada, e a U0/H0
# não autoriza mutate em Google nem em Meta. O degrau existe no vocabulário para
# que a porta de escrita, quando existir, seja recusada por AUSÊNCIA DECLARADA
# em vez de por um `if` esquecido.

LER = "ler"
PROPOR = "propor"
ESCREVER = "escrever"

CAPACIDADES: Tuple[str, ...] = (LER, PROPOR, ESCREVER)


# ═══════════════════════════════════════════════════════════════════════════
# IDENTIDADE
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class IdentidadeDeCampanha:
    """`CampaignIdentity`. Uma instância, 1:1 com uma campanha externa (ADR-02).

    A identidade INTERNA é `volc_campaign_id` e nunca muda. A identidade
    EXTERNA passou a ser uma TRINCA — plataforma, conta, id externo — e não mais
    o par `(customer_id, campaign_id)`.

    ⚠️ A plataforma no meio da identidade é a mudança da H0, e ela é pequena de
    propósito. Sem ela, o dia em que a primeira campanha do Meta entrar traz uma
    colisão silenciosa: ids externos são numéricos nas duas plataformas e nada
    impede que o Google e o Meta emitam o mesmo número. Duas campanhas
    diferentes viveriam sob a mesma identidade externa, e o sistema não teria
    como perceber — a atribuição de receita de uma iria para a outra.

    Nome NUNCA entra na identidade. Ele muda, é editável por qualquer pessoa no
    painel da plataforma, e é a primeira coisa que alguém renomeia.
    """

    volc_campaign_id: str
    plataforma: str
    #: A conta na plataforma. `None` quando ainda não se sabe qual é — estado
    #: real, e não erro: há linhas legadas sem conta declarada, e afirmar uma
    #: seria inventar.
    conta_externa: Optional[str]
    id_externo: str

    def __post_init__(self) -> None:
        if self.plataforma not in PLATAFORMAS:
            raise ValueError(
                f"plataforma {self.plataforma!r} não existe. As plataformas "
                f"são: {', '.join(PLATAFORMAS)}.")
        if not str(self.volc_campaign_id or "").strip():
            raise ValueError("identidade interna vazia não é identidade.")
        if not str(self.id_externo or "").strip():
            raise ValueError("identidade externa sem id não é identidade.")

    @property
    def chave_externa(self) -> Tuple[str, Optional[str], str]:
        """A trinca que identifica a campanha fora daqui."""
        return (self.plataforma, self.conta_externa, self.id_externo)


@dataclass(frozen=True)
class LinhagemDeCampanha:
    """`CampaignLineage`. A intenção operacional, 1:N sobre instâncias (ADR-02).

    Uma linhagem agrupa testes, relançamentos e substituições da MESMA intenção.
    É o que permite responder "quantas vezes tentamos este termo?" sem confundir
    com "quantas campanhas existem".

    ⚠️ **Declarada no lançamento, nunca inferida.** Inferir equivalência por
    semelhança agruparia campanhas que só se parecem, e o histórico passaria a
    contar uma história que ninguém viveu. A inferência pode existir como
    SUGESTÃO; a atribuição é declaração.

    Ela atravessa plataformas de propósito: a mesma intenção pode ser perseguida
    no Google e no Meta, e separá-las por plataforma esconderia exatamente a
    comparação que justifica ter as duas.
    """

    campaign_lineage_id: str
    rotulo: str
    declarada_por: str
    motivo: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# O MANIFESTO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ManifestoDeCanal:
    """`ChannelProfile`. O que este canal pode, e — igualmente — o que não pode.

    Cada campo responde a uma pergunta que a tela ou a porta de criação faz. Um
    campo vazio é resposta, não lacuna: `campos_do_pedido=()` significa "não há
    pedido para montar", e é o que impede a tela de desenhar um formulário para
    um canal que não sabe construir nada.
    """

    plataforma: str
    canal: str
    #: Como o operador chama isto na tela.
    rotulo: str

    #: `hierarquia exibida` — os degraus da árvore, do topo para baixo. É o que
    #: a tela usa para saber quantos níveis desenhar e como nomeá-los.
    hierarquia: Tuple[str, ...]

    #: `painéis disponíveis` — o que o cockpit injeta dentro do shell comum.
    #: Vazio = só o shell, e o shell sozinho é uma tela honesta: cabeçalho,
    #: frescor, histórico e fila continuam valendo para qualquer canal.
    paineis: Tuple[str, ...] = ()

    #: `campos necessários para montagem/prova`. Vazio = não há builder.
    campos_do_pedido: Tuple[str, ...] = ()

    #: `capacidades de leitura` / `de proposta` / `de escrita`.
    capacidades: Tuple[str, ...] = (LER,)

    #: `provas obrigatórias` antes de qualquer criação. Elas são o que separa
    #: "montei o pedido" de "tenho o direito de gastar".
    provas_obrigatorias: Tuple[str, ...] = ()

    #: Portas distintas: um canal pode possuir builder + validate_only sem ser
    #: aceito pelo executor de mutação real. Demand Gen é exatamente esse caso.
    permite_prova: bool = False
    permite_mutacao_real: bool = False

    #: `indisponibilidades conhecidas` — por que este canal não faz o que não
    #: faz, em uma frase que a tela pode mostrar. É a diferença entre um botão
    #: cinza sem explicação e uma recusa que ensina.
    indisponibilidades: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.plataforma not in PLATAFORMAS:
            raise ValueError(f"plataforma {self.plataforma!r} não existe.")
        for nivel in self.hierarquia:
            if nivel not in NIVEIS:
                raise ValueError(
                    f"nível {nivel!r} não existe no vocabulário: "
                    f"{', '.join(NIVEIS)}.")
        for c in self.capacidades:
            if c not in CAPACIDADES:
                raise ValueError(f"capacidade {c!r} não existe.")
        if ESCREVER in self.capacidades and PROPOR not in self.capacidades:
            # Escrever sem propor é escrever sem antes/depois, sem validação e
            # sem autorização — exatamente a escada que a atuação segura existe
            # para não pular.
            raise ValueError(
                f"{self.canal}: escrever exige propor. A escada é fato "
                f"observado → proposta → validação → autorização → execução.")
        if self.permite_prova and not self.campos_do_pedido:
            raise ValueError(f"{self.canal}: prova sem campos de pedido")
        if self.permite_mutacao_real and not self.permite_prova:
            raise ValueError(f"{self.canal}: mutação real sem porta de prova")

    @property
    def sabe_provar(self) -> bool:
        return bool(self.campos_do_pedido) and self.permite_prova

    @property
    def sabe_criar(self) -> bool:
        """Há construtor para este canal?

        A tela deriva o botão daqui, e não da lista de canais. Um canal sem
        campos de pedido não tem o que montar, e oferecer a montagem só descobre
        isso depois do trabalho do operador.
        """
        return self.sabe_provar and self.permite_mutacao_real

    def pode(self, capacidade: str) -> bool:
        return capacidade in self.capacidades

    def json(self) -> Dict[str, Any]:
        return {
            "plataforma": self.plataforma,
            "canal": self.canal,
            "rotulo": self.rotulo,
            "hierarquia": list(self.hierarquia),
            "paineis": list(self.paineis),
            "campos_do_pedido": list(self.campos_do_pedido),
            "capacidades": list(self.capacidades),
            "provas_obrigatorias": list(self.provas_obrigatorias),
            "indisponibilidades": list(self.indisponibilidades),
            "sabe_criar": self.sabe_criar,
            "sabe_provar": self.sabe_provar,
        }


class AdaptadorDeCanal(Protocol):
    """`ChannelAdapter`. Traduz entre o núcleo e a API de cada canal.

    O núcleo pede fatos no vocabulário comum; o adaptador sabe onde eles moram
    na plataforma. É por aqui que a URL de destino entra sem o núcleo precisar
    saber que no Search ela vive no anúncio e em Performance Max viveria no
    asset group.

    ⚠️ Este Protocol descreve o adaptador de LEITURA, que é o único que existe.
    O de escrita não está declarado porque não há escrita aprovada (ADR-11), e
    declarar uma interface que ninguém implementa é o código morto com nome
    bonito que o ADR-19 proíbe.
    """

    plataforma: str
    canal: str

    def entidades_filhas(self) -> Tuple[str, ...]:
        """Rótulos do que este adaptador lê além da campanha."""

    def ler_filhas(self, buscar: Callable[[str], Iterable[Any]],
                   ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """Campos COMUNS extraídos das entidades filhas, por id externo."""


# ═══════════════════════════════════════════════════════════════════════════
# OS MANIFESTOS DE HOJE
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ Cada linha abaixo é um FATO MEDIDO sobre o repositório, não uma intenção.
# `test_o_manifesto_bate_com_o_que_o_engine_sabe_fazer` compara estas
# declarações com o que `volc_ads` de fato implementa — se alguém acrescentar um
# construtor sem atualizar o manifesto, ou o contrário, o teste derruba.

#: As provas que um canal roda antes de subir. Elas não são formalidade: `selo`
#: é o `validate_only` na conta real, e sem ele "montei o pedido" não é "posso
#: gastar". São as mesmas três em Search e em Display — o engine as declara uma
#: vez em `volc_ads/campanha/perfil.py:_PROVAS`, e aqui é a projeção para a tela.
_PROVAS_SEARCH: Tuple[str, ...] = ("politica", "duplicidade", "selo")

SEARCH = ManifestoDeCanal(
    plataforma=GOOGLE_ADS,
    canal=dom.canal_canonico("SEARCH") or "SEARCH",
    rotulo="Search",
    hierarquia=(CAMPANHA, GRUPO, ANUNCIO, KEYWORD),
    paineis=("keywords", "termos_de_busca", "anuncios", "negativas"),
    campos_do_pedido=("grupos", "keywords", "negativas", "copy", "url_final",
                      "verba_diaria", "estrategia_de_lance"),
    capacidades=(LER, PROPOR),
    provas_obrigatorias=_PROVAS_SEARCH,
    permite_prova=True,
    permite_mutacao_real=True,
)

#: ⚠️ Display passou a saber criar em 26/08/2026 (`volc_ads/campanha/display.py`),
#: e este manifesto mudou na MESMA entrega — é o que
#: O teste de coerência cobra: se o construtor
#: entra e o manifesto não acompanha, a tela esconde uma capacidade real.
#:
#: As indisponibilidades abaixo deixaram de falar de ausência de construtor e
#: passaram a descrever o que a PRIMEIRA FATIA não monta. Ausência declarada
#: continua sendo conteúdo: é o que impede a tela de desenhar um campo de
#: segmentação que o pedido não carrega.
DISPLAY = ManifestoDeCanal(
    plataforma=GOOGLE_ADS,
    canal="DISPLAY",
    rotulo="Display",
    hierarquia=(CAMPANHA, GRUPO, ANUNCIO, ASSET),
    paineis=("anuncios", "criativos"),
    campos_do_pedido=("copy", "criativos", "url_final", "verba_diaria",
                      "estrategia_de_lance"),
    capacidades=(LER, PROPOR),
    provas_obrigatorias=_PROVAS_SEARCH,
    permite_prova=True,
    permite_mutacao_real=True,
    indisponibilidades=(
        "a primeira fatia de Display não monta segmentação: a campanha nasce em "
        "inventário aberto, escolhido pelo lance. Tópicos, listas de público e "
        "demografia estão confirmados na matriz de API do canal e entram na "
        "fatia seguinte.",
        "segmentação positiva por posicionamento não entra: a documentação "
        "oficial se contradiz — a tabela de critérios diz que não existe, e a "
        "configuração de rede da campanha fala em veicular nos posicionamentos "
        "especificados — e a prova por validate_only na conta real ainda não "
        "foi autorizada. Excluir posicionamento (negativo) é onde as duas "
        "fontes concordam.",
        "sitelink, chamada e trecho estruturado não são montados em Display — "
        "a matriz não declara tipo nem campo para eles neste canal, e montá-los "
        "por analogia com Search subiria recurso que não veicula.",
        "Display não aceita lance manual: a tabela oficial de estratégias não "
        "declara compatibilidade do CPC manual com este canal, e sem termo de "
        "busca ele não teria sinal que filtrasse inventário. Só maximizar "
        "conversões, com CPA-alvo dentro.",
        "as palavras-chave do pedido não viram critério em Display; elas "
        "continuam servindo à triagem no cockpit.",
    ),
)

DEMAND_GEN = ManifestoDeCanal(
    plataforma=GOOGLE_ADS,
    canal="DEMAND_GEN",
    rotulo="Demand Gen",
    hierarquia=(CAMPANHA, GRUPO, ANUNCIO, ASSET),
    paineis=("anuncios", "criativos", "audiencias", "canais"),
    campos_do_pedido=(
        "copy", "criativos", "url_final", "verba_diaria",
        "estrategia_de_lance", "upgraded_targeting", "channel_controls",
        "audiencias", "intencoes", "exclusoes_de_audiencia",
    ),
    capacidades=(LER, PROPOR),
    provas_obrigatorias=_PROVAS_SEARCH,
    permite_prova=True,
    permite_mutacao_real=False,
    indisponibilidades=(
        "Demand Gen pode ser montado e conferido por validate_only somente "
        "quando a capacidade experimental do servidor estiver ligada. Ela "
        "nasce desligada.",
        "criação real continua recusada em /subir, no canário e no executor, "
        "mesmo depois de uma prova aceita.",
        "esta onda escolhe explicitamente o anúncio multi-asset; carrossel, "
        "vídeo responsivo e produto permanecem não suportados.",
        "intenção e exclusão têm campos próprios, mas itens não vazios falham "
        "fechado até a documentação/SDK confirmarem operações compatíveis.",
    ),
)

PERFORMANCE_MAX = ManifestoDeCanal(
    plataforma=GOOGLE_ADS,
    canal="PERFORMANCE_MAX",
    rotulo="Performance Max",
    hierarquia=(CAMPANHA, ASSET_GROUP, ASSET),
    capacidades=(LER,),
    indisponibilidades=(
        "o módulo PMax monta e serializa offline, mas a porta HTTP não possui "
        "o contrato tipado de assets e mensuração; por isso não oferece prova "
        "nem criação nesta versão.",
    ),
)

#: Meta Ads: **declarado, não implementado**, e a diferença está no manifesto.
#:
#: Ele existe aqui por uma razão concreta e presente: a tela precisa desenhar o
#: eixo de rede (Google | Meta) e precisa saber que o segundo nível do Meta se
#: chama CONJUNTO, e não "grupo de anúncios". Traduzir o vocabulário do Meta
#: para o do Google faria o operador procurar no painel do Meta uma palavra que
#: não existe lá.
#:
#: `capacidades=()` é a declaração de que nem ler é possível hoje — não há
#: credencial, não há adaptador, não há conta ligada. É o que impede a tela de
#: mostrar "0 campanhas" para o Meta, que afirmaria uma leitura que ninguém fez.
META = ManifestoDeCanal(
    plataforma=META_ADS,
    canal="META",
    rotulo="Meta Ads",
    hierarquia=(CAMPANHA, CONJUNTO, ANUNCIO, CRIATIVO),
    capacidades=(),
    indisponibilidades=(
        "não há credencial, adaptador nem conta ligada para o Meta. O eixo "
        "existe na navegação; o inventário dele não foi lido, e zero campanhas "
        "seria uma afirmação sobre uma leitura que ninguém fez.",
    ),
)

_MANIFESTOS: Dict[Tuple[str, str], ManifestoDeCanal] = {
    (m.plataforma, m.canal): m
    for m in (SEARCH, DISPLAY, DEMAND_GEN, PERFORMANCE_MAX, META)
}


def manifesto(plataforma: str, canal: Any) -> Optional[ManifestoDeCanal]:
    """O manifesto de um canal, ou `None` quando não há.

    O canal passa pela normalização do vocabulário (`PMAX` → `PERFORMANCE_MAX`,
    ADR-18) antes da busca: o apelido de tela nunca chega ao registro.
    """
    alvo = dom.canal_de_leitura(canal) or str(canal or "").strip().upper()
    return _MANIFESTOS.get((str(plataforma or "").strip().upper(), alvo))


def manifestos_de(plataforma: str) -> Tuple[ManifestoDeCanal, ...]:
    """Todos os canais de uma plataforma, em ordem estável."""
    alvo = str(plataforma or "").strip().upper()
    return tuple(m for (p, _), m in sorted(_MANIFESTOS.items())
                 if p == alvo)


def exigir_construtor(plataforma: str, canal: Any) -> ManifestoDeCanal:
    """O manifesto, e ele PRECISA saber criar. Levanta com a lista do que existe.

    ⚠️ **Esta não é a recusa autoritativa.** A porta de criação já recusa canal
    sem construtor no próprio engine (`volc_ads/subir.py:resolver_construtor`),
    e é lá que a decisão vale — nada sobe sem passar por ela.

    Esta função existe para as superfícies do HUB: ela permite recusar antes de
    montar o pedido, e permite à tela não oferecer o que será recusado. As duas
    dizem a mesma coisa por construção, e
    o teste de coerência compara o manifesto com
    o registro real do engine — duas verdades sobre o mesmo fato é o defeito,
    não a solução.
    """
    m = manifesto(plataforma, canal)
    if m is None:
        conhecidos = ", ".join(sorted({c for _, c in _MANIFESTOS}))
        raise ValueError(
            f"canal {canal!r} não existe em {plataforma!r}. Os canais "
            f"conhecidos são: {conhecidos}.")
    if not m.sabe_criar:
        porque = m.indisponibilidades[0] if m.indisponibilidades else (
            "este canal não tem construtor de campanha")
        sabem = ", ".join(sorted(x.rotulo for x in _MANIFESTOS.values()
                                 if x.sabe_criar))
        raise ValueError(
            f"{m.rotulo}: {porque} Hoje o VOLC O.S. sabe criar em: {sabem}.")
    return m


def exigir_provador(plataforma: str, canal: Any) -> ManifestoDeCanal:
    """Exige builder/prova; não implica permissão para criar remotamente."""
    m = manifesto(plataforma, canal)
    if m is None or not m.sabe_provar:
        sabem = ", ".join(
            sorted(x.rotulo for x in _MANIFESTOS.values() if x.sabe_provar)
        )
        raise ValueError(
            f"canal {canal!r} não possui porta de prova. Disponíveis: {sabem}."
        )
    return m
