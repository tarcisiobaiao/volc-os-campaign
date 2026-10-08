from __future__ import annotations
from datetime import date
import re
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class PageRole(str, Enum):
    LP = "LP"
    PRESELL = "PRESELL"
    SOLUTION = "SOLUTION"


_ROLE_PRESELL_RE = re.compile(r"-pr\d*$")
_ROLE_SOLUTION_RE = re.compile(r"-p\d+$")


def derive_role(slug: str) -> PageRole:
    """Pure slug->role. `-pr` -> PRESELL, `-p<N>` -> SOLUTION, else LP.
    PRESELL is checked first so `-pr` never matches the numeric rule."""
    s = slug.strip().rstrip("/")
    if _ROLE_PRESELL_RE.search(s):
        return PageRole.PRESELL
    if _ROLE_SOLUTION_RE.search(s):
        return PageRole.SOLUTION
    return PageRole.LP


class Route(BaseModel):
    placement: str
    kind: str
    target: str
    anchor: str = ""
    reason: str = ""


class EditorialLink(BaseModel):
    target: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class EditorialIntent(BaseModel):
    reader_question: str = Field(min_length=1)
    useful_delivery: str = Field(min_length=1)
    cta_label: str = Field(min_length=1)
    links: list[EditorialLink] = Field(default_factory=list)


def _url_normalizada(url: str) -> str:
    """Forma canônica para comparar duas URLs: esquema e host em minúsculas,
    sem barra final. O CAMINHO preserva maiúsculas de propósito (há servidor
    que diferencia), então a comparação continua estrita onde precisa ser."""
    from urllib.parse import urlparse
    partes = urlparse((url or "").strip())
    consulta = f"?{partes.query}" if partes.query else ""
    return f"{partes.scheme.lower()}://{partes.netloc.lower()}{partes.path.rstrip('/')}{consulta}"


def resolve_route(route: Route, *, domain: str, post_type: str,
                  authorized_external: list[str] | None = None) -> str:
    """Resolve uma Route no href absoluto, aplicando a LEI DO MESMO DOMÍNIO.

    `authorized_external` são as URLs EXTERNAS que a PESQUISA desta página
    trouxe e o motor já escolheu (ver `steps.build_official_links`). Não é
    lista de domínios por instalação: é a evidência daquela página, URL a URL.
    Sem evidência não há link externo -- falha FECHADO por ausência de prova,
    nunca por o host estar fora de uma lista.

    Por que URL exata e não host: o risco real não é o host errado, é o redator
    inventar um caminho plausível num host legítimo ("gov.br/beneficio-liberado",
    "ifood.com.br/cadastro-vip"). Comparar a URL inteira mata os dois casos."""
    kind = route.kind
    target = route.target.strip()
    if kind == "funnel":
        slug = target.strip("/")
        if not slug:
            raise ValueError("empty funnel target (would produce a bare dead /rec link)")
        href = f"{domain.rstrip('/')}/{post_type}/{slug}"
        if "//" in href.split("://", 1)[-1]:
            raise ValueError(f"double slash in resolved href: {href}")
        return href
    if kind == "cross_funnel":
        # cross_funnel is a REAL, absolute same-domain URL picked from the site
        # sitemap -- NEVER reconstructed from a slug, so an invented page is
        # impossible. It must already be a full same-domain URL.
        from urllib.parse import urlparse
        if not target.startswith(("http://", "https://")):
            raise ValueError(f"cross_funnel target must be an absolute URL: {target}")
        host = urlparse(target).netloc.lower()
        dhost = urlparse(domain).netloc.lower()
        if not (host == dhost or host.endswith("." + dhost) or dhost.endswith("." + host)):
            raise ValueError(f"cross_funnel target not same-domain: {target}")
        return target
    if kind == "external_official":
        if not target.startswith("https://"):
            raise ValueError(f"canal oficial precisa ser uma URL https absoluta: {target}")
        autorizadas = {_url_normalizada(u) for u in (authorized_external or [])}
        if _url_normalizada(target) not in autorizadas:
            raise ValueError(
                f"canal oficial sem lastro na pesquisa desta página: {target}. "
                "Só entra URL que a busca devolveu e o motor verificou.")
        return target
    raise ValueError(f"unknown route kind: {kind}")


# ---------------------------------------------------------------------------
# A JORNADA DO LEITOR (07/10/2026). Contrato OPCIONAL e aditivo, irmão do
# `editorial`: o `editorial` diz o que a página entrega e para onde ela liga; a
# `jornada` diz EM QUE PONTO do caminho o leitor está — o que ele já resolveu,
# qual a próxima dúvida ainda aberta, quando a tarefa acaba e se a saída para a
# fonte oficial ali é boa ou prematura.
#
# ⚠️ Fica FORA do `EditorialIntent` de propósito: `editorial.model_dump()` vai
# cru para os prompts do ramo antigo, cujo ouro é byte a byte. Um campo novo lá
# dentro mudaria o prompt de todo card que já tem `editorial`.
#
# Toda referência entre páginas usa `duvida_id`, nunca slug: o slug ganha
# sufixo de posição no backend e na ponte; a dúvida não muda de nome.
# ---------------------------------------------------------------------------

#: De onde o leitor chega. Vocabulário fechado: canal, não pessoa — o contrato
#: não carrega estado pessoal nem identificador de sessão.
CANAIS_DE_ENTRADA: tuple[str, ...] = (
    "paid_search", "organic_search", "discover", "social", "display", "direct",
)
#: Canais de tráfego FRIO (sem tarefa declarada na busca). Paid Search de alta
#: intenção e estes não recebem a mesma promessa por padrão.
CANAIS_FRIOS: frozenset[str] = frozenset({"discover", "social", "display"})

Canal = Literal["paid_search", "organic_search", "discover", "social", "display", "direct"]
ClassificacaoDeSaida = Literal["boa", "prematura", "nao_aplicavel"]
NaturezaDoDado = Literal["hipotese", "simulacao", "observacao_real"]

#: O que uma página entrega de útil. Toda página com jornada declara ao menos
#: uma; página que só recircula tráfego não tem o que pôr aqui.
ENTREGAS: tuple[str, ...] = (
    "resposta_direta", "passo_a_passo", "comparacao", "exemplo", "checklist",
    "calculo", "tabela", "fonte_oficial_explicada", "ferramenta",
    "decisao_pratica", "proximo_passo_concreto",
)
Entrega = Literal[
    "resposta_direta", "passo_a_passo", "comparacao", "exemplo", "checklist",
    "calculo", "tabela", "fonte_oficial_explicada", "ferramenta",
    "decisao_pratica", "proximo_passo_concreto",
]


def canon_rotulo(valor: object) -> object:
    """Variação COSMÉTICA de um valor de vocabulário fechado: caixa, acento,
    espaço e hífen ("Observação real" -> "observacao_real", "paid-search" ->
    "paid_search"). Não traduz sinônimo: alias semântico é decisão do backend,
    logo depois do arquiteto. Valor fora do vocabulário sai canonizado e o
    schema o recusa com o nome do campo."""
    if not isinstance(valor, str):
        return valor
    texto = _sem_acento(valor).strip().lower()
    return re.sub(r"[\s\-]+", "_", texto)


_MARCAS_DE_NAO_OBSERVACAO = ("simulacao", "simulation", "simulad", "mirofish",
                             "hipotese", "hypothesis")


def fonte_nao_observada(fonte: str) -> bool:
    """A guarda ÚNICA de "isto não é dado observado". Vale para a evidência da
    jornada e para a leitura do contrato de medição: "MiroFish", "simulação:x",
    " SIMULACAO : x" e "hipótese" caem aqui com qualquer caixa, acento ou
    espaço."""
    bruto = re.sub(r"\s+", "", _sem_acento(fonte or "").lower())
    return any(m in bruto for m in _MARCAS_DE_NAO_OBSERVACAO)


class EvidenciaDaJornada(BaseModel):
    """Uma premissa do desenho, com a NATUREZA dita: hipótese do arquiteto,
    simulação (ex.: MiroFish) ou observação real. Lista vazia é ausência
    explícita de evidência — nunca é preenchida por suposição.

    Observação real exige fonte verificável, data de coleta e um identificador
    (relatório, consulta, export) que alguém consiga reabrir."""
    natureza: NaturezaDoDado
    afirmacao: str = Field(min_length=1)
    fonte: str = ""
    confianca: Literal["baixa", "media", "alta"] | None = None
    coletado_em: date | None = None
    referencia: str = ""

    @field_validator("natureza", "confianca", mode="before")
    @classmethod
    def _rotulo(cls, value: object) -> object:
        return canon_rotulo(value)

    @model_validator(mode="after")
    def _fonte_coerente_com_a_natureza(self) -> "EvidenciaDaJornada":
        if self.natureza != "hipotese" and not self.fonte.strip():
            raise ValueError(f"evidência de natureza '{self.natureza}' sem fonte")
        if self.natureza == "simulacao" and not self.fonte.startswith("simulacao:"):
            raise ValueError("simulação precisa de fonte 'simulacao:<origem>'")
        if self.natureza == "observacao_real":
            if fonte_nao_observada(self.fonte):
                raise ValueError("observação real não pode vir de simulação nem de hipótese")
            if self.coletado_em is None or not self.referencia.strip():
                raise ValueError("observação real exige coletado_em e referencia verificável")
        return self


class SaidaOficialPrevista(BaseModel):
    """A saída para a fonte oficial NESTA página — e a AUTORIDADE sobre a rota
    oficial: `esperada=False` não ganha link oficial obrigatório; `boa` vem
    primeiro; `prematura` vem depois do CTA da próxima dúvida. `classificacao`
    é o que o arquiteto declarou; a régua (`jornada.classificar_saida_oficial`)
    recalcula e a divergência vira achado."""
    esperada: bool = False
    classificacao: ClassificacaoDeSaida = "nao_aplicavel"
    condicao: str = ""
    justificativa: str = ""

    @field_validator("classificacao", mode="before")
    @classmethod
    def _rotulo(cls, value: object) -> object:
        return canon_rotulo(value)


class MonetizacaoDaPagina(BaseModel):
    """O papel do anúncio no desenho da página e o que ele não pode fazer."""
    papel: Literal["nenhum", "secundario", "principal"] = "secundario"
    restricoes: list[str] = []

    @field_validator("papel", mode="before")
    @classmethod
    def _rotulo(cls, value: object) -> object:
        return canon_rotulo(value)


class ValorDaPagina(BaseModel):
    """Por que a página existe. Sem isto declarado, ela não vai à redação."""
    problema: str = ""
    informacao_nova: str = ""
    evidencia: str = ""
    capacidade_do_leitor: str = ""        # o que ele consegue FAZER depois
    por_que_nao_fundir: str = ""
    entregas: list[Entrega] = []

    @field_validator("entregas", mode="before")
    @classmethod
    def _rotulos(cls, value: object) -> object:
        return [canon_rotulo(v) for v in value] if isinstance(value, list) else value


class BlocoVisual(BaseModel):
    """Um item do `visual_plan` declarado já pelo arquiteto, no MESMO
    vocabulário do briefing (`validators.briefing_contract.INTENCOES_VISUAIS`).
    O revisor de esqueleto confere padrão × intenção × entregas da página."""
    secao: str = Field(min_length=1)
    intencao: str = Field(min_length=1)
    padrao: str = Field(min_length=1)
    funcao: str = ""                      # a função editorial, em uma frase
    posicao: Literal["apos_resposta", "secao", "fechamento"] = "secao"

    @field_validator("intencao", "padrao", "posicao", mode="before")
    @classmethod
    def _rotulo(cls, value: object) -> object:
        return canon_rotulo(value)


class AtivoInterativo(BaseModel):
    """Um widget pedido pelo arquiteto. O arquiteto declara a NECESSIDADE
    semântica da prova — `rule_source_fact_id` (o requisito factual da página
    que prova a regra) e, se o ativo mostra valor em reais,
    `current_value_source_fact_id` — e o dossiê vincula cada uma à melhor fonte
    citada e verificada. A URL da prova não é escolhida de antemão.

    `fonte_da_regra` é LEGADO (cards anteriores ao contrato): sem os ids, a URL
    tem de estar entre as fontes verificadas, como antes."""
    pergunta: str = Field(min_length=1)
    entradas: list[str] = []
    logica: str = ""
    resultado: str = ""
    rule_source_fact_id: str = ""
    current_value_source_fact_id: str = ""
    fonte_da_regra: str = ""
    fallback_sem_js: str = ""
    acessibilidade: str = ""
    evento_de_medicao: str = ""
    custo_estimado_usd: float | None = None

    @field_validator("rule_source_fact_id", "current_value_source_fact_id", mode="before")
    @classmethod
    def _requisito(cls, value: object) -> object:
        return canon_rotulo(value) if value else ""


class FatorDaDerivacao(BaseModel):
    requisito: str = Field(min_length=1)
    unidade: str = Field(min_length=1)       # núcleo da unidade esperado ("salarios", "r$")


class DerivacaoDeclarada(BaseModel):
    """Um valor que o CÓDIGO calcula a partir de dois fatos verificados. Só a
    operação permitida; fórmula livre não existe."""
    operacao: Literal["multiplicacao"]
    fatores: list[FatorDaDerivacao] = Field(min_length=2, max_length=2)
    unidade_resultado: str = Field(min_length=1)


class RequisitoFactual(BaseModel):
    """O que a promessa da página EXIGE provar antes de alguém escrever (ex.:
    `renda.limite_per_capita`, aceito como `numero` ou `condicao`). O dossiê
    só libera a página quando cada requisito crítico tem fato verificado."""
    id: str = Field(min_length=1, pattern=r"^[a-z0-9_.]+$")
    descricao: str = Field(min_length=1)
    tipos: list[str] = ["numero", "prazo", "data", "mudanca", "condicao", "orgao",
                        "fonte_legal", "processo"]
    critico: bool = True
    derivacao: DerivacaoDeclarada | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _rotulo(cls, value: object) -> object:
        return canon_rotulo(value) if isinstance(value, str) else value


def _ids(value: object) -> object:
    return [canon_rotulo(v) for v in value] if isinstance(value, list) else value


class JornadaDaPagina(BaseModel):
    duvida_id: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    pergunta_principal: str = Field(min_length=1)
    trabalho_do_leitor: str = ""
    # A promessa da primeira dobra. Vazio é permitido no MODELO para que o
    # revisor de esqueleto reprove com o nome certo (`lp_so_roteia`,
    # `resposta_imediata_ausente`) em vez de um erro de schema.
    resposta_imediata: str = ""
    coortes_de_entrada: list[Canal] = []
    # O que o leitor resolveu no caminho PLANEJADO pelo arquiteto. É o
    # "possivelmente resolvido": quem entra direto não passou por ele. O que é
    # CERTO em todos os caminhos o motor calcula (`jornada.estado_do_leitor`).
    ja_resolvido: list[str] = []
    proxima_duvida: str = ""
    condicao_terminal: str = ""
    entrada_direta: Literal["autocontida", "depende_de_contexto"] = "autocontida"
    saida_oficial: SaidaOficialPrevista = SaidaOficialPrevista()
    monetizacao: MonetizacaoDaPagina = MonetizacaoDaPagina()
    # duvida_id do destino -> por que este link de volta tem ganho real (ex.:
    # "quem entrou direto pela busca ainda não fez a conta"). Sem isto, um
    # link que fecha ciclo ou reoferece dúvida resolvida é falha estrutural.
    retornos_justificados: dict[str, str] = {}
    hipotese_de_medicao: str = ""
    evidencias: list[EvidenciaDaJornada] = []
    valor: ValorDaPagina | None = None
    plano_visual: list[BlocoVisual] = []
    ativos: list[AtivoInterativo] = []
    requisitos: list[RequisitoFactual] = []

    @field_validator("duvida_id", "proxima_duvida", "entrada_direta", mode="before")
    @classmethod
    def _rotulo(cls, value: object) -> object:
        return canon_rotulo(value)

    @field_validator("ja_resolvido", "coortes_de_entrada", mode="before")
    @classmethod
    def _rotulos(cls, value: object) -> object:
        return _ids(value)

    @field_validator("retornos_justificados", mode="before")
    @classmethod
    def _chaves(cls, value: object) -> object:
        if isinstance(value, dict):
            return {canon_rotulo(k): v for k, v in value.items()}
        return value


class CoorteDeEntrada(BaseModel):
    canal: Canal
    entrada: str = Field(min_length=1)          # duvida_id da página de entrada
    promessa: str = Field(min_length=1)
    profundidade: Literal["resposta_direta", "guiada"] = "guiada"
    proximo_passo: str = ""                     # duvida_id ("" = resolve ali)

    @field_validator("canal", "entrada", "profundidade", "proximo_passo", mode="before")
    @classmethod
    def _rotulo(cls, value: object) -> object:
        return canon_rotulo(value)


class JornadaDoFunil(BaseModel):
    intencao_principal: str = Field(min_length=1)
    solucao_principal: str = ""                 # duvida_id
    checkpoint: str = ""                        # duvida_id
    coortes: list[CoorteDeEntrada] = []
    hipotese_de_medicao: str = ""
    evidencias: list[EvidenciaDaJornada] = []
    # Abrangência geográfica do conteúdo (siglas de UF). Vazio = nacional: fonte
    # regional não vale como prova universal de regra.
    ufs: list[str] = []

    @field_validator("ufs", mode="before")
    @classmethod
    def _ufs(cls, value: object) -> object:
        return [str(u).strip().lower() for u in (value or []) if str(u).strip()]


    @field_validator("solucao_principal", "checkpoint", mode="before")
    @classmethod
    def _rotulo(cls, value: object) -> object:
        return canon_rotulo(value)


class PageTypeSpec(BaseModel):
    role: PageRole
    allowed_targets: list[str]
    required_targets: list[str]
    forbidden_targets: list[str]
    cta_min: int
    cta_max: int
    requires_external_official: bool = False
    requires_cross_funnel_exit: bool = False
    distinct_targets: bool = False
    anchor_congruent: bool = True


class Page(BaseModel):
    page_number: int
    page_type: str
    h1_title: str
    slug: str
    emotional_objective: str = ""
    main_content_structure: list[str] = []
    hook_to_next_page: str = ""
    next_page_slug: str = ""
    target_keywords: list[str] = []
    role: PageRole | None = None
    ordinal: int = 0
    routes: list[Route] = []
    # None preserves old checkpoints; new plans carry an explicit reader contract.
    editorial: EditorialIntent | None = None
    # A FORMA DA PERGUNTA que esta página responde, no vocabulário do eixo
    # `engajamento` do motor de pautas: condicional | sequencial | comparativo |
    # diagnostico | dado_unico. Vazio = desconhecido (o motor não opinou), e aí
    # o motor aplica inferência semântica determinística sobre H1/estrutura.
    #
    # Este é o campo de ligação da F06 (ponte Pautador -> Runner): é a menor
    # superfície possível entre os dois projetos -- uma string por página, sem
    # acoplar modelos. Ver `ENGAJAMENTO_PARA_ARQUETIPO` em pipeline/steps.py.
    engajamento: str = ""
    # Ver `JornadaDaPagina`. None = card anterior à jornada (roteamento e
    # prompts exatamente como antes).
    jornada: JornadaDaPagina | None = None


def effective_role(page: Page) -> PageRole:
    return page.role or derive_role(page.slug)


def role_matches_slug(page: Page) -> bool:
    return page.role is None or page.role == derive_role(page.slug)


# ---------------------------------------------------------------------------
# CONTEXTOS DO FUNIL que vêm do backend no `funnel_architecture` (contrato
# entre as trilhas, 30/09). Todos OPCIONAIS e aditivos: um card antigo não os
# tem, e ausência é dita como ausência — nunca preenchida por suposição.
# ---------------------------------------------------------------------------

class TermoDeBusca(BaseModel):
    termo: str = Field(min_length=1)
    impressoes: int = Field(ge=0)
    cliques: int = Field(ge=0)
    custo: float | None = None


class JanelaDeColeta(BaseModel):
    inicio: date
    fim: date
    fuso: str = "America/Sao_Paulo"

    @model_validator(mode="after")
    def _fim_depois_do_inicio(self) -> "JanelaDeColeta":
        if self.fim < self.inicio:
            raise ValueError("janela com fim antes do início")
        return self


_FONTE_DE_TERMOS_RE = re.compile(r"^(search_term_view|arquivo:[0-9a-f]{64})$")


class TermosDeBusca(BaseModel):
    """O que o leitor digitou, em TRÊS estados — o mesmo JSON dos dois lados.

    `presente`         -> consulta feita na janela, com termos.
    `vazio_confirmado` -> consulta feita na janela, zero termos (é informação).
    `ausente`          -> ninguém coletou (funil novo, sem credencial...). NUNCA
                          vira lista: `termos` tem de vir vazio.
    """
    estado: Literal["presente", "vazio_confirmado", "ausente"]
    janela: JanelaDeColeta | None = None
    coletado_em: str | None = None
    fonte: str | None = None
    termos: list[TermoDeBusca] = []
    motivo_ausencia: str | None = None

    @model_validator(mode="after")
    def _coerente_com_o_estado(self) -> "TermosDeBusca":
        if self.estado in ("ausente", "vazio_confirmado") and self.termos:
            raise ValueError(f"estado '{self.estado}' não pode trazer termos")
        if self.estado == "presente" and not self.termos:
            raise ValueError("estado 'presente' sem nenhum termo")
        if self.estado != "ausente":
            faltando = [nome for nome in ("janela", "coletado_em", "fonte")
                        if not getattr(self, nome)]
            if faltando:
                raise ValueError(f"estado '{self.estado}' sem {', '.join(faltando)}")
            if not _FONTE_DE_TERMOS_RE.match(self.fonte or ""):
                raise ValueError("fonte deve ser 'search_term_view' ou 'arquivo:<sha256>'")
        return self


class Tensao(BaseModel):
    frase: str = Field(min_length=1)
    evidencia: str = ""


class ContextoDeLeitura(BaseModel):
    """Perguntas reais dos leitores (PAA) e a tensão medida na validação.

    É DADO, não instrução: o briefing trata a tensão como hipótese com a
    evidência que a sustenta."""
    perguntas_paa: list[str] = []
    tensao: Tensao | None = None

    @field_validator("perguntas_paa", mode="after")
    @classmethod
    def _sem_vazias(cls, value: list[str]) -> list[str]:
        return [p.strip() for p in value if isinstance(p, str) and p.strip()]


class ContextoDeAnuncio(BaseModel):
    """A promessa do anúncio que traz o leitor à LP (títulos e descrições)."""
    estado: Literal["presente", "ausente"]
    titulos: list[str] = []
    descricoes: list[str] = []
    fonte: str = ""
    motivo_ausencia: str | None = None

    @model_validator(mode="after")
    def _coerente_com_o_estado(self) -> "ContextoDeAnuncio":
        if self.estado == "presente" and not (self.titulos or self.descricoes):
            raise ValueError("anúncio 'presente' sem título nem descrição")
        if self.estado == "ausente" and (self.titulos or self.descricoes):
            raise ValueError("anúncio 'ausente' não pode trazer texto")
        return self


class FunnelPlan(BaseModel):
    avatar_summary: str = ""
    tone_voice: str = ""
    total_pages: int = 0
    pages: list[Page] = []
    # Ramo editorial novo pedido pela ARQUITETURA do card (o perfil do run
    # também pode ligar; ver `pipeline.editorial_v2_do_run`).
    editorial_v2: bool = False
    contexto_de_leitura: ContextoDeLeitura | None = None
    contexto_de_busca: TermosDeBusca | None = None
    contexto_de_anuncio: ContextoDeAnuncio | None = None
    jornada: JornadaDoFunil | None = None


# ---------------------------------------------------------------------------
# FATOS TIPADOS — o vocabulário fechado do contrato entre as trilhas (30/09).
#
# O tipo diz o que o fato AFIRMA, não de que campo da pesquisa ele veio. Antes
# desta reforma a ponte do backend deduzia o tipo pelo campo de origem
# (`dados_validados` -> "afirmacao", `fatos_verificados` -> "numero") e o motor
# jogava fora qualquer `tipo` que a pesquisa mandasse. No run Senac isso custou
# 3 de 7 fatos na copy e transformou o número de um decreto em "numero".
#
# `contexto` sustenta relevância e nomeação; NUNCA sustenta número, prazo ou
# condição. A mesma lista vale no backend (`volc_ads`): mudar aqui exige mudar
# lá, e o teste de contrato da integração compara as duas.
# ---------------------------------------------------------------------------
TIPOS_DE_FATO: tuple[str, ...] = (
    "numero", "prazo", "data", "mudanca", "condicao",
    "orgao", "fonte_legal", "processo", "contexto",
)

#: Unidades da federação aceitas em `escopo = "regional:UF"`.
UFS: frozenset[str] = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
})


def _sem_acento(texto: str) -> str:
    import unicodedata
    normal = unicodedata.normalize("NFKD", texto)
    return "".join(ch for ch in normal if not unicodedata.combining(ch))


def canon_tipo_de_fato(valor: object) -> str | None:
    """Grafia canônica de um tipo: minúsculas, sem acento, `_` no lugar de
    espaço/hífen ("Fonte legal" -> "fonte_legal", "Condição" -> "condicao").

    NÃO decide se o tipo é válido: um valor fora do vocabulário sai canonizado
    e intacto, para o validador `research_facts_contract` recusá-lo com o nome
    certo. Trocar por None aqui esconderia o erro da pesquisa."""
    if valor is None:
        return None
    texto = _sem_acento(str(valor)).strip().lower()
    texto = re.sub(r"[\s\-]+", "_", texto)
    return texto or None


def canon_escopo(valor: object) -> str | None:
    """`nacional` | `unidade` | `regional:UF` (UF em maiúsculas). Fora disso,
    sai minúsculo e intacto para o validador recusar."""
    if valor is None:
        return None
    texto = _sem_acento(str(valor)).strip().lower()
    if not texto:
        return None
    texto = re.sub(r"\s*:\s*", ":", texto)
    if texto.startswith("regional:"):
        uf = texto.split(":", 1)[1].strip()
        return f"regional:{uf.upper()}"
    return texto


def canon_citavel(valor: object) -> bool | None:
    """Booleano tolerante ("sim"/"não" também). Desconhecido = não declarado."""
    if isinstance(valor, bool) or valor is None:
        return valor
    texto = _sem_acento(str(valor)).strip().lower()
    if texto in {"sim", "true", "1", "yes", "verdadeiro"}:
        return True
    if texto in {"nao", "false", "0", "no", "falso"}:
        return False
    return None


def escopo_valido(escopo: str | None) -> bool:
    if escopo is None:
        return True
    if escopo in ("nacional", "unidade"):
        return True
    return escopo.startswith("regional:") and escopo.split(":", 1)[1] in UFS


class VerifiedFact(BaseModel):
    """One publication-grade fact, with enough provenance to audit it.

    ``dados_validados`` remains available on :class:`ResearchFacts` for
    backwards-compatible qualitative notes.  Numbers, deadlines and legal
    claims, however, are only publishable when represented by this stricter
    shape and later accepted by the research/content gates.

    `tipo`, `escopo` e `citavel` são ADITIVOS e opcionais: um `state.json`
    anterior à reforma não os tem e continua carregando (None = não declarado;
    a ponte aplica a regra de legado). O vocabulário é conferido pelo validador
    `research_facts_contract`, não aqui — ver `canon_tipo_de_fato`.
    """

    valor: str = Field(min_length=1)
    unidade: str = Field(min_length=1)
    fonte_primaria: str = Field(min_length=1)
    dispositivo: str = Field(min_length=1)
    vigente_desde: date
    verificado_em: date
    tipo: str | None = None
    escopo: str | None = None
    citavel: bool | None = None

    @field_validator("fonte_primaria")
    @classmethod
    def fonte_must_be_absolute_https(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("https://"):
            raise ValueError("fonte_primaria deve ser uma URL HTTPS absoluta")
        return value

    @field_validator("tipo", mode="before")
    @classmethod
    def _tipo_canonico(cls, value: object) -> str | None:
        return canon_tipo_de_fato(value)

    @field_validator("escopo", mode="before")
    @classmethod
    def _escopo_canonico(cls, value: object) -> str | None:
        return canon_escopo(value)

    @field_validator("citavel", mode="before")
    @classmethod
    def _citavel_tolerante(cls, value: object) -> bool | None:
        return canon_citavel(value)


class ResearchFacts(BaseModel):
    resumo: str = ""
    dados_validados: list[dict] = []
    fatos_verificados: list[VerifiedFact] = []
    passo_a_passo: list[str] = []
    fontes: list[str] = []
    # Filled by the engine, never trusted from prose.  When a live verifier is
    # wired, only URLs that actually resolved are copied here.  Critical-claim
    # validation trusts this set rather than the model-authored ``fontes``.
    fontes_resolvidas: list[str] = []
    sparse: bool = False

    @field_validator("dados_validados", mode="after")
    @classmethod
    def _dados_tipados_canonicos(cls, value: list[dict]) -> list[dict]:
        """Mesma grafia canônica dos fatos verificados, só onde a chave existe:
        um dado antigo sem `tipo` continua sem `tipo` (a ponte decide)."""
        saida: list[dict] = []
        for item in value:
            if isinstance(item, dict):
                item = dict(item)
                if "tipo" in item:
                    item["tipo"] = canon_tipo_de_fato(item["tipo"])
                if "escopo" in item:
                    item["escopo"] = canon_escopo(item["escopo"])
                if "citavel" in item:
                    item["citavel"] = canon_citavel(item["citavel"])
            saida.append(item)
        return saida


class PageDraft(BaseModel):
    page_number: int
    page_type: str
    format: str            # "markers" (P1) | "gutenberg" (P2-P5)
    content: str
    word_count: int = 0


class Verdict(BaseModel):
    approved: bool = False
    blocking: bool = False
    scores: dict[str, int] = {}
    feedback: list[str] = []


# Fail-closed gate criteria: a judge score < 7 on any of these FAILS the page
# (skips build+publish). proof_and_authority was DEMOTED out of this set
# ("cirurgico"/trust-Gemini smoke decision): we trust the Gemini web-search
# research, so weak/thin proof is now advisory feedback, never a hard block.
# Only the arbitrage + legal invariants stay existential. See
# `_existential_criteria_for` (SOLUTION also drops single_destination) and
# judge.jinja's REGRA_DE_APROVACAO, which are kept consistent with this tuple.
EXISTENTIAL_CRITERIA: tuple[str, ...] = (
    "single_destination", "compliance", "cta_discipline",
)


class Issue(BaseModel):
    code: str
    message: str


class StepStatus(str, Enum):
    OK = "OK"
    RETRIED = "RETRIED"
    FALLBACK = "FALLBACK"
    FAILED = "FAILED"
    # Non-essential step that failed/errored and was deliberately skipped
    # rather than failing the page (e.g. image generation -- see
    # steps.py's step_image). Distinct from FAILED so build/publish gates
    # (`_page_blocked` in pipeline.py) that key on FAILED never trip on it.
    SKIPPED = "SKIPPED"


class StepResult(BaseModel):
    step: str
    status: StepStatus
    model_used: str = ""
    # O modelo que a config PEDIU. Com `model_used` diferente, o status é
    # FALLBACK — e os dois nomes ficam lado a lado no estado e no relatório.
    model_requested: str = ""
    # Procedência da última tentativa: modo de autenticação (`api_key` |
    # `chatgpt_plan`), esforço de raciocínio pedido e id da resposta.
    auth_mode: str = ""
    reasoning_effort: str = ""
    response_id: str = ""
    attempts: int = 0
    issues: list[Issue] = []
    artifact_path: str | None = None
    # --- telemetry (summed across attempts) ---
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


#: Campos de PROCEDÊNCIA de uma chamada (quem pediu o quê, a quem, como).
CAMPOS_DE_PROCEDENCIA = ("model_requested", "auth_mode", "reasoning_effort", "response_id")


def procedencia(res: "StepResult | None") -> dict[str, str]:
    """A procedência de um `StepResult` do runner, para quem monta OUTRO
    `StepResult` a partir dele (widget, engajamento, revisor) não a perder."""
    if res is None:
        return {}
    return {c: getattr(res, c) for c in CAMPOS_DE_PROCEDENCIA if getattr(res, c, "")}


class AdSlot(BaseModel):
    slot_id: str
    page_role: PageRole
    placement: str
    sizes: list[str] = []
    min_height_px: int = 0
    refresh_eligible: bool = False
    source_key: str = ""


class VignetteCap(BaseModel):
    enabled: bool = True
    max_per_window: int = 1
    window_seconds: int = 600


class AdManifest(BaseModel):
    slots: list[AdSlot] = []
    vignette: VignetteCap = VignetteCap()


class IndexDecision(BaseModel):
    robots: str = "noindex,follow"
    canonical: str | None = None


class RunState(BaseModel):
    run_id: str
    briefing_text: str = ""
    plan: FunnelPlan | None = None
    facts: dict[int, ResearchFacts] = {}
    drafts: dict[int, PageDraft] = {}
    seo: dict[int, dict] = {}
    images: dict[int, str] = {}
    image_reviews: dict[int, dict] = {}
    # Official-destination screenshots per SOLUTION page (CARD-0005): each value
    # is a list of {"url": <official_link>, "path": <local webp>} dicts captured
    # best-effort by step_screenshot and embedded after the matching link at
    # publish. Empty/absent when the feature flag is off, the page is not
    # SOLUTION, or no ScreenshotProvider is wired.
    screenshots: dict[int, list[dict]] = {}
    # AS URLS EXTERNAS QUE CADA PÁGINA PODE USAR -- decididas UMA VEZ, logo
    # depois da pesquisa daquela página (ver steps.registrar_canais_oficiais),
    # porque a decisão precisa de browser (confirmar que a página existe e que
    # não é um portal que vive de anúncio) e browser é caro. O redator, o gate
    # de conteúdo e o screenshot LEEM daqui, então os três nunca discordam sobre
    # qual é o canal oficial da página. Vazio = a pesquisa não trouxe nada
    # linkável, e a página falha fechada no gate de densidade.
    official_links: dict[int, list[str]] = {}
    # O QUE O WORDPRESS DEVOLVEU AO PUBLICAR, por página. É o contrato de elo
    # com o módulo de campanha do Google Ads.
    #
    # Até aqui o motor recebia do WP um objeto com `id`, `slug`, `link` e
    # `status`, extraía SÓ o `id` e descartava o resto — então as 5 a 7 URLs de
    # um funil publicado precisavam ser REDIGITADAS à mão para que a receita do
    # AdSense fosse atribuída à campanha.
    #
    # ⚠️ GRAVADO VERBATIM, nunca remontado a partir do slug. O slug muda em três
    # pontos independentes: `_slug_com_sufixo` (a ponte), `dedupe_slugs` (o
    # motor) e o próprio WordPress, que acrescenta `-2` quando o slug já existe
    # e só conta isso na resposta REST.
    #
    # ⚠️ E o `link` de um RASCUNHO não é o permalink: o WP devolve
    # `?post_type=r&p=2146` e só troca por `/r/<slug>/` quando o post vai ao ar.
    # Medido no run de 17/08/2026. Quem consome tem de saber disso — por isso o
    # `status_wp` viaja junto, e não se deve derivar URL final de rascunho.
    published: dict[int, dict] = {}
    step_status: dict[str, StepResult] = {}
    # RAMO EDITORIAL NOVO (B4). Gravado no estado para ser PEGAJOSO: um run que
    # nasceu no ramo novo continua nele quando retomado sem o perfil, em vez
    # de escrever metade do funil com um prompt e metade com outro.
    editorial_v2: bool = False
    # O briefing-v1 VALIDADO de cada página escrita no ramo novo. Página com
    # briefing aqui = página escrita a partir dele (a B5 usa isso para exigir
    # revisão e recibo só onde o ramo novo escreveu).
    briefings: dict[int, dict] = {}
    # REVISOR CONTEXTUAL (B5), só no ramo novo. `revisoes[n]` é o registro
    # revisao-v1 da página (rodadas, achados, patches aplicados e recusados,
    # decisão, erro, sha256 de entrada e de saída); `recibos[n]` só existe com
    # decisão `aprovado` (do revisor ou da pessoa) e carrega o sha256 que o
    # `step_publish` confere; `decisoes_humanas[n]` é a saída da revisão humana
    # (`funnelforge decidir`), presa ao sha256 do conteúdo.
    revisoes: dict[int, dict] = {}
    recibos: dict[int, dict] = {}
    decisoes_humanas: dict[int, dict] = {}
    # O que as normalizações determinísticas mudaram no texto (normalize do
    # Gutenberg, aviso canônico, template da LP) e as decorações estruturais
    # que a publicação acrescentou DEPOIS do recibo (aviso de identidade,
    # imagem, prints). Nada mais pode mudar o texto depois do recibo.
    normalizacoes: dict[int, list[dict]] = {}
    decoracoes: dict[int, list[dict]] = {}
    # REVISÃO GLOBAL do funil pronto (só com `jornada`): uma verificação
    # consolidada depois da redação, com achados localizados e PROPOSTAS para
    # decisão humana. Não reescreve nada. Vazio = não rodou.
    revisao_global: dict = {}
    # METADADOS E JSON-LD por página (`pipeline/metadados.py`), calculados sem
    # LLM depois do portão final. Ainda não são enviados ao WordPress.
    metadados: dict[int, dict] = {}
    # DOSSIÊ FACTUAL congelado (`domain/dossie.py`) e o hash do conteúdo. Um
    # resume usa este mesmo dossiê; nada muda os fatos durante a redação.
    dossie: dict = {}
    dossie_sha256: str = ""

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, s: str) -> RunState:
        return cls.model_validate_json(s)
