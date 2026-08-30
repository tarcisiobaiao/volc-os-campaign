"""Marcação de URL — o contrato de rastreio, nativo e por canal.

## Por que este módulo existe

A receita mora no GAM e o custo mora no Google Ads. O que junta os dois é o
que chega na URL da landing page no momento do clique. Se um parâmetro falta,
o par não fecha, e o placement vira prejuízo fantasma — foi exatamente a falha
que a F05 mediu: R$ 223.713 de investimento classificados como prejuízo por
ausência de chave, e 74.595 placements na fila de negativação por engano.

## A decisão central: `final_url_suffix`, não concatenar na URL

O forge antigo montava a marcação concatenando na `final_url`:

    https://site/r/pagina/?utm_source=gads&utm_campaign={campaignid}

Três defeitos nisso, e todos aparecem em produção:

  1. **Quebra quando a URL já tem query string.** O código escolhia entre `?` e
     `&` na hora; qualquer URL com parâmetro próprio já entrava em risco.
  2. **Não alcança as outras URLs.** Sitelink, asset e anúncio têm cada um a sua
     `final_url`. Concatenar cobre uma; as outras saem sem marcação.
  3. **Vira parte do destino.** A URL final com parâmetro é o que a política
     compara com a página. Sufixo é aplicado pelo Google *no clique* e não
     participa dessa comparação.

`final_url_suffix` resolve os três de uma vez: é declarado UMA vez na campanha
e o Google o aplica a toda URL final servida por ela — anúncio, sitelink,
asset, todos. A `final_url` volta a ser o endereço limpo da página.

Existe em `customer`, `campaign`, `ad_group`, `ad` e `ad_group_criterion`.
Vence o mais específico. O forge declara na **campanha**: é onde a informação
de canal existe e onde o custo é agregado.

## O que a API NÃO protege — medido em 11/08/2026, validate_only na Crédito Up

    {lpurl}                    ❌ url_field_error.INVALID_TAG_IN_FINAL_URL_SUFFIX
    começar com '?' ou '&'     ❌ url_field_error.FINAL_URL_SUFFIX_MALFORMED
    espaço no nome do campo    ❌ string_format_error.ILLEGAL_CHARS
    utm_x={naoexiste}          ✅ PASSA

A última linha é a que importa. **A API aceita macro que não existe.** Um typo
em `{campaignid}` não dá erro em lugar nenhum: a campanha sobe, roda, gasta, e
a coluna chega vazia no join semanas depois. Por isso a validação de nome de
macro é local e obrigatória — a API não vai avisar.

Também medido: nenhum limite de tamanho até 4.000 caracteres no validate_only.
O teto real é o da URL **expandida** (macro vira valor no clique), e esse a API
não checa na validação. O limite aqui é nosso, conservador, com margem para a
expansão do `{placement}`, que é o mais longo de todos.

## O gclid não entra aqui

`customer.auto_tagging_enabled = True` na conta. Com auto-tagging o Google já
anexa `gclid` à URL final por conta própria. Declarar `{gclid}` no sufixo
duplicaria o parâmetro. O gclid continua sendo pré-requisito do upload de
conversão offline — ele só não vem por este caminho.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── registro de macros ──────────────────────────────────────────────────────
# As 26 aceitas pela API na v25, confirmadas uma a uma por validate_only em
# 11/08/2026. `{lpurl}` é a única recusada e por isso não está aqui.
#
# `canais` é conhecimento semântico, não restrição de API: a API aceita
# `{keyword}` numa campanha de Display sem reclamar — ela simplesmente chega
# vazia. Declarar o canal evita parâmetro morto na URL, que só gasta caractere
# e polui o relatório com coluna sempre vazia.

TODOS = frozenset({"SEARCH", "DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX", "VIDEO"})
CONTEUDO = frozenset({"DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX", "VIDEO"})
BUSCA = frozenset({"SEARCH", "PERFORMANCE_MAX"})


@dataclass(frozen=True)
class Macro:
    nome: str
    canais: frozenset[str]
    descricao: str
    # comprimento típico do valor expandido, para estimar a URL final
    expansao: int = 12


MACROS: dict[str, Macro] = {
    m.nome: m for m in (
        Macro("campaignid", TODOS, "id da campanha", 11),
        Macro("adgroupid", TODOS, "id do grupo de anúncios", 11),
        Macro("creative", TODOS, "id do anúncio", 12),
        Macro("targetid", TODOS, "id do critério que casou", 12),
        Macro("device", TODOS, "m | t | c", 1),
        Macro("devicemodel", TODOS, "marca e modelo do aparelho", 20),
        Macro("network", TODOS, "g | s | d | u | ytv | ytsp", 4),
        Macro("loc_physical_ms", TODOS, "id do local físico do usuário", 7),
        Macro("loc_interest_ms", TODOS, "id do local de interesse", 7),
        Macro("feeditemid", TODOS, "id do item de feed/extensão", 12),
        Macro("extensionid", TODOS, "id da extensão clicada", 12),
        Macro("campaign_name", TODOS, "nome da campanha", 60),
        Macro("adgroup_name", TODOS, "nome do grupo", 60),
        Macro("random", TODOS, "número aleatório de cache-busting", 20),
        Macro("gclid", TODOS, "id do clique — REDUNDANTE com auto-tagging", 90),
        Macro("keyword", BUSCA, "texto da keyword que casou", 40),
        Macro("matchtype", BUSCA, "e | p | b", 1),
        Macro("adposition", BUSCA, "posição do anúncio", 6),
        # TODOS, e não só CONTEUDO, de propósito. Em Search o `{placement}`
        # popula nos cliques vindos de PARCEIRO DE BUSCA — e a operação roda
        # com `target_search_network = True`. `{network}` diz apenas *se* foi
        # parceiro; `{placement}` diz **qual**, que é o que permite negativar.
        # Parceiro de busca é vetor conhecido de tráfego inválido (FG-CMP-004).
        # Em clique do google.com chega vazio, e isso é informação também.
        Macro("placement", TODOS, "domínio, app ou parceiro de busca de origem", 40),
        Macro("target", CONTEUDO, "categoria de placement", 30),
        Macro("merchant_id", CONTEUDO, "id do Merchant Center", 11),
        Macro("product_id", CONTEUDO, "id do produto", 20),
        Macro("store_code", CONTEUDO, "código da loja", 12),
        Macro("ifmobile:m", TODOS, "condicional: só em celular", 1),
        Macro("ifsearch:s", TODOS, "condicional: só na busca", 1),
        Macro("ifcontent:c", TODOS, "condicional: só no conteúdo", 1),
    )
}

# ── o contrato ──────────────────────────────────────────────────────────────
# Os sete primeiros são EXATAMENTE os que o runner n8n emitia. Mantidos com o
# mesmo nome de propósito: o parser do lado da receita já depende deles, e
# renomear quebraria o join que a F05 acabou de consertar.
#
# Os `vc_` são novos. Prefixo próprio para nunca colidir com utm_* nem com
# parâmetro de terceiro, e para serem greppáveis no log do publisher.

@dataclass(frozen=True)
class Parametro:
    chave: str
    valor: str            # literal, ou "{macro}"
    porque: str

    @property
    def macro(self) -> str | None:
        m = re.fullmatch(r"\{([^}]+)\}", self.valor)
        return m.group(1) if m else None


CONTRATO: tuple[Parametro, ...] = (
    # herdados do n8n — não renomear sem migrar o parser da receita
    Parametro("utm_source", "google", "origem fixa; separa de orgânico e social"),
    Parametro("utm_medium", "cpc", "mídia paga; o eixo de custo do painel de margem"),
    Parametro("utm_campaign", "{campaignid}", "A CHAVE do join custo × receita"),
    Parametro("utm_term", "{keyword}", "keyword real — alimenta o tribunal de termo"),
    Parametro("utm_content", "{adgroupid}", "grupo — onde o tCPA vive (9,4:1 vs campanha)"),
    Parametro("utm_device", "{device}", "corte por aparelho; RPM difere muito"),
    Parametro("utm_placement", "{placement}", "O placement. Sem ele a F05 se repete"),
    # novos
    Parametro("vc_creative", "{creative}", "id do anúncio — pré-requisito do RSA Darwin (F13)"),
    Parametro("vc_match", "{matchtype}", "e|p|b — separa broad de phrase no mesmo grupo"),
    Parametro("vc_network", "{network}", "g|s|d — isola parceiro de busca, que tem RPM próprio"),
    Parametro("vc_target", "{targetid}", "id do critério; casa com o corte de placement"),
    Parametro("vc_loc", "{loc_physical_ms}", "geo real do usuário — o eixo que geo.py descarta hoje"),
    Parametro("vc_ext", "{extensionid}", "qual sitelink foi clicado, sem bifurcar a URL"),
)

# Teto conservador. A API não impôs limite até 4.000 chars no validate_only,
# mas quem estoura é a URL EXPANDIDA: o Google recusa final URL acima de 2.048
# caracteres, e `{placement}` sozinho pode trazer 40+. Ver `estimar_expansao`.
MAX_SUFIXO = 1024
MAX_URL_EXPANDIDA = 2048

_CHAVE_OK = re.compile(r"^[A-Za-z0-9_.\-]+$")
_MACRO = re.compile(r"\{([^}]*)\}")
_PROIBIDAS = ("lpurl", "unescapedlpurl", "escapedlpurl", "ignore")


@dataclass
class Achado:
    severidade: str   # "erro" | "aviso"
    campo: str
    motivo: str


@dataclass
class Resultado:
    achados: list[Achado] = field(default_factory=list)

    @property
    def erros(self) -> list[Achado]:
        return [a for a in self.achados if a.severidade == "erro"]

    @property
    def ok(self) -> bool:
        return not self.erros

    def erro(self, campo, motivo):
        self.achados.append(Achado("erro", campo, motivo))

    def aviso(self, campo, motivo):
        self.achados.append(Achado("aviso", campo, motivo))

    def resumo(self) -> str:
        if not self.achados:
            return "sem achados"
        return "\n".join(f"  [{a.severidade}] {a.campo}: {a.motivo}" for a in self.achados)


def parametros(canal: str, *, incluir_gclid: bool = False,
               extras: dict[str, str] | None = None) -> list[Parametro]:
    """Os parâmetros que fazem sentido para `canal`, na ordem do contrato.

    Macro que não popula no canal é descartada em vez de ir vazia: parâmetro
    sempre vazio custa caractere na URL e cria coluna morta no relatório.
    """
    if canal not in TODOS:
        raise ValueError(f"canal {canal!r} fora de {sorted(TODOS)}")
    saida: list[Parametro] = []
    for p in CONTRATO:
        nome = p.macro
        if nome is None:
            saida.append(p)
            continue
        m = MACROS.get(nome)
        if m is None or canal not in m.canais:
            continue
        saida.append(p)
    if incluir_gclid:
        saida.append(Parametro("vc_gclid", "{gclid}",
                               "explícito — só quando auto-tagging estiver DESLIGADO"))
    for k, v in (extras or {}).items():
        saida.append(Parametro(k, v, "extra do brief"))
    return saida


def montar(canal: str, *, incluir_gclid: bool = False,
           extras: dict[str, str] | None = None) -> str:
    """O `final_url_suffix` pronto para a campanha. Nunca começa com ? ou &."""
    ps = parametros(canal, incluir_gclid=incluir_gclid, extras=extras)
    return "&".join(f"{p.chave}={p.valor}" for p in ps)


def estimar_expansao(sufixo: str, url_final: str = "") -> int:
    """Tamanho estimado da URL depois que o Google trocar macro por valor.

    O validate_only aprova sufixo de 4.000 caracteres porque valida a string
    crua. Quem recusa a URL expandida é o servidor de anúncio, no clique — e aí
    já é tarde. Esta estimativa é a única checagem possível antes de subir.
    """
    n = len(url_final) + (1 if url_final and "?" not in url_final else 0) + len(sufixo)
    for nome in _MACRO.findall(sufixo):
        m = MACROS.get(nome)
        n += (m.expansao if m else 20) - (len(nome) + 2)
    return n


def validar(sufixo: str, *, canal: str | None = None, url_final: str = "",
            auto_tagging: bool = True) -> Resultado:
    """Tudo que a API deixa passar e depois cobra caro.

    A ordem das checagens é deliberada: primeiro o que a API recusaria (para o
    erro sair local e barato), depois o que ela ACEITA e não deveria.
    """
    r = Resultado()
    if not sufixo:
        return r

    # ── o que a API também recusaria ──
    if sufixo[0] in "?&":
        r.erro("sufixo", "não pode começar com '?' nem '&' (FINAL_URL_SUFFIX_MALFORMED)")
    for nome in _MACRO.findall(sufixo):
        if nome.split(":")[0].lower() in _PROIBIDAS:
            r.erro(f"{{{nome}}}", "tag proibida em final_url_suffix (INVALID_TAG_IN_FINAL_URL_SUFFIX)")

    # ── o que a API ACEITA e é defeito ──
    vistas: set[str] = set()
    for parte in sufixo.split("&"):
        if not parte:
            r.aviso("sufixo", "'&' duplicado ou sobrando")
            continue
        if "=" not in parte:
            r.erro(parte[:40], "parâmetro sem '='")
            continue
        chave, _, valor = parte.partition("=")
        if not _CHAVE_OK.match(chave):
            r.erro(chave[:40], "caractere inválido no nome do parâmetro (ILLEGAL_CHARS)")
        if chave in vistas:
            r.erro(chave, "parâmetro duplicado — o último vence e o outro some sem aviso")
        vistas.add(chave)
        if not valor:
            r.aviso(chave, "valor vazio")

    for nome in _MACRO.findall(sufixo):
        if nome.split(":")[0].lower() in _PROIBIDAS:
            continue
        m = MACROS.get(nome)
        if m is None:
            # A checagem que só existe aqui. A API aprova isto sem piscar.
            r.erro(f"{{{nome}}}", "macro inexistente — a API ACEITA e a coluna "
                                  "chega vazia semanas depois")
            continue
        if canal and canal not in m.canais:
            r.aviso(f"{{{nome}}}", f"não popula em {canal}; chega vazia "
                                   f"(vale em {', '.join(sorted(m.canais))})")
        if nome == "gclid" and auto_tagging:
            r.erro("{gclid}", "auto-tagging está ligado: o Google já anexa gclid; "
                              "declarar aqui duplica o parâmetro")

    # ── tamanho ──
    if len(sufixo) > MAX_SUFIXO:
        r.erro("sufixo", f"{len(sufixo)} chars > teto interno de {MAX_SUFIXO}")
    exp = estimar_expansao(sufixo, url_final)
    if exp > MAX_URL_EXPANDIDA:
        r.erro("sufixo", f"URL expandida estimada em {exp} chars > {MAX_URL_EXPANDIDA}")
    elif exp > MAX_URL_EXPANDIDA * 0.75:
        r.aviso("sufixo", f"URL expandida estimada em {exp} chars — perto do teto "
                          f"de {MAX_URL_EXPANDIDA}")
    return r


def analisar(sufixo: str) -> dict[str, str]:
    """Lê de volta o que uma campanha tem. Round-trip com `montar()`.

    Serve ao diagnóstico: comparar o que está na conta com o que o contrato
    manda, e apontar a diferença — sem isso a marcação apodrece em silêncio,
    que é exatamente como a F05 nasceu.
    """
    out: dict[str, str] = {}
    for parte in sufixo.split("&"):
        if "=" in parte:
            k, _, v = parte.partition("=")
            out[k] = v
    return out


def divergencia(sufixo_atual: str, canal: str, **kw) -> dict[str, tuple[str | None, str | None]]:
    """`{chave: (atual, esperado)}` só onde os dois discordam."""
    atual = analisar(sufixo_atual)
    esperado = analisar(montar(canal, **kw))
    saida = {}
    for k in sorted(set(atual) | set(esperado)):
        a, e = atual.get(k), esperado.get(k)
        if a != e:
            saida[k] = (a, e)
    return saida
