"""JSON ⇄ configuração de canal — a forma é a do PRÓPRIO dataclass do motor.

## Por que este módulo existe

As quatro configurações de canal (`search_config.ConfiguracaoSearch`,
`display_config.ConfiguracaoDisplay`, `demand_gen_config.
ConfiguracaoDemandGenV25`, `pmax_config.ConfiguracaoPMaxV25`) são dataclasses
congelados que recusam combinação impossível no `__post_init__`. A rota HTTP
precisa montá-las a partir do JSON do front, e a tela precisa de um JSON Schema
para desenhar o formulário.

A tentação é escrever um modelo Pydantic espelho para cada uma. Seriam QUATRO
contratos paralelos que divergem no primeiro campo que só um ganhar — o defeito
que `automacoes.py` e `perfil.py` já documentam. Aqui a única autoridade de
forma é o dataclass: `de_dict` lê as anotações de tipo dele, monta os objetos
aninhados e deixa o `__post_init__` do próprio motor julgar. `esquema` lê as
mesmas anotações (mais o vocabulário que cada módulo declara em
`ESQUEMA_JSON`) e projeta o JSON Schema que a tela consome.

## As três regras da travessia

1. **Chave desconhecida é ERRO, nunca descarte.** Um campo com erro de grafia
   que some em silêncio é uma decisão do operador que não chega ao payload.
2. **O erro carrega o CAMINHO.** `configuracao_display.exclusoes.placement`
   e não "campo inválido": a tela precisa apontar o campo do formulário.
3. **Tipo errado é erro, não coerção.** `"3"` não vira `3`, `1` não vira `True`.
   Coerção é o caminho pelo qual "0/1" substituiria uma escolha imutável — o
   que `ConfiguracaoPMax.brand_guidelines_enabled` já recusa.

Stdlib pura, de propósito: o backend importa isto no boot e não pode arrastar
o SDK do Google.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
import types
import typing
from collections.abc import Mapping as _MappingABC
from typing import Any, Callable, Iterable, Mapping

#: Versão do contrato publicado em `docs/contracts/GADS-CRIACAO-CANAIS-v1.md`.
VERSAO_DO_CONTRATO = "GADS-CRIACAO-CANAIS-v1.1"

Resolvedor = Callable[[Any, str], Any]

_NADA = type(None)


#: Códigos estáveis da recusa de FORMA (`ctx.codigo` do 422). A tela pode
#: ramificar por eles; a frase (`msg`) é para gente e pode mudar.
CAMPO_DESCONHECIDO = "CAMPO_DESCONHECIDO"  # chave que o dataclass não tem
CAMPO_OBRIGATORIO = "CAMPO_OBRIGATORIO"    # campo sem default, ausente
VALOR_INVALIDO = "VALOR_INVALIDO"          # tipo, enum, faixa ou combinação


class ConfiguracaoInvalida(ValueError):
    """A configuração não tem a forma que o dataclass do motor aceita.

    `caminho` é o endereço do campo no JSON (`configuracao_search.lance.
    estrategia`), e é ele que a fronteira HTTP devolve no 422. `codigo` é o
    motivo estável (`CAMPO_DESCONHECIDO`, `CAMPO_OBRIGATORIO`,
    `VALOR_INVALIDO`).
    """

    def __init__(self, caminho: str, mensagem: str,
                 codigo: str = VALOR_INVALIDO) -> None:
        self.caminho = caminho
        self.mensagem = mensagem
        self.codigo = codigo
        super().__init__(f"{caminho}: {mensagem}")


# ═══════════════════════════════════════════════════════════════════════════
# JSON → dataclass
# ═══════════════════════════════════════════════════════════════════════════


def campos_de_entrada(cls: type) -> tuple[dataclasses.Field, ...]:
    return tuple(f for f in dataclasses.fields(cls) if f.init)


def campos_proprios(cls: type, base: type) -> tuple[str, ...]:
    """Os campos que `cls` acrescenta à `base` — a parte V25 de uma extensão."""
    herdados = {f.name for f in dataclasses.fields(base)}
    return tuple(f.name for f in campos_de_entrada(cls) if f.name not in herdados)


def de_dict(
    cls: type,
    dados: Any,
    caminho: str = "configuracao",
    *,
    apenas: Iterable[str] | None = None,
    fixos: Mapping[str, Any] | None = None,
    resolvedores: Mapping[Any, Resolvedor] | None = None,
) -> Any:
    """Monta `cls` a partir de um objeto JSON. Levanta `ConfiguracaoInvalida`.

    `apenas` restringe as chaves aceitas do JSON (as de uma extensão V25, cuja
    base vem de outro lugar); `fixos` completa o construtor com o que não veio
    do JSON. `resolvedores` traduz tipos que não são representáveis em JSON —
    `ImagensPMax` carrega bytes e recibo, e quem os produz é o portão de
    política + a ponte criativa, nunca o JSON.
    """
    if not isinstance(dados, dict):
        raise ConfiguracaoInvalida(
            caminho, f"esperado objeto JSON, veio {_nome_json(dados)}")
    resolvedores = dict(resolvedores or {})
    if cls in resolvedores:
        return resolvedores[cls](dados, caminho)
    if not dataclasses.is_dataclass(cls):
        raise ConfiguracaoInvalida(caminho, f"{cls!r} não é dataclass")

    entrada = {f.name: f for f in campos_de_entrada(cls)}
    aceitos = set(apenas) if apenas is not None else set(entrada)
    sobra = sorted(set(dados) - aceitos)
    if sobra:
        raise ConfiguracaoInvalida(
            f"{caminho}.{sobra[0]}",
            f"campo(s) desconhecido(s) {sobra} — aceitos: {sorted(aceitos)}. "
            "Chave desconhecida é erro, não descarte: ela seria uma decisão "
            "que não chega ao payload", CAMPO_DESCONHECIDO)

    dicas = _dicas(cls)
    kw: dict[str, Any] = {}
    for nome in sorted(aceitos):
        campo = entrada.get(nome)
        if campo is None:  # pragma: no cover — `apenas` fora do dataclass
            raise ConfiguracaoInvalida(f"{caminho}.{nome}", "campo inexistente")
        sub = f"{caminho}.{nome}"
        if nome not in dados:
            if _obrigatorio(campo):
                raise ConfiguracaoInvalida(
                    sub, "campo obrigatório ausente — não há default seguro",
                    CAMPO_OBRIGATORIO)
            continue
        kw[nome] = _converter(dicas[nome], dados[nome], sub, resolvedores)
    kw.update(dict(fixos or {}))
    try:
        return cls(**kw)
    except ConfiguracaoInvalida:
        raise
    except (ValueError, TypeError) as exc:
        raise ConfiguracaoInvalida(caminho, str(exc)) from exc


def _obrigatorio(campo: dataclasses.Field) -> bool:
    return (campo.default is dataclasses.MISSING
            and campo.default_factory is dataclasses.MISSING)


def _dicas(cls: type) -> dict[str, Any]:
    # Sem `globalns`: cada classe da MRO resolve as anotações no PRÓPRIO
    # módulo — `ConfiguracaoDemandGenV25` herda campos anotados em `brief.py`.
    return typing.get_type_hints(cls)


def _nome_json(valor: Any) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "booleano"
    if isinstance(valor, (int, float)):
        return "número"
    if isinstance(valor, str):
        return "texto"
    if isinstance(valor, (list, tuple)):
        return "lista"
    if isinstance(valor, dict):
        return "objeto"
    return type(valor).__name__


def _uniao(tipo: Any) -> tuple[Any, ...] | None:
    origem = typing.get_origin(tipo)
    if origem is typing.Union or origem is types.UnionType:
        return typing.get_args(tipo)
    return None


def _cabe(tipo: Any, valor: Any) -> bool:
    """O valor JSON tem a FORMA que este tipo aceita? (Para escolher na união.)"""
    origem = typing.get_origin(tipo) or tipo
    if valor is None:
        return tipo is _NADA
    if isinstance(valor, bool):
        return tipo is bool
    if isinstance(valor, (int, float)):
        return tipo in (int, float) and not (tipo is int and isinstance(valor, float))
    if isinstance(valor, str):
        return tipo is str
    if isinstance(valor, list):
        return origem in (tuple, list, frozenset, set)
    if isinstance(valor, dict):
        return (dataclasses.is_dataclass(tipo)
                or origem in (dict, _MappingABC, typing.Mapping))
    return False


def _converter(tipo: Any, valor: Any, caminho: str,
               resolvedores: Mapping[Any, Resolvedor]) -> Any:
    if tipo in resolvedores:
        return resolvedores[tipo](valor, caminho)
    if tipo is Any:
        return valor

    membros = _uniao(tipo)
    if membros is not None:
        if valor is None:
            if _NADA in membros:
                return None
            raise ConfiguracaoInvalida(caminho, "null não é aceito aqui")
        candidatos = [m for m in membros if m is not _NADA]
        for m in candidatos:
            if m in resolvedores:
                return resolvedores[m](valor, caminho)
        cabem = [m for m in candidatos if _cabe(m, valor)]
        if len(cabem) == 1:
            return _converter(cabem[0], valor, caminho, resolvedores)
        if len(candidatos) == 1:
            return _converter(candidatos[0], valor, caminho, resolvedores)
        if not cabem:
            raise ConfiguracaoInvalida(
                caminho, f"{_nome_json(valor)} não cabe em nenhuma das formas "
                f"aceitas ({_descrever(tipo)})")
        nomes = ", ".join(getattr(m, "__name__", str(m)) for m in cabem)
        raise ConfiguracaoInvalida(
            caminho, f"o valor é ambíguo entre {nomes} e nenhum deles é "
            "representável em JSON nesta fronteira")

    if valor is None:
        raise ConfiguracaoInvalida(
            caminho, "null não é aceito aqui — ausência é omitir a chave")

    if tipo is bool:
        if not isinstance(valor, bool):
            raise ConfiguracaoInvalida(
                caminho, f"esperado booleano, veio {_nome_json(valor)} — 0/1 não "
                "substituem uma escolha declarada")
        return valor
    if tipo is int:
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ConfiguracaoInvalida(
                caminho, f"esperado inteiro, veio {_nome_json(valor)}")
        return valor
    if tipo is float:
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ConfiguracaoInvalida(
                caminho, f"esperado número, veio {_nome_json(valor)}")
        return float(valor)
    if tipo is str:
        if not isinstance(valor, str):
            raise ConfiguracaoInvalida(
                caminho, f"esperado texto, veio {_nome_json(valor)}")
        return valor
    if tipo is bytes:
        raise ConfiguracaoInvalida(
            caminho, "bytes não atravessam esta fronteira em JSON")

    origem = typing.get_origin(tipo)
    args = typing.get_args(tipo)
    if origem in (tuple, list, frozenset, set):
        if not isinstance(valor, (list, tuple)):
            raise ConfiguracaoInvalida(
                caminho, f"esperada lista, veio {_nome_json(valor)}")
        if origem is tuple and args and not (len(args) == 2 and args[1] is Ellipsis):
            if len(valor) != len(args):
                raise ConfiguracaoInvalida(
                    caminho, f"esperada lista de {len(args)} itens, veio "
                    f"{len(valor)}")
            return tuple(_converter(a, v, f"{caminho}[{i}]", resolvedores)
                         for i, (a, v) in enumerate(zip(args, valor)))
        item = args[0] if args else Any
        itens = [_converter(item, v, f"{caminho}[{i}]", resolvedores)
                 for i, v in enumerate(valor)]
        if origem in (frozenset, set):
            return frozenset(itens)
        return list(itens) if origem is list else tuple(itens)
    if origem in (dict, _MappingABC) or tipo in (dict, typing.Mapping):
        if not isinstance(valor, dict):
            raise ConfiguracaoInvalida(
                caminho, f"esperado objeto, veio {_nome_json(valor)}")
        k_tipo, v_tipo = (args + (Any, Any))[:2] if args else (Any, Any)
        return {
            _converter(k_tipo, k, f"{caminho}.{k}", resolvedores):
                _converter(v_tipo, v, f"{caminho}.{k}", resolvedores)
            for k, v in valor.items()
        }
    if dataclasses.is_dataclass(tipo):
        return de_dict(tipo, valor, caminho, resolvedores=resolvedores)
    if isinstance(tipo, type) and isinstance(valor, tipo):
        return valor
    raise ConfiguracaoInvalida(
        caminho, f"tipo {_descrever(tipo)} não é representável em JSON nesta "
        "fronteira")


def _descrever(tipo: Any) -> str:
    return getattr(tipo, "__name__", None) or str(tipo).replace("typing.", "")


# ═══════════════════════════════════════════════════════════════════════════
# dataclass → JSON (o inverso, para eco e para os defaults do esquema)
# ═══════════════════════════════════════════════════════════════════════════


def para_json(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: para_json(getattr(obj, f.name))
                for f in dataclasses.fields(obj)}
    if isinstance(obj, (tuple, list)):
        return [para_json(x) for x in obj]
    if isinstance(obj, (frozenset, set)):
        return sorted(para_json(x) for x in obj)
    if isinstance(obj, dict):
        return {str(k): para_json(v) for k, v in obj.items()}
    return obj


# ═══════════════════════════════════════════════════════════════════════════
# dataclass → JSON Schema (o que a tela lê para desenhar o formulário)
# ═══════════════════════════════════════════════════════════════════════════


def esquema(
    cls: type,
    *,
    apenas: Iterable[str] | None = None,
    metadados: Mapping[str, Mapping[str, Any]] | None = None,
    sobrescritas: Mapping[Any, Mapping[str, Any]] | None = None,
    titulo: str | None = None,
    extras: Mapping[str, Any] | None = None,
) -> dict:
    """JSON Schema (draft 2020-12) da configuração, derivado das anotações.

    `metadados` é o vocabulário do módulo do canal (`ESQUEMA_JSON`), indexado
    por `"Classe.campo"`: enums, limites e padrões que a anotação de tipo não
    carrega. `sobrescritas` troca o esquema de um TIPO inteiro — é por ela que
    `ImagensPMax` vira a lista de envelopes de asset da fronteira HTTP.
    """
    defs: dict[str, dict] = {}
    raiz = _esquema_de_classe(cls, defs, dict(metadados or {}),
                              dict(sobrescritas or {}), apenas=apenas)
    out: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": titulo or cls.__name__,
        **raiz,
    }
    if defs:
        out["$defs"] = dict(sorted(defs.items()))
    out.update(dict(extras or {}))
    return out


def _descricao_da_classe(cls: type) -> str:
    doc = inspect.getdoc(cls) or ""
    primeiro = doc.split("\n\n", 1)[0].strip()
    # O docstring automático do dataclass (`Nome(campo: tipo, …)`) não é
    # descrição de ninguém.
    if primeiro.startswith(f"{cls.__name__}("):
        return ""
    return " ".join(primeiro.split())


_COMENTARIO = re.compile(r"^\s*#:\s?(.*)$")
_CAMPO = re.compile(r"^\s{4}([a-z_][a-z0-9_]*)\s*:")


def _comentarios_dos_campos(cls: type) -> dict[str, str]:
    """Os `#:` que precedem cada campo no corpo da classe — a ajuda da tela."""
    try:
        linhas = inspect.getsource(cls).splitlines()
    except (OSError, TypeError):  # pragma: no cover — classe sem fonte
        return {}
    saida: dict[str, str] = {}
    acumulado: list[str] = []
    for linha in linhas[1:]:
        m = _COMENTARIO.match(linha)
        if m:
            acumulado.append(m.group(1).strip())
            continue
        c = _CAMPO.match(linha)
        if c and acumulado:
            saida[c.group(1)] = " ".join(t for t in acumulado if t)
        acumulado = []
    return saida


def _esquema_de_classe(cls: type, defs: dict, meta: dict, sobre: dict, *,
                       apenas: Iterable[str] | None = None) -> dict:
    dicas = _dicas(cls)
    comentarios = _comentarios_dos_campos(cls)
    nomes = set(apenas) if apenas is not None else None
    props: dict[str, Any] = {}
    obrigatorios: list[str] = []
    for f in campos_de_entrada(cls):
        if nomes is not None and f.name not in nomes:
            continue
        s = _esquema_de_tipo(dicas[f.name], defs, meta, sobre)
        extra = meta.get(f"{cls.__name__}.{f.name}")
        substituido = bool(extra and "$substituir" in extra)
        if substituido:
            # Campo cuja anotação é união de formas legadas (ex.: automações de
            # Demand Gen, `Mapping | tuple[par]`): o esquema publicado é a forma
            # CANÔNICA, e o vocabulário a declara inteira.
            s = dict(extra["$substituir"])
        elif extra:
            s = _mesclar(s, extra)
        if f.name in comentarios and "description" not in s:
            s = {**s, "description": comentarios[f.name]}
        if _obrigatorio(f):
            obrigatorios.append(f.name)
        elif substituido and "default" in s:
            # ⚠️ A forma canônica declara o PRÓPRIO default, e ele vence o do
            # dataclass. O default do dataclass está na forma interna (`()`,
            # tupla de pares — hashável para o selo), e `para_json(())` é `[]`:
            # publicar `type: object` com `default: []` mandava a tela montar
            # uma lista onde o servidor exige objeto (achado do front, 08/10).
            pass
        else:
            padrao = (f.default if f.default is not dataclasses.MISSING
                      else f.default_factory())
            s = {**s, "default": para_json(padrao)}
        props[f.name] = s
    out: dict[str, Any] = {"type": "object", "properties": props,
                           "additionalProperties": False}
    if obrigatorios:
        out["required"] = obrigatorios
    desc = _descricao_da_classe(cls)
    if desc:
        out["description"] = desc
    return out


def _mesclar(base: dict, extra: Mapping[str, Any]) -> dict:
    """Aplica o vocabulário ao esquema do campo, atravessando `anyOf` e `items`."""
    if "anyOf" in base:
        de_ramo = {k: v for k, v in extra.items() if k not in ("description", "x-volc")}
        ramos = []
        for r in base["anyOf"]:
            ramos.append(r if r.get("type") == "null" else _mesclar(r, de_ramo))
        out = {**base, "anyOf": ramos}
        for chave in ("description", "x-volc"):
            if chave in extra:
                out[chave] = extra[chave]
        return out
    out = dict(base)
    for chave, valor in extra.items():
        if chave == "items" and isinstance(valor, Mapping) and isinstance(out.get("items"), dict):
            out["items"] = _mesclar(out["items"], valor)
        else:
            out[chave] = valor
    return out


def _esquema_de_tipo(tipo: Any, defs: dict, meta: dict, sobre: dict) -> dict:
    if tipo in sobre:
        return dict(sobre[tipo])
    if tipo is Any:
        return {}
    membros = _uniao(tipo)
    if membros is not None:
        sem_nada = [m for m in membros if m is not _NADA]
        ramos = []
        for m in sem_nada:
            if m in sobre:
                ramos.append(dict(sobre[m]))
            else:
                ramos.append(_esquema_de_tipo(m, defs, meta, sobre))
        unicos: list[dict] = []
        for r in ramos:  # duas formas iguais (ex.: duas recusas) viram uma
            if r not in unicos:
                unicos.append(r)
        if _NADA in membros:
            unicos.append({"type": "null"})
        return unicos[0] if len(unicos) == 1 else {"anyOf": unicos}
    if tipo is bool:
        return {"type": "boolean"}
    if tipo is int:
        return {"type": "integer"}
    if tipo is float:
        return {"type": "number"}
    if tipo is str:
        return {"type": "string"}
    if tipo is bytes:
        return {"not": {}, "description": "bytes não atravessam a fronteira JSON"}
    origem = typing.get_origin(tipo)
    args = typing.get_args(tipo)
    if origem in (tuple, list, frozenset, set):
        if origem is tuple and args and not (len(args) == 2 and args[1] is Ellipsis):
            return {"type": "array",
                    "prefixItems": [_esquema_de_tipo(a, defs, meta, sobre) for a in args],
                    "minItems": len(args), "maxItems": len(args)}
        s = {"type": "array",
             "items": _esquema_de_tipo(args[0] if args else Any, defs, meta, sobre)}
        if origem in (frozenset, set):
            s["uniqueItems"] = True
        return s
    if origem in (dict, _MappingABC) or tipo in (dict, typing.Mapping):
        v = args[1] if len(args) == 2 else Any
        return {"type": "object",
                "additionalProperties": _esquema_de_tipo(v, defs, meta, sobre)}
    if dataclasses.is_dataclass(tipo):
        nome = tipo.__name__
        if nome not in defs:
            defs[nome] = {}  # reserva: tipos recursivos não entram em laço
            defs[nome] = _esquema_de_classe(tipo, defs, meta, sobre)
        return {"$ref": f"#/$defs/{nome}"}
    return {"description": f"tipo {_descrever(tipo)} não representável em JSON",
            "not": {}}
