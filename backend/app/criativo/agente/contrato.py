"""Contrato estrito do Assistente de Criativos Meta.

O LLM propõe; este módulo decide se a resposta tem forma suficiente para
entrar no sistema. IDs de provedor, mídia e campanha não pertencem aqui.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, model_serializer
from app.criativo.contexto_pagina import ContextoDaPagina, conferir_vinculo_contexto


SCHEMA_VERSION = "1.0"
MAX_VARIACOES = 15


class ModeloEstrito(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Fase(str, Enum):
    NOVA_OPERACAO = "NOVA_OPERACAO"
    DIAGNOSTICO = "DIAGNOSTICO"
    ARQUITETURA = "ARQUITETURA"
    MATRIZ = "MATRIZ"
    COPY = "COPY"
    REFACAO = "REFACAO"


class EscopoFeedback(str, Enum):
    PONTUAL = "PONTUAL"
    GRUPO = "GRUPO"
    PROJETO = "PROJETO"
    UNIVERSAL = "UNIVERSAL"


class FatoDaOferta(ModeloEstrito):
    ref: str = Field(pattern=r"^fact_[a-z0-9_-]{3,64}$")
    declaracao: str = Field(min_length=3, max_length=1200)
    origem: Literal["LANDING_PAGE", "OPERADOR", "POLICY_RECEIPT", "PERFORMANCE_RECEIPT"]
    evidencia_ref: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9:_-]{3,180}$"
    )


class Restricao(ModeloEstrito):
    ref: str = Field(pattern=r"^rule_[a-z0-9_-]{3,64}$")
    texto: str = Field(min_length=3, max_length=1000)
    escopo: EscopoFeedback = EscopoFeedback.PROJETO
    termos_bloqueados: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("termos_bloqueados")
    @classmethod
    def termos_validos(cls, value: list[str]) -> list[str]:
        limpos = [termo.strip() for termo in value]
        if any(len(termo) < 2 or len(termo) > 100 for termo in limpos):
            raise ValueError("termos_bloqueados devem ter entre 2 e 100 caracteres")
        if len({termo.casefold() for termo in limpos}) != len(limpos):
            raise ValueError("termos_bloqueados contém duplicatas")
        return limpos


class ElementoCongelado(ModeloEstrito):
    ref: str = Field(pattern=r"^frozen_[a-z0-9_-]{3,64}$")
    caminho: str = Field(min_length=3, max_length=180)
    # Snapshot de uma peça inclui copy, direção e big idea. Não é só um campo
    # de texto: o teto anterior recusava a retomada de uma aprovação válida.
    valor: str = Field(min_length=1, max_length=16000)
    aprovado_em: str = Field(min_length=10, max_length=40)


class PedidoDoAgente(ModeloEstrito):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    fase: Fase = Fase.NOVA_OPERACAO
    project_ref: str = Field(pattern=r"^crproj_[a-f0-9]{24}$")
    nome_da_operacao: str = Field(min_length=3, max_length=200)
    brand_pack_ref: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9:_-]{3,180}$"
    )
    # Vínculo interno opcional. O Assistente não abre URL nem precisa obrigar o
    # operador a conhecer uma referência técnica para criar uma estratégia.
    destination_ref: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9:_-]{3,180}$"
    )
    objetivo_meta: str | None = Field(default=None, min_length=3, max_length=64)
    url_destino: str | None = None
    contexto_da_pagina: ContextoDaPagina | None = None
    # Âncora editorial confirmada pelo operador, não um objetivo de mídia.
    # Opcional para permitir replay dos briefings históricos.
    assunto_principal: str | None = Field(default=None, min_length=2, max_length=160)
    #: O que a ARTE precisa comunicar no primeiro olhar, que não é a mesma
    #: pergunta que `assunto_principal` responde.
    #:
    #: `assunto_principal` responde "do que esta página trata?" — uma pergunta de
    #: congruência e governança, e a resposta certa para uma matéria sobre um
    #: aplicativo é o nome do aplicativo. `ancora_de_desejo` responde "o que faz
    #: alguém parar o polegar?", e numa matéria sobre consultar um benefício a
    #: resposta é o benefício, não o canal de consulta.
    #:
    #: Colapsar as duas num campo só produziu um lote inteiro de headlines
    #: institucionais: o validador exigia o nome longo do app dentro de cada
    #: imagem, e ele consumia a headline sozinho. Quando a âncora não é
    #: declarada, `assunto_principal` continua valendo — é o comportamento
    #: histórico, e nenhum briefing antigo precisa ser reescrito.
    ancora_de_desejo: str | None = Field(default=None, min_length=2, max_length=80)
    #: Formas que o operador confirma como equivalentes à âncora na arte.
    #:
    #: A contraprova compara sequência literal de tokens, então sem esta lista
    #: "Poupança do ensino médio" seria recusada como ausente mesmo sendo o
    #: mesmo assunto escrito melhor. Quem decide o que é sinônimo é o operador,
    #: nunca o modelo: aceitar variante proposta na mesma resposta que ela
    #: precisa validar tornaria a contraprova circular.
    ancoras_aceitas: list[Annotated[str, Field(min_length=2, max_length=80)]] = Field(
        default_factory=list, max_length=6
    )
    #: A família cromática do universo do assunto, confirmada pelo operador.
    #:
    #: Existe porque instrução em prosa não segurou a cor. Num lote real, com o
    #: prompt já mandando derivar a paleta de objetos, as quatro peças voltaram
    #: azul-marinho (#1C3F94, #133270, #0F2952, #0E1E3D): o modelo passou a
    #: justificar com objeto e chegou no mesmo lugar. Cor precisa do mesmo
    #: tratamento que rota e registro — dado tipado com contraprova, não conselho.
    #:
    #: É AFINIDADE TEMÁTICA, não identidade oficial. Usar a família de cor do
    #: universo de um programa é o que faz a peça ser reconhecida em meio
    #: segundo; reproduzir logotipo, brasão, emblema ou assinatura institucional
    #: continua proibido. São coisas diferentes e o código não pode confundi-las.
    familia_cromatica: list[Annotated[str, Field(min_length=3, max_length=60)]] = Field(
        default_factory=list, max_length=5
    )
    referencias_visuais: str | None = Field(default=None, max_length=1500)
    pais: str = Field(default="BR", pattern=r"^[A-Z]{2}$")
    idioma: str = Field(default="pt-BR", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    contexto_do_publico: str = Field(min_length=3, max_length=4000)
    fatos_da_oferta: list[FatoDaOferta] = Field(min_length=1, max_length=80)
    restricoes: list[Restricao] = Field(default_factory=list, max_length=80)
    elementos_congelados: list[ElementoCongelado] = Field(default_factory=list, max_length=100)
    formatos_permitidos: list[str] = Field(default_factory=lambda: ["1x1", "4x5", "9x16"], min_length=1, max_length=12)
    quantidade_de_pecas: int = Field(default=6, ge=1, le=MAX_VARIACOES)
    feedback: str | None = Field(default=None, max_length=4000)
    feedback_escopo: EscopoFeedback | None = None
    #: O lote que a run anterior produziu, quando existe.
    #:
    #: Refinar sem ele é reescrever do zero: o modelo recebia briefing, feedback
    #: e elementos congelados, mas NÃO o que ele mesmo tinha proposto — então
    #: "troque o hook da peça do frio" não tinha peça nenhuma para trocar, e a
    #: run devolvia um lote novo que só coincidia com o anterior nos pontos
    #: congelados. O campo é montado no servidor a partir da última run
    #: concluída; o cliente não o envia e não pode forjá-lo.
    saida_anterior: "SaidaDoAgente | None" = None

    @field_validator("assunto_principal", mode="before")
    @classmethod
    def assunto_legivel(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            if not any(c.isalnum() for c in value):
                raise ValueError("assunto_principal deve identificar um assunto, não só espaços ou sinais")
        return value

    @field_validator("formatos_permitidos")
    @classmethod
    def formatos_unicos(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("formatos_permitidos contém duplicatas")
        return value

    @model_validator(mode="after")
    def feedback_com_escopo(self) -> "PedidoDoAgente":
        self.url_destino = conferir_vinculo_contexto(self.url_destino, self.contexto_da_pagina)
        if bool(self.feedback) != bool(self.feedback_escopo):
            raise ValueError("feedback e feedback_escopo devem ser enviados juntos")
        refs = [f.ref for f in self.fatos_da_oferta]
        if len(refs) != len(set(refs)):
            raise ValueError("fatos_da_oferta contém refs duplicadas")
        if self.fase == Fase.REFACAO and not self.feedback:
            raise ValueError("REFACAO exige feedback escopado")
        return self


class EntradaNovaOperacao(ModeloEstrito):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    nome_da_operacao: str = Field(min_length=3, max_length=200)
    brand_pack_ref: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9:_-]{3,180}$"
    )
    destination_ref: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9:_-]{3,180}$"
    )
    objetivo_meta: str | None = Field(default=None, min_length=3, max_length=64)
    url_destino: str | None = None
    contexto_da_pagina: ContextoDaPagina | None = None
    assunto_principal: str | None = Field(default=None, min_length=2, max_length=160)
    #: A família cromática do universo do assunto, confirmada pelo operador.
    #:
    #: Existe porque instrução em prosa não segurou a cor. Num lote real, com o
    #: prompt já mandando derivar a paleta de objetos, as quatro peças voltaram
    #: azul-marinho (#1C3F94, #133270, #0F2952, #0E1E3D): o modelo passou a
    #: justificar com objeto e chegou no mesmo lugar. Cor precisa do mesmo
    #: tratamento que rota e registro — dado tipado com contraprova, não conselho.
    #:
    #: É AFINIDADE TEMÁTICA, não identidade oficial. Usar a família de cor do
    #: universo de um programa é o que faz a peça ser reconhecida em meio
    #: segundo; reproduzir logotipo, brasão, emblema ou assinatura institucional
    #: continua proibido. São coisas diferentes e o código não pode confundi-las.
    familia_cromatica: list[Annotated[str, Field(min_length=3, max_length=60)]] = Field(
        default_factory=list, max_length=5
    )
    referencias_visuais: str | None = Field(default=None, max_length=1500)
    pais: str = Field(default="BR", pattern=r"^[A-Z]{2}$")
    idioma: str = Field(default="pt-BR", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    contexto_do_publico: str = Field(min_length=3, max_length=4000)
    fatos_da_oferta: list[FatoDaOferta] = Field(min_length=1, max_length=80)
    restricoes: list[Restricao] = Field(default_factory=list, max_length=80)
    formatos_permitidos: list[str] = Field(default_factory=lambda: ["1x1", "4x5", "9x16"], min_length=1, max_length=12)
    quantidade_de_pecas: int = Field(default=6, ge=1, le=MAX_VARIACOES)

    @field_validator("assunto_principal", mode="before")
    @classmethod
    def assunto_legivel(cls, value: str | None) -> str | None:
        return PedidoDoAgente.assunto_legivel(value)

    @model_validator(mode="after")
    def contexto_vinculado(self) -> "EntradaNovaOperacao":
        self.url_destino = conferir_vinculo_contexto(self.url_destino, self.contexto_da_pagina)
        return self

    @field_validator("formatos_permitidos")
    @classmethod
    def formatos_unicos(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("formatos_permitidos contém duplicatas")
        return value


class PedidoDeContinuacao(ModeloEstrito):
    fase: Fase
    quantidade_de_pecas: int | None = Field(default=None, ge=1, le=MAX_VARIACOES)
    formatos_permitidos: list[str] | None = Field(default=None, min_length=1, max_length=12)
    feedback: str | None = Field(default=None, max_length=4000)
    feedback_escopo: EscopoFeedback | None = None

    @model_validator(mode="after")
    def feedback_com_escopo(self) -> "PedidoDeContinuacao":
        if bool(self.feedback) != bool(self.feedback_escopo):
            raise ValueError("feedback e feedback_escopo devem ser enviados juntos")
        if self.fase == Fase.REFACAO and not self.feedback:
            raise ValueError("REFACAO exige feedback escopado")
        return self


class PedidoDeDecisao(ModeloEstrito):
    run_ref: str = Field(pattern=r"^crrun_[a-f0-9]{24}$")
    decisao: Literal["APROVADO", "REPROVADO"]
    escopo: EscopoFeedback
    caminho: str = Field(pattern=r"^/(?:[A-Za-z0-9_-]+/?)+$", max_length=300)
    feedback: str | None = Field(default=None, max_length=4000)


class Diagnostico(ModeloEstrito):
    oferta_real: str = Field(min_length=3, max_length=1500)
    promessa_maxima: str = Field(min_length=3, max_length=1000)
    tensao_central: str = Field(min_length=3, max_length=1000)
    desconhecidos: list[str] = Field(default_factory=list, max_length=30)
    fato_refs: list[str] = Field(min_length=1, max_length=30)


class EstadoMental(ModeloEstrito):
    ref: str = Field(pattern=r"^state_[a-z0-9_-]{3,64}$")
    nome: str = Field(min_length=3, max_length=160)
    ja_sabe: str = Field(min_length=3, max_length=600)
    duvida: str = Field(min_length=3, max_length=600)
    tensao: str = Field(min_length=3, max_length=600)
    proximo_movimento: str = Field(min_length=3, max_length=600)


class GrupoEstrategico(ModeloEstrito):
    ref: str = Field(pattern=r"^group_[a-z0-9_-]{3,64}$")
    nome: str = Field(min_length=3, max_length=160)
    estado_mental_refs: list[str] = Field(min_length=1, max_length=12)
    funcao: str = Field(min_length=3, max_length=600)
    territorio: str = Field(min_length=3, max_length=600)
    diferenca_material: str = Field(min_length=3, max_length=600)


class CopyCompartilhada(ModeloEstrito):
    ref: str = Field(pattern=r"^copy_[a-z0-9_-]{3,64}$")
    group_ref: str = Field(pattern=r"^group_[a-z0-9_-]{3,64}$")
    texto_principal: str = Field(min_length=1, max_length=2200)
    titulo: str = Field(min_length=1, max_length=255)
    descricao: str = Field(min_length=1, max_length=255)
    cta_nativa: Literal["LEARN_MORE", "SIGN_UP", "GET_QUOTE", "APPLY_NOW", "CONTACT_US", "DOWNLOAD"] = "LEARN_MORE"
    narracao: str | None = Field(default=None, max_length=1200)
    fato_refs: list[str] = Field(min_length=1, max_length=30)


#: Onde o texto vive na peça. Fechado de propósito — ver `DirecaoDeArte`.
ROTAS_DE_TEXTO = (
    "integrado_na_cena",       # letra encosta na cena, com peso/contorno/sombra
    "campo_cromatico",         # área chapada dedicada ao texto (a única que autoriza tarja)
    "tipografia_protagonista", # o texto É a imagem; a cena é fundo ou textura
    "rodape_limpo",            # assunto ocupa o quadro; texto num rodapé estreito
)

#: O gênero fotográfico da peça.
REGISTROS = (
    "foto_crua",       # parece foto de celular, não peça diagramada
    "editorial",       # fotografia publicitária dirigida
    "documento",       # papel, calendário, impresso fotografado
    "natureza_morta",  # objeto isolado sobre campo, luz dura
    "grafico",         # ilustração de dado, número como imagem
    # O vernáculo brasileiro de anúncio de benefício: campo de cor saturado,
    # objeto-herói recortado com sombra, tipografia pesada em caixa alta sobre
    # faixas irregulares, selo de valor e barra de CTA. Feio para um diretor de
    # arte de marca e altamente eficaz em arbitragem — é o registro que o
    # público desta categoria já sabe ler, e ele estava fora do vocabulário.
    "cartaz_beneficio",
)

#: Quanta pessoa entra no quadro.
PRESENCAS_HUMANAS = ("ausente", "maos", "close", "ambiental")

#: Quantos BLOCOS DE TEXTO a peça carrega, e o teto de cada nível.
#:
#: O operador que roda arbitragem olhou as duas melhores peças do lote e disse:
#: "acho que tem informação demais (em quantidade diferente)". Densidade não é
#: gosto — é contável, e o que não é contado não é controlado. Um bloco é cada
#: elemento textual que o olho precisa processar: headline, complemento, CTA,
#: selo, ressalva e CADA item de checklist.
#:
#: 'minima' é a peça de capa editorial — headline e CTA, e mais nada. 'alta' é o
#: cartaz de benefício, que é dense de propósito e funciona assim. Um lote
#: precisa dos dois extremos para testar densidade como variável, em vez de
#: assumir uma e nunca descobrir a outra.
DENSIDADES = ("minima", "media", "alta")
TETO_DE_BLOCOS = {"minima": 3, "media": 5, "alta": 8}


class DirecaoDeArte(ModeloEstrito):
    """Decisões de direção propostas junto da estratégia, nunca por outro agente.

    ## Por que três campos fechados no meio de cinco campos de prosa

    Porque prosa não é auditável, e o lote de 09/09/2026 provou o custo disso: as
    quatro peças declararam cenas diferentes e a MESMA paleta, a MESMA arquitetura
    de texto e o MESMO enquadramento de pessoa — e passaram no portão de
    diversidade, que só compara cinco campos de estratégia. Não havia como o
    código perguntar "esta peça é visualmente diferente daquela?", porque a
    resposta morava em parágrafos livres que só um humano compara.

    Enum, o código compara. E o que ele compara ele pode exigir que varie.

    Os três eixos são ortogonais de propósito: dá para ter `campo_cromatico` com
    `foto_crua` e com `natureza_morta`, `rosto ausente` com qualquer registro. É
    essa ortogonalidade que faz um lote de 4 peças cobrir território de verdade
    em vez de repetir um arranjo com cores trocadas.

    São opcionais porque um blueprint histórico não os tem, e replay de aprovação
    antiga não é aprovação nova. Quem os exige é `validacao.py`, e só para peça
    nova e não congelada.
    """
    blueprint_version: Literal["volc.art-direction/2"] | None = None
    rota_de_texto: Literal[ROTAS_DE_TEXTO] | None = None  # type: ignore[valid-type]
    registro: Literal[REGISTROS] | None = None  # type: ignore[valid-type]
    presenca_humana: Literal[PRESENCAS_HUMANAS] | None = None  # type: ignore[valid-type]
    #: Quantos blocos de texto esta peça pode carregar. Ver DENSIDADES.
    densidade: Literal[DENSIDADES] | None = None  # type: ignore[valid-type]
    #: Quem escreve a tipografia: o modelo de imagem ou o nosso código.
    #:
    #: 'modelo' é o caminho histórico — o provider desenha cena E texto, e a
    #: letra sai do jeito que sair. 'codigo' pede ao provider apenas a CENA,
    #: com um plano de composição que abre a zona por queda de luz, e a
    #: tipografia é desenhada depois com fonte real e contraste medido. O
    #: segundo custa a mesma geração e produz texto que não alucina.
    fonte_do_texto: Literal["modelo", "codigo"] | None = None
    #: O número concreto que ancora o interesse, desenhado como selo destacado.
    #:
    #: Em arbitragem de benefício o algarismo é o que para o polegar — "13KG",
    #: "R$ 200", "9 parcelas" —, não o adjetivo. É texto que vai aos pixels e,
    #: como todo texto de arte, precisa sair de um fato aprovado.
    selo_de_valor: str | None = Field(default=None, min_length=2, max_length=40)
    #: A ressalva que mantém o selo honesto ("conforme critérios do programa").
    #:
    #: Obrigatória quando o selo afirma gratuidade ou valor: é ela que separa
    #: "100% GRATUITO*" de propaganda enganosa por omissão (CDC art. 37 §1º).
    qualificador: str | None = Field(default=None, min_length=3, max_length=90)
    #: Até três promessas de leitura, no padrão de checklist do vernáculo.
    #: São o que a MATÉRIA entrega, nunca o que o benefício concede.
    checklist: list[Annotated[str, Field(min_length=3, max_length=60)]] = Field(
        default_factory=list, max_length=3
    )

    @field_validator("checklist", mode="before")
    @classmethod
    def ausencia_e_lista_vazia(cls, valor):
        """`null` é como um LLM diz "esta peça não tem checklist".

        O schema declara uma lista opcional e o modelo responde `null` — que é
        semanticamente certo e sintaticamente inválido. Recusar o lote inteiro
        por isso é gastar duas tentativas num desacordo de notação, não num
        defeito de conteúdo.
        """
        return [] if valor is None else valor
    composicao: str = Field(min_length=10, max_length=600)
    tipografia: str = Field(min_length=10, max_length=400)
    paleta_e_contraste: str = Field(min_length=10, max_length=400)
    cena: str = Field(min_length=10, max_length=600)
    tratamento: str = Field(min_length=10, max_length=400)

    @model_serializer(mode="wrap")
    def preservar_forma_legada(self, handler):
        # Persisted approvals/signatures compare nested dumps, not just specs.
        # A new null key would rewrite every historical direction on readback.
        #
        # Vale para TODO campo opcional acrescentado depois, não só para
        # `blueprint_version`: `CreativeSpec.direcao_de_arte` é `dict[str, str]`,
        # então uma chave nula não só reescreveria a assinatura de aprovações
        # antigas como faria a spec inteira falhar na releitura.
        material = handler(self)
        for campo in ("blueprint_version", "rota_de_texto", "registro", "presenca_humana",
                      "densidade", "fonte_do_texto", "selo_de_valor", "qualificador"):
            if getattr(self, campo) is None:
                material.pop(campo, None)
        if not self.checklist:
            material.pop("checklist", None)
        return material


class BigIdea(ModeloEstrito):
    """Hipótese editorial revisável; não é diagnóstico nem previsão de CTR."""
    ideia_central: str = Field(min_length=3, max_length=300)
    pergunta_latente: str = Field(min_length=3, max_length=200)
    promessa_do_clique: str = Field(min_length=3, max_length=300)
    cena_chave: str = Field(min_length=3, max_length=400)


class PecaCriativa(ModeloEstrito):
    ref: str = Field(pattern=r"^creative_[a-z0-9_-]{3,64}$")
    group_ref: str = Field(pattern=r"^group_[a-z0-9_-]{3,64}$")
    shared_copy_ref: str = Field(pattern=r"^copy_[a-z0-9_-]{3,64}$")
    estado_mental_ref: str = Field(pattern=r"^state_[a-z0-9_-]{3,64}$")
    angulo: str = Field(min_length=3, max_length=300)
    subangulo: str = Field(min_length=3, max_length=300)
    hipotese: str = Field(min_length=3, max_length=700)
    hook: str = Field(min_length=3, max_length=300)
    mecanismo_de_interrupcao: str = Field(min_length=3, max_length=300)
    formato: str = Field(min_length=2, max_length=80)
    headline_interna: str = Field(min_length=1, max_length=160)
    complemento_interno: str | None = Field(default=None, max_length=300)
    cta_visual: str | None = Field(default=None, max_length=60)
    direcao_visual: str = Field(min_length=3, max_length=1200)
    # Opcional para retomar lotes antigos sem reescrever aprovações históricas.
    direcao_de_arte: DirecaoDeArte | None = None
    big_idea: BigIdea | None = None
    fato_refs: list[str] = Field(min_length=1, max_length=30)
    rule_refs: list[str] = Field(default_factory=list, max_length=30)

    @model_serializer(mode="wrap")
    def preservar_big_idea_legada(self, handler):
        material = handler(self)
        if self.big_idea is None:
            material.pop("big_idea", None)
        return material


class ReciboDeValidacao(ModeloEstrito):
    valido: bool
    codigos: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    knowledge_base_version: str = "copiloto-meta-ads-v2-derived@1.0"


class SaidaDoAgente(ModeloEstrito):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    project_ref: str = Field(pattern=r"^crproj_[a-f0-9]{24}$")
    fase_concluida: Fase
    diagnostico: Diagnostico
    jornada: list[EstadoMental] = Field(min_length=1, max_length=20)
    grupos: list[GrupoEstrategico] = Field(min_length=1, max_length=12)
    copies_compartilhadas: list[CopyCompartilhada] = Field(min_length=1, max_length=24)
    pecas: list[PecaCriativa] = Field(min_length=1, max_length=MAX_VARIACOES)
    recibo: ReciboDeValidacao = Field(
        default_factory=lambda: ReciboDeValidacao(valido=False)
    )
    proximo_ato: str = Field(min_length=3, max_length=500)


_METADADO_NA_PECA = re.compile(
    r"\b(?:G\d+-C\d+|V\d+|APROVAD[OA]|REPROVAD[OA]|STATUS\s*[:=]|GRUPO\s+\d+)\b",
    re.IGNORECASE,
)


def campos_textuais_da_peca(peca: PecaCriativa) -> str:
    return " ".join(
        filter(None, [peca.headline_interna, peca.complemento_interno, peca.cta_visual])
    )


def contem_metadado_operacional(peca: PecaCriativa) -> bool:
    return bool(_METADADO_NA_PECA.search(campos_textuais_da_peca(peca)))


# `PedidoDoAgente.saida_anterior` referencia `SaidaDoAgente`, que nasce mais
# abaixo neste módulo. A reconstrução resolve a referência adiante sem inverter
# a ordem de leitura do arquivo, que vai do pedido para a saída de propósito.
PedidoDoAgente.model_rebuild()
