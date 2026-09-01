"""O plano de campanha — o payload dito em português, sem o SDK do Google.

## Por que este módulo existe

`construir()` devolve `(list[MutateOperation], Resultado)`. Isso é exatamente o
que o executor precisa e exatamente o que mais ninguém consegue usar:

- `MutateOperation` é protobuf. Não serializa em JSON, não atravessa HTTP e não
  chega à tela.
- Importar qualquer módulo de canal puxa `google.ads.googleads`. O Hub
  (`backend/app/`) **não depende do SDK em tempo de import** e não pode passar a
  depender — `campanha/perfil.py` documenta isso e dois testes de árvore
  sintática o vigiam.
- `Resultado.Achado` carrega `motivo` legível, que é ótimo para humano e
  inútil para código: a tela não pode ligar comportamento a substring de frase
  em português.

O plano resolve os três: é dataclass pura, JSON-nativa, com **código estável de
bloqueio** ao lado da causa legível.

## O plano é PROJEÇÃO do payload, não uma segunda montagem

A tentação seria escrever, por canal, uma função que remonta o plano a partir do
brief. Seria uma segunda implementação da mesma decisão — e duas implementações
da mesma decisão divergem, sempre, e a divergência aparece no lote.

Aqui é o contrário: `projetar()` lê **as operações que iriam para a API** e as
traduz. Se o builder mudar o orçamento, o plano muda junto porque é o mesmo
objeto sendo lido. Um plano que discorda do payload é impossível por construção,
não por disciplina.

Efeito colateral que vale o preço: projetar obriga a serializar cada operação,
então `PlanoDeCanal.n_bytes_operacoes` é prova executável de que o grafo v25
existe e serializa — não é uma promessa no docstring.

## `ausente ≠ zero ≠ falha ≠ não aplicável`

Os quatro estados vivem em campos diferentes:

- **ausente** — `None` em campo opcional (`orcamento.tcpa_micros is None`);
- **zero** — o número zero, que só aparece quando a API o recebeu de fato;
- **falha** — entra em `bloqueios`, com código;
- **não aplicável** — entra em `nao_operado`, que é resposta declarada do canal
  ("Display não monta sitelink"), nunca lacuna.

## O que este módulo NÃO faz

Não importa `perfil.py` (que importa os canais, que importam este módulo — seria
ciclo), não decide autorização de fronteira externa e não conhece nenhum canal
pelo nome. Quem sabe se um canal pode chegar ao `validate_only` é o canal, e ele
entrega essa resposta pronta em `Prontidao`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

# ═══════════════════════════════════════════════════════════════════════════
# CÓDIGOS DE BLOQUEIO
# ═══════════════════════════════════════════════════════════════════════════
#
# Contrato com a API/tela. São ESTÁVEIS: mudar o texto de um `motivo` é livre,
# mudar um código é quebrar consumidor. Cada código responde "o que o operador
# faz agora", não "onde o programa parou".

#: O canal não tem builder — não há o que planejar.
CANAL_SEM_BUILDER = "CANAL_SEM_BUILDER"
#: O SDK instalado não tem o namespace/campo v25 que o builder emite.
SDK_V25_INDISPONIVEL = "SDK_V25_INDISPONIVEL"
#: Texto reprovado por limite, contagem, duplicata ou DKI.
CONTEUDO_REPROVADO = "CONTEUDO_REPROVADO"
#: Texto reprovado pelo portão de política (país × vertical).
POLITICA_REPROVADA = "POLITICA_REPROVADA"
#: Falta asset obrigatório do formato (papel sem nenhum item).
ASSET_OBRIGATORIO_AUSENTE = "ASSET_OBRIGATORIO_AUSENTE"
#: Asset excede o teto de itens do papel, ou o teto combinado.
ASSET_ACIMA_DO_TETO = "ASSET_ACIMA_DO_TETO"
#: Asset remoto/local chegou sem `ReciboAssetAprovado` da ponte criativa.
ASSET_SEM_RECIBO = "ASSET_SEM_RECIBO"
#: Recibo existe e não confere com os bytes, o papel, o hash ou a conta.
ASSET_RECIBO_DIVERGENTE = "ASSET_RECIBO_DIVERGENTE"
#: Resource name fora da forma canônica `customers/<cid>/assets/<id>`.
RESOURCE_NAME_INVALIDO = "RESOURCE_NAME_INVALIDO"
#: O brief trouxe um campo que ESTE canal não opera. Recusa, não descarte.
CAMPO_NAO_OPERADO = "CAMPO_NAO_OPERADO"
#: Decisão obrigatória do canal não foi tomada (nem True nem False).
CONFIGURACAO_AUSENTE = "CONFIGURACAO_AUSENTE"
#: `estrategia_lance` fora da lista fechada do canal.
LANCE_NAO_PERMITIDO = "LANCE_NAO_PERMITIDO"
#: Não há conversão válida declarada — o canal não pode ser criado sem medir.
MENSURACAO_INADEQUADA = "MENSURACAO_INADEQUADA"
#: Sinal de audiência obrigatório ausente para este subtipo de campanha.
SINAL_OBRIGATORIO_AUSENTE = "SINAL_OBRIGATORIO_AUSENTE"
#: O grafo monta, mas o executor não encaminha este canal ao mutate real.
CRIACAO_NAO_AUTORIZADA = "CRIACAO_NAO_AUTORIZADA"
#: Performance Max planeja e serializa offline, e não está no registro do
#: executor. Código PRÓPRIO, e não `CANAL_SEM_BUILDER`, porque as duas leituras
#: são opostas para quem opera: "o canal não existe aqui" convida a desistir,
#: "o canal planeja e a porta ainda não abriu" convida a pedir a porta. O 422
#: que a rota devolve para `canal=PMAX` precisa carregar ESTE código.
PMAX_FORA_DO_EXECUTOR = "PMAX_FORA_DO_EXECUTOR"
#: O grafo monta, mas a prova externa (`validate_only`) não está habilitada.
PROVA_EXTERNA_NAO_AUTORIZADA = "PROVA_EXTERNA_NAO_AUTORIZADA"
#: A API respondeu recusando o payload no `validate_only`.
VALIDATE_ONLY_RECUSADO = "VALIDATE_ONLY_RECUSADO"
#: Achado real que a tabela abaixo ainda não sabe nomear. Nunca é silêncio: o
#: `motivo` legível viaja junto e a tela mostra o texto cru.
BLOQUEIO_NAO_CLASSIFICADO = "BLOQUEIO_NAO_CLASSIFICADO"

CODIGOS: tuple[str, ...] = (
    CANAL_SEM_BUILDER,
    SDK_V25_INDISPONIVEL,
    CONTEUDO_REPROVADO,
    POLITICA_REPROVADA,
    ASSET_OBRIGATORIO_AUSENTE,
    ASSET_ACIMA_DO_TETO,
    ASSET_SEM_RECIBO,
    ASSET_RECIBO_DIVERGENTE,
    RESOURCE_NAME_INVALIDO,
    CAMPO_NAO_OPERADO,
    CONFIGURACAO_AUSENTE,
    LANCE_NAO_PERMITIDO,
    MENSURACAO_INADEQUADA,
    SINAL_OBRIGATORIO_AUSENTE,
    CRIACAO_NAO_AUTORIZADA,
    PMAX_FORA_DO_EXECUTOR,
    PROVA_EXTERNA_NAO_AUTORIZADA,
    VALIDATE_ONLY_RECUSADO,
    BLOQUEIO_NAO_CLASSIFICADO,
)

# Classificação por PREFIXO do campo do achado, do mais específico ao mais
# genérico. O campo é escolhido pelo builder e já é estável — `demand_gen.
# upgraded_targeting`, `imagens_display.marketing`, `estrategia_lance`. Ligar o
# código ao campo, e não ao texto do motivo, é o que permite reescrever uma
# mensagem sem quebrar a tela.
_POR_PREFIXO: tuple[tuple[str, str], ...] = (
    ("sdk.google_ads", SDK_V25_INDISPONIVEL),
    ("mensuracao", MENSURACAO_INADEQUADA),
    ("pmax.mensuracao", MENSURACAO_INADEQUADA),
    ("pmax.sinais", SINAL_OBRIGATORIO_AUSENTE),
    ("estrategia_lance", LANCE_NAO_PERMITIDO),
    ("politica", POLITICA_REPROVADA),
    ("imagens", ASSET_OBRIGATORIO_AUSENTE),
    ("assets", ASSET_OBRIGATORIO_AUSENTE),
    ("videos", ASSET_OBRIGATORIO_AUSENTE),
)

# Achados de asset chegam todos sob o mesmo prefixo de campo; o que separa
# "faltou" de "veio adulterado" é o motivo. Aqui — e SÓ aqui — o texto participa
# da classificação, porque é o único lugar onde o builder não tem campo distinto
# para oferecer. A tabela é fechada e o que ela não reconhece cai no código
# genérico de asset, nunca em silêncio.
_MOTIVO_DE_ASSET: tuple[tuple[str, str], ...] = (
    ("sem ReciboAssetAprovado", ASSET_SEM_RECIBO),
    ("sem recibo", ASSET_SEM_RECIBO),
    ("recibo não foi emitido", ASSET_RECIBO_DIVERGENTE),
    ("recibo é do canal", ASSET_RECIBO_DIVERGENTE),
    ("recibo aprovou papel", ASSET_RECIBO_DIVERGENTE),
    ("divergente", ASSET_RECIBO_DIVERGENTE),
    ("divergem", ASSET_RECIBO_DIVERGENTE),
    ("diverge", ASSET_RECIBO_DIVERGENTE),
    ("resource_name", RESOURCE_NAME_INVALIDO),
    ("resource name", RESOURCE_NAME_INVALIDO),
    ("não está na conta", RESOURCE_NAME_INVALIDO),
    ("atravessa conta", RESOURCE_NAME_INVALIDO),
    ("temporário", RESOURCE_NAME_INVALIDO),
    ("máximo", ASSET_ACIMA_DO_TETO),
    ("acima", ASSET_ACIMA_DO_TETO),
    ("mínimo", ASSET_OBRIGATORIO_AUSENTE),
    ("exige", ASSET_OBRIGATORIO_AUSENTE),
    ("ausente", ASSET_OBRIGATORIO_AUSENTE),
)

_TEXTO = ("headline", "description", "long_headline", "business_name",
          "callout", "sitelink", "snippet", "keyword")


def classificar(campo: str, motivo: str) -> str:
    """Achado do builder → código estável de bloqueio.

    Sem correspondência devolve ``BLOQUEIO_NAO_CLASSIFICADO`` — que é uma
    resposta, não um buraco: o consumidor sabe que precisa mostrar o `motivo`
    cru em vez de tomar decisão automática.
    """
    c = (campo or "").strip().lower()
    m = (motivo or "").strip().lower()
    # ⚠️ A raiz é o segmento ANTES do primeiro ponto, e ela precisa casar por
    # `startswith` e não por igualdade: os três canais que operam asset nomeiam
    # o campo como `imagens_display.marketing`, `imagens_demand_gen.logo_quadrado`,
    # `imagens_pmax.marketing_quadrada`. Um casamento exato contra "imagens"
    # falharia nos três e mandaria todo achado de asset para o código genérico
    # — que é como um bloqueio de recibo adulterado vira "não classificado".
    raiz = c.split(".", 1)[0]

    for prefixo, codigo in sorted(_POR_PREFIXO, key=lambda p: -len(p[0])):
        if c == prefixo or c.startswith(prefixo + ".") or raiz.startswith(prefixo):
            if codigo is ASSET_OBRIGATORIO_AUSENTE:
                for agulha, especifico in _MOTIVO_DE_ASSET:
                    if agulha in m:
                        return especifico
                # ⚠️ NÃO cai em "obrigatório ausente". Um achado de asset que a
                # tabela não reconhece pode ser peso, geometria ou conta errada,
                # e carimbar "faltou asset" mandaria o operador adicionar uma
                # imagem quando o problema é a que já está lá. Errar o código é
                # pior do que admitir que não se sabe.
                return BLOQUEIO_NAO_CLASSIFICADO
            return codigo

    if raiz in ("demand_gen", "pmax", "rede", "sub_intencoes"):
        return CONFIGURACAO_AUSENTE
    if any(c.startswith(t) for t in _TEXTO):
        if "termo proibido" in m or "política" in m or "politica" in m:
            return POLITICA_REPROVADA
        return CONTEUDO_REPROVADO
    if "não opera" in m or "nao opera" in m or "não migra" in m:
        return CAMPO_NAO_OPERADO
    return BLOQUEIO_NAO_CLASSIFICADO


# ═══════════════════════════════════════════════════════════════════════════
# AS PARTES DO PLANO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Achado:
    """Um bloqueio ou aviso, com código de máquina E causa de gente."""

    codigo: str
    campo: str
    causa: str
    valor: str = ""

    def para_json(self) -> dict:
        return {"codigo": self.codigo, "campo": self.campo,
                "causa": self.causa, "valor": self.valor}


@dataclass(frozen=True)
class Orcamento:
    """O que a campanha vai gastar, lido do `CampaignBudget` + `Campaign`.

    Micros porque é a unidade da API: converter aqui inventaria uma moeda que o
    plano não conhece (o `currency_code` é da CONTA e não vem no payload).
    """

    diario_micros: int | None = None
    total_micros: int | None = None
    periodo: str = ""
    compartilhado: bool | None = None
    estrategia_lance: str = ""
    tcpa_micros: int | None = None
    target_roas: float | None = None

    def para_json(self) -> dict:
        return {
            "diario_micros": self.diario_micros,
            "total_micros": self.total_micros,
            "periodo": self.periodo,
            "compartilhado": self.compartilhado,
            "estrategia_lance": self.estrategia_lance,
            "tcpa_micros": self.tcpa_micros,
            "target_roas": self.target_roas,
        }


@dataclass(frozen=True)
class Criterio:
    """Um `CampaignCriterion` ou `AdGroupCriterion` já traduzido.

    `negativo` é tri-estado de propósito: `None` é "o payload não declarou",
    que em PMax significa coisa diferente de `False`.
    """

    tipo: str
    valor: str
    nivel: str
    negativo: bool | None = None

    def para_json(self) -> dict:
        return {"tipo": self.tipo, "valor": self.valor,
                "nivel": self.nivel, "negativo": self.negativo}


@dataclass(frozen=True)
class Sinal:
    """`AssetGroupSignal` — a dica que substitui targeting positivo em PMax."""

    tipo: str
    valor: str

    def para_json(self) -> dict:
        return {"tipo": self.tipo, "valor": self.valor}


@dataclass(frozen=True)
class Asset:
    """Um asset do payload, com procedência quando ela existe.

    `com_recibo=False` não é acusação: Display aceita `str` puro por
    compatibilidade. É informação — a tela mostra o que subiu sem procedência.
    """

    papel: str
    origem: str            # "bytes" | "resource_name" | "texto"
    identidade: str        # nome do Asset, resource name, ou o próprio texto
    conteudo_hash: str | None = None
    mime: str | None = None
    largura: int | None = None
    altura: int | None = None
    bytes_totais: int | None = None
    com_recibo: bool | None = None
    catalogo_id: str | None = None

    def para_json(self) -> dict:
        return {
            "papel": self.papel, "origem": self.origem,
            "identidade": self.identidade, "conteudo_hash": self.conteudo_hash,
            "mime": self.mime, "largura": self.largura, "altura": self.altura,
            "bytes_totais": self.bytes_totais, "com_recibo": self.com_recibo,
            "catalogo_id": self.catalogo_id,
        }


@dataclass(frozen=True)
class Anuncio:
    """O anúncio, ou — em PMax — a combinação que o Google vai montar sozinho."""

    tipo: str
    headlines: tuple[str, ...] = ()
    long_headlines: tuple[str, ...] = ()
    descriptions: tuple[str, ...] = ()
    business_name: str = ""
    urls_finais: tuple[str, ...] = ()
    status: str = ""
    assets: tuple[Asset, ...] = ()

    def para_json(self) -> dict:
        return {
            "tipo": self.tipo,
            "headlines": list(self.headlines),
            "long_headlines": list(self.long_headlines),
            "descriptions": list(self.descriptions),
            "business_name": self.business_name,
            "urls_finais": list(self.urls_finais),
            "status": self.status,
            "assets": [a.para_json() for a in self.assets],
        }


@dataclass(frozen=True)
class Unidade:
    """O degrau intermediário: `ad_group` em três canais, `asset_group` em PMax.

    Um nome só para dois tipos porque a TELA faz a mesma pergunta nos quatro
    canais ("o que está dentro da campanha?"), e `tipo` preserva a diferença que
    a API faz — PMax não tem ad group, e fingir que tem é o erro que este
    projeto recusa explicitamente.
    """

    tipo: str
    nome: str
    status: str = ""
    anuncios: tuple[Anuncio, ...] = ()
    assets: tuple[Asset, ...] = ()
    criterios: tuple[Criterio, ...] = ()
    sinais: tuple[Sinal, ...] = ()
    urls_finais: tuple[str, ...] = ()

    def para_json(self) -> dict:
        return {
            "tipo": self.tipo, "nome": self.nome, "status": self.status,
            "anuncios": [a.para_json() for a in self.anuncios],
            "assets": [a.para_json() for a in self.assets],
            "criterios": [c.para_json() for c in self.criterios],
            "sinais": [s.para_json() for s in self.sinais],
            "urls_finais": list(self.urls_finais),
        }


@dataclass(frozen=True)
class Segmentacao:
    """Quem vê o anúncio — incluindo a declaração de quem NÃO foi segmentado.

    `aberto_por_ausencia` é o campo que impede a mentira mais cara deste
    domínio: uma campanha sem critério de audiência não é "segmentada com zero
    audiências", é uma campanha que roda em inventário aberto. A tela precisa
    poder dizer isso com todas as letras.
    """

    criterios: tuple[Criterio, ...] = ()
    sinais: tuple[Sinal, ...] = ()
    nivel_geo_idioma: str = ""
    aberto_por_ausencia: tuple[str, ...] = ()

    def para_json(self) -> dict:
        return {
            "criterios": [c.para_json() for c in self.criterios],
            "sinais": [s.para_json() for s in self.sinais],
            "nivel_geo_idioma": self.nivel_geo_idioma,
            "aberto_por_ausencia": list(self.aberto_por_ausencia),
        }


@dataclass(frozen=True)
class Prontidao:
    """A resposta às três perguntas de fronteira, cada uma com seu motivo.

    Nenhuma delas é derivada das outras duas nem inferida do `Resultado`: quem
    responde é o módulo do canal, porque a autorização mora nele e no executor,
    não num heurístico deste arquivo.
    """

    monta: bool
    pode_provar: bool
    pode_criar: bool
    motivo_nao_monta: str = ""
    motivo_nao_prova: str = ""
    motivo_nao_cria: str = ""

    def para_json(self) -> dict:
        return {
            "monta": self.monta,
            "pode_provar": self.pode_provar,
            "pode_criar": self.pode_criar,
            "motivo_nao_monta": self.motivo_nao_monta,
            "motivo_nao_prova": self.motivo_nao_prova,
            "motivo_nao_cria": self.motivo_nao_cria,
        }


@dataclass(frozen=True)
class PlanoDeCanal:
    """O que a API devolve e a tela desenha. JSON-nativo do topo às folhas."""

    canal: str
    customer_id: str
    login_customer_id: str
    nome_da_campanha: str = ""
    tipo_de_campanha: str = ""
    status_inicial: str = ""
    url_final: str = ""
    orcamento: Orcamento = field(default_factory=Orcamento)
    segmentacao: Segmentacao = field(default_factory=Segmentacao)
    unidades: tuple[Unidade, ...] = ()
    assets_de_campanha: tuple[Asset, ...] = ()
    bloqueios: tuple[Achado, ...] = ()
    avisos: tuple[Achado, ...] = ()
    nao_operado: tuple[str, ...] = ()
    prontidao: Prontidao = field(
        default_factory=lambda: Prontidao(False, False, False)
    )
    n_operacoes: int = 0
    tipos_de_operacao: tuple[str, ...] = ()
    n_bytes_operacoes: int = 0
    impressao: str = ""

    @property
    def bloqueado(self) -> bool:
        return bool(self.bloqueios)

    @property
    def codigos_de_bloqueio(self) -> tuple[str, ...]:
        vistos: list[str] = []
        for b in self.bloqueios:
            if b.codigo not in vistos:
                vistos.append(b.codigo)
        return tuple(vistos)

    def para_json(self) -> dict:
        return {
            "canal": self.canal,
            "customer_id": self.customer_id,
            "login_customer_id": self.login_customer_id,
            "nome_da_campanha": self.nome_da_campanha,
            "tipo_de_campanha": self.tipo_de_campanha,
            "status_inicial": self.status_inicial,
            "url_final": self.url_final,
            "orcamento": self.orcamento.para_json(),
            "segmentacao": self.segmentacao.para_json(),
            "unidades": [u.para_json() for u in self.unidades],
            "assets_de_campanha": [a.para_json() for a in self.assets_de_campanha],
            "bloqueios": [b.para_json() for b in self.bloqueios],
            "avisos": [a.para_json() for a in self.avisos],
            "nao_operado": list(self.nao_operado),
            "prontidao": self.prontidao.para_json(),
            "codigos_de_bloqueio": list(self.codigos_de_bloqueio),
            "operacoes": {
                "quantidade": self.n_operacoes,
                "tipos": list(self.tipos_de_operacao),
                "bytes": self.n_bytes_operacoes,
                "impressao": self.impressao,
            },
        }


# ═══════════════════════════════════════════════════════════════════════════
# A PROJEÇÃO
# ═══════════════════════════════════════════════════════════════════════════
#
# Daqui para baixo lê-se protobuf. Nada disso importa o SDK: as operações
# chegam prontas de quem já o tem, e a leitura usa só `getattr` e o descritor
# que o próprio objeto carrega. Um plano projetado a partir de uma lista vazia
# é um plano vazio — não um erro.


def _oneof(op: Any) -> str:
    """Qual operação este `MutateOperation` carrega."""
    pb = getattr(op, "_pb", op)
    try:
        return pb.WhichOneof("operation") or ""
    except Exception:  # noqa: BLE001 — dublê de teste sem descritor
        return ""


def _bytes_da_operacao(op: Any) -> bytes:
    pb = getattr(op, "_pb", op)
    return pb.SerializeToString(deterministic=True)


def _nome_enum(valor: Any) -> str:
    """Enum do proto → nome. Inteiro cru vira string do inteiro, nunca ''."""
    if valor is None:
        return ""
    nome = getattr(valor, "name", None)
    if isinstance(nome, str):
        return nome
    return str(valor)


def _texto_dos(assets: Iterable[Any]) -> tuple[str, ...]:
    return tuple(str(getattr(a, "text", "")) for a in assets)


def _micros(valor: Any) -> int | None:
    """`0` só é zero quando o proto o declarou; ausência continua None.

    Em proto3 escalar não distingue os dois. Aqui, `0` num campo de dinheiro é
    tratado como ausência PORQUE nenhum builder deste repositório emite
    orçamento zero — e um zero exibido como valor real seria pior do que um
    campo vazio: ele afirma que alguém escolheu não gastar.
    """
    if valor in (None, 0):
        return None
    return int(valor)


def _asset_do_proto(op_create: Any) -> Asset:
    """`asset_operation.create` → Asset do plano, de texto OU de imagem.

    Os dois convivem porque Performance Max cria assets de TEXTO como recurso
    próprio: em PMax não existe anúncio onde a headline pudesse morar inline,
    então cada título é um `Asset` ligado ao asset group por `AssetGroupAsset`.
    Nos outros três canais o texto vive dentro do `Ad`, e aqui só passam
    imagens.

    Em asset de texto, `identidade` É o texto — e isso é deliberado: é ele que
    a régua de cobertura lê para decidir a regra "ao menos uma DESCRIPTION com
    60 caracteres ou menos".
    """
    texto = getattr(getattr(op_create, "text_asset", None), "text", "") or ""
    if texto:
        return Asset(
            papel="TEXT",
            origem="texto",
            identidade=str(texto),
            bytes_totais=None,
        )
    dados = bytes(getattr(getattr(op_create, "image_asset", None), "data", b"") or b"")
    return Asset(
        papel=_nome_enum(getattr(op_create, "type_", None)) or "IMAGE",
        origem="bytes",
        identidade=str(getattr(op_create, "name", "") or ""),
        conteudo_hash=("sha256:" + hashlib.sha256(dados).hexdigest()) if dados else None,
        bytes_totais=len(dados) or None,
    )


def _criterio_de(create: Any, nivel: str) -> Criterio:
    """`CampaignCriterion`/`AdGroupCriterion` → tipo e valor legíveis."""
    negativo = getattr(create, "negative", None)
    if negativo is not None:
        negativo = bool(negativo)

    for campo, tipo, leitor in (
        ("location", "location", lambda x: str(getattr(x, "geo_target_constant", ""))),
        ("language", "language", lambda x: str(getattr(x, "language_constant", ""))),
        ("keyword", "keyword", lambda x: str(getattr(x, "text", ""))),
        ("brand", "brand", lambda x: str(getattr(x, "display_name", "") or
                                         getattr(x, "entity_ids", ""))),
        ("webpage", "webpage", lambda x: str(getattr(x, "criterion_name", ""))),
        ("user_list", "user_list", lambda x: str(getattr(x, "user_list", ""))),
        ("audience", "audience", lambda x: str(getattr(x, "audience", ""))),
        ("age_range", "age_range", lambda x: _nome_enum(getattr(x, "type_", None))),
        ("gender", "gender", lambda x: _nome_enum(getattr(x, "type_", None))),
    ):
        interno = getattr(create, campo, None)
        if interno is None:
            continue
        # proto-plus devolve a mensagem-filha mesmo quando não setada; o oneof
        # do pai é quem diz qual ramo foi ocupado.
        pb = getattr(create, "_pb", create)
        try:
            ocupado = pb.WhichOneof("criterion")
        except Exception:  # noqa: BLE001
            ocupado = None
        if ocupado is not None and ocupado != campo:
            continue
        valor = leitor(interno)
        if ocupado is None and not valor:
            continue
        return Criterio(tipo=tipo, valor=valor, nivel=nivel, negativo=negativo)

    return Criterio(tipo="desconhecido", valor="", nivel=nivel, negativo=negativo)


def _anuncio_de(create: Any) -> Anuncio:
    """`ad_group_ad_operation.create` → anúncio do plano, por formato."""
    ad = getattr(create, "ad", None)
    urls = tuple(str(u) for u in getattr(ad, "final_urls", ()) or ())
    status = _nome_enum(getattr(create, "status", None))

    for campo, tipo in (
        ("responsive_search_ad", "responsive_search_ad"),
        ("responsive_display_ad", "responsive_display_ad"),
        ("demand_gen_multi_asset_ad", "demand_gen_multi_asset_ad"),
    ):
        pb = getattr(ad, "_pb", ad)
        try:
            ocupado = pb.WhichOneof("ad_data")
        except Exception:  # noqa: BLE001
            ocupado = None
        if ocupado is not None and ocupado != campo:
            continue
        info = getattr(ad, campo, None)
        if info is None:
            continue

        longa = getattr(info, "long_headline", None)
        if longa is not None and hasattr(longa, "text"):
            longas = (str(longa.text),) if str(longa.text) else ()
        else:
            longas = _texto_dos(getattr(info, "long_headlines", ()) or ())

        assets: list[Asset] = []
        for papel, atributo in (
            ("MARKETING_IMAGE", "marketing_images"),
            ("SQUARE_MARKETING_IMAGE", "square_marketing_images"),
            ("PORTRAIT_MARKETING_IMAGE", "portrait_marketing_images"),
            ("TALL_PORTRAIT_MARKETING_IMAGE", "tall_portrait_marketing_images"),
            ("LOGO", "logo_images"),
            ("SQUARE_LOGO", "square_logo_images"),
            ("YOUTUBE_VIDEO", "youtube_videos"),
        ):
            for item in getattr(info, atributo, ()) or ():
                assets.append(Asset(
                    papel=papel, origem="resource_name",
                    identidade=str(getattr(item, "asset", "")),
                ))

        return Anuncio(
            tipo=tipo,
            headlines=_texto_dos(getattr(info, "headlines", ()) or ()),
            long_headlines=longas,
            descriptions=_texto_dos(getattr(info, "descriptions", ()) or ()),
            business_name=str(getattr(info, "business_name", "") or ""),
            urls_finais=urls,
            status=status,
            assets=tuple(assets),
        )

    return Anuncio(tipo="desconhecido", urls_finais=urls, status=status)


def projetar(
    *,
    canal: str,
    customer_id: str,
    login_customer_id: str,
    operacoes: Sequence[Any],
    resultado: Any,
    prontidao: Prontidao,
    nao_operado: Sequence[str] = (),
    aberto_por_ausencia: Sequence[str] = (),
    nivel_geo_idioma: str = "campanha",
    assets_por_resource_name: Mapping[str, Asset] | None = None,
) -> PlanoDeCanal:
    """Traduz o payload real em plano serializável.

    `resultado` é um `validacao.Resultado` — recebido por duck typing para que
    este módulo não importe o pacote de validação e ganhe um ciclo. Só se lê
    `.achados`, e cada achado vira `Achado` com código estável.
    """
    bloqueios: list[Achado] = []
    avisos: list[Achado] = []
    for a in getattr(resultado, "achados", ()) or ():
        destino = bloqueios if getattr(a, "severidade", "") == "erro" else avisos
        # O código DITO pelo builder ganha do adivinhado. A tabela por prefixo
        # continua existindo para os achados antigos, que são a maioria; ela é
        # a rede, não a regra.
        codigo = str(getattr(a, "codigo", "") or "") or classificar(
            getattr(a, "campo", ""), getattr(a, "motivo", ""))
        destino.append(Achado(
            codigo=codigo,
            campo=str(getattr(a, "campo", "")),
            causa=str(getattr(a, "motivo", "")),
            valor=str(getattr(a, "valor", "")),
        ))

    # ⚠️ Só quando NADA MAIS explica a ausência do grafo. Um brief reprovado no
    # conteúdo também produz `monta=False`, e carimbar `CANAL_SEM_BUILDER` ali
    # mandaria o operador procurar um builder que existe — enquanto o defeito
    # está numa headline de 34 caracteres, que já está listada logo acima.
    if not prontidao.monta and prontidao.motivo_nao_monta and not bloqueios:
        bloqueios.append(Achado(
            codigo=CANAL_SEM_BUILDER, campo="canal",
            causa=prontidao.motivo_nao_monta, valor=canal,
        ))

    conhecidos: dict[str, Asset] = dict(assets_por_resource_name or {})
    orcamento = Orcamento()
    segmentacao_criterios: list[Criterio] = []
    sinais: list[Sinal] = []
    unidades: list[Unidade] = []
    assets_de_campanha: list[Asset] = []
    nome = tipo_campanha = status = url = ""
    tipos: list[str] = []
    total_bytes = 0
    impressao = hashlib.sha256()

    # Um índice por resource name temporário para religar o asset que nasce no
    # mesmo mutate ao anúncio que só o referencia por id.
    assets_novos: dict[str, Asset] = {}
    criterios_de_unidade: list[Criterio] = []
    anuncios_soltos: list[Anuncio] = []
    unidades_por_rn: dict[str, list] = {}

    for op in operacoes:
        qual = _oneof(op)
        tipos.append(qual or "desconhecida")
        try:
            crus = _bytes_da_operacao(op)
        except Exception:  # noqa: BLE001 — dublê sem serialização
            crus = b""
        total_bytes += len(crus)
        impressao.update(crus)

        create = getattr(getattr(op, qual, None), "create", None) if qual else None
        if create is None:
            continue

        if qual == "campaign_budget_operation":
            orcamento = Orcamento(
                diario_micros=_micros(getattr(create, "amount_micros", None)),
                total_micros=_micros(getattr(create, "total_amount_micros", None)),
                periodo=_nome_enum(getattr(create, "period", None)),
                compartilhado=bool(getattr(create, "explicitly_shared", False)),
                estrategia_lance=orcamento.estrategia_lance,
                tcpa_micros=orcamento.tcpa_micros,
                target_roas=orcamento.target_roas,
            )
        elif qual == "campaign_operation":
            nome = str(getattr(create, "name", "") or "")
            tipo_campanha = _nome_enum(
                getattr(create, "advertising_channel_type", None))
            status = _nome_enum(getattr(create, "status", None))
            pb = getattr(create, "_pb", create)
            try:
                lance = pb.WhichOneof("campaign_bidding_strategy") or ""
            except Exception:  # noqa: BLE001
                lance = ""
            tcpa = roas = None
            if lance == "maximize_conversions":
                tcpa = _micros(getattr(
                    getattr(create, "maximize_conversions"), "target_cpa_micros", None))
            elif lance == "maximize_conversion_value":
                bruto = getattr(
                    getattr(create, "maximize_conversion_value"), "target_roas", None)
                roas = float(bruto) if bruto else None
            orcamento = Orcamento(
                diario_micros=orcamento.diario_micros,
                total_micros=orcamento.total_micros,
                periodo=orcamento.periodo,
                compartilhado=orcamento.compartilhado,
                estrategia_lance=lance.upper(),
                tcpa_micros=tcpa,
                target_roas=roas,
            )
        elif qual == "campaign_criterion_operation":
            segmentacao_criterios.append(_criterio_de(create, "campanha"))
        elif qual == "ad_group_operation":
            unidades_por_rn.setdefault(
                str(getattr(create, "resource_name", "") or f"ad_group[{len(unidades_por_rn)}]"),
                [Unidade(
                    tipo="ad_group",
                    nome=str(getattr(create, "name", "") or ""),
                    status=_nome_enum(getattr(create, "status", None)),
                )],
            )
        elif qual == "ad_group_criterion_operation":
            criterios_de_unidade.append(_criterio_de(create, "ad_group"))
        elif qual == "ad_group_ad_operation":
            anuncios_soltos.append(_anuncio_de(create))
        elif qual == "asset_operation":
            a = _asset_do_proto(create)
            rn = str(getattr(create, "resource_name", "") or "")
            if rn:
                assets_novos[rn] = a
        elif qual == "asset_group_operation":
            unidades_por_rn.setdefault(
                str(getattr(create, "resource_name", "") or f"asset_group[{len(unidades_por_rn)}]"),
                [Unidade(
                    tipo="asset_group",
                    nome=str(getattr(create, "name", "") or ""),
                    status=_nome_enum(getattr(create, "status", None)),
                    urls_finais=tuple(
                        str(u) for u in getattr(create, "final_urls", ()) or ()),
                )],
            )
        elif qual == "asset_group_asset_operation":
            grupo = str(getattr(create, "asset_group", "") or "")
            rn = str(getattr(create, "asset", "") or "")
            papel = _nome_enum(getattr(create, "field_type", None))
            base = conhecidos.get(rn) or assets_novos.get(rn)
            a = Asset(
                papel=papel,
                origem=base.origem if base else "resource_name",
                identidade=base.identidade if base else rn,
                conteudo_hash=base.conteudo_hash if base else None,
                mime=base.mime if base else None,
                largura=base.largura if base else None,
                altura=base.altura if base else None,
                bytes_totais=base.bytes_totais if base else None,
                com_recibo=base.com_recibo if base else None,
                catalogo_id=base.catalogo_id if base else None,
            )
            unidades_por_rn.setdefault(grupo, [Unidade(
                tipo="asset_group", nome="(referenciado antes de criado)")])
            u = unidades_por_rn[grupo][0]
            unidades_por_rn[grupo][0] = Unidade(
                tipo=u.tipo, nome=u.nome, status=u.status, anuncios=u.anuncios,
                assets=u.assets + (a,), criterios=u.criterios, sinais=u.sinais,
                urls_finais=u.urls_finais,
            )
        elif qual == "asset_group_signal_operation":
            grupo = str(getattr(create, "asset_group", "") or "")
            pb = getattr(create, "_pb", create)
            try:
                ramo = pb.WhichOneof("signal") or ""
            except Exception:  # noqa: BLE001
                ramo = ""
            if ramo == "audience":
                valor = str(getattr(getattr(create, "audience"), "audience", ""))
            elif ramo == "search_theme":
                valor = str(getattr(getattr(create, "search_theme"), "text", ""))
            else:
                valor = ""
            s = Sinal(tipo=ramo or "desconhecido", valor=valor)
            sinais.append(s)
            if grupo in unidades_por_rn:
                u = unidades_por_rn[grupo][0]
                unidades_por_rn[grupo][0] = Unidade(
                    tipo=u.tipo, nome=u.nome, status=u.status,
                    anuncios=u.anuncios, assets=u.assets,
                    criterios=u.criterios, sinais=u.sinais + (s,),
                    urls_finais=u.urls_finais,
                )
        elif qual == "campaign_asset_operation":
            rn = str(getattr(create, "asset", "") or "")
            base = conhecidos.get(rn) or assets_novos.get(rn)
            assets_de_campanha.append(Asset(
                papel=_nome_enum(getattr(create, "field_type", None)),
                origem=base.origem if base else "resource_name",
                identidade=base.identidade if base else rn,
                conteudo_hash=base.conteudo_hash if base else None,
                mime=base.mime if base else None,
                largura=base.largura if base else None,
                altura=base.altura if base else None,
                bytes_totais=base.bytes_totais if base else None,
                com_recibo=base.com_recibo if base else None,
                catalogo_id=base.catalogo_id if base else None,
            ))

    # Religa: os assets criados no mesmo mutate voltam ao anúncio que os
    # referencia por id temporário, e o anúncio entra na sua unidade.
    def _religar(a: Asset) -> Asset:
        base = conhecidos.get(a.identidade) or assets_novos.get(a.identidade)
        if base is None:
            return a
        return Asset(
            papel=a.papel, origem=base.origem, identidade=base.identidade,
            conteudo_hash=base.conteudo_hash, mime=base.mime,
            largura=base.largura, altura=base.altura,
            bytes_totais=base.bytes_totais, com_recibo=base.com_recibo,
            catalogo_id=base.catalogo_id,
        )

    anuncios_religados = tuple(
        Anuncio(
            tipo=an.tipo, headlines=an.headlines, long_headlines=an.long_headlines,
            descriptions=an.descriptions, business_name=an.business_name,
            urls_finais=an.urls_finais, status=an.status,
            assets=tuple(_religar(a) for a in an.assets),
        )
        for an in anuncios_soltos
    )

    for i, (_rn, caixa) in enumerate(unidades_por_rn.items()):
        u = caixa[0]
        if u.tipo == "ad_group":
            u = Unidade(
                tipo=u.tipo, nome=u.nome, status=u.status,
                anuncios=anuncios_religados if i == 0 else (),
                assets=u.assets,
                criterios=tuple(criterios_de_unidade) if i == 0 else (),
                sinais=u.sinais, urls_finais=u.urls_finais,
            )
        unidades.append(u)

    if not unidades and anuncios_religados:
        unidades.append(Unidade(tipo="ad_group", nome="(sem operação de grupo)",
                                anuncios=anuncios_religados))

    if unidades and unidades[0].tipo == "ad_group" and unidades[0].anuncios:
        url = unidades[0].anuncios[0].urls_finais[0] if unidades[0].anuncios[0].urls_finais else ""
    elif unidades and unidades[0].urls_finais:
        url = unidades[0].urls_finais[0]

    return PlanoDeCanal(
        canal=canal,
        customer_id=str(customer_id),
        login_customer_id=str(login_customer_id),
        nome_da_campanha=nome,
        tipo_de_campanha=tipo_campanha,
        status_inicial=status,
        url_final=url,
        orcamento=orcamento,
        segmentacao=Segmentacao(
            criterios=tuple(segmentacao_criterios),
            sinais=tuple(sinais),
            nivel_geo_idioma=nivel_geo_idioma,
            aberto_por_ausencia=tuple(aberto_por_ausencia),
        ),
        unidades=tuple(unidades),
        assets_de_campanha=tuple(assets_de_campanha),
        bloqueios=tuple(bloqueios),
        avisos=tuple(avisos),
        nao_operado=tuple(nao_operado),
        prontidao=prontidao,
        n_operacoes=len(tipos),
        tipos_de_operacao=tuple(tipos),
        n_bytes_operacoes=total_bytes,
        impressao=impressao.hexdigest() if tipos else "",
    )
