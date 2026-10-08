"""A configuração de cada canal na fronteira HTTP — JSON do front → dataclass do motor.

## Por que este módulo existe, e por que fora do router

`POST /provar` e `POST /subir` passaram a aceitar UM objeto de configuração por
canal (`configuracao_search`, `configuracao_display`, `configuracao_demand_gen`,
`configuracao_pmax`). A regra de cada um — forma, enums, combinações que a API
recusa — já mora nos dataclasses do motor (`volc_ads/campanha/*_config.py`).
Este módulo é o ADAPTADOR entre as duas pontas, e só isso:

  * decide qual campo HTTP pertence a qual canal e recusa o do canal errado;
  * monta o dataclass pelo `de_json` do PRÓPRIO módulo do canal (não existe
    modelo Pydantic espelho — seriam quatro contratos paralelos divergindo);
  * traduz a recusa do motor em `ConfiguracaoRecusada`, com o CAMINHO do campo,
    que a rota devolve como 422;
  * publica o JSON Schema de cada configuração (`GET /canais/esquema`);
  * diz qual é a estratégia de lance EFETIVA (a da configuração, quando ela
    existe), porque o portão de mensuração precisa julgar a que vai ao Google;
  * aplica a correspondência por keyword que o operador escolheu
    (`match_por_keyword`) sobre o conjunto pago aprovado.

O router (`app/routers/trafego.py`) continua dono do HTTP — status, ordem dos
portões, resposta. Nenhuma regra de canal foi escrita lá.

⚠️ Os módulos `*_config` são stdlib pura: importar este arquivo no boot não
arrasta o SDK do Google. O `sys.path` é ajustado aqui pelo mesmo motivo de
`contrato_canais`: `volc_ads` mora fora de `backend/`.

⚠️ Por que não `adaptador_<canal>.py`: aqueles quatro são PERFIS DE VARREDURA
(leitura da conta para o inventário) e se registram no `sincronizador` no
import, que acontece de propósito só dentro de `resolver_perfil()`. Importá-los
daqui anteciparia esse registro para o boot do router — outra ordem de carga,
para uma responsabilidade que não é deles.
"""
from __future__ import annotations

import pathlib
import re
import sys
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

_RAIZ = pathlib.Path(__file__).resolve().parents[3]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from volc_ads.campanha import (  # noqa: E402 — depois do sys.path, de propósito
    config_json,
    demand_gen_config as dgc,
    display_config as dc,
    pmax_config as pc,
    search_config as sc,
)
from volc_ads.campanha.brief import (  # noqa: E402
    ROAS_MAX,
    ROAS_MIN,
    ConfiguracaoDemandGen,
    ConfiguracaoPMax,
    ImagensPMax,
    faixa_de_roas_invalida,
)

#: Versão do contrato publicado. Mesma string de `config_json`.
VERSAO = config_json.VERSAO_DO_CONTRATO

#: O campo HTTP de cada canal. UM por canal, e o canal é o do pedido.
CAMPO_POR_CANAL: Mapping[str, str] = {
    "SEARCH": "configuracao_search",
    "DISPLAY": "configuracao_display",
    "DEMAND_GEN": "configuracao_demand_gen",
    "PERFORMANCE_MAX": "configuracao_pmax",
}
CANAL_POR_CAMPO: Mapping[str, str] = {v: k for k, v in CAMPO_POR_CANAL.items()}

#: Onde a configuração entra no motor — a tela não precisa disto para montar o
#: formulário, mas precisa para explicar por que DG/PMax pedem DOIS objetos.
ENTRADA_NO_MOTOR: Mapping[str, str] = {
    "SEARCH": "search.construir(configuracao=ConfiguracaoSearch)",
    "DISPLAY": "display.construir(configuracao=ConfiguracaoDisplay)",
    "DEMAND_GEN": "brief.demand_gen = ConfiguracaoDemandGenV25 (base = objeto `demand_gen`)",
    "PERFORMANCE_MAX": "brief.pmax = ConfiguracaoPMaxV25 (base = objeto `pmax`)",
}

#: Códigos estáveis das recusas desta fronteira — `ctx.codigo` de TODO 422 de
#: configuração (§2 do contrato). A tela pode ramificar por eles; o `msg` é
#: para gente e pode mudar de redação.
CAMPO_DESCONHECIDO = config_json.CAMPO_DESCONHECIDO
CAMPO_OBRIGATORIO = config_json.CAMPO_OBRIGATORIO
VALOR_INVALIDO = config_json.VALOR_INVALIDO
#: Configuração (ou `match_por_keyword`) de um canal num pedido de outro.
CANAL_DIFERENTE = "CANAL_DIFERENTE"
#: Campo do envelope que o builder do canal pedido não materializa (ex.:
#: `match_type` num pedido Display). Recusado, nunca descartado.
CAMPO_NAO_OPERADO = "CAMPO_NAO_OPERADO"
#: `estrategia_lance` do envelope diverge de `configuracao_<canal>.lance`.
ESTRATEGIA_DIVERGENTE = "ESTRATEGIA_DIVERGENTE"
#: `match_por_keyword` com chave fora do conjunto pago aprovado.
MATCH_FORA_DO_CONJUNTO = "MATCH_FORA_DO_CONJUNTO"

CODIGOS_DE_RECUSA: Tuple[str, ...] = (
    CAMPO_DESCONHECIDO, CAMPO_OBRIGATORIO, VALOR_INVALIDO, CANAL_DIFERENTE,
    CAMPO_NAO_OPERADO, ESTRATEGIA_DIVERGENTE, MATCH_FORA_DO_CONJUNTO,
)

MATCH_TYPES: Tuple[str, ...] = ("EXACT", "PHRASE", "BROAD")


#: O erro de forma do motor — quem valida um pedaço que o JSON não representa
#: (o envelope de asset de um grupo PMax) levanta este, com o caminho.
ErroDeForma = config_json.ConfiguracaoInvalida


def _loc(caminho: str) -> Tuple[Any, ...]:
    """`configuracao_display.frequencia[0].impressoes` → partes do `loc`."""
    partes: List[Any] = []
    for pedaco in caminho.split("."):
        m = re.fullmatch(r"([^\[]+)((?:\[\d+\])*)", pedaco)
        if not m:
            partes.append(pedaco)
            continue
        partes.append(m.group(1))
        partes.extend(int(i) for i in re.findall(r"\[(\d+)\]", m.group(2)))
    return tuple(partes)


class ConfiguracaoRecusada(ValueError):
    """A configuração não tem a forma que o motor aceita. Vira 422 com caminho.

    Carrega UMA ou MAIS recusas (`itens`): o pedido com três campos que o
    builder não opera volta com os três, cada um no seu `loc` — a tela pinta
    os três campos de uma vez em vez de o operador descobrir um por rodada.
    `caminho`/`mensagem`/`codigo` são os do primeiro item.

    `tipo` é o `type` do item no 422 — por padrão o código em minúsculas; a
    projeção estrita de Demand Gen preserva o tipo nativo do pydantic
    (`extra_forbidden`, `too_long`…). Quem ramifica lê `ctx.codigo`, sempre.
    """

    def __init__(self, caminho: str, mensagem: str,
                 codigo: str = VALOR_INVALIDO, *, tipo: Optional[str] = None) -> None:
        self.caminho = caminho
        self.mensagem = mensagem
        self.codigo = codigo
        self.tipo = tipo or codigo.lower()
        self.itens: Tuple["ConfiguracaoRecusada", ...] = (self,)
        super().__init__(f"{caminho}: {mensagem}")

    @classmethod
    def varias(cls, recusas: Sequence["ConfiguracaoRecusada"]) -> "ConfiguracaoRecusada":
        if not recusas:  # pragma: no cover — chamador sempre tem ao menos uma
            raise ValueError("nenhuma recusa para levantar")
        primeira = recusas[0]
        exc = cls(primeira.caminho, primeira.mensagem, primeira.codigo,
                  tipo=primeira.tipo)
        exc.itens = tuple(recusas)
        if len(recusas) > 1:
            exc.args = (" | ".join(f"{r.caminho}: {r.mensagem}" for r in recusas),)
        return exc

    def loc(self) -> Tuple[Any, ...]:
        """`configuracao_display.frequencia[0].impressoes` → loc do FastAPI."""
        return ("body",) + _loc(self.caminho)

    def erros(self, *, prefixo: Tuple[Any, ...] = ("body",)) -> List[Dict[str, Any]]:
        """Os itens no formato de erro de corpo do FastAPI (§2 do contrato)."""
        return [{
            "type": r.tipo,
            "loc": prefixo + _loc(r.caminho),
            "msg": r.mensagem,
            "input": None,
            "ctx": {"codigo": r.codigo, "caminho": r.caminho},
        } for r in self.itens]

    def erro_de_validacao(self, titulo: str):
        """A mesma recusa como `pydantic_core.ValidationError`, com `loc` exato.

        Para o validador do ENVELOPE (`model_validator`): um `ValueError` solto
        ali vira `loc: ["body"]` com `msg: "Value error, …"` e sem `ctx` — o
        formato que o front encontrou e que este contrato não promete. Uma
        `ValidationError` levantada dentro do validador atravessa o pydantic
        com as linhas de erro intactas, e o FastAPI só acrescenta `body`.
        """
        from pydantic_core import InitErrorDetails, PydanticCustomError, ValidationError

        linhas = []
        for r in self.itens:
            # `{`/`}` no texto seriam lidos como marcador do template.
            frase = r.mensagem.replace("{", "(").replace("}", ")")
            linhas.append(InitErrorDetails(
                type=PydanticCustomError(r.tipo, frase,
                                         {"codigo": r.codigo, "caminho": r.caminho}),
                loc=_loc(r.caminho),
                input=None,
            ))
        return ValidationError.from_exception_data(titulo, linhas)

    def para_json(self) -> Dict[str, Any]:
        return {"codigo": self.codigo, "caminho": self.caminho,
                "mensagem": self.mensagem}


def exigir_target_roas(valor: Any) -> Any:
    """`target_roas` do envelope: razão em `ROAS_MIN..ROAS_MAX`, nos 4 canais.

    Levanta `PydanticCustomError` (para o `field_validator`): o 422 sai com
    `loc: ["body", "target_roas"]`, frase em português e `ctx.codigo =
    VALOR_INVALIDO` — o mesmo formato das recusas de configuração.
    """
    recusa = faixa_de_roas_invalida(valor)
    if recusa:
        from pydantic_core import PydanticCustomError

        raise PydanticCustomError(
            VALOR_INVALIDO.lower(), recusa.replace("{", "(").replace("}", ")"),
            {"codigo": VALOR_INVALIDO, "caminho": "target_roas"})
    return valor


def canal_canonico(canal: Any) -> str:
    bruto = str(canal or "SEARCH").strip().upper()
    return "PERFORMANCE_MAX" if bruto == "PMAX" else bruto


def campos_declarados(dados: Mapping[str, Any]) -> List[str]:
    """Os campos de configuração presentes (e não nulos) num corpo cru."""
    return [c for c in CAMPO_POR_CANAL.values()
            if c in dados and dados[c] is not None]


def recusar_de_outro_canal(dados: Mapping[str, Any]) -> None:
    """Configuração de canal diferente do `canal` do pedido é RECUSADA.

    Ignorar seria o defeito clássico desta rota: o operador manda segmentação
    de Display num pedido Search e vê um plano sem ela, sem erro nenhum.

    Uma recusa por campo (`loc` = o campo), todas de uma vez, código
    `CANAL_DIFERENTE`. `match_por_keyword` entra aqui pela mesma razão: é
    configuração de Search, e num pedido de outro canal seria descartada.
    """
    canal = canal_canonico(dados.get("canal"))
    recusas: List[ConfiguracaoRecusada] = []
    for campo in campos_declarados(dados):
        dono = CANAL_POR_CAMPO[campo]
        if dono != canal:
            recusas.append(ConfiguracaoRecusada(
                campo,
                f"`{campo}` é a configuração de {dono} e o pedido é "
                f"canal={canal}. Nada foi projetado: configuração de outro "
                "canal seria descartada em silêncio.",
                CANAL_DIFERENTE))
    if dados.get("match_por_keyword") and canal != "SEARCH":
        recusas.append(ConfiguracaoRecusada(
            "match_por_keyword",
            "`match_por_keyword` é correspondência de keyword POSITIVA, que só "
            f"Search opera; o pedido é canal={canal}. Nada foi projetado.",
            CANAL_DIFERENTE))
    if recusas:
        raise ConfiguracaoRecusada.varias(recusas)


def _traduzir(exc: config_json.ConfiguracaoInvalida) -> ConfiguracaoRecusada:
    return ConfiguracaoRecusada(exc.caminho, exc.mensagem,
                                getattr(exc, "codigo", VALOR_INVALIDO))


# ═══════════════════════════════════════════════════════════════════════════
# JSON → configuração do motor
# ═══════════════════════════════════════════════════════════════════════════


def de_search(dados: Mapping[str, Any]) -> sc.ConfiguracaoSearch:
    try:
        return sc.de_json(dict(dados), "configuracao_search")
    except config_json.ConfiguracaoInvalida as exc:
        raise _traduzir(exc) from exc


def de_display(dados: Mapping[str, Any]) -> dc.ConfiguracaoDisplay:
    try:
        return dc.de_json(dict(dados), "configuracao_display")
    except config_json.ConfiguracaoInvalida as exc:
        raise _traduzir(exc) from exc


def de_demand_gen(dados: Mapping[str, Any],
                  base: ConfiguracaoDemandGen) -> dgc.ConfiguracaoDemandGenV25:
    try:
        return dgc.de_json(dict(dados), base, "configuracao_demand_gen")
    except config_json.ConfiguracaoInvalida as exc:
        raise _traduzir(exc) from exc


def de_pmax(dados: Mapping[str, Any], base: ConfiguracaoPMax, *,
            imagens_do_grupo: Callable[[Any, str], ImagensPMax]) -> pc.ConfiguracaoPMaxV25:
    try:
        return pc.de_json(dict(dados), base, imagens_do_grupo=imagens_do_grupo,
                          caminho="configuracao_pmax")
    except config_json.ConfiguracaoInvalida as exc:
        raise _traduzir(exc) from exc


#: As bases NEUTRAS para julgar a FORMA antes da rede. A base de verdade (DG:
#: `demand_gen` da rota; PMax: com o recibo de mensuração lido no servidor) só
#: existe depois — e o `__post_init__` V25 não cruza campo da base, então a
#: neutra julga exatamente o mesmo que a real julgaria.
_BASE_DG_NEUTRA = ConfiguracaoDemandGen(
    upgraded_targeting=None, controles_de_canal=None, audiencias=None,
    intencoes=None, exclusoes_de_audiencia=None)
_BASE_PMAX_NEUTRA = ConfiguracaoPMax(
    brand_guidelines_enabled=None, mensuracao=None, sinais=None, negativas=None)


def validar_forma(corpo: Mapping[str, Any], *,
                  validar_envelope: Callable[[Any, str], None],
                  teto_por_grupo: int = 85) -> Dict[str, Any]:
    """Julga a FORMA de toda configuração declarada, antes de qualquer rede.

    Devolve `{campo: objeto montado}` (Search/Display prontos; DG/PMax com a
    base neutra — servem só como prova de forma). `validar_envelope(item,
    caminho)` confere cada envelope de asset dos grupos adicionais de PMax com
    o MESMO modelo da fronteira (`assets_pmax`).
    """
    recusar_de_outro_canal(corpo)
    saida: Dict[str, Any] = {}
    for campo in campos_declarados(corpo):
        dados = corpo[campo]
        if not isinstance(dados, Mapping):
            raise ConfiguracaoRecusada(campo, "esperado objeto JSON")  # VALOR_INVALIDO
        if campo == "configuracao_search":
            saida[campo] = de_search(dados)
        elif campo == "configuracao_display":
            saida[campo] = de_display(dados)
        elif campo == "configuracao_demand_gen":
            saida[campo] = de_demand_gen(dados, _BASE_DG_NEUTRA)
        else:
            def _so_forma(valor: Any, caminho: str) -> ImagensPMax:
                if not isinstance(valor, list):
                    raise config_json.ConfiguracaoInvalida(
                        caminho, "esperada lista de envelopes de asset")
                if len(valor) > teto_por_grupo:
                    raise config_json.ConfiguracaoInvalida(
                        caminho, f"{len(valor)} assets; o teto da fronteira é "
                        f"{teto_por_grupo} por grupo (protege a memória, não é "
                        "a régua do canal)")
                for i, item in enumerate(valor):
                    validar_envelope(item, f"{caminho}[{i}]")
                return ImagensPMax()
            saida[campo] = de_pmax(dados, _BASE_PMAX_NEUTRA,
                                   imagens_do_grupo=_so_forma)
    return saida


# ═══════════════════════════════════════════════════════════════════════════
# O que a configuração muda nas decisões que a rota toma
# ═══════════════════════════════════════════════════════════════════════════


def estrategia_efetiva(canal: Any, estrategia_lance: Any,
                       corpo: Mapping[str, Any]) -> str:
    """A estratégia que VAI AO GOOGLE — da configuração, quando declarada.

    O portão de mensuração (`prontidao.exigir_para_criacao`) julgava
    `body.estrategia_lance`. Com a configuração, um pedido Search com
    `estrategia_lance` no default (MANUAL_CPC) e `configuracao_search.lance =
    MAXIMIZE_CONVERSIONS` subiria em lance automático sem o portão ver —
    exatamente o caso que ele existe para barrar.
    """
    alvo = canal_canonico(canal)
    padrao = str(estrategia_lance or "MANUAL_CPC").strip().upper()
    campo = CAMPO_POR_CANAL.get(alvo)
    dados = corpo.get(campo) if campo else None
    lance = dados.get("lance") if isinstance(dados, Mapping) else None
    if isinstance(lance, Mapping) and str(lance.get("estrategia") or "").strip():
        return str(lance["estrategia"]).strip().upper()
    return padrao


def lance_da_configuracao(canal: Any, corpo: Mapping[str, Any]) -> Optional[str]:
    """A estratégia declarada em `configuracao_<canal>.lance`, ou None."""
    alvo = canal_canonico(canal)
    campo = CAMPO_POR_CANAL.get(alvo)
    dados = corpo.get(campo) if campo else None
    lance = dados.get("lance") if isinstance(dados, Mapping) else None
    if isinstance(lance, Mapping) and str(lance.get("estrategia") or "").strip():
        return str(lance["estrategia"]).strip().upper()
    return None


def rede_da_configuracao(corpo: Mapping[str, Any]) -> Optional[Dict[str, bool]]:
    """`configuracao_search.rede` no vocabulário de `brief.RedeDePesquisa`.

    O canário julga a rede (parceiros e expansão desligados). Se ela só
    existisse na configuração, `canario.exigir` olharia `body.rede=None` e
    recusaria por ausência — ou pior, um chamador mandaria a rede só aqui e o
    canário nunca a veria.
    """
    dados = corpo.get("configuracao_search")
    rede = dados.get("rede") if isinstance(dados, Mapping) else None
    if not isinstance(rede, Mapping):
        return None
    return {
        "google_search": bool(rede.get("google_search")),
        "search_partners": bool(rede.get("parceiros")),
        "display_expansion": bool(rede.get("display_expansion")),
    }


def tem_videos_sem_portao(canal: Any, corpo: Mapping[str, Any]) -> Tuple[str, ...]:
    """Ids de YouTube declarados na configuração — que o portão de política não lê.

    O portão criativo julga BYTES. Um id público do YouTube não tem bytes no
    servidor: não há `content_sha256`, inspeção nem recibo. Os builders criam o
    asset por id no mesmo mutate (medido e aceito pela API), e a decisão do dono
    é que vídeo vive dentro de Demand Gen e PMax. A rota NÃO os recusa — e por
    isso precisa DIZER que eles atravessam sem o portão. A lista vai num aviso
    do plano, e os ids estão na impressão aprovável (a configuração entra nela).
    """
    alvo = canal_canonico(canal)
    dados = corpo.get(CAMPO_POR_CANAL.get(alvo, ""), None)
    if not isinstance(dados, Mapping):
        return ()
    ids: List[str] = []
    if alvo == "DISPLAY":
        ids += list((dados.get("anuncio") or {}).get("videos_youtube") or ())
    elif alvo == "DEMAND_GEN":
        ids += list((dados.get("video") or {}).get("youtube_ids") or ())
    elif alvo == "PERFORMANCE_MAX":
        ids += [v.get("video_id") for v in (dados.get("videos") or ())
                if isinstance(v, Mapping)]
        for g in dados.get("grupos_adicionais") or ():
            if isinstance(g, Mapping):
                ids += [v.get("video_id") for v in (g.get("videos") or ())
                        if isinstance(v, Mapping)]
    return tuple(dict.fromkeys(str(i) for i in ids if i))


def exigencia_de_imagens_demand_gen(dados: Optional[Mapping[str, Any]]):
    """A régua de IMAGEM do lote Demand Gen quando o formato não é multi-asset.

    `requisitos.exigencia_binaria_de("DEMAND_GEN")` descreve o multi-asset:
    imagem base (paisagem ou quadrada) obrigatória. Vídeo responsivo e
    carrossel têm UM campo de imagem no anúncio — o logo quadrado — e o builder
    recusa qualquer outra imagem nesses formatos. Validar o lote do vídeo pela
    régua do multi-asset exigiria uma imagem que o builder recusaria em seguida.

    A projeção é um RECORTE da exigência do dono (`criativo/requisitos.py`),
    não uma régua nova: mantém a especificação do logo quadrado inteira e só os
    tetos combinados que tratam exclusivamente dele. `None` = multi-asset, a
    régua de sempre.
    """
    formato = str((dados or {}).get("formato") or "MULTI_ASSET").strip().upper()
    if formato == "MULTI_ASSET":
        return None
    from volc_ads.criativo import requisitos
    from volc_ads.criativo.contrato import TipoDeAsset

    base = requisitos.exigencia_binaria_de("DEMAND_GEN")
    logo = TipoDeAsset.LOGO_QUADRADO
    return replace(
        base,
        especificacoes=tuple(s for s in base.especificacoes if s.tipo is logo),
        combinados=tuple(c for c in base.combinados
                         if c.tipos and set(c.tipos) <= {logo}),
    )


def exigencia_de_imagens_pmax_grupo_adicional(brand_guidelines_enabled: Any):
    """A régua de IMAGEM de um asset group ADICIONAL de PMax.

    Com brand guidelines LIGADO, LOGO e LANDSCAPE_LOGO são assets da CAMPANHA
    (vêm do grupo 0), e o builder recusa logo no grupo adicional
    (`BRAND_ASSETS_NOT_LINKED_AT_CAMPAIGN_LEVEL`). A régua padrão do Estúdio
    exige logo em todo lote PMax — e recusaria o grupo que o builder aceita.
    Recorte da exigência do dono, sem número novo. Desligado: régua de sempre.
    """
    if brand_guidelines_enabled is not True:
        return None
    from volc_ads.criativo import requisitos
    from volc_ads.criativo.contrato import TipoDeAsset

    base = requisitos.exigencia_binaria_de("PERFORMANCE_MAX")
    logos = {TipoDeAsset.LOGO_QUADRADO, TipoDeAsset.LOGO_PAISAGEM}
    return replace(
        base,
        especificacoes=tuple(s for s in base.especificacoes if s.tipo not in logos),
        combinados=tuple(c for c in base.combinados
                         if not (set(c.tipos) & logos)),
    )


# ═══════════════════════════════════════════════════════════════════════════
# A correspondência por keyword (o furo do seletor de match type)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TrocaDeMatch:
    texto: str
    de: str
    para: str


def aplicar_match_por_keyword(
    criterios_aprovados: Sequence[Any], mapa: Optional[Mapping[str, str]],
) -> Tuple[List[Any], Tuple[TrocaDeMatch, ...]]:
    """A correspondência que o operador escolheu, sobre as positivas APROVADAS.

    ## O furo que isto fecha

    A tela tem um seletor de correspondência por keyword (`MesaDeCriterios`,
    `rascunho.matchPorKeyword`, chave = texto normalizado). O pedido nunca o
    carregava: as positivas vêm do conjunto pago aprovado, e o corpo recusa
    positiva. A tela passou a mostrar o seletor como "somente leitura" — o
    operador via EXACT, trocava, e o Google recebia o match do conjunto.

    ## O que é permitido, e o que continua fechado

    * Só TROCA a correspondência de keyword que JÁ está no conjunto aprovado.
      Não acrescenta, não retira, não duplica: a cardinalidade do conjunto é
      a que foi aprovada (é ela que o defeito de 4 positivas alterava).
    * Chave que não está no conjunto é RECUSADA, e não ignorada.
    * BROAD sob lance manual continua recusado — pelo `Brief`, não aqui.
    * A troca entra na impressão aprovável (`match_por_keyword` participa do
      plano quando preenchido) e é conferida no brief FINAL contra esta mesma
      lista — `conferir_positivas_do_brief` recebe o conjunto já trocado.
    """
    if not mapa:
        return list(criterios_aprovados), ()
    from volc_ads.campanha.criterio import chave as _chave

    pedido: Dict[str, str] = {}
    for k, v in mapa.items():
        mt = str(v or "").strip().upper()
        if mt not in MATCH_TYPES:
            raise ConfiguracaoRecusada(
                f"match_por_keyword.{k}", f"correspondência {v!r} inválida — use "
                f"{', '.join(MATCH_TYPES)}", VALOR_INVALIDO)
        pedido[_chave(str(k))] = mt
    aprovadas = {c.chave for c in criterios_aprovados if not c.negativa}
    fora = sorted(set(pedido) - aprovadas)
    if fora:
        raise ConfiguracaoRecusada(
            f"match_por_keyword.{fora[0]}",
            f"{len(fora)} keyword(s) fora do conjunto aprovado: {fora[:5]}. A "
            "correspondência só pode ser trocada em keyword aprovada — "
            "acrescentar positiva exige aprovar o conjunto de novo.",
            MATCH_FORA_DO_CONJUNTO)
    saida: List[Any] = []
    trocas: List[TrocaDeMatch] = []
    for c in criterios_aprovados:
        novo = pedido.get(c.chave) if not c.negativa else None
        if novo and novo != c.match_type:
            trocas.append(TrocaDeMatch(c.texto, c.match_type, novo))
            saida.append(replace(c, match_type=novo))
        else:
            saida.append(c)
    return saida, tuple(trocas)


# ═══════════════════════════════════════════════════════════════════════════
# O esquema publicado
# ═══════════════════════════════════════════════════════════════════════════


def esquemas(*, esquema_de_asset: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """O contrato que a tela lê para desenhar os quatro formulários.

    Cada esquema é DERIVADO das anotações do dataclass do motor + o vocabulário
    do módulo do canal (`ESQUEMA_JSON`): enums, limites e defaults saem do
    mesmo lugar que a validação usa.
    """
    imagens = None
    if esquema_de_asset is not None:
        imagens = {
            "type": "array",
            "items": dict(esquema_de_asset),
            "description": pc.ESQUEMA_IMAGENS_PADRAO["description"],
        }
    por_canal = {
        "SEARCH": sc.esquema_json(),
        "DISPLAY": dc.esquema_json(),
        "DEMAND_GEN": dgc.esquema_json(),
        "PERFORMANCE_MAX": pc.esquema_json(esquema_de_imagens=imagens),
    }
    return {
        "versao": VERSAO,
        "documento": "docs/contracts/GADS-CRIACAO-CANAIS-v1.md",
        "canais": {
            canal: {
                "campo_http": CAMPO_POR_CANAL[canal],
                "entra_no_motor_como": ENTRADA_NO_MOTOR[canal],
                "esquema": esquema,
            }
            for canal, esquema in por_canal.items()
        },
        "regras": [
            "um objeto por canal, e só o do `canal` do pedido (outro canal → 422)",
            "chave desconhecida → 422 com o caminho do campo (nunca descarte)",
            "tipo errado → 422; não há coerção ('3' não vira 3, 1 não vira true)",
            "omitir o objeto = comportamento de antes desta versão (payload idêntico)",
            "objeto presente entra na impressão aprovável do plano",
            "todo 422 de configuração: detail[] com loc do campo, msg sem "
            "prefixo e ctx.codigo em " + ", ".join(CODIGOS_DE_RECUSA),
            f"target_roas é razão (4.0 = 400%) em [{ROAS_MIN}, {ROAS_MAX}] "
            "nos quatro canais",
        ],
    }
