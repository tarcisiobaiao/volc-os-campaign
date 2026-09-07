"""A fronteira entre estratégia aprovada e pedido de imagem.

## Por que existe um contrato aqui, e não uma chamada direta

A peça estratégica e o pedido de render falam de coisas diferentes. A peça tem
`hook`, `hipotese`, `angulo` — vocabulário de arbitragem. O motor quer um texto
de briefing e uma lista de slots. Sem uma fronteira nomeada, a tradução acabaria
espalhada por um router, e o campo errado seria usado por engano exatamente uma
vez: `texto_principal` é a copy que vai FORA da imagem, no anúncio, e usá-la
como se fosse a arte inteira é o erro mais fácil de cometer aqui.

## O que este módulo se recusa a decidir

Ele não escolhe estratégia, não reescreve copy, não aprova pixel e não infere
elegibilidade Meta. Ele recebe um lote que o `AgenteCriativoMeta` produziu, uma
seleção que uma pessoa fez, e devolve pedidos de render com a linhagem intacta.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


SCHEMA_VERSION = "1"

#: Teto de renders por pedido de geração.
#:
#: É SEPARADO do `MAX_VARIACOES = 15` estratégico de propósito: aquele limita
#: quantas ideias diferentes cabem num lote, este limita quantos arquivos um
#: clique pode mandar produzir. 15 peças × 3 formatos já são 45 renders, e o
#: número que importa para o custo é o segundo.
MAX_RENDERS_POR_PEDIDO = 45


class ModeloEstrito(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Linhagem(ModeloEstrito):
    """De onde esta imagem veio, em refs que sobrevivem à próxima run."""

    creative_ref: str = Field(pattern=r"^creative_[a-z0-9_-]{3,64}$")
    group_ref: str = Field(pattern=r"^group_[a-z0-9_-]{3,64}$")
    copy_ref: str = Field(pattern=r"^copy_[a-z0-9_-]{3,64}$")
    state_ref: str = Field(pattern=r"^state_[a-z0-9_-]{3,64}$")
    project_ref: str = Field(pattern=r"^crproj_[a-f0-9]{24}$")
    run_ref: str = Field(pattern=r"^crrun_[a-f0-9]{24}$")
    fato_refs: list[str] = Field(default_factory=list, max_length=30)
    rule_refs: list[str] = Field(default_factory=list, max_length=30)


class BriefingDeImagem(ModeloEstrito):
    """O que o motor precisa saber para compor UMA peça, em UM formato.

    `texto_na_arte` e `copy_da_campanha` são campos separados e continuam
    separados até o fim: o primeiro é para os pixels, o segundo para o anúncio.
    Fundi-los faria a imagem nascer com o texto do post carimbado nela.
    """

    linhagem: Linhagem
    formato_slot: str = Field(min_length=2, max_length=16)
    direcao_visual: str = Field(min_length=3, max_length=1200)
    texto_na_arte: str = Field(min_length=1, max_length=560)
    contexto_do_publico: str = Field(min_length=3, max_length=4000)
    objetivo: str = Field(min_length=3, max_length=64)


class AutorizacaoDeGasto(ModeloEstrito):
    """O que a PESSOA confirmou ver antes do clique que gasta.

    Não é telemetria e não é conveniência de interface: é o consentimento que a
    rota de geração exige para despachar. Os três campos são exatamente os três
    que o operador precisa ter lido — qual modelo vai rodar, quantos arquivos
    saem, e até quanto ele autoriza — e o servidor RECALCULA os três antes de
    aceitar. Um teto conferido no browser não é um teto.

    ⚠️ `teto_custo_usd` limita uma ESTIMATIVA. O provider devolve contagem de
    token, nunca dólar, então este número é derivado de tabela de referência e
    não de fatura. O limite que o servidor consegue impor com exatidão é
    `total_de_renders`: ele conta chamadas, e chamada é o que se paga. Prometer
    controle financeiro exato aqui seria mentira; os dois campos existem juntos
    porque um é verificável e o outro é declarado.
    """

    #: O identificador do motor tal como a tela o exibiu (ex.: "gemini:<modelo>").
    modelo: str = Field(min_length=3, max_length=120)
    #: Quantos arquivos o operador viu que seriam produzidos. Divergiu, recusa.
    total_de_renders: int = Field(ge=1, le=MAX_RENDERS_POR_PEDIDO)
    #: Teto autorizado, em dólares, sobre a ESTIMATIVA de referência.
    teto_custo_usd: float | None = Field(default=None, ge=0)


class PedidoDeGeracao(ModeloEstrito):
    """O que o cliente manda. Refs opacas; nada de credencial ou SQL."""

    schema_version: str = SCHEMA_VERSION
    run_ref: str = Field(pattern=r"^crrun_[a-f0-9]{24}$")
    selected_creative_refs: list[str] = Field(min_length=1, max_length=15)
    format_ids: list[str] = Field(min_length=1, max_length=12)
    brand_pack_ref: str | None = Field(default=None, pattern=r"^[A-Za-z0-9:_-]{3,180}$")
    #: Ausente ao PLANEJAR (planejar não gasta) e obrigatória ao GERAR.
    #: Deixá-la opcional no modelo é o que permite a mesma forma servir as duas
    #: rotas; quem exige é a rota que despacha, e ela exige explicitamente.
    autorizacao: AutorizacaoDeGasto | None = None

    @model_validator(mode="after")
    def sem_duplicatas(self) -> "PedidoDeGeracao":
        if len(set(self.selected_creative_refs)) != len(self.selected_creative_refs):
            raise ValueError("selected_creative_refs contém refs duplicadas")
        if len(set(self.format_ids)) != len(self.format_ids):
            raise ValueError("format_ids contém formatos duplicados")
        return self


class Bloqueio(ModeloEstrito):
    """Um motivo pelo qual este pedido não pode virar render.

    Cada bloqueio é uma frase para o operador e um código para quem investiga.
    Eles são calculados ANTES de qualquer escrita ou chamada de provider: a
    lista existe para a tela desenhar a recusa, não para explicar um gasto que
    já aconteceu.
    """

    codigo: str
    mensagem: str


class PlanoDeGeracao(ModeloEstrito):
    """N conceitos × M formatos, com o preço e as recusas na mesma folha."""

    briefings: list[BriefingDeImagem]
    conceitos: int
    formatos: int
    total_de_renders: int
    teto: int = MAX_RENDERS_POR_PEDIDO
    #: `None` quando o custo é desconhecido. NUNCA zero: zero é um preço, e
    #: "não sei" não é um preço.
    custo_estimado_usd: float | None = None
    bloqueios: list[Bloqueio] = Field(default_factory=list)

    @property
    def pode_executar(self) -> bool:
        return not self.bloqueios and bool(self.briefings)
